"""flexind -- THE OPEN INDICATOR LIBRARY and THE DAY CALENDAR of the open layer (families/_flex.py, families/flex.py; owner 2026-10-11: "any
indicator in any setting, any time window, everything"). Pure math: no engine state, no tape, no prices of a day it was not handed.

INDICATORS. One object per indicator, fed ONE CLOSED tf bar at a time (`update(o, h, l, c, v, vw)`), so a day costs O(1) a bar and the
value at a decision never sees a bar that has not closed. `v` = the value after the last bar, `p` = the value before it, None = no
signal yet (too few bars since the restart, a flat line). Every period is a setting; nothing is a constant of this file but the
textbook definitions below. DIRECTIONAL indicators have a centre; the line is `centre +/- lvl`:

  kind        v                                                          centre  bars needed   lvl is in
  rsi         Wilder RSI(n) of the closes                                  50     n + 1         RSI points beyond 50
  price_ema   (close - EMA(n)) / ATR(14)                                    0     n             ATRs
  ema_x       (EMA(n) - EMA(m)) / ATR(14)                                   0     max(n, m)     ATRs
  macd        (EMA(n) - EMA(m) - EMA(s) of that line) / ATR(14)             0     max(n, m)     ATRs
  zscore      (close - mean(n)) / sd(n), population sd, bar included        0     n             sigmas (= a Bollinger band of k sigma)
  stoch       100 x (close - lowest low n) / (highest high n - lowest low)  50     n             points beyond 50
  roc         100 x (close / close n bars ago - 1)                          0     n + 1         percent
  cci         (typical - mean(typical, n)) / (0.015 x mean deviation)       0     n             CCI points
  vwap_dev    (close - session VWAP) / session sigma (given by the engine)  0     1             sigmas
NON-DIRECTIONAL (a regime, not a side):
  adx         Wilder ADX(n)                                                       2 n           ADX points
  atr_rank    rank (0..1) of the last ATR(14) among the n before it               n + 14        a share
  bbw_rank    rank (0..1) of the last Bollinger bandwidth (20, 2 sigma) among n   n + 20        a share
  er          Kaufman's efficiency ratio of n steps                               n + 1         0..1
EMAs are seeded with the first close of the day (the Template's own); ATR(14) is the Template's own (mean of the first 14 true ranges,
then Wilder). All indicators restart with the engine's own restart (00:00 ET of the trade date, 18:00 for an evening).

THE TWO READS (what gate and signal mean, one place):
  gate_ok(ind, side, g_side, lvl)  a state. Directional: bull = v > centre + lvl, bear = v < centre - lvl; `with` = a long needs bull and a
                                   short bear, `against` = the mirror. Non-directional: `with` = v >= lvl, `against` = v < lvl.
  event(ind, lvl, edge)            a crossing at THIS bar: enter = v crosses above centre + lvl (+1) / below centre - lvl (-1); exit =
                                   v comes back out of the lower zone (+1) / the upper zone (-1). 0 = nothing.

THE DAY CALENDAR (`day_ok`): the schedule of cache/events.csv (official release dates, known in advance: no look-ahead) and the weekday /
month arithmetic of the ISO date. Weekdays only; the file ends 2026-10-02, a later date has no release rows (refresh the file to extend).
"""
from __future__ import annotations

import csv
import datetime as dt
from collections import deque
from functools import lru_cache
from pathlib import Path

import numpy as np

EVENTS = Path(__file__).resolve().parent / "cache" / "events.csv"
ATR_N = 14
TIER1 = ("NFP", "CPI", "PPI", "RETAIL", "GDP", "PCE")                 # the 08:30 releases that move the whole tape (judge.TIER1)
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri")
DAY_RULES = ("all", "news", "nonews", "rel0830", "rel1000", "tier1", "notier1", "nfp", "cpi", "ppi", "retail", "gdp", "pce", "claims", "fomc", "nofomc",
             "ism", "jolts", "umich", *WEEKDAYS, "month_end", "month_start", "opex")
KINDS_DIR = ("rsi", "price_ema", "ema_x", "macd", "zscore", "stoch", "roc", "cci", "vwap_dev")
KINDS_REGIME = ("adx", "atr_rank", "bbw_rank", "er")
KINDS = KINDS_DIR + KINDS_REGIME


