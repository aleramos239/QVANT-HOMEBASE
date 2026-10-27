"""Audit repair pass (broker group): the reviewer's findings on the first-pass fixes."""
from __future__ import annotations

import asyncio
import datetime as dt
import json

import homebase.broker.tradovate as T
from tests.test_tradovate import mkadapter, run, tradovate_like, BUY_MKT
from tests.test_audit_broker_wire import MKT, _now, _timeout_adapter


def _reuse_at(tmp_path, monkeypatch, now_utc, minutes_left):
    ad = mkadapter(tmp_path, lambda e, q, b: None)
    exp = (now_utc + dt.timedelta(minutes=minutes_left)).strftime("%Y-%m-%dT%H:%M:%S")
    ad._auth.token_persist_path.write_text(json.dumps(
        {"env": "demo", "access_token": "tok", "md_access_token": "md", "expiration_time": exp, "name": "Me"}))
    ad._auth.tokens = None
    ad._now = lambda: now_utc
    monkeypatch.setattr(T, "get_credentials", lambda k: {"username": "me", "password": "pw"})
    logged, opened = [], []
    ad._auth.login = lambda u, p: logged.append(u)

    async def open_socket(**kw):
        opened.append(1)
    ad._open_socket = open_socket
    ad._schedule_seed = lambda: None

    async def go():
        await ad.connect()
        ad._keepalive.cancel()
    run(go())
    return logged, opened


def test_a_saved_token_that_dies_in_the_open_hold_is_not_reused(tmp_path, monkeypatch):
    # Wed 09:22 ET: 15 min of life is under the reconnect buffer (it would come due at 09:37)
    logged, _ = _reuse_at(tmp_path, monkeypatch, dt.datetime(2026, 10, 28, 13, 22, tzinfo=dt.timezone.utc), 15)
    assert logged == ["me"]


def test_a_saved_token_that_lasts_past_the_hold_is_reused(tmp_path, monkeypatch):
    logged, opened = _reuse_at(tmp_path, monkeypatch, dt.datetime(2026, 10, 28, 13, 22, tzinfo=dt.timezone.utc), 120)
    assert logged == [] and opened == [1]


def test_a_foreign_plain_order_with_no_version_is_not_adopted(tmp_path):
    o = {"id": 55, "accountId": 66121477, "contractId": 3267315, "timestamp": _now(), "action": "Buy",
         "ordStatus": "Working"}
    r = run(_timeout_adapter(tmp_path, [o]).place_order(MKT))
    assert not r.ok and r.raw["outcome_unknown"]


def test_a_lone_oso_entry_with_no_bracket_and_no_version_is_not_adopted_or_cancelled(tmp_path):
    o = {"id": 78, "accountId": 66121477, "contractId": 3267315, "timestamp": _now(), "action": "Buy",
         "ordStatus": "Working"}
    ad = mkadapter(tmp_path, lambda e, q, b: [o] if e == "order/list" else tradovate_like(e, q, b))
    ad._lost_polls, ad._lost_poll_s, ad._lost_retry_s = 1, 0, 0

    async def no_answer(**kw):
        raise asyncio.TimeoutError()
    ad._ws.place_oso = no_answer
    r = run(ad.place_bracket(BUY_MKT))
    assert not r.ok and r.raw["outcome_unknown"]
    assert not [f for f in ad._ws.ws.sent if f.startswith("order/cancelorder")]


def test_a_parked_fill_whose_order_has_no_account_is_not_requeued(tmp_path, monkeypatch):
    ad = mkadapter(tmp_path, lambda e, q, b: None)
    monkeypatch.setattr(T, "PARK_DELAYS_S", (0, 0))
    seen = []

    async def lookup(oid):
        return {"id": oid}                       # an order with no accountId
    ad._lookup_order = lookup
    ad._enqueue_fill = lambda ent: seen.append(ent)
    audits = []
    ad.audit = lambda e: audits.append(e)
    run(ad._retry_fill({"id": 9, "orderId": 777}))
    assert seen == [] and audits[0]["event"] == "fill_unresolved"


def test_a_parked_fill_whose_order_has_an_account_is_requeued(tmp_path, monkeypatch):
    ad = mkadapter(tmp_path, lambda e, q, b: None)
    monkeypatch.setattr(T, "PARK_DELAYS_S", (0,))
    seen = []

    async def lookup(oid):
        return {"id": oid, "accountId": 66121477}
    ad._lookup_order = lookup
    ad._enqueue_fill = lambda ent: seen.append(ent)
    run(ad._retry_fill({"id": 9, "orderId": 777}))
    assert len(seen) == 1


def test_the_lost_oso_look_returns_its_own_none_seen_flag(tmp_path):
    # the flag rides back with the result, not on the adapter: two calls cannot overwrite each other
    ad = mkadapter(tmp_path, lambda e, q, b: [] if e == "order/list" else tradovate_like(e, q, b))
    sent = dt.datetime.now(dt.timezone.utc)
    assert run(ad._find_lost_oso(BUY_MKT, "NQZ6", sent)) == (None, True)
    assert not hasattr(ad, "_lost_none")
