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
    assert asked == [dt.time(9, 12), dt.time(9, 35), dt.time(9, 45), dt.time(9, 55)]   # 09:22 is skipped


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
    assert retried == [symbols.resolve_contract("BTC")]        # GC and SI wait for the window to close


# ------------------------------------------------------------------ switch_md
# Task 4, 2026-09-27 accounts-paper-layouts-appsettings plan: the runtime market-data login
# switch, hardened in Fix round 1 after review of bdaccbd (C1/C2/I1/I2/I3/I4/M3). switch_md only
# ever leaves a REQUEST for run() to service -- there is no second connector -- so every test
# here drives run() as a live background task alongside switch_md, never hand-setting feed.ws
# the way the pre-review version did (that shape can no longer express what changed: switch_md
# now genuinely depends on run() to resolve it).
#
# `feed.ws` and `.connected` only mean anything WHILE run() is still active: _drive's teardown
# (feed.stop(), the same as a real shutdown) closes and nulls `feed.ws` like any other cycle end.
# So every check of "which socket is live" happens INSIDE body(), before _drive tears down --
# `feed.md_env`, `.subs`, `.refused`, `.switch_error` and a FakeWS's own `.connected`/`.sent` all
# outlive the drive and are asserted after it, exactly like the pre-existing tests above.

async def _drive(feed, body):
    """Runs feed.run() as a background task for the duration of `body()`, then stops it and
    waits for it to actually exit -- every test below's shape, so a bug that hangs run() fails
    the test (5 s) instead of hanging the whole suite."""
    task = asyncio.ensure_future(feed.run())
    try:
        return await asyncio.wait_for(body(), timeout=5)
    finally:
        feed.stop()
        await asyncio.wait_for(task, timeout=5)


def test_switch_md_subscribes_before_installing_and_closes_and_detaches_the_old_socket():
    old_ws, new_ws = FakeWS(), FakeWS()

    async def connect():
        return old_ws

    async def connect_env(env):
        assert env == "live"
        return new_ws

    feed = TickFeed(["NQ", "ES"], lambda *a: None, connect=connect, connect_env=connect_env,
                    sleep=nosleep, md_env="demo")

    async def body():
        while not feed.connected:      # let run() finish its initial "demo" connect first
            await asyncio.sleep(0)
        assert feed.ws is old_ws
        got = await feed.switch_md("live")
        return got, feed.ws is new_ws, feed._on_event in new_ws.event_handlers

    got, ws_is_new, handler_on_new = run(_drive(feed, body))
    assert got == "live" and feed.md_env == "live"
    assert ws_is_new and handler_on_new
    assert not old_ws.connected                              # closed once the new socket was proven
    assert feed._on_event not in old_ws.event_handlers        # M3: detached, not just outgrown
    # re-subscribed on the NEW socket, one getChart per root -- no bulk history refetch
    assert [b["symbol"] for _, b in new_ws.sent] == [symbols.resolve_contract("NQ"), symbols.resolve_contract("ES")]
    assert sorted({root for root, _ in feed.subs.values()}) == ["ES", "NQ"]
    assert feed.switch_error is None


def test_switch_md_is_a_noop_when_already_on_that_login_and_connected():
    ws = FakeWS()
    feed = TickFeed(["NQ"], lambda *a: None, sleep=nosleep, md_env="live")
    feed.ws = ws
    got = run(feed.switch_md("live"))
    assert got == "live" and ws.sent == []                    # no getChart, nothing touched


def test_an_unknown_login_is_refused_without_touching_anything():
    feed = TickFeed(["NQ"], lambda *a: None, sleep=nosleep, md_env="demo")
    with pytest.raises(ValueError):
        run(feed.switch_md("paper"))
    assert feed.md_env == "demo" and feed._pending_env is None


def test_a_failed_connect_falls_back_and_keeps_the_old_login_and_socket():
    old_ws = FakeWS()

    async def connect():
        return old_ws

    async def connect_env(env):
        raise RuntimeError("md refused the new login")

    feed = TickFeed(["NQ"], lambda *a: None, connect=connect, connect_env=connect_env,
                    sleep=nosleep, md_env="demo")

    async def body():
        while not feed.connected:
            await asyncio.sleep(0)
        sent_before = list(old_ws.sent)
        with pytest.raises(RuntimeError, match="md refused the new login"):
            await feed.switch_md("live")
        return sent_before, feed.ws is old_ws, old_ws.connected

    sent_before, ws_is_old, old_connected = run(_drive(feed, body))
    assert ws_is_old and old_connected                        # the old socket was never touched
    assert feed.md_env == "demo"                              # unchanged: the caller must not persist it
    assert old_ws.sent == sent_before                          # no re-subscribe attempted on a failed switch
    assert feed._pending_env is None and feed._pending_fut is None
    assert feed.switch_error == {"to": "live", "error": "RuntimeError: md refused the new login",
                                 "at": feed.switch_error["at"]}


