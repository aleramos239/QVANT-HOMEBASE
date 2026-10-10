"""The would-be fills: the tester's fill law fed tick by tick must give the tester's own trades.

The three traps of a tape that is still arriving (an order's first eligible print, a flat with no print yet, the end
of the tape), each against run_session on the whole day; then the rest of the object."""
from __future__ import annotations

import datetime as dt
from array import array

from homebase.backtest.engine import Costs, run_session
from homebase.backtest.tape import Tape, et_ns
from homebase.labrun.shadowfills import ShadowFills
from homebase.strategies.base import Strategy

D = dt.date(2024, 3, 5)
MS = 1_000_000
KEYS = ("side", "qty", "entry_ns", "entry_price", "exit_ns", "exit_price", "exit_reason", "net")


def at(hms: str, ms: int = 0) -> int:
    return et_ns(D, hms) + ms * MS


def tape(rows, root="NQ") -> Tape:
    return Tape(root, D, "X", array("q", [r[0] for r in rows]), array("d", [r[1] for r in rows]),
                array("i", [r[2] for r in rows]), {"h": 0.0, "l": 0.0, "c": 0.0})


def cls_of(source: str) -> type:
    """The one Strategy subclass a draft's text defines, loaded here for the tester's side of a comparison."""
    ns: dict = {}
    exec(compile(source, "<case>", "exec"), ns)
    (cls,) = [v for v in ns.values() if isinstance(v, type) and issubclass(v, Strategy) and v is not Strategy]
    return cls


def cut(trades) -> list:
    return [tuple(t[k] for k in KEYS) for t in trades]


def whole_day(strategy, rows, root="NQ") -> list:
    """The tester's trades for the whole day."""
    return cut(t.to_dict() for t in run_session(strategy, tape(rows, root), Costs()).trades)


def entry(i, kind, side, price, sl=None, tp=None, tp_rr=None, ref=None, move=False, qty=1) -> dict:
    return {"op": "entry", "id": i, "kind": kind, "side": side, "price": price, "qty": qty, "own_qty": False,
            "sl": sl, "tp": tp, "tp_rr": tp_rr, "ref": price if ref is None and kind != "market" else ref, "move": move}


def event(f: ShadowFills, t_ns: int, intents) -> None:
    """One event as the host runs it: the prints before it, the clock, the strategy's orders."""
    f.advance_to(t_ns)
    f.now(t_ns)
    f.apply(intents)


class BuyStop(Strategy):
    """A buy stop at 110 placed at 09:30:00, flat at 15:55."""
    id, name, root = "t", "T", "NQ"

    def times(self):
        return ["09:30:00", "15:55"]

    def on_time(self, ctx, et_time):
        if et_time == "09:30:00":
            ctx.stop_entry("long", 110.0, sl=100.0, tp=130.0)
        else:
            ctx.flatten("time")


