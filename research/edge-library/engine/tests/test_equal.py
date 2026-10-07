"""EQUAL HIGHS / LOWS: engine/levels.py `eq` -- the owner's rule (2026-10-06): two consecutive swings (50 five-minute bars each side) within 10 points,
the SECOND not beyond the FIRST (a second high above the first high, a second low below the first low, makes it one swing, not an equal), nothing
in between beyond the first either; the level is the first swing's price, known once the second swing is confirmed, live until a bar trades beyond.
NQ only (the tolerance is in NQ points).

(i) the pair rule against a brute-force loop and by hand (tolerance edge, equal prices, the second beyond, a sweep in between, the chain);
(ii) which pairs are still live; (iii) the level on synthetic sessions with an exact answer, next to `sw`; (iv) NO LOOK-AHEAD; (v) the `liq` trigger.
No net, win rate or profit factor is read.
"""
import math

import numpy as np
import pytest

import l2sim as S
import levels as LV
from test_blocks import minute_tape
from test_liq import PREV, D, daily, flatg, go, run_liq, tape_of
from test_swing import Sw, history, quiet_day, stub, sw_at


# ---- (i) the pair rule ---------------------------------------------------------------------------------------------------------------------

def loop_pairs(h, l, n, tol):
    """The rule written as plain loops (no shared code): consecutive swings, second not beyond the first, within tol, nothing between beyond the first."""
    hi = [i for i in range(n, len(h) - n) if all(h[i] > h[j] for j in range(i - n, i)) and all(h[i] > h[j] for j in range(i + 1, i + n + 1))]
    lo = [i for i in range(n, len(l) - n) if all(l[i] < l[j] for j in range(i - n, i)) and all(l[i] < l[j] for j in range(i + 1, i + n + 1))]
    out = {"hi": [], "lo": []}
    for a, b in zip(hi[:-1], hi[1:]):
        if h[b] <= h[a] and h[a] - h[b] <= tol and all(h[j] <= h[a] for j in range(a + 1, b + 1)):
            out["hi"].append((a, b, float(h[a])))
    for a, b in zip(lo[:-1], lo[1:]):
        if l[b] >= l[a] and l[b] - l[a] <= tol and all(l[j] >= l[a] for j in range(a + 1, b + 1)):
            out["lo"].append((a, b, float(l[a])))
    return out


@pytest.mark.parametrize("n,tol", [(2, 1.0), (4, 3.0), (10, 5.0), (50, 10.0)])
def test_equal_pairs_match_a_loop_on_random_series(n, tol):
    rng = np.random.default_rng(n)
    got = 0
    for _ in range(40):
        c = np.cumsum(rng.integers(-3, 4, 700)).astype(float) * (tol / 3)
        h, l = c + rng.integers(0, 3, 700) * tol / 4, c - rng.integers(0, 3, 700) * tol / 4
        want = loop_pairs(h.tolist(), l.tolist(), n, tol)
        assert LV.equal_pairs(h, l, n, tol) == want
        got += len(want["hi"]) + len(want["lo"])
    assert got > 0


