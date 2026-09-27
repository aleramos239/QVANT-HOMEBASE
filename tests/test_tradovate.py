"""Tradovate wire + fill path. No network: a fake socket answers frames the
way Tradovate does.

Regression for 2026-09-21: the buy stop filled and the fill push ARRIVED,
but the adapter dropped it — the contract-name lookup sent its id in the
BODY line, Tradovate answered 404, and a fill with no name was discarded.
The engine never heard of the entry, so the sell stop was never cancelled.
"""
from __future__ import annotations

import asyncio
import json

from homebase.broker.base import OrderRequest
from homebase.broker.tradovate import TradovateAdapter
from homebase.broker.tradovate_ws import TradovateWS


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


class FakeSocket:
    """Answers each frame (endpoint \\n id \\n query \\n body) via `answer`;
    None -> 404 with empty data, exactly what Tradovate sent back."""

    def __init__(self, ws: TradovateWS, answer):
        self.ws, self.answer, self.sent = ws, answer, []

    async def send(self, frame: str) -> None:
        self.sent.append(frame)
        endpoint, mid, query, body = frame.split("\n", 3)
        d = self.answer(endpoint, query, body)
        self.ws._pending.pop(int(mid)).set_result(
            {"s": 404 if d is None else 200, "i": int(mid),
             "d": "" if d is None else d})

    async def close(self) -> None: ...


def tradovate_like(endpoint, query, body):
    """Lookups answer only with the param in the QUERY line (verified live
    2026-09-21: body line -> 404, query line -> 200 on all four)."""
    if endpoint == "contract/item" and query == "id=3267315":
        return {"id": 3267315, "name": "NQZ6"}
    if endpoint == "contract/find" and query.startswith("name="):
        return {"id": 3267315, "name": query[len("name="):]}
    if endpoint == "order/item" and query == "id=663695020149":
        return {"id": 663695020149, "accountId": 66121477, "ordStatus": "Filled"}
    if endpoint == "position/list":
        return [{"accountId": 66121477, "contractId": 3267315, "netPos": 3}]
    if endpoint == "order/placeoso":                # the real reply shape
        return {"orderId": 663695020149, "oso1Id": 663695020150,
                "oso2Id": 663695020151}
    if endpoint == "order/cancelorder":
        return {}
    if endpoint == "order/modifyorder":
        return {}
    return None


def every_lookup_404s(endpoint, query, body):
    """The morning of 2026-09-21 as the adapter experienced it."""
    if endpoint == "order/placeoso":
        return {"orderId": 663695020149}
    return None


def mkadapter(tmp_path, answer) -> TradovateAdapter:
    ad = TradovateAdapter("acct", env="demo", keyring_key="k", state_dir=tmp_path)
    ws = TradovateWS(token="t")
    ws.ws = FakeSocket(ws, answer)
    ws.connected = True                         # as after the 'o' open frame
    ad._ws, ad._acct_num, ad._acct_name, ad._connected = ws, 66121477, "APEX", True
    return ad


def fill_push(order_id, action, qty, price, fid):
    """A real 2026-09-21 push, same keys Tradovate sent."""
    return {"e": "props", "d": {"entityType": "fill", "entity": {
        "id": fid, "orderId": order_id, "contractId": 3267315,
        "timestamp": "2026-09-21T13:30:00.337Z",
        "tradeDate": {"year": 2026, "month": 9, "day": 21},
        "action": action, "qty": qty, "price": price, "active": True,
        "finallyPaired": 0, "external": False}}}


BUY_STOP = OrderRequest(symbol="NQ", side="Buy", qty=3, order_type="Stop",
                        price=30231.5, stop_price=30226.5, tp_price=30246.5,
                        text="homebase:entry")


def collect_fills(ad, pushes, place=None):
    got = []

    async def scenario():
        async def on_fill(ev):
            got.append(ev)
        await ad.observe_fills(on_fill)
        if place is not None:
            assert (await ad.place_bracket(place)).ok
        for p in pushes:
            ad._on_ws_event(p)
        for _ in range(100):
            if len(got) >= len(pushes):
                break
            await asyncio.sleep(0.01)
        await ad.close()

    run(scenario())
    return got


