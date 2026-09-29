"""Tick feed: one subscription per root, routing by chart id, penalty, reconnect backoff."""
from __future__ import annotations

import asyncio
import datetime as dt

import pytest

from homebase import symbols
from homebase.charts import DEFAULT_ROOTS
from homebase.charts.session import ET
from homebase.charts.tickfeed import RETRY_REFUSED_S, Refused, SwitchInProgress, TickFeed


def run(coro):
    return asyncio.run(coro)


_UNSET = object()


class FakeWS:
    def __init__(self, replies=None, environment=_UNSET):
        self.connected = True
        self.event_handlers = []
        self.sent = []
        self.replies = list(replies or [])
        # only set when a test asks for it: TickFeed.run()'s C2 mismatch check reads
        # `getattr(ws, "environment", env)`, which must default to a MATCH for every test that
        # never mentions environment at all (only the C2-specific tests below do).
        if environment is not _UNSET:
            self.environment = environment

    async def request(self, ep, body=""):
        self.sent.append((ep, body))
        if self.replies:
            return self.replies.pop(0)
        n = len(self.sent)
        return {"historicalId": 10 + n, "realtimeId": 100 + n}

    async def close(self):
        self.connected = False

    def push(self, rid, tks):
        for h in list(self.event_handlers):
            h({"e": "chart", "d": {"charts": [{"id": rid, "bp": 400, "bt": 1000, "ts": 0.25, "tks": tks}]}})


async def nosleep(_s):
    await asyncio.sleep(0)


def test_one_subscription_per_root_and_ticks_route_by_chart_id():
    ws, got = FakeWS(), []
    feed = TickFeed(["NQ", "ES"], lambda r, c, rows: got.append((r, c, rows)), sleep=nosleep)
    feed.ws = ws
    ws.event_handlers.append(feed._on_event)
    run(feed.subscribe("NQ"))
    run(feed.subscribe("ES"))
    assert [b["symbol"] for _, b in ws.sent] == [symbols.resolve_contract("NQ"), symbols.resolve_contract("ES")]
    assert ws.sent[0][1]["chartDescription"]["underlyingType"] == "Tick"
    ws.push(101, [{"t": 5, "p": 1, "s": 2, "b": 0, "a": 1, "id": 9}])
    ws.push(11, [{"t": 6, "p": 2, "s": 1, "id": 10}])            # the historical id routes too
    ws.push(999, [{"t": 7, "p": 3, "s": 1, "id": 11}])           # not ours
    assert [(g[0], g[2][0]["price"], g[2][0]["ts_ms"]) for g in got] == [("NQ", 100.25, 1005), ("NQ", 100.5, 1006)]
    assert got[0][2][0]["bid"] == 100.0 and got[0][2][0]["ask"] == 100.25
    assert feed.budget_used() == 2
    st = feed.status()
    assert st["roots"]["NQ"]["contract"] == symbols.resolve_contract("NQ") and st["budget_hour"] == 2


def test_a_penalty_reply_is_resent_with_its_ticket():
    slept = []

    async def sleep(s):
        slept.append(s)
    ws = FakeWS([{"p-ticket": "tk", "p-time": 2}, {"historicalId": 1, "realtimeId": 2}])
    feed = TickFeed(["NQ"], lambda *a: None, sleep=sleep)
    feed.ws = ws
    run(feed.subscribe("NQ"))
    assert ws.sent[1][1]["p-ticket"] == "tk" and slept == [3] and feed.budget_used() == 2


def test_reconnect_backs_off_resubscribes_and_reports_the_last_tick():
    socks, slept, subs = [], [], []

    async def connect():
        ws = FakeWS()
        socks.append(ws)
        return ws

    async def sleep(s):
        slept.append(s)
        await asyncio.sleep(0)
        if s == 1:
            if len(socks) == 1:
                socks[0].push(101, [{"t": 5, "p": 1, "s": 1, "id": 1}])
            socks[-1].connected = False                # the socket drops
            if slept.count(1) >= 3:
                feed.stop()

    async def on_sub(root, contract, since):
        subs.append((root, since))

    feed = TickFeed(["NQ"], lambda *a: None, on_subscribed=on_sub, connect=connect, sleep=sleep)
    run(feed.run())
    assert len(socks) == 3
    assert [s for s in slept if s != 1] == [5, 10]
    assert subs == [("NQ", None), ("NQ", 1005), ("NQ", 1005)]
    assert feed.reconnects == 2 and not feed.connected


def test_a_failed_gap_refill_is_recorded_in_status():
    async def connect():
        return FakeWS()

    async def bad_refill(root, contract, since):
        raise RuntimeError("boom")

    async def sleep(s):
        await asyncio.sleep(0)          # let the on_subscribed task run and raise
        await asyncio.sleep(0)          # let its done-callback run (call_soon-deferred)
        feed.stop()

    feed = TickFeed(["NQ"], lambda *a: None, on_subscribed=bad_refill, connect=connect, sleep=sleep)
    run(feed.run())
    assert "refill NQ" in feed.status()["error"] and "boom" in feed.status()["error"]


class YieldingWS(FakeWS):
    """Like FakeWS, but request() genuinely yields once, so a fast-failing
    on_subscribed task for an earlier root can finish (and run its
    done-callback) while a later root in the same subscribe loop is still
    mid-flight — the window the cycle-reset race needs to be observed."""

    async def request(self, ep, body=""):
        await asyncio.sleep(0)
        return await super().request(ep, body)


def test_a_refill_error_recorded_mid_subscribe_survives_the_cycle_reset():
    ws = YieldingWS()

    async def connect():
        return ws

    async def maybe_bad(root, contract, since):
        if root == "NQ":
            raise RuntimeError("boom")

    async def sleep(s):
        await asyncio.sleep(0)          # one steady-state tick, then stop
        feed.stop()

    feed = TickFeed(["NQ", "ES", "YM"], lambda *a: None, on_subscribed=maybe_bad,
                    connect=connect, sleep=sleep)
    run(feed.run())
    assert "refill NQ" in feed.status()["error"] and "boom" in feed.status()["error"]


def test_a_refused_root_leaves_the_other_roots_subscribed():
    socks, subs = [], []

    async def connect():
        ws = FakeWS(replies=[{"historicalId": 11, "realtimeId": 101}, {"errorText": "Access is denied"},
                             {"historicalId": 13, "realtimeId": 103}])
        socks.append(ws)
        return ws

    async def on_sub(root, contract, since):
        subs.append(root)

    async def sleep(_s):
        await asyncio.sleep(0)
        feed.stop()                      # one cycle is enough

    feed = TickFeed(["NQ", "BTC", "ES"], lambda *a: None, on_subscribed=on_sub, connect=connect, sleep=sleep)
    run(feed.run())
    assert len(socks) == 1 and feed.reconnects == 0            # no reconnect loop
    assert sorted({root for root, _ in feed.subs.values()}) == ["ES", "NQ"]
    assert subs == ["NQ", "ES"]
    st = feed.status()
    assert "refused" in st["roots"]["BTC"]["error"] and st["roots"]["NQ"]["error"] is None
    assert st["error"] is None


