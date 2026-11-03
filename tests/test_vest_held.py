"""Vest held stop entries (fired as market orders off the CME price), the loss-floor guard and the slippage cap.
No network: the fake gateway of test_vest_adapter (an httpx MockTransport)."""
from __future__ import annotations

import asyncio
import datetime as dt
import json

import httpx
import pytest

from homebase.broker import vest
from homebase.broker.base import FillEvent, OrderRequest
from homebase.broker.vest import VestAdapter
from homebase.broker.vest_auth import DeviceKey, VestSession
from homebase.broker.vest_held import HeldBook, HeldEntry, floor_room, slip_ok
from homebase.core.clock import ET
from homebase.data.feed import Bar
from homebase.store import secrets_store
from tests.test_vest_adapter import ACC, CLOSE, FAR, KEY, OPEN, SYM, Gateway, body, pos, run

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
    # measured on the CME push (R33): NQ-PERP's own price (basis) makes no difference
    for close, mark, fired in ((21011, "21000", False), (21009, "21100", True), (21011, "20950", False)):
        ad, gw, j = mk(mark=mark)
        run(hold(ad, sl=20))

        async def go():
            await push(ad, bar(), bar(h=close + 1, c=close))
        run(go())
        assert bool(opens(gw)) is fired, (close, mark)
        assert bool(skipped(j)) is not fired and all("late" in k["reason"] for k in skipped(j))


def test_flatten_waits_for_a_firing_entry():
    ad, gw, j = mk()
    run(hold(ad))

    async def go():
        gate = asyncio.Event()

        async def slow_open(req):
            await gate.wait()
            gw.positions.append(pos("long", "20"))
            return httpx.Response(200, json={"orderId": "o1", "positionId": "p1", "commandId": "c1"})
        gw.h[("POST", OPEN)] = slow_open
        await push(ad, bar())
        ad.on_bar("NQ", bar(h=21001))
        for _ in range(100):
            await asyncio.sleep(0.01)
            if opens(gw):
                break
        assert opens(gw) and ad._firing                                       # the open is on its way
        sweep = asyncio.ensure_future(ad.flatten_all())
        await asyncio.sleep(0.05)
        assert not sweep.done()                                               # the kill waits for it
        gate.set()
        return await sweep
    r = run(go())
    assert r.ok and r.raw["closed"] == 1 and not gw.positions
    assert [c.url.path for c in gw.api("POST")].count(CLOSE) == 1


def fill_frame(oid="o1", side="buy"):
    return json.dumps({"channel": "account_state", "data": {"account_id": ACC, "account_seq": 1, "positions": [], "orders": [
        {"order_id": oid, "symbol": SYM, "side": side, "status": "filled", "executed_quantity": "20",
         "execution_price": "21003"}]}})


def test_fill_before_the_post_answers_keeps_the_held_id():
    for answer in ({"orderId": "o1", "positionId": "p1", "commandId": "c1"}, {}):
        (vest.state_dir() / "vest_roots_vest1.json").unlink(missing_ok=True)   # each answer a first start: "o1" unknown
        ad, gw, j = mk()
        r = run(hold(ad))
        got = []

        async def early_fill(req, answer=answer):
            await ad._on_message(fill_frame())                                # the socket beats the POST answer
            gw.positions.append(pos("long", "20"))
            return httpx.Response(200, json=answer)
        gw.h[("POST", OPEN)] = early_fill

        async def go():
            async def on_fill(ev):
                got.append(ev)
            ad._on_fill = on_fill
            await push(ad, bar(), bar(h=21001))
        run(go())
        assert len(opens(gw)) == 1, answer
        assert [(f.raw["orderId"], f.raw["vestOrderId"]) for f in got] == [(r.order_id, "o1")], answer


def test_fired_status_survives_a_restart():
    ad, gw, j = mk()
    r = run(hold(ad))

    async def go():
        await push(ad, bar(), bar(h=21001))
    run(go())
    assert opens(gw)
    ad2, gw2, _ = mk()
    assert run(ad2.get_order_status(r.order_id)) == "Filled"
    assert not run(ad2.cancel_order_by_id(r.order_id)).ok
    assert run(ad2.get_order_status("held:unknown")) is None                  # no record: unknown, never Canceled


