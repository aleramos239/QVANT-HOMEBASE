"""A fake broker with a round trip, for the exit tests: every call an adapter makes takes `Wire.rt`
seconds, is recorded in the order it was SENT, and moves a little book of its own (the net position and
the working orders) -- so "flat, nothing working" is read off the book, never off the engine's word.
No broker, no network."""
from __future__ import annotations

import asyncio

from homebase.broker.base import FillEvent, OrderResult
from homebase.config import AccountCfg, AppCfg, StrategyCfg
from homebase.engine import Engine
from tests.test_engine import ALERT, Clock, FakeAdapter

RATE_LIMITED = "failed: status=429 data=None"       # as tradovate_ws.request words it


class Wire:
    """What the broker saw, over every account."""

    def __init__(self, rt: float = 0.0):
        self.rt = rt
        self.calls: list[tuple[str, str]] = []      # (account, call) in the order they were sent
        self.out: dict[str, int] = {}               # account -> requests out right now
        self.peak_accounts = 0                      # most accounts with a request out at once
        self.peak_requests = 0                      # most requests out at once
        self.together: set[frozenset] = set()       # every set of accounts seen out at the same time

    def of(self, account: str) -> list[str]:
        return [c for a, c in self.calls if a == account]

    def overlapped(self, a: str, b: str) -> bool:
        return any({a, b} <= s for s in self.together)

    def clear(self) -> None:
        self.calls.clear()
        self.together.clear()
        self.peak_accounts = self.peak_requests = 0


class SlowAdapter(FakeAdapter):
    """FakeAdapter behind a Wire. `raises` / `limited` hold call prefixes ("place_order",
    "cancel a01-101-sl", "cancel_all", ...): a call in the first raises every time it is made (a fake
    that blows up, as no real adapter should), one in the second is answered 429 ONCE, the way the
    Tradovate adapter reports it. `broker` is the broker-side account the adapter trades (two desk
    entries may share one)."""

    def __init__(self, aid: str, wire: Wire, broker=None):
        super().__init__(aid)
        self.wire = wire
        self.working: set[str] = set()
        self.raises: set[str] = set()
        self.limited: set[str] = set()
        self.broker = broker if broker is not None else self

    @property
    def broker_key(self):
        return id(self.broker)

    async def _rt(self, call: str) -> bool:
        """One round trip. False: the broker answered 429 (once)."""
        w, a = self.wire, self.account_id
        w.calls.append((a, call))
        if any(call.startswith(x) for x in self.raises):
            raise RuntimeError(f"{call.split(' ', 1)[0]} blew up")
        w.out[a] = w.out.get(a, 0) + 1
        busy = frozenset(k for k, n in w.out.items() if n)
        w.together.add(busy)
        w.peak_accounts = max(w.peak_accounts, len(busy))
        w.peak_requests = max(w.peak_requests, sum(w.out.values()))
        try:
            await asyncio.sleep(w.rt)
        finally:
            w.out[a] -= 1
        hit = next((x for x in self.limited if call.startswith(x)), None)
        if hit is not None:
            self.limited.discard(hit)
            return False
        return True

    # --- the calls, as the Tradovate adapter answers them ---------------------------------------
    async def get_net_position(self, symbol):
        if not self._connected:
            raise RuntimeError("adapter not connected")
        if not await self._rt(f"get_net_position {symbol}"):
            raise RuntimeError(f"position/list {RATE_LIMITED}")
        return self.broker.net

    async def place_order(self, req):
        if not self._connected:
            return OrderResult(ok=False, error="adapter not connected")
        self.orders.append(req)
        if not await self._rt(f"place_order {req.order_type} {req.side} {req.qty}"):
            return OrderResult(ok=False, error=f"order/placeorder {RATE_LIMITED}")
        if req.order_type == "Market":
            self.broker.net += req.qty if req.side == "Buy" else -req.qty
        return OrderResult(ok=True, order_id="plain")

    async def place_bracket(self, req):
        r = await super().place_bracket(req)
        if r.ok:
            self.working |= {r.order_id, r.raw["sl_order_id"], r.raw["tp_order_id"]}
        return r

    async def cancel_order_by_id(self, order_id):
        if not self._connected:
            return OrderResult(ok=False, error="adapter not connected")
        self.cancelled.append(str(order_id))
        if not await self._rt(f"cancel {order_id}"):
            return OrderResult(ok=False, error=f"order/cancelorder {RATE_LIMITED}")
        oid = str(order_id)
        if oid in self.working and not oid.endswith(("-sl", "-tp")):
            self.working -= {f"{oid}-sl", f"{oid}-tp"}       # a WORKING entry takes its stop/target with it
        self.working.discard(oid)
        return OrderResult(ok=True)

    async def cancel_all(self):
        if not self._connected:
            return OrderResult(ok=False, error="adapter not connected")
        self.cancel_all_calls += 1
        if not await self._rt("cancel_all"):
            return OrderResult(ok=False, error=f"order/cancelallorders {RATE_LIMITED}")
        self.working.clear()
        return OrderResult(ok=True)

    async def flatten_all(self):
        if not self._connected:
            return OrderResult(ok=False, error="adapter not connected")
        self.flatten_calls += 1
        if not await self._rt("flatten_all"):
            return OrderResult(ok=False, error=f"position/list {RATE_LIMITED}")
        self.broker.net = 0
        return OrderResult(ok=True)

    async def get_order_status(self, order_id):
        self.wire.calls.append((self.account_id, f"get_order_status {order_id}"))   # the pushed cache: no round trip
        return self.order_status.get(str(order_id))

    @property
    def flat(self) -> bool:
        """Flat at the broker and nothing left working."""
        return self.broker.net == 0 and not self.working


