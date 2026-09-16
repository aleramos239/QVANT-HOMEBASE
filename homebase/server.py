"""The homebase server: webhook in, dashboard out.

    POST /hook            TradingView webhook (shared secret in the payload)
    GET  /                dashboard (single page, self-contained)
    GET  /api/status      everything the dashboard renders
    POST /api/arm         {"armed": true|false} — the master switch
    POST /api/kill        cancel everything + flatten + disarm
    POST /api/test-alert  synthetic valid-geometry alert; REFUSED while armed
    POST /api/connect     store a Tradovate DEMO login + reconnect in place
    GET  /api/tv-setup    webhook URL pieces + per-strategy alert JSON for TV

Binds to localhost; reach it from the laptop over Tailscale (or the tunnel
for /hook). UI endpoints carry no auth of their own — exposure is the
network boundary, so never port-forward this to the open internet.

Runs fine with no broker credentials: the adapter panel reports its own
failure loudly and the engine still validates + journals (dry run).
The /api/connect flow only ever writes DEMO logins; going live is a
deliberate hand-edit of config.json, not a click.
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

# python.org macOS builds ship no CA bundle for urllib; point the stdlib at
# certifi's (present via requirements) so the Tradovate TLS handshake verifies.
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:  # pragma: no cover — certifi rides in via requirements
    pass

from . import config as config_mod
from . import secrets_store
from .broker.base import BrokerAdapter
from .broker.tradovate import TradovateAdapter
from .engine import Engine
from .marketdata import TradovateMD
from .paths import state_dir
from .timer import SelfTimer

STATIC = Path(__file__).resolve().parent / "static"
CLOCK_INTERVAL_S = 5
RECONNECT_INTERVAL_S = 30
EQUITY_INTERVAL_S = 60
JOURNAL_TAIL = 60


def _equity_path() -> Path:
    return state_dir() / "equity.jsonl"


def record_equity(account: str, equity: float, date: str) -> None:
    """Append today's equity for an account. Last line per (date, account)
    wins on read, so polling just keeps appending — the day's final value is
    the day's close, same reconstruction the copier's journal used."""
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
    """{'days': {date: pnl}, 'total': x} for one YYYY-MM month — equity
    close-over-close, so the first ever day has no P&L (no prior close)."""
    eq = equity_by_day(account)
    days, prev, total = {}, None, 0.0
    for date, e in eq.items():
        if prev is not None and date.startswith(month):
            pnl = round(e - prev, 2)
            days[date] = pnl
            total += pnl
        prev = e
    return {"days": days, "total": round(total, 2)}


READINESS_FROM = (9, 25)   # journal a not-ready state once, at 9:25 ET


def compute_readiness(now_et, cfg: config_mod.AppCfg, states: dict,
                      broker_connected: bool, broker_error: str | None) -> dict:
    """Every check the desk needs before the open, across ALL strategies.
    levels: ok | info | warn | bad — 'ready' means no 'bad'."""
    import datetime as dt
    checks = []
    checks.append({"level": "ok" if broker_connected else "bad",
                   "label": "Broker",
                   "detail": "connected" if broker_connected
                   else (broker_error or "not connected")})
    checks.append({"level": "ok" if cfg.webhook_secret else "bad",
                   "label": "Webhook secret",
                   "detail": "set" if cfg.webhook_secret else "missing — TV alerts would be rejected"})
    enabled = {n: s for n, s in cfg.strategies.items() if s.enabled}
    checks.append({"level": "ok" if enabled else "warn",
                   "label": "Strategies",
                   "detail": (", ".join(enabled) or "none enabled")})
    weekday = now_et.weekday() < 5
    for name, s in enabled.items():
        st = states.get(name)
        status = getattr(st, "status", "idle")
        h, m = s.accept_until_et.split(":")
        after_window = now_et.time() > dt.time(int(h), int(m))
        if weekday and after_window and status == "idle":
            if s.gated:
                checks.append({"level": "warn", "label": name,
                               "detail": "no alert today — gated day (expected) "
                                         "or the TV alert is broken"})
            else:
                checks.append({"level": "bad", "label": name,
                               "detail": "no alert arrived — this strategy "
                                         "trades every day, check the TV alert"})
        elif status != "idle":
            checks.append({"level": "ok", "label": name, "detail": status})
    checks.append({"level": "info", "label": "Mode",
                   "detail": "ARMED — alerts place real orders" if cfg.armed
                   else "shadow — alerts journal only"})
    return {"ready": not any(c["level"] == "bad" for c in checks),
            "checks": checks}


def should_fire_readiness(now_et, fired_date: str | None) -> bool:
    """True once per weekday, in the 9:25-9:30 ET slot."""
    if now_et.weekday() >= 5 or fired_date == now_et.date().isoformat():
        return False
    t = now_et.time()
    return t.hour == READINESS_FROM[0] and t.minute >= READINESS_FROM[1]


def build_adapter(cfg: config_mod.AppCfg) -> BrokerAdapter:
    env = "live" if cfg.account.live else "demo"
    sel = {"account_name": cfg.account.account_name} \
        if cfg.account.account_name else None
    return TradovateAdapter("tradovate", env=env,
                            keyring_key=cfg.account.keyring_key,
                            account_selector=sel)


def create_app(cfg: config_mod.AppCfg | None = None,
               adapter: BrokerAdapter | None = None,
               *, background: bool = True,
               adapter_factory=build_adapter) -> FastAPI:
    cfg = cfg or config_mod.load()
    box = {"adapter": adapter or adapter_factory(cfg)}
    engine = Engine(cfg, box["adapter"])
    broker_status: dict = {"connected": False, "error": "not connected yet"}
    timer = SelfTimer(cfg, engine, md_factory=lambda: TradovateMD(
        cfg.account.keyring_key, "live" if cfg.account.live else "demo"))

    async def _try_connect() -> None:
        ad = box["adapter"]
        await ad.connect()
        await ad.observe_fills(engine.on_fill)
        broker_status.update(connected=True, error=None)
        engine.journal("broker_connected", account=ad.account_id)

    readiness_fired = {"date": None}

    async def _clock_loop():
        while True:
            try:
                await engine.clock_tick()
                now = engine.now_et()
                if should_fire_readiness(now, readiness_fired["date"]):
                    readiness_fired["date"] = now.date().isoformat()
                    r = compute_readiness(now, cfg, engine.states,
                                          box["adapter"].connected,
                                          broker_status.get("error"))
                    engine.journal(
                        "morning_readiness", ready=r["ready"],
                        problems=[c["label"] + ": " + c["detail"]
                                  for c in r["checks"]
                                  if c["level"] in ("bad", "warn")])
            except Exception as e:  # noqa: BLE001 — the clock must never die
                engine.journal("clock_error", error=str(e))
            await asyncio.sleep(CLOCK_INTERVAL_S)

    async def _broker_loop():
        while True:
            if not box["adapter"].connected:
                try:
                    await _try_connect()
                except Exception as e:  # noqa: BLE001 — report, retry later
                    broker_status.update(connected=False, error=str(e))
            await asyncio.sleep(RECONNECT_INTERVAL_S)

    async def _equity_loop():
        """Snapshot account equity once a minute while connected — the raw
        material for the P&L calendar (last snapshot of a day = its close)."""
        while True:
            try:
                ad = box["adapter"]
                if ad.connected:
                    m = await ad.get_metrics()
                    if m.get("balance") is not None and m.get("account"):
                        record_equity(str(m["account"]), float(m["balance"]),
                                      engine.now_et().date().isoformat())
            except Exception:  # noqa: BLE001 — snapshots must never crash
                pass
            await asyncio.sleep(EQUITY_INTERVAL_S)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        tasks = []
        if background:
            import uvicorn  # noqa: PLC0415 — only the real server needs it
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
            with contextlib.suppress(Exception):
                await box["adapter"].close()

    app = FastAPI(title="Ramos Quant Homebase", lifespan=lifespan)
    app.state.engine = engine
    app.state.cfg = cfg
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

    # The tunnel-facing app: ONE route, nothing else. A tunnel pointed at
    # hook_port can never reach the dashboard, arm, kill, or connect.
    hook_app = FastAPI(title="Homebase hook")
    hook_app.post("/hook")(_handle_hook)
    app.state.hook_app = hook_app

    # ------------------------------------------------------------ dashboard
    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/status")
    async def status():
        try:
            metrics = await box["adapter"].get_metrics()
        except Exception as e:  # noqa: BLE001 — dashboard must render anyway
            metrics = {"connected": False, "error": f"metrics: {e}"}
        if broker_status.get("error") and not metrics.get("error"):
            metrics["error"] = broker_status["error"]
        journal = []
        jp = state_dir() / "journal.jsonl"
        if jp.exists():
            lines = jp.read_text().splitlines()[-JOURNAL_TAIL:]
            journal = [json.loads(l) for l in lines][::-1]
        return {
            "armed": cfg.armed,
            "et_now": engine.now_et().isoformat(timespec="seconds"),
            "account_env": "live" if cfg.account.live else "demo",
            "readiness": compute_readiness(
                engine.now_et(), cfg, engine.states,
                metrics.get("connected", False), metrics.get("error")),
            "timer": timer.status(),
            "broker": metrics,
            "strategies": {
                name: {
                    "cfg": {"symbol": s.symbol, "qty": s.qty,
                            "offset_pts": s.offset_pts, "sl_pts": s.sl_pts,
                            "tp_pts": s.tp_pts, "cancel_et": s.cancel_et,
                            "flat_et": s.flat_et, "enabled": s.enabled},
                    "state": vars(engine._state(name)),
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
        for call in ("cancel_all", "flatten_all"):
            try:
                r = await getattr(box["adapter"], call)()
                results[call] = {"ok": r.ok, "error": r.error}
            except Exception as e:  # noqa: BLE001 — kill must always finish
                results[call] = {"ok": False, "error": str(e)}
        engine.journal("kill_switch", **results)
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
        out = await engine.handle_alert(payload, force_window=True)
        return {"sent": payload, "result": out}

    # ------------------------------------------------------------ setup
    async def _rebuild_and_connect() -> dict:
        with contextlib.suppress(Exception):
            await box["adapter"].close()
        box["adapter"] = adapter_factory(cfg)
        engine.adapter = box["adapter"]
        try:
            await _try_connect()
        except Exception as e:  # noqa: BLE001 — surface the reason to the UI
            broker_status.update(connected=False, error=str(e))
            return {"ok": False, "error": str(e)}
        ad = box["adapter"]
        m = await ad.get_metrics()
        accounts = ad.list_accounts() if hasattr(ad, "list_accounts") else []
        return {"ok": True, "account": m.get("account"), "accounts": accounts}

    @app.get("/api/logins")
    async def logins():
        """Saved broker logins — key names and metadata only, never values."""
        out = []
        for key in secrets_store._load_all():
            parts = key.split(":")
            out.append({"key": key,
                        "label": (parts[-1] or key).upper(),
                        "env": parts[1] if len(parts) == 3 else "demo",
                        "in_use": key == cfg.account.keyring_key})
        return {"logins": out}

    @app.post("/api/logins/delete")
    async def logins_delete(request: Request):
        body = await request.json()
        key = str(body.get("key") or "")
        if key == cfg.account.keyring_key:
            raise HTTPException(409, "that login is in use — connect another first")
        secrets_store.delete_credentials(key)
        return {"ok": True}

    @app.post("/api/connect")
    async def connect(request: Request):
        """Connect with a saved login (key only) or a new Tradovate DEMO
        login. A new password goes straight into the local secrets store
        (gitignored) and is never echoed back. Live trading is deliberately
        NOT reachable from here — that stays a config-file decision."""
        body = await request.json()
        saved = str(body.get("saved_key") or "")
        if saved:
            if not secrets_store.get_credentials(saved):
                raise HTTPException(404, f"no saved login {saved!r}")
            key = saved
        else:
            username = str(body.get("username") or "").strip()
            password = str(body.get("password") or "")
            if not username or not password:
                raise HTTPException(400, "username and password required")
            key = f"tv:demo:{username.lower()}"
            secrets_store.set_credentials(key, username=username,
                                          password=password)
        if key != cfg.account.keyring_key:
            cfg.account.account_name = ""      # new login: pin nothing yet
        cfg.account.keyring_key = key
        cfg.account.live = False
        config_mod.save(cfg)
        return await _rebuild_and_connect()

    @app.post("/api/select-account")
    async def select_account(request: Request):
        """Pin one account under the connected login and reconnect to it."""
        body = await request.json()
        cfg.account.account_name = str(body.get("account_name") or "").strip()
        config_mod.save(cfg)
        return await _rebuild_and_connect()

    @app.get("/api/calendar")
    async def calendar(month: str, account: str = ""):
        """Monthly P&L calendar for one account (default: the connected one),
        from the app's own daily equity snapshots."""
        if not account:
            try:
                m = await box["adapter"].get_metrics()
                account = str(m.get("account") or "")
            except Exception:  # noqa: BLE001
                account = ""
        d = daily_pnl(account, month)
        return {"account": account, "month": month, **d,
                "history_since": next(iter(equity_by_day(account)), None)}

    @app.post("/api/hook-url")
    async def set_hook_url(request: Request):
        """Record the tunnel's public origin so the TV card shows the real
        URL to paste (a quick tunnel's origin changes on every restart)."""
        body = await request.json()
        cfg.public_hook_url = str(body.get("url") or "").rstrip("/")
        config_mod.save(cfg)
        return {"ok": True, "public_hook_url": cfg.public_hook_url}

    @app.get("/api/tv-setup")
    async def tv_setup():
        """Everything TradingView needs, ready to paste. The Pine script
        builds the alert body itself; the secret rides in a script INPUT so
        it never sits in the Pine source or the TV alert dialog."""
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

    return app


app = create_app()
