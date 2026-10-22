"""TradingView's long-tail studies (studies_tv2.py): each equals its Pine formula, restated here over whole lists the way
Pine reads a series (None = na, src[k] = k bars back, a comparison with na is false, x / 0 is na), at every bar of a
random walk; PARAMS / WARM / PRIME have the shape studies_tv.make_tv expects; a preview never commits."""
from __future__ import annotations

import datetime as dt
import math
import random
import re

import pytest

from homebase.charts.bars import Bar
from homebase.charts.session import ET
from homebase.charts.studies_ta import _Study
from homebase.charts.studies_tv2 import PARAMS, PRIME, WARM


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


def study(name, *args):
    cls, spec = PARAMS[name]
    return cls(*(list(args) + [d for d, _, _ in spec[len(args):]]))


def run(name, bars):
    s = study(name)
    return [s.push(b) for b in bars]


# ---- Pine's series functions over whole lists (None = na) ----
def O(b): return [x.o for x in b]
def H(b): return [x.h for x in b]
def L(b): return [x.l for x in b]
def C(b): return [x.c for x in b]
def V(b): return [float(x.v) for x in b]
def hl2(b): return [(x.h + x.l) / 2 for x in b]
def hlc3(b): return [(x.h + x.l + x.c) / 3 for x in b]


def na(*xs):
    return any(x is None for x in xs)


def nz(x, d=0.0):
    return d if x is None else x


def shift(xs, k):
    """src[k]."""
    return [None] * k + list(xs[:len(xs) - k]) if k else list(xs)


def binop(f):
    def op(a, b):
        b = b if isinstance(b, list) else [b] * len(a)
        return [None if na(x, y) else f(x, y) for x, y in zip(a, b)]
    return op


add, sub, mul = binop(lambda x, y: x + y), binop(lambda x, y: x - y), binop(lambda x, y: x * y)
div = binop(lambda x, y: None if y == 0 else x / y)


def fmap(f, xs):
    return [None if x is None else f(x) for x in xs]


def window(xs, n, f):
    return [None if i + 1 < n or na(*xs[i + 1 - n:i + 1]) else f(xs[i + 1 - n:i + 1]) for i in range(len(xs))]


def sma(xs, n): return window(xs, n, lambda w: sum(w) / n)
def msum(xs, n): return window(xs, n, sum)
def highest(xs, n): return window(xs, n, max)
def lowest(xs, n): return window(xs, n, min)
def wma(xs, n): return window(xs, n, lambda w: sum(x * (i + 1) for i, x in enumerate(w)) / (n * (n + 1) / 2))
def stdev(xs, n): return window(xs, n, lambda w: math.sqrt(sum((x - sum(w) / n) ** 2 for x in w) / n))
def dev(xs, n): return window(xs, n, lambda w: sum(abs(x - sum(w) / n) for x in w) / n)


def smooth(xs, n, alpha):
    """sum := na(sum[1]) ? ta.sma(src, n) : alpha src + (1 - alpha) sum[1]."""
    s, out, prev = sma(xs, n), [], None
    for x, seed in zip(xs, s):
        v = seed if prev is None else (None if x is None else alpha * x + (1 - alpha) * prev)
        out.append(v)
        prev = v
    return out


def ema(xs, n): return smooth(xs, n, 2 / (n + 1))
def rma(xs, n): return smooth(xs, n, 1 / n)
def change(xs, k=1): return sub(xs, shift(xs, k))
def roc(xs, n): return mul(div(change(xs, n), shift(xs, n)), 100.0)


def tr(b, handle_na):
    h, l, pc = H(b), L(b), shift(C(b), 1)
    return [(hh - ll if handle_na else None) if p is None else max(hh - ll, abs(hh - p), abs(ll - p))
            for hh, ll, p in zip(h, l, pc)]


def atr(b, n): return rma(tr(b, True), n)


def rsi(xs, n):
    d = change(xs)
    ru, rd = rma(fmap(lambda x: max(x, 0.0), d), n), rma(fmap(lambda x: max(-x, 0.0), d), n)
    out = []
    for u, dn in zip(ru, rd):
        if na(u, dn):
            out.append(None)
        elif dn == 0:
            out.append(None if u == 0 else 100.0)
        else:
            out.append(100 - 100 / (1 + u / dn))
    return out


def stoch(src, hi, lo, n):
    return div(mul(sub(src, lowest(lo, n)), 100.0), sub(highest(hi, n), lowest(lo, n)))


