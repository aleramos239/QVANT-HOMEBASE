"""Every chart-trading guard, the bot lock (incl. DST), placement across
accounts, and the journal. No broker, no network."""
from __future__ import annotations

import asyncio
import datetime as dt
import re

import pytest

from homebase.broker.base import OrderResult
from homebase.engine import ET
from homebase.trading import in_lock_window, parse_order
from tests.trading_util import ESC, MNQC, NQC, journal, mkdesk, quote, run

UTC = dt.timezone.utc


def order(desk, **kw):
    body = {"client_id": kw.pop("cid", "c1"), "accounts": kw.pop("accounts", ["a1"]),
            "root": kw.pop("root", "NQ"), "side": "Buy", "qty": 1, "type": "Market", **kw}
    return run(desk.order(body))["results"]


WORKING = {"order_id": "77", "symbol": NQC, "side": "Buy", "type": "Limit", "qty": 2,
           "price": 99.0, "stop_price": None, "status": "Working"}


async def _ok(oid):
    return OrderResult(ok=True, order_id=oid)


# --- parsing ---------------------------------------------------------------------
@pytest.mark.parametrize("patch,msg", [
    ({"side": "buy"}, "side: Buy or Sell"),
    ({"type": "Trailing"}, "type: Market, Limit, Stop or StopLimit"),
    ({"qty": 1.5}, "qty: a whole number"),
    ({"qty": True}, "qty: a whole number"),
    ({"type": "Limit"}, "price is required"),
    ({"price": 100.0}, "a Market order carries no price"),
    ({"accounts": []}, "accounts: a list of 1-20 account ids"),
    ({"root": "N Q"}, "root: a symbol root such as NQ"),
    ({"client_id": ""}, "client_id: a string of 1-64 characters"),
    ({"sl_price": float("nan")}, "sl_price: a positive number"),
])
def test_parse_order_rejects_malformed_bodies(patch, msg):
    body = {"client_id": "c", "accounts": ["a1"], "root": "NQ", "side": "Buy", "qty": 1,
            "type": "Market", **patch}
    with pytest.raises(ValueError, match=re.escape(msg)):
        parse_order(body)


# --- guards 1 and 2 ----------------------------------------------------------------
def test_chart_trading_off_refuses_everything(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path, enabled=False)
    res = order(desk, accounts=["a1", "a2"])
    assert all(r["ok"] is False and r["refused"] for r in res.values())
    assert res["a1"]["error"] == "chart trading is off — switch it on on the desk page"
    assert ads["a1"].orders == [] and ads["a2"].orders == []
    ev = [e for e in journal(tmp_path) if e["event"] == "manual_refused"]
    assert len(ev) == 2 and ev[0]["action"] == "order" and "strategy" not in ev[0]


