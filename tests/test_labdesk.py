"""Step B (B3): LabDesk's intake half -- the one door a promoted strategy's orders go through. One test per check of
design C3 (both verdicts), one per ruling on top of it, the heartbeat rule, the stream, the start lines.

The REAL engine on the engine tests' fake adapters: an order "sent" here is a bracket a fake adapter recorded. No
broker, no network; the store is the conftest's temp folder, the engine's root the test's tmp_path."""
from __future__ import annotations

import asyncio
import dataclasses
import datetime as dt
import json
from collections import deque

import pytest

from homebase import engine as engine_mod
from homebase import labcfg, labdesk, trading
from homebase.config import StrategyCfg
from homebase.engine import DayState, Engine
from homebase.labdesk import LabDesk, Refused, parse_event
from homebase.labrun import door, host, store
from homebase.server import compute_readiness
from tests.labdesk_util import DATE, LAB, LIMITS, MARK, body, entry, journal, mkdesk, now_ms, pair, rec, send
from tests.test_engine import Clock, FakeAdapter, run
from tests.test_engine_lab import fill_entry, fill_exit
from tests.trading_util import Mono

UTC = dt.timezone.utc
NQ930 = StrategyCfg(symbol="ES", qty=1, offset_pts=10.0, sl_pts=5.0, tp_pts=15.0, enabled=True, self_fire=True)
# (never handed to a desk as it is: every use below makes its own copy, with dataclasses.replace)


def st(d, a="a1"):
    return d.eng.states[f"{LAB}@{a}"]


def tick(d):
    d.eng._retry_at.clear()                          # the engine's throttles use the wall clock
    run(d.eng.clock_tick())


def placed(d, a="a1"):
    return [(q.side, q.order_type, q.price, q.stop_price, q.tp_price, q.qty) for q in d.ads[a].brackets]


def refusal(out, i=0):
    return out["results"][i]["refused"]


def events(d, name=None):
    return journal(d.tmp, name)


def working(d, seq=1, **kw):
    """The desk with one entry resting at the broker (round 1, placed)."""
    out = send(d, entry(**kw), seq=seq)
    assert out["results"][0]["status"] == "working", out
    return out


def live(d, seq=1, px=110.25):
    """... and filled: a long position of 1 with its broker stop."""
    working(d, seq)
    fill_entry(d.eng, d.ads["a1"], st(d), px)
    assert st(d).status == "live"


# ---------------------------------------------------------------- the words
def test_the_intakes_sentences_are_the_engines_the_doors_and_the_designs():
    assert (labdesk.OFF, labdesk.KILLED, labdesk.TAKE_RULE, labdesk.NOT_WRITTEN, labdesk.NOT_ON_DESK, labdesk.PLACING_UNKNOWN) == \
        (engine_mod.LAB_OFF, engine_mod.LAB_KILLED, engine_mod.LAB_TAKE_RULE, engine_mod.LAB_NOT_WRITTEN,
         engine_mod.LAB_NOT_ON_DESK, engine_mod.PLACING_UNKNOWN)
    assert (labdesk.STOPPED_TODAY, labdesk.OUT_OF_DATE, labdesk.TOO_MANY, labdesk.FIRE_FIRST, labdesk.PRICE_PAST) == \
        ("Stopped for today.", "This order is out of date.", "Too many orders at once.", "The 9:30 orders go first.",
         "The price is already past this entry.")
    assert labdesk.TOO_MANY == host.TOO_MANY and labdesk.MAX_ORDERS == host.MAX_ORDERS == 20
    assert (labdesk.RATE_N, labdesk.RATE_WINDOW_S) == (trading.RATE_N, trading.RATE_WINDOW_S) == (5, 1.0)
    assert labdesk.OPEN == trading.BOT_BUSY and labdesk.RUNNER_ALIVE_S == 20 and labdesk.HOLD_S == 2.0
    assert labdesk.OPEN_WITHOUT_CFG == "A Lab trade is open but its strategy is not on this Desk. Check it."


# ---------------------------------------------------------------- the body (design C2)
def test_parse_event_reads_the_runners_event(tmp_path):
    d = mkdesk(tmp_path)
    ev = parse_event(body(d, pair() + [{"op": "cancel", "id": 2}, {"op": "flatten", "reason": "time"},
                                       {"op": "stop", "why": "Strategy error: x", "flatten": True},
                                       {"op": "plot", "name": "v", "t_ms": 1, "value": 2.0}], seq=17))
    assert (ev.strategy, ev.date, list(ev.mark), ev.seq) == (LAB, DATE, MARK, 17)
    assert (ev.last_price, ev.last_ms, ev.prices_late) == (100.0, now_ms(d), False)
    assert [i["op"] for i in ev.intents] == ["entry", "entry", "oco", "cancel", "flatten", "stop", "plot"]
    assert len(ev.entries) == 2 and [i["op"] for i in ev.exits] == ["cancel", "flatten", "stop"]


@pytest.mark.parametrize("change", [
    {"strategy": ""}, {"strategy": 5}, {"date": "today"}, {"date": None}, {"mark": "ab"}, {"mark": ["ab"]},
    {"mark": ["ab", 5]}, {"seq": -1}, {"seq": 1.0}, {"seq": True}, {"seq": None}, {"t_ns": "now"}, {"state": None},
    {"state": {"last_price": "100", "last_ms": 1}}, {"state": {"last_price": float("nan"), "last_ms": 1}},
    {"state": {"last_price": 100.0, "last_ms": 1.5}}, {"intents": None}, {"intents": [{"op": "nope"}]},
    {"intents": [{"op": "entry", "id": 1}]}, {"intents": [{"op": "stop", "why": "x"}]},
    {"intents": [entry(1), entry(1)]},                                           # an order id used twice
    {"intents": [{"op": "cancel", "id": i} for i in range(21)]},                 # 20 orders at most
])
def test_parse_event_refuses_a_body_that_does_not_read(tmp_path, change):
    d = mkdesk(tmp_path)
    with pytest.raises(ValueError):
        parse_event({**body(d, [entry()]), **change})
    for junk in (None, [], "x", 5):
        with pytest.raises(ValueError):
            parse_event(junk)


def test_prices_are_late_unless_the_runner_plainly_says_they_are_not(tmp_path):
    d = mkdesk(tmp_path)
    b = body(d, [entry()])
    assert parse_event(b).prices_late is False
    for v in (True, None, "false", 0):
        assert parse_event({**b, "state": {**b["state"], "prices_late": v}}).prices_late is True
    del b["state"]["prices_late"]
    assert parse_event(b).prices_late is True


# ---------------------------------------------------------------- an entry that passes every check
def test_an_entry_goes_to_every_booked_account_at_that_accounts_size(tmp_path):
    d = mkdesk(tmp_path, accounts=("a1", "a2"))
    run(d.ld.set_book(LAB, [{"account": "a1", "qty": 1}, {"account": "a2", "qty": 2}]))
    out = send(d, entry(tp=120.0))
    assert placed(d, "a1") == [("Buy", "Stop", 110.0, 105.0, 120.0, 1)]
    assert placed(d, "a2") == [("Buy", "Stop", 110.0, 105.0, 120.0, 2)]
    assert out["ok"] is True and out["seq"] == 1
    assert out["results"] == [{"op": "entry", "id": 1, "status": "working", "refused": None, "accounts": {
        "a1": {"ok": True, "round": 1, "reason": None}, "a2": {"ok": True, "round": 1, "reason": None}}}]
    assert out["brain"] == {"flat": True, "working": 1, "entries_today": 1, "orders": {"1": {"status": "working"}}}
    assert st(d).status == st(d, "a2").status == "placed" and events(d, "lab_refused") == []


def test_the_event_is_written_down_before_the_order_leaves_and_again_with_its_answer(tmp_path):
    d = mkdesk(tmp_path)
    send(d, entry(), seq=4)
    names = [e["event"] for e in events(d)]
    assert names.index("lab_event") < names.index("lab_round") < names.index("placed") < names.index("lab_event_done")
    ahead, done = events(d, "lab_event")[0], events(d, "lab_event_done")[0]
    assert (ahead["strategy"], ahead["seq"], ahead["date"], ahead["mark"]) == (LAB, 4, DATE, MARK)
    assert ahead["intents"] == [entry()] and ahead["state"]["last_price"] == 100.0
    assert (done["seq"], done["entries"], done["untaken"], done["dead"]) == (4, 1, 0, [])
    assert done["results"][0]["accounts"]["a1"]["ok"] is True


