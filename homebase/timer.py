"""Self-fire timer: the strategy is pure clock, so the app IS the signal.

Per enabled strategy with self_fire (all times ET, weekdays only):

    9:20        gate — daily bars from market data, house ADX(14) TREND test
                (ungated strategies skip straight to staged)
    9:28:30     prestage — subscribe the live quote, warm everything
    9:30:00     anchor = the last trade OF ITS OWN SYMBOL received before
                09:30:00.000 → engine.handle_alert(
                source="timer"); every strategy due fires at the same moment.
                A fire more than FIRE_LATE_MAX_S past 09:30:00.000 (a desk
                restart, a late switch-on, a slow stage, a stalled loop)
                still goes out while the accept window is open, on the
                latest trade at that moment — journaled late, with why.
                No fresh trade yet (none at all, or the newest too old):
                it waits, trying every tick, and fires on the first fresh
                trade — until the accept window closes: then missed
    9:31        unsubscribe, done

Fail-safe by construction: no gate reading → no fire; no fresh quote → no
fire (yet); accept window over → no fire; day already acted (e.g. the TV
alert beat us) → no fire; fired once → never again that day, restarts
included. Every decision is journaled. The TV alert stays
a cross-check — when disarmed both paths journal dry runs (free anchor
A/B); when armed the second arrival is refused by the one-trade-per-day
rule.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
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
FIRE_LATE_MAX_S = 1.0      # a fire moment within this of 09:30:00.000 is ON TIME: anchored on
                           # the last trade RECEIVED before 09:30:00.000 (the research anchor).
                           # _sleep_s lands the fire tick ON 09:30:00.000 (late by loop jitter:
                           # ms); a stage on the tick across the open adds up to one TICK_S
                           # (0.2 s) plus its own round trips: 1 s is ~5 ticks of room. Past it
                           # (a desk restart, a strategy switched on after the open, a slow
                           # stage, a stalled loop) the fire is LATE: it still goes out while
                           # the accept window is open, on the latest trade at that moment --
                           # both stops sit offset_pts either side of the current price, so
                           # nothing is placed through the market -- journaled late, with why.
QUOTE_MAX_AGE_S = 15.0     # anchor must come from a trade this fresh
STAMP_RAW_MAX = 40         # a quote push's raw `timestamp`, as journaled
GATE_RETRY_S = 60.0
GATE_BARS = 250            # ask for plenty; Tradovate serves ~120 dailies
MIN_GATE_BARS = 110        # RMA needs history to converge: at 119 bars the
                           # ADX sits within 0.05 of the research value, at
                           # 100 it drifts 0.35 — below 110, refuse to gate
PRESTAGE_READ_S = 2.0      # every booked account's position, read concurrently, at most this long
PRESTAGE_MARGIN_S = 0.5    # ...and never closer than this to 09:30:00 (ruling P6)

# why a fire was late or off the pre-open anchor, or a day missed, in plain words (the
# review, readiness; the charts pill, homebase/static/charts/trade.js, keeps the same words)
LATE_WHY = {"late_start": "the desk started after the open",
            "late_switch_on": "it was switched on after the open",
            "late_stage": "it was not staged by the open",
            "no_pre_open_quote": "it had no fresh quote before the open"}
MISS_WHY = {"late_start": "the desk started after the accept window closed",
            "late_switch_on": "it was switched on after the accept window closed",
            "window_closed": "the accept window closed before it could fire",
            "no_fresh_quote": "no fresh quote came before the accept window closed"}
# a timer outcome in the journal -> the stage it leaves (after a restart: what stands)
DECIDED = {"timer_fired": "fired", "timer_skipped": "skipped", "timer_error": "error",
           "timer_deferred": "done", "timer_missed": "missed"}
# a fire's status fields, as the journal also has them (a restart restores them)
FIRED_KEYS = ("anchor", "late", "late_s", "reason", "anchor_source", "waited_s")


def fire_clock(late_s) -> str:
    """09:30:00 + late_s as the fire's ET wall time to the second: "9:31:04"."""
    s = FIRE_T.hour * 3600 + FIRE_T.minute * 60 + FIRE_T.second + int(float(late_s or 0))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def late_why(reason, late_s, waited_s=None) -> str:
    """Why a fire was late or off the pre-open anchor, in plain words: "the
    fire ran 2.1 s late", "it waited 600.2 s for a fresh quote"."""
    waited = float(waited_s or 0)
    if reason == "waited_for_quote":
        return f"it waited {waited:.1f} s for a fresh quote"
    if reason == "late_fire":
        why = f"the fire ran {float(late_s or 0) - waited:.1f} s late"
    else:
        why = LATE_WHY.get(reason, f"it fired {float(late_s or 0):.1f} s past the open")
    return why + (f", then waited {waited:.1f} s for a fresh quote" if waited else "")


