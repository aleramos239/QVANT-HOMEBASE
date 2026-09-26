"""Chart trading's adapter surface: the entity listener, the position/cash
caches, symbol-scoped flatten/cancel. No network: the fake socket from
tests/test_tradovate.py answers every frame."""
from __future__ import annotations

import asyncio
import json

from homebase import symbols
from homebase.broker.tradovate import TradovateAdapter
from tests.test_tradovate import (BUY_STOP, collect_fills, fill_push, mkadapter, run,
                                  tradovate_like)

NQC, ESC = symbols.resolve_contract("NQ"), symbols.resolve_contract("ES")
CID = {NQC: 3267315, ESC: 3267400}
ME, OTHER = 66121477, 99


def broker(positions=None, cash=None, place=None):
    """An answer function + the list of (endpoint, query, body) it saw.
    positions=None -> position/list answers 404 (unreadable)."""
    sent = []

    def answer(endpoint, query, body):
        sent.append((endpoint, query, json.loads(body) if body else None))
        if endpoint == "contract/find":
            name = query[len("name="):]
            return {"id": CID[name], "name": name} if name in CID else None
        if endpoint == "contract/item":
            cid = int(query[len("id="):])
            name = {v: k for k, v in CID.items()}.get(cid)
            return {"id": cid, "name": name} if name else None
        if endpoint == "position/list":
            return positions
        if endpoint == "cashBalance/list":
            return cash if cash is not None else []
        if endpoint == "order/placeorder":
            return place if place is not None else {"orderId": 900}
        if endpoint == "order/cancelorder":
            return {}
        return None

    return answer, sent


def push(ad, et, ent):
    ad._on_ws_event({"e": "props", "d": {"entityType": et, "entity": ent}})


def working(oid, cid, acct=ME, status="Working", action="Sell"):
    return {"id": oid, "accountId": acct, "contractId": cid, "ordStatus": status, "action": action}


# --- the listener ------------------------------------------------------------
def test_listener_hears_this_accounts_entities_after_the_cache_took_them(tmp_path):
    ad = mkadapter(tmp_path, tradovate_like)
    ad._contracts[3267315] = "NQZ6"
    got = []
    ad.add_listener(lambda et, ent: got.append((et, dict(ent))))
    push(ad, "order", working(5, 3267315, action="Buy"))
    push(ad, "order", working(6, 3267315, acct=OTHER))
    push(ad, "orderVersion", {"id": 50, "orderId": 5, "orderType": "Limit", "price": 100.0, "orderQty": 2})
    push(ad, "orderVersion", {"id": 60, "orderId": 6, "orderType": "Limit", "price": 1.0, "orderQty": 1})
    push(ad, "position", {"id": 7, "accountId": ME, "contractId": 3267315, "netPos": 2, "netPrice": 100.0})
    push(ad, "position", {"id": 8, "accountId": OTHER, "contractId": 3267315, "netPos": 9})
    push(ad, "cashBalance", {"id": 1, "accountId": ME, "amount": 5.0, "realizedPnL": 1.5})
    push(ad, "cashBalance", {"id": 2, "accountId": OTHER, "amount": 7.0})
    push(ad, "contract", {"id": 3267315, "name": "NQZ6"})          # not a listened type
    assert [et for et, _ in got] == ["order", "orderVersion", "position", "cashBalance"]
    assert got[0][1] == ad._orders[5]                                 # the cache took it first
    v = ad.trade_view()
    assert v["positions"] == [{"contract_id": 3267315, "symbol": "NQZ6", "net": 2, "avg_price": 100.0}]
    assert v["orders"] == [{"order_id": "5", "symbol": "NQZ6", "side": "Buy", "type": "Limit",
                            "qty": 2, "price": 100.0, "stop_price": None, "status": "Working"}]
    assert (v["balance"], v["realized_pnl"]) == (5.0, 1.5)


def test_the_fill_path_is_unchanged_by_listeners(tmp_path):
    pushes = [fill_push(663695020149, "Buy", 3, 30231.5, 7001),
              fill_push(663695020149, "Buy", 3, 30231.5, 7001)]         # a duplicate push
    plain = collect_fills(mkadapter(tmp_path / "a", tradovate_like), list(pushes), place=BUY_STOP)
    ad = mkadapter(tmp_path / "b", tradovate_like)
    heard = []
    ad.add_listener(lambda et, ent: heard.append((et, ent.get("id"))))
    ad.add_listener(lambda et, ent: 1 / 0)                           # a broken listener changes nothing
    watched = collect_fills(ad, list(pushes), place=BUY_STOP)

    def key(fs):
        return [(f.account_id, f.symbol, f.side, f.qty, f.price, f.raw.get("orderId")) for f in fs]

    assert key(watched) == key(plain) and len(plain) == 1
    assert heard == [("fill", 7001)]           # our own order's fill, announced once


