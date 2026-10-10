"""Step B (B3), fix round 1: one test per finding of the task review (task-b3-review.md), each written before its
fix and failing on 9ea26379. The reviewer's probes (which asserted the PROBLEM) are turned round here: a pass means
the problem is gone. The real engine on the engine tests' fake adapters; no broker, no network."""
from __future__ import annotations

import asyncio
import dataclasses
import datetime as dt
import json
import time

import pytest

from homebase import desk_api, engine as engine_mod, labcfg, labdesk
from homebase.broker.base import OrderResult
from homebase.labdesk import LabDesk, Refused
from homebase.labrun import door
from tests.labdesk_util import DATE, LAB, MARK, Stepper, body, entry, journal, mkdesk, pair, send
from tests.test_engine import run
from tests.test_engine_lab import fill_entry, fill_exit
from tests.test_labdesk import NQ930, hold_clock, placed, refusal, st, tick
from tests.trading_util import Mono

LAST_TRADE = "The Desk cannot check the last trade's orders."
BOT = {"nq930": dataclasses.replace(NQ930, self_fire=False)}     # a strategy that is not from the Lab (its acks can hang)


def restart(d) -> LabDesk:
    """The desk process starts again on the same engine root and journal."""
    ld2 = LabDesk(d.cfg, d.eng, d.ads)
    ld2._mono = Stepper()
    ld2.start()
    return ld2


def lines(d, name=None):
    return journal(d.tmp, name)


# ================================================================ C1: an exit under an answered seq is another event
def test_an_exit_that_reuses_an_answered_seq_is_applied(tmp_path):
    d = mkdesk(tmp_path)
    first = send(d, entry(1), seq=1)
    fill_entry(d.eng, d.ads["a1"], st(d), 110.25)                                  # in a position
    # the runner lost its place and counts from 1 again; the strategy crashed
    out = send(d, {"op": "stop", "why": "Strategy error: boom", "flatten": True}, seq=1)
    assert out["results"][0]["op"] == "stop" and out["results"][0]["accounts"]["a1"]["sold"] == 1
    assert [(o.side, o.qty, o.text) for o in d.ads["a1"].orders] == [("Sell", 1, "homebase:lab-flat")]
    assert d.ld._rec(LAB)["stopped"] == "Strategy error: boom"
    # the first event's stored answer is kept: the very same event again applies nothing and reads as it did
    again = send(d, entry(1), seq=1)
    assert again["results"] == first["results"] and len(d.ads["a1"].brackets) == 1
    assert d.ld.snapshot()["strategies"][LAB]["answered"] == [1]


def test_another_event_under_an_answered_seq_has_its_exits_applied_and_its_entries_refused(tmp_path):
    d = mkdesk(tmp_path)
    send(d, entry(1), seq=1)
    out = send(d, [{"op": "cancel", "id": 1}, entry(2)], seq=1)                    # not the event the desk answered as 1
    assert out["results"][0]["accounts"]["a1"]["state"] == "cancelled" and st(d).exit_reason == "cancelled"
    assert refusal(out, 1) == "This order is out of date." and len(d.ads["a1"].brackets) == 1
    tick(d)
    out = send(d, {"op": "flatten", "reason": "x"}, seq=1)                         # and a third one: applied too
    assert out["results"][0]["op"] == "flatten"


def test_a_restarted_desk_still_tells_the_same_event_from_another_under_its_seq(tmp_path):
    d = mkdesk(tmp_path)
    first = send(d, entry(1), seq=1)
    fill_entry(d.eng, d.ads["a1"], st(d), 110.25)
    ld2 = restart(d)
    again = run(ld2.event(body(d, [entry(1)], seq=1)))
    assert again["results"] == first["results"] and len(d.ads["a1"].brackets) == 1
    out = run(ld2.event(body(d, [{"op": "flatten", "reason": "time"}], seq=1)))
    assert out["results"][0]["accounts"]["a1"]["sold"] == 1 and len(d.ads["a1"].orders) == 1
    ld3 = restart(d)                                                               # two events under seq 1 in the journal:
    again = run(ld3.event(body(d, [entry(1)], seq=1)))                             # the first one's answer is the stored one
    assert again["results"] == first["results"] and len(d.ads["a1"].brackets) == 1


