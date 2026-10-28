"""fvg_tap_disp (families/fvg_tap_disp.py), the owner's idea of 2026-10-27: a 15-minute gap is tapped, a 1-minute displacement close
out of it (close out) or inside / out of it (close in) -> market with the gap; a 15-minute close through the gap kills it."""
import l2sim as S
from families import blocks
from families import fvg_tap_disp as F
from test_blocks import DAILY
from test_open_fvg import bar, day, mirror, rest, sec, sec_of, tape_of

BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "struct", "tgt_r": 1.0}
# 09:00-09:14 quiet at 15000 (high 15001), 09:15-09:29 climbs, 09:30-09:44 quiet at 15015 (low 15014): an UP 15-min gap 15001 .. 15014
GAP = rest(15, 15000.0) + rest(14, 15000.0) + [bar(15000.0, 15015.0)] + rest(20, 15015.0)
TAP = (15015.0, 15016.0, 15008.0, 15012.0, 40)                      # 09:50: wicks into the gap, closes inside (no displacement)


class Spy(F.FvgTapDisp):
    log: list = []

    def _mkt(self, ctx, side, struct=None, **kw):
        o = super()._mkt(ctx, side, struct=struct, **kw)
        type(self).log.append((sec_of(ctx), side, self.C[-1], struct))
        return o


def play(bars, **params):
    cls = type("Spy", (Spy,), {"log": []})
    st = cls({**BASE, **params})
    st.ROLLS = frozenset()
    S.run_session(st, tape_of(day(bars, at="09:00")), daily=list(DAILY), on_error="raise")
    return list(cls.log)


def test_tap_then_a_displacement_close_above_the_gap_buys_with_the_stop_at_the_taps_low_and_the_mirror():
    g = GAP + [TAP, bar(15012.0, 15030.0)] + rest(30, 15030.0)
    assert play(g) == [(sec(9, 52), "long", 15030.0, 15008.0)]
    assert play(mirror(g)) == [(sec(9, 52), "short", 14970.0, 14992.0)]


def test_close_inside_the_gap_trades_only_in_the_in_version():
    deep = (15015.0, 15016.0, 15002.0, 15003.0, 40)
    g = GAP + [deep, bar(15003.0, 15012.0)] + rest(30, 15012.0)    # displacement that closes inside the gap (15001 .. 15014)
    assert play(g, close="out") == []
    assert play(g, close="in") == [(sec(9, 52), "long", 15012.0, 15002.0)]


def test_a_small_body_or_leaving_without_displacement_does_not_trade():
    assert play(GAP + [TAP, bar(15012.0, 15016.0)] + rest(30, 15016.0), k=2.0) == []
    # left the gap quietly at 09:51; a displacement much later without a new tap is not a bounce
    assert play(GAP + [TAP, bar(15012.0, 15016.0)] + rest(10, 15020.0) + [bar(15020.0, 15040.0)] + rest(20, 15040.0), k=2.0) == []


def test_a_15_minute_close_below_the_gap_kills_it():
    # 09:45-09:59 closes at 14995, under the bottom 15001: the gap is inversed; the 10:00 tap + displacement is ignored
    g = GAP[:-5] + rest(14, 15005.0) + [bar(15005.0, 14995.0)] + [(14995.0, 15009.0, 14994.0, 15008.0, 40), bar(15008.0, 15030.0)]
    assert play(g + rest(20, 15030.0)) == []


def test_registered_one_instance():
    assert "fvg_tap_disp" in blocks.WRAPPED
    assert F.FvgTapDisp(BASE).fam_filter(["nyam", "mid", "pm"]) == ["t"]


def test_wick_displacement_needs_a_close_past_the_previous_wick_and_2x_its_body():
    W = {"disp": "wick", "k": 2.0}
    g = GAP + [TAP, bar(15012.0, 15030.0)] + rest(30, 15030.0)     # TAP body 3, high 15016; next closes 15030 with body 18
    assert play(g, **W) == [(sec(9, 52), "long", 15030.0, 15008.0)]
    assert play(mirror(g), **W) == [(sec(9, 52), "short", 14970.0, 14992.0)]
    big = (15020.0, 15021.0, 15008.0, 15012.0, 40)                # body 8, high 15021
    g = GAP + [big, bar(15012.0, 15025.0)] + rest(30, 15025.0)     # past the wick, body 13: under 2x (16), over 1.5x (12)
    assert play(g, **W) == []
    assert play(g, disp="wick", k=1.5) == [(sec(9, 52), "long", 15025.0, 15008.0)]
    g = GAP + [big, bar(15012.0, 15020.0)] + rest(30, 15020.0)     # body 8 = 1x, and closes under the wick 15021
    assert play(g, disp="wick", k=1.0) == []


