"""JJ FAIR: the `jj_fair` entry trigger (families/jj_fair.py), JJ Simon's fair-price reversion as taught (the owner, 2026-10-19).

THE RULE UNDER TEST: fair = the 09:30 open; 09:35-11:00, 30+ points below it -> long on an up displacement (body larger than the previous
red bar's, close above its high), above -> short on the mirror; market at the close, 25 / 38 points, every signal one at a time, stop
after 3 losses in a row. Synthetic 1-minute days (test_open_fvg's helpers)."""
import l2sim as S
from families import blocks
from families import jj_fair as JJ
from test_blocks import DAILY
from test_open_fvg import bar, day, mirror, rest, sec
from test_fvg_oside import tape_of

BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 25.0, "tgt_r": 38.0 / 25.0}

DROP = [bar(15000.0, 14990.0), bar(14990.0, 14975.0), bar(14975.0, 14965.0), bar(14965.0, 14960.0), bar(14960.0, 14958.0)]  # 09:30-09:34


def pair(p):
    """A red bar down to p, then an up displacement to p + 7 (body 7 > 3, close above the red bar's high p + 3)."""
    return [bar(p + 3.0, p), bar(p, p + 7.0)]


def play(bars, pre=15000.0, **kw):
    st = JJ.JjFair({**BASE, **kw})
    st.ROLLS = frozenset()
    return S.run_session(st, tape_of(day(bars, pre=pre)), daily=list(DAILY), on_error="raise").trades


def test_30_points_below_the_open_an_up_displacement_goes_long_25_stop_38_target():
    g = DROP + pair(14955.0) + rest(300, 14962.0)
    t = play(g)
    assert len(t) == 1
    t = t[0]
    assert t["side"] == "long" and t["sl"] == t["entry_price"] - 25.0 and abs(t["tp"] - (t["entry_price"] + 38.0)) < 1e-9
    assert abs(t["entry_price"] - 14962.0) <= 1.5          # filled on the next print (tick replay)
    s = play(mirror(g))
    assert len(s) == 1 and s[0]["side"] == "short" and abs(s[0]["entry_price"] - 15038.0) <= 1.5


def test_too_close_to_the_open_or_before_0935_or_after_1100_is_no_trade():
    near = [bar(15000.0, 14990.0), bar(14990.0, 14985.0)] + rest(3, 14985.0)
    assert play(near + pair(14980.0) + rest(300, 14987.0)) == []                       # close 14987: 13 points from the open
    assert play([bar(15000.0, 14958.0)] + pair(14955.0) + rest(300, 14962.0)) == []    # the displacement closes at 09:33
    late = DROP + rest(85, 14958.0)                                                     # 09:35 .. 10:59 quiet, the pair at 11:00-11:01
    assert play(late + pair(14955.0) + rest(300, 14962.0)) == []


def test_the_bar_before_must_be_the_opposite_colour_unless_opp_off():
    g = DROP + [bar(14955.0, 14958.0), bar(14958.0, 14965.0)] + rest(300, 14965.0)     # green then a bigger green
    assert play(g) == []
    t = play(g, opp="off")
    assert len(t) == 1 and t[0]["side"] == "long"


def test_wick_off_takes_a_bigger_body_that_does_not_close_beyond_the_wick():
    g = DROP + [(14958.0, 14966.0, 14955.0, 14955.0, 40), bar(14955.0, 14963.0)] + rest(300, 14963.0)  # body 8 > 3, close under 14966
    assert play(g) == []
    assert len(play(g, wick="off")) == 1


def test_every_signal_one_at_a_time_and_done_after_three_losses_in_a_row():
    g, p = list(DROP), 14955.0
    for _ in range(4):
        g += pair(p) + [bar(p + 7.0, p - 25.0)]            # each long is stopped 25 below its entry by the next bar
        p -= 28.0
    t = play(g + rest(300, p + 3.0))
    assert len(t) == 3 and all(x["side"] == "long" and x["net"] < 0 for x in t)
    assert len(play(g + rest(300, p + 3.0), max_loss=4)) == 4


def test_registered_with_the_window_0935_1100():
    assert "jj_fair" in blocks.WRAPPED and JJ.ENTRY_WINDOWS["jj_fair"] == (sec(9, 35), sec(11) + 59)


