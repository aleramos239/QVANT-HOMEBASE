"""candle930 -- the 09:30 candle followed at its close, with the owner's "strong candle" measures (manual lane, owner 2026-10-17).

win_candle (families/flex.py) with every rule as it is -- the tf candle that opens at `start` (09:30 default), green long / red short at its
close, structure stop = its other extreme -- plus five more gates, all off at 0 (the owner's numbers; 1 is win_candle's own body_r):
  2 close_r   the close within the outer close_r of its range (green: high - close, red: close - low, <= close_r x range)
  3 med_m     body >= med_m x the median body of the same clock candle on the 14 trade dates before (10 of 14 with a tape needed)
  4 atr_b     body >= atr_b x ATR(14) of the tf bars before it
  5 pre_min   green closes above the high, red below the low, of the 1-minute bars in the pre_min minutes before the candle
  6 big_n     body >= every body of the big_n tf bars before it (big_n of them needed)
  7 pre_n     green closes above the high, red below the low, of the pre_n candles of the candle's own size before it
  8 pre_dir   with: green only when 08:30 -> 09:30 ET went up (the last 1-minute close before 09:30 above the 08:30 open), red only when
              it went down; a flat hour is no trade (owner 2026-10-18)
SECONDS (owner 2026-10-18): sec > 0 makes the candle `sec` seconds long (a divisor of 60: 30 = the 30-second candle), read from the prints of
  [start, start + sec) at the clock time start + sec; tf stays the bars the ATR and the other blocks read (1). Entry, stop and gates as above;
  k, big_n and entry "break" read tf bars and are refused with sec. With sec the gates read sec-candles: pre_n the high / low of the prints
  in the pre_n x sec seconds before the candle; atr_b the mean true range of the 14 sec-candles before it; med_m the same clock sec-candle
  on the 14 dates before; vol_m its volume x the median volume of that candle on the 14 dates before (both from the tapes, build days
  only). Prints at or after the decision are never read.
SCAN (owner 2026-10-18): with sec, scan_end "HH:MM" makes every sec-candle that opens in [start, scan_end) a candidate, each decided at
  its own close; the first that passes every gate is traded (one trade a session). The gates read THAT candle (its own lookback, its own
  clock candle on the dates before); pre_dir stays the 08:30 -> 09:30 move. scan_end must fall in the same pass as the first close.
The gates read the candle's direction, not the trade's side (mode fade trades against a strong candle).
EXITS "own" (spec file): STOPS below x the six standard targets (none, 0.5R, 0.75R, 1R, 2R, 3R) = 120 cells. The family's own stop modes:
  struct  stop_val x the distance to the candle's other extreme (1 = at it, 0.5 = its middle, 2 = a candle past it)
  datr    stop_val PERCENT of the Wilder ATR(14) of the daily bars before today (the engine's stop_val floor is 0.1)
  pre     the other side of the 08:30-09:30 ET range (1-minute bars)       onr  the other side of the 00:00-09:30 ET range
  (pts / pct / atr are the engine's own.) A stop that cannot be read (no daily ATR, no range bars) is no trade.
ENTRY "close" (default): win_candle's market order at the candle's close. "break" = the straddle: at the candle's close, OCO stop entries one tick
  above its high (long) and below its low (short), live to the pass's last 5 minutes; struct = the other extreme. A doji is no signal in either.
A module of its own so flex.py, hashed into every flex store, stays byte for byte. med_m reads earlier dates' tapes under the BUILD seal
switch: build days only (a test-days date raises). Tests: engine/tests/test_candle930.py.
"""
from __future__ import annotations

import numpy as np

import l2sim as S

from . import flex as FX
from .orb830 import STRUCT_TGT_R

MED_DAYS, MED_MIN = 14, 10
STOPS = ([("struct", v) for v in (0.5, 0.75, 1.0, 1.5, 2.0)] + [("pts", v) for v in (10.0, 20.0, 30.0, 45.0, 60.0, 100.0)]
         + [("atr", 1.5), ("atr", 3.0), ("pct", 0.1), ("pct", 0.2)] + [("datr", v) for v in (5.0, 10.0, 15.0)] + [("pre", 1.0), ("onr", 1.0)])