def test_a_linked_pair_is_one_round_with_two_legs_and_one_trade(tmp_path):
    d = mkdesk(tmp_path)
    out = send(d, pair())
    assert placed(d) == [("Buy", "Stop", 110.0, 105.0, 120.0, 1), ("Sell", "Stop", 90.0, 95.0, 80.0, 1)]
    assert [r["op"] for r in out["results"]] == ["entry", "entry", "oco"]
    assert out["results"][0]["status"] == out["results"][1]["status"] == "working"
    assert out["results"][2] == {"op": "oco", "ids": [3, 4], "refused": None}
    assert out["brain"]["entries_today"] == 1 and out["brain"]["working"] == 2      # a pair counts once
    assert d.eng.lab_rounds(LAB)[0]["iid"] == {"Buy": 3, "Sell": 4} and len(events(d, "lab_round")) == 1


def test_a_market_entry_carries_its_stop(tmp_path):
    d = mkdesk(tmp_path)
    send(d, entry(kind="market", sl=95.0, tp=110.0, ref=100.0))
    assert placed(d) == [("Buy", "Market", None, 95.0, 110.0, 1)]


def test_a_target_given_as_an_rr_goes_out_priced_and_is_re_priced_at_the_fill(tmp_path):
    d = mkdesk(tmp_path)
    send(d, entry(tp=None, tp_rr=2.0))
    assert placed(d) == [("Buy", "Stop", 110.0, 105.0, 120.0, 1)]                  # 110 + 2 x |110 - 105|
    fill_entry(d.eng, d.ads["a1"], st(d), 110.5)
    assert st(d).tp_px == 121.5                                                    # 110.5 + 2 x 5.5: the engine's law
    b = d.ld.snapshot()["strategies"][LAB]["brain"]
    assert b["orders"]["1"] == {"status": "filled", "fill_px": 110.5, "fill_sl": 105.0, "fill_tp": 121.5,
                                "fill_ms": b["orders"]["1"]["fill_ms"]}
    send(d, entry(2, kind="market", sl=95.0, tp=None, tp_rr=1.5, ref=None), seq=2)  # (refused: not flat) no leg is built
    d2 = mkdesk(tmp_path / "m", own_store=True)
    send(d2, entry(kind="market", side="short", sl=104.0, tp=None, tp_rr=1.5, ref=None))
    assert placed(d2) == [("Sell", "Market", None, 104.0, 94.0, 1)]                # from the last print: 100 - 1.5 x 4


# ---------------------------------------------------------------- C3 row 1: known, kind lab
def test_an_entry_for_a_strategy_that_is_not_on_the_desk_is_refused(tmp_path):
    d = mkdesk(tmp_path, extra={"nq930": dataclasses.replace(NQ930)})
    for name in ("lab_nope", "nq930", "pp"):
        out = run(d.ld.event(body(d, [entry()], strategy=name)))
        assert refusal(out) == "That strategy is not on the Desk." and out["results"][0]["status"] == "cancelled"
    assert placed(d) == [] and set(d.ld._days) <= {LAB} and "lab_nope" not in d.ld._locks
    assert [e["text"] for e in events(d, "lab_refused")] == ["That strategy is not on the Desk."] * 3
    assert run(d.ld.event(body(d, [{"op": "cancel", "id": 1}, {"op": "flatten", "reason": "x"}], strategy="lab_nope")))["ok"]


# ---------------------------------------------------------------- C3 row 2: the mark and the date
def test_an_order_made_for_another_promotion_or_another_day_is_out_of_date(tmp_path):
    d = mkdesk(tmp_path)
    for over in ({"mark": ["cd", MARK[1]]}, {"mark": [MARK[0], "2026-10-10T08:00:00+00:00"]}, {"date": "2026-09-13"},
                 {"date": "2026-09-15"}):
        out = run(d.ld.event({**body(d, [entry()]), **over}))
        assert refusal(out) == "This order is out of date.", over
    assert placed(d) == []
    assert send(d, entry())["results"][0]["status"] == "working"                   # ... and the right one goes


def test_the_mark_must_be_the_sidecars_too(tmp_path):
    d = mkdesk(tmp_path)
    m = labcfg.entry(d.cfg, LAB)
    kept = m["saved"]
    for saved in ({**kept, "mark": ["cd", MARK[1]]}, None, {"unreadable": True}):
        m["saved"] = saved
        assert refusal(send(d, entry())) == "This order is out of date."
    m["saved"] = kept
    m["mark"] = ["cd", MARK[1]]                                                    # the record was promoted again
    assert refusal(send(d, entry())) == "This order is out of date." and placed(d) == []


def test_a_desk_that_does_not_own_the_store_takes_no_entry(tmp_path):
    d = mkdesk(tmp_path)
    d.cfg.__dict__["_lab_owed"] = True                                             # it holds the lock and owes its re-read
    assert refusal(send(d, entry())) == "Another Desk is running on this store."
    d.cfg.__dict__["_lab_owed"] = False
    d.cfg.__dict__["_lab_store"] = "busy"
    lease, d.cfg.__dict__["_lab_lease"] = d.cfg.__dict__["_lab_lease"], None       # another desk holds it
    assert refusal(send(d, entry(), seq=2)) == "Another Desk is running on this store."
    d.cfg.__dict__["_lab_store"] = "unknown"                                       # the lock could not even be tried
    assert refusal(send(d, entry(), seq=3)) == "The Desk cannot check this order."
    assert placed(d) == []
    d.cfg.__dict__["_lab_lease"], d.cfg.__dict__["_lab_store"] = lease, "owner"
    assert send(d, entry(), seq=4)["results"][0]["status"] == "working"


def test_an_entry_with_no_account_booked_is_out_of_date(tmp_path):
    d = mkdesk(tmp_path, qty=0)
    out = send(d, entry())
    assert refusal(out) == "This order is out of date." and out["results"][0]["accounts"] == {}
    assert placed(d) == []


# ---------------------------------------------------------------- C3 row 3: the rate limit
def test_the_sixth_entry_request_in_a_second_is_refused_and_nothing_is_applied(tmp_path):
    d = mkdesk(tmp_path)
    mono = d.ld._mono = Mono()
    for i in range(1, 6):
        send(d, entry(i), seq=i)
    with pytest.raises(Refused) as e:
        send(d, entry(6), seq=6)
    assert (str(e.value), e.value.status) == ("Too many orders at once.", 429)
    assert [x["seq"] for x in events(d, "lab_event")] == [1, 2, 3, 4, 5]           # nothing of it was written or applied
    assert d.ld.status_view(LAB)["refused"][-1]["text"] == "Too many orders at once."
    mono.t += 1.0
    assert send(d, entry(7), seq=7)["ok"]                                          # a second later it is taken again


def test_the_rate_limit_never_stops_an_exit(tmp_path):
    d = mkdesk(tmp_path)
    d.ld._mono = Mono()
    working(d)
    for i in range(2, 30):                                                         # exits alone are never counted
        assert send(d, {"op": "cancel", "id": 99}, seq=i)["ok"]
    d.ld._hits[LAB] = deque([d.ld._mono()] * 5)
    out = send(d, [{"op": "cancel", "id": 1}, entry(2)], seq=30)                   # over the limit, with an exit in it
    assert out["results"][0]["accounts"]["a1"]["state"] == "cancelled" and st(d).exit_reason == "cancelled"
    assert refusal(out, 1) == "Too many orders at once." and len(placed(d)) == 1


# ---------------------------------------------------------------- C3 row 4: seq
def test_a_seq_already_answered_gets_the_same_answer_and_nothing_is_applied_twice(tmp_path):
    d = mkdesk(tmp_path)
    first = send(d, entry(), seq=7)
    again = send(d, entry(), seq=7)
    assert again["results"] == first["results"] and len(placed(d)) == 1 and len(events(d, "lab_event")) == 1
    fill_entry(d.eng, d.ads["a1"], st(d), 110.25)
    one = send(d, {"op": "flatten", "reason": "time"}, seq=8)
    two = send(d, {"op": "flatten", "reason": "time"}, seq=8)                      # the runner's retry
    assert one["results"] == two["results"] and len(d.ads["a1"].orders) == 1       # ONE close order
    assert two["brain"]["flat"] is False                                           # the brain is the one of now
    assert d.ld.snapshot()["strategies"][LAB]["answered"] == [7, 8]


def test_an_earlier_seq_the_desk_never_answered_carries_no_entry(tmp_path):
    d = mkdesk(tmp_path)
    send(d, {"op": "cancel", "id": 9}, seq=10)
    out = send(d, [entry(), {"op": "cancel", "id": 9}], seq=5)
    assert refusal(out) == "This order is out of date." and placed(d) == []
    assert out["results"][1]["refused"] is None                                    # its exit is still applied
    assert send(d, entry(), seq=11)["results"][0]["status"] == "working"


