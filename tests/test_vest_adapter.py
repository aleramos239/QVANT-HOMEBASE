"""Vest adapter core: bodies, sizing, modify, flatten, fills. No network: a real VestSession runs over an httpx
MockTransport (the fake gateway), with the credentials store pointed at tmp_path."""
from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import httpx
import pytest

from homebase.broker import vest
from homebase.broker.base import OrderRequest
from homebase.broker.vest import VestAdapter, parse_account_state, poll_fills, units_of
from homebase.broker.vest_auth import DeviceKey, VestSession
from homebase.store import secrets_store

KEY = "vest:0xabc0000000000000000000000000000000000001"
ACC = "acc-1"
FAR = 4_000_000_000_000
SYM = "NDX-USD-PERP"
OPEN, CLOSE, CANCEL = "/v3/positions/open", "/v3/positions/close", "/v3/positions/cancel-order"
REDUCE = "/v3/positions/reduce"


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets_store, "_store_path", lambda: tmp_path / "credentials.json")
    secrets_store.set_credentials(KEY, primary_addr="0xabc", refresh_token="RT", refresh_token_id="RTID",
                                  refresh_expires_ms=FAR, device_pem=DeviceKey.new().pem())


class Gateway:
    """Fake Vest gateway. `h[(METHOD, path)]` = callable(req) -> Response | None (None: the default answer)."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.h: dict = {}
        self.mark = "21030"
        self.positions: list = []
        self.orders: list = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        p = req.url.path
        if (req.method, p) in self.h:
            r = self.h[(req.method, p)](req)
            if r is not None:
                return r
        if p == "/v3/auth/account-token":
            return httpx.Response(200, json={"accessToken": "ACCT-1", "accessExpiresAtMs": FAR})
        if p == "/v3/exchangeInfo":
            return httpx.Response(200, json={"symbols": [
                {"symbol": "ES-USD-PERP", "tickSizes": ["0.5"], "sizeDecimals": 2, "priceDecimals": 1},
                {"symbol": SYM, "tickSizes": ["0.25"], "sizeDecimals": 4, "priceDecimals": 2, "capitalInitMarginRatio": "0.02"}]})
        if p == "/v3/ticker/latest":
            return httpx.Response(200, json={"tickers": [{"symbol": SYM, "markPrice": self.mark}]})
        if p == "/v3/positions/opened":
            return httpx.Response(200, json={"positions": self.positions})
        if p == "/v3/positions/opened-orders":
            return httpx.Response(200, json={"orders": self.orders})
        if p == "/v3/accounts":
            return httpx.Response(200, json=[{"account_id": ACC, "account_type": 1, "amount": "1234.5", "active": True}])
        if p == "/v3/capital/accounts":
            return httpx.Response(200, json={"accounts": [], "limits": {}})
        if p in (OPEN, CLOSE, REDUCE):
            b = json.loads(req.content)
            if p == OPEN:
                self.orders.append({"order_id": "o1", "account_id": ACC, "position_id": "p1", "symbol": SYM,
                                    "side": "buy" if b["side"] == "long" else "sell", "quantity": b["quantity"]})
            elif p == CLOSE:
                self.positions = [x for x in self.positions if x["positionId"] != b["positionId"]]
            else:
                for x in self.positions:
                    if x["positionId"] == b["positionId"]:
                        x["quantity"] = str(Decimal(x["quantity"]) - Decimal(b["quantity"]))
        return httpx.Response(200, json={"orderId": "o1", "positionId": "p1", "commandId": "c1"})

    def api(self, method=None):
        """Order-path calls only (no auth, no reads)."""
        return [c for c in self.calls if c.url.path.startswith("/v3/positions/") and (method is None or c.method == method)
                and c.url.path not in ("/v3/positions/opened", "/v3/positions/opened-orders")]

    def writes(self):
        return [c for c in self.calls if c.method != "GET" and not c.url.path.startswith("/v3/auth/")]


def mk(gw=None, vest_account_id=ACC):
    gw = gw or Gateway()
    sess = VestSession(KEY, http=httpx.AsyncClient(transport=httpx.MockTransport(gw)))
    sess._user = ("AT", FAR)
    return VestAdapter("vest1", keyring_key=KEY, vest_account_id=vest_account_id, session=sess), gw


def body(c):
    return json.loads(c.content)


def pos(side="long", qty="20", pid="p1", **kw):
    return {"accountId": ACC, "positionId": pid, "symbol": SYM, "side": side, "quantity": qty, "openPrice": "21000",
            "takeProfits": [], "stopLosses": [], **kw}


# ---- sizing ------------------------------------------------------------------------------------------------
def test_units_of():
    assert units_of("NQZ6", 1) == "20"
    assert units_of("MNQZ6", 3) == "6"
    with pytest.raises(ValueError):
        units_of("ESZ6", 1)
    for bad in (0, -1):
        with pytest.raises(ValueError):
            units_of("NQZ6", bad)


# ---- bodies ------------------------------------------------------------------------------------------------
def test_limit_bracket_body():
    ad, gw = mk()
    r = run(ad.place_bracket(OrderRequest("NQZ6", "Buy", 1, "Limit", price=21000, stop_price=20980, tp_price=21040)))
    assert r.ok and r.order_id == "o1" and r.raw["positionId"] == "p1"
    (c,) = gw.api()
    assert (c.method, c.url.path) == ("POST", OPEN)
    assert c.headers["authorization"] == "Bearer ACCT-1"          # the account token
    assert body(c) == {
        "symbol": SYM, "side": "long", "orderType": "limit", "quantity": "20", "leverage": "50", "timeInForce": "GTC",
        "price": "21000", "takeProfits": [{"executionType": "market", "triggerPrice": "21040"}],
        "stopLosses": [{"executionType": "market", "triggerPrice": "20980"}]}


def test_market_bracket_body_from_perp_price_rounded_to_tick():
    ad, gw = mk()
    gw.mark = "21030.13"
    r = run(ad.place_bracket(OrderRequest("MNQZ6", "Sell", 2, "Market", price=21010, stop_price=21025, tp_price=20980)))
    assert r.ok
    (c,) = gw.api()
    assert body(c) == {
        "symbol": SYM, "side": "short", "orderType": "market", "quantity": "4", "leverage": "50", "timeInForce": "IOC",
        "takeProfits": [{"executionType": "market", "triggerPrice": "21000.25"}],
        "stopLosses": [{"executionType": "market", "triggerPrice": "21045"}]}


def test_sl_tp_round_toward_the_entry():
    ad, gw = mk()
    gw.mark = "21030.13"
    run(ad.place_bracket(OrderRequest("NQZ6", "Buy", 1, "Market", price=21010, stop_price=20990, tp_price=21050)))
    b = body(gw.api()[0])
    assert b["stopLosses"][0]["triggerPrice"] == "21010.25" and b["takeProfits"][0]["triggerPrice"] == "21070"   # long SL up, TP down


def test_plain_market_and_stop_entry_refused():
    ad, gw = mk()
    assert run(ad.place_order(OrderRequest("NQZ6", "Buy", 1, "Market"))).ok
    assert body(gw.api()[0])["stopLosses"] == []
    n = len(gw.calls)
    r = run(ad.place_bracket(OrderRequest("NQZ6", "Buy", 1, "Stop", stop_price=20980, trigger_price=21010)))
    assert not r.ok and len(gw.calls) == n


def test_market_bracket_without_reference_refused():
    ad, gw = mk()
    r = run(ad.place_bracket(OrderRequest("NQZ6", "Buy", 1, "Market", stop_price=20980)))
    assert not r.ok and not gw.api()


def test_probe_account_refuses_every_order():
    ad, gw = mk(vest_account_id="")
    for r in (run(ad.place_order(OrderRequest("NQZ6", "Buy", 1))), run(ad.flatten_all()), run(ad.cancel_all()),
              run(ad.cancel_order_by_id("x")), run(ad.modify_order("x", "Limit", price=1))):
        assert not r.ok and r.error == "vest: no Vest account selected"
    assert not gw.calls


# ---- modify ------------------------------------------------------------------------------------------------
def test_modify_tp_sl_is_one_put():
    ad, gw = mk()
    gw.positions = [pos(takeProfits=[{"id": "tp1", "executionType": "market", "sizeMode": "full_position", "triggerPrice": "21040"}],
                        stopLosses=[{"id": "sl1", "executionType": "market", "sizeMode": "full_position", "triggerPrice": "20980"}])]
    assert run(ad.modify_order("sl1", "Stop", stop_price=20990.1)).ok
    assert [(c.method, c.url.path) for c in gw.writes()] == [("PUT", "/v3/positions/stop-loss")]
    assert body(gw.writes()[0]) == {"positionId": "p1", "stopLossId": "sl1", "executionType": "market", "triggerPrice": "20990"}
    gw.calls.clear()
    assert run(ad.modify_order("tp1", "Limit", price=21050)).ok
    assert [(c.method, c.url.path) for c in gw.writes()] == [("PUT", "/v3/positions/take-profit")]
    assert body(gw.writes()[0])["takeProfitId"] == "tp1"


def test_exit_orders_close_or_reduce_never_open():
    ad, gw = mk()
    gw.positions = [pos("long", "20")]
    assert run(ad.place_order(OrderRequest("NQZ6", "Sell", 1, "Market"))).ok
    assert [c.url.path for c in gw.api("POST")] == [CLOSE]                       # 20 units >= 20: close, zero /open
    assert body(gw.api("POST")[0]) == {"symbol": SYM, "positionId": "p1", "orderType": "market", "leverage": "50"}
    ad, gw = mk()
    gw.positions = [pos("long", "20")]
    assert run(ad.place_order(OrderRequest("MNQZ6", "Sell", 1, "Market"))).ok     # 2 units < 20: reduce
    assert [c.url.path for c in gw.api("POST")] == [REDUCE]
    assert body(gw.api("POST")[0]) == {"positionId": "p1", "symbol": SYM, "orderType": "market", "leverage": "50",
                                       "quantity": "2", "timeInForce": "IOC", "reduceOnly": True}
    ad, gw = mk()
    gw.positions = [pos("short", "20")]
    assert run(ad.place_order(OrderRequest("NQZ6", "Buy", 2, "Limit", price=21000.1))).ok     # bigger than the position: close
    assert body(gw.api("POST")[0])["limitPrice"] == "21000" and body(gw.api("POST")[0])["orderType"] == "limit"


def test_same_side_with_position_open_refused_without_a_call():
    ad, gw = mk()
    gw.positions = [pos("long", "20")]
    r = run(ad.place_order(OrderRequest("NQZ6", "Buy", 1, "Market")))
    assert not r.ok and r.error == "vest: position already open" and not gw.api()
    r = run(ad.place_bracket(OrderRequest("NQZ6", "Sell", 1, "Market", price=21000, stop_price=21010)))   # a bracketed entry too
    assert not r.ok and not gw.api()


def test_modify_resting_entry_not_supported_and_never_cancels():
    ad, gw = mk()
    entry = run(ad.place_order(OrderRequest("NQZ6", "Buy", 1, "Limit", price=21000)))
    gw.calls.clear()
    r = run(ad.modify_order(entry.order_id, "Limit", price=21005))
    assert not r.ok and r.error == "vest: modify not supported" and not gw.calls      # known entry: no call at all
    r = run(ad.modify_order("other", "Limit", price=21005))                              # unknown id: reads only
    assert not r.ok and r.error == "vest: modify not supported" and not gw.writes()


# ---- errors / resend ---------------------------------------------------------------------------------------
def test_401_order_resent_once():
    ad, gw = mk()
    n = []

    def first_401(req):
        n.append(1)
        return httpx.Response(401) if len(n) == 1 else None
    gw.h[("POST", OPEN)] = first_401
    assert run(ad.place_order(OrderRequest("NQZ6", "Buy", 1, "Market"))).ok
    assert len(gw.api("POST")) == 2
    gw.calls.clear()
    gw.h[("POST", OPEN)] = lambda req: httpx.Response(401)
    assert not run(ad.place_order(OrderRequest("NQZ6", "Buy", 1, "Market"))).ok
    assert len(gw.api("POST")) == 2


def test_timeout_order_not_resent():
    ad, gw = mk()

    def boom(req):
        raise httpx.ReadTimeout("slow", request=req)
    gw.h[("POST", OPEN)] = boom
    r = run(ad.place_order(OrderRequest("NQZ6", "Buy", 1, "Market")))
    assert not r.ok and r.error == vest.UNCONFIRMED and len(gw.api("POST")) == 1       # never resent, never a bare reject

    def boom_but_filled(req):                       # the order reached Vest: the position is there afterwards
        gw.positions = [pos("long", "20")]
        raise httpx.ReadTimeout("slow", request=req)
    gw.positions, gw.h[("POST", OPEN)] = [], boom_but_filled
    gw.calls.clear()
    assert run(ad.place_order(OrderRequest("NQZ6", "Buy", 1, "Market"))).ok and len(gw.api("POST")) == 1


def test_error_body_code_in_result():
    ad, gw = mk()
    gw.h[("POST", OPEN)] = lambda req: httpx.Response(400, json={"code": 1152, "msg": "MIN_NOTIONAL_SIZE"})
    r = run(ad.place_order(OrderRequest("NQZ6", "Buy", 1, "Market")))
    assert not r.ok and "1152" in r.error and "MIN_NOTIONAL_SIZE" in r.error
    gw.h[("POST", OPEN)] = lambda req: httpx.Response(400, json={"detail": {"code": 3002, "msg": "margin"}})
    assert "3002" in run(ad.place_order(OrderRequest("NQZ6", "Buy", 1, "Market"))).error


def test_signed_out_is_a_result_not_a_raise():
    secrets_store.set_credentials(KEY, refresh_token="")
    ad, gw = mk()
    ad.session._user = None
    r = run(ad.place_order(OrderRequest("NQZ6", "Buy", 1, "Market")))
    assert not r.ok and r.error == "vest: sign in again"


# ---- flatten / cancel / reads ------------------------------------------------------------------------------
def test_flatten_all_closes_and_cancels():
    ad, gw = mk()
    gw.positions = [pos(), {**pos(pid="other"), "accountId": "someone-else"}]
    gw.orders = [{"order_id": "r1", "account_id": ACC, "symbol": SYM}, {"order_id": "r2", "account_id": "someone-else"}]
    r = run(ad.flatten_all())
    assert r.ok
    posts = gw.api("POST")
    assert [c.url.path for c in posts].count(CLOSE) == 1 and [c.url.path for c in posts].count(CANCEL) == 1
    assert body(next(c for c in posts if c.url.path == CLOSE)) == {
        "symbol": SYM, "positionId": "p1", "orderType": "market", "leverage": "50"}
    assert body(next(c for c in posts if c.url.path == CANCEL)) == {"orderId": "r1"}


def test_cancel_all_and_benign_already_gone():
    ad, gw = mk()
    gw.orders = [{"order_id": "r1", "account_id": ACC}]
    gw.h[("POST", CANCEL)] = lambda req: httpx.Response(400, json={"code": 3017, "msg": "ORDER_NOT_FOUND"})
    assert run(ad.cancel_all()).ok
    assert run(ad.cancel_order_by_id("zz")).ok
    gw.h[("POST", CANCEL)] = lambda req: httpx.Response(400, json={"code": 1005, "msg": "FORBIDDEN"})
    assert not run(ad.cancel_order_by_id("zz")).ok


def test_net_position_in_contracts():
    ad, gw = mk()
    gw.positions = [pos("short", "40"), {**pos("long", "100", pid="x"), "accountId": "someone-else"}]
    assert run(ad.get_net_position("NQZ6")) == -2
    assert run(ad.get_net_position("MNQZ6")) == -20
    gw.positions = []
    assert run(ad.get_net_position("NQ")) == 0


def test_balance_and_accounts():
    ad, gw = mk()
    assert run(ad.get_balance())["balance"] == 1234.5
    assert run(ad.list_accounts()) == [{"name": "Vest primary", "id": ACC, "kind": "primary", "demo": False}]


def test_capital_accounts_kind_never_guessed():
    ad, gw = mk()
    gw.h[("GET", "/v3/capital/accounts")] = lambda req: httpx.Response(200, json={"accounts": [
        {"account_id": "c1", "stage": "Evaluation"}, {"account_id": "c2", "status": "funded"}, {"account_id": "c3", "mystery": 1}]})
    kinds = {r["id"]: (r["kind"], r["demo"]) for r in run(ad.list_accounts())}
    assert kinds == {ACC: ("primary", False), "c1": ("demo", True), "c2": ("funded", False)}      # c3 skipped


# ---- fills -------------------------------------------------------------------------------------------------
def acct_msg(orders, positions=(), seq=1, acc=ACC):
    return {"channel": "account_state", "data": {"event_id": "e", "account_id": acc, "account_seq": seq,
                                                 "positions": list(positions), "orders": orders, "balances": [],
                                                 "order_intents": [], "final_balance": "0"}}


def order_row(**kw):
    return {"event_type": "ORDER_EVENT_TYPE_FILLED", "order_id": "o1", "position_id": "p1", "account_id": ACC, "symbol": SYM,
            "side": "buy", "order_type": "limit", "status": "filled", "quantity": "40", "executed_quantity": "40",
            "price": "21000", "execution_price": "20999.5", **kw}


def test_fill_event_from_account_state():
    seen: dict = {}
    opened = {"event_type": "POSITION_EVENT_TYPE_OPENED", "position_id": "p1", "account_id": ACC, "symbol": SYM,
              "side": "long", "quantity": "40"}
    (f,) = parse_account_state(acct_msg([order_row()], [opened]), account_id="vest1", vest_account_id=ACC, seen=seen)
    assert (f.account_id, f.symbol, f.side, f.qty, f.price, f.position_after) == ("vest1", "NQ", "Buy", 2, 20999.5, 2)
    assert f.raw["orderId"] == "o1"
    assert parse_account_state(acct_msg([order_row()]), account_id="vest1", vest_account_id=ACC, seen=seen) == []   # replay


def test_partial_fills_are_deltas_and_zero_price_falls_back():
    kw = dict(account_id="vest1", vest_account_id=ACC, seen={})
    a = parse_account_state(acct_msg([order_row(event_type="ORDER_EVENT_TYPE_UPDATED", status="partially_filled",
                                                executed_quantity="20", execution_price="0")]), **kw)
    b = parse_account_state(acct_msg([order_row()]), **kw)
    assert [(x.qty, x.price) for x in a] == [(1, 21000.0)] and [x.qty for x in b] == [1]


def test_other_accounts_symbols_and_roots_ignored_or_mapped():
    kw = dict(account_id="vest1", vest_account_id=ACC)
    assert parse_account_state(acct_msg([order_row()], acc="other"), seen={}, **kw) == []
    assert parse_account_state(acct_msg([order_row(symbol="ES-USD-PERP")]), seen={}, **kw) == []
    assert parse_account_state({"channel": "command_events", "data": {}}, seen={}, **kw) == []
    (f,) = parse_account_state(acct_msg([order_row(quantity="4", executed_quantity="4", side="sell")]), seen={},
                               roots={"p1": "MNQ"}, **kw)
    assert (f.symbol, f.side, f.qty) == ("MNQ", "Sell", 2)


def test_poll_fallback_fills_from_position_changes():
    kw = dict(account_id="vest1", vest_account_id=ACC)
    ev, cur = poll_fills(None, [pos(qty="20")], **kw)
    assert ev == []                                                   # first read only seeds
    ev, cur = poll_fills(cur, [pos(qty="60", openPrice="21001")], **kw)
    assert [(e.side, e.qty, e.price, e.position_after) for e in ev] == [("Buy", 2, 21001.0, 3)]
    ev, cur = poll_fills(cur, [], **kw)                               # gone: closed, price unknown
    assert [(e.side, e.qty, e.price, e.position_after) for e in ev] == [("Sell", 3, None, 0)]


def test_ws_loop_delivers_fill_and_dedupes_seq(monkeypatch):
    ad, gw = mk()
    got, urls = [], []

    class FakeWS:
        def __init__(self, msgs):
            self.msgs = msgs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def __aiter__(self):
            async def gen():
                for m in self.msgs:
                    yield json.dumps(m)
                await asyncio.sleep(3600)
            return gen()

    def fake_connect(url, **kw):
        urls.append((url, kw["subprotocols"]))
        return FakeWS([acct_msg([order_row()], seq=5), acct_msg([order_row(order_id="o2")], seq=5)])
    monkeypatch.setattr(vest.websockets, "connect", fake_connect)

    async def go():
        async def on_fill(ev):
            got.append(ev)
        await ad.observe_fills(on_fill)
        await asyncio.sleep(0.2)
        await ad.close()
    run(go())
    assert urls == [("wss://ws.hz.vestmarkets.com/ws/private", ["vest.v1", "ACCT-1"])]
    assert [g.raw["orderId"] for g in got] == ["o1"]               # the second frame reused seq 5: dropped


# ---- fix round 1: outcomes, socket health, sweep, status ---------------------------------------------------
class Sock:
    """A fake private socket: frames put on `q` are read by the adapter's socket loop."""

    def __init__(self):
        self.q: asyncio.Queue = asyncio.Queue()
        self.seq = 100

    def put(self, msg):
        self.q.put_nowait(json.dumps(msg))

    def state(self, orders, positions=()):
        self.seq += 1
        self.put(acct_msg(orders, positions, seq=self.seq))

    def patch(self, monkeypatch):
        sock = self

        class FakeWS:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            def __aiter__(self):
                async def gen():
                    while True:
                        yield await sock.q.get()
                return gen()
        monkeypatch.setattr(vest.websockets, "connect", lambda url, **kw: FakeWS())


