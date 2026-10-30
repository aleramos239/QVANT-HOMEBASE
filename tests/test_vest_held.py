"""Vest held stop entries (fired as market orders off the CME price), the loss-floor guard and the slippage cap.
No network: the fake gateway of test_vest_adapter (an httpx MockTransport)."""
from __future__ import annotations

import asyncio
import datetime as dt
import json

import httpx
import pytest

from homebase.broker import vest
from homebase.broker.base import OrderRequest
from homebase.broker.vest import VestAdapter
from homebase.broker.vest_auth import DeviceKey, VestSession
from homebase.broker.vest_held import HeldBook, HeldEntry, floor_room, slip_ok
from homebase.core.clock import ET
from homebase.data.feed import Bar
from homebase.store import secrets_store
from tests.test_vest_adapter import ACC, FAR, KEY, OPEN, SYM, Gateway, body, pos, run

T0 = dt.datetime(2026, 10, 29, 14, 0, tzinfo=dt.timezone.utc)
NOW = dt.datetime(2026, 10, 29, 10, 0, tzinfo=ET)            # desk day 2026-10-29
NO_LIMIT = {"max_drawdown_equity": -1e9}


def signed_in():
    secrets_store.set_credentials(KEY, primary_addr="0xabc", refresh_token="RT", refresh_token_id="RTID",
                                  refresh_expires_ms=FAR, device_pem=DeviceKey.new().pem())


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets_store, "_store_path", lambda: tmp_path / "credentials.json")
    monkeypatch.setattr(vest, "state_dir", lambda: tmp_path)
    signed_in()


def mk(gw=None, floors=NO_LIMIT, mark="21003", **kw):
    gw = gw or Gateway()
    gw.mark = mark
    sess = VestSession(KEY, http=httpx.AsyncClient(transport=httpx.MockTransport(gw)))
    sess._user = ("AT", FAR)
    j: list = []
    ad = VestAdapter("vest1", keyring_key=KEY, vest_account_id=ACC, session=sess, floors=floors,
                     journal=lambda ev, **k: j.append((ev, k)), **kw)
    ad.feed_ok = lambda: True
    ad._now = lambda: NOW
    return ad, gw, j


def bar(h=20995.0, l=20985.0, o=20990.0, c=None, m=0):
    return Bar(ts=T0 + dt.timedelta(minutes=m), o=o, h=h, l=l, c=o if c is None else c, vol=1, root="NQ", minutes=1)


def hold(ad, side="Buy", level=21000.0, sl=20.0, tp=40.0, sym="NQZ6", qty=1):
    s = 1 if side == "Buy" else -1
    return ad.place_bracket(OrderRequest(sym, side, qty, "Stop", price=level, stop_price=level - s * sl,
                                         tp_price=level + s * tp, text="homebase:entry"))


async def push(ad, *bars):
    for b in bars:
        ad.on_bar("NQ", b)
        await asyncio.gather(*list(ad._fires))


def opens(gw):
    return [c for c in gw.api("POST") if c.url.path == OPEN]


def skipped(j):
    return [k for ev, k in j if ev == "vest_held_skipped"]


def accounts(gw, **row):
    gw.h[("GET", "/v3/accounts")] = lambda req: httpx.Response(200, json=[{"account_id": ACC, "account_type": 1, **row}])


# ---- firing ------------------------------------------------------------------------------------------------
def test_buy_fires_once_on_cross():
    ad, gw, j = mk()
    r = run(hold(ad))
    assert r.ok and r.order_id.startswith("held:") and not gw.writes()          # held by Homebase: nothing sent
    got = []

    async def go():
        async def on_fill(ev):
            got.append(ev)
        ad._on_fill = on_fill
        await push(ad, bar(h=20995))
        assert not opens(gw)
        await push(ad, bar(h=21001))
        assert len(opens(gw)) == 1
        await push(ad, bar(h=21010), bar(h=21012, m=1))
        assert len(opens(gw)) == 1                                           # fires once
        frame = {"channel": "account_state", "data": {"account_id": ACC, "account_seq": 1, "positions": [], "orders": [
            {"order_id": "o1", "symbol": SYM, "side": "buy", "status": "filled", "executed_quantity": "20",
             "execution_price": "21003"}]}}
        await ad._on_message(json.dumps(frame))
    run(go())
    b = body(opens(gw)[0])
    assert (b["orderType"], b["side"], b["quantity"]) == ("market", "long", "20")
    assert b["stopLosses"][0]["triggerPrice"] == "20983" and b["takeProfits"][0]["triggerPrice"] == "21043"
    assert [(ev, k["id"]) for ev, k in j if ev == "vest_held_fired"] == [("vest_held_fired", r.order_id)]
    (f,) = got
    assert f.raw["orderId"] == r.order_id and f.raw["vestOrderId"] == "o1"      # R30: the engine sees its own id
    assert run(ad.get_order_status(r.order_id)) == "Filled"                     # status follows the Vest order


