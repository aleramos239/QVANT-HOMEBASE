"""LiveCtx: the tester's Ctx surface, with orders turned into plain intents."""
from __future__ import annotations

import datetime as dt
import inspect
import json
import types

import pytest

from homebase.backtest.engine import Ctx, to_tick
from homebase.labrun import livectx
from homebase.labrun.livectx import LiveCtx, LiveOrder

D = dt.date(2024, 3, 5)
HOST_ONLY = {"begin", "drain"}               # the child's side of the object, not the strategy's


def ctx(root="NQ", tick=0.25, pv=20.0, qty=2, daily=None) -> LiveCtx:
    return LiveCtx(root=root, date=D, tick=tick, point_value=pv, qty=qty, daily=daily or [])


def public(obj):
    return {n for n in dir(obj) if not n.startswith("_")}


def make_tester_ctx() -> Ctx:
    sim = types.SimpleNamespace(root="NQ", date=D, tick=0.25, pv=20.0, now=0)
    return Ctx(sim, 2, [])


def test_surface_matches_the_testers_ctx():
    assert public(ctx()) - HOST_ONLY == public(make_tester_ctx())
    for n in sorted(public(Ctx)):
        a = getattr(Ctx, n)
        if callable(a):
            sa = inspect.signature(a)
            sb = inspect.signature(getattr(LiveCtx, n))
            assert [(p.name, p.default, p.kind) for p in sb.parameters.values()] == \
                   [(p.name, p.default, p.kind) for p in sa.parameters.values()], n


def test_instance_attributes_match_the_testers_ctx():
    c = ctx()
    assert (c.root, c.date, c.tick, c.point_value, c.qty, c.daily) == ("NQ", D, 0.25, 20.0, 2, [])
    assert c.move_brackets_to_fill is False
    assert (c.now_ns, c.last_price, c.flat) == (0, None, True)


def test_nothing_extra_to_reach():
    c = ctx()
    for name in ("_s", "_sim", "positions", "orders", "res"):
        with pytest.raises(AttributeError):
            getattr(c, name)
    assert not hasattr(c, "nope")


def test_stop_entry_queues_an_entry_intent_field_for_field():
    c = ctx()
    o = c.stop_entry("long", 100.1, sl=99.0, tp=103.0)
    assert isinstance(o, LiveOrder)
    assert (o.id, o.side, o.kind, o.price, o.qty, o.role) == (1, 1, "stop", 100.0, 2, "entry")
    assert (o.sl, o.tp, o.tp_rr, o.ref, o.oco, o.status) == (99.0, 103.0, None, 100.1, None, "working")
    assert (o.fill_px, o.fill_sl, o.fill_tp, o.fill_ms) == (None, None, None, None)
    assert c.drain() == [{"op": "entry", "id": 1, "kind": "stop", "side": "long", "price": 100.0, "qty": 2,
                          "own_qty": False, "sl": 99.0, "tp": 103.0, "tp_rr": None, "ref": 100.1, "move": False}]
    assert c.drain() == []


def test_limit_and_market_intents():
    c = ctx()
    c.begin(1, 50.0, True, [])
    c.move_brackets_to_fill = True
    c.limit_entry("short", 101.0, qty=3, sl=102.0, tp_rr=2.0)
    m = c.market("long", sl=49.0, ref=50.1)
    assert m.id == 2 and m.kind == "market" and m.price is None and m.qty == 2 and m.side == 1
    got = c.drain()
    assert got[0] == {"op": "entry", "id": 1, "kind": "limit", "side": "short", "price": 101.0, "qty": 3,
                      "own_qty": True, "sl": 102.0, "tp": None, "tp_rr": 2.0, "ref": 101.0, "move": True}
    assert got[1] == {"op": "entry", "id": 2, "kind": "market", "side": "long", "price": None, "qty": 2,
                      "own_qty": False, "sl": 49.0, "tp": None, "tp_rr": None, "ref": 50.1, "move": True}
    json.dumps(got, allow_nan=False)


def test_bad_side_raises_like_the_tester():
    c = ctx()
    for call in (lambda: c.stop_entry("up", 1.0), lambda: c.limit_entry("buy", 1.0), lambda: c.market("x")):
        with pytest.raises(ValueError, match="side must be 'long' or 'short'"):
            call()
    assert c.drain() == []


def test_prices_are_snapped_to_the_tick_grid():
    c = ctx("GC", 0.1, 100.0, 1)
    c.stop_entry("long", 64.04 + 0.1, sl=64.04 + 0.1 - 1.0, tp=70.0 + 0.1 + 0.1)
    i = c.drain()[0]
    assert i["price"] == to_tick(64.14, 0.1) == 64.1
    assert i["sl"] == to_tick(63.14, 0.1) == 63.1
    assert i["tp"] == to_tick(70.2, 0.1) == 70.2
    assert to_tick(64.04 + 0.1, 0.1) == livectx.to_tick(64.04 + 0.1, 0.1)


def test_oco_links_orders_to_the_first_id_and_queues_one_intent():
    c = ctx()
    a, b = c.stop_entry("long", 101, sl=100), c.stop_entry("short", 99, sl=100)
    c.oco(a, b)
    assert a.oco == b.oco == a.id
    assert c.drain()[-1] == {"op": "oco", "ids": [1, 2]}


def test_cancel_acts_at_once_and_only_on_a_working_order():
    c = ctx()
    a = c.stop_entry("long", 101, sl=100)
    c.drain()
    c.cancel(a)
    assert a.status == "cancelled"
    assert c.drain() == [{"op": "cancel", "id": 1}]
    c.cancel(a)                                  # not working any more: nothing is sent
    assert c.drain() == []


