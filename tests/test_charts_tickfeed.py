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