# ================================================================ I1: a line with another mark and a restart
def test_a_line_with_another_mark_never_makes_a_restart_forget_the_answered_set(tmp_path):
    d = mkdesk(tmp_path)
    send(d, entry(1), seq=1)
    send(d, {"op": "cancel", "id": 1}, seq=2)
    tick(d)
    assert d.eng.lab_rounds(LAB)[0]["clean"] is True
    stale = body(d, [{"op": "cancel", "id": 1}], seq=40)                           # an old child's exit: applied, by ruling
    stale["mark"] = ["old", "2026-10-01T00:00:00+00:00"]
    run(d.ld.event(stale))
    assert [x["counted"] for x in lines(d, "lab_event")] == [True, True, False]
    ld2 = restart(d)
    r = ld2._rec(LAB)
    assert (r["mark"], sorted(r["answers"]), r["seq_max"]) == (MARK, [1, 2], 2)
    run(ld2.event(body(d, [entry(1)], seq=1)))                                     # the runner sends seq 1 again
    assert len(d.ads["a1"].brackets) == 1                                          # answered from the store: not applied twice


def test_counters_and_the_stop_still_come_back_from_every_line(tmp_path):
    d = mkdesk(tmp_path)
    send(d, entry(1), seq=1)
    stale = body(d, [{"op": "stop", "why": "Strategy error: old child", "flatten": False}], seq=40)
    stale["mark"] = ["old", "2026-10-01T00:00:00+00:00"]
    run(d.ld.event(stale))
    r = restart(d)._rec(LAB)
    assert (r["entries"], r["stopped"], sorted(r["answers"])) == (1, "Strategy error: old child", [1])


# ================================================================ I2: both legs filled stops the strategy
def whipsaw(d, a="a1"):
    s = st(d, a)
    fill_entry(d.eng, d.ads[a], s, 110.25, "Buy")
    try:
        fill_entry(d.eng, d.ads[a], s, 89.75, "Sell")                              # the other leg fills too
    except AssertionError:
        pass
    assert (s.status, s.exit_reason) == ("error", "both_filled")


def test_both_legs_filled_stops_the_strategy_and_takes_the_other_accounts_entries_out(tmp_path):
    d = mkdesk(tmp_path, accounts=("a1", "a2"))
    assert send(d, pair(), seq=1)["results"][0]["status"] == "working"
    whipsaw(d)
    assert st(d, "a2").status == "placed"                                          # a2's two entry stops still rest
    run(d.ld._intake_tick())
    assert d.ld._rec(LAB)["stopped"] == "Both entries filled."
    assert (st(d, "a2").status, st(d, "a2").exit_reason) == ("done", "cancelled")
    said = lines(d, "lab_stopped")
    assert [(x["why"], x["cause"], x["flatten"]) for x in said] == [("Both entries filled.", "both_filled", False)]
    assert d.ld.snapshot()["strategies"][LAB]["stopped"] == "Both entries filled."
    for _ in range(3):
        run(d.ld._intake_tick())
    assert len(lines(d, "lab_stopped")) == 1                                       # once
    assert d.ads["a1"].orders == [] or all(o.text != "homebase:lab-flat" for o in d.ads["a1"].orders)


def test_the_both_filled_stop_never_waits_for_an_event_that_is_being_applied(tmp_path):
    d = mkdesk(tmp_path)
    send(d, pair(), seq=1)
    whipsaw(d)

    async def go():
        async with d.ld._lock(LAB):
            await asyncio.wait_for(d.ld._intake_tick(), 1)
            assert d.ld._rec(LAB)["stopped"] is None                               # the next pass
        await d.ld._intake_tick()
    run(go())
    assert d.ld._rec(LAB)["stopped"] == "Both entries filled."


# ================================================================ I3: the heartbeat rule, once per round
def test_the_rule_guards_a_round_opened_after_it_fired(tmp_path):
    d = mkdesk(tmp_path)
    mono = d.ld._mono = Mono()
    d.ld._t0 = mono.t
    send(d, entry(1), seq=1)
    mono.t += 25
    run(d.ld._runner_rule())
    assert st(d).exit_reason == "cancelled"
    tick(d)
    mono.t += 1
    assert send(d, entry(2), seq=2)["results"][0]["status"] == "working"           # an event is not a beat: still none
    mono.t += 300
    for _ in range(10):
        run(d.ld._runner_rule())
    assert (st(d).status, st(d).exit_reason) == ("done", "cancelled")              # round 2's entry is taken out too
    down = lines(d, "lab_runner_down")
    assert len(down) == 2 and d.ld.status_view(LAB)["refused"] == []


