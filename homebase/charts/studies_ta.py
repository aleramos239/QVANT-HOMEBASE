"""The chart's technical-analysis studies, each the SAME definition the strategy engine uses
(research/edge-library/engine: indicators.py, families/blocks.py, families/port1.py, families/port2.py), so a line on
the chart is the line a strategy's filter or trigger reads. Pure; the Study contract of studies.py (push / preview,
immutable state, None while warming up).

Wire keys (every part after the name is a number; a missing one takes its default):
  rsi:14            Wilder RSI, the first average = the mean of the first n changes            -> float
  macd:12:26:9      EMA(fast) - EMA(slow), its EMA(signal), the histogram                       -> {macd, signal, hist}
  bb:20:2           Bollinger bands: mean +/- k population standard deviations of the closes    -> {mid, up, dn}
  atr:14            Wilder ATR, seeded with the mean of the first n true ranges                 -> float
  stoch:14:3:3      %K over n bars, smoothed, and %D = SMA of the smoothed %K                    -> {k, d}
  supertrend:10:3   the ATR(10)-band trend line of port2.Supertrend, band = hl2 +/- mult x ATR   -> {line, dir}
  donchian:20       highest high / lowest low of the last n bars, this one included             -> {up, dn, mid}
  keltner:20:20:1.5 EMA(n) +/- mult x SMA(true range, m): port1's squeeze channel                -> {mid, up, dn}
  tema:20           triple EMA: 3 e1 - 3 e2 + e3                                                -> float
  mfi:14            Money Flow Index of the last n bars                                         -> float
  er:14             Kaufman efficiency ratio of the last n steps (0 .. 1)                       -> float
  orb:15            the first n minutes from 09:30 ET: high, low, mid, growing until n is up    -> {hi, lo, mid}
  orb:5:180         the same from another start: the 2nd number is the start minute of the ET day (180 = 03:00).
                    A start at 18:00 or later is the evening BEFORE the session's date (its candle opens the session)
  sess:london       high / low of a named session window so far today (asia 00:00-03:00, london 03:00-08:25,
                    pre 08:25-09:30, nyam 09:30-11:00; ET), kept through the rest of the day  -> {hi, lo}
  sess:1080:180     high / low of a window of your own: start and end as ET minutes of the day (1080 = 18:00); an end
                    before the start crosses midnight; one at 18:00 or later is the evening before the session  -> {hi, lo}
  fvg:0.25:14       the newest unfilled fair value gap each side, of the chart's own bars, inside the session: three
                    bars where bar 3's low is above bar 1's high (up) or the mirror (down), at least k x ATR(n) high:
                    families/fvg.py's rule. A gap ends when a later bar trades through its far edge -> {uh, ul, dh, dl}
  wk / mo           the PRIOR week's / month's high, low and close, and the open of this one (the session dates'
                    ISO week / calendar month)                                                -> {hi, lo, close, open}
  topen:0           the open price at a time of the ET day (0 = midnight; same start rule as orb), held from then
                    until the session ends                                                    -> float

Structure (engine/levels.py pivots, ranges.py, zones.py, families/round1.py va_reclaim, families/noise.py):
  swing:50          the latest swing high / low no later bar traded beyond; a swing is a bar strictly above / below
                    the n bars before AND the n after it, so it is known n bars later          -> {hi, lo}
  equal:50:10       the latest equal high / low: two consecutive swings within `tol` points, the second not beyond the
                    first, nothing between them beyond it, and no bar since beyond the level   -> {hi, lo}
  rmove:200         the move in progress: a zigzag of N points; its range, middle and OTE band   -> {hi, lo, mid, ote1, ote2, dir}
  rswing:50         the range between the latest untouched swing high and swing low, same value
  vaprev            the PRIOR session's 09:30-16:00 value area (70 %) and point of control      -> {vah, val, poc}
  noise:0.3:rth     open +/- k x the daily ATR(14) of the sessions before: families/noise.py   -> {up, dn}
  rvol:14:10        bar volume over the median of the same clock bar on the n days before     -> float
  dhl:5             highest high / lowest low of the last n completed sessions                -> {hi, lo}
"""
from __future__ import annotations

import datetime as dt
import math

from .session import ET


def _et(bar) -> dt.datetime:
    return dt.datetime.fromtimestamp(bar.t / 1000, ET)


def _mean(xs) -> float:
    return sum(xs) / len(xs)


class _Study:
    """Study's contract, restated so this module does not import studies.py (which imports it)."""

    def __init__(self):
        self.state = self.initial()

    def initial(self) -> tuple:
        return ()

    def step(self, state: tuple, bar):
        raise NotImplementedError

    def push(self, bar):
        self.state, v = self.step(self.state, bar)
        return v

    def preview(self, bar):
        return self.step(self.state, bar)[1]