def test_cancel_loses_to_a_fill_that_beat_it():
    c = ctx()
    a = c.stop_entry("long", 101, sl=100)
    c.drain()
    c.cancel(a)
    c.begin(5, 101.0, False, [{"id": 1, "status": "filled", "fill_px": 101.25, "fill_sl": 100.0,
                               "fill_tp": None, "fill_ms": 9}])
    assert a.status == "filled" and a.fill_px == 101.25


def test_cancel_a_filled_order_sends_nothing():
    c = ctx()
    a = c.market("long", sl=1.0)
    c.drain()
    c.begin(1, 5.0, False, [{"id": 1, "status": "filled", "fill_px": 5.0, "fill_sl": 1.0, "fill_tp": None,
                             "fill_ms": 1}])
    c.cancel(a)
    assert a.status == "filled" and c.drain() == []


def test_flatten_queues_cancels_working_entries_and_reads_flat_until_begin():
    c = ctx()
    a, b = c.stop_entry("long", 101, sl=100), c.stop_entry("short", 99, sl=100)
    c.begin(2, 100.0, False, [])                 # a position is open
    assert c.flat is False
    c.flatten()
    assert c.flat is True
    assert (a.status, b.status) == ("cancelled", "cancelled")
    assert c.drain()[-1] == {"op": "flatten", "reason": "time"}
    c.flatten("eod")
    assert c.drain() == [{"op": "flatten", "reason": "eod"}]
    c.begin(3, 100.0, False, [])
    assert c.flat is False


def test_flatten_leaves_filled_orders_alone():
    c = ctx()
    a = c.market("long", sl=1.0)
    c.begin(1, 5.0, False, [{"id": 1, "status": "filled", "fill_px": 5.0, "fill_sl": 1.0, "fill_tp": None,
                             "fill_ms": 1}])
    c.flatten()
    assert a.status == "filled"


def test_begin_sets_clock_price_flat_and_applies_updates():
    c = ctx()
    a = c.stop_entry("long", 101, sl=100)
    c.begin(1_700_000_000_000_000_000, 100.5, False,
            [{"id": 1, "status": "filled", "fill_px": 101.25, "fill_sl": 100.0, "fill_tp": 103.0, "fill_ms": 123},
             {"id": 99, "status": "filled", "fill_px": 1.0, "fill_sl": None, "fill_tp": None, "fill_ms": 1}])
    assert (c.now_ns, c.last_price, c.flat) == (1_700_000_000_000_000_000, 100.5, False)
    assert (a.status, a.fill_px, a.fill_sl, a.fill_tp, a.fill_ms) == ("filled", 101.25, 100.0, 103.0, 123)


def test_plot_and_hline_intents():
    c = ctx()
    c.begin(2_000_000_000, None, True, [])
    c.plot("vwap", 1_500_000_000, 101.5)
    rec = c.hline("up", 100.0, role="entry")
    assert rec == {"name": "up", "price": 100.0, "date": "2024-03-05", "role": "entry", "t_ms": 2000}
    assert c.hline("lvl", 5.0)["role"] == "level"
    rec["name"] = "renamed"                      # display-only: nothing more is sent
    assert c.drain() == [{"op": "plot", "name": "vwap", "t_ms": 1500, "value": 101.5},
                         {"op": "hline", "name": "up", "price": 100.0, "role": "entry", "t_ms": 2000},
                         {"op": "hline", "name": "lvl", "price": 5.0, "role": "level", "t_ms": 2000}]


def test_bad_hline_role_raises_like_the_tester():
    c = ctx()
    with pytest.raises(ValueError, match="role must be one of anchor, entry, sl, tp, level"):
        c.hline("x", 1.0, role="bogus")
    assert c.drain() == []


def test_skip_intent():
    c = ctx()
    c.skip("no print before 09:30")
    assert c.drain() == [{"op": "skip", "reason": "no print before 09:30"}]


def test_ids_run_1_2_3_in_creation_order():
    c = ctx()
    ids = [c.market("long", sl=1.0).id, c.stop_entry("short", 5, sl=6).id, c.limit_entry("long", 4, sl=3).id]
    assert ids == [1, 2, 3]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_plot_or_hline_that_is_not_finite_is_dropped_and_costs_nothing(bad):
    c = ctx()
    c.begin(2_000_000_000, 100.0, True, [])
    c.plot("vwap", 1_500_000_000, bad)
    rec = c.hline("up", bad, role="entry")
    assert rec["price"] != rec["price"] or rec["price"] in (float("inf"), float("-inf"))   # the record still comes back
    assert rec["name"] == "up" and rec["role"] == "entry"
    o = c.market("long", sl=99.0)
    c.plot("ok", 1_500_000_000, 1.0)
    got = c.drain()
    assert [i["op"] for i in got] == ["entry", "plot"] and got[0]["id"] == o.id
    json.dumps(got, allow_nan=False)


@pytest.mark.parametrize("bad", [None, "x", True, False, [1.0], float("nan"), float("inf")])
def test_a_plot_or_hline_that_is_not_a_finite_number_never_raises(bad):
    c = ctx()
    c.plot("p", 1_000_000, bad)
    rec = c.hline("h", bad)
    assert rec["name"] == "h" and rec["price"] is bad
    assert c.drain() == []
    c.plot("p", 1_000_000, 2)                        # an int is a number
    c.hline("h", 3)
    assert [i["op"] for i in c.drain()] == ["plot", "hline"]
