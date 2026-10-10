"""The final fix wave of Step B, wave A (the Desk side): I1 (the window must end by the flat time), I2 (a fill the Desk
adopted from an order read reads filled), I3 (the state line says "check" while a trade needs a look), G1 (the runner
not connected), M-D1 (a finished trade whose old order still works), M-D2 (the day file follows a failed Lab write).
Real engine over the engine tests' fake adapters; no broker, no network; the store and the engine's root are temp
folders."""
from __future__ import annotations

import pytest

from homebase import labcfg
from homebase.broker.base import FillEvent
from homebase.labdesk import Refused
from homebase.labrun import store
from tests.labdesk_util import DATE, LAB, LIMITS, entry, mkdesk, rec, send
from tests.test_engine import run
from tests.test_engine_lab import fill_entry, tick

WINDOW_PAST_FLAT = "Its window ends after the flat time. Shorten the window to end by 15:55."


# ---------------------------------------------------------------- I1: the window must end by the flat time
def test_the_sentence_is_labcfgs_own():
    assert labcfg.SAY_WINDOW == WINDOW_PAST_FLAT


def test_a_window_to_1600_takes_no_limits_with_the_sentence(tmp_path):
    d = mkdesk(tmp_path, limits=None, window=("09:25", "16:00"))
    with pytest.raises(ValueError) as e:
        run(d.ld.set_limits(LAB, LIMITS))
    assert str(e.value) == WINDOW_PAST_FLAT
    assert labcfg.limits_of(d.cfg, LAB) is None and store.get_desk("pp") is None


def test_a_window_to_1600_takes_no_account_with_the_sentence(tmp_path):
    d = mkdesk(tmp_path, limits=None, window=("09:25", "16:00"))
    with pytest.raises(Refused) as e:
        run(d.ld.set_book(LAB, [{"account": "a1", "qty": 1}]))
    assert str(e.value) == WINDOW_PAST_FLAT and e.value.status == 409
    assert not d.cfg.book.get(LAB)
    d.ld.check_book(LAB, [])                     # taking accounts off is never refused for it


def test_a_window_to_1555_books(tmp_path):
    d = mkdesk(tmp_path, window=("09:25", "15:55"))
    assert d.cfg.book[LAB] == [{"account": "a1", "qty": 1}]
    assert labcfg.limits_of(d.cfg, LAB).flat_et == "15:55"


def test_a_window_that_ends_before_the_flat_time_books(tmp_path):
    d = mkdesk(tmp_path, window=("09:25", "12:00"))
    assert d.cfg.book[LAB] == [{"account": "a1", "qty": 1}]


def test_flat_1530_with_a_window_to_1555_is_refused(tmp_path):
    d = mkdesk(tmp_path, limits=None, window=("09:25", "15:55"))
    with pytest.raises(ValueError) as e:
        run(d.ld.set_limits(LAB, {**LIMITS, "flat_et": "15:30"}))
    assert str(e.value) == WINDOW_PAST_FLAT
    run(d.ld.set_limits(LAB, {**LIMITS, "flat_et": "15:55"}))      # at the window's end: fine


def test_a_book_is_refused_when_its_limits_flat_time_is_before_the_window_end(tmp_path):
    """Limits kept from a window that ended earlier (the record changed under them): no account."""
    d = mkdesk(tmp_path, qty=0, window=("09:25", "15:00"), limits={**LIMITS, "flat_et": "15:00"})
    store.put(rec(session_window=["09:25", "15:55"]))
    run(d.ld.refresh())
    assert labcfg.record_of(d.cfg, LAB)["session_window"] == ["09:25", "15:55"]
    assert labcfg.limits_of(d.cfg, LAB).flat_et == "15:00"
    with pytest.raises(Refused) as e:
        d.ld.check_book(LAB, [{"account": "a1", "qty": 1}])
    assert str(e.value) == WINDOW_PAST_FLAT


@pytest.mark.parametrize("end, flat, past", [("16:00", None, True), ("15:55", None, False), ("15:00", None, False),
                                              ("15:55", "15:30", True), ("15:55", "15:55", False),
                                              ("15:00", "15:30", False)])
def test_ends_after_flat(end, flat, past):
    lim = labcfg.LabLimits(3, 2, 300.0, "11:00", flat) if flat else None
    assert labcfg.ends_after_flat({"session_window": ["09:25", end]}, lim) is past


