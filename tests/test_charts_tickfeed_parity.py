"""Re-review N1/N2, fix round 2 (Task 4, 2026-09-27 app-settings plan): with no switch ever
requested, TickFeed.run() must behave EXACTLY as main's did. `MainFeed` carries main's
run(), subscribe() and _start() VERBATIM (copied from main 473659c / ffad9a5, where
homebase/charts/tickfeed.py is unchanged); both feeds are driven through the same script
against the same fake broker -- startup with a tick arriving between two roots' subscribes, a
tick-carrying steady state, a mid-stream drop and reconnect, a refused root and its 10-min
retry, a failed connect, a socket that refuses every root (the 600 s wait), and a p-ticket --
and every broker call, sleep, close, refill and delivered tick is compared in order.
Fakes only: no broker, no token, nothing written anywhere."""
from __future__ import annotations

import asyncio
import datetime as dt

from homebase import symbols
from homebase import ticks as T
from homebase.charts.session import ET
from homebase.charts.tickfeed import BACKOFF_S, HEALTHY_S, RETRY_REFUSED_S, Refused, TickFeed


class MainFeed(TickFeed):
    """main's TickFeed.run() and the two methods it calls, verbatim. Everything else
    (status, _on_event, _quiet, ...) is shared with TickFeed and unchanged from main."""

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


T0 = dt.datetime(2026, 9, 24, 10, 0, tzinfo=ET).timestamp()   # a Thursday, well clear of 09:20
ROOTS = ["NQ", "ES", "BTC"]


def c(root):
    return symbols.resolve_contract(root)


class ScriptWS:
    """A fake md socket that writes everything it is asked into the shared log. `script` maps
    a call number (1-based, per socket) to a reply dict, or to a callable run BEFORE the reply
    (to push a tick mid-subscribe, the N1 window)."""

    def __init__(self, n, log, replies=None, before=None):
        self.n, self.log = n, log
        self.connected = True
        self.event_handlers = []
        self.calls = 0
        self.replies = dict(replies or {})
        self.before = dict(before or {})
        self.rid = {}                     # contract -> realtimeId handed out

    async def request(self, ep, body=""):
        self.calls += 1
        self.log.append(("req", self.n, ep, body.get("symbol"), body.get("p-ticket")))
        hook = self.before.get(self.calls)
        if hook is not None:
            hook(self)
        if self.calls in self.replies:
            return self.replies[self.calls]
        rid = 1000 * self.n + self.calls
        self.rid[body.get("symbol")] = rid
        return {"historicalId": rid + 500, "realtimeId": rid}

    async def close(self):
        self.log.append(("close", self.n))
        self.connected = False

    def push(self, contract, t):
        rid = self.rid.get(contract, -1)
        for h in list(self.event_handlers):
            h({"e": "chart", "d": {"charts": [{"id": rid, "bp": 400, "bt": 1000, "ts": 0.25,
                                               "tks": [{"t": t, "p": 1, "s": 1, "id": t}]}]}})


def drive(cls):
    """One scripted life of the feed; returns the full ordered log."""
    log, socks, clock, polls, connects = [], [], [T0], [0], [0]

    def sock(n, **kw):
        ws = ScriptWS(n, log, **kw)
        socks.append(ws)
        return ws

    async def connect():
        connects[0] += 1
        n = connects[0]
        log.append(("connect", n))
        if n == 1:   # startup: an NQ tick arrives while ES's getChart is still out (N1)
            return sock(1, before={2: lambda ws: ws.push(c("NQ"), 7)})
        if n == 2:   # reconnect: BTC refused, and an ES tick lands while BTC is being asked
            return sock(2, replies={3: {"errorText": "Access is denied"}},
                        before={3: lambda ws: ws.push(c("ES"), 11)})
        if n == 3:
            raise ConnectionError("md handshake failed")
        if n == 4:   # a socket that refuses every root: the 600 s wait
            return sock(4, replies={1: {"s": 1}, 2: {"s": 1}, 3: {"s": 1}})
        # 5: a p-ticket on the first request, honoured and resent
        return sock(5, replies={1: {"p-ticket": "tk", "p-time": 2}})

    async def sleep(s):
        log.append(("sleep", s))
        clock[0] += s
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        if s != 1:
            return
        polls[0] += 1
        ws = socks[-1]
        k = polls[0]
        if ws.n == 1:
            if k == 2:
                ws.push(c("ES"), 9)
            if k == 3:
                ws.connected = False                     # a mid-stream drop
        elif ws.n == 2:
            if k == 4:
                clock[0] += RETRY_REFUSED_S              # the refused root's 10-min retry is due
            if k == 6:
                ws.push(c("BTC"), 13)
                ws.push(c("NQ"), 14)
            if k == 7:
                ws.connected = False
        elif ws.n == 5 and k >= 9:
            feed.stop()

    ticks = []

    async def on_sub(root, contract, since):
        log.append(("refill", root, contract, since))

    def on_ticks(root, contract, rows):
        log.append(("tick", root, contract, [r["ts_ms"] for r in rows]))

    feed = cls(ROOTS, on_ticks, on_subscribed=on_sub, connect=connect, sleep=sleep,
               now=lambda: clock[0])

    async def main():
        await asyncio.wait_for(feed.run(), timeout=2)

    try:
        asyncio.run(main())
    except TimeoutError:
        raise AssertionError(log[-40:])
    status = feed.status()
    log.append(("end", feed.reconnects, feed.error, sorted(feed.subs.items()),
                dict(feed.refused), feed.budget_used(),
                {r: v["error"] for r, v in status["roots"].items()}))
    return log


def test_run_matches_main_call_for_call_when_no_switch_is_requested():
    old, new = drive(MainFeed), drive(TickFeed)
    # the script really exercised what it claims to (so a vacuous match cannot pass)
    kinds = [e[0] for e in old]
    assert kinds.count("connect") == 5
    assert ("sleep", 5) in old and ("sleep", 10) in old and ("sleep", RETRY_REFUSED_S) in old
    assert ("tick", "NQ", c("NQ"), [1007]) in old          # the tick between two subscribes
    assert ("tick", "BTC", c("BTC"), [1013]) in old        # the refused root, after its retry
    assert any(e[0] == "req" and e[4] == "tk" for e in old)   # the p-ticket resend
    assert new == old


def test_a_tick_between_two_roots_subscribes_is_delivered_on_an_ordinary_connect():
    """N1 on its own: the handler is on the socket before the first subscribe, as in main."""
    log = drive(TickFeed)
    first_es_req = log.index(("req", 1, "md/getChart", c("ES"), None))
    tick = log.index(("tick", "NQ", c("NQ"), [1007]))
    assert tick == first_es_req + 1
