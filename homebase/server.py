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
import os
from dataclasses import asdict
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config as config_mod
from . import secrets_store
from .broker.base import AccountNotOnLogin, BrokerAdapter, OrderRequest
from .broker.login_budget import LoginBudget, LoginDeferred, is_rate_limited
from .broker.paper import BASE_URL as PAPER_URL, PaperAdapter
from .broker.tradovate import RENEW_EARLY_FROM, RENEW_QUIET, TradovateAdapter
from .engine import Engine, _hhmm
from .feed import MarketFeed
from .marketdata import TradovateMD
from .rules import RULES
from .metrics import live_metrics, strategy_live_detail
from .paths import state_dir
from .leveltimer import LevelTimer
from .timer import SelfTimer, fire_clock, fire_said, fire_time, miss_why, off_anchor, schedule
from . import desk_api
from .trading import ChartDesk

STATIC = Path(__file__).resolve().parent / "static"
CLOCK_INTERVAL_S = 1       # also paces the sibling-cancel backstop (cache reads)
RECONNECT_INTERVAL_S = 5   # cheap now: reconnects reuse the token
GONE_CONFIRM_S = 300       # an account missing from its login is removed only when a 2nd
                           # successful sync at least this much later still misses it
GONE_QUIET = (dt.time(9, 20), dt.time(9, 35))   # weekdays ET: never unbook/remove in here
GONE_CHECK_QUIET = (dt.time(9, 10), dt.time(9, 35))   # ... and never a confirming re-sync
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
FEED_QUIET = (dt.time(9, 20), dt.time(9, 35))   # weekdays ET: no non-urgent feed (re)connect


def _equity_path() -> Path:
    return state_dir() / "equity.jsonl"


def record_equity(account: str, equity: float, date: str) -> None:
    with open(_equity_path(), "a") as f:
        f.write(json.dumps({"date": date, "account": account,
                            "equity": equity}) + "\n")


def equity_by_day(account: str) -> dict[str, float]:
    out: dict[str, float] = {}
    p = _equity_path()
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("account") == account and r.get("equity") is not None:
            out[r["date"]] = float(r["equity"])
    return dict(sorted(out.items()))


def daily_pnl(account: str, month: str) -> dict:
    eq = equity_by_day(account)
    days, prev, total = {}, None, 0.0
    for date, e in eq.items():
        if prev is not None and date.startswith(month):
            pnl = round(e - prev, 2)
            days[date] = pnl
            total += pnl
        prev = e
    return {"days": days, "total": round(total, 2)}


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


def feed_deferred(now_et, strategies: dict) -> bool:
    """Weekdays 09:20-09:35 ET a price-feed (re)connect or a new bars subscription --
    market-data requests on the login the 9:30 bot's quote may ride -- waits for 09:35,
    unless an enabled bars strategy's accept window opens by 09:35 and is not over (it needs
    bars then, and one opening at 09:35 exactly must not lose its first bar to the wait).
    The (re)connect at 09:35 loads the warm-up history again, so a rule that starts later
    (nq10am: 09:59) loses nothing."""
    t = now_et.time()
    if now_et.weekday() >= 5 or not FEED_QUIET[0] <= t < FEED_QUIET[1]:
        return False
    return not any(_hhmm(s.accept_from_et) <= FEED_QUIET[1] and t <= _hhmm(s.accept_until_et)
                   for s in strategies.values())