def test_restore_drops_a_level_the_first_push_already_reached():
    ad, gw, j = mk()
    run(hold(ad))
    ad2, gw2, j2 = mk()
    ad2.feed_bars = history(ad2)

    async def go():
        await push(ad2, bar(c=20990, h=21003))                                  # back under, but its high traded it
        await push(ad2, bar(h=21005, m=1))
    run(go())
    assert not opens(gw2) and not ad2._book.entries
    assert ["traded while down" in k["reason"] for k in skipped(j2)] == [True]


def test_feed_reset_makes_the_next_push_a_first_push():
    ad, gw, j = mk()
    run(hold(ad))

    async def go():
        await push(ad, bar())
        ad.feed_reset()
        await push(ad, bar(h=21001))
    run(go())
    assert not opens(gw) and "late" in skipped(j)[0]["reason"]


def test_floor_guard_is_serialised():
    ad, gw, _ = mk(floors={"max_drawdown_equity": 49000})
    accounts(gw, equity="50000")                                                  # room 1000: one 600 entry

    async def go():
        return await asyncio.gather(*(ad.place_bracket(OrderRequest("NQZ6", "Buy", 1, "Limit", price=21000,
                                                                    stop_price=20970)) for _ in range(2)))
    rs = run(go())
    assert [x.ok for x in rs].count(True) == 1 and len(opens(gw)) == 1


def test_slow_fire_is_skipped():
    ad, gw, j = mk()
    t = [1000.0]
    ad._mono = lambda: t[0]
    run(hold(ad))

    def slow_ticker(req):
        t[0] += 3                                                                 # the perp read took 3 s
    gw.h[("GET", "/v3/ticker/latest")] = slow_ticker

    async def go():
        await push(ad, bar())
        t[0] += 1
        await push(ad, bar(h=21001))
    run(go())
    assert not opens(gw) and "slow" in skipped(j)[0]["reason"]


def test_oco_pairing_needs_a_close_add_time_and_a_straddle():
    ad, gw, _ = mk()
    t = [1000.0]
    ad._mono = lambda: t[0]
    run(hold(ad, "Buy", 21000))
    t[0] += 3
    run(hold(ad, "Sell", 20950))
    assert [e.oco_group for e in ad._book.entries] == [None, None]                # 3 s apart: not one signal
    ad, gw, _ = mk()
    ad._mono, ad._book.entries = (lambda: t[0]), []                              # same state file: start empty
    run(hold(ad, "Buy", 20900))
    run(hold(ad, "Sell", 20950))
    assert [e.oco_group for e in ad._book.entries] == [None, None]                # buy under the sell: no straddle
    ad, gw, _ = mk()
    ad._mono, ad._book.entries = (lambda: t[0]), []                              # same state file: start empty
    a, b = run(hold(ad, "Buy", 21000)), run(hold(ad, "Sell", 20950))
    assert [e.oco_group for e in ad._book.entries] == [a.order_id, a.order_id]


def test_exits_are_never_blocked_by_the_floor_guard():
    ad, gw, _ = mk(floors=None)
    gw.positions = [pos("long", "20")]
    assert run(ad.place_order(OrderRequest("NQZ6", "Sell", 1, "Market"))).ok
    assert [c.url.path for c in gw.api("POST")] == [CLOSE]


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
    ad2.feed_bars = history(ad2)

    async def go():
        await push(ad2, bar(c=21002, h=21002))                                   # the level traded while down
        await push(ad2, bar(h=21005, m=1))
    run(go())
    assert not opens(gw2) and not ad2._book.entries
    assert [k["reason"] for k in skipped(j2)] == ["restart: level traded while down"]


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


def test_day_start_recorded_by_any_equity_read():
    ad, gw, _ = mk(floors={"daily_loss": 1100})
    ad._now = lambda: dt.datetime(2026, 10, 29, 20, 1, tzinfo=ET)
    accounts(gw, equity="50000")
    assert run(ad.get_balance())["balance"] == 50000                             # the first read after 20:00 ET
    ad._now = lambda: dt.datetime(2026, 10, 29, 20, 30, tzinfo=ET)
    accounts(gw, equity="49500")                                                  # floor 48900: room 600
    r = run(ad.place_bracket(OrderRequest("NQZ6", "Buy", 1, "Market", price=21000, stop_price=20969)))
    assert not r.ok and "room $600" in r.error


