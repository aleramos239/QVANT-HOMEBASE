"""BATCH 4 filter blocks: bbw, atrp, er, macd, rsidiv, mfi, deltadiv, candle -- engine/indicators.py (the math, first-guess definitions of
2026-10-06 in its docstring) and their glue in families/blocks.py.

  (i)   the math at its thresholds on hand-built bars (rank, ratio, divergence, money flow, candle shapes), and the glue's verdict at each
        threshold of each side (the indicator is replaced by a number): both sides blocked where there is no signal;
  (ii)  each block against an INDEPENDENT loop on random minute bars: the verdict at EVERY decision of a session for both sides and every mode;
  (iii) NO LOOK-AHEAD: prints (and flow rows) from a decision on change nothing decided up to it;
  (iv)  the registry: filters, plain words, defaults, the delta cap; (v) real BUILD days: identical trades at 1 and 8 workers on NQ, ES and GC.
No net, win rate or profit factor is printed or read."""
import math

import numpy as np
import pytest

import flowtab as FT
import indicators as IND
import l2sim as S
import run_menus as RM
from families import blocks as B
from test_blocks import D, W, days_of, flat_bars, garble, minute_tape, ns, rand_bars, real_days, rsi_ref
from test_blocks_batch1 import T0, bars_until, probe, tape_of
from test_blocks_flow import minute_index, prefix

NEW = {"bbw": ("tight", "wide"), "atrp": ("high", "low"), "er": ("trend", "chop"), "macd": ("with", "against"), "rsidiv": ("with", "against"),
       "mfi": ("with", "against", "extreme_against"), "deltadiv": ("with", "against"), "candle": ("displace", "engulf", "reject")}
SIDES = (("long", 1), ("short", -1))


