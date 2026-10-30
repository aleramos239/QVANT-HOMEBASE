"""Vest Markets order adapter (NQ-PERP, API symbol NDX-USD-PERP): market / limit entries with SL/TP, flatten, fills.

Wire format: `.superpowers/sdd/2026-10-29-vest-broker/vest-orders-api.md` (read from the web app). Every field name sits in
the body builders (`_open_body`, `_modify`, `_flatten`, `parse_account_state`) so a day-one fix is one line.

Stop entries are held by Homebase (`vest_held.py`) and fired as a market bracket when a CME push trades the level
(`on_bar`, the feed hook), never late: not while the feed or the Vest session is down, not on the first push after a
gap, not past the slippage cap. Every entry (placed or fired) passes the loss-floor guard first; with no floors known it
is refused. StopLimit entries are refused.

Sizing: 1 NQ = 20 units, 1 MNQ = 2 units (1 unit = $1 a point); contracts in, contracts out.
Order methods never raise: a failure is `OrderResult(ok=False, error=...)`. Secrets are never logged (order bodies hold none).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import math
import time
import uuid
from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Callable, Optional

import httpx
import websockets

from ..core.clock import ET
from ..paths import state_dir
from .base import BrokerAdapter, FillCallback, FillEvent, OrderRequest, OrderResult
from .paper import root_of
from . import vest_auth
from .vest_auth import HEADERS, NeedsSignature, VestSession, urgent
from .vest_held import HeldBook, HeldEntry, _proot, floor_room, reached, slip_ok

log = logging.getLogger(__name__)

SYMBOL = "NDX-USD-PERP"
UNITS = {"NQ": 20, "MNQ": 2}
SIZE_DECIMALS = 4
WS_URL = "wss://ws.hz.vestmarkets.com/ws/private"
OUTCOME_S = 5.0                               # how long an order waits for its socket outcome before the REST reconcile
KEEP = 1000                                   # per-order memory (ids, seen quantities, outcomes): oldest dropped past this
POLL_S = 2.0                                  # fallback reads, only while the socket is down AND something rests / is open
WS_RETRY_S = 1.0                              # first wait before the private socket reconnects (doubles to 30 s)
NO_ACCT = "vest: no Vest account selected"
NOT_SUPPORTED = "vest: modify not supported"
ORDER_GONE = (3017, 10010, 11004)             # cancel: already gone
POSITION_GONE = (10009,)                      # close: no such position (10029, close already requested, is NOT gone)
EXIT_TAGS = ("homebase:flat", "homebase:kill", "homebase:lab-flat", "homebase:chart-exit")   # with no position: never open
UNCONFIRMED = "vest: unconfirmed — check Vest"
LOGIN_ENDING = "vest: wallet login ends within 12 h — sign again"
_STATUS = {"pending": "Working", "accepted": "Working", "partially_filled": "Working", "filled": "Filled",
           "cancelled": "Canceled", "rejected": "Rejected"}      # Vest order status -> the engine's words
DETAILS_TRIES = 3                             # a closed position whose /details fails this many reads: report it by size
DEFAULTS = {"tick": Decimal("0.25"), "price_dec": 2, "lev": "50"}
HELD = "held:"                                # order ids of the stop entries Homebase holds
GAP_S = 10.0                                  # a push this long after the previous one (or the first) never fires (R1)
SLOW_S = 2.0                                  # a fire whose /open would go out later than this after its push: skipped (R40)
PAIR_S = 1.0                                  # two opposite held legs added this close together are one signal (OCO)
DAY_START_KEY = "dayStartEquity"              # the account row's day-start equity: name unconfirmed (T7 Step 0)


# ---- pure helpers ------------------------------------------------------------------------------------------
def _dec(x) -> Decimal:
    return Decimal(str(x))


def _trim(d: Decimal, places: int, rounding) -> str:
    s = format(d.quantize(Decimal(1).scaleb(-places), rounding=rounding), "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def units_of(symbol: str, qty: int) -> str:
    root = root_of(symbol)
    if qty <= 0:
        raise ValueError("vest: quantity must be positive")
    if root not in UNITS:
        raise ValueError(f"vest: no sizing for {symbol!r} (NQ and MNQ only)")
    return _trim(Decimal(qty * UNITS[root]), SIZE_DECIMALS, ROUND_DOWN)


def _contracts(units: Decimal, root: str) -> int:
    """Units -> contracts of `root`, away from zero: a remainder never reads as flat (an exit closes the whole position)."""
    n = units / UNITS[root]
    return int(abs(n).to_integral_value(ROUND_CEILING)) * (1 if n >= 0 else -1)


def _cap(d: dict) -> None:
    while len(d) > KEEP:
        d.pop(next(iter(d)))


def _signed(row: dict) -> Decimal:
    q = _dec(row.get("quantity") or 0)
    return q if str(row.get("side")).lower() == "long" else -q


def _rows(j, *keys) -> list:
    if isinstance(j, list):
        return j
    for k in keys:
        if isinstance(j.get(k), list):
            return j[k]
    return []


def _err(e: Exception) -> tuple[Optional[int], str]:
    """(Vest error code or None, text for OrderResult.error). The text carries the code/msg of the body, nothing else."""
    if isinstance(e, httpx.HTTPStatusError):
        try:
            j = e.response.json()
            j = j["detail"] if isinstance(j.get("detail"), dict) else j
            code = int(j["code"])
            return code, f"vest {code}: {str(j.get('msg') or '')[:200]}"
        except (ValueError, KeyError, TypeError, AttributeError):
            return None, f"vest: HTTP {e.response.status_code}"
    if isinstance(e, NeedsSignature):
        return None, "vest: sign in again"
    return None, f"vest: {type(e).__name__}"


def _same_acct(v, acct) -> bool:
    """Vest may send an account id as a number; the desk saves it as text (R56)."""
    return v is not None and str(v) == str(acct)


def parse_account_state(msg: dict, *, account_id: str, vest_account_id: str, seen: dict,
                        roots: Optional[dict] = None, default_root: str = "NQ") -> list[FillEvent]:
    """Fills out of one `account_state` frame (the socket's, or one the poll built from /details). An order's
    executed_quantity is cumulative: `seen` (order id -> units already reported) turns it into per-fill deltas, so a
    replayed frame, or the same order from the other feed, yields nothing. Contracts are the difference of the
    cumulative contracts, so pieces never add up to more than the order."""
    d = msg.get("data") or {}
    if msg.get("channel") != "account_state" or not _same_acct(d.get("account_id"), vest_account_id):
        return []
    roots = roots or {}
    held = [p for p in d.get("positions") or [] if p.get("symbol") == SYMBOL]
    out = []
    for o in d.get("orders") or []:
        if o.get("symbol") != SYMBOL or not _same_acct(o.get("account_id", vest_account_id), vest_account_id):
            continue
        oid = str(o.get("order_id"))
        done = _dec(o.get("executed_quantity") or 0)
        before = seen.get(oid, Decimal(0))
        if done <= before:
            continue
        seen[oid] = done
        side = "Buy" if o.get("side") == "buy" else "Sell"
        root = roots.get(str(o.get("position_id"))) or roots.get(oid) or default_root
        qty = _contracts(done, root) - _contracts(before, root)
        if qty <= 0:                                # units are noted in `seen`; the contract shows once they complete it
            continue
        px = _dec(o.get("execution_price") or 0) or _dec(o.get("price") or 0)       # zero execution price: use the limit
        after = None
        if held:
            after = _contracts(sum((Decimal(0) if str(p.get("event_type", "")).endswith("CLOSED") else _signed(p)
                                    for p in held), Decimal(0)), root)
        out.append(FillEvent(account_id=account_id, symbol=root, side=side,
                             qty=qty, price=float(px) if px else None, position_after=after,
                             ts=time.time(), raw={"orderId": oid, "positionId": o.get("position_id"),
                                                  "order_type": o.get("order_type"), "units": str(done - before)},
                             seen=time.perf_counter()))
    return out


def poll_changes(prev: Optional[dict], rows: list, *, vest_account_id: str) -> tuple[list, dict]:
    """Fallback when the socket is down: (position ids whose size changed since the last read, the new sizes). First
    read (prev None): nothing changed, it only seeds."""
    cur = {str(r["positionId"]): _signed(r) for r in rows
           if _same_acct(r.get("accountId"), vest_account_id) and r.get("symbol") == SYMBOL}
    if prev is None:
        return [], cur
    return [p for p in sorted(cur.keys() | prev.keys()) if cur.get(p, Decimal(0)) != prev.get(p, Decimal(0))], cur


def details_frame(pid: str, detail: dict, *, vest_account_id: str) -> dict:
    """A position's /details orders as an `account_state` frame, so the poll reports fills through the same per-order
    dedup as the socket. The rows may carry no side: an opening order has the position's side, a closing one the other.
    A row with no marker of either is never guessed: it goes to `skipped` (the poll retries it)."""
    pos = detail.get("position") or {}
    long_ = str(pos.get("side")).lower() == "long"
    orders, skipped = [], []
    for o in pos.get("orders") or []:
        kind = str(o.get("position_order_type")).lower().rsplit("_", 1)[-1]        # "close" or "POSITION_ORDER_TYPE_CLOSE"
        closing = (o.get("reduce_only") is True or kind in ("close", "reduce")
                   or str(o.get("order_type")).lower() in ("take_profit", "stop_loss"))
        if not (o.get("side") or closing or kind in ("open", "append")):
            skipped.append(o)
            continue
        orders.append({**o, "symbol": SYMBOL, "account_id": vest_account_id, "position_id": str(pid),
                       "side": o.get("side") or ("buy" if long_ != closing else "sell")})
    return {"channel": "account_state", "data": {"account_id": vest_account_id, "positions": [], "orders": orders},
            "skipped": skipped}


# ---- adapter -----------------------------------------------------------------------------------------------
class VestAdapter(BrokerAdapter):
    platform = "vest"

    def __init__(self, account_id: str, *, keyring_key: str, vest_account_id: str, session: VestSession | None = None,
                 floors: dict | None = None, slip_frac: float = 0.5, root: str = "NQ",
                 journal: Optional[Callable[..., None]] = None):
        super().__init__(account_id, live=True)
        self.vest_account_id = vest_account_id          # "" = probe: connect + list_accounts only, no orders
        self.session = session or VestSession(keyring_key)
        self._own_session = session is None
        self.root = root                                # this account's contract root (fills after a restart use it)
        # floors: {"max_drawdown_equity", "daily_loss"} (AccountCfg.floors); none -> every entry refused
        self.floors, self.slip_frac = floors, slip_frac
        self.journal = journal or (lambda event, **kw: None)
        self.feed_ok: Callable[[], bool] = lambda: False    # the CME feed is up (wired by the desk); default: never fire
        self._now = lambda: dt.datetime.now(ET)
        self._mono = time.monotonic
        self._book = HeldBook(state_dir() / f"vest_held_{account_id}.json")
        self._restored = False                          # the saved book is pruned at the first CME push
        self._pushed: dict[str, float] = {}             # feed root -> monotonic time of its last push (feed up)
        self._firing: Optional[str] = None              # the held id whose market open is in flight
        self._fires: set[asyncio.Task] = set()
        self._parked: list[FillEvent] = []              # fills seen while a fire waits for its POST answer (R30)
        self._added: dict[str, float] = {}              # held id -> monotonic time it was added (OCO pairing)
        self._entry_lock = asyncio.Lock()               # floor guard + POST of one entry at a time (R39)
        self._sweeping = 0                              # sweeps running: entries not yet POSTed are refused (R41)
        self._sweeps = 0                                # sweeps ever started: a hold that spans one is refused
        self._held_of: dict[str, str] = {}              # Vest order id -> held id (its fills carry the held id, R30)
        self._risk: dict[str, Decimal] = {}             # resting limit entry id -> $ at risk to its stop
        self._sp: Optional[dict] = None
        self._roots: dict[str, str] = {}                # order id / position id -> root we placed it with
        self._on_fill: Optional[FillCallback] = None
        self._tasks: list[asyncio.Task] = []
        self._ws_up = False
        self._busy = True                               # poll fallback: something may rest / be open
        self._seq = 0                                   # last account_seq seen on the socket
        self._seen: dict[str, Decimal] = {}
        self._events: dict[str, tuple[str, Optional[str]]] = {}     # command / order id -> (status, error) off the socket
        self._pos_of: dict[str, str] = {}               # order id -> position id (for get_order_status)
        self._closed_pids: dict[str, bool] = {}         # positions whose exit the poll reported: later fills on them dropped
        # the last known picture (R59): position id -> signed units and resting order id -> position id, as the last read
        # or the socket since then left it; None until the first read. The poll and a reconnect diff against it.
        self._known: Optional[dict[str, Decimal]] = None
        self._known_orders: dict[str, str] = {}
        self._pass_lock = asyncio.Lock()                # one read-and-diff pass at a time
        self._fails: dict[str, int] = {}                # position id -> /details failures in a row
        self._warned: dict[str, bool] = {}

    # --- plumbing ---------------------------------------------------------------------------------
    async def _api(self, method: str, path: str, *, account: bool = True, **kw):
        resp = await self.session.request(method, path, account_id=self.vest_account_id if account else None, **kw)
        return resp.json() if resp.content else {}

    async def _guard(self, work) -> OrderResult:
        if not self.vest_account_id:
            return OrderResult(ok=False, error=NO_ACCT)
        try:
            return await work()
        except Exception as e:  # noqa: BLE001 -- an order method never raises (a raise is a reject)
            log.warning("vest %s: order call failed: %s", self.account_id, type(e).__name__)
            return OrderResult(ok=False, error=_err(e)[1])

    async def _post(self, path: str, body: dict, gone: tuple = ()) -> Optional[str]:
        """POST an order action; None = done (or already gone), else the error text. Never raises."""
        log.debug("vest %s: POST %s %s", self.account_id, path, body)
        try:
            await self._api("POST", path, json=body)
        except Exception as e:  # noqa: BLE001
            code, text = _err(e)
            return None if code in gone else text
        return None

    async def _spec(self) -> dict:
        """Tick, price decimals and leverage (floor of 1 / capitalInitMarginRatio) of NDX-USD-PERP, read once."""
        if self._sp is None:
            try:
                row = next(r for r in _rows(await self._api("GET", "/v3/exchangeInfo", account=False), "symbols")
                           if r.get("symbol") == SYMBOL)
                ratio = _dec(row.get("capitalInitMarginRatio") or row["initMarginRatio"])
                self._sp = {"tick": _dec((row.get("tickSizes") or [row["defaultTickSize"]])[0]),
                            "price_dec": int(row["priceDecimals"]), "lev": str(int(1 / ratio))}
            except Exception as e:  # noqa: BLE001 -- fall back to the known values, try again next time
                log.warning("vest %s: exchangeInfo unreadable (%s), using defaults", self.account_id, type(e).__name__)
                return DEFAULTS
        return self._sp

    def _px(self, price, sp: dict, rounding=ROUND_HALF_UP) -> str:
        ticks = (_dec(price) / sp["tick"]).quantize(Decimal(1), rounding=rounding)           # default: nearest, ties up
        return _trim(ticks * sp["tick"], sp["price_dec"], ROUND_HALF_UP)

    async def _opened(self) -> list:
        rows = _rows(await self._api("GET", "/v3/positions/opened", account=False), "positions")
        return [r for r in rows if _same_acct(r.get("accountId"), self.vest_account_id)]

    async def _resting(self) -> list:
        rows = _rows(await self._api("GET", "/v3/positions/opened-orders", account=False), "orders")
        return [r for r in rows if _same_acct(r.get("account_id"), self.vest_account_id)]

    # --- connection ---------------------------------------------------------------------------------
    async def connect(self) -> None:
        await (self.session.account_token(self.vest_account_id) if self.vest_account_id else self.session.user_token())
        if self.vest_account_id and not any(_same_acct(a["id"], self.vest_account_id) for a in await self.list_accounts()):
            # a plain error, not AccountNotOnLogin (that parks for good): an unreadable capital list must retry (R56)
            raise RuntimeError(f"vest: account {self.vest_account_id} not on this login")
        await self._spec()
        self._connected = True

    async def close(self) -> None:
        for t in self._tasks:
            t.cancel()
        self._tasks = []
        self._connected = False
        if self._own_session:
            await self.session.aclose()

    def login_days_left(self) -> Optional[float]:
        """Days until the wallet login (refresh token) ends; None = no login stored."""
        exp = self.session.refresh_expires_ms
        return (exp - vest_auth._now_ms()) / 86_400_000 if exp else None

    def _login_ending(self) -> Optional[str]:
        """No new entry in the login's last 12 h: its end must meet a flat account (R58). Exits still run."""
        left = self.login_days_left()
        return LOGIN_ENDING if left is None or left < 0.5 else None

    async def get_metrics(self) -> dict:
        m = await super().get_metrics()
        left = self.login_days_left()
        if left is not None and 0 < left <= 3:
            n = math.ceil(left)
            m["notice"] = f"login ends in {n} day{'s' if n != 1 else ''}"
        return m

    async def list_accounts(self) -> list[dict]:
        out = []
        for r in _rows(await self._api("GET", "/v3/accounts", account=False), "accounts"):
            if r.get("account_type") == 1 and r.get("active") is not False and r.get("account_id"):
                out.append({"name": "Vest primary", "id": r["account_id"], "kind": "primary", "demo": False})
            else:
                log.info("vest %s: account row skipped, keys=%s", self.account_id, sorted(r))
        try:
            capital = _rows(await self._api("GET", "/v3/capital/accounts", account=False), "accounts")
        except httpx.HTTPError as e:
            log.info("vest %s: capital accounts unreadable (%s)", self.account_id, type(e).__name__)
            capital = []
        for r in capital:
            # the row shape is unknown: a kind is read from the row's own words, never guessed
            words = " ".join([k.lower() for k, v in r.items() if v is True and "id" not in k.lower()]
                             + [v.lower() for k, v in r.items() if isinstance(v, str) and "id" not in k.lower()])
            kind = "demo" if ("eval" in words or "demo" in words) else "funded" if "funded" in words else None
            aid = r.get("account_id") or r.get("accountId") or r.get("id")
            if kind and aid:
                out.append({"name": f"Vest {kind} {str(aid)[:6]}", "id": aid, "kind": kind, "demo": kind == "demo"})
            else:
                log.info("vest %s: capital account row skipped, keys=%s", self.account_id, sorted(r))
        return out

    async def perp_price(self) -> float:
        j = await self._api("GET", "/v3/ticker/latest", account=False, params={"symbols": SYMBOL})
        row = next((r for r in _rows(j, "tickers", "data") if r.get("symbol") == SYMBOL), j if "markPrice" in j else None)
        return float(row["markPrice"])

    # --- orders -------------------------------------------------------------------------------------
    async def _order(self, req: OrderRequest, *, bracket: bool, held_id: Optional[str] = None,
                     fire_t: Optional[float] = None) -> OrderResult:
        """An entry opens a position; an order against this account's open position is an EXIT (close / reduce), never /open.
        `held_id`/`fire_t`: a held stop entry firing (its id for the fills, the monotonic time of its crossing push)."""
        if req.order_type not in ("Market", "Limit"):
            return OrderResult(ok=False, error=f"vest: {req.order_type} entries are not placed here")
        limit = req.order_type == "Limit"
        if limit and req.price is None:
            return OrderResult(ok=False, error="vest: a limit order needs a price")
        legs = bracket and (req.stop_price is not None or req.tp_price is not None)
        if legs and req.price is None:
            return OrderResult(ok=False, error="vest: a bracket needs the strategy's reference price in `price`")
        units, root, sp = units_of(req.symbol, req.qty), root_of(req.symbol), await self._spec()
        long = req.side == "Buy"
        async with self._entry_lock:                    # guard + POST as one step: two entries never share room
            rows = await self._opened()
            held = [p for p in rows if p.get("symbol") == SYMBOL]
            if not held and (req.text or "").startswith(EXIT_TAGS):            # an exit never opens (an SL/TP may have won the race)
                return OrderResult(ok=True, raw={"note": "nothing to close"})
            if held:
                if legs or (str(held[0].get("side")).lower() == "long") == long:
                    return OrderResult(ok=False, error="vest: position already open")
                return await self._exit(req, held[0], units, root, sp)
            if err := self._login_ending():
                return OrderResult(ok=False, error=err)
            # an entry: its full stop risk (none attached = unbounded) must fit above the loss floors
            risk = (_dec(units) * (abs(_dec(req.price) - _dec(req.stop_price)) + self._slip())
                    if legs and req.stop_price is not None else None)
            err = await self._floor_err(risk, rows)
            if err:
                return OrderResult(ok=False, error=err)
            body = {"symbol": SYMBOL, "side": "long" if long else "short", "orderType": "limit" if limit else "market",
                    "quantity": units, "leverage": sp["lev"], "timeInForce": "GTC" if limit else "IOC"}
            if limit:
                body["price"] = self._px(req.price, sp)
            # SL/TP keep the strategy's point distances (from the limit price, or for a market entry from NQ-PERP's own price),
            # rounded toward the entry so the protection is never looser than asked
            body["takeProfits"], body["stopLosses"] = [], []
            if legs:
                base = _dec(req.price) if limit else _dec(await self.perp_price())
                for key, px, up in (("takeProfits", req.tp_price, not long), ("stopLosses", req.stop_price, long)):
                    if px is not None:
                        body[key] = [{"executionType": "market", "triggerPrice": self._px(
                            base + _dec(px) - _dec(req.price), sp, ROUND_CEILING if up else ROUND_FLOOR)}]
            want, bs = body["side"], "buy" if long else "sell"
            if self._sweeping:                          # a kill or flatten started: nothing new goes out (R41)
                return OrderResult(ok=False, error="kill: a flatten is in progress" if fire_t is not None
                                   else "vest: flatten in progress")
            if fire_t is not None and self._mono() - fire_t > SLOW_S:
                return OrderResult(ok=False, error=f"slow: {self._mono() - fire_t:.1f} s after the crossing push")
            r = await self._submit(
                "/v3/positions/open", body, root, market=not limit, held_id=held_id,
                rest_hit=lambda o, ids: str(o.get("order_id")) in ids if ids else
                (o.get("side") == bs and _dec(o.get("quantity") or 0) == _dec(units)
                 and limit and _dec(o.get("price") or 0) == _dec(body["price"])),
                state_ok=lambda rows: any(str(r.get("side")).lower() == want and 0 < abs(_signed(r)) <= _dec(units)
                                          for r in rows if r.get("symbol") == SYMBOL))
            if limit and r.order_id:                        # a resting entry's risk counts against the next one
                self._risk[r.order_id] = risk
                _cap(self._risk)
            return r

    async def _exit(self, req: OrderRequest, p: dict, units: str, root: str, sp: dict) -> OrderResult:
        pid, before, limit = p["positionId"], abs(_signed(p)), req.order_type == "Limit"
        lev, typ = str(p.get("leverage") or sp["lev"]), "limit" if limit else "market"
        gone = lambda rows: not any(r.get("positionId") == pid for r in rows)          # noqa: E731
        if _dec(units) >= before:
            path, state_ok = "/v3/positions/close", gone
            body = {"symbol": SYMBOL, "positionId": pid, "orderType": typ, "leverage": lev}
            if limit:
                body["limitPrice"] = self._px(req.price, sp)
        else:
            path = "/v3/positions/reduce"
            body = {"positionId": pid, "symbol": SYMBOL, "orderType": typ, "leverage": lev, "quantity": units,
                    "timeInForce": "GTC" if limit else "IOC", "reduceOnly": True}
            if limit:
                body["price"] = self._px(req.price, sp)
            state_ok = lambda rows: gone(rows) or any(                                  # noqa: E731
                r.get("positionId") == pid and abs(_signed(r)) <= before - _dec(units) for r in rows)
        return await self._submit(
            path, body, root, state_ok=state_ok, market=not limit,
            rest_hit=lambda o, ids: str(o.get("order_id")) in ids if ids else
            (limit and o.get("position_id") == pid and _dec(o.get("price") or 0) == _dec(self._px(req.price, sp))))

    async def _submit(self, path: str, body: dict, root: str, *, rest_hit, state_ok, market: bool,
                      gone: tuple = (), held_id: Optional[str] = None) -> OrderResult:
        """POST an order action, then wait (OUTCOME_S) for its outcome on the socket; silence, a timeout or a 5xx is
        reconciled against REST, never reported as a bare reject. A 4xx with a Vest code is a reject. A MARKET order
        never rests: only FILLED / CANCELLED / REJECTED answer it, otherwise the position decides."""
        log.debug("vest %s: POST %s %s", self.account_id, path, body)
        j = None
        try:
            j = await self._api("POST", path, json=body)
        except httpx.HTTPStatusError as e:
            code, text = _err(e)
            if code in gone:
                return OrderResult(ok=True, raw={"gone": code})
            if e.response.status_code < 500:
                return OrderResult(ok=False, error=text)
        except (httpx.TransportError, ValueError) as e:                      # sent, answer unknown: reconcile
            log.warning("vest %s: %s answer unknown (%s)", self.account_id, path, type(e).__name__)
        j = j if isinstance(j, dict) else {}                                   # not an answer we can read: reconcile
        self._busy = True
        oid = str(j["orderId"]) if j.get("orderId") is not None else None
        ids = {str(j[k]) for k in ("commandId", "orderId") if j.get(k) is not None}
        for k in (oid, j.get("positionId")):
            if k:
                self._roots[str(k)] = root
        if oid and j.get("positionId"):
            self._pos_of[oid] = str(j["positionId"])
        if oid and held_id:                             # mapped before the wait: a fill on the socket already finds it
            self._held_of[oid] = held_id
        _cap(self._roots), _cap(self._pos_of), _cap(self._held_of)
        # fills parked before this answer are delivered by _fire once the entry lock is released (never inside it)
        hits = await self._wait(ids, market)
        bad = next((h for h in hits if h[0] not in ("Working", "Filled")), None)
        if bad:
            return OrderResult(ok=False, order_id=oid, error=bad[1] or f"vest: order {bad[0]}", raw=j)
        if any(h[0] == "Filled" or (not market and h[0] == "Working") for h in hits) \
                or await self._reconciled(rest_hit, state_ok, ids, market):
            return OrderResult(ok=True, order_id=oid, raw=j)
        return OrderResult(ok=False, order_id=oid, error=UNCONFIRMED, raw=j)

    async def _wait(self, ids: set, market: bool) -> list:
        """Outcomes of `ids` off the socket, waiting up to OUTCOME_S (not at all when no socket is running). A market
        order is only answered by a terminal status."""
        end = time.monotonic() + OUTCOME_S
        while True:
            hits = [self._events[i] for i in ids if i in self._events]
            if any(h[0] in ("Filled", "Canceled", "Rejected") for h in hits) or (hits and not market) \
                    or not self._tasks or time.monotonic() >= end:
                return hits
            await asyncio.sleep(0.02)

    async def _reconciled(self, rest_hit, state_ok, ids: set, market: bool) -> bool:
        if not market:                          # a market order never rests: a resting order proves nothing about it
            try:
                if any(rest_hit(o, ids) for o in await self._resting()):
                    return True
            except Exception as e:  # noqa: BLE001 -- each read on its own: the other may still answer
                log.warning("vest %s: reconcile read failed (%s)", self.account_id, type(e).__name__)
        try:
            return bool(state_ok(await self._opened()))
        except Exception as e:  # noqa: BLE001
            log.warning("vest %s: reconcile read failed (%s)", self.account_id, type(e).__name__)
            return False

    async def place_order(self, req: OrderRequest) -> OrderResult:
        if (req.text or "").startswith(EXIT_TAGS):     # the engine's kill / flatten: never waits out a refresh backoff
            with urgent():
                return await self._guard(lambda: self._order(req, bracket=False))
        return await self._guard(lambda: self._order(req, bracket=False))

    async def place_bracket(self, req: OrderRequest) -> OrderResult:
        if req.order_type in ("Stop", "StopLimit"):
            return await self._guard(lambda: self._hold(req))
        return await self._guard(lambda: self._order(req, bracket=True))

    async def cancel_order_by_id(self, order_id: str) -> OrderResult:
        if not self.vest_account_id:
            return OrderResult(ok=False, error=NO_ACCT)
        if str(order_id).startswith(HELD):              # held by Homebase: no broker call
            oid = str(order_id)
            if self._book.drop(oid) is None and (oid == self._firing or oid in self._book.fired):
                return OrderResult(ok=False, error="vest: that held entry already fired")
            return OrderResult(ok=True)
        err = await self._post("/v3/positions/cancel-order", {"orderId": str(order_id)}, ORDER_GONE)
        return OrderResult(ok=err is None, error=err)

    async def modify_order(self, order_id: str, order_type: str, *, price: Optional[float] = None,
                           stop_price: Optional[float] = None, qty: Optional[int] = None) -> OrderResult:
        """Move a TP/SL leg of an open position in place: exactly one PUT. A resting entry cannot be moved (Vest has no
        endpoint; never cancel + replace here)."""
        return await self._guard(lambda: self._modify(str(order_id), price if stop_price is None else stop_price))

    async def _modify(self, oid: str, px) -> OrderResult:
        if oid in self._roots or px is None:            # an entry we placed: no call at all
            return OrderResult(ok=False, error=NOT_SUPPORTED)
        for p in await self._opened():
            for path, id_key, legs_key in (("take-profit", "takeProfitId", "takeProfits"),
                                           ("stop-loss", "stopLossId", "stopLosses")):
                leg = next((x for x in p.get(legs_key) or [] if str(x.get("id")) == oid), None)
                if leg is None:
                    continue
                trig = self._px(px, await self._spec())
                body = {"positionId": p["positionId"], id_key: oid, "executionType": leg.get("executionType") or "market",
                        "triggerPrice": trig}
                if body["executionType"] == "limit":
                    body["limitPrice"] = trig
                if leg.get("sizeMode") not in (None, "full_position"):
                    body["quantity"] = leg["quantity"]
                log.debug("vest %s: PUT /v3/positions/%s %s", self.account_id, path, body)
                return OrderResult(ok=True, order_id=oid, raw=await self._api("PUT", f"/v3/positions/{path}", json=body))
        return OrderResult(ok=False, error=NOT_SUPPORTED)

    # --- flatten / cancel ---------------------------------------------------------------------------
    async def cancel_all(self) -> OrderResult:
        return await self._guard(lambda: self._sweep(close=False))

    async def flatten_all(self) -> OrderResult:
        return await self._guard(lambda: self._sweep(close=True))

    async def flatten_symbol(self, symbol: str) -> OrderResult:     # one market on this venue
        return await self.flatten_all()

    async def _sweep(self, *, close: bool) -> OrderResult:
        self._sweeping += 1                             # from here no entry, fire or limit, POSTs (R41)
        self._sweeps += 1
        try:
            with urgent():                              # only a 401 stops a kill / flatten (R57)
                return await self._sweep_now(close=close)
        finally:
            self._sweeping -= 1

    async def _sweep_now(self, *, close: bool) -> OrderResult:
        """Cancel every resting order, then (close) market-close every open position and re-read: ok only if none is left
        (one more close if one is). Each step in its own try, so a failed read of one never stops the other."""
        errs, cancelled, closed = [], 0, 0
        for e in list(self._book.entries):              # held stop entries first: none may fire after a sweep
            self._book.drop(e.id)
            cancelled += 1
        # an entry already firing is never cut mid-POST: wait for it (asyncio.wait never cancels it, even if this sweep
        # is cancelled), then for any entry holding the lock, so the close below sees what they opened (R36, R41)
        fires = set(self._fires) - {asyncio.current_task()}        # a sweep from a fire's own fill callback: not itself
        if fires:
            await asyncio.wait(fires)
        async with self._entry_lock:
            pass
        try:
            resting = await self._resting()
        except Exception as e:  # noqa: BLE001
            errs.append(_err(e)[1])
            resting = []
        for o in resting:
            e = await self._post("/v3/positions/cancel-order", {"orderId": str(o["order_id"])}, ORDER_GONE)
            errs += [e] if e else []
            cancelled += e is None
        if close:
            try:
                held = await self._opened()
            except Exception as e:  # noqa: BLE001
                errs.append(_err(e)[1])
                held = None
            first, tried = len(held or []), []
            for _ in range(2):
                if not held:
                    break
                for p in held:
                    try:
                        r = await self._submit(
                            "/v3/positions/close", {"symbol": SYMBOL, "positionId": p["positionId"], "orderType": "market",
                                                    "leverage": str(p.get("leverage") or (await self._spec())["lev"])},
                            self.root, gone=POSITION_GONE, rest_hit=lambda o, ids: False, market=True,
                            state_ok=lambda rows, pid=p["positionId"]: not any(x.get("positionId") == pid for x in rows))
                    except Exception as e:  # noqa: BLE001
                        r = OrderResult(ok=False, error=_err(e)[1])
                    tried += [] if r.ok else [r.error]
                try:
                    held = await self._opened()
                except Exception as e:  # noqa: BLE001
                    errs.append(_err(e)[1])
                    held = None
            if held:
                errs += tried + ["position still open"]
            closed = first - len(held) if held is not None else 0           # re-read failed: closed is unknown
        return OrderResult(ok=not errs, error="; ".join(errs) or None, raw={"cancelled": cancelled, "closed": closed})

    # --- reads --------------------------------------------------------------------------------------
    async def get_net_position(self, symbol: str) -> int:
        return _contracts(sum((_signed(p) for p in await self._opened() if p.get("symbol") == SYMBOL), Decimal(0)),
                          root_of(symbol))

    async def get_order_status(self, order_id: str) -> Optional[str]:
        """"Working" if it rests; else its outcome off the socket; else Vest's own order row; else None (unknown)."""
        oid = str(order_id)
        if oid.startswith(HELD):                        # held: working until it fires, then Filled (a market IOC)
            if self._book.get(oid) or oid == self._firing:
                return "Working"
            f = self._book.fired.get(oid)
            if f:                                       # unconfirmed: its Vest order's status, if we have its id
                return "Filled" if f.get("ok") else await self.get_order_status(f["vest"]) if f.get("vest") else None
            return "Canceled" if oid in self._book.dropped else None       # no record: unknown
        if any(str(o.get("order_id")) == oid for o in await self._resting()):
            return "Working"
        seen = self._events.get(oid)
        if seen and seen[0] != "Working":
            return seen[0]
        if oid in self._pos_of:
            d = await self._api("GET", f"/v3/positions/{self._pos_of[oid]}/details")
            for o in (d.get("position") or {}).get("orders") or []:
                if str(o.get("order_id")) == oid:
                    return _STATUS.get(str(o.get("status")).lower())
        return None

    async def _account_row(self) -> dict:
        rows = _rows(await self._api("GET", "/v3/accounts", account=False), "accounts")
        row = next((r for r in rows if _same_acct(r.get("account_id"), self.vest_account_id)), {})
        equity = row.get("equity") or row.get("amount")
        if equity is not None and row.get(DAY_START_KEY) is None:      # the first read after 20:00 ET, any caller (R35)
            self._day_start(float(equity))
        return row

    async def get_balance(self) -> dict:
        row = await self._account_row()
        v = row.get("equity") or row.get("amount")
        return {"balance": float(v) if v is not None else None, "realized_pnl": None}

    # --- loss-floor guard ---------------------------------------------------------------------------
    async def _floor_err(self, risk: Optional[Decimal], opened: Optional[list] = None) -> Optional[str]:
        """None if an entry risking `risk` $ to its stop keeps equity above both floors with what is already at risk;
        else why not. Fails closed: no stop, no equity, an unknown risk or no floors -> refused."""
        if risk is None:
            return "vest: an entry needs a stop loss (loss-floor guard)"
        row, resting = await asyncio.gather(self._account_row(), self._resting())
        equity = row.get("equity") or row.get("amount")
        if equity is None:
            return "vest: equity unreadable (loss-floor guard)"
        fl = dict(self.floors or {})
        if row.get(DAY_START_KEY) is not None:
            fl["day_start_equity"] = float(row[DAY_START_KEY])
        elif fl.get("daily_loss") is not None:
            fl["day_start_equity"] = self._day_start(float(equity))
        at_risk = self._open_risk(await self._opened() if opened is None else opened, resting)
        if at_risk is None:
            return "vest: open risk unknown (loss-floor guard)"
        room = floor_room(float(equity), fl, float(at_risk))
        if room is None:
            return "vest: no loss floors known (loss-floor guard)"
        if float(risk) > room:
            return f"vest: entry risk ${float(risk):,.0f} would cross the loss floor (room ${room:,.0f})"
        return None

    def _slip(self) -> Decimal:
        """Points of slippage allowed for per unit at risk (R60): a market stop fills past its trigger."""
        return _dec((self.floors or {}).get("slip_pts", 5.0))

    def _open_risk(self, opened: list, resting: list) -> Optional[Decimal]:
        """$ to the stops of this account's open positions and resting entries; None if one has no known stop."""
        risk = Decimal(0)
        for p in opened:
            long_ = str(p.get("side")).lower() == "long"
            stops = [_dec(x["triggerPrice"]) for x in p.get("stopLosses") or [] if x.get("triggerPrice")]
            if not stops:
                return None
            # shortcut: from the open price, not the mark; only other symbols' positions get here (SYMBOL refuses entries)
            far = min(stops) if long_ else max(stops)
            risk += abs(_signed(p)) * (max(Decimal(0), (_dec(p["openPrice"]) - far) * (1 if long_ else -1)) + self._slip())
        for o in resting:
            if o.get("reduce_only") or str(o.get("position_order_type")).lower().endswith(("close", "reduce")):
                continue
            r = self._risk.get(str(o.get("order_id")))
            if r is None:
                return None
            risk += r
        return risk

    def _day_start(self, equity: float) -> float:
        """Day-start equity of the daily loss floor: the first read after 20:00 ET (when the limit resets), saved."""
        day = (self._now() + dt.timedelta(hours=4)).date().isoformat()
        if self._book.day_start.get("day") != day:
            self._book.day_start = {"day": day, "equity": equity}
            self._book.save()
        return float(self._book.day_start["equity"])

    # --- held stop entries --------------------------------------------------------------------------
    def _desk_day(self) -> str:
        t = self._now()
        return (t.date() + dt.timedelta(days=t.hour >= 18)).isoformat()

    def _j(self, event: str, **kw) -> None:
        try:
            self.journal(event, account=self.account_id, **kw)
        except Exception as e:  # noqa: BLE001 -- a journal failure never stops an order path
            log.warning("vest %s: journal failed (%s)", self.account_id, type(e).__name__)

    def _skip(self, e: HeldEntry, reason: str, **kw) -> None:
        log.info("vest %s: held %s skipped: %s", self.account_id, e.id, reason)
        self._j("vest_held_skipped", id=e.id, side=e.side, level=e.level, reason=reason, **kw)

    async def _hold(self, req: OrderRequest) -> OrderResult:
        """A Stop entry: held here (nothing sent), checked against the floors now and again when it fires."""
        if self._sweeping:
            return OrderResult(ok=False, error="vest: flatten in progress")
        if err := self._login_ending():
            return OrderResult(ok=False, error=err)
        sweeps = self._sweeps
        if req.order_type != "Stop":
            return OrderResult(ok=False, error="vest: stop-limit entries are not supported")
        if req.price is None or req.stop_price is None:
            return OrderResult(ok=False, error="vest: a held stop entry needs its level in `price` and a stop loss")
        if not self.feed_ok():                          # nothing could fire it: the desk says so now (R49)
            return OrderResult(ok=False, error="vest: no CME price feed")
        units, level = units_of(req.symbol, req.qty), float(req.price)
        last = self._book.last_close(root_of(req.symbol))
        if last is not None and reached(req.side, level, last):
            return OrderResult(ok=False, error="vest: the level already traded")
        sl = abs(level - float(req.stop_price))
        err = await self._floor_err(_dec(units) * (_dec(sl) + self._slip()))
        if err:
            return OrderResult(ok=False, error=err)
        if self._sweeping or self._sweeps != sweeps:  # a flatten ran while the floor read was awaited
            return OrderResult(ok=False, error="vest: flatten in progress")
        day = self._desk_day()
        e = HeldEntry(HELD + uuid.uuid4().hex[:12], req.symbol, req.side, req.qty, level, sl,
                      None if req.tp_price is None else abs(float(req.tp_price) - level), day, None)
        # the engine's two legs of one signal arrive together: the new leg pairs with an unpaired opposite one added
        # within PAIR_S, same symbol and qty, the buy above the sell (shortcut: inferred, until the engine passes a group)
        now = self._mono()
        mate = next((x for x in self._book.entries if x.oco_group is None and x.side != req.side and x.day == day
                     and x.symbol == req.symbol and x.qty == req.qty and now - self._added.get(x.id, -1e9) <= PAIR_S
                     and (level > x.level if req.side == "Buy" else level < x.level)), None)
        if mate is not None:
            mate.oco_group = e.oco_group = mate.id
        self._added[e.id] = now
        _cap(self._added)
        self._book.add(e)
        log.info("vest %s: held %s %s %s @ %s", self.account_id, e.id, e.side, e.qty, e.level)
        return OrderResult(ok=True, order_id=e.id, raw={"held": True, "level": level})

    def feed_reset(self) -> None:
        """The CME feed (re)connected: the next push of every root is a first push (never fires, R1), and the last close
        before the gap is forgotten (a stale one must not refuse a hold as 'already traded', R50)."""
        self._pushed.clear()
        self._book._last.clear()

    def on_bar(self, root: str, bar) -> None:
        """The CME feed hook (sync, never awaits): fires at most one held entry a push. A crossed entry leaves the book
        first (so it fires once at most), then its market open is scheduled on the running loop."""
        try:
            self._on_bar(root, bar)
        except Exception as e:  # noqa: BLE001 -- the feed hook must never break the feed
            log.warning("vest %s: on_bar failed (%s)", self.account_id, type(e).__name__)

    def _on_bar(self, root: str, bar) -> None:
        now, feed = self._mono(), self.feed_ok()
        prev = self._pushed.pop(root, None)
        if feed:                                        # a push while the feed is down: the next one counts as a gap
            self._pushed[root] = now
        if not self._restored and _proot(root) == _proot(self.root):       # after a restart: only levels not reached
            self._restored = True
            before, today = list(self._book.entries), self._desk_day()
            kept = {x.id for x in self._book.restore(today, bar.h, bar.l)}       # this push's extreme (R38)
            for x in before:
                if x.id not in kept:
                    self._skip(x, "restart: the day is over" if x.day != today else "restart: traded while down")
        hits = self._book.crossed(root, bar)
        if not hits:
            return
        why = ("feed down" if not feed else "Vest session: sign in again" if self.session.needs_signature
               else "late cross (first push after a gap)" if prev is None or now - prev > GAP_S
               else "another held entry is firing" if self._firing else None)
        fire = None if why else hits[0]
        if fire is not None and not slip_ok(fire.level, bar.c, fire.side, fire.sl_pts, self.slip_frac):
            why = (f"late: CME {bar.c:g} is more than {self.slip_frac:g} of the {fire.sl_pts:g}-point stop past the "
                   f"level")                            # measured on the CME push, not NQ-PERP (R33)
            fire = None
        for e in hits:
            self._book.drop(e.id)
            if e is not fire:
                self._skip(e, why or "another held entry fired on this push")
            for s in self._book.drop_group(e.oco_group):
                self._skip(s, "its other leg " + ("fired" if e is fire else "was skipped"))
        if fire is not None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                self._skip(fire, "no running loop")
                return
            self._firing = fire.id
            t = loop.create_task(self._fire(fire, now, bar.c))
            self._fires.add(t)
            t.add_done_callback(self._fires.discard)

    async def _fire(self, e: HeldEntry, t: float, cme: float) -> None:
        """A crossed held entry (slippage already checked on the CME push): the market bracket path (floors, position
        check, outcome wait), skipped if its POST would go out more than SLOW_S after the push. SL/TP keep their point
        distances, measured from NQ-PERP's price."""
        r = None
        s = 1 if e.side == "Buy" else -1
        try:
            req = OrderRequest(e.symbol, e.side, e.qty, "Market", price=e.level, stop_price=e.level - s * e.sl_pts,
                               tp_price=None if e.tp_pts is None else e.level + s * e.tp_pts, text="homebase:entry")
            r = await self._guard(lambda: self._order(req, bracket=True, held_id=e.id, fire_t=t))
            if r.ok or r.error == UNCONFIRMED:          # it may be open: its status follows the Vest order
                self._book.fired[e.id] = {"vest": str(r.order_id or ""), "day": e.day, "ok": r.ok}
                _cap(self._book.fired)
                try:
                    self._book.save()
                except Exception as ex:  # noqa: BLE001 -- the fire is done: it is still journaled and reported
                    log.warning("vest %s: held book save failed (%s)", self.account_id, type(ex).__name__)
            if r.ok:
                self._j("vest_held_fired", id=e.id, side=e.side, level=e.level, cme=cme, order_id=r.order_id,
                        slippage=round((cme - e.level) * s, 2))
            else:
                self._skip(e, r.error or "refused", cme=cme)
        finally:
            self._firing = None
            left, self._parked = self._parked, []
            for ev in left:                             # ok with no order id: its own opening fills are this entry's
                if r is not None and r.ok and not r.order_id and ev.side == e.side \
                        and ev.symbol == root_of(e.symbol) and not str(ev.raw.get("orderId")).startswith("size:"):
                    ev.raw["vestOrderId"], ev.raw["orderId"] = ev.raw.get("orderId"), e.id
            if left:
                await self._deliver(left)

    # --- fills --------------------------------------------------------------------------------------
    async def observe_fills(self, on_fill: FillCallback) -> None:
        self._on_fill = on_fill
        if self.vest_account_id and not self._tasks:
            self._tasks = [asyncio.ensure_future(self._ws_loop()), asyncio.ensure_future(self._poll_loop())]

    def _size_fill(self, pid: str, units: Decimal, net: Decimal) -> FillEvent:
        """A closed position whose /details keeps failing: its exit from the size change alone. No price (None, never
        0): the engine keeps the trade's P&L unknown rather than booking a fill at 0."""
        root = self._roots.get(pid) or self.root
        self._closed(pid)
        return FillEvent(account_id=self.account_id, symbol=root, side="Sell" if units > 0 else "Buy",
                         qty=_contracts(abs(units), root), price=None, position_after=_contracts(net, root),
                         ts=time.time(), raw={"orderId": f"size:{pid}", "positionId": pid, "units": str(abs(units)),
                                              "src": "poll",
                                              "note": "details failed: size change only"},
                         seen=time.perf_counter())

    def _closed(self, pid: str) -> None:
        self._closed_pids[pid] = True
        _cap(self._closed_pids)

    def _live(self, events: list[FillEvent]) -> list[FillEvent]:
        """Drops fills on a position whose exit was already reported (a socket replay, a late /details row)."""
        return [e for e in events if str(e.raw.get("positionId")) not in self._closed_pids]

    async def _deliver(self, events: list[FillEvent]) -> None:
        for ev in events:
            oid = str(ev.raw.get("orderId"))
            if self._firing and oid not in self._held_of and oid not in self._roots:
                self._parked.append(ev)                 # maybe the firing entry's, before its POST answered
                continue
            hid = self._held_of.get(oid)
            if hid:                                     # a fired held entry's fill: the engine knows the held id
                ev.raw["vestOrderId"], ev.raw["orderId"] = ev.raw["orderId"], hid
            if self._on_fill is not None:
                try:
                    await self._on_fill(ev)
                except Exception as e:  # noqa: BLE001 -- one bad callback must not stop the feed
                    log.warning("vest %s: on_fill failed: %s", self.account_id, type(e).__name__)

    async def _on_message(self, raw) -> None:
        try:
            msg = json.loads(raw)
            ch, d = msg.get("channel"), msg.get("data") or {}
        except (ValueError, AttributeError):
            return
        if ch not in ("command_events", "account_state") or not _same_acct(d.get("account_id"), self.vest_account_id):
            return
        if ch == "command_events":
            self._ws_up = True                  # the socket has spoken for this account: the poll fallback may rest
            if d.get("status") == "REJECTED":
                log.warning("vest %s: command rejected, code=%s order=%s", self.account_id, d.get("error_code"), d.get("order_id"))
                self._events[str(d.get("command_id"))] = ("Rejected", f"vest {d.get('error_code')}")
                _cap(self._events)
            return
        seq = d.get("account_seq")
        if isinstance(seq, int):
            if seq <= self._seq:
                return
            self._seq = seq
        self._ws_up = True                      # a frame past the seq check: the socket reports, the poll may rest (R55)
        self._note_state(d)
        for o in d.get("orders") or []:
            st = _STATUS.get(str(o.get("status")).lower())
            if st and o.get("order_id") is not None:
                code = o.get("error_code")
                bad = st in ("Canceled", "Rejected")
                self._events[str(o["order_id"])] = (st, (f"vest {code}" if code else None) if bad else None)
        _cap(self._events)
        await self._deliver(self._live(parse_account_state(msg, account_id=self.account_id, roots=self._roots,
                                                           vest_account_id=self.vest_account_id, seen=self._seen,
                                                           default_root=self.root)))
        _cap(self._seen)

    def _note_state(self, d: dict) -> None:
        """Apply one socket frame to the known picture, so a later poll / reconnect diffs from what the socket said (R59)."""
        pos, ords = d.get("positions") or [], d.get("orders") or []
        if pos or ords:
            self._busy = True
        if self._known is None:                 # no first read yet: that read seeds
            return
        for p in pos:
            if p.get("symbol") != SYMBOL or p.get("position_id") is None:
                continue
            pid = str(p["position_id"])
            if str(p.get("event_type", "")).endswith("CLOSED"):
                self._known.pop(pid, None)
            else:
                self._known[pid] = _signed(p)
        for o in ords:
            if o.get("order_id") is None:
                continue
            if _STATUS.get(str(o.get("status")).lower()) == "Working":
                self._known_orders[str(o["order_id"])] = str(o.get("position_id"))
            else:
                self._known_orders.pop(str(o["order_id"]), None)

    async def _ws_loop(self) -> None:
        delay = WS_RETRY_S
        while True:
            try:
                tok = await self.session.account_token(self.vest_account_id)
                async with websockets.connect(WS_URL, subprotocols=["vest.v1", tok],
                                              additional_headers={"Origin": HEADERS["Origin"]}) as ws:
                    delay = WS_RETRY_S              # _ws_up waits for the first frame
                    self._seq = 0                   # account_seq starts over on every connection (R55)
                    try:                            # the gap since the last report, read once before the frames (R59)
                        await self._pass(reconcile=True)
                    except Exception as e:  # noqa: BLE001
                        log.warning("vest %s: reconnect read failed (%s)", self.account_id, type(e).__name__)
                    async for raw in ws:
                        await self._on_message(raw)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 -- the poll fallback covers the gap; never log the exception text (token)
                log.warning("vest %s: private socket down (%s)", self.account_id, type(e).__name__)
            finally:
                self._ws_up = False
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)

    async def _poll_loop(self) -> None:
        """Reads every POLL_S, only while the socket is down AND an order rests / a position is open (never otherwise)."""
        while True:
            await asyncio.sleep(POLL_S)
            if self._ws_up or not self._busy:
                continue
            try:
                await self._pass()
            except Exception as e:  # noqa: BLE001
                log.warning("vest %s: poll read failed (%s)", self.account_id, type(e).__name__)

    async def _pass(self, *, reconcile: bool = False) -> None:
        """Read positions and resting orders, diff them against the known picture and report each changed position's
        /details through the socket's per-order dedup. The first read ever only seeds: what is already filled is not a fill.
        `reconcile`: the read at a socket (re)connect, made even though the socket is up."""
        async with self._pass_lock:
            if not reconcile and self._ws_up:
                return
            held, resting = await self._opened(), await self._resting()
            if not reconcile and self._ws_up:   # the socket spoke while we were reading: it reports, we do not
                return
            prev, fails, warned = self._known, self._fails, self._warned
            changed, cur = poll_changes(prev, held, vest_account_id=self.vest_account_id)
            now_orders = {str(o["order_id"]): str(o.get("position_id")) for o in resting if o.get("order_id") is not None}
            left = {pid for oid, pid in self._known_orders.items() if oid not in now_orders and pid not in ("None", "")}
            seeding, retry, events, again = prev is None, False, [], set()
            net = sum((_signed(r) for r in held if r.get("symbol") == SYMBOL), Decimal(0))

            def hold(pid):                      # keep the old size: the next read sees the change again and retries
                again.add(pid)
                if pid in (prev or {}):
                    cur[pid] = prev[pid]
                else:
                    cur.pop(pid, None)

            def give_up(pid, gone) -> bool:     # a closed position /details cannot settle: its exit by size, then drop
                if not (gone or (pid not in (prev or {}) and pid not in cur)):
                    return False
                fails[pid] = fails.get(pid, 0) + 1
                if fails[pid] < DETAILS_TRIES:
                    return False
                del fails[pid]
                if not gone:                    # opened and closed inside the gap: no size change to report by
                    log.warning("vest %s: position %s unreadable after its order left, dropped", self.account_id, pid)
                elif pid not in self._closed_pids:          # its closing row was not reported already
                    events.append(self._size_fill(pid, prev[pid], net))
                return True
            for pid in sorted(cur) if seeding else sorted(set(changed) | left):
                gone = pid in (prev or {}) and pid not in cur
                try:
                    frame = details_frame(pid, await self._api("GET", f"/v3/positions/{pid}/details"),
                                          vest_account_id=self.vest_account_id)
                except Exception as e:  # noqa: BLE001 -- report nothing for this read, the next one retries; never guess
                    log.warning("vest %s: poll details read failed (%s)", self.account_id, type(e).__name__)
                    if not give_up(pid, gone):
                        retry = True
                        hold(pid)
                    continue
                if seeding:                     # what is already filled is not a fill
                    for o in frame["data"]["orders"] + frame["skipped"]:
                        self._seen.setdefault(str(o.get("order_id")), _dec(o.get("executed_quantity") or 0))
                    continue
                if not frame["skipped"]:
                    fails.pop(pid, None)
                else:                           # a row whose side is unknown: not seen, read again next time
                    for oid in (str(o.get("order_id")) for o in frame["skipped"]):
                        if oid not in warned:
                            warned[oid] = True
                            log.warning("vest: poll skipped order %s (side unknown)", oid)
                    _cap(warned)
                    if not give_up(pid, gone):
                        retry = True
                        hold(pid)
                evs = self._live(parse_account_state(frame, account_id=self.account_id, roots=self._roots,
                                                     vest_account_id=self.vest_account_id, seen=self._seen,
                                                     default_root=self.root))
                for ev in evs:
                    ev.raw["src"], ev.position_after = "poll", _contracts(net, ev.symbol)
                    events.append(ev)
                if evs and gone:                # its exit is reported: a replay of it is not a fill
                    self._closed(pid)
            _cap(self._seen)
            self._known = None if seeding and retry else cur
            # an order that left while its position's read failed stays known, so the next read tries it again
            self._known_orders = {**{o: p for o, p in self._known_orders.items() if p in again and o not in now_orders},
                                  **now_orders}
            self._busy = bool(held or resting or retry)
        await self._deliver(events)
