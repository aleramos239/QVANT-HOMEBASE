"""FVG ODIR: the `fvg_odir` entry trigger (families/fvg_odir.py), the owner's idea of 2026-10-19.

THE RULE UNDER TEST: the 09:30-10:00 move sets the side; the first fvg gap on that side whose bar 3 closes after 10:00 and before 15:00 ->
a limit at its near edge, stop at the middle candle's far end (bar 2's low up / high down), one trade a day, unfilled order cancelled at 15:00.
Synthetic 1-minute days with exact numbers (the helpers of test_open_fvg)."""
import l2sim as S
from families import blocks
from families import fvg_odir as FO
from test_blocks import DAILY
from test_open_fvg import bar, day, mirror, rest, sec, sec_of, tape_of, up_gap

BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "struct", "tgt_r": 1.0}
UP_OPEN = [bar(15000.0, 15010.0)] + rest(29, 15010.0)                # 09:30-09:59: up 10 points (and an up gap at 09:32, before 10:00)


class Spy(FO.FvgOdir):
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


def test_an_up_open_takes_the_first_up_gap_after_10_with_the_stop_at_the_middle_candles_low_and_the_mirror():
    g = UP_OPEN + rest(5, 15010.0) + up_gap(15010.0) + rest(3, 15021.0)     # gap bars 10:05 / 10:06 / 10:07, read at 10:08
    log, gone, res = play(day(g))
    assert log == [(sec(10, 8), "long", 15016.0, 15010.0, True)]     # near edge = bar 3's low, stop = bar 2's low (not bar 1's high 15011)
    assert gone == [sec(15, 0)] and res.trades == []                 # never filled: cancelled at 15:00
    log, _, _ = play(day(mirror(g)))
    assert log == [(sec(10, 8), "short", 14984.0, 14990.0, True)]


def test_a_gap_against_the_direction_is_ignored_and_only_the_first_gap_on_the_side_trades():
    down = mirror(up_gap(15010.0), 15010.0)                          # a DOWN gap on an up day: not a signal
    g = UP_OPEN + rest(5, 15010.0) + down + rest(3, 14999.0) + up_gap(14999.0) + rest(3, 15010.0) + up_gap(15010.0) + rest(3, 15021.0)
    log, _, _ = play(day(g))
    assert log == [(sec(10, 14), "long", 15005.0, 14999.0, True)]    # the first up gap only; the second (10:17-10:19) is ignored


def test_no_move_from_0930_to_1000_means_no_trade_and_a_gap_before_10_never_counts():
    flat_open = rest(30, 15000.0)
    assert play(day(flat_open + rest(5, 15000.0) + up_gap(15000.0) + rest(3, 15011.0)))[0] == []
    assert play(day(UP_OPEN + rest(200, 15010.0)))[0] == []         # the 09:32 gap is the only one: it came before 10:00


def test_a_return_fills_at_the_near_edge_and_the_stop_sits_at_the_middle_candle_one_trade_a_day():
    back = (15021.0, 15021.0, 15009.0, 15009.5, 40)                  # through the near edge 15016 and the stop 15010
    g = UP_OPEN + rest(5, 15010.0) + up_gap(15010.0) + rest(3, 15021.0) + [back] + rest(3, 15009.0) + up_gap(15009.0) + rest(3, 15020.0)
    log, _, res = play(day(g))
    assert len(log) == 1 and len(res.trades) == 1
    t = res.trades[0]
    assert (t["side"], t["entry_price"], t["sl"], t["tp"]) == ("long", 15016.0, 15010.0, 15022.0)      # 1:1 on the 6-point stop


def test_registered_with_one_instance_and_the_owners_window():
    assert "fvg_odir" in blocks.WRAPPED and FO.ENTRY_WINDOWS["fvg_odir"] == (sec(10), sec(15) + 59)
    st = FO.FvgOdir(BASE)
    assert st.fam_sessions() == {"t": (sec(9, 30), sec(15, 58))} and st.fam_filter(["nyam", "mid", "pm"]) == ["t"]


def test_pick_newest_moves_the_order_to_each_new_gap_on_the_side_until_one_fills():
    g = UP_OPEN + rest(5, 15010.0) + up_gap(15010.0) + rest(3, 15021.0) + up_gap(15021.0) + rest(3, 15032.0)
    log, gone, res = play(day(g), pick="newest")
    assert log == [(sec(10, 8), "long", 15016.0, 15010.0, True), (sec(10, 14), "long", 15027.0, 15021.0, True)]
    assert gone == [sec(10, 14), sec(15, 0)] and res.trades == []    # the older order is cancelled when the newer gap comes
    assert play(day(g))[0] == log[:1]                                 # first (the default): the second gap is ignored
    back = (15021.0, 15021.0, 15009.0, 15009.5, 40)                  # the first order fills (and stops out) ...
    g2 = UP_OPEN + rest(5, 15010.0) + up_gap(15010.0) + rest(3, 15021.0) + [back] + rest(3, 15009.0) + up_gap(15009.0) + rest(3, 15020.0)
    log, _, res = play(day(g2), pick="newest")
    assert len(log) == 1 and len(res.trades) == 1                    # ... and the day is done: one trade a day


def test_atr1_puts_the_stop_k_times_the_1_minute_atr14_from_the_entry():
    back = (15021.0, 15021.0, 15009.0, 15009.5, 40)
    g = UP_OPEN + rest(5, 15010.0) + up_gap(15010.0) + rest(3, 15021.0) + [back] + rest(60, 15009.0)
    st = FO.FvgOdir({**BASE, "atr1": 2.0})
    st.ROLLS = frozenset()
    res = S.run_session(st, tape_of(day(g)), daily=list(DAILY), on_error="raise")
    t = res.trades[0]
    # the 14 minutes before 10:08: rest bars (range 2) + the gap's three: TRs 2 x 11, then 2, 10, 6 -> mean (22 + 18) / 14
    a1 = (2.0 * 11 + 2.0 + 10.0 + 6.0) / 14.0
    sl = round((15016.0 - 2.0 * a1) * 4) / 4
    assert t["entry_price"] == 15016.0 and abs(t["sl"] - sl) <= 0.25, (t["sl"], sl)
