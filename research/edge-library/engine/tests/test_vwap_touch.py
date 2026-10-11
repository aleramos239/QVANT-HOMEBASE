"""VWAP_TOUCH: the `vwap_touch` entry trigger (families/vwap_touch.py), the first return to VWAP, written test-first from its rule.

THE RULE UNDER TEST (Rother, IQCapital, XWJlBBikUc0; the owner's request of 2026-10-11):
    VWAP     = volume-weighted (h + l + c) / 3 of the 1-minute bars from the anchor (us 09:30, london 03:00, day 00:00 ET)
    arm      = a 1-minute close at least `away` ticks above the VWAP arms a LONG, at least `away` ticks below a SHORT
    order    = at a tf close, an arm set, flat: a limit AT the VWAP (long below the last print, short above it), re-priced at every tf close
    touch    = the first 1-minute bar that comes within `near` ticks of the VWAP (as it stood when that minute began) uses the arm up,
               filled or not; a working order dies at that minute's close; a NEW close `away` ticks away arms it again
    fill     = the engine's limit law: a ONE-tick trade-through, at the order's price; a touch to the tick is no fill
Synthetic days with EXACT numbers cover each behaviour (a quiet day at 15000, one tick either side, one bar changed at a time); the VWAP
is restated here, independently, from the bars. No net, win rate or profit factor is read.
"""
import pytest

import families
import l2sim as S
from families import blocks as B
from families import vwap_touch as VT
from test_blocks import DAILY, TICK, minute_tape, ns

BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0,
        "anchor": "day", "away": 24, "near": 3, "max_tr": 5}
PX = 15000.0
MS0 = ns("00:00") // 1_000_000


def sec(h, m=0, s=0):
    return h * 3600 + m * 60 + s


def quiet(n, px=PX, v=40):
    return [(px, px + TICK, px - TICK, px, v)] * n


