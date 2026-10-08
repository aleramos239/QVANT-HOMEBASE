"""The 3 NQ prop strategies in the tester: entries, brackets, exits, the take, the clock, half days.

Each test builds a synthetic tape from 00:00 ET (the ATR restarts there), runs ONE session through the real
tick engine, and compares the orders with the numbers the research definition gives (ref_atr in
test_atrbars is a port of the research template)."""
from __future__ import annotations

import datetime as dt
from array import array

import pytest

from homebase.backtest.engine import Costs, run_session, to_tick
from homebase.backtest.tape import Tape, et_ns
from homebase.risk import take_points
from homebase.strategies import REGISTRY
from tests.test_atrbars import FIRE_NYAM, FIRE_ORB, FIRE_PM, day_minutes, ref_atr

D = dt.date(2026, 10, 2)                       # a Friday, an ordinary session
TICK, PV = 0.25, 20.0


def hms(s: float) -> str:
    return "%02d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)


def tape_of(minutes, extra=()) -> Tape:
    """1-minute (start_sec, o, h, l, c) bars -> prints at :10 :20 :30 :40, then `extra` [(sec, px)] after."""
    rows = []
    for s, o, h, l, c in minutes:
        rows += [(s + 10, o), (s + 20, h), (s + 30, l), (s + 40, c)]
    rows += list(extra)
    rows.sort(key=lambda r: r[0])
    ts, px = array("q"), array("d")
    for s, p in rows:
        ts.append(et_ns(D, hms(int(s))) + int((s % 1) * 1000) * 1_000_000)
        px.append(p)
    return Tape("NQ", D, "NQZ6", ts, px, array("i", [1] * len(ts)), {})


def run(name, tape, qty=4, **params):
    return run_session(REGISTRY[name](params), tape, Costs(4.0, 1.0), qty=qty)


def straddle_expectation(mins, fire, off_atr, sl_atr=3.0, tf=30):
    atr, _ = ref_atr(mins, tf, fire)
    anchor = mins[-1][4]
    upper, lower = to_tick(anchor + off_atr * atr, TICK), to_tick(anchor - off_atr * atr, TICK)
    return atr, anchor, upper, lower, to_tick(max(sl_atr * atr, 2 * TICK), TICK)


# ---------------------------------------------------------------------------------------- nyam straddle
def nyam_day():
    mins = day_minutes(11, until_s=FIRE_NYAM)
    return mins, *straddle_expectation(mins, FIRE_NYAM, 0.25)


def test_nyam_straddle_wins_the_flex_take():
    mins, atr, anchor, upper, lower, sl = nyam_day()
    fill = upper + TICK                                              # a stop fills at the trigger + 1 tick of slip
    tp = take_points(1500, 4, PV, 4.0, TICK)
    assert tp == 19.0
    rise = [(FIRE_NYAM + 5, upper), (FIRE_NYAM + 20, fill + tp / 2), (FIRE_NYAM + 40, fill + tp + TICK)]
    res = run("nq_nyam_flex", tape_of(mins, rise))
    t, = res.trades
    assert (t.side, t.qty, t.order_price, t.entry_price) == ("long", 4, upper, fill)
    assert (t.sl, t.tp) == (to_tick(fill - sl, TICK), fill + tp)         # both moved to the fill
    assert t.exit_reason == "tp" and t.exit_price == fill + tp
    assert t.net == pytest.approx(tp * PV * 4 - 16) and t.net >= 1500     # the take is net of the $16 fee
    # what the chart shows: the anchor, both entries, and the planned stops / takes
    names = {h["name"]: h["price"] for h in res.hlines}
    assert names["anchor"] == anchor and names["Long entry"] == upper and names["Short entry"] == lower
    assert names["Long SL (planned)"] == upper - sl and names["Short take (planned)"] == lower - tp


def test_nyam_straddle_stop_is_3_atr_from_the_fill():
    mins, atr, anchor, upper, lower, sl = nyam_day()
    fill = lower - TICK
    drop = [(FIRE_NYAM + 5, lower), (FIRE_NYAM + 30, to_tick(fill + sl, TICK))]     # sells, then rallies to the stop
    t, = run("nq_nyam_flex", tape_of(mins, drop)).trades
    assert t.side == "short" and t.entry_price == fill
    assert t.sl == to_tick(fill + sl, TICK)
    assert t.exit_reason == "sl" and t.exit_price == to_tick(fill + sl, TICK) + TICK     # a stop pays a tick of slip
    assert sl == to_tick(3.0 * atr, TICK)


