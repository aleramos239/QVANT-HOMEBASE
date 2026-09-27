"""The desk's `exits` action: an SL and/or TP added to an open position from
the chart's drag handles, always ending as ONE SL + ONE TP for the whole
position (a broker OCO when both). No broker, no network: a mock adapter."""
from __future__ import annotations

import re

import pytest

from homebase.broker.base import BrokerAdapter, OrderResult
from homebase.trading import exit_levels, parse_exits, Refused
from tests.trading_util import NQC, journal, mkdesk, quote, run


def setup(tmp_path, *, net=3, orders=(), et=(11, 0), oco="ok"):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path, et=et)
    ad = ads["a1"]
    ad.net = net
    ad.view["positions"] = [{"contract_id": 1, "symbol": NQC, "net": net, "avg_price": 100.0}] if net else []
    ad.view["orders"] = [dict(o) for o in orders]
    ad.oco_mode = oco
    ad.net_after_cancel = None             # the position after a cancel (the old exit filling mid-change)
    real_cancel = ad.cancel_order_by_id

    async def cancel(oid):
        r = await real_cancel(oid)
        if r.ok and ad.net_after_cancel is not None:
            ad.net = ad.net_after_cancel
        return r

    ad.cancel_order_by_id = cancel
    return desk, eng, ad, clock


def exits(desk, clock, *, cid="x1", last=100.0, **kw):
    body = {"client_id": cid, "accounts": ["a1"], "root": "NQ", "quotes": quote(clock, last=last), **kw}
    return run(desk.exits(body))["results"]["a1"]


SL = {"order_id": "71", "symbol": NQC, "side": "Sell", "type": "Stop", "qty": 3, "price": None,
      "stop_price": 95.0, "status": "Working", "tif": "GTC"}
TP = {"order_id": "72", "symbol": NQC, "side": "Sell", "type": "Limit", "qty": 3, "price": 110.0,
      "stop_price": None, "status": "Working", "tif": "GTC"}


# --- parsing -------------------------------------------------------------------------
@pytest.mark.parametrize("patch,msg", [
    ({}, "an sl_price or a tp_price is required"),
    ({"sl_price": -1}, "sl_price: a positive number"),
    ({"tp_price": float("inf")}, "tp_price: a positive number"),
    ({"sl_price": 95.0, "account": "a1"}, "send `accounts` or `account`, not both"),
    ({"sl_price": 95.0, "accounts": []}, "accounts: a list of 1-20 account ids"),
])
def test_parse_exits_rejects_malformed_bodies(patch, msg):
    body = {"client_id": "c", "accounts": ["a1"], "root": "NQ", **patch}
    with pytest.raises(ValueError, match=re.escape(msg)):
        parse_exits(body)


def test_parse_exits_takes_a_single_account_too():
    it = parse_exits({"client_id": "c", "account": "a2", "root": "nq", "tp_price": 110.0})
    assert it.accounts == ("a2",) and it.root == "NQ" and it.sl_price is None and it.tp_price == 110.0


# --- the pure rule -------------------------------------------------------------------------
def test_exit_levels_keeps_the_existing_half_and_checks_both_sides_of_the_last_price():
    assert exit_levels(3, [SL], None, 110.0, 100.0)[2:] == (95.0, 110.0)
    assert exit_levels(-2, [], 105.0, 90.0, 100.0)[2:] == (105.0, 90.0)
    with pytest.raises(Refused, match="stop loss must be below the last price"):
        exit_levels(3, [], 100.0, None, 100.0)                  # at the last trade: marketable
    with pytest.raises(Refused, match="target must be above the last price"):
        exit_levels(3, [], None, 99.0, 100.0)
    with pytest.raises(Refused, match="stop loss must be above"):
        exit_levels(-3, [], 99.0, None, 100.0)
    with pytest.raises(Refused, match="target must be below"):
        exit_levels(-3, [], None, 101.0, 100.0)
    with pytest.raises(Refused, match="needs a fresh price"):
        exit_levels(3, [], 95.0, None, None)


def test_exit_levels_refuses_exits_that_do_not_match_the_position():
    for exits in ([{**SL, "qty": 2}], [SL, {**SL, "order_id": "73"}], [TP, {**TP, "order_id": "74"}],
                  [{**SL, "type": "StopLimit", "price": 94.0}], [{**SL, "type": "TrailingStop"}]):
        with pytest.raises(Refused, match="exits don't match the position"):
            exit_levels(3, exits, None, 110.0, 100.0)
    with pytest.raises(Refused, match="already has a stop loss"):
        exit_levels(3, [SL], 96.0, None, 100.0)
    with pytest.raises(Refused, match="already has a target"):
        exit_levels(3, [TP], None, 111.0, 100.0)


