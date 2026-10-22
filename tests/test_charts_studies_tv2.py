"""TradingView's long-tail studies (studies_tv2.py): each equals its Pine formula, restated here over whole lists the way
Pine reads a series (None = na, src[k] = k bars back, a comparison with na is false, x / 0 is na), at every bar of a
random walk; PARAMS / WARM / PRIME have the shape studies_tv.make_tv expects; a preview never commits."""
from __future__ import annotations

import datetime as dt
import json
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
            out.append(100.0)                       # the RSI script's `down == 0 ? 100`: a flat series too (as RSI in studies_tv)
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
def hma_pine(c, n):
    """TradingView's built-in Hull MA (pine-facade STD;Hull%1MA v28, Pine v6): ta.wma(2 ta.wma(src, length / 2) - ta.wma(src,
    length), math.floor(math.sqrt(length))); length / 2 is cut to an int by ta.wma."""
    return wma(sub(mul(wma(c, n // 2), 2.0), wma(c, n)), math.floor(math.sqrt(n)))


def ref_hma(b):
    return hma_pine(C(b), 9)


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
    c, n, fa, sa = C(b), 10, 2 / 3, 2 / 31
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
    return mul(div(sub(up, dn), basis), 100.0)


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
    """ta.tsi: the raw ratio in [-1, 1]; only the TSI indicator scales it by 100, SMI Ergodic plots it as it is."""
    pc = change(src)
    return div(ema(ema(pc, long), short), ema(ema(fmap(abs, pc), long), short))


def ref_tsi(b):
    t = mul(tsi(C(b), 13, 25), 100.0)
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
    assert run("stochrsi", flat)[-1] is None                      # rsi is a flat 100, so its stoch is 0 / 0: na
    assert run("connors", flat + walk(150))[-1] is not None
    up = [mk(100.0 + i, h=100.5 + i, l=99.5 + i, o=100.0 + i, v=10) for i in range(30)]
    assert run("sar", up)[0] is None and run("sar", up)[1] is not None
    assert run("sar", up)[-1] < up[-1].l and run("vstop", up)[-1]["dir"] == 1 and run("chandelier", up)[-1]["dir"] == 1
    assert run("netvol", up)[0] == 0.0 and run("obv", up)[0] is None and run("obv", up)[-1] == 290.0
    assert run("fractals", up)[-1] is None
    peak = up[:10] + [mk(130.0, h=140.0, l=109.0, o=110.0)] + [mk(100.0 - i, h=100.5 - i, l=99.5 - i, o=100.0 - i) for i in range(10)]
    assert run("fractals", peak)[12] == {"up": 140.0}            # known 2 bars after the peak, the mark is its high


def test_ichimoku_lines_each_read_their_own_length_even_above_the_span():
    """The window was capped at the span, so a conversion or base length above it never produced a value
    (TradingView reads every line from its own length). A line that is ready shows even while another is still warming:
    conversion 20 / base 10 / span 30 draws the base from bar 9, not from bar 19 when the conversion fills."""
    bars = walk(400)
    for conv, base, span, disp in ((30, 26, 20, 26), (9, 60, 20, 26), (9, 26, 52, 26), (20, 10, 30, 1), (20, 30, 10, 5)):
        def donchian(n):
            return avg(lowest(L(bars), n), highest(H(bars), n))
        c, b = donchian(conv), donchian(base)
        cols = dict(conv=c, base=b, a=shift(avg(c, b), disp - 1), b=shift(donchian(span), disp - 1))
        want = [None if all(v[i] is None for v in cols.values()) else {k: v[i] for k, v in cols.items()} for i in range(len(bars))]
        s = study("ichimoku", conv, base, span, disp)
        got = [s.push(x) for x in bars]
        bad = [i for i in range(len(bars)) if not same(got[i], want[i])]
        assert not bad, ((conv, base, span), bad[:3], [(got[i], want[i]) for i in bad[:2]])
        assert got[-1] is not None and got[-1]["base"] is not None and got[-1]["a"] is not None
        assert WARM["ichimoku"]([str(conv), str(base), str(span), str(disp)]) == max(conv, base, span) + disp


def test_the_rsi_inside_stochrsi_and_connors_is_the_tv_rsi_study_even_on_a_flat_start():
    """tv:rsi said 100 on a flat series while the helper under stochrsi / connors said na: one rule now."""
    from homebase.charts.studies import make
    from homebase.charts.studies_tv2 import _RSI0, _rsi
    flat, moving = [mk(100.0) for _ in range(40)], walk(120)
    bars = flat + [mk(b.c, h=b.h, l=b.l, o=b.o, t=b.t) for b in moving]
    tv, st, got = make("tv:rsi:14"), _RSI0, []
    for b in bars:
        st, v = _rsi(st, b.c, 14)
        got.append(v)
    want = [tv.push(b) for b in bars]
    assert want[20] == 100.0 and want[39] == 100.0
    assert all(same(g, w) for g, w in zip(got, want)), [(i, g, w) for i, (g, w) in enumerate(zip(got, want)) if not same(g, w)][:3]
    assert run("connors", [mk(100.0) for _ in range(150)])[-1] == 100.0    # rsi(close, 3) is 100 on a flat start, not na


# ---- review round 2: Hull MA, SMI scale, zero closes, Ichimoku warm-up, linear-time windows, a measured WARM table ----
def test_hma_floors_the_square_root_like_tradingviews_built_in():
    """round(sqrt(n)) and floor(sqrt(n)) differ whenever sqrt(n) ends in .5 or more: n = 15 (4 vs 3) and 21 (5 vs 4);
    the default 9 (sqrt 3) cannot tell them apart."""
    bars = walk(200)
    for n in (15, 21):
        s = study("hma", n)
        got, want = [s.push(b) for b in bars], hma_pine(C(bars), n)
        bad = [i for i in range(len(bars)) if not same(got[i], want[i])]
        assert not bad and got[-1] is not None, (n, bad[:3])


def test_smi_ergodic_is_the_raw_tsi_ratio_and_only_tsi_is_times_100():
    bars = walk(300)
    a, b, o = study("tsi", 20, 5, 5), study("smi", 20, 5, 5), study("smio", 20, 5, 5)
    seen = 0
    for x in bars:
        t, m, d = a.push(x), b.push(x), o.push(x)
        if m is None:
            assert t is None and d is None
            continue
        seen += 1
        assert abs(m["erg"]) <= 1.0 and math.isclose(t["tsi"], 100.0 * m["erg"], rel_tol=1e-12, abs_tol=1e-12)
        assert (t["signal"] is None) == (m["sig"] is None) == (d is None)
        if d is not None:
            assert math.isclose(t["signal"], 100.0 * m["sig"], rel_tol=1e-12, abs_tol=1e-12) and math.isclose(d, m["erg"] - m["sig"])
    assert seen > 250


def test_mcginley_turns_a_zero_close_into_na_and_goes_on_from_the_ema_it_froze():
    """mg + (c - mg) / (n (c / mg)^4) divided by zero at a close of 0: Pine's x / 0 is na, and hub.py pushes study values with
    no try/except, so the crash left the bar-close handler. TradingView's script calls ta.ema only while mg[1] is na, so the
    bar after a na takes that EMA up from where it froze (the seed, bar n - 1), not from a fresh start: PineTS 0.12.1 running
    that source gives k close + (1 - k) seed there as well."""
    bars = walk(60)
    s = study("mcginley")
    for b in bars[:30]:
        s.push(b)
    zero = mk(0.0, h=0.0, l=0.0, o=0.0, t=bars[30].t)
    assert s.preview(zero) is None and s.push(zero) is None
    assert [study("mcginley").push(mk(0.0)) for _ in range(3)] == [None] * 3
    k, seed = 2 / 15, sum(C(bars[:14])) / 14
    mg = seed + k * (bars[31].c - seed)
    assert s.push(bars[31]) == pytest.approx(mg, rel=1e-12)
    for b in bars[32:]:                                       # then the plain recursion again
        mg = mg + (b.c - mg) / (14 * (b.c / mg) ** 4)
        assert s.push(b) == pytest.approx(mg, rel=1e-12)


@pytest.mark.parametrize("f", [0.3, 0.1, 0.01, 1e-5])
def test_mcginley_survives_a_crash_in_the_price_and_never_writes_inf(f):
    """(close / mg)^4 under 1 blows the step up (mg turns negative and grows): it overflows a float, or the line reaches inf, and
    json.dumps writes Infinity, which the client cannot parse. Both are na, and the EMA goes on after them."""
    bars = walk(200)
    bars[60] = mk(bars[60].c * f, t=bars[60].t)
    s = study("mcginley")
    got = [s.push(b) for b in bars]                           # no raise is the claim
    assert all(g is None or math.isfinite(g) for g in got)
    json.dumps(got, allow_nan=False)
    assert got[-1] is not None and abs(got[-1] - bars[-1].c) < 5          # back on the price once the EMA has seeded


def test_mcginley_survives_a_close_whose_fourth_power_is_past_a_float():
    bars = walk(80)
    bars[40] = mk(1e80, t=bars[40].t)                         # (1e80 / 100) ** 4 is past 1.8e308: Python raises OverflowError
    s = study("mcginley")
    got = [s.push(b) for b in bars]
    assert all(g is None or math.isfinite(g) for g in got) and got[-1] is not None


@pytest.mark.parametrize("name", sorted(PARAMS))
def test_a_zero_close_is_na_not_a_crash(name):
    """x / 0 and log(0) are na in Pine and hub.py pushes study values with no try/except: one bad close (a zero tick, a bad feed)
    must not raise. The bar after it has less (1) or more (100) volume than the zero bar (10): nvi and pvi look at that."""
    for where in (0, 30):
        for after in (1, 100):
            bars = walk(80)
            bars[where] = mk(0.0, h=0.0, l=0.0, o=0.0, v=10, t=bars[where].t)
            nxt = bars[where + 1]
            bars[where + 1] = mk(nxt.c, h=nxt.h, l=nxt.l, o=nxt.o, v=after, t=nxt.t)
            s = study(name)
            for b in bars[:where]:
                s.push(b)
            s.preview(bars[where])
            for b in bars[where:]:
                s.push(b)                                    # no raise is the claim


def _bad_feeds():
    """Feeds a broken tick source can produce: a run of zero bars, a dead feed, no volume, a close that falls to a fraction
    of the price or jumps past a float."""
    def with_bar(i, f, **kw):
        bars = walk(120, 2)
        b = bars[i]
        bars[i] = mk(b.c * f, h=b.h * f, l=b.l * f, o=b.o * f, v=kw.get("v", b.v), t=b.t)
        return bars
    run = walk(120, 2)
    for i in range(30, 70):
        run[i] = mk(0.0, v=10, t=run[i].t)
    yield "zero_run", run
    yield "all_zero", [mk(0.0, v=10, t=i) for i in range(120)]
    yield "no_volume", [mk(b.c, h=b.h, l=b.l, o=b.o, v=0, t=b.t) for b in walk(120, 2)]
    for f in (0.3, 0.1, 0.01):
        yield f"falls_to_{f}", with_bar(60, f)
    yield "jumps_to_1e80", with_bar(60, 1e78)                  # (close / mg) ** 4 passes a float


@pytest.mark.parametrize("name", sorted(PARAMS))
def test_a_bad_feed_never_raises_and_never_writes_a_non_finite_number(name):
    """hub.py pushes study values with no try/except and server.py writes them with json.dumps, which turns inf / nan into
    Infinity / NaN, and the client's JSON.parse stops on those: a study gives a finite number or na for any bar it is fed."""
    for label, bars in _bad_feeds():
        s = study(name)
        for b in bars:
            s.preview(b)
            json.dumps(s.push(b), allow_nan=False)


def test_ichimoku_shows_a_ready_line_while_the_conversion_line_is_still_warming():
    s = study("ichimoku", 20, 10, 30, 1)
    got = [s.push(b) for b in walk(40)]
    assert got[8] is None and got[9]["conv"] is None and got[9]["base"] is not None      # base is ready at bar 9, conv at bar 19
    assert got[19]["conv"] is not None and got[29]["b"] is not None


def test_alligator_shows_a_ready_line_while_the_longest_one_is_still_warming():
    """Like Ichimoku: the lips line (30 bars) is the last to fill, and the jaw (5 bars, shown 3 later) was hidden until it did."""
    bars = walk(80)
    x, args = hl2(bars), (5, 8, 30, 3, 5, 3)
    cols = dict(jaw=shift(rma(x, 5), 3), teeth=shift(rma(x, 8), 5), lips=shift(rma(x, 30), 3))
    want = [None if all(v[i] is None for v in cols.values()) else {k: v[i] for k, v in cols.items()} for i in range(len(bars))]
    s = study("alligator", *args)
    got = [s.push(b) for b in bars]
    assert [i for i in range(len(bars)) if not same(got[i], want[i])] == []
    assert got[6] is None and got[7]["jaw"] is not None and got[7]["teeth"] is None and got[7]["lips"] is None
    assert got[-1]["lips"] is not None


def _ulcer_brute(c, m):
    """The old O(n^2) per bar Ulcer Index, restated: every one of the m trailing windows rescanned for its highest close."""
    out = []
    for i in range(len(c)):
        if i + 1 < 2 * m - 1:
            out.append(None)
            continue
        w = c[i - 2 * m + 2:i + 1]
        if any(max(w[j:j + m]) == 0 for j in range(m)):          # 0 / 0: na, and na in any term of the sma is na
            out.append(None)
            continue
        dd = [(100.0 * (w[j + m - 1] - max(w[j:j + m])) / max(w[j:j + m])) ** 2 for j in range(m)]
        out.append(math.sqrt(sum(dd) / len(dd)))
    return out


def _rci_brute(c, n):
    """The old O(n^2) per bar Rank Correlation Index: the price rank of each close counted by scanning the window."""
    out = []
    for i in range(len(c)):
        if i + 1 < n:
            out.append(None)
            continue
        w = c[i - n + 1:i + 1]
        d = sum(((n - j) - (1 + sum(1 for y in w if y > x))) ** 2 for j, x in enumerate(w))
        out.append((1 - 6.0 * d / (n * (n * n - 1))) * 100.0)
    return out


def _ties(n=500, seed=5):
    """Closes on a handful of price levels, so highs and ranks tie constantly."""
    r = random.Random(seed)
    return [mk(float(r.randint(1, 6))) for _ in range(n)]


@pytest.mark.parametrize("n", [2, 5, 14, 60])
def test_ulcer_equals_the_rescanning_definition(n):
    for bars in (walk(400, 3), _ties()):
        s = study("ulcer", n)
        assert [s.push(b) for b in bars] == _ulcer_brute(C(bars), n)


@pytest.mark.parametrize("n", [3, 14])
def test_ulcer_is_na_while_a_window_is_all_zero_and_equals_the_definition_after_it(n):
    """A window of n closes at 0 has a highest of 0: dd = 100 (c - 0) / 0 is na, and so is the sma of it (a run of n zero
    closes, or a dead feed, raised ZeroDivisionError out of the bar-close handler)."""
    bars = walk(150, 3)
    lo, hi = 30, 30 + 2 * n                                   # the zero run, bars lo .. hi - 1, longer than a window
    for i in range(lo, hi):
        bars[i] = mk(0.0, t=bars[i].t)
    s = study("ulcer", n)
    got = [s.push(b) for b in bars]                           # no raise is the claim
    dead = range(lo + n - 1, hi + n - 1)                      # some window of the 2 n - 1 closes sits wholly inside the run
    assert [k for k, g in enumerate(got) if g is None and k >= 2 * n - 2] == list(dead)
    want = _ulcer_brute(C(bars), n)
    assert got == want
    assert [study("ulcer", n).push(mk(0.0)) for _ in range(4 * n)][-1] is None


class _Counted(float):
    """A close that counts the comparisons made with it: a test can tell O(n) a bar from O(n^2) without a clock."""
    seen = 0

    def __lt__(self, other):
        _Counted.seen += 1
        return float.__lt__(self, other)

    def __gt__(self, other):
        _Counted.seen += 1
        return float.__gt__(self, other)


@pytest.mark.parametrize("name", ["ulcer", "rci"])
def test_a_long_window_costs_far_fewer_than_n_squared_comparisons_a_bar(name):
    """tv:ulcer:500 and tv:rci:500 took 1-3 ms a bar when each bar rescanned its window per close (n^2), 20-60 s over a long
    history, and add_study runs on the event loop. Equal values (the tests above) cannot tell, and a clock is flaky: count."""
    n, last = 200, 30
    bars = [mk(_Counted(b.c), t=b.t) for b in walk(2 * n + last, 4)]
    s = study(name, n)
    for b in bars[:-last]:
        s.push(b)
    _Counted.seen = 0
    for b in bars[-last:]:
        s.push(b)
    per_bar = _Counted.seen / last
    assert 0 < per_bar < n * n / 4, per_bar                   # the scan did n^2 = 40000; sorted + bisect and two running maxima ~ 1e3


@pytest.mark.parametrize("n", [2, 3, 10, 61])
def test_rci_equals_the_scanning_definition(n):
    for bars in (walk(400, 3), _ties()):
        s = study("rci", n)
        assert [s.push(b) for b in bars] == _rci_brute(C(bars), n)


# ---- WARM is MEASURED: a study cold-started at a join against the same study run from the first bar ----
def _leaves(v):
    return {} if v is None else v if isinstance(v, dict) else {"": v}


def dependence(name, args, bars, cut, tol=1e-3, horizon=None):
    """Bars after a join that a study's value still depends on: run it from bar 0 and cold-started at `cut` (what a chart's own
    study does at its first bar), and return the last bar after the cut (+ 1) where the cold run is missing a value the full
    run has, or differs from it by more than `tol` x that line's own deviation. 1e-3 is where a 5 n EMA tail (e^-10) sits."""
    s, c = study(name, *args), study(name, *args)
    full = [s.push(b) for b in bars]
    cold = [c.push(b) for b in bars[cut:cut + horizon if horizon else None]]
    sd = {}
    for k in {k for v in full for k in _leaves(v)}:
        xs = [_leaves(v)[k] for v in full if _leaves(v).get(k) is not None]
        m = sum(xs) / len(xs)
        sd[k] = math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs)) or 1.0
    last = -1
    for i, v in enumerate(cold):
        f, g = _leaves(full[cut + i]), _leaves(v)
        for k in f.keys() | g.keys():
            a, b = f.get(k), g.get(k)
            if (a is None) != (b is None) or (a is not None and abs(a - b) > tol * sd[k]):
                last = i
                break
    return last + 1


# every study with a finite memory, by arg sets (wire-key order) that put the LONGEST length where the table did not look
MEASURED = {name: [()] for name in PARAMS}
for _name in ("obv", "pvt", "adl", "nvi", "pvi"):
    del MEASURED[_name]                      # a running sum remembers every bar: no finite WARM, see the next test
MEASURED.update({
    "bbtrend": [(), (100, 10, 2.0), (10, 100, 2.0)],
    "ao": [(), (60, 5), (5, 60)],
    "alligator": [(), (13, 60, 5, 8, 5, 3), (13, 8, 60, 8, 5, 3), (5, 8, 13, 3, 5, 40), (5, 8, 30, 3, 5, 3),
                  (5, 5, 5, 100, 0, 0), (5, 5, 5, 0, 100, 0), (5, 5, 5, 0, 0, 100)],      # short lengths, one long offset each
    "ppo": [(), (100, 26, 9), (12, 80, 9), (12, 26, 60), (100, 99, 3)],          # a difference of two EMAs is 6 n, the near-equal ones show it
    "pvo": [(), (100, 26, 9), (12, 80, 9), (12, 26, 60), (69, 66, 3), (85, 84, 5)],
    "uo": [(), (42, 7, 14), (7, 42, 28), (7, 14, 60)],
    "rvgi": [(), (5,), (30,)],
    "coppock": [(), (10, 40, 11), (10, 14, 50), (30, 14, 11)],
    "kst": [(), (50, 15, 20, 30, 10, 10, 10, 15, 9), (10, 15, 60, 30, 10, 10, 10, 15, 9), (10, 15, 20, 30, 10, 10, 80, 15, 9),
            (10, 15, 20, 30, 10, 10, 10, 15, 60)],
    "chaikin": [(), (100, 10), (10, 3), (30, 31), (40, 41), (45, 44)],
    "klinger": [(), (100, 55, 13), (34, 10, 13), (34, 55, 80), (56, 55, 3), (60, 59, 3)],
})


@pytest.mark.parametrize("name,args", [(n, a) for n, sets in sorted(MEASURED.items()) for a in sets], ids=lambda x: str(x).replace(" ", ""))
def test_warm_covers_the_measured_dependence(name, args):
    bars = walk(2400, 7)
    want = dependence(name, args, bars, 800)
    got = WARM[name]([str(a) for a in args])
    assert got >= want, f"tv:{name}{args}: the repair covers {got} bars after a join but the value still depends on {want}"


@pytest.mark.parametrize("n", [2, 3])
def test_fractals_warm_covers_the_equal_bar_skip(n):
    """On tick-quantised bars (equal highs and lows) a mark can hang on bars up to 2n + 4 back; a random walk never shows that."""
    r, px, bars = random.Random(3), 100.0, []
    for i in range(1500):
        o = px
        px = round((px + r.uniform(-1.5, 1.5)) * 4) / 4
        bars.append(mk(px, h=max(o, px) + r.randint(0, 2) * 0.25, l=min(o, px) - r.randint(0, 2) * 0.25, o=o, t=i))
    worst = max(dependence("fractals", (n,), bars, cut, horizon=40) for cut in range(100, 500))
    assert 2 * n < worst <= WARM["fractals"]([str(n)]) == 2 * n + 4


def test_a_running_sum_asks_for_all_the_history_the_hub_will_repair_and_netvol_for_one_bar():
    """obv / pvt / adl / nvi / pvi add up across every bar, so no finite WARM is exact: they ask for the most the hub repairs
    (HISTORY_MAX; it clamps anything bigger). netvol looks one bar back: its first bar after a join is -/+ volume, not 0."""
    from homebase.charts.hub import HISTORY_MAX, warm_bars
    for name in ("obv", "pvt", "adl", "nvi", "pvi"):
        assert WARM[name]([]) == HISTORY_MAX == warm_bars(f"tv:{name}"), name
    assert WARM["netvol"]([]) == 1 == warm_bars("tv:netvol")
    assert warm_bars("tv:rvgi") == 15 and warm_bars("tv:fractals") == 8


# ---- review round 3: two defaults / scales that were off against TradingView's own built-ins ----
def test_bbw_is_a_percent_of_the_middle_line_like_tradingviews_bandwidth():
    """STD;Bollinger_Bands_Width: bbw = ((upper - lower) / basis) * 100. Closes alternating 99 / 101 over 20 bars: basis 100, stdev 1,
    bands 100 +- 2, so the width is 4 (percent), not 0.04."""
    s = study("bbw")
    got = [s.push(mk(99.0 if i % 2 else 101.0)) for i in range(20)]
    assert got[18] is None and got[19] == pytest.approx(4.0)


def test_kama_defaults_to_tradingviews_er_length_10_in_every_copy():
    """STD;Kaufmans_Adaptive_Moving_Average: erLenInput = input.int(10, "ER length", 1), fast 2, slow 30."""
    from homebase.charts import studies
    from homebase.charts.studies_tv2 import KAMA
    assert [d for d, _, _ in PARAMS["kama"][1]] == [10, 2, 30]
    assert KAMA().n == studies.make("tv:kama").n == 10
    assert WARM["kama"]([]) == 10 + 5 * 30 and WARM["kama"](["20"]) == 20 + 5 * 30
