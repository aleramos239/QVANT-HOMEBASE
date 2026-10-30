"""TopstepX account socket: a minimal SignalR JSON client (what the topstepx.com site's own client does with skipNegotiation).

Frames end with RS ("\\x1e"). Open: send the protocol line, then invoke SubscribeAccounts. Type 1 = a server call
(`on_event(target, arg)` once per argument), 6 = ping (answered), 7 = the server closes (we reconnect). One hub serves one
TopstepX login; `on_event` is its single sink, and sharing it out to accounts is the caller's job.

The token rides in the URL as `?access_token=`, so it is kept out of every log line: only the host and path are logged and
exception text is scrubbed of it.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import sys
from typing import Awaitable, Callable
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import websockets

from .login_budget import LoginDeferred
from .topstepx_auth import HEADERS, HUB_URL, TsxSession

RS = "\x1e"
RECONNECT_S = (0.2, 1.5, 3.0, 5.0)      # the site's own schedule; the last step repeats
MAX_FRAME = 16 * 1024 * 1024


def log(msg: str) -> None:
    now = dt.datetime.now(ZoneInfo("America/New_York")).strftime("%H:%M:%S")
    print(f"[topstepx_ws] {now} {msg}", file=sys.stderr, flush=True)


class TsxHub:
    def __init__(self, session: TsxSession, on_event: Callable[[str, dict], None], *, url: str = HUB_URL,
                 on_up: Callable[[], Awaitable[None]] | None = None,
                 on_auth_lost: Callable[[], Awaitable[None]] | None = None):
        self.session = session
        self.on_event = on_event
        self.url = url
        self.on_up = on_up
        self.on_auth_lost = on_auth_lost
        self.up = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.up = False

    async def _run(self) -> None:
        step = 0
        while True:
            token = ""
            try:
                token = await self.session.token()
                await self._connected(token)
                step = 0                # it opened: the backoff restarts
            except asyncio.CancelledError:
                raise
            except websockets.InvalidStatus as e:
                code = e.response.status_code
                log(f"open refused: HTTP {code}")
                if code == 401:
                    await self._auth_lost()
            except Exception as e:  # noqa: BLE001 -- the loop must outlive any one failure
                log(f"socket error: {type(e).__name__}: {str(e).replace(token, '***') if token else e}")
            self.up = False
            await asyncio.sleep(RECONNECT_S[min(step, len(RECONNECT_S) - 1)])
            step += 1

    async def _auth_lost(self) -> None:
        try:
            if self.on_auth_lost is not None:
                await self.on_auth_lost()
            else:
                await self.session.relogin("socket 401")
        except LoginDeferred as e:
            log(f"re-login deferred: {e}")
        except Exception as e:  # noqa: BLE001
            log(f"re-login failed: {type(e).__name__}")        # no text: it could carry the credentials' URL or body

    async def _connected(self, token: str) -> None:
        """One socket's life, until it ends."""
        parts = urlsplit(self.url)
        log(f"connecting → {parts.netloc}{parts.path}")
        async with websockets.connect(f"{self.url}?access_token={token}", additional_headers=HEADERS,
                                      max_size=MAX_FRAME) as ws:
            await ws.send(json.dumps({"protocol": "json", "version": 1}) + RS)
            await ws.send(json.dumps({"type": 1, "target": "SubscribeAccounts", "arguments": []}) + RS)
            self.up = True
            log("socket up")
            if self.on_up is not None:
                try:
                    await self.on_up()
                except Exception as e:  # noqa: BLE001
                    log(f"on_up failed: {type(e).__name__}: {e}")
            try:
                async for raw in ws:
                    if not await self._frames(ws, raw):
                        await ws.close()
                        log("server asked to close")
                        break
                else:
                    log(f"socket closed: code={ws.close_code}")
            except websockets.ConnectionClosed:
                log(f"socket closed: code={ws.close_code}")

    async def _frames(self, ws, raw: str | bytes) -> bool:
        """Handle one message (one or more RS-ended records). False when the server sent a close (type 7)."""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        for rec in raw.split(RS):
            if not rec:
                continue
            try:
                msg = json.loads(rec)
            except ValueError:
                log(f"bad frame: {rec[:80]!r}")
                continue
            kind = msg.get("type") if isinstance(msg, dict) else None
            if kind == 1:
                for arg in msg.get("arguments") or []:
                    try:
                        self.on_event(msg.get("target", ""), arg)
                    except Exception as e:  # noqa: BLE001 -- one bad event must not end the feed
                        log(f"event handler error: {type(e).__name__}: {e}")
            elif kind == 6:
                await ws.send(json.dumps({"type": 6}) + RS)
            elif kind == 7:
                return False
        return True