# ---------------------------------------------------------------- I2: a fill the Desk adopted from an order read
def _adopted(tmp_path):
    """A buy stop that filled with its push lost: the clock's order read (_guard_placed) makes the trade live."""
    d = mkdesk(tmp_path)
    assert send(d, entry(1))["ok"] is True
    s = d.eng.states[f"{LAB}@a1"]
    ad = d.ads["a1"]
    ad.order_status[s.upper_id], ad.filled[s.upper_id], ad.net = "Filled", 1, 1
    ad.order_status[f"{s.upper_id}-sl"] = ad.order_status[f"{s.upper_id}-tp"] = "Working"
    tick(d.eng)
    assert (s.status, s.entry_side, s.entry_qty) == ("live", "Buy", 0)        # adopted whole, no fill push counted
    return d, s, ad


def test_an_adopted_entry_reads_filled_to_the_strategy(tmp_path):
    d, s, ad = _adopted(tmp_path)
    sent = list(ad.orders)
    (row,) = d.eng.lab_rounds(LAB)
    assert row["entry_qty"] == 1 and row["status"] == "live"
    assert d.ld._brain(LAB)["orders"]["1"]["status"] == "filled"
    assert d.ld._brain(LAB)["flat"] is False
    assert ad.orders == sent                                       # reading it sends nothing


def test_an_adopted_entry_then_its_target_reads_the_right_exit_and_pnl(tmp_path):
    d, s, ad = _adopted(tmp_path)
    eid = s.upper_id
    ad.order_status[f"{eid}-tp"], ad.order_status[f"{eid}-sl"], ad.net = "Filled", "Canceled", 0
    run(d.eng.on_fill(FillEvent(account_id="a1", symbol="NQZ6", side="Sell", qty=1, price=120.0,
                                raw={"orderId": f"{eid}-tp"})))
    tick(d.eng)
    assert (s.status, s.exit_reason, s.exit_fill) == ("done", "tp", 120.0)
    (row,) = d.eng.lab_rounds(LAB)
    assert (row["entry_qty"], row["exit_qty"], row["exit_reason"], row["pnl"]) == (1, 1, "tp", s.pnl)
    b = d.ld._brain(LAB)
    assert b["orders"]["1"]["status"] == "filled" and b["flat"] is True


def test_a_round_with_no_entry_side_still_reads_its_own_count(tmp_path):
    d = mkdesk(tmp_path)
    send(d, entry(1))
    (row,) = d.eng.lab_rounds(LAB)
    assert (row["entry_side"], row["entry_qty"]) == (None, 0)
    assert d.ld._brain(LAB)["orders"]["1"]["status"] == "working"


# ---------------------------------------------------------------- I3: the state line says "check" while a trade needs a look
CANNOT_CHECK = "The Desk cannot check the last trade's orders."


def _live(tmp_path, **kw):
    d = mkdesk(tmp_path, **kw)
    assert send(d, entry(1))["ok"] is True
    s = d.eng.states[f"{LAB}@a1"]
    fill_entry(d.eng, d.ads["a1"], s, 110.0)
    assert s.status == "live"
    return d, s


def _view(d):
    v = d.ld.status_view(LAB)
    return v["state"], v["why"]


def test_a_live_trade_with_nothing_to_look_at_reads_in_position(tmp_path):
    d, s = _live(tmp_path)
    assert _view(d) == ("in_position", None)


def test_a_done_trade_whose_stop_still_works_reads_check(tmp_path):
    d, s = _live(tmp_path)
    ad, eid = d.ads["a1"], s.upper_id
    ad.order_status[f"{eid}-tp"], ad.net = "Filled", 0                 # the target filled; its stop stays Working
    ad.stuck.add(f"{eid}-sl")                                          # (a cancel is taken and the stop keeps working)
    run(d.eng.on_fill(FillEvent(account_id="a1", symbol="NQZ6", side="Sell", qty=1, price=120.0,
                                raw={"orderId": f"{eid}-tp"})))
    tick(d.eng)
    assert s.status == "done" and ad.order_status[f"{eid}-sl"] == "Working"
    assert _view(d) == ("check", CANNOT_CHECK)


def test_a_live_trade_whose_record_was_lost_reads_check(tmp_path):
    d, s = _live(tmp_path)
    x = d.eng._lab_x(s)
    x["check"], x["why"], x["lost"] = True, CANNOT_CHECK, True        # what the engine's load writes for a lost record
    assert s.status == "live"
    assert _view(d) == ("check", CANNOT_CHECK)