def test_a_fill_is_enqueued_before_any_listener_runs(tmp_path):
    ad = mkadapter(tmp_path, tradovate_like)
    ad._on_fill = lambda ev: None                 # observed as master
    seen_q = []
    ad.add_listener(lambda et, ent: seen_q.append(ad._fill_q.qsize()))
    ad._order_symbols[663695020149] = "NQZ6"
    ad._on_ws_event(fill_push(663695020149, "Buy", 3, 30231.5, 7001))
    assert seen_q == [1]


def test_unobserved_fills_are_still_deduped_and_never_enqueued(tmp_path):
    ad = mkadapter(tmp_path, tradovate_like)
    ad._order_symbols[663695020149] = "NQZ6"
    heard = []
    ad.add_listener(lambda et, ent: heard.append(et))
    ad._on_ws_event(fill_push(663695020149, "Buy", 3, 30231.5, 7001))
    ad._on_ws_event(fill_push(663695020149, "Buy", 3, 30231.5, 7001))
    assert ad._fill_q.qsize() == 0 and 7001 in ad._seen_fills and heard == ["fill"]


# --- P3: an order's contract may stay unresolved ------------------------------
def test_order_pushes_resolve_an_unknown_contract_in_the_background(tmp_path):
    answer, sent = broker()
    ad = mkadapter(tmp_path, answer)
    got = []
    ad.add_listener(lambda et, ent: got.append((et, ent.get("id"))))

    async def go():
        push(ad, "order", working(21, CID[ESC], action="Buy"))
        push(ad, "orderVersion", {"id": 210, "orderId": 21, "contractId": CID[ESC],
                                  "orderType": "Limit", "price": 5.0, "orderQty": 1})
        for _ in range(100):
            if CID[ESC] in ad._contracts:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.01)

    run(go())
    assert ad._contracts[CID[ESC]] == ESC
    assert [e for e, _, _ in sent].count("contract/item") == 1       # one lookup, not one per push
    assert ad.trade_view()["orders"][0]["symbol"] == ESC
    assert got[-1] == ("order", 21)                                   # re-announced once named


def test_our_own_order_is_named_from_what_we_placed_without_a_lookup(tmp_path):
    answer, sent = broker()
    ad = mkadapter(tmp_path, answer)
    ad._order_symbols[22] = NQC

    async def go():
        push(ad, "order", working(22, 555))
        await asyncio.sleep(0.02)

    run(go())
    assert ad._contracts[555] == NQC
    assert not any(e == "contract/item" for e, _, _ in sent)


def test_an_unresolvable_order_never_breaks_the_view(tmp_path):
    answer, _ = broker()
    ad = mkadapter(tmp_path, answer)
    ad._orders.update({31: working(31, 777),                              # contract/item 404s
                       32: {"id": 32, "accountId": ME, "ordStatus": "Working"}})
    ad._order_symbols[32] = NQC                                           # ours, contract id unknown

    async def go():
        push(ad, "order", working(31, 777))
        await asyncio.sleep(0.02)
        return ad.trade_view()

    v = run(go())
    assert [(o["order_id"], o["symbol"]) for o in v["orders"]] == [("31", None), ("32", NQC)]
    assert ad._contract_lookups == set()                                  # a later push may retry


# --- the caches ----------------------------------------------------------------
def test_seed_reads_this_accounts_positions_and_cash_and_resolves_names(tmp_path):
    answer, _ = broker(
        positions=[{"accountId": ME, "contractId": CID[NQC], "netPos": 2, "netPrice": 30100.5},
                   {"accountId": ME, "contractId": CID[ESC], "netPos": 0},
                   {"accountId": OTHER, "contractId": CID[ESC], "netPos": 1}],
        cash=[{"accountId": OTHER, "amount": 1.0},
              {"accountId": ME, "amount": 50123.5, "realizedPnL": -80.0}])
    ad = mkadapter(tmp_path, answer)
    got = []
    ad.add_listener(lambda et, ent: got.append(et))
    run(ad._seed_caches())
    v = ad.trade_view()
    assert v["seeded"] is True and (v["balance"], v["realized_pnl"]) == (50123.5, -80.0)
    assert v["positions"] == [{"contract_id": CID[NQC], "symbol": NQC, "net": 2, "avg_price": 30100.5}]
    assert got[-1] == "sync"