# --- placing -------------------------------------------------------------------------------
def test_a_lone_sl_is_one_gtc_stop_for_the_whole_position(tmp_path):
    desk, eng, ad, clock = setup(tmp_path)
    r = exits(desk, clock, sl_price=95.1)
    assert r["ok"] is True
    [req] = ad.orders
    assert (req.symbol, req.side, req.qty, req.order_type, req.stop_price, req.price, req.time_in_force) == \
        (NQC, "Sell", 3, "Stop", 95.0, None, "GTC")
    assert ad.ocos == [] and ad.cancelled == []
    ev = journal(tmp_path)[-1]
    assert ev["event"] == "manual_exits" and ev["ok"] and ev["sl"] == 95.0 and ev["tp"] is None
    assert "strategy" not in ev


def test_a_lone_tp_on_a_short_is_one_buy_limit(tmp_path):
    desk, eng, ad, clock = setup(tmp_path, net=-2)
    assert exits(desk, clock, tp_price=90.0)["ok"] is True
    [req] = ad.orders
    assert (req.side, req.qty, req.order_type, req.price, req.stop_price) == ("Buy", 2, "Limit", 90.0, None)


def test_both_at_once_are_one_oco_pair(tmp_path):
    desk, eng, ad, clock = setup(tmp_path)
    r = exits(desk, clock, sl_price=95.0, tp_price=110.0)
    assert r == {"ok": True, "order_id": "901", "error": None}
    assert ad.ocos == [(NQC, "Sell", 3, 95.0, 110.0, "GTC")] and ad.orders == []
    # the pair's ids are positively chart-placed (a flatten cancels them if the cache lags)
    assert desk._is_chart_order("a1", "901") and desk._is_chart_order("a1", "902")


def test_a_tp_added_to_an_existing_sl_cancels_it_then_places_the_pair_at_the_kept_price(tmp_path):
    desk, eng, ad, clock = setup(tmp_path, orders=[SL])
    r = exits(desk, clock, tp_price=110.0)
    assert r["ok"] is True
    assert ad.cancelled == ["71"]
    assert ad.ocos == [(NQC, "Sell", 3, 95.0, 110.0, "GTC")]
    steps = journal(tmp_path)[-1]["steps"]
    assert steps["cancel"]["ok"] and steps["place"]["ok"] and "restore" not in steps


def test_an_sl_added_to_an_existing_tp_keeps_the_tp_price(tmp_path):
    desk, eng, ad, clock = setup(tmp_path, orders=[TP])
    assert exits(desk, clock, sl_price=94.0)["ok"] is True
    assert ad.cancelled == ["72"] and ad.ocos == [(NQC, "Sell", 3, 94.0, 110.0, "GTC")]


def test_a_refused_pair_puts_the_original_exit_back_at_its_price(tmp_path):
    desk, eng, ad, clock = setup(tmp_path, orders=[SL], oco="reject")
    r = exits(desk, clock, tp_price=110.0)
    assert r["ok"] is False
    assert "OCO rejected by test" in r["error"] and "original stop was put back" in r["error"]
    assert ad.cancelled == ["71"]
    [restore] = ad.orders
    assert (restore.side, restore.qty, restore.order_type, restore.stop_price, restore.time_in_force) == \
        ("Sell", 3, "Stop", 95.0, "GTC")
    assert journal(tmp_path)[-1]["steps"]["restore"]["ok"] is True


def test_a_failed_restore_is_reported_as_unprotected(tmp_path):
    desk, eng, ad, clock = setup(tmp_path, orders=[TP], oco="reject")

    async def refuse(req):
        ad.orders.append(req)
        return OrderResult(ok=False, error="limit rejected by test")

    ad.place_order = refuse
    r = exits(desk, clock, sl_price=94.0)
    assert r["ok"] is False and "THIS POSITION IS UNPROTECTED" in r["error"]
    assert [o.order_type for o in ad.orders] == ["Limit"] and ad.orders[0].price == 110.0


def test_a_pair_of_unknown_outcome_is_never_doubled_up(tmp_path):
    desk, eng, ad, clock = setup(tmp_path, orders=[SL], oco="unknown")
    r = exits(desk, clock, tp_price=110.0)
    assert r["ok"] is False and "CHECK THIS POSITION'S PROTECTION NOW" in r["error"]
    assert ad.orders == []                         # no second stop on top of a pair that may be working


def test_a_failed_cancel_changes_nothing(tmp_path):
    desk, eng, ad, clock = setup(tmp_path, orders=[SL])
    ad.fail_cancel_ids = {"71"}
    r = exits(desk, clock, tp_price=110.0)
    assert r["ok"] is False and "could not be cancelled" in r["error"]
    assert ad.ocos == [] and ad.orders == []


def test_an_exit_that_filled_during_the_cancel_places_nothing(tmp_path):
    desk, eng, ad, clock = setup(tmp_path, orders=[SL])
    ad.net_after_cancel = 0                        # the stop filled instead of cancelling: flat now
    r = exits(desk, clock, tp_price=110.0)
    assert r["ok"] is False and "NO exit was placed" in r["error"]
    assert ad.ocos == [] and ad.orders == []