def test_rejected_command_frame_is_ok_false_with_the_code(monkeypatch):
    ad, gw = mk()
    sock = Sock()
    sock.patch(monkeypatch)
    gw.h[("POST", OPEN)] = lambda req: sock.put(
        {"channel": "command_events", "data": {"command_id": "c1", "status": "REJECTED", "error_code": 3002,
                                              "account_id": ACC}}) or httpx.Response(
        200, json={"orderId": "o1", "positionId": "p1", "commandId": "c1"})

    async def go():
        await ad.observe_fills(lambda ev: asyncio.sleep(0))
        r = await ad.place_order(OrderRequest("NQZ6", "Buy", 1, "Market"))
        await ad.close()
        return r
    r = run(go())
    assert not r.ok and r.error == "vest 3002"


def test_cancelled_order_frame_is_ok_false_and_filled_frame_is_ok(monkeypatch):
    ad, gw = mk()
    sock = Sock()
    sock.patch(monkeypatch)
    row = {"order_id": "o1", "position_id": "p1", "account_id": ACC, "symbol": SYM}
    ans = httpx.Response(200, json={"orderId": "o1", "positionId": "p1", "commandId": "c1"})
    gw.h[("POST", OPEN)] = lambda req: sock.state([{**row, "status": "cancelled", "error_code": 3029}]) or ans

    async def go():
        got = []

        async def on_fill(ev):
            got.append(ev)
        await ad.observe_fills(on_fill)
        bad = await ad.place_order(OrderRequest("NQZ6", "Buy", 1, "Market"))
        gw.h[("POST", OPEN)] = lambda req: sock.state(
            [{**row, "order_id": "o1", "status": "filled", "side": "buy", "executed_quantity": "20", "quantity": "20",
              "execution_price": "21000"}]) or ans
        ad._events.clear()
        good = await ad.place_order(OrderRequest("NQZ6", "Buy", 1, "Market"))
        await asyncio.sleep(0.05)
        await ad.close()
        return bad, good, got
    bad, good, got = run(go())
    assert not bad.ok and bad.error == "vest 3029" and good.ok
    assert [g.qty for g in got] == [1]


