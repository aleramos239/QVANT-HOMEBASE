"""The judgements behind tools/preopen_check.py (the collectors only read; these are the parts that decide)."""
from __future__ import annotations

from tools.preopen_check import (FAIL, OK, WARN, clock_level, depth_lag_level, fd_level, load_level, minutes_in_gaps,
                                 power_level, thin_stretches)

BUSY = {m: 90 for m in range(1000, 1100)}          # 100 normal minutes, ~90 trades each


def test_a_few_near_empty_minutes_between_busy_ones_are_one_stretch():
    c = dict(BUSY)
    for m in (1040, 1041, 1044, 1045):             # the 2026-10-02 06:05-06:10 shape: one trade in some minutes
        c[m] = 1
    assert thin_stretches(c, 1000, 1099) == [(1040, 1041), (1044, 1045)]


def test_quiet_hours_are_never_flagged():
    quiet = {m: 4 for m in range(1000, 1100)}
    quiet[1050] = 0
    assert thin_stretches(quiet, 1000, 1099) == []


def test_a_long_run_of_empty_minutes_is_still_found_but_marked_gaps_are_skipped():
    c = dict(BUSY)
    for m in range(1040, 1046):
        c.pop(m)
    assert thin_stretches(c, 1000, 1099) == [(1040, 1045)]
    marked = minutes_in_gaps([[1040 * 60000, 1045 * 60000 + 59999]])
    assert thin_stretches(c, 1000, 1099, skip=marked) == []


def test_malformed_gaps_are_ignored():
    assert minutes_in_gaps([["x"], None, [60000, 120000]]) == {1, 2}


def test_levels():
    assert depth_lag_level(14) == OK and depth_lag_level(600) == WARN
    assert fd_level(60, 256) == OK and fd_level(150, 256) == WARN and fd_level(250, 256) == FAIL
    assert load_level(3, 10) == OK and load_level(9, 10) == WARN and load_level(20, 10) == FAIL
    assert clock_level(0.2) == OK and clock_level(-3) == WARN and clock_level(40) == FAIL
    assert power_level(False, None, 500) == OK
    assert power_level(True, 600, 500) == WARN                  # on battery but it will last
    assert power_level(True, 96, 500) == FAIL                   # on battery and it will not reach the close


def test_one_quiet_minute_is_a_lull_but_one_empty_minute_is_a_gap():
    lull = dict(BUSY); lull[1050] = 2
    assert thin_stretches(lull, 1000, 1099) == []
    empty = dict(BUSY); del empty[1050]
    assert thin_stretches(empty, 1000, 1099) == [(1050, 1050)]
