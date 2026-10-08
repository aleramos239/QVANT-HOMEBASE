"""levels.py: the day's geometry (one definition for the desk and the tester) and what each account gets of it."""
from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from homebase.atrbars import MIN_MS, TickBars, et_ms
from tests.levels_util import strategy_cfg
from homebase.dayrules import DayBook, DayRules
from homebase.levels import (Geometry, account_leg, compute_geometry, is_early_close_skip, orb_geometry,
                             straddle_geometry)
from tests.test_atrbars import FIRE_NYAM, FIRE_ORB, day_minutes, fed

D = dt.date(2026, 10, 2)
TICK = 0.25


def cfg(name):
    return strategy_cfg(name)


# ------------------------------------------------------------------------------------------------ geometry
def test_straddle_geometry_is_anchor_plus_minus_off_atr_on_the_tick_grid():
    g = straddle_geometry(20000.10, 44.0, 0.25, 3.0, TICK, 19)
    assert (g.upper, g.lower) == (20011.0, 19989.0)            # 20000.10 +/- 11.0 = 20011.10 / 19989.10, snapped to the tick
    assert g.sl_pts == 132.0 and (g.atr, g.atr_bars, g.anchor) == (44.0, 19, 20000.10)
    g = straddle_geometry(20000.0, 67.0, 1.0, 3.0, TICK)
    assert (g.upper, g.lower, g.sl_pts) == (20067.0, 19933.0, 201.0)


def test_the_stop_is_floored_at_two_ticks():
    assert straddle_geometry(100.0, 0.01, 0.25, 3.0, TICK).sl_pts == 0.5


def test_orb_geometry_is_one_tick_beyond_the_range():
    g = orb_geometry(20108.0, 20098.0, 41.0, 3.0, TICK, last_px=20103.0)
    assert (g.upper, g.lower, g.sl_pts, g.range_hi, g.range_lo) == (20108.25, 20097.75, 123.0, 20108.0, 20098.0)


def test_leg_stop_is_the_testers_stop_to_the_tick():
    """The research placed the stop at tick(raw trigger -/+ d) and the tester moved it by (fill - raw trigger): with the
    straddle's raw trigger off the tick grid the two legs' stops sit a tick apart in distance.  leg_stop must give,
    for every anchor / ATR / slip, exactly the stop the tester ends up with (backtest.engine.to_tick, Ctx._entry,
    _Sim._fill)."""
    import random
    from homebase.backtest.engine import to_tick
    from homebase.levels import leg_stop
    rnd, seen = random.Random(7), set()
    for _ in range(20000):
        anchor = round(rnd.uniform(10000, 30000) * 4) / 4 + rnd.choice([0, 0, 0.1])
        atr = rnd.uniform(5, 150)
        off = rnd.choice([0.25, 1.0]) * atr
        d = max(3.0 * atr, 2 * TICK)
        for buy in (True, False):
            sd = 1 if buy else -1
            raw = anchor + sd * off                                     # the raw trigger (research: px)
            slip = rnd.choice([0, 0, 1, 3]) * TICK
            fill = to_tick(to_tick(raw, TICK) + sd * slip, TICK)       # stop fill: the trigger (rounded) +/- slip
            sl_order = to_tick(raw - sd * d, TICK)                      # Ctx._entry rounds the stop order
            sl_final = to_tick(sl_order + (fill - raw), TICK)           # _Sim._fill: moved by fill - ref (ref = raw px)
            got = leg_stop(raw, atr, 3.0, TICK, buy)
            assert to_tick(fill - sd * got, TICK) == sl_final, (anchor, atr, buy, slip)
            seen.add((buy, round(got - to_tick(d, TICK), 2)))
    assert {x[1] for x in seen} >= {0.0, 0.25, -0.25}                   # the one-tick wobble really occurs


