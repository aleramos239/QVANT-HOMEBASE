from __future__ import annotations

import asyncio
import datetime as dt
import time

import httpx
import pytest

from homebase.broker import alphatrader
from homebase.broker import alphatrader_proto as proto
from homebase.broker.alphatrader import AlphaTraderAdapter
from homebase.broker.alphatrader_auth import AtrSession
from homebase.broker.base import AccountNotOnLogin, OrderRequest

KEY = "atr:o@x.com"
ACCOUNTS = [{"accountId": "A1", "accountNumber": "1001", "accountName": "AF-50K-1", "displayName": "Alpha 50K Eval"},
            {"accountId": "A2", "accountNumber": "1002", "accountName": "AF-50K-2", "displayName": "Alpha 50K"}]
TODAY = dt.date(2026, 10, 30)          # NQ's front month: Z26
ALL = {"subscribe": proto.ALL_UPDATES, "subscribeAllAccounts": True, "uplMode": proto.AVERAGE}
NQZ26, NQH27, ESZ26 = "XCME_Eq NQ (Z26)", "XCME_Eq NQ (H27)", "XCME_Eq ES (Z26)"


class FakeSocket:
    """Stands in for AtrSocket: start() answers the login (accounts) and runs on_up; tests push events with push()."""
    made: list["FakeSocket"] = []
    accounts = ACCOUNTS

    def __init__(self, session, on_event, *, on_up=None, on_taken=None, url=None):
        self.session, self.on_event, self.on_up, self.on_taken = session, on_event, on_up, on_taken
        self.up, self.starts, self.stopped = False, 0, False
        self.sent: list[tuple[str, dict]] = []
        self.reply = None           # (payload, data) -> [(event, data)]: T4's answer, pushed right after the send
        FakeSocket.made.append(self)

    async def start(self):
        self.starts += 1
        if self.up:
            return
        self.on_event("loginResponse", {"sessionId": "S1", "accounts": self.accounts})
        self.up = True
        await self.on_up()

    async def stop(self):
        self.up, self.stopped = False, True

    async def send(self, payload, data):
        if not self.up:
            raise ConnectionError("down")
        self.sent.append((payload, data))
        for name, d in (self.reply(payload, data) if self.reply else []):
            asyncio.get_running_loop().call_soon(self.on_event, name, d)

    def push(self, name, data):
        self.on_event(name, data)


@pytest.fixture(autouse=True)
def fake_socket(monkeypatch):
    FakeSocket.made = []
    monkeypatch.setattr(alphatrader, "AtrSocket", FakeSocket)

    async def pause(s):
        await asyncio.sleep(0)
    monkeypatch.setattr(alphatrader, "_pause", pause)


def session(rows=(), calls=None):
    """A real AtrSession holding a token; /market/symbols/ answers `rows` (each call is recorded)."""
    def alpha(req: httpx.Request):
        assert req.url.path == "/api/v1/market/symbols/"
        if calls is not None:
            calls.append(dict(req.url.params))
        return httpx.Response(200, json={"results": list(rows)})
    s = AtrSession(KEY, http=httpx.AsyncClient(transport=httpx.MockTransport(alpha)))
    s._access, s.expires_at = "tok", time.time() + 3600
    return s


def adapter(s, name="AF-50K-1", acct="d1"):
    return AlphaTraderAdapter(acct, keyring_key=KEY, account_name=name, session=s)


def pos(acct, market, root, buys=0, sells=0):
    row = {"accountId": acct, "contractId": root, "marketId": market}
    if buys:
        row["buys"] = buys          # proto3: a 0 is not on the wire
    if sells:
        row["sells"] = sells
    return row


def snapshot(acct, *messages):
    return {"accountId": acct, "messages": list(messages)}


def test_connect_picks_the_named_account_and_a_missing_name_raises_AccountNotOnLogin():
    async def go():
        s = session()
        a = adapter(s, "af-50k-2")                     # by name, any case
        await a.connect()
        assert a.connected and a.broker_key == ("alphatrader", "A2") and a.pinned_ok
        b = adapter(s, "A1", "d2")                     # or by id
        await b.connect()
        assert b.broker_key == ("alphatrader", "A1")
        c = adapter(s, "AF-NOPE", "d3")
        with pytest.raises(AccountNotOnLogin) as e:
            await c.connect()
        assert "AF-NOPE" in str(e.value) and not c.connected
        assert c not in s.adapters and s.adapters == [a, b]
        probe = adapter(s, "", "probe")                # a probe only lists
        await probe.connect()
        assert probe.connected and probe.broker_key == "probe"
        assert [r["id"] for r in probe.list_accounts()] == ["A1", "A2"]
    asyncio.run(go())


