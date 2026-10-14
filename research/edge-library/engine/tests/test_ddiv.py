"""DDIV: the `ddiv` entry trigger (families/ddiv.py), the chart's delta-divergence study traded at the close that confirms it.

THE RULE UNDER TEST (homebase/charts/studies_flow.py DeltaDiv, restated in the module text):
    swing high = a tf bar whose high is strictly above the highs of the n bars before and the n bars after it; KNOWN at the n-th bar's close
    cumulative delta = the aggressors' net buying volume of the whole minutes since 18:00 ET of the evening before, to that bar's close
    SHORT  = a swing high above the previous swing high with a LOWER cumulative delta;  LONG = the mirror at the lows
    every swing replaces the previous one of its kind;  both at one close = no trade;  entries only inside the idea's session.
Seeded random-walk days with a random delta per minute are checked against an independent restatement at several n and bar sizes; exact
synthetic cases pin the strict inequalities, the confirming close and the swing memory. No net, win rate or profit factor is read.
"""
import numpy as np
import pytest

import families
import flowtab as FT
import l2sim as S
from families import blocks as B
from families import ddiv as DD
from test_blocks import D, DAILY, TICK, minute_tape, ns, rand_bars
from test_blocks_flow import minute_index, prefix

BASE = {"hold_to": "day", "tf": "5", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "max_tr": 20, "n": 3}
PX = 15000.0
NY_START, NY_END = 34200, 39600                      # 09:30 - 11:00 ET, seconds after 00:00 ET


def flow_table(monkeypatch, delta, vol=100):
    tab = {D.isoformat(): prefix(vol=vol, delta=delta)}
    monkeypatch.setattr(FT, "_table", lambda r: tab)
    return tab


