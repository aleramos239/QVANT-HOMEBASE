"""Audit 2026-10-27, chart group: the desk's chart-trading half (homebase/desk/trading.py). No broker, no network."""
from __future__ import annotations

import asyncio
import datetime as dt

from homebase.broker.base import OrderResult
from homebase.config import StrategyCfg
from tests.test_trading_exits import SL, TP, exits, setup
from tests.trading_util import NQC, mkdesk, quote, run

WORKING = {"status": "Working", "tif": "Day", "qty": 1, "price": None, "stop_price": None}


def order(desk, clock, cid="o1", **kw):
    body = {"client_id": cid, "accounts": ["a1"], "root": "NQ", "side": "Buy", "qty": 1, "type": "Market",
            "quotes": quote(clock, last=100.0), **kw}
    return run(desk.order(body))["results"]["a1"]


def long_with_stop(ads, net=2):
    a = ads["a1"]
    a.net = net
    a.view["positions"] = [{"contract_id": 1, "symbol": NQC, "net": net, "avg_price": 100.0}]
    a.view["orders"] = [{**WORKING, "order_id": "88", "symbol": NQC, "type": "Stop", "side": "Sell",
                         "qty": net, "stop_price": 95.0}]
    return a


# --- a plain place_order timeout is not a clean refusal ----------------------------------------------
def test_a_timed_out_entry_is_reserved_and_reported_as_unknown(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path)

    async def timed_out(req):
        return OrderResult(ok=False, error="")           # tradovate.place_order on asyncio.TimeoutError
    ads["a1"].place_order = timed_out
    r = order(desk, clock)
    assert r["ok"] is False and "outcome unknown" in r["error"] and "Orders tab" in r["error"]
    assert [rv["contract"] for rv in desk._reserved["a1"]] == [NQC]      # it counts until the cache shows it


def test_a_refused_entry_with_a_reason_is_still_a_plain_refusal(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path)
    ads["a1"].fail_market = True
    r = order(desk, clock)
    assert r["error"] == "market rejected by test" and not desk._reserved.get("a1")


def test_a_timed_out_exit_pair_never_puts_the_old_exit_back(tmp_path):
    desk, eng, ad, clock = setup(tmp_path, orders=[SL])

    async def silent_oco(*a, **k):
        ad.ocos.append(a)
        return OrderResult(ok=False, error="")           # no reason, no id: it may be working
    ad.place_oco = silent_oco
    r = exits(desk, clock, tp_price=110.0)
    assert r["ok"] is False and "outcome is unknown" in r["error"]
    assert ad.orders == [], "the old stop was re-placed on top of a pair that may be working"


# --- size caps are enforced here ----------------------------------------------------------------
def test_an_order_over_the_per_order_cap_is_refused(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path)
    r = order(desk, clock, qty=11)
    assert r["refused"] and "limit of 10 an order" in r["error"] and ads["a1"].orders == []
    assert order(desk, clock, cid="o2", qty=10)["ok"] is True


def test_an_order_that_could_pass_the_position_cap_is_refused(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path)
    ads["a1"].view["positions"] = [{"contract_id": 1, "symbol": NQC, "net": 15, "avg_price": 100.0}]
    r = order(desk, clock, qty=6)
    assert r["refused"] and "limit of 20 a position" in r["error"] and ads["a1"].orders == []
    assert order(desk, clock, cid="o2", qty=5)["ok"] is True


# --- every account not paper is real money ---------------------------------------------------------
def test_a_funded_account_goes_out_as_live(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path)
    assert desk.cfg.accounts["a1"].live is False          # funded PA/LTF accounts are live=False
    assert desk.account_view("a1")["env"] == "live"