def test_with_a_position_open_and_no_beat_the_rule_speaks_once_for_that_round(tmp_path):
    d = mkdesk(tmp_path)
    mono = d.ld._mono = Mono()
    d.ld._t0 = mono.t
    send(d, entry(1), seq=1)
    fill_entry(d.eng, d.ads["a1"], st(d), 110.25)
    mono.t += 25
    for _ in range(8):                                                             # two seconds of passes
        run(d.ld._runner_rule())
        mono.t += 0.25
    assert len(lines(d, "lab_runner_down")) == 1 and st(d).status == "live" and d.ads["a1"].orders == []
    assert d.ld.status_view(LAB)["state"] == "runner_down"


# ================================================================ I4: a market entry whose stop is already through
@pytest.mark.parametrize("side,sl,last,past", [("long", 95.0, 94.0, True), ("long", 95.0, 95.0, True),
                                               ("long", 95.0, 95.25, False), ("short", 105.0, 106.0, True),
                                               ("short", 105.0, 105.0, True), ("short", 105.0, 104.75, False)])
def test_a_market_entry_whose_stop_the_last_price_is_already_through_is_refused(tmp_path, side, sl, last, past):
    d = mkdesk(tmp_path)
    out = send(d, entry(1, kind="market", side=side, sl=sl, tp=None, ref=100.0, move=False), seq=1, last=last)
    assert refusal(out) == ("The price is already past this entry." if past else None)
    assert len(d.ads["a1"].brackets) == (0 if past else 1)


# ================================================================ I5: refusals at checks 1-2 and the rate limit
def test_stale_entry_events_count_against_the_rate_limit(tmp_path):
    d = mkdesk(tmp_path)
    d.ld._mono = Mono()                                                            # one instant
    n0 = len(lines(d))
    for i in range(1, 6):
        b = body(d, [entry(i)], seq=i)
        b["mark"] = ["zz", "x"]
        assert refusal(run(d.ld.event(b))) == "This order is out of date."
    n1 = len(lines(d))
    assert n1 - n0 == 15
    for i in range(6, 40):
        b = body(d, [entry(i)], seq=i)
        b["mark"] = ["zz", "x"]
        with pytest.raises(Refused) as e:
            run(d.ld.event(b))
        assert (str(e.value), e.value.status) == ("Too many orders at once.", 429)
    assert len(lines(d)) == n1                                                     # over the limit: not a line
    b = body(d, [{"op": "cancel", "id": 1}, entry(99)], seq=99)                    # with an exit in it: applied, not 429
    b["mark"] = ["zz", "x"]
    assert run(d.ld.event(b))["results"][0]["refused"] is None


def test_an_event_for_a_name_that_is_not_a_lab_strategy_here_writes_one_refusal_a_minute_and_nothing_else(tmp_path):
    d = mkdesk(tmp_path, extra={"nq930": dataclasses.replace(NQ930)})
    mono = d.ld._mono = Mono()
    n0 = len(lines(d))
    for name in ("lab_ghost", "nq930"):
        for i in range(1, 4):
            out = run(d.ld.event(body(d, [entry(i), {"op": "cancel", "id": 9}], seq=i, strategy=name)))
            assert refusal(out) == "That strategy is not on the Desk."
            mono.t += 2.0
    new = lines(d)[n0:]
    assert [(x["event"], x["strategy"]) for x in new] == [("lab_refused", "lab_ghost"), ("lab_refused", "nq930")]
    mono.t += 60.0
    run(d.ld.event(body(d, [entry(7)], seq=7, strategy="lab_ghost")))
    assert len(lines(d)) == n0 + 3                                                 # a minute later: once more


def test_names_that_are_not_on_the_desk_share_one_rate_limit(tmp_path):
    d = mkdesk(tmp_path)
    d.ld._mono = Mono()
    for i in range(1, 6):
        run(d.ld.event(body(d, [entry(i)], seq=i, strategy=f"lab_ghost{i}")))
    with pytest.raises(Refused) as e:
        run(d.ld.event(body(d, [entry(6)], seq=6, strategy="lab_ghost6")))
    assert e.value.status == 429 and len(d.ld._hits) <= 2                          # nothing grows with the names
    assert send(d, entry(1), seq=1)["results"][0]["status"] == "working"           # the Lab strategy's own limit is its own


