"""The runner's desk side across a restart (Step B, task B4). A runner that starts again mid-day feeds a fresh child
the tell-log's own inputs and sends NOTHING while it does; the child must answer what it answered before and the Desk
must know exactly the events the log says it answered. Also here: the Desk's stream dropping and coming back
mid-trade, which needs no replay at all. Stub Desk, hand-fed prints, tmp_path stores."""
from __future__ import annotations

import copy

import pytest

from homebase.labrun import host, store
from tests.labrun_desk_util import (ACCOUNT, DATE, DESK_ID, EVERY, ONE, REPLACE, StubDesk, at, desk_day, feed, filled,
                                    mark_of, ms_of, plots, rnd, sidecar, snap, state, ticks)
from tests.test_labrun_host import Desk as Kit
from tests.test_labrun_host import HEAD

WORKING = {"status": "working"}
CANCELLED = {"status": "cancelled"}
NO_RESUME = "Could not pick up where it left off."
SESSION = ticks("09:29:50", [21000.0] * 11) + ticks("09:30:01", [21010.0] * 60)      # 09:29:50 .. 09:31:00
STOP_KEEP = [{"op": "stop", "why": NO_RESUME, "flatten": False}]


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


def texts(day) -> list:
    return [(o["text"], o["refused"]) for o in day.summary()["orders"]]


