"""Broker adapter interface — every execution platform implements this.

An adapter instance is bound to ONE account. It can act as a MASTER
(emit fills via observe_fills) and/or a FOLLOWER (place/flatten orders).
The CopyEngine wires one master adapter's fills out to N follower adapters.
"""
from __future__ import annotations

import abc
import sys
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional


class AccountNotOnLogin(RuntimeError):
    """A pinned account (by id or name) is not exposed by this login's
    account list. Permanent until the config pin or the login itself
    changes — never a signal to retry with a fresh username/password login."""


@dataclass
class FillEvent:
    """A normalized fill observed on a master account."""
    account_id: str
    symbol: str                       # platform-native; engine maps per follower
    side: str                         # "Buy" | "Sell"
    qty: int
    price: Optional[float] = None
    position_after: Optional[int] = None   # net position after this fill, if known
    ts: float = 0.0
    raw: dict = field(default_factory=dict)


@dataclass
class OrderRequest:
    symbol: str
    side: str                         # "Buy" | "Sell"
    qty: int
    order_type: str = "Market"
    price: Optional[float] = None
    stop_price: Optional[float] = None
    tp_price: Optional[float] = None
    text: str = "Onyx"
    # Appended last so positional callers are unchanged. A StopLimit entry's
    # limit rides in `price` and its trigger HERE -- never in `stop_price`,
    # which is the protective SL of a bracket.
    trigger_price: Optional[float] = None
    time_in_force: str = "Day"


@dataclass
class OrderResult:
    ok: bool
    order_id: Optional[str] = None
    error: Optional[str] = None
    raw: dict = field(default_factory=dict)


FillCallback = Callable[[FillEvent], Awaitable[None]]
EntityListener = Callable[[str, dict], None]