# ---------------------------------------------------------------- trap 1: the first eligible print is decided by TIME
def test_an_order_waits_for_the_first_print_after_its_placement_time_not_the_next_print_to_arrive():
    rows = [(at("09:29:59"), 105.0, 1),
            (at("09:30:00", 10), 111.0, 1),        # through the stop, but 10 ms after the event: the order is not live yet
            (at("09:30:00", 50), 105.0, 1),
            (at("09:30:00", 90), 112.0, 1),        # the first print at or after 09:30:00.085
            (at("09:30:05"), 131.0, 1)]
    f = ShadowFills("NQ", D, Costs(), 85)
    f.add_ticks(rows[:1])
    event(f, at("09:30:00"), [entry(1, "stop", "long", 110.0, sl=100.0, tp=130.0)])
    f.advance_all()
    assert f.updates() == []
    f.add_ticks(rows[1:2])                         # the next print to arrive
    f.advance_all()
    assert f.flat and f.updates() == []
    f.add_ticks(rows[2:3])
    f.advance_all()
    assert f.flat
    f.add_ticks(rows[3:4])
    f.advance_all()
    assert not f.flat
    assert f.updates() == [{"id": 1, "status": "filled", "fill_px": 112.25, "fill_sl": 100.0, "fill_tp": 130.0,
                            "fill_ms": at("09:30:00", 90) // MS}]
    f.add_ticks(rows[4:])
    f.finish()
    assert cut(f.trades()) == whole_day(BuyStop(), rows)
    assert cut(f.trades())[0][2:4] == (at("09:30:00", 90), 112.25)


def test_the_placement_time_holds_when_the_later_prints_are_already_held():
    """A batch that runs past the event: the same answer as when they come one by one."""
    rows = [(at("09:29:59"), 105.0, 1), (at("09:30:00", 10), 111.0, 1), (at("09:30:00", 90), 112.0, 1),
            (at("09:30:05"), 131.0, 1)]
    f = ShadowFills("NQ", D, Costs(), 85)
    f.add_ticks(rows)
    event(f, at("09:30:00"), [entry(1, "stop", "long", 110.0, sl=100.0, tp=130.0)])
    f.finish()
    assert cut(f.trades()) == whole_day(BuyStop(), rows)


# ---------------------------------------------------------------- trap 2: a flat whose print has not arrived
def test_a_flat_reads_true_at_once_and_is_priced_on_the_first_print_at_or_after_its_time():
    rows = [(at("09:29:59"), 105.0, 1), (at("09:30:01"), 110.0, 1), (at("15:54:50"), 118.0, 1),
            (at("15:55:02"), 120.0, 1), (at("15:55:03"), 90.0, 1)]
    f = ShadowFills("NQ", D, Costs(), 85)
    f.add_ticks(rows[:1])
    event(f, at("09:30:00"), [entry(1, "stop", "long", 110.0, sl=100.0, tp=130.0)])
    f.add_ticks(rows[1:3])
    f.advance_all()
    assert not f.flat
    event(f, at("15:55:00"), [{"op": "flatten", "reason": "time"}])     # no print at or after 15:55:00 has arrived
    assert f.flat and f.trades() == []
    f.advance_all()
    assert f.flat and f.trades() == []
    f.add_ticks(rows[3:])
    f.advance_all()
    (t,) = f.trades()
    assert (t["exit_ns"], t["exit_price"], t["exit_reason"]) == (at("15:55:02"), 119.75, "time")
    f.finish()
    assert cut(f.trades()) == whole_day(BuyStop(), rows)


def test_a_flat_whose_print_never_comes_closes_on_the_last_print_as_eod():
    rows = [(at("09:29:59"), 105.0, 1), (at("09:30:01"), 110.0, 1), (at("15:54:50"), 118.0, 1)]
    f = ShadowFills("NQ", D, Costs(), 85)
    f.add_ticks(rows[:1])
    event(f, at("09:30:00"), [entry(1, "stop", "long", 110.0, sl=100.0, tp=130.0)])
    f.add_ticks(rows[1:])
    event(f, at("15:55:00"), [{"op": "flatten", "reason": "time"}])
    assert f.flat and f.trades() == []
    f.finish()
    (t,) = f.trades()
    assert (t["exit_ns"], t["exit_price"], t["exit_reason"]) == (at("15:54:50"), 117.75, "eod")
    assert cut(f.trades()) == whole_day(BuyStop(), rows)


class Reverse(Strategy):
    """Long at 09:30; at 10:00 flat and short at once (no placement delay): both on the first print at or after 10:00."""
    id, name, root = "r", "R", "NQ"
    placement_ms = 0

    def times(self):
        return ["09:30:00", "10:00:00"]

    def on_time(self, ctx, et_time):
        if et_time == "09:30:00":
            ctx.market("long", sl=50.0)
        else:
            ctx.flatten("time")
            ctx.market("short", sl=150.0)


def test_a_waiting_flat_closes_before_an_order_of_the_same_event_fills_on_that_print():
    rows = [(at("09:29:59"), 105.0, 1), (at("09:30:01"), 106.0, 1), (at("10:00:03"), 108.0, 1),
            (at("10:00:04"), 109.0, 1)]
    f = ShadowFills("NQ", D, Costs(), 0)
    f.add_ticks(rows[:1])
    event(f, at("09:30:00"), [entry(1, "market", "long", None, sl=50.0)])
    f.add_ticks(rows[1:2])
    event(f, at("10:00:00"), [{"op": "flatten", "reason": "time"}, entry(2, "market", "short", None, sl=150.0)])
    assert f.flat
    f.add_ticks(rows[2:])
    f.finish()
    got = cut(f.trades())
    assert got == whole_day(Reverse(), rows)
    assert [t[0] for t in got] == ["long", "short"] and got[0][4] == got[1][2] == at("10:00:03")


# ---------------------------------------------------------------- trap 3: the end of the tape is not a fixed number
def test_prints_that_arrive_after_the_object_was_made_fill_orders_and_price_a_flat():
    rows = [(at("09:29:59"), 105.0, 1), (at("09:30:01"), 110.0, 1), (at("15:54:50"), 118.0, 1),
            (at("15:55:02"), 120.0, 1), (at("15:58:00"), 125.0, 1)]
    f = ShadowFills("NQ", D, Costs(), 85)            # made with no print at all
    assert f.last_price() is None and f.flat
    f.add_ticks(rows[:1])
    f.advance_all()
    event(f, at("09:30:00"), [entry(1, "stop", "long", 110.0, sl=100.0, tp=130.0)])
    for r in rows[1:3]:
        f.add_ticks([r])
        f.advance_all()
    assert not f.flat and f.last_price() == 118.0
    f.add_ticks(rows[3:])                            # the print at 15:55:02 is here: the flat is priced on it, not on
    event(f, at("15:55:00"), [{"op": "flatten", "reason": "time"}])     # the tape's last print
    (t,) = f.trades()
    assert (t["exit_ns"], t["exit_price"], t["exit_reason"]) == (at("15:55:02"), 119.75, "time")
    f.finish()
    assert cut(f.trades()) == whole_day(BuyStop(), rows)


# ---------------------------------------------------------------- the rest of the object
def test_last_price_is_the_last_print_strictly_before_the_event():
    f = ShadowFills("NQ", D, Costs(), 85)
    f.add_ticks([(at("09:29:59"), 105.0, 1), (at("09:30:00"), 106.0, 1), (at("09:30:01"), 107.0, 1)])
    f.advance_to(at("09:30:00"))
    assert f.last_price() == 105.0
    f.advance_to(at("09:30:01"))
    assert f.last_price() == 106.0


def test_an_older_print_is_dropped_so_the_tape_stays_in_time_order():
    f = ShadowFills("NQ", D, Costs(), 85)
    f.add_ticks([(at("09:30:00"), 105.0, 1), (at("09:29:59"), 99.0, 1), (at("09:30:00"), 106.0, 2)])
    assert list(f.ts) == [at("09:30:00")] * 2 and list(f.px) == [105.0, 106.0] and list(f.size) == [1, 2]


def test_an_oco_pair_one_fills_the_other_is_cancelled_and_both_are_reported_once():
    f = ShadowFills("NQ", D, Costs(), 85)
    f.add_ticks([(at("09:29:59"), 105.0, 1)])
    event(f, at("09:30:00"), [entry(1, "stop", "long", 110.0, sl=105.0, tp=120.0, move=True),
                              entry(2, "stop", "short", 100.0, sl=105.0, tp=90.0, move=True),
                              {"op": "oco", "ids": [1, 2]}])
    f.add_ticks([(at("09:30:01"), 111.0, 1)])        # gaps a point through the buy stop: the bracket moves with the fill
    f.advance_all()
    assert f.updates() == [
        {"id": 1, "status": "filled", "fill_px": 111.25, "fill_sl": 106.25, "fill_tp": 121.25,
         "fill_ms": at("09:30:01") // MS},
        {"id": 2, "status": "cancelled", "fill_px": None, "fill_sl": None, "fill_tp": None, "fill_ms": None}]
    assert f.updates() == []


def test_a_cancel_or_an_oco_naming_an_unknown_id_is_ignored():
    f = ShadowFills("NQ", D, Costs(), 85)
    f.add_ticks([(at("09:29:59"), 105.0, 1)])
    event(f, at("09:30:00"), [entry(1, "stop", "long", 110.0, sl=105.0), {"op": "cancel", "id": 9},
                              {"op": "oco", "ids": [1, 7]}, {"op": "cancel", "id": 1}, {"op": "cancel", "id": 1}])
    assert f.updates() == [{"id": 1, "status": "cancelled", "fill_px": None, "fill_sl": None, "fill_tp": None,
                            "fill_ms": None}]
    f.add_ticks([(at("09:30:01"), 111.0, 1)])
    f.finish()
    assert f.trades() == []


def test_plot_hline_and_skip_go_to_the_result():
    f = ShadowFills("NQ", D, Costs(), 85)
    event(f, at("09:30:00"), [{"op": "plot", "name": "vwap", "t_ms": 5, "value": 1.5},
                              {"op": "hline", "name": "anchor", "price": 105.0, "role": "anchor", "t_ms": 7},
                              {"op": "skip", "reason": "below VWAP"}])
    f.finish(at("16:00"))
    assert f.result.plots == {"vwap": [[5, 1.5]]} and f.result.skip == "below VWAP"
    assert f.result.hlines == [{"name": "anchor", "price": 105.0, "date": "2024-03-05", "role": "anchor", "t_ms": 7,
                                "end_ms": at("16:00") // MS}]


class OffTick(Strategy):
    """A stop entry whose price is off the tick grid, brackets re-priced to the fill: the move is measured from the
    price the strategy sent (ref), not from the snapped one. Half a tick off is where the two answers part."""
    id, name, root = "o", "O", "NQ"

    def times(self):
        return ["09:30:00"]

    def on_time(self, ctx, et_time):
        ctx.move_brackets_to_fill = True
        ctx.stop_entry("long", 110.125, sl=105.25, tp=115.0)


def test_the_bracket_moves_by_the_distance_to_the_price_the_strategy_sent():
    rows = [(at("09:29:59"), 105.0, 1), (at("09:30:01"), 110.25, 1), (at("09:30:02"), 105.75, 1),
            (at("09:30:03"), 105.5, 1)]
    f = ShadowFills("NQ", D, Costs(), 85)
    f.add_ticks(rows)
    event(f, at("09:30:00"), [entry(1, "stop", "long", 110.0, sl=105.25, tp=115.0, ref=110.125, move=True)])
    f.finish()
    want = whole_day(OffTick(), rows)
    assert cut(f.trades()) == want and want[0][4:7] == (at("09:30:03"), 105.25, "sl")


def test_crash_cancels_every_order_and_flattens_at_the_current_print():
    f = ShadowFills("NQ", D, Costs(), 85)
    f.add_ticks([(at("09:29:59"), 105.0, 1)])
    event(f, at("09:30:00"), [entry(1, "market", "long", None, sl=50.0)])
    f.add_ticks([(at("09:30:01"), 106.0, 1), (at("09:31:00"), 108.0, 1), (at("09:31:05"), 109.0, 1)])
    event(f, at("09:31:00"), [entry(2, "stop", "long", 120.0, sl=110.0)])
    f.crash()
    (t,) = f.trades()
    assert (t["exit_ns"], t["exit_price"], t["exit_reason"]) == (at("09:31:00"), 107.75, "strategy error")
    assert f.flat and {u["id"]: u["status"] for u in f.updates()} == {1: "filled", 2: "cancelled"}
    f.advance_all()
    assert len(f.trades()) == 1


def test_crash_with_no_print_at_the_event_closes_on_the_last_print_held():
    f = ShadowFills("NQ", D, Costs(), 85)
    f.add_ticks([(at("09:29:59"), 105.0, 1)])
    event(f, at("09:30:00"), [entry(1, "market", "long", None, sl=50.0)])
    f.add_ticks([(at("09:30:01"), 106.0, 1)])
    f.advance_to(at("09:31:00"))
    f.now(at("09:31:00"))
    f.crash()
    (t,) = f.trades()
    assert (t["exit_ns"], t["exit_price"]) == (at("09:30:01"), 105.75) and f.flat

