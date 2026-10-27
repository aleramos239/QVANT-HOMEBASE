"""The bars price feed: up only while a bars strategy is enabled and the RTH window is open; closed bars go through
the rules, signals to the engine.

Moved verbatim from homebase.server.create_app."""
from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
from types import SimpleNamespace

from .. import config as config_mod
from ..broker.tradovate import RENEW_EARLY_FROM, RENEW_EARLY_UNTIL
from ..rules import RULES

FEED_FROM = (8, 55)        # the price feed runs through the RTH day, weekdays
FEED_UNTIL = (16, 10)
FEED_RETRY_S = 30


def feed_window(now_et) -> bool:
    if now_et.weekday() >= 5:
        return False
    import datetime as dt
    return dt.time(*FEED_FROM) <= now_et.time() <= dt.time(*FEED_UNTIL)


def feed_recycle_window(now_et) -> bool:
    """Weekdays, the early-renewal window (09:10-09:19:30 ET, broker/tradovate.py): a feed
    on an older md token than its login now holds is rebuilt on the new one before 09:20,
    so it cannot die at the old token's expiry around the 9:30 fire."""
    return now_et.weekday() < 5 and RENEW_EARLY_FROM <= now_et.time() < RENEW_EARLY_UNTIL


def _rides_older_token(feed) -> bool:
    try:
        return bool(feed.rides_older_token())
    except Exception:  # noqa: BLE001 — unknown is not "older"
        return False



def make(*, cfg, engine, adapters, feed_factory) -> SimpleNamespace:
    feed_box: dict = {"feed": None, "retry_at": 0.0, "error": None}

    def _bars_strategies() -> dict[str, config_mod.StrategyCfg]:
        return {n: s for n, s in cfg.strategies.items()
                if s.enabled and getattr(s, "kind", "straddle") == "bars"}

    async def _feed_close(reason: str) -> None:
        f = feed_box["feed"]
        feed_box["feed"] = None
        if f is not None:
            with contextlib.suppress(Exception):
                await f.close()
            engine.journal("feed_stopped", reason=reason)

    async def feed_step(now_et=None) -> list[dict]:
        """One step of the price feed: keep it up (only) while a bars
        strategy is enabled and the market window is open; drain closed
        bars into the rules; hand signals to the engine. Returns what the
        rules produced (for tests / the log)."""
        import time as _t
        now_et = now_et or engine.now_et()
        strategies = _bars_strategies()
        if not strategies or not feed_window(now_et):
            if feed_box["feed"] is not None:
                await _feed_close("window closed" if strategies else "no bars strategy enabled")
            return []
        f = feed_box["feed"]
        if f is not None and f.connected and feed_recycle_window(now_et) \
                and _rides_older_token(f):
            # an early renewal rolled its login's md token: rebuild now, on the new one --
            # riding the old one, it would die at that token's expiry, maybe at the 9:30 fire
            await _feed_close("recycled onto the renewed market-data token before 09:20")
            f = None
        if f is None or not f.connected:
            if _t.time() < feed_box["retry_at"]:
                return []
            try:
                if f is not None:
                    with contextlib.suppress(Exception):
                        await f.close()
                f = feed_box["feed"] = feed_factory(cfg, adapters)
                await f.connect()
                for s in strategies.values():
                    await f.watch_bars(s.symbol, int(s.bar_minutes), int(s.warmup_bars))
                feed_box["error"] = None
                engine.journal("feed_started", watching=list(f.status()["watching"]))
            except Exception as e:  # noqa: BLE001 — retry, never die
                feed_box["error"] = str(e)[:200]
                # a rate-limit penalty ("180 requests per hour") means every
                # retry costs budget: rest 5 minutes, not 30 seconds
                penalized = "p-ticket" in str(e) or "Rate limit" in str(e)
                feed_box["retry_at"] = _t.time() + (300 if penalized else FEED_RETRY_S)
                engine.journal("feed_error", error=str(e)[:200], penalized=penalized)
                return []
        for s in strategies.values():           # a strategy enabled after start
            if (s.symbol, int(s.bar_minutes)) not in f.watching():
                try:
                    await f.watch_bars(s.symbol, int(s.bar_minutes), int(s.warmup_bars))
                except Exception as e:  # noqa: BLE001
                    engine.journal("feed_error", error=str(e)[:200])
        out = []
        for root, minutes, bar in f.tick(now_et.astimezone(dt.timezone.utc)):
            for name, s in strategies.items():
                if s.symbol != root or int(s.bar_minutes) != minutes:
                    continue
                rule = RULES.get(s.rule)
                if rule is None:
                    engine.journal("feed_error", strategy=name, error=f"unknown rule {s.rule!r}")
                    continue
                try:
                    sig = rule(f.bars(root, minutes), now_et, s)
                except Exception as e:  # noqa: BLE001 — a rule bug is journaled, not fatal
                    engine.journal("rule_error", strategy=name, error=str(e)[:200])
                    continue
                if sig is None:
                    continue
                res = await engine.handle_signal(name, sig, source="feed")
                out.append({"strategy": name, "signal": sig, "result": res})
        return out

    def feed_status() -> dict:
        f = feed_box["feed"]
        st = f.status() if f is not None else {"connected": False, "watching": {}}
        return {**st, "error": feed_box["error"],
                "window": feed_window(engine.now_et())}

    async def _feed_loop():
        while True:
            try:
                await feed_step()
            except Exception as e:  # noqa: BLE001 — the feed loop must never die
                engine.journal("feed_loop_error", error=str(e)[:200])
            await asyncio.sleep(1.0)

    return SimpleNamespace(box=feed_box, step=feed_step, status=feed_status, close=_feed_close, loop=_feed_loop)
