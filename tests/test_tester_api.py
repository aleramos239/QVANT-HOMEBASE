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
        listed = c.get("/api/tester/prop-rules").json()
        rules = {r["id"]: r for r in listed}
        # exactly the evals the account holder runs, newest version per family
        assert [r["name"] for r in listed] == ["Apex EOD 50K", "Apex Legacy 50K", "LucidFlex 50K",
                                               "LucidFlex 50K · $1,200 daily limit", "LucidPro 50K · $1,200 daily limit",
                                               "LucidPro 50K · no daily loss limit", "Topstep 50K"]
        assert rules["lucid-flex-50k@2026-09-27"]["confirmed"] is True
        assert rules["lucid-pro-50k@2026-09-27b"]["confirmed"] is True
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


def test_montecarlo_runs_over_a_finished_bundle_and_reuses_its_prop_rules(tmp_path, monkeypatch):
    from homebase.backtest.stats import montecarlo as MC
    calls = []
    real = MC.run
    monkeypatch.setattr(MC, "run", lambda *a, **kw: calls.append((a, kw)) or real(*a, **kw))
    with client(tmp_path) as c:
        rid = c.post("/api/tester/run", json=RUN).json()["id"]
        poll(c, rid)
        r = c.post("/api/tester/montecarlo", json={"run_id": rid, "paths": 500},
                   headers={"origin": "http://localhost:8852"})
        assert r.status_code == 200
        mc = r.json()
        assert mc["paths"] == 500 and mc["mode"] == "shuffle" and mc["n_trades"] == 1 and mc["unit"] == "day"
        for k in ("drawdown", "final_net", "losing_streak"):
            assert set(mc[k]) == {"p5", "p25", "p50", "p75", "p95"}
        assert mc["floor"] == 2000.0 and 0.0 <= mc["p_ruin"] <= 1.0     # LucidFlex's trailing max loss
        assert mc["p_prop_pass"] is not None and mc["prop_rules"]["confirmed"] is True
        assert mc["seed"] == MC.seed_for(rid)                         # I2: repeatable without a seed
        assert "histogram" in mc and "actual" in mc
        (args, kw), = calls
        assert isinstance(args[0][0], dict) and "date" in args[0][0]   # C2: trades, not bare nets
        again = c.post("/api/tester/montecarlo", json={"run_id": rid, "paths": 500}).json()
        assert again == mc and len(calls) == 1                         # I3: served from the cache
        other = c.post("/api/tester/montecarlo", json={"run_id": rid, "paths": 500, "floor": 500}).json()
        assert other["floor"] == 500.0 and len(calls) == 2
        assert c.post("/api/tester/montecarlo", json={"run_id": rid, "paths": 500, "seed": 7}).json()["seed"] == 7


