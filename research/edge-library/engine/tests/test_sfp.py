"""SFP: the `sfp` entry trigger (families/sfp.py), the swing failure at a small swing, written from its rule.

THE RULE UNDER TEST (the JadeCap videos tFKOaF4HMcg, TLEaD163obc, wZ4ea0VJnrw, Y8gUPDVnDgw, research/edge-library/videos):
    swing bars = bars of `swing` minutes (15 | 30 | 60) on clock multiples, made of the day's own 1-minute bars (from 00:00 ET; an evening idea:
                 from 18:00 of the evening before); only bars that have ENDED count
    swing high = a swing bar whose high is strictly above the highs of the bar before it and the bar after it; KNOWN once the bar after it ended
    level      = live from then until a bar of the idea's size trades beyond it
    SHORT      = a bar's high is above a live swing high and its close is strictly back below it -> market at the next bar's open
    LONG       = the mirror at a swing low;  beyond a level without a close back = the level is dead, no signal;  each level signals once
    both sides at one close = no trade;  entries inside the idea's session, up to max_tr a session, one position at a time; flat 15:58.
Synthetic days with EXACT numbers cover each behaviour (a flat day at 15000 with single minutes changed); seeded random-walk days check the
signal list against an independent restatement of the rule at every bar size, session and swing size; the real BUILD days check the
invariants (window, one position, flat 15:58) at 1 worker. No net, win rate or profit factor is read.
"""
import datetime as dt

import numpy as np
import pytest

import families
import l2sim as S
import run_menus as RM
from families import sfp as SF
from test_blocks import D, DAILY, TICK, days_of, garble, minute_tape, ns, rand_bars, real_days

BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "max_tr": 5, "swing": "15"}
PX = 15000.0


def sec(h, m=0, s=0):
    return h * 3600 + m * 60 + s


def flat(n, px=PX, v=40):
    return [(px, px + TICK, px - TICK, px, v)] * n


def up(px, c=PX):
    """A minute that trades up to px and closes at c (its low is the quiet day's low)."""
    return (PX, px, PX - TICK, c, 40)


def dn(px, c=PX):
    """A minute that trades down to px and closes at c."""
    return (PX, PX + TICK, px, c, 40)


