"""TradovateMD for the level timer: the trade hook (every push, with its size and stamp) and the 1-minute history."""
from __future__ import annotations

import asyncio
import datetime as dt

import pytest

from homebase.marketdata import TradovateMD


class Md(TradovateMD):
    """TradovateMD without a socket: the real _on_event / minute_bars over a scripted fake."""

    def __init__(self):                                     # no TradovateAuth, no state dir
        self._trades, self._tape, self._cid_sym, self._pushes = {}, {}, {3267315: "NQZ6"}, {}
        self._clock = lambda: 1000.0
        self.trade_hooks = []
        self._ws = None


def quote(price, size=2, ts="2026-09-14T13:29:59.950Z", cid=3267315, with_trade=True):
    entries = {"Trade": {"price": price, "size": size}} if with_trade else {"Bid": {"price": 1, "size": 1}}
    return {"e": "md", "d": {"quotes": [{"contractId": cid, "timestamp": ts, "entries": entries}]}}


def test_every_trade_push_reaches_the_hook_with_size_and_stamp():
    md, got = Md(), []
    md.trade_hooks.append(lambda *a: got.append(a))
    md._on_event(quote(20000.25, 3))
    md._on_event(quote(0, with_trade=False))                  # a bid-only push has no trade
    md._on_event(quote(1.0, cid=999))                          # a contract nobody subscribed
    (sym, px, size, seen, stamp), = got
    assert (sym, px, size, seen) == ("NQZ6", 20000.25, 3, 1000.0)
    assert stamp == dt.datetime(2026, 9, 14, 13, 29, 59, 950000, tzinfo=dt.timezone.utc).timestamp()
    assert md.last("NQZ6") == (20000.25, 1000.0)               # the anchor path the 9:30 bot reads is unchanged


def test_a_hook_that_raises_never_stops_the_quote_stream():
    md, got = Md(), []

    def bad(*a):
        raise RuntimeError("consumer bug")

    md.trade_hooks += [bad, lambda *a: got.append(a)]
    md._on_event(quote(1.0))
    md._on_event(quote(2.0))
    assert [g[1] for g in got] == [1.0, 2.0] and md.last("NQZ6")[0] == 2.0


def test_an_md_without_hooks_still_works():
    """FakeMDs in the timer tests copy _on_event onto classes that never set trade_hooks."""
    md = Md()
    del md.trade_hooks
    md._on_event(quote(5.0))
    assert md.last("NQZ6")[0] == 5.0


class FakeWS:
    def __init__(self, bars, eoh=True, silent=False):
        self.event_handlers, self.requests, self.bars, self.eoh, self.silent = [], [], bars, eoh, silent

    async def request(self, path, body=None):
        self.requests.append((path, body))
        if path == "md/getChart":
            if not self.silent:
                msg = {"e": "chart", "d": {"charts": [{"id": 7, "bars": self.bars, **({"eoh": True} if self.eoh else {})}]}}
                for h in list(self.event_handlers):
                    h(msg)
            return {"realtimeId": 7, "historicalId": 8}
        return {}


def bar(minute, o, h, l, c, up=3, down=2):
    return {"timestamp": f"2026-09-14T13:{minute:02d}:00.000Z", "open": o, "high": h, "low": l, "close": c,
            "upVolume": up, "downVolume": down}


def test_minute_bars_are_the_charts_one_minute_bars_ascending():
    md = Md()
    md._ws = FakeWS([bar(2, 3, 4, 2, 3), bar(0, 1, 2, 0, 1), {"timestamp": "bad"}, bar(1, 2, 3, 1, 2)])
    got = asyncio.new_event_loop().run_until_complete(md.minute_bars("NQ", 2))
    base = dt.datetime(2026, 9, 14, 13, 0, tzinfo=dt.timezone.utc).timestamp() * 1000
    assert [(b["start_ms"], b["o"], b["h"], b["l"], b["c"], b["v"]) for b in got] == \
        [(base + 60_000, 2.0, 3.0, 1.0, 2.0, 5), (base + 120_000, 3.0, 4.0, 2.0, 3.0, 5)]     # the last 2, oldest first
    path, body = md._ws.requests[0]
    assert body["chartDescription"] == {"underlyingType": "MinuteBar", "elementSize": 1,
                                        "elementSizeUnit": "UnderlyingUnits", "withHistogram": False}
    assert body["timeRange"] == {"asMuchAsElements": 3} and body["symbol"].startswith("NQ")
    assert md._ws.requests[1][0] == "md/cancelChart" and md._ws.event_handlers == []        # no chart left running


def test_minute_bars_time_out_when_the_chart_never_answers():
    md = Md()
    md._ws = FakeWS([], silent=True)
    with pytest.raises(RuntimeError, match="no data"):
        asyncio.new_event_loop().run_until_complete(md.minute_bars("NQ", 5, timeout_s=0.05))
    assert md._ws.event_handlers == []
