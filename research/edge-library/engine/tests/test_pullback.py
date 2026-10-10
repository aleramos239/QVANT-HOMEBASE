"""PULLBACK: the `pullback` entry trigger (families/pullback.py), a limit order part of the way back into a swing leg, written from its rule.

THE RULE UNDER TEST (the owner's request of 2026-10-10; traders call it the optimal trade entry or a Fibonacci pullback):
    swing bars = sfp's: bars of `swing` minutes (15 | 30 | 60) on clock multiples, made of the day's own 1-minute bars; only ENDED bars count
    swing high = a swing bar whose high is strictly above the highs of the bar before it and the bar after it; KNOWN once the bar after it ended
    UP LEG     = a newly known swing high H strictly above the swing high known before it; its START = the lowest low of the swing bars after
                 that earlier swing high up to and including H's bar. DOWN LEG = the mirror. The latest leg replaces any earlier one.
    PRICE      = H - level x (H - start), rounded to the tick toward the start (the mirror for a down leg)
    LIVE       = a leg is live from the close it becomes known until: its order fills (one entry a leg); a bar trades beyond H; a bar AFTER
                 the bar that made H (the first of them) trades at or beyond the price while no order of the leg works (the pullback
                 happened without us: also before the leg was known, outside the session, while another trade was open); a newer leg comes.
    ORDER      = while a leg is live and has no working order, a LIMIT with the leg at that price is asked for at every close inside the
                 session (the Template decides). The leg's start goes with the order as its structure level.
    entries inside the idea's session, up to max_tr a session, one position at a time; flat 15:58.
Synthetic days with EXACT numbers cover each behaviour (a quiet day at 15000 with single minutes changed and the quiet price stepped; every
up-leg case is also run upside down as a down leg); seeded random days check the live leg and the first trade of a day against an independent
restatement of the rule at every bar size, session, swing size and level; the swing lines are compared with sfp's, which they restate; the
real BUILD days check the invariants (window, one position, flat 15:58) at 1 worker. No net, win rate or profit factor is read.
"""
import datetime as dt
import math
from fractions import Fraction

import numpy as np
import pytest

import families
import l2sim as S
import run_menus as RM
from families import pullback as PB
from families import sfp as SF
from test_blocks import D, DAILY, TICK, days_of, garble, minute_tape, ns, rand_bars, real_days

BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 1000.0, "tgt_r": 0.0, "max_tr": 5, "swing": "15", "level": 0.5}
PX = 15000.0
LAT = 85 * 10**6                                    # the engine's order delay, ns


def sec(h, m=0, s=0):
    return h * 3600 + m * 60 + s


def q(b):
    """A quiet minute at b: it opens and closes there, one tick up, never below."""
    return (b, b + TICK, b, b, 40)


def hi(px, c=None):
    """A minute that trades up to px (and closes at c, else back at the quiet price)."""
    return lambda b: (b, px, b, b if c is None else c, 40)


def lo(px, c=None):
    """A minute that trades down to px."""
    return lambda b: (b, b + TICK, px, b if c is None else c, 40)


