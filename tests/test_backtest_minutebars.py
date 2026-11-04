"""1-minute sidecars: bars composed from a tape's minutes equal build_bars over its prints, and the sidecar file is
made once, kept fresh, never fails a run and never lands in the shared cache from a draft's store."""
from __future__ import annotations

import datetime as dt
import os
import random
from array import array
from bisect import bisect_left

from homebase.backtest import minutebars
from homebase.backtest import tape as tape_mod
from homebase.backtest.engine import Costs, build_bars, run_session
from homebase.backtest.tape import OverlayTapeStore, Tape, TapeStore, et_ns
from homebase.strategies.base import Strategy
from tests.charts_util import rows, write_archive

D = dt.date(2024, 3, 5)                                   # Tuesday
M = 60_000_000_000


def synthetic(seed: int = 7) -> Tape:
    """18:00 the evening before to 16:00: steps of 0 ns (prints sharing one ns) to minutes (empty minutes), prints on and
    one ns before whole minutes, and an empty 02:00-03:10."""
    r = random.Random(seed)
    ts, px, sz = array("q"), array("d"), array("i")
    t, end, p = et_ns(D, "-18:00"), et_ns(D, "16:00"), 18000.0
    hole = (et_ns(D, "02:00"), et_ns(D, "03:10"))
    while t < end:
        k = r.randrange(9)
        if k == 7:
            t = t - t % M + M                             # on a whole minute
        elif k == 8:
            t = t - t % M + M - 1                         # one ns before it
        else:
            t += (0, 0, 1, 250_000_000, 3_000_000_000, 45_000_000_000, 170_000_000_000)[k]
        if hole[0] <= t < hole[1]:
            t = hole[1] + 17
        p += r.choice((-0.25, 0.0, 0.25))
        ts.append(t)
        px.append(p)
        sz.append(r.randint(1, 9))
    return Tape("NQ", D, "NQH4", ts, px, sz, {})


SESSIONS = [("-18:00", "16:00"), ("09:30", "16:00"), ("09:30", "13:15"), ("09:31", "15:47"), ("-17:03", "11:00"),
            ("02:30", "03:30")]
BAR_WINDOWS = [None, ("09:00", "16:00"), ("09:31", "15:47"), ("-18:00", "16:00"), ("09:30:30", "12:00:10")]


def test_composed_bars_equal_build_bars_over_the_prints():
    tp = synthetic()
    m1 = minutebars.build(tp.ts, tp.px, tp.size)
    n = 0
    for w in SESSIONS:
        s0, s1 = et_ns(D, w[0]), et_ns(D, w[1])
        lo, hi = bisect_left(tp.ts, s0), bisect_left(tp.ts, s1)
        for bw in BAR_WINDOWS:
            t0, t1 = (s0, s1) if bw is None else (et_ns(D, bw[0]), et_ns(D, bw[1]))
            for mins in (1, 2, 3, 5, 15, 30, 60):
                want = build_bars(tp.ts, tp.px, tp.size, lo, hi, t0, t1, mins)
                assert build_bars(tp.ts, tp.px, tp.size, lo, hi, t0, t1, mins, m1) == want, (w, bw, mins)
                n += bool(want)
    assert n > 150


def test_a_window_with_no_prints_makes_no_bars():
    tp = synthetic()
    m1 = minutebars.build(tp.ts, tp.px, tp.size)
    lo = hi = bisect_left(tp.ts, et_ns(D, "02:00"))
    assert build_bars(tp.ts, tp.px, tp.size, lo, hi, et_ns(D, "02:00"), et_ns(D, "03:00"), 5, m1) == []


class Bars(Strategy):
    id, root = "bars", "NQ"

    def __init__(self, minutes, window, bar_window=None):
        super().__init__({})
        self.bar_minutes, self.session_window, self.bar_window, self.seen = minutes, window, bar_window, []

    def on_bar(self, ctx, bar):
        self.seen.append(bar)


def test_run_session_composes_only_on_whole_minutes():
    for w, bw, mins, composed in [(("09:30", "16:00"), None, 5, True), (("09:30", "13:15"), ("09:30", "16:00"), 15, True),
                                  (("09:30", "11:00"), ("09:00", "12:00"), 60, True), (("-18:00", "16:00"), None, 1, True),
                                  (("09:30:30", "16:00"), None, 5, False), (("09:30", "15:59:59"), None, 3, False)]:
        tp = synthetic()
        tp._m1, tp._m1_read = minutebars.build(tp.ts, tp.px, tp.size), True        # as if read from a fresh sidecar
        asked, real = [], tp.minutes
        tp.minutes = lambda: asked.append(1) or real()
        s = Bars(mins, w, bw)
        run_session(s, tp, Costs())
        b0, b1 = bw or w
        s0, s1 = et_ns(D, w[0]), et_ns(D, w[1])
        lo, hi = bisect_left(tp.ts, s0), bisect_left(tp.ts, s1)
        want = build_bars(tp.ts, tp.px, tp.size, lo, hi, et_ns(D, b0), et_ns(D, b1), mins)
        assert s.seen and s.seen == [b for b in want if b.end_ns < s1], (w, bw)          # a bar closing at the end: never seen
        assert bool(asked) == composed, (w, mins)


def test_a_tape_made_in_memory_has_no_minutes_and_its_bars_come_from_the_prints():
    tp = synthetic()
    assert tp.path is None and tp.minutes() is None
    s = Bars(5, ("09:30", "16:00"))
    run_session(s, tp, Costs())
    lo, hi = bisect_left(tp.ts, et_ns(D, "09:30")), bisect_left(tp.ts, et_ns(D, "16:00"))
    want = build_bars(tp.ts, tp.px, tp.size, lo, hi, et_ns(D, "09:30"), et_ns(D, "16:00"), 5)
    assert s.seen == [b for b in want if b.end_ns < et_ns(D, "16:00")]


