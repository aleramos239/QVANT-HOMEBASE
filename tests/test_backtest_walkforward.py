"""Walk-forward: 1 month to SELECT, the next 3 months to TEST, stepping monthly, on the research window
2021-2024 only. Window stepping, the selection tie-break, non-overlapping stitching, the per-month cache
equalling a single run over that month, and the manager end to end (a fake runner child)."""
from __future__ import annotations

import datetime as dt
import subprocess
import threading
import time
from pathlib import Path

import pytest

from homebase.backtest import grid, report
from homebase.backtest import walkforward as wf
from homebase.backtest.discipline import DisciplineError
from homebase.backtest.runner import read_json, write_json
from homebase.backtest.walkforward import WalkForwardManager

AXES = [{"key": "offset_pts", "values": [10, 12]}, {"key": "sl_pts", "values": [5]}]      # 2 cells


def wbody(**kw):
    return {"strategy": "nq930", "inputs": {"adx_gate": False}, "axes": AXES, **kw}


def weekdays(month: str, n: int) -> list[str]:
    d = dt.date.fromisoformat(month + "-01")
    out = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def trade(date: str, net: float) -> dict:
    """A trade as trades.json holds it (entry_ms/exit_ms, never _ns)."""
    ms = int(dt.datetime.fromisoformat(date + "T14:31:00+00:00").timestamp() * 1000)
    return {"date": date, "side": "long", "qty": 1, "entry_ms": ms, "entry_price": 100.0, "exit_ms": ms + 60_000,
            "exit_price": 101.0, "exit_reason": "tp", "order_price": 100.0, "sl": 95.0, "tp": 110.0, "gross": net + 4.0,
            "commission": 4.0, "net": net, "mae_pts": -1.0, "mfe_pts": 2.0, "mae_usd": -20.0, "mfe_usd": 40.0,
            "bars": 1, "seconds": 60.0}


def trades(month: str, nets: list[float]) -> list[dict]:
    return [trade(d, n) for d, n in zip(weekdays(month, len(nets)), nets)]


# ---------------------------------------------------------------- window stepping

def test_the_research_window_is_48_whole_months():
    ms = wf.month_list(dt.date(2021, 1, 1), dt.date(2024, 12, 31))
    assert len(ms) == 48 and ms[0] == "2021-01" and ms[-1] == "2024-12"
    assert ms[11:13] == ["2021-12", "2022-01"]                                # the year boundary


def test_month_list_keeps_whole_months_only():
    assert wf.month_list(dt.date(2021, 1, 15), dt.date(2021, 4, 30)) == ["2021-02", "2021-03", "2021-04"]
    assert wf.month_list(dt.date(2021, 1, 1), dt.date(2021, 3, 30)) == ["2021-01", "2021-02"]
    assert wf.month_list(dt.date(2024, 2, 1), dt.date(2024, 2, 29)) == ["2024-02"]     # leap February
    assert wf.month_list(dt.date(2023, 2, 1), dt.date(2023, 2, 28)) == ["2023-02"]
    assert wf.month_list(dt.date(2023, 2, 2), dt.date(2023, 2, 28)) == []


def test_steps_select_one_month_and_test_the_next_three_and_drop_the_last_partial_window():
    s = wf.steps(["2022-01", "2022-02", "2022-03", "2022-04", "2022-05"])
    assert s == [{"k": 0, "select": "2022-01", "test": ["2022-02", "2022-03", "2022-04"]},
                 {"k": 1, "select": "2022-02", "test": ["2022-03", "2022-04", "2022-05"]}]
    assert wf.steps(["2022-01", "2022-02", "2022-03"]) == []                  # no complete 3-month test
    research = wf.steps(wf.month_list(dt.date(2021, 1, 1), dt.date(2024, 12, 31)))
    assert len(research) == 45
    assert research[0] == {"k": 0, "select": "2021-01", "test": ["2021-02", "2021-03", "2021-04"]}
    assert research[-1] == {"k": 44, "select": "2024-09", "test": ["2024-10", "2024-11", "2024-12"]}
    for st in research:                                                       # test is strictly after select
        assert all(m > st["select"] for m in st["test"])


# ---------------------------------------------------------------- selection

def S(net, n=5, **kw):
    return {"net_profit": net, "trades": n, "sharpe": kw.get("sharpe", 1.0), "profit_factor": kw.get("pf", 1.5),
            "t_stat": kw.get("t", 1.0)}


