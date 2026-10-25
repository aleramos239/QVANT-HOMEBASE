"""TOD_DRIFT_TREND (families/tod_drift_trend.py): tod_drift's entry with a prior-daily-close-vs-SMA gate. Synthetic evening, no net or win rate read."""
import datetime as dt

import l2sim as S
from families import blocks as B
from families import tod_drift_trend as T  # noqa: F401  (registers the family)
from test_blocks import D, daily_rows, minute_tape

BASE = {"hold_to": "day", "tf": "5", "sess": "eve", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "exit_bars": 3, "off_min": 120}
BARS = [(15000.0, 15001.0, 14999.0, 15000.0, 40)] * 240


def run(closes, **params):
    tape = minute_tape(BARS, "18:00", D - dt.timedelta(days=1))
    tape.date = D
    st = B.WRAPPED["tod_drift_trend"]({**BASE, **params})
    st.ROLLS = frozenset()
    return S.run_session(st, tape, daily=daily_rows(closes), on_error="raise", window=st.eve_window, segment="eve").trades


UP, DOWN = [100.0] * 24 + [110.0], [100.0] * 24 + [90.0]


def test_a_long_trades_when_the_prior_close_is_above_the_mean():
    assert [t["side"] for t in run(UP, sma_d=20)] == ["long"]


def test_a_long_waits_when_the_prior_close_is_below_the_mean():
    assert run(DOWN, sma_d=20) == []


def test_the_short_mirror_trades_only_below_the_mean():
    assert [t["side"] for t in run(DOWN, sma_d=20, dir="short")] == ["short"] and run(UP, sma_d=20, dir="short") == []


def test_sma_zero_is_the_plain_drift_on_any_day():
    assert len(run(DOWN, sma_d=0)) == 1 and len(run(UP, sma_d=0)) == 1


def test_too_few_daily_bars_trade_nothing():
    assert run([100.0] * 5 + [110.0], sma_d=20) == []
