from __future__ import annotations

import asyncio
import datetime as dt
import time

import httpx
import pytest

from homebase.broker import topstepx
from homebase.broker.base import AccountNotOnLogin, OrderRequest
from homebase.broker.topstepx import TopstepXAdapter
from homebase.broker.topstepx_auth import TsxSession

TOKEN = "TOK-SECRET-456"
ACCOUNTS = [
    {"id": 11, "name": "PRAC-V2-1", "balance": 150000.0},
    {"id": 22, "name": "Combine-50K", "balance": 50000.0},
]


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class Api:
    """A fake TopstepX userapi: records every call; `handlers` maps (method, path) to a function(req) -> Response | raises."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.handlers: dict = {}
        self.orders: list[dict] = []          # what GET /Order/account/22 lists
        self.trades: list[dict] = []          # what GET /Trade/id/22 lists
        self.positions: list[dict] = []       # what GET /Position/all/account/22 lists

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        h = self.handlers.get((req.method, req.url.path))
        if h:
            return h(req)
        if req.url.path == "/TradingAccount":
            return httpx.Response(200, json=ACCOUNTS)
        if req.method == "GET" and req.url.path == "/Trade/id/22":
            return httpx.Response(200, json=self.trades)
        if req.method == "GET" and req.url.path == "/Position/all/account/22":
            return httpx.Response(200, json=self.positions)
        if req.method == "POST" and req.url.path == "/Order":
            return httpx.Response(200, json={"success": True, "orderId": 9001})
        if req.method == "GET" and req.url.path.startswith("/Order/account/"):
            return httpx.Response(200, json=self.orders)
        return httpx.Response(200, json={"success": True})

    def sent(self, method, path):
        import json
        return [json.loads(c.content) if c.content else None for c in self.calls
                if c.method == method and c.url.path == path]

    def paths(self):
        return [(c.method, c.url.path) for c in self.calls]


class StubHub:
    made: list = []
    up = False

    def __init__(self, session, on_event, *, on_up=None, on_auth_lost=None, **kw):
        self.session, self.on_event, self.on_up, self.on_auth_lost = session, on_event, on_up, on_auth_lost
        self.started = self.stopped = 0
        StubHub.made.append(self)

    async def start(self):
        self.started += 1

    async def stop(self):
        self.stopped += 1


@pytest.fixture(autouse=True)
def stub_hub(monkeypatch):
    StubHub.made = []
    monkeypatch.setattr(topstepx, "TsxHub", StubHub)


@pytest.fixture
def api():
    return Api()


def make_session(api):
    s = TsxSession("tsx:owner", http=httpx.AsyncClient(transport=httpx.MockTransport(api)))
    s._token, s.expires_at = TOKEN, time.time() + 3600      # logged in: no /Login in these tests
    return s


def adapter(api, name="Combine-50K", session=None, **kw):
    return TopstepXAdapter("acct-1", keyring_key="tsx:owner", account_name=name,
                           session=session or make_session(api), **kw)


def connected(api, name="Combine-50K"):
    a = adapter(api, name)
    run(a.connect())
    return a


# ---- accounts -----------------------------------------------------------------------------------------------------
def test_connect_picks_the_named_account_and_a_missing_name_raises_AccountNotOnLogin(api):
    a = adapter(api, "combine-50k")                      # case-insensitive
    run(a.connect())
    assert a.connected and a.broker_key == ("topstepx", 22)
    assert a.pinned_ok
    b = adapter(api, "Nope")
    with pytest.raises(AccountNotOnLogin) as ei:
        run(b.connect())
    assert ei.value.listed == ["PRAC-V2-1", "Combine-50K"]
    assert not b.connected


def test_list_accounts_marks_practice_rows(api):
    a = connected(api)
    assert a.list_accounts() == [
        {"id": 11, "name": "PRAC-V2-1", "active": True, "practice": True},
        {"id": 22, "name": "Combine-50K", "active": True, "practice": False}]


def test_a_probe_lists_accounts_and_starts_no_socket(api):
    s = make_session(api)
    p = adapter(api, "", session=s)
    run(p.connect())
    assert len(p.list_accounts()) == 2
    assert StubHub.made == [] and s.listeners == [] and s.hub is None


def test_one_socket_per_login_and_close_stops_it_only_with_the_last_listener(api):
    s = make_session(api)
    a, b = adapter(api, session=s), adapter(api, "PRAC-V2-1", session=s)
    run(a.connect())
    run(b.connect())
    run(b.connect())                                     # a reconnect does not list b twice
    assert len(StubHub.made) == 1 and s.hub is StubHub.made[0] and StubHub.made[0].started == 1
    assert s.listeners == [a, b]
    run(a.close())
    assert s.listeners == [b] and s.hub is not None and StubHub.made[0].stopped == 0
    run(b.close())
    assert s.listeners == [] and s.hub is None and StubHub.made[0].stopped == 1
    assert ("POST", "/Logout") not in api.paths()        # the session is never closed


def test_contract_id_for_nq_es_gc_front_months(api):
    a = adapter(api)
    today = dt.date(2026, 10, 30)
    assert a.contract_id("NQ", today=today) == "CON.F.US.ENQ.Z26"
    assert a.contract_id("MNQ", today=today) == "CON.F.US.MNQ.Z26"
    assert a.contract_id("ES", today=today) == "CON.F.US.EP.Z26"
    assert a.contract_id("GC", today=today) == "CON.F.US.GCE.Z26"
    assert a.contract_id("MGC", today=today) == "CON.F.US.MGC.Z26"
    assert a.contract_id("NQH27", today=today) == "CON.F.US.ENQ.H27"       # an explicit contract is kept
    assert a.contract_id("GC", today=dt.date(2026, 12, 28)) == "CON.F.US.GCE.G27"   # rolled into next year
    with pytest.raises(ValueError):
        a.contract_id("CL", today=today)


# ---- brackets -----------------------------------------------------------------------------------------------------
def test_a_buy_limit_bracket_sends_one_order_with_stopLoss_and_takeProfit_in_ticks(api):
    a = connected(api)
    r = run(a.place_bracket(OrderRequest("NQ", "Buy", 1, "Limit", price=20000, stop_price=19990, tp_price=20020,
                                         text="Onyx")))
    assert r.ok and r.order_id == "9001"
    assert r.raw["sl_order_id"] is None and r.raw["tp_order_id"] is None and r.raw["bracket"] == "attached"
    (body,) = api.sent("POST", "/Order")
    assert body["accountId"] == 22 and body["positionSize"] == 1 and body["type"] == 1
    assert body["limitPrice"] == 20000 and "stopPrice" not in body
    assert body["stopLoss"] == {"ticks": 40, "type": 0} and body["takeProfit"] == {"ticks": 80, "type": 0}
    assert body["contractId"].startswith("CON.F.US.ENQ.")
    assert body["customTag"].startswith("Onyx:") and len(body["customTag"]) == len("Onyx:") + 12
    assert sum(1 for p in api.paths() if p == ("POST", "/Order")) == 1


def test_a_sell_stop_entry_bracket(api):
    a = connected(api)
    r = run(a.place_bracket(OrderRequest("MGC", "Sell", 3, "Stop", price=2500.0, stop_price=2501.0, tp_price=2498.0)))
    assert r.ok
    (body,) = api.sent("POST", "/Order")
    assert body["positionSize"] == -3 and body["type"] == 4 and body["stopPrice"] == 2500.0
    assert "limitPrice" not in body
    assert body["stopLoss"] == {"ticks": 10, "type": 0} and body["takeProfit"] == {"ticks": 20, "type": 0}


def test_a_stoplimit_entry_bracket_measures_from_the_trigger(api):
    a = connected(api)
    run(a.place_bracket(OrderRequest("ES", "Buy", 2, "StopLimit", price=5000.5, trigger_price=5000.0,
                                     stop_price=4999.0, tp_price=5002.0)))
    (body,) = api.sent("POST", "/Order")
    assert body["type"] == 3 and body["limitPrice"] == 5000.5 and body["stopPrice"] == 5000.0
    assert body["stopLoss"]["ticks"] == 4 and body["takeProfit"]["ticks"] == 8


def test_a_market_bracket_with_a_price_is_measured_from_it(api):
    a = connected(api)
    run(a.place_bracket(OrderRequest("NQ", "Sell", 1, "Market", price=20000, stop_price=20010, tp_price=19990)))
    (body,) = api.sent("POST", "/Order")
    assert body["type"] == 2 and body["positionSize"] == -1
    assert "limitPrice" not in body and "stopPrice" not in body
    assert body["stopLoss"]["ticks"] == 40 and body["takeProfit"]["ticks"] == 40


def test_a_bracketed_market_entry_without_a_price_is_refused_and_nothing_is_sent(api):
    a = connected(api)
    n = len(api.calls)
    r = run(a.place_bracket(OrderRequest("NQ", "Buy", 1, "Market", stop_price=19990, tp_price=20020)))
    assert not r.ok and r.error == "topstepx: a bracketed market entry needs a price"
    assert len(api.calls) == n


def test_a_stop_on_the_wrong_side_is_refused_and_a_sub_tick_stop_rounds_to_one_tick(api):
    a = connected(api)
    n = len(api.calls)
    for req in (OrderRequest("NQ", "Buy", 1, "Limit", price=20000, stop_price=20000, tp_price=20010),   # stop at the entry
                OrderRequest("NQ", "Buy", 1, "Limit", price=20000, stop_price=20005, tp_price=20010),   # stop above a buy
                OrderRequest("NQ", "Sell", 1, "Limit", price=20000, stop_price=19995, tp_price=19990),  # stop below a sell
                OrderRequest("NQ", "Buy", 1, "Limit", price=20000, stop_price=19990, tp_price=19995),   # target below a buy
                OrderRequest("NQ", "Sell", 1, "Limit", price=20000, stop_price=20010, tp_price=20000)): # target at the entry
        r = run(a.place_bracket(req))
        assert not r.ok and r.error.startswith("topstepx:") and not r.raw.get("outcome_unknown")
    assert len(api.calls) == n
    r = run(a.place_bracket(OrderRequest("NQ", "Buy", 1, "Limit", price=20000, stop_price=19999.9, tp_price=20000.1)))
    assert r.ok
    (body,) = api.sent("POST", "/Order")
    assert body["stopLoss"]["ticks"] == 1 and body["takeProfit"]["ticks"] == 1


def test_a_stop_only_or_target_only_bracket_sends_just_that_leg(api):
    a = connected(api)
    run(a.place_bracket(OrderRequest("NQ", "Buy", 1, "Limit", price=20000, stop_price=19990)))
    (body,) = api.sent("POST", "/Order")
    assert "stopLoss" in body and "takeProfit" not in body


def test_ticks_round_away_from_the_entry(api):
    a = connected(api)
    run(a.place_bracket(OrderRequest("NQ", "Buy", 1, "Limit", price=20000, stop_price=19990.1, tp_price=20020.1)))
    (body,) = api.sent("POST", "/Order")
    assert body["stopLoss"]["ticks"] == 40 and body["takeProfit"]["ticks"] == 81   # 39.6 -> 40, 80.4 -> 81


# ---- plain orders -------------------------------------------------------------------------------------------------
def test_an_unbracketed_order_sends_no_stopLoss_or_takeProfit(api):
    a = connected(api)
    r = run(a.place_order(OrderRequest("NQ", "Buy", 2, "Limit", price=20000.1, stop_price=19990, tp_price=20020)))
    assert r.ok
    (body,) = api.sent("POST", "/Order")
    assert "stopLoss" not in body and "takeProfit" not in body
    assert body["limitPrice"] == 20000.0                  # rounded to the 0.25 tick


def test_a_bare_stop_uses_the_stop_price_and_a_bare_stop_entry_falls_back_to_price(api):
    a = connected(api)
    run(a.place_order(OrderRequest("NQ", "Sell", 1, "Stop", stop_price=19990)))
    run(a.place_order(OrderRequest("NQ", "Buy", 1, "Stop", price=20010)))
    s1, s2 = api.sent("POST", "/Order")
    assert s1["type"] == 4 and s1["stopPrice"] == 19990 and s1["positionSize"] == -1
    assert s2["stopPrice"] == 20010


def test_an_order_without_the_price_its_type_needs_is_refused_and_nothing_is_sent(api):
    a = connected(api)
    n = len(api.calls)
    for req in (OrderRequest("NQ", "Buy", 1, "Limit"), OrderRequest("NQ", "Buy", 1, "Stop"),
                OrderRequest("NQ", "Buy", 1, "StopLimit", price=1.0), OrderRequest("NQ", "Buy", 0, "Market"),
                OrderRequest("NQ", "Hold", 1, "Market"), OrderRequest("NQ", "Buy", 1, "Iceberg")):
        r = run(a.place_order(req))
        assert not r.ok and r.error.startswith("topstepx:")
    assert len(api.calls) == n


def test_a_refused_order_reports_the_brokers_words(api):
    api.handlers[("POST", "/Order")] = lambda req: httpx.Response(
        200, json={"success": False, "errorMessage": "Insufficient margin", "result": 3})
    a = connected(api)
    r = run(a.place_order(OrderRequest("NQ", "Buy", 1, "Market")))
    assert not r.ok and "Insufficient margin" in r.error and not r.raw.get("outcome_unknown")


def test_order_answer_shapes():
    f = topstepx._order_answer
    assert f({"result": 0, "orderId": 5}) == (True, "5", None)
    assert f({"success": True, "id": 6}) == (True, "6", None)
    assert f({"success": True}) == (False, None, None)                      # accepted, no id: ambiguous, not "ok"
    assert f({"success": False, "errorMessage": "no"}) == (False, None, "no")
    assert f({"result": 2, "orderId": 7, "errorMessage": "bad"}) == (False, None, "bad")


# ---- a timeout after the send -------------------------------------------------------------------------------------
def _timeout(req):
    raise httpx.ReadTimeout("slow")


def test_a_timeout_after_send_finds_the_order_by_customTag_and_never_resends(api):
    seen = {}

    def lookup(req):
        # the order the timed-out POST created, as the account's list shows it
        return httpx.Response(200, json=[{"id": 1, "customTag": "other:1"},
                                         {"id": 777, "customTag": seen["tag"]}])

    def post(req):
        import json
        seen["tag"] = json.loads(req.content)["customTag"]
        raise httpx.ReadTimeout("slow")

    api.handlers[("POST", "/Order")] = post
    api.handlers[("GET", "/Order/account/22")] = lookup
    a = connected(api)
    r = run(a.place_bracket(OrderRequest("NQ", "Buy", 1, "Limit", price=20000, stop_price=19990, tp_price=20020)))
    assert r.ok and r.order_id == "777"
    assert r.raw["sl_order_id"] is None and r.raw["bracket"] == "attached"
    assert sum(1 for p in api.paths() if p == ("POST", "/Order")) == 1


def test_a_timeout_after_send_and_not_found_is_outcome_unknown(api):
    api.handlers[("POST", "/Order")] = _timeout
    api.orders = [{"id": 1, "customTag": "other:1"}]
    a = connected(api)
    r = run(a.place_order(OrderRequest("NQ", "Buy", 1, "Market")))
    assert not r.ok and r.raw["outcome_unknown"] is True
    assert r.error.startswith("topstepx: order outcome unknown")
    assert TOKEN not in r.error
    assert sum(1 for p in api.paths() if p == ("POST", "/Order")) == 1


def test_a_failing_lookup_is_outcome_unknown_too(api):
    api.handlers[("POST", "/Order")] = _timeout
    api.handlers[("GET", "/Order/account/22")] = lambda req: httpx.Response(500, text="boom")
    a = connected(api)
    r = run(a.place_order(OrderRequest("NQ", "Buy", 1, "Market")))
    assert not r.ok and r.raw["outcome_unknown"] is True
    assert sum(1 for p in api.paths() if p == ("POST", "/Order")) == 1


def test_a_5xx_answer_to_the_order_is_looked_up_not_resent(api):
    api.handlers[("POST", "/Order")] = lambda req: httpx.Response(502, text="bad gateway")
    a = connected(api)
    r = run(a.place_order(OrderRequest("NQ", "Buy", 1, "Market")))
    assert not r.ok and r.raw["outcome_unknown"] is True
    assert sum(1 for p in api.paths() if p == ("POST", "/Order")) == 1


def test_an_accepted_answer_without_an_id_is_looked_up(api):
    api.handlers[("POST", "/Order")] = lambda req: httpx.Response(200, json={"success": True})
    a = connected(api)
    r = run(a.place_order(OrderRequest("NQ", "Buy", 1, "Market")))
    assert not r.ok and r.raw["outcome_unknown"] is True


def test_connect_refused_before_sending_is_a_plain_failure_with_no_lookup(api):
    def refuse(req):
        raise httpx.ConnectError("refused")

    api.handlers[("POST", "/Order")] = refuse
    a = connected(api)
    r = run(a.place_order(OrderRequest("NQ", "Buy", 1, "Market")))
    assert not r.ok and not r.raw.get("outcome_unknown")
    assert ("GET", "/Order/account/22") not in api.paths()


# ---- flatten / cancel ---------------------------------------------------------------------------------------------
def test_flatten_all_and_cancel_all_call_close_and_cancel_all_for_this_account_only(api):
    a = connected(api)
    assert run(a.flatten_all()).ok
    assert run(a.cancel_all()).ok
    assert run(a.cancel_order_by_id("123")).ok
    paths = [p for p in api.paths() if p[1] != "/TradingAccount"]
    assert paths == [("POST", "/Position/close/22"), ("POST", "/Order/cancel/22/all"), ("POST", "/Order/cancel/22/id/123")]


def test_a_refused_flatten_is_an_error_not_flat(api):
    api.handlers[("POST", "/Position/close/22")] = lambda req: httpx.Response(
        200, json={"success": False, "errorMessage": "market closed"})
    a = connected(api)
    r = run(a.flatten_all())
    assert not r.ok and "market closed" in r.error
    api.handlers[("POST", "/Position/close/22")] = lambda req: httpx.Response(500, text="x")
    assert not run(a.flatten_all()).ok


def test_cancel_order_by_id_refuses_a_non_numeric_id(api):
    a = connected(api)
    n = len(api.calls)
    assert not run(a.cancel_order_by_id("1/../../all")).ok
    assert len(api.calls) == n


def test_flatten_symbol_closes_every_held_contract_of_the_root(api):
    api.handlers[("GET", "/Position/all/account/22")] = lambda req: httpx.Response(200, json=[
        {"contractId": "CON.F.US.ENQ.U26", "positionSize": 2},          # an older contract still held
        {"contractId": "CON.F.US.EP.Z26", "positionSize": -1},
        {"contractId": "CON.F.US.ENQ.Z26", "positionSize": 0}])
    a = connected(api)
    r = run(a.flatten_symbol("NQ"))
    assert r.ok and r.raw["flattened"] == 1
    assert [p for p in api.paths() if "close" in p[1]] == [("POST", "/Position/close/22/contract/CON.F.US.ENQ.U26")]


def test_get_net_position_sums_the_root_and_raises_when_unreadable(api):
    api.handlers[("GET", "/Position/all/account/22")] = lambda req: httpx.Response(200, json=[
        {"contractId": "CON.F.US.ENQ.Z26", "positionSize": -2}, {"contractId": "CON.F.US.EP.Z26", "positionSize": 5}])
    a = connected(api)
    assert run(a.get_net_position("NQ")) == -2
    assert run(a.get_net_position("GC")) == 0
    api.handlers[("GET", "/Position/all/account/22")] = lambda req: httpx.Response(500, text="x")
    with pytest.raises(RuntimeError):
        run(a.get_net_position("NQ"))


def test_get_balance_and_metrics(api):
    a = connected(api)
    assert run(a.get_balance())["amount"] == 50000.0
    m = run(a.get_metrics())
    assert m["connected"] is True and m["account"] == "Combine-50K"
    assert set(m) >= {"balance", "realized_pnl", "open_positions", "open_position_count", "working_orders", "protective"}


# ---- fills, positions, a taken session ----------------------------------------------------------------------------
ENQ = "CON.F.US.ENQ.Z26"


def trade(tid, *, side=0, size=1, price=20000.0, account=22, contract=ENQ, ts="2026-10-30T14:00:00Z", **kw):
    return {"id": tid, "accountId": account, "contractId": contract, "price": price, "size": size, "side": side,
            "creationTimestamp": ts, **kw}


def pos(net, *, account=22, contract=ENQ):
    return {"accountId": account, "contractId": contract, "type": 1 if net > 0 else 2, "size": abs(net)}


def live(api, session=None):
    """A connected adapter whose socket is 'up', with a fill sink and a journal."""
    a = adapter(api, session=session)
    a.got, a.notes, a.log = [], [], []

    async def sink(ev):
        a.got.append(ev)

    a.journal = lambda event, **kw: a.log.append((event, kw))
    a.add_listener(lambda kind, ent: a.notes.append(kind))
    run(a.connect())
    StubHub.made[-1].up = True
    return a, sink


def test_a_trade_push_becomes_one_FillEvent_and_a_repeat_is_ignored(api):
    a, sink = live(api)

    async def go():
        await a.observe_fills(sink)
        await a._on_up()                                          # seeds (nothing yet)
        a._on_event("RealTimePosition", pos(2))
        a._on_event("RealTimeTrade", trade(501, side=0, size=2, price=20001.25))
        a._on_event("RealTimeTrade", trade(501, side=0, size=2, price=20001.25))     # the same trade again
        a._on_event("RealTimeTrade", trade(502, side=1, size=2, price=20010.0))
        a._on_event("RealTimePosition", pos(0))
        await a._pump
    run(go())
    assert [(e.symbol, e.side, e.qty, e.price, e.position_after) for e in a.got] == [
        ("NQ", "Buy", 2, 20001.25, 2), ("NQ", "Sell", 2, 20010.0, 2)]     # position_after = the cache when the trade came
    assert a.got[0].account_id == "acct-1" and a.got[0].raw["id"] == 501 and a.got[0].ts > 0
    assert a.notes.count("fill") == 2 and a.notes.count("position") == 2


def test_another_accounts_trade_a_voided_one_and_an_unreadable_one_are_not_delivered(api):
    a, sink = live(api)

    async def go():
        await a.observe_fills(sink)
        await a._on_up()
        a._on_event("RealTimeTrade", trade(1, account=11))
        a._on_event("RealTimeTrade", trade(2, account=None))                 # not provably ours
        a._on_event("RealTimeTrade", trade(3, voided=True))
        a._on_event("RealTimeTrade", trade(4, side=7))                       # unreadable side
        a._on_event("RealTimeTrade", trade(5, size=0))
        a._on_event("RealTimeOrder", {"id": 9, "accountId": 11})
        a._on_event("RealTimePosition", pos(3, account=11))
        await asyncio.sleep(0)
    run(go())
    assert a.got == [] and a._pump is None and a.notes == []
    assert sum(1 for e, _ in a.log if e == "tsx_trade_unreadable") == 2       # the bad side and the zero size
    assert a._pos == {}                                                   # the other account's position never entered


def test_trade_and_position_shapes():
    f, n = topstepx._trade_fields, topstepx._net_of
    assert f(trade(1, side=1, size=3))["side"] == "Sell" and f(trade(1, voided=True)) is None
    for bad in (trade(None), trade(1, size=1.5), trade(1, side=2), trade(1, contract=""), "x"):
        with pytest.raises(ValueError):
            f(bad)
    assert n({"type": 1, "size": 3}) == 3 and n({"type": 2, "size": 3}) == -3 and n({"type": 2, "size": 0}) == 0
    assert n({"positionSize": -2}) == -2 and n({"size": -2}) == -2 and n({"type": 0, "size": 0}) == 0
    assert n({"type": 2, "positionSize": -2}) == -2
    for bad in ({}, {"type": 1, "size": -1}, {"type": 0, "size": 2}, {"size": "2"}, {"positionSize": 1.5}, None):
        with pytest.raises(ValueError):
            n(bad)


def test_position_push_updates_get_net_position_without_a_rest_call(api):
    api.positions = [pos(1)]
    a, sink = live(api)
    n_reads = lambda: sum(1 for p in api.paths() if p == ("GET", "/Position/all/account/22"))
    assert run(a.get_net_position("NQ")) == 1 and n_reads() == 1       # never seeded: one REST read
    assert run(a.get_net_position("NQ")) == 1 and n_reads() == 1       # now served from the cache

    async def go():
        a._on_event("RealTimePosition", pos(-3))                       # long 1 -> short 3
        a._on_event("RealTimePosition", {"accountId": 22, "contractId": "CON.F.US.EP.Z26", "positionSize": 2})
        return await a.get_net_position("NQ"), await a.get_net_position("ES"), await a.get_net_position("GC")
    assert run(go()) == (-3, 2, 0) and n_reads() == 1
    m = run(a.get_metrics())
    assert m["open_positions"] == [{"symbol": "NQ", "net": -3}, {"symbol": "ES", "net": 2}]
    assert m["open_position_count"] == 2 and m["positions_known"] is True and m["balance"] == 50000.0
    assert a.notes == ["position", "position"]
    # an unreadable push: the cache can no longer be trusted, the next read goes to the broker
    a._on_event("RealTimePosition", {"accountId": 22, "contractId": ENQ, "size": "?"})
    api.positions = [pos(-1)]
    assert run(a.get_net_position("NQ")) == -1 and n_reads() == 2
    # the socket is down: the cache may have missed pushes, so the broker is asked
    StubHub.made[-1].up = False
    assert run(a.get_net_position("NQ")) == -1 and n_reads() == 3
    # flatten always asks the broker what is held now
    StubHub.made[-1].up = True
    api.positions = [pos(4)]
    assert run(a.flatten_symbol("NQ")).ok and n_reads() == 4
    assert ("POST", f"/Position/close/22/contract/{ENQ}") in api.paths()


def test_a_position_read_that_cannot_be_read_raises_and_is_never_flat(api):
    api.positions = [{"contractId": ENQ}]                              # no size at all
    a, sink = live(api)
    with pytest.raises(ValueError):
        run(a.get_net_position("NQ"))


def test_a_position_pushed_while_the_book_is_being_read_wins_over_the_read(api):
    a, sink = live(api)

    def slow_read(req):
        a._on_event("RealTimePosition", pos(5))                        # lands while the read is in flight
        return httpx.Response(200, json=[pos(1)])

    api.handlers[("GET", "/Position/all/account/22")] = slow_read
    assert run(a.get_net_position("NQ")) == 5


def _kick_setup(api, tmp_path, monkeypatch, budget=None):
    from homebase.store import secrets_store
    monkeypatch.setattr(secrets_store, "_store_path", lambda: tmp_path / "credentials.json")
    secrets_store.set_credentials("tsx:owner", username="Owner", password="pw-SECRET-9")
    api.handlers[("POST", "/Login")] = lambda req: httpx.Response(200, json={"token": "TOK-NEW", "userId": 5})
    s = make_session(api)
    s.budget = budget
    s.journal = lambda event, **kw: s.rec.append((event, kw))
    s.rec = []
    return s


def test_session_taken_journals_relogs_in_once_and_replays_missed_trades(api, tmp_path, monkeypatch):
    s = _kick_setup(api, tmp_path, monkeypatch)
    api.trades = [trade(601, ts="2026-10-30T14:00:00Z")]               # the day's history at connect
    a, sink = live(api, session=s)
    b = adapter(api, "PRAC-V2-1", session=s)
    run(b.connect())                                                   # a second desk account on the same login
    hub = StubHub.made[-1]
    assert hub.on_auth_lost is not None and len(StubHub.made) == 1
    real_relogin = s.relogin

    async def slow_relogin(why):                                       # a login takes time: the second call arrives meanwhile
        await asyncio.sleep(0.01)
        await real_relogin(why)
    s.relogin = slow_relogin

    async def go():
        await a.observe_fills(sink)
        await hub.on_up()                                              # the first open: seeds, delivers nothing
        assert a.got == []
        # the owner opens TopstepX: our socket is refused with a 401 at reopen; two paths call the handler at once
        await asyncio.gather(hub.on_auth_lost(), hub.on_auth_lost())
        api.trades = [trade(601), trade(603, side=1, ts="2026-10-30T14:07:00Z"), trade(602, ts="2026-10-30T14:05:00Z")]
        await hub.on_up()                                              # the socket is back: the gap is read
        await hub.on_up()                                              # and a second open finds nothing new
    run(go())
    assert api.paths().count(("POST", "/Login")) == 1 and s.taken == 1
    assert [x for x in s.rec if x[0] == "tsx_session_taken"] == [
        ("tsx_session_taken", {"accounts": ["Combine-50K", "PRAC-V2-1"], "count": 1})]
    assert [e.raw["id"] for e in a.got] == [602, 603] and [e.side for e in a.got] == ["Buy", "Sell"]    # oldest first, once
    assert all(e.position_after is None for e in a.got)
    assert run(a.get_metrics())["session_taken"] == 1
    assert "TOK-NEW" not in repr(s.rec) and TOKEN not in repr(s.rec) and "pw-SECRET-9" not in repr(s.rec)


def test_session_taken_with_the_budget_spent_does_not_log_in_and_says_why(api, tmp_path, monkeypatch):
    from homebase.broker.login_budget import LoginBudget
    budget = LoginBudget()
    s = _kick_setup(api, tmp_path, monkeypatch, budget=budget)
    for _ in range(4):
        budget.record_login("tsx:owner")                               # the hourly cap is reached
    a, sink = live(api, session=s)
    hub = StubHub.made[-1]
    run(hub.on_auth_lost())                                            # returns: no raise, no spin
    run(hub.on_auth_lost())
    assert ("POST", "/Login") not in api.paths() and s._token == TOKEN
    lines = [kw for e, kw in s.rec if e == "tsx_session_taken"]
    assert [k.get("deferred") for k in lines] == [None, lines[1]["deferred"], None, lines[3]["deferred"]]
    assert "logins on this user in the last hour" in lines[1]["deferred"] and lines[1]["count"] == 1
    assert s.taken == 2 and run(a.get_metrics())["session_taken"] == 2


def test_a_failed_relogin_is_journaled_by_class_only_and_reaches_the_hub(api, tmp_path, monkeypatch):
    s = _kick_setup(api, tmp_path, monkeypatch)
    api.handlers[("POST", "/Login")] = lambda req: httpx.Response(200, json={"errorMessage": "bad pw-SECRET-9"})
    a, sink = live(api, session=s)
    with pytest.raises(Exception):
        run(StubHub.made[-1].on_auth_lost())
    (kw,) = [kw for e, kw in s.rec if e == "tsx_session_taken" and "failed" in kw]
    assert kw["failed"] == "TsxLoginFailed" and "pw-SECRET-9" not in repr(s.rec)


def test_a_late_joiner_on_an_open_socket_seeds_itself_and_a_failing_read_never_raises(api):
    s = make_session(api)
    a, sink = live(api, session=s)
    StubHub.made[-1].up = True
    api.trades = [trade(1)]
    b = adapter(api, "PRAC-V2-1", session=s)
    api.handlers[("GET", "/Trade/id/11")] = lambda req: httpx.Response(200, json=[trade(7, account=11)])
    run(b.connect())                                                   # hub up: b's on_up ran in connect
    assert b._trades_seeded and 7 in b._seen
    api.handlers[("GET", "/Trade/id/22")] = lambda req: httpx.Response(500, text="x")
    run(a._on_up())                                                    # logged, not raised
    assert not a._trades_seeded


def test_session_pushes_do_not_log_in_and_violations_are_journaled_and_shown(api):
    s = make_session(api)
    s.rec = []
    s.journal = lambda event, **kw: s.rec.append((event, kw))
    a, sink = live(api, session=s)
    b = adapter(api, "PRAC-V2-1", session=s)
    run(b.connect())
    for x in (a, b):
        x._on_event("RealTimeSession", {"userId": 5, "token": TOKEN, "status": "ended"})
    assert s.rec == [("tsx_session_event", {"keys": ["status", "token", "userId"]})]      # keys only, once per login
    assert ("POST", "/Login") not in api.paths() and s.taken == 0
    a._on_event("RealTimeTradingAccountViolation", {"accountId": 11, "reason": "x"})       # another account's
    assert a.log == [] and run(a.get_metrics())["tsx_violation"] is None
    a._on_event("RealTimeRiskSettingsLockout", {"accountId": 22, "reason": "daily loss", "until": "t"})
    assert a.log == [("tsx_violation", {"account": "acct-1", "kind": "RealTimeRiskSettingsLockout",
                                        "keys": ["accountId", "reason", "until"]})]
    assert run(a.get_metrics())["tsx_violation"] == "RealTimeRiskSettingsLockout"
    a._on_event("RealTimeAccount", {"id": 22, "balance": 49000.5})
    assert run(a.get_metrics())["balance"] == 49000.5
