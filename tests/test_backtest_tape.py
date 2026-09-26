"""Tape loader: front-contract pick, cache, tape order, coverage — on a synthetic archive."""
from __future__ import annotations

import datetime as dt
import json
import os

import pytest

from homebase.backtest import tape as tape_mod
from homebase.backtest.tape import TapeStore, coverage_reason, et_ns, missing_hours
from tests.charts_util import FIELDS, rows, write_archive, write_gz

D = dt.date(2024, 3, 5)                                   # Tuesday


def ms(hms: str) -> int:
    return et_ns(D, hms) // 1_000_000


def archive(tmp_path, n=1500, contract="NQH4", start="09:00:00", step_ms=1000):
    base = tmp_path / "ticks"
    write_archive(base, "NQ", D, contract, rows(ms(start), [100.0 + (i % 8) * 0.25 for i in range(n)],
                                                step_ms=step_ms))
    return base


def listing(p):
    return sorted((str(q.relative_to(p)), q.stat().st_mtime_ns) for q in p.rglob("*"))


def test_front_contract_is_the_file_with_the_most_ticks(tmp_path):
    base = archive(tmp_path, n=1500, contract="NQH4")
    write_archive(base, "NQ", D, "NQM4", rows(ms("09:00:00"), [200.0] * 1200))
    s = TapeStore(base, tmp_path / "cache")
    assert s.pick("NQ", D)[1] == "NQH4"
    t = s.load("NQ", D)
    assert t.contract == "NQH4" and len(t.ts) == 1500 and t.px[0] == 100.0


def test_a_holiday_stub_under_min_ticks_has_no_tape(tmp_path):
    s = TapeStore(archive(tmp_path, n=999), tmp_path / "cache")
    assert s.pick("NQ", D) is None and s.load("NQ", D) is None


def test_live_recordings_are_never_used(tmp_path):
    base = tmp_path / "ticks"
    write_gz(base / "NQ" / "2024" / f"{D}_NQH4.live.csv.gz", rows(ms("09:00:00"), [1.0] * 2000))
    assert TapeStore(base, tmp_path / "cache").pick("NQ", D) is None


def test_ts_ns_is_used_when_present_and_ts_ms_otherwise(tmp_path):
    base = tmp_path / "ticks"
    rs = rows(ms("09:30:00"), [100.0] * 1200)
    for i, r in enumerate(rs):
        r["ts_ns"] = r["ts_ms"] * 1_000_000 + 7 + i
    p = write_gz(base / "NQ" / "2024" / f"{D}_NQH4.csv.gz", rs, fields=FIELDS + ["ts_ns"])
    p.with_name(f"{D}_NQH4.json").write_text(json.dumps({"ticks": 1200}))
    t = TapeStore(base, tmp_path / "cache").load("NQ", D)
    assert t.ts[0] == et_ns(D, "09:30:00") + 7
    t2 = TapeStore(archive(tmp_path / "b"), tmp_path / "cache2").load("NQ", D)
    assert t2.ts[0] == et_ns(D, "09:00:00")


def test_out_of_order_rows_are_stable_sorted_keeping_same_ts_row_order(tmp_path):
    base = tmp_path / "ticks"
    rs = rows(ms("09:30:00"), [float(i) for i in range(1200)])
    rs[5]["ts_ms"] = rs[3]["ts_ms"]                        # row 5 shares row 3's stamp...
    rs[1], rs[2] = rs[2], rs[1]                            # ...and rows 1/2 arrive swapped
    write_archive(base, "NQ", D, "NQH4", rs)
    t = TapeStore(base, tmp_path / "cache").load("NQ", D)
    assert list(t.px[:6]) == [0.0, 1.0, 2.0, 3.0, 5.0, 4.0]    # 5 sorts with 3, after it


def test_the_cache_is_built_once_and_rebuilt_when_the_source_changes(tmp_path, monkeypatch):
    base = archive(tmp_path)
    s = TapeStore(base, tmp_path / "cache")
    assert not s.cached("NQ", D)
    s.load("NQ", D)
    assert s.cache_path("NQ", D).exists() and s.cached("NQ", D)
    calls = []
    real = tape_mod.read_archive_csv
    monkeypatch.setattr(tape_mod, "read_archive_csv", lambda p: calls.append(p) or real(p))
    s.load("NQ", D)
    assert calls == []                                     # served from the cache
    src = base / "NQ" / "2024" / f"{D}_NQH4.csv.gz"
    os.utime(src, ns=(src.stat().st_atime_ns, src.stat().st_mtime_ns + 1_000_000_000))
    s.load("NQ", D)
    assert len(calls) == 1                                 # stale -> rebuilt


