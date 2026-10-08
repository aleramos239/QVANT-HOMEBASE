"""NOISE BAND: the `noise_band` entry trigger (families/noise.py), written test-first from its rule.

THE RULE UNDER TEST (Zarattini / Aziz / Barbon 2024 + Maroy 2025 "noise-area momentum"; Conti's "vault break"):
    reference = the OPEN of an anchor (rth: the 09:30 ET minute bar; globex: the 01:00 ET minute bar = midnight Central)
    A         = the toolkit's daily ATR(14) over the days BEFORE the trade date (Template.datr, the source `gap` and `mid_fade` use)
    band      = reference +/- k x A, fixed for the day
    LONG      = a tf bar CLOSES above reference + k x A AND above the VWAP since the anchor -> market at the next bar's open
    SHORT     = the mirror; entries only inside the idea's session; up to max_tr a session; one position at a time.
A synthetic day with EXACT numbers (daily ranges of 100 -> A = 100, k = 0.25 -> a band of 25 points) covers each behaviour; a seeded
random-walk day checks the signal list against an independent restatement of the rule at every bar size, session and anchor;
the real BUILD days check the invariants (window, one position, flat 15:58) at 1 worker. No net, win rate or profit factor is read.
"""
import datetime as dt

import numpy as np
import pytest

import families
import l2sim as S
import run_menus as RM
from families import noise as NB
from test_blocks import D, TICK, days_of, garble, minute_tape, ns, rand_bars, real_days

K = 0.25
A = 100.0
BAND = K * A                                                       # 25 points
BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "max_tr": 5, "k": K}


def sec(h, m=0, s=0):
    return h * 3600 + m * 60 + s


def rows(ranges):
    """Daily bars dated before D: high 15000 + range, low 15000, close 15050 -> every true range is the range itself."""
    return [{"date": (D - dt.timedelta(days=len(ranges) - i)).isoformat(), "h": 15000.0 + r, "l": 15000.0, "c": 15050.0, "contract": "NQM3"}
            for i, r in enumerate(ranges)]


DAILY = rows([100.0] * 25)                                         # Wilder ATR(14) = exactly 100.0


def wilder(rs):
    """Wilder ATR(14) of daily rows, restated here (the definition, not the engine's code)."""
    trs = [max(r["h"] - r["l"], abs(r["h"] - p["c"]), abs(r["l"] - p["c"])) for p, r in zip(rs, rs[1:])]
    a = sum(trs[:14]) / 14.0
    for x in trs[14:]:
        a = (a * 13.0 + x) / 14.0
    return a


def flat(n, px=15000.0, v=40):
    return [(px, px + TICK, px - TICK, px, v)] * n


def bar(o, c, v=40):
    return (o, max(o, c), min(o, c), c, v)


def day(g, pre=15000.0, at="09:30", head=None):
    """A full day of minute bars from 00:00 ET to 15:59: flat at `pre` until `at` (or the bars `head`, which must fill 00:00 .. `at`),
    then the bars `g`, then flat at the last close."""
    t = S._sec(at) // 60
    b = list(head) if head is not None else flat(t, pre)
    assert len(b) == t, (len(b), t)
    b += list(g)
    return b + flat(960 - len(b), b[-1][3])


def tape_of(bars):
    return minute_tape(bars, "00:00", D)


def sec_of(ctx):
    return (ctx.now_ns - ns("00:00")) // S.NS


def run(params, bars, daily=DAILY, cls=None, tape=None):
    """One instance through one day (the explicit roll list: none). -> (the instance, the result)."""
    st = (cls or NB.NoiseBand)({**BASE, **params})
    st.ROLLS = frozenset()
    res = S.run_session(st, tape or tape_of(bars), daily=daily, on_error="raise")
    return st, res


class Spy(NB.NoiseBand):
    """Logs every entry decision: (second of the decision, side, an order was placed)."""
    log: list = []

    def _mkt(self, ctx, side, **kw):
        o = super()._mkt(ctx, side, **kw)
        type(self).log.append((sec_of(ctx), side, o is not None))
        return o


def decisions(params, bars, daily=DAILY, tape=None):
    cls = type("Spy", (Spy,), {"log": []})
    run(params, bars, daily, cls, tape)
    return list(cls.log)


