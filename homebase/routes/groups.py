"""Teams (engine_groups.py): delete one. A team is made and changed by the Set-up save (routes/setup.py). One module, so the
practice Desk (tools/fake_desk.py) registers exactly these routes instead of a copy."""
from __future__ import annotations

from fastapi import HTTPException, Request

from ..desk.engine_groups import GroupError


def register(app, *, engine) -> None:

    @app.post("/api/groups/delete")
    async def group_delete(request: Request):
        body = await request.json()
        try:
            engine.delete_group((body or {}).get("id") if isinstance(body, dict) else None)
        except GroupError as e:
            raise HTTPException(404, str(e)) from None
        return {"ok": True}
