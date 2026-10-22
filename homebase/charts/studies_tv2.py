"""TradingView's long tail of built-in studies, each in Pine's own math with TradingView's default inputs, so a line
here is the line TradingView draws for the same bars. Pure; the Study contract of studies.py (push / preview, immutable
tuple state, None while warming up). Dispatched under the "tv:" namespace by studies_tv.make_tv, which merges PARAMS,
WARM and PRIME from here. Every class docstring is the Pine formula in one line; a value that TradingView shows
displaced (Ichimoku's cloud, the Alligator's lines) is given AS SHOWN UNDER THIS BAR.

Pine's rules kept throughout: ta.ema / ta.rma are na until `n` values exist, seed with their SMA at bar n-1, and an
na input makes them na (then they re-seed); a comparison with na is false; x / 0 is na; a window with an na in it is na;
ta.tr(true) is high - low on the first bar, ta.tr is na there.
"""
from __future__ import annotations

import math

from .studies_ta import _Study


# ---- Pine's building blocks, as pure functions on immutable state ----
def _push(w, x, n):
    return (w + (x,))[-n:]


def _full(w, n):
    return len(w) == n and None not in w


def _mean(w):
    return sum(w) / len(w)


def _sd(w):
    """ta.stdev, biased (population) as Pine's default."""
    m = _mean(w)
    return math.sqrt(sum((x - m) ** 2 for x in w) / len(w))


def _wma(w):
    """ta.wma: weights 1 .. n, the newest heaviest."""
    n = len(w)
    return sum(x * (i + 1) for i, x in enumerate(w)) / (n * (n + 1) / 2)


def _div(a, b):
    return None if a is None or b is None or b == 0 else a / b


def _sub(a, b):
    return None if a is None or b is None else a - b


def _ma(st, x, n, k):
    """One step of ta.ema (k = 2/(n+1)) or ta.rma (k = 1/n): sum := na(sum[1]) ? ta.sma(src, n) : k src + (1-k) sum[1]."""
    w, e = st
    w = _push(w, x, n)
    if e is None:
        e = _mean(w) if _full(w, n) else None
    elif x is None:
        e = None
    else:
        e += k * (x - e)
    return (w, e), e


def _k(n):
    return 2.0 / (n + 1)


def _delay(q, x, k):
    """x as it was k bars ago (a plot with offset = k, read under this bar); None before k bars."""
    q = _push(q, x, k + 1)
    return q, (q[0] if len(q) == k + 1 else None)


def _tr(bar, pc):
    """ta.tr(true): high - low on the first bar."""
    return bar.h - bar.l if pc is None else max(bar.h - bar.l, abs(bar.h - pc), abs(bar.l - pc))


def _rsi(st, x, n):
    """One step of ta.rsi: 100 - 100 / (1 + rma(up, n) / rma(down, n)); down = 0 -> 100, up = 0 -> 0, both 0 -> na."""
    px, su, sd = st
    d = None if px is None or x is None else x - px
    u, dn = (None, None) if d is None else (max(d, 0.0), max(-d, 0.0))
    su, ru = _ma(su, u, n, 1.0 / n)
    sd, rd = _ma(sd, dn, n, 1.0 / n)
    if ru is None or rd is None:
        v = None
    elif rd == 0:
        v = None if ru == 0 else 100.0
    else:
        v = 100.0 - 100.0 / (1.0 + ru / rd)
    return (x, su, sd), v


_RSI0 = (None, ((), None), ((), None))


def _hl2(bar):
    return (bar.h + bar.l) / 2.0


def _hlc3(bar):
    return (bar.h + bar.l + bar.c) / 3.0


def _fit(w):
    """The least-squares line through a window (oldest first): its value at the newest bar (ta.linreg(src, n, 0)) and
    the deviation of the window around it, sqrt(sum of squares / (n - 1)) as the Linear Regression channel's."""
    n = len(w)
    xm, ym = (n - 1) / 2.0, _mean(w)
    sxx = sum((i - xm) ** 2 for i in range(n))
    b = sum((i - xm) * (y - ym) for i, y in enumerate(w)) / sxx
    res = sum((y - (ym + b * (i - xm))) ** 2 for i, y in enumerate(w))
    return ym + b * (n - 1 - xm), math.sqrt(res / (n - 1))


class _Closes(_Study):
    """A study of a window of closes: `value(window)` once n closes exist."""

    def __init__(self, n):
        self.n = int(n)
        super().__init__()

    def step(self, w, bar):
        w = _push(w, bar.c, self.n)
        return w, (self.value(w) if len(w) == self.n else None)


# ---- moving averages ----
class HMA(_Closes):
    """ta.hma(close, 9) = wma(2 wma(src, n/2) - wma(src, n), round(sqrt(n))); n/2 is Pine's integer division."""

    def __init__(self, n: int = 9):
        super().__init__(n)
        self.h, self.s = self.n // 2, round(math.sqrt(self.n))

    def initial(self):
        return ((), ())   # closes, the inner series

    def step(self, st, bar):
        w, d = st
        w = _push(w, bar.c, self.n)
        d = _push(d, (2 * _wma(w[-self.h:]) - _wma(w)) if len(w) == self.n else None, self.s)
        return (w, d), (_wma(d) if _full(d, self.s) else None)


class DEMA(_Study):
    """DEMA(9): 2 e1 - ta.ema(e1, n), e1 = ta.ema(close, n)."""

    def __init__(self, n: int = 9):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return (((), None), ((), None))

    def step(self, st, bar):
        s1, e1 = _ma(st[0], bar.c, self.n, _k(self.n))
        s2, e2 = _ma(st[1], e1, self.n, _k(self.n))
        return (s1, s2), (None if e2 is None else 2 * e1 - e2)


class SMMA(_Study):
    """Smoothed MA(7): ta.rma(close, n), the SMA of the first n as the seed."""

    def __init__(self, n: int = 7):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return ((), None)

    def step(self, st, bar):
        return _ma(st, bar.c, self.n, 1.0 / self.n)


class ALMA(_Closes):
    """ta.alma(close, 9, 0.85, 6): weights exp(-(i - offset (n-1))^2 / (2 (n / sigma)^2)), i = 0 the oldest, normalised."""

    def __init__(self, n: int = 9, offset: float = 0.85, sigma: float = 6.0):
        super().__init__(n)
        m, s = float(offset) * (self.n - 1), self.n / float(sigma)
        self.w = tuple(math.exp(-((i - m) ** 2) / (2 * s * s)) for i in range(self.n))

    def value(self, w):
        return sum(x * k for x, k in zip(w, self.w)) / sum(self.w)


class LSMA(_Closes):
    """Least Squares MA: ta.linreg(close, 25, 0), the regression line's value at this bar."""

    def __init__(self, n: int = 25):
        super().__init__(n)

    def value(self, w):
        return _fit(w)[0]


class McGinley(_Study):
    """McGinley Dynamic(14): mg := na(mg[1]) ? ta.ema(close, n) : mg[1] + (close - mg[1]) / (n pow(close / mg[1], 4))."""

    def __init__(self, n: int = 14):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return (((), None), None)   # the EMA (until the seed), mg

    def step(self, st, bar):
        es, mg = st
        if mg is None:
            es, mg = _ma(es, bar.c, self.n, _k(self.n))
        else:
            mg = mg + (bar.c - mg) / (self.n * (bar.c / mg) ** 4)
        return (es, mg), mg