def test_a_refused_root_is_asked_again_every_ten_minutes():
    clock = [1000.0]
    ws = FakeWS(replies=[{"historicalId": 11, "realtimeId": 101}, {"errorText": "no entitlement"},
                         {"historicalId": 12, "realtimeId": 102}])
    waits = [0]

    async def connect():
        return ws

    async def sleep(_s):
        await asyncio.sleep(0)
        waits[0] += 1
        clock[0] += 300                  # each 1 s wait jumps five minutes
        if waits[0] >= 3:
            feed.stop()

    feed = TickFeed(["NQ", "BTC"], lambda *a: None, connect=connect, sleep=sleep, now=lambda: clock[0])
    run(feed.run())
    assert [b["symbol"] for _, b in ws.sent] == [symbols.resolve_contract("NQ"), symbols.resolve_contract("BTC"),
                                                 symbols.resolve_contract("BTC")]
    assert feed.status()["roots"]["BTC"]["error"] is None
    assert feed.contracts["BTC"] == symbols.resolve_contract("BTC")


def test_a_socket_failure_while_subscribing_still_reconnects_everything():
    socks = []

    class DyingWS(FakeWS):
        async def request(self, ep, body=""):
            self.sent.append((ep, body))
            if len(self.sent) == 2:
                raise ConnectionError("socket reset")
            return {"historicalId": 11, "realtimeId": 101}

    async def connect():
        socks.append(DyingWS())
        return socks[-1]

    async def sleep(_s):
        await asyncio.sleep(0)
        if len(socks) >= 2:
            feed.stop()

    feed = TickFeed(["NQ", "ES"], lambda *a: None, connect=connect, sleep=sleep)
    run(feed.run())
    assert len(socks) >= 2 and feed.reconnects >= 1


class RaisingWS(FakeWS):
    """Like the real TradovateWS.request: a non-200 answer RAISES RuntimeError
    and a request nobody answers raises TimeoutError after 15 s -- neither
    comes back as a reply dict. `fail` maps a contract to what its getChart
    raises; every other contract subscribes."""

    def __init__(self, fail):
        super().__init__()
        self.fail = dict(fail)

    async def request(self, ep, body=""):
        self.sent.append((ep, body))
        e = self.fail.get(body["symbol"])
        if e is not None:
            raise e
        n = len(self.sent)
        return {"historicalId": 10 + n, "realtimeId": 100 + n}


def _one_cycle_with(fail_btc):
    socks, subs = [], []

    async def connect():
        socks.append(RaisingWS({symbols.resolve_contract("BTC"): fail_btc}))
        return socks[-1]

    async def on_sub(root, contract, since):
        subs.append(root)

    async def sleep(_s):
        await asyncio.sleep(0)
        feed.stop()                      # one steady-state second is enough

    feed = TickFeed(["NQ", "BTC", "ES"], lambda *a: None, on_subscribed=on_sub, connect=connect, sleep=sleep)
    run(feed.run())
    return feed, socks, subs


def test_a_raised_non_200_refusal_leaves_the_other_roots_subscribed():
    feed, socks, subs = _one_cycle_with(RuntimeError("md/getChart failed: status=404 data='Unknown symbol'"))
    assert len(socks) == 1 and feed.reconnects == 0            # no reconnect loop
    assert sorted({root for root, _ in feed.subs.values()}) == ["ES", "NQ"] and subs == ["NQ", "ES"]
    st = feed.status()
    assert "status=404" in st["roots"]["BTC"]["error"] and "Unknown symbol" in st["roots"]["BTC"]["error"]
    assert st["roots"]["NQ"]["error"] is None and st["error"] is None


def test_a_getchart_timeout_on_one_root_leaves_the_other_roots_subscribed():
    feed, socks, subs = _one_cycle_with(TimeoutError())
    assert len(socks) == 1 and feed.reconnects == 0
    assert sorted({root for root, _ in feed.subs.values()}) == ["ES", "NQ"] and subs == ["NQ", "ES"]
    st = feed.status()
    assert "TimeoutError" in st["roots"]["BTC"]["error"] and st["error"] is None


def test_a_raise_after_the_socket_died_is_not_a_refusal_it_reconnects():
    """A dead socket's request raises RuntimeError too ("websocket not
    connected"): with the socket gone it must reconnect everything at the
    normal backoff, not be filed as that root's refusal."""
    socks, slept = [], []

    class DyingWS(FakeWS):
        async def request(self, ep, body=""):
            self.sent.append((ep, body))
            if len(self.sent) == 2:
                self.connected = False              # the reader saw the socket close
                raise RuntimeError("websocket not connected")
            return {"historicalId": 11, "realtimeId": 101}

    async def connect():
        socks.append(DyingWS())
        return socks[-1]

    async def sleep(s):
        slept.append(s)
        await asyncio.sleep(0)
        if len(socks) >= 2:
            feed.stop()

    feed = TickFeed(["NQ", "ES"], lambda *a: None, connect=connect, sleep=sleep)
    run(feed.run())
    assert len(socks) >= 2 and feed.reconnects >= 1 and slept[0] == 5
    assert "websocket not connected" in feed.status()["error"]


def test_subscribe_reraises_websocket_not_connected_even_if_connected_still_reads_true():
    """TradovateWS.connected only flips False in the reader's finally, but
    request() already raises "websocket not connected" once the socket is
    CLOSING (tradovate_ws.py's _ws_is_closed). A fresh socket that closes
    right before this fires must not have that filed as THIS symbol's
    refusal just because .connected hasn't caught up yet."""
    class StuckWS(FakeWS):
        async def request(self, ep, body=""):
            raise RuntimeError("websocket not connected")

    ws = StuckWS()
    assert ws.connected is True                     # the race: still True when it raises
    feed = TickFeed(["NQ"], lambda *a: None, sleep=nosleep)
    feed.ws = ws
    with pytest.raises(RuntimeError) as exc_info:
        run(feed.subscribe("NQ"))
    assert not isinstance(exc_info.value, Refused)
    assert str(exc_info.value) == "websocket not connected"


