"""Task B4, fix round 2: the re-review's findings on the after-a-crash path. Scenario tests on a Runner with a stub Desk
(tests/test_labrun_fix1.py's kit), crashed and started again; tmp_path stores, no socket, no service.

    N1   a tell-log that starts with an older promotion's head line is still this promotion's day
    N2   the heartbeat names only what the runner is hosting now, and days that are final
    N3   a day that was let go never writes over the new day's file
    (a)  the eod flatten has a row in the day file, with the Desk's sentence when it did not go through
    (b)  a stop the Desk never got in its ten seconds is asked once more when the Desk's stream is back"""
from __future__ import annotations

from homebase.labrun import host, store
from tests.labrun_desk_util import (ACCOUNT, DATE, DESK_ID, ONE, StubDesk, at, desk_day, feed, filled, mark_of, rnd,
                                    sidecar, snap, state)
from tests.test_labrun_fix1 import (LIVE, NO_RESUME, SHORT, a_short_day, booked_at_nine, crash, days, kits, minute,  # noqa: F401
                                    not_ok, restart)
from tests.test_labrun_host import MARKET_930, rec

WORKING = {"status": "working"}
NEW = "2026-10-10T12:00:00+00:00"            # promoted again that morning


def mark2() -> list:
    r = rec(ONE, promoted_utc=NEW)
    return [r["sha256"], r["promoted_utc"]]


def snap2(**kw) -> dict:
    return {**snap(ONE, **kw), "mark": mark2()}


def side2(**kw) -> dict:
    return {**sidecar(ONE, **kw), "mark": mark2()}


# ================================================================ N1: the last head line of this promotion
def promoted_again_in_the_morning(kits):
    """Promotion A is booked overnight (its head line for today is in the tell-log). Before the window: accounts off,
    promote B, accounts on. B's day runs in desk mode, its entry fills, the 09:31 bar is seen."""
    k = kits()
    k.promote(ONE)
    store.put_desk("lab_x", sidecar(ONE), k.at)
    k.clock("08:00:00")
    k.open()
    k.rows("08:20:00", [21000.0] * 2)
    k.r.take(state(snap(ONE)))
    k.r.sync()
    assert k.r.day("lab_x").mode == "desk"
    store.put_desk("lab_x", sidecar(ONE, accounts=()), k.at)
    k.r.sync()
    k.promote(ONE, promoted_utc=NEW)
    store.put_desk("lab_x", side2(), k.at)
    k.r.take(state(snap2()))
    k.r.sync()
    assert k.r.day("lab_x").mode == "desk"
    assert [t["mark"][1] for t in store.tells("lab_x", DATE, k.at)] == [mark_of(ONE)[1], NEW]      # two head lines
    minute(k, "09:29:01")
    k.r.take(("desk", "strategy", snap2(answered=[2], **LIVE)))
    minute(k, "09:30:01", px=21010.0)
    assert k.today()["mode"] == "desk" and k.stub.ops() == [["entry"]]
    return k


def test_a_day_promoted_again_that_morning_is_still_picked_up_in_desk_mode_after_a_crash(kits):
    """The reviewer's probe "repromote": read_tells saw promotion A's head first and found nothing to pick up; the
    begun desk day was hosted in shadow, its file rewritten, the beat said shadow."""
    k = promoted_again_in_the_morning(kits)
    before = k.today()
    crash(k)
    k2 = restart(kits, "09:31:30", [("08:20:00", [21000.0] * 2), ("09:29:01", [21000.0] * 60), ("09:30:01", [21010.0] * 60)],
                 snap2(answered=[2], **LIVE))
    day = k2.r.day("lab_x")
    assert day is not None and day.mode == "desk" and day.state == "running" and k2.stub.bodies == []
    s = k2.today()
    assert s["mode"] == "desk" and s["orders"] == before["orders"]
    k2.r.beat()
    assert k2.stub.said[-1]["strategies"][DESK_ID]["mode"] == "desk"
    minute(k2, "09:31:31", n=89)                                             # .. 09:32:59
    minute(k2, "09:33:00", n=1)
    assert k2.stub.bodies == []                                              # it is filled: no cancel at 09:33


