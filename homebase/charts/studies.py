"""Indicators, computed incrementally on bars. Pure.

push(bar) commits a CLOSED bar and returns its value; preview(bar) values
the DEVELOPING bar without committing. State is an immutable tuple, so a
preview can never corrupt it. Values: float, dict, or None (warming up).

Wire keys: "sma:50", "sma:50:hl2" (length + optional source, sma/ema only; default source is close), "ema:20",
"vwma:15", "vwap", "vwap:rth", "vwap:week", "vwap:month", "vwap:t0200" (anchor eth/rth/week/month/tHHMM;
"vwap" alone is "eth"), "adx:14", "cumdelta", "levels". ("profile" is not a Study — see Profile.) The technical
studies (rsi, macd, bb, atr, stoch, supertrend, donchian, keltner, tema, mfi, er, orb, sess) are in studies_ta.py.

A key may end in "@<seconds>" (2026-10-11): the study is computed on bars of that longer timeframe -- "ema:20@3600" is
the 20-period EMA of 1-hour bars -- and read on every chart bar (see HTF). Only the window / smoothing studies take it
(HTF_OK); an anchored one (vwap, levels, orb, sess ...) has no meaning on another timeframe.
"""
from __future__ import annotations

import math
import re

from .session import custom_anchor_key, is_rth, month_key, week_key
from .studies_ta import NAMES as TA_NAMES, make_ta

SOURCES = ("close", "open", "high", "low", "hl2", "hlc3", "ohlc4")


def _source_value(bar, source: str) -> float:
    if source == "close":
        return bar.c
    if source == "open":
        return bar.o
    if source == "high":
        return bar.h
    if source == "low":
        return bar.l
    if source == "hl2":
        return (bar.h + bar.l) / 2
    if source == "hlc3":
        return (bar.h + bar.l + bar.c) / 3
    if source == "ohlc4":
        return (bar.o + bar.h + bar.l + bar.c) / 4
    raise ValueError(f"source {source!r} (have {', '.join(SOURCES)})")


class Study:
    def __init__(self):
        self.state = self.initial()

    def initial(self) -> tuple:
        return ()

    def step(self, state: tuple, bar) -> tuple:     # -> (new state, value)
        raise NotImplementedError

    def push(self, bar):
        self.state, v = self.step(self.state, bar)
        return v

    def preview(self, bar):
        return self.step(self.state, bar)[1]


class SMA(Study):
    """Simple moving average of `source` (default close -- "sma:50" is unchanged)."""

    def __init__(self, n: int = 20, source: str = "close"):
        self.n = int(n)
        if source not in SOURCES:
            raise ValueError(f"source {source!r} (have {', '.join(SOURCES)})")
        self.source = source
        super().__init__()

    def step(self, st, bar):
        w = (st + (_source_value(bar, self.source),))[-self.n:]
        return w, (sum(w) / self.n if len(w) == self.n else None)


class EMA(Study):
    """pandas ewm(span=n, adjust=False): alpha 2/(n+1), seeded with the first value of `source` (default
    close -- "ema:20" is unchanged)."""

    def __init__(self, n: int = 20, source: str = "close"):
        self.n = int(n)
        self.a = 2.0 / (self.n + 1)
        if source not in SOURCES:
            raise ValueError(f"source {source!r} (have {', '.join(SOURCES)})")
        self.source = source
        super().__init__()

    def initial(self):
        return (None,)

    def step(self, st, bar):
        prev = st[0]
        x = _source_value(bar, self.source)
        v = x if prev is None else prev + (x - prev) * self.a
        return (v,), v


class VWMA(Study):
    """sum(close * volume) / sum(volume) over the last n bars."""

    def __init__(self, n: int = 20):
        self.n = int(n)
        super().__init__()

    def step(self, st, bar):
        w = (st + ((bar.c, bar.v),))[-self.n:]
        if len(w) < self.n:
            return w, None
        vol = sum(v for _, v in w)
        return w, (sum(c * v for c, v in w) / vol if vol else None)


_CUSTOM_ANCHOR = re.compile(r"^t(\d{2})(\d{2})$")