def test_a_websocket_not_connected_raise_backs_off_normally_not_as_refused():
    """Filed as a socket failure (not a refusal), the run loop must reconnect
    at the plain backoff (5 s) -- not wait RETRY_REFUSED_S (600 s), which is
    only for a root the feed deliberately refuses."""
    slept = []

    class StuckWS(FakeWS):
        async def request(self, ep, body=""):
            raise RuntimeError("websocket not connected")

    async def connect():
        return StuckWS()

    async def sleep(s):
        slept.append(s)
        await asyncio.sleep(0)
        feed.stop()

    feed = TickFeed(["NQ"], lambda *a: None, connect=connect, sleep=sleep)
    run(feed.run())
    assert slept == [5]
    assert feed.status()["roots"]["NQ"]["error"] is None


def test_every_root_refused_on_a_fresh_socket_reconnects_within_the_md_budget():
    """Nothing subscribed = the socket or the login is sick, not a symbol:
    the whole feed reconnects. A login that refuses everything must not
    burn the shared 180/hour budget doing it: at the plain 5 s -> 5 min
    backoff that is ~17 rounds of 11 getCharts in the first hour (~187)."""
    clock = [1_000_000.0]
    socks, slept = [], []

    async def connect():
        socks.append(RaisingWS({symbols.resolve_contract(r): RuntimeError("md/getChart failed: status=500 data=None")
                                for r in DEFAULT_ROOTS}))
        return socks[-1]

    async def sleep(s):
        slept.append(s)
        await asyncio.sleep(0)
        clock[0] += s
        if clock[0] - 1_000_000.0 >= 3600:
            feed.stop()

    feed = TickFeed(DEFAULT_ROOTS, lambda *a: None, connect=connect, sleep=sleep, now=lambda: clock[0])
    run(feed.run())
    assert len(socks) >= 2 and feed.reconnects >= 1                  # a sick socket is still replaced
    assert all(s >= RETRY_REFUSED_S for s in slept)                  # never faster than the refused-root retry
    asked = sum(len(ws.sent) for ws in socks)
    assert asked <= 6 * len(DEFAULT_ROOTS) < 180                     # <= one round per 10 min
    st = feed.status()
    assert "every symbol refused" in st["error"] and "status=500" in st["roots"]["NQ"]["error"]


def test_refused_all_wait_is_extended_to_clear_the_quiet_window():
    """A reconnect due while every root is refused must not land inside
    09:20-09:35 ET: from 09:12 the plain max(backoff, RETRY_REFUSED_S) wait
    (600 s) would land at 09:22 -- it must be extended to end at 09:35
    instead, so the reconnect's getChart round never fires inside the
    window."""
    t0 = dt.datetime(2026, 9, 24, 9, 12, tzinfo=ET).timestamp()     # a Thursday
    clock = [t0]
    slept = []

    async def connect():
        return RaisingWS({symbols.resolve_contract(r): RuntimeError("md/getChart failed: status=500 data=None")
                          for r in ("NQ", "BTC")})

    async def sleep(s):
        slept.append(s)
        await asyncio.sleep(0)
        clock[0] += s
        feed.stop()                      # one cycle is enough to see the computed wait

    feed = TickFeed(["NQ", "BTC"], lambda *a: None, connect=connect, sleep=sleep, now=lambda: clock[0])
    run(feed.run())
    assert slept == [23 * 60]            # 09:12 -> 09:35, not the plain 600 s (which lands at 09:22)


def test_a_refused_root_is_not_retried_inside_the_0920_0935_quiet_window():
    t0 = dt.datetime(2026, 9, 24, 9, 12, tzinfo=ET).timestamp()     # a Thursday
    clock = [t0]
    btc = symbols.resolve_contract("BTC")
    asked = []

    class WS(FakeWS):
        async def request(self, ep, body=""):
            if body["symbol"] == btc:
                asked.append(dt.datetime.fromtimestamp(clock[0], ET).time())
                self.sent.append((ep, body))
                return {"errorText": "no entitlement"}
            return await super().request(ep, body)

    ws = WS()

    async def connect():
        return ws

    async def sleep(_s):
        await asyncio.sleep(0)
        clock[0] += 60                   # each 1 s wait jumps a minute
        if clock[0] >= t0 + 45 * 60:     # to 09:57
            feed.stop()

    feed = TickFeed(["NQ", "BTC"], lambda *a: None, connect=connect, sleep=sleep, now=lambda: clock[0])
    run(feed.run())
    # 09:22 falls in the window: asked at 09:35; then twice the wait (review 5): 09:55
    assert asked == [dt.time(9, 12), dt.time(9, 35), dt.time(9, 55)]


def test_a_refused_retry_round_stops_mid_round_when_the_quiet_window_opens():
    """A retry round can straddle 09:20: with 3 refused roots and each
    request taking real time (15 s here, like a real getChart round-trip),
    the round must stop the instant a root's turn lands inside 09:20-09:35,
    leaving the rest for the next scheduled round -- the OLD code checked
    _quiet() once for the whole round and would have sent all 3."""
    t0 = dt.datetime(2026, 9, 24, 9, 9, 14, tzinfo=ET).timestamp()   # a Thursday
    clock = [t0]
    fail = {symbols.resolve_contract(r) for r in ("BTC", "GC", "SI")}

    class SlowRefusingWS(FakeWS):
        async def request(self, ep, body=""):
            self.sent.append((ep, body))
            if body["symbol"] in fail:
                clock[0] += 15            # a refusal round-trip costs real time too
                return {"errorText": "no entitlement"}
            n = len(self.sent)
            return {"historicalId": 10 + n, "realtimeId": 100 + n}

    ws = SlowRefusingWS()

    async def connect():
        return ws

    async def sleep(s):
        await asyncio.sleep(0)
        clock[0] += s
        if clock[0] >= t0 + 700:         # past the partial round, short of the next one at 09:35
            feed.stop()

    feed = TickFeed(["NQ", "BTC", "GC", "SI"], lambda *a: None, connect=connect, sleep=sleep, now=lambda: clock[0])
    run(feed.run())
    retried = [b["symbol"] for _, b in ws.sent[4:]]     # calls after the 4 initial subscribes
    # each root keeps its own clock (refused 15 s apart): BTC and GC come due before 09:20,
    # SI's turn is 09:20:14 -- inside the window, so it waits for it to close
    assert retried == [symbols.resolve_contract("BTC"), symbols.resolve_contract("GC")]


# ------------------------------------------------------------------ switch_md
# Task 4 (2026-09-27 app-settings plan), fix round 2. switch_md only leaves a request that
# run() services. Every test drives a real run() and, after the switch's outcome, LETS IT KEEP
# GOING for a number of 1 s polls, then checks what run() did next: round 1's tests stopped at
# the moment of failure and missed a teardown-and-reconnect loop (re-review N2).

