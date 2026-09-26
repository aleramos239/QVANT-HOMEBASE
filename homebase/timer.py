"""Self-fire timer: the strategy is pure clock, so the app IS the signal.

Per enabled strategy with self_fire (all times ET, weekdays only):

    9:20        gate — daily bars from market data, house ADX(14) TREND test
                (ungated strategies skip straight to staged)
    9:28:30     prestage — subscribe the live quote, warm everything
    9:30:00     anchor = last trade OF ITS OWN SYMBOL → engine.handle_alert(
                source="timer"); every strategy due fires at the same moment
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
from typing import Callable
from zoneinfo import ZoneInfo

from .config import AppCfg, assignments
from .engine import Engine, _hhmm
from .gate import trend_gate

ET = ZoneInfo("America/New_York")

GATE_T = dt.time(9, 20)
STAGE_T = dt.time(9, 28, 30)
FIRE_T = dt.time(9, 30, 0)
DONE_T = dt.time(9, 31)
TICK_S = 0.2
QUOTE_MAX_AGE_S = 15.0     # anchor must come from a trade this fresh
GATE_RETRY_S = 60.0
GATE_BARS = 250            # ask for plenty; Tradovate serves ~120 dailies
MIN_GATE_BARS = 110        # RMA needs history to converge: at 119 bars the
                           # ADX sits within 0.05 of the research value, at
                           # 100 it drifts 0.35 — below 110, refuse to gate
PRESTAGE_READ_S = 2.0      # every booked account's position, read concurrently, at most this long
PRESTAGE_MARGIN_S = 0.5    # ...and never closer than this to 09:30:00 (ruling P6)


class SelfTimer:
    def __init__(self, cfg: AppCfg, engine: Engine, md_factory: Callable,
                 now_fn: Callable[[], dt.datetime] | None = None):
        self.cfg = cfg
        self.engine = engine
        self._md_factory = md_factory
        self._now = now_fn or (lambda: dt.datetime.now(dt.timezone.utc))
        self._md = None
        self._subs: dict[str, str] = {}   # strategy symbol -> quote feed (contract)
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
        fires = []
        for name, s in self.cfg.strategies.items():
            if not (s.enabled and getattr(s, "self_fire", False)
                    and getattr(s, "kind", "straddle") == "straddle"):
                continue                     # bars strategies run off the feed
            st = day.setdefault(name, {"stage": "idle", "gate": None,
                                       "adx": None, "anchor": None})
            try:
                fire = await self._advance(name, s, st, t, date)
            except Exception as e:  # noqa: BLE001 — journal, never die
                st["stage"] = "error"
                st["error"] = str(e)
                self.engine.journal("timer_error", strategy=name, error=str(e))
                continue
            if fire is not None:
                fires.append((name, st, fire))
        # everything due at 9:30 fires together — no strategy waits on
        # another's broker round trip
        results = await asyncio.gather(*(f for _, _, f in fires),
                                       return_exceptions=True)
        for (name, st, _), r in zip(fires, results):
            if isinstance(r, Exception):
                st["stage"] = "error"
                st["error"] = str(r)
                self.engine.journal("timer_error", strategy=name, error=str(r))

    async def _advance(self, name, s, st, t, date):
        """Move one strategy along its stages; at 9:30 return its fire
        (a coroutine) so tick() can launch every due fire at once."""
        # HARD upper bound. Without it every stage test is "t >= <time>",
        # which is true at 11pm too: a restart any time after 9:30 would
        # stage and fire immediately on a stale anchor. (The engine's accept
        # window catches it, but the timer must not try in the first place.)
        end = _hhmm(s.accept_until_et)
        if t > end:
            if st["stage"] in ("idle", "gated", "staged"):
                st["stage"] = "missed"
                self.engine.journal("timer_missed", strategy=name,
                                    at=str(t), window_end=s.accept_until_et)
            sub = self._subs.pop(s.symbol, None)
            if sub is not None and self._md is not None:
                await self._md.unsubscribe_quote(sub)
            return

        stage = st["stage"]
        if stage in ("fired", "skipped", "done", "error", "missed"):
            if stage == "error" and t < STAGE_T:
                st["stage"] = "idle"        # errors before staging retry
            elif t >= DONE_T and s.symbol in self._subs:
                await self._md.unsubscribe_quote(self._subs.pop(s.symbol))
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
            if s.symbol not in self._subs:
                self._subs[s.symbol] = await md.subscribe_quote(s.symbol)
            await self._prestage_skip(name, s, st)
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
            px, seen = (self._md.last(self._subs.get(s.symbol))
                        if self._md else (None, 0.0))
            if px is None or _t.time() - seen > QUOTE_MAX_AGE_S:
                st.update(stage="error", error="no fresh trade for the anchor")
                self.engine.journal("timer_error", strategy=name,
                                    error=st["error"])
                return
            st.update(anchor=px, stage="fired")
            return self._fire(name, s, px)      # tick() fires all due at once

    async def _prestage_skip(self, name, s, st) -> None:
        """User-approved (spec 2026-09-26): a booked account that already holds
        a position in this strategy's symbol at the prestage is skipped for
        the day — and so is one with a working order resting in it (ruling
        P1: it could fill inside the bot's window). Otherwise the bot would
        net against those contracts at its 12:55/15:55 flatten and could
        misattribute their fills. Positions are the broker's
        (get_net_position), read concurrently; orders are the adapter's
        cached view (trade_view, no broker call), matched by the engine's
        substring rule (NQ also claims MNQZ6). The read takes at most
        PRESTAGE_READ_S and always ends PRESTAGE_MARGIN_S before 09:30:00
        (ruling P6). Unreadable, timed out, no time left, or an order whose
        contract is unresolved -> the account fires as before (journaled).
        Never raises: the stage must not fail on this check."""
        now = self.now_et()
        left = (dt.datetime.combine(now.date(), FIRE_T, tzinfo=ET)
                - now).total_seconds() - PRESTAGE_MARGIN_S
        budget = min(PRESTAGE_READ_S, left)
        if budget <= 0:
            self.engine.journal("prestage_check_failed", strategy=name,
                                error="too close to the fire")
            return
        sym = s.symbol.upper()

        async def read(aid):
            ad = self.engine.adapters.get(aid)
            if ad is None or not ad.connected:
                return aid, None, [], None, "not connected"
            try:
                net = await ad.get_net_position(s.symbol)
            except Exception as e:  # noqa: BLE001
                return aid, None, [], None, str(e)[:120] or type(e).__name__
            mine, problem = [], None
            try:
                view = ad.trade_view()          # cache only; None = no order view
                unresolved = []
                for o in ((view or {}).get("orders") or []):
                    if o.get("symbol") is None:
                        unresolved.append(str(o.get("order_id")))
                    elif sym in str(o["symbol"]).upper():
                        mine.append(str(o.get("order_id")))
                if unresolved:
                    problem = (f"working order(s) {', '.join(unresolved)}: "
                               "contract unresolved")
            except Exception as e:  # noqa: BLE001
                mine, problem = [], "order view: " + (str(e)[:120] or type(e).__name__)
            return aid, net, mine, problem, None

        try:
            got = await asyncio.wait_for(
                asyncio.gather(*(read(a["account"]) for a in assignments(self.cfg, name))),
                budget)
        except Exception as e:  # noqa: BLE001 — incl. the timeout: fire as before
            self.engine.journal("prestage_check_failed", strategy=name,
                                error=str(e)[:200] or type(e).__name__)
            return
        skipped, skipped_orders = {}, {}
        for aid, net, orders, problem, err in got:
            if err is not None:
                self.engine.journal("prestage_check_failed", strategy=name, account=aid, error=err)
                continue
            if problem is not None:
                self.engine.journal("prestage_check_failed", strategy=name, account=aid,
                                    error=problem)
            if net or orders:
                skipped[aid] = int(net or 0)
                if orders:
                    skipped_orders[aid] = orders
                self.engine.skip_today(name, aid)
                self.engine.journal("timer_skipped", strategy=name,
                                    reason="manual_position" if net else "manual_order",
                                    account=aid, net=int(net or 0), orders=orders)
        if skipped:
            st["skipped_accounts"] = skipped
        if skipped_orders:
            st["skipped_orders"] = skipped_orders

    async def _fire(self, name, s, px) -> None:
        out = await self.engine.handle_alert(
            {"strategy": name, "upper": px + s.offset_pts,
             "lower": px - s.offset_pts}, source="timer")
        self.engine.journal("timer_fired", strategy=name, anchor=px,
                            result=out.get("ok"),
                            note=out.get("reason") or out.get("note"))

    def _sleep_s(self) -> float:
        """One tick — except when a strategy is staged and 9:30:00 is closer
        than that: then exactly the time left, so the fire lands on
        9:30:00.000 instead of up to a tick late (and the anchor is the last
        trade BEFORE the open, as in the research, not one after it)."""
        now = self.now_et()
        staged = any(st.get("stage") == "staged"
                     for st in self.days.get(now.date().isoformat(), {}).values())
        left = (dt.datetime.combine(now.date(), FIRE_T, tzinfo=ET)
                - now).total_seconds()
        return left if staged and 0 < left < TICK_S else TICK_S

    async def loop(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception as e:  # noqa: BLE001
                self.engine.journal("timer_loop_error", error=str(e))
            await asyncio.sleep(self._sleep_s())
