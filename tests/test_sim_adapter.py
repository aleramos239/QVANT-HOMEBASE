"""Step B (B5): the simulated broker account of the practice Desk (tools/sim_adapter.py). Every fill below is decided
by the tester's own fill law on scripted prints; the first test holds the adapter's fills equal to the runner's shadow
fills (labrun/shadowfills.py) print for print. No network, no service, every folder a tmp_path."""
from __future__ import annotations

import asyncio
import datetime as dt
import inspect
import json

import pytest

from homebase.backtest.engine import Costs
from homebase.backtest.tape import ET
from homebase.broker.base import BrokerAdapter, OrderRequest
from homebase.engine import TERMINAL, WORKING
from homebase.labrun.shadowfills import ShadowFills
from tests.test_broker_paper import run
from tools.sim_adapter import Faults, SimAdapter

D = dt.date(2026, 9, 14)


def ms(hms: str, extra: int = 0) -> int:
    return int(dt.datetime.combine(D, dt.time.fromisoformat(hms), ET).timestamp() * 1000) + extra


class Acct:
    """One simulated account at 10:00:00 with a first print at 100, and the fills it told."""

    def __init__(self, tmp_path=None, **kw):
        kw.setdefault("placement_ms", 0)
        self.ad = SimAdapter("sim041", tmp_path, label="SIM 41", **kw)
        self.told = []
        run(self.ad.connect())
        run(self.ad.observe_fills(self.on_fill))
        self.t = ms("10:00:00")
        self.prints([100.0])

    async def on_fill(self, ev):
        self.told.append((ev.side, ev.qty, ev.price, ev.raw["orderId"], ev.position_after))

    def prints(self, prices, step_ms=1000):
        rows = []
        for p in prices:
            rows.append([self.t, p, 1])
            self.t += step_ms
        run(self.ad.on_ticks("NQ", rows))

    def bracket(self, side="Buy", typ="Stop", price=110.0, sl=105.0, tp=120.0, qty=1):
        return run(self.ad.place_bracket(OrderRequest(symbol="NQ", side=side, qty=qty, order_type=typ, price=price,
                                                      stop_price=sl, tp_price=tp, text="homebase:entry")))

    def state(self, oid):
        return run(self.ad.get_order_state(oid))

    def net(self):
        return run(self.ad.get_net_position("NQ"))


def ids(r):
    return r.order_id, r.raw["sl_order_id"], r.raw["tp_order_id"]


