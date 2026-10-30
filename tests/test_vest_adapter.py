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
from homebase.broker.vest import VestAdapter, details_frame, parse_account_state, poll_changes, units_of
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
    monkeypatch.setattr(vest, "state_dir", lambda: tmp_path)
    # the loss-floor guard (it refuses entries with no stop or no floors) is tested in test_vest_held.py
    monkeypatch.setattr(VestAdapter, "_floor_err", lambda self, risk, opened=None: asyncio.sleep(0))
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
        self.details: dict = {}

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
        if p.startswith("/v3/positions/") and p.endswith("/details"):
            pid = p.split("/")[3]
            side = next((x["side"] for x in self.positions if x["positionId"] == pid), "long")
            return httpx.Response(200, json={"position": {"positionId": pid, "side": side, "orders": self.details.get(pid, [])}})
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
            if p == OPEN and b["orderType"] == "market":
                self.positions.append(pos(b["side"], b["quantity"]))
            elif p == OPEN:
                self.orders.append({"order_id": "o1", "account_id": ACC, "position_id": "p1", "symbol": SYM,
                                    "side": "buy" if b["side"] == "long" else "sell", "quantity": b["quantity"],
                                    "price": b["price"]})
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


def test_plain_market_body_and_bad_stop_entry_refused():
    ad, gw = mk()
    # the body of a market entry with no legs; in production the guard refuses it (no stop, R34), stubbed here
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
    gw.positions.clear()
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


def test_poll_changes_seeds_then_names_the_changed_positions():
    kw = dict(vest_account_id=ACC)
    ch, cur = poll_changes(None, [pos(qty="20")], **kw)
    assert ch == [] and cur == {"p1": Decimal(20)}                    # first read only seeds
    ch, cur = poll_changes(cur, [pos(qty="20")], **kw)
    assert ch == []
    ch, cur = poll_changes(cur, [pos(qty="60"), pos(pid="p2", qty="5")], **kw)
    assert ch == ["p1", "p2"]
    ch, cur = poll_changes(cur, [pos(qty="60")], **kw)                # p2 gone
    assert ch == ["p2"] and cur == {"p1": Decimal(60)}


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
    x0 = {"order_id": "x0", "status": "filled", "quantity": "20", "executed_quantity": "20", "execution_price": "21000",
          "position_order_type": "open"}
    gw.details["p1"] = [x0]
    got = []

    async def go():
        async def on_fill(ev):
            got.append(ev)
        await ad.observe_fills(on_fill)
        await asyncio.sleep(0.1)                                # connected, silent: poll seeds (x0 is not a fill)
        assert not ad._ws_up
        gw.positions = [pos("long", "40")]
        gw.details["p1"] = [x0, {**x0, "order_id": "x1", "position_order_type": "append", "execution_price": "21001"}]
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


def test_net_position_rounds_away_from_zero():
    ad, gw = mk()
    for side, qty, want in (("long", "7", 1), ("long", "30", 2), ("short", "30", -2), ("long", "5", 1), ("long", "40", 2)):
        gw.positions = [pos(side, qty)]
        assert run(ad.get_net_position("NQ")) == want, (side, qty)


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


# ---- fix round 2: never report flat (or ok) while a position may still be open -----------------------------------
def test_sweep_cancels_first_then_closes_and_rereads():
    ad, gw = mk()
    gw.positions = [pos()]
    gw.orders = [{"order_id": "r1", "account_id": ACC, "symbol": SYM}]
    r = run(ad.flatten_all())
    assert r.ok and r.raw == {"cancelled": 1, "closed": 1}
    assert [c.url.path for c in gw.api("POST")] == [CANCEL, CLOSE]
    opened = [i for i, c in enumerate(gw.calls) if c.url.path == "/v3/positions/opened"]
    assert gw.calls[-1].url.path == "/v3/positions/opened" and len(opened) >= 2       # read, close (+ its own check), re-read


