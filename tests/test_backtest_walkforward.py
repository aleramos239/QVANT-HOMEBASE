"""Walk-forward: 1 month to SELECT, the next N months to TEST (the 1:1 / 1:2 / 1:3 ratio), stepping
monthly, over whatever window the request names. Window stepping, the selection tie-break,
non-overlapping stitching at every ratio, the per-month cache equalling a single run over that month,
and the manager end to end (a fake runner child)."""
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


def test_stepping_at_every_ratio_and_a_window_too_short_for_one_cycle():
    """1:1, 1:2 and 1:3 all select on ONE month and test on the next N; a window without
    a complete N-month test window after a selection month yields no step at all."""
    months = ["2022-01", "2022-02", "2022-03", "2022-04", "2022-05"]
    assert wf.steps(months, 1) == [{"k": k, "select": months[k], "test": [months[k + 1]]} for k in range(4)]
    assert wf.steps(months, 2) == [{"k": 0, "select": "2022-01", "test": ["2022-02", "2022-03"]},
                                   {"k": 1, "select": "2022-02", "test": ["2022-03", "2022-04"]},
                                   {"k": 2, "select": "2022-03", "test": ["2022-04", "2022-05"]}]
    assert len(wf.steps(months, 3)) == 2
    for n in (1, 2, 3):
        assert wf.steps(months[:n], n) == []                                  # never a partial test window
        assert wf.steps(months[:n + 1], n) == [{"k": 0, "select": months[0], "test": months[1:n + 1]}]
    research = wf.month_list(dt.date(2021, 1, 1), dt.date(2024, 12, 31))
    assert [len(wf.steps(research, n)) for n in (1, 2, 3)] == [47, 46, 45]


def test_the_stitched_chain_never_overlaps_at_any_ratio():
    """The chain steps by N, so its test windows tile the out-of-sample months once each --
    the no-overlap rule, whichever ratio is chosen."""
    months = wf.month_list(dt.date(2021, 1, 1), dt.date(2024, 12, 31))
    for n in (1, 2, 3):
        st = wf.steps(months, n)
        for phase in range(n):
            ks = wf.chain(len(st), phase, n)
            assert ks == list(range(phase, len(st), n))
            covered = [m for k in ks for m in st[k]["test"]]
            assert len(covered) == len(set(covered))                          # no month twice
            assert covered == months[phase + 1:phase + 1 + len(covered)]      # contiguous, in order
    assert [m for k in wf.chain(len(wf.steps(months, 1)), 0, 1) for m in wf.steps(months, 1)[k]["test"]] == months[1:48]


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
    col = report.column(leg, 50_000.0, [], ["2022-02", "2022-03", "2022-04"])   # the grid spans the covered months
    st = r["stitched"]
    for k in ("net_profit", "profit_factor", "win_rate", "sharpe", "max_drawdown", "trades"):
        assert st["stats"][k] == col[k], k
    assert st["months"] == ["2022-02", "2022-03", "2022-04"] and st["legs"] == [0]
    assert st["equity"] == report.equity(sorted(leg, key=lambda t: (t["exit_ns"], t["entry_ns"])))
    assert st["equity"]["equity"][-1] == -480
    assert [(p["phase"], p["net_profit"], p["trades"]) for p in r["phases"]] == [(0, -480, 7), (1, -60, 3), (2, 0, 0)]
    assert r["scheme"]["select_months"] == 1 and r["scheme"]["test_months"] == 3 and r["scheme"]["step_months"] == 1


