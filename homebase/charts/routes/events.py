"""The paper strategy, the economic calendar and the news."""
from __future__ import annotations

from fastapi import HTTPException, Request

from ... import netguard
from ..paper import STRATEGY_ID as PAPER_ID, describe as paper_describe


def register(app, *, paper, cal, news) -> None:
    @app.get("/api/paper/strategies")
    async def paper_strategies():
        return [paper_describe()]

    @app.get("/api/paper/history")
    async def paper_history(strategy: str = PAPER_ID):
        if strategy != PAPER_ID:
            raise HTTPException(404, f"no paper strategy {strategy!r}")
        return paper.history()

    @app.get("/api/calendar")
    async def api_calendar(request: Request):
        q = request.query_params
        try:
            frm, to = int(q.get("from", 0)), int(q.get("to", 2 ** 62))
        except ValueError:
            raise HTTPException(400, "from / to: epoch ms") from None
        countries = [c.strip() for c in q.get("countries", "").split(",") if c.strip()]
        return cal.events(frm, to, countries or None)

    @app.get("/api/news")
    async def api_news(request: Request):
        bad = netguard.refusal(request.method, request.scope["headers"], netguard.allowlist())
        if bad is not None:
            raise HTTPException(*bad)
        q = request.query_params
        try:
            frm, to = int(q.get("from", 0)), int(q.get("to", 2 ** 62))
        except ValueError:
            raise HTTPException(400, "from / to: epoch ms") from None
        tags = [t.strip() for t in q.get("tags", "").split(",") if t.strip()]
        sources = [s.strip() for s in q.get("sources", "").split(",") if s.strip()]
        return news.items(frm, to, tags or None, sources or None)
