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
analogue of the engine's min_i with placement_ms = 0). A Stop Limit (the engine has none) triggers like a stop,
never fills on its trigger print (pessimistic, like the engine's bracket rule), and on the NEXT print fills like a
market order capped at its limit (print +/- slip, never worse than the limit) when that print is at or better
than the limit; a print beyond the limit leaves it resting as an ordinary 1-tick-penetration limit. Prints the service missed (a feed gap) are never invented: a stop
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
import os
import re
import time
import unicodedata
from collections import deque
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response

from .. import netguard
from ..backtest.engine import Costs, tick_cmp, to_tick
from ..contracts import point_value, tick_size
from ..symbols import resolve_contract
from . import _jsonl

PAPER_ID = "paper"                # the first (built-in) paper account; every other one is "paper-<n>"
LABEL = "PAPER"
START_BALANCE = 50_000.0          # a paper account's default opening cash
MIN_BALANCE, MAX_BALANCE = 1_000.0, 10_000_000.0
MAX_ACCOUNTS = 20                 # paper accounts at once (the page's account lists are not built for hundreds)
NAME_MAX = 32
# "paper" or "paper-<n>" -- never a colon, so no id can collide with a forward-test algo key "paper:<strategy>"
PAPER_ID_RE = re.compile(r"paper(?:-[1-9][0-9]{0,5})?")
# fix round 1 (I2): what a paper account's name may be -- see clean_name()
_LOOKALIKE = str.maketrans({                      # letters that pass for p/a/e/r in "PAPER" (Cyrillic, Greek)
    "\u0440": "p", "\u0420": "p", "\u03c1": "p", "\u03a1": "p",
    "\u0430": "a", "\u0410": "a", "\u03b1": "a", "\u0391": "a",
    "\u0435": "e", "\u0415": "e", "\u03b5": "e", "\u0395": "e",
    "\u0433": "r", "\u0413": "r"})
# the desk page (:8850) may create / remove / list paper accounts -- EXACTLY these origins, only on those routes
DESK_ORIGINS = frozenset({"http://localhost:8850", "http://127.0.0.1:8850"})
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
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return False
    try:
        return math.isfinite(v)
    except OverflowError:                       # fix round 1 (M1): a 400-digit int is not a number we take
        return False


def clean_name(raw) -> str:
    """A paper account's name, or ValueError (fix round 1, I2): NFKC-normalised, trimmed, 1-NAME_MAX characters,
    at least one visible one, and none in Unicode category C* (control, format -- zero-width, bidi overrides and
    isolates, BOM --, surrogate, private use, unassigned) or Zl / Zp (line / paragraph separators)."""
    if not isinstance(raw, str):
        raise ValueError("name: text")
    name = unicodedata.normalize("NFKC", raw).strip()
    bad = [c for c in name if unicodedata.category(c)[0] == "C" or unicodedata.category(c) in ("Zl", "Zp")]
    if bad:
        raise ValueError("name: no control, invisible or text-direction characters")
    if not name or not 1 <= len(name) <= NAME_MAX:
        raise ValueError(f"name: 1-{NAME_MAX} characters")
    return name


def name_key(name: str) -> str:
    """What two names are compared by: NFKC + casefold (so "Scalps" / "SCALPS" / "Ｓｃａｌｐｓ" collide)."""
    return unicodedata.normalize("NFKC", name).casefold()


def looks_like_paper(name: str) -> bool:
    """"PAPER" is the built-in's: reserved in any look-alike spelling -- case, width, spacing or punctuation
    ("P.A.P.E.R", "p a p e r") and the Cyrillic / Greek letters that pass for its own."""
    letters = "".join(c for c in name_key(name).translate(_LOOKALIKE) if c.isalnum())
    return letters == "paper"


def _atomic_json(path: Path, data) -> None:
    """Fix round 1 (I3): write, fsync the file, rename over, fsync the directory -- a power loss leaves the old
    file or the new one, never an empty one."""
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(data))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


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


