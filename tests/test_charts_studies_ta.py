"""The technical studies (studies_ta.py): each equals the strategy engine's own definition on the same closes, a
preview never commits, a bad wire key is refused, and the session-anchored ones reset on the right clock."""
from __future__ import annotations

import datetime as dt
import math
import random

import pytest

from homebase.charts.bars import Bar
from homebase.charts.hub import warm_bars
from homebase.charts.session import ET
from homebase.charts.studies import make


def ms(y, mo, d, h, mi) -> int:
    return int(dt.datetime(y, mo, d, h, mi, tzinfo=ET).timestamp() * 1000)


def mk(c, h=None, l=None, o=None, v=10, t=0, session="2026-10-07"):
    return Bar(t=t, session=session, o=c if o is None else o, h=c if h is None else h, l=c if l is None else l, c=c, v=v)


def walk(n=400, seed=7):
    """A reproducible random walk of OHLCV bars."""
    r, px, out = random.Random(seed), 100.0, []
    for i in range(n):
        o = px
        px += r.uniform(-1.5, 1.6)
        h, l = max(o, px) + r.uniform(0, 0.8), min(o, px) - r.uniform(0, 0.8)
        out.append(mk(px, h=h, l=l, o=o, v=r.randint(5, 80), t=ms(2026, 10, 7, 9, 30) + i * 60000))
    return out


def run(key, bars):
    s = make(key)
    return [s.push(b) for b in bars]


# ---- the engine's own definitions, restated (research/edge-library/engine/{indicators,families/blocks}.py) ----
def ref_rsi(closes, n=14):
    if len(closes) < n + 1:
        return None
    g = l = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        if d > 0:
            g += d
        else:
            l -= d
    g, l = g / n, l / n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        g = (g * (n - 1) + (d if d > 0 else 0.0)) / n
        l = (l * (n - 1) + (-d if d < 0 else 0.0)) / n
    return 50.0 if g + l == 0 else 100.0 * g / (g + l)


def ref_atr(H, L, C, n=14):
    tr = [H[0] - L[0]] + [max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1])) for i in range(1, len(C))]
    a = sum(tr[:n]) / n
    out = [a]
    for x in tr[n:]:
        a = (a * (n - 1) + x) / n
        out.append(a)
    return out


def ref_efficiency(C, n=14):
    w = C[-n - 1:]
    path = sum(abs(b - a) for a, b in zip(w, w[1:]))
    return None if path == 0 else abs(w[-1] - w[0]) / path


def ref_mfi(H, L, C, V, n=14):
    tp = [(h + l + c) / 3.0 for h, l, c in zip(H[-n - 1:], L[-n - 1:], C[-n - 1:])]
    pos = neg = 0.0
    for i in range(1, n + 1):
        flow = tp[i] * V[-n - 1 + i]
        if tp[i] > tp[i - 1]:
            pos += flow
        elif tp[i] < tp[i - 1]:
            neg += flow
    return None if pos + neg == 0 else 100.0 * pos / (pos + neg)


def test_rsi_equals_the_engines_wilder_rsi_at_every_bar():
    bars = walk()
    C = [b.c for b in bars]
    got = run("rsi:14", bars)
    assert got[:14] == [None] * 14
    for i in (14, 15, 40, 200, 399):
        assert got[i] == pytest.approx(ref_rsi(C[:i + 1]), abs=1e-9)
    assert run("rsi", bars) == got                              # no parameter = 14
    assert run("rsi:2", bars)[2] == pytest.approx(ref_rsi(C[:3], 2))
    assert run("rsi:14", [mk(5.0)] * 30)[-1] == 50.0            # nothing moved


def test_atr_equals_the_engines_wilder_atr():
    bars = walk()
    H, L, C = [b.h for b in bars], [b.l for b in bars], [b.c for b in bars]
    got = run("atr:14", bars)
    ref = ref_atr(H, L, C)
    assert got[:13] == [None] * 13
    assert got[13:] == pytest.approx(ref, abs=1e-9)


