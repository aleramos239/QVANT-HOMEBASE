"""Bars: every type, footprint, session anchoring, live == bulk, resample == direct."""
from __future__ import annotations

import datetime as dt

import pytest

from homebase.charts.bars import BarBuilder, BarSpec, build, resample
from homebase.charts.tick import BUY, SELL, Tick
from tests.charts_util import D, session_ms

TS = 0.25
M = session_ms(D, 9, 30)


def T(ms, p, q=1, side=BUY, i=0):
    return Tick(ms, p, q, side, i)


def _k(b):
    return (b.t, b.session, b.o, b.h, b.l, b.c, b.v, b.buy, b.sell, b.n,
            round(b.pv, 6), round(b.p2v, 4), b.fp, b.big)


def test_spec_parse():
    assert BarSpec.parse("time:60") == BarSpec("time", 60)
    assert BarSpec.parse("tick:500").key == "tick:500"
    assert BarSpec("time", 300).from_minutes and not BarSpec("time", 30).from_minutes
    for bad in ("time", "time:0", "bogus:5", "tick:x"):
        with pytest.raises(ValueError):
            BarSpec.parse(bad)


def test_time_bars_footprint_and_big_prints():
    ticks = [T(M, 100.0), T(M + 20_000, 100.5, 2, SELL), T(M + 61_000, 101.0, 12)]
    closed, cur = build(ticks, BarSpec("time", 60), TS)
    b = closed[0]
    assert b.t == M and b.closed and not cur.closed
    assert (b.o, b.h, b.l, b.c, b.v, b.buy, b.sell, b.delta) == (100.0, 100.5, 100.0, 100.5, 3, 1, 2, -1)
    assert b.fp == {400: [0, 1], 402: [2, 0]}
    assert b.pv == 100.0 + 201.0
    assert cur.t == M + 60_000 and cur.big == [[M + 61_000, 101.0, 12, BUY]]


def test_four_hour_bars_anchor_at_the_18_et_open():
    t0 = session_ms(D, 18, 0)
    closed, cur = build([T(t0 + 1, 1.0), T(session_ms(D, 22, 0) + 5, 2.0)], BarSpec("time", 14400), TS)
    assert closed[0].t == t0 and cur.t == session_ms(D, 22, 0)


def test_no_bar_spans_two_sessions():
    nxt = D + dt.timedelta(days=1)
    closed, cur = build([T(session_ms(D, 16, 59, 59), 1.0), T(session_ms(nxt, 18, 0), 2.0)],
                        BarSpec("time", 86400), TS)
    assert [x.session for x in closed] == [D.isoformat()] and cur.session == nxt.isoformat()


def test_tick_volume_and_range_bars():
    ticks = [T(M + i, 100 + 0.25 * i, q=3) for i in range(10)]
    closed, cur = build(ticks, BarSpec("tick", 4), TS)
    assert [b.n for b in closed] == [4, 4] and cur.n == 2
    closed, cur = build(ticks, BarSpec("volume", 7), TS)
    assert [b.v for b in closed] == [9, 9, 9] and cur.v == 3
    closed, cur = build(ticks, BarSpec("range", 3), TS)
    assert [(b.l, b.h) for b in closed] == [(100.0, 100.75), (101.0, 101.75)]
    assert (cur.l, cur.h) == (102.0, 102.25)


def test_live_with_a_clock_equals_the_bulk_build():
    ticks = [T(M + i * 7_000, 100 + (i % 5) * 0.25, 1 + i % 3, BUY if i % 2 else SELL, i)
             for i in range(60)]
    spec = BarSpec("time", 30)
    bulk, bulk_cur = build(ticks, spec, TS)
    bb, live = BarBuilder(spec, TS), []
    for tk in ticks:
        live += bb.on_clock(tk.ts_ms - 1)      # the pump's clock, just behind each tick
        live += bb.add(tk)
    assert live == bulk and bb.cur == bulk_cur


def test_a_late_tick_after_a_clock_close_never_duplicates_a_bar():
    bb = BarBuilder(BarSpec("time", 60), TS)
    bb.add(T(M + 1_000, 100.0))
    assert len(bb.on_clock(M + 61_500)) == 1
    bb.add(T(M + 59_000, 100.25))              # late print for the closed minute
    assert bb.cur.t == M + 60_000


def test_on_clock_leaves_non_time_bars_alone():
    bb = BarBuilder(BarSpec("tick", 5), TS)
    bb.add(T(M, 100.0))
    assert bb.on_clock(M + 10 ** 9) == [] and bb.cur is not None


def test_resample_equals_a_direct_build():
    ticks = [T(M + i * 13_000, 100 + (i % 7) * 0.25, 1 + i % 4, BUY if i % 3 else SELL, i)
             for i in range(400)]
    minutes, cur = build(ticks, BarSpec("time", 60), TS)
    cur.closed = True
    minutes.append(cur)
    for size in (300, 900, 3600):
        direct, dcur = build(ticks, BarSpec("time", size), TS)
        rs = resample(minutes, BarSpec("time", size))
        assert [_k(b) for b in rs] == [_k(b) for b in direct + [dcur]]
    assert resample(minutes, BarSpec("time", 60)) is minutes


def test_resample_does_not_mutate_its_input():
    ticks = [T(M + i * 20_000, 100.0 + 0.25 * (i % 3), 2, BUY, i) for i in range(12)]
    minutes, cur = build(ticks, BarSpec("time", 60), TS)
    before = [_k(b) for b in minutes]
    resample(minutes, BarSpec("time", 300))
    assert [_k(b) for b in minutes] == before