def two_highs(h1, h2, between=None, n=3, gap=8):
    """A series with a swing high h1, then h2 `gap` bars later (n = 3 bars each side, flat 100 elsewhere), optionally an extra bar `between` above 100."""
    h = np.full(30, 100.0)
    h[8], h[8 + gap] = h1, h2
    if between is not None:
        h[8 + gap // 2] = between
    return h, h - 5.0


def test_the_second_high_must_not_be_above_the_first_and_the_gap_is_at_most_the_tolerance():
    for h1, h2, ok in ((120, 118, True), (120, 110, True), (120, 120, True), (120, 109.75, False), (120, 121, False), (120, 130, False)):
        h, l = two_highs(h1, h2)
        got = LV.equal_pairs(h, l, 3, 10.0)["hi"]
        assert got == ([(8, 16, float(h1))] if ok else []), (h1, h2, got)       # the level is the FIRST swing's price; the same price counts


def test_a_bar_between_the_swings_that_traded_beyond_the_first_breaks_the_pair():
    h, l = two_highs(120.0, 118.0, gap=14)
    assert LV.equal_pairs(h, l, 3, 10.0)["hi"] == [(8, 22, 120.0)]
    h[15] = h[16] = 121.0                                               # two equal bars in between: no swing of their own, both above the first swing
    assert LV.pivots(h, l, 3)[0].tolist() == [8, 22]
    assert LV.equal_pairs(h, l, 3, 10.0)["hi"] == loop_pairs(h.tolist(), l.tolist(), 3, 10.0)["hi"] == []
    h[15] = h[16] = 120.0                                               # exactly the first swing's price: not beyond it
    assert LV.equal_pairs(h, l, 3, 10.0)["hi"] == [(8, 22, 120.0)]


def test_equal_lows_are_the_mirror_a_second_low_below_the_first_is_not_an_equal():
    def two_lows(l1, l2):
        l = np.full(30, 100.0)
        l[8], l[16] = l1, l2
        return l + 5.0, l
    for l1, l2, ok in ((80, 82, True), (80, 90, True), (80, 90.25, False), (80, 79, False), (80, 70, False)):
        h, l = two_lows(l1, l2)
        got = LV.equal_pairs(h, l, 3, 10.0)["lo"]
        assert (len(got) == 1) == ok, (l1, l2, got)
        if ok:
            assert got[0] == (8, 16, float(l1))


def test_the_chain_continues_from_the_second_swing():
    h = np.full(60, 100.0)
    h[8], h[18], h[28] = 120.0, 125.0, 123.0                           # the second is higher (no pair), the third is within 10 of the second and below it
    l = h - 5.0
    assert LV.equal_pairs(h, l, 3, 10.0)["hi"] == [(18, 28, 125.0)]


# ---- (ii) which pairs are still live ----------------------------------------------------------------------------------------------------

def test_a_pair_stays_live_until_a_bar_trades_beyond_its_level():
    n = 3
    h, l = two_highs(120.0, 118.0)
    h = np.concatenate((h, np.full(10, 100.0)))
    l = h - 5.0
    assert LV.live_equal(h, l, n, 10.0)[0] == 120.0
    h2 = h.copy(); h2[26] = 120.0                                       # an equal price later: not beyond
    assert LV.live_equal(h2, h2 - 5.0, n, 10.0)[0] == 120.0
    h3 = h.copy(); h3[26] = 120.25                                      # a bar above it: swept
    assert LV.live_equal(h3, h3 - 5.0, n, 10.0)[0] is None
    assert LV.live_equal(h[:16 + n], l[:16 + n], n, 10.0)[0] is None    # the second swing is not confirmed until 3 bars after it
    assert LV.live_equal(h[:16 + n + 1], l[:16 + n + 1], n, 10.0)[0] == 120.0


def test_the_latest_live_pair_wins_and_a_swept_one_gives_way_to_an_older_live_one():
    h = np.full(70, 100.0)
    h[8], h[16], h[40], h[48] = 150.0, 146.0, 120.0, 118.0              # an older pair at 150 and a newer one at 120
    l = h - 5.0
    assert LV.live_equal(h, l, 3, 10.0)[0] == 120.0                     # the newest live pair
    h2 = h.copy(); h2[60] = h2[61] = 125.0                              # two equal bars above 120 (no swing of their own): the newer level is swept
    assert LV.live_equal(h2, h2 - 5.0, 3, 10.0)[0] == 150.0             # the older one is still live
    h3 = h2.copy(); h3[66] = h3[67] = 151.0
    assert LV.live_equal(h3, h3 - 5.0, 3, 10.0)[0] is None              # both swept
    h4 = h.copy(); h4[60] = h4[61] = 119.0                              # under both levels: nothing changes
    assert LV.live_equal(h4, h4 - 5.0, 3, 10.0)[0] == 120.0


# ---- (iii) the level on synthetic sessions -----------------------------------------------------------------------------------------------

def eq_at(**kw):
    cls = type("E", (Sw,), {"asked": []})
    cls.fam_signal = lambda self, ctx: type(self).asked.append(((ctx.now_ns - S.et_ns(D, "00:00")) // S.NS, LV.levels(self, "all")))
    go(cls, {"hold_to": "day", "tf": "5", "sess": kw.get("sess", "nyam"), "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "max_tr": 20, "max_tr": 20},
       tape_of(kw.get("bars") or quiet_day()), kw.get("rolls", ()))
    return cls.asked


HIST = dict(peaks=[(150, 15300.0), (300, 15296.0)], troughs=[(250, 14710.0), (420, 14714.0)])


def test_the_level_is_the_latest_live_equal_high_and_equal_low_next_to_the_swing_level(monkeypatch):
    stub(monkeypatch, history(**HIST))
    got = eq_at()
    assert got and {x[1]["eq"] for x in got} == {(15300.0, 14710.0)}            # the FIRST swings' prices
    assert {x[1]["sw"] for x in got} == {(15296.0, 14714.0)}                    # the swing level is the latest swings: both exist side by side
    stub(monkeypatch, history(peaks=[(150, 15300.0), (300, 15305.0)], troughs=[(250, 14710.0), (420, 14705.0)]))
    assert all("eq" not in x[1] for x in eq_at())                                # the second beyond the first, on both sides: no equal


def test_a_side_traded_beyond_today_is_dropped_and_a_sweep_in_between_breaks_the_pair(monkeypatch):
    stub(monkeypatch, history(**HIST))
    over = quiet_day()
    over[100] = over[110] = (15000.0, 15400.0, 15000.0, 15000.0, 40)           # two bars at 15400 (no swing of their own): above the equal high's level
    assert eq_at(bars=over)[0][1]["eq"] == (math.inf, 14710.0)
    h = history(**HIST)
    k = sorted(h)[1]                                                             # the second session holds bars 120..239; local 80 and 90 lie between the two peaks
    end, hh, ll = h[k]
    hh = hh.copy(); hh[80] = hh[90] = 15310.0                                    # two equal bars (no swing of their own) above the first peak, 10 bars apart
    h[k] = (end, hh, ll)
    stub(monkeypatch, h)
    assert eq_at()[0][1]["eq"] == (math.inf, 14710.0)                            # 15300 was swept between the swings: no equal high; the low side stays


def test_only_nq_has_the_level(monkeypatch):
    stub(monkeypatch, history(**HIST))
    t = minute_tape(quiet_day(), "19:58", PREV)
    for root in ("ES", "GC"):
        cls = type("E", (Sw,), {"asked": []})
        cls.fam_signal = lambda self, ctx: type(self).asked.append(LV.levels(self, "eq"))
        st = cls({"hold_to": "day", "tf": "5", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "max_tr": 20})
        st.ROLLS = frozenset()
        S.run_session(st, S.Tape(root, D, "X", t.ts, t.px, t.size), daily=daily(), on_error="raise")
        assert cls.asked and all(x == {} for x in cls.asked), root


# ---- (iv) no look-ahead -----------------------------------------------------------------------------------------------------------------

def test_the_first_decision_does_not_change_when_the_prints_after_it_change(monkeypatch):
    stub(monkeypatch, history(**HIST))
    a = quiet_day()
    first = eq_at(bars=a)[0]
    b = list(a)
    for k in range(812 + 12, len(b)):
        b[k] = (15005.0, 16500.0, 13000.0, 15005.0, 40) if k % 2 else (15005.0, 15010.0, 12000.0, 12500.0, 40)
    got = eq_at(bars=b)
    assert got[0] == first and {x[1]["eq"] for x in got} == {first[1]["eq"]}


def test_a_pair_whose_second_swing_forms_today_is_unknown_until_50_bars_have_closed(monkeypatch):
    stub(monkeypatch, history(peaks=[(150, 15300.0)]))
    bars = quiet_day()
    bars[812 - 5] = (15005.0, 15296.0, 15005.0, 15005.0, 40)                    # 09:25: a second high 4 points under the first, 5 minutes before the decision
    assert all("eq" not in x[1] for x in eq_at(bars=bars))
    bars2 = quiet_day()
    bars2[300] = (15005.0, 15296.0, 15005.0, 15005.0, 40)                       # the same second high, hours earlier (long since confirmed)
    assert eq_at(bars=bars2)[0][1]["eq"][0] == 15300.0


# ---- (v) the trigger ---------------------------------------------------------------------------------------------------------------------

def test_liq_sweeps_the_equal_high_with_the_extreme_as_the_structure(monkeypatch):
    stub(monkeypatch, history(**HIST))
    g = flatg(10) + [(15005.0, 15330.0, 15005.0, 15320.0, 40), (15320.0, 15325.0, 15290.0, 15295.0, 40)] + flatg(30, 15295.0)
    got = run_liq({"mode": "sweep", "levels": "eq"}, quiet_day(g))
    assert [(side, struct) for _, side, struct, ok in got] == [("short", 15330.0)] and got[0][3]
