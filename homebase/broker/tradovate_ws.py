"""Direct WebSocket client for Tradovate's order/account API.

Talks to wss://{demo,live}.tradovateapi.com/v1/websocket using a bearer token
from TradovateAuth. No browser required.

Protocol (SockJS-style, decoded from the web app):
    - frames: 'o'=open, 'h'=heartbeat, 'a[...]'=array of messages
    - request:  f"{endpoint}\\n{id}\\n\\n{body}"   (body is a JSON string or '')
    - response: {"s":200,"i":<id>,"d":<data>}
    - unsolicited push (entity updates): {"e":"props","d":{...}}  (no "i")
    - client heartbeat: send '[]' every ~2.5s
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any, Optional

import websockets

WS_DEMO = "wss://demo.tradovateapi.com/v1/websocket"
WS_LIVE = "wss://live.tradovateapi.com/v1/websocket"


def log(msg: str) -> None:
    print(f"[tradovate_ws] {msg}", file=sys.stderr, flush=True)


def _ws_is_closed(ws) -> bool:
    """`.closed` was removed in newer websockets versions — probe state instead."""
    if ws is None:
        return True
    if hasattr(ws, "closed"):
        return ws.closed
    state = getattr(ws, "state", None)
    if state is None:
        return False
    return getattr(state, "value", 1) >= 2  # 2=CLOSING, 3=CLOSED


class TradovateWS:
    def __init__(self, token: str, environment: str = "demo"):
        self.token = token
        self.environment = environment
        self.url = WS_LIVE if environment == "live" else WS_DEMO
        self.ws: Optional[Any] = None
        self._next_id = 2  # id 1 conceptually reserved
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self.connected = False
        self.authorized = False
        # Pub/sub for unsolicited entity updates (fills, positions, orders, ...)
        self.event_handlers: list = []

    async def connect(self) -> None:
        log(f"connecting → {self.url}")
        self.ws = await websockets.connect(self.url, max_size=64 * 1024 * 1024)
        self._reader_task = asyncio.create_task(self._reader())
        deadline = time.time() + 10
        while not self.connected and time.time() < deadline:
            await asyncio.sleep(0.05)
        if not self.connected:
            raise RuntimeError("did not receive 'o' (open) frame from server")
        self._heartbeat_task = asyncio.create_task(self._heartbeat())

    async def _heartbeat(self) -> None:
        try:
            while self.ws and not _ws_is_closed(self.ws):
                await asyncio.sleep(2.5)
                try:
                    await self.ws.send("[]")
                except Exception:
                    return
        except asyncio.CancelledError:
            return

    async def _reader(self) -> None:
        try:
            async for raw in self.ws:
                if raw == "o":
                    self.connected = True
                    continue
                if raw == "h":
                    continue
                if not isinstance(raw, str) or not raw.startswith("a"):
                    continue
                try:
                    arr = json.loads(raw[1:])
                except json.JSONDecodeError:
                    log(f"bad JSON frame: {raw[:80]!r}")
                    continue
                for msg in arr:
                    mid = msg.get("i")
                    if mid is not None and mid in self._pending:
                        fut = self._pending.pop(mid)
                        if not fut.done():
                            fut.set_result(msg)
                    else:
                        for h in self.event_handlers:
                            try:
                                h(msg)
                            except Exception as e:
                                log(f"event handler error: {e}")
        except websockets.ConnectionClosed:
            log("websocket closed")
        except Exception as e:
            log(f"reader error: {e}")
        finally:
            # The socket is dead once the read loop exits — surface that so the
            # adapter (and the dashboard) stop reporting a phantom connection.
            self.connected = False

    async def request(self, endpoint: str, body: Any = "") -> Any:
        """Send a request, await the matching response, return its `.d` payload."""
        if not self.ws or _ws_is_closed(self.ws):
            raise RuntimeError("websocket not connected")
        self._next_id += 1
        mid = self._next_id
        body_str = body if isinstance(body, str) else json.dumps(body)
        frame = f"{endpoint}\n{mid}\n\n{body_str}"
        fut = asyncio.get_running_loop().create_future()
        self._pending[mid] = fut
        await self.ws.send(frame)
        m = await asyncio.wait_for(fut, timeout=15)
        status = m.get("s")
        if status != 200:
            raise RuntimeError(f"{endpoint} failed: status={status} data={m.get('d')}")
        return m.get("d")

    async def authorize(self) -> None:
        if not self.ws or _ws_is_closed(self.ws):
            raise RuntimeError("not connected")
        self._next_id += 1
        mid = self._next_id
        frame = f"authorize\n{mid}\n\n{self.token}"
        fut = asyncio.get_running_loop().create_future()
        self._pending[mid] = fut
        await self.ws.send(frame)
        m = await asyncio.wait_for(fut, timeout=10)
        if m.get("s") != 200:
            raise RuntimeError(f"authorize failed: {m}")
        self.authorized = True
        log("authorized")

    # ---- reads ----
    async def user_sync(self) -> dict:
        return await self.request("user/syncrequest", {"splitResponses": False})

    async def account_list(self) -> list:
        return await self.request("account/list", "")

    async def position_list(self) -> list:
        return await self.request("position/list", "")

    async def cash_balance_list(self) -> list:
        return await self.request("cashBalance/list", "")

    async def contract_find(self, name: str) -> dict:
        return await self.request("contract/find", f"name={name}")

    async def contract_item(self, contract_id: int) -> dict:
        return await self.request("contract/item", f"id={contract_id}")

    async def order_item(self, order_id: int) -> dict:
        return await self.request("order/item", f"id={order_id}")

    async def fill_item(self, fill_id: int) -> dict:
        return await self.request("fill/item", f"id={fill_id}")

    # ---- writes ----
    async def place_order(
        self, *,
        account_id: int,
        symbol: str,
        side: str,
        qty: int,
        order_type: str = "Market",
        time_in_force: str = "Day",
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        text: str = "Onyx",
    ) -> dict:
        body = {
            "accountId": account_id,
            "action": "Buy" if side.lower() == "buy" else "Sell",
            "symbol": symbol,
            "orderQty": qty,
            "orderType": order_type,
            "timeInForce": time_in_force,
            "isAutomated": True,
            "text": text,
        }
        if price is not None:
            body["price"] = price
        if stop_price is not None:
            body["stopPrice"] = stop_price
        return await self.request("order/placeorder", body)

    async def place_oso(
        self, *,
        account_id: int,
        symbol: str,
        side: str,                          # "Buy" | "Sell" (parent/entry side)
        qty: int,
        stop_price: Optional[float] = None,  # absolute SL price (opposite side)
        tp_price: Optional[float] = None,    # absolute TP price (opposite side)
        entry_type: str = "Market",          # entry: Market, Limit or Stop
        entry_price: Optional[float] = None,  # Limit price, or Stop trigger
        time_in_force: str = "Day",
        text: str = "Onyx",
    ) -> dict:
        """Place a One-Sends-Other bracketed order: entry + protective stop
        and/or target. Tradovate auto-cancels the surviving bracket when its
        sibling (or the position) closes — true broker-side OCO. At least one of
        `stop_price` / `tp_price` is required. Returns {orderId} for the parent."""
        if stop_price is None and tp_price is None:
            raise ValueError("place_oso needs at least a stop or a target price")
        opposite = "Sell" if side.lower() == "buy" else "Buy"
        parent_action = "Buy" if side.lower() == "buy" else "Sell"
        body = {
            "accountId": account_id,
            "action": parent_action,
            "symbol": symbol,
            "orderQty": qty,
            "orderType": entry_type,
            "timeInForce": time_in_force,
            "isAutomated": True,
            "text": text,
        }
        if entry_price is not None and entry_type == "Limit":
            body["price"] = entry_price
        elif entry_price is not None and entry_type == "Stop":
            # Stop entry (e.g. a straddle leg): the trigger rides in stopPrice,
            # exactly as order/placeorder does it; brackets below are unchanged.
            body["stopPrice"] = entry_price
        # bracket1 takes the stop when present; otherwise the lone target lands
        # in bracket1 so we never send an empty bracket1 with a filled bracket2.
        if stop_price is not None:
            body["bracket1"] = {"action": opposite, "orderType": "Stop",
                                "stopPrice": stop_price, "timeInForce": "GTC"}
            if tp_price is not None:
                body["bracket2"] = {"action": opposite, "orderType": "Limit",
                                    "price": tp_price, "timeInForce": "GTC"}
        else:
            body["bracket1"] = {"action": opposite, "orderType": "Limit",
                                "price": tp_price, "timeInForce": "GTC"}
        return await self.request("order/placeOSO", body)

    async def cancel_order(self, order_id: int) -> dict:
        return await self.request("order/cancelorder", {"orderId": order_id})

    async def liquidate_position(self, *, account_id: int, contract_id: int,
                                 admin: bool = False) -> dict:
        return await self.request("order/liquidateposition", {
            "accountId": account_id,
            "contractId": contract_id,
            "admin": admin,
        })

    async def cancel_all_orders(self, account_id: int) -> dict:
        return await self.request("order/cancelallorders", {"accountId": account_id})

    async def close(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._reader_task:
            self._reader_task.cancel()
        if self.ws and not _ws_is_closed(self.ws):
            await self.ws.close()
