"""TradingView's built-in indicators in Pine's own math: the "tv:" namespace (2026-10-21). The house studies of
studies.py / studies_ta.py keep the strategy engine's definitions and never change; these keep TradingView's, so a line
here can be checked against TradingView's own export (tools/tvparity.py). Pure; the Study contract of studies.py
(push / preview, immutable state, None = Pine's na). Every study reads only OHLCV, buy / sell and n, so each key may
take a timeframe ("tv:ema:20@3600"), except the two mark studies tv:pivothl and tv:fractals (split_timeframe refuses
them). The long tail (hma, cci, obv, ...) is studies_tv2.py, merged into PARAMS here.

Wire keys "tv:<name>[:args]"; a missing argument takes TradingView's default, a source is one of SOURCES:
  tv:sma:9:close         ta.sma                                                                     -> float
  tv:ema:9:close         ta.ema: alpha 2/(n+1), seeded with the SMA at bar n-1, na before            -> float
  tv:rma:7:close         ta.rma: alpha 1/n, the same seed (TV's Smoothed Moving Average)             -> float
  tv:wma:9:close         ta.wma: weights n..1, the newest bar the heaviest                           -> float
  tv:rsi:14:close        ta.rsi: rma(ups) / rma(downs); down = 0 -> 100, up = 0 -> 0                 -> float
  tv:macd:12:26:9:close  ta.ema(fast) - ta.ema(slow), signal = ta.ema(macd, sig)                     -> {macd, signal, hist}
  tv:stoch:14:1:3        100 (c - LL) / (HH - LL); %K = sma(.., smoothK), %D = sma(%K, smoothD); a flat range is na
                                                                                                    -> {k, d}
  tv:adx:14:14           the ADX / DMI built-ins (dilen, adxlen): ta.tr is na at bar 0, so its rma seeds one bar later;
                         fixnan on the DIs; a DI sum of 0 divides by 1                               -> {adx, pdi, mdi}
  tv:atr:14              ta.atr = rma(ta.tr(true), n)                                               -> float
  tv:bb:20:2:close       ta.sma +/- mult x ta.stdev (population)                                    -> {mid, up, dn}
  tv:keltner:20:2:10:atr Keltner Channels: ta.ema(close, n) +/- mult x the band: "atr" = ta.atr(m) (TV's default,
                         "Average True Range"), "tr" = the bar's own ta.tr(true), "range" = rma(high - low, n)
                                                                                                    -> {mid, up, dn}
  tv:donchian:20         ta.highest / ta.lowest and their middle                                    -> {up, dn, mid}
  tv:supertrend:10:3     ta.supertrend(factor 3, atr 10), TV's sign: dir 1 = down (the line is the upper band), -1 = up;
                         it starts down, and a flip compares the close with THIS bar's band           -> {line, dir}
  tv:tema:9:close        3 (e1 - e2) + e3, each a ta.ema                                            -> float
  tv:mfi:14              ta.mfi(hlc3) over the last n changes; no down flow = 100, 0/0 = na         -> float
  tv:vwap:session        ta.vwap(hlc3) since the anchor (session = the 18:00 ET session, week, month, quarter, year)
                         and its bands at 1, 2, 3 volume-weighted standard deviations of hlc3
                                                                                                    -> {vwap, u1, l1, u2, l2, u3, l3}
  tv:cvd                 Cumulative Volume Delta, TV's lower-timeframe rule on the chart's own bars: close > open = up
                         volume, < open = down, equal = against the previous close, still equal = the previous bar's
                         side; summed over the session, as a candle                                 -> {o, h, l, c}
  tv:vdelta              Volume Delta: one bar's delta by the same rule, as a candle from 0           -> {o, h, l, c}
  tv:updown              Up/Down Volume: the up volume, the down volume (negative) and their sum     -> {up, down, delta}
  tv:rvol:14:cumulative  Relative Volume at Time: the session's volume so far over the MEAN of the volume by the same
                         time since the open on the last n sessions (a session's last bar at or before that time);
                         "regular" = this bar's volume alone over the mean of theirs                 -> float
  tv:adr:14              Average Daily Range: sma(high - low, n) of the last n COMPLETED sessions     -> float
  tv:pivots:traditional  Pivot Points Standard on the prior session's high / low / last-trade close (traditional,
                         fibonacci, woodie, classic, dm, camarilla)                                  -> {p, r1, s1, ...}
  tv:pivothl:10:10       Pivot Points High Low: ta.pivothigh / ta.pivotlow (left, right), the price on the bar that
                         confirms it, `right` bars after the pivot                                  -> {hi, lo}
  tv:twap:ohlc4          TWAP: the mean of the source over the session so far                       -> float
"""
from __future__ import annotations