def test_efficiency_and_mfi_equal_the_engines():
    bars = walk()
    H, L, C, V = ([getattr(b, k) for b in bars] for k in "hlcv")
    er, mfi = run("er:14", bars), run("mfi:14", bars)
    assert er[:14] == [None] * 14 and mfi[:14] == [None] * 14
    for i in (14, 50, 399):
        assert er[i] == pytest.approx(ref_efficiency(C[:i + 1]), abs=1e-9)
        assert mfi[i] == pytest.approx(ref_mfi(H[:i + 1], L[:i + 1], C[:i + 1], V[:i + 1]), abs=1e-9)
    assert run("er:5", [mk(1.0)] * 9)[-1] is None               # no movement: no reading


def test_macd_is_ema_fast_minus_ema_slow_with_its_signal_and_histogram():
    bars = walk()
    C = [b.c for b in bars]
    got = run("macd:12:26:9", bars)
    f = s = sg = None
    for i, c in enumerate(C):
        f = c if f is None else f + (2 / 13) * (c - f)
        s = c if s is None else s + (2 / 27) * (c - s)
        if i + 1 < 26:
            assert got[i] is None
            continue
        m = f - s
        sg = m if sg is None else sg + (2 / 10) * (m - sg)
        assert got[i]["macd"] == pytest.approx(m, abs=1e-9)
        if i + 1 < 26 + 9 - 1:
            assert got[i]["signal"] is None and got[i]["hist"] is None
        else:
            assert got[i]["signal"] == pytest.approx(sg, abs=1e-9)
            assert got[i]["hist"] == pytest.approx(m - sg, abs=1e-9)


def test_bollinger_is_mean_plus_minus_k_population_deviations():
    bars = walk(60)
    got = run("bb:20:2", bars)
    assert got[18] is None
    w = [b.c for b in bars[40:60]]
    mid = sum(w) / 20
    sd = math.sqrt(sum((x - mid) ** 2 for x in w) / 20)
    assert got[59] == pytest.approx({"mid": mid, "up": mid + 2 * sd, "dn": mid - 2 * sd})
    assert run("bb:20:3", bars)[59]["up"] == pytest.approx(mid + 3 * sd)


def test_stochastic_donchian_keltner_tema():
    bars = walk(80)
    st = run("stoch:14:3:3", bars)
    assert st[14] is None and st[15]["d"] is None and st[15]["k"] is not None   # 14 bars -> raw, 3 raws -> %K, 3 %Ks -> %D
    assert st[16]["d"] is None and st[17]["d"] is not None
    raw = [100.0 * (bars[i].c - min(b.l for b in bars[i - 13:i + 1])) /
           (max(b.h for b in bars[i - 13:i + 1]) - min(b.l for b in bars[i - 13:i + 1])) for i in range(77, 80)]
    assert st[79]["k"] == pytest.approx(sum(raw) / 3)
    assert 0 <= st[79]["k"] <= 100 and 0 <= st[79]["d"] <= 100
    dn = run("donchian:20", bars)
    assert dn[18] is None
    assert dn[79] == {"up": max(b.h for b in bars[60:80]), "dn": min(b.l for b in bars[60:80]),
                      "mid": (max(b.h for b in bars[60:80]) + min(b.l for b in bars[60:80])) / 2}
    kc = run("keltner:20:20:1.5", bars)
    assert kc[18] is None and kc[19] is not None
    assert kc[79]["up"] - kc[79]["mid"] == pytest.approx(kc[79]["mid"] - kc[79]["dn"])
    e = None
    for b in bars:
        e = b.c if e is None else e + (2 / 21) * (b.c - e)
    assert kc[79]["mid"] == pytest.approx(e)
    te = run("tema:10", bars)
    assert te[8] is None and te[9] is not None
    flat = run("tema:10", [mk(7.0)] * 40)
    assert flat[-1] == pytest.approx(7.0)                       # a flat series is its own average