def test_wire_is_et_wall_clock_with_priced_footprint():
    closed, _ = build([T(M, 100.0, 2, SELL), T(M + 1, 100.25, 3)], BarSpec("tick", 2), TS)
    w = closed[0].wire(TS)
    assert w["t"] == int(dt.datetime(2026, 9, 24, 9, 30, tzinfo=dt.timezone.utc).timestamp())
    assert w["ms"] == M and w["s"] == D.isoformat()
    assert w["fp"] == [[100.0, 2, 0], [100.25, 0, 3]] and w["d"] == 1
    assert "fp" not in closed[0].wire(TS, fp=False)


def test_wire_leaves_out_the_footprint_and_the_big_prints_only_when_asked_to():
    closed, _ = build([T(M, 100.0, 12, SELL), T(M + 1, 100.25, 3)], BarSpec("tick", 2), TS)
    full = closed[0].wire(TS)
    assert list(full)[-4:] == ["big", "sw", "bub", "fp"] and full["big"] == [[M, 100.0, 12, SELL]]
    assert closed[0].wire(TS, fp=False, big=False, flow=False) == {k: v for k, v in full.items() if k not in ("fp", "big", "sw", "bub")}
    assert closed[0].wire(TS, fp=False) == {k: v for k, v in full.items() if k != "fp"}
    assert closed[0].wire(TS, big=False) == {k: v for k, v in full.items() if k != "big"}
    assert closed[0].wire(TS, flow=False) == {k: v for k, v in full.items() if k not in ("sw", "bub")}


def test_resample_caps_sweeps_and_bubbles_once_with_the_same_rows_as_capping_every_merge():
    """merge(cap=False) + finish_merge() keeps exactly the rows that capping after every merge kept (the cap takes the
    top rows of a total order), however many one-minute bars an hour bar absorbs."""
    import random
    from tests.charts_util import D, session_ms
    from homebase.charts.bars import BUB_CAP, SW_CAP, Bar, BarSpec, resample
    rnd = random.Random(7)
    base = session_ms(D, 10, 0)      # on an hour bucket's edge (buckets anchor at the 18:00 open)
    minutes = []
    for i in range(60):
        b = Bar.open_at(base + i * 60_000, D.isoformat(), 100.0)
        b.closed, b.span = True, 60_000
        b.bub = [[base // 1000 + i * 60 + rnd.randrange(60), 100 + 0.25 * rnd.randrange(20), rnd.randrange(3, 40),
                  rnd.choice((1, -1))] for _ in range(30)]
        b.sw = [[base + i * 60_000 + rnd.randrange(60_000), 100.0, 100.5 + 0.25 * rnd.randrange(8), rnd.randrange(2, 30),
                 rnd.choice((1, -1))] for _ in range(8)]
        minutes.append(b)
    assert sum(len(m.bub) for m in minutes) > 5 * BUB_CAP and sum(len(m.sw) for m in minutes) > SW_CAP
    got = resample(minutes, BarSpec("time", 3600))
    ref = minutes[0].copy()
    for m in minutes[1:]:
        ref.merge(m)                      # the original behaviour: cap and sort after every merge
    assert len(got) == 1 and got[0].bub == ref.bub and got[0].sw == ref.sw
    assert len(got[0].bub) == BUB_CAP and len(got[0].sw) == SW_CAP


# ---- aggressive order counts (ords_b / ords_s): runs of one side's prints inside one millisecond

def test_a_bar_counts_the_orders_each_side_sent_one_run_per_millisecond_and_side():
    ticks = [T(M, 100.0, 1, BUY), T(M, 100.25, 2, BUY), T(M, 100.5, 3, BUY),     # one buy order walking up 3 levels
             T(M + 5, 100.5, 1, SELL),                                           # a sell order
             T(M + 9, 100.25, 1, BUY), T(M + 20, 100.25, 1, BUY),                # two more buy orders
             T(M + 30, 100.0, 4, SELL), T(M + 30, 99.75, 4, SELL)]               # one sell order, two prints
    closed, cur = build(ticks, BarSpec("time", 60), TS)
    b = cur
    assert (b.ords_b, b.ords_s) == (3, 2)
    assert b.n == 8 and b.buy == 8 and b.sell == 9


def test_order_counts_survive_resampling_and_an_uncounted_minute_makes_the_bar_uncounted():
    ticks = [T(M, 100.0, 1, BUY), T(M + 1, 100.0, 1, SELL), T(M + 61_000, 100.0, 1, BUY), T(M + 61_001, 100.0, 1, BUY),
             T(M + 130_000, 100.0, 1, BUY)]
    direct, cur = build(ticks, BarSpec("time", 180), TS)
    direct = direct + [cur]
    mins, cur1 = build(ticks, BarSpec("time", 60), TS)
    mins = mins + [cur1]
    for m in mins:
        m.closed = True
    five = resample(mins, BarSpec("time", 180))
    assert [(b.ords_b, b.ords_s) for b in five] == [(b.ords_b, b.ords_s) for b in direct] == [(4, 1)]
    mins[1].ords_b = mins[1].ords_s = -1                                        # a minute cached before the counts
    assert [(b.ords_b, b.ords_s) for b in resample(mins, BarSpec("time", 180))] == [(-1, -1)]


def test_a_pickled_bar_from_before_the_counts_loads_as_uncounted():
    import pickle
    from homebase.charts.bars import Bar
    b = Bar.open_at(M, "2026-10-09", 100.0)
    state = dict(b.__dict__)
    del state["ords_b"], state["ords_s"]
    old = Bar.__new__(Bar)
    old.__dict__.update(state)
    again = pickle.loads(pickle.dumps(old))
    assert (again.ords_b, again.ords_s) == (-1, -1)