# ================================================================ I6: the words when a round is not clean
def test_flat_with_a_round_that_is_not_clean_is_refused_in_the_engines_words(tmp_path):
    assert labdesk.LAST_TRADE == engine_mod.LAB_CANNOT_CHECK == LAST_TRADE
    d = mkdesk(tmp_path, accounts=("a1", "a2"))
    send(d, entry(1), seq=1)
    assert refusal(send(d, entry(2), seq=2)) == door.ONE_AT_A_TIME                 # an entry is working: the door's words
    for a in ("a1", "a2"):
        fill_entry(d.eng, d.ads[a], st(d, a), 110.25)
    assert refusal(send(d, entry(3), seq=3)) == door.ONE_AT_A_TIME                 # in a position
    for a in ("a1", "a2"):
        fill_exit(d.eng, d.ads[a], st(d, a), 120.0, "tp")
    out = send(d, entry(4), seq=4)                                                 # out; the orders not read ended yet
    assert refusal(out) == LAST_TRADE and out["results"][0]["status"] == "cancelled"
    assert out["results"][0]["accounts"] == {a: {"ok": False, "round": None, "reason": LAST_TRADE} for a in ("a1", "a2")}
    assert (d.ld._rec(LAB)["untaken"], d.ld._rec(LAB)["stopped"]) == (0, None)     # the desk's refusal: counts nothing
    assert len(d.ads["a1"].brackets) == len(d.ads["a2"].brackets) == 1             # no account takes it, as built
    assert refusal(send(d, entry(5, sl=None), seq=5)) == door.NO_STOP              # the door's other sentences come first
    tick(d)
    assert send(d, entry(6), seq=6)["results"][0]["status"] == "working"


def test_two_re_entries_right_after_an_exit_do_not_stop_the_day(tmp_path):
    d = mkdesk(tmp_path)
    seq = 0
    for n in (1, 2):
        seq += 1
        send(d, entry(n), seq=seq)
        fill_entry(d.eng, d.ads["a1"], st(d), 110.25)
        fill_exit(d.eng, d.ads["a1"], st(d), 120.0, "tp")
        seq += 1
        assert refusal(send(d, entry(10 + n), seq=seq)) == LAST_TRADE
        tick(d)
    assert d.ld._rec(LAB)["stopped"] is None and d.ld._rec(LAB)["untaken"] == 0


# ================================================================ I7: checks that had no test of their own
def test_the_same_event_posted_twice_at_once_is_one_entry(tmp_path):                 # the per-strategy lock
    d = mkdesk(tmp_path, extra=dict(BOT))
    bot = d.eng._state("nq930", "a1")
    bot.status = "placing"
    d.ld._mono = time.monotonic

    async def go():
        t1 = asyncio.ensure_future(d.ld.event(body(d, [entry(1)], seq=1)))
        t2 = asyncio.ensure_future(d.ld.event(body(d, [entry(1)], seq=1)))
        await asyncio.sleep(0.1)
        bot.status = "placed"
        return await asyncio.gather(t1, t2)
    a, b = run(go())
    assert len(d.ads["a1"].brackets) == 1 and a["results"] == b["results"]


def test_a_caller_that_goes_away_in_the_hold_leaves_one_whole_event(tmp_path):       # the shield
    d = mkdesk(tmp_path, extra=dict(BOT))
    bot = d.eng._state("nq930", "a1")
    bot.status = "placing"
    d.ld._mono = time.monotonic

    async def go():
        t1 = asyncio.ensure_future(d.ld.event(body(d, [entry(1)], seq=1)))
        await asyncio.sleep(0.05)
        t1.cancel()                                                                # the HTTP connection drops
        with pytest.raises(asyncio.CancelledError):
            await t1
        bot.status = "placed"
        await asyncio.sleep(0.1)                                                   # the event finishes by itself
        n = len(d.ads["a1"].brackets)
        return n, await d.ld.event(body(d, [entry(1)], seq=1))                     # the runner asks again
    n, again = run(go())
    assert n == 1 and len(d.ads["a1"].brackets) == 1 and again["results"][0]["status"] == "working"
    assert [x["event"] for x in lines(d) if x["event"] in ("lab_event", "lab_event_done")] == ["lab_event", "lab_event_done"]


@pytest.mark.parametrize("change,sentence", [("mark", "This order is out of date."),
                                             ("store", "The Desk cannot check this order.")])