class VWAP(Study):
    """Session VWAP from every trade (bars carry sum(p*q)) + its volume-weighted standard deviation for bands.

    Anchor (wire key "vwap:<anchor>", "vwap" alone means "eth"):
      "eth"    resets at the 18:00 ET session open (TradingView's session default) -- wire key "vwap"
      "rth"    resets at 09:30 ET and is None before it -- wire key "vwap:rth"
      "week"   resets at the week's first session (Sunday 18:00 ET) -- wire key "vwap:week"
      "month"  resets at the first session of the calendar month, by CME trade date -- wire key "vwap:month"
      "tHHMM"  resets every day at HH:MM ET, e.g. "t0200" = 02:00 ET -- wire key "vwap:t0200".

    The period key is decided from each CLOSED bar's own start (bar.t; a Study never sees mid-bar ticks), the
    same rule the "rth" anchor already used for is_rth. So on bars coarser than the anchor (e.g. 1h bars with a
    09:30 anchor) a bar that STARTS before the anchor is still the old period even though its span crosses the
    anchor -- the reset first shows on the next bar, the first one whose start is at or after the anchor
    instant, i.e. the first bar that fully contains only time at-or-past the anchor.
    """

    def __init__(self, anchor: str = "eth"):
        if anchor in ("eth", "rth", "week", "month"):
            self.kind, self.hh, self.mm = anchor, None, None
        else:
            m = _CUSTOM_ANCHOR.match(anchor)
            if not m:
                raise ValueError(f"vwap anchor {anchor!r} (eth, rth, week, month, or tHHMM e.g. t0200)")
            hh, mm = int(m.group(1)), int(m.group(2))
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                raise ValueError(f"vwap anchor {anchor!r}: HH must be 00-23 and MM 00-59")
            self.kind, self.hh, self.mm = "custom", hh, mm
        self.anchor = anchor
        super().__init__()

    def initial(self):
        return (None, 0.0, 0.0, 0)

    def _period(self, bar):
        """The accumulator resets whenever this key changes bar over bar."""
        if self.kind in ("eth", "rth"):
            return bar.session
        if self.kind == "week":
            return week_key(bar.session)
        if self.kind == "month":
            return month_key(bar.session)
        return custom_anchor_key(bar.t, self.hh, self.mm)

    def step(self, st, bar):
        if self.kind == "rth" and not is_rth(bar.t, bar.session):
            return st, None
        key = self._period(bar)
        _, pv, p2v, v = st if st[0] == key else (key, 0.0, 0.0, 0)
        pv, p2v, v = pv + bar.pv, p2v + bar.p2v, v + bar.v
        new = (key, pv, p2v, v)
        if not v:
            return new, None
        vw = pv / v
        return new, {"vwap": vw, "sd": math.sqrt(max(p2v / v - vw * vw, 0.0))}


class ADX(Study):
    """Wilder ADX/DI — bit-for-bit the house definition in homebase.gate:
    RMA = prev + (x - prev) * (1/n) seeded with the first value, a 0/0 DX
    carries the previous ADX, and no reading before bar 2n."""

    def __init__(self, n: int = 14):
        self.n = int(n)
        self.a = 1.0 / self.n
        super().__init__()

    def initial(self):
        return (0, None, None, None, None, None, None, None)   # i, ph, pl, pc, atr, p, m, adx

    def _rma(self, prev, x):
        return x if prev is None else prev + (x - prev) * self.a

    def step(self, st, bar):
        i, ph, pl, pc, atr, p, m, adx = st
        h, l, c = bar.h, bar.l, bar.c
        if i == 0:
            tr, up_dm, dn_dm = h - l, 0.0, 0.0
        else:
            tr = max(h - l, abs(h - pc), abs(l - pc))
            up, dn = h - ph, pl - l
            up_dm = up if (up > dn and up > 0) else 0.0
            dn_dm = dn if (dn > up and dn > 0) else 0.0
        atr, p, m = self._rma(atr, tr), self._rma(p, up_dm), self._rma(m, dn_dm)
        pdi = 100.0 * p / atr if atr else 0.0
        mdi = 100.0 * m / atr if atr else 0.0
        s = pdi + mdi
        dx = 100.0 * abs(pdi - mdi) / s if s else None
        if dx is not None:
            adx = self._rma(adx, dx)
        val = {"adx": adx, "pdi": pdi, "mdi": mdi} if i >= 2 * self.n else None
        return (i + 1, h, l, c, atr, p, m, adx), val


