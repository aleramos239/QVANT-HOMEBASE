"""Per-root trading day: classic Globex (18:00 -> 17:00 ET, weekdays) vs
24/7 roots (CME crypto since 2026-05-30: a session every day, 18:00 -> 18:00)."""
from __future__ import annotations

import datetime as dt

from homebase.charts.bars import BarBuilder, BarSpec, build
from homebase.charts.session import ET, always_open, session_date, session_range_ms, split_by_session
from homebase.charts.tick import BUY, Tick

WED, THU, FRI, SAT, SUN, MON = (dt.date(2026, 9, 23), dt.date(2026, 9, 24), dt.date(2026, 9, 25),
                                dt.date(2026, 9, 26), dt.date(2026, 9, 27), dt.date(2026, 9, 28))


def et(day: dt.date, hh: int, mm: int = 0, ss: int = 0) -> int:
    return int(dt.datetime.combine(day, dt.time(hh, mm, ss), ET).timestamp() * 1000)


def T(ms: int, p: float = 100000.0) -> Tick:
    return Tick(ms, p, 1, BUY, 0)


def test_which_roots_trade_around_the_clock():
    assert all(always_open(r) for r in ("BTC", "MBT", "ETH", "MET", "btc"))
    assert not any(always_open(r) for r in ("NQ", "GC", "", None))


def test_a_24_7_root_has_a_session_every_day_from_18_to_18():
    assert session_date(et(FRI, 16, 59), "BTC") == FRI
    assert session_date(et(FRI, 17, 30), "BTC") == FRI          # the classic maintenance hour trades
    assert session_date(et(FRI, 18, 0), "BTC") == SAT
    assert session_date(et(SAT, 10), "BTC") == SAT
    assert session_date(et(SUN, 17, 59), "BTC") == SUN
    assert session_date(et(SUN, 18, 0), "BTC") == MON
    assert session_range_ms(SAT, "BTC") == (et(FRI, 18), et(SAT, 18))
    assert session_range_ms(MON, "BTC") == (et(SUN, 18), et(MON, 18))


def test_classic_roots_keep_the_weekday_18_to_17_session():
    assert session_date(et(SAT, 10), "NQ") == MON               # a weekend print files into Monday
    assert session_date(et(SAT, 10)) == MON                     # no root = classic
    assert session_date(et(FRI, 16, 59), "NQ") == FRI
    assert session_range_ms(FRI, "NQ") == (et(THU, 18), et(FRI, 17))
    assert session_range_ms(FRI) == session_range_ms(FRI, "NQ")


def test_a_stretch_of_time_splits_into_the_sessions_it_crosses():
    """(session, start, end) pieces, each clipped to its session; time in no
    session (a classic root's 17:00 hour and weekend) belongs to no piece."""
    assert split_by_session("BTC", et(FRI, 17, 40), et(FRI, 18, 5)) == [
        (FRI, et(FRI, 17, 40), et(FRI, 18, 0)), (SAT, et(FRI, 18, 0), et(FRI, 18, 5))]
    assert split_by_session("NQ", et(WED, 16, 50), et(WED, 18, 10)) == [
        (WED, et(WED, 16, 50), et(WED, 17, 0)), (THU, et(WED, 18, 0), et(WED, 18, 10))]
    assert split_by_session("NQ", et(FRI, 16), et(SUN, 18, 30)) == [
        (FRI, et(FRI, 16), et(FRI, 17)), (MON, et(SUN, 18), et(SUN, 18, 30))]


def test_24_7_time_bars_run_through_17_00_and_into_the_weekend():
    ticks = [T(et(FRI, 16, 59, 30)), T(et(FRI, 17, 30, 5)), T(et(FRI, 18, 0, 5)), T(et(SAT, 10, 0, 5))]
    closed, cur = build(ticks, BarSpec.parse("time:60"), 5.0, "BTC")
    assert [(b.session, b.t) for b in closed + [cur]] == [
        (FRI.isoformat(), et(FRI, 16, 59)), (FRI.isoformat(), et(FRI, 17, 30)),
        (SAT.isoformat(), et(FRI, 18, 0)), (SAT.isoformat(), et(SAT, 10, 0))]


def test_a_24_7_hour_bar_closes_on_the_clock_at_18_not_17():
    bb = BarBuilder(BarSpec.parse("time:3600"), 5.0, "BTC")
    bb.add(T(et(FRI, 17, 10)))
    assert bb.on_clock(et(FRI, 17, 59, 59)) == []
    (b,) = bb.on_clock(et(FRI, 18, 0))
    assert b.session == FRI.isoformat() and b.t == et(FRI, 17, 0)


def test_a_classic_hour_bar_still_closes_at_the_17_00_session_end():
    bb = BarBuilder(BarSpec.parse("time:3600"), 0.25, "NQ")
    bb.add(T(et(FRI, 16, 30)))
    (b,) = bb.on_clock(et(FRI, 17, 0))
    assert b.t == et(FRI, 16, 0)


def test_a_late_print_after_the_clock_closed_a_24_7_session_opens_no_stray_bar():
    """A 17:59:59.9 print that reaches the builder after the clock closed the
    17:59 bar (past the 1.5 s grace) but before the new session's first
    print: its next bucket, 18:00, is the session END. It must not open a
    1-tick 18:00 bar labelled with the OLD session (an extra candle beside
    the new session's 18:00 bar; the old VWAP and cumulative delta take the
    print). Skipped live; it is on disk, and a reload files it in 17:59."""
    bb = BarBuilder(BarSpec.parse("time:60"), 5.0, "BTC")
    bb.add(T(et(FRI, 17, 59, 30)))
    (b,) = bb.on_clock(et(FRI, 18, 0))
    assert (b.t, b.session) == (et(FRI, 17, 59), FRI.isoformat())
    assert bb.add(T(et(FRI, 17, 59, 59) + 900)) == [] and bb.cur is None
    assert bb.add(T(et(FRI, 18, 0, 1))) == []
    assert (bb.cur.t, bb.cur.session, bb.cur.n) == (et(FRI, 18, 0), SAT.isoformat(), 1)


def test_a_classic_late_print_mid_session_still_opens_the_next_bucket():
    """Classic roots are unchanged inside the session: a print for a bar the
    clock already closed still opens the NEXT bucket (never a duplicate).
    Only at the 17:00 close does the same session-end rule apply: no 17:00
    bar in the maintenance hour under the closing session's label."""
    bb = BarBuilder(BarSpec.parse("time:60"), 0.25, "NQ")
    bb.add(T(et(THU, 10, 0, 30)))
    (b,) = bb.on_clock(et(THU, 10, 1, 1))
    assert b.t == et(THU, 10, 0)
    assert bb.add(T(et(THU, 10, 0, 59))) == []
    assert (bb.cur.t, bb.cur.session) == (et(THU, 10, 1), THU.isoformat())
    close = BarBuilder(BarSpec.parse("time:60"), 0.25, "NQ")
    close.add(T(et(THU, 16, 59, 30)))
    (b,) = close.on_clock(et(THU, 17, 0))
    assert b.t == et(THU, 16, 59)
    assert close.add(T(et(THU, 16, 59, 59) + 900)) == [] and close.cur is None
