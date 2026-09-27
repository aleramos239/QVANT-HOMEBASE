"""The broker order bodies, pinned byte for byte. No network: the ws client's
`request` is replaced by a fake that captures (endpoint, body).

The BYTE-IDENTICAL tests below hold literal bodies captured from the code
BEFORE Stop Limit / time-in-force were added (2026-09-27, branch
feat/desk-stoplimit, from commit 375679d). Every order the 9:30 bot or the
chart sends without the new fields must still produce exactly these bytes.
Do not edit a literal to make a test pass: a difference is a behaviour change
on the live order path.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from homebase.broker.base import OrderRequest
from homebase.broker.tradovate import TradovateAdapter
from homebase.broker.tradovate_ws import TradovateWS


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def capturing_ws():
    ws = TradovateWS(token="t")
    sent: list = []

    async def fake_request(endpoint, body="", query=""):
        # the real request() sends json.dumps(body): pin that exact string
        sent.append((endpoint, body, json.dumps(body)))
        return {"orderId": 1, "oso1Id": 2, "oso2Id": 3}

    ws.request = fake_request
    return ws, sent


def mkadapter(tmp_path):
    ad = TradovateAdapter("acct", env="demo", keyring_key="k", state_dir=tmp_path)
    ws, sent = capturing_ws()
    ad._ws, ad._acct_num, ad._acct_name, ad._connected = ws, 66121477, "APEX", True
    return ad, sent


def assert_bytes(sent_one, endpoint, literal):
    ep, body, wire = sent_one
    assert ep == endpoint
    assert body == literal
    assert wire == json.dumps(literal)          # key order included: byte-identical


KW = dict(account_id=66121477, symbol="NQZ6", side="Buy", qty=3, account_spec="APEX")

# ---- literal pre-change bodies (captured from 375679d) -------------------------------------
WS_MARKET = {"accountSpec": "APEX", "accountId": 66121477, "action": "Buy", "symbol": "NQZ6",
             "orderQty": 3, "orderType": "Market", "timeInForce": "Day", "isAutomated": True,
             "text": "Onyx"}
WS_LIMIT = {"accountSpec": "APEX", "accountId": 66121477, "action": "Buy", "symbol": "NQZ6",
            "orderQty": 3, "orderType": "Limit", "timeInForce": "Day", "isAutomated": True,
            "text": "Onyx", "price": 21000.25}
WS_STOP = {"accountSpec": "APEX", "accountId": 66121477, "action": "Buy", "symbol": "NQZ6",
           "orderQty": 3, "orderType": "Stop", "timeInForce": "Day", "isAutomated": True,
           "text": "Onyx", "stopPrice": 21010.5}
WS_PROTECTIVE_STOP = {"accountId": 66121477, "action": "Sell", "symbol": "NQZ6", "orderQty": 2,
                      "orderType": "Stop", "timeInForce": "Day", "isAutomated": True,
                      "text": "homebase:chart", "stopPrice": 20990.0}
WS_OSO_BUY_STOP = {"accountSpec": "APEX", "accountId": 66121477, "action": "Buy", "symbol": "NQZ6",
                   "orderQty": 3, "orderType": "Stop", "timeInForce": "Day", "isAutomated": True,
                   "text": "Onyx", "stopPrice": 21010.5,
                   "bracket1": {"action": "Sell", "orderType": "Stop", "stopPrice": 21005.5,
                                "timeInForce": "GTC"},
                   "bracket2": {"action": "Sell", "orderType": "Limit", "price": 21025.5,
                                "timeInForce": "GTC"}}
WS_OSO_SELL_STOP = {"accountId": 66121477, "action": "Sell", "symbol": "NQZ6", "orderQty": 3,
                    "orderType": "Stop", "timeInForce": "Day", "isAutomated": True, "text": "930",
                    "stopPrice": 20990.5,
                    "bracket1": {"action": "Buy", "orderType": "Stop", "stopPrice": 20995.5,
                                 "timeInForce": "GTC"},
                    "bracket2": {"action": "Buy", "orderType": "Limit", "price": 20975.5,
                                 "timeInForce": "GTC"}}
WS_OSO_MARKET = {"accountSpec": "APEX", "accountId": 66121477, "action": "Buy", "symbol": "NQZ6",
                 "orderQty": 3, "orderType": "Market", "timeInForce": "Day", "isAutomated": True,
                 "text": "Onyx",
                 "bracket1": {"action": "Sell", "orderType": "Stop", "stopPrice": 21005.5,
                              "timeInForce": "GTC"},
                 "bracket2": {"action": "Sell", "orderType": "Limit", "price": 21025.5,
                              "timeInForce": "GTC"}}
WS_OSO_LIMIT_TP_ONLY = {"accountSpec": "APEX", "accountId": 66121477, "action": "Buy",
                        "symbol": "NQZ6", "orderQty": 3, "orderType": "Limit",
                        "timeInForce": "Day", "isAutomated": True, "text": "Onyx",
                        "price": 21000.0,
                        "bracket1": {"action": "Sell", "orderType": "Limit", "price": 21025.5,
                                     "timeInForce": "GTC"}}

AD_MARKET = {"accountSpec": "APEX", "accountId": 66121477, "action": "Buy", "symbol": "NQZ6",
             "orderQty": 1, "orderType": "Market", "timeInForce": "Day", "isAutomated": True,
             "text": "Onyx"}
AD_LIMIT = {"accountSpec": "APEX", "accountId": 66121477, "action": "Sell", "symbol": "NQZ6",
            "orderQty": 2, "orderType": "Limit", "timeInForce": "Day", "isAutomated": True,
            "text": "Onyx", "price": 21000.25}
AD_STOP_ENTRY = {"accountSpec": "APEX", "accountId": 66121477, "action": "Buy", "symbol": "NQZ6",
                 "orderQty": 1, "orderType": "Stop", "timeInForce": "Day", "isAutomated": True,
                 "text": "Onyx", "stopPrice": 21010.5}
AD_PROTECTIVE_STOP = {"accountSpec": "APEX", "accountId": 66121477, "action": "Sell",
                      "symbol": "NQZ6", "orderQty": 1, "orderType": "Stop",
                      "timeInForce": "Day", "isAutomated": True, "text": "x",
                      "stopPrice": 20990.0}
AD_OSO_BUY_STOP = {"accountSpec": "APEX", "accountId": 66121477, "action": "Buy", "symbol": "NQZ6",
                   "orderQty": 3, "orderType": "Stop", "timeInForce": "Day", "isAutomated": True,
                   "text": "930", "stopPrice": 21010.5,
                   "bracket1": {"action": "Sell", "orderType": "Stop", "stopPrice": 21005.5,
                                "timeInForce": "GTC"},
                   "bracket2": {"action": "Sell", "orderType": "Limit", "price": 21025.5,
                                "timeInForce": "GTC"}}
AD_OSO_SELL_STOP = {"accountSpec": "APEX", "accountId": 66121477, "action": "Sell",
                    "symbol": "NQZ6", "orderQty": 3, "orderType": "Stop", "timeInForce": "Day",
                    "isAutomated": True, "text": "930", "stopPrice": 20990.5,
                    "bracket1": {"action": "Buy", "orderType": "Stop", "stopPrice": 20995.5,
                                 "timeInForce": "GTC"},
                    "bracket2": {"action": "Buy", "orderType": "Limit", "price": 20975.5,
                                 "timeInForce": "GTC"}}
AD_OSO_MARKET = {"accountSpec": "APEX", "accountId": 66121477, "action": "Buy", "symbol": "NQZ6",
                 "orderQty": 1, "orderType": "Market", "timeInForce": "Day", "isAutomated": True,
                 "text": "Onyx",
                 "bracket1": {"action": "Sell", "orderType": "Stop", "stopPrice": 21005.5,
                              "timeInForce": "GTC"},
                 "bracket2": {"action": "Sell", "orderType": "Limit", "price": 21025.5,
                              "timeInForce": "GTC"}}
AD_OSO_LIMIT_SL_ONLY = {"accountSpec": "APEX", "accountId": 66121477, "action": "Buy",
                        "symbol": "NQZ6", "orderQty": 1, "orderType": "Limit",
                        "timeInForce": "Day", "isAutomated": True, "text": "Onyx",
                        "price": 21000.0,
                        "bracket1": {"action": "Sell", "orderType": "Stop", "stopPrice": 20995.0,
                                     "timeInForce": "GTC"}}


# ---- BYTE-IDENTICAL: the ws client, called without the new fields -------------------------
@pytest.mark.parametrize("kwargs,literal", [
    (dict(KW), WS_MARKET),
    (dict(KW, order_type="Limit", price=21000.25), WS_LIMIT),
    (dict(KW, order_type="Stop", price=21010.5), WS_STOP),
    (dict(account_id=66121477, symbol="NQZ6", side="Sell", qty=2, order_type="Stop",
          stop_price=20990.0, text="homebase:chart"), WS_PROTECTIVE_STOP),
], ids=["market", "limit", "stop-entry", "protective-stop"])
def test_byte_identical_ws_place_order(kwargs, literal):
    ws, sent = capturing_ws()
    run(ws.place_order(**kwargs))
    assert len(sent) == 1
    assert_bytes(sent[0], "order/placeorder", literal)


@pytest.mark.parametrize("kwargs,literal", [
    (dict(KW, stop_price=21005.5, tp_price=21025.5, entry_type="Stop", entry_price=21010.5),
     WS_OSO_BUY_STOP),
    (dict(account_id=66121477, symbol="NQZ6", side="Sell", qty=3, stop_price=20995.5,
          tp_price=20975.5, entry_type="Stop", entry_price=20990.5, text="930"), WS_OSO_SELL_STOP),
    (dict(KW, stop_price=21005.5, tp_price=21025.5), WS_OSO_MARKET),
    (dict(KW, tp_price=21025.5, entry_type="Limit", entry_price=21000.0), WS_OSO_LIMIT_TP_ONLY),
], ids=["buy-stop-entry-sl-tp", "sell-stop-entry-sl-tp", "market-sl-tp", "limit-tp-only"])
def test_byte_identical_ws_place_oso(kwargs, literal):
    ws, sent = capturing_ws()
    run(ws.place_oso(**kwargs))
    assert len(sent) == 1
    assert_bytes(sent[0], "order/placeoso", literal)


# ---- BYTE-IDENTICAL: the adapter, OrderRequest built without the new fields -----------------
@pytest.mark.parametrize("req,literal", [
    (OrderRequest("NQZ6", "Buy", 1), AD_MARKET),
    (OrderRequest("NQZ6", "Sell", 2, "Limit", 21000.25), AD_LIMIT),
    (OrderRequest("NQZ6", "Buy", 1, "Stop", 21010.5), AD_STOP_ENTRY),
    (OrderRequest("NQZ6", "Sell", 1, "Stop", None, 20990.0, text="x"), AD_PROTECTIVE_STOP),
], ids=["market", "limit", "stop-entry", "protective-stop"])
def test_byte_identical_adapter_place_order(tmp_path, req, literal):
    ad, sent = mkadapter(tmp_path)
    assert run(ad.place_order(req)).ok
    assert len(sent) == 1
    assert_bytes(sent[0], "order/placeorder", literal)


@pytest.mark.parametrize("req,literal", [
    (OrderRequest("NQZ6", "Buy", 3, "Stop", 21010.5, 21005.5, 21025.5, "930"), AD_OSO_BUY_STOP),
    (OrderRequest(symbol="NQZ6", side="Sell", qty=3, order_type="Stop", price=20990.5,
                  stop_price=20995.5, tp_price=20975.5, text="930"), AD_OSO_SELL_STOP),
    (OrderRequest("NQZ6", "Buy", 1, "Market", None, 21005.5, 21025.5), AD_OSO_MARKET),
    (OrderRequest("NQZ6", "Buy", 1, "Limit", 21000.0, 20995.0, None), AD_OSO_LIMIT_SL_ONLY),
], ids=["buy-stop-entry-sl-tp", "sell-stop-entry-sl-tp", "market-sl-tp", "limit-sl-only"])
def test_byte_identical_adapter_place_bracket(tmp_path, req, literal):
    ad, sent = mkadapter(tmp_path)
    assert run(ad.place_bracket(req)).ok
    assert len(sent) == 1
    assert_bytes(sent[0], "order/placeoso", literal)


def test_order_request_positional_fields_are_unchanged():
    r = OrderRequest("NQZ6", "Buy", 2, "Limit", 1.0, 2.0, 3.0, "t")
    assert (r.symbol, r.side, r.qty, r.order_type, r.price, r.stop_price, r.tp_price, r.text) == \
        ("NQZ6", "Buy", 2, "Limit", 1.0, 2.0, 3.0, "t")
    assert (r.trigger_price, r.time_in_force) == (None, "Day")


# ---- the new fields ----------------------------------------------------------------------
def test_ws_oso_stoplimit_entry_sends_the_limit_in_price_and_the_trigger_in_stopprice():
    ws, sent = capturing_ws()
    run(ws.place_oso(**KW, stop_price=20995.0, tp_price=21030.0, entry_type="StopLimit",
                     entry_price=21002.0, entry_trigger_price=21000.0, time_in_force="GTC"))
    assert_bytes(sent[0], "order/placeoso", {
        "accountSpec": "APEX", "accountId": 66121477, "action": "Buy", "symbol": "NQZ6",
        "orderQty": 3, "orderType": "StopLimit", "timeInForce": "GTC", "isAutomated": True,
        "text": "Onyx", "price": 21002.0, "stopPrice": 21000.0,
        "bracket1": {"action": "Sell", "orderType": "Stop", "stopPrice": 20995.0,
                     "timeInForce": "GTC"},
        "bracket2": {"action": "Sell", "orderType": "Limit", "price": 21030.0,
                     "timeInForce": "GTC"}})


def test_ws_oso_stoplimit_without_a_trigger_is_refused_before_sending():
    ws, sent = capturing_ws()
    with pytest.raises(ValueError):
        run(ws.place_oso(**KW, stop_price=20995.0, entry_type="StopLimit", entry_price=21002.0))
    assert sent == []


def test_adapter_stoplimit_order_sends_the_trigger_never_the_sl(tmp_path):
    ad, sent = mkadapter(tmp_path)
    req = OrderRequest("NQZ6", "Sell", 1, "StopLimit", 20990.0, stop_price=12345.0,
                       trigger_price=20992.0, time_in_force="GTC")
    assert run(ad.place_order(req)).ok
    assert_bytes(sent[0], "order/placeorder", {
        "accountSpec": "APEX", "accountId": 66121477, "action": "Sell", "symbol": "NQZ6",
        "orderQty": 1, "orderType": "StopLimit", "timeInForce": "GTC", "isAutomated": True,
        "text": "Onyx", "price": 20990.0, "stopPrice": 20992.0})


def test_adapter_stoplimit_bracket_sends_trigger_limit_and_the_sl_bracket(tmp_path):
    ad, sent = mkadapter(tmp_path)
    req = OrderRequest("NQZ6", "Buy", 2, "StopLimit", 21002.0, 20995.0, 21030.0, "homebase:chart",
                       trigger_price=21000.0)
    r = run(ad.place_bracket(req))
    assert r.ok and r.raw["sl_order_id"] == 2 and r.raw["tp_order_id"] == 3
    assert_bytes(sent[0], "order/placeoso", {
        "accountSpec": "APEX", "accountId": 66121477, "action": "Buy", "symbol": "NQZ6",
        "orderQty": 2, "orderType": "StopLimit", "timeInForce": "Day", "isAutomated": True,
        "text": "homebase:chart", "price": 21002.0, "stopPrice": 21000.0,
        "bracket1": {"action": "Sell", "orderType": "Stop", "stopPrice": 20995.0,
                     "timeInForce": "GTC"},
        "bracket2": {"action": "Sell", "orderType": "Limit", "price": 21030.0,
                     "timeInForce": "GTC"}})


def test_adapter_gtc_reaches_the_entry_of_a_plain_limit(tmp_path):
    ad, sent = mkadapter(tmp_path)
    assert run(ad.place_order(OrderRequest("NQZ6", "Buy", 1, "Limit", 21000.0,
                                           time_in_force="GTC"))).ok
    assert sent[0][1]["timeInForce"] == "GTC"
    assert run(ad.place_bracket(OrderRequest("NQZ6", "Buy", 1, "Limit", 21000.0, 20995.0,
                                             time_in_force="GTC"))).ok
    assert sent[1][1]["timeInForce"] == "GTC"
    assert sent[1][1]["bracket1"]["timeInForce"] == "GTC"


@pytest.mark.parametrize("trigger,price", [(None, 21002.0), (21000.0, None)])
def test_adapter_refuses_a_stoplimit_missing_its_limit_or_trigger(tmp_path, trigger, price):
    ad, sent = mkadapter(tmp_path)
    req = OrderRequest("NQZ6", "Buy", 1, "StopLimit", price, trigger_price=trigger)
    r = run(ad.place_order(req))
    assert not r.ok and r.error == "a Stop Limit order needs both a limit price and a trigger"
    r = run(ad.place_bracket(OrderRequest("NQZ6", "Buy", 1, "StopLimit", price, 20990.0,
                                          trigger_price=trigger)))
    assert not r.ok and r.error == "a Stop Limit order needs both a limit price and a trigger"
    assert sent == []


def test_trade_view_stoplimit_rows_carry_the_limit_and_the_trigger(tmp_path):
    ad, _ = mkadapter(tmp_path)
    ad._contracts[7] = "NQZ6"
    ad._orders = {
        5: {"id": 5, "accountId": 66121477, "contractId": 7, "action": "Buy",
            "ordStatus": "Working", "orderType": "StopLimit"},
        6: {"id": 6, "accountId": 66121477, "contractId": 7, "action": "Sell",
            "ordStatus": "Working", "orderType": "Limit"}}
    ad._order_versions = {
        5: {"orderId": 5, "orderType": "StopLimit", "orderQty": 1, "price": 21002.0,
            "stopPrice": 21000.0},
        6: {"orderId": 6, "orderType": "Limit", "orderQty": 1, "price": 21050.0}}
    rows = {o["order_id"]: o for o in ad.trade_view()["orders"]}
    assert rows["5"]["type"] == "StopLimit"
    assert (rows["5"]["price"], rows["5"]["trigger"]) == (21002.0, 21000.0)
    assert "trigger" not in rows["6"]                     # only a StopLimit row carries a trigger
    assert rows["6"] == {"order_id": "6", "symbol": "NQZ6", "side": "Sell", "type": "Limit",
                         "qty": 1, "price": 21050.0, "stop_price": None, "status": "Working",
                         "tif": None}


def test_trade_view_rows_carry_the_tif_from_the_broker(tmp_path):
    ad, _ = mkadapter(tmp_path)
    ad._contracts[7] = "NQZ6"
    ad._orders = {
        5: {"id": 5, "accountId": 66121477, "contractId": 7, "action": "Buy", "ordStatus": "Working"},
        6: {"id": 6, "accountId": 66121477, "contractId": 7, "action": "Buy", "ordStatus": "Working",
            "timeInForce": "Day"},
        8: {"id": 8, "accountId": 66121477, "contractId": 7, "action": "Buy", "ordStatus": "Working"}}
    ad._order_versions = {
        5: {"orderId": 5, "orderType": "Limit", "orderQty": 1, "price": 1.0, "timeInForce": "GTC"},
        6: {"orderId": 6, "orderType": "Limit", "orderQty": 1, "price": 2.0},
        8: {"orderId": 8, "orderType": "Limit", "orderQty": 1, "price": 3.0}}
    rows = {o["order_id"]: o["tif"] for o in ad.trade_view()["orders"]}
    assert rows == {"5": "GTC", "6": "Day", "8": None}      # the version first, then the order, else None


def _legged():
    """The base class's legged place_bracket (no native OSO), recording place_order."""
    from homebase.broker.base import BrokerAdapter, OrderResult

    class Legged(BrokerAdapter):
        platform = "legged"

        def __init__(self):
            super().__init__("legged")
            self.sent = []

        async def connect(self): ...
        async def close(self): ...
        async def observe_fills(self, on_fill): ...
        async def flatten_all(self): return OrderResult(ok=True)
        async def cancel_all(self): return OrderResult(ok=True)
        async def get_balance(self): return {}
        async def get_net_position(self, symbol): return 0

        async def place_order(self, req):
            self.sent.append(req)
            return OrderResult(ok=True, order_id=str(len(self.sent)))

    return Legged()


