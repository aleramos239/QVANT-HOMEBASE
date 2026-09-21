"""The homebase server: signals in, the book out.

    POST /hook               TradingView webhook (shared secret in payload)
    GET  /                   dashboard
    GET  /api/status         everything the dashboard renders
    POST /api/arm            {"armed": true|false} — the master switch
    POST /api/kill           cancel + flatten EVERY account + disarm
    POST /api/test-alert     synthetic dry-run signal; REFUSED while armed
    POST /api/connect        validate a DEMO login, return its accounts
    POST /api/accounts/add   add one broker account to the pool
    POST /api/book           set a strategy's account assignments
    GET  /api/tv-setup       webhook URL/secret + per-strategy alert steps
    POST /api/hook-url       record the tunnel's public origin
    GET  /api/logins (+delete), GET /api/calendar

Binds to localhost; the ONLY tunneled surface is the hook-only port.
Runs fine with zero accounts: everything reports its own state loudly and
the engine still validates + journals (dry run).
"""
from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config as config_mod
from . import secrets_store
from .broker.base import BrokerAdapter, OrderRequest
from .broker.tradovate import TradovateAdapter
from .engine import Engine
from .marketdata import TradovateMD
from .metrics import live_metrics, strategy_live_detail
from .paths import state_dir
from .timer import SelfTimer

STATIC = Path(__file__).resolve().parent / "static"
CLOCK_INTERVAL_S = 5
RECONNECT_INTERVAL_S = 5   # cheap now: reconnects reuse the token
EQUITY_INTERVAL_S = 60
JOURNAL_TAIL = 60
READINESS_FROM = (9, 25)


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


def compute_readiness(now_et, cfg: config_mod.AppCfg, engine,
                      acct_status: dict) -> dict:
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
    checks.append({"level": "ok" if cfg.webhook_secret else "bad",
                   "label": "Webhook secret",
                   "detail": "set" if cfg.webhook_secret else "missing"})
    enabled = {n: s for n, s in cfg.strategies.items() if s.enabled}
    for name, s in enabled.items():
        if not config_mod.assignments(cfg, name):
            checks.append({"level": "warn", "label": name,
                           "detail": "enabled but no accounts assigned"})
    weekday = now_et.weekday() < 5
    for name, s in enabled.items():
        status = engine.day_status(name)
        h, m = s.accept_until_et.split(":")
        after_window = now_et.time() > dt.time(int(h), int(m))
        if weekday and after_window and status == "idle":
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
    checks.append({"level": "info", "label": "Mode",
                   "detail": "ARMED — signals place real orders" if cfg.armed
                   else "shadow — signals journal only"})
    return {"ready": not any(c["level"] == "bad" for c in checks),
            "checks": checks}


def should_fire_readiness(now_et, fired_date: str | None) -> bool:
    if now_et.weekday() >= 5 or fired_date == now_et.date().isoformat():
        return False
    t = now_et.time()
    return t.hour == READINESS_FROM[0] and t.minute >= READINESS_FROM[1]


def build_adapter(account_id: str, a: config_mod.AccountCfg) -> BrokerAdapter:
    env = "live" if a.live else "demo"
    sel = {"account_name": a.account_name} if a.account_name else None
    return TradovateAdapter(account_id, env=env, keyring_key=a.keyring_key,
                            account_selector=sel)


