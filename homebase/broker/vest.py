"""Vest Markets order adapter (NQ-PERP, API symbol NDX-USD-PERP): market / limit entries with SL/TP, flatten, fills.

Wire format: `.superpowers/sdd/2026-10-29-vest-broker/vest-orders-api.md` (read from the web app). Every field name sits in
the body builders (`_open_body`, `_modify`, `_flatten`, `parse_account_state`) so a day-one fix is one line. Held stop
entries and the desk wiring are not here (later tasks): Stop / StopLimit entries are refused.

Sizing: 1 NQ = 20 units, 1 MNQ = 2 units (1 unit = $1 a point); contracts in, contracts out.
Order methods never raise: a failure is `OrderResult(ok=False, error=...)`. Secrets are never logged (order bodies hold none).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Optional

import httpx
import websockets

from .base import BrokerAdapter, FillCallback, FillEvent, OrderRequest, OrderResult
from .paper import root_of
from .vest_auth import HEADERS, NeedsSignature, VestSession

log = logging.getLogger(__name__)

SYMBOL = "NDX-USD-PERP"
UNITS = {"NQ": 20, "MNQ": 2}
SIZE_DECIMALS = 4
WS_URL = "wss://ws.hz.vestmarkets.com/ws/private"
POLL_S = 2.0                                  # fallback reads, only while the socket is down AND something rests / is open
NO_ACCT = "vest: no Vest account selected"
NOT_SUPPORTED = "vest: modify not supported"
ORDER_GONE = (3017, 10010, 11004)             # cancel: already gone
POSITION_GONE = (10009, 10029)                # close: no such position / close already requested
DEFAULTS = {"tick": Decimal("0.25"), "price_dec": 2, "lev": "50"}


# ---- pure helpers ------------------------------------------------------------------------------------------
def _dec(x) -> Decimal:
    return Decimal(str(x))


def _trim(d: Decimal, places: int, rounding) -> str:
    s = format(d.quantize(Decimal(1).scaleb(-places), rounding=rounding), "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def units_of(symbol: str, qty: int) -> str:
    root = root_of(symbol)
    if root not in UNITS:
        raise ValueError(f"vest: no sizing for {symbol!r} (NQ and MNQ only)")
    return _trim(Decimal(qty * UNITS[root]), SIZE_DECIMALS, ROUND_DOWN)


def _contracts(units: Decimal, root: str) -> int:
    """Units -> contracts of `root`; a remainder never reads as flat (rounded away from zero)."""
    n = units / UNITS[root]
    return int(abs(n).to_integral_value(ROUND_CEILING)) * (1 if n >= 0 else -1)


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
    return None, f"vest: {type(e).__name__} {e}"[:200]


def parse_account_state(msg: dict, *, account_id: str, vest_account_id: str, seen: dict,
                        roots: Optional[dict] = None) -> list[FillEvent]:
    """Fills out of one private-socket `account_state` frame. An order's executed_quantity is cumulative: `seen`
    (order id -> units already reported) turns it into per-fill deltas, so a replayed frame yields nothing."""
    d = msg.get("data") or {}
    if msg.get("channel") != "account_state" or d.get("account_id") != vest_account_id:
        return []
    roots = roots or {}
    held = [p for p in d.get("positions") or [] if p.get("symbol") == SYMBOL]
    out = []
    for o in d.get("orders") or []:
        if o.get("symbol") != SYMBOL or o.get("account_id", vest_account_id) != vest_account_id:
            continue
        oid = str(o.get("order_id"))
        done = _dec(o.get("executed_quantity") or 0)
        delta = done - seen.get(oid, Decimal(0))
        if delta <= 0:
            continue
        seen[oid] = done
        root = roots.get(str(o.get("position_id"))) or roots.get(oid) or "NQ"
        px = _dec(o.get("execution_price") or 0) or _dec(o.get("price") or 0)       # zero execution price: use the limit
        after = None
        if held:
            after = _contracts(sum((Decimal(0) if str(p.get("event_type", "")).endswith("CLOSED") else _signed(p)
                                    for p in held), Decimal(0)), root)
        out.append(FillEvent(account_id=account_id, symbol=root, side="Buy" if o.get("side") == "buy" else "Sell",
                             qty=_contracts(delta, root), price=float(px) if px else None, position_after=after,
                             ts=time.time(), raw={"orderId": oid, "positionId": o.get("position_id"),
                                                  "order_type": o.get("order_type"), "units": str(delta)},
                             seen=time.perf_counter()))
    return out


def poll_fills(prev: Optional[dict], rows: list, *, account_id: str, vest_account_id: str,
               roots: Optional[dict] = None) -> tuple[list[FillEvent], dict]:
    """Fallback when the socket is down: fills = changes in the open positions between two reads (first read: seed only).
    A close has no price on the opened list, so its price is None."""
    cur = {r["positionId"]: (_signed(r), r.get("openPrice")) for r in rows
           if r.get("accountId") == vest_account_id and r.get("symbol") == SYMBOL}
    if prev is None:
        return [], cur
    roots = roots or {}
    net = sum((v[0] for v in cur.values()), Decimal(0))
    out = []
    for pid in sorted(cur.keys() | prev.keys()):
        d = cur.get(pid, (Decimal(0), None))[0] - prev.get(pid, (Decimal(0), None))[0]
        if d == 0:
            continue
        root = roots.get(pid) or "NQ"
        px = cur.get(pid, (None, None))[1]
        out.append(FillEvent(account_id=account_id, symbol=root, side="Buy" if d > 0 else "Sell",
                             qty=_contracts(abs(d), root), price=float(px) if px else None,
                             position_after=_contracts(net, root), ts=time.time(),
                             raw={"positionId": pid, "units": str(abs(d)), "src": "poll"}, seen=time.perf_counter()))
    return out, cur


# ---- adapter -----------------------------------------------------------------------------------------------
class VestAdapter(BrokerAdapter):
    platform = "vest"

    def __init__(self, account_id: str, *, keyring_key: str, vest_account_id: str, session: VestSession | None = None,
                 floors: dict | None = None, slip_frac: float = 0.5):
        super().__init__(account_id, live=True)
        self.vest_account_id = vest_account_id          # "" = probe: connect + list_accounts only, no orders
        self.session = session or VestSession(keyring_key)
        self._own_session = session is None
        self.floors, self.slip_frac = floors, slip_frac    # used by the held stop entries (later task)
        self._sp: Optional[dict] = None
        self._roots: dict[str, str] = {}                # order id / position id -> root we placed it with
        self._on_fill: Optional[FillCallback] = None
        self._tasks: list[asyncio.Task] = []
        self._ws_up = False
        self._busy = True                               # poll fallback: something may rest / be open
        self._seq = 0                                   # last account_seq seen on the socket
        self._seen: dict[str, Decimal] = {}

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

    def _px(self, price, sp: dict) -> str:
        ticks = (_dec(price) / sp["tick"]).quantize(Decimal(1), rounding=ROUND_HALF_UP)       # nearest tick, ties up
        return _trim(ticks * sp["tick"], sp["price_dec"], ROUND_HALF_UP)

    async def _opened(self) -> list:
        rows = _rows(await self._api("GET", "/v3/positions/opened", account=False), "positions")
        return [r for r in rows if r.get("accountId") == self.vest_account_id]

    async def _resting(self) -> list:
        rows = _rows(await self._api("GET", "/v3/positions/opened-orders", account=False), "orders")
        return [r for r in rows if r.get("account_id") == self.vest_account_id]

    # --- connection ---------------------------------------------------------------------------------
    async def connect(self) -> None:
        await (self.session.account_token(self.vest_account_id) if self.vest_account_id else self.session.user_token())
        await self._spec()
        self._connected = True

    async def close(self) -> None:
        for t in self._tasks:
            t.cancel()
        self._tasks = []
        self._connected = False
        if self._own_session:
            await self.session.aclose()

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
    async def _open(self, req: OrderRequest, *, bracket: bool) -> OrderResult:
        if req.order_type not in ("Market", "Limit"):
            return OrderResult(ok=False, error=f"vest: {req.order_type} entries are not placed here")
        limit = req.order_type == "Limit"
        if limit and req.price is None:
            return OrderResult(ok=False, error="vest: a limit entry needs a price")
        legs = bracket and (req.stop_price is not None or req.tp_price is not None)
        if legs and req.price is None:
            return OrderResult(ok=False, error="vest: a bracket needs the strategy's reference price in `price`")
        sp = await self._spec()
        body = {"symbol": SYMBOL, "side": "long" if req.side == "Buy" else "short",
                "orderType": "limit" if limit else "market", "quantity": units_of(req.symbol, req.qty),
                "leverage": sp["lev"], "timeInForce": "GTC" if limit else "IOC"}
        if limit:
            body["price"] = self._px(req.price, sp)
        # SL/TP keep the strategy's point distances, from the limit price or (market) from NQ-PERP's own price
        body["takeProfits"], body["stopLosses"] = [], []
        if legs:
            base = _dec(req.price) if limit else _dec(await self.perp_price())
            for key, px in (("takeProfits", req.tp_price), ("stopLosses", req.stop_price)):
                if px is not None:
                    body[key] = [{"executionType": "market", "triggerPrice": self._px(base + _dec(px) - _dec(req.price), sp)}]
        log.debug("vest %s: POST /v3/positions/open %s", self.account_id, body)
        j = await self._api("POST", "/v3/positions/open", json=body)
        oid = str(j["orderId"]) if j.get("orderId") is not None else None
        for k in (oid, j.get("positionId")):
            if k:
                self._roots[str(k)] = root_of(req.symbol)
        self._busy = True
        return OrderResult(ok=True, order_id=oid, raw=dict(j))

    async def place_order(self, req: OrderRequest) -> OrderResult:
        return await self._guard(lambda: self._open(req, bracket=False))

    async def place_bracket(self, req: OrderRequest) -> OrderResult:
        return await self._guard(lambda: self._open(req, bracket=True))

    async def cancel_order_by_id(self, order_id: str) -> OrderResult:
        if not self.vest_account_id:
            return OrderResult(ok=False, error=NO_ACCT)
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
        """Cancel every resting order, then (close) market-close every open position. Keeps going past a failure."""
        errs, cancelled, closed = [], 0, 0
        for o in await self._resting():
            e = await self._post("/v3/positions/cancel-order", {"orderId": str(o["order_id"])}, ORDER_GONE)
            errs += [e] if e else []
            cancelled += e is None
        for p in (await self._opened()) if close else []:
            e = await self._post("/v3/positions/close", {
                "symbol": SYMBOL, "positionId": p["positionId"], "orderType": "market",
                "leverage": str(p.get("leverage") or (await self._spec())["lev"])}, POSITION_GONE)
            errs += [e] if e else []
            closed += e is None
        return OrderResult(ok=not errs, error="; ".join(errs) or None, raw={"cancelled": cancelled, "closed": closed})

    # --- reads --------------------------------------------------------------------------------------
    async def get_net_position(self, symbol: str) -> int:
        return _contracts(sum((_signed(p) for p in await self._opened() if p.get("symbol") == SYMBOL), Decimal(0)),
                          root_of(symbol))

    async def get_balance(self) -> dict:
        rows = _rows(await self._api("GET", "/v3/accounts", account=False), "accounts")
        row = next((r for r in rows if r.get("account_id") == self.vest_account_id), {})
        v = row.get("equity") or row.get("amount")
        return {"balance": float(v) if v is not None else None, "realized_pnl": None}

    # --- fills --------------------------------------------------------------------------------------
    async def observe_fills(self, on_fill: FillCallback) -> None:
        self._on_fill = on_fill
        if self.vest_account_id and not self._tasks:
            self._tasks = [asyncio.ensure_future(self._ws_loop()), asyncio.ensure_future(self._poll_loop())]

    async def _deliver(self, events: list[FillEvent]) -> None:
        for ev in events:
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
        if ch == "command_events" and d.get("status") == "REJECTED" and d.get("account_id") == self.vest_account_id:
            log.warning("vest %s: command rejected, code=%s order=%s", self.account_id, d.get("error_code"), d.get("order_id"))
        elif ch == "account_state" and d.get("account_id") == self.vest_account_id:
            seq = d.get("account_seq")
            if isinstance(seq, int):
                if seq <= self._seq:
                    return
                self._seq = seq
            await self._deliver(parse_account_state(msg, account_id=self.account_id, vest_account_id=self.vest_account_id,
                                                    seen=self._seen, roots=self._roots))

    async def _ws_loop(self) -> None:
        delay = 1.0
        while True:
            try:
                tok = await self.session.account_token(self.vest_account_id)
                async with websockets.connect(WS_URL, subprotocols=["vest.v1", tok],
                                              additional_headers={"Origin": HEADERS["Origin"]}) as ws:
                    self._ws_up, delay = True, 1.0
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
        prev = None
        while True:
            await asyncio.sleep(POLL_S)
            if self._ws_up:
                prev = None                     # re-seed when the fallback is needed again
                continue
            if not self._busy:
                continue
            try:
                held, resting = await self._opened(), await self._resting()
            except Exception as e:  # noqa: BLE001
                log.warning("vest %s: poll read failed (%s)", self.account_id, type(e).__name__)
                continue
            events, prev = poll_fills(prev, held, account_id=self.account_id, vest_account_id=self.vest_account_id,
                                      roots=self._roots)
            self._busy = bool(held or resting)
            await self._deliver(events)