def test_the_promotion_and_the_store_are_asked_again_after_the_wait(tmp_path, change, sentence):
    d = mkdesk(tmp_path, extra=dict(BOT))
    hold_clock(d)
    bot = d.eng._state("nq930", "a1")
    bot.status = "placing"

    def flip(n):
        if n == 5:
            if change == "mark":
                labcfg.entry(d.cfg, LAB)["mark"] = ["cd", "2026-10-10T08:00:00+00:00"]      # promoted again meanwhile
            else:
                d.ld.close()                                                       # the desk let the store go
            bot.status = "placed"
    d.on_poll.append(flip)
    assert refusal(send(d, entry())) == sentence and placed(d) == []


def test_the_daily_limit_holds_for_an_account_that_sat_an_earlier_trade_out(tmp_path):   # the door's entries_today
    d = mkdesk(tmp_path, accounts=("a1", "a2"), limits={"max_trades_day": 1, "max_qty": 2, "max_risk_usd": 300,
                                                         "last_entry_et": "11:00", "flat_et": "15:55"})
    d.ads["a1"]._connected = False
    out = send(d, entry(1), seq=1)                                                 # a2 takes it, a1 sits it out
    assert out["results"][0]["accounts"]["a1"]["round"] is None and out["results"][0]["accounts"]["a2"]["round"] == 1
    send(d, {"op": "cancel", "id": 1}, seq=2)
    tick(d)
    d.ads["a1"]._connected = True
    out = send(d, entry(2), seq=3)                                                 # a1 has had no round of its own today
    assert refusal(out) == "Daily limit reached (1 trade)." and d.ads["a1"].brackets == []


def test_the_engine_is_handed_the_limit_as_its_own_cap(tmp_path):                        # ... and the engine's max_rounds
    d = mkdesk(tmp_path)
    seen, real = [], d.eng.lab_enter

    async def spy(name, legs, sizes, **kw):
        seen.append(kw)
        return await real(name, legs, sizes, **kw)
    d.eng.lab_enter = spy
    send(d, entry(1), seq=1)
    assert seen == [{"max_rounds": 3, "source": "lab"}]


def test_a_new_day_starts_a_new_intake_record(tmp_path):
    d = mkdesk(tmp_path)
    send(d, entry(1), seq=1)
    send(d, {"op": "stop", "why": "x", "flatten": False}, seq=2)
    assert d.ld._rec(LAB)["stopped"] == "x"
    tick(d)
    d.clock.dt += dt.timedelta(days=1)                                             # the same process, a Tuesday
    out = run(d.ld.event(body(d, [entry(1)], seq=1, date="2026-09-15")))
    r = d.ld._rec(LAB)
    assert out["results"][0]["status"] == "working" and len(d.ads["a1"].brackets) == 2
    assert (r["stopped"], r["entries"], sorted(r["answers"])) == (None, 1, [1])
    assert refusal(run(d.ld.event(body(d, [entry(9)], seq=9, date=DATE)))) == "This order is out of date."


def test_the_desks_stop_waits_for_the_event_that_is_being_applied(tmp_path):            # stop() takes the event lock
    d = mkdesk(tmp_path, extra=dict(BOT))
    bot = d.eng._state("nq930", "a1")
    bot.status = "placing"
    d.ld._mono = time.monotonic

    async def go():
        ev = asyncio.ensure_future(d.ld.event(body(d, [entry(1)], seq=1)))         # held: the 9:30 acks are out
        await asyncio.sleep(0.05)
        off = asyncio.ensure_future(d.ld.stop(LAB, "off"))                          # the owner switches it off meanwhile
        await asyncio.sleep(0.05)
        assert not off.done()                                                      # it waits its turn
        bot.status = "placed"
        return await asyncio.gather(ev, off)
    out, res = run(go())
    names = [x["event"] for x in lines(d) if x["event"] in ("lab_event_done", "lab_stopped")]
    assert names == ["lab_event_done", "lab_stopped"]                              # one after the other, never interleaved
    assert out["results"][0]["status"] == "working" and res["a1"]["state"] == "cancelled"
    assert (st(d).status, st(d).exit_reason) == ("done", "cancelled")              # and nothing of it is left resting