def test_supertrend_flips_with_price_and_trails_one_side():
    up = [mk(100 + i, h=100.6 + i, l=99.4 + i) for i in range(40)]
    down = [mk(140 - i, h=140.6 - i, l=139.4 - i) for i in range(40)]
    got = run("supertrend:10:3", up + down)
    assert got[8] is None and got[9] is not None
    assert got[30]["dir"] == 1 and got[30]["line"] < up[30].c
    assert got[-1]["dir"] == -1 and got[-1]["line"] > down[-1].c
    dirs = [g["dir"] for g in got if g]
    assert dirs.count(-1) and dirs.index(-1) > 30                # it flips only after the turn, not before


def test_preview_never_commits():
    for key in ("rsi:5", "macd:3:6:3", "bb:5", "atr:5", "stoch:5:2:2", "supertrend:3:2", "donchian:5", "keltner:5:5",
                "tema:5", "mfi:5", "er:5", "orb:15", "sess:london"):
        s = make(key)
        bars = walk(30)
        for b in bars[:25]:
            s.push(b)
        state = s.state
        a = s.preview(bars[25])
        assert s.preview(bars[25]) == a and s.state == state, key


def test_opening_range_grows_for_the_window_then_freezes():
    t0 = ms(2026, 10, 7, 9, 30)
    bars = [mk(100 + i, h=101 + i, l=99 + i, t=t0 + i * 60000) for i in range(30)]
    pre = [mk(90, h=200, l=1, t=ms(2026, 10, 7, 9, 29))]       # before the open: never counts
    got = run("orb:15", pre + bars)
    assert got[0] is None
    assert got[1] == {"hi": 101, "lo": 99, "mid": 100.0}
    assert got[15]["hi"] == 101 + 14 and got[15]["lo"] == 99    # minute 14 is the last one inside 15 minutes
    assert got[16] == got[15] == got[30]                        # frozen from 09:45 on
    nxt = mk(500, t=ms(2026, 10, 8, 9, 30), session="2026-10-08")
    s = make("orb:15")
    for b in pre + bars:
        s.push(b)
    assert s.push(nxt) == {"hi": 500, "lo": 500, "mid": 500.0}   # a new session starts its own range


def test_session_range_holds_through_the_day_and_clears_at_midnight():
    night = [mk(100 + i, h=101 + i, l=99 + i, t=ms(2026, 10, 7, 3, 0) + i * 60 * 1000 * 30) for i in range(10)]
    got = run("sess:london", night)
    assert got[0] == {"hi": 101, "lo": 99}
    assert got[9] == {"hi": 110, "lo": 99}
    s = make("sess:london")
    for b in night:
        s.push(b)
    later = mk(300, h=999, l=1, t=ms(2026, 10, 7, 11, 0))        # NY midday: London is over, its range stays
    assert s.push(later) == {"hi": 110, "lo": 99}
    assert s.push(mk(300, t=ms(2026, 10, 8, 0, 5))) is None      # next calendar day: cleared until London opens
    with pytest.raises(ValueError):
        make("sess:mars")


@pytest.mark.parametrize("key", ["rsi:1", "rsi:9999", "rsi:x", "rsi:14:3", "macd:12:26:9:1", "bb:20:0", "stoch:1",
                                 "orb:0", "orb:999", "supertrend:10:99", "nope:1", "rsi:nan", "rsi:inf"])
def test_a_bad_key_is_refused(key):
    with pytest.raises(ValueError):
        make(key)


def test_warm_bars_covers_each_studys_memory():
    assert warm_bars("rsi:14") == 140 and warm_bars("atr:20") == 200
    assert warm_bars("macd:12:26:9") == 5 * 26 + 5 * 9
    assert warm_bars("bb:20:2") == 20 and warm_bars("donchian:50") == 50
    assert warm_bars("stoch:14:3:3") == 20 and warm_bars("mfi:14") == 15
    assert warm_bars("orb:15") == 0 and warm_bars("sess:london") == 0
    assert warm_bars("supertrend:10:3") == 100 and warm_bars("tema:20") == 300
    assert warm_bars("ema:20") == 100                           # the existing ones are untouched


