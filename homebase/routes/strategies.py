"""A strategy's switch, take-turns, target, flatten and its account book.

Moved verbatim from homebase.server.create_app (2026-10-20): same paths, same bodies, registered straight on the app."""
from __future__ import annotations

from fastapi import HTTPException, Request

from .. import config as config_mod
from ..desk import labdesk as labdesk_mod


def register(app, *, cfg, engine, labdesk) -> None:

    @app.post("/api/strategy")
    async def strategy_toggle(request: Request):
        """Turn one strategy on or off — off means it ignores everything:
        no signals accepted, the timer skips it, readiness skips it."""
        body = await request.json()
        name = str(body.get("strategy") or "")
        if name not in cfg.strategies:
            raise HTTPException(404, f"unknown strategy {name!r}")
        if labdesk.is_lab(name):
            # a promoted Lab strategy has ONE switch, its store record's (the runner hosts by it): nothing of it
            # is in config.json
            on = bool(body.get("enabled"))
            if not on:                       # first, whatever the write below does: its unfilled entries are
                await labdesk.stop(name, "off")      # cancelled and its day is over (never raises)
            try:
                if not await labdesk.set_enabled(name, on):
                    raise HTTPException(409, labdesk_mod.RECORD_CHANGED)
            except labdesk_mod.Refused as e:
                raise HTTPException(e.status, str(e)) from None
            engine.journal("strategy_toggled", strategy=name, enabled=on)
            return {"ok": True, "strategy": name, "enabled": on}
        cfg.strategies[name].enabled = bool(body.get("enabled"))
        config_mod.save(cfg)
        engine.journal("strategy_toggled", strategy=name,
                       enabled=cfg.strategies[name].enabled)
        return {"ok": True, "strategy": name,
                "enabled": cfg.strategies[name].enabled}

    @app.post("/api/rotation")
    async def strategy_rotation(request: Request):
        """{strategy, on}: take turns -- each trade goes to ONE booked account, the next in book order that can take
        it -- or (off, the default) every booked account, as always."""
        body = await request.json()
        name = str((body or {}).get("strategy") or "") if isinstance(body, dict) else ""
        if name not in cfg.strategies:
            raise HTTPException(404, f"unknown strategy {name!r}")
        if not isinstance(body.get("on"), bool):
            raise HTTPException(400, "on must be true or false")
        return {"ok": True, "strategy": name, **engine.set_rotation(name, body["on"])}

    @app.post("/api/strategy-rr")
    async def strategy_rr(request: Request):
        """Set a straddle's target as a multiple of its stop: tp_pts = round(sl_pts * rr, 4). The body may also
        carry sl_pts (the stop in points; rr then defaults to the current one). Refused while the strategy has
        working orders or an open position today (stop and target are read when the legs go out and re-price)."""
        body = await request.json()
        name = str(body.get("strategy") or "")
        if name not in cfg.strategies:
            raise HTTPException(404, f"unknown strategy {name!r}")
        s = cfg.strategies[name]
        if s.kind != "straddle" or not s.sl_pts > 0:
            raise HTTPException(400, f"{name} has no fixed stop to take a target from")
        rr = body.get("rr", s.rr if "sl_pts" in body else None)
        if isinstance(rr, bool) or not isinstance(rr, (int, float)) or not 0.25 <= rr <= 20:
            raise HTTPException(400, "rr must be a number from 0.25 to 20")
        sl = body.get("sl_pts", s.sl_pts)
        if isinstance(sl, bool) or not isinstance(sl, (int, float)) or not 0.25 <= sl <= 200:
            raise HTTPException(400, "sl_pts must be a number from 0.25 to 200")
        busy = [st.account for st in engine.day_states(name)
                if st.status in ("placing", "placed", "live", "error")]
        if busy:
            raise HTTPException(409, f"refused: {name} has orders or a position today "
                                "— change the target once it is flat")
        previous = {"rr": s.rr, "tp_pts": s.tp_pts, "sl_pts": s.sl_pts}
        s.rr, s.sl_pts = float(rr), float(sl)
        s.tp_pts = round(s.sl_pts * s.rr, 4)
        config_mod.save(cfg)
        engine.journal("strategy_rr_changed", strategy=name, rr=s.rr, tp_pts=s.tp_pts, sl_pts=s.sl_pts,
                       previous=previous)
        return {"ok": True, "strategy": name, "rr": s.rr, "tp_pts": s.tp_pts, "sl_pts": s.sl_pts}

    @app.post("/api/strategy-flatten")
    async def strategy_flatten(request: Request):
        """Flatten one strategy everywhere it acted today AND switch it off."""
        body = await request.json()
        name = str(body.get("strategy") or "")
        if name not in cfg.strategies:
            raise HTTPException(404, f"unknown strategy {name!r}")
        if labdesk.is_lab(name):             # a Lab strategy's day ends here too, before anything else: no entry of
            await labdesk.stop(name, "off")  # it passes from now on, and its unfilled entries go (never raises)
        results = await engine.flatten_strategy(name)
        if labdesk.is_lab(name):             # its switch is the store record's
            try:
                await labdesk.set_enabled(name, False)
            except Exception as e:  # noqa: BLE001 -- the flatten is done: its result is answered whatever the switch did
                engine.journal("lab_save_error", strategy=name, error=str(e)[:200], cause="manual_flatten")
                s = cfg.strategies.get(name)
                return {"ok": True, "enabled": bool(s is not None and s.enabled), "results": results,
                        **labdesk.flatten_check(name, results), "detail": labdesk_mod.SWITCH_NOT_OFF}
            engine.journal("strategy_toggled", strategy=name, enabled=False,
                           cause="manual_flatten")
            # `check` (kind lab, only when there is one): the accounts where a person must look -- every account
            # of `results` that is not in it is ok (flat, or its close order is out)
            return {"ok": True, "enabled": False, "results": results, **labdesk.flatten_check(name, results)}
        cfg.strategies[name].enabled = False
        config_mod.save(cfg)
        engine.journal("strategy_toggled", strategy=name, enabled=False,
                       cause="manual_flatten")
        return {"ok": True, "enabled": False, "results": results}

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
        try:
            if labdesk.is_lab(name):         # its book lives in its own file beside its record, never in config.json
                await labdesk.set_book(name, rows)
                engine.journal("book_updated", strategy=name, assignments=rows)
                note = labdesk.window_note(name) if rows else None      # its window runs past the flat time: a note, never a refusal
                return {"ok": True, "book": labdesk.book_view(), **({"note": note} if note else {})}
            labdesk.check_book(name, rows)   # says nothing unless a promoted Lab strategy is on the desk
        except labdesk_mod.Refused as e:
            raise HTTPException(e.status, str(e)) from None
        cfg.book[name] = rows
        config_mod.save(cfg)
        engine.journal("book_updated", strategy=name, assignments=rows)
        return {"ok": True, "book": labdesk.book_view()}     # cfg.book itself unless a Lab strategy is on the desk

