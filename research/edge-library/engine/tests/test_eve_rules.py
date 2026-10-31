"""eve_rule (families/eve_rules.py): each rule fires on the side its text says, on a synthetic evening. No net or win rate is read."""
import datetime as dt

import l2sim as S
from families import blocks as B
from families import eve_rules as ER  # noqa: F401  (registers the family)
from test_blocks import D, minute_tape
from test_noise import DAILY, bar, flat

BASE = {"hold_to": "day", "tf": "1", "sess": "eve", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "max_tr": 1}


def run(bars, daily=DAILY, **kw):
    st = B.WRAPPED["eve_rule"]({**BASE, **kw})
    st.ROLLS = frozenset()
    tape = minute_tape(bars, start="18:00", d=D - dt.timedelta(days=1))
    tape.date = D
    return S.run_session(st, tape, daily=daily, on_error="raise", window=st.eve_window, segment="eve").trades


def sides(bars, **kw):
    return [t["side"] for t in run(bars, **kw)]


def last_close(c):
    return DAILY[:-1] + [{**DAILY[-1], "c": c}]


F50 = flat(200, 15050.0)
UP = flat(30, 15050.0) + [bar(15050.0 + 2 * i, 15052.0 + 2 * i) for i in range(40)] + flat(60, 15130.0)


def test_loc10_follows_the_close_location_and_fade_flips_it():
    assert sides(F50, rule="loc10", off_min=30) == []                         # a close in the middle of the range: no trade
    assert sides(F50, daily=last_close(15099.0), rule="loc10", off_min=30) == ["long"]
    assert sides(F50, daily=last_close(15099.0), rule="loc10", off_min=30, mode="fade") == ["short"]
    assert sides(F50, daily=last_close(15001.0), rule="loc10", off_min=30) == ["short"]


def test_wkgap_needs_the_gap_and_follows_it():
    up = flat(200, 15100.0)
    assert sides(up, rule="wkgap", off_min=30, k=0.3) == ["long"]            # a 50-point gap, ATR 100
    assert sides(up, rule="wkgap", off_min=30, k=0.8) == []
    assert sides(up, rule="wkgap", off_min=30, k=0.3, mode="fade") == ["short"]


def test_the_day_of_week_gate_uses_the_trade_date():
    assert D.weekday() == 1
    assert sides(flat(200, 15100.0), rule="wkgap", off_min=30, k=0.3, dow="0") == []
    assert sides(flat(200, 15100.0), rule="wkgap", off_min=30, k=0.3, dow="1") == ["long"]


def test_above_both_the_open_and_the_vwap():
    assert sides(UP, rule="above_both", off_min=60) == ["long"]


def test_range_regime_gate():
    brk = flat(65, 15050.0) + [bar(15050.0 + i, 15051.0 + i) for i in range(30)] + flat(60, 15080.0)
    assert sides(brk, rule="brk_win", rg="quiet", rq=1.5) == ["long"]        # prior range 100 < 1.5 x 100
    assert sides(brk, rule="brk_win", rg="quiet", rq=0.6) == []
    assert sides(brk, rule="brk_win", rg="wide", rq=0.6) == ["long"]


def test_sweep_of_the_first_hour_range_fades():
    up = flat(60, 15050.0) + [(15050.0, 15060.0, 15049.75, 15050.0, 40)] + flat(30, 15050.0)
    assert sides(up, rule="sweep", s_end="19:05") == ["short"]


def test_c18_candle_fade_and_mid_limit():
    c = [bar(15050.0, 15070.0)] + flat(90, 15070.0)
    assert sides(c, rule="c18", k=0.1, tf="1") == ["short"]
    dip = [bar(15050.0, 15070.0)] + flat(5, 15070.0) + [bar(15070.0, 15055.0)] + flat(60, 15055.0)
    assert sides(dip, rule="c18", k=0.1, ent="mid") == ["long"]              # a limit at the candle's 50 % (15060) is hit on the way down


def test_streak_follow_and_fade():
    s = flat(20, 15050.0) + [bar(15050.0, 15052.0), bar(15052.0, 15054.0), bar(15054.0, 15056.0)] + flat(40, 15056.0)
    assert sides(s, rule="streak", nbars=3) == ["long"]
    assert sides(s, rule="streak", nbars=3, mode="fade") == ["short"]


def test_pcb_trades_the_open_side():
    s = flat(20, 15050.0) + [bar(15050.0, 15053.0), bar(15053.0, 15056.0)] + flat(40, 15056.0)
    assert sides(s, rule="pcb") == ["long"]


def test_doji_at_the_evening_high_arms_a_bracket():
    s = [bar(15050.0 + i, 15051.0 + i) for i in range(10)] + [(15060.0, 15064.0, 15056.0, 15060.0, 40), bar(15060.0, 15070.0)] + flat(40, 15070.0)
    assert sides(s, rule="doji", dj=0.1) == ["long"]


def test_gap_disagree_trades_the_candle():
    s = [bar(15050.0, 15040.0)] + flat(60, 15040.0)                           # the gap is 0 (open 15050 = close), so no disagreement
    assert sides(s, rule="gap_disagree") == []
    s = [bar(15040.0, 15060.0)] + flat(60, 15060.0)                           # opens 10 below the prior close, the candle is up
    assert sides(s, rule="gap_disagree") == ["long"]