def test_break_of_structure_entry_closes_past_the_last_known_swing_toward_fair():
    # below the open: a swing high at bar 09:37 (high 14966 above both neighbours), known at 09:38; the 09:39 close above it = long
    g = DROP + [bar(14958.0, 14960.0), (14960.0, 14966.0, 14959.0, 14962.0, 40), bar(14961.5, 14962.0), bar(14962.0, 14968.0)] + rest(300, 14968.0)
    assert play(g) == []                                                                  # no displacement there (the bar before is green too)
    t = play(g, entry="bos")
    assert len(t) == 1 and t[0]["side"] == "long" and abs(t[0]["entry_price"] - 14968.0) <= 1.5
    assert len(play(g, entry="both")) == 1


def test_vwap_fair_reads_the_session_vwap_instead_of_the_open():
    g = DROP + pair(14955.0) + rest(300, 14962.0)
    assert play(g) and play(g, fair="vwap") == []       # the VWAP sits near 14965 after the drop: no 30 points of room


def test_adapt_fair_moves_the_line_after_three_losses_instead_of_stopping():
    g, p = list(DROP), 14955.0
    for _ in range(4):
        g += pair(p) + [bar(p + 7.0, p - 25.0)]
        p -= 28.0
    g += rest(300, p + 3.0)
    assert len(play(g)) == 3
    t = play(g, fair="adapt")
    assert len(t) >= 3 and t[-1]["entry_price"] < t[2]["entry_price"] - 20   # after the 3rd loss the line moved down, trading went on


STRUCT = {"stop_mode": "struct", "tgt_r": 1.5}


def test_room_exit_is_80_percent_of_the_way_to_fair_at_1_to_1_5():
    g = DROP + pair(14950.0) + rest(300, 14957.0)           # the close 14957 is 43 points under the open
    t = play(g, exit="room", **STRUCT)
    assert len(t) == 1
    e, tp, sl = t[0]["entry_price"], t[0]["tp"], t[0]["sl"]
    assert abs((tp - e) - 0.8 * 43.0) < 2.0 and abs((e - sl) - 0.8 * 43.0 / 1.5) < 2.0


def test_a_displacement_under_a_structure_stop_gets_25_points_not_the_default_stop_val():
    g = DROP + pair(14955.0) + rest(300, 14962.0)
    t = play(g, stop_val=1.5, **STRUCT)                    # the taught lane leaves the Template's 1.5 default: it must not be the stop
    assert len(t) == 1 and abs((t[0]["entry_price"] - t[0]["sl"]) - 25.0) < 1.6


def test_the_opening_continuation_trades_the_first_candles_colour_once_a_day():
    g = [bar(15000.0, 14985.0)] + rest(300, 14985.0)      # a 15-point red open: short at 09:31, 25 / 38
    t = play(g, cont="on", stop_mode="struct", tgt_r=1.52)
    assert len(t) == 1 and t[0]["side"] == "short" and abs((t[0]["sl"] - t[0]["entry_price"]) - 25.0) < 1.6
    big = [bar(15000.0, 14960.0)] + rest(300, 14960.0)    # a 40-point body: 50 / 76
    b = play(big, cont="on", stop_mode="struct", tgt_r=1.52)
    assert len(b) == 1 and abs((b[0]["sl"] - b[0]["entry_price"]) - 50.0) < 1.6
    assert play(g) == []                                   # cont off: no trade from the opening candle


def test_start_10_00_skips_the_first_half_hour():
    g = DROP + pair(14955.0) + rest(300, 14962.0)
    assert play(g) and play(g, start="10:00") == []


def test_screen_readings_any_mom_pre_and_the_second_candle_continuation():
    g = DROP + pair(14955.0) + rest(300, 14962.0)
    assert len(play(g, entry="any")) == 1 and play(g, entry="any")[0]["side"] == "long"      # every close toward fair, one at a time
    m = play(mirror(DROP) + mirror(pair(14955.0)) + rest(300, 15038.0), entry="mom")
    assert m == []                                                                           # that displacement points toward fair: mom skips it
    assert play(g, fair="pre") and abs(play(g, fair="pre")[0]["entry_price"] - 14962.0) <= 1.5   # pre-open close 15000 = the open here
    two = [bar(15000.0, 14995.0), bar(14995.0, 14985.0)] + rest(300, 14985.0)
    t = play(two, cont="2nd", stop_mode="struct", tgt_r=1.52)
    assert len(t) == 1 and t[0]["side"] == "short" and abs((t[0]["sl"] - t[0]["entry_price"]) - 25.0) < 1.6


