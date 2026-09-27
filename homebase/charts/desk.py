"""The chart service's link to the desk (spec 2026-09-26 desk-on-chart).

Only the desk (:8850) talks to the broker's order API. This module:
  * DeskLink: one SSE connection to the desk's /api/trade/stream (key from
    homebase/.state/desk.key), reconnecting 1 s -> 30 s. Each event goes to
    every page over the existing /ws as {"type": "desk", "event": <state|
    account|bot|fill|result>, "data": ...}; while the desk is unreachable:
    {"type": "desk", "down": "<reason>"} and the page disables trading.
    (The spec writes {"t": "desk"}; every /ws message is keyed on "type".)
  * Fanout: those messages to every page without ever waiting on one. Each
    page has a bounded outbox; a page that falls behind loses its oldest
    messages and is resynced with a fresh full state (DeskLink.hello()).
  * register(): POST /api/desk/{order|modify|cancel|cancel-symbol|flatten|
    reverse} -> the desk's /api/trade/*, after the Host check (netguard's
    shared allowlist — DNS rebinding, ruling P4), the page-origin check and
    the JSON-only rule, with the body capped at 4 KB, the key added, and
    `quotes` (this service's latest quote per root) attached for the desk's
    stop-side check.
  * Quotes: bid/ask for the Buy/Sell buttons, "as of last trade": every tick
    the md feed delivers carries the quote at that trade. Decided
    2026-09-26: no md quote subscription — nothing in the repo shows one is
    exempt from the 180 requests/hour md budget, and that budget belongs to
    the login whose feed the 9:30 bot anchors on.

The desk key is read from its file for each request and kept nowhere else:
it never goes to a page, into a log line, or into /api/status. In replay
there is no DeskLink at all and the proxy answers 503 (ruling 10).
In replay the link may point at the fake desk (tools/fake_desk.py) only.
"""
from __future__ import annotations

import asyncio
import copy
import json
import math
import re
from collections import deque
from pathlib import Path
from typing import AsyncIterator, Callable, Hashable, Optional

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from .. import netguard

DESK_URL = "http://127.0.0.1:8850"
ACTIONS = ("order", "modify", "cancel", "cancel-symbol", "flatten", "reverse")
BODY_MAX = 4096
LINE_MAX = 256 * 1024          # an SSE line, or one event's joined data, over this: drop + reconnect
BACKOFF_S = (1, 2, 4, 8, 16, 30)
READ_TIMEOUT_S = 45.0          # three missed 15 s heartbeats = the desk is gone
POST_TIMEOUT_S = 20.0
DESK_QUEUE_MAX = 64            # desk messages held per page before its oldest are dropped
NOTICES = ("fill", "result")   # events a fresh state does not carry: kept across a resync
NO_LINK = "chart trading is not available here (replay, or started without the desk link)"
UNAVAILABLE = "desk link unavailable"
PAUSED = "desk paused around 9:30 — reconnecting"
# the desk_api.py END_HELD comment's prefix (": end: more than %d events held in the 9:30
# pause; reconnect for a fresh state"): the ONLY case where a clean stream end is not "down"
_PAUSE_MARK = ": end: more than "
_KEY = re.compile(r"[0-9a-f]{64}")


class DeskDown(Exception):
    """The desk cannot be reached or refused us; str(e) is shown to the page."""


class _NonFiniteNumber(ValueError):
    """Raised by _reject_nonfinite so the proxy answers 400 "invalid number",
    not the generic "the body is not JSON" (json.loads otherwise accepts the
    non-standard NaN/Infinity/-Infinity tokens as float values)."""


def _reject_nonfinite(token: str):
    raise _NonFiniteNumber(token)


def _f(v) -> Optional[float]:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


class SSEParser:
    """text/event-stream, line by line: `event:` and `data:` fields, a blank
    line ends one event, `:` lines are comments; data lines join with \\n.
    A line, or one event's joined data, over LINE_MAX raises DeskDown: the
    event is dropped and the caller (DeskLink.run) reconnects rather than
    holding an unbounded buffer for a runaway or hostile stream."""

    def __init__(self):
        self._event, self._data, self._size = "message", [], 0

    def feed(self, line: str):
        if len(line) > LINE_MAX:
            self._event, self._data, self._size = "message", [], 0
            raise DeskDown("desk stream line too large (over 256 KB) — reconnecting")
        if line == "":
            if not self._data:
                self._event = "message"
                return None
            out = (self._event, "\n".join(self._data))
            self._event, self._data, self._size = "message", [], 0
            return out
        if line.startswith(":"):
            return None
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "event":
            self._event = value
        elif field == "data":
            self._size += len(value) + 1
            if self._size > LINE_MAX:
                self._event, self._data, self._size = "message", [], 0
                raise DeskDown("desk stream event too large (over 256 KB) — reconnecting")
            self._data.append(value)
        return None