# --- the wire ---------------------------------------------------------------
def test_lookups_send_their_params_in_the_query_line():
    ws = TradovateWS(token="t")
    ws.ws = sock = FakeSocket(ws, tradovate_like)
    assert run(ws.contract_item(3267315))["name"] == "NQZ6"
    assert run(ws.contract_find("NQZ6"))["id"] == 3267315
    assert run(ws.order_item(663695020149))["ordStatus"] == "Filled"
    endpoint, _, query, body = sock.sent[0].split("\n", 3)
    assert (endpoint, query, body) == ("contract/item", "id=3267315", "")


def test_writes_keep_their_json_in_the_body_line():
    ws = TradovateWS(token="t")
    ws.ws = sock = FakeSocket(ws, tradovate_like)
    run(ws.cancel_order(663695020169))
    endpoint, _, query, body = sock.sent[0].split("\n", 3)
    assert (endpoint, query, body) == ("order/cancelorder", "",
                                       '{"orderId": 663695020169}')


# --- the fill path (the 2026-09-21 failure) -----------------------------------
def test_entry_fill_reaches_the_engine_even_when_every_lookup_fails(tmp_path):
    """Cold contract cache + every lookup 404s: the fill for an order WE
    placed must still be delivered, named from the order itself."""
    ad = mkadapter(tmp_path, every_lookup_404s)
    got = collect_fills(ad, [fill_push(663695020149, "Buy", 3, 30231.75,
                                       663695020156)], place=BUY_STOP)
    assert len(got) == 1
    ev = got[0]
    assert ev.raw["orderId"] == 663695020149
    assert (ev.side, ev.qty, ev.price) == ("Buy", 3, 30231.75)
    assert ev.symbol.startswith("NQ")


def test_unnameable_fill_is_still_delivered_with_its_order_id(tmp_path):
    """Not our order, no name to be had: deliver it anyway — the engine
    matches entry legs on the order id, never on the name."""
    ad = mkadapter(tmp_path, every_lookup_404s)
    got = collect_fills(ad, [fill_push(663695020151, "Sell", 2, 30246.5,
                                       663695020181)])
    assert len(got) == 1 and got[0].raw["orderId"] == 663695020151
    assert got[0].symbol == ""


def test_cold_cache_fill_is_named_by_the_fixed_lookup(tmp_path):
    ad = mkadapter(tmp_path, tradovate_like)
    got = collect_fills(ad, [fill_push(663695020151, "Sell", 2, 30246.5,
                                       663695020181)])
    assert got[0].symbol == "NQZ6"


# --- reads that went through the same broken lookup ---------------------------
def test_net_position_reads_through_the_lookup(tmp_path):
    """contract/find 404'd too, so get_net_position always said 0 — the
    Flatten button and the reconnect recovery never saw a position."""
    ad = mkadapter(tmp_path, tradovate_like)
    assert run(ad.get_net_position("NQ")) == 3


def test_order_status_from_cache_then_lookup(tmp_path):
    ad = mkadapter(tmp_path, tradovate_like)
    ad._orders[663695020169] = {"id": 663695020169, "ordStatus": "Working"}
    assert run(ad.get_order_status("663695020169")) == "Working"   # cache
    assert run(ad.get_order_status("663695020149")) == "Filled"    # order/item
    assert ad._orders[663695020149]["ordStatus"] == "Filled"        # cached now
    assert run(ad.get_order_status("")) is None


# --- re-pricing the brackets to the fill -------------------------------------
def test_bracket_result_names_its_stop_and_target(tmp_path):
    ad = mkadapter(tmp_path, tradovate_like)
    r = run(ad.place_bracket(BUY_STOP))
    assert (r.raw["sl_order_id"], r.raw["tp_order_id"]) == (663695020150, 663695020151)