T_OK = dt.datetime(2026, 9, 24, 11, 0, tzinfo=ET).timestamp()   # a Thursday, clear of 09:20


class Rig:
    """run() in the background, a fake clock that moves 1 s per poll, a count of every
    connect, and every refill and delivered tick recorded with the socket in use at the time."""

    def __init__(self, roots, *, env_socks=None, ordinary=None, md_env="demo", now0=T_OK,
                 block_backoff=False):
        self.clock = [now0]
        self.slept = []
        self.connects = []                      # ("ordinary", ws) / (env, ws or exc)
        self.env_socks = env_socks or {}        # env -> ws, exception, or a list consumed in order
        self.ordinary = ordinary or (lambda: FakeWS())
        self.ticks, self.refills = [], []
        self.block_backoff = block_backoff
        self.gate = asyncio.Event()

        async def connect():
            ws = self.ordinary()
            if asyncio.iscoroutine(ws):
                ws = await ws
            self.connects.append(("ordinary", ws))
            return ws

        async def connect_env(env):
            v = self.env_socks[env]
            if isinstance(v, list):
                v = v.pop(0)
            if callable(v) and not isinstance(v, FakeWS):
                v = await v()
            self.connects.append((env, v))
            if isinstance(v, BaseException):
                raise v
            return v

        async def sleep(s):
            self.slept.append(s)
            if s != 1 and self.block_backoff:
                await self.gate.wait()          # a backoff that only a wake can end
            self.clock[0] += s
            await asyncio.sleep(0)

        async def on_sub(root, contract, since):
            self.refills.append((root, since, self.feed.ws))

        def on_ticks(root, contract, rows):
            self.ticks.append((root, [r["ts_ms"] for r in rows]))

        self.feed = TickFeed(roots, on_ticks, on_subscribed=on_sub, connect=connect,
                             connect_env=connect_env, sleep=sleep, now=lambda: self.clock[0],
                             md_env=md_env)

    async def polls(self, n):
        """Let run() take n more 1 s steady-loop steps."""
        target = self.slept.count(1) + n
        while self.slept.count(1) < target:
            await asyncio.sleep(0)

    async def up(self):
        while not self.feed.connected:
            await asyncio.sleep(0)
        await self.polls(1)

    def drive(self, body):
        async def go():
            task = asyncio.ensure_future(self.feed.run())
            try:
                return await asyncio.wait_for(body(), timeout=5)
            finally:
                self.feed.stop()
                await asyncio.wait_for(task, timeout=5)
        return run(go())


def _push(ws, rid, t):
    ws.push(rid, [{"t": t, "p": 1, "s": 1, "id": t}])


def _still_serving(rig, ws, ordinary_connects=1):
    """What must hold after a FAILED switch while `ws` was serving (N2): no reconnect, no
    teardown, no backoff, the same socket installed, routed and untouched."""
    f = rig.feed
    assert f.ws is ws and ws.connected and f._on_event in ws.event_handlers
    assert [k for k, _ in rig.connects].count("ordinary") == ordinary_connects
    assert f.reconnects == 0 and [s for s in rig.slept if s != 1] == []
    assert f.switch_in_progress is False


# ---- success ----

def test_switch_installs_only_a_verified_socket_and_refills_after_installing():
    old = FakeWS()
    seen_ws_during_candidate = []

    class Cand(FakeWS):
        async def request(self, ep, body=""):
            seen_ws_during_candidate.append(rig.feed.ws)       # Depth follows feed.ws (M-b)
            _push(old, 101, 50 + len(self.sent))                 # the old socket still serving
            return await super().request(ep, body)

    new = Cand()
    rig = Rig(["NQ", "ES"], ordinary=lambda: old, env_socks={"live": new})

    async def body():
        await rig.up()
        refills_before = len(rig.refills)
        got = await rig.feed.switch_md("live")
        await rig.polls(5)
        _push(new, 101, 99)
        _push(old, 101, 98)                                      # detached: never delivered
        return got, refills_before

    got, refills_before = rig.drive(body)
    f = rig.feed
    assert got == "live" and f.md_env == "live" and f.switch_error is None
    assert all(w is old for w in seen_ws_during_candidate)       # never the unverified candidate
    assert rig.ticks == [("NQ", [1050]), ("NQ", [1051]), ("NQ", [1099])]   # no gap, no stale login
    assert not old.connected and f._on_event not in old.event_handlers
    assert [b["symbol"] for _, b in new.sent] == [symbols.resolve_contract("NQ"),
                                                  symbols.resolve_contract("ES")]
    # M-c: the switch's refills start only after the install, on the new socket, from the
    # last tick the old socket delivered
    after = rig.refills[refills_before:]
    assert [(r, s) for r, s, _ in after] == [("NQ", 1051), ("ES", None)]
    assert all(w is new for _, _, w in after)
    assert [k for k, _ in rig.connects] == ["ordinary", "live"]   # nothing else connected after


def test_after_a_switch_an_ordinary_reconnect_stays_on_the_new_login():
    old, new = FakeWS(), FakeWS()
    later = FakeWS()
    rig = Rig(["NQ"], env_socks={"demo": old, "live": [new, later]})
    rig.feed._connect = lambda: rig.feed._connect_env(rig.feed.md_env)   # the production default

    async def body():
        await rig.up()
        await rig.feed.switch_md("live")
        new.connected = False                                    # the new socket drops
        while not later.connected or rig.feed.ws is not later:
            await asyncio.sleep(0)

    rig.drive(body)
    assert [k for k, _ in rig.connects] == ["demo", "live", "live"]


def test_switch_md_is_a_noop_when_already_on_that_login_and_connected():
    ws = FakeWS()
    feed = TickFeed(["NQ"], lambda *a: None, sleep=nosleep, md_env="live")
    feed.ws = ws
    got = run(feed.switch_md("live"))
    assert got == "live" and ws.sent == []


def test_an_unknown_login_is_refused_without_touching_anything():
    feed = TickFeed(["NQ"], lambda *a: None, sleep=nosleep, md_env="demo")
    with pytest.raises(ValueError):
        run(feed.switch_md("paper"))
    assert feed.md_env == "demo" and feed._pending_env is None


# ---- failures while a socket is serving: run() goes on watching it (N2) ----

@pytest.mark.parametrize("case", ["connect_raises", "env_mismatch", "refuses_all",
                                  "refuses_more", "p_ticket", "drops_mid_subscribe"])
