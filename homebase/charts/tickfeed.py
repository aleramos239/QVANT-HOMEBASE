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

Runtime login switch (Task 4, 2026-09-27 app-settings plan, fix round 2):
`switch_md()` only leaves a REQUEST that `run()` services at two hooks --
the steady loop's 1 s poll (a socket is up: it keeps serving, untouched,
while `_switch` connects, subscribes and verifies the other login on a
candidate socket; only a verified candidate is installed, and a failed one
is closed and the steady loop simply carries on watching the old socket)
and the top of a cycle (nothing is up: the switch is that cycle's connect).
With no switch requested, `run()` is main's loop, line for line
(tests/test_charts_tickfeed_parity.py drives a frozen copy of main's
run() against this one and compares every broker call and delivered tick),
plus one more hook that acts only weekdays 09:10-09:19:30 ET:

Early rebuild (RECYCLE, 2026-09-28): the desk renews its tokens early then, so
a socket still on the OLD md token would die at that token's expiry, maybe
inside 09:20-09:35 while the user trades the open from these charts. In that
window, at most once a day, a socket riding an md token other than the
freshest one on disk for its login is rebuilt on it through `_switch` on the
same login: make-before-break (the old socket serves until the new one is
subscribed and installed -- no blank chart), one getChart per root paced
RECYCLE_PACE_S apart, only while the hour's budget leaves room, no gap refills.
A failure keeps the socket in use. Reconnects are unchanged: a socket that
dies anyway reconnects at once, window or not, reading the freshest token.
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

MD_ENVS = ("live", "demo")
BACKOFF_S = (5, 10, 20, 40, 80, 160, 300)
HEALTHY_S = 600          # a connection that lived this long resets the backoff
RETRY_REFUSED_S = 600    # a root the feed refused is asked again this often (and on every reconnect)
# The desk renews its tokens early, weekdays 09:10-09:19:30 ET (broker/tradovate.py): a socket
# still on the OLD md token dies at that token's expiry -- maybe inside 09:20-09:35, the open.
# In that same window the socket is rebuilt on the freshest md token on disk, make-before-break
# (_switch): the old one serves until the new one is subscribed and installed.
RECYCLE = (dt.time(9, 10), dt.time(9, 19, 30))   # weekdays ET, = the desk's early-renewal window
RECYCLE_CHECK_S = 20      # inside it, the token on disk is compared this often
RECYCLE_PACE_S = 0.5      # between the rebuild's getCharts: no burst
RECYCLE_BUDGET_MAX = 120  # rebuilt only if the hour's chart requests stay at most this after it
# The swap itself can lose one tick per root: its copy on the new socket came before the
# install (no handler yet), its copy on the old one after (handler gone). Nothing refills that
# (no budget spent), so the recording gets a gap marker around the swap: (before, after) ms --
# the old socket's copy may still be in flight, and exchange stamps vs this clock may skew.
SWAP_GAP_MS = (2000, 1000)


def in_quiet(ts_s: float) -> bool:
    """Is epoch time ts_s inside the 09:20-09:35 ET window around the 9:30
    fire, when this process sends no optional md requests?"""
    return QUIET[0] <= dt.datetime.fromtimestamp(ts_s, ET).time() < QUIET[1]


class SwitchInProgress(RuntimeError):
    """switch_md() was called while an earlier switch is still pending:
    the caller (PUT /api/settings) turns this into a 409, never a queue."""


class Refused(RuntimeError):
    """The md feed will not chart this root: getChart answered without a
    realtimeId or failed (a non-200 status, no answer in 15 s) while the
    socket stayed up, or the root has no resolvable contract."""


async def connect_env(env: str):
    """A socket under `env`'s login ("live"|"demo"). md_token treats the
    wish as a preference and falls back to the other login's token when
    this one has none valid: an ordinary (re)connect accepts that exactly
    as before (status() reports it as md_mismatch); a switch refuses it."""
    return await T.connect_md(prefer_live=(env == "live"))


async def connect_default():
    return await connect_env(MD_ENV)


class TickFeed:
    def __init__(self, roots, on_ticks: Callable[[str, str, list], None],
                 on_subscribed: Optional[Callable[[str, str, Optional[int]], Awaitable[None]]] = None,
                 connect=None, sleep=asyncio.sleep, now=time.time,
                 connect_env=connect_env, md_env: Optional[str] = None, fresh_token=None,
                 on_gap: Optional[Callable[[str, str, int, int], None]] = None):
        self.roots = [r.upper() for r in roots]
        self.on_ticks = on_ticks
        self.on_subscribed = on_subscribed
        self.on_gap = on_gap        # (root, contract, start_ms, end_ms): a recording gap marker
        # md_env: the login in use. It moves only when run() installs a verified switch.
        self.md_env = md_env if md_env is not None else MD_ENV
        self._connect_env = connect_env
        # an ordinary (re)connect: `connect` if the caller gave one (the pre-switch seam), else
        # the active login's -- read at call time, so a reconnect after a switch stays on it
        self._connect = connect or (lambda: self._connect_env(self.md_env))
        self._sleep, self._now = sleep, now
        self.ws = None
        self.subs: dict[int, tuple[str, str]] = {}
        self.contracts: dict[str, str] = {}
        self.last_tick: dict[str, float] = {}      # root -> wall time of the last delivery
        self.last_ms: dict[str, int] = {}          # root -> newest tick timestamp delivered
        self.refused: dict[str, str] = {}          # root -> why the feed refused it
        self._requests: dict[str, list[float]] = {}   # per login: each has its own 180/h
        self.reconnects = 0
        self.error: Optional[str] = None
        self._stop = False
        self._tasks: set = set()
        # the login switch: a request (env + Future) that only run() services
        self._pending_env: Optional[str] = None
        self._pending_fut: Optional[asyncio.Future] = None
        self.switch_error: Optional[dict] = None     # the last failed switch, until one succeeds
        self._running = False
        self._wake: Optional[asyncio.Event] = None  # ends a backoff wait early for a switch or stop()
        # the early rebuild (RECYCLE): (prefer_live) -> (md token, env), the freshest on disk
        self._fresh_token = fresh_token or T.md_token
        self._recycled_day: Optional[str] = None      # at most one rebuild a day
        self._next_recycle_check = 0.0
        self.recycle: Optional[dict] = None           # the last rebuild: {"day", "ok", "error"}

    def count_request(self, env: Optional[str] = None) -> None:
        """One chart request, charged to `env`'s login (default: the active one)."""
        self._requests.setdefault(env or self.md_env, []).append(self._now())

    def budget_used(self, env: Optional[str] = None) -> int:
        """Chart requests in the last hour on `env`'s login (default: the active one)."""
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
        return self._pending_fut is not None

    def md_mismatch(self) -> Optional[str]:
        """The socket up is not the login md_env names (an ordinary connect took the other
        login's token because this one had none valid): said, never silently."""
        got = getattr(self.ws, "environment", None) if self.connected else None
        if got is None or got == self.md_env:
            return None
        return f"set to the {self.md_env} login, but it has no valid md token: charts come from {got}"

    def status(self) -> dict:
        now = self._now()
        return {"mode": "live", "md": self.md_env, "connected": self.connected, "error": self.error,
                "md_mismatch": self.md_mismatch(), "switching_to": self._pending_env,
                "switch_error": self.switch_error, "recycle": self.recycle,
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

    async def subscribe(self, root: str, *, cand=None, subs: Optional[dict] = None,
                        contracts: Optional[dict] = None, env: Optional[str] = None) -> str:
        """`cand` set: a switch is verifying candidate socket `cand` of login `env`. The
        request goes to it, ids and contract land in the caller's own maps (the socket in use
        keeps routing through self.subs untouched), and a p-ticket is a refusal, not a wait:
        a switch must never stall inside the PUT or spend a penalty on the target login."""
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
            self.count_request(env)
            try:
                d = await (self.ws if cand is None else cand).request("md/getChart", body)
            except (RuntimeError, TimeoutError) as e:
                # TradovateWS.request raises on a non-200 status and after 15 s
                # without an answer. With the socket still up that is THIS
                # symbol's refusal; with it gone (a timeout because the reader
                # died, or "websocket not connected" once the socket is
                # CLOSING) the whole feed reconnects. .connected itself only
                # flips in the reader's finally, so it can still read True on
                # a socket that already raises that message -- check the
                # message too, not just the flag.
                up = self.connected if cand is None else bool(getattr(cand, "connected", False))
                if not up or str(e) == "websocket not connected":
                    raise
                why = str(e) or f"md/getChart {type(e).__name__}"      # a timeout has no message
                raise Refused(f"{contract}: {why}") from None
            if isinstance(d, dict) and d.get("p-ticket"):
                if cand is not None:
                    raise Refused(f"{contract}: rate-limited (p-ticket) during a login switch")
                pen = T.Penalty(d)
                await self._sleep(pen.wait_s + 1)
                body = {**body, "p-ticket": pen.ticket}
                continue
            break
        if not isinstance(d, dict) or d.get("realtimeId") is None:
            raise Refused(f"{contract}: getChart refused: {d!r}")
        subs = self.subs if subs is None else subs
        for k in ("historicalId", "realtimeId"):
            if d.get(k) is not None:
                subs[int(d[k])] = (root, contract)
        (self.contracts if contracts is None else contracts)[root] = contract
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
        self._refill_after(root, contract, since)

    def _refill_after(self, root: str, contract: str, since: Optional[int]) -> None:
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
        """main's connection loop, unchanged, plus the two switch hooks marked SWITCH.
        Whatever way this exits (stop, cancel, a crash), a pending switch is answered."""
        self._running = True
        self._wake = asyncio.Event()
        try:
            await self._run()
        finally:
            self._running = False
            if self._pending_fut is not None:
                self._resolve_pending(RuntimeError("the market-data feed stopped"))

    async def _run(self) -> None:
        attempt = 0
        while not self._stop:
            started = self._now()
            refused_all = False
            try:
                if self._pending_env is not None:
                    # SWITCH (nothing is up): the switch is this cycle's connect. A failure is
                    # this cycle's failure -- the usual backoff, then the active login again.
                    # Never the 10-minute refused-all wait: that verdict was about the OTHER login,
                    # and it must not keep the active one dark (re-review 2, R1).
                    await self._switch(self._pending_env)
                else:
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
                    if self._pending_env is not None:
                        # SWITCH (a socket is up): it keeps serving while _switch verifies the
                        # other login. Success installs it; failure leaves this socket exactly
                        # as it was and this loop goes on watching it -- no teardown, no
                        # reconnect, no backoff (re-review N2).
                        try:
                            await self._switch(self._pending_env)
                            next_retry = self._now() + RETRY_REFUSED_S
                        except Exception:  # noqa: BLE001 — answered and recorded by _switch
                            pass
                        continue
                    if await self._recycle_due():
                        # RECYCLE (a socket is up, weekdays 09:10-09:19:30 ET): the same login
                        # on the freshest md token on disk; a failure keeps this socket serving
                        try:
                            await self._switch(self.md_env, recycle=True)
                            next_retry = self._now() + RETRY_REFUSED_S
                        except Exception:  # noqa: BLE001 — recorded in self.recycle
                            pass
                        continue
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
            await self._backoff(wait)
            attempt += 1

    async def _backoff(self, wait: float) -> None:
        """self._sleep(wait), cut short by a switch request or stop(). A switch already
        pending skips it: the feed is down, and the switch is the next connect."""
        if self._pending_env is not None:
            return
        self._wake.clear()
        sleeper = asyncio.ensure_future(self._sleep(wait))
        waker = asyncio.ensure_future(self._wake.wait())
        try:
            await asyncio.wait({sleeper, waker}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in (sleeper, waker):
                t.cancel()
            await asyncio.gather(sleeper, waker, return_exceptions=True)

    def _resolve_pending(self, error: Optional[BaseException]) -> None:
        """Answer the pending switch (success when error is None) and record the outcome."""
        env, fut = self._pending_env, self._pending_fut
        self._pending_env, self._pending_fut = None, None
        if error is None:
            self.switch_error = None
        else:
            self.switch_error = {"to": env, "error": str(error) or type(error).__name__,
                                 "at": self._now()}
        if fut is not None and not fut.done():
            if error is None:
                fut.set_result(self.md_env)
            else:
                fut.set_exception(error)

    async def _recycle_due(self) -> bool:
        """The early rebuild (RECYCLE): weekdays 09:10-09:19:30 ET, at most once a day, the
        token on disk compared at most every RECYCLE_CHECK_S: due when the socket rides an
        md token other than the freshest valid one for its login (the desk renewed it), and
        the hour's chart requests stay at most RECYCLE_BUDGET_MAX after one getChart per
        root. Outside the window it returns at once, without awaiting anything."""
        now = self._now()
        et = dt.datetime.fromtimestamp(now, ET)
        if et.weekday() >= 5 or not RECYCLE[0] <= et.time() < RECYCLE[1]:
            return False
        day = et.date().isoformat()
        if self._recycled_day == day or now < self._next_recycle_check:
            return False
        self._next_recycle_check = now + RECYCLE_CHECK_S
        mine = getattr(self.ws, "token", None)
        if not mine:
            return False
        try:   # small files, but never on this loop (GOTCHAS)
            fresh, env = await asyncio.to_thread(self._fresh_token, self.md_env == "live")
        except Exception:  # noqa: BLE001 — no valid token on disk: nothing to move to
            return False
        if env != self.md_env or not fresh or fresh == mine:
            return False
        if self.budget_used(self.md_env) + len(self.roots) > RECYCLE_BUDGET_MAX:
            return False                  # the hour's budget stays for the open; asked again later
        self._recycled_day = day
        return True

    async def _switch(self, env: str, *, recycle: bool = False) -> None:
        """Connect `env`'s login on a candidate socket, subscribe every root on it, verify, and
        only then install it. The socket in use (if any) keeps serving throughout and is closed
        only after the install. Any failure closes the candidate, touches nothing else, answers
        the pending switch with the error and raises it. The requests are charged to `env`.

        recycle: the early rebuild on the same login (RECYCLE) -- its getCharts paced
        RECYCLE_PACE_S apart, no gap refills (the socket in use served until the install), and
        the outcome recorded in self.recycle, never in the user's pending switch/switch_error."""
        old = self.ws if self.connected else None
        cand = None
        try:
            if self._quiet():
                raise RuntimeError("the 9:30 window is open — keeping the previous login")
            cand = await self._connect_env(env)
            got = getattr(cand, "environment", env)
            if got != env:
                raise RuntimeError(f"no valid {env} md token on disk (the connect came back as "
                                   f"{got}) — keeping the previous login")
            subs: dict = {}
            contracts: dict = {}
            refused: dict = {}
            ok: list = []
            for i, r in enumerate(self.roots):
                if self._quiet():   # the 9:30 window opened mid-switch
                    raise RuntimeError("the 9:30 window opened during the switch — "
                                       "keeping the previous login")
                if recycle and i:
                    await self._sleep(RECYCLE_PACE_S)
                try:
                    ok.append((r, await self.subscribe(r, cand=cand, subs=subs,
                                                       contracts=contracts, env=env)))
                except Refused as e:
                    refused[r] = str(e)
            if self.roots and not ok:
                raise Refused(f"the {env} login refused every symbol — keeping the previous login")
            if old is not None and len(refused) > len(self.refused):
                raise RuntimeError(f"the {env} login refused {len(refused)} symbol(s), the "
                                   f"previous one {len(self.refused)} — keeping the previous login")
        except BaseException as e:
            if cand is not None:
                try:
                    await cand.close()
                except Exception:  # noqa: BLE001
                    pass
            if recycle:
                self.recycle = {"day": self._recycled_day, "ok": False,
                                "error": str(e) or type(e).__name__}
            elif isinstance(e, Exception):
                self._resolve_pending(e)
            raise
        # install: no await until the new socket routes, so no tick falls between the two
        if old is not None:
            try:
                old.event_handlers.remove(self._on_event)
            except ValueError:
                pass
        self.ws = cand
        cand.event_handlers.append(self._on_event)
        self.subs, self.contracts, self.refused = subs, contracts, refused
        self.md_env = env
        self.error = None
        if recycle:
            self.recycle = {"day": self._recycled_day, "ok": True, "error": None}
            # no refill (budget): a gap marker around the swap for every root it moved, so the
            # archive and QA can see the tick it may have lost (SWAP_GAP_MS)
            swap_ms = int(self._now() * 1000)
            for r, c in ok if self.on_gap is not None else ():
                try:
                    self.on_gap(r, c, swap_ms - SWAP_GAP_MS[0], swap_ms + SWAP_GAP_MS[1])
                except Exception as e:  # noqa: BLE001 — a marker never undoes the swap
                    self.recycle["gap_error"] = f"{r}: {type(e).__name__}: {e}"
        else:
            self._resolve_pending(None)
            # gap refills start only now, on the installed socket and its login: their fetch
            # runs past this moment, so it covers every tick between each root's last delivery
            # and the new socket routing
            for r, c in ok:
                self._refill_after(r, c, self.last_ms.get(r))
        if old is not None:
            try:
                await old.close()
            except Exception:  # noqa: BLE001
                pass

    def stop(self) -> None:
        self._stop = True
        if self._wake is not None:
            self._wake.set()

    async def switch_md(self, new_env: str) -> str:
        """Ask run() to move the feed to `new_env`'s login; returns once it has (the login now
        in use) or raises the reason it did not (RuntimeError; the previous login is kept).
        One at a time: a second request while one is pending raises SwitchInProgress."""
        if new_env not in MD_ENVS:
            raise ValueError(f"unknown md login {new_env!r}")
        if self._pending_fut is not None:
            raise SwitchInProgress("a market-data login switch is already in progress")
        if new_env == self.md_env and self.connected:
            return self.md_env
        if self._stop or not self._running:
            raise RuntimeError("the market-data feed is not running")
        fut = asyncio.get_running_loop().create_future()
        self._pending_env, self._pending_fut = new_env, fut
        self._wake.set()
        return await fut
