"""Audit 2026-10-27 (feed group): MarketFeed.watch_bars leaves nothing half-registered when it fails, keeps what arrives with
its own reply, takes a late push as the bar's real close, and never logs in by password."""
from __future__ import annotations

import asyncio
import datetime as dt

import pytest

from homebase.data.feed import MarketFeed
from homebase.data.marketdata import TradovateMD

UTC = dt.timezone.utc


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def push(feed, cid, bars, eoh=False):
    feed._on_chart({"e": "chart", "d": {"charts": [
        {"id": cid, "eoh": True} if eoh else
        {"id": cid, "bars": [{"timestamp": ts, "open": o, "high": h, "low": l, "close": c,
                              "upVolume": v, "downVolume": 0} for ts, o, h, l, c, v in bars]}]}})


class WS:
    connected = True

    def __init__(self, reply=None, boom=None, feed=None, during=None):
        self.reply, self.boom, self.feed, self.during = reply, boom, feed, during

    async def request(self, op, body):
        if self.during:
            self.during()                          # a push in the same breath as the reply
        if self.boom:
            raise self.boom
        return self.reply


def feed_with(ws):
    f = MarketFeed("k", "demo", token_provider=lambda: "t")
    f._ws = ws
    f.resolve = lambda root: "NQZ6"
    return f


def test_a_failed_getchart_leaves_the_key_unwatched_so_it_is_asked_again():
    f = feed_with(WS(boom=TimeoutError("15 s")))
    with pytest.raises(TimeoutError):
        run(f.watch_bars("NQ", 5))
    assert f.watching() == {} and f._warming == set() and f._cur == {}
    f._retry_at.clear()                                          # the wait before the next ask is its own test
    f._ws = WS(reply={"realtimeId": 11, "historicalId": 12})
    run(f.watch_bars("NQ", 5))
    assert f.watching() == {("NQ", 5): 0} and f._watch == {11: ("NQ", 5), 12: ("NQ", 5)}


def test_a_reply_without_a_subscription_leaves_the_key_unwatched():
    f = feed_with(WS(reply={}))
    with pytest.raises(RuntimeError):
        run(f.watch_bars("NQ", 5))
    assert f.watching() == {} and f._warming == set()


def test_history_pushed_with_the_reply_is_kept_not_dropped():
    f = feed_with(None)
    f._ws = WS(reply={"realtimeId": 11, "historicalId": 12},
               during=lambda: (push(f, 12, [("2026-09-22T13:57Z", 1, 2, 0.5, 1.5, 10),
                                            ("2026-09-22T13:58Z", 1.5, 2, 1, 1.8, 11)]), push(f, 12, [], eoh=True)))
    run(f.watch_bars("NQ", 1))
    assert [b.ts.minute for b in f.bars("NQ", 1)] == [57] and f._warming == set() and f._early == {}


def test_a_late_push_replaces_the_bar_the_grace_closed_early():
    f = feed_with(None)
    f._watch[7] = ("NQ", 1)
    f._hist[("NQ", 1)], f._cur[("NQ", 1)] = [], None
    push(f, 7, [("2026-09-22T13:59Z", 1, 1.5, 1, 1.2, 1)])
    assert len(f.tick(dt.datetime(2026, 9, 22, 14, 0, 4, tzinfo=UTC))) == 1       # closed on the clock, incomplete
    push(f, 7, [("2026-09-22T13:59Z", 1, 3, 0.5, 2.5, 9)])                         # the lag ends: the real bar
    push(f, 7, [("2026-09-22T14:00Z", 2.5, 2.5, 2.5, 2.5, 1)])
    f.tick(dt.datetime(2026, 9, 22, 14, 0, 5, tzinfo=UTC))
    b, = f.bars("NQ", 1)
    assert (b.h, b.l, b.c) == (3, 0.5, 2.5)


def test_connect_never_falls_back_to_a_password_login():
    f = MarketFeed("k", "demo", token_provider=lambda: "")
    with pytest.raises(RuntimeError, match="not logging in"):
        run(f.connect())


def test_a_refused_subscribe_is_not_asked_again_every_pass():
    calls = []

    class Counting(WS):
        async def request(self, op, body):
            calls.append(op)
            return await super().request(op, body)
    f = feed_with(Counting(boom=TimeoutError("15 s")))
    with pytest.raises(TimeoutError):
        run(f.watch_bars("NQ", 5))
    run(f.watch_bars("NQ", 5))                                   # the next 1 s pass: held back, no request, no raise
    assert len(calls) == 1 and f.watching() == {}
    f._retry_at[("NQ", 5)] = 0.0                                 # the wait is over
    with pytest.raises(TimeoutError):
        run(f.watch_bars("NQ", 5))
    assert len(calls) == 2


def test_a_penalty_waits_longer_and_a_failed_subscribe_drops_the_stale_early_pushes():
    f = feed_with(WS(reply={"p-ticket": "x", "p-time": 0}, boom=None))
    f._ws.request = lambda op, body: (_ for _ in ()).throw(RuntimeError("getChart: p-ticket"))
    f._early[99] = [{"id": 99}]                                  # ids of a subscribe that died
    with pytest.raises(RuntimeError):
        run(f.watch_bars("NQ", 5))
    import time
    assert f._early == {} and f._retry_at[("NQ", 5)] - time.monotonic() > 250