def test_a_failed_switch_leaves_the_old_socket_serving_and_run_carries_on(case):
    old = FakeWS()
    nq, es = symbols.resolve_contract("NQ"), symbols.resolve_contract("ES")

    class Dropping(FakeWS):
        async def request(self, ep, body=""):
            if self.sent:
                self.sent.append((ep, body))
                self.connected = False
                raise RuntimeError("websocket not connected")
            return await super().request(ep, body)

    cand = {
        "connect_raises": RuntimeError("md refused the new login"),
        "env_mismatch": FakeWS(environment="demo"),
        "refuses_all": FakeWS(replies=[{"errorText": "no entitlement"}] * 2),
        "refuses_more": FakeWS(replies=[{"historicalId": 1, "realtimeId": 2},
                                        {"errorText": "no entitlement"}]),
        "p_ticket": FakeWS(replies=[{"p-ticket": "tk", "p-time": 999},
                                    {"p-ticket": "tk", "p-time": 999}]),
        "drops_mid_subscribe": Dropping(),
    }[case]
    want = {"connect_raises": "md refused the new login", "env_mismatch": "no valid live md token",
            "refuses_all": "refused every symbol", "refuses_more": "refused 1 symbol",
            "p_ticket": "refused every symbol", "drops_mid_subscribe": "websocket not connected"}[case]
    rig = Rig(["NQ", "ES"], ordinary=lambda: old, env_socks={"live": cand})

    async def body():
        await rig.up()
        sent_before, refills_before = list(old.sent), len(rig.refills)
        with pytest.raises(RuntimeError, match=want):
            await rig.feed.switch_md("live")
        await rig.polls(30)                                   # run()'s NEXT steps
        _push(old, 101, 77)
        _still_serving(rig, old)
        return sent_before, refills_before

    sent_before, refills_before = rig.drive(body)
    f = rig.feed
    assert old.sent == sent_before                            # the old login spent nothing
    assert len(rig.refills) == refills_before                 # no refill for a rejected candidate
    assert rig.ticks[-1] == ("NQ", [1077])                    # ... and it still routes
    assert f.md_env == "demo" and f.refused == {} and f.error is None
    assert f.contracts == {"NQ": nq, "ES": es}
    assert f.switch_error["to"] == "live" and want in f.switch_error["error"]
    assert 1000 not in rig.slept                              # a p-ticket is never waited out
    if isinstance(cand, FakeWS):
        assert not cand.connected                             # the candidate was closed
    assert f.budget_used("demo") == 2                         # the target's requests are charged
    assert f.budget_used("live") == len(getattr(cand, "sent", []))   # to the target (I3/N4)


def test_the_930_window_opening_mid_switch_aborts_and_nothing_follows_inside_it():
    old = FakeWS()
    t0 = dt.datetime(2026, 9, 24, 9, 19, 58, tzinfo=ET).timestamp()
    rig = Rig(["NQ", "ES"], ordinary=lambda: old, now0=t0)

    class Clocked(FakeWS):
        async def request(self, ep, body=""):
            rig.clock[0] += 5                                 # the second root lands at 09:20:0x
            return await super().request(ep, body)

    cand = Clocked()
    rig.env_socks["live"] = cand
    rig.clock[0] = t0

    async def body():
        while not rig.feed.connected:
            await asyncio.sleep(0)
        rig.clock[0] = t0                                     # the switch starts at 09:19:58
        with pytest.raises(RuntimeError, match="9:30 window opened"):
            await rig.feed.switch_md("live")
        await rig.polls(60)                                   # a minute on, inside the window
        _still_serving(rig, old)

    rig.drive(body)
    assert len(cand.sent) == 1 and not cand.connected and rig.feed.md_env == "demo"


def test_a_switch_asked_inside_the_window_never_connects():
    old = FakeWS()
    rig = Rig(["NQ"], ordinary=lambda: old, env_socks={"live": FakeWS()},
              now0=dt.datetime(2026, 9, 24, 9, 25, tzinfo=ET).timestamp())

    async def body():
        await rig.up()
        with pytest.raises(RuntimeError, match="9:30 window"):
            await rig.feed.switch_md("live")
        await rig.polls(10)
        _still_serving(rig, old)

    rig.drive(body)
    assert [k for k, _ in rig.connects] == ["ordinary"]


def test_a_failed_switch_then_a_real_drop_reconnects_normally_on_the_old_login():
    """After a failed switch, the old socket's own drop is handled exactly as in main: backoff 5,
    an ordinary reconnect of the ACTIVE login, all roots resubscribed, no "worse than" check."""
    socks = [FakeWS(), FakeWS(replies=[{"historicalId": 1, "realtimeId": 2},
                                       {"errorText": "roll day"}])]
    rig = Rig(["NQ", "ES"], ordinary=lambda: socks.pop(0),
              env_socks={"live": RuntimeError("no live token")})

    async def body():
        await rig.up()
        first = rig.feed.ws
        with pytest.raises(RuntimeError):
            await rig.feed.switch_md("live")
        await rig.polls(3)
        first.connected = False
        while rig.feed.ws is first or not rig.feed.connected:
            await asyncio.sleep(0)
        await rig.polls(3)
        return rig.feed.ws

    second = rig.drive(body)
    assert [k for k, _ in rig.connects] == ["ordinary", "live", "ordinary"]
    assert [s for s in rig.slept if s != 1] == [5]
    assert rig.feed.md_env == "demo" and rig.feed.reconnects == 1
    assert "ES" in rig.feed.refused and second.sent                     # one refusal is just a refusal


# ---- switches while nothing is up ----

def test_a_switch_during_backoff_cuts_it_short_and_becomes_the_next_connect():
    rig = Rig(["NQ"], ordinary=lambda: _raise(RuntimeError("demo down")),
              env_socks={"live": FakeWS()}, block_backoff=True)

    async def body():
        while not any(s != 1 for s in rig.slept):
            await asyncio.sleep(0)
        got = await rig.feed.switch_md("live")
        await rig.polls(5)
        return got

    got = rig.drive(body)
    assert got == "live" and rig.feed.md_env == "live"
    assert [k for k, _ in rig.connects] == ["live"]           # the ordinary connect failed before
    assert rig.feed.connected is False                        # (stopped at the end of the drive)


def _raise(e):
    async def f():
        raise e
    return f()


