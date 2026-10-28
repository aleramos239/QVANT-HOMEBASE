"""first5_follow (families/first5_follow.py): win_candle, and a doji traded the way of the gap (open vs the prior daily close)."""
from __future__ import annotations

import pytest

import l2sim as S
from families import blocks as B
from test_blocks import TICK, daily_rows, minute_tape
from test_flex import BIG, trades
from test_orb830 import PX, hold

F5, WCAN = B.WRAPPED["first5_follow"], B.WRAPPED["win_candle"]
P = {"tf": "5", "sess": "nyam", "start": "09:30"}
K = S._sec("09:30") // 60
GREEN = (PX, PX + 7.0, PX - 1.0, PX + 6.0, 40)
RED = (PX, PX + 1.0, PX - 7.0, PX - 6.0, 40)
DOJI = (PX, PX + 3.0, PX - 2.0, PX, 40)


def sides(cls, candle, prior_close):
    b = [(PX, PX + TICK, PX - TICK, PX, 40)] * 960
    b[K] = candle
    b[K + 1:K + 5] = [hold(candle[3])] * 4
    st = cls({**BIG, **P})
    st.ROLLS = frozenset()
    daily = daily_rows([2 * (prior_close - 15000.0)] * 25)          # close = 15000 + r / 2
    res = S.run_session(st, minute_tape(b, "00:00"), costs=S.Costs(), daily=daily, on_error="raise")
    return [x[1] for x in trades(res)]


@pytest.mark.parametrize("candle,want", [(GREEN, ["long"]), (RED, ["short"])])
def test_a_coloured_candle_is_win_candle(candle, want):
    for pc in (14950.0, 15050.0):
        assert sides(F5, candle, pc) == sides(WCAN, candle, pc) == want


def test_a_doji_goes_with_the_gap():
    assert sides(WCAN, DOJI, 14950.0) == []                        # win_candle trades nothing
    assert sides(F5, DOJI, 14950.0) == ["long"]                    # open above the prior close
    assert sides(F5, DOJI, 15050.0) == ["short"]                   # open below it
    assert sides(F5, DOJI, 15000.0) == []                          # no gap: no vote
