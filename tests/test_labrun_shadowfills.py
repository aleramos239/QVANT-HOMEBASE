"""The would-be fills: the tester's fill law fed tick by tick must give the tester's own trades.

First the three traps of a tape that is still arriving (an order's first eligible print, a flat with no print yet, the
end of the tape), each against run_session on the whole day. Then PARITY, the gate: whole days through the child +
LiveCtx + ShadowFills (host.run_day) equal run_session trade for trade."""
from __future__ import annotations

import datetime as dt
import json
import os
import random
import subprocess
import sys
from array import array
from pathlib import Path

import pytest

from homebase import draftstore
from homebase.backtest import sandbox
from homebase.backtest.engine import Costs, run_session
from homebase.backtest.tape import ARCHIVE, CACHE, OverlayTapeStore, Tape, TapeStore, effective_session_window, et_ns
from homebase.labrun.host import run_day
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


# ================================================================ PARITY: the gate
# A whole day through the child + LiveCtx + ShadowFills (host.run_day), prints arriving a few at a time, must give the
# trades run_session gives on the whole day: every field of every trade, in the same order.
REPO = Path(__file__).resolve().parent.parent
HEAD = "from homebase.strategies.base import Input, Strategy\n\n\n"

STRADDLE = HEAD + '''class Straddle(Strategy):
    """(a) a 09:30 OCO stop straddle, brackets re-priced to the fill, entries cancelled 12:55, flat 15:55."""
    id, name, root = "a", "A", "NQ"
    session_window = ("09:25", "16:00")

    @classmethod
    def inputs(cls):
        return [Input("off", "Offset", "float", 2.125, 0.0, 500.0, 0.005),      # half a tick off the grid
                Input("sl", "Stop", "float", 4.0, 0.05, 500.0, 0.05), Input("tp", "Target", "float", 9.0, 0.0, 500.0, 0.05)]

    def times(self):
        return ["09:30:00", "12:55", "15:55"]

    def on_session(self, ctx):
        self.legs = ()

    def on_time(self, ctx, et_time):
        if et_time == "09:30:00":
            px = ctx.last_price
            if px is None:
                ctx.skip("no print before 09:30")
                return
            up, dn = px + self.p["off"], px - self.p["off"]
            ctx.hline("anchor", px, role="anchor")
            ctx.move_brackets_to_fill = True
            a = ctx.stop_entry("long", up, sl=px - self.p["sl"], tp=px + self.p["tp"])
            b = ctx.stop_entry("short", dn, sl=px + self.p["sl"], tp=px - self.p["tp"])
            ctx.oco(a, b)
            self.legs = (a, b)
        elif et_time == "12:55":
            for o in self.legs:
                ctx.cancel(o)
        else:
            ctx.flatten("time")
'''

BARS = HEAD + '''class Bars(Strategy):
    """(b) one-minute bars: a market entry after two bars the same way while flat, out after five bars by ctx.flatten;
    what the strategy reads back from its orders (status, fill) steers it, so the updates must be the tester's too."""
    id, name, root = "b", "B", "NQ"
    session_window = ("09:30", "15:00")
    bar_minutes = 1
    placement_ms = 40

    def on_session(self, ctx):
        self.prev = self.order = None
        self.held = self.cool = 0

    def on_bar(self, ctx, bar):
        up = bar.c > bar.o
        o = self.order
        if o is not None and o.status == "filled" and not ctx.flat:
            self.held += 1
            ctx.plot("fill", bar.end_ns, o.fill_px + (o.fill_sl or 0.0) + (o.fill_ms or 0) % 1000)
            if self.held >= 5:
                ctx.flatten("bars")
                self.cool = 2
                assert ctx.flat
        elif ctx.flat:
            self.held = 0
            if self.cool:
                self.cool -= 1
            elif self.prev is not None and up == self.prev and bar.c != bar.o:
                side = "long" if up else "short"
                sl = bar.l - 1.0 if up else bar.h + 1.0
                self.order = ctx.market(side, sl=sl, tp=None if bar.v % 2 else bar.c + (8.0 if up else -8.0), ref=bar.c)
        self.prev = up
'''