def test_a_failed_switch_while_down_backs_off_then_reconnects_the_active_login():
    good = FakeWS()
    calls = {"n": 0}

    def ordinary():
        calls["n"] += 1
        return _raise(RuntimeError("demo down")) if calls["n"] == 1 else good

    rig = Rig(["NQ"], ordinary=ordinary, env_socks={"live": RuntimeError("no live token")},
              block_backoff=True)

    async def body():
        while not any(s != 1 for s in rig.slept):
            await asyncio.sleep(0)
        with pytest.raises(RuntimeError, match="no live token"):
            await rig.feed.switch_md("live")
        while not any(s != 1 for s in rig.slept[1:]):         # the failed switch's own backoff
            await asyncio.sleep(0)
        rig.gate.set()                                        # let it elapse
        while rig.feed.ws is not good:
            await asyncio.sleep(0)
        await rig.polls(3)

    rig.drive(body)
    f = rig.feed
    # "demo" connect failed (in the ordinary connect's own call, not recorded) -> the switch ->
    # a backoff -> the active login again
    assert [k for k, _ in rig.connects] == ["live", "ordinary"]
    assert [s for s in rig.slept if s != 1] == [5, 10]
    assert f.md_env == "demo" and f.switch_error["to"] == "live"


def test_a_switch_while_an_ordinary_connect_is_in_flight_waits_its_turn():
    entered, release = asyncio.Event(), asyncio.Event()
    demo, live = FakeWS(), FakeWS()

    async def slow():
        entered.set()
        await release.wait()
        return demo

    rig = Rig(["NQ"], ordinary=slow, env_socks={"live": live})

    async def body():
        await entered.wait()
        sw = asyncio.ensure_future(rig.feed.switch_md("live"))
        await asyncio.sleep(0)
        release.set()
        got = await sw
        await rig.polls(3)
        return got, rig.feed.ws is live

    got, is_live = rig.drive(body)
    assert got == "live" and is_live and not demo.connected
    assert [k for k, _ in rig.connects] == ["ordinary", "live"]   # one connector, in turn


def test_a_second_switch_while_one_is_in_flight_is_refused_with_switchinprogress():
    entered, release = asyncio.Event(), asyncio.Event()
    live = FakeWS()

    async def slow_live():
        entered.set()
        await release.wait()
        return live

    rig = Rig(["NQ"], env_socks={"live": slow_live})

    async def body():
        await rig.up()
        first = asyncio.ensure_future(rig.feed.switch_md("live"))
        await entered.wait()
        with pytest.raises(SwitchInProgress):
            await rig.feed.switch_md("demo")
        assert rig.feed.status()["switching_to"] == "live"
        release.set()
        return await first

    assert rig.drive(body) == "live"


# ---- the Future is always answered (N3) ----

def test_switch_md_is_refused_when_run_is_not_running():
    feed = TickFeed(["NQ"], lambda *a: None, sleep=nosleep, md_env="demo")
    with pytest.raises(RuntimeError, match="not running"):
        run(asyncio.wait_for(feed.switch_md("live"), 5))     # answered, never left hanging
    assert feed.switch_in_progress is False


def test_cancelling_run_mid_switch_answers_the_switch_and_closes_the_candidate():
    entered = asyncio.Event()

    class Hanging(FakeWS):
        async def request(self, ep, body=""):
            entered.set()
            await asyncio.Event().wait()

    cand = Hanging()
    rig = Rig(["NQ"], env_socks={"live": cand})

    async def go():
        task = asyncio.ensure_future(rig.feed.run())
        await rig.up()
        sw = asyncio.ensure_future(rig.feed.switch_md("live"))
        await entered.wait()
        task.cancel()
        with pytest.raises(RuntimeError, match="feed stopped"):
            await asyncio.wait_for(sw, 5)
        with pytest.raises(asyncio.CancelledError):
            await task

    run(go())
    assert not cand.connected and rig.feed.switch_in_progress is False
    assert rig.feed.md_env == "demo"


def test_stop_during_a_pending_switch_answers_it():
    rig = Rig(["NQ"], ordinary=lambda: _raise(RuntimeError("down")),
              env_socks={"live": FakeWS()}, block_backoff=True)

    async def go():
        task = asyncio.ensure_future(rig.feed.run())
        while not any(s != 1 for s in rig.slept):
            await asyncio.sleep(0)
        rig.feed._pending_env = "live"                         # a request run() has not reached
        rig.feed._pending_fut = asyncio.get_running_loop().create_future()
        fut = rig.feed._pending_fut
        rig.feed.stop()
        await asyncio.wait_for(task, 5)
        with pytest.raises(RuntimeError, match="feed stopped"):
            await fut

    run(go())
    assert rig.feed.switch_in_progress is False


# ---- status, budget, startup ----

def test_switch_error_appears_in_status_and_clears_on_the_next_successful_switch():
    old, live = FakeWS(), FakeWS()
    rig = Rig(["NQ"], ordinary=lambda: old, env_socks={"live": [RuntimeError("first fails"), live]})

    async def body():
        await rig.up()
        with pytest.raises(RuntimeError):
            await rig.feed.switch_md("live")
        assert rig.feed.status()["switch_error"]["to"] == "live"
        await rig.polls(3)
        await rig.feed.switch_md("live")
        return rig.feed.status()

    st = rig.drive(body)
    assert st["switch_error"] is None and st["md"] == "live" and st["switching_to"] is None


def test_budget_is_tracked_per_login_and_charged_to_the_target():
    rig = Rig(["NQ", "ES"], env_socks={"live": FakeWS()})

    async def body():
        await rig.up()
        assert rig.feed.budget_used("demo") == 2 and rig.feed.budget_used("live") == 0
        await rig.feed.switch_md("live")

    rig.drive(body)
    f = rig.feed
    assert f.budget_used("live") == 2 and f.budget_used("demo") == 2
    assert f.budget_used() == f.budget_used("live")


def test_startup_takes_whatever_login_connects_like_main_and_says_so_in_status():
    """M-a, decided: an ordinary connect never fails closed (main never did, and a dark chart
    helps nobody); a socket that is not the configured login is reported, never hidden."""
    ws = FakeWS(environment="live")
    rig = Rig(["NQ"], md_env="demo")
    rig.feed._connect = lambda: _ret(ws)

    async def body():
        await rig.up()
        return rig.feed.status()

    st = rig.drive(body)
    assert st["md"] == "demo" and st["error"] is None
    assert "no valid md token" in st["md_mismatch"] and "live" in st["md_mismatch"]


async def _ret(v):
    return v


def test_an_ordinary_reconnect_starts_from_fresh_subscriptions():
    """M-e: main's `self.subs = {}` per cycle -- ids from a dead socket never linger."""
    socks = [FakeWS(), FakeWS(replies=[{"historicalId": 21, "realtimeId": 201}])]
    rig = Rig(["NQ"], ordinary=lambda: socks.pop(0))

    async def body():
        await rig.up()
        first = rig.feed.ws
        first.connected = False
        while rig.feed.ws is first or not rig.feed.connected:
            await asyncio.sleep(0)
        return dict(rig.feed.subs)

    subs = rig.drive(body)
    nq = symbols.resolve_contract("NQ")
    assert subs == {21: ("NQ", nq), 201: ("NQ", nq)}          # the dead socket's 11/101 are gone