class Sig(DD.Ddiv):
    """Logs every signal the family sees (no order is placed, so every qualifying close shows): (second, side)."""
    seen: list = []

    def fam_signal(self, ctx):
        if self.go:
            type(self).seen.append(((ctx.now_ns - ns("00:00")) // S.NS, "long" if self.go > 0 else "short"))


def signals(params, bars):
    cls = type("Sig", (Sig,), {"seen": []})
    st = cls({**BASE, **params})
    st.ROLLS = frozenset()
    S.run_session(st, minute_tape(bars, "00:00"), daily=list(DAILY), on_error="raise")
    return list(cls.seen)


def restate(bars, delta, tf, n):
    """The rule, written again from the text: [(close second, side)] of every confirming close of a day of minute bars from 00:00 ET."""
    step = tf * 60
    buckets = {}
    for i, (o, h, l, c, v) in enumerate(bars):
        b = buckets.setdefault(i * 60 // step, [h, l])
        b[0], b[1] = max(b[0], h), min(b[1], l)
    keys = sorted(buckets)
    H = [buckets[k][0] for k in keys]
    L = [buckets[k][1] for k in keys]
    closes = [(k + 1) * step for k in keys]
    cum = [int(delta[0:minute_index(c)].sum()) for c in closes]       # minute 0 of the table is 18:00 ET of the evening before
    ph = pl = None
    out = []
    for j in range(n, len(H) - n):
        hi = H[j] > max(H[j - n:j]) and H[j] > max(H[j + 1:j + n + 1])
        lo = L[j] < min(L[j - n:j]) and L[j] < min(L[j + 1:j + n + 1])
        bear = hi and ph is not None and H[j] > ph[0] and cum[j] < ph[1]
        bull = lo and pl is not None and L[j] < pl[0] and cum[j] > pl[1]
        if hi:
            ph = (H[j], cum[j])
        if lo:
            pl = (L[j], cum[j])
        if bear != bull:
            out.append((closes[j + n], "short" if bear else "long"))
    return out


def inside(sig):
    return [x for x in sig if NY_START < x[0] <= NY_END]


@pytest.mark.parametrize("seed,n,tf", [(1, 3, 5), (3, 2, 5), (4, 3, 1), (6, 5, 1), (7, 4, 1), (8, 6, 1)])
def test_signals_are_the_rule_restated_on_random_days(monkeypatch, seed, n, tf):
    g = np.random.default_rng(100 + seed)
    delta = g.integers(-40, 41, B.NMIN)
    flow_table(monkeypatch, delta)
    bars = rand_bars(960, seed, step=7.0)
    got = signals({"n": n, "tf": str(tf)}, bars)
    want = inside(restate(bars, delta, tf, n))
    assert len(want) > 0, "the seeded day has no signal inside the session: the test would prove nothing"
    interior = [x for x in want if x[0] < NY_END - 300]                 # never in the last 5 minutes of the session
    assert set(interior) <= set(got) <= set(want)


def test_a_signal_is_made_at_the_confirming_close_not_at_the_swing(monkeypatch):
    """A swing high at 09:44 (the bar 09:40-09:45): with n = 3 it is known at the close of the 3rd bar after it, 10:00 -- never earlier. The
    earlier swing high (09:12, 15010) is a swing too: the 15020 comes more than 3 bars after it."""
    delta = np.zeros(B.NMIN, np.int64)
    # a quiet day with a swing high (15010 at 09:12) on a high delta, then a higher swing high at 09:44 (15020) on a LOWER delta
    bars = [(PX, PX + TICK, PX - TICK, PX, 40)] * 960
    bars[9 * 60 + 12] = (PX, 15010.0, PX - TICK, PX, 40)
    bars[9 * 60 + 44] = (PX, 15020.0, PX - TICK, PX, 40)
    delta[minute_index(9 * 3600 + 12 * 60)] = 500                        # cumulative delta rises to 500 by the first swing ...
    delta[minute_index(9 * 3600 + 44 * 60)] = -300                       # ... and is 200 at the second: higher price, lower delta
    flow_table_ = {D.isoformat(): prefix(vol=100, delta=delta)}
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(FT, "_table", lambda r: flow_table_)
        got = signals({"n": 3}, bars)
    finally:
        mp.undo()
    assert got == [(10 * 3600, "short")]                                 # 09:40-09:45 bar + 3 bars = the close at 10:00


def test_equal_highs_or_equal_delta_is_no_signal(monkeypatch):
    """Both swings are real swings (09:12 and 09:44, more than n bars apart); only the strict comparison is under test."""
    bars = [(PX, PX + TICK, PX - TICK, PX, 40)] * 960
    bars[9 * 60 + 12] = (PX, 15010.0, PX - TICK, PX, 40)
    delta = np.zeros(B.NMIN, np.int64)
    delta[minute_index(9 * 3600 + 12 * 60)] = 500
    delta[minute_index(9 * 3600 + 44 * 60)] = -300                       # the second swing's cumulative delta is LOWER
    flow_table(monkeypatch, delta)
    bars[9 * 60 + 44] = (PX, 15010.0, PX - TICK, PX, 40)                 # an equal high is not higher
    assert signals({"n": 3}, bars) == []
    bars[9 * 60 + 44] = (PX, 15020.0, PX - TICK, PX, 40)                 # a higher high on a lower delta: the signal
    assert signals({"n": 3}, bars) == [(10 * 3600, "short")]
    delta[minute_index(9 * 3600 + 44 * 60)] = 0                          # a higher high on an EQUAL cumulative delta is not lower
    flow_table(monkeypatch, delta)
    assert signals({"n": 3}, bars) == []


def test_the_mirror_is_a_long_at_a_lower_low_on_a_higher_delta(monkeypatch):
    bars = [(PX, PX + TICK, PX - TICK, PX, 40)] * 960
    bars[9 * 60 + 12] = (PX, PX + TICK, 14990.0, PX, 40)
    bars[9 * 60 + 44] = (PX, PX + TICK, 14980.0, PX, 40)
    delta = np.zeros(B.NMIN, np.int64)
    delta[minute_index(9 * 3600 + 12 * 60)] = -500
    delta[minute_index(9 * 3600 + 44 * 60)] = 300                        # a lower low and a HIGHER cumulative delta (-200 > -500)
    flow_table(monkeypatch, delta)
    assert signals({"n": 3}, bars) == [(10 * 3600, "long")]


def test_no_flow_row_for_the_day_means_no_signal(monkeypatch):
    monkeypatch.setattr(FT, "_table", lambda r: {})
    bars = rand_bars(960, 9, step=7.0)
    assert signals({"n": 3}, bars) == []


def test_the_family_is_registered_and_bar_based():
    assert "ddiv" in families.REGISTRY
    assert "ddiv" in B.BASES and "ddiv" in B.WRAPPED
