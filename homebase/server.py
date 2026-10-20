"""The homebase server: signals in, the book out.

    GET  /                   dashboard
    GET  /api/status         everything the dashboard renders
    GET  /api/journal        journal events for a day, filterable, newest first
    POST /api/arm            {"armed": true|false} — the master switch
    POST /api/kill           cancel + flatten EVERY account + disarm
    POST /api/test-alert     synthetic dry-run signal; REFUSED while armed
    POST /api/connect        validate a login (demo or live), return its accounts
    POST /api/accounts/add   add one broker account to the pool
    POST /api/book           set a strategy's account assignments
    GET  /api/logins (+delete), GET /api/calendar

The routes live in homebase/routes/ (one module per concern); create_app builds the desk and registers them.

Binds to localhost only. The TradingView webhook (/hook, its hook-only port 8851 and the
Cloudflare tunnel in front of it) was REMOVED 2026-09-27 at the user's request -- signals come
from the desk's own 9:30 timer.
Runs fine with zero accounts: everything reports its own state loudly and
the engine still validates + journals (dry run).
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import json
import math
import os
import sys
from dataclasses import asdict
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import bothistory, equity
from . import config as config_mod
from . import secrets_store
from .broker.base import AccountNotOnLogin, BrokerAdapter, OrderRequest
from .broker.login_budget import LoginBudget, LoginDeferred, is_rate_limited
from .broker.paper import BASE_URL as PAPER_URL, PaperAdapter
from .broker.tradovate import RENEW_EARLY_FROM, RENEW_EARLY_UNTIL, TradovateAdapter
from .engine import Engine, _hhmm
from .feed import MarketFeed
from .marketdata import TradovateMD
from .rules import RULES
from .metrics import live_metrics, strategy_live_detail
from .paths import state_dir
from .leveltimer import LevelTimer
from .timer import SelfTimer, fire_clock, fire_said, fire_time, miss_why, off_anchor, schedule
from . import desk_api, routes
from . import inactive as inactive_mod
from . import labdesk as labdesk_mod
from .trading import ChartDesk

STATIC = Path(__file__).resolve().parent / "static"
CLOCK_INTERVAL_S = 1       # also paces the sibling-cancel backstop (cache reads)
SIBLING_INTERVAL_S = 0.25  # engine.sibling_tick: the close watch on the other entry after a fill
RECONNECT_INTERVAL_S = 5   # cheap now: reconnects reuse the token
GONE_CONFIRM_S = 300       # an account missing from its login is removed only when a 2nd
                           # successful sync at least this much later still misses it
GONE_CHECK_TIMEOUT_S = 30  # a confirming re-sync runs in its own task, at most this long
NOTICES_KEPT = 10
ADD_MANY_MAX = 60           # accounts in one "add several" (a prop firm hands out ~20)
INPLACE_RETRY_S = (10, 60)   # a dropped socket whose token is still valid, while its user's
                             # logins are paused: retry in place 10 s, doubling to 60 s
EQUITY_INTERVAL_S = 60
JOURNAL_TAIL = 60
READINESS_FROM = (9, 25)
FEED_FROM = (8, 55)        # the price feed runs through the RTH day, weekdays
FEED_UNTIL = (16, 10)
FEED_RETRY_S = 30


def _equity_path() -> Path:
    return state_dir() / "equity.jsonl"


_POWER_CACHE: dict = {"ts": 0.0, "out": None}


def power_status() -> dict | None:
    """{'ac': bool, 'pct': int|None, 'discharging': bool} from pmset, cached
    60 s so /api/status never waits on a subprocess. None off-macOS."""
    import re
    import subprocess
    import time as _t
    if _t.time() - _POWER_CACHE["ts"] < 60:
        return _POWER_CACHE["out"]
    try:
        txt = subprocess.run(["pmset", "-g", "batt"], capture_output=True,
                             text=True, timeout=3).stdout
    except Exception:  # noqa: BLE001 — not macOS / pmset missing
        txt = ""
    out = None
    if txt:
        m = re.search(r"(\d+)%", txt)
        out = {"ac": "AC Power" in txt, "pct": int(m.group(1)) if m else None,
               "discharging": "discharging" in txt}
    _POWER_CACHE.update(ts=_t.time(), out=out)
    return out


def _plus_min(t):
    """`t` (a time of day) a minute later: the readiness check's gate + 1 min."""
    import datetime as dt
    return (dt.datetime.combine(dt.date(2000, 1, 3), t) + dt.timedelta(minutes=1)).time()


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


def _timer_day(tst: dict | None, status: str, s, armed: bool) -> tuple[str, str] | None:
    """A self-fire straddle's day as its timer saw it, from the open on, as
    (level, detail): a late or off-anchor fire (loud, whatever it placed), a
    wait for a quote, a miss, a timer error, a skip, a fire that placed
    nothing. None: the day status says it."""
    tst = tst or {}
    stage = tst.get("stage")
    if stage == "fired" and off_anchor(tst):
        return "warn", f"{fire_said(tst, fire_time(s))} · " + (status if status != "idle" else "nothing placed")
    if status != "idle":
        return None
    if stage == "waiting":
        return "bad", (f"waiting for a quote since {fire_clock(tst.get('wait_late_s'), fire_time(s))} — "
                       f"{tst.get('wait_text')}")
    if stage == "missed":
        return "bad", "missed today — " + miss_why(tst.get("reason"))
    if stage == "error":
        return "bad", "timer error: " + str(tst.get("error"))[:80]
    if stage == "skipped":
        adx = tst.get("adx")
        chop = "CHOP" + (f" ADX {adx:.1f}" if isinstance(adx, (int, float)) else "")
        return "ok", "skipped today — " + ("killed" if tst.get("killed") else
                                            chop if tst.get("gate") is False else "skipped")
    if stage == "fired":
        if armed and not getattr(s, "shadow", False):
            return "warn", "fired at the open, but nothing was placed — see the journal"
        return "info", "fired at the open — journaled only (" + (
            "shadow" if getattr(s, "shadow", False) else "disarmed") + ")"
    return None