def test_a_switch_while_down_to_a_login_refusing_every_root_backs_off_normally():
    """Re-review 2, R1: the refused-all verdict is about the OTHER login -- the active one must come
    back on the ordinary 5 s backoff, never the 10-minute refused wait (which near 09:14 would have
    run past 09:35 and kept the charts dark through the open)."""
    good = FakeWS()
    calls = {"n": 0}

    def ordinary():
        calls["n"] += 1
        return _raise(RuntimeError("demo down")) if calls["n"] == 1 else good

    rig = Rig(["NQ"], ordinary=ordinary, env_socks={"live": FakeWS(replies=[{"errorText": "Access is denied"}])},
              block_backoff=True)

    async def body():
        while not any(s != 1 for s in rig.slept):
            await asyncio.sleep(0)
        with pytest.raises(Exception):
            await rig.feed.switch_md("live")
        while not any(s != 1 for s in rig.slept[1:]):
            await asyncio.sleep(0)
        rig.gate.set()
        while rig.feed.ws is not good:
            await asyncio.sleep(0)
        await rig.polls(3)

    rig.drive(body)
    waits = [s for s in rig.slept if s != 1]
    assert waits[:2] == [5, 10] and 600 not in waits and rig.feed.md_env == "demo"


# ------------------------------------------------------------------ the early rebuild (RECYCLE)
# 2026-09-28: the desk renews its tokens early (weekdays 09:10-09:19:30 ET); a socket still on
# the old md token is rebuilt on the freshest one then, make-before-break, so it cannot die at
# the old token's expiry during the open the user trades from these charts.

T_REBUILD = dt.datetime(2026, 9, 14, 9, 15, tzinfo=ET).timestamp()     # a Monday, in the window


def _tok(ws, token):
    ws.token = token
    return ws


def test_the_rebuild_window_is_the_desks_early_renewal_window():
    from homebase.broker import tradovate
    from homebase.charts.tickfeed import RECYCLE
    assert RECYCLE == (tradovate.RENEW_EARLY_FROM, tradovate.RENEW_QUIET[0])


def test_a_socket_on_an_older_md_token_is_rebuilt_make_before_break_before_0920():
    from homebase.charts.tickfeed import RECYCLE_PACE_S
    old, new = _tok(FakeWS(), "md-1"), _tok(FakeWS(), "md-2")
    rig = Rig(["NQ", "ES", "GC"], ordinary=lambda: old, env_socks={"demo": new}, now0=T_REBUILD)
    rig.feed._fresh_token = lambda prefer_live: ("md-2", "demo")

    async def body():
        await rig.polls(3)
        _push(new, 101, 77)                                  # the new socket routes
        return rig.feed.ws, rig.feed.connected

    in_use, up = rig.drive(body)
    f = rig.feed
    assert in_use is new and up and not old.connected and f._on_event not in old.event_handlers
    assert [b["symbol"] for _, b in new.sent] == [symbols.resolve_contract(r)
                                                  for r in ("NQ", "ES", "GC")]
    assert rig.slept.count(RECYCLE_PACE_S) == 2              # 3 getCharts, paced: no burst
    # the startup's refills only (one per root, on the old socket): none after the rebuild,
    # the old socket served until the install -- there is no gap to fill
    assert [(r, w) for r, _, w in rig.refills] == [("NQ", old), ("ES", old), ("GC", old)]
    assert f.recycle["ok"] is True and f.switch_error is None and f.md_env == "demo"
    assert ("NQ", [1077]) in rig.ticks and f.reconnects == 0
    assert [k for k, _ in rig.connects] == ["ordinary", "demo"]


@pytest.mark.parametrize("start, disk, budget_used", [
    ((2026, 9, 14, 9, 15), ("md-1", "demo"), 0),      # already on the freshest token
    ((2026, 9, 14, 9, 19, 30), ("md-2", "demo"), 0),  # the window is over: reconnects as today
    ((2026, 9, 14, 9, 5), ("md-2", "demo"), 0),       # not yet
    ((2026, 9, 19, 9, 15), ("md-2", "demo"), 0),      # Saturday
    ((2026, 9, 14, 9, 15), ("md-2", "live"), 0),      # only the other login has a fresh one
    ((2026, 9, 14, 9, 15), ("md-2", "demo"), 118),    # the hour's budget: kept for the open
])
def test_no_rebuild_unless_due(start, disk, budget_used):
    old = _tok(FakeWS(), "md-1")
    rig = Rig(["NQ", "ES", "GC"], ordinary=lambda: old, env_socks={"demo": _tok(FakeWS(), "x")},
              now0=dt.datetime(*start, tzinfo=ET).timestamp())
    rig.feed._fresh_token = lambda prefer_live: disk
    rig.feed._requests["demo"] = [rig.clock[0]] * budget_used

    async def body():
        await rig.up()
        await rig.polls(4)
        return rig.feed.ws, old.connected

    in_use, up = rig.drive(body)
    assert in_use is old and up and rig.feed.recycle is None
    assert [k for k, _ in rig.connects] == ["ordinary"]


def test_one_rebuild_a_day():
    from homebase.charts.tickfeed import RECYCLE_CHECK_S
    old, new, newer = (_tok(FakeWS(), t) for t in ("md-1", "md-2", "md-3"))
    rig = Rig(["NQ"], ordinary=lambda: old, env_socks={"demo": [new, newer]}, now0=T_REBUILD)
    disk = {"tok": "md-2"}
    rig.feed._fresh_token = lambda prefer_live: (disk["tok"], "demo")

    async def body():
        await rig.up()
        await rig.polls(2)
        disk["tok"] = "md-3"                                 # renewed again the same morning
        await rig.polls(RECYCLE_CHECK_S * 3)
        return rig.feed.ws

    assert rig.drive(body) is new and [k for k, _ in rig.connects] == ["ordinary", "demo"]