def test_list_accounts_marks_practice_rows():
    async def go():
        s = session()
        a = adapter(s, "")
        await a.connect()
        sock = FakeSocket.made[0]
        sock.push("accountSnapshot", snapshot("A2", {"accountDetails": {"accountId": "A2", "groupName": "Practice Accounts",
                                                                        "enabled": 1}}))
        sock.push("accountDetails", {"accountId": "A1"})       # enabled 0 (dropped on the wire): not active
        return a.list_accounts()
    rows = asyncio.run(go())
    assert rows == [{"id": "A1", "name": "Alpha 50K Eval", "active": False, "practice": True},     # "eval" in the name
                    {"id": "A2", "name": "Alpha 50K", "active": True, "practice": True}]          # "practice" in the group


def test_two_adapters_on_one_login_share_one_socket_and_each_keeps_its_own_account_events():
    async def go():
        s = session()
        a, b = adapter(s, "AF-50K-1", "d1"), adapter(s, "AF-50K-2", "d2")
        await a.connect()
        await b.connect()
        assert len(FakeSocket.made) == 1 and s.socket is FakeSocket.made[0]
        sock = s.socket
        assert sock.sent == [("accountSubscribe", ALL)]        # b joined an open socket: every snapshot again
        sock.push("accountSnapshot", snapshot("A1", {"accountPosition": pos("A1", NQZ26, "NQ", buys=2)},
                                              {"accountUpdate": {"accountId": "A1", "balance": 50100.0}}))
        sock.push("accountSnapshot", snapshot("A2", {"accountPosition": pos("A2", NQZ26, "NQ", sells=1)},
                                              {"accountUpdate": {"accountId": "A2", "balance": 49000.0}}))
        sock.push("accountPosition", pos("A2", ESZ26, "ES", buys=1))
        assert await a.get_net_position("NQ") == 2 and await b.get_net_position("NQ") == -1
        assert await a.get_net_position("ES") == 0 and await b.get_net_position("ES") == 1
        assert await a.get_balance() == {"amount": 50100.0} and await b.get_balance() == {"amount": 49000.0}
        await a.close()
        assert not sock.stopped and s.adapters == [b]          # the socket stops with its last adapter
        await a.connect()                                       # back on the open socket: its book was missed meanwhile
        assert sock.sent[-1] == ("accountSubscribe", ALL)
        with pytest.raises(RuntimeError, match="position unknown"):
            await a.get_net_position("NQ")
        await a.close()
        await b.close()
        assert sock.stopped and s.socket is None
    asyncio.run(go())


def test_market_id_resolves_the_front_month_and_caches_it():
    calls: list = []
    rows = [{"contract_id": "NQ", "exchange_id": "CME_Eq", "market_id": NQH27},
            {"contract_id": "MNQ", "exchange_id": "CME_Eq", "market_id": "XCME_Eq MNQ (Z26)"},
            {"contract_id": "NQ", "exchange_id": "CME_Eq", "market_id": NQZ26}]

    async def go():
        s = session(rows, calls)
        a = adapter(s)
        assert await a.market_id("NQ", TODAY) == NQZ26
        assert await a.market_id("nq", TODAY) == NQZ26
        assert len(calls) == 1 and calls[0] == {"page_size": "100", "search": "NQ"}
        assert await a.market_id("NQH27", TODAY) == NQH27      # an explicit month
        with pytest.raises(ValueError):
            await a.market_id("CL", TODAY)                       # a root we do not trade
        with pytest.raises(ValueError):
            await a.market_id("NQU27", TODAY)                    # no row for that month
    asyncio.run(go())


def test_snapshot_seeds_positions_and_net_sums_every_month_of_a_root():
    async def go():
        s = session()
        a = adapter(s)
        await a.connect()
        assert not a.positions_known and not a.orders_known
        s.socket.push("accountSnapshot", snapshot(
            "A1", {"accountPosition": pos("A1", NQZ26, "NQ", buys=3, sells=1)},
            {"accountPosition": pos("A1", NQH27, "NQ", buys=1)},             # an older / hand-opened month counts too
            {"accountPosition": pos("A1", ESZ26, "ES", sells=2)},
            {"orderUpdateMulti": {"accountId": "A1", "marketId": NQZ26, "updates": [{"orderUpdate": {
                "uniqueId": "U1", "accountId": "A1", "marketId": NQZ26, "status": proto.WORKING, "buySell": proto.SELL,
                "priceType": proto.STOP_MARKET, "currentVolume": 3, "currentStopPrice": {"value": "19990.25"},
                "tag": "hb", "tagClOrdId": "HB_1", "orderLink": proto.AUTO_OCO_P, "ordersLinked": "U2"}}]}}))
        assert a.positions_known and a.orders_known
        assert await a.get_net_position("NQ") == 3 and await a.get_net_position("ES") == -2
        o = a._orders["U1"]
        assert (o["status"], o["buySell"], o["priceType"], o["volume"], o["stopPrice"], o["limitPrice"], o["clOrdId"],
                o["orderLink"], o["ordersLinked"], o["filled"]) == (proto.WORKING, proto.SELL, proto.STOP_MARKET, 3,
                                                                    19990.25, None, "HB_1", proto.AUTO_OCO_P, "U2", 0)
        s.socket.push("orderUpdateStatus", {"uniqueId": "U1", "accountId": "A1", "marketId": NQZ26,
                                            "status": proto.FINISHED})     # every field of the message is set
        assert a._orders["U1"]["status"] == proto.FINISHED and a._orders["U1"]["volume"] == 0
        m = await a.get_metrics()
        assert m["positions_known"] and m["open_positions"] == [{"symbol": "NQ", "net": 3}, {"symbol": "ES", "net": -2}]
        assert m["working_orders"] == 0 and m["session_taken"] == 0 and m["no_stop"] == []
    asyncio.run(go())