# ---- fix round 2 ------------------------------------------------------------------------------------------
def test_early_fill_delivered_outside_the_entry_lock():
    ad, gw, j = mk()
    run(hold(ad))
    exits = []

    async def early_fill(req):
        await ad._on_message(fill_frame())
        gw.positions.append(pos("long", "20"))
        return httpx.Response(200, json={"orderId": "o1", "positionId": "p1", "commandId": "c1"})
    gw.h[("POST", OPEN)] = early_fill

    async def go():
        async def on_fill(ev):                                                    # the engine places an order at once
            exits.append(await ad.place_order(OrderRequest("NQZ6", "Sell", 1, "Market", text="homebase:flat")))
        ad._on_fill = on_fill
        await asyncio.wait_for(push(ad, bar(), bar(h=21001)), 2)
    run(go())
    assert [x.ok for x in exits] == [True] and not gw.positions


def test_cancelled_sweep_never_cancels_a_fire():
    ad, gw, j = mk()
    r = run(hold(ad))

    async def go():
        gate = asyncio.Event()

        async def slow_open(req):
            await gate.wait()
            gw.positions.append(pos("long", "20"))
            return httpx.Response(200, json={"orderId": "o1", "positionId": "p1", "commandId": "c1"})
        gw.h[("POST", OPEN)] = slow_open
        await push(ad, bar())
        ad.on_bar("NQ", bar(h=21001))
        (fire,) = ad._fires
        await asyncio.sleep(0.05)                                                 # the open is on its way
        sweep = asyncio.ensure_future(ad.flatten_all())
        await asyncio.sleep(0.05)
        sweep.cancel()
        await asyncio.sleep(0.01)
        gate.set()
        await asyncio.sleep(0.05)
        return fire
    fire = run(go())
    assert fire.done() and not fire.cancelled() and r.order_id in ad._book.fired


def test_kill_stops_a_fire_that_has_not_posted():
    ad, gw, j = mk()
    run(hold(ad))

    async def go():
        gate = asyncio.Event()

        async def slow_ticker(req):                                               # the fire is mid perp read
            await gate.wait()
            return httpx.Response(200, json={"tickers": [{"symbol": SYM, "markPrice": "21003"}]})
        gw.h[("GET", "/v3/ticker/latest")] = slow_ticker
        await push(ad, bar())
        ad.on_bar("NQ", bar(h=21001))
        await asyncio.sleep(0.05)
        sweep = asyncio.ensure_future(ad.flatten_all())
        await asyncio.sleep(0.05)
        gate.set()
        return await sweep
    r = run(go())
    assert r.ok and not opens(gw) and not gw.positions
    assert "kill" in skipped(j)[0]["reason"]


def test_kill_stops_a_limit_entry_that_has_not_posted():
    ad, gw, j = mk()

    async def go():
        gate = asyncio.Event()

        async def slow_accounts(req):                                             # the entry is mid guard read
            await gate.wait()
            return httpx.Response(200, json=[{"account_id": ACC, "account_type": 1, "amount": "50000"}])
        gw.h[("GET", "/v3/accounts")] = slow_accounts
        entry = asyncio.ensure_future(ad.place_bracket(OrderRequest("NQZ6", "Buy", 1, "Limit", price=21000,
                                                                    stop_price=20980)))
        await asyncio.sleep(0.05)
        sweep = asyncio.ensure_future(ad.flatten_all())
        await asyncio.sleep(0.05)
        gate.set()
        return await entry, await sweep
    e, r = run(go())
    assert not e.ok and "flatten in progress" in e.error and r.ok and not gw.api("POST")


def test_a_hold_that_spans_a_flatten_is_refused():
    ad, gw, j = mk()

    async def go():
        gate = asyncio.Event()

        async def slow_accounts(req):                                             # the hold is mid floor read
            await gate.wait()
            return httpx.Response(200, json=[{"account_id": ACC, "account_type": 1, "amount": "50000"}])
        gw.h[("GET", "/v3/accounts")] = slow_accounts
        h = asyncio.ensure_future(hold(ad))
        await asyncio.sleep(0.05)
        r = await ad.flatten_all()                                                 # starts and ends during the read
        gate.set()
        return await h, r
    e, r = run(go())
    assert r.ok and not e.ok and "flatten in progress" in e.error and not ad._book.entries


