"""Tradovate adapter — binds one Tradovate account (demo or live).

MASTER role: `observe_fills` streams this account's fills via the WebSocket
entity push. FOLLOWER role: `place_order` / `flatten_all` / `cancel_all`.

Auth is the reverse-engineered web-client flow (no paid API). Credentials come
from the OS keychain via `secrets_store`, keyed by the account's `keyring_key`.
"""
from __future__ import annotations

import asyncio
import sys
import time
from collections import deque
from pathlib import Path
from typing import Callable, Optional

from .. import symbols
from ..paths import state_dir as _default_state_dir
from ..secrets_store import get_credentials
from .base import BrokerAdapter, FillCallback, FillEvent, OrderRequest, OrderResult
from .tradovate_auth import TradovateAuth
from .tradovate_ws import TradovateWS, _ws_is_closed

_SEEN_FILL_CAP = 20000


def _log(msg: str) -> None:
    print(f"[tradovate] {msg}", file=sys.stderr, flush=True)


def _reject_reason(d) -> str:
    """Human-readable reason from an order/placeorder response that carried no
    orderId. Tradovate returns transport status 200 even on a logical reject and
    puts the cause in failureText / failureReason, so a missing orderId is the
    real failure signal — without this the engine reports a reject as success."""
    if isinstance(d, dict):
        return str(d.get("failureText") or d.get("failureReason") or "").strip()
    return ""


