"""A SIMULATED broker account for rehearsals on the practice Desk (python -m tools.fake_desk --lab). Never a broker,
never a login, never a socket: one adapter is one made-up account whose orders rest in memory (and in one small file)
and are filled by the tester's own fill law from the prints it is handed.

    ad = SimAdapter("sim041", <folder>)          # <folder>/sim-sim041.json holds its book (None: memory only)
    await ad.on_clock(now_ms)                     # the tick stream's clock
    await ad.on_ticks("NQ", [[ts_ms, price, size], ...])    # the prints, in time order: fills happen here

THE FILL LAW IS NOT WRITTEN AGAIN. Whether a print triggers an order, and at what price it fills, is asked of the
tester's own code (homebase.backtest.engine._Sim._trigger / _fill_price) through the object the runner's shadow mode
uses for it (homebase.labrun.shadowfills.ShadowFills, which also keeps the tape in time order):
  * an order goes live `placement_ms` after it was placed (by the stream's clock), and never fills on a print this
    account already held when it was placed;
  * a Stop fills at the worse of its level and the print, plus one side of slippage; a Market at the print plus
    slippage; a Limit only once a print trades one tick THROUGH it, at its own price;
  * the prints are worked one at a time, oldest first, the orders in the order they were placed; a fill is told to
    the engine (observe_fills) before the next print is looked at, so what the engine does about it -- the other
    entry cancelled, the stop and target moved to the fill -- is in the book before that next print, as in the tester.
What IS written here is the broker's book around that law: order ids, a bracket's two legs, statuses, the net position.

WHAT IT ASSUMES ABOUT A BROKER (the real ones' behaviour here is NOT proven: each line is on the demo checklist).
Where the paper account's adapter (homebase/broker/paper.py) shows a behaviour, this one mirrors it.
  A1  A bracket's stop and target exist from the moment the entry is acknowledged, each with its own id (returned in
      raw as sl_order_id / tp_order_id). Until the entry fills they read "Suspended"; then "Working".
  A2  The entry is a Day order, its stop and target are GTC. At the first print (or clock) of a new session a Day
      ENTRY of an earlier one is cancelled, with its held legs (A3); a stop, a target and a closing order never
      expire. This is the paper book's rule (paperbook._expire, with its session_of). It reads "Canceled", as a
      vanished paper order does -- a real broker may say "Expired".
  A3  An entry cancelled with NO fill takes its stop and target with it: they read "Canceled" (the paper book's rule).
      The fault `legs_outlive` turns that off: they then stay "Suspended" until each is cancelled by its id.
  A4  An entry cancelled AFTER a part fill keeps its stop and target working, at the size that filled.
  A5  A part-filled entry's stop and target work at the size filled so far, and grow with each further fill.
  A6  When a bracket's stop or target fills, the other one is cancelled. An unfilled rest of a part-filled entry is
      NOT: it keeps working, and when it fills later nothing protects that contract (the paper book has no part
      fills and shows nothing here; this is the harder case for the engine, so it is the one rehearsed).
  A7  Finished orders read "Filled", "Canceled" or "Rejected" -- the words the engine calls terminal. An id this
      account never issued reads "Canceled" with filled_qty None (the paper adapter's answer for a vanished order).
  A8  get_order_state: a working order {"status": "Working" | "Suspended", "filled_qty": contracts so far (0 = none)};
      a finished one its filled contracts, or None when none filled.
  A9  Cancelling an order that is not working is refused ("order N is not working on <label>"), as the paper book does.
  A10 A Stop whose trigger the last print is already at or through is REFUSED, in the paper book's words ("a buy
      stop must be above the last price (...)"; with no print yet: "no NQ print yet ..."), when it is placed and
      when a working one is moved. A held stop or target is checked against its entry's price instead, as there.
      The tester itself would fill such a stop at the market: here the broker's refusal wins, as on paper.
  A11 A modify moves a price, never a size (the paper book's rule); a stop or target can be moved before its entry fills.
  A12 A Market order with no bracket (the engine's one close order) fills on the next print whatever the position is,
      and cancels nothing: the stop and target it leaves behind keep working until they are cancelled.
  A13 A refused order leaves nothing behind: no id, no order.

FAULTS (SimAdapter.faults, set by POST /fake/lab on the practice Desk): see Faults.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from homebase.backtest.engine import Costs, Order, tick_cmp
from homebase.broker.base import BrokerAdapter, FillCallback, FillEvent, OrderRequest, OrderResult
from homebase.broker.paper import root_of
from homebase.charts.paperbook import session_of     # the paper book's own rule for which session a moment is in
from homebase.contracts import point_value, tick_size
from homebase.labrun.shadowfills import ShadowFills
from homebase.strategies.base import Strategy

PLACEMENT_MS = Strategy.placement_ms        # the tester's own order-placement latency (85 ms)
FILLS_KEPT = 200
LIVE = ("Working", "Suspended")
KIND = {"Market": "market", "Stop": "stop", "Limit": "limit"}
REJECT_WORDS = "OSO rejected (no orderId returned)"     # broker/tradovate.py's words for an answer with no order
CLOSE_REFUSED = "order rejected (no orderId returned)"  # ... and for a plain order
UNREADABLE = "position unreadable (simulated fault)"


@dataclass
class Faults:
    """What goes wrong on purpose, per account. Each one is read where a real broker would fail."""
    reject_next: int = 0                 # the next n ENTRY orders (place_bracket) are refused, with `reject_words`
    reject_words: str = REJECT_WORDS
    partial_next: int = 0                # the next entry fill gives only this many contracts; the rest keeps working
    fill_both: bool = False              # when one entry fills, every other working entry in that market fills too
    ack_delay_ms: int = 0                # an order is in the book at once; its answer comes this much later
    order_status_unknown: object = None  # an order id (or True: every order) whose status cannot be read
    position_unreadable: bool = False    # the position read fails
    close_refused: bool = False          # a Market order with no bracket (the engine's close) is refused
    legs_outlive: bool = False           # assumption A3 switched off

    def set(self, body: dict) -> None:
        for k, v in body.items():
            if k not in self.__dataclass_fields__:
                raise ValueError(f"unknown fault {k!r}")
            was = getattr(self, k)
            if k == "order_status_unknown":
                v = None if v in (None, False, "") else (True if v is True else str(v))
            elif isinstance(was, bool):
                if not isinstance(v, bool):
                    raise ValueError(f"{k}: true or false")
            elif isinstance(was, int):
                if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                    raise ValueError(f"{k}: a whole number, 0 or more")
            elif not isinstance(v, str) or not v.strip():
                raise ValueError(f"{k}: some words")
            setattr(self, k, v)


@dataclass
class SimOrder:
    id: str
    symbol: str                          # as the engine sent it
    market: str                          # its root: the tape it fills on
    side: str                            # "Buy" | "Sell"
    type: str                            # "Market" | "Stop" | "Limit"
    price: Optional[float]               # a Stop's or a Limit's level
    qty: int
    filled: int = 0
    status: str = "Working"              # Working | Suspended | Filled | Canceled | Rejected
    role: str = ""                       # "entry" | "sl" | "tp" | "" (a plain order)
    parent: Optional[str] = None         # a bracket leg's entry
    tif: str = "Day"
    text: str = ""
    live_ns: int = 0                     # it may fill from this time on (the stream's clock) ...
    born: int = 0                        # ... and only on a print that arrived after it was placed (the tape's length then)
    session: str = ""                    # the session it was placed for (a Day entry ends with it: A2)


class SimAdapter(BrokerAdapter):
    platform = "sim"

    def __init__(self, account_id: str, root=None, *, live: bool = False, label: str = "", costs: Costs | None = None,
                 placement_ms: int = PLACEMENT_MS, first_id: int = 1, balance: float = 50_000.0):
        super().__init__(account_id, live=live)
        self.pinned_ok = True
        self.label = label or account_id
        self.faults = Faults()
        self.away = False                # a saved book was loaded: fills are booked, not told, until back()
        self._costs, self._place_ns = costs or Costs(), int(placement_ms) * 1_000_000
        self._path = Path(root) / f"sim-{account_id}.json" if root is not None else None
        self._tapes: dict[str, ShadowFills] = {}
        self._used: dict[str, list] = {}             # market -> [its newest print's ns, how many it holds at that ns]
        self._skip: dict[str, int] = {}              # after a restart: prints AT that ns still to drop (used before it)
        self._at: dict[str, int] = {}                # market -> the next print to work (an order placed now is born there)
        self._fid = 0
        self._last: dict[str, float] = {}            # market -> its last print's price (what a new Stop is checked against)
        self._sess: dict[str, str] = {}              # market -> the session its last print (or the clock) was in
        self._dirty = False              # the book changed since it was last saved
        self._clock_ns = 0
        self._ids = int(first_id)
        self._balance0 = float(balance)
        self._realized = 0.0
        self.orders: dict[str, SimOrder] = {}        # every order of this account, in the order they were placed
        self.pos: dict[str, dict] = {}               # market -> {"net": int, "avg": float | None}
        self.fills: list[dict] = []
        self._on_fill: Optional[FillCallback] = None
        self._lock: Optional[tuple] = None           # (loop, asyncio.Lock): one batch of prints at a time
        self._load()

    # ---- the book on disk (a restart of the practice Desk finds its orders and positions, as at a broker)
    def _load(self) -> None:
        if self._path is None or not self._path.is_file():
            return
        d = json.loads(self._path.read_text())
        self.orders = {o["id"]: SimOrder(**o) for o in d["orders"]}
        self.pos, self.fills, self._ids = d["pos"], d["fills"], int(d["ids"])
        self._realized, self._used, self._clock_ns = float(d["realized"]), d["used"], int(d["clock_ns"])
        self._fid, self._skip = int(d.get("fid") or 0), {m: int(u[1]) for m, u in self._used.items()}
        self._last, self._sess = dict(d.get("last") or {}), dict(d.get("sess") or {})
        for o in self.orders.values():
            o.born = 0                   # a new tape: every print it takes is one that came after this order
        self.away = True

    def _save(self) -> None:
        if self._path is None:
            return
        self._dirty = False
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "orders": [asdict(o) for o in self.orders.values()], "pos": self.pos, "fills": self.fills[-FILLS_KEPT:],
            "ids": self._ids, "fid": self._fid, "last": self._last, "sess": self._sess, "realized": self._realized, "used": self._used, "clock_ns": self._clock_ns}))
        os.replace(tmp, self._path)

    def back(self) -> None:
        """The stream has caught up after a start on a saved book: from here a fill is told to the engine again.
        (What filled while the Desk was down was booked only: a broker pushes a fill once, to whoever listens then.)"""
        self.away = False

    # ---- lifecycle
    async def connect(self) -> None:
        self._connected = True

    async def close(self) -> None:
        self._connected = False

    async def observe_fills(self, on_fill: FillCallback) -> None:
        self._on_fill = on_fill

    # ---- the tape and the law
    def _tape(self, market: str) -> ShadowFills:
        t = self._tapes.get(market)
        if t is None:
            day = dt.datetime.fromtimestamp(self._clock_ns / 1e9, dt.timezone.utc).date()
            t = self._tapes[market] = ShadowFills(market, day, self._costs, 0)
        return t

    def _next_id(self) -> str:
        i, self._ids = self._ids, self._ids + 1
        return str(i)

    def _batch_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock[0] is not loop:
            self._lock = (loop, asyncio.Lock())
        return self._lock[1]

    async def on_clock(self, now_ms: int) -> None:
        """The stream's clock (it may go back: a replay that starts again)."""
        self._clock_ns = int(now_ms) * 1_000_000
        for market in {o.market for o in self.orders.values() if o.status in LIVE}:
            self._session(market, int(now_ms))
        if self._dirty:
            self._save()

    def _session(self, market: str, ts_ms: int) -> None:
        """A2: a new session on this market ends the Day ENTRIES placed for an earlier one (paperbook._expire)."""
        sess = session_of(ts_ms, market)
        if self._sess.get(market) == sess:
            return
        self._sess[market] = sess
        for o in list(self.orders.values()):
            if o.market == market and o.tif == "Day" and o.role == "entry" and o.status in LIVE \
                    and o.session and o.session < sess:
                self._end_entry(o)
                self._dirty = True

    def _end_entry(self, o: SimOrder) -> None:
        """An entry cancelled (by hand, or by its session's end). A3: with no fill its held legs go with it."""
        o.status = "Canceled"
        for leg in self._legs(o.id):
            if leg.status == "Suspended" and not o.filled and not self.faults.legs_outlive:
                leg.status = "Canceled"                                             # (A4: after a fill they stay)

    def _stop_refusal(self, market: str, side: str, level) -> Optional[str]:
        """A10, the paper book's rule and words (paperbook._check_prices): a Stop needs a last print, and its trigger
        must be on the far side of it."""
        last, tick = self._last.get(market), tick_size(market) or 0.25
        if last is None:
            return f"no {market} print yet — a stop needs a price to check against"
        if side == "Buy" and tick_cmp(level, last, tick) <= 0:
            return f"a buy stop must be above the last price ({last:,})"
        if side == "Sell" and tick_cmp(level, last, tick) >= 0:
            return f"a sell stop must be below the last price ({last:,})"
        return None

    def now_ns(self) -> int:
        return self._clock_ns

    def _fresh(self, market: str, rows) -> list:
        """The prints not used yet, as (ns, price, size): none older than the newest one used, and of those AT its
        time only the ones beyond the count already used (the tick client's own rule, kept across a restart)."""
        ns0, n = self._used.get(market, (-1, 0))
        out, skip = [], self._skip.get(market, 0)
        for r in rows:
            t = int(r[0]) * 1_000_000            # ns: the tester's rule for ms recordings (labrun/host.py on_rows)
            if t < ns0:
                continue
            if t > ns0:
                ns0, n, skip = t, 0, 0
            elif skip:
                skip -= 1
                continue
            n += 1
            out.append((t, float(r[1]), int(r[2])))
        self._used[market], self._skip[market] = [ns0, n], skip
        return out

    async def on_ticks(self, market: str, rows) -> None:
        """Prints [[ts_ms, price, size], ...] of one market, in time order. Every fill they cause is booked, and told
        to the engine, here."""
        async with self._batch_lock():
            fresh = self._fresh(market, rows)
            if not fresh:
                return
            tape = self._tape(market)
            k0 = len(tape.ts)
            tape.add_ticks(fresh)
            try:
                for k in range(k0, len(tape.ts)):
                    self._at[market] = k + 1                 # an order placed while print k is worked may fill from k + 1
                    if tape.ts[k] > self._clock_ns:
                        self._clock_ns = int(tape.ts[k])
                    self._session(market, int(tape.ts[k]) // 1_000_000)
                    self._last[market] = float(tape.px[k])
                    await self._print(market, tape, k)
            finally:
                self._at.pop(market, None)
                if self._dirty:              # a batch that filled nothing writes nothing (it would only say which
                    self._save()             # prints were used: after a restart those are worked again, to the same end)

    def _hit(self, tape: ShadowFills, o: SimOrder, k: int) -> Optional[float]:
        """The tester's law, asked for ONE print: the fill price when print k fills this order, else None."""
        if o.status != "Working" or k < o.born or tape.ts[k] < o.live_ns:
            return None
        law = Order(0, 1 if o.side == "Buy" else -1, KIND[o.type], o.price, o.qty, k, role=o.role or "entry")
        sim = tape._sim
        return sim._fill_price(law, tape.px[k]) if sim._trigger(law, k, k + 1) == k else None

    async def _print(self, market: str, tape: ShadowFills, k: int) -> None:
        events: list[FillEvent] = []
        for o in list(self.orders.values()):
            if o.market != market:
                continue
            px = self._hit(tape, o, k)
            if px is None:
                continue
            events += self._fill(o, px, tape, k)
            if o.role == "entry" and self.faults.fill_both:
                for x in list(self.orders.values()):         # the fault: the other entry fills before any cancel lands
                    if x is not o and x.market == market and x.role == "entry" and x.status == "Working":
                        law = Order(0, 1 if x.side == "Buy" else -1, KIND[x.type], x.price, x.qty, k)
                        events += self._fill(x, tape._sim._fill_price(law, tape.px[k]), tape, k)
            for ev in events:                                # told before the next order of this print is looked at
                await self._tell(ev)
            events = []

    def _fill(self, o: SimOrder, px: float, tape: ShadowFills, k: int) -> list[FillEvent]:
        self._dirty = True
        qty = o.qty - o.filled
        if o.role == "entry" and self.faults.partial_next and self.faults.partial_next < qty:
            qty, self.faults.partial_next = self.faults.partial_next, 0
        o.filled += qty
        if o.filled >= o.qty:
            o.status = "Filled"
        ns = int(tape.ts[k])
        p = self.pos.setdefault(market := o.market, {"net": 0, "avg": None})
        s, net0, avg0 = (1 if o.side == "Buy" else -1), p["net"], p["avg"]
        closing = min(qty, abs(net0)) if net0 and (net0 > 0) != (s > 0) else 0
        if closing:
            self._realized += (px - avg0) * (1 if net0 > 0 else -1) * closing * (point_value(market) or 0.0)
        net1 = net0 + s * qty
        p["net"] = net1
        p["avg"] = None if net1 == 0 else px if closing >= abs(net0) and closing else avg0 if closing else \
            round(((avg0 or 0.0) * abs(net0) + px * qty) / abs(net1), 6)
        self._fid += 1
        f = {"id": self._fid, "order_id": o.id, "symbol": o.symbol, "side": o.side, "qty": qty, "price": px,
             "time_ns": ns, "role": o.role}
        self.fills.append(f)
        del self.fills[:-FILLS_KEPT * 2]
        if o.role == "entry":                                # A1, A5: its legs work from the next print, at the size in
            for leg in self._legs(o.id):
                if leg.status in LIVE:
                    leg.status, leg.qty = "Working", o.filled
                    leg.born = max(leg.born, k + 1)
        elif o.role in ("sl", "tp") and o.status == "Filled":    # A6: the other leg. An unfilled rest of the entry
            for x in self._legs(o.parent):                       # is left working: no broker is known to end it
                if x is not o and x.status in LIVE:
                    x.status = "Canceled"
        return [FillEvent(account_id=self.account_id, symbol=o.symbol, side=o.side, qty=qty, price=px,
                          position_after=net1, ts=ns / 1e9, raw={"orderId": o.id, "role": o.role, "fill": dict(f)})]

    def _legs(self, entry_id) -> list[SimOrder]:
        return [x for x in self.orders.values() if x.parent == entry_id and entry_id is not None]

    async def _tell(self, ev: FillEvent) -> None:
        if self.away:
            return
        self._notify("fill", dict(ev.raw["fill"]))
        if self._on_fill is not None:
            await self._on_fill(ev)

    # ---- orders
    def _new(self, req: OrderRequest, typ: str, price, *, side=None, role="", parent=None, status="Working",
             tif="Day") -> SimOrder:
        market = root_of(req.symbol)
        tick = tick_size(market) or 0.25
        o = SimOrder(id=self._next_id(), symbol=req.symbol, market=market, side=side or req.side, type=typ,
                     price=None if price is None else round(round(float(price) / tick) * tick, 6), qty=int(req.qty),
                     status=status, role=role, parent=parent, tif=tif, text=req.text,
                     live_ns=self._clock_ns + self._place_ns,
                     born=self._at.get(market, len(self._tape(market).ts)),
                     session=session_of(self._clock_ns // 1_000_000, market))
        self.orders[o.id] = o
        return o

    @staticmethod
    def _level(req: OrderRequest):
        if req.order_type == "Stop":
            return req.price if req.price is not None else req.stop_price
        return req.price if req.order_type == "Limit" else None

    async def _ack(self) -> None:
        self._save()
        if self.faults.ack_delay_ms:
            await asyncio.sleep(self.faults.ack_delay_ms / 1000)

    def _unknown_type(self, req: OrderRequest) -> Optional[OrderResult]:
        if req.order_type not in KIND:
            return OrderResult(ok=False, error=f"the simulated account takes Market, Stop and Limit orders, not {req.order_type}")
        if not self.connected:
            return OrderResult(ok=False, error="adapter not connected")
        if req.order_type == "Stop":                                                # A10
            why = self._stop_refusal(root_of(req.symbol), req.side, self._level(req))
            if why is not None:
                return OrderResult(ok=False, error=why)
        return None

    async def place_order(self, req: OrderRequest) -> OrderResult:
        """One plain order (no bracket). The engine's close is one of these: a Market order."""
        bad = self._unknown_type(req)
        if bad is not None:
            return bad
        if req.order_type == "Market" and self.faults.close_refused:
            return OrderResult(ok=False, error=CLOSE_REFUSED)
        o = self._new(req, req.order_type, self._level(req), tif=req.time_in_force)
        await self._ack()
        return OrderResult(ok=True, order_id=o.id, raw={"ok": True, "order_id": o.id, "error": None})

    async def place_bracket(self, req: OrderRequest) -> OrderResult:
        """The entry and its stop / target as one order with three ids (A1): the legs' ids ride in raw as
        sl_order_id / tp_order_id, as the engine reads them. A target that is not asked for has no order (None)."""
        bad = self._unknown_type(req)
        if bad is not None:
            return bad
        if self.faults.reject_next:
            self.faults.reject_next -= 1
            return OrderResult(ok=False, error=self.faults.reject_words)            # A13
        e = self._new(req, req.order_type, self._level(req), role="entry", tif=req.time_in_force)
        out = "Sell" if req.side == "Buy" else "Buy"
        sl = self._new(req, "Stop", req.stop_price, side=out, role="sl", parent=e.id, status="Suspended", tif="GTC") \
            if req.stop_price is not None else None
        tp = self._new(req, "Limit", req.tp_price, side=out, role="tp", parent=e.id, status="Suspended", tif="GTC") \
            if req.tp_price is not None else None
        await self._ack()
        return OrderResult(ok=True, order_id=e.id, raw={
            "ok": True, "order_id": e.id, "error": None,
            "sl_order_id": sl.id if sl else None, "tp_order_id": tp.id if tp else None})

    def _refuse(self, oid) -> OrderResult:
        return OrderResult(ok=False, error=f"order {oid} is not working on {self.label}")

    async def cancel_order_by_id(self, order_id: str) -> OrderResult:
        o = self.orders.get(str(order_id))
        if o is None or o.status not in LIVE:
            return self._refuse(order_id)                                           # A9
        if o.role == "entry":
            self._end_entry(o)                                                      # A3 / A4
        else:
            o.status = "Canceled"
        self._save()
        return OrderResult(ok=True, order_id=o.id, raw={"ok": True, "order_id": o.id, "error": None})

    async def modify_order(self, order_id: str, order_type: str, *, price: Optional[float] = None,
                           stop_price: Optional[float] = None, qty: Optional[int] = None) -> OrderResult:
        level = stop_price if order_type == "Stop" and stop_price is not None else price
        if level is None:
            return OrderResult(ok=False, error="modify: a price is required")
        o = self.orders.get(str(order_id))
        if o is None or o.status not in LIVE:
            return self._refuse(order_id)
        if o.type not in ("Stop", "Limit"):
            return OrderResult(ok=False, error=f"only Limit and Stop orders can be moved (this one is {o.type})")
        size = o.qty if o.status == "Working" or o.parent is None else self.orders[o.parent].qty
        if qty is not None and int(qty) != int(size):
            return OrderResult(ok=False, error="the simulated account moves an order's price, never its size")   # A11
        tick = tick_size(o.market) or 0.25
        px = round(round(float(level) / tick) * tick, 6)
        why = None
        if o.status == "Suspended":                  # a held leg: against its entry's price (paperbook._check_held_leg)
            p = self.orders.get(o.parent or "")
            if p is None or p.price is None:
                why = f"the entry of bracket leg {o.id} has no price to check against — cancel it and place again"
            elif o.role == "sl" and not (1 if p.side == "Buy" else -1) * tick_cmp(p.price, px, tick) > 0:
                why = f"the stop loss must be on the losing side of its entry ({p.price:,})"
            elif o.role == "tp" and not (1 if p.side == "Buy" else -1) * tick_cmp(px, p.price, tick) > 0:
                why = f"the target must be on the winning side of its entry ({p.price:,})"
        elif o.type == "Stop":                       # a working stop: against the last print (A10)
            why = self._stop_refusal(o.market, o.side, px)
        if why is not None:
            return OrderResult(ok=False, error=why)
        o.price = px
        self._save()
        return OrderResult(ok=True, order_id=o.id, raw={"ok": True, "order_id": o.id, "error": None})

    async def cancel_all(self) -> OrderResult:
        n = 0
        for o in list(self.orders.values()):
            if o.status in LIVE:
                o.status, n = "Canceled", n + 1
        self._save()
        return OrderResult(ok=True, raw={"cancelled": n})

    async def flatten_all(self) -> OrderResult:
        bad = []
        for market, p in list(self.pos.items()):
            if p["net"]:
                r = await self.place_order(OrderRequest(symbol=market, side="Sell" if p["net"] > 0 else "Buy",
                                                        qty=abs(p["net"]), order_type="Market", text="sim:flatten"))
                if not r.ok:
                    bad.append(str(r.error))
        return OrderResult(ok=not bad, error="; ".join(bad) or None)

    # ---- reads
    def _hidden(self, oid: str) -> bool:
        u = self.faults.order_status_unknown
        return u is True or (u is not None and str(u) == str(oid))

    async def get_order_state(self, order_id: str) -> dict:
        oid = str(order_id)
        if self._hidden(oid):
            return {"status": None, "filled_qty": None}
        o = self.orders.get(oid)
        if o is None:
            return {"status": "Canceled", "filled_qty": None}                       # A7
        if o.status in LIVE:
            return {"status": o.status, "filled_qty": o.filled}
        return {"status": o.status, "filled_qty": o.filled or None}                 # A8

    async def get_order_status(self, order_id: str) -> Optional[str]:
        return (await self.get_order_state(order_id))["status"]

    async def get_net_position(self, symbol: str) -> int:
        if self.faults.position_unreadable:
            raise RuntimeError(UNREADABLE)
        return int((self.pos.get(root_of(symbol)) or {}).get("net") or 0)

    async def get_balance(self) -> dict:
        return {"balance": round(self._balance0 + self._realized, 2), "realized_pnl": round(self._realized, 2)}

    async def get_metrics(self) -> dict:
        pos = [{"symbol": m, "net": p["net"]} for m, p in sorted(self.pos.items()) if p["net"]]
        return {"connected": self.connected, "account": self.label, **(await self.get_balance()),
                "open_positions": pos, "open_position_count": len(pos),
                "working_orders": sum(1 for o in self.orders.values() if o.status == "Working"), "protective": {}}

    def book(self) -> dict:
        """What a person looking at the simulated account would see (GET /fake/lab on the practice Desk)."""
        return {"account": self.account_id, "label": self.label, "live": self.live, "faults": asdict(self.faults),
                "positions": {m: p for m, p in self.pos.items() if p["net"]},
                "orders": [asdict(o) for o in self.orders.values() if o.status in LIVE],
                "ended": [{"id": o.id, "status": o.status, "filled": o.filled, "role": o.role}
                          for o in list(self.orders.values())[-40:] if o.status not in LIVE],
                "fills": self.fills[-20:], "realized_pnl": round(self._realized, 2)}
