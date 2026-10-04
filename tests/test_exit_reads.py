"""A position read asks the broker for the POSITION every time and for the contract's id only the first
time (TradovateAdapter.get_net_position over contract_id's cache): one round trip less on every flatten,
kill, reverse and exits check -- and never a position the broker did not just report.
Real adapter, fake wire (tests/test_tradovate.py); the chart desk and the engine on top of it."""
from __future__ import annotations

import asyncio
import json

import pytest

from homebase.engine import Engine
from tests.test_adapter_caches import CID, ME, OTHER, broker, push, working
from tests.test_engine import Clock, mkcfg
from tests.test_tradovate import fill_push, mkadapter, run
from tests.trading_util import NQC, journal, mkdesk, wire_adapter

NQ = CID[NQC]


def eps(sent) -> list[str]:
    return [e for e, _, _ in sent]


def long(n: int) -> list[dict]:
    return [{"accountId": ME, "contractId": NQ, "netPos": n}]


# --- the adapter ------------------------------------------------------------------------------------
def test_the_position_is_read_every_time_the_contract_only_the_first(tmp_path):
    positions = long(3)
    answer, sent = broker(positions=positions)
    ad = mkadapter(tmp_path, answer)
    assert run(ad.get_net_position("NQ")) == 3
    assert eps(sent) == ["contract/find", "position/list"]            # the first read finds the contract
    positions[0]["netPos"] = -1                                       # it changed at the broker
    assert run(ad.get_net_position("NQ")) == -1                       # never the value read before
    assert run(ad.get_net_position(NQC)) == -1                        # root or contract: the same id
    assert eps(sent)[2:] == ["position/list", "position/list"]        # one round trip each, not two


def test_a_contract_the_socket_already_named_costs_no_lookup(tmp_path):
    answer, sent = broker(positions=long(2) + [{"accountId": OTHER, "contractId": NQ, "netPos": 9}])
    ad = mkadapter(tmp_path, answer)
    push(ad, "contract", {"id": NQ, "name": NQC})                     # a contract push
    assert run(ad.get_net_position("NQ")) == 2 and eps(sent) == ["position/list"]
    # ... or an order WE placed: its push names the contract it was placed on
    answer, sent = broker(positions=long(-4), place={"orderId": 900})
    ad = mkadapter(tmp_path, answer)
    from homebase.broker.base import OrderRequest
    assert run(ad.place_order(OrderRequest(symbol="NQ", side="Sell", qty=4))).ok
    push(ad, "order", working(900, NQ))
    assert run(ad.get_net_position("NQ")) == -4
    assert eps(sent) == ["order/placeorder", "position/list"]


def test_an_unreadable_position_is_never_flat_with_the_contract_cached_or_not(tmp_path):
    answer, sent = broker(positions=None)                             # position/list answers 404
    ad = mkadapter(tmp_path, answer)
    for _ in range(2):                                                # cold, then with the id cached
        with pytest.raises(RuntimeError, match="position/list failed"):
            run(ad.get_net_position("NQ"))
    assert eps(sent) == ["contract/find", "position/list", "position/list"]
    answer, sent = broker(positions=long(3))
    ad = mkadapter(tmp_path, answer)
    with pytest.raises(RuntimeError, match="contract/find failed"):   # a contract the broker does not know
        run(ad.get_net_position("NQH9"))
    assert eps(sent) == ["contract/find"]                             # ... and nothing is cached for it
    with pytest.raises(RuntimeError):
        run(ad.get_net_position("NQH9"))
    assert eps(sent) == ["contract/find", "contract/find"]
    ad._ws = None
    with pytest.raises(RuntimeError, match="adapter not connected"):
        run(ad.get_net_position("NQ"))


def test_a_symbol_flatten_is_the_read_the_market_out_and_the_cancels(tmp_path):
    answer, sent = broker(positions=long(3))
    ad = mkadapter(tmp_path, answer)
    ad._orders[1] = working(1, NQ)
    assert run(ad.flatten_symbol("NQ")).ok
    assert eps(sent) == ["contract/find", "position/list", "order/placeorder", "order/cancelorder"]
    del sent[:]
    ad._orders[1] = working(1, NQ)
    assert run(ad.flatten_symbol("NQ")).ok                            # from then on: no lookup at all
    assert eps(sent) == ["position/list", "order/placeorder", "order/cancelorder"]