class Quotes:
    """Last bid/ask/trade per root, from the tick rows (the quote AT each
    trade). A crossed or missing quote keeps the previous bid/ask."""

    def __init__(self):
        self._q: dict[str, dict] = {}
        self._dirty: set[str] = set()

    def note(self, root: str, rows: list) -> None:
        if not rows:
            return
        q = dict(self._q.get(root) or {"bid": None, "ask": None})
        for r in rows:
            bid, ask = _f(r.get("bid")), _f(r.get("ask"))
            if bid is not None and ask is not None and bid <= ask:
                q["bid"], q["ask"] = bid, ask
            q["last"], q["ts_ms"] = float(r["price"]), int(r["ts_ms"])
        self._q[root] = q
        self._dirty.add(root)

    def snapshot(self) -> dict:
        return {r: dict(q) for r, q in self._q.items()}

    def drain(self) -> list[dict]:
        out = [{"type": "quote", "root": r, **self._q[r], "asof": "last_trade"}
               for r in sorted(self._dirty)]
        self._dirty.clear()
        return out


class _Outbox:
    """One page's desk messages. put() never waits: past `maxlen` the oldest
    is dropped and the page owes a resync (a fresh full state)."""

    def __init__(self, send: Callable[[dict], None], room: Callable[[], bool], maxlen: int):
        self.send, self.room = send, room
        self.q: deque = deque()
        self.maxlen = maxlen
        self.resync = True                   # a new page is greeted with hello()

    def put(self, msg: dict) -> None:
        if len(self.q) >= self.maxlen:
            # drop the oldest VIEW event (state/account/bot/down) first -- a
            # fresh state at the next resync replaces it anyway. A fill or
            # result notice is dropped only once nothing else is left to give.
            for i, m in enumerate(self.q):
                if m.get("event") not in NOTICES:
                    del self.q[i]
                    break
            else:
                self.q.popleft()
            self.resync = True
        self.q.append(msg)

    def flush(self, hello: Callable[[], dict]) -> None:
        while self.room():
            if self.resync:
                # the fresh state supersedes every queued state/account/bot/
                # down message; fills and results are not in it, so they stay
                self.resync = False
                self.q = deque(m for m in self.q if m.get("event") in NOTICES)
                self.send(hello())
            elif self.q:
                self.send(self.q.popleft())
            else:
                return


class Fanout:
    """Desk messages to every page, never waiting on any of them: the SSE
    reader calls publish() and returns at once whatever the pages do.

    attach(key, send, room): `send(msg)` must not block (the chart service's
    Conn.send queues); `room()` says whether that page's socket can take
    more now. What a page cannot take waits in its outbox until the next
    publish() or flush() (the chart service's pump calls it). A page whose
    send raises is detached."""

    def __init__(self, hello: Optional[Callable[[], dict]] = None, *,
                 maxlen: int = DESK_QUEUE_MAX):
        self.hello = hello or (lambda: {"type": "desk", "down": NO_LINK})
        self.maxlen = maxlen
        self._boxes: dict[Hashable, _Outbox] = {}

    def attach(self, key: Hashable, send: Callable[[dict], None],
               room: Callable[[], bool]) -> None:
        self._boxes[key] = _Outbox(send, room, self.maxlen)
        self._flush(key)

    def detach(self, key: Hashable) -> None:
        self._boxes.pop(key, None)

    def publish(self, msg: dict) -> None:
        for box in self._boxes.values():
            box.put(msg)
        self.flush()

    def flush(self) -> None:
        for key in list(self._boxes):
            self._flush(key)

    def _flush(self, key: Hashable) -> None:
        box = self._boxes.get(key)
        if box is None:
            return
        try:
            box.flush(self.hello)
        except Exception:  # noqa: BLE001 — one broken page never stops the others
            self._boxes.pop(key, None)