def test_a_hold_during_a_flatten_is_refused():
    ad, gw, j = mk()
    ad._sweeping = 1
    e = run(hold(ad))
    assert not e.ok and "flatten in progress" in e.error and not ad._book.entries


def test_no_order_id_rewrite_claims_only_its_own_fill():
    ad, gw, j = mk()
    r = run(hold(ad))
    got = []

    async def early_fill(req):
        await ad._on_message(fill_frame())
        await ad._deliver([FillEvent(account_id="vest1", symbol="ES", side="Buy", qty=1, raw={"orderId": "x9"})])
        gw.positions.append(pos("long", "20"))
        return httpx.Response(200, json={})
    gw.h[("POST", OPEN)] = early_fill

    async def go():
        async def on_fill(ev):
            got.append(ev)
        ad._on_fill = on_fill
        await push(ad, bar(), bar(h=21001))
    run(go())
    assert sorted((f.symbol, f.raw["orderId"]) for f in got) == [("ES", "x9"), ("NQ", r.order_id)]


def test_a_save_failure_never_kills_the_fire():
    ad, gw, j = mk()
    r = run(hold(ad))
    real = ad._book.save

    def save():
        if ad._book.fired:
            raise OSError("disk full")
        real()
    ad._book.save = save

    async def go():
        await push(ad, bar(), bar(h=21001))
    run(go())
    assert [k["id"] for ev, k in j if ev == "vest_held_fired"] == [r.order_id]
    assert run(ad.get_order_status(r.order_id)) == "Filled"


# ---- fix round 1 (R45, R49, R50) ---------------------------------------------------------------------------
def test_a_cross_inside_the_bars_range_fires_on_that_push():
    """R45: the bar's high 21020 printed before the Buy stop at 21015 was held; price came back to 21000 and now trades
    up through the level inside the same bar (no higher high): it fires on this push, not at the next bar."""
    b = HeldBook(vest.state_dir() / "b.json")
    B = lambda c, h=21020.0, l=20995.0: Bar(T0, 21000.0, h, l, c, 1, "NQ", 1)      # noqa: E731
    assert b.crossed("NQ", B(21000.0)) == []
    b.entries.append(HeldEntry("h1", "NQZ6", "Buy", 1, 21015.0, 20.0, None, "d", None))
    b.entries.append(HeldEntry("s1", "NQZ6", "Sell", 1, 20998.0, 20.0, None, "d", None))
    assert [e.id for e in b.crossed("NQ", B(21016.0))] == ["h1"]
    b.entries.remove(b.get("h1"))
    assert b.crossed("NQ", B(21017.0)) == []                                   # no cross since the last push
    assert [e.id for e in b.crossed("NQ", B(20997.0))] == ["s1"]               # the Sell mirror (low already 20995)
    b2 = HeldBook(vest.state_dir() / "b2.json")
    b2.crossed("NQ", B(21010.0))
    b2.entries.append(HeldEntry("u", "NQZ6", "Buy", 1, 21025.0, 20.0, None, "d", None))
    b2.entries.append(HeldEntry("d", "NQZ6", "Sell", 1, 20990.0, 20.0, None, "d", None))
    nxt = Bar(T0 + dt.timedelta(minutes=1), 20991.0, 21031.0, 20989.0, 21000.0, 1, "NQ", 1)
    assert [e.id for e in b2.crossed("NQ", nxt)] == ["u", "d"]   # a new bar: nearest the last close (21010), not the open


def test_no_feed_refuses_a_held_entry():
    """R49: with no CME feed the desk says so at once; nothing is held."""
    ad, gw, j = mk()
    ad.feed_ok = lambda: False
    r = run(hold(ad))
    assert not r.ok and r.error == "vest: no CME price feed"
    assert ad._book.entries == [] and not gw.api("GET")                        # refused before the floor read


def test_feed_reset_forgets_the_stale_last_close():
    """R50: yesterday's last close above a Buy level must not refuse today's hold as 'already traded'."""
    ad, gw, j = mk()
    run(push(ad, bar(h=21050, c=21040)))
    assert not run(hold(ad, level=21000)).ok                                    # the level already traded (stale)
    ad.feed_reset()
    assert run(hold(ad, level=21000)).ok