def test_net_position_raises_while_unknown_or_dirty():
    async def go():
        s = session()
        a = adapter(s)
        await a.connect()
        with pytest.raises(RuntimeError, match="position unknown"):
            await a.get_net_position("NQ")                       # no snapshot yet: never 0
        assert (await a.get_metrics())["open_position_count"] is None
        s.socket.push("accountSnapshot", snapshot("A1"))       # a flat book
        assert await a.get_net_position("NQ") == 0
        s.socket.push("orderUpdateTrade", {"uniqueId": "U9", "accountId": "A1", "marketId": NQZ26, "volume": 1,
                                           "totalFillVolume": 1})
        assert not a.positions_known
        with pytest.raises(RuntimeError, match="position unknown"):
            await a.get_net_position("NQ")                       # a fill seen, its position not yet
        s.socket.push("accountPosition", pos("A1", NQZ26, "NQ", buys=1))
        assert await a.get_net_position("NQ") == 1
        s.socket.push("accountPosition", pos("A2", NQZ26, "NQ", buys=5))     # another account's: not ours
        assert await a.get_net_position("NQ") == 1
        s.socket.up = False                                      # the socket dropped
        with pytest.raises(RuntimeError, match="position unknown"):
            await a.get_net_position("NQ")
        s.socket.up = True
        await s.socket.on_up()                                   # back up: unknown until the fresh snapshot
        with pytest.raises(RuntimeError, match="position unknown"):
            await a.get_net_position("NQ")
        s.socket.push("accountSnapshot", snapshot("A1", {"accountPosition": pos("A1", NQZ26, "NQ", buys=1)}))
        assert await a.get_net_position("NQ") == 1
    asyncio.run(go())


async def seeded(s, name="AF-50K-1", *rows):
    a = adapter(s, name)
    await a.connect()
    s.socket.push("accountSnapshot", snapshot(a._acct_id, *({"accountPosition": r} for r in rows)))
    return a


def test_a_position_root_in_another_form_counts_an_untraded_root_is_its_own_and_an_unreadable_one_reads_unknown():
    async def go():
        s = session()
        a = await seeded(s, "AF-50K-1", pos("A1", NQZ26, "NQZ26", buys=1), pos("A1", NQH27, "CME_Eq NQ", buys=1),
                         pos("A1", ESZ26, "", sells=1))         # no contractId: the market id names it
        assert await a.get_net_position("NQ") == 2 and await a.get_net_position("ES") == -1
        s.socket.push("accountPosition", pos("A1", "XCME_C CL (Z26)", "CL", buys=1))   # a hand-opened market we do not trade
        assert await a.get_net_position("NQ") == 2                   # is just another market
        assert (await a.get_metrics())["open_positions"][-1] == {"symbol": "CL", "net": 1}
        s.socket.push("accountPosition", pos("A1", "T4-123", "", buys=1))     # a held row we cannot read
        with pytest.raises(RuntimeError, match="position unknown"):
            await a.get_net_position("NQ")                       # it could be NQ: never read past it
        s.socket.push("accountPosition", pos("A1", "T4-123", ""))           # flat again: harmless
        assert await a.get_net_position("NQ") == 2
    asyncio.run(go())