def test_pick_takes_the_best_metric_among_cells_with_enough_trades():
    assert wf.pick({0: S(100), 1: S(300), 2: S(200)}, "net_profit", 5) == 1
    assert wf.pick({0: S(100), 1: S(300, n=4), 2: S(200)}, "net_profit", 5) == 2       # 4 trades: ineligible
    assert wf.pick({0: S(100, n=4), 1: None}, "net_profit", 5) is None                  # nobody qualifies
    assert wf.pick({0: S(100, sharpe=2.0), 1: S(300, sharpe=0.5)}, "sharpe", 5) == 0
    assert wf.pick({0: S(100, sharpe=None), 1: S(-50, sharpe=-0.2)}, "sharpe", 5) == 1  # no value: ineligible
    assert wf.pick({0: S(-100), 1: S(-50)}, "net_profit", 5) == 1                       # a losing month still picks


def test_the_tie_break_is_deterministic_more_trades_then_the_lowest_cell_index():
    assert wf.pick({0: S(300, n=5), 1: S(300, n=9), 2: S(300, n=9)}, "net_profit", 5) == 1
    assert wf.pick({2: S(300), 1: S(300), 0: S(300)}, "net_profit", 5) == 0             # dict order is irrelevant
    assert wf.pick({0: S(0.3), 1: S(0.1 + 0.2)}, "net_profit", 5) == 0                  # float noise is a tie
    for _ in range(3):
        assert wf.pick({i: S(1.0) for i in (5, 3, 4)}, "net_profit", 5) == 3


# ---------------------------------------------------------------- stitching

def test_the_stitched_chain_is_every_third_step_and_its_test_months_never_overlap():
    months = wf.month_list(dt.date(2021, 1, 1), dt.date(2024, 12, 31))
    st = wf.steps(months)
    for phase in (0, 1, 2):
        ks = wf.chain(len(st), phase)
        assert ks == list(range(phase, len(st), 3))
        covered = [m for k in ks for m in st[k]["test"]]
        assert len(covered) == len(set(covered))                               # no month twice
        assert covered == months[phase + 1:phase + 1 + len(covered)]           # contiguous, in order
    assert [m for k in wf.chain(len(st), 0) for m in st[k]["test"]] == months[1:46]     # 2021-02 .. 2024-10


# ---------------------------------------------------------------- the per-month cache

def test_month_stats_is_the_report_column_of_that_months_trades():
    tr = trades("2022-01", [100, -50, 25]) + trades("2022-03", [40])
    skipped = [{"date": "2022-01-10", "reason": "strategy error: boom"}]
    ms = wf.month_stats(tr, skipped, 50_000.0, ["2022-01", "2022-02", "2022-03"])
    col = report.column([wf.to_ns(t) for t in tr[:3]], 50_000.0, skipped)
    for k in wf.STAT_KEYS:
        if k != "skipped_by_error":
            assert ms["2022-01"][k] == col[k], k
    assert ms["2022-01"]["skipped_by_error"] == 1 and ms["2022-03"]["skipped_by_error"] == 0
    assert ms["2022-02"]["trades"] == 0 and ms["2022-02"]["net_profit"] == 0
    assert ms["2022-03"]["net_profit"] == 40


# ---------------------------------------------------------------- compute, end to end on 5 months

def five_month_cells():
    """cell 0 wins January, cell 1 wins February; both trade once a month afterwards."""
    c0 = trades("2022-01", [100] * 5) + trades("2022-02", [-100] * 5) + trades("2022-03", [10]) \
        + trades("2022-04", [10]) + trades("2022-05", [10])
    c1 = trades("2022-01", [50] * 5) + trades("2022-02", [50] * 5) + trades("2022-03", [-20]) \
        + trades("2022-04", [-20]) + trades("2022-05", [-20])
    return {0: c0, 1: c1}


