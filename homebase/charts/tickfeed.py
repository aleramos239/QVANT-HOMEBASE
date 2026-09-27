"""Live ticks from the broker for the charts: ONE md socket and ONE Tick
chart subscription per root, however many charts are open.

The md budget (180 chart requests/hour/login; a burst penalizes the whole
hour) is shared with the trading process when both ride one login, so:
every request is counted (status shows the hour's total, per login -- see
`budget_used`), a rate-limit reply is honored with its p-ticket, and
reconnects back off 5 s doubling to 5 min, so a flapping socket can neither
burn the hour nor trip the auth captcha. Each (re)connect reads the
freshest md token the desk has on disk.

A symbol the feed refuses is isolated: the other roots stay subscribed, it
is asked again every 10 min (never 09:20-09:35 ET) and on every reconnect.
A fresh socket that refuses EVERY root is replaced, but no faster than that
10-min retry: a login that refuses everything must not spend 11 getCharts
per 5 s-5 min backoff step (~187 in the first hour, over the 180 budget).

Runtime login switch (Task 4, 2026-09-27 app-settings plan; hardened in Fix
round 1 after review of bdaccbd -- C1/C2/I1/I4/M3): `switch_md()` only ever
leaves a REQUEST for `run()` to service. There is never a second connector
racing the feed's own reconnect loop, never two live sockets, and a socket
already serving the page keeps doing so, untouched, until a replacement is
fully validated. See `run()`'s docstring for the mechanism.
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
MD_ENVS = ("live", "demo")


def in_quiet(ts_s: float) -> bool:
    """Is epoch time ts_s inside the 09:20-09:35 ET window around the 9:30
    fire, when this process sends no optional md requests?"""
    return QUIET[0] <= dt.datetime.fromtimestamp(ts_s, ET).time() < QUIET[1]


class Refused(RuntimeError):
    """The md feed will not chart this root: getChart answered without a
    realtimeId or failed (a non-200 status, no answer in 15 s) while the
    socket stayed up, or the root has no resolvable contract."""


class SwitchInProgress(RuntimeError):
    """switch_md() was called while an earlier switch is still being
    serviced by run(): the caller (PUT /api/settings) turns this into a
    409, never a queued second attempt."""


async def connect_env(env: str) -> "T.TradovateWS":
    """Connect under `env`'s login ("live"|"demo") -- never a login of its
    own (see ticks.md_token). `run()` (below) is the only caller in
    production; IT is what checks the socket really is the login asked for
    (review C2: `prefer_live` is a preference, not a guarantee -- md_token
    silently falls back to the other login's token when the one asked for
    has none valid on disk)."""
    return await T.connect_md(prefer_live=(env == "live"))


class TickFeed:
    def __init__(self, roots, on_ticks: Callable[[str, str, list], None],
                 on_subscribed: Optional[Callable[[str, str, Optional[int]], Awaitable[None]]] = None,
                 connect=None, connect_env=connect_env, sleep=asyncio.sleep, now=time.time,
                 md_env: Optional[str] = None):
        self.roots = [r.upper() for r in roots]
        self.on_ticks = on_ticks
        self.on_subscribed = on_subscribed
        # md_env: the ACTIVE login (Task 4, 2026-09-27 app-settings plan): defaults to MD_ENV (the
        # env var / today's behaviour) so a caller that never touches this is unaffected. It only
        # ever changes once run() has actually connected AND subscribed at least one root under
        # the new value -- never optimistically (review C1/I1).
        self.md_env = md_env if md_env is not None else MD_ENV
        self._connect_env = connect_env
        # `connect`, if given, is the zero-arg seam every pre-Task-4 test already uses (it never
        # cares which login: those tests never touch switch_md). The default routes through
        # connect_env(env) so a real switch (which DOES care which login) can ask for a specific
        # one; ordinary reconnects call it with self.md_env, exactly as before.
        self._connect = connect or (lambda: self._connect_env(self.md_env))
        self._sleep, self._now = sleep, now
        self.ws = None
        self.subs: dict[int, tuple[str, str]] = {}
        self.contracts: dict[str, str] = {}
        self.last_tick: dict[str, float] = {}      # root -> wall time of the last delivery
        self.last_ms: dict[str, int] = {}          # root -> newest tick timestamp delivered
        self.refused: dict[str, str] = {}          # root -> why the feed refused it
        # the 180/hour budget is per LOGIN (review I3): switching must not let the fresh login's
        # own hour inherit whatever the OTHER login already spent, nor hide what it has itself
        # spent from an earlier stint on it.
        self._requests: dict[str, list[float]] = {}
        self._request_env = self.md_env    # which login count_request() charges right now
        self.reconnects = 0
        self.error: Optional[str] = None
        # I2: the last switch_md that failed ITS OWN attempt (not an ordinary reconnect drop),
        # cleared the moment any switch (to any login) next succeeds.
        self.switch_error: Optional[dict] = None
        self._stop = False
        self._tasks: set = set()
        # C1: a switch is a REQUEST, consumed by run() itself -- never a second connector.
        self._pending_env: Optional[str] = None
        self._pending_fut: Optional["asyncio.Future"] = None
        self._wake = asyncio.Event()   # lets switch_md interrupt a backoff/idle wait immediately

    def count_request(self) -> None:
        self._requests.setdefault(self._request_env, []).append(self._now())

    def budget_used(self, env: Optional[str] = None) -> int:
        """Chart requests in the last hour on `env`'s login (default: the currently ACTIVE
        login). Each login keeps its own window (review I3)."""
        env = env or self.md_env
        cut = self._now() - 3600
        kept = [t for t in self._requests.get(env, []) if t > cut]
        self._requests[env] = kept
        return len(kept)

    @property
    def connected(self) -> bool:
        return bool(self.ws is not None and getattr(self.ws, "connected", False))

    @property
    def switch_in_progress(self) -> bool:
        """True from the moment switch_md registers a request until run() resolves it. The PUT
        route checks this BEFORE its cooldown (review I3): a second request for an already-
        in-flight switch is "already in progress" (409), not "too soon" (429) -- those are
        different situations even though switch_md itself would raise SwitchInProgress either
        way."""
        return self._pending_fut is not None

    def status(self) -> dict:
        now = self._now()
        return {"mode": "live", "md": self.md_env, "connected": self.connected, "error": self.error,
                "switch_error": self.switch_error,
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

    async def subscribe(self, root: str, subs: Optional[dict] = None,
                        allow_penalty_wait: bool = True) -> str:
        """`subs` (review I1/M3): where a fresh subscription id is recorded. Defaults to
        `self.subs` -- every pre-Task-4 caller (including every direct `feed.subscribe(...)`
        test) is unaffected. run() passes an explicit LOCAL dict while a switch is validating a
        new socket, so an old-but-still-live socket keeps routing through the UNCHANGED
        `self.subs` until the new one is proven and committed.

        `allow_penalty_wait=False` (review I3): a p-ticket is refused immediately instead of
        waiting it out -- run() passes this while subscribing a SWITCH's candidate socket, so a
        rate limit there counts toward "did the new login do worse than the old one" (see run())
        rather than stalling the PUT /api/settings request that is awaiting the switch."""
        subs = self.subs if subs is None else subs
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
                if not allow_penalty_wait:
                    raise Refused(f"{contract}: rate-limited (p-ticket) during a login switch")
                pen = T.Penalty(d)
                await self._sleep(pen.wait_s + 1)
                body = {**body, "p-ticket": pen.ticket}
                continue
            break
        if not isinstance(d, dict) or d.get("realtimeId") is None:
            raise Refused(f"{contract}: getChart refused: {d!r}")
        for k in ("historicalId", "realtimeId"):
            if d.get(k) is not None:
                subs[int(d[k])] = (root, contract)
        self.contracts[root] = contract
        return contract

    def _on_subscribed_done(self, root: str, t: "asyncio.Task") -> None:
        self._tasks.discard(t)
        if t.cancelled():
            return
        e = t.exception()
        if e is not None:
            self.error = f"refill {root}: {type(e).__name__}: {e}"

    async def _start(self, root: str, subs: Optional[dict] = None,
                     allow_penalty_wait: bool = True) -> None:
        """Subscribe one root and start its gap refill. A root the feed
        refuses is recorded for status() and retried later: it must never
        take the other roots' subscriptions down with it (a raise here used
        to tear the whole socket down and loop reconnecting every root)."""
        since = self.last_ms.get(root)
        try:
            contract = await self.subscribe(root, subs=subs, allow_penalty_wait=allow_penalty_wait)
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

    async def _wait(self, seconds: float) -> None:
        """`self._sleep(seconds)` (the exact test seam every existing test already patches),
        but preemptible: switch_md sets `self._wake` so a manual switch does not sit through a
        multi-minute backoff, or up to a second of the steady-state poll (review C1's "switch
        during backoff" race)."""
        self._wake.clear()
        sleeper = asyncio.ensure_future(self._sleep(seconds))
        waiter = asyncio.ensure_future(self._wake.wait())
        try:
            await asyncio.wait({sleeper, waiter}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in (sleeper, waiter):
                if not t.done():
                    t.cancel()
            await asyncio.gather(sleeper, waiter, return_exceptions=True)

    def _resolve_pending(self, requested_env: str, error: Optional[BaseException]) -> None:
        """Finishes the switch run() just serviced (successfully or not): clears the request so
        the next iteration goes back to normal reconnects, resolves switch_md's Future (its
        caller -- the PUT route -- is awaiting it), and records/clears switch_error (I2)."""
        fut, self._pending_fut = self._pending_fut, None
        self._pending_env = None
        if error is None:
            self.switch_error = None
        else:
            self.switch_error = {"to": requested_env, "error": f"{type(error).__name__}: {error}",
                                 "at": self._now()}
        if fut is not None and not fut.done():
            if error is None:
                fut.set_result(self.md_env)
            else:
                fut.set_exception(error if isinstance(error, Exception) else RuntimeError(str(error)))

    async def run(self) -> None:
        """The ONLY thing that ever connects or subscribes -- switch_md (below) just leaves a
        request (`self._pending_env` + a Future) and wakes this loop; it never opens a socket of
        its own (review C1: two independent connectors is how the old version doubled sockets
        and bursts, and could install a socket for a login this loop's own in-flight connect was
        about to overwrite anyway).

        Each iteration decides which login to try from `self._pending_env` (a live switch
        request) else `self.md_env` (the login already in use) -- so a switch that arrives while
        an ordinary reconnect is already mid-connect is simply picked up on the NEXT iteration;
        it never races the one in flight, because there is only ever one.

        While validating a candidate socket, `self.ws` has to point at it (subscribe() sends on
        `self.ws`), but the OLD socket -- if this is a switch away from a connection that was
        actually working -- keeps routing every tick through the UNCHANGED `self.subs` until the
        candidate is proven: it subscribes into a local map first (review I1/M3), and only once
        at least one root subscribed, no root count exceeds what was asked for the window not
        opening mid-subscribe (review I4), and the socket's own `.environment` matches what was
        asked for (review C2), does `self.subs`/`self.md_env` move and the old socket get
        detached and closed. Any failure leaves the old socket (if any) exactly as it was --
        that IS the fallback, no separate code path for it -- and resolves a pending switch's
        Future with the error."""
        attempt = 0
        while not self._stop:
            started = self._now()
            refused_all = False
            committed = False
            keep_for_switch = False   # committed, but a NEW switch (not a drop) ended the cycle:
                                       # leave self.ws alone for the next iteration's old_ws
            pending = self._pending_env      # the switch THIS iteration will try to satisfy, if any
            env = pending if pending is not None else self.md_env
            self._request_env = env          # count_request() below charges the right login's hour
            old_ws = self.ws                 # None on an ordinary reconnect; a switch's live socket otherwise
            old_contracts, old_refused = dict(self.contracts), dict(self.refused)
            connector = self._connect_env(pending) if pending is not None else self._connect()
            try:
                new_ws = await connector
                got_env = getattr(new_ws, "environment", env)
                if got_env != env:   # C2: md_token fell back to the OTHER login's token
                    try:
                        await new_ws.close()
                    except Exception:  # noqa: BLE001
                        pass
                    raise RuntimeError(f"asked for the {env} md login, got {got_env!r} instead "
                                       "(no valid token for the one asked for)")
                self.error = None            # a fresh cycle; a refill error below now sticks
                self.ws = new_ws
                self.contracts = {}
                self.refused = {}
                subs_target = {} if old_ws is not None else self.subs
                for r in self.roots:
                    if pending is not None and self._quiet():
                        # I4: the 9:30 window opened while this switch was subscribing -- abort
                        # to the old login (nothing has been committed yet) rather than finish a
                        # second login's worth of getCharts inside the sacred window
                        raise RuntimeError("the 9:30 window opened during the switch — "
                                          "keeping the previous login")
                    await self._start(r, subs=subs_target, allow_penalty_wait=pending is None)
                if self.roots and all(r in self.refused for r in self.roots):
                    # nothing subscribed: the socket or the login is sick, not a symbol
                    refused_all = True
                    raise Refused("every symbol refused")
                if old_ws is not None and len(self.refused) > len(old_refused):
                    # I1: a switch must not land somewhere WORSE than the login it came from
                    raise RuntimeError(f"the {env} login refused {len(self.refused)} root(s) "
                                       f"(the previous login had {len(old_refused)}) — "
                                       "keeping the previous login")
                # validated: commit. Only now does a switch's old socket stop being the one
                # ticks route through, and only now does it get detached and closed (review M3).
                new_ws.event_handlers.append(self._on_event)
                self.subs = subs_target
                self.md_env = env
                committed = True
                if old_ws is not None:
                    try:
                        old_ws.event_handlers.remove(self._on_event)
                    except ValueError:
                        pass
                    try:
                        await old_ws.close()
                    except Exception:  # noqa: BLE001
                        pass
                if pending is not None:
                    self._resolve_pending(pending, None)
                next_retry = self._now() + RETRY_REFUSED_S
                while not self._stop and self.connected:
                    await self._wait(1)
                    if self._pending_env is not None:
                        break   # a NEW switch arrived: drop out, no backoff, retry at the top now
                    if self.refused and self._now() >= next_retry and not self._quiet():
                        next_retry = self._now() + RETRY_REFUSED_S
                        for r in list(self.refused):
                            if self._quiet() or self._pending_env is not None:
                                break   # a round can straddle 09:20; re-check every root, not once
                            await self._start(r)
                if self._pending_env is not None and self.connected:
                    # the steady loop broke for a NEW switch, not a drop: this connection is
                    # still good, so it becomes the NEXT iteration's `old_ws` (review I1/M3) --
                    # it must keep serving (and keep its handler) until THAT switch is validated
                    keep_for_switch = True
                elif not self._stop and self._pending_env is None:
                    self.error = "md socket closed"
            except Exception as e:  # noqa: BLE001 — any failure = reconnect with backoff (or, for a
                                     # switch, a fallback -- see the `finally` below)
                self.error = f"{type(e).__name__}: {e}"
                if pending is not None:
                    self._resolve_pending(pending, e)
            finally:
                if committed and keep_for_switch:
                    pass   # self.ws stays exactly as it is: still connected, still THE connection
                elif committed:
                    # the cycle's own socket actually dropped: it's done, the next iteration
                    # connects fresh
                    ws, self.ws = self.ws, None
                    if ws is not None:
                        try:
                            await ws.close()
                        except Exception:  # noqa: BLE001
                            pass
                else:
                    # this attempt never became THE connection: discard only its own (failed)
                    # candidate and restore whatever was already running untouched -- None on an
                    # ordinary reconnect failure, the still-good old socket on a failed switch
                    if self.ws is not None and self.ws is not old_ws:
                        try:
                            await self.ws.close()
                        except Exception:  # noqa: BLE001
                            pass
                    self.ws = old_ws
                    if old_ws is not None:   # a failed SWITCH: its own reporting is restored too
                        self.contracts, self.refused = old_contracts, old_refused
            if self._stop:
                break
            if self._pending_env is not None:
                continue   # a switch is queued (fresh, or arrived mid-cycle): try now, no backoff
            if self._now() - started >= HEALTHY_S:
                attempt = 0
            self.reconnects += 1
            wait = BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)]
            if refused_all:
                wait = max(wait, RETRY_REFUSED_S)   # each such round costs one getChart per root
                wait = self._extend_past_quiet(wait)
            await self._wait(wait)
            attempt += 1

    def stop(self) -> None:
        self._stop = True
        self._wake.set()

    async def switch_md(self, new_env: str) -> str:
        """Runtime switch (Task 4, 2026-09-27 app-settings plan): asks run() (above) to reconnect
        under `new_env`'s login ("live"|"demo") in place of whatever it is doing right now --
        finishing or aborting an in-flight connect under the old login first if one was already
        underway, never opening a second socket. Serialized: a switch already in flight raises
        SwitchInProgress rather than queuing a second one (the caller -- the /api/settings PUT --
        turns that into a 409). A failed switch (a bad connect, an environment mismatch, every
        root refused, or the 9:30 window opening mid-subscribe) leaves the previous connection
        running untouched -- run() restores it -- and raises RuntimeError; the caller must not
        persist the new choice."""
        if new_env not in MD_ENVS:
            raise ValueError(f"unknown md login {new_env!r}")
        if self._pending_fut is not None:
            raise SwitchInProgress("a market-data login switch is already in progress")
        if new_env == self.md_env and self.connected:
            return self.md_env
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self._pending_env, self._pending_fut = new_env, fut
        self.switch_error = None
        # wakes a backoff `_wait` immediately, and gets noticed within one `_wait(1)` tick of the
        # steady-state loop if a connection is already up. NOTHING here closes `self.ws`: the
        # current connection (if any) keeps serving until run() has a validated replacement --
        # never an eager blank window before the new login is even known to work.
        self._wake.set()
        return await fut
