"""Audit 2026-10-27 (feed group): the md feed recycles a socket that is up but silent, follows the front-contract roll, resets
its backoff after a socket that delivered, says why it reconnected, and moves to a renewed token through the RTH day."""
from __future__ import annotations

import asyncio
import datetime as dt

import pytest

from homebase import symbols
from homebase.charts import tickfeed
from homebase.charts.session import ET
from homebase.charts.tickfeed import MdSilent, TickFeed
from tests.test_charts_tickfeed import FakeWS, Rig, _tok


def at(h, m=0, d=14):          # Monday 2026-09-14
    return dt.datetime(2026, 9, d, h, m, tzinfo=ET).timestamp()


def drive(feed, clock, advance, until):
    """run() with a fake clock that moves `advance` s on every sleep, until `until(feed)`."""
    async def sleep(_s):
        await asyncio.sleep(0)
        clock[0] += advance
        if until(feed):
            feed.stop()
    feed._sleep = sleep
    asyncio.run(asyncio.wait_for(feed.run(), 5))


def mk(clock, socks, **kw):
    async def connect():
        socks.append(FakeWS())
        return socks[-1]
    return TickFeed(["NQ", "ES"], lambda *a: None, connect=connect, now=lambda: clock[0], **kw)


def test_a_socket_that_is_up_but_sends_nothing_is_replaced_in_rth():
    clock, socks = [at(10)], []
    feed = mk(clock, socks)
    drive(feed, clock, 10, lambda f: len(socks) >= 2)
    assert len(socks) >= 2 and feed.drops[0]["error"].startswith("MdSilent: md silent: no NQ print")
    assert feed.drops[0]["lived_s"] >= tickfeed.SILENT_S


def test_a_quiet_market_outside_rth_or_with_prints_is_left_alone():
    for start in (at(20), at(10, d=19)):                           # evening, Saturday
        clock, socks = [start], []
        feed = mk(clock, socks)
        drive(feed, clock, 10, lambda f: clock[0] > start + 300)
        assert len(socks) == 1
    clock, socks = [at(10)], []
    feed = mk(clock, socks)

    def prints(f):
        if socks and f.subs:
            socks[0].push(min(f.subs), [{"t": 5, "p": 1, "s": 1, "id": 1}])
            socks[0].push(max(f.subs), [{"t": 5, "p": 1, "s": 1, "id": 1}])
        return clock[0] > at(10) + 300
    drive(feed, clock, 10, prints)
    assert len(socks) == 1


def test_silent_reconnects_in_a_row_wait_four_times_longer_each():
    clock, socks = [at(10)], []
    feed = mk(clock, socks)
    drive(feed, clock, 5, lambda f: len(socks) >= 3)
    first, second = feed.drops[0]["lived_s"], feed.drops[1]["lived_s"]
    assert second >= 4 * tickfeed.SILENT_S > first - 10


def test_the_session_roll_moves_the_feed_to_the_new_front_contract(monkeypatch):
    clock, socks = [at(10)], []
    feed = mk(clock, socks, watchdog=True)
    contract = {"c": None}
    real = tickfeed.session_contract

    def fake(root, ts):
        return contract["c"] if contract["c"] and root == "NQ" else real(root, ts)
    monkeypatch.setattr(tickfeed, "session_contract", fake)

    def until(f):
        if len(socks) == 1 and clock[0] > at(10) + 60:
            contract["c"] = "NQZ9"                                   # the roll
        for s in socks:
            for sid in f.subs:
                s.push(sid, [{"t": 5, "p": 1, "s": 1, "id": 1}])    # prints flow: not silent
        return len(socks) >= 2
    drive(feed, clock, 10, until)
    assert len(socks) == 2 and "front contract of NQ rolled" in feed.drops[0]["error"]


def test_a_socket_that_delivered_resets_the_backoff():
    clock, socks = [at(10)], []
    feed = mk(clock, socks, watchdog=False)
    state = {"n": 0}

    def until(f):
        if socks and f.subs and clock[0] > at(10) + 40 * (state["n"] + 1) - 20:
            socks[-1].push(min(f.subs), [{"t": 5, "p": 1, "s": 1, "id": 1}])
            socks[-1].connected = False                              # kicked after 40 s, having delivered
            state["n"] += 1
        return state["n"] >= 5
    slept = []
    orig = feed._backoff

    async def spy(wait):
        slept.append(wait)
        await orig(wait)
    feed._backoff = spy
    drive(feed, clock, 10, until)
    assert slept[:3] == [5, 5, 5]      # not 5, 10, 20


def test_a_flap_that_delivered_keeps_its_backoff_once_the_hours_budget_is_spent():
    clock, socks = [at(10)], []
    feed = mk(clock, socks, watchdog=False)
    feed._requests["demo"] = [clock[0] + 1] * 101   # ~100 getCharts already this hour
    feed._requests["live"] = list(feed._requests["demo"])
    state = {"n": 0}

    def until(f):
        if socks and f.subs and clock[0] > at(10) + 40 * (state["n"] + 1) - 20:
            socks[-1].push(min(f.subs), [{"t": 5, "p": 1, "s": 1, "id": 1}])
            socks[-1].connected = False
            state["n"] += 1
        return state["n"] >= 4
    slept = []
    orig = feed._backoff

    async def spy(wait):
        slept.append(wait)
        await orig(wait)
    feed._backoff = spy
    drive(feed, clock, 10, until)
    assert slept[:3] == [5, 10, 20]      # the reset is off: a 35 s flap must not run at 5 s a time against 180/h


def test_the_daytime_rebuild_waits_out_the_open():
    old = _tok(FakeWS(), "md-1")
    rig = Rig(["NQ"], ordinary=lambda: old, env_socks={"demo": _tok(FakeWS(), "x")}, now0=at(9, 30))
    rig.feed._fresh_token = lambda prefer_live: ("md-2", "demo")

    async def body():
        await rig.polls(3)
        return rig.feed.ws

    assert rig.drive(body) is old


def test_a_renewed_token_is_moved_to_after_the_early_window_too():
    from tests.test_charts_tickfeed import T_REBUILD  # noqa: F401
    old, new = _tok(FakeWS(), "md-1"), _tok(FakeWS(), "md-2")
    rig = Rig(["NQ"], ordinary=lambda: old, env_socks={"demo": new}, now0=at(11))
    rig.feed._fresh_token = lambda prefer_live: ("md-2", "demo")

    async def body():
        await rig.polls(3)
        return rig.feed.ws

    assert rig.drive(body) is new


def test_no_daytime_rebuild_in_the_evening():
    old = _tok(FakeWS(), "md-1")
    rig = Rig(["NQ"], ordinary=lambda: old, env_socks={"demo": _tok(FakeWS(), "x")}, now0=at(20))
    rig.feed._fresh_token = lambda prefer_live: ("md-2", "demo")

    async def body():
        await rig.up()
        await rig.polls(4)
        return rig.feed.ws

    assert rig.drive(body) is old