def test_a_late_joiners_resubscribe_is_all_accounts_and_a_repeated_snapshot_keeps_a_seeded_adapter_right():
    async def go():
        s = session()
        a = await seeded(s, "AF-50K-1", pos("A1", NQZ26, "NQ", buys=2))
        s.socket.push("orderUpdate", {"uniqueId": "U1", "accountId": "A1", "marketId": NQZ26, "status": proto.WORKING,
                                      "buySell": proto.SELL, "priceType": proto.STOP_MARKET, "currentVolume": 2})
        b = adapter(s, "AF-50K-2", "d2")
        await b.connect()
        assert s.socket.sent == [("accountSubscribe", ALL)]
        assert a.positions_known and await a.get_net_position("NQ") == 2    # a keeps reading until the repeat arrives
        s.socket.push("accountSnapshot", snapshot("A1", {"accountPosition": pos("A1", NQZ26, "NQ", buys=2)}))
        s.socket.push("accountSnapshot", snapshot("A2"))
        assert await a.get_net_position("NQ") == 2 and await b.get_net_position("NQ") == 0
        assert a.orders_known and a._orders["U1"]["status"] == proto.WORKING     # a known order book is kept
    asyncio.run(go())


def test_an_ambiguous_account_name_raises_and_an_id_wins(monkeypatch):
    monkeypatch.setattr(FakeSocket, "accounts", [
        {"accountId": "A1", "accountName": "Main"}, {"accountId": "A2", "accountName": "MAIN"},
        {"accountId": "A3", "accountName": "A1", "displayName": "Main"}])

    async def go():
        s = session()
        with pytest.raises(AccountNotOnLogin, match="more than one account named main"):
            await adapter(s, "main").connect()
        a = adapter(s, "a1", "d2")                     # an id beats an accountName
        await a.connect()
        assert a.broker_key == ("alphatrader", "A1")
        with pytest.raises(AccountNotOnLogin, match="not on this login"):
            await adapter(s, "1001", "d3").connect()   # accountNumber / displayName do not pin
    asyncio.run(go())


def test_a_repeated_order_update_of_the_same_trades_does_not_make_the_market_dirty_again():
    async def go():
        s = session()
        a = await seeded(s)
        fill = {"uniqueId": "U1", "accountId": "A1", "marketId": NQZ26, "status": proto.FINISHED, "buySell": proto.BUY,
                "totalFillVolume": 1, "trades": [{"sequenceOrder": 1, "volume": 1}]}
        s.socket.push("orderUpdate", fill)
        assert not a.positions_known
        s.socket.push("accountPosition", pos("A1", NQZ26, "NQ", buys=1))
        s.socket.push("orderUpdate", fill)                      # the same trades again
        assert a.positions_known and await a.get_net_position("NQ") == 1
    asyncio.run(go())


def test_a_market_still_dirty_asks_for_the_snapshots_once_per_episode(monkeypatch):
    monkeypatch.setattr(alphatrader, "DIRTY_RESYNC_S", 0.0)

    async def go():
        s = session()
        a = await seeded(s)
        trade = lambda n: {"uniqueId": "U1", "accountId": "A1", "marketId": NQZ26, "totalFillVolume": n}
        s.socket.push("orderUpdateTrade", trade(1))
        await asyncio.sleep(0.01)
        assert s.socket.sent == [("accountSubscribe", ALL)]
        s.socket.push("orderUpdateTrade", trade(2))             # the same episode: no second ask
        await asyncio.sleep(0.01)
        assert len(s.socket.sent) == 1
        s.socket.push("accountPosition", pos("A1", NQZ26, "NQ", buys=2))     # the episode ends
        s.socket.push("orderUpdateTrade", trade(3))
        await asyncio.sleep(0.01)
        assert len(s.socket.sent) == 2
    asyncio.run(go())


def test_a_trade_with_no_market_makes_every_position_unknown_until_the_snapshot(monkeypatch):
    monkeypatch.setattr(alphatrader, "DIRTY_RESYNC_S", 0.0)

    async def go():
        s = session()
        a = await seeded(s, "AF-50K-1", pos("A1", NQZ26, "NQ", buys=1))
        s.socket.push("orderUpdateTrade", {"uniqueId": "U7", "accountId": "A1", "totalFillVolume": 1})
        assert "" not in a._dirty and not a.positions_known
        await asyncio.sleep(0.01)
        assert s.socket.sent == [("accountSubscribe", ALL)]
        s.socket.push("accountSnapshot", snapshot("A1", {"accountPosition": pos("A1", NQZ26, "NQ", buys=2)}))
        assert await a.get_net_position("NQ") == 2
    asyncio.run(go())


def test_a_taken_session_reads_unknown_until_the_next_snapshot():
    async def go():
        s = session()
        a = await seeded(s, "AF-50K-1", pos("A1", NQZ26, "NQ", buys=1))
        await s.socket.on_taken("logged in elsewhere")
        with pytest.raises(RuntimeError, match="position unknown"):
            await a.get_net_position("NQ")
    asyncio.run(go())