import bisect
import datetime as dt
import math

from .session import ET, always_open, month_key, week_key
from .studies_ta import _Study, make_ta_num

try:
    from .studies_tv2 import PARAMS as PARAMS2, PRIME as PRIME2, WARM as WARM2
except ImportError:                 # the long tail is not there yet
    PARAMS2, PRIME2, WARM2 = {}, {}, {}

SOURCES = {"close": lambda b: b.c, "open": lambda b: b.o, "high": lambda b: b.h, "low": lambda b: b.l,
           "hl2": lambda b: (b.h + b.l) / 2, "hlc3": lambda b: (b.h + b.l + b.c) / 3,
           "ohlc4": lambda b: (b.o + b.h + b.l + b.c) / 4}


def _source(name):
    if name not in SOURCES:
        raise ValueError(f"source {name!r} (have {', '.join(SOURCES)})")
    return SOURCES[name]


def _sma(w, x, n):
    """One bar of ta.sma on x (None = na, which empties the window: the SMA is na while the window holds one)."""
    w = () if x is None else (w + (x,))[-n:]
    return w, (sum(w) / n if len(w) == n else None)


def _smooth(st, x, n, alpha):
    """One bar of ta.ema (alpha 2/(n+1)) or ta.rma (alpha 1/n) on x: `sum := na(sum[1]) ? ta.sma(src, n) : alpha * src +
    (1 - alpha) * sum[1]`, so it seeds with the SMA of the first n values in a row that are not na. State (window, value)."""
    w, v = st
    if x is None:
        return ((), None), None
    if v is None:
        w, v = _sma(w, x, n)
    else:
        v = alpha * x + (1.0 - alpha) * v
    return (w, v), v


def _tr(bar, pc):
    """ta.tr(true): the plain range on the first bar."""
    return bar.h - bar.l if pc is None else max(bar.h - bar.l, abs(bar.h - pc), abs(bar.l - pc))


class _MA(_Study):
    """A study of one source over n bars."""

    def __init__(self, n: int = 9, source: str = "close"):
        self.n, self.src = int(n), _source(source)
        super().__init__()


class SMA(_MA):
    def step(self, w, bar):
        return _sma(w, self.src(bar), self.n)


class EMA(_MA):
    def initial(self):
        return ((), None)

    def step(self, st, bar):
        return _smooth(st, self.src(bar), self.n, 2.0 / (self.n + 1))


class RMA(_MA):
    def __init__(self, n: int = 7, source: str = "close"):
        super().__init__(n, source)

    def initial(self):
        return ((), None)

    def step(self, st, bar):
        return _smooth(st, self.src(bar), self.n, 1.0 / self.n)


class WMA(_MA):
    def step(self, w, bar):
        w = (w + (self.src(bar),))[-self.n:]
        if len(w) < self.n:
            return w, None
        return w, sum(x * (i + 1) for i, x in enumerate(w)) / (self.n * (self.n + 1) / 2.0)


class RSI(_MA):
    def __init__(self, n: int = 14, source: str = "close"):
        super().__init__(n, source)

    def initial(self):
        return (None, ((), None), ((), None))   # previous source, rma of the ups, rma of the downs

    def step(self, st, bar):
        pc, up, dn = st
        x = self.src(bar)
        if pc is None:                          # ta.change is na on the first bar
            return (x, up, dn), None
        d = x - pc
        up, u = _smooth(up, max(d, 0.0), self.n, 1.0 / self.n)
        dn, l = _smooth(dn, max(-d, 0.0), self.n, 1.0 / self.n)
        if u is None:
            return (x, up, dn), None
        return (x, up, dn), (100.0 if l == 0 else 0.0 if u == 0 else 100.0 - 100.0 / (1.0 + u / l))