def test_sweep_position_still_open_is_not_ok_and_closes_twice():
    ad, gw = mk()
    gw.positions = [pos()]
    gw.h[("POST", CLOSE)] = lambda req: httpx.Response(200, json={"orderId": "o1", "positionId": "p1", "commandId": "c1"})
    r = run(ad.flatten_all())
    assert not r.ok and "position still open" in r.error
    assert [c.url.path for c in gw.api("POST")].count(CLOSE) == 2                      # one more try, then the truth


def test_close_already_requested_is_not_gone():
    ad, gw = mk()
    gw.positions = [pos()]
    gw.h[("POST", CLOSE)] = lambda req: httpx.Response(400, json={"code": 10029, "msg": "CLOSE_ALREADY_REQUESTED"})
    r = run(ad.flatten_all())
    assert not r.ok and "position still open" in r.error

    def no_position(req):                                                              # 10009: truly gone
        gw.positions = []
        return httpx.Response(400, json={"code": 10009, "msg": "NO_POSITION"})
    ad, gw = mk()
    gw.positions = [pos()]
    gw.h[("POST", CLOSE)] = no_position
    assert run(ad.flatten_all()).ok


def test_sweep_reread_failing_is_not_ok():
    ad, gw = mk()
    gw.positions = [pos()]
    calls = []

    def second_read_fails(req):
        calls.append(1)
        return httpx.Response(500) if len(calls) >= 2 else None
    gw.h[("GET", "/v3/positions/opened")] = second_read_fails
    r = run(ad.flatten_all())
    assert not r.ok and len(gw.api("POST")) == 1 and r.raw["closed"] == 0               # the re-read said nothing: unknown


def _frames(sock, *states):
    row = {"order_id": "o1", "position_id": "p1", "account_id": ACC, "symbol": SYM, "side": "sell"}
    for delay, extra in states:
        asyncio.get_event_loop().call_later(delay, sock.state, [{**row, **extra}])


def test_market_close_accepted_then_cancelled_is_not_ok(monkeypatch):
    ad, gw = mk()
    sock = Sock()
    sock.patch(monkeypatch)
    gw.positions = [pos("long", "20")]
    ans = httpx.Response(200, json={"orderId": "o1", "positionId": "p1", "commandId": "c1"})
    gw.h[("POST", CLOSE)] = lambda req: ans

    async def go():
        await ad.observe_fills(lambda ev: asyncio.sleep(0))
        _frames(sock, (0, {"status": "accepted"}), (0.15, {"status": "cancelled", "error_code": 3029}))
        r = await ad.place_order(OrderRequest("NQZ6", "Sell", 1, "Market"))
        await ad.close()
        return r
    r = run(go())
    assert not r.ok and r.error == "vest 3029"


def test_market_close_accepted_then_filled_is_ok(monkeypatch):
    ad, gw = mk()
    sock = Sock()
    sock.patch(monkeypatch)
    gw.positions = [pos("long", "20")]
    gw.h[("POST", CLOSE)] = lambda req: httpx.Response(200, json={"orderId": "o1", "positionId": "p1", "commandId": "c1"})

    async def go():
        await ad.observe_fills(lambda ev: asyncio.sleep(0))
        _frames(sock, (0, {"status": "accepted"}),
                (0.15, {"status": "filled", "executed_quantity": "20", "quantity": "20", "execution_price": "21000"}))
        r = await ad.place_order(OrderRequest("NQZ6", "Sell", 1, "Market"))
        await ad.close()
        return r
    assert run(go()).ok


def test_market_close_partially_filled_then_silence_with_position_open_is_not_ok(monkeypatch):
    monkeypatch.setattr(vest, "OUTCOME_S", 0.1)
    ad, gw = mk()
    sock = Sock()
    sock.patch(monkeypatch)
    gw.positions = [pos("long", "20")]
    gw.h[("POST", CLOSE)] = lambda req: httpx.Response(200, json={"orderId": "o1", "positionId": "p1", "commandId": "c1"})

    async def go():
        await ad.observe_fills(lambda ev: asyncio.sleep(0))
        _frames(sock, (0, {"status": "partially_filled", "executed_quantity": "5", "quantity": "20"}))
        r = await ad.place_order(OrderRequest("NQZ6", "Sell", 1, "Market"))
        await ad.close()
        return r
    r = run(go())
    assert not r.ok and r.error == vest.UNCONFIRMED