def test_compute_at_each_ratio_reports_both_sides_and_the_drop():
    """The user's "and then OOS for each": the stitched chain carries the selection months'
    own (in-sample) result beside the out-of-sample one, and the drop between them."""
    months = ["2022-01", "2022-02", "2022-03", "2022-04", "2022-05"]
    tr = five_month_cells()
    cells = [{"i": i, "params": {"offset_pts": 10.0 + i}, "months": wf.month_stats(tr[i], [], 50_000.0, months)}
             for i in (0, 1)]
    got = {}
    for n in (1, 2, 3):
        r = wf.compute(cells, months, trades_of=lambda i: (tr[i], []), metric="net_profit", min_trades=5,
                       capital=50_000.0, test_months=n)
        assert r["scheme"]["test_months"] == n and r["n_steps"] == len(wf.steps(months, n))
        assert len(r["phases"]) == n
        # the IS side is the chain's selection months, each read as a single run over that month
        is_months = [r["steps"][k]["select"] for k in r["stitched"]["legs"]]
        assert r["stitched_is"]["months"] == is_months
        want = report.column([wf.to_ns(t) for k in r["stitched"]["legs"] if r["steps"][k]["cell"] is not None
                              for t in tr[r["steps"][k]["cell"]] if t["date"][:7] == r["steps"][k]["select"]],
                             50_000.0, [])
        assert r["stitched_is"]["stats"]["net_profit"] == want["net_profit"]
        # the two sides span different month counts (1 per leg vs N per leg): compare per month
        oos_n, is_n = r["stitched"]["n_months"], r["stitched_is"]["n_months"]
        assert oos_n == len(r["stitched"]["months"]) and is_n == len(r["stitched_is"]["months"])
        assert r["stitched"]["per_month"]["net_profit"] == round(r["stitched"]["stats"]["net_profit"] / oos_n, 2)
        assert r["stitched_is"]["per_month"]["net_profit"] == round(r["stitched_is"]["stats"]["net_profit"] / is_n, 2)
        assert r["drop"]["net_profit_per_month"] == round(
            r["stitched"]["per_month"]["net_profit"] - r["stitched_is"]["per_month"]["net_profit"], 2)
        assert "net_profit" not in r["drop"]          # a raw-total "drop" across unequal spans is never reported
        # the out-of-sample trades travel with the result: the List of trades tab reads them
        assert len(r["stitched"]["trades"]) == r["stitched"]["stats"]["trades"]
        assert all("entry_ms" in t and "entry_ns" not in t for t in r["stitched"]["trades"])
        got[n] = r["stitched"]["stats"]["net_profit"]
    # 1:1 holds January's pick for February alone, then re-selects (cell 1 wins February, −20 in
    # March); 1:3 holds January's pick across Feb-Apr. Different schemes, different chains.
    assert got == {1: -520, 2: -490, 3: -480}


def test_at_1to3_an_oos_earning_a_third_of_is_per_month_reads_minus_67_percent():
    """Review important 2: at 1:3 the IS side is 1 month per leg and the OOS side 3. An OOS month
    earning exactly 1/3 of the IS month has the SAME stitched total -- a raw-total drop of $0 would
    say nothing was lost. Per month, it is -67%."""
    months = ["2022-01", "2022-02", "2022-03", "2022-04"]
    tr = trades("2022-01", [60.0] * 5) + trades("2022-02", [20.0] * 5) + trades("2022-03", [20.0] * 5) \
        + trades("2022-04", [20.0] * 5)
    cells = [{"i": 0, "params": {"offset_pts": 10.0}, "months": wf.month_stats(tr, [], 50_000.0, months)}]
    r = wf.compute(cells, months, trades_of=lambda i: (tr, []), metric="net_profit", min_trades=5,
                   capital=50_000.0, test_months=3)
    assert r["stitched"]["stats"]["net_profit"] == r["stitched_is"]["stats"]["net_profit"] == 300.0   # equal totals...
    assert (r["stitched_is"]["n_months"], r["stitched"]["n_months"]) == (1, 3)
    assert r["stitched_is"]["per_month"] == {"net_profit": 300.0, "trades": 5.0}
    assert r["stitched"]["per_month"] == {"net_profit": 100.0, "trades": 5.0}
    assert r["drop"]["net_profit_per_month"] == -200.0                                             # ...not per month
    assert round(r["drop"]["pct"]) == -67


def test_the_months_never_tested_out_of_sample_are_listed():
    """Review minor 6: when the chain's last leg can't fit, the tail months are never OOS -- say which."""
    research = wf.month_list(dt.date(2021, 1, 1), dt.date(2024, 12, 31))
    tr = trades("2021-01", [10.0] * 5)
    cells = [{"i": 0, "params": {}, "months": wf.month_stats(tr, [], 50_000.0, research)}]
    got = {n: wf.compute(cells, research, trades_of=lambda i: (tr, []), metric="net_profit", min_trades=5,
                         capital=50_000.0, test_months=n)["stitched"]["uncovered"] for n in (1, 2, 3)}
    assert got == {1: [], 2: ["2024-12"], 3: ["2024-11", "2024-12"]}


