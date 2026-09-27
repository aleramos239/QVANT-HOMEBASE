"""Stop Limit + time-in-force on the chart's order path: parsing, the price
guards, what reaches the adapter, the journal, and modify. No broker, no network."""
from __future__ import annotations

import re

import pytest

from homebase.trading import TIFS, TYPES, parse_order
from tests.trading_util import NQC, journal, mkdesk, quote, run

BASE = {"client_id": "c", "accounts": ["a1"], "root": "NQ", "side": "Buy", "qty": 1}


def order(desk, **kw):
    body = {"client_id": kw.pop("cid", "c1"), "accounts": ["a1"], "root": "NQ", "side": "Buy",
            "qty": 1, "type": "StopLimit", **kw}
    return run(desk.order(body))["results"]["a1"]


def test_types_and_tifs():
    assert TYPES == ("Market", "Limit", "Stop", "StopLimit")
    assert TIFS == ("Day", "GTC")


# --- parsing ----------------------------------------------------------------------
@pytest.mark.parametrize("patch,msg", [
    ({"type": "StopLimit", "price": 101.0}, "trigger_price is required"),
    ({"type": "StopLimit", "trigger_price": 101.0}, "price is required"),
    ({"type": "StopLimit", "price": 101.0, "trigger_price": -1.0}, "trigger_price: a positive number"),
    ({"type": "Limit", "price": 101.0, "trigger_price": 100.0},
     "only a Stop Limit order carries a trigger_price"),
    ({"type": "Stop", "price": 101.0, "trigger_price": 100.0},
     "only a Stop Limit order carries a trigger_price"),
    ({"type": "Market", "trigger_price": 100.0}, "only a Stop Limit order carries a trigger_price"),
    ({"type": "Market", "tif": "IOC"}, "tif: Day or GTC"),
    ({"type": "Market", "tif": "day"}, "tif: Day or GTC"),
    ({"type": "Trailing"}, "type: Market, Limit, Stop or StopLimit"),
])
def test_parse_refuses(patch, msg):
    with pytest.raises(ValueError, match=re.escape(msg)):
        parse_order({**BASE, **patch})


def test_parse_reads_the_trigger_and_the_tif():
    it = parse_order({**BASE, "type": "StopLimit", "price": 102.0, "trigger_price": 101.0,
                      "tif": "GTC"})
    assert (it.type, it.price, it.trigger_price, it.tif) == ("StopLimit", 102.0, 101.0, "GTC")
    it = parse_order({**BASE, "type": "Limit", "price": 99.0})
    assert (it.trigger_price, it.tif) == (None, "Day")          # tif defaults to Day


# --- check_prices ------------------------------------------------------------------
def test_the_trigger_is_checked_like_a_stop_against_the_last_price(tmp_path):
    desk, eng, ads, clock, mono, _ = mkdesk(tmp_path)
    q = quote(clock, last=100.25)
    assert order(desk, price=101.0, trigger_price=100.0, quotes=q)["error"] == \
        "a buy stop limit's trigger must be above the last price (100.25)"
    assert order(desk, cid="c2", side="Sell", price=100.0, trigger_price=100.5, quotes=q)["error"] == \
        "a sell stop limit's trigger must be below the last price (100.25)"
    assert order(desk, cid="c3", price=102.0, trigger_price=101.0)["error"] == \
        f"no trade in {NQC} in the last 30 s — a stop limit order needs a fresh price"
    assert ads["a1"].orders == [] and ads["a1"].brackets == []


def test_the_limit_must_be_on_the_fill_allowing_side_of_the_trigger(tmp_path):
    desk, eng, ads, clock, mono, _ = mkdesk(tmp_path)
    q = quote(clock, last=100.0)
    assert order(desk, price=100.75, trigger_price=101.0, quotes=q)["error"] == \
        "a buy stop limit's limit must be at or above its trigger"
    assert order(desk, cid="c2", side="Sell", price=99.25, trigger_price=99.0, quotes=q)["error"] == \
        "a sell stop limit's limit must be at or below its trigger"
    mono.t += 1
    assert order(desk, cid="c3", price=101.0, trigger_price=101.0, quotes=q)["ok"] is True   # equal is fine
    assert order(desk, cid="c4", side="Sell", price=98.5, trigger_price=99.0, quotes=q)["ok"] is True