def off_anchor(e: dict) -> bool:
    """A timer fire past its grace, or not on the pre-open anchor: said loud."""
    return e.get("late") is True or e.get("anchor_source") == "current"


def fire_said(e: dict) -> str:
    """A loud fire (off_anchor) in plain words: "fired late at 9:31:04 · the desk
    started after the open"; "fired at 9:30:00, off the pre-open anchor · it had
    no fresh quote before the open"."""
    lead = (f"fired late at {fire_clock(e.get('late_s'))}" if e.get("late") is True
            else f"fired at {fire_clock(e.get('late_s'))}, off the pre-open anchor")
    return f"{lead} · {late_why(e.get('reason'), e.get('late_s'), e.get('waited_s'))}"


def miss_why(reason) -> str:
    return MISS_WHY.get(reason, "its accept window closed before it fired")


def _et_ms(ts) -> str | None:
    """unix seconds -> ET "HH:MM:SS.mmm"; None when it is no usable instant."""
    try:
        return dt.datetime.fromtimestamp(ts, ET).strftime("%H:%M:%S.%f")[:-3]
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _push_fields(prefix: str, p) -> dict:
    """One kept trade push (TradovateMD.trade_push) as journal fields: when it
    was received, the `timestamp` it carried (raw, and parsed) and received
    minus stamped. The first live mornings read these to learn that field's
    presence and format and the clock/feed skew; the anchor never uses them."""
    seen, raw, ts = (p[0], p[2], p[3]) if p is not None else (None, None, None)
    return {f"{prefix}_seen": _et_ms(seen) if seen is not None else None,
            f"{prefix}_stamp_raw": str(raw)[:STAMP_RAW_MAX] if raw is not None else None,
            f"{prefix}_stamp": _et_ms(ts) if ts is not None else None,
            f"{prefix}_lag_ms": (round((seen - ts) * 1000)
                                 if seen is not None and ts is not None else None)}


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
        self._up_at: dt.datetime | None = None   # this timer's first tick: the desk came up
        self._decided_day: tuple = (None, {})     # (date, today's journaled outcomes): _decided

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
        if self._up_at is None:
            self._up_at = now
        if now.weekday() >= 5:
            return
        date = now.date().isoformat()
        day = self._day(date)
        t = now.time()
        mine = []
        for name, s in self.cfg.strategies.items():
            if not (s.enabled and getattr(s, "self_fire", False)
                    and getattr(s, "kind", "straddle") == "straddle"):
                continue                     # bars strategies run off the feed
            st = day.get(name)
            if st is None:                   # first seen (seen_at: a late fire's why)
                st = day[name] = {"stage": "idle", "gate": None, "adx": None,
                                  "anchor": None, "seen_at": _et_ms(now.timestamp())}
            mine.append((name, s, st))
        # Staged by an earlier tick (or waiting for a quote), a strategy reaches
        # its fire with no await (the anchor is a read of the quote already
        # kept): every one due fires first, together -- no strategy waits on
        # another's broker round trip -- and before any other strategy
        # advances: a gate retry, a stage or an md reconnect can take seconds,
        # and would hold these orders on levels read at 09:30:00.000.
        staged = [m for m in mine if m[2]["stage"] in ("staged", "waiting")]
        rest = [m for m in mine if m[2]["stage"] not in ("staged", "waiting")]
        await self._settle(await self._advance_all(staged, t, date))
        await self._settle(await self._advance_all(rest, t, date))

    async def _advance_all(self, todo, t, date) -> list:
        """_advance each (name, cfg, state) in turn. A fire is launched the moment
        _advance returns it, so it never waits behind a later strategy's gate or
        stage. -> [(name, state, fire task)]"""
        fires = []
        for name, s, st in todo:
            try:
                fire = await self._advance(name, s, st, t, date)
            except Exception as e:  # noqa: BLE001 — journal, never die
                st["stage"] = "error"
                st["error"] = str(e)
                self.engine.journal("timer_error", strategy=name, error=str(e))
                continue
            if fire is not None:
                fires.append((name, st, asyncio.ensure_future(fire)))
        return fires

    async def _settle(self, fires) -> None:
        """Wait for every launched fire; one that raised is its strategy's error."""
        results = await asyncio.gather(*(f for _, _, f in fires),
                                       return_exceptions=True)
        for (name, st, _), r in zip(fires, results):
            if isinstance(r, Exception):
                st["stage"] = "error"
                st["error"] = str(r)
                self.engine.journal("timer_error", strategy=name, error=str(r))

    async def _advance(self, name, s, st, t, date):
        """Move one strategy along its stages; at 9:30 return its fire
        (a coroutine) for tick() to launch -- with no await on the way when
        the strategy was already staged."""
        # HARD upper bound. Without it every stage test is "t >= <time>",
        # which is true at 11pm too: a restart any time after 9:30 would
        # stage and fire immediately on a stale anchor. (The engine's accept
        # window catches it, but the timer must not try in the first place.)
        # Inside the window a fire past FIRE_LATE_MAX_S still goes out: late,
        # on the latest trade.
        end = _hhmm(s.accept_until_et)
        if t > end:
            if st["stage"] in ("idle", "gated", "staged", "waiting"):
                self._closed(name, s, st, date)
            if not self._quote_needed(s.symbol, name):
                sub = self._subs.pop(s.symbol, None)
                if sub is not None and self._md is not None:
                    await self._md.unsubscribe_quote(sub)
            return

        if st["stage"] in ("idle", "gated", "staged", "waiting") and self.engine.killed_today(name):
            st.update(stage="skipped", killed=True)       # the per-strategy Kill: never fire today
            self.engine.journal("timer_skipped", strategy=name, reason="killed")
        stage = st["stage"]
        if stage in ("fired", "skipped", "done", "error", "missed"):
            if stage == "error" and t < STAGE_T:
                st["stage"] = "idle"        # errors before staging retry
            elif t >= DONE_T and s.symbol in self._subs \
                    and not self._quote_needed(s.symbol, name):
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
            st.update(stage="staged", staged_at=_et_ms(self._now().timestamp()))

        if st["stage"] in ("staged", "waiting") and t >= FIRE_T:
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
            if st["stage"] == "staged" and self._up_at is not None and self._up_at > fire_at:
                e = self._decided(date).get(name)        # the desk came up after the open:
                if e is not None and e["event"] == "timer_fired":   # did its earlier run fire?
                    st.update(stage="fired", **{k: e[k] for k in FIRED_KEYS if k in e})
                    return                  # once a day, restarts or not (dry runs too)
            now = self._now()
            now_ts = now.timestamp()
            late_s = now_ts - fire_at.timestamp()
            late = late_s > FIRE_LATE_MAX_S
            sub = self._subs.get(s.symbol)
            # On time: the last trade received before 09:30:00.000, the research
            # anchor. Late -- or on time with no fresh pre-open trade -- the
            # accept window still open: the latest trade now; both stops sit
            # offset_pts either side of the current price, so nothing is placed
            # through the market. Freshness is judged on the timer's own clock
            # (the wall clock the pushes are received on). No fresh trade at
            # all: wait for one, every tick -- never final (_wait).
            got, source = (None if late else self._fresh(sub, fire_at.timestamp(), now_ts)), "pre_open"
            if got is None:
                got, source = self._fresh(sub, None, now_ts), "current"
            if got is None:
                return self._wait(name, st, sub, now_ts, late, late_s, fire_at)
            waited = st["stage"] == "waiting"
            if source == "pre_open":
                reason = None
            elif waited:                    # late before the wait: that; on time: the wait
                reason = st.get("wait_why") or "waited_for_quote"
            else:
                reason = self._late_why(st, fire_at) if late else "no_pre_open_quote"
            info = {"late": late, "late_s": round(late_s, 3),
                    **({"reason": reason} if reason else {}),
                    "anchor_source": source,
                    **({"waited_s": round(late_s - st["wait_late_s"], 3),
                        "wait_reason": st.get("wait_reason")} if waited else {}),
                    **self._stamps(sub, fire_at.timestamp() if source == "pre_open" else None)}
            st.update(anchor=got[0], stage="fired",       # a late or off-anchor one shows loud
                      **{k: info[k] for k in FIRED_KEYS if k in info})
            return self._fire(name, s, got[0], info)   # tick() fires all due at once

    def _fresh(self, sub, before, now_ts):
        """(price, received) of the latest trade received before `before` (None:
        the latest of all) -- or None: there is none, or it is older than
        QUOTE_MAX_AGE_S."""
        px, seen = self._md.last(sub, before=before) if self._md is not None else (None, 0.0)
        return (px, seen) if px is not None and now_ts - seen <= QUOTE_MAX_AGE_S else None

    def _wait(self, name, st, sub, now_ts, late, late_s, fire_at) -> None:
        """No fresh trade to anchor on yet -- never final: the account holder
        would rather it fire. It tries again every tick, and fires on the
        first fresh trade (anchor_source current), until the accept window
        closes (_closed: missed, no_fresh_quote). One timer_waiting line when
        the wait starts, with why and the push count -- never one a tick; the
        status says "waiting" and why, kept current as the cause changes."""
        cause, text, told = self._no_anchor(sub, now_ts)
        if st["stage"] == "waiting":
            if cause != st.get("wait_reason"):
                st.update(wait_reason=cause, wait_text=text)
            return
        why = self._late_why(st, fire_at) if late else None   # late already: that is why
        st.update(stage="waiting", wait_reason=cause, wait_text=text,
                  wait_late_s=round(late_s, 3), wait_why=why)
        try:
            self.engine.journal("timer_waiting", strategy=name, reason=cause, text=text, **told,
                                late=late, late_s=round(late_s, 3),
                                **({"late_reason": why} if why else {}),
                                **self._stamps(sub, None if late else fire_at.timestamp()))
        except Exception as e:  # noqa: BLE001 — a failed line never ends the wait
            print(f"homebase timer: journal timer_waiting for {name} failed: {e!r}", file=sys.stderr)

    def _no_anchor(self, sub, now_ts) -> tuple[str, str, dict]:
        """Why there is no fresh trade to anchor on, told apart -> (cause, text,
        journal fields), with the contract's quote push count: no_pushes (none
        at all), no_trade (pushes, none with a trade), stale_trade (the newest
        trade is older than QUOTE_MAX_AGE_S: its age). A dead md socket is said.
        Never raises: the wait stands, only what it knows shrinks."""
        md = self._md
        try:
            n = int(md.pushes(sub)) if md is not None else 0
        except Exception:  # noqa: BLE001
            n = None
        try:
            px, seen = md.last(sub) if md is not None else (None, 0.0)
        except Exception:  # noqa: BLE001
            px, seen = None, 0.0
        down = "" if md is not None and getattr(md, "connected", False) \
            else " (market data disconnected)"
        of = f"{'?' if n is None else n} quote push{'' if n == 1 else 'es'}"
        if px is None and n == 0:
            return "no_pushes", f"no quote pushes at all for {sub}{down}", {"pushes": 0}
        if px is None:
            return "no_trade", f"none of {of} for {sub} had a trade{down}", {"pushes": n}
        age = round(now_ts - seen, 1)
        return ("stale_trade", f"newest trade is {age} s old ({of}, {sub}){down}",
                {"pushes": n, "age_s": age})

    def _quote_needed(self, symbol, but) -> bool:
        """Another strategy on this symbol is staged or waiting for a quote: its
        feed must not be unsubscribed from under it."""
        return any(n != but and st.get("stage") in ("staged", "waiting")
                   and getattr(self.cfg.strategies.get(n), "symbol", None) == symbol
                   for day in self.days.values() for n, st in day.items())

    def _late_why(self, st, fire_at) -> str:
        """Why a fire is past FIRE_LATE_MAX_S. late_fire: staged before the
        open, the fire's own tick ran late (a stalled loop, a sleeping
        machine). late_stage: seen by the open, staged only after it (a slow
        gate or stage, a gate retry). late_start: this timer -- the desk --
        came up after the open. late_switch_on: the desk was up, but the
        strategy was first seen after the open (switched on then)."""
        at_open = _et_ms(fire_at.timestamp())       # "09:30:00.000": the same day's
        staged, seen = st.get("staged_at"), st.get("seen_at")   # ET times compare as text
        if staged is not None and staged < at_open:
            return "late_fire"
        if seen is not None and seen <= at_open:
            return "late_stage"
        return ("late_switch_on" if self._up_at is not None and self._up_at <= fire_at
                else "late_start")

    def _closed(self, name, s, st, date) -> None:
        """The accept window closed on a strategy this timer never fired,
        skipped or deferred today. A day that acted is done, a killed one
        skipped; after a restart, what the desk's earlier run decided (today's
        journal) stands, unsaid again. Only a day nothing decided is MISSED --
        with why (no_fresh_quote: it waited for a quote to the end;
        late_start: the desk came up after the window; late_switch_on: first
        seen after it; window_closed: known in time, never fired: a stall, a
        gate retry) -- journaled once per strategy per day."""
        if self.engine.day_status(name) != "idle":
            st["stage"] = "done"
            return
        if self.engine.killed_today(name):
            st.update(stage="skipped", killed=True)
            return
        waited = st["stage"] == "waiting"        # this run tried: its wait is the day
        e = None if waited else self._decided(date).get(name)
        if e is not None:
            st.update(stage=DECIDED[e["event"]],
                      **{k: e[k] for k in FIRED_KEYS + ("error", "adx") if k in e})
            if e.get("reason") == "gate_chop":
                st["gate"] = False
            elif e.get("reason") == "killed":
                st["killed"] = True
            return
        now = self._now()
        day = dt.date.fromisoformat(date)
        fire_at = dt.datetime.combine(day, FIRE_T, tzinfo=ET)
        end_at = dt.datetime.combine(day, _hhmm(s.accept_until_et), tzinfo=ET)
        seen = st.get("seen_at")
        reason = ("no_fresh_quote" if waited else
                  "late_start" if self._up_at is None or self._up_at > end_at else
                  "late_switch_on" if seen is not None and seen > _et_ms(end_at.timestamp()) else
                  "window_closed")
        late_s = round(now.timestamp() - fire_at.timestamp(), 3)
        wait = ({"wait_reason": st.get("wait_reason"), "text": st.get("wait_text"),
                 "waited_s": round(late_s - st.get("wait_late_s", 0.0), 3)} if waited else {})
        st.update(stage="missed", reason=reason, late_s=late_s)
        self.engine.journal("timer_missed", strategy=name, reason=reason,
                            at=_et_ms(now.timestamp()), late_s=late_s,
                            window_end=s.accept_until_et, **wait)

    def _decided(self, date: str) -> dict:
        """strategy -> today's timer outcome in the journal: its fire if it
        fired (a fire stands, whatever a later restart logged), else its last
        outcome (skipped, error, deferred, missed). Read once per date, and
        only after an accept window closed or at the first fire attempt of a
        desk that came up after the open -- never on an on-time fire. A
        prestage's account-level skip decides nothing. An unreadable journal
        decides nothing either, and never raises into the timer."""
        if self._decided_day[0] != date:
            out: dict = {}
            try:
                p = self.engine.journal_path
                for line in (p.read_text(errors="replace").splitlines() if p.exists() else ()):
                    if '"timer_' not in line:
                        continue
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(e, dict) and e.get("event") in DECIDED and e.get("strategy") \
                            and str(e.get("et", "")).startswith(date) \
                            and not (e["event"] == "timer_skipped" and e.get("account")):
                        prior = out.get(str(e["strategy"]))
                        if prior is None or prior["event"] != "timer_fired":
                            out[str(e["strategy"])] = e
            except Exception as ex:  # noqa: BLE001 — a missed day is said, never a crash
                print(f"homebase timer: reading today's journal failed: {ex!r}", file=sys.stderr)
            self._decided_day = (date, out)
        return self._decided_day[1]

    def _stamps(self, sub, cut) -> dict:
        """The anchor's push (the one last(sub, before=cut) answers from) and the
        newest push at this moment, as journal fields (_push_fields). Journal
        only: never raises into the fire."""
        try:
            anchor, newest = self._md.trade_push(sub, cut), self._md.trade_push(sub)
        except Exception:  # noqa: BLE001 — diagnostics never touch the fire
            anchor = newest = None
        return {**_push_fields("anchor", anchor), **_push_fields("newest", newest)}

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

    async def _fire(self, name, s, px, info) -> None:
        out = await self.engine.handle_alert(
            {"strategy": name, "upper": px + s.offset_pts,
             "lower": px - s.offset_pts}, source="timer")
        self.engine.journal("timer_fired", strategy=name, anchor=px,
                            result=out.get("ok"),
                            note=out.get("reason") or out.get("note"), **info)

    def _sleep_s(self) -> float:
        """One tick — except when a strategy is staged and 9:30:00 is closer
        than that: then exactly the time left, so the fire lands on
        9:30:00.000 instead of up to a tick late: on time, anchored on the
        last trade received before 09:30:00.000 as in the research (see
        FIRE_LATE_MAX_S)."""
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
