"""The broker order bodies a Lab strategy's entry sends, pinned byte for byte (Step B, task B2; design question 9).

A stop with no target is a legal bracket (`tp_price=None`): the OSO carries bracket1 (the stop) and no bracket2.
The existing pins (tests/test_order_bodies_pinned.py) hold that shape only for a Limit entry; a Lab strategy sends it
on a Stop entry and on a Market entry. No network: the ws client's `request` is the capturing fake of that file.

Two links are pinned, so the bytes below are the bytes the ENGINE's Lab path produces:
  1. engine.lab_enter -> the OrderRequest handed to the adapter (a recording adapter);
  2. that same OrderRequest -> the Tradovate adapter -> the `order/placeoso` body.
Do not edit a literal to make a test pass: a difference is a behaviour change on the order path.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from homebase import labcfg
from homebase.broker.base import OrderRequest
from homebase.config import AccountCfg, AppCfg
from homebase.engine import Engine, LabLeg
from tests.test_engine import Clock, FakeAdapter
from tests.test_order_bodies_pinned import assert_bytes, mkadapter

LAB = "lab_pp"
CONTRACT = "NQZ6"                    # the record's market, already a contract name: no front-month lookup in a pin


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---- the requests the engine builds --------------------------------------------------------------------------
REQ_STOP_SL_ONLY = OrderRequest(symbol=CONTRACT, side="Buy", qty=2, order_type="Stop", price=21010.5,
                                stop_price=21005.5, tp_price=None, text="homebase:entry")
REQ_MARKET_SL_ONLY = OrderRequest(symbol=CONTRACT, side="Sell", qty=1, order_type="Market", price=None,
                                  stop_price=21020.0, tp_price=None, text="homebase:entry")
REQ_STOP_SL_TP = OrderRequest(symbol=CONTRACT, side="Buy", qty=2, order_type="Stop", price=21010.5,
                              stop_price=21005.5, tp_price=21025.5, text="homebase:entry")
REQ_PAIR_SELL_SL_ONLY = OrderRequest(symbol=CONTRACT, side="Sell", qty=2, order_type="Stop", price=20990.5,
                                     stop_price=20995.5, tp_price=None, text="homebase:entry")

# ---- the bodies on the wire ------------------------------------------------------------------------------------
BODY_STOP_SL_ONLY = {"accountSpec": "APEX", "accountId": 66121477, "action": "Buy", "symbol": "NQZ6",
                     "orderQty": 2, "orderType": "Stop", "timeInForce": "Day", "isAutomated": True,
                     "text": "homebase:entry", "stopPrice": 21010.5,
                     "bracket1": {"action": "Sell", "orderType": "Stop", "stopPrice": 21005.5,
                                  "timeInForce": "GTC"}}
BODY_MARKET_SL_ONLY = {"accountSpec": "APEX", "accountId": 66121477, "action": "Sell", "symbol": "NQZ6",
                       "orderQty": 1, "orderType": "Market", "timeInForce": "Day", "isAutomated": True,
                       "text": "homebase:entry",
                       "bracket1": {"action": "Buy", "orderType": "Stop", "stopPrice": 21020.0,
                                    "timeInForce": "GTC"}}
BODY_STOP_SL_TP = {"accountSpec": "APEX", "accountId": 66121477, "action": "Buy", "symbol": "NQZ6",
                   "orderQty": 2, "orderType": "Stop", "timeInForce": "Day", "isAutomated": True,
                   "text": "homebase:entry", "stopPrice": 21010.5,
                   "bracket1": {"action": "Sell", "orderType": "Stop", "stopPrice": 21005.5,
                                "timeInForce": "GTC"},
                   "bracket2": {"action": "Sell", "orderType": "Limit", "price": 21025.5,
                                "timeInForce": "GTC"}}
BODY_PAIR_SELL_SL_ONLY = {"accountSpec": "APEX", "accountId": 66121477, "action": "Sell", "symbol": "NQZ6",
                          "orderQty": 2, "orderType": "Stop", "timeInForce": "Day", "isAutomated": True,
                          "text": "homebase:entry", "stopPrice": 20990.5,
                          "bracket1": {"action": "Buy", "orderType": "Stop", "stopPrice": 20995.5,
                                       "timeInForce": "GTC"}}


def mkengine(tmp_path):
    rec = {"name": "pp", "root": CONTRACT, "label": "PP", "enabled": True, "qty": 2, "commission": 4.0,
           "session_window": ["09:25", "16:00"]}
    limits = labcfg.LabLimits(max_trades_day=3, max_qty=2, max_risk_usd=300.0, last_entry_et="11:00", flat_et="15:55")
    cfg = AppCfg(armed=True, accounts={"a1": AccountCfg(keyring_key="k", account_name="A1")},
                 book={LAB: [{"account": "a1", "qty": 2}]}, strategies={LAB: labcfg.strategy_cfg(rec, limits)})
    ad = FakeAdapter("a1")
    return Engine(cfg, {"a1": ad}, now_fn=Clock(), root=tmp_path), ad


# ---- link 1: lab_enter -> the adapter's OrderRequest -----------------------------------------------------------
@pytest.mark.parametrize("legs,qty,want", [
    ([LabLeg(iid=1, side="Buy", entry="Stop", entry_price=21010.5, sl_px=21005.5, tp_px=None, tp_rr=None,
             ref_px=21010.5)], 2, [REQ_STOP_SL_ONLY]),
    ([LabLeg(iid=1, side="Sell", entry="Market", entry_price=None, sl_px=21020.0, tp_px=None, tp_rr=None,
             ref_px=21015.0)], 1, [REQ_MARKET_SL_ONLY]),
    ([LabLeg(iid=1, side="Buy", entry="Stop", entry_price=21010.5, sl_px=21005.5, tp_px=21025.5, tp_rr=2.0,
             ref_px=21010.5, move=True)], 2, [REQ_STOP_SL_TP]),
    ([LabLeg(iid=3, side="Sell", entry="Stop", entry_price=20990.5, sl_px=20995.5, tp_px=None, tp_rr=None,
             ref_px=20990.5),
      LabLeg(iid=4, side="Buy", entry="Stop", entry_price=21010.5, sl_px=21005.5, tp_px=None, tp_rr=None,
             ref_px=21010.5)], 2, [REQ_STOP_SL_ONLY, REQ_PAIR_SELL_SL_ONLY]),      # the buy leg always goes first
], ids=["stop-entry-sl-only", "market-entry-sl-only", "stop-entry-sl-tp", "pair-sl-only"])
def test_the_requests_lab_enter_hands_the_adapter(tmp_path, legs, qty, want):
    eng, ad = mkengine(tmp_path)
    out = run(eng.lab_enter(LAB, legs, {"a1": qty}, max_rounds=3))
    assert out["accounts"]["a1"]["ok"] is True
    assert ad.brackets == want
    assert ad.orders == []                                 # the entry and its stop are ONE bracketed order


# ---- link 2: that OrderRequest -> the bytes on the wire --------------------------------------------------------
@pytest.mark.parametrize("req,literal", [
    (REQ_STOP_SL_ONLY, BODY_STOP_SL_ONLY),
    (REQ_MARKET_SL_ONLY, BODY_MARKET_SL_ONLY),
    (REQ_STOP_SL_TP, BODY_STOP_SL_TP),
    (REQ_PAIR_SELL_SL_ONLY, BODY_PAIR_SELL_SL_ONLY),
], ids=["stop-entry-sl-only", "market-entry-sl-only", "stop-entry-sl-tp", "pair-sell-leg-sl-only"])
def test_byte_identical_lab_brackets(tmp_path, req, literal):
    ad, sent = mkadapter(tmp_path)
    r = run(ad.place_bracket(req))
    assert r.ok and len(sent) == 1
    assert_bytes(sent[0], "order/placeoso", literal)
    assert "bracket2" in literal or "bracket2" not in sent[0][1]
    # the stop's id is bracket1's; with no target there is no target id for the engine to re-price or cancel
    assert r.raw["sl_order_id"] == 2
    if req.tp_price is None:
        assert json.loads(sent[0][2]).get("bracket2") is None


def test_a_stop_only_bracket_gives_the_engine_no_target_id(tmp_path):
    """The real adapter answers a stop-only OSO with oso1Id = the stop. The capturing fake returns an oso2Id
    for every request, so this pins the adapter's own mapping on a faithful answer."""
    ad, sent = mkadapter(tmp_path)

    async def answer(endpoint, body="", query=""):
        return {"orderId": 11, "oso1Id": 12}

    ad._ws.request = answer
    r = run(ad.place_bracket(REQ_STOP_SL_ONLY))
    assert r.ok and (r.order_id, r.raw["sl_order_id"], r.raw["tp_order_id"]) == ("11", 12, None)