class KAMA(_Study):
    """KAMA(14, 2, 30): er = |change(src, n)| / sum(|change(src)|, n); alpha = (er (2/(fast+1) - 2/(slow+1)) + 2/(slow+1))^2;
    kama := alpha src + (1 - alpha) nz(kama[1], src)."""

    def __init__(self, n: int = 14, fast: int = 2, slow: int = 30):
        self.n, self.fa, self.sa = int(n), _k(int(fast)), _k(int(slow))
        super().__init__()

    def initial(self):
        return ((), None)   # the last n + 1 closes, kama

    def step(self, st, bar):
        w, kama = st
        w = _push(w, bar.c, self.n + 1)
        if len(w) <= self.n:
            return (w, kama), None
        vol = sum(abs(b - a) for a, b in zip(w, w[1:]))
        er = abs(w[-1] - w[0]) / vol if vol != 0 else 0.0
        a = (er * (self.fa - self.sa) + self.sa) ** 2
        kama = bar.c if kama is None else a * bar.c + (1 - a) * kama
        return (w, kama), kama


class Envelope(_Closes):
    """Envelope(20, 10 %): basis = ta.sma(close, n); upper = basis (1 + p/100), lower = basis (1 - p/100)."""

    def __init__(self, n: int = 20, pct: float = 10.0):
        super().__init__(n)
        self.p = float(pct) / 100.0

    def value(self, w):
        m = _mean(w)
        return {"mid": m, "up": m * (1 + self.p), "dn": m * (1 - self.p)}


# ---- bands and stops ----
class StochRSI(_Study):
    """Stoch RSI(14, 14, 3, 3): k = sma(stoch(rsi, rsi, rsi, n_stoch), smooth_k), d = sma(k, smooth_d), rsi = ta.rsi(close, n_rsi)."""

    def __init__(self, n_rsi: int = 14, n_stoch: int = 14, k: int = 3, d: int = 3):
        self.nr, self.ns, self.sk, self.sd = int(n_rsi), int(n_stoch), int(k), int(d)
        super().__init__()

    def initial(self):
        return (_RSI0, (), (), ())   # rsi, rsi window, raw stoch window, k window

    def step(self, st, bar):
        rs, w, raw, ks = st
        rs, r = _rsi(rs, bar.c, self.nr)
        w = _push(w, r, self.ns)
        x = None
        if _full(w, self.ns):
            hi, lo = max(w), min(w)
            x = _div(100.0 * (r - lo), hi - lo)
        raw = _push(raw, x, self.sk)
        k = _mean(raw) if _full(raw, self.sk) else None
        ks = _push(ks, k, self.sd)
        return (rs, w, raw, ks), (None if k is None else {"k": k, "d": _mean(ks) if _full(ks, self.sd) else None})


class BBPct(_Closes):
    """BB %B(20, 2): (close - lower) / (upper - lower), bands = sma +/- mult stdev."""

    def __init__(self, n: int = 20, mult: float = 2.0):
        super().__init__(n)
        self.m = float(mult)

    def value(self, w):
        sd = self.m * _sd(w)
        return _div(w[-1] - (_mean(w) - sd), 2 * sd)


class BBW(_Closes):
    """BB Width(20, 2): (upper - lower) / basis."""

    def __init__(self, n: int = 20, mult: float = 2.0):
        super().__init__(n)
        self.m = float(mult)

    def value(self, w):
        return _div(2 * self.m * _sd(w), _mean(w))


class BBTrend(_Study):
    """BBTrend(20, 50, 2): (|lowerS - lowerL| - |upperS - upperL|) / midS * 100, the short and long Bollinger bands."""

    def __init__(self, short: int = 20, long: int = 50, mult: float = 2.0):
        self.s, self.l, self.m = int(short), int(long), float(mult)
        super().__init__()

    def step(self, w, bar):
        w = _push(w, bar.c, max(self.s, self.l))
        if len(w) < max(self.s, self.l):
            return w, None
        ws, wl = w[-self.s:], w[-self.l:]
        ms, ml = _mean(ws), _mean(wl)
        ds, dl = self.m * _sd(ws), self.m * _sd(wl)
        return w, _div((abs((ms - ds) - (ml - dl)) - abs((ms + ds) - (ml + dl))) * 100.0, ms)


class SAR(_Study):
    """ta.sar(0.02, 0.02, 0.2), Pine's reference implementation: the trend starts on bar 1 from close vs close[1], the
    stop steps by acceleration x (extreme - stop), flips through the price, and never enters the last two bars' range."""

    def __init__(self, start: float = 0.02, inc: float = 0.02, mx: float = 0.2):
        self.start, self.inc, self.mx = float(start), float(inc), float(mx)
        super().__init__()

    def initial(self):
        return (0, None, None, None, None, None, None, None, None, False)   # bars seen, h1, l1, c1, h2, l2, sar, extreme, acc, below

    def step(self, st, bar):
        i, h1, l1, c1, h2, l2, r, mm, acc, below = st
        h, l, c = bar.h, bar.l, bar.c
        if i == 0:
            return (1, h, l, c, None, None, None, None, None, False), None
        first = False
        if i == 1:
            below, mm, r = (True, h, l1) if c > c1 else (False, l, h1)
            first, acc = True, self.start
        r = r + acc * (mm - r)
        if below:
            if r > l:
                first, below, r, mm, acc = True, False, max(h, mm), l, self.start
        elif r < h:
            first, below, r, mm, acc = True, True, min(l, mm), h, self.start
        if not first:
            if below and h > mm:
                mm, acc = h, min(acc + self.inc, self.mx)
            elif not below and l < mm:
                mm, acc = l, min(acc + self.inc, self.mx)
        if below:
            r = min(r, l1) if i == 1 else min(r, l1, l2)
        else:
            r = max(r, h1) if i == 1 else max(r, h1, h2)
        return (i + 1, h, l, c, h1, l1, r, mm, acc, below), r


class Chandelier(_Study):
    """Chandelier Exit(22, 3, close extremes): long = highest(close, n) - mult atr(n), ratcheted up while close[1] > its
    previous value; short = lowest(close, n) + mult atr(n) mirrored; dir := close > short[1] ? 1 : close < long[1] ? -1 : dir."""

    def __init__(self, n: int = 22, mult: float = 3.0):
        self.n, self.m = int(n), float(mult)
        super().__init__()

    def initial(self):
        return (None, ((), None), (), None, None, 1)   # prev close, ATR, closes, long stop, short stop, dir

    def step(self, st, bar):
        pc, a, w, lp, sp, dr = st
        a, atr = _ma(a, _tr(bar, pc), self.n, 1.0 / self.n)
        w = _push(w, bar.c, self.n)
        if atr is None:
            return (bar.c, a, w, None, None, dr), None
        ls, ss = max(w) - self.m * atr, min(w) + self.m * atr
        lp0, sp0 = (ls if lp is None else lp), (ss if sp is None else sp)
        if pc is not None and pc > lp0:
            ls = max(ls, lp0)
        if pc is not None and pc < sp0:
            ss = min(ss, sp0)
        dr = 1 if bar.c > sp0 else -1 if bar.c < lp0 else dr
        return (bar.c, a, w, ls, ss, dr), {"long": ls, "short": ss, "dir": dr}


class VStop(_Study):
    """Volatility Stop(20, 2): atrM = nz(atr(n) mult, ta.tr); max/min of close since the flip; stop := nz(up ? max(stop,
    max - atrM) : min(stop, min + atrM), close); up := close - stop >= 0; on a flip the extremes and stop restart."""

    def __init__(self, n: int = 20, mult: float = 2.0):
        self.n, self.m = int(n), float(mult)
        super().__init__()

    def initial(self):
        return (None, ((), None), None, None, True, None)   # prev close, ATR, max, min, uptrend, stop

    def step(self, st, bar):
        pc, a, mx, mn, up, stop = st
        a, atr = _ma(a, _tr(bar, pc), self.n, 1.0 / self.n)
        atrm = atr * self.m if atr is not None else (None if pc is None else _tr(bar, pc))
        src = bar.c
        mx, mn = (src if mx is None else max(mx, src)), (src if mn is None else min(mn, src))
        if atrm is None:
            stop = src
        else:
            cand = mx - atrm if up else mn + atrm
            stop = cand if stop is None else (max(stop, cand) if up else min(stop, cand))
        up2 = src - stop >= 0
        if up2 != up:
            mx = mn = src
            stop = mx - atrm if up2 else mn + atrm
        return (bar.c, a, mx, mn, up2, stop), {"stop": stop, "dir": 1 if up2 else -1}


