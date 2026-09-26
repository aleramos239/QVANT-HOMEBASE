"""Tick feed: one subscription per root, routing by chart id, penalty, reconnect backoff."""
from __future__ import annotations

import asyncio

from homebase import symbols
from homebase.charts.tickfeed import TickFeed


def run(coro):
    return asyncio.run(coro)


class FakeWS:
    def __init__(self, replies=None):
        self.connected = True
        self.event_handlers = []
        self.sent = []
        self.replies = list(replies or [])

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