def test_a_second_switch_while_one_is_in_flight_is_refused_with_switchinprogress():
    entered = asyncio.Event()
    release = asyncio.Event()

    async def connect():
        return FakeWS()

    async def slow_connect_env(env):
        entered.set()
        await release.wait()
        return FakeWS()

    feed = TickFeed(["NQ"], lambda *a: None, connect=connect, connect_env=slow_connect_env,
                    sleep=nosleep, md_env="demo")

    async def body():
        while not feed.connected:
            await asyncio.sleep(0)
        first = asyncio.ensure_future(feed.switch_md("live"))
        await entered.wait()
        with pytest.raises(SwitchInProgress):
            await feed.switch_md("demo")
        release.set()
        return await first

    got = run(_drive(feed, body))
    assert got == "live" and feed.md_env == "live"


# ---- C2: the socket connect_env hands back must actually be the login that was asked for ----

def test_c2_environment_mismatch_is_a_failed_switch_and_closes_the_mismatched_socket():
    old_ws = FakeWS()

    async def connect():
        return old_ws

    mismatched = FakeWS(environment="demo")   # asked for "live", got a demo socket back

    async def connect_env(env):
        assert env == "live"
        return mismatched

    feed = TickFeed(["NQ"], lambda *a: None, connect=connect, connect_env=connect_env,
                    sleep=nosleep, md_env="demo")

    async def body():
        while not feed.connected:
            await asyncio.sleep(0)
        with pytest.raises(RuntimeError, match="asked for the live md login, got 'demo'"):
            await feed.switch_md("live")
        return feed.ws is old_ws, old_ws.connected

    ws_is_old, old_connected = run(_drive(feed, body))
    assert ws_is_old and old_connected
    assert feed.md_env == "demo"
    assert not mismatched.connected                           # the mismatched candidate was closed
    assert feed.switch_error["to"] == "live"


def test_c2_a_mismatch_at_startup_never_connects_and_shows_in_status():
    ws = FakeWS(environment="demo")

    async def connect_env(env):
        return ws

    slept = []

    async def sleep(s):
        slept.append(s)
        if len(slept) >= 2:
            feed.stop()
        await asyncio.sleep(0)

    feed = TickFeed(["NQ"], lambda *a: None, connect_env=connect_env, sleep=sleep, md_env="live")
    run(feed.run())
    assert not feed.connected
    assert "asked for the live md login" in feed.status()["error"]
    assert not ws.connected


# ---- C1: the three races the review reproduced against the OLD (two-connector) design ----

def test_race_switch_during_backoff_preempts_it_instead_of_waiting_it_out():
    attempts = {"demo": 0}

    async def connect():
        attempts["demo"] += 1
        raise RuntimeError("demo down")

    live_ws = FakeWS()

    async def connect_env(env):
        assert env == "live"
        return live_ws

    slept = []

    async def sleep(s):
        slept.append(s)
        await asyncio.Event().wait()   # blocks forever: only feed._wake can end this wait

    feed = TickFeed(["NQ"], lambda *a: None, connect=connect, connect_env=connect_env,
                    sleep=sleep, md_env="demo")

    async def body():
        while not slept:               # let run() fail once and settle into its backoff _wait
            await asyncio.sleep(0)
        assert attempts["demo"] == 1
        got = await feed.switch_md("live")
        return got, feed.ws is live_ws

    got, ws_is_live = run(_drive(feed, body))
    assert got == "live" and feed.md_env == "live" and ws_is_live
    assert attempts["demo"] == 1       # the backoff never actually elapsed -- the switch preempted it