def test_lost_market_exit_is_decided_by_the_position_not_a_resting_tp():
    def lost(req):
        raise httpx.ReadTimeout("slow", request=req)
    ad, gw = mk()
    gw.positions = [pos("long", "20")]
    gw.orders = [{"order_id": "tp1", "account_id": ACC, "position_id": "p1", "symbol": SYM, "side": "sell", "quantity": "20"}]
    gw.h[("POST", CLOSE)] = lost
    r = run(ad.place_order(OrderRequest("NQZ6", "Sell", 1, "Market")))
    assert not r.ok and r.error == vest.UNCONFIRMED                                    # the position is still there
    ad, gw = mk()
    gw.positions = [pos("long", "20")]

    def lost_but_closed(req):
        gw.positions = []
        raise httpx.ReadTimeout("slow", request=req)
    gw.h[("POST", CLOSE)] = lost_but_closed
    assert run(ad.place_order(OrderRequest("NQZ6", "Sell", 1, "Market"))).ok
    ad, gw = mk()
    gw.positions = [pos("long", "20")]
    gw.h[("POST", REDUCE)] = lost                                                      # a reduce: smaller position = done
    assert not run(ad.place_order(OrderRequest("MNQZ6", "Sell", 1, "Market"))).ok

    def lost_but_reduced(req):
        gw.positions = [pos("long", "18")]
        raise httpx.ReadTimeout("slow", request=req)
    gw.h[("POST", REDUCE)] = lost_but_reduced
    assert run(ad.place_order(OrderRequest("MNQZ6", "Sell", 1, "Market"))).ok


def test_lost_open_matches_by_position_for_market_and_by_side_qty_price_for_limit():
    def lost(req):
        raise httpx.ReadTimeout("slow", request=req)
    ad, gw = mk()
    gw.orders = [{"order_id": "z", "account_id": ACC, "symbol": SYM, "side": "buy", "quantity": "20"}]
    gw.h[("POST", OPEN)] = lost
    assert not run(ad.place_order(OrderRequest("NQZ6", "Buy", 1, "Market"))).ok        # a resting order is no market fill
    for price, ok in (("20000", False), ("21000", True)):
        ad, gw = mk()
        gw.orders = [{"order_id": "z", "account_id": ACC, "symbol": SYM, "side": "buy", "quantity": "20", "price": price}]
        gw.h[("POST", OPEN)] = lost
        assert run(ad.place_order(OrderRequest("NQZ6", "Buy", 1, "Limit", price=21000))).ok is ok


def test_flatten_tagged_order_with_no_position_never_opens():
    ad, gw = mk()
    r = run(ad.place_order(OrderRequest("NQZ6", "Sell", 1, "Market", text="homebase:flat NQ")))
    assert r.ok and not gw.api("POST")
    assert run(ad.place_order(OrderRequest("NQZ6", "Sell", 1, "Market"))).ok and [c.url.path for c in gw.api("POST")] == [OPEN]


def test_every_exit_tag_refuses_to_open_but_chart_reverse_opens():
    for tag in vest.EXIT_TAGS:
        ad, gw = mk()
        r = run(ad.place_order(OrderRequest("NQZ6", "Sell", 1, "Market", text=tag)))
        assert r.ok and r.raw == {"note": "nothing to close"} and not gw.api("POST"), tag
    ad, gw = mk()
    assert run(ad.place_order(OrderRequest("NQZ6", "Sell", 1, "Market", text="homebase:chart-reverse"))).ok
    assert [c.url.path for c in gw.api("POST")] == [OPEN]


def test_non_dict_200_body_is_reconciled_not_rejected():
    ad, gw = mk()

    def odd(req):
        gw.positions = [pos("long", "20")]
        return httpx.Response(200, json=["not", "a", "dict"])
    gw.h[("POST", OPEN)] = odd
    assert run(ad.place_order(OrderRequest("NQZ6", "Buy", 1, "Market"))).ok


def _poll_frame(oid, units, pid="p1", side="long", **kw):
    row = {"order_id": oid, "status": "filled", "quantity": "20", "executed_quantity": units, "execution_price": "21000",
           "position_order_type": "open", **kw}
    return details_frame(pid, {"position": {"side": side, "orders": [row]}}, vest_account_id=ACC)