# --- exits work with chart trading off; entries do not --------------------------------------------
def test_cancel_flatten_modify_and_exits_work_with_chart_trading_off(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path, enabled=False)
    a = long_with_stop(ads)
    r = run(desk.flatten({"client_id": "f1", "accounts": ["a1"], "root": "NQ"}))["results"]["a1"]
    assert r["ok"] is True and a.flattened == [NQC]
    r = run(desk.cancel({"client_id": "c1", "account": "a1", "order_id": "88"}))["results"]["a1"]
    assert r["ok"] is True and a.cancelled == ["88"]
    r = run(desk.modify({"client_id": "m1", "account": "a1", "order_id": "88", "price": 96.0,
                         "quotes": quote(clock, last=100.0)}))["results"]["a1"]
    assert r["ok"] is True and a.modified == [("88", "Stop", 96.0)]
    assert order(desk, clock)["error"] == "chart trading is off — switch it on on the desk page"
    rv = run(desk.reverse({"client_id": "r1", "accounts": ["a1"], "root": "NQ"}))["results"]["a1"]
    assert rv["error"] == "chart trading is off — switch it on on the desk page"


def test_an_exits_swap_with_chart_trading_off_places_the_new_pair(tmp_path):
    desk, eng, ad, clock = setup(tmp_path, orders=[TP])
    desk.cfg.chart_trading.enabled = False
    r = exits(desk, clock, sl_price=95.0)
    assert r["ok"] is True and len(ad.ocos) == 1


# --- the position's own contract across the roll ----------------------------------------------------
def test_flatten_uses_the_month_the_position_is_in(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path)
    old = "NQH0" if NQC != "NQH0" else "NQM0"
    a = ads["a1"]
    a.view["positions"] = [{"contract_id": 1, "symbol": old, "net": 2, "avg_price": 100.0}]
    a.net = 2
    run(desk.flatten({"client_id": "f1", "accounts": ["a1"], "root": "NQ"}))
    assert a.flattened == [old]


def test_flatten_falls_back_to_the_front_month_when_flat(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path)
    run(desk.flatten({"client_id": "f1", "accounts": ["a1"], "root": "NQ"}))
    assert ads["a1"].flattened == [NQC]


# --- no fresh trade: the protective moves still go --------------------------------------------------
def test_a_protective_stop_moves_with_no_fresh_quote_but_an_entry_stop_does_not(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path)
    a = long_with_stop(ads)
    r = run(desk.modify({"client_id": "m1", "account": "a1", "order_id": "88", "price": 99.0}))["results"]["a1"]
    assert r["ok"] is True and a.modified == [("88", "Stop", 99.0)]
    a.view["orders"].append({**WORKING, "order_id": "89", "symbol": NQC, "type": "Stop", "side": "Buy",
                             "qty": 1, "stop_price": 110.0})
    r = run(desk.modify({"client_id": "m2", "account": "a1", "order_id": "89", "price": 111.0}))["results"]["a1"]
    assert r["refused"] and "fresh price" in r["error"]


def test_a_stop_can_be_added_with_no_fresh_quote_on_the_safe_side_of_the_average(tmp_path):
    desk, eng, ad, clock = setup(tmp_path)
    r = exits(desk, clock, sl_price=95.0, quotes=None)        # avg 100: below it, safe
    assert r["ok"] is True
    r = exits(desk, clock, cid="x2", sl_price=105.0, quotes=None)
    assert r["refused"]


# --- reverse ------------------------------------------------------------------------------------------
def test_reverse_is_not_blocked_by_a_chart_entry_that_already_filled(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path)
    a = ads["a1"]
    a.net = 2
    a.view["positions"] = [{"contract_id": 1, "symbol": NQC, "net": 2, "avg_price": 100.0}]
    assert order(desk, clock)["ok"] is True                      # order id "plain", reserved for 10 s
    a.order_status["plain"] = "Filled"
    r = run(desk.reverse({"client_id": "r1", "accounts": ["a1"], "root": "NQ"}))["results"]["a1"]
    assert r["ok"] is True, r


