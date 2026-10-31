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
NQZ26, NQH27, ESZ26 = "XCME_Eq NQ (Z26)", "XCME_Eq NQ (H27)", "XCME_Eq ES (Z26)"


class FakeSocket:
    """Stands in for AtrSocket: start() answers the login (accounts) and runs on_up; tests push events with push()."""
    made: list["FakeSocket"] = []

    def __init__(self, session, on_event, *, on_up=None, on_taken=None, url=None):
        self.session, self.on_event, self.on_up, self.on_taken = session, on_event, on_up, on_taken
        self.up, self.starts, self.stopped = False, 0, False
        self.sent: list[tuple[str, dict]] = []
        FakeSocket.made.append(self)

    async def start(self):
        self.starts += 1
        if self.up:
            return
        self.on_event("loginResponse", {"sessionId": "S1", "accounts": ACCOUNTS})
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
        assert sock.sent == [("accountSubscribe", {"subscribe": proto.ALL_UPDATES, "accountId": "A2",
                                                   "uplMode": proto.AVERAGE})]     # b joined an open socket: its snapshot
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
        assert sock.sent[-1] == ("accountSubscribe", {"subscribe": proto.ALL_UPDATES, "accountId": "A1",
                                                      "uplMode": proto.AVERAGE})
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
        s.socket.push("orderUpdateTrade", {"uniqueId": "U9", "accountId": "A1", "marketId": NQZ26, "volume": 1})
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