# ---- the day calendar -----------------------------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _events() -> dict:
    """ISO date -> [(time ET 'HH:MM', type)] of cache/events.csv. Read once a process."""
    out: dict = {}
    with EVENTS.open(newline="") as fh:
        for r in csv.DictReader(fh):
            out.setdefault(r["date"], []).append((r["time_et"], r["type"]))
    return out


def _has(iso: str, times=None, types=None) -> bool:
    return any((times is None or t in times) and (types is None or ty in types) for t, ty in _events().get(iso, ()))


def day_ok(iso: str, rule: str) -> bool:
    """Is the trade date `iso` a day of the rule (module docstring)? An unknown rule raises: a typo must not trade every day."""
    if rule == "all":
        return True
    d = dt.date.fromisoformat(iso)
    if rule in WEEKDAYS:
        return d.weekday() == WEEKDAYS.index(rule)
    if rule == "news":
        return _has(iso, ("08:30", "10:00"))
    if rule == "nonews":
        return not _has(iso, ("08:30", "10:00"))
    if rule == "rel0830":                                             # any release at 08:30 ET (claims, NFP, CPI, GDP ...)
        return _has(iso, ("08:30",))
    if rule == "rel1000":                                             # any release at 10:00 ET (ISM, JOLTS, Michigan ...)
        return _has(iso, ("10:00",))
    if rule == "tier1":
        return _has(iso, ("08:30",), TIER1)
    if rule == "notier1":
        return not _has(iso, ("08:30",), TIER1)
    if rule in ("nfp", "cpi", "ppi", "retail", "gdp", "pce", "claims", "fomc", "jolts", "umich"):
        return _has(iso, None, (rule.upper(),))
    if rule == "nofomc":
        return not _has(iso, None, ("FOMC",))
    if rule == "ism":
        return _has(iso, None, ("ISM_MFG", "ISM_SVC"))
    if rule == "month_end":                                           # the last weekday of its month (a holiday is not known here)
        n = d + dt.timedelta(days=1)
        while n.weekday() >= 5:
            n += dt.timedelta(days=1)
        return n.month != d.month
    if rule == "month_start":
        p = d - dt.timedelta(days=1)
        while p.weekday() >= 5:
            p -= dt.timedelta(days=1)
        return p.month != d.month
    if rule == "opex":                                                # the monthly options expiry: the third Friday
        return d.weekday() == 4 and 15 <= d.day <= 21
    raise ValueError(f"day rule {rule!r}: one of {', '.join(DAY_RULES)}")


# ---- the indicators --------------------------------------------------------------------------------------------------------------
def _midrank(x: float, ref) -> float:
    """The share of `ref` below x, ties counted half."""
    r = np.asarray(ref, float)
    return (float((r < x).sum()) + 0.5 * float((r == x).sum())) / len(r)


class Ind:
    """One indicator (module docstring). Subclasses implement `_step` and set `centre`, `directional`, `need`."""
    centre = 0.0
    directional = True

    def __init__(self, n: int, m: int = 0, s: int = 0):
        self.n, self.m, self.s = int(n), int(m), int(s)
        self.v = self.p = None
        self.bars = 0
        self._tr: list = []
        self._atr = None
        self._pc = None
        self._init()

    def _init(self) -> None:
        pass

    def atr(self):
        return self._atr

    def update(self, o: float, h: float, l: float, c: float, v: float = 0.0, vw=None) -> None:
        """Feed one CLOSED tf bar (`vw` = (session VWAP, its sigma) at this bar's close, for vwap_dev only)."""
        tr = h - l if self._pc is None else max(h - l, abs(h - self._pc), abs(l - self._pc))
        self.bars += 1
        if self.bars <= ATR_N:
            self._tr.append(tr)
            self._atr = sum(self._tr) / self.bars
        else:
            self._atr = (self._atr * (ATR_N - 1) + tr) / ATR_N
        self.p = self.v
        self.v = self._step(o, h, l, c, v, vw, tr)
        self._pc = c


class _EmaMixin:
    @staticmethod
    def _ema(e, c, n):
        return c if e is None else e + 2.0 / (n + 1) * (c - e)


