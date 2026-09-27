"""The fake desk used by the chart page's browser checks. It never reaches a broker."""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from tools import fake_desk
from tools.fake_desk import FakeDesk, create_fake_desk, stream

KEY = "ab" * 32
H = {"x-homebase-key": KEY}
Q = {"NQ": {"bid": 30900.0, "ask": 30900.25, "last": 30900.25, "ts_ms": 1}}


def client(desk=None):
    return TestClient(create_fake_desk(KEY, desk or FakeDesk()))


def order(c, **kw):
    body = {"client_id": kw.pop("cid", "c1"), "accounts": kw.pop("accounts", ["sim041"]), "root": "NQ",
            "side": "Buy", "qty": 1, "type": "Market", "quotes": Q, **kw}
    return c.post("/api/trade/order", json=body, headers=H)


def acct(c, aid="sim041"):
    return next(a for a in c.get("/api/trade/state", headers=H).json()["accounts"] if a["id"] == aid)


def test_the_key_is_required_and_browsers_are_refused():
    c = client()
    assert c.get("/api/trade/state").status_code == 401
    assert c.get("/api/trade/state", headers={**H, "origin": "http://x"}).status_code == 403
    st = c.get("/api/trade/state", headers=H).json()
    assert st["enabled"] is True and st["limits"] == {"max_order_qty": 10, "max_position_qty": 20}
    assert [a["env"] for a in st["accounts"]] == ["demo", "demo", "live"]


def test_a_market_buy_fills_at_the_ask_and_rests_its_bracket_as_an_oco_pair():
    c = client()
    r = order(c, qty=2, sl_price=30890.0, tp_price=30920.0).json()
    assert r["results"]["sim041"]["ok"] is True
    a = acct(c)
    assert a["positions"] == [{"contract_id": 1, "symbol": "NQZ6", "net": 2, "avg_price": 30900.25,
                               "root": "NQ", "point_value": 20.0}]
    kinds = sorted((o["type"], o["side"], o["price"] or o["stop_price"]) for o in a["orders"])
    assert kinds == [("Limit", "Sell", 30920.0), ("Stop", "Sell", 30890.0)]
    tp = next(o for o in a["orders"] if o["type"] == "Limit")
    assert c.post("/fake/fill", json={"account": "sim041", "order_id": tp["order_id"]}).status_code == 200
    a = acct(c)
    assert a["positions"] == [] and a["orders"] == []          # the stop went with it (OCO)
    assert a["realized_pnl"] == pytest.approx((30920.0 - 30900.25) * 2 * 20)


def test_limit_rests_moves_and_cancels():
    c = client()
    oid = order(c, type="Limit", price=30880.13).json()["results"]["sim041"]["order_id"]
    assert acct(c)["orders"][0]["price"] == 30880.25               # tick-rounded
    assert c.post("/api/trade/modify", json={"client_id": "m", "account": "sim041", "order_id": oid,
                                             "price": 30870.0}, headers=H).json()["results"]["sim041"]["ok"]
    assert acct(c)["orders"][0]["price"] == 30870.0
    c.post("/api/trade/cancel", json={"client_id": "x", "account": "sim041", "order_id": oid}, headers=H)
    assert acct(c)["orders"] == []


def test_refusals_carry_the_desks_sentences():
    c = client()
    assert order(c, qty=11).json()["results"]["sim041"]["error"] == "quantity must be 1-10"
    r = order(c, type="Stop", price=30890.0).json()["results"]["sim041"]
    assert r == {"ok": False, "order_id": None, "error": "a buy stop must be above the last price (30,900.25)",
                 "refused": True}
    c.post("/fake/refuse", json={"reason": "NQZ6 on SIM0000041 is locked 09:20-09:35 ET for the nq930 bot"})
    assert "locked" in order(c).json()["results"]["sim041"]["error"]
    c.post("/fake/refuse", json={"reason": None})
    c.post("/fake/enabled", json={"on": False})
    assert order(c).json()["results"]["sim041"]["error"] == \
        "chart trading is off — switch it on on the desk page"
    assert c.post("/api/trade/order", json={"client_id": "c"}, headers=H).status_code == 400   # the desk's parser


def test_flatten_and_reverse():
    c = client()
    order(c, qty=3)
    c.post("/api/trade/reverse", json={"client_id": "r", "accounts": ["sim041"], "root": "NQ", "quotes": Q},
           headers=H)
    assert acct(c)["positions"][0]["net"] == -3
    c.post("/api/trade/flatten", json={"client_id": "f", "accounts": ["sim041"], "root": "NQ", "quotes": Q},
           headers=H)
    assert acct(c)["positions"] == []


def test_bot_scenarios():
    c = client()
    b = c.post("/fake/bot", json={"scenario": "placed", "anchor": 30900.0}).json()
    s = b["strategies"]["nq930"]
    assert (s["day_status"], s["timer"]["gate"], s["accounts"]["sim041"]["upper"]) == ("placed", True, 30910.0)
    assert {o["owner"] for o in acct(c)["orders"]} == {"nq930"}
    s = c.post("/fake/bot", json={"scenario": "done", "anchor": 30900.0}).json()["strategies"]["nq930"]
    assert s["day_status"] == "done" and s["accounts"]["sim041"]["pnl"] == 296.0
    assert [f["owner"] for f in acct(c)["fills"]][-2:] == ["nq930", "nq930"]
    assert c.post("/fake/bot", json={"scenario": "nope"}).status_code == 400


def test_the_stream_sends_state_first_then_events_then_heartbeats():
    async def run():
        d = FakeDesk()
        g = stream(d, heartbeat_s=0.01)
        first = await g.__anext__()
        assert first.startswith("event: state\n")
        d.publish("bot", {"x": 1})
        assert (await g.__anext__()).startswith("event: bot\n")
        assert (await g.__anext__()).startswith("event: heartbeat\n")
        await g.aclose()
        assert not d.subs
    asyncio.run(run())


@pytest.mark.parametrize("port", ["8850", "8852", "8854"])
def test_the_cli_refuses_the_real_services_ports(port, monkeypatch, capsys):
    """As in the chart service's own CLI guard test: stub uvicorn.run so a bind failure (8850 is the
    live desk's own port -- already taken on this machine) can never masquerade as the ap.error()
    guard. This fails if the port check is removed, and capsys checks the actual message."""
    def unreachable(*a, **k):
        pytest.fail("uvicorn.run must not be reached: the port guard should have refused first")
    monkeypatch.setattr(fake_desk.uvicorn, "run", unreachable)
    with pytest.raises(SystemExit):
        fake_desk.main(["--port", port])
    err = capsys.readouterr().err
    assert f"port {port} belongs to the real desk or the chart service" in err