def test_unknown_disconnected_unpinned_unseeded_accounts_are_refused(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    assert order(desk, accounts=["zz"])["zz"]["error"] == "unknown account 'zz'"
    ads["a1"]._connected = False
    desk.acct_status["a1"] = {"connected": False, "error": "account A1 not on this login (has: A3)"}
    assert order(desk, cid="c2")["a1"]["error"] == \
        "A1 is not connected (account A1 not on this login (has: A3))"
    ads["a1"]._connected = True
    ads["a1"].pinned_ok = False
    assert "pinned broker account" in order(desk, cid="c3")["a1"]["error"]
    ads["a1"].pinned_ok = True
    ads["a1"].view["seeded"] = False
    assert "not loaded yet" in order(desk, cid="c4")["a1"]["error"]
    assert ads["a1"].orders == []


def test_a_root_without_a_contract_spec_is_refused(tmp_path):
    desk, *_ = mkdesk(tmp_path)
    assert order(desk, root="ZZZ")["a1"]["error"] == \
        "ZZZ has no contract spec on the desk — not tradable from the chart"


# --- guard 3: quantity -----------------------------------------------------------------
def test_quantity_limits(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    assert order(desk, qty=0)["a1"]["error"] == "quantity must be 1-10"
    assert order(desk, cid="c2", qty=11)["a1"]["error"] == "quantity must be 1-10"
    assert order(desk, cid="c3", qty=10)["a1"]["ok"] is True
    assert ads["a1"].orders[-1].qty == 10


def test_position_limit_counts_the_position_and_every_working_order(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a1"].view["positions"] = [{"contract_id": 1, "symbol": NQC, "net": 18, "avg_price": 100.0}]
    assert order(desk, qty=3)["a1"]["error"] == \
        f"that could take {NQC} on A1 to 21 contracts (limit 20)"
    assert order(desk, cid="c2", qty=3, side="Sell")["a1"]["ok"] is True       # reducing
    ads["a1"].view["positions"] = [{"contract_id": 2, "symbol": ESC, "net": 20, "avg_price": 5000.0}]
    ads["a1"].view["orders"] = [{**WORKING, "qty": 15}]
    assert order(desk, cid="c3", qty=6)["a1"]["error"].endswith("to 21 contracts (limit 20)")
    assert order(desk, cid="c4", qty=5)["a1"]["ok"] is True                     # ES never counts


def test_an_unresolved_contract_in_the_cache_refuses_orders(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a1"].view["positions"] = [{"contract_id": 9, "symbol": None, "net": 1, "avg_price": 1.0}]
    assert order(desk)["a1"]["error"] == \
        "a position or order's contract is not resolved yet — try again in a moment"


# --- guard 4: the bot lock ---------------------------------------------------------------
@pytest.mark.parametrize("hh,mm,locked", [(9, 19, False), (9, 20, True), (9, 34, True), (9, 35, False)])
def test_bot_lock_window_on_a_booked_account(tmp_path, hh, mm, locked):
    desk, eng, ads, *_ = mkdesk(tmp_path, et=(hh, mm))
    r = order(desk, accounts=["a1", "a2"])
    assert (r["a1"]["ok"] is False) is locked
    if locked:
        assert r["a1"]["error"] == f"{NQC} on A1 is locked 09:20-09:35 ET for the nq930 bot"
    assert r["a2"]["ok"] is True                        # not booked: never window-locked


def test_lock_covers_mnq_but_not_es_and_not_weekends(tmp_path):
    desk, eng, ads, clock, *_ = mkdesk(tmp_path, et=(9, 25))
    assert order(desk, root="MNQ")["a1"]["error"] == \
        f"{MNQC} on A1 is locked 09:20-09:35 ET for the nq930 bot"
    assert order(desk, cid="c2", root="ES")["a1"]["ok"] is True
    clock.dt = dt.datetime(2026, 9, 19, 13, 25, tzinfo=UTC)          # Saturday 09:25 ET
    assert order(desk, cid="c3")["a1"]["ok"] is True


def test_lock_window_follows_new_york_time_across_dst(tmp_path):
    def et(y, m, d, hh, mm):
        return dt.datetime(y, m, d, hh, mm, tzinfo=UTC).astimezone(ET)
    # Fri 2026-03-06 is EST (UTC-5): 14:25 UTC = 09:25 ET locked; 13:25 UTC = 08:25 open
    assert in_lock_window(et(2026, 3, 6, 14, 25)) and not in_lock_window(et(2026, 3, 6, 13, 25))
    # Mon 2026-03-09 is EDT (DST began Sun 03-08): 13:25 UTC = 09:25 locked; 14:25 = 10:25 open
    assert in_lock_window(et(2026, 3, 9, 13, 25)) and not in_lock_window(et(2026, 3, 9, 14, 25))
    # Mon 2026-11-02 is EST again (DST ended Sun 11-01)
    assert in_lock_window(et(2026, 11, 2, 14, 25)) and not in_lock_window(et(2026, 11, 2, 13, 25))
    desk, eng, ads, clock, mono, _ = mkdesk(tmp_path)
    clock.dt = dt.datetime(2026, 3, 9, 13, 25, tzinfo=UTC)
    assert "locked 09:20-09:35" in order(desk)["a1"]["error"]
    clock.dt = dt.datetime(2026, 3, 6, 13, 25, tzinfo=UTC)
    assert order(desk, cid="c2")["a1"]["ok"] is True


@pytest.mark.parametrize("status,locked", [("placing", True), ("placed", True), ("live", True),
                                           ("done", False), ("error", False), ("idle", False)])
def test_the_bots_day_state_locks_its_symbol_on_its_account(tmp_path, status, locked):
    desk, eng, ads, *_ = mkdesk(tmp_path)                             # 11:00 ET: outside the window
    eng._state("nq930", "a1").status = status
    r = order(desk)["a1"]
    assert (not r["ok"]) is locked
    if locked:
        assert r["error"] == (f"{NQC} on A1 belongs to the nq930 bot right now ({status}) "
                              "— use the desk's Kill in an emergency")
    assert order(desk, cid="c2", root="ES")["a1"]["ok"] is True


# --- guard 5: rate -------------------------------------------------------------------------
def test_at_most_five_actions_a_second_per_account(tmp_path):
    desk, eng, ads, clock, mono, _ = mkdesk(tmp_path)
    oks = [order(desk, cid=f"c{i}")["a1"]["ok"] for i in range(6)]
    assert oks == [True] * 5 + [False]
    assert order(desk, cid="c5")["a1"]["error"] == "too fast — at most 5 actions a second on A1"
    assert order(desk, cid="c9", accounts=["a2"])["a2"]["ok"] is True          # per account
    mono.t += 1.0
    assert order(desk, cid="c10")["a1"]["ok"] is True


# --- guard 6: prices -------------------------------------------------------------------------
def test_stop_orders_need_a_fresh_price_on_the_right_side(tmp_path):
    desk, eng, ads, clock, mono, _ = mkdesk(tmp_path)
    q = quote(clock, last=100.25)
    assert order(desk, type="Stop", price=100.0, quotes=q)["a1"]["error"] == \
        "a buy stop must be above the last price (100.25)"
    assert order(desk, cid="c2", type="Stop", side="Sell", price=100.5, quotes=q)["a1"]["error"] == \
        "a sell stop must be below the last price (100.25)"
    assert order(desk, cid="c3", type="Stop", price=101.0)["a1"]["error"] == \
        f"no trade in {NQC} in the last 30 s — a stop order needs a fresh price"
    stale = quote(clock, last=100.25, age_s=31)
    assert "no trade" in order(desk, cid="c4", type="Stop", price=101.0, quotes=stale)["a1"]["error"]
    mono.t += 1
    assert order(desk, cid="c5", type="Stop", price=101.0, quotes=q)["a1"]["ok"] is True
    o = ads["a1"].orders[-1]
    assert (o.order_type, o.price, o.symbol) == ("Stop", 101.0, NQC)


def test_prices_are_tick_rounded(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    assert order(desk, type="Limit", price=100.1)["a1"]["ok"] is True
    assert ads["a1"].orders[-1].price == 100.0
    assert order(desk, cid="c2", type="Limit", price=100.13, sl_price=95.06,
                 tp_price=110.2)["a1"]["ok"] is True
    b = ads["a1"].brackets[-1]
    assert (b.price, b.stop_price, b.tp_price) == (100.25, 95.0, 110.25)


def test_bracket_levels_must_sit_on_the_right_sides(tmp_path):
    desk, eng, ads, clock, *_ = mkdesk(tmp_path)
    assert order(desk, type="Limit", price=100.0, sl_price=101.0)["a1"]["error"] == \
        "the stop loss must be on the losing side of the entry"
    assert order(desk, cid="c2", type="Limit", side="Sell", price=100.0,
                 tp_price=101.0)["a1"]["error"] == "the target must be on the winning side of the entry"
    assert order(desk, cid="c3", sl_price=99.0)["a1"]["error"] == \
        f"no trade in {NQC} in the last 30 s — a bracket on a market order needs a fresh price"
    r = order(desk, cid="c4", sl_price=99.0, tp_price=102.0, quotes=quote(clock, last=100.0))["a1"]
    assert r["ok"] is True and ads["a1"].brackets[-1].order_type == "Market"
    assert ads["a1"].orders == []                          # brackets go through place_bracket only


# --- placement, dedup, journal -----------------------------------------------------------------
def test_one_order_goes_to_every_ticked_account_with_a_result_each(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a2"]._connected = False
    r = order(desk, accounts=["a1", "a2", "a1"])
    assert list(r) == ["a1", "a2"]
    assert r["a1"] == {"ok": True, "order_id": "plain", "error": None}
    assert r["a2"]["ok"] is False and r["a2"]["error"] == "A2 is not connected"
    placed = [e for e in journal(tmp_path) if e["event"] == "manual_order"]
    assert len(placed) == 1 and placed[0]["account"] == "a1" and placed[0]["contract"] == NQC
    assert placed[0]["source"] == "chart" and "strategy" not in placed[0]


def test_accounts_are_placed_concurrently(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)

    async def go():
        both, started = asyncio.Event(), []

        async def slow(req, ad):
            started.append(ad.account_id)
            if len(started) == 2:
                both.set()
            await asyncio.wait_for(both.wait(), 1.0)    # a sequential placement would time out here
            return OrderResult(ok=True, order_id=ad.account_id)

        for ad in ads.values():
            ad.place_order = (lambda req, ad=ad: slow(req, ad))
        return await desk.order({"client_id": "c", "accounts": ["a1", "a2"], "root": "NQ",
                                 "side": "Buy", "qty": 1, "type": "Market"})

    out = run(go())["results"]
    assert out["a1"]["order_id"] == "a1" and out["a2"]["order_id"] == "a2"


def test_a_repeated_client_id_returns_the_first_result_without_placing_again(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    first = order(desk)
    assert order(desk) == first and len(ads["a1"].orders) == 1


def test_every_action_publishes_its_result(tmp_path):
    desk, *_ = mkdesk(tmp_path)

    async def go():
        q = desk.subscribe()
        await desk.order({"client_id": "c", "accounts": ["a1"], "root": "NQ", "side": "Buy",
                          "qty": 1, "type": "Market"})
        return q.get_nowait()

    ev, data = run(go())
    assert ev == "result" and data["client_id"] == "c" and data["action"] == "order"
    assert data["results"]["a1"]["ok"] is True


# --- modify / cancel ---------------------------------------------------------------------------
def test_modify_moves_a_manual_order_tick_rounded(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a1"].view["orders"] = [dict(WORKING)]
    r = run(desk.modify({"client_id": "m1", "account": "a1", "order_id": "77", "price": 98.6}))
    assert r["results"]["a1"] == {"ok": True, "order_id": "77", "error": None}
    assert ads["a1"].modified == [("77", "Limit", 98.5)]
    assert [e["event"] for e in journal(tmp_path)][-1] == "manual_modify"


def test_modify_refuses_bot_orders_unknown_orders_and_wrong_side_stops(tmp_path):
    desk, eng, ads, clock, *_ = mkdesk(tmp_path)
    st = eng._state("nq930", "a1")
    st.status, st.up_sl_id = "done", "55"
    stop = {**WORKING, "type": "Stop", "side": "Sell", "price": None, "stop_price": 95.0}
    ads["a1"].view["orders"] = [dict(WORKING), {**stop, "order_id": "55"}, {**stop, "order_id": "56"}]

    def m(cid, oid, px, **kw):
        body = {"client_id": cid, "account": "a1", "order_id": oid, "price": px, **kw}
        return run(desk.modify(body))["results"]["a1"]

    assert m("m1", "55", 96.0)["error"] == \
        "order 55 belongs to the nq930 bot — it cannot be changed from the chart"
    assert m("m2", "99", 96.0)["error"] == "order 99 is not working on A1"
    assert m("m3", "56", 101.0, quotes=quote(clock, last=100.0))["error"] == \
        "a sell stop must be below the last price (100.0)"
    assert m("m4", "56", 96.0, quotes=quote(clock, last=100.0))["ok"] is True
    assert ads["a1"].modified == [("56", "Stop", 96.0)]


def test_cancel_by_id_stays_allowed_in_the_window_but_never_for_bot_orders(tmp_path):
    # fix round 1: while the bot is busy only an order placed FROM THE CHART
    # is positively manual, so "77" is placed through the desk at 09:00 first
    desk, eng, ads, clock, *_ = mkdesk(tmp_path, et=(9, 0))
    ads["a1"].place_order = lambda req: _ok("77")
    assert order(desk, type="Limit", price=99.0, cid="p77")["a1"]["order_id"] == "77"
    clock.set_et(9, 25)
    st = eng._state("nq930", "a1")
    st.status, st.upper_id = "placed", "60"
    ads["a1"].view["orders"] = [dict(WORKING), {**WORKING, "order_id": "60", "type": "Stop"}]

    def c(cid, oid):
        return run(desk.cancel({"client_id": cid, "account": "a1", "order_id": oid}))["results"]["a1"]

    assert c("x1", "77")["ok"] is True
    assert c("x2", "60")["error"] == \
        "order 60 belongs to the nq930 bot — it cannot be changed from the chart"
    st.status = "placing"
    assert c("x3", "77")["error"].startswith(f"{NQC} on A1 belongs to the nq930 bot right now (placing)")
    assert ads["a1"].cancelled == ["77"]
    assert [e["event"] for e in journal(tmp_path) if e["event"].startswith("manual_")] == \
        ["manual_order", "manual_cancel", "manual_refused", "manual_refused"]


# --- flatten / cancel-symbol / reverse ------------------------------------------------------------
def test_flatten_and_cancel_symbol_are_symbol_scoped_and_journaled(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    body = {"client_id": "f1", "accounts": ["a1", "a2"], "root": "NQ"}
    r = run(desk.flatten(body))["results"]
    assert r["a1"]["ok"] and r["a2"]["ok"]
    assert ads["a1"].flattened == [NQC] and ads["a2"].flattened == [NQC]
    run(desk.cancel_symbol({**body, "client_id": "f2"}))
    assert ads["a1"].sym_cancelled == [NQC] and ads["a2"].sym_cancelled == [NQC]
    ev = [e for e in journal(tmp_path) if e["event"] in ("manual_flatten", "manual_cancel")]
    assert [e["event"] for e in ev] == ["manual_flatten"] * 2 + ["manual_cancel"] * 2
    assert all(e["source"] == "chart" and "strategy" not in e for e in ev)


def test_flatten_is_locked_in_the_window_for_the_booked_account_only(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path, et=(9, 25))
    r = run(desk.flatten({"client_id": "f1", "accounts": ["a1", "a2"], "root": "NQ"}))["results"]
    assert r["a1"]["error"] == f"{NQC} on A1 is locked 09:20-09:35 ET for the nq930 bot"
    assert r["a2"]["ok"] is True and ads["a1"].flattened == []


def test_reverse_flattens_then_opens_the_other_side(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a1"].net = 2
    r = run(desk.reverse({"client_id": "r1", "accounts": ["a1"], "root": "NQ"}))["results"]["a1"]
    assert r["ok"] is True and ads["a1"].flattened == [NQC]
    o = ads["a1"].orders[-1]
    assert (o.symbol, o.side, o.qty, o.order_type) == (NQC, "Sell", 2, "Market")
    assert [e["step"] for e in journal(tmp_path) if e["event"] == "manual_reverse"] == ["flatten", "open"]


def test_reverse_refuses_flat_oversized_and_a_failed_flatten(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)

    def rv(cid):
        return run(desk.reverse({"client_id": cid, "accounts": ["a1"], "root": "NQ"}))["results"]["a1"]

    assert rv("r1")["error"] == f"no {NQC} position on A1 to reverse"
    ads["a1"].net = -11
    assert rv("r2")["error"] == "reversing 11 is over the per-order limit (10)"
    ads["a1"].net, ads["a1"].fail_flatten = -3, True
    assert rv("r3")["error"] == "flatten failed: flatten rejected by test — not reversed"
    assert ads["a1"].orders == []


# --- ruling 3: an unseeded / missing cache is never read as flat ---------------------------------
def test_no_cached_view_refuses_every_action_and_nothing_reaches_the_broker(tmp_path):
    desk, eng, ads, clock, mono, _ = mkdesk(tmp_path)
    ads["a1"].trade_view = lambda: None                 # an adapter with no cache at all
    assert "not loaded yet" in order(desk)["a1"]["error"]
    ads["a1"].trade_view = lambda: {"seeded": False, "positions": [], "orders": []}
    ads["a1"].net = 3                                   # the broker holds a position the cache has not
    body = {"accounts": ["a1"], "root": "NQ"}
    for i, act in enumerate((desk.flatten, desk.cancel_symbol, desk.reverse)):
        mono.t += 1                                     # clear of the rate guard
        r = run(act({**body, "client_id": f"s{i}"}))["results"]["a1"]
        assert r["ok"] is False and r["refused"] and "not loaded yet" in r["error"]
    mono.t += 1
    r = run(desk.modify({"client_id": "m", "account": "a1", "order_id": "77", "price": 99.0}))
    assert "not loaded yet" in r["results"]["a1"]["error"]
    r = run(desk.cancel({"client_id": "x", "account": "a1", "order_id": "77"}))
    assert "not loaded yet" in r["results"]["a1"]["error"]
    a = ads["a1"]
    assert (a.orders, a.brackets, a.flattened, a.sym_cancelled, a.modified, a.cancelled) == \
        ([], [], [], [], [], [])


# --- ruling 1: settings pause with the 09:30 fire (P2), except a switch-off ----------------------
PAUSED = "settings can't change 09:29:50–09:30:30 or while the bot is placing — try again in a moment"


def _settings(desk, body):
    async def go():
        q = desk.subscribe()
        try:
            return desk.set_settings(body), [e for e, _ in [q.get_nowait() for _ in range(q.qsize())]]
        finally:
            desk.unsubscribe(q)
    return run(go())


@pytest.mark.parametrize("when", ["window", "placing"])
def test_settings_are_refused_in_the_fire_pause(tmp_path, when):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path, enabled=False)
    if when == "window":
        clock.dt = dt.datetime(2026, 9, 14, 13, 29, 50, tzinfo=UTC)      # Mon 09:29:50 ET
    else:
        eng._state("nq930", "a1").status = "placing"                     # 11:00 ET
    for body in ({"enabled": True}, {"max_order_qty": 4}, {"enabled": False, "max_order_qty": 4}):
        with pytest.raises(ValueError, match=re.escape(PAUSED)):
            _settings(desk, body)
    ct = desk.cfg.chart_trading
    assert (ct.enabled, ct.max_order_qty, ct.max_position_qty) == (False, 10, 20)
    assert saved == [] and not [e for e in journal(tmp_path) if e["event"] == "chart_trading_set"]


def test_a_switch_off_is_applied_inside_the_pause_like_kill(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path)
    clock.dt = dt.datetime(2026, 9, 14, 13, 30, 29, tzinfo=UTC)          # Mon 09:30:29 ET
    out, evs = _settings(desk, {"enabled": False, "max_order_qty": 10})  # limits unchanged
    assert out == {"enabled": False, "max_order_qty": 10, "max_position_qty": 20}
    assert desk.cfg.chart_trading.enabled is False and saved[-1].chart_trading.enabled is False
    assert evs == ["state"]
    assert [e for e in journal(tmp_path) if e["event"] == "chart_trading_set"][-1]["enabled"] is False
    assert order(desk)["a1"]["error"] == "chart trading is off — switch it on on the desk page"


def test_settings_change_normally_outside_the_pause(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path, enabled=False)
    clock.dt = dt.datetime(2026, 9, 14, 13, 30, 30, tzinfo=UTC)          # 09:30:30 ET: pause over
    assert _settings(desk, {"enabled": True, "max_order_qty": 4})[0]["max_order_qty"] == 4
    clock.dt = dt.datetime(2026, 9, 14, 13, 29, 49, tzinfo=UTC)          # 09:29:49 ET: not yet
    assert _settings(desk, {"max_position_qty": 30})[0]["max_position_qty"] == 30
    clock.dt = dt.datetime(2026, 9, 19, 13, 29, 55, tzinfo=UTC)          # Saturday 09:29:55 ET
    assert _settings(desk, {"max_order_qty": 5})[0]["max_order_qty"] == 5
    eng._state("nq930", "a1").status = "done"                          # a finished bot: no pause
    assert _settings(desk, {"max_order_qty": 6})[0]["max_order_qty"] == 6
    assert len(saved) == 4


def test_a_repeated_client_id_in_flight_waits_for_the_first_and_never_places_twice(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)

    async def go():
        gate, calls = asyncio.Event(), []

        async def slow(req):
            calls.append(req)
            await gate.wait()
            return OrderResult(ok=True, order_id="once")

        ads["a1"].place_order = slow
        body = {"client_id": "dup", "accounts": ["a1"], "root": "NQ", "side": "Buy",
                "qty": 1, "type": "Market"}
        first = asyncio.ensure_future(desk.order(dict(body)))
        await asyncio.sleep(0)
        second = asyncio.ensure_future(desk.order(dict(body)))   # the broker has not answered yet
        await asyncio.sleep(0)
        gate.set()
        return await first, await second, calls

    a, b, calls = run(go())
    assert len(calls) == 1 and a == b and a["results"]["a1"]["order_id"] == "once"


# === fix round 1 ====================================================================================
BUY10 = {"accounts": ["a1"], "root": "NQ", "side": "Buy", "qty": 10, "type": "Market"}


def _slow_orders(ad):
    """place_order that yields to the loop before the broker 'answers'."""
    async def slow(req):
        ad.orders.append(req)
        for _ in range(3):
            await asyncio.sleep(0)
        return OrderResult(ok=True, order_id=str(500 + len(ad.orders)))
    ad.place_order = slow


def test_two_concurrent_orders_cannot_both_pass_the_position_limit(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a1"].view["positions"] = [{"contract_id": 1, "symbol": NQC, "net": 10, "avg_price": 100.0}]
    _slow_orders(ads["a1"])

    async def go():
        return await asyncio.gather(desk.order({**BUY10, "client_id": "k1"}),
                                    desk.order({**BUY10, "client_id": "k2"}))

    rs = [r["results"]["a1"] for r in run(go())]
    assert sorted(r["ok"] for r in rs) == [False, True] and len(ads["a1"].orders) == 1
    bad = next(r for r in rs if not r["ok"])
    assert bad["error"] == f"that could take {NQC} on A1 to 30 contracts (limit 20)"


def test_two_concurrent_reverses_only_one_proceeds(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a1"].net = 2
    _slow_orders(ads["a1"])
    flat = ads["a1"].flatten_symbol

    async def slow_flat(symbol):
        await asyncio.sleep(0)
        return await flat(symbol)
    ads["a1"].flatten_symbol = slow_flat

    async def go():
        b = {"accounts": ["a1"], "root": "NQ"}
        return await asyncio.gather(desk.reverse({**b, "client_id": "r1"}),
                                    desk.reverse({**b, "client_id": "r2"}))

    rs = [r["results"]["a1"] for r in run(go())]
    assert [r["ok"] for r in rs] == [True, False]
    assert rs[1]["error"] == (f"an order sent from the chart in {NQC} on A1 is not confirmed "
                              "yet — try again in a moment")
    assert ads["a1"].flattened == [NQC] and len(ads["a1"].orders) == 1


def test_a_reservation_counts_only_while_the_cache_does_not_show_the_order(tmp_path):
    desk, eng, ads, clock, mono, _ = mkdesk(tmp_path)
    ads["a1"].view["positions"] = [{"contract_id": 1, "symbol": NQC, "net": 5, "avg_price": 100.0}]
    ads["a1"].place_order = lambda req: _ok("501")
    assert order(desk, cid="b1", qty=10)["a1"]["ok"] is True
    assert order(desk, cid="b2", qty=6)["a1"]["error"].endswith("to 21 contracts (limit 20)")
    ads["a1"].view["orders"] = [{**WORKING, "order_id": "501", "type": "Market", "qty": 10,
                                 "side": "Buy", "price": None}]
    # counted once (the cache), not twice (cache + reservation = 31)
    assert order(desk, cid="b3", qty=6)["a1"]["error"].endswith("to 21 contracts (limit 20)")
    # it filled: gone from the orders, but the position update has not come in
    # yet (still 5) — the reservation counts again instead of vanishing
    ads["a1"].view["orders"] = []
    assert order(desk, cid="b4", qty=6)["a1"]["error"].endswith("to 21 contracts (limit 20)")
    mono.t += 10.1                                      # kept the full 10 s, then gone
    assert order(desk, cid="b5", qty=6)["a1"]["ok"] is True


def test_flatten_also_cancels_chart_orders_the_cache_does_not_show_yet(tmp_path):
    """An order the broker accepted a moment ago, not in the cache yet, would
    survive the adapter's symbol flatten (it cancels what the cache shows)
    and could fill after it: the desk cancels those ids itself, first."""
    desk, eng, ads, clock, mono, _ = mkdesk(tmp_path)
    a = ads["a1"]
    calls: list = []
    ids = iter(["601", "603"])

    async def place(req):
        return OrderResult(ok=True, order_id=next(ids))
    a.place_order = place
    assert order(desk, cid="o1")["a1"]["ok"] is True                        # NQ 601, not cached
    assert order(desk, cid="o2", type="Limit", price=99.0, sl_price=95.0,
                 tp_price=110.0)["a1"]["ok"] is True                        # NQ bracket a1-101
    assert order(desk, cid="o3", root="ES")["a1"]["ok"] is True             # ES 603, not cached
    a.view["orders"] = [{**WORKING, "order_id": "a1-101"}]                  # the entry is cached
    a.fail_cancel_ids = {"601"}                                             # e.g. it just filled
    cancel, flat = a.cancel_order_by_id, a.flatten_symbol

    async def c(oid):
        calls.append(("cancel", oid))
        return await cancel(oid)

    async def f(sym):
        calls.append(("flatten", sym))
        return await flat(sym)
    a.cancel_order_by_id, a.flatten_symbol = c, f
    r = run(desk.flatten({"client_id": "fl", "accounts": ["a1"], "root": "NQ"}))["results"]["a1"]
    assert r["ok"] is True                                   # a failed cancel never stops the flatten
    assert calls == [("cancel", "601"), ("cancel", "a1-101-sl"), ("cancel", "a1-101-tp"),
                     ("flatten", NQC)]                       # cancels first; ES untouched
    ev = next(e for e in journal(tmp_path) if e["event"] == "manual_flatten")
    assert ev["reserved_cancels"] == {
        "601": {"ok": False, "error": "cancel rejected by test"},
        "a1-101-sl": {"ok": True, "error": None}, "a1-101-tp": {"ok": True, "error": None}}
    assert "strategy" not in ev
    calls.clear()
    mono.t += 10.1                                           # the reservations lapsed
    run(desk.flatten({"client_id": "fl2", "accounts": ["a1"], "root": "NQ"}))
    assert calls == [("flatten", NQC)]


def test_a_reservation_clears_after_ten_seconds(tmp_path):
    desk, eng, ads, clock, mono, _ = mkdesk(tmp_path)
    ads["a1"].view["positions"] = [{"contract_id": 1, "symbol": NQC, "net": 5, "avg_price": 100.0}]
    assert order(desk, cid="t1", qty=10)["a1"]["ok"] is True
    mono.t += 9.9
    assert order(desk, cid="t2", qty=6)["a1"]["error"].endswith("to 21 contracts (limit 20)")
    mono.t += 0.2
    assert order(desk, cid="t3", qty=6)["a1"]["ok"] is True


def test_kill_during_a_reverse_stops_it_before_the_open(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a1"].net = 2
    flat = ads["a1"].flatten_symbol

    async def flat_then_kill(symbol):
        r = await flat(symbol)
        desk.disable(cause="kill")                     # the desk's Kill lands mid-reverse
        return r
    ads["a1"].flatten_symbol = flat_then_kill
    r = run(desk.reverse({"client_id": "r", "accounts": ["a1"], "root": "NQ"}))["results"]["a1"]
    assert r["ok"] is False and r["refused"]
    assert r["error"] == "chart trading was switched off during the reverse — flattened only"
    assert ads["a1"].flattened == [NQC] and ads["a1"].orders == []


def test_a_reverse_that_runs_into_the_lock_window_does_not_open(tmp_path):
    desk, eng, ads, clock, *_ = mkdesk(tmp_path)
    clock.dt = dt.datetime(2026, 9, 14, 13, 19, 59, 800000, tzinfo=UTC)   # 09:19:59.8 ET
    ads["a1"].net = 2
    flat = ads["a1"].flatten_symbol

    async def slow_flat(symbol):
        clock.dt += dt.timedelta(milliseconds=500)     # the flatten takes the clock past 09:20
        return await flat(symbol)
    ads["a1"].flatten_symbol = slow_flat
    r = run(desk.reverse({"client_id": "r", "accounts": ["a1"], "root": "NQ"}))["results"]["a1"]
    assert r["error"] == f"{NQC} on A1 is locked 09:20-09:35 ET for the nq930 bot — flattened only"
    assert ads["a1"].flattened == [NQC] and ads["a1"].orders == []


def test_an_unknown_id_bot_stop_cannot_be_cancelled_while_the_bot_is_live(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a1"].place_order = lambda req: _ok("4242")
    assert order(desk, cid="p", type="Limit", price=90.0)["a1"]["ok"] is True   # a chart order
    st = eng._state("nq930", "a1")
    st.status = "live"                                  # its leg ids are NOT known to the desk
    stop = {**WORKING, "order_id": "88", "type": "Stop", "side": "Sell", "price": None,
            "stop_price": 95.0}
    ads["a1"].view["orders"] = [stop, {**WORKING, "order_id": "4242"}]

    def c(cid, oid):
        return run(desk.cancel({"client_id": cid, "account": "a1", "order_id": oid}))["results"]["a1"]

    assert c("x1", "88")["error"] == (
        f"order 88 on A1 was not placed from the chart and the nq930 bot is live in {NQC} "
        "— it may be one of the bot's; use the desk's Kill in an emergency")
    assert c("x2", "4242")["ok"] is True                # positively manual: still cancellable
    ads["a1"].view["orders"] = [{**stop, "symbol": None}]
    assert "was not placed from the chart" in c("x3", "88")["error"]   # unresolved contract too
    assert ads["a1"].cancelled == ["4242"]


def test_a_journal_failure_after_the_broker_accepted_still_reports_the_order(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    real = eng.journal

    def broken(event, **data):
        if event == "manual_order":
            raise OSError("disk full")
        real(event, **data)
    eng.journal = broken
    r = order(desk)["a1"]
    assert r["ok"] is True and r["order_id"] == "plain" and r["journal_error"] == "OSError: disk full"


def test_an_unexpected_error_is_journaled_as_manual_error(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)

    def boom():
        raise RuntimeError("cache exploded")
    ads["a1"].trade_view = boom
    r = order(desk)["a1"]
    assert r["ok"] is False and r["error"] == "internal error: RuntimeError: cache exploded"
    ev = [e for e in journal(tmp_path) if e["event"] == "manual_error"]
    assert len(ev) == 1 and ev[0]["source"] == "chart" and "strategy" not in ev[0]
    assert ads["a1"].orders == []


def test_a_quote_from_the_future_is_not_fresh(tmp_path):
    desk, eng, ads, clock, mono, _ = mkdesk(tmp_path)
    assert "no trade" in order(desk, cid="q1", type="Stop", price=101.0,
                               quotes=quote(clock, last=100.0, age_s=-5.1))["a1"]["error"]
    assert order(desk, cid="q2", type="Stop", price=101.0,
                 quotes=quote(clock, last=100.0, age_s=-4.9))["a1"]["ok"] is True


def test_an_account_pinned_twice_in_config_is_refused_on_both(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    desk.cfg.accounts["a2"].account_name = "a1"         # same login ("k"), same account, any case
    r = order(desk, accounts=["a1", "a2"])
    assert r["a1"]["error"] == "A1: account pinned twice in config — chart trading refuses it"
    assert r["a2"]["error"].endswith("account pinned twice in config — chart trading refuses it")
    assert ads["a1"].orders == [] and ads["a2"].orders == []
    assert [a["tradable"] for a in desk.snapshot()["accounts"]] == [False, False]


def test_an_order_with_an_unknown_side_counts_as_worst_case(tmp_path):
    desk, eng, ads, clock, mono, _ = mkdesk(tmp_path)
    ads["a1"].view["orders"] = [{**WORKING, "side": None, "qty": 15}]
    assert order(desk, cid="u1", qty=6)["a1"]["error"].endswith("to 21 contracts (limit 20)")
    assert order(desk, cid="u2", qty=6, side="Sell")["a1"]["error"].endswith("to 21 contracts (limit 20)")
    assert order(desk, cid="u3", qty=5)["a1"]["ok"] is True


def test_reverse_refuses_an_unreadable_position(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a1"].net_error = True
    r = run(desk.reverse({"client_id": "r", "accounts": ["a1"], "root": "NQ"}))["results"]["a1"]
    assert r["error"] == f"the {NQC} position on A1 is unreadable (position read failed) — nothing done"
    assert ads["a1"].flattened == [] and ads["a1"].orders == []


def test_modify_refuses_a_market_order_and_an_unresolved_contract(tmp_path):
    desk, eng, ads, clock, mono, _ = mkdesk(tmp_path)
    ads["a1"].view["orders"] = [{**WORKING, "order_id": "70", "type": "Market", "price": None},
                                {**WORKING, "order_id": "71", "symbol": None}]

    def m(cid, oid):
        body = {"client_id": cid, "account": "a1", "order_id": oid, "price": 99.0}
        return run(desk.modify(body))["results"]["a1"]

    assert m("m1", "70")["error"] == "only Limit and Stop orders can be moved (this one is Market)"
    assert m("m2", "71")["error"] == "that order's contract is not resolved yet — try again in a moment"
    assert ads["a1"].modified == []
