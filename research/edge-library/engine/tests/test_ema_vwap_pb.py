"""EMA_VWAP_PB: the regime-filtered EMA pullback (families/ema_vwap_pb.py), written with the family.

THE RULE UNDER TEST (15-minute bars, New York time): the close above (below) the EMA(200), the EMA(n) above (below) the 18:00 session VWAP,
the bar's low (high) at or past the EMA(n) and its close back on the trend side of it -> market entry at the next bar's open; no trade
before 14 bars of the day, with fewer than 400 closes of history, or in the other direction.
Synthetic days with exact numbers: flat 1-minute bars at 15000 from 18:00 (VWAP 15000), the history before today patched to a flat run at
`pre` (15010 above, 14990 below), so the EMAs sit above / below the VWAP and decay toward it through the night. One 'push' bar at 03:45-04:00.
No net, win rate or profit factor is read."""
import datetime as dt

import numpy as np

import l2sim as S
from families import avwap as AV
from families import blocks as B
from families import ema_vwap_pb as PB
from test_blocks import D, DAILY, minute_tape

V = 40
P0 = 15000.0
BASE = {"hold_to": "day", "tf": "15", "sess": "asia", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0}
MS0 = S.et_ns(D, "00:00") // 1_000_000
PUSH_MIN = 225                                      # the bar 03:45-04:00 starts at minute 225 of the day; its entry is minute 240


def quiet(n, px=P0):
    return [(px, px + 1, px - 1, px, V)] * n


def day(push, at=PUSH_MIN):
    """18:00 (evening before) .. 15:59: quiet at P0 (1320 minutes), the 15 minutes of `push` starting at minute `at` after 00:00."""
    b = quiet(360 + at) + list(push)
    return b + quiet(1320 - len(b), P0)


def long_push(low=P0 + 1.0, close=P0 + 10.0):
    """15 minute bars closing at `close`; one of them reaches down to `low`."""
    return [(close, close + 1, low, close, V)] + [(close, close + 1, close - 1, close, V)] * 14


def mirror(push):
    return [(2 * P0 - o, 2 * P0 - l, 2 * P0 - h, 2 * P0 - c, v) for o, h, l, c, v in push]


def run(monkeypatch, bars, pre=P0 + 10.0, n_pre=600, params=None):
    """-> the trades. History before today = n_pre closes at `pre`."""
    PB._C.clear()
    AV._MIN.clear()
    tape = minute_tape(bars, "18:00", D - dt.timedelta(days=1))
    tape.date = D                                   # the prints start the evening before, the session is the trade date's
    monkeypatch.setattr(S, "load_tape", lambda d, root="NQ", **kw: tape if str(d) == D.isoformat() else None)
    monkeypatch.setattr(PB, "prior_closes", lambda st, tf, need: np.full(n_pre, pre))
    st = B.WRAPPED["ema_vwap_pb"]({**BASE, **(params or {})})
    st.ROLLS = frozenset()
    return S.run_session(st, tape, daily=list(DAILY), on_error="raise").trades


def test_a_rejection_of_the_ema_above_the_vwap_in_an_uptrend_is_bought(monkeypatch):
    t = run(monkeypatch, day(long_push(close=P0 + 10.0)))
    assert [x["side"] for x in t] == ["long"] and (t[0]["entry_ms"] - MS0) // 60000 == PUSH_MIN + 15


def test_the_mirror_is_sold(monkeypatch):
    t = run(monkeypatch, day(mirror(long_push())), pre=P0 - 10.0)
    assert [x["side"] for x in t] == ["short"] and (t[0]["entry_ms"] - MS0) // 60000 == PUSH_MIN + 15


def test_a_low_that_does_not_reach_the_ema_trades_nothing(monkeypatch):
    assert run(monkeypatch, day(long_push(low=P0 + 6.0))) == []


def test_a_close_under_the_ema200_trades_nothing(monkeypatch):
    assert run(monkeypatch, day(long_push(close=P0 + 5.0))) == []          # EMA(200) is about 15006.8 here, the close 15005


def test_an_ema_on_the_wrong_side_of_the_vwap_trades_nothing(monkeypatch):
    # history at 14990: EMA(50) is about 14997.8 < the VWAP 15000 -> no long, even with the close above the EMA(200)
    assert run(monkeypatch, day(long_push()), pre=P0 - 10.0) == []


def test_too_short_a_history_trades_nothing(monkeypatch):
    assert run(monkeypatch, day(long_push()), n_pre=100) == []


def test_no_entry_before_the_atr_is_warm(monkeypatch):
    assert run(monkeypatch, day(long_push(), at=60)) == []                 # the bar 01:00-01:15 is the 5th of the day: WARM = 14


def test_the_ema_steps_only_through_closed_bars_and_matches_a_direct_run():
    closes = np.array([100.0, 101.0, 99.0, 103.0, 104.0])
    assert abs(PB.ema_run(closes, 3) - _slow(closes, 3)) < 1e-12 and PB.ema_run(np.zeros(0), 3) is None


def _slow(c, n):
    e = c[0]
    for x in c[1:]:
        e = (1 - 2 / (n + 1)) * e + 2 / (n + 1) * x
    return e


def test_prior_closes_run_oldest_first_and_stop_at_a_roll_day(monkeypatch):
    got = {"2023-03-09": (None, np.array([1.0, 2.0])), "2023-03-10": (None, np.array([3.0])), "2023-03-13": (None, np.array([4.0, 5.0]))}
    monkeypatch.setattr(PB, "session_closes", lambda root, iso, tf: got.get(iso))

    class St:
        day, ROLLS = "2023-03-14", frozenset({"2023-03-10"})
        dl = [{"date": k} for k in got]
        _cx = type("C", (), {"root": "NQ"})()

    assert list(PB.prior_closes(St, 15, 100)) == [3.0, 4.0, 5.0]          # the roll day is the first session of its contract
