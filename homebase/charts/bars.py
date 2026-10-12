"""Ticks -> bars, for every bar type the charts offer. Pure: no clock, no I/O.

One BarBuilder per (symbol, bar type). add(tick) returns the bars that tick
CLOSED; `cur` is the developing bar. Every bar also carries its footprint
(volume per price: sells at the bid / buys at the ask), buy/sell volume,
sum(price*size) for an exact VWAP, and its big prints. No bar ever spans
two sessions. Time bars are anchored at the session open (18:00 ET), so a
4h bar is 18-22, 22-02, ... and a daily bar is the whole session.

The backtester (Build 3) imports this file unchanged — that is what makes
a backtest see exactly the bars the live chart saw.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .session import et_wall_s, session_date, session_range_ms
from .tick import Tick

KINDS = ("time", "tick", "volume", "range")
BIG_MIN = 10        # prints of >= this many contracts are kept per bar
SWEEP_TICKS = 2     # a burst of same-side prints inside one millisecond that spans >= this many ticks is a sweep
BUB_MIN = 3         # trade bubbles: contracts printed in one second at one price on one side, at least this many
BUB_CAP = 60        # ... and at most this many per bar (the largest)
SW_CAP = 60         # sweeps kept per bar: the largest (a 1D bar of an NQ day would otherwise carry ~11,000)


@dataclass(frozen=True)
class BarSpec:
    kind: str       # time | tick | volume | range
    size: int       # seconds | trades | contracts | price ticks

    @staticmethod
    def parse(key: str) -> "BarSpec":
        kind, _, n = str(key).partition(":")
        if kind not in KINDS or not n.isdigit() or int(n) <= 0:
            raise ValueError(f"bad bar type {key!r} (want e.g. time:60, tick:500, volume:2000, range:10)")
        return BarSpec(kind, int(n))

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.size}"

    @property
    def from_minutes(self) -> bool:
        """True when these bars can be resampled from 1-minute bars."""
        return self.kind == "time" and self.size % 60 == 0


def _cap_bubbles(rows: list) -> list:
    """The BUB_CAP largest bubbles, in time order; a tie on size is broken by time then price, so the same prints
    always keep the same rows however the bar was assembled."""
    rows.sort(key=lambda r: (-r[2], r[0], r[1], r[3]))
    return sorted(rows[:BUB_CAP], key=lambda r: (r[0], r[1], r[3]))


def _cap_sweeps(rows: list) -> list:
    """The SW_CAP largest sweeps ([ts_ms, from, to, size, side]), in time order; a tie on size is broken by time,
    then price, so the same prints always keep the same rows however the bar was assembled. A new list."""
    if len(rows) > SW_CAP:
        rows = sorted(rows, key=lambda r: (-r[3], r[0], r[1], r[2], r[4]))[:SW_CAP]
    return sorted(rows, key=lambda r: (r[0], r[1], r[2], r[4]))


@dataclass
class Bar:
    t: int                  # start, epoch ms (time: bucket start; others: first trade)
    session: str            # session date, ISO
    o: float
    h: float
    l: float
    c: float
    v: int = 0
    buy: int = 0
    sell: int = 0
    n: int = 0
    pv: float = 0.0         # sum(price * size) -> exact VWAP
    p2v: float = 0.0        # sum(price^2 * size) -> VWAP bands
    fp: dict = field(default_factory=dict)    # price in ticks -> [sell at bid, buy at ask]
    big: list = field(default_factory=list)   # [ts_ms, price, size, side], size >= BIG_MIN
    closed: bool = False
    te: int = 0                                # ms of the bar's last print
    span: int = 0                              # a time bar's length in ms (0: a tick / volume / range bar)
    sw: list = field(default_factory=list)     # sweeps: [ts_ms, price_from, price_to, size, side]
    bub: list = field(default_factory=list)    # bubbles: [sec, price, size, side], sealed (see seal())
    _bd: dict = field(default_factory=dict, repr=False, compare=False)   # developing bubbles: (sec, tick, side) -> size
    _g: object = field(default=None, repr=False, compare=False)          # the sweep group in progress
    _bs: int = field(default=0, repr=False, compare=False)               # the latest second in _bd

    @classmethod
    def open_at(cls, t: int, session: str, price: float) -> "Bar":
        return cls(t=t, session=session, o=price, h=price, l=price, c=price)

    @property
    def delta(self) -> int:
        return self.buy - self.sell

    def add(self, tk: Tick, tick_size: float) -> None:
        p, q = tk.price, tk.size
        if p > self.h:
            self.h = p
        if p < self.l:
            self.l = p
        self.c = p
        self.v += q
        self.n += 1
        self.pv += p * q
        self.p2v += p * p * q
        k = round(p / tick_size)
        cell = self.fp.get(k)
        if cell is None:
            cell = self.fp[k] = [0, 0]
        if tk.side > 0:
            self.buy += q
            cell[1] += q
        else:
            self.sell += q
            cell[0] += q
        if q >= BIG_MIN:
            self.big.append([tk.ts_ms, p, q, tk.side])
        if tk.ts_ms > self.te:
            self.te = tk.ts_ms
        sec = tk.ts_ms // 1000
        if sec > self._bs:
            # a second is past: fold it into the capped list, so _bd holds only the current second (wire() and the
            # bar's memory stay small however long the bar develops)
            if self._bd:
                self.bub = self._bubbles(tick_size, sec)
                self._bd = {x: n for x, n in self._bd.items() if x[0] >= sec}
            self._bs = sec
        bk = (sec, k, 1 if tk.side > 0 else -1)
        self._bd[bk] = self._bd.get(bk, 0) + q
        g = self._g
        if g is not None and g[0] == tk.ts_ms and g[1] == tk.side:
            g[2] = min(g[2], k)
            g[3] = max(g[3], k)
            g[4] += q
            g[5] += 1
        else:
            self._flush_group(tick_size)
            self._g = [tk.ts_ms, tk.side, k, k, q, 1]

    def _flush_group(self, tick_size: float) -> None:
        g, self._g = self._g, None
        if g is not None and g[5] >= 2 and g[3] - g[2] >= SWEEP_TICKS:
            row = [g[0], round(g[2] * tick_size, 6), round(g[3] * tick_size, 6), g[4], g[1]]
            self.sw = _cap_sweeps(self.sw + [row]) if len(self.sw) >= SW_CAP else self.sw + [row]

    def seal(self, tick_size: float) -> None:
        """The bar is closed: finish the sweep group and fold the developing bubbles into the capped list."""
        self._flush_group(tick_size)
        self.bub = self._bubbles(tick_size)
        self._bd = {}

    def _bubbles(self, tick_size: float, below: int | None = None) -> list:
        """The sealed rows plus the developing seconds (those before `below`, when given) at >= BUB_MIN, capped.
        A late print for a second already folded adds to its row."""
        acc = {(r[0], r[1], r[3]): r[2] for r in self.bub}
        for (s, k, side), q in self._bd.items():
            if q >= BUB_MIN and (below is None or s < below):
                key = (s, round(k * tick_size, 6), side)
                acc[key] = acc.get(key, 0) + q
        return _cap_bubbles([[s, px, q, side] for (s, px, side), q in acc.items()])

    def copy(self) -> "Bar":
        return Bar(self.t, self.session, self.o, self.h, self.l, self.c, self.v,
                   self.buy, self.sell, self.n, self.pv, self.p2v,
                   {k: list(c) for k, c in self.fp.items()},
                   [list(x) for x in self.big], self.closed, self.te, self.span,
                   [list(x) for x in self.sw], [list(x) for x in self.bub], dict(self._bd),
                   list(self._g) if self._g else None, self._bs)

    def finish_merge(self) -> None:
        """Cap and order the sweeps and bubbles after merge(..., cap=False) calls. The cap keeps the top rows of a total
        order, so capping once at the end keeps exactly the rows capping after every merge did."""
        self.sw = _cap_sweeps(self.sw)
        self.bub = _cap_bubbles(self.bub)

    def merge(self, other: "Bar", cap: bool = True) -> None:
        """Absorb the NEXT bar in time (resampling). cap=False leaves the sweeps and bubbles uncapped and unsorted:
        the caller merges a whole run and then calls finish_merge() once (a 1D bar merges ~1,400 one-minute bars, and
        sorting both lists at every step was most of a session's resample time)."""
        self.h = max(self.h, other.h)
        self.l = min(self.l, other.l)
        self.c = other.c
        self.v += other.v
        self.buy += other.buy
        self.sell += other.sell
        self.n += other.n
        self.pv += other.pv
        self.p2v += other.p2v
        for k, (s, b) in other.fp.items():
            cell = self.fp.setdefault(k, [0, 0])
            cell[0] += s
            cell[1] += b
        self.big.extend(list(x) for x in other.big)
        self.te = max(self.te, other.te)
        if cap:
            self.sw = _cap_sweeps([list(x) for x in self.sw] + [list(x) for x in other.sw])
            self.bub = _cap_bubbles([list(x) for x in self.bub] + [list(x) for x in other.bub])
        else:
            self.sw.extend(list(x) for x in other.sw)
            self.bub.extend(list(x) for x in other.bub)
        for bk, q in other._bd.items():
            self._bd[bk] = self._bd.get(bk, 0) + q
        self._bs = max(self._bs, other._bs)
        self._g = list(other._g) if other._g else None

    def wire(self, tick_size: float, fp: bool = True, big: bool = True, flow: bool = True) -> dict:
        """JSON for the page: t = ET wall-clock seconds (the axis shows ET),
        ms = the real start in epoch ms. fp / big / flow False: without the footprint / the big prints / the
        sweeps and trade bubbles (a chart that draws none of them does not ask for them)."""
        d = {"t": et_wall_s(self.t), "ms": self.t, "s": self.session,
             "o": self.o, "h": self.h, "l": self.l, "c": self.c,
             "v": self.v, "d": self.delta, "n": self.n}
        if big:
            d["big"] = self.big
        if flow:
            g = self._g
            d["sw"] = _cap_sweeps(self.sw + ([[g[0], round(g[2] * tick_size, 6), round(g[3] * tick_size, 6), g[4], g[1]]]
                                             if g and g[5] >= 2 and g[3] - g[2] >= SWEEP_TICKS else []))
            d["bub"] = self._bubbles(tick_size) if self._bd else self.bub
        if fp:
            d["fp"] = [[round(k * tick_size, 6), s, b] for k, (s, b) in sorted(self.fp.items())]
        return d


class BarBuilder:
    def __init__(self, spec: BarSpec, tick_size: float, root: str | None = None):
        self.spec = spec
        self.tick_size = tick_size
        self.root = root        # picks the trading day (session.always_open); None = classic
        self.cur: Bar | None = None
        self._sess: str | None = None
        self._s0 = self._s1 = 0
        self._floor = 0     # time bars: no new bar may start before this (set by on_clock)

    def _enter_session(self, ts: int) -> None:
        if self._sess is not None and self._s0 <= ts < self._s1:
            return
        d = session_date(ts, self.root)
        self._sess = d.isoformat()
        self._s0, self._s1 = session_range_ms(d, self.root)
        self._floor = 0

    def _bucket(self, ts: int) -> int:
        n = self.spec.size * 1000
        return max(self._s0 + (ts - self._s0) // n * n, self._floor)

    def add(self, tk: Tick) -> list[Bar]:
        closed: list[Bar] = []
        self._enter_session(tk.ts_ms)
        cur = self.cur
        if cur is not None and (cur.session != self._sess or self._breaks(cur, tk)):
            closed.append(self._close())
        if self.cur is None:
            t = self._bucket(tk.ts_ms) if self.spec.kind == "time" else tk.ts_ms
            if self.spec.kind == "time" and t >= self._s1:
                # a late print for a session whose last bar the clock already
                # closed: its next bucket starts at the session end -- a stray bar
                # under the old session's label. Not charted live; it is on disk,
                # and a rebuild from the recorded ticks files it in its own bar.
                return closed
            self.cur = Bar.open_at(t, self._sess, tk.price)
            if self.spec.kind == "time":
                self.cur.span = self.spec.size * 1000
        self.cur.add(tk, self.tick_size)
        if self._full(self.cur):
            closed.append(self._close())
        return closed

    def _breaks(self, cur: Bar, tk: Tick) -> bool:
        k = self.spec.kind
        if k == "time":
            return self._bucket(tk.ts_ms) != cur.t
        if k == "range":
            hi, lo = max(cur.h, tk.price), min(cur.l, tk.price)
            return round((hi - lo) / self.tick_size) > self.spec.size
        return False

    def _full(self, cur: Bar) -> bool:
        if self.spec.kind == "tick":
            return cur.n >= self.spec.size
        if self.spec.kind == "volume":
            return cur.v >= self.spec.size
        return False

    def on_clock(self, now_ms: int) -> list[Bar]:
        """Close a TIME bar whose end has passed, so a quiet market doesn't
        hold the last bar open. A tick that arrives later for the closed
        bucket (feed latency beyond the caller's grace) opens the NEXT bucket
        instead of duplicating the closed one (no bucket at or past the
        session end: add() skips it) — a reload rebuilds from the recorded
        ticks and is the truth."""
        cur = self.cur
        if cur is None or self.spec.kind != "time":
            return []
        end = min(cur.t + self.spec.size * 1000, self._s1)
        if now_ms < end:
            return []
        self._floor = end
        return [self._close()]

    def resume(self, cur: Bar, ts_ms: int) -> None:
        """Carry on from a developing bar built elsewhere (resampled from 1-minute bars), as if add() had
        just taken that bar's last tick, stamped ts_ms, here."""
        self._enter_session(ts_ms)
        self.cur = cur

    def _close(self) -> Bar:
        b, self.cur = self.cur, None
        b.closed = True
        b.seal(self.tick_size)
        return b


def build(ticks, spec: BarSpec, tick_size: float, root: str | None = None) -> tuple[list[Bar], Bar | None]:
    """All bars of a tick sequence: (closed, developing)."""
    bb = BarBuilder(spec, tick_size, root)
    closed: list[Bar] = []
    for tk in ticks:
        closed.extend(bb.add(tk))
    return closed, bb.cur


def resample(minutes: list[Bar], spec: BarSpec) -> list[Bar]:
    """Closed time bars of `spec` (whole minutes) from closed 1-minute bars,
    anchored at the session open like BarBuilder — equal to building the
    same ticks directly (tested). Never mutates `minutes`; spec 1m returns
    the input list itself."""
    if spec.size == 60:
        return minutes
    n = spec.size * 1000
    out: list[Bar] = []
    cur: Bar | None = None
    for m in minutes:
        s0, _ = session_range_ms(dt.date.fromisoformat(m.session))
        t = s0 + (m.t - s0) // n * n
        if cur is None or cur.session != m.session or cur.t != t:
            if cur is not None:
                cur.finish_merge()
                out.append(cur)
            cur = m.copy()
            cur.t = t
            cur.span = n
            cur.closed = True
        else:
            cur.merge(m, cap=False)
    if cur is not None:
        cur.finish_merge()
        out.append(cur)
    return out
