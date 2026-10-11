"""VWAPADX: the `vwap_adx` entry (families/vwapadx.py), written test-first from Conti's VWAP pullback with ADX gate (video A0G14JYYVTk).

THE RULE UNDER TEST (New York time, 1-minute bars, long only):
    opening range = high / low of 09:30 .. 10:00        VWAP = volume-weighted (h + l + c) / 3 of the minutes from 09:30
    1 arm      a close after 10:00 strictly above the opening range high (once a day)
    2 touch    on that bar or a later one, the low at or under the VWAP
    3 + 4      on the touch bar or a later one: a close strictly above the VWAP, ADX(14) strictly above adx_min and not higher than a bar ago
    entry      market at that close; target = the highest high of the last 5 bars, stop = the lowest low of the last 20 (the signal bar counted)
    one trade a day; flat 15:55
Synthetic days with EXACT numbers cover each behaviour (the ADX is scripted where a test is about the gate, so the gate is tested by itself);
the real BUILD days check the invariants. No net, win rate or profit factor is read.
"""
import pytest

import families
import l2sim as S
from families import blocks as B
from families import vwapadx as VA
from test_blocks import D, days_of, minute_tape, ns, rand_bars, real_days

V = 40
BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "struct", "stop_val": 1.0, "tgt_r": 1.0}
P0 = 15000.0                                                        # the quiet price, and (about) the VWAP of every day below
ORH, ORL = 15020.0, 14990.0


def sec(h, m=0):
    return h * 3600 + m * 60


def q(n, px, v=V):
    """n zero-range minutes at px."""
    return [(px, px, px, px, v)] * n


def head():
    """00:00 .. 10:00 (600 minutes): quiet at 15000; the opening range 09:30-10:00 holds one minute up to 15020 and one down to 14990."""
    b = q(600, P0)
    b[575] = (P0, ORH, P0, P0, V)
    b[585] = (P0, P0, ORL, P0, V)
    return b


def day(after):
    """A full day: head(), then the minutes of `after` from 10:00, then quiet at the last close to 15:59."""
    b = head() + list(after)
    return b + q(960 - len(b), b[-1][3])


# (the VWAP of these days sits between 15000 and 15006: every bar below is clearly on one side of it)
ARM = (15005.0, 15030.0, 15005.0, 15030.0, V)                       # closes above the range high; its low stays above the VWAP
PULL = (15030.0, 15030.0, 14998.0, 14999.0, V)                      # down through the VWAP, closes under it
BACK = (14999.0, 15012.0, 14999.0, 15010.0, V)                      # closes back above the VWAP


class Flat:
    """A scripted ADX: 30.0 at every bar (above 20 and not rising: the gate is open), `at` = {bar number: value} where a test says otherwise."""
    at: dict = {}

    def __init__(self, n=14):
        self.k = 0

    def add(self, h, l, c):
        self.k += 1
        return type(self).at.get(self.k, 30.0)


def scripted(monkeypatch, at=None):
    monkeypatch.setattr(VA, "Adx", type("Scripted", (Flat,), {"at": dict(at or {})}))


def sec_of(ctx):
    return (ctx.now_ns - ns("00:00")) // S.NS


def run(params, bars, cls=None):
    st = (cls or VA.VwapAdx)({**BASE, **params})
    st.ROLLS = frozenset()
    res = S.run_session(st, minute_tape(bars, "00:00", D), daily=[], on_error="raise")
    return st, res


def decisions(params, bars):
    log = []

    class Spy(VA.VwapAdx):
        def _mkt(self, ctx, side, **kw):
            o = super()._mkt(ctx, side, **kw)
            log.append((sec_of(ctx), side, o is not None))
            return o

    run(params, bars, Spy)
    return log


def bar_no(h, m):
    """The number of the 1-minute bar that CLOSES at h:m (bars are counted from 00:00, the first is 1)."""
    return h * 60 + m


# ---- (i) the ADX kept bar by bar is blocks.adx_last -------------------------------------------------------------------------------------------

def test_the_running_adx_equals_adx_last_on_every_bar():
    bars = rand_bars(400, 7)
    H, L, C = [b[1] for b in bars], [b[2] for b in bars], [b[3] for b in bars]
    a = VA.Adx()
    for i in range(len(bars)):
        got, want = a.add(H[i], L[i], C[i]), B.adx_last(H[:i + 1], L[:i + 1], C[:i + 1])
        assert (got is None) == (want is None), i
        if want is not None:
            assert got == pytest.approx(want, rel=1e-12, abs=1e-12), i


# ---- (ii) arm, touch, close back above -----------------------------------------------------------------------------------------------------------

def test_arm_then_touch_then_a_close_back_above_the_vwap_buys_at_that_close(monkeypatch):
    scripted(monkeypatch)
    assert decisions({}, day([ARM, PULL, BACK])) == [(sec(10, 3), "long", True)]


def test_without_a_close_above_the_range_high_there_is_no_trade(monkeypatch):
    scripted(monkeypatch)
    near = (P0, ORH, P0, ORH, V)                                    # closes ON the range high: not above it
    assert decisions({}, day([near, PULL, BACK])) == []
    wick = (P0, 15040.0, P0, 15010.0, V)                            # trades above it and closes back inside
    assert decisions({}, day([wick, PULL, BACK])) == []


