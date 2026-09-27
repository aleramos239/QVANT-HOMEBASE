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
    # a distinct client_id per call: a real client never reuses one across separate orders, and the desk
    # (fake and real alike) now treats a repeated (action, client_id) as a retry of the FIRST one (review item 6)
    c = client()
    assert order(c, cid="r1", qty=11).json()["results"]["sim041"]["error"] == "quantity must be 1-10"
    r = order(c, cid="r2", type="Stop", price=30890.0).json()["results"]["sim041"]
    assert r == {"ok": False, "order_id": None, "error": "a buy stop must be above the last price (30,900.25)",
                 "refused": True}
    c.post("/fake/refuse", json={"reason": "NQZ6 on SIM0000041 is locked 09:20-09:35 ET for the nq930 bot"})
    assert "locked" in order(c, cid="r3").json()["results"]["sim041"]["error"]
    c.post("/fake/refuse", json={"reason": None})
    c.post("/fake/enabled", json={"on": False})
    assert order(c, cid="r4").json()["results"]["sim041"]["error"] == \
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


def test_fills_are_stamped_from_the_quotes_ts_ms_not_wall_clock_time():
    """2026-09-27 review of Tasks 5-6: a fill used to be stamped with real wall-clock time even under
    --replay, landing outside every loaded bar's range on a replay chart. A Market order's quote already
    carries `ts_ms`; the fill now uses it."""
    c = client()
    order(c, qty=1).json()
    assert acct(c)["fills"][-1]["time"] == "1970-01-01T00:00:00.001Z"   # Q's ts_ms is 1
    # /fake/fill (no quotes context) takes an optional explicit ts_ms the same way
    oid = order(c, cid="c2", type="Limit", price=30880.0).json()["results"]["sim041"]["order_id"]
    c.post("/fake/fill", json={"account": "sim041", "order_id": oid, "ts_ms": 2000})
    assert acct(c)["fills"][-1]["time"] == "1970-01-01T00:00:02.000Z"
    # no ts_ms at all: falls back to real wall-clock time (still an ISO string, just not epoch-0-ish)
    oid = order(c, cid="c3", type="Limit", price=30880.0, quotes={}).json()["results"]["sim041"]["order_id"]
    c.post("/fake/fill", json={"account": "sim041", "order_id": oid})
    assert acct(c)["fills"][-1]["time"].startswith("20")   # a real year, not 1970


def test_a_retried_client_id_is_idempotent_not_a_second_order():
    """2026-09-27 review (item 6): the real desk de-duplicates on (action, client_id); the fake one did not,
    so a retried send (or any client bug that re-sent the same body) quietly placed a second order."""
    c = client()
    first = order(c, cid="dup1", qty=2).json()
    again = order(c, cid="dup1", qty=2).json()
    assert again == first
    assert len(acct(c)["fills"]) == 1
    assert acct(c)["positions"][0]["net"] == 2   # not 4: the retry never re-executed
    # the same guard applies to modify/cancel/flatten/reverse (all keyed by (action, client_id))
    oid = order(c, cid="dup2", type="Limit", price=30880.0).json()["results"]["sim041"]["order_id"]
    m1 = c.post("/api/trade/modify", json={"client_id": "modid", "account": "sim041", "order_id": oid,
                                            "price": 30870.0}, headers=H).json()
    m2 = c.post("/api/trade/modify", json={"client_id": "modid", "account": "sim041", "order_id": oid,
                                            "price": 30860.0}, headers=H).json()
    assert m1 == m2
    assert acct(c)["orders"][0]["price"] == 30870.0   # the second modify's price never applied


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


# --- Stop Limit + time-in-force ---------------------------------------------------------------
def quote_tick(c, last, root="NQ"):
    return c.post("/fake/quote", json={"root": root, "last": last})


def test_a_stop_limit_rests_with_its_limit_trigger_and_tif():
    c = client()
    r = order(c, type="StopLimit", price=30905.13, trigger_price=30902.0, tif="GTC").json()
    assert r["results"]["sim041"]["ok"] is True
    (o,) = acct(c)["orders"]
    assert (o["type"], o["price"], o["stop_price"], o["trigger"], o["tif"]) == \
        ("StopLimit", 30905.25, 30902.0, 30902.0, "GTC")
    lim = order(c, cid="c2", type="Limit", price=30880.0).json()["results"]["sim041"]["order_id"]
    assert next(o for o in acct(c)["orders"] if o["order_id"] == lim)["tif"] == "Day"   # the default


