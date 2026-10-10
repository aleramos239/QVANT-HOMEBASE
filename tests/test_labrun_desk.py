"""The runner's desk side (Step B, task B4): a day hosted in DESK MODE. The strategy's orders go to the Desk's intake
ONCE and the child hears only what the Desk says happened. The Desk here is a stub (tests/labrun_desk_util.py) or, for
the transport's failures, the real DeskClient over an httpx mock transport. No socket is opened, no service is called,
every store is a tmp_path."""
from __future__ import annotations

import json

import httpx
import pytest

from homebase.labrun import host
from homebase.labrun.deskclient import DeskClient
from tests.labrun_desk_util import (ACCOUNT, D, DATE, DESK_ID, EVERY, ONE, REPLACE, StubDesk, at, desk_day, feed, filled,
                                    mark_of, ms_of, plots, rec, rnd, snap, ticks)
from tests.test_labrun_host import MARKET_930, STOPS, plain, planted

WORKING = {"status": "working"}
CANCELLED = {"status": "cancelled"}


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


# ---------------------------------------------------------------- an order goes to the Desk, once
def test_an_entry_goes_to_the_desk_once_as_the_desk_reads_it_and_nothing_is_filled_here(days):
    day, stub, side, tells, _ = days()
    assert day.mode == "desk" and day.state == "waiting"
    feed(day, "09:29:50", [21000.0] * 11)                                    # 09:29:50 .. 09:30:00
    (body,) = stub.bodies
    assert body == {"strategy": DESK_ID, "date": DATE, "mark": mark_of(ONE), "seq": 2, "t_ns": at("09:30:00"),
                    "state": {"last_price": 21000.0, "last_ms": ms_of("09:29:59"), "prices_late": False},
                    "intents": [{"op": "entry", "id": 1, "kind": "stop", "side": "long", "price": 21005.0, "qty": 1,
                                 "own_qty": False, "sl": 20995.0, "tp": None, "tp_rr": 2.0, "ref": 21005.0, "move": False}]}
    assert texts(day) == [("Buy stop 21,005.00, stop 20,995.00, target 2 x the stop", None)]
    assert day.fills.working_entries == 0 and day.fills.flat is True         # the tape's model never saw the order
    feed(day, "09:30:01", [21010.0] * 5)                                     # through the trigger: the model would fill
    assert day.trades() == [] and day.summary()["trades"] == [] and day.fills.trades() == []
    assert len(stub.bodies) == 1 and day.state == "running"


def test_the_child_is_told_only_what_the_desk_says(days):
    day, stub, side, _, _ = days()
    feed(day, "09:29:50", [21000.0] * 11)
    feed(day, "09:30:01", [21010.0] * 60)                                    # the 09:30 bar closes at 09:31
    assert list(plots(day)) == ["status working"] and plots(day)["status working"][0][1] == 1.0     # flat, working
    day.on_desk(snap(orders={1: filled()}, flat=False, answered=[2]))        # the Desk: filled on its account
    feed(day, "09:31:01", [21012.0] * 60)
    assert plots(day)["status filled"] == [[ms_of("09:32:00"), 0.0]]         # ... filled, and not flat
    assert plots(day)["fill"] == [[ms_of("09:32:00"), 21005.25]]             # the account's own fill price
    day.on_desk(snap(orders={1: filled()}, flat=True, answered=[2], rounds=[rnd()]))
    feed(day, "09:32:01", [21012.0] * 60)
    assert plots(day)["status filled"][-1] == [ms_of("09:33:00"), 1.0]       # flat again, as the Desk says
    assert stub.ops() == [["entry"]]                                         # 09:33: it is filled, so no cancel


def test_only_orders_leave_drawings_never_do_and_an_event_with_no_order_sends_nothing(days):
    day, stub, _, _, _ = days()
    feed(day, "09:29:50", [21000.0] * 11)
    feed(day, "09:30:01", [21001.0] * 180)                                   # three bars (plots only), then 09:33
    assert stub.ops() == [["entry"], ["cancel"]]
    assert [b["seq"] for b in stub.bodies] == [2, 6]                         # every event has a number; few are sent
    assert texts(day)[-1] == ("Cancel", None)