# ------------------------------------------------------------------ orders (Task 5)
ROWS = [{"contract_id": "NQ", "exchange_id": "CME_Eq", "market_id": NQZ26},
        {"contract_id": "ES", "exchange_id": "CME_Eq", "market_id": ESZ26}]


def subs(sock):
    return [d for p, d in sock.sent if p == "orderSubmit"]


def pulls(sock):
    return [(d["marketId"], p["uniqueId"]) for k, d in sock.sent if k == "orderPull" for p in d["pulls"]]


def t4(acct="A1", refuse=(), after=None):
    """A T4 stand-in: a submit is answered per order (an entry WORKING, a leg HELD, a MARKET close FINISHED and its market's
    position set to `after[marketId]` (flat by default)); a refused market answers orderUpdateFailed with no uniqueId; a
    pull is answered FINISHED."""
    n = iter(range(1, 1000))

    def reply(payload, d):
        out = []
        if payload == "orderSubmit":
            for o in d["orders"]:
                if d["marketId"] in refuse:
                    out.append(("orderUpdateFailed", {"accountId": acct, "marketId": d["marketId"], "status": proto.REJECTED,
                                                      "statusDetail": "Order rejected: market closed",
                                                      "tagClOrdId": o["ClOrdId"]}))
                    continue
                close = o.get("priceType", 0) == proto.MARKET and not d.get("orderLink")
                status = proto.HELD if o.get("activationType") else proto.FINISHED if close else proto.WORKING
                out.append(("orderUpdate", {"uniqueId": f"U{next(n)}", "accountId": acct, "marketId": d["marketId"],
                                            "status": status, "buySell": o["buySell"], "priceType": o.get("priceType", 0),
                                            "currentVolume": o.get("volume", 0), "tagClOrdId": o["ClOrdId"]}))
                if close:
                    buys, sells = (after or {}).get(d["marketId"], (0, 0))
                    out.append(("accountPosition", pos(acct, d["marketId"], "", buys=buys, sells=sells)))
        elif payload == "orderPull":
            out += [("orderUpdateStatus", {"uniqueId": p["uniqueId"], "accountId": acct, "marketId": d["marketId"],
                                           "status": proto.FINISHED}) for p in d["pulls"]]
        return out
    return reply


def working(uid, market, status=proto.WORKING, acct="A1", side=proto.SELL, ptype=proto.STOP_MARKET):
    return {"orderUpdate": {"uniqueId": uid, "accountId": acct, "marketId": market, "status": status, "buySell": side,
                            "priceType": ptype, "currentVolume": 1}}


async def ready(*book, rows=ROWS, name="AF-50K-1"):
    """A connected adapter whose snapshot holds `book` (positions and order updates), with T4 answering."""
    s = session(rows)
    a = adapter(s, name)
    await a.connect()
    s.socket.push("accountSnapshot", snapshot(a._acct_id, *book))
    s.socket.reply = t4(a._acct_id)
    return a, s.socket


BUY_BRACKET = OrderRequest("NQZ26", "Buy", 1, "Limit", price=20000, stop_price=19990, tp_price=20020, text="hb:test")


def test_a_buy_limit_bracket_is_one_submit_with_three_orders_auto_oco_p():
    async def go():
        a, sock = await ready()
        r = await a.place_bracket(BUY_BRACKET)
        assert r.ok and r.order_id == "U1"
        [sub] = subs(sock)                                          # exactly one submit: entry, target and stop together
        assert (sub["accountId"], sub["marketId"], sub["orderLink"], sub["manualOrderIndicator"]) == \
            ("A1", NQZ26, proto.AUTO_OCO_P, False)
        entry, tp, sl = sub["orders"]
        assert (entry["buySell"], entry["priceType"], entry["timeType"], entry["volume"], entry["limitPrice"]) == \
            (proto.BUY, proto.LIMIT, proto.NORMAL, 1, {"value": "20000.00"})
        assert "stopPrice" not in entry and not entry.get("activationType")
        assert (tp["buySell"], tp["priceType"], tp["timeType"], tp["volume"], tp["limitPrice"], tp["activationType"]) == \
            (proto.SELL, proto.LIMIT, proto.GTC, 0, {"value": "20020.00"}, proto.HOLD)
        assert (sl["buySell"], sl["priceType"], sl["timeType"], sl["volume"], sl["stopPrice"], sl["activationType"]) == \
            (proto.SELL, proto.STOP_MARKET, proto.GTC, 0, {"value": "19990.00"}, proto.HOLD)
        ids = [o["ClOrdId"] for o in sub["orders"]]
        assert len(set(ids)) == 3 and all(i.startswith("HB_") and len(i) == 35 for i in ids)
        assert {o["tag"] for o in sub["orders"]} == {"hb:test"}
        back = proto.decode("ClientMessage", proto.client("orderSubmit", sub))["orderSubmit"]   # every key is on the wire
        assert [o["ClOrdId"] for o in back["orders"]] == ids and back["orders"][2]["buySell"] == -1
        assert back["orders"][2]["stopPrice"] == {"value": "19990.00"}
    asyncio.run(go())


