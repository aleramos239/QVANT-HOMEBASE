"""Live ticks from the broker for the charts: ONE md socket and ONE Tick
chart subscription per root, however many charts are open.

The md budget (180 chart requests/hour/login; a burst penalizes the whole
hour) is shared with the trading process when both ride one login, so:
every request is counted (status shows the hour's total), a rate-limit
reply is honored with its p-ticket, and reconnects back off 5 s doubling
to 5 min, so a flapping socket can neither burn the hour nor trip the auth
captcha. Each (re)connect reads the freshest md token the desk has on disk.

A symbol the feed refuses is isolated: the other roots stay subscribed, it
is asked again every 10 min (never 09:20-09:35 ET) and on every reconnect.
A fresh socket that refuses EVERY root is replaced, but no faster than that
10-min retry: a login that refuses everything must not spend 11 getCharts
per 5 s-5 min backoff step (~187 in the first hour, over the 180 budget).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import time
from typing import Awaitable, Callable, Optional

from .. import symbols
from .. import ticks as T
from . import MD_ENV, QUIET
from .session import ET

BACKOFF_S = (5, 10, 20, 40, 80, 160, 300)
HEALTHY_S = 600          # a connection that lived this long resets the backoff
RETRY_REFUSED_S = 600    # a root the feed refused is asked again this often (and on every reconnect)


def in_quiet(ts_s: float) -> bool:
    """Is epoch time ts_s inside the 09:20-09:35 ET window around the 9:30
    fire, when this process sends no optional md requests?"""
    return QUIET[0] <= dt.datetime.fromtimestamp(ts_s, ET).time() < QUIET[1]


class Refused(RuntimeError):
    """The md feed will not chart this root: getChart answered without a
    realtimeId or failed (a non-200 status, no answer in 15 s) while the
    socket stayed up, or the root has no resolvable contract."""


async def connect_default():
    return await T.connect_md(prefer_live=(MD_ENV == "live"))


class TickFeed:
    def __init__(self, roots, on_ticks: Callable[[str, str, list], None],
                 on_subscribed: Optional[Callable[[str, str, Optional[int]], Awaitable[None]]] = None,
                 connect=connect_default, sleep=asyncio.sleep, now=time.time):
        self.roots = [r.upper() for r in roots]
        self.on_ticks = on_ticks
        self.on_subscribed = on_subscribed
        self._connect, self._sleep, self._now = connect, sleep, now
        self.ws = None
        self.subs: dict[int, tuple[str, str]] = {}
        self.contracts: dict[str, str] = {}
        self.last_tick: dict[str, float] = {}      # root -> wall time of the last delivery
        self.last_ms: dict[str, int] = {}          # root -> newest tick timestamp delivered
        self.refused: dict[str, str] = {}          # root -> why the feed refused it
        self._requests: list[float] = []
        self.reconnects = 0
        self.error: Optional[str] = None
        self._stop = False
        self._tasks: set = set()

    def count_request(self) -> None:
        self._requests.append(self._now())

    def budget_used(self) -> int:
        cut = self._now() - 3600
        self._requests = [t for t in self._requests if t > cut]
        return len(self._requests)

    @property
    def connected(self) -> bool:
        return bool(self.ws is not None and getattr(self.ws, "connected", False))

    def status(self) -> dict:
        now = self._now()
        return {"mode": "live", "md": MD_ENV, "connected": self.connected, "error": self.error,
                "reconnects": self.reconnects, "budget_hour": self.budget_used(),
                "roots": {r: {"contract": self.contracts.get(r),
                              "last_tick_age_s": (round(now - self.last_tick[r], 1)
                                                  if r in self.last_tick else None),
                              "error": self.refused.get(r)}
                          for r in self.roots}}

    def _on_event(self, msg: dict) -> None:
        if msg.get("e") != "chart":
            return
        for ch in (msg.get("d") or {}).get("charts", []) or []:
            sub = self.subs.get(ch.get("id"))
            if sub is None or not ch.get("tks"):
                continue
            rows = T._unpack(ch)
            if rows:
                root = sub[0]
                self.last_tick[root] = self._now()
                self.last_ms[root] = max(self.last_ms.get(root, 0), max(r["ts_ms"] for r in rows))
                self.on_ticks(root, sub[1], rows)

    async def subscribe(self, root: str) -> str:
        try:
            contract = symbols.resolve_contract(root)
        except ValueError as e:
            raise Refused(f"{root}: no front contract ({e})") from None
        body = {"symbol": contract,
                "chartDescription": {"underlyingType": "Tick", "elementSize": 1,
                                     "elementSizeUnit": "UnderlyingUnits", "withHistogram": False},
                "timeRange": {"asMuchAsElements": 1}}
        d = None
        for _ in range(3):
            self.count_request()
            try:
                d = await self.ws.request("md/getChart", body)
            except (RuntimeError, TimeoutError) as e:
                # TradovateWS.request raises on a non-200 status and after 15 s
                # without an answer. With the socket still up that is THIS
                # symbol's refusal; with it gone (a timeout because the reader
                # died, or "websocket not connected" once the socket is
                # CLOSING) the whole feed reconnects. .connected itself only
                # flips in the reader's finally, so it can still read True on
                # a socket that already raises that message -- check the
                # message too, not just the flag.
                if not self.connected or str(e) == "websocket not connected":
                    raise
                why = str(e) or f"md/getChart {type(e).__name__}"      # a timeout has no message
                raise Refused(f"{contract}: {why}") from None
            if isinstance(d, dict) and d.get("p-ticket"):
                pen = T.Penalty(d)
                await self._sleep(pen.wait_s + 1)
                body = {**body, "p-ticket": pen.ticket}
                continue
            break
        if not isinstance(d, dict) or d.get("realtimeId") is None:
            raise Refused(f"{contract}: getChart refused: {d!r}")
        for k in ("historicalId", "realtimeId"):
            if d.get(k) is not None:
                self.subs[int(d[k])] = (root, contract)
        self.contracts[root] = contract
        return contract

    def _on_subscribed_done(self, root: str, t: "asyncio.Task") -> None:
        self._tasks.discard(t)
        if t.cancelled():
            return
        e = t.exception()
        if e is not None:
            self.error = f"refill {root}: {type(e).__name__}: {e}"

    async def _start(self, root: str) -> None:
        """Subscribe one root and start its gap refill. A root the feed
        refuses is recorded for status() and retried later: it must never
        take the other roots' subscriptions down with it (a raise here used
        to tear the whole socket down and loop reconnecting every root)."""
        since = self.last_ms.get(root)
        try:
            contract = await self.subscribe(root)
        except Refused as e:
            self.refused[root] = str(e)
            return
        self.refused.pop(root, None)
        if self.on_subscribed is not None:
            t = asyncio.create_task(self.on_subscribed(root, contract, since))
            self._tasks.add(t)
            t.add_done_callback(lambda t, root=root: self._on_subscribed_done(root, t))

    def _quiet(self) -> bool:
        """Inside the 09:20-09:35 ET window around the 9:30 fire."""
        return in_quiet(self._now())

    def _extend_past_quiet(self, wait: float) -> float:
        """If reconnecting `wait` seconds from now would land inside the
        quiet window, push the wait out to end exactly at QUIET[1] (09:35 ET)
        instead: a refused-all reconnect costs one getChart per root, and
        that must never fire inside the 9:30 desk's window."""
        now = self._now()
        when = dt.datetime.fromtimestamp(now + wait, ET)
        if QUIET[0] <= when.time() < QUIET[1]:
            end = when.replace(hour=QUIET[1].hour, minute=QUIET[1].minute, second=0, microsecond=0)
            return end.timestamp() - now
        return wait

    async def run(self) -> None:
        attempt = 0
        while not self._stop:
            started = self._now()
            refused_all = False
            try:
                self.ws = await self._connect()
                self.error = None            # a fresh cycle; a refill error below now sticks
                self.ws.event_handlers.append(self._on_event)
                self.subs = {}
                self.refused = {}
                for r in self.roots:
                    await self._start(r)
                if self.roots and all(r in self.refused for r in self.roots):
                    # nothing subscribed: the socket or the login is sick, not a symbol
                    refused_all = True
                    raise Refused("every symbol refused")
                next_retry = self._now() + RETRY_REFUSED_S
                while not self._stop and self.connected:
                    await self._sleep(1)
                    if self.refused and self._now() >= next_retry and not self._quiet():
                        next_retry = self._now() + RETRY_REFUSED_S
                        for r in list(self.refused):
                            if self._quiet():   # a round can straddle 09:20; re-check every root, not once
                                break
                            await self._start(r)
                if not self._stop:
                    self.error = "md socket closed"
            except Exception as e:  # noqa: BLE001 — any failure = reconnect with backoff
                self.error = f"{type(e).__name__}: {e}"
            finally:
                ws, self.ws = self.ws, None
                if ws is not None:
                    try:
                        await ws.close()
                    except Exception:  # noqa: BLE001
                        pass
            if self._stop:
                break
            if self._now() - started >= HEALTHY_S:
                attempt = 0
            self.reconnects += 1
            wait = BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)]
            if refused_all:
                wait = max(wait, RETRY_REFUSED_S)   # each such round costs one getChart per root
                wait = self._extend_past_quiet(wait)
            await self._sleep(wait)
            attempt += 1

    def stop(self) -> None:
        self._stop = True