def test_silence_reconciles_by_rest_both_ways(monkeypatch):
    monkeypatch.setattr(vest, "OUTCOME_S", 0.05)
    ad, gw = mk()
    Sock().patch(monkeypatch)                                  # a socket that never speaks

    async def go():
        await ad.observe_fills(lambda ev: asyncio.sleep(0))
        ok = await ad.place_order(OrderRequest("NQZ6", "Buy", 1, "Limit", price=21000))     # rests on Vest: found
        gw.h[("POST", OPEN)] = lambda req: httpx.Response(200, json={"orderId": "o9", "positionId": "p9", "commandId": "c9"})
        gw.orders.clear()
        lost = await ad.place_order(OrderRequest("NQZ6", "Buy", 1, "Limit", price=21000))   # nowhere: unconfirmed
        await ad.close()
        return ok, lost
    ok, lost = run(go())
    assert ok.ok and not lost.ok and lost.error == vest.UNCONFIRMED


def test_socket_counts_as_up_only_after_its_first_frame_and_poll_covers_until_then(monkeypatch):
    monkeypatch.setattr(vest, "POLL_S", 0.01)
    ad, gw = mk()
    sock = Sock()
    sock.patch(monkeypatch)
    gw.positions = [pos("long", "20")]
    got = []

    async def go():
        async def on_fill(ev):
            got.append(ev)
        await ad.observe_fills(on_fill)
        await asyncio.sleep(0.1)                                # connected, silent: poll seeds
        assert not ad._ws_up
        gw.positions = [pos("long", "40")]
        await asyncio.sleep(0.1)
        polled = list(got)
        sock.put({"channel": "command_events", "data": {"command_id": "x", "status": "ACCEPTED", "account_id": ACC}})
        await asyncio.sleep(0.05)
        up = ad._ws_up
        await ad.close()
        return polled, up
    polled, up = run(go())
    assert [(g.side, g.qty, g.raw["src"]) for g in polled] == [("Buy", 1, "poll")] and up