class MACD(_Study):
    def __init__(self, fast: int = 12, slow: int = 26, sig: int = 9, source: str = "close"):
        self.fast, self.slow, self.sig, self.src = int(fast), int(slow), int(sig), _source(source)
        super().__init__()

    def initial(self):
        return (((), None), ((), None), ((), None))   # fast EMA, slow EMA, signal EMA

    def step(self, st, bar):
        f, s, g = st
        x = self.src(bar)
        f, fv = _smooth(f, x, self.fast, 2.0 / (self.fast + 1))
        s, sv = _smooth(s, x, self.slow, 2.0 / (self.slow + 1))
        m = None if fv is None or sv is None else fv - sv
        g, gv = _smooth(g, m, self.sig, 2.0 / (self.sig + 1))
        if m is None:
            return (f, s, g), None
        return (f, s, g), {"macd": m, "signal": gv, "hist": None if gv is None else m - gv}


class Stochastic(_Study):
    def __init__(self, n: int = 14, k: int = 1, d: int = 3):
        self.n, self.k, self.d = int(n), int(k), int(d)
        super().__init__()

    def initial(self):
        return ((), (), ())   # (high, low) window, raw %K window, %K window

    def step(self, st, bar):
        hl, raw, ks = st
        hl = (hl + ((bar.h, bar.l),))[-self.n:]
        x = None
        if len(hl) == self.n:
            hi, lo = max(h for h, _ in hl), min(l for _, l in hl)
            x = None if hi == lo else 100.0 * (bar.c - lo) / (hi - lo)   # Pine divides by zero into na
        raw, k = _sma(raw, x, self.k)
        ks, d = _sma(ks, k, self.d)
        return (hl, raw, ks), (None if k is None else {"k": k, "d": d})


class ADX(_Study):
    def __init__(self, di: int = 14, adx: int = 14):
        self.di, self.adx = int(di), int(adx)
        super().__init__()

    def initial(self):
        # previous high, low, close; rma of tr, +DM, -DM; the last +DI, -DI that were not na (fixnan); rma of DX
        return (None, None, None, ((), None), ((), None), ((), None), None, None, ((), None))

    def step(self, st, bar):
        ph, pl, pc, trs, ps, ms, lp, lm, dxs = st
        h, l, c = bar.h, bar.l, bar.c
        if pc is None:                          # ta.tr and ta.change are na on the first bar
            tr = up_dm = dn_dm = None
        else:
            tr = max(h - l, abs(h - pc), abs(l - pc))
            up, dn = h - ph, pl - l
            up_dm = up if up > dn and up > 0 else 0.0
            dn_dm = dn if dn > up and dn > 0 else 0.0
        a = 1.0 / self.di
        trs, trv = _smooth(trs, tr, self.di, a)
        ps, pv = _smooth(ps, up_dm, self.di, a)
        ms, mv = _smooth(ms, dn_dm, self.di, a)
        if trv:                                 # a zero true range divides into na: fixnan keeps the last reading
            lp, lm = 100.0 * pv / trv, 100.0 * mv / trv
        dx = None
        if lp is not None:
            s = lp + lm
            dx = abs(lp - lm) / (s if s else 1.0)
        dxs, adx = _smooth(dxs, dx, self.adx, 1.0 / self.adx)
        st = (h, l, c, trs, ps, ms, lp, lm, dxs)
        if lp is None:
            return st, None
        return st, {"adx": None if adx is None else 100.0 * adx, "pdi": lp, "mdi": lm}


class ATR(_Study):
    def __init__(self, n: int = 14):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return (None, ((), None))   # previous close, the rma

    def step(self, st, bar):
        pc, s = st
        s, v = _smooth(s, _tr(bar, pc), self.n, 1.0 / self.n)
        return (bar.c, s), v


