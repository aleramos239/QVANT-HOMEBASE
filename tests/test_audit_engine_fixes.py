"""Audit 2026-10-27, group engine: the fixes, one small test each. Fake adapters only."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from homebase.broker.base import FillEvent, OrderResult
from homebase.desk.engine import Engine
from tests.test_desk_api import desk_client  # noqa: F401 -- the fixture
from tests.test_engine import ALERT, Clock, mkcfg, mkengine, run, st_of
from tests.test_engine_groups import mk as mkgroups


def test_a_corrupt_day_file_never_stops_the_desk_and_is_kept(tmp_path):
    eng, _, clock = mkengine(tmp_path)
    p = eng._day_path(eng._today())
    p.write_text("{not json")
    eng2 = Engine(mkcfg(), {}, now_fn=clock, root=tmp_path)
    assert eng2.states == {} and not p.exists() and p.with_name(p.name + ".corrupt").exists()


def test_journal_never_raises(tmp_path):
    eng, _, _ = mkengine(tmp_path)
    eng._root = tmp_path / "missing" / "dir"            # the append fails: OSError
    eng.journal("x", a=object())                          # no raise


def test_straddle_survivor_cancel_is_retried_and_a_resting_leg_stays_tracked(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    ad.fail_leg = "Sell"
    ad.fail_cancel_ids = {"main-101"}                   # refuses once: the retry gets it
    out = run(eng.handle_alert(dict(ALERT)))
    st = st_of(eng)
    assert not out["ok"] and st.status == "error" and "main-101" in ad.cancelled and "check it" not in st.note
    # a cancel that never works: the leg rests, so the run is "placed" -- its fill is booked, 12:55 cancels it
    (tmp_path / "b").mkdir()
    eng2, ad2, _ = mkengine(tmp_path / "b")
    ad2.fail_leg = "Sell"

    async def never(order_id):
        return OrderResult(ok=False, error="refused")

    ad2.cancel_order_by_id = never
    ad2.order_status["main-101"] = "Working"
    out = run(eng2.handle_alert(dict(ALERT)))
    st = st_of(eng2)
    assert not out["ok"] and st.status == "placed" and st.upper_id == "main-101" and "check it" in st.note
    run(eng2.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Buy", qty=3, price=24510.0,
                               raw={"orderId": "main-101"})))
    assert st.status == "live" and st.entry_side == "Buy"


def test_12_55_entry_cancel_refused_keeps_the_state_placed(tmp_path):
    eng, ad, clock = mkengine(tmp_path)
    run(eng.handle_alert(dict(ALERT)))
    st = st_of(eng)
    ad.fail_cancel_ids = {st.upper_id}
    ad.order_status[st.upper_id] = "Working"
    clock.set_et(12, 56)
    run(eng.clock_tick())
    assert st_of(eng).status == "placed"


def test_arm_and_strategy_need_a_real_bool(desk_client):
    c = desk_client
    assert c.post("/api/arm", json={"armed": "false"}, headers=c.H).status_code == 400
    assert c.post("/api/strategy", json={"strategy": "nq930", "enabled": "false"}, headers=c.H).status_code == 400


def _kill_with(c, flatten_ok, cancel_ok):
    ad = c.adapters["a1"]
    calls = []

    async def fl():
        calls.append("flatten")
        return OrderResult(ok=flatten_ok, error=None if flatten_ok else "no")

    async def ca():
        calls.append("cancel_all")
        return OrderResult(ok=cancel_ok, error=None if cancel_ok else "no")

    ad.flatten_all, ad.cancel_all = fl, ca
    eng, seen = c.app.state.engine, []
    real = eng.flatten_today

    async def spy(**kw):
        seen.append(kw)
        return await real(**kw)

    eng.flatten_today = spy
    return calls, seen


def test_kill_does_not_cancel_stops_when_the_flatten_failed(desk_client):
    c = desk_client
    calls, seen = _kill_with(c, False, True)
    r = c.post("/api/kill", json={}, headers=c.H).json()
    assert calls == ["flatten"] and r["ok"] is False and r["failed"] == ["a1"]
    assert seen == [{"close": False, "accounts": set()}]       # no account flattened: no strategy's orders touched


def test_kill_still_cancels_the_strategies_orders_when_only_cancel_all_failed(desk_client):
    c = desk_client
    calls, seen = _kill_with(c, True, False)
    r = c.post("/api/kill", json={}, headers=c.H).json()
    assert calls == ["flatten", "cancel_all"] and r["ok"] is False and r["failed"] == ["a1"]
    assert seen == [{"close": False, "accounts": {"a1"}}]      # the per-order cancels are the fallback for it


def test_account_flatten_cleans_up_only_after_the_flatten_went_through(desk_client):
    c = desk_client
    calls, seen = _kill_with(c, False, True)
    r = c.post("/api/account-flatten", json={"account": "a1"}, headers=c.H).json()
    assert r["ok"] is False and seen == [] and calls == ["flatten"]       # a failed flatten: strategies untouched
    calls, seen = _kill_with(c, True, False)
    r = c.post("/api/account-flatten", json={"account": "a1"}, headers=c.H).json()
    assert r["ok"] is False and len(seen) == 1                            # cancel_all failed: the fallback still runs


def test_one_bad_group_does_not_turn_the_others_off(tmp_path):
    eng, _, _ = mkgroups(tmp_path)
    (tmp_path / "groups.json").write_text(json.dumps({
        "good": {"name": "g", "members": ["a"], "accounts": ["a1"], "on": True},
        "bad": {"name": "b", "risk_usd": "x", "on": True}}))
    eng.groups = {}
    eng._load_groups()
    assert eng.groups["good"]["on"] is True and "bad" not in eng.groups


# --- repair pass: the unreadable-state block, the timeouts, the exits, the day lock --------------------------
from homebase.desk.daystate import DayState  # noqa: E402
from homebase.desk.engine_kill import EXIT_TIMEOUT_S  # noqa: E402


def _live(eng, name="nq930", **kw):
    """A done/live run injected straight into today's states."""
    st = DayState(strategy=name, account="main", date=eng._today(), qty=2, upper_id=f"{name}-u",
                  lower_id=f"{name}-l", up_sl_id=f"{name}-usl", up_tp_id=f"{name}-utp",
                  **{"status": "live", "entry_side": "Buy", "entry_fill": 24510.0, "entry_qty": 2, **kw})
    eng.states[f"{name}@main"] = st
    return st


