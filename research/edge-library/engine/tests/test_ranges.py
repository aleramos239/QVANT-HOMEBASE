"""THE THREE RANGES: engine/ranges.py and the blocks pdz_move / pdz_swing / pdz_leg / ote_move / ote_swing / ote_leg (zones.py, families/blocks.py).
The owner's choice of 2026-10-07: the move in progress (a 200-point zigzag), the swing pair (latest untouched 50-bar swing high and low) and the leg
rule (the biggest, fastest leg between 180-bar swings).

(i) the move against hand-made series with exact answers and an independent loop; (ii) the swing pair against a brute-force loop on random walks;
(iii) the leg rule on hand-made swings (pick, broken, extended, too small, too old); (iv) NO LOOK-AHEAD: the last bar is the last bar given, a
swing needs its n bars after; (v) the blocks on synthetic sessions with an exact range, in both directions, a roll that cuts the history, and the
decision unchanged when the prints after it change; (vi) the lists: filters, plain words, defaults, markets, caches. No net, win rate or profit
factor is read.
"""
import datetime as dt

import numpy as np
import pytest

import l2sim as S
import levels as LV
import ranges as RG
import zones as Z
from families import blocks as B
from test_liq import daily, flatg
from test_swing import brute
from test_zones import first


# ---- (i) the move in progress -------------------------------------------------------------------------------------------------------------

def hl(c, w=1.0):
    c = np.asarray(c, float)
    return c + w, c - w


def zig(h, l, thr):
    """An independent version: the running extreme and the last turning point as two lists, the leg decided by the distance from the extreme."""
    top, bot, leg, piv = h[0], l[0], 0, None
    ext = None
    for i in range(1, len(h)):
        if leg == 0:
            top, bot = max(top, h[i]), min(bot, l[i])
            if h[i] - bot >= thr:
                leg, piv, ext = 1, bot, h[i]
            elif top - l[i] >= thr:
                leg, piv, ext = -1, top, l[i]
        elif leg == 1:
            if h[i] > ext:
                ext = h[i]
            elif ext - l[i] >= thr:
                leg, piv, ext = -1, ext, l[i]
        else:
            if l[i] < ext:
                ext = l[i]
            elif h[i] - ext >= thr:
                leg, piv, ext = 1, ext, h[i]
    return None if leg == 0 else (min(piv, ext), max(piv, ext), leg)


def test_the_move_is_the_last_turning_point_to_the_extreme_since_and_needs_a_whole_move():
    up = np.concatenate((np.full(20, 15000.0), np.linspace(15000, 15250, 30)))
    h, l = hl(up)
    assert RG.move(h, l) == (14999.0, 15251.0, 1)                              # up from the first low, to the last high
    h2, l2 = hl(np.concatenate((up, np.linspace(15250, 15060, 20))))            # 190 back: not a 200-point reversal
    assert RG.move(h2, l2) == (14999.0, 15251.0, 1)
    h3, l3 = hl(np.concatenate((up, np.linspace(15250, 15040, 20))))            # 210 + the bar's 2 points back: the leg turns
    assert RG.move(h3, l3) == (15039.0, 15251.0, -1)
    h4, l4 = hl(np.full(50, 15000.0))
    assert RG.move(h4, l4) is None and RG.move([], []) is None                  # nothing moved


def test_the_move_matches_an_independent_loop_on_random_walks():
    rng = np.random.default_rng(11)
    for thr in (30.0, 100.0, 200.0):
        for _ in range(12):
            c = np.cumsum(rng.normal(0, 12, 900))
            h, l = c + rng.random(900) * 4, c - rng.random(900) * 4
            assert RG.move(h, l, thr) == zig(h.tolist(), l.tolist(), thr)


# ---- (ii) the swing pair -----------------------------------------------------------------------------------------------------------------