def seg(n, edits=None, steps=None, t0="00:00", base=PX):
    """n minute bars from t0, quiet at `base`; steps {"09:30": 15015.0} moves the quiet price from that minute on; edits {"09:35": hi(15020.0)}
    changes single minutes."""
    first = S._sec(t0) // 60
    at = lambda t: (S._sec(t) // 60 - first) % 1440  # noqa: E731
    ed, st = {at(t): f for t, f in (edits or {}).items()}, {at(t): v for t, v in (steps or {}).items()}
    assert all(0 <= k < n for k in list(ed) + list(st))
    out = []
    for i in range(n):
        base = st.get(i, base)
        out.append(ed[i](base) if i in ed else q(base))
    return out


def mirror(bars):
    """The same bars upside down around 15000: every up leg becomes a down leg."""
    return [(2 * PX - o, 2 * PX - l, 2 * PX - h, 2 * PX - c, v) for o, h, l, c, v in bars]


def day(edits=None, steps=None, flip=False):
    """A full day of minute bars from 00:00 ET to 15:59 (seg); flip = upside down."""
    b = seg(960, edits, steps)
    return mirror(b) if flip else b


def mp(px, flip):
    return 2 * PX - px if flip else px


def sd(flip):
    return "short" if flip else "long"


@pytest.fixture(params=[False, True], ids=["up", "down"])
def flip(request):
    return request.param


def tape_of(bars):
    return minute_tape(bars, "00:00")


def sec_of(ctx):
    return (ctx.now_ns - ns("00:00")) // S.NS


def side_of(s):
    return "long" if s > 0 else "short"


def run(params, bars, cls=None, tape=None, **kw):
    """One instance through one day (the explicit roll list: none). -> (the instance, the result)."""
    st = (cls or PB.Pullback)({**BASE, **params})
    st.ROLLS = frozenset()
    res = S.run_session(st, tape or tape_of(bars), daily=list(DAILY), on_error="raise", **kw)
    return st, res


class Spy(PB.Pullback):
    """Logs every order the family asks for: (ns of the decision, side, price, the structure level, an order was placed)."""
    log: list = []

    def _lim(self, ctx, side, px, **kw):
        o = super()._lim(ctx, side, px, **kw)
        type(self).log.append((ctx.now_ns, side, px, kw.get("struct"), o is not None))
        return o


def orders(params, bars, tape=None, raw=False, **kw):
    """[(second of the decision, side, price, structure level, placed)] of one day."""
    cls = type("Spy", (Spy,), {"log": []})
    run(params, bars, cls, tape, **kw)
    return list(cls.log) if raw else [((t - ns("00:00")) // S.NS, *x) for t, *x in cls.log]


def trades(params, bars, tape=None, **kw):
    return sorted(run(params, bars, None, tape, **kw)[1].trades, key=lambda t: t["entry_ms"])


def minute(t):
    """The minute of the day a trade entered in, as seconds after 00:00 ET."""
    return (t["entry_ms"] - ns("00:00") // 1_000_000) // 60_000 * 60


def watch(params, bars, tape=None, **kw):
    """The live leg after every tf close of the day, in and out of the session -> (every close as (second, None | (side, price, start)),
    every leg at the close it became live as (second, side, price, start))."""
    seen, born = [], []

    class Look(PB.Pullback):
        def fam_day(self, ctx):
            super().fam_day(ctx)
            self.was = None

        def fam_update(self, ctx):
            super().fam_update(ctx)
            g = self.leg
            row = None if g is None else (side_of(g[0]), g[2], g[3])
            seen.append((sec_of(ctx), row))
            if g is not None and g is not self.was:
                born.append((sec_of(ctx), *row))
            self.was = g

    run(params, bars, Look, tape, **kw)
    return seen, born


def closes(params, bars, tape=None, **kw):
    """The live leg at every tf close of the day: [(second, None | (side, price, start))]."""
    return watch(params, bars, tape, **kw)[0]


def legs(params, bars, tape=None, **kw):
    """Every leg that became live, all day: [(second it became known, side, price, start)]."""
    return watch(params, bars, tape, **kw)[1]


def live(params, bars, at, tape=None, **kw):
    """The live leg after the tf close at second `at` (None = no leg is live)."""
    return dict(closes(params, bars, tape, **kw))[at]


class Sig(PB.Pullback):
    """Logs every order the family asks for inside its session and places none (so no order ever works and no trade blocks the next):
    (second, side, price, start) at every close a leg is live."""
    seen: list = []

    def fam_signal(self, ctx):
        g = self.leg
        if g is not None:
            type(self).seen.append((sec_of(ctx), side_of(g[0]), g[2], g[3]))


def wants(params, bars, tape=None, **kw):
    cls = type("Sig", (Sig,), {"seen": []})
    run(params, bars, cls, tape, **kw)
    return list(cls.seen)


def resting(params, bars, tape=None, **kw):
    """The prices of the entry orders that work after every tf close: {second: (price, ...)} (the last close of a second wins)."""
    seen = {}

    class Look(PB.Pullback):
        def _close(self, ctx):
            super()._close(ctx)
            seen[sec_of(ctx)] = tuple(r[0].price for r in self.orders if r[0].status == "working")

    run(params, bars, Look, tape, **kw)
    return seen


def trendy(n, seed, scale=1, p0=PX):
    """A seeded day of n minute bars on the tick grid made of legs and pullbacks: a run of 20 to 45 minutes one way, 16 to 36 minutes in which
    it stalls (the swing gets known) and a pullback of 10 to 30 minutes, again and again; the side turns every few rounds. scale 2 / 4 makes
    the rounds 2 / 4 times as long and as slow (for the 30- and 60-minute swings). A plain random walk seldom leaves a leg standing."""
    g = np.random.default_rng(seed)
    out, o, plan, side, rounds = [], p0, [], 1.0, 0
    while len(out) < n:
        if not plan:
            if rounds == 0:
                side, rounds = -side if g.random() < 0.7 else side, int(g.integers(2, 6))
            rounds -= 1
            plan = [[int(g.integers(20, 45)) * scale, side * float(g.uniform(1.5, 3.0)) / scale],
                    [int(g.integers(16, 36)) * scale, side * float(g.uniform(-0.15, 0.15)) / scale],
                    [int(g.integers(10, 30)) * scale, -side * float(g.uniform(1.0, 2.5)) / scale]]
        plan[0][0] -= 1
        drift = plan[0][1]
        if plan[0][0] <= 0:
            plan.pop(0)
        c = o + round((drift + float(g.normal(0, 1.0))) / TICK) * TICK
        h = max(o, c) + int(g.integers(0, 5)) * TICK
        l = min(o, c) - int(g.integers(0, 5)) * TICK
        out.append((o, h, l, c, 40))
        o = c
    return out


# THE BASE DAY. Quiet at 15000; the 09:00 swing bar holds a swing high of 15010 (known 09:30); from 09:30 the quiet price is 15015 and the
# 09:30 swing bar holds a swing high of 15020 (known 10:00): a higher high. The leg: H 15020, start 15000 (the lowest low of the swing bars
# 09:15 and 09:30), half way back = 15010. Nothing since 09:30 has traded at 15010, so at 10:00 a buy limit rests at 15010.
E0, S0 = {"09:05": hi(15010.0), "09:35": hi(15020.0)}, {"09:30": 15015.0}


def base(edits=None, steps=None, flip=False):
    return day({**E0, **(edits or {})}, {**S0, **(steps or {})}, flip)


# ---- (i) the leg, its start and the entry price ---------------------------------------------------------------------------------------------------

def test_a_higher_swing_high_rests_a_buy_limit_half_way_back_and_the_mirror_a_sell_limit(flip):
    assert orders({}, base(flip=flip)) == [(sec(10), sd(flip), mp(15010.0, flip), 15000.0, True)]
    assert legs({}, base(flip=flip)) == [(sec(10), sd(flip), mp(15010.0, flip), 15000.0)]
    assert trades({}, base(flip=flip)) == []                                           # no pullback, no trade
    tr = trades({}, base({"10:05": lo(15009.75)}, flip=flip))                          # one tick through the limit: filled at its price
    assert [(minute(t), t["side"], t["entry_price"], t["order_price"]) for t in tr] == [(sec(10, 5), sd(flip), mp(15010.0, flip), mp(15010.0, flip))]


def test_the_level_sets_the_depth_and_the_price_is_rounded_to_the_tick_toward_the_start(flip):
    # the leg is 20 points: 0.62 back = 15007.6 -> 15007.5 (down, toward the start); 0.79 back = 15004.2 -> 15004.0; upside down 14992.4 -> 14992.5
    for level, px in ((0.5, 15010.0), (0.62, 15007.5), (0.79, 15004.0), (0.4, 15012.0), (0.9, 15002.0)):
        assert orders({"level": level}, base(flip=flip)) == [(sec(10), sd(flip), mp(px, flip), 15000.0, True)], level
    assert PB.Pullback.defaults()["level"] == 0.62


def test_entry_price_is_exact_on_the_tick_grid_of_each_market():
    f = PB.entry_price
    assert f(1, 15020.0, 15000.0, 0.5, 0.25) == 15010.0 and f(-1, 14980.0, 15000.0, 0.5, 0.25) == 14990.0
    assert f(1, 15020.0, 15000.0, 0.62, 0.25) == 15007.5 and f(-1, 14980.0, 15000.0, 0.62, 0.25) == 14992.5
    assert f(1, 4000.0, 3990.25, 0.5, 0.25) == 3995.0 and f(-1, 3990.25, 4000.0, 0.5, 0.25) == 3995.25       # 3995.125: down for a buy, up for a sell
    # gold's tick (0.1) is no binary number: a price that IS on the grid must stay on it, on either side
    assert f(1, 2000.5, 2000.3, 0.5, 0.1) == 2000.4 and f(-1, 2000.3, 2000.5, 0.5, 0.1) == 2000.4
    assert f(1, 2000.5, 1990.5, 0.62, 0.1) == 1994.3 and f(-1, 1990.5, 2000.5, 0.62, 0.1) == 1996.7
    n = 0
    for tick in (0.25, 0.1):
        for a in range(0, 400, 7):
            for b in range(a + 1, a + 300, 11):
                for level in ("0.25", "0.5", "0.62", "0.79", "0.9"):
                    lo_, hi_ = Fraction(20000) + a * Fraction(str(tick)), Fraction(20000) + b * Fraction(str(tick))
                    x = hi_ - Fraction(level) * (hi_ - lo_)
                    want = math.floor(x / Fraction(str(tick))) * Fraction(str(tick))
                    got = f(1, float(hi_), float(lo_), float(level), tick)
                    assert abs(got - float(want)) < 1e-9, (tick, a, b, level)
                    y = lo_ + Fraction(level) * (hi_ - lo_)
                    want = math.ceil(y / Fraction(str(tick))) * Fraction(str(tick))
                    assert abs(f(-1, float(lo_), float(hi_), float(level), tick) - float(want)) < 1e-9, (tick, a, b, level)
                    assert float(lo_) - 1e-9 <= got <= float(hi_) + 1e-9                  # never beyond the leg
                    n += 1
    assert n > 10000


def test_the_start_is_the_lowest_low_after_the_earlier_swing_high(flip):
    # a low of 14990 in the swing bar between the two swing highs: the leg is 30 points, half way back = 15005
    assert orders({}, base({"09:20": lo(14990.0)}, flip=flip)) == [(sec(10), sd(flip), mp(15005.0, flip), mp(14990.0, flip), True)]
    # the same low in the earlier swing high's own bar, or before it, is not the leg's
    assert orders({}, base({"09:10": lo(14990.0)}, flip=flip)) == [(sec(10), sd(flip), mp(15010.0, flip), 15000.0, True)]
    assert orders({}, base({"08:50": lo(14990.0)}, flip=flip)) == [(sec(10), sd(flip), mp(15010.0, flip), 15000.0, True)]
    # ... and so is a low after H's own bar (it is above the entry price here, so the order is placed)
    assert orders({}, base({"09:50": lo(15012.0)}, flip=flip)) == [(sec(10), sd(flip), mp(15010.0, flip), 15000.0, True)]


def test_the_swing_high_must_be_strictly_above_the_one_before_it(flip):
    one = lambda px: day({"09:05": hi(15010.0), "09:35": hi(px)}, {"09:30": 15008.0}, flip)  # noqa: E731
    assert legs({"level": 0.79}, one(15010.25)) == [(sec(10), sd(flip), mp(15002.0, flip), 15000.0)]       # one tick higher: a leg
    assert legs({"level": 0.79}, one(15010.0)) == [] and legs({"level": 0.79}, one(15009.0)) == []           # equal, lower: none


def test_the_first_swing_high_of_the_day_makes_no_leg(flip):
    assert legs({}, day({"09:35": hi(15020.0)}, S0, flip)) == []
    assert legs({}, base(flip=flip)) != []


def test_a_lower_swing_high_makes_no_leg_and_is_the_one_the_next_is_compared_with(flip):
    # swing highs 15010 (08:30 bar), 15005 (09:00 bar: lower, no leg), 15008 (09:30 bar): above 15005, the one known before it -> a leg
    g = day({"08:35": hi(15010.0), "09:05": hi(15005.0), "09:35": hi(15008.0)}, {"09:30": 15006.0}, flip)
    assert legs({}, g) == [(sec(10), sd(flip), mp(15004.0, flip), 15000.0)]
    # without the 15005 swing in between, 15008 is below the swing high before it (15010): no leg
    assert legs({}, day({"08:35": hi(15010.0), "09:35": hi(15008.0)}, {"09:30": 15006.0}, flip)) == []


def test_a_bar_that_is_a_higher_high_and_a_lower_low_at_once_is_no_order_and_replaces_the_leg_before_it(flip):
    # london. 03:35 a swing high of 14905 at a quiet 14900; from 04:00 the price is 15045 with a swing high of 15050 (known 04:30): a leg from
    # 14900, half way back 14975 -- a buy limit that rests far below all day. From 04:30 the price is 15015: a swing high of 15016 (04:45 bar,
    # lower: no leg) and the day's first swing low, 15014 (05:15 bar). The bars 05:45 and 06:00 both trade 14990 .. 15040: equal neighbours, so
    # no swing, but they are the extremes since those two swings. Then the 06:30 bar trades 15010 .. 15020 between quiet bars: a higher swing
    # high (above 15016) AND a lower swing low (under 15014), known at 07:00. Each alone would be a leg with an order (a buy at 15005 from the
    # 14990 low, a sell at 15025 from the 15040 high; the bar itself stayed between the two prices). Together: no order, and the 04:30 leg's
    # order is gone.
    wide = lambda b: (b, 15040.0, 14990.0, b, 40)  # noqa: E731
    e = {"03:35": hi(14905.0), "04:05": hi(15050.0), "04:50": hi(15016.0), "05:20": lo(15014.0), "05:50": wide, "06:05": wide}
    st = {"00:00": 14900.0, "04:00": 15045.0, "04:30": 15015.0}
    p = {"sess": "london"}
    first = (sec(4, 30), sd(flip), mp(14975.0, flip), mp(14900.0, flip))
    g = day({**e, "06:35": lambda b: (b, 15020.0, 15010.0, b, 40)}, st, flip)
    assert legs(p, g) == [first] and orders(p, g) == [(*first, True)]
    r = resting(p, g)
    assert r[sec(6, 59)] == (mp(14975.0, flip),) and all(r[s] == () for s in r if s >= sec(7))
    # the two halves of that bar, each on its own day, are the two legs
    up, dn = day({**e, "06:35": hi(15020.0)}, st, flip), day({**e, "06:35": lo(15010.0)}, st, flip)
    assert legs(p, up) == [first, (sec(7), sd(flip), mp(15005.0, flip), mp(14990.0, flip))]
    assert legs(p, dn) == [first, (sec(7), sd(not flip), mp(15025.0, flip), mp(15040.0, flip))]


# ---- (ii) the pullback happened without us: the bars AFTER the bar that made the high -------------------------------------------------------------------

def leg0(flip, at=None):
    """The base day's leg as legs() shows it."""
    return (sec(10) if at is None else at, sd(flip), mp(15010.0, flip), 15000.0)


def test_a_bar_at_or_beyond_the_entry_price_after_the_high_and_before_the_leg_is_known_kills_it(flip):
    # in the swing bar after H's: exactly at the price = nothing; one tick short of it = the order
    assert legs({}, base({"09:50": lo(15010.0)}, flip=flip)) == [] and orders({}, base({"09:50": lo(15010.0)}, flip=flip)) == []
    assert legs({}, base({"09:50": lo(15009.0)}, flip=flip)) == []
    assert legs({}, base({"09:50": lo(15010.25)}, flip=flip)) == [leg0(flip)]
    # in H's own swing bar, the minute after the one that made the high (09:35): it counts too
    assert legs({}, base({"09:36": lo(15010.0)}, flip=flip)) == [] and legs({}, base({"09:36": lo(15010.25)}, flip=flip)) == [leg0(flip)]
    # the level decides: the same day asks for 15015 at level 0.25, where the price has been since 09:30
    assert legs({"level": 0.25}, base(flip=flip)) == []
    assert legs({"level": 0.25}, base({}, {"09:30": 15016.0}, flip)) == [(sec(10), sd(flip), mp(15015.0, flip), 15000.0)]
    # a leg that gave nothing is not offered when the price comes back later
    assert trades({}, base({"09:50": lo(15010.0), "10:10": lo(15005.0)}, flip=flip)) == []


def test_the_bars_up_to_the_one_that_made_the_high_do_not_count(flip):
    # a dip to the entry price EARLIER in H's own swing bar (09:32, the high comes at 09:35) is part of the rise: a leg like any other
    assert orders({}, base({"09:32": lo(15010.0)}, flip=flip)) == [(*leg0(flip), True)]
    # ... also when that dip is the leg's own start: the leg rose inside H's own swing bar, from 14990 to 15020; half way back = 15005
    g = base({"09:32": lo(14990.0), "10:05": lo(15004.75)}, flip=flip)
    assert orders({}, g) == [(sec(10), sd(flip), mp(15005.0, flip), mp(14990.0, flip), True)]
    assert [(minute(t), t["entry_price"]) for t in trades({}, g)] == [(sec(10, 5), mp(15005.0, flip))]
    # the last minute before H's swing bar began (the leg's start, 14999, lies in the 09:15 bar)
    assert legs({}, base({"09:29": lo(14999.0)}, flip=flip)) == [(sec(10), sd(flip), mp(15009.5, flip), mp(14999.0, flip))]


def test_the_bar_that_made_the_high_is_a_bar_of_the_idea_s_own_size(flip):
    # the high is made at 09:35. A dip to the entry price at 09:37 is AFTER the 1-minute bar that made it, but INSIDE the 5-minute bar
    # (09:35-09:40) and the 15-minute bar (09:30-09:45) that made it: the bar itself is not counted (what came first inside it is unknown)
    g = base({"09:37": lo(15010.0)}, flip=flip)
    assert legs({"tf": "1"}, g) == [] and legs({"tf": "5"}, g) == [leg0(flip)] and legs({"tf": "15"}, g) == [leg0(flip)]
    g = base({"09:40": lo(15010.0)}, flip=flip)                                        # the next 5-minute bar
    assert legs({"tf": "1"}, g) == [] and legs({"tf": "5"}, g) == [] and legs({"tf": "15"}, g) == [leg0(flip)]
    g = base({"09:45": lo(15010.0)}, flip=flip)                                        # the next 15-minute bar
    assert legs({"tf": "1"}, g) == [] and legs({"tf": "5"}, g) == [] and legs({"tf": "15"}, g) == []


def test_of_several_bars_at_the_high_the_first_one_counts(flip):
    two = {"09:41": hi(15020.0)}                                                       # 09:35 and 09:41 both trade 15020
    assert legs({}, base({**two, "09:38": lo(15010.0)}, flip=flip)) == []              # a dip between them is after the FIRST: it counts
    assert legs({}, base({**two, "09:38": lo(15010.25)}, flip=flip)) == [leg0(flip)]
    assert legs({}, base({**two, "09:33": lo(15010.0)}, flip=flip)) == [leg0(flip)]    # ... and one before the first does not
    # the first bar at the high INSIDE H's own swing bar: an older bar at the very same price (08:35, an earlier swing high) is not it
    assert legs({}, base({"08:35": hi(15020.0)}, flip=flip)) == [leg0(flip)]


# ---- (iii) the life of the order ---------------------------------------------------------------------------------------------------------------------

def test_the_limit_fills_only_on_a_trade_through_and_the_leg_s_start_is_its_structure_level(flip):
    touch = base({"10:05": lo(15010.0)}, flip=flip)                                    # a print AT the limit is no fill (the engine's limit law)
    assert trades({}, touch) == [] and resting({}, touch)[sec(10, 30)] == (mp(15010.0, flip),)
    tr = trades({"stop_mode": "struct", "tgt_r": 1.0}, base({"10:05": lo(15009.75)}, flip=flip))
    assert len(tr) == 1 and (tr[0]["side"], tr[0]["entry_price"], tr[0]["sl"], tr[0]["tp"]) == (sd(flip), mp(15010.0, flip), 15000.0, mp(15020.0, flip))
    assert orders({"level": 0.79}, base(flip=flip))[0][3] == 15000.0 and orders({}, base({"09:20": lo(14990.0)}, flip=flip))[0][3] == mp(14990.0, flip)


def test_a_bar_beyond_h_cancels_the_order_and_a_touch_of_h_does_not(flip):
    grow = base({"10:05": hi(15020.25), "10:10": lo(15009.75)}, flip=flip)             # one tick above H at 10:05, then the pullback
    r = resting({}, grow)
    assert r[sec(10)] == r[sec(10, 5)] == (mp(15010.0, flip),) and all(r[s] == () for s in r if s >= sec(10, 6))
    assert trades({}, grow) == [] and len(orders({}, grow)) == 1
    touch = base({"10:05": hi(15020.0), "10:10": lo(15009.75)}, flip=flip)
    assert resting({}, touch)[sec(10, 10)] == (mp(15010.0, flip),) and [minute(t) for t in trades({}, touch)] == [sec(10, 10)]
    # the bar decides at its close: a 5-minute idea cancels at 10:10, and the pullback at 10:08 (inside the bar that went beyond H) still fills
    late = base({"10:06": hi(15020.25), "10:08": lo(15009.75)}, flip=flip)
    assert [minute(t) for t in trades({"tf": "5"}, late)] == [sec(10, 8)] and trades({}, late) == []


def test_after_the_cancel_a_new_leg_comes_when_the_next_swing_is_known(flip):
    # from 10:00 the quiet price is 15022 (above H 15020: the first order goes at the 10:01 close) and 10:05 makes a swing high of 15025, known
    # 10:30: a leg from 15015 (the lowest low since the 09:30 swing high) to 15025, half way back = 15020
    g = base({"10:05": hi(15025.0)}, {"10:00": 15022.0}, flip)
    assert orders({}, g) == [(sec(10), sd(flip), mp(15010.0, flip), 15000.0, True), (sec(10, 30), sd(flip), mp(15020.0, flip), mp(15015.0, flip), True)]
    r = resting({}, g)
    assert r[sec(10)] == (mp(15010.0, flip),) and all(r[s] == () for s in r if sec(10, 1) <= s < sec(10, 30)) and r[sec(10, 30)] == (mp(15020.0, flip),)


def test_a_newer_leg_of_the_other_side_replaces_the_order(flip):
    # the buy limit rests at 15010 with the price at 15015. Swing lows of 15013 (09:45 bar, known 10:15) and 15011 (10:15 bar, known 10:45): a
    # lower low = a DOWN leg from 15015.25 (the highest high since the 15013 low) to 15011; half way back 15013.125 -> 15013.25 (up, toward the start)
    e = {"09:50": lo(15013.0), "10:20": lo(15011.0)}
    g = base(e, {"10:15": 15012.0}, flip)
    other = sd(not flip)
    assert orders({}, g) == [(sec(10), sd(flip), mp(15010.0, flip), 15000.0, True), (sec(10, 45), other, mp(15013.25, flip), mp(15015.25, flip), True)]
    r = resting({}, g)
    assert r[sec(10, 44)] == (mp(15010.0, flip),) and r[sec(10, 45)] == (mp(15013.25, flip),)
    tr = trades({}, base({**e, "10:50": hi(15013.5)}, {"10:15": 15012.0}, flip))       # one tick through the new limit
    assert [(minute(t), t["side"], t["entry_price"]) for t in tr] == [(sec(10, 50), other, mp(15013.25, flip))]
    # a newer leg that gives no order itself (the price stayed at 15015: it has been at 15013.25 already) replaces the old order all the same
    g = base({**e, "10:50": lo(15009.75)}, flip=flip)
    assert len(orders({}, g)) == 1 and trades({}, g) == [] and resting({}, g)[sec(10, 44)] == (mp(15010.0, flip),) and resting({}, g)[sec(10, 45)] == ()


def test_a_swing_that_makes_no_leg_leaves_the_order_alone(flip):
    g = base({"10:05": hi(15018.0), "10:40": lo(15009.75)}, flip=flip)                 # a lower swing high (known 10:30): no leg
    assert len(orders({}, g)) == 1 and resting({}, g)[sec(10, 35)] == (mp(15010.0, flip),)
    assert [(minute(t), t["entry_price"]) for t in trades({}, g)] == [(sec(10, 40), mp(15010.0, flip))]
    g = base({"10:05": lo(15012.0), "10:40": lo(15009.75)}, flip=flip)                 # the first swing low of the day (known 10:30): no leg
    assert [(minute(t), t["entry_price"]) for t in trades({}, g)] == [(sec(10, 40), mp(15010.0, flip))]


def test_the_order_goes_in_the_last_five_minutes_of_the_session_and_the_leg_lives_on(flip):
    assert [minute(t) for t in trades({}, base({"10:54": lo(15009.75)}, flip=flip))] == [sec(10, 54)]
    late = base({"10:55": lo(15009.75), "11:20": lo(15009.75)}, flip=flip)
    assert trades({}, late) == [] and resting({}, late)[sec(10, 54)] == (mp(15010.0, flip),) and resting({}, late)[sec(10, 56)] == ()
    # the Template's cancel does not end the leg by itself ...
    assert live({}, base(flip=flip), sec(10, 58)) == leg0(flip)[1:] and len(orders({}, base(flip=flip))) == 1
    # ... a bar at the entry price does, now that no order works (10:57; the 10:55 minute itself is such a bar too)
    g = base({"10:57": lo(15010.0)}, flip=flip)
    assert live({}, g, sec(10, 57)) == leg0(flip)[1:] and live({}, g, sec(10, 58)) is None
    assert live({}, late, sec(10, 55)) == leg0(flip)[1:] and live({}, late, sec(10, 56)) is None
    # while the order works, a bar AT the price (no fill: the limit needs one tick through) leaves the leg alone
    g = base({"10:20": lo(15010.0)}, flip=flip)
    assert live({}, g, sec(10, 30)) == leg0(flip)[1:] and resting({}, g)[sec(10, 30)] == (mp(15010.0, flip),)


def test_a_leg_that_outlives_a_session_gets_its_order_in_the_next_one(flip):
    # one instance that trades every session of the day in turn (the tester's own way, hold_to = session): the morning's order is cancelled at
    # 10:55, the leg is still live, and the midday session's first close (11:01) places it again
    p = {"sess": "all", "hold_to": "session"}
    g = base({"11:20": lo(15009.75)}, flip=flip)
    assert orders(p, g) == [(*leg0(flip), True), (*leg0(flip, sec(11, 1)), True)]
    assert [(minute(t), t["entry_price"]) for t in trades(p, g)] == [(sec(11, 20), mp(15010.0, flip))]
    # ... unless the price got there in between, with no order working
    g = base({"10:57": lo(15010.0), "11:20": lo(15009.75)}, flip=flip)
    assert orders(p, g) == [(*leg0(flip), True)] and trades(p, g) == []
    # a leg known at 11:00 (the morning's end): the morning idea cannot trade it, the midday idea places it at its first close
    g = day({"10:05": hi(15010.0), "10:35": hi(15020.0), "11:20": lo(15009.75)}, {"10:30": 15015.0}, flip)
    assert legs({}, g) == [leg0(flip, sec(11))] and orders({}, g) == []
    assert orders({"sess": "mid"}, g) == [(*leg0(flip, sec(11, 1)), True)] and [minute(t) for t in trades({"sess": "mid"}, g)] == [sec(11, 20)]


def test_a_fill_and_a_bar_beyond_h_inside_one_bar_is_a_trade_the_fill_ends_the_leg(flip):
    # a 5-minute idea: 10:01 fills the limit, 10:03 trades beyond H. At the 10:05 close the leg is over by its fill
    g = base({"10:01": lo(15009.75), "10:03": hi(15020.25)}, flip=flip)
    st, res = run({"tf": "5", "exit_bars": 1, "max_tr": 1}, g)
    assert len(res.trades) == 1 and st.n_ent == 1
    t = res.trades[0]
    assert (minute(t), t["exit_reason"]) == (sec(10, 1), "bars") and t["exit_ms"] < ns("10:06") // 1_000_000


def test_a_fill_and_a_newer_leg_at_one_close_the_fill_is_counted_first(flip):
    # the buy limit rests at 15010; swing lows of 15013 (09:45 bar) and 15011 (10:15 bar). The minutes 10:31-10:46 never printed, so the swing bar
    # 10:30-10:45 holds one minute; the 10:47 minute fills the limit. At its close (10:48) the fill is seen AND the 10:15 bar's lower low
    # becomes known: a newer leg, which clears the family's orders -- after the fill has been counted (the trade leaves one bar later, by exit_bars)
    g = base({"09:50": lo(15013.0), "10:20": lo(15011.0), "10:47": lo(15009.75)}, {"10:15": 15012.0}, flip)
    t = tape_of(g)
    keep = ~((t.ts >= ns("10:31")) & (t.ts < ns("10:47")))
    hole = S.Tape(t.root, t.date, t.contract, t.ts[keep], t.px[keep], t.size[keep])
    st, res = run({"exit_bars": 1, "max_tr": 1}, None, tape=hole)
    assert len(res.trades) == 1 and st.n_ent == 1 and (st.ph if flip else st.pl)[1] == mp(15011.0, flip)       # (the 10:15 swing was known by then)
    x = res.trades[0]
    assert (minute(x), x["exit_reason"]) == (sec(10, 47), "bars") and x["exit_ms"] < ns("10:49") // 1_000_000


# ---- (iv) one leg, at most one entry -------------------------------------------------------------------------------------------------------------------

def test_a_leg_gives_one_entry(flip):
    g = base({"10:05": lo(15009.75), "10:20": lo(15009.75)}, flip=flip)                # back at the price after the trade has left
    tr = trades({"exit_bars": 2}, g)
    assert [minute(t) for t in tr] == [sec(10, 5)] and tr[0]["exit_ms"] < ns("10:10") // 1_000_000
    assert len(orders({"exit_bars": 2}, g)) == 1


def two_legs(flip, **more):
    """10:02 fills the first leg's limit (15010). From 10:15 the quiet price is 15022 and 10:20 makes a swing high of 15025, known 10:45: a second
    leg from 15009.75 (the fill's low) to 15025, half way back 15017.375 -> 15017.25. -> (the bars, the second leg as legs() shows it)."""
    g = base({"10:02": lo(15009.75), "10:20": hi(15025.0), **more}, {"10:15": 15022.0}, flip)
    return g, (sec(10, 45), sd(flip), mp(15017.25, flip), mp(15009.75, flip))


def test_a_leg_known_while_a_trade_is_open_gets_its_order_when_that_trade_has_ended(flip):
    g, second = two_legs(flip, **{"10:53": lo(15017.0)})                               # 10:53 trades through the second leg's price
    assert legs({}, g) == [leg0(flip), second]
    # the first trade leaves 2 bars after its fill: flat at 10:45, the second leg's order is placed at once and fills
    assert orders({"exit_bars": 2}, g)[1:] == [(*second, True)] and [minute(t) for t in trades({"exit_bars": 2}, g)] == [sec(10, 2), sec(10, 53)]
    # it leaves at the 10:47 close instead: open at 10:45 (no order), the order is placed at the first close after it has ended, 10:48
    assert orders({"exit_bars": 45}, g)[1:] == [(sec(10, 48), *second[1:], True)]
    assert [minute(t) for t in trades({"exit_bars": 45}, g)] == [sec(10, 2), sec(10, 53)]


def test_a_leg_is_killed_when_the_price_gets_there_while_another_trade_is_open(flip):
    g, second = two_legs(flip, **{"10:46": lo(15017.25), "10:53": lo(15017.0)})        # 10:46 touches the price: the first trade is still open
    assert legs({}, g) == [leg0(flip), second]
    assert live({"exit_bars": 45}, g, sec(10, 46)) == second[1:] and live({"exit_bars": 45}, g, sec(10, 47)) is None
    assert len(orders({"exit_bars": 45}, g)) == 1 and [minute(t) for t in trades({"exit_bars": 45}, g)] == [sec(10, 2)]
    # (the same touch with the second order already working -- the first trade left at 10:04 -- leaves the leg alone: the fill comes at 10:53)
    assert [minute(t) for t in trades({"exit_bars": 2}, g)] == [sec(10, 2), sec(10, 53)]


def test_a_leg_known_before_the_session_opens_gets_its_order_at_the_first_close_inside(flip):
    # the base day 45 minutes earlier: the leg is known at 09:15, before the 09:30 session. 09:40 trades through its price
    g = day({"08:20": hi(15010.0), "08:50": hi(15020.0), "09:40": lo(15009.75)}, {"08:45": 15015.0}, flip)
    assert legs({}, g) == [leg0(flip, sec(9, 15))]
    assert orders({}, g) == [(*leg0(flip, sec(9, 31)), True)] and [minute(t) for t in trades({}, g)] == [sec(9, 40)]
    assert orders({"tf": "5"}, g) == [(*leg0(flip, sec(9, 35)), True)] and [minute(t) for t in trades({"tf": "5"}, g)] == [sec(9, 40)]
    # a 15-minute idea's first close inside is 09:45: the 09:40 pullback came first, with no order working -- the leg is gone
    assert orders({"tf": "15"}, g) == [] and trades({"tf": "15"}, g) == []
    assert orders({"sess": "pre"}, g) == [(*leg0(flip, sec(9, 15)), True)]             # an 08:25-09:30 idea places it at 09:15
    # known exactly at 09:30, the session's start: that close is not inside the session, the next one is
    g = day({"08:35": hi(15010.0), "09:05": hi(15020.0), "09:40": lo(15009.75)}, {"09:00": 15015.0}, flip)
    assert legs({}, g) == [leg0(flip, sec(9, 30))] and orders({}, g) == [(*leg0(flip, sec(9, 31)), True)]
    assert [minute(t) for t in trades({}, g)] == [sec(9, 40)]


def test_a_leg_dies_before_the_session_when_the_price_reaches_the_entry(flip):
    e = {"08:20": hi(15010.0), "08:50": hi(15020.0), "09:40": lo(15009.75)}
    g = day({**e, "09:20": lo(15010.0)}, {"08:45": 15015.0}, flip)                     # known 09:15; 09:20 trades AT the entry price
    assert legs({}, g) == [leg0(flip, sec(9, 15))] and live({}, g, sec(9, 20)) == leg0(flip)[1:] and live({}, g, sec(9, 21)) is None
    assert orders({}, g) == [] and trades({}, g) == []
    g = day({**e, "09:20": lo(15010.25)}, {"08:45": 15015.0}, flip)                    # one tick short of it: still live at the open
    assert orders({}, g) == [(*leg0(flip, sec(9, 31)), True)] and len(trades({}, g)) == 1
    # a bar beyond H before the session ends it as well
    g = day({**e, "09:20": hi(15020.25)}, {"08:45": 15015.0}, flip)
    assert live({}, g, sec(9, 21)) is None and trades({}, g) == []


def test_dir_runs_one_side_only(flip):
    assert PB.Pullback.defaults()["dir"] == "both"
    g = base({"10:05": lo(15009.75)}, flip=flip)
    assert [x[4] for x in orders({"dir": sd(flip)}, g)] == [True] and len(trades({"dir": sd(flip)}, g)) == 1
    off = orders({"dir": sd(not flip)}, g)                                             # asked at every close while the leg lives, never placed
    assert [x[0] for x in off] == list(range(sec(10), sec(10, 6), 60)) and not any(x[4] for x in off) and trades({"dir": sd(not flip)}, g) == []
    assert [x[4] for x in orders({}, g)] == [True]


def stairs(n=5, flip=False):
    """n up legs in the london session, one an hour, each pulled back into at once. Leg k: the quiet price steps up 30 points at 03:30 + k hours,
    a swing high 5 points above it, known half an hour later; the minute after that trades one tick through the entry price.
    -> (the bars, [(second the leg is known, entry price, start)])."""
    edits, steps, want = {"03:05": hi(15010.0)}, {}, []
    start = 15000.0
    for k in range(n):
        b = 15015.0 + 30.0 * k
        h0 = 3 + k
        steps["%02d:30" % h0] = b
        edits["%02d:35" % h0] = hi(b + 5.0)
        px = PB.entry_price(1, b + 5.0, start, 0.5, TICK)
        assert start < px < b and (b + 5.0 - px) >= 0.5 * (b + 5.0 - start)
        edits["%02d:02" % (h0 + 1)] = lo(px - TICK)
        want.append((sec(h0 + 1), px, start))
        start = px - TICK                                                              # the next leg starts at this pullback's low
    return day(edits, steps, flip), want


def test_max_tr_defaults_to_three_and_caps_the_entries_of_a_session(flip):
    assert PB.Pullback.defaults()["max_tr"] == 3
    bars, want = stairs(5, flip)
    assert want[:2] == [(sec(4), 15010.0, 15000.0), (sec(5), 15029.75, 15009.75)]      # (the arithmetic of the staircase, by hand)
    full = [(s, sd(flip), mp(px, flip), mp(st, flip)) for s, px, st in want]
    assert legs({"sess": "london"}, bars) == full
    p = {k: v for k, v in BASE.items() if k != "max_tr"}
    cls = type("Spy", (Spy,), {"log": []})
    st = cls({**p, "sess": "london", "exit_bars": 1})                                  # the default max_tr (3); each trade leaves one bar after its fill
    st.ROLLS = frozenset()
    res = S.run_session(st, tape_of(bars), daily=list(DAILY), on_error="raise")
    assert st.p["max_tr"] == 3 and len(res.trades) == 3 and [((t - ns("00:00")) // S.NS, *x) for t, *x in cls.log] == [(*x, True) for x in full[:3]]
    for m in (1, 2, 4, 5):
        tr = trades({"sess": "london", "max_tr": m, "exit_bars": 1}, bars)
        assert [(minute(t), t["entry_price"]) for t in tr] == [(s + 120, mp(px, flip)) for s, px, _ in want[:m]], m


def test_one_position_at_a_time(flip):
    bars, want = stairs(5, flip)
    tr = trades({"sess": "london", "exit_bars": 2}, bars)
    assert len(tr) == 5 and all(a["exit_ms"] <= b["entry_ms"] for a, b in zip(tr, tr[1:]))
    assert len(trades({"sess": "london"}, bars)) == 1                                  # without an exit the one open trade blocks every later leg


# ---- (v) the swing bars: three bars, strictly, known one bar late, the swing size -------------------------------------------------------------------------

def test_a_leg_is_unknown_until_the_swing_bar_after_h_has_closed(flip):
    c = dict(closes({}, base(flip=flip)))
    assert all(c[s] is None for s in range(sec(9, 31), sec(10), 60)) and c[sec(10)] == (sd(flip), mp(15010.0, flip), 15000.0)
    assert orders({}, base(flip=flip)) == [(*leg0(flip), True)]                        # its order is placed at that close
    # a pullback at 09:50, before the leg is known, is no entry (and the leg then gives nothing: the price has been there)
    assert trades({}, base({"09:50": lo(15009.75)}, flip=flip)) == []


def test_the_swing_size_sets_when_a_leg_is_known(flip):
    # swing highs at 06:10 (15010) and 08:10 (15020), the quiet price 15015 from 08:00.
    # 15 min: the bar 08:00-08:15, known 08:30; 30 min: 08:00-08:30, known 09:00; 60 min: 08:00-09:00, known 10:00
    g = day({"06:10": hi(15010.0), "08:10": hi(15020.0)}, {"08:00": 15015.0}, flip)
    for swing, known in (("15", sec(8, 30)), ("30", sec(9, 0)), ("60", sec(10, 0))):
        assert legs({"swing": swing}, g) == [(known, sd(flip), mp(15010.0, flip), 15000.0)], swing
    assert orders({"swing": "60"}, g) == [(sec(10), sd(flip), mp(15010.0, flip), 15000.0, True)]
    assert orders({"swing": "15"}, g) == [(*leg0(flip, sec(9, 31)), True)]             # known 08:30 and still live at the open
    assert PB.Pullback.defaults()["swing"] == "15"


def test_the_high_must_be_strictly_above_both_neighbours(flip):
    assert legs({}, base({"09:50": hi(15020.0)}, flip=flip)) == []                     # the bar after H's has the same high: no swing
    assert legs({}, base({"09:50": hi(15019.75)}, flip=flip)) != []
    assert legs({}, base({"09:20": hi(15010.0)}, flip=flip)) == []                     # the earlier swing high's neighbour has the same high: one swing only
    assert legs({}, base({"09:20": hi(15009.75)}, flip=flip)) != []


def test_the_first_swing_bar_of_the_day_is_never_a_swing_and_the_earliest_leg(flip):
    p = {"sess": "asia"}
    # swing highs in the swing bars 1 (00:15) and 3 (00:45): the leg is known at 01:15, the earliest a 15-minute leg can be
    assert legs(p, day({"00:20": hi(15010.0), "00:50": hi(15020.0)}, {"00:45": 15015.0}, flip)) == [(sec(1, 15), sd(flip), mp(15010.0, flip), 15000.0)]
    # the same highs in the bars 0 and 2: bar 0 has no bar before it, so the 00:30 bar's high is the first swing high of the day -- no leg
    assert legs(p, day({"00:05": hi(15010.0), "00:35": hi(15020.0)}, {"00:30": 15015.0}, flip)) == []
    # 30-minute bars: 02:30 at the earliest. 60-minute bars: 05:00, so an asia idea (00:00-03:00) never trades
    g = day({"00:40": hi(15010.0), "01:40": hi(15020.0)}, {"01:30": 15015.0}, flip)
    assert legs({**p, "swing": "30"}, g) == [(sec(2, 30), sd(flip), mp(15010.0, flip), 15000.0)]
    assert orders({**p, "swing": "30"}, g) == [(sec(2, 30), sd(flip), mp(15010.0, flip), 15000.0, True)]
    g = day({"01:10": hi(15010.0), "03:10": hi(15020.0)}, {"03:00": 15015.0}, flip)
    assert legs({"sess": "london", "swing": "60"}, g) == [(sec(5), sd(flip), mp(15010.0, flip), 15000.0)]      # (an asia idea's replay ends at 03:00)
    assert orders({**p, "swing": "60"}, g) == [] and legs({**p, "swing": "60"}, g) == []


def test_the_idea_bar_size_does_not_move_the_leg_and_the_entry_is_after_the_decision(flip):
    g = base({"10:07": lo(15009.75)}, flip=flip)
    for tf in ("1", "5", "15"):
        assert orders({"tf": tf}, g) == [(sec(10), sd(flip), mp(15010.0, flip), 15000.0, True)], tf
        assert [minute(t) for t in trades({"tf": tf}, g)] == [sec(10, 7)], tf


def test_an_evening_idea_reads_the_evening_before_and_a_day_idea_does_not(flip):
    # 18:00-23:59 of the evening before the trade date: swing highs at 18:20 (15010) and 18:50 (15020), the quiet price 15015 from 18:45 -> the
    # leg is known at 19:15. The day goes on at 15015 and makes one swing high (15030) at 09:35.
    eve = seg(360, {"18:20": hi(15010.0), "18:50": hi(15020.0), "19:20": lo(15009.75)}, {"18:45": 15015.0}, t0="18:00")
    rest = seg(960, {"09:35": hi(15030.0)}, {"09:30": 15025.0}, base=15015.0)
    bars = mirror(eve + rest) if flip else eve + rest
    t = minute_tape(bars, "18:00", D - dt.timedelta(days=1))
    tape = S.Tape(t.root, D, t.contract, t.ts, t.px, t.size)                           # the tape of trade date D holds its evening
    got = orders({"sess": "eve"}, None, tape=tape, segment="eve")
    assert got == [(sec(19, 15) - 86400, sd(flip), mp(15010.0, flip), 15000.0, True)]  # seconds before 00:00 of the trade date
    tr = trades({"sess": "eve"}, None, tape=tape, segment="eve")
    assert [(minute(x) + 86400, x["entry_price"]) for x in tr] == [(sec(19, 20), mp(15010.0, flip))]
    # the evening idea's swings run on into the day: 15030 is above the evening's 15020 (a leg at 10:00, outside its session)
    assert [x[0] for x in legs({"sess": "eve"}, None, tape=tape, segment="eve")] == [sec(19, 15) - 86400, sec(10)]
    # the nyam idea starts its swing bars at 00:00: 15030 is its first swing high of the day, no leg
    assert legs({}, None, tape=tape) == [] and orders({}, None, tape=tape) == []


# ---- (vi) flat by 15:58 and the standard exits ---------------------------------------------------------------------------------------------------------------

def test_a_trade_with_no_stop_hit_is_flat_by_15_58_and_the_standard_stop_acts(flip):
    for sess, h0 in (("nyam", 9), ("mid", 11), ("pm", 14)):
        e = {"%02d:05" % h0: hi(15010.0), "%02d:35" % h0: hi(15020.0), "%02d:05" % (h0 + 1): lo(15009.75)}
        tr = trades({"sess": sess}, day(e, {"%02d:30" % h0: 15015.0}, flip))
        assert len(tr) == 1 and tr[0]["side"] == sd(flip) and tr[0]["exit_ms"] <= (ns("15:58") // 1_000_000) + 60_000, sess
    # a stop of the standard table acts as in every family: 4 points, and the pullback goes on 8 points through the entry
    tr = trades({"stop_val": 4.0}, base({"10:05": lo(15009.75), "10:07": lo(15002.0)}, flip=flip))
    assert len(tr) == 1 and tr[0]["net"] < 0 and tr[0]["exit_reason"] == "sl" and tr[0]["exit_ms"] < ns("10:08") // 1_000_000


# ---- (vii) NO LOOK-AHEAD ---------------------------------------------------------------------------------------------------------------------------------------

RUNS = [(47, "london", "15", 0.5), (93, "london", "15", 0.62), (41, "london", "15", 0.79), (66, "london", "15", 0.5), (89, "mid", "30", 0.79), (91, "london", "30", 0.79),
        (85, "london", "30", 0.62), (98, "pm", "60", 0.79), (93, "mid", "60", 0.79)]      # (seed, session, swing, level): days with several orders and fills


def test_a_future_bar_cannot_change_an_earlier_order_or_leg():
    n = 0
    for seed, sess, swing, level in RUNS:
        bars = trendy(960, seed, int(swing) // 15)
        tape = tape_of(bars)
        p = {"sess": sess, "swing": swing, "level": level}
        cl, od = closes(p, bars, tape=tape), orders(p, bars, tape=tape)
        known = [x[0] for x in legs(p, bars, tape=tape)]
        for cut in known[:6] + [x[0] for x in od] + [sec(9, 44, 30)]:    # the decision AT the cut stands whatever prints from that second on
            dirty = garble(tape, ns("00:00") + cut * S.NS)
            assert [x for x in closes(p, bars, tape=dirty) if x[0] <= cut] == [x for x in cl if x[0] <= cut], (seed, cut)
            assert [x for x in orders(p, bars, tape=dirty) if x[0] <= cut] == [x for x in od if x[0] <= cut], (seed, cut)
            n += 1
    assert n > 30


def test_an_entry_is_never_before_its_decision_plus_the_order_delay():
    n = 0
    for seed, sess, swing, level in RUNS:
        for tf in ("1", "5", "15"):
            bars = trendy(960, seed, int(swing) // 15)
            p = {"sess": sess, "swing": swing, "level": level, "tf": tf, "exit_bars": 3}
            cls = type("Spy", (Spy,), {"log": []})
            _, res = run(p, bars, cls)
            assert all((t - ns("00:00")) % (int(tf) * 60 * S.NS) == 0 for t, *_ in cls.log)             # orders at a close of the idea's bars only
            for t in res.trades:
                dec = [x[0] for x in cls.log if x[4] and x[1] == t["side"] and x[2] == t["order_price"] and x[0] <= t["entry_ns"]]
                assert t["entry_price"] == t["order_price"] and dec and t["entry_ns"] >= max(dec) + LAT
                n += 1
    assert n > 30


def test_a_bar_closed_late_after_a_hole_in_the_tape_does_not_read_the_unfinished_swing_bar():
    # 5-minute bars, 15-minute swing bars. The minutes 09:54-09:58 never printed, so the Template closes the bar 09:50-09:55 late: at 10:00:00, when
    # the 09:59 minute bar arrives and BEFORE that minute is added. The 09:59 minute holds the high (15030) of the swing bar 09:45-10:00, which
    # makes the bar before it (09:30-09:45, high 15020) no swing at all. A rule that took the wall clock (10:00) of that late close would call the
    # bar 09:45-10:00 ended without its last minute, see a higher swing high and rest a buy limit.
    bars = base({"09:59": hi(15030.0)})
    t = tape_of(bars)
    keep = ~((t.ts >= ns("09:54")) & (t.ts < ns("09:59")))
    hole = S.Tape(t.root, t.date, t.contract, t.ts[keep], t.px[keep], t.size[keep])
    p = {"tf": "5"}
    assert orders(p, bars, tape=hole) == [] and legs(p, bars, tape=hole) == [] and legs(p, bars) == []
    assert [x[0] for x in closes(p, bars, tape=hole)].count(sec(10)) == 2             # two closes at the 10:00:00 event: the late one (09:50-09:55) and 09:55-10:00
    # the same hole with a quiet 09:59: the leg is known at the 10:00 close and not at the late close before it
    t = tape_of(base())
    hole = S.Tape(t.root, t.date, t.contract, t.ts[keep], t.px[keep], t.size[keep])
    assert [g for s, g in closes(p, None, tape=hole) if s == sec(10)] == [None, ("long", 15010.0, 15000.0)]


def test_a_leg_known_late_that_has_already_been_passed_gives_no_order(flip):
    # the minutes 09:46-10:06 never printed. The swing bar 09:45-10:00 holds one minute (09:45); when the 10:07 minute closes, that bar has
    # ended and H (the 09:30 bar) becomes known -- with the 10:07 minute already in the next swing bar. Its high is above H: the leg is still
    # growing, no order. (A quiet 10:07: the order, at 10:08.)
    def holed(bars):
        t = tape_of(bars)
        keep = ~((t.ts >= ns("09:46")) & (t.ts < ns("10:07")))
        return S.Tape(t.root, t.date, t.contract, t.ts[keep], t.px[keep], t.size[keep])
    assert orders({}, None, tape=holed(base(flip=flip))) == [(sec(10, 8), sd(flip), mp(15010.0, flip), 15000.0, True)]
    assert orders({}, None, tape=holed(base({"10:07": hi(15020.25)}, flip=flip))) == []
    assert orders({}, None, tape=holed(base({"10:07": hi(15020.0)}, flip=flip))) != []
    assert orders({}, None, tape=holed(base({"10:07": lo(15010.0)}, flip=flip))) == []         # ... and a pullback in that minute counts too


# ---- (viii) the rule against an independent restatement, on random days --------------------------------------------------------------------------------------

def swing_bars(bars, w):
    """(high, low) of the swing bars of w minutes: bar j = the minutes [j x w, (j + 1) x w)."""
    return [(max(b[1] for b in bars[j:j + w]), min(b[2] for b in bars[j:j + w])) for j in range(0, len(bars), w)]


def ref_legs(bars, sw, w, j, level):
    """The legs swing bar j makes when it becomes known, from the written rule alone, in exact arithmetic: [(side, H, start, entry price)]."""
    def is_hi(i):
        return 0 < i < len(sw) - 1 and sw[i][0] > sw[i - 1][0] and sw[i][0] > sw[i + 1][0]

    def is_lo(i):
        return 0 < i < len(sw) - 1 and sw[i][1] < sw[i - 1][1] and sw[i][1] < sw[i + 1][1]
    lv, tk, out = Fraction(str(level)), Fraction(str(TICK)), []
    if is_hi(j):
        prev = [i for i in range(j) if is_hi(i)]
        if prev and sw[j][0] > sw[prev[-1]][0]:
            end, start = sw[j][0], min(sw[i][1] for i in range(prev[-1] + 1, j + 1))
            out.append(("long", end, start, float(math.floor((Fraction(end) - lv * (Fraction(end) - Fraction(start))) / tk) * tk)))
    if is_lo(j):
        prev = [i for i in range(j) if is_lo(i)]
        if prev and sw[j][1] < sw[prev[-1]][1]:
            end, start = sw[j][1], max(sw[i][0] for i in range(prev[-1] + 1, j + 1))
            out.append(("short", end, start, float(math.ceil((Fraction(end) + lv * (Fraction(start) - Fraction(end))) / tk) * tk)))
    return out


def ref_walk(bars, tf, sess, w, level, fills):
    """One day walked close by close from the written rule alone (every minute has a bar: no holes).
    fills False = no order is ever placed (class Sig): -> every close inside the session at which a live leg asks for its order, as
                  (second, side, price, start).
    fills True  = the order is placed, cancelled and filled as the rule says: -> the first trade of the day as (the minute it fills in,
                  side, price), or None (the stop is 1000 points away: only the first trade is compared)."""
    s0, s1 = S.SESS[sess]
    sw = swing_bars(bars, w)
    tfb = [(max(b[1] for b in bars[k:k + tf]), min(b[2] for b in bars[k:k + tf])) for k in range(0, len(bars), tf)]     # tf bar t = the minutes [t x tf, (t + 1) x tf)
    leg, since, asks = None, None, []                                 # leg = (side, H, price, start); since = the minute its order has worked from
    for m in range(tf, len(bars) + 1, tf):                            # the tf bar m // tf - 1 closes at minute m
        end, (bh, bl) = m * 60, tfb[m // tf - 1]
        if leg is not None:
            side, h, px, _ = leg
            up = side == "long"
            if since is not None:
                for i in range(max(since, m - tf), m):                # the order worked through this bar, up to the session's last 5 minutes
                    if i * 60 < s1 - 300 and (bars[i][2] <= px - TICK if up else bars[i][1] >= px + TICK):
                        return i * 60, side, px
                if end > s1 - 300:
                    since = None                                      # the Template cancelled it inside this bar
            if (bh > h) if up else (bl < h):
                leg = since = None                                    # a bar beyond H
            elif since is None and ((bl <= px) if up else (bh >= px)):
                leg = None                                            # at the price with no order working: the pullback happened without us
        j = m // w - 2                                                # the swing bar whose neighbour has just ended
        if m % w == 0 and j >= 1:
            lg = ref_legs(bars, sw, w, j, level)
            if lg:
                leg = since = None                                    # the latest leg replaces any earlier one
                if len(lg) == 1:
                    side, h, start, px = lg[0]
                    up = side == "long"
                    x = next(t for t in range(j * w // tf, (j + 1) * w // tf) if tfb[t][0 if up else 1] == h)       # the FIRST tf bar at the extreme
                    after = tfb[x + 1:m // tf]
                    if not (min(a[1] for a in after) <= px if up else max(a[0] for a in after) >= px):
                        leg = (side, h, px, start)
        if leg is not None and since is None and s0 < end <= s1 and end < s1 - 300:
            if fills:
                since = m
            else:
                asks.append((end, leg[0], leg[2], leg[3]))
    return None if fills else asks


def ref_wants(bars, tf, sess, w, level):
    return ref_walk(bars, tf, sess, w, level, False)


def ref_first_trade(bars, tf, sess, w, level):
    return ref_walk(bars, tf, sess, w, level, True)


def asked(rows):
    """The legs among the asks of a day (a leg asks at every close it is live): how many different ones."""
    return sum(1 for a, b in zip([None] + rows, rows) if a is None or a[1:] != b[1:])


LEVELS = (0.5, 0.62, 0.79)
SESSIONS = ("asia", "london", "pre", "nyam", "mid", "pm")


def random_days(swing):
    """62 seeded days for a swing size: 60 of legs and pullbacks at that size's pace, 2 plain random walks."""
    return [trendy(960, seed, swing // 15) for seed in range(40, 100)] + [rand_bars(960, seed, p0=PX, step=4.0) for seed in (3, 11)]


@pytest.mark.parametrize("swing", [15, 30, 60])
@pytest.mark.parametrize("sess", SESSIONS)
@pytest.mark.parametrize("tf", [1, 5, 15])
def test_the_orders_and_the_first_trade_equal_the_written_rule_on_random_days(tf, sess, swing):
    n = 0
    for i, bars in enumerate(random_days(swing)):
        level = LEVELS[i % 3]
        p = {"swing": str(swing), "tf": str(tf), "sess": sess, "level": level}
        want = ref_wants(bars, tf, sess, swing, level)
        assert wants(p, bars) == want, (i, want[:3])
        first = ref_first_trade(bars, tf, sess, swing, level)
        tr = trades(p, bars)
        assert [(minute(t), t["side"], t["entry_price"]) for t in tr[:1]] == ([] if first is None else [first]), (i, first)
        n += asked(want)
    if (sess, swing) == ("asia", 60):
        assert n == 0                                                # the first 60-minute leg is known at 05:00, after the session
    elif swing == 15:
        assert n > 0, "the random days never gave an order: the comparison would be empty"


def test_the_random_days_give_orders_and_fills_at_every_swing_size_and_bar_size():
    for swing in (15, 30, 60):                                       # (the written rule alone: what the comparison above compares with)
        for tf in (1, 5, 15):
            n = k = 0
            for sess in SESSIONS:
                for i, bars in enumerate(random_days(swing)):
                    n += asked(ref_wants(bars, tf, sess, swing, LEVELS[i % 3]))
                    k += ref_first_trade(bars, tf, sess, swing, LEVELS[i % 3]) is not None
            assert n >= 50 and k >= 8, (swing, tf, n, k)


# ---- (ix) the swing lines are sfp's ------------------------------------------------------------------------------------------------------------------------------

class Tap(list):
    """A list that remembers what was appended to it."""
    def __init__(self, xs):
        super().__init__(xs)
        self.new = []

    def append(self, x):
        self.new.append(x)
        super().append(x)


def both_families():
    """Two classes that log, at every tf close, the swing highs and lows that became known at it: sfp's own lines and their restatement here.
    Neither places an order (a trade held past the session's end would make the one replay longer than the other)."""
    a, b = [], []

    class A(SF.Sfp):
        def fam_update(self, ctx):
            h, l = Tap(self.hi), Tap(self.lo)
            self.hi, self.lo = h, l
            super().fam_update(ctx)
            a.append((self.day, ctx.now_ns, tuple(h.new), tuple(l.new)))

        def fam_signal(self, ctx):
            pass

    class B(PB.Pullback):
        def _known(self):
            out = super()._known()
            b.append((self.day, self._cx.now_ns, tuple(self.sw[i][1] for i, h, _ in out if h), tuple(self.sw[i][2] for i, _, l in out if l)))
            return out

        def fam_signal(self, ctx):
            pass
    return A, B, a, b


def test_the_swings_are_sfp_s_swings_on_random_days_and_through_holes():
    n = 0
    for seed in (40, 41, 42, 43):
        bars = trendy(960, seed)
        t = tape_of(bars)
        g = np.random.default_rng(seed)
        keep = np.ones(len(t.ts), bool)
        for _ in range(12):                                          # twelve holes of 3 to 40 minutes
            a0 = int(g.integers(30, 900)) * 60
            keep &= ~((t.ts >= ns("00:00") + a0 * S.NS) & (t.ts < ns("00:00") + (a0 + int(g.integers(3, 40)) * 60) * S.NS))
        for tape in (t, S.Tape(t.root, t.date, t.contract, t.ts[keep], t.px[keep], t.size[keep])):
            for tf in ("1", "5", "15"):
                for swing in ("15", "30", "60"):
                    A, B, a, b = both_families()
                    p = {"hold_to": "day", "tf": tf, "sess": "pm", "swing": swing}
                    for cls in (A, B):
                        st = cls(p)
                        st.ROLLS = frozenset()
                        S.run_session(st, tape, daily=list(DAILY), on_error="raise")
                    assert a == b and len(a) > 40
                    n += sum(len(x[2]) + len(x[3]) for x in a)
    assert n > 500


@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_the_swings_are_sfp_s_swings_on_real_build_days(root):
    real_days()
    days = days_of(root, 2)
    n = 0
    for sess in ("pm", "eve"):
        for tf, swing in (("1", "15"), ("5", "30"), ("15", "60"), ("5", "15")):
            A, B, a, b = both_families()
            p = {"hold_to": "day", "tf": tf, "sess": sess, "swing": swing}
            out = S.run_many([(A, p), (B, p)], root=root, days=days, period="build", workers=1, on_error="raise")
            assert sum(r["skipped_by_error"] for r in out) == 0 and sorted(a) == sorted(b) and len(a) > 20
            n += sum(len(x[2]) + len(x[3]) for x in a)
    assert n > 100


# ---- (x) the settings and the registry ---------------------------------------------------------------------------------------------------------------------------

def test_the_settings_and_their_limits():
    d, sc = PB.Pullback.defaults(), PB.Pullback.schema()
    assert (d["level"], d["swing"], d["max_tr"], d["dir"]) == (0.62, "15", 3, "both")
    assert sc["level"] == ("float", 0.25, 0.9) and sc["swing"] == ("choice", ("15", "30", "60")) and sc["max_tr"] == ("int", 1, 5)
    for bad in ({"level": 0.2}, {"level": 0.95}, {"level": "deep"}, {"swing": "5"}, {"swing": "45"}, {"swing": 60}, {"swing": "move"}, {"max_tr": 0},
                {"max_tr": 6}, {"max_tr": 1.5}, {"dir": "up"}, {"mode": "touch"}):
        with pytest.raises(ValueError):
            PB.Pullback({"tf": "5", **bad})
    for ok in ({"level": 0.25}, {"level": 0.9}, {"level": 0.705}, {"swing": "15"}, {"swing": "30"}, {"swing": "60"}, {"max_tr": 1}, {"max_tr": 5}, {"dir": "short"}):
        PB.Pullback({"tf": "5", **ok})


def test_the_registry_holds_pullback_as_written_and_it_is_a_block():
    assert families.ERRORS == {}
    cls, inputs, both, notes = families.REGISTRY["pullback"]
    lib = families.library("pullback")
    assert cls is PB.Pullback and inputs == {} and both is False and cls.FEATURES == () and cls.SCREEN_TFS == ("1", "5", "15")
    assert cls.SCREEN_RUN == {"strict_limit": True}                   # a limit entry: a fill print through the stop is a loss (as fvg)
    assert families.MODULE_OF["pullback"] == "pullback" and lib["roots"] == ("NQ", "ES", "GC") and not lib["l2"] and not lib["weak"]
    assert lib["mirror"] is None and lib["complexity"] == 10 and lib["variants"] == [{"level": 0.5}, {"level": 0.62}, {"level": 0.79}]
    assert len(lib["rationale"]) > 60 and "limit" in notes and "swing" in notes
    from families import blocks as B
    assert issubclass(B.WRAPPED["pullback"], PB.Pullback) and B.BASES["pullback"][0] is PB.Pullback and B.B_pullback is B.WRAPPED["pullback"]
    with pytest.raises(ValueError):
        B.WRAPPED["pullback"]({"tf": "5", "stop_mode": "rng"})        # no structure height is registered for it: the standard table's stops
    B.WRAPPED["pullback"]({"tf": "5", "stop_mode": "struct"})         # ... of which `struct` reads the leg's start
    for s in RM.DAY_PASSES:                                           # it runs in every session
        assert cls({"tf": "5", "sess": s, "hold_to": "day"}).sessions() == [s]


def test_the_block_runs_the_family_trade_for_trade():
    from families import blocks as B
    for seed, sess, swing, level in RUNS[:3]:
        tape = tape_of(trendy(960, seed, int(swing) // 15))
        p = {**BASE, "sess": sess, "swing": swing, "level": level, "stop_mode": "struct", "tgt_r": 2.0, "tf": "5"}
        out = []
        for cls in (PB.Pullback, B.WRAPPED["pullback"]):
            st = cls(p)
            st.ROLLS = frozenset()
            out.append(S.run_session(st, tape, daily=list(DAILY), on_error="raise", costs=S.Costs(strict_limit=True)).trades)
        assert out[0] == out[1] and len(out[0]) > 0


# ---- (xi) real BUILD days: the invariants of the code check, at 1 worker -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_real_build_days_hold_the_window_one_position_and_the_flat_time(root):
    real_days()
    days = days_of(root, 4)
    tick = S.SPECS[root][1]
    hd = {"tf": "5", "hold_to": "day", "stop_mode": "atr", "stop_val": 1.5, "tgt_r": 2.0}
    specs = [(PB.Pullback, {**hd, "sess": s, "swing": w, "level": lv}) for s in ("london", "nyam", "mid", "pm") for w in ("15", "30", "60") for lv in (0.5, 0.79)]
    specs += [(PB.Pullback, {**hd, "tf": "1", "sess": "nyam", "stop_mode": "struct"}), (PB.Pullback, {**hd, "tf": "15", "sess": "eve", "level": 0.79})]
    out = S.run_many(specs, root=root, days=days, period="build", workers=1, on_error="raise", strict_limit=True)
    again = S.run_many(specs, root=root, days=days, period="build", workers=1, on_error="raise", strict_limit=True)
    assert [r["trades"] for r in out] == [r["trades"] for r in again]
    assert sum(r["skipped_by_error"] for r in out) == 0 and all(r["both_sides_sessions"] == 0 for r in out)
    total = 0
    for (cls, p), r in zip(specs, out):
        s0, s1 = S.SESS[p["sess"]]
        last, per_day = {}, {}
        for t in sorted(r["trades"], key=lambda t: t["entry_ms"]):
            d = S._date(t["date"])
            es = (t["entry_ms"] // 1000) - S.et_ns(d, "00:00") // S.NS
            assert s0 < es < s1 - 300, (p, t["date"], es)                             # a resting order fills inside the window, before its last 5 minutes
            assert t["exit_ms"] <= S.et_ns(d, S.day_flat(d, root)) // 1_000_000 + 60_000
            assert last.get(t["date"], 0) <= t["entry_ms"]                            # one position at a time
            assert t["entry_price"] == t["order_price"] and abs(t["order_price"] / tick - round(t["order_price"] / tick)) < 1e-6      # a limit fills at its price, on the grid
            if p["stop_mode"] == "struct":                                            # the leg's start is behind the entry
                assert (t["entry_price"] - t["sl"]) * (1 if t["side"] == "long" else -1) > 0
            last[t["date"]] = t["exit_ms"]
            per_day[t["date"]] = per_day.get(t["date"], 0) + 1
            total += 1
        assert all(v <= 3 for v in per_day.values())                                  # max_tr: three a session
    assert total > 0
