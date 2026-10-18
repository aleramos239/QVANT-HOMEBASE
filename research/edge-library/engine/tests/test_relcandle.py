"""relcandle (engine/relcandle.py): the release candle of a data-release day -- the price just before 08:30:00 ET against the price m minutes
after, the file it is kept in, and the refusal of a date the file does not hold. Synthetic tapes only; no price of a real day is read."""
import datetime as dt

import numpy as np
import pytest

import l2sim as S
import relcandle as RC


class FakeTape:
    def __init__(self, d, pts):
        self.date = d
        t0 = S.et_ns(d, "08:30")
        self.ts = np.array([t0 + int(s * 1e9) for s, _ in pts], np.int64)
        self.px = np.array([p for _, p in pts], float)


def test_candle_is_last_print_before_the_release_against_last_print_m_minutes_after():
    d = dt.date(2024, 3, 12)
    tape = FakeTape(d, [(-30, 100.0), (-0.5, 101.0), (0.0, 101.5), (30, 103.0), (59.9, 99.0), (60.0, 98.0), (200, 105.0), (1000, 90.0)])
    c = RC.candle_of(tape)
    assert c["p0"] == 101.5                      # a print AT 08:30:00 counts as the price before the burst
    assert c["p1"] == 98.0                       # the print stamped exactly +60 s is inside the first minute
    assert c["p5"] == 105.0 and c["p15"] == 105.0 and c["p30"] == 90.0     # the print at +1000 s is past the 15-minute mark


def test_a_tape_with_nothing_before_the_release_has_no_price(tmp_path, monkeypatch):
    d = dt.date(2024, 3, 12)
    c = RC.candle_of(FakeTape(d, [(5.0, 100.0)]))
    assert np.isnan(c["p0"])


def test_file_round_trip_direction_gap_and_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "CACHE", tmp_path)
    RC._MEM.clear()
    tapes = {"2024-03-12": FakeTape(dt.date(2024, 3, 12), [(-1, 100.0), (60, 103.0), (300, 99.0)]),
             "2024-04-10": None}
    monkeypatch.setattr(S, "load_tape", lambda iso, root, allow_holdout=None: tapes[iso])
    out = RC.build("NQ", ["2024-03-12", "2024-04-10"], allow_holdout="x")
    assert out["added"] == 2 and out["rows"] == 2
    assert RC.direction("NQ", "2024-03-12", 1) == 1 and RC.direction("NQ", "2024-03-12", 5) == -1
    assert RC.direction("NQ", "2024-04-10", 5) is None                                  # a known date without a tape
    with pytest.raises(RC.RelCandleMissing):
        RC.direction("NQ", "2024-05-15", 5)                                             # a date never built: a code problem, not a quiet skip
    with pytest.raises(ValueError):
        RC.direction("NQ", "2024-03-12", 7)
    assert RC.build("NQ", ["2024-03-12"], allow_holdout="x")["added"] == 0              # nothing is loaded twice


def test_the_build_switch_refuses_a_day_of_the_test_range():
    with pytest.raises(S.HoldoutSealed):
        S.check_holdout(dt.date(2025, 7, 1), S.ALLOW_BP)