def test_compute_selects_tests_and_stitches_a_two_cell_grid_over_five_months():
    months = ["2022-01", "2022-02", "2022-03", "2022-04", "2022-05"]
    tr = five_month_cells()
    cells = [{"i": i, "params": {"offset_pts": p}, "months": wf.month_stats(tr[i], [], 50_000.0, months)}
             for i, p in ((0, 10.0), (1, 12.0))]
    r = wf.compute(cells, months, trades_of=lambda i: (tr[i], []), metric="net_profit", min_trades=5,
                   capital=50_000.0)
    assert r["n_cells"] == 2 and r["n_steps"] == 2 and r["looks"] == 4          # every selection month's grid
    s0, s1 = r["steps"]
    assert (s0["select"], s0["test"], s0["cell"], s0["params"]) == ("2022-01", ["2022-02", "2022-04"], 0, {"offset_pts": 10.0})
    assert s0["is"]["net_profit"] == 500 and s0["is"]["trades"] == 5
    assert s0["oos"]["net_profit"] == -480 and s0["oos"]["trades"] == 7
    assert (s1["cell"], s1["is"]["net_profit"], s1["oos"]["net_profit"], s1["oos"]["trades"]) == (1, 250, -60, 3)
    assert s0["stitched"] is True and s1["stitched"] is False
    assert s0["changed"] is None and s1["changed"] is True
    assert r["stability"] == {"changes": 1, "pairs": 1, "distinct": 2, "no_pick": 0, "top": {"cell": 0, "count": 1}}
    # stitched = step 0's three test months of cell 0, exactly the report column of those trades
    leg = [wf.to_ns(t) for t in tr[0] if "2022-02" <= t["date"][:7] <= "2022-04"]
    col = report.column(leg, 50_000.0, [])
    st = r["stitched"]
    for k in ("net_profit", "profit_factor", "win_rate", "sharpe", "max_drawdown", "trades"):
        assert st["stats"][k] == col[k], k
    assert st["months"] == ["2022-02", "2022-03", "2022-04"] and st["legs"] == [0]
    assert st["equity"] == report.equity(sorted(leg, key=lambda t: (t["exit_ns"], t["entry_ns"])))
    assert st["equity"]["equity"][-1] == -480
    assert [(p["phase"], p["net_profit"], p["trades"]) for p in r["phases"]] == [(0, -480, 7), (1, -60, 3), (2, 0, 0)]
    assert r["scheme"]["select_months"] == 1 and r["scheme"]["test_months"] == 3 and r["scheme"]["step_months"] == 1


def test_a_month_with_no_eligible_cell_sits_out_flat():
    months = ["2022-01", "2022-02", "2022-03", "2022-04", "2022-05"]
    tr = five_month_cells()
    cells = [{"i": i, "params": {"offset_pts": 10.0 + i}, "months": wf.month_stats(tr[i], [], 50_000.0, months)}
             for i in (0, 1)]
    r = wf.compute(cells, months, trades_of=lambda i: (tr[i], []), metric="net_profit", min_trades=6,
                   capital=50_000.0)
    assert [s["cell"] for s in r["steps"]] == [None, None]
    assert r["steps"][0]["oos"] is None and r["stitched"]["stats"]["trades"] == 0
    assert r["stability"]["no_pick"] == 2 and r["stability"]["changes"] == 0 and r["looks"] == 4


# ---------------------------------------------------------------- validation: the research window, forced

def test_validate_forces_the_research_window_and_counts_the_steps():
    g = wf.validate_wf(wbody())
    w = g["walkforward"]
    assert w["metric"] == "net_profit" and w["min_trades"] == 5
    assert w["months"][0] == "2021-01" and w["months"][-1] == "2024-12" and w["n_steps"] == 45
    assert g["range"]["start"] == "2021-01-01" and g["range"]["end"] == "2024-12-31"
    for c in g["cells"]:
        assert c["req"]["range"]["kind"] == "research" and c["req"]["holdout"] is None
    assert wf.validate_wf(wbody(metric="sharpe", min_trades=3))["walkforward"]["metric"] == "sharpe"


@pytest.mark.parametrize("extra", [{"range": {"kind": "custom", "start": "2022-01-01", "end": "2022-06-30"}},
                                   {"range": {"kind": "custom", "start": "2024-01-01", "end": "2025-06-30"}},
                                   {"range": {"kind": "is_months"}}, {"range": {"kind": "research", "end": "2025-06-30"}},
                                   {"holdout": {"reason": "peek"}}])
def test_any_other_window_or_a_holdout_is_refused(extra):
    with pytest.raises(DisciplineError, match="walk-forward runs on the research window 2021–2024 only"):
        wf.validate_wf(wbody(**extra))


@pytest.mark.parametrize("extra,msg", [({"metric": "win_rate"}, "metric"), ({"metric": 3}, "metric"),
                                       ({"min_trades": 0}, "min_trades"), ({"min_trades": 2.5}, "min_trades"),
                                       ({"min_trades": True}, "min_trades"), ({"zz": 1}, "unknown field")])
def test_bad_walkforward_fields_are_refused(extra, msg):
    with pytest.raises(ValueError, match=msg):
        wf.validate_wf(wbody(**extra))


# ---------------------------------------------------------------- a month slice == a single run over that month