def test_the_swing_pair_matches_a_loop_on_random_walks_and_needs_both_sides():
    rng = np.random.default_rng(5)
    for n in (3, 8, 20):
        for _ in range(10):
            c = np.cumsum(rng.normal(0, 1, 400))
            h, l = c + rng.random(400), c - rng.random(400)
            bh, bl = brute(h.tolist(), l.tolist(), n)
            hh = [i for i in bh if i >= 399 - 90 and all(h[j] <= h[i] for j in range(i + 1, 400))]
            ll = [i for i in bl if i >= 399 - 90 and all(l[j] >= l[i] for j in range(i + 1, 400))]
            want = None if not hh or not ll else (l[ll[-1]], h[hh[-1]], 1 if ll[-1] < hh[-1] else -1)
            got = RG.swing_pair(h, l, n, 90)
            assert (got is None) == (want is None)
            if got:
                assert got[0] == pytest.approx(want[0]) and got[1] == pytest.approx(want[1]) and got[2] == want[2]


def test_the_swing_pair_direction_is_which_swing_came_first():
    n = 3
    h = np.array([5, 5, 5, 5, 20, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5.0])
    l = h - 1
    l[12] = -30.0
    h[12] = -29.0
    assert RG.swing_pair(h, l, n, 100) == (-30.0, 20.0, -1)                      # the high first: the leg points DOWN
    h2, l2 = h.copy(), l.copy()
    h2[4], l2[4] = 5.0, 4.0
    h2[12], l2[12] = 20.0, 19.0
    l2[4], h2[4] = -30.0, -29.0
    assert RG.swing_pair(h2, l2, n, 100) == (-30.0, 20.0, 1)                     # the low first: UP


# ---- (iii) the leg rule ------------------------------------------------------------------------------------------------------------------

def sw_series(spec, n_bars):
    """Bars flat at 150 (+-1) with a swing at each given (bar, price): the flat bars tie among themselves, so only the given bars are swings."""
    h, l = np.full(n_bars, 151.0), np.full(n_bars, 149.0)
    for i, px in spec:
        h[i], l[i] = px + 1.0, px - 1.0
    return h, l


KW = dict(n=5, within=500, back=500, min_size=100.0)


def test_the_leg_rule_picks_the_biggest_size_times_speed_among_the_legs_that_ended_lately():
    # swings (n = 5): low 0 @20, high 300 @60 (300 points in 40 bars), low 100 @100 (200 down in 40 bars), high 200 @140 (100 up in 40 bars)
    h, l = sw_series([(20, 0.0), (60, 300.0), (100, 100.0), (140, 200.0)], 170)
    assert RG.leg(h, l, **KW) == (-1.0, 301.0, 1)                                 # size squared over the bars: 2250 against 1000 and 250
    assert RG.leg(h, l, **{**KW, "min_size": 400.0}) is None                      # nothing is 400 points
    assert RG.leg(h, l, **{**KW, "min_size": 250.0}) == (-1.0, 301.0, 1)
    h2, l2 = sw_series([(20, 140.0), (60, 300.0), (100, 100.0), (140, 200.0)], 170)    # the first leg is now 160 points: the second one (200 down) wins
    assert RG.leg(h2, l2, **KW) == (99.0, 301.0, -1)


def test_a_broken_leg_is_out_and_a_passed_end_extends_the_leg():
    # low 0 @20, high 300 @60; two bars tie at -50 (no swing of their own) and price is back through the origin: the leg is broken
    h, l = sw_series([(20, 0.0), (60, 300.0)], 120)
    for i in (85, 86):
        h[i], l[i] = -49.0, -51.0
    assert RG.leg(h, l, **KW) is None
    # not broken, but a higher high in the last bars (too recent to be a swing): the leg runs to it
    h2, l2 = sw_series([(20, 0.0), (60, 300.0)], 120)
    h2[117], l2[117] = 321.0, 319.0
    assert RG.leg(h2, l2, **KW) == (-1.0, 321.0, 1)