# ---- structure: each against the engine's own functions, restated in pure Python (engine/levels.py, ranges.py, round1.py) ----
def ref_pivots(h, l, n):
    hi = [i for i in range(n, len(h) - n) if h[i] > max(h[i - n:i]) and h[i] > max(h[i + 1:i + n + 1])]
    lo = [i for i in range(n, len(l) - n) if l[i] < min(l[i - n:i]) and l[i] < min(l[i + 1:i + n + 1])]
    return hi, lo


def ref_untouched(h, l, n):
    ih, il = ref_pivots(h, l, n)
    hh = [i for i in ih if max(h[i + 1:], default=-1e18) <= h[i]]
    ll = [i for i in il if min(l[i + 1:], default=1e18) >= l[i]]
    return (h[hh[-1]] if hh else None), (l[ll[-1]] if ll else None), (hh[-1] if hh else None), (ll[-1] if ll else None)


def ref_equal(h, l, n, tol):
    ih, il = ref_pivots(h, l, n)
    out = [None, None]
    for k, (idx, y) in enumerate(((ih, h), (il, [-x for x in l]))):
        pairs = [(a, b, y[a]) for a, b in zip(idx[:-1], idx[1:]) if 0 <= y[a] - y[b] <= tol and max(y[a + 1:b + 1]) <= y[a]]
        for a, b, lvl in reversed(pairs):
            if max(y[b + 1:], default=-1e18) <= lvl:
                out[k] = lvl if k == 0 else -lvl
                break
    return out


def zig(n=900, seed=3, amp=3.0):
    """A wavy walk with real swings."""
    r, px, out = random.Random(seed), 100.0, []
    for i in range(n):
        o = px
        px += amp * math.sin(i / 23.0) + r.uniform(-1.2, 1.2)
        out.append(mk(px, h=max(o, px) + r.uniform(0, 0.6), l=min(o, px) - r.uniform(0, 0.6), o=o, v=r.randint(5, 80),
                      t=ms(2026, 10, 7, 9, 30) + i * 60000))
    return out


def test_swing_levels_equal_the_engines_untouched_swings_at_every_bar():
    bars = zig()
    H, L = [b.h for b in bars], [b.l for b in bars]
    got = run("swing:5", bars)
    seen = 0
    for i in range(len(bars)):
        rh, rl, _, _ = ref_untouched(H[:i + 1], L[:i + 1], 5)
        if rh is None and rl is None:
            assert got[i] is None
            continue
        seen += 1
        assert got[i]["hi"] == rh and got[i]["lo"] == rl, i
    assert seen > 400                                           # the walk really has swings


def test_equal_levels_equal_the_engines_live_equals():
    bars = zig(1200, seed=11, amp=1.5)
    H, L = [b.h for b in bars], [b.l for b in bars]
    got = run("equal:4:1.5", bars)
    hits = 0
    for i in range(0, len(bars), 7):
        rh, rl = ref_equal(H[:i + 1], L[:i + 1], 4, 1.5)
        g = got[i] or {"hi": None, "lo": None}
        assert (g["hi"], g["lo"]) == (rh, rl), i
        hits += rh is not None or rl is not None
    assert hits > 20


def ref_move(h, l, thr):
    mode, hi, lo, pv, ex = 0, h[0], l[0], 0.0, 0.0
    for i in range(1, len(h)):
        if mode == 0:
            hi, lo = max(hi, h[i]), min(lo, l[i])
            if h[i] - lo >= thr:
                mode, pv, ex = 1, lo, h[i]
            elif hi - l[i] >= thr:
                mode, pv, ex = -1, hi, l[i]
        elif mode == 1:
            if h[i] > ex:
                ex = h[i]
            elif ex - l[i] >= thr:
                mode, pv, ex = -1, ex, l[i]
        else:
            if l[i] < ex:
                ex = l[i]
            elif h[i] - ex >= thr:
                mode, pv, ex = 1, ex, h[i]
    return None if mode == 0 else (min(pv, ex), max(pv, ex), mode)


