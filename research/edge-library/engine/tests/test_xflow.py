"""XFLOW: ma_x (a fast average crosses a slow one) and rvol_break (a channel break on relative volume), families/xflow.py, written with the
family (portfolio hunt 2026-10-20). Synthetic days with exact numbers (a quiet day at 15000, one bar changed at a time); relative volume's
reference (avwap.vol_ref) is replaced so the gate is exact. No net, win rate or profit factor is read."""
import pytest

import families
import l2sim as S
from families import avwap as AV
from families import blocks as B
from families import xflow as XF
from test_blocks import D, DAILY, minute_tape
from test_vwap_touch import PX, day, sec

MS0 = S.et_ns(D, "00:00") // 1_000_000
BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0}


def run(cls, params, bars):
    st = cls({**BASE, **params})
    st.ROLLS = frozenset()
    res = S.run_session(st, minute_tape(bars, "00:00"), costs=S.Costs(), daily=list(DAILY), on_error="raise")
    return [((t["entry_ms"] - MS0) // 1000, t["side"], t) for t in sorted(res.trades, key=lambda t: t["entry_ms"])]


def bar(c, v=40, lo=None, hi=None):
    return (c, max(c, hi or c) + 0.25, min(c, lo or c) - 0.25, c, v)


# closes flat at 15000 to 09:59, then 14999 / 14998 (the fast sma(2) under the slow sma(4)), then 15003 at 10:02: fast 15000.5 > slow 15000
CROSS = {"10:00": bar(14999.0), "10:01": bar(14998.0), "10:02": bar(15003.0), **{f"10:{m:02d}": bar(15003.0) for m in range(3, 10)}}
MAP = {"fast": "sma", "fast_n": 2, "slow": "sma", "slow_n": 4, "swing": 3}


def test_the_families_are_registered_wrapped_and_carry_a_structure_level():
    assert families.ERRORS == {}
    for n in ("ma_x", "rvol_break"):
        assert families.MODULE_OF[n] == "xflow" and B.WRAPPED[n].__name__ == f"B_{n}" and n in B.STRUCT_FAMILIES


def test_ma_x_goes_long_at_the_close_of_the_crossing_bar():
    got = run(XF.MaX, MAP, day(CROSS))
    assert [(g[0] // 60, g[1]) for g in got] == [(sec(10, 3) // 60, "long")]


def test_ma_x_structure_stop_is_the_lowest_low_of_the_last_swing_bars():
    got = run(XF.MaX, {**MAP, "stop_mode": "struct", "tgt_r": 1.0}, day(CROSS))
    assert got[0][2]["sl"] == pytest.approx(14998.0 - 0.25)                     # 10:01's low, the lowest of 10:00 .. 10:02


def test_ma_x_rvol_gate(monkeypatch):
    monkeypatch.setattr(AV, "vol_ref", lambda root, dates, a, b: 100.0)
    assert run(XF.MaX, {**MAP, "rvol_m": 1.0}, day(CROSS)) == []                # the crossing bar traded 40, the clock's median 100
    monkeypatch.setattr(AV, "vol_ref", lambda root, dates, a, b: 20.0)
    assert [g[1] for g in run(XF.MaX, {**MAP, "rvol_m": 1.5}, day(CROSS))] == ["long"]    # 40 >= 1.5 x 20


def test_ma_x_vwap_side_blocks_a_long_under_the_session_vwap():
    # one heavy 09:45 bar with a high wick and a close at 15000: the closes (and so the averages) do not move, the session VWAP rises to ~15030
    heavy = {"09:45": (PX, 15100.0, PX - 0.25, PX, 40000)}
    got = run(XF.MaX, {**MAP, "side": "vwap"}, day({**heavy, **CROSS}))
    assert [(g[0] // 60, g[1]) for g in got] == [(sec(10, 11) // 60, "short")]   # the 10:02 cross up (under the VWAP) is skipped; the 10:10 cross down is not
    assert [g[1] for g in run(XF.MaX, {**MAP, "side": "off"}, day({**heavy, **CROSS}))] == ["long"]


def test_ma_x_on_the_0930_vwap_reads_the_anchored_line():
    st = XF.MaX({**BASE, **MAP, "slow": "rth"})
    st.ROLLS = frozenset()
    S.run_session(st, minute_tape(day(CROSS), "00:00"), costs=S.Costs(), daily=list(DAILY), on_error="raise")
    assert st.vwr() is not None


def test_rvol_break_needs_the_channel_and_the_volume(monkeypatch):
    up = {"10:00": bar(15010.0, v=40, lo=15000.0)}                               # a 10-point bar from 15000, closing at 15010
    monkeypatch.setattr(AV, "vol_ref", lambda root, dates, a, b: 10.0)
    got = run(XF.RvolBreak, {"n": 5, "m": 2.0, "stop_mode": "struct", "tgt_r": 1.0}, day(up))
    assert [(g[0] // 60, g[1]) for g in got] == [(sec(10, 1) // 60, "long")]
    assert got[0][2]["entry_price"] - got[0][2]["sl"] == pytest.approx(15010.0 - (15000.0 - 0.25))     # the distance close - the bar's low
    monkeypatch.setattr(AV, "vol_ref", lambda root, dates, a, b: 30.0)
    assert run(XF.RvolBreak, {"n": 5, "m": 2.0}, day(up)) == []                  # 40 < 2 x 30: no break on ordinary volume
    assert run(XF.RvolBreak, {"n": 5, "m": 2.0}, day()) == []                    # no channel break: nothing


def test_rvol_reads_only_the_dates_before_today(monkeypatch):
    seen = []
    monkeypatch.setattr(AV, "vol_ref", lambda root, dates, a, b: seen.append(list(dates)) or 10.0)
    run(XF.RvolBreak, {"n": 5, "m": 2.0}, day({"10:00": bar(15010.0)}))
    assert seen and all(max(d) < D.isoformat() for d in seen)
