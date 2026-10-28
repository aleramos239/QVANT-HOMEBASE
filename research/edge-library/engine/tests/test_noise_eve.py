"""noise_band_eve (families/noise_eve.py): the noise band anchored at the 18:00 evening open. Synthetic minute evening; no net or win rate read."""
import datetime as dt

import l2sim as S
from families import blocks as B
from families import noise_eve as NE  # noqa: F401  (registers the family)
from test_blocks import D, minute_tape
from test_noise import BAND, DAILY, flat, bar

BASE = {"hold_to": "day", "tf": "1", "sess": "eve", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "max_tr": 5, "k": 0.25, "anchor": "eve"}


def run(bars, **kw):
    st = B.WRAPPED["noise_band_eve"]({**BASE, **kw})
    st.ROLLS = frozenset()
    tape = minute_tape(bars, start="18:00", d=D - dt.timedelta(days=1))
    tape.date = D
    return S.run_session(st, tape, daily=DAILY, on_error="raise", window=st.eve_window, segment="eve").trades


def test_a_close_beyond_the_evening_band_and_the_vwap_trades_with_it():
    up = flat(100) + [bar(15000.0 + i, 15001.0 + i) for i in range(60)]          # the band is 15025: crossed from the 26th rising minute
    dn = flat(100) + [bar(15000.0 - i, 14999.0 - i) for i in range(60)]
    assert [t["side"] for t in run(up)][:1] == ["long"] and [t["side"] for t in run(dn)][:1] == ["short"]


def test_a_flat_evening_is_no_trade_and_the_band_is_k_times_the_daily_atr():
    assert run(flat(160)) == []
    wide = flat(100) + [bar(15000.0 + i, 15001.0 + i) for i in range(60)]
    assert run(wide, k=3.0) == []                                                # a 300-point band is not crossed
    assert BAND == 25.0