def test_the_tell_log_is_read_from_the_last_head_line_of_this_promotion():
    a, b = ["sha", "promotion A"], ["sha", "promotion B"]
    ev = [{"seq": 1, "t_ns": 1, "kind": "session", "flat": True}, {"seq": 1, "intents": []}]
    lines = [{"head": 1, "mark": a}, {"head": 1, "mark": b}, *ev]
    assert host.read_tells(lines, b)["last"] == 1                            # B's day: its own lines only
    assert host.read_tells(lines, a) is None                                 # A's: another promotion's head follows it
    assert host.read_tells([{"head": 1, "mark": a}, *ev, {"head": 1, "mark": b}], b)["last"] == 0     # A's events are not B's
    assert host.read_tells([{"head": 1, "mark": a}, *ev, {"head": 1, "mark": b}], a) is None
    assert host.read_tells([{"head": 1, "mark": a}, *ev], a)["last"] == 1    # one promotion: as before
    assert host.read_tells([{"head": 1, "mark": a}, {"head": 1, "mark": a}, *ev], a)["last"] == 1
    assert host.read_tells(ev, a) is None and host.read_tells([], a) is None


def test_the_old_promotions_begun_day_is_never_the_new_promotions(kits):
    """Promoted again mid-day (the old day had begun): the new promotion's day has nothing to pick up, and it is
    shadow today -- the old day's events in the same file are not its own."""
    k = booked_at_nine(kits)
    minute(k, "09:29:01")
    k.promote(ONE, promoted_utc=NEW)
    store.put_desk("lab_x", side2(), k.at)                                   # (booked again at once)
    k.r.take(state(snap2()))
    k.r.sync()
    crash(k)
    k2 = restart(kits, "09:31:30", [("09:20:00", [21000.0] * 2), ("09:29:01", [21000.0] * 60), ("09:30:01", [21000.0] * 60)],
                 snap2())
    day = k2.r.day("lab_x")
    assert day is not None and day.mode == "shadow" and k2.stub.bodies == []


# ================================================================ N2: who the heartbeat names
def test_after_a_crash_with_the_tick_stream_down_no_beat_names_the_strategy(kits):
    """The reviewer's probe "blindbeat". An entry is working; the runner is killed and starts again while the chart
    service's stream is not live. Nothing is hosted. A beat that named the strategy would switch off the Desk's own
    rule (no beat for 20 s: its unfilled entries are cancelled)."""
    k = booked_at_nine(kits)
    minute(k, "09:29:01")
    k.r.beat()
    assert k.stub.said[-1]["strategies"][DESK_ID]["mode"] == "desk" and k.stub.ops() == [["entry"]]
    crash(k)
    k2 = kits(live=False)                                                    # the tick stream is not live
    k2.r.sync()
    k2.r.beat()
    assert k2.r.hosting() == [] and k2.stub.said[-1]["strategies"] == {}
    k2.r.take(state(snap(orders={1: WORKING}, answered=[2])))                # the Desk's stream is up
    k2.wall[0] += 60.0
    k2.r.idle()
    k2.r.sync()
    k2.r.beat()
    assert k2.stub.said[-1]["strategies"] == {} and k2.stub.bodies == []
    k2.r.take(("connect",))                                                  # ... and while the backlog comes in
    k2.open()
    k2.rows("09:29:01", [21000.0] * 60)
    k2.r.sync()
    k2.r.beat()
    assert k2.stub.said[-1]["strategies"] == {}