def backoff_recorder(ad, stop_after=None):
    """Replace the seed's sleep: record each delay; optionally 'disconnect'
    the adapter after `stop_after` sleeps."""
    delays = []

    async def fake_sleep(s):
        delays.append(s)
        if stop_after is not None and len(delays) >= stop_after:
            ad._connected = False

    ad._seed_sleep = fake_sleep
    return delays


def test_a_failed_seed_leaves_the_caches_unseeded_and_is_audited(tmp_path):
    answer, _ = broker(positions=None)                     # position/list -> 404
    ad = mkadapter(tmp_path, answer)
    events = []
    ad.audit = events.append
    backoff_recorder(ad, stop_after=1)                     # disconnects during the first backoff
    run(ad._seed_caches())
    assert ad.caches_seeded is False and ad.trade_view()["seeded"] is False
    assert events and events[-1]["event"] == "cache_seed_error"


def test_the_seed_retries_with_backoff_until_both_reads_land(tmp_path):
    fails = {"position/list": 2}
    base, sent = broker(positions=[{"accountId": ME, "contractId": CID[NQC], "netPos": 1}],
                        cash=[{"accountId": ME, "amount": 9.0}])

    def answer(endpoint, query, body):
        if fails.get(endpoint, 0) > 0:
            fails[endpoint] -= 1
            sent.append((endpoint, query, None))
            return None
        return base(endpoint, query, body)

    ad = mkadapter(tmp_path, answer)
    events, got = [], []
    ad.audit = events.append
    ad.add_listener(lambda et, ent: got.append(et))
    delays = backoff_recorder(ad)
    run(ad._seed_caches())
    assert delays == [1, 2]
    assert ad.caches_seeded is True and ad.trade_view()["balance"] == 9.0
    assert [e["event"] for e in events] == ["cache_seed_error", "cache_seed_error"]
    assert got == ["sync"]


def test_a_seed_retry_rereads_only_the_part_that_failed(tmp_path):
    fails = {"cashBalance/list": 1}
    base, sent = broker(positions=[], cash=[{"accountId": ME, "amount": 3.0}])

    def answer(endpoint, query, body):
        if fails.get(endpoint, 0) > 0:
            fails[endpoint] -= 1
            sent.append((endpoint, query, None))
            return None
        return base(endpoint, query, body)

    ad = mkadapter(tmp_path, answer)
    backoff_recorder(ad)
    run(ad._seed_caches())
    eps = [e for e, _, _ in sent]
    assert ad.caches_seeded is True
    assert eps.count("position/list") == 1 and eps.count("cashBalance/list") == 2


def test_the_seed_backoff_doubles_to_a_60s_cap_and_stops_on_disconnect(tmp_path):
    answer, _ = broker(positions=None)
    ad = mkadapter(tmp_path, answer)
    delays = backoff_recorder(ad, stop_after=9)
    run(ad._seed_caches())
    assert delays == [1, 2, 4, 8, 16, 32, 60, 60, 60]
    assert ad.caches_seeded is False


class SyncWS:
    """Stands in for TradovateWS during reconnect(): no network."""

    def __init__(self, token=None, environment="demo"):
        self.event_handlers, self.connected = [], True

    async def connect(self): ...
    async def authorize(self): ...
    async def close(self): ...

    async def user_sync(self):
        return {"accounts": [{"id": ME, "name": "APEX"}], "contracts": [{"id": CID[NQC], "name": NQC}]}

    async def position_list(self):
        return [{"accountId": ME, "contractId": CID[NQC], "netPos": -1, "netPrice": 5.0}]

    async def cash_balance_list(self):
        return [{"accountId": ME, "amount": 7.0}]