def is_paper_id(x) -> bool:
    return isinstance(x, str) and PAPER_ID_RE.fullmatch(x) is not None


def _only_paper(body: dict, aid: str = PAPER_ID) -> None:
    """A book takes ITS OWN account and nothing else -- the page splits a mixed send, and PaperBooks splits a
    send across paper accounts; an id here that is not this book's means a split failed, and it is refused whole
    rather than guessed at (fail closed). Every account key a body carries must name it (fix round 1, M7)."""
    if "accounts" not in body and "account" not in body:
        raise ValueError(f"account: this paper book takes only {aid!r}")
    if "accounts" in body:
        a = body.get("accounts")
        if not isinstance(a, list) or not a or any(x != aid for x in a):
            raise ValueError(f"accounts: this paper book takes only [{aid!r}]")
    if "account" in body and body.get("account") != aid:
        raise ValueError(f"account: this paper book takes only {aid!r}")


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
    kind: str                        # the fill law's: market | limit | stop | stoplimit (untriggered) |
                                     # triggered (a Stop Limit's first live print: market capped at its limit)
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
                 log: Callable[[str], None] = lambda m: None, account_id: str = PAPER_ID, label: str = LABEL,
                 start_balance: float = START_BALANCE):
        if not is_paper_id(account_id):
            raise ValueError(f"not a paper account id: {account_id!r}")
        self.id, self.label, self.start_balance = account_id, label, float(start_balance)
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
        self._heal()
        for ev in _jsonl.read_all(self.path):
            try:
                self._apply(ev, seq=0)
            except Exception as e:  # noqa: BLE001 — one bad line never loses the rest of the book
                self.log(f"paperbook: skipped a bad event {str(ev)[:120]}: {type(e).__name__}: {e}")
        for o in self.orders.values():
            o.min_seq = 0                            # a restart: every working order may fill on the next print

    def _heal(self) -> None:
        """Fix round 1, I2: a crash mid-append leaves a torn last line with no newline; the next append would glue
        onto it and BOTH events would be lost on the following load. Cut the file back to its last complete line
        before anything can append."""
        try:
            with open(self.path, "rb+") as f:
                data = f.read()
                if data and not data.endswith(b"\n"):
                    keep = data.rfind(b"\n") + 1
                    f.truncate(keep)
                    self.log(f"paperbook: cut a torn last line ({len(data) - keep} bytes) from {self.path.name}")
        except FileNotFoundError:
            pass

    def _do(self, ev: dict, seq: int = 0) -> None:
        # fix round 1, M5: persisted FIRST -- an append that fails (disk full) raises before the book changes, so
        # memory never holds what a restart would not, and a retried client_id is not answered from a ghost
        if self.path is not None:
            _jsonl.append(self.path, ev)
        self._apply(ev, seq=seq)
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
        elif kind == "trigger":                      # a Stop Limit touched its trigger: live as a limit from the NEXT print
            o = self.orders[ev["id"]]
            o.kind, o.min_seq = "triggered", seq + 1
        elif kind == "rest":                         # a triggered Stop Limit whose first print was beyond its limit
            self.orders[ev["id"]].kind = "limit"
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
            if hit.kind == "triggered" and not self._marketable(hit, px, tick):
                self._do({"ev": "rest", "id": hit.id}, seq=s)   # from now on an ordinary resting limit
                continue
            self._fid += 1
            self._do({"ev": "fill", "id": hit.id, "price": self._fill_price(hit, px, tick), "ts_ns": ts_ns,
                      "fid": self._fid}, seq=s)

    def _triggers(self, o: POrder, px: float, tick: float) -> bool:
        if o.kind in ("market", "triggered"):                            # engine.py L292-293 (a triggered Stop
            return True                                                  # Limit's first live print: see _fill_price)
        if o.kind in ("stop", "stoplimit"):                              # engine.py L294-296: touch
            lvl = o.trigger if o.kind == "stoplimit" else o.price
            return tick_cmp(px, lvl, tick) >= 0 if o.side > 0 else tick_cmp(px, lvl, tick) <= 0
        if o.side > 0:                                                   # engine.py L297-300: 1-tick penetration
            return tick_cmp(px, to_tick(o.price - tick, tick), tick) <= 0
        return tick_cmp(px, to_tick(o.price + tick, tick), tick) >= 0

    @staticmethod
    def _marketable(o: POrder, p: float, tick: float) -> bool:
        """A triggered Stop Limit's limit is a CAP: the print is at or better than it."""
        return tick_cmp(p, o.price, tick) <= 0 if o.side > 0 else tick_cmp(p, o.price, tick) >= 0

    def _fill_price(self, o: POrder, p: float, tick: float) -> float:
        slip = self.costs.slippage_ticks * tick                          # engine.py L267
        if o.kind == "triggered":
            # fix round 1, I1: on its first live print a triggered Stop Limit is a MARKET order capped at its limit
            # (a real exchange fills a marketable limit at the market, never at the far cap): the print +/- slip,
            # never worse than the limit -- the engine's market fill (L307-308) with the limit as a bound
            raw = min(o.price, p + slip) if o.side > 0 else max(o.price, p - slip)
            return to_tick(raw, tick)
        if o.kind == "limit":                                            # engine.py L303-304: at the limit
            return o.price
        if o.kind == "stop":                                             # engine.py L305-306: the gap + slip
            raw = max(o.price, p) + slip if o.side > 0 else min(o.price, p) - slip
        else:                                                            # engine.py L307-308: market +/- slip
            raw = p + o.side * slip
        return to_tick(raw, tick)

    def _expire(self, root: str, sess: str) -> None:
        """A new session on `root`: Day ENTRIES placed for an earlier one are cancelled. Protective legs (SL/TP) and
        closing orders (a flatten's / reverse's close) never expire (fix round 1, M4): the book never leaves a
        paper position open or naked by itself."""
        ids = [o.id for o in self.orders.values() if o.root == root and o.tif == "Day"
               and o.role == "entry" and o.session and o.session < sess]
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
        out = {"results": {self.id: res}}
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
        _only_paper(body, self.id)
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
            raise Refused(f"that could take {root} on {self.label} to {worst} contracts (limit {MAX_POSITION_QTY})")
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
            raise Refused(f"order {oid} is not working on {self.label}")
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
            raise Refused(f"no {root} position on {self.label} to reverse")
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
        return {"id": self.id, "label": self.label, "pinned": None, "broker_account": None, "env": "paper",
                "connected": True, "error": None, "tradable": True,
                "start_balance": self.start_balance, "balance": round(self.start_balance + self.realized, 2), "realized_pnl": round(self.realized, 2),
                "positions": positions,
                "orders": [_order_view(o) for o in self.orders.values() if o.status == "working"],
                "fills": list(self.fills), "strategies": []}

    def busy(self) -> bool:
        """An open position or any order (working, or a bracket leg waiting on its entry)."""
        return bool(self.orders) or any(p["net"] for p in self.pos.values())


