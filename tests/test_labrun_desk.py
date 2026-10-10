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


# ---------------------------------------------------------------- an entry is never sent twice
KEY = "ab" * 32


def boom(exc):
    def handler(req):
        raise exc
    return handler


TRANSPORT = {
    "timeout": boom(httpx.ReadTimeout("no answer in 5 s")),
    "connect timeout": boom(httpx.ConnectTimeout("no answer")),
    "refused": boom(httpx.ConnectError("refused")),
    "dropped": boom(httpx.RemoteProtocolError("Server disconnected without sending a response.")),
    "500": lambda req: httpx.Response(500, text="Internal Server Error"),
    "502": lambda req: httpx.Response(502),
    "503": lambda req: httpx.Response(503, json={"detail": "the runner's key is not available"}),
    "200 that does not read": lambda req: httpx.Response(200, text="<html>"),
}


class Wire:
    """The real DeskClient over a mock transport: every request that leaves the process is kept. `fail`: how the
    first `n` requests end; after that the Desk answers as tests.labrun_desk_util.StubDesk does."""

    def __init__(self, tmp_path, fail, n=1, key=KEY):
        self.requests, self.fail, self.n, self.stub = [], fail, n, StubDesk()
        self.key_file = tmp_path / "lab.key"
        if key is not None:
            self.key_file.write_text(key + "\n")
        self.client = DeskClient("http://127.0.0.1:8859", self.key_file, lambda item: None,
                                 transport=httpx.MockTransport(self.handle))

    def handle(self, req):
        self.requests.append(req)
        if len(self.requests) <= self.n:
            return self.fail(req)
        return httpx.Response(200, json=self.stub.take(json.loads(req.content)))

    def bodies(self) -> list:
        return [json.loads(r.content) for r in self.requests]

    def entry_requests(self) -> int:
        return sum(1 for b in self.bodies() if any(it["op"] == "entry" for it in b["intents"]))


@pytest.mark.parametrize("case", list(TRANSPORT))
def test_whatever_the_transport_does_exactly_one_entry_request_leaves_the_process(days, tmp_path, case):
    wire = Wire(tmp_path, TRANSPORT[case], n=99)
    day, _, side, tells, wall = days(stub=wire.client)
    feed(day, "09:29:50", [21000.0] * 11)
    assert texts(day) == [("Buy stop 21,005.00, stop 20,995.00, target 2 x the stop", "The Desk did not answer.")]
    assert tells[-1] == {"seq": 2, "sent": True, "ok": False,
                         "results": [{"op": "entry", "id": 1, "refused": "The Desk did not answer.", "dead": False}]}
    for _ in range(15):                                                      # the retry clock runs out: still one
        wall.t += 1.0
        day.tend()
    feed(day, "09:30:01", [21000.0] * 60)
    assert wire.entry_requests() == 1 and len(wire.requests) == 1
    assert list(plots(day)) == ["status working"]                            # the child is told nothing new


def test_an_entry_with_no_answer_is_resolved_only_by_the_stream(days):
    day, stub, side, _, _ = days(stub=StubDesk(StubDesk.NO_ANSWER))
    feed(day, "09:29:50", [21000.0] * 11)
    day.on_desk(snap(answered=[]))                                           # the Desk has not seen event 2 (yet?)
    feed(day, "09:30:01", [21000.0] * 60)
    assert list(plots(day)) == ["status working"]
    day.on_desk(snap(orders={1: filled()}, flat=False, answered=[2]))        # it did get there, and it filled
    feed(day, "09:31:01", [21000.0] * 60)
    assert plots(day)["fill"] == [[ms_of("09:32:00"), 21005.25]] and len(stub.entries()) == 1
    lost, stub2, _, _, _ = days(stub=StubDesk(StubDesk.NO_ANSWER))
    feed(lost, "09:29:50", [21000.0] * 11)
    lost.on_desk(snap(answered=[2]))                                         # answered, and no account holds it
    feed(lost, "09:30:01", [21000.0] * 60)
    assert list(plots(lost)) == ["status cancelled"] and len(stub2.entries()) == 1