def test_the_limit_must_be_within_100_ticks_of_the_trigger(tmp_path):
    desk, eng, ads, clock, mono, _ = mkdesk(tmp_path)
    q = quote(clock, last=100.0)
    # NQ ticks are 0.25: 100 ticks = 25 points
    assert order(desk, price=126.25, trigger_price=101.0, quotes=q)["error"] == \
        "a stop limit's limit must be within 100 ticks of its trigger"
    assert order(desk, cid="c2", side="Sell", price=73.75, trigger_price=99.0, quotes=q)["error"] == \
        "a stop limit's limit must be within 100 ticks of its trigger"
    assert order(desk, cid="c3", price=126.0, trigger_price=101.0, quotes=q)["ok"] is True


def test_trigger_and_limit_are_tick_rounded_and_reach_the_adapter_apart(tmp_path):
    desk, eng, ads, clock, *_ = mkdesk(tmp_path)
    r = order(desk, price=102.13, trigger_price=101.06, tif="GTC", quotes=quote(clock, last=100.0))
    assert r["ok"] is True
    o = ads["a1"].orders[-1]
    assert (o.order_type, o.price, o.trigger_price, o.stop_price, o.time_in_force, o.symbol) == \
        ("StopLimit", 102.25, 101.0, None, "GTC", NQC)


def test_the_bracket_ref_is_the_limit_price(tmp_path):
    desk, eng, ads, clock, *_ = mkdesk(tmp_path)
    q = quote(clock, last=100.0)
    # trigger 101 / limit 103: an SL at 103.5 is above the LIMIT (the entry) -> refused, although
    # a TP at 102 is above the trigger it is below the limit -> refused too
    assert order(desk, price=103.0, trigger_price=101.0, sl_price=103.5, quotes=q)["error"] == \
        "the stop loss must be on the losing side of the entry"
    assert order(desk, cid="c2", price=103.0, trigger_price=101.0, tp_price=102.0, quotes=q)["error"] == \
        "the target must be on the winning side of the entry"
    r = order(desk, cid="c3", price=103.0, trigger_price=101.0, sl_price=102.0, tp_price=110.0,
              quotes=q)
    assert r["ok"] is True
    b = ads["a1"].brackets[-1]
    assert (b.order_type, b.price, b.trigger_price, b.stop_price, b.tp_price, b.time_in_force) == \
        ("StopLimit", 103.0, 101.0, 102.0, 110.0, "Day")
    assert ads["a1"].orders == []


# --- what the other types send, and the journal ----------------------------------------------
def test_other_types_send_no_trigger_and_day_unless_asked(tmp_path):
    desk, eng, ads, clock, mono, _ = mkdesk(tmp_path)
    assert order(desk, type="Limit", price=99.0)["ok"] is True
    o = ads["a1"].orders[-1]
    assert (o.trigger_price, o.time_in_force) == (None, "Day")
    assert order(desk, cid="c2", type="Limit", price=99.0, tif="GTC")["ok"] is True
    assert ads["a1"].orders[-1].time_in_force == "GTC"


def test_the_journal_records_the_trigger_and_the_tif(tmp_path):
    desk, eng, ads, clock, *_ = mkdesk(tmp_path)
    order(desk, price=102.0, trigger_price=101.0, tif="GTC", quotes=quote(clock, last=100.0))
    order(desk, cid="c2", type="Market")
    placed = [e for e in journal(tmp_path) if e["event"] == "manual_order"]
    assert (placed[0]["type"], placed[0]["price"], placed[0]["trigger"], placed[0]["tif"]) == \
        ("StopLimit", 102.0, 101.0, "GTC")
    assert (placed[1]["type"], placed[1]["trigger"], placed[1]["tif"]) == ("Market", None, "Day")
    refused = order(desk, cid="c3", price=100.0, trigger_price=99.0, quotes=quote(clock, last=100.0))
    assert refused["refused"] is True
    assert journal(tmp_path)[-1]["event"] == "manual_refused"


# --- modify ----------------------------------------------------------------------------
def test_a_stop_limit_order_cannot_be_moved(tmp_path):
    desk, eng, ads, clock, *_ = mkdesk(tmp_path)
    ads["a1"].view["orders"] = [{"order_id": "80", "symbol": NQC, "side": "Buy", "type": "StopLimit",
                                 "qty": 1, "price": 102.0, "stop_price": 101.0, "trigger": 101.0,
                                 "status": "Working"}]
    r = run(desk.modify({"client_id": "m1", "account": "a1", "order_id": "80", "price": 103.0,
                         "quotes": quote(clock, last=100.0)}))["results"]["a1"]
    assert r["error"] == "Stop Limit orders can't be moved — cancel and place again"
    assert ads["a1"].modified == []