class Sig(NB.NoiseBand):
    """Logs every signal the family sees (no order is placed, so every qualifying close shows): (second, side)."""
    seen: list = []

    def fam_signal(self, ctx):
        if self.go:
            type(self).seen.append((sec_of(ctx), "long" if self.go > 0 else "short"))


def signals(params, bars, daily=DAILY, tape=None):
    cls = type("Sig", (Sig,), {"seen": []})
    run(params, bars, daily, cls, tape)
    return list(cls.seen)


# ---- (i) the band: the anchor's open, k x A, fixed for the day ------------------------------------------------------------------------------

def up_bars(first=15025.0, then=15025.25):
    """09:30 on: eight flat minutes, a minute that closes at `first`, then one that closes at `then`."""
    return flat(8) + [bar(15000.0, first), bar(first, then)] + flat(20, then)


def test_band_is_the_anchor_open_plus_and_minus_k_times_the_daily_atr():
    st, _ = run({}, day(up_bars()))
    assert st.ref == 15000.0 and st.up == 15000.0 + BAND and st.dn == 15000.0 - BAND


def test_the_reference_is_the_open_of_the_09_30_bar_not_the_close_before_it():
    head = flat(569, 15000.0) + [bar(15000.0, 14990.0)]            # the 09:29 bar closes at 14990; the 09:30 bar opens at 15010 (a gap)
    g = [bar(15010.0, 15010.0)] + flat(20, 15010.0)
    st, _ = run({}, day(g, head=head))
    assert st.ref == 15010.0 and st.up == 15010.0 + BAND and st.dn == 15010.0 - BAND


def test_a_close_exactly_on_the_band_is_no_signal_and_one_tick_beyond_it_is():
    log = decisions({}, day(up_bars(15025.0, 15025.25)))
    assert log == [(sec(9, 40), "long", True)]                      # the 09:38 close sits ON the band (15025.0): nothing; the 09:39 close is above it
    log = decisions({}, day(flat(8) + [bar(15000.0, 14975.0), bar(14975.0, 14974.75)] + flat(20, 14974.75)))
    assert log == [(sec(9, 40), "short", True)]


def test_the_band_is_fixed_for_the_day_a_later_move_does_not_shift_it():
    g = flat(8) + [bar(15000.0, 15200.0)] + flat(50, 15200.0)
    st, _ = run({}, day(g))
    assert (st.ref, st.up, st.dn) == (15000.0, 15025.0, 14975.0)


def test_k_scales_the_band():
    for k in (0.05, 0.5, 1.0, 3.0):
        st, _ = run({"k": k}, day(up_bars()))
        assert st.up == 15000.0 + k * A and st.dn == 15000.0 - k * A


# ---- (ii) A: the toolkit's daily ATR over the days before today -----------------------------------------------------------------------------

def test_a_is_wilder_atr14_of_the_daily_bars_not_a_plain_mean():
    rs = rows([300.0] * 14 + [100.0] * 11)
    assert abs(wilder(rs) - sum(r["h"] - r["l"] for r in rs[-14:]) / 14.0) > 5.0          # (the two differ here: the test can tell them apart)
    st, _ = run({}, day(up_bars()), daily=rs)
    assert st.up == pytest.approx(15000.0 + K * wilder(rs)) and st.dn == pytest.approx(15000.0 - K * wilder(rs))


def test_the_band_follows_the_last_prior_daily_bar_only():
    a = rows([100.0] * 25)
    b = a[:-1] + [{**a[-1], "h": a[-1]["h"] + 80.0}]               # the LAST prior day was 80 points wider
    sa, _ = run({}, day(up_bars()), daily=a)
    sb, _ = run({}, day(up_bars()), daily=b)
    assert sb.up > sa.up and sb.up == pytest.approx(15000.0 + K * wilder(b))


def test_the_runner_hands_over_prior_days_only_so_a_real_days_a_is_made_of_days_before_it():
    real_days()
    day_iso = days_of("NQ", 3)[1]
    seen = []

    class Look(NB.NoiseBand):
        def fam_day(self, ctx):
            super().fam_day(ctx)
            seen.append((self.day, self.dl[-1]["date"] if self.dl else None, len(self.dl), self.datr()))

    out = S.run_many([(Look, {**BASE, "tf": "5", "k": 0.3})], root="NQ", days=[day_iso], period="build", workers=1, on_error="raise")
    assert out[0]["used"] == 1
    assert len(seen) == 1 and seen[0][0] == day_iso and seen[0][1] < day_iso and seen[0][2] >= 15 and seen[0][3] > 0
    prior = [r for r in S.load_daily("NQ") if r["date"] < day_iso]
    assert seen[0][3] == pytest.approx(wilder(prior))


