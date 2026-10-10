"""Task B4, fix round 1: what the review found. All of it is "what happens after a restart, or when the Desk talks
back", so every test here is a scenario: a Runner on a temp store with a stub Desk (or one StrategyDay), driven through
the day, crashed and started again where the finding needs it. No socket to a desk, no service, tmp_path stores.

    C1   a day that ran in shadow is never turned into a desk day (a head-only tell-log is nothing to pick up)
    I1   the runner's own stop keeps being asked after the Desk's stream repeats `stopped`
    I2   a tell-log with an event means: never a shadow day for that date
    I3   nothing is sent for a day while the Desk's stream says another date
    I4   one flatten "eod" at the strategy's own window end
    M1-M7, the reviewer's unpinned rules, and the `t_ns` rule of a resend."""
from __future__ import annotations

import json
import threading
import time

import httpx
import pytest

from homebase.labrun import __main__ as cli
from homebase.labrun import host, store
from homebase.labrun.deskclient import DeskClient
from tests.labrun_desk_util import (ACCOUNT, DATE, DESK_ID, EVERY, ONE, REPLACE, StubDesk, at, desk_day, feed, filled,
                                    mark_of, ms_of, plots, rnd, sidecar, snap, state, ticks)
from tests.test_labrun_host import HEAD, MARKET_930, STOPS, planted
from tests.test_labrun_host import Desk as Kit

WORKING = {"status": "working"}
CANCELLED = {"status": "cancelled"}
NO_RESUME = "Could not pick up where it left off."
OTHER_DAY = "The Desk is on another day."
LIVE = dict(orders={1: filled()}, flat=False, rounds=[rnd(status="live", exit_=None, pnl=None, reason=None)])

# A market entry at 09:30 in a window that ends at 10:00 (the reviewer's probe P5).
SHORT = HEAD + '''class W(Strategy):
    id, name, root = "w", "W", "NQ"
    session_window = ("09:25", "10:00")

    def times(self):
        return ["09:30:00"]

    def on_time(self, ctx, et_time):
        ctx.market("long", sl=ctx.last_price - 10, ref=ctx.last_price)
'''

# An entry at 09:30, a flatten at 09:31 (the reviewer's probe "otherday").
IN_OUT = HEAD + '''class Fl(Strategy):
    id, name, root = "f", "Fl", "NQ"

    def times(self):
        return ["09:30:00", "09:31:00"]

    def on_time(self, ctx, et_time):
        if et_time == "09:30:00":
            ctx.market("long", sl=ctx.last_price - 10, ref=ctx.last_price)
        else:
            ctx.flatten("time")
'''

# Flat with nothing working, it flattens and enters in ONE event (a reversal's shape) at 09:30.
REVERSE = HEAD + '''class Rv(Strategy):
    id, name, root = "r", "Rv", "NQ"

    def times(self):
        return ["09:30:00"]

    def on_time(self, ctx, et_time):
        ctx.flatten("reverse")
        ctx.market("short", sl=ctx.last_price + 10, ref=ctx.last_price)
'''


# ---------------------------------------------------------------- a runner on a temp store, crashed and started again
@pytest.fixture
def kits(tmp_path):
    made = []

    def make(**kw):
        k = Kit(tmp_path, desk=kw.pop("stub", None) or StubDesk(), **kw)
        k.stub = k.r._desk
        k.r._nap = lambda s: None
        made.append(k)
        return k
    make.made = made
    yield make
    for k in made:
        try:
            k.r.close()
        finally:
            for p in k.spawned:
                if p.poll() is None:
                    p.kill()


def minute(k, start, px=21000.0, n=60):
    """`n` prints a second apart, then the stream's clock at the last one."""
    k.rows(start, [px] * n)
    h, m, s = (int(x) for x in start.split(":"))
    total = h * 3600 + m * 60 + s + n - 1
    k.clock(f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}")


def booked_at_nine(kits, source=ONE, **kw):
    """09:00: promoted, booked, the Desk's stream up, hosted before its window: a desk day, waiting."""
    k = kits(**kw)
    k.promote(source)
    store.put_desk("lab_x", sidecar(source), k.at)
    k.clock("09:00:00")
    k.open()
    k.rows("09:20:00", [21000.0] * 2)
    k.r.take(state(snap(source)))
    k.r.sync()
    return k


def crash(k):
    """The process is gone: children killed, nothing sent, nothing written."""
    for h in k.r._days.values():
        h.day.drop()
    k.r._days.clear()


def restart(kits, at_, backlog, *snaps, up=True):
    """A new runner on the same store: the session's backlog, live, the Desk's stream, the clock, the store read."""
    k = kits(live=False)
    k.r.sync()
    k.r.take(("connect",))
    k.open()
    for start, prices in backlog:
        k.rows(start, prices)
    k.r.take(("live",))
    if up:
        k.r.take(state(*snaps))
    k.clock(at_)
    k.r.sync()
    return k


def texts(day) -> list:
    return [(o["text"], o["refused"]) for o in day.summary()["orders"]]


