import asyncio

import pytest

from homebase.charts import exitrunner as xr


def view(net=0, avg=30900.0, orders=()):
    return {"positions": [{"symbol": "NQZ6", "root": "NQ", "net": net, "avg_price": avg}] if net else [],
            "orders": list(orders)}


def stop(price, oid="s1", side="Sell", status="Working"):
    return {"order_id": oid, "symbol": "NQZ6", "side": side, "type": "Stop", "stop_price": price, "status": status}


def arm(**kw):
    a = {"kind": "be", "root": "NQ", "side": "Buy", "accounts": ["a"], "level": 30920.0, "at": 1000.0,
         "seen": False, "done": [], "sent_at": 0}
    a.update(kw)
    return a


def test_parse_arm_refuses_bad_bodies():
    assert xr.parse_arm({"kind": "be", "root": "nq", "side": "Buy", "accounts": ["a"], "level": 1.5})["root"] == "NQ"
    assert xr.parse_arm({"kind": "trail", "root": "NQ", "side": "Sell", "accounts": ["a"], "dist": 20})["dist"] == 20
    for bad in ({}, {"kind": "x"}, {"kind": "be", "root": "NQ", "side": "Buy", "accounts": ["a"]},
                {"kind": "trail", "root": "NQ", "side": "Buy", "accounts": ["a"], "dist": 0},
                {"kind": "be", "root": "NQ", "side": "Long", "accounts": ["a"], "level": 1},
                {"kind": "be", "root": "NQ", "side": "Buy", "accounts": [], "level": 1}):
        with pytest.raises(ValueError):
            xr.parse_arm(bad)


def test_stop_plan_moves_adds_never_loosens():
    assert xr.stop_plan("Buy", [], 30900.25, 1, 0.25) == ("add", [])
    assert xr.stop_plan("Buy", [stop(30880)], 30900.25, 1, 0.25) == ("move", ["s1"])
    assert xr.stop_plan("Buy", [stop(30905)], 30900.25, 1, 0.25) == ("none", [])
    # a split bracket's two stops at one price: both move
    assert xr.stop_plan("Buy", [stop(30880, "s1"), stop(30880, "s2")], 30900.25, 1, 0.25) == ("move", ["s1", "s2"])
    assert xr.stop_plan("Buy", [stop(30880, "s1"), stop(30870, "s2")], 30900.25, 1, 0.25)[0] == "error"
    assert xr.stop_plan("Buy", [stop(30880, status="Suspended")], 30900.25, 1, 0.25)[0] == "error"
    assert xr.stop_plan("Sell", [stop(30920, side="Buy")], 30899.75, 1, 0.25) == ("move", ["s1"])
    # step: 3 ticks tighter is not enough for a 4-tick step
    assert xr.stop_plan("Buy", [stop(30904.25)], 30905, 4, 0.25) == ("none", [])


def test_breakeven_waits_fires_once_and_drops():
    a = arm()
    assert xr.arm_step(a, {"a": view(orders=[{"order_id": "e", "symbol": "NQZ6", "side": "Buy", "type": "Limit",
                                              "price": 30890, "status": "Working"}])}, 30930, 2000) == ("wait", None)
    assert xr.arm_step(a, {"a": view()}, 30930, 1005) == ("wait", None)          # just sent
    assert xr.arm_step(a, {"a": view()}, 30930, 1020) == ("drop", "no order")
    a = arm()
    assert xr.arm_step(a, {"a": view(1, orders=[stop(30880)])}, 30919.75, 1001) == ("wait", None)
    assert a["seen"]
    what, acts = xr.arm_step(a, {"a": view(1, orders=[stop(30880)])}, 30920, 1001)
    assert what == "act" and acts == [{"account": "a", "net": 1, "price": 30900.25, "plan": "move", "ids": ["s1"]}]
    a["done"].append("a")
    assert xr.arm_step(a, {"a": view(1, orders=[stop(30880)])}, 30925, 1001) == ("drop", "done")
    assert xr.arm_step(arm(seen=True), {"a": view()}, 30925, 1001) == ("drop", "flat")
    assert xr.arm_step(arm(), {"a": view(1)}, 30925, 1000 + 9 * 3600) == ("drop", "expired")
    assert xr.arm_step(arm(), {"a": view(-1)}, 30925, 1001)[0] == "wait", "the other side is not its trade"


