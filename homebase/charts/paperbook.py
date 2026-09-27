"""The PAPER account (2026-09-27 accounts/paper/layouts plan, Task 2): a virtual account the chart page trades
exactly like a desk account -- the Buy/Sell block, the order panel, the chart menu, draggable lines -- filled by
the backtester's own tick law against the live prints this service already streams.

It NEVER reaches a broker: this module imports nothing from homebase.broker, homebase.trading, homebase.desk_api
or homebase.charts.desk (tests/test_charts_paperbook.py asserts it, transitively), holds no key and opens no
connection. It is NOT the forward-test runner (paper.py, "paper:<id>" algos, /api/paper/strategies|history):
that one re-runs a strategy on the prints; this one is an account the viewer trades by hand.

Fill law -- homebase/backtest/engine.py, line for line (cited where each rule is applied):
  * a STOP (and a stop-loss) fills on TOUCH -- a buy on the first print >= its price, a sell on the first print
    <= it -- at max(price, print) + slip for a buy, min(price, print) - slip for a sell: a gap costs the gap
    (engine.py L4-7, L295-296, L306);
  * a LIMIT (and a target) needs 1-TICK PENETRATION -- a buy fills only on a print <= price - tick, a sell only on
    one >= price + tick -- AT the limit, no slip (engine.py L8-10, L297-300, L303-304);
  * a MARKET order fills at the first print after it goes live, +/- slip (engine.py L11, L292-293, L308);
  * $4 per round turn per contract, charged when a position is reduced (engine.py L98, L373);
  * slippage 1 tick per side on market and stop fills only (engine.py L99, L267);
  * every price comparison is `tick_cmp`-tolerant and every price `to_tick`-snapped (engine.py L23-28, L53-67);
  * orders that trigger on the same print fill oldest first; a bracket's SL/TP go live from the print AFTER
    the entry's (engine.py L13-14, L19, L313-326, L351-357).
"Goes live": an order accepted between two prints may fill from the next print this book sees (the real-time
analogue of the engine's min_i with placement_ms = 0). A Stop Limit (the engine has none) triggers like a stop
and then rests as a limit at its limit price from the NEXT print -- never filled on its trigger print
(pessimistic, like the engine's bracket rule). Prints the service missed (a feed gap) are never invented: a stop
whose level was crossed inside the gap fills on the first print after it, paying the gap.

Caps, as the desk's (trading.py guards 3 and 6): 1-10 contracts per order; the worst-case |net| in the contract
(the position + every working order on the order's side + this order) at most 20; a buy stop above / a sell stop
below the last print, a bracket on the losing / winning side of its entry, a Stop Limit's limit on the
fill-allowing side of its trigger within 100 ticks. A Day entry expires when its session ends; the SL/TP legs of
a filled position never expire (a paper position is never left naked overnight by the book itself).

State: an append-only event log (`book.jsonl`: place / cancel / modify / trigger / fill), replayed on start, so
it survives a restart. Everything runs on the chart service's loop and is O(working orders) per print -- no
file is read after start, and a line is appended only when something changes.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import time
from collections import deque
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from .. import netguard
from ..backtest.engine import Costs, tick_cmp, to_tick
from ..contracts import point_value, tick_size
from ..symbols import resolve_contract
from . import _jsonl

PAPER_ID = "paper"
LABEL = "PAPER"
START_BALANCE = 50_000.0          # the virtual account's opening cash
MAX_ORDER_QTY = 10                # the desk's per-order cap (trading.py guard 3)
MAX_POSITION_QTY = 20             # the desk's per-position cap (trading.py guard 3)
STOPLIMIT_MAX_TICKS = 100         # the desk's (trading.py check_prices)
FILLS_KEPT = 50                   # fills in the account view (the desk's FILLS_KEPT)
DEDUP_TTL_S = 600.0
ACTIONS = ("order", "modify", "cancel", "cancel-symbol", "flatten", "reverse")
TYPES = ("Market", "Limit", "Stop", "StopLimit")
TIFS = ("Day", "GTC")
SIDES = {"Buy": 1, "Sell": -1}
SIDE_NAME = {1: "Buy", -1: "Sell"}
BODY_MAX = 4096
LIVE_ONLY = "paper trading is live only (not in a replay)"
_ROOT = re.compile(r"[A-Z0-9]{1,6}")
_ORDER_ID = re.compile(r"[0-9]{1,20}")
_ET = ZoneInfo("America/New_York")
_ALWAYS_OPEN = frozenset({"BTC", "MBT", "ETH", "MET"})   # session.py's ALWAYS_OPEN (not imported: session.py
                                                          # pulls homebase.ticks, which imports the broker's ws)


class Refused(Exception):
    """A guard said no: the account's result is {ok: false, error, refused: true}, never an HTTP error."""