def test_a_touch_before_the_arm_does_not_count(monkeypatch):
    scripted(monkeypatch)
    up = ARM                                                        # arms; its low stays above the VWAP
    hold = q(5, 15030.0)
    assert decisions({}, day([PULL, up] + hold)) == []              # the only touch came before the arm
    assert decisions({}, day([PULL, up] + hold + [PULL, BACK])) == [(sec(10, 9), "long", True)]


def test_arm_touch_and_close_can_all_be_one_bar(monkeypatch):
    scripted(monkeypatch)
    one = (P0, 15040.0, 14999.0, 15030.0, V)                        # dips under the VWAP, closes above the range high (and the VWAP)
    assert decisions({}, day([one])) == [(sec(10, 1), "long", True)]


def test_a_close_under_the_vwap_after_the_touch_is_no_signal_the_next_close_above_it_is(monkeypatch):
    scripted(monkeypatch)

    class Look(VA.VwapAdx):
        seen: dict = {}

        def fam_signal(self, ctx):
            type(self).seen[sec_of(ctx)] = self.vwap
            super().fam_signal(ctx)

    Look.seen = {}
    run({}, day([ARM, PULL, BACK]), Look)
    vw = Look.seen[sec(10, 3)]
    assert 15000.0 < vw < 15010.0
    # a bar closing under the VWAP after the touch: nothing; the next bar closing above it: the trade
    under = (14999.0, 14999.0, 14998.5, 14998.5, V)
    assert decisions({}, day([ARM, PULL, under, BACK])) == [(sec(10, 4), "long", True)]


# ---- (iii) the ADX gate ------------------------------------------------------------------------------------------------------------------------------

def test_a_rising_adx_waits_and_the_first_bar_that_is_not_higher_trades(monkeypatch):
    k = bar_no(10, 3)                                               # the bar of BACK
    scripted(monkeypatch, {k - 1: 30.0, k: 31.0, k + 1: 32.0, k + 2: 32.0})
    after = [ARM, PULL, BACK] + q(4, 15010.0)                       # the price stays above the VWAP while the ADX climbs
    assert decisions({}, day(after)) == [(sec(10, 5), "long", True)]            # 32.0 after 32.0: not higher


def test_the_adx_must_be_strictly_above_adx_min(monkeypatch):
    k = bar_no(10, 3)
    scripted(monkeypatch, {k: 20.0, k + 1: 20.0, k + 2: 20.25, k + 3: 20.25})
    after = [ARM, PULL, BACK] + q(4, 15010.0)
    assert decisions({}, day(after)) == [(sec(10, 6), "long", True)]            # 20.0 is not above 20; 20.25 rose; 20.25 again trades
    scripted(monkeypatch, {k: 19.0})
    assert decisions({"adx_min": 18.5}, day([ARM, PULL, BACK])) == [(sec(10, 3), "long", True)]


def test_the_wait_needs_the_price_above_the_vwap_at_the_bar_that_trades(monkeypatch):
    k = bar_no(10, 3)
    scripted(monkeypatch, {k: 31.0, k + 1: 31.0})                   # BACK: rising. The next bar: not rising ...
    under = (15010.0, 15010.0, 14998.0, 14998.0, V)                 # ... and it closes UNDER the VWAP: no trade
    assert decisions({}, day([ARM, PULL, BACK, under])) == []


# ---- (iv) the exits, one trade, the clock ------------------------------------------------------------------------------------------------------------

def test_the_target_is_the_high_of_the_last_5_bars_and_the_stop_the_low_of_the_last_20(monkeypatch):
    scripted(monkeypatch)
    st, res = run({}, day([ARM, PULL, BACK]))
    t = res.trades[0]
    # the last 5 bars before the entry (09:58 .. 10:03): the high is ARM's / PULL's 15030; the last 20 (09:43 ..): the low is the range's 14990
    slip = t["entry_price"] - 15010.0                               # the fill against the signal close: the brackets move with it
    assert t["side"] == "long" and t["tp"] == pytest.approx(15030.0 + slip) and t["sl"] == pytest.approx(14990.0 + slip)
    st, res = run({"tp_bars": 1, "sl_bars": 2}, day([ARM, PULL, BACK]))
    t = res.trades[0]
    slip = t["entry_price"] - 15010.0
    assert t["tp"] == pytest.approx(15012.0 + slip) and t["sl"] == pytest.approx(14998.0 + slip)     # BACK's own high; PULL's low


def test_a_target_within_2_ticks_of_the_close_is_no_trade_and_the_day_goes_on(monkeypatch):
    scripted(monkeypatch)
    top = (14999.0, 15010.25, 14999.0, 15010.0, V)                  # closes a tick under its own high
    later = (15010.0, 15016.0, 15010.0, 15011.0, V)                 # the next bar: its high is 5 points above its close
    got = decisions({"tp_bars": 1}, day([ARM, PULL, top, later]))
    assert got == [(sec(10, 3), "long", False), (sec(10, 4), "long", True)]


