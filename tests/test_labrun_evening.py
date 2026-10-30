"""A Lab strategy whose session opens the evening before its date (window start "-20:00": the tester reads it since
b489f667). The runner hosts it in SHADOW, through midnight, like the tester's day; the Desk never books it on an
account when it crosses midnight (its time-of-day logic cannot order that): no limits, no book, no typed limits.
One that ends at midnight (["-18:00", "00:00"], "same night") may be booked, flat by 23:55 (owner, 2026-10-30)."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from homebase.desk import labcfg, labdesk
from homebase.backtest.engine import Costs, run_session
from homebase.labrun import deskside, host
from tests.labdesk_util import LAB, mkdesk
from tests.test_engine import run
from tests.test_labcfg import desk_cfg, rec as cfg_rec
from tests.test_labrun_host import D, HEAD, days, meta_source, ticks  # noqa: F401 (days: the fixture)
from tests.test_labrun_shadowfills import cls_of, tape

EVE = HEAD + '''class E(Strategy):
    id, name, root = "e", "E", "NQ"
    session_window = ("-20:00", "16:00")
    bar_minutes = 5

    def times(self):
        return ["15:58"]

    def on_session(self, ctx):
        self.taken = False
        self.close_ns = ctx.now_ns + 5 * 60_000_000_000          # the 20:00 candle closes here (20:05:00)

    def on_bar(self, ctx, bar):
        if self.taken or bar.end_ns != self.close_ns:
            return
        self.taken = True
        if bar.c > bar.o:
            ctx.market("long", sl=bar.c - 20, tp=bar.c + 60, ref=bar.c)

    def on_time(self, ctx, et_time):
        if et_time == "15:58":
            ctx.flatten("time")
'''


def eve_rows() -> list:
    rows = ticks("-20:00", [21000.0, 21004.0, 21008.0, 21010.0, 21012.0], 60_000)       # the 20:00 candle, up
    rows += ticks("-20:05:01", [21012.0, 21013.0, 21015.0], 20_000)                      # the bar after it closes
    rows += ticks("-23:30", [21016.0, 21020.0], 1000)                                    # before midnight
    rows += ticks("03:00", [21030.0, 21025.0], 1000)                                     # after midnight, Tuesday
    rows += ticks("09:30", [21040.0, 21050.0], 1000)
    rows += ticks("15:57:50", [21060.0] * 3, 3000)                                       # up to 15:57:56
    rows += ticks("15:58:30", [21061.0, 21062.0], 1000)                                  # the flat
    rows += ticks("16:00:01", [21070.0])                                                 # after the window
    return rows


def test_an_evening_before_window_is_a_window_and_the_rest_are_still_not():
    for w in (("-20:00", "16:00"), ("-00:00", "09:30"), ("-23:59", "00:01")):
        assert host._window(list(w)), w
    for w in (("-20:00", "-16:00"), ("-25:00", "16:00"), ("-2000", "16:00"), ("--20:00", "16:00"), ("20:00", "-16:00"),
              ("-20:00:00", "16:00"), ("-", "16:00"), ("16:00", "09:25")):
        assert not host._window(list(w)), w


def test_the_evening_day_is_read_and_waits(days):  # noqa: F811
    day = days(meta_source(session_window=("-20:00", "16:00"), bar_minutes=5))
    assert (day.state, day.summary()["why"]) == ("waiting", None)


def test_the_evening_day_trades_through_midnight_exactly_as_the_tester_does(days):  # noqa: F811
    rows = eve_rows()
    day = days(EVE)
    for i in range(0, len(rows), 4):
        day.on_ticks(rows[i:i + 4])
    s = day.summary()
    assert s["state"] == "done" and s["why"] is None
    want = run_session(cls_of(EVE)(), tape(rows), Costs()).trades
    assert len(want) == 1 and len(s["trades"]) == 1                          # the entry went through the door at 20:05
    (got,), (w,) = s["trades"], [t.to_dict() for t in want]
    assert (got["side"], got["entry_px"], got["exit_px"], got["net"], got["reason"]) == \
        (w["side"], w["entry_price"], w["exit_price"], w["net"], w["exit_reason"])
    assert got["entry_t"] == "20:05:01" and got["exit_t"] == "15:58:30" and got["reason"] == "time"
    assert s["orders"][0]["refused"] is None                                 # the door did not say "too late"


def test_the_door_reads_an_evening_window_in_minutes_since_it_opened(days):  # noqa: F811
    day = days(EVE)
    assert day._evening is True
    assert day._limits["session_from_et"] == "00:00" and day._limits["last_entry_et"] == "20:00"   # 20:00 -> 16:00


def test_a_same_day_window_is_read_exactly_as_before(days):  # noqa: F811
    day = days(meta_source(session_window=("09:25", "16:00")))
    assert day._evening is False
    assert (day._limits["session_from_et"], day._limits["last_entry_et"]) == ("09:25", "16:00")


def test_an_evening_day_is_never_hosted_in_desk_mode(days):  # noqa: F811
    side = deskside.DeskSide("lab_lab_x", ["ab", "2026-10-09T12:00:00+00:00"], D.isoformat(), ["a1"])
    day = days(EVE, desk=side, send=lambda body, timeout=5.0: {}, tell=lambda row: None)
    assert (day.state, day.summary()["why"]) == ("stopped", host.EVENING_DESK)
    assert day.child_alive() is False and day.summary()["orders"] == []


EVE_REC = {"session_window": ["-20:00", "16:00"], "auto_limits": {"max_trades_day": 1}, "qty": 1}


def test_an_evening_record_has_no_desk_limits_and_no_typed_ones():
    r = cfg_rec(**EVE_REC)
    assert labcfg.evening(r) is True and labcfg.evening(cfg_rec()) is False
    assert labcfg.window(r) == ("20:00", "16:00")                             # (never the 09:25-16:00 default)
    assert labcfg.derive_limits(r) is None
    with pytest.raises(ValueError) as e:
        labcfg.parse_limits({"max_trades_day": 1, "max_qty": 1, "max_risk_usd": 300, "last_entry_et": "11:00",
                             "flat_et": "15:55"}, r)
    assert str(e.value) == labcfg.SAY_EVENING
    assert deskside.own_limits({**r, "name": "x"}) is None
    assert deskside.limits_read({"max_trades_day": 1, "max_qty": 1, "max_risk_usd": 300, "last_entry_et": "11:00",
                                 "flat_et": "15:55"}, r) is False
    for bad in (["-20:00", "-16:00"], ["-2000", "16:00"], ["-20:00"], "-20:00"):   # not a window: read as before
        assert labcfg.evening(cfg_rec(session_window=bad)) is False, bad


def test_the_same_day_records_are_read_as_before():
    r = cfg_rec(session_window=["08:20", "15:55"], qty=4, auto_limits={"max_trades_day": 1})
    assert labcfg.derive_limits(r) == labcfg.LabLimits(1, 4, 0.0, "15:54", "15:55")
    assert deskside.own_limits(r) == {"max_trades_day": 1, "max_qty": 4, "max_risk_usd": 0.0, "last_entry_et": "15:54",
                                      "flat_et": "15:55"}


def test_an_evening_record_is_never_booked_on_an_account(tmp_path):
    d = mkdesk(tmp_path, limits=None, qty=0, window=("-20:00", "16:00"), rec_kw={"auto_limits": {"max_trades_day": 1}})
    assert labcfg.limits_of(d.cfg, LAB) is None
    with pytest.raises(labdesk.Refused) as e:
        run(d.ld.set_book(LAB, [{"account": "a1", "qty": 1}]))
    assert str(e.value) == labcfg.SAY_EVENING
    assert d.cfg.book.get(LAB) in (None, [])
    with pytest.raises(ValueError) as e2:                                     # typed limits do not make it bookable
        run(d.ld.set_limits(LAB, {"max_trades_day": 1, "max_qty": 1, "max_risk_usd": 300, "last_entry_et": "11:00",
                                  "flat_et": "15:55"}))
    assert str(e2.value) == labcfg.SAY_EVENING


def test_the_settings_lock_covers_the_evening_before_and_the_morning_of_an_evening_session(tmp_path):
    d = mkdesk(tmp_path, limits=None, qty=0, window=("-20:00", "16:00"), start=False)
    rec = labcfg.record_of(d.cfg, LAB)
    for at, want in (((19, 59), False), ((20, 0), True), ((23, 30), True), ((3, 0), True), ((15, 59), True), ((16, 0), False),
                     ((10, 0), True)):
        d.clock.dt = dt.datetime(2026, 9, 14, *at, tzinfo=ZoneInfo("America/New_York"))        # a Monday
        assert d.ld._in_session(rec) is want, at


# ---------------------------------------------------------------- same night: opens 18:00+, ends at midnight (2026-10-30)
NIGHT = {"session_window": ["-18:00", "00:00"], "auto_limits": {"max_trades_day": 1}, "qty": 2}
TYPED = {"max_trades_day": 1, "max_qty": 1, "max_risk_usd": 300, "last_entry_et": "23:00", "flat_et": "23:55"}


def test_a_same_night_record_has_desk_limits_flat_by_2355_on_both_sides():
    r = cfg_rec(**NIGHT)
    assert labcfg.same_night(r) is True and labcfg.window(r) == ("18:00", "00:00")
    assert labcfg.derive_limits(r) == labcfg.LabLimits(1, 2, 0.0, "23:54", "23:55")
    assert deskside.own_limits({**r, "name": "x"}) == {"max_trades_day": 1, "max_qty": 2, "max_risk_usd": 0.0,
                                                       "last_entry_et": "23:54", "flat_et": "23:55"}
    assert labcfg.parse_limits(TYPED, r).flat_et == "23:55" and deskside.limits_read(TYPED, r) is True
    with pytest.raises(ValueError) as e:
        labcfg.parse_limits({**TYPED, "flat_et": "23:56"}, r)
    assert str(e.value) == labcfg.SAY_FLAT_EVENING
    assert deskside.limits_read({**TYPED, "flat_et": "23:56"}, r) is False
    with pytest.raises(ValueError):
        labcfg.parse_limits({**TYPED, "last_entry_et": "17:30"}, r)              # before the session opens
    assert labcfg.window_note(r, labcfg.derive_limits(r)) is None
    c = labcfg.strategy_cfg(r, labcfg.derive_limits(r))
    assert (c.accept_from_et, c.accept_until_et, c.flat_et) == ("18:00", "23:54", "23:55")


def test_an_evening_that_opens_before_1800_or_ends_after_midnight_stays_shadow_only():
    for w in (["-17:00", "00:00"], ["-20:00", "00:30"], ["-20:00", "16:00"]):
        r = cfg_rec(**{**NIGHT, "session_window": w})
        assert labcfg.same_night(r) is False and labcfg.derive_limits(r) is None, w
        assert deskside.own_limits({**r, "name": "x"}) is None and deskside.limits_read(TYPED, r) is False, w
        with pytest.raises(ValueError):
            labcfg.parse_limits(TYPED, r)


def test_a_same_night_record_is_booked_on_an_account(tmp_path):
    d = mkdesk(tmp_path, limits=None, qty=0, window=("-18:00", "00:00"), rec_kw={"auto_limits": {"max_trades_day": 1}})
    assert labcfg.limits_of(d.cfg, LAB) == labcfg.LabLimits(1, 1, 0.0, "23:54", "23:55")
    run(d.ld.set_book(LAB, [{"account": "a1", "qty": 1}]))
    assert [r["account"] for r in d.cfg.book[LAB]] == ["a1"]


def test_a_same_night_day_is_hosted_in_desk_mode_and_flat_on_the_evening_before(days):  # noqa: F811
    side = deskside.DeskSide("lab_lab_x", ["ab", "2026-10-09T12:00:00+00:00"], D.isoformat(), ["a1"])
    day = days(meta_source(session_window=("-20:00", "00:00"), bar_minutes=5), desk=side,
               send=lambda body, timeout=5.0: {}, tell=lambda row: None, flat_et="23:55")
    assert day.summary()["why"] != host.EVENING_DESK and day._evening is True
    assert day._flat_ns() == host.et_ns(D, "-23:55") < host.et_ns(D, "00:00")


def test_past_the_flat_time_reads_the_desk_day_for_an_evening():
    from homebase.desk.engine_lab import lab_past_flat
    eve = labcfg.strategy_cfg(cfg_rec(**NIGHT), labcfg.derive_limits(cfg_rec(**NIGHT)))
    for at, want in (((18, 0), False), ((23, 54), False), ((23, 55), True), ((0, 0), True), ((3, 0), True),
                     ((17, 59), True)):
        assert lab_past_flat(eve, dt.time(*at)) is want, at
    day = labcfg.strategy_cfg(cfg_rec(session_window=["09:25", "16:00"], auto_limits={"max_trades_day": 1}), None)
    for at, want in (((9, 30), False), ((15, 54), False), ((15, 55), True), ((20, 0), True), ((3, 0), False)):
        assert lab_past_flat(day, dt.time(*at)) is want, at