def session_of(ts_ms: int, root: str) -> str:
    """The trading session a moment belongs to (ISO date): a classic root's session D runs 18:00 ET on D-1 to
    17:00 on D, weekends filed into Monday (session.py's rule), and anything from 17:00 on belongs to the NEXT
    one -- an order placed in the 17:00 break is for the coming session. A 24/7 root rolls at 18:00 every day."""
    t = dt.datetime.fromtimestamp(ts_ms / 1000, _ET)
    roll = dt.time(18, 0) if root in _ALWAYS_OPEN else dt.time(17, 0)
    d = t.date() + dt.timedelta(days=1) if t.time() >= roll else t.date()
    if root not in _ALWAYS_OPEN:
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
    return d.isoformat()


def _session_until(ts_ms: int, root: str) -> int:
    """The next moment `session_of` may change for this root (its next 17:00 / 18:00 ET roll), in epoch ms."""
    t = dt.datetime.fromtimestamp(ts_ms / 1000, _ET)
    roll = dt.time(18, 0) if root in _ALWAYS_OPEN else dt.time(17, 0)
    day = t.date() + dt.timedelta(days=1) if t.time() >= roll else t.date()
    return int(dt.datetime.combine(day, roll, _ET).timestamp() * 1000)


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _price(v, name: str, required: bool = False) -> Optional[float]:
    if v is None:
        if required:
            raise ValueError(f"{name}: a price is required")
        return None
    if not _finite(v) or v <= 0:
        raise ValueError(f"{name}: a positive number")
    return float(v)


def _client_id(body: dict) -> str:
    cid = body.get("client_id")
    if not isinstance(cid, str) or not 1 <= len(cid) <= 64:
        raise ValueError("client_id: a string of 1-64 characters")
    return cid


def _only_paper(body: dict) -> None:
    """The paper book takes the PAPER account and nothing else -- the page splits a mixed send; an id here that
    is not PAPER means that split failed, and it is refused whole rather than guessed at (fail closed)."""
    if "accounts" in body:
        a = body.get("accounts")
        if not isinstance(a, list) or not a or any(x != PAPER_ID for x in a):
            raise ValueError(f"accounts: the paper book takes only [{PAPER_ID!r}]")
    else:
        if body.get("account") != PAPER_ID:
            raise ValueError(f"account: the paper book takes only {PAPER_ID!r}")


def _worst_net(net: int, legs: list, side: int, qty: int) -> int:
    """trading.py worst_net: the worst-case |net| if this order AND every working order on its side fill."""
    legs = legs + [(side, qty)]
    buys = sum(q for s, q in legs if s > 0)
    sells = sum(q for s, q in legs if s < 0)
    return max(abs(net + buys), abs(net - sells))


@dataclass
class POrder:
    id: str
    root: str
    symbol: str
    side: int                        # +1 buy, -1 sell
    type: str                        # what the page shows: Market | Limit | Stop | StopLimit
    kind: str                        # the fill law's: market | limit | stop | stoplimit (untriggered)
    price: Optional[float]           # a Limit's / Stop Limit's limit, a Stop's trigger; None for a Market
    trigger: Optional[float]         # a Stop Limit's trigger
    qty: int
    tif: str = "Day"
    role: str = "entry"              # entry | sl | tp | flat
    parent: Optional[str] = None     # a bracket leg's entry
    oco: Optional[str] = None        # a bracket's two legs share one group: one filling cancels the other
    status: str = "working"          # working | held (a bracket leg until its entry fills)
    placed_ms: int = 0
    session: str = ""                # the session it was placed for (a Day entry expires after it)
    sl: Optional[float] = None       # an entry's bracket, as sent (recording only: the legs are real orders)
    tp: Optional[float] = None
    min_seq: int = 0                 # the first print (this root's counter) it may fill on -- never persisted