def day(edits):
    """A full day of minute bars from 00:00 ET to 15:59, flat at 15000 (every swing bar alike: no swing), with the minutes `edits` changed:
    {"09:05": up(15020.0), ...}."""
    b = flat(960)
    for t, x in edits.items():
        b[S._sec(t) // 60] = x
    return b


def tape_of(bars):
    return minute_tape(bars, "00:00")


def sec_of(ctx):
    return (ctx.now_ns - ns("00:00")) // S.NS


def run(params, bars, cls=None, tape=None, **kw):
    """One instance through one day (the explicit roll list: none). -> (the instance, the result)."""
    st = (cls or SF.Sfp)({**BASE, **params})
    st.ROLLS = frozenset()
    res = S.run_session(st, tape or tape_of(bars), daily=list(DAILY), on_error="raise", **kw)
    return st, res


class Spy(SF.Sfp):
    """Logs every entry decision: (second of the decision, side, an order was placed)."""
    log: list = []

    def _mkt(self, ctx, side, **kw):
        o = super()._mkt(ctx, side, **kw)
        type(self).log.append((sec_of(ctx), side, o is not None))
        return o


def decisions(params, bars, tape=None, **kw):
    cls = type("Spy", (Spy,), {"log": []})
    run(params, bars, cls, tape, **kw)
    return list(cls.log)


class Sig(SF.Sfp):
    """Logs every signal the family sees (no order is placed, so every qualifying close shows): (second, side)."""
    seen: list = []

    def fam_signal(self, ctx):
        if self.go:
            type(self).seen.append((sec_of(ctx), "long" if self.go > 0 else "short"))


def signals(params, bars, tape=None, **kw):
    cls = type("Sig", (Sig,), {"seen": []})
    run(params, bars, cls, tape, **kw)
    return list(cls.seen)


def levels(params, bars, tape=None):
    """What the family holds after every tf close of the day: [(second of the close, the live swing highs, the live swing lows)]."""
    seen = []

    class Look(SF.Sfp):
        def fam_update(self, ctx):
            super().fam_update(ctx)
            seen.append((sec_of(ctx), tuple(self.hi), tuple(self.lo)))

    run(params, bars, Look, tape)
    return seen


def wicky(n, seed, p0=PX):
    """A seeded day of n minute bars on the tick grid that keeps coming back to p0, with long wicks: swing levels are taken and closed back
    through many times a day (a plain random walk seldom does it)."""
    g = np.random.default_rng(seed)
    out, o = [], p0
    for _ in range(n):
        c = o + round(float(g.normal(0, 3.0) - 0.05 * (o - p0)) / TICK) * TICK
        h = max(o, c) + int(g.integers(0, 24)) * TICK
        l = min(o, c) - int(g.integers(0, 24)) * TICK
        out.append((o, h, l, c, 40))
        o = c
    return out


HIGH = {"09:05": up(15020.0)}                        # a swing high of 15020 in the 15-minute bar 09:00-09:15: known at 09:30
LOW = {"09:05": dn(14980.0)}


# ---- (i) the failure: beyond a live swing level and a close back ---------------------------------------------------------------------------------

def test_a_bar_above_a_swing_high_that_closes_back_below_it_is_a_short_and_the_mirror_is_a_long():
    assert decisions({}, day({**HIGH, "09:40": up(15025.0, 15010.0)})) == [(sec(9, 41), "short", True)]
    assert decisions({}, day({**LOW, "09:40": dn(14975.0, 14990.0)})) == [(sec(9, 41), "long", True)]


def test_the_close_must_be_strictly_back_inside_a_close_on_the_level_kills_it():
    assert signals({}, day({**HIGH, "09:40": up(15025.0, 15020.0 - TICK)})) == [(sec(9, 41), "short")]
    on = {**HIGH, "09:40": up(15025.0, 15020.0)}
    assert signals({}, day(on)) == []
    assert signals({}, day({**on, "09:42": up(15022.0, 15010.0)})) == []               # the level is gone: the next bar above it is nothing
    assert signals({}, day({**LOW, "09:40": dn(14975.0, 14980.0 + TICK)})) == [(sec(9, 41), "long")]
    assert signals({}, day({**LOW, "09:40": dn(14975.0, 14980.0), "09:42": dn(14978.0, 14990.0)})) == []


def test_the_bar_must_trade_beyond_the_level_a_touch_is_nothing_and_leaves_it_live():
    touch = {**HIGH, "09:40": up(15020.0, 15010.0)}                                    # a high exactly on the level
    assert signals({}, day(touch)) == []
    assert signals({}, day({**touch, "09:42": up(15020.0 + TICK, 15010.0)})) == [(sec(9, 43), "short")]


def test_a_bar_that_trades_beyond_and_does_not_close_back_kills_the_level_without_a_signal():
    assert signals({}, day({**HIGH, "09:50": up(15022.0, 15010.0)})) == [(sec(9, 51), "short")]
    assert signals({}, day({**HIGH, "09:40": up(15025.0, 15024.0), "09:50": up(15022.0, 15010.0)})) == []
    assert signals({}, day({**LOW, "09:50": dn(14978.0, 14990.0)})) == [(sec(9, 51), "long")]
    assert signals({}, day({**LOW, "09:40": dn(14975.0, 14976.0), "09:50": dn(14978.0, 14990.0)})) == []


def test_a_level_gives_one_signal():
    assert signals({}, day({**HIGH, "09:40": up(15025.0, 15010.0), "09:50": up(15022.0, 15010.0)})) == [(sec(9, 41), "short")]
    assert signals({}, day({**LOW, "09:40": dn(14975.0, 14990.0), "09:50": dn(14978.0, 14990.0)})) == [(sec(9, 41), "long")]


def test_several_levels_of_one_side_in_one_bar_are_one_signal():
    two = {"08:35": up(15030.0), **HIGH}                                               # swing highs 15030 (known 09:00) and 15020 (known 09:30)
    assert [x[1] for x in levels({}, day(two)) if x[0] == sec(9, 30)] == [(15030.0, 15020.0)]
    assert signals({}, day({**two, "09:40": up(15035.0, 15010.0)})) == [(sec(9, 41), "short")]      # back below both
    assert signals({}, day({**two, "09:40": up(15035.0, 15025.0)})) == [(sec(9, 41), "short")]      # back below 15030 only: 15020 is dead
    assert signals({}, day({**two, "09:40": up(15035.0, 15032.0)})) == []                           # back below none: both are dead
    assert signals({}, day({**two, "09:40": up(15025.0, 15010.0), "09:45": up(15035.0, 15010.0)})) == [(sec(9, 41), "short"), (sec(9, 46), "short")]


def test_a_bar_that_fails_on_both_sides_is_no_trade_and_both_levels_are_gone():
    both = {"09:05": (PX, 15020.0, 14980.0, PX, 40)}                                   # one swing bar with the swing high and the swing low
    assert [x[1:] for x in levels({}, day(both)) if x[0] == sec(9, 30)] == [((15020.0,), (14980.0,))]
    wide = {**both, "09:40": (PX, 15025.0, 14975.0, PX, 40)}
    assert signals({}, day(wide)) == [] and decisions({}, day(wide)) == []
    assert signals({}, day({**wide, "09:42": up(15022.0, 15010.0), "09:43": dn(14978.0, 14990.0)})) == []
    # a bar that fails at the high and closes THROUGH the low is the short (the low is dead)
    assert signals({}, day({**both, "09:40": (PX, 15025.0, 14975.0, 14978.0, 40)})) == [(sec(9, 41), "short")]
    assert signals({}, day({**both, "09:40": (PX, 15025.0, 14975.0, 15022.0, 40)})) == [(sec(9, 41), "long")]


# ---- (ii) the swing: three swing bars, strictly, known one bar late ------------------------------------------------------------------------------

def test_a_swing_is_unknown_until_the_swing_bar_after_it_has_closed():
    one = {"09:35": up(15020.0)}                                                       # the swing bar 09:30-09:45; the bar after it ends at 10:00
    lv = dict((x[0], x[1]) for x in levels({}, day(one)))
    assert all(lv[s] == () for s in range(sec(9, 31), sec(10, 0), 60)) and lv[sec(10, 0)] == (15020.0,)
    # a bar that takes the high at 09:50, before the swing is known, is no failure: a rule that read the 09:30 bar as a swing at once would sell here
    early = {**one, "09:50": up(15025.0, 15010.0)}
    assert signals({}, day(early)) == []
    # ... and the first bar after 10:00 that takes it is one
    assert signals({}, day({**one, "10:00": up(15025.0, 15010.0)})) == [(sec(10, 1), "short")]
    lo = dict((x[0], x[2]) for x in levels({}, day({"09:35": dn(14980.0)})))
    assert lo[sec(9, 59)] == () and lo[sec(10, 0)] == (14980.0,)


def test_the_swing_size_sets_when_a_swing_is_known():
    spike = {"08:10": up(15020.0)}                   # 15 min: the bar 08:00-08:15, known 08:30; 30 min: 08:00-08:30, known 09:00; 60 min: 08:00-09:00, known 10:00
    for swing, known in (("15", sec(8, 30)), ("30", sec(9, 0)), ("60", sec(10, 0))):
        lv = dict((x[0], x[1]) for x in levels({"swing": swing}, day(spike)))
        assert lv[known - 60] == () and lv[known] == (15020.0,), swing
    take = {**spike, "09:40": up(15025.0, 15010.0)}                                    # 09:40 is before 10:00: with 60-minute bars the 08:00 bar is no swing at all
    assert signals({"swing": "15"}, day(take)) == [(sec(9, 41), "short")] and signals({"swing": "30"}, day(take)) == [(sec(9, 41), "short")]
    assert signals({"swing": "60"}, day(take)) == []
    assert signals({"swing": "60"}, day({**spike, "10:05": up(15025.0, 15010.0)})) == [(sec(10, 6), "short")]
    assert SF.Sfp.defaults()["swing"] == "60"


def test_the_high_must_be_strictly_above_both_neighbours():
    assert signals({}, day({**HIGH, "09:20": up(15020.0), "09:40": up(15025.0, 15010.0)})) == []       # the bar after it has the same high
    assert signals({}, day({**HIGH, "08:50": up(15020.0), "09:40": up(15025.0, 15010.0)})) == []       # the bar before it has the same high
    assert signals({}, day({**HIGH, "09:20": up(15020.0 - TICK), "09:40": up(15025.0, 15010.0)})) == [(sec(9, 41), "short")]
    assert signals({}, day({**LOW, "09:20": dn(14980.0), "09:40": dn(14975.0, 14990.0)})) == []
    assert signals({}, day({**LOW, "08:50": dn(14980.0 + TICK), "09:40": dn(14975.0, 14990.0)})) == [(sec(9, 41), "long")]


def test_the_first_swing_bar_of_the_day_is_never_a_swing():
    p = {"sess": "asia"}
    assert signals(p, day({"00:05": up(15020.0), "00:50": up(15025.0, 15010.0)})) == []                # 00:00-00:15 has no bar before it
    assert signals(p, day({"00:20": up(15020.0), "00:50": up(15025.0, 15010.0)})) == [(sec(0, 51), "short")]
    lv = dict((x[0], x[1]) for x in levels(p, day({"00:20": up(15020.0)})))
    assert lv[sec(0, 44)] == () and lv[sec(0, 45)] == (15020.0,)                                       # the earliest a 15-minute swing can be known
    # 60-minute bars: the first swing is known at 03:00, so an asia idea never trades
    assert signals({**p, "swing": "60"}, day({"01:20": up(15020.0), "02:10": up(15025.0, 15010.0), "02:50": up(15030.0, 15010.0)})) == []


def test_a_new_swing_does_not_touch_the_older_levels():
    # swing highs 15030 (08:30 bar) and 15020 (09:00 bar), swing lows 14970 (08:45 bar) and 14980 (09:15 bar, known 09:45)
    g = {"08:35": up(15030.0), "09:05": up(15020.0), "08:50": dn(14970.0), "09:20": dn(14980.0)}
    lv = {x[0]: x[1:] for x in levels({}, day(g))}
    assert lv[sec(9, 0)] == ((15030.0,), ()) and lv[sec(9, 15)] == ((15030.0,), (14970.0,))
    assert lv[sec(9, 30)] == ((15030.0, 15020.0), (14970.0,)) and lv[sec(9, 45)] == ((15030.0, 15020.0), (14970.0, 14980.0))


# ---- (iii) the levels are followed all day; the signal is inside the session only ---------------------------------------------------------------------

def test_a_level_taken_before_the_session_is_gone():
    early = {"08:35": up(15020.0), "09:10": up(15025.0, 15010.0)}                      # known 09:00, taken at 09:10: before the 09:30 session
    assert signals({}, day(early)) == []
    assert signals({}, day({**early, "09:40": up(15022.0, 15010.0)})) == []            # ... the level is gone (15025, the new swing high, is not reached)
    assert signals({"sess": "pre"}, day(early)) == [(sec(9, 11), "short")]             # an 08:25-09:30 idea trades that same failure
    assert signals({}, day({"08:35": up(15020.0), "09:40": up(15022.0, 15010.0)})) == [(sec(9, 41), "short")]


def test_entries_happen_only_inside_the_session():
    g = {**HIGH, "11:10": up(15025.0, 15010.0)}
    assert decisions({"sess": "nyam"}, day(g)) == [] and decisions({"sess": "mid"}, day(g)) == [(sec(11, 11), "short", True)]
    assert decisions({"sess": "pm"}, day(g)) == [] and decisions({"sess": "pm"}, day({**HIGH, "13:40": up(15025.0, 15010.0)})) == [(sec(13, 41), "short", True)]


def test_no_entry_in_the_last_five_minutes_of_a_session_nor_after_it():
    for sess, end in (("nyam", sec(11)), ("mid", sec(13, 30)), ("pm", sec(15, 58))):
        m = (end - 420) // 60                                                          # the minute that closes at end - 6 min
        ok = day({**HIGH, "%02d:%02d" % divmod(m, 60): up(15025.0, 15010.0)})
        assert decisions({"sess": sess}, ok) == [(end - 360, "short", True)], sess
        late = day({**HIGH, "%02d:%02d" % divmod(m + 1, 60): up(15025.0, 15010.0)})    # it closes at end - 5 min: too late
        assert decisions({"sess": sess}, late) == [], sess


def test_the_idea_bar_size_decides_and_the_entry_is_the_next_bars_open():
    # a 60-minute swing high at 04:10 (the bar 04:00-05:00, known 06:00); the 06:16 minute takes it and closes back
    g = {"04:10": up(15020.0), "06:16": up(15025.0, 15010.0)}
    p = {"sess": "london", "swing": "60"}
    for tf, at in ((1, sec(6, 17)), (5, sec(6, 20)), (15, sec(6, 30))):
        d = decisions({**p, "tf": str(tf)}, day(g))
        assert d == [(at, "short", True)], tf
        _, res = run({**p, "tf": str(tf)}, day(g))
        t, ms0 = res.trades[0], ns("00:00") // 1_000_000
        assert at * 1000 + ms0 <= t["entry_ms"] < at * 1000 + ms0 + tf * 60_000 and t["side"] == "short", tf
    # the 06:18 minute closes above the level again: the 1-minute bar at 06:17 has failed already, the 5-minute bar 06:15-06:20 has not (dead level)
    g2 = {**g, "06:18": (PX, 15023.0, PX - TICK, 15022.0, 40), "06:19": (15022.0, 15023.0, 15021.0, 15022.0, 40)}
    assert [x[:2] for x in decisions({**p, "tf": "1"}, day(g2))] == [(sec(6, 17), "short")]
    assert decisions({**p, "tf": "5"}, day(g2)) == []
    assert decisions({**p, "tf": "15"}, day(g2)) == [(sec(6, 30), "short", True)]       # (by 06:30 the price is back under it)


def test_an_evening_idea_reads_the_evening_before_and_a_day_idea_does_not():
    eve = flat(360)                                                                    # 18:00-23:59 of the evening before the trade date
    eve[20] = up(15020.0)                                                              # 18:20: the swing bar 18:15-18:30, known 18:45
    eve[60] = up(15025.0, 15010.0)                                                     # 19:00 takes it and closes back
    t = minute_tape(eve + day({"09:40": up(15035.0, 15010.0)}), "18:00", D - dt.timedelta(days=1))
    tape = S.Tape(t.root, D, t.contract, t.ts, t.px, t.size)                           # the tape of trade date D holds its evening
    got = signals({"sess": "eve"}, None, tape=tape, segment="eve")
    assert got == [(sec(19, 1) - 86400, "short")]                                      # seconds before 00:00 of the trade date
    # the nyam idea starts its swing bars at 00:00: the evening's highs (15020, 15025) are not levels for it, the 09:40 bar takes nothing
    assert signals({}, None, tape=tape) == []
    lv = levels({}, None, tape=tape)
    assert all(x[1] == () for x in lv if x[0] <= sec(9, 41))


# ---- (iv) max_tr, one position at a time, dir ---------------------------------------------------------------------------------------------------------

FIVE = {"07:05": up(15100.0), "07:35": up(15090.0), "08:05": up(15080.0), "08:35": up(15070.0), "09:05": up(15060.0),       # five swing highs, each lower
        "09:35": up(15065.0, 15010.0), "09:40": up(15075.0, 15010.0), "09:46": up(15085.0, 15010.0), "09:50": up(15095.0, 15010.0),
        "10:01": up(15105.0, 15010.0)}                                                                                      # ... taken one by one
FIVE_AT = [sec(9, 36), sec(9, 41), sec(9, 47), sec(9, 51), sec(10, 2)]


def test_max_tr_defaults_to_three_and_caps_the_entries_of_a_session():
    assert SF.Sfp.defaults()["max_tr"] == 3
    bars = day(FIVE)
    assert signals({}, bars) == [(s, "short") for s in FIVE_AT]
    p = {k: v for k, v in BASE.items() if k != "max_tr"}
    cls = type("Spy", (Spy,), {"log": []})
    st = cls({**p, "exit_bars": 1})                                  # the default max_tr (3); each trade leaves one bar after its fill
    st.ROLLS = frozenset()
    S.run_session(st, tape_of(bars), daily=list(DAILY), on_error="raise")
    assert st.p["max_tr"] == 3 and cls.log == [(s, "short", True) for s in FIVE_AT[:3]]
    for m in (1, 2, 4, 5):
        assert decisions({"max_tr": m, "exit_bars": 1}, bars) == [(s, "short", True) for s in FIVE_AT[:m]], m


def test_one_position_at_a_time_and_a_level_taken_while_a_trade_is_open_is_gone():
    bars = day(FIVE)
    _, res = run({"max_tr": 5, "exit_bars": 2}, bars)
    tr = sorted(res.trades, key=lambda t: t["entry_ms"])
    assert len(tr) == 5 and all(a["exit_ms"] <= b["entry_ms"] for a, b in zip(tr, tr[1:]))
    # without an exit the one open trade blocks every later failure
    _, res = run({"max_tr": 5}, bars)
    assert len(res.trades) == 1
    # the trade leaves after 7 bars (09:43): the failures at 09:41 are not traded and their level is not offered again; 09:47 is the next entry
    assert decisions({"max_tr": 5, "exit_bars": 7}, bars)[:2] == [(sec(9, 36), "short", True), (sec(9, 47), "short", True)]
    again = day({**FIVE, "09:44": up(15072.0, 15010.0)})             # above 15070 once more, flat again: that level went at 09:41
    assert decisions({"max_tr": 5, "exit_bars": 7}, again)[:2] == [(sec(9, 36), "short", True), (sec(9, 47), "short", True)]


def test_dir_runs_one_side_only_and_both_is_the_default():
    assert SF.Sfp.defaults()["dir"] == "both"
    hi, lo = day({**HIGH, "09:40": up(15025.0, 15010.0)}), day({**LOW, "09:40": dn(14975.0, 14990.0)})
    placed = lambda p, b: [x[1] for x in decisions(p, b) if x[2]]  # noqa: E731  (a blocked side is asked and not placed)
    assert placed({"dir": "short"}, hi) == ["short"] and placed({"dir": "long"}, hi) == []
    assert placed({"dir": "long"}, lo) == ["long"] and placed({"dir": "short"}, lo) == []
    assert placed({}, hi) == ["short"] and placed({}, lo) == ["long"]
    # a level whose signal was switched off by dir is gone all the same
    assert placed({"dir": "long"}, day({**HIGH, "09:40": up(15025.0, 15010.0), "09:42": up(15022.0, 15010.0)})) == []


# ---- (v) flat by 15:58 and the standard exits -----------------------------------------------------------------------------------------------------------

def test_a_trade_with_no_stop_hit_is_flat_by_15_58_and_the_standard_stop_acts():
    for sess, at in (("nyam", "09:40"), ("mid", "11:10"), ("pm", "13:40")):
        _, res = run({"sess": sess}, day({**HIGH, at: up(15025.0, 15010.0)}))
        assert len(res.trades) == 1 and res.trades[0]["side"] == "short" and res.trades[0]["exit_ms"] <= (ns("15:58") // 1_000_000) + 60_000, sess
    # a stop of the standard table acts as in every family: 10 points, and the price goes 30 against the short
    _, res = run({"stop_val": 10.0, "tgt_r": 1.0}, day({**HIGH, "09:40": up(15025.0, 15010.0), "09:45": up(15040.0, 15030.0)}))
    t = res.trades[0]
    assert t["side"] == "short" and t["net"] < 0 and t["exit_ms"] < ns("09:47") // 1_000_000


# ---- (vi) NO LOOK-AHEAD -------------------------------------------------------------------------------------------------------------------------------------

MIX = {**FIVE, "08:20": dn(14950.0), "08:50": dn(14960.0), "09:38": dn(14955.0, 14990.0), "09:55": dn(14945.0, 14990.0)}      # + two swing lows, taken at 09:38 and 09:55


def test_a_future_bar_cannot_change_an_earlier_signal():
    bars = day(MIX)
    tape = tape_of(bars)
    sig = signals({}, bars, tape=tape)
    assert len(sig) == 7 and {x[1] for x in sig} == {"long", "short"}
    for cut in [x[0] for x in sig] + [sec(9, 30), sec(9, 44, 30)]:   # the signal AT the cut stands whatever prints from that second on
        got = signals({}, bars, tape=garble(tape, ns("00:00") + cut * S.NS))
        assert [x for x in got if x[0] <= cut] == [x for x in sig if x[0] <= cut], cut
    params = {"exit_bars": 2, "max_tr": 5}
    clean = decisions(params, bars, tape=tape)
    assert len(clean) == 5
    for cut in [x[0] for x in clean[:-1]]:
        got = decisions(params, bars, tape=garble(tape, ns("00:00") + cut * S.NS))
        assert [x for x in got if x[0] <= cut] == [x for x in clean if x[0] <= cut], cut


def test_the_levels_at_a_decision_are_made_of_ended_swing_bars_only():
    bars = day(MIX)
    tape = tape_of(bars)
    clean = levels({}, bars, tape=tape)
    for cut in (sec(8, 45), sec(9, 0), sec(9, 30), sec(9, 37), sec(9, 45), sec(10, 0)):
        dirty = levels({}, bars, tape=garble(tape, ns("00:00") + cut * S.NS))
        assert [x for x in dirty if x[0] <= cut] == [x for x in clean if x[0] <= cut], cut
    # a level is first there exactly at the end of the swing bar AFTER its swing, never while that bar is still forming, whatever it holds so far
    for swing, w in (("15", 900), ("30", 1800), ("60", 3600)):
        n = 0
        for rb in (flat(60) + rand_bars(900, 3, p0=PX, step=4.0), flat(60) + wicky(900, 11), flat(60) + wicky(900, 21)):
            got = levels({"swing": swing, "sess": "pm"}, rb)         # (a pm idea is replayed to 15:58)
            sw = [(max(b[1] for b in rb[j:j + w // 60]), min(b[2] for b in rb[j:j + w // 60])) for j in range(0, 960, w // 60)]
            for j in range(1, len(sw) - 1):
                if (j + 2) * w > sec(15, 55) or any(sw[i] == sw[j] for i in range(j)):       # (an earlier bar with the very same high and low: skipped)
                    continue
                if sw[j][0] > sw[j - 1][0] and sw[j][0] > sw[j + 1][0] and not any(sw[i][0] == sw[j][0] for i in range(j)):
                    assert min((x[0] for x in got if sw[j][0] in x[1]), default=None) == (j + 2) * w, (swing, j)
                    n += 1
                if sw[j][1] < sw[j - 1][1] and sw[j][1] < sw[j + 1][1] and not any(sw[i][1] == sw[j][1] for i in range(j)):
                    assert min((x[0] for x in got if sw[j][1] in x[2]), default=None) == (j + 2) * w, (swing, j)
                    n += 1
        assert n >= 10, (swing, n)


def test_a_bar_closed_late_after_a_hole_in_the_tape_does_not_read_the_unfinished_swing_bar():
    # 5-minute bars, 15-minute swing bars. The minutes 09:54-09:58 never printed, so the Template closes the bar 09:50-09:55 late: at 10:00:00, when
    # the 09:59 minute bar arrives and BEFORE that minute is added. The 09:59 minute holds the high (15030) of the swing bar 09:45-10:00, which
    # makes the bar before it (09:30-09:45, high 15020) no swing at all. A rule that took the wall clock (10:00) of that late close would call the
    # bar 09:45-10:00 ended without its last minute, make 15020 a level and sell the 09:55-10:00 bar.
    bars = day({"09:35": up(15020.0), "09:59": up(15030.0)})
    t = tape_of(bars)
    keep = ~((t.ts >= ns("09:54")) & (t.ts < ns("09:59")))
    hole = S.Tape(t.root, t.date, t.contract, t.ts[keep], t.px[keep], t.size[keep])
    p = {"tf": "5"}
    assert signals(p, bars, tape=hole) == [] and signals(p, bars) == []
    lv = levels(p, bars, tape=hole)
    assert [x[0] for x in lv].count(sec(10, 0)) == 2                 # two closes at the 10:00:00 event: the late one (09:50-09:55) and 09:55-10:00
    assert all(15020.0 not in x[1] for x in lv) and (sec(10, 15), (15030.0,), ()) in lv
    # the same hole with a quiet 09:59: 09:30-09:45 is a swing, known at the 10:00 close and not at the late close before it
    quiet = day({"09:35": up(15020.0)})
    t = tape_of(quiet)
    hole = S.Tape(t.root, t.date, t.contract, t.ts[keep], t.px[keep], t.size[keep])
    at = [x for x in levels(p, quiet, tape=hole) if x[0] == sec(10, 0)]
    assert [x[1] for x in at] == [(), (15020.0,)]


# ---- (vii) the rule against an independent restatement, on random days --------------------------------------------------------------------------------------

def reference(bars, tf, sess, swing):
    """Every failure at a live swing level inside the session as (second, side), from the written rule alone: at each close everything is worked
    out again from the minute bars that have ended."""
    s0, s1 = S.SESS[sess]
    sw = [(max(b[1] for b in bars[j:j + swing]), min(b[2] for b in bars[j:j + swing])) for j in range(0, len(bars), swing)]       # swing bar j = minutes [j x swing, (j + 1) x swing)
    dead_hi, dead_lo, out = set(), set(), []
    for m in range(tf, len(bars) + 1, tf):                           # the tf bar of the minutes [m - tf, m) closes at minute m
        end = m * 60
        ch = bars[m - tf:m]
        h, l, c = max(b[1] for b in ch), min(b[2] for b in ch), ch[-1][3]
        n = m // swing                                               # the swing bars that have ended by this close: 0 .. n - 1
        short = long = False
        for j in range(1, n - 1):                                    # bar j with a bar before it and an ended bar after it
            if j not in dead_hi and sw[j][0] > sw[j - 1][0] and sw[j][0] > sw[j + 1][0] and h > sw[j][0]:
                dead_hi.add(j)
                short = short or c < sw[j][0]
            if j not in dead_lo and sw[j][1] < sw[j - 1][1] and sw[j][1] < sw[j + 1][1] and l < sw[j][1]:
                dead_lo.add(j)
                long = long or c > sw[j][1]
        if short != long and s0 < end <= s1 and end < s1 - 300:
            out.append((end, "short" if short else "long"))
    return out


@pytest.mark.parametrize("swing", [15, 30, 60])
@pytest.mark.parametrize("sess", ["asia", "london", "pre", "nyam", "mid", "pm"])
@pytest.mark.parametrize("tf", [1, 5, 15])
def test_the_signals_equal_the_written_rule_on_random_days(tf, sess, swing):
    n = 0
    days = [flat(60) + rand_bars(900, seed, p0=PX, step=4.0 if seed % 2 else 8.0) for seed in (3, 11, 21, 8)]
    days += [flat(60) + wicky(900, seed) for seed in range(40, 52)]
    for i, bars in enumerate(days):
        want = reference(bars, tf, sess, swing)
        got = signals({"swing": str(swing), "tf": str(tf), "sess": sess}, bars)
        assert got == want, (i, got[:5], want[:5])
        n += len(want)
    if (sess, swing) == ("asia", 60):
        assert n == 0                                                # the first 60-minute swing is known at 03:00, the end of the session
    else:
        assert n > 0, "the random days never failed at a swing: the comparison would be empty"


# ---- (viii) the settings and the registry ----------------------------------------------------------------------------------------------------------------------

def test_the_settings_and_their_limits():
    d, sc = SF.Sfp.defaults(), SF.Sfp.schema()
    assert (d["swing"], d["max_tr"], d["dir"]) == ("60", 3, "both")
    assert sc["swing"] == ("choice", ("15", "30", "60")) and sc["max_tr"] == ("int", 1, 5)
    for bad in ({"swing": "5"}, {"swing": "45"}, {"swing": 60}, {"swing": "120"}, {"max_tr": 0}, {"max_tr": 6}, {"max_tr": 1.5}, {"dir": "up"}, {"levels": "pd"}):
        with pytest.raises(ValueError):
            SF.Sfp({"tf": "5", **bad})
    for ok in ({"swing": "15"}, {"swing": "30"}, {"swing": "60"}, {"max_tr": 1}, {"max_tr": 5}, {"dir": "short"}):
        SF.Sfp({"tf": "5", **ok})


def test_the_registry_holds_sfp_as_written_and_it_is_a_block():
    assert families.ERRORS == {}
    cls, inputs, both, notes = families.REGISTRY["sfp"]
    lib = families.library("sfp")
    assert cls is SF.Sfp and inputs == {} and both is False and cls.FEATURES == () and cls.SCREEN_TFS == ("1", "5", "15")
    assert families.MODULE_OF["sfp"] == "sfp" and lib["roots"] == ("NQ", "ES", "GC") and not lib["l2"] and not lib["weak"]
    assert lib["mirror"] is None and lib["complexity"] == 7 and lib["variants"] == [{"swing": "15"}, {"swing": "30"}, {"swing": "60"}]
    assert len(lib["rationale"]) > 60 and "swing" in notes
    from families import blocks as B
    assert issubclass(B.WRAPPED["sfp"], SF.Sfp) and B.BASES["sfp"][0] is SF.Sfp and B.B_sfp is B.WRAPPED["sfp"]
    with pytest.raises(ValueError):
        B.WRAPPED["sfp"]({"tf": "5", "stop_mode": "rng"})             # the family has no structure height: only the standard table's stops
    for s in RM.DAY_PASSES:                                           # it runs in every session
        assert cls({"tf": "5", "sess": s, "hold_to": "day"}).sessions() == [s]


# ---- (ix) real BUILD days: the invariants of the code check, at 1 worker -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_real_build_days_hold_the_window_one_position_and_the_flat_time(root):
    real_days()
    days = days_of(root, 4)
    hd = {"tf": "5", "hold_to": "day", "stop_mode": "atr", "stop_val": 1.5, "tgt_r": 2.0}
    specs = [(SF.Sfp, {**hd, "sess": s, "swing": w}) for s in ("nyam", "mid", "pm") for w in ("15", "30", "60")]
    out = S.run_many(specs, root=root, days=days, period="build", workers=1, on_error="raise")
    again = S.run_many(specs, root=root, days=days, period="build", workers=1, on_error="raise")
    assert [r["trades"] for r in out] == [r["trades"] for r in again]
    assert sum(r["skipped_by_error"] for r in out) == 0
    total = 0
    for (cls, p), r in zip(specs, out):
        s0, s1 = S.SESS[p["sess"]]
        last, per_day = {}, {}
        for t in sorted(r["trades"], key=lambda t: t["entry_ms"]):
            d = S._date(t["date"])
            es = (t["entry_ms"] // 1000) - S.et_ns(d, "00:00") // S.NS
            assert s0 < es < s1 - 300 + 120, (p, t["date"], es)                       # inside the window (a fill a little after the decision)
            assert t["exit_ms"] <= S.et_ns(d, S.day_flat(d, root)) // 1_000_000 + 60_000
            assert last.get(t["date"], 0) <= t["entry_ms"]                            # one position at a time
            last[t["date"]] = t["exit_ms"]
            per_day[t["date"]] = per_day.get(t["date"], 0) + 1
            total += 1
        assert all(v <= 3 for v in per_day.values())                                  # max_tr: three a session
    assert total > 0
