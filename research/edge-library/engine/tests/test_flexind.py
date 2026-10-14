"""flexind: the open layer's indicators against plain restatements (numpy, written here from the textbook definitions), the two reads
(gate_ok, event) and the day calendar. No engine, no tape."""
import numpy as np
import pytest

import flexind as F

rng = np.random.default_rng(7)
N = 400
C = 15000 + np.cumsum(rng.normal(0, 8, N))
O = np.r_[C[0], C[:-1]] + rng.normal(0, 2, N)
H = np.maximum(O, C) + np.abs(rng.normal(0, 4, N))
L = np.minimum(O, C) - np.abs(rng.normal(0, 4, N))
V = rng.integers(50, 500, N).astype(float)


def feed(ind):
    out = []
    for i in range(N):
        ind.update(O[i], H[i], L[i], C[i], V[i])
        out.append(ind.v)
    return out


def ema(x, n):
    e, out = x[0], [x[0]]
    for v in x[1:]:
        e = e + 2.0 / (n + 1) * (v - e)
        out.append(e)
    return np.array(out)


def atr14():
    tr = np.r_[H[0] - L[0], np.maximum.reduce([H[1:] - L[1:], abs(H[1:] - C[:-1]), abs(L[1:] - C[:-1])])]
    a = [tr[:k + 1].mean() for k in range(14)]
    for x in tr[14:]:
        a.append((a[-1] * 13 + x) / 14)
    return np.array(a)


def close(a, b):
    assert a is not None and abs(a - b) < 1e-9 * max(1.0, abs(b)), (a, b)


def test_ema_family_matches_a_restatement():
    A = atr14()
    pe, ex, mc = feed(F.make("price_ema", 20)), feed(F.make("ema_x", 9, 21)), feed(F.make("macd", 12, 26, 9))
    e20, e9, e21, e12, e26 = ema(C, 20), ema(C, 9), ema(C, 21), ema(C, 12), ema(C, 26)
    line = e12 - e26
    sig = ema(line, 9)
    assert pe[18] is None and ex[19] is None and mc[24] is None                       # not before n / max(n, m) bars
    for i in (19, 100, 399):
        close(pe[i], (C[i] - e20[i]) / A[i])
    for i in (20, 150, 399):
        close(ex[i], (e9[i] - e21[i]) / A[i])
    for i in (25, 150, 399):
        close(mc[i], (line[i] - sig[i]) / A[i])


def test_rsi_is_wilders():
    r = feed(F.make("rsi", 14))
    d = np.diff(C)
    up, dn = np.maximum(d, 0), np.maximum(-d, 0)
    ag, al = up[:14].mean(), dn[:14].mean()
    ref = {14: 100 - 100 / (1 + ag / al)}
    for i in range(14, len(d)):
        ag, al = (ag * 13 + up[i]) / 14, (al * 13 + dn[i]) / 14
        ref[i + 1] = 100 - 100 / (1 + ag / al)
    assert all(x is None for x in r[:14]) and r[0] is None
    for i in (14, 15, 60, 399):
        close(r[i], ref[i])


@pytest.mark.parametrize("kind,n", [("zscore", 20), ("stoch", 14), ("roc", 10), ("cci", 20), ("er", 14)])
def test_window_indicators_match_numpy(kind, n):
    r = feed(F.make(kind, n))
    for i in (n + 1, 120, 399):
        w = slice(i - n + 1, i + 1)
        if kind == "zscore":
            ref = (C[i] - C[w].mean()) / C[w].std()
        elif kind == "stoch":
            ref = 100 * (C[i] - L[w].min()) / (H[w].max() - L[w].min())
        elif kind == "roc":
            ref = 100 * (C[i] / C[i - n] - 1)
        elif kind == "cci":
            tp = (H + L + C) / 3
            ref = (tp[i] - tp[w].mean()) / (0.015 * np.abs(tp[w] - tp[w].mean()).mean())
        else:
            ref = abs(C[i] - C[i - n]) / np.abs(np.diff(C[i - n:i + 1])).sum()
        close(r[i], ref)


def test_adx_is_wilders():
    n = 14
    r = feed(F.make("adx", n))
    up, dn = H[1:] - H[:-1], L[:-1] - L[1:]
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum.reduce([H[1:] - L[1:], abs(H[1:] - C[:-1]), abs(L[1:] - C[:-1])])
    st, sp, sm = tr[:n].sum(), pdm[:n].sum(), mdm[:n].sum()
    dx = [100 * abs(sp - sm) / (sp + sm)]
    for i in range(n, len(tr)):
        st, sp, sm = st - st / n + tr[i], sp - sp / n + pdm[i], sm - sm / n + mdm[i]
        dx.append(100 * abs(sp - sm) / (sp + sm))
    adx = [np.mean(dx[:n])]
    for x in dx[n:]:
        adx.append((adx[-1] * (n - 1) + x) / n)
    first = 2 * n - 1                                                                 # the bar index of the first ADX
    assert r[first - 1] is None and r[0] is None
    for j in (0, 5, 100, len(adx) - 1):
        close(r[first + j], adx[j])


