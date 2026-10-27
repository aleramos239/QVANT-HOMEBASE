"""Audit 2026-10-27, chart group: the server BE/trail runner (homebase/charts/exitrunner.py)."""
import asyncio

from homebase.charts import exitrunner as xr
from tests.test_charts_exitrunner import stop, view


def runner(views, last, send, clock):
    return xr.ExitRunner(None, views=lambda: views, last_of=lambda root: last[0], send=send,
                         clock=lambda: clock[0], log=lambda m: None)


def test_a_refused_breakeven_send_keeps_the_arm_and_is_retried():
    sent, ok, clock = [], [False], [1001.0]

    async def send(action, body):
        sent.append(action)
        return {"results": {"a": {"ok": ok[0], "error": None if ok[0] else "a sell stop must be below the last price"}}}

    views = {"a": view(1, orders=[stop(30880)])}
    r = runner(views, [30920.0], send, clock)
    arm = r.arm({"kind": "be", "root": "NQ", "side": "Buy", "accounts": ["a"], "level": 30920})
    asyncio.run(r.tick_once())
    assert len(sent) == 1 and r.arms and r.arms[0]["error"] and r.arms[0]["done"] == []
    asyncio.run(r.tick_once())
    assert len(sent) == 1, "not hammered every 0.5 s"
    clock[0] += xr.RETRY_S + 0.1
    ok[0] = True
    asyncio.run(r.tick_once())
    assert len(sent) == 2 and r.arms[0]["done"] == ["a"] and r.arms[0]["error"] is None and arm["id"]
    asyncio.run(r.tick_once())
    assert r.arms == [], "landed once, then dropped"


def test_a_pending_order_error_is_not_marked_done():
    clock = [1001.0]

    async def send(action, body):
        return {"results": {}}

    pending = stop(30880, "s2", status="Suspended")
    views = {"a": view(1, orders=[stop(30880), pending])}
    r = runner(views, [30920.0], send, clock)
    r.arm({"kind": "be", "root": "NQ", "side": "Buy", "accounts": ["a"], "level": 30920})
    asyncio.run(r.tick_once())
    assert r.arms[0]["done"] == [] and "pending" in r.arms[0]["error"]
    views["a"] = view(1, orders=[stop(30880)])            # the other order cleared: the arm still fires
    asyncio.run(r.tick_once())
    assert r.arms[0]["done"] == ["a"]


def test_an_arm_with_no_price_says_so_after_15_s_and_clears_when_it_returns():
    clock, last = [1001.0], [None]

    async def send(action, body):
        return {"results": {"a": {"ok": True}}}

    r = runner({"a": view(1, orders=[stop(30880)])}, last, send, clock)
    r.arm({"kind": "trail", "root": "NQ", "side": "Buy", "accounts": ["a"], "dist": 20})
    asyncio.run(r.tick_once())
    assert r.arms[0]["error"] is None
    clock[0] += xr.NO_PRICE_S + 1
    asyncio.run(r.tick_once())
    assert r.arms[0]["error"] == xr.NO_PRICE
    last[0] = 30930.0
    asyncio.run(r.tick_once())
    assert r.arms[0]["error"] is None


def test_a_stop_not_sized_to_the_position_is_never_moved():
    odd = {**stop(30880), "qty": 3}                        # a Sell Stop of 3 against a long of 1
    assert xr.stop_plan("Buy", [odd], 30900.25, 1, 0.25, 1)[0] == "error"
    assert xr.stop_plan("Buy", [{**odd, "qty": 1}], 30900.25, 1, 0.25, 1) == ("move", ["s1"])
    clock = [1001.0]
    sent = []

    async def send(action, body):
        sent.append(action)
        return {"results": {"a": {"ok": True}}}

    r = runner({"a": view(1, orders=[odd])}, [30920.0], send, clock)
    r.arm({"kind": "be", "root": "NQ", "side": "Buy", "accounts": ["a"], "level": 30920})
    asyncio.run(r.tick_once())
    assert sent == [] and "not sized" in r.arms[0]["error"]


def test_every_account_of_one_arm_is_sent_in_the_same_tick():
    sent, clock = [], [1001.0]

    async def send(action, body):
        sent.append(body["account"])
        return {"results": {body["account"]: {"ok": True}}}

    views = {a: view(1, orders=[stop(30880)]) for a in ("a", "b", "c")}
    r = runner(views, [30920.0], send, clock)
    r.arm({"kind": "be", "root": "NQ", "side": "Buy", "accounts": ["a", "b", "c"], "level": 30920})
    asyncio.run(r.tick_once())
    assert sorted(sent) == ["a", "b", "c"], "no 3 s per-account stagger"
    assert r.arms[0]["done"] == ["a", "b", "c"] and not r.arms[0].get("retry_at")


def test_a_refused_account_is_retried_alone():
    sent, clock, bad = [], [1001.0], {"b"}

    async def send(action, body):
        a = body["account"]
        sent.append(a)
        return {"results": {a: {"ok": a not in bad, "error": "no" if a in bad else None}}}

    views = {a: view(1, orders=[stop(30880)]) for a in ("a", "b")}
    r = runner(views, [30920.0], send, clock)
    r.arm({"kind": "be", "root": "NQ", "side": "Buy", "accounts": ["a", "b"], "level": 30920})
    asyncio.run(r.tick_once())
    asyncio.run(r.tick_once())
    assert sorted(sent) == ["a", "b"], "b waits out its own gap, a is done"
    clock[0] += xr.RETRY_S + 0.1
    bad.clear()
    asyncio.run(r.tick_once())
    assert sorted(sent) == ["a", "b", "b"]
