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
from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_UP, Decimal
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
OUTCOME_S = 5.0                               # how long an order waits for its socket outcome before the REST reconcile
KEEP = 1000                                   # per-order memory (ids, seen quantities, outcomes): oldest dropped past this
POLL_S = 2.0                                  # fallback reads, only while the socket is down AND something rests / is open
NO_ACCT = "vest: no Vest account selected"
NOT_SUPPORTED = "vest: modify not supported"
ORDER_GONE = (3017, 10010, 11004)             # cancel: already gone
POSITION_GONE = (10009,)                      # close: no such position (10029, close already requested, is NOT gone)
CREDIT_S = 60.0                               # a poll-reported fill stops offsetting the socket's report after this
UNCONFIRMED = "vest: unconfirmed — check Vest"
_STATUS = {"pending": "Working", "accepted": "Working", "partially_filled": "Working", "filled": "Filled",
           "cancelled": "Canceled", "rejected": "Rejected"}      # Vest order status -> the engine's words
DEFAULTS = {"tick": Decimal("0.25"), "price_dec": 2, "lev": "50"}


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


def parse_account_state(msg: dict, *, account_id: str, vest_account_id: str, seen: dict,
                        roots: Optional[dict] = None, default_root: str = "NQ",
                        polled: Optional[dict] = None) -> list[FillEvent]:
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
        side = "Buy" if o.get("side") == "buy" else "Sell"
        credit = (polled or {}).get((str(o.get("position_id")), side))      # units the poll fallback already reported
        if credit:
            polled.pop((str(o.get("position_id")), side))
            if time.monotonic() - credit[1] < CREDIT_S:
                use = min(credit[0], delta)
                delta -= use
                if credit[0] > use:
                    polled[(str(o.get("position_id")), side)] = (credit[0] - use, credit[1])
                if delta <= 0:
                    continue
        root = roots.get(str(o.get("position_id"))) or roots.get(oid) or default_root
        px = _dec(o.get("execution_price") or 0) or _dec(o.get("price") or 0)       # zero execution price: use the limit
        after = None
        if held:
            after = _contracts(sum((Decimal(0) if str(p.get("event_type", "")).endswith("CLOSED") else _signed(p)
                                    for p in held), Decimal(0)), root)
        out.append(FillEvent(account_id=account_id, symbol=root, side=side,
                             qty=_contracts(delta, root), price=float(px) if px else None, position_after=after,
                             ts=time.time(), raw={"orderId": oid, "positionId": o.get("position_id"),
                                                  "order_type": o.get("order_type"), "units": str(delta)},
                             seen=time.perf_counter()))
    return out


def poll_fills(prev: Optional[dict], rows: list, *, account_id: str, vest_account_id: str,
               roots: Optional[dict] = None, default_root: str = "NQ",
               polled: Optional[dict] = None) -> tuple[list[FillEvent], dict]:
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
        root = roots.get(pid) or default_root
        px = cur.get(pid, (None, None))[1]
        if polled is not None:                  # the socket will report this order too: it subtracts what we reported
            k = (pid, "Buy" if d > 0 else "Sell")
            polled[k] = (polled.get(k, (Decimal(0), 0))[0] + abs(d), time.monotonic())
        out.append(FillEvent(account_id=account_id, symbol=root, side="Buy" if d > 0 else "Sell",
                             qty=_contracts(abs(d), root), price=float(px) if px else None,
                             position_after=_contracts(net, root), ts=time.time(),
                             raw={"positionId": pid, "units": str(abs(d)), "src": "poll"}, seen=time.perf_counter()))
    return out, cur