TIME_EXIT = HEAD + '''class TimeExit(Strategy):
    """(c) in at a time with a stop and no target, out at a time; twice a day, the second the other way."""
    id, name, root = "c", "C", "NQ"
    session_window = ("09:25", "16:00")
    placement_ms = 0

    def times(self):
        return ["10:00:00", "11:30:00", "13:00:00", "14:00:00"]

    def on_time(self, ctx, et_time):
        px = ctx.last_price
        if et_time == "10:00:00":
            ctx.market("short", sl=px + 12.0)
        elif et_time == "13:00:00":
            ctx.flatten("reverse")
            ctx.market("long", sl=px - 12.0)
        else:
            ctx.flatten("time")
'''

RR = HEAD + '''class RR(Strategy):
    """(d) targets by tp_rr: a stop entry (re-priced to the fill) in the morning, a market entry with a ref later."""
    id, name, root = "d", "D", "NQ"
    session_window = ("09:25", "16:00")

    def times(self):
        return ["09:45:00", "12:00:00", "12:30:00", "15:30:00"]

    def on_time(self, ctx, et_time):
        px = ctx.last_price
        if et_time == "09:45:00":
            ctx.move_brackets_to_fill = True
            self.o = ctx.stop_entry("long", px + 2.125, sl=px - 3.0, tp_rr=1.5)     # half a tick off the grid
        elif et_time == "12:00:00":
            ctx.cancel(self.o)
            ctx.flatten("noon")
        elif et_time == "12:30:00":
            ctx.market("short", sl=px + 5.0, tp_rr=2, ref=px, qty=2)
        else:
            ctx.flatten("time")
'''

LIMIT = HEAD + '''class Limit(Strategy):
    """Limit entries (the Desk does not take them yet; the would-be fills still follow the tester's law)."""
    id, name, root = "e", "E", "NQ"
    session_window = ("09:25", "16:00")

    def times(self):
        return ["10:00:00", "12:00:00", "15:55"]

    def on_time(self, ctx, et_time):
        px = ctx.last_price
        if et_time == "10:00:00":
            self.o = ctx.limit_entry("long", px - 2.0, sl=px - 8.0, tp=px + 4.0)
        elif et_time == "12:00:00":
            ctx.cancel(self.o)
        else:
            ctx.flatten("time")
'''

CASES = {"straddle": STRADDLE, "bars": BARS, "time exit": TIME_EXIT, "tp_rr": RR, "limit": LIMIT}


def plain(argv, run_dir):
    """A child with no sandbox: the tests' own strategies only (never the owner's drafts)."""
    return subprocess.Popen(argv, cwd=REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            env={**os.environ, "HOMEBASE_LABRUN_UNSANDBOXED_TESTS": "1"})


ACT_AT = ("09:30:00", "09:45:00", "10:00:00", "11:30:00", "12:00:00", "12:30:00", "12:55:00", "13:00:00", "14:00:00",
          "15:30:00", "15:55:00")