def test_poll_then_socket_reports_each_order_once():
    kw = dict(account_id="vest1", vest_account_id=ACC)
    seen = {}
    (poll,) = parse_account_state(_poll_frame("X", "20"), seen=seen, **kw)
    assert (poll.side, poll.qty) == ("Buy", 1)
    assert parse_account_state(acct_msg([order_row(order_id="X", quantity="20", executed_quantity="20")]),
                               seen=seen, **kw) == []                                   # the socket's twin of the poll fill
    seen = {}
    (a,) = parse_account_state(_poll_frame("X", "10"), seen=seen, **kw)                 # poll saw 10 of the 20
    rest = parse_account_state(acct_msg([order_row(order_id="X", quantity="20", executed_quantity="20")]), seen=seen, **kw)
    assert a.qty + sum(r.qty for r in rest) == 1                                        # a 1-lot never reads 2
    assert a.raw["units"] == "10"


def test_poll_fill_of_one_order_does_not_offset_a_socket_fill_of_another():
    kw = dict(account_id="vest1", vest_account_id=ACC)
    seen = {}
    assert len(parse_account_state(_poll_frame("X", "20"), seen=seen, **kw)) == 1
    (y,) = parse_account_state(acct_msg([order_row(order_id="Y", quantity="20", executed_quantity="20")]), seen=seen, **kw)
    assert y.qty == 1 and y.raw["orderId"] == "Y"


def test_details_frame_gives_closing_orders_the_other_side():
    f = _poll_frame("C", "20", side="long", position_order_type="close")
    (o,) = f["data"]["orders"]
    assert o["side"] == "sell" and o["symbol"] == SYM and o["position_id"] == "p1"
    assert _poll_frame("S", "20", side="short")["data"]["orders"][0]["side"] == "sell"
    assert _poll_frame("T", "20", side="short", order_type="take_profit")["data"]["orders"][0]["side"] == "buy"


def test_poll_details_failure_reports_nothing_and_the_next_read_retries(monkeypatch):
    monkeypatch.setattr(vest, "POLL_S", 0.01)
    ad, gw = mk()
    Sock().patch(monkeypatch)
    gw.positions = [pos("long", "20")]
    x0 = {"order_id": "x0", "status": "filled", "quantity": "20", "executed_quantity": "20", "execution_price": "21000",
          "position_order_type": "open"}
    gw.details["p1"] = [x0]
    state, got = {"fail": False, "tries": 0}, []

    def details(req):
        if state["fail"]:
            state["tries"] += 1
            return httpx.Response(500) if state["tries"] <= 2 else None
    gw.h[("GET", "/v3/positions/p1/details")] = details

    async def go():
        async def on_fill(ev):
            got.append(ev)
        await ad.observe_fills(on_fill)
        await asyncio.sleep(0.1)                                # seeded
        state["fail"] = True
        gw.positions = [pos("long", "40")]
        gw.details["p1"] = [x0, {**x0, "order_id": "x1", "position_order_type": "append"}]
        await asyncio.sleep(0.4)
        await ad.close()
    run(go())
    assert state["tries"] >= 3 and [(g.qty, g.raw["orderId"]) for g in got] == [(1, "x1")]    # nothing guessed, then once


def test_poll_does_not_emit_when_the_socket_spoke_during_its_read(monkeypatch):
    monkeypatch.setattr(vest, "POLL_S", 0.01)
    ad, gw = mk()
    Sock().patch(monkeypatch)
    gw.positions = [pos("long", "20")]
    reads, got = [], []

    def read(req):
        reads.append(1)
        if len(reads) == 2:                      # the socket speaks while the poll is reading
            ad._ws_up = True
            gw.positions = [pos("long", "40")]

    gw.h[("GET", "/v3/positions/opened")] = read

    async def go():
        async def on_fill(ev):
            got.append(ev)
        await ad.observe_fills(on_fill)
        await asyncio.sleep(0.2)
        await ad.close()
    run(go())
    assert len(reads) >= 2 and got == []