def test_a_leg_that_ended_too_long_ago_is_out_and_so_is_one_whose_swing_is_not_confirmed():
    h, l = sw_series([(20, 0.0), (60, 300.0)], 400)
    assert RG.leg(h, l, **KW) == (-1.0, 301.0, 1)
    assert RG.leg(h, l, **{**KW, "within": 100}) is None                           # it ended 340 bars ago
    h2, l2 = sw_series([(20, 0.0), (60, 300.0)], 63)                               # only 2 bars after the high: not a swing yet
    assert RG.leg(h2, l2, **KW) is None


def test_two_swing_highs_in_a_row_keep_the_higher_one():
    h, l = sw_series([(20, 0.0), (50, 200.0), (80, 320.0)], 130)
    assert RG.leg(h, l, **KW) == (-1.0, 321.0, 1)


# ---- (iv) no look-ahead ---------------------------------------------------------------------------------------------------------------------

def test_a_swing_or_a_leg_is_known_only_after_its_n_bars_and_later_bars_do_not_change_the_past():
    rng = np.random.default_rng(9)
    c = np.cumsum(rng.normal(0, 8, 700))
    h, l = c + 1.0, c - 1.0
    for k in (400, 500, 600, 699):
        for fn in (RG.move, RG.swing_pair, RG.leg):
            a = fn(h[:k + 1], l[:k + 1])
            h2, l2 = h.copy(), l.copy()
            h2[k + 1:], l2[k + 1:] = h[k + 1:] + 900.0, l[k + 1:] - 900.0
            assert fn(h2[:k + 1], l2[:k + 1]) == a


# ---- (v) the blocks on synthetic sessions ---------------------------------------------------------------------------------------------------

NB = 120
DATES = [r["date"] for r in daily()[-12:]]


def hist12(h, l):
    """The 12 prior sessions of NB 5-minute bars each from two arrays of 12 * NB values."""
    base = S.et_ns(dt.date(2023, 1, 2) - dt.timedelta(days=60), "18:00")
    end = base + (np.arange(12 * NB) + 1) * 300 * S.NS
    return {d: (end[k * NB:(k + 1) * NB], h[k * NB:(k + 1) * NB], l[k * NB:(k + 1) * NB]) for k, d in enumerate(DATES)}


def stub(monkeypatch, hist):
    monkeypatch.setattr(LV, "session_bars", lambda root, iso, tf=LV.SW_TF: hist.get(iso))


def day_at(px, extra=0):
    """19:58 .. 09:30 + 60 minutes flat at px: the first decision's close is px."""
    return flatg(812 + 60 + extra, px)


def rise_history():
    """12 sessions: flat at 15000 for 600 bars, then +300 points in 100 bars, then flat at 15300 (an UP move of 300 points; no swing, no leg of
    its own: every bar of a flat stretch ties). A move of the 200-point zigzag turns once price is 200 points off its extreme, so a close is
    in the discount of an up move only while the move is under 400 points, and in the OTE zone only for a pullback of 186 .. 200 points."""
    c = np.concatenate((np.full(600, 15000.0), np.linspace(15000, 15300, 100), np.full(12 * NB - 700, 15300.0)))
    return hl(c, 0.25)


def test_pdz_move_buys_the_discount_of_the_move_in_progress(monkeypatch):
    stub(monkeypatch, hist12(*rise_history()))                                   # the move: 14999.75 .. 15300.25, midpoint 15150
    assert first({"f_pdz_move": "with"}, day_at(15140.0)) == (True, False)       # 160 below the top: discount
    assert first({"f_pdz_move": "with"}, day_at(15250.0)) == (False, True)       # premium
    assert first({"f_pdz_move": "against"}, day_at(15140.0)) == (False, True)
    assert first({"f_pdz_move": "against"}, day_at(15250.0)) == (True, False)
    assert first({"f_pdz_move": "with"}, day_at(15150.0)) == (False, False)      # exactly the midpoint
    assert first({"f_pdz_move": "against"}, day_at(15150.0)) == (False, False)
    # 220 below the top the move has turned: a DOWN move 15300.25 .. 15079.75 (R = 220.5), the close on its lower half
    assert first({"f_pdz_move": "with"}, day_at(15100.0)) == (True, False)