class BrokerAdapter(abc.ABC):
    """One adapter == one account on one platform."""

    platform: str = "base"

    def __init__(self, account_id: str, *, live: bool = False):
        self.account_id = account_id
        self.live = live              # False => demo/sim; live needs explicit opt-in
        self._connected = False
        # True only when the broker account was chosen by the config's pin
        # (chart trading refuses any account that is not on its own pin)
        self.pinned_ok = False
        self._listeners: list[EntityListener] = []
        # canonical symbol -> [broker order id, ...] for protective stops/targets
        # WE placed on this account, so we can cancel them when the leg is closed.
        self._protective: dict[str, list[str]] = {}

    @staticmethod
    def _opposite(side: str) -> str:
        """The exit side for a position opened on `side`."""
        return "Sell" if str(side).lower() == "buy" else "Buy"

    @staticmethod
    def _canon_key(symbol: str) -> str:
        """Stable per-adapter key for protective bookkeeping. The engine always
        hands adapters the same canonical symbol string, so upper() is enough."""
        return str(symbol or "").strip().upper()

    @staticmethod
    def _entry_only(req: OrderRequest) -> OrderRequest:
        """The bare entry order from a bracket request — protective stop/target
        prices stripped so the entry doesn't get sent with a stop attached."""
        return OrderRequest(symbol=req.symbol, side=req.side, qty=req.qty,
                            order_type=req.order_type, price=req.price, text=req.text,
                            trigger_price=req.trigger_price, time_in_force=req.time_in_force)

    @property
    def connected(self) -> bool:
        return self._connected

    @abc.abstractmethod
    async def connect(self) -> None: ...

    @abc.abstractmethod
    async def close(self) -> None: ...

    async def reconnect(self) -> None:
        """Re-establish the live connection in place, preserving the registered
        fill callback and dedup cache. Default: re-run connect(); adapters with a
        cheaper in-place path (rebuild just the socket) override this."""
        await self.connect()

    # --- MASTER role -------------------------------------------------------
    @abc.abstractmethod
    async def observe_fills(self, on_fill: FillCallback) -> None:
        """Register a coroutine invoked for every fill on this account."""

    # --- FOLLOWER role -----------------------------------------------------
    @abc.abstractmethod
    async def place_order(self, req: OrderRequest) -> OrderResult: ...

    @abc.abstractmethod
    async def flatten_all(self) -> OrderResult: ...

    @abc.abstractmethod
    async def cancel_all(self) -> OrderResult: ...

    # --- protective brackets ----------------------------------------------
    # A "protective bracket" is an entry plus opposite-side resting orders (a
    # Stop loss and an optional Limit target) so a disconnect can't leave the
    # copied position naked. Adapters with native bracketing (Tradovate OSO,
    # NinjaTrader OCO) override `place_bracket` for atomic one-cancels-other;
    # the default below legs in separate resting orders and relies on the engine
    # to cancel the survivor when the position goes flat.
    async def _leg_protection(self, symbol: str, exit_side: str, qty: int,
                              stop_price: Optional[float], target_price: Optional[float],
                              *, text: str = "protect") -> tuple[list[str], list[str]]:
        """Rest an opposite-side Stop and/or Limit target as separate resting
        orders, recording their ids under `symbol`. Returns (placed_ids, errors).
        Shared by `place_bracket` and `set_protection`."""
        placed: list[str] = []
        errors: list[str] = []
        if stop_price is not None:
            r = await self.place_order(OrderRequest(
                symbol=symbol, side=exit_side, qty=qty, order_type="Stop",
                stop_price=stop_price, text=f"{text}:stop"))
            if r.ok and r.order_id:
                placed.append(r.order_id)
            elif not r.ok:
                errors.append(f"stop: {r.error}")
        if target_price is not None:
            r = await self.place_order(OrderRequest(
                symbol=symbol, side=exit_side, qty=qty, order_type="Limit",
                price=target_price, text=f"{text}:target"))
            if r.ok and r.order_id:
                placed.append(r.order_id)
            elif not r.ok:
                errors.append(f"target: {r.error}")
        if placed:
            self._protective.setdefault(self._canon_key(symbol), []).extend(placed)
        return placed, errors

    async def place_bracket(self, req: OrderRequest) -> OrderResult:
        """Place `req` as the entry, then rest a protective Stop at
        ``req.stop_price`` and/or a Limit target at ``req.tp_price`` on the
        opposite side. Returns the ENTRY's result (ok reflects the entry);
        protective order ids and any protective errors ride in ``raw``."""
        if req.stop_price is None and req.tp_price is None:
            return await self.place_order(req)
        if req.order_type in ("Stop", "StopLimit"):
            # legging rests the SL the moment the entry is PLACED, not when it
            # fills: for a stop entry that is the wrong side of the market
            return OrderResult(ok=False, error="bracketed stop entries need a broker OSO")
        entry = await self.place_order(self._entry_only(req))
        if not entry.ok:
            return entry
        placed, errors = await self._leg_protection(
            req.symbol, self._opposite(req.side), req.qty,
            req.stop_price, req.tp_price, text=req.text)
        raw = dict(entry.raw or {})
        raw["protective_ids"] = placed
        if errors:
            raw["protective_errors"] = errors
        return OrderResult(ok=entry.ok, order_id=entry.order_id,
                           error=entry.error, raw=raw)

    async def set_protection(self, symbol: str, exit_side: str, qty: int, *,
                             stop_price: Optional[float] = None,
                             target_price: Optional[float] = None) -> OrderResult:
        """Re-rest protection for an EXISTING position: cancel any protective
        orders we already have for `symbol`, then (if qty>0 and a level is given)
        rest fresh ones sized to `qty`. The engine calls this after an add /
        reduce / flip so the protective size always tracks the live net."""
        await self.cancel_protective_orders(symbol)
        if qty <= 0 or (stop_price is None and target_price is None):
            return OrderResult(ok=True, raw={"protective_ids": []})
        placed, errors = await self._leg_protection(
            symbol, exit_side, qty, stop_price, target_price)
        return OrderResult(ok=not errors, error="; ".join(errors) or None,
                           raw={"protective_ids": placed})

    async def get_protective_orders(self, symbol: str) -> list[dict]:
        """Resting protective orders on this account for `symbol`, as
        ``[{"order_id", "kind", "side", "price", "qty"}]`` where kind is
        "stop" | "target". Used to MIRROR a leader's stop/target onto followers.
        Default: empty (adapter can't read resting orders)."""
        return []

    async def cancel_order_by_id(self, order_id: str) -> OrderResult:
        """Cancel a single resting order by its broker id. Default: unsupported."""
        return OrderResult(ok=False, error="cancel_order_by_id not supported")

    async def modify_order(self, order_id: str, order_type: str, *,
                           price: Optional[float] = None,
                           stop_price: Optional[float] = None,
                           qty: Optional[int] = None) -> OrderResult:
        """Re-price one resting order in place. Default: unsupported."""
        return OrderResult(ok=False, error="modify_order not supported")

    async def get_order_status(self, order_id: str) -> Optional[str]:
        """Broker status of one order ("Working", "Filled", ...); None if
        unknown. Default: unknown."""
        return None

    async def cancel_protective_orders(self, symbol: str) -> OrderResult:
        """Cancel the protective orders WE placed for `symbol` (best-effort).
        Called by the engine when the copied leg goes flat, so a surviving Stop
        or target can't later open a brand-new position."""
        ids = self._protective.pop(self._canon_key(symbol), [])
        errors: list[str] = []
        n = 0
        for oid in ids:
            try:
                r = await self.cancel_order_by_id(oid)
                if r.ok:
                    n += 1
                elif r.error:
                    errors.append(r.error)
            except Exception as e:    # noqa: BLE001 — best-effort cleanup
                errors.append(str(e))
        return OrderResult(ok=not errors, error="; ".join(errors) or None,
                           raw={"cancelled": n})

    # --- chart trading (spec 2026-09-26) -------------------------------------
    def add_listener(self, cb: EntityListener) -> None:
        """Call cb(entity_type, entity) for THIS account's entity pushes, after
        the adapter's own caches took them. Types: order, orderVersion,
        position, fill, cashBalance, and "sync" (the caches were reseeded:
        re-read everything). Adding the same callable twice is a no-op."""
        if cb not in self._listeners:
            self._listeners.append(cb)

    def _notify(self, entity_type: str, entity: dict) -> None:
        for cb in list(self._listeners):
            try:
                cb(entity_type, entity)
            except Exception as e:  # noqa: BLE001 — a listener must never break the socket reader
                print(f"[broker] {self.account_id}: listener error: {type(e).__name__}: {e}",
                      file=sys.stderr, flush=True)

    def trade_view(self) -> Optional[dict]:
        """Cached positions / working orders / cash for chart trading, with no
        broker call. None = this adapter cannot provide one."""
        return None

    def contract_name(self, contract_id) -> Optional[str]:
        return None

    async def flatten_symbol(self, symbol: str) -> OrderResult:
        return OrderResult(ok=False, error="flatten_symbol not supported")

    async def cancel_symbol(self, symbol: str) -> OrderResult:
        return OrderResult(ok=False, error="cancel_symbol not supported")

    # --- reads -------------------------------------------------------------
    @abc.abstractmethod
    async def get_net_position(self, symbol: str) -> int: ...

    @abc.abstractmethod
    async def get_balance(self) -> dict: ...

    async def get_metrics(self) -> dict:
        """A status snapshot for the dashboard. Adapters override to fill in
        live numbers; the keys here are the contract the UI relies on, so
        every adapter returns the same shape."""
        return {
            "connected": self.connected,
            "account": None,        # broker-side display name of the account
            "balance": None,        # cash balance, in account currency
            "realized_pnl": None,   # realized P&L for the session/day
            "open_positions": [],   # [{"symbol": str, "net": int}, ...]
            "open_position_count": 0,
            "working_orders": None,  # count of resting (unfilled) orders
            "protective": {},        # symbol -> {"stop": price|None, "target": price|None}
        }