# ---- fix round 4: R24 unclassifiable rows, R25 closed position with failing /details, R26 chart-exit ---------
def test_details_frame_skips_a_row_it_cannot_classify():
    f = _poll_frame("U", "20", position_order_type=None, order_type="limit")
    assert f["data"]["orders"] == [] and [o["order_id"] for o in f["skipped"]] == ["U"]
    assert _poll_frame("E", "20", position_order_type="POSITION_ORDER_TYPE_CLOSE")["data"]["orders"][0]["side"] == "sell"
    sided = details_frame("p1", {"position": {"side": "long", "orders": [{"order_id": "B", "side": "sell",
                                                                          "executed_quantity": "20"}]}}, vest_account_id=ACC)
    assert sided["skipped"] == [] and sided["data"]["orders"][0]["side"] == "sell"     # the row's own side: classified


def _poll_run(monkeypatch, ad, middle, wait=0.4, after=None):
    """Seed the poll on gw's state, run `middle()` (the change), give the poll `wait` s, then `after(sock)` (a socket
    frame) and 0.1 s more; -> the fills reported."""
    monkeypatch.setattr(vest, "POLL_S", 0.01)
    sock = Sock()
    sock.patch(monkeypatch)
    got = []

    async def go():
        async def on_fill(ev):
            got.append(ev)
        await ad.observe_fills(on_fill)
        await asyncio.sleep(0.1)                                # seeded
        middle()
        await asyncio.sleep(wait)
        if after:
            after(sock)
            await asyncio.sleep(0.1)
        await ad.close()
    run(go())
    return got


X0 = {"order_id": "x0", "status": "filled", "quantity": "20", "executed_quantity": "20", "execution_price": "21000",
      "position_order_type": "open"}


def test_poll_unclassifiable_row_is_not_reported_not_seen_and_retried(monkeypatch, caplog):
    ad, gw = mk()
    gw.positions, gw.details["p1"] = [pos("long", "20")], [X0]
    reads = []
    gw.h[("GET", "/v3/positions/p1/details")] = lambda req: reads.append(1)

    def change():
        reads.clear()
        gw.positions = [pos("long", "40")]
        gw.details["p1"] = [X0, {**X0, "order_id": "u1", "position_order_type": None, "order_type": "limit"}]
    with caplog.at_level("WARNING"):
        got = _poll_run(monkeypatch, ad, change)
    assert got == [] and "u1" not in ad._seen
    assert len(reads) >= 3                                       # the next reads try again (retry set)
    assert sum("u1" in r.getMessage() for r in caplog.records) == 1


def test_poll_closed_position_with_failing_details_reports_one_exit_from_the_size(monkeypatch):
    ad, gw = mk()
    gw.positions, gw.details["p1"] = [pos("long", "20")], [X0]
    fails = []

    def details(req):
        if not gw.positions:
            fails.append(1)
            return httpx.Response(404, json={"code": 10009, "msg": "no position"})
    gw.h[("GET", "/v3/positions/p1/details")] = details

    def close():
        gw.positions = []
    got = _poll_run(monkeypatch, ad, close)
    assert len(fails) == 3                                       # then dropped: no more /details for p1
    (ev,) = got
    assert (ev.side, ev.qty, ev.price, ev.position_after, ev.symbol) == ("Sell", 1, None, 0, "NQ")
    assert ev.raw["positionId"] == "p1" and ev.raw["src"] == "poll"
    assert ev.raw["orderId"] == "size:p1"                         # never orderless: the engine cannot take it as an entry


def test_size_fallback_then_the_socket_replaying_the_close_reports_once(monkeypatch):
    ad, gw = mk()
    gw.positions, gw.details["p1"] = [pos("long", "20")], [X0]

    def details(req):
        if not gw.positions:
            return httpx.Response(404, json={"code": 10009, "msg": "no position"})
    gw.h[("GET", "/v3/positions/p1/details")] = details

    def close():
        gw.positions = []

    def replay(sock):
        sock.state([order_row(order_id="c1", position_id="p1", side="sell", quantity="20", executed_quantity="20")])
    got = _poll_run(monkeypatch, ad, close, after=replay)
    assert [g.raw["orderId"] for g in got] == ["size:p1"]