def day(edits=None):
    """A full day of minute bars from 00:00 ET, quiet at 15000, with `edits` ({"HH:MM": (o, h, l, c, v)}) changed."""
    b = quiet(960)
    for t, x in (edits or {}).items():
        b[S._sec(t) // 60] = x
    return b


def hold(frm, to, px, v=40):
    """The edits that keep the minutes frm .. to (both included) quiet at px."""
    return {f"{m // 60:02d}:{m % 60:02d}": (px, px + TICK, px - TICK, px, v) for m in range(S._sec(frm) // 60, S._sec(to) // 60 + 1)}


def vwap(bars, a, b):
    """The VWAP of the minute bars a .. b-1 (minute indexes from 00:00): volume-weighted (h + l + c) / 3, restated."""
    vv = sum(x[4] for x in bars[a:b])
    return sum(x[4] * (x[1] + x[2] + x[3]) / 3.0 for x in bars[a:b]) / vv


def tk(px):
    return round(px / TICK) * TICK


def run(params, bars):
    st = VT.VwapTouch({**BASE, **params})
    st.ROLLS = frozenset()
    res = S.run_session(st, minute_tape(bars, "00:00"), costs=S.Costs(**VT.VwapTouch.SCREEN_RUN), daily=list(DAILY), on_error="raise")
    return st, res


def trades(bars, **params):
    _, res = run(params, bars)
    return [((t["entry_ms"] - MS0) // 1000, t["side"], t["entry_price"]) for t in sorted(res.trades, key=lambda t: t["entry_ms"])]


# the VWAP at the close of minute 09:50 of a day whose only change is the away bar below (590 quiet minutes at typical price 15000)
AWAY_UP = (PX, 15010.0, PX - TICK, 15010.0, 40)        # prints 15000, 14999.75, 15010, 15010: a close 40 ticks above the VWAP
W50 = tk(vwap(day({"09:50": AWAY_UP}), 0, 591))        # = 15000.0 (VWAP 15000.011)


def test_the_family_is_registered_and_wrapped():
    assert "vwap_touch" in families.REGISTRY and families.ERRORS == {}
    assert B.WRAPPED["vwap_touch"].__name__ == "B_vwap_touch"


def test_no_arm_no_order_no_trade_on_a_quiet_day():
    assert trades(day({"09:55": (PX, PX + TICK, PX - 5.0, PX, 40)})) == []               # a dip through the VWAP with no arm: nothing rests


def test_a_close_away_arms_a_limit_at_the_vwap_and_a_one_tick_trade_through_fills_it_there():
    bars = day({"09:50": AWAY_UP, **hold("09:51", "09:54", 15010.0), "09:55": (15010.0, 15010.0, W50 - TICK, 15010.0, 40)})
    assert trades(bars) == [(sec(9, 55, 15), "long", W50)]


def test_a_touch_to_the_tick_is_no_fill_and_uses_the_arm_up():
    # 09:55 trades down to the VWAP itself and closes at 15003 (not away): no fill, the arm is gone; 10:05 trades through it: nothing rests
    bars = day({"09:50": AWAY_UP, **hold("09:51", "09:54", 15010.0), "09:55": (15010.0, 15010.0, W50, 15003.0, 40),
                **hold("09:56", "10:04", 15003.0), "10:05": (15003.0, 15003.0, W50 - TICK, 15003.0, 40)})
    assert trades(bars) == []


def test_a_bar_that_comes_within_near_ticks_uses_the_arm_up_without_reaching_the_order():
    low = W50 + 2 * TICK                                                                  # two ticks above the VWAP
    bars = day({"09:50": AWAY_UP, **hold("09:51", "09:54", 15010.0), "09:55": (15010.0, 15010.0, low, 15003.0, 40),
                **hold("09:56", "10:04", 15003.0), "10:05": (15003.0, 15003.0, W50 - TICK, 15003.0, 40)})
    assert trades(bars, near=3) == []                                                    # within 3 ticks: used up, the later dip has no order
    bars = day({"09:50": AWAY_UP, **hold("09:51", "09:54", 15010.0), "09:55": (15010.0, 15010.0, low, 15010.0, 40),
                "09:56": (15010.0, 15010.0, W50 - TICK, 15010.0, 40)})
    assert trades(bars, near=1) == [(sec(9, 56, 15), "long", W50)]                       # near 1: two ticks away is no touch, the order trades


def test_a_new_close_away_arms_it_again():
    bars = day({"09:50": AWAY_UP, **hold("09:51", "09:54", 15010.0), "09:55": (15010.0, 15010.0, W50, 15003.0, 40),
                **hold("09:56", "09:59", 15003.0), "10:00": (15003.0, 15010.0, 15003.0, 15010.0, 40),
                **hold("10:01", "10:04", 15010.0), "10:05": (15010.0, 15010.0, 14999.0, 15010.0, 40)})
    got = trades(bars)
    assert len(got) == 1 and got[0][:2] == (sec(10, 5, 15), "long") and abs(got[0][2] - PX) < 0.5


def test_a_short_is_the_mirror_a_close_below_arms_a_limit_sell_at_the_vwap():
    away_dn = (PX, PX + TICK, 14990.0, 14990.0, 40)
    w = tk(vwap(day({"09:50": away_dn}), 0, 591))
    bars = day({"09:50": away_dn, **hold("09:51", "09:54", 14990.0), "09:55": (14990.0, w + TICK, 14990.0, 14990.0, 40)})
    assert trades(bars) == [(sec(9, 55, 30), "short", w)]


def test_the_order_is_re_priced_at_every_tf_close():
    # a pump of heavy minutes at 15010 drags the VWAP up; the order must sit at the VWAP of the LAST close, not at the first one's
    pump = {f"09:{m:02d}": (15010.0, 15010.0 + TICK, 15010.0 - TICK, 15010.0, 4000) for m in range(31, 50)}
    bars = day({**pump})
    w49 = tk(vwap(bars, 0, S._sec("09:50") // 60))                                       # the VWAP once 09:49 has ended
    w31 = tk(vwap(bars, 0, S._sec("09:32") // 60))
    assert w49 > w31 + 1.0                                                               # the line really moved
    bars = day({**pump, "09:50": (15010.0, 15010.0, w49 - TICK, 15010.0, 40)})
    got = trades(bars)
    assert got == [(sec(9, 50, 15), "long", w49)]


@pytest.mark.parametrize("anchor,minute", [("us", 570), ("london", 180), ("day", 0)])
def test_the_vwap_runs_from_its_anchor_and_no_earlier(anchor, minute):
    bars = day({"04:00": (PX, 15100.0, PX - TICK, PX, 4000), "09:50": (PX, 15001.0, PX - TICK, 15001.0, 40)})
    st, _ = run({"anchor": anchor}, bars)
    assert st.vwap() == pytest.approx(vwap(bars, minute, st.mi))


def test_the_sessions_are_those_that_end_after_the_anchor_and_never_the_evening():
    st = VT.VwapTouch({**BASE, "anchor": "us", "sess": "all", "hold_to": "session"})
    assert st.sessions() == ["nyam", "mid", "pm"]
    st = VT.VwapTouch({**BASE, "anchor": "day", "sess": "all", "hold_to": "session"})
    assert "eve" not in st.sessions() and "nyam" in st.sessions()