def test_nothing_is_ever_written_under_the_archive(tmp_path):
    base = archive(tmp_path)
    before = listing(base)
    s = TapeStore(base, tmp_path / "cache")
    s.load("NQ", D)
    s.daily("NQ", D)
    assert listing(base) == before
    with pytest.raises(ValueError):
        TapeStore(base, base / "NQ" / "cache")


def test_daily_bar_is_the_whole_session(tmp_path):
    s = TapeStore(archive(tmp_path), tmp_path / "cache")
    assert s.daily("NQ", D) == {"date": "2024-03-05", "h": 101.75, "l": 100.0, "c": 100.0 + (1499 % 8) * 0.25}


def test_sessions_lists_weekdays_with_a_manifest_in_range(tmp_path):
    base = archive(tmp_path)
    write_archive(base, "NQ", dt.date(2024, 3, 9), "NQH4", rows(ms("09:00:00"), [1.0] * 1500))   # Saturday
    write_archive(base, "NQ", dt.date(2024, 3, 7), "NQH4", rows(ms("09:00:00"), [1.0] * 1500))
    s = TapeStore(base, tmp_path / "cache")
    assert s.sessions("NQ", dt.date(2024, 3, 1), dt.date(2024, 3, 31)) == [D, dt.date(2024, 3, 7)]
    assert s.sessions("NQ", dt.date(2024, 3, 6), dt.date(2024, 3, 6)) == []


def test_missing_hours_lists_runs_of_empty_clock_hours(tmp_path):
    base = tmp_path / "ticks"
    rs = rows(ms("09:25:00"), [1.0] * 2100, step_ms=6000)          # 09:25 -> 12:55
    rs += rows(ms("15:10:00"), [1.0] * 100, step_ms=6000)          # 15:10 -> 15:20
    write_archive(base, "NQ", D, "NQH4", rs)
    t = TapeStore(base, tmp_path / "cache").load("NQ", D)
    gaps = missing_hours(t.ts, D, ("09:25", "16:00"))
    assert gaps == [("13:00", "15:00")]
    assert coverage_reason(gaps) == "missing 13:00–15:00 ET"
    assert missing_hours(t.ts, D, ("09:25", "13:00")) == []
    assert missing_hours(t.ts, D, ("08:20", "09:56")) == [("08:20", "09:00")]


# Item 2: half days -- the day after Thanksgiving, and Dec 24 / Jul 3 when they land
# on a weekday -- shorten equity-index trading to 13:15 ET; that empty afternoon is
# an early close, not a coverage hole.

def test_the_early_close_calendar_has_the_expected_dates():
    assert dt.date(2024, 11, 29) in tape_mod.EARLY_CLOSES     # day after Thanksgiving 2024 (Fri)
    assert dt.date(2021, 11, 26) in tape_mod.EARLY_CLOSES     # day after Thanksgiving 2021 (Fri)
    assert dt.date(2024, 12, 24) in tape_mod.EARLY_CLOSES     # a Tuesday
    assert dt.date(2022, 12, 24) not in tape_mod.EARLY_CLOSES  # a Saturday: not even a session
    assert dt.date(2023, 7, 3) in tape_mod.EARLY_CLOSES       # a Monday
    assert dt.date(2021, 7, 2) in tape_mod.EARLY_CLOSES       # observed: Jul 4, 2021 was a Sunday
    assert dt.date(2022, 7, 1) not in tape_mod.EARLY_CLOSES   # Jul 4, 2022 was a Monday: no half day


def test_early_close_et_is_scoped_to_equity_index_roots():
    assert tape_mod.early_close_et("NQ", dt.date(2024, 12, 24)) == "13:15"
    assert tape_mod.early_close_et("YM", dt.date(2024, 12, 24)) == "13:15"
    assert tape_mod.early_close_et("GC", dt.date(2024, 12, 24)) is None      # no time for metals here
    assert tape_mod.early_close_et("NQ", dt.date(2024, 3, 5)) is None        # an ordinary day


def test_effective_session_window_clamps_to_the_early_close():
    assert tape_mod.effective_session_window("NQ", dt.date(2024, 12, 24),
                                              ("09:25", "16:00")) == ("09:25", "13:15")
    assert tape_mod.effective_session_window("NQ", D, ("09:25", "16:00")) == ("09:25", "16:00")
    assert tape_mod.effective_session_window("GC", dt.date(2024, 12, 24),
                                              ("08:20", "09:56")) == ("08:20", "09:56")
    # a strategy whose ordinary window already ends before the early close is unaffected
    assert tape_mod.effective_session_window("NQ", dt.date(2024, 12, 24),
                                              ("09:25", "10:00")) == ("09:25", "10:00")
