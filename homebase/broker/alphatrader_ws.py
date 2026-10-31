"""AlphaTrader's T4 trading socket: binary protobuf frames (`alphatrader_proto`), one message per frame.

Each connect: a budget pre-check (no websocket while it says wait), then under `session.lock`: fetch fresh T4 credentials, book a
budget slot, send `loginRequest`, wait for its answer and report it to the budget. On success: `accountSubscribe`, then `up`. Heartbeat every HEARTBEAT_S; SILENT_S with nothing received
closes and reconnects. A drop reconnects on the RECONNECT_S ladder (back to its start after STABLE_S up). T4 ending the session
for another login (`loginResponse` 6, or 7 once up) calls `on_taken` and logs in again at once, through the budget. A refused
login (1/9/18, 24 = a code, or a refused credential fetch) stops the socket with its words in `session.lost`, no retry loop.
One socket serves one AlphaTrader login; `on_event` is its single sink.

The T4 username and password live only inside one login call: never kept, logged or put in an exception's text.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import sys
import time
from typing import Awaitable, Callable
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import websockets

from . import alphatrader_proto as proto
from .alphatrader_auth import CODE_ASKED, HEADERS, WS_URL, AtrLoginFailed, AtrSession, NeedsCode
from .login_budget import LoginDeferred

HEARTBEAT_S = 20.0
SILENT_S = 60.0                          # nothing received this long: close and reconnect (also the login answer's wait)
STABLE_S = 10.0                          # up this long and the reconnect ladder starts over
RECONNECT_S = (1, 2, 4, 8, 15)           # the last step repeats; a deferred login waits the last step too
MAX_FRAME = 16 * 1024 * 1024
TAKEN = "logged in elsewhere"
STOP_WORDS = {proto.LOGIN_FAILED: "T4 login failed", proto.UNAUTHORIZED: "T4 login unauthorized",
              proto.LOCKED_OUT: "T4 login locked out"}

_WIRE_LOG = logging.getLogger(__name__ + ".wire")
_WIRE_LOG.setLevel(logging.INFO)         # websockets logs every frame at DEBUG: the loginRequest's password with it


class _Refused(RuntimeError):
    """T4 refused the login: the socket stops."""


class _Taken(Exception):
    """T4 ended this session for another login."""


async def _pause(seconds: float) -> None:       # tests record / shorten the waits here
    await asyncio.sleep(seconds)


def log(msg: str) -> None:
    now = dt.datetime.now(ZoneInfo("America/New_York")).strftime("%H:%M:%S")
    print(f"[alphatrader_ws] {now} {msg}", file=sys.stderr, flush=True)


class AtrSocket:
    def __init__(self, session: AtrSession, on_event: Callable[[str, dict], None], *, url: str = WS_URL,
                 on_up: Callable[[], Awaitable[None]] | None = None,
                 on_taken: Callable[[str], Awaitable[None]] | None = None):
        self.session = session
        self.on_event = on_event
        self.url = url
        self.on_up = on_up
        self.on_taken = on_taken
        self.up = False
        self._ws = None
        self._task: asyncio.Task | None = None
        self._up_at: float | None = None        # when the current socket logged in (monotonic)

    @property
    def running(self) -> bool:
        """False once stopped, or stopped for good by a refused login (a code asked, a wrong password)."""
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            if task is not asyncio.current_task():     # called from on_up / on_taken: the cancel ends the loop at its next await
                await asyncio.gather(task, return_exceptions=True)
        self.up = False

    async def send(self, payload: str, data: dict) -> None:
        ws = self._ws
        if not self.up or ws is None:
            raise ConnectionError("AlphaTrader T4 socket is down")
        try:
            await ws.send(proto.client(payload, data))
        except websockets.ConnectionClosed:
            raise ConnectionError("AlphaTrader T4 socket closed") from None

    def _log(self, msg: str) -> None:
        log(f"{self.session.key}: {msg}")

    async def _run(self) -> None:
        step = 0
        while True:
            self._up_at = None
            try:
                await self._connected()
            except asyncio.CancelledError:
                raise
            except _Taken:
                self.up = False
                self._log(f"T4 session ended: {TAKEN}")
                if self.on_taken is not None:
                    try:
                        await self.on_taken(TAKEN)
                    except Exception as e:  # noqa: BLE001
                        self._log(f"on_taken failed: {type(e).__name__}: {e}")
                continue                                        # log in again at once; the budget says when to wait
            except (NeedsCode, AtrLoginFailed, _Refused) as e:
                self.session.lost = str(e)
                self._log(f"stopped: {e}")
                return
            except LoginDeferred as e:
                self.session.lost = str(e)
                self._log(f"login deferred: {e}")
                await _pause(RECONNECT_S[-1])
                continue
            except Exception as e:  # noqa: BLE001 -- the loop must outlive any one transport failure
                self._log(f"socket error: {type(e).__name__}: {e}"[:300])
            self.up = False
            if self._up_at is not None and time.monotonic() - self._up_at >= STABLE_S:
                step = 0
            await _pause(RECONNECT_S[min(step, len(RECONNECT_S) - 1)])
            step += 1

    async def _connected(self) -> None:
        """One socket's life, until it drops (returns) or T4 ends it (raises)."""
        s = self.session
        if s.budget is not None and (why := s.budget.blocked(s.key)):
            raise LoginDeferred(why)                    # no bare T4 connect while the budget says wait
        parts = urlsplit(self.url)
        self._log(f"connecting → {parts.netloc}{parts.path}")
        async with websockets.connect(self.url, origin=HEADERS["Origin"], user_agent_header=HEADERS["User-Agent"],
                                      max_size=MAX_FRAME, logger=_WIRE_LOG) as ws:
            await self._login(ws)
            await ws.send(proto.client("accountSubscribe", {"subscribe": proto.ALL_UPDATES, "subscribeAllAccounts": True,
                                                            "uplMode": proto.AVERAGE}))
            beat = asyncio.create_task(self._beat(ws))
            try:
                self._ws, self.up = ws, True
                self.session.lost = None
                self._log("logged in")
                if self.on_up is not None:
                    try:
                        await self.on_up()
                    except Exception as e:  # noqa: BLE001
                        self._log(f"on_up failed: {type(e).__name__}: {e}")
                self._up_at = time.monotonic()
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), SILENT_S)
                    except TimeoutError:
                        self._log(f"nothing received for {SILENT_S:g} s: reconnecting")
                        return
                    except websockets.ConnectionClosed:
                        self._log(f"socket closed: code={ws.close_code}")
                        return
                    self._frame(raw)
            finally:
                self._ws, self.up = None, False
                self.session.lost = None                # stale words (a renewal failed while up) must not read as lost
                beat.cancel()
                await asyncio.gather(beat, return_exceptions=True)

    async def _login(self, ws) -> None:
        s = self.session
        async with s.lock:
            c = await s.t4_creds()
            await s.t4_login_slot()                     # booked after the fetch: a slot is one real T4 login
            await ws.send(proto.client("loginRequest", {"firm": c.firm, "username": c.username, "password": c.password,
                                                        "appName": c.app_name, "appLicense": c.app_license,
                                                        "priceFormat": 0}))
            async with asyncio.timeout(SILENT_S):
                name = ""
                while name != "loginResponse":
                    name, data = proto.server(await ws.recv())
            r = data.get("result", 0)
            if s.budget is not None:
                ok = r in (proto.LOGIN_OK, proto.TWO_FACTOR_REQUIRED)     # a code request is not a failed login
                s.budget.login_result(s.key, None if ok else f"T4 login result {r}")
            if r == proto.LOGIN_OK:
                try:
                    self.on_event(name, data)           # the adapters read loginResponse.accounts (no credential in it)
                except Exception as e:  # noqa: BLE001
                    self._log(f"event handler error: {type(e).__name__}: {e}")
                return
            if r == proto.LOGGED_IN_ELSEWHERE:
                raise _Taken()
            if r == proto.TWO_FACTOR_REQUIRED:
                raise NeedsCode(CODE_ASKED)
            if r in STOP_WORDS:
                why = data.get("errorMessage", "")
                for secret in (c.username, c.password):
                    why = why.replace(secret, "***") if secret else why
                raise _Refused(f"{STOP_WORDS[r]}: {why}"[:200] if why else STOP_WORDS[r])
            raise ConnectionError(f"T4 login result {r}")       # 7 before up, or a result we do not know: a drop

    def _frame(self, raw) -> None:
        try:
            name, data = proto.server(raw)
        except (ValueError, TypeError):
            self._log("bad frame skipped")
            return
        if name in ("", "heartbeat"):
            return
        if name == "loginResponse" and data.get("result", 0) in (proto.LOGGED_IN_ELSEWHERE, proto.LOGOUT):
            raise _Taken()
        try:
            self.on_event(name, data)
        except Exception as e:  # noqa: BLE001 -- one bad event must not end the feed
            self._log(f"event handler error: {type(e).__name__}: {e}")

    async def _beat(self, ws) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_S)
            await ws.send(proto.client("heartbeat", {"timestamp": int(time.time() * 1000)}))