def test_a_step_is_the_single_run_over_its_own_months():
    """A step's IS and OOS numbers ARE report.column over those months' trades of the picked
    cell -- the same thing a single run over each month would have produced."""
    months = ["2022-01", "2022-02", "2022-03", "2022-04", "2022-05"]
    tr = five_month_cells()
    cells = [{"i": i, "params": {"offset_pts": 10.0 + i}, "months": wf.month_stats(tr[i], [], 50_000.0, months)}
             for i in (0, 1)]
    r = wf.compute(cells, months, trades_of=lambda i: (tr[i], []), metric="net_profit", min_trades=5,
                   capital=50_000.0, test_months=2)
    assert any(row["cell"] is not None for row in r["steps"])
    for row in r["steps"]:
        i = row["cell"]
        if i is None:
            assert row["is"] is None and row["oos"] is None
            continue
        sel = report.column([wf.to_ns(t) for t in tr[i] if t["date"][:7] == row["select"]], 50_000.0, [])
        oos = report.column([wf.to_ns(t) for t in tr[i] if row["test"][0] <= t["date"][:7] <= row["test"][1]], 50_000.0, [])
        for k in ("net_profit", "trades", "win_rate", "sharpe", "max_drawdown"):
            assert row["is"][k] == sel[k], (row["select"], k)
            assert row["oos"][k] == oos[k], (row["test"], k)


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

def test_validate_defaults_to_the_research_window_and_counts_the_steps():
    g = wf.validate_wf(wbody())
    w = g["walkforward"]
    assert w["metric"] == "net_profit" and w["min_trades"] == 5
    assert w["months"][0] == "2021-01" and w["months"][-1] == "2024-12" and w["n_steps"] == 45
    assert g["range"]["start"] == "2021-01-01" and g["range"]["end"] == "2024-12-31"
    for c in g["cells"]:
        assert c["req"]["range"]["kind"] == "research" and "holdout" not in c["req"]
    assert wf.validate_wf(wbody(metric="sharpe", min_trades=3))["walkforward"]["metric"] == "sharpe"


def test_the_walkforward_runs_whatever_window_it_is_given():
    """2026-09-27: the window comes from the range picker, 2025+ included, and the months
    the scheme steps over are that window's own whole calendar months."""
    g = wf.validate_wf(wbody(range={"kind": "custom", "start": "2025-01-01", "end": "2026-06-30"}))
    w = g["walkforward"]
    assert w["months"][0] == "2025-01" and w["months"][-1] == "2026-06" and len(w["months"]) == 18
    assert w["n_steps"] == 15
    assert (g["range"]["start"], g["range"]["end"]) == ("2025-01-01", "2026-06-30")
    for c in g["cells"]:
        assert (c["req"]["range"]["start"], c["req"]["range"]["end"]) == ("2025-01-01", "2026-06-30")


def test_a_window_too_short_for_one_full_cycle_is_refused():
    with pytest.raises(ValueError, match="too short"):
        wf.validate_wf(wbody(range={"kind": "custom", "start": "2024-01-01", "end": "2024-03-31"}))
    # the same window IS long enough at 1:1 and 1:2 -- the refusal is per ratio
    for n in (1, 2):
        g = wf.validate_wf(wbody(range={"kind": "custom", "start": "2024-01-01", "end": "2024-03-31"}, test_months=n))
        assert g["walkforward"]["n_steps"] == 3 - n
    with pytest.raises(ValueError, match="too short"):
        wf.validate_wf(wbody(range={"kind": "custom", "start": "2024-01-01", "end": "2024-01-31"}, test_months=1))


def test_the_ratio_is_part_of_the_job():
    for n in (1, 2, 3):
        g = wf.validate_wf(wbody(test_months=n))
        assert g["walkforward"]["test_months"] == n
        assert g["walkforward"]["n_steps"] == len(wf.steps(g["walkforward"]["months"], n))
        assert f"1:{n}" in g["walkforward"]["stitch"] or f"{n}-month" in g["walkforward"]["stitch"]
    assert wf.validate_wf(wbody())["walkforward"]["test_months"] == 3        # 1:3 stays the default
    for bad in (0, 4, 2.5, 2.0, True, "2", None):      # 2.0 is not a ratio either (review minor 3)
        with pytest.raises(ValueError, match="test_months"):
            wf.validate_wf(wbody(test_months=bad))