def test_fewer_than_15_daily_bars_means_no_band_and_no_trade():
    st, _ = run({}, day(up_bars()), daily=rows([100.0] * 14))
    assert st.up is None and decisions({}, day(up_bars()), daily=rows([100.0] * 14)) == []
    assert decisions({}, day(up_bars()), daily=rows([100.0] * 15)) == [(sec(9, 40), "long", True)]


# ---- (iii) the VWAP: since the anchor, volume-weighted typical price ------------------------------------------------------------------------

def vwap_of(bars, start_min, upto_min):
    """Volume-weighted (h + l + c) / 3 of the minute bars [start_min, upto_min) of a day built from 00:00."""
    vp = vv = 0.0
    for o, h, l, c, v in bars[start_min:upto_min]:
        vp += v * (h + l + c) / 3.0
        vv += v
    return vp / vv


def test_the_vwap_is_counted_from_the_anchor_and_matches_the_definition():
    bars = day([bar(15000.0, 15090.0, v=8000)] + flat(30, 15040.0))
    st, _ = run({}, bars)
    # st.mi = the minute bars the family has added; its VWAP is the one since 09:30 (minute 570) over exactly those, and not the one since 00:00
    assert st.mi > 600 and st.vwap() == pytest.approx(vwap_of(bars, 570, st.mi))
    assert st.vwap() > 15001.0


def test_a_close_beyond_the_band_but_on_the_wrong_side_of_the_vwap_is_no_signal():
    # a 09:31 spike (volume 4000) lifts the VWAP to about 15079; closes at 15040 are above the band (15025) and below the VWAP: no long
    bars = day(flat(1) + [(15000.0, 15200.0, 15000.0, 15040.0, 4000)] + flat(60, 15040.0))
    assert signals({}, bars) == []
    assert decisions({}, bars) == []
    # ... and the same band break with the VWAP below the close signals
    low = day(flat(1) + [(15000.0, 15001.0, 15000.0, 15040.0, 4)] + flat(60, 15040.0))
    assert signals({}, low)[0] == (sec(9, 32), "long")


def test_the_short_needs_the_close_below_the_vwap_too():
    bars = day(flat(1) + [(15000.0, 15000.0, 14800.0, 14960.0, 4000)] + flat(60, 14960.0))
    assert signals({}, bars) == []
    low = day(flat(1) + [(15000.0, 15000.0, 14999.0, 14960.0, 4)] + flat(60, 14960.0))
    assert signals({}, low)[0] == (sec(9, 32), "short")


def test_the_vwap_of_a_midday_session_still_starts_at_the_cash_open():
    # 09:30: a big up bar (volume 8000) to 15090; 09:31-10:59 at 15040; 11:00 on a gentle climb to 15047 (above the band, above a VWAP restarted
    # at 11:00, BELOW the VWAP since 09:30 which is about 15058): the mid session must not trade.
    g = [bar(15000.0, 15090.0, v=8000)] + flat(89, 15040.0) + [bar(15040.0 + 0.25 * i, 15040.0 + 0.25 * (i + 1)) for i in range(20)] + flat(30, 15045.0)
    bars = day(g)
    assert signals({"sess": "mid"}, bars) == [] and decisions({"sess": "mid"}, bars) == []
    st, _ = run({"sess": "mid"}, bars)
    assert st.vwap() == pytest.approx(vwap_of(bars, 570, st.mi)) and st.vwap() > 15050.0


# ---- (iv) the anchors ----------------------------------------------------------------------------------------------------------------------

def globex_head():
    """00:00-09:29: flat 14950 with a heavy minute at 00:30 (outside any VWAP from 01:00), the 01:00 open at 14900, 14950 by 03:00, 15000 by 09:00."""
    h = flat(570, 14950.0)
    h[30] = (14950.0, 14951.0, 14949.0, 14950.0, 8000)
    h[60:180] = [bar(14900.0, 14900.0)] + flat(119, 14900.0)
    h[180:540] = flat(360, 14950.0)
    h[540:570] = flat(30, 15000.0)
    return h