def test_only_hosted_strategies_and_final_days_are_named(kits):
    k = kits()
    k.promote(ONE)                                                           # hosted in a moment
    k.promote(MARKET_930, name="lab_y")
    store.put_desk("lab_y", sidecar(MARKET_930), k.at)
    k.promote(MARKET_930, name="lab_done")
    k.promote(MARKET_930, name="lab_stop")
    k.promote(MARKET_930, name="lab_run")                                    # a day file that is NOT final
    sha = rec(MARKET_930)["sha256"]
    base = {"date": DATE, "sha256": sha, "promoted_utc": rec(MARKET_930)["promoted_utc"], "orders": [], "trades": [],
            "net": 0.0, "match": None, "updated_utc": "x"}
    store.put_day("lab_done", {**base, "state": "done", "why": None, "mode": "desk"}, k.at)
    store.put_day("lab_stop", {**base, "state": "stopped", "why": "Too slow: no answer in 1 s."}, k.at)
    k.clock("09:00:00")
    k.r.sync()
    k.r.beat()                                                               # no print yet: nothing is hosted, and
    assert sorted(k.stub.said[-1]["strategies"]) == ["lab_lab_done", "lab_lab_stop"]     # only the final days are named
    k.open()
    k.rows("09:20:00", [21000.0] * 2)
    k.r.sync()
    store.put_day("lab_run", {**base, "state": "running", "why": None, "mode": "desk"}, k.at)     # (written over its own)
    k.r.day("lab_run").drop()
    del k.r._days["lab_run"]                                                 # ... as if it were not hosted
    k.r.beat()
    named = k.stub.said[-1]["strategies"]
    assert named == {DESK_ID: {"state": "waiting", "why": None, "mode": "shadow"},
                     "lab_lab_y": {"state": "waiting", "why": None, "mode": "desk"},
                     "lab_lab_done": {"state": "done", "why": None, "mode": "desk"},
                     "lab_lab_stop": {"state": "stopped", "why": "Too slow: no answer in 1 s.", "mode": "shadow"}}


# ================================================================ N3: a day that was let go writes nothing more
def test_a_day_let_go_at_a_re_promotion_never_writes_over_the_new_days_file(kits):
    """The reviewer's probe "letgo": the old day's stop got no answer; each time it was asked again the old
    promotion's summary (mode desk, running) was written over the new day's file."""
    NO = StubDesk.NO_ANSWER
    k = booked_at_nine(kits, stub=StubDesk("took", NO, NO, NO, NO))
    minute(k, "09:29:01")
    k.promote(ONE, promoted_utc="2026-10-10T13:00:00+00:00")
    k.r.sync()
    assert k.r.day("lab_x").mode == "shadow" and len(k.r._ending) == 1
    for _ in range(3):
        k.wall[0] += 1.1
        k.r.idle()
        f = k.file()
        assert f["promoted_utc"] == "2026-10-10T13:00:00+00:00" and "mode" not in f     # the new day's own file
    assert k.stub.ops() == [["entry"], ["stop"], ["stop"], ["stop"], ["stop"]]         # the stop WAS asked again


def test_a_day_switched_off_and_on_again_is_not_written_over_by_the_old_days_stop(kits):
    NO = StubDesk.NO_ANSWER
    k = booked_at_nine(kits, stub=StubDesk("took", NO, NO))
    minute(k, "09:29:01")
    store.set_enabled("lab_x", False, k.at)
    k.r.sync()
    off = k.file()
    assert off["state"] == "off" and len(k.r._ending) == 1
    k.wall[0] += 1.1
    k.r.idle()
    assert k.file() == off                                                   # the retry wrote nothing


# ================================================================ (a): the eod flatten has a row
def test_the_eod_flatten_has_a_row_in_the_day_file(kits):
    k = a_short_day(kits)
    k.clock("10:00:03")
    rows = k.today()["orders"]
    assert rows == [{"t": "09:30:00", "text": "Buy at market, stop 20,990.00", "refused": None},
                    {"t": "10:00:00", "text": "Flatten (eod)", "refused": None}]
    assert [x["text"] for x in k.journal() if x["kind"] == "order"][-1] == "Flatten (eod)"


def test_an_eod_flatten_that_did_not_go_through_says_so_on_its_row(kits):
    k = a_short_day(kits)
    k.stub.script = [StubDesk.NO_ANSWER] * 30
    k.clock("10:00:03")
    assert k.today()["orders"][-1] == {"t": "10:00:00", "text": "Flatten (eod)", "refused": "The Desk did not answer."}
    for _ in range(12):
        k.wall[0] += 1.0
        k.r.idle()
    assert k.today()["orders"][-1]["refused"] == "The Desk did not answer."  # ten seconds on: still there