def test_the_days_trades_and_net_are_the_lead_accounts_real_ones(days):
    day, stub, side, _, _ = days()
    feed(day, "09:29:50", [21000.0] * 11)
    day.on_desk(snap(orders={1: filled()}, flat=True, answered=[2], rounds=[rnd(pnl=396.0)]))
    s = day.summary()
    assert s["trades"] == [{"side": "long", "qty": 1, "entry_t": "09:30:30", "entry_px": 21005.25, "exit_t": "09:40:00",
                            "exit_px": 21025.25, "reason": "tp", "net": 396.0}]
    assert s["net"] == 396.0 and s["mode"] == "desk" and day.trade_count == 1
    assert "mode" not in host.StrategyDay(rec(MARKET_930), D, spawn=plain, daily=[]).summary()      # a shadow day's


# ---------------------------------------------------------------- the tell-log
def test_every_event_is_written_down_before_the_child_is_asked_then_its_intents_then_the_results(days):
    day, stub, side, tells, _ = days()
    assert tells == [{"head": 1, "strategy": DESK_ID, "mark": mark_of(ONE), "date": DATE}]
    feed(day, "09:29:50", [21000.0] * 11)
    assert tells[1] == {"seq": 1, "t_ns": at("09:25:00"), "kind": "session", "arg": None, "last_price": None,
                        "flat": True, "updates": [], "daily": []}
    assert tells[2] == {"seq": 1, "intents": []}
    assert tells[3] == {"seq": 2, "t_ns": at("09:30:00"), "kind": "time", "arg": "09:30:00", "last_price": 21000.0,
                        "flat": True, "updates": []}
    assert tells[4] == {"seq": 2, "intents": stub.bodies[0]["intents"]}
    assert tells[5] == {"seq": 2, "sent": True, "ok": True,
                        "results": [{"op": "entry", "id": 1, "refused": None, "dead": False}]}
    day.on_desk(snap(orders={1: filled()}, flat=False, answered=[2]))
    feed(day, "09:30:01", [21010.0] * 60)
    assert tells[6]["kind"] == "bar" and tells[6]["flat"] is False
    assert tells[6]["updates"] == [{"id": 1, **filled()}]                    # what the child was told, as it was told
    assert tells[7]["intents"][0]["op"] == "plot" and len(tells) == 8        # a drawing: no results line
    json.dumps(tells)                                                        # every line is plain JSON


def test_the_event_line_is_there_even_when_the_child_never_answers(days):
    body, why = STOPS["raises"]
    day, stub, _, tells, _ = days(planted(body))
    feed(day, "09:29:50", [21000.0] * 11)
    feed(day, "09:30:01", [21000.0] * 62)
    assert day.state == "stopped" and day.summary()["why"] == why
    asked = [t for t in tells if t.get("kind") == "time" and t["arg"] == "09:31:00"]
    assert len(asked) == 1 and not [t for t in tells if t.get("seq") == asked[0]["seq"] and "intents" in t and "own" not in t]


# ---------------------------------------------------------------- entries refused here, without a request
def test_prices_late_refuses_the_entry_here_and_nothing_is_sent(days):
    day, stub, _, _, _ = days()
    day.on_clock(ms_of("09:29:55"))
    day.on_ticks(ticks("09:29:52", [21000.0]))                               # arrives 3 s behind the clock
    day.on_clock(ms_of("09:29:59"))
    day.on_ticks(ticks("09:29:56", [21000.0]))
    day.on_clock(ms_of("09:30:00", 500))
    day.on_ticks(ticks("09:29:57", [21000.0]))                               # ... for more than 5 s: late
    day.on_clock(ms_of("09:30:02"))                                          # 09:30:00 fires by the clock
    assert texts(day) == [("Buy stop 21,005.00, stop 20,995.00, target 2 x the stop", "Prices are late.")]
    assert stub.bodies == [] and day.summary()["why"] == "Prices are late."


def test_a_silent_tick_stream_refuses_the_entry_here(days):
    day, stub, _, _, _ = days()
    day.on_ticks(ticks("09:29:50", [21000.0] * 9))
    day.no_prices(True)
    feed(day, "09:29:59", [21000.0] * 2)
    assert [r for _, r in texts(day)] == ["Prices are late."] and stub.bodies == []