class RSI(_Study):
    def __init__(self, n: int = 14):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return (None, 0, 0.0, 0.0)   # previous close, changes seen, average gain, average loss

    def step(self, st, bar):
        pc, k, g, l = st
        c = bar.c
        if pc is None:
            return (c, 0, 0.0, 0.0), None
        d = c - pc
        gain, loss = (d, 0.0) if d > 0 else (0.0, -d)
        n = self.n
        if k < n:                                   # still adding up the first n changes
            k, g, l = k + 1, g + gain, l + loss
            if k < n:
                return (c, k, g, l), None
            g, l = g / n, l / n
        else:
            k, g, l = k + 1, (g * (n - 1) + gain) / n, (l * (n - 1) + loss) / n
        return (c, k, g, l), (50.0 if g + l == 0 else 100.0 * g / (g + l))


class MACD(_Study):
    def __init__(self, fast: int = 12, slow: int = 26, sig: int = 9):
        self.fast, self.slow, self.sig = int(fast), int(slow), int(sig)
        self.kf, self.ks, self.kg = (2.0 / (n + 1) for n in (self.fast, self.slow, self.sig))
        super().__init__()

    def initial(self):
        return (0, None, None, None)   # bars seen, fast EMA, slow EMA, signal EMA of the MACD line

    def step(self, st, bar):
        i, f, s, sg = st
        c = bar.c
        f = c if f is None else f + self.kf * (c - f)
        s = c if s is None else s + self.ks * (c - s)
        i += 1
        if i < self.slow:
            return (i, f, s, sg), None
        m = f - s
        sg = m if sg is None else sg + self.kg * (m - sg)
        if i < self.slow + self.sig - 1:
            return (i, f, s, sg), {"macd": m, "signal": None, "hist": None}
        return (i, f, s, sg), {"macd": m, "signal": sg, "hist": m - sg}


class Bollinger(_Study):
    def __init__(self, n: int = 20, k: float = 2.0):
        self.n, self.k = int(n), float(k)
        super().__init__()

    def step(self, st, bar):
        w = (st + (bar.c,))[-self.n:]
        if len(w) < self.n:
            return w, None
        mid = _mean(w)
        sd = math.sqrt(sum((x - mid) ** 2 for x in w) / self.n)
        return w, {"mid": mid, "up": mid + self.k * sd, "dn": mid - self.k * sd}


def _true_range(bar, pc) -> float:
    return bar.h - bar.l if pc is None else max(bar.h - bar.l, abs(bar.h - pc), abs(bar.l - pc))


class ATR(_Study):
    def __init__(self, n: int = 14):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return (None, 0, 0.0, None)   # previous close, bars seen, running sum of the first n TRs, the ATR

    def step(self, st, bar):
        pc, k, total, a = st
        tr = _true_range(bar, pc)
        if a is None:
            k, total = k + 1, total + tr
            if k < self.n:
                return (bar.c, k, total, None), None
            a = total / self.n
        else:
            a = (a * (self.n - 1) + tr) / self.n
        return (bar.c, k, total, a), a


class Stochastic(_Study):
    def __init__(self, n: int = 14, smooth: int = 3, d: int = 3):
        self.n, self.smooth, self.d = int(n), int(smooth), int(d)
        super().__init__()

    def initial(self):
        return ((), (), ())   # (high, low) window, raw %K window, smoothed %K window

    def step(self, st, bar):
        hl, raw, slow = st
        hl = (hl + ((bar.h, bar.l),))[-self.n:]
        if len(hl) < self.n:
            return (hl, raw, slow), None
        hi, lo = max(h for h, _ in hl), min(l for _, l in hl)
        x = 50.0 if hi == lo else 100.0 * (bar.c - lo) / (hi - lo)
        raw = (raw + (x,))[-self.smooth:]
        if len(raw) < self.smooth:
            return (hl, raw, slow), None
        k = _mean(raw)
        slow = (slow + (k,))[-self.d:]
        return (hl, raw, slow), {"k": k, "d": _mean(slow) if len(slow) == self.d else None}


class Supertrend(_Study):
    """port2.Supertrend with the day restart left out: one unbroken line along the chart. The ATR is the mean of the
    first n true ranges, then Wilder's smoothing."""

    def __init__(self, n: int = 10, mult: float = 3.0):
        self.n, self.mult = int(n), float(mult)
        super().__init__()

    def initial(self):
        return (None, 0, 0.0, None, None, None, 1)   # prev close, bars seen, TR sum, ATR, upper-support, lower-resistance, dir

    def step(self, st, bar):
        pc, k, total, a, up, dn, dr = st
        tr = _true_range(bar, pc)
        k += 1
        if a is None:
            total += tr
            if k < self.n:
                return (bar.c, k, total, None, None, None, dr), None
            a = total / self.n
        else:
            a = (a * (self.n - 1) + tr) / self.n
        mid = (bar.h + bar.l) / 2.0
        nup, ndn = mid - self.mult * a, mid + self.mult * a
        if up is not None:
            if pc > up:
                nup = max(nup, up)
            if pc < dn:
                ndn = min(ndn, dn)
            if dr == -1 and bar.c > dn:
                dr = 1
            elif dr == 1 and bar.c < up:
                dr = -1
        return (bar.c, k, total, a, nup, ndn, dr), {"line": nup if dr == 1 else ndn, "dir": dr}


