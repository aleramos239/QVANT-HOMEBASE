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
from homebase.broker.base import AccountNotOnLogin

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
