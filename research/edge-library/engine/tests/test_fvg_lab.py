"""fvg_lab (families/fvg_lab.py): the owner's 100-ideas batch family. Synthetic days with exact numbers: the plain rule, a market entry, the
side bias (prior close), a quality filter, the fade and the window."""
import l2sim as S
from families import fvg_lab as F
from test_blocks import DAILY
from test_open_fvg import bar, day, mirror, rest, sec, sec_of, tape_of

BASE = {"hold_to": "day", "tf": "5", "sess": "nyam", "stop_mode": "pts", "stop_val": 20.0, "tgt_r": 1.0, "min_gap": 0.0}
# 09:30-09:34 quiet at 15000 (high 15001); 09:35-09:39 climbs to 15010; 09:40-09:44 quiet at 15010 (low 15009): an UP 5-min gap 15001 .. 15009
GAP = rest(5, 15000.0) + [bar(15000.0 + 2 * i, 15002.0 + 2 * i) for i in range(5)] + rest(5, 15010.0)


class Spy(F.FvgLab):
    log: list = []

    def _lim(self, ctx, side, px, struct=None, **kw):
        type(self).log.append((sec_of(ctx), "lim", side, px))
        return super()._lim(ctx, side, px, struct=struct, **kw)

    def _mkt(self, ctx, side, struct=None, **kw):
        type(self).log.append((sec_of(ctx), "mkt", side, self.C[-1]))
        return super()._mkt(ctx, side, struct=struct, **kw)


def play(bars, pre=15000.0, **params):
    cls = type("Spy", (Spy,), {"log": []})
    st = cls({**BASE, **params})
    st.ROLLS = frozenset()
    S.run_session(st, tape_of(day(bars, at="09:30", pre=pre)), daily=list(DAILY), on_error="raise")
    return list(cls.log)


def test_plain_gap_rests_a_limit_at_the_near_edge_and_the_mirror_sells():
    g = GAP + rest(30, 15010.0)
    assert play(g) == [(sec(9, 45), "lim", "long", 15009.0)]
    assert play(mirror(g)) == [(sec(9, 45), "lim", "short", 14991.0)]


def test_go_is_a_market_order_at_bar_3s_close_and_mid_is_the_middle():
    g = GAP + rest(30, 15010.0)
    assert play(g, mode="go") == [(sec(9, 45), "mkt", "long", 15010.0)]
    assert play(g, mode="mid") == [(sec(9, 45), "lim", "long", 15005.0)]


def test_side_pdc_trades_only_with_the_prior_close_and_fade_flips_it():
    g = GAP + rest(30, 15010.0)          # price ~15010 is below the prior close 15050: shorts only
    assert play(g, side="pdc") == []
    assert play(mirror(g), side="pdc") == [(sec(9, 45), "lim", "short", 14991.0)]
    assert play(g, side="pdc", fade=1) == [(sec(9, 45), "lim", "long", 15009.0)]


def test_clean_quality_needs_bar_2_to_stay_out_of_bar_1():
    g = GAP + rest(30, 15010.0)          # bar 2 trades down to 15000 / 14999, inside bar 1's range: not clean
    assert play(g, q="clean") == []
    assert play(g, q="body") == [(sec(9, 45), "lim", "long", 15009.0)]


def test_fill_trades_against_the_thrust_and_a_late_start_waits():
    g = GAP + rest(30, 15010.0)
    assert play(g, trig="fill") == [(sec(9, 45), "mkt", "short", 15010.0)]
    assert play(g, start="10:00") == []


def test_ovw_needs_the_open_and_vwap_to_agree_and_rej_buys_the_close_back_out_of_a_wick_tap():
    g = GAP + rest(30, 15010.0)
    assert play(g, side="ovw") == [(sec(9, 45), "lim", "long", 15009.0)]
    assert play(mirror(g), side="ovw") == [(sec(9, 45), "lim", "short", 14991.0)]
    tap = [(15010.0, 15011.0, 15005.0, 15010.0, 40)] + rest(4, 15012.0)       # 09:45 bar wicks to 15005 (through the near edge 15009), closes 15012
    assert play(g[:15] + tap + rest(30, 15012.0), mode="rej") == [(sec(9, 50), "mkt", "long", 15012.0)]


def test_onb_trades_with_the_side_that_broke_the_overnight_range():
    g = GAP + rest(30, 15010.0)          # the climb breaks the overnight high 15001; the mirror breaks the low
    assert play(g, pre=14990.0, side="onb") == [(sec(9, 45), "lim", "long", 15009.0)]
    assert play(mirror(g), pre=15010.0, side="onb") == [(sec(9, 45), "lim", "short", 14991.0)]
    assert play(g, side="onb") == []     # the quiet range of the fixture is broken on both sides: no bias