def test_race_switch_while_a_normal_reconnects_own_connect_is_in_flight():
    """The switch arrives before run()'s OWN (non-switch) connect() call for the CURRENT login
    has even returned. review C1 bullet 2: the old design let the switch's socket get installed
    and then silently overwritten by this in-flight connect finishing after it. Here there is
    only one connector: the switch is simply picked up on run()'s NEXT iteration."""
    entered_connect = asyncio.Event()
    release_connect = asyncio.Event()

    async def connect():                     # the ordinary reconnect's own connect (md_env == "demo")
        entered_connect.set()
        await release_connect.wait()
        return FakeWS()

    live_ws = FakeWS()

    async def connect_env(env):
        assert env == "live"
        return live_ws

    feed = TickFeed(["NQ"], lambda *a: None, connect=connect, connect_env=connect_env,
                    sleep=nosleep, md_env="demo")

    async def body():
        await entered_connect.wait()          # run() is awaiting connect() for "demo" right now
        switch = asyncio.ensure_future(feed.switch_md("live"))
        await asyncio.sleep(0)                # let switch_md register its request (self.ws is still None)
        release_connect.set()                 # now let the in-flight "demo" connect finish
        got = await switch
        return got, feed.ws is live_ws, live_ws.connected

    got, ws_is_live, live_connected = run(_drive(feed, body))
    assert got == "live" and ws_is_live and live_connected
    assert feed.md_env == "live"


def test_race_switch_while_subscribing_a_normal_reconnect_aborts_that_attempt_cleanly():
    """The switch arrives while run() is mid-subscribe on its OWN (non-switch) candidate socket.
    review C1 bullet 3: the old design let the switch's socket take over while run()'s remaining
    _start calls kept landing on it too, double-subscribing every root. Here, closing the
    in-flight candidate makes its own subscribe fail (a real closed socket would too), which
    aborts that attempt; the switch is serviced cleanly on the next iteration."""
    entered_es = asyncio.Event()
    release_es = asyncio.Event()

    class SlowWS(FakeWS):
        def __init__(self):
            super().__init__()
            self._waited = False

        async def request(self, ep, body=""):
            if not self.connected:
                raise RuntimeError("websocket not connected")
            if not self._waited and ep == "md/getChart" and body.get("symbol") == symbols.resolve_contract("ES"):
                self._waited = True
                entered_es.set()
                await release_es.wait()
                if not self.connected:
                    raise RuntimeError("websocket not connected")
            return await super().request(ep, body)

    demo_ws = SlowWS()

    async def connect():
        return demo_ws

    live_ws = FakeWS()

    async def connect_env(env):
        assert env == "live"
        return live_ws

    feed = TickFeed(["NQ", "ES"], lambda *a: None, connect=connect, connect_env=connect_env,
                    sleep=nosleep, md_env="demo")

    async def body():
        await entered_es.wait()         # NQ subscribed; ES's getChart is in flight on demo_ws
        switch = asyncio.ensure_future(feed.switch_md("live"))
        await asyncio.sleep(0)
        release_es.set()                # the stuck ES request now sees its socket closed
        got = await switch
        return got, feed.ws is live_ws

    got, ws_is_live = run(_drive(feed, body))
    assert got == "live" and ws_is_live
    assert feed.md_env == "live"
    # both roots end up subscribed on the WINNING (live) socket only -- never doubled
    assert sorted({root for root, _ in feed.subs.values()}) == ["ES", "NQ"]
    assert [b["symbol"] for _, b in live_ws.sent] == [symbols.resolve_contract("NQ"), symbols.resolve_contract("ES")]


# ---- I1: a switch must not land somewhere worse than where it started ----

def test_i1_a_switch_that_refuses_every_root_falls_back():
    old_ws = FakeWS()

    async def connect():
        return old_ws

    bad_ws = FakeWS(replies=[{"errorText": "no entitlement"}])

    async def connect_env(env):
        return bad_ws

    feed = TickFeed(["NQ"], lambda *a: None, connect=connect, connect_env=connect_env,
                    sleep=nosleep, md_env="demo")

    async def body():
        while not feed.connected:
            await asyncio.sleep(0)
        with pytest.raises(Refused, match="every symbol refused"):
            await feed.switch_md("live")
        return feed.ws is old_ws, old_ws.connected

    ws_is_old, old_connected = run(_drive(feed, body))
    assert ws_is_old and old_connected
    assert feed.md_env == "demo"
    assert not bad_ws.connected
    assert "NQ" not in feed.refused                            # the OLD (working) picture is restored


def test_i1_a_switch_that_refuses_more_roots_than_the_old_login_falls_back():
    old_ws = FakeWS()   # both roots subscribe fine on the old login

    async def connect():
        return old_ws

    # the new login refuses ES (the old login had 0 refusals) -- strictly worse, must fall back
    bad_ws = FakeWS(replies=[{"historicalId": 1, "realtimeId": 2}, {"errorText": "no entitlement"}])

    async def connect_env(env):
        return bad_ws

    feed = TickFeed(["NQ", "ES"], lambda *a: None, connect=connect, connect_env=connect_env,
                    sleep=nosleep, md_env="demo")

    async def body():
        while not feed.connected:
            await asyncio.sleep(0)
        with pytest.raises(RuntimeError, match="refused 1 root"):
            await feed.switch_md("live")
        return feed.ws is old_ws

    ws_is_old = run(_drive(feed, body))
    assert ws_is_old
    assert feed.md_env == "demo"
    assert feed.refused == {}                                  # the old login's own (clean) picture, restored