# ---- adapter -----------------------------------------------------------------------------------------------
class VestAdapter(BrokerAdapter):
    platform = "vest"

    def __init__(self, account_id: str, *, keyring_key: str, vest_account_id: str, session: VestSession | None = None,
                 floors: dict | None = None, slip_frac: float = 0.5, root: str = "NQ"):
        super().__init__(account_id, live=True)
        self.vest_account_id = vest_account_id          # "" = probe: connect + list_accounts only, no orders
        self.session = session or VestSession(keyring_key)
        self._own_session = session is None
        self.root = root                                # this account's contract root (fills after a restart use it)
        self.floors, self.slip_frac = floors, slip_frac    # used by the held stop entries (later task)
        self._sp: Optional[dict] = None
        self._roots: dict[str, str] = {}                # order id / position id -> root we placed it with
        self._on_fill: Optional[FillCallback] = None
        self._tasks: list[asyncio.Task] = []
        self._ws_up = False
        self._busy = True                               # poll fallback: something may rest / be open
        self._seq = 0                                   # last account_seq seen on the socket
        self._seen: dict[str, Decimal] = {}
        self._polled: dict[tuple, tuple] = {}           # (position id, side) -> (units the poll reported, when)
        self._events: dict[str, tuple[str, Optional[str]]] = {}     # command / order id -> (status, error) off the socket
        self._pos_of: dict[str, str] = {}               # order id -> position id (for get_order_status)

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
    async def _order(self, req: OrderRequest, *, bracket: bool) -> OrderResult:
        """An entry opens a position; an order against this account's open position is an EXIT (close / reduce), never /open."""
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
        held = [p for p in await self._opened() if p.get("symbol") == SYMBOL]
        if not held and (req.text or "").startswith("homebase:flat"):      # a flatten never opens (an SL/TP may have won the race)
            return OrderResult(ok=True, raw={"note": "nothing to close"})
        if held:
            if legs or (str(held[0].get("side")).lower() == "long") == long:
                return OrderResult(ok=False, error="vest: position already open")
            return await self._exit(req, held[0], units, root, sp)
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
        return await self._submit(
            "/v3/positions/open", body, root, market=not limit,
            rest_hit=lambda o, ids: str(o.get("order_id")) in ids if ids else
            (o.get("side") == bs and _dec(o.get("quantity") or 0) == _dec(units)
             and limit and _dec(o.get("price") or 0) == _dec(body["price"])),
            state_ok=lambda rows: any(str(r.get("side")).lower() == want and 0 < abs(_signed(r)) <= _dec(units)
                                      for r in rows if r.get("symbol") == SYMBOL))

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
                      gone: tuple = ()) -> OrderResult:
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
        _cap(self._roots), _cap(self._pos_of)
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
        return await self._guard(lambda: self._order(req, bracket=False))

    async def place_bracket(self, req: OrderRequest) -> OrderResult:
        return await self._guard(lambda: self._order(req, bracket=True))

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
        """Cancel every resting order, then (close) market-close every open position and re-read: ok only if none is left
        (one more close if one is). Each step in its own try, so a failed read of one never stops the other."""
        errs, cancelled, closed = [], 0, 0
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
            closed = first - len(held or [])
        return OrderResult(ok=not errs, error="; ".join(errs) or None, raw={"cancelled": cancelled, "closed": closed})

    # --- reads --------------------------------------------------------------------------------------
    async def get_net_position(self, symbol: str) -> int:
        return _contracts(sum((_signed(p) for p in await self._opened() if p.get("symbol") == SYMBOL), Decimal(0)),
                          root_of(symbol))

    async def get_order_status(self, order_id: str) -> Optional[str]:
        """"Working" if it rests; else its outcome off the socket; else Vest's own order row; else None (unknown)."""
        oid = str(order_id)
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
        if ch not in ("command_events", "account_state") or d.get("account_id") != self.vest_account_id:
            return
        self._ws_up = True                      # the socket has spoken for this account: the poll fallback may rest
        if ch == "command_events":
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
        for o in d.get("orders") or []:
            st = _STATUS.get(str(o.get("status")).lower())
            if st and o.get("order_id") is not None:
                code = o.get("error_code")
                bad = st in ("Canceled", "Rejected")
                self._events[str(o["order_id"])] = (st, (f"vest {code}" if code else None) if bad else None)
        _cap(self._events)
        await self._deliver(parse_account_state(msg, account_id=self.account_id, vest_account_id=self.vest_account_id,
                                                seen=self._seen, roots=self._roots, default_root=self.root,
                                                polled=self._polled))
        _cap(self._seen)

    async def _ws_loop(self) -> None:
        delay = 1.0
        while True:
            try:
                tok = await self.session.account_token(self.vest_account_id)
                async with websockets.connect(WS_URL, subprotocols=["vest.v1", tok],
                                              additional_headers={"Origin": HEADERS["Origin"]}) as ws:
                    delay = 1.0                     # _ws_up waits for the first frame
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
            if self._ws_up:                     # the socket spoke while we were reading: it reports, we do not
                prev = None
                continue
            events, prev = poll_fills(prev, held, account_id=self.account_id, vest_account_id=self.vest_account_id,
                                      roots=self._roots, default_root=self.root, polled=self._polled)
            _cap(self._polled)
            self._busy = bool(held or resting)
            await self._deliver(events)