def test_start_0000_trades_before_the_open_and_0930_does_not():
    early = GAP[:30] + rest(15, 15015.0) + [TAP, bar(15012.0, 15030.0)] + rest(30, 15030.0)   # same day, shifted to 03:00
    cls = type("Spy", (Spy,), {"log": []})
    for start, want in (("09:30", []), ("00:00", [(sec(3, 47), "long", 15030.0, 15008.0)])):
        cls.log = []
        st = cls({**BASE, "start": start})
        st.ROLLS = frozenset()
        S.run_session(st, tape_of(day(early, at="03:00")), daily=list(DAILY), on_error="raise")
        assert cls.log == want


def test_tf5_taps_and_displaces_on_5_minute_candles():
    # 09:50-09:54 dips into the gap and closes inside; 09:55-09:59 closes 15030 (body 18, past the 5-min wick 15016, 6x its body)
    g = GAP + [TAP] + rest(4, 15012.0) + [bar(15012.0, 15030.0)] + rest(30, 15030.0)
    for disp in ("atr", "wick"):
        assert play(g, tf="5", disp=disp, k=2.0) == [(sec(10, 0), "long", 15030.0, 15008.0)]
        assert play(mirror(g), tf="5", disp=disp, k=2.0) == [(sec(10, 0), "short", 14970.0, 14992.0)]


def test_start_1800_trades_in_the_evening_and_through_midnight():
    # one held segment 18:00 of the evening before -> 16:00: the same up gap + tap + displacement 52 minutes after 18:00, and 7 hours later (01:52)
    import datetime as dt
    from test_blocks import D, minute_tape
    cls = type("Spy", (Spy,), {"log": []})
    for lead, want in ((0, sec(18, 52) - 86400), (420, sec(1, 52))):
        cls.log = []
        st = cls({**BASE, "start": "18:00"})
        st.ROLLS = frozenset()
        assert st.session_window is None and st.eve_window[0] == "18:00" and st.S["t"] == (-21600, F.END_S)
        g = rest(lead, 15000.0) + GAP + [TAP, bar(15012.0, 15030.0)] + rest(30, 15030.0)
        g += rest(1320 - len(g), 15030.0)
        t = minute_tape(g, start="18:00", d=D - dt.timedelta(days=1))        # the prints start 18:00 of the evening before; the tape's date is the trade date
        tape = S.Tape("NQ", D, "NQM3", t.ts, t.px, t.size)
        S.run_session(st, tape, daily=list(DAILY), on_error="raise", window=st.eve_window, segment="eve")
        assert [x[0] for x in cls.log] == [want]


def test_gtf2_adds_a_second_gap_size_and_a_gap_dies_only_by_a_close_of_its_own_size():
    g = GAP + [TAP, bar(15012.0, 15030.0)] + rest(30, 15030.0)
    assert play(g, gtf=60) == []                                              # no 1-hour gap yet at 09:50
    assert play(g, gtf=60, gtf2=15) == [(sec(9, 52), "long", 15030.0, 15008.0)]
    assert play(g, gtf=15, gtf2=15) == play(g, gtf=15)                         # the same size twice = one set of gaps
    dead = GAP[:-5] + rest(14, 15005.0) + [bar(15005.0, 14995.0)] + [(14995.0, 15009.0, 14994.0, 15008.0, 40), bar(15008.0, 15030.0)]
    assert play(dead + rest(20, 15030.0), gtf=60, gtf2=15) == []              # the 15-minute close through it kills the 15-minute gap


def test_one_minute_gaps_and_the_candle_extreme_stop_and_inversion():
    # 09:35-09:37 leave a 1-minute UP gap 15001 .. 15006; 20 quiet minutes; 09:58 taps to 15004 and closes inside; 09:59 displaces from 15005 (low 15004.5)
    core = [(15000.0, 15001.0, 14999.0, 15000.0, 40), (15000.0, 15012.0, 15000.0, 15011.0, 40), (15011.0, 15013.0, 15006.0, 15012.0, 40)] \
        + rest(20, 15012.0) + [(15012.0, 15013.0, 15004.0, 15005.0, 40), (15005.0, 15020.0, 15004.5, 15019.0, 40)] + rest(30, 15019.0)
    g = rest(35, 15000.0) + core
    one = {"gtf": 1}
    assert play(g, **one) == [(sec(10, 0), "long", 15019.0, 15004.0)]                       # the tap's low
    assert play(g, stop_at="candle", **one) == [(sec(10, 0), "long", 15019.0, 15004.5)]      # the displacement candle's low
    assert play(mirror(g), stop_at="candle", **one) == [(sec(10, 0), "short", 14981.0, 14995.5)]
    dead = rest(35, 15000.0) + core[:3] + rest(10, 15012.0) + [(15012.0, 15012.0, 15000.0, 15000.5, 40)] + rest(9, 15012.0) + core[23:]   # a 1-minute close under the bottom 15001
    assert play(dead + rest(30, 15019.0), **one) == []


def test_the_trade_limit_can_be_lifted_to_1000():
    assert F.FvgTapDisp({**BASE, "max_tr": 1000}).p["max_tr"] == 1000