def test_modify_sends_type_and_the_orders_own_qty(tmp_path):
    """Tradovate rejects a modify without orderType or orderQty; the qty
    comes from the order's own pushed version, never a guess."""
    ad = mkadapter(tmp_path, tradovate_like)
    ad._order_versions[663695020150] = {"orderId": 663695020150, "orderQty": 3}
    r = run(ad.modify_order("663695020150", "Stop", stop_price=30226.75, qty=9))
    assert r.ok
    endpoint, _, query, body = ad._ws.ws.sent[-1].split("\n", 3)
    assert endpoint == "order/modifyorder" and query == ""
    assert json.loads(body) == {"orderId": 663695020150, "orderType": "Stop",
                                "orderQty": 3, "stopPrice": 30226.75}


def test_modify_reports_a_logical_reject(tmp_path):
    def rejects(endpoint, query, body):
        if endpoint == "order/modifyorder":
            return {"failureReason": "UnknownReason", "failureText": "Too late"}
        return None
    ad = mkadapter(tmp_path, rejects)
    r = run(ad.modify_order("663695020150", "Stop", stop_price=1.0, qty=3))
    assert not r.ok and "Too late" in r.error


def test_engine_and_adapter_move_the_brackets_on_the_wire(tmp_path):
    """Real engine + real adapter, fake wire. Today's 9:30 replayed: the buy
    stop 30231.5 fills 1 tick worse at 30231.75 — on the wire the sell stop is
    cancelled and the SL/TP are re-priced 5/15 points from the FILL."""
    from homebase.engine import Engine
    from tests.test_engine import Clock, mkcfg

    ids = iter([(663695020149, 663695020150, 663695020151),
                (663695020169, 663695020170, 663695020171)])

    def wire(endpoint, query, body):
        if endpoint == "order/placeoso":
            o, s1, s2 = next(ids)
            return {"orderId": o, "oso1Id": s1, "oso2Id": s2}
        if endpoint in ("order/cancelorder", "order/modifyorder"):
            return {}
        return None                                 # lookups 404, as on 09-21

    ad = mkadapter(tmp_path, wire)
    cfg = mkcfg()
    cfg.accounts = {"acct": cfg.accounts["main"]}
    cfg.book = {"nq930": [{"account": "acct", "qty": 3}]}
    eng = Engine(cfg, {"acct": ad}, now_fn=Clock(), root=tmp_path)

    async def scenario():
        await ad.observe_fills(eng.on_fill)
        assert (await eng.handle_alert({"strategy": "nq930", "upper": 30231.5,
                                        "lower": 30211.5}))["ok"]
        ad._on_ws_event(fill_push(663695020149, "Buy", 3, 30231.75, 663695020156))
        for _ in range(100):
            if eng._state("nq930", "acct").brackets_moved:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
        await ad.close()

    run(scenario())
    sent = [(e, json.loads(b)) for e, _, _, b in
            (f.split("\n", 3) for f in ad._ws.ws.sent)
            if e in ("order/cancelorder", "order/modifyorder")]
    assert ("order/cancelorder", {"orderId": 663695020169}) in sent
    assert ("order/modifyorder", {"orderId": 663695020150, "orderType": "Stop",
                                  "orderQty": 3, "stopPrice": 30226.75}) in sent
    assert ("order/modifyorder", {"orderId": 663695020151, "orderType": "Limit",
                                  "orderQty": 3, "price": 30246.75}) in sent


# --- never leg a stop entry; rejects and read errors are not success ----------
def _sent_endpoints(ad):
    return [f.split("\n", 1)[0] for f in ad._ws.ws.sent]


def test_oso_reject_never_legs_a_stop_entry(tmp_path):
    """The old fallback placed a plain stop entry AND rested its stop at once
    on the wrong side of price — an instant, unwanted trade."""
    def rejects(endpoint, query, body):
        if endpoint == "order/placeoso":
            return {"failureReason": "UnknownReason", "failureText": "Rejected"}
        return {}
    ad = mkadapter(tmp_path, rejects)
    r = run(ad.place_bracket(BUY_STOP))
    assert not r.ok and "Rejected" in r.error
    assert "order/placeorder" not in _sent_endpoints(ad)