_ORDER_FIELDS = {f.name for f in fields(POrder)} - {"min_seq"}


class PaperBook:
    def __init__(self, path: Optional[Path], *, roots=(), clock_ms: Callable[[], int] = lambda: int(time.time() * 1000),
                 costs: Optional[Costs] = None, mono: Callable[[], float] = time.monotonic,
                 log: Callable[[str], None] = lambda m: None):
        self.path = Path(path) if path is not None else None
        self.roots = {r.upper() for r in roots}
        self.clock_ms, self.mono, self.log = clock_ms, mono, log
        self.costs = costs or Costs()
        self.orders: dict[str, POrder] = {}          # working + held, in the order they went live (engine.orders)
        self.pos: dict[str, dict] = {}               # root -> {symbol, net, avg}
        self.realized = 0.0                          # net of commission, since the book began
        self.commission = 0.0
        self.fills: deque = deque(maxlen=FILLS_KEPT)
        self.seq: dict[str, int] = {}                # prints seen per root (this process)
        self.last: dict[str, float] = {}             # the last print per root
        self.session: dict[str, str] = {}            # the session of that print per root
        self._until: dict[str, int] = {}             # ...valid until this ms (its next roll): no clock maths per print
        self._id = 0
        self._fid = 0
        self._done: dict[tuple, tuple[float, dict]] = {}
        self.dirty = True
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._load()

    # ---- the event log --------------------------------------------------------------------------------------
    def _load(self) -> None:
        for ev in _jsonl.read_all(self.path):
            try:
                self._apply(ev, seq=0)
            except Exception as e:  # noqa: BLE001 — one bad line never loses the rest of the book
                self.log(f"paperbook: skipped a bad event {str(ev)[:120]}: {type(e).__name__}: {e}")
        for o in self.orders.values():
            o.min_seq = 0                            # a restart: every working order may fill on the next print

    def _do(self, ev: dict, seq: int = 0) -> None:
        self._apply(ev, seq=seq)
        if self.path is not None:
            _jsonl.append(self.path, ev)
        self.dirty = True

    def _apply(self, ev: dict, seq: int) -> None:
        kind = ev.get("ev")
        if kind == "place":
            for d in ev["orders"]:
                o = POrder(**{k: v for k, v in d.items() if k in _ORDER_FIELDS})
                o.min_seq = seq + 1                  # accepted after print `seq`: live from the next one
                self.orders[o.id] = o
                self._id = max(self._id, int(o.id))
        elif kind == "cancel":
            for oid in ev["ids"]:
                self._drop(oid)
        elif kind == "modify":
            self.orders[ev["id"]].price = float(ev["price"])
        elif kind == "trigger":                      # a Stop Limit touched its trigger: a resting limit from the NEXT print
            o = self.orders[ev["id"]]
            o.kind, o.min_seq = "limit", seq + 1
        elif kind == "fill":
            self._fill(self.orders[ev["id"]], float(ev["price"]), int(ev["ts_ns"]), int(ev["fid"]), seq)
        else:
            raise ValueError(f"unknown event {kind!r}")

    def _drop(self, oid: str) -> None:
        o = self.orders.pop(oid, None)
        if o is None:
            return
        for c in [c for c in self.orders.values() if c.parent == oid and c.status == "held"]:
            del self.orders[c.id]                    # an entry cancelled: its bracket legs never go live

    def _fill(self, o: POrder, price: float, ts_ns: int, fid: int, seq: int) -> None:
        del self.orders[o.id]
        self._fid = max(self._fid, fid)
        pv = point_value(o.root) or 0.0
        p = self.pos.get(o.root) or {"symbol": o.symbol, "net": 0, "avg": 0.0}
        net, avg, q, s = p["net"], p["avg"], o.qty, o.side
        pnl = None
        if net == 0 or (net > 0) == (s > 0):
            avg = (avg * abs(net) + price * q) / (abs(net) + q)
            net += s * q
        else:
            closed, was = min(q, abs(net)), (1 if net > 0 else -1)
            gross = was * (price - avg) * pv * closed         # engine.py L372
            comm = self.costs.commission_rt * closed          # engine.py L373: per round turn, per contract
            pnl = round(gross - comm, 2)
            self.realized += gross - comm
            self.commission += comm
            net += s * q
            if net == 0:
                avg = 0.0
            elif (net > 0) != (was > 0):
                avg = price                                   # through zero: the rest opened at this fill
        self.pos[o.root] = {"symbol": p["symbol"] if p["net"] else o.symbol, "net": net, "avg": avg}
        if o.oco is not None:                                 # a bracket leg filled: its twin is cancelled
            for x in [x for x in self.orders.values() if x.oco == o.oco]:
                del self.orders[x.id]
        for c in [c for c in self.orders.values() if c.parent == o.id and c.status == "held"]:
            # the entry filled: its SL/TP go live from the print AFTER this one (engine.py L353, L357), and join
            # the working list at its end -- the engine appends them at fill time (L354, L358)
            del self.orders[c.id]
            c.status, c.min_seq = "working", seq + 1
            self.orders[c.id] = c
        self.fills.append({"id": fid, "order_id": o.id, "symbol": o.symbol, "side": SIDE_NAME[s], "qty": q,
                           "price": price, "time": _iso(ts_ns), "owner": None, "role": o.role,
                           **({"pnl": pnl} if pnl is not None else {})})

    # ---- prints -------------------------------------------------------------------------------------------
    def on_ticks(self, root: str, rows: list) -> None:
        """The live tick rows the service just kept for `root` ({ts_ms, price, ts_ns?}), in tape order."""
        root = root.upper()
        for r in rows:
            ts_ns = int(r["ts_ns"]) if r.get("ts_ns") else int(r["ts_ms"]) * 1_000_000
            self.on_print(root, ts_ns, float(r["price"]))

    def on_print(self, root: str, ts_ns: int, px: float) -> None:
        s = self.seq[root] = self.seq.get(root, 0) + 1
        self.last[root] = px
        ms = ts_ns // 1_000_000
        if root not in self._until or ms >= self._until[root]:
            sess, self._until[root] = session_of(ms, root), _session_until(ms, root)
            if self.session.get(root) != sess:
                self.session[root] = sess
                self._expire(root, sess)
        if not self.orders:
            return
        tick = tick_size(root)
        while True:
            # engine.py L313-326: among the orders live on this print, the OLDEST that triggers fills first; then
            # the rest are looked at again on the same print (a fill's own bracket legs are not live on it yet)
            hit = next((o for o in self.orders.values() if o.root == root and o.status == "working"
                        and s >= o.min_seq and self._triggers(o, px, tick)), None)
            if hit is None:
                return
            if hit.kind == "stoplimit":
                self._do({"ev": "trigger", "id": hit.id}, seq=s)
                continue
            self._fid += 1
            self._do({"ev": "fill", "id": hit.id, "price": self._fill_price(hit, px, tick), "ts_ns": ts_ns,
                      "fid": self._fid}, seq=s)

    def _triggers(self, o: POrder, px: float, tick: float) -> bool:
        if o.kind == "market":                                           # engine.py L292-293
            return True
        if o.kind in ("stop", "stoplimit"):                              # engine.py L294-296: touch
            lvl = o.trigger if o.kind == "stoplimit" else o.price
            return tick_cmp(px, lvl, tick) >= 0 if o.side > 0 else tick_cmp(px, lvl, tick) <= 0
        if o.side > 0:                                                   # engine.py L297-300: 1-tick penetration
            return tick_cmp(px, to_tick(o.price - tick, tick), tick) <= 0
        return tick_cmp(px, to_tick(o.price + tick, tick), tick) >= 0

    def _fill_price(self, o: POrder, p: float, tick: float) -> float:
        slip = self.costs.slippage_ticks * tick                          # engine.py L267
        if o.kind == "limit":                                            # engine.py L303-304: at the limit
            return o.price
        if o.kind == "stop":                                             # engine.py L305-306: the gap + slip
            raw = max(o.price, p) + slip if o.side > 0 else min(o.price, p) - slip
        else:                                                            # engine.py L307-308: market +/- slip
            raw = p + o.side * slip
        return to_tick(raw, tick)

    def _expire(self, root: str, sess: str) -> None:
        """A new session on `root`: Day ENTRIES placed for an earlier one are cancelled (bracket legs of a filled
        position are not -- the book never leaves a paper position naked by itself)."""
        ids = [o.id for o in self.orders.values() if o.root == root and o.tif == "Day"
               and o.role in ("entry", "flat") and o.session and o.session < sess]
        if ids:
            self._do({"ev": "cancel", "ids": ids, "why": "expired"})

    # ---- the page's actions (the desk's request shapes: trading.py parse_*) -----------------------------------
    def _next_id(self) -> str:
        self._id += 1
        return str(self._id)

    def _root(self, body: dict) -> str:
        r = body.get("root")
        if not isinstance(r, str) or not _ROOT.fullmatch(r.upper()):
            raise ValueError("root: a symbol root such as NQ")
        return r.upper()

    def _order_id(self, body: dict) -> str:
        o = body.get("order_id")
        if isinstance(o, int) and not isinstance(o, bool):
            o = str(o)
        if not isinstance(o, str) or not _ORDER_ID.fullmatch(o):
            raise ValueError("order_id: a paper order id")
        return o

    def _once(self, action: str, cid: str, work: Callable[[], dict]) -> dict:
        now = self.mono()
        for k in [k for k, (t, _) in self._done.items() if now - t > DEDUP_TTL_S]:
            del self._done[k]
        hit = self._done.get((action, cid))
        if hit is not None:
            return hit[1]
        try:
            res = work()
        except Refused as e:
            res = {"ok": False, "order_id": None, "error": str(e), "refused": True}
        out = {"results": {PAPER_ID: res}}
        self._done[(action, cid)] = (now, out)
        return out

    def act(self, action: str, body) -> dict:
        """POST /api/paper/{action}: {"results": {"paper": {ok, order_id, error}}} like the desk's. A malformed
        body raises ValueError (HTTP 400); a guard's refusal is an ok=false result."""
        if action not in ACTIONS:
            raise ValueError(f"unknown paper action {action!r}")
        if not isinstance(body, dict):
            raise ValueError("the body is a JSON object")
        cid = _client_id(body)
        _only_paper(body)
        if action == "order":
            return self._order(cid, body)
        if action in ("modify", "cancel"):
            oid = self._order_id(body)
            if action == "modify":
                price = _price(body.get("price"), "price", required=True)
                return self._once(action, cid, lambda: self._modify(oid, price))
            return self._once(action, cid, lambda: self._cancel(oid))
        root = self._root(body)
        fn = {"cancel-symbol": self._cancel_symbol, "flatten": self._flatten, "reverse": self._reverse}[action]
        return self._once(action, cid, lambda: fn(root))

    def _order(self, cid: str, body: dict) -> dict:
        side, typ, qty = body.get("side"), body.get("type"), body.get("qty")
        if side not in SIDES:
            raise ValueError("side: Buy or Sell")
        if typ not in TYPES:
            raise ValueError("type: Market, Limit, Stop or StopLimit")
        if isinstance(qty, bool) or not isinstance(qty, int):
            raise ValueError("qty: a whole number")
        price = _price(body.get("price"), "price", required=typ != "Market")
        if typ == "Market" and price is not None:
            raise ValueError("a Market order carries no price")
        if typ != "StopLimit" and body.get("trigger_price") is not None:
            raise ValueError("only a Stop Limit order carries a trigger_price")
        trigger = _price(body.get("trigger_price"), "trigger_price", required=typ == "StopLimit")
        sl, tp = _price(body.get("sl_price"), "sl_price"), _price(body.get("tp_price"), "tp_price")
        tif = body.get("tif", "Day")
        if tif not in TIFS:
            raise ValueError("tif: Day or GTC")
        if typ == "Market" and tif != "Day":
            raise ValueError("a Market order is Day only")
        root = self._root(body)
        return self._once("order", cid, lambda: self._place(root, SIDES[side], typ, qty, price, trigger, sl, tp, tif))

    def _working(self, root: str) -> list[POrder]:
        return [o for o in self.orders.values() if o.root == root and o.status == "working"]

    def _place(self, root, side, typ, qty, price, trigger, sl, tp, tif) -> dict:
        if self.roots and root not in self.roots:
            raise Refused(f"{root} is not streamed by this chart service — no prints to fill against")
        if not 1 <= qty <= MAX_ORDER_QTY:                                  # trading.py guard 3
            raise Refused(f"quantity must be 1-{MAX_ORDER_QTY}")
        net = (self.pos.get(root) or {}).get("net", 0)
        worst = _worst_net(net, [(o.side, o.qty) for o in self._working(root)], side, qty)
        if worst > MAX_POSITION_QTY:
            raise Refused(f"that could take {root} on {LABEL} to {worst} contracts (limit {MAX_POSITION_QTY})")
        tick = tick_size(root)
        rnd = (lambda p: None if p is None else to_tick(p, tick))
        price, trigger, sl, tp = rnd(price), rnd(trigger), rnd(sl), rnd(tp)
        self._check_prices(root, side, typ, price, trigger, sl, tp, tick)
        now = self.clock_ms()
        contract = resolve_contract(root)
        base = {"root": root, "symbol": contract, "side": side, "qty": qty, "placed_ms": now,
                "session": session_of(now, root)}
        eid = self._next_id()
        kind = {"Market": "market", "Limit": "limit", "Stop": "stop", "StopLimit": "stoplimit"}[typ]
        entry = POrder(id=eid, type=typ, kind=kind, price=price, trigger=trigger, tif=tif, sl=sl, tp=tp, **base)
        legs = []
        if sl is not None:
            legs.append(POrder(id=self._next_id(), type="Stop", kind="stop", price=sl, trigger=None, tif="GTC",
                               role="sl", parent=eid, oco=eid, status="held", **{**base, "side": -side}))
        if tp is not None:
            legs.append(POrder(id=self._next_id(), type="Limit", kind="limit", price=tp, trigger=None, tif="GTC",
                               role="tp", parent=eid, oco=eid, status="held", **{**base, "side": -side}))
        self._do({"ev": "place", "orders": [_od(o) for o in (entry, *legs)]}, seq=self.seq.get(root, 0))
        return {"ok": True, "order_id": eid, "error": None}

    def _check_prices(self, root, side, typ, price, trigger, sl, tp, tick) -> None:
        """trading.py check_prices, against this book's own last print (any age: the page checked freshness)."""
        last = self.last.get(root)
        buy = side > 0
        if typ in ("Stop", "StopLimit"):
            what, lvl = ("stop", price) if typ == "Stop" else ("stop limit's trigger", trigger)
            if last is None:
                raise Refused(f"no {root} print yet — a {what} needs a price to check against")
            if buy and tick_cmp(lvl, last, tick) <= 0:
                raise Refused(f"a buy {what} must be above the last price ({last:,})")
            if not buy and tick_cmp(lvl, last, tick) >= 0:
                raise Refused(f"a sell {what} must be below the last price ({last:,})")
        if typ == "StopLimit":
            if buy and tick_cmp(price, trigger, tick) < 0:
                raise Refused("a buy stop limit's limit must be at or above its trigger")
            if not buy and tick_cmp(price, trigger, tick) > 0:
                raise Refused("a sell stop limit's limit must be at or below its trigger")
            if round(abs(price - trigger) / tick) > STOPLIMIT_MAX_TICKS:
                raise Refused(f"a stop limit's limit must be within {STOPLIMIT_MAX_TICKS} ticks of its trigger")
        if sl is not None or tp is not None:
            ref = price if typ != "Market" else last
            if ref is None:
                raise Refused(f"no {root} print yet — a bracket on a market order needs a price")
            sgn = 1 if buy else -1
            if typ == "StopLimit" and sl is not None and not sgn * (trigger - sl) > 0:
                raise Refused("the stop loss must be beyond the trigger price")
            if sl is not None and not sgn * (ref - sl) > 0:
                raise Refused("the stop loss must be on the losing side of the entry")
            if tp is not None and not sgn * (tp - ref) > 0:
                raise Refused("the target must be on the winning side of the entry")

    def _find(self, oid: str) -> POrder:
        o = self.orders.get(oid)
        if o is None or o.status != "working":
            raise Refused(f"order {oid} is not working on {LABEL}")
        return o

    def _modify(self, oid: str, price: float) -> dict:
        o = self._find(oid)
        if o.type == "StopLimit":
            raise Refused("Stop Limit orders can't be moved — cancel and place again")
        if o.type not in ("Limit", "Stop"):
            raise Refused(f"only Limit and Stop orders can be moved (this one is {o.type})")
        tick = tick_size(o.root)
        px = to_tick(price, tick)
        if o.type == "Stop":
            self._check_prices(o.root, o.side, "Stop", px, None, None, None, tick)
        self._do({"ev": "modify", "id": oid, "price": px})
        return {"ok": True, "order_id": oid, "error": None}

    def _cancel(self, oid: str) -> dict:
        self._find(oid)
        self._do({"ev": "cancel", "ids": [oid]})
        return {"ok": True, "order_id": oid, "error": None}

    def _cancel_all(self, root: str) -> None:
        ids = [o.id for o in self.orders.values() if o.root == root and o.parent is None]
        ids += [o.id for o in self.orders.values() if o.root == root and o.parent is not None and o.parent not in ids]
        if ids:
            self._do({"ev": "cancel", "ids": ids})

    def _market(self, root: str, side: int, qty: int, role: str) -> None:
        now = self.clock_ms()
        o = POrder(id=self._next_id(), root=root, symbol=(self.pos.get(root) or {}).get("symbol") or resolve_contract(root),
                   side=side, type="Market", kind="market", price=None, trigger=None, qty=qty, role=role,
                   placed_ms=now, session=session_of(now, root))
        self._do({"ev": "place", "orders": [_od(o)]}, seq=self.seq.get(root, 0))

    def _cancel_symbol(self, root: str) -> dict:
        self._cancel_all(root)
        return {"ok": True, "order_id": None, "error": None}

    def _flatten(self, root: str) -> dict:
        """Cancel every order in the root, then close the position at market (it fills on the next print)."""
        self._cancel_all(root)
        net = (self.pos.get(root) or {}).get("net", 0)
        if net:
            self._market(root, -1 if net > 0 else 1, abs(net), "flat")
        return {"ok": True, "order_id": None, "error": None}

    def _reverse(self, root: str) -> dict:
        net = (self.pos.get(root) or {}).get("net", 0)
        if not net:
            raise Refused(f"no {root} position on {LABEL} to reverse")
        if abs(net) > MAX_ORDER_QTY or abs(net) > MAX_POSITION_QTY:
            raise Refused(f"reversing {abs(net)} is over the per-order limit ({MAX_ORDER_QTY})")
        self._cancel_all(root)
        side = -1 if net > 0 else 1
        self._market(root, side, abs(net), "flat")       # the close, then the open: both on the next print, in order
        self._market(root, side, abs(net), "entry")
        return {"ok": True, "order_id": str(self._id), "error": None}

    # ---- what the page sees (the desk's account_view shape: trading.py ChartDesk.account_view) -----------------
    def view(self) -> dict:
        positions = [{"symbol": p["symbol"], "net": p["net"], "avg_price": round(p["avg"], 6), "root": r,
                      "point_value": point_value(r)} for r, p in sorted(self.pos.items()) if p["net"]]
        return {"id": PAPER_ID, "label": LABEL, "pinned": None, "broker_account": None, "env": "paper",
                "connected": True, "error": None, "tradable": True,
                "balance": round(START_BALANCE + self.realized, 2), "realized_pnl": round(self.realized, 2),
                "positions": positions,
                "orders": [_order_view(o) for o in self.orders.values() if o.status == "working"],
                "fills": list(self.fills), "strategies": []}

    def message(self, clear: bool = True) -> dict:
        """The /ws push: {"type": "paperbook", "account": <view>, "limits": {...}}; clears `dirty` unless a single
        page is being greeted (`clear=False`)."""
        if clear:
            self.dirty = False
        return {"type": "paperbook", "account": self.view(),
                "limits": {"max_order_qty": MAX_ORDER_QTY, "max_position_qty": MAX_POSITION_QTY}}