class Donchian(_Study):
    def __init__(self, n: int = 20):
        self.n = int(n)
        super().__init__()

    def step(self, st, bar):
        w = (st + ((bar.h, bar.l),))[-self.n:]
        if len(w) < self.n:
            return w, None
        up, dn = max(h for h, _ in w), min(l for _, l in w)
        return w, {"up": up, "dn": dn, "mid": (up + dn) / 2.0}


class Keltner(_Study):
    def __init__(self, n: int = 20, m: int = 20, mult: float = 1.5):
        self.n, self.m, self.mult = int(n), int(m), float(mult)
        self.a = 2.0 / (self.n + 1)
        super().__init__()

    def initial(self):
        return (None, None, ())   # previous close, EMA, true-range window

    def step(self, st, bar):
        pc, e, trs = st
        e = bar.c if e is None else e + self.a * (bar.c - e)
        trs = (trs + (_true_range(bar, pc),))[-self.m:]
        new = (bar.c, e, trs)
        if len(trs) < self.m:
            return new, None
        w = self.mult * _mean(trs)
        return new, {"mid": e, "up": e + w, "dn": e - w}


class TEMA(_Study):
    def __init__(self, n: int = 20):
        self.n = int(n)
        self.a = 2.0 / (self.n + 1)
        super().__init__()

    def initial(self):
        return (0, None, None, None)

    def step(self, st, bar):
        i, e1, e2, e3 = st
        c = bar.c
        e1 = c if e1 is None else e1 + self.a * (c - e1)
        e2 = e1 if e2 is None else e2 + self.a * (e1 - e2)
        e3 = e2 if e3 is None else e3 + self.a * (e2 - e3)
        i += 1
        return (i, e1, e2, e3), (3 * e1 - 3 * e2 + e3 if i >= self.n else None)


class MFI(_Study):
    def __init__(self, n: int = 14):
        self.n = int(n)
        super().__init__()

    def step(self, st, bar):
        w = (st + (((bar.h + bar.l + bar.c) / 3.0, bar.v),))[-(self.n + 1):]
        if len(w) < self.n + 1:
            return w, None
        pos = neg = 0.0
        for (p0, _), (p1, v1) in zip(w, w[1:]):
            if p1 > p0:
                pos += p1 * v1
            elif p1 < p0:
                neg += p1 * v1
        return w, (None if pos + neg == 0 else 100.0 * pos / (pos + neg))


class Efficiency(_Study):
    def __init__(self, n: int = 14):
        self.n = int(n)
        super().__init__()

    def step(self, st, bar):
        w = (st + (bar.c,))[-(self.n + 1):]
        if len(w) < self.n + 1:
            return w, None
        path = sum(abs(b - a) for a, b in zip(w, w[1:]))
        return w, (None if path == 0 else abs(w[-1] - w[0]) / path)