def test_two_sided_one_push_only_first():
    ad, gw, j = mk()

    async def go():
        up, dn = await asyncio.gather(hold(ad, "Buy", 21000), hold(ad, "Sell", 20950))
        await push(ad, bar())
        await push(ad, bar(o=20990, h=21001, l=20949, m=1))
        await push(ad, bar(o=20940, h=20945, l=20900, m=2))                   # the sell level trades again later
        return up, dn
    up, dn = run(go())
    (o,) = opens(gw)
    assert body(o)["side"] == "long"                                          # the level nearest the bar's open
    assert [k["id"] for k in skipped(j)] == [dn.order_id] and "other leg" in skipped(j)[0]["reason"]
    assert run(ad.get_order_status(dn.order_id)) == "Canceled"


def test_skip_when_feed_or_session_down():
    for why in ("feed", "session", "late"):
        ad, gw, j = mk()
        r = run(hold(ad))

        async def go():
            await push(ad, bar())
            if why == "feed":
                ad.feed_ok = lambda: False
            elif why == "session":
                secrets_store.set_credentials(KEY, refresh_token="")               # the 30-day login ran out
                assert ad.session.needs_signature
            else:
                ad._pushed["NQ"] -= 11                                        # the last push was 11 s ago
            await push(ad, bar(h=21001))
            ad.feed_ok = lambda: True
            signed_in()
            await push(ad, bar(h=21005), bar(h=21010, m=1))                  # trades again later: nothing
        run(go())
        assert not opens(gw), why
        (k,) = skipped(j)
        assert k["id"] == r.order_id and k["reason"], why
        assert {"feed": "feed down", "session": "sign in", "late": "late"}[why] in k["reason"]


def test_slippage_cap():
    assert not slip_ok(21000, 21011, "Buy", 20, 0.5) and slip_ok(21000, 21009, "Buy", 20, 0.5)
    assert not slip_ok(21000, 20989, "Sell", 20, 0.5) and slip_ok(21000, 20991, "Sell", 20, 0.5)
    assert slip_ok(21000, 20990, "Buy", 20, 0.5)                              # better than the level: fine
    for mark, fired in (("21011", False), ("21009", True)):
        ad, gw, j = mk(mark=mark)
        run(hold(ad, sl=20))

        async def go():
            await push(ad, bar(), bar(h=21001))
        run(go())
        assert bool(opens(gw)) is fired, mark
        assert bool(skipped(j)) is not fired and all("slippage" in k["reason"] for k in skipped(j))


# ---- loss floors -------------------------------------------------------------------------------------------
def test_floor_guard():
    assert floor_room(50000, {"max_drawdown_equity": 48000}, 1500) == 500        # 600 > 500 refused, 60 allowed
    assert floor_room(50000, {"max_drawdown_equity": 48000, "daily_loss": 1000, "day_start_equity": 49500}, 0) == 1500
    assert floor_room(50000, {"max_drawdown_equity": 48000, "daily_loss": 1000, "day_start_equity": 48500}, 0) == 2000
    assert floor_room(50000, {}, 0) is None
    es = pos(symbol="ES-USD-PERP", openPrice="6000", quantity="20", stopLosses=[{"triggerPrice": "5925"}])   # $1,500 at risk

    def adapter(floors):
        ad, gw, _ = mk(floors=floors)
        accounts(gw, equity="50000")
        gw.positions = [es]
        return ad, gw
    ad, gw = adapter({"max_drawdown_equity": 48000})
    nq = run(ad.place_bracket(OrderRequest("NQZ6", "Buy", 1, "Market", price=21000, stop_price=20970)))
    assert not nq.ok and "floor" in nq.error and not opens(gw)
    assert run(ad.place_bracket(OrderRequest("MNQZ6", "Buy", 1, "Market", price=21000, stop_price=20970))).ok
    ad, gw = adapter({"max_drawdown_equity": 48000})
    assert not run(hold(ad, sl=30)).ok                                            # a held entry: checked when placed
    assert run(hold(ad, sl=30, sym="MNQZ6")).ok
    ad, gw = adapter({"max_drawdown_equity": 48000})
    assert not run(ad.place_bracket(OrderRequest("MNQZ6", "Buy", 1, "Limit", price=21000))).ok   # no stop: unbounded
    for floors in (None, {}):
        ad, gw = adapter(floors)
        r = run(ad.place_bracket(OrderRequest("MNQZ6", "Buy", 1, "Market", price=21000, stop_price=20999)))
        assert not r.ok and "floor" in r.error and not opens(gw)