def test_an_event_more_than_three_seconds_behind_the_streams_clock_sends_no_entry(days):
    day, stub, _, _, _ = days()
    day.on_ticks(ticks("09:29:50", [21000.0] * 9) + ticks("09:30:03", [21000.0]))     # exactly 3 s behind: it goes
    assert stub.ops() == [["entry"]] and texts(day)[0][1] is None
    late, stub2, _, _, _ = days()
    late.on_ticks(ticks("09:29:50", [21000.0] * 9) + [(at("09:30:03", 1), 21000.0, 1)])
    assert texts(late) == [("Buy stop 21,005.00, stop 20,995.00, target 2 x the stop", "Too late for this one.")]
    assert stub2.bodies == []


def test_a_clock_that_ran_ahead_makes_the_event_late_too(days):
    day, stub, _, _, _ = days(now_ns=at("09:00:00"))
    day.on_ticks(ticks("09:29:50", [21000.0] * 9))
    day.on_clock(ms_of("09:30:05"))                                          # the clock fires it, 5 s late
    assert [r for _, r in texts(day)] == ["Too late for this one."] and stub.bodies == []


@pytest.mark.parametrize("how", ["never heard", "down", "silent 15 s", "another promotion's snapshot", "another day's snapshot",
                                 "not on the Desk"])
def test_a_desk_that_is_not_answering_refuses_the_entry_here(days, how):
    day, stub, side, _, wall = days(up=how != "never heard")
    if how == "down":
        side.down()
    elif how == "silent 15 s":
        wall.t += 15.1
    elif how == "another promotion's snapshot":
        day.on_desk({**snap(flat=False), "mark": ["x", "y"]})
    elif how == "another day's snapshot":
        day.on_desk({**snap(flat=False), "date": "2024-03-04"})
    elif how == "not on the Desk":
        side.gone()
    feed(day, "09:29:50", [21000.0] * 11)
    assert [r for _, r in texts(day)] == ["The Desk is not answering."] and stub.bodies == []
    assert day.summary()["why"] == "The Desk is not answering." and day.state == "running"
    feed(day, "09:30:01", [21000.0] * 60)
    assert list(plots(day)) == ["status cancelled"]                          # the child knows it never went


def test_exits_in_the_same_event_still_go_when_the_entry_is_refused_here(days):
    day, stub, side, tells, _ = days(REPLACE)
    feed(day, "09:29:50", [21000.0] * 11)
    side.down()
    feed(day, "09:30:01", [21000.0] * 60)                                    # 09:31: cancel 1, entry 2
    assert stub.ops() == [["entry"], ["cancel"]]                             # the entry stayed here, the cancel went
    assert texts(day)[1:] == [("Cancel", None), ("Buy stop 21,006.00, stop 20,996.00", "The Desk is not answering.")]
    assert tells[-1] == {"seq": 3, "sent": True, "ok": True,
                         "results": [{"op": "cancel", "id": 1, "refused": None, "dead": False},
                                     {"op": "entry", "id": 2, "refused": "The Desk is not answering.", "dead": True}]}


