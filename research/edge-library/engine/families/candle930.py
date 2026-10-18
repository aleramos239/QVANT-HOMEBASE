"""candle930 -- the 09:30 candle followed at its close, with the owner's "strong candle" measures (manual lane, owner 2026-10-17).

win_candle (families/flex.py) with every rule as it is -- the tf candle that opens at `start` (09:30 default), green long / red short at its
close, structure stop = its other extreme -- plus five more gates, all off at 0 (the owner's numbers; 1 is win_candle's own body_r):
  2 close_r   the close within the outer close_r of its range (green: high - close, red: close - low, <= close_r x range)
  3 med_m     body >= med_m x the median body of the same clock candle on the 14 trade dates before (10 of 14 with a tape needed)
  4 atr_b     body >= atr_b x ATR(14) of the tf bars before it
  5 pre_min   green closes above the high, red below the low, of the 1-minute bars in the pre_min minutes before the candle
  6 big_n     body >= every body of the big_n tf bars before it (big_n of them needed)
  7 pre_n     green closes above the high, red below the low, of the pre_n candles of the candle's own size before it
SECONDS (owner 2026-10-18): sec > 0 makes the candle `sec` seconds long (a divisor of 60: 30 = the 30-second candle), read from the prints of
  [start, start + sec) at the clock time start + sec; tf stays the bars the ATR and the other blocks read (1). Entry, stop and gates as above;
  k, atr_b, big_n, med_m, vol_m and entry "break" read tf bars and are refused with sec. pre_n then counts sec-candles: the high / low of the
  prints in the pre_n x sec seconds before the candle (the highest high of those candles). Prints at or after the decision are never read.
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
_BODY: dict = {}                                    # (root, iso, open second, tf) -> |close - open| of that date's candle, or None


def past_body(root: str, iso: str, a: int, tf: int):
    """The body of the tf candle that opens `a` seconds after 00:00 ET on trade date `iso`, from its tape (None: no tape or no print)."""
    key = (root, iso, a, tf)
    if key not in _BODY:
        t = S.load_tape(iso, root, allow_holdout=S.ALLOW_BP)
        b = None
        if t is not None and len(t.ts):
            lo = S.et_ns(t.date, "00:00") + a * S.NS
            px = t.px[(t.ts >= lo) & (t.ts < lo + tf * 60 * S.NS)]
            b = float(abs(px[-1] - px[0])) if len(px) else None
        _BODY[key] = b
    return _BODY[key]


class Candle930(FX.WinCandle):
    """candle930 (module docstring): win_candle's signal, then the strong-candle gates, then its market order."""
    DEFAULTS = {**FX.WinCandle.DEFAULTS, "close_r": 0.0, "med_m": 0.0, "atr_b": 0.0, "pre_min": 0, "big_n": 0, "entry": "close",
                "sec": 0, "pre_n": 0}
    SCHEMA = {**FX.WinCandle.SCHEMA, "close_r": ("float", 0, 1), "med_m": ("float", 0, 50), "atr_b": ("float", 0, 50),
              "pre_min": ("int", 0, 600), "big_n": ("int", 0, 500), "entry": ("choice", ("close", "break")),
              "sec": ("int", 0, 59), "pre_n": ("int", 0, 100)}

    def _plan(self) -> tuple:
        sec = int(self.p["sec"])
        if not sec:
            return super()._plan()
        p = self.p
        if 60 % sec:
            raise ValueError(f"sec {sec}: a divisor of 60 (10, 15, 20, 30 ...)")
        bad = [k for k in ("k", "atr_b", "med_m", "vol_m", "big_n") if float(p[k])] + (["entry break"] if p["entry"] == "break" else [])
        if bad:
            raise ValueError(f"sec {sec} reads the candle from the prints: {', '.join(bad)} read tf bars and cannot be used with it")
        a = FX._clock(p["start"], "start")
        if a % sec:
            raise ValueError(f"start {p['start']!r} is not a whole {sec}-second candle")
        return a, a + sec, FX._home(a + sec, f"candle930 start {p['start']} sec {sec}")

    def fam_times(self):
        return [S._hms(self._plan()[1])] if int(self.p["sec"]) and self.sessions() else []

    def _prints(self, ctx, a, b):
        """The prices of the prints in [a, b) seconds after 00:00 ET of the trade date, never past the current event (no look-ahead)."""
        sim, t0 = ctx._s, S.et_ns(ctx.date, "00:00")
        ts = sim.ts[sim.lo:sim.i]
        i, j = np.searchsorted(ts, [t0 + a * S.NS, t0 + b * S.NS], side="left")
        return sim.px[sim.lo + i:sim.lo + j]

    def fam_time(self, ctx, sec):
        """sec > 0: the candle closes on the clock, not on a tf bar -> win_candle's own signal (doji, body_r, body_pts, mode) on its prints."""
        if not int(self.p["sec"]):
            return
        a, b, home = self._plan()
        if sec != b or self.sid != home or not self.can_enter(ctx):
            return
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
        ab = float(p["atr_b"])
        if ab > 0 and (not self.atr_p or body < ab * self.atr_p):
            return False
        n = int(p["big_n"])
        if n > 0 and (len(self.O) <= n or body < max(abs(y - x) for x, y in zip(self.O[-n - 1:-1], self.C[-n - 1:-1]))):
            return False
        start = self._plan()[0]
        pm = int(p["pre_min"])
        if pm > 0:
            r = self.rng(start - pm * 60, start)
            if r is None or not (c > r[0] if up else c < r[1]):
                return False
        n = int(p["pre_n"])
        if n > 0:
            sec = int(p["sec"])
            if sec:
                px = self._prints(ctx, start - n * sec, start)
                r = (float(px.max()), float(px.min())) if len(px) else None
            else:
                r = self.rng(start - n * self.tf * 60, start)
            if r is None or not (c > r[0] if up else c < r[1]):
                return False
        mm = float(p["med_m"])
        if mm > 0:
            ref = [b for b in (past_body(ctx.root, str(r["date"]), start, self.tf) for r in self.dl[-MED_DAYS:]) if b is not None]
            if len(ref) < MED_MIN or body < mm * float(np.median(ref)):
                return False
        return True


FAMILIES = {
    "candle930": (Candle930, {}, False,
                  "candle930: win_candle (the tf candle that opens at `start`, 09:30 default, followed or faded at its close, stop at its other "
                  "extreme) + the strong-candle gates, all off at 0: close_r (close in the outer share of its range), med_m (body x the 14-date "
                  "median of the same candle), atr_b (body x ATR of the bars before), pre_min (close beyond the high / low of the minutes before), "
                  "big_n (body >= every body of the bars before), pre_n (close beyond the high / low of the pre_n candles before); sec > 0 = a "
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
