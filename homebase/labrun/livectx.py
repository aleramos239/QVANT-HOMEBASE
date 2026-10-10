"""LiveCtx: what a Lab strategy sees on live prices (the tester's Ctx, with orders turned into intents).

A strategy written for the tester (backtest/engine.py, class Ctx) runs here unchanged: the same names, arguments,
defaults and ValueErrors. The difference is the far end. An entry call returns a LiveOrder and queues a plain
"intent" dict; the host reads the queue with drain() and decides what happens (the door, the would-be fill).
What the host learned since (fills, cancels) arrives through begin() before each handler runs.

Stdlib only; imports nothing from homebase, so the child can load it without the engine.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

SIDE = {"long": 1, "short": -1}
ROLES = ("anchor", "entry", "sl", "tp", "level")   # Ctx.hline: what the page styles a level by


def to_tick(px: float, tick: float) -> float:
    return round(round(px / tick) * tick, 6)


def _finite(v) -> bool:
    """A real, finite number (a bool is not one). Anything else is not drawn: a bad point must not cost the orders."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


@dataclass(eq=False)
class LiveOrder:
    id: int
    side: int                       # +1 buy, -1 sell
    kind: str                       # "stop" | "limit" | "market"
    price: float | None             # trigger (stop) / limit price; None for market
    qty: int
    role: str = "entry"
    sl: float | None = None         # absolute prices, as the strategy sent them
    tp: float | None = None
    tp_rr: float | None = None
    ref: float | None = None
    oco: int | None = None
    status: str = "working"         # working | filled | cancelled
    fill_px: float | None = None    # what the host reports: what the entry became
    fill_sl: float | None = None
    fill_tp: float | None = None
    fill_ms: int | None = None


class LiveCtx:
    """What a strategy sees. One per child, one trading day."""

    def __init__(self, *, root: str, date, tick: float, point_value: float, qty: int, daily: list):
        self.root = root
        self.date = date
        self.tick = tick
        self.point_value = point_value
        self.qty = qty
        self.daily = daily
        self.move_brackets_to_fill = False
        self._now = 0
        self._last: float | None = None
        self._flat = True
        self._flattened = False        # ctx.flat reads True after ctx.flatten() until the next begin()
        self._ids = 0
        self._orders: dict[int, LiveOrder] = {}
        self._out: list[dict] = []

    # ---- the host's side (child.py only)
    def begin(self, now_ns: int, last_price: float | None, flat: bool, updates: list) -> None:
        """Set the clock, the last price and flat; apply what the host learned about its orders."""
        self._now, self._last, self._flat, self._flattened = now_ns, last_price, bool(flat), False
        for u in updates:
            o = self._orders.get(u.get("id"))
            if o is None:
                continue
            o.status = u["status"]
            o.fill_px, o.fill_sl, o.fill_tp, o.fill_ms = (u.get("fill_px"), u.get("fill_sl"), u.get("fill_tp"),
                                                          u.get("fill_ms"))

    def drain(self) -> list[dict]:
        """The intents queued since the last drain, in call order."""
        out, self._out = self._out, []
        return out

    # ---- what a strategy sees
    @property
    def now_ns(self) -> int:
        return self._now

    @property
    def last_price(self) -> float | None:
        return self._last

    @property
    def flat(self) -> bool:
        return self._flat or self._flattened

    def _entry(self, kind, side, price, qty, sl, tp, tp_rr, ref) -> LiveOrder:
        if side not in SIDE:
            raise ValueError(f"side must be 'long' or 'short', not {side!r}")
        price = None if price is None else to_tick(price, self.tick)
        sl = None if sl is None else to_tick(sl, self.tick)
        tp = None if tp is None else to_tick(tp, self.tick)
        self._ids += 1
        o = LiveOrder(self._ids, SIDE[side], kind, price, int(qty or self.qty), sl=sl, tp=tp, tp_rr=tp_rr, ref=ref)
        self._orders[o.id] = o
        self._out.append({"op": "entry", "id": o.id, "kind": kind, "side": side, "price": price, "qty": o.qty,
                          "own_qty": qty is not None, "sl": sl, "tp": tp, "tp_rr": tp_rr, "ref": ref,
                          "move": bool(self.move_brackets_to_fill)})
        return o

    def stop_entry(self, side: str, price: float, qty: int | None = None, sl=None, tp=None,
                   tp_rr=None) -> LiveOrder:
        return self._entry("stop", side, price, qty, sl, tp, tp_rr, price)

    def limit_entry(self, side: str, price: float, qty: int | None = None, sl=None, tp=None,
                    tp_rr=None) -> LiveOrder:
        return self._entry("limit", side, price, qty, sl, tp, tp_rr, price)

    def market(self, side: str, qty: int | None = None, sl=None, tp=None, tp_rr=None,
               ref: float | None = None) -> LiveOrder:
        return self._entry("market", side, None, qty, sl, tp, tp_rr, ref)

    def oco(self, *orders: LiveOrder) -> None:
        g = orders[0].id
        for o in orders:
            o.oco = g
        self._out.append({"op": "oco", "ids": [o.id for o in orders]})

    def cancel(self, order: LiveOrder) -> None:
        if order.status == "working":
            order.status = "cancelled"
            self._out.append({"op": "cancel", "id": order.id})

    def flatten(self, reason: str = "time") -> None:
        for o in self._orders.values():
            if o.status == "working":
                o.status = "cancelled"
        self._flattened = True
        self._out.append({"op": "flatten", "reason": reason})

    def plot(self, name: str, t_ns: int, value: float) -> None:
        if not _finite(value):              # a bad point is dropped: it must never cost the event's orders
            return
        self._out.append({"op": "plot", "name": name, "t_ms": t_ns // 1_000_000, "value": value})

    def hline(self, name: str, price: float, role: str = "level") -> dict:
        """Record a level the strategy placed, for the chart only -- it never reaches an order. Returns the
        record, which a strategy may still rename; the rename is display-only and is not sent."""
        if role not in ROLES:
            raise ValueError(f"role must be one of {', '.join(ROLES)}, not {role!r}")
        t_ms = self._now // 1_000_000
        if _finite(price):                  # a bad level is not sent, the record still comes back
            self._out.append({"op": "hline", "name": name, "price": price, "role": role, "t_ms": t_ms})
        return {"name": name, "price": price, "date": self.date.isoformat(), "role": role, "t_ms": t_ms}

    def skip(self, reason: str) -> None:
        self._out.append({"op": "skip", "reason": reason})
