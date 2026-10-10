"""IFVG: the `ifvg` entry trigger (families/ifvg.py), written test-first from its rule.

THE RULE UNDER TEST (the "IFVG" entry of 9O6JU5_xTd8 and the "failed gap squeeze" of 3LrXQDS187Y, research/edge-library/videos):
    gap       = fvg's: three tf bars, bar 3's low above bar 1's high (UP, zone bar 1's high .. bar 3's low) or bar 3's high below bar 1's low
                (DOWN, zone bar 3's high .. bar 1's low); all three closed inside the session; zone >= max(min_gap x ATR14 of the tf, one tick)
    open      = for the `age` tf bars after bar 3, in its own session only
    SHORT     = a tf bar CLOSES strictly below the lower edge of an open UP gap -> market at the next bar's open
    LONG      = a tf bar closes strictly above the upper edge of an open DOWN gap
    once      = an inverted gap is used up; several gaps of one side inverted by one bar are one signal
    entries   = inside the idea's session, up to max_tr a session, one position at a time; the standard exits, flat 15:58.
Synthetic days with EXACT numbers cover each behaviour; seeded random-walk days check the signal list against an independent restatement of the
rule at every bar size and session, and the gaps against fvg's own; the real BUILD days check the invariants (window, one position, flat 15:58)
at 1 worker. No net, win rate or profit factor is read.
"""
import pytest

import families
import l2sim as S
import run_menus as RM
from families import fvg as FV
from families import ifvg as IF
from test_blocks import DAILY, TICK, days_of, garble, minute_tape, ns, rand_bars, real_days

BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "max_tr": 5, "min_gap": 0.1}


def sec(h, m=0, s=0):
    return h * 3600 + m * 60 + s


def flat(n, px=15000.0, v=40):
    return [(px, px + TICK, px - TICK, px, v)] * n


def rest(n, px, v=40):
    """n quiet minutes one point either side of px."""
    return [(px, px + 1.0, px - 1.0, px, v)] * n


def bar(o, c, v=40):
    return (o, max(o, c), min(o, c), c, v)


def up_gap(base=15000.0):
    """Three minutes that leave an UP gap: bar 1 tops at base + 1, bar 2 runs to base + 10, bar 3 bottoms at base + 6 and closes at
    base + 11. The zone is base + 1 .. base + 6 (5 points)."""
    return [(base, base + 1.0, base - 1.0, base, 40), (base, base + 10.0, base, base + 10.0, 40), (base + 10.0, base + 12.0, base + 6.0, base + 11.0, 40)]


def mirror(bars, px=15000.0):
    return [(2 * px - o, 2 * px - l, 2 * px - h, 2 * px - c, v) for o, h, l, c, v in bars]


def stretch(bars, tf):
    """Every minute bar tf times: the tf bars of the result have the highs, lows and closes of `bars`."""
    return [b for b in bars for _ in range(tf)]