# ---- final fix I6 (R60): a slippage allowance in the floor guard ---------------------------------------------
def test_floor_guard_counts_a_slippage_allowance_per_open_and_new_position():
    """slip_pts (default 5) x units ($1 a point a unit) on the new entry and on every open position."""
    def nq(sl):
        return run(ad.place_bracket(OrderRequest("NQZ6", "Buy", 1, "Market", price=21000, stop_price=21000 - sl)))
    ad, gw, _ = mk(floors={"max_drawdown_equity": 49000})
    accounts(gw, equity="50000")                                                  # room 1000
    assert not nq(46).ok and not opens(gw)                                         # 920 fits, 920 + 100 does not
    gw.positions.clear()
    assert nq(45).ok                                                               # 900 + 100: just fits
    ad, gw, _ = mk(floors={"max_drawdown_equity": 49000, "slip_pts": 2})
    accounts(gw, equity="50000")
    assert nq(46).ok                                                               # the account's own allowance: 40
    ad, gw, _ = mk(floors={"max_drawdown_equity": 49000})
    accounts(gw, equity="50000")
    gw.positions = [pos(symbol="ES-USD-PERP", openPrice="6000", quantity="20", stopLosses=[{"triggerPrice": "5970"}])]
    r = run(ad.place_bracket(OrderRequest("MNQZ6", "Buy", 1, "Market", price=21000, stop_price=21000 - 146)))
    assert not r.ok and "room $300" in r.error                                     # 1000 - (600 + 100) open


# ---- final fix R38 (R62): the restore reads the feed's bars since the book was saved --------------------------
def history(ad, *highs):
    """Feed bars (1-minute, closed): one from before the book's save, then one per high after it."""
    saved = dt.datetime.fromtimestamp(ad._book.saved_at, dt.timezone.utc).replace(second=0, microsecond=0)
    rows = [Bar(ts=saved - dt.timedelta(minutes=5), o=20980, h=20985, l=20975, c=20980, vol=1, root="NQ", minutes=1)]
    rows += [Bar(ts=saved + dt.timedelta(minutes=1 + i), o=20980, h=h, l=20975, c=20980, vol=1, root="NQ", minutes=1)
             for i, h in enumerate(highs)]
    return lambda root, minutes: rows if (root, minutes) == ("NQ", 1) else []


def test_a_level_that_traded_while_the_desk_was_down_is_dropped_never_fired_late():
    ad, gw, j = mk()
    run(hold(ad))                                                               # saved at T
    ad2, gw2, j2 = mk()                                                         # a restart: the same file
    ad2.feed_bars = history(ad2, 20990, 21004, 20992)                           # 21004 after T: it traded

    async def go():
        await push(ad2, bar(h=20995, c=20990))                                  # the first push is under the level
        await push(ad2, bar(h=21001, m=1))
    run(go())
    assert not opens(gw2) and not ad2._book.entries
    assert [k["reason"] for k in skipped(j2)] == ["restart: level traded while down"]


def test_a_level_the_history_never_reached_survives_the_restart_and_fires():
    ad, gw, j = mk()
    run(hold(ad))
    ad2, gw2, j2 = mk()
    ad2.feed_bars = history(ad2, 20990, 20996)

    async def go():
        await push(ad2, bar(h=20995, c=20990))
        await push(ad2, bar(h=21001, c=21000))
    run(go())
    assert len(opens(gw2)) == 1 and not skipped(j2)


def test_no_feed_history_back_to_the_save_drops_the_held_entries():
    ad, gw, j = mk()
    run(hold(ad))
    ad2, gw2, j2 = mk()                                                         # feed_bars: none (fail closed)

    async def go():
        await push(ad2, bar(h=20995, c=20990))
        await push(ad2, bar(h=21001, m=1))
    run(go())
    assert not opens(gw2) and not ad2._book.entries
    assert [k["reason"] for k in skipped(j2)] == ["restart: no price history since the save"]


# ---- final fix M3 (R64): a skip is journaled before the save; a failed save is logged, never raised mid-push ----------
def test_a_skip_is_journaled_even_when_the_book_cannot_be_saved(monkeypatch, caplog):
    from homebase.broker import vest_held
    ad, gw, j = mk()
    run(hold(ad))
    ad.feed_ok = lambda: False

    def disk_full(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(vest_held, "write_json", disk_full)

    async def go():
        await push(ad, bar(), bar(h=21001))
    run(go())
    assert [k["reason"] for k in skipped(j)] == ["feed down"] and not ad._book.entries and not opens(gw)
    assert "save failed" in caplog.text
