"""The master switch, Kill, one account's flatten and day lock, and the dry-run test alert.

Moved verbatim from homebase.server.create_app (2026-10-20): same paths, same bodies, registered straight on the app."""
from __future__ import annotations

import math

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from .. import config as config_mod


def register(app, *, _kill_lock, adapters, cfg, desk, engine) -> None:

    @app.post("/api/arm")
    async def arm(request: Request):
        body = await request.json()
        cfg.armed = bool(body.get("armed"))
        config_mod.save(cfg)
        engine.journal("armed_toggled", armed=cfg.armed)
        return {"ok": True, "armed": cfg.armed}

    @app.post("/api/account-day-lock")
    async def account_day_lock(request: Request):
        """An account's own day take, the group's: {account, day_lock} in dollars of CLOSED net P&L, 0 = off. Once a
        trade of any strategy booked on the account closes with the day at or above it, no new entry is taken on the
        account for the rest of the day (resting entries are cancelled, open trades run to their stop / target). Set
        at or below the day's closed P&L it locks now; a lock already taken stays for the day."""
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, "{account, day_lock}")
        aid = str(body.get("account") or "")
        if aid not in cfg.accounts:
            raise HTTPException(404, f"unknown account {aid!r}")
        v = body.get("day_lock")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 100000:
            raise HTTPException(400, "The day take is a dollar amount from 0 (off) to 100000.")
        prev = cfg.accounts[aid].day_lock
        cfg.accounts[aid].day_lock = float(v)
        try:
            config_mod.save(cfg)
        except Exception as e:  # noqa: BLE001 -- nothing changed: the memory goes back with the file
            cfg.accounts[aid].day_lock = prev
            raise HTTPException(500, f"Could not save it: {e}") from None
        engine.journal("account_day_lock_set", account=aid, day_lock=float(v), previous=prev)
        await engine.apply_day_lock(aid)
        return {"ok": True, "account": aid, **engine.day_view(aid)}

    async def _sweep(ad) -> dict:
        """One account's two account-wide calls: cancel every working order, then flatten every position.
        Never raises: each call's own answer, or why it could not be made."""
        r = {}
        for call in ("cancel_all", "flatten_all"):
            try:
                x = await getattr(ad, call)()
                r[call] = {"ok": x.ok, "error": x.error}
            except Exception as e:  # noqa: BLE001 — kill always finishes
                r[call] = {"ok": False, "error": str(e)}
        return r

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
            import time as _t
            t0 = _t.perf_counter()
            # every strategy's own orders first, with the proven per-order calls;
            # then the account-wide calls sweep up anything else. Both go account
            # beside account (engine.each_account), each account's own steps in order
            strategies = await engine.flatten_today(close=False)    # the sweep closes at the broker
            t1 = _t.perf_counter()

            pool = dict(adapters)
            got, took = await engine.each_account(pool, lambda aid: _sweep(pool[aid]))
            results = {aid: (g if isinstance(g, dict) else
                             {call: {"ok": False, "error": str(g)}
                              for call in ("cancel_all", "flatten_all")})
                       for aid, g in got.items()}
            t2 = _t.perf_counter()
            engine.journal("kill_switch", results=results, strategies=strategies,
                           # timing only: the strategies' own flatten, the sweep, each account's sweep
                           kill_ms={"strategies": round((t1 - t0) * 1000, 1),
                                    "sweep": round((t2 - t1) * 1000, 1),
                                    "total": round((t2 - t0) * 1000, 1), "accounts": took})
        return {"ok": True, "armed": False, "results": results,
                "strategies": strategies}

    @app.post("/api/account-flatten")
    async def account_flatten(request: Request):
        """The Kill's broker work for ONE account: its strategies' orders today (engine.flatten_today,
        cancels only), then the account-wide cancel and the broker-side flatten (liquidateposition: the
        broker closes what IT holds, so a repeat click never sells a stale position twice). Nothing is
        disarmed and no strategy is switched off; a run that was working on this account today is over
        for today. It holds the Kill's locks, so it never reads a net alongside a Kill or a
        per-strategy Kill."""
        body = await request.json()
        aid = str(body.get("account") or "")
        if aid not in cfg.accounts:
            raise HTTPException(404, f"unknown account {aid!r}")
        ad = adapters.get(aid)
        if ad is None:
            raise HTTPException(409, "account not connected — nothing can be sent to it")
        async with _kill_lock(), engine.all_kill_locks():
            strategies = await engine.flatten_today(account=aid, reason="manual_flat", close=False)
            results = await _sweep(ad)
            engine.journal("account_flatten", account=aid, results=results, strategies=strategies)
        return {"ok": True, "account": aid, "results": {aid: results}, "strategies": strategies}

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

