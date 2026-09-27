"""Desk-side HTTP for trading from the chart (spec 2026-09-26 desk-on-chart).

/api/trade/* is for the chart service only:
  * the Host header must be exactly 127.0.0.1 or localhost (optional port):
    a DNS-rebinding page (evil.example resolving to 127.0.0.1) arrives with
    Host: evil.example and is refused (controller ruling P4);
  * any request carrying an Origin header is refused (403): browsers send
    one, the chart service does not;
  * every route needs X-Homebase-Key = the hex secret in
    homebase/.state/desk.key (created 0600 at startup); a browser cannot send
    that header cross-origin without a preflight this app never answers.
POST /api/chart-trading is the desk page's own switch + limits: an allowed
Host, JSON only, and an Origin (when present) on the same allowlist
(netguard: loopback + cfg.allowed_hosts).

WriteGuard (Task 5b) is the desk-wide version of that check, on the main
app only (never the tunneled hook app): EVERY request needs an allowed Host
(403) — a rebound page cannot even read /api/tv-setup — and every request
that is not GET/HEAD/OPTIONS also needs an allowed Origin when one is sent
(403) and Content-Type: application/json (415): a web page cannot arm, kill
or place a self-test order with a CORS "simple request". It skips
/api/trade/*, whose own gate above is stricter (loopback Host only, ANY
Origin refused, the desk key).

The SSE stream (/api/trade/stream) obeys ChartDesk's P2 pause (09:29:50-
09:30:30 ET, or any bot `placing`): nothing but fills and the heartbeat is
serialized then; what was held goes out when the pause ends. It ends — and
the desk forgets the reader — when the client disconnects, when it falls
SUB_QUEUE_MAX events behind, when the pause holds more than HELD_MAX events
for it, or when the server cancels the request (uvicorn
--timeout-graceful-shutdown): a client that never reads blocks nothing.
GET /api/trade/state answers 503 in the pause (no snapshot is built then).
GET /api/trade/bot-history answers 503 from 09:29:00 to 09:30:30 ET (and in
the pause): its journal parse runs in a thread, and none starts near the fire. POST /api/trade/bot-kill
(ChartDesk.bot_kill) is never paused and never gated by chart trading: it
is one strategy's emergency stop.
"""
from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Optional

import anyio
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.websockets import WebSocketClose

from . import netguard

KEY_FILE = "desk.key"
BODY_MAX = 16 * 1024
SETTINGS_BODY_MAX = 1024
HEARTBEAT_S = 15.0
PAUSE_POLL_S = 0.25               # how often a stream holding events re-checks the pause
HELD_MAX = 200                    # events a stream may hold in the pause before it ends
TRADE_HOSTS = frozenset({"localhost", "127.0.0.1"})   # /api/trade/*: the chart service only
PAUSED = "paused around the 9:30 fire"
END_HELD = ": end: more than %d events held in the 9:30 pause; reconnect for a fresh state\n\n"
VIEW_EVENTS = ("state", "account", "bot")   # a fresh snapshot supersedes all three
_KEY = re.compile(r"[0-9a-f]{64}")


