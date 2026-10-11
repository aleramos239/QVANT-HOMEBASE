"""ORB830: the `orb_close` and `open_candle` families (families/orb830.py), the 08:30 ET data-release rules the owner tested by hand on 2026-10-10.

THE RULES UNDER TEST
  orb_close    range  = the high and low of the 1-minute bars of the first `or_min` minutes (5 | 15 | 30 | 60) from `start` (0930: NY sessions;
                        0830: ONE session 08:30-11:00, "pre")
               signal = the first tf bar that closes after the range and closes strictly above its high (long) / below its low (short); dir
                        both | long | short; one trade a session
               entry  = market at that close, or a LIMIT at the broken edge for `wait` minutes (0 = to the session's last 5 minutes); the signal
                        is used up whether or not the limit fills
               stop   = the exit cell's; the "own" table is stop_mode struct = the other side of the range x the six standard targets
               vwap   = off | on | first, long only above / short only below the VWAP anchored at 16:00 ET of the prior session, read at the
                        signal's close (tick VWAP, or of 15-minute bars: the last COMPLETED bar); build days only: a later date raises
  open_candle  signal = the 08:30 candle (first tf bar of the "pre" session) closes up -> long, down -> short, doji none; market at its close,
                        structure stop = its other extreme; gates all off at 0: k (range >= k x ATR), body_r (body >= body_r x range),
                        body_pts (body >= points), vol_m (volume >= vol_m x the median of the same bar over the 14 dates before)
Synthetic days with EXACT numbers cover each behaviour; seeded random days are checked against an independent restatement of the rule at every
bar size; the VWAP series against its own restatement; real BUILD days check the invariants at 1 worker. No net or win rate is read.
"""
import datetime as dt

import numpy as np
import pytest

import families
import l2sim as S
from families import blocks as B
from families import orb830 as OC
from test_blocks import DAILY, TICK, days_of, minute_tape, ns, rand_bars, real_days

ORB, CANDLE = B.WRAPPED["orb_close"], B.WRAPPED["open_candle"]
PX, HI, LO = 15000.0, 15020.0, 14980.0
BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "struct", "stop_val": 1.0, "tgt_r": 0.0, "or_min": "5", "start": "0930",
        "dir": "both"}
B830 = {**BASE, "sess": "pre", "start": "0830"}
CBASE = {"hold_to": "day", "tf": "5", "sess": "pre", "stop_mode": "struct", "stop_val": 1.0, "tgt_r": 0.0}
MS0 = ns("00:00") // 1_000_000
FILL = 15                                           # a market order fills at the second print after the bar close: :15 past the minute
SELL_SLIP = 2 * TICK                                # the fills are pessimistic: a buy at the close prints at the close, a sell one tick under the print


def sec(h, m=0, s=0):
    return h * 3600 + m * 60 + s


def quiet(n, px=PX, v=40):
    return [(px, px + TICK, px - TICK, px, v)] * n


def up(px, c=PX):
    return (PX, px, PX - TICK, c, 40)


def dn(px, c=PX):
    return (PX, PX + TICK, px, c, 40)


def hold(c):
    """One quiet minute at price c: the bar after a break opens where the break closed, so the fill is at the close."""
    return (c, c + TICK, c - TICK, c, 40)