def test_closed_position_stuck_on_unclassifiable_rows_falls_back_once(monkeypatch):
    ad, gw = mk()
    gw.positions, gw.details["p1"] = [pos("long", "20")], [X0]
    reads = []
    gw.h[("GET", "/v3/positions/p1/details")] = lambda req: reads.append(1) if not gw.positions else None

    def close():
        gw.positions = []
        gw.details["p1"] = [{**X0, "order_id": "u1", "position_order_type": None, "order_type": "limit"}]
    got = _poll_run(monkeypatch, ad, close)
    assert len(reads) == 3                                       # then dropped: no more /details for p1
    assert [(g.side, g.qty, g.raw["orderId"]) for g in got] == [("Sell", 1, "size:p1")]


def test_closed_position_reported_by_its_closing_row_never_falls_back(monkeypatch):
    ad, gw = mk()
    gw.positions, gw.details["p1"] = [pos("long", "20")], [X0]
    reads = []
    gw.h[("GET", "/v3/positions/p1/details")] = lambda req: reads.append(1) if not gw.positions else None

    def close():
        gw.positions = []
        gw.details["p1"] = [{**X0, "order_id": "c1", "position_order_type": "close"},
                            {**X0, "order_id": "u1", "position_order_type": None, "order_type": "limit"}]
    got = _poll_run(monkeypatch, ad, close)
    assert len(reads) == 3 and "p1" in ad._closed_pids
    assert [g.raw["orderId"] for g in got] == ["c1"]             # its close was reported: no size fill on top


def test_poll_closed_position_details_ok_on_the_second_read_gives_the_order_fill(monkeypatch):
    ad, gw = mk()
    gw.positions, gw.details["p1"] = [pos("long", "20")], [X0]
    fails = []

    def details(req):
        if not gw.positions and not fails:
            fails.append(1)
            return httpx.Response(404, json={"code": 10009, "msg": "no position"})
    gw.h[("GET", "/v3/positions/p1/details")] = details

    def close():
        gw.positions = []
        gw.details["p1"] = [X0, {**X0, "order_id": "c1", "position_order_type": "close"}]
    got = _poll_run(monkeypatch, ad, close)
    assert [(g.side, g.qty, g.raw["orderId"]) for g in got] == [("Sell", 1, "c1")]


def test_chart_exit_never_opens_but_still_closes_a_position():
    ad, gw = mk()
    r = run(ad.place_order(OrderRequest("NQZ6", "Sell", 1, "Limit", price=21010, text="homebase:chart-exit")))
    assert r.ok and r.raw == {"note": "nothing to close"} and not gw.api("POST")
    ad, gw = mk()
    gw.positions = [pos("long", "20")]
    assert run(ad.place_order(OrderRequest("NQZ6", "Sell", 1, "Limit", price=21010, text="homebase:chart-exit"))).ok
    assert [c.url.path for c in gw.api("POST")] == [CLOSE]


# ---- final fix (R55-R63) -----------------------------------------------------------------------------------
class Socks:
    """One fake private socket per connect: frames put on `q[n]` reach the adapter on its n-th connection; a None
    ends that connection (a drop: the socket loop reconnects)."""

    def __init__(self, n=3):
        self.q = [asyncio.Queue() for _ in range(n)]
        self.n = 0

    def put(self, i, msg):
        self.q[i].put_nowait(None if msg is None else json.dumps(msg))

    def patch(self, monkeypatch):
        socks = self

        class FakeWS:
            def __init__(self):
                self.q = socks.q[socks.n]
                socks.n += 1

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            def __aiter__(self):
                async def gen():
                    while True:
                        m = await self.q.get()
                        if m is None:
                            return
                        yield m
                return gen()
        monkeypatch.setattr(vest.websockets, "connect", lambda url, **kw: FakeWS())


