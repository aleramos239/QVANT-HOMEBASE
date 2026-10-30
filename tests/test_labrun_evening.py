"""A Lab strategy whose session opens the evening before its date (window start "-20:00": the tester reads it since
b489f667). The runner hosts it through midnight, like the tester's day. Since 2026-10-30 (owner: "trade at any time")
the Desk books any window that fits one Desk day (18:00 ET -> 17:00 ET the next day): morning, afternoon to 16:55,
evening, overnight across midnight. Times order in that day (core.clock.desk_minutes). A window that does not fit
stays shadow only."""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict
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


def test_a_day_whose_window_does_not_fit_one_desk_day_is_never_hosted_in_desk_mode(days):  # noqa: F811
    side = deskside.DeskSide("lab_lab_x", ["ab", "2026-10-09T12:00:00+00:00"], D.isoformat(), ["a1"])
    src = EVE.replace('session_window = ("-20:00", "16:00")', 'session_window = ("-17:00", "16:00")')
    day = days(src, desk=side, send=lambda body, timeout=5.0: {}, tell=lambda row: None)
    assert (day.state, day.summary()["why"]) == ("stopped", host.EVENING_DESK)
    assert day.child_alive() is False and day.summary()["orders"] == []


EVE_REC = {"session_window": ["-20:00", "16:00"], "auto_limits": {"max_trades_day": 1}, "qty": 1}


def test_an_overnight_record_has_desk_limits_ordered_across_midnight():
    r = cfg_rec(**EVE_REC)
    assert labcfg.evening(r) is True and labcfg.evening(cfg_rec()) is False
    assert labcfg.window(r) == ("20:00", "16:00") and labcfg.span(r) == (120, 1320)
    assert labcfg.derive_limits(r) == labcfg.LabLimits(1, 1, 0.0, "15:54", "15:55")       # the 16:00 close keeps 15:55
    for last, flat in (("23:00", "03:00"), ("20:00", "00:00"), ("02:00", "16:55"), ("21:00", "21:30")):
        typed = {"max_trades_day": 1, "max_qty": 1, "max_risk_usd": 300, "last_entry_et": last, "flat_et": flat}
        assert labcfg.parse_limits(typed, r).flat_et == flat and deskside.limits_read(typed, r) is True, (last, flat)
    for last, flat, say in (("19:00", "03:00", labcfg.SAY_LAST),        # before its 20:00 start
                            ("03:00", "23:00", labcfg.SAY_LAST),        # last after flat in the Desk day
                            ("11:00", "16:56", labcfg.SAY_FLAT), ("11:00", "17:30", labcfg.SAY_FLAT)):
        typed = {"max_trades_day": 1, "max_qty": 1, "max_risk_usd": 300, "last_entry_et": last, "flat_et": flat}
        with pytest.raises(ValueError) as e:
            labcfg.parse_limits(typed, r)
        assert str(e.value) == say and deskside.limits_read(typed, r) is False, (last, flat)
    for bad in (["-20:00", "-16:00"], ["-2000", "16:00"], ["-20:00"], "-20:00"):   # not a window: read as before
        assert labcfg.evening(cfg_rec(session_window=bad)) is False, bad


def test_derived_limits_match_on_both_sides_for_every_kind_of_window():
    for w, want in ((["-18:00", "00:00"], ("23:59", "00:00")), (["-20:00", "03:00"], ("02:59", "03:00")),
                    (["16:00", "17:00"], ("16:54", "16:55")), (["12:00", "16:30"], ("16:29", "16:30")),
                    (["03:00", "09:30"], ("09:29", "09:30")), (["09:25", "16:00"], ("15:54", "15:55")),
                    (["00:00", "15:30"], ("15:29", "15:30"))):
        r = cfg_rec(session_window=w, auto_limits={"max_trades_day": 1}, qty=1)
        got = labcfg.derive_limits(r)
        assert (got.last_entry_et, got.flat_et) == want, w
        assert deskside.own_limits({**r, "name": "x"}) == {**asdict(got), "max_risk_usd": 0.0}, w
        assert (labcfg.window_note(r, got) is None) is (w[1] == got.flat_et), w     # a note only when it closes early
    for w in (["-17:00", "00:00"], ["-18:00", "23:00"], ["09:00", "18:30"], ["19:00", "23:00"], ["17:30", "17:45"]):
        r = cfg_rec(session_window=w, auto_limits={"max_trades_day": 1}, qty=1)
        assert labcfg.span(r) is None and labcfg.derive_limits(r) is None, w
        assert deskside.own_limits({**r, "name": "x"}) is None, w
        with pytest.raises(ValueError) as e:
            labcfg.parse_limits({"max_trades_day": 1, "max_qty": 1, "max_risk_usd": 300, "last_entry_et": "11:00",
                                 "flat_et": "15:55"}, r)
        assert str(e.value) == labcfg.SAY_EVENING, w