def compute_readiness(now_et, cfg: config_mod.AppCfg, engine,
                      acct_status: dict, feed_status: dict | None = None,
                      timer_status: dict | None = None,
                      power: dict | None = None, lab=None) -> dict:
    """Every check the desk needs before the open, across ALL strategies
    and ALL accounts. levels: ok | info | warn | bad; ready = no bad."""
    import datetime as dt
    checks = []
    if not cfg.accounts:
        checks.append({"level": "bad", "label": "Accounts",
                       "detail": "none connected — the book is empty"})
    for aid, a in cfg.accounts.items():
        s = acct_status.get(aid, {})
        checks.append({"level": "ok" if s.get("connected") else "bad",
                       "label": a.label or a.account_name or aid,
                       "detail": "connected" if s.get("connected")
                       else (s.get("error") or "not connected")})
    if power is not None:
        if power.get("discharging") and (power.get("pct") or 100) < 25:
            checks.append({"level": "bad", "label": "Power",
                           "detail": f"battery {power.get('pct')}% and unplugged — "
                                     "the laptop will die"})
        elif power.get("discharging"):
            # under half is worth a look; above it, on battery is a fact and the shield stays quiet
            low = (power.get("pct") or 100) < 50
            checks.append({"level": "warn" if low else "info", "label": "Power",
                           "detail": f"on battery ({power.get('pct')}%)" + (" — plug in" if low else "")})
        else:
            checks.append({"level": "ok", "label": "Power", "detail": "on power"})
    def shown(n):                       # a strategy as the page names it: its label, else its id
        return cfg.strategies[n].label or n

    # an event-day strategy (only_dates) is not part of a day it does not trade
    enabled = {n: s for n, s in cfg.strategies.items()
               if s.enabled and s.trades_on(now_et.date())}
    for name, s in enabled.items():
        if not config_mod.assignments(cfg, name):
            if getattr(s, "kind", "straddle") == "lab":      # a promoted Lab strategy: its resting state too
                checks.append({"level": "info", "label": shown(name),
                               "detail": "no account: runs in shadow"})
                continue
            # a SHADOW strategy with no account is a normal resting state —
            # it must not hold the bulb amber forever
            checks.append({"level": "info" if getattr(s, "shadow", False) else "warn",
                           "label": shown(name),
                           "detail": "enabled but no accounts assigned"})
    weekday = now_et.weekday() < 5
    if weekday:                          # a booked strategy that will not trade today says why (inactive.py)
        for name, s in cfg.strategies.items():
            why = dict(engine.inactive_today(name))
            got = inactive_mod.static_reason(cfg, engine, name, s, now_et.date())
            if got is not None:
                why.setdefault(*got)
            why.pop("not_scheduled_today", None)    # an event-day strategy off its day: expected, journaled only
            if why and s.enabled and config_mod.assignments(cfg, name):
                checks.append({"level": "warn", "label": shown(name),
                               "detail": "inactive today — " + "; ".join(why.values())})
    live_strats = [n for n, s in enabled.items()
                   if not getattr(s, "shadow", False)
                   and config_mod.assignments(cfg, n)]
    if timer_status is not None and weekday:
        # a minute after the gate (09:21 for the 9:30 fire) every enabled self-fire straddle must
        # have gated (ungated ones gate instantly at the gate time) — idle here means its fire is
        # NOT coming; error carries the reason (e.g. no market data)
        tstat = timer_status.get("strategies") or {}
        for name, sc in enabled.items():
            if getattr(sc, "kind", "straddle") != "straddle" \
                    or not getattr(sc, "self_fire", False):
                continue
            gate_t, _, fire_t, _ = schedule(sc)
            if not (_plus_min(gate_t) <= now_et.time() < fire_t):
                continue
            stage = (tstat.get(name) or {}).get("stage")
            if stage in (None, "idle"):
                checks.append({"level": "bad", "label": shown(name),
                               "detail": f"timer has not gated — the {fire_t.hour}:{fire_t.minute:02d} fire "
                                         "is not armed"})
            elif stage == "error":
                checks.append({"level": "bad", "label": shown(name),
                               "detail": "timer error: " +
                                         str((tstat.get(name) or {}).get("error"))[:80]})
    for name, tst in ((timer_status or {}).get("strategies") or {}).items():
        sym = getattr(cfg.strategies.get(name), "symbol", "?")
        orders = tst.get("skipped_orders") or {}
        unreadable = tst.get("skipped_unreadable") or {}
        unsynced = tst.get("skipped_unsynced") or {}
        checked_at = tst.get("prestage_checked_at") or "09:28:30"   # the real check time
        for aid, net in (tst.get("skipped_accounts") or {}).items():
            a = cfg.accounts.get(aid)
            if aid in unsynced:
                detail = (f"{shown(name)} skipped today — its positions and orders were not synced "
                          f"at {checked_at}: unknown, never taken as flat")
            elif net:
                detail = (f"{shown(name)} skipped today — holds {int(net):+d} {sym} "
                          f"(manual position at {checked_at})")
            elif aid in unreadable:
                # the broker read failed and no cached position confirms one
                # either way — say so, rather than implying a known flat book
                detail = (f"{shown(name)} skipped today — position unknown, "
                          f"{len(orders.get(aid) or ())} working {sym} order(s) "
                          f"(manual, at {checked_at})")
            else:
                detail = (f"{shown(name)} skipped today — {len(orders.get(aid) or ())} "
                          f"working {sym} order(s) (manual, at {checked_at})")
            checks.append({"level": "bad",
                           "label": (a.label or a.account_name or aid) if a else aid,
                           "detail": detail})
    bars = [n for n, s in enabled.items() if getattr(s, "kind", "straddle") == "bars"]
    if bars and weekday and feed_window(now_et):
        up = bool((feed_status or {}).get("connected"))
        if up:
            import datetime as _dt
            closes = [w.get("last_close") for w in
                      ((feed_status or {}).get("watching") or {}).values()]
            closes = [c for c in closes if c]
            age = None
            if closes:
                newest = max(_dt.datetime.fromisoformat(c) for c in closes)
                age = (now_et.astimezone(_dt.timezone.utc) - newest).total_seconds()
            if age is not None and age > 240:
                checks.append({"level": "bad", "label": "Price feed",
                               "detail": f"stale — last bar closed {age / 60:.0f} min ago"})
            else:
                checks.append({"level": "ok", "label": "Price feed",
                               "detail": "live bars flowing"})
        else:
            checks.append({"level": "bad", "label": "Price feed",
                           "detail": "down — " + ", ".join(bars) + " cannot see price"})
    tstrats = (timer_status or {}).get("strategies") or {}
    for name, s in enabled.items():
        status = engine.day_status(name)
        if getattr(s, "kind", "straddle") == "lab":
            # the runner stopped its day (2026-10-19: no sandbox on the VPS, both strategies silent all day while the
            # desk said ready): a problem is bad, the owner's own stop or kill only a warning
            said = lab.runner_said(name) if lab is not None else None
            if said and said.get("state") == "stopped":
                why = said.get("why") or "no reason given"
                checks.append({"level": "warn" if why in ("Stopped for today.", "Killed today.") else "bad",
                               "label": shown(name), "detail": "stopped for the day — " + why})
                continue
            if status != "idle":
                checks.append({"level": "ok", "label": shown(name), "detail": status})
            continue                     # no trade by its last-entry time is a normal day for a Lab strategy
        h, m = s.accept_until_et.split(":")
        after_window = now_et.time() > dt.time(int(h), int(m))
        if getattr(s, "kind", "straddle") == "bars":
            if status != "idle":
                checks.append({"level": "ok", "label": shown(name), "detail": status})
            continue                     # a rule with no setup today is normal
        if getattr(s, "kind", "straddle") == "levels":
            if status != "idle":
                checks.append({"level": "ok", "label": shown(name), "detail": status})
            continue                     # leveltimer journals every fire / skip / miss with its why
        # from the open, a self-fire straddle's own timer says what its day was
        # (09:21-09:30 has its own check above)
        told = (_timer_day(tstrats.get(name), status, s, cfg.armed)
                if weekday and getattr(s, "self_fire", False) and now_et.time() >= fire_time(s)
                else None)
        if told is not None:
            checks.append({"level": told[0], "label": shown(name), "detail": told[1]})
        elif weekday and after_window and status == "idle":
            if s.gated:
                checks.append({"level": "warn", "label": shown(name),
                               "detail": "no signal today — gated day (expected) "
                                         "or the pipe is broken"})
            else:
                checks.append({"level": "bad", "label": shown(name),
                               "detail": "no signal arrived — this strategy "
                                         "trades every day"})
        elif status != "idle":
            checks.append({"level": "ok", "label": shown(name), "detail": status})
    lab_line = labdesk_mod.readiness_line(cfg)   # only on a desk that reads another desk's Lab store
    if lab_line is not None:
        checks.append(lab_line)
    lab_line = labdesk_mod.orphan_line(cfg, engine)   # only when a Lab round is open for a strategy this desk lacks
    if lab_line is not None:
        checks.append(lab_line)
    if cfg.armed:
        checks.append({"level": "info", "label": "Mode",
                       "detail": "ARMED — signals place real orders"})
    else:
        # disarmed with a live book on a weekday = the algo will NOT trade
        checks.append({"level": "warn" if (weekday and live_strats) else "info",
                       "label": "Mode",
                       "detail": ("DISARMED — " + ", ".join(live_strats) +
                                  " will journal only, no orders")
                       if (weekday and live_strats)
                       else "shadow — signals journal only"})
    return {"ready": not any(c["level"] == "bad" for c in checks),
            "checks": checks}


