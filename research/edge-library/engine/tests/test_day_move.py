"""DAY_MOVE: the late-day momentum family (families/day_move.py), written with the family (hunt Amendment O, batch 4b). Synthetic days
with exact numbers: flat at 15000 to 09:30, the 09:30 bar moves x points, flat from there; test_blocks.DAILY's 20-day range is 100
points. No net, win rate or profit factor is read."""
import numpy as np

import families
import l2sim as S
from families import blocks as B
from families import day_move as DM
from test_blocks import D, DAILY, daily_rows, minute_tape

PX, V = 15000.0, 40
MS0 = S.et_ns(D, "00:00") // 1_000_000
BASE = {"hold_to": "day", "tf": "5", "sess": "pm", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0}


def sec(h, m=0):
    return h * 3600 + m * 60


def q(n, px):
    return [(px, px, px, px, V)] * n


def day(x, after=None, late=0):
    """00:00 .. 15:59 (960 minutes): flat at PX, the bar `late` minutes after 09:30 opens at PX and closes at PX + x, flat there to the
    end; `after` = the price of every minute from 15:00 on."""
    b = q(570 + late, PX) + [(PX, max(PX, PX + x), min(PX, PX + x), PX + x, V)] + q(389 - late, PX + x)
    if after is not None:
        b[900:] = q(60, after)
    return b


def gap_tape(bars, late):
    """The day's tape without the minutes 09:30 .. 09:30 + late: the open's first bar comes `late` minutes late."""
    a, b = minute_tape(bars[:570], "00:00"), minute_tape(bars[570 + late:], f"09:{30 + late}")
    return S.Tape("NQ", D, "NQM3", *(np.concatenate([x, y]) for x, y in ((a.ts, b.ts), (a.px, b.px), (a.size, b.size))))


def run(params, bars=None, daily=DAILY, tape=None):
    """-> [(the fill's minute of the day, side)] in order."""
    st = DM.DayMove({**BASE, **params})
    st.ROLLS = frozenset()
    res = S.run_session(st, tape or minute_tape(bars, "00:00"), daily=list(daily), on_error="raise")
    return [((t["entry_ms"] - MS0) // 60000, t["side"]) for t in sorted(res.trades, key=lambda t: t["entry_ms"])]


def test_a_move_of_k_times_the_20_day_range_at_15_00_goes_with_it_at_the_next_bar():
    assert run({}, day(40.0)) == [(sec(15) // 60, "long")]            # +40 >= 0.25 x 100: long, filled in the 15:00 minute
    assert run({}, day(-40.0)) == [(sec(15) // 60, "short")]


def test_the_threshold_is_k_times_the_range_at_or_above():
    assert run({"k": 0.25}, day(25.0)) == [(sec(15) // 60, "long")]
    assert run({"k": 0.25}, day(24.75)) == []
    assert run({"k": 0.35}, day(30.0)) == []


def test_a_flat_day_does_nothing():
    assert run({}, day(0.0)) == []


def test_at_sets_the_clock_time():
    assert run({"at": "14:30"}, day(40.0)) == [(sec(14, 30) // 60, "long")]


def test_fewer_than_20_daily_bars_is_no_trade():
    assert run({}, day(40.0), daily=daily_rows([100.0] * 19)) == []
    assert run({}, day(40.0), daily=daily_rows([100.0] * 20)) == [(sec(15) // 60, "long")]


def test_the_range_is_the_mean_of_the_last_20_daily_ranges():
    rows = daily_rows([1000.0] * 5 + [60.0] * 10 + [140.0] * 10)      # the last 20 average 100; all 25 average 280; the last one is 140
    assert run({}, day(30.0), daily=rows) == [(sec(15) // 60, "long")]   # 30 >= 0.25 x 100 (not 0.25 x 280, not 0.25 x 140)


def test_nothing_is_read_after_at_a_crash_from_15_00_changes_nothing():
    assert run({}, day(40.0, after=PX - 500.0)) == run({}, day(40.0)) == [(sec(15) // 60, "long")]


def test_a_09_30_open_more_than_5_minutes_late_is_no_trade():
    assert run({}, tape=gap_tape(day(40.0, late=6), 6)) == []
    assert run({}, tape=gap_tape(day(40.0, late=5), 5)) == [(sec(15) // 60, "long")]


def test_the_family_is_registered_wrapped_and_runs_in_the_pm_pass_only():
    assert families.ERRORS == {}
    cls, inputs, both, notes = families.REGISTRY["day_move"]
    lib = families.library("day_move")
    assert cls is DM.DayMove and both is False and cls.FEATURES == () and lib["roots"] == ("NQ", "ES", "GC")
    assert lib["variants"] == [{"k": 0.15}, {"k": 0.25}, {"k": 0.35}] and cls({"tf": "5"}).p["max_tr"] == 1
    assert families.MODULE_OF["day_move"] == "day_move" and issubclass(B.WRAPPED["day_move"], DM.DayMove)
    for s in ("asia", "london", "pre", "nyam", "mid", "pm", "eve"):
        assert DM.DayMove({"tf": "5", "sess": s, "hold_to": "day"}).sessions() == (["pm"] if s == "pm" else [])