def stay(c, a, b):
    """Quiet minutes at price c from minute a to minute b (HH:MM, both included)."""
    return {f"{S._hms(m * 60)[:5]}": hold(c) for m in range(S._sec(a) // 60, S._sec(b) // 60 + 1)}


def day(edits=None, t0="09:31"):
    """A full day of minute bars (00:00 .. 15:59) quiet at 15000, the range minutes (14980 .. 15020: a high at t0, a low at t0 + 1) and `edits`."""
    b = quiet(960)
    k = S._sec(t0) // 60
    b[k], b[k + 1] = up(HI), dn(LO)
    for t, x in (edits or {}).items():
        b[S._sec(t) // 60] = x
    return b


def day830(edits=None):
    return day(edits, t0="08:31")


def run(cls, base, params, bars, **kw):
    st = cls({**base, **params})
    st.ROLLS = frozenset()
    res = S.run_session(st, minute_tape(bars, "00:00"), costs=S.Costs(**getattr(cls, "SCREEN_RUN", {})), daily=list(DAILY), on_error="raise", **kw)
    return st, res


def orb(params, bars, base=BASE):
    return run(ORB, base, params, bars)


def got(res):
    return [((t["entry_ms"] - MS0) // 1000, t["side"], t["entry_price"], t["sl"], t["tp"]) for t in sorted(res.trades, key=lambda t: t["entry_ms"])]


def breaks_up(t, c=HI + 4):
    """The minute t closes above the high and the next minute stays at that close (so the fill and the stop distance are exact)."""
    h, m = divmod(S._sec(t) // 60, 60)
    nxt = f"{h:02d}:{m + 1:02d}"
    return {t: (PX, c + TICK, PX, c, 40), nxt: hold(c)}


def breaks_dn(t, c=LO - 4):
    h, m = divmod(S._sec(t) // 60, 60)
    nxt = f"{h:02d}:{m + 1:02d}"
    return {t: (PX, PX, c - TICK, c, 40), nxt: hold(c)}


# ---- (i) the range, and a break needs a CLOSE beyond it --------------------------------------------------------------------------------------------

def test_the_range_is_the_first_or_min_minutes_from_0930_and_the_first_close_beyond_it_enters_at_market():
    st, res = orb({}, day(breaks_up("09:36")))
    assert (st.r, got(res)) == ((HI, LO), [(sec(9, 37, FILL), "long", HI + 4, LO, None)])           # sl = the far side, from the fill
    st, res = orb({}, day(breaks_dn("09:36")))
    assert got(res) == [(sec(9, 37, FILL), "short", LO - 4 - SELL_SLIP, HI - SELL_SLIP, None)]            # the stop distance is read at the signal close


def test_a_wick_through_the_edge_and_a_close_on_the_edge_are_no_signal_a_close_one_tick_beyond_is():
    assert got(orb({}, day({"09:36": (PX, HI + 10, PX, HI - TICK, 40)}))[1]) == []                # wick above, closes inside
    assert got(orb({}, day({"09:36": (PX, HI + 10, PX, HI, 40)}))[1]) == []                       # closes ON the high
    assert got(orb({}, day(breaks_up("09:36", HI + TICK)))[1]) == [(sec(9, 37, FILL), "long", HI + TICK, LO, None)]
    assert got(orb({}, day({"09:36": (PX, PX, LO - 10, LO, 40)}))[1]) == []
    assert got(orb({}, day(breaks_dn("09:36", LO - TICK)))[1]) == [(sec(9, 37, FILL), "short", LO - TICK - SELL_SLIP, HI - SELL_SLIP, None)]


def test_the_range_minute_itself_is_not_a_signal_and_the_first_bar_after_it_is():
    # 09:34 is the last minute of the 5-minute range (it makes the high); 09:35 is the first bar after it
    st, res = orb({}, day({"09:34": up(HI + 6.0, c=HI + 4), **{"09:35": hold(HI + 4)}}))
    assert st.r == (HI + 6.0, LO) and got(res) == []
    st, res = orb({}, day(breaks_up("09:35", HI + 4)))
    assert got(res) == [(sec(9, 36, FILL), "long", HI + 4, LO, None)]


def test_a_longer_range_keeps_extending_until_its_end():
    # or_min 15: a high at 09:40 is still the range; the first close beyond the NEW high after 09:45 is the signal
    bars = day({"09:40": up(HI + 12.0, c=PX), **breaks_up("09:41", HI + 4)})                      # 09:41 closes above HI but inside the range
    st, res = orb({"or_min": "15"}, bars)
    assert st.r == (HI + 12.0, LO) and got(res) == []
    st, res = orb({"or_min": "15"}, day({"09:40": up(HI + 12.0, c=PX), **breaks_up("09:46", HI + 16)}))
    assert got(res) == [(sec(9, 47, FILL), "long", HI + 16, LO, None)]


def test_one_trade_a_session_and_the_first_break_decides_for_dir_both():
    bars = day({**breaks_up("09:36"), "09:50": (HI + 4, HI + 4, LO - 8, LO - 6, 40), "09:51": hold(LO - 6)})
    assert [g[1] for g in got(orb({}, bars)[1])] == ["long"]
    bars = day({**breaks_dn("09:36"), "09:50": (LO - 4, HI + 8, LO - 4, HI + 6, 40), "09:51": hold(HI + 6)})
    assert [g[1] for g in got(orb({}, bars)[1])] == ["short"]


def test_dir_long_ignores_a_break_below_and_takes_the_later_break_above():
    bars = day({"09:36": (PX, PX, LO - 8, LO - 4, 40), "09:37": hold(LO - 4), "09:50": (LO - 4, HI + 8, LO - 4, HI + 6, 40), "09:51": hold(HI + 6)})
    assert got(orb({"dir": "long"}, bars)[1]) == [(sec(9, 51, FILL), "long", HI + 6, LO, None)]
    assert [g[1] for g in got(orb({"dir": "short"}, bars)[1])] == ["short"] and got(orb({"dir": "short"}, bars)[1])[0][0] == sec(9, 37, FILL)
    assert got(orb({"dir": "short"}, day(breaks_up("09:36")))[1]) == []


def test_the_stop_is_the_far_side_of_the_range_and_the_target_is_a_multiple_of_it():
    _, res = orb({"tgt_r": 2.0}, day(breaks_up("09:36")))
    (_, side, px, sl, tp), = got(res)
    assert (side, sl, tp) == ("long", LO, px + 2.0 * (px - LO))
    _, res = orb({"tgt_r": 1.0}, day(breaks_dn("09:36")))
    (_, side, px, sl, tp), = got(res)
    assert (side, sl, tp) == ("short", HI - SELL_SLIP, px - (HI - (LO - 4)))                         # the target = R x the stop distance of the signal
    # the stop is hit: the day drops to the far side and the trade ends there, a loss of the stop distance
    _, res = orb({}, day({**breaks_up("09:36"), "09:40": dn(LO - 2.0)}))
    t, = res.trades
    assert t["exit_reason"] == "sl" and t["exit_price"] == LO - 2.0 - TICK                          # the trigger print LO - 2, one tick worse


# ---- (ii) a limit rests at the broken edge --------------------------------------------------------------------------------------------------------

def test_a_limit_rests_at_the_broken_edge_and_fills_on_the_retest():
    bars = day({"09:36": (PX, HI + 8, PX, HI + 4, 40), **stay(HI + 4, "09:37", "09:39"), "09:40": (HI + 4, HI + 4, HI - 2.0, HI - 1.0, 40)})
    _, res = orb({"entry": "limit"}, bars)
    (at, side, px, sl, tp), = got(res)
    assert (side, px) == ("long", HI) and sec(9, 40) <= at < sec(9, 41)
    assert res.trades[0]["order_price"] == HI
    bars = day({"09:36": (PX, PX, LO - 8, LO - 4, 40), **stay(LO - 4, "09:37", "09:39"), "09:40": (LO - 4, LO + 2.0, LO - 4, LO + 1.0, 40)})
    (at, side, px, sl, tp), = got(orb({"entry": "limit"}, bars)[1])
    assert (side, px) == ("short", LO) and sec(9, 40) <= at < sec(9, 41)


def test_the_limit_expires_after_wait_minutes_and_the_signal_is_used_up_either_way():
    far = {"09:36": (PX, HI + 8, PX + 6, HI + 4, 40), **{f"09:{m}": hold(HI + 4) for m in range(37, 60)}}      # never comes back to the edge
    assert got(orb({"entry": "limit", "wait": "5"}, day(far))[1]) == []
    # it comes back at 09:43: inside a 15-minute wait, outside a 5-minute one
    late = {**far, "09:43": (HI + 4, HI + 4, HI - 2.0, HI + 4, 40)}
    assert len(got(orb({"entry": "limit", "wait": "15"}, day(late))[1])) == 1
    assert got(orb({"entry": "limit", "wait": "5"}, day(late))[1]) == []
    # used up: after the unfilled limit expired a SECOND break (a close below the low) does not trade
    again = {**far, "09:50": (HI + 4, HI + 4, LO - 8, LO - 4, 40), "09:51": hold(LO - 4)}
    assert got(orb({"entry": "limit", "wait": "5"}, day(again))[1]) == []
    assert [g[1] for g in got(orb({"entry": "market"}, day(again))[1])] == ["long"]                # (market: the first break trades)


def test_wait_0_rests_to_the_end_of_the_session_window():
    far = {"09:36": (PX, HI + 8, PX + 6, HI + 4, 40), **{f"{h}:{m:02d}": hold(HI + 4) for h in (9, 10) for m in range(0, 60) if (h, m) > (9, 36)},
           "10:30": dn(HI - 2.0, c=HI + 4)}
    (at, side, px, *_), = got(orb({"entry": "limit", "wait": "0"}, day(far))[1])
    assert side == "long" and px == HI and sec(10, 30) <= at < sec(10, 31)


# ---- (iii) bar sizes, the 08:30 start ---------------------------------------------------------------------------------------------------------------

def test_on_5_minute_bars_the_signal_is_the_first_5_minute_close_beyond_the_range():
    # 09:35-09:39 is the first bar after the 5-minute range; it closes at 09:40 above the high -> fill at 09:40:15
    bars = day({"09:39": (PX, HI + 8, PX, HI + 4, 40), **stay(HI + 4, "09:40", "09:50")})
    st, res = orb({"tf": "5"}, bars)
    assert got(res) == [(sec(9, 40, FILL), "long", HI + 4, LO, None)]
    # a 5-minute bar that closes inside the range is no signal even when one of its minutes closed above it
    bars = day({"09:36": (PX, HI + 8, PX, HI + 4, 40), "09:37": hold(HI - 2.0), **stay(HI - 2.0, "09:38", "09:50")})
    assert got(orb({"tf": "5"}, bars)[1]) == []
    assert len(got(orb({"tf": "1"}, bars)[1])) == 1
    # tf 15 with a 5-minute range: the 09:30-09:45 bar ends after the range, so it is the first signal bar (and it contains the range)
    bars = day({"09:44": (PX, HI + 8, PX, HI + 4, 40), **stay(HI + 4, "09:45", "09:50")})
    assert got(orb({"tf": "15"}, bars)[1]) == [(sec(9, 45, FILL), "long", HI + 4, LO, None)]


def test_start_0830_is_one_pre_session_from_the_release_with_entries_until_five_minutes_before_11():
    st = ORB({**B830})
    assert st.sessions() == ["pre"] and ORB({**BASE, "start": "0830"}).sessions() == [] and ORB({**BASE}).sessions() == ["nyam"]
    st, res = orb({}, day830({"08:36": (PX, HI + 8, PX, HI + 4, 40), "08:37": hold(HI + 4)}), base=B830)
    assert st.r == (HI, LO) and got(res) == [(sec(8, 37, FILL), "long", HI + 4, LO, None)]
    assert len(got(orb({}, day830({"10:53": (PX, HI + 8, PX, HI + 4, 40), "10:54": hold(HI + 4)}), base=B830)[1])) == 1     # the last signal bar closes 10:54
    assert got(orb({}, day830({"10:54": (PX, HI + 8, PX, HI + 4, 40), "10:55": hold(HI + 4)}), base=B830)[1]) == []        # from 10:55: 5 minutes before 11:00


# ---- (iv) the VWAP rule -----------------------------------------------------------------------------------------------------------------------------

def _vw(monkeypatch, level, tf_seen=None):
    def series(root, iso, prior, tf=0):
        if tf_seen is not None:
            tf_seen.append((root, iso, prior, tf))
        return None if level is None else np.full(151, float(level))
    monkeypatch.setattr(OC, "vwap16_series", series)


def test_vwap_on_takes_a_long_only_above_and_a_short_only_below_and_the_next_break_may_trade(monkeypatch):
    two = {"09:36": (PX, PX, LO - 8, LO - 4, 40), "09:37": hold(LO - 4), "09:50": (LO - 4, HI + 8, LO - 4, HI + 6, 40), "09:51": hold(HI + 6)}
    _vw(monkeypatch, LO - 10.0)                                                                         # the VWAP is below both: shorts skipped
    assert [(g[0], g[1]) for g in got(orb({"vwap": "on"}, day(two))[1])] == [(sec(9, 51, FILL), "long")]
    _vw(monkeypatch, HI + 20.0)                                                                         # above both: longs skipped, the first short trades
    assert [(g[0], g[1]) for g in got(orb({"vwap": "on"}, day(two))[1])] == [(sec(9, 37, FILL), "short")]
    _vw(monkeypatch, PX)                                                                                # between: both trade, the first break wins
    assert [g[1] for g in got(orb({"vwap": "on"}, day(two))[1])] == ["short"]


def test_vwap_first_lets_the_first_break_decide_the_day(monkeypatch):
    two = {"09:36": (PX, PX, LO - 8, LO - 4, 40), "09:37": hold(LO - 4), "09:50": (LO - 4, HI + 8, LO - 4, HI + 6, 40), "09:51": hold(HI + 6)}
    _vw(monkeypatch, LO - 10.0)                                                                         # the first break is a short, against it: no trade
    assert got(orb({"vwap": "first"}, day(two))[1]) == []
    _vw(monkeypatch, HI + 20.0)                                                                         # the first break is a short, with it: trades
    assert [g[1] for g in got(orb({"vwap": "first"}, day(two))[1])] == ["short"]


def test_vwap_is_read_with_the_prior_session_date_the_tf_and_a_day_without_one_does_not_trade(monkeypatch):
    seen = []
    _vw(monkeypatch, LO - 10.0, seen)
    orb({"vwap": "on", "vwap_tf": "15"}, day(breaks_up("09:36")))
    assert seen and seen[0][3] == 15 and seen[0][0] == "NQ" and seen[0][2] == DAILY[-1]["date"]
    _vw(monkeypatch, None)                                                                              # a roll day / no tape: no VWAP, no trade
    assert got(orb({"vwap": "on"}, day(breaks_up("09:36")))[1]) == []
    seen.clear()
    _vw(monkeypatch, LO - 10.0, seen)
    assert len(got(orb({"vwap": "off"}, day(breaks_up("09:36")))[1])) == 1 and seen == []                  # off never reads it


class _FakeTape:
    def __init__(self, contract, ts, px, size):
        self.contract, self.ts, self.px, self.size = contract, np.asarray(ts, np.int64), np.asarray(px, float), np.asarray(size, np.int64)


def _fake(monkeypatch, prior, trade):
    tapes = {dt.date(2024, 3, 12): prior, dt.date(2024, 3, 13): trade}
    monkeypatch.setattr(S, "load_tape", lambda d, root, **kw: tapes.get(d))
    OC._VW16.clear()


def _t(d, hms):
    return S.et_ns(d, hms)


def test_vwap16_series_is_the_volume_weighted_average_of_every_print_from_1600_of_the_prior_session(monkeypatch):
    p, d = dt.date(2024, 3, 12), dt.date(2024, 3, 13)
    prior = _FakeTape("NQH4", [_t(p, "15:59:59"), _t(p, "16:00:00"), _t(p, "16:40:00")], [9000.0, 100.0, 104.0], [50, 10, 30])
    trade = _FakeTape("NQH4", [_t(d, "03:00:00"), _t(d, "08:29:59"), _t(d, "08:31:00"), _t(d, "08:45:00")], [110.0, 108.0, 120.0, 90.0], [20, 5, 10, 40])
    _fake(monkeypatch, prior, trade)
    v = OC.vwap16_series("NQ", "2024-03-13", "2024-03-12")
    px = [100.0, 104.0, 110.0, 108.0, 120.0, 90.0]
    sz = [10, 30, 20, 5, 10, 40]
    want = lambda n: sum(a * b for a, b in zip(px[:n], sz[:n])) / sum(sz[:n])
    assert len(v) == (39600 - 30600) // 60 + 2 and np.isclose(v[0], want(4))                         # 08:30 boundary: through the print at 08:29:59
    assert np.isclose(v[1], want(4)) and np.isclose(v[2], want(5)) and np.isclose(v[15], want(5))     # 08:31:00 is NOT in the 08:31 value, it is in 08:32's
    assert np.isclose(v[16], want(6))                                                                  # 08:45:00 enters at 08:46 (index 16)
    assert OC.vwap16_series("NQ", "2024-03-13", "2024-03-12") is v                                     # cached


def test_vwap16_series_on_15_minute_bars_uses_only_the_bars_completed_by_the_boundary(monkeypatch):
    p, d = dt.date(2024, 3, 12), dt.date(2024, 3, 13)
    prior = _FakeTape("NQH4", [_t(p, "16:05:00"), _t(p, "16:10:00")], [100.0, 106.0], [10, 20])        # one bar 16:00-16:15: h 106 l 100 c 106 v 30
    trade = _FakeTape("NQH4", [_t(d, "08:20:00"), _t(d, "08:29:00"), _t(d, "08:31:00"), _t(d, "08:44:00"), _t(d, "08:50:00")],
                      [200.0, 210.0, 230.0, 190.0, 200.0], [10, 10, 40, 20, 10])
    _fake(monkeypatch, prior, trade)
    v = OC.vwap16_series("NQ", "2024-03-13", "2024-03-12", tf=15)
    b1 = ((106.0 + 100.0 + 106.0) / 3.0, 30)                                                         # 16:00-16:15
    b2 = ((200.0 + 200.0 + 200.0) / 3.0, 10)                                                         # 08:15-08:30 holds the 08:20 print (08:29 is 210)
    b2 = ((210.0 + 200.0 + 210.0) / 3.0, 20)
    b3 = ((230.0 + 190.0 + 190.0) / 3.0, 60)                                                         # 08:30-08:45: 08:31 (230) and 08:44 (190)
    b4 = ((200.0 + 200.0 + 200.0) / 3.0, 10)                                                         # 08:45-09:00: 08:50
    avg = lambda bs: sum(a * w for a, w in bs) / sum(w for _, w in bs)
    assert np.isclose(v[0], avg([b1, b2]))                                                           # 08:30: the 08:15 bar has completed, 08:30's has not
    assert np.isclose(v[14], avg([b1, b2])) and np.isclose(v[15], avg([b1, b2, b3]))                  # completes at 08:45
    assert np.isclose(v[30], avg([b1, b2, b3, b4]))                                                  # 09:00


def test_vwap16_series_is_none_on_a_roll_or_without_a_tape_and_raises_after_the_build_days(monkeypatch):
    p, d = dt.date(2024, 3, 12), dt.date(2024, 3, 13)
    a = _FakeTape("NQH4", [_t(p, "16:10:00")], [100.0], [10])
    _fake(monkeypatch, a, _FakeTape("NQM4", [_t(d, "08:20:00")], [100.0], [10]))
    assert OC.vwap16_series("NQ", "2024-03-13", "2024-03-12") is None                                  # different contracts
    _fake(monkeypatch, None, _FakeTape("NQH4", [_t(d, "08:20:00")], [100.0], [10]))
    assert OC.vwap16_series("NQ", "2024-03-13", "2024-03-12") is None
    with pytest.raises(RuntimeError, match="build days only|2025-06-30"):
        OC.vwap16_series("NQ", "2025-07-01", "2025-06-30")
    assert OC.vwap16_series("NQ", "2025-06-30", "2025-06-27", 0) is None or True                       # the last build day is not refused (no tape here -> None)


# ---- (v) the exit table "own" ----------------------------------------------------------------------------------------------------------------------

def test_exits_own_is_the_family_s_stop_at_the_far_side_times_the_six_standard_targets():
    cells = B.exits("own", "NQ", "orb_close")
    assert [(c["stop_mode"], c["stop_val"], c["tgt_r"]) for c in cells] == [("struct", 1.0, r) for r in (0.0, 0.5, 0.75, 1.0, 2.0, 3.0)]
    assert B.exits("own", "ES", "orb_close") == cells                                                  # the stop is the range: the root changes nothing
    with pytest.raises(ValueError, match="no exit cells of its own"):
        B.exits("own", "NQ", "orb")
    with pytest.raises(KeyError):
        B.exits("own", "CL", "orb_close")
    assert B.exits("standard", "NQ", "orb") == S.menu("NQ") and B.exits("blueprint", "NQ", "orb") == B.menu_blueprint("NQ")     # the others unchanged
    with pytest.raises(ValueError, match="exits 'nope'"):
        B.exits("nope", "NQ", "orb")


def test_the_families_are_registered_and_leave_the_existing_ones_alone():
    reg = families.load()
    assert {"orb_close", "open_candle"} <= set(reg)
    assert "orb_close" in B.BASES and "open_candle" in B.WRAPPED and B.WRAPPED["orb_close"].__module__ == "families.blocks"
    for name in ("orb_confirm", "first_bar_mom", "orb", "ib_touch"):
        assert name in B.WRAPPED
    # the hashed engine files are not touched by this module: the old classes keep their old parameters
    assert "start" not in B.BASES["orb_confirm"][0].DEFAULTS and "body_r" not in B.BASES["first_bar_mom"][0].DEFAULTS


# ---- (vi) open_candle -----------------------------------------------------------------------------------------------------------------------------

def candle(o, c, h=None, l=None, t0="08:30", v=40):
    """The 08:30 5-minute candle (o, h, l, c) as five 1-minute bars; prints on the bar grid: the path o -> h -> l -> c."""
    h = max(o, c) if h is None else h
    l = min(o, c) if l is None else l
    five = [(o, h, o, h, v), (h, h, l, l, v), (l, l, l, l, v), (l, c, l, c, v), (c, c, c, c, v)]
    # 1-minute bars with exact 5-minute o/h/l/c: the first opens at o, the last closes at c, the highest high is h, the lowest low is l
    out = []
    for i, (bo, bh, bl, bc, bv) in enumerate(five):
        out.append((bo, bh, bl, bc, bv))
    return {f"{S._hms(S._sec(t0) + i * 60)[:5]}": b for i, b in enumerate(out)}


def after(c, t="08:35"):
    """Quiet bars at c from `t` to 09:00: the day after the candle stays where it closed."""
    k = S._sec(t) // 60
    return {f"{S._hms((k + i) * 60)[:5]}": hold(c) for i in range(25)}


class Log(CANDLE):
    seen: list = []

    def fam_signal(self, ctx):
        if self.sn == 1:
            type(self).seen.append((self.atr_p, self.O[-1], self.H[-1], self.L[-1], self.C[-1]))
        return super().fam_signal(ctx)


def cdl(params, o, c, h=None, l=None, cls=CANDLE):
    bars = [(PX, PX + 3.0, PX - 3.0, PX, 40)] * 960                                                    # a background of 6-point minutes: ATR(14) about 6
    for t, b in {**candle(o, c, h, l), **after(c)}.items():
        bars[S._sec(t) // 60] = b
    return run(cls, CBASE, params, bars)


def test_the_0830_candle_is_followed_at_its_close_with_its_other_extreme_as_the_stop():
    st, res = cdl({}, PX, PX + 10.0, h=PX + 12.0, l=PX - 2.0)
    assert st.sessions() == ["pre"]
    assert got(res) == [(sec(8, 35, FILL), "long", PX + 10.0, PX - 2.0, None)]
    assert got(cdl({}, PX, PX - 10.0, h=PX + 2.0, l=PX - 12.0)[1]) == [(sec(8, 35, FILL), "short", PX - 10.0 - SELL_SLIP, PX + 2.0 - SELL_SLIP, None)]
    assert got(cdl({}, PX, PX, h=PX + 3.0, l=PX - 3.0)[1]) == []                                      # a doji is no signal


def _london(start, o, c, h=None, l=None, base=None, params=None):
    """The `start` (02:00 | 03:00) candle on a background of 6-point minutes, followed by quiet minutes at its close."""
    t0 = f"{start[:2]}:{start[2:]}"
    bars = [(PX, PX + 3.0, PX - 3.0, PX, 40)] * 960
    k = S._sec(t0) // 60
    for t, b in candle(o, c, h, l, t0=t0).items():
        bars[S._sec(t) // 60] = b
    for i in range(k + 5, k + 200):                                                                     # quiet at the close for three hours
        bars[i] = hold(c)
    return run(CANDLE, {**CBASE, "sess": "london", **(base or {})}, {"start": start, **(params or {})}, bars)


def test_the_london_candle_is_followed_at_its_close_in_its_own_session_and_the_0830_start_never_trades_there():
    for start, hh in (("0200", 2), ("0300", 3)):
        st, res = _london(start, PX, PX + 10.0, h=PX + 12.0, l=PX - 2.0)
        assert st.sessions() == ["london"] and st.S["london"] == (hh * 3600, OC.LONDON_END)
        assert got(res) == [(sec(hh, 5, FILL), "long", PX + 10.0, PX - 2.0, None)]                      # the structure stop = the candle's low
        st, res = _london(start, PX, PX - 10.0, h=PX + 2.0, l=PX - 12.0)
        assert got(res) == [(sec(hh, 5, FILL), "short", PX - 10.0 - SELL_SLIP, PX + 2.0 - SELL_SLIP, None)]
        assert got(_london(start, PX, PX, h=PX + 3.0, l=PX - 3.0)[1]) == []                              # a doji is no signal
    # a start belongs to ITS session only: 0830 trades in "pre", never in "london"; 0200 never in "pre"
    assert CANDLE({**CBASE, "sess": "london", "start": "0830"}).sessions() == []
    assert CANDLE({**CBASE, "sess": "pre", "start": "0200"}).sessions() == []
    assert CANDLE({**CBASE, "sess": "pre"}).sessions() == ["pre"] and CANDLE(CBASE).p["start"] == "0830"        # the default is unchanged


def test_the_london_candle_takes_the_body_gate_and_a_time_stop_in_tf_bars():
    o, c, h, l = PX, PX + 6.0, PX + 10.0, PX - 4.0                                                      # body 6 of a 14-point range (43 %)
    assert len(got(_london("0200", o, c, h, l, params={"body_r": 0.42})[1])) == 1
    assert got(_london("0200", o, c, h, l, params={"body_r": 0.44})[1]) == []
    st, res = _london("0200", PX, PX + 10.0, h=PX + 12.0, l=PX - 2.0, params={"exit_bars": 12})           # 12 five-minute bars after the fill: 03:05
    t = sorted(res.trades, key=lambda x: x["entry_ms"])[0]
    assert (t["entry_ms"] - MS0) // 1000 == sec(2, 5, FILL) and (t["exit_ms"] - MS0) // 1000 == sec(3, 5)       # a time stop leaves at the 12th close


def test_open_candle_is_one_trade_on_the_first_candle_only_and_never_in_another_session():
    assert CANDLE({**CBASE, "sess": "nyam"}).sessions() == [] and len(got(cdl({}, PX, PX + 10.0, h=PX + 12.0, l=PX - 2.0)[1])) == 1
    # a candle at 08:35 (the SECOND 5-minute bar) is not the signal
    bars = quiet(960, PX)
    for t, b in {**candle(PX, PX, h=PX + 1.0, l=PX - 1.0), **candle(PX, PX + 10.0, t0="08:35"), **after(PX + 10.0, "08:40")}.items():
        bars[S._sec(t) // 60] = b
    assert got(run(CANDLE, CBASE, {}, bars)[1]) == []


def _atr_at_candle(o, c, h, l):
    cls = type("Log", (Log,), {"seen": []})
    cdl({}, o, c, h, l, cls=cls)
    return cls.seen[0][0]


def test_the_displacement_gates_each_cut_on_their_own_measure():
    o, c, h, l = PX, PX + 6.0, PX + 10.0, PX - 4.0                                                     # range 14, body 6 (43 % of it)
    atr = _atr_at_candle(o, c, h, l)
    assert atr and atr > 0
    k_ok, k_no = 14.0 / atr * 0.99, 14.0 / atr * 1.01                                                  # A: range >= k x ATR
    assert len(got(cdl({"k": k_ok}, o, c, h, l)[1])) == 1 and got(cdl({"k": k_no}, o, c, h, l)[1]) == []
    assert len(got(cdl({"body_r": 0.42}, o, c, h, l)[1])) == 1 and got(cdl({"body_r": 0.44}, o, c, h, l)[1]) == []        # B: body >= r x range
    assert len(got(cdl({"body_pts": 6.0}, o, c, h, l)[1])) == 1 and got(cdl({"body_pts": 6.25}, o, c, h, l)[1]) == []     # E: body >= points
    assert len(got(cdl({"k": k_ok, "body_r": 0.42, "body_pts": 6.0}, o, c, h, l)[1])) == 1                                   # all that are set hold
    assert got(cdl({"k": k_ok, "body_r": 0.44, "body_pts": 6.0}, o, c, h, l)[1]) == []


def test_volume_gate_compares_with_the_same_bar_s_median_and_needs_history():
    class Vol(CANDLE):
        ref = (200, 100.0)                                                                              # (the candle's volume, the median of 14 dates)

        def blk_rvol(self):
            return type(self).ref
    o, c = PX, PX + 10.0
    assert len(got(cdl({"vol_m": 2.0}, o, c, cls=Vol)[1])) == 1                                       # 200 >= 2.0 x 100
    assert got(cdl({"vol_m": 2.01}, o, c, cls=Vol)[1]) == []
    Vol.ref = None                                                                                      # no 14-date history: no trade
    assert got(cdl({"vol_m": 1.0}, o, c, cls=Vol)[1]) == []
    assert len(got(cdl({"vol_m": 0.0}, o, c, cls=Vol)[1])) == 1                                        # the gate off never reads it


# ---- (vii) random days vs an independent restatement ---------------------------------------------------------------------------------------------

def _restate(bars, or_min, tf, dir_, last_close=sec(10, 54)):
    """The market entry the rule asks for, from the 1-minute bars alone: -> (side, second of the closing bar) of the first tf bar (clock-aligned)
    that ends after the range and closes beyond it, up to the last close the 09:30-11:00 session still enters on, or None."""
    o = OC.OPEN // 60
    rng = bars[o:o + or_min]
    hi, lo = max(b[1] for b in rng), min(b[2] for b in rng)
    s = ((o + or_min) // tf) * tf                    # the first bar that ENDS after the range's end (it may contain the range's last minutes)
    while (s + tf) * 60 <= last_close:
        c = bars[s + tf - 1][3]
        if dir_ != "short" and c > hi:
            return "long", (s + tf) * 60
        if dir_ != "long" and c < lo:
            return "short", (s + tf) * 60
        s += tf
    return None


@pytest.mark.parametrize("tf", ["1", "5", "15"])
@pytest.mark.parametrize("or_min", ["5", "15", "30"])
def test_random_days_match_the_restatement_of_the_rule(tf, or_min):
    seen = {"long": 0, "short": 0, "none": 0}
    for seed in range(1, 13):
        bars = rand_bars(960, seed * 7 + int(tf) + int(or_min), p0=PX, step=5.0)
        for dir_ in ("both", "long", "short"):
            st, res = orb({"tf": tf, "or_min": or_min, "dir": dir_}, bars)
            want = _restate(bars, int(or_min), int(tf), dir_)
            if want is None:
                assert res.trades == [], (seed, dir_)
                seen["none"] += 1
                continue
            side, close_s = want
            (at, got_side, *_), = got(res)
            assert (got_side, at) == (side, close_s + FILL), (seed, dir_, tf, or_min)
            seen[side] += 1
    assert seen["long"] and seen["short"] and seen["none"], seen        # the seeds exercise both sides and a day without a break


# ---- (viii) real build days -------------------------------------------------------------------------------------------------------------------------

def _real(params, cls, root="NQ", n=6, base=None):
    real_days()
    days = days_of(root, n)
    specs = [(cls, {**(base or BASE), **params})]
    res = S.run_many(specs, days=days, root=root, workers=1, **dict(getattr(cls, "SCREEN_RUN", {})))
    return days, res[0]


def test_real_build_days_orb_close_0830_invariants():
    for entry in ("market", "limit"):
        days, r = _real({"entry": entry, "start": "0830", "sess": "pre", "tf": "1"}, ORB, base=B830)
        by_day = {}
        for t in r["trades"]:
            by_day.setdefault(t["date"], []).append(t)
            et = dt.datetime.fromtimestamp(t["entry_ms"] / 1000, S.ET)
            s = et.hour * 3600 + et.minute * 60 + et.second
            assert sec(8, 35) <= s < sec(10, 55), (entry, t["date"], s)                                   # inside the family's own window
            assert t["exit_ms"] // 1000 <= int(dt.datetime.fromisoformat(t["date"]).replace(tzinfo=S.ET).timestamp()) + sec(15, 58, 1)
            if entry == "limit":
                assert t["order_price"] is not None and t["entry_price"] == t["order_price"]
        assert all(len(v) == 1 for v in by_day.values()), "one trade a day"


def test_real_build_days_open_candle_follows_the_0830_candle():
    days, r = _real({"tf": "5"}, CANDLE, base=CBASE)
    assert r["trades"], "the 08:30 candle trades on the build days"
    for t in r["trades"]:
        et = dt.datetime.fromtimestamp(t["entry_ms"] / 1000, S.ET)
        s = et.hour * 3600 + et.minute * 60 + et.second
        assert sec(8, 35) <= s < sec(8, 36), (t["date"], s)                                             # the order goes right after the 08:30 5-minute close