PRE = (30600, 34200)                                # 08:30-09:30 ET
MODES = ("datr", "pre", "onr")                      # the family's own stop modes (struct reads stop_val too)
_DAY: dict = {}                                     # (root, iso, length s) -> (candle numbers, bodies, volumes) of every candle of that date, or None


def _day_candles(root: str, iso: str, secs: int):
    """Every `secs`-second candle of trade date `iso` (candle number = open second after 00:00 ET // secs) from one read of its tape."""
    key = (root, iso, secs)
    if key not in _DAY:
        t = S.load_tape(iso, root, allow_holdout=S.ALLOW_BP)
        v = None
        if t is not None and len(t.ts):
            k = (t.ts - S.et_ns(t.date, "00:00")) // (secs * S.NS)
            st = np.flatnonzero(np.r_[True, k[1:] != k[:-1]])
            en = np.r_[st[1:], len(k)]
            v = (k[st], np.abs(t.px[en - 1] - t.px[st]), np.add.reduceat(t.size, st).astype(float))
        _DAY[key] = v
    return _DAY[key]


def past_candle(root: str, iso: str, a: int, secs: int):
    """(body, volume) of the `secs`-second candle that opens `a` seconds after 00:00 ET on trade date `iso` (None: no tape or no print)."""
    v = _day_candles(root, iso, secs)
    if v is None:
        return None
    i = int(np.searchsorted(v[0], a // secs))
    return (float(v[1][i]), float(v[2][i])) if i < len(v[0]) and v[0][i] == a // secs else None


def past_body(root: str, iso: str, a: int, secs: int):
    """The body of that candle (past_candle), or None."""
    c = past_candle(root, iso, a, secs)
    return None if c is None else c[0]


class Candle930(FX.WinCandle):
    """candle930 (module docstring): win_candle's signal, then the strong-candle gates, then its market order."""
    DEFAULTS = {**FX.WinCandle.DEFAULTS, "close_r": 0.0, "med_m": 0.0, "atr_b": 0.0, "pre_min": 0, "big_n": 0, "entry": "close",
                "sec": 0, "pre_n": 0, "pre_dir": "off", "scan_end": ""}
    SCHEMA = {**FX.WinCandle.SCHEMA, "close_r": ("float", 0, 1), "med_m": ("float", 0, 50), "atr_b": ("float", 0, 50),
              "pre_min": ("int", 0, 600), "big_n": ("int", 0, 500), "entry": ("choice", ("close", "break")),
              "sec": ("int", 0, 59), "pre_n": ("int", 0, 100), "pre_dir": ("choice", ("off", "with")), "scan_end": ("str",)}

    def _plan(self) -> tuple:
        sec = int(self.p["sec"])
        if not sec:
            return super()._plan()
        p = self.p
        if 60 % sec:
            raise ValueError(f"sec {sec}: a divisor of 60 (10, 15, 20, 30 ...)")
        bad = [k for k in ("k", "big_n") if float(p[k])] + (["entry break"] if p["entry"] == "break" else [])
        if bad:
            raise ValueError(f"sec {sec} reads the candle from the prints: {', '.join(bad)} read tf bars and cannot be used with it")
        a = FX._clock(p["start"], "start")
        if a % sec:
            raise ValueError(f"start {p['start']!r} is not a whole {sec}-second candle")
        home = FX._home(a + sec, f"candle930 start {p['start']} sec {sec}")
        if p["scan_end"]:
            e = FX._clock(p["scan_end"], "scan_end")
            if e <= a or (e - a) % sec or FX._home(e, f"candle930 scan_end {p['scan_end']}") != home:
                raise ValueError(f"scan_end {p['scan_end']!r}: after start, a whole number of {sec}-second candles, in the same pass")
        return a, a + sec, home

    def _closes(self) -> list:
        """The seconds a sec-candle decides at: the first candle's close, or (scan_end) every close up to scan_end."""
        a, b, _ = self._plan()
        e = FX._clock(self.p["scan_end"], "scan_end") if self.p["scan_end"] else b
        return list(range(b, e + 1, int(self.p["sec"])))

    def fam_times(self):
        return [S._hms(x) for x in self._closes()] if int(self.p["sec"]) and self.sessions() else []

    def _prints(self, ctx, a, b):
        """The prices of the prints in [a, b) seconds after 00:00 ET of the trade date, never past the current event (no look-ahead)."""
        sim, t0 = ctx._s, S.et_ns(ctx.date, "00:00")
        ts = sim.ts[sim.lo:sim.i]
        i, j = np.searchsorted(ts, [t0 + a * S.NS, t0 + b * S.NS], side="left")
        return sim.px[sim.lo + i:sim.lo + j]

    def _sec_atr(self, ctx, a: int, sec: int, n: int = 14):
        """The mean true range of the n sec-candles before second a (empty candles skipped; None under n / 2 of them)."""
        trs, pc = [], None
        for k in range(n, 0, -1):
            px = self._prints(ctx, a - k * sec, a - (k - 1) * sec)
            if not len(px):
                continue
            h, lo = float(px.max()), float(px.min())
            trs.append(h - lo if pc is None else max(h, pc) - min(lo, pc))
            pc = float(px[-1])
        return sum(trs) / len(trs) if len(trs) >= n // 2 else None

    def fam_time(self, ctx, sec):
        """sec > 0: the candle closes on the clock, not on a tf bar -> win_candle's own signal (doji, body_r, body_pts, mode) on its prints."""
        if not int(self.p["sec"]):
            return
        _, _, home = self._plan()
        if self.sid != home or sec not in self._closes() or not self.can_enter(ctx):
            return
        b = sec
        a = self._sec_a = b - int(self.p["sec"])
        px = self._prints(ctx, a, b)
        if not len(px):
            return
        o, h, l, c = float(px[0]), float(px.max()), float(px.min()), float(px[-1])
        body = abs(c - o)
        if c == o or body < float(self.p["body_r"]) * (h - l) or body < float(self.p["body_pts"]):
            return
        self._sec_candle = (o, h, l, c)
        side = "long" if (c > o) == (self.p["mode"] == "follow") else "short"
        self._mkt(ctx, side, struct=l if side == "long" else h, ref=c)

    @classmethod
    def unit_exits(cls, root):
        """exits "own": STOPS x the six standard targets, stops outer."""
        return [{"stop_mode": m, "stop_val": v, "tgt_r": r} for m, v in STOPS for r in STRUCT_TGT_R]

    def _mkt(self, ctx, side, *a, **kw):
        if not self._strong(ctx):                   # win_candle calls _mkt once, at the candle's close
            return
        if self.p["entry"] == "break":              # the straddle: OCO stops one tick beyond the candle, each leg's stop past the other extreme
            h, l, t = self.H[-1], self.L[-1], ctx.tick
            legs = [(sd, px, st, None) for sd, px, st in (("long", h + t, l), ("short", l - t, h)) if self._dist(ctx, px, st) is not None]
            self._arm(ctx, legs)
        elif self._dist(ctx, kw.get("ref") or self.C[-1], kw.get("struct")) is not None:
            super()._mkt(ctx, side, *a, **kw)

    def _dist(self, ctx, ref, struct):
        m, v = self.p["stop_mode"], float(self.p["stop_val"])
        if m in ("pts", "pct", "atr"):
            return super()._dist(ctx, ref, struct)
        if m == "struct":
            d = abs(ref - struct) * v
        elif m == "datr":
            a = self.datr()
            d = None if a is None else v / 100.0 * a
        else:
            r = self.rng(*PRE) if m == "pre" else (self.onh, self.onl) if self.onh is not None else None
            d = None if r is None else (ref - r[1] if struct < ref else r[0] - ref)          # struct (the candle's other extreme) is on the stop's side
            d = None if d is None or d <= 0 else d
        return None if d is None else max(d, 0.25 * self.atr, 2 * ctx.tick)

    def _strong(self, ctx) -> bool:
        p = self.p
        o, h, l, c = self._sec_candle if int(p["sec"]) else (self.O[-1], self.H[-1], self.L[-1], self.C[-1])
        up, body = c > o, abs(c - o)
        cr = float(p["close_r"])
        if cr > 0 and (h - c if up else c - l) > cr * (h - l):
            return False
        sec = int(p["sec"])
        start = self._sec_a if sec else self._plan()[0]          # with sec: the open of the candle in hand (scan_end: not always the first)
        ab = float(p["atr_b"])
        if ab > 0:
            atr = self._sec_atr(ctx, start, sec) if sec else self.atr_p
            if not atr or body < ab * atr:
                return False
        n = int(p["big_n"])
        if n > 0 and (len(self.O) <= n or body < max(abs(y - x) for x, y in zip(self.O[-n - 1:-1], self.C[-n - 1:-1]))):
            return False
        pm = int(p["pre_min"])
        if pm > 0:
            r = self.rng(start - pm * 60, start)
            if r is None or not (c > r[0] if up else c < r[1]):
                return False
        n = int(p["pre_n"])
        if n > 0:
            if sec:
                px = self._prints(ctx, start - n * sec, start)
                r = (float(px.max()), float(px.min())) if len(px) else None
            else:
                r = self.rng(start - n * self.tf * 60, start)
            if r is None or not (c > r[0] if up else c < r[1]):
                return False
        if p["pre_dir"] == "with":
            po, pc = self.mo(PRE[0]), self.mc(*PRE)
            if po is None or pc is None or pc == po or (pc > po) != up:
                return False
        secs = sec or self.tf * 60
        mm = float(p["med_m"])
        if mm > 0:
            ref = [b for b in (past_body(ctx.root, str(r["date"]), start, secs) for r in self.dl[-MED_DAYS:]) if b is not None]
            if len(ref) < MED_MIN or body < mm * float(np.median(ref)):
                return False
        vm = float(p["vol_m"])
        if vm > 0 and sec:                          # (on tf bars win_candle checked vol_m itself)
            now = past_candle(ctx.root, self.day, start, sec)          # the candle has closed: its prints are all before the decision
            ref = [x[1] for x in (past_candle(ctx.root, str(r["date"]), start, sec) for r in self.dl[-MED_DAYS:]) if x is not None]
            if now is None or len(ref) < MED_MIN or now[1] < vm * float(np.median(ref)):
                return False
        return True


FAMILIES = {
    "candle930": (Candle930, {}, False,
                  "candle930: win_candle (the tf candle that opens at `start`, 09:30 default, followed or faded at its close, stop at its other "
                  "extreme) + the strong-candle gates, all off at 0: close_r (close in the outer share of its range), med_m (body x the 14-date "
                  "median of the same candle), atr_b (body x ATR of the bars before), pre_min (close beyond the high / low of the minutes before), "
                  "big_n (body >= every body of the bars before), pre_n (close beyond the high / low of the pre_n candles before), pre_dir (with the 08:30-09:30 move), scan_end (with sec: every candle to that time, the first that passes); sec > 0 = a "
                  "candle of sec seconds (30 = the 30-second candle) read from the prints; one trade a session, flat 15:58",
                  {"rationale": "The opening candle is the first vote of the cash session; a candle that is large against its own past, closes at "
                                "its edge and leaves the pre-open range shows buyers or sellers who had to act, and the stop at its other extreme "
                                "is where that reading is wrong.",
                   "complexity": 5,
                   "variants": [{"body_r": 0.0}, {"body_r": 0.5}, {"body_r": 0.7}]}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED, as orb830 does (its import installed the exits "own" hook). Idempotent."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        cls.SCHEMA = {"stop_mode": ("choice", tuple(blocks.Blocks.SCHEMA["stop_mode"][1]) + MODES)}   # the Blocks mixin's choice list sits in front of ours
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