def test_i1_a_p_ticket_during_a_switch_counts_as_a_refusal_not_a_stalled_wait():
    old_ws = FakeWS()

    async def connect():
        return old_ws

    slept = []

    async def sleep(s):
        slept.append(s)
        await asyncio.sleep(0)

    penalized_ws = FakeWS(replies=[{"p-ticket": "tk", "p-time": 999}])

    async def connect_env(env):
        return penalized_ws

    feed = TickFeed(["NQ"], lambda *a: None, connect=connect, connect_env=connect_env,
                    sleep=sleep, md_env="demo")

    async def body():
        while not feed.connected:
            await asyncio.sleep(0)
        slept.clear()
        with pytest.raises(Refused):
            await feed.switch_md("live")
        return feed.ws is old_ws

    ws_is_old = run(_drive(feed, body))
    assert 1000 not in slept                                    # never slept out the p-ticket's wait_s (999 + 1)
    assert ws_is_old and feed.md_env == "demo"


# ---- I2: a failed switch is reported in status(), cleared by the next success ----

def test_i2_switch_error_appears_in_status_and_clears_on_the_next_successful_switch():
    old_ws, live_ws = FakeWS(), FakeWS()

    async def connect():
        return old_ws

    calls = {"n": 0}

    async def connect_env(env):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("first attempt fails")
        return live_ws

    feed = TickFeed(["NQ"], lambda *a: None, connect=connect, connect_env=connect_env,
                    sleep=nosleep, md_env="demo")

    async def body():
        while not feed.connected:
            await asyncio.sleep(0)
        with pytest.raises(RuntimeError):
            await feed.switch_md("live")
        assert feed.status()["switch_error"]["to"] == "live"
        await feed.switch_md("live")
        return feed.status()

    st = run(_drive(feed, body))
    assert st["switch_error"] is None
    assert st["md"] == "live"


# ---- I3: the md budget is tracked per login, not pooled ----

def test_i3_budget_is_tracked_per_login_not_pooled():
    old_ws, new_ws = FakeWS(), FakeWS()

    async def connect():
        return old_ws

    async def connect_env(env):
        return new_ws

    feed = TickFeed(["NQ", "ES"], lambda *a: None, connect=connect, connect_env=connect_env,
                    sleep=nosleep, md_env="demo")

    async def body():
        while not feed.connected:
            await asyncio.sleep(0)
        assert feed.budget_used("demo") == 2   # NQ + ES subscribed on the old login
        assert feed.budget_used("live") == 0   # never touched yet
        await feed.switch_md("live")

    run(_drive(feed, body))
    assert feed.budget_used("live") == 2       # NQ + ES subscribed fresh on the new login
    assert feed.budget_used("demo") == 2       # the old login's own hour is untouched by the switch
    assert feed.budget_used() == feed.budget_used("live")   # default = the ACTIVE login


# ---- I4: the 9:30 window opening mid-switch aborts to the old login ----

def test_i4_the_quiet_window_opening_mid_switch_aborts_and_falls_back():
    old_ws = FakeWS()

    async def connect():
        return old_ws

    t0 = dt.datetime(2026, 9, 24, 9, 19, 58, tzinfo=ET).timestamp()   # a Thursday, just before 09:20
    clock = [t0]

    class ClockedWS(FakeWS):
        async def request(self, ep, body=""):
            clock[0] += 5          # each getChart costs real time; the second root lands at 09:20:03
            return await super().request(ep, body)

    new_ws = ClockedWS()

    async def connect_env(env):
        return new_ws

    feed = TickFeed(["NQ", "ES"], lambda *a: None, connect=connect, connect_env=connect_env,
                    sleep=nosleep, now=lambda: clock[0], md_env="demo")

    async def body():
        while not feed.connected:
            await asyncio.sleep(0)
        with pytest.raises(RuntimeError, match="9:30 window opened"):
            await feed.switch_md("live")
        return feed.ws is old_ws

    ws_is_old = run(_drive(feed, body))
    assert ws_is_old and feed.md_env == "demo"
    assert new_ws.sent and not new_ws.connected                # NQ got as far as being asked, then aborted