def test_a_failed_rebuild_keeps_the_socket_serving_and_is_not_retried_that_day():
    from homebase.charts.tickfeed import RECYCLE_CHECK_S
    old = _tok(FakeWS(), "md-1")
    refusing = _tok(FakeWS(replies=[{"errorText": "Access is denied"}] * 3), "md-2")
    rig = Rig(["NQ", "ES", "GC"], ordinary=lambda: old,
              env_socks={"demo": [refusing, _tok(FakeWS(), "md-2")]}, now0=T_REBUILD)
    rig.feed._fresh_token = lambda prefer_live: ("md-2", "demo")

    async def body():
        await rig.up()
        await rig.polls(RECYCLE_CHECK_S * 3)
        _push(old, 101, 55)
        return rig.feed.ws, old.connected

    in_use, up = rig.drive(body)
    f = rig.feed
    assert in_use is old and up and not refusing.connected
    assert f.recycle["ok"] is False and "refused every symbol" in f.recycle["error"]
    assert f.switch_error is None and f.reconnects == 0      # the user's switch state untouched
    assert [k for k, _ in rig.connects] == ["ordinary", "demo"]
    assert ("NQ", [1055]) in rig.ticks


def test_the_swap_marks_a_gap_for_every_root_it_moved_in_the_real_recording(tmp_path):
    """The swap can lose one tick per root (its copies straddle the install) and nothing
    refills it (budget): the recording gets a gap marker around the swap -- the real
    LiveRecorder, in a temp dir, read back from the file the store reads."""
    import json
    from homebase.charts.recorder import LiveRecorder
    from homebase.charts.session import session_date
    from homebase.charts.store import gaps_path
    from homebase.charts.tickfeed import SWAP_GAP_MS
    rec = LiveRecorder(tmp_path)
    old, new = _tok(FakeWS(), "md-1"), _tok(FakeWS(), "md-2")
    rig = Rig(["NQ", "ES"], ordinary=lambda: old, env_socks={"demo": new}, now0=T_REBUILD)
    rig.feed._fresh_token = lambda prefer_live: ("md-2", "demo")
    rig.feed.on_gap = rec.mark_gap_span

    async def body():
        await rig.polls(3)
        return rig.feed.ws

    assert rig.drive(body) is new
    d = session_date(int(T_REBUILD * 1000), "NQ")
    marks = {r: json.loads(gaps_path(rec.path(r, d, symbols.resolve_contract(r))).read_text())
             for r in ("NQ", "ES")}
    (a, b), = marks["NQ"]
    assert marks["ES"] == [[a, b]]                       # one marker per root, the same swap
    assert b - a == sum(SWAP_GAP_MS)
    assert T_REBUILD * 1000 <= a + SWAP_GAP_MS[0] <= rig.clock[0] * 1000
    assert rig.feed.recycle["ok"] is True and "gap_error" not in rig.feed.recycle
    assert [k for k, _ in rig.connects] == ["ordinary", "demo"]   # no refill, no other request


def test_a_marker_that_fails_never_undoes_the_swap():
    old, new = _tok(FakeWS(), "md-1"), _tok(FakeWS(), "md-2")
    rig = Rig(["NQ"], ordinary=lambda: old, env_socks={"demo": new}, now0=T_REBUILD)
    rig.feed._fresh_token = lambda prefer_live: ("md-2", "demo")

    def disk_full(*a):
        raise OSError("disk full")

    rig.feed.on_gap = disk_full

    async def body():
        await rig.polls(3)
        return rig.feed.ws

    assert rig.drive(body) is new
    assert rig.feed.recycle["ok"] is True and "disk full" in rig.feed.recycle["gap_error"]


def test_the_chart_service_wires_the_swap_marker_to_its_recorder(tmp_path, monkeypatch):
    import homebase.charts.server as cs
    from homebase.charts.recorder import LiveRecorder
    from tests.test_charts_settings_server import FakeMdWS, app_with
    seen = {}

    class Capture(cs.TickFeed):
        def __init__(self, *a, **k):
            seen.update(k)
            super().__init__(*a, **k)

    monkeypatch.setattr(cs, "TickFeed", Capture)
    app_with(tmp_path, {"demo": FakeMdWS("demo")})
    assert seen["on_gap"].__func__ is LiveRecorder.mark_gap_span


def test_a_refused_root_backs_off_exponentially_and_resets_when_it_subscribes():
    """Review 5: a refused root was asked every 10 min for ever (3 refused FX
    roots = 18 getCharts an hour of the live login's 180). Now 10, 20, 40 min
    ... at most 4 h; a success resets it."""
    t0 = dt.datetime(2026, 9, 24, 11, 0, tzinfo=ET).timestamp()
    clock = [t0]
    btc = symbols.resolve_contract("BTC")
    asked, ok = [], {"from": t0 + 5 * 3600}

    class WS(FakeWS):
        async def request(self, ep, body=""):
            if body["symbol"] == btc:
                asked.append(round((clock[0] - t0) / 60))
                if clock[0] < ok["from"]:
                    self.sent.append((ep, body))
                    return {"errorText": "no entitlement"}
            return await super().request(ep, body)

    ws = WS()

    async def connect():
        return ws

    async def sleep(_s):
        await asyncio.sleep(0)
        clock[0] += 60
        if clock[0] >= t0 + 7 * 3600:
            feed.stop()

    feed = TickFeed(["NQ", "BTC"], lambda *a: None, connect=connect, sleep=sleep, now=lambda: clock[0])
    run(feed.run())
    assert asked[:5] == [0, 10, 30, 70, 150]             # minutes after 11:00: +10, +20, +40, +80
    assert asked[5] == 310 and "BTC" not in feed.refused  # +160, now entitled
    assert feed._retry_n == {}


def test_the_feed_publishes_its_hourly_chart_requests_for_the_tick_job(tmp_path):
    clock = [1_790_000_000.0]
    feed = TickFeed(["NQ"], lambda *a: None, now=lambda: clock[0], usage_path=tmp_path / "md_usage.json")
    feed.count_request("live")
    clock[0] += 3000
    feed.count_request("live")
    feed.count_request("demo")
    clock[0] += 1000
    feed.count_request("live")
    got = __import__("json").loads((tmp_path / "md_usage.json").read_text())
    assert got == {"requests": {"live": [1_790_003_000.0, 1_790_004_000.0], "demo": [1_790_003_000.0]}}


def test_a_failed_reconnect_waits_out_the_0930_window_but_the_first_one_goes_at_once():
    t0 = dt.datetime(2026, 9, 24, 9, 24, tzinfo=ET).timestamp()
    clock, waits, tries = [t0], [], []

    async def connect():
        tries.append(clock[0])
        raise OSError("network is down")

    async def sleep(s):
        await asyncio.sleep(0)
        waits.append(s)
        clock[0] += s
        if len(tries) >= 3:
            feed.stop()

    feed = TickFeed(["NQ"], lambda *a: None, connect=connect, sleep=sleep, now=lambda: clock[0])
    run(feed.run())
    assert waits[0] == 5                                   # the first reconnect: at once
    assert dt.datetime.fromtimestamp(tries[2], ET).time() >= dt.time(9, 35)   # then past 09:35
