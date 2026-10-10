"""The would-be fills of a Lab strategy on live prices: the tester's own fill law, fed tick by tick (2026-10-09).

The tester (backtest/engine.py: _Sim, Ctx, run_session) works on a whole day's arrays. Here the day arrives print by
print, and the SAME code must give the SAME trades, so a shadow day equals a backtest of that day. Nothing of the law
is written again: ShadowFills drives the engine's own Ctx over a _Sim whose tape grows, and changes the three places
where the engine leans on having the whole day:

  1. An order goes live `placement_ms` after the event that sent it. The engine finds its first eligible print with a
     bisect over the day; here those prints have not arrived, so the first eligible print is decided by TIME (the
     event's time + the placement) once a print at or after that time exists -- never "the next print to arrive".
  2. A flat fills on the first print at or after its time. That print may not have arrived: `flat` reads True at once
     (as in the tester), the position's stop and target ride until that print, and the close is priced on it when it
     comes -- or on the last print, reason "eod", if none ever comes.
  3. The end of the tape (`hi`) is not a fixed number: it is however many prints are held.

Nothing here places an order: an intent (labrun/livectx.py) goes in, a would-be fill is written down.
"""
from __future__ import annotations

import datetime as dt
from array import array
from bisect import bisect_left

from ..backtest.engine import Costs, Ctx, Order, _Sim, to_tick

FIELDS = ("status", "fill_px", "fill_sl", "fill_tp", "fill_ms")     # what an update carries about an order


class _LiveSim(_Sim):
    """The engine's _Sim over a tape that is still arriving."""

    def __init__(self, root, d, ts, px, costs: Costs, placement_ms: int):
        super().__init__(root, d, ts, px, 0, 0, costs, placement_ms)
        self.live_at: dict[Order, int] = {}     # an entry -> when it goes live, until its first eligible print is known
        self.closing: list[tuple[int, str, list]] = []   # (time, reason, positions): flats waiting for their print

    @property
    def hi(self) -> int:
        return len(self.ts)

    @hi.setter
    def hi(self, _n: int) -> None:      # the engine sets it once; the tape's end is never a fixed number here
        pass

    def new_order(self, side, kind, price, qty, **kw) -> Order:
        o = super().new_order(side, kind, price, qty, **kw)     # min_i: right only if that print is already held
        self.live_at[o] = self.now + self.place_ns
        return o

    def _settle(self) -> None:
        """Each waiting entry's first eligible print: the first at or after its live time, final once one is held."""
        n = len(self.ts)
        for o, t in list(self.live_at.items()):
            if o.status != "working":
                del self.live_at[o]
                continue
            o.min_i = bisect_left(self.ts, t, min(o.min_i, n), n)
            if o.min_i < n:
                del self.live_at[o]

    def waiting(self) -> set:
        return {p for _, _, held in self.closing for p in held}

    def flatten(self, reason: str) -> None:
        for o in list(self.orders):
            if o.role == "entry":
                self.cancel(o)
        if not self.positions:
            return
        if self.i < len(self.ts) and self.ts[self.i] >= self.now:
            super().flatten(reason)              # the print is here: the engine's own close
            return
        seen = self.waiting()
        held = [p for p in self.positions if p not in seen]
        if held:
            self.closing.append((self.now, reason, held))

    def advance(self, j: int) -> None:
        self._settle()
        while self.closing:
            t, reason, held = self.closing[0]
            k = bisect_left(self.ts, t, self.i, len(self.ts))
            if k > j or k >= len(self.ts):
                break
            super().advance(k)                   # the prints before it: a stop or a target may still get there first
            for pos in held:
                if pos in self.positions:
                    self._close(pos, to_tick(self.px[k] - pos.side * self.slip, self.tick), k, reason)
            self.closing.pop(0)
        super().advance(j)

    def end(self, reason: str) -> None:
        """Close what is open now: on the print at the clock, else on the last print held (the engine's flatten)."""
        self.closing.clear()
        _Sim.flatten(self, reason)