def test_a_sell_stop_entry_bracket_legs_are_buys():
    async def go():
        a, sock = await ready()
        r = await a.place_bracket(OrderRequest("NQZ26", "Sell", 2, "Stop", price=19980.1, stop_price=19990,
                                               tp_price=19950))
        assert r.ok
        entry, tp, sl = subs(sock)[0]["orders"]
        assert (entry["buySell"], entry["priceType"], entry["volume"], entry["stopPrice"]) == \
            (proto.SELL, proto.STOP_MARKET, 2, {"value": "19980.00"})      # on the tick
        assert tp["buySell"] == sl["buySell"] == proto.BUY
        assert (tp["limitPrice"], sl["stopPrice"]) == ({"value": "19950.00"}, {"value": "19990.00"})
    asyncio.run(go())


def test_a_bracketed_market_entry_without_a_price_is_refused_and_nothing_is_sent():
    async def go():
        a, sock = await ready()
        r = await a.place_bracket(OrderRequest("NQZ26", "Buy", 1, "Market", stop_price=19990, tp_price=20020))
        assert not r.ok and r.error == "alphatrader: a bracketed market entry needs a price"
        assert subs(sock) == []
        r = await a.place_bracket(OrderRequest("NQZ26", "Buy", 1, "Market", price=20000, stop_price=19990))
        assert r.ok                                                  # with a price: the market bracket, no target
        [sub] = subs(sock)
        entry, sl = sub["orders"]
        assert entry["priceType"] == proto.MARKET and "limitPrice" not in entry and "stopPrice" not in entry
        assert (sl["priceType"], sl["buySell"]) == (proto.STOP_MARKET, proto.SELL)
    asyncio.run(go())


def test_a_stop_on_the_wrong_side_is_refused():
    async def go():
        a, sock = await ready()
        for req in (OrderRequest("NQZ26", "Buy", 1, "Limit", price=20000, stop_price=20010, tp_price=20020),
                    OrderRequest("NQZ26", "Buy", 1, "Limit", price=20000, stop_price=20000.1),   # the tick: on the entry
                    OrderRequest("NQZ26", "Sell", 1, "Limit", price=20000, stop_price=19990),
                    OrderRequest("NQZ26", "Buy", 1, "StopLimit", price=20002, trigger_price=20000, stop_price=20001),
                    OrderRequest("NQZ26", "Buy", 1, "Limit", price=20000, stop_price=19990, tp_price=19995)):
            r = await a.place_bracket(req)
            assert not r.ok and "wrong side" in r.error, req
        assert sock.sent == []
    asyncio.run(go())


def test_the_answer_is_matched_by_ClOrdId_and_a_reject_carries_T4s_words():
    async def go():
        a, sock = await ready()

        def reply(payload, d):
            cid = d["orders"][0]["ClOrdId"]
            return [("orderUpdate", {"uniqueId": "U7", "accountId": "A1", "marketId": NQZ26, "status": proto.WORKING,
                                     "tagClOrdId": "HB_someone_else"}),          # another order's answer: not ours
                    ("orderUpdateFailed", {"accountId": "A1", "marketId": NQZ26, "status": proto.REJECTED,
                                           "statusDetail": "Insufficient margin", "tagClOrdId": cid})]   # no uniqueId yet
        sock.reply = reply
        r = await a.place_order(OrderRequest("NQZ26", "Buy", 1, "Limit", price=20000))
        assert not r.ok and "Insufficient margin" in r.error and r.order_id is None
        sock.reply = lambda p, d: [("orderUpdate", {"uniqueId": "U8", "accountId": "A1", "marketId": NQZ26,
                                                    "status": proto.REJECTED, "statusDetail": "Price out of range",
                                                    "tagClOrdId": d["orders"][0]["ClOrdId"]})]
        r = await a.place_order(OrderRequest("NQZ26", "Buy", 1, "Limit", price=20000))
        assert not r.ok and "Price out of range" in r.error
        assert len(subs(sock)) == 2                                   # one send each, never again
    asyncio.run(go())