def walk(seed: int, n: int = 12_000, start: str = "09:24:00", end: str = "16:02:00", px0: float = 21000.0,
         ns_noise: bool = False, burst: bool = False) -> list:
    """A synthetic NQ day: a random walk on the tick grid with prints that share a millisecond and gaps of many ticks
    (through a stop). Around the times strategies act at there is either no print for seconds, or (burst) a crowd of
    prints inside the placement delay, so an order's first eligible print is not the next one to arrive."""
    rng = random.Random(seed)
    a, b = at(start) // MS, at(end) // MS
    acts = [at(t) // MS for t in ACT_AT]
    times = [rng.randrange(a, b) for _ in range(n)]
    if burst:
        acts += [at("09:30:00") // MS + 60_000 * m for m in range(1, 90)]        # and the first bar closes
        times += [t + rng.randrange(-60, 160) for t in acts for _ in range(25)]
    else:
        times = [ms for ms in times if not any(t - 1500 <= ms < t + 2500 for t in acts)]
    rows, px = [], px0
    for ms in sorted(times):
        if rng.random() < 0.25 and rows:
            ms = rows[-1][0] // MS                               # the same millisecond as the print before
        step = rng.choice((-2, -1, -1, 0, 1, 1, 2)) * 0.25
        if rng.random() < 0.004:
            step = rng.choice((-1, 1)) * rng.randrange(20, 60) * 0.25   # a gap
        px = round(px + step, 2)
        ns = ms * MS + (rng.randrange(MS) if ns_noise else 0)
        rows.append((max(ns, rows[-1][0]) if rows else ns, px, rng.randrange(1, 9)))
    return rows


def whole_session(source: str, rows, d: dt.date = D, params=None, qty: int = 1, daily=None, as_tape=None) -> list:
    """The tester's trades for the day, as runner.execute runs a session (the half-day window included)."""
    cls = cls_of(source)
    strat = cls(params)
    strat.session_window = effective_session_window(cls.root, d, cls.session_window)
    t = as_tape if as_tape is not None else Tape(cls.root, d, "X", array("q", [r[0] for r in rows]),
                                                 array("d", [r[1] for r in rows]), array("i", [r[2] for r in rows]), {})
    res = run_session(strat, t, Costs(), qty, daily)
    assert res.skip is None or not res.skip.startswith("strategy error"), res.skip
    return [x.to_dict() for x in res.trades]


def shadow_day(source: str, rows, d: dt.date = D, params=None, qty: int = 1, daily=None, batch: int = 200,
               name: str = "lab_case") -> dict:
    record = {"name": name, "root": cls_of(source).root, "source": source, "sha256": "x", "params": params or {},
              "qty": qty}
    return run_day(record, rows, d, spawn=plain, daily=daily, batch=batch, deadline_s=5.0)


def same(got: dict, want: list) -> None:
    assert got["summary"]["state"] == "done", got["summary"]
    assert cut(got["trades"]) == cut(want)                       # the fields the gate names
    assert got["trades"] == want                                 # ... and every other one


@pytest.mark.parametrize("case", list(CASES))
@pytest.mark.parametrize("seed, ns_noise, burst", [(1, False, False), (2, True, True), (3, False, True)])
def test_parity_on_synthetic_days(case, seed, ns_noise, burst):
    rows = walk(seed, ns_noise=ns_noise, burst=burst)
    want = whole_session(CASES[case], rows)
    same(shadow_day(CASES[case], rows), want)
    TRADED[case] = TRADED.get(case, 0) + len(want)


TRADED: dict = {}


def test_the_synthetic_days_traded():
    """The parity above compared real trades, not empty lists (runs after it, in file order)."""
    if set(TRADED) == set(CASES):
        assert all(n >= 2 for n in TRADED.values()), TRADED


@pytest.mark.parametrize("case", list(CASES))
@pytest.mark.parametrize("batch", [1, 7])
def test_parity_when_the_prints_come_one_at_a_time(case, batch):
    rows = walk(4, n=2500, burst=True)
    same(shadow_day(CASES[case], rows, batch=batch), whole_session(CASES[case], rows))


@pytest.mark.parametrize("case", list(CASES))
def test_parity_on_a_day_whose_tape_stops_early(case):
    """No print at or after the last flat: the close is the last print, "eod", on both sides."""
    rows = [r for r in walk(5) if r[0] < at("13:40:00")]
    want = whole_session(CASES[case], rows)
    same(shadow_day(CASES[case], rows), want)
    if case in ("straddle", "time exit"):
        assert want and want[-1]["exit_reason"] in ("eod", "sl", "tp")


def test_parity_with_settings_and_size():
    rows = walk(6)
    params = {"off": 1.5, "sl": 3.25, "tp": 20.0}
    want = whole_session(STRADDLE, rows, params=params, qty=3)
    same(shadow_day(STRADDLE, rows, params=params, qty=3), want)
    assert want and want[0]["qty"] == 3


# ---- the owner's own drafts on real archive days: OPT-IN, read-only, and their code runs only inside the sandbox.
# ---- Without HOMEBASE_REAL_DRAFTS=1 the suite never reads ~/.homebase and never runs a draft that is not its own.
REAL_DRAFTS = "HOMEBASE_REAL_DRAFTS"
DRAFTS = Path.home() / ".homebase" / "strategies"
REAL = [("pp_orb", dt.date(2024, 3, 5)), ("pp_orb", dt.date(2025, 6, 17)),
        ("s930_nq", dt.date(2024, 3, 5)), ("s930_nq", dt.date(2024, 11, 29)),          # 11-29: a half day (13:15)
        ("nq_long_930_vwap", dt.date(2024, 3, 6)), ("nq_long_930_vwap", dt.date(2025, 6, 17))]
# The tester's side of the comparison, as whole_session runs it, in a sandboxed child: the draft is loaded there only.
TESTER = '''import datetime as dt, json, sys
out, sys.stdout = sys.stdout, sys.stderr
from homebase.backtest import drafthost
from homebase.backtest.engine import Costs, run_session
from homebase.backtest.tape import OverlayTapeStore, effective_session_window
job = json.load(sys.stdin)
d = dt.date.fromisoformat(job["date"])
cls = drafthost.register_source(job["name"], job["source"])
strat = cls(None)
strat.session_window = effective_session_window(cls.root, d, cls.session_window)
tape = OverlayTapeStore(job["archive"], job["cache"], job["private"]).load(cls.root, d)
res = run_session(strat, tape, Costs(), 1, job["daily"])
json.dump({"needs_daily": bool(strat.needs_daily()), "skip": res.skip, "trades": [t.to_dict() for t in res.trades]}, out)
'''


class Rows:
    """A tape as run_day's rows, cut on demand (a real day is a million prints)."""

    def __init__(self, t: Tape):
        self.t = t

    def __len__(self) -> int:
        return len(self.t.ts)

    def __getitem__(self, s: slice) -> list:
        return list(zip(self.t.ts[s], self.t.px[s], self.t.size[s]))


def sandboxed_tester(name: str, source: str, d: dt.date, daily: list, run_dir: Path) -> dict:
    """run_session on the archive's day in the sandbox a draft backtest runs in: {"needs_daily", "skip", "trades"}."""
    run_dir.mkdir()
    job = {"name": name, "source": source, "date": d.isoformat(), "daily": daily, "archive": str(ARCHIVE),
           "cache": str(CACHE), "private": str(run_dir / "tape")}
    prm = sandbox.params(run_dir=run_dir, archive=ARCHIVE, cache=CACHE, tmp=run_dir)
    p = subprocess.run(sandbox.command([sys.executable, "-c", TESTER], prm), input=json.dumps(job), cwd=run_dir,
                       env=sandbox.env(run_dir), capture_output=True, text=True, timeout=600)
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout)


def test_the_real_draft_cases_are_asked_for_never_run_by_default():
    """C3. The suite does not execute the owner's drafts, or read ~/.homebase, unless HOMEBASE_REAL_DRAFTS=1 says so."""
    marks = [m for m in test_parity_of_a_real_draft_on_a_real_day.pytestmark if m.name == "skipif"]
    assert [m.args[0] for m in marks] == [os.environ.get(REAL_DRAFTS) != "1"] and REAL_DRAFTS in marks[0].kwargs["reason"]
    src = Path(__file__).read_text()
    body = src[src.rindex("def test_parity_of_a_real_draft_on_a_real_day"):]
    assert "plain" not in body and "cls_of(" not in body and "whole_session(" not in body     # the sandbox, on both sides


@pytest.mark.skipif(os.environ.get(REAL_DRAFTS) != "1", reason=f"the owner's real drafts run only when asked: {REAL_DRAFTS}=1")
@pytest.mark.parametrize("name, d", REAL, ids=[f"{n} {d}" for n, d in REAL])
def test_parity_of_a_real_draft_on_a_real_day(name, d, tmp_path):
    if not sandbox.available():
        pytest.skip("the macOS sandbox is not working here: a real draft never runs outside it")
    f = DRAFTS / f"{name}.py"
    shared = TapeStore(ARCHIVE, CACHE)
    try:
        source = f.read_text(encoding="utf-8")
        root = draftstore.static_meta(source)["root"]            # read from the text: nothing of the draft runs here
        ready = shared.cached(root, d)
    except (OSError, ValueError):
        pytest.skip(f"{f} or its market's tape is not on this machine")
    if not ready:
        pytest.skip(f"no cached tape of {root} {d} on this machine")
    tapes = OverlayTapeStore(ARCHIVE, CACHE, tmp_path / "tape")      # reads the shared cache, never writes it
    t = tapes.load(root, d)
    daily = [tapes.daily(root, x) for x in tapes.sessions(root, d - dt.timedelta(days=400), d)
             if x < d and shared.cached(root, x)]
    want = sandboxed_tester(name, source, d, daily, tmp_path / "tester")
    assert want["skip"] is None or not want["skip"].startswith("strategy error"), want["skip"]
    before = d - dt.timedelta(days=3 if d.weekday() == 0 else 1)
    if want["needs_daily"] and (not daily or daily[-1]["date"] < before.isoformat()):
        pytest.skip(f"no cached tape of {root} {before} (the day before) on this machine")
    record = {"name": name, "root": root, "source": source, "sha256": "x", "params": {}, "qty": 1}
    got = run_day(record, Rows(t), d, daily=daily, deadline_s=5.0)   # the default spawn: the sandbox
    same(got, want["trades"])