class TradovateAdapter(BrokerAdapter):
    platform = "tradovate"

    def __init__(
        self,
        account_id: str,
        *,
        env: str = "demo",
        keyring_key: str = "",
        account_selector: Optional[dict] = None,
        audit: Optional[Callable[[dict], None]] = None,
        state_dir: Optional[Path] = None,
    ):
        super().__init__(account_id, live=(env == "live"))
        self.env = env
        self.keyring_key = keyring_key or account_id
        self.account_selector = account_selector or {}
        self.audit = audit or (lambda e: None)
        state_dir = state_dir or _default_state_dir()
        state_dir.mkdir(parents=True, exist_ok=True)
        self._auth = TradovateAuth(
            env=env,
            token_persist_path=state_dir / f"{account_id}.tokens.json",
            device_persist_path=state_dir / f"{account_id}.device.json",
        )
        self._ws: Optional[TradovateWS] = None
        self._acct_num: Optional[int] = None
        self._acct_name: str = ""
        self._all_accounts: list = []   # every account the login exposes
        self._contracts: dict[int, str] = {}     # contractId -> symbol name
        self._orders: dict[int, dict] = {}        # orderId -> order entity
        self._order_versions: dict[int, dict] = {}  # orderId -> latest orderVersion
        self._seen_fills: set[int] = set()
        self._seen_order: deque = deque(maxlen=_SEEN_FILL_CAP)
        self._on_fill: Optional[FillCallback] = None
        self._fill_q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._consumer: Optional[asyncio.Task] = None
        self._keepalive: Optional[asyncio.Task] = None

    @property
    def connected(self) -> bool:
        """True only while the WebSocket is actually live. ``_connected`` records
        that we finished login + connect, but the socket can drop silently
        afterwards; the reader flips ``ws.connected`` on exit and the close probe
        catches a wedged socket, so a dead link reports disconnected instead of a
        phantom green dot the dashboard would keep trusting."""
        ws = self._ws
        if not self._connected or ws is None:
            return False
        return bool(ws.connected) and not _ws_is_closed(ws)

    # ------------------------------------------------------------ lifecycle
    async def connect(self) -> None:
        creds = get_credentials(self.keyring_key)
        if not creds or not creds.get("username") or not creds.get("password"):
            raise RuntimeError(
                f"no credentials in keychain for key {self.keyring_key!r} — run: "
                f"python -m homebase.secrets_store set {self.keyring_key}"
            )
        await asyncio.to_thread(self._auth.login, creds["username"], creds["password"])
        self._ws = TradovateWS(token=self._auth.access_token, environment=self.env)
        self._ws.event_handlers.append(self._on_ws_event)
        await self._ws.connect()
        await self._ws.authorize()
        sync = await self._ws.user_sync()
        self._ingest_sync(sync)
        self._connected = True
        self._keepalive = asyncio.create_task(self._keepalive_loop())
        self.audit({"event": "adapter_connected", "account": self.account_id,
                    "platform": self.platform, "env": self.env,
                    "tradovate_account": self._acct_name, "tradovate_id": self._acct_num})
        _log(f"{self.account_id}: connected as {self._acct_name} "
             f"(#{self._acct_num}) env={self.env}")

    async def reconnect(self) -> None:
        """Rebuild the websocket and re-authorize in place, preserving the fill
        callback, dedup cache, and fill queue so mirroring resumes transparently.
        Recovery is driven by the engine's connection supervisor."""
        try:
            if self._ws:
                await self._ws.close()
        except Exception:
            pass
        await asyncio.to_thread(self._auth.ensure_valid)
        self._ws = TradovateWS(token=self._auth.access_token, environment=self.env)
        self._ws.event_handlers.append(self._on_ws_event)
        await self._ws.connect()
        await self._ws.authorize()
        sync = await self._ws.user_sync()
        self._ingest_sync(sync)
        self._connected = True
        if self._consumer is None or self._consumer.done():
            self._consumer = asyncio.create_task(self._consume_fills())
        self.audit({"event": "adapter_reconnected", "account": self.account_id})

    async def close(self) -> None:
        self._connected = False
        for t in (self._keepalive, self._consumer):
            if t:
                t.cancel()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass

    # ------------------------------------------------------------ sync ingest
    def _ingest_sync(self, sync: dict) -> None:
        for c in sync.get("contracts", []) or []:
            if "id" in c and "name" in c:
                self._contracts[c["id"]] = c["name"]
        for o in sync.get("orders", []) or []:
            if "id" in o:
                self._orders[o["id"]] = o
        for ov in sync.get("orderVersions", []) or []:
            oid = ov.get("orderId")
            if oid is not None:
                self._order_versions[oid] = ov
        for f in sync.get("fills", []) or []:
            if "id" in f:
                self._mark_seen(f["id"])   # historical fills must not be copied
        self._resolve_account(sync.get("accounts", []) or [])

    def list_accounts(self) -> list[dict]:
        """Every account under the connected login (for the connect wizard)."""
        return [{"id": a.get("id"),
                 "name": a.get("name") or a.get("nickname") or str(a.get("id")),
                 "active": a.get("active", True)} for a in self._all_accounts]

    def _resolve_account(self, accounts: list) -> None:
        self._all_accounts = list(accounts)
        if not accounts:
            raise RuntimeError(f"{self.account_id}: login exposes no accounts")
        sel = self.account_selector
        chosen = None
        want_id = sel.get("tradovate_account_id")
        if want_id:
            chosen = next((a for a in accounts if a.get("id") == want_id), None)
        want_name = sel.get("account_name") or sel.get("tradovate_account_name")
        if chosen is None and want_name:
            w = str(want_name).lower()
            chosen = next((a for a in accounts
                           if str(a.get("name", "")).lower() == w
                           or str(a.get("nickname", "")).lower() == w), None)
        if chosen is None:
            active = [a for a in accounts if a.get("active", True)]
            chosen = (active or accounts)[0]
            if len(accounts) > 1:
                _log(f"{self.account_id}: {len(accounts)} accounts under this login; "
                     f"using {chosen.get('name')} (#{chosen.get('id')}). "
                     f"Pin one with extra.account_name in config.")
        self._acct_num = chosen.get("id")
        self._acct_name = chosen.get("name") or chosen.get("nickname") or str(self._acct_num)

    # ------------------------------------------------------------ fill stream
    def _mark_seen(self, fid: int) -> bool:
        """Record a fill id; return True if it was not seen before."""
        if fid in self._seen_fills:
            return False
        if len(self._seen_order) == self._seen_order.maxlen:
            self._seen_fills.discard(self._seen_order[0])
        self._seen_order.append(fid)
        self._seen_fills.add(fid)
        return True

    def _on_ws_event(self, msg: dict) -> None:
        """Sync handler invoked from the WS reader for every unsolicited frame."""
        if msg.get("e") != "props":
            return
        d = msg.get("d") or {}
        et = d.get("entityType")
        ent = d.get("entity")
        if not et or not isinstance(ent, dict):
            return
        if et == "contract":
            if "id" in ent and "name" in ent:
                self._contracts[ent["id"]] = ent["name"]
        elif et == "order":
            if "id" in ent:
                self._orders[ent["id"]] = {**self._orders.get(ent["id"], {}), **ent}
        elif et == "orderVersion":
            oid = ent.get("orderId")
            if oid is not None:
                self._order_versions[oid] = {**self._order_versions.get(oid, {}), **ent}
        elif et == "fill":
            fid = ent.get("id")
            if fid is None or not self._mark_seen(fid):
                return
            if self._on_fill is None:
                return  # this account is not being observed as master
            self._enqueue_fill(ent)

    def _enqueue_fill(self, ent: dict) -> None:
        """Queue a fill for the consumer; a full queue is surfaced as an audit
        event (a dropped fill = a silently un-copied trade), not just a log line."""
        try:
            self._fill_q.put_nowait(ent)
        except asyncio.QueueFull:
            fid = ent.get("id")
            _log(f"{self.account_id}: fill queue full, dropping fill {fid}")
            self.audit({"event": "fill_dropped", "account": self.account_id,
                        "fill_id": fid})

    async def observe_fills(self, on_fill: FillCallback) -> None:
        self._on_fill = on_fill
        if self._consumer is None:
            self._consumer = asyncio.create_task(self._consume_fills())
        self.audit({"event": "observing_fills", "account": self.account_id,
                    "tradovate_account": self._acct_name})

    async def _consume_fills(self) -> None:
        while True:
            ent = await self._fill_q.get()
            try:
                fe = await self._build_fill_event(ent)
                if fe and self._on_fill:
                    await self._on_fill(fe)
            except Exception as e:
                _log(f"{self.account_id}: fill dispatch error: {e}")
                self.audit({"event": "fill_error", "account": self.account_id,
                            "error": str(e)})

    async def _build_fill_event(self, ent: dict) -> Optional[FillEvent]:
        fid = ent.get("id")
        order_id = ent.get("orderId")
        order = await self._lookup_order(order_id)
        contract_id = ent.get("contractId") or (order or {}).get("contractId")

        # Real-time fill pushes are often partial — they can omit contractId
        # (and sometimes orderId/qty/action). Re-fetch the full fill entity to
        # recover the missing fields before giving up.
        if (contract_id is None or ent.get("qty") is None) and fid is not None:
            try:
                full = await self._ws.fill_item(fid)
            except Exception as e:
                _log(f"{self.account_id}: fill/item {fid} failed: {e}")
                full = None
            if isinstance(full, dict):
                ent = {**full, **{k: v for k, v in ent.items() if v is not None}}
                contract_id = contract_id or full.get("contractId")
                if order is None and full.get("orderId") is not None:
                    order_id = full.get("orderId")
                    order = await self._lookup_order(order_id)

        acct_id = (order or {}).get("accountId")
        if acct_id is not None and self._acct_num is not None and acct_id != self._acct_num:
            return None  # fill belongs to another account under the same login

        symbol = self._contracts.get(contract_id, "") if contract_id is not None else ""
        if not symbol and contract_id is not None:
            try:
                c = await self._ws.contract_item(contract_id)
                symbol = (c or {}).get("name", "")
                if symbol:
                    self._contracts[contract_id] = symbol
            except Exception as e:
                _log(f"{self.account_id}: contract/item {contract_id} failed: {e}")
        if not symbol:
            _log(f"{self.account_id}: unresolved symbol for fill {fid} "
                 f"(contractId={contract_id}, orderId={order_id}, "
                 f"keys={sorted(ent.keys())})")
            return None
        qty = int(ent.get("qty") or 0)
        if qty <= 0:
            return None
        return FillEvent(
            account_id=self.account_id,
            symbol=symbol,
            side="Buy" if str(ent.get("action", "")).lower() == "buy" else "Sell",
            qty=qty,
            price=ent.get("price"),
            ts=time.time(),
            raw=ent,
        )

    async def _lookup_order(self, order_id) -> Optional[dict]:
        """Return the cached order for `order_id`, fetching it once if needed."""
        if order_id is None:
            return None
        order = self._orders.get(order_id)
        if order is not None:
            return order
        try:
            order = await self._ws.order_item(order_id)
        except Exception as e:
            _log(f"{self.account_id}: order/item {order_id} failed: {e}")
            return None
        if isinstance(order, dict) and "id" in order:
            self._orders[order["id"]] = order
            return order
        return None

    # ------------------------------------------------------------ follower ops
    async def place_order(self, req: OrderRequest) -> OrderResult:
        if self._ws is None or self._acct_num is None:
            return OrderResult(ok=False, error="adapter not connected")
        sym = symbols.resolve_contract(req.symbol)
        if self.live:
            _log(f"{self.account_id}: LIVE ORDER {req.side} {req.qty} {sym}")
        try:
            d = await self._ws.place_order(
                account_id=self._acct_num, symbol=sym, side=req.side,
                qty=req.qty, order_type=req.order_type, price=req.price,
                stop_price=req.stop_price, text=req.text,
                account_spec=self._acct_name or None,
            )
            oid = d.get("orderId") if isinstance(d, dict) else None
            if oid is None:
                reason = _reject_reason(d) or "order rejected (no orderId returned)"
                _log(f"{self.account_id}: order rejected: {reason}")
                return OrderResult(ok=False, error=reason,
                                   raw=d if isinstance(d, dict) else {})
            return OrderResult(ok=True, order_id=str(oid),
                               raw=d if isinstance(d, dict) else {})
        except Exception as e:
            return OrderResult(ok=False, error=str(e))

    async def place_bracket(self, req: OrderRequest) -> OrderResult:
        """Entry + protective stop/target as a single Tradovate OSO, so the
        broker manages the one-cancels-other and the protection survives a
        disconnect. Falls back to legged resting orders if OSO is rejected."""
        if self._ws is None or self._acct_num is None:
            return OrderResult(ok=False, error="adapter not connected")
        if req.stop_price is None and req.tp_price is None:
            return await self.place_order(req)
        sym = symbols.resolve_contract(req.symbol)
        if self.live:
            _log(f"{self.account_id}: LIVE BRACKET {req.side} {req.qty} {sym} "
                 f"stop={req.stop_price} tp={req.tp_price}")
        try:
            d = await self._ws.place_oso(
                account_id=self._acct_num, symbol=sym, side=req.side,
                qty=req.qty, stop_price=req.stop_price, tp_price=req.tp_price,
                entry_type=req.order_type, entry_price=req.price, text=req.text,
                account_spec=self._acct_name or None)
            oid = d.get("orderId") if isinstance(d, dict) else None
            if oid is None:
                # A 200 with no orderId is a logical OSO reject; leg it instead.
                _log(f"{self.account_id}: OSO rejected ({_reject_reason(d) or 'no orderId'}); "
                     "legging bracket instead")
                return await super().place_bracket(req)
            # The OSO's brackets are broker-managed OCO — no local id tracking
            # needed; flattening the position cancels them server-side.
            return OrderResult(ok=True, order_id=str(oid),
                               raw=d if isinstance(d, dict) else {})
        except Exception as e:
            _log(f"{self.account_id}: OSO rejected ({e}); legging bracket instead")
            return await super().place_bracket(req)

    async def get_protective_orders(self, symbol: str) -> list[dict]:
        """Resting Stop/Limit orders on this account for `symbol`, read from the
        WS entity cache (order + latest orderVersion). Lets the engine mirror a
        Tradovate leader's stop/target onto the followers."""
        if self._ws is None or self._acct_num is None:
            return []
        try:
            c = await self._ws.contract_find(symbols.resolve_contract(symbol))
        except Exception:
            c = None
        cid = (c or {}).get("id")
        out: list[dict] = []
        for oid, o in list(self._orders.items()):
            if o.get("accountId") != self._acct_num:
                continue
            if o.get("ordStatus") not in self._WORKING_STATUSES:
                continue
            ov = self._order_versions.get(oid, {})
            o_cid = o.get("contractId") or ov.get("contractId")
            if cid is not None and o_cid is not None and o_cid != cid:
                continue
            otype = ov.get("orderType") or o.get("orderType")
            side = o.get("action") or ov.get("action")
            qty = ov.get("orderQty") or o.get("orderQty")
            if otype == "Stop":
                out.append({"order_id": str(oid), "kind": "stop", "side": side,
                            "price": ov.get("stopPrice") or o.get("stopPrice"),
                            "qty": qty})
            elif otype == "Limit":
                out.append({"order_id": str(oid), "kind": "target", "side": side,
                            "price": ov.get("price") or o.get("price"), "qty": qty})
        return out

    async def cancel_order_by_id(self, order_id: str) -> OrderResult:
        if self._ws is None:
            return OrderResult(ok=False, error="adapter not connected")
        try:
            await self._ws.cancel_order(int(order_id))
            return OrderResult(ok=True)
        except Exception as e:
            return OrderResult(ok=False, error=str(e))

    async def flatten_all(self) -> OrderResult:
        if self._ws is None or self._acct_num is None:
            return OrderResult(ok=False, error="adapter not connected")
        try:
            errors: list[str] = []
            n = 0
            for p in await self._ws.position_list():
                if p.get("accountId") != self._acct_num:
                    continue
                if not (p.get("netPos") or 0):
                    continue
                try:
                    await self._ws.liquidate_position(
                        account_id=self._acct_num, contract_id=p.get("contractId"))
                    n += 1
                except Exception as e:
                    errors.append(str(e))
            if errors:
                return OrderResult(ok=False, error="; ".join(errors), raw={"flattened": n})
            return OrderResult(ok=True, raw={"flattened": n})
        except Exception as e:
            return OrderResult(ok=False, error=str(e))

    async def cancel_all(self) -> OrderResult:
        if self._ws is None or self._acct_num is None:
            return OrderResult(ok=False, error="adapter not connected")
        try:
            await self._ws.cancel_all_orders(self._acct_num)
            return OrderResult(ok=True)
        except Exception as e:
            return OrderResult(ok=False, error=str(e))

    # ------------------------------------------------------------ reads
    async def get_net_position(self, symbol: str) -> int:
        if self._ws is None or self._acct_num is None:
            return 0
        try:
            c = await self._ws.contract_find(symbols.resolve_contract(symbol))
            cid = (c or {}).get("id")
            if cid is None:
                return 0
            for p in await self._ws.position_list():
                if p.get("accountId") == self._acct_num and p.get("contractId") == cid:
                    return int(p.get("netPos") or 0)
        except Exception:
            pass
        return 0

    async def get_balance(self) -> dict:
        if self._ws is None or self._acct_num is None:
            return {}
        try:
            for b in await self._ws.cash_balance_list():
                if b.get("accountId") == self._acct_num:
                    return {"amount": b.get("amount"),
                            "realizedPnL": b.get("realizedPnL"),
                            "currencyId": b.get("currencyId")}
        except Exception:
            pass
        return {}

    _WORKING_STATUSES = {"Working", "PendingNew", "Pending", "Suspended", "PendingReplace"}

    async def get_metrics(self) -> dict:
        m = await super().get_metrics()
        m["account"] = self._acct_name or None
        if self._ws is None or self._acct_num is None:
            return m
        try:
            bal = await self.get_balance()
            m["balance"] = bal.get("amount")
            m["realized_pnl"] = bal.get("realizedPnL")
        except Exception:
            pass
        try:
            positions = []
            for p in await self._ws.position_list():
                if p.get("accountId") != self._acct_num:
                    continue
                net = int(p.get("netPos") or 0)
                if net == 0:
                    continue
                cid = p.get("contractId")
                symbol = self._contracts.get(cid, "") if cid is not None else ""
                if not symbol and cid is not None:
                    try:
                        c = await self._ws.contract_item(cid)
                        symbol = (c or {}).get("name", "")
                        if symbol:
                            self._contracts[cid] = symbol
                    except Exception:
                        pass
                positions.append({"symbol": symbol or f"#{cid}", "net": net})
            m["open_positions"] = positions
            m["open_position_count"] = len(positions)
        except Exception:
            pass
        # Working orders: count from the cache, scoped to this account.
        m["working_orders"] = sum(
            1 for o in self._orders.values()
            if o.get("accountId") == self._acct_num
            and o.get("ordStatus") in self._WORKING_STATUSES
        )
        return m

    # ------------------------------------------------------------ token refresh
    async def _renew_if_needed(self) -> bool:
        """Keep the access token fresh; drop the socket if it rolled.

        Tradovate ties a WebSocket session to the access token it was authorized
        with and rejects re-authorizing a *live* socket (``404 Not found:
        authorize``) — the previous in-place re-auth failed on every token cycle,
        so the refreshed token never reached the socket and Tradovate closed it
        at expiry, mid-trade. Instead, when the token rolls we close the
        stale-token socket so the engine's connection supervisor rebuilds it on
        the fresh token (a clean reconnect that also recovers any fill missed in
        the gap). Returns True if the socket was dropped for renewal."""
        before = self._auth.access_token
        await asyncio.to_thread(self._auth.ensure_valid, 600)
        after = self._auth.access_token
        if after and after != before and self._ws:
            self.audit({"event": "token_renewed", "account": self.account_id})
            try:
                await self._ws.close()
            except Exception:
                pass
            return True
        return False

    async def _keepalive_loop(self) -> None:
        try:
            while self._connected:
                await asyncio.sleep(60)
                if not self.connected:
                    continue   # socket down; the engine supervisor owns reconnect
                try:
                    await self._renew_if_needed()
                except Exception as e:
                    _log(f"{self.account_id}: keepalive error: {e}")
                    self.audit({"event": "keepalive_error",
                                "account": self.account_id, "error": str(e)})
        except asyncio.CancelledError:
            return