def test_the_globex_anchor_takes_the_01_00_open_and_the_vwap_since_01_00():
    head = globex_head()
    g = flat(20, 15000.0)
    bars = day(g, head=head)
    st, _ = run({"anchor": "globex"}, bars)
    assert st.ref == 14900.0 and st.up == 14925.0 and st.dn == 14875.0
    assert st.vwap() == pytest.approx(vwap_of(bars, 60, st.mi))        # the heavy 00:30 minute is NOT in it
    assert abs(st.vwap() - vwap_of(bars, 0, st.mi)) > 1.0
    # price 15000 is far above 14925 and above the VWAP since 01:00: a long at the first decision of the session; rth (open 15000) has none
    assert decisions({"anchor": "globex"}, bars)[0] == (sec(9, 31), "long", True)
    assert decisions({"anchor": "rth"}, bars) == []


def test_the_rth_anchor_does_not_depend_on_the_session():
    for s in ("nyam", "mid", "pm"):
        st, _ = run({"sess": s}, day(up_bars()))
        assert (st.ref, st.up, st.dn) == (15000.0, 15025.0, 14975.0), s
    for s in ("nyam", "mid", "pm"):
        st, _ = run({"sess": s, "anchor": "globex"}, day(up_bars(), head=globex_head()))
        assert st.ref == 14900.0, s


def test_no_anchor_bar_means_no_trade_for_the_day():
    bars = day(up_bars())
    t = tape_of(bars)
    keep = ~((t.ts >= ns("09:30")) & (t.ts < ns("09:40")))           # the first 10 minutes after the cash open never printed
    gap = S.Tape(t.root, t.date, t.contract, t.ts[keep], t.px[keep], t.size[keep])
    st, _ = run({}, bars, tape=gap)
    assert st.ref is None and st.up is None
    assert decisions({}, bars, tape=gap) == []
    keep = ~((t.ts >= ns("01:00")) & (t.ts < ns("01:10")))
    gap = S.Tape(t.root, t.date, t.contract, t.ts[keep], t.px[keep], t.size[keep])
    assert decisions({"anchor": "globex"}, bars, tape=gap) == []


# ---- (v) the session window ----------------------------------------------------------------------------------------------------------------

def test_entries_happen_only_inside_the_session_even_when_the_break_came_earlier():
    g = flat(10) + [bar(15000.0, 15060.0)] + flat(500, 15060.0)       # the break at 09:40 holds all day
    bars = day(g)
    assert decisions({"sess": "nyam"}, bars)[0][0] == sec(9, 41)
    assert decisions({"sess": "mid"}, bars) == [(sec(11, 1), "long", True)]       # the first decision inside 11:00-13:30
    assert decisions({"sess": "pm"}, bars) == [(sec(13, 31), "long", True)]


def test_no_entry_in_the_last_five_minutes_of_a_session_nor_after_it():
    for sess, end in (("nyam", sec(11)), ("mid", sec(13, 30)), ("pm", sec(15, 58))):
        i = (end - 420) // 60 - 570                                  # the minute that closes at end - 6 min: the last decision is end - 6 min
        ok = day(flat(i) + [bar(15000.0, 15060.0)] + flat(30, 15060.0))
        assert decisions({"sess": sess}, ok) == [(end - 360, "long", True)], sess
        late = day(flat(i + 1) + [bar(15000.0, 15060.0)] + flat(30, 15060.0))            # the break closes at end - 5 min: too late
        assert decisions({"sess": sess}, late) == [], sess


def test_entry_is_the_next_bars_open_and_the_decision_is_the_signal_bars_close():
    for tf in (1, 5, 15, 30):
        g = flat(30, 15000.0) + [bar(15000.0, 15060.0)] * tf + flat(300, 15060.0)       # a break from 10:00 on
        st, res = run({"tf": str(tf)}, day(g))
        d = decisions({"tf": str(tf)}, day(g))
        assert d and d[0][1] == "long", tf
        t = res.trades[0]
        first = d[0][0]
        assert first % (tf * 60) == 0 and first >= sec(10, 0) + tf * 60 - 60
        assert first * 1000 + ns("00:00") // 1_000_000 <= t["entry_ms"] < first * 1000 + ns("00:00") // 1_000_000 + tf * 60_000, tf


# ---- (vi) max_tr, one position at a time, re-entry after an exit -----------------------------------------------------------------------------

