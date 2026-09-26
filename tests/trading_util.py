"""Shared fakes for the chart-trading tests: a desk with two accounts, no broker, no network."""
from __future__ import annotations

import asyncio
import json

from homebase import symbols
from homebase.broker.base import OrderResult
from homebase.config import AccountCfg, AppCfg, ChartTradingCfg, StrategyCfg
from homebase.engine import Engine
from homebase.trading import ChartDesk
from tests.test_engine import Clock, FakeAdapter

NQC = symbols.resolve_contract("NQ")
ESC = symbols.resolve_contract("ES")
MNQC = symbols.resolve_contract("MNQ")


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


class Mono:
    """Injected monotonic clock for the rate limiter."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class TradeAdapter(FakeAdapter):
    """FakeAdapter + the chart-trading surface: a live view, symbol-scoped
    flatten/cancel, a pinned account."""

    def __init__(self, aid):
        super().__init__(aid)
        self.pinned_ok = True
        self.view = {"broker_account": aid.upper(), "pinned": True, "seeded": True,
                     "balance": 50000.0, "realized_pnl": 0.0, "positions": [], "orders": []}
        self.flattened: list[str] = []
        self.sym_cancelled: list[str] = []
        self.fail_flatten = False

    def trade_view(self):
        return {**self.view, "positions": [dict(p) for p in self.view["positions"]],
                "orders": [dict(o) for o in self.view["orders"]]}

    def contract_name(self, cid):
        return {1: NQC, 2: ESC}.get(cid)

    async def flatten_symbol(self, symbol):
        self.flattened.append(symbol)
        if self.fail_flatten:
            return OrderResult(ok=False, error="flatten rejected by test")
        return OrderResult(ok=True, raw={"net_before": self.net})

    async def cancel_symbol(self, symbol):
        self.sym_cancelled.append(symbol)
        return OrderResult(ok=True, raw={"cancelled": 1})


def mkdesk(tmp_path, *, enabled=True, et=(11, 0), book=None):
    """Desk at `et` ET on Monday 2026-09-14 (EDT). a1 is booked to nq930 (NQ)."""
    clock = Clock()
    clock.set_et(*et)
    cfg = AppCfg(
        armed=True, webhook_secret="s",
        accounts={a: AccountCfg(keyring_key="k", account_name=a.upper(), label=a.upper())
                  for a in ("a1", "a2")},
        book=book if book is not None else {"nq930": [{"account": "a1", "qty": 3}]},
        strategies={"nq930": StrategyCfg(symbol="NQ", qty=3, offset_pts=10.0, sl_pts=5.0,
                                         tp_pts=15.0, enabled=True, self_fire=True)},
        chart_trading=ChartTradingCfg(enabled=enabled))
    adapters = {a: TradeAdapter(a) for a in cfg.accounts}
    engine = Engine(cfg, adapters, now_fn=clock, root=tmp_path)
    saved: list = []
    mono = Mono()
    desk = ChartDesk(cfg, engine, adapters, {}, save=saved.append, mono=mono,
                     timer_status=lambda: {"date": "2026-09-14", "strategies": {
                         "nq930": {"stage": "gated", "gate": True, "adx": 23.4, "anchor": None}}})
    return desk, engine, adapters, clock, mono, saved


def quote(clock, root="NQ", last=100.0, age_s=0.0):
    """The `quotes` block the chart service attaches to a proxied body."""
    ms = int((clock().timestamp() - age_s) * 1000)
    return {root: {"bid": last - 0.25, "ask": last, "last": last, "ts_ms": ms}}


def journal(tmp_path):
    p = tmp_path / "journal.jsonl"
    return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []


def drain(q) -> list:
    return [q.get_nowait() for _ in range(q.qsize())]