def test_each_account_timeout_is_opt_in_and_reports_the_account(tmp_path):
    eng, _, _ = mkengine(tmp_path)

    async def slow(a):
        await asyncio.sleep(0.2)
        return "late"

    got, _ = run(eng.each_account({"main": 1}, slow))                      # the clock / Lab paths: never cut off
    assert got == {"main": "late"}
    got, _ = run(eng.each_account({"main": 1}, slow, 0.01))                # the Kill's sweep: cut off and reported
    assert isinstance(got["main"], asyncio.TimeoutError) and EXIT_TIMEOUT_S > 15


def test_flatten_today_reports_every_run_of_an_account_whose_turn_raised(tmp_path):
    eng, _, _ = mkengine(tmp_path)
    run(eng.handle_alert(dict(ALERT)))

    async def broke(accounts, fn, timeout=None):
        return {a: TimeoutError("hung") for a in accounts}, {}

    eng.each_account = broke
    out = run(eng.flatten_today(close=False))
    assert list(out) == ["nq930@main"] and "internal error" in out["nq930@main"][0]


def test_an_unreadable_day_file_blocks_new_placements_today_and_across_a_restart(tmp_path):
    eng, ad, clock = mkengine(tmp_path)
    p = eng._day_path(eng._today())
    p.write_text("{not json")
    eng2 = Engine(mkcfg(), {"main": ad}, now_fn=clock, root=tmp_path)
    out = run(eng2.handle_alert(dict(ALERT)))
    assert out["ok"] is False and ad.brackets == [] and eng2.killed_today("nq930")
    eng3 = Engine(mkcfg(), {"main": ad}, now_fn=clock, root=tmp_path)     # day file gone, the journal remembers
    assert eng3.killed_today("nq930") and run(eng3.handle_alert(dict(ALERT)))["ok"] is False


def test_one_unreadable_day_record_blocks_new_placements_too(tmp_path):
    eng, ad, clock = mkengine(tmp_path)
    p = eng._day_path(eng._today())
    p.write_text(json.dumps({"nq930@main": {"account": "main", "bogus_field": 1}}))
    eng2 = Engine(mkcfg(), {"main": ad}, now_fn=clock, root=tmp_path)
    assert eng2.killed_today("nq930") and run(eng2.handle_alert(dict(ALERT)))["ok"] is False