# ---------------------------------------------------------------- C3 row 5: write-ahead
def test_an_entry_that_cannot_be_written_down_is_not_sent_and_an_exit_still_is(tmp_path):
    d = mkdesk(tmp_path)
    working(d)
    real = d.eng.journal

    def full(event, **kw):
        if event == "lab_event":
            raise OSError(28, "No space left on device")
        return real(event, **kw)
    d.eng.journal = full
    out = send(d, [{"op": "cancel", "id": 1}, entry(2)], seq=2)
    assert refusal(out, 1) == "The Desk could not write this trade down. Nothing was sent."
    assert out["results"][0]["accounts"]["a1"]["state"] == "cancelled" and len(placed(d)) == 1


# ---------------------------------------------------------------- C3 row 6: off, killed, stopped, no limits
def test_an_entry_is_refused_while_the_strategy_is_off(tmp_path):
    d = mkdesk(tmp_path, enabled=False)
    assert refusal(send(d, entry())) == "It is off." and placed(d) == []
    labcfg.set_enabled(d.cfg, LAB, True)
    assert send(d, entry(), seq=2)["results"][0]["status"] == "working"


def test_an_entry_is_refused_once_the_strategy_was_killed_today(tmp_path):
    d = mkdesk(tmp_path)
    d.eng.kill_today(LAB)
    assert refusal(send(d, entry())) == "Killed today." and placed(d) == []


def test_an_entry_is_refused_once_the_strategy_was_stopped_today(tmp_path):
    d = mkdesk(tmp_path)
    send(d, {"op": "stop", "why": "Strategy error: boom", "flatten": False})
    assert refusal(send(d, entry(), seq=2)) == "Stopped for today." and placed(d) == []


def test_an_entry_is_refused_until_the_limits_are_set(tmp_path):
    d = mkdesk(tmp_path, limits=None)
    d.cfg.book[LAB] = [{"account": "a1", "qty": 1}]                                # (a book with no limits cannot be saved)
    labcfg.entry(d.cfg, LAB)["saved"] = {"mark": MARK, "limits": None, "book": []}
    assert refusal(send(d, entry())) == "Set the limits first."
    labcfg.entry(d.cfg, LAB)["frozen"] = True                                      # limits on disk that do not read
    assert refusal(send(d, entry(), seq=2)) == "The Desk cannot read its limits."
    assert placed(d) == []


def test_a_disarmed_desk_writes_the_entry_down_and_sends_nothing(tmp_path):
    d = mkdesk(tmp_path, armed=False)
    out = send(d, entry())
    assert refusal(out) == "The desk is disarmed: written down only." and out["results"][0]["status"] == "cancelled"
    assert placed(d) == [] and len(events(d, "dry_run")) == 1 and d.ld._rec(LAB)["untaken"] == 0
    assert out["brain"]["orders"] == {"1": {"status": "cancelled"}} and out["brain"]["entries_today"] == 0


# ---------------------------------------------------------------- C3 row 7: the door, once per booked account
def test_the_door_says_what_it_said_in_shadow(tmp_path):
    d = mkdesk(tmp_path)
    cases = [(entry(sl=None), door.NO_STOP), (entry(sl=115.0), door.WRONG_SIDE), (entry(own_qty=True), door.OWN_SIZE),
             (entry(kind="limit", price=95.0, sl=90.0, tp=None), door.NO_LIMIT),
             (entry(sl=90.0), "Stop too far: $400 at risk, limit $300.")]
    for n, (it, sentence) in enumerate(cases, 1):
        out = send(d, it, seq=n)
        assert refusal(out) == sentence and out["results"][0]["accounts"] == {"a1": {"ok": False, "round": None, "reason": sentence}}
    out = send(d, [entry(3), entry(4, side="short", price=90.0, sl=95.0, tp=80.0), {"op": "oco", "ids": [3, 9]}], seq=9)
    assert out["results"][2]["refused"] == door.NOT_A_PAIR
    assert placed(d) == [("Buy", "Stop", 110.0, 105.0, 120.0, 1)]                  # the first lone entry took the slot
    assert refusal(out, 1) == door.ONE_AT_A_TIME


def test_one_position_at_a_time(tmp_path):
    d = mkdesk(tmp_path)
    working(d)
    assert refusal(send(d, entry(2), seq=2)) == door.ONE_AT_A_TIME                 # an entry is working
    fill_entry(d.eng, d.ads["a1"], st(d), 110.25)
    assert refusal(send(d, entry(3), seq=3)) == door.ONE_AT_A_TIME                 # in a position
    fill_exit(d.eng, d.ads["a1"], st(d), 120.0, "tp")
    assert st(d).status == "done"
    # out, its orders not read ended yet: no account takes it, and the words are the engine's (fix round 1, I6)
    assert refusal(send(d, entry(4), seq=4)) == "The Desk cannot check the last trade's orders."
    tick(d)
    assert d.eng.lab_rounds(LAB)[0]["clean"] is True
    assert send(d, entry(5), seq=5)["results"][0]["status"] == "working"           # clean: the next round


def test_a_block_carried_from_an_earlier_day_is_that_accounts_business_only(tmp_path):
    d = mkdesk(tmp_path, accounts=("a1", "a2"))
    d.eng.lab_open(LAB)
    assert d.eng._lab_carry_make((LAB, "a1"), {"date": "2026-09-11", "status": "live", "orders": []}, DATE)
    out = send(d, entry())
    assert out["results"][0]["status"] == "working" and placed(d, "a2") and placed(d, "a1") == []
    assert out["results"][0]["accounts"]["a1"] == {"ok": False, "round": None,
                                                   "reason": "The Desk cannot check the last trade's orders."}
    assert out["brain"]["entries_today"] == 1
    assert [(r["account"], r["carried"]) for r in d.ld.snapshot()["strategies"][LAB]["rounds"]] == [("a1", True), ("a2", False)]


def test_too_late_for_a_new_trade(tmp_path):
    d = mkdesk(tmp_path)
    d.clock.set_et(11, 1)
    assert refusal(send(d, entry())) == door.TOO_LATE and placed(d) == []
    d.clock.set_et(9, 20)                                                          # before its session
    assert refusal(send(d, entry(), seq=2)) == door.TOO_LATE


def test_the_risk_cap_is_judged_with_each_accounts_own_size(tmp_path):
    d = mkdesk(tmp_path, accounts=("a1", "a2"))
    run(d.ld.set_book(LAB, [{"account": "a1", "qty": 1}, {"account": "a2", "qty": 2}]))
    out = send(d, entry(sl=102.0))                                                 # 8 pts: $160 on one, $320 on two
    assert out["results"][0]["status"] == "working" and out["results"][0]["refused"] is None
    assert out["results"][0]["accounts"] == {"a1": {"ok": True, "round": 1, "reason": None},
                                             "a2": {"ok": False, "round": None, "reason": "Stop too far: $320 at risk, limit $300."}}
    assert len(placed(d, "a1")) == 1 and placed(d, "a2") == []
    assert [(e["account"], e["text"]) for e in events(d, "lab_refused")] == [("a2", "Stop too far: $320 at risk, limit $300.")]


def test_prices_are_judged_by_the_desks_own_clock(tmp_path):
    d = mkdesk(tmp_path)
    assert refusal(send(d, entry(), late=True)) == door.PRICES_LATE
    assert refusal(send(d, entry(), seq=2, age_ms=31_000)) == door.PRICES_LATE     # the last print is 31 s old
    assert refusal(send(d, entry(), seq=3, age_ms=-6_000)) == door.PRICES_LATE     # ... or stamped ahead of the desk
    b = body(d, [entry()], seq=4)
    b["state"]["last_ms"] = None
    assert refusal(run(d.ld.event(b))) == door.PRICES_LATE
    assert placed(d) == []
    assert send(d, entry(), seq=5, age_ms=29_000)["results"][0]["status"] == "working"


def test_the_daily_limit_counts_the_desks_own_trades(tmp_path):
    d = mkdesk(tmp_path, limits={**LIMITS, "max_trades_day": 2})
    for n in (1, 2):
        working(d, seq=10 * n, iid=n)
        send(d, {"op": "cancel", "id": n}, seq=10 * n + 1)
        tick(d)
    assert d.ld._rec(LAB)["entries"] == 2
    assert refusal(send(d, entry(3), seq=30)) == "Daily limit reached (2 trades)." and len(placed(d)) == 2