def test_ranks_count_the_bars_before_and_need_their_bars():
    a = feed(F.make("atr_rank", 50))
    A = atr14()
    i = 200
    close(a[i], (np.sum(A[i - 50:i] < A[i]) + 0.5 * np.sum(A[i - 50:i] == A[i])) / 50)
    assert a[F.bars_needed("atr_rank", 50) - 2] is None and a[F.bars_needed("atr_rank", 50) - 1] is not None
    b = feed(F.make("bbw_rank", 30))
    assert b[F.bars_needed("bbw_rank", 30) - 2] is None and b[F.bars_needed("bbw_rank", 30) - 1] is not None
    assert all(0.0 <= x <= 1.0 for x in b if x is not None)


def test_bars_needed_is_the_first_bar_with_a_value():
    for kind, args in (("rsi", (14,)), ("price_ema", (20,)), ("ema_x", (9, 21)), ("macd", (12, 26, 9)), ("zscore", (20,)), ("stoch", (14,)),
                       ("roc", (10,)), ("cci", (20,)), ("adx", (14,)), ("er", (14,)), ("price_sma", (50,)), ("sma_x", (20, 50))):
        r = feed(F.make(kind, *args))
        k = F.bars_needed(kind, *args)
        assert r[k - 2] is None and r[k - 1] is not None, (kind, k)


def test_gate_and_event_reads():
    d = F.make("rsi", 14)
    d.v, d.p = 72.0, 65.0
    assert F.gate_ok(d, "long", "with", 20) and not F.gate_ok(d, "short", "with", 20)         # bull: 72 > 50 + 20
    assert F.gate_ok(d, "short", "against", 20) and not F.gate_ok(d, "long", "against", 20)    # a fade of the extreme
    d.v = 60.0
    assert not F.gate_ok(d, "long", "with", 20) and not F.gate_ok(d, "short", "with", 20)      # inside the band: neither side
    assert F.gate_ok(d, "long", "with", 0)
    r = F.make("adx", 14)
    r.v = 30.0
    assert F.gate_ok(r, "long", "with", 25) and F.gate_ok(r, "short", "with", 25) and not F.gate_ok(r, "long", "against", 25)
    r.v = None
    assert not F.gate_ok(r, "long", "with", 0) and not F.gate_ok(r, "short", "against", 0)
    d.v, d.p = 71.0, 69.0
    assert F.event(d, 20, "enter") == 1                                                       # crosses above 70
    d.v, d.p = 29.0, 31.0
    assert F.event(d, 20, "enter") == -1
    d.v, d.p = 31.0, 29.0
    assert F.event(d, 20, "exit") == 1                                                        # comes back out of the oversold zone
    d.v, d.p = 69.0, 71.0
    assert F.event(d, 20, "exit") == -1
    d.v, d.p = 70.0, 70.0
    assert F.event(d, 20, "enter") == 0
    d.v, d.p = 71.0, None
    assert F.event(d, 20, "enter") == 0 and F.event(r, 0, "enter") == 0


def test_the_day_calendar():
    assert F.day_ok("2025-01-10", "nfp") and F.day_ok("2025-01-10", "news") and F.day_ok("2025-01-10", "tier1") and F.day_ok("2025-01-10", "fri")
    assert not F.day_ok("2025-01-10", "nonews") and not F.day_ok("2025-01-10", "mon")
    assert F.day_ok("2025-01-31", "month_end") and not F.day_ok("2025-01-30", "month_end")
    assert F.day_ok("2025-03-31", "month_end") and F.day_ok("2025-02-03", "month_start") and not F.day_ok("2025-02-04", "month_start")   # Feb 1 is a Saturday
    assert F.day_ok("2025-01-17", "opex") and not F.day_ok("2025-01-10", "opex")
    assert F.day_ok("2025-09-17", "fomc") and not F.day_ok("2025-09-17", "nofomc")
    assert F.day_ok("2025-06-04", "all")
    assert F.day_ok("2025-01-10", "rel0830") and F.day_ok("2025-01-10", "rel1000")             # NFP 08:30 and Michigan 10:00 the same day
    assert F.day_ok("2025-01-14", "rel0830") and not F.day_ok("2025-01-14", "rel1000")         # PPI at 08:30 only
    ism = next(r["date"] for r in __import__("csv").DictReader(F.EVENTS.open()) if r["time_et"] == "10:00" and r["type"] == "ISM_MFG")
    assert F.day_ok(ism, "rel1000") and F.day_ok(ism, "news")
    with pytest.raises(ValueError):
        F.day_ok("2025-01-10", "nfp_only")
    assert set(F.DAY_RULES) >= {"all", "news", "nonews", "mon", "fri", "month_end", "opex"}


def test_price_sma_and_sma_x_are_the_plain_mean_over_atr():
    g = np.random.default_rng(8)
    bars = [(100.0 + i * 0.1 + float(g.normal(0, 1)),) * 1 for i in range(120)]
    c = [b[0] for b in bars]
    ps, sx, ref = F.make("price_sma", 50), F.make("sma_x", 20, 50), F.make("price_ema", 50)
    for i, x in enumerate(c):
        for ind in (ps, sx, ref):
            ind.update(x, x + 0.5, x - 0.5, x, 1.0)
        if i + 1 >= 50:
            assert ps.v == pytest.approx((x - sum(c[i - 49:i + 1]) / 50) / ps.atr())
            assert sx.v == pytest.approx((sum(c[i - 19:i + 1]) / 20 - sum(c[i - 49:i + 1]) / 50) / sx.atr())
        else:
            assert ps.v is None and sx.v is None