def test_the_kill_landing_mid_change_puts_the_old_exit_back(tmp_path):
    desk, eng, ad, clock = setup(tmp_path, orders=[SL])
    real = ad.cancel_order_by_id

    async def cancel_then_kill(oid):
        r = await real(oid)
        desk.cfg.chart_trading.enabled = False
        return r

    ad.cancel_order_by_id = cancel_then_kill
    r = exits(desk, clock, tp_price=110.0)
    assert r["ok"] is False and "switched off" in r["error"] and "put back" in r["error"]
    assert ad.ocos == [] and [o.stop_price for o in ad.orders] == [95.0]


# --- refusals ------------------------------------------------------------------------------
def test_no_position_is_refused(tmp_path):
    desk, eng, ad, clock = setup(tmp_path, net=0)
    r = exits(desk, clock, sl_price=95.0)
    assert r["refused"] and r["error"] == f"no {NQC} position on A1 to protect"
    assert ad.orders == []


def test_a_cache_that_disagrees_with_the_broker_is_refused(tmp_path):
    desk, eng, ad, clock = setup(tmp_path)
    ad.net = 2
    assert "is changing" in exits(desk, clock, sl_price=95.0)["error"]
    ad.net_error = True
    assert "unreadable" in exits(desk, clock, cid="x2", sl_price=95.0)["error"]
    assert ad.orders == []


def test_the_bots_exits_are_never_touched(tmp_path):
    desk, eng, ad, clock = setup(tmp_path, orders=[SL])
    st = eng._state("nq930", "a1")
    st.status, st.up_sl_id = "done", "71"
    r = exits(desk, clock, tp_price=110.0)
    assert r["refused"] and "nq930 bot's exits" in r["error"]
    assert ad.cancelled == [] and ad.ocos == []


def test_partial_or_extra_exits_are_refused_before_anything_is_cancelled(tmp_path):
    for i, orders in enumerate(([{**SL, "qty": 1}], [SL, {**SL, "order_id": "73", "stop_price": 94.0}],
                                [{**SL, "type": "StopLimit", "price": 94.5, "trigger": 95.0}])):
        desk, eng, ad, clock = setup(tmp_path / str(i), orders=orders)
        r = exits(desk, clock, tp_price=110.0)
        assert r["refused"] and "exits don't match the position" in r["error"]
        assert ad.cancelled == [] and ad.ocos == [] and ad.orders == []


def test_marketable_levels_are_refused(tmp_path):
    desk, eng, ad, clock = setup(tmp_path)
    assert "stop loss must be below the last price" in exits(desk, clock, sl_price=100.0)["error"]
    assert "target must be above the last price" in exits(desk, clock, cid="x2", tp_price=99.75)["error"]
    stale = {"client_id": "x3", "accounts": ["a1"], "root": "NQ", "sl_price": 95.0,
             "quotes": quote(clock, last=100.0, age_s=60)}
    assert "needs a fresh price" in run(desk.exits(stale))["results"]["a1"]["error"]
    assert ad.orders == []


def test_a_kept_exit_already_through_the_market_is_refused(tmp_path):
    desk, eng, ad, clock = setup(tmp_path, orders=[SL])
    r = exits(desk, clock, tp_price=110.0, last=94.0)     # the old stop is above the last trade
    assert r["refused"] and "stop loss must be below" in r["error"] and ad.cancelled == []


def test_the_desk_gates_apply(tmp_path):
    desk, eng, ad, clock = setup(tmp_path, et=(9, 25))           # a1 is booked to nq930: the lock window
    assert "locked 09:20-09:35" in exits(desk, clock, sl_price=95.0)["error"]
    desk.cfg.chart_trading.enabled = False
    assert exits(desk, clock, cid="x2", sl_price=95.0)["error"] == \
        "chart trading is off — switch it on on the desk page"
    desk.cfg.chart_trading.enabled = True
    clock.set_et(11, 0)
    ad.pinned_ok = False
    assert "pinned broker account" in exits(desk, clock, cid="x3", sl_price=95.0)["error"]
    ad.pinned_ok = True
    ad.view["positions"][0]["symbol"] = None
    assert "not resolved yet" in exits(desk, clock, cid="x4", sl_price=95.0)["error"]
    assert ad.orders == []


def test_a_repeated_client_id_places_once(tmp_path):
    desk, eng, ad, clock = setup(tmp_path)
    a = exits(desk, clock, sl_price=95.0)
    b = exits(desk, clock, sl_price=95.0)
    assert a == b and len(ad.orders) == 1


def test_a_pair_on_a_broker_without_oco_is_refused_before_any_cancel(tmp_path):
    desk, eng, ad, clock = setup(tmp_path, orders=[SL])
    ad.__class__ = type("NoOco", (type(ad),), {"place_oco": BrokerAdapter.place_oco})   # the base: no OCO
    r = exits(desk, clock, tp_price=110.0)
    assert r["refused"] and "no OCO" in r["error"] and ad.cancelled == []


def test_the_route_is_wired():
    from homebase.charts import desk as chart_desk
    assert "exits" in chart_desk.ACTIONS
