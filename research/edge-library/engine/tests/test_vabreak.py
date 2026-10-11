"""VA_BREAK: the `va_break` entry (families/vabreak.py), written test-first from the video's rule (Gianluca Bruni, IQCapital, nlLGlVJGrtw).

THE RULE UNDER TEST (New York time, 15-minute bars unless a test says 5):
    value area  = yesterday's 70 % value area (VAL, VAH) of 09:30-16:00 (here set by hand: `value_area` is monkeypatched)
    BREAK       = a bar closes >= VAH + buf_pts (6) while the bar before it closed under that; it ENGULFS (close above the previous bar's high)
                  and shows LOW EFFORT (volume under its EMA(20) or under the previous bar's); on a trend day (developing value area's middle
                  above yesterday's)
    STRUCTURE   = the RTH high so far is the structure high; the nearest valid down candle at or before its bar holds the structure low; a
                  bar under it kills the setup
    EXITS       = market at the close, stop at the trigger candle's low, target tgt_r x the stop cut to the structure high
    CONTINUATION= after the break trade, later engulfing low-effort bars enter until a bar's high reaches the structure high
Synthetic days with EXACT numbers cover each behaviour; seeded random days restate the rule; real BUILD days check the invariants.
No net, win rate or profit factor is read.
"""
import datetime as dt

import numpy as np
import pytest

import families
import l2sim as S
from families import blocks as B
from families import vabreak as VB
from test_blocks import D, days_of, minute_tape, ns, rand_bars, real_days

TICK = 0.25
P0 = 14980.0
VAL, VAH = 14950.0, 15000.0
BASE = {"hold_to": "day", "tf": "15", "sess": "nyam", "stop_mode": "struct", "tgt_r": 2.0, "dir": "long", "trend": "on"}


def sec(h, m=0):
    return h * 3600 + m * 60


def rows(n=40):
    return [{"date": (D - dt.timedelta(days=n - i)).isoformat(), "h": 15000.0 + 100, "l": 15000.0, "c": 15050.0, "contract": "NQM3"}
            for i in range(n)]


DAILY = rows()


def rnd(x):
    return round(x / TICK) * TICK


def bucket(o, h, l, c, vol, n=15):
    """n minute bars that make ONE tf bar (o, h, l, c) with `vol` in total (a multiple of 4 n): the path o -> (l, h) -> c in thirds."""
    p1, p2 = (l, h) if c >= o else (h, l)
    pts = [o, p1, p2, c]
    path = [rnd(np.interp(i, [0, n / 3, 2 * n / 3, n], pts)) for i in range(n + 1)]
    path[0], path[n] = o, c
    v = vol // n
    return [(path[i], max(path[i], path[i + 1]), min(path[i], path[i + 1]), path[i + 1], v) for i in range(n)]


def day(buckets, tail=P0):
    """00:00 .. 15:59: quiet at P0 (40 a minute) until 09:30, then the 15-minute buckets (o, h, l, c, vol) from 09:30, then quiet at their last close."""
    out = [(P0, P0, P0, P0, 40)] * (9 * 60 + 30)
    last = P0
    for o, h, l, c, v in buckets:
        out += bucket(o, h, l, c, v)
        last = c
    return out + [(last, last, last, last, 40)] * (960 - len(out))


def run(params, bars, va=(VAL, VAH), daily=None, cls=None, monkeypatch=None):
    st = (cls or VB.VaBreak)({**BASE, **params})
    st.ROLLS = frozenset()
    S_ = S.run_session(st, minute_tape(bars, "00:00", D), daily=daily or DAILY, on_error="raise")
    return st, S_


@pytest.fixture(autouse=True)
def yesterday(monkeypatch):
    monkeypatch.setattr(VB, "value_area", lambda root, iso: YEST["va"])
    YEST["va"] = (VAL, VAH)


YEST = {"va": (VAL, VAH)}