def test_no_answer_is_outcome_unknown_never_resent_and_a_late_update_is_cached(monkeypatch):
    monkeypatch.setattr(alphatrader, "ORDER_WAIT_S", 0.05)

    async def go():
        a, sock = await ready()
        sock.reply = None                                             # T4 says nothing
        r = await a.place_order(OrderRequest("NQZ26", "Buy", 1, "Limit", price=20000))
        assert not r.ok and r.raw["outcome_unknown"] is True
        [sub] = subs(sock)
        cid = sub["orders"][0]["ClOrdId"]
        await asyncio.sleep(0.1)
        assert len(subs(sock)) == 1                                   # never resent
        sock.push("orderUpdate", {"uniqueId": "U9", "accountId": "A1", "marketId": NQZ26, "status": proto.WORKING,
                                  "tagClOrdId": cid})
        assert a._orders["U9"]["clOrdId"] == cid and a._orders["U9"]["status"] == proto.WORKING
        assert len(subs(sock)) == 1
    asyncio.run(go())


def test_bracket_leg_ids_are_recorded_from_order_updates():
    async def go():
        a, sock = await ready()
        r = await a.place_bracket(BUY_BRACKET)
        assert r.ok and (r.order_id, r.raw["tp_order_id"], r.raw["sl_order_id"]) == ("U1", "U2", "U3")
        answer = t4()
        sock.reply = lambda payload, d: list(reversed(answer(payload, d)))     # the legs report before the entry
        r = await a.place_bracket(BUY_BRACKET)
        assert r.ok and (r.order_id, r.raw["tp_order_id"], r.raw["sl_order_id"]) == ("U1", "U2", "U3")   # matched by id
    asyncio.run(go())


def test_flatten_reads_positions_first_closes_each_month_then_pulls_only_closed_markets():
    async def go():
        a, sock = await ready({"accountPosition": pos("A1", NQZ26, "NQ", buys=2)},
                              {"accountPosition": pos("A1", NQH27, "NQ", sells=1)},     # an older month still held
                              {"accountPosition": pos("A1", ESZ26, "ES", buys=1)},
                              working("U10", NQZ26), working("U11", NQH27, proto.HELD, side=proto.BUY),
                              working("U12", ESZ26), working("U13", NQZ26, proto.FINISHED))
        r = await a.flatten_symbol("NQ")
        assert r.ok, r.error
        closes = {s["marketId"]: s["orders"] for s in subs(sock)}
        assert set(closes) == {NQZ26, NQH27} and all(len(o) == 1 for o in closes.values())
        assert (closes[NQZ26][0]["buySell"], closes[NQZ26][0]["priceType"], closes[NQZ26][0]["volume"]) == \
            (proto.SELL, proto.MARKET, 2)
        assert (closes[NQH27][0]["buySell"], closes[NQH27][0]["volume"]) == (proto.BUY, 1)
        assert all(not s.get("orderLink") for s in subs(sock))
        assert sorted(pulls(sock)) == [(NQH27, "U11"), (NQZ26, "U10")]   # never ES's, never a finished one
        kinds = [k for k, _ in sock.sent]
        assert kinds.index("orderPull") > max(i for i, k in enumerate(kinds) if k == "orderSubmit")   # close first
        assert await a.get_net_position("NQ") == 0 and await a.get_net_position("ES") == 1
    asyncio.run(go())


def test_a_refused_close_on_one_month_still_pulls_the_other_months_orders():
    async def go():
        a, sock = await ready({"accountPosition": pos("A1", NQZ26, "NQ", buys=2)},
                              {"accountPosition": pos("A1", NQH27, "NQ", sells=1)},
                              working("U10", NQZ26), working("U11", NQH27, side=proto.BUY))
        sock.reply = t4(refuse=(NQH27,))
        r = await a.flatten_symbol("NQ")
        assert not r.ok and "market closed" in r.error
        assert pulls(sock) == [(NQZ26, "U10")]                       # the refused month keeps its stop
    asyncio.run(go())


def test_flatten_refuses_while_positions_are_unknown():
    async def go():
        s = session(ROWS)
        a = adapter(s)
        await a.connect()                                            # no snapshot yet
        for r in (await a.flatten_symbol("NQ"), await a.flatten_all()):
            assert not r.ok and "unknown" in r.error
        s.socket.push("accountSnapshot", snapshot("A1", {"accountPosition": pos("A1", NQZ26, "NQ", buys=1)}))
        s.socket.push("orderUpdateTrade", {"uniqueId": "U9", "accountId": "A1", "marketId": NQZ26, "totalFillVolume": 1})
        r = await a.flatten_symbol("NQ")                             # a fill whose position has not landed
        assert not r.ok and "unknown" in r.error
        assert [k for k, _ in s.socket.sent] == []
    asyncio.run(go())