LIMITS = {"max_order_qty": MAX_ORDER_QTY, "max_position_qty": MAX_POSITION_QTY}


class PaperBooks:
    """Every paper account the user made (2026-09-27 Task 2b), each with its OWN book (PaperBook) and its OWN log:
    the first, built-in "paper" keeps paper/book.jsonl exactly where it always was (its book carries over untouched);
    "paper-<n>" logs to paper/books/paper-<n>.jsonl. The list is paper/accounts.json ({next, accounts: [{id, label,
    start_balance, created_ms}]}, written atomically). Ids are never reused: `next` only grows. Removing an account
    is refused while it holds a position or any order; a removed account's log moves to paper/archive/ and its
    record is appended to paper/archive/accounts.jsonl -- archived, never deleted. `dir` None: in memory only."""

    def __init__(self, dir: Optional[Path], *, roots=(), clock_ms: Callable[[], int] = lambda: int(time.time() * 1000),
                 costs: Optional[Costs] = None, mono: Callable[[], float] = time.monotonic,
                 log: Callable[[str], None] = lambda m: None):
        self.dir = Path(dir) if dir is not None else None
        self.kw = {"roots": roots, "clock_ms": clock_ms, "costs": costs, "mono": mono, "log": log}
        self.clock_ms, self.log = clock_ms, log
        self.books: dict[str, PaperBook] = {}
        self.meta: dict[str, dict] = {}
        self.next = 2
        self._dirty = True
        self.broken: Optional[str] = None            # why the registry cannot be trusted (fail closed), or None
        rows = self._read_registry()
        if not any(r["id"] == PAPER_ID for r in rows):   # the built-in first account, always there
            rows.insert(0, {"id": PAPER_ID, "label": LABEL, "start_balance": START_BALANCE, "created_ms": 0})
        self.next = max(self.next, self._max_seen(rows) + 1)
        for r in rows:
            self._open(r)
        if self.dir is not None and self.broken is None and not (self.dir / "accounts.json").exists():
            self._save()

    def _read_registry(self) -> list[dict]:
        """The registry's rows. Missing: a first start (the built-in only). Present but unreadable, not an object, or
        without an `accounts` list: BROKEN -- logged loudly, reported in status, creates and removes refused, and the
        file is never rewritten until someone repairs it (fix round 1, I3: never silently drop accounts). A single
        bad field is coerced or its row skipped, loudly (M4) -- never a crash at startup."""
        if self.dir is None:
            return []
        p = self.dir / "accounts.json"
        if not p.exists():
            return []
        try:
            reg = json.loads(p.read_text())
            if not isinstance(reg, dict) or not isinstance(reg.get("accounts"), list):
                raise ValueError("not {next, accounts: [...]}")
        except (OSError, ValueError) as e:
            self.broken = f"paper/accounts.json is unreadable ({type(e).__name__}: {e}) — user paper accounts are " \
                          "not loaded and none can be created or removed until it is repaired"
            self.log(f"paperbook: REGISTRY BROKEN: {self.broken}")
            return []
        try:
            self.next = max(2, int(reg.get("next") or 2))
        except (TypeError, ValueError):
            self.log(f"paperbook: accounts.json `next` {reg.get('next')!r} is not a number — derived from disk")
        rows = []
        for r in reg["accounts"]:
            if not isinstance(r, dict) or not is_paper_id(r.get("id")) or any(x["id"] == r["id"] for x in rows):
                self.log(f"paperbook: accounts.json row skipped: {str(r)[:120]}")
                continue
            try:
                bal = float(r.get("start_balance") or START_BALANCE)
                if not math.isfinite(bal) or bal <= 0:
                    raise ValueError(bal)
            except (TypeError, ValueError, OverflowError):
                self.log(f"paperbook: {r['id']}: start_balance {r.get('start_balance')!r} unreadable — $50,000 used")
                bal = START_BALANCE
            try:
                created = int(r.get("created_ms") or 0)
            except (TypeError, ValueError):
                created = 0
            rows.append({"id": r["id"], "label": str(r.get("label") or r["id"])[:NAME_MAX], "start_balance": bal,
                         "created_ms": created})
        return rows

    def _max_seen(self, rows: list[dict]) -> int:
        """The highest paper-<n> ever used: the registry, every log in books/, every archived log and every
        archived record (fix round 1, I3) -- so an id is never handed out twice, even after a lost registry."""
        n = [1] + [int(r["id"].split("-")[1]) for r in rows if r["id"] != PAPER_ID]
        if self.dir is not None:
            for f in list((self.dir / "books").glob("paper-*.jsonl")) + list((self.dir / "archive").glob("paper-*.jsonl")):
                m = re.match(r"paper-([1-9][0-9]{0,5})(?:-|\.jsonl$)", f.name)
                if m:
                    n.append(int(m.group(1)))
            for r in _jsonl.read_all(self.dir / "archive" / "accounts.jsonl"):
                if is_paper_id(r.get("id")) and r["id"] != PAPER_ID:
                    n.append(int(r["id"].split("-")[1]))
        return max(n)

    def status(self) -> dict:
        return {"accounts": len(self.books), "broken": self.broken}

    def path_for(self, aid: str) -> Optional[Path]:
        if self.dir is None:
            return None
        return self.dir / "book.jsonl" if aid == PAPER_ID else self.dir / "books" / f"{aid}.jsonl"

    def _open(self, r: dict) -> None:
        aid = r["id"]
        label = str(r.get("label") or aid)[:NAME_MAX]
        bal = float(r["start_balance"])
        self.meta[aid] = {"id": aid, "label": label, "start_balance": bal, "created_ms": int(r.get("created_ms") or 0)}
        self.books[aid] = PaperBook(self.path_for(aid), account_id=aid, label=label, start_balance=bal, **self.kw)

    def _save(self) -> None:
        if self.dir is None:
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        if self.broken is not None:                  # never overwrite a registry someone has to repair
            raise Refused(self.broken)
        _atomic_json(self.dir / "accounts.json", {"next": self.next, "accounts": list(self.meta.values())})

    # ---- the tick path and the page ----
    def on_ticks(self, root: str, rows: list) -> None:
        for b in self.books.values():
            b.on_ticks(root, rows)

    @property
    def dirty(self) -> bool:
        return self._dirty or any(b.dirty for b in self.books.values())

    def views(self) -> list[dict]:
        return [b.view() for b in self.books.values()]

    def message(self, clear: bool = True) -> dict:
        """The /ws push: {"type": "paperbook", "accounts": [<view>, ...], "limits"}; clears `dirty` unless a single
        page is being greeted (`clear=False`)."""
        out = {"type": "paperbook", "accounts": self.views(), "limits": dict(LIMITS)}
        if clear:
            self._dirty = False
            for b in self.books.values():
                b.dirty = False
        return out

    def listing(self) -> list[dict]:
        """GET /api/paper/accounts: what the desk page lists -- no orders or fills, just who and how much."""
        out = []
        for aid, b in self.books.items():
            v = b.view()
            out.append({"id": aid, "label": b.label, "env": "paper", "start_balance": b.start_balance,
                        "balance": v["balance"], "realized_pnl": v["realized_pnl"],
                        "positions": len(v["positions"]), "orders": len(b.orders), "removable": aid != PAPER_ID})
        return out

    # ---- orders: split per paper account, each book answers for itself ----
    def act(self, action: str, body) -> dict:
        if action not in ACTIONS:
            raise ValueError(f"unknown paper action {action!r}")
        if not isinstance(body, dict):
            raise ValueError("the body is a JSON object")
        _client_id(body)
        if "accounts" in body:
            ids = body.get("accounts")
            if not isinstance(ids, list) or not ids or not all(is_paper_id(x) for x in ids) or len(ids) > 20:
                raise ValueError("accounts: a list of paper account ids")
            if "account" in body:
                raise ValueError("send `accounts` or `account`, not both")
            ids = list(dict.fromkeys(ids))
        else:
            if not is_paper_id(body.get("account")):
                raise ValueError("account: a paper account id")
            ids = [body["account"]]
        results = {}
        for aid in ids:
            b = self.books.get(aid)
            if b is None:
                results[aid] = {"ok": False, "order_id": None, "error": f"paper account {aid} does not exist",
                                "refused": True}
                continue
            one = {**body, "accounts": [aid]} if "accounts" in body else body
            results.update(b.act(action, one)["results"])
        return {"results": results}

    # ---- create / remove ----
    def create(self, body) -> dict:
        if not isinstance(body, dict):
            raise ValueError("the body is a JSON object")
        if self.broken is not None:
            raise ValueError(self.broken)
        name = clean_name(body.get("name"))
        bal = body.get("start_balance", START_BALANCE)
        if not _finite(bal) or not MIN_BALANCE <= bal <= MAX_BALANCE:
            raise ValueError(f"start_balance: ${MIN_BALANCE:,.0f} to ${MAX_BALANCE:,.0f}")
        if looks_like_paper(name):
            raise ValueError(f"{LABEL!r} is the built-in account's name")
        if any(name_key(m["label"]) == name_key(name) for m in self.meta.values()):
            raise ValueError(f"a paper account is already called {name!r}")
        if len(self.books) >= MAX_ACCOUNTS:
            raise ValueError(f"at most {MAX_ACCOUNTS} paper accounts")
        self.next = max(self.next, self._max_seen(list(self.meta.values())) + 1)
        aid = f"paper-{self.next}"
        if self.path_for(aid) is not None and self.path_for(aid).exists():   # fail closed: never adopt a log
            raise ValueError(f"{aid}'s log already exists on disk — refusing to reuse it")
        self.next += 1
        r = {"id": aid, "label": name, "start_balance": float(bal), "created_ms": int(self.clock_ms())}
        self._open(r)
        try:
            self._save()
        except Exception:
            del self.books[aid], self.meta[aid]
            raise
        self._dirty = True
        return {"ok": True, "account": self.books[aid].view()}

    def remove(self, body) -> dict:
        """{"account": id} -> {ok, archived} or {ok: false, error} (still holding something / the built-in one)."""
        if not isinstance(body, dict) or not is_paper_id(body.get("account")):
            raise ValueError("account: a paper account id")
        aid = body["account"]
        b = self.books.get(aid)
        if b is None:
            return {"ok": False, "error": f"paper account {aid} does not exist"}
        if aid == PAPER_ID:
            return {"ok": False, "error": "the built-in PAPER account can't be removed"}
        if b.busy():
            return {"ok": False, "error": f"{b.label} has an open position or working orders — flatten it first"}
        if self.broken is not None:
            return {"ok": False, "error": self.broken}
        now = int(self.clock_ms())
        archived = None
        v = b.view()
        meta = self.meta.pop(aid)
        del self.books[aid]
        try:
            self._save()                             # fix round 1 (M5): the registry first -- a failed save changes
        except Exception:                            # nothing, not even the archive
            self.meta[aid], self.books[aid] = meta, b
            raise
        if self.dir is not None:
            arch = self.dir / "archive"
            arch.mkdir(parents=True, exist_ok=True)
            src = self.path_for(aid)
            if src.exists():
                archived = arch / f"{aid}-{now}.jsonl"
                src.replace(archived)
            _jsonl.append(arch / "accounts.jsonl", {**meta, "removed_ms": now, "balance": v["balance"],
                                                    "realized_pnl": v["realized_pnl"],
                                                    "log": archived.name if archived else None})
        self._dirty = True
        return {"ok": True, "archived": archived.name if archived else None}


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