class ChandeKroll(_Study):
    """Chande Kroll Stop(10, 1, 9): short = highest(highest(high, p) - x atr(p), q), long = lowest(lowest(low, p) + x atr(p), q)."""

    def __init__(self, p: int = 10, x: float = 1.0, q: int = 9):
        self.p, self.x, self.q = int(p), float(x), int(q)
        super().__init__()

    def initial(self):
        return (None, ((), None), (), (), ())   # prev close, ATR, (h, l) window, first high stops, first low stops

    def step(self, st, bar):
        pc, a, hl, hs, ls = st
        a, atr = _ma(a, _tr(bar, pc), self.p, 1.0 / self.p)
        hl = _push(hl, (bar.h, bar.l), self.p)
        ok = atr is not None and len(hl) == self.p
        hs = _push(hs, max(h for h, _ in hl) - self.x * atr if ok else None, self.q)
        ls = _push(ls, min(l for _, l in hl) + self.x * atr if ok else None, self.q)
        new = (bar.c, a, hl, hs, ls)
        if not _full(hs, self.q):
            return new, None
        return new, {"short": max(hs), "long": min(ls)}


class Ichimoku(_Study):
    """Ichimoku(9, 26, 52, 26): conv = avg(highest, lowest)(9), base = (26), a = avg(conv, base), b = (52); a and b are
    the cloud AS SHOWN under this bar (plotted displacement - 1 bars ahead). The lagging span (close, 25 bars back) is left out."""

    def __init__(self, conv: int = 9, base: int = 26, span: int = 52, disp: int = 26):
        self.c, self.b, self.s, self.d = int(conv), int(base), int(span), int(disp) - 1
        super().__init__()

    def initial(self):
        return ((), (), ())   # (h, l) window, delayed a, delayed b

    def step(self, st, bar):
        hl, qa, qb = st
        hl = _push(hl, (bar.h, bar.l), self.s)

        def don(n):
            w = hl[-n:]
            return None if len(w) < n else (max(h for h, _ in w) + min(l for _, l in w)) / 2.0
        conv, base, b = don(self.c), don(self.b), don(self.s)
        a = None if conv is None or base is None else (conv + base) / 2.0
        qa, ad = _delay(qa, a, self.d)
        qb, bd = _delay(qb, b, self.d)
        new = (hl, qa, qb)
        if conv is None:
            return new, None
        return new, {"conv": conv, "base": base, "a": ad, "b": bd}


class Alligator(_Study):
    """Williams Alligator: jaw = rma(hl2, 13) shown 8 bars later, teeth = rma(hl2, 8) 5 later, lips = rma(hl2, 5) 3 later;
    each AS SHOWN under this bar."""

    def __init__(self, jaw: int = 13, teeth: int = 8, lips: int = 5, jaw_off: int = 8, teeth_off: int = 5, lips_off: int = 3):
        self.n = (int(jaw), int(teeth), int(lips))
        self.off = (int(jaw_off), int(teeth_off), int(lips_off))
        super().__init__()

    def initial(self):
        return tuple((((), None), ()) for _ in range(3))

    def step(self, st, bar):
        x, out, new = _hl2(bar), [], []
        for (ms, q), n, off in zip(st, self.n, self.off):
            ms, v = _ma(ms, x, n, 1.0 / n)
            q, v = _delay(q, v, off)
            new.append((ms, q))
            out.append(v)
        if out[2] is None:
            return tuple(new), None
        return tuple(new), {"jaw": out[0], "teeth": out[1], "lips": out[2]}


def _fractal(vals, n, up):
    """Williams Fractals' test of bar [n] (vals newest last): the n bars after it strictly below (above) it, and the n bars
    before it too, where up to 4 equal bars right before it may be skipped; a missing bar compares false."""
    def v(j):
        return vals[-1 - j] if j < len(vals) else None

    def lt(a, b):
        return a is not None and b is not None and (a < b if up else a > b)

    def le(a, b):
        return a is not None and b is not None and (a <= b if up else a >= b)
    p = v(n)
    if p is None or not all(lt(v(n - i), p) for i in range(1, n + 1)):
        return False
    return any(all(le(v(n + j), p) for j in range(1, k + 1)) and all(lt(v(n + i + k), p) for i in range(1, n + 1))
               for k in range(5))


class Fractals(_Study):
    """Williams Fractals(2): up when high[n] tops the n bars each side (equal highs before it skipped, up to 4), down
    mirrored on lows; the mark belongs to the bar n bars BEFORE this one -> {up: its high} / {dn: its low}, None otherwise."""

    def __init__(self, n: int = 2):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return ((), ())   # highs, lows

    def step(self, st, bar):
        hs, ls = _push(st[0], bar.h, 2 * self.n + 5), _push(st[1], bar.l, 2 * self.n + 5)
        v = {}
        if _fractal(hs, self.n, True):
            v["up"] = hs[-1 - self.n]
        if _fractal(ls, self.n, False):
            v["dn"] = ls[-1 - self.n]
        return (hs, ls), (v or None)


# ---- oscillators ----
class CCI(_Study):
    """ta.cci(hlc3, 20): (src - sma(src, n)) / (0.015 dev(src, n)), dev = the mean absolute deviation."""

    def __init__(self, n: int = 20):
        self.n = int(n)
        super().__init__()

    def step(self, w, bar):
        w = _push(w, _hlc3(bar), self.n)
        if len(w) < self.n:
            return w, None
        m = _mean(w)
        return w, _div(w[-1] - m, 0.015 * _mean([abs(x - m) for x in w]))


class WPR(_Study):
    """Williams %R(14): 100 (close - highest(high, n)) / (highest(high, n) - lowest(low, n))."""

    def __init__(self, n: int = 14):
        self.n = int(n)
        super().__init__()

    def step(self, w, bar):
        w = _push(w, (bar.h, bar.l), self.n)
        if len(w) < self.n:
            return w, None
        hi, lo = max(h for h, _ in w), min(l for _, l in w)
        return w, _div(100.0 * (bar.c - hi), hi - lo)


class Momentum(_Closes):
    """Momentum(10): close - close[n]."""

    def __init__(self, n: int = 10):
        super().__init__(n + 1)

    def value(self, w):
        return w[-1] - w[0]


class ROC(_Closes):
    """ta.roc(close, 9): 100 (close - close[n]) / close[n]."""

    def __init__(self, n: int = 9):
        super().__init__(n + 1)

    def value(self, w):
        return _div(100.0 * (w[-1] - w[0]), w[0])


class AO(_Study):
    """Awesome Oscillator: sma(hl2, 5) - sma(hl2, 34)."""

    def __init__(self, fast: int = 5, slow: int = 34):
        self.f, self.s = int(fast), int(slow)
        super().__init__()

    def step(self, w, bar):
        w = _push(w, _hl2(bar), max(self.f, self.s))
        if len(w) < max(self.f, self.s):
            return w, None
        return w, _mean(w[-self.f:]) - _mean(w[-self.s:])


class BOP(_Study):
    """Balance of Power: (close - open) / (high - low)."""

    def step(self, st, bar):
        return st, _div(bar.c - bar.o, bar.h - bar.l)


class BBPower(_Study):
    """Bull Bear Power(13): (high - ema(close, n)) + (low - ema(close, n))."""

    def __init__(self, n: int = 13):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return ((), None)

    def step(self, st, bar):
        st, e = _ma(st, bar.c, self.n, _k(self.n))
        return st, (None if e is None else (bar.h - e) + (bar.l - e))