def test_straddle_legs_may_have_different_stop_distances_and_geometry_serves_both():
    g = Geometry("atr_straddle", 100.25, 99.75, 10.0, 4.0, 19, sl_sell_pts=10.25)
    assert (g.sl_for("Buy"), g.sl_for("long"), g.sl_for("Sell"), g.sl_for("short"), g.sl_max) == (10.0, 10.0, 10.25, 10.25, 10.25)
    assert Geometry("orb", 1.0, 0.5, 8.0, 4.0, 19).sl_for("Sell") == 8.0        # no sell distance: the buy leg's


def test_geometry_serialises():
    assert straddle_geometry(1.0, 1.0, 1.0, 3.0, TICK).to_dict()["shape"] == "atr_straddle"


# ------------------------------------------------------------------------------------ compute_geometry
def day(until, seed=1):
    return fed(day_minutes(seed, until_s=until), as_ticks=False)


def test_compute_straddle_from_the_days_bars():
    tb = day(FIRE_NYAM)
    c = cfg("nq_nyam_flex")
    g, why = compute_geometry(c, tb, et_ms(D, "09:30:00"), TICK)
    assert why == "ok" and g.shape == "atr_straddle"
    atr, n = tb.atr(30, et_ms(D, "09:30:00"))
    assert (g.atr, g.atr_bars) == (atr, n) and n == 19
    assert g.anchor == tb.last_before(et_ms(D, "09:30:00"))
    assert g.upper > g.anchor > g.lower


def test_compute_orb_uses_the_five_minutes_before_the_fire():
    tb = day(FIRE_ORB)
    g, why = compute_geometry(cfg("nq_orb_pro"), tb, et_ms(D, "11:05:00"), TICK)
    hi, lo, k = tb.range(et_ms(D, "11:00:00"), et_ms(D, "11:05:00"))
    assert why == "ok" and k == 5
    assert (g.range_hi, g.range_lo, g.upper, g.lower) == (hi, lo, hi + TICK, lo - TICK)
    assert g.last_px == tb.last_before(et_ms(D, "11:05:00"))


def test_a_late_fire_is_anchored_on_the_latest_print():
    tb = day(FIRE_NYAM)
    fire = et_ms(D, "09:30:00")
    tb.add_tick(fire + 400, 20500.0, 1)
    c = cfg("nq_nyam_flex")
    on_time, _ = compute_geometry(c, tb, fire, TICK)
    late, _ = compute_geometry(c, tb, fire, TICK, last_ms=fire + 1000)
    assert on_time.anchor != 20500.0 and late.anchor == 20500.0
    assert late.atr == on_time.atr                                   # the ATR is still the bars closed by the fire


def test_no_geometry_without_atr_or_with_too_few_bars():
    c = cfg("nq_nyam_flex")
    assert compute_geometry(c, TickBars(D), et_ms(D, "09:30:00"), TICK)[0] is None
    thin = TickBars(D)
    for i in range(30):                                              # a single 30-minute bar: WARM is 3
        thin.add_minute(et_ms(D, "09:00:00") + i * MIN_MS, 100, 101, 99, 100)
    g, why = compute_geometry(c, thin, et_ms(D, "09:30:00"), TICK)
    assert g is None and "no ATR (1 closed 30-minute bars" in why


def test_no_orb_without_range_bars_or_a_print():
    tb = day(FIRE_ORB - 300)                                          # nothing from 11:00
    g, why = compute_geometry(cfg("nq_orb_pro"), tb, et_ms(D, "11:05:00"), TICK)
    assert g is None and "opening range" in why


def test_a_leg_through_the_last_print_is_refused_not_half_placed():
    tb = day(FIRE_ORB)
    # a print breaks out of the range just before the fire: the buy stop would sit BELOW the market
    tb.add_tick(et_ms(D, "11:04:59") + 500, 99999.0, 1)
    g, why = compute_geometry(cfg("nq_orb_pro"), tb, et_ms(D, "11:05:00"), TICK)
    assert g is None and "already through" in why


def test_unknown_shape():
    c = dataclasses.replace(cfg("nq_nyam_flex"), shape="nope")
    assert compute_geometry(c, day(FIRE_NYAM), et_ms(D, "09:30:00"), TICK)[1] == "unknown shape 'nope'"