def test_an_unreadable_day_book_is_kept_and_blocks_placements(tmp_path):
    eng, ad, clock = mkengine(tmp_path)
    eng.book("main").locked = "day_lock"
    eng._save_books()
    p = eng._books_path()
    p.write_text("{torn")
    eng2 = Engine(mkcfg(), {"main": ad}, now_fn=clock, root=tmp_path)
    assert p.with_name(p.name + ".corrupt").exists() and eng2.killed_today("nq930")
    assert run(eng2.handle_alert(dict(ALERT)))["ok"] is False             # a locked account cannot trade on a fresh book


def test_day_books_save_is_atomic(tmp_path, monkeypatch):
    eng, _, _ = mkengine(tmp_path)
    eng.book("main").closed_net = 10.0
    eng._save_books()
    p = eng._books_path()
    before = p.read_text()
    monkeypatch.setattr(Path, "write_text", lambda self, text, *a, **kw: (_ for _ in ()).throw(OSError("full")))
    with pytest.raises(OSError):
        eng.book("main").closed_net = 99.0
        eng._save_books()
    assert p.read_text() == before


def test_a_flatten_fill_is_split_across_the_done_runs_of_the_account(tmp_path):
    cfg = mkcfg(book={"nq930": [{"account": "main", "qty": 2}], "nq2": [{"account": "main", "qty": 2}]})
    cfg.strategies["nq2"] = StrategyCfg(symbol="NQ", qty=2, offset_pts=10.0, sl_pts=5.0, tp_pts=15.0, enabled=True)
    eng, ad, _ = mkengine(tmp_path, cfg=cfg)
    a = _live(eng, "nq930", status="done", exit_reason="killed")
    b = _live(eng, "nq2", status="done", exit_reason="killed")
    # one market-out sold the account's whole net of 5 (4 held by these runs, 1 not anyone's)
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Sell", qty=5, price=24520.0, raw={})))
    assert (a.exit_qty, b.exit_qty) == (2, 2) and a.pnl is not None and b.pnl is not None
    rem = _events(tmp_path, "exit_fill_remainder")
    assert len(rem) == 1 and rem[0]["qty"] == 1


def test_a_fill_of_another_runs_order_is_not_booked_as_this_runs_exit(tmp_path):
    cfg = mkcfg(book={"nq930": [{"account": "main", "qty": 2}], "nq2": [{"account": "main", "qty": 2}]})
    cfg.strategies["nq2"] = StrategyCfg(symbol="NQ", qty=2, offset_pts=10.0, sl_pts=5.0, tp_pts=15.0, enabled=True)
    eng, ad, _ = mkengine(tmp_path, cfg=cfg)
    done = _live(eng, "nq930", status="done", exit_reason="killed")
    _live(eng, "nq2", status="placed", entry_side=None, entry_fill=None, entry_qty=0)
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Sell", qty=2, price=24520.0,
                              raw={"orderId": "nq2-utp"})))                 # nq2's own target
    assert done.exit_qty == 0 and done.pnl is None
    # and a done run never takes more than it entered
    done.exit_qty = 2
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Sell", qty=2, price=24520.0, raw={})))
    assert done.exit_qty == 2 and done.pnl is None


def test_a_day_take_print_booking_is_trued_up_to_the_real_fill(tmp_path):
    from homebase.desk.engine import TAKE_PRINT_NOTE
    eng, ad, _ = mkengine(tmp_path)
    st = _live(eng, status="done", exit_reason="day_take", note=TAKE_PRINT_NOTE, exit_fill=24520.0)
    st.pnl = eng._gross_pnl(st, eng.cfg.strategies["nq930"])
    before = eng.book("main").closed_net
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Sell", qty=2, price=24530.0, raw={})))
    assert st.exit_fill == 24530.0 and st.note == "" and eng.book("main").closed_net > before
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Sell", qty=2, price=24540.0, raw={})))
    assert st.exit_fill == 24530.0                                           # booked once