class CMO(_Study):
    """ta.cmo(close, 9): 100 (sum(up, n) - sum(down, n)) / (sum(up, n) + sum(down, n)), up / down = the change's sides."""

    def __init__(self, n: int = 9):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return (None, ())   # prev close, changes

    def step(self, st, bar):
        pc, w = st
        w = _push(w, None if pc is None else bar.c - pc, self.n)
        if not _full(w, self.n):
            return (bar.c, w), None
        up, dn = sum(x for x in w if x >= 0), sum(-x for x in w if x < 0)
        return (bar.c, w), _div(100.0 * (up - dn), up + dn)


class Connors(_Study):
    """Connors RSI(3, 2, 100): avg(rsi(close, 3), rsi(streak, 2), percentrank(roc(close, 1), 100)); the streak counts
    consecutive ups (+) or downs (-), 0 on an equal close, and is -1 on the first bar (Pine's na compares false)."""

    def __init__(self, n_rsi: int = 3, n_streak: int = 2, n_rank: int = 100):
        self.nr, self.ns, self.nk = int(n_rsi), int(n_streak), int(n_rank)
        super().__init__()

    def initial(self):
        return (None, _RSI0, 0.0, _RSI0, ())   # prev close, rsi(close), streak, rsi(streak), roc window

    def step(self, st, bar):
        pc, r1, ud, r2, w = st
        c = bar.c
        r1, a = _rsi(r1, c, self.nr)
        if pc is not None and c == pc:
            ud = 0.0
        elif pc is not None and c > pc:
            ud = 1.0 if ud <= 0 else ud + 1
        else:
            ud = -1.0 if ud >= 0 else ud - 1
        r2, b = _rsi(r2, ud, self.ns)
        w = _push(w, None if pc is None else _div(100.0 * (c - pc), pc), self.nk + 1)
        pr = None if not _full(w, self.nk + 1) else 100.0 * sum(1 for x in w[:-1] if x <= w[-1]) / self.nk
        v = None if a is None or b is None or pr is None else (a + b + pr) / 3.0
        return (c, r1, ud, r2, w), v


class Fisher(_Study):
    """Fisher Transform(9): v := clamp(0.66 ((hl2 - lowest(hl2, n)) / (highest - lowest) - 0.5) + 0.67 nz(v[1]), +/-0.999);
    fisher := 0.5 ln((1 + v) / (1 - v)) + 0.5 nz(fisher[1]); trigger = fisher[1]."""

    def __init__(self, n: int = 9):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return ((), None, None)   # hl2 window, value, fisher

    def step(self, st, bar):
        w, val, f = st
        w = _push(w, _hl2(bar), self.n)
        if len(w) < self.n:
            return (w, val, f), None
        x = _div(w[-1] - min(w), max(w) - min(w))
        if x is None:
            return (w, None, None), None
        v = 0.66 * (x - 0.5) + 0.67 * (val or 0.0)
        v = 0.999 if v > 0.99 else -0.999 if v < -0.99 else v
        nf = 0.5 * math.log((1 + v) / (1 - v)) + 0.5 * (f or 0.0)
        return (w, v, nf), {"fisher": nf, "trigger": f}


class PPO(_Study):
    """Price Oscillator(12, 26, 9): (ema(src, fast) - ema(src, slow)) / ema(src, slow) * 100, signal = ema(ppo, sig)."""
    SRC = staticmethod(lambda bar: bar.c)
    NAME = "ppo"

    def __init__(self, fast: int = 12, slow: int = 26, sig: int = 9):
        self.f, self.s, self.g = int(fast), int(slow), int(sig)
        super().__init__()

    def initial(self):
        return (((), None), ((), None), ((), None))

    def step(self, st, bar):
        x = self.SRC(bar)
        sf, f = _ma(st[0], x, self.f, _k(self.f))
        ss, s = _ma(st[1], x, self.s, _k(self.s))
        p = _div(_sub(f, s), s)
        p = None if p is None else p * 100.0
        sg, g = _ma(st[2], p, self.g, _k(self.g))
        return (sf, ss, sg), (None if p is None else {self.NAME: p, "signal": g, "hist": _sub(p, g)})


class PVO(PPO):
    """Percentage Volume Oscillator(12, 26, 9): the Price Oscillator on volume."""
    SRC = staticmethod(lambda bar: float(bar.v))
    NAME = "pvo"


class TRIX(_Study):
    """TRIX(18): 10000 change(ema(ema(ema(log(close), n), n), n))."""

    def __init__(self, n: int = 18):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return (((), None), ((), None), ((), None), None)

    def step(self, st, bar):
        s1, e1 = _ma(st[0], math.log(bar.c), self.n, _k(self.n))
        s2, e2 = _ma(st[1], e1, self.n, _k(self.n))
        s3, e3 = _ma(st[2], e2, self.n, _k(self.n))
        return (s1, s2, s3, e3), (None if e3 is None or st[3] is None else 10000.0 * (e3 - st[3]))


def _tsi0():
    return (None, ((), None), ((), None), ((), None), ((), None))


def _tsi(st, x, short, long):
    """One step of ta.tsi(src, short, long): 100 ema(ema(change, long), short) / ema(ema(|change|, long), short)."""
    px, a1, a2, b1, b2 = st
    d = None if px is None else x - px
    a1, u = _ma(a1, d, long, _k(long))
    a2, u = _ma(a2, u, short, _k(short))
    b1, v = _ma(b1, None if d is None else abs(d), long, _k(long))
    b2, v = _ma(b2, v, short, _k(short))
    t = _div(u, v)
    return (x, a1, a2, b1, b2), (None if t is None else 100.0 * t)


class TSI(_Study):
    """True Strength Index(25, 13, 13): ta.tsi(close, short, long) and its ema(signal)."""

    def __init__(self, long: int = 25, short: int = 13, sig: int = 13):
        self.l, self.s, self.g = int(long), int(short), int(sig)
        super().__init__()

    def initial(self):
        return (_tsi0(), ((), None))

    def step(self, st, bar):
        ts, t = _tsi(st[0], bar.c, self.s, self.l)
        sg, g = _ma(st[1], t, self.g, _k(self.g))
        return (ts, sg), (None if t is None else {"tsi": t, "signal": g})


class SMI(_Study):
    """SMI Ergodic Indicator(20, 5, 5): erg = ta.tsi(close, short, long), sig = ema(erg, n_sig)."""

    def __init__(self, long: int = 20, short: int = 5, sig: int = 5):
        self.l, self.s, self.g = int(long), int(short), int(sig)
        super().__init__()

    def initial(self):
        return (_tsi0(), ((), None))

    def step(self, st, bar):
        ts, t = _tsi(st[0], bar.c, self.s, self.l)
        sg, g = _ma(st[1], t, self.g, _k(self.g))
        return (ts, sg), (None if t is None else {"erg": t, "sig": g})


class SMIO(SMI):
    """SMI Ergodic Oscillator(20, 5, 5): erg - sig."""

    def step(self, st, bar):
        st, v = super().step(st, bar)
        return st, (None if v is None or v["sig"] is None else v["erg"] - v["sig"])