# ---------------------------------------------------------------- the law is the tester's
@pytest.mark.parametrize("kind,side,price,sl,tp,prices", [
    ("stop", "long", 110.0, 105.0, 120.0, [104.0, 110.0, 111.0, 120.0, 120.25, 119.0]),      # target, one tick through
    ("stop", "long", 110.0, 105.0, 120.0, [100.0, 112.5, 106.0, 105.0, 100.0]),              # a gap fill, then its stop
    ("stop", "short", 90.0, 95.0, 80.0, [91.0, 89.5, 94.75, 95.5]),                          # a short, stopped
    ("market", "long", None, 95.0, 104.0, [100.5, 103.0, 104.25]),
    ("market", "short", None, 104.0, None, [100.0, 101.0, 104.0]),                           # stop only, no target
])
@pytest.mark.parametrize("placement_ms", [0, 85])
def test_the_fills_are_the_shadow_fills_print_for_print(kind, side, price, sl, tp, prices, placement_ms):
    """The same order on the same prints through the runner's shadow fills and through the simulated account: the
    same entry price, the same exit price, on the same prints."""
    t0 = ms("10:00:00")
    rows = [[t0 + 40 + i * 500, p, 1] for i, p in enumerate(prices)]        # the first print 40 ms after the order
    sf = ShadowFills("NQ", D, Costs(), placement_ms)
    sf.add_ticks([(t0 * 10 ** 6 - 10 ** 9, 100.0, 1)])
    sf.advance_to(t0 * 10 ** 6)
    sf.now(t0 * 10 ** 6)
    sf.apply([{"op": "entry", "id": 1, "kind": kind, "side": side, "price": price, "qty": 1, "sl": sl, "tp": tp,
               "tp_rr": None, "ref": price, "move": False}])
    sf.add_ticks([(r[0] * 10 ** 6, r[1], r[2]) for r in rows])
    sf.advance_all()
    want = [(t["side"], t["entry_ns"], t["entry_price"], t["exit_ns"], t["exit_price"], t["exit_reason"]) for t in sf.trades()]

    ad = SimAdapter("a", None, placement_ms=placement_ms)
    told = []

    async def on_fill(ev):
        told.append((ev.side, int(round(ev.ts * 1e9)) // 10 ** 6, ev.price, ev.raw["role"]))

    async def go():
        await ad.connect()
        await ad.observe_fills(on_fill)
        await ad.on_ticks("NQ", [[t0 - 1000, 100.0, 1]])
        await ad.on_clock(t0)
        r = await ad.place_bracket(OrderRequest(
            symbol="NQ", side="Buy" if side == "long" else "Sell", qty=1, order_type="Stop" if kind == "stop" else "Market",
            price=price, stop_price=sl, tp_price=tp))
        assert r.ok
        await ad.on_ticks("NQ", rows)
    asyncio.new_event_loop().run_until_complete(go())
    assert want, "the script must make the tester trade"
    (w,) = want
    entry, exit_ = told
    assert (entry[1], entry[2]) == (w[1] // 10 ** 6, w[2]) and entry[3] == "entry"
    assert (exit_[1], exit_[2], exit_[3]) == (w[3] // 10 ** 6, w[4], w[5])
    assert entry[0] == ("Buy" if side == "long" else "Sell") and exit_[0] != entry[0]


def test_it_is_a_broker_adapter_with_every_method_the_engines_lab_paths_call():
    assert issubclass(SimAdapter, BrokerAdapter) and not getattr(SimAdapter, "__abstractmethods__", None)
    for name in ("place_bracket", "place_order", "cancel_order_by_id", "modify_order", "get_order_status",
                 "get_order_state", "get_net_position", "observe_fills", "get_metrics", "cancel_all", "flatten_all"):
        assert inspect.iscoroutinefunction(getattr(SimAdapter, name)), name
    assert SimAdapter("x").broker_key == "x" and SimAdapter("x").connected is False


# ---------------------------------------------------------------- one method at a time
def test_a_stop_entry_rests_with_its_two_legs_and_fills_at_the_trigger_plus_slippage():
    a = Acct()
    r = a.bracket()
    e, sl, tp = ids(r)
    assert r.ok and len({e, sl, tp}) == 3 and all(isinstance(i, str) for i in (e, sl, tp))
    assert a.state(e) == {"status": "Working", "filled_qty": 0}
    assert a.state(sl) == a.state(tp) == {"status": "Suspended", "filled_qty": 0}
    assert {a.state(i)["status"] for i in (e, sl, tp)} <= WORKING
    a.prints([109.75])
    assert a.told == [] and a.net() == 0
    a.prints([110.0])
    assert a.told == [("Buy", 1, 110.25, e, 1)] and a.net() == 1
    assert a.state(e) == {"status": "Filled", "filled_qty": 1}
    assert a.state(sl)["status"] == a.state(tp)["status"] == "Working"


def test_a_print_the_account_already_held_never_fills_a_new_order():
    a = Acct()
    a.prints([111.0])
    r = a.bracket()                                  # a buy stop at 110 with the last print at 111 (assumption A10)
    assert a.told == []
    a.prints([111.0])
    assert a.told == [("Buy", 1, 111.25, r.order_id, 1)]      # the market plus slippage, on the next print


def test_an_order_goes_live_after_the_placement_delay_by_the_streams_clock():
    a = Acct(placement_ms=85)
    run(a.ad.on_clock(a.t))
    r = a.bracket()
    run(a.ad.on_ticks("NQ", [[a.t + 84, 110.0, 1]]))
    assert a.told == []
    run(a.ad.on_ticks("NQ", [[a.t + 85, 110.0, 1]]))
    assert a.told == [("Buy", 1, 110.25, r.order_id, 1)]


def test_a_market_entry_with_a_stop_and_no_target():
    a = Acct()
    r = a.bracket(side="Sell", typ="Market", price=None, sl=104.0, tp=None)
    e, sl, tp = ids(r)
    assert tp is None and sl
    a.prints([100.0])
    assert a.told == [("Sell", 1, 99.75, e, -1)]
    a.prints([103.75, 104.0])
    assert a.told[-1] == ("Buy", 1, 104.25, sl, 0) and a.net() == 0
    assert a.state(sl) == {"status": "Filled", "filled_qty": 1}


def test_the_target_fills_one_tick_through_and_cancels_the_stop_and_the_other_way_round():
    a = Acct()
    e, sl, tp = ids(a.bracket())
    a.prints([110.0, 120.0])
    assert len(a.told) == 1                          # at the target is not through it
    a.prints([120.25])
    assert a.told[-1] == ("Sell", 1, 120.0, tp, 0)
    assert a.state(sl) == {"status": "Canceled", "filled_qty": None} and a.state(sl)["status"] in TERMINAL
    b = Acct()
    e, sl, tp = ids(b.bracket())
    b.prints([110.0, 105.0])
    assert b.told[-1] == ("Sell", 1, 104.75, sl, 0) and b.state(tp)["status"] == "Canceled" and b.net() == 0
    b.prints([121.0, 100.0])
    assert len(b.told) == 2                          # nothing of that bracket is left to fill


def test_the_stop_and_target_can_be_moved_before_and_after_the_fill_and_fill_where_they_were_moved_to():
    a = Acct()
    e, sl, tp = ids(a.bracket())
    assert run(a.ad.modify_order(sl, "Stop", stop_price=106.0, qty=1)).ok          # held: moved before the fill
    a.prints([110.0])
    assert run(a.ad.modify_order(sl, "Stop", stop_price=108.1, qty=1)).ok          # snapped to the tick: 108.0
    assert run(a.ad.modify_order(tp, "Limit", price=112.0, qty=1)).ok
    a.prints([108.25])
    assert len(a.told) == 1
    a.prints([108.0])
    assert a.told[-1] == ("Sell", 1, 107.75, sl, 0)
    r = run(a.ad.modify_order(tp, "Limit", price=113.0, qty=1))
    assert not r.ok and r.error == f"order {tp} is not working on SIM 41"
    b = Acct()
    e, sl, tp = ids(b.bracket(qty=2))
    assert run(b.ad.modify_order(sl, "Stop", stop_price=106.0, qty=1)).error == \
        "the simulated account moves an order's price, never its size"
    assert run(b.ad.modify_order(sl, "Stop")).error == "modify: a price is required"
    assert run(b.ad.modify_order(e, "Stop", stop_price=111.0, qty=2)).ok and b.ad.orders[e].price == 111.0   # an entry too
    m = b.bracket(typ="Market", price=None)
    assert run(b.ad.modify_order(m.order_id, "Limit", price=1.0)).error == "only Limit and Stop orders can be moved (this one is Market)"
    assert not run(b.ad.modify_order("999", "Stop", stop_price=1.0)).ok


def test_a_cancelled_entry_takes_its_legs_with_it_and_a_second_cancel_is_refused():
    a = Acct()
    e, sl, tp = ids(a.bracket())
    r = run(a.ad.cancel_order_by_id(e))
    assert r.ok and r.order_id == e
    assert a.state(e) == a.state(sl) == a.state(tp) == {"status": "Canceled", "filled_qty": None}
    again = run(a.ad.cancel_order_by_id(e))
    assert not again.ok and again.error == f"order {e} is not working on SIM 41"
    assert not run(a.ad.cancel_order_by_id(sl)).ok
    a.prints([111.0, 100.0])
    assert a.told == [] and a.net() == 0
    assert a.state("12345") == {"status": "Canceled", "filled_qty": None}          # an id it never issued (A7)


def test_with_legs_outlive_a_cancelled_entrys_legs_stay_until_each_is_cancelled():
    a = Acct()
    a.ad.faults.set({"legs_outlive": True})
    e, sl, tp = ids(a.bracket())
    assert run(a.ad.cancel_order_by_id(e)).ok
    assert a.state(sl)["status"] == a.state(tp)["status"] == "Suspended"
    a.prints([111.0, 100.0, 125.0])
    assert a.told == []                              # a held leg never fills
    assert run(a.ad.cancel_order_by_id(sl)).ok and run(a.ad.cancel_order_by_id(tp)).ok
    assert a.state(sl)["status"] == a.state(tp)["status"] == "Canceled"


def test_a_part_fill_and_the_stop_that_outlives_its_cancelled_entry():
    a = Acct()
    a.ad.faults.set({"partial_next": 1})
    e, sl, tp = ids(a.bracket(qty=2))
    a.prints([110.0])
    assert a.told == [("Buy", 1, 110.25, e, 1)] and a.ad.faults.partial_next == 0
    assert a.state(e) == {"status": "Working", "filled_qty": 1}
    assert a.ad.orders[sl].qty == 1 and a.state(sl)["status"] == "Working"
    assert run(a.ad.cancel_order_by_id(e)).ok                                       # the rest is cancelled ...
    assert a.state(e) == {"status": "Canceled", "filled_qty": 1}
    assert a.state(sl)["status"] == a.state(tp)["status"] == "Working"              # ... the contract in keeps its stop
    a.prints([111.0, 105.0])
    assert a.told[-1] == ("Sell", 1, 104.75, sl, 0) and a.net() == 0 and a.state(tp)["status"] == "Canceled"


def test_the_rest_of_a_part_fill_fills_on_a_later_print_and_the_legs_grow_with_it():
    a = Acct()
    a.ad.faults.set({"partial_next": 1})
    e, sl, tp = ids(a.bracket(qty=3))
    a.prints([110.0, 109.0])
    assert [t[1] for t in a.told] == [1] and a.net() == 1
    a.prints([110.5])
    assert a.told[-1] == ("Buy", 2, 110.75, e, 3) and a.state(e) == {"status": "Filled", "filled_qty": 3}
    assert a.ad.orders[sl].qty == a.ad.orders[tp].qty == 3
    assert run(a.ad.modify_order(sl, "Stop", stop_price=106.0, qty=3)).ok
    a.prints([106.0])
    assert a.told[-1] == ("Sell", 3, 105.75, sl, 0)


def test_a_stop_that_fills_ends_an_unfilled_rest_of_its_entry():
    a = Acct()
    a.ad.faults.set({"partial_next": 1})
    e, sl, tp = ids(a.bracket(qty=2))
    a.prints([110.0, 105.0])
    assert a.net() == 0 and a.state(e) == {"status": "Canceled", "filled_qty": 1}
    a.prints([112.0])
    assert a.net() == 0 and len(a.told) == 2


def test_a_rejected_entry_leaves_nothing_behind_and_the_next_one_goes():
    a = Acct()
    a.ad.faults.set({"reject_next": 1})
    r = a.bracket()
    assert not r.ok and r.order_id is None and r.error == "OSO rejected (no orderId returned)" and a.ad.orders == {}
    assert a.bracket().ok and a.ad.faults.reject_next == 0
    a.ad.faults.set({"reject_next": 1, "reject_words": "Insufficient margin"})
    assert a.bracket().error == "Insufficient margin"


def test_both_legs_of_a_pair_fill_when_the_fault_is_on():
    a = Acct()
    a.ad.faults.set({"fill_both": True})
    up = a.bracket(price=110.0, sl=105.0, tp=120.0)
    dn = a.bracket(side="Sell", price=90.0, sl=95.0, tp=80.0)
    a.prints([110.0])
    assert a.told == [("Buy", 1, 110.25, up.order_id, 1), ("Sell", 1, 89.75, dn.order_id, 0)]
    assert a.state(up.order_id)["status"] == a.state(dn.order_id)["status"] == "Filled"
    assert not run(a.ad.cancel_order_by_id(dn.order_id)).ok
    b = Acct()                                       # ... and without it the other entry just rests
    b.bracket()
    dn = b.bracket(side="Sell", price=90.0, sl=95.0, tp=80.0)
    b.prints([110.0])
    assert len(b.told) == 1 and b.state(dn.order_id)["status"] == "Working"


def test_the_close_is_a_plain_market_order_that_cancels_nothing():
    a = Acct()
    e, sl, tp = ids(a.bracket())
    a.prints([110.0])
    r = run(a.ad.place_order(OrderRequest(symbol="NQ", side="Sell", qty=1, order_type="Market", text="homebase:lab-flat")))
    assert r.ok and r.order_id not in (e, sl, tp)
    a.prints([111.0])
    assert a.told[-1] == ("Sell", 1, 110.75, r.order_id, 0) and a.net() == 0
    assert a.state(sl)["status"] == a.state(tp)["status"] == "Working"              # the engine cancels them itself
    assert run(a.ad.cancel_order_by_id(sl)).ok and run(a.ad.cancel_order_by_id(tp)).ok
    a.prints([100.0, 125.0])
    assert a.net() == 0


def test_the_faults_a_read_or_a_close_can_meet():
    a = Acct()
    e, sl, tp = ids(a.bracket())
    a.ad.faults.set({"order_status_unknown": sl})
    assert a.state(sl) == {"status": None, "filled_qty": None} and run(a.ad.get_order_status(sl)) is None
    assert a.state(e)["status"] == "Working"
    a.ad.faults.set({"order_status_unknown": True})
    assert a.state(e)["status"] is None
    a.ad.faults.set({"order_status_unknown": None, "position_unreadable": True, "close_refused": True})
    assert a.state(e)["status"] == "Working"
    with pytest.raises(RuntimeError, match="position unreadable"):
        a.net()
    r = run(a.ad.place_order(OrderRequest(symbol="NQ", side="Sell", qty=1, order_type="Market")))
    assert not r.ok and r.error == "order rejected (no orderId returned)" and len(a.ad.orders) == 3
    assert a.bracket(typ="Market", price=None).ok                                   # an entry is not a close
    for bad in ({"nope": 1}, {"reject_next": -1}, {"reject_next": True}, {"fill_both": 1}, {"reject_words": " "}):
        with pytest.raises(ValueError):
            Faults().set(bad)


def test_an_answer_that_comes_late_leaves_the_order_live_in_the_meantime():
    a = Acct()
    a.ad.faults.set({"ack_delay_ms": 30})

    async def go():
        place = asyncio.ensure_future(a.ad.place_bracket(OrderRequest(
            symbol="NQ", side="Buy", qty=1, order_type="Stop", price=110.0, stop_price=105.0, tp_price=120.0)))
        await asyncio.sleep(0)
        await a.ad.on_ticks("NQ", [[a.t, 110.0, 1]])
        assert not place.done() and len(a.told) == 1                                # the fill beat the answer
        return await place
    r = asyncio.new_event_loop().run_until_complete(go())
    assert r.ok and a.told == [("Buy", 1, 110.25, r.order_id, 1)]


def test_what_the_engine_does_about_a_fill_is_in_the_book_before_the_next_print():
    a = Acct()
    e, sl, tp = ids(a.bracket())

    async def on_fill(ev):                           # the engine's own reaction: the stop goes to the fill
        if ev.raw["orderId"] == e:
            assert (await a.ad.modify_order(sl, "Stop", stop_price=109.0, qty=1)).ok
        a.told.append((ev.side, ev.price))
    run(a.ad.observe_fills(on_fill))
    a.prints([110.0, 109.0, 108.0])                  # one batch: the moved stop is hit by the very next print
    assert a.told == [("Buy", 110.25), ("Sell", 108.75)]


def test_an_order_placed_while_a_print_is_worked_may_fill_on_the_next_print_of_the_same_batch():
    a = Acct()
    e, sl, tp = ids(a.bracket())
    placed = []

    async def on_fill(ev):                           # what a both-legs emergency does: a market order, in the callback
        a.told.append((ev.side, ev.price, ev.raw["orderId"]))
        if ev.raw["orderId"] == e:
            req = OrderRequest(symbol="NQ", side="Sell", qty=1, order_type="Market")
            placed.append((await a.ad.place_order(req)).order_id)
    run(a.ad.observe_fills(on_fill))
    a.prints([110.0, 111.0, 112.0])                  # one batch
    assert a.told == [("Buy", 110.25, e), ("Sell", 110.75, placed[0])] and a.net() == 0


def test_a_fill_is_told_before_the_next_order_is_tried_on_the_same_print():
    a = Acct()
    first, second = a.bracket(), a.bracket()         # two buy stops at 110: one print reaches both

    async def on_fill(ev):                           # the engine's reaction to the first: the other is cancelled
        a.told.append(ev.raw["orderId"])
        if ev.raw["orderId"] == first.order_id:
            assert (await a.ad.cancel_order_by_id(second.order_id)).ok
    run(a.ad.observe_fills(on_fill))
    a.prints([110.0, 111.0])
    assert a.told == [first.order_id] and a.net() == 1
    assert a.state(second.order_id) == {"status": "Canceled", "filled_qty": None}


def test_the_metrics_and_the_account_wide_calls():
    a = Acct()
    e, sl, tp = ids(a.bracket())
    a.prints([110.0])
    m = run(a.ad.get_metrics())
    assert m["connected"] is True and m["account"] == "SIM 41" and m["open_positions"] == [{"symbol": "NQ", "net": 1}]
    assert m["working_orders"] == 2 and m["balance"] == 50_000.0 and m["realized_pnl"] == 0.0
    assert run(a.ad.flatten_all()).ok
    a.prints([111.0])
    assert run(a.ad.cancel_all()).ok
    assert a.net() == 0 and run(a.ad.get_metrics())["working_orders"] == 0
    assert run(a.ad.get_balance()) == {"balance": 50_010.0, "realized_pnl": 10.0}  # 110.25 -> 110.75, $20 a point
    assert a.ad.book()["positions"] == {} and a.ad.book()["orders"] == []
    run(a.ad.close())
    assert a.ad.connected is False and not a.bracket().ok


# ---------------------------------------------------------------- a restart of the practice Desk
def test_the_book_comes_back_from_its_file_and_a_print_is_never_used_twice(tmp_path):
    a = Acct(tmp_path)
    e, sl, tp = ids(a.bracket())
    a.prints([110.0])
    assert json.loads((tmp_path / "sim-sim041.json").read_text())["pos"] == {"NQ": {"net": 1, "avg": 110.25}}
    seen = [[ms("10:00:00"), 100.0, 1], [ms("10:00:01"), 110.0, 1]]

    b = SimAdapter("sim041", tmp_path, label="SIM 41", placement_ms=0)
    told = []

    async def on_fill(ev):
        told.append((ev.side, ev.price))
    run(b.connect())
    run(b.observe_fills(on_fill))
    assert b.away is True and run(b.get_net_position("NQ")) == 1
    assert run(b.get_order_state(sl)) == {"status": "Working", "filled_qty": 0}
    run(b.on_ticks("NQ", seen + [[ms("10:00:02"), 105.0, 1]]))                      # the stream starts over
    assert run(b.get_net_position("NQ")) == 0 and told == []                        # filled while away: booked only
    assert run(b.get_order_state(sl))["status"] == "Filled" and len(b.fills) == 2   # ... and 110 did not fill twice
    b.back()
    r = run(b.place_bracket(OrderRequest(symbol="NQ", side="Buy", qty=1, order_type="Market", stop_price=90.0)))
    assert int(r.order_id) > int(tp)                                                # ids go on where they were
    run(b.on_ticks("NQ", [[ms("10:00:03"), 106.0, 1]]))
    assert told == [("Buy", 106.25)]


def test_after_a_restart_a_print_from_before_an_order_was_placed_never_fills_it(tmp_path):
    a = Acct(tmp_path)
    a.prints([111.0])                                # 10:00:01, before the order: it never counted for it
    a.prints([100.0])
    r = a.bracket()                                  # a buy stop at 110, resting since 10:00:02
    b = SimAdapter("sim041", tmp_path, label="SIM 41", placement_ms=0)
    run(b.connect())
    session = [[ms("10:00:00"), 100.0, 1], [ms("10:00:01"), 111.0, 1], [ms("10:00:02"), 100.0, 1]]
    run(b.on_ticks("NQ", session))                   # the stream starts over from the session's first print
    assert run(b.get_order_state(r.order_id)) == {"status": "Working", "filled_qty": 0} and b.fills == []
    run(b.on_ticks("NQ", session + [[ms("10:00:03"), 110.0, 1]]))
    assert run(b.get_order_state(r.order_id))["status"] == "Filled" and len(b.fills) == 1


def test_after_a_restart_an_old_print_never_fills_a_stop_that_was_moved_since(tmp_path):
    a = Acct(tmp_path)
    e, sl, tp = ids(a.bracket())
    a.prints([110.0, 108.0, 112.0])                  # in at 110.25; 108 was above its stop then
    assert run(a.ad.modify_order(sl, "Stop", stop_price=109.0, qty=1)).ok          # ... and the stop was raised after it
    b = SimAdapter("sim041", tmp_path, label="SIM 41", placement_ms=0)
    run(b.connect())
    t0 = ms("10:00:00")
    session = [[t0 + i * 1000, p, 1] for i, p in enumerate([100.0, 110.0, 108.0, 112.0])]
    run(b.on_ticks("NQ", session))                   # the stream starts over: 108 is history, not a new print
    assert run(b.get_net_position("NQ")) == 1 and run(b.get_order_state(sl))["status"] == "Working"
    run(b.on_ticks("NQ", [[t0 + 4000, 109.0, 1]]))
    assert run(b.get_net_position("NQ")) == 0 and b.fills[-1]["price"] == 108.75


def test_with_no_folder_nothing_is_written(tmp_path):
    a = Acct()
    a.bracket()
    a.prints([110.0])
    assert list(tmp_path.iterdir()) == [] and a.ad.away is False
