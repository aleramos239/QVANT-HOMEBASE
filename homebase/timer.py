"""Self-fire timer: the strategy is pure clock, so the app IS the signal.

Per enabled strategy with self_fire (all times ET, weekdays only):

    9:20        gate — daily bars from market data, house ADX(14) TREND test
                (ungated strategies skip straight to staged)
    9:28:30     prestage — subscribe the live quote, warm everything
    9:30:00     anchor = the last trade OF ITS OWN SYMBOL that the exchange
                stamped before 09:30:00.000 → engine.handle_alert(
                source="timer"); every strategy due fires at the same moment,
                and only within FIRE_LATE_MAX_S of 09:30:00.000 — later (a
                desk restart, a late switch-on, a stalled loop) it is missed
    9:31        unsubscribe, done

Fail-safe by construction: no gate reading → no fire; stale quote → no
fire; past the fire's grace → no fire; day already acted (e.g. the TV
alert beat us) → no fire. Every decision is journaled. The TV alert stays
a cross-check — when disarmed both paths journal dry runs (free anchor
A/B); when armed the second arrival is refused by the one-trade-per-day
rule.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import sys
import time
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
FIRE_LATE_MAX_S = 1.0      # fire moment later than this after 09:30:00.000 -> MISSED, never
                           # fired. _sleep_s lands the fire tick ON 09:30:00.000 (late by loop
                           # jitter: ms); a stage on the tick across the open adds up to one
                           # TICK_S (0.2 s) plus its own round trips: 1 s is ~5 ticks of room.
                           # The anchor does not ride on it (the last trade the exchange stamped
                           # before 09:30:00.000, however late the fire): it only bounds how old
                           # the levels are when the orders go out. Past it = a desk restart, a
                           # strategy switched on / booked after the open, a stalled loop.
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
        # Inside the window, FIRE_LATE_MAX_S does the same from 09:30:01.
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

        if st["stage"] in ("idle", "gated", "staged") and self.engine.killed_today(name):
            st.update(stage="skipped", killed=True)       # the per-strategy Kill: never fire today
            self.engine.journal("timer_skipped", strategy=name, reason="killed")
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
            fire_at = dt.datetime.combine(dt.date.fromisoformat(date), FIRE_T, tzinfo=ET)
            # staged by an earlier tick: this tick woke late; staged just now:
            # the desk (re)started, or it was switched on / booked, after the open
            if self._missed_late(name, st, fire_at,
                                 "late_fire" if stage == "staged" else "late_start"):
                return
            import time as _t
            px, seen = (self._md.last(self._subs.get(s.symbol),
                                      before=fire_at.timestamp())
                        if self._md else (None, 0.0))
            if px is None or _t.time() - seen > QUOTE_MAX_AGE_S:
                st.update(stage="error",
                          error="no fresh trade stamped before 09:30:00 for the anchor")
                self.engine.journal("timer_error", strategy=name,
                                    error=st["error"])
                return
            st.update(anchor=px, stage="fired")
            return self._fire(name, s, st, px, fire_at)   # tick() fires all due at once

    def _missed_late(self, name, st, fire_at, reason) -> bool:
        """True, with the day marked missed and journaled, when now is more
        than FIRE_LATE_MAX_S past 09:30:00.000: the open has moved on, so the
        straddle is never placed on it."""
        now = self._now()
        late = now.timestamp() - fire_at.timestamp()
        if late <= FIRE_LATE_MAX_S:
            return False
        st.update(stage="missed", anchor=None)
        self.engine.journal("timer_missed", strategy=name, reason=reason,
                            at=now.astimezone(ET).strftime("%H:%M:%S.%f")[:-3],
                            late_s=round(late, 3), grace_s=FIRE_LATE_MAX_S)
        return True

    async def _prestage_skip(self, name, s, st) -> None:
        """User-approved (spec 2026-09-26): a booked account that already holds
        a position in this strategy's symbol at the prestage is skipped for
        the day — and so is one with a working order resting in it (ruling
        P1: it could fill inside the bot's window). Otherwise the bot would
        net against those contracts at its 12:55/15:55 flatten and could
        misattribute their fills.

        Orders are the adapter's cached view (trade_view, no broker call),
        matched by the engine's substring rule (NQ also claims MNQZ6); they
        are read first and always. So is the adapter's cached position view
        (trade_view()["positions"]), same substring rule — a naked MNQ
        position, or a different-expiry NQ position, triggers the skip even
        when the pinned contract's own net (below) reads flat. Positions are
        ALSO read from the broker (get_net_position), read concurrently, at
        most PRESTAGE_READ_S and always ending PRESTAGE_MARGIN_S before
        09:30:00 (ruling P6). A position that cannot be read (error, timeout,
        no time left) fires as before — unless a manual order or cached
        position is present: then the account is skipped
        (`position_unreadable`). An order whose contract is unresolved never
        skips by itself. Every decision is journaled, but a failing journal
        write never changes one (logged to stderr instead). Never raises on
        a read: the stage must not fail on this check. The read's own broker
        round trips (timing only, no extra request) are journaled as
        `prestage_rtt` {prestage_rtt_ms: {account: {request: ms}}}: the open's
        baseline next to the fire's `placed` leg_ms.

        Ruling (2026-09-26): if the strategy's day is no longer idle —
        already placed, live, done, or errored, e.g. a desk restart between
        09:30 and 09:45 replays gate -> stage on a fresh SelfTimer with no
        in-memory `st` — the bot's OWN fill now shows as a position at this
        same check and must never be mistaken for a manual one. No-op
        entirely: no skip, no journal, no readiness change."""
        if self.engine.day_status(name) != "idle":
            return

        def jnl(event, **kw):
            try:
                self.engine.journal(event, strategy=name, **kw)
            except Exception as e:  # noqa: BLE001 — the decision stands
                try:
                    print(f"homebase timer: journal {event} for {name} failed: {e!r} {kw}",
                          file=sys.stderr)
                except Exception:  # noqa: BLE001 — nothing in this path may raise into the stage
                    pass

        sym = s.symbol.upper()
        accounts = [a["account"] for a in assignments(self.cfg, name)]

        def cached_view(aid):
            """One trade_view() call per account, shared by the order and
            position checks below (never call it twice — a broken cache
            must journal ONE failure, not one per check)."""
            ad = self.engine.adapters.get(aid)
            try:
                return (ad.trade_view() if ad is not None else None), None  # None = no view
            except Exception as e:  # noqa: BLE001
                return None, "cached view: " + (str(e)[:120] or type(e).__name__)

        def orders_in(view):
            mine, unresolved, bad = [], [], 0
            for o in ((view or {}).get("orders") or []):
                try:
                    if o.get("symbol") is None:
                        unresolved.append(str(o.get("order_id")))
                    elif sym in str(o["symbol"]).upper():
                        mine.append(str(o.get("order_id")))
                except Exception:  # noqa: BLE001 — one bad cached order must not hide the rest
                    bad += 1
            problems = []
            if unresolved:
                problems.append(f"working order(s) {', '.join(unresolved)}: contract unresolved")
            if bad:
                problems.append(f"{bad} malformed cached order(s) ignored")
            return mine, ("; ".join(problems) if problems else None)

        def positions_in(view):
            """The same substring rule as orders_in, on the adapter's cached
            positions (trade_view()["positions"]): a naked MNQ position, or a
            different-expiry NQ position, is caught even when the pinned
            contract's own broker-read net (below) is flat. NEVER summed
            across contracts — a hedged MNQZ6 +1 / MNQH6 -1 book still holds
            a position in the bot's symbol, so any single matching contract
            with a non-zero net is enough; the reported net is that
            contract's own value (the first non-zero match)."""
            net, unresolved, bad = 0, [], 0
            for p in ((view or {}).get("positions") or []):
                try:
                    net_p = int(p.get("net") or 0)
                    if not net_p:
                        continue
                    if p.get("symbol") is None:
                        unresolved.append(str(p.get("contract_id")))
                    elif sym in str(p["symbol"]).upper() and not net:
                        net = net_p
                except Exception:  # noqa: BLE001 — one bad cached position must not hide the rest
                    bad += 1
            problems = []
            if unresolved:
                problems.append(f"position(s) {', '.join(unresolved)}: contract unresolved")
            if bad:
                problems.append(f"{bad} malformed cached position(s) ignored")
            return net, ("; ".join(problems) if problems else None)

        views = {aid: cached_view(aid) for aid in accounts}
        orders, cached_nets, view_errors = {}, {}, {}
        for aid, (view, verr) in views.items():
            view_errors[aid] = verr
            if verr is not None:
                orders[aid] = ([], None)
                cached_nets[aid] = (0, None)
                continue
            try:
                orders[aid] = orders_in(view)
            except Exception as e:  # noqa: BLE001 — a malformed cache must not crash the stage
                orders[aid] = ([], "order view: " + (str(e)[:120] or type(e).__name__))
            try:
                cached_nets[aid] = positions_in(view)
            except Exception as e:  # noqa: BLE001
                cached_nets[aid] = (0, "position view: " + (str(e)[:120] or type(e).__name__))

        rtts: dict = {}         # account -> {request: round trip ms}: timing only

        def timed(aid, ad, since) -> None:
            """The broker round trips of the read below (no extra request): the
            open's baseline, next to the fire's own `placed` leg_ms."""
            try:
                got = ad.request_rtts_ms(since)
            except Exception:  # noqa: BLE001 — timing never touches the check
                return
            if got:
                rtts[aid] = got

        async def read(aid):
            ad = self.engine.adapters.get(aid)
            if ad is None or not ad.connected:
                return aid, None, "not connected"
            since = time.perf_counter()
            try:
                return aid, await ad.get_net_position(s.symbol), None
            except Exception as e:  # noqa: BLE001
                return aid, None, str(e)[:120] or type(e).__name__
            finally:
                timed(aid, ad, since)

        now = self.now_et()
        st["prestage_checked_at"] = now.strftime("%H:%M:%S")   # the REAL check
                                                                # time, for readiness text
        left = (dt.datetime.combine(now.date(), FIRE_T, tzinfo=ET)
                - now).total_seconds() - PRESTAGE_MARGIN_S
        budget = min(PRESTAGE_READ_S, left)
        nets: dict = {}                   # account -> (net, error); absent = not read
        if budget <= 0:
            jnl("prestage_check_failed", error="too close to the fire")
        else:
            try:
                got = await asyncio.wait_for(asyncio.gather(*(read(a) for a in accounts)),
                                             budget)
                nets = {aid: (net, err) for aid, net, err in got}
            except Exception as e:  # noqa: BLE001 — incl. the timeout
                jnl("prestage_check_failed", error=str(e)[:200] or type(e).__name__)
            if rtts:
                jnl("prestage_rtt", prestage_rtt_ms=rtts)

        skipped, skipped_orders, skipped_unreadable = {}, {}, {}
        for aid in accounts:
            net, err = nets.get(aid, (None, None))
            mine, problem = orders[aid]
            cached_net, pos_problem = cached_nets[aid]
            if err is not None:
                jnl("prestage_check_failed", account=aid, error=err)
            if view_errors[aid] is not None:
                jnl("prestage_check_failed", account=aid, error=view_errors[aid])
            if problem is not None:
                jnl("prestage_check_failed", account=aid, error=problem)
            if pos_problem is not None:
                jnl("prestage_check_failed", account=aid, error=pos_problem)
            unreadable = aid not in nets or err is not None
            net_hit = net or cached_net              # OR: either source is enough
            if not (net_hit or mine):
                continue                      # flat / unreadable, no manual order: fire
            skipped[aid] = int(net_hit or 0)
            if mine:
                skipped_orders[aid] = mine
            if unreadable:
                skipped_unreadable[aid] = True   # the position itself is unknown, not just flat
            self.engine.skip_today(name, aid)
            jnl("timer_skipped", reason="manual_position" if net_hit else "manual_order",
                account=aid, net=int(net_hit or 0), orders=mine,
                **({"position_unreadable": True} if unreadable else {}))
        if skipped:
            st["skipped_accounts"] = skipped
        if skipped_orders:
            st["skipped_orders"] = skipped_orders
        if skipped_unreadable:
            st["skipped_unreadable"] = skipped_unreadable

    async def _fire(self, name, s, st, px, fire_at) -> None:
        # checked again AT the fire: another strategy's gate or stage earlier
        # in this same tick can hold it past the grace
        if self._missed_late(name, st, fire_at, "late_fire"):
            return
        out = await self.engine.handle_alert(
            {"strategy": name, "upper": px + s.offset_pts,
             "lower": px - s.offset_pts}, source="timer")
        self.engine.journal("timer_fired", strategy=name, anchor=px,
                            result=out.get("ok"),
                            note=out.get("reason") or out.get("note"))

    def _sleep_s(self) -> float:
        """One tick — except when a strategy is staged and 9:30:00 is closer
        than that: then exactly the time left, so the fire lands on
        9:30:00.000 instead of up to a tick late. (The anchor does not ride on
        this: it is the last trade the exchange stamped before 09:30:00.000,
        as in the research, however late the fire — see FIRE_LATE_MAX_S.)"""
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