def test_an_eod_flatten_the_desk_could_not_carry_out_carries_the_desks_sentence(kits):
    again = a_short_day(kits)
    again.stub.script = [not_ok("Check it: the close order was not confirmed. Its stop is still working.")] * 5
    again.clock("10:00:03")
    for _ in range(4):
        again.wall[0] += 1.0
        again.r.idle()
    assert again.today()["orders"][-1]["refused"] == "Check it: the close order was not confirmed. Its stop is still working."
    assert again.stub.ops() == [["entry"], ["flatten"], ["flatten"]]         # once more, then its answer stands


def test_an_eod_flatten_that_waits_for_the_desks_day_reads_unanswered_until_it_goes(kits):
    k = a_short_day(kits)
    k.r.take(("desk", "state", {"date": "2026-10-12", "armed": True, "strategies": {}}))
    k.clock("10:00:03")
    assert k.stub.ops() == [["entry"]] and k.today()["orders"][-1]["refused"] == "The Desk did not answer."
    k.r.take(state(snap(SHORT, answered=[2], **LIVE)))
    k.wall[0] += 1.0
    k.r.idle()
    assert k.stub.ops() == [["entry"], ["flatten"]] and k.today()["orders"][-1]["refused"] is None


# ================================================================ (b): a stop the Desk never got, once more
def a_stop_that_ran_out(days, script=None):
    """The strategy raised with a trade open; its stop (flatten) got no answer for the whole ten seconds."""
    from tests.test_labrun_host import STOPS, planted
    src = planted(STOPS["raises"][0])
    stub = StubDesk("took", *[StubDesk.NO_ANSWER] * 11)
    day, stub, side, _, wall = days(src, stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    day.on_desk(snap(src, answered=[2], **LIVE))
    side.down()                                                              # the Desk goes away
    feed(day, "09:30:01", [21000.0] * 60)                                    # 09:31: it raises -> the stop
    for _ in range(12):
        wall.t += 1.0
        day.tend()
    assert day.state == "stopped" and not day.pending() and len(stub.bodies) == 12
    return src, day, stub, side, wall


def test_a_stop_the_desk_never_got_is_asked_once_more_when_its_stream_is_back(days):
    src, day, stub, side, wall = a_stop_that_ran_out(days)
    wall.t += 300.0
    day.tend()
    assert len(stub.bodies) == 12                                            # nothing while the Desk is away
    day.on_desk(snap(src, answered=[2], **LIVE))                             # its stream is back: it never got the stop
    assert len(stub.bodies) == 13 and stub.bodies[12] == stub.bodies[1]      # the same request: seq, intents, t_ns
    assert stub.bodies[12]["intents"] == [{"op": "stop", "why": "Strategy error: boom", "flatten": True}]
    day.on_desk(snap(src, answered=[2], **LIVE))
    wall.t += 60.0
    day.tend()
    assert len(stub.bodies) == 13                                            # once


def test_no_stop_is_asked_again_when_the_stream_shows_the_desk_did_get_it(days):
    src, day, stub, side, wall = a_stop_that_ran_out(days)
    day.on_desk(snap(src, answered=[2, 4], stopped="Strategy error: boom", **LIVE))
    assert len(stub.bodies) == 12
    day.on_desk(snap(src, answered=[2, 4], stopped="Strategy error: boom", **LIVE))
    assert len(stub.bodies) == 12


def test_a_switched_off_days_stop_is_asked_once_more_too_though_it_is_no_longer_hosted(kits):
    NO = StubDesk.NO_ANSWER
    k = booked_at_nine(kits, stub=StubDesk("took", *[NO] * 11))
    minute(k, "09:29:01")
    k.r.take(("desk_down",))
    store.set_enabled("lab_x", False, k.at)
    k.r.sync()
    for _ in range(12):
        k.wall[0] += 1.0
        k.r.idle()
    assert k.stub.ops() == [["entry"]] + [["stop"]] * 11
    k.r.take(state(snap(orders={1: WORKING}, answered=[2])))                 # the Desk is back; it never got the stop
    assert k.stub.ops() == [["entry"]] + [["stop"]] * 12 and k.stub.bodies[12] == k.stub.bodies[1]
    k.r.take(state(snap(orders={1: WORKING}, answered=[2])))
    k.wall[0] += 5.0
    k.r.idle()
    assert len(k.stub.bodies) == 13 and k.r._ending == []                    # once, and then it is let go for good