class Bollinger(_MA):
    def __init__(self, n: int = 20, mult: float = 2.0, source: str = "close"):
        self.mult = float(mult)
        super().__init__(n, source)

    def step(self, w, bar):
        w, mid = _sma(w, self.src(bar), self.n)
        if mid is None:
            return w, None
        sd = math.sqrt(sum((x - mid) ** 2 for x in w) / self.n)
        return w, {"mid": mid, "up": mid + self.mult * sd, "dn": mid - self.mult * sd}


class Keltner(_Study):
    STYLES = ("atr", "tr", "range")

    def __init__(self, n: int = 20, mult: float = 2.0, m: int = 10, style: str = "atr"):
        if style not in self.STYLES:
            raise ValueError(f"keltner style {style!r} (have {', '.join(self.STYLES)})")
        self.n, self.mult, self.m, self.style = int(n), float(mult), int(m), style
        super().__init__()

    def initial(self):
        return (None, ((), None), ((), None))   # previous close, the EMA, the band's rma

    def step(self, st, bar):
        pc, e, r = st
        e, mid = _smooth(e, bar.c, self.n, 2.0 / (self.n + 1))
        if self.style == "tr":
            band = _tr(bar, pc)
        elif self.style == "atr":
            r, band = _smooth(r, _tr(bar, pc), self.m, 1.0 / self.m)
        else:
            r, band = _smooth(r, bar.h - bar.l, self.n, 1.0 / self.n)
        st = (bar.c, e, r)
        if mid is None or band is None:
            return st, None
        return st, {"mid": mid, "up": mid + self.mult * band, "dn": mid - self.mult * band}


class Donchian(_Study):
    def __init__(self, n: int = 20):
        self.n = int(n)
        super().__init__()

    def step(self, w, bar):
        w = (w + ((bar.h, bar.l),))[-self.n:]
        if len(w) < self.n:
            return w, None
        up, dn = max(h for h, _ in w), min(l for _, l in w)
        return w, {"up": up, "dn": dn, "mid": (up + dn) / 2.0}


class Supertrend(_Study):
    def __init__(self, n: int = 10, mult: float = 3.0):
        self.n, self.mult = int(n), float(mult)
        super().__init__()

    def initial(self):
        # previous close, the ATR's rma, the previous bar's lower / upper band (nz: 0 while the ATR is na), its direction
        return (None, ((), None), 0.0, 0.0, None)

    def step(self, st, bar):
        pc, a, plo, pup, pdir = st
        a, atr = _smooth(a, _tr(bar, pc), self.n, 1.0 / self.n)
        if atr is None:
            return (bar.c, a, 0.0, 0.0, None), None
        mid = (bar.h + bar.l) / 2.0
        lo, up = mid - self.mult * atr, mid + self.mult * atr
        if not (lo > plo or (pc is not None and pc < plo)):
            lo = plo
        if not (up < pup or (pc is not None and pc > pup)):
            up = pup
        if pdir is None:                        # na(atr[1]): the first bar with a band starts down
            d = 1
        elif pdir == 1:
            d = -1 if bar.c > up else 1
        else:
            d = 1 if bar.c < lo else -1
        return (bar.c, a, lo, up, d), {"line": lo if d == -1 else up, "dir": d}


class TEMA(_MA):
    def initial(self):
        return (((), None), ((), None), ((), None))

    def step(self, st, bar):
        a = 2.0 / (self.n + 1)
        e1, v1 = _smooth(st[0], self.src(bar), self.n, a)
        e2, v2 = _smooth(st[1], v1, self.n, a)
        e3, v3 = _smooth(st[2], v2, self.n, a)
        return (e1, e2, e3), (None if v3 is None else 3 * (v1 - v2) + v3)