def _window_start(session: str, minute: int) -> dt.datetime:
    """The ET time a window that starts at `minute` of the ET day begins, for the session keyed `session` (its date). The
    session opens the evening before: a start at 18:00 or later falls on the previous calendar day."""
    d = dt.date.fromisoformat(session)
    if minute >= 18 * 60:
        d -= dt.timedelta(days=1)
    return dt.datetime(d.year, d.month, d.day, minute // 60, minute % 60, tzinfo=ET)


class OpeningRange(_Study):
    """High / low of the first `minutes` from 09:30 ET on the session's own day. The range GROWS while the window
    is open (so the lines show the developing range) and is frozen after it; None before 09:30. A bar counts when
    it starts inside the window."""

    def __init__(self, minutes: int = 15, start: int = 9 * 60 + 30):
        self.minutes, self.start = int(minutes), int(start)
        super().__init__()

    def initial(self):
        return (None, None, None)   # session, high, low

    def step(self, st, bar):
        sess, hi, lo = st
        if sess != bar.session:
            sess, hi, lo = bar.session, None, None
        t = _et(bar)
        w0 = _window_start(bar.session, self.start)
        if w0 <= t < w0 + dt.timedelta(minutes=self.minutes):
            hi = bar.h if hi is None else max(hi, bar.h)
            lo = bar.l if lo is None else min(lo, bar.l)
        return (sess, hi, lo), self._val(hi, lo)

    @staticmethod
    def _val(hi, lo):
        return None if hi is None else {"hi": hi, "lo": lo, "mid": (hi + lo) / 2.0}


# name -> (start minute, end minute) ET, the window a named session covers (bp.py's session table)
SESSIONS = {"asia": (0, 180), "london": (180, 8 * 60 + 25), "pre": (8 * 60 + 25, 9 * 60 + 30), "nyam": (9 * 60 + 30, 11 * 60)}


class SessionRange(_Study):
    """High / low of one named window since it began today (ET calendar day), held through the rest of that day;
    None before the window starts, and from the next midnight until it starts again."""

    def __init__(self, name: str = "london"):
        if name not in SESSIONS:
            raise ValueError(f"session {name!r} (have {', '.join(SESSIONS)})")
        self.name = name
        self.a, self.b = SESSIONS[name]
        super().__init__()

    def initial(self):
        return (None, None, None)   # ET date, high, low

    def step(self, st, bar):
        day, hi, lo = st
        t = _et(bar)
        d = t.date()
        if day != d:
            day, hi, lo = d, None, None
        minute = t.hour * 60 + t.minute
        if self.a <= minute < self.b:
            hi = bar.h if hi is None else max(hi, bar.h)
            lo = bar.l if lo is None else min(lo, bar.l)
        return (day, hi, lo), (None if hi is None else {"hi": hi, "lo": lo})



class WindowRange(_Study):
    """High / low of a window of the ET day that you choose (`a` .. `b` minutes; `b` <= `a` crosses midnight), per session,
    growing while it is open and held after it, like the named sessions. A window starting at 18:00 or later is the
    evening before the session's date. None until it opens."""

    def __init__(self, a: int, b: int):
        if a == b:
            raise ValueError("bad study 'sess': a window needs a start and an end that differ")
        self.a, self.length = int(a), (int(b) - int(a)) % 1440
        super().__init__()

    def initial(self):
        return (None, None, None)   # session, high, low

    def step(self, st, bar):
        sess, hi, lo = st
        if sess != bar.session:
            sess, hi, lo = bar.session, None, None
        w0 = _window_start(bar.session, self.a)
        if w0 <= _et(bar) < w0 + dt.timedelta(minutes=self.length):
            hi = bar.h if hi is None else max(hi, bar.h)
            lo = bar.l if lo is None else min(lo, bar.l)
        return (sess, hi, lo), (None if hi is None else {"hi": hi, "lo": lo})


class FairValueGap(_Study):
    """families/fvg.py's gap on the chart's own bars: three bars of the session, bar 3's low above bar 1's high (an up gap)
    or bar 3's high below bar 1's low (down), at least `k` x ATR(`n`) high and never less than a tick. Per side the
    NEWEST gap not yet filled: a later bar trading through its far edge ends it. The gap is known at bar 3's close."""

    def __init__(self, k: float = 0.25, n: int = 14, tick: float = 0.25):
        self.k, self.n, self.tick = float(k), int(n), float(tick)
        super().__init__()

    def initial(self):
        # session, the bars so far of it ((h, l) newest last, at most 3), ATR state (prev close, count, sum, atr), up gap, down gap
        return (None, (), (None, 0, 0.0, None), None, None)

    def step(self, st, bar):
        sess, hl, (pc, nt, tsum, atr), up, dn = st
        if bar.session != sess:
            sess, hl, up, dn = bar.session, (), None, None
        # the gap still open ends when this bar trades through its far edge (the bar that forms a gap is not a fill)
        if up is not None and bar.l <= up[1]:
            up = None
        if dn is not None and bar.h >= dn[0]:
            dn = None
        hl = (hl + ((bar.h, bar.l),))[-3:]
        if len(hl) == 3 and atr is not None:
            (h1, l1), (h3, l3) = hl[0], hl[2]
            if l3 > h1 and l3 - h1 >= max(self.k * atr, self.tick):
                up = (l3, h1)                                  # (near edge, far edge): the zone is far..near
            elif h3 < l1 and l1 - h3 >= max(self.k * atr, self.tick):
                dn = (l1, h3)
        if pc is not None:                                     # Wilder ATR, seeded with the mean of the first n ranges
            tr = _true_range(bar, pc)
            nt += 1
            if nt <= self.n:
                tsum += tr
                if nt == self.n:
                    atr = tsum / self.n
            else:
                atr = (atr * (self.n - 1) + tr) / self.n
        st = (sess, hl, (bar.c, nt, tsum, atr), up, dn)
        if up is None and dn is None:
            return st, None
        return st, {"uh": up[0] if up else None, "ul": up[1] if up else None,
                    "dh": dn[0] if dn else None, "dl": dn[1] if dn else None}


class PeriodLevels(_Study):
    """The PRIOR period's high, low and close and the open of the current one, the period being a week or a month of
    session dates. None until a period has finished (the first value comes with the second period's first bar)."""
    KEY = None

    def initial(self):
        # current period key, its open / high / low / last close, the finished period's (high, low, close)
        return (None, None, None, None, None, None)

    def period(self, session: str):
        raise NotImplementedError

    def step(self, st, bar):
        per, op, h, l, c, prev = st
        k = self.period(bar.session)
        if k != per:
            if per is not None:
                prev = (h, l, c)
            per, op, h, l = k, bar.o, bar.h, bar.l
        else:
            h, l = max(h, bar.h), min(l, bar.l)
        c = bar.c
        st = (per, op, h, l, c, prev)
        if prev is None:
            return st, None
        return st, {"hi": prev[0], "lo": prev[1], "close": prev[2], "open": op}


class WeekLevels(PeriodLevels):
    def period(self, session):
        y, w, _ = dt.date.fromisoformat(session).isocalendar()
        return (y, w)


class MonthLevels(PeriodLevels):
    def period(self, session):
        return session[:7]


class TimeOpen(_Study):
    """The open price at a time of the ET day (`minute`, same start rule as the windows): the first bar starting at or
    after it, at most 5 minutes late, held until the session ends. None before it or when no bar came near it."""

    def __init__(self, minute: int = 0):
        self.minute = int(minute)
        super().__init__()

    def initial(self):
        return (None, None, False)   # session, the open, gave up

    def step(self, st, bar):
        sess, px, dead = st
        if sess != bar.session:
            sess, px, dead = bar.session, None, False
        if px is None and not dead:
            late = (_et(bar) - _window_start(bar.session, self.minute)).total_seconds() / 60.0
            if late >= 0:
                if late <= 5:
                    px = bar.o
                else:
                    dead = True
        return (sess, px, dead), px


# ---- structure ----------------------------------------------------------------------------------------------------
_NEG = float("-inf")


def _side_initial():
    return ((), 0, None, _NEG, (), ())     # window, bars seen, previous swing (index, y), max since it, untouched swings, live equals


def _side_step(st, y, n, tol):
    """One side of the pivots (a low side is run on y = -low). `swings` are the swings no later bar went beyond,
    `eqs` the equal levels no bar went beyond since their second swing (engine/levels.py pivots, equal_pairs)."""
    win, i, prev, runmax, swings, eqs = st
    if swings:
        swings = tuple(s for s in swings if y <= s[1])
    if eqs:
        eqs = tuple(e for e in eqs if y <= e)
    win = (win + (y,))[-(2 * n + 1):]
    i += 1
    if prev is not None and y > runmax:
        runmax = y
    if len(win) == 2 * n + 1:
        c = win[n]
        if c > max(win[:n]) and c > max(win[n + 1:]):
            if prev is not None and 0 <= prev[1] - c <= tol and runmax <= prev[1]:
                eqs = (eqs + (prev[1],))[-50:]
            swings = (swings + ((i - 1 - n, c),))[-200:]
            prev = (i - 1 - n, c)
            runmax = max(win[n + 1:])
    return (win, i, prev, runmax, swings, eqs)


class Swing(_Study):
    def __init__(self, n: int = 50):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return (_side_initial(), _side_initial())

    def step(self, st, bar):
        hi, lo = _side_step(st[0], bar.h, self.n, 0.0), _side_step(st[1], -bar.l, self.n, 0.0)
        if not hi[4] and not lo[4]:
            return (hi, lo), None
        return (hi, lo), {"hi": hi[4][-1][1] if hi[4] else None, "lo": -lo[4][-1][1] if lo[4] else None}


class EqualHL(_Study):
    def __init__(self, n: int = 50, tol: float = 10.0):
        self.n, self.tol = int(n), float(tol)
        super().__init__()

    def initial(self):
        return (_side_initial(), _side_initial())

    def step(self, st, bar):
        hi, lo = _side_step(st[0], bar.h, self.n, self.tol), _side_step(st[1], -bar.l, self.n, self.tol)
        if not hi[5] and not lo[5]:
            return (hi, lo), None
        return (hi, lo), {"hi": hi[5][-1] if hi[5] else None, "lo": -lo[5][-1] if lo[5] else None}


OTE_LO, OTE_HI = 0.62, 0.79


def _range_value(lo, hi, d):
    """A dealing range with its middle and the 62 % .. 79 % retracement band of a leg pointing d (+1 up)."""
    r = hi - lo
    if not r > 0:
        return None
    if d == 1:
        a, b = hi - OTE_LO * r, hi - OTE_HI * r
    else:
        a, b = lo + OTE_LO * r, lo + OTE_HI * r
    return {"hi": hi, "lo": lo, "mid": (hi + lo) / 2.0, "ote1": a, "ote2": b, "dir": d}


class RangeMove(_Study):
    """engine/ranges.move: a zigzag of `points`; the range runs from the last turning point to the extreme reached since."""

    def __init__(self, points: float = 200.0):
        self.points = float(points)
        super().__init__()

    def initial(self):
        return (False, 0, None, None, 0.0, 0.0)   # started, mode, running high, running low, pivot, extreme

    def step(self, st, bar):
        started, mode, hi, lo, pv, ex = st
        h, l, thr = bar.h, bar.l, self.points
        if not started:
            return (True, 0, h, l, 0.0, 0.0), None
        if mode == 0:
            hi, lo = max(hi, h), min(lo, l)
            if h - lo >= thr:
                mode, pv, ex = 1, lo, h
            elif hi - l >= thr:
                mode, pv, ex = -1, hi, l
        elif mode == 1:
            if h > ex:
                ex = h
            elif ex - l >= thr:
                mode, pv, ex = -1, ex, l
        else:
            if l < ex:
                ex = l
            elif h - ex >= thr:
                mode, pv, ex = 1, ex, h
        return (True, mode, hi, lo, pv, ex), (None if mode == 0 else _range_value(min(pv, ex), max(pv, ex), mode))


class RangeSwing(_Study):
    """engine/ranges.swing_pair: the latest untouched swing high and swing low (the 5-session limit is left out)."""

    def __init__(self, n: int = 50):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return (_side_initial(), _side_initial())

    def step(self, st, bar):
        hi, lo = _side_step(st[0], bar.h, self.n, 0.0), _side_step(st[1], -bar.l, self.n, 0.0)
        if not hi[4] or not lo[4]:
            return (hi, lo), None
        (a, h), (b, ny) = hi[4][-1], lo[4][-1]
        return (hi, lo), _range_value(-ny, h, 1 if b < a else -1)


def _value_area(vol: dict, share: float = 0.70):
    """(VAL, VAH, POC) as tick rows of a {row: volume} map, engine/families/round1.value_area_of: start at the heaviest row
    (ties: the lowest), add the larger neighbour (equal: both) until `share` of the volume is inside."""
    k0, k1 = min(vol), max(vol)
    rows = [float(vol.get(k0 + i, 0.0)) for i in range(k1 - k0 + 1)]
    tot = sum(rows)
    if tot <= 0:
        return None
    lo = hi = max(range(len(rows)), key=lambda i: (rows[i], -i))
    poc, acc, n = lo, rows[lo], len(rows)
    while acc < share * tot and (lo > 0 or hi < n - 1):
        up = rows[hi + 1] if hi < n - 1 else -1.0
        dn = rows[lo - 1] if lo > 0 else -1.0
        if up >= dn:
            hi += 1
            acc += up
        if dn >= up:
            lo -= 1
            acc += dn
    return k0 + lo, k0 + hi, k0 + poc


_RTH_OPEN, _RTH_CLOSE = dt.time(9, 30), dt.time(16, 0)


class VaPrev(_Study):
    """The prior session's RTH value area. The volume by price comes from each bar's footprint rows."""

    def __init__(self, tick: float = 0.25):
        self.tick = float(tick)
        super().__init__()

    def initial(self):
        return (None, {}, None)   # session, its RTH volume by tick row so far (replaced, never changed in place), last finished value area

    def step(self, st, bar):
        sess, vol, last = st
        if bar.session != sess:
            if vol:
                last = _value_area(vol) or last
            sess, vol = bar.session, {}
        t = _et(bar)
        fp = getattr(bar, "fp", None)
        if fp and t.date().isoformat() == bar.session and _RTH_OPEN <= t.time() < _RTH_CLOSE:
            vol = dict(vol)
            for k, (s, b) in fp.items():
                vol[k] = vol.get(k, 0) + s + b
        out = None if last is None else {"val": round(last[0] * self.tick, 6), "vah": round(last[1] * self.tick, 6),
                                         "poc": round(last[2] * self.tick, 6)}
        return (sess, vol, last), out


class NoiseBand(_Study):
    """families/noise.py: the anchor's open +/- k x the daily ATR(14) of the sessions BEFORE today (none until 15 exist).
    The anchor's open is the first bar starting at or after the anchor, at most 5 minutes late."""

    ANCHOR = {"rth": 9 * 60 + 30, "globex": 60}

    def __init__(self, k: float = 0.3, anchor: str = "rth"):
        if anchor not in self.ANCHOR:
            raise ValueError(f"anchor {anchor!r} (have {', '.join(self.ANCHOR)})")
        self.k, self.anchor, self.am = float(k), anchor, self.ANCHOR[anchor]
        super().__init__()

    def initial(self):
        # session, its high, low, close, the close before it, true ranges so far, their sum, the ATR, the anchor's open, gave up today
        return (None, None, None, None, None, 0, 0.0, None, None, False)

    def step(self, st, bar):
        sess, h, l, c, pc, nt, tsum, atr, ref, dead = st
        if bar.session != sess:
            if sess is not None:                                   # the session that just ended becomes a daily bar
                if pc is not None:
                    tr = max(h - l, abs(h - pc), abs(l - pc))
                    nt += 1
                    if nt <= 14:
                        tsum += tr
                        if nt == 14:
                            atr = tsum / 14.0
                    else:
                        atr = (atr * 13.0 + tr) / 14.0
                pc = c
            sess, h, l, c, ref, dead = bar.session, bar.h, bar.l, bar.c, None, False
        else:
            h, l, c = max(h, bar.h), min(l, bar.l), bar.c
        if ref is None and not dead:
            t = _et(bar)
            late = t.hour * 60 + t.minute - self.am
            if t.date().isoformat() == bar.session and late >= 0:
                if late <= 5:
                    ref = bar.o
                else:
                    dead = True
        new = (sess, h, l, c, pc, nt, tsum, atr, ref, dead)
        if ref is None or atr is None:
            return new, None
        return new, {"up": ref + self.k * atr, "dn": ref - self.k * atr}


class RelVolume(_Study):
    """families/blocks.py rvol: the bar's volume over the median volume of the SAME clock bar on the `days` days before; None
    with fewer than `need` of them. The per-clock history is kept inside the study; preview reads it without adding."""

    def __init__(self, days: int = 14, need: int = 10):
        self.days, self.need = int(days), int(need)
        self.hist = {}
        super().__init__()

    def _ratio(self, bar):
        t = _et(bar)
        key = t.hour * 60 + t.minute
        h = self.hist.get(key, ())
        ratio = None
        if len(h) >= self.need:
            s = sorted(h)
            m = (s[len(s) // 2] + s[(len(s) - 1) // 2]) / 2.0
            ratio = bar.v / m if m > 0 else None
        return key, ratio

    def push(self, bar):
        key, ratio = self._ratio(bar)
        self.hist[key] = (self.hist.get(key, ()) + (bar.v,))[-self.days:]
        return ratio

    def preview(self, bar):
        return self._ratio(bar)[1]


class DayHL(_Study):
    """Highest high / lowest low of the last `days` COMPLETED sessions."""

    def __init__(self, days: int = 5):
        self.days = int(days)
        super().__init__()

    def initial(self):
        return (None, None, None, ())   # session, its high, low, the finished sessions' (high, low)

    def step(self, st, bar):
        sess, h, l, done = st
        if bar.session != sess:
            if sess is not None:
                done = (done + ((h, l),))[-self.days:]
            sess, h, l = bar.session, bar.h, bar.l
        else:
            h, l = max(h, bar.h), min(l, bar.l)
        if not done:
            return (sess, h, l, done), None
        return (sess, h, l, done), {"hi": max(x for x, _ in done), "lo": min(y for _, y in done)}

# name -> (class, parameters): each parameter is (default, minimum, maximum); a wire key may give them in order
PARAMS = {
    "rsi": (RSI, ((14, 2, 500),)),
    "macd": (MACD, ((12, 2, 500), (26, 2, 500), (9, 1, 500))),
    "bb": (Bollinger, ((20, 2, 500), (2.0, 0.1, 10))),
    "atr": (ATR, ((14, 1, 500),)),
    "stoch": (Stochastic, ((14, 2, 500), (3, 1, 100), (3, 1, 100))),
    "supertrend": (Supertrend, ((10, 1, 200), (3.0, 0.5, 10))),
    "donchian": (Donchian, ((20, 2, 1000),)),
    "keltner": (Keltner, ((20, 2, 500), (20, 1, 500), (1.5, 0.1, 10))),
    "tema": (TEMA, ((20, 2, 500),)),
    "mfi": (MFI, ((14, 2, 500),)),
    "er": (Efficiency, ((14, 2, 500),)),
    "orb": (OpeningRange, ((15, 1, 240), (570, 0, 1439))),
    "swing": (Swing, ((50, 2, 500),)),
    "equal": (EqualHL, ((50, 2, 500), (10.0, 0.25, 1000))),
    "rmove": (RangeMove, ((200.0, 1, 5000),)),
    "rswing": (RangeSwing, ((50, 2, 500),)),
    "rvol": (RelVolume, ((14, 3, 60), (10, 1, 60))),
    "dhl": (DayHL, ((5, 1, 60),)),
    "vaprev": (VaPrev, ()),
    "fvg": (FairValueGap, ((0.25, 0.0, 10.0), (14, 1, 200))),
    "wk": (WeekLevels, ()),
    "mo": (MonthLevels, ()),
    "topen": (TimeOpen, ((0, 0, 1439),)),
}
NAMES = tuple(PARAMS) + ("sess", "noise")


def make_ta_num(name: str, args: list, i: int, default, lo, hi) -> float:
    """Parameter `i` of a wire key as a number inside lo..hi, or `default` when the key stops short of it."""
    if i >= len(args):
        return default
    try:
        x = float(args[i])
    except ValueError:
        raise ValueError(f"bad study {name!r}: {args[i]!r} is not a number") from None
    if not (math.isfinite(x) and lo <= x <= hi):
        raise ValueError(f"bad study {name!r}: parameter {i + 1} must be {lo}..{hi}")
    return x


def make_ta(name: str, args: list, tick: float = 0.25):
    """The study `name` with its wire-key `args` (strings), or ValueError: too many parameters, one not a number or
    outside its range. `tick` is the market's tick size, for the studies that read footprint rows."""
    if name == "noise":
        if len(args) > 2:
            raise ValueError("bad study 'noise': noise:<k>:<rth|globex>")
        try:
            k = float(args[0]) if args else 0.3
        except ValueError:
            raise ValueError(f"bad study 'noise': {args[0]!r} is not a number") from None
        if not (math.isfinite(k) and 0.05 <= k <= 3.0):
            raise ValueError("bad study 'noise': k must be 0.05..3")
        return NoiseBand(k, *args[1:])
    if name == "sess":
        if len(args) > 2:
            raise ValueError(f"bad study {name!r}: sess takes one session name ({', '.join(SESSIONS)}) or a start and an end minute")
        if len(args) == 2 and all(a.lstrip("-").isdecimal() for a in args):
            a, b = int(args[0]), int(args[1])
            if not (0 <= a < 1440 and 0 <= b < 1440):
                raise ValueError("bad study 'sess': a window's start and end are minutes of the day, 0..1439")
            return WindowRange(a, b)
        if len(args) > 1:
            raise ValueError("bad study 'sess': a named session takes no more parameters")
        return SessionRange(*args)
    cls, spec = PARAMS[name]
    if cls is VaPrev:
        if args:
            raise ValueError("bad study 'vaprev': it takes no parameters")
        return VaPrev(tick)
    if cls is FairValueGap and len(args) <= 2:
        k = make_ta_num(name, args, 0, 0.25, 0.0, 10.0)
        n = int(make_ta_num(name, args, 1, 14, 1, 200))
        return FairValueGap(k, n, tick)
    if len(args) > len(spec):
        raise ValueError(f"bad study {name!r}: at most {len(spec)} parameter(s)")
    vals = []
    for i, (default, lo, hi) in enumerate(spec):
        if i >= len(args):
            vals.append(default)
            continue
        try:
            x = float(args[i])
        except ValueError:
            raise ValueError(f"bad study {name!r}: {args[i]!r} is not a number") from None
        if not (math.isfinite(x) and lo <= x <= hi):
            raise ValueError(f"bad study {name!r}: parameter {i + 1} must be {lo}..{hi}")
        vals.append(int(x) if isinstance(default, int) else x)
    return cls(*vals)


def warm_ta(name: str, rest: list) -> int:
    """Bars after a join that a study's value still depends on (hub.warm_bars): a window's length; an EMA's 5n and a
    Wilder average's 10n, where the memory fades below e^-10; 0 for the session-anchored ones."""
    def num(i, default):
        try:
            return int(float(rest[i]))
        except (IndexError, ValueError):
            return default
    if name == "rsi" or name == "atr":
        return 10 * num(0, 14)
    if name == "macd":
        return 5 * num(1, 26) + 5 * num(2, 9)
    if name == "bb" or name == "donchian":
        return num(0, 20)
    if name == "stoch":
        return num(0, 14) + num(1, 3) + num(2, 3)
    if name == "supertrend":
        return 10 * num(0, 10)
    if name == "keltner":
        return 5 * num(0, 20) + num(1, 20)
    if name == "tema":
        return 15 * num(0, 20)
    if name in ("mfi", "er"):
        return num(0, 14) + 1
    if name in ("swing", "rswing"):
        return 10 * num(0, 50)
    if name == "equal":
        return 10 * num(0, 50)
    if name == "rmove":
        return 400
    if name == "vaprev":
        return 400
    if name == "fvg":
        return 10 * num(1, 14) + 3
    return 0


def prime_ta(name: str, rest: list) -> int:
    """Completed sessions BEFORE the loaded ones that a study needs to be fed (hub.prime_sessions) so its first value
    is right: the noise band's ATR needs 15 daily bars, relative volume its days, a day high / low its days. A chart
    loads only 1-5 prior sessions (hub.sessions_back), so without this these read nothing on a 1-minute chart."""
    def num(i, default):
        try:
            return int(float(rest[i]))
        except (IndexError, ValueError):
            return default
    return {"noise": 16, "rvol": num(0, 14) + 1, "dhl": num(0, 5) + 1, "vaprev": 1, "swing": 3, "rswing": 3, "equal": 3,
            "rmove": 5, "wk": 11, "mo": 45}.get(name, 0)