def test_move_range_equals_the_engines_zigzag_and_carries_the_ote_band():
    bars = zig(600, seed=5, amp=4.0)
    H, L = [b.h for b in bars], [b.l for b in bars]
    got = run("rmove:6", bars)
    flips = 0
    for i in range(0, len(bars), 5):
        ref = ref_move(H[:i + 1], L[:i + 1], 6.0)
        if ref is None:
            assert got[i] is None
            continue
        lo, hi, d = ref
        g = got[i]
        assert (g["lo"], g["hi"], g["dir"]) == (lo, hi, d), i
        r = hi - lo
        assert g["mid"] == pytest.approx((hi + lo) / 2)
        if d == 1:                                              # an up leg retraces DOWN from its high
            assert (g["ote1"], g["ote2"]) == pytest.approx((hi - 0.62 * r, hi - 0.79 * r))
        else:
            assert (g["ote1"], g["ote2"]) == pytest.approx((lo + 0.62 * r, lo + 0.79 * r))
        flips += d == -1
    assert flips


def test_swing_range_is_the_latest_untouched_pair_and_points_the_way_its_low_came():
    bars = zig(700, seed=9)
    H, L = [b.h for b in bars], [b.l for b in bars]
    got = run("rswing:5", bars)
    n = 0
    for i in range(0, len(bars), 6):
        rh, rl, ia, ib = ref_untouched(H[:i + 1], L[:i + 1], 5)
        if rh is None or rl is None:
            assert got[i] is None
            continue
        n += 1
        d = 1 if ib < ia else -1
        assert (got[i]["lo"], got[i]["hi"], got[i]["dir"]) == (rl, rh, d), i
    assert n > 30


def test_prior_day_value_area_is_the_engines_70_percent_around_the_heaviest_row():
    def day(session, rows, day_ms):
        # one 1-minute bar per row group at 10:00 ET carrying a footprint: {tick row: (sell, buy)}
        b = mk(100.0, t=day_ms, session=session)
        b.fp = rows
        return b
    d1 = ms(2026, 10, 6, 10, 0)
    vols = {400: 10, 401: 30, 402: 100, 403: 20, 404: 5, 405: 5}          # heaviest 402; 100 of 170
    b1 = day("2026-10-06", {k: (v, 0) for k, v in vols.items()}, d1)
    after = mk(100.0, t=ms(2026, 10, 7, 9, 45), session="2026-10-07")
    s = make("vaprev", 0.25)
    assert s.push(b1) is None                                    # no prior session yet
    got = s.push(after)
    # 70 % of 170 = 119: start 402 (100), neighbours 401 (30) vs 403 (20) -> 401 (130 >= 119)
    assert got == {"val": 401 * 0.25, "vah": 402 * 0.25, "poc": 402 * 0.25}
    # outside RTH nothing counts
    ovn = mk(100.0, t=ms(2026, 10, 8, 3, 0), session="2026-10-08")
    ovn.fp = {500: (999, 999)}
    s.push(ovn)
    s2 = make("vaprev", 0.25)
    for b in (b1, after, ovn, mk(100.0, t=ms(2026, 10, 9, 9, 45), session="2026-10-09")):
        out = s2.push(b)
    assert out["poc"] == 402 * 0.25                              # the overnight prints never reach a profile: the last real one stays


def test_value_area_ties_take_both_neighbours_like_the_engine():
    from homebase.charts.studies_ta import _value_area
    # heaviest row 5; its neighbours tie at 40: both join, 100 + 40 + 40 = 180 >= 70 % of 220
    assert _value_area({4: 40, 5: 100, 6: 40, 7: 20, 3: 20}) == (4, 6, 5)
    # a tie for heaviest takes the lowest row
    assert _value_area({1: 50, 2: 50})[2] == 1