def desk_origin_refusal(headers) -> Optional[tuple[int, str]]:
    """The create / remove / list routes: an Origin, when sent, must be this service's own page (scheme://Host) or
    EXACTLY the desk page's (DESK_ORIGINS) -- netguard's rule ignores ports, which is only safe without CORS, and
    these routes answer the desk page cross-origin. None: allowed."""
    origin = headers.get("origin")
    if origin is None:
        return None
    if origin in DESK_ORIGINS or origin == f"http://{headers.get('host', '')}":
        return None
    return 403, "origin not allowed"


def _cors(resp, request: Request):
    o = request.headers.get("origin")
    if o in DESK_ORIGINS:
        resp.headers["access-control-allow-origin"] = o
        resp.headers["vary"] = "Origin"
    return resp


async def _read_json(request: Request):
    cl = request.headers.get("content-length")
    if cl is not None and (not cl.isdigit() or int(cl) > BODY_MAX):
        raise HTTPException(413, "request too large (4 KB max)")
    raw = b""
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > BODY_MAX:
            raise HTTPException(413, "request too large (4 KB max)")
    try:
        return json.loads(raw, parse_constant=_reject)
    except _NonFinite:
        raise HTTPException(400, "invalid number") from None
    except ValueError:
        raise HTTPException(400, "the body is not JSON") from None


