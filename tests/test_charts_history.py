"""History: 1-minute cache on disk, resampled bars == direct build, invalidation."""
from __future__ import annotations

import os
import time

from homebase.charts.bars import BarSpec, build
from homebase.charts.history import History
from homebase.charts.store import TickStore
from tests.charts_util import D, rows, session_ms, write_archive, write_gz


def _k(b):
    return (b.t, b.o, b.h, b.l, b.c, b.v, b.buy, b.sell, round(b.pv, 6), b.fp)


def setup(tmp_path, n=600):
    r = rows(session_ms(D, 9, 30), [100 + 0.25 * (i % 9) for i in range(n)], step_ms=7_000,
             sides=[1 if i % 3 else -1 for i in range(n)])
    src = write_archive(tmp_path / "ticks", "NQ", D, "NQZ6", r)
    store = TickStore(tmp_path / "ticks")
    return History(store, cache_dir=tmp_path / "cache"), store, src


def test_resampled_history_equals_a_direct_build(tmp_path):
    h, store, _ = setup(tmp_path)
    ticks = store.load("NQ", D).ticks
    for spec in (BarSpec("time", 60), BarSpec("time", 300), BarSpec("tick", 50)):
        closed, cur = build(ticks, spec, 0.25)
        want = closed + ([cur] if cur else [])
        got = h.bars("NQ", spec, D)
        assert [_k(b) for b in got] == [_k(b) for b in want]
        assert all(b.closed for b in got)


def test_minutes_are_cached_on_disk_and_reused(tmp_path):
    h, store, _ = setup(tmp_path)
    first = h.minutes("NQ", D)
    calls = []
    orig = store.load
    store.load = lambda *a: calls.append(a) or orig(*a)
    h2 = History(store, cache_dir=tmp_path / "cache")
    assert [_k(b) for b in h2.minutes("NQ", D)] == [_k(b) for b in first]
    assert calls == []


def test_a_newer_source_file_invalidates_the_cache(tmp_path):
    h, store, src = setup(tmp_path)
    h.minutes("NQ", D)
    future = time.time() + 60
    os.utime(src, (future, future))
    calls = []
    orig = store.load
    store.load = lambda *a: calls.append(a) or orig(*a)
    History(store, cache_dir=tmp_path / "cache").minutes("NQ", D)
    assert len(calls) == 1


def test_info_labels_the_session(tmp_path):
    h, _, _ = setup(tmp_path, n=5)
    assert h.info("NQ", D) == {"date": D.isoformat(), "contract": "NQZ6", "source": "archive",
                               "approx": False, "gaps": []}
    live = write_gz(tmp_path / "ticks" / "ES" / "2026" / f"{D}_ESZ6.live.csv.gz",
                    rows(session_ms(D, 9, 30), [1.0]))
    live.with_name(f"{D}_ESZ6.live.gaps").write_text(f"[[{session_ms(D, 9, 0)}, {session_ms(D, 9, 5)}]]")
    info = h.info("ES", D)
    assert info["source"] == "live" and len(info["gaps"]) == 1
    assert info["gaps"][0][1] - info["gaps"][0][0] == 300
    assert h.info("YM", D)["source"] is None