def test_noise_band_is_open_plus_minus_k_times_the_daily_atr_of_the_days_before():
    bars = []
    day = dt.date(2026, 9, 1)
    ranges = []
    for i in range(16):                                         # 16 sessions of one bar before the test day
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        hi, lo = 100.0 + i, 90.0 - i * 0.5
        bars.append(mk(95.0, h=hi, l=lo, o=95.0, t=ms(day.year, day.month, day.day, 10, 0), session=day.isoformat()))
        day += dt.timedelta(days=1)
    s = make("noise:0.5:rth")
    for b in bars:
        s.push(b)
    while day.weekday() >= 5:
        day += dt.timedelta(days=1)
    open_bar = mk(120.0, h=121.0, l=119.0, o=120.0, t=ms(day.year, day.month, day.day, 9, 30), session=day.isoformat())
    got = s.push(open_bar)
    # reference: Wilder ATR(14) over the 16 finished days' true ranges against the previous close (all closes 95)
    H = [100.0 + i for i in range(16)]
    L = [90.0 - i * 0.5 for i in range(16)]
    C = [95.0] * 16
    trs = [max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1])) for i in range(1, 16)]
    a = sum(trs[:14]) / 14
    for x in trs[14:]:
        a = (a * 13 + x) / 14
    assert got["up"] == pytest.approx(120.0 + 0.5 * a) and got["dn"] == pytest.approx(120.0 - 0.5 * a)
    # the early part of the day, before the anchor, has no band
    pre = mk(110.0, t=ms(day.year, day.month, day.day, 9, 0), session=day.isoformat())
    assert make("noise:0.5:rth").push(pre) is None
    # fewer than 15 sessions: no ATR, no band
    assert make("noise").push(open_bar) is None


def test_relative_volume_is_the_bar_over_the_median_of_its_clock_bar():
    s = make("rvol:5:3")
    out = []
    for d in range(7):
        b = mk(100.0, v=100 + d * 10, t=ms(2026, 10, 1 + d, 9, 31), session=f"2026-10-0{1 + d}")
        out.append(s.push(b))
    assert out[:3] == [None, None, None]                         # fewer than 3 days of that clock bar
    assert out[3] == pytest.approx(130 / 110.0)                  # median(100, 110, 120) = 110
    assert out[6] == pytest.approx(160 / 130.0)                  # the last 5 days: 110..150 -> median 130
    probe = mk(100.0, v=300, t=ms(2026, 10, 8, 9, 31), session="2026-10-08")
    assert s.preview(probe) == pytest.approx(300 / 140.0) and s.preview(probe) == s.preview(probe)   # last 5: 120..160


def test_day_high_low_covers_only_finished_sessions():
    s = make("dhl:2")
    days = [("2026-10-05", 110, 90), ("2026-10-06", 120, 95), ("2026-10-07", 105, 80)]
    out = []
    for sess, h, l in days:
        d = dt.date.fromisoformat(sess)
        out.append(s.push(mk(100.0, h=h, l=l, t=ms(d.year, d.month, d.day, 10, 0), session=sess)))
    assert out[0] is None
    assert out[1] == {"hi": 110, "lo": 90}                       # only 10-05 has finished
    assert out[2] == {"hi": 120, "lo": 90}                       # 10-05 and 10-06
    d = dt.date(2026, 10, 8)
    assert s.push(mk(100.0, t=ms(2026, 10, 8, 10, 0), session="2026-10-08")) == {"hi": 120, "lo": 80}   # last two: 10-06, 10-07


def test_structure_keys_and_warmup():
    for key in ("swing", "swing:20", "equal:50:5", "rmove", "rmove:150", "rswing", "vaprev", "noise", "noise:0.4:globex",
                "rvol", "rvol:20:10", "dhl", "dhl:10"):
        make(key)
    for key in ("swing:1", "equal:50:0", "rmove:0", "vaprev:1", "noise:9", "noise:0.3:moon", "rvol:2", "dhl:0", "noise:0.3:rth:x"):
        with pytest.raises(ValueError):
            make(key)
    assert warm_bars("swing:50") == 500 and warm_bars("vaprev") == 400 and warm_bars("noise") == 0
