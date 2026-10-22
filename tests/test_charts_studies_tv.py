"""The "tv:" studies (studies_tv.py): each equals Pine's own formula, restated here in plain loops, at every bar of a
random walk with sessions; a bad key is refused; warm-up and priming are declared; a timeframe works; the house keys
are untouched."""
from __future__ import annotations

import datetime as dt
import math
import random

import pytest

from homebase.charts.bars import Bar
from homebase.charts.hub import prime_sessions, warm_bars
from homebase.charts.session import ET
from homebase.charts.studies import make

MIN = 60_000


def weekdays(n, start=dt.date(2026, 9, 1)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def walk(dates=None, per=120, seed=7):
    """A reproducible random walk of 1-minute OHLCV bars over sessions (default 16 weekdays), each opening 18:00 ET."""
    r, px, out = random.Random(seed), 100.0, []
    for d in dates or weekdays(16):
        t0 = int((dt.datetime(d.year, d.month, d.day, 18, 0, tzinfo=ET) - dt.timedelta(days=1)).timestamp() * 1000)
        for i in range(per):
            o = px
            px += r.uniform(-1.5, 1.6)
            h, l = max(o, px) + r.uniform(0, 0.8), min(o, px) - r.uniform(0, 0.8)
            v = r.randint(5, 80)
            buy = r.randint(0, v)
            out.append(Bar(t=t0 + i * MIN, session=d.isoformat(), o=o, h=h, l=l, c=px, v=v, buy=buy, sell=v - buy, n=v))
    return out


def bar(o, c, v=10, h=None, l=None, session="2026-10-07", i=0):
    t = int(dt.datetime(2026, 10, 6, 18, 0, tzinfo=ET).timestamp() * 1000) + i * MIN
    return Bar(t=t, session=session, o=o, h=max(o, c) if h is None else h, l=min(o, c) if l is None else l, c=c, v=v)


def run(key, bars):
    s = make(key)
    return [s.push(b) for b in bars]


def same(got, want, abs=1e-9):
    assert len(got) == len(want)
    for i, (g, w) in enumerate(zip(got, want)):
        if isinstance(w, dict):
            assert g is not None and set(g) == set(w), (i, g, w)
            for k in w:
                assert (g[k] is None) == (w[k] is None), (i, k, g, w)
                if w[k] is not None:
                    assert g[k] == pytest.approx(w[k], abs=abs), (i, k, g, w)
        elif w is None:
            assert g is None, (i, g)
        else:
            assert g == pytest.approx(w, abs=abs), (i, g, w)


# ---- Pine's ta.* restated: a None is na --------------------------------------------------------------------------
def ref_sma(xs, n):
    return [None if i < n - 1 or None in xs[i - n + 1:i + 1] else sum(xs[i - n + 1:i + 1]) / n for i in range(len(xs))]


def ref_smooth(xs, n, alpha):
    """sum := na(sum[1]) ? ta.sma(src, n) : alpha * src + (1 - alpha) * sum[1]"""
    v = [None] * len(xs)
    for i, x in enumerate(xs):
        prev = v[i - 1] if i else None
        if x is None:
            continue
        if prev is not None:
            v[i] = alpha * x + (1 - alpha) * prev
        elif i >= n - 1 and None not in xs[i - n + 1:i + 1]:
            v[i] = sum(xs[i - n + 1:i + 1]) / n
    return v


def ref_ema(xs, n):
    return ref_smooth(xs, n, 2 / (n + 1))


def ref_rma(xs, n):
    return ref_smooth(xs, n, 1 / n)


def ref_tr(bars, handle_na):
    """ta.tr(handle_na): na on the first bar unless handle_na, then high - low."""
    out = [bars[0].h - bars[0].l if handle_na else None]
    for p, b in zip(bars, bars[1:]):
        out.append(max(b.h - b.l, abs(b.h - p.c), abs(b.l - p.c)))
    return out


def cols(bars):
    return [b.o for b in bars], [b.h for b in bars], [b.l for b in bars], [b.c for b in bars], [b.v for b in bars]


def test_sma_ema_rma_wma_and_the_source_option():
    bars = walk()
    O, H, L, C, V = cols(bars)
    same(run("tv:sma:9", bars), ref_sma(C, 9))
    same(run("tv:ema:9", bars), ref_ema(C, 9))
    same(run("tv:rma:7", bars), ref_rma(C, 7))
    hl2 = [(h + l) / 2 for h, l in zip(H, L)]
    same(run("tv:ema:20:hl2", bars), ref_ema(hl2, 20))
    same(run("tv:sma:5:open", bars), ref_sma(O, 5))
    wma = [None if i < 8 else sum(C[i - 8 + j] * (j + 1) for j in range(9)) / 45 for i in range(len(C))]
    same(run("tv:wma:9", bars), wma)
    assert run("tv:ema", bars) == run("tv:ema:9:close", bars)         # TV's default length, the default source
    assert run("tv:ema:9", bars)[:8] == [None] * 8 and run("tv:ema:9", bars)[8] == pytest.approx(sum(C[:9]) / 9)


def test_rsi_is_the_rma_ratio_with_pines_zero_rules():
    bars = walk()
    C = cols(bars)[3]
    ch = [None] + [b - a for a, b in zip(C, C[1:])]
    up = ref_rma([None if x is None else max(x, 0) for x in ch], 14)
    dn = ref_rma([None if x is None else max(-x, 0) for x in ch], 14)
    want = [None if u is None else 100 if d == 0 else 0 if u == 0 else 100 - 100 / (1 + u / d) for u, d in zip(up, dn)]
    assert want[:14] == [None] * 14 and want[14] is not None
    same(run("tv:rsi:14", bars), want)
    rising = [bar(100 + i, 101 + i, i=i) for i in range(20)]
    assert run("tv:rsi:5", rising)[-1] == 100                           # down = 0
    falling = [bar(100 - i, 99 - i, i=i) for i in range(20)]
    assert run("tv:rsi:5", falling)[-1] == 0                            # up = 0
    assert run("tv:rsi:5", [bar(5, 5, i=i) for i in range(20)])[-1] == 100   # nothing moved: down = 0 first


def test_macd_is_two_emas_and_an_ema_signal_each_with_the_sma_seed():
    bars = walk()
    C = cols(bars)[3]
    f, s = ref_ema(C, 12), ref_ema(C, 26)
    m = [None if a is None or b is None else a - b for a, b in zip(f, s)]
    g = ref_ema(m, 9)
    want = [None if x is None else {"macd": x, "signal": y, "hist": None if y is None else x - y} for x, y in zip(m, g)]
    assert want[24] is None and want[25]["signal"] is None and want[33]["signal"] is not None
    same(run("tv:macd:12:26:9", bars), want)
    assert run("tv:macd", bars) == run("tv:macd:12:26:9:close", bars)


def test_stochastic_with_a_flat_range_na_and_tvs_1_3_smoothing():
    bars = walk()
    H, L, C = cols(bars)[1:4]
    raw = []
    for i in range(len(C)):
        if i < 13:
            raw.append(None)
            continue
        hi, lo = max(H[i - 13:i + 1]), min(L[i - 13:i + 1])
        raw.append(None if hi == lo else 100 * (C[i] - lo) / (hi - lo))
    k = ref_sma(raw, 1)
    d = ref_sma(k, 3)
    same(run("tv:stoch:14:1:3", bars), [None if a is None else {"k": a, "d": b} for a, b in zip(k, d)])
    k3 = ref_sma(raw, 3)
    same(run("tv:stoch:14:3:3", bars), [None if a is None else {"k": a, "d": b} for a, b in zip(k3, ref_sma(k3, 3))])
    flat = [bar(5, 5, i=i) for i in range(10)] + [bar(5, 6, i=10 + i) for i in range(6)]
    got = run("tv:stoch:5:1:3", flat)
    assert got[9] is None and got[10]["k"] == 100 and got[10]["d"] is None and got[12]["d"] == 100


def test_adx_and_dmi_seed_one_bar_late_and_fixnan_the_dis():
    bars = walk()
    H, L, C = cols(bars)[1:4]
    tr = ref_tr(bars, False)
    pdm, mdm = [None], [None]
    for i in range(1, len(C)):
        up, dn = H[i] - H[i - 1], L[i - 1] - L[i]
        pdm.append(up if up > dn and up > 0 else 0)
        mdm.append(dn if dn > up and dn > 0 else 0)
    trs, ps, ms = ref_rma(tr, 14), ref_rma(pdm, 14), ref_rma(mdm, 14)
    plus, minus, dx = [], [], []
    lp = lm = None
    for t, p, m in zip(trs, ps, ms):
        if t is not None and t != 0:
            lp, lm = 100 * p / t, 100 * m / t
        plus.append(lp)
        minus.append(lm)
        s = None if lp is None else lp + lm
        dx.append(None if lp is None else abs(lp - lm) / (1 if s == 0 else s))
    adx = ref_rma(dx, 14)
    want = [None if p is None else {"adx": None if a is None else 100 * a, "pdi": p, "mdi": m} for p, m, a in zip(plus, minus, adx)]
    assert want[13] is None and want[14]["adx"] is None and want[27]["adx"] is not None
    same(run("tv:adx:14:14", bars), want)
    assert run("tv:adx", bars) == run("tv:adx:14:14", bars)
    # dead bars first: a true-range rma of 0 divides into na, and fixnan has no earlier reading to keep
    got = run("tv:adx:3:3", [bar(50, 50, i=i) for i in range(20)] + walk()[:40])
    assert got[:20] == [None] * 20 and got[25]["pdi"] is not None


def test_atr_bb_donchian_and_the_three_keltner_bands():
    bars = walk()
    H, L, C = cols(bars)[1:4]
    same(run("tv:atr:14", bars), ref_rma(ref_tr(bars, True), 14))
    bb = []
    for i, m in enumerate(ref_sma(C, 20)):
        sd = None if m is None else math.sqrt(sum((x - m) ** 2 for x in C[i - 19:i + 1]) / 20)
        bb.append(None if m is None else {"mid": m, "up": m + 2 * sd, "dn": m - 2 * sd})
    same(run("tv:bb:20:2", bars), bb)
    dc = [None if i < 19 else {"up": max(H[i - 19:i + 1]), "dn": min(L[i - 19:i + 1]), "mid": (max(H[i - 19:i + 1]) + min(L[i - 19:i + 1])) / 2}
          for i in range(len(C))]
    same(run("tv:donchian:20", bars), dc)
    e = ref_ema(C, 20)
    tr = ref_tr(bars, True)
    for key, band in (("tv:keltner:20:2:10", ref_rma(tr, 10)), ("tv:keltner:20:2:10:tr", tr),
                      ("tv:keltner:20:2:10:range", ref_rma([h - l for h, l in zip(H, L)], 20))):
        want = [None if a is None or b is None else {"mid": a, "up": a + 2 * b, "dn": a - 2 * b} for a, b in zip(e, band)]
        same(run(key, bars), want)
    assert run("tv:keltner", bars) == run("tv:keltner:20:2:10:atr", bars)


def test_supertrend_follows_pines_reference_bar_for_bar():
    bars = walk()
    H, L, C = cols(bars)[1:4]
    atr = ref_rma(ref_tr(bars, True), 10)
    want, lower, upper, direction = [], [], [], []
    for i in range(len(C)):
        if atr[i] is None:
            want.append(None)
            lower.append(None)
            upper.append(None)
            direction.append(None)
            continue
        src = (H[i] + L[i]) / 2
        lo, up = src - 3 * atr[i], src + 3 * atr[i]
        plo = 0 if i == 0 or lower[i - 1] is None else lower[i - 1]       # nz(lowerBand[1])
        pup = 0 if i == 0 or upper[i - 1] is None else upper[i - 1]
        pc = C[i - 1] if i else None
        lo = lo if (lo > plo or (pc is not None and pc < plo)) else plo
        up = up if (up < pup or (pc is not None and pc > pup)) else pup
        if i == 0 or atr[i - 1] is None:
            d = 1
        elif direction[i - 1] == 1:                                     # superTrend[1] == upperBand[1]
            d = -1 if C[i] > up else 1
        else:
            d = 1 if C[i] < lo else -1
        lower.append(lo)
        upper.append(up)
        direction.append(d)
        want.append({"line": lo if d == -1 else up, "dir": d})
    assert want[9]["dir"] == 1 and {w["dir"] for w in want[10:]} == {1, -1}
    same(run("tv:supertrend:10:3", bars), want)
    same(run("tv:supertrend", bars), want)


def test_tema_and_mfi():
    bars = walk()
    H, L, C, V = cols(bars)[1:]
    e1 = ref_ema(C, 9)
    e2 = ref_ema(e1, 9)
    e3 = ref_ema(e2, 9)
    tema = [None if c is None else 3 * (a - b) + c for a, b, c in zip(e1, e2, e3)]
    assert tema[23] is None and tema[24] is not None
    same(run("tv:tema:9", bars), tema)
    tp = [(h + l + c) / 3 for h, l, c in zip(H, L, C)]
    mfi = []
    for i in range(len(C)):
        if i < 14:
            mfi.append(None)
            continue
        up = sum(tp[j] * V[j] for j in range(i - 13, i + 1) if tp[j] > tp[j - 1])
        dn = sum(tp[j] * V[j] for j in range(i - 13, i + 1) if tp[j] < tp[j - 1])
        mfi.append(None if dn == 0 else 100 - 100 / (1 + up / dn))
    same(run("tv:mfi:14", bars), mfi)
    rising = [bar(100 + i, 101 + i, i=i) for i in range(20)]
    assert run("tv:mfi:5", rising)[-1] is None                          # no down flow: Pine divides into na


def test_vwap_of_hlc3_with_volume_weighted_bands_per_anchor():
    dates = [dt.date(2026, 9, 28), dt.date(2026, 9, 29), dt.date(2026, 10, 5), dt.date(2026, 10, 6), dt.date(2026, 12, 30),
             dt.date(2026, 12, 31), dt.date(2027, 1, 4), dt.date(2027, 1, 5)]
    bars = walk(dates, per=30)
    anchors = {"session": lambda d: d, "week": lambda d: d.isocalendar()[:2], "month": lambda d: (d.year, d.month),
               "quarter": lambda d: (d.year, (d.month - 1) // 3), "year": lambda d: d.year}
    for name, keyf in anchors.items():
        want, acc = [], {}
        for b in bars:
            k = keyf(dt.date.fromisoformat(b.session))
            pv, p2v, v = acc.get(k, (0.0, 0.0, 0))
            p = (b.h + b.l + b.c) / 3
            pv, p2v, v = pv + p * b.v, p2v + p * p * b.v, v + b.v
            acc = {k: (pv, p2v, v)}
            vw = pv / v
            sd = math.sqrt(max(p2v / v - vw * vw, 0.0))                 # a one-bar period rounds to -1e-12
            want.append({"vwap": vw, "u1": vw + sd, "l1": vw - sd, "u2": vw + 2 * sd, "l2": vw - 2 * sd, "u3": vw + 3 * sd, "l3": vw - 3 * sd})
        same(run(f"tv:vwap:{name}", bars), want, abs=1e-6)
    assert run("tv:vwap", bars) == run("tv:vwap:session", bars)
    resets = {}
    for name in anchors:                                                 # a reset bar's VWAP is its own hlc3
        got = run(f"tv:vwap:{name}", bars)
        resets[name] = [i for i in range(1, len(bars)) if got[i]["vwap"] == pytest.approx((bars[i].h + bars[i].l + bars[i].c) / 3)]
    assert resets["session"] == [30, 60, 90, 120, 150, 180, 210]
    assert resets["week"] == [60, 120, 180] and resets["month"] == [60, 120, 180] and resets["quarter"] == [60, 180]
    assert resets["year"] == [180]


def ref_sides(bars):
    out, pc, ps = [], None, 0
    for b in bars:
        if b.c > b.o:
            s = 1
        elif b.c < b.o:
            s = -1
        elif pc is None or b.c == pc:
            s = ps
        else:
            s = 1 if b.c > pc else -1
        out.append(s)
        pc, ps = b.c, s
    return out


def test_cvd_vdelta_and_updown_use_tvs_side_rule():
    bars = walk()
    sides = ref_sides(bars)
    cvd, vd, ud, cum, sess = [], [], [], 0, None
    for b, s in zip(bars, sides):
        if b.session != sess:
            sess, cum = b.session, 0
        d = s * b.v
        cvd.append({"o": cum, "h": max(cum, cum + d), "l": min(cum, cum + d), "c": cum + d})
        cum += d
        vd.append({"o": 0, "h": max(0, d), "l": min(0, d), "c": d})
        ud.append({"up": b.v if s > 0 else 0, "down": -b.v if s < 0 else 0, "delta": d})
    assert run("tv:cvd", bars) == cvd and run("tv:vdelta", bars) == vd and run("tv:updown", bars) == ud
    hand = [bar(100, 101, 10), bar(101, 100, 5), bar(100, 100, 4), bar(102, 102, 3), bar(102, 102, 6, session="2026-10-08")]
    assert run("tv:cvd", hand) == [{"o": 0, "h": 10, "l": 0, "c": 10}, {"o": 10, "h": 10, "l": 5, "c": 5},
                                   {"o": 5, "h": 5, "l": 1, "c": 1},          # equal: against the previous close, equal again: inherit down
                                   {"o": 1, "h": 4, "l": 1, "c": 4},          # equal: 102 > the previous close 100
                                   {"o": 0, "h": 6, "l": 0, "c": 6}]          # a new session; inherits up
    assert run("tv:updown", hand)[2] == {"up": 0, "down": -4, "delta": -4}
    assert run("tv:vdelta", [bar(5, 5, 7)]) == [{"o": 0, "h": 0, "l": 0, "c": 0}]   # no side yet


def ref_rvol(bars, n, cumulative):
    """Each session's rows of (seconds since 18:00 ET, volume or volume so far); a bar reads the last row at or before
    its time in each of the last n finished sessions and divides by their mean."""
    out, done, rows, cum, sess = [], [], [], 0, None
    for b in bars:
        if b.session != sess:
            if sess is not None:
                done = (done + [rows])[-n:]
            sess, rows, cum = b.session, [], 0
        et = dt.datetime.fromtimestamp(b.t / 1000, ET)
        off = (et.hour * 3600 + et.minute * 60 - 18 * 3600) % 86400
        cum += b.v
        x = cum if cumulative else b.v
        rows.append((off, x))
        past = [max((r for r in d if r[0] <= off), key=lambda r: r[0])[1] for d in done if d and d[0][0] <= off]
        out.append(None if not past else x / (sum(past) / len(past)))
    return out


def test_relative_volume_at_time_cumulative_and_regular():
    bars = walk()
    gone = {bars[3 * 120 + 5].t, bars[3 * 120 + 6].t}                   # two minutes missing from the fourth session
    bars = [b for b in bars if b.t not in gone]
    assert len(bars) == 16 * 120 - 2
    same(run("tv:rvol:14", bars), ref_rvol(bars, 14, True))
    same(run("tv:rvol:14:regular", bars), ref_rvol(bars, 14, False))
    same(run("tv:rvol:3:cumulative", bars), ref_rvol(bars, 3, True))
    got = run("tv:rvol:14", bars)
    assert got[:120] == [None] * 120 and got[120] is not None          # the first session has nothing to compare with
    assert got[120] == pytest.approx(bars[120].v / bars[0].v)


def test_average_daily_range_is_the_sma_of_the_finished_sessions_ranges():
    bars = walk()
    rng, want, sess, h, l = [], [], None, None, None
    for b in bars:
        if b.session != sess:
            if sess is not None:
                rng.append(h - l)
            sess, h, l = b.session, b.h, b.l
        h, l = max(h, b.h), min(l, b.l)
        want.append(sum(rng[-14:]) / 14 if len(rng) >= 14 else None)
    same(run("tv:adr:14", bars), want)
    assert want[14 * 120 - 1] is None and want[14 * 120] is not None
    assert run("tv:adr:3", bars)[3 * 120] == pytest.approx(sum(rng[:3]) / 3)


def ref_pivots(kind, po, h, l, c, o):
    r = h - l
    p = (h + l + c) / 3
    if kind == "traditional":
        return {"p": p, "r1": 2 * p - l, "s1": 2 * p - h, "r2": p + r, "s2": p - r, "r3": h + 2 * (p - l), "s3": l - 2 * (h - p),
                "r4": h + 3 * (p - l), "s4": l - 3 * (h - p), "r5": h + 4 * (p - l), "s5": l - 4 * (h - p)}
    if kind == "fibonacci":
        return {"p": p, "r1": p + 0.382 * r, "s1": p - 0.382 * r, "r2": p + 0.618 * r, "s2": p - 0.618 * r, "r3": p + r, "s3": p - r}
    if kind == "woodie":
        p = (h + l + 2 * o) / 4
        return {"p": p, "r1": 2 * p - l, "s1": 2 * p - h, "r2": p + r, "s2": p - r, "r3": h + 2 * (p - l), "s3": l - 2 * (h - p),
                "r4": h + 2 * (p - l) + r, "s4": l - 2 * (h - p) - r}
    if kind == "classic":
        return {"p": p, "r1": 2 * p - l, "s1": 2 * p - h, "r2": p + r, "s2": p - r, "r3": p + 2 * r, "s3": p - 2 * r, "r4": p + 3 * r, "s4": p - 3 * r}
    if kind == "dm":
        x = h + 2 * l + c if c < po else (2 * h + l + c if c > po else h + l + 2 * c)
        return {"p": x / 4, "r1": x / 2 - l, "s1": x / 2 - h}
    r5 = h / l * c
    return {"p": p, "r1": c + 1.1 * r / 12, "s1": c - 1.1 * r / 12, "r2": c + 1.1 * r / 6, "s2": c - 1.1 * r / 6, "r3": c + 1.1 * r / 4,
            "s3": c - 1.1 * r / 4, "r4": c + 1.1 * r / 2, "s4": c - 1.1 * r / 2, "r5": r5, "s5": 2 * c - r5}


@pytest.mark.parametrize("kind", ["traditional", "fibonacci", "woodie", "classic", "dm", "camarilla"])
def test_pivot_points_standard_from_the_prior_session(kind):
    bars = walk(per=40)
    want, days, sess = [], [], None
    for b in bars:
        if b.session != sess:
            sess = b.session
            days.append([b.o, b.h, b.l, b.c])
        d = days[-1]
        d[1], d[2], d[3] = max(d[1], b.h), min(d[2], b.l), b.c
        want.append(None if len(days) < 2 else ref_pivots(kind, *days[-2], days[-1][0]))
    assert want[39] is None and want[40] is not None and want[40] == want[79]
    same(run(f"tv:pivots:{kind}", bars), want)
    assert run("tv:pivots", bars) == run("tv:pivots:traditional", bars)
    dm = [bar(100, 110, i=0), bar(110, 100, i=1), bar(100, 100, i=2, session="2026-10-08")]      # close == open: X = H + L + 2C
    assert run("tv:pivots:dm", dm)[-1] == {"p": (110 + 100 + 200) / 4, "r1": 410 / 2 - 100, "s1": 410 / 2 - 110}


def test_pivot_high_low_is_known_right_bars_later():
    bars = walk()
    H, L = cols(bars)[1:3]
    want = []
    for i in range(len(H)):
        if i < 20:
            want.append(None)
            continue
        j = i - 10
        hi = H[j] if all(H[k] < H[j] for k in range(j - 10, j + 11) if k != j) else None
        lo = L[j] if all(L[k] > L[j] for k in range(j - 10, j + 11) if k != j) else None
        want.append(None if hi is None and lo is None else {"hi": hi, "lo": lo})
    assert sum(w is not None for w in want) > 10
    assert run("tv:pivothl:10:10", bars) == want
    assert run("tv:pivothl", bars) == want
    tie = [bar(1, 1, h=5, i=0), bar(1, 1, h=9, i=1), bar(1, 1, h=9, i=2), bar(1, 1, h=5, i=3), bar(1, 1, h=5, i=4)]
    assert all(v is None or v["hi"] is None for v in run("tv:pivothl:1:1", tie))   # an equal high is no pivot


def test_twap_is_the_sessions_running_mean_of_ohlc4():
    bars = walk(per=30)
    want, sess, tot, k = [], None, 0.0, 0
    for b in bars:
        if b.session != sess:
            sess, tot, k = b.session, 0.0, 0
        tot, k = tot + (b.o + b.h + b.l + b.c) / 4, k + 1
        want.append(tot / k)
    same(run("tv:twap", bars), want)
    same(run("tv:twap:close", bars[:30]), [sum(x.c for x in bars[:i + 1]) / (i + 1) for i in range(30)])


@pytest.mark.parametrize("key", ["tv", "tv:", "tv:nope", "tv:rsi:0", "tv:rsi:x", "tv:rsi:14:foo", "tv:rsi:14:close:1", "tv:vwap:rth",
                                 "tv:keltner:20:2:10:sma", "tv:cvd:1", "tv:pivots:bob", "tv:rvol:14:median", "tv:stoch:14:1:3:1",
                                 "tv:rsi:nan", "tv:bb:20:0", "tv:adr:0", "tv:twap:vwap"])
def test_a_bad_key_is_refused(key):
    with pytest.raises(ValueError):
        make(key)


def test_warm_bars_and_prime_sessions_cover_each_studys_memory():
    assert warm_bars("tv:ema:20") == 100 and warm_bars("tv:ema") == 45 and warm_bars("tv:sma:9:hl2") == 9
    assert warm_bars("tv:rma:7") == 70 and warm_bars("tv:wma:9") == 9 and warm_bars("tv:rsi:14") == 140
    assert warm_bars("tv:macd") == 5 * 26 + 5 * 9 and warm_bars("tv:macd:5:10:3") == 65
    assert warm_bars("tv:stoch:14:1:3") == 18 and warm_bars("tv:adx:14:14") == 280 and warm_bars("tv:adx:7") == 210
    assert warm_bars("tv:atr:14") == 140 and warm_bars("tv:bb:20:2") == 20 and warm_bars("tv:donchian:50") == 50
    assert warm_bars("tv:keltner:20:2:10") == 200 and warm_bars("tv:supertrend:10:3") == 100
    assert warm_bars("tv:tema:9") == 135 and warm_bars("tv:mfi:14") == 15 and warm_bars("tv:pivothl:10:10") == 21
    assert [warm_bars(k) for k in ("tv:vwap", "tv:vwap:week", "tv:cvd", "tv:vdelta", "tv:updown", "tv:rvol:14", "tv:adr:14",
                                   "tv:pivots", "tv:twap")] == [0] * 9
    assert warm_bars("tv:ema:20@3600") == 6000
    assert [prime_sessions(k) for k in ("tv:rvol:14", "tv:rvol", "tv:rvol:5:regular", "tv:adr:14", "tv:adr:3", "tv:pivots",
                                        "tv:pivots:dm", "tv:ema:20", "tv:vwap:week", "tv:cvd")] == [15, 15, 6, 15, 4, 1, 1, 0, 0, 0]
    assert prime_sessions("tv:ema:20@3600") == 6                        # 100 hour bars = 4.3 trading days, plus one


def test_a_tv_study_takes_a_timeframe():
    bars = walk(per=130)[:130]                                           # one session, 18:00 .. 20:09
    got = run("tv:sma:2@3600", bars)
    assert got[:60] == [None] * 60                                       # the second hour opens at bar 60
    assert got[60] == pytest.approx((bars[59].c + bars[60].c) / 2)       # the finished 18:00 hour and the 19:00 hour so far
    assert got[119] == pytest.approx((bars[59].c + bars[119].c) / 2)
    assert got[120] == pytest.approx((bars[119].c + bars[120].c) / 2)
    st = make("tv:cvd@900")
    for b in bars[:40]:
        st.push(b)
    before = st.state
    assert st.preview(bars[40]) == st.preview(bars[40]) and st.state is before


def test_the_house_keys_are_untouched_and_differ_only_where_pine_does():
    bars = walk()
    house, tv = run("rsi:14", bars), run("tv:rsi:14", bars)
    same(house, tv)                                                      # the same seed: equal on a moving market
    flat = [bar(5, 5, i=i) for i in range(30)]
    assert run("rsi:14", flat)[-1] == 50.0 and run("tv:rsi:14", flat)[-1] == 100.0
    house, tv = run("ema:9", bars), run("tv:ema:9", bars)
    assert house[0] == bars[0].c and tv[0] is None                       # the house EMA seeds with the first close
    assert abs(house[8] - tv[8]) > 1e-6 and abs(house[-1] - tv[-1]) < 1e-6   # the seeds differ, the memory fades
    same(run("atr:14", bars), run("tv:atr:14", bars))                   # ta.atr is the house ATR
    same(run("bb:20:2", bars), run("tv:bb:20:2", bars))
    same(run("donchian:20", bars), run("tv:donchian:20", bars))
    with pytest.raises(ValueError):
        make("rsi:14:tv")                                                # no new token on a house key
