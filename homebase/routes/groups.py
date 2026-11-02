"""Account cycle groups (engine_groups.py): make or change one, delete it (following its Desk group: routes/setup.py). One module, so the
practice Desk (tools/fake_desk.py) registers exactly these routes instead of a copy."""
from __future__ import annotations

from fastapi import HTTPException, Request

from ..desk.engine_groups import GroupError


def register(app, *, engine) -> None:

    @app.post("/api/groups")
    async def group_set(request: Request):
        """{id, name?, members?, accounts?, risk_usd?, max_minis?, on?}: create or change one account cycle group
        (engine_groups). Fields left out keep their value."""
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, "a JSON object")
        try:
            return {"ok": True, "id": body.get("id"), **engine.set_group(body.get("id"), body)}
        except GroupError as e:
            raise HTTPException(400, str(e)) from None

    @app.post("/api/groups/delete")
    async def group_delete(request: Request):
        body = await request.json()
        try:
            engine.delete_group((body or {}).get("id") if isinstance(body, dict) else None)
        except GroupError as e:
            raise HTTPException(404, str(e)) from None
        return {"ok": True}
