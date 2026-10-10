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
from tests.labdesk_util import LAB, LIMITS, entry, mkdesk, rec, send
from tests.test_engine import run
from tests.test_engine_lab import tick

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