class DeskLink:
    def __init__(self, fanout: Callable[[dict], None], *, key_path, url: str = DESK_URL,
                 transport: Optional[httpx.AsyncBaseTransport] = None, sleep=asyncio.sleep):
        self.fanout = fanout                  # (msg) -> None: never waits (Fanout.publish)
        self.key_path = Path(key_path)
        self.url = url
        self._transport = transport
        self._sleep = sleep
        self.state: Optional[dict] = None
        self.down: Optional[str] = "connecting to the desk"
        self._stop = False

    def key(self) -> str:
        """The desk key, read now. Never stored on the link, never logged:
        a DeskDown's text says what is wrong, not what the file holds."""
        try:
            k = self.key_path.read_text().strip()
        except FileNotFoundError:
            raise DeskDown("desk key missing — start the desk "
                           "(it creates homebase/.state/desk.key)") from None
        except (OSError, UnicodeDecodeError):
            raise DeskDown("desk key unreadable") from None
        if not _KEY.fullmatch(k):
            raise DeskDown("desk key unreadable")
        return k

    def _client(self, timeout) -> httpx.AsyncClient:
        # trust_env=False: a proxy from the environment must never carry the key
        return httpx.AsyncClient(timeout=timeout, transport=self._transport, trust_env=False)

    def hello(self) -> dict:
        """What a page gets when it connects or resyncs (a copy: later events
        must not change a message already queued to a page)."""
        if self.down is not None or self.state is None:
            return {"type": "desk", "down": self.down or "connecting to the desk"}
        return {"type": "desk", "event": "state", "data": copy.deepcopy(self.state)}

    def _apply(self, event: str, data) -> None:
        if event == "state":
            self.state = copy.deepcopy(data)      # the fanned-out `data` is never mutated
        elif event == "account" and isinstance(data, dict) and self.state is not None:
            accts = self.state.setdefault("accounts", [])
            for i, a in enumerate(accts):
                if a.get("id") == data.get("id"):
                    accts[i] = data
                    break
            else:
                accts.append(data)
        elif event == "bot" and self.state is not None:
            self.state["bot"] = data
        # fill / result: passed through, nothing cached

    def on_event(self, event: str, raw: str) -> None:
        if event == "heartbeat":
            return
        try:
            data = json.loads(raw)
        except ValueError:
            return
        if event == "state":
            if not isinstance(data, dict):
                return
            self.down = None
        elif self.down is not None:
            return                                   # nothing to build on before a state
        self._apply(event, data)
        self.fanout({"type": "desk", "event": event, "data": data})

    def _set_down(self, reason: str) -> None:
        self.state = None
        if reason != self.down:                      # announced once per change, not per retry
            self.down = reason
            self.fanout({"type": "desk", "down": reason})

    async def _lines(self, key: str) -> AsyncIterator[str]:
        async with self._client(httpx.Timeout(10.0, read=READ_TIMEOUT_S)) as c:
            async with c.stream("GET", f"{self.url}/api/trade/stream",
                                headers={"X-Homebase-Key": key}) as r:
                if r.status_code != 200:
                    raise DeskDown(f"desk refused the stream: HTTP {r.status_code}")
                async for line in r.aiter_lines():
                    yield line

    async def run(self) -> None:
        attempt = 0
        while not self._stop:
            paused = False        # the desk's END_HELD comment: a deliberate close, not a failure
            try:
                key = self.key()
                parser = SSEParser()
                async for line in self._lines(key):
                    if line.startswith(_PAUSE_MARK):
                        paused = True
                    got = parser.feed(line)
                    if got is not None:
                        self.on_event(*got)
                        if got[0] == "state":
                            attempt = 0
                reason = PAUSED if paused else "the desk closed the stream"
            except DeskDown as e:
                reason = str(e)
            except Exception as e:  # noqa: BLE001 — any failure: down, then retry with backoff
                reason = f"desk unreachable: {type(e).__name__}: {e}"[:200]
            if self._stop:
                break
            self._set_down(reason)
            await self._sleep(BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)])
            attempt += 1

    def stop(self) -> None:
        self._stop = True

    async def post(self, action: str, body: dict) -> tuple[int, dict]:
        try:
            key = self.key()
        except DeskDown as e:
            return 503, {"detail": f"{UNAVAILABLE}: {e}"}
        try:
            async with self._client(POST_TIMEOUT_S) as c:
                r = await c.post(f"{self.url}/api/trade/{action}", json=body,
                                 headers={"X-Homebase-Key": key})
        except httpx.TimeoutException:
            return 504, {"detail": f"no answer from the desk in {POST_TIMEOUT_S:.0f} s — "
                                   "check the Orders tab before trying again"}
        except Exception as e:  # noqa: BLE001
            return 502, {"detail": f"desk unreachable: {type(e).__name__}"}
        try:
            data = r.json()
        except ValueError:
            data = {"detail": r.text[:200]}
        return r.status_code, data if isinstance(data, dict) else {"detail": data}


def register(app, *, link: Optional[DeskLink], quotes: Quotes, browser_write_ok,
             allowed: frozenset = netguard.allowlist()) -> None:
    """POST /api/desk/{action}: the page's trading requests, relayed to the desk.
    Refused in this order: a Host off the shared allowlist (403, a DNS-rebound
    page), an Origin off it (403), not application/json (415), then the
    chart service's own origin rule (browser_write_ok, 403)."""

    @app.post("/api/desk/{action}")
    async def desk_proxy(action: str, request: Request):
        bad = netguard.refusal(request.method, request.scope["headers"], allowed)
        if bad is not None:
            raise HTTPException(*bad)
        browser_write_ok(request)
        if action not in ACTIONS:
            raise HTTPException(404, f"unknown desk action {action!r}")
        if link is None:
            raise HTTPException(503, NO_LINK)
        cl = request.headers.get("content-length")
        if cl is not None and (not cl.isdigit() or int(cl) > BODY_MAX):
            raise HTTPException(413, "request too large (4 KB max)")
        raw = b""
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > BODY_MAX:
                raise HTTPException(413, "request too large (4 KB max)")
        try:
            body = json.loads(raw, parse_constant=_reject_nonfinite)
        except _NonFiniteNumber:
            raise HTTPException(400, "invalid number") from None
        except ValueError:
            raise HTTPException(400, "the body is not JSON") from None
        if not isinstance(body, dict):
            raise HTTPException(400, "the body is a JSON object")
        body["quotes"] = quotes.snapshot()          # ours, never the page's
        status, data = await link.post(action, body)
        return JSONResponse(data, status_code=status)