class CumDelta(Study):
    """Buy minus sell volume, summed over the session."""

    def initial(self):
        return (None, 0)

    def step(self, st, bar):
        cum = (st[1] if st[0] == bar.session else 0) + bar.delta
        return (bar.session, cum), cum


class Levels(Study):
    """Prior session high/low/close, overnight high/low (18:00 -> 09:30 ET)
    and the RTH open. Exact on bar sizes that split at 09:30 (<= 30m)."""

    def initial(self):
        return (None, None, None, None, None, None, None, None)  # sess, h, l, c, prev, onh, onl, open

    def step(self, st, bar):
        sess, h, l, c, prev, onh, onl, ropen = st
        if sess != bar.session:
            if sess is not None:
                prev = (h, l, c)
            sess, h, l, c, onh, onl, ropen = bar.session, bar.h, bar.l, bar.c, None, None, None
        else:
            h, l, c = max(h, bar.h), min(l, bar.l), bar.c
        if is_rth(bar.t, bar.session):
            if ropen is None:
                ropen = bar.o
        else:
            onh = bar.h if onh is None else max(onh, bar.h)
            onl = bar.l if onl is None else min(onl, bar.l)
        val = {"pdh": prev[0] if prev else None, "pdl": prev[1] if prev else None,
               "pdc": prev[2] if prev else None, "onh": onh, "onl": onl, "rth_open": ropen}
        return (sess, h, l, c, prev, onh, onl, ropen), val


class HTF(Study):
    """A study read on a longer timeframe. The chart's bars are gathered into bars of `seconds` (aligned to the trading
    day's 18:00 ET start; a day or more = the trading date), the inner study is stepped over the FINISHED ones, and
    its value on every chart bar is what it reads with the higher bar so far (the developing one). Nothing from a
    later chart bar is ever used, so a past value is what it showed when that bar was live. State is immutable, so
    preview() never commits a developing bar."""

    def __init__(self, inner: Study, seconds: int):
        self.inner = inner
        self.sec = int(seconds)
        super().__init__()

    def initial(self):
        return (self.inner.initial(), None, None)

    def _key(self, bar):
        if self.sec >= 86400:
            return (bar.session, 0)
        import datetime as dt
        from .studies_ta import ET
        et = dt.datetime.fromtimestamp(bar.t / 1000, ET)
        since_open = (et.hour * 3600 + et.minute * 60 + et.second - 18 * 3600) % 86400      # seconds since the day opened (18:00 ET)
        return (bar.session, since_open // self.sec)

    @staticmethod
    def _merge(agg, bar):
        from .bars import Bar
        if agg is None:
            return Bar(t=bar.t, session=bar.session, o=bar.o, h=bar.h, l=bar.l, c=bar.c, v=bar.v, buy=bar.buy, sell=bar.sell, n=bar.n)
        return Bar(t=agg.t, session=agg.session, o=agg.o, h=max(agg.h, bar.h), l=min(agg.l, bar.l), c=bar.c, v=agg.v + bar.v,
                   buy=agg.buy + bar.buy, sell=agg.sell + bar.sell, n=agg.n + bar.n)

    def step(self, st, bar):
        inner_state, key, agg = st
        k = self._key(bar)
        if agg is not None and k == key:
            agg = self._merge(agg, bar)
        else:
            if agg is not None:                      # the higher bar that just ended joins the inner study's history
                inner_state, _ = self.inner.step(inner_state, agg)
            agg = self._merge(None, bar)
        _, value = self.inner.step(inner_state, agg)
        return (inner_state, k, agg), value


HTF_OK = ("sma", "ema", "vwma", "adx", "rsi", "macd", "stoch", "mfi", "er", "atr", "bb", "keltner", "donchian", "supertrend", "tema")
HTF_MAX_S = 86400       # any timeframe from a second to a day: the page's box takes "15m", "1h", "90s"
REGISTRY = {"sma": SMA, "ema": EMA, "vwma": VWMA, "vwap": VWAP, "adx": ADX,
            "cumdelta": CumDelta, "levels": Levels}
LENGTHS = range(1, 1001)        # the length a windowed study may be given


def split_timeframe(key: str) -> tuple[str, int]:
    """("ema:20", 3600) from "ema:20@3600"; a key with no "@" is (key, 0). ValueError on a timeframe that is not one of
    HTF_SECONDS or on a study that cannot take one."""
    base, at, tf = str(key).partition("@")
    if not at:
        return base, 0
    name = base.split(":")[0]
    if name not in HTF_OK:
        raise ValueError(f"bad study {key!r}: {name} has no timeframe option")
    if not tf.isdecimal() or not 1 <= int(tf) <= HTF_MAX_S:
        raise ValueError(f"bad study {key!r}: the timeframe is 1 to {HTF_MAX_S} seconds")
    return base, int(tf)


def make(key: str, tick_size: float = 0.25) -> Study:
    """A Study from its wire key. ValueError on anything malformed: an
    unknown name, a length outside LENGTHS, or a parameter too many."""
    base, sec = split_timeframe(key)
    if sec:
        return HTF(make(base, tick_size), sec)
    name, *args = str(key).split(":")
    if name in TA_NAMES:
        return make_ta(name, args, tick_size)
    cls = REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"unknown study {key!r} (have {', '.join(sorted([*REGISTRY, *TA_NAMES]))}, profile)")
    if cls in (SMA, EMA):
        if len(args) > 2 or (args and not (args[0].isdecimal() and int(args[0]) in LENGTHS)):
            raise ValueError(f"bad study {key!r}: {name} takes a length and optional source "
                              f"{LENGTHS[0]}..{LENGTHS[-1]}, e.g. {name}:20 or {name}:20:hl2")
        return cls() if not args else cls(int(args[0]), *args[1:])
    if cls in (VWMA, ADX):
        if len(args) > 1 or (args and not (args[0].isdecimal() and int(args[0]) in LENGTHS)):
            raise ValueError(f"bad study {key!r}: {name} takes one length "
                             f"{LENGTHS[0]}..{LENGTHS[-1]}, e.g. {name}:20")
        return cls(*map(int, args))
    if len(args) > (1 if cls is VWAP else 0):
        raise ValueError(f"bad study {key!r}: too many parameters")
    return cls(*args)


