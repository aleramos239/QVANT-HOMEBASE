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
from .paths import state_dir

STATIC = Path(__file__).resolve().parent / "static"
CLOCK_INTERVAL_S = 5
RECONNECT_INTERVAL_S = 30
JOURNAL_TAIL = 60


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

    async def _try_connect() -> None:
        ad = box["adapter"]
        await ad.connect()
        await ad.observe_fills(engine.on_fill)
        broker_status.update(connected=True, error=None)
        engine.journal("broker_connected", account=ad.account_id)

    async def _clock_loop():
        while True:
            try:
                await engine.clock_tick()
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

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        tasks = []
        if background:
            tasks = [asyncio.create_task(_clock_loop()),
                     asyncio.create_task(_broker_loop())]
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
    @app.post("/hook")
    async def hook(request: Request):
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
    @app.post("/api/connect")
    async def connect(request: Request):
        """Store a Tradovate DEMO login and reconnect in place. The password
        goes straight into the local secrets store (gitignored); it is never
        echoed back. Live trading is deliberately NOT reachable from here."""
        body = await request.json()
        username = str(body.get("username") or "").strip()
        password = str(body.get("password") or "")
        account_name = str(body.get("account_name") or "").strip()
        if not username or not password:
            raise HTTPException(400, "username and password required")
        key = f"tv:demo:{username.lower()}"
        secrets_store.set_credentials(key, username=username, password=password)
        cfg.account.keyring_key = key
        cfg.account.account_name = account_name
        cfg.account.live = False
        config_mod.save(cfg)
        with contextlib.suppress(Exception):
            await box["adapter"].close()
        box["adapter"] = adapter_factory(cfg)
        engine.adapter = box["adapter"]
        try:
            await _try_connect()
        except Exception as e:  # noqa: BLE001 — surface the reason to the UI
            broker_status.update(connected=False, error=str(e))
            return {"ok": False, "error": str(e)}
        m = await box["adapter"].get_metrics()
        return {"ok": True, "account": m.get("account")}

    @app.get("/api/tv-setup")
    async def tv_setup():
        """Everything TradingView needs, ready to paste. The Pine script
        builds the alert body itself; the secret rides in a script INPUT so
        it never sits in the Pine source or the TV alert dialog."""
        return {
            "hook_path": "/hook",
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
