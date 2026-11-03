"""Variant sets (desk/variants.py): Combine, rename, label, Split, Not these. One module, so the practice Desk
(tools/fake_desk.py) registers exactly these routes instead of a copy."""
from __future__ import annotations

from fastapi import HTTPException, Request

from ..desk import labcfg, variants


def register(app, *, cfg, engine) -> None:

    @app.post("/api/variants/{action}")
    async def variants_action(action: str, request: Request):
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, "a JSON object")
        try:
            d = variants.apply(engine._root, action, body, teams=engine.groups, names=set(labcfg.lab_ids(cfg)))
        except variants.VariantError as e:
            raise HTTPException(400, str(e)) from None
        engine.journal("variants_changed", action=action, set=body.get("id"), members=body.get("members"))
        return {"ok": True, "sets": d["sets"]}


def status_view(cfg, engine) -> dict:
    """status.variants: the sets (members no longer on the Desk drop out) and what the Desk suggests."""
    names = labcfg.lab_ids(cfg)
    d = variants.load(engine._root, set(names))
    team = {m for g in engine.groups.values() for m in g["members"]}
    sug = variants.suggest(names, in_team=team, sets=d["sets"], dismissed=d["dismissed"])
    return {"sets": d["sets"], "suggest": [{**s, "stem": s["stem"].removeprefix("lab_")} for s in sug]}