def test_max_tr_defaults_to_three_and_caps_the_entries_of_a_session():
    assert NB.NoiseBand.defaults()["max_tr"] == 3
    bars = day(flat(8) + [bar(15000.0, 15060.0)] + flat(400, 15060.0))
    p = {k: v for k, v in BASE.items() if k != "max_tr"}
    cls = type("Spy", (Spy,), {"log": []})
    st = cls({**p, "exit_bars": 1})                                  # the default max_tr (3); each trade leaves one bar after its fill
    st.ROLLS = frozenset()
    S.run_session(st, tape_of(bars), daily=DAILY, on_error="raise")
    assert st.p["max_tr"] == 3 and [x[2] for x in cls.log].count(True) == 3
    for m in (1, 2, 4, 5):
        got = decisions({"max_tr": m, "exit_bars": 1}, bars)
        assert [x[2] for x in got].count(True) == m, m


def test_one_position_at_a_time_and_a_new_entry_only_after_the_exit():
    bars = day(flat(8) + [bar(15000.0, 15060.0)] + flat(400, 15060.0))
    _, res = run({"max_tr": 5, "exit_bars": 2}, bars)
    tr = sorted(res.trades, key=lambda t: t["entry_ms"])
    assert len(tr) == 5
    assert all(a["exit_ms"] <= b["entry_ms"] for a, b in zip(tr, tr[1:]))
    # without an exit the one open trade blocks every other qualifying close
    _, res = run({"max_tr": 5}, bars)
    assert len(res.trades) == 1


def test_the_re_entry_can_be_on_the_other_side_with_both_sides_on():
    bars = day(flat(8) + [bar(15000.0, 15060.0)] * 3 + [bar(15060.0, 14900.0)] + flat(60, 14900.0) + [bar(14900.0, 14850.0)] + flat(100, 14850.0))
    sides = [x[1] for x in decisions({"exit_bars": 2, "max_tr": 5}, bars) if x[2]]
    assert "long" in sides and "short" in sides and sides[0] == "long"


# ---- (vii) sides: dir ---------------------------------------------------------------------------------------------------------------------------

def test_dir_runs_one_side_only_and_both_is_the_default():
    assert NB.NoiseBand.defaults()["dir"] == "both"
    up, dn = day(up_bars()), day(flat(8) + [bar(15000.0, 14975.0), bar(14975.0, 14974.75)] + flat(20, 14974.75))
    placed = lambda p, b: [x[1] for x in decisions(p, b) if x[2]]  # noqa: E731  (a blocked side is asked and not placed)
    assert placed({"dir": "long"}, up) == ["long"] and placed({"dir": "short"}, up) == []
    assert placed({"dir": "short"}, dn) == ["short"] and placed({"dir": "long"}, dn) == []
    assert placed({}, up) == ["long"] and placed({}, dn) == ["short"]


# ---- (viii) flat by 15:58 and the standard exits ------------------------------------------------------------------------------------------------

