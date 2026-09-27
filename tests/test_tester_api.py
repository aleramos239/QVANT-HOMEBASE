"""The tester routes on the chart service: schema list, run lifecycle, Origin + Host checks."""
from __future__ import annotations

import datetime as dt
import subprocess
import threading
import time
from pathlib import Path

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


def test_montecarlo_runs_over_a_finished_bundle_and_reuses_its_prop_rules(tmp_path):
    with client(tmp_path) as c:
        rid = c.post("/api/tester/run", json=RUN).json()["id"]
        poll(c, rid)
        r = c.post("/api/tester/montecarlo", json={"run_id": rid, "paths": 500, "seed": 1},
                   headers={"origin": "http://localhost:8852"})
        assert r.status_code == 200
        mc = r.json()
        assert mc["paths"] == 500 and mc["mode"] == "shuffle" and mc["n_trades"] == 1
        for k in ("drawdown", "final_net", "losing_streak"):
            assert set(mc[k]) == {"p5", "p25", "p50", "p75", "p95"}
        assert 0.0 <= mc["p_ruin"] <= 1.0
        assert mc["p_prop_pass"] is not None            # RUN's default prop_rules ran clean
        assert "histogram" in mc and "actual" in mc
        # same seed -> identical result; a different seed need not match
        again = c.post("/api/tester/montecarlo", json={"run_id": rid, "paths": 500, "seed": 1}).json()
        assert again == mc


def test_montecarlo_refuses_bad_requests_and_cross_site_writes(tmp_path):
    with client(tmp_path) as c:
        rid = c.post("/api/tester/run", json=RUN).json()["id"]
        assert c.post("/api/tester/montecarlo", json={"run_id": rid}, headers=EVIL).status_code == 403
        assert c.post("/api/tester/montecarlo", json={"run_id": rid},
                      headers={"origin": "http://evil.example", **REBIND_HOST}).status_code == 403
        assert c.post("/api/tester/montecarlo", json={"run_id": "20260926-120000-nq930-abcd"}).status_code == 404
        r = c.post("/api/tester/montecarlo", json={"run_id": rid, "paths": 10_001})
        assert r.status_code == 400 and "paths" in r.json()["detail"]
        r = c.post("/api/tester/montecarlo", json={"run_id": rid, "mode": "bogus"})
        assert r.status_code == 400 and "mode" in r.json()["detail"]
        # the run is still queued/running: no trades to resample yet
        r = c.post("/api/tester/montecarlo", json={"run_id": rid})
        assert r.status_code in (400, 409)
        poll(c, rid)
        assert c.post("/api/tester/montecarlo", json={"run_id": rid}).status_code == 200


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
        # Item 7: a non-dict `inputs` is a 400 (a bad request), never a 500.
        for bad_inputs in (["sl_pts"], 5, "sl_pts", True):
            r = c.post("/api/tester/run", json={**RUN, "inputs": bad_inputs})
            assert r.status_code == 400 and "inputs" in r.json()["detail"]
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


# ---------------------------------------------------------------- the parameter heat-map

GRID = {"strategy": "nq930", "inputs": {"adx_gate": False},
        "axes": [{"key": "offset_pts", "values": [10, 12]}, {"key": "sl_pts", "values": [5, 6]}]}


def poll_grid(c, gid, s=120.0):
    t = time.monotonic() + s
    while time.monotonic() < t:
        st = c.get(f"/api/tester/grid/{gid}").json()
        if st["status"] in ("done", "cancelled"):
            return st
        time.sleep(0.05)
    raise AssertionError("grid never finished")