def test_trail_follows_best_in_steps_and_waits_for_breakeven():
    a = arm(kind="trail", dist=20, be_id=None)
    del a["level"]
    v = {"a": view(1, orders=[stop(30880)])}
    what, acts = xr.arm_step(a, v, 30910, 1001)
    assert what == "act" and acts[0]["price"] == 30905 and acts[0]["plan"] == "move"
    a["sent_at"] = 1001
    assert xr.arm_step(a, v, 30915, 1002) == ("wait", None), "moves at most every 2 s"
    assert a["best"] == 30915
    # the market fell to the trail price: wait
    assert xr.arm_step(a, v, 30910, 1010) == ("wait", None)
    b = arm(kind="trail", dist=20, be_id="be1")
    assert xr.arm_step(b, v, 30910, 1001, frozenset({"be1"})) == ("wait", None)
    assert xr.arm_step(b, v, 30910, 1001, frozenset())[0] == "act"


def test_runner_sends_through_the_desk_actions_and_saves(tmp_path):
    sent = []

    async def send(action, body):
        sent.append((action, body))
        return {"results": {body.get("account") or body["accounts"][0]: {"ok": True}}}

    views = {"a": view(1, orders=[stop(30880)])}
    r = xr.ExitRunner(tmp_path / "arms.json", views=lambda: views, last_of=lambda root: 30920.0, send=send,
                      clock=lambda: 1001.0, log=lambda m: None)
    made = r.arm({"kind": "be", "root": "NQ", "side": "Buy", "accounts": ["a"], "level": 30920})
    asyncio.run(r.tick_once())
    assert [(a, b["order_id"], b["price"]) for a, b in sent] == [("modify", "s1", 30900.25)]
    asyncio.run(r.tick_once())
    assert len(sent) == 1, "each account once"
    assert r.arms == []
    # no stop: an exits action for the whole position
    views["a"] = view(2)
    r.arm({"kind": "be", "root": "NQ", "side": "Buy", "accounts": ["a"], "level": 30920})
    asyncio.run(r.tick_once())
    assert sent[-1][0] == "exits" and sent[-1][1]["sl_price"] == 30900.25 and sent[-1][1]["expected_net"] == {"a": 2}
    asyncio.run(r.tick_once())
    assert len(sent) == 2 and r.arms == [], "fired once, then dropped"
    # saved and read back
    r.arm({"kind": "trail", "root": "NQ", "side": "Buy", "accounts": ["a"], "dist": 8})
    again = xr.ExitRunner(tmp_path / "arms.json", views=lambda: {}, last_of=lambda root: None, send=send)
    assert [a["kind"] for a in again.arms] == ["trail"] and made["id"]
    assert again.cancel(again.arms[0]["id"]) and again.arms == []


def test_routes_arm_list_cancel_and_guards():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    async def send(action, body):
        return {"results": {}}

    r = xr.ExitRunner(None, views=lambda: {}, last_of=lambda root: None, send=send, log=lambda m: None)
    app = FastAPI()
    xr.register(app, runner=r, browser_write_ok=lambda req: None)
    c = TestClient(app, base_url="http://localhost:8852")
    j = {"content-type": "application/json"}
    made = c.post("/api/exitrunner/arm", headers=j,
                  json={"kind": "trail", "root": "NQ", "side": "Buy", "accounts": ["paper"], "dist": 20}).json()
    assert made["kind"] == "trail" and made["id"]
    assert [a["id"] for a in c.get("/api/exitrunner").json()["arms"]] == [made["id"]]
    assert c.post("/api/exitrunner/arm", headers=j, json={"kind": "trail"}).status_code == 400
    assert c.post("/api/exitrunner/arm", content=b"{}", headers={"content-type": "text/plain"}).status_code == 415
    assert c.get("/api/exitrunner", headers={"host": "evil.example"}).status_code == 403
    assert c.post("/api/exitrunner/cancel", headers=j, json={"id": made["id"]}).json() == {"ok": True}
    assert c.get("/api/exitrunner").json()["arms"] == []
    off = FastAPI()
    xr.register(off, runner=None, browser_write_ok=lambda req: None)
    assert TestClient(off, base_url="http://localhost").get("/api/exitrunner").status_code == 503