def test_a_carried_block_reads_check(tmp_path):
    d = mkdesk(tmp_path)
    d.eng.lab_open(LAB)
    assert d.eng._lab_carry_make((LAB, "a1"), {"date": "2026-09-11", "status": "live", "orders": []}, DATE)
    state, why = _view(d)
    assert state == "check" and why == CANNOT_CHECK


def test_a_refused_close_reads_check(tmp_path):
    d, s = _live(tmp_path)
    d.ads["a1"].fail_market = True
    run(d.eng.lab_flatten(LAB))
    assert s.status == "live"
    assert _view(d) == ("check", "Check it: the close order was not confirmed. Its stop is still working.")


def test_a_trade_whose_stop_order_the_desk_does_not_know_reads_check(tmp_path):
    d, s = _live(tmp_path)
    d.eng._lab_x(s)["blind"] = True
    assert _view(d) == ("check", "Check it: the Desk does not know this trade's stop order.")


def test_a_failed_entry_reads_check_with_its_rows_sentence(tmp_path):
    d = mkdesk(tmp_path)
    d.ads["a1"].reject = "Insufficient margin"
    send(d, entry(1))
    (row,) = d.ld.status_view(LAB)["rounds"]
    assert row["why"] and _view(d) == ("check", row["why"])


# ---------------------------------------------------------------- G1: the runner up but not connected to the Desk
NOT_CONNECTED = "The runner is not connected to the Desk."


def _runner_file(d):
    store.put_runner({"pid": 1, "seen_utc": d.ld._utc().isoformat()})
    run(d.ld.refresh())


def test_a_booked_strategy_whose_runner_never_beat_reads_runner_down_even_with_a_fresh_runner_file(tmp_path):
    d = mkdesk(tmp_path)
    _runner_file(d)
    v = d.ld.status_view(LAB)
    assert v["runner"]["alive"] is True                                # alive by its file alone
    assert (v["state"], v["why"]) == ("runner_down", NOT_CONNECTED)


def test_a_beat_that_names_another_strategy_does_not_connect_this_one(tmp_path):
    d = mkdesk(tmp_path)
    d.ld.heartbeat({"pid": 7, "strategies": {}})
    assert _view(d) == ("runner_down", NOT_CONNECTED)


def test_once_the_runner_names_it_the_state_is_the_usual_one(tmp_path):
    d = mkdesk(tmp_path)
    d.ld.heartbeat({"pid": 7, "strategies": {LAB: {"state": "waiting", "why": None, "mode": "desk"}}})
    assert _view(d) == ("waiting", None)
    d.ld.heartbeat({"pid": 7, "strategies": {LAB: {"state": "running", "why": None, "mode": "desk"}}})
    assert _view(d) == ("watching", None)


def test_a_disarmed_desk_says_disarmed_first(tmp_path):
    """Disarmed, nothing goes out whatever the runner does: the desk-wide fact is the one to read."""
    d = mkdesk(tmp_path, armed=False)
    assert _view(d) == ("disarmed", None)


def test_with_no_account_or_switched_off_the_runner_sentence_is_not_said(tmp_path):
    shadow = mkdesk(tmp_path / "s", qty=0, own_store=True)
    assert _view(shadow) == ("shadow", None)
    off = mkdesk(tmp_path / "o", enabled=False, own_store=True)
    assert _view(off) == ("off", None)


def test_a_trade_that_needs_a_look_still_reads_check_with_the_runner_not_connected(tmp_path):
    d, s = _live(tmp_path)
    d.eng._lab_x(s)["blind"] = True
    assert _view(d)[0] == "check"


# ---------------------------------------------------------------- M-D1: a finished trade whose old order still works
FLATTEN_FIRST = "Flatten it first."
OLD_ORDER = "An old order of this trade is still working. Cancel it first."


def _done_not_clean(tmp_path):
    d, s = _live(tmp_path)
    ad, eid = d.ads["a1"], s.upper_id
    ad.order_status[f"{eid}-tp"], ad.net = "Filled", 0
    ad.stuck.add(f"{eid}-sl")
    run(d.eng.on_fill(FillEvent(account_id="a1", symbol="NQZ6", side="Sell", qty=1, price=120.0,
                                raw={"orderId": f"{eid}-tp"})))
    tick(d.eng)
    assert s.status == "done" and d.ld._open(LAB) == ["a1"]
    return d