# ---------------------------------------------------------------- C3 row 8: the size cap, the price already past
def test_a_size_above_the_cap_is_refused_on_that_account(tmp_path):
    d = mkdesk(tmp_path, accounts=("a1", "a2"))
    d.cfg.book[LAB] = [{"account": "a1", "qty": 3}, {"account": "a2", "qty": 2}]   # (the book's own check keeps this out)
    out = send(d, entry(sl=108.0))
    assert out["results"][0]["accounts"]["a1"] == {"ok": False, "round": None, "reason": "Size is capped at 2 here."}
    assert placed(d, "a1") == [] and [q[5] for q in placed(d, "a2")] == [2]


@pytest.mark.parametrize("it,last,past", [
    (entry(price=110.0), 109.75, False), (entry(price=110.0), 110.0, True), (entry(price=110.0), 110.25, True),
    (entry(side="short", price=90.0, sl=95.0, tp=80.0), 90.25, False),
    (entry(side="short", price=90.0, sl=95.0, tp=80.0), 90.0, True),
    (entry(side="short", price=90.0, sl=95.0, tp=80.0), 89.75, True),
])
def test_a_stop_entry_the_market_is_already_through_is_refused(tmp_path, it, last, past):      # ruling Q6
    d = mkdesk(tmp_path)
    out = send(d, it, last=last)
    assert refusal(out) == ("The price is already past this entry." if past else None)
    assert len(placed(d)) == (0 if past else 1)


@pytest.mark.parametrize("last", [110.5, 89.5])                                    # the buy leg's turn, then the sell leg's
def test_a_pair_with_one_leg_already_through_sends_neither(tmp_path, last):
    d = mkdesk(tmp_path)
    out = send(d, pair(buy=110.0, sell=90.0), last=last)
    assert refusal(out, 0) == refusal(out, 1) == "The price is already past this entry." and placed(d) == []
    assert out["results"][2]["refused"] is None
    assert out["results"][0]["accounts"] == out["results"][1]["accounts"] == {
        "a1": {"ok": False, "round": None, "reason": "The price is already past this entry."}}


# ---------------------------------------------------------------- C3 row 9: the 9:30 orders go first (ruling Q5)
def hold_clock(d):
    """The hold's waits, without waiting: each poll moves the desk's monotonic clock AND the engine's clock."""
    mono, slept = Mono(), []

    async def sleep(s):
        slept.append(s)
        mono.t += s
        d.clock.dt += dt.timedelta(seconds=s)
        for fn in list(d.on_poll):
            fn(len(slept))
    d.on_poll = []
    d.ld._mono, d.ld._sleep = mono, sleep
    return slept


def test_an_entry_waits_for_the_930_orders_acks_and_then_goes(tmp_path):
    d = mkdesk(tmp_path, extra={"nq930": dataclasses.replace(NQ930, self_fire=False)})
    slept = hold_clock(d)
    bot = d.eng._state("nq930", "a1")
    bot.status = "placing"
    d.on_poll.append(lambda n: n == 10 and setattr(bot, "status", "placed"))       # the acks land 200 ms later
    out = send(d, entry())
    assert out["results"][0]["status"] == "working" and len(placed(d)) == 1
    assert slept == [0.02] * 10


def test_an_entry_is_refused_when_the_930_orders_are_still_placing_after_two_seconds(tmp_path):
    d = mkdesk(tmp_path, extra={"nq930": dataclasses.replace(NQ930, self_fire=False)})
    slept = hold_clock(d)
    d.eng._state("nq930", "a1").status = "placing"
    out = send(d, entry())
    assert refusal(out) == "The 9:30 orders go first." and placed(d) == []
    assert 1.98 <= sum(slept) <= 2.02 and set(slept) == {0.02}                     # 2 s at most, polled every 20 ms
    assert d.ld._rec(LAB)["untaken"] == 0 and d.ld._rec(LAB)["entries"] == 0


def test_an_exit_never_waits_for_the_930_orders(tmp_path):
    d = mkdesk(tmp_path, extra={"nq930": dataclasses.replace(NQ930, self_fire=False)})
    working(d)
    slept = hold_clock(d)
    d.eng._state("nq930", "a1").status = "placing"
    out = send(d, [{"op": "cancel", "id": 1}], seq=2)
    assert out["results"][0]["accounts"]["a1"]["state"] == "cancelled" and slept == []


def at(d, hh, mm, ss, ms=0):
    d.clock.dt = dt.datetime(2026, 9, 14, hh + 4, mm, ss, ms * 1000, tzinfo=UTC)


def test_an_entry_in_the_two_seconds_before_a_timer_fire_is_held(tmp_path):
    d = mkdesk(tmp_path, extra={"nq930": dataclasses.replace(NQ930)})                                   # an enabled, self-firing straddle
    slept = hold_clock(d)
    at(d, 9, 29, 57, 900)
    assert d.ld._near_fire(d.eng.now_et()) is False
    at(d, 9, 29, 58, 0)                                                            # 2 s before: the wait runs out
    out = send(d, entry())
    assert refusal(out) == "The 9:30 orders go first." and placed(d) == [] and 1.98 <= sum(slept) <= 2.02
    del slept[:]
    at(d, 9, 29, 59, 200)                                                          # 0.8 s before the fire
    out = send(d, entry(2), seq=2)
    assert out["results"][0]["status"] == "working"                                # held until just after it, then sent
    assert 1.28 <= sum(slept) <= 1.34 and len(placed(d)) == 1


def test_what_counts_as_a_timer_fire(tmp_path):
    d = mkdesk(tmp_path, extra={"nq930": dataclasses.replace(NQ930)})
    near = lambda: d.ld._near_fire(d.eng.now_et())                                 # noqa: E731
    at(d, 9, 29, 59)
    assert near() is True
    d.cfg.strategies["nq930"] = dataclasses.replace(NQ930, enabled=False)
    assert near() is False                                                         # off: it will not fire
    d.cfg.strategies["nq930"] = dataclasses.replace(NQ930, self_fire=False)
    assert near() is False                                                         # nothing of the desk fires it
    d.cfg.strategies["nq930"] = dataclasses.replace(NQ930, only_dates=["2026-09-15"])
    assert near() is False                                                         # an event-day strategy, another day
    d.cfg.strategies["nq930"] = dataclasses.replace(NQ930, fire_et="08:30:00")
    assert near() is False
    at(d, 8, 29, 58, 500)
    assert near() is True                                                          # ... its own fire time
    d.cfg.strategies["nq930"] = dataclasses.replace(NQ930, kind="levels", fire_et="08:30:00")
    assert near() is True                                                          # the levels timer's too
    d.clock.dt = dt.datetime(2026, 9, 19, 12, 29, 59, tzinfo=UTC)                  # a Saturday
    d.cfg.strategies["nq930"] = dataclasses.replace(NQ930)
    assert near() is False
    at(d, 9, 29, 59)
    del d.cfg.strategies["nq930"]
    assert near() is False                                                         # the Lab strategy itself is not one


def test_a_switch_off_during_the_wait_stops_the_entry(tmp_path):
    d = mkdesk(tmp_path, extra={"nq930": dataclasses.replace(NQ930, self_fire=False)})
    hold_clock(d)
    bot = d.eng._state("nq930", "a1")
    bot.status = "placing"

    def flip(n):
        if n == 5:
            d.ld._rec(LAB)["stopped"] = "off"
            bot.status = "placed"
    d.on_poll.append(flip)
    assert refusal(send(d, entry())) == "Stopped for today." and placed(d) == []


# ---------------------------------------------------------------- C3 row 10: applied in call order
def test_cancel_cancels_the_unfilled_entry(tmp_path):
    d = mkdesk(tmp_path)
    working(d)
    out = send(d, {"op": "cancel", "id": 1}, seq=2)
    assert out["results"] == [{"op": "cancel", "id": 1, "refused": None, "accounts": {
        "a1": {"ok": True, "state": "cancelled", "actions": out["results"][0]["accounts"]["a1"]["actions"]}}}]
    assert d.ads["a1"].cancelled[0] == st(d).upper_id and (st(d).status, st(d).exit_reason) == ("done", "cancelled")
    assert out["brain"] == {"flat": True, "working": 0, "entries_today": 1, "orders": {"1": {"status": "cancelled"}}}


