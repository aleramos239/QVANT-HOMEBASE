"""The cache warm-up command: every completed session's 1-minute bars built once, built ones skipped, a
session whose ticks changed rebuilt, the archive only read."""
from __future__ import annotations

import datetime as dt
import os

from homebase.charts.warm import parse_args, warm
from tests.charts_util import D, rows, session_ms, weekdays_before, write_archive


def archive(tmp_path, n=3):
    base = tmp_path / "ticks"
    days = weekdays_before(D, n)
    for k, d in enumerate(days + [D]):                             # D: today, still being written
        write_archive(base, "NQ", d, "NQZ6", rows(session_ms(d, 9, 30), [100.0 + k] * 5, first_id=100 * (k + 1)))
    return base, days


def test_warm_builds_each_completed_session_once(tmp_path):
    base, days = archive(tmp_path)
    cache, said = tmp_path / "cache", []
    seen = {p: p.stat().st_mtime_ns for p in base.rglob("*")}
    assert warm(["NQ"], base=base, cache_dir=cache, today=D, out=said.append) == {"built": 3, "skipped": 0}
    assert len(list(cache.glob("*.m1.pkl"))) == 3                   # not today's
    assert warm(["NQ"], base=base, cache_dir=cache, today=D, out=said.append) == {"built": 0, "skipped": 3}
    assert warm(["NQ"], days[1], base=base, cache_dir=cache, today=D, out=said.append) == {"built": 0, "skipped": 2}
    assert {p: p.stat().st_mtime_ns for p in base.rglob("*")} == seen   # the archive is only read
    assert any(days[0].isoformat() in line and "NQ" in line for line in said)


def test_warm_rebuilds_a_session_whose_ticks_changed(tmp_path):
    base, days = archive(tmp_path)
    cache = tmp_path / "cache"
    warm(["NQ"], base=base, cache_dir=cache, today=D, out=lambda line: None)
    src = next((base / "NQ").rglob(f"{days[0].isoformat()}_*.csv.gz"))
    later = src.stat().st_mtime_ns + 5_000_000_000
    os.utime(src, ns=(later, later))                               # a refill rewrote that session's ticks
    assert warm(["NQ"], base=base, cache_dir=cache, today=D, out=lambda line: None) == {"built": 1, "skipped": 2}


def test_the_command_line():
    a = parse_args(["--roots", "nq,ES", "--since", "2021-09-22"])
    assert a.roots == ["NQ", "ES"] and a.since == dt.date(2021, 9, 22)
    a = parse_args([])
    assert a.since is None and "NQ" in a.roots                     # the chart service's roots
