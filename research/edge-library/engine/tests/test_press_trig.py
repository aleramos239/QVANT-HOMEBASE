"""PRESS_TRIG (engine/press_trig.py): enter with the chart's pressure at +/-lvl, stop at the signal candle's extreme. Synthetic minute days;
tapeflow.pressure is replaced by a fixed answer, no net or win rate is read."""
import l2sim as S
import press_trig as P
from test_noise import DAILY, bar, day, flat, tape_of

BASE = {"tf": "1", "sess": "nyam", "stop_mode": "own", "stop_val": 1.0, "tgt_r": 0.5, "hold_to": "session", "t_end": "15:00", "max_tr": 1}


def trades(monkeypatch, value, bars, **params):
    monkeypatch.setattr(P.TF, "pressure", lambda root, iso, b, tf: value(b) if callable(value) else value)
    st = P.PressTrig({**BASE, **params})
    st.ROLLS = frozenset()
    return S.run_session(st, tape_of(bars), daily=DAILY, on_error="raise").trades


def moves():
    # 09:30-09:34 flat, then one wide candle (low 14990, high 15010), then flat
    return day([bar(15000.0, 15000.0)] * 5 + [(15000.0, 15010.0, 14990.0, 15000.0, 40)] + flat(30, 15000.0))


def test_long_at_plus_lvl_and_short_at_minus_lvl(monkeypatch):
    assert [t["side"] for t in trades(monkeypatch, 30.0, moves())] == ["long"]
    assert [t["side"] for t in trades(monkeypatch, -30.0, moves())] == ["short"]


def test_below_lvl_or_no_tape_is_no_trade(monkeypatch):
    assert trades(monkeypatch, 24.9, moves()) == []
    assert trades(monkeypatch, -24.9, moves()) == []
    assert trades(monkeypatch, None, moves()) == []


def test_lvl_is_a_setting(monkeypatch):
    assert [t["side"] for t in trades(monkeypatch, 12.0, moves(), lvl=10.0)] == ["long"]


def test_no_entry_at_or_after_t_end(monkeypatch):
    assert trades(monkeypatch, 30.0, moves(), t_end="09:30") == []


def test_the_stop_sits_at_the_signal_candles_other_extreme(monkeypatch):
    # pressure fires on the wide candle only (09:35, the minute that closes at 09:36)
    at = lambda b: 30.0 if b == 9 * 3600 + 36 * 60 else None            # noqa: E731
    t = trades(monkeypatch, at, moves())
    assert len(t) == 1 and t[0]["side"] == "long"
    assert (t[0]["sl"], t[0]["tp"]) == (14990.0, 15005.0)               # the candle's low; a target of 0.5 x the 10-point stop


def test_vw18_filter_blocks_longs_below_and_shorts_above_the_vwap(monkeypatch):
    # the day trades at 15000 (VWAP ~15000), then one candle closes at 15000 -> pressure +30 / -30 is read with close == VWAP: neither side passes
    assert trades(monkeypatch, 30.0, moves(), vw18="with") == []
    assert trades(monkeypatch, -30.0, moves(), vw18="with") == []


def test_no_entry_before_t_start(monkeypatch):
    at = lambda b: 30.0 if b == 9 * 3600 + 36 * 60 else None            # noqa: E731  one signal, at 09:36
    assert trades(monkeypatch, at, moves(), t_start="09:45") == []
    assert [t["side"] for t in trades(monkeypatch, at, moves(), t_start="09:30")] == ["long"]
