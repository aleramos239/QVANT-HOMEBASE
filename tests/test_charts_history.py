"""History: 1-minute cache on disk, resampled bars == direct build, invalidation."""
from __future__ import annotations

import datetime as dt
import os
import time

from homebase.charts.bars import BarSpec, build
from homebase.charts.history import History
from homebase.charts.recorder import LiveRecorder
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


def test_a_24_7_session_keeps_its_17_00_hour_and_weekend_bars(tmp_path):
    """Bitcoin's Saturday session (Fri 18:00 -> Sat 18:00) is built with its
    own trading day: its bars, the 17:00 hour included, are Saturday's --
    not Monday's (the classic weekend rule)."""
    sat = D + dt.timedelta(days=2)
    write_gz(tmp_path / "ticks" / "BTC" / "2026" / f"{sat}_BTCV6.live.csv.gz",
             rows(session_ms(sat, 16, 59, 30), [100_000.0, 100_005.0], step_ms=31 * 60_000))
    h = History(TickStore(tmp_path / "ticks"), cache_dir=tmp_path / "cache")
    assert [(b.session, b.t) for b in h.bars("BTC", BarSpec("time", 60), sat)] == [
        (sat.isoformat(), session_ms(sat, 16, 59)), (sat.isoformat(), session_ms(sat, 17, 30))]


def test_a_build_racing_a_write_to_its_session_is_not_served_again(tmp_path):
    """A refill can append to an OLD session's file while a chart builds that
    session in a worker thread, and the server then clears the memo. That
    build read the file before the append: what it produced must not be
    served afterwards -- neither from the memo nor from the minute cache."""
    fri = D + dt.timedelta(days=1)
    base = tmp_path / "ticks"
    src = write_gz(base / "BTC" / "2026" / f"{fri}_BTCV6.live.csv.gz",
                   rows(session_ms(fri, 17, 38), [1.0, 2.0, 3.0], step_ms=60_000))
    past = time.time() - 60
    os.utime(src, (past, past))                                  # recorded a minute ago

    class Racing(History):
        hook = None

        def _from_ticks(self, root, spec, d):
            out = super()._from_ticks(root, spec, d)             # reads the file...
            hook, Racing.hook = Racing.hook, None
            if hook:
                hook()                                           # ...then the refill lands
            return out

    h = Racing(TickStore(base), cache_dir=tmp_path / "cache")
    rec = LiveRecorder(base)

    def refill_lands():
        rec.append("BTC", "BTCV6", rows(session_ms(fri, 17, 50), [4.0], first_id=100))
        rec.flush()
        h.clear()

    Racing.hook = refill_lands
    h.bars("BTC", BarSpec("time", 60), fri)                     # the racing build
    assert [b.t for b in h.bars("BTC", BarSpec("time", 60), fri)] == [
        session_ms(fri, 17, m) for m in (38, 39, 40, 50)]


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