def test_reconnect_reseeds_the_caches_in_the_background(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.broker.tradovate.TradovateWS", SyncWS)
    ad = TradovateAdapter("acct", env="demo", keyring_key="k", state_dir=tmp_path,
                          account_selector={"account_name": "APEX"})
    monkeypatch.setattr(ad._auth, "ensure_valid", lambda *a: None)

    async def go():
        await ad.reconnect()
        for _ in range(100):
            if ad.caches_seeded:
                break
            await asyncio.sleep(0.01)
        v = ad.trade_view()
        await ad.close()
        return v

    v = run(go())
    assert v["seeded"] is True and v["pinned"] is True and v["balance"] == 7.0
    assert v["positions"][0]["net"] == -1 and ad.caches_seeded is False   # close() clears it


class FailingSeedWS(SyncWS):
    """The position read never succeeds while this socket lives."""

    async def position_list(self):
        raise RuntimeError("position/list failed: status=404")


def test_a_failing_seed_never_blocks_reconnect_and_dies_with_close(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.broker.tradovate.TradovateWS", FailingSeedWS)
    ad = TradovateAdapter("acct", env="demo", keyring_key="k", state_dir=tmp_path,
                          account_selector={"account_name": "APEX"})
    monkeypatch.setattr(ad._auth, "ensure_valid", lambda *a: None)

    async def go():
        await asyncio.wait_for(ad.reconnect(), timeout=1)
        await asyncio.sleep(0.05)
        task = ad._seed_task
        running = not task.done()
        await ad.close()
        await asyncio.sleep(0)
        return running, task

    running, task = run(go())
    assert running is True and task.cancelled() and ad.caches_seeded is False


# --- symbol-scoped flatten / cancel ----------------------------------------------
def orders_nq_es(ad):
    ad._contracts.update({CID[NQC]: NQC, CID[ESC]: ESC})
    ad._orders.update({1: working(1, CID[NQC]), 2: working(2, CID[ESC], action="Buy"),
                       3: working(3, CID[NQC], acct=OTHER, action="Buy"),
                       4: working(4, CID[NQC], status="Filled", action="Buy"),
                       5: {"id": 5, "accountId": ME, "ordStatus": "Working"}})   # contract unknown


def test_flatten_symbol_markets_out_then_cancels_only_that_contract(tmp_path):
    answer, sent = broker(positions=[{"accountId": ME, "contractId": CID[NQC], "netPos": 3},
                                     {"accountId": OTHER, "contractId": CID[NQC], "netPos": 5}])
    ad = mkadapter(tmp_path, answer)
    orders_nq_es(ad)
    r = run(ad.flatten_symbol("NQ"))
    assert r.raw["net_before"] == 3 and r.raw["market"]["ok"] is True
    assert r.ok is False and r.error == "1 working order(s) with an unknown contract left working"
    eps = [e for e, _, _ in sent]
    placed = [b for e, _, b in sent if e == "order/placeorder"]
    assert len(placed) == 1
    assert (placed[0]["action"], placed[0]["orderQty"], placed[0]["symbol"],
            placed[0]["orderType"], placed[0]["accountId"]) == ("Sell", 3, NQC, "Market", ME)
    assert [b["orderId"] for e, _, b in sent if e == "order/cancelorder"] == [1]
    assert eps.index("order/placeorder") < eps.index("order/cancelorder")


def test_flatten_symbol_refused_market_cancels_nothing(tmp_path):
    answer, sent = broker(positions=[{"accountId": ME, "contractId": CID[NQC], "netPos": -2}],
                          place={"failureReason": "Risk", "failureText": "Insufficient margin"})
    ad = mkadapter(tmp_path, answer)
    orders_nq_es(ad)
    r = run(ad.flatten_symbol("NQ"))
    assert r.ok is False and r.error == "flatten order refused: Insufficient margin — orders left working"
    assert not any(e == "order/cancelorder" for e, _, _ in sent)


def test_flatten_symbol_unreadable_position_does_nothing(tmp_path):
    answer, sent = broker(positions=None)
    ad = mkadapter(tmp_path, answer)
    orders_nq_es(ad)
    r = run(ad.flatten_symbol("NQ"))
    assert r.ok is False and r.error.startswith("position unreadable")
    assert not any(e in ("order/placeorder", "order/cancelorder") for e, _, _ in sent)


def test_cancel_symbol_touches_only_this_accounts_working_orders_in_that_contract(tmp_path):
    answer, sent = broker()
    ad = mkadapter(tmp_path, answer)
    orders_nq_es(ad)
    r = run(ad.cancel_symbol("ES"))
    assert r.raw == {"cancelled": 1, "ids": ["2"], "unknown_contract": 1}
    assert r.ok is False and r.error == "1 working order(s) with an unknown contract left working"
    assert [b["orderId"] for e, _, b in sent if e == "order/cancelorder"] == [2]


def test_reconnect_cancels_the_old_sockets_seed_before_anything_else(tmp_path, monkeypatch):
    class BrokenWS(SyncWS):
        async def user_sync(self):
            raise RuntimeError("user/syncrequest failed")

    monkeypatch.setattr("homebase.broker.tradovate.TradovateWS", BrokenWS)
    ad = TradovateAdapter("acct", env="demo", keyring_key="k", state_dir=tmp_path,
                          account_selector={"account_name": "APEX"})
    monkeypatch.setattr(ad._auth, "ensure_valid", lambda *a: None)

    async def go():
        old = asyncio.create_task(asyncio.sleep(3600))   # the old socket's seed, mid-read
        ad._seed_task = old
        try:
            await ad.reconnect()                        # fails after the socket swap
        except RuntimeError:
            pass
        await asyncio.sleep(0)
        return old

    old = run(go())
    assert old.cancelled() and ad.caches_seeded is False


# --- fix round 1 -------------------------------------------------------------------
def test_a_position_push_during_the_seed_read_survives_the_older_snapshot(tmp_path):
    holder = {}
    base, _ = broker(positions=[{"accountId": ME, "contractId": CID[NQC], "netPos": 0},
                                {"accountId": ME, "contractId": CID[ESC], "netPos": 2}],
                     cash=[{"accountId": ME, "amount": 100.0}])

    def answer(endpoint, query, body):
        ad = holder["ad"]
        if endpoint == "position/list":          # the NQ fill lands while the read is in flight
            push(ad, "position", {"id": 7, "accountId": ME, "contractId": CID[NQC],
                                  "netPos": 1, "netPrice": 30000.0})
        if endpoint == "cashBalance/list":
            push(ad, "cashBalance", {"id": 1, "accountId": ME, "amount": 95.0})
        return base(endpoint, query, body)

    ad = holder["ad"] = mkadapter(tmp_path, answer)
    run(ad._seed_caches())
    v = ad.trade_view()
    assert {p["symbol"]: p["net"] for p in v["positions"]} == {NQC: 1, ESC: 2}
    assert v["balance"] == 95.0


def test_a_push_before_the_seed_read_is_replaced_by_the_snapshot(tmp_path):
    answer, _ = broker(positions=[{"accountId": ME, "contractId": CID[NQC], "netPos": 0}])
    ad = mkadapter(tmp_path, answer)
    push(ad, "position", {"id": 7, "accountId": ME, "contractId": CID[NQC], "netPos": 4})
    push(ad, "cashBalance", {"id": 1, "accountId": ME, "amount": 1.0})
    run(ad._seed_caches())
    assert ad.trade_view()["positions"] == [] and ad.trade_view()["balance"] is None


def test_flatten_never_cancels_its_own_market_order(tmp_path):
    holder = {}
    base, sent = broker(positions=[{"accountId": ME, "contractId": CID[NQC], "netPos": 2}],
                        place={"orderId": 900})

    def answer(endpoint, query, body):
        if endpoint == "order/placeorder":       # its push is cached before the reply returns
            push(holder["ad"], "order", working(900, CID[NQC], status="PendingNew"))
        return base(endpoint, query, body)

    ad = holder["ad"] = mkadapter(tmp_path, answer)
    ad._contracts.update({CID[NQC]: NQC, CID[ESC]: ESC})
    ad._orders.update({1: working(1, CID[NQC]), 2: working(2, CID[ESC], action="Buy")})
    r = run(ad.flatten_symbol("NQ"))
    assert r.ok is True and r.raw["market"]["order_id"] == "900"
    assert [b["orderId"] for e, _, b in sent if e == "order/cancelorder"] == [1]


def test_cancel_symbol_cancels_our_own_unnamed_order_by_what_we_placed(tmp_path):
    answer, sent = broker()
    ad = mkadapter(tmp_path, answer)
    ad._contracts.update({CID[NQC]: NQC, CID[ESC]: ESC})
    ad._orders.update({6: {"id": 6, "accountId": ME, "ordStatus": "Working"},    # ours, NQ
                       7: {"id": 7, "accountId": ME, "ordStatus": "Working"},    # ours, ES
                       2: working(2, CID[ESC], action="Buy")})
    ad._order_symbols.update({6: NQC, 7: ESC})
    r = run(ad.cancel_symbol("ES"))
    assert r.ok is True and (r.raw["cancelled"], r.raw["unknown_contract"]) == (2, 0)
    assert sorted(r.raw["ids"]) == ["2", "7"]
    assert sorted(b["orderId"] for e, _, b in sent if e == "order/cancelorder") == [2, 7]


def test_close_cancels_pending_contract_lookups_so_a_reconnect_can_retry(tmp_path):
    answer, _ = broker()
    ad = mkadapter(tmp_path, answer)

    async def go():
        push(ad, "order", working(21, CID[ESC]))
        tasks = set(ad._lookup_tasks)
        await ad.close()
        await asyncio.sleep(0)
        return tasks

    tasks = run(go())
    assert len(tasks) == 1 and all(t.cancelled() for t in tasks)
    assert ad._lookup_tasks == set() and ad._contract_lookups == set()