# ---- the sidecar file

def archive(tmp_path):
    base = tmp_path / "ticks"
    prices = [100.0 + (i % 11) * 0.25 for i in range(1500)]
    write_archive(base, "NQ", D, "NQH4", rows(et_ns(D, "09:00:00") // 1_000_000, prices, step_ms=7_000,
                                              size=[1 + i % 4 for i in range(1500)]))
    return base


def counting(monkeypatch) -> list:
    calls, real = [], minutebars.build
    monkeypatch.setattr(minutebars, "build", lambda *a: calls.append(1) or real(*a))
    return calls


def listing(p):
    return sorted((str(q.relative_to(p)), q.stat().st_mtime_ns) for q in p.rglob("*"))


def test_the_sidecar_is_written_once_beside_the_tape_and_reused(tmp_path, monkeypatch):
    s = TapeStore(archive(tmp_path), tmp_path / "cache")
    tp = s.load("NQ", D)
    m = tp.minutes()
    assert tp.path == s.cache_path("NQ", D) and (tmp_path / "cache" / "NQ" / f"{D}.m1").exists()
    assert m == minutebars.build(tp.ts, tp.px, tp.size) and minutebars.fresh(tp.path)
    calls = counting(monkeypatch)
    again = s.load("NQ", D)
    assert again.minutes() == m and again.minutes() is again.minutes() and calls == []


def test_a_changed_or_torn_tape_sidecar_is_rebuilt(tmp_path, monkeypatch):
    s = TapeStore(archive(tmp_path), tmp_path / "cache")
    m = s.load("NQ", D).minutes()
    p = s.cache_path("NQ", D)
    calls = counting(monkeypatch)
    os.utime(p, ns=(p.stat().st_atime_ns, p.stat().st_mtime_ns + 1_000_000_000))     # the .tape rebuilt
    assert not minutebars.fresh(p)
    assert s.load("NQ", D).minutes() == m and len(calls) == 1 and minutebars.fresh(p)
    side = minutebars.sidecar(p)
    side.write_bytes(side.read_bytes()[:100])                                                 # a torn file
    assert s.load("NQ", D).minutes() == m and len(calls) == 2 and minutebars.fresh(p)


def test_a_sidecar_that_cannot_be_written_fails_nothing(tmp_path, monkeypatch):
    s = TapeStore(archive(tmp_path), tmp_path / "cache")
    tp = s.load("NQ", D)

    def refuse(*a):
        raise PermissionError("read-only cache")
    monkeypatch.setattr(minutebars.os, "replace", refuse)
    assert tp.minutes() == minutebars.build(tp.ts, tp.px, tp.size)
    assert [q.name for q in (tmp_path / "cache" / "NQ").iterdir()] == [f"{D}.tape"]          # no sidecar, no .tmp


def test_a_drafts_store_reads_the_shared_sidecar_and_never_builds_one(tmp_path, monkeypatch):
    base, shared, private = archive(tmp_path), tmp_path / "shared", tmp_path / "private"
    TapeStore(base, shared).load("NQ", D)                                                     # the .tape, no sidecar yet
    before = listing(shared)
    calls = counting(monkeypatch)
    tp = OverlayTapeStore(base, shared, private).load("NQ", D)
    assert tp.path == shared / "NQ" / f"{D}.tape"
    assert tp.minutes() is None and calls == []                 # no sidecar yet: its bars come from the prints, as before
    assert listing(shared) == before and not list(private.rglob("*.m1"))
    m = TapeStore(base, shared).load("NQ", D).minutes()                                       # the warm job's sidecar
    assert len(calls) == 1
    assert OverlayTapeStore(base, shared, private).load("NQ", D).minutes() == m and len(calls) == 1
    assert not list(private.rglob("*.m1"))


def test_the_warm_job_keeps_the_sidecar_fresh(tmp_path):
    base, cache = archive(tmp_path), tmp_path / "cache"
    p = TapeStore(base, cache).cache_path("NQ", D)
    tape_mod._warm_one((str(base), str(cache), "NQ", D))
    assert p.exists() and minutebars.fresh(p)
    os.utime(p, ns=(p.stat().st_atime_ns, p.stat().st_mtime_ns + 1_000_000_000))
    tape_mod._warm_one((str(base), str(cache), "NQ", D))
    assert minutebars.fresh(p)


def test_5_15_and_30_second_bars_sit_on_whole_seconds_and_make_up_the_minute():
    tp = synthetic()
    t0, t1 = et_ns(D, "09:30"), et_ns(D, "16:00")
    lo, hi = bisect_left(tp.ts, t0), bisect_left(tp.ts, t1)
    one = build_bars(tp.ts, tp.px, tp.size, lo, hi, t0, t1, 1)
    for mins, secs in ((0.5, 30), (0.25, 15), (5 / 60, 5)):
        bars = build_bars(tp.ts, tp.px, tp.size, lo, hi, t0, t1, mins)
        assert bars and all(type(b.start_ns) is int and b.start_ns % (secs * 1_000_000_000) == 0
                            and b.end_ns - b.start_ns == secs * 1_000_000_000 for b in bars)
        by_min = {}
        for b in bars:
            by_min.setdefault(b.start_ns - b.start_ns % M, []).append(b)
        for m in one:                                  # the sub-minute bars of a minute rebuild it
            parts = by_min[m.start_ns]
            assert (parts[0].o, max(p.h for p in parts), min(p.l for p in parts), parts[-1].c, sum(p.v for p in parts)) \
                == (m.o, m.h, m.l, m.c, m.v)
