"""The pages (/, /backtest), the status, the burst strip, the symbols and the Lab runner's tick stream."""
from __future__ import annotations

from contextlib import suppress

from fastapi import HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse

from ... import netguard
from ..paperbook import _cors, desk_origin_refusal
from .common import LOCAL_HOSTS

TIMEFRAMES = [["5s", "time:5"], ["15s", "time:15"], ["30s", "time:30"], ["1m", "time:60"],
              ["2m", "time:120"], ["3m", "time:180"], ["5m", "time:300"], ["10m", "time:600"],
              ["15m", "time:900"], ["30m", "time:1800"], ["1h", "time:3600"], ["4h", "time:14400"],
              ["1D", "time:86400"], ["500T", "tick:500"], ["1000T", "tick:1000"],
              ["2000V", "volume:2000"], ["10R", "range:10"], ["20R", "range:20"]]


class _TickStream(StreamingResponse):
    """A StreamingResponse that closes its generator whatever ends it -- the reader hung up, the task was cancelled --
    so the reader leaves the fan-out at once, not when its queue fills."""

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with suppress(Exception):
                await self.body_iterator.aclose()


def register(app, *, STATIC, status, burst_book, app_roots, tick_fan) -> None:
    @app.get("/")
    async def index():
        return FileResponse(STATIC / "charts.html", headers={"cache-control": "no-cache"})

    @app.get("/backtest")
    async def backtest_index():
        """2026-09-28 three-tabs plan: the same chart shell as / (charts.html), minus every trading
        module -- see docs/superpowers/specs/2026-09-28-three-tabs-design.md. Its own page, not a
        query param on /, so a plain <link> to it works with no JS and WKWebView's navigation
        delegate can tell the two apart by path alone."""
        return FileResponse(STATIC / "backtest.html", headers={"cache-control": "no-cache"})

    @app.get("/api/status")
    async def api_status(request: Request, response: Response):
        """Desk-settings plan: also answers the desk page's origin (the last switch error and
        any md login mismatch feed the Settings dialog there) -- same exact-origin CORS as
        /api/settings and the paper-account routes; everything else stays same-origin."""
        bad = desk_origin_refusal(request.headers)
        if bad is not None:
            raise HTTPException(*bad)
        _cors(response, request)
        return status()

    @app.get("/api/bursts/now")
    async def api_bursts_now():
        # Task 2, the burst radar strip: every streamed root's current ratio, for the page's
        # first paint before its /ws status (which carries the same thing every STATUS_S) lands.
        # Reads BurstBook's own cached per-root ratio -- no new md request, no event-loop work.
        return burst_book.now()

    @app.get("/api/symbols")
    async def api_symbols():
        return {"roots": app_roots, "timeframes": TIMEFRAMES}

    @app.get("/api/labrun/ticks")
    async def api_labrun_ticks(request: Request, roots: str = "", since_ms: int = 0):
        """The Lab strategy runner's tick stream (python -m homebase.labrun), Server-Sent Events: TickFan.stream.
        Read-only, and for a local process only: the Host must be 127.0.0.1 or localhost, and ANY request that
        carries an Origin -- a browser's -- is refused (the gate the desk keeps on /api/trade/*). A market this
        service does not chart is left out; no market at all still gets the clock. No broker request is made."""
        if not netguard.host_allowed(request.headers.get("host"), frozenset(LOCAL_HOSTS)):
            raise HTTPException(403, "the tick stream answers only as 127.0.0.1 or localhost")
        if request.headers.get("origin") is not None:
            raise HTTPException(403, "browser requests are refused")
        want = dict.fromkeys(r.strip().upper() for r in roots.split(","))
        return _TickStream(tick_fan.stream([r for r in want if r in app_roots], since_ms),
                           media_type="text/event-stream", headers={"cache-control": "no-cache"})