def test_montecarlo_over_a_heatmap_cell(tmp_path):
    with client(tmp_path) as c:
        gid = c.post("/api/tester/grid", json=GRID).json()["id"]
        poll_grid(c, gid)
        r = c.post("/api/tester/montecarlo", json={"grid_id": gid, "cell": 1, "paths": 200})
        assert r.status_code == 200 and r.json()["n_trades"] >= 0
        cell_run = c.get(f"/api/tester/grid/{gid}/cell/1/bundle").json()["run"]["id"]
        from homebase.backtest.stats import montecarlo as MC
        assert r.json()["seed"] == MC.seed_for(cell_run)
        assert c.post("/api/tester/montecarlo", json={"grid_id": gid, "cell": 9}).status_code == 404
        assert c.post("/api/tester/montecarlo", json={"grid_id": "20260927-120000-nq930-abcd", "cell": 0}).status_code == 404
        assert c.post("/api/tester/montecarlo", json={"grid_id": gid}).status_code == 400
        assert c.post("/api/tester/montecarlo", json={"grid_id": gid, "cell": 0, "run_id": "x"}).status_code == 400


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
        for bad in (0, -5, "x", True):
            r = c.post("/api/tester/montecarlo", json={"run_id": rid, "floor": bad})
            assert r.status_code == 400 and "floor" in r.json()["detail"], bad
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
        # 2026-09-27: a 2025+ range is no longer refused -- only a malformed one is.
        r = c.post("/api/tester/run", json={**RUN, "range": {"kind": "custom", "start": "2025-02-02",
                                                             "end": "2025-01-01"}})
        assert r.status_code == 400 and "after" in r.json()["detail"]
        r = c.post("/api/tester/run", json={**RUN, "holdout": {"reason": "x"}})
        assert r.status_code == 400 and "unknown field" in r.json()["detail"]
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
        for bad, word in (({**GRID, "range": {"kind": "custom", "start": "2025-03-01", "end": "2024-01-01"}}, "after"),
                          ({**GRID, "holdout": {"reason": "x"}}, "unknown field"),
                          ({**GRID, "axes": [{"key": "offset_pts", "values": list(range(61))},
                                             {"key": "sl_pts", "values": [5]}]}, "capped at 60"),
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


# ---------------------------------------------------------------- walk-forward

WF = {"strategy": "nq930", "inputs": {"adx_gate": False}, "min_trades": 1,
      "axes": [{"key": "offset_pts", "values": [10, 12]}, {"key": "sl_pts", "values": [5]}]}


def poll_wf(c, wid, s=120.0):
    t = time.monotonic() + s
    while time.monotonic() < t:
        st = c.get(f"/api/tester/walkforward/{wid}").json()
        if st["status"] in ("done", "cancelled", "error"):
            return st
        time.sleep(0.05)
    raise AssertionError("walk-forward never finished")


def test_a_walkforward_goes_from_post_to_a_stitched_result_and_counts_cells_x_steps(tmp_path):
    with client(tmp_path) as c:
        wid = c.post("/api/tester/walkforward", json=WF, headers={"origin": "http://localhost:8852"}).json()["id"]
        st = poll_wf(c, wid)
        assert st["status"] == "done", st.get("error")
        assert st["total"] == 2 and st["walkforward"]["n_steps"] == 45 and st["looks_added"] == 90
        assert st["range"]["start"] == "2021-01-01" and st["range"]["end"] == "2024-12-31"
        assert all("net_profit" not in (cell.get("summary") or {}) for cell in st["cells"])
        assert c.get("/api/tester/looks").json() == {"nq930": 90}
        r = c.get(f"/api/tester/walkforward/{wid}/result").json()
        assert r["n_steps"] == 45 and r["n_cells"] == 2 and r["looks"] == 90
        by = {s["select"]: s for s in r["steps"]}
        assert by["2024-03"]["cell"] is not None and by["2024-03"]["is"]["trades"] >= 1   # the synthetic March day
        assert by["2024-03"]["oos"]["trades"] == 0                                         # April-June: no tape
        assert set(r["stitched"]["stats"]) >= {"net_profit", "profit_factor", "win_rate", "sharpe", "max_drawdown"}
        assert c.get("/api/tester/walkforwards").json()[0]["id"] == wid
        assert c.get("/api/tester/grids").json() == []                 # never mixed into the heat-map's list
        assert c.get(f"/api/tester/grid/{wid}").status_code == 404
        assert c.get(f"/api/tester/grid/{wid}/cell/0/bundle").status_code == 404
        assert c.get("/api/tester/runs").json() == []


def test_walkforward_requests_the_rules_refuse(tmp_path):
    with client(tmp_path) as c:
        for bad, word in (({**WF, "range": {"kind": "custom", "start": "2022-01-01", "end": "2022-03-31"}}, "too short"),
                          ({**WF, "holdout": {"reason": "x"}}, "unknown field"),
                          ({**WF, "metric": "win_rate"}, "metric"), ({**WF, "min_trades": 0}, "min_trades"),
                          ({**WF, "axes": [{"key": "offset_pts", "values": list(range(61))},
                                           {"key": "sl_pts", "values": [5]}]}, "capped at 60")):
            r = c.post("/api/tester/walkforward", json=bad)
            assert r.status_code == 400 and word in r.json()["detail"], r.json()
        assert c.post("/api/tester/walkforward", json=WF, headers=EVIL).status_code == 403
        for path in ("/api/tester/walkforward/20260927-120000-nq930-abcd",
                     "/api/tester/walkforward/20260927-120000-nq930-abcd/result"):
            assert c.get(path).status_code == 404, path
        assert c.post("/api/tester/walkforward/20260927-120000-nq930-abcd/cancel").status_code == 404
        assert c.get("/api/tester/walkforwards", headers=REBIND_HOST).status_code == 403


def test_a_queued_walkforward_can_be_cancelled_and_has_no_result(tmp_path, monkeypatch):
    from homebase.backtest import slots
    monkeypatch.setattr(slots, "et_now", lambda: dt.datetime(2026, 9, 28, 9, 25, tzinfo=slots.ET))
    with client(tmp_path) as c:
        wid = c.post("/api/tester/walkforward", json=WF).json()["id"]
        st = c.get(f"/api/tester/walkforward/{wid}").json()
        assert st["status"] == "queued" and st["paused"] == "paused for the 9:30 window" and st["eta_s"] is None
        assert c.post(f"/api/tester/walkforward/{wid}/cancel", headers=EVIL).status_code == 403
        assert c.post(f"/api/tester/walkforward/{wid}/cancel").json()["status"] == "cancelled"
        assert c.get(f"/api/tester/walkforward/{wid}/result").status_code == 409
        assert c.get("/api/tester/looks").json() == {}


def test_the_walkforward_scheme_comes_from_the_server(tmp_path):
    with client(tmp_path) as c:
        s = c.get("/api/tester/walkforward-scheme").json()
        assert s["n_steps"] == 45 and (s["first_select"], s["last_select"]) == ("2021-01", "2024-09")
        assert (s["select_months"], s["test_months"], s["step_months"]) == (1, 3, 1)
        assert s["metrics"][0] == ["net_profit", "Net $"] and s["default_min_trades"] == 5
        assert s["ratios"] == [1, 2, 3] and s["default_test_months"] == 3
        # the step count follows the ratio AND the window the picker shows
        one = c.get("/api/tester/walkforward-scheme", params={"test_months": 1}).json()
        assert one["n_steps"] == 47 and one["test_months"] == 1
        w = c.get("/api/tester/walkforward-scheme",
                  params={"test_months": 2, "start": "2025-01-01", "end": "2026-06-30"}).json()
        assert w["n_steps"] == 16 and w["window"] == {"start": "2025-01-01", "end": "2026-06-30"}
        short = c.get("/api/tester/walkforward-scheme",
                      params={"start": "2024-01-01", "end": "2024-02-29"}).json()
        assert short["n_steps"] == 0 and short["first_select"] is None
        assert c.get("/api/tester/walkforward-scheme", params={"start": "nope"}).status_code == 400
        r = c.get("/api/tester/walkforward-scheme", params={"test_months": 5})
        assert r.status_code == 400 and "test_months" in r.json()["detail"]        # never coerced to 1:3
        assert c.get("/api/tester/walkforward-scheme", params={"test_months": "2.0"}).status_code in (400, 422)
        r = c.post("/api/tester/walkforward", json={**WF, "test_months": 2.0})
        assert r.status_code == 400 and "test_months" in r.json()["detail"]        # a 400, never a 500
        assert c.get("/api/tester/walkforward-scheme", headers=REBIND_HOST).status_code == 403


PRO = "lucid-pro-50k@2026-09-27"


def test_rescoring_a_run_under_another_eval_equals_a_fresh_run_and_is_cached(tmp_path, monkeypatch):
    """The prop eval reads only the finished ledger, so re-scoring IS re-running: the re-score
    under Pro equals a fresh run under Pro; a repeat is served from the cache; the run's saved
    propsim.json stays the eval it was run with (a re-score is a view, not an overwrite)."""
    from homebase.backtest import propsim as P
    with client(tmp_path) as c:
        rid = c.post("/api/tester/run", json=RUN).json()["id"]
        assert poll(c, rid)["status"] == "done"
        saved_path = tmp_path / "state" / "tester" / "runs" / rid / "propsim.json"
        saved_bytes = saved_path.read_bytes()
        fresh = c.post("/api/tester/run", json={**RUN, "prop_rules": PRO}).json()["id"]
        assert poll(c, fresh)["status"] == "done"
        fresh_prop = c.get(f"/api/tester/run/{fresh}/bundle").json()["propsim"]

        calls = []
        real = P.evaluate
        monkeypatch.setattr(P, "evaluate", lambda *a, **kw: calls.append(a) or real(*a, **kw))
        r = c.post(f"/api/tester/runs/{rid}/propsim", json={"prop_rules": PRO},
                   headers={"origin": "http://localhost:8852"})
        assert r.status_code == 200
        assert r.json() == fresh_prop
        assert r.json()["rules"]["label"] == "LucidPro 50K (before the daily limit) · unconfirmed rules"
        again = c.post(f"/api/tester/runs/{rid}/propsim", json={"prop_rules": PRO}).json()
        assert again == fresh_prop and len(calls) == 1                     # cache hit
        # the run's own eval comes back as its saved file, untouched
        own = c.post(f"/api/tester/runs/{rid}/propsim", json={"prop_rules": P.DEFAULT_RULES}).json()
        assert own == c.get(f"/api/tester/run/{rid}/bundle").json()["propsim"]
        assert saved_path.read_bytes() == saved_bytes
        # the general route takes {run_id} too
        assert c.post("/api/tester/propsim", json={"run_id": rid, "prop_rules": PRO}).json() == fresh_prop


def test_rescoring_refuses_bad_requests_and_cross_site_writes(tmp_path):
    with client(tmp_path) as c:
        rid = c.post("/api/tester/run", json=RUN).json()["id"]
        poll(c, rid)
        r = c.post(f"/api/tester/runs/{rid}/propsim", json={"prop_rules": "nope@1"})
        assert r.status_code == 400 and "prop_rules" in r.json()["detail"]
        assert c.post(f"/api/tester/runs/{rid}/propsim", json={}).status_code == 400
        assert c.post("/api/tester/runs/20260927-120000-nq930-abcd/propsim", json={"prop_rules": PRO}).status_code == 404
        assert c.post(f"/api/tester/runs/{rid}/propsim", json={"prop_rules": PRO}, headers=EVIL).status_code == 403


def test_rescoring_a_heatmap_cell(tmp_path):
    from homebase.backtest import propsim as P
    with client(tmp_path) as c:
        gid = c.post("/api/tester/grid", json=GRID).json()["id"]
        poll_grid(c, gid)
        b = c.get(f"/api/tester/grid/{gid}/cell/1/bundle").json()
        r = c.post("/api/tester/propsim", json={"grid_id": gid, "cell": 1, "prop_rules": PRO})
        assert r.status_code == 200
        assert r.json() == P.evaluate(b["trades"], PRO, n_paths=P.N_PATHS, rules=P.load_rules(PRO))
        assert c.post("/api/tester/propsim", json={"grid_id": gid, "cell": 9, "prop_rules": PRO}).status_code == 404
        assert c.post("/api/tester/propsim", json={"grid_id": gid, "prop_rules": PRO}).status_code == 400