class SMIndex(_Study):
    """Stochastic Momentum Index(10, 3, 3): 200 ema(ema(close - avg(highest(k), lowest(k)), d), d) / ema(ema(highest(k)
    - lowest(k), d), d), and its ema(n_ema)."""

    def __init__(self, k: int = 10, d: int = 3, e: int = 3):
        self.k, self.d, self.e = int(k), int(d), int(e)
        super().__init__()

    def initial(self):
        return ((), ((), None), ((), None), ((), None), ((), None), ((), None))

    def step(self, st, bar):
        hl, a1, a2, b1, b2, es = st
        hl = _push(hl, (bar.h, bar.l), self.k)
        rel = rng = None
        if len(hl) == self.k:
            hi, lo = max(h for h, _ in hl), min(l for _, l in hl)
            rel, rng = bar.c - (hi + lo) / 2.0, hi - lo
        a1, u = _ma(a1, rel, self.d, _k(self.d))
        a2, u = _ma(a2, u, self.d, _k(self.d))
        b1, v = _ma(b1, rng, self.d, _k(self.d))
        b2, v = _ma(b2, v, self.d, _k(self.d))
        smi = _div(u, v)
        smi = None if smi is None else 200.0 * smi
        es, e = _ma(es, smi, self.e, _k(self.e))
        return (hl, a1, a2, b1, b2, es), (None if smi is None else {"smi": smi, "ema": e})


class UO(_Study):
    """Ultimate Oscillator(7, 14, 28): bp = close - min(low, close[1]), tr = max(high, close[1]) - min(low, close[1]);
    100 (4 sum(bp, 7)/sum(tr, 7) + 2 sum(bp, 14)/sum(tr, 14) + sum(bp, 28)/sum(tr, 28)) / 7."""

    def __init__(self, a: int = 7, b: int = 14, c: int = 28):
        self.n = (int(a), int(b), int(c))
        super().__init__()

    def initial(self):
        return (None, ())   # prev close, (bp, tr) window

    def step(self, st, bar):
        pc, w = st
        m = max(self.n)
        if pc is None:
            return (bar.c, _push(w, None, m)), None
        lo, hi = min(bar.l, pc), max(bar.h, pc)
        w = _push(w, (bar.c - lo, hi - lo), m)
        if not _full(w, m):
            return (bar.c, w), None

        def avg(n):
            part = w[-n:]
            return _div(sum(b for b, _ in part), sum(t for _, t in part))
        a, b, c = (avg(n) for n in self.n)
        if a is None or b is None or c is None:
            return (bar.c, w), None
        return (bar.c, w), 100.0 * (4 * a + 2 * b + c) / 7.0


def _swma(w):
    """ta.swma: x[3]/6 + x[2]/3 + x[1]/3 + x[0]/6 (w oldest first)."""
    return (w[0] + 2 * w[1] + 2 * w[2] + w[3]) / 6.0


class RVGI(_Study):
    """Relative Vigor Index(10): rvi = sum(swma(close - open), n) / sum(swma(high - low), n), sig = swma(rvi)."""

    def __init__(self, n: int = 10):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return ((), (), (), (), ())   # close-open, high-low, swma numerators, swma denominators, rvi

    def step(self, st, bar):
        co, hl, a, b, r = st
        co, hl = _push(co, bar.c - bar.o, 4), _push(hl, bar.h - bar.l, 4)
        a = _push(a, _swma(co) if len(co) == 4 else None, self.n)
        b = _push(b, _swma(hl) if len(hl) == 4 else None, self.n)
        rvi = _div(sum(a), sum(b)) if _full(a, self.n) else None
        r = _push(r, rvi, 4)
        new = (co, hl, a, b, r)
        if rvi is None:
            return new, None
        return new, {"rvi": rvi, "sig": _swma(r) if _full(r, 4) else None}


class RVI(_Study):
    """Relative Volatility Index(10, 14): sd = stdev(close, n); up = ema(change <= 0 ? 0 : sd, m), dn = ema(change > 0
    ? 0 : sd, m); 100 up / (up + dn)."""

    def __init__(self, n: int = 10, m: int = 14):
        self.n, self.m = int(n), int(m)
        super().__init__()

    def initial(self):
        return ((), ((), None), ((), None))

    def step(self, st, bar):
        w, su, sdn = st
        d = None if not w else bar.c - w[-1]
        w = _push(w, bar.c, self.n)
        sd = _sd(w) if len(w) == self.n else None
        up = None if sd is None else (0.0 if d is not None and d <= 0 else sd)
        dn = None if sd is None else (0.0 if d is not None and d > 0 else sd)
        su, u = _ma(su, up, self.m, _k(self.m))
        sdn, v = _ma(sdn, dn, self.m, _k(self.m))
        r = _div(u, None if u is None or v is None else u + v)
        return (w, su, sdn), (None if r is None else 100.0 * r)


class Coppock(_Study):
    """Coppock Curve(10, 14, 11): wma(roc(close, long) + roc(close, short), n)."""

    def __init__(self, n: int = 10, long: int = 14, short: int = 11):
        self.n, self.l, self.s = int(n), int(long), int(short)
        super().__init__()

    def initial(self):
        return ((), ())   # closes, the roc sum

    def step(self, st, bar):
        w, r = st
        w = _push(w, bar.c, max(self.l, self.s) + 1)
        x = None
        if len(w) > max(self.l, self.s):
            x = 100.0 * (w[-1] - w[-1 - self.l]) / w[-1 - self.l] + 100.0 * (w[-1] - w[-1 - self.s]) / w[-1 - self.s]
        r = _push(r, x, self.n)
        return (w, r), (_wma(r) if _full(r, self.n) else None)


class KST(_Study):
    """Know Sure Thing: kst = sma(roc(10), 10) + 2 sma(roc(15), 10) + 3 sma(roc(20), 10) + 4 sma(roc(30), 15), sig = sma(kst, 9)."""

    def __init__(self, r1: int = 10, r2: int = 15, r3: int = 20, r4: int = 30, s1: int = 10, s2: int = 10, s3: int = 10,
                 s4: int = 15, sig: int = 9):
        self.r = (int(r1), int(r2), int(r3), int(r4))
        self.s = (int(s1), int(s2), int(s3), int(s4))
        self.g = int(sig)
        super().__init__()

    def initial(self):
        return ((), (), (), (), (), ())   # closes, four roc windows, kst window

    def step(self, st, bar):
        w = _push(st[0], bar.c, max(self.r) + 1)
        rocs, parts = [], []
        for r, s, q in zip(self.r, self.s, st[1:5]):
            q = _push(q, _div(100.0 * (w[-1] - w[-1 - r]), w[-1 - r]) if len(w) > r else None, s)
            rocs.append(q)
            parts.append(_mean(q) if _full(q, s) else None)
        k = None if None in parts else parts[0] + 2 * parts[1] + 3 * parts[2] + 4 * parts[3]
        ks = _push(st[5], k, self.g)
        return (w, *rocs, ks), (None if k is None else {"kst": k, "sig": _mean(ks) if _full(ks, self.g) else None})


class DPO(_Study):
    """Detrended Price Oscillator(21, not centered): close - sma(close, n)[n / 2 + 1]."""

    def __init__(self, n: int = 21):
        self.n, self.back = int(n), int(n) // 2 + 1
        super().__init__()

    def initial(self):
        return ((), ())   # closes, delayed SMA

    def step(self, st, bar):
        w = _push(st[0], bar.c, self.n)
        q, m = _delay(st[1], _mean(w) if len(w) == self.n else None, self.back)
        return (w, q), _sub(bar.c, m)


class MassIndex(_Study):
    """Mass Index(10): sum(ema(high - low, 9) / ema(ema(high - low, 9), 9), n)."""

    def __init__(self, n: int = 10):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return (((), None), ((), None), ())

    def step(self, st, bar):
        s1, e1 = _ma(st[0], bar.h - bar.l, 9, _k(9))
        s2, e2 = _ma(st[1], e1, 9, _k(9))
        w = _push(st[2], _div(e1, e2), self.n)
        return (s1, s2, w), (sum(w) if _full(w, self.n) else None)