@pytest.mark.parametrize("gated", [False, True])
def test_a_cells_month_slice_equals_a_single_run_over_that_month(tmp_path, gated):
    from homebase.backtest import runner as R
    from homebase.backtest.tape import TapeStore
    from tests.backtest_util import nq_archive
    archive = nq_archive(tmp_path / "ticks")
    inputs = {"adx_gate": gated, "offset_pts": 10.0}
    full = R.prepare({"strategy": "nq930", "inputs": inputs, "range": {"kind": "research"}}, tmp_path / "a")
    R.execute(tmp_path / "a" / "runs" / full, TapeStore(archive, tmp_path / "cache"))
    one = R.prepare({"strategy": "nq930", "inputs": inputs,
                     "range": {"kind": "custom", "start": "2024-03-01", "end": "2024-03-31"}}, tmp_path / "b")
    R.execute(tmp_path / "b" / "runs" / one, TapeStore(archive, tmp_path / "cache"))
    months = wf.cell_months(tmp_path / "a" / "runs" / full, ["2024-02", "2024-03"])
    single = read_json(tmp_path / "b" / "runs" / one / "run.json")["report"]["summary"]["all"]
    assert single["trades"] >= (0 if gated else 1)
    for k in wf.STAT_KEYS:
        if k != "skipped_by_error":
            assert months["2024-03"][k] == single[k], k
    assert months["2024-02"]["trades"] == 0


# ---------------------------------------------------------------- the manager, with a fake runner child

TRADES = {  # cell index -> the trades.json its fake child writes (full research window, but only 2022-01..05)
    0: five_month_cells()[0], 1: five_month_cells()[1]}


class FakeChild:
    def __init__(self, argv, release: threading.Event, fail: set):
        self.cdir = Path(argv[argv.index("exec") + 1])
        self.release, self.fail, self.pid = release, fail, 4242
        self._done = threading.Event()

    def wait(self, timeout=None):
        if not self._done.is_set():
            if not self.release.wait(timeout if timeout is not None else 30):
                raise subprocess.TimeoutExpired("fake", timeout)
            self._finish(ok=int(self.cdir.name) not in self.fail)
        return 0

    def _finish(self, ok: bool):
        if self._done.is_set():
            return
        req = read_json(self.cdir / "request.json")
        i = int(self.cdir.name)
        if ok:
            tr = TRADES[i]
            allc = {"net_profit": 123456.0, "sharpe": 9.9, "trades": len(tr)}
            write_json(self.cdir / "trades.json", tr)
            write_json(self.cdir / "run.json", {"id": req["id"], "range": req["range"], "capital": req["capital"],
                                                "report": {"summary": {"all": allc}, "skipped_by_error": 0},
                                                "coverage": {"sessions": 900, "used": 900, "skipped": [], "no_trade": []}})
            write_json(self.cdir / "status.json", {"id": req["id"], "status": "done"})
        else:
            write_json(self.cdir / "status.json", {"id": req["id"], "status": "error", "error": "boom"})
        self._done.set()

    def terminate(self):
        self._finish(ok=False)

    def kill(self):
        self._finish(ok=False)


@pytest.fixture
def fake(monkeypatch):
    release, fail, spawned = threading.Event(), set(), []

    def popen(argv, **kw):
        ch = FakeChild(argv, release, fail)
        spawned.append(ch)
        return ch

    monkeypatch.setattr(grid.subprocess, "Popen", popen)
    return release, fail, spawned


def wait_wf(m, wid, s=30.0):
    t = time.monotonic() + s
    while time.monotonic() < t:
        st = m.status(wid)
        if st["status"] in ("done", "cancelled", "error"):
            return st
        time.sleep(0.02)
    raise AssertionError(f"walk-forward stuck at {m.status(wid)['status']}")