def test_ote_move_is_the_62_to_79_percent_zone_of_a_leg_that_points_the_trades_way(monkeypatch):
    stub(monkeypatch, hist12(*rise_history()))                                   # R = 300.5; zone 15300.25 - .79 R .. - .62 R = 15062.8 .. 15113.9
    assert first({"f_ote_move": "in"}, day_at(15105.0)) == (True, False)         # a 195-point pullback: the move is still up
    assert first({"f_ote_move": "in"}, day_at(15200.0)) == (False, False)
    assert first({"f_ote_move": "out"}, day_at(15200.0)) == (True, False)        # a short has no leg of its direction: never a signal
    # a 220-point pullback turned the move DOWN (15300.25 .. 15079.75, R = 220.5): the zone for a short is 15216.5 .. 15254.0
    assert first({"f_ote_move": "in"}, day_at(15080.0)) == (False, False) and first({"f_ote_move": "out"}, day_at(15080.0)) == (False, True)


def test_the_blocks_decide_from_the_range_and_the_close_alone(monkeypatch):
    from types import SimpleNamespace as NS
    monkeypatch.setattr(Z, "range_of", lambda st, k: (100.0, 200.0, 1))        # an UP range 100 .. 200, midpoint 150, zone 121 .. 138
    st = lambda c: NS(nb=1, C=[c])                                               # noqa: E731
    assert [Z.pdz_range(st(c), "move") for c in (99.0, 201.0, 150.0, 149.0, 151.0)] == [None, None, None, "discount", "premium"]
    assert [Z.ote_range(st(c), 1, "move") for c in (121.0, 130.0, 138.0, 120.9, 138.1, 250.0)] == [True, True, True, False, False, False]
    assert Z.ote_range(st(130.0), -1, "move") is None                            # a short needs a DOWN leg
    monkeypatch.setattr(Z, "range_of", lambda st, k: (100.0, 200.0, -1))
    assert [Z.ote_range(st(c), -1, "move") for c in (162.0, 179.0, 161.9, 179.1)] == [True, True, False, False] and Z.ote_range(st(170.0), 1, "move") is None
    monkeypatch.setattr(Z, "range_of", lambda st, k: None)
    assert Z.pdz_range(st(150.0), "move") is None and Z.ote_range(st(150.0), 1, "move") is None


def test_a_move_under_40_points_is_no_range(monkeypatch):
    c = np.concatenate((np.full(1000, 15000.0), np.linspace(15000, 15020, 20), np.full(12 * NB - 1020, 15020.0)))
    stub(monkeypatch, hist12(*hl(c, 0.25)))
    monkeypatch.setattr(RG, "MOVE_PTS", 10.0)
    monkeypatch.setitem(RG.KINDS, "move", lambda h, l: RG.move(h, l, 10.0))
    assert first({"f_pdz_move": "with"}, day_at(15010.0)) == (False, False)


def swing_history():
    h, l = np.full(12 * NB, 15001.0), np.full(12 * NB, 14999.0)
    h[900], l[900] = 15301.0, 15299.0                                            # a swing high 540 bars before today
    l[1200], h[1200] = 14699.0, 14701.0                                          # a swing low 240 bars before it: the high came FIRST
    return h, l


def test_pdz_swing_and_ote_swing_use_the_latest_untouched_swing_pair(monkeypatch):
    stub(monkeypatch, hist12(*swing_history()))                                  # the range 14699 .. 15301, a DOWN leg; midpoint 15000
    assert first({"f_pdz_swing": "with"}, day_at(15100.0)) == (False, True)      # premium
    assert first({"f_pdz_swing": "with"}, day_at(14900.0)) == (True, False)
    assert first({"f_ote_swing": "in"}, day_at(15100.0)) == (False, True)        # zone 14699 + .62 R .. + .79 R = 15072.2 .. 15174.6
    assert first({"f_ote_swing": "in"}, day_at(14900.0)) == (False, False) and first({"f_ote_swing": "out"}, day_at(14900.0)) == (False, True)
    assert first({"f_pdz_swing": "with"}, day_at(15040.0)) == (False, True)      # 15040 is in the premium of 14699 .. 15301
    h, l = swing_history()
    h[1300], l[1300] = 15401.0, 15399.0                                          # a later bar above the swing high: that swing is gone; 15401 is the new swing high
    stub(monkeypatch, hist12(h, l))                                              # the range is now 14699 .. 15401 (the low came first: UP), midpoint 15050
    assert first({"f_pdz_swing": "with"}, day_at(15040.0)) == (True, False)      # the same close is in the discount of the new range