def test_nyam_straddle_one_side_only_and_unfilled_entries_cancel_at_1055():
    mins, atr, anchor, upper, lower, sl = nyam_day()
    quiet = [(FIRE_NYAM + 30, anchor), (10 * 3600 + 55 * 60 - 1, anchor + 0.5), (11 * 3600 - 1, anchor)]
    res = run("nq_nyam_flex", tape_of(mins, quiet))
    assert res.trades == [] and res.skip is None
    # a breakout AFTER 10:55 finds nothing resting
    late = [(10 * 3600 + 56 * 60, upper + 5), (10 * 3600 + 57 * 60, upper + 10)]
    assert run("nq_nyam_flex", tape_of(mins, late)).trades == []


def test_nyam_straddle_is_flat_at_1100():
    mins, atr, anchor, upper, lower, sl = nyam_day()
    path = [(FIRE_NYAM + 5, upper), (10 * 3600, upper + 3), (11 * 3600 + 5, upper + 4)]
    t, = run("nq_nyam_flex", tape_of(mins, path)).trades
    assert t.exit_reason == "time" and t.exit_ns == et_ns(D, "11:00:05")      # out on the first print at/after 11:00


def test_pro_defaults_to_its_first_day_target_take():
    mins, atr, anchor, upper, lower, sl = nyam_day()
    flex, pro = REGISTRY["nq_nyam_flex"]({}), REGISTRY["nq_nyam_pro"]({})
    assert flex.p["take_usd"] == 1500.0 and pro.p["take_usd"] == 3000.0
    fill = upper + TICK
    tp = take_points(3000, 4, PV, 4.0, TICK)
    assert tp == 37.75
    t, = run("nq_nyam_pro", tape_of(mins, [(FIRE_NYAM + 5, upper), (FIRE_NYAM + 60, fill + tp + TICK)])).trades
    assert t.exit_reason == "tp" and t.exit_price == fill + tp and t.net >= 3000


def test_take_scales_with_the_run_qty():
    mins, atr, anchor, upper, lower, sl = nyam_day()
    for qty in (1, 2, 3):
        tp = take_points(1500, qty, PV, 4.0, TICK)
        fill = upper + TICK
        t, = run("nq_nyam_flex", tape_of(mins, [(FIRE_NYAM + 5, upper), (FIRE_NYAM + 60, fill + tp + TICK)]),
                 qty=qty).trades
        assert t.qty == qty and t.exit_price == fill + tp and t.net >= 1500


def test_an_inputs_override_the_geometry():
    mins = day_minutes(11, until_s=FIRE_NYAM)
    atr, anchor, upper, lower, sl = straddle_expectation(mins, FIRE_NYAM, 0.5, sl_atr=2.0)
    res = run("nq_nyam_flex", tape_of(mins, [(FIRE_NYAM + 5, upper)]), off_atr=0.5, sl_atr=2.0)
    names = {h["name"]: h["price"] for h in res.hlines}
    assert names["Long entry"] == upper and names["Long SL (planned)"] == upper - sl


def test_no_trade_without_three_closed_bars_of_the_day():
    """Prints only from 08:50: one closed 30-minute bar at 09:30 -- the research's WARM is 3."""
    mins = [m for m in day_minutes(5, until_s=FIRE_NYAM) if m[0] >= 8 * 3600 + 50 * 60]
    res = run("nq_nyam_flex", tape_of(mins, [(FIRE_NYAM + 5, mins[-1][4] + 50)]))
    assert res.trades == [] and res.skip and "no ATR" in res.skip


# -------------------------------------------------------------------------------------------- ORB 11:05
def orb_day():
    mins = day_minutes(21, until_s=FIRE_ORB - 300)
    rng = [(FIRE_ORB - 300 + 60 * i, 20100, hi, lo, c)
           for i, (hi, lo, c) in enumerate([(20104, 20098, 20101), (20106, 20099, 20103), (20108, 20100, 20105),
                                            (20107, 20101, 20102), (20105, 20100, 20103)])]
    mins += rng
    atr, _ = ref_atr(mins, 5, FIRE_ORB)
    return mins, atr, 20108.0, 20098.0, to_tick(3.0 * atr, TICK)


def test_orb_breaks_the_5_minute_range_by_one_tick():
    mins, atr, hi, lo, sl = orb_day()
    fill = hi + 2 * TICK                                              # trigger = high + 1 tick, + 1 tick of slip
    tp = take_points(1000, 4, PV, 4.0, TICK)
    assert tp == 12.75
    path = [(FIRE_ORB + 10, 20103), (FIRE_ORB + 20, hi + TICK), (FIRE_ORB + 50, fill + tp + TICK)]
    res = run("nq_orb_pro", tape_of(mins, path))
    t, = res.trades
    assert (t.side, t.order_price, t.entry_price) == ("long", hi + TICK, fill)
    assert t.sl == to_tick(fill - sl, TICK) and t.tp == fill + tp
    assert t.exit_reason == "tp" and t.net >= 1000
    names = {h["name"]: h["price"] for h in res.hlines}
    assert names["range high"] == hi and names["range low"] == lo and names["Short entry"] == lo - TICK


