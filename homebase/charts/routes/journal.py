"""The journal on the chart: a Desk day's round trips (read-only on the desk's journal) and a trip's note and tags."""
from __future__ import annotations

import asyncio
import datetime as dt

from fastapi import HTTPException, Request

from ... import netguard
from .. import journal


def register(app, *, journal_path, fills_dir, notes, browser_write_ok) -> None:
    @app.get("/api/journal/day")
    async def journal_day(request: Request, date: str | None = None):
        bad = netguard.refusal(request.method, request.scope["headers"], netguard.allowlist())
        if bad is not None:
            raise HTTPException(*bad)
        try:
            day = dt.date.fromisoformat(date or "").isoformat()
        except ValueError:
            raise HTTPException(400, "date: YYYY-MM-DD") from None
        trips = await asyncio.to_thread(journal.day_trips, journal_path, fills_dir, day)
        saved = notes.all()
        for t in trips:
            n = saved.get(t["id"])
            t["note"], t["tags"] = (n.get("note", ""), n.get("tags", [])) if isinstance(n, dict) else ("", [])
        return {"date": day, "trips": trips}

    @app.put("/api/journal/note")
    async def journal_note(request: Request):
        bad = netguard.refusal(request.method, request.scope["headers"], netguard.allowlist(), require_json=False)
        if bad is not None:
            raise HTTPException(*bad)
        browser_write_ok(request)
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "the body is not JSON") from None
        if not isinstance(body, dict):
            raise HTTPException(400, "the body is a JSON object")
        try:
            await asyncio.to_thread(notes.put, body.get("id"), body.get("note", ""), body.get("tags", []))
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return {"ok": True}
