"""BIG_PRINT: the `big_print` entry trigger (families/big_print.py), the owner's idea of 2026-10-12: when an order of MORE than `lots`
contracts is filled, enter with it. One trade a day, from 09:30.

THE RULE UNDER TEST (restated in the module text):
    ORDER  = the largest aggressor order of a whole minute (flowtab's `big` series: prints sharing one exchange stamp), signed by its side
    SIGNAL = at a 1-minute bar's close, that minute's largest order is strictly above `lots` -> its side, market order at the next open
    one position at a time, max_tr entries a session (default 1), entries inside the idea's session only (a close in (start, end])
Seeded random minutes are checked against an independent restatement; exact synthetic cases pin the strict inequality, the minute of the
decision, the pre-open order, the sign and the one-trade cap. No net, win rate or profit factor is read.
"""
import numpy as np
import pytest

import families
import flowtab as FT
import l2sim as S
from families import blocks as B
from families import big_print as BP
from test_blocks import D, DAILY, TICK, minute_tape, ns, rand_bars
from test_blocks_flow import minute_index, prefix, series_at

BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "max_tr": 20, "lots": 25}
PX = 15000.0
NY_START, NY_END = 34200, 39600                      # 09:30 - 11:00 ET, seconds after 00:00 ET


def flow_table(monkeypatch, big):
    tab = {D.isoformat(): prefix(vol=100, big=big)}
    monkeypatch.setattr(FT, "_table", lambda r: tab)
    return tab


class Sig(BP.BigPrint):
    """Logs every signal the family sees (no order is placed, so every qualifying close shows): (second, side)."""
    seen: list = []

    def fam_signal(self, ctx):
        if self.go:
            type(self).seen.append(((ctx.now_ns - ns("00:00")) // S.NS, "long" if self.go > 0 else "short"))


def signals(params, bars):
    cls = type("Sig", (Sig,), {"seen": []})
    st = cls({**BASE, **params})
    st.ROLLS = frozenset()
    S.run_session(st, minute_tape(bars, "00:00"), daily=list(DAILY), on_error="raise")
    return list(cls.seen)


def restate(big, lots):
    """The rule, written again from the text: [(close second, side)] of every minute close inside the session whose largest order is > lots."""
    out = []
    for m in range(NY_START // 60 - 1, NY_END // 60):                # the minute that starts at m * 60 closes at (m + 1) * 60
        v = int(big[minute_index(m * 60)])
        close = (m + 1) * 60
        if abs(v) > lots and NY_START < close <= NY_END:
            out.append((close, "long" if v > 0 else "short"))
    return out


def quiet_bars():
    return [(PX, PX + TICK, PX - TICK, PX, 40)] * 960


@pytest.mark.parametrize("seed,lots", [(1, 25), (2, 25), (3, 10), (4, 40)])
def test_signals_are_the_rule_restated_on_random_days(monkeypatch, seed, lots):
    g = np.random.default_rng(300 + seed)
    big = g.integers(-60, 61, FT.NMIN)
    flow_table(monkeypatch, big)
    got = signals({"lots": lots}, rand_bars(960, seed, step=7.0))
    want = restate(big, lots)
    assert len(want) > 0, "the seeded day has no signal inside the session: the test would prove nothing"
    interior = [x for x in want if x[0] < NY_END - 300]                 # never in the last 5 minutes of the session
    assert set(interior) <= set(got) <= set(want)


def test_an_order_of_exactly_the_size_is_not_above_it(monkeypatch):
    flow_table(monkeypatch, series_at({9 * 3600 + 40 * 60: 25, 9 * 3600 + 50 * 60: 26}))
    assert signals({"lots": 25}, quiet_bars()) == [(9 * 3600 + 51 * 60, "long")]


def test_the_decision_is_at_the_close_of_the_minute_of_the_order_and_the_sign_is_the_side(monkeypatch):
    flow_table(monkeypatch, series_at({9 * 3600 + 40 * 60: -30}))
    assert signals({}, quiet_bars()) == [(9 * 3600 + 41 * 60, "short")]


def test_an_order_before_the_open_is_no_signal(monkeypatch):
    """The minute 09:29 closes at 09:30:00, which is not inside (start, end]; a 08:45 order is outside the session altogether."""
    flow_table(monkeypatch, series_at({9 * 3600 + 29 * 60: 80, 8 * 3600 + 45 * 60: -80}))
    assert signals({}, quiet_bars()) == []


def test_the_first_minute_of_the_session_can_signal(monkeypatch):
    flow_table(monkeypatch, series_at({9 * 3600 + 30 * 60: 40}))
    assert signals({}, quiet_bars()) == [(9 * 3600 + 31 * 60, "long")]


def test_no_flow_row_for_the_day_means_no_signal(monkeypatch):
    monkeypatch.setattr(FT, "_table", lambda r: {})
    assert signals({}, rand_bars(960, 9, step=7.0)) == []


def test_one_trade_a_day_is_the_default_and_the_cap(monkeypatch):
    """Three qualifying minutes, the real order logic: with max_tr 1 the day has ONE entry, at the first of them."""
    flow_table(monkeypatch, series_at({9 * 3600 + 35 * 60: 40, 9 * 3600 + 40 * 60: -40, 9 * 3600 + 45 * 60: 40}))
    assert BP.BigPrint.DEFAULTS["max_tr"] == 1

    bars = quiet_bars()
    bars[9 * 60 + 37] = (PX, PX + TICK, PX - 20.0, PX, 40)               # stops the 09:36 long (5 pt stop) out ...
    bars[9 * 60 + 42] = (PX, PX + 20.0, PX - TICK, PX, 40)               # ... and the 09:41 short: one position at a time is free again

    def entries(cap):
        st = BP.BigPrint({**BASE, "max_tr": cap, "stop_val": 5.0})
        st.ROLLS = frozenset()
        S.run_session(st, minute_tape(bars, "00:00"), daily=list(DAILY), on_error="raise")
        return st.n_ent
    assert (entries(1), entries(3)) == (1, 3)                            # the cap is what holds it to one: three are on offer


def test_the_family_is_registered_bar_based_and_one_minute_only():
    assert "big_print" in families.REGISTRY
    assert "big_print" in B.BASES and "big_print" in B.WRAPPED
    assert BP.BigPrint.SCREEN_TFS == ("1",)
