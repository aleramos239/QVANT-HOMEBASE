"""FVG OSIDE: the `fvg_oside` entry trigger (families/fvg_oside.py), the owner's idea of 2026-10-19 (the second one).

THE RULE UNDER TEST: above the 09:30 open -> a limit at the near edge of the newest up gap (below: the newest down gap), stop at the middle
candle's far end; a newer gap or a flip of the side moves the order; one trade a day. Synthetic 1-minute days (test_open_fvg's helpers)."""
import l2sim as S
from families import blocks
from families import fvg_oside as FS
from test_blocks import DAILY
from test_open_fvg import bar, day, mirror, rest, sec, sec_of, tape_of, up_gap

BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "struct", "tgt_r": 0.5}


class Spy(FS.FvgOside):
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


def play(bars, **params):
    cls = type("Spy", (Spy,), {"log": [], "gone": []})
    st = cls({**BASE, **params})
    st.ROLLS = frozenset()
    res = S.run_session(st, tape_of(bars), daily=list(DAILY), on_error="raise")
    return list(cls.log), list(cls.gone), res


GAPS = rest(5, 15000.0) + up_gap(15000.0) + rest(3, 15011.0) + up_gap(15011.0)     # up gaps read at 09:38 and 09:44, all above the open


def test_above_the_open_rests_at_the_newest_up_gap_and_a_newer_gap_moves_it_and_the_mirror():
    log, gone, res = play(day(GAPS + rest(200, 15022.0)))
    assert log == [(sec(9, 38), "long", 15006.0, 15000.0, True), (sec(9, 44), "long", 15017.0, 15011.0, True)]
    assert gone == [sec(9, 44), sec(15, 0)] and res.trades == []
    log, _, _ = play(day(mirror(GAPS + rest(200, 15022.0))))
    assert log == [(sec(9, 38), "short", 14994.0, 15000.0, True), (sec(9, 44), "short", 14983.0, 14989.0, True)]


def test_a_gap_below_the_open_rests_only_once_price_is_above_it_and_a_flip_below_cancels_it():
    g = [(15000.0, 15000.0, 14980.0, 14980.0, 40)] + rest(4, 14980.0) + up_gap(14980.0) + [(14991.0, 15002.0, 14988.0, 15001.0, 40)]
    g += [(15001.0, 15002.0, 14992.0, 15001.0, 40)] * 3 + [bar(15001.0, 14995.0)]      # wide bars: no newer gap above the open
    log, gone, res = play(day(g + rest(200, 14995.0), pre=14980.0))     # quiet at 14980 before 09:30: the open bar leaves no gap
    assert log == [(sec(9, 39), "long", 14986.0, 14980.0, True)]    # nothing at 09:38 (below the open, no down gap)
    assert gone == [sec(9, 43)] and res.trades == []                 # the close below the open cancels it; no down gap to rest


def test_a_return_fills_at_the_near_edge_with_a_half_r_target_and_one_trade_a_day():
    back = (15011.0, 15011.0, 15005.0, 15006.0, 40)                  # through the near edge 15006, not the stop 15000
    g = rest(5, 15000.0) + up_gap(15000.0) + rest(3, 15011.0) + [back] + rest(3, 15012.0) + up_gap(15012.0) + rest(200, 15023.0)
    log, _, res = play(day(g))
    assert len(log) == 1 and len(res.trades) == 1
    t = res.trades[0]
    assert (t["side"], t["entry_price"], t["sl"], t["tp"]) == ("long", 15006.0, 15000.0, 15009.0)      # 0.5R on the 6-point stop


def test_registered_with_one_instance_and_the_window_0930_1500():
    assert "fvg_oside" in blocks.WRAPPED and FS.ENTRY_WINDOWS["fvg_oside"] == (sec(9, 30), sec(15) + 59)
    st = FS.FvgOside(BASE)
    assert st.fam_sessions() == {"t": (sec(9, 30), sec(15, 58))} and st.fam_filter(["nyam", "mid", "pm"]) == ["t"]


def test_stop_atr_puts_the_stop_k_atr14_from_the_near_edge():
    class AtrSpy(FS.FvgOside):
        seen: list = []

        def _lim(self, ctx, side, px, **kw):
            type(self).seen.append((px, kw.get("struct"), self.atr))
            return super()._lim(ctx, side, px, **kw)

    st = AtrSpy({**BASE, "stop_atr": 1.5})
    st.ROLLS = frozenset()
    S.run_session(st, tape_of(day(GAPS + rest(200, 15022.0))), daily=list(DAILY), on_error="raise")
    assert [px for px, _, _ in AtrSpy.seen] == [15006.0, 15017.0]
    assert all(a > 0 and abs(px - st_ - 1.5 * a) < 1e-9 for px, st_, a in AtrSpy.seen)


def test_a_gap_whose_first_candle_is_before_0930_never_counts():
    g = [(15000.0, 15010.0, 15000.0, 15010.0, 40), (15010.0, 15012.0, 15006.0, 15011.0, 40)]     # bar 1 = 09:29: an up gap read at 09:32
    assert play(day(g + rest(200, 15011.0)))[0] == []


def test_atr1_puts_the_stop_k_one_minute_atr14_from_the_near_edge_without_the_tf_floor():
    class A1(FS.FvgOside):
        seen: list = []

        def _lim(self, ctx, side, px, **kw):
            type(self).seen.append((px, kw.get("struct"), self.atr1m()))
            return super()._lim(ctx, side, px, **kw)

    st = A1({**BASE, "tf": "5", "atr1": 2.0})
    st.ROLLS = frozenset()
    g = rest(15, 15000.0) + [(15000.0, 15030.0, 15000.0, 15030.0, 40)] * 5 + rest(5, 15040.0) + rest(200, 15060.0)  # 5m gap 09:45-10:00
    res = S.run_session(st, tape_of(day(g)), daily=list(DAILY), on_error="raise")
    assert A1.seen and all(abs(px - s_ - 2.0 * a) < 1e-9 for px, s_, a in A1.seen)
    assert all(abs(t["entry_price"] - t["sl"] - (A1.seen[0][0] - A1.seen[0][1])) < 1e-9 for t in res.trades)


def test_with_max_tr_above_1_the_next_new_gap_after_a_closed_trade_is_the_next_entry():
    back = (15011.0, 15011.0, 15005.0, 15006.0, 40)                  # fills 15006, then 15012 > the 0.5R target 15009: closed
    g = rest(5, 15000.0) + up_gap(15000.0) + rest(3, 15011.0) + [back] + rest(3, 15012.0) + up_gap(15012.0) + rest(200, 15023.0)
    assert len(play(day(g))[0]) == 1                                 # max_tr 1: the day is over
    log, _, res = play(day(g), max_tr=2)
    assert [r[1:] for r in log] == [("long", 15006.0, 15000.0, True), ("long", 15018.0, 15012.0, True)] and len(res.trades) == 1