def ensure_key(path: Path) -> tuple[Optional[str], Optional[str]]:
    """(key, None), creating `path` (32 random bytes as hex, mode 0600) when
    missing; (None, reason) when it cannot be read or holds no key. Never
    raises: the desk must start for the 9:30 bot whatever this file looks
    like — the trade routes then answer 503."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        try:
            key = path.read_text().strip()
            os.chmod(path, 0o600)
        except OSError as e:
            return None, f"{path.name} unreadable: {e}"
        if not _KEY.fullmatch(key):
            return None, (f"{path.name} does not hold a desk key — delete it and restart "
                          "the desk to make a new one")
        return key, None
    except OSError as e:
        return None, f"{path.name} could not be created: {e}"
    key = secrets.token_hex(32)
    with os.fdopen(fd, "w") as f:
        f.write(key + "\n")
    return key, None


def host_is_local(host: Optional[str]) -> bool:
    """The Host header is exactly 127.0.0.1 or localhost, with an optional
    port (P4: DNS rebinding). Hostnames are case-insensitive; nothing else
    — no other loopback spelling, no suffix, no whitespace, no configured
    allowed_hosts — passes: the trade routes serve the local chart service."""
    return netguard.host_allowed(host, TRADE_HOSTS)


def local_host_only(request: Request) -> None:
    if not host_is_local(request.headers.get("host")):
        raise HTTPException(403, "the desk answers only as 127.0.0.1 or localhost")


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def event_stream(desk, *, heartbeat_s: float = HEARTBEAT_S,
                       poll_s: float = PAUSE_POLL_S):
    """`state` first, then every published event in order; a heartbeat when
    nothing was sent for heartbeat_s. Subscribes BEFORE the snapshot, so
    nothing published in between is lost. Ends if the desk dropped this
    reader (it fell SUB_QUEUE_MAX behind): the client reconnects.

    P2: while `desk.views_paused()`, only fills (small, and the user must see
    them) and the heartbeat are serialized. A view event (state/account/bot)
    is not serialized at all: the stream owes a FRESH state instead, sent
    when the pause ends — it supersedes them and carries every fill so far.
    Other events (results) are held and follow it, in order. A stream opened
    in the pause sends its first state when the pause ends; the fills before
    it are in that state."""
    q = desk.subscribe()
    loop = asyncio.get_running_loop()
    need_state = True                  # a state is owed (the first, or one held in the pause)
    started = False                    # the first state went out
    held: list = []                    # non-view events held in the pause, in order
    last = loop.time()
    try:
        while True:
            if (need_state or held) and not desk.views_paused():
                if need_state:
                    need_state, started = False, True
                    yield sse("state", desk.snapshot())
                while held:
                    event, data = held.pop(0)
                    yield sse(event, data)
                last = loop.time()
                continue
            wait = heartbeat_s - (loop.time() - last)
            if need_state or held:
                wait = min(wait, poll_s)
            try:
                event, data = await asyncio.wait_for(q.get(), max(wait, 0.0))
            except asyncio.TimeoutError:
                if loop.time() - last >= heartbeat_s:
                    yield sse("heartbeat", {"ts": time.time()})
                    last = loop.time()
                continue
            if event is None:
                return
            if event == "fill":
                if started:            # before the first state: that state carries it
                    yield sse(event, data)
                    last = loop.time()
                continue
            if not (need_state or held) and not desk.views_paused():
                yield sse(event, data)
                last = loop.time()
            elif event in VIEW_EVENTS:
                need_state = True
            else:
                held.append((event, data))
                if len(held) > HELD_MAX:
                    # an SSE comment: no parser makes an event of it; the
                    # client reconnects and its first event is a fresh state
                    yield END_HELD % HELD_MAX
                    return
    finally:
        desk.unsubscribe(q)


class EventStreamResponse(StreamingResponse):
    """A StreamingResponse that always watches for the client's disconnect
    (whatever the ASGI spec version: Starlette skips that watch at 2.4 and
    would then only notice at the next send) and always closes its generator
    — so the desk unsubscribes the reader at once — on a disconnect, an end
    or a cancel (uvicorn's --timeout-graceful-shutdown). Nothing here waits
    on the client."""

    async def __call__(self, scope, receive, send) -> None:
        try:
            async with anyio.create_task_group() as tg:
                async def stream() -> None:
                    with contextlib.suppress(OSError):   # uvicorn's ClientDisconnected
                        await self.stream_response(send)
                    tg.cancel_scope.cancel()

                tg.start_soon(stream)
                await self.listen_for_disconnect(receive)
                tg.cancel_scope.cancel()
        finally:
            with contextlib.suppress(Exception):
                await self.body_iterator.aclose()


async def read_json(request: Request, limit: int):
    cl = request.headers.get("content-length")
    if cl is not None and (not cl.isdigit() or int(cl) > limit):
        raise HTTPException(413, f"request too large ({limit} bytes max)")
    raw = b""
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > limit:
            raise HTTPException(413, f"request too large ({limit} bytes max)")
    try:
        return json.loads(raw or b"null")
    except ValueError:
        raise HTTPException(400, "the body is not JSON") from None


def trade_router(desk) -> APIRouter:
    r = APIRouter()

    def check(request: Request) -> None:
        local_host_only(request)
        if request.headers.get("origin") is not None:
            raise HTTPException(403, "browser requests are refused — trade through the chart service")
        key = getattr(request.app.state, "desk_key", None)
        if not key:
            raise HTTPException(503, "the desk key is not available — see desk_key_error in the journal")
        got = request.headers.get("x-homebase-key", "")
        if not hmac.compare_digest(got.encode(), key.encode()):
            raise HTTPException(401, "bad or missing X-Homebase-Key")

    @r.get("/state")
    async def trade_state(request: Request):
        check(request)
        if desk.views_paused():             # P2: no snapshot is built around the fire
            return JSONResponse({"error": PAUSED}, 503)
        return desk.snapshot()

    @r.get("/stream")
    async def trade_stream(request: Request):
        check(request)
        return EventStreamResponse(event_stream(desk), media_type="text/event-stream",
                                   headers={"Cache-Control": "no-cache"})

    def post(path: str, fn) -> None:
        async def handler(request: Request):
            check(request)
            body = await read_json(request, BODY_MAX)
            try:
                return await fn(body)
            except ValueError as e:
                raise HTTPException(400, str(e)) from None
        r.add_api_route(path, handler, methods=["POST"], name=f"trade_{path.strip('/')}")

    @r.get("/bot-history")
    async def bot_history(request: Request):
        check(request)
        if desk.history_paused():           # 09:29:00-09:30:30: no journal parse near the fire
            return JSONResponse({"error": PAUSED}, 503)
        q = request.query_params
        try:
            return await desk.bot_history(q.get("strategy"), q.get("days"))
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    post("/order", desk.order)
    post("/modify", desk.modify)
    post("/cancel", desk.cancel)
    post("/cancel-symbol", desk.cancel_symbol)
    post("/flatten", desk.flatten)
    post("/reverse", desk.reverse)
    post("/bot-kill", desk.bot_kill)
    return r


def same_origin_json(request: Request, allowed: frozenset) -> None:
    """The desk page's own POSTs: an allowed Host (P4 — the Origin check
    alone compares Origin to Host, and a rebound page has both = its own
    name), JSON only (a cross-site form cannot send it without a preflight),
    and an Origin, when present, on the same allowlist (netguard)."""
    if not netguard.host_allowed(request.headers.get("host"), allowed):
        raise HTTPException(403, "the desk does not answer to that Host")
    if not netguard.is_json(request.headers.get("content-type")):
        raise HTTPException(415, "send JSON (Content-Type: application/json)")
    origin = request.headers.get("origin")
    if origin is not None and not netguard.origin_allowed(origin, allowed):
        raise HTTPException(403, "changes from another site are refused")


def settings_router(desk) -> APIRouter:
    r = APIRouter()

    @r.post("/api/chart-trading")
    async def chart_trading(request: Request):
        same_origin_json(request, netguard.allowlist(desk.cfg.allowed_hosts))
        body = await read_json(request, SETTINGS_BODY_MAX)
        try:
            out = desk.set_settings(body)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return {"ok": True, "chart_trading": out}

    return r


class WriteGuard:
    """Pure-ASGI guard for the desk's MAIN app (Task 5b + fix round 1):
    netguard.refusal() on every HTTP request — the Host on EVERY method
    (GETs and the /static mount included: a rebound page must not read the
    webhook secret from /api/tv-setup), the Origin and a JSON Content-Type on
    writes. Refusals are {"error": ...} with 403 / 415. It skips
    /api/trade/*, whose own gate is stricter (loopback Host only on every
    method, ANY Origin refused, the desk key). `hosts()` returns the
    configured allowed_hosts, read per request. Pure ASGI (not
    BaseHTTPMiddleware): what passes goes straight through, the SSE stream
    and its disconnect watch untouched.

    WebSocket scopes (none mounted today) get the Host + Origin checks on
    EVERY path, /api/trade/* included: a cross-site page can open a socket
    with no CORS at all. A refusal closes the handshake (1008 -> HTTP 403)."""

    def __init__(self, app, hosts):
        self.app, self.hosts = app, hosts

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "websocket":
            refused = netguard.refusal("WEBSOCKET", scope["headers"],
                                       netguard.allowlist(self.hosts()), require_json=False)
            if refused is None:
                await self.app(scope, receive, send)
            else:
                await WebSocketClose(code=1008, reason=refused[1])(scope, receive, send)
            return
        if scope["type"] != "http" or scope["path"].startswith("/api/trade/"):
            await self.app(scope, receive, send)
            return
        refused = netguard.refusal(scope["method"], scope["headers"],
                                   netguard.allowlist(self.hosts()))
        if refused is None:
            await self.app(scope, receive, send)
            return
        status, error = refused
        await JSONResponse({"error": error}, status)(scope, receive, send)
