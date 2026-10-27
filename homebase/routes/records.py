"""Read-only records: a strategy's research curve, its live detail, and the account calendar.

Moved verbatim from homebase.server.create_app (2026-10-20): same paths, same bodies, registered straight on the app."""
from __future__ import annotations

import asyncio
import json

from fastapi import HTTPException

from .. import equity
from ..metrics import strategy_live_detail


def register(app, *, STATIC, _equity_path, adapters, cfg, journal_cache, state_dir) -> None:

    @app.get("/api/research-equity")
    async def research_equity(strategy: str):
        """The strategy's backtest equity curve — a committed research
        artifact (real export), or nothing. Never synthesized."""
        s = cfg.strategies.get(strategy)
        fname = (s.metrics or {}).get("equity_file") if s else None
        p = STATIC.parent / "research" / fname if fname else None
        if not p or not p.exists():
            return {"points": None}
        return json.loads(p.read_text())

    @app.get("/api/strategy-live")
    async def strategy_live(strategy: str):
        """One strategy's live record — calendar days, metrics, trade log —
        summed across every account running it, from real fills only."""
        if strategy not in cfg.strategies:
            raise HTTPException(404, f"unknown strategy {strategy!r}")
        jp = state_dir() / "journal.jsonl"
        snap = await asyncio.to_thread(journal_cache.whole, jp)    # in a thread: parsed once, then only what is new
        if strategy not in cfg.strategies:                         # removed while it read: unknown, as it is now
            raise HTTPException(404, f"unknown strategy {strategy!r}")
        # a line that is JSON but not an object made this a 500 before: then it reads the file itself, as before
        return strategy_live_detail(jp, strategy, cfg, None if snap is None or snap[1] else snap[0])

    @app.get("/api/calendar")
    async def calendar(month: str, account: str = ""):
        if not account:
            for ad in adapters.values():
                try:
                    m = await ad.get_metrics()
                    if m.get("account"):
                        account = str(m["account"])
                        break
                except Exception:  # noqa: BLE001
                    continue
        d = equity.daily_pnl(_equity_path(), account, month)
        return {"account": account, "month": month, **d,
                "history_since": next(iter(equity.equity_by_day(_equity_path(), account)), None)}

