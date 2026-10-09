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
