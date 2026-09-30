"""The desk's adapter for a PAPER account: the chart service's virtual book (homebase.charts.paperbook)
driven through its localhost HTTP API, so an algo's whole desk path -- the timer, the engine, the gates, the
journal, the brackets -- runs on it exactly as on any other desk account, with the book's fill law on the
live prints and Level 2 and no login or exchange connection anywhere.

One adapter == one paper account; the account's id on the desk IS its paper id ("paper", "paper-3"). The book
is the chart service's own and this module imports nothing from it (the book never depends on the desk, nor
the desk on the book's code): only its documented routes, POST /api/paper/{order|modify|cancel|cancel-symbol|
flatten} and GET /api/paper/book.

Fills arrive by polling that view (the book pushes to no one): a fill is seen within POLL_S, fast enough for
the engine's entry/exit bookkeeping, which never depends on the order of arrival. A fill is reported once,
by its id; the ones already in the view when the adapter starts watching are history, never replayed.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import re
import uuid
from typing import Optional

import httpx

from .base import BrokerAdapter, FillCallback, FillEvent, OrderRequest, OrderResult

BASE_URL = "http://127.0.0.1:8852"        # the chart service (homebase.charts.PORT)
POLL_S = 0.25                             # while an order works or a position is open
IDLE_POLL_S = 1.0                         # nothing working: no algo is waiting on a fill
DOWN_AFTER = 4                            # consecutive failed reads before the account is "not connected"
_CONTRACT = re.compile(r"^([A-Z0-9]+?)[FGHJKMNQUVXZ]\d{1,2}$")


def root_of(symbol: str) -> str:
    """NQ -> NQ, NQZ6 -> NQ, 6EZ6 -> 6E."""
    s = str(symbol or "").strip().upper()
    m = _CONTRACT.match(s)
    return m.group(1) if m else s


def _ts(iso: str) -> float:
    try:
        return dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


class PaperAdapter(BrokerAdapter):
    platform = "paper"

    def __init__(self, account_id: str, *, base_url: str = BASE_URL,
                 client: Optional[httpx.AsyncClient] = None, poll_s: float = POLL_S):
        super().__init__(account_id, live=False)
        self.pinned_ok = True
        self.poll_s = poll_s
        self._own = client is None
        self._http = client or httpx.AsyncClient(base_url=base_url, timeout=5.0)
        self._view: dict = {}
        self._fails = 0
        self._last_fid = 0
        self._on_fill: Optional[FillCallback] = None
        self._task: Optional[asyncio.Task] = None

    # --- the book's routes ------------------------------------------------------------------------
    async def _read(self) -> dict:
        """GET the book and keep this account's view; raises when the service or the account is not there."""
        r = await self._http.get("/api/paper/book")
        r.raise_for_status()
        for v in r.json().get("accounts", []):
            if v.get("id") == self.account_id:
                self._view, self._fails, self._connected = v, 0, True
                return v
        raise RuntimeError(f"paper account {self.account_id} is not in the chart service's book")

    async def _act(self, action: str, **body) -> OrderResult:
        try:
            r = await self._http.post(f"/api/paper/{action}", json={
                "client_id": uuid.uuid4().hex, "account": self.account_id, **body})
            if r.status_code != 200:
                return OrderResult(ok=False, error=f"paper book {r.status_code}: {r.text[:160]}")
            res = (r.json().get("results") or {}).get(self.account_id) or {}
        except (httpx.HTTPError, ValueError) as e:
            return OrderResult(ok=False, error=f"paper book unreachable: {e}")
        oid = res.get("order_id")
        return OrderResult(ok=bool(res.get("ok")), order_id=None if oid is None else str(oid),
                           error=res.get("error"), raw=dict(res))

    # --- lifecycle --------------------------------------------------------------------------------
    async def connect(self) -> None:
        await self._read()
        self._connected = True

    async def close(self) -> None:
        self._connected = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._own:
            await self._http.aclose()

    async def observe_fills(self, on_fill: FillCallback) -> None:
        self._on_fill = on_fill
        self._last_fid = max((int(f.get("id") or 0) for f in self._view.get("fills", [])), default=0)
        if self._task is None or self._task.done():
            self._task = asyncio.ensure_future(self._poll())

    async def _poll(self) -> None:
        while True:
            busy = bool(self._view.get("orders") or self._view.get("positions"))
            await asyncio.sleep(self.poll_s if busy else IDLE_POLL_S)
            try:
                v = await self._read()
            except (httpx.HTTPError, RuntimeError, ValueError):
                self._fails += 1
                if self._fails >= DOWN_AFTER:
                    self._connected = False
                continue
            await self._deliver(v)

    async def _deliver(self, v: dict) -> None:
        new = sorted((f for f in v.get("fills", []) if int(f.get("id") or 0) > self._last_fid),
                     key=lambda f: int(f["id"]))
        for f in new:
            self._last_fid = int(f["id"])
            root = root_of(f.get("symbol"))
            after = next((p["net"] for p in v.get("positions", []) if p.get("root") == root), 0)
            ev = FillEvent(account_id=self.account_id, symbol=str(f.get("symbol") or ""), side=f["side"],
                           qty=int(f["qty"]), price=f.get("price"), position_after=after, ts=_ts(f.get("time")),
                           raw={"orderId": str(f.get("order_id")), "role": f.get("role"), "src": f.get("src")})
            self._notify("fill", dict(f))
            if self._on_fill is not None:
                await self._on_fill(ev)

    # --- orders -----------------------------------------------------------------------------------
    @staticmethod
    def _body(req: OrderRequest, *, legs: bool) -> dict:
        typ = req.order_type
        b = {"root": root_of(req.symbol), "side": req.side, "qty": int(req.qty), "type": typ,
             "tif": "Day" if typ == "Market" else req.time_in_force}
        if typ == "Stop":                     # a Stop's level: `price` (a bracket's SL rides in stop_price)
            b["price"] = req.price if req.price is not None else req.stop_price
        elif typ == "StopLimit":
            b["price"], b["trigger_price"] = req.price, req.trigger_price
        elif typ == "Limit":
            b["price"] = req.price
        if legs:
            if req.stop_price is not None:
                b["sl_price"] = req.stop_price
            if req.tp_price is not None:
                b["tp_price"] = req.tp_price
        return b

    async def place_order(self, req: OrderRequest) -> OrderResult:
        return await self._act("order", **self._body(req, legs=False))

    async def place_bracket(self, req: OrderRequest) -> OrderResult:
        """The book brackets natively: the entry and its SL/TP legs (held until the entry fills, one-cancels-
        other) in one call; the legs' ids come back in raw as sl_order_id / tp_order_id, as the engine reads them."""
        return await self._act("order", **self._body(req, legs=True))

    async def cancel_order_by_id(self, order_id: str) -> OrderResult:
        return await self._act("cancel", order_id=str(order_id))

    async def modify_order(self, order_id: str, order_type: str, *, price: Optional[float] = None,
                           stop_price: Optional[float] = None, qty: Optional[int] = None) -> OrderResult:
        level = stop_price if order_type == "Stop" and stop_price is not None else price
        if level is None:
            return OrderResult(ok=False, error="modify: a price is required")
        if qty is not None:
            try:
                have = next((o["qty"] for o in (await self._read()).get("orders", [])
                             if str(o["order_id"]) == str(order_id)), None)
            except (httpx.HTTPError, RuntimeError, ValueError) as e:
                return OrderResult(ok=False, error=f"paper book unreachable: {e}")
            if have is not None and int(have) != int(qty):
                return OrderResult(ok=False, error="the paper book moves an order's price, never its size")
        return await self._act("modify", order_id=str(order_id), price=float(level))

    async def flatten_symbol(self, symbol: str) -> OrderResult:
        return await self._act("flatten", root=root_of(symbol))

    async def cancel_symbol(self, symbol: str) -> OrderResult:
        return await self._act("cancel-symbol", root=root_of(symbol))

    async def _roots(self) -> list[str]:
        v = await self._read()
        roots = {p["root"] for p in v.get("positions", [])}
        roots |= {root_of(o["symbol"]) for o in v.get("orders", [])}
        return sorted(roots)

    async def flatten_all(self) -> OrderResult:
        try:
            roots = await self._roots()
        except (httpx.HTTPError, RuntimeError, ValueError) as e:
            return OrderResult(ok=False, error=f"paper book unreachable: {e}")
        res = [await self._act("flatten", root=r) for r in roots]
        bad = [r.error for r in res if not r.ok]
        return OrderResult(ok=not bad, error="; ".join(bad) or None, raw={"roots": roots})

    async def cancel_all(self) -> OrderResult:
        try:
            roots = await self._roots()
        except (httpx.HTTPError, RuntimeError, ValueError) as e:
            return OrderResult(ok=False, error=f"paper book unreachable: {e}")
        res = [await self._act("cancel-symbol", root=r) for r in roots]
        bad = [r.error for r in res if not r.ok]
        return OrderResult(ok=not bad, error="; ".join(bad) or None, raw={"roots": roots})

    # --- reads ------------------------------------------------------------------------------------
    async def get_net_position(self, symbol: str) -> int:
        v = await self._read()
        root = root_of(symbol)
        return int(next((p["net"] for p in v.get("positions", []) if p.get("root") == root), 0))

    async def get_order_status(self, order_id: str) -> Optional[str]:
        return (await self.get_order_state(order_id))["status"]

    async def get_order_state(self, order_id: str) -> dict:
        v = await self._read()
        oid = str(order_id)
        for o in v.get("orders", []):
            if str(o["order_id"]) == oid:
                return {"status": o["status"], "filled_qty": 0}
        done = sum(int(f["qty"]) for f in v.get("fills", []) if str(f.get("order_id")) == oid)
        if done:
            return {"status": "Filled", "filled_qty": done}
        return {"status": "Canceled", "filled_qty": None}     # gone and never filled (the fills list is capped)

    async def get_balance(self) -> dict:
        v = self._view
        return {"balance": v.get("balance"), "realized_pnl": v.get("realized_pnl")}

    async def get_metrics(self) -> dict:
        v = self._view
        pos = [{"symbol": p["symbol"], "net": p["net"]} for p in v.get("positions", [])]
        return {"connected": self.connected, "account": v.get("label"), "balance": v.get("balance"),
                "realized_pnl": v.get("realized_pnl"), "open_positions": pos, "open_position_count": len(pos),
                "working_orders": sum(1 for o in v.get("orders", []) if o.get("status") == "Working"),
                "protective": {}}
