"""OPEN FVG: the `open_fvg` entry trigger (families/open_fvg.py), written test-first from its rule.

THE RULE UNDER TEST (the fair value gap through the opening candle; the owner's request of 2026-10-10):
    candle    = the high and low of the first oc_min minutes from 09:30 ET (5 | 15 | 30), from 1-minute bars; the day's two levels
    gap       = fvg's: three tf bars, bar 3's low above bar 1's high (UP: near edge bar 3's low, far edge bar 1's high) or bar 3's high below
                bar 1's low (DOWN: near edge bar 3's high, far edge bar 1's low); all three closed inside the session; far to near edge >=
                max(min_gap x ATR14 of the tf, one tick)
    counts    = bar 2 closed after the candle ended and broke the level: UP low2 <= high_oc < close2, DOWN high2 >= low_oc > close2
    signal    = the first counting gap of the session, either side (max_tr signals a session, default 1; a later one only once the earlier
                order is gone and its trade closed)
    order     = at bar 3's close a LIMIT at the near edge, with the gap; it stays until it fills, a tf bar closes beyond the far edge, or
                the session's last 5 minutes; structure level = bar 1's low (up) / high (down)
    entries   = nyam / mid / pm only, one position at a time; the standard exits, flat 15:58.
Synthetic days with EXACT numbers cover each behaviour; seeded random-walk days check the signals, the orders and the fills against an
independent restatement of the rule at every bar size and session, and the gaps against fvg's own; real BUILD days check the signals
against the same restatement built from the raw prints, and the invariants (window, one position, flat 15:58) at 1 worker. No net, win rate
or profit factor is read.
"""
import numpy as np
import pytest

import families
import l2sim as S
import run_menus as RM
from families import fvg as FV
from families import open_fvg as OF
from test_blocks import D, DAILY, TICK, days_of, garble, minute_tape, ns, rand_bars, real_days

BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "min_gap": 0.1}
NY = ("nyam", "mid", "pm")
MS0 = ns("00:00") // 1_000_000
OPEN = 9 * 3600 + 30 * 60


def sec(h, m=0, s=0):
    return h * 3600 + m * 60 + s