def accounts(n: int) -> list[str]:
    return [f"a{i:02d}" for i in range(1, n + 1)]


def exit_cfg(n: int, strategies=("nq930",)) -> AppCfg:
    """`n` accounts, every one booked to every strategy (all NQ, qty 3)."""
    ids = accounts(n)
    return AppCfg(
        armed=True,
        accounts={a: AccountCfg(keyring_key="k", account_name=a.upper()) for a in ids},
        book={s: [{"account": a, "qty": 3} for a in ids] for s in strategies},
        strategies={s: StrategyCfg(symbol="NQ", qty=3, offset_pts=10.0, sl_pts=5.0, tp_pts=15.0,
                                   enabled=True) for s in strategies})


def go_live(eng: Engine, adapters: dict, strategy: str = "nq930", flat=()) -> None:
    """The morning, on every account at once: the straddle placed, the buy stop filled 3 (the engine
    cancels the sell stop and re-prices the stop/target), so each account is long 3 with its stop and
    target working. Accounts in `flat` were closed by their target since: no position, nothing working."""

    async def morning():
        out = await eng.handle_alert({**ALERT, "strategy": strategy})
        assert out["ok"], out
        for a, ad in adapters.items():
            st = eng._state(strategy, a)
            ad.working.discard(st.upper_id)                         # the entry filled
            await eng.on_fill(FillEvent(account_id=a, symbol="NQZ6", side="Buy", qty=3,
                                        price=24510.25, raw={"orderId": st.upper_id}))
            ad.broker.net += 3
            if a in flat:
                ad.working.clear()
                await eng.on_fill(FillEvent(account_id=a, symbol="NQZ6", side="Sell", qty=3,
                                            price=24525.25, raw={"orderId": st.up_tp_id}))
                ad.broker.net -= 3
    asyncio.run(morning())


def mkadapters(cfg: AppCfg, wire: Wire, same_broker=None) -> dict:
    """One SlowAdapter per account. `same_broker` {entry: other entry}: the first trades the SAME
    broker account as the second (an unpinned entry that landed on another entry's account)."""
    adapters: dict = {}
    for a in cfg.accounts:
        adapters[a] = SlowAdapter(a, wire, broker=adapters.get((same_broker or {}).get(a)))
    return adapters


def mkexits(tmp_path, n: int, *, rt: float = 0.0, strategies=("nq930",), flat=(), same_broker=None):
    """-> (engine, adapters, wire, clock): `n` accounts live long 3 NQ on every strategy, at 09:31 ET."""
    wire, clock = Wire(), Clock()
    cfg = exit_cfg(n, strategies)
    adapters = mkadapters(cfg, wire, same_broker)
    eng = Engine(cfg, adapters, now_fn=clock, root=tmp_path)
    for s in strategies:
        go_live(eng, adapters, s, flat)
    wire.clear()
    wire.rt = rt
    return eng, adapters, wire, clock
