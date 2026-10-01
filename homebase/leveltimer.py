"""Level timer: fires the "levels" strategies (config kind "levels") at THEIR OWN clock time.

The 9:30 SelfTimer (timer.py) is hard-wired to 09:30:00 and a daily-bar gate.  The NQ prop strategies fire at
09:30:00 (nyam straddle), 11:05:00 (ORB) and 13:30:00 (pm straddle) from a geometry that is new every day
(ATR of N-minute bars since 00:00 ET, an opening range), so they have their own timer and leave the 9:30 bot's
path untouched.  Per strategy, all times ET, weekdays only:

    fire - (bar + 5 min)  stage    subscribe the quote; prints are turned into minute bars (atrbars.TickBars)
    + 3 min               history  the broker's 1-minute chart history since 00:00 ET (exact bars); the live
                                   prints cover everything after it -- no hole (TickBars.coverage)
    fire_et               fire     geometry = compute_geometry(...): anchor = the LAST print stamped before the
                                   fire, ATR from the closed bars of the day; engine.handle_levels places one OCO
                                   pair per booked account with that account's own size and take
    fire + 2 min          audit    the exact bars again: the ATR the fire used vs the one the exact bars give

Fail-safe by construction (same spirit as the 9:30 timer): no coverage, no ATR, no fresh print, a leg already
through the price, a roll between the stage and the fire, an early-close day, a strategy killed today, a day that
already acted -> NO fire, journaled with why.  A fire never repeats (once a day, restarts included: the journal
is read).  After the accept window closes an unfired strategy is MISSED, journaled.  No market-data request is
made 09:20-09:35 ET (the 9:30 window): the history is read before it.

The price watcher: while a "levels" trade is open the quote stays subscribed and every tick the engine's
check_takes(prices) is run -- the day_take backstop to the broker-side take limit.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import sys
from typing import Callable
from zoneinfo import ZoneInfo

from . import symbols
from .atrbars import MIN_MS, TickBars
from .config import AppCfg, assignments
from .contracts import tick_size
from .engine import Engine, _hhmm
from .levels import SHAPES, compute_geometry, is_early_close_skip
from .timer import _orders_in, _positions_in

ET = ZoneInfo("America/New_York")
QUIET = (dt.time(9, 20), dt.time(9, 35))     # weekdays: no market-data request
TICK_S = 0.2
STAGE_LEAD_EXTRA_MIN = 5       # the quote is subscribed this long before the last bar the ATR needs begins
HISTORY_AFTER_S = 180          # history is read this long after the subscription (it closes the partial minute)
HISTORY_RETRY_S = 60.0
MD_RETRY_S = 15.0              # a dead / refused market-data socket is rebuilt at most this often
ERROR_JOURNAL_S = 30.0         # the same failure is journaled at most this often (it is retried every tick)
AUDIT_AFTER_S = 120.0
LATE_MAX_S = 1.0               # a fire within this of the fire time is ON TIME (anchored before it)
PRE_FIRE_MAX_AGE_S = 5.0       # the newest print must be this fresh at an on-time fire
CURRENT_MAX_AGE_S = 1.5        # ... and at a late one
PRICE_MAX_AGE_S = 5.0          # a take-watcher price older than this is unknown (no decision)
STAMP_SKEW_S = 5.0             # a push's own stamp is used for its minute only within this of its receive time


def in_quiet(now: dt.datetime) -> bool:
    return now.weekday() < 5 and QUIET[0] <= now.time() < QUIET[1]


def _t(s: str) -> dt.time:
    return dt.time.fromisoformat(s if s.count(":") == 2 else s + ":00")


def lead_min(cfg) -> int:
    """Minutes before the fire at which the stage starts: the last bar the geometry needs (the ATR bar, or
    the opening range) plus a margin."""
    bar = int(cfg.atr_tf) if cfg.shape == "atr_straddle" else max(int(cfg.atr_tf), int(cfg.or_min))
    return bar + STAGE_LEAD_EXTRA_MIN


class LevelTimer:
    def __init__(self, cfg: AppCfg, engine: Engine, md_factory: Callable,
                 now_fn: Callable[[], dt.datetime] | None = None):
        self.cfg = cfg
        self.engine = engine
        self._md_factory = md_factory
        self._now = now_fn or (lambda: dt.datetime.now(dt.timezone.utc))
        self._md = None
        self._subs: dict[str, str] = {}              # strategy symbol -> subscribed contract
        self._bars: dict[str, TickBars] = {}         # strategy symbol -> today's bars
        self._by_contract: dict[str, TickBars] = {}
        self._hist: dict[str, dict] = {}             # symbol -> {"ok", "at" (retry clock), "error"}
        self._md_retry_at = float("-inf")
        self._drop: list[str] = []                   # yesterday's quote subscriptions, released outside the quiet window
        self._err_at: dict[str, float] = {}
        self.days: dict = {}
        self._decided_day: tuple = (None, {})

    # ------------------------------------------------------------------ plumbing
    def now_et(self) -> dt.datetime:
        return self._now().astimezone(ET)

    def _day(self, date: str) -> dict:
        if date not in self.days:
            self.days.clear()
            self.days[date] = {}
            self._drop.extend(self._subs.values())      # a new day starts with new bars: subscribe again
            self._subs.clear()
            self._bars.clear()
            self._by_contract.clear()
            self._hist.clear()
        return self.days[date]

    def status(self) -> dict:
        date = self.now_et().date().isoformat()
        return {"date": date, "strategies": self._day(date)}

    def _strategies(self):
        return [(n, s) for n, s in self.cfg.strategies.items()
                if s.enabled and getattr(s, "kind", "") == "levels" and getattr(s, "self_fire", False)
                and s.shape in SHAPES]

    def _journal(self, event: str, **kw) -> None:
        try:
            self.engine.journal(event, **kw)
        except Exception as e:  # noqa: BLE001 — a failing journal never changes a decision
            print(f"homebase leveltimer: journal {event} failed: {e!r}", file=sys.stderr)

    def _inactive(self, name: str, code: str, why: str) -> None:
        """Say once that a booked strategy will not trade today (inactive.py); never changes a decision."""
        try:
            if assignments(self.cfg, name):
                self.engine.note_inactive(name, code, why, source="leveltimer")
        except Exception as e:  # noqa: BLE001
            print(f"homebase leveltimer: inactive {name} failed: {e!r}", file=sys.stderr)

    def _on_trade(self, contract, px, size, seen, stamp) -> None:
        bars = self._by_contract.get(contract)
        if bars is None:
            return
        ts = stamp if stamp is not None and abs(stamp - seen) <= STAMP_SKEW_S else seen
        bars.add_tick(int(ts * 1000), float(px), float(size or 0))

    async def _ensure_md(self, now: dt.datetime):
        """The md socket, (re)built when there is none or it died; a new socket has no subscriptions, so
        every symbol staged today is subscribed again and its live coverage restarts at that moment
        (prints missed while it was down are a hole the history read must close, or the day is skipped).
        A rebuild that fails half way leaves NO socket (the next try starts clean).  Always on an md token a
        connected login already holds (allow_login=False): a password login from here could cost the 9:30 fire
        its own."""
        if self._md is not None and self._md.connected:
            return self._md
        md = self._md_factory()
        await md.connect(allow_login=False)      # never the password login: Tradovate logins are scarce
        if hasattr(md, "trade_hooks") and self._on_trade not in md.trade_hooks:
            md.trade_hooks.append(self._on_trade)
        old = dict(self._subs)
        self._md = md
        self._subs.clear()
        self._by_contract.clear()
        try:
            for sym in old:
                await self._subscribe(sym, now)
                self._hist[sym] = {"ok": False, "at": 0.0}      # read the history again: it closes the hole
        except Exception:
            self._md = None
            raise
        return md

    async def _keep_md(self, now: dt.datetime) -> bool:
        """The socket is up (rebuilt now if it is not; at most every MD_RETRY_S, never by the password login in
        the quiet window).  A failure is journaled and tried again -- it never ends the day by itself."""
        if self._md is not None and self._md.connected:
            return True
        t = self._now().timestamp()
        if t - self._md_retry_at < MD_RETRY_S:
            return False
        self._md_retry_at = t
        try:
            await self._ensure_md(now)
            return True
        except Exception as e:  # noqa: BLE001
            self._journal("level_md_error", error=str(e)[:200])
            return False

    async def _subscribe(self, symbol: str, now: dt.datetime) -> None:
        contract = await self._md.subscribe_quote(symbol)
        self._subs[symbol] = contract
        bars = self._bars.get(symbol)
        if bars is None:
            bars = self._bars[symbol] = TickBars(now.date())
        bars.start_live(int(self._now().timestamp() * 1000), reset=True)
        self._by_contract[contract] = bars

    async def _load_history(self, symbol: str, now: dt.datetime) -> bool:
        """The broker's 1-minute bars since 00:00 ET; only bars already finished.  False = could not."""
        bars = self._bars[symbol]
        n = int((self._now().timestamp() * 1000 - bars.t0) // MIN_MS) + 6
        got = await self._md.minute_bars(symbol, n)
        now_ms = int(self._now().timestamp() * 1000)
        k = 0
        for b in got:
            if b["start_ms"] + MIN_MS <= now_ms:
                bars.add_minute(b["start_ms"], b["o"], b["h"], b["l"], b["c"], b.get("v", 0))
                k += 1
        self._journal("level_history", symbol=symbol, bars=k, first=bars.hist_start, end=bars.hist_end)
        return k > 0

    # ------------------------------------------------------------------ the loop
    async def tick(self) -> None:
        now = self.now_et()
        if now.weekday() >= 5:
            return
        date = now.date().isoformat()
        day = self._day(date)
        mine = []
        for name, s in self._strategies():
            st = day.get(name)
            if st is None:
                st = day[name] = {"stage": "idle", "fire_at": s.fire_et, "seen_at": now.strftime("%H:%M:%S")}
            mine.append((name, s, st))
        await self._release_old(now)
        await self._resubscribe_for_open_trades(now)
        for name, s, st in mine:
            try:
                await self._advance(name, s, st, now, date)
            except Exception as e:  # noqa: BLE001 — journal, never die; the stage stands and is tried again
                # (nothing that could place twice is retried: a day that acted reads "done", see _advance)
                st["error"] = str(e)[:200]
                t = self._now().timestamp()
                if t - self._err_at.get(name, float("-inf")) >= ERROR_JOURNAL_S:
                    self._err_at[name] = t
                    self._journal("level_error", strategy=name, error=st["error"])
        await self._watch(now)

    async def _resubscribe_for_open_trades(self, now: dt.datetime) -> None:
        """A desk restarted mid-trade (or one whose strategy is already done for the day) still has a
        position / resting entries out: its day_take watcher needs a price, so the quote is subscribed again."""
        today = now.date().isoformat()
        need = sorted({cfg.symbol for st in self.engine.states.values()
                       for cfg in [self.cfg.strategies.get(st.strategy)]
                       if cfg is not None and cfg.kind == "levels" and st.date == today
                       and st.status in ("placed", "live") and cfg.symbol not in self._subs})
        if need and await self._keep_md(now):
            for sym in need:
                if sym not in self._subs:
                    await self._subscribe(sym, now)
                    self._journal("level_watch_resubscribed", symbol=sym)

    async def _release_old(self, now: dt.datetime) -> None:
        if self._drop and self._md is not None and self._md.connected and not in_quiet(now):
            for sub in self._drop:
                try:
                    await self._md.unsubscribe_quote(sub)
                except Exception:  # noqa: BLE001
                    pass
            self._drop.clear()

    async def _advance(self, name, s, st, now, date) -> None:
        d = dt.date.fromisoformat(date)
        fire_at = dt.datetime.combine(d, _t(s.fire_et), tzinfo=ET)
        stage_at = fire_at - dt.timedelta(minutes=lead_min(s))
        end_at = dt.datetime.combine(d, _hhmm(s.accept_until_et), tzinfo=ET)
        if st["stage"] in ("fired", "skipped", "missed", "done", "error"):
            if st["stage"] == "fired" and not st.get("audited"):
                await self._audit(name, s, st, now, fire_at)
            return
        if self.engine.killed_today(name):
            st.update(stage="skipped", reason="killed")
            self._journal("level_skipped", strategy=name, reason="killed")
            return
        if now < stage_at:
            return
        if now > end_at:
            await self._closed(name, s, st, d, now, fire_at)
            return
        if self.engine.day_status(name) != "idle":
            st["stage"] = "done"
            self._journal("level_deferred", strategy=name, status=self.engine.day_status(name))
            return
        if s.skip_early_close and is_early_close_skip(s.symbol, d, s.flat_et):
            st.update(stage="skipped", reason="early_close")
            self._journal("level_skipped", strategy=name, reason="early_close", date=date)
            self._inactive(name, "early_close", f"half day: the market closes before its {s.flat_et} flat")
            return
        if st["stage"] == "idle":                          # stage: subscribe, start the bars
            if await self._decided_earlier(name, date):    # a restart: once a day
                st["stage"] = "done"
                return
            self._bars.setdefault(s.symbol, TickBars(d))
            if not await self._keep_md(now):
                return
            if s.symbol not in self._subs:
                await self._subscribe(s.symbol, now)
                self._hist[s.symbol] = {"ok": False, "at": 0.0}
            st.update(stage="live", staged_at=now.strftime("%H:%M:%S"))
            self._journal("level_staged", strategy=name, contract=self._subs[s.symbol], fire=s.fire_et)
        if st["stage"] in ("live", "waiting"):
            await self._keep_md(now)                      # a socket that died after the stage is rebuilt
            await self._history(s.symbol, now, stage_at)
            if now >= fire_at:
                await self._fire(name, s, st, now, fire_at)

    async def _history(self, symbol: str, now: dt.datetime, stage_at: dt.datetime) -> None:
        h = self._hist.setdefault(symbol, {"ok": False, "at": 0.0})
        if in_quiet(now) or now < stage_at + dt.timedelta(seconds=HISTORY_AFTER_S):
            return
        bars = self._bars.get(symbol)
        if h["ok"] and bars is not None and bars.coverage(int(self._now().timestamp() * 1000))[0]:
            return                                      # read, and nothing has opened a hole since
        t = self._now().timestamp()
        if t - h["at"] < HISTORY_RETRY_S:
            return
        h["at"] = t
        try:
            if not await self._keep_md(now):
                return
            loaded = await self._load_history(symbol, now)
            # ok only when history + live prints leave no hole up to now: a desk that came up mid-minute
            # reads again a minute later, when the partial minute has closed
            h["ok"] = loaded and self._bars[symbol].coverage(int(self._now().timestamp() * 1000))[0]
            h.pop("error", None)
        except Exception as e:  # noqa: BLE001 — retried; the fire refuses without coverage
            h["error"] = str(e)[:200]
            self._journal("level_history_error", symbol=symbol, error=h["error"])

    def _fresh_ok(self, bars: TickBars, fire_ms: int, now_ms: int, late: bool) -> bool:
        """On time: a print stamped within PRE_FIRE_MAX_AGE_S BEFORE the fire (the anchor; NQ prints many
        times a second, so an older last print means a dead feed).  Late: a print within
        CURRENT_MAX_AGE_S of now."""
        if late:
            return bars.last_tick_ms is not None and (now_ms - bars.last_tick_ms) / 1000.0 <= CURRENT_MAX_AGE_S
        got = bars.last_print_before(fire_ms)
        return got is not None and (fire_ms - got[0]) / 1000.0 <= PRE_FIRE_MAX_AGE_S

    async def _fire(self, name, s, st, now, fire_at) -> None:
        bars = self._bars.get(s.symbol)
        fire_ms = int(fire_at.timestamp() * 1000)
        now_ms = int(self._now().timestamp() * 1000)
        late_s = (now_ms - fire_ms) / 1000.0
        late = late_s > LATE_MAX_S
        wait = None
        if bars is None:
            wait = "no bars"
        else:
            ok, why = bars.coverage(fire_ms)
            if not ok:
                wait = f"no coverage: {why}"
            elif not self._fresh_ok(bars, fire_ms, now_ms, late):
                wait = "no fresh print"
        if wait is not None:                               # never final: tried again each tick until the window closes
            if st["stage"] != "waiting" or st.get("wait") != wait:
                st.update(stage="waiting", wait=wait)
                self._journal("level_waiting", strategy=name, reason=wait, late_s=round(late_s, 3))
            return
        contract = self._subs.get(s.symbol)
        if contract is None or symbols.resolve_contract(s.symbol) != contract:
            st.update(stage="skipped", reason="contract_changed")
            self._journal("level_skipped", strategy=name, reason="contract_changed",
                          staged=contract, front=symbols.resolve_contract(s.symbol))
            self._inactive(name, "contract_changed", "the front contract rolled between the stage and the fire")
            return
        tick = tick_size(s.symbol) or 0.25
        geo, why = compute_geometry(s, bars, fire_ms, tick, last_ms=now_ms + 1 if late else None)
        if geo is None:
            st.update(stage="skipped", reason=why)
            self._journal("level_skipped", strategy=name, reason=why)
            self._inactive(name, "no_geometry", why)
            return
        self._manual_skips(name, s)
        info = {"late": late, "late_s": round(late_s, 3), "contract": contract,
                "fire_et": s.fire_et, "ticks": bars.ticks, "coverage": bars.coverage(fire_ms)[1],
                "live_from": bars.live_from, "hist_end": bars.hist_end}
        res = await self.engine.handle_levels(name, geo, source="leveltimer", info=info)
        st.update(stage="fired", late=late, late_s=round(late_s, 3), geometry=geo.to_dict(),
                  fired_at=now.strftime("%H:%M:%S"), result=res.get("ok"),
                  note=res.get("reason") or res.get("note"))
        self._journal("level_fired", strategy=name, result=res.get("ok"),
                      note=res.get("reason") or res.get("note"), geometry=geo.to_dict(), **info)

    def _own_orders(self, aid) -> set:
        return {str(i) for st in self.engine.day_states_for_account(aid)
                for i in (st.upper_id, st.lower_id, st.up_sl_id, st.up_tp_id,
                          st.dn_sl_id, st.dn_tp_id) if i}

    def _manual_skips(self, name, s) -> None:
        """A booked account that holds a position or a working order in the bot's symbol that the desk did
        not place is skipped for the day (the 9:30 prestage's rule, from the adapters' cached view: no
        broker call at the fire); a view not yet synced is unknown, never flat."""
        sym, skipped = s.symbol.upper(), self.engine.skipped_today(name)
        for a in assignments(self.cfg, name):
            aid = a["account"]
            if aid in skipped:
                continue
            ad = self.engine.adapters.get(aid)
            if ad is None or not ad.connected:
                continue                                   # the engine says place_failed
            try:
                view = ad.trade_view()
            except Exception as e:  # noqa: BLE001
                view = None
                self._journal("level_check_failed", strategy=name, account=aid, error=str(e)[:120])
            if view is None:
                continue
            if view.get("seeded") is not True:
                self.engine.skip_today(name, aid)
                self._journal("timer_skipped", strategy=name, reason="view_unsynced", account=aid)
                continue
            mine = [o for o in _orders_in(view, sym)[0] if o not in self._own_orders(aid)]
            net = _positions_in(view, sym)[0]
            if net or mine:
                self.engine.skip_today(name, aid)
                self._journal("timer_skipped", strategy=name, account=aid, net=int(net or 0), orders=mine,
                              reason="manual_position" if net else "manual_order")

    async def _closed(self, name, s, st, d, now, fire_at) -> None:
        """The accept window closed on a strategy this timer never fired: MISSED, with why."""
        if self.engine.day_status(name) != "idle":
            st["stage"] = "done"
            return
        if await self._decided_earlier(name, d.isoformat()):
            st["stage"] = "done"
            return
        reason = st.get("wait") or ("the desk started after the window" if st["stage"] == "idle"
                                    else "the window closed before it could fire")
        st.update(stage="missed", reason=reason)
        self._journal("level_missed", strategy=name, reason=reason, window_end=s.accept_until_et)
        self._inactive(name, "missed", reason)

    async def _decided_earlier(self, name: str, date: str) -> bool:
        """Once a day, restarts included: did an earlier run of this desk already fire / skip this strategy
        today?  (today's journal)"""
        if self._decided_day[0] != date:
            self._decided_day = (date, await asyncio.to_thread(self._read_decided, date))
        return name in self._decided_day[1]

    def _read_decided(self, date: str) -> set:
        out: set = set()
        try:
            p = self.engine.journal_path
            for line in (p.read_text(errors="replace").splitlines() if p.exists() else ()):
                if '"level_' not in line:
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if isinstance(e, dict) and e.get("event") in ("level_fired", "level_skipped") \
                        and e.get("strategy") and str(e.get("et", "")).startswith(date):
                    out.add(str(e["strategy"]))
        except Exception as ex:  # noqa: BLE001
            print(f"homebase leveltimer: reading today's journal failed: {ex!r}", file=sys.stderr)
        return out

    # ------------------------------------------------------------------ audit + price watcher
    async def _audit(self, name, s, st, now, fire_at) -> None:
        """ATR parity, once, after the fire: the exact 1-minute bars vs the ATR the fire used (built from
        prints plus the history read before the open).  Journal only; never a decision."""
        if (now - fire_at).total_seconds() < AUDIT_AFTER_S or in_quiet(now):
            return
        st["audited"] = True
        bars = self._bars.get(s.symbol)
        if bars is None or self._md is None or not self._md.connected:
            return
        used = (st.get("geometry") or {}).get("atr")
        try:
            before = len(bars.parity)
            await self._load_history(s.symbol, now)
            atr, n = bars.atr(int(s.atr_tf), int(fire_at.timestamp() * 1000))
            self._journal("level_atr_parity", strategy=name, used=used, exact=atr, bars=n,
                          differs=(used is not None and atr is not None and abs(used - atr) > 1e-6),
                          minutes_corrected=len(bars.parity) - before)
        except Exception as e:  # noqa: BLE001
            self._journal("level_atr_parity", strategy=name, used=used, error=str(e)[:200])

    def _needed(self, symbol: str) -> bool:
        """Keep the quote while a levels strategy of this symbol is yet to fire or has a position/order out."""
        today = self.now_et().date().isoformat()
        for n, s in self._strategies():
            if s.symbol == symbol and (self.days.get(today, {}).get(n) or {}).get("stage") in (
                    "idle", "live", "waiting"):
                return True
        for st in self.engine.states.values():
            cfg = self.cfg.strategies.get(st.strategy)
            if st.date == today and cfg is not None and cfg.kind == "levels" and cfg.symbol == symbol \
                    and st.status in ("placed", "live"):
                return True
        return False

    async def _watch(self, now: dt.datetime) -> None:
        """The day_take backstop: latest prints -> engine.check_takes; and let go of a quote nobody needs."""
        if self._md is None or not self._subs:
            return
        prices = {}
        for symbol, contract in list(self._subs.items()):
            try:
                px, seen = self._md.last(contract)
            except Exception:  # noqa: BLE001
                continue
            if px is not None and self._now().timestamp() - seen <= PRICE_MAX_AGE_S:
                prices[symbol] = px
            if not self._needed(symbol) and not in_quiet(now):
                sub = self._subs.pop(symbol, None)
                self._by_contract.pop(contract, None)
                if sub is not None:
                    await self._md.unsubscribe_quote(sub)
        if prices:
            await self.engine.check_takes(prices)

    async def loop(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception as e:  # noqa: BLE001
                self._journal("level_loop_error", error=str(e)[:200])
            await asyncio.sleep(TICK_S)
