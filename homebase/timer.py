"""Self-fire timer: the strategy is pure clock, so the app IS the signal.

Per enabled strategy with self_fire (all times ET, weekdays only):

    9:20        gate — daily bars from market data, house ADX(14) TREND test
                (ungated strategies skip straight to staged)
    9:28:30     prestage — subscribe the live quote, warm everything
    9:30:00     anchor = last trade → engine.handle_alert(source="timer")
    9:31        unsubscribe, done

Fail-safe by construction: no gate reading → no fire; stale quote → no
fire; day already acted (e.g. the TV alert beat us) → no fire. Every
decision is journaled. The TV alert stays a cross-check — when disarmed
both paths journal dry runs (free anchor A/B); when armed the second
arrival is refused by the one-trade-per-day rule.
"""
from __future__ import annotations

import asyncio
import datetime as dt
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from .config import AppCfg
from .engine import Engine
from .gate import trend_gate

ET = ZoneInfo("America/New_York")

GATE_T = dt.time(9, 20)
STAGE_T = dt.time(9, 28, 30)
FIRE_T = dt.time(9, 30, 0)
DONE_T = dt.time(9, 31)
QUOTE_MAX_AGE_S = 15.0     # anchor must come from a trade this fresh
GATE_RETRY_S = 60.0
GATE_BARS = 250            # ask for plenty; Tradovate serves ~120 dailies
MIN_GATE_BARS = 110        # RMA needs history to converge: at 119 bars the
                           # ADX sits within 0.05 of the research value, at
                           # 100 it drifts 0.35 — below 110, refuse to gate


class SelfTimer:
    def __init__(self, cfg: AppCfg, engine: Engine, md_factory: Callable,
                 now_fn: Callable[[], dt.datetime] | None = None):
        self.cfg = cfg
        self.engine = engine
        self._md_factory = md_factory
        self._now = now_fn or (lambda: dt.datetime.now(dt.timezone.utc))
        self._md = None
        self._sub: Optional[str] = None
        self._gate_attempt: float = 0.0
        self.days: dict = {}          # date -> {strategy: state dict}

    def now_et(self) -> dt.datetime:
        return self._now().astimezone(ET)

    def _day(self, date: str) -> dict:
        if date not in self.days:
            self.days.clear()               # keep only today
            self.days[date] = {}
        return self.days[date]

    def status(self) -> dict:
        date = self.now_et().date().isoformat()
        return {"date": date, "strategies": self._day(date)}

    async def _ensure_md(self):
        if self._md is None or not self._md.connected:
            self._md = self._md_factory()
            await self._md.connect()
        return self._md

    async def tick(self) -> None:
        now = self.now_et()
        if now.weekday() >= 5:
            return
        date = now.date().isoformat()
        day = self._day(date)
        t = now.time()
        for name, s in self.cfg.strategies.items():
            if not (s.enabled and getattr(s, "self_fire", False)):
                continue
            st = day.setdefault(name, {"stage": "idle", "gate": None,
                                       "adx": None, "anchor": None})
            try:
                await self._advance(name, s, st, t, date)
            except Exception as e:  # noqa: BLE001 — journal, never die
                st["stage"] = "error"
                st["error"] = str(e)
                self.engine.journal("timer_error", strategy=name, error=str(e))

    async def _advance(self, name, s, st, t, date) -> None:
        stage = st["stage"]
        if stage in ("fired", "skipped", "done", "error"):
            if stage == "error" and t < STAGE_T:
                st["stage"] = "idle"        # errors before staging retry
            elif t >= DONE_T and self._sub:
                md, sub = self._md, self._sub
                self._sub = None
                await md.unsubscribe_quote(sub)
            else:
                return

        if st["stage"] == "idle" and t >= GATE_T:
            if not s.gated:
                st.update(gate=True, stage="gated")
            else:
                import time as _t
                if _t.time() - self._gate_attempt < GATE_RETRY_S:
                    return
                self._gate_attempt = _t.time()
                md = await self._ensure_md()
                bars = [b for b in await md.daily_bars(s.symbol, GATE_BARS)
                        if b["date"] < date]        # completed days only
                gate, adx = (None, None) if len(bars) < MIN_GATE_BARS \
                    else trend_gate(bars)
                st.update(gate=gate, adx=adx, stage="gated")
                self.engine.journal("timer_gate", strategy=name, gate=gate,
                                    adx=adx, bars=len(bars))

        if st["stage"] == "gated" and t >= STAGE_T:
            md = await self._ensure_md()
            if self._sub is None:
                self._sub = await md.subscribe_quote(s.symbol)
            st["stage"] = "staged"

        if st["stage"] == "staged" and t >= FIRE_T:
            if st["gate"] is False:
                st["stage"] = "skipped"
                self.engine.journal("timer_skipped", strategy=name,
                                    reason="gate_chop", adx=st["adx"])
                return
            if st["gate"] is None:
                st.update(stage="error", error="gate unknown — refusing to fire")
                self.engine.journal("timer_error", strategy=name,
                                    error=st["error"])
                return
            day = self.engine.day_status(name)
            if day != "idle":
                st["stage"] = "done"        # something (TV?) already acted
                self.engine.journal("timer_deferred", strategy=name,
                                    status=day)
                return
            import time as _t
            md = self._md
            px = md.last_trade if md else None
            if px is None or _t.time() - md.last_trade_ts > QUOTE_MAX_AGE_S:
                st.update(stage="error", error="no fresh trade for the anchor")
                self.engine.journal("timer_error", strategy=name,
                                    error=st["error"])
                return
            st.update(anchor=px, stage="fired")
            out = await self.engine.handle_alert(
                {"strategy": name, "upper": px + s.offset_pts,
                 "lower": px - s.offset_pts}, source="timer")
            self.engine.journal("timer_fired", strategy=name, anchor=px,
                                result=out.get("ok"),
                                note=out.get("reason") or out.get("note"))

    async def loop(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception as e:  # noqa: BLE001
                self.engine.journal("timer_loop_error", error=str(e))
            await asyncio.sleep(0.2)