def test_flatten_closes_the_strategys_own_position_and_no_more(tmp_path):
    d = mkdesk(tmp_path)
    live(d)
    d.ads["a1"].net = 3                                                            # 2 more, opened by hand
    out = send(d, {"op": "flatten", "reason": "time"}, seq=2)
    assert out["results"][0]["accounts"]["a1"]["sold"] == 1
    assert [(o.side, o.qty, o.order_type, o.text) for o in d.ads["a1"].orders] == [("Sell", 1, "Market", "homebase:lab-flat")]
    send(d, {"op": "flatten", "reason": "time"}, seq=3)                            # a second one sends nothing
    assert len(d.ads["a1"].orders) == 1 and d.ads["a1"].flatten_calls == 0


def test_a_flatten_and_an_entry_in_one_event_are_applied_in_call_order(tmp_path):
    d = mkdesk(tmp_path)
    live(d)
    out = send(d, [{"op": "flatten", "reason": "flip"}, entry(2, side="short", price=90.0, sl=95.0, tp=80.0)], seq=2)
    assert out["results"][0]["accounts"]["a1"]["sold"] == 1
    assert refusal(out, 1) == door.ONE_AT_A_TIME and len(placed(d)) == 1           # judged on the state BEFORE the event


def test_the_engines_answer_for_each_account_is_that_accounts_sentence(tmp_path):
    d = mkdesk(tmp_path, accounts=("a1", "a2", "a3", "a4", "a5"))
    d.ads["a1"]._connected = False
    d.ads["a2"].net = 2
    d.ads["a3"].net_error = True
    d.eng.book("a4").locked = "day_lock"
    out = send(d, entry())
    got = {a: r["reason"] for a, r in out["results"][0]["accounts"].items()}
    assert got == {"a1": "The account is not connected.", "a2": "The account already holds NQ. Check it.",
                   "a3": "The Desk cannot read this account's position.", "a4": "This account is stopped for the day.",
                   "a5": None}
    assert out["results"][0]["status"] == "working" and out["results"][0]["refused"] is None
    assert [len(placed(d, a)) for a in d.ads] == [0, 0, 0, 0, 1]
    assert sorted((e["account"], e["text"]) for e in events(d, "lab_refused")) == sorted(
        (a, s) for a, s in got.items() if s)


def test_an_account_with_a_take_rule_or_another_strategy_in_the_market_sits_out(tmp_path):
    d = mkdesk(tmp_path, accounts=("a1", "a2", "a3"))
    d.cfg.strategies["lv"] = StrategyCfg(symbol="ES", kind="levels", qty=1, offset_pts=1, sl_pts=1, tp_pts=1,
                                         enabled=True, day_take=500.0)
    d.cfg.book["lv"] = [{"account": "a1", "qty": 1}]
    d.cfg.strategies["mnq"] = StrategyCfg(symbol="MNQ", qty=1, offset_pts=1, sl_pts=1, tp_pts=1, enabled=False)
    d.cfg.book["mnq"] = [{"account": "a2", "qty": 1}]
    out = send(d, entry())
    got = {a: r["reason"] for a, r in out["results"][0]["accounts"].items()}
    assert got == {"a1": "This account has a daily take rule. A Lab strategy cannot share it.",
                   "a2": "Another strategy trades MNQ on this account.", "a3": None}


def test_an_entry_the_broker_refused_shows_its_words_and_no_account_holds_it(tmp_path):
    d = mkdesk(tmp_path)
    d.ads["a1"].reject = "Insufficient margin"
    out = send(d, entry())
    assert out["results"][0] == {"op": "entry", "id": 1, "status": "cancelled", "refused": "The Desk cannot check this order.",
                                 "accounts": {"a1": {"ok": False, "round": 1, "reason": "The Desk cannot check this order.",
                                                     "detail": "The broker refused it: Insufficient margin"}}}
    assert out["brain"]["orders"] == {"1": {"status": "cancelled"}}
    assert out["brain"]["entries_today"] == 1                                      # it reached a broker call: counted, once
    assert (d.ld._rec(LAB)["entries"], d.ld._rec(LAB)["untaken"]) == (1, 1)


def test_an_entry_no_account_took_is_cancelled_to_the_strategy(tmp_path):
    d = mkdesk(tmp_path)
    d.ads["a1"]._connected = False
    out = send(d, entry())
    assert (out["results"][0]["status"], refusal(out)) == ("cancelled", "The account is not connected.")
    assert out["brain"] == {"flat": True, "working": 0, "entries_today": 0, "orders": {"1": {"status": "cancelled"}}}
    assert d.ld.snapshot()["strategies"][LAB]["brain"]["orders"] == {"1": {"status": "cancelled"}}   # the stream says so too


def test_one_intent_that_raises_never_stops_the_exit_after_it(tmp_path):
    d = mkdesk(tmp_path)
    live(d)

    async def boom(*a, **k):
        raise RuntimeError("cancel blew up")
    d.eng.lab_cancel = boom
    out = send(d, [{"op": "cancel", "id": 1}, {"op": "flatten", "reason": "x"}], seq=2)
    assert "cancel blew up" in out["results"][0]["error"] and out["results"][1]["accounts"]["a1"]["sold"] == 1
    assert events(d, "lab_event_error")[0]["op"] == "cancel"


def test_an_engine_error_on_an_entry_is_fail_closed_and_stays_with_its_strategy(tmp_path):
    d = mkdesk(tmp_path)

    async def boom(*a, **k):
        raise RuntimeError("enter blew up")
    real, d.eng.lab_enter = d.eng.lab_enter, boom
    out = send(d, entry())
    assert (out["results"][0]["status"], refusal(out)) == ("cancelled", "The Desk cannot check this order.")
    assert d.ld._rec(LAB)["entries"] == 1                                          # unknown outcome: counted
    d.eng.lab_enter = real
    run(d.eng.clock_tick())                                                        # the engine's clock is untouched
    assert events(d, "clock_error") == []


# ---------------------------------------------------------------- exits are applied in EVERY desk state
STATES = {"off": "It is off.", "killed": "Killed today.", "stopped": "Stopped for today.",
          "disarmed": door.ONE_AT_A_TIME, "not ready": "The Desk cannot check this order.",
          "mark changed": "This order is out of date.", "limits unreadable": "The Desk cannot read its limits.",
          "rate limited": "Too many orders at once.", "record gone": "It is off."}


def into(d, state) -> dict:
    """Put the desk in one of the states an entry is refused in. -> what to change in the event's body."""
    m = labcfg.entry(d.cfg, LAB)
    if state == "off":
        labcfg.set_enabled(d.cfg, LAB, False)
    elif state == "killed":
        d.eng.kill_today(LAB)
    elif state == "stopped":
        d.ld._rec(LAB)["stopped"] = "Strategy error: boom"
    elif state == "disarmed":
        d.cfg.armed = False
    elif state == "not ready":
        d.ld.close()
    elif state == "mark changed":
        return {"mark": ["cd", "2026-10-10T08:00:00+00:00"]}
    elif state == "limits unreadable":
        m["limits"], m["frozen"] = None, True
    elif state == "rate limited":
        d.ld._hits[LAB] = deque([d.ld._mono()] * 5)
    elif state == "record gone":
        m["gone"] = True
        d.cfg.strategies[LAB] = dataclasses.replace(d.cfg.strategies[LAB], enabled=False)
    return {}


@pytest.mark.parametrize("state", list(STATES))
def test_a_cancel_is_applied_in_every_desk_state_and_the_entry_beside_it_is_not(tmp_path, state):
    d = mkdesk(tmp_path)
    d.ld._mono = Mono()
    working(d)
    over = into(d, state)
    out = run(d.ld.event({**body(d, [{"op": "cancel", "id": 1}, entry(2)], seq=2), **over}))
    assert out["results"][0]["accounts"]["a1"]["state"] == "cancelled", state
    assert st(d).upper_id in d.ads["a1"].cancelled and (st(d).status, st(d).exit_reason) == ("done", "cancelled")
    assert refusal(out, 1) == STATES[state] and len(placed(d)) == 1


@pytest.mark.parametrize("state", list(STATES))
def test_a_flatten_is_applied_in_every_desk_state(tmp_path, state):
    d = mkdesk(tmp_path)
    d.ld._mono = Mono()
    live(d)
    over = into(d, state)
    out = run(d.ld.event({**body(d, [{"op": "flatten", "reason": "time"}, entry(2)], seq=2), **over}))
    assert out["results"][0]["accounts"]["a1"]["sold"] == 1, state
    assert [(o.side, o.qty, o.text) for o in d.ads["a1"].orders] == [("Sell", 1, "homebase:lab-flat")]
    assert out["results"][1]["status"] == "cancelled" and len(placed(d)) == 1