def test_is_months_is_refused_for_a_walkforward():
    """Review minor 5: the scheme steps CALENDAR months; an IS-months window would select on empty
    months and score test legs over partly empty windows."""
    with pytest.raises(ValueError, match="calendar months"):
        wf.validate_wf(wbody(range={"kind": "is_months"}))


def test_the_scheme_route_reports_the_step_count_for_a_ratio_and_a_window():
    sc = wf.scheme()
    assert sc["n_steps"] == 45 and sc["test_months"] == 3 and sc["ratios"] == [1, 2, 3]
    assert (sc["first_select"], sc["last_select"]) == ("2021-01", "2024-09")
    assert wf.scheme(test_months=1)["n_steps"] == 47 and wf.scheme(test_months=2)["n_steps"] == 46
    w = wf.scheme(start="2025-01-01", end="2026-06-30", test_months=1)
    assert w["n_steps"] == 17 and w["first_select"] == "2025-01" and w["last_select"] == "2026-05"
    short = wf.scheme(start="2024-01-01", end="2024-02-29", test_months=3)
    assert short["n_steps"] == 0 and short["first_select"] is None
    for bad in (0, 4, 5, 2.0, True):                   # review minor 4: never silently 1:3
        with pytest.raises(ValueError, match="test_months"):
            wf.scheme(test_months=bad)


def test_a_malformed_window_is_still_refused():
    with pytest.raises(DisciplineError):
        wf.validate_wf(wbody(range={"kind": "nope"}))
    with pytest.raises(ValueError, match="unknown field"):
        wf.validate_wf(wbody(holdout={"reason": "peek"}))


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


# ---------------------------------------------------------------- compare: 1:1 · 1:2 · 1:3 from one grid run

def test_a_compare_job_is_the_same_grid_and_counts_every_schemes_steps():
    g, one = wf.validate_wf(wbody(compare=True)), wf.validate_wf(wbody(test_months=3))
    w = g["walkforward"]
    assert w["compare"] is True and w["test_months"] is None and w["ratios"] == [1, 2, 3]
    assert w["n_steps_by"] == {"1": 47, "2": 46, "3": 45} and w["n_steps"] == 138
    assert (w["metric"], w["min_trades"], w["months"]) == ("net_profit", 5, one["walkforward"]["months"])
    # the cells ARE a 1:N job's cells: one full-window run each, whatever the ratio
    assert [c["req"] for c in g["cells"]] == [c["req"] for c in one["cells"]]
    assert (g["range"], g["axes"], g["qty"], g["commission"], g["slippage_ticks"]) == \
        (one["range"], one["axes"], one["qty"], one["commission"], one["slippage_ticks"])


def test_compare_refuses_a_ratio_a_non_bool_and_a_window_too_short_for_1to3():
    with pytest.raises(ValueError, match="without test_months"):
        wf.validate_wf(wbody(compare=True, test_months=2))
    for bad in (1, "true", None):
        with pytest.raises(ValueError, match="compare"):
            wf.validate_wf(wbody(compare=bad))
    # Jan-Mar fits 1:1 and 1:2 but not 1:3: a comparison with an empty column is refused
    with pytest.raises(ValueError, match="too short to compare"):
        wf.validate_wf(wbody(compare=True, range={"kind": "custom", "start": "2024-01-01", "end": "2024-03-31"}))
    g = wf.validate_wf(wbody(compare=False))
    assert g["walkforward"]["test_months"] == 3 and not g["walkforward"].get("compare")


def test_the_compare_scheme_sums_each_ratios_steps():
    sc = wf.compare_scheme()
    assert sc["compare"] is True and sc["n_steps"] == 138 and sc["runnable"] is True
    assert sc["n_steps_by"] == {"1": 47, "2": 46, "3": 45}
    assert wf.compare_scheme("2024-01-01", "2024-03-31")["runnable"] is False


def _five_month_results():
    months = ["2022-01", "2022-02", "2022-03", "2022-04", "2022-05"]
    tr = five_month_cells()
    cells = [{"i": i, "params": {"offset_pts": 10.0 + i}, "months": wf.month_stats(tr[i], [], 50_000.0, months)}
             for i in (0, 1)]
    return {n: wf.compute(cells, months, trades_of=lambda i: (tr[i], []), metric="net_profit", min_trades=5,
                          capital=50_000.0, test_months=n) for n in (1, 2, 3)}


