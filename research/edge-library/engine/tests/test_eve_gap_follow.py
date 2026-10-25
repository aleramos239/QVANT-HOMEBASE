"""EVE_GAP_FOLLOW (families/eve_gap_follow.py): the side follows (last price - prior daily close). Synthetic evening, no net or win rate read."""
import datetime as dt

import l2sim as S
from families import blocks as B
from families import eve_gap_follow as G  # noqa: F401  (registers the family)
from test_blocks import D, daily_rows, minute_tape

BASE = {"hold_to": "day", "tf": "5", "sess": "eve", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "exit_bars": 3, "off_min": 120}
BARS = [(15000.0, 15001.0, 14999.0, 15000.0, 40)] * 240


def run(last_range, **params):
    tape = minute_tape(BARS, "18:00", D - dt.timedelta(days=1))
    tape.date = D
    st = B.WRAPPED["eve_gap_follow"]({**BASE, **params})
    st.ROLLS = frozenset()
    return S.run_session(st, tape, daily=daily_rows([100.0] * 24 + [last_range]), on_error="raise", window=st.eve_window, segment="eve").trades


# daily close = 15000 + range / 2, the tape sits at 15000: range -40 = prior close 14980 = gap +20; range +40 = gap -20
def test_a_gap_up_goes_long():
    assert [t["side"] for t in run(-40.0)] == ["long"]


def test_a_gap_down_goes_short():
    assert [t["side"] for t in run(40.0)] == ["short"]


def test_a_gap_under_gap_pts_trades_nothing():
    assert run(-40.0, gap_pts=30.0) == [] and len(run(-40.0, gap_pts=10.0)) == 1
