"""A promoted Lab strategy's limits, settings, Remove and Clear (labdesk.py does the work).

Moved verbatim from homebase.server.create_app (2026-10-20): same paths, same bodies, registered straight on the app."""
from __future__ import annotations

from fastapi import HTTPException, Request

from ..desk import labdesk as labdesk_mod


def register(app, *, labdesk) -> None:

    @app.post("/api/lab-limits")
    async def lab_limits(request: Request):
        """Set a promoted Lab strategy's limits: {strategy, limits: {max_trades_day, max_qty, max_risk_usd,
        last_entry_et, flat_et}}. A bad field is a 400 with its sentence; refused (409) while it has a
        round open."""
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, "{strategy, limits}")
        try:
            return await labdesk.set_limits(str(body.get("strategy") or ""), body.get("limits"))
        except labdesk_mod.Refused as e:
            raise HTTPException(e.status, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @app.post("/api/lab-settings")
    async def lab_settings(request: Request):
        """Change the settings a promoted Lab strategy declared adjustable: {strategy, settings: {key: value}}. A bad
        key or value is a 400 with its sentence; refused (409) while its session runs and while it has a round
        open. Takes effect from its next session."""
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, "{strategy, settings}")
        try:
            return await labdesk.set_settings(str(body.get("strategy") or ""), body.get("settings"))
        except labdesk_mod.Refused as e:
            raise HTTPException(e.status, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @app.post("/api/lab-identity")
    async def lab_identity(request: Request):
        """Rename a promoted Lab strategy and/or switch the contract its orders go to: {strategy, label?, instrument?
        ("mini" | "micro")}. Sizes move at the same exposure; one that would not come out whole is refused with its
        sentence (409). A bad field is a 400."""
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, "{strategy, label, instrument}")
        try:
            return await labdesk.set_identity(str(body.get("strategy") or ""), {k: v for k, v in body.items() if k != "strategy"})
        except labdesk_mod.Refused as e:
            raise HTTPException(e.status, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @app.post("/api/lab-duplicate")
    async def lab_duplicate(request: Request):
        """Copy a promoted Lab strategy under a new name: {strategy}. The copy is OFF, on no account, with no history."""
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, "{strategy}")
        try:
            return await labdesk.duplicate(str(body.get("strategy") or ""))
        except labdesk_mod.Refused as e:
            raise HTTPException(e.status, str(e)) from None

    @app.post("/api/lab-remove")
    async def lab_remove(request: Request):
        """Take a promoted Lab strategy off the Desk: {strategy}. Its accounts are unassigned, its record and
        its limits go, its history stays. Refused (409) while it has a round open."""
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, "{strategy}")
        try:
            return await labdesk.remove(str(body.get("strategy") or ""))
        except labdesk_mod.Refused as e:
            raise HTTPException(e.status, str(e)) from None

    @app.post("/api/lab-clear")
    async def lab_clear(request: Request):
        """Clear the block a Lab strategy carries on one account from an earlier day: {strategy, account}. Only with
        the account's position in that market at exactly 0 and no known order of that trade still working; it sends
        nothing. Refused (409) with the sentence."""
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, "{strategy, account}")
        try:
            return await labdesk.clear_block(str(body.get("strategy") or ""), str(body.get("account") or ""))
        except labdesk_mod.Refused as e:
            raise HTTPException(e.status, str(e)) from None