def test_reverse_opens_nothing_when_the_flatten_closed_another_size(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path)
    a = ads["a1"]
    a.net = 2

    async def flatten_found_flat(symbol):                     # the stop filled between the two reads
        a.flattened.append(symbol)
        return OrderResult(ok=True, raw={"net_before": 0})
    a.flatten_symbol = flatten_found_flat
    r = run(desk.reverse({"client_id": "r1", "accounts": ["a1"], "root": "NQ"}))["results"]["a1"]
    assert r["ok"] is False and "flattened only" in r["error"] and a.orders == []


# --- the pause covers a levels fire too ---------------------------------------------------------------
def test_the_fire_pause_covers_a_levels_strategy(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path)
    desk.cfg.strategies["lv"] = StrategyCfg(symbol="NQ", qty=1, offset_pts=0.0, sl_pts=0.0, tp_pts=0.0,
                                            kind="levels", enabled=True, self_fire=True, fire_et="11:05:00")
    now = dt.datetime(2026, 9, 14, 11, 4, 55)
    assert desk._other_fire_near(now, 10.0) is True


# --- repair pass ---------------------------------------------------------------------------------------
def test_a_reverse_whose_open_leg_times_out_is_reserved_and_reported_as_unknown(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path)
    a = ads["a1"]
    a.net = 2

    async def timed_out(req):
        return OrderResult(ok=False, error="")
    a.place_order = a.place_bracket = timed_out
    r = run(desk.reverse({"client_id": "r1", "accounts": ["a1"], "root": "NQ"}))["results"]["a1"]
    assert r["ok"] is False and "outcome unknown" in r["error"] and "Orders tab" in r["error"]
    assert [rv["contract"] for rv in desk._reserved["a1"] if rv.get("reverse")] == [NQC]


def test_a_chart_entry_limit_cannot_be_repriced_with_chart_trading_off(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path, enabled=False)
    a = ads["a1"]
    a.view["orders"] = [{**WORKING, "order_id": "70", "symbol": NQC, "type": "Limit", "side": "Buy",
                         "qty": 1, "price": 90.0}]
    r = run(desk.modify({"client_id": "m1", "account": "a1", "order_id": "70", "price": 120.0,
                         "quotes": quote(clock, last=100.0)}))["results"]["a1"]
    assert r["refused"] and "chart trading is off" in r["error"] and a.modified == []


def test_a_reducing_order_is_not_blocked_by_the_position_cap(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path)
    a = ads["a1"]
    a.view["positions"] = [{"contract_id": 1, "symbol": NQC, "net": 10, "avg_price": 100.0}]
    a.view["orders"] = [{**WORKING, "order_id": "81", "symbol": NQC, "type": "Stop", "side": "Sell",
                         "qty": 10, "stop_price": 95.0},
                        {**WORKING, "order_id": "82", "symbol": NQC, "type": "Limit", "side": "Sell",
                         "qty": 10, "price": 110.0}]
    desk.cfg.chart_trading.max_position_qty = 12
    assert order(desk, clock, side="Sell", qty=10)["ok"] is True       # closes it: never grows |net|
    r = order(desk, clock, cid="o2", side="Buy", qty=5)                # grows it: 10 + 10 + 5 working > cap
    assert r["refused"] and "a position" in r["error"]


def test_a_pre_send_error_is_a_plain_refusal_not_an_unknown_outcome(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path)

    async def bad_request(req):
        raise ValueError("bad request: nothing sent")
    ads["a1"].place_order = bad_request
    r = order(desk, clock)
    assert r["ok"] is False and "outcome unknown" not in r["error"] and not desk._reserved.get("a1")


def test_a_timeout_exception_is_an_unknown_outcome(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path)

    async def hang(req):
        raise asyncio.TimeoutError()
    ads["a1"].place_order = hang
    r = order(desk, clock)
    assert "outcome unknown" in r["error"] and [rv["contract"] for rv in desk._reserved["a1"]] == [NQC]