def test_an_entry_no_account_took_is_remembered_across_a_restart(tmp_path):              # `untaken` from the journal
    d = mkdesk(tmp_path)
    d.ads["a1"]._connected = False
    send(d, entry(1), seq=1)
    ld2 = restart(d)
    assert ld2._rec(LAB)["untaken"] == 1 and ld2._rec(LAB)["stopped"] is None
    out = run(ld2.event(body(d, [entry(2)], seq=2)))
    assert refusal(out) == "The account is not connected." and ld2._rec(LAB)["stopped"] == "Stopped for today."


def test_the_streams_first_state_waits_for_the_930_acks(tmp_path):
    d = mkdesk(tmp_path, extra=dict(BOT))
    bot = d.eng._state("nq930", "a1")
    bot.status = "placing"

    async def go():
        gen = desk_api.lab_stream(d.ld, heartbeat_s=0.03, poll_s=0.005)
        try:
            first = await gen.__anext__()
            assert first.startswith("event: heartbeat\n")                          # no snapshot is built while they are out
            bot.status = "placed"
            return await gen.__anext__()
        finally:
            await gen.aclose()
    assert run(go()).startswith("event: state\ndata: ")


# ================================================================ m1: the stop is on disk before the engine is asked
def test_the_stop_line_is_written_before_the_engine_is_asked(tmp_path):
    d = mkdesk(tmp_path)
    send(d, entry(1), seq=1)
    seen, real = [], d.eng.lab_cancel

    async def spy(name, iid=None, **kw):
        seen.append([x["why"] for x in lines(d, "lab_stopped")])
        return await real(name, iid, **kw)
    d.eng.lab_cancel = spy
    send(d, {"op": "stop", "why": "Strategy error: boom", "flatten": False}, seq=2)
    assert seen == [["Strategy error: boom"]]


def test_two_entries_no_account_took_stop_the_day_again_after_a_restart_even_without_the_line(tmp_path):
    d = mkdesk(tmp_path)
    d.ads["a1"]._connected = False
    send(d, entry(1), seq=1)
    real = d.eng.journal

    def flaky(event, **kw):
        if event == "lab_stopped":
            raise OSError("disk hiccup")
        return real(event, **kw)
    d.eng.journal = flaky
    send(d, entry(2), seq=2)
    assert d.ld._rec(LAB)["stopped"] == "Stopped for today."
    d.eng.journal = real
    d.ads["a1"]._connected = True
    ld2 = restart(d)
    assert (ld2._rec(LAB)["untaken"], ld2._rec(LAB)["stopped"]) == (2, "Stopped for today.")
    assert refusal(run(ld2.event(body(d, [entry(3)], seq=3)))) == "Stopped for today." and placed(d) == []


# ================================================================ m2: a raise in the entry checks never loses an exit
@pytest.mark.parametrize("where", ["_not_now", "_stale"])
def test_a_raise_in_the_entry_checks_still_applies_the_exit_beside_it(tmp_path, where):
    d = mkdesk(tmp_path)
    send(d, entry(1), seq=1)
    fill_entry(d.eng, d.ads["a1"], st(d), 110.25)
    def boom(*a):
        raise RuntimeError("the limits blew up")
    setattr(d.ld, where, boom)
    out = send(d, [{"op": "flatten", "reason": "time"}, entry(2)], seq=2)
    assert out["results"][0]["accounts"]["a1"]["sold"] == 1 and len(d.ads["a1"].orders) == 1
    assert refusal(out, 1) == "The Desk cannot check this order." and len(d.ads["a1"].brackets) == 1


# ================================================================ m5: after a wait the book and the door are asked again
def test_a_size_lowered_during_the_wait_goes_out_at_the_new_size(tmp_path):
    d = mkdesk(tmp_path, qty=2, extra=dict(BOT))
    hold_clock(d)
    bot = d.eng._state("nq930", "a1")
    bot.status = "placing"

    def flip(n):
        if n == 5:
            d.cfg.book[LAB] = [{"account": "a1", "qty": 1}]                         # the owner lowers the size on the page
            bot.status = "placed"
    d.on_poll.append(flip)
    send(d, entry(1, sl=108.0), seq=1)
    assert [q[5] for q in placed(d)] == [1]