def test_the_whole_path_engine_to_wire_for_a_stop_only_entry(tmp_path):
    """lab_enter on the real Tradovate adapter (fake wire): one request, the pinned bytes, and the round's ids."""
    (tmp_path / "e").mkdir()
    eng, _ = mkengine(tmp_path / "e")
    ad, sent = mkadapter(tmp_path)
    # no socket in a test (the wire is the capturing fake): THIS instance alone reads connected
    ad.__class__ = type("Wired", (type(ad),), {"connected": property(lambda self: True)})

    async def flat(symbol):                                # the position read in front of every Lab entry (fix
        return 0                                           # round 1, C2): not what this file pins

    ad.get_net_position = flat
    eng.adapters["a1"] = ad
    out = run(eng.lab_enter(LAB, [LabLeg(iid=1, side="Buy", entry="Stop", entry_price=21010.5, sl_px=21005.5,
                                         tp_px=None, tp_rr=None, ref_px=21010.5)], {"a1": 2}, max_rounds=3))
    assert out["accounts"]["a1"]["ok"] is True
    assert len(sent) == 1
    assert_bytes(sent[0], "order/placeoso", BODY_STOP_SL_ONLY)
    st = eng.states[f"{LAB}@a1"]
    assert (st.status, st.upper_id, st.up_sl_id) == ("placed", "1", "2")