def register(app, *, books: Optional[PaperBooks], browser_write_ok, allowed: frozenset = netguard.allowlist()) -> None:
    """GET /api/paper/book, POST /api/paper/{order|modify|cancel|cancel-symbol|flatten|reverse} -- the desk proxy's
    request rules (desk.py register): the Host allowlist, the Origin, JSON only, this service's own origin rule,
    4 KB, no NaN. GET /api/paper/accounts, POST /api/paper/accounts/{create|remove} (Task 2b) add the same rules
    plus an EXACT origin check (desk_origin_refusal), and answer CORS for the desk page's two origins only. Nothing
    here forwards anything anywhere. The forward-test routes (GET /api/paper/strategies, /history) are left alone."""

    def guard(request: Request, write: bool) -> None:
        bad = netguard.refusal(request.method, request.scope["headers"], allowed)
        if bad is not None:
            raise HTTPException(*bad)
        if write:
            browser_write_ok(request)
        if books is None:
            raise HTTPException(503, LIVE_ONLY)

    @app.get("/api/paper/book")
    async def paper_book(request: Request):
        guard(request, False)
        return {"accounts": books.views(), "limits": dict(LIMITS)}

    def answered(request: Request, e: HTTPException):
        """Fix round 1 (M2): a refusal AFTER the exact origin check passed is readable by the desk page (so it can
        say why, not "unreachable"); a request whose origin failed that check never gets here."""
        return _cors(JSONResponse({"ok": False, "detail": e.detail}, status_code=e.status_code), request)

    @app.get("/api/paper/accounts")
    async def paper_accounts(request: Request):
        bad = desk_origin_refusal(request.headers)
        if bad is not None:
            raise HTTPException(*bad)
        try:
            guard(request, False)
        except HTTPException as e:
            return answered(request, e)
        return _cors(JSONResponse({"accounts": books.listing(), "broken": books.broken}), request)

    @app.options("/api/paper/accounts/{what}")
    async def paper_accounts_preflight(what: str, request: Request):
        """The desk page's CORS preflight: allowed for DESK_ORIGINS only (anything else: no allow-origin header,
        so the browser never sends the write)."""
        o = request.headers.get("origin")
        if what not in ("create", "remove") or o not in DESK_ORIGINS:
            return JSONResponse({"detail": "origin not allowed"}, status_code=403)
        return Response(status_code=204, headers={
            "access-control-allow-origin": o, "vary": "Origin", "access-control-allow-methods": "POST",
            "access-control-allow-headers": "content-type", "access-control-max-age": "600"})

    @app.post("/api/paper/accounts/{what}")
    async def paper_accounts_write(what: str, request: Request):
        bad = desk_origin_refusal(request.headers)
        if bad is not None:
            raise HTTPException(*bad)
        try:
            guard(request, True)
            if what not in ("create", "remove"):
                raise HTTPException(404, f"unknown paper accounts action {what!r}")
            body = await _read_json(request)
        except HTTPException as e:
            return answered(request, e)
        try:
            out = books.create(body) if what == "create" else books.remove(body)
        except ValueError as e:
            return _cors(JSONResponse({"ok": False, "detail": str(e)}, status_code=400), request)
        return _cors(JSONResponse(out), request)

    @app.post("/api/paper/{action}")
    async def paper_action(action: str, request: Request):
        bad = netguard.refusal(request.method, request.scope["headers"], allowed)
        if bad is not None:
            raise HTTPException(*bad)
        browser_write_ok(request)
        if action not in ACTIONS:
            raise HTTPException(404, f"unknown paper action {action!r}")
        if books is None:
            raise HTTPException(503, LIVE_ONLY)
        body = await _read_json(request)
        try:
            out = books.act(action, body)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return JSONResponse(out)