def day(g, at="09:30", pre=15000.0):
    """A full day of minute bars from 00:00 ET to 15:59: flat at `pre` until `at`, then the bars `g`, then flat at the last close."""
    b = flat(S._sec(at) // 60, pre) + list(g)
    return b + flat(960 - len(b), b[-1][3])


def tape_of(bars):
    return minute_tape(bars, "00:00")


def sec_of(ctx):
    return (ctx.now_ns - ns("00:00")) // S.NS


def run(params, bars, cls=None, tape=None):
    """One instance through one day (the explicit roll list: none). -> (the instance, the result)."""
    st = (cls or IF.Ifvg)({**BASE, **params})
    st.ROLLS = frozenset()
    res = S.run_session(st, tape or tape_of(bars), daily=list(DAILY), on_error="raise")
    return st, res


class Spy(IF.Ifvg):
    """Logs every entry decision: (second of the decision, side, an order was placed)."""
    log: list = []

    def _mkt(self, ctx, side, **kw):
        o = super()._mkt(ctx, side, **kw)
        type(self).log.append((sec_of(ctx), side, o is not None))
        return o


def decisions(params, bars, tape=None):
    cls = type("Spy", (Spy,), {"log": []})
    run(params, bars, cls, tape)
    return list(cls.log)


class Sig(IF.Ifvg):
    """Logs every signal the family sees (no order is placed, so every qualifying close shows): (second, side)."""
    seen: list = []

    def fam_signal(self, ctx):
        if self.go:
            type(self).seen.append((sec_of(ctx), "long" if self.go > 0 else "short"))


def signals(params, bars, tape=None):
    cls = type("Sig", (Sig,), {"seen": []})
    run(params, bars, cls, tape)
    return list(cls.seen)


def basic(k=7, close=15000.75):
    """09:30 on: ten flat minutes, an UP gap in the bars 09:40 / 09:41 / 09:42 (zone 15001 .. 15006, read at 09:43:00), k quiet minutes at
    15011, then one minute that closes at `close`."""
    return flat(10) + up_gap() + rest(k, 15011.0) + [bar(15011.0, close)]


# ---- (i) the inversion: a close through the whole gap, against it -----------------------------------------------------------------------------

def test_a_close_below_an_up_gap_is_a_short_and_a_close_above_a_down_gap_is_a_long():
    assert decisions({}, day(basic())) == [(sec(9, 51), "short", True)]                # the 09:50 bar closes at 15000.75, under the edge 15001
    assert decisions({}, day(mirror(basic()))) == [(sec(9, 51), "long", True)]         # the mirror: a DOWN gap 14994 .. 14999, a close at 14999.25


def test_a_close_exactly_on_the_edge_is_nothing_and_one_tick_through_it_is_the_signal():
    assert signals({}, day(basic(close=15001.0))) == []
    assert signals({}, day(basic(close=15001.0 - TICK))) == [(sec(9, 51), "short")]
    assert signals({}, day(mirror(basic(close=15001.0)))) == []
    assert signals({}, day(mirror(basic(close=15001.0 - TICK)))) == [(sec(9, 51), "long")]


def test_a_close_inside_the_gap_is_nothing_it_must_close_through_the_whole_gap():
    assert signals({}, day(basic(close=15003.0))) == []                                # under the near edge 15006, not under the far edge 15001
    assert signals({}, day(basic(close=15006.0 - TICK))) == []


def test_a_wick_through_the_gap_that_closes_back_is_nothing_and_the_gap_stays_open():
    g = flat(10) + up_gap() + rest(2, 15011.0) + [(15011.0, 15011.0, 15000.0, 15008.0, 40)] + rest(4, 15011.0)
    assert signals({}, day(g)) == []                                                   # the 09:45 bar trades to 15000 and closes at 15008
    assert signals({}, day(g + [bar(15011.0, 15000.75)])) == [(sec(9, 51), "short")]   # ... and the gap is still there for a close through it


def test_a_gap_inverts_once():
    # 09:50 closes under the gap (the signal), 09:51 closes back inside it at 15003, 09:52 closes under it again: no second signal
    g = basic() + [(15000.75, 15003.25, 15000.5, 15003.0, 40), bar(15003.0, 15000.5)] + flat(20, 15000.5)
    assert signals({}, day(g)) == [(sec(9, 51), "short")]


def test_several_gaps_inverted_by_one_bar_are_one_signal_and_all_of_them_are_used_up():
    two = flat(10) + up_gap() + rest(3, 15011.0) + up_gap(15011.0) + rest(3, 15022.0)   # gaps 15001 .. 15006 and 15012 .. 15017
    one_bar = day(two + [bar(15022.0, 15000.75)] + flat(20, 15000.75))
    assert signals({}, one_bar) == [(sec(9, 53), "short")]                              # the 09:52 bar closes under both
    st, _ = run({}, one_bar, type("Sig", (Sig,), {"seen": []}))
    assert [g for g in st.gaps if g[0] == "long"] == []
    # the same two gaps closed through one after the other are two signals
    steps = day(two + [bar(15022.0, 15011.5)] + rest(2, 15011.5) + [bar(15011.5, 15000.75)] + flat(20, 15000.75))
    assert signals({}, steps) == [(sec(9, 53), "short"), (sec(9, 56), "short")]


# ---- (ii) the gap: fvg's, with its size floor ---------------------------------------------------------------------------------------------------

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
    bars = day(basic())
    a = atr14(tf_bars(bars, 1))[9 * 60 + 42]                         # the ATR after the 09:42 bar (bar 3) has closed
    assert 1.0 < a < 3.0                                             # (the 5-point gap is a few ATR: min_gap around 5 / a decides)
    assert signals({"min_gap": 5.0 / a * 0.999}, bars) == [(sec(9, 51), "short")]
    assert signals({"min_gap": 5.0 / a * 1.001}, bars) == []
    later = atr14(tf_bars(bars, 1))[9 * 60 + 50]                     # the ATR after the closing bar (09:50) is bigger: read there, the gap
    assert later * (5.0 / a * 0.999) > 5.0 * 1.1                     # ... of the first line would have been too small. Bar 3's ATR is the one read


def test_a_gap_is_never_less_than_one_tick_even_with_min_gap_zero():
    def one(low3):                                                    # bar 3's low against bar 1's high (15001)
        g = flat(10) + [up_gap()[0], up_gap()[1], (15010.0, 15012.0, low3, 15011.0, 40)] + rest(7, 15011.0) + [bar(15011.0, 15000.75)]
        return signals({"min_gap": 0.0}, day(g))
    assert one(15001.0 + TICK) == [(sec(9, 51), "short")] and one(15001.0) == []


def test_the_gaps_are_fvgs_own_gaps_on_random_days():
    n = 0
    for tf in (1, 5, 15):                                             # the bar sizes both families run
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

            class LookI(IF.Ifvg):
                def fam_update(self, ctx):
                    super().fam_update(ctx)
                    b.extend((sec_of(ctx), g[0], g[1], g[2]) for g in self.gaps if g[3] == self.nb)

            for sess in ("london", "nyam", "pm"):
                a.clear()
                b.clear()
                for cls in (LookF, LookI):
                    st = cls({"hold_to": "day", "tf": str(tf), "sess": sess, "min_gap": 0.25})
                    st.ROLLS = frozenset()
                    S.run_session(st, tape, daily=list(DAILY), on_error="raise")
                assert a == b, (tf, seed, sess)
                n += len(a)
    assert n > 20


# ---- (iii) open for `age` bars, in its own session only -----------------------------------------------------------------------------------------

def test_a_gap_is_open_for_age_bars_after_bar_3_and_no_longer():
    # bar 3 is the 09:42 bar; with k quiet minutes after it the closing bar is bar k + 1 after bar 3
    assert signals({"age": 5}, day(basic(k=4))) == [(sec(9, 48), "short")]             # bar 5: still open
    assert signals({"age": 5}, day(basic(k=5))) == []                                  # bar 6: gone
    assert IF.Ifvg.defaults()["age"] == 30
    assert signals({}, day(basic(k=29))) == [(sec(10, 13), "short")]                   # the default: bar 30 still inverts it
    assert signals({}, day(basic(k=30))) == []
    assert signals({"age": 240}, day(basic(k=60))) == [(sec(10, 44), "short")]


def test_the_three_bars_must_close_inside_the_session():
    g = up_gap() + rest(7, 15011.0) + [bar(15011.0, 15000.75)]
    assert signals({}, day(g, at="09:29")) == []                                       # the 09:29 bar closes at 09:30:00: not inside 09:30-11:00
    assert signals({}, day(g, at="09:30")) == [(sec(9, 41), "short")]                  # the third close of the session is the first that can show a gap


def test_a_gap_of_an_earlier_session_is_not_this_sessions():
    g = up_gap() + rest(15, 15011.0) + [bar(15011.0, 15000.75)]                        # the gap at 10:50-10:52, the close through it at 11:08
    bars = day(g, at="10:50")
    assert signals({"sess": "mid"}, bars) == [] and signals({"sess": "nyam"}, bars) == []
    assert signals({"sess": "mid"}, day(g, at="11:00")) == [(sec(11, 19), "short")]
    # one instance that trades session after session (hold_to session, sess all): asia's gap (02:50-02:52) is not carried into london (from 03:00)
    every = {"hold_to": "session", "sess": "all"}
    assert signals(every, day(g, at="02:50")) == [] and signals(every, day(g, at="03:00")) == [(sec(3, 19), "short")]


def test_no_entry_in_the_last_five_minutes_of_a_session_nor_after_it():
    for sess, end in (("nyam", sec(11)), ("mid", sec(13, 30)), ("pm", sec(15, 58))):
        g = up_gap() + rest(7, 15011.0) + [bar(15011.0, 15000.75)]                     # the close through it is the 11th bar
        at = (end - 360) // 60 - 11                                                    # ... so it closes at end - 6 min
        ok = day(g, at="%02d:%02d" % divmod(at, 60))
        assert decisions({"sess": sess}, ok) == [(end - 360, "short", True)], sess
        late = day(g, at="%02d:%02d" % divmod(at + 1, 60))                             # the close through it at end - 5 min: too late
        assert decisions({"sess": sess}, late) == [], sess


def test_entry_is_the_next_bars_open_and_the_decision_is_the_signal_bars_close():
    for tf in (1, 5, 15, 30):
        g = stretch(up_gap() + rest(2, 15011.0) + [bar(15011.0, 15000.75)], tf)        # 6 tf bars from 03:00: the close through it is the 6th
        bars = day(g, at="03:00")
        p = {"tf": str(tf), "sess": "london"}
        d = decisions(p, bars)
        assert d == [(sec(3) + 6 * tf * 60, "short", True)], tf
        _, res = run(p, bars)
        t, first = res.trades[0], d[0][0]
        ms0 = ns("00:00") // 1_000_000
        assert first * 1000 + ms0 <= t["entry_ms"] < first * 1000 + ms0 + tf * 60_000 and t["side"] == "short", tf


# ---- (iv) max_tr, one position at a time, dir -------------------------------------------------------------------------------------------------

def waves(n):
    """n times: an UP gap, three quiet minutes, a minute that closes back under it, four quiet minutes (each wave starts 0.75 higher)."""
    g, b = flat(5), 15000.0
    for _ in range(n):
        g += up_gap(b) + rest(3, b + 11.0) + [bar(b + 11.0, b + 0.75)] + rest(4, b + 0.75)
        b += 0.75
    return day(g)


def test_max_tr_defaults_to_three_and_caps_the_entries_of_a_session():
    assert IF.Ifvg.defaults()["max_tr"] == 3
    bars = waves(7)
    assert len([x for x in signals({"dir": "short"}, bars) if x[1] == "short"]) == 7   # (seven closes through an up gap)
    p = {k: v for k, v in BASE.items() if k != "max_tr"}
    cls = type("Spy", (Spy,), {"log": []})
    st = cls({**p, "exit_bars": 1, "dir": "short"})                                    # the default max_tr (3); each trade leaves one bar after its fill
    st.ROLLS = frozenset()
    S.run_session(st, tape_of(bars), daily=list(DAILY), on_error="raise")
    assert st.p["max_tr"] == 3 and [x[2] for x in cls.log].count(True) == 3
    for m in (1, 2, 4, 5):
        got = decisions({"max_tr": m, "exit_bars": 1, "dir": "short"}, bars)
        assert [x[2] for x in got].count(True) == m, m


def test_one_position_at_a_time_and_a_gap_inverted_while_a_trade_is_open_is_used_up():
    bars = waves(5)
    _, res = run({"max_tr": 5, "exit_bars": 2, "dir": "short"}, bars)
    tr = sorted(res.trades, key=lambda t: t["entry_ms"])
    assert len(tr) == 5 and all(a["exit_ms"] <= b["entry_ms"] for a, b in zip(tr, tr[1:]))
    # without an exit the one open trade blocks every later close through a gap
    _, res = run({"max_tr": 5, "dir": "short"}, bars)
    assert len(res.trades) == 1
    # the second gap (15001.75 .. 15006.75) is closed through at 09:53 while the first trade is still open (it leaves after 40 bars, at 10:22):
    # it is used up, so the close under it at 10:34, with the instance flat again and the gap not yet too old (age 240), is no signal
    g = flat(5) + up_gap() + rest(3, 15011.0) + [bar(15011.0, 15000.75)] + rest(4, 15000.75)
    g += up_gap(15000.75) + rest(3, 15011.75) + [bar(15011.75, 15001.5)] + rest(40, 15003.0) + [bar(15003.0, 15001.0)] + flat(20, 15001.0)
    p = {"max_tr": 5, "exit_bars": 40, "dir": "short", "age": 240}
    assert decisions(p, day(g)) == [(sec(9, 42), "short", True)]
    _, res = run(p, day(g))
    assert len(res.trades) == 1 and res.trades[0]["exit_ms"] < ns("10:30") // 1_000_000
    # (the same close with the first trade gone before the second gap is closed through: it is traded)
    assert [x for x in decisions({**p, "exit_bars": 2}, day(g)) if x[2]] == [(sec(9, 42), "short", True), (sec(9, 53), "short", True)]


def test_dir_runs_one_side_only_and_both_is_the_default():
    assert IF.Ifvg.defaults()["dir"] == "both"
    up, dn = day(basic()), day(mirror(basic()))
    placed = lambda p, b: [x[1] for x in decisions(p, b) if x[2]]  # noqa: E731  (a blocked side is asked and not placed)
    assert placed({"dir": "short"}, up) == ["short"] and placed({"dir": "long"}, up) == []
    assert placed({"dir": "long"}, dn) == ["long"] and placed({"dir": "short"}, dn) == []
    assert placed({}, up) == ["short"] and placed({}, dn) == ["long"]


# ---- (v) flat by 15:58 and the standard exits ---------------------------------------------------------------------------------------------------

def test_a_trade_with_no_stop_hit_is_flat_by_15_58_and_the_standard_stop_acts():
    g = up_gap() + rest(7, 15011.0) + [bar(15011.0, 15000.75)]
    for sess, at in (("nyam", "09:40"), ("mid", "11:10"), ("pm", "13:40")):
        _, res = run({"sess": sess}, day(g, at=at))
        assert len(res.trades) == 1 and res.trades[0]["side"] == "short" and res.trades[0]["exit_ms"] <= (ns("15:58") // 1_000_000) + 60_000, sess
    # a stop of the standard table acts as in every family: 10 points, the price comes back up 20
    up = day(g + rest(5, 15000.75) + [bar(15000.75, 15020.0)] + flat(60, 15020.0), at="09:40")
    _, res = run({"stop_val": 10.0, "tgt_r": 1.0}, up)
    t = res.trades[0]
    assert t["side"] == "short" and t["net"] < 0 and t["exit_ms"] < ns("11:00") // 1_000_000


# ---- (vi) NO LOOK-AHEAD -----------------------------------------------------------------------------------------------------------------------------

def test_a_future_bar_cannot_change_an_earlier_signal():
    bars = waves(6)
    tape = tape_of(bars)
    params = {"exit_bars": 2, "max_tr": 5}
    clean = decisions(params, bars, tape=tape)
    assert len(clean) >= 5 and {x[1] for x in clean} == {"long", "short"}
    for cut in sorted({x[0] for x in clean})[:-1] + [sec(9, 37), sec(9, 44, 30)]:
        dirty = garble(tape, ns("00:00") + cut * S.NS)
        got = decisions(params, bars, tape=dirty)
        assert [x for x in got if x[0] <= cut] == [x for x in clean if x[0] <= cut], cut
        assert any(x[0] > cut for x in clean)                        # (there is a later decision the garbled prints could have bent)
    sig = signals({}, bars, tape=tape)
    assert len(sig) >= 6
    for cut in [x[0] for x in sig]:                                  # the signal AT the cut stands whatever prints from that second on
        got = signals({}, bars, tape=garble(tape, ns("00:00") + cut * S.NS))
        assert [x for x in got if x[0] <= cut] == [x for x in sig if x[0] <= cut], cut


def test_the_open_gaps_at_a_decision_are_made_of_closed_bars_only():
    bars = waves(4)
    tape = tape_of(bars)
    seen = []

    class Look(IF.Ifvg):
        def fam_update(self, ctx):
            super().fam_update(ctx)
            seen.append((sec_of(ctx), self.go, tuple(self.gaps)))

    a = []
    for t in (tape, garble(tape, ns("09:50"))):
        seen.clear()
        st = Look({**BASE})
        st.ROLLS = frozenset()
        S.run_session(st, t, daily=list(DAILY), on_error="raise")
        a.append([x for x in seen if x[0] <= sec(9, 50)])
    assert a[0] == a[1] and any(x[2] for x in a[0]) and any(x[1] for x in a[0])
    # a gap enters the list at bar 3's close and never earlier: its three bars are 09:35 / 09:36 / 09:37 here
    first = next(x for x in a[0] if x[2])
    assert first[0] == sec(9, 38) and first[2][0][:3] == ("long", 15006.0, 15001.0)


# ---- (vii) the rule against an independent restatement, on random days ------------------------------------------------------------------------------

def reference(bars, tf, sess, min_gap, age):
    """Every close through an open gap inside the session as (second, side), from the written rule alone. Also: did one close ever go through
    an up gap and a down gap at once (the rule says it cannot)."""
    s0, s1 = S.SESS[sess]
    tb = tf_bars(bars, tf)
    atr = atr14(tb)
    gaps, out, n_in, clash = [], [], 0, False                        # a gap: [kind, the edge a close must pass, the index of its bar 3]
    for n, (end, o, h, l, c) in enumerate(tb):
        if not s0 < end <= s1:
            continue
        n_in += 1
        sides = set()
        for g in gaps:
            if g[2] is None or n - g[2] > age:
                continue
            if (g[0] == "up" and c < g[1]) or (g[0] == "down" and c > g[1]):
                sides.add("short" if g[0] == "up" else "long")
                g[2] = None                                          # used up
        clash = clash or len(sides) == 2
        if len(sides) == 1 and end < s1 - 300:
            out.append((end, sides.pop()))
        if n_in >= 3:
            h1, l1, h3, l3 = tb[n - 2][2], tb[n - 2][3], h, l
            floor = max(min_gap * atr[n], TICK)
            if l3 > h1 and l3 - h1 >= floor:
                gaps.append(["up", h1, n])
            elif h3 < l1 and l1 - h3 >= floor:
                gaps.append(["down", l1, n])
    return out, clash


def random_day(seed, tf, plain):
    """A seeded random-walk day from 01:00 after a flat hour. plain: 900 random minutes (few gaps on big bars). Not plain: one random bar per
    tf bar, each written tf times, so the tf bars are the random bars themselves and gaps are as common at 30 minutes as at 1."""
    return flat(60) + (rand_bars(900, seed, p0=15000.0, step=6.0) if plain else stretch(rand_bars(900 // tf, seed, p0=15000.0, step=6.0), tf))


SETS = ((0.1, 30), (0.25, 30), (0.1, 5), (0.5, 240), (0.0, 12))      # (min_gap, age)


@pytest.mark.parametrize("sess", ["asia", "london", "pre", "nyam", "mid", "pm"])
@pytest.mark.parametrize("tf", [1, 5, 15, 30])
def test_the_signals_equal_the_written_rule_on_random_days(sess, tf):
    n = 0
    days = [(seed, True) for seed in (3, 11, 21, 33, 5)] + [(seed, False) for seed in range(100, 110 if tf < 15 else 180)]
    for i, (seed, plain) in enumerate(days):
        min_gap, age = SETS[i % len(SETS)]
        bars = random_day(seed, tf, plain)
        want, clash = reference(bars, tf, sess, min_gap, age)
        got = signals({"min_gap": min_gap, "age": age, "tf": str(tf), "sess": sess}, bars)
        assert got == want, (seed, plain, got[:5], want[:5])
        assert not clash
        n += len(want)
    s0, s1 = S.SESS[sess]
    closes = [e for e in range(tf * 60, 86400, tf * 60) if s0 < e <= s1]
    if any(e < s1 - 300 for e in closes[3:]):                        # a close is left after the first one that can show a gap
        assert n > 0, "the random days never closed through a gap: the comparison would be empty"
    else:
        assert n == 0 and (sess, tf) in (("pre", 30), ("nyam", 30))  # three 30-minute closes: the third shows the first gap, none is left to close through it


# ---- (viii) the settings and the registry --------------------------------------------------------------------------------------------------------------

def test_the_settings_and_their_limits():
    d, sc = IF.Ifvg.defaults(), IF.Ifvg.schema()
    assert (d["min_gap"], d["age"], d["max_tr"], d["dir"]) == (0.25, 30, 3, "both")
    assert sc["min_gap"] == ("float", 0.0, 10.0) and sc["age"] == ("int", 5, 240) and sc["max_tr"] == ("int", 1, 5)
    assert sc["min_gap"] == FV.Fvg.schema()["min_gap"] and d["min_gap"] == FV.Fvg.defaults()["min_gap"]
    for bad in ({"min_gap": -0.1}, {"min_gap": 10.5}, {"age": 4}, {"age": 241}, {"age": 7.5}, {"max_tr": 0}, {"max_tr": 6}, {"dir": "up"}, {"mode": "go"}):
        with pytest.raises(ValueError):
            IF.Ifvg({"tf": "5", **bad})
    for ok in ({"min_gap": 0.0}, {"min_gap": 10.0}, {"age": 5}, {"age": 240}, {"max_tr": 1}, {"max_tr": 5}, {"dir": "short"}):
        IF.Ifvg({"tf": "5", **ok})


def test_the_registry_holds_ifvg_as_written_and_it_is_a_block():
    assert families.ERRORS == {}
    cls, inputs, both, notes = families.REGISTRY["ifvg"]
    lib = families.library("ifvg")
    assert cls is IF.Ifvg and inputs == {} and both is False and cls.FEATURES == () and cls.SCREEN_TFS == ("1", "5", "15", "30")
    assert families.MODULE_OF["ifvg"] == "ifvg" and lib["roots"] == ("NQ", "ES", "GC") and not lib["l2"] and not lib["weak"]
    assert lib["mirror"] is None and lib["complexity"] == 7 and lib["variants"] == [{"min_gap": 0.1}, {"min_gap": 0.25}, {"min_gap": 0.5}]
    assert len(lib["rationale"]) > 60 and "inver" in notes
    from families import blocks as B
    assert issubclass(B.WRAPPED["ifvg"], IF.Ifvg) and B.BASES["ifvg"][0] is IF.Ifvg and B.B_ifvg is B.WRAPPED["ifvg"]
    with pytest.raises(ValueError):
        B.WRAPPED["ifvg"]({"tf": "5", "stop_mode": "rng"})            # the family has no structure height: only the standard table's stops
    for s in RM.DAY_PASSES:                                           # it trades in every session
        assert cls({"tf": "5", "sess": s, "hold_to": "day"}).sessions() == [s]


# ---- (ix) real BUILD days: the invariants of the code check, at 1 worker ---------------------------------------------------------------------------------

@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_real_build_days_hold_the_window_one_position_and_the_flat_time(root):
    real_days()
    days = days_of(root, 4)
    hd = {"tf": "5", "hold_to": "day", "stop_mode": "atr", "stop_val": 1.5, "tgt_r": 2.0}
    specs = [(IF.Ifvg, {**hd, "sess": s, "min_gap": m}) for s in ("nyam", "mid", "pm") for m in (0.1, 0.25)]
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