def test_oso_error_never_legs_a_stop_entry(tmp_path):
    def errors(endpoint, query, body):
        return None if endpoint == "order/placeoso" else {}   # 404 on the OSO
    ad = mkadapter(tmp_path, errors)
    r = run(ad.place_bracket(BUY_STOP))
    assert not r.ok
    assert "order/placeorder" not in _sent_endpoints(ad)


def test_cancel_reports_a_logical_reject(tmp_path):
    def rejects(endpoint, query, body):
        if endpoint == "order/cancelorder":
            return {"failureReason": "UnknownReason", "failureText": "Already filled"}
        return None
    ad = mkadapter(tmp_path, rejects)
    r = run(ad.cancel_order_by_id("663695020169"))
    assert not r.ok and "Already filled" in r.error


def test_a_failed_position_read_is_not_flat(tmp_path):
    """A read error used to come back as 0 — 'flat' — which is how the 404
    hid for a week, and would let a flatten cancel a live position's stop."""
    import pytest
    def broken(endpoint, query, body):
        if endpoint == "contract/find":
            return {"id": 3267315, "name": "NQZ6"}
        return None                                   # position/list 404s
    ad = mkadapter(tmp_path, broken)
    with pytest.raises(Exception):
        run(ad.get_net_position("NQ"))


# --- the chart's exits: one OCO pair (order/placeoco) -------------------------------------
def test_place_oco_sends_one_stop_with_its_limit_as_other_and_reads_both_ids(tmp_path):
    def wire(endpoint, query, body):
        if endpoint == "order/placeoco":
            return {"orderId": 663695020301, "ocoId": 663695020302}
        return None
    ad = mkadapter(tmp_path, wire)
    r = run(ad.place_oco("NQ", "Sell", 3, 30210.25, 30260.5))
    assert r.ok and r.order_id == "663695020301"
    assert (r.raw["sl_order_id"], r.raw["tp_order_id"]) == ("663695020301", "663695020302")
    [frame] = ad._ws.ws.sent
    endpoint, _, query, body = frame.split("\n", 3)
    assert (endpoint, query) == ("order/placeoco", "")
    sym = json.loads(body)["symbol"]
    assert json.loads(body) == {
        "accountSpec": "APEX", "accountId": 66121477, "action": "Sell", "symbol": sym,
        "orderQty": 3, "orderType": "Stop", "stopPrice": 30210.25, "timeInForce": "GTC",
        "isAutomated": True, "text": "homebase:chart-exit",
        "other": {"action": "Sell", "orderType": "Limit", "price": 30260.5, "timeInForce": "GTC"}}
    assert sym.startswith("NQ") and len(sym) == 4           # the front contract, never the bare root


def test_place_oco_reject_timeout_and_half_answers_are_not_ok(tmp_path):
    def rejects(endpoint, query, body):
        return {"failureReason": "UnknownReason", "failureText": "Rejected"}
    r = run(mkadapter(tmp_path, rejects).place_oco("NQ", "Buy", 1, 30300.0, 30200.0))
    assert not r.ok and r.error == "Rejected" and not r.raw.get("outcome_unknown")

    def errors(endpoint, query, body):
        return None                                  # 404: the request raised
    r = run(mkadapter(tmp_path, errors).place_oco("NQ", "Buy", 1, 30300.0, 30200.0))
    assert not r.ok and r.error.startswith("OCO failed") and r.raw["outcome_unknown"] is True

    def half(endpoint, query, body):
        return {"orderId": 5}
    r = run(mkadapter(tmp_path, half).place_oco("NQ", "Buy", 1, 30300.0, 30200.0))
    assert not r.ok and r.order_id == "5" and r.raw["outcome_unknown"] is True


def test_the_base_adapter_has_no_oco():
    from homebase.broker.base import BrokerAdapter
    r = run(BrokerAdapter.place_oco(None, "NQ", "Sell", 1, 1.0, 2.0))
    assert not r.ok and r.error == "this broker has no OCO"