@pytest.fixture
def days():
    made = []

    def make(*a, **kw):
        got = desk_day(*a, **kw)
        made.append(got[0])
        return got
    yield make
    for d in made:
        d.kill()


# ================================================================ C1: a shadow day never becomes a desk day
def test_a_day_that_ran_in_shadow_is_not_turned_into_a_desk_day_by_a_restart(kits):
    """The reviewer's probe. Booked at 09:00 (the desk day writes its tell-log's head), every account taken off before
    the window (shadow), the shadow day runs and fills on paper, the account is booked again at 09:30:30 (the page:
    "It starts with the next session."), the runner starts again at 09:30:40. It sent a real market entry at 09:31."""
    k = booked_at_nine(kits, EVERY)
    assert k.r.day("lab_x").mode == "desk"
    store.put_desk("lab_x", sidecar(EVERY, accounts=()), k.at)
    k.r.sync()
    assert k.r.day("lab_x").mode == "shadow"
    minute(k, "09:29:01")
    minute(k, "09:30:01", n=30)
    assert k.today()["state"] == "running" and len(k.today()["orders"]) == 1 and k.stub.bodies == []
    store.put_desk("lab_x", sidecar(EVERY), k.at)
    k.r.sync()
    assert k.r.day("lab_x").mode == "shadow"
    crash(k)
    k2 = restart(kits, "09:30:40", [("09:20:00", [21000.0] * 2), ("09:29:01", [21000.0] * 90)], snap(EVERY))
    day = k2.r.day("lab_x")
    assert day.mode == "shadow" and day.state == "running"
    minute(k2, "09:30:41", n=20)                                             # .. 09:31:00
    minute(k2, "09:31:01", n=5)
    assert k2.stub.bodies == []                                              # nothing: it is a shadow day
    s = k2.today()
    assert "mode" not in s and [o["refused"] for o in s["orders"]] == [None, "One position at a time."]
    k2.r.beat()
    assert k2.stub.said[-1]["strategies"][DESK_ID]["mode"] == "shadow"


def test_booked_the_evening_before_and_the_runner_down_across_the_open_is_shadow_today(kits):
    k = booked_at_nine(kits, EVERY)
    assert [t.get("head") for t in store.tells("lab_x", DATE, k.at)] == [1]  # a desk day that never began
    crash(k)
    k2 = restart(kits, "09:30:40", [("09:20:00", [21000.0] * 2), ("09:29:01", [21000.0] * 90)], snap(EVERY))
    day = k2.r.day("lab_x")
    assert day.mode == "shadow" and day.rebuilt is True
    minute(k2, "09:30:41", n=30)
    assert k2.stub.bodies == []


def test_a_tell_log_with_no_event_is_nothing_to_pick_up_for_a_day_made_after_its_window_began(days):
    head = [{"head": 1, "strategy": DESK_ID, "mark": mark_of(EVERY), "date": DATE}]
    day, stub, _, _, _ = days(EVERY, resume=list(head), now_ns=at("09:30:40"))
    day.on_ticks(ticks("09:29:50", [21000.0] * 50) + ticks("09:30:41", [21000.0] * 20))
    assert day.mode == "shadow" and stub.bodies == []
    early, stub2, _, tells, _ = days(EVERY, resume=list(head), now_ns=at("09:00:00"))     # before its window: a desk day
    assert early.mode == "desk" and tells == []                              # (the head is there already)


def test_a_real_desk_day_is_still_picked_up(kits):
    k = booked_at_nine(kits, EVERY)
    minute(k, "09:29:01")
    assert k.stub.ops() == [["entry"]] and k.today()["mode"] == "desk"
    crash(k)
    k2 = restart(kits, "09:30:40", [("09:20:00", [21000.0] * 2), ("09:29:01", [21000.0] * 90)],
                 snap(EVERY, answered=[2], **LIVE))
    day = k2.r.day("lab_x")
    assert day.mode == "desk" and day.state == "running" and k2.stub.bodies == []
    assert k2.today()["mode"] == "desk"


# ================================================================ I2: a tell-log with an event is a desk day, or none
@pytest.mark.parametrize("how", ["unreadable", "empty book", "limits gone", "the day file is a shadow day's"])
def test_a_desk_day_that_cannot_be_picked_up_is_ended_never_replaced_by_a_shadow_day(kits, how):
    """The reviewer's probe P2. The entry is out and filled at the Desk; the runner dies; at the restart the Desk's
    sidecar no longer books. A shadow child was hosted over the desk day's file and beat "shadow"."""
    k = booked_at_nine(kits)
    minute(k, "09:29:01")
    k.r.take(("desk", "strategy", snap(answered=[2], **LIVE)))
    minute(k, "09:30:01", px=21010.0)
    before = k.today()
    assert before["mode"] == "desk" and k.stub.ops() == [["entry"]]
    crash(k)
    if how == "unreadable":
        (k.at / "lab_x.desk.json").write_text("{not json")
    elif how == "empty book":
        store.put_desk("lab_x", sidecar(accounts=()), k.at)
    elif how == "limits gone":
        store.put_desk("lab_x", sidecar(limits=None), k.at)
    else:
        store.put_day("lab_x", {k_: v for k_, v in before.items() if k_ != "mode"}, k.at)
    k2 = restart(kits, "09:31:30", [("09:20:00", [21000.0] * 2), ("09:29:01", [21000.0] * 60), ("09:30:01", [21010.0] * 60)],
                 snap(answered=[2], **LIVE))
    for _ in range(3):
        k2.r.sync()
    assert k2.spawned == [] and k2.r.day("lab_x") is None                    # no child: not desk, and never shadow
    s = k2.file()
    assert (s["state"], s["why"]) == ("stopped", NO_RESUME)
    assert s["orders"] == before["orders"] and "rebuilt" not in s            # what the desk day wrote stays
    assert k2.stub.bodies == []
    k2.r.beat()
    assert DESK_ID not in k2.stub.said[-1]["strategies"]                     # no beat names it: the Desk's own
    assert [x["why"] for x in k2.journal() if x["kind"] == "stop"] == [NO_RESUME]     # "Runner down" rule acts