def test_the_manager_runs_the_cells_selects_stitches_and_counts_cells_x_steps_looks(tmp_path, fake, tester_shared):
    release, fail, spawned = fake
    grid.add_look(tester_shared / "looks.json", "nq930", 7)                   # an earlier heat-map
    m = WalkForwardManager(tmp_path)
    wid = m.submit(wbody())
    st = m.status(wid)
    assert st["status"] in ("queued", "running") and st["total"] == 2 and st["walkforward"]["n_steps"] == 45
    assert "progress" in st and "eta_s" in st
    release.set()
    st = wait_wf(m, wid)
    assert st["status"] == "done", st.get("error")
    assert st["looks_added"] == 90 and st["looks"] == 97                     # 2 cells x 45 selection months
    assert grid.read_looks(tester_shared / "looks.json") == {"nq930": 97}
    assert st["progress"] == 1.0
    for c in st["cells"]:                                                    # never the full-window numbers
        assert "net_profit" not in (c.get("summary") or {}) and "sharpe" not in (c.get("summary") or {})
    assert (m.dir(wid) / "cells" / "00" / "months.json").is_file()           # the per-month cache
    r = m.result(wid)
    assert r["n_steps"] == 45 and r["looks"] == 90
    by = {s["select"]: s for s in r["steps"]}
    assert by["2022-01"]["cell"] == 0 and by["2022-01"]["oos"]["net_profit"] == -480
    assert by["2022-02"]["cell"] == 1 and by["2022-02"]["oos"]["net_profit"] == -60
    assert by["2021-06"]["cell"] is None                                     # no trades: nobody qualifies
    assert r["stitched"]["months"][0] == "2021-02" and r["stitched"]["months"][-1] == "2024-10"
    assert m.list()[0]["id"] == wid
    with pytest.raises(KeyError):
        m.cell_bundle(wid, 0)                                                # the full-window cells stay unseen
    m2 = WalkForwardManager(tmp_path)                                        # a restart reads it back
    assert m2.status(wid)["status"] == "done" and m2.result(wid)["looks"] == 90
    assert grid.read_looks(tester_shared / "looks.json") == {"nq930": 97}   # never counted twice


def test_a_cancelled_walkforward_counts_no_looks_and_has_no_result(tmp_path, fake, tester_shared):
    release, fail, spawned = fake
    m = WalkForwardManager(tmp_path)
    wid = m.submit(wbody())
    t = time.monotonic() + 5
    while len(spawned) < 2 and time.monotonic() < t:
        time.sleep(0.01)
    assert m.cancel(wid)["status"] == "cancelled"
    assert grid.read_looks(tester_shared / "looks.json") == {}
    with pytest.raises(ValueError, match="cancelled"):
        m.result(wid)


def test_a_failed_cell_means_no_selection_and_no_looks(tmp_path, fake, tester_shared):
    release, fail, spawned = fake
    fail.add(1)
    m = WalkForwardManager(tmp_path)
    wid = m.submit(wbody())
    release.set()
    st = wait_wf(m, wid)
    assert st["status"] == "error" and "1 of 2 cells" in st["error"]
    assert grid.read_looks(tester_shared / "looks.json") == {}


def test_a_corrupt_looks_file_withholds_the_result(tmp_path, fake, tester_shared):
    release, fail, spawned = fake
    m = WalkForwardManager(tmp_path)
    wid = m.submit(wbody())
    (tester_shared / "looks.json").write_text("{torn")                      # broken after the submit
    release.set()
    st = wait_wf(m, wid)
    assert st["status"] == "error" and "looks" in st["error"]
    with pytest.raises(ValueError):
        m.result(wid)
    assert (tester_shared / "looks.json").read_text() == "{torn"


def test_walkforwards_live_apart_from_heatmap_grids(tmp_path, fake):
    release, fail, spawned = fake
    wfm, gm = WalkForwardManager(tmp_path), grid.GridManager(tmp_path)
    wid = wfm.submit(wbody())
    assert gm.list() == [] and wfm.list()[0]["id"] == wid
    with pytest.raises(KeyError):
        gm.status(wid)
    release.set()
    wait_wf(wfm, wid)


# ---------------------------------------------------------------- review M3 / M4

def test_a_strategy_not_flagged_session_independent_is_refused(monkeypatch):
    from homebase import strategies
    cls = strategies.get("nq930")
    assert cls.session_independent is True
    monkeypatch.setattr(cls, "session_independent", False)
    with pytest.raises(ValueError, match="session"):
        wf.validate_wf(wbody())


def test_walkforward_cells_skip_the_unused_prop_sim(tmp_path, fake):
    release, fail, spawned = fake
    m = WalkForwardManager(tmp_path)
    wid = m.submit(wbody())
    for c in ("00", "01"):
        assert read_json(m.dir(wid) / "cells" / c / "request.json")["propsim"] is False
    release.set()
    wait_wf(m, wid)


def test_execute_without_prop_sim_writes_a_skipped_marker(tmp_path):
    from homebase.backtest import runner as R
    from homebase.backtest.tape import TapeStore
    from tests.backtest_util import nq_archive
    rid = R.prepare({"strategy": "nq930", "inputs": {"adx_gate": False}, "range": {"kind": "research"}}, tmp_path)
    d = tmp_path / "runs" / rid
    write_json(d / "request.json", {**read_json(d / "request.json"), "propsim": False})
    meta = R.execute(d, TapeStore(nq_archive(tmp_path / "ticks"), tmp_path / "cache"))
    assert "skipped" in read_json(d / "propsim.json") and meta["propsim_error"] is False