def decisions(params, bars, va=None):
    log = []

    class Spy(VB.VaBreak):
        def _mkt(self, ctx, side, **kw):
            o = super()._mkt(ctx, side, **kw)
            log.append(((ctx.now_ns - ns("00:00")) // S.NS, side, o is not None))
            return o

    if va is not None:
        YEST["va"] = va
    run(params, bars, cls=Spy)
    return log


# ---- the scenario: the happy path, every number worked by hand --------------------------------------------------------------------------------
#   b0 09:30 a VALID down candle (body 13 > wicks 1 and 2), low 14980 = the structure low
#   b1 09:45 up to 15012 (the structure high), closes 15004: under VAH + 6 = 15006
#   b2 10:00 a pullback, high 15005, close 14992
#   b3 10:15 THE BREAK: close 15008 >= 15006, above b2's high 15005, volume 300 under b2's 900; low 14991 = the stop (17 points)
B0 = (14995.0, 14996.0, 14980.0, 14982.0, 900)
B1 = (14982.0, 15012.0, 14981.0, 15004.0, 900)
B2 = (15004.0, 15005.0, 14990.0, 14992.0, 900)
B3 = (14992.0, 15010.0, 14991.0, 15008.0, 300)


def test_a_close_through_vah_plus_6_that_engulfs_on_low_effort_buys_and_the_target_is_cut_to_the_structure_high():
    got = decisions({}, day([B0, B1, B2, B3]))
    assert got == [(sec(10, 30), "long", True)]
    st, res = run({}, day([B0, B1, B2, B3]))
    t = res.trades[0]
    assert t["entry_price"] - t["sl"] == pytest.approx(17.0)                         # 15008 - 14991: the trigger candle's low
    assert t["tp"] - t["entry_price"] == pytest.approx(4.0)                          # 2R = 34 would be 15042; the structure high 15012 is nearer
    assert st.took[1] is True and st.cont[1] == 15012.0


def test_the_target_stays_2r_when_the_structure_high_is_further_and_a_high_under_the_entry_cuts_nothing():
    far = (14982.0, 15040.0, 14981.0, 15004.0, 900)                                   # structure high 15040
    b3 = (15000.0, 15010.0, 15000.0, 15008.0, 300)                                    # stop 8 -> 2R = 16 -> 15024, under 15040
    st, res = run({}, day([B0, far, B2, b3]))
    t = res.trades[0]
    assert t["entry_price"] - t["sl"] == pytest.approx(8.0) and t["tp"] - t["entry_price"] == pytest.approx(16.0)
    low = (14982.0, 15004.0, 14981.0, 15004.0, 900)                                   # the high before the trigger is 15004: under the entry
    b2 = (15004.0, 15004.0, 14990.0, 14992.0, 900)
    st, res = run({}, day([B0, low, b2, B3]))
    t = res.trades[0]
    assert t["tp"] - t["entry_price"] == pytest.approx(34.0)                          # no structure high above the entry: plain 2R


# ---- the break ---------------------------------------------------------------------------------------------------------------------------------

def test_the_close_must_be_at_least_6_points_over_vah_and_the_bar_before_must_be_under_that():
    under = (14992.0, 15010.0, 14991.0, 15005.75, 300)                                # 15005.75 < 15006
    assert decisions({}, day([B0, B1, B2, under])) == []
    on = (14992.0, 15010.0, 14991.0, 15006.0, 300)
    assert decisions({}, day([B0, B1, B2, on])) == [(sec(10, 30), "long", True)]
    already = (15004.0, 15012.0, 14990.0, 15007.0, 900)                               # b2 itself closes beyond 15006: THAT bar breaks, not b3
    b3 = (15007.0, 15015.0, 15007.0, 15012.0, 300)                                    # higher close, engulfs, low effort: not a break (no break trade yet)
    assert decisions({}, day([B0, B1, already, b3])) == []


def test_the_bar_must_close_above_the_previous_bars_high():
    no_engulf = (14992.0, 15010.0, 14991.0, 15008.0, 300)
    b2 = (15004.0, 15009.0, 14990.0, 14992.0, 900)                                    # high 15009 > the trigger's close 15008
    assert decisions({}, day([B0, B1, b2, no_engulf])) == []
    b2 = (15004.0, 15008.0, 14990.0, 14992.0, 900)                                    # high 15008 == close: not above
    assert decisions({}, day([B0, B1, b2, no_engulf])) == []


def ema_at(vols):
    e = None
    for v in vols:
        e = v if e is None else e + (v - e) * 2.0 / 21.0
    return e


def test_low_effort_is_under_the_ema_or_under_the_previous_bar_and_off_asks_nothing():
    # the day's volumes: 38 overnight bars of 600, then the RTH bars
    def scene(prev_vol, trig_vol):
        b2 = (15004.0, 15005.0, 14990.0, 14992.0, prev_vol)
        b3 = (14992.0, 15010.0, 14991.0, 15008.0, trig_vol)
        vols = [600] * 38 + [900, 900, prev_vol, trig_vol]
        return day([B0, B1, b2, b3]), vols
    bars, vols = scene(900, 1500)                                                      # louder than the EMA AND than the bar before
    assert vols[-1] > ema_at(vols) and vols[-1] > vols[-2]
    assert decisions({}, bars) == [] and decisions({"vol": "ema"}, bars) == []
    assert [d[2] for d in decisions({"vol": "off"}, bars)] == [True]
    bars, vols = scene(2400, 1500)                                                     # louder than the EMA but under the bar before
    assert vols[-1] > ema_at(vols) and vols[-1] < vols[-2]
    assert [d[2] for d in decisions({}, bars)] == [True]                               # either: the fall is enough
    assert decisions({"vol": "ema"}, bars) == []                                       # ema alone: no
    bars, vols = scene(900, 480)                                                       # under the EMA
    assert vols[-1] < ema_at(vols)
    assert [d[2] for d in decisions({"vol": "ema"}, bars)] == [True]


# ---- the trend day -----------------------------------------------------------------------------------------------------------------------------

def test_the_developing_value_area_must_sit_higher_than_yesterdays():
    heavy = [(14960.0, 14960.0, 14960.0, 14960.0, 3600)] * 3                           # 10 800 of 13 800 traded at 14960: today's value area is 14960
    bars = day(heavy + [B0, B1, B2, B3])
    assert decisions({"trend": "off"}, bars, va=(14990.0, 15000.0)) == [(sec(10, 30) + 3 * 900, "long", True)]
    assert decisions({}, bars, va=(14990.0, 15000.0)) == []                              # yesterday's middle 14995 is higher than today's 14960
    assert [d[2] for d in decisions({}, bars, va=(14900.0, 15000.0))] == [True]          # 14950 is lower: a trend day


def test_developing_value_area_is_round1s_rule_on_the_minutes_of_the_rth_so_far():
    st, _ = run({"trend": "off"}, day([B0, B1]))
    got = VB.developing_value_area(st)
    ticks, vol = {}, {}
    for m in st.M:
        if m[0] >= sec(9, 30) and m[5] > 0:
            k = round(m[4] / TICK)
            vol[k] = vol.get(k, 0) + m[5]
    tot = sum(vol.values())
    lo = hi = max(vol, key=lambda k: (vol[k], -k))
    acc = vol[lo]
    while acc < 0.7 * tot:
        up, dn = vol.get(hi + 1, -1), vol.get(lo - 1, -1)
        if up >= dn:
            hi += 1
            acc += max(up, 0)
        if dn >= up:
            lo -= 1
            acc += max(dn, 0)
    assert got == (lo * TICK, hi * TICK)


# ---- the structure ------------------------------------------------------------------------------------------------------------------------------

def test_a_bar_under_the_last_valid_down_candles_low_kills_the_setup_and_no_valid_candle_kills_nothing():
    dip = (15004.0, 15005.0, 14979.0, 14992.0, 900)                                   # b2 trades under the structure low 14980
    assert decisions({}, day([B0, B1, dip, B3])) == []
    own = (14992.0, 15010.0, 14979.0, 15008.0, 300)                                   # the trigger bar itself dips under it
    assert decisions({}, day([B0, B1, B2, own])) == []
    wicky = (14995.0, 15010.0, 14970.0, 14996.0, 900)                                 # an up candle: no valid down candle exists
    assert [d[2] for d in decisions({}, day([wicky, B1, (15004.0, 15005.0, 14965.0, 14992.0, 900), B3]))] == [True]


def test_the_nearest_valid_down_candle_before_the_high_is_the_one_that_counts():
    v1 = (15000.0, 15001.0, 14990.0, 14992.0, 900)                                    # a second VALID down candle, nearer the high: low 14990
    up = (14992.0, 15012.0, 14991.0, 15004.0, 900)                                    # the structure high 15012
    over_far_under_near = (15004.0, 15005.0, 14985.0, 14992.0, 900)                   # under 14990 (the nearest), over 14980 (the far one)
    assert decisions({}, day([B0, v1, up, over_far_under_near, B3])) == []
    inside = (15004.0, 15005.0, 14991.0, 14992.0, 900)
    assert [d[2] for d in decisions({}, day([B0, v1, up, inside, B3]))] == [True]


# ---- the continuation ---------------------------------------------------------------------------------------------------------------------------

def test_after_the_break_trade_engulfing_low_effort_bars_enter_again_until_the_structure_high_is_reached():
    hi = (14982.0, 15060.0, 14981.0, 15004.0, 900)                                    # structure high 15060
    b3 = (15000.0, 15010.0, 15000.0, 15008.0, 300)                                    # break, stop 8, target 15024
    b4 = (15008.0, 15026.0, 15006.0, 15025.0, 280)                                    # reaches the target (the trade is closed in it)
    b5 = (15025.0, 15036.0, 15024.0, 15034.0, 260)                                    # engulfs b4 (15034 > 15026), low effort: continuation
    b6 = (15034.0, 15062.0, 15033.0, 15060.0, 250)                                    # its high reaches the structure high: the leg is over
    b7 = (15060.0, 15070.0, 15059.0, 15068.0, 240)                                    # engulfs, low effort: nothing, the leg is over
    got = decisions({}, day([B0, hi, B2, b3, b4, b5, b6, b7]))
    # b3 breaks (10:30). b4 closes at 10:45 after the target was hit inside it: it engulfs b3 on low effort -> the continuation entry (stop
    # 15006, 2R = 15063 cut to 15060). b5 engulfs too but that position is open. b6's high reaches 15060: the leg is over, b7 trades nothing.
    assert [(g[0], g[2]) for g in got] == [(sec(10, 30), True), (sec(10, 45), True)]
    st, res = run({}, day([B0, hi, B2, b3, b4, b5, b6, b7]))
    assert [t["exit_reason"] for t in res.trades] == ["tp", "tp"]
    assert res.trades[1]["tp"] - res.trades[1]["entry_price"] == pytest.approx(15060.0 - 15025.0)
    assert st.cont[1] is None and st.took[1] is True


def test_no_break_trade_no_continuation():
    hi = (14982.0, 15060.0, 14981.0, 15004.0, 900)
    quiet = (14992.0, 15003.0, 14991.0, 15002.0, 300)                                 # a close under VAH + 6: no break
    nxt = (15002.0, 15005.0, 15001.0, 15004.0, 250)                                   # engulfs, low effort, but there was no break trade
    assert decisions({}, day([B0, hi, B2, quiet, nxt])) == []


def test_one_position_at_a_time_and_the_cap_is_a_day_cap():
    hi = (14982.0, 15060.0, 14981.0, 15004.0, 900)
    b3 = (15000.0, 15010.0, 15000.0, 15008.0, 300)
    b4 = (15008.0, 15012.0, 15007.0, 15011.0, 280)                                    # the first trade stays open (no target hit, no stop)
    b5 = (15011.0, 15016.0, 15010.0, 15015.0, 260)                                    # engulfs, low effort: but a position is open
    assert [g[2] for g in decisions({}, day([B0, hi, B2, b3, b4, b5]))] == [True]
    assert len(decisions({"max_tr": 1}, day([B0, hi, B2, b3, b4, b5]))) == 1


# ---- the mirror ----------------------------------------------------------------------------------------------------------------------------------

def mirror(bars, m=15000.0):
    return [(2 * m - o, 2 * m - l, 2 * m - h, 2 * m - c, v) for o, h, l, c, v in bars]


def test_short_is_the_exact_mirror_through_val():
    # trend off: the developing value area's tie rules (lowest price first) are not mirror-symmetric
    bars = day([B0, B1, B2, B3])
    long_trades = run({"trend": "off"}, bars)[1].trades
    YEST["va"] = (30000.0 - VAH, 30000.0 - VAL)
    st = VB.VaBreak({**BASE, "dir": "short", "trend": "off"})
    st.ROLLS = frozenset()
    res = S.run_session(st, minute_tape(mirror(bars), "00:00", D), daily=DAILY, on_error="raise")
    short_trades = res.trades
    assert len(long_trades) == len(short_trades) == 1
    a, b = long_trades[0], short_trades[0]
    assert a["side"] == "long" and b["side"] == "short" and a["entry_ms"] == b["entry_ms"]
    assert 30000.0 - a["entry_price"] == pytest.approx(b["entry_price"])
    assert 30000.0 - a["sl"] == pytest.approx(b["sl"]) and 30000.0 - a["tp"] == pytest.approx(b["tp"])


# ---- sessions and the registry --------------------------------------------------------------------------------------------------------------------

def test_one_instance_09_30_to_15_58_stands_for_the_ny_passes():
    st = VB.VaBreak({**BASE})
    assert st.fam_sessions() == {"t": (sec(9, 30), sec(15, 58))}
    assert st.fam_filter(["asia", "london", "pre", "nyam", "mid", "pm"]) == ["t"]
    assert st.fam_filter(["mid", "pm"]) == []
    assert VB.VaBreak.ONE_INSTANCE_PASSES == ("nyam", "mid", "pm")
    assert st.p["buf_pts"] == 6.0 and st.p["vol"] == "either" and st.p["trend"] == "on" and st.p["max_tr"] == 10


def test_the_registry_holds_va_break_and_va_reclaim_is_untouched():
    assert families.ERRORS == {}
    cls, inputs, both, notes = families.REGISTRY["va_break"]
    assert cls is VB.VaBreak and cls.FEATURES == () and both is False
    assert families.LIBRARY["va_break"]["roots"] == ("NQ",)
    assert "va_break" in B.BASES and "va_break" in B.WRAPPED
    assert families.REGISTRY["va_reclaim"][0].DEFAULTS == {"d_atr": 0.25, "max_tr": 2}


# ---- seeded random days restate the rule ----------------------------------------------------------------------------------------------------------

def oracle(bars_min, va, tf, buf=6.0, vol="either"):
    """An independent restatement of the BREAK on the RTH tf bars of a day of minute bars (trend gate off): the bar indexes (RTH) at which
    a LONG break is met, and the set of bars at which engulf + low effort + not dead hold. Position state is not modelled."""
    n = len(bars_min) // tf
    o = [bars_min[i * tf][0] for i in range(n)]
    h = [max(b[1] for b in bars_min[i * tf:(i + 1) * tf]) for i in range(n)]
    l = [min(b[2] for b in bars_min[i * tf:(i + 1) * tf]) for i in range(n)]
    c = [bars_min[(i + 1) * tf - 1][3] for i in range(n)]
    v = [sum(b[4] for b in bars_min[i * tf:(i + 1) * tf]) for i in range(n)]
    ema, ev = None, []
    for x in v:
        ema = x if ema is None else ema + (x - ema) * 2.0 / 21.0
        ev.append(ema)
    i0 = (9 * 60 + 30) // tf
    vah = va[1]
    breaks, ok = [], []
    for j in range(i0 + 1, n):
        if not c[j] > h[j - 1]:
            continue
        low = v[j] < ev[j]
        eff = True if vol == "off" else low if vol == "ema" else (low or v[j] < v[j - 1])
        if not eff:
            continue
        top = max(h[i0:j])
        jx = max(k for k in range(i0, j) if h[k] == top)
        dead = False
        for k in range(jx, i0 - 1, -1):
            body = o[k] - c[k]
            if body > 0 and body > max(h[k] - o[k], c[k] - l[k]):
                dead = min(l[k + 1:j + 1]) < l[k]
                break
        if dead:
            continue
        ok.append(j)
        if c[j] - vah >= buf and c[j - 1] - vah < buf:
            breaks.append(j)
    return breaks, ok


@pytest.mark.parametrize("tf", [5, 15])
def test_seeded_random_days_first_break_and_every_decision_follow_the_rule(tf):
    n_days, hit = 0, 0
    for seed in range(40):
        walk = rand_bars(960, seed, p0=15000.0, step=2.0)
        va = (14990.0, 15010.0)
        YEST["va"] = va
        breaks, ok = oracle(walk, va, tf)
        log = []

        class Spy(VB.VaBreak):
            def _mkt(self, ctx, side, **kw):
                o = super()._mkt(ctx, side, **kw)
                log.append(((ctx.now_ns - ns("00:00")) // S.NS // 60, o is not None))
                return o

        run({"tf": str(tf), "trend": "off"}, walk, cls=Spy)
        took = [m // tf - 1 for m, t in log if t]                                       # the tf bar that closed at that minute
        n_days += 1
        if breaks:
            assert took and took[0] == breaks[0], (seed, took, breaks)
            hit += 1
        else:
            assert not took, (seed, took)
        assert all(j in ok for j in took), (seed, took, ok)
    assert hit >= 3                                                                   # the days do contain breaks


# ---- real BUILD days -----------------------------------------------------------------------------------------------------------------------------

def test_real_build_days_hold_the_window_the_cap_and_the_flat_time(monkeypatch):
    real_days()
    monkeypatch.undo()                                                                 # the real value area (the cache file or the tape)
    days = days_of("NQ", 8)
    spec = (VB.VaBreak, {**BASE, "tf": "5", "sess": "all", "dir": "both"})
    out = S.run_many([spec], root="NQ", days=days, period="build", workers=1, on_error="raise")
    again = S.run_many([spec], root="NQ", days=days, period="build", workers=1, on_error="raise")
    assert out[0]["trades"] == again[0]["trades"] and out[0]["skipped_by_error"] == 0
    per_day, last_exit = {}, {}
    for t in out[0]["trades"]:
        d = S._date(t["date"])
        es = (t["entry_ms"] // 1000) - S.et_ns(d, "00:00") // S.NS
        assert sec(9, 30) + 300 <= es <= sec(15, 58) - 300 + 120, (t["date"], es)
        assert t["exit_ms"] <= S.et_ns(d, "15:58") // 1_000_000 + 60_000
        assert t["entry_ms"] >= last_exit.get(t["date"], 0)                             # one position at a time
        last_exit[t["date"]] = t["exit_ms"]
        per_day[t["date"]] = per_day.get(t["date"], 0) + 1
    assert all(n <= 10 for n in per_day.values())