def test_floor_guard_runs_again_at_fire_time():
    ad, gw, j = mk(floors={"max_drawdown_equity": 48000})
    accounts(gw, equity="50000")
    r = run(hold(ad, sl=30))
    assert r.ok
    accounts(gw, equity="48500")                                                  # equity fell meanwhile

    async def go():
        await push(ad, bar(), bar(h=21001))
    run(go())
    assert not opens(gw) and "floor" in skipped(j)[0]["reason"]


def test_daily_floor_resets_2000_et(tmp_path):
    def at(h, m=0, day=29):
        return dt.datetime(2026, 10, day, h, m, tzinfo=ET)

    def nq(sl=30):
        ok = run(ad.place_bracket(OrderRequest("NQZ6", "Buy", 1, "Market", price=21000, stop_price=21000 - sl))).ok
        gw.positions.clear()                                                      # flat again for the next try
        return ok
    # the API's day-start equity wins
    ad, gw, _ = mk(floors={"daily_loss": 1000})
    accounts(gw, equity="48700", dayStartEquity="49000")                          # floor 48000, room 700
    assert nq(30) and not nq(40)
    # none from the API: recorded at the first read of the day (the day rolls at 20:00 ET) and saved
    ad, gw, _ = mk(floors={"daily_loss": 1000})
    ad._now = lambda: at(19, 59)
    accounts(gw, equity="50000")
    assert nq()                                                                   # day-start 50000 recorded
    accounts(gw, equity="49500")
    assert not nq()                                                               # floor 49000: room 500 < 600
    ad._now = lambda: at(20, 1)
    assert nq()                                                                   # new day: day-start 49500
    saved = json.loads((tmp_path / "vest_held_vest1.json").read_text())
    assert saved["day_start"] == {"day": "2026-10-30", "equity": 49500.0}
    ad, gw, _ = mk(floors={"daily_loss": 1000})                                  # a restart keeps the day's start
    ad._now = lambda: at(23, 0)
    accounts(gw, equity="49000")
    assert not nq()                                                               # floor 48500: room 500 < 600
    # a daily limit with no day-start equity: refused
    assert floor_room(50000, {"daily_loss": 1000}, 0) is None
    assert floor_room(50000, {"max_drawdown_equity": 40000, "daily_loss": 1000}, 0) is None


# ---- restart / cancel --------------------------------------------------------------------------------------
def test_restore_after_restart(tmp_path):
    path = tmp_path / "book.json"
    b = HeldBook(path)
    b.add(HeldEntry("held:a", "NQZ6", "Buy", 1, 21000.0, 20.0, 40.0, "2026-10-29", None))
    b.add(HeldEntry("held:old", "NQZ6", "Buy", 1, 21000.0, 20.0, 40.0, "2026-10-28", None))
    assert [e.id for e in HeldBook(path).restore("2026-10-29", 20990.0)] == ["held:a"]
    assert [e.id for e in HeldBook(path).entries] == ["held:a"]                  # the drop is saved
    assert HeldBook(path).restore("2026-10-29", 21002.0) == []


def test_restart_restores_at_the_first_push():
    ad, gw, j = mk()
    run(hold(ad))
    ad2, gw2, j2 = mk()                                                           # a restart: the same file

    async def go():
        await push(ad2, bar(c=21002, h=21002))                                   # the level traded while down
        await push(ad2, bar(h=21005, m=1))
    run(go())
    assert not opens(gw2) and not ad2._book.entries and skipped(j2)


def test_cancel_drops_held():
    ad, gw, j = mk()
    r = run(hold(ad))
    c = run(ad.cancel_order_by_id(r.order_id))
    assert c.ok and not gw.writes() and not ad._book.entries
    assert run(ad.get_order_status(r.order_id)) == "Canceled"

    async def go():
        await push(ad, bar(), bar(h=21001))
    run(go())
    assert not opens(gw)
    run(hold(ad, level=21100))
    assert run(ad.cancel_all()).ok and not ad._book.entries                       # a kill / sweep drops held entries too


def test_held_entry_refused_when_the_level_already_traded_or_stop_limit():
    ad, gw, j = mk()

    async def go():
        await push(ad, bar(c=21005, h=21006))
    run(go())
    assert not run(hold(ad, level=21000)).ok                                       # a buy stop under the market
    assert not run(ad.place_bracket(OrderRequest("NQZ6", "Buy", 1, "StopLimit", price=21110, trigger_price=21100,
                                                 stop_price=21080))).ok
    assert not ad._book.entries and not gw.writes()