class MFI(_Study):
    def __init__(self, n: int = 14):
        self.n = int(n)
        super().__init__()

    def step(self, w, bar):
        w = (w + (((bar.h + bar.l + bar.c) / 3.0, bar.v),))[-(self.n + 1):]
        if len(w) < self.n + 1:
            return w, None
        up = sum(p1 * v1 for (p0, _), (p1, v1) in zip(w, w[1:]) if p1 > p0)
        dn = sum(p1 * v1 for (p0, _), (p1, v1) in zip(w, w[1:]) if p1 < p0)
        # Pine's 100 - 100 / (1 + up / dn) read as IEEE (x / 0 = inf -> 100, 0 / 0 = nan -> na); no TV export has settled it
        return w, (None if dn == 0 and up == 0 else 100.0 if dn == 0 else 100.0 - 100.0 / (1.0 + up / dn))


class VWAP(_Study):
    ANCHORS = ("session", "week", "month", "quarter", "year")

    def __init__(self, anchor: str = "session"):
        if anchor not in self.ANCHORS:
            raise ValueError(f"vwap anchor {anchor!r} (have {', '.join(self.ANCHORS)})")
        self.anchor = anchor
        super().__init__()

    def initial(self):
        return (None, 0.0, 0.0, 0)   # period, sum(hlc3 v), sum(hlc3^2 v), sum v

    def _period(self, bar):
        if self.anchor == "session":
            return bar.session
        if self.anchor == "week":
            return week_key(bar.session)
        y, m = month_key(bar.session)
        return (y, m) if self.anchor == "month" else (y, (m - 1) // 3) if self.anchor == "quarter" else y

    def step(self, st, bar):
        key = self._period(bar)
        _, pv, p2v, v = st if st[0] == key else (key, 0.0, 0.0, 0)
        p = (bar.h + bar.l + bar.c) / 3.0
        pv, p2v, v = pv + p * bar.v, p2v + p * p * bar.v, v + bar.v
        st = (key, pv, p2v, v)
        if not v:
            return st, None
        vw = pv / v
        sd = math.sqrt(max(p2v / v - vw * vw, 0.0))
        return st, {"vwap": vw, "u1": vw + sd, "l1": vw - sd, "u2": vw + 2 * sd, "l2": vw - 2 * sd,
                    "u3": vw + 3 * sd, "l3": vw - 3 * sd}


def _side(st, bar):
    """TV's up / down volume rule on one bar: (previous close, previous side) -> (new state, side +1 / -1; 0 only while no
    bar has shown a side)."""
    pc, ps = st
    if bar.c > bar.o:
        s = 1
    elif bar.c < bar.o:
        s = -1
    elif pc is None or bar.c == pc:
        s = ps
    else:
        s = 1 if bar.c > pc else -1
    return (bar.c, s), s


class CVD(_Study):
    def initial(self):
        return (None, 0, (None, 0))   # session, its running delta, the side rule's state

    def step(self, st, bar):
        sess, cum, side = st
        if bar.session != sess:
            sess, cum = bar.session, 0
        side, s = _side(side, bar)
        c = cum + s * bar.v
        return (sess, c, side), {"o": cum, "h": max(cum, c), "l": min(cum, c), "c": c}


class VolumeDelta(_Study):
    def initial(self):
        return (None, 0)

    def step(self, st, bar):
        st, s = _side(st, bar)
        d = s * bar.v
        return st, {"o": 0, "h": max(0, d), "l": min(0, d), "c": d}


class UpDown(_Study):
    def initial(self):
        return (None, 0)

    def step(self, st, bar):
        st, s = _side(st, bar)
        up, dn = (bar.v if s > 0 else 0), (-bar.v if s < 0 else 0)
        return st, {"up": up, "down": dn, "delta": up + dn}


def _since_open(bar) -> int:
    """Seconds since the session opened (18:00 ET)."""
    et = dt.datetime.fromtimestamp(bar.t / 1000, ET)
    return (et.hour * 3600 + et.minute * 60 + et.second - 18 * 3600) % 86400


class RelVolumeAtTime(_Study):
    MODES = ("cumulative", "regular")

    def __init__(self, n: int = 14, mode: str = "cumulative"):
        if mode not in self.MODES:
            raise ValueError(f"rvol mode {mode!r} (have {', '.join(self.MODES)})")
        self.n, self.mode = int(n), mode
        super().__init__()

    def initial(self):
        # session, its (seconds since open, volume) rows so far, its volume so far, the finished sessions' rows (newest last)
        return (None, (), 0, ())

    def step(self, st, bar):
        sess, rows, cum, done = st
        if bar.session != sess:
            if sess is not None:
                done = (done + (rows,))[-self.n:]
            sess, rows, cum = bar.session, (), 0
        off = _since_open(bar)
        cum += bar.v
        x = cum if self.mode == "cumulative" else bar.v
        rows = rows + ((off, x),)
        past = []
        for r in done:                          # each session's last bar at or before this time of day
            i = bisect.bisect_right(r, (off, math.inf))
            if i:
                past.append(r[i - 1][1])
        st = (sess, rows, cum, done)
        if not past:
            return st, None
        m = sum(past) / len(past)
        return st, (x / m if m > 0 else None)


class ADR(_Study):
    def __init__(self, n: int = 14):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return (None, None, None, ())   # session, its high, low, the finished sessions' ranges

    def step(self, st, bar):
        sess, h, l, done = st
        if bar.session != sess:
            if sess is not None:
                done = (done + (h - l,))[-self.n:]
            sess, h, l = bar.session, bar.h, bar.l
        else:
            h, l = max(h, bar.h), min(l, bar.l)
        return (sess, h, l, done), (sum(done) / self.n if len(done) == self.n else None)


def _pivot_levels(kind, po, h, l, c, o):
    """TradingView's Pivot Points Standard from the prior period's open po, high h, low l and close c, and this
    period's open o (Woodie). Camarilla's R5 / S5 and Woodie's R3 / R4 are from memory: verify on the export."""
    r = h - l
    if kind == "dm":
        x = h + 2 * l + c if c < po else 2 * h + l + c if c > po else h + l + 2 * c
        return {"p": x / 4, "r1": x / 2 - l, "s1": x / 2 - h}
    if kind == "woodie":
        p = (h + l + 2 * o) / 4
        r3, s3 = h + 2 * (p - l), l - 2 * (h - p)
        return {"p": p, "r1": 2 * p - l, "s1": 2 * p - h, "r2": p + r, "s2": p - r, "r3": r3, "s3": s3,
                "r4": r3 + r, "s4": s3 - r}
    p = (h + l + c) / 3
    if kind == "fibonacci":
        return {"p": p, "r1": p + 0.382 * r, "s1": p - 0.382 * r, "r2": p + 0.618 * r, "s2": p - 0.618 * r,
                "r3": p + r, "s3": p - r}
    if kind == "camarilla":
        k, r5 = 1.1 * r, h / l * c
        return {"p": p, "r1": c + k / 12, "s1": c - k / 12, "r2": c + k / 6, "s2": c - k / 6, "r3": c + k / 4,
                "s3": c - k / 4, "r4": c + k / 2, "s4": c - k / 2, "r5": r5, "s5": c - (r5 - c)}
    if kind == "classic":
        return {"p": p, "r1": 2 * p - l, "s1": 2 * p - h, "r2": p + r, "s2": p - r, "r3": p + 2 * r, "s3": p - 2 * r,
                "r4": p + 3 * r, "s4": p - 3 * r}
    return {"p": p, "r1": 2 * p - l, "s1": 2 * p - h, "r2": p + r, "s2": p - r, "r3": 2 * p + (h - 2 * l),
            "s3": 2 * p - (2 * h - l), "r4": 3 * p + (h - 3 * l), "s4": 3 * p - (3 * h - l), "r5": 4 * p + (h - 4 * l),
            "s5": 4 * p - (4 * h - l)}


class Pivots(_Study):
    """The prior SESSION's levels (TV's Auto anchor is 1D on charts up to 15 minutes). The close is the session's last
    trade. TODO: TV's daily close for futures is the settlement, which Homebase has no source for."""
    TYPES = ("traditional", "fibonacci", "woodie", "classic", "dm", "camarilla")

    def __init__(self, kind: str = "traditional"):
        if kind not in self.TYPES:
            raise ValueError(f"pivots type {kind!r} (have {', '.join(self.TYPES)})")
        self.kind = kind
        super().__init__()

    def initial(self):
        return (None, None, None, None, None, None)   # session, its open, high, low, close, the prior session's (o, h, l, c)

    def step(self, st, bar):
        sess, o, h, l, c, prev = st
        if bar.session != sess:
            if sess is not None:
                prev = (o, h, l, c)
            sess, o, h, l = bar.session, bar.o, bar.h, bar.l
        else:
            h, l = max(h, bar.h), min(l, bar.l)
        st = (sess, o, h, l, bar.c, prev)
        return st, (None if prev is None else _pivot_levels(self.kind, *prev, o))


class PivotHL(_Study):
    """ta.pivothigh / ta.pivotlow: the bar `right` bars back is strictly beyond the `left` bars before it and the `right`
    after it (the tie rule is from memory: verify on the export)."""

    def __init__(self, left: int = 10, right: int = 10):
        self.left, self.right = int(left), int(right)
        super().__init__()

    def step(self, w, bar):
        w = (w + ((bar.h, bar.l),))[-(self.left + self.right + 1):]
        if len(w) < self.left + self.right + 1:
            return w, None
        i = self.left
        h, l = w[i]
        hi = h if all(x < h for j, (x, _) in enumerate(w) if j != i) else None
        lo = l if all(y > l for j, (_, y) in enumerate(w) if j != i) else None
        return w, (None if hi is None and lo is None else {"hi": hi, "lo": lo})


class TWAP(_Study):
    def __init__(self, source: str = "ohlc4"):
        self.src = _source(source)
        super().__init__()

    def initial(self):
        return (None, 0.0, 0)   # session, the sum of the source, bars

    def step(self, st, bar):
        sess, tot, k = st if st[0] == bar.session else (bar.session, 0.0, 0)
        tot, k = tot + self.src(bar), k + 1
        return (sess, tot, k), tot / k


# name -> (class, parameters): a number is (default, minimum, maximum), a word is (default, its choices); a wire key
# may give them in order. The defaults are TradingView's.
_SRC = ("close", tuple(SOURCES))
PARAMS = {
    "sma": (SMA, ((9, 1, 1000), _SRC)),
    "ema": (EMA, ((9, 1, 1000), _SRC)),
    "rma": (RMA, ((7, 1, 1000), _SRC)),
    "wma": (WMA, ((9, 1, 1000), _SRC)),
    "rsi": (RSI, ((14, 1, 1000), _SRC)),
    "macd": (MACD, ((12, 1, 1000), (26, 1, 1000), (9, 1, 1000), _SRC)),
    "stoch": (Stochastic, ((14, 1, 1000), (1, 1, 1000), (3, 1, 1000))),
    "adx": (ADX, ((14, 1, 1000), (14, 1, 1000))),
    "atr": (ATR, ((14, 1, 1000),)),
    "bb": (Bollinger, ((20, 1, 1000), (2.0, 0.001, 50), _SRC)),
    "keltner": (Keltner, ((20, 1, 1000), (2.0, 0.001, 50), (10, 1, 1000), ("atr", Keltner.STYLES))),
    "donchian": (Donchian, ((20, 1, 1000),)),
    "supertrend": (Supertrend, ((10, 1, 1000), (3.0, 0.01, 100))),
    "tema": (TEMA, ((9, 1, 1000), _SRC)),
    "mfi": (MFI, ((14, 1, 1000),)),
    "vwap": (VWAP, (("session", VWAP.ANCHORS),)),
    "cvd": (CVD, ()),
    "vdelta": (VolumeDelta, ()),
    "updown": (UpDown, ()),
    "rvol": (RelVolumeAtTime, ((14, 1, 60), ("cumulative", RelVolumeAtTime.MODES))),
    "adr": (ADR, ((14, 1, 250),)),
    "pivots": (Pivots, (("traditional", Pivots.TYPES),)),
    "pivothl": (PivotHL, ((10, 1, 500), (10, 1, 500))),
    "twap": (TWAP, (("ohlc4", tuple(SOURCES)),)),
}


def make_tv(key: str, tick: float = 0.25):
    """The study of a "tv:<name>[:args]" wire key (this module's PARAMS plus studies_tv2's), or ValueError: an unknown
    name, too many parameters, one not a number, outside its range or not one of its words. `tick` is unused: no tv
    study reads footprint rows."""
    parts = str(key).split(":")
    name, args = (parts[1] if len(parts) > 1 else ""), parts[2:]
    table = {**PARAMS, **PARAMS2}
    if name not in table:
        raise ValueError(f"unknown study {key!r} (tv: {', '.join(sorted(table))})")
    cls, spec = table[name]
    if len(args) > len(spec):
        raise ValueError(f"bad study {key!r}: at most {len(spec)} parameter(s)")
    vals = []
    for i, p in enumerate(spec):
        if len(p) == 2:
            default, words = p
            w = args[i] if i < len(args) else default
            if w not in words:
                raise ValueError(f"bad study {key!r}: parameter {i + 1} is one of {', '.join(words)}")
            vals.append(w)
        else:
            default, lo, hi = p
            x = make_ta_num(name, args, i, default, lo, hi)
            vals.append(int(x) if isinstance(default, int) else x)
    return cls(*vals)


def _num(name, rest, i) -> int:
    """Parameter i of a tv key as an int, or its PARAMS default (0 for a word)."""
    try:
        return int(float(rest[i]))
    except (IndexError, ValueError):
        spec = {**PARAMS, **PARAMS2}.get(name, (None, ()))[1]
        return int(spec[i][0]) if i < len(spec) and len(spec[i]) == 3 else 0


def warm_tv(name: str, rest: list) -> int:
    """Bars after a join that a tv study's value still depends on (hub.warm_bars), as warm_ta: a window's length, 5n for an
    EMA, 10n for a Wilder average; 0 for the session-anchored ones. A studies_tv2 study brings its own WARM function."""
    if name in ("sma", "wma", "bb", "donchian"):
        return _num(name, rest, 0)
    if name == "ema":
        return 5 * _num(name, rest, 0)
    if name == "tema":
        return 15 * _num(name, rest, 0)
    if name in ("rma", "rsi", "atr", "supertrend"):
        return 10 * _num(name, rest, 0)
    if name == "macd":
        return 5 * max(_num(name, rest, 0), _num(name, rest, 1)) + 5 * _num(name, rest, 2)     # the longer of the two EMAs
    if name == "stoch":
        return _num(name, rest, 0) + _num(name, rest, 1) + _num(name, rest, 2)
    if name == "adx":
        return 10 * (_num(name, rest, 0) + _num(name, rest, 1))
    if name == "keltner":
        return 5 * _num(name, rest, 0) + 10 * _num(name, rest, 2)
    if name == "mfi":
        return _num(name, rest, 0) + 1
    if name == "pivothl":
        return _num(name, rest, 0) + _num(name, rest, 1) + 1
    if name in WARM2:
        return WARM2[name](list(rest))
    if name in PARAMS:
        return 0
    return 10 * _num(name, rest, 0)


def prime_tv(name: str, rest: list, root: str | None = None) -> int:
    """Completed sessions BEFORE the loaded ones a tv study must be fed first (hub.prime_sessions): the relative volume's
    and daily range's n sessions, the pivots' one, and the most a week's or a month's VWAP can have behind the first
    loaded session -- 4 / 22 on a classic root (five sessions a week, 23 weekdays a month), 6 / 30 on a 24/7 one (a session
    every calendar day). A quarter's and a year's (64 / 259, 92 / 366 on a 24/7 root) are not primed: those count the
    sessions the chart loaded."""
    if name in ("rvol", "adr"):
        return _num(name, rest, 0) + 1
    if name == "vwap":
        week, month = (6, 30) if always_open(root) else (4, 22)
        return {"week": week, "month": month}.get(rest[0] if rest else "", 0)
    if name in PRIME2:
        return PRIME2[name](list(rest)) if callable(PRIME2[name]) else PRIME2[name]
    return 1 if name == "pivots" else 0