# ------------------------------------------------------------------------------------------------ calendar
@pytest.mark.parametrize("d, flat, skip", [
    (dt.date(2026, 11, 27), "15:58", True),      # the day after Thanksgiving: 13:15 close
    (dt.date(2026, 12, 24), "13:30", True),
    (dt.date(2026, 12, 24), "11:00", False),     # flat before the close: an ordinary morning
    (dt.date(2026, 11, 26), "15:58", False),
    (dt.date(2027, 11, 26), "13:30", True),      # not only the tester's table
    (dt.date(2027, 12, 24), "15:58", True),
    (dt.date(2026, 10, 2), "15:58", False),
])
def test_half_days(d, flat, skip):
    assert is_early_close_skip("NQ", d, flat) is skip


def test_other_roots_have_no_half_day_in_this_calendar():
    assert is_early_close_skip("GC", dt.date(2026, 11, 27), "15:58") is False


# ------------------------------------------------------------------------------------------ account_leg
GEO = Geometry("atr_straddle", 24510.0, 24490.0, 130.0, 43.5, 19, anchor=24500.0)


def leg(name, qty=4, rules=None, book=None, profit=None):
    c = cfg(name)
    rules = rules or DayRules(c.day_take, c.day_lock, c.target_take)
    return account_leg(c, "a", qty, rules, book or DayBook("a", "d"), GEO, profit)


def test_flex_day_one_take():
    got, why = leg("nq_nyam_flex")
    assert why == "ok" and (got.qty, got.tp_pts, got.take_usd, got.take_src) == (4, 19.0, 1500.0, "day_take")
    assert got.stop_usd == 10400.0 and got.to_dict()["account"] == "a"


def test_the_take_is_net_of_what_the_day_already_closed():
    got, _ = leg("nq_nyam_flex", book=DayBook("a", "d", closed_net=700.0))
    assert got.take_usd == 800.0 and got.tp_pts == 10.25            # (800 + 16) / 80 = 10.2 -> the tick above


def test_a_day_whose_take_is_already_in_sits_out():
    got, why = leg("nq_nyam_flex", book=DayBook("a", "d", closed_net=1500.0))
    assert got is None and "already in" in why


def test_a_locked_account_sits_out():
    got, why = leg("nq_nyam_flex", book=DayBook("a", "d", locked="day_lock"))
    assert got is None and "day_lock" in why


def test_target_take_alone_needs_a_level():
    assert leg("nq_nyam_pro")[0] is None
    got, _ = leg("nq_nyam_pro", book=DayBook("a", "d", target_level=2200.0))
    assert (got.take_src, got.take_usd, got.tp_pts) == ("target_take", 2200.0, 27.75)     # 2,216 / 80 = 27.7


def test_the_lower_of_day_take_and_target_take_wins():
    got, _ = leg("nq_nyam_flex", book=DayBook("a", "d", target_level=900.0))
    assert (got.take_src, got.take_usd) == ("target_take", 900.0)
    got, _ = leg("nq_nyam_flex", book=DayBook("a", "d", target_level=2500.0))
    assert (got.take_src, got.take_usd) == ("day_take", 1500.0)


def test_pm_sizes_by_profit_and_the_book_caps_it():
    assert leg("nq_pm_flex", profit=500)[0].qty == 2
    assert leg("nq_pm_flex", profit=1500)[0].qty == 3
    assert leg("nq_pm_flex", profit=9000)[0].qty == 4
    assert leg("nq_pm_flex", profit=9000, qty=3)[0].qty == 3
    assert leg("nq_pm_flex", profit=None)[0].qty == 2           # unknown standing: the smallest


def test_with_no_take_rule_the_target_is_tgt_r_x_the_stop():
    c = dataclasses.replace(cfg("nq_nyam_flex"), day_take=0.0, target_take=False)
    got, _ = account_leg(c, "a", 4, DayRules(), DayBook("a", "d"), GEO, None)
    assert (got.take_src, got.take_usd, got.tp_pts) == ("fallback", None, 260.0)