def test_a_key_file_that_cannot_be_read_refuses_the_entry_here_and_nothing_leaves(days, tmp_path):
    wire = Wire(tmp_path, lambda req: pytest.fail("a request left without a key"), key=None)
    day, _, _, tells, _ = days(stub=wire.client)
    feed(day, "09:29:50", [21000.0] * 11)
    assert [r for _, r in texts(day)] == ["The Desk is not answering."] and wire.requests == []
    assert tells[-1]["sent"] is False and tells[-1]["results"][0]["dead"] is True and day.state == "running"


def test_the_key_never_reaches_a_url_a_log_line_the_tell_log_or_the_day_file(days, tmp_path, capfd):
    saved = []
    wire = Wire(tmp_path, TRANSPORT["timeout"], n=1)
    day, _, _, tells, wall = days(REPLACE, stub=wire.client, save=saved.append)
    feed(day, "09:29:50", [21000.0] * 11)                                    # no answer
    feed(day, "09:30:01", [21000.0] * 60)                                    # answered
    feed(day, "09:31:01", [21000.0] * 60)
    day.kill()
    assert len(wire.requests) == 3 and all(r.headers["x-homebase-key"] == KEY for r in wire.requests)
    out = capfd.readouterr()
    for text in (json.dumps(tells), json.dumps(saved), out.err, out.out, *(str(r.url) for r in wire.requests),
                 *(r.content.decode() for r in wire.requests)):
        assert KEY not in text
    assert "desk:" in out.err                                                # (the failed request was logged)


# ---------------------------------------------------------------- an exit is asked again
def test_a_cancel_whose_answer_never_came_is_asked_again_once_a_second_with_the_same_seq_and_the_same_bytes(days, tmp_path):
    wire = Wire(tmp_path, TRANSPORT["timeout"], n=0)
    day, _, side, tells, wall = days(stub=wire.client)
    feed(day, "09:29:50", [21000.0] * 11)                                    # the entry is taken
    wire.n = 4                                                               # ... and then the Desk goes quiet
    feed(day, "09:30:01", [21000.0] * 180)                                   # 09:33: the cancel
    assert texts(day)[-1] == ("Cancel", "The Desk did not answer.") and len(wire.requests) == 2
    day.tend()
    assert len(wire.requests) == 2                                           # not before a second has gone by
    for n in (3, 4, 5):
        wall.t += 1.0
        day.tend()
        day.tend()
        assert len(wire.requests) == n
    assert texts(day)[-1] == ("Cancel", None) and day.pending() is False     # the fourth try was answered
    assert len({r.content for r in wire.requests[1:]}) == 1                  # the same seq, the same intents: one body
    assert json.loads(wire.requests[1].content)["seq"] == 6 and wire.entry_requests() == 1
    assert [t for t in tells if t.get("seq") == 6 and "results" in t][-1] == {
        "seq": 6, "sent": True, "ok": True, "results": [{"op": "cancel", "id": 1, "refused": None, "dead": False}]}
    wall.t += 5.0
    day.tend()
    assert len(wire.requests) == 5