def before_the_crash(days, source=ONE, stub=None):
    """A day that sent its entry at 09:30, was told it filled, saw the 09:31 bar -- and then the runner was gone
    (no stop: a crash). -> the tell-log as the store would hold it, what it had sent, its order rows."""
    day, stub, side, tells, _ = days(source, stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    day.on_desk(snap(source, orders={1: filled()}, flat=False, answered=[2]))
    feed(day, "09:30:01", [21010.0] * 60)
    rows = texts(day)
    seen = copy.deepcopy(plots(day))
    day.drop()                                                               # the process is gone: nothing is sent
    return copy.deepcopy(tells), list(stub.bodies), rows, seen


def again(days, tells, source=ONE, *, up=None, rows=SESSION, at_="09:31:30", stub=None, **kw):
    """The runner starts again at `at_`: a fresh child, the session's prints so far fed at once (catch-up)."""
    day, stub, side, new, wall = days(source, stub=stub, up=up if up is not None else False, resume=list(tells),
                                      now_ns=at(at_), tells=list(tells), **kw)
    day.on_ticks(rows)
    day.on_clock(ms_of(at_))
    return day, stub, side, new, wall


# ---------------------------------------------------------------- the log, read back
def test_a_tell_log_is_picked_up_only_for_its_own_promotion(days):
    tells, _, _, _ = before_the_crash(days)
    got = host.read_tells(tells, mark_of(ONE))
    assert [e["line"]["seq"] for e in got["replay"]] == [1, 2, 3] and got["last"] == 3
    assert got["must"] == {2} and got["maybe"] == set() and got["never"] == {1, 3} and got["flat"] is False
    assert host.read_tells(tells, ["x", "promoted again"]) is None
    assert host.read_tells(tells[1:], mark_of(ONE)) is None                  # no head line: not a desk day's log
    assert host.read_tells([], mark_of(ONE)) is None and host.read_tells(None, mark_of(ONE)) is None
    assert host.read_tells(tells[:1], mark_of(ONE))["last"] == 0             # a day that never began


def test_what_the_log_says_of_each_event():
    mark = ["ab", "x"]
    lines = [{"head": 1, "mark": mark},
             {"seq": 1, "t_ns": 1, "kind": "session", "flat": True}, {"seq": 1, "intents": []},
             {"seq": 2, "t_ns": 2, "kind": "time", "flat": True}, {"seq": 2, "intents": [{"op": "entry", "id": 1}]},
             {"seq": 2, "sent": True, "ok": True, "results": []},
             {"seq": 3, "t_ns": 3, "kind": "time", "flat": True}, {"seq": 3, "intents": [{"op": "entry", "id": 2}]},
             {"seq": 3, "sent": False, "ok": False, "results": []},              # refused here: never left
             {"seq": 4, "t_ns": 4, "kind": "time", "flat": False}, {"seq": 4, "intents": [{"op": "cancel", "id": 1}]},
             {"seq": 4, "sent": True, "ok": False, "results": []},               # left, no answer
             {"seq": 4, "sent": True, "ok": True, "results": []},                # ... asked again, and taken
             {"seq": 5, "t_ns": 5, "kind": "time", "flat": False}, {"seq": 5, "intents": [{"op": "flatten", "reason": "x"}]},
             {"seq": 5, "sent": True, "ok": False, "results": []},               # left, no answer, never taken
             {"seq": 6, "own": "blind", "intents": [{"op": "cancel", "id": 1}]},
             {"seq": 6, "sent": True, "ok": True, "results": []},
             {"seq": 7, "t_ns": 7, "kind": "bar", "flat": True},                 # the child was never heard
             {"seq": 8, "t_ns": 7, "kind": "bar", "flat": True}, {"seq": 8, "intents": [{"op": "flatten", "reason": "y"}]},
             "not a line", {"seq": "x"}, {"seq": 0, "kind": "time"}]
    got = host.read_tells([x for x in lines if isinstance(x, dict)], mark)
    assert [e["line"]["seq"] for e in got["replay"]] == [1, 2, 3, 4, 5, 8]   # the child's events, never the runner's own
    assert got["last"] == 8 and got["must"] == {2, 4, 6} and got["maybe"] == {8} and got["never"] == {1, 3, 7}
    assert got["flat"] is True


# ---------------------------------------------------------------- picked up
def test_a_runner_that_starts_again_feeds_the_log_back_sends_nothing_and_goes_on_from_the_desks_word(days):
    tells, sent, rows, seen = before_the_crash(days)
    day, stub, side, new, _ = again(days, tells)
    assert day.mode == "desk" and day.state == "running" and day.rebuilt is True
    assert stub.bodies == [] and new == tells                                # nothing sent, nothing written again
    assert texts(day) == rows and plots(day) == seen                         # the same day so far, as the child saw it
    day.on_desk(snap(orders={1: filled()}, flat=True, answered=[2], rounds=[rnd()]))      # the trade ended meanwhile
    feed(day, "09:31:01", [21012.0] * 60)
    assert plots(day)["status filled"][-1] == [ms_of("09:32:00"), 1.0]       # the child: filled, and flat again
    assert new[-2]["seq"] == 4 and new[-2]["flat"] is True and new[-2]["updates"] == []   # (it knew it was filled)
    assert stub.bodies == [] and len(day.summary()["trades"]) == 1


def test_the_next_event_after_a_resume_has_the_logs_last_number_plus_one(days):
    tells, _, _, _ = before_the_crash(days)
    day, stub, side, new, _ = again(days, tells, up=snap(orders={1: WORKING}, flat=True, answered=[2]))
    feed(day, "09:31:01", [21012.0] * 120)                                   # 09:33: the cancel
    assert stub.ops() == [["cancel"]] and stub.bodies[0]["seq"] == 6         # 4 and 5 were the bars
    assert day.state == "running"


def test_events_between_the_logs_end_and_now_refuse_their_entries_and_still_send_their_exits(days):
    day, stub, side, tells, _ = days(REPLACE)
    feed(day, "09:29:50", [21000.0] * 11)
    day.on_desk(snap(REPLACE, orders={1: WORKING}, answered=[2]))
    day.drop()                                                               # gone at 09:30
    rows = ticks("09:29:50", [21000.0] * 11) + ticks("09:30:01", [21000.0] * 200)
    late, stub2, _, new, _ = again(days, tells, REPLACE, rows=rows, at_="09:33:25",
                                   up=snap(REPLACE, orders={1: WORKING}, answered=[2]))
    assert stub2.ops() == [["cancel"], ["flatten"]]                          # 09:31's cancel and 09:32's flatten went
    assert [b["seq"] for b in stub2.bodies] == [3, 4]
    assert texts(late)[1:] == [("Cancel", None), ("Buy stop 21,006.00, stop 20,996.00", "Too late for this one."),
                               ("Flatten (time)", None)]
    assert len(stub2.entries()) == 0 and late.state == "running"


# ---------------------------------------------------------------- not picked up
def test_a_child_that_answers_something_else_this_time_is_stopped_and_keeps_the_position(days):
    tells, _, _, _ = before_the_crash(days)
    bent = copy.deepcopy(tells)
    line = next(t for t in bent if t.get("seq") == 2 and "intents" in t)
    line["intents"][0]["price"] = 21004.75                                   # the log holds another order
    day, stub, side, new, _ = again(days, bent, up=snap(orders={1: filled()}, flat=False, answered=[2]))
    assert (day.state, day.summary()["why"]) == ("stopped", NO_RESUME) and day.child_alive() is False
    assert stub.ops() == [["stop"]] and stub.bodies[0]["intents"] == STOP_KEEP
    assert stub.bodies[0]["seq"] == 4 and stub.entries() == []               # above the log's last (3)
    assert "event 2" in day.detail


def test_a_schedule_that_does_not_reach_the_logs_event_is_not_picked_up(days):
    tells, _, _, _ = before_the_crash(days)
    bent = copy.deepcopy(tells)
    next(t for t in bent if t.get("kind") == "bar")["t_ns"] += 60 * 10 ** 9  # the log's bar closed a minute later
    day, stub, _, _, _ = again(days, bent, up=snap(orders={1: filled()}, flat=False, answered=[2]))
    assert (day.state, day.summary()["why"]) == ("stopped", NO_RESUME) and stub.bodies[0]["intents"] == STOP_KEEP


def test_an_event_the_days_schedule_no_longer_has_is_not_picked_up_even_when_the_child_would_answer_the_same(days):
    tells, _, _, _ = before_the_crash(days)
    bent = copy.deepcopy(tells)
    next(t for t in bent if t.get("kind") == "session")["t_ns"] -= 10 ** 9   # the log's session began a second early
    day, stub, _, _, _ = again(days, bent, up=snap(orders={1: filled()}, flat=False, answered=[2]))
    assert (day.state, day.summary()["why"]) == ("stopped", NO_RESUME) and "event 1" in day.detail
    assert stub.ops() == [["stop"]]


def test_what_this_runner_sent_before_the_desks_first_snapshot_is_not_held_against_the_log(days):
    """A day that began with the Desk away: its flatten went out (exits always go) and was answered. The Desk's first
    snapshot then lists that event -- this process's own, not one the log never sent."""
    day, stub, side, _, _ = days(REPLACE, up=False)
    feed(day, "09:29:50", [21000.0] * 11)                                    # 09:30: the entry is refused here
    feed(day, "09:30:01", [21000.0] * 60)                                    # 09:31: another, refused here
    feed(day, "09:31:01", [21000.0] * 60)                                    # 09:32: the flatten goes
    assert stub.ops() == [["flatten"]] and stub.bodies[0]["seq"] == 4
    day.on_desk(snap(REPLACE, answered=[4]))
    assert day.state == "running" and stub.ops() == [["flatten"]]
    other, stub2, _, _, _ = days(REPLACE, up=False)
    feed(other, "09:29:50", [21000.0] * 11)
    other.on_desk(snap(REPLACE, answered=[4]))                               # ... while one it never sent IS held against it
    assert other.state == "stopped" and other.summary()["why"] == NO_RESUME


def test_a_strategy_that_breaks_while_it_is_fed_the_log_is_not_picked_up_and_never_flattens(days):
    """In the replay nothing is the strategy's own doing yet: a fresh child that raises there keeps the position."""
    src = HEAD + '''import os


class Twice(Strategy):
    id, name, root = "t", "Twice", "NQ"

    def times(self):
        return ["09:30:00", "09:30:30"]

    def on_time(self, ctx, et_time):
        if et_time == "09:30:00":
            ctx.market("long", sl=ctx.last_price - 10, ref=ctx.last_price)
        elif os.path.exists(%r):
            raise RuntimeError("boom")
'''
    import tempfile
    flag = tempfile.mktemp(prefix="hb-b4-flag-")
    src = src % flag
    try:
        day, stub, _, tells, _ = days(src)
        feed(day, "09:29:50", [21000.0] * 11)
        feed(day, "09:30:01", [21000.0] * 40)
        assert day.state == "running" and stub.ops() == [["entry"]]
        day.drop()
        open(flag, "w").close()                                              # this time it raises at 09:30:30
        late, stub2, _, _, _ = again(days, tells, src, up=snap(src, orders={1: filled()}, flat=False, answered=[2]),
                                     rows=ticks("09:29:50", [21000.0] * 11) + ticks("09:30:01", [21000.0] * 40))
        assert (late.state, late.summary()["why"]) == ("stopped", NO_RESUME)
        assert stub2.bodies[0]["intents"] == STOP_KEEP and "boom" in late.detail
    finally:
        import os
        if os.path.exists(flag):
            os.unlink(flag)


def test_a_seq_the_desk_does_not_know_is_not_picked_up(days):
    tells, _, _, _ = before_the_crash(days)
    day, stub, _, _, _ = again(days, tells, up=snap(answered=[]))            # the log: event 2 was answered
    assert (day.state, day.summary()["why"]) == ("stopped", NO_RESUME) and stub.bodies[0]["intents"] == STOP_KEEP
    assert "event 2" in day.detail and stub.entries() == []


def test_a_log_that_is_behind_the_desk_is_not_picked_up_and_the_stop_goes_above_every_number_the_desk_knows(days):
    tells, _, _, _ = before_the_crash(days)                                  # the log ends at event 3
    day, stub, _, new, _ = again(days, tells, up=snap(orders={1: filled()}, flat=False, answered=[2, 5, 7]))
    assert (day.state, day.summary()["why"]) == ("stopped", NO_RESUME)
    assert stub.ops() == [["stop"]] and stub.bodies[0]["seq"] == 8           # never a number the Desk has answered
    assert stub.bodies[0]["intents"] == STOP_KEEP and "event 5" in day.detail
    assert {"seq": 8, "own": "stop", "t_ns": stub.bodies[0]["t_ns"], "intents": STOP_KEEP} in new


def test_an_event_the_desk_answered_that_the_log_never_sent_is_not_picked_up(days):
    tells, _, _, _ = before_the_crash(days)
    day, stub, _, _, _ = again(days, tells, up=snap(orders={1: filled()}, flat=False, answered=[1, 2]))    # 1: a bar-less session event
    assert (day.state, day.summary()["why"]) == ("stopped", NO_RESUME) and "event 1" in day.detail


@pytest.mark.parametrize("answered, state_", [([2], "running"), ([], "stopped")])
def test_an_event_cut_off_before_its_answer_was_written_is_picked_up_only_if_the_desk_has_it(days, answered, state_):
    tells, _, _, _ = before_the_crash(days)
    cut = [t for t in tells if not (t.get("seq") == 2 and "results" in t)]   # gone between the request and the note
    day, stub, _, _, _ = again(days, cut, up=snap(orders={1: filled()} if answered else {}, flat=not answered,
                                                  answered=answered))
    assert day.state == state_
    if answered:
        assert stub.bodies == [] and texts(day)[0][1] == "The Desk did not answer."     # (this runner has no answer)
        assert plots(day)["status filled"]                                   # ... but the Desk says what happened
    else:
        assert day.summary()["why"] == NO_RESUME and stub.bodies[0]["intents"] == STOP_KEEP


def test_a_fresh_day_that_finds_events_already_answered_at_the_desk_does_not_trade_on_top_of_them(days):
    """No tell-log, yet the Desk has answered events of this promotion today: the numbers would collide."""
    day, stub, side, _, _ = days(up=False)
    day.on_ticks(ticks("09:20:00", [21000.0]))
    day.on_desk(snap(answered=[1, 2, 3]))
    assert (day.state, day.summary()["why"]) == ("stopped", NO_RESUME)
    assert stub.bodies == []                                                 # it never began: nothing of it is there


def test_a_child_that_cannot_start_again_still_tells_the_desk_and_keeps_the_position(days):
    def no_sandbox(argv, run_dir):
        raise host.sandbox.SandboxUnavailable("no sandbox here")
    tells, _, _, _ = before_the_crash(days)
    day, stub, _, _, _ = days(ONE, up=snap(orders={1: filled()}, flat=False, answered=[2]), resume=list(tells),
                              now_ns=at("09:31:30"), spawn=no_sandbox)
    assert (day.state, day.summary()["why"]) == ("stopped", "The sandbox is not working.")
    assert stub.bodies[0]["intents"] == [{"op": "stop", "why": "The sandbox is not working.", "flatten": False}]
    assert stub.bodies[0]["seq"] == 4


def test_the_desk_stopped_it_meanwhile_the_day_is_over_and_nothing_is_sent(days):
    tells, _, _, _ = before_the_crash(days)
    day, stub, _, _, _ = again(days, tells, up=snap(orders={1: filled()}, answered=[2, 9], stopped="off"))
    assert (day.state, day.summary()["why"]) == ("stopped", "Stopped for today.") and stub.bodies == []


# ---------------------------------------------------------------- the Desk is down when the runner starts again
def test_with_the_desk_down_at_the_resume_nothing_is_sent_until_its_first_snapshot_agrees_with_the_log(days):
    day, stub, side, tells, _ = days(REPLACE)
    feed(day, "09:29:50", [21000.0] * 11)
    day.on_desk(snap(REPLACE, orders={1: WORKING}, answered=[2]))
    day.drop()
    rows = ticks("09:29:50", [21000.0] * 11) + ticks("09:30:01", [21000.0] * 60)
    late, stub2, side2, new, wall = again(days, tells, REPLACE, rows=rows, at_="09:31:00", up=False)
    assert late.state == "running" and late.mode == "desk"
    assert stub2.bodies == []                                                # 09:31: cancel 1 + entry 2 -- nothing left
    assert texts(late)[1:] == [("Cancel", "The Desk did not answer."),
                               ("Buy stop 21,006.00, stop 20,996.00", "The Desk is not answering.")]
    assert late.summary()["why"] == "The Desk is not answering."
    for _ in range(20):                                                      # however long the Desk stays away
        wall.t += 1.0
        late.tend()
    assert stub2.bodies == [] and late.pending()
    late.on_desk(snap(REPLACE, orders={1: WORKING}, answered=[2]))           # it is back, and it agrees with the log
    late.tend()
    assert stub2.ops() == [["cancel"]] and stub2.bodies[0]["seq"] == 3 and not late.pending()
    assert texts(late)[1] == ("Cancel", None) and stub2.entries() == []


def test_with_the_desk_down_at_the_resume_and_a_log_it_does_not_agree_with_only_the_stop_goes(days):
    day, stub, side, tells, _ = days(REPLACE)
    feed(day, "09:29:50", [21000.0] * 11)
    day.drop()
    rows = ticks("09:29:50", [21000.0] * 11) + ticks("09:30:01", [21000.0] * 60)
    late, stub2, _, _, wall = again(days, tells, REPLACE, rows=rows, at_="09:31:00", up=False)
    assert stub2.bodies == [] and late.pending()                             # the 09:31 cancel waits
    late.on_desk(snap(REPLACE, answered=[2, 3, 4]))                          # the Desk is ahead of the log
    wall.t += 2.0
    late.tend()
    assert late.state == "stopped" and late.summary()["why"] == NO_RESUME
    assert stub2.ops() == [["stop"]] and stub2.bodies[0]["seq"] == 5         # the held cancel (number 3) never went


# ---------------------------------------------------------------- the stream drops and comes back mid-trade
def test_a_stream_that_drops_and_comes_back_mid_trade_needs_nothing_replayed(days):
    day, stub, side, tells, _ = days(EVERY)
    feed(day, "09:29:50", [21000.0] * 11)                                    # 09:30: in
    day.on_desk(snap(EVERY, orders={1: filled(px=21000.25)}, flat=False, answered=[2]))
    side.down()                                                              # the Desk restarts
    feed(day, "09:30:01", [21000.0] * 60)                                    # 09:31: an entry -- refused here
    assert texts(day)[-1][1] == "The Desk is not answering." and stub.ops() == [["entry"]]
    assert tells[-3]["flat"] is False and tells[-3]["updates"] == [{"id": 1, **filled(px=21000.25)}]
    side.heard()                                                             # the stream is open again ...
    assert side.silent() is True                                             # ... but has not said anything of us yet
    day.on_desk(snap(EVERY, orders={1: filled(px=21000.25), 2: CANCELLED}, flat=True, answered=[2],
                     rounds=[rnd(entry=21000.25, exit_=20990.25, reason="sl", pnl=-200.0)]))     # stopped out meanwhile
    feed(day, "09:31:01", [21000.0] * 60)                                    # 09:32: flat again, a new entry goes
    assert stub.ops() == [["entry"], ["entry"]] and tells[-3]["flat"] is True
    assert day.summary()["trades"][0]["reason"] == "sl" and day.state == "running"
    assert len({b["seq"] for b in stub.bodies}) == 2


def test_cancels_and_flattens_made_while_the_desk_is_away_are_asked_again_for_ten_seconds(days):
    stub = StubDesk()
    day, stub, side, _, wall = days(REPLACE, stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    stub.script = [StubDesk.NO_ANSWER] * 4
    side.down()
    feed(day, "09:30:01", [21000.0] * 60)                                    # 09:31: the cancel (the entry stays here)
    for _ in range(4):
        wall.t += 1.0
        day.tend()
    assert stub.ops() == [["entry"]] + [["cancel"]] * 5 and not day.pending()
    assert len({b["seq"] for b in stub.bodies[1:]}) == 1 and stub.bodies[1] == stub.bodies[5]


# ---------------------------------------------------------------- the runner itself, started again
def booked_kit(tmp_path, **kw):
    k = Kit(tmp_path, desk=StubDesk(), **kw)
    k.stub = k.r._desk
    k.r._nap = lambda s: None
    return k


def first_runner(tmp_path):
    k = booked_kit(tmp_path)
    k.promote(ONE)
    store.put_desk("lab_x", sidecar(), k.at)
    k.clock("09:00:00")
    k.open()
    k.rows("09:20:00", [21000.0] * 2)
    k.r.take(state(snap()))
    k.r.sync()
    k.rows("09:29:01", [21000.0] * 60)
    k.clock("09:30:00")
    assert k.stub.ops() == [["entry"]] and k.r.day("lab_x").mode == "desk"
    return k


def second_runner(tmp_path, *snaps, at_="09:31:30"):
    k = booked_kit(tmp_path, live=False)
    k.r.sync()
    k.r.take(state(*snaps)) if snaps else None
    k.r.take(("connect",))
    k.open()
    k.rows("09:20:00", [21000.0] * 2)
    k.rows("09:29:01", [21000.0] * 60)
    k.rows("09:30:01", [21010.0] * 60)
    k.r.take(("live",))
    k.clock(at_)
    k.r.sync()
    return k


def test_a_runner_that_crashed_picks_its_desk_day_up_from_the_store(tmp_path):
    k = first_runner(tmp_path)
    k.r.day("lab_x").drop()                                                  # a crash: no stop, nothing written
    k.r._days.clear()
    k2 = second_runner(tmp_path, snap(orders={1: filled()}, flat=False, answered=[2]))
    try:
        day = k2.r.day("lab_x")
        assert day.mode == "desk" and day.state == "running" and day.rebuilt is True and k2.stub.bodies == []
        assert [o["text"] for o in k2.today()["orders"]] == ["Buy stop 21,005.00, stop 20,995.00, target 2 x the stop"]
        assert k2.journal()[1:] == []                                        # (the first runner wrote the order's line)
        k2.rows("09:31:01", [21012.0] * 120)
        k2.clock("09:33:00")
        assert k2.stub.bodies == [] and plots(day)["status filled"]          # filled: no cancel at 09:33
    finally:
        k2.r.close()
    assert k2.stub.ops() == [["stop"]]                                       # ... and a clean stop at the end


def test_after_a_clean_shutdown_the_day_is_over_and_is_not_picked_up(tmp_path):
    k = first_runner(tmp_path)
    k.r.close()
    assert k.file()["state"] == "stopped"
    k2 = second_runner(tmp_path, snap(orders={1: CANCELLED}, answered=[2, 3], stopped="Stopped for today."))
    try:
        assert k2.spawned == [] and k2.r.day("lab_x") is None and k2.stub.bodies == []
    finally:
        k2.r.close()


def test_a_shutdown_the_desk_never_heard_of_is_picked_up_like_a_crash(tmp_path):
    k = first_runner(tmp_path)
    k.stub.script = [StubDesk.NO_ANSWER] * 99
    k.r.close()                                                              # the stop never got through
    assert k.file()["state"] == "running"
    k2 = second_runner(tmp_path, snap(orders={1: WORKING}, answered=[2]))
    try:
        assert k2.r.day("lab_x").mode == "desk" and k2.r.day("lab_x").state == "running"
        k2.rows("09:31:01", [21012.0] * 120)
        k2.clock("09:33:00")
        assert k2.stub.ops() == [["cancel"]]
        assert k2.stub.bodies[0]["seq"] > max(b["seq"] for b in k.stub.bodies)     # above the stop that was tried
    finally:
        k2.r.close()


def test_a_day_with_no_tell_log_made_after_its_window_began_is_shadow_whatever_the_book_says(tmp_path):
    k2 = booked_kit(tmp_path, live=False)
    k2.promote(ONE)
    store.put_desk("lab_x", sidecar(), k2.at)
    k2.r.sync()
    k2.r.take(state(snap()))
    k2.r.take(("connect",))
    k2.open()
    k2.rows("09:29:01", [21000.0] * 60)
    k2.r.take(("live",))
    k2.clock("09:31:30")
    k2.r.sync()
    try:
        assert k2.r.day("lab_x").mode == "shadow" and k2.stub.bodies == []
    finally:
        k2.r.close()
    assert k2.stub.bodies == []


def test_a_tell_log_of_another_promotion_is_not_picked_up(tmp_path):
    k = first_runner(tmp_path)
    k.r.day("lab_x").drop()
    k.r._days.clear()
    newer = ONE + "# promoted again\n"
    k2 = booked_kit(tmp_path, live=False)
    k2.promote(newer)
    store.put_desk("lab_x", sidecar(newer), k2.at)
    k2.r.sync()
    k2.r.take(state(snap(newer)))
    k2.r.take(("connect",))
    k2.open()
    k2.rows("09:29:01", [21000.0] * 60)
    k2.r.take(("live",))
    k2.clock("09:31:30")
    k2.r.sync()
    try:
        assert k2.r.day("lab_x").mode == "shadow" and k2.stub.bodies == []
    finally:
        k2.r.close()


def test_a_strategy_that_no_longer_loads_when_the_runner_starts_again_keeps_the_position(days, tmp_path):
    """Its own error sentence ("Strategy error: ...") would flatten in a live event. Here the day is only being
    picked up: the trade keeps its stop."""
    flag = tmp_path / "now-it-breaks"
    src = HEAD + f'''import os

if os.path.exists({str(flag)!r}):
    raise RuntimeError("boom at load")


class L(Strategy):
    id, name, root = "l", "L", "NQ"

    def times(self):
        return ["09:30:00"]

    def on_time(self, ctx, et_time):
        ctx.market("long", sl=ctx.last_price - 10, ref=ctx.last_price)
'''
    day, stub, _, tells, _ = days(src)
    feed(day, "09:29:50", [21000.0] * 11)
    assert stub.ops() == [["entry"]]
    day.drop()
    flag.write_text("x")
    late, stub2, _, _, _ = days(src, up=snap(src, orders={1: filled()}, flat=False, answered=[2]), resume=list(tells),
                                now_ns=at("09:31:30"))
    assert late.state == "stopped" and late.summary()["why"] == "Strategy error: boom at load"
    assert stub2.bodies[0]["intents"] == [{"op": "stop", "why": "Strategy error: boom at load", "flatten": False}]
    assert stub2.bodies[0]["seq"] == 3
