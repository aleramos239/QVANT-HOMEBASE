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
Its parts (readiness, the bars feed, the accounts, the loops and the lifespan) live in homebase/desk_app/.

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

from .desk import bothistory, equity
from . import config as config_mod
from .store import secrets_store
from .broker.base import AccountNotOnLogin, BrokerAdapter, OrderRequest
from .broker.login_budget import LoginBudget, LoginDeferred, is_rate_limited
from .broker.paper import BASE_URL as PAPER_URL, PaperAdapter
from .broker.tradovate import RENEW_EARLY_FROM, RENEW_EARLY_UNTIL, TradovateAdapter
from .desk.engine import Engine, _hhmm
from .data.feed import MarketFeed
from .data.marketdata import TradovateMD
from .desk.rules import RULES
from .desk.metrics import live_metrics, strategy_live_detail
from .paths import state_dir
from .desk.leveltimer import LevelTimer
from .desk.timer import SelfTimer, fire_clock, fire_said, fire_time, miss_why, off_anchor, schedule
from .desk import desk_api
from . import routes
from .desk import inactive as inactive_mod
from .desk import labdesk as labdesk_mod
from .desk.trading import ChartDesk
from .desk_app import background as background_mod, barsfeed, brokers
# every name this module had before the split stays importable from here (homebase.server stays the desk's front door);
# the constants are copies: to change one for the desk, set it in its homebase.desk_app module
from .desk_app.background import CLOCK_INTERVAL_S, EQUITY_INTERVAL_S, SIBLING_INTERVAL_S  # noqa: F401
from .desk_app.barsfeed import (FEED_FROM, FEED_RETRY_S, FEED_UNTIL, _rides_older_token,  # noqa: F401
                                feed_recycle_window, feed_window)
from .desk_app.brokers import (GONE_CHECK_TIMEOUT_S, GONE_CONFIRM_S, INPLACE_RETRY_S, NOTICES_KEPT,  # noqa: F401
                               RECONNECT_INTERVAL_S, _key_env, _md_expiry_of, _md_token_of, build_adapter,
                               build_feed, md_source)
from .desk_app.readiness import (READINESS_FROM, _POWER_CACHE, _plus_min, _timer_day, compute_readiness,  # noqa: F401
                                 power_status, should_fire_readiness)

STATIC = Path(__file__).resolve().parent / "static"
ADD_MANY_MAX = 60           # accounts in one "add several" (a prop firm hands out ~20)
JOURNAL_TAIL = 60


