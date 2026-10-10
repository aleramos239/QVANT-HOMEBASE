"""Step B, final fix wave B (the runner's side of final-review-b.md). Scenario tests on a Runner with a stub Desk
(tests/test_labrun_fix1.py's kit), crashed and started again where the finding needs it; tmp_path stores, no socket,
no service.

    R1   after a restart the heartbeat names a final desk day only when the Desk's own snapshot says it ended it; a
         stop the Desk never took is sent once more, the same request
    R3   a begun desk day whose book stops reading mid-day is ended at the Desk with a stop
    R2   a picked-up event the Desk answered is never counted as a refused one
    I1   in desk mode the day ends at the Desk's flat time when that comes before the window's end
    G2   the install script installs the runner job
    B4   an owed stop is asked once more when the Desk answers a heartbeat"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from homebase.labrun import host, store
from tests.labrun_desk_util import DATE, DESK_ID, ONE, StubDesk, at, feed, sidecar, snap, state  # noqa: F401
from tests.test_labrun_fix1 import (LIVE, NO_RESUME, SHORT, a_short_day, booked_at_nine, crash, days, kits, minute,  # noqa: F401
                                    restart)
from tests.test_labrun_host import HEAD

REPO = Path(__file__).resolve().parents[1]
WORKING = {"status": "working"}

# A stop entry at 09:30; at 09:31 it raises (the reviewer's probe p1_owed_stop_restart.py).
RAISES = HEAD + '''class R(Strategy):
    id, name, root = "r", "R", "NQ"

    def times(self):
        return ["09:30:00", "09:31:00"]

    def on_time(self, ctx, et_time):
        if et_time == "09:30:00":
            ctx.stop_entry("long", ctx.last_price + 50, sl=ctx.last_price - 5, tp_rr=2.0)
        else:
            raise RuntimeError("boom")
'''

# A market entry at 09:30, held: the window is the default one (09:25-16:00).
HOLD = HEAD + '''class H(Strategy):
    id, name, root = "h", "H", "NQ"

    def times(self):
        return ["09:30:00"]

    def on_time(self, ctx, et_time):
        ctx.market("long", sl=ctx.last_price - 10, ref=ctx.last_price)
'''

BACKLOG = [("09:20:00", [21000.0] * 2), ("09:29:01", [21000.0] * 60), ("09:30:01", [21000.0] * 60),
           ("09:31:01", [21000.0] * 2)]


def named(k) -> dict:
    k.r.beat()
    return k.stub.said[-1]["strategies"]


# ================================================================ R1: the owed stop and a runner restart
def a_stop_owed_at_the_crash(kits):
    """Its stop entry is working at the Desk; the Desk goes down; at 09:31 the strategy raises, and its stop (flatten)
    gets no answer for its ten seconds: owed. Then the runner is killed."""
    k = kits()
    k.promote(RAISES)
    store.put_desk("lab_x", sidecar(RAISES), k.at)
    k.clock("09:00:00")
    k.open()
    k.rows("09:20:00", [21000.0] * 2)
    k.r.take(state(snap(RAISES)))
    k.r.sync()
    assert k.r.day("lab_x").mode == "desk"
    k.stub.script = ["took"] + [StubDesk.NO_ANSWER] * 40
    minute(k, "09:29:01")
    minute(k, "09:30:01", n=30)                                              # the entry leaves (seq 2)
    k.r.take(("desk_down",))
    minute(k, "09:30:31", n=32)                                              # 09:31: it raises -> the stop
    for _ in range(12):
        k.wall[0] += 1.0
        k.r.idle()
    day = k.r.day("lab_x")
    assert day.owes_stop() and k.file()["state"] == "stopped" and k.stub.ops() == [["entry"]] + [["stop"]] * 11
    stop = k.stub.bodies[1]
    assert stop["intents"] == [{"op": "stop", "why": "Strategy error: boom", "flatten": True}]
    crash(k)
    return stop


def test_after_a_restart_an_owed_stop_is_sent_once_more_and_the_beat_does_not_name_the_day(kits):
    """The reviewer's probe P1 (R1): the next runner named the day "stopped", which switched off the Desk's own rule
    (no beat for 20 s: unfilled entries cancelled), and nothing ever sent the stop again."""
    stop = a_stop_owed_at_the_crash(kits)
    k2 = restart(kits, "09:32:00", BACKLOG, snap(RAISES, orders={1: WORKING}, answered=[2]))
    assert k2.r.hosting() == [] and k2.stub.bodies == []
    assert DESK_ID not in named(k2)                                          # the Desk's 20 s rule stays on
    assert k2.stub.bodies == [stop]                                          # the very request: seq, intents, t_ns
    for _ in range(3):
        k2.wall[0] += 5.0
        k2.r.idle()
        k2.r.sync()
        assert DESK_ID not in named(k2)
    assert len(k2.stub.bodies) == 1                                          # once
    # the Desk took it: its stream says the day is stopped; from then on the beat names it again
    k2.r.take(("desk", "strategy", snap(RAISES, answered=[2, stop["seq"]], stopped="Strategy error: boom")))
    assert named(k2)[DESK_ID] == {"state": "stopped", "why": "Strategy error: boom", "mode": "desk"}
    assert len(k2.stub.bodies) == 1
    assert [t["ok"] for t in store.tells("lab_x", DATE, k2.at) if t.get("seq") == stop["seq"] and "ok" in t][-1] is True


def test_an_owed_stop_waits_for_the_desks_snapshot_of_that_day(kits):
    stop = a_stop_owed_at_the_crash(kits)
    k2 = restart(kits, "09:32:00", BACKLOG, up=False)                        # the Desk's stream is not up
    assert DESK_ID not in named(k2) and k2.stub.bodies == []
    k2.r.take(state(date="2024-03-06"))                                      # the Desk is on another day
    assert DESK_ID not in named(k2) and k2.stub.bodies == []
    k2.r.take(state(snap(RAISES, orders={1: WORKING}, answered=[2], mark=["other", "promotion"])))
    assert DESK_ID not in named(k2) and k2.stub.bodies == []                 # another promotion's snapshot
    k2.r.take(state(snap(RAISES, orders={1: WORKING}, answered=[2])))
    assert DESK_ID not in named(k2) and k2.stub.bodies == [stop]


@pytest.mark.parametrize("desk", ["stopped", "answered"])
def test_an_owed_stop_the_desk_did_get_is_never_sent_again(kits, desk):
    stop = a_stop_owed_at_the_crash(kits)
    said = {"stopped": "Strategy error: boom"} if desk == "stopped" else {}
    k2 = restart(kits, "09:32:00", BACKLOG, snap(RAISES, answered=[2, stop["seq"]], **said))
    got = named(k2)
    assert k2.stub.bodies == []
    assert (got[DESK_ID]["state"] == "stopped") if desk == "stopped" else (DESK_ID not in got)


def test_a_done_day_whose_eod_flatten_was_lost_is_not_named_after_a_restart(kits):
    """Same class: the eod flatten never reached the Desk. Nothing of the runner's ends the day at the Desk, so no beat
    may say it is there (the Desk cancels its unfilled entries itself). The eod is not sent again."""
    k = a_short_day(kits)
    k.stub.script = [StubDesk.NO_ANSWER] * 30
    k.clock("10:00:03")
    for _ in range(12):
        k.wall[0] += 1.0
        k.r.idle()
    assert k.file()["state"] == "done" and k.stub.ops() == [["entry"]] + [["flatten"]] * 11
    crash(k)
    k2 = restart(kits, "10:01:00", [("09:20:00", [21000.0] * 2), ("09:29:01", [21000.0] * 60)],
                 snap(SHORT, answered=[2], **LIVE))
    assert k2.r.day("lab_x") is None and DESK_ID not in named(k2) and k2.stub.bodies == []


def test_a_day_that_could_not_be_picked_up_is_not_named_after_a_second_restart_either(kits):
    k = booked_at_nine(kits)
    minute(k, "09:29:01")
    k.r.take(("desk", "strategy", snap(answered=[2], **LIVE)))
    minute(k, "09:30:01", px=21010.0)
    crash(k)
    store.put_desk("lab_x", sidecar(accounts=()), k.at)                      # the book is gone: it cannot be picked up
    back = [("09:20:00", [21000.0] * 2), ("09:29:01", [21000.0] * 60), ("09:30:01", [21010.0] * 60)]
    k2 = restart(kits, "09:31:30", back, snap(answered=[2], **LIVE))
    assert k2.file()["why"] == NO_RESUME and DESK_ID not in named(k2)
    crash(k2)
    k3 = restart(kits, "09:32:30", back, snap(answered=[2], **LIVE))
    assert k3.r.day("lab_x") is None and DESK_ID not in named(k3) and k3.stub.bodies == []


def test_the_tell_logs_owed_stop():
    mark = ["sha", "p"]
    stop = {"seq": 4, "own": "stop", "t_ns": 9, "intents": [{"op": "stop", "why": "x", "flatten": True}]}
    no = {"seq": 4, "sent": True, "ok": False, "went": 0, "results": []}
    yes = {**no, "ok": True}
    head = {"head": 1, "mark": mark}
    assert host.owed_stop([head, stop, no, no], mark) == stop
    assert host.owed_stop([head, stop], mark) == stop                        # it never left, or no answer was written
    assert host.owed_stop([head, stop, no, yes], mark) is None               # the Desk answered it
    assert host.owed_stop([head, {k: v for k, v in stop.items() if k != "t_ns"}, no], mark) is None   # an older log
    assert host.owed_stop([head, stop, no], ["sha", "q"]) is None            # another promotion's
    assert host.owed_stop([head, stop, no, {"head": 1, "mark": mark}], mark) is None    # a later head: not this day's
    assert host.owed_stop([head, {"seq": 6, "own": "eod", "t_ns": 9, "intents": []}], mark) is None


def test_the_runners_stop_line_in_the_tell_log_carries_its_event_time(days):
    from tests.test_labrun_host import STOPS, planted
    day, stub, _, tells, _ = days(planted(STOPS["raises"][0]))
    feed(day, "09:29:50", [21000.0] * 11)
    feed(day, "09:30:01", [21000.0] * 60)
    assert stub.ops() == [["entry"], ["stop"]]
    assert {"seq": 4, "own": "stop", "t_ns": stub.bodies[1]["t_ns"], "intents": stub.bodies[1]["intents"]} in tells


# ================================================================ R3: every account gone mid-day
@pytest.mark.parametrize("how", ["unreadable", "empty book", "limits gone"])
def test_a_begun_desk_day_whose_book_stops_reading_sends_one_stop_and_then_ends(kits, how):
    k = booked_at_nine(kits)
    minute(k, "09:29:01")
    assert k.stub.ops() == [["entry"]]
    if how == "unreadable":
        (k.at / "lab_x.desk.json").write_text("{not json")
    elif how == "empty book":
        store.put_desk("lab_x", sidecar(accounts=()), k.at)
    else:
        store.put_desk("lab_x", sidecar(limits=None), k.at)
    k.r.sync()
    assert k.stub.ops() == [["entry"], ["stop"]]
    assert k.stub.bodies[1]["intents"] == [{"op": "stop", "why": "Stopped for today.", "flatten": False}]
    assert k.r.day("lab_x").state == "done" and k.today()["state"] == "done"
    for _ in range(3):
        k.wall[0] += 1.0
        k.r.idle()
        k.r.sync()
    minute(k, "09:30:01")
    assert len(k.stub.bodies) == 2


def test_a_stop_at_the_unbooking_that_gets_no_answer_is_asked_again(kits):
    k = booked_at_nine(kits)
    minute(k, "09:29:01")
    k.stub.script = [StubDesk.NO_ANSWER]
    store.put_desk("lab_x", sidecar(accounts=()), k.at)
    k.r.sync()
    k.wall[0] += 1.0
    k.r.idle()
    assert k.stub.ops() == [["entry"], ["stop"], ["stop"]] and k.stub.bodies[1] == k.stub.bodies[2]


# ================================================================ R2: a replayed event the Desk answered
@pytest.mark.parametrize("answered", [True, False])
def test_a_replayed_event_with_no_results_line_counts_as_refused_only_when_the_desk_did_not_answer_it(days, answered):
    """The reviewer's probe P2 (b): the runner died between the request and its results line; the Desk had taken it.
    (False: the Desk's snapshot is not in yet, so nobody knows: it reads as before.)"""
    day, stub, _, tells, _ = days(ONE)
    feed(day, "09:29:01", [21000.0] * 60)                                    # 09:30: the entry leaves (seq 2), taken
    assert stub.ops() == [["entry"]] and day._refused_run == 0
    day.kill()
    cut = [t for t in tells if not ("results" in t and t.get("seq") == 2)]
    up = snap(ONE, orders={1: WORKING}, answered=[2]) if answered else False
    day2, stub2, _, _, _ = days(ONE, resume=cut, tells=list(cut), up=up)
    feed(day2, "09:29:01", [21000.0] * 60)
    assert stub2.bodies == [] and day2.state == "running"
    if answered:
        assert day2._refused_run == 0 and day2.orders[-1]["refused"] is None
    else:
        assert day2._refused_run == 1 and day2.orders[-1]["refused"] == "The Desk did not answer."