def test_a_runner_without_a_desk_line_still_hosts_in_shadow_whatever_the_tell_log_holds(kits, tmp_path):
    """Shadow only is Step A: it reads no tell-log. (Do not take --desk off mid-session.)"""
    k = booked_at_nine(kits)
    minute(k, "09:29:01")
    crash(k)
    plain_ = Kit(tmp_path, live=False)                                       # no desk line
    try:
        plain_.r.sync()
        plain_.r.take(("connect",))
        plain_.open()
        plain_.rows("09:29:01", [21000.0] * 60)
        plain_.r.take(("live",))
        plain_.clock("09:30:05")
        plain_.r.sync()
        assert plain_.r.day("lab_x").mode == "shadow"
    finally:
        plain_.r.close()


# ================================================================ I1: the runner's own stop and the Desk's echo of it
def not_ok(sentence="check it — its orders are not acknowledged yet"):
    def answer(body):
        return {"ok": True, "seq": body["seq"], "brain": None, "results": [
            {"op": it["op"], **({"id": it["id"]} if "id" in it else {}), "refused": None,
             "accounts": {ACCOUNT: {"ok": False, "actions": [sentence]}}} for it in body["intents"]]}
    return answer


def test_the_runners_own_stop_is_still_asked_again_after_the_desks_stream_repeats_it(days):
    """The reviewer's probe "echo". The strategy raises with a trade open; the stop (flatten) is answered "check it"
    for the account; the Desk's stream says `stopped` at once, because the stop itself set it."""
    src = planted(STOPS["raises"][0])
    stub = StubDesk("took", not_ok(), "took")
    day, stub, _, _, wall = days(src, stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    day.on_desk(snap(src, answered=[2], **LIVE))
    feed(day, "09:30:01", [21000.0] * 60)                                    # 09:31: it raises
    assert day.state == "stopped" and stub.ops() == [["entry"], ["stop"]] and day.pending()
    day.on_desk(snap(src, answered=[2, stub.bodies[-1]["seq"]], stopped="Strategy error: boom", **LIVE))     # the echo
    assert day.pending() and day.summary()["why"] == "Strategy error: boom"  # its own sentence stays
    wall.t += 1.1
    day.tend()
    assert stub.ops() == [["entry"], ["stop"], ["stop"]]                     # asked once more, a new event
    assert stub.bodies[2]["intents"] == [{"op": "stop", "why": "Strategy error: boom", "flatten": True}]
    assert stub.bodies[2]["seq"] == stub.bodies[1]["seq"] + 1 and not day.pending()


def test_a_stop_with_no_answer_keeps_being_asked_with_the_same_body_after_the_echo(days):
    stub = StubDesk()
    day, stub, _, _, wall = days(stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    stub.script = [StubDesk.NO_ANSWER, StubDesk.NO_ANSWER]
    day.off()                                                                # stop "off": no answer
    day.on_desk(snap(orders={1: WORKING}, answered=[2, 3], stopped="off"))   # ... yet it did get there
    for _ in range(3):
        wall.t += 1.0
        day.tend()
    assert stub.ops() == [["entry"], ["stop"], ["stop"], ["stop"]] and not day.pending()
    assert stub.bodies[1] == stub.bodies[2] == stub.bodies[3]                # the Desk answers it from its store


def test_after_its_own_stop_only_the_stop_is_still_asked_the_other_exits_are_dropped(days):
    stub = StubDesk()
    day, stub, _, _, wall = days(stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    stub.script = [StubDesk.NO_ANSWER] * 2
    feed(day, "09:30:01", [21000.0] * 180)                                   # 09:33: the cancel, no answer
    day.off()                                                                # the stop, no answer
    assert stub.ops() == [["entry"], ["cancel"], ["stop"]] and len(day._retry) == 2
    day.on_desk(snap(orders={1: CANCELLED}, answered=[2], stopped="off"))
    wall.t += 1.0
    day.tend()
    assert stub.ops()[3:] == [["stop"]] and not day.pending()


def test_a_shutdown_whose_stop_got_no_answer_reads_stopped_once_the_stream_says_so(days):
    stub = StubDesk()
    day, stub, _, _, wall = days(stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    stub.script = [StubDesk.NO_ANSWER]
    day.leave()
    assert day.state == "running"
    day.on_desk(snap(orders={1: WORKING}, answered=[2, 3], stopped="Stopped for today."))
    assert (day.state, day.summary()["why"]) == ("stopped", "Stopped for today.") and day.child_alive() is False


def test_the_desks_own_stop_still_ends_a_day_that_sent_none_and_nothing_goes_back(days):
    stub = StubDesk()
    day, stub, _, _, wall = days(stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    stub.script = [StubDesk.NO_ANSWER] * 3
    feed(day, "09:30:01", [21000.0] * 180)
    assert day.pending()
    day.on_desk(snap(orders={1: CANCELLED}, answered=[2], stopped="Both entries filled."))
    wall.t += 5.0
    day.tend()
    assert day.state == "stopped" and not day.pending() and stub.ops() == [["entry"], ["cancel"]]


def test_killed_ends_everything_also_a_stop_that_was_being_asked_again(days):
    stub = StubDesk()
    day, stub, _, _, wall = days(stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    stub.script = [StubDesk.NO_ANSWER] * 5
    day.off()
    day.on_desk(snap(orders={1: CANCELLED}, answered=[2], killed=True))
    wall.t += 2.0
    day.tend()
    assert not day.pending() and stub.ops() == [["entry"], ["stop"]]


# ================================================================ I3: the Desk is on another day
@pytest.mark.parametrize("src, rows", [(IN_OUT, 2), (EVERY, 3)])
def test_nothing_is_sent_for_a_day_while_the_desks_stream_says_another_date(days, src, rows):
    """The reviewer's probe "otherday": a replay on the tick stream, or a practice runner at the real Desk. The Desk
    applies an exit whatever date the event carries: the flatten and the stop would act on today's real trade."""
    other = {**snap(src), "date": "2026-10-12"}
    day, stub, side, _, wall = days(src, up=other)
    for start in ("09:29:50", "09:30:01", "09:31:01", "09:32:01", "09:33:01"):
        feed(day, start, [21000.0] * (11 if start == "09:29:50" else 60))
    for _ in range(15):
        wall.t += 1.0
        day.tend()
        day.blind(60.0)
    assert stub.bodies == []                                                 # no entry, no flatten, no stop, no cancel
    assert len(texts(day)) >= rows and all(r is not None for _, r in texts(day)[:1])
    if src is IN_OUT:
        assert day.state == "running" and day.summary()["why"] == OTHER_DAY
    else:                                                                    # three refused in a row: stopped, unsent
        assert day.state == "stopped" and stub.bodies == []
    day.leave()
    day.off()
    assert stub.bodies == []


def test_what_was_held_goes_when_the_desks_day_is_the_days_own_again(days):
    other = {**snap(IN_OUT), "date": "2024-03-04"}
    day, stub, side, _, wall = days(IN_OUT, up=other)
    feed(day, "09:29:50", [21000.0] * 11)
    feed(day, "09:30:01", [21000.0] * 60)                                    # the flatten: held
    assert stub.bodies == [] and day.pending()
    wall.t += 30.0
    day.tend()
    assert stub.bodies == []
    day.on_desk(snap(IN_OUT))                                                # midnight: the Desk's day is ours
    day.tend()
    assert stub.ops() == [["flatten"]] and not day.pending() and day.summary()["why"] is None


def test_the_desks_day_changing_mid_day_holds_everything_from_then_on(days):
    day, stub, side, _, wall = days(IN_OUT)
    feed(day, "09:29:50", [21000.0] * 11)
    assert stub.ops() == [["entry"]]
    day.on_desk({**snap(IN_OUT), "date": "2026-10-12"})                      # a replay took the Desk's place, or ours
    feed(day, "09:30:01", [21000.0] * 60)
    wall.t += 2.0
    day.tend()
    assert stub.ops() == [["entry"]] and day.summary()["why"] == OTHER_DAY
    side.down()                                                              # the stream is gone: its date is unknown,
    wall.t += 1.0                                                            # and an exit goes as it always did
    day.tend()
    assert stub.ops() == [["entry"], ["flatten"]]


def test_the_runner_tells_every_desk_day_which_day_the_desks_stream_is_on(kits):
    k = booked_at_nine(kits, IN_OUT)
    day = k.r.day("lab_x")
    minute(k, "09:29:01")
    assert k.stub.ops() == [["entry"]]
    k.r.take(("desk", "state", {"date": "2026-10-12", "armed": True, "strategies": {}}))     # it does not even list us
    minute(k, "09:30:01")
    k.wall[0] += 2.0
    k.r.idle()
    assert k.stub.ops() == [["entry"]] and day.desk.other_day is True
    assert k.today()["why"] == OTHER_DAY
    k.r.close()
    assert k.stub.ops() == [["entry"]]                                       # no stop for a day that is not the Desk's


def test_a_day_hosted_the_evening_before_does_not_say_the_desk_is_on_another_day(days):
    day, stub, _, _, _ = days(up={**snap(), "date": "2024-03-04"})
    day.on_ticks(ticks("09:20:00", [21000.0]))
    assert day.state == "waiting" and day.summary()["why"] is None


# ================================================================ I4 / (a): one flatten at the window's own end
def a_short_day(kits, fill=True):
    k = booked_at_nine(kits, SHORT)
    minute(k, "09:29:01")
    if fill:
        k.r.take(("desk", "strategy", snap(SHORT, answered=[2], **LIVE)))
    return k


def test_at_the_strategys_own_window_end_one_flatten_eod_is_sent(kits):
    """The reviewer's probe P5: the window ends at 10:00 with the trade open, the Desk's "Flat by" is 15:55."""
    k = a_short_day(kits)
    minute(k, "09:59:01", n=59)                                              # .. 09:59:59
    assert k.stub.ops() == [["entry"]]
    k.rows("10:00:00", [21000.0])                                            # a print at the end: the day is over
    day = k.r.day("lab_x")
    assert day.state == "done" and k.stub.ops() == [["entry"], ["flatten"]]
    assert k.stub.bodies[1]["intents"] == [{"op": "flatten", "reason": "eod"}]    # the tester's own word
    assert k.stub.bodies[1]["seq"] == 3 and k.stub.bodies[1]["t_ns"] == at("10:00:00")
    assert {"seq": 3, "own": "eod", "intents": [{"op": "flatten", "reason": "eod"}]} in store.tells("lab_x", DATE, k.at)
    k.clock("10:00:05")
    k.r.idle()
    assert len(k.stub.bodies) == 2                                           # one
    assert [o["text"] for o in k.today()["orders"]] == ["Buy at market, stop 20,990.00"]     # not the strategy's order


def test_the_flatten_goes_whatever_the_runners_own_view_of_the_brain_says(kits):
    k = a_short_day(kits, fill=False)                                        # its view: flat, the entry still working
    k.r.take(("desk_down",))                                                 # ... and the stream is down
    k.clock("10:00:03")                                                      # the clock ends the day (2 s of grace)
    assert k.r.day("lab_x").state == "done" and k.stub.ops() == [["entry"], ["flatten"]]


def test_the_eod_flatten_is_asked_again_like_any_exit(kits):
    k = a_short_day(kits)
    k.stub.script = [StubDesk.NO_ANSWER, StubDesk.NO_ANSWER]
    k.clock("10:00:03")
    assert k.stub.ops() == [["entry"], ["flatten"]]
    for _ in range(3):
        k.wall[0] += 1.0
        k.r.idle()
    assert k.stub.ops() == [["entry"]] + [["flatten"]] * 3 and k.stub.bodies[1] == k.stub.bodies[2] == k.stub.bodies[3]
    assert k.r.day("lab_x").pending() is False


@pytest.mark.parametrize("why", ["no entry was sent", "the Desk ended the day", "it was stopped", "every account taken off"])
def test_no_eod_flatten_when_there_is_nothing_of_the_day_at_the_desk_or_the_day_is_over(kits, why):
    if why == "no entry was sent":
        k = booked_at_nine(kits, SHORT)
        k.r.take(("desk_down",))
        minute(k, "09:29:01")                                                # the entry is refused here
        assert k.today()["orders"][0]["refused"] == "The Desk is not answering."
    else:
        k = a_short_day(kits)
    n = len(k.stub.bodies)
    if why == "the Desk ended the day":
        k.r.take(("desk", "strategy", snap(SHORT, answered=[2], stopped="off", **LIVE)))
    elif why == "it was stopped":
        store.set_enabled("lab_x", False, k.at)
        k.r.sync()
        n += 1                                                               # its own stop
    elif why == "every account taken off":
        store.put_desk("lab_x", sidecar(SHORT, accounts=()), k.at)
        k.r.sync()
    k.clock("10:00:03")
    k.r.idle()
    assert len(k.stub.bodies) == n and not any(it["op"] == "flatten" for b in k.stub.bodies for it in b["intents"])


def test_a_day_picked_up_after_a_crash_still_sends_its_eod_flatten(kits):
    k = a_short_day(kits)
    crash(k)
    k2 = restart(kits, "09:31:30", [("09:20:00", [21000.0] * 2), ("09:29:01", [21000.0] * 60), ("09:30:01", [21000.0] * 60)],
                 snap(SHORT, answered=[2], **LIVE))
    assert k2.r.day("lab_x").mode == "desk" and k2.stub.bodies == []
    k2.clock("10:00:03")
    assert k2.stub.ops() == [["flatten"]] and k2.stub.bodies[0]["seq"] == 3


def test_a_shadow_days_end_sends_nothing(kits):
    k = kits()
    k.promote(SHORT)
    k.clock("09:00:00")
    k.open()
    k.rows("09:20:00", [21000.0] * 2)
    k.r.take(state(snap(SHORT)))
    k.r.sync()
    minute(k, "09:29:01")
    minute(k, "09:30:01")
    k.clock("10:00:03")
    assert k.r.day("lab_x").state == "done"
    assert k.stub.bodies == [] and k.file()["trades"][0]["reason"] == "eod"


# ================================================================ M2: a mixed event from flat is not asked again
def test_the_exits_of_a_mixed_event_are_not_asked_again_when_the_day_was_flat_with_nothing_working(days):
    """The reviewer's RD1: [flatten, entry], applied, the answer lost; a second later the flatten went again and
    cancelled the entry just placed. From flat with nothing working that flatten had nothing to do."""
    stub = StubDesk(StubDesk.NO_ANSWER)
    day, stub, _, _, wall = days(REVERSE, stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    assert stub.ops() == [["flatten", "entry"]] and not day.pending()
    for _ in range(12):
        wall.t += 1.0
        day.tend()
    assert len(stub.bodies) == 1
    assert texts(day) == [("Flatten (reverse)", "The Desk did not answer."),
                          ("Sell at market, stop 21,010.00", "The Desk did not answer.")]


def test_with_something_open_the_exits_of_a_mixed_event_are_still_asked_again(days):
    stub = StubDesk("took", StubDesk.NO_ANSWER)
    day, stub, _, _, wall = days(REPLACE, stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    feed(day, "09:30:01", [21000.0] * 60)                                    # [cancel 1, entry 2] with order 1 working
    assert day.pending()
    wall.t += 1.0
    day.tend()
    assert stub.ops() == [["entry"], ["cancel", "entry"], ["cancel"]]


# ================================================================ M1: one wall-clock limit on a send
def test_one_send_never_holds_the_runner_longer_than_its_limit_however_the_answer_comes(tmp_path):
    gate = threading.Event()
    seen = []

    def handler(req):
        seen.append(req)
        gate.wait(5.0)                                                       # a Desk that answers in pieces, or never
        return httpx.Response(200, json={"ok": True, "seq": 1, "results": [], "brain": None})
    key = tmp_path / "lab.key"
    key.write_text("ab" * 32)
    c = DeskClient("http://127.0.0.1:8859", key, lambda item: None, transport=httpx.MockTransport(handler))
    t0 = time.monotonic()
    got = c.send({"seq": 1, "intents": []}, timeout=0.3)
    took = time.monotonic() - t0
    gate.set()
    assert got == {"ok": False, "left": True, "status": None, "detail": None} and took < 1.5
    assert len(seen) == 1                                                    # ... and it was one request, as ever
    assert c.send({"seq": 2, "intents": []}, timeout=2.0)["ok"] is True      # the line still works afterwards


# ================================================================ M3: promoted again mid-day
def test_promoted_again_mid_day_the_begun_desk_day_is_stopped_at_the_desk_before_it_is_let_go(kits):
    k = booked_at_nine(kits)
    minute(k, "09:29:01")
    old = k.r.day("lab_x")
    k.promote(ONE, promoted_utc="2026-10-10T13:00:00+00:00")                 # (the chart service's refusal raced)
    k.r.sync()
    assert k.stub.ops() == [["entry"], ["stop"]]
    assert k.stub.bodies[1]["intents"] == [{"op": "stop", "why": "Stopped for today.", "flatten": False}]
    assert k.stub.bodies[1]["mark"] == mark_of(ONE)                          # the promotion that sent the entry
    day = k.r.day("lab_x")
    assert day is not old and day.mode == "shadow" and old.child_alive() is False


def test_a_stop_at_a_re_promotion_that_got_no_answer_is_asked_again(kits):
    k = booked_at_nine(kits)
    minute(k, "09:29:01")
    k.stub.script = [StubDesk.NO_ANSWER]
    k.promote(ONE, promoted_utc="2026-10-10T13:00:00+00:00")
    k.r.sync()
    k.wall[0] += 1.0
    k.r.idle()
    assert k.stub.ops() == [["entry"], ["stop"], ["stop"]] and k.stub.bodies[1] == k.stub.bodies[2]


# ================================================================ M4: the heartbeat names every enabled strategy
def test_a_strategy_the_runner_does_not_host_is_still_named_in_the_heartbeat(kits):
    """The reviewer's probe P6: the Desk stopped it; after a restart nothing named it, and with a position open the
    Desk read "Runner down"."""
    k = booked_at_nine(kits)
    minute(k, "09:29:01")
    crash(k)
    k2 = restart(kits, "09:31:30", [("09:20:00", [21000.0] * 2), ("09:29:01", [21000.0] * 60)],
                 snap(answered=[2], stopped="off", **LIVE))
    assert k2.r.day("lab_x") is None and k2.file()["state"] == "stopped"
    k2.r.beat()
    assert k2.stub.said[-1]["strategies"] == {DESK_ID: {"state": "stopped", "why": "Stopped for today.", "mode": "desk"}}


def test_an_enabled_strategy_with_no_day_yet_is_named_too_and_one_switched_off_is_not(kits):
    k = kits()
    k.promote(ONE)                                                           # no account
    k.promote(MARKET_930, name="lab_y")
    store.put_desk("lab_y", sidecar(MARKET_930), k.at)                       # booked
    k.promote(MARKET_930, name="lab_z", enabled=False)
    k.clock("09:00:00")
    k.r.sync()                                                               # no print yet: nothing is hosted
    k.r.beat()
    assert k.r.hosting() == []
    assert k.stub.said[-1]["strategies"] == {DESK_ID: {"state": "waiting", "why": None, "mode": "shadow"},
                                             "lab_lab_y": {"state": "waiting", "why": None, "mode": "desk"}}


# ================================================================ M5: an event in the future is not on time either
def test_an_event_ahead_of_the_streams_clock_sends_no_entry(days):
    day, stub, _, _, _ = days()
    feed(day, "09:29:50", [21000.0] * 5)                                     # the newest print: 09:29:54
    day.end()                                                                # the session rolled: what is left runs
    assert stub.entries() == [] and texts(day)[0][1] == "Too late for this one."


# ================================================================ M6: the Desk's silence reaches the day file
def test_the_day_file_says_the_desk_is_not_answering_as_soon_as_it_is_and_no_longer_when_it_is_back(days):
    saved = []
    day, stub, side, _, wall = days(save=saved.append)
    feed(day, "09:29:50", [21000.0] * 11)
    assert saved[-1]["why"] is None
    n = len(saved)
    side.down()
    day.tend()                                                               # the runner's idle step: nothing else changed
    assert len(saved) == n + 1 and saved[-1]["why"] == "The Desk is not answering."
    day.tend()
    assert len(saved) == n + 1
    day.on_desk(snap(orders={1: WORKING}, answered=[2]))
    day.tend()
    assert saved[-1]["why"] is None


# ================================================================ M7: the same address with a default port
@pytest.mark.parametrize("charts, desk", [("http://127.0.0.1", "http://127.0.0.1:80"), ("http://localhost", "http://127.0.0.1:80")])
def test_the_chart_service_on_the_default_port_is_the_same_address_as_port_80(charts, desk, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(host, "run", lambda *a, **k: pytest.fail("the runner started"))
    assert cli.main(["--root", str(tmp_path), "--charts", charts, "--desk", desk]) == 2
    assert "chart service" in capsys.readouterr().err


# ================================================================ the reviewer's unpinned rules
def test_in_a_quiet_market_an_old_event_after_a_pick_up_is_too_late_by_the_clock_the_day_was_made_at(days):
    """L8. No print since, no clock yet: the stream's clock is at least the one the day was made at."""
    day, stub, _, tells, _ = days(EVERY)
    day.on_ticks(ticks("09:25:01", [21000.0]))                               # the session event, then the runner dies
    day.drop()
    late, stub2, _, _, _ = days(EVERY, resume=list(tells), now_ns=at("09:40:00"), up=snap(EVERY))
    late.on_ticks(ticks("09:25:01", [21000.0]) + ticks("09:30:00", [21000.0]))     # the tape so far: quiet since 09:30
    assert stub2.bodies == [] and texts(late) == [("Buy at market, stop 20,990.00", "Too late for this one.")]


def test_before_the_desks_first_snapshot_a_picked_up_child_is_told_the_logs_last_flat(kits):
    """B6."""
    k = booked_at_nine(kits)
    minute(k, "09:29:01")
    k.r.take(("desk", "strategy", snap(answered=[2], **LIVE)))
    minute(k, "09:30:01", px=21010.0)                                        # the 09:31 bar: told filled, not flat
    crash(k)
    k2 = restart(kits, "09:31:30", [("09:20:00", [21000.0] * 2), ("09:29:01", [21000.0] * 60), ("09:30:01", [21010.0] * 60)],
                 up=False)                                                   # the Desk is away
    day = k2.r.day("lab_x")
    assert day.mode == "desk" and day.desk.flat is False
    minute(k2, "09:31:01", px=21010.0)
    assert plots(day)["status filled"][-1] == [ms_of("09:32:00"), 0.0]       # still: not flat


def test_the_line_to_the_desk_never_follows_a_redirect_and_never_takes_a_proxy_from_the_environment(tmp_path, monkeypatch):
    """B7, B8. The key is in a header: a redirect would carry it to wherever the answer points, a proxy variable
    would route it through another machine."""
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(var, "http://10.9.9.9:3128")
    key = tmp_path / "lab.key"
    key.write_text("ab" * 32)
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(307, headers={"location": "http://10.0.0.5:9/steal"})
    c = DeskClient("http://127.0.0.1:8859", key, lambda item: None, transport=httpx.MockTransport(handler))
    got = c.send({"seq": 1, "intents": []})
    assert got["ok"] is False and got["status"] == 307 and len(seen) == 1 and seen[0].url.host == "127.0.0.1"
    stop = threading.Event()
    c2 = DeskClient("http://127.0.0.1:8859", key, lambda item: None, transport=httpx.MockTransport(handler),
                    sleep=lambda s: stop.set())
    c2.run(stop)
    assert len(seen) == 2 and seen[1].url.host == "127.0.0.1"                # the stream: not followed either
    real = DeskClient("http://127.0.0.1:8859", key, lambda item: None)       # the real transport, never used here
    assert real._http.trust_env is False and real._http.follow_redirects is False
    assert not {k_: v for k_, v in real._http._mounts.items() if v is not None}      # no proxy transport was mounted


def test_a_whole_state_that_does_not_list_the_strategy_makes_the_desk_silent_for_it(kits):
    """B11."""
    k = booked_at_nine(kits)
    day = k.r.day("lab_x")
    assert day.desk.silent() is False
    k.r.take(state())                                                        # every Lab strategy, whole: not us
    assert day.desk.silent() is True
    minute(k, "09:29:01")
    assert k.stub.bodies == [] and k.today()["orders"][0]["refused"] == "The Desk is not answering."


def test_an_entry_that_was_dead_before_the_crash_is_dead_again_after_the_pick_up(days):
    """B18. The Desk refused it; the runner died before the child's next event. Picked up with the Desk away, the
    child must still hear "cancelled"."""
    stub = StubDesk()
    stub.script = [stub.refuse("One position at a time.")]
    day, stub, _, tells, _ = days(stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    day.drop()
    late, stub2, _, new, _ = days(resume=list(tells), now_ns=at("09:30:30"), up=False, tells=list(tells))
    late.on_ticks(ticks("09:29:50", [21000.0] * 11) + ticks("09:30:01", [21000.0] * 60))
    assert list(plots(late)) == ["status cancelled"]
    assert [t for t in new if t.get("kind") == "bar"][0]["updates"] == [
        {"id": 1, "status": "cancelled", "fill_px": None, "fill_sl": None, "fill_tp": None, "fill_ms": None}]


def test_a_stop_the_desk_said_of_another_promotion_does_not_keep_todays_from_being_hosted(kits):
    """B20."""
    k = kits()
    k.promote(ONE)
    store.put_desk("lab_x", sidecar(), k.at)
    k.clock("09:00:00")
    k.open()
    k.rows("09:20:00", [21000.0] * 2)
    k.r.take(state({**snap(stopped="off"), "mark": ["x", "yesterday's promotion"]}))
    k.r.sync()
    assert k.r.day("lab_x") is not None and k.r.day("lab_x").mode == "desk" and len(k.spawned) == 1


# ================================================================ a resend is the first request, byte for byte
def test_a_request_sent_again_is_the_first_one_exactly_its_t_ns_too_however_far_the_clock_has_moved(days):
    stub = StubDesk()
    day, stub, _, tells, wall = days(stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    stub.script = [StubDesk.NO_ANSWER] * 3
    feed(day, "09:30:01", [21000.0] * 180)                                   # 09:33: the cancel, no answer
    first = json.dumps(stub.bodies[1], sort_keys=True)
    line = next(t for t in tells if t.get("kind") == "time" and t["arg"] == "09:33:00")
    assert stub.bodies[1]["t_ns"] == line["t_ns"] == at("09:33:00")          # the event's own time, as the log holds it
    for s in range(3):
        day.on_ticks(ticks(f"09:33:0{s + 1}", [21001.0]))                    # prints and the clock move on
        day.on_clock(ms_of(f"09:33:0{s + 2}"))
        wall.t += 1.0
        day.tend()
    assert len(stub.bodies) == 5 and not day.pending()
    assert [json.dumps(b, sort_keys=True) for b in stub.bodies[1:]] == [first] * 4

    own = StubDesk("took", StubDesk.NO_ANSWER, StubDesk.NO_ANSWER)           # the runner's own stop: the same rule
    d2, own, _, _, wall2 = days(stub=own)
    feed(d2, "09:29:50", [21000.0] * 11)
    d2.off()
    d2.on_clock(ms_of("09:45:00"))
    wall2.t += 1.0
    d2.tend()
    wall2.t += 1.0
    d2.tend()
    assert own.bodies[1] == own.bodies[2] == own.bodies[3] and own.bodies[1]["t_ns"] == at("09:30:00")


def test_a_pick_up_after_a_crash_sends_no_request_of_the_log_again(kits):
    """An exit that was still being asked when the runner died is not sent by the next one: it could only be another
    event under that number (another `t_ns`), which the Desk would apply as new."""
    k = booked_at_nine(kits, REPLACE)
    minute(k, "09:29:01")
    k.r.take(("desk", "strategy", snap(REPLACE, orders={1: WORKING}, answered=[2])))
    k.stub.script = [StubDesk.NO_ANSWER] * 5
    minute(k, "09:30:01")                                                    # 09:31: [cancel 1, entry 2], no answer
    minute(k, "09:31:01")                                                    # 09:32: the flatten, no answer
    old = {b["seq"] for b in k.stub.bodies}
    crash(k)
    k2 = restart(kits, "09:32:30", [("09:20:00", [21000.0] * 2), ("09:29:01", [21000.0] * 180)],
                 snap(REPLACE, orders={1: WORKING}, answered=[2]))
    day = k2.r.day("lab_x")
    assert day.mode == "desk" and day.state == "running"
    for _ in range(12):
        k2.wall[0] += 1.0
        k2.r.idle()
    minute(k2, "09:32:01", n=40)
    assert k2.stub.bodies == []                                              # nothing of the log, under any number
    k2.r.close()
    assert [b["seq"] for b in k2.stub.bodies] == [max(old) + 1]              # the clean stop: a new number