@pytest.mark.parametrize("state", list(STATES))
def test_a_stop_is_applied_in_every_desk_state(tmp_path, state):
    d = mkdesk(tmp_path)
    d.ld._mono = Mono()
    live(d)
    over = into(d, state)
    out = run(d.ld.event({**body(d, [{"op": "stop", "why": "Too slow: no answer in 1 s.", "flatten": True}], seq=2), **over}))
    assert out["results"][0]["accounts"]["a1"]["sold"] == 1, state
    assert len(d.ads["a1"].orders) == 1 and d.ld._rec(LAB)["stopped"] is not None


# ---------------------------------------------------------------- stop
def test_a_stop_with_flatten_closes_the_trade_at_once_and_stops_the_day(tmp_path):
    d = mkdesk(tmp_path)
    live(d)
    out = send(d, {"op": "stop", "why": "Strategy error: boom", "flatten": True}, seq=2)
    assert out["results"][0]["accounts"]["a1"]["sold"] == 1
    assert [(o.side, o.qty, o.text) for o in d.ads["a1"].orders] == [("Sell", 1, "homebase:lab-flat")]
    fill_exit(d.eng, d.ads["a1"], st(d), 109.0, "market")
    assert (st(d).status, st(d).exit_reason) == ("done", "stopped")
    line = events(d, "lab_stopped")[0]
    assert (line["strategy"], line["why"], line["flatten"], line["cause"], line["first"]) == \
        (LAB, "Strategy error: boom", True, "runner", True)
    snap = d.ld.snapshot()["strategies"][LAB]
    assert snap["stopped"] == "Strategy error: boom"
    send(d, {"op": "stop", "why": "again", "flatten": True}, seq=3)                # one close order per round, ever
    assert len(d.ads["a1"].orders) == 1 and d.ld._rec(LAB)["stopped"] == "Strategy error: boom"


def test_a_stop_without_flatten_cancels_the_entries_and_leaves_the_position_on_its_stop(tmp_path):
    d = mkdesk(tmp_path)
    live(d)
    out = send(d, {"op": "stop", "why": "off", "flatten": False}, seq=2)
    assert d.ads["a1"].orders == [] and st(d).status == "live"                     # never a market order
    assert out["results"][0]["accounts"]["a1"]["state"] == "filled"
    d2 = mkdesk(tmp_path / "w", own_store=True)
    working(d2)
    send(d2, {"op": "stop", "why": "off", "flatten": False}, seq=2)
    assert (st(d2).status, st(d2).exit_reason) == ("done", "cancelled")            # an unfilled entry goes


def test_the_desks_own_switch_off_cancels_unfilled_entries_and_never_raises(tmp_path):
    d = mkdesk(tmp_path)
    working(d)
    assert run(d.ld.stop(LAB, "off"))["a1"]["state"] == "cancelled"
    assert events(d, "lab_stopped")[0]["cause"] == "desk" and d.ld._rec(LAB)["stopped"] == "off"

    async def boom(*a, **k):
        raise RuntimeError("x")
    real, d.eng.lab_cancel = d.eng.lab_cancel, boom
    assert "error" in run(d.ld.stop(LAB, "off"))                                   # the engine's failure is its answer
    d.eng.lab_cancel = real
    assert run(d.ld.stop("lab_nope", "off")) == {} and run(d.ld.stop("nq930", "off")) == {}
    assert len(events(d, "lab_stopped")) == 2                                      # nothing is said of a strategy it lacks
    assert run(LabDesk(d.cfg, d.eng, d.ads, on=False).stop(LAB, "off")) == {}


# ---------------------------------------------------------------- trades a day; two no account took
def test_two_entries_no_account_took_stop_the_strategy_for_today(tmp_path):
    d = mkdesk(tmp_path)
    d.ads["a1"]._connected = False
    assert refusal(send(d, entry(1), seq=1)) == "The account is not connected."
    assert d.ld._rec(LAB)["stopped"] is None
    assert refusal(send(d, entry(2), seq=2)) == "The account is not connected."
    assert d.ld._rec(LAB)["stopped"] == "Stopped for today."
    line = events(d, "lab_stopped")[0]
    assert (line["cause"], line["flatten"], line["why"]) == ("untaken", False, "Stopped for today.")
    d.ads["a1"]._connected = True
    assert refusal(send(d, entry(3), seq=3)) == "Stopped for today." and placed(d) == []
    assert d.ld._rec(LAB)["entries"] == 0                                          # none reached a broker call


def test_an_entry_the_desk_itself_refused_is_not_one_no_account_took(tmp_path):
    d = mkdesk(tmp_path)
    for n in range(1, 5):
        assert refusal(send(d, entry(n, sl=None), seq=n)) == door.NO_STOP
    assert (d.ld._rec(LAB)["untaken"], d.ld._rec(LAB)["stopped"], d.ld._rec(LAB)["entries"]) == (0, None, 0)
    assert send(d, entry(9), seq=9)["results"][0]["status"] == "working"


def test_a_trade_counts_once_however_many_accounts_took_it(tmp_path):
    d = mkdesk(tmp_path, accounts=("a1", "a2", "a3"))
    d.ads["a2"].reject = "margin"
    out = send(d, entry())
    assert [r["round"] for r in out["results"][0]["accounts"].values()] == [1, 1, 1]
    assert d.ld._rec(LAB)["entries"] == 1 and d.ld._rec(LAB)["untaken"] == 0       # two took it


# ---------------------------------------------------------------- the counters come back from the journal
def test_a_restarted_desk_knows_todays_events_trades_and_stop(tmp_path):
    d = mkdesk(tmp_path)
    first = working(d, seq=3)
    send(d, {"op": "cancel", "id": 1}, seq=4)
    send(d, entry(2, sl=None), seq=5)
    send(d, {"op": "stop", "why": "Strategy error: boom", "flatten": False}, seq=6)
    ld2 = LabDesk(d.cfg, d.eng, d.ads)
    ld2.start()
    r = ld2._rec(LAB)
    assert (r["entries"], r["untaken"], r["stopped"], r["seq_max"], r["dead"]) == (1, 0, "Strategy error: boom", 6, [2])
    assert sorted(r["answers"]) == [3, 4, 5, 6] and [x["text"] for x in r["refused"]] == [door.NO_STOP]
    again = run(ld2.event(body(d, [entry()], seq=3)))
    assert again["results"] == first["results"] and len(placed(d)) == 1            # answered before the restart
    assert refusal(run(ld2.event(body(d, [entry(7)], seq=7)))) == "Stopped for today."
    assert ld2.status_view(LAB)["trades_today"] == 1


def test_an_event_the_desk_went_down_in_the_middle_of_is_counted_and_its_seq_is_spent(tmp_path):
    d = mkdesk(tmp_path)
    d.eng.journal("lab_event", strategy=LAB, seq=9, date=DATE, mark=MARK, counted=True, t_ns=1, state={}, intents=[entry(5)])
    d.eng.journal("lab_event", strategy=LAB, seq=10, date=DATE, mark=MARK, counted=True, t_ns=1, state={},
                  intents=[{"op": "cancel", "id": 5}])
    ld2 = LabDesk(d.cfg, d.eng, d.ads)
    ld2.start()
    assert (ld2._rec(LAB)["entries"], ld2._rec(LAB)["seq_max"], sorted(ld2._rec(LAB)["answers"])) == (1, 10, [])
    assert refusal(run(ld2.event(body(d, [entry(5)], seq=9)))) == "This order is out of date."
    assert run(ld2.event(body(d, [{"op": "cancel", "id": 5}], seq=10)))["ok"] and placed(d) == []


def test_yesterdays_lines_and_other_desks_lines_are_not_todays(tmp_path):
    d = mkdesk(tmp_path)
    working(d)
    send(d, {"op": "stop", "why": "x", "flatten": False}, seq=2)
    d.clock.dt += dt.timedelta(days=1)
    ld2 = LabDesk(d.cfg, d.eng, d.ads)
    ld2.start()
    r = ld2._rec(LAB)
    assert (r["entries"], r["stopped"], dict(r["answers"]), r["date"]) == (0, None, {}, "2026-09-15")
    (tmp_path / "journal.jsonl").write_text("not json\n[1]\n" + '{"event": "lab_event_done", "et": 5}\n')
    LabDesk(d.cfg, d.eng, d.ads).start()                                           # a journal that does not read: no crash


# ---------------------------------------------------------------- the heartbeat (design C4)
def beat(d, **named):
    return d.ld.heartbeat({"pid": 77, "strategies": named or {LAB: {"state": "running", "why": None, "mode": "desk"}}})