def test_the_same_day_records_are_read_as_before():
    r = cfg_rec(session_window=["08:20", "15:55"], qty=4, auto_limits={"max_trades_day": 1})
    assert labcfg.derive_limits(r) == labcfg.LabLimits(1, 4, 0.0, "15:54", "15:55")
    assert deskside.own_limits(r) == {"max_trades_day": 1, "max_qty": 4, "max_risk_usd": 0.0, "last_entry_et": "15:54",
                                      "flat_et": "15:55"}


def test_an_overnight_record_is_booked_and_one_that_does_not_fit_is_not(tmp_path):
    d = mkdesk(tmp_path / "a", limits=None, qty=0, window=("-20:00", "16:00"), rec_kw={"auto_limits": {"max_trades_day": 1}})
    run(d.ld.set_book(LAB, [{"account": "a1", "qty": 1}]))
    assert [r["account"] for r in d.cfg.book[LAB]] == ["a1"]
    d = mkdesk(tmp_path / "b", limits=None, qty=0, window=("-17:00", "16:00"), own_store=True, rec_kw={"auto_limits": {"max_trades_day": 1}})
    assert labcfg.limits_of(d.cfg, LAB) is None
    with pytest.raises(labdesk.Refused) as e:
        run(d.ld.set_book(LAB, [{"account": "a1", "qty": 1}]))
    assert str(e.value) == labcfg.SAY_EVENING and d.cfg.book.get(LAB) in (None, [])


def test_the_settings_lock_covers_the_evening_before_and_the_morning_of_an_evening_session(tmp_path):
    d = mkdesk(tmp_path, limits=None, qty=0, window=("-20:00", "16:00"), start=False)
    rec = labcfg.record_of(d.cfg, LAB)
    for at, want in (((19, 59), False), ((20, 0), True), ((23, 30), True), ((3, 0), True), ((15, 59), True), ((16, 0), False),
                     ((10, 0), True)):
        d.clock.dt = dt.datetime(2026, 9, 14, *at, tzinfo=ZoneInfo("America/New_York"))        # a Monday
        assert d.ld._in_session(rec) is want, at


# ---------------------------------------------------------------- the engine and the runner in the Desk day
def test_a_same_night_record_is_booked_on_an_account(tmp_path):
    d = mkdesk(tmp_path, limits=None, qty=0, window=("-18:00", "00:00"), rec_kw={"auto_limits": {"max_trades_day": 1}})
    assert labcfg.limits_of(d.cfg, LAB) == labcfg.LabLimits(1, 1, 0.0, "23:59", "00:00")
    run(d.ld.set_book(LAB, [{"account": "a1", "qty": 1}]))
    assert [r["account"] for r in d.cfg.book[LAB]] == ["a1"]


def test_an_overnight_day_is_hosted_in_desk_mode_and_its_flat_lands_on_the_right_evening(days):  # noqa: F811
    for flat, at in (("23:30", "-23:30"), ("03:00", "03:00"), ("15:55", "15:55")):
        side = deskside.DeskSide("lab_lab_x", ["ab", "2026-10-09T12:00:00+00:00"], D.isoformat(), ["a1"])
        day = days(meta_source(session_window=("-20:00", "16:00"), bar_minutes=5), desk=side,
                   send=lambda body, timeout=5.0: {}, tell=lambda row: None, flat_et=flat)
        assert day.summary()["why"] != host.EVENING_DESK and day._evening is True
        assert day._flat_ns() == host.et_ns(D, at), flat


def test_past_the_flat_time_and_the_entry_window_read_the_desk_day():
    from homebase.desk.engine_lab import lab_in_window, lab_past_flat
    on = labcfg.strategy_cfg(cfg_rec(**EVE_REC), labcfg.LabLimits(1, 1, 300.0, "02:00", "03:00"))   # 20:00 -> 03:00
    for at, past, inside in (((19, 59), False, False), ((20, 0), False, True), ((23, 59), False, True),
                             ((0, 30), False, True), ((2, 0), False, True), ((2, 1), False, False),
                             ((3, 0), True, False), ((12, 0), True, False), ((17, 30), True, False)):
        t = dt.time(*at)
        assert lab_past_flat(on, t) is past and lab_in_window(on, t.strftime("%H:%M")) is inside, at
    pm = labcfg.strategy_cfg(cfg_rec(session_window=["16:00", "17:00"], auto_limits={"max_trades_day": 1}), None)
    assert (pm.accept_from_et, pm.accept_until_et, pm.flat_et) == ("16:00", "16:55", "16:55")
    for at, past, inside in (((15, 59), False, False), ((16, 30), False, True), ((16, 55), True, True),
                             ((17, 0), True, False), ((18, 30), False, False)):
        t = dt.time(*at)
        assert lab_past_flat(pm, t) is past and lab_in_window(pm, t.strftime("%H:%M")) is inside, at
    day = labcfg.strategy_cfg(cfg_rec(session_window=["09:25", "16:00"], auto_limits={"max_trades_day": 1}), None)
    for at, want in (((9, 30), False), ((15, 54), False), ((15, 55), True), ((17, 30), True), ((3, 0), False)):
        assert lab_past_flat(day, dt.time(*at)) is want, at