def cum(xs):
    out, s = [], None
    for x in xs:
        s = None if x is None else nz(s) + x
        out.append(s)
    return out


def swma(xs):
    return [None if i < 3 or na(*xs[i - 3:i + 1]) else xs[i - 3] / 6 + xs[i - 2] / 3 + xs[i - 1] / 3 + xs[i] / 6
            for i in range(len(xs))]


def percentrank(xs, n):
    return [None if i < n or na(*xs[i - n:i + 1]) else 100.0 * sum(1 for j in range(i - n, i) if xs[j] <= xs[i]) / n
            for i in range(len(xs))]


def calc_slope(src, i, n):
    """The Linear Regression channel's calcSlope at bar i: [slope, average, intercept] with per = j + 1, j = 0 the newest."""
    sx = sy = sxx = sxy = 0.0
    for j in range(n):
        val, per = src[i - j], j + 1.0
        sx, sy, sxx, sxy = sx + per, sy + val, sxx + per * per, sxy + val * per
    slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    average = sy / n
    return slope, average, average - slope * sx / n + slope


def linreg(xs, n):
    return [None if i + 1 < n else calc_slope(xs, i, n)[2] for i in range(len(xs))]


def avg(*lists):
    return [None if na(*xs) else sum(xs) / len(xs) for xs in zip(*lists)]


def rows(**cols):
    """Per-bar dicts of the named columns; None where the first column is na."""
    first = next(iter(cols.values()))
    return [None if first[i] is None else {k: v[i] for k, v in cols.items()} for i in range(len(first))]