class Ulcer(_Closes):
    """Ulcer Index(14): sqrt(sma(dd^2, n)), dd = 100 (close - highest(close, n)) / highest(close, n)."""

    def __init__(self, n: int = 14):
        super().__init__(2 * int(n) - 1)
        self.m = int(n)

    def value(self, w):
        dd = []
        for i in range(self.m):
            part = w[i:i + self.m]
            hi = max(part)
            dd.append((100.0 * (part[-1] - hi) / hi) ** 2)
        return math.sqrt(_mean(dd))


def _bars_since(w, best):
    """ta.highestbars / lowestbars: minus the offset of the extreme (w newest last; the newest of equals)."""
    return -(len(w) - 1 - max(i for i, x in enumerate(w) if x == best))


class Aroon(_Study):
    """Aroon(14): up = 100 (highestbars(high, n + 1) + n) / n, down = 100 (lowestbars(low, n + 1) + n) / n."""

    def __init__(self, n: int = 14):
        self.n = int(n)
        super().__init__()

    def step(self, w, bar):
        w = _push(w, (bar.h, bar.l), self.n + 1)
        if len(w) <= self.n:
            return w, None
        hs, ls = [h for h, _ in w], [l for _, l in w]
        up = 100.0 * (_bars_since(hs, max(hs)) + self.n) / self.n
        dn = 100.0 * (_bars_since(ls, min(ls)) + self.n) / self.n
        return w, {"up": up, "dn": dn}


class AroonOsc(Aroon):
    """Aroon Oscillator(14): up - down."""

    def step(self, st, bar):
        st, v = super().step(st, bar)
        return st, (None if v is None else v["up"] - v["dn"])


class Vortex(_Study):
    """Vortex(14): vip = sum(|high - low[1]|, n) / sum(atr(1), n), vim = sum(|low - high[1]|, n) / the same."""

    def __init__(self, n: int = 14):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return (None, ())   # prev (h, l, c), (vm+, vm-, tr) window

    def step(self, st, bar):
        prev, w = st
        if prev is None:
            w = _push(w, None, self.n)
        else:
            ph, pl, pc = prev
            w = _push(w, (abs(bar.h - pl), abs(bar.l - ph), _tr(bar, pc)), self.n)
        new = ((bar.h, bar.l, bar.c), w)
        if not _full(w, self.n):
            return new, None
        tr = sum(t for _, _, t in w)
        return new, {"vip": _div(sum(p for p, _, _ in w), tr), "vim": _div(sum(m for _, m, _ in w), tr)}


class Chop(_Study):
    """Choppiness Index(14): 100 log10(sum(atr(1), n) / (highest(high, n) - lowest(low, n))) / log10(n)."""

    def __init__(self, n: int = 14):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return (None, ())   # prev close, (h, l, tr) window

    def step(self, st, bar):
        pc, w = st
        w = _push(w, (bar.h, bar.l, _tr(bar, pc)), self.n)
        if len(w) < self.n:
            return (bar.c, w), None
        x = _div(sum(t for _, _, t in w), max(h for h, _, _ in w) - min(l for _, l, _ in w))
        return (bar.c, w), (None if x is None or x <= 0 else 100.0 * math.log10(x) / math.log10(self.n))


class RCI(_Closes):
    """Rank Correlation Index(10): (1 - 6 sum((time rank - price rank)^2) / (n (n^2 - 1))) 100, rank 1 = the newest bar
    and the highest price."""

    def __init__(self, n: int = 10):
        super().__init__(n)

    def value(self, w):
        n = len(w)
        d = sum(((n - i) - (1 + sum(1 for y in w if y > x))) ** 2 for i, x in enumerate(w))
        return (1 - 6.0 * d / (n * (n * n - 1))) * 100.0


class HV(_Study):
    """Historical Volatility(10): 100 stdev(log(close / close[1]), n) sqrt(365) (intraday and daily bars)."""

    def __init__(self, n: int = 10):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return (None, ())

    def step(self, st, bar):
        pc, w = st
        w = _push(w, None if pc is None else math.log(bar.c / pc), self.n)
        return (bar.c, w), (100.0 * _sd(w) * math.sqrt(365) if _full(w, self.n) else None)


# ---- volume ----
class OBV(_Study):
    """ta.obv: cum(sign(change(close)) volume); na on the first bar."""

    def initial(self):
        return (None, 0.0)

    def step(self, st, bar):
        pc, s = st
        if pc is None:
            return (bar.c, s), None
        s += (bar.v if bar.c > pc else -bar.v if bar.c < pc else 0)
        return (bar.c, s), s


class PVT(_Study):
    """ta.pvt: cum(change(close) / close[1] volume); na on the first bar."""

    def initial(self):
        return (None, 0.0)

    def step(self, st, bar):
        pc, s = st
        if pc is None:
            return (bar.c, s), None
        s += (bar.c - pc) / pc * bar.v
        return (bar.c, s), s


def _clv(bar):
    """((close - low) - (high - close)) / (high - low), 0 when the bar has no range."""
    return 0.0 if bar.h == bar.l else ((bar.c - bar.l) - (bar.h - bar.c)) / (bar.h - bar.l)


class ADL(_Study):
    """ta.accdist: cum(((close - low) - (high - close)) / (high - low) volume)."""

    def initial(self):
        return (0.0,)

    def step(self, st, bar):
        s = st[0] + _clv(bar) * bar.v
        return (s,), s


class CMF(_Study):
    """Chaikin Money Flow(20): sum(clv volume, n) / sum(volume, n)."""

    def __init__(self, n: int = 20):
        self.n = int(n)
        super().__init__()

    def step(self, w, bar):
        w = _push(w, (_clv(bar) * bar.v, bar.v), self.n)
        if len(w) < self.n:
            return w, None
        return w, _div(sum(a for a, _ in w), sum(v for _, v in w))


class Chaikin(_Study):
    """Chaikin Oscillator(3, 10): ema(accdist, fast) - ema(accdist, slow)."""

    def __init__(self, fast: int = 3, slow: int = 10):
        self.f, self.s = int(fast), int(slow)
        super().__init__()

    def initial(self):
        return (0.0, ((), None), ((), None))

    def step(self, st, bar):
        ad = st[0] + _clv(bar) * bar.v
        sf, f = _ma(st[1], ad, self.f, _k(self.f))
        ss, s = _ma(st[2], ad, self.s, _k(self.s))
        return (ad, sf, ss), _sub(f, s)


class Klinger(_Study):
    """Klinger Oscillator(34, 55, 13): sv = change(hlc3) >= 0 ? volume : -volume (minus on the first bar); kvo = ema(sv, 34)
    - ema(sv, 55), sig = ema(kvo, 13)."""

    def __init__(self, fast: int = 34, slow: int = 55, sig: int = 13):
        self.f, self.s, self.g = int(fast), int(slow), int(sig)
        super().__init__()

    def initial(self):
        return (None, ((), None), ((), None), ((), None))

    def step(self, st, bar):
        p = _hlc3(bar)
        sv = float(bar.v) if st[0] is not None and p - st[0] >= 0 else -float(bar.v)
        sf, f = _ma(st[1], sv, self.f, _k(self.f))
        ss, s = _ma(st[2], sv, self.s, _k(self.s))
        k = _sub(f, s)
        sg, g = _ma(st[3], k, self.g, _k(self.g))
        return (p, sf, ss, sg), (None if k is None else {"kvo": k, "sig": g})


class EFI(_Study):
    """Elder Force Index(13): ema(change(close) volume, n)."""

    def __init__(self, n: int = 13):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return (None, ((), None))

    def step(self, st, bar):
        pc, es = st
        es, e = _ma(es, None if pc is None else (bar.c - pc) * bar.v, self.n, _k(self.n))
        return (bar.c, es), e