def _od(o: POrder) -> dict:
    d = asdict(o)
    d.pop("min_seq", None)
    return d


def _order_view(o: POrder) -> dict:
    """A working order as the desk's adapter shows one (tradovate.py trade_view): a Stop's level in stop_price, a
    Stop Limit's limit in price and its trigger in stop_price + trigger."""
    stop = o.price if o.type == "Stop" else o.trigger if o.type == "StopLimit" else None
    limit = o.price if o.type in ("Limit", "StopLimit") else None
    row = {"order_id": o.id, "symbol": o.symbol, "side": SIDE_NAME[o.side], "type": o.type, "qty": o.qty,
           "price": limit, "stop_price": stop, "status": "Working", "tif": o.tif, "owner": None, "role": o.role}
    if o.type == "StopLimit":
        row["trigger"] = o.trigger
    return row


def _iso(ts_ns: int) -> str:
    return dt.datetime.fromtimestamp(ts_ns / 1e9, dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class _NonFinite(ValueError):
    pass


def _reject(token: str):
    raise _NonFinite(token)


def register(app, *, book: Optional[PaperBook], browser_write_ok, allowed: frozenset = netguard.allowlist()) -> None:
    """GET /api/paper/book and POST /api/paper/{order|modify|cancel|cancel-symbol|flatten|reverse} -- the desk
    proxy's request rules (desk.py register): the Host allowlist, the Origin, JSON only, this service's own
    origin rule, 4 KB, no NaN. Nothing here forwards anything anywhere: the book answers itself. The existing
    forward-test routes (GET /api/paper/strategies, /api/paper/history) are GETs and are left alone."""

    @app.get("/api/paper/book")
    async def paper_book(request: Request):
        bad = netguard.refusal(request.method, request.scope["headers"], allowed)
        if bad is not None:
            raise HTTPException(*bad)
        if book is None:
            raise HTTPException(503, LIVE_ONLY)
        return {"account": book.view(), "limits": {"max_order_qty": MAX_ORDER_QTY, "max_position_qty": MAX_POSITION_QTY}}

    @app.post("/api/paper/{action}")
    async def paper_action(action: str, request: Request):
        bad = netguard.refusal(request.method, request.scope["headers"], allowed)
        if bad is not None:
            raise HTTPException(*bad)
        browser_write_ok(request)
        if action not in ACTIONS:
            raise HTTPException(404, f"unknown paper action {action!r}")
        if book is None:
            raise HTTPException(503, LIVE_ONLY)
        cl = request.headers.get("content-length")
        if cl is not None and (not cl.isdigit() or int(cl) > BODY_MAX):
            raise HTTPException(413, "request too large (4 KB max)")
        raw = b""
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > BODY_MAX:
                raise HTTPException(413, "request too large (4 KB max)")
        try:
            body = json.loads(raw, parse_constant=_reject)
        except _NonFinite:
            raise HTTPException(400, "invalid number") from None
        except ValueError:
            raise HTTPException(400, "the body is not JSON") from None
        try:
            out = book.act(action, body)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return JSONResponse(out)