def test_compare_summary_is_each_schemes_stitched_oos_and_nothing_in_sample():
    per = _five_month_results()
    s = wf.compare_summary(per)
    assert s["compare"] is True and [c["ratio"] for c in s["schemes"]] == ["1:1", "1:2", "1:3"]
    assert s["looks"] == sum(r["looks"] for r in per.values()) == 2 * (4 + 3 + 2)
    assert s["window"] == {"start": "2022-01", "end": "2022-05"} and s["n_cells"] == 2
    for c in s["schemes"]:
        r = per[c["test_months"]]
        assert c["stats"] == r["stitched"]["stats"] and c["equity"] == r["stitched"]["equity"]
        assert c["n_months"] == r["stitched"]["n_months"] and c["n_steps"] == r["n_steps"]
        assert c["span"] == [r["stitched"]["months"][0], r["stitched"]["months"][-1]]
        for k in ("net_profit", "trades", "win_rate", "profit_factor", "avg_trade", "max_drawdown", "sharpe"):
            assert k in c["stats"], k
    # 1:1 chain = steps 0..3 (select Jan..Apr, test Feb..May); 1:3 chain = step 0 only (test Feb-Apr)
    one, three = s["schemes"][0], s["schemes"][2]
    assert one["span"] == ["2022-02", "2022-05"] and three["span"] == ["2022-02", "2022-04"]
    assert three["uncovered"] == ["2022-05"] and one["uncovered"] == []
    assert one["legs"]["n"] == 4 and three["legs"]["n"] == 1
    legs1 = [row for row in per[1]["steps"] if row["stitched"]]
    assert one["legs"]["no_pick"] == sum(1 for row in legs1 if row["cell"] is None)
    assert one["legs"]["profitable"] == sum(1 for row in legs1 if row["oos"] and row["oos"]["net_profit"] > 0)
    assert one["legs"]["pct_profitable"] == round(one["legs"]["profitable"] / 4 * 100, 2)
    assert three["legs"]["profitable"] == 0 and three["legs"]["pct_profitable"] == 0.0     # -480 on its one leg
    # out-of-sample only: no in-sample figure anywhere in the comparison
    import json as _json
    blob = _json.dumps(s)
    for leak in ("stitched_is", '"drop"', '"is"', '"steps": ['):      # the per-step table carries IS
        assert leak not in blob, leak


def test_each_column_carries_its_phase_chains_and_their_spread():
    per = _five_month_results()
    s = wf.compare_summary(per)
    for c in s["schemes"]:
        ph = per[c["test_months"]]["phases"]
        assert c["phases"] == ph and len(ph) == c["test_months"]
        nets = [p["net_profit"] for p in ph]
        assert c["phase_spread"]["net_profit"] == {"min": min(nets), "max": max(nets),
                                                    "mean": round(sum(nets) / len(nets), 4), "n": len(nets)}
        assert c["phase_spread"]["sharpe"]["n"] == len([p for p in ph if p["sharpe"] is not None])
    three = s["schemes"][2]["phase_spread"]["net_profit"]
    assert (three["min"], three["max"]) == (-480, 0)                  # phases -480 / -60 / 0
    nets = [c["stats"]["net_profit"] for c in s["schemes"]]
    pc = s["phase_check"]
    assert pc["gap_between_schemes"] == round(max(nets) - min(nets), 2)
    assert pc["widest_phase_spread"] == 480
    assert (pc["warning"] is not None) == (480 > pc["gap_between_schemes"])
    assert pc["warning"] in (None, "the start month moves these more than the ratio does")


def test_the_phase_warning_is_off_when_the_ratio_moves_more_than_the_start_month():
    per = _five_month_results()
    per[1] = {**per[1], "stitched": {**per[1]["stitched"], "stats": {**per[1]["stitched"]["stats"], "net_profit": 10_000.0}}}
    assert wf.compare_summary(per)["phase_check"]["warning"] is None