def create_app(cfg: config_mod.AppCfg | None = None,
               adapters: dict[str, BrokerAdapter] | None = None,
               *, background: bool = True,
               adapter_factory=build_adapter) -> FastAPI:
    cfg = cfg or config_mod.load()
    adapters: dict[str, BrokerAdapter] = adapters if adapters is not None else {}
    engine = Engine(cfg, adapters)
    acct_status: dict[str, dict] = {}

    def _md_token() -> str:
        """The md token from any already-connected adapter — no extra login."""
        for ad in adapters.values():
            auth = getattr(ad, "_auth", None)
            tok = getattr(getattr(auth, "tokens", None), "md_access_token", "")
            if tok and ad.connected:
                return tok
        return ""

    def _md_factory():
        for a in cfg.accounts.values():
            if a.keyring_key:
                return TradovateMD(a.keyring_key,
                                   "live" if a.live else "demo",
                                   token_provider=_md_token)
        raise RuntimeError("no accounts configured for market data")

    timer = SelfTimer(cfg, engine, md_factory=_md_factory)

    async def _connect_account(aid: str, force_login: bool = False) -> str:
        """(Re)connect one account. Prefers an in-place reconnect on the token
        it already holds — no login spent — and only falls back to a full
        login. A drop used to cost a full login every time: ~20/hour on a
        sleeping laptop against Tradovate's ~5/hour limit."""
        a = cfg.accounts[aid]
        ad = adapters.get(aid)
        if ad is None:
            ad = adapters[aid] = adapter_factory(aid, a)
        mode = "login"
        has_token = bool(getattr(getattr(ad, "_auth", None), "tokens", None))
        if has_token and not force_login and hasattr(ad, "reconnect"):
            try:
                await ad.reconnect()
                mode = "reconnect"
            except Exception as e:  # noqa: BLE001 — fall back to a real login
                engine.journal("reconnect_fell_back_to_login", account=aid,
                               error=str(e)[:200])
                await ad.connect()
        else:
            await ad.connect()
        await ad.observe_fills(engine.on_fill)
        acct_status[aid] = {"connected": True, "error": None}
        engine.journal("broker_connected", account=aid,
                       broker_account=a.account_name, mode=mode)
        try:
            await engine.reconcile_account(aid)
        except Exception as e:  # noqa: BLE001 — never block the connect on it
            engine.journal("reconcile_error", account=aid, error=str(e)[:200])
        return mode

    _login_cooldown: dict[str, float] = {}   # account id -> unix ts of next try

    async def _broker_loop():
        import time as _t
        while True:
            for aid in list(cfg.accounts):
                ad = adapters.get(aid)
                if ad is not None and ad.connected:
                    continue
                if _t.time() < _login_cooldown.get(aid, 0):
                    continue
                try:
                    await _connect_account(aid)
                    _login_cooldown.pop(aid, None)
                except Exception as e:  # noqa: BLE001 — report, back off
                    msg = str(e)
                    acct_status[aid] = {"connected": False, "error": msg}
                    # NEVER hammer the login endpoint: auth rejections and
                    # rate-limit tickets wait 30 min; anything else 5 min.
                    slow = ("Login failed" in msg or "p-ticket" in msg
                            or "p-captcha" in msg)
                    _login_cooldown[aid] = _t.time() + (1800 if slow else 300)
            await asyncio.sleep(RECONNECT_INTERVAL_S)

    async def _equity_loop():
        while True:
            for aid, ad in list(adapters.items()):
                try:
                    if ad.connected:
                        m = await ad.get_metrics()
                        if m.get("balance") is not None and m.get("account"):
                            record_equity(str(m["account"]), float(m["balance"]),
                                          engine.now_et().date().isoformat())
                except Exception:  # noqa: BLE001 — snapshots must never crash
                    pass
            await asyncio.sleep(EQUITY_INTERVAL_S)

    readiness_fired = {"date": None}

    async def _clock_loop():
        while True:
            try:
                await engine.clock_tick()
                now = engine.now_et()
                if should_fire_readiness(now, readiness_fired["date"]):
                    readiness_fired["date"] = now.date().isoformat()
                    r = compute_readiness(now, cfg, engine, acct_status)
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
        tasks = []
        if background:
            import uvicorn  # noqa: PLC0415
            hook_server = uvicorn.Server(uvicorn.Config(
                hook_app, host="127.0.0.1", port=cfg.hook_port,
                log_level="warning"))
            tasks = [asyncio.create_task(_clock_loop()),
                     asyncio.create_task(_broker_loop()),
                     asyncio.create_task(_equity_loop()),
                     asyncio.create_task(timer.loop()),
                     asyncio.create_task(hook_server.serve())]
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            for ad in adapters.values():
                with contextlib.suppress(Exception):
                    await ad.close()

    app = FastAPI(title="Ramos Quant Homebase", lifespan=lifespan)
    app.state.engine = engine
    app.state.cfg = cfg
    app.state.adapters = adapters
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    # ------------------------------------------------------------ webhook
    async def _handle_hook(request: Request):
        try:
            payload = json.loads(await request.body())
        except Exception:
            raise HTTPException(400, "body must be JSON")
        secret = str(payload.pop("secret", ""))
        if not cfg.webhook_secret or \
                not hmac.compare_digest(secret, cfg.webhook_secret):
            engine.journal("hook_rejected", reason="bad_secret")
            raise HTTPException(401, "bad secret")
        return await engine.handle_alert(payload)

    app.post("/hook")(_handle_hook)
    hook_app = FastAPI(title="Homebase hook")
    hook_app.post("/hook")(_handle_hook)
    app.state.hook_app = hook_app

    # ------------------------------------------------------------ dashboard
    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/status")
    async def status():
        accounts = {}
        for aid, a in cfg.accounts.items():
            ad = adapters.get(aid)
            try:
                m = await ad.get_metrics() if ad else {"connected": False}
            except Exception as e:  # noqa: BLE001
                m = {"connected": False, "error": f"metrics: {e}"}
            s = acct_status.get(aid, {})
            if s.get("error") and not m.get("error"):
                m["error"] = s["error"]
            accounts[aid] = {"label": a.label or a.account_name or aid,
                             "env": "live" if a.live else "demo", **m}
        live = live_metrics(state_dir() / "journal.jsonl")
        journal = []
        jp = state_dir() / "journal.jsonl"
        if jp.exists():
            journal = [json.loads(l) for l in
                       jp.read_text().splitlines()[-JOURNAL_TAIL:]][::-1]
        return {
            "armed": cfg.armed,
            "et_now": engine.now_et().isoformat(timespec="seconds"),
            "readiness": compute_readiness(engine.now_et(), cfg, engine,
                                           acct_status),
            "timer": timer.status(),
            "accounts": accounts,
            "book": cfg.book,
            "strategies": {
                name: {
                    "cfg": {"symbol": s.symbol, "qty": s.qty,
                            "offset_pts": s.offset_pts, "sl_pts": s.sl_pts,
                            "tp_pts": s.tp_pts, "cancel_et": s.cancel_et,
                            "flat_et": s.flat_et, "enabled": s.enabled,
                            "gated": s.gated, "self_fire": s.self_fire,
                            "pine_file": getattr(s, "pine_file", "")},
                    "research": s.metrics,
                    "live": live.get(name),
                    "day_status": engine.day_status(name),
                    "accounts": [vars(st) for st in engine.day_states(name)],
                } for name, s in cfg.strategies.items()
            },
            "journal": journal,
        }

    @app.post("/api/arm")
    async def arm(request: Request):
        body = await request.json()
        cfg.armed = bool(body.get("armed"))
        config_mod.save(cfg)
        engine.journal("armed_toggled", armed=cfg.armed)
        return {"ok": True, "armed": cfg.armed}

    @app.post("/api/kill")
    async def kill():
        cfg.armed = False
        config_mod.save(cfg)
        results = {}
        for aid, ad in adapters.items():
            r = {}
            for call in ("cancel_all", "flatten_all"):
                try:
                    x = await getattr(ad, call)()
                    r[call] = {"ok": x.ok, "error": x.error}
                except Exception as e:  # noqa: BLE001 — kill always finishes
                    r[call] = {"ok": False, "error": str(e)}
            results[aid] = r
        engine.journal("kill_switch", results=results)
        return {"ok": True, "armed": False, "results": results}

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
            parts = key.split(":")
            out.append({"key": key, "label": (parts[-1] or key).upper(),
                        "env": parts[1] if len(parts) == 3 else "demo",
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
        """Validate a DEMO login (saved or new) with a throwaway probe and
        return every account under it. Nothing is added to the pool yet —
        that is /api/accounts/add, one click per account."""
        body = await request.json()
        saved = str(body.get("saved_key") or "")
        if saved:
            if not secrets_store.get_credentials(saved):
                raise HTTPException(404, f"no saved login {saved!r}")
            key = saved
        else:
            username = str(body.get("username") or "").strip()
            # newlines/CRs are never valid in a password but ride along with
            # clipboard pastes; spaces are preserved (could be legitimate)
            password = str(body.get("password") or "").strip("\r\n")
            if not username or not password:
                raise HTTPException(400, "username and password required")
            key = f"tv:demo:{username.lower()}"
            secrets_store.set_credentials(key, username=username,
                                          password=password)
        probe = adapter_factory("probe", config_mod.AccountCfg(keyring_key=key))
        try:
            await probe.connect()
            accounts = probe.list_accounts() if hasattr(probe, "list_accounts") else []
        except Exception as e:  # noqa: BLE001 — surface to the wizard
            return {"ok": False, "error": str(e), "key": key}
        finally:
            with contextlib.suppress(Exception):
                await probe.close()
        return {"ok": True, "key": key, "accounts": accounts}

    @app.post("/api/accounts/add")
    async def accounts_add(request: Request):
        """Add one broker account to the pool (demo only) and connect it."""
        body = await request.json()
        key = str(body.get("key") or "")
        account_name = str(body.get("account_name") or "").strip()
        if not key or not secrets_store.get_credentials(key):
            raise HTTPException(400, "unknown login key")
        if not account_name:
            raise HTTPException(400, "account_name required")
        aid = account_name.lower()
        cfg.accounts[aid] = config_mod.AccountCfg(
            keyring_key=key, account_name=account_name, live=False,
            label=str(body.get("label") or account_name))
        config_mod.save(cfg)
        try:
            await _connect_account(aid)
        except Exception as e:  # noqa: BLE001
            acct_status[aid] = {"connected": False, "error": str(e)}
            return {"ok": True, "account": aid, "connected": False,
                    "error": str(e)}
        return {"ok": True, "account": aid, "connected": True}

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
        """Manual reconnect for one account (or all). Clears any login backoff —
        the user is explicitly asking — and reconciles positions afterwards."""
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
            try:
                mode = await _connect_account(aid)
                results[aid] = {"ok": True, "mode": mode}
            except Exception as e:  # noqa: BLE001 — surface the reason
                acct_status[aid] = {"connected": False, "error": str(e)}
                results[aid] = {"ok": False, "error": str(e)[:200]}
        engine.journal("manual_reconnect", results=results)
        return {"ok": all(r["ok"] for r in results.values()) if results else False,
                "results": results}

    @app.post("/api/accounts/remove")
    async def accounts_remove(request: Request):
        """Remove an account from the pool: unassign it from every strategy,
        close its adapter, drop it. Refused while it holds an open position."""
        body = await request.json()
        aid = str(body.get("account") or "")
        if aid not in cfg.accounts:
            raise HTTPException(404, f"unknown account {aid!r}")
        ad = adapters.get(aid)
        if ad is not None and ad.connected:
            try:
                for s in cfg.strategies.values():
                    if await ad.get_net_position(s.symbol):
                        raise HTTPException(409, "account has an open position "
                                            "— flatten first")
            except HTTPException:
                raise
            except Exception:  # noqa: BLE001 — can't read = allow removal
                pass
        for name in list(cfg.book):
            cfg.book[name] = [a for a in cfg.book[name]
                              if a.get("account") != aid]
        cfg.accounts.pop(aid)
        config_mod.save(cfg)
        acct_status.pop(aid, None)
        old = adapters.pop(aid, None)
        if old is not None:
            with contextlib.suppress(Exception):
                await old.close()
        engine.journal("account_removed", account=aid)
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

    @app.post("/api/hook-url")
    async def set_hook_url(request: Request):
        body = await request.json()
        cfg.public_hook_url = str(body.get("url") or "").rstrip("/")
        config_mod.save(cfg)
        return {"ok": True, "public_hook_url": cfg.public_hook_url}

    @app.get("/api/tv-setup")
    async def tv_setup():
        return {
            "hook_path": "/hook",
            "public_hook_url": (cfg.public_hook_url + "/hook")
            if cfg.public_hook_url else None,
            "secret": cfg.webhook_secret,
            "strategies": {
                name: {
                    "symbol": s.symbol,
                    "alert_body_example": json.dumps({
                        "secret": cfg.webhook_secret, "strategy": name,
                        "upper": 24500 + s.offset_pts,
                        "lower": 24500 - s.offset_pts}),
                    "steps": [
                        f"Open the {s.symbol} 15s chart with the strategy script",
                        "Paste the webhook secret into the script's input",
                        "Create alert: condition = the script, 'Any alert() "
                        "function call', open-ended, webhook URL = this "
                        "server's /hook",
                    ],
                } for name, s in cfg.strategies.items()
            },
        }

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