def test_an_account_taken_off_and_a_risk_that_no_longer_fits_are_seen_after_the_wait(tmp_path):
    d = mkdesk(tmp_path, accounts=("a1", "a2"), extra=dict(BOT))
    hold_clock(d)
    bot = d.eng._state("nq930", "a1")
    bot.status = "placing"

    def flip(n):
        if n == 5:
            d.cfg.book[LAB] = [{"account": "a2", "qty": 2}]                         # a1 off the book, a2 up to 2: $400 at risk
            bot.status = "placed"
    d.on_poll.append(flip)
    out = send(d, entry(1, sl=100.0), seq=1)
    assert placed(d, "a1") == [] and placed(d, "a2") == []
    assert out["results"][0]["accounts"] == {"a2": {"ok": False, "round": None, "reason": "Stop too far: $400 at risk, limit $300."}}


def test_an_entry_that_never_waited_is_judged_once(tmp_path):
    d = mkdesk(tmp_path)
    calls, real = [], d.ld._verdicts

    def spy(*a):
        calls.append(1)
        return real(*a)
    d.ld._verdicts = spy
    send(d, entry(1), seq=1)
    assert calls == [1]


# ================================================================ m6: no snapshot is built in the seconds before a fire
def test_nothing_is_published_in_the_seconds_before_a_timer_fire(tmp_path):
    d = mkdesk(tmp_path, extra={"nq930": dataclasses.replace(NQ930)})
    send(d, entry(1), seq=1)
    q = d.ld.subscribe()
    d.ld.publish_changed()
    while q.qsize():
        q.get_nowait()
    d.clock.dt = dt.datetime(2026, 9, 14, 13, 29, 59, 900000, tzinfo=dt.timezone.utc)     # 09:29:59.9 ET
    assert d.ld._near_fire(d.eng.now_et()) is True and d.ld.held() is False
    fill_entry(d.eng, d.ads["a1"], st(d), 110.25)
    assert d.ld.publish_changed() is False and q.qsize() == 0
    d.clock.dt = dt.datetime(2026, 9, 14, 13, 30, 1, tzinfo=dt.timezone.utc)
    assert d.ld.publish_changed() is True and q.get_nowait()[1]["brain"]["orders"]["1"]["status"] == "filled"


# ================================================================ m8: the ids no account took do not grow all day
def test_the_order_ids_no_account_took_are_capped(tmp_path):
    d = mkdesk(tmp_path)
    for n in range(1, 231):
        send(d, entry(n, sl=None), seq=n)
    dead = d.ld._rec(LAB)["dead"]
    assert len(dead) == labdesk.DEAD_KEPT == 200 and dead[0] == 31 and dead[-1] == 230
    assert len(lines(d, "lab_event_done")[-1]["dead"]) == 200
    assert len(restart(d)._rec(LAB)["dead"]) == 200


# ================================================================ m11: the stream holds a queued snapshot while placing
def test_the_stream_holds_a_queued_snapshot_while_the_930_orders_are_placing(tmp_path):
    d = mkdesk(tmp_path, extra=dict(BOT))
    bot = d.eng._state("nq930", "a1")

    async def go():
        gen = desk_api.lab_stream(d.ld, heartbeat_s=0.03, poll_s=0.005)
        try:
            assert (await gen.__anext__()).startswith("event: state\n")
            bot.status = "placing"
            d.ld._publish("strategy", {"strategy": LAB, "n": 1})                   # queued just before the acks went out
            d.ld._publish("strategy", {"strategy": LAB, "n": 2})
            held = await gen.__anext__()
            assert held.startswith("event: heartbeat\n")                           # nothing is serialized meanwhile
            bot.status = "placed"
            return await gen.__anext__(), await gen.__anext__()
        finally:
            await gen.aclose()
    first, then = run(go())
    assert json.loads(first.split("data: ", 1)[1]) == {"strategy": LAB, "n": 2}    # the newest level, once
    assert first.startswith("event: strategy\n") and then.startswith("event: heartbeat\n")


def test_a_reader_dropped_while_its_snapshot_was_held_still_ends(tmp_path):
    d = mkdesk(tmp_path, extra=dict(BOT))
    bot = d.eng._state("nq930", "a1")

    async def go():
        gen = desk_api.lab_stream(d.ld, heartbeat_s=5, poll_s=0.005)
        assert (await gen.__anext__()).startswith("event: state\n")
        bot.status = "placing"
        q = next(iter(d.ld._subs))
        q.put_nowait(("strategy", {"strategy": LAB, "n": 1}))
        q.put_nowait((None, None))                                                 # the desk dropped this reader
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(gen.__anext__(), 1)
    run(go())
    assert d.ld._subs == set()