def test_cancel_all_pulls_only_this_accounts_working_orders():
    async def go():
        a, sock = await ready(working("U10", NQZ26), working("U11", ESZ26, proto.HELD),
                              working("U12", NQZ26, proto.FINISHED))
        sock.push("orderUpdate", working("U20", NQZ26, acct="A2")["orderUpdate"])     # another account's order
        r = await a.cancel_all()
        assert r.ok and sorted(pulls(sock)) == [(ESZ26, "U11"), (NQZ26, "U10")]
        p = next(d for k, d in sock.sent if k == "orderPull")
        assert p["accountId"] == "A1" and p["manualOrderIndicator"] is False
        assert a._orders["U10"]["status"] == proto.FINISHED
        sock.sent.clear()
        a._orders["U10"]["status"] = proto.WORKING
        assert (await a.cancel_order_by_id("U10")).ok and pulls(sock) == [(NQZ26, "U10")]
        r = await a.cancel_order_by_id("U404")                       # not in the book: its market is not known
        assert not r.ok and len(pulls(sock)) == 1
    asyncio.run(go())


def test_a_bare_protective_stop_uses_stop_price_and_a_plain_bracket_is_a_plain_order():
    async def go():
        a, sock = await ready()
        assert (await a.place_order(OrderRequest("NQZ26", "Sell", 1, "Stop", stop_price=19990, price=20000))).ok
        assert (await a.place_order(OrderRequest("NQZ26", "Buy", 1, "Stop", price=20010))).ok
        assert (await a.place_bracket(OrderRequest("NQZ26", "Buy", 1, "StopLimit", price=20012,
                                                   trigger_price=20010))).ok
        prot, entry, plain = subs(sock)
        assert prot["orders"][0]["stopPrice"] == {"value": "19990.00"} and prot["orders"][0]["buySell"] == proto.SELL
        assert entry["orders"][0]["stopPrice"] == {"value": "20010.00"} and not entry["orderLink"]
        assert len(plain["orders"]) == 1 and not plain["orderLink"]
        assert (plain["orders"][0]["priceType"], plain["orders"][0]["limitPrice"], plain["orders"][0]["stopPrice"]) == \
            (proto.STOP_LIMIT, {"value": "20012.00"}, {"value": "20010.00"})
        r = await a.place_order(OrderRequest("NQZ26", "Buy", 1, "Limit"))
        assert not r.ok and "needs a price" in r.error and len(subs(sock)) == 3
    asyncio.run(go())


def test_a_down_socket_sends_nothing_and_queues_nothing():
    async def go():
        a, sock = await ready({"accountPosition": pos("A1", NQZ26, "NQ", buys=1)}, working("U10", NQZ26))
        sock.up = False
        for r in (await a.place_order(OrderRequest("NQZ26", "Buy", 1, "Limit", price=20000)),
                  await a.place_bracket(BUY_BRACKET), await a.cancel_all(), await a.cancel_order_by_id("U10"),
                  await a.flatten_symbol("NQ"), await a.flatten_all()):
            assert not r.ok and r.error == "alphatrader: not connected"
        sock.up = True
        await asyncio.sleep(0.01)
        assert sock.sent == []
    asyncio.run(go())


def test_flatten_closes_again_only_when_the_net_flipped_sign(monkeypatch):
    monkeypatch.setattr(alphatrader, "ORDER_WAIT_S", 0.05)

    async def go():
        a, sock = await ready({"accountPosition": pos("A1", NQZ26, "NQ", buys=2)})
        sock.reply = t4(after={NQZ26: (0, 1)})                       # the bracket's stop filled too: short 1
        r = await a.flatten_symbol("NQ")
        assert [(s["orders"][0]["buySell"], s["orders"][0]["volume"]) for s in subs(sock)] == \
            [(proto.SELL, 2), (proto.BUY, 1)]
        assert r.ok, r.error

        a, sock = await ready({"accountPosition": pos("A1", NQZ26, "NQ", buys=2)})
        sock.reply = t4(after={NQZ26: (2, 0)})                       # the close has not filled yet
        r = await a.flatten_symbol("NQ")
        assert len(subs(sock)) == 1 and not r.ok and "not sent again" in r.error
    asyncio.run(go())


def test_flatten_all_closes_every_market_held_even_one_we_do_not_trade():
    async def go():
        cl = "XCME_C CL (Z26)"
        a, sock = await ready({"accountPosition": pos("A1", NQZ26, "NQ", sells=3)},
                              {"accountPosition": pos("A1", cl, "CL", buys=1)},
                              working("U10", ESZ26, ptype=proto.LIMIT))           # an entry resting with no position
        r = await a.flatten_all()
        assert r.ok, r.error
        assert sorted((s["marketId"], s["orders"][0]["buySell"], s["orders"][0]["volume"]) for s in subs(sock)) == \
            sorted([(NQZ26, proto.BUY, 3), (cl, proto.SELL, 1)])
        assert pulls(sock) == [(ESZ26, "U10")]
    asyncio.run(go())
