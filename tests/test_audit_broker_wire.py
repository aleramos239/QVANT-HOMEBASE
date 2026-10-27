"""Audit 2026-10-27, broker group: lost plain orders, a dying socket, fills, status backstops, tokens."""
from __future__ import annotations

import asyncio
import datetime as dt
import json

import pytest

from homebase.broker.base import OrderRequest
from homebase.broker import tradovate_ws as W
from homebase.broker.tradovate_ws import TradovateWS, WSClosed
from tests.test_tradovate import mkadapter, run, tradovate_like

MKT = OrderRequest(symbol="NQ", side="Buy", qty=2, order_type="Market", text="homebase:chart")


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _timeout_adapter(tmp_path, orders):
    def answer(endpoint, query, body):
        if endpoint == "order/list":
            return orders
        return tradovate_like(endpoint, query, body)
    ad = mkadapter(tmp_path, answer)

    async def no_answer(**kw):
        raise asyncio.TimeoutError()
    ad._ws.place_order = no_answer
    return ad


def test_plain_order_timeout_is_unknown_not_a_refusal(tmp_path):
    ad = _timeout_adapter(tmp_path, [])
    r = run(ad.place_order(MKT))
    assert not r.ok and r.error and (r.raw or {}).get("outcome_unknown") is True


def test_plain_order_timeout_finds_the_order_at_the_broker(tmp_path):
    o = {"id": 55, "accountId": 66121477, "contractId": 3267315, "timestamp": _now(), "action": "Buy",
         "ordStatus": "Working"}
    ad = _timeout_adapter(tmp_path, [o])
    ad._order_versions[55] = {"orderQty": 2, "orderType": "Market"}
    r = run(ad.place_order(MKT))
    assert r.ok and r.order_id == "55"


def test_plain_order_with_a_different_known_qty_is_not_adopted(tmp_path):
    o = {"id": 55, "accountId": 66121477, "contractId": 3267315, "timestamp": _now(), "action": "Buy",
         "ordStatus": "Working"}
    ad = _timeout_adapter(tmp_path, [o])
    ad._order_versions[55] = {"orderQty": 9, "orderType": "Market"}
    r = run(ad.place_order(MKT))
    assert not r.ok and r.raw["outcome_unknown"]


def test_a_refusal_status_stays_a_plain_refusal(tmp_path):
    ad = mkadapter(tmp_path, lambda e, q, b: None)       # the order call answers 404
    r = run(ad.place_order(MKT))
    assert not r.ok and not (r.raw or {}).get("outcome_unknown")


def test_socket_death_fails_every_pending_request_at_once():
    async def go():
        ws = TradovateWS(token="t")

        class Dead:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        ws.ws = Dead()
        futs = [asyncio.get_running_loop().create_future() for _ in range(2)]
        ws._pending = {5: futs[0], 6: futs[1]}
        await ws._reader()
        return futs, ws
    futs, ws = run(go())
    assert all(isinstance(f.exception(), WSClosed) for f in futs) and ws._pending == {}


def test_a_timed_out_request_leaves_no_pending_id(monkeypatch):
    async def go():
        ws = TradovateWS(token="t")

        class Quiet:
            async def send(self, frame): ...
        ws.ws = Quiet()
        real = asyncio.wait_for

        async def fast(f, timeout):
            return await real(f, 0.01)
        monkeypatch.setattr(W.asyncio, "wait_for", fast)
        with pytest.raises(asyncio.TimeoutError):
            await ws.request("x")
        return ws._pending
    assert run(go()) == {}


def test_a_failed_authorize_closes_the_socket():
    async def go():
        ws = TradovateWS(token="t")
        closed = []

        class S:
            async def send(self, frame):
                endpoint, mid, *_ = frame.split("\n", 3)
                ws._pending.pop(int(mid)).set_result({"s": 401, "i": int(mid)})

            async def close(self):
                closed.append(1)
        ws.ws = S()
        with pytest.raises(RuntimeError, match="authorize failed"):
            await ws.authorize()
        return closed
    assert run(go()) == [1]


def test_unresolved_fill_is_parked_not_delivered(tmp_path):
    ad = mkadapter(tmp_path, lambda e, q, b: None)       # every lookup 404s

    async def go():
        fe = await ad._build_fill_event({"id": 9, "orderId": 777, "contractId": 3267315, "qty": 1,
                                         "action": "Sell", "price": 1.0})
        n = len(ad._lookup_tasks)
        for t in list(ad._lookup_tasks):
            t.cancel()
        return fe, n
    fe, parked = run(go())
    assert fe is None and parked == 1