def test_a_stop_limit_is_refused_with_the_desks_sentences():
    c = client()
    r = order(c, type="StopLimit", price=30900.0, trigger_price=30900.0).json()["results"]["sim041"]
    assert r["error"] == "a buy stop limit's trigger must be above the last price (30,900.25)"
    r = order(c, cid="c2", type="StopLimit", price=30901.0, trigger_price=30902.0).json()["results"]["sim041"]
    assert r["error"] == "a buy stop limit's limit must be at or above its trigger"
    r = order(c, cid="c3", type="StopLimit", price=30905.0, trigger_price=30902.0, quotes={}).json()
    assert "a stop limit order needs a fresh price" in r["results"]["sim041"]["error"]
    assert acct(c)["orders"] == []


def test_a_stop_limit_fills_at_its_limit_once_triggered_and_marketable():
    c = client()
    order(c, type="StopLimit", price=30905.0, trigger_price=30902.0, sl_price=30895.0, tp_price=30920.0)
    quote_tick(c, 30901.0)                                     # below the trigger: nothing
    assert acct(c)["orders"][0]["type"] == "StopLimit" and acct(c)["positions"] == []
    quote_tick(c, 30907.0)                                     # triggered, but past the limit: rests
    assert acct(c)["orders"][0]["type"] == "StopLimit" and acct(c)["positions"] == []
    quote_tick(c, 30904.0)                                     # back inside the limit: fills AT the limit
    a = acct(c)
    assert a["positions"][0]["net"] == 1 and a["positions"][0]["avg_price"] == 30905.0
    assert sorted(o["type"] for o in a["orders"]) == ["Limit", "Stop"]     # its bracket rests
    assert {o["tif"] for o in a["orders"]} == {"GTC"}


def test_a_sell_stop_limit_triggers_and_fills_in_one_quote_and_can_be_filled_by_hand():
    c = client()
    order(c, side="Sell", type="StopLimit", price=30895.0, trigger_price=30898.0)
    quote_tick(c, 30897.0)                                     # through the trigger, above the limit
    assert acct(c)["positions"][0]["net"] == -1 and acct(c)["fills"][-1]["price"] == 30895.0
    oid = order(c, cid="c2", side="Sell", type="StopLimit", price=30890.0,
                trigger_price=30892.0).json()["results"]["sim041"]["order_id"]
    c.post("/fake/fill", json={"account": "sim041", "order_id": oid})
    assert acct(c)["fills"][-1]["price"] == 30890.0             # by hand: the limit too


def test_a_stop_limit_cannot_be_moved():
    c = client()
    oid = order(c, type="StopLimit", price=30905.0, trigger_price=30902.0).json()["results"]["sim041"]["order_id"]
    r = c.post("/api/trade/modify", json={"client_id": "m", "account": "sim041", "order_id": oid,
                                           "price": 30906.0}, headers=H).json()["results"]["sim041"]
    assert r["error"] == "Stop Limit orders can't be moved — cancel and place again"


def test_session_end_drops_day_orders_and_keeps_gtc():
    c = client()
    order(c, qty=1, sl_price=30890.0)                           # a market fill: its SL rests GTC
    order(c, cid="c2", type="Limit", price=30880.0)             # Day
    order(c, cid="c3", type="Limit", price=30870.0, tif="GTC")  # GTC
    assert c.post("/fake/session-end").json() == {"dropped": 1}
    kept = sorted((o["type"], o["tif"], o["price"] or o["stop_price"]) for o in acct(c)["orders"])
    assert kept == [("Limit", "GTC", 30870.0), ("Stop", "GTC", 30890.0)]