def test_reconnect_books_the_exit_the_target_filled_while_away(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    st = _live(eng)
    st.tp_pts = None
    ad.net = 0
    ad.order_status["nq930-utp"] = "Filled"
    assert run(eng.reconcile_account("main")) == {"nq930": "exit_recovered"}
    assert st.status == "done" and st.exit_fill == 24525.0 and st.pnl and st.pnl > 0
    assert _events(tmp_path, "exit_recovered_on_reconnect")[0]["booked"] is True


def test_reconnect_with_an_exit_it_cannot_tell_books_nothing_and_says_check_it(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    st = _live(eng)
    ad.net = 0                                                # neither bracket reads Filled
    run(eng.reconcile_account("main"))
    assert st.status == "done" and st.pnl is None and "check it" in st.note


def _placed_run(eng):
    st = _live(eng, status="placed", entry_side=None, entry_fill=None, entry_qty=0)
    return st


def test_day_lock_waits_while_an_entry_reads_still_working(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    eng._kill_sleep = lambda s: asyncio.sleep(0)
    st = _placed_run(eng)
    ad.order_status.update({"nq930-u": "Working", "nq930-l": "Canceled"})
    run(eng._lock_account("main", "day_lock"))
    assert st.status == "placed" and "check it" in st.note and "nq930-usl" not in ad.cancelled


def test_day_lock_settles_a_pending_cancel_and_then_cancels_the_brackets(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    eng._kill_sleep = lambda s: asyncio.sleep(0)
    st = _placed_run(eng)
    reads = iter(["PendingCancel", "Canceled"])
    orig = ad.get_order_status

    async def status(oid):
        return next(reads) if oid == "nq930-u" else "Canceled"

    ad.get_order_status = status
    run(eng._lock_account("main", "day_lock"))
    assert st.status == "done" and "nq930-usl" in ad.cancelled


def test_a_refused_cancel_with_no_status_is_not_gone_in_either_path(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    assert run(eng._order_gone(ad, "x", accepted=False)) is False
    assert run(eng._order_gone(ad, "x", accepted=True)) is True


def test_a_kill_flatten_does_not_report_check_it_for_a_cancel_that_is_pending(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    eng._kill_sleep = lambda s: asyncio.sleep(0)
    st = _live(eng)
    ad.fail_cancel_ids = {"nq930-u"}
    reads = iter(["PendingCancel", "Canceled"])

    async def status(oid):
        return next(reads, "Canceled") if oid == "nq930-u" else "Canceled"

    ad.get_order_status = status
    flat, acts = run(eng._flatten_state(st, eng.cfg.strategies["nq930"], ad, close=False))
    assert flat is True and not any("check it" in a for a in acts)


def test_the_12_55_refusal_is_journaled_once_a_minute_not_every_tick(tmp_path):
    eng, ad, clock = mkengine(tmp_path)
    run(eng.handle_alert(dict(ALERT)))
    st = st_of(eng)

    async def refuse(oid):
        return OrderResult(ok=False, error="no")

    ad.cancel_order_by_id = refuse
    ad.order_status[st.upper_id] = "Working"
    clock.set_et(12, 56)
    for _ in range(3):
        run(eng.clock_tick())
    assert len(_events(tmp_path, "cancel_entries_failed")) == 1 and st_of(eng).status == "placed"


def test_set_group_that_cannot_save_leaves_no_switch_on_in_memory(tmp_path):
    eng, ads, _ = mkgroups(tmp_path)
    from tests.test_engine_groups import group
    group(eng, on=False)
    before = dict(eng.groups["g"])

    def boom():
        raise OSError("disk full")

    eng._save_groups = boom
    with pytest.raises(OSError):
        group(eng, on=True)
    assert eng.groups["g"] == before
    del eng.groups["g"]
    with pytest.raises(OSError):
        group(eng, on=False)
    assert "g" not in eng.groups


def test_a_position_with_no_contract_name_counts_as_a_hedge_risk(tmp_path):
    from homebase.desk.engine_lab import GROUP_HEDGE
    from tests import test_engine_lab as tlab
    from tests.test_engine_groups import enter, group
    eng, ads, _ = mkgroups(tmp_path)
    group(eng)
    ads["a3"].trade_view = lambda: {"positions": [{"net": -2}], "orders": []}
    assert enter(eng, tlab.LAB, tlab.leg(side="Buy"))["reason"] == GROUP_HEDGE


def test_a_clean_refusal_does_not_use_up_the_daily_limit(tmp_path):
    from tests import test_engine_lab as tlab
    eng, ads, _ = tlab.mk(tmp_path)
    ads["a1"].reject = "OSO rejected (no orderId returned)"
    out = tlab.go(eng, tlab.leg(), max_rounds=1)
    assert out["accounts"]["a1"]["ok"] is False
    ads["a1"].reject = None
    assert tlab.go(eng, tlab.leg(iid=2), {"a1": 1}, max_rounds=1)["accounts"]["a1"]["ok"] is True


def _events(tmp_path, name):
    return [json.loads(l) for l in (tmp_path / "journal.jsonl").read_text().splitlines()
            if json.loads(l)["event"] == name]


from homebase.config import StrategyCfg  # noqa: E402