def profile_from(vol: dict, tick_size: float, va: float = 0.70) -> dict | None:
    """POC, value area (grown one price row at a time from the POC toward
    the heavier neighbour until it holds `va` of the volume) and the rows,
    from volume per price-in-ticks."""
    if not vol:
        return None
    keys = sorted(vol)
    total = sum(vol.values())
    i = max(range(len(keys)), key=lambda j: (vol[keys[j]], -j))
    lo = hi = i
    acc = vol[keys[i]]
    while acc < va * total and (lo > 0 or hi < len(keys) - 1):
        up = vol[keys[hi + 1]] if hi < len(keys) - 1 else -1
        dn = vol[keys[lo - 1]] if lo > 0 else -1
        if up >= dn:
            hi += 1
            acc += up
        else:
            lo -= 1
            acc += dn

    def px(k):
        return round(k * tick_size, 6)

    return {"poc": px(keys[i]), "vah": px(keys[hi]), "val": px(keys[lo]),
            "rows": [[px(k), vol[k]] for k in keys]}


class Profile:
    """Session volume profile, accumulated bar by bar. Not a Study: its value
    is the whole profile, not one number per bar."""

    def __init__(self, tick_size: float):
        self.tick_size = tick_size
        self.session: str | None = None
        self.vol: dict = {}

    def push(self, bar) -> None:
        if bar.session != self.session:
            self.session, self.vol = bar.session, {}
        for k, (s, b) in bar.fp.items():
            self.vol[k] = self.vol.get(k, 0) + s + b

    def value(self, live=None) -> dict | None:
        vol = self.vol
        if live is not None:
            vol = dict(vol) if live.session == self.session else {}
            for k, (s, b) in live.fp.items():
                vol[k] = vol.get(k, 0) + s + b
        return profile_from(vol, self.tick_size)