def test_a_fill_of_an_order_we_placed_is_still_delivered(tmp_path):
    ad = mkadapter(tmp_path, lambda e, q, b: None)
    ad._order_symbols[777] = "NQZ6"
    fe = run(ad._build_fill_event({"id": 9, "orderId": 777, "contractId": 3267315, "qty": 1,
                                   "action": "Sell", "price": 1.0}))
    assert fe is not None


def test_status_backstop_rereads_a_cached_working_order(tmp_path):
    ad = mkadapter(tmp_path, lambda e, q, b: {"id": 5, "ordStatus": "Filled"} if e == "order/item" else None)
    ad._orders[5] = {"id": 5, "ordStatus": "Working"}    # the fill push was lost
    assert run(ad.get_order_status("5")) == "Filled"
    ad._ws.ws.sent.clear()
    assert run(ad.get_order_status("5")) == "Filled" and ad._ws.ws.sent == []   # final: trusted from cache


def test_lost_market_oso_cancel_still_pending_is_not_adopted(tmp_path, monkeypatch):
    from tests.test_tradovate import _lost_oso
    import homebase.broker.tradovate as T
    orig = T.TradovateAdapter.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        self._lost_polls, self._lost_poll_s, self._lost_retry_s = 2, 0, 0
    monkeypatch.setattr(T.TradovateAdapter, "__init__", init)
    ad, r = _lost_oso(tmp_path, "Working", "PendingCancel")
    assert not r.ok and r.error.startswith("OSO failed") and r.raw["outcome_unknown"]


def test_flatten_still_liquidates_when_the_position_read_fails(tmp_path):
    def answer(endpoint, query, body):
        if endpoint == "position/list":
            return None                                  # 404
        if endpoint == "order/liquidateposition":
            return {"orderId": 91, "failureReason": "Success"}
        return tradovate_like(endpoint, query, body)
    ad = mkadapter(tmp_path, answer)
    r = run(ad.flatten_symbol("NQ"))
    assert r.ok and r.raw["net_before"] is None and r.raw["market"]["order_id"] == "91"


def test_saved_token_is_reused_after_a_restart(tmp_path, monkeypatch):
    import homebase.broker.tradovate as T
    ad = mkadapter(tmp_path, lambda e, q, b: None)
    exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%S")
    ad._auth.token_persist_path.write_text(json.dumps(
        {"env": "demo", "access_token": "tok", "md_access_token": "md", "expiration_time": exp, "name": "Me"}))
    ad._auth.tokens = None
    monkeypatch.setattr(T, "get_credentials", lambda k: {"username": "me", "password": "pw"})
    logged = []
    ad._auth.login = lambda u, p: logged.append(u)
    opened = []

    async def open_socket(**kw):
        opened.append(ad._auth.access_token)
    ad._open_socket = open_socket
    ad._schedule_seed = lambda: None

    async def go():
        await ad.connect()
        ad._keepalive.cancel()
    run(go())
    assert logged == [] and opened == ["tok"]


def test_token_file_is_written_atomically(tmp_path):
    from homebase.broker.tradovate_auth import TradovateAuth, TradovateTokens
    a = TradovateAuth("demo", tmp_path / "t.json", tmp_path / "d.json")
    a.tokens = TradovateTokens(access_token="x")
    a._persist_tokens()
    assert json.loads((tmp_path / "t.json").read_text())["access_token"] == "x"
    assert not list(tmp_path.glob("*.tmp"))


def test_login_cap_can_be_lowered_by_env(monkeypatch):
    from homebase.broker.login_budget import LoginBudget
    monkeypatch.setenv("HOMEBASE_LOGINS_PER_HOUR", "1")
    b = LoginBudget()
    b.record_login("k")
    assert b.blocked("k") and "last hour" in b.blocked("k")


def test_a_desk_md_without_a_budget_never_password_logs_in(tmp_path, monkeypatch):
    import homebase.data.marketdata as md_mod
    monkeypatch.setattr(md_mod, "state_dir", lambda: tmp_path)
    monkeypatch.setattr(md_mod, "get_credentials", lambda key: pytest.fail("read the password"))
    m = md_mod.TradovateMD("k", "demo", token_provider=lambda: "")
    with pytest.raises(RuntimeError, match="no login budget"):
        run(m.connect())