def should_fire_readiness(now_et, fired_date: str | None) -> bool:
    if now_et.weekday() >= 5 or fired_date == now_et.date().isoformat():
        return False
    t = now_et.time()
    return t.hour == READINESS_FROM[0] and t.minute >= READINESS_FROM[1]


def _key_env(key: str) -> str:
    """A login key is 'tv:<env>:<user>' — the env it was verified on. The
    user part may itself hold colons (Google-linked logins are
    'Google:1012...'), so split twice at most."""
    parts = key.split(":", 2)
    return "live" if len(parts) == 3 and parts[1] == "live" else "demo"


def _md_token_of(ad) -> str:
    tok = getattr(getattr(getattr(ad, "_auth", None), "tokens", None),
                  "md_access_token", "")
    return tok if (tok and ad.connected) else ""


def _md_expiry_of(ad) -> float:
    """Unix expiry of the token the adapter's md token came with; 0 when unknown."""
    try:
        return float(getattr(getattr(getattr(ad, "_auth", None), "tokens", None),
                             "expires_at_unix", 0) or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def md_source(cfg: config_mod.AppCfg, adapters: dict):
    """Market data rides ONE login: its env's md host AND its md token — a
    token only works on its own env's host. Demo first: the proven feed, and
    a live account then needs no md subscription of its own. Within that env,
    the connected login whose token expires LAST (config order on a tie): an
    md socket dies when its token does, so the freshest carries it furthest —
    after the early renewal (09:10-09:19:30 ET) the timer's 09:20 / 09:28:30
    md socket starts on a token that lasts past 10:10. Returns
    (keyring_key, env, token_provider)."""
    ranked = sorted(cfg.accounts.items(), key=lambda kv: kv[1].live)
    up = [(a, adapters[aid]) for aid, a in ranked
          if a.keyring_key and adapters.get(aid) is not None and _md_token_of(adapters[aid])]
    if up:
        live = up[0][0].live
        a, ad = max((c for c in up if c[0].live == live), key=lambda c: _md_expiry_of(c[1]))
        return (a.keyring_key, "live" if a.live else "demo",
                lambda ad=ad: _md_token_of(ad))
    for aid, a in ranked:            # nothing connected: that login logs in
        if a.keyring_key:
            return a.keyring_key, "live" if a.live else "demo", None
    raise RuntimeError("no accounts configured for market data")


def build_adapter(account_id: str, a: config_mod.AccountCfg) -> BrokerAdapter:
    if a.paper:                      # a chart-service paper account: no login, no broker (broker/paper.py)
        return PaperAdapter(account_id)
    env = "live" if a.live else "demo"
    sel = {"account_name": a.account_name} if a.account_name else None
    # entries on one login share its token: one login / renewal per Tradovate user
    return TradovateAdapter(account_id, env=env, keyring_key=a.keyring_key,
                            account_selector=sel, share_auth=bool(a.keyring_key))


def build_feed(cfg: config_mod.AppCfg, adapters: dict) -> MarketFeed:
    key, env, provider = md_source(cfg, adapters)
    return MarketFeed(key, env, token_provider=provider)


def create_app(cfg: config_mod.AppCfg | None = None,
               adapters: dict[str, BrokerAdapter] | None = None,
               *, background: bool = True,
               adapter_factory=build_adapter, feed_factory=build_feed,
               login_budget: LoginBudget | None = None,
               paper_client: httpx.AsyncClient | None = None,
               lab: bool | None = None) -> FastAPI:
    cfg = cfg or config_mod.load()
    # The Lab side (promoted Lab strategies on this desk) is opt-in per desk: None = on only when the file
    # <state_dir>/lab_desk.on exists (labdesk.py's docstring). Off: the store is never read, nothing below is a Lab path.
    lab_on = labdesk_mod.flagged(state_dir()) if lab is None else bool(lab)
    if lab_on:
        labdesk_mod.attach(cfg)  # promoted Lab strategies join the config in memory (never config.json); never raises
    adapters: dict[str, BrokerAdapter] = adapters if adapters is not None else {}
    engine = Engine(cfg, adapters)
    acct_status: dict[str, dict] = {}
    paper_http = paper_client or httpx.AsyncClient(base_url=PAPER_URL, timeout=5.0)   # the paper accounts list
    # logins are budgeted per Tradovate USER (the login key), never per entry: five
    # entries on one Apex user each falling back to a login ran it into 429 (2026-09-29)
    budget = login_budget or LoginBudget()
    budget.journal = engine.journal
    _logged_in_once: set[str] = set()        # entries that logged in / rode the shared token
    _login_first_spent: set[tuple] = set()   # (login key, live): its one exempt first login
    _went_private: set[str] = set()          # entries refused on the shared token
    _parked: dict[str, str] = {}             # entry -> why (its account is not on its login)
    # entry -> its account-gone state: first/next_check (unix), unbooked, confirmed
    _gone: dict[str, dict] = {}
    _no_accounts_warned: set[str] = set()
    notices: list[dict] = []                 # one-liners for the desk page (status payload)

    def _notice(text: str, **kw) -> None:
        notices.append({"et": engine.now_et().isoformat(timespec="seconds"),
                        "text": text, **kw})
        del notices[:-NOTICES_KEPT]

    def _short(aid: str) -> str:
        a = cfg.accounts.get(aid)
        name = (a.account_name if a is not None else "") or aid
        return "…" + name[-3:] if len(name) > 6 else name

    def _login_label(aid: str) -> str:
        tail = _login_key(aid).rsplit(":", 1)[-1].split("_", 1)[0]
        return tail.capitalize() if tail else "Tradovate"

    _listed: dict[str, set[str]] = {}        # login key -> account names its last probe listed
    _add_lock = asyncio.Lock()               # one "add accounts" at a time

    def _on_desk(key: str, name: str) -> str | None:
        """The desk entry that already carries this broker account of this login: pinned
        to it, or -- unpinned -- riding it (the connected adapter says which)."""
        low = name.lower()
        for aid, a in cfg.accounts.items():
            if a.keyring_key != key:
                continue
            pinned = a.account_name or getattr(adapters.get(aid), "_acct_name", "") or ""
            if pinned.lower() == low or aid == low:
                return aid
        return None

    _login_uid: dict[str, object] = {}       # login key -> the Tradovate user id first seen
    _login_suspect: set[str] = set()         # login keys already warned "may have changed"
    _gone_tasks: dict[str, asyncio.Task] = {}

    def _login_key(aid: str) -> str:
        a = cfg.accounts.get(aid)
        return (a.keyring_key if a is not None else "") or aid

    def _md_factory():
        key, env, provider = md_source(cfg, adapters)
        return TradovateMD(key, env, token_provider=provider)

    timer = SelfTimer(cfg, engine, md_factory=_md_factory)
    # the "levels" strategies (NQ prop algos): their own clock, their own market-data socket, and the
    # day_take price watcher; target_take reads the desk's daily balance record
    level_timer = LevelTimer(cfg, engine, md_factory=_md_factory)
    engine.balance_history = lambda account: equity.equity_by_day(_equity_path(), account)
    # trading from the chart (spec 2026-09-26): views, guards, journaling
    desk = ChartDesk(cfg, engine, adapters, acct_status, timer_status=timer.status)
    # promoted Lab strategies (kind "lab"): limits, book checks, the switch, Remove, the status block (labdesk.py)
    labdesk = labdesk_mod.LabDesk(cfg, engine, adapters, paused=desk.views_paused, on=lab_on)
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
            if (s.symbol, int(s.bar_minutes)) not in f.watching() and not deferred:
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

    _connect_locks: dict[str, asyncio.Lock] = {}

    async def _connect_account(aid: str, force_login: bool = False,
                               manual: bool = False) -> str:
        """One (re)connect per account at a time (the supervisor, a manual Reconnect and
        a gone re-check can race), and never for an account no longer on the desk."""
        async with _connect_locks.setdefault(aid, asyncio.Lock()):
            if aid not in cfg.accounts:
                raise RuntimeError(f"{aid} is no longer on the desk")
            return await _connect_account_locked(aid, force_login, manual)

    async def _connect_account_locked(aid: str, force_login: bool = False,
                                      manual: bool = False) -> str:
        """(Re)connect one account. Prefers an in-place reconnect on the token
        it already holds — no login spent — and only falls back to a full
        login. A drop used to cost a full login every time: ~20/hour on a
        sleeping laptop against Tradovate's ~5/hour limit. Every login goes
        through the user's LoginBudget (429 cool-down, hourly cap, backoff;
        `manual` skips only the backoff); refused, it raises LoginDeferred."""
        a = cfg.accounts[aid]
        key = _login_key(aid)
        ad = adapters.get(aid)
        if ad is None:
            ad = adapters[aid] = adapter_factory(aid, a)
        if hasattr(ad, "login_budget") and ad.login_budget is not budget:
            ad.login_budget = budget        # the token refresh's login fallback asks it too

        login_id = (key, a.live)

        async def _login(fell_back_from=None) -> None:
            if a.paper:              # nothing to log in to: the chart service's book, no budget spent
                await ad.connect()
                return
            # the cap/backoff exemption is ONE first login per Tradovate login per process
            # (its entries share the token), never for an entry that went private
            first = (aid not in _logged_in_once and login_id not in _login_first_spent
                     and aid not in _went_private)
            why = budget.blocked(key, first=first, manual=manual)
            if why:
                raise LoginDeferred(why if fell_back_from is None else
                                    f"{str(fell_back_from)[:120]} — no login fallback: {why}")
            if fell_back_from is not None:
                engine.journal("reconnect_fell_back_to_login", account=aid,
                               error=str(fell_back_from)[:200])
            _logged_in_once.add(aid)
            _login_first_spent.add(login_id)
            budget.record_login(key)
            try:
                await ad.connect()
            except AccountNotOnLogin:
                budget.login_result(key)    # the login itself worked
                raise
            except Exception as e:  # noqa: BLE001
                budget.login_result(key, e)
                raise
            budget.login_result(key)

        mode = "login"
        has_token = bool(getattr(getattr(ad, "_auth", None), "tokens", None))
        if has_token and not force_login and hasattr(ad, "reconnect"):
            try:
                await ad.reconnect()
                mode = "reconnect"
                _logged_in_once.add(aid)           # on the shared token: the login's
                _login_first_spent.add(login_id)   # first login is spent already
            except AccountNotOnLogin:
                # Permanent: the pin is wrong for THIS login, not a dropped
                # socket. A full login would just burn the shared keyring
                # login (other pins on it need it) chasing a pin that will
                # never be there — never retry it as a transient drop.
                raise
            except Exception as e:  # noqa: BLE001 — fall back to a real login
                budget.note_error(key, e)          # a 429 cools the whole user down
                if (getattr(ad, "auth_shared", False) and "authorize failed" in str(e)
                        and not is_rate_limited(e)):
                    # the shared token was refused on THIS socket: its login must never
                    # re-roll the token every sibling rides -- a private one, budgeted
                    ad.go_private()
                    _went_private.add(aid)
                    engine.journal("shared_token_refused", account=aid, error=str(e)[:200])
                await _login(fell_back_from=e)
        else:
            await _login()
        await ad.observe_fills(engine.on_fill)
        if not a.paper:              # the chart page trades a paper account through its own book, never the desk
            desk.attach(aid, ad)
        _parked.pop(aid, None)
        _inplace_streak.pop(aid, None)
        _no_accounts_warned.discard(aid)
        uid = getattr(getattr(getattr(ad, "_auth", None), "tokens", None), "user_id", None)
        if uid:
            _login_uid.setdefault(key, uid)
        g = _gone.pop(aid, None)
        if g is not None:
            restored = []
            for name, rows in (g.get("booked") or {}).items():
                have = cfg.book.setdefault(name, [])
                for r in rows:
                    if not any(x.get("account") == aid for x in have):
                        have.append(dict(r))
                        restored.append(name)
            if restored:
                config_mod.save(cfg)
            engine.journal("account_back", account=aid, rebooked=restored)
            _notice(f"{_short(aid)} is back on your {_login_label(aid)} login", account=aid)
        acct_status[aid] = {"connected": True, "error": None}
        engine.journal("broker_connected", account=aid,
                       broker_account=a.account_name, mode="paper" if a.paper else mode)
        try:
            await engine.reconcile_account(aid)
        except Exception as e:  # noqa: BLE001 — never block the connect on it
            engine.journal("reconcile_error", account=aid, error=str(e)[:200])
        return mode

    _login_cooldown: dict[str, float] = {}   # account id -> unix ts of next try
    _inplace_streak: dict[str, int] = {}     # failed in-place-only retries in a row

    def _token_left(aid: str) -> float:
        import time as _t
        tokens = getattr(getattr(adapters.get(aid), "_auth", None), "tokens", None)
        exp = getattr(tokens, "expires_at_unix", 0) or 0
        return exp - _t.time() if exp else 0.0

    def _connect_failed(aid: str, e: Exception) -> None:
        """Record a failed (re)connect. An account missing from its login is PARKED:
        never retried automatically (the loop would log in on the shared user every
        few minutes forever -- apex...049, closed at Apex, 2026-09-29), only by a
        manual Reconnect, once per click."""
        import time as _t
        if aid not in cfg.accounts:
            return                           # removed meanwhile: nothing to record
        msg = str(e)
        if isinstance(e, AccountNotOnLogin):
            a = cfg.accounts.get(aid)
            name = (a.account_name if a is not None else "") or aid
            if aid not in _parked:
                engine.journal("account_parked", account=aid, error=msg[:200])
            _parked[aid] = msg
            _login_cooldown.pop(aid, None)
            acct_status[aid] = {"connected": False, "parked": True,
                                "error": f"account {name} is not on this login — "
                                         f"remove it from the desk ({msg[:160]})"}
            _note_gone(aid, e)
            return
        if "login exposes no accounts" in msg:
            # never evidence that an account is gone: warn, act on nothing
            if aid not in _no_accounts_warned:
                _no_accounts_warned.add(aid)
                engine.journal("login_lists_no_accounts", account=aid, login=_login_key(aid))
                _notice(f"your {_login_label(aid)} login listed no accounts — nothing was "
                        "removed; check the login at Tradovate", account=aid, level="warn")
        acct_status[aid] = {"connected": False, "error": msg}
        if isinstance(e, LoginDeferred) and _token_left(aid) > 120:
            # the socket dropped, its token is still good, only the login fallback was
            # refused (a 429 cool-down, the cap): no login is spent retrying in place,
            # so do it soon -- a healthy entry must not sit out 5 minutes before the fire
            n = _inplace_streak[aid] = _inplace_streak.get(aid, 0) + 1
            lo, hi = INPLACE_RETRY_S
            _login_cooldown[aid] = _t.time() + min(lo * 2 ** (n - 1), hi)
            return
        # NEVER hammer the login endpoint: auth rejections and rate-limit
        # tickets wait 30 min; anything else 5 min (the user's LoginBudget
        # gates the login itself on top of this)
        slow = ("Login failed" in msg or "p-ticket" in msg or "p-captcha" in msg)
        _login_cooldown[aid] = _t.time() + (1800 if slow else 300)

    def _note_gone(aid: str, e: AccountNotOnLogin) -> None:
        """A successful sync listed the login's accounts and this entry's is not among
        them. The first sighting parks it and journals account_gone; one at least
        GONE_CONFIRM_S later confirms: _gone_step then unbooks and removes it. Never evidence: a failed, 429'd or empty sync (no listing), a login
        whose Tradovate user changed, or one where not only a MINORITY of the login's
        pinned entries is missing -- that is a changed login, not a closed account: park,
        warn, touch nothing."""
        import time as _t
        listed = getattr(e, "listed", None)
        if not listed or aid not in cfg.accounts:
            return
        key, live = _login_key(aid), cfg.accounts[aid].live
        pins = {x: (a.account_name or "").lower() for x, a in cfg.accounts.items()
                if _login_key(x) == key and a.live == live and a.account_name}
        have = {str(n).lower() for n in listed}
        missing = [x for x, pin in pins.items() if pin not in have]
        uid, was = getattr(e, "user_id", None), _login_uid.get(key)
        if (uid and was and uid != was) or 2 * len(missing) >= len(pins):
            _gone.pop(aid, None)
            if key not in _login_suspect:
                _login_suspect.add(key)
                engine.journal("login_changed_suspect", login=key, missing=missing,
                               user_changed=bool(uid and was and uid != was),
                               login_lists=list(listed))
                _notice(f"your {_login_label(aid)} login no longer lists "
                        f"{', '.join(_short(x) for x in missing) or _short(aid)} — the login may "
                        "have changed; nothing was unbooked or removed. Check it at Tradovate",
                        account=aid, level="warn")
            return
        now = _t.time()
        g = _gone.get(aid)
        if g is None:
            _gone[aid] = {"first": now, "next_check": now + GONE_CONFIRM_S,
                          "confirmed": False, "listed": list(listed)}
            engine.journal("account_gone", account=aid, login_lists=list(listed))
            _notice(f"{_short(aid)} is no longer on your {_login_label(aid)} login — parked; "
                    "removed from the desk if a second check agrees", account=aid)
        elif now - g["first"] >= GONE_CONFIRM_S:
            g["confirmed"] = True

    async def _drop_account(aid: str, **journal_extra) -> None:
        """Unassign an entry from every strategy, drop it from the pool, close it. An
        in-flight gone re-check is cancelled first, and the account's connect lock is
        held, so a removed adapter is never reconnected behind the removal. Also waits
        for the Kill lock (2026-09-29 review): the Kill sweep reads `adapters` and calls
        each one's cancel_all/flatten_all in turn, so a removal mid-sweep must wait its
        turn rather than pop an entry out from under it (this covers every removal path,
        the manual endpoint AND the gone-account auto-removal below, alike)."""
        t = _gone_tasks.pop(aid, None)
        if t is not None and not t.done():
            t.cancel()
            with contextlib.suppress(BaseException):
                await t
        async with _kill_lock(), _connect_locks.setdefault(aid, asyncio.Lock()):
            await _drop_account_locked(aid, **journal_extra)
        _connect_locks.pop(aid, None)

    async def _drop_account_locked(aid: str, **journal_extra) -> None:
        for name in list(cfg.book):
            cfg.book[name] = [a for a in cfg.book[name]
                              if a.get("account") != aid]
        cfg.accounts.pop(aid, None)
        config_mod.save(cfg)
        acct_status.pop(aid, None)
        _parked.pop(aid, None)
        _gone.pop(aid, None)
        _login_cooldown.pop(aid, None)
        old = adapters.pop(aid, None)
        if old is not None:
            with contextlib.suppress(Exception):
                await old.close()
        engine.journal("account_removed", account=aid, **journal_extra)

    async def _gone_check(aid: str) -> None:
        """One confirming re-sync, in its own task: it never holds the supervisor."""
        try:
            await asyncio.wait_for(_connect_account(aid), GONE_CHECK_TIMEOUT_S)
        except Exception as e:  # noqa: BLE001 — _note_gone judges it
            _connect_failed(aid, e)

    async def _gone_step() -> None:
        """Accounts that left their login: one confirming re-sync GONE_CONFIRM_S after the
        first sighting, then -- confirmed -- unbook and remove. The bookings are kept in case it
        comes back."""
        import time as _t
        if not _gone:
            return
        now_et = engine.now_et()
        for aid, g in list(_gone.items()):
            if aid not in cfg.accounts:
                _gone.pop(aid, None)
                continue
            if g["confirmed"]:
                g["booked"] = {n: [dict(r) for r in rows if r.get("account") == aid]
                               for n, rows in cfg.book.items()
                               if any(r.get("account") == aid for r in rows)}
                line = (f"{_short(aid)} is no longer on your {_login_label(aid)} login — "
                        "removed from the desk")           # worded before the entry goes
                await _drop_account(aid, reason="not on the login any more",
                                    unbooked=sorted(g["booked"]))
                _notice(line, account=aid)
                continue
            t = _gone_tasks.get(aid)
            if (t is None or t.done()) and _t.time() >= g["next_check"]:
                g["next_check"] = _t.time() + GONE_CONFIRM_S
                _gone_tasks[aid] = asyncio.create_task(_gone_check(aid))

    async def _sync_paper() -> None:
        """Every chart-service paper account is an account of the desk's pool (assignable to an algo in
        + Assign) -- one per paper id, labelled "<name> (paper)". Added here, never by hand; removed only
        with the account on the Charts page (its adapter then fails to read the book and drops out of
        the readiness checks). A service that is down adds nothing."""
        if not (background or paper_client is not None):
            return                   # a test app reaches no service it was not handed
        try:
            r = await paper_http.get("/api/paper/accounts")
            r.raise_for_status()
            rows = r.json()["accounts"]
        except Exception:  # noqa: BLE001 — the chart service is down: the adapters say so themselves
            return
        for row in rows:
            aid = str(row["id"])
            if aid in cfg.accounts or aid == "paper":   # the built-in PAPER is chart trading's own (owner, 2026-10-20)
                continue
            label = str(row.get("label") or aid)
            cfg.accounts[aid] = config_mod.AccountCfg(paper=True, label=f"{label} (paper)", account_name=label)
            config_mod.save(cfg)
            engine.journal("account_added", account=aid, live=False, paper=True)
        gone = {aid for aid, a in cfg.accounts.items() if a.paper} - {str(r["id"]) for r in rows}
        for aid in gone:
            acct_status[aid] = {"connected": False, "error": "this paper account no longer exists on the Charts page"}

    async def _broker_loop():
        import time as _t
        while True:
            budget.tick()                    # a cool-down's one "ended" line
            with contextlib.suppress(Exception):
                await _sync_paper()
            try:
                await _gone_step()
            except Exception as e:  # noqa: BLE001 — never kill the supervisor
                engine.journal("account_gone_error", error=str(e)[:200])
            for aid in list(cfg.accounts):
                if aid in _parked:
                    continue                 # only a manual Reconnect retries it
                ad = adapters.get(aid)
                if ad is not None and ad.connected:
                    continue
                if _t.time() < _login_cooldown.get(aid, 0):
                    continue
                try:
                    await _connect_account(aid)
                    _login_cooldown.pop(aid, None)
                except Exception as e:  # noqa: BLE001 — report, back off
                    _connect_failed(aid, e)
            await asyncio.sleep(RECONNECT_INTERVAL_S)

    async def _refresh_snapshots() -> None:
        """The caches' slow refresh: ONE position/list + cashBalance/list per
        Tradovate user (its lists cover every account under the login), on the first
        connected entry that can do it. Skipped for a user in a 429 cool-down."""
        by_user: dict[tuple, list] = {}
        for aid, ad in list(adapters.items()):
            if aid in cfg.accounts and ad.connected and hasattr(ad, "refresh_snapshot"):
                by_user.setdefault((_login_key(aid), cfg.accounts[aid].live), []).append(ad)
        for (key, _live), ads in by_user.items():
            if budget.cooling(key):
                continue
            try:
                await ads[0].refresh_snapshot(ads[1:])
            except Exception as e:  # noqa: BLE001 — the pushes still carry the caches
                budget.note_error(key, e)

    async def _equity_loop():
        while True:
            with contextlib.suppress(Exception):
                await _refresh_snapshots()
            for aid, ad in list(adapters.items()):
                try:        # from the caches: no broker request
                    if ad.connected:
                        m = await ad.get_metrics()
                        if m.get("balance") is not None and m.get("account"):
                            equity.record_equity(_equity_path(), str(m["account"]), float(m["balance"]),
                                                 engine.now_et().date().isoformat())
                except Exception:  # noqa: BLE001 — snapshots must never crash
                    pass
            await asyncio.sleep(EQUITY_INTERVAL_S)

    readiness_fired = {"date": None}

    async def _feed_loop():
        while True:
            try:
                await feed_step()
            except Exception as e:  # noqa: BLE001 — the feed loop must never die
                engine.journal("feed_loop_error", error=str(e)[:200])
            await asyncio.sleep(1.0)

    async def _sibling_loop():
        while True:
            try:
                await engine.sibling_tick()
            except Exception as e:  # noqa: BLE001 — the sibling watch must never die
                engine.journal("sibling_loop_error", error=str(e)[:200])
            await asyncio.sleep(SIBLING_INTERVAL_S)

    async def _inactive_loop():
        while True:
            try:
                inactive_mod.sweep(cfg, engine, engine.now_et())
            except Exception as e:  # noqa: BLE001 — a journaling aid must never die or block
                engine.journal("inactive_loop_error", error=str(e)[:200])
            await asyncio.sleep(20.0)

    async def _clock_loop():
        while True:
            try:
                await engine.clock_tick()
                now = engine.now_et()
                if should_fire_readiness(now, readiness_fired["date"]):
                    readiness_fired["date"] = now.date().isoformat()
                    r = compute_readiness(now, cfg, engine, acct_status,
                                          feed_status(), timer.status(), power_status(), lab=labdesk)
                    engine.journal(
                        "morning_readiness", ready=r["ready"],
                        problems=[c["label"] + ": " + c["detail"]
                                  for c in r["checks"]
                                  if c["level"] in ("bad", "warn")])
            except Exception as e:  # noqa: BLE001 — the clock must never die
                engine.journal("clock_error", error=str(e))
            await asyncio.sleep(CLOCK_INTERVAL_S)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        _app.state.desk_key, key_err = desk_api.ensure_key(state_dir() / desk_api.KEY_FILE)
        if key_err:
            engine.journal("desk_key_error", error=key_err)
        # the Lab runner's OWN key (never the chart service's): /api/lab/* answers 503 without it
        _app.state.lab_key = None

        def _lab_key() -> None:
            if not labdesk.on:                       # an OFF desk makes no key: the gate answers 503 and the runner
                return                               # has none to read (it stays in shadow)
            _app.state.lab_key, lab_key_err = desk_api.ensure_key(state_dir() / desk_api.LAB_KEY_FILE)
            if lab_key_err:
                engine.journal("lab_key_error", error=lab_key_err)

        for step in (_lab_key, labdesk.start):       # (start: says whether the Lab side is on, rebuilds its counters)
            try:                             # a Lab problem never fails the desk's start, and one step's never the other's
                step()
            except Exception as e:  # noqa: BLE001
                print(f"homebase desk: the Lab side's start failed: {e!r}", file=sys.stderr)
                with contextlib.suppress(Exception):
                    engine.journal("lab_start_error", error=f"{type(e).__name__}: {e}"[:200])
        tasks = []
        if background:
            tasks = [asyncio.create_task(_clock_loop()),
                     asyncio.create_task(_broker_loop()),
                     asyncio.create_task(_equity_loop()),
                     asyncio.create_task(timer.loop()),
                     asyncio.create_task(level_timer.loop()),
                     asyncio.create_task(_inactive_loop()),
                     asyncio.create_task(_sibling_loop()),
                     asyncio.create_task(_feed_loop()),
                     asyncio.create_task(desk.run())]
            if labdesk.on:
                tasks.append(asyncio.create_task(labdesk.run()))
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            with contextlib.suppress(Exception):
                labdesk.close()              # the Lab store's desk lock goes back (the desk that starts next owns it)
            await _feed_close("shutdown")
            for ad in adapters.values():
                with contextlib.suppress(Exception):
                    await ad.close()
            with contextlib.suppress(Exception):
                await paper_http.aclose()

    app = FastAPI(title="Ramos Quant Homebase", lifespan=lifespan)
    app.state.engine = engine
    app.state.cfg = cfg
    app.state.adapters = adapters
    app.state.feed_step = feed_step
    app.state.inactive_sweep = lambda now_et=None: inactive_mod.sweep(cfg, engine, now_et or engine.now_et())
    app.state.sync_paper = _sync_paper
    # test-only hooks onto the broker reconnect loop (never called by the
    # app itself outside `background=True`'s lifespan task)
    app.state.connect_account = _connect_account
    app.state.broker_loop = _broker_loop
    app.state.login_cooldown = _login_cooldown
    app.state.login_budget = budget
    app.state.parked = _parked
    app.state.gone = _gone
    app.state.login_uid = _login_uid
    app.state.gone_step = _gone_step
    app.state.drop_account = _drop_account
    app.state.connect_failed = _connect_failed
    app.state.refresh_snapshots = _refresh_snapshots
    app.state.notices = notices
    app.state.feed_box = feed_box
    app.state.desk = desk
    app.state.labdesk = labdesk
    app.include_router(desk_api.trade_router(desk), prefix="/api/trade")
    app.include_router(desk_api.labdesk_router(labdesk), prefix="/api/lab")   # the Lab runner's door (its own gate and key)
    app.include_router(desk_api.settings_router(desk))
    # Task 5b: every write needs an allowed Host/Origin and a JSON body (main app only)
    app.add_middleware(desk_api.WriteGuard, hosts=lambda: cfg.allowed_hosts)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")


    kill_lock_box: dict = {}

    def _kill_lock() -> asyncio.Lock:
        """The Kill's own lock, bound to the running loop (a TestClient and a
        bare asyncio.run each bring their own)."""
        loop = asyncio.get_running_loop()
        held = kill_lock_box.get("lock")
        if held is None or held[0] is not loop:
            held = kill_lock_box["lock"] = (loop, asyncio.Lock())
        return held[1]

    # ------------------------------------------------------------ the routes (homebase/routes/, one module per concern)
    routes.status.register(app, JOURNAL_TAIL=JOURNAL_TAIL, STATIC=STATIC, _login_cooldown=_login_cooldown,
                                acct_status=acct_status, adapters=adapters, cfg=cfg,
                                compute_readiness=compute_readiness, engine=engine, feed_status=feed_status,
                                labdesk=labdesk, level_timer=level_timer, notices=notices, power_status=power_status,
                                state_dir=lambda: state_dir(), timer=timer)
    routes.control.register(app, _kill_lock=_kill_lock, adapters=adapters, cfg=cfg, desk=desk, engine=engine)
    routes.accounts.register(app, ADD_MANY_MAX=ADD_MANY_MAX, _add_lock=_add_lock, _connect_account=_connect_account,
                                  _connect_failed=_connect_failed, _drop_account=_drop_account, _key_env=_key_env,
                                  _listed=_listed, _login_cooldown=_login_cooldown,
                                  _login_first_spent=_login_first_spent, _on_desk=_on_desk, acct_status=acct_status,
                                  adapter_factory=adapter_factory, adapters=adapters, budget=budget, cfg=cfg,
                                  engine=engine, paper_http=paper_http)
    routes.strategies.register(app, cfg=cfg, engine=engine, labdesk=labdesk)
    routes.lab.register(app, labdesk=labdesk)
    routes.records.register(app, STATIC=STATIC, _equity_path=_equity_path, adapters=adapters, cfg=cfg,
                                 state_dir=lambda: state_dir())

    return app


# python.org macOS builds: the CA shim lives in homebase/__init__.py
assert os.environ.get("SSL_CERT_FILE") or True
app = create_app()