class Rsi(Ind):
    centre = 50.0

    def _init(self):
        self.ag = self.al = None
        self.g, self.l_, self.k = 0.0, 0.0, 0

    def _step(self, o, h, l, c, v, vw, tr):
        if self._pc is None:
            return None
        d = c - self._pc
        up, dn = max(d, 0.0), max(-d, 0.0)
        self.k += 1
        if self.ag is None:
            self.g += up
            self.l_ += dn
            if self.k < self.n:
                return None
            self.ag, self.al = self.g / self.n, self.l_ / self.n
        else:
            self.ag = (self.ag * (self.n - 1) + up) / self.n
            self.al = (self.al * (self.n - 1) + dn) / self.n
        if self.al == 0:
            return 50.0 if self.ag == 0 else 100.0
        return 100.0 - 100.0 / (1.0 + self.ag / self.al)


class PriceEma(Ind, _EmaMixin):
    def _init(self):
        self.e = None

    def _step(self, o, h, l, c, v, vw, tr):
        self.e = self._ema(self.e, c, self.n)
        return (c - self.e) / self._atr if self.bars >= self.n and self._atr else None


class EmaX(Ind, _EmaMixin):
    def _init(self):
        self.a = self.b = None

    def _step(self, o, h, l, c, v, vw, tr):
        self.a, self.b = self._ema(self.a, c, self.n), self._ema(self.b, c, self.m)
        return (self.a - self.b) / self._atr if self.bars >= max(self.n, self.m) and self._atr else None


class Macd(Ind, _EmaMixin):
    def _init(self):
        self.a = self.b = self.sg = None

    def _step(self, o, h, l, c, v, vw, tr):
        self.a, self.b = self._ema(self.a, c, self.n), self._ema(self.b, c, self.m)
        line = self.a - self.b
        self.sg = self._ema(self.sg, line, self.s)
        return (line - self.sg) / self._atr if self.bars >= max(self.n, self.m) and self._atr else None


class ZScore(Ind):
    def _init(self):
        self.w = deque(maxlen=self.n)

    def _step(self, o, h, l, c, v, vw, tr):
        self.w.append(c)
        if len(self.w) < self.n:
            return None
        a = np.fromiter(self.w, float, self.n)
        sd = float(a.std())
        return None if sd == 0 else (c - float(a.mean())) / sd


class Stoch(Ind):
    centre = 50.0

    def _init(self):
        self.hw, self.lw = deque(maxlen=self.n), deque(maxlen=self.n)

    def _step(self, o, h, l, c, v, vw, tr):
        self.hw.append(h)
        self.lw.append(l)
        if len(self.hw) < self.n:
            return None
        hh, ll = max(self.hw), min(self.lw)
        return None if hh == ll else 100.0 * (c - ll) / (hh - ll)


class Roc(Ind):
    def _init(self):
        self.w = deque(maxlen=self.n + 1)

    def _step(self, o, h, l, c, v, vw, tr):
        self.w.append(c)
        return 100.0 * (c / self.w[0] - 1.0) if len(self.w) == self.n + 1 and self.w[0] else None


class Cci(Ind):
    def _init(self):
        self.w = deque(maxlen=self.n)

    def _step(self, o, h, l, c, v, vw, tr):
        tp = (h + l + c) / 3.0
        self.w.append(tp)
        if len(self.w) < self.n:
            return None
        a = np.fromiter(self.w, float, self.n)
        md = float(np.abs(a - a.mean()).mean())
        return None if md == 0 else (tp - float(a.mean())) / (0.015 * md)


class VwapDev(Ind):
    def _step(self, o, h, l, c, v, vw, tr):
        if vw is None or not vw[1] or vw[1] <= 0:
            return None
        return (c - vw[0]) / vw[1]


class Adx(Ind):
    directional = False

    def _init(self):
        self.ph = self.pl = None
        self.k = 0
        self.s_tr = self.s_p = self.s_m = 0.0
        self.dxs: list = []
        self.adx = None

    def _step(self, o, h, l, c, v, vw, tr):
        if self.ph is None:
            self.ph, self.pl = h, l
            return None
        up, dn = h - self.ph, self.pl - l
        pdm = up if up > dn and up > 0 else 0.0
        mdm = dn if dn > up and dn > 0 else 0.0
        self.ph, self.pl = h, l
        self.k += 1
        n = self.n
        if self.k <= n:
            self.s_tr, self.s_p, self.s_m = self.s_tr + tr, self.s_p + pdm, self.s_m + mdm
            if self.k < n:
                return None
        else:
            self.s_tr += tr - self.s_tr / n
            self.s_p += pdm - self.s_p / n
            self.s_m += mdm - self.s_m / n
        if self.s_tr == 0:
            return self.adx
        pi, mi = 100.0 * self.s_p / self.s_tr, 100.0 * self.s_m / self.s_tr
        dx = 0.0 if pi + mi == 0 else 100.0 * abs(pi - mi) / (pi + mi)
        if self.adx is None:
            self.dxs.append(dx)
            if len(self.dxs) < n:
                return None
            self.adx = sum(self.dxs) / n
        else:
            self.adx = (self.adx * (n - 1) + dx) / n
        return self.adx