def _refused(coro_or_fn):
    with pytest.raises(Refused) as e:
        coro_or_fn()
    return str(e.value)


def test_the_sentence_is_the_engines_own():
    from homebase import engine, labdesk
    assert labdesk.OLD_ORDER_WORKING == engine.LAB_OLD_ORDER_WORKING == OLD_ORDER


def test_a_done_trade_whose_stop_still_works_asks_to_cancel_the_old_order_not_to_flatten(tmp_path):
    d = _done_not_clean(tmp_path)
    assert _refused(lambda: run(d.ld.set_limits(LAB, LIMITS))) == OLD_ORDER
    assert _refused(lambda: d.ld.check_book(LAB, [])) == OLD_ORDER
    assert _refused(lambda: run(d.ld.set_book(LAB, []))) == OLD_ORDER
    assert _refused(lambda: run(d.ld.remove(LAB))) == OLD_ORDER
    d.ld.check_book(LAB, [{"account": "a1", "qty": 1}])          # keeping the account is not refused


def test_a_really_open_trade_still_asks_to_flatten_first(tmp_path):
    d, s = _live(tmp_path)
    assert _refused(lambda: run(d.ld.set_limits(LAB, LIMITS))) == FLATTEN_FIRST
    assert _refused(lambda: d.ld.check_book(LAB, [])) == FLATTEN_FIRST
    assert _refused(lambda: run(d.ld.remove(LAB))) == FLATTEN_FIRST


def test_an_open_trade_on_one_account_and_an_old_order_on_another_asks_to_flatten(tmp_path):
    d = mkdesk(tmp_path, accounts=("a1", "a2"))
    send(d, entry(1))
    for a in ("a1", "a2"):
        fill_entry(d.eng, d.ads[a], d.eng.states[f"{LAB}@{a}"], 110.0)
    s1 = d.eng.states[f"{LAB}@a1"]
    ad, eid = d.ads["a1"], s1.upper_id
    ad.order_status[f"{eid}-tp"], ad.net = "Filled", 0
    ad.stuck.add(f"{eid}-sl")
    run(d.eng.on_fill(FillEvent(account_id="a1", symbol="NQZ6", side="Sell", qty=1, price=120.0,
                                raw={"orderId": f"{eid}-tp"})))
    tick(d.eng)
    assert s1.status == "done" and d.eng.states[f"{LAB}@a2"].status == "live"
    assert _refused(lambda: run(d.ld.set_limits(LAB, LIMITS))) == FLATTEN_FIRST
    assert _refused(lambda: d.ld.check_book(LAB, [{"account": "a2", "qty": 1}])) == OLD_ORDER    # only a1 leaves
    assert _refused(lambda: d.ld.check_book(LAB, [{"account": "a1", "qty": 1}])) == FLATTEN_FIRST  # a2 leaves


# ---------------------------------------------------------------- M-D2: the day file follows a Lab write that failed
def test_a_round_whose_lab_file_cannot_be_written_leaves_the_day_file_saying_error_not_placing(tmp_path):
    import json

    from tests.test_engine_lab import go, leg, mk, restart
    eng, ads, _ = mk(tmp_path)

    def full(strict=False):
        if strict:
            raise OSError("disk full")
    eng._lab_save = full
    assert go(eng, leg())["accounts"]["a1"]["ok"] is False
    on_disk = json.loads(eng._day_path(eng._today()).read_text())[f"{LAB}@a1"]
    assert (on_disk["status"], on_disk["note"]) == ("error", "not written: disk full")      # the file is what memory is
    assert ads["a1"].brackets == []
    del eng._lab_save
    eng2 = restart(eng, tmp_path)
    assert eng2.states[f"{LAB}@a1"].status == "error"


def test_a_day_file_that_cannot_be_written_either_still_answers_nothing_was_sent(tmp_path):
    from tests.test_engine_lab import go, leg, mk
    eng, ads, _ = mk(tmp_path)

    def broken():
        raise OSError("disk gone")
    eng._save = broken
    out = go(eng, leg())["accounts"]["a1"]
    assert out == {"ok": False, "round": 1, "reason": "The Desk could not write this trade down. Nothing was sent."}
    assert ads["a1"].brackets == [] and eng.states[f"{LAB}@a1"].status == "error"
