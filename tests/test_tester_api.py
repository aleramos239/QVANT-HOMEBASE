"""The tester routes on the chart service: schema list, run lifecycle, Origin + Host checks."""
from __future__ import annotations

import datetime as dt
import subprocess
import threading
import time

from fastapi.testclient import TestClient

from homebase.backtest import runner
from homebase.charts.server import create_app
from tests.backtest_util import D1, nq_archive

EVIL = {"origin": "https://evil.example"}
REBIND_HOST = {"host": "evil.example"}
RUN = {"strategy": "nq930", "inputs": {"adx_gate": False},
       "range": {"kind": "custom", "start": "2024-03-01", "end": "2024-03-31"}}


def app(tmp_path):
    return create_app(roots=["NQ"], base=nq_archive(tmp_path / "ticks"), replay=D1, speed=1,
                      start_et=dt.time(9, 30), state=tmp_path / "state")


def client(tmp_path):
    """A TestClient whose default Host header is this loopback service's own —
    a real browser request to :8852 always carries it, so ordinary calls in
    these tests need no extra headers to pass the Host allowlist."""
    return TestClient(app(tmp_path), base_url="http://localhost:8852")


def poll(c, rid, s=30.0):
    t = time.monotonic() + s
    while time.monotonic() < t:
        st = c.get(f"/api/tester/run/{rid}").json()
        if st["status"] in ("done", "error", "cancelled"):
            return st
        time.sleep(0.05)
    raise AssertionError("run never finished")


def test_strategies_lists_the_schemas(tmp_path):
    with client(tmp_path) as c:
        got = {s["id"]: s for s in c.get("/api/tester/strategies").json()}
        assert set(got) == {"nq930", "ym930", "nq10am", "gc_nfpcpi"}
        assert got["nq930"]["inputs"][0]["key"] == "offset_pts"


def test_prop_rule_sets_are_listed_with_the_unconfirmed_flag(tmp_path):
    with client(tmp_path) as c:
        rules = {r["id"]: r for r in c.get("/api/tester/prop-rules").json()}
        assert rules["lucid-flex-50k@2026-08"]["confirmed"] is True
        assert rules["apex-50k@unconfirmed"]["confirmed"] is False
        r = c.post("/api/tester/run", json={**RUN, "prop_rules": "nope@1"})
        assert r.status_code == 400 and "prop_rules" in r.json()["detail"]


def test_a_run_goes_from_post_to_bundle(tmp_path):
    with client(tmp_path) as c:
        rid = c.post("/api/tester/run", json=RUN, headers={"origin": "http://localhost:8852"}).json()["id"]
        assert poll(c, rid)["status"] == "done"
        b = c.get(f"/api/tester/run/{rid}/bundle").json()
        assert b["run"]["coverage"]["skipped_by_reason"] == {"missing 13:00–16:00 ET": 1}
        assert len(b["trades"]) == 1 and b["equity"]["equity"] == [b["trades"][0]["net"]]
        assert b["propsim"]["rules"]["label"] == "LucidFlex 50K" and "headline" in b["propsim"]
        assert c.get("/api/tester/runs").json()[0]["id"] == rid
        assert (tmp_path / "state" / "tester" / "runs" / rid / "run.json").exists()


def test_writes_from_another_site_are_refused(tmp_path):
    with client(tmp_path) as c:
        assert c.post("/api/tester/run", json=RUN, headers=EVIL).status_code == 403
        assert c.get("/api/tester/runs").json() == []


def test_bad_requests_and_unknown_runs(tmp_path):
    with client(tmp_path) as c:
        r = c.post("/api/tester/run", json={**RUN, "range": {"kind": "custom", "start": "2025-01-02",
                                                               "end": "2025-02-01"}})
        assert r.status_code == 400 and "Holdout" in r.json()["detail"]
        assert c.post("/api/tester/run", json={**RUN, "strategy": "zz"}).status_code == 400
        assert c.get("/api/tester/run/20260926-120000-nq930-abcd").status_code == 404
        assert c.get("/api/tester/run/..%2F..%2Fetc").status_code == 404
        assert c.post("/api/tester/run/20260926-120000-nq930-abcd/cancel").status_code == 404
        rid = c.post("/api/tester/run", json=RUN).json()["id"]
        poll(c, rid)
        assert c.post(f"/api/tester/run/{rid}/cancel", headers=EVIL).status_code == 403
        assert c.post(f"/api/tester/run/{rid}/cancel").json()["status"] == "done"   # already final


def test_a_rebinding_host_is_refused_on_writes_and_the_bundle(tmp_path):
    """DNS-rebinding defence (review amendment): a request whose Origin agrees
    with its (rebound) Host must still be refused, because the Host itself is
    not this loopback service — origin_ok's `o == h` rule alone would pass it."""
    with client(tmp_path) as c:
        same_site = {"origin": "http://evil.example", **REBIND_HOST}
        assert c.post("/api/tester/run", json=RUN, headers=same_site).status_code == 403
        rid = c.post("/api/tester/run", json=RUN).json()["id"]
        poll(c, rid)
        assert c.post(f"/api/tester/run/{rid}/cancel", headers=same_site).status_code == 403
        assert c.get(f"/api/tester/run/{rid}/bundle", headers=REBIND_HOST).status_code == 403
        # the same route succeeds once Host is genuinely this service's own
        assert c.get(f"/api/tester/run/{rid}/bundle").status_code == 200


def test_a_rebinding_host_is_refused_on_every_get_route(tmp_path):
    """Ruling (broader scope): the Host allowlist applies to EVERY tester
    route, not just the writes and the bundle — none of these GETs is
    secret, but the DNS-rebinding defence is applied uniformly rather than
    routed around it. A rebinding Host gets 403 even though Origin is
    absent (as a same-site XHR from the rebound page would send)."""
    with client(tmp_path) as c:
        rid = c.post("/api/tester/run", json=RUN).json()["id"]
        poll(c, rid)
        for path in ("/api/tester/strategies", "/api/tester/prop-rules",
                     f"/api/tester/run/{rid}", f"/api/tester/run/{rid}/bundle", "/api/tester/runs"):
            assert c.get(path, headers=REBIND_HOST).status_code == 403, path
            assert c.get(path).status_code == 200, path   # the same route, genuine Host


def test_shutdown_terminates_an_in_flight_runner_child(tmp_path, monkeypatch):
    """Review amendment: the chart service must stop the runner's child on
    its own shutdown (lifespan) rather than orphan it. Fakes the child
    process so the test needs no real backtest run to still be in flight
    when the service goes down."""
    events: list[str] = []
    started = threading.Event()

    class FakeProc:
        def __init__(self):
            self.pid = 424242
            self._done = threading.Event()

        def wait(self, timeout=None):
            if not self._done.wait(timeout):
                raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)
            return 0

        def terminate(self):
            events.append("terminate")
            self._done.set()

        def kill(self):
            events.append("kill")
            self._done.set()

    def fake_popen(*a, **k):
        proc = FakeProc()
        started.set()
        return proc

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)

    with client(tmp_path) as c:
        rid = c.post("/api/tester/run", json=RUN).json()["id"]
        assert started.wait(5), "the manager never launched the (fake) child"
        assert c.get(f"/api/tester/run/{rid}").json()["status"] in ("queued", "running")
    # the `with` block's exit ran the app's shutdown lifecycle
    assert events and events[0] in ("terminate", "kill")