def _equity_path() -> Path:
    return state_dir() / "equity.jsonl"


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
    if lab_on:      # a leftover charts team file (deskgroups.json) joins the Desk's teams once, then is renamed .retired
        from .desk.engine_groups import retire
        from .labrun import store as lab_store
        leftover = lab_store.root().parent / "deskgroups.json"
        try:
            engine.adopt_teams(leftover)
            retire(leftover)
        except Exception as e:  # noqa: BLE001 -- the desk must still start; the file stays for the next start
            print(f"homebase: adopting {leftover} failed: {e!r}", file=sys.stderr)
    acct_status: dict[str, dict] = {}
    paper_http = paper_client or httpx.AsyncClient(base_url=PAPER_URL, timeout=5.0)   # the paper accounts list
    # logins are budgeted per Tradovate USER (the login key), never per entry: five
    # entries on one Apex user each falling back to a login ran it into 429 (2026-09-29)
    budget = login_budget or LoginBudget()
    budget.journal = engine.journal
    def _md_factory():
        key, env, provider = md_source(cfg, adapters)
        return TradovateMD(key, env, token_provider=provider)

    timer = SelfTimer(cfg, engine, md_factory=_md_factory)
    # the "levels" strategies (NQ prop algos): their own clock, their own market-data socket, and the
    # day_take price watcher; target_take reads the desk's daily balance record
    level_timer = LevelTimer(cfg, engine, md_factory=_md_factory)
    engine.balance_history = lambda account: equity.equity_by_day(_equity_path(), account)
    try:    # the prop rules the engine's first prepare of the day imports (load_rules): loaded now, not in a fire
        from .backtest import propsim  # noqa: F401
    except Exception:  # noqa: BLE001  -- as before: that import then fails in the fire, and the engine journals why
        pass
    # trading from the chart (spec 2026-09-26): views, guards, journaling
    desk = ChartDesk(cfg, engine, adapters, acct_status, timer_status=timer.status)
    # promoted Lab strategies (kind "lab"): limits, book checks, the switch, Remove, the status block (labdesk.py)
    labdesk = labdesk_mod.LabDesk(cfg, engine, adapters, paused=desk.views_paused, on=lab_on)
    journal_cache = bothistory.JournalCache()    # the journal parsed once: /api/status, /api/journal, /api/strategy-live
    feed = barsfeed.make(cfg=cfg, engine=engine, adapters=adapters, feed_factory=feed_factory)
    kill_lock_box: dict = {}

    def _kill_lock() -> asyncio.Lock:
        """The Kill's own lock, bound to the running loop (a TestClient and a
        bare asyncio.run each bring their own)."""
        loop = asyncio.get_running_loop()
        held = kill_lock_box.get("lock")
        if held is None or held[0] is not loop:
            held = kill_lock_box["lock"] = (loop, asyncio.Lock())
        return held[1]
    acc = brokers.make(cfg=cfg, engine=engine, adapters=adapters, acct_status=acct_status, budget=budget, desk=desk,
                       paper_http=paper_http, paper_client=paper_client, background=background,
                       adapter_factory=adapter_factory, _kill_lock=_kill_lock)
    lifespan = background_mod.make_lifespan(
        cfg=cfg, engine=engine, adapters=adapters, acct_status=acct_status, timer=timer, level_timer=level_timer,
        desk=desk, labdesk=labdesk, paper_http=paper_http, background=background, state_dir=lambda: state_dir(),
        _equity_path=_equity_path, _refresh_snapshots=acc.refresh_snapshots, _broker_loop=acc.broker_loop,
        feed_status=feed.status, _feed_loop=feed.loop, _feed_close=feed.close)

    app = FastAPI(title="Ramos Quant Homebase", lifespan=lifespan)
    app.state.engine = engine
    app.state.cfg = cfg
    app.state.adapters = adapters
    app.state.feed_step = feed.step
    app.state.inactive_sweep = lambda now_et=None: inactive_mod.sweep(cfg, engine, now_et or engine.now_et())
    app.state.sync_paper = acc.sync_paper
    # test-only hooks onto the broker reconnect loop (never called by the
    # app itself outside `background=True`'s lifespan task)
    app.state.connect_account = acc.connect_account
    app.state.broker_loop = acc.broker_loop
    app.state.login_cooldown = acc.login_cooldown
    app.state.login_budget = budget
    app.state.parked = acc.parked
    app.state.gone = acc.gone
    app.state.login_uid = acc.login_uid
    app.state.gone_step = acc.gone_step
    app.state.drop_account = acc.drop_account
    app.state.connect_failed = acc.connect_failed
    app.state.refresh_snapshots = acc.refresh_snapshots
    app.state.notices = acc.notices
    app.state.feed_box = feed.box
    app.state.desk = desk
    app.state.labdesk = labdesk
    app.include_router(desk_api.trade_router(desk), prefix="/api/trade")
    app.include_router(desk_api.labdesk_router(labdesk), prefix="/api/lab")   # the Lab runner's door (its own gate and key)
    app.include_router(desk_api.settings_router(desk))
    # Task 5b: every write needs an allowed Host/Origin and a JSON body (main app only)
    app.add_middleware(desk_api.WriteGuard, hosts=lambda: cfg.allowed_hosts)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    # ------------------------------------------------------------ the routes (homebase/routes/, one module per concern)
    routes.status.register(app, JOURNAL_TAIL=JOURNAL_TAIL, STATIC=STATIC, _login_cooldown=acc.login_cooldown,
                                acct_status=acct_status, adapters=adapters, cfg=cfg,
                                compute_readiness=compute_readiness, engine=engine, feed_status=feed.status,
                                journal_cache=journal_cache, labdesk=labdesk, level_timer=level_timer,
                                notices=acc.notices, power_status=power_status, state_dir=lambda: state_dir(), timer=timer)
    routes.deploy.register(app, STATIC=STATIC)
    routes.health.register(app, state_dir=lambda: state_dir())
    routes.control.register(app, _kill_lock=_kill_lock, adapters=adapters, cfg=cfg, desk=desk, engine=engine)
    routes.accounts.register(app, ADD_MANY_MAX=ADD_MANY_MAX, _add_lock=acc.add_lock, _connect_account=acc.connect_account,
                                  _connect_failed=acc.connect_failed, _drop_account=acc.drop_account, _key_env=_key_env,
                                  _listed=acc.listed, _login_cooldown=acc.login_cooldown,
                                  _login_first_spent=acc.login_first_spent, _on_desk=acc.on_desk, acct_status=acct_status,
                                  adapter_factory=adapter_factory, adapters=adapters, budget=budget, cfg=cfg,
                                  engine=engine, paper_http=paper_http)
    routes.strategies.register(app, cfg=cfg, engine=engine, labdesk=labdesk)
    routes.groups.register(app, engine=engine)
    routes.setup.register(app, cfg=cfg, engine=engine, labdesk=labdesk)
    routes.lab.register(app, labdesk=labdesk)
    routes.records.register(app, STATIC=STATIC, _equity_path=_equity_path, adapters=adapters, cfg=cfg,
                                 journal_cache=journal_cache, state_dir=lambda: state_dir())

    return app


# python.org macOS builds: the CA shim lives in homebase/__init__.py
assert os.environ.get("SSL_CERT_FILE") or True
app = create_app()
