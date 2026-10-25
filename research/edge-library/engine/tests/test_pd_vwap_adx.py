"""PD_VWAP_ADX: the prior-RTH-extreme fade stretched from VWAP with ADX turning down (families/pd_vwap_adx.py), written with the family.

THE RULE UNDER TEST (5-minute bars, New York time): a bar whose high reaches the prior RTH high (low reaches the prior RTH low) AND closes at
least k x ATR(14) above (below) the 09:30 VWAP AND has ADX(14) lower than the bar before -> market entry; one trade a day; flat 15:55.
Synthetic days with exact numbers: 2-point minute bars at 15000 (ATR about 2, VWAP 15000) and one pushed bar at 10:00. The ADX is scripted
(bar number k counted from 00:00: the 10:00 bar is the 121st) so the gate is tested by itself; the prior level is patched except in the test
of rth_level. No net, win rate or profit factor is read."""
import numpy as np

import l2sim as S
from families import blocks as B
from families import pd_vwap_adx as PV
from families import vwapadx as VA
from test_blocks import D, DAILY, minute_tape

V = 40
P0 = 15000.0
BASE = {"hold_to": "day", "tf": "5", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0}
MS0 = S.et_ns(D, "00:00") // 1_000_000
PUSH_BAR = 121                                      # the 10:00-10:05 bar, counted from 00:00 in 5-minute bars


def quiet(n, px=P0):
    return [(px, px + 1, px - 1, px, V)] * n


def day(push):
    """00:00 .. 10:00 quiet, then the five minutes of `push`, then quiet at the last close to 15:59."""
    b = quiet(600) + list(push)
    return b + quiet(960 - len(b), b[-1][3])


UP = [(P0, P0 + 8, P0, P0 + 8, V)] + [(P0 + 8, P0 + 12, P0 + 8, P0 + 8, V)] * 4         # high 15012, close 15008
DOWN = [(2 * P0 - o, 2 * P0 - l, 2 * P0 - h, 2 * P0 - c, v) for o, h, l, c, v in UP]    # the mirror: low 14988, close 14992


class Scripted:
    """A scripted ADX: 30.0 at every bar, `at` = {bar number: value}."""
    at: dict = {}

    def __init__(self, n=14):
        self.k = 0

    def add(self, h, l, c):
        self.k += 1
        return type(self).at.get(self.k, 30.0)


def run(monkeypatch, bars, adx=None, level=(15010.0, 14990.0), params=None):
    """-> the trades: the ADX falls at the push bar unless `adx` says otherwise; level = the patched prior RTH (high, low)."""
    monkeypatch.setattr(PV, "Adx", type("S", (Scripted,), {"at": {PUSH_BAR: 25.0} if adx is None else adx}))
    monkeypatch.setattr(PV, "rth_level", lambda root, iso: level)
    st = B.WRAPPED["pd_vwap_adx"]({**BASE, **(params or {})})
    st.ROLLS = frozenset()
    return S.run_session(st, minute_tape(bars, "00:00"), daily=list(DAILY), on_error="raise").trades


def test_a_push_into_the_prior_high_with_adx_falling_is_faded(monkeypatch):
    t = run(monkeypatch, day(UP))
    assert [x["side"] for x in t] == ["short"] and (t[0]["entry_ms"] - MS0) // 60000 == 605


def test_a_push_into_the_prior_low_with_adx_falling_is_bought(monkeypatch):
    t = run(monkeypatch, day(DOWN))
    assert [x["side"] for x in t] == ["long"] and (t[0]["entry_ms"] - MS0) // 60000 == 605


def test_adx_rising_or_unchanged_trades_nothing(monkeypatch):
    assert run(monkeypatch, day(UP), adx={PUSH_BAR: 35.0}) == []
    assert run(monkeypatch, day(UP), adx={}) == []


def test_a_bar_that_does_not_reach_the_level_trades_nothing(monkeypatch):
    assert run(monkeypatch, day(UP), level=(15020.0, 14990.0)) == []


def test_a_close_short_of_k_atr_from_the_vwap_trades_nothing(monkeypatch):
    assert run(monkeypatch, day(UP), params={"k": 5.0}) == []


def test_no_prior_level_trades_nothing(monkeypatch):
    assert run(monkeypatch, day(UP), level=None) == []


def test_one_trade_a_day_and_flat_at_15_55(monkeypatch):
    t = run(monkeypatch, day(UP + UP), adx={PUSH_BAR: 25.0, PUSH_BAR + 1: 20.0})
    assert len(t) == 1 and t[0]["exit_reason"] == "time" and t[0]["exit_ms"] == S.et_ns(D, "15:55") // 1_000_000


def test_only_the_nyam_pass_trades_and_its_window_is_09_30_to_15_55():
    st = PV.PdVwapAdx({**BASE})
    assert st.fam_filter(["asia", "london", "pre", "nyam", "mid", "pm"]) == ["nyam"]
    assert st.fam_sessions() == {"nyam": (34200, 57300)}


def test_rth_level_keeps_only_the_bars_from_09_30_to_16_00(monkeypatch):
    t = lambda hm: S.et_ns(D, hm)
    # 5-minute bars (end_ns, high, low): overnight 15100 / 14900, the bar ending 09:30 (an overnight bar), 09:35, 16:00, 16:05 (after the close)
    end = np.array([t("03:00"), t("09:30"), t("09:35"), t("16:00"), t("16:05")], np.int64)
    hi = np.array([15100.0, 15090.0, 15010.0, 15005.0, 15080.0])
    lo = np.array([14900.0, 14910.0, 14990.0, 14985.0, 14920.0])
    monkeypatch.setattr(PV.L, "session_bars", lambda root, iso: (end, hi, lo))
    assert PV.rth_level("NQ", D.isoformat()) == (15010.0, 14985.0)


def test_the_adx_is_the_blocks_adx():
    """Wilder's ADX kept bar by bar equals families/blocks.adx_last on every bar (the same class vwapadx holds to it)."""
    g = np.random.default_rng(7)
    c = 15000 + np.cumsum(g.normal(0, 5, 120))
    h, l = c + g.uniform(0, 4, 120), c - g.uniform(0, 4, 120)
    ax = VA.Adx()
    for i in range(120):
        a = ax.add(h[i], l[i], c[i])
        want = B.adx_last(h[:i + 1], l[:i + 1], c[:i + 1])
        assert (a is None) == (want is None) and (a is None or abs(a - want) < 1e-9)
