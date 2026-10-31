"""prev_break_oside (families/prev_break_oside.py): a close beyond the previous bar's high / low, on the 09:30 open's side only; stop = the previous bar's other end."""
from __future__ import annotations

import l2sim as S
from families import blocks as B
from test_blocks import TICK, minute_tape
from test_flex import BIG, trades
from test_orb830 import PX, hold

PB = B.WRAPPED["prev_break_oside"]
P = {"tf": "15", "sess": "nyam", "stop_mode": "struct", "stop_val": 1.0}
K = S._sec("09:30") // 60
T0945 = S._sec("09:45")


def run(c1, open_px=PX):
    """The 09:15 bar spans PX-8 .. PX+8; the 09:30 bar opens at open_px, makes one move to c1 and holds. Returns [(sec, side, entry, stop)]."""
    b = [(PX, PX + TICK, PX - TICK, PX, 40)] * 960
    b[K - 15] = (PX, PX + 8, PX - 8, PX, 40)
    b[K - 14:K] = [hold(PX)] * 14
    b[K] = (open_px, max(open_px, c1) + 1, min(open_px, c1) - 1, c1, 40)
    b[K + 1:] = [hold(c1)] * (len(b) - K - 1)
    st = PB({**BIG, **P})
    st.ROLLS = frozenset()
    return trades(S.run_session(st, minute_tape(b, "00:00"), costs=S.Costs(), daily=[], on_error="raise"))


def test_a_close_over_the_previous_high_above_the_open_is_a_long_stopped_at_the_previous_low():
    t = run(PX + 10)
    assert [(x[0], x[1]) for x in t] == [(T0945 + 15, "long")] and abs(t[0][3] - (PX - 8)) <= 1.0


def test_a_close_under_the_previous_low_below_the_open_is_a_short_stopped_at_the_previous_high():
    t = run(PX - 10)
    assert [(x[0], x[1]) for x in t] == [(T0945 + 15, "short")] and abs(t[0][3] - (PX + 8)) <= 1.0           # the engine keeps the stop distance from the close and shifts it to the fill


def test_a_break_up_that_closes_under_the_09_30_open_is_no_trade():
    assert run(PX + 10, open_px=PX + 12) == []                     # closes above the previous high but below the open
    assert run(PX - 10, open_px=PX - 12) == []                     # closes under the previous low but above the open


def test_per_day_is_the_sessions_entry_cap():
    assert PB({**BIG, **P, "per_day": 3}).p["max_tr"] == 3