class EOM(_Study):
    """Ease of Movement(14, 10000): sma(div change(hl2) (high - low) / volume, n)."""

    def __init__(self, n: int = 14, div: float = 10000.0):
        self.n, self.d = int(n), float(div)
        super().__init__()

    def initial(self):
        return (None, ())

    def step(self, st, bar):
        ph, w = st
        x = _hl2(bar)
        w = _push(w, None if ph is None else _div(self.d * (x - ph) * (bar.h - bar.l), bar.v), self.n)
        return (x, w), (_mean(w) if _full(w, self.n) else None)


class NVI(_Study):
    """Negative Volume Index: nvi := volume < volume[1] ? nvi[1] (1 + change(close) / close[1]) : nvi[1], from 1000."""
    DOWN = True

    def initial(self):
        return (None, None, 1000.0)   # prev close, prev volume, the index

    def step(self, st, bar):
        pc, pv, x = st
        if pv is not None and (bar.v < pv if self.DOWN else bar.v > pv):
            x = x + (bar.c - pc) / pc * x
        return (bar.c, bar.v, x), x


class PVI(NVI):
    """Positive Volume Index: the same on volume > volume[1]."""
    DOWN = False


class NetVolume(_Study):
    """Net Volume: change(close) > 0 ? volume : change(close) < 0 ? -volume : 0."""

    def initial(self):
        return (None,)   # prev close

    def step(self, st, bar):
        pc = st[0]
        v = 0.0 if pc is None else (float(bar.v) if bar.c > pc else -float(bar.v) if bar.c < pc else 0.0)
        return (bar.c,), v


# ---- structure and statistics ----
class ZigZag(_Study):
    """Zig Zag(5 %, 10): a pivot is a high (low) no bar within depth/2 on either side beats, known depth/2 bars later; a
    same-side pivot beyond the last one moves it, an opposite one further than deviation % starts a new leg -> the last
    pivot {px, back (bars ago), dir (1 high, -1 low)}."""

    def __init__(self, dev: float = 5.0, depth: int = 10):
        self.dev, self.len = float(dev), int(depth) // 2
        super().__init__()

    def initial(self):
        return ((), 0, None, 0.0, True, 0)   # (h, l) window, bar index, last pivot's index, price, is-high, lines count

    def _pivot(self, w, i, up):
        n = self.len
        if n * 2 > i:
            return None
        vals = [h if up else l for h, l in w]
        p = vals[-1 - n]
        others = vals[-1 - 2 * n:-1 - n] + vals[-n:]
        if any(x > p if up else x < p for x in others):
            return None
        return p

    def _found(self, st, up, i, price):
        w, _, il, pl, hl, cnt = st
        if hl == up and il is not None:
            if price > pl if up else price < pl:
                return (w, i, i - self.len, price, up, cnt)
            return st
        if il is None or abs(_div(100.0 * (price - pl), abs(pl)) or 0.0) >= self.dev:
            return (w, i, i - self.len, price, up, cnt + 1)
        return st

    def step(self, st, bar):
        w = _push(st[0], (bar.h, bar.l), 2 * self.len + 1)
        i = st[1]
        st = (w, i) + st[2:]
        if len(w) == 2 * self.len + 1:
            ph, pl = self._pivot(w, i, True), self._pivot(w, i, False)
            if ph is not None:
                st = self._found(st, True, i, ph)
            if pl is not None:
                st = self._found(st, False, i, pl)
        w, _, il, pl, hl, cnt = st
        st = (w, i + 1, il, pl, hl, cnt)
        return st, (None if il is None else {"px": pl, "back": i - il, "dir": 1 if hl else -1})


class Median(_Study):
    """Median(3): ta.percentile_nearest_rank(hl2, n, 50), the ceil(n / 2)-th smallest."""

    def __init__(self, n: int = 3):
        self.n = int(n)
        super().__init__()

    def step(self, w, bar):
        w = _push(w, _hl2(bar), self.n)
        return w, (sorted(w)[math.ceil(self.n / 2) - 1] if len(w) == self.n else None)


class COG(_Closes):
    """ta.cog(close, 10): -sum(close[i] (i + 1)) / sum(close, n), i = 0 the newest."""

    def __init__(self, n: int = 10):
        super().__init__(n)

    def value(self, w):
        return _div(-sum(x * (self.n - i) for i, x in enumerate(w)), sum(w))


class Corr(_Closes):
    """Trend Strength Index(14): ta.correlation(close, bar_index, n), Pearson's r of price against time."""

    def __init__(self, n: int = 14):
        super().__init__(n)

    def value(self, w):
        n = len(w)
        xm, ym = (n - 1) / 2.0, _mean(w)
        sxy = sum((i - xm) * (y - ym) for i, y in enumerate(w))
        sxx, syy = sum((i - xm) ** 2 for i in range(n)), sum((y - ym) ** 2 for y in w)
        return _div(sxy, math.sqrt(sxx * syy))


class LinReg(_Closes):
    """Linear Regression channel(100, 2): the regression line's value at this bar +/- mult x the window's deviation around
    the line (sqrt(sum of squares / (n - 1)))."""

    def __init__(self, n: int = 100, mult: float = 2.0):
        super().__init__(n)
        self.m = float(mult)

    def value(self, w):
        mid, sd = _fit(w)
        return {"mid": mid, "up": mid + self.m * sd, "dn": mid - self.m * sd}


