"""The final fix wave of Step B, wave A (the Desk side): I1 (the window must end by the flat time), I2 (a fill the Desk
adopted from an order read reads filled), I3 (the state line says "check" while a trade needs a look), G1 (the runner
not connected), M-D1 (a finished trade whose old order still works), M-D2 (the day file follows a failed Lab write).
Real engine over the engine tests' fake adapters; no broker, no network; the store and the engine's root are temp
folders."""
from __future__ import annotations

import pytest

from homebase import labcfg
from homebase.labdesk import Refused
from homebase.labrun import store
from tests.labdesk_util import LAB, LIMITS, mkdesk, rec
from tests.test_engine import run

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