def hm(s):
    return "%02d:%02d" % divmod(s // 60, 60)


def flat(n, px=15000.0, v=40):
    return [(px, px + TICK, px - TICK, px, v)] * n


def rest(n, px, v=40):
    """n quiet minutes one point either side of px."""
    return [(px, px + 1.0, px - 1.0, px, v)] * n


def bar(o, c, v=40):
    return (o, max(o, c), min(o, c), c, v)


def oc(hi=15004.0, lo=14996.0, n=5):
    """The opening candle: its first minute trades hi and lo, the other n - 1 are quiet at 15000."""
    return [(15000.0, hi, lo, 15000.0, 40)] + flat(n - 1)


def up_gap(base=15000.0):
    """Three minutes that leave an UP gap: bar 1 is base - 1 .. base + 1, bar 2 runs from base to base + 10, bar 3 bottoms at base + 6 and
    closes at base + 11. Near edge base + 6, far edge base + 1, bar 1's low base - 1."""
    return [(base, base + 1.0, base - 1.0, base, 40), (base, base + 10.0, base, base + 10.0, 40), (base + 10.0, base + 12.0, base + 6.0, base + 11.0, 40)]


def mirror(bars, px=15000.0):
    return [(2 * px - o, 2 * px - l, 2 * px - h, 2 * px - c, v) for o, h, l, c, v in bars]


def mir(rows, px=15000.0):
    """Logged rows the mirror way: the other side, every price reflected at px."""
    flip = {"long": "short", "short": "long"}
    return [tuple(flip[x] if x in flip else 2 * px - x if isinstance(x, float) else x for x in r) for r in rows]


def stretch(bars, tf):
    """Every minute bar tf times: the tf bars of the result have the highs, lows and closes of `bars`."""
    return [b for b in bars for _ in range(tf)]


def day(g, at="09:30", pre=15000.0):
    """A full day of minute bars from 00:00 ET to 15:59: flat at `pre` until `at`, then the bars `g`, then flat at the last close."""
    b = flat(S._sec(at) // 60, pre) + list(g)
    return b + flat(960 - len(b), b[-1][3])


def std(g, hi=15004.0, lo=14996.0):
    """From 09:30: the opening candle (5 minutes, high `hi`, low `lo`), five quiet minutes, then the bars `g` from 09:40."""
    return oc(hi, lo) + flat(5) + list(g)


def late(g, at):
    """The standard candle at 09:30, quiet until second `at`, then the bars `g`."""
    return day(oc() + flat((at - OPEN) // 60 - 5) + list(g))


def tape_of(bars, prints=None):
    """The day's tape from 00:00 (test_blocks.minute_tape: four prints a minute at :00 open, :15 and :30 the low and the high -- the low
    first in an up bar -- and :45 close). prints = {minute index: [(ms after the minute's start, price), ...]} replaces a minute's prints."""
    if not prints:
        return minute_tape(bars, "00:00")
    ts, px, sz = [], [], []
    for i, (o, h, l, c, v) in enumerate(bars):
        rows = prints[i] if i in prints else [(k * 15000, p) for k, p in enumerate((o, *((l, h) if c >= o else (h, l)), c))]
        for ms, p in rows:
            ts.append(ns("00:00") + i * 60 * S.NS + ms * 1_000_000)
            px.append(p)
            sz.append(v // 4)
    return S.Tape("NQ", D, "NQM3", np.array(ts, np.int64), np.array(px, float), np.array(sz, np.int64))


def sec_of(ctx):
    return (ctx.now_ns - S.et_ns(ctx.date, "00:00")) // S.NS


def run(params, bars, cls=None, tape=None):
    """One instance through one day (the explicit roll list: none). -> (the instance, the result)."""
    st = (cls or OF.OpenFvg)({**BASE, **params})
    st.ROLLS = frozenset()
    res = S.run_session(st, tape or tape_of(bars), daily=list(DAILY), on_error="raise")
    return st, res


class Spy(OF.OpenFvg):
    """Logs every order the family asks for: (second of the decision, side, limit price, structure level, an order was placed), and every
    cancel that took a working order away: its second."""
    log: list = []
    gone: list = []

    def _lim(self, ctx, side, px, **kw):
        o = super()._lim(ctx, side, px, **kw)
        type(self).log.append((sec_of(ctx), side, px, kw.get("struct"), o is not None))
        return o

    def _cancel(self, ctx):
        if any(r[0].status == "working" for r in self.orders):
            type(self).gone.append(sec_of(ctx))
        super()._cancel(ctx)


def play(params, bars, tape=None):
    """-> (the orders asked, the cancels, the result)."""
    cls = type("Spy", (Spy,), {"log": [], "gone": []})
    _, res = run(params, bars, cls, tape)
    return list(cls.log), list(cls.gone), res


class Sig(OF.OpenFvg):
    """Logs every signal the family sees (no order is placed, so nothing ever rests or is open): (second, side, near edge, far edge,
    structure level)."""
    seen: list = []

    def fam_signal(self, ctx):
        if self.gap is not None:
            type(self).seen.append((sec_of(ctx), *self.gap))


def signals(params, bars, tape=None):
    cls = type("Sig", (Sig,), {"seen": []})
    run(params, bars, cls, tape)
    return list(cls.seen)


B1 = (15000.0, 15001.0, 14999.0, 15000.0, 40)                        # up_gap()'s three bars
B2 = (15000.0, 15010.0, 15000.0, 15010.0, 40)
B3 = (15010.0, 15012.0, 15006.0, 15011.0, 40)
BACK = (15011.0, 15011.0, 15005.0, 15008.0, 40)                      # a minute that comes back through the near edge 15006 (its low prints at :30)
SIG1 = (sec(9, 43), "long", 15006.0, 15001.0, 14999.0)               # std(up_gap()): bars 09:40 / 09:41 / 09:42, read at 09:43:00
ORD1 = (sec(9, 43), "long", 15006.0, 14999.0, True)


# ---- (i) the signal and its order ----------------------------------------------------------------------------------------------------------------

def test_an_up_gap_through_the_candles_high_rests_a_buy_at_bar_3s_low_and_the_mirror_a_sell():
    g = std(up_gap() + rest(3, 15011.0))                             # bar 2 runs 15000 -> 15010 through the candle's high 15004
    assert signals({}, day(g)) == [SIG1]
    log, gone, res = play({}, day(g))
    assert log == [ORD1] and res.trades == []                        # price never comes back: the order rests ...
    assert gone == [sec(10, 55)]                                     # ... until the session's last 5 minutes
    assert signals({}, day(mirror(g))) == mir([SIG1]) == [(sec(9, 43), "short", 14994.0, 14999.0, 15001.0)]
    log, gone, res = play({}, day(mirror(g)))
    assert log == mir([ORD1]) == [(sec(9, 43), "short", 14994.0, 15001.0, True)] and res.trades == [] and gone == [sec(10, 55)]


def test_the_limit_fills_on_a_return_one_tick_through_the_near_edge_at_its_price():
    def back(low):
        return std(up_gap() + rest(3, 15011.0) + [(15011.0, 15011.0, low, 15008.0, 40)])
    assert play({}, day(back(15006.0)))[2].trades == []              # a touch of the edge is not a fill (the engine's limit law)
    for bars, side, px in ((day(back(15006.0 - TICK)), "long", 15006.0), (day(mirror(back(15006.0 - TICK))), "short", 14994.0)):
        log, _, res = play({}, bars)
        t = res.trades[0]
        assert len(res.trades) == 1 and len(log) == 1 and (t["side"], t["entry_price"], t["order_price"]) == (side, px, px)
        assert t["entry_ms"] == MS0 + (sec(9, 46) + 30) * 1000       # the 09:46 minute's extreme prints at :30


def test_the_structure_level_is_bar_1s_far_extreme_not_the_gaps_far_edge():
    p = {"stop_mode": "struct", "tgt_r": 1.0}
    g = std(up_gap() + rest(3, 15011.0) + [BACK])
    t = play(p, day(g))[2].trades[0]
    assert (t["entry_price"], t["sl"], t["tp"]) == (15006.0, 14999.0, 15013.0)      # the stop at bar 1's LOW, 7 points; the target 7 points
    t = play(p, day(mirror(g)))[2].trades[0]
    assert (t["entry_price"], t["sl"], t["tp"]) == (14994.0, 15001.0, 14987.0)      # a down gap: bar 1's HIGH
    st = FV.Fvg({**BASE, **p, "min_gap": 0.1, "mode": "touch"})       # fvg on the same bars passes the gap's far edge (bar 1's high)
    st.ROLLS = frozenset()
    f = S.run_session(st, tape_of(day(g)), daily=list(DAILY), on_error="raise").trades[0]
    assert (f["entry_price"], f["sl"]) == (15006.0, 15001.0)


# ---- (ii) through the level: the middle bar trades at it and closes beyond it ----------------------------------------------------------------------

def three(b2, b3, b1=B1, lead=(), **candle):
    """The standard candle (or oc(**candle)), five quiet minutes, `lead`, then b1 / b2 / b3 and three quiet minutes at b3's close."""
    return std(list(lead) + [b1, b2, b3] + rest(3, b3[3]), **candle)


def both_ways(bars, want):
    assert signals({}, day(bars)) == want
    assert signals({}, day(mirror(bars))) == mir(want)


def test_a_close_exactly_on_the_level_is_not_through_it_and_one_tick_beyond_is():
    b3 = (15004.0, 15006.0, 15002.0, 15005.0, 40)                    # the gap 15001 .. 15002 either way
    both_ways(three(bar(15000.0, 15004.0), b3), [])                  # bar 2 closes ON the candle's high 15004
    both_ways(three(bar(15000.0, 15004.0 + TICK), b3), [(sec(9, 43), "long", 15002.0, 15001.0, 14999.0)])


def test_the_middle_bar_must_trade_at_the_level_a_bar_that_opens_beyond_it_is_nothing():
    both_ways(three((15004.0 + TICK, 15010.0, 15004.0 + TICK, 15010.0, 40), B3), [])       # its low is one tick above the level
    both_ways(three((15004.0, 15010.0, 15004.0, 15010.0, 40), B3), [SIG1])                 # its low is ON the level: it traded there


def test_it_is_the_middle_bar_that_must_cross_not_bar_3_and_not_bar_1():
    both_ways(three(B2, B3, hi=15010.5, lo=14989.5), [])             # bar 2 closes at 15010 under the level, bar 3 closes over it
    lead = [(15000.0, 15006.0, 14999.0, 15000.0, 40)]                # (a minute that reaches 15006, so the bars before bar 1 leave no gap of their own)
    b1, b2, b3 = (15000.0, 15005.0, 14999.0, 15005.0, 40), (15005.0, 15015.0, 15005.0, 15015.0, 40), (15015.0, 15017.0, 15011.0, 15016.0, 40)
    both_ways(three(b2, b3, b1, lead), [])                           # bar 1 closes over 15004; bar 2 never trades at it: the gap 15005 .. 15011 is nothing


def test_a_gap_whose_middle_bar_does_not_reach_a_level_is_nothing_and_does_not_use_the_signal():
    both_ways(three(B2, B3, hi=15020.0, lo=14980.0), [])             # the same gap between the two levels of a wide candle
    g = std(up_gap() + rest(2, 15011.0) + up_gap(15011.0) + rest(3, 15022.0), hi=15020.0, lo=14980.0)
    want = (sec(9, 48), "long", 15017.0, 15012.0, 15010.0)           # the SECOND gap (09:45 / 46 / 47): its bar 2 runs 15011 -> 15021 through 15020
    both_ways(g, [want])
    assert play({}, day(g))[0] == [(want[0], "long", 15017.0, 15010.0, True)]              # no order was asked for the first gap


def test_the_level_is_the_candle_of_the_first_oc_min_minutes():
    spike = lambda x: (15000.0, 15000.0 + x, 15000.0 - x, 15000.0, 40)  # noqa: E731
    g = ([spike(4.0)] + flat(4) + [spike(20.0)] + flat(9) + [spike(40.0)] + flat(19)       # 09:30 +-4, 09:35 +-20, 09:45 +-40, quiet to 10:04
         + up_gap() + rest(2, 15011.0)                               # 10:05 / 06 / 07: bar 2 15000 -> 15010, through 15004 only
         + up_gap(15011.0) + rest(2, 15022.0)                        # 10:10 / 11 / 12: bar 2 15011 -> 15021, through 15020 only
         + up_gap(15033.0) + rest(3, 15044.0))                       # 10:15 / 16 / 17: bar 2 15033 -> 15043, through 15040 only
    want = {"5": (sec(10, 8), "long", 15006.0, 15001.0, 14999.0), "15": (sec(10, 13), "long", 15017.0, 15012.0, 15010.0),
            "30": (sec(10, 18), "long", 15039.0, 15034.0, 15032.0)}
    for oc_min, x in (("5", 4.0), ("15", 20.0), ("30", 40.0)):
        assert signals({"oc_min": oc_min}, day(g)) == [want[oc_min]], oc_min
        assert signals({"oc_min": oc_min}, day(mirror(g))) == mir([want[oc_min]]), oc_min
        st, _ = run({"oc_min": oc_min}, day(g))
        assert (st.och, st.ocl) == (15000.0 + x, 15000.0 - x)
    assert OF.OpenFvg.defaults()["oc_min"] == "5" and signals({}, day(g)) == [want["5"]]


def spikes():
    """A quiet day at 15000 with one spike minute each side of every candle's two ends: 09:29 +-50 (before the open), 09:34 +-5,
    09:35 +-6, 09:44 +-15, 09:45 +-16, 09:59 +-30, 10:00 +-31."""
    b = flat(960)
    for i, x in ((569, 50.0), (574, 5.0), (575, 6.0), (584, 15.0), (585, 16.0), (599, 30.0), (600, 31.0)):
        b[i] = (15000.0, 15000.0 + x, 15000.0 - x, 15000.0, 40)
    return b


@pytest.mark.parametrize("tf", [1, 5, 15])
def test_the_candle_is_the_minutes_from_09_30_to_its_end_and_no_other(tf):
    for oc_min, x in (("5", 5.0), ("15", 15.0), ("30", 30.0)):
        for sess in NY:
            st, res = run({"tf": str(tf), "oc_min": oc_min, "sess": sess}, spikes())
            assert (st.och, st.ocl) == (15000.0 + x, 15000.0 - x) and res.trades == [], (oc_min, sess)


def test_a_gap_inside_the_candle_is_nothing_however_it_looks_against_the_candle_so_far():
    # 09:36 / 37 / 38: bar 2 closes at 15010, over the high of the first minutes (15004). Then quiet at 15011 to 09:45, and a second gap at
    # 09:46 / 47 / 48 whose bar 2 runs 15011 -> 15021
    g = oc() + flat(1) + up_gap() + rest(7, 15011.0) + up_gap(15011.0) + rest(3, 15022.0)
    assert signals({"oc_min": "5"}, day(g)) == [(sec(9, 39), "long", 15006.0, 15001.0, 14999.0)]       # the 5-minute candle had ended
    # the 15-minute candle (09:30-09:45) holds the first gap: its high is 15012, and the second gap's bar 2 goes through that
    assert signals({"oc_min": "15"}, day(g)) == [(sec(9, 49), "long", 15017.0, 15012.0, 15010.0)]
    st, _ = run({"oc_min": "15"}, day(g))
    assert (st.och, st.ocl) == (15012.0, 14996.0)
    both_ways(g[:-6] + rest(9, 15011.0), [(sec(9, 39), "long", 15006.0, 15001.0, 14999.0)])              # (default oc_min 5, without the second gap)
    assert signals({"oc_min": "15"}, day(g[:-6] + rest(9, 15011.0))) == []


FIRST = {(1, 5): sec(9, 37), (1, 15): sec(9, 47), (1, 30): sec(10, 2), (5, 5): sec(9, 45), (5, 15): sec(9, 55), (5, 30): sec(10, 10),
         (15, 5): sec(10, 15), (15, 15): sec(10, 15), (15, 30): sec(10, 30)}       # the module docstring's table


@pytest.mark.parametrize("oc_min", [5, 15, 30])
@pytest.mark.parametrize("tf", [1, 5, 15])
def test_the_first_close_that_can_show_a_counting_gap(tf, oc_min):
    step, end = tf * 60, OPEN + oc_min * 60
    b2 = -(-end // step) * step                                      # bar 2 begins at the first tf boundary at or after the candle's end
    pat = stretch(up_gap() + rest(3, 15011.0), tf)
    p = {"tf": str(tf), "oc_min": str(oc_min)}
    assert b2 + 2 * step == FIRST[(tf, oc_min)]
    assert signals(p, day(pat, at=hm(b2 - step))) == [(b2 + 2 * step, "long", 15006.0, 15001.0, 14999.0)]
    assert signals(p, day(mirror(pat), at=hm(b2 - step))) == [(b2 + 2 * step, "short", 14994.0, 14999.0, 15001.0)]
    assert signals(p, day(pat, at=hm(b2 - 2 * step))) == []          # one bar earlier: bar 2 is a piece of the candle, or bar 1 is before the session


def test_with_5_minute_bars_and_a_5_minute_candle_bar_1_is_the_opening_candle_itself():
    bars = day(stretch(up_gap() + rest(3, 15011.0), 5))              # bar 1 = 09:30-09:35 (14999 .. 15001), bar 2 = 09:35-09:40, bar 3 = 09:40-09:45
    p = {"tf": "5", "oc_min": "5"}
    st, _ = run(p, bars)
    assert (st.och, st.ocl) == (15001.0, 14999.0)
    assert signals(p, bars) == [(sec(9, 45), "long", 15006.0, st.och, st.ocl)]      # the far edge is the candle's high, the structure level its low
    assert play(p, bars)[0] == [(sec(9, 45), "long", 15006.0, 14999.0, True)]


# ---- (iii) the gap: fvg's, with its size floor ---------------------------------------------------------------------------------------------------

def tf_bars(bars, tf):
    """The tf bars of a day of minute bars from 00:00 (clock multiples): [(end second, o, h, l, c)]."""
    out = []
    for i in range(0, len(bars) - tf + 1, tf):
        ch = bars[i:i + tf]
        out.append(((i + tf) * 60, ch[0][0], max(b[1] for b in ch), min(b[2] for b in ch), ch[-1][3]))
    return out


def atr14(tb):
    """Wilder ATR(14) after each bar of [(end, o, h, l, c)], restated: the plain mean of the true ranges up to 14 bars, then (13 x old + new) / 14.
    The first bar's true range is its high - low."""
    out, trs, a = [], [], None
    for n, (_, o, h, l, c) in enumerate(tb):
        tr = h - l if n == 0 else max(h - l, abs(h - tb[n - 1][4]), abs(l - tb[n - 1][4]))
        trs.append(tr)
        a = sum(trs) / len(trs) if len(trs) <= 14 else (a * 13.0 + tr) / 14.0
        out.append(a)
    return out


def test_the_gap_must_be_min_gap_times_the_atr_of_the_bar_size_at_bar_3s_close():
    bars = day(std(up_gap() + rest(3, 15011.0)))
    atr = atr14(tf_bars(bars, 1))
    a, before = atr[9 * 60 + 42], atr[9 * 60 + 41]                   # the ATR after the 09:42 bar (bar 3) has closed, and one bar earlier
    assert 1.0 < a < 4.0 and abs(before - a) > 0.01 * a              # (the 5-point gap is a few ATR: min_gap around 5 / a decides)
    assert signals({"min_gap": 5.0 / a * 0.999}, bars) == [SIG1]
    assert signals({"min_gap": 5.0 / a * 1.001}, bars) == []
    assert OF.OpenFvg.defaults()["min_gap"] == 0.1


def test_a_gap_is_never_less_than_one_tick_even_with_min_gap_zero():
    def one(low3):                                                   # bar 3's low against bar 1's high (15001)
        return signals({"min_gap": 0.0}, day(three(B2, (15010.0, 15012.0, low3, 15011.0, 40))))
    assert one(15001.0 + TICK) == [(sec(9, 43), "long", 15001.0 + TICK, 15001.0, 14999.0)] and one(15001.0) == []


def test_the_gaps_are_fvgs_own_gaps_on_random_days():
    n = 0
    for tf in (1, 5, 15):
        for seed in (3, 11):
            tape = tape_of(flat(60) + rand_bars(900, seed, p0=15000.0, step=6.0))
            a, b = [], []

            class LookF(FV.Fvg):
                def fam_update(self, ctx):
                    super().fam_update(ctx)
                    if self.gap is not None:
                        a.append((sec_of(ctx), *self.gap))

                def fam_signal(self, ctx):
                    pass

            class LookO(OF.OpenFvg):
                def fam_update(self, ctx):
                    super().fam_update(ctx)
                    if self.raw is not None:
                        b.append((sec_of(ctx), *self.raw))

                def fam_signal(self, ctx):
                    pass

            for sess in NY:
                a.clear()
                b.clear()
                for cls in (LookF, LookO):
                    st = cls({"hold_to": "day", "tf": str(tf), "sess": sess, "min_gap": 0.25})
                    st.ROLLS = frozenset()
                    S.run_session(st, tape, daily=list(DAILY), on_error="raise")
                assert a == b, (tf, seed, sess)
                n += len(a)
    assert n > 20


def test_the_three_bars_must_close_inside_the_session():
    g = up_gap() + rest(3, 15011.0)
    # bar 1 = the 10:58 minute and bar 2 = the 10:59 minute (it closes at 11:00:00, the end of nyam and not yet inside mid)
    for sess in ("nyam", "mid"):
        assert signals({"sess": sess}, late(g, sec(10, 58))) == []
        assert signals({"sess": sess}, late(g, sec(10, 59))) == []    # bar 1 closes at 11:00:00
    assert signals({"sess": "mid"}, late(g, sec(11))) == [(sec(11, 3), "long", 15006.0, 15001.0, 14999.0)]
    assert signals({"sess": "pm"}, late(g, sec(13, 29))) == []
    assert signals({"sess": "pm"}, late(g, sec(13, 30))) == [(sec(13, 33), "long", 15006.0, 15001.0, 14999.0)]


# ---- (iv) the first one only; max_tr; the order's life ---------------------------------------------------------------------------------------------

def waves(n):
    """n times, from 09:40, 8 minutes each: the up gap through 15004 (read at 09:43 + 8i), a quiet minute, a minute back through the near
    edge (the order fills at :30 of 09:44 + 8i), a minute down to 15000, two quiet minutes."""
    g = []
    for _ in range(n):
        g += up_gap() + rest(1, 15011.0) + [BACK, bar(15008.0, 15000.0)] + flat(2)
    return day(std(g))


def test_the_first_counting_gap_is_the_days_signal_and_max_tr_allows_up_to_three():
    bars = waves(5)
    at = lambda i: sec(9, 43) + 480 * i  # noqa: E731
    assert OF.OpenFvg.defaults()["max_tr"] == 1
    assert signals({}, bars) == [SIG1]                               # five counting gaps: the first one only
    for m in (1, 2, 3):
        assert signals({"max_tr": m}, bars) == [(at(i), *SIG1[1:]) for i in range(m)], m
        log, _, res = play({"max_tr": m, "exit_bars": 1}, bars)      # (each trade leaves at the first close after its fill)
        assert log == [(at(i), *ORD1[1:]) for i in range(m)] and len(res.trades) == m, m
        tr = sorted(res.trades, key=lambda t: t["entry_ms"])
        assert [t["entry_ms"] for t in tr] == [MS0 + (at(i) + 90) * 1000 for i in range(m)]
        assert all(a["exit_ms"] <= b["entry_ms"] for a, b in zip(tr, tr[1:]))
    # one position at a time: without an exit the first trade stays open and every later gap is nothing, whatever max_tr
    log, _, res = play({"max_tr": 3}, bars)
    assert log == [ORD1] and len(res.trades) == 1


def test_a_counting_gap_while_the_order_still_rests_is_not_a_signal_and_is_not_counted():
    second = [(15011.0, 15012.0, 15007.0, 15008.0, 40), (15008.0, 15020.0, 15007.5, 15020.0, 40), (15020.0, 15022.0, 15016.0, 15021.0, 40)]
    third = [(15006.0, 15007.0, 15005.0, 15006.0, 40), (15006.0, 15016.0, 15006.0, 15016.0, 40), (15016.0, 15018.0, 15012.0, 15017.0, 40)]
    g = (up_gap() + rest(2, 15011.0)                                 # 09:40-42: read at 09:43, a buy rests at 15006 (the candle's high is 15008 here)
         + second                                                    # 09:45-47: bar 2 goes through 15008 again, never under 15007: the order is untouched
         + [(15021.0, 15021.0, 15005.0, 15006.0, 40)]                # 09:48: back through 15006: the first order fills at 09:48:30
         + third + rest(3, 15017.0))                                 # 09:49-51: a third gap through 15008, read at 09:52
    bars = day(std(g, hi=15008.0))
    s2, s3 = (sec(9, 48), "long", 15016.0, 15012.0, 15007.0), (sec(9, 52), "long", 15012.0, 15007.0, 15005.0)
    assert signals({"max_tr": 3}, bars) == [SIG1, s2, s3]            # (with no order resting, each of the three is a counting gap)
    o3 = (sec(9, 52), "long", 15012.0, 15005.0, True)
    assert play({"exit_bars": 1}, bars)[0] == [ORD1]                 # max_tr 1: the first only
    for m in (2, 3):                                                 # the second gap formed while the first order rested: no signal, and not counted,
        log, _, res = play({"max_tr": m, "exit_bars": 1}, bars)      # so the third gap is the SECOND signal
        assert log == [ORD1, o3] and len(res.trades) == 1 and res.trades[0]["entry_ms"] == MS0 + (sec(9, 48) + 30) * 1000, m


def test_a_counting_gap_while_the_trade_is_open_is_not_a_signal_and_is_not_counted():
    second = [(15011.0, 15012.0, 15007.0, 15008.0, 40), (15008.0, 15020.0, 15007.5, 15020.0, 40), (15020.0, 15022.0, 15016.0, 15021.0, 40)]
    third = [(15006.0, 15007.0, 15005.0, 15006.0, 40), (15006.0, 15016.0, 15006.0, 15016.0, 40), (15016.0, 15018.0, 15012.0, 15017.0, 40)]
    g = (up_gap()                                                    # 09:40-42: read at 09:43
         + [(15011.0, 15011.0, 15005.0, 15011.0, 40)]                # 09:43: back through 15006 at once: the trade is open from 09:43:15
         + second + rest(1, 15021.0)                                 # 09:44-46: a counting gap read at 09:47, the trade still open (it leaves at 09:48:00)
         + [(15021.0, 15021.0, 15006.0, 15006.0, 40)]                # 09:48
         + third + rest(3, 15017.0))                                 # 09:49-51: read at 09:52, flat again
    bars = day(std(g, hi=15008.0))
    o3 = (sec(9, 52), "long", 15012.0, 15005.0, True)
    log, _, res = play({"exit_bars": 5}, bars)
    assert log == [ORD1] and [t["exit_ms"] for t in res.trades] == [MS0 + sec(9, 48) * 1000]
    for m in (2, 3):
        assert play({"max_tr": m, "exit_bars": 5}, bars)[0] == [ORD1, o3], m


def two_sides():
    """An up gap through the candle's high (read at 09:43), a fall back to 15000 at 09:45, a down gap through its low (read at 09:49)."""
    return std(up_gap() + rest(2, 15011.0) + [bar(15011.0, 15000.0)] + mirror(up_gap()) + rest(3, 14989.0))


def test_dir_decides_which_orders_are_placed_not_which_gap_is_the_first():
    assert OF.OpenFvg.defaults()["dir"] == "both"
    bars, o2 = day(two_sides()), (sec(9, 49), "short", 14994.0, 15001.0, True)
    assert signals({"max_tr": 3}, bars) == [SIG1, (sec(9, 49), "short", 14994.0, 14999.0, 15001.0)]
    key = lambda res: [(t["side"], t["entry_ms"], t["entry_price"]) for t in res.trades]  # noqa: E731
    both, long, short = (play({"dir": d}, bars) for d in ("both", "long", "short"))
    assert both[0] == long[0] == [ORD1] and key(both[2]) == key(long[2]) == [("long", MS0 + (sec(9, 45) + 30) * 1000, 15006.0)]
    assert short[0] == [(*ORD1[:4], False)] and short[2].trades == []        # the first gap is the day's signal: its side is off, no order, no trade
    assert key(long[2]) + key(short[2]) == key(both[2])                      # max_tr 1: the two sides are together the trades of dir both
    assert play({"dir": "short", "max_tr": 2}, bars)[0] == [(*ORD1[:4], False), o2]       # max_tr 2: the down gap is the second signal
    assert play({"dir": "both", "max_tr": 2}, bars)[0] == [ORD1]             # ... which dir both never sees: its long trade is still open
    # the mirror day: a down gap first
    m = day(mirror(two_sides()))
    assert play({"dir": "long"}, m)[0] == mir([(*ORD1[:4], False)]) and play({"dir": "long"}, m)[2].trades == []
    assert play({"dir": "short"}, m)[0] == mir([ORD1]) and play({"dir": "long", "max_tr": 2}, m)[0] == mir([(*ORD1[:4], False), o2])


def test_a_signal_whose_order_cannot_rest_is_used_all_the_same():
    low_close = (15010.0, 15012.0, 15006.0, 15006.0, 40)             # bar 3 closes ON its low: a buy at 15006 would not be on the passive side
    g = std([B1, B2, low_close, bar(15006.0, 15000.0)] + flat(2) + up_gap() + rest(3, 15011.0))        # ... and a second gap, read at 09:49
    for bars, f in ((day(g), lambda x: x), (day(mirror(g)), mir)):
        log, _, res = play({}, bars)
        assert log == f([(*ORD1[:4], False)]) and res.trades == []
        assert play({"max_tr": 2}, bars)[0] == f([(*ORD1[:4], False), (sec(9, 49), *ORD1[1:])])


def crossed(close):
    """The standard gap, read at 09:43:00 (the buy at 15006 is placed then: no print fills it for 85 ms). The 09:43 minute is ONE print,
    10 ms after the close, at `close`; quiet minutes there afterwards. -> (bars, tape, the same mirrored)."""
    bars = day(std(up_gap() + [(close, close, close, close, 40)]))
    m = mirror(bars)
    return bars, tape_of(bars, {583: [(10, close)]}), m, tape_of(m, {583: [(10, 30000.0 - close)]})


def test_the_order_is_cancelled_at_a_close_beyond_the_gaps_far_edge():
    for close in (14990.0, 15001.0 - TICK):                          # under bar 1's high 15001: the gap failed
        bars, tape, m, mtape = crossed(close)
        for b, t, f in ((bars, tape, lambda x: x), (m, mtape, mir)):
            log, gone, res = play({}, b, t)
            assert log == f([ORD1]) and gone == [sec(9, 44)] and res.trades == [], close      # cancelled at the 09:43 minute's close: never filled


def test_a_close_on_the_far_edge_or_inside_the_gap_leaves_the_order():
    for close in (15001.0, 15003.0):                                 # ON bar 1's high / between the two edges
        bars, tape, m, mtape = crossed(close)
        for b, t, px in ((bars, tape, 15006.0), (m, mtape, 14994.0)):
            log, gone, res = play({}, b, t)
            assert len(log) == 1 and gone == [] and len(res.trades) == 1, close
            assert (res.trades[0]["entry_price"], res.trades[0]["entry_ms"]) == (px, MS0 + sec(9, 44) * 1000)     # it fills at the next print


def test_a_wick_beyond_the_far_edge_that_closes_back_leaves_the_order():
    # the 09:43 minute prints 14990 inside the order delay (under the far edge 15001, no fill) and closes at 15008: it did not CLOSE beyond
    # the edge, so the buy still rests and the 09:44 minute's low 15005 fills it
    bars = day(std(up_gap() + [(14990.0, 15008.0, 14990.0, 15008.0, 40), (15008.0, 15008.0, 15005.0, 15008.0, 40)]))
    m = mirror(bars)
    for b, t, px, at in ((bars, tape_of(bars, {583: [(10, 14990.0), (30000, 15008.0)]}), 15006.0, 15),
                         (m, tape_of(m, {583: [(10, 15010.0), (30000, 14992.0)]}), 14994.0, 30)):       # (the mirrored minute prints its high at :30)
        log, gone, res = play({}, b, t)
        assert len(log) == 1 and gone == [] and len(res.trades) == 1
        assert (res.trades[0]["entry_price"], res.trades[0]["entry_ms"]) == (px, MS0 + (sec(9, 44) + at) * 1000)


def test_a_return_that_fills_and_then_closes_beyond_the_far_edge_is_a_trade_like_any_other():
    g = std(up_gap() + rest(1, 15011.0) + [(15011.0, 15011.0, 14998.0, 14999.0, 40)])       # 09:44: through the whole gap, the close under bar 1's high
    for bars, px in ((day(g), 15006.0), (day(mirror(g)), 14994.0)):
        log, gone, res = play({"exit_bars": 1}, bars)                # the order filled at :30: nothing is left to cancel at that close,
        assert len(log) == 1 and gone == [] and len(res.trades) == 1                           # ... and the Template manages the trade (it leaves after one bar)
        t = res.trades[0]
        assert (t["entry_price"], t["entry_ms"], t["exit_ms"], t["exit_reason"]) == (px, MS0 + (sec(9, 44) + 30) * 1000, MS0 + sec(9, 45) * 1000, "bars")


def test_after_a_cancelled_order_the_next_counting_gap_is_a_signal_only_with_max_tr_above_1():
    again = [(14990.0, 14991.0, 14989.0, 14990.0, 40), (14990.0, 15010.0, 14990.0, 15010.0, 40), B3]    # 09:46-48: back up through 15004
    bars = day(std(up_gap() + [(14990.0,) * 4 + (40,)] + flat(2, 14990.0) + again + rest(3, 15011.0)))
    tape = tape_of(bars, {583: [(10, 14990.0)]})
    log, gone, res = play({}, bars, tape)
    assert log == [ORD1] and gone == [sec(9, 44)] and res.trades == []
    log, gone, res = play({"max_tr": 2}, bars, tape)
    assert log == [ORD1, (sec(9, 49), "long", 15006.0, 14989.0, True)] and gone == [sec(9, 44), sec(10, 55)] and res.trades == []


def test_the_close_that_cancels_an_order_can_show_the_next_signal():
    # 09:40 bar 1 (high 14990); 09:41 bar 2 runs 14995 -> 15010 through the high 15004; 09:42 bar 3 falls back and closes at 14993, under the
    # candle's low 14996, its low 14992 still over bar 1's high: an UP gap 14990 .. 14992, read at 09:43:00, a buy rests at 14992.
    # 09:43: two prints inside the order delay, 14982 and 14980. That minute closes under the far edge 14990 (the buy is cancelled) AND is bar 3
    # of a DOWN gap 14982 .. 14995 whose middle bar (09:42) broke the candle's low: with max_tr 2 it is the second signal, at the same close.
    g = [(14989.0, 14990.0, 14988.0, 14989.0, 40), (14995.0, 15010.0, 14995.0, 15010.0, 40), (15010.0, 15010.0, 14992.0, 14993.0, 40),
         (14982.0, 14982.0, 14980.0, 14980.0, 40)]
    bars = day(std(g))
    tape = tape_of(bars, {583: [(5, 14982.0), (10, 14980.0)]})
    o1, o2 = (sec(9, 43), "long", 14992.0, 14988.0, True), (sec(9, 44), "short", 14982.0, 15010.0, True)
    log, gone, res = play({"max_tr": 2}, bars, tape)
    assert log == [o1, o2] and gone == [sec(9, 44), sec(10, 55)] and res.trades == []
    log, gone, res = play({}, bars, tape)
    assert log == [o1] and gone == [sec(9, 44)] and res.trades == []
    m = mirror(bars)
    assert play({"max_tr": 2}, m, tape_of(m, {583: [(5, 15018.0), (10, 15020.0)]}))[0] == mir([o1, o2])


def test_no_order_in_the_last_five_minutes_and_a_resting_one_is_cancelled_there():
    for sess, end in (("nyam", sec(11)), ("mid", sec(13, 30)), ("pm", sec(15, 58))):
        at = end - 360 - 180                                         # bar 3 closes 6 minutes before the end
        want = (end - 360, "long", 15006.0, 14999.0, True)
        log, gone, res = play({"sess": sess}, late(up_gap() + rest(3, 15011.0) + [BACK], at))
        assert log == [want] and gone == [end - 300] and res.trades == [], sess          # the return comes at end - 3 min: the order is gone
        log, gone, res = play({"sess": sess}, late(up_gap() + [BACK], at))
        assert log == [want] and gone == [] and len(res.trades) == 1, sess                # (the same return before the last 5 minutes fills)
        assert res.trades[0]["entry_ms"] == MS0 + (end - 360 + 30) * 1000
        log, gone, res = play({"sess": sess}, late(up_gap() + [BACK], at + 60))           # bar 3 closes 5 minutes before the end: too late
        assert log == [] and gone == [] and res.trades == [], sess
        assert signals({"sess": sess, "max_tr": 3}, late(up_gap() + [BACK], at + 60)) == []


@pytest.mark.parametrize("tf", [1, 5, 15])
def test_the_order_is_placed_at_bar_3s_close_and_fills_later_at_the_near_edge(tf):
    bars = day(stretch(up_gap() + rest(1, 15011.0) + [BACK], tf), at="11:00")      # five tf bars from 11:00; the return is the fifth
    p = {"tf": str(tf), "sess": "mid"}
    decided = sec(11) + 3 * tf * 60
    log, _, res = play(p, bars)
    assert log == [(decided, "long", 15006.0, 14999.0, True)] and len(res.trades) == 1, tf
    t = res.trades[0]
    assert t["entry_ms"] == MS0 + (sec(11) + 4 * tf * 60 + 30) * 1000 and t["entry_ms"] >= MS0 + decided * 1000 + 85 and t["entry_price"] == 15006.0


# ---- (v) the sessions ---------------------------------------------------------------------------------------------------------------------------------

def test_it_trades_the_new_york_day_sessions_only():
    for s in RM.DAY_PASSES:
        assert OF.OpenFvg({"tf": "5", "sess": s, "hold_to": "day"}).sessions() == ([s] if s in NY else []), s
    assert OF.OpenFvg({"tf": "5", "sess": "all"}).sessions() == list(NY) == OF.OpenFvg({"tf": "5", "sess": "globex"}).sessions()
    g = up_gap() + rest(3, 15011.0)
    for sess, at in (("asia", "01:00"), ("london", "04:00"), ("pre", "08:40")):
        assert signals({"sess": sess}, day(g, at=at)) == [] and play({"sess": sess}, day(g, at=at))[2].trades == []


def test_a_new_session_starts_fresh_and_keeps_the_days_levels():
    # nyam: the gap at 09:40 (read 09:43), the fall back to 15000 at 09:45; quiet to 11:10; the same gap again at 11:10 (read 11:13, in mid)
    g = std(up_gap() + rest(2, 15011.0) + [bar(15011.0, 15000.0)] + flat(84) + up_gap() + rest(3, 15011.0))
    bars, s2 = day(g), (sec(11, 13), *SIG1[1:])
    assert signals({"sess": "nyam"}, bars) == [SIG1] and signals({"sess": "mid"}, bars) == [s2] and signals({"sess": "pm"}, bars) == []
    every = {"hold_to": "session", "sess": "all"}                    # one instance that trades session after session
    assert signals(every, bars) == [SIG1, s2]                        # max_tr 1 is a session's: mid has its own first gap, through the same level
    log, _, res = play(every, bars)
    assert log == [ORD1, (sec(11, 13), *ORD1[1:])] and len(res.trades) == 1
    st, _ = run(every, bars)
    assert (st.och, st.ocl) == (15004.0, 14996.0)


# ---- (vi) NO LOOK-AHEAD ------------------------------------------------------------------------------------------------------------------------------

def test_a_future_bar_cannot_change_an_earlier_decision():
    bars = waves(4)
    tape = tape_of(bars)
    params = {"max_tr": 3, "exit_bars": 1}
    clean, _, _ = play(params, bars, tape)
    assert len(clean) == 3
    for cut in [x[0] for x in clean] + [sec(9, 33), sec(9, 35), sec(9, 41, 30), sec(9, 44, 20), sec(9, 52)]:
        got, _, _ = play(params, bars, garble(tape, ns("00:00") + cut * S.NS))
        assert [x for x in got if x[0] <= cut] == [x for x in clean if x[0] <= cut], cut       # a decision AT the cut reads prints before it
        assert cut == clean[-1][0] or any(x[0] > cut for x in clean)                           # (a later decision was there to bend)
    sig = signals({"max_tr": 3}, bars, tape)
    assert len(sig) == 3
    for cut in [x[0] for x in sig]:                                  # the signal AT the cut stands whatever prints from that second on
        got = signals({"max_tr": 3}, bars, garble(tape, ns("00:00") + cut * S.NS))
        assert [x for x in got if x[0] <= cut] == [x for x in sig if x[0] <= cut], cut


@pytest.mark.parametrize("tf,oc_min,x", [(1, 5, 5.0), (5, 5, 5.0), (15, 5, 5.0), (1, 15, 15.0), (5, 15, 15.0), (15, 15, 15.0), (1, 30, 30.0),
                                         (5, 30, 30.0), (15, 30, 30.0)])
def test_the_candle_is_read_at_its_end_and_never_before_from_closed_bars_only(tf, oc_min, x):
    tape, seen = tape_of(spikes()), []

    class Look(OF.OpenFvg):
        def fam_update(self, ctx):
            super().fam_update(ctx)
            seen.append((sec_of(ctx), self.och, self.ocl))

    end = OPEN + oc_min * 60
    first = -(-end // (tf * 60)) * tf * 60                           # the first tf close at or after the candle's end
    levels = []
    for t in (tape, garble(tape, ns("00:00") + end * S.NS), garble(tape, ns("00:00") + (end - 60) * S.NS)):
        seen.clear()
        run({"tf": str(tf), "oc_min": str(oc_min)}, None, Look, t)
        assert [s for s, _, _ in seen] == sorted(s for s, _, _ in seen) and any(s < first for s, _, _ in seen)
        assert all(a is None and b is None for s, a, b in seen if s < first)        # not read while the candle is still forming
        after = {(a, b) for s, a, b in seen if s >= first}
        assert len(after) == 1 and seen[-1][0] > first                               # read at that close, and kept all day
        levels.append(after.pop())
    assert levels[0] == levels[1] == (15000.0 + x, 15000.0 - x)      # every print from the candle's end on rewritten: the same two levels
    assert levels[2] != levels[0]                                    # (its own last minute rewritten: they move -- the rewrite has teeth)


# ---- (vii) the rule against an independent restatement, on random days ----------------------------------------------------------------------------------

def counting(tb, sess, och, ocl, oc_end, min_gap, tick=TICK):
    """Every counting gap of the session from the written rule alone, as (second of bar 3's close, side, near edge, far edge, structure level,
    bar 3's close). tb = the day's tf bars [(end second, o, h, l, c)]; och / ocl = the opening candle's high / low; oc_end = its end second."""
    s0, s1 = S.SESS[sess]
    atr = atr14(tb)
    out, n_in = [], 0
    for n, (end, o, h, l, c) in enumerate(tb):
        if not s0 < end <= s1:
            continue
        n_in += 1
        if n_in < 3 or och is None:
            continue
        (_, _, h1, l1, _), (end2, _, h2, l2, c2) = tb[n - 2], tb[n - 1]
        floor = max(min_gap * atr[n], tick)
        if end2 <= oc_end:                                           # bar 2 closed after the opening candle has ended
            continue
        if l > h1 and l - h1 >= floor and l2 <= och < c2:
            out.append((end, "long", l, h1, l1, c))
        elif h < l1 and l1 - h >= floor and h2 >= ocl > c2:
            out.append((end, "short", h, l1, h1, c))
    return out


def reference(tb, sess, och, ocl, oc_end, min_gap, max_tr, tick=TICK):
    """The signals a family that never places an order sees: the first max_tr counting gaps, those read before the last 5 minutes."""
    return [x[:5] for x in counting(tb, sess, och, ocl, oc_end, min_gap, tick)[:max_tr] if x[0] < S.SESS[sess][1] - 300]


def candle(bars, oc_min):
    xs = bars[570:570 + oc_min]
    return max(b[1] for b in xs), min(b[2] for b in xs)


def random_day(seed, tf, plain):
    """A seeded random-walk day from 01:00 after a flat hour. plain: 900 random minutes (few gaps on big bars). Not plain: one random bar per
    tf bar, each written tf times, so the tf bars are the random bars themselves and gaps are as common at 15 minutes as at 1."""
    return flat(60) + (rand_bars(900, seed, p0=15000.0, step=6.0) if plain else stretch(rand_bars(900 // tf, seed, p0=15000.0, step=6.0), tf))


def random_days(tf):
    return [(seed, True) for seed in (3, 11, 21, 33, 5)] + [(seed, False) for seed in range(100, 115 if tf < 15 else 220)]


SETS = ((5, 0.1, 1), (15, 0.25, 3), (30, 0.0, 2), (5, 0.5, 3), (15, 0.1, 1), (30, 0.1, 3))      # (oc_min, min_gap, max_tr)


@pytest.mark.parametrize("sess", NY)
@pytest.mark.parametrize("tf", [1, 5, 15])
def test_the_signals_equal_the_written_rule_on_random_days(sess, tf):
    n = sides = 0
    for i, (seed, plain) in enumerate(random_days(tf)):
        oc_min, min_gap, max_tr = SETS[i % len(SETS)]
        bars = random_day(seed, tf, plain)
        want = reference(tf_bars(bars, tf), sess, *candle(bars, oc_min), OPEN + oc_min * 60, min_gap, max_tr)
        got = signals({"oc_min": str(oc_min), "min_gap": min_gap, "max_tr": max_tr, "tf": str(tf), "sess": sess}, bars)
        assert got == want, (seed, plain, got[:3], want[:3])
        n += len(want)
        sides |= {"long": 1, "short": 2}.get(want[0][1], 0) if want else 0
    assert n > 5 and sides == 3, "the random days hold too few counting gaps: the comparison would be empty"


def ref_orders(bars, tf, sess, oc_min, min_gap, max_tr):
    """With a stop no print reaches and no target: the orders asked [(second, side, limit, structure level, placed)] and the one fill
    (second, side, price) or None, from the written rule and the engine's two order laws (a limit fills at its price at the first print one
    tick through it; no print fills an order in the 85 ms after it was placed -- here: the print stamped at the decision's own second).
    A filled trade stays open to 15:58, so nothing follows it. On these tapes (4 prints a minute) no order can be cancelled by a close
    beyond the far edge before it fills: that cancel is not modelled."""
    s1 = S.SESS[sess][1]
    prints = [(i * 60 + k * 15, p) for i, (o, h, l, c, v) in enumerate(bars) for k, p in enumerate((o, *((l, h) if c >= o else (h, l)), c))]

    def fill_of(t0, sd, px):
        return next((t for t, p in prints if t0 < t < s1 - 300 and (px - p) * sd >= TICK), None)

    used, log, resting = 0, [], None
    for end, side, near, far, struct, c3 in counting(tf_bars(bars, tf), sess, *candle(bars, oc_min), OPEN + oc_min * 60, min_gap):
        sd = 1 if side == "long" else -1
        if resting is not None:
            f = fill_of(*resting[:3])
            if f is not None and f < end:
                return log, (f, resting[3], resting[2])              # filled before this close: the trade is open, nothing follows
            continue                                                 # still resting at this close: not a signal, not counted
        if used >= max_tr:
            break
        used += 1
        if end >= s1 - 300:
            continue                                                 # the last 5 minutes: used, no order asked
        placed = (c3 - near) * sd > 0                                # on the passive side of the last print (bar 3's close)
        log.append((end, side, near, struct, placed))
        if placed:
            resting = (end, sd, near, side)
    if resting is not None:
        f = fill_of(*resting[:3])
        if f is not None:
            return log, (f, resting[3], resting[2])
    return log, None


@pytest.mark.parametrize("sess", NY)
@pytest.mark.parametrize("tf", [1, 5, 15])
def test_the_orders_and_the_fill_equal_the_written_rule_on_random_days(sess, tf):
    asked = fills = unplaced = second = 0
    for i, (seed, plain) in enumerate(random_days(tf)):
        oc_min, min_gap, max_tr = SETS[i % len(SETS)]
        bars = random_day(seed, tf, plain)
        want, fill = ref_orders(bars, tf, sess, oc_min, min_gap, max_tr)
        p = {"oc_min": str(oc_min), "min_gap": min_gap, "max_tr": max_tr, "tf": str(tf), "sess": sess, "stop_val": 1000.0}
        log, gone, res = play(p, bars)
        assert log == want, (seed, plain, log[:3], want[:3])
        got = [(t["entry_ms"] // 1000 - MS0 // 1000, t["side"], t["entry_price"]) for t in res.trades]
        assert got == ([fill] if fill else []), (seed, plain, got, fill)
        assert all(t["exit_ms"] >= MS0 + sec(15, 57) * 1000 for t in res.trades)               # (the stop was never reached: flat at 15:58)
        assert all(g == S.SESS[sess][1] - 300 for g in gone) and len(gone) == (1 if want and want[-1][4] and not fill else 0)
        asked += len(want)
        fills += fill is not None
        unplaced += sum(not x[4] for x in want)
        second += len(want) > 1
    assert asked > 5 and fills > 2, (asked, fills)
    if tf == 1 and sess == "nyam":
        assert unplaced > 0 and second > 0, (unplaced, second)      # (a signal without an order, and a second signal after it, did happen)


# ---- (viii) the settings and the registry -----------------------------------------------------------------------------------------------------------------

def test_the_settings_and_their_limits():
    d, sc = OF.OpenFvg.defaults(), OF.OpenFvg.schema()
    assert (d["oc_min"], d["min_gap"], d["max_tr"], d["dir"]) == ("5", 0.1, 1, "both")
    assert sc["oc_min"] == ("choice", ("5", "15", "30")) and sc["min_gap"] == ("float", 0.0, 10.0) and sc["max_tr"] == ("int", 1, 3)
    assert sc["min_gap"] == FV.Fvg.schema()["min_gap"]
    for bad in ({"oc_min": 5}, {"oc_min": "10"}, {"oc_min": "60"}, {"min_gap": -0.1}, {"min_gap": 10.5}, {"max_tr": 0}, {"max_tr": 4}, {"max_tr": 1.5},
                {"dir": "up"}, {"mode": "touch"}, {"age": 30}):
        with pytest.raises(ValueError):
            OF.OpenFvg({"tf": "5", **bad})
    for ok in ({"oc_min": "5"}, {"oc_min": "15"}, {"oc_min": "30"}, {"min_gap": 0.0}, {"min_gap": 10.0}, {"max_tr": 1}, {"max_tr": 3}, {"dir": "short"}):
        OF.OpenFvg({"tf": "5", **ok})


def test_the_registry_holds_open_fvg_as_written_and_it_is_a_block():
    assert families.ERRORS == {}
    cls, inputs, both, notes = families.REGISTRY["open_fvg"]
    lib = families.library("open_fvg")
    assert cls is OF.OpenFvg and inputs == {} and both is False and cls.FEATURES == () and cls.SCREEN_TFS == ("1", "5", "15")
    assert cls.SCREEN_RUN == {"strict_limit": True} == FV.Fvg.SCREEN_RUN                 # limit entries: a fill print through the stop is a loss
    assert families.MODULE_OF["open_fvg"] == "open_fvg" and lib["roots"] == ("NQ", "ES", "GC") and not lib["l2"] and not lib["weak"]
    assert lib["mirror"] is None and lib["complexity"] == 9 and lib["variants"] == [{"oc_min": "5"}, {"oc_min": "15"}, {"oc_min": "30"}]
    assert len(lib["rationale"]) > 60 and "opening candle" in lib["rationale"] and "opening candle" in notes and "near edge" in notes
    from families import blocks as B
    assert issubclass(B.WRAPPED["open_fvg"], OF.OpenFvg) and B.BASES["open_fvg"][0] is OF.OpenFvg and B.B_open_fvg is B.WRAPPED["open_fvg"]
    with pytest.raises(ValueError):
        B.WRAPPED["open_fvg"]({"tf": "5", "stop_mode": "rng"})        # the family has no structure height: only the standard table's stops
    assert B.WRAPPED["open_fvg"]({"tf": "5", "stop_mode": "struct"}).p["oc_min"] == "5"
    for s in RM.DAY_PASSES:
        assert cls({"tf": "5", "sess": s, "hold_to": "day"}).sessions() == ([s] if s in NY else [])


# ---- (ix) real BUILD days: the rule from the raw prints, and the invariants of the code check, at 1 worker -------------------------------------------------

def real_minutes(tape):
    """The minute bars of 00:00 .. 16:10 ET built here from the raw prints: [(minute index from 00:00, o, h, l, c)], printed minutes only."""
    t0, t1 = S.et_ns(tape.date, "00:00"), S.et_ns(tape.date, "16:10")
    m = (tape.ts >= t0) & (tape.ts < t1)
    k, px = (tape.ts[m] - t0) // (60 * S.NS), tape.px[m]
    st = np.flatnonzero(np.concatenate(([True], k[1:] != k[:-1])))
    en = np.concatenate((st[1:], [len(px)]))
    return list(zip(k[st].tolist(), px[st].tolist(), np.maximum.reduceat(px, st).tolist(), np.minimum.reduceat(px, st).tolist(), px[en - 1].tolist()))


def real_tf(mins, tf):
    """The tf bars (clock multiples, printed ones only) of real_minutes: [(end second, o, h, l, c)]."""
    out = []
    for i, o, h, l, c in mins:
        k = i // tf
        if out and out[-1][0] == k:
            out[-1][2:] = [max(out[-1][2], h), min(out[-1][3], l), c]
        else:
            out.append([k, o, h, l, c])
    return [((k + 1) * tf * 60, o, h, l, c) for k, o, h, l, c in out]


class Clock(Sig):
    """Sig that logs the CLOCK close of the signal bar (a real tf bar whose last minute had no print is handed over a little later)."""

    def fam_signal(self, ctx):
        if self.gap is not None:
            type(self).seen.append(((self.M[-1][0] // (self.tf * 60) + 1) * self.tf * 60, *self.gap))


@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_the_signals_on_real_build_days_equal_the_rule_restated_from_the_raw_prints(root):
    real_days()
    tick, n, sides = S.SPECS[root][1], 0, set()
    tapes = [S.load_tape(d, root) for d in days_of(root, 4)]
    days = [(t, real_minutes(t)) for t in tapes]
    for oc_min in (5, 15, 30):
        for tf in (1, 5, 15):
            for sess in NY:
                for min_gap, max_tr in ((0.1, 3), (0.5, 1)):
                    cls = type("Clock", (Clock,), {"seen": []})
                    st = cls({**BASE, "tf": str(tf), "sess": sess, "oc_min": str(oc_min), "min_gap": min_gap, "max_tr": max_tr})
                    st.ROLLS = frozenset()
                    for tape, mins in days:                          # ONE instance through the days in order: nothing of a day is left for the next
                        xs = [b for b in mins if 570 <= b[0] < 570 + oc_min]
                        och, ocl = max(b[2] for b in xs), min(b[3] for b in xs)
                        want = reference(real_tf(mins, tf), sess, och, ocl, OPEN + oc_min * 60, min_gap, max_tr, tick)
                        cls.seen.clear()
                        S.run_session(st, tape, daily=list(DAILY), on_error="raise")
                        assert cls.seen == want, (root, tape.date, oc_min, tf, sess, min_gap, cls.seen[:2], want[:2])
                        assert (st.och, st.ocl) == (och, ocl)
                        n += len(want)
                        sides |= {x[1] for x in want}
    assert n > 20 and sides == {"long", "short"}, (n, sides)


@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_real_build_days_hold_the_window_one_position_and_the_flat_time(root):
    real_days()
    days = days_of(root, 4)
    hd = {"hold_to": "day", "stop_mode": "atr", "stop_val": 1.5, "tgt_r": 2.0}
    specs = [(OF.OpenFvg, {**hd, "tf": tf, "sess": s, "oc_min": o, "max_tr": m}) for tf in ("1", "5") for s in NY for o in ("5", "15") for m in (1, 3)]
    out = S.run_many(specs, root=root, days=days, period="build", workers=1, on_error="raise", **OF.OpenFvg.SCREEN_RUN)
    again = S.run_many(specs, root=root, days=days, period="build", workers=1, on_error="raise", **OF.OpenFvg.SCREEN_RUN)
    assert [r["trades"] for r in out] == [r["trades"] for r in again]
    assert sum(r["skipped_by_error"] for r in out) == 0 and sum(r["both_sides_sessions"] for r in out) == 0
    total = 0
    for (cls, p), r in zip(specs, out):
        s0, s1 = S.SESS[p["sess"]]
        last, per_day = {}, {}
        for t in sorted(r["trades"], key=lambda t: t["entry_ms"]):
            d = S._date(t["date"])
            es = (t["entry_ms"] // 1000) - S.et_ns(d, "00:00") // S.NS
            assert s0 + 3 * int(p["tf"]) * 60 <= es < s1 - 300, (p, t["date"], es)     # a limit fills while it rests: after bar 3's close, before the last 5 minutes
            assert t["entry_price"] == t["order_price"] and not t["oco"]              # ... and at its own price
            assert t["exit_ms"] <= S.et_ns(d, S.day_flat(d, root)) // 1_000_000 + 60_000
            assert last.get(t["date"], 0) <= t["entry_ms"]                            # one position at a time
            last[t["date"]] = t["exit_ms"]
            per_day[t["date"]] = per_day.get(t["date"], 0) + 1
            total += 1
        assert all(v <= p["max_tr"] for v in per_day.values())                        # max_tr signals a session: never more trades
    assert total > 0
    # max_tr 1: the trades of dir long and of dir short are together the trades of dir both
    key = lambda r: sorted((t["date"], t["side"], t["entry_ms"], t["exit_ms"], t["entry_price"], t["exit_price"]) for t in r["trades"])  # noqa: E731
    sp = [(OF.OpenFvg, {**hd, "tf": tf, "sess": s, "dir": d}) for tf in ("1", "5") for s in NY for d in ("both", "long", "short")]
    res = S.run_many(sp, root=root, days=days, period="build", workers=1, on_error="raise", **OF.OpenFvg.SCREEN_RUN)
    for i in range(0, len(sp), 3):
        assert key(res[i]) == sorted(key(res[i + 1]) + key(res[i + 2])), sp[i][1]
        assert {t["side"] for t in res[i + 1]["trades"]} <= {"long"} and {t["side"] for t in res[i + 2]["trades"]} <= {"short"}