def test_momb_breaks_structure_away_from_fair_and_cbias_blocks_a_continuation_with_the_last_6_hours():
    # above the open after a rise: a swing low at 15046 (bar 09:37), known at 09:38; the 09:39 close under it = short, away from fair? no: toward.
    up = [bar(15000.0, 15010.0), bar(15010.0, 15025.0), bar(15025.0, 15035.0), bar(15035.0, 15040.0), bar(15040.0, 15042.0),
          bar(15042.0, 15040.0), (15040.0, 15041.0, 15034.0, 15038.0, 40), bar(15038.5, 15038.0), bar(15038.0, 15032.0)] + rest(300, 15032.0)
    assert play(up, entry="momb") == []                      # that break points back toward the open: not momentum
    assert len(play(up, entry="bos")) == 1                   # ... it is the fade's structure entry
    one = [bar(15000.0, 15015.0)] + rest(300, 15015.0)
    assert len(play(one, cont="on", stop_mode="struct", tgt_r=1.52)) == 1
    assert play(one, pre=14900.0, cont="on", cbias="on", stop_mode="struct", tgt_r=1.52) == []   # up 100 since 03:30: the bias is short, no long
    assert len(play(one, pre=15100.0, cont="on", cbias="on", stop_mode="struct", tgt_r=1.52)) == 1   # down 100 since 03:30: the long is with the bias


def test_entry_cont_is_the_opening_continuation_alone():
    g = [bar(15000.0, 14985.0)] + DROP[1:] + pair(14955.0) + rest(300, 14962.0)
    t = play(g, entry="cont", cont="on", stop_mode="struct", tgt_r=1.52)
    assert len(t) == 1 and t[0]["side"] == "short"           # the 09:31 short only; the later displacement is not traded


def test_batch5_knobs_min_body_vwap_dir_and_hours():
    g = DROP + pair(14955.0) + rest(300, 14962.0)              # the displacement body is 7 points; quiet bars give an ATR of ~2-3
    assert play(g) and play(g, min_body=5.0) == []              # 7 < 5 x ATR(~2.5): no trade
    m = mirror(DROP) + mirror(pair(14955.0)) + rest(300, 15038.0)
    assert play(g, entry="mom") == [] and play(m, entry="mom") == []   # both displacements point toward fair: mom skips them
    assert play(g, hours="pm") == [] and play(g, hours="am")    # 09:41 is inside am, outside pm
    assert play(g, vwap_dir="on") == []                         # a long below the session VWAP (price fell from 15000) is refused


def test_vwap_slope_and_pullback_knobs():
    g = DROP + pair(14955.0) + rest(300, 14962.0)              # the fade's long after a 45-point drop: the VWAP is falling
    assert play(g) and play(g, vwap_slope=5) == []              # a long against a falling VWAP is refused
    m = mirror(g)                                               # the mirror: a short after a rise, the VWAP rising: refused too
    assert play(m) and play(m, vwap_slope=5) == []
    assert play(g, pullback="on") == []                         # the bar before (14955-14958) never touched the VWAP (~14970): refused


def test_near_widens_the_vwap_touch():
    g = DROP + pair(14955.0) + rest(300, 14962.0)
    assert play(g, pullback="on", vwap_slope=0) == [] and play(g, pullback="on", vwap_slope=0, near=30.0)   # ~15 points off the VWAP: a 30-point band takes it


def test_cont_min_takes_only_a_big_opening_bar():
    small = [bar(15000.0, 14985.0)] + rest(300, 14985.0)
    big = [bar(15000.0, 14960.0)] + rest(300, 14960.0)
    assert play(small, cont="on", cont_min=25.0, stop_mode="struct", tgt_r=1.52) == []
    assert len(play(big, cont="on", cont_min=25.0, stop_mode="struct", tgt_r=1.52)) == 1