class AtrRank(Ind):
    directional = False

    def _init(self):
        self.w = deque(maxlen=self.n + 1)

    def _step(self, o, h, l, c, v, vw, tr):
        if self.bars < ATR_N:
            return None
        self.w.append(self._atr)
        return _midrank(self.w[-1], list(self.w)[:-1]) if len(self.w) == self.n + 1 else None


class BbwRank(Ind):
    directional = False
    BB_N = 20

    def _init(self):
        self.cw = deque(maxlen=self.BB_N)
        self.w = deque(maxlen=self.n + 1)

    def _step(self, o, h, l, c, v, vw, tr):
        self.cw.append(c)
        if len(self.cw) < self.BB_N:
            return None
        a = np.fromiter(self.cw, float, self.BB_N)
        mid = float(a.mean())
        if mid == 0:
            return None
        self.w.append(4.0 * float(a.std()) / mid)                     # (upper - lower) / middle of a 2-sigma band
        return _midrank(self.w[-1], list(self.w)[:-1]) if len(self.w) == self.n + 1 else None


class Er(Ind):
    directional = False

    def _init(self):
        self.w = deque(maxlen=self.n + 1)

    def _step(self, o, h, l, c, v, vw, tr):
        self.w.append(c)
        if len(self.w) < self.n + 1:
            return None
        a = np.fromiter(self.w, float, self.n + 1)
        path = float(np.abs(np.diff(a)).sum())
        return None if path == 0 else abs(float(a[-1] - a[0])) / path


_KINDS = {"rsi": Rsi, "price_ema": PriceEma, "ema_x": EmaX, "macd": Macd, "zscore": ZScore, "stoch": Stoch, "roc": Roc, "cci": Cci,
          "vwap_dev": VwapDev, "adx": Adx, "atr_rank": AtrRank, "bbw_rank": BbwRank, "er": Er}


def make(kind: str, n: int, m: int = 0, s: int = 0) -> Ind:
    """A fresh indicator of `kind` (module docstring); `m` = the slow period (ema_x, macd), `s` = the macd signal span."""
    if kind not in _KINDS:
        raise ValueError(f"indicator {kind!r}: one of {', '.join(KINDS)}")
    return _KINDS[kind](n, m, s)


def bars_needed(kind: str, n: int, m: int = 0, s: int = 0) -> int:
    """The tf bars since the restart before the indicator can have a value (the module docstring's table)."""
    return {"rsi": n + 1, "price_ema": n, "ema_x": max(n, m), "macd": max(n, m), "zscore": n, "stoch": n, "roc": n + 1, "cci": n,
            "vwap_dev": 1, "adx": 2 * n, "atr_rank": n + ATR_N, "bbw_rank": n + 20, "er": n + 1}[kind]


# ---- the two reads -----------------------------------------------------------------------------------------------------------------
def gate_ok(ind: Ind, side: str, g_side: str, lvl: float) -> bool:
    """A state read (module docstring). No value yet: False for both sides."""
    v = ind.v
    if v is None:
        return False
    if not ind.directional:
        return v >= lvl if g_side == "with" else v < lvl
    bull, bear = v > ind.centre + lvl, v < ind.centre - lvl
    return bull if (side == "long") == (g_side == "with") else bear


def event(ind: Ind, lvl: float, edge: str) -> int:
    """A crossing at the bar that just closed (module docstring): +1, -1 or 0."""
    v, p = ind.v, ind.p
    if v is None or p is None or not ind.directional:
        return 0
    up, lo = ind.centre + lvl, ind.centre - lvl
    if edge == "enter":
        return 1 if p <= up < v else -1 if p >= lo > v else 0
    return 1 if p < lo <= v else -1 if p > up >= v else 0