def leg_history():
    h, l = np.full(12 * NB, 15001.0), np.full(12 * NB, 14999.0)
    l[500], h[500] = 14599.0, 14601.0                                            # a 180-bar swing low
    h[900], l[900] = 15101.0, 15099.0                                            # a 180-bar swing high: an UP leg of 500 points in 400 bars
    return h, l


def test_pdz_leg_and_ote_leg_read_the_leg_rule(monkeypatch):
    stub(monkeypatch, hist12(*leg_history()))                                    # (14599, 15101, up); R = 502; zone 15101 - .79 R .. - .62 R = 14704.4 .. 14789.8
    assert first({"f_pdz_leg": "with"}, day_at(14700.0)) == (True, False)
    assert first({"f_pdz_leg": "with"}, day_at(15000.0)) == (False, True)
    assert first({"f_ote_leg": "in"}, day_at(14750.0)) == (True, False)
    assert first({"f_ote_leg": "in"}, day_at(14800.0)) == (False, False) and first({"f_ote_leg": "out"}, day_at(14800.0)) == (True, False)


def test_a_contract_roll_cuts_the_history_of_the_ranges(monkeypatch):
    stub(monkeypatch, hist12(*leg_history()))
    assert first({"f_pdz_leg": "with"}, day_at(14700.0)) == (True, False)
    from test_zones import run
    got = run({"f_pdz_leg": "with"}, day_at(14700.0), rolls={DATES[-2]})        # the roll day is the first session of the new contract: the swing low is older
    assert got and got[0][1:] == (False, False)


def test_the_decision_does_not_change_when_the_prints_after_it_change(monkeypatch):
    stub(monkeypatch, hist12(*rise_history()))
    a = day_at(15100.0, 40)
    b = list(a)
    for k in range(812 + 12, len(b)):                                            # everything from 09:42 on: a spike and a collapse
        b[k] = (15100.0, 17000.0, 13000.0, 15100.0, 40) if k % 2 else (15100.0, 15110.0, 12000.0, 12500.0, 40)
    for blk in ("pdz_move", "ote_move"):
        assert first({f"f_{blk}": "with" if blk.startswith("pdz") else "in"}, a) == first({f"f_{blk}": "with" if blk.startswith("pdz") else "in"}, b)


# ---- (vi) the lists ----------------------------------------------------------------------------------------------------------------------------

def test_the_six_blocks_are_filters_with_plain_words_defaults_off_nq_only_and_ask_for_the_bar_cache():
    for blk, sides in (("pdz", ("with", "against")), ("ote", ("in", "out"))):
        for k in RG.KINDS:
            b = f"{blk}_{k}"
            assert tuple(B.FILTERS[b]) == sides and all((b, s) in B.PLAIN for s in sides)
            assert B.Blocks.DEFAULTS[f"f_{b}"] == "off" and B.Blocks.SCHEMA[f"f_{b}"][1][0] == "off"
            assert B.BLOCK_MARKETS[b] == ("NQ",) and b in Z.RANGE_BLOCKS
            assert Z.prep_roots("NQ", "orb", (b, sides[0])) == ["NQ"]
            assert B.filter_inputs(b, sides[0]) == {f"f_{b}": sides[0]}
    assert Z.prep_roots("NQ", "orb", ("pdz", "with")) == []                       # the day-range block needs no bar cache
