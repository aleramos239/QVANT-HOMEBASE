"""The data rules: research window default, IS months, the holdout switch + spend log."""
from __future__ import annotations

import datetime as dt

import pytest

from homebase.backtest.discipline import (HOLDOUT_START, IS_MONTHS, RESEARCH_END, RESEARCH_START,
                                          DisciplineError, check, parse_range, record_spend, spends)


def test_constants_are_the_users_rules():
    assert (RESEARCH_START, RESEARCH_END) == (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
    assert HOLDOUT_START == dt.date(2025, 1, 1) and IS_MONTHS == (1, 4, 7, 10)


def test_default_range_is_the_research_window():
    r = parse_range(None)
    assert (r.kind, r.start, r.end, r.holdout) == ("research", RESEARCH_START, RESEARCH_END, False)
    assert r.label == "Research window 2021–2024"
    assert parse_range({"kind": "research", "end": "2026-01-01"}).end == RESEARCH_END   # fixed bounds
    assert check(r, None) is None


def test_is_months_keeps_jan_apr_jul_oct_only():
    r = parse_range({"kind": "is_months"})
    assert (r.start, r.end) == (RESEARCH_START, RESEARCH_END)
    assert r.includes(dt.date(2022, 4, 5)) and not r.includes(dt.date(2022, 5, 5))
    assert not r.includes(dt.date(2025, 1, 6))


def test_custom_range_validation():
    r = parse_range({"kind": "custom", "start": "2023-01-01", "end": "2023-06-30"})
    assert r.includes(dt.date(2023, 5, 5)) and not r.includes(dt.date(2023, 7, 3))
    for bad in ({"kind": "custom", "start": "2023-01-01"}, {"kind": "custom", "start": "x", "end": "2023-01-02"},
                {"kind": "custom", "start": "2023-02-01", "end": "2023-01-01"}, {"kind": "all"}, "research"):
        with pytest.raises(DisciplineError):
            parse_range(bad)


def test_a_2025_range_without_the_switch_is_refused():
    r = parse_range({"kind": "custom", "start": "2024-06-01", "end": "2025-01-01"})
    assert r.holdout
    for h in (None, {}, {"reason": "  "}, {"reason": "two\nlines"}, {"reason": "x" * 201}):
        with pytest.raises(DisciplineError):
            check(r, h)
    assert check(r, {"reason": " forward check of the OOS claim "}) == "forward check of the OOS claim"


def test_the_holdout_switch_inside_the_research_window_changes_nothing():
    assert check(parse_range(None), {"reason": "curious"}) is None


def test_a_spend_line_is_appended_never_rewritten(tmp_path):
    p = tmp_path / "tester" / "spends.jsonl"
    r = parse_range({"kind": "custom", "start": "2025-01-01", "end": "2025-06-30"})
    a = record_spend(p, strategy="nq930", inputs={"offset_pts": 5.0}, rng=r, reason="why", ts="T1")
    record_spend(p, strategy="ym930", inputs={}, rng=r, reason="again", ts="T2")
    p.write_text(p.read_text() + "{torn")
    got = spends(p)
    assert got[0] == a == {"ts": "T1", "strategy": "nq930", "inputs": {"offset_pts": 5.0},
                           "range": r.to_dict(), "reason": "why"}
    assert [s["strategy"] for s in got] == ["nq930", "ym930"]
