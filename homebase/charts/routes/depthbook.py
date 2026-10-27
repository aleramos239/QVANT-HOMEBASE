"""The depth (liquidity heatmap) and book-indicator histories."""
from __future__ import annotations

import time

from fastapi import HTTPException, Request, Response

from ..bookhist import MAX_SPAN_MS as BOOK_MAX_SPAN_MS
from ..depthgrid import MAX_COLS as DEPTH_MAX_COLS, MAX_SPAN_MS as DEPTH_MAX_SPAN_MS, Busy, Paused, paused_reason


def register(app, *, known_root, clock, replay, depth_pool, book_pool) -> None:
    # the liquidity heatmap's history (depthgrid.py): the recorded depth files as a down-sampled grid, built
    # in ONE spawned worker process (never this process, never the default thread pool), one request at a
    # time (busy -> 503, never queued), <= 2 MB, never past now (a replay's own clock in a replay: no
    # look-ahead), and never decoded 08:29:30-08:31 ET on weekdays, by the wall clock
    # (the service's clock when live, so tests can place it)
    def depth_wall_ms() -> float:
        return time.time() * 1000 if replay else clock()

    @app.get("/api/depth/history")
    async def api_depth_history(request: Request):
        q = request.query_params
        root = known_root(q.get("root", ""))
        now = clock()
        try:
            frm, to = int(q["from_ms"]), int(q["to_ms"])
            cols = int(q.get("cols", DEPTH_MAX_COLS // 2))
        except (KeyError, ValueError):
            raise HTTPException(400, "from_ms / to_ms: epoch ms; cols: a whole number") from None
        if frm < 0 or to > now + 86_400_000 or to <= frm or to - frm > DEPTH_MAX_SPAN_MS:
            raise HTTPException(400, f"0 <= from_ms < to_ms <= now + 1 day, "
                                     f"at most {DEPTH_MAX_SPAN_MS // 3_600_000} h apart")
        wall = depth_wall_ms()
        why = paused_reason(wall / 1000)
        if why:
            raise HTTPException(503, why)
        try:
            body = await depth_pool.grid(root, frm, to, cols, now, wall - time.time() * 1000)
        except (Busy, Paused) as e:
            raise HTTPException(503, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return Response(body, media_type="application/json")

    # the book indicators' history (bookhist.py): the recorded depth files + the tick archive replayed through the
    # same BookTracker the live feed runs; one spawned worker, one request at a time (busy -> 503), the same

    @app.get("/api/book/history")
    async def api_book_history(request: Request):
        q = request.query_params
        root = known_root(q.get("root", ""))
        now = clock()
        try:
            frm, to = int(q["from_ms"]), int(q["to_ms"])
        except (KeyError, ValueError):
            raise HTTPException(400, "from_ms / to_ms: epoch ms") from None
        if frm < 0 or to > now + 86_400_000 or to <= frm or to - frm > BOOK_MAX_SPAN_MS:
            raise HTTPException(400, f"0 <= from_ms < to_ms <= now + 1 day, "
                                     f"at most {BOOK_MAX_SPAN_MS // 3_600_000} h apart")
        wall = depth_wall_ms()
        why = paused_reason(wall / 1000)
        if why:
            raise HTTPException(503, why)
        try:
            body = await book_pool.window(root, frm, to, now, wall - time.time() * 1000)
        except (Busy, Paused) as e:
            raise HTTPException(503, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return Response(body, media_type="application/json")
