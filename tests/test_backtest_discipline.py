"""The data rules: the build days by default, IS months, and the (never blocking) spend log."""
from __future__ import annotations

import datetime as dt

import pytest

from homebase.backtest.discipline import (HOLDOUT_START, IS_MONTHS, RESEARCH_END, RESEARCH_START,
                                          DisciplineError, parse_range, record, spends, stored_range)


def test_constants_are_the_blueprints_dates():
    """research/edge-library/BLUEPRINT.md section 2: build 2021-09-22 -> 2025-06-30, test from 2025-07-01."""
    assert (RESEARCH_START, RESEARCH_END) == (dt.date(2021, 9, 22), dt.date(2025, 6, 30))
    assert HOLDOUT_START == dt.date(2025, 7, 1) == RESEARCH_END + dt.timedelta(days=1)
    assert IS_MONTHS == (1, 4, 7, 10)


def test_default_range_is_the_build_days():
    r = parse_range(None)
    assert (r.kind, r.start, r.end, r.holdout) == ("research", RESEARCH_START, RESEARCH_END, False)
    assert r.label == "Build · Sep 2021 – Jun 2025"
    assert parse_range({"kind": "research", "end": "2026-01-01"}).end == RESEARCH_END   # fixed bounds


def test_labels_are_plain_words():
    """Build and Test by name; any other window by its dates."""
    assert parse_range({"kind": "research"}).label == "Build · Sep 2021 – Jun 2025"
    test = parse_range({"kind": "custom", "start": "2025-07-01", "end": "2026-10-06"})
    assert test.label == "Test · Jul 2025 → 2026-10-06" and test.holdout is True
    for start, end in (("2021-01-01", "2026-10-06"), ("2021-09-22", "2025-06-30"), ("2021-01-01", "2024-12-31")):
        assert parse_range({"kind": "custom", "start": start, "end": end}).label == f"{start} → {end}"
    assert parse_range({"kind": "is_months", "start": "2025-07-01", "end": "2026-01-31"}).label == \
        "IS months (Jan/Apr/Jul/Oct) 2025-07-01 → 2026-01-31"


def test_a_stored_research_range_keeps_the_dates_it_was_stored_with():
    """A request.json written when the default was 2021-2024 -- before 2026-10-06, or by a chart service
    still on that code -- runs ITS days, so a result never carries a label its days do not match."""
    old = {"kind": "research", "start": "2021-01-01", "end": "2024-12-31",
           "label": "Research window 2021–2024", "holdout": False}
    r = stored_range(old)
    assert (r.kind, r.start, r.end, r.holdout) == ("research", dt.date(2021, 1, 1), dt.date(2024, 12, 31), False)
    assert parse_range(old) == parse_range(None)          # a CLIENT's body still cannot move the default
    assert stored_range({"kind": "research"}) == parse_range(None)                    # no dates: today's
    for rng in (None, {"kind": "custom", "start": "2025-07-01", "end": "2026-01-31"},
                {"kind": "is_months", "start": "2024-10-01", "end": "2026-04-30"}):
        assert stored_range(parse_range(rng).to_dict()) == parse_range(rng)           # every kind round-trips
    with pytest.raises(DisciplineError):
        stored_range({"kind": "research", "start": "2024-12-31", "end": "2021-01-01"})


def test_is_months_keeps_jan_apr_jul_oct_only():
    r = parse_range({"kind": "is_months"})
    assert (r.start, r.end) == (RESEARCH_START, RESEARCH_END)
    assert r.includes(dt.date(2022, 4, 5)) and not r.includes(dt.date(2022, 5, 5))
    assert r.includes(dt.date(2025, 4, 7)) and not r.includes(dt.date(2025, 7, 7))    # July: past the build days
    assert not r.includes(dt.date(2021, 7, 6))                                         # ... and before them


def test_custom_range_validation():
    r = parse_range({"kind": "custom", "start": "2023-01-01", "end": "2023-06-30"})
    assert r.includes(dt.date(2023, 5, 5)) and not r.includes(dt.date(2023, 7, 3))
    for bad in ({"kind": "custom", "start": "2023-01-01"}, {"kind": "custom", "start": "x", "end": "2023-01-02"},
                {"kind": "custom", "start": "2023-02-01", "end": "2023-01-01"}, {"kind": "all"}, "research"):
        with pytest.raises(DisciplineError):
            parse_range(bad)


def test_no_range_is_refused_any_more_however_late_it_reaches():
    """2026-09-27, the user's instruction: the 2025+ guard is gone. discipline still
    LABELS a range as reaching the test days (2025-07-01 on), but nothing refuses it."""
    for late in ({"kind": "custom", "start": "2024-06-01", "end": "2025-07-01"},
                 {"kind": "custom", "start": "2025-07-01", "end": "2026-12-31"},
                 {"kind": "is_months", "start": "2024-10-01", "end": "2026-04-30"}):
        assert parse_range(late).holdout is True
    # the first half of 2025 is build days now: reading it is not a read of the test days
    assert parse_range({"kind": "custom", "start": "2025-01-01", "end": "2025-06-30"}).holdout is False
    assert not hasattr(__import__("homebase.backtest.discipline", fromlist=["x"]), "check")


def test_a_malformed_range_is_still_refused():
    """Nothing blocks a DATE any more, but a range that is not a range still fails."""
    for bad in ({"kind": "custom", "start": "2025-01-01"}, {"kind": "custom", "start": "x", "end": "2025-01-02"},
                {"kind": "custom", "start": "2025-02-01", "end": "2025-01-01"}, {"kind": "all"}, "research"):
        with pytest.raises(DisciplineError):
            parse_range(bad)


def test_a_spend_line_is_appended_never_rewritten(tmp_path):
    p = tmp_path / "tester" / "spends.jsonl"
    r = parse_range({"kind": "custom", "start": "2025-07-01", "end": "2025-12-31"})
    a = record(p, strategy="nq930", inputs={"offset_pts": 5.0}, rng=r, ts="T1")
    record(p, strategy="ym930", inputs={}, rng=r, ts="T2")
    p.write_text(p.read_text() + "{torn")
    got = spends(p)
    assert got[0] == a == {"ts": "T1", "strategy": "nq930", "inputs": {"offset_pts": 5.0},
                           "range": r.to_dict()}
    assert [s["strategy"] for s in got] == ["nq930", "ym930"]


def test_a_range_inside_the_build_days_writes_nothing(tmp_path):
    """The log records what touched the test days, nothing else -- and it never blocks either way."""
    p = tmp_path / "tester" / "spends.jsonl"
    assert record(p, strategy="nq930", inputs={}, rng=parse_range(None)) is None
    assert record(p, strategy="nq930", inputs={},
                  rng=parse_range({"kind": "custom", "start": "2022-01-01", "end": "2025-06-30"})) is None
    assert not p.exists() and spends(p) == []


def test_a_spend_records_its_run_id_when_given(tmp_path):
    """execute()'s dedup keys off run_id, so a spend that carries one lets a later
    caller recognize it was already logged for this run."""
    p = tmp_path / "tester" / "spends.jsonl"
    r = parse_range({"kind": "custom", "start": "2025-07-01", "end": "2025-12-31"})
    a = record(p, strategy="nq930", inputs={}, rng=r, run_id="RID1", ts="T1")
    assert a["run_id"] == "RID1" and spends(p)[0]["run_id"] == "RID1"