# name -> (class, parameters): each parameter is (default, minimum, maximum), TradingView's defaults; a wire key
# "tv:<name>[:args]" gives them in order (studies_tv.make_tv merges this table into its own)
PARAMS = {
    "hma": (HMA, ((9, 2, 500),)),
    "dema": (DEMA, ((9, 1, 500),)),
    "smma": (SMMA, ((7, 1, 500),)),
    "alma": (ALMA, ((9, 1, 500), (0.85, 0.0, 1.0), (6.0, 0.1, 100))),
    "lsma": (LSMA, ((25, 2, 500),)),
    "mcginley": (McGinley, ((14, 1, 500),)),
    "kama": (KAMA, ((14, 1, 500), (2, 1, 500), (30, 1, 500))),
    "envelope": (Envelope, ((20, 1, 500), (10.0, 0.01, 100))),
    "stochrsi": (StochRSI, ((14, 1, 500), (14, 1, 500), (3, 1, 100), (3, 1, 100))),
    "bbpct": (BBPct, ((20, 2, 500), (2.0, 0.001, 50))),
    "bbw": (BBW, ((20, 2, 500), (2.0, 0.001, 50))),
    "bbtrend": (BBTrend, ((20, 2, 500), (50, 2, 500), (2.0, 0.001, 50))),
    "sar": (SAR, ((0.02, 0.0001, 1.0), (0.02, 0.0001, 1.0), (0.2, 0.0001, 1.0))),
    "chandelier": (Chandelier, ((22, 1, 500), (3.0, 0.1, 20))),
    "vstop": (VStop, ((20, 2, 500), (2.0, 0.25, 20))),
    "chandekroll": (ChandeKroll, ((10, 1, 500), (1.0, 0.1, 20), (9, 1, 500))),
    "ichimoku": (Ichimoku, ((9, 1, 500), (26, 1, 500), (52, 1, 500), (26, 1, 500))),
    "alligator": (Alligator, ((13, 1, 500), (8, 1, 500), (5, 1, 500), (8, 0, 100), (5, 0, 100), (3, 0, 100))),
    "fractals": (Fractals, ((2, 2, 50),)),
    "cci": (CCI, ((20, 1, 500),)),
    "wpr": (WPR, ((14, 1, 500),)),
    "mom": (Momentum, ((10, 1, 500),)),
    "roc": (ROC, ((9, 1, 500),)),
    "ao": (AO, ((5, 1, 500), (34, 1, 500))),
    "bop": (BOP, ()),
    "bbp": (BBPower, ((13, 1, 500),)),
    "cmo": (CMO, ((9, 1, 500),)),
    "connors": (Connors, ((3, 1, 500), (2, 1, 500), (100, 1, 1000))),
    "fisher": (Fisher, ((9, 1, 500),)),
    "ppo": (PPO, ((12, 1, 500), (26, 1, 500), (9, 1, 500))),
    "pvo": (PVO, ((12, 1, 500), (26, 1, 500), (9, 1, 500))),
    "trix": (TRIX, ((18, 1, 500),)),
    "tsi": (TSI, ((25, 1, 500), (13, 1, 500), (13, 1, 500))),
    "smi": (SMI, ((20, 1, 500), (5, 1, 500), (5, 1, 500))),
    "smio": (SMIO, ((20, 1, 500), (5, 1, 500), (5, 1, 500))),
    "smindex": (SMIndex, ((10, 1, 500), (3, 1, 500), (3, 1, 500))),
    "uo": (UO, ((7, 1, 500), (14, 1, 500), (28, 1, 500))),
    "rvgi": (RVGI, ((10, 1, 500),)),
    "rvi": (RVI, ((10, 2, 500), (14, 1, 500))),
    "coppock": (Coppock, ((10, 1, 500), (14, 1, 500), (11, 1, 500))),
    "kst": (KST, ((10, 1, 500), (15, 1, 500), (20, 1, 500), (30, 1, 500), (10, 1, 500), (10, 1, 500), (10, 1, 500),
                  (15, 1, 500), (9, 1, 500))),
    "dpo": (DPO, ((21, 1, 500),)),
    "massindex": (MassIndex, ((10, 1, 500),)),
    "ulcer": (Ulcer, ((14, 1, 500),)),
    "aroon": (Aroon, ((14, 1, 500),)),
    "aroonosc": (AroonOsc, ((14, 1, 500),)),
    "vortex": (Vortex, ((14, 1, 500),)),
    "chop": (Chop, ((14, 2, 500),)),
    "rci": (RCI, ((10, 2, 500),)),
    "hv": (HV, ((10, 2, 500),)),
    "obv": (OBV, ()),
    "pvt": (PVT, ()),
    "adl": (ADL, ()),
    "cmf": (CMF, ((20, 1, 500),)),
    "chaikin": (Chaikin, ((3, 1, 500), (10, 1, 500))),
    "klinger": (Klinger, ((34, 1, 500), (55, 1, 500), (13, 1, 500))),
    "efi": (EFI, ((13, 1, 500),)),
    "eom": (EOM, ((14, 1, 500), (10000.0, 1, 1e9))),
    "nvi": (NVI, ()),
    "pvi": (PVI, ()),
    "netvol": (NetVolume, ()),
    "zigzag": (ZigZag, ((5.0, 0.00001, 100), (10, 1, 500))),
    "median": (Median, ((3, 1, 500),)),
    "cog": (COG, ((10, 1, 500),)),
    "corr": (Corr, ((14, 2, 500),)),
    "linreg": (LinReg, ((100, 2, 1000), (2.0, 0.0, 20))),
}


def _num(args, i, default):
    try:
        return int(float(args[i]))
    except (IndexError, ValueError, TypeError):
        return default


def _warm_of(spec):
    """A study's memory in bars from its wire-key args: windows add up, an EMA of n counts 5 n, a Wilder average 10 n."""
    def warm(args):
        return sum(m * _num(args, i, d) for i, m, d in spec)
    return warm


# name -> fn(args: list[str]) -> bars after a join the value still depends on (hub.warm_bars through studies_tv.warm_tv);
# (arg index, multiplier, default) terms, plus a constant where a length is fixed in the formula
WARM = {
    "hma": _warm_of(((0, 2, 9),)),
    "dema": _warm_of(((0, 10, 9),)),
    "smma": _warm_of(((0, 10, 7),)),
    "alma": _warm_of(((0, 1, 9),)),
    "lsma": _warm_of(((0, 1, 25),)),
    "mcginley": _warm_of(((0, 10, 14),)),
    "kama": _warm_of(((0, 1, 14), (2, 5, 30))),
    "envelope": _warm_of(((0, 1, 20),)),
    "stochrsi": _warm_of(((0, 10, 14), (1, 1, 14), (2, 1, 3), (3, 1, 3))),
    "bbpct": _warm_of(((0, 1, 20),)),
    "bbw": _warm_of(((0, 1, 20),)),
    "bbtrend": _warm_of(((1, 1, 50),)),
    "sar": lambda args: 400,
    "chandelier": _warm_of(((0, 10, 22),)),
    "vstop": _warm_of(((0, 10, 20),)),
    "chandekroll": _warm_of(((0, 10, 10), (2, 1, 9))),
    "ichimoku": _warm_of(((2, 1, 52), (3, 1, 26))),
    "alligator": _warm_of(((0, 10, 13), (3, 1, 8))),
    "fractals": _warm_of(((0, 2, 2),)),
    "cci": _warm_of(((0, 1, 20),)),
    "wpr": _warm_of(((0, 1, 14),)),
    "mom": _warm_of(((0, 1, 10),)),
    "roc": _warm_of(((0, 1, 9),)),
    "ao": _warm_of(((1, 1, 34),)),
    "bop": lambda args: 0,
    "bbp": _warm_of(((0, 5, 13),)),
    "cmo": _warm_of(((0, 1, 9),)),
    "connors": _warm_of(((0, 10, 3), (1, 10, 2), (2, 1, 100))),
    "fisher": _warm_of(((0, 10, 9),)),
    "ppo": _warm_of(((1, 5, 26), (2, 5, 9))),
    "pvo": _warm_of(((1, 5, 26), (2, 5, 9))),
    "trix": _warm_of(((0, 15, 18),)),
    "tsi": _warm_of(((0, 5, 25), (1, 5, 13), (2, 5, 13))),
    "smi": _warm_of(((0, 5, 20), (1, 5, 5), (2, 5, 5))),
    "smio": _warm_of(((0, 5, 20), (1, 5, 5), (2, 5, 5))),
    "smindex": _warm_of(((0, 1, 10), (1, 10, 3), (2, 5, 3))),
    "uo": _warm_of(((2, 1, 28),)),
    "rvgi": _warm_of(((0, 1, 10),)),
    "rvi": _warm_of(((0, 1, 10), (1, 5, 14))),
    "coppock": _warm_of(((0, 1, 10), (1, 1, 14))),
    "kst": _warm_of(((3, 1, 30), (7, 1, 15), (8, 1, 9))),
    "dpo": _warm_of(((0, 2, 21),)),
    "massindex": lambda args: 90 + _num(args, 0, 10),
    "ulcer": _warm_of(((0, 2, 14),)),
    "aroon": _warm_of(((0, 1, 14),)),
    "aroonosc": _warm_of(((0, 1, 14),)),
    "vortex": _warm_of(((0, 1, 14),)),
    "chop": _warm_of(((0, 1, 14),)),
    "rci": _warm_of(((0, 1, 10),)),
    "hv": _warm_of(((0, 1, 10),)),
    "obv": lambda args: 0,
    "pvt": lambda args: 0,
    "adl": lambda args: 0,
    "cmf": _warm_of(((0, 1, 20),)),
    "chaikin": _warm_of(((1, 5, 10),)),
    "klinger": _warm_of(((1, 5, 55), (2, 5, 13))),
    "efi": _warm_of(((0, 5, 13),)),
    "eom": _warm_of(((0, 1, 14),)),
    "nvi": lambda args: 0,
    "pvi": lambda args: 0,
    "netvol": lambda args: 0,
    "zigzag": lambda args: 400,
    "median": _warm_of(((0, 1, 3),)),
    "cog": _warm_of(((0, 1, 10),)),
    "corr": _warm_of(((0, 1, 14),)),
    "linreg": _warm_of(((0, 1, 100),)),
}

# name -> completed sessions to feed before the loaded ones (hub.prime_sessions): none here reads a prior session,
# so every study primes 0 (a missing name means 0)
PRIME = {}