def feed_recycle_window(now_et) -> bool:
    """Weekdays, the early-renewal window (09:10-09:19:30 ET, broker/tradovate.py): a feed
    on an older md token than its login now holds is rebuilt on the new one before 09:20,
    so it cannot die at the old token's expiry inside 09:20-09:35."""
    return now_et.weekday() < 5 and RENEW_EARLY_FROM <= now_et.time() < RENEW_QUIET[0]


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
                      power: dict | None = None) -> dict:
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
            checks.append({"level": "warn", "label": "Power",
                           "detail": f"on battery ({power.get('pct')}%) — plug in"})
        else:
            checks.append({"level": "ok", "label": "Power", "detail": "on power"})
    # an event-day strategy (only_dates) is not part of a day it does not trade
    enabled = {n: s for n, s in cfg.strategies.items()
               if s.enabled and s.trades_on(now_et.date())}
    for name, s in enabled.items():
        if not config_mod.assignments(cfg, name):
            # a SHADOW strategy with no account is a normal resting state —
            # it must not hold the bulb amber forever
            checks.append({"level": "info" if getattr(s, "shadow", False) else "warn",
                           "label": name,
                           "detail": "enabled but no accounts assigned"})
    weekday = now_et.weekday() < 5
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
                checks.append({"level": "bad", "label": name,
                               "detail": f"timer has not gated — the {fire_t.hour}:{fire_t.minute:02d} fire "
                                         "is not armed"})
            elif stage == "error":
                checks.append({"level": "bad", "label": name,
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
                detail = (f"{name} skipped today — its positions and orders were not synced "
                          f"at {checked_at}: unknown, never taken as flat")
            elif net:
                detail = (f"{name} skipped today — holds {int(net):+d} {sym} "
                          f"(manual position at {checked_at})")
            elif aid in unreadable:
                # the broker read failed and no cached position confirms one
                # either way — say so, rather than implying a known flat book
                detail = (f"{name} skipped today — position unknown, "
                          f"{len(orders.get(aid) or ())} working {sym} order(s) "
                          f"(manual, at {checked_at})")
            else:
                detail = (f"{name} skipped today — {len(orders.get(aid) or ())} "
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
        elif feed_deferred(now_et, {n: enabled[n] for n in bars}):
            checks.append({"level": "warn", "label": "Price feed",
                           "detail": "down — reconnects at 09:35 (no market-data requests around "
                                     "the 9:30 fire); " + ", ".join(bars) + " needs bars only later"})
        else:
            checks.append({"level": "bad", "label": "Price feed",
                           "detail": "down — " + ", ".join(bars) + " cannot see price"})
    tstrats = (timer_status or {}).get("strategies") or {}
    for name, s in enabled.items():
        status = engine.day_status(name)
        h, m = s.accept_until_et.split(":")
        after_window = now_et.time() > dt.time(int(h), int(m))
        if getattr(s, "kind", "straddle") == "bars":
            if status != "idle":
                checks.append({"level": "ok", "label": name, "detail": status})
            continue                     # a rule with no setup today is normal
        if getattr(s, "kind", "straddle") == "levels":
            if status != "idle":
                checks.append({"level": "ok", "label": name, "detail": status})
            continue                     # leveltimer journals every fire / skip / miss with its why
        # from the open, a self-fire straddle's own timer says what its day was
        # (09:21-09:30 has its own check above)
        told = (_timer_day(tstrats.get(name), status, s, cfg.armed)
                if weekday and getattr(s, "self_fire", False) and now_et.time() >= fire_time(s)
                else None)
        if told is not None:
            checks.append({"level": told[0], "label": name, "detail": told[1]})
        elif weekday and after_window and status == "idle":
            if s.gated:
                checks.append({"level": "warn", "label": name,
                               "detail": "no signal today — gated day (expected) "
                                         "or the pipe is broken"})
            else:
                checks.append({"level": "bad", "label": name,
                               "detail": "no signal arrived — this strategy "
                                         "trades every day"})
        elif status != "idle":
            checks.append({"level": "ok", "label": name, "detail": status})
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
               paper_client: httpx.AsyncClient | None = None) -> FastAPI:
    cfg = cfg or config_mod.load()
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

    def _in_gone_quiet(now_et, span=GONE_QUIET) -> bool:
        return now_et.weekday() < 5 and span[0] <= now_et.time() < span[1]

    _listed: dict[str, set[str]] = {}        # login key -> account names its last probe listed
    _add_lock = asyncio.Lock()               # one "add accounts" at a time

    def _refuse_adding_now() -> None:
        if _in_gone_quiet(engine.now_et()):
            raise HTTPException(409, "refused: accounts aren't added 09:20-09:35 ET on weekdays "
                                "(the 9:30 window) — try again after 09:35")

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
    engine.balance_history = lambda account: equity_by_day(account)
    # trading from the chart (spec 2026-09-26): views, guards, journaling
    desk = ChartDesk(cfg, engine, adapters, acct_status, timer_status=timer.status)
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
            # riding the old one, it would die at that token's expiry, maybe in 09:20-09:35
            await _feed_close("recycled onto the renewed market-data token before 09:20")
            f = None
        deferred = feed_deferred(now_et, strategies)
        if f is None or not f.connected:
            if deferred:
                return []      # no md (re)connect around the 9:30 fire: at 09:35, with history
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
        GONE_CONFIRM_S later confirms: _gone_step then unbooks and removes it (outside
        09:20-09:35). Never evidence: a failed, 429'd or empty sync (no listing), a login
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
        first sighting (never 09:10-09:35 ET), then -- confirmed -- unbook and remove
        (never 09:20-09:35 ET). The bookings are kept in case it comes back."""
        import time as _t
        if not _gone:
            return
        now_et = engine.now_et()
        for aid, g in list(_gone.items()):
            if aid not in cfg.accounts:
                _gone.pop(aid, None)
                continue
            if g["confirmed"]:
                if _in_gone_quiet(now_et):
                    continue
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
            if (t is None or t.done()) and _t.time() >= g["next_check"] \
                    and not _in_gone_quiet(now_et, GONE_CHECK_QUIET):
                g["next_check"] = _t.time() + GONE_CONFIRM_S
                _gone_tasks[aid] = asyncio.create_task(_gone_check(aid))

    async def _sync_paper() -> None:
        """Every chart-service paper account is an account of the desk's pool (assignable to an algo in
        + Assign) -- one per paper id, labelled "<name> (paper)". Added here, never by hand; removed only
        with the account on the Charts page (its adapter then fails to read the book and drops out of
        the readiness checks). Never adds during the 9:30 window, and a service that is down adds nothing."""
        if not (background or paper_client is not None) or _in_gone_quiet(engine.now_et()):
            return                   # a test app reaches no service it was not handed
        try:
            r = await paper_http.get("/api/paper/accounts")
            r.raise_for_status()
            rows = r.json()["accounts"]
        except Exception:  # noqa: BLE001 — the chart service is down: the adapters say so themselves
            return
        for row in rows:
            aid = str(row["id"])
            if aid in cfg.accounts:
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
        connected entry that can do it. Skipped for a user in a 429 cool-down and
        09:20-09:35 ET (the fire's socket carries only the fire)."""
        if _in_gone_quiet(engine.now_et()):
            return
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
                            record_equity(str(m["account"]), float(m["balance"]),
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

    async def _clock_loop():
        while True:
            try:
                await engine.clock_tick()
                now = engine.now_et()
                if should_fire_readiness(now, readiness_fired["date"]):
                    readiness_fired["date"] = now.date().isoformat()
                    r = compute_readiness(now, cfg, engine, acct_status,
                                          feed_status(), timer.status(), power_status())
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
        tasks = []
        if background:
            tasks = [asyncio.create_task(_clock_loop()),
                     asyncio.create_task(_broker_loop()),
                     asyncio.create_task(_equity_loop()),
                     asyncio.create_task(timer.loop()),
                     asyncio.create_task(level_timer.loop()),
                     asyncio.create_task(_feed_loop()),
                     asyncio.create_task(desk.run())]
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
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
    app.include_router(desk_api.trade_router(desk), prefix="/api/trade")
    app.include_router(desk_api.settings_router(desk))
    # Task 5b: every write needs an allowed Host/Origin and a JSON body (main app only)
    app.add_middleware(desk_api.WriteGuard, hosts=lambda: cfg.allowed_hosts)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")


    # ------------------------------------------------------------ dashboard
    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/status")
    async def status():
        import time as _t
        accounts = {}
        for aid, a in cfg.accounts.items():
            ad = adapters.get(aid)
            try:        # the adapters' caches only: a poll costs Tradovate nothing
                m = await ad.get_metrics() if ad else {"connected": False}
            except Exception as e:  # noqa: BLE001
                m = {"connected": False, "error": f"metrics: {e}"}
            s = acct_status.get(aid, {})
            if s.get("error") and not m.get("error"):
                m["error"] = s["error"]
            cooldown_s = max(0.0, _login_cooldown.get(aid, 0) - _t.time())
            accounts[aid] = {"label": a.label or a.account_name or aid,
                             "env": "paper" if a.paper else "live" if a.live else "demo",
                             "cooldown_s": round(cooldown_s, 1) if cooldown_s else 0, **m}
        live = live_metrics(state_dir() / "journal.jsonl")
        journal = []
        jp = state_dir() / "journal.jsonl"
        if jp.exists():
            journal = [json.loads(l) for l in
                       jp.read_text().splitlines()[-JOURNAL_TAIL:]][::-1]
        return {
            "armed": cfg.armed,
            "chart_trading": asdict(cfg.chart_trading),
            "et_now": engine.now_et().isoformat(timespec="seconds"),
            "readiness": compute_readiness(engine.now_et(), cfg, engine,
                                           acct_status, feed_status(),
                                           timer.status(), power_status()),
            "timer": timer.status(),
            "levels": level_timer.status(),
            "feed": feed_status(),
            "accounts": accounts,
            "notices": notices[::-1],      # newest first, one line each, page wording
            "book": cfg.book,
            "strategies": {
                name: {
                    "cfg": {"symbol": s.symbol, "qty": s.qty,
                            "offset_pts": s.offset_pts, "sl_pts": s.sl_pts,
                            "tp_pts": s.tp_pts, "cancel_et": s.cancel_et,
                            "flat_et": s.flat_et, "fire_et": s.fire_et,
                            "only_dates": list(s.only_dates), "enabled": s.enabled,
                            "gated": s.gated, "self_fire": s.self_fire,
                            "pine_file": getattr(s, "pine_file", ""),
                            "kind": getattr(s, "kind", "straddle"),
                            "shadow": getattr(s, "shadow", False),
                            "rule": getattr(s, "rule", ""),
                            "bar_minutes": getattr(s, "bar_minutes", 1),
                            "shape": s.shape, "fire_et": s.fire_et, "day_take": s.day_take,
                            "day_lock": s.day_lock, "target_take": s.target_take,
                            "size_tiers": s.size_tiers, "ack_open_loss": s.ack_open_loss},
                    "research": s.metrics,
                    "live": live.get(name),
                    "day_status": engine.day_status(name),
                    "killed": engine.killed_today(name),
                    "accounts": [{**vars(st), "check_it": engine.needs_check(st)}
                                 for st in engine.day_states(name)],
                } for name, s in cfg.strategies.items()
            },
            "journal": journal,
        }

    def _read_journal_records(jp: Path) -> list[dict]:
        """The blocking half of /api/journal: read the file and parse each line, off the
        event loop (asyncio.to_thread). A line that isn't valid JSON, or parses to
        something other than an object (a bare number/string/array), is skipped."""
        if not jp.exists():
            return []
        out = []
        for line in jp.read_text().splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                out.append(rec)
        return out

    @app.get("/api/journal")
    async def journal_query(date: str | None = None, event: str | None = None,
                            account: str | None = None, limit: int = 200):
        """Journal events, newest first, for a day (default today ET) -- unlike /api/status's
        fixed JOURNAL_TAIL preview, this one takes a date and filters, for a real read of what
        happened (the MCP desk_journal tool; the dashboard doesn't call this)."""
        limit = max(1, min(int(limit), 2000))
        day = date or engine.now_et().date().isoformat()
        jp = state_dir() / "journal.jsonl"
        records = await asyncio.to_thread(_read_journal_records, jp)
        out = []
        for rec in records:
            if str(rec.get("et", "")).split("T", 1)[0] != day:
                continue
            if event and rec.get("event") != event:
                continue
            if account and rec.get("account") != account:
                continue
            out.append(rec)
        out.reverse()
        return {"date": day, "count": len(out), "events": out[:limit]}

    @app.post("/api/arm")
    async def arm(request: Request):
        body = await request.json()
        cfg.armed = bool(body.get("armed"))
        config_mod.save(cfg)
        engine.journal("armed_toggled", armed=cfg.armed)
        return {"ok": True, "armed": cfg.armed}

    kill_lock_box: dict = {}

    def _kill_lock() -> asyncio.Lock:
        """The Kill's own lock, bound to the running loop (a TestClient and a
        bare asyncio.run each bring their own)."""
        loop = asyncio.get_running_loop()
        held = kill_lock_box.get("lock")
        if held is None or held[0] is not loop:
            held = kill_lock_box["lock"] = (loop, asyncio.Lock())
        return held[1]

    @app.post("/api/kill")
    async def kill():
        """Disarm, switch chart trading off, then cancel and flatten everything.

        Two Kills never overlap (second review, 2026-09-28): flatten_today reads
        each net position and market-sells it, so two at once on a slow broker
        could both sell. The disarm is immediate for every Kill -- it never waits
        -- and the broker work runs one Kill at a time: a second Kill waits for
        the first, then runs in full (a retry after a partial failure must still
        act)."""
        cfg.armed = False
        desk.disable(cause="kill")          # chart trading off too; never raises
        config_mod.save(cfg)
        # ... and never alongside a per-strategy Kill from the chart (engine.kill_strategy):
        # the broker work also holds every strategy's own kill lock
        async with _kill_lock(), engine.all_kill_locks():
            # every strategy's own orders first, with the proven per-order calls;
            # then the account-wide calls sweep up anything else
            strategies = await engine.flatten_today()
            results = {}
            for aid, ad in list(adapters.items()):
                r = {}
                for call in ("cancel_all", "flatten_all"):
                    try:
                        x = await getattr(ad, call)()
                        r[call] = {"ok": x.ok, "error": x.error}
                    except Exception as e:  # noqa: BLE001 — kill always finishes
                        r[call] = {"ok": False, "error": str(e)}
                results[aid] = r
            engine.journal("kill_switch", results=results, strategies=strategies)
        return {"ok": True, "armed": False, "results": results,
                "strategies": strategies}

    @app.post("/api/test-alert")
    async def test_alert(request: Request):
        if cfg.armed:
            return JSONResponse({"ok": False, "reason": "disarm first — test "
                                 "alerts only run in dry-run mode"}, 409)
        body = await request.json()
        name = str(body.get("strategy") or "")
        s = cfg.strategies.get(name)
        if s is None:
            raise HTTPException(404, f"unknown strategy {name!r}")
        base = float(body.get("base") or 24500.0)
        payload = {"strategy": name, "upper": base + s.offset_pts,
                   "lower": base - s.offset_pts}
        out = await engine.handle_alert(payload, force_window=True,
                                        source="test")
        return {"sent": payload, "result": out}

    # ------------------------------------------------------------ setup
    @app.get("/api/logins")
    async def logins():
        in_use = {a.keyring_key for a in cfg.accounts.values()}
        out = []
        for key in secrets_store._load_all():
            out.append({"key": key, "label": (key.split(":", 2)[-1] or key).upper(),
                        "env": _key_env(key),
                        "in_use": key in in_use})
        return {"logins": out}

    @app.post("/api/logins/delete")
    async def logins_delete(request: Request):
        body = await request.json()
        key = str(body.get("key") or "")
        if any(a.keyring_key == key for a in cfg.accounts.values()):
            raise HTTPException(409, "that login is in use by an account")
        secrets_store.delete_credentials(key)
        return {"ok": True}

    @app.post("/api/connect")
    async def connect(request: Request):
        """Validate a login (saved or new; demo by default, live on request)
        with a throwaway probe and return every account under it. Nothing is
        added to the pool yet — that is /api/accounts/add, one per account."""
        # the probe is a real login that re-rolls the login's shared token: never
        # in the 9:30 window, like the adds it leads to
        _refuse_adding_now()
        body = await request.json()
        env = "live" if str(body.get("env") or "").lower() == "live" else "demo"
        saved = str(body.get("saved_key") or "")
        if saved:
            if not secrets_store.get_credentials(saved):
                raise HTTPException(404, f"no saved login {saved!r}")
            key, env = saved, _key_env(saved)
        else:
            username = str(body.get("username") or "").strip()
            # newlines/CRs are never valid in a password but ride along with
            # clipboard pastes; spaces are preserved (could be legitimate)
            password = str(body.get("password") or "").strip("\r\n")
            if not username or not password:
                raise HTTPException(400, "username and password required")
            key = f"tv:{env}:{username.lower()}"
            secrets_store.set_credentials(key, username=username,
                                          password=password)
        # the probe is a real login: it goes through the user's budget like every other
        # (a 429 cool-down or the hourly cap refuses it; the wizard shows why). It is the
        # ONE login of an "add several" -- the entries then ride the token it leaves on
        # the shared auth (reconnect, no login).
        login_id = (key, env == "live")
        why = budget.blocked(key, first=login_id not in _login_first_spent, manual=True)
        if why:
            return {"ok": False, "error": why, "key": key}
        _login_first_spent.add(login_id)
        budget.record_login(key)
        probe = adapter_factory("probe", config_mod.AccountCfg(
            keyring_key=key, live=(env == "live")))
        try:
            await probe.connect()
            accounts = probe.list_accounts() if hasattr(probe, "list_accounts") else []
            budget.login_result(key)
        except Exception as e:  # noqa: BLE001 — surface to the wizard
            budget.login_result(key, e)
            return {"ok": False, "error": str(e), "key": key}
        finally:
            with contextlib.suppress(Exception):
                await probe.close()
        _listed[key] = {str(a.get("name") or "").lower() for a in accounts}
        accounts = [{**a, "on_desk": _on_desk(key, str(a.get("name") or "")) is not None}
                    for a in accounts]
        return {"ok": True, "key": key, "env": env, "accounts": accounts}

    @app.post("/api/accounts/add")
    async def accounts_add(request: Request):
        """Add one broker account to the pool and connect it. Demo or live is
        the login's (verified) env — never a client flag. A new account is
        never assigned to a strategy: it trades only once the user assigns it."""
        body = await request.json()
        key = str(body.get("key") or "")
        account_name = str(body.get("account_name") or "").strip()
        _refuse_adding_now()
        if not key or not secrets_store.get_credentials(key):
            raise HTTPException(400, "unknown login key")
        if not account_name:
            raise HTTPException(400, "account_name required")
        aid = account_name.lower()
        live = _key_env(key) == "live"
        cfg.accounts[aid] = config_mod.AccountCfg(
            keyring_key=key, account_name=account_name, live=live,
            label=str(body.get("label") or account_name))
        config_mod.save(cfg)
        engine.journal("account_added", account=aid, live=live)
        try:
            await _connect_account(aid, manual=True)
        except Exception as e:  # noqa: BLE001
            _connect_failed(aid, e)
            return {"ok": True, "account": aid, "connected": False,
                    "error": acct_status[aid]["error"]}
        return {"ok": True, "account": aid, "connected": True}

    @app.post("/api/accounts/add-many")
    async def accounts_add_many(request: Request):
        """Add several accounts of ONE login (the wizard's checkboxes). Each becomes a
        normal entry pinned to its own broker account -- never booked, never assigned to
        a strategy: booking stays the account holder's call. One at a time, on the shared
        token the wizard's probe left (reconnect, no login): N accounts cost the probe's
        ONE login, and the batch stops at the first failure that could spend another
        (a login refused, a socket error), so it never turns into N logins. Refused
        09:20-09:35 ET on weekdays, before and between accounts.
        Answers one row per requested account: added (connected or not, with why),
        exists (already on the desk) or failed (with the reason)."""
        body = await request.json()
        key = str(body.get("key") or "")
        raw = body.get("accounts")
        if not isinstance(raw, list) or not raw or not all(isinstance(n, str) for n in raw):
            raise HTTPException(400, "accounts: a list of account names required")
        names: list[str] = []
        for n in raw:
            n = n.strip()
            if n and n.lower() not in {x.lower() for x in names}:
                names.append(n)
        if not names:
            raise HTTPException(400, "accounts: a list of account names required")
        if len(names) > ADD_MANY_MAX:
            raise HTTPException(400, f"at most {ADD_MANY_MAX} accounts at a time")
        _refuse_adding_now()
        if not key or not secrets_store.get_credentials(key):
            raise HTTPException(400, "unknown login key")
        listed = _listed.get(key)
        if listed is None:
            raise HTTPException(409, "look this login's accounts up first (Find my accounts)")
        live = _key_env(key) == "live"
        rows: list[dict] = []
        stop = ""                    # why the rest were not tried
        async with _add_lock:
            for name in names:
                low = name.lower()
                row = {"name": name}
                rows.append(row)
                if not stop and _in_gone_quiet(engine.now_et()):
                    stop = "adding stops 09:20-09:35 ET (the 9:30 window)"
                if stop:
                    row.update(status="failed", error=f"not tried — {stop}")
                    continue
                if low not in listed:
                    row.update(status="failed", error="not on this login")
                    continue
                have = _on_desk(key, name)
                if have is not None:
                    row.update(status="exists", id=have)
                    continue
                if low in cfg.accounts:
                    row.update(status="failed", error="another entry on the desk already "
                               "uses this id")
                    continue
                cfg.accounts[low] = config_mod.AccountCfg(
                    keyring_key=key, account_name=name, live=live, label=name)
                config_mod.save(cfg)
                engine.journal("account_added", account=low, live=live, batch=True)
                row.update(status="added", id=low)
                try:
                    row["mode"] = await _connect_account(low, manual=True)
                    row["connected"] = True
                    if row["mode"] == "login":
                        # the shared token did not carry it, so it spent a login: the
                        # next one could too -- stop here, the rest can be added again
                        stop = "the previous account had to log in again"
                except Exception as e:  # noqa: BLE001 — recorded, reported per account
                    _connect_failed(low, e)
                    row["connected"] = False
                    row["error"] = str((acct_status.get(low) or {}).get("error") or e)[:200]
                    if not isinstance(e, AccountNotOnLogin):
                        stop = "the connection failed (" + str(e)[:120] + ")"
        counts = {s: sum(1 for r in rows if r["status"] == s)
                  for s in ("added", "exists", "failed")}
        engine.journal("accounts_added_batch", login=key, live=live, **counts)
        return {"ok": not counts["failed"], "results": rows, **counts}

    @app.post("/api/strategy")
    async def strategy_toggle(request: Request):
        """Turn one strategy on or off — off means it ignores everything:
        no signals accepted, the timer skips it, readiness skips it."""
        body = await request.json()
        name = str(body.get("strategy") or "")
        if name not in cfg.strategies:
            raise HTTPException(404, f"unknown strategy {name!r}")
        cfg.strategies[name].enabled = bool(body.get("enabled"))
        config_mod.save(cfg)
        engine.journal("strategy_toggled", strategy=name,
                       enabled=cfg.strategies[name].enabled)
        return {"ok": True, "strategy": name,
                "enabled": cfg.strategies[name].enabled}

    @app.post("/api/strategy-flatten")
    async def strategy_flatten(request: Request):
        """Flatten one strategy everywhere it acted today AND switch it off."""
        body = await request.json()
        name = str(body.get("strategy") or "")
        if name not in cfg.strategies:
            raise HTTPException(404, f"unknown strategy {name!r}")
        results = await engine.flatten_strategy(name)
        cfg.strategies[name].enabled = False
        config_mod.save(cfg)
        engine.journal("strategy_toggled", strategy=name, enabled=False,
                       cause="manual_flatten")
        return {"ok": True, "enabled": False, "results": results}

    @app.post("/api/accounts/reconnect")
    async def accounts_reconnect(request: Request):
        """Manual reconnect for one account (or all). Clears the account's retry
        cooldown and the user's login backoff -- the user is explicitly asking --
        but never a 429 cool-down or the hourly login cap. One attempt each: a
        parked account (not on its login) is retried once and stays parked if it
        still is not there. Reconciles positions afterwards."""
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 — empty body = all accounts
            body = {}
        only = str(body.get("account") or "")
        targets = [only] if only else list(cfg.accounts)
        results = {}
        for aid in targets:
            if aid not in cfg.accounts:
                results[aid] = {"ok": False, "error": "unknown account"}
                continue
            _login_cooldown.pop(aid, None)
            try:     # one attempt: a parked account stays parked if it fails again
                mode = await _connect_account(aid, manual=True)
                _login_cooldown.pop(aid, None)
                results[aid] = {"ok": True, "mode": mode}
            except Exception as e:  # noqa: BLE001 — surface the reason
                _connect_failed(aid, e)
                results[aid] = {"ok": False, "error": acct_status[aid]["error"][:200]}
        engine.journal("manual_reconnect", results=results)
        if str(body.get("source") or "") == "mcp":
            engine.journal("mcp_action", tool="account_reconnect", account=only or "all",
                           results=results)
        return {"ok": all(r["ok"] for r in results.values()) if results else False,
                "results": results}

    @app.post("/api/accounts/remove")
    async def accounts_remove(request: Request):
        """Remove an account from the pool: unassign it from every strategy,
        close its adapter, drop it. Refused (409) unless the adapter is
        connected with its caches seeded, its cached view shows no position
        in any symbol and no working order, and today's day-states show it
        neither placing, placed nor live. An MCP-sourced request is also
        refused 09:10-09:35 ET on weekdays, server-side (never only the
        tool's own client-side check). This is NOT the path the login-loop
        fix's automatic gone-account removal takes (_gone_step -> _drop_account
        directly) -- that keeps removing a truly gone account on its own terms."""
        body = await request.json()
        aid = str(body.get("account") or "")
        if aid not in cfg.accounts:
            raise HTTPException(404, f"unknown account {aid!r}")
        if cfg.accounts[aid].paper:
            raise HTTPException(409, "a paper account is managed on the Charts page — remove it there")
        from_mcp = str(body.get("source") or "") == "mcp"
        if from_mcp and _in_gone_quiet(engine.now_et(), GONE_CHECK_QUIET):
            raise HTTPException(409, "refused: not 09:10-09:35 ET on weekdays "
                                "(the 9:30 window) — try again after 09:35")
        ad = adapters.get(aid)
        readable = (ad is not None and ad.connected
                    and getattr(ad, "caches_seeded", False))
        if readable:
            view = ad.trade_view()
            if view is None:
                raise HTTPException(409, "can't read this adapter's cached view — "
                                    "try again once it's connected")
            if view.get("positions"):
                raise HTTPException(409, "account has an open position — flatten first")
            if view.get("orders"):
                raise HTTPException(409, "account has a working order — cancel it first")
        elif from_mcp:
            # Claude never removes an account whose state it can't read
            raise HTTPException(409, "account not connected (or its caches haven't "
                                "seeded yet) — try again once it's connected")
        # else: the account holder's own Remove (the desk page confirms it) of an
        # account the desk can't read -- a blown / closed / broken-login entry.
        # Their call: it has nothing the desk can manage anyway.
        for st in engine.day_states_for_account(aid):
            if st.status in ("placing", "placed", "live"):
                raise HTTPException(409, f"account is {st.status} in "
                                    f"{st.strategy!r} today — wait for it to finish")
        await _drop_account(aid)
        if from_mcp:
            engine.journal("mcp_action", tool="account_remove", account=aid)
        return {"ok": True, "removed": aid}

    @app.get("/api/diag-permissions")
    async def diag_permissions(account: str):
        """Read-only: what the broker says this login may do. No orders."""
        ad = adapters.get(account)
        if ad is None or not ad.connected:
            raise HTTPException(409, "account not connected")
        ws = getattr(ad, "_ws", None)
        if ws is None:
            raise HTTPException(409, "no socket")
        out: dict = {}
        try:
            sync = await ad._ws.user_sync()
            out["userPlugins"] = sync.get("userPlugins")
            out["accountRiskStatuses"] = sync.get("accountRiskStatuses")
            out["userProperties"] = sync.get("userProperties")
            out["users"] = [{k: v for k, v in u.items()
                             if k in ("id", "name", "status", "professional",
                                      "organizationId", "userType")}
                            for u in (sync.get("users") or [])]
        except Exception as e:  # noqa: BLE001
            out["sync_error"] = str(e)
        for label, ep in (("tradingPermissions", "tradingPermission/list"),):
            try:
                out[label] = await ws.request(ep, "")
            except Exception as e:  # noqa: BLE001
                out[label] = f"ERROR: {e}"
        return out

    @app.post("/api/selftest-order")
    async def selftest_order(request: Request):
        """Prove the REAL order path end to end: place one bracketed stop
        entry far from the market, confirm the broker accepted it, then
        cancel it. qty is forced to 1 and the offset has a hard floor, so
        it cannot fill. Parent is a Day order, so even a failed cancel
        expires at the session end."""
        body = await request.json()
        aid = str(body.get("account") or "")
        if aid not in cfg.accounts:
            raise HTTPException(404, f"unknown account {aid!r}")
        ad = adapters.get(aid)
        if ad is None or not ad.connected:
            raise HTTPException(409, "account not connected")
        symbol = str(body.get("symbol") or "NQ")
        offset = max(20.0, float(body.get("offset_pts") or 1000))
        plain = bool(body.get("plain"))      # single order, no bracket
        ref = body.get("ref_price")
        if ref is None:
            raise HTTPException(400, "ref_price required (a recent market price)")
        entry = round(float(ref) + offset, 2)
        trace: dict = {"symbol": symbol, "entry_stop": entry, "qty": 1,
                       "offset_pts": offset, "mode": "plain" if plain else "bracket"}
        req = OrderRequest(symbol=symbol, side="Buy", qty=1, order_type="Stop",
                           price=entry,
                           stop_price=None if plain else entry - 5,
                           tp_price=None if plain else entry + 15,
                           text="homebase:selftest")
        if str(body.get("transport") or "ws") == "rest":
            # Same account, same token, completely different transport — tells
            # us whether the refusal is the socket path or the account itself.
            import urllib.request, urllib.error  # noqa: PLC0415
            host = "live" if cfg.accounts[aid].live else "demo"
            url = f"https://{host}.tradovateapi.com/v1/order/placeorder"
            payload = {"accountSpec": getattr(ad, "_acct_name", ""),
                       "accountId": getattr(ad, "_acct_num", 0),
                       "action": "Buy", "symbol": TradovateMD.resolve(symbol),
                       "orderQty": 1, "orderType": "Stop", "stopPrice": entry,
                       "timeInForce": "Day", "isAutomated": True,
                       "text": "homebase:selftest"}
            tok = getattr(getattr(ad, "_auth", None), "access_token", "")
            rq = urllib.request.Request(
                url, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json",
                         "Accept": "application/json",
                         "Authorization": f"Bearer {tok}"})
            def _post():
                try:
                    with urllib.request.urlopen(rq, timeout=20) as resp:
                        return resp.status, resp.read().decode()[:600]
                except urllib.error.HTTPError as e:
                    return e.code, e.read().decode()[:600]
                except Exception as e:  # noqa: BLE001
                    return -1, str(e)[:300]
            st, txt = await asyncio.to_thread(_post)
            trace["rest"] = {"url": url, "http_status": st, "response": txt,
                             "sent": {k: v for k, v in payload.items()
                                      if k != "accountSpec"}}
            engine.journal("selftest_order_rest", account=aid, **trace["rest"])
            return {"ok": st == 200, "trace": trace}
        r = await ad.place_order(req) if plain else await ad.place_bracket(req)
        trace["placed"] = {"ok": r.ok, "order_id": r.order_id, "error": r.error,
                           "raw": r.raw}      # full broker response, verbatim
        try:
            if r.ok and r.order_id:
                await asyncio.sleep(1.5)
                try:
                    m = await ad.get_metrics()
                    trace["working_orders_after_place"] = m.get("working_orders")
                    trace["net_position"] = await ad.get_net_position(symbol)
                except Exception as e:  # noqa: BLE001
                    trace["readback_error"] = str(e)
        finally:
            if r.ok and r.order_id:
                c = await ad.cancel_order_by_id(r.order_id)
                trace["cancelled"] = {"ok": c.ok, "error": c.error}
                if not c.ok:
                    ca = await ad.cancel_all()
                    trace["cancel_all_fallback"] = {"ok": ca.ok, "error": ca.error}
                await asyncio.sleep(1.0)
                try:
                    m2 = await ad.get_metrics()
                    trace["working_orders_after_cancel"] = m2.get("working_orders")
                    # safety: a close-to-market test stop could fill before the
                    # cancel lands — never leave a position behind
                    net = await ad.get_net_position(symbol)
                    trace["net_after_cancel"] = net
                    if net:
                        f = await ad.flatten_all()
                        trace["emergency_flatten"] = {"ok": f.ok, "error": f.error}
                except Exception as e:  # noqa: BLE001
                    trace["final_readback_error"] = str(e)
        engine.journal("selftest_order", account=aid, **trace)
        return {"ok": bool(r.ok), "trace": trace}

    @app.post("/api/book")
    async def set_book(request: Request):
        """Set one strategy's assignments: [{account, qty}, ...]."""
        body = await request.json()
        name = str(body.get("strategy") or "")
        if name not in cfg.strategies:
            raise HTTPException(404, f"unknown strategy {name!r}")
        rows = []
        for a in body.get("assignments") or []:
            aid, qty = str(a.get("account") or ""), int(a.get("qty") or 0)
            if aid not in cfg.accounts:
                raise HTTPException(400, f"unknown account {aid!r}")
            if qty > 0:
                rows.append({"account": aid, "qty": qty})
        cfg.book[name] = rows
        config_mod.save(cfg)
        engine.journal("book_updated", strategy=name, assignments=rows)
        return {"ok": True, "book": cfg.book}

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

    @app.get("/api/pine")
    async def pine_source(strategy: str):
        """The strategy's committed Pine source (research artifact)."""
        s = cfg.strategies.get(strategy)
        fname = getattr(s, "pine_file", "") if s else ""
        p = STATIC.parent / "research" / fname if fname else None
        if not p or not p.exists():
            return {"source": None}
        return {"name": fname, "source": p.read_text()}

    @app.get("/api/strategy-live")
    async def strategy_live(strategy: str):
        """One strategy's live record — calendar days, metrics, trade log —
        summed across every account running it, from real fills only."""
        if strategy not in cfg.strategies:
            raise HTTPException(404, f"unknown strategy {strategy!r}")
        return strategy_live_detail(state_dir() / "journal.jsonl", strategy, cfg)

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
        d = daily_pnl(account, month)
        return {"account": account, "month": month, **d,
                "history_since": next(iter(equity_by_day(account)), None)}

    return app


# python.org macOS builds: the CA shim lives in homebase/__init__.py
assert os.environ.get("SSL_CERT_FILE") or True
app = create_app()
