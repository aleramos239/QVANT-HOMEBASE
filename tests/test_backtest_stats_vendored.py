# VENDORED from ONYX TRADING tests/test_report_stats.py at commit c98121b; the propsim5
# tests were dropped (propsim is not vendored). Re-vendor instead of editing.
"""Report-card math: hand-computed fixtures, not golden-file snapshots."""
from __future__ import annotations

import calendar
import json
import os
import tempfile

import pytest

from homebase.backtest.stats import ledger as L
from homebase.backtest.stats import stats


def _ts(y, m, d, hh=15):
    return calendar.timegm((y, m, d, hh, 0, 0, 0, 0, 0))


def _t(pnl, *, y=2025, m=1, d=1, side="long", qty=None, runup=None,
       drawdown=None, risk=None):
    return L.Trade(_ts(y, m, d), _ts(y, m, d), side, qty, pnl, runup, drawdown, risk)


# --- ledger normalization ----------------------------------------------------

def test_tv_csv_roundtrip():
    csv = (
        "entry_time,entry_price,entry_id,exit_time,exit_price,exit_id,qty,"
        "profit,profit_pct,cum_profit,runup,drawdown,commission\n"
        "2025-01-06T16:00:00+00:00,100,L,2025-01-06T19:45:00+00:00,110,x,2,"
        "541,0.009,541,558,69,2\n"
        "2025-01-07T16:00:00+00:00,100,S,2025-01-07T19:45:00+00:00,110,x,3,"
        "-200,-0.004,341,10,220,2\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
        fh.write(csv)
        path = fh.name
    try:
        tr = L.load(path)
    finally:
        os.unlink(path)
    assert [t.side for t in tr] == ["long", "short"]
    assert [t.pnl for t in tr] == [541.0, -200.0]
    assert [t.qty for t in tr] == [2.0, 3.0]
    assert tr[0].runup == 558.0 and tr[0].drawdown == 69.0
    # +00:00 offset honored, not double-counted
    assert tr[0].entry_ts == _ts(2025, 1, 6, 16)


def test_side_inferred_from_price_when_id_is_descriptive():
    """A named entry ('PbD b break 21124.25') carries no L/S token; price
    direction vs GROSS pnl must still identify the short."""
    csv = (
        "entry_time,entry_price,entry_id,exit_time,exit_price,exit_id,qty,"
        "profit,runup,drawdown,commission\n"
        "2024-07-30T14:30:00+00:00,21118.25,PbD b break 21124.25,"
        "2024-07-30T15:00:00+00:00,20999.75,x,,696,703.5,81,15\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
        fh.write(csv)
        path = fh.name
    try:
        assert L.load(path)[0].side == "short"
    finally:
        os.unlink(path)


def test_commission_flips_naive_price_inference():
    """A long that moved up but netted negative after fees stays a LONG."""
    csv = ("entry_time,entry_price,exit_time,exit_price,profit,commission\n"
           "2025-01-06T16:00:00Z,100,2025-01-06T17:00:00Z,101,-3,5\n")
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
        fh.write(csv)
        path = fh.name
    try:
        assert L.load(path)[0].side == "long"   # gross = -3 + 5 = +2, price up
    finally:
        os.unlink(path)


def test_bare_pnl_list_loads_but_is_timeless():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump([100, -50, 25], fh)
        path = fh.name
    try:
        tr = L.load(path)
        assert [t.pnl for t in tr] == [100.0, -50.0, 25.0]
        with pytest.raises(L.LedgerError, match="no timestamps"):
            L.daily_pnls(tr)
    finally:
        os.unlink(path)


def test_unknown_pnl_column_raises_and_names_headers():
    csv = "alpha,beta\n1,2\n"
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
        fh.write(csv)
        path = fh.name
    try:
        with pytest.raises(L.LedgerError) as e:
            L.load(path)
        assert "alpha" in str(e.value) and "beta" in str(e.value)
    finally:
        os.unlink(path)


def test_multi_arm_json_requires_a_key():
    data = {"armA": [{"usd": 1}], "armB": [{"usd": 2}]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(data, fh)
        path = fh.name
    try:
        with pytest.raises(L.LedgerError, match="armA"):
            L.load(path)
        assert L.load(path, key="armB")[0].pnl == 2.0
    finally:
        os.unlink(path)


# --- resize -----------------------------------------------------------------

def test_resize_scales_by_recorded_risk():
    tr = [_t(1000, risk=500, qty=2), _t(-250, risk=500, qty=2)]
    out = L.resize(tr, 350)
    assert out[0].pnl == pytest.approx(700.0)
    assert out[1].pnl == pytest.approx(-175.0)
    assert out[0].qty == pytest.approx(1.4)


def test_resize_without_risk_raises_rather_than_fudging():
    with pytest.raises(L.LedgerError, match="no risk recorded"):
        L.resize([_t(100)], 350)


# --- metric pack ------------------------------------------------------------

def test_core_metrics_hand_computed():
    tr = [_t(100, d=1), _t(-50, d=2), _t(200, d=3), _t(-25, d=6)]
    p = stats.pack(tr)
    assert p["n_trades"] == 4
    assert p["net"] == 225.0
    assert p["win_rate"] == 0.5
    assert p["profit_factor"] == pytest.approx(300 / 75)
    assert p["expectancy"] == pytest.approx(225 / 4)
    assert p["avg_win"] == 150.0
    assert p["avg_loss"] == -37.5
    assert p["payoff_ratio"] == pytest.approx(4.0)
    assert p["largest_win"] == 200.0
    assert p["smallest_win"] == 100.0
    assert p["largest_loss"] == -50.0
    assert p["smallest_loss"] == -25.0


def test_max_drawdown_and_runup_are_equity_curve_moves():
    # curve: 0, 100, 50, 250, 225  -> dd -50 (100->50), runup +250 (0->250)
    tr = [_t(100, d=1), _t(-50, d=2), _t(200, d=3), _t(-25, d=4)]
    p = stats.pack(tr)
    assert p["max_drawdown"] == pytest.approx(-50.0)
    assert p["max_runup"] == pytest.approx(250.0)


def test_streaks_scratch_breaks_both_runs():
    pnls = [1, 1, 1, -1, -1, 0, 1, -1, -1, -1, -1]
    tr = [_t(p, d=i + 1) for i, p in enumerate(pnls)]
    p = stats.pack(tr)
    assert p["win_streak_max"] == 3      # the leading 1,1,1
    assert p["win_streak_min"] == 1      # the lone 1 after the scratch
    assert p["win_streak_avg"] == pytest.approx(2.0)   # (3 + 1) / 2
    assert p["loss_streak_max"] == 4
    assert p["loss_streak_min"] == 2
    assert p["loss_streak_avg"] == pytest.approx(3.0)  # (2 + 4) / 2
    assert p["n_scratch"] == 1


def test_streak_dollars_measure_the_run_not_the_trade():
    """Runs are reported in money as well as in trades — the money is what
    sizes a drawdown. Runs here: +150 (2), -60 (3), scratch, +200 (1), -40 (1)."""
    pnls = [100, 50, -30, -20, -10, 0, 200, -40]
    p = stats.pack([_t(v, d=i + 1) for i, v in enumerate(pnls)])
    assert p["win_streak_avg"] == pytest.approx(1.5)     # (2 + 1) / 2
    assert p["win_streak_pnl_avg"] == pytest.approx(175.0)   # (150 + 200) / 2
    assert p["win_streak_pnl_best"] == pytest.approx(200.0)
    assert p["loss_streak_avg"] == pytest.approx(2.0)    # (3 + 1) / 2
    assert p["loss_streak_pnl_avg"] == pytest.approx(-50.0)  # (-60 + -40) / 2
    assert p["loss_streak_pnl_worst"] == pytest.approx(-60.0)
    # every trade lands in exactly one run, so the runs reconcile to net
    assert p["win_streak_pnl_avg"] * 2 + p["loss_streak_pnl_avg"] * 2 == \
        pytest.approx(p["net"])


def test_streak_dollars_absent_when_a_side_never_ran():
    """All winners -> there is no losing run, and that is None, not $0."""
    p = stats.pack([_t(100, d=1), _t(50, d=2)])
    assert p["win_streak_pnl_avg"] == pytest.approx(150.0)   # one run of 2
    assert p["loss_streak_pnl_avg"] is None
    assert p["loss_streak_pnl_worst"] is None


def test_r_multiple_only_when_risk_recorded():
    assert stats.pack([_t(100), _t(-50)])["avg_r_multiple"] is None
    p = stats.pack([_t(1000, risk=500), _t(-500, risk=500)])
    assert p["avg_r_multiple"] == pytest.approx(0.5)   # (+2R + -1R) / 2


def test_qty_stats_absent_when_ledger_has_no_qty():
    p = stats.pack([_t(100), _t(-50)])
    assert p["qty_avg"] is None and p["qty_max"] is None
    p = stats.pack([_t(100, qty=1), _t(-50, qty=4)])
    assert p["qty_avg"] == pytest.approx(2.5)
    assert (p["qty_max"], p["qty_min"]) == (4, 1)


def test_sharpe_pools_same_day_trades_into_one_day():
    """Two trades on one day is ONE daily observation, not two."""
    same_day = [_t(100, d=1), _t(-100, d=1), _t(50, d=2), _t(50, d=3)]
    p = stats.pack(same_day)
    assert p["n_days"] == 3


def test_report_splits_long_short_and_year():
    tr = [_t(100, y=2024, d=1, side="long"), _t(-40, y=2024, d=2, side="short"),
          _t(60, y=2025, d=1, side="long")]
    r = stats.report(tr)
    assert r["dated"] is True
    assert r["pooled"]["combined"]["net"] == 120.0
    assert r["pooled"]["long"]["net"] == 160.0
    assert r["pooled"]["short"]["net"] == -40.0
    assert sorted(r["by_year"]) == [2024, 2025]
    assert r["by_year"][2024]["combined"]["net"] == 60.0
    assert r["by_year"][2025]["combined"]["n_trades"] == 1
    # per-year nets reconcile to the pooled net
    assert sum(r["by_year"][y]["combined"]["net"] for y in r["by_year"]) == 120.0


def test_year_attribution_uses_exit_not_entry():
    """A trade opened Dec 31 and closed Jan 2 belongs to the closing year."""
    t = L.Trade(_ts(2024, 12, 31), _ts(2025, 1, 2), "long", None, 500.0)
    r = stats.report([t])
    assert list(r["by_year"]) == [2025]


def test_timeless_ledger_still_reports_pooled():
    tr = [L.Trade(None, None, "long", None, x) for x in (100, -50)]
    r = stats.report(tr)
    assert r["dated"] is False
    assert r["by_year"] == {}
    assert r["pooled"]["combined"]["net"] == 50.0


# --- cost ladder -------------------------------------------------------------

def _tc(pnl, cost, *, y=2025, d=1, qty=None):
    return L.Trade(_ts(y, 1, d), _ts(y, 1, d), "long", qty, pnl, risk=None, cost=cost)


def test_rung_adds_back_1x_cost_then_charges_k():
    """pnl is already NET of cost at 1x, so rung k = pnl + (1-k)*cost."""
    tr = [_tc(100.0, 10.0)]
    assert stats._at_rung(tr, 1.0)[0].pnl == pytest.approx(100.0)   # unchanged
    assert stats._at_rung(tr, 0.5)[0].pnl == pytest.approx(105.0)   # half the cost
    assert stats._at_rung(tr, 2.0)[0].pnl == pytest.approx(90.0)
    assert stats._at_rung(tr, 4.0)[0].pnl == pytest.approx(70.0)
    assert stats._at_rung(tr, 0.0)[0].pnl == pytest.approx(110.0)   # gross


def test_breakeven_multiple_is_exact_not_bisected():
    """net(k) = N + (1-k)C is linear, so breakeven is 1 + N/C exactly.
    N=300, C=100 -> dies at 4x; net at 4x must be exactly 0."""
    tr = [_tc(100.0, 33.0), _tc(100.0, 33.0), _tc(100.0, 34.0)]
    lad = stats.cost_ladder(tr)
    assert lad["total_cost_1x"] == pytest.approx(100.0)
    assert lad["gross"] == pytest.approx(400.0)
    assert lad["breakeven_mult"] == pytest.approx(4.0)
    by_mult = {s["mult"]: s for s in lad["rungs"]}
    assert by_mult[4.0]["net"] == pytest.approx(0.0)
    assert by_mult[2.0]["net"] == pytest.approx(200.0)
    assert by_mult[0.5]["net"] == pytest.approx(350.0)


def test_ladder_flags_the_rung_it_dies_on():
    # N=50, C=100 -> breakeven 1.5x, so 2x is the first dead rung
    lad = stats.cost_ladder([_tc(50.0, 100.0)])
    assert lad["breakeven_mult"] == pytest.approx(1.5)
    assert lad["dies_at_rung"] == 2.0
    assert lad["survives_all"] is False
    alive = {s["mult"]: s["alive"] for s in lad["rungs"]}
    assert alive == {0.5: True, 1.0: True, 2.0: False, 4.0: False}


def test_narrow_death_zone_is_visible():
    """Griffioen's point: alive at one rung, dead at the next. N=10, C=100
    -> breakeven 1.1x, so it survives 1x and dies by 2x."""
    lad = stats.cost_ladder([_tc(10.0, 100.0)])
    assert lad["breakeven_mult"] == pytest.approx(1.1)
    assert lad["dies_at_rung"] == 2.0


def test_win_rate_is_recomputed_per_rung_not_carried():
    """Added friction flips marginal winners into losers — that flip is most of
    what the ladder is for, so win rate must move down the rungs."""
    tr = [_tc(5.0, 10.0), _tc(5.0, 10.0), _tc(-50.0, 10.0)]
    by = {s["mult"]: s for s in stats.cost_ladder(tr)["rungs"]}
    assert by[1.0]["win_rate"] == pytest.approx(2 / 3)
    # at 2x each winner loses another $10 -> both go negative
    assert by[2.0]["win_rate"] == pytest.approx(0.0)


def test_ladder_survives_all_when_costs_are_a_rounding_error():
    lad = stats.cost_ladder([_tc(1000.0, 1.0)])
    assert lad["survives_all"] is True and lad["dies_at_rung"] is None
    assert lad["breakeven_mult"] == pytest.approx(1001.0)


def test_ladder_refuses_without_a_cost_on_every_trade():
    with pytest.raises(ValueError, match="1 of 2 have none"):
        stats.cost_ladder([_tc(10.0, 1.0), _t(10.0)])


def test_report_attaches_ladder_only_when_costs_are_known():
    assert stats.report([_t(100, d=1)])["cost_ladder"] is None
    r = stats.report([_tc(100.0, 10.0, y=2025), _tc(50.0, 10.0, y=2026)])
    assert r["cost_ladder"] is not None
    assert sorted(r["cost_ladder_by_year"]) == [2025, 2026]


# --- apply_cost --------------------------------------------------------------

def test_apply_cost_per_contract_scales_with_size():
    """A 2-lot and a 74-lot do not pay the same friction — the whole reason
    per-contract is the default unit."""
    tr = [_t(100, qty=2), _t(100, qty=74)]
    out = L.apply_cost(tr, per_contract=1.24)
    assert out[0].cost == pytest.approx(2.48)
    assert out[1].cost == pytest.approx(91.76)
    assert [t.pnl for t in out] == [100, 100]      # pnl is NOT re-charged


def test_apply_cost_per_contract_needs_qty():
    with pytest.raises(L.LedgerError, match="needs a qty"):
        L.apply_cost([_t(100)], per_contract=1.24)


def test_apply_cost_rejects_both_or_neither():
    for kw in ({}, {"per_contract": 1.0, "per_trade": 1.0}):
        with pytest.raises(L.LedgerError, match="exactly one"):
            L.apply_cost([_t(100, qty=1)], **kw)


def test_tv_commission_column_becomes_the_cost_basis():
    csv = ("entry_time,entry_price,entry_id,exit_time,exit_price,profit,commission\n"
           "2025-01-06T16:00:00Z,100,L,2025-01-06T17:00:00Z,110,541,2\n")
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
        fh.write(csv)
        path = fh.name
    try:
        assert L.load(path)[0].cost == 2.0
    finally:
        os.unlink(path)


def test_cost_per_day_aligns_with_daily_pnls():
    tr = [_tc(100.0, 5.0, d=1), _tc(-40.0, 3.0, d=1), _tc(20.0, 2.0, d=3)]
    assert L.daily_pnls(tr) == [60.0, 20.0]
    assert L.cost_per_day(tr) == [8.0, 2.0]


def test_resize_scales_cost_with_the_position():
    tr = [_tc(1000.0, 20.0, qty=2)]
    tr[0].risk = 500.0
    out = L.resize(tr, 250.0)
    assert out[0].pnl == pytest.approx(500.0)
    assert out[0].cost == pytest.approx(10.0)     # half the size, half the fees


# --- propsim horizons -------------------------------------------------------