@pytest.mark.parametrize("typ,kw", [("Stop", {}), ("StopLimit", {"trigger_price": 100.0})])
def test_legged_fallback_refuses_bracketed_stop_entries(typ, kw):
    """Fix round 1 (review Minor 6): the legged fallback rests the SL the moment the entry is PLACED,
    not when it fills -- for a stop entry that is the wrong side of the market."""
    ad = _legged()
    r = run(ad.place_bracket(OrderRequest("NQZ6", "Buy", 1, typ, 101.0, 99.0, 110.0, **kw)))
    assert not r.ok and r.error == "bracketed stop entries need a broker OSO"
    assert ad.sent == []


def test_legged_fallback_still_legs_market_and_limit_entries():
    ad = _legged()
    assert run(ad.place_bracket(OrderRequest("NQZ6", "Buy", 1, "Limit", 101.0, 99.0, 110.0))).ok
    assert [(r.order_type, r.side) for r in ad.sent] == \
        [("Limit", "Buy"), ("Stop", "Sell"), ("Limit", "Sell")]
    ad = _legged()
    r = run(ad.place_bracket(OrderRequest("NQZ6", "Buy", 1, "Stop", 101.0)))   # no SL/TP: a plain stop
    assert r.ok and [x.order_type for x in ad.sent] == ["Stop"]