def test_orb_range_is_the_five_minutes_before_the_fire_and_nothing_else():
    mins, atr, hi, lo, sl = orb_day()
    # a spike in the 10:59 minute is NOT in the 11:00-11:05 range
    mins2 = [(s, o, (h + 500 if s == FIRE_ORB - 360 else h), l, c) for s, o, h, l, c in mins]
    res = run("nq_orb_pro", tape_of(mins2))
    assert {h["name"]: h["price"] for h in res.hlines}["range high"] == hi


def test_orb_short_side_and_the_other_leg_is_cancelled():
    mins, atr, hi, lo, sl = orb_day()
    fill = lo - 2 * TICK
    path = [(FIRE_ORB + 10, 20103), (FIRE_ORB + 20, lo - TICK), (FIRE_ORB + 30, hi + 20)]     # sells, then the other
    t, = run("nq_orb_pro", tape_of(mins, path)).trades                                       # side's level is hit
    assert t.side == "short" and t.entry_price == fill and t.exit_reason in ("sl", "time", "eod")


def test_orb_is_flat_at_1330_and_cancels_at_1325():
    mins, atr, hi, lo, sl = orb_day()
    res = run("nq_orb_pro", tape_of(mins, [(FIRE_ORB + 20, hi + TICK), (13 * 3600 + 31 * 60, hi + 2)]))
    t, = res.trades
    assert t.exit_reason == "time"
    assert REGISTRY["nq_orb_pro"]({}).provenance()["flat_et"] == "13:30"


# -------------------------------------------------------------------------------------------- pm straddle
def test_pm_straddle_is_one_atr_either_side_with_a_600_take():
    mins = day_minutes(31, until_s=FIRE_PM)
    atr, anchor, upper, lower, sl = straddle_expectation(mins, FIRE_PM, 1.0)
    assert upper - anchor == pytest.approx(atr, abs=0.25)
    fill = upper + TICK
    tp4, tp2 = take_points(600, 4, PV, 4.0, TICK), take_points(600, 2, PV, 4.0, TICK)
    assert (tp4, tp2) == (7.75, 15.25)
    t, = run("nq_pm_flex", tape_of(mins, [(FIRE_PM + 5, upper), (FIRE_PM + 60, fill + tp4 + TICK)])).trades
    assert t.exit_price == fill + tp4 and t.net >= 600 and t.qty == 4
    t, = run("nq_pm_flex", tape_of(mins, [(FIRE_PM + 5, upper), (FIRE_PM + 60, fill + tp2 + TICK)]), qty=2).trades
    assert t.exit_price == fill + tp2 and t.net >= 600 and t.qty == 2


def test_pm_straddle_runs_to_1558_and_cancels_at_1553():
    s = REGISTRY["nq_pm_flex"]({})
    assert (s.fire, s.cancel_et, s.flat_et) == ("13:30:00", "15:53", "15:58")
    assert s.times() == ["13:30:00", "15:53", "15:58"]


# -------------------------------------------------------------------------------------------- the calendar
def test_half_days_skip_the_strategies_that_would_arm_or_hold_in_a_closed_market():
    thanksgiving_friday, dec24, ordinary = dt.date(2026, 11, 27), dt.date(2026, 12, 24), dt.date(2026, 11, 20)
    for name in ("nq_pm_flex", "nq_orb_pro"):
        s = REGISTRY[name]({})
        assert not s.trades_on(thanksgiving_friday) and not s.trades_on(dec24) and s.trades_on(ordinary)
    nyam = REGISTRY["nq_nyam_flex"]({})            # flat at 11:00: a half day is an ordinary morning for it
    assert nyam.trades_on(thanksgiving_friday) and nyam.trades_on(dec24)


def test_the_tester_strategies_follow_the_desk_config():
    from homebase.config import levels_reference
    cfg = levels_reference()
    for name in ("nq_nyam_flex", "nq_nyam_pro", "nq_orb_pro", "nq_pm_flex"):
        s = REGISTRY[name]({})
        assert (s.fire, s.cancel_et, s.flat_et) == (cfg[name].fire_et, cfg[name].cancel_et, cfg[name].flat_et)
        assert s.session_window[0] == "00:00" and s.session_independent and s.bar_minutes == 1
        assert not cfg[name].enabled and cfg[name].kind == "levels"          # off, unbooked
        assert s.provenance()["desk_cfg"]["shape"] == cfg[name].shape