def shaped_bars(n, seed):
    """rand_bars with a big impulse bar (body 36 points, the close at its extreme) every 29th bar, up and down in turn, the walk shifted after it."""
    out, shift = [], 0.0
    for i, (o, h, l, c, v) in enumerate(rand_bars(n, seed, step=4.0)):
        o, h, l, c = o + shift, h + shift, l + shift, c + shift
        if i % 29 == 28:
            up = (i // 29) % 2 == 1
            c2 = o + (36.0 if up else -36.0)
            h, l = (c2, o - 0.25) if up else (o + 0.25, c2)
            shift += c2 - c
            c = c2
        out.append((o, h, l, c, v))
    return out


N_BARS = 330                                        # 08:00 .. 13:30: the "mid" session (11:00 .. 13:30) has >= 180 closes at every decision
BARS = shaped_bars(N_BARS, 11)
TAPE = tape_of(BARS)
MID = {"sess": "mid"}
FLAT = minute_tape(flat_bars(60), "09:00")


def put(p, params):
    return probe({**MID, **p, **params}, TAPE)


# ---- (i) the math on hand-built bars ---------------------------------------------------------------------------------------------------

def test_midrank_counts_the_share_below_and_half_of_the_ties():
    assert IND._midrank(3, [1, 2, 3, 4, 5]) == 0.5 and IND._midrank(0, [1, 2]) == 0.0 and IND._midrank(9, [1, 2]) == 1.0
    assert IND._midrank(1.0, [1.0] * 7) == 0.5                      # a flat series sits in the middle, never at an end


def test_bbw_rank_needs_140_closes_and_ranks_the_last_bandwidth_among_the_120_before():
    g = np.random.default_rng(3)
    noise = (15000.0 + g.normal(0, 1.0, 120)).tolist()
    assert IND.bbw_rank(noise + [15000.0] * 19) is None             # 139 closes
    assert IND.bbw_rank(noise + [15000.0] * 20) == 0.0              # the last band is flat: narrower than all 120 before
    assert IND.bbw_rank([15000.0] * 120 + (15000.0 + g.normal(0, 5.0, 20)).tolist()) == 1.0     # wider than every calm band
    assert IND.bbw_rank([15000.0] * 140) == 0.5                      # nothing varies: the middle
    assert IND.bbw_rank(noise + [15000.0] * 20 + [15000.0]) is not None


def test_atr_rank_is_wilders_atr_among_the_100_before_and_needs_114_bars():
    def bars(ranges):
        return [15000.0 + r for r in ranges], [15000.0] * len(ranges), [15000.0] * len(ranges)       # high, low, close (close = low: TR = the range)
    h, l, c = bars([4.0] * 113)
    assert IND.atr_rank(h, l, c) is None                             # 113 bars
    h, l, c = bars([4.0] * 114)
    assert IND.atr_rank(h, l, c) == 0.5                              # a constant range: the middle
    h, l, c = bars([4.0] * 113 + [40.0])
    assert IND.atr_rank(h, l, c) == 1.0
    h, l, c = bars([40.0 - 0.2 * i for i in range(114)])             # a shrinking range: the last ATR is the lowest
    assert IND.atr_rank(h, l, c) == 0.0
    a = IND.atr_series([5.0] * 3, [1.0] * 3, [3.0] * 3, 2)           # TR = 4 each (the first = high - low): ATR(2) = 4 throughout
    assert a == [4.0, 4.0]


def test_efficiency_ratio_at_its_thresholds():
    def walk(*steps):                                               # closes from 100 by (size, count) steps
        c = [100.0]
        for size, n in steps:
            for _ in range(n):
                c.append(c[-1] + size)
        assert len(c) == 15
        return c
    assert IND.efficiency(walk((1.0, 14))) == 1.0 and IND.efficiency(walk((-1.0, 14))) == 1.0
    assert IND.efficiency(walk((1.0, 12), (-1.0, 2))) == 10 / 14
    assert IND.efficiency(walk((1.0, 12), (-2.0, 2))) == 0.5       # net 8, path 16
    assert IND.efficiency(walk((1.0, 10), (-1.5, 4))) == 0.25      # net 4, path 16
    assert IND.efficiency(walk((1.0, 10), (-1.5, 3), (-1.0, 1))) > 0.25
    assert IND.efficiency([100.0] * 15) is None and IND.efficiency(walk((1.0, 14))[1:]) is None      # no movement / 14 closes


def test_macd_direction_needs_35_closes_and_a_histogram_that_is_not_fading():
    up = [100.0 + 0.1 * i * i for i in range(60)]
    assert IND.macd_dir(up) == 1 and IND.macd_dir([-x for x in up]) == -1
    assert IND.macd_dir(up[:34]) is None and IND.macd_dir(up[:35]) == 1
    assert IND.macd_dir([100.0] * 50) is None                       # a flat price: the histogram is exactly 0
    ramp_then_flat = lambda k: [100.0 + i for i in range(40)] + [140.0] * k
    assert IND.macd_dir(ramp_then_flat(2)) is None and IND.macd_dir([-x for x in ramp_then_flat(2)]) is None     # above 0 and falling: no signal
    assert IND.macd_dir(ramp_then_flat(8)) == -1 and IND.macd_dir([-x for x in ramp_then_flat(8)]) == 1          # it crossed 0 and keeps falling
    # the histogram by a plain loop: ema lists (the last two values)
    def ema(xs, n):
        out = [xs[0]]
        for x in xs[1:]:
            out.append(out[-1] + (x - out[-1]) * 2 / (n + 1))
        return out
    c = [100.0 + math.sin(i / 5.0) * 7 + i * 0.02 for i in range(80)]
    line = [a - b for a, b in zip(ema(c, 12), ema(c, 26))]
    hist = [m - s for m, s in zip(line, ema(line, 9))]
    want = 1 if hist[-1] > 0 and hist[-1] >= hist[-2] else -1 if hist[-1] < 0 and hist[-1] <= hist[-2] else None
    assert IND.macd_dir(c) == want


def fake_rsi(table):
    return lambda i: table.get(i)


def test_rsidiv_compares_the_last_bar_with_the_lowest_low_of_the_bars_minus_20_to_minus_3():
    L, H = [100.0] * 20, [105.0] * 20
    L[5], L[19] = 99.0, 98.5                                         # a new low at the last bar, the earlier low at bar 5
    assert IND.rsidiv(H, L, fake_rsi({19: 40.0, 5: 30.0})) == 1
    assert IND.rsidiv(H, L, fake_rsi({19: 30.0, 5: 30.0})) is None  # equal RSI: no divergence
    assert IND.rsidiv(H, L, fake_rsi({19: 25.0, 5: 30.0})) is None  # a lower RSI at the new low: no divergence
    assert IND.rsidiv(H, L, fake_rsi({19: 40.0})) is None            # no RSI at the earlier low
    L[19] = 99.0
    assert IND.rsidiv(H, L, fake_rsi({19: 40.0, 5: 30.0})) is None  # the last low EQUALS the earlier low: not below it
    L[19] = 98.5
    L[9] = 99.0                                                      # the lowest low is held twice: the LAST bar holding it counts
    assert IND.rsidiv(H, L, fake_rsi({19: 40.0, 9: 35.0, 5: 45.0})) == 1
    L[9] = 100.0
    L[17] = 90.0                                                     # bar 17 is one of the last 3: not a reference
    assert IND.rsidiv(H, L, fake_rsi({19: 40.0, 5: 30.0})) == 1
    assert IND.rsidiv(H, L[1:], fake_rsi({18: 40.0, 4: 30.0})) is None      # 19 bars
    # the mirror on the highs
    L2, H2 = [100.0] * 20, [105.0] * 20
    H2[5], H2[19] = 106.0, 106.5
    assert IND.rsidiv(H2, L2, fake_rsi({19: 60.0, 5: 70.0})) == -1
    assert IND.rsidiv(H2, L2, fake_rsi({19: 70.0, 5: 70.0})) is None
    assert IND.rsidiv(H2, L2, fake_rsi({19: 80.0, 5: 70.0})) is None
    L2[7], L2[19] = 99.0, 98.5                                       # a new low AND a new high at once, both with a divergent RSI
    assert IND.rsidiv(H2, L2, fake_rsi({19: 50.0, 7: 40.0, 5: 60.0})) is None


def test_mfi_is_the_share_of_positive_money_flow_and_exactly_50_when_the_flows_balance():
    price = [100.0 + i for i in range(15)]
    assert IND.mfi_last(price, price, price, [10.0] * 15) == 100.0
    assert IND.mfi_last(price[::-1], price[::-1], price[::-1], [10.0] * 15) == 0.0
    assert IND.mfi_last([100.0] * 15, [100.0] * 15, [100.0] * 15, [10.0] * 15) is None          # no change in the typical price: no flow
    assert IND.mfi_last(price[:14], price[:14], price[:14], [10.0] * 14) is None                # 14 bars
    p = [100.0 if i % 2 == 0 else 101.0 for i in range(15)]                                      # 7 up steps to 101, 7 down steps to 100
    v = [0.0] + [100.0 if i % 2 else 101.0 for i in range(1, 15)]                                # flow up = 101 x 100, flow down = 100 x 101
    assert IND.mfi_last(p, p, p, v) == 50.0
    assert IND.mfi_last([x + 3 for x in p], [x - 3 for x in p], p, v) == 50.0                    # the typical price is (h + l + c) / 3
    v2 = list(v)
    v2[1] = 101.0                                                                                # one up flow a little larger
    assert IND.mfi_last(p, p, p, v2) > 50.0


def test_delta_div_is_price_against_the_net_delta():
    assert IND.delta_div(-1.0, 5) == 1 and IND.delta_div(1.0, -5) == -1
    assert IND.delta_div(1.0, 5) is None and IND.delta_div(-1.0, -5) is None
    assert IND.delta_div(0.0, 5) is None and IND.delta_div(0.0, -5) is None and IND.delta_div(-1.0, 0) is None and IND.delta_div(1.0, 0) is None


def bar(o, h, l, c):
    return [o], [h], [l], [c]


def test_candle_displace_at_its_thresholds():
    atr = 2.0                                                        # body >= 3
    assert IND.candle("displace", 1, *bar(100.0, 103.0, 100.0, 103.0), atr) and not IND.candle("displace", -1, *bar(100.0, 103.0, 100.0, 103.0), atr)
    assert not IND.candle("displace", 1, *bar(100.25, 103.0, 100.0, 103.0), atr)                   # body 2.75
    assert IND.candle("displace", -1, *bar(103.0, 103.0, 100.0, 100.0), atr) and not IND.candle("displace", 1, *bar(103.0, 103.0, 100.0, 100.0), atr)
    assert IND.candle("displace", 1, *bar(99.25, 104.0, 99.0, 102.75), atr)                        # the close exactly at 75 % of the range 99 .. 104
    assert not IND.candle("displace", 1, *bar(99.25, 104.0, 99.0, 102.5), atr)                     # a little below it
    assert IND.candle("displace", -1, *bar(103.75, 104.0, 99.0, 100.25), atr)                      # exactly at 25 %
    assert not IND.candle("displace", -1, *bar(103.75, 104.0, 99.0, 100.5), atr)
    assert not IND.candle("displace", 1, *bar(100.0, 103.0, 100.0, 103.0), None) and not IND.candle("displace", 1, *bar(100.0, 100.0, 100.0, 100.0), 0.0)


def test_candle_engulf_needs_a_covering_body_of_the_other_colour_the_trades_way():
    def eng(sd, po, pc, o, c):
        O, H, L, C = [po, o], [max(po, pc) + 1, max(o, c) + 1], [min(po, pc) - 1, min(o, c) - 1], [pc, c]
        return IND.candle("engulf", sd, O, H, L, C, 1.0)
    assert eng(1, 102.0, 100.0, 99.5, 102.5) and not eng(-1, 102.0, 100.0, 99.5, 102.5)           # bullish engulfs bearish
    assert eng(1, 102.0, 100.0, 100.0, 102.0)                                                      # the same body edges: covers
    assert not eng(1, 102.0, 100.0, 100.25, 102.5) and not eng(1, 102.0, 100.0, 99.5, 101.75)      # one edge short
    assert not eng(1, 100.0, 102.0, 99.5, 102.5)                                                   # the same colour
    assert not eng(1, 101.0, 101.0, 99.5, 102.5)                                                   # a doji before it has no colour
    assert eng(-1, 100.0, 102.0, 102.5, 99.5) and not eng(1, 100.0, 102.0, 102.5, 99.5)           # the mirror
    assert not IND.candle("engulf", 1, [100.0], [103.0], [99.0], [102.0], 1.0)                      # one bar only


def test_candle_reject_is_a_wick_of_twice_the_body_on_the_trades_side():
    assert IND.candle("reject", 1, *bar(100.0, 101.0, 98.0, 101.0), 9.0)                           # body 1, lower wick 2
    assert not IND.candle("reject", 1, *bar(100.0, 101.0, 98.25, 101.0), 9.0)                      # wick 1.75
    assert IND.candle("reject", 1, *bar(101.0, 101.0, 98.0, 100.0), 9.0)                           # a down bar: the wick runs below the close
    assert IND.candle("reject", -1, *bar(101.0, 103.0, 100.0, 100.0), 9.0) and not IND.candle("reject", 1, *bar(101.0, 103.0, 100.0, 100.0), 9.0)
    assert IND.candle("reject", -1, *bar(100.0, 103.0, 100.0, 101.0), 9.0)
    assert not IND.candle("reject", 1, *bar(100.0, 100.0, 95.0, 100.0), 9.0)                       # body 0: no signal even with a long wick
    assert IND.candle("reject", 1, *bar(100.0, 101.0, 98.0, 101.0), None)                          # no ATR needed


# ---- (i) the glue at each threshold -------------------------------------------------------------------------------------------------

def glue(monkeypatch, where, name, value, block, mode):
    """(a long, a short) allowed when the indicator `name` of `where` returns `value` at every decision."""
    monkeypatch.setattr(where, name, lambda *a, **k: value)
    out = []
    for go, _ in SIDES:
        got = set(probe({"go": go, f"f_{block}": mode}, FLAT).values())
        assert len(got) == 1, (block, mode, value)
        out.append(got.pop())
    return tuple(out)


@pytest.mark.parametrize("block,mode,table", [
    ("bbw", "tight", [(0.2, True), (0.2000001, False), (0.8, False), (0.5, False), (None, False)]),
    ("bbw", "wide", [(0.8, True), (0.7999999, False), (0.2, False), (0.5, False), (None, False)]),
    ("atrp", "high", [(0.7, True), (0.6999999, False), (0.3, False), (None, False)]),
    ("atrp", "low", [(0.3, True), (0.3000001, False), (0.7, False), (None, False)]),
    ("er", "trend", [(0.5, True), (0.4999999, False), (0.25, False), (None, False)]),
    ("er", "chop", [(0.25, True), (0.2500001, False), (0.5, False), (None, False)])])
def test_the_direction_free_blocks_cut_at_their_thresholds_and_block_both_sides_without_a_signal(monkeypatch, block, mode, table):
    fn = {"bbw": "bbw_rank", "atrp": "atr_rank", "er": "efficiency"}[block]
    for value, ok in table:
        assert glue(monkeypatch, IND, fn, value, block, mode) == (ok, ok), (block, mode, value)


@pytest.mark.parametrize("block", ["macd", "rsidiv", "deltadiv"])
def test_the_direction_blocks_pair_a_bullish_signal_with_longs_and_a_bearish_one_with_shorts(monkeypatch, block):
    where, name = (IND, {"macd": "macd_dir", "rsidiv": "rsidiv"}[block]) if block != "deltadiv" else (B.Blocks, "blk_deltadiv")
    for value, mode, want in ((1, "with", (True, False)), (-1, "with", (False, True)), (1, "against", (False, True)), (-1, "against", (True, False)),
                              (None, "with", (False, False)), (None, "against", (False, False))):
        assert glue(monkeypatch, where, name, value, block, mode) == want, (block, value, mode)


def test_mfi_sides_and_the_extreme_cut_at_20_and_80(monkeypatch):
    for value, mode, want in ((50.0001, "with", (True, False)), (49.9999, "with", (False, True)), (50.0, "with", (False, False)),
                              (50.0001, "against", (False, True)), (49.9999, "against", (True, False)), (50.0, "against", (False, False)),
                              (20.0, "extreme_against", (True, False)), (20.0001, "extreme_against", (False, False)),
                              (80.0, "extreme_against", (False, True)), (79.9999, "extreme_against", (False, False)),
                              (50.0, "extreme_against", (False, False)), (None, "with", (False, False)), (None, "extreme_against", (False, False))):
        assert glue(monkeypatch, IND, "mfi_last", value, "mfi", mode) == want, (value, mode)


def test_the_candle_block_hands_the_bars_the_side_and_the_atr_to_the_shape(monkeypatch):
    seen = []

    def spy(kind, sd, O, H, L, C, atr):
        seen.append((kind, sd, len(C), atr is not None and atr > 0))
        return sd > 0
    monkeypatch.setattr(IND, "candle", spy)
    assert [set(probe({"go": go, "f_candle": "reject"}, FLAT).values()) for go, _ in SIDES] == [{True}, {False}]
    assert {(k, sd) for k, sd, _, _ in seen} == {("reject", 1), ("reject", -1)} and all(has for *_, has in seen)


# ---- (ii) each block against an independent loop on random bars ----------------------------------------------------------------------------

def closes(b):
    return [x[3] for x in b]


def ref_bbw_rank(b):
    c = closes(b)
    if len(c) < 140:
        return None
    bw = []
    for i in range(len(c) - 121, len(c)):
        w = c[i - 19:i + 1]
        m = sum(w) / 20
        s = math.sqrt(sum((x - m) ** 2 for x in w) / 20)
        bw.append(4 * s / m)
    ref = bw[:-1]
    return (sum(r < bw[-1] for r in ref) + 0.5 * sum(r == bw[-1] for r in ref)) / 120


def ref_atr(b):
    """Wilder's ATR(14) after every bar from the 14th, bar 0's true range = its range."""
    tr = [b[0][1] - b[0][2]] + [max(x[1] - x[2], abs(x[1] - p[3]), abs(x[2] - p[3])) for p, x in zip(b, b[1:])]
    out, a = [], None
    for i, t in enumerate(tr):
        if i == 13:
            a = sum(tr[:14]) / 14
        elif i > 13:
            a = (a * 13 + t) / 14
        if a is not None:
            out.append(a)
    return out


def ref_atr_rank(b):
    a = ref_atr(b)
    if len(a) < 101:
        return None
    ref = a[-101:-1]
    return (sum(r < a[-1] for r in ref) + 0.5 * sum(r == a[-1] for r in ref)) / 100


def ref_er(b):
    c = closes(b)[-15:]
    if len(c) < 15:
        return None
    path = sum(abs(c[i + 1] - c[i]) for i in range(14))
    return None if path == 0 else abs(c[-1] - c[0]) / path


def ref_macd(b):
    c = closes(b)
    if len(c) < 35:
        return None
    e12, e26, sig, hist = c[0], c[0], 0.0, []
    for i, x in enumerate(c):
        if i:
            e12, e26 = e12 + (x - e12) * 2 / 13, e26 + (x - e26) * 2 / 27
        m = e12 - e26
        sig = m if i == 0 else sig + (m - sig) * 2 / 10
        hist.append(m - sig)
    h, p = hist[-1], hist[-2]
    return 1 if h > 0 and h >= p else -1 if h < 0 and h <= p else None


def ref_rsidiv(b):
    c = closes(b)
    if len(b) < 20:
        return None
    win = b[-20:-3]
    lo, hi = min(x[2] for x in win), max(x[1] for x in win)
    jl = max(i for i, x in enumerate(win) if x[2] == lo) + len(b) - 20
    jh = max(i for i, x in enumerate(win) if x[1] == hi) + len(b) - 20
    r0 = rsi_ref(c)
    bull = b[-1][2] < lo and rsi_ref(c[:jl + 1]) is not None and r0 > rsi_ref(c[:jl + 1])
    bear = b[-1][1] > hi and rsi_ref(c[:jh + 1]) is not None and r0 < rsi_ref(c[:jh + 1])
    return None if bull == bear else 1 if bull else -1


def ref_mfi(b):
    if len(b) < 15:
        return None
    pos = neg = 0.0
    for p, x in zip(b[-15:], b[-14:]):
        tp0, tp1 = (p[1] + p[2] + p[3]) / 3, (x[1] + x[2] + x[3]) / 3
        pos += tp1 * x[4] * (tp1 > tp0)
        neg += tp1 * x[4] * (tp1 < tp0)
    return None if pos + neg == 0 else 100 * pos / (pos + neg)


def ref_candle(b, mode, sd):
    o, h, l, c, _ = b[-1]
    body = abs(c - o)
    if mode == "displace":
        atr = ref_atr(b)[-1]
        top = (c - l) / (h - l)                                      # where the close sits in the range, 0 .. 1
        return body >= 1.5 * atr and (top >= 0.75 if sd > 0 else top <= 0.25)
    if mode == "engulf":
        po, pc = b[-2][0], b[-2][3]
        up, pup = c > o, pc > po
        return (c != o and pc != po and up != pup and (up == (sd > 0))
                and max(o, c) >= max(po, pc) and min(o, c) <= min(po, pc))
    wick = (min(o, c) - l) if sd > 0 else (h - max(o, c))
    return body > 0 and wick >= 2 * body


VERDICT = {
    "bbw": lambda b, m, sd: (lambda r: r is not None and (r <= 0.2 if m == "tight" else r >= 0.8))(ref_bbw_rank(b)),
    "atrp": lambda b, m, sd: (lambda r: r is not None and (r >= 0.7 if m == "high" else r <= 0.3))(ref_atr_rank(b)),
    "er": lambda b, m, sd: (lambda r: r is not None and (r >= 0.5 if m == "trend" else r <= 0.25))(ref_er(b)),
    "macd": lambda b, m, sd: (lambda d: d is not None and ((d == sd) == (m == "with")))(ref_macd(b)),
    "rsidiv": lambda b, m, sd: (lambda d: d is not None and ((d == sd) == (m == "with")))(ref_rsidiv(b)),
    "mfi": lambda b, m, sd: (lambda x: x is not None and (((x - 50) * sd > 0) if m == "with" else ((x - 50) * sd < 0) if m == "against"
                                                          else (x - 50) * sd <= -30))(ref_mfi(b)),
    "candle": lambda b, m, sd: len(b) >= 15 and ref_candle(b, m, sd)}


@pytest.mark.parametrize("block", ["bbw", "atrp", "er", "macd", "rsidiv", "mfi", "candle"])
def test_each_block_matches_an_independent_loop_at_every_decision(block):
    outcomes = set()
    for go, sd in SIDES:
        for mode in NEW[block]:
            got = put({"go": go, f"f_{block}": mode}, {})
            assert len(got) > 120
            for s, ok in got.items():
                b = bars_until(BARS, s)
                assert ok is bool(VERDICT[block](b, mode, sd)), (block, mode, go, s)
                outcomes.add((go, mode, ok))
    assert outcomes == {(go, m, ok) for go, _ in SIDES for m in NEW[block] for ok in (True, False)}, block      # every side met both outcomes


def flow_table(monkeypatch, delta, vol=100):
    tab = {D.isoformat(): prefix(vol=vol, delta=delta)}
    monkeypatch.setattr(FT, "_table", lambda r: tab)
    return tab


def test_deltadiv_is_the_close_over_20_bars_against_the_net_delta_of_the_same_minutes(monkeypatch):
    g = np.random.default_rng(4)
    delta = g.integers(-30, 31, B.NMIN)
    flow_table(monkeypatch, delta)
    outcomes = set()
    for go, sd in SIDES:
        for mode in NEW["deltadiv"]:
            got = put({"go": go, "f_deltadiv": mode}, {})
            assert len(got) > 120
            for s, ok in got.items():
                b = bars_until(BARS, s)
                net = int(delta[minute_index(s - 1200):minute_index(s)].sum())       # the 20 minutes before the decision
                move = b[-1][3] - b[-21][3]
                d = 1 if move < 0 < net else -1 if move > 0 > net else None
                assert ok is (d is not None and ((d == sd) == (mode == "with"))), (mode, go, s, move, net)
                outcomes.add((go, mode, ok))
    assert outcomes == {(go, m, ok) for go, _ in SIDES for m in NEW["deltadiv"] for ok in (True, False)}


def test_deltadiv_has_no_signal_without_flow_rows_a_window_without_volume_or_20_bars(monkeypatch):
    delta = np.full(B.NMIN, 25, np.int64)
    for tab in ({}, {"2023-03-13": prefix(vol=100, delta=delta)}):                   # no row for today (another date does not count)
        monkeypatch.setattr(FT, "_table", lambda r, tab=tab: tab)
        assert not any(v for go, _ in SIDES for m in ("with", "against") for v in put({"go": go, "f_deltadiv": m}, {}).values())
    flow_table(monkeypatch, delta, vol=0)                                            # a window with no volume
    assert not any(v for go, _ in SIDES for m in ("with", "against") for v in put({"go": go, "f_deltadiv": m}, {}).values())
    flow_table(monkeypatch, delta)
    assert any(any(put({"go": go, "f_deltadiv": m}, {}).values()) for go, _ in SIDES for m in ("with", "against"))     # (the same table with volume: signals)


# ---- (iii) no look-ahead ----------------------------------------------------------------------------------------------------------------

LOOK = [{"f_bbw": "tight"}, {"f_bbw": "wide"}, {"f_atrp": "high"}, {"f_atrp": "low"}, {"f_er": "trend"}, {"f_er": "chop"}, {"f_macd": "with"},
        {"f_macd": "against"}, {"f_rsidiv": "with"}, {"f_rsidiv": "against"}, {"f_mfi": "with"}, {"f_mfi": "extreme_against"}, {"f_candle": "displace"},
        {"f_candle": "engulf"}, {"f_candle": "reject"}, {"f_deltadiv": "with"}, {"f_deltadiv": "against"}]


def test_prints_and_flow_rows_from_a_decision_on_change_nothing_decided_before(monkeypatch):
    delta = np.random.default_rng(9).integers(-30, 31, B.NMIN)
    tab = flow_table(monkeypatch, delta)
    clean_row = tab[D.isoformat()].copy()
    for extra in LOOK:
        for go, _ in SIDES:
            tab[D.isoformat()] = clean_row
            clean = put({"go": go, **extra}, {})
            for cut in (ns("11:47"), ns("12:20:30"), ns("12:51")):
                c = (cut - ns("00:00")) // S.NS
                row = clean_row.copy()
                k = minute_index(c)
                row[:, k + 1:] += 10 ** 6 * np.arange(1, B.NMIN + 1 - k)               # every flow minute from the cut on rewritten
                tab[D.isoformat()] = row
                dirty = probe({**MID, "go": go, **extra}, garble(TAPE, cut))
                assert {s: v for s, v in dirty.items() if s <= c} == {s: v for s, v in clean.items() if s <= c}, (extra, go, cut)
    for extra in LOOK:                                                               # (the clean run meets both outcomes, so the test can fail)
        tab[D.isoformat()] = clean_row
        assert len({v for go, _ in SIDES for v in put({"go": go, **extra}, {}).values()}) == 2, extra


# ---- (iv) the registry ----------------------------------------------------------------------------------------------------------------------

def test_the_registry_the_plain_words_the_defaults_and_the_flow_cap():
    for blk, modes in NEW.items():
        assert tuple(B.FILTERS[blk]) == modes and B.Blocks.DEFAULTS[f"f_{blk}"] == "off"
        assert B.Blocks.SCHEMA[f"f_{blk}"] == ("choice", ("off", *modes))
        for m in modes:
            assert B.PLAIN[(blk, m)].startswith("only when") and B.filter_inputs(blk, m, "GC") == {f"f_{blk}": m}
        assert blk not in B.BLOCK_MARKETS and blk not in B.L2_BLOCKS            # NQ, ES and GC
    assert sum(len(s) for s in B.FILTERS.values()) == 99 and set(B.FLOW_BLOCKS) == {"delta", "cumdelta", "sweep", "bigorder", "deltadiv"}
    assert B.DIR_BLOCKS == ("macd", "rsidiv", "deltadiv")
    assert "deltadiv" not in B.FLOW_SERIES                                       # it has no series of its own: the delta of the flow table, summed
    assert all((b, s) in B.PLAIN for b, sides in B.FILTERS.items() for s in sides)


# ---- (v) real days: the same trades at 1 and 8 workers --------------------------------------------------------------------------------------

@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_identical_trades_at_1_and_8_workers_with_the_batch_4_blocks(root):
    real_days()
    FT._table.cache_clear()
    days = days_of(root)
    hd = {"tf": "5", "hold_to": "day", "stop_mode": "atr", "stop_val": 2.0, "tgt_r": 2.0, "n": 10}
    specs = [(B.WRAPPED["donchian"], {**hd, "sess": sess, f"f_{blk}": mode}) for sess in ("nyam", "pm") for blk, modes in NEW.items() for mode in modes]
    a = S.run_many(specs, days=days, root=root, workers=1)
    b = S.run_many(specs, days=days, root=root, workers=W)
    seen = {}
    for (cls, p), x, y in zip(specs, a, b):
        assert x["skipped_by_error"] == 0 and y["skipped_by_error"] == 0, (p, x["no_trade"][:2])
        assert x["trades"] == y["trades"], p
        k = next(k for k in p if k.startswith("f_"))
        seen[k] = seen.get(k, 0) + len(x["trades"])
    assert all(v > 0 for v in seen.values()) and len(seen) == len(NEW), seen          # every block let some trades through
    assert RM.hold_checks(a, root) == {"exit_after_day_flat": 0, "overlap_in_session": 0, "entry_in_no_session": 0}