# ---------------------------------------------------------------- what the Desk says about an order
def test_the_order_row_carries_the_desks_sentence_and_the_child_hears_cancelled(days):
    stub = StubDesk()
    stub.script = [stub.refuse("One position at a time.")]
    day, stub, _, tells, _ = days(stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    assert texts(day) == [("Buy stop 21,005.00, stop 20,995.00, target 2 x the stop", "One position at a time.")]
    assert tells[-1]["results"] == [{"op": "entry", "id": 1, "refused": "One position at a time.", "dead": True}]
    feed(day, "09:30:01", [21000.0] * 60)
    assert list(plots(day)) == ["status cancelled"]


def test_several_accounts_fold_to_one_line(days):
    took = {"op": "entry", "id": 1, "refused": None, "status": "working",
            "accounts": {"a1": {"ok": False, "round": None, "reason": "The account is not connected."},
                         "a2": {"ok": True, "round": 1, "reason": None}}}
    none = {"op": "entry", "id": 1, "refused": None, "status": "cancelled",
            "accounts": {"a1": {"ok": False, "round": None, "reason": "The account is not connected."},
                         "a2": {"ok": False, "round": None, "reason": "This account is stopped for the day."}}}
    assert host.desk_sentence(took) is None                                  # taken by at least one: no sentence
    assert host.desk_sentence(none) == "The account is not connected."       # taken by none: the first account's
    assert host.desk_sentence({**none, "refused": "Killed today."}) == "Killed today."     # the Desk's own fold
    assert host.desk_sentence({"status": "cancelled"}) == "The Desk cannot check this order."


def test_too_many_at_once_is_a_refusal_and_is_never_sent_again(days):
    stub = StubDesk({"ok": False, "left": True, "status": 429, "detail": "Too many orders at once."})
    day, stub, _, _, wall = days(stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    assert [r for _, r in texts(day)] == ["Too many orders at once."]
    for _ in range(12):
        wall.t += 1.0
        day.tend()
    feed(day, "09:30:01", [21000.0] * 60)
    assert len(stub.entries()) == 1 and list(plots(day)) == ["status cancelled"]


@pytest.mark.parametrize("status, detail, sentence", [
    (409, "Lab strategies are switched off on this Desk.", "Lab strategies are switched off on this Desk."),
    (400, "The request does not read.", "The Desk is not answering."), (401, None, "The Desk is not answering."),
    (403, None, "The Desk is not answering.")])
def test_a_request_the_desk_refused_whole_is_a_refusal_of_its_entries(days, status, detail, sentence):
    stub = StubDesk({"ok": False, "left": True, "status": status, "detail": detail})
    day, stub, _, tells, _ = days(stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    assert [r for _, r in texts(day)] == [sentence] and tells[-1]["results"][0]["dead"] is True
    assert tells[-1]["sent"] is True and tells[-1]["ok"] is False


def test_three_events_in_a_row_whose_entries_were_all_refused_stop_the_strategy_and_keep_the_position(days):
    stub = StubDesk()
    stub.script = [stub.refuse("Too late for a new trade today.")] * 3
    day, stub, _, _, _ = days(EVERY, stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    feed(day, "09:30:01", [21000.0] * 60)
    assert day.state == "running" and len(stub.bodies) == 2
    feed(day, "09:31:01", [21000.0] * 60)                                    # the third
    assert day.state == "stopped" and day.summary()["why"] == "Too late for a new trade today."
    assert stub.bodies[-1]["intents"] == [{"op": "stop", "why": "Too late for a new trade today.", "flatten": False}]
    assert len(stub.entries()) == 3 and day.child_alive() is False


def test_a_taken_entry_ends_the_run_of_refusals_and_a_refusal_here_counts(days):
    stub = StubDesk()
    stub.script = [stub.refuse("One position at a time."), stub.refuse("One position at a time."), "took",
                   stub.refuse("One position at a time.")]
    day, stub, side, _, _ = days(EVERY, stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)                                    # 09:30 refused
    for minute in ("09:30:01", "09:31:01", "09:32:01"):                      # 09:31 refused, 09:32 taken, 09:33 refused
        feed(day, minute, [21000.0] * 60)
    assert day.state == "running" and len(stub.bodies) == 4
    side.down()                                                              # ... and the next one is refused HERE:
    feed(day, "09:33:01", [21000.0] * 60)                                    # two in a row again, not three
    assert day.state == "running" and len(stub.bodies) == 4
    assert [r for _, r in texts(day)] == ["One position at a time.", "One position at a time.", None,
                                          "One position at a time.", "The Desk is not answering."]


def test_a_stop_after_three_floods_of_the_desk_keeps_the_position(days):
    """Three 429s read "Too many orders at once.", the very words of a strategy that floods its own pipe -- but this
    stop is the runner's, and it never flattens."""
    busy = {"ok": False, "left": True, "status": 429, "detail": "Too many orders at once."}
    day, stub, _, _, _ = days(EVERY, stub=StubDesk(busy, busy, busy))
    feed(day, "09:29:50", [21000.0] * 11)
    feed(day, "09:30:01", [21000.0] * 60)
    feed(day, "09:31:01", [21000.0] * 60)
    assert day.state == "stopped" and day.summary()["why"] == "Too many orders at once."
    assert stub.bodies[-1]["intents"] == [{"op": "stop", "why": "Too many orders at once.", "flatten": False}]