# ---- the Pine formulas, one per study ----
def ref_hma(b):
    c, n = C(b), 9
    return wma(sub(mul(wma(c, n // 2), 2.0), wma(c, n)), round(math.sqrt(n)))


def ref_dema(b):
    e1 = ema(C(b), 9)
    return sub(mul(e1, 2.0), ema(e1, 9))


def ref_smma(b):
    return rma(C(b), 7)


def ref_alma(b):
    c, n, offset, sigma = C(b), 9, 0.85, 6
    m, s, out = offset * (n - 1), n / sigma, []
    for i in range(len(c)):
        if i + 1 < n:
            out.append(None)
            continue
        norm = total = 0.0
        for j in range(n):
            w = math.exp(-1 * (j - m) ** 2 / (2 * s ** 2))
            norm += w
            total += c[i - (n - j - 1)] * w
        out.append(total / norm)
    return out


def ref_lsma(b):
    return linreg(C(b), 25)


def ref_mcginley(b):
    c, e, out, mg = C(b), ema(C(b), 14), [], None
    for x, seed in zip(c, e):
        mg = seed if mg is None else mg + (x - mg) / (14 * (x / mg) ** 4)
        out.append(mg)
    return out


def ref_kama(b):
    c, n, fa, sa = C(b), 14, 2 / 3, 2 / 31
    mom, vol = fmap(abs, change(c, n)), msum(fmap(abs, change(c)), n)
    out, prev = [], None
    for x, m, v in zip(c, mom, vol):
        er = None if na(m, v) else (m / v if v != 0 else 0.0)
        alpha = None if er is None else (er * (fa - sa) + sa) ** 2
        prev = None if alpha is None else alpha * x + (1 - alpha) * nz(prev, x)
        out.append(prev)
    return out


def ref_envelope(b):
    basis = sma(C(b), 20)
    return rows(mid=basis, up=mul(basis, 1.1), dn=mul(basis, 0.9))


def ref_stochrsi(b):
    r = rsi(C(b), 14)
    k = sma(stoch(r, r, r, 14), 3)
    return rows(k=k, d=sma(k, 3))


def bands(c, n, mult):
    basis, d = sma(c, n), mul(stdev(c, n), mult)
    return basis, add(basis, d), sub(basis, d)


def ref_bbpct(b):
    _, up, dn = bands(C(b), 20, 2.0)
    return div(sub(C(b), dn), sub(up, dn))


def ref_bbw(b):
    basis, up, dn = bands(C(b), 20, 2.0)
    return div(sub(up, dn), basis)


def ref_bbtrend(b):
    ms, us, ls = bands(C(b), 20, 2.0)
    _, ul, ll = bands(C(b), 50, 2.0)
    return mul(div(sub(fmap(abs, sub(ls, ll)), fmap(abs, sub(us, ul))), ms), 100.0)


def ref_sar(b):
    h, l, c, start, inc, mx = H(b), L(b), C(b), 0.02, 0.02, 0.2
    out, result, max_min, acc, below = [], None, None, None, False
    for i in range(len(c)):
        if i == 0:
            out.append(None)
            continue
        first = False
        if i == 1:
            if c[i] > c[i - 1]:
                below, max_min, result = True, h[i], l[i - 1]
            else:
                below, max_min, result = False, l[i], h[i - 1]
            first, acc = True, start
        result = result + acc * (max_min - result)
        if below:
            if result > l[i]:
                first, below, result, max_min, acc = True, False, max(h[i], max_min), l[i], start
        else:
            if result < h[i]:
                first, below, result, max_min, acc = True, True, min(l[i], max_min), h[i], start
        if not first:
            if below:
                if h[i] > max_min:
                    max_min, acc = h[i], min(acc + inc, mx)
            else:
                if l[i] < max_min:
                    max_min, acc = l[i], min(acc + inc, mx)
        if below:
            result = min(result, l[i - 1])
            if i > 1:
                result = min(result, l[i - 2])
        else:
            result = max(result, h[i - 1])
            if i > 1:
                result = max(result, h[i - 2])
        out.append(result)
    return out


def ref_chandelier(b):
    c, a = C(b), mul(atr(b, 22), 3.0)
    long0, short0 = sub(highest(c, 22), a), add(lowest(c, 22), a)
    out, lp, sp, dr = [], None, None, 1
    for i in range(len(c)):
        ls, ss, pc = long0[i], short0[i], c[i - 1] if i else None
        if ls is None:
            out.append(None)
            continue
        lp0, sp0 = nz(lp, ls), nz(sp, ss)
        if pc is not None and pc > lp0:
            ls = max(ls, lp0)
        if pc is not None and pc < sp0:
            ss = min(ss, sp0)
        dr = 1 if c[i] > sp0 else -1 if c[i] < lp0 else dr
        lp, sp = ls, ss
        out.append({"long": ls, "short": ss, "dir": dr})
    return out


def ref_vstop(b):
    c, a, t = C(b), atr(b, 20), tr(b, False)
    out, mx, mn, up, stop = [], None, None, True, None
    for i in range(len(c)):
        src = c[i]
        atrm = nz(None if a[i] is None else a[i] * 2.0, t[i])
        mx, mn = max(nz(mx, src), src), min(nz(mn, src), src)
        cand = None if atrm is None else (mx - atrm if up else mn + atrm)
        stop = nz(None if cand is None else (cand if stop is None else (max(stop, cand) if up else min(stop, cand))), src)
        new_up = src - stop >= 0.0
        if new_up != up:
            mx = mn = src
            stop = mx - atrm if new_up else mn + atrm
        up = new_up
        out.append({"stop": stop, "dir": 1 if up else -1})
    return out


def ref_chandekroll(b):
    a = atr(b, 10)
    return rows(short=highest(sub(highest(H(b), 10), a), 9), long=lowest(add(lowest(L(b), 10), a), 9))


def ref_ichimoku(b):
    def donchian(n):
        return avg(lowest(L(b), n), highest(H(b), n))
    conv, base = donchian(9), donchian(26)
    return rows(conv=conv, base=base, a=shift(avg(conv, base), 25), b=shift(donchian(52), 25))


def ref_alligator(b):
    x = hl2(b)
    jaw, teeth, lips = shift(rma(x, 13), 8), shift(rma(x, 8), 5), shift(rma(x, 5), 3)
    return rows(lips=lips, jaw=jaw, teeth=teeth)


def ref_fractals(b):
    h, l, n, out = H(b), L(b), 2, []

    def flag(src, i, up):
        def at(k):
            return src[i - k] if i - k >= 0 else None

        def lt(x, y):
            return not na(x, y) and (x < y if up else x > y)

        def le(x, y):
            return not na(x, y) and (x <= y if up else x >= y)
        p = at(n)
        down_frontier = all(lt(at(n - j), p) for j in range(1, n + 1))
        f0 = all(lt(at(n + j), p) for j in range(1, n + 1))
        f1 = all(le(at(n + 1), p) and lt(at(n + j + 1), p) for j in range(1, n + 1))
        f2 = all(le(at(n + 1), p) and le(at(n + 2), p) and lt(at(n + j + 2), p) for j in range(1, n + 1))
        f3 = all(le(at(n + 1), p) and le(at(n + 2), p) and le(at(n + 3), p) and lt(at(n + j + 3), p) for j in range(1, n + 1))
        f4 = all(le(at(n + 1), p) and le(at(n + 2), p) and le(at(n + 3), p) and le(at(n + 4), p) and lt(at(n + j + 4), p)
                 for j in range(1, n + 1))
        return down_frontier and (f0 or f1 or f2 or f3 or f4)
    for i in range(len(h)):
        v = {}
        if flag(h, i, True):
            v["up"] = h[i - n]
        if flag(l, i, False):
            v["dn"] = l[i - n]
        out.append(v or None)
    return out


def ref_cci(b):
    src = hlc3(b)
    return div(sub(src, sma(src, 20)), mul(dev(src, 20), 0.015))


def ref_wpr(b):
    mx, mn = highest(H(b), 14), lowest(L(b), 14)
    return div(mul(sub(C(b), mx), 100.0), sub(mx, mn))


def ref_mom(b): return change(C(b), 10)
def ref_roc(b): return roc(C(b), 9)
def ref_ao(b): return sub(sma(hl2(b), 5), sma(hl2(b), 34))
def ref_bop(b): return div(sub(C(b), O(b)), sub(H(b), L(b)))


def ref_bbp(b):
    e = ema(C(b), 13)
    return add(sub(H(b), e), sub(L(b), e))


def ref_cmo(b):
    mom = change(C(b))
    sm1 = msum([m if m is not None and m >= 0 else 0.0 for m in mom], 9)
    sm2 = msum([0.0 if m is not None and m >= 0 else (None if m is None else -m) for m in mom], 9)
    return div(mul(sub(sm1, sm2), 100.0), add(sm1, sm2))


def ref_connors(b):
    c = C(b)
    ud, prev = [], None
    for i, x in enumerate(c):
        p = c[i - 1] if i else None
        equal, growing = p is not None and x == p, p is not None and x > p
        prev = 0.0 if equal else ((1.0 if nz(prev) <= 0 else nz(prev) + 1) if growing else (-1.0 if nz(prev) >= 0 else nz(prev) - 1))
        ud.append(prev)
    return avg(rsi(c, 3), rsi(ud, 2), percentrank(roc(c, 1), 100))


def ref_fisher(b):
    x, hi, lo = hl2(b), highest(hl2(b), 9), lowest(hl2(b), 9)
    out, value, fish = [], None, None
    for i in range(len(x)):
        ratio = None if na(hi[i], lo[i]) or hi[i] == lo[i] else (x[i] - lo[i]) / (hi[i] - lo[i])
        if ratio is None:
            value = fish = None
            out.append(None)
            continue
        v = 0.66 * (ratio - 0.5) + 0.67 * nz(value)
        value = 0.999 if v > 0.99 else -0.999 if v < -0.99 else v
        prev = fish
        fish = 0.5 * math.log((1 + value) / (1 - value)) + 0.5 * nz(fish)
        out.append({"fisher": fish, "trigger": prev})
    return out


def po(src, key):
    p = mul(div(sub(ema(src, 12), ema(src, 26)), ema(src, 26)), 100.0)
    sig = ema(p, 9)
    return rows(**{key: p, "signal": sig, "hist": sub(p, sig)})


def ref_ppo(b): return po(C(b), "ppo")
def ref_pvo(b): return po(V(b), "pvo")


def ref_trix(b):
    return mul(change(ema(ema(ema(fmap(math.log, C(b)), 18), 18), 18)), 10000.0)


def tsi(src, short, long):
    pc = change(src)
    return mul(div(ema(ema(pc, long), short), ema(ema(fmap(abs, pc), long), short)), 100.0)


def ref_tsi(b):
    t = tsi(C(b), 13, 25)
    return rows(tsi=t, signal=ema(t, 13))


def ref_smi(b):
    erg = tsi(C(b), 5, 20)
    return rows(erg=erg, sig=ema(erg, 5))


def ref_smio(b):
    erg = tsi(C(b), 5, 20)
    return sub(erg, ema(erg, 5))


def ref_smindex(b):
    hh, ll = highest(H(b), 10), lowest(L(b), 10)

    def ema_ema(xs):
        return ema(ema(xs, 3), 3)
    smi = mul(div(ema_ema(sub(C(b), div(add(hh, ll), 2.0))), ema_ema(sub(hh, ll))), 200.0)
    return rows(smi=smi, ema=ema(smi, 3))


def ref_uo(b):
    pc = shift(C(b), 1)
    high_ = [None if p is None else max(h, p) for h, p in zip(H(b), pc)]
    low_ = [None if p is None else min(l, p) for l, p in zip(L(b), pc)]
    bp, tr_ = sub(C(b), low_), sub(high_, low_)

    def average(n):
        return div(msum(bp, n), msum(tr_, n))
    return div(mul(add(add(mul(average(7), 4.0), mul(average(14), 2.0)), average(28)), 100.0), 7.0)


def ref_rvgi(b):
    rvi = div(msum(swma(sub(C(b), O(b))), 10), msum(swma(sub(H(b), L(b))), 10))
    return rows(rvi=rvi, sig=swma(rvi))


def ref_rvi(b):
    sd, d = stdev(C(b), 10), change(C(b))
    upper = ema([None if s is None else (0.0 if x is not None and x <= 0 else s) for s, x in zip(sd, d)], 14)
    lower = ema([None if s is None else (0.0 if x is not None and x > 0 else s) for s, x in zip(sd, d)], 14)
    return mul(div(upper, add(upper, lower)), 100.0)


def ref_coppock(b):
    return wma(add(roc(C(b), 14), roc(C(b), 11)), 10)


def ref_kst(b):
    c = C(b)

    def smaroc(r, s):
        return sma(roc(c, r), s)
    kst = add(add(smaroc(10, 10), mul(smaroc(15, 10), 2.0)), add(mul(smaroc(20, 10), 3.0), mul(smaroc(30, 15), 4.0)))
    return rows(kst=kst, sig=sma(kst, 9))


def ref_dpo(b):
    return sub(C(b), shift(sma(C(b), 21), 21 // 2 + 1))


def ref_massindex(b):
    span = sub(H(b), L(b))
    return msum(div(ema(span, 9), ema(ema(span, 9), 9)), 10)


def ref_ulcer(b):
    hi = highest(C(b), 14)
    dd = div(mul(sub(C(b), hi), 100.0), hi)
    return fmap(math.sqrt, sma(fmap(lambda x: x * x, dd), 14))


def bars_of(src, n, want_high):
    """ta.highestbars / ta.lowestbars(src, n): minus the offset of the extreme, the newest of equals."""
    out = []
    for i in range(len(src)):
        if i + 1 < n:
            out.append(None)
            continue
        best = 0
        for k in range(1, n):
            if (src[i - k] > src[i - best]) if want_high else (src[i - k] < src[i - best]):
                best = k
        out.append(-best)
    return out


def ref_aroon(b):
    up = div(mul(add(bars_of(H(b), 15, True), 14.0), 100.0), 14.0)
    dn = div(mul(add(bars_of(L(b), 15, False), 14.0), 100.0), 14.0)
    return rows(up=up, dn=dn)


def ref_aroonosc(b):
    return [None if v is None else v["up"] - v["dn"] for v in ref_aroon(b)]


def ref_vortex(b):
    vmp = msum(fmap(abs, sub(H(b), shift(L(b), 1))), 14)
    vmm = msum(fmap(abs, sub(L(b), shift(H(b), 1))), 14)
    s = msum(atr(b, 1), 14)
    return rows(vip=div(vmp, s), vim=div(vmm, s))


def ref_chop(b):
    x = div(msum(atr(b, 1), 14), sub(highest(H(b), 14), lowest(L(b), 14)))
    return fmap(lambda v: 100 * math.log10(v) / math.log10(14), x)


def ref_rci(b):
    c, n, out = C(b), 10, []
    for i in range(len(c)):
        if i + 1 < n:
            out.append(None)
            continue
        d = 0.0
        for j in range(n):
            rank = 1 + sum(1 for k in range(n) if c[i - k] > c[i - j])
            d += ((j + 1) - rank) ** 2
        out.append((1 - 6 * d / (n * (n * n - 1))) * 100)
    return out


def ref_hv(b):
    return mul(stdev(fmap(math.log, div(C(b), shift(C(b), 1))), 10), 100 * math.sqrt(365))


def ref_obv(b):
    sign = fmap(lambda x: (x > 0) - (x < 0), change(C(b)))
    return cum(mul(sign, V(b)))


def ref_pvt(b):
    return cum(mul(div(change(C(b)), shift(C(b), 1)), V(b)))


def clv(b):
    return [0.0 if x.h == x.l else ((x.c - x.l) - (x.h - x.c)) / (x.h - x.l) for x in b]


def ref_adl(b):
    return cum(mul(clv(b), V(b)))


def ref_cmf(b):
    return div(msum(mul(clv(b), V(b)), 20), msum(V(b), 20))


def ref_chaikin(b):
    ad = ref_adl(b)
    return sub(ema(ad, 3), ema(ad, 10))


def ref_klinger(b):
    sv = [v if d is not None and d >= 0 else -v for d, v in zip(change(hlc3(b)), V(b))]
    kvo = sub(ema(sv, 34), ema(sv, 55))
    return rows(kvo=kvo, sig=ema(kvo, 13))


def ref_efi(b):
    return ema(mul(change(C(b)), V(b)), 13)


def ref_eom(b):
    return sma(div(mul(mul(change(hl2(b)), 10000.0), sub(H(b), L(b))), V(b)), 14)


def volume_index(b, down):
    c, v, out, x = C(b), V(b), [], None
    for i in range(len(c)):
        x = nz(x, 1000.0)
        if i and (v[i] < v[i - 1] if down else v[i] > v[i - 1]):
            x = x + (c[i] - c[i - 1]) / c[i - 1] * x
        out.append(x)
    return out


def ref_nvi(b): return volume_index(b, True)
def ref_pvi(b): return volume_index(b, False)


def ref_netvol(b):
    return [0.0 if d is None else (v if d > 0 else -v if d < 0 else 0.0) for d, v in zip(change(C(b)), V(b))]


def ref_zigzag(b):
    """TradingView's Zig Zag script, its pivots() and pivotFound() as written, over bar_index."""
    h, l, dev_threshold, length = H(b), L(b), 5.0, 10 // 2

    def pivots(src, i, is_high):
        p = nz(src[i - length] if i - length >= 0 else None)
        found = True
        for k in list(range(0, length)) + list(range(length + 1, 2 * length + 1)):
            x = src[i - k] if i - k >= 0 else None
            if x is not None and (x > p if is_high else x < p):
                found = False
        return (i - length, p) if found and length * 2 <= i else (None, None)

    def calc_dev(base, price):
        return None if base == 0 else 100 * (price - base) / abs(base)
    out, has_line, i_last, p_last, is_high_last = [], False, 0, 0.0, True
    for i in range(len(h)):
        ih, ph = pivots(h, i, True)
        il, pl = pivots(l, i, False)
        for found, is_high, idx, price in ((ih is not None, True, ih, ph), (il is not None, False, il, pl)):
            if not found:
                continue
            d = calc_dev(p_last, price)
            if is_high_last == is_high and has_line:
                if price > p_last if is_high else price < p_last:
                    i_last, p_last = idx, price
            elif not has_line or (d is not None and abs(d) >= dev_threshold):
                has_line, is_high_last, i_last, p_last = True, is_high, idx, price
        out.append({"px": p_last, "back": i - i_last, "dir": 1 if is_high_last else -1} if has_line else None)
    return out


def ref_median(b):
    return window(hl2(b), 3, lambda w: sorted(w)[math.ceil(0.5 * 3) - 1])


def ref_cog(b):
    c, n, out = C(b), 10, []
    for i in range(len(c)):
        if i + 1 < n:
            out.append(None)
            continue
        num = sum(c[i - j] * (j + 1) for j in range(n))
        out.append(-num / sum(c[i - n + 1:i + 1]))
    return out


def ref_corr(b):
    c, n = C(b), 14
    idx = [float(i) for i in range(len(c))]
    cov = sub(sma(mul(c, idx), n), mul(sma(c, n), sma(idx, n)))
    return div(cov, mul(stdev(c, n), stdev(idx, n)))


def ref_linreg(b):
    c, n, mult, out = C(b), 100, 2.0, []
    for i in range(len(c)):
        if i + 1 < n:
            out.append(None)
            continue
        slope, _, intercept = calc_slope(c, i, n)
        val, acc = intercept, 0.0
        for j in range(n):
            price = c[i - j] - val
            acc += price * price
            val += slope
        sd = math.sqrt(acc / (n - 1))
        out.append({"mid": intercept, "up": intercept + mult * sd, "dn": intercept - mult * sd})
    return out


REFS = {k[4:]: f for k, f in dict(globals()).items() if k.startswith("ref_")}


def same(a, b):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, dict) or isinstance(b, dict):
        return isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)


def test_every_study_has_a_reference():
    assert set(REFS) == set(PARAMS)


@pytest.mark.parametrize("seed", [7, 11])
@pytest.mark.parametrize("name", sorted(PARAMS))
def test_study_equals_its_pine_formula_at_every_bar(name, seed):
    bars = walk(400, seed)
    got, want = run(name, bars), REFS[name](bars)
    assert len(want) == len(bars)
    bad = [i for i in range(len(bars)) if not same(got[i], want[i])]
    assert not bad, (name, bad[:5], [(got[i], want[i]) for i in bad[:2]])
    assert sum(v is not None for v in got) > 50, name       # the formula produced values, not a long warm-up of None


def test_params_warm_and_prime_have_the_shape_make_tv_expects():
    for name, (cls, spec) in PARAMS.items():
        assert re.fullmatch(r"[a-z]+", name)
        assert issubclass(cls, _Study) and cls.__doc__, name
        for d, lo, hi in spec:
            assert isinstance(d, (int, float)) and lo <= d <= hi, name
        assert isinstance(study(name).state, tuple), name
        w = WARM[name]
        assert isinstance(w([]), int) and w([]) >= 0 and w(["x"]) == w([]), name
    assert set(WARM) == set(PARAMS) and set(PRIME) <= set(PARAMS)
    assert WARM["hma"](["20"]) == 40 and WARM["dema"](["9"]) == 90 and WARM["kst"]([]) == 54
    assert WARM["linreg"](["50", "2"]) == 50 and WARM["bop"]([]) == 0 and WARM["sar"]([]) == 400


def test_a_wire_key_arg_sets_the_length():
    bars = walk(80)
    assert run("mom", bars)[5] is None and run("mom", bars)[10] is not None
    s = study("mom", 5)
    got = [s.push(b) for b in bars]
    assert got[4] is None and math.isclose(got[5], bars[5].c - bars[0].c)
    s = study("smma", 3)
    assert [s.push(b) for b in bars][2] == pytest.approx(sum(b.c for b in bars[:3]) / 3)


@pytest.mark.parametrize("name", sorted(PARAMS))
def test_preview_never_commits(name):
    s, bars = study(name), walk(160)
    for b in bars[:150]:
        s.push(b)
    state = s.state
    a = s.preview(bars[150])
    assert same(s.preview(bars[150]), a) and s.state == state, name
    assert same(s.push(bars[150]), a), name


def test_values_are_floats_dicts_or_none():
    bars = walk(200)
    for name in PARAMS:
        for v in run(name, bars):
            if isinstance(v, dict):
                assert all(x is None or isinstance(x, (int, float)) for x in v.values()), name
            else:
                assert v is None or isinstance(v, (int, float)), name


def test_pine_edge_rules():
    flat = [mk(100.0, h=100.0, l=100.0, o=100.0, v=0) for _ in range(40)]
    assert run("bop", flat)[-1] is None                           # (c - o) / (h - l): x / 0 is na
    assert run("wpr", flat)[-1] is None and run("cci", flat)[-1] is None
    assert run("eom", flat)[-1] is None                           # volume 0 -> na inside the SMA window
    assert run("cmf", flat)[-1] is None and run("adl", flat)[-1] == 0.0
    assert run("stochrsi", flat)[-1] is None                      # rsi 0/0 is na, so its stoch is na
    assert run("connors", flat + walk(150))[-1] is not None
    up = [mk(100.0 + i, h=100.5 + i, l=99.5 + i, o=100.0 + i, v=10) for i in range(30)]
    assert run("sar", up)[0] is None and run("sar", up)[1] is not None
    assert run("sar", up)[-1] < up[-1].l and run("vstop", up)[-1]["dir"] == 1 and run("chandelier", up)[-1]["dir"] == 1
    assert run("netvol", up)[0] == 0.0 and run("obv", up)[0] is None and run("obv", up)[-1] == 290.0
    assert run("fractals", up)[-1] is None
    peak = up[:10] + [mk(130.0, h=140.0, l=109.0, o=110.0)] + [mk(100.0 - i, h=100.5 - i, l=99.5 - i, o=100.0 - i) for i in range(10)]
    assert run("fractals", peak)[12] == {"up": 140.0}            # known 2 bars after the peak, the mark is its high
