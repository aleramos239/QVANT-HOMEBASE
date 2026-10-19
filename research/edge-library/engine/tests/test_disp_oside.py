"""DISP OSIDE: the `disp_oside` entry trigger (families/disp_oside.py), the owner's idea of 2026-10-19 (the third one).

THE RULE UNDER TEST: below the 09:30 open -> long on the first up displacement (body larger than the previous bar's, close above its high),
above -> short on the mirror; market at the close, 30-point stop, one trade a day. Synthetic 1-minute days (test_open_fvg's helpers)."""
import l2sim as S
from families import blocks
from families import disp_oside as DO
from test_blocks import DAILY
from test_open_fvg import bar, day, mirror, rest, sec
from test_fvg_oside import tape_of

BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 30.0, "tgt_r": 0.5}

DROP = [bar(15000.0, 14990.0), bar(14990.0, 14989.0)]          # below the open; the 09:30 bar is a down displacement on the wrong side
DISP = bar(14989.0, 14995.0)                                    # body 6 > 1, close above the previous high 14990: long at 09:32


def play(bars):
    st = DO.DispOside(BASE)
    st.ROLLS = frozenset()
    return S.run_session(st, tape_of(day(bars)), daily=list(DAILY), on_error="raise").trades


def test_below_the_open_an_up_displacement_goes_long_with_a_30_point_stop_and_one_trade_a_day():
    g = DROP + [DISP] + rest(5, 14995.0) + [bar(14995.0, 14985.0), bar(14985.0, 14995.0)] + rest(200, 14995.0)
    t = play(g)
    assert len(t) == 1                                          # the second displacement at 09:39 is not traded
    t = t[0]
    assert t["side"] == "long" and t["sl"] == t["entry_price"] - 30.0 and t["tp"] == t["entry_price"] + 15.0
    assert abs(t["entry_price"] - 14995.0) <= 1.5          # filled on the next print (tick replay)
    s = play(mirror(g))
    assert len(s) == 1 and s[0]["side"] == "short" and abs(s[0]["entry_price"] - 15005.0) <= 1.5


def test_a_displacement_with_the_side_or_a_smaller_body_or_no_close_through_the_wick_is_no_trade():
    assert play([bar(15000.0, 15001.0), bar(15001.0, 15010.0)] + rest(200, 15010.0)) == []    # up displacement above the open
    assert play(DROP + [bar(14989.0, 14989.5)] + rest(200, 14989.5)) == []                       # body 0.5 < 1
    assert play(DROP + [(14985.0, 14990.0, 14985.0, 14989.5, 40)] + rest(200, 14989.5)) == []    # body 4.5, close under the high 14990


def test_registered_with_one_instance_and_the_window_0930_1500():
    assert "disp_oside" in blocks.WRAPPED and DO.ENTRY_WINDOWS["disp_oside"] == (sec(9, 30), sec(15) + 59)