def test_the_shared_block_is_every_metric_on_the_months_all_three_chains_test():
    months = ["2022-01", "2022-02", "2022-03", "2022-04", "2022-05"]
    tr = five_month_cells()
    cells = [{"i": i, "params": {"offset_pts": 10.0 + i}, "months": wf.month_stats(tr[i], [], 50_000.0, months)}
             for i in (0, 1)]
    kw = dict(trades_of=lambda i: (tr[i], []), metric="net_profit", min_trades=5, capital=50_000.0)
    per, s = wf.compare_results(cells, months, **kw)
    shared = ["2022-02", "2022-03", "2022-04"]                     # 1:3's span, inside 1:1's and 1:2's
    assert [wf.chain_months(months, n) for n in (1, 2, 3)] == [months[1:], months[1:], shared]
    assert s["shared_months"] == {"months": shared, "n": 3, "span": ["2022-02", "2022-04"]}
    for n in (1, 2, 3):
        assert per[n] == wf.compute(cells, months, test_months=n, **kw)      # the ordinary result, untouched
        c = s["schemes"][n - 1]
        sh = c["shared"]
        oos = [t for t in per[n]["stitched"]["trades"] if t["date"][:7] in shared]
        ns = sorted((wf.to_ns(t) for t in oos), key=lambda t: (t["exit_ns"], t["entry_ns"]))
        col = report.column(ns, 50_000.0, [], shared)
        for k in ("net_profit", "trades", "win_rate", "profit_factor", "avg_trade", "max_drawdown", "sharpe"):
            assert sh["stats"][k] == col[k], (n, k)
        assert sh["months"] == shared and sh["n_months"] == 3 and sh["span"] == ["2022-02", "2022-04"]
        assert sh["per_month"]["net_profit"] == round(col["net_profit"] / 3, 2)
        assert sh["equity"] == report.equity(ns)
    assert s["schemes"][2]["shared"]["stats"] == s["schemes"][2]["stats"]    # 1:3's full span IS the shared one
    assert s["schemes"][0]["shared"]["legs"]["n"] == 3 and s["schemes"][0]["legs"]["n"] == 4
    assert s["schemes"][1]["shared"]["legs"]["n"] == 2                      # the 04-05 leg reaches in by April


def test_compare_summary_refuses_schemes_that_do_not_share_one_setup():
    per = _five_month_results()
    per[2] = {**per[2], "scheme": {**per[2]["scheme"], "min_trades": 3}}
    with pytest.raises(ValueError, match="do not share"):
        wf.compare_summary(per)
    with pytest.raises(ValueError, match="no schemes"):
        wf.compare_summary({})


def test_a_compare_job_runs_each_cell_once_and_equals_three_separate_walkforwards(tmp_path, fake, tester_shared):
    release, fail, spawned = fake
    m = WalkForwardManager(tmp_path)
    wid = m.submit(wbody(compare=True))
    st = m.status(wid)
    assert st["total"] == 2 and st["walkforward"]["compare"] is True
    release.set()
    st = wait_wf(m, wid)
    assert st["status"] == "done", st.get("error")
    assert len(spawned) == 2                                   # 2 cells run once -- not 3 x 2
    assert st["looks_added"] == 2 * 138 and grid.read_looks(tester_shared / "looks.json") == {"nq930": 276}
    s = m.compare(wid)
    assert [c["test_months"] for c in s["schemes"]] == [1, 2, 3] and s["looks"] == 276
    with pytest.raises(ValueError, match="comparison"):
        m.result(wid)                                          # a compare job has no single result
    with pytest.raises(ValueError, match="test_months"):
        m.result(wid, 4)
    # each scheme IS the ordinary 1:N result a separate job produces over the same cells
    for n in (1, 2, 3):
        sep = m.submit(wbody(test_months=n))
        assert wait_wf(m, sep)["status"] == "done"
        assert m.result(wid, n) == m.result(sep) == m.result(sep, n)
        col = s["schemes"][n - 1]
        assert col["stats"] == m.result(sep)["stitched"]["stats"]
        with pytest.raises(ValueError, match="not a comparison"):
            m.compare(sep)
        with pytest.raises(ValueError, match=f"1:{n}, not"):
            m.result(sep, 1 + n % 3)
    listed = {g["id"]: g for g in m.list()}                  # ids sort by second + random suffix: look up by id
    assert listed[wid]["compare"] is True and listed[sep]["compare"] is False and listed[sep]["test_months"] == 3
    m2 = WalkForwardManager(tmp_path)                          # a restart reads it back, counted once
    assert m2.compare(wid) == s and m2.result(wid, 2) == m.result(wid, 2)
    assert grid.read_looks(tester_shared / "looks.json") == {"nq930": 276 + 2 * 138}