def test_the_heartbeat_answers_the_switches_of_the_strategies_on_this_desk(tmp_path):
    d = mkdesk(tmp_path)
    assert beat(d) == {"ok": True, "armed": True, "strategies": {LAB: {"enabled": True, "killed": False, "stopped": None}}}
    d.eng.kill_today(LAB)
    d.cfg.armed = False
    send(d, {"op": "stop", "why": "Strategy error: boom", "flatten": False})
    got = beat(d, **{LAB: {"state": "stopped", "why": "x", "mode": "desk"}, "lab_other": {}, "nq930": {}})
    assert got == {"ok": True, "armed": False,
                   "strategies": {LAB: {"enabled": True, "killed": True, "stopped": "Strategy error: boom"}}}
    for junk in (None, [], {"pid": 1}, {"pid": "1", "strategies": {}}, {"pid": True, "strategies": {}},
                 {"pid": 1, "strategies": []}):
        with pytest.raises(ValueError):
            d.ld.heartbeat(junk)
    with pytest.raises(Refused):
        LabDesk(d.cfg, d.eng, d.ads, on=False).heartbeat({"pid": 1, "strategies": {}})


def test_twenty_seconds_without_a_beat_cancel_the_unfilled_entries_once(tmp_path):
    d = mkdesk(tmp_path)
    mono = d.ld._mono = Mono()
    d.ld._t0 = mono.t
    working(d)
    beat(d)
    mono.t += 19.9
    run(d.ld._runner_rule())
    assert d.ads["a1"].cancelled == [] and events(d, "lab_runner_down") == []
    mono.t += 0.2
    run(d.ld._runner_rule())
    assert d.ads["a1"].cancelled[0] == st(d).upper_id and (st(d).status, st(d).exit_reason) == ("done", "cancelled")
    line = events(d, "lab_runner_down")
    assert len(line) == 1 and line[0]["strategy"] == LAB and line[0]["results"]["a1"]["state"] == "cancelled"
    sent = list(d.ads["a1"].cancelled)
    mono.t += 60
    run(d.ld._runner_rule())
    assert len(events(d, "lab_runner_down")) == 1 and d.ads["a1"].cancelled == sent         # once
    assert events(d, "lab_cancelled")[0]["why"] == "runner_down"


def test_a_dead_runner_never_flattens_the_position_keeps_its_stop(tmp_path):
    d = mkdesk(tmp_path)
    mono = d.ld._mono = Mono()
    d.ld._t0 = mono.t
    live(d)
    mono.t += 25
    run(d.ld._runner_rule())
    assert len(events(d, "lab_runner_down")) == 1
    assert d.ads["a1"].orders == [] and st(d).status == "live"                     # no market order: never a flatten
    assert d.ads["a1"].order_status[f"{st(d).upper_id}-sl"] == "Working"           # its broker stop is still there
    assert d.ld.status_view(LAB)["state"] == "runner_down"
    assert beat(d)["ok"] and len(events(d, "lab_runner_back")) == 1
    assert d.ld.status_view(LAB)["state"] == "in_position"
    beat(d)
    assert len(events(d, "lab_runner_back")) == 1


def test_the_twenty_seconds_count_from_the_desks_start_and_only_with_a_round_open(tmp_path):
    d = mkdesk(tmp_path)
    mono = d.ld._mono = Mono()
    d.ld._t0 = mono.t
    mono.t += 100
    run(d.ld._runner_rule())
    assert events(d, "lab_runner_down") == []                                      # no round open: nothing to cancel
    working(d)
    run(d.ld._runner_rule())                                                       # no beat since the start, 100 s ago
    assert len(events(d, "lab_runner_down")) == 1 and st(d).exit_reason == "cancelled"


def test_the_rule_never_waits_for_an_event_that_is_being_applied(tmp_path):
    d = mkdesk(tmp_path)
    mono = d.ld._mono = Mono()
    d.ld._t0 = mono.t
    working(d)
    mono.t += 30

    async def go():
        async with d.ld._lock(LAB):
            await asyncio.wait_for(d.ld._runner_rule(), 1)                         # it comes back at once
            assert d.ld._alive(LAB)["down"] is False and d.ads["a1"].cancelled == []
        await d.ld._runner_rule()
        assert d.ld._alive(LAB)["down"] is True
    run(go())


# ---------------------------------------------------------------- the stream (design C5, D7)
def drain(q):
    return [q.get_nowait() for _ in range(q.qsize())]


def test_every_change_is_published_as_that_strategys_whole_snapshot(tmp_path):
    d = mkdesk(tmp_path)
    q = d.ld.subscribe()
    assert d.ld.publish_changed() is True and [e for e, _ in drain(q)] == ["strategy"]
    assert d.ld.publish_changed() is False and drain(q) == []                      # nothing changed: nothing sent
    working(d)                                                                     # right after the intake action
    (name, snap), = drain(q)
    assert name == "strategy" and snap == d.ld.snapshot()["strategies"][LAB]
    assert set(snap) == {"strategy", "mark", "date", "enabled", "armed", "killed", "stopped", "brain", "rounds", "answered"}
    assert set(snap["rounds"][0]) == {"account", "round", "status", "date", "carried", "iid", "qty", "entry_side",
                                      "entry_qty", "entry_fill", "exit_qty", "exit_fill", "exit_reason", "sl", "tp",
                                      "pnl", "clean", "entry_ms", "exit_ms", "why"}
    fill_entry(d.eng, d.ads["a1"], st(d), 110.25)                                  # a fill: found by the 0.25 s pass
    run(d.ld._intake_tick())
    (_, snap), = drain(q)
    assert snap["brain"]["orders"]["1"]["status"] == "filled" and snap["brain"]["flat"] is False
    json.dumps(snap)                                                               # it goes over the wire as it is
    d.ld.unsubscribe(q)
    d.cfg.armed = False
    assert d.ld.publish_changed() is False                                         # nobody listens: nothing is built


def test_a_slow_reader_is_dropped_and_the_intake_still_answers(tmp_path, monkeypatch):
    monkeypatch.setattr(labdesk, "SUB_QUEUE_MAX", 3)
    d = mkdesk(tmp_path)
    slow, quick = d.ld.subscribe(), d.ld.subscribe()
    for n in range(1, 6):
        assert send(d, {"op": "cancel", "id": n}, seq=n)["ok"]                     # never waits for a reader
        drain(quick)
    assert drain(slow) == [(None, None)] and slow not in d.ld._subs and quick in d.ld._subs
    assert send(d, entry(), seq=9)["results"][0]["status"] == "working"


def test_nothing_is_published_while_the_930_orders_are_placing(tmp_path):
    d = mkdesk(tmp_path, extra={"nq930": dataclasses.replace(NQ930, self_fire=False)})
    q = d.ld.subscribe()
    d.ld.publish_changed()
    drain(q)
    bot = d.eng._state("nq930", "a1")
    bot.status = "placing"
    assert d.ld.held() is True
    send(d, {"op": "cancel", "id": 1})
    d.cfg.armed = False
    run(d.ld._intake_tick())
    assert drain(q) == []
    bot.status = "placed"
    run(d.ld._intake_tick())
    assert [e for e, _ in drain(q)] == ["strategy"]                                # the level, once the acks are in
    d.eng._state(LAB, "a1").status = "placing"                                     # a Lab round placing holds nothing
    assert d.ld.held() is False


def test_a_strategy_that_leaves_the_desk_is_said_with_a_whole_state(tmp_path):
    d = mkdesk(tmp_path, qty=0)
    q = d.ld.subscribe()
    d.ld.publish_changed()
    drain(q)
    run(d.ld.remove(LAB))
    assert d.ld.publish_changed() is True
    (name, snap), = drain(q)
    assert name == "state" and snap["strategies"] == {} and snap["date"] == DATE


# ---------------------------------------------------------------- run(): the Lab call and the publish step
def test_run_makes_a_lab_call_for_every_strategy_also_while_the_views_are_paused(tmp_path):
    d = mkdesk(tmp_path)
    d.ld._paused = lambda: True                                                    # the refresh's disk part is skipped
    calls, real = [], d.eng.lab_open
    d.eng.lab_open = lambda name: (calls.append(name), real(name))[1]
    q = d.ld.subscribe()

    async def go():
        t = asyncio.create_task(d.ld.run(interval_s=0.01, publish_s=0.005))
        await asyncio.sleep(0.08)
        t.cancel()
    run(go())
    assert len(calls) >= 3 and set(calls) == {LAB}
    assert [e for e, _ in drain(q)] == ["strategy"]                                # ... and the stream was fed
    assert events(d, "lab_refresh_error") == [] and events(d, "lab_intake_error") == []


