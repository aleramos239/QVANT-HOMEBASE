"""The homebase server: webhook in, dashboard out.

    POST /hook            TradingView webhook (shared secret in the payload)
    GET  /                dashboard (single page, self-contained)
    GET  /api/status      everything the dashboard renders
    POST /api/arm         {"armed": true|false} — the master switch
    POST /api/kill        cancel everything + flatten + disarm
    POST /api/test-alert  synthetic valid-geometry alert through the real
                          validation path; REFUSED while armed

Binds to localhost; reach it from the laptop over Tailscale (or the tunnel
for /hook). UI endpoints carry no auth of their own — exposure is the
network boundary, so never port-forward this to the open internet.

Runs fine with no broker credentials: the adapter panel reports its own
failure loudly and the engine still validates + journals (dry run).
"""
from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config as config_mod
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
    return TradovateAdapter(cfg.account.keyring_key, env=env,
                            keyring_key=cfg.account.keyring_key)


def create_app(cfg: config_mod.AppCfg | None = None,
               adapter: BrokerAdapter | None = None,
               *, background: bool = True) -> FastAPI:
    cfg = cfg or config_mod.load()
    adapter = adapter or build_adapter(cfg)
    engine = Engine(cfg, adapter)
    broker_status: dict = {"connected": False, "error": "not connected yet"}

    async def _clock_loop():
        while True:
            try:
                await engine.clock_tick()
            except Exception as e:  # noqa: BLE001 — the clock must never die
                engine.journal("clock_error", error=str(e))
            await asyncio.sleep(CLOCK_INTERVAL_S)

    async def _broker_loop():
        while True:
            if not adapter.connected:
                try:
                    await adapter.connect()
                    await adapter.observe_fills(engine.on_fill)
                    broker_status.update(connected=True, error=None)
                    engine.journal("broker_connected", account=adapter.account_id)
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
                await adapter.close()

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
            metrics = await adapter.get_metrics()
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
                r = await getattr(adapter, call)()
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

    return app


app = create_app()