class ShadowFills:
    """One strategy's would-be orders and fills for one day. The host calls, in this order for each event:
    advance_to(t), now(t), [the strategy runs], apply(intents); then advance_all() once the due events are done."""

    def __init__(self, root: str, date: dt.date, costs: Costs, placement_ms: int):
        self.ts, self.px, self.size = array("q"), array("d"), array("q")
        self._sim = _LiveSim(root, date, self.ts, self.px, costs, placement_ms)
        self._ctx = self._sim._ctx = Ctx(self._sim, 1, [])
        self._orders: dict[int, Order] = {}          # the LiveCtx order id -> the engine's order
        self._told: dict[int, tuple] = {}            # ... -> what the strategy was last told about it

    # ---- the tape
    def add_ticks(self, rows) -> None:
        """Append prints (ts_ns, price, size). Fills nothing. A print older than the newest one held is dropped: the
        tape stays in time order, as the tick client keeps it."""
        last = self.ts[-1] if self.ts else 0
        for ts_ns, price, size in rows:
            if ts_ns < last:
                continue
            last = ts_ns
            self.ts.append(ts_ns)
            self.px.append(price)
            self.size.append(size)

    def advance_to(self, t_ns: int) -> None:
        """Process the prints strictly before t_ns (what run_session does before an event)."""
        s = self._sim
        s.advance(bisect_left(self.ts, t_ns, s.i, len(self.ts)))

    def advance_all(self) -> None:
        self._sim.advance(len(self.ts))

    def now(self, t_ns: int) -> None:
        self._sim.now = t_ns

    # ---- what the tester's ctx would say at this moment
    def last_price(self) -> float | None:
        return self._ctx.last_price

    @property
    def flat(self) -> bool:
        s = self._sim
        return not s.positions or s.waiting().issuperset(s.positions)

    @property
    def working_entries(self) -> int:
        return sum(1 for o in self._sim.orders if o.role == "entry")

    # ---- the strategy's side
    def apply(self, intents) -> None:
        s, ctx = self._sim, self._ctx
        for it in intents:
            op = it["op"]
            if op == "entry":
                ctx.move_brackets_to_fill = bool(it["move"])
                # Ctx._entry is what stop_entry / limit_entry / market all call: `ref` goes in as the strategy sent it
                # (a stop entry's ref is its price BEFORE the tick snap, which the intent's price no longer is)
                o = ctx._entry(it["kind"], it["side"], it.get("price"), it["qty"], it.get("sl"), it.get("tp"),
                               it.get("tp_rr"), it.get("ref"))
                self._orders[it["id"]] = o
                self._told[it["id"]] = self._state(o)
            elif op == "oco":
                legs = [self._orders.get(i) for i in it["ids"]]
                if legs and None not in legs:
                    ctx.oco(*legs)
            elif op == "cancel":
                o = self._orders.get(it["id"])
                if o is not None:
                    ctx.cancel(o)
            elif op == "flatten":
                ctx.flatten(it["reason"])
            elif op == "plot":
                s.res.plots.setdefault(it["name"], []).append([it["t_ms"], it["value"]])
            elif op == "hline":
                s.res.hlines.append({"name": it["name"], "price": it["price"], "date": s.date.isoformat(),
                                     "role": it["role"], "t_ms": it["t_ms"]})
            elif op == "skip":
                s.res.skip = it["reason"]

    @staticmethod
    def _state(o: Order) -> tuple:
        return tuple(getattr(o, k) for k in FIELDS)

    def updates(self) -> list[dict]:
        """One update per order whose status or fill changed since the last call. An order that is no longer working
        cannot change again and is not looked at after it was reported."""
        out = []
        for i, was in list(self._told.items()):
            o = self._orders[i]
            st = self._state(o)
            if st != was:
                out.append({"id": i, **dict(zip(FIELDS, st))})
                self._told[i] = st
            if o.status != "working":
                del self._told[i]
        return out

    # ---- the end of the day
    def finish(self, end_ns: int | None = None) -> None:
        """The end of the session: every print held, then the engine's end-of-day flat ("eod")."""
        s = self._sim
        self.advance_all()
        s.i = len(self.ts)
        s.end("eod")
        if end_ns is not None:
            for rec in s.res.hlines:
                rec["end_ms"] = end_ns // 1_000_000

    def crash(self, reason: str = "strategy error") -> None:
        """The tester's law for a strategy error: cancel every working order and flatten at the current print."""
        self._sim.end(reason)

    def trades(self) -> list[dict]:
        return [t.to_dict() for t in self._sim.res.trades]

    @property
    def result(self):
        return self._sim.res