def test_seq_starts_over_on_every_socket_connection(monkeypatch):
    """I1 (R55): a new connection's account_seq starts again; its fills are delivered, not dropped as stale."""
    monkeypatch.setattr(vest, "WS_RETRY_S", 0.01, raising=False)
    ad, gw = mk()
    socks = Socks()
    socks.patch(monkeypatch)
    got = []

    async def go():
        async def on_fill(ev):
            got.append(ev)
        await ad.observe_fills(on_fill)
        socks.put(0, acct_msg([order_row()], seq=50))
        socks.put(0, None)                                       # the socket drops
        socks.put(1, acct_msg([order_row(order_id="o2", position_id="p2")], seq=1))
        await asyncio.sleep(0.3)
        await ad.close()
    run(go())
    assert [g.raw["orderId"] for g in got] == ["o1", "o2"] and socks.n == 2


def test_socket_counts_as_up_only_for_a_frame_past_the_seq_check():
    ad, gw = mk()
    ad._seq = 5

    async def go():
        await ad._on_message(json.dumps(acct_msg([], seq=3)))     # stale: not proof the socket reports
        stale = ad._ws_up
        await ad._on_message(json.dumps(acct_msg([], seq=6)))
        return stale, ad._ws_up
    assert run(go()) == (False, True)


def test_a_numeric_account_id_matches_the_saved_text_id(monkeypatch):
    """I2 (R56): Vest may send account ids as numbers; the desk saves them as text. Every comparison is by text."""
    ad, gw = mk(vest_account_id="7")
    gw.positions = [pos("long", "20", accountId=7)]
    gw.h[("GET", "/v3/accounts")] = lambda req: httpx.Response(200, json=[{"account_id": 7, "account_type": 1,
                                                                           "equity": "900"}])
    assert [r["positionId"] for r in run(ad._opened())] == ["p1"]
    assert run(ad.get_balance())["balance"] == 900.0
    assert poll_changes(None, gw.positions, vest_account_id="7")[1] == {"p1": Decimal(20)}
    frame = acct_msg([order_row(account_id=7)], acc=7)
    assert len(parse_account_state(frame, account_id="vest1", vest_account_id="7", seen={})) == 1
    run(ad._on_message(json.dumps(frame)))
    assert ad._ws_up and ad._seen.get("o1") == Decimal(40)


def test_connect_refuses_an_account_not_on_this_login():
    ad, gw = mk(vest_account_id="nope")
    with pytest.raises(RuntimeError, match="vest: account nope not on this login"):
        run(ad.connect())
    assert not ad.connected
    ad, gw = mk()
    run(ad.connect())
    assert ad.connected


def _blocked_login(ad, gw):
    """Every token expired, the refresh inside its backoff and the wallet-login budget cooling down (a 429)."""
    from homebase.broker import vest_auth
    gw.h[("POST", "/v3/auth/refresh")] = lambda req: httpx.Response(200, json={
        "accessToken": "AT-2", "accessExpiresAtMs": FAR, "refreshToken": "RT-2", "refreshTokenId": "RTID-2",
        "refreshExpiresAtMs": FAR})
    ad.session._user, ad.session._accounts = None, {}
    ad.session._refresh_fails, ad.session._refresh_next_ms = 3, vest_auth._now_ms() + 60_000
    ad.session.budget.note_error(KEY, "status=429")


def test_a_flatten_during_a_login_block_still_sends_its_close():
    """I3 (R57 d): kill / flatten are never refused by a backoff or a budget block; only a 401 stops them."""
    ad, gw = mk()
    gw.positions = [pos("long", "20")]
    _blocked_login(ad, gw)
    assert run(ad.flatten_all()).ok
    assert CLOSE in [c.url.path for c in gw.api("POST")]
    ad, gw = mk()
    gw.positions = [pos("long", "20")]
    _blocked_login(ad, gw)
    assert run(ad.place_order(OrderRequest("NQZ6", "Sell", 1, "Market", text="homebase:kill"))).ok
    assert CLOSE in [c.url.path for c in gw.api("POST")]


def test_an_entry_during_the_refresh_backoff_is_refused():
    ad, gw = mk()
    _blocked_login(ad, gw)
    r = run(ad.place_order(OrderRequest("NQZ6", "Buy", 1, "Market")))
    assert not r.ok and "LoginDeferred" in r.error and not gw.api("POST")