def test_the_first_lab_call_is_made_at_the_start(tmp_path):
    d = mkdesk(tmp_path, start=False)
    calls, real = [], d.eng.lab_open
    d.eng.lab_open = lambda name: (calls.append(name), real(name))[1]
    assert events(d, "lab_side") == []
    d.ld.start()
    assert calls == [LAB]                                                          # the engine rolls its Lab day at a Lab call
    assert (tmp_path / f"labday-{DATE}.json").exists()
    assert [e["on"] for e in events(d, "lab_side")] == [True]


def test_an_error_in_the_publish_step_is_said_once_and_never_ends_the_task(tmp_path):
    d = mkdesk(tmp_path)
    d.ld.subscribe()
    d.eng.lab_rounds = None                                                        # the snapshot cannot be built

    async def boom():
        raise RuntimeError("rule blew up")
    d.ld._runner_rule = boom

    async def go():
        t = asyncio.create_task(d.ld.run(interval_s=0.005, publish_s=0.005))
        await asyncio.sleep(0.05)
        assert not t.done()
        t.cancel()
    run(go())
    errs = events(d, "lab_intake_error")
    assert len(errs) == 1 and "rule blew up" in errs[0]["error"]


# ---------------------------------------------------------------- the start lines and the readiness line
def orphan_desk(tmp_path, status="live", note="", on=False):
    """A desk whose day file holds a Lab round and whose config holds no such strategy."""
    from homebase.config import AccountCfg, AppCfg
    clock = Clock()
    clock.set_et(10, 0)
    cfg = AppCfg(armed=True, accounts={"a1": AccountCfg(keyring_key="k", account_name="A1")}, book={}, strategies={})
    eng = Engine(cfg, {"a1": FakeAdapter("a1")}, now_fn=clock, root=tmp_path)
    eng.states[f"{LAB}@a1"] = DayState(strategy=LAB, account="a1", date=DATE, status=status, qty=1, note=note)
    return LabDesk(cfg, eng, eng.adapters, on=on), cfg, eng


LINE = {"level": "bad", "label": "Lab strategies", "detail": "A Lab trade is open but its strategy is not on this Desk. Check it."}


@pytest.mark.parametrize("on", [False, True])
def test_a_lab_round_open_with_no_strategy_on_the_desk_is_said(tmp_path, on):
    ld, cfg, eng = orphan_desk(tmp_path, on=on)
    ld.start()
    ld.start()
    said = journal(tmp_path, "lab_open_without_cfg")
    assert len(said) == 1 and (said[0]["strategy"], said[0]["account"], said[0]["status"], said[0]["lab_side"]) == (LAB, "a1", "live", on)
    assert labdesk.orphan_line(cfg, eng) == LINE
    now = eng.now_et()
    assert [c for c in compute_readiness(now, cfg, eng, {}, None, None, None)["checks"] if c["label"] == "Lab strategies"] == [LINE]
    eng.states[f"{LAB}@a2"] = DayState(strategy=LAB, account="a2", date=DATE, status="placed", qty=1)
    assert compute_readiness(now, cfg, eng, {}, None, None, None)["checks"].count(LINE) == 1      # ONE line, however many
    assert compute_readiness(now, cfg, eng, {}, None, None, None)["ready"] is False


@pytest.mark.parametrize("status,note,open_", [("placing", "", True), ("placed", "", True), ("live", "", True),
                                               ("error", labdesk.PLACING_UNKNOWN, True), ("error", "entry: no", False),
                                               ("done", "", False), ("idle", "", False)])
def test_which_rounds_are_open(tmp_path, status, note, open_):
    ld, cfg, eng = orphan_desk(tmp_path, status, note)
    assert (labdesk.orphan_line(cfg, eng) == LINE) is open_
    ld.start()
    assert len(journal(tmp_path, "lab_open_without_cfg")) == (1 if open_ else 0)
    assert journal(tmp_path, "lab_side") == []                                     # an OFF desk journals no other Lab line


def test_no_line_for_a_round_of_a_strategy_the_desk_knows_or_of_another_day_or_kind(tmp_path):
    d = mkdesk(tmp_path)
    live(d)
    assert labdesk.orphan_line(d.cfg, d.eng) is None and events(d, "lab_open_without_cfg") == []
    ld, cfg, eng = orphan_desk(tmp_path / "o")
    eng.states[f"{LAB}@a1"].date = "2026-09-11"
    eng.states["nq930@a1"] = DayState(strategy="nq930", account="a1", date=DATE, status="live")
    assert labdesk.orphan_line(cfg, eng) is None
    eng.states = None                                                              # whatever breaks: no line, no raise
    assert labdesk.orphan_line(cfg, eng) is None


# ---------------------------------------------------------------- check_book: the take rule (ruling B2 Q-B)
def test_a_lab_strategy_cannot_be_booked_on_an_account_with_a_daily_take_rule(tmp_path):
    lv = StrategyCfg(symbol="ES", kind="levels", qty=1, offset_pts=1, sl_pts=1, tp_pts=1, enabled=True, day_take=500.0)
    tt = StrategyCfg(symbol="GC", kind="levels", qty=1, offset_pts=1, sl_pts=1, tp_pts=1, enabled=True, target_take=True)
    d = mkdesk(tmp_path, accounts=("a1", "a2", "a3"), qty=0, extra={"lv": lv, "tt": tt},
               book={"lv": [{"account": "a1", "qty": 1}], "tt": [{"account": "a2", "qty": 1}]})
    for a in ("a1", "a2"):
        with pytest.raises(Refused) as e:
            run(d.ld.set_book(LAB, [{"account": a, "qty": 1}]))
        assert str(e.value) == "This account has a daily take rule. A Lab strategy cannot share it." and e.value.status == 409
    assert LAB not in d.cfg.book
    run(d.ld.set_book(LAB, [{"account": "a3", "qty": 1}]))                         # no take rule there
    d.cfg.strategies["lv"].enabled = False                                         # a rule that is off is not in force
    run(d.ld.set_book(LAB, [{"account": "a1", "qty": 1}, {"account": "a3", "qty": 1}]))
    d.ld.check_book("lv", [{"account": "a1", "qty": 2}])                           # the other strategies' books: as before


# ---------------------------------------------------------------- the status block's intake fields
def test_the_status_block_shows_trades_refusals_and_what_the_runner_says(tmp_path):
    d = mkdesk(tmp_path)
    d.ld._mono = Mono()
    v = d.ld.status_view(LAB)       # booked, and no runner has named it to this Desk yet (final wave G1)
    assert (v["state"], v["why"], v["trades_today"], v["mode_today"], v["refused"]) == \
        ("runner_down", "The runner is not connected to the Desk.", 0, None, [])
    beat(d)
    v = d.ld.status_view(LAB)
    assert (v["state"], v["mode_today"]) == ("watching", "desk")
    send(d, entry(sl=None))
    working(d, seq=2)
    v = d.ld.status_view(LAB)
    assert (v["state"], v["trades_today"]) == ("working", 1)
    assert v["refused"] == [{"t": "10:00:00", "text": door.NO_STOP, "account": None}]
    send(d, {"op": "cancel", "id": 1}, seq=3)
    tick(d)
    beat(d, **{LAB: {"state": "done", "why": None, "mode": "desk"}})
    assert d.ld.status_view(LAB)["state"] == "done"
    beat(d, **{LAB: {"state": "stopped", "why": "Strategy error: boom", "mode": "desk"}})
    assert (d.ld.status_view(LAB)["state"], d.ld.status_view(LAB)["why"]) == ("stopped", "Strategy error: boom")
    d.ld._mono.t += 21                                                             # its beat is old: what it said is too
    v = d.ld.status_view(LAB)
    assert (v["state"], v["mode_today"]) == ("waiting", None)
    send(d, {"op": "stop", "why": "Too slow: no answer in 1 s.", "flatten": False}, seq=4)
    v = d.ld.status_view(LAB)
    assert (v["state"], v["why"]) == ("stopped", "Too slow: no answer in 1 s.")


# ---------------------------------------------------------------- the Lab side off
def test_with_the_lab_side_off_nothing_of_the_intake_is_reachable(tmp_path):
    d = mkdesk(tmp_path)
    off = LabDesk(d.cfg, d.eng, d.ads, on=False)
    with pytest.raises(Refused) as e:
        run(off.event(body(d, [entry()])))
    assert (str(e.value), e.value.status) == ("Lab strategies are switched off on this Desk.", 409)
    with pytest.raises(Refused):
        run(off.clear_block(LAB, "a1"))
    assert off.snapshot()["strategies"] == {} and off.publish_changed() is False
    assert run(asyncio.wait_for(off.run(), 1)) is None and placed(d) == []