def test_min_tp_skips_a_signal_whose_target_is_nearer_and_the_day_goes_on_to_the_next_one(monkeypatch):
    scripted(monkeypatch)
    # BACK closes at 15010 with the 5-bar high at 15030: a target 20 points away
    assert decisions({"min_tp": 20.0}, day([ARM, PULL, BACK])) == [(sec(10, 3), "long", True)]
    assert decisions({"min_tp": 0.0}, day([ARM, PULL, BACK])) == [(sec(10, 3), "long", True)]         # off: the video's rule
    # 20.25 is more than this target: no trade at 10:03 ... and the bars after it sit at 15010 with the high of 15030 leaving the window
    assert decisions({"min_tp": 20.25}, day([ARM, PULL, BACK])) == []
    # ... but a later signal with a far target trades: a new spike up, a fall back to 15010 (above the VWAP), ADX open
    spike = (15010.0, 15060.0, 15010.0, 15055.0, V)
    fall = (15055.0, 15055.0, 15008.0, 15010.0, V)
    got = decisions({"min_tp": 20.25}, day([ARM, PULL, BACK] + q(6, 15010.0) + [spike, fall]))
    assert got == [(sec(10, 11), "long", True)]


def test_one_trade_a_day(monkeypatch):
    scripted(monkeypatch)
    stop_out = (15010.0, 15010.0, 14980.0, 14985.0, V)              # through the stop (14990)
    again = [PULL, BACK]
    got = decisions({}, day([ARM, PULL, BACK, stop_out] + q(3, 14985.0) + again))
    assert got == [(sec(10, 3), "long", True)]
    more = decisions({"max_tr": 3}, day([ARM, PULL, BACK, stop_out] + q(3, 14985.0) + again))
    assert [d[0] for d in more] == [sec(10, 3), sec(10, 9)]         # with a higher cap: a touch and a close of its own trade again


def test_no_entry_in_the_last_5_minutes_and_a_trade_is_flat_at_15_55(monkeypatch):
    scripted(monkeypatch)
    quiet = q(sec(15, 50) // 60 - 600 - 1, 15030.0)                 # armed at 10:01, then above the VWAP until 15:50
    pull = (15030.0, 15030.0, 15020.0, 15021.0, V)                  # (by then the VWAP is near 15028)
    back = (15021.0, 15040.0, 15021.0, 15035.0, V)
    late = day([ARM] + quiet + [pull, back])                        # the close back above comes at 15:52
    assert decisions({}, late) == []
    early = day([ARM] + quiet[:-3] + [pull, back])                  # ... and here at 15:49
    assert [d[0] for d in decisions({}, early)] == [sec(15, 49)]
    wide = (14999.0, 15400.0, 14999.0, 15010.0, V)                  # a target 390 points away
    st, res = run({"tp_bars": 1, "sl_bars": 240}, day([ARM, PULL, wide]))
    t = res.trades[0]
    assert t["exit_reason"] == "time" and t["exit_ms"] == ns("15:55") // 1_000_000


def test_only_the_nyam_pass_trades_and_its_window_is_09_30_to_15_55():
    st = VA.VwapAdx({**BASE})
    assert st.fam_filter(["asia", "london", "pre", "nyam", "mid", "pm"]) == ["nyam"]
    assert st.fam_sessions() == {"nyam": (sec(9, 30), sec(15, 55))}


# ---- (v) real BUILD days: the invariants of the code check, at 1 worker --------------------------------------------------------------------------

@pytest.mark.parametrize("root", ["NQ", "ES"])
def test_real_build_days_hold_one_long_trade_a_day_the_window_and_the_flat_time(root):
    real_days()
    days = days_of(root, 6)
    spec = (VA.VwapAdx, {**BASE})
    out = S.run_many([spec], root=root, days=days, period="build", workers=1, on_error="raise")
    again = S.run_many([spec], root=root, days=days, period="build", workers=1, on_error="raise")
    assert out[0]["trades"] == again[0]["trades"]
    assert out[0]["skipped_by_error"] == 0
    per_day = {}
    for t in out[0]["trades"]:
        d = S._date(t["date"])
        es = (t["entry_ms"] // 1000) - S.et_ns(d, "00:00") // S.NS
        assert t["side"] == "long" and sec(10) < es <= sec(15, 50) + 120, (t["date"], es)
        assert t["exit_ms"] <= S.et_ns(d, "15:55") // 1_000_000 + 60_000
        assert t["sl"] < t["entry_price"] < t["tp"]
        per_day[t["date"]] = per_day.get(t["date"], 0) + 1
    assert all(n == 1 for n in per_day.values())


# ---- (vi) the registry -----------------------------------------------------------------------------------------------------------------------------

def test_the_registry_holds_vwap_adx_wrapped_for_the_blocks():
    assert families.ERRORS == {}
    cls, inputs, both, notes = families.REGISTRY["vwap_adx"]
    assert cls is VA.VwapAdx and both is False and cls.FEATURES == ()
    assert families.MODULE_OF["vwap_adx"] == "vwapadx"
    assert "vwap_adx" in B.BASES and "vwap_adx" in B.WRAPPED