# --- the bots: history + the per-strategy kill ------------------------------------------------
def test_bot_history_is_seeded_and_keyed():
    c = client()
    assert c.get("/api/trade/bot-history?strategy=nq930").status_code == 401
    body = c.get("/api/trade/bot-history?strategy=nq930", headers=H).json()
    assert (body["strategy"], body["symbol"]) == ("nq930", "NQ")
    runs = body["runs"]
    assert {r["status"] for r in runs} >= {"traded", "skipped", "no_fill", "refused"}
    traded = [r for r in runs if r["status"] == "traded"]
    assert {r["exit"]["kind"] for r in traded} >= {"tp", "sl"}
    assert all("pnl_usd" in r and r["entry"]["price"] and r["legs"] for r in traded)
    assert any(r["account"] is None for r in runs)                     # a whole-day skip
    assert all(r["date"] < fake_desk.dt.date.today().isoformat() for r in runs)
    few = c.get("/api/trade/bot-history?strategy=nq930&days=3", headers=H).json()["runs"]
    assert len(few) < len(runs)
    assert c.get("/api/trade/bot-history?strategy=nope", headers=H).status_code == 400
    assert c.get("/api/trade/bot-history?strategy=nq930&days=0", headers=H).status_code == 400


def test_bot_kill_cancels_the_bots_orders_and_flattens_only_its_position():
    c = client()
    manual = order(c, cid="m1", type="Limit", price=30880.0).json()["results"]["sim041"]["order_id"]
    order(c, cid="m2", accounts=["sim047"], qty=2)                      # another account's position
    c.post("/fake/bot", json={"scenario": "live", "anchor": 30900.0})
    assert acct(c)["positions"][0]["net"] == 1
    r = c.post("/api/trade/bot-kill", json={"client_id": "k1", "strategy": "nq930", "quotes": Q},
               headers=H).json()
    assert r["ok"] is True and r["results"]["sim041"]["ok"] is True
    a = acct(c)
    assert a["positions"] == []                                         # the bot's contract, flat
    assert [o["order_id"] for o in a["orders"]] == [manual]             # the manual order stays
    assert acct(c, "sim047")["positions"][0]["net"] == 2               # outside the book: untouched
    s = c.get("/api/trade/state", headers=H).json()["bot"]["strategies"]["nq930"]
    assert s["killed"] is True and s["accounts"]["sim041"]["exit_reason"] == "killed"
    again = c.post("/api/trade/bot-kill", json={"client_id": "k1", "strategy": "nq930"}, headers=H).json()
    assert again == r
    assert c.post("/api/trade/bot-kill", json={"client_id": "k2", "strategy": "x"}, headers=H).status_code == 400
    assert c.post("/api/trade/bot-kill", json={"client_id": "k3", "strategy": "nq930"}).status_code == 401


def test_bot_kill_before_the_fire_just_marks_it_killed():
    c = client()
    r = c.post("/api/trade/bot-kill", json={"client_id": "k", "strategy": "nq930"}, headers=H).json()
    assert r["ok"] is True and "actions" not in r["results"]["sim041"]
    assert c.get("/api/trade/state", headers=H).json()["bot"]["strategies"]["nq930"]["killed"] is True
    assert acct(c)["orders"] == [] and acct(c)["positions"] == []


def test_exits_add_a_tp_to_a_positions_stop_as_one_oco_pair():
    c = client()
    assert order(c, qty=2, sl_price=30890.0).json()["results"]["sim041"]["ok"]
    body = {"client_id": "e1", "accounts": ["sim041"], "root": "NQ", "tp_price": 30920.0, "quotes": Q}
    assert c.post("/api/trade/exits", json=body, headers=H).json()["results"]["sim041"]["ok"] is True
    a = acct(c)
    assert sorted((o["type"], o["qty"], o["price"] or o["stop_price"], o["tif"]) for o in a["orders"]) == \
        [("Limit", 2, 30920.0, "GTC"), ("Stop", 2, 30890.0, "GTC")]
    stop = next(o for o in a["orders"] if o["type"] == "Stop")
    c.post("/fake/fill", json={"account": "sim041", "order_id": stop["order_id"]})
    assert acct(c)["orders"] == []                              # the target went with it
    body = {**body, "client_id": "e2", "sl_price": 30950.0, "tp_price": None}
    r = c.post("/api/trade/exits", json=body, headers=H).json()["results"]["sim041"]
    assert r["refused"] and "no NQZ6 position" in r["error"]