def test_an_exit_is_given_up_after_ten_seconds_and_its_row_says_so(days):
    stub = StubDesk()
    day, stub, _, _, wall = days(stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    stub.script = [StubDesk.NO_ANSWER] * 50
    feed(day, "09:30:01", [21000.0] * 180)
    for _ in range(30):
        wall.t += 0.5
        day.tend()
    assert len(stub.bodies) == 2 + 10 and day.pending() is False             # one a second, ten seconds
    assert texts(day)[-1] == ("Cancel", "The Desk did not answer.")


def test_the_exits_of_an_event_that_also_carried_an_entry_go_again_alone_under_a_new_seq(days):
    """No answer to [cancel 1, entry 2]: the entry is never sent again. Sending the cancel again under the same
    number would be another event with that number, so it goes as a new event of its own."""
    stub = StubDesk("took", StubDesk.NO_ANSWER)
    day, stub, _, tells, wall = days(REPLACE, stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    feed(day, "09:30:01", [21000.0] * 60)                                    # 09:31: cancel 1 + entry 2, no answer
    assert stub.ops() == [["entry"], ["cancel", "entry"]]
    assert texts(day)[1:] == [("Cancel", "The Desk did not answer."),
                              ("Buy stop 21,006.00, stop 20,996.00", "The Desk did not answer.")]
    wall.t += 1.0
    day.tend()
    assert stub.ops()[2] == ["cancel"] and stub.bodies[2]["seq"] == 4 and stub.bodies[1]["seq"] == 3
    assert texts(day)[1:] == [("Cancel", None), ("Buy stop 21,006.00, stop 20,996.00", "The Desk did not answer.")]
    assert {"seq": 4, "own": "again", "intents": [{"op": "cancel", "id": 1}]} in tells
    assert len(stub.entries()) == 2 and day.pending() is False               # (order 1 and order 2, once each)


def test_when_the_stream_shows_the_first_request_arrived_its_exits_are_not_sent_again(days):
    stub = StubDesk("took", StubDesk.NO_ANSWER)
    day, stub, _, _, wall = days(REPLACE, stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    feed(day, "09:30:01", [21000.0] * 60)
    day.on_desk(snap(REPLACE, orders={1: CANCELLED, 2: WORKING}, answered=[2, 3]))    # event 3 did reach the Desk
    wall.t += 1.0
    day.tend()
    assert len(stub.bodies) == 2 and day.pending() is False and texts(day)[1] == ("Cancel", None)


def not_ok(sentence="check it — its orders are not acknowledged yet"):
    def answer(body):
        return {"ok": True, "seq": body["seq"], "brain": None, "results": [
            {"op": it["op"], **({"id": it["id"]} if "id" in it else {}), "refused": None,
             "accounts": {ACCOUNT: {"ok": False, "state": "working", "actions": ["cancel entry 7: failed", sentence]}}}
            for it in body["intents"]]}
    return answer


def test_an_exit_the_desk_answered_but_could_not_carry_out_is_tried_again_under_a_new_seq(days):
    stub = StubDesk("took", not_ok(), not_ok())
    day, stub, _, tells, wall = days(stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    feed(day, "09:30:01", [21000.0] * 180)                                   # the cancel: answered, not carried out
    assert texts(day)[-1] == ("Cancel", "check it — its orders are not acknowledged yet") and day.pending()
    wall.t += 1.0
    day.tend()                                                               # again: a NEW event (the first was answered)
    wall.t += 1.0
    day.tend()                                                               # ... and this time the account did it
    assert [b["seq"] for b in stub.bodies] == [2, 6, 7, 8] and stub.ops()[1:] == [["cancel"]] * 3
    assert texts(day)[-1] == ("Cancel", None) and day.pending() is False
    assert [t["seq"] for t in tells if t.get("own") == "again"] == [7, 8]


def test_an_exit_the_desk_cannot_carry_out_is_given_up_after_ten_seconds_with_the_desks_sentence(days):
    stub = StubDesk()
    day, stub, _, _, wall = days(stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    stub.script = [not_ok("check it")] * 50
    feed(day, "09:30:01", [21000.0] * 180)
    for _ in range(40):
        wall.t += 0.5
        day.tend()
    seqs = [b["seq"] for b in stub.bodies[1:]]
    assert len(seqs) == 1 + 10 and seqs == sorted(set(seqs))                 # ten more tries, each a new number
    assert texts(day)[-1] == ("Cancel", "check it") and day.pending() is False
    assert host.exit_trouble({"accounts": {"a": {"ok": True}, "b": {"ok": False, "reason": "The account is not connected."}}}) \
        == "The account is not connected."
    assert host.exit_trouble({"accounts": {"error": "TypeError: x"}}) == "The Desk cannot check this order."
    assert host.exit_trouble({"accounts": {"a": {"ok": True, "sold": 1}}}) is None and host.exit_trouble({}) is None


# ---------------------------------------------------------------- stops
@pytest.mark.parametrize("case", ["raises", "spins", "floods its stdout", "50 orders", "exits", "talks out of turn"])
def test_a_strategy_that_breaks_gets_out_at_once_a_stop_with_flatten(days, case):
    body, why = STOPS[case]
    day, stub, _, tells, _ = days(planted(body))
    feed(day, "09:29:50", [21000.0] * 11)                                    # its entry
    feed(day, "09:30:01", [21000.0] * 60)                                    # 09:31: it breaks
    assert day.state == "stopped" and day.summary()["why"] == why and day.child_alive() is False
    assert stub.ops() == [["entry"], ["stop"]]
    assert stub.bodies[1]["intents"] == [{"op": "stop", "why": why, "flatten": True}]
    assert stub.bodies[1]["seq"] == 4 and stub.bodies[1]["strategy"] == DESK_ID and stub.bodies[1]["date"] == DATE
    assert {"seq": 4, "own": "stop", "intents": stub.bodies[1]["intents"]} in tells
    feed(day, "09:31:01", [21000.0] * 60)
    assert len(stub.bodies) == 2                                             # once


def test_switched_off_is_a_stop_that_keeps_the_position(days):
    day, stub, _, _, _ = days()
    feed(day, "09:29:50", [21000.0] * 11)
    day.off()
    assert day.state == "off" and stub.bodies[-1]["intents"] == [{"op": "stop", "why": "off", "flatten": False}]
    day.off()
    assert stub.ops() == [["entry"], ["stop"]]


def test_a_runner_that_goes_away_on_purpose_ends_the_desk_day_and_keeps_the_position(days):
    day, stub, _, _, _ = days()
    feed(day, "09:29:50", [21000.0] * 11)
    day.leave()
    assert stub.bodies[-1]["intents"] == [{"op": "stop", "why": "Stopped for today.", "flatten": False}]
    s = day.summary()
    assert (s["state"], s["why"]) == ("stopped", "Stopped for today.") and day.child_alive() is False
    day.leave()
    assert stub.ops() == [["entry"], ["stop"]]


def test_a_day_that_has_not_begun_sends_no_stop_when_the_runner_goes_or_it_is_switched_off(days):
    """A day hosted the evening before, or hours before its window: nothing of it is at the Desk, and a stop would
    end the strategy's Desk day for nothing."""
    day, stub, _, _, _ = days()
    day.on_ticks(ticks("09:20:00", [21000.0]))
    day.leave()
    assert day.state == "waiting" and stub.bodies == []
    day.off()
    assert day.state == "off" and stub.bodies == []


def test_a_stop_the_desk_does_not_answer_is_asked_again_with_the_same_seq_and_the_runner_stays_running_meanwhile(days):
    stub = StubDesk()
    day, stub, _, _, wall = days(stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    stub.script = [StubDesk.NO_ANSWER, StubDesk.NO_ANSWER]
    day.leave()
    assert day.state == "running" and day.pending()                          # not over until the Desk has it
    wall.t += 1.0
    day.tend()
    wall.t += 1.0
    day.tend()
    assert day.state == "stopped" and not day.pending()
    assert stub.bodies[1] == stub.bodies[2] == stub.bodies[3] and stub.bodies[1]["seq"] == 3


# ---------------------------------------------------------------- the Desk ends the day itself
@pytest.mark.parametrize("word, why", [({"killed": True}, "Killed today."), ({"stopped": "off"}, "Stopped for today."),
                                       ({"stopped": "Both entries filled."}, "Stopped for today.")])
def test_killed_or_stopped_on_the_stream_stops_the_child_and_nothing_is_sent(days, word, why):
    day, stub, _, _, wall = days()
    feed(day, "09:29:50", [21000.0] * 11)
    day.on_desk(snap(orders={1: WORKING}, answered=[2], **word))
    assert day.state == "stopped" and day.summary()["why"] == why and day.child_alive() is False
    feed(day, "09:30:01", [21000.0] * 200)
    wall.t += 30.0
    day.tend()
    day.blind(60.0)
    day.leave()
    day.off()
    assert stub.ops() == [["entry"]]                                         # no stop, no cancel: nothing more


def test_once_the_desk_says_stopped_what_was_still_to_be_asked_again_is_dropped(days):
    stub = StubDesk()
    day, stub, _, _, wall = days(stub=stub)
    feed(day, "09:29:50", [21000.0] * 11)
    stub.script = [StubDesk.NO_ANSWER] * 5
    feed(day, "09:30:01", [21000.0] * 180)                                   # the cancel: no answer, to be asked again
    assert day.pending()
    day.on_desk(snap(orders={1: CANCELLED}, answered=[2], stopped="off"))
    wall.t += 5.0
    day.tend()
    assert not day.pending() and len(stub.bodies) == 2


def test_a_snapshot_of_another_day_that_says_stopped_stops_nothing(days):
    day, stub, _, _, _ = days()
    feed(day, "09:29:50", [21000.0] * 11)
    day.on_desk({**snap(stopped="off", killed=True), "date": "2024-03-04"})  # yesterday's word
    assert day.state == "running"


# ---------------------------------------------------------------- no prices
def test_twenty_seconds_without_prices_cancels_every_unfilled_entry_once(days):
    day, stub, side, tells, wall = days()
    feed(day, "09:29:50", [21000.0] * 11)
    day.blind(19.9)
    assert stub.ops() == [["entry"]]
    day.blind(20.0)
    assert stub.ops() == [["entry"], ["cancel"]] and stub.bodies[1]["intents"] == [{"op": "cancel", "id": 1}]
    assert stub.bodies[1]["seq"] == 3 and {"seq": 3, "own": "blind", "intents": [{"op": "cancel", "id": 1}]} in tells
    day.blind(25.0)
    day.blind(300.0)
    assert len(stub.bodies) == 2                                             # once for the spell
    assert texts(day) == [("Buy stop 21,005.00, stop 20,995.00, target 2 x the stop", None)]      # not the strategy's order
    day.on_desk(snap(orders={1: CANCELLED}, answered=[2, 3]))
    day.blind(0.5)                                                           # prices are back
    feed(day, "09:30:01", [21000.0] * 60)
    assert list(plots(day)) == ["status cancelled"]                          # the child hears it from the Desk


def test_no_prices_with_nothing_working_sends_nothing(days):
    day, stub, _, _, _ = days()
    day.blind(60.0)
    feed(day, "09:29:50", [21000.0] * 11)
    day.on_desk(snap(orders={1: filled()}, flat=False, answered=[2]))        # in a position: it keeps its broker stop
    feed(day, "09:30:01", [21000.0] * 60)
    day.blind(60.0)
    assert stub.ops() == [["entry"]]
    assert host.StrategyDay(rec(MARKET_930), D, spawn=plain, daily=[]).blind(60.0) is None        # a shadow day: nothing


# ---------------------------------------------------------------- what is not today's
def test_a_carried_row_is_never_a_trade_and_never_makes_the_day_not_flat(days):
    day, stub, _, _, _ = days()
    feed(day, "09:29:50", [21000.0] * 11)
    old = rnd(status="live", exit_=None, reason=None, pnl=None, carried=True, date="2024-03-04")
    day.on_desk(snap(orders={1: WORKING}, flat=True, answered=[2], rounds=[old]))
    feed(day, "09:30:01", [21000.0] * 60)
    assert day.trades() == [] and day.summary()["trades"] == [] and plots(day)["status working"][0][1] == 1.0