def test_flatten_closes_even_when_the_orders_read_fails():
    ad, gw = mk()
    gw.positions = [pos()]
    gw.h[("GET", "/v3/positions/opened-orders")] = lambda req: httpx.Response(429)
    r = run(ad.flatten_all())
    assert [c.url.path for c in gw.api("POST")] == [CLOSE] and r.raw["closed"] == 1 and not r.ok and "429" in r.error


def test_net_position_truncates_toward_zero():
    ad, gw = mk()
    gw.positions = [pos("long", "30")]
    assert run(ad.get_net_position("NQ")) == 1
    gw.positions = [pos("short", "30")]
    assert run(ad.get_net_position("NQ")) == -1
    gw.positions = [pos("long", "5")]
    assert run(ad.get_net_position("NQ")) == 0


def test_get_order_status_from_rest_socket_and_details():
    ad, gw = mk()
    gw.orders = [{"order_id": "r1", "account_id": ACC}]
    assert run(ad.get_order_status("r1")) == "Working"
    assert run(ad.get_order_status("nope")) is None
    ad._events["e1"] = ("Canceled", None)
    assert run(ad.get_order_status("e1")) == "Canceled"
    ad._pos_of["d1"] = "p7"
    gw.h[("GET", "/v3/positions/p7/details")] = lambda req: httpx.Response(
        200, json={"position": {"orders": [{"order_id": "d1", "status": "filled"}]}})
    assert run(ad.get_order_status("d1")) == "Filled"


def test_root_kwarg_caps_and_generic_errors(monkeypatch):
    ad = VestAdapter("v", keyring_key=KEY, vest_account_id=ACC, session=mk()[0].session, root="MNQ")
    assert ad.root == "MNQ"
    (f,) = parse_account_state(acct_msg([order_row(quantity="4", executed_quantity="4", position_id="unknown")]), seen={},
                               account_id="v", vest_account_id=ACC, default_root=ad.root)
    assert (f.symbol, f.qty) == ("MNQ", 2)
    monkeypatch.setattr(vest, "KEEP", 3)
    d = {i: i for i in range(6)}
    vest._cap(d)
    assert list(d) == [3, 4, 5]
    assert vest._err(RuntimeError("SECRET-TOKEN"))[1] == "vest: RuntimeError"
