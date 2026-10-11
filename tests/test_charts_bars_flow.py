"""The tick fields a Bar carries for the order-flow indicators: te, span, sweeps (sw), bubbles (bub)."""
from __future__ import annotations

import random

from homebase.charts.bars import BUB_CAP, BarSpec, build, resample
from homebase.charts.tick import BUY, SELL, Tick

TS = 0.25
BASE = 1_760_000_040_000          # a whole minute (a multiple of 60 000 ms)
M1 = BarSpec.parse("time:60")


def T(ms, price, size=1, side=BUY):
    return Tick(BASE + ms, price, size, side)


def test_te_is_the_last_print_and_span_the_time_bars_length():
    closed, cur = build([T(0, 100.0), T(1500, 100.25), T(61_000, 101.0)], M1, TS)
    assert closed[0].te == BASE + 1500 and closed[0].span == 60_000
    assert cur.te == BASE + 61_000 and cur.span == 60_000
    tick_bars, _ = build([T(i * 10, 100.0) for i in range(6)], BarSpec.parse("tick:3"), TS)
    assert tick_bars[0].span == 0


def test_a_sweep_is_one_aggressor_walking_levels_inside_one_millisecond():
    ticks = [T(0, 100.0, 1), T(0, 100.25, 2), T(0, 100.75, 5),       # one ms, one side, 4 ticks wide
             T(5, 101.0, 4), T(5, 101.0, 3),                          # same ms and level twice: not a sweep
             T(9, 101.0, 1, SELL), T(9, 100.75, 1, SELL),             # two levels (1 tick): not a sweep
             T(20, 100.0, 1)]
    closed, cur = build(ticks, M1, TS)
    assert cur.wire(TS)["sw"] == [[BASE, 100.0, 100.75, 8, BUY]]
    closed, _ = build(ticks + [T(61_000, 100.0)], M1, TS)
    assert closed[0].sw == [[BASE, 100.0, 100.75, 8, BUY]]            # sealed with the bar


def test_bubbles_are_second_price_side_totals_of_at_least_three_largest_sixty_kept():
    ticks = [T(0, 100.0, 1), T(400, 100.0, 2), T(999, 100.0, 1, SELL),       # 100.0 buy 3 in second 0; the sell is 1
             T(1000, 100.0, 2), T(1100, 100.25, 9, SELL)]                    # second 1: buy 2 (below min), sell 9
    closed, cur = build(ticks + [T(61_000, 100.0)], M1, TS)
    sec0 = BASE // 1000
    assert closed[0].bub == [[sec0, 100.0, 3, BUY], [sec0 + 1, 100.25, 9, SELL]]
    many = [T(s * 1000, 100.0 + (s % 50) * TS, 3 + s % 7) for s in range(55)] + [T(s * 1000 + 500, 90.0, 40) for s in range(30)]
    bar, _ = build(many + [T(61_000, 100.0)], M1, TS)
    assert len(bar[0].bub) == BUB_CAP
    assert min(b[2] for b in bar[0].bub) >= 3
    assert sum(1 for b in bar[0].bub if b[2] == 40) == 30           # the big ones all stayed


def test_wire_carries_sw_and_bub_with_the_flow_flag_and_not_without():
    closed, _ = build([T(0, 100.0, 12), T(0, 100.5, 3), T(61_000, 100.0)], M1, TS)
    w = closed[0].wire(TS)
    assert "sw" in w and "bub" in w and "big" in w
    lean = closed[0].wire(TS, flow=False)
    assert "sw" not in lean and "bub" not in lean and "big" in lean
    assert "sw" in closed[0].wire(TS, big=False)


def test_resampled_bubbles_and_sweeps_equal_the_direct_build_on_an_ordered_tape():
    rng = random.Random(7)
    ticks, t = [], 0
    for _ in range(12000):
        t += rng.choice([0, 0, 1, 3, 40, 300, 900])
        ticks.append(T(t, 100.0 + rng.randint(0, 12) * TS, rng.randint(1, 15), rng.choice([BUY, SELL])))
    cut = ticks[-1].ts_ms + 1
    ticks.append(Tick(cut + 120_000, 100.0, 1, BUY))
    m1, _ = build(ticks, M1, TS)
    direct, _ = build(ticks, BarSpec.parse("time:300"), TS)
    via = resample(m1, BarSpec.parse("time:300"))
    n = min(len(direct), len(via)) - 1
    assert n >= 3
    for a, b in zip(direct[:n], via[:n]):
        assert a.sw == b.sw and a.bub == b.bub and a.te == b.te and a.span == b.span


def test_copy_keeps_the_developing_state_and_never_shares_it():
    _, cur = build([T(0, 100.0, 2), T(0, 100.25, 1)], M1, TS)      # one tick wide so far: no sweep
    c = cur.copy()
    c.add(T(0, 101.0, 4), TS)
    assert cur.wire(TS)["sw"] == [] and c.wire(TS)["sw"] == [[BASE, 100.0, 101.0, 7, BUY]]