def test_a_cancelled_compare_job_counts_nothing_and_has_no_results(tmp_path, fake, tester_shared):
    release, fail, spawned = fake
    m = WalkForwardManager(tmp_path)
    wid = m.submit(wbody(compare=True))
    t = time.monotonic() + 5
    while len(spawned) < 2 and time.monotonic() < t:
        time.sleep(0.01)
    assert m.cancel(wid)["status"] == "cancelled"
    release.set()
    time.sleep(0.2)
    assert m.status(wid)["status"] == "cancelled"
    assert grid.read_looks(tester_shared / "looks.json") == {}
    with pytest.raises(ValueError, match="cancelled"):
        m.compare(wid)
    with pytest.raises(ValueError, match="cancelled"):
        m.result(wid, 1)
    assert not list(m.dir(wid).glob("result*.json")) and not (m.dir(wid) / "compare.json").exists()


def test_a_compare_job_keeps_to_the_two_slot_cap_and_the_930_pause(tmp_path, fake, tester_shared, monkeypatch):
    from homebase.backtest import slots
    release, fail, spawned = fake
    monkeypatch.setitem(TRADES, 2, TRADES[0])
    three = [{"key": "offset_pts", "values": [10, 12, 14]}, {"key": "sl_pts", "values": [5]}]
    m = WalkForwardManager(tmp_path)
    wid = m.submit(wbody(compare=True, axes=three))
    t = time.monotonic() + 5
    while len(spawned) < 2 and time.monotonic() < t:
        time.sleep(0.01)
    time.sleep(0.2)
    assert len(spawned) == 2                                   # the machine-wide cap: two at once, one queued
    assert sorted(c["status"] for c in m.status(wid)["cells"]) == ["queued", "running", "running"]
    m.cancel(wid)
    # inside 09:20-09:35 ET nothing starts: the job queues and says so
    monkeypatch.setattr(slots, "et_now", lambda: dt.datetime(2026, 9, 28, 9, 25, tzinfo=slots.ET))
    before = len(spawned)
    wid2 = m.submit(wbody(compare=True))
    time.sleep(0.3)
    st = m.status(wid2)
    assert st["status"] == "queued" and st["paused"] == "paused for the 9:30 window" and len(spawned) == before
    m.cancel(wid2)
    release.set()


# ---------------------------------------------------------------- the stitched Sharpe grid spans the covered months

def test_the_stitched_sharpe_grid_spans_the_chains_months_not_first_to_last_trade():
    """GOTCHAS: a flat no-pick month at the end of a chain is flat days, not outside the record.
    Changes an existing 1:N Sharpe slightly -- only where the chain's ends were flat."""
    months = ["2022-01", "2022-02", "2022-03", "2022-04"]
    # one cell: wins January (the selection), trades Feb 1-4 (+, -, +, +) and nothing in March
    tr = trades("2022-01", [100] * 5) + trades("2022-02", [50, -20, 40, 30])
    cells = [{"i": 0, "params": {}, "months": wf.month_stats(tr, [], 50_000.0, months)}]
    r = wf.compute(cells, months, trades_of=lambda i: (tr, []), metric="net_profit", min_trades=5,
                   capital=50_000.0, test_months=2)
    assert r["stitched"]["months"] == ["2022-02", "2022-03"]
    leg = [wf.to_ns(t) for t in tr if t["date"][:7] == "2022-02"]
    bounded = report.column(leg, 50_000.0, [], ["2022-02", "2022-03"])
    first_to_last = report.column(leg, 50_000.0, [])
    assert r["stitched"]["stats"]["sharpe"] == bounded["sharpe"]
    assert bounded["sharpe"] < first_to_last["sharpe"]          # 41 flat weekdays more, same net
    grid = report.weekday_daily_pnl(leg, [], ["2022-02", "2022-03"])
    assert len(grid) == 20 + 23 and sum(grid) == 100              # Feb + Mar 2022 weekdays
    assert len(report.weekday_daily_pnl(leg, [])) == 4            # the old first->last-trade grid
    # a hole is still dropped from the bounded grid
    assert len(report.weekday_daily_pnl(leg, [{"date": "2022-03-01", "reason": "no data"}], ["2022-02", "2022-03"])) == 42
    # the phase chains use their own covered months too
    assert r["phases"][0]["sharpe"] == r["stitched"]["stats"]["sharpe"]
