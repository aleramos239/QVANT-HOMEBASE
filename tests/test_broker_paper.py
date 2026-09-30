"""The desk's paper adapter (homebase/broker/paper.py) against the REAL paper book (charts/paperbook.py): an
httpx mock transport routes the adapter's requests to PaperBooks.act / .views in this process, so every
order, bracket, modify, cancel and fill below is decided by the book's own fill law. No network, no service."""
from __future__ import annotations

import asyncio

import httpx
import pytest

from homebase.backtest.tape import et_ns
from homebase.broker.base import OrderRequest
from homebase.broker.paper import PaperAdapter, root_of
from homebase.charts.paperbook import PaperBooks
from tests.test_backtest_engine import D

T0 = et_ns(D, "09:30:00")


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class Service:
    """The chart service's /api/paper/book and /api/paper/{action}, in process."""

    def __init__(self, accounts=1):
        self.books = PaperBooks(None, roots=["NQ"], clock_ms=lambda: T0 // 1_000_000)
        for i in range(accounts - 1):
            self.books.create({"name": f"t{i}"})
        self.down = False
        self.posts: list = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("connection refused")
        if request.method == "GET" and request.url.path == "/api/paper/book":
            return httpx.Response(200, json={"accounts": self.books.views(), "limits": {}})
        action = request.url.path.rsplit("/", 1)[-1]
        import json
        body = json.loads(request.content)
        self.posts.append((action, body))
        return httpx.Response(200, json=self.books.act(action, body))

    def feed(self, prints, aid="paper", root="NQ"):
        for t, p in prints:
            hms, _, ms = t.partition(".")
            self.books.books[aid].on_print(root, et_ns(D, hms) + int(ms or 0) * 1_000_000, p)


@pytest.fixture
def svc():
    return Service()


def adapter(svc, aid="paper", **kw):
    client = httpx.AsyncClient(transport=httpx.MockTransport(svc.handler), base_url="http://paper.test")
    return PaperAdapter(aid, client=client, **kw)


def straddle_leg(side="Buy", px=101.0, sl=96.0, tp=116.0, qty=2):
    return OrderRequest(symbol="NQ", side=side, qty=qty, order_type="Stop", price=px, stop_price=sl,
                        tp_price=tp, text="homebase:entry")


def test_root_of_strips_the_contract_month():
    assert [root_of(s) for s in ("NQ", "NQZ6", "6EZ6", "MBTV6", " esz6 ")] == ["NQ", "NQ", "6E", "MBT", "ES"]


def test_connect_reads_the_account_and_a_missing_one_is_refused(svc):
    ad = adapter(svc)
    run(ad.connect())
    assert ad.connected and ad.platform == "paper" and ad.live is False
    ghost = adapter(svc, "paper-9")
    with pytest.raises(RuntimeError, match="not in the chart service's book"):
        run(ghost.connect())
    assert not ghost.connected


def test_a_bracketed_stop_entry_returns_its_legs_ids_and_fills_like_the_book_says(svc):
    ad = adapter(svc)
    run(ad.connect())
    svc.feed([("09:29:59", 100.0)])
    r = run(ad.place_bracket(straddle_leg()))
    assert r.ok and r.order_id and r.raw["sl_order_id"] and r.raw["tp_order_id"]
    view = run(ad._read())
    legs = {o["order_id"]: o for o in view["orders"]}
    assert legs[r.raw["sl_order_id"]]["status"] == "Suspended" and legs[r.raw["sl_order_id"]]["role"] == "sl"
    assert run(ad.get_order_state(r.order_id)) == {"status": "Working", "filled_qty": 0}
    svc.feed([("09:30:02", 101.0)])                                   # touch: fills at 101.25 (1 tick slip)
    assert run(ad.get_net_position("NQ")) == 2
    assert run(ad.get_order_state(r.order_id)) == {"status": "Filled", "filled_qty": 2}


def test_a_fill_is_delivered_once_with_the_order_id_the_engine_matches_on(svc):
    ad = adapter(svc)
    got = []

    async def on_fill(ev):
        got.append(ev)

    async def go():
        await ad.connect()
        await ad.observe_fills(on_fill)
        ad._task.cancel()                                             # drive _deliver by hand, no timing
        svc.feed([("09:29:59", 100.0)])
        r = await ad.place_bracket(straddle_leg())
        svc.feed([("09:30:02", 101.0)])
        await ad._deliver(await ad._read())
        await ad._deliver(await ad._read())                          # the same view again: nothing new
        return r

    r = run(go())
    assert len(got) == 1
    ev = got[0]
    assert (ev.account_id, ev.side, ev.qty, ev.price, ev.position_after) == ("paper", "Buy", 2, 101.25, 2)
    assert ev.raw["orderId"] == r.order_id and ev.symbol.startswith("NQ")


def test_fills_already_in_the_book_are_history_not_replayed(svc):
    ad = adapter(svc)
    got = []

    async def on_fill(ev):
        got.append(ev)

    async def go():
        await ad.connect()
        svc.feed([("09:29:59", 100.0)])
        await ad.place_bracket(straddle_leg())
        svc.feed([("09:30:02", 101.0)])                               # a fill BEFORE anyone watches
        await ad.connect()
        await ad.observe_fills(on_fill)
        ad._task.cancel()
        await ad._deliver(await ad._read())

    run(go())
    assert got == []


def test_the_polling_loop_delivers_a_fill(svc):
    ad = adapter(svc, poll_s=0.01)
    got = []

    async def on_fill(ev):
        got.append(ev)

    async def go():
        await ad.connect()
        await ad.observe_fills(on_fill)
        svc.feed([("09:29:59", 100.0)])
        await ad.place_bracket(straddle_leg())
        svc.feed([("09:30:02", 101.0)])
        for _ in range(400):                                          # idle polls are 1 s; the first may be slow
            if got:
                break
            await asyncio.sleep(0.01)
        await ad.close()

    run(go())
    assert [e.side for e in got] == ["Buy"]


def test_the_engines_bracket_moves_and_a_sibling_cancel_go_through(svc):
    ad = adapter(svc)
    run(ad.connect())
    svc.feed([("09:29:59", 100.0)])
    up = run(ad.place_bracket(straddle_leg("Buy", 101.0, 96.0, 116.0)))
    dn = run(ad.place_bracket(straddle_leg("Sell", 99.0, 104.0, 84.0)))
    assert up.ok and dn.ok
    assert run(ad.cancel_order_by_id(dn.order_id)).ok                 # the engine cancels the sibling on a fill
    svc.feed([("09:30:02", 101.0)])
    # _move_brackets: re-price both held-then-live legs from the actual fill, size unchanged
    assert run(ad.modify_order(up.raw["sl_order_id"], "Stop", stop_price=96.25, qty=2)).ok
    assert run(ad.modify_order(up.raw["tp_order_id"], "Limit", price=116.25, qty=2)).ok
    bad = run(ad.modify_order(up.raw["tp_order_id"], "Limit", price=117.0, qty=1))
    assert not bad.ok and "never its size" in bad.error
    prices = {o["order_id"]: (o["stop_price"], o["price"]) for o in run(ad._read())["orders"]}
    assert prices[up.raw["sl_order_id"]][0] == 96.25 and prices[up.raw["tp_order_id"]][1] == 116.25


def test_flatten_all_cancels_orders_and_closes_the_position(svc):
    ad = adapter(svc)
    run(ad.connect())
    svc.feed([("09:29:59", 100.0)])
    run(ad.place_bracket(straddle_leg()))
    svc.feed([("09:30:02", 101.0)])
    assert run(ad.get_net_position("NQZ6")) == 2
    r = run(ad.flatten_all())
    assert r.ok and r.raw["roots"] == ["NQ"]
    svc.feed([("09:30:03", 101.25), ("09:30:04", 101.25)])
    assert run(ad.get_net_position("NQ")) == 0
    assert not run(ad._read())["orders"]


def test_a_market_entry_and_a_plain_stop_order_take_their_level(svc):
    ad = adapter(svc)
    run(ad.connect())
    svc.feed([("09:29:59", 100.0)])
    m = run(ad.place_bracket(OrderRequest(symbol="NQ", side="Buy", qty=1, order_type="Market",
                                          stop_price=95.0, tp_price=110.0, text="homebase:entry")))
    assert m.ok and m.raw["sl_order_id"]
    s = run(ad.place_order(OrderRequest(symbol="NQ", side="Sell", qty=1, order_type="Stop", stop_price=90.0)))
    assert s.ok                                                      # a protective Stop: its level rides in stop_price
    posts = {a: b for a, b in svc.posts}
    assert posts["order"]["type"] == "Stop" and posts["order"]["price"] == 90.0 and "sl_price" not in posts["order"]


def test_a_service_that_is_down_is_a_failed_result_never_an_exception(svc):
    ad = adapter(svc)
    run(ad.connect())
    svc.down = True
    r = run(ad.place_order(OrderRequest(symbol="NQ", side="Buy", qty=1, order_type="Market")))
    assert not r.ok and "unreachable" in r.error
    assert not run(ad.cancel_order_by_id("1")).ok
    assert not run(ad.flatten_all()).ok


def test_the_book_refuses_what_the_desk_would_and_the_adapter_says_why(svc):
    ad = adapter(svc)
    run(ad.connect())
    svc.feed([("09:29:59", 100.0)])
    r = run(ad.place_bracket(OrderRequest(symbol="NQ", side="Buy", qty=36, order_type="Stop", price=101.0)))
    assert not r.ok and "quantity must be 1-35" in r.error


def test_a_second_paper_account_is_its_own_book(svc):
    svc2 = Service(accounts=2)
    a, b = adapter(svc2, "paper"), adapter(svc2, "paper-2")
    run(a.connect())
    run(b.connect())
    svc2.feed([("09:29:59", 100.0)], "paper")
    svc2.feed([("09:29:59", 100.0)], "paper-2")
    run(a.place_bracket(straddle_leg()))
    svc2.feed([("09:30:02", 101.0)], "paper")
    svc2.feed([("09:30:02", 101.0)], "paper-2")
    assert run(a.get_net_position("NQ")) == 2 and run(b.get_net_position("NQ")) == 0