def test_a_trade_with_no_stop_hit_is_flat_by_15_58():
    bars = day(flat(8) + [bar(15000.0, 15060.0)] + flat(400, 15060.0))
    for sess in ("nyam", "mid", "pm"):
        _, res = run({"sess": sess}, bars)
        assert len(res.trades) == 1 and res.trades[0]["exit_ms"] <= (ns("15:58") // 1_000_000) + 60_000, sess
    # a stop and a target of the standard table act as in every family: stop 10 pts, target 1R
    drop = day(flat(8) + [bar(15000.0, 15060.0)] + flat(20, 15060.0) + [bar(15060.0, 15040.0)] + flat(100, 15040.0))
    _, res = run({"stop_val": 10.0, "tgt_r": 1.0}, drop)
    t = res.trades[0]
    assert t["side"] == "long" and t["net"] < 0 and t["exit_ms"] < ns("11:00") // 1_000_000


# ---- (ix) NO LOOK-AHEAD ------------------------------------------------------------------------------------------------------------------------------

def test_a_future_bar_cannot_change_an_earlier_signal():
    bars = day(flat(8) + [bar(15000.0, 15060.0)] + flat(4, 15060.0) + [bar(15060.0, 14900.0)] + flat(6, 14900.0) + [bar(14900.0, 14800.0)] + flat(80, 14800.0))
    tape = tape_of(bars)
    params = {"exit_bars": 2, "max_tr": 5}
    clean = decisions(params, bars, tape=tape)
    assert [(x[0], x[1]) for x in clean] == [(sec(9, 39), "long"), (sec(9, 42), "long"), (sec(9, 45), "short"), (sec(9, 48), "short"), (sec(9, 51), "short")]
    for cut in (sec(9, 35), sec(9, 40), sec(9, 43), sec(9, 46)):
        dirty = garble(tape, ns("00:00") + cut * S.NS)
        got = decisions(params, bars, tape=dirty)
        assert [x for x in got if x[0] <= cut] == [x for x in clean if x[0] <= cut], cut
        assert any(x[0] > cut for x in clean)                        # (there is a later decision the garbled prints could have bent)
    for anchor in ("rth", "globex"):
        sig = signals({"anchor": anchor}, bars, tape=tape)
        assert sig
        for cut in (sec(9, 40), sec(9, 46)):
            got = signals({"anchor": anchor}, bars, tape=garble(tape, ns("00:00") + cut * S.NS))
            assert [x for x in got if x[0] <= cut] == [x for x in sig if x[0] <= cut], (anchor, cut)


def test_the_band_and_the_vwap_at_a_decision_use_only_what_had_printed():
    bars = day(flat(8) + [bar(15000.0, 15060.0)] + flat(60, 15060.0))
    tape = tape_of(bars)
    seen = []

    class Look(NB.NoiseBand):
        def fam_signal(self, ctx):
            seen.append((sec_of(ctx), self.up, self.dn, self.vwap()))

    a = []
    for t in (tape, garble(tape, ns("09:45"))):
        seen.clear()
        st = Look({**BASE})
        st.ROLLS = frozenset()
        S.run_session(st, t, daily=DAILY, on_error="raise")
        a.append([x for x in seen if x[0] <= sec(9, 45)])
    assert a[0] == a[1] and a[0]


# ---- (x) the rule against an independent restatement, on random days --------------------------------------------------------------------------------

def reference(bars, k, a_, tf, anchor, sess):
    """Every qualifying close inside the session as (second, side), from the written rule alone."""
    s0, s1 = S.SESS[sess]
    anc = 34200 if anchor == "rth" else 3600
    ref = None
    vp = vv = 0.0
    out = []
    for i, (o, h, l, c, v) in enumerate(bars):
        s = 60 * i
        if s >= anc:
            ref = o if ref is None else ref
            vp += v * (h + l + c) / 3.0
            vv += v
        end = s + 60
        if end % (tf * 60) or ref is None or vv <= 0:
            continue
        if not (s0 < end <= s1 and end < s1 - 300):
            continue
        w = vp / vv
        if c > ref + k * a_ and c > w:
            out.append((end, "long"))
        elif c < ref - k * a_ and c < w:
            out.append((end, "short"))
    return out


@pytest.mark.parametrize("anchor", ["rth", "globex"])
@pytest.mark.parametrize("sess", ["nyam", "mid", "pm"])
@pytest.mark.parametrize("tf", [1, 5, 15, 30])
def test_the_signals_equal_the_written_rule_on_random_days(anchor, sess, tf):
    n = 0
    for seed in (3, 11, 21, 33):
        bars = flat(60) + rand_bars(900, seed, p0=15000.0, step=4.0)
        want = reference(bars, 0.3, wilder(DAILY), tf, anchor, sess)
        got = signals({"k": 0.3, "tf": str(tf), "sess": sess, "anchor": anchor}, bars)
        assert got == want, (seed, got[:5], want[:5])
        n += len(want)
    assert n > 0, "the random days never crossed the band: the comparison would be empty"


# ---- (xi) the settings and the registry ---------------------------------------------------------------------------------------------------------------

def test_the_settings_and_their_limits():
    d, sc = NB.NoiseBand.defaults(), NB.NoiseBand.schema()
    assert (d["k"], d["anchor"], d["max_tr"], d["dir"]) == (0.3, "rth", 3, "both")
    assert sc["k"] == ("float", 0.05, 3.0) and sc["anchor"] == ("choice", ("rth", "globex")) and sc["max_tr"] == ("int", 1, 5)
    for bad in ({"k": 0.04}, {"k": 3.01}, {"anchor": "asia"}, {"max_tr": 0}, {"max_tr": 6}, {"max_tr": 1.5}, {"dir": "up"}):
        with pytest.raises(ValueError):
            NB.NoiseBand({"tf": "5", **bad})
    for ok in ({"k": 0.05}, {"k": 3.0}, {"anchor": "globex"}, {"max_tr": 1}, {"max_tr": 5}, {"dir": "short"}):
        NB.NoiseBand({"tf": "5", **ok})
    with pytest.raises(ValueError):
        NB.NoiseBand({"tf": "5", "stop_mode": "rng"})                # the family has no structure height: only the standard table's stops (the wrapped class says so too)


def test_the_family_runs_every_bar_size_and_each_session_that_ends_after_its_anchor():
    assert NB.NoiseBand.SCREEN_TFS == ("1", "5", "15", "30") and NB.NoiseBand.FEATURES == ()
    for tf in NB.NoiseBand.SCREEN_TFS:
        for s in ("nyam", "mid", "pm"):
            for a in ("rth", "globex"):
                assert NB.NoiseBand({"tf": tf, "sess": s, "hold_to": "day", "anchor": a}).sessions() == [s]
    # a session that is over before the anchor can never trade: 09:30 closes pre, london and asia; 01:00 leaves asia open; the evening before never
    ok = lambda a, s: NB.NoiseBand({"tf": "5", "sess": s, "hold_to": "day", "anchor": a}).sessions()  # noqa: E731
    assert [ok("rth", s) for s in ("asia", "london", "pre", "eve")] == [[], [], [], []]
    assert [ok("globex", s) for s in ("asia", "london", "pre")] == [["asia"], ["london"], ["pre"]] and ok("globex", "eve") == []
    assert NB.NoiseBand({"tf": "5", "sess": "all", "anchor": "rth"}).sessions() == ["nyam", "mid", "pm"]


# ---- (xii) real BUILD days: the invariants of the code check, at 1 worker --------------------------------------------------------------------------------

@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_real_build_days_hold_the_window_one_position_and_the_flat_time(root):
    real_days()
    days = days_of(root, 4)
    hd = {"tf": "5", "hold_to": "day", "stop_mode": "atr", "stop_val": 1.5, "tgt_r": 2.0, "k": 0.2}
    specs = [(NB.NoiseBand, {**hd, "sess": s, "anchor": a}) for s in ("nyam", "mid", "pm") for a in ("rth", "globex")]
    out = S.run_many(specs, root=root, days=days, period="build", workers=1, on_error="raise")
    again = S.run_many(specs, root=root, days=days, period="build", workers=1, on_error="raise")
    assert [r["trades"] for r in out] == [r["trades"] for r in again]
    assert sum(r["skipped_by_error"] for r in out) == 0
    total = 0
    for (cls, p), r in zip(specs, out):
        s0, s1 = S.SESS[p["sess"]]
        last = {}
        for t in sorted(r["trades"], key=lambda t: t["entry_ms"]):
            d = S._date(t["date"])
            es = (t["entry_ms"] // 1000) - S.et_ns(d, "00:00") // S.NS
            assert s0 < es < s1 - 300 + 120, (p, t["date"], es)                       # inside the window (a fill a little after the decision)
            assert t["exit_ms"] <= S.et_ns(d, S.day_flat(d, root)) // 1_000_000 + 60_000
            assert last.get(t["date"], 0) <= t["entry_ms"]                            # one position at a time
            last[t["date"]] = t["exit_ms"]
            total += 1
    assert total > 0


# ---- (xiii) the registry ------------------------------------------------------------------------------------------------------------------------------

def test_the_registry_holds_noise_band_with_dir_as_its_mirror_axis():
    assert families.ERRORS == {}
    cls, inputs, both, notes = families.REGISTRY["noise_band"]
    lib = families.library("noise_band")
    assert cls is NB.NoiseBand and both is False and cls.FEATURES == () and lib["roots"] == ("NQ", "ES", "GC")
    assert families.MODULE_OF["noise_band"] == "noise"
    assert lib["mirror"] == "dir" and {v["dir"] for v in lib["variants"]} == {"long", "short"} and {v["k"] for v in lib["variants"]} == {0.2, 0.3, 0.4}
    assert "14" in notes and "15" in notes                          # the daily ATR(14) here against Conti's 15 sessions: said in the family's words
    from families import blocks as B
    assert issubclass(B.WRAPPED["noise_band"], NB.NoiseBand) and "noise_band" in B.BASES
    assert [s for s in RM.DAY_PASSES if cls({"tf": "5", "sess": s, "hold_to": "day"}).sessions()] == ["nyam", "mid", "pm"]       # (the rth anchor, the default)