def test_a_grid_goes_from_post_to_cell_bundles_and_counts_its_looks(tmp_path):
    with client(tmp_path) as c:
        assert c.get("/api/tester/looks").json() == {}
        gid = c.post("/api/tester/grid", json=GRID, headers={"origin": "http://localhost:8852"}).json()["id"]
        st = poll_grid(c, gid)
        assert st["status"] == "done" and st["total"] == 4 and st["looks"] == 4
        assert st["range"]["start"] == "2021-01-01" and st["range"]["end"] == "2024-12-31"
        assert [a["key"] for a in st["axes"]] == ["offset_pts", "sl_pts"]
        cell = st["cells"][3]
        assert cell["params"] == {"offset_pts": 12.0, "sl_pts": 6.0} and "net_profit" in cell["summary"]
        b = c.get(f"/api/tester/grid/{gid}/cell/3/bundle").json()
        assert b["run"]["inputs"]["offset_pts"] == 12.0 and b["run"]["range"]["kind"] == "research"
        assert b["run"]["report"]["summary"]["all"]["net_profit"] == cell["summary"]["net_profit"]
        assert c.get("/api/tester/looks").json() == {"nq930": 4}
        assert c.get("/api/tester/grids").json()[0]["id"] == gid
        assert c.get("/api/tester/runs").json() == []            # cells never flood Recent runs
        import os
        assert (Path(os.environ["HOMEBASE_TESTER_SHARED"]) / "looks.json").exists()


def test_grid_requests_the_rules_refuse(tmp_path):
    with client(tmp_path) as c:
        for bad, word in (({**GRID, "range": {"kind": "custom", "start": "2024-01-01", "end": "2025-03-01"}}, "research window"),
                          ({**GRID, "holdout": {"reason": "x"}}, "research window"),
                          ({**GRID, "axes": [{"key": "offset_pts", "values": list(range(61))},
                                             {"key": "sl_pts", "values": [5]}]}, "at most 60"),
                          ({**GRID, "axes": GRID["axes"][:1]}, "2 or 3")):
            r = c.post("/api/tester/grid", json=bad)
            assert r.status_code == 400 and word in r.json()["detail"], r.json()
        assert c.post("/api/tester/grid", json=GRID, headers=EVIL).status_code == 403
        assert c.post("/api/tester/grid", json=GRID, headers={"origin": "http://evil.example", **REBIND_HOST}).status_code == 403
        for path in ("/api/tester/grid/20260927-120000-nq930-abcd", "/api/tester/grid/..%2F..%2Fetc",
                     "/api/tester/grid/20260927-120000-nq930-abcd/cell/0/bundle"):
            assert c.get(path).status_code == 404, path
        assert c.post("/api/tester/grid/20260927-120000-nq930-abcd/cancel").status_code == 404
        for path in ("/api/tester/grids", "/api/tester/looks"):
            assert c.get(path, headers=REBIND_HOST).status_code == 403
        assert c.get("/api/tester/grids").json() == []


def test_a_single_run_request_in_the_quiet_window_is_refused_with_the_pause_text(tmp_path, monkeypatch):
    from homebase.backtest import slots
    monkeypatch.setattr(slots, "et_now", lambda: dt.datetime(2026, 9, 28, 9, 25, tzinfo=slots.ET))
    with client(tmp_path) as c:
        r = c.post("/api/tester/run", json=RUN)
        assert r.status_code == 400 and "paused for the 9:30 window" in r.json()["detail"]
        gid = c.post("/api/tester/grid", json=GRID).json()["id"]      # a grid may queue; its cells wait
        st = c.get(f"/api/tester/grid/{gid}").json()
        assert st["paused"] == "paused for the 9:30 window" and st["status"] == "queued"
        c.post(f"/api/tester/grid/{gid}/cancel")


def test_a_corrupt_looks_counter_is_a_409_on_looks_and_a_400_on_a_new_grid(tmp_path, tester_shared):
    (tester_shared / "looks.json").write_text("{torn")
    with client(tmp_path) as c:
        r = c.get("/api/tester/looks")
        assert r.status_code == 409 and "looks.json.bak" in r.json()["detail"]
        r = c.post("/api/tester/grid", json=GRID)
        assert r.status_code == 400 and "never reset silently" in r.json()["detail"]
    assert (tester_shared / "looks.json").read_text() == "{torn"