# --- the engine's flatten (the Kill, the clock, the strategy flatten) on the wire ---------------------
def test_the_engines_flatten_reads_the_position_once_and_never_looks_the_contract_up(tmp_path):
    """The bot's own orders name their contract when their pushes come in, so by the time anything is
    flattened the id is known: position/list, the market-out, the cancels."""
    ids = iter([(101, 102, 103), (201, 202, 203)])
    sent = []
    net = {"n": 0}

    def wire(endpoint, query, body):
        sent.append((endpoint, query, json.loads(body) if body else None))
        if endpoint == "order/placeoso":
            o, s1, s2 = next(ids)
            return {"orderId": o, "oso1Id": s1, "oso2Id": s2}
        if endpoint == "order/placeorder":
            net["n"] = 0
            return {"orderId": 300}
        if endpoint == "position/list":
            return long(net["n"])
        return {} if endpoint in ("order/cancelorder", "order/modifyorder") else None

    ad = mkadapter(tmp_path, wire)
    cfg = mkcfg()
    cfg.accounts = {"acct": cfg.accounts["main"]}
    cfg.book = {"nq930": [{"account": "acct", "qty": 3}]}
    eng = Engine(cfg, {"acct": ad}, now_fn=Clock(), root=tmp_path)

    async def scenario():
        await ad.observe_fills(eng.on_fill)
        assert (await eng.handle_alert({"strategy": "nq930", "upper": 30231.5, "lower": 30211.5}))["ok"]
        for oid in (101, 201):                                        # the entries' own order pushes
            push(ad, "order", working(oid, NQ, action="Buy" if oid == 101 else "Sell"))
        ad._on_ws_event(fill_push(101, "Buy", 3, 30231.5, 9001))
        for _ in range(100):
            if eng._state("nq930", "acct").status == "live":
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.02)
        net["n"] = 3
        del sent[:]
        out = await eng.flatten_today()
        await ad.close()
        return out

    out = run(scenario())
    assert out["nq930@acct"][0] == "market Sell 3: ok"
    assert eps(sent) == ["position/list", "order/placeorder"] + ["order/cancelorder"] * 6
    assert sent[1][2]["orderQty"] == 3 and sent[1][2]["action"] == "Sell"
    assert "contract/find" not in eps(sent)


# --- the chart's Reverse ------------------------------------------------------------------------------
def reverse_desk(tmp_path, reads):
    """The chart desk over a real adapter whose position/list answers the next of `reads` each time."""
    desk, eng, ads, _, mono, _ = mkdesk(tmp_path, book={})
    desk.mono = mono
    seq, sent, ids = iter(reads), [], iter(range(900, 999))

    def wire(endpoint, query, body):
        sent.append((endpoint, query, json.loads(body) if body else None))
        if endpoint == "contract/find":
            return {"id": NQ, "name": query[len("name="):]}
        if endpoint == "position/list":
            return long(next(seq))
        if endpoint == "order/placeorder":
            return {"orderId": next(ids)}
        return {} if endpoint == "order/cancelorder" else None

    ads["a1"] = wire_adapter(tmp_path, wire)
    return desk, ads["a1"], sent


def reverse(desk, cid="r1"):
    return run(desk.reverse({"client_id": cid, "accounts": ["a1"], "root": "NQ"}))["results"]["a1"]


def test_a_reverse_is_two_position_reads_the_close_and_the_open(tmp_path):
    """Before: contract/find + position/list, the same again inside the flatten, the close, one more
    contract/find for the cancels, the open -- 7 round trips. Now 5 the first time, 4 after."""
    desk, ad, sent = reverse_desk(tmp_path, [2, 2, -2, -2])
    assert reverse(desk)["ok"]
    assert eps(sent) == ["contract/find", "position/list", "position/list",
                         "order/placeorder", "order/placeorder"]
    del sent[:]
    desk.mono.t += 11                                                 # the first open is confirmed by now
    assert reverse(desk, "r2")["ok"]                                  # short 2 now: back to long
    assert eps(sent) == ["position/list", "position/list", "order/placeorder", "order/placeorder"]
    close, open_ = [b for e, _, b in sent if e == "order/placeorder"]
    assert (close["action"], close["orderQty"], open_["action"], open_["orderQty"]) == ("Buy", 2, "Buy", 2)
    steps = [(e["step"], e["ok"]) for e in journal(tmp_path) if e["event"] == "manual_reverse"]
    assert steps == [("flatten", True), ("open", True)] * 2


def test_a_reverse_closes_what_the_broker_reports_at_the_close_not_what_it_read_before(tmp_path):
    """The position's own target took one contract between the reverse's read (+2) and the flatten's
    own read (+1). That second read is KEPT: the close sells 1 -- selling the 2 read before would leave
    the account short before the open even goes out."""
    desk, ad, sent = reverse_desk(tmp_path, [2, 1])
    assert reverse(desk)["ok"]
    close, open_ = [b for e, _, b in sent if e == "order/placeorder"]
    assert (close["action"], close["orderQty"], close["text"]) == ("Sell", 1, "homebase:chart-flat")
    assert (open_["action"], open_["orderQty"], open_["text"]) == ("Sell", 2, "homebase:chart-reverse")
    assert eps(sent).count("position/list") == 2
    flat = next(e for e in journal(tmp_path) if e["event"] == "manual_reverse" and e["step"] == "flatten")
    assert flat["net_before"] == 2 and flat["ok"]


def test_a_reverse_that_finds_the_position_gone_at_the_close_sells_nothing_there(tmp_path):
    desk, ad, sent = reverse_desk(tmp_path, [2, 0])                   # its stop closed it meanwhile
    reverse(desk)
    placed = [b for e, _, b in sent if e == "order/placeorder"]
    assert [b["text"] for b in placed] == ["homebase:chart-reverse"]  # no close order: nothing to close
