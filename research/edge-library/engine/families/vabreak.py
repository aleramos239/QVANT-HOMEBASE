"""va_break -- the VALUE AREA BREAK ON LOW EFFORT, as the video says it (Gianluca Bruni, IQCapital, video nlLGlVJGrtw, "the low-effort strategy"),
written from the video's rule before any result. No Level-2 feature is read (FEATURES = ()): NQ, 1 contract, hold_to = 'day' (flat 15:58 ET).
Rule sheet (what is taught, what is my pick): taught/RULE_SHEET_nlLGlVJGrtw_2026-10-11.md. Notes: videos/nlLGlVJGrtw.md.

THE RULE (LONG; SHORT is the exact mirror: VAL, the low, a valid up candle). Bars = the idea's own tf (the video: 15 minutes; the lane runs 5 and 15).
  * VALUE AREA  = the PRIOR trade date's 70 % value area of its 09:30-16:00 ET prints (volume by price in 1-tick rows): round1.value_area, the
                  same VAL / VAH `va_reclaim` reads. A contract-roll day has none and does not trade.
  * RTH BARS    = the tf bars that start at or after 09:30 ET. Every "so far today" below counts RTH bars only.
  * THE BREAK   = a tf bar closes at least `buf_pts` points above VAH (the video: 6 NQ points) while the bar before it closed under VAH +
                  buf_pts: the bar that breaks it, from under. It must also
      ENGULF    : close above the HIGH of the bar before it (the video: "the highest wick of the previous candle"; the size of the candle
                  does not matter), and
      LOW EFFORT: `vol` either (default) = its volume is under the EMA(20) of the tf-bar volumes of the day (from 00:00 ET) OR under the
                  previous bar's volume (the video accepts either: "below the EMA" or "reducing volume"); ema = the first only; off = no gate.
  * TREND DAY   : `trend` on (default) = the day's DEVELOPING value area (70 %, the 1-minute closes of today's RTH bars weighted by their
                  volume, 1-tick rows, read at this close) has its middle above yesterday's. off = no gate.
  * STRUCTURE   : the day's high so far (before the trigger bar) is the STRUCTURE HIGH. The STRUCTURE LOW = the low of the nearest VALID down
                  candle at or before the bar of that high (valid = its body is larger than its longer wick). A bar that trades under the
                  structure low after it (the trigger bar included) kills the setup: no entry, "forget the whole thing". No valid candle = no
                  structure low = nothing to kill it.
  * ENTRY       = market at that close. STOP = the trigger candle's low (stop_mode struct). TARGET = tgt_r x the stop distance (the video: 2),
                  cut to the structure high when that is nearer ("we cannot go above this high"); no structure high above the entry = no cut.
  * CONTINUATION: once the break trade is placed, a later bar that ENGULFS and shows LOW EFFORT enters again (no break, no trend test), until
                  a bar's high reaches the structure high of that first trade: then the leg is over and the side does not trade again that
                  day. No break trade = no continuation. One position at a time; the structure kill applies to every entry.
  * WINDOW      : ONE instance 09:30 -> 15:58 (entries 5 minutes before the end at the latest); the cap `max_tr` is a DAY cap (the video gives none:
                  default 10, the structure high ends the leg). `dir` is the Template's (the video shows the long side only).

WHAT IS MY PICK, NOT THE VIDEO'S (the video does not define them; the owner may change each): the value area is the 09:30-16:00 one;
"developing value area higher" = its middle above yesterday's; the structure high is the RTH day high before the trigger bar, the structure low
the nearest valid down candle before that bar; the EMA runs from 00:00 over the instance's own bars; the developing value area uses 1-minute
closes with the minute's volume (a print-level profile is not read); the buffer is in points, NQ's 6, never scaled.
NOT BUILT: the news-day skip (the video's "NFP, CPI at the trigger"), scoring a setup 0-5 and sizing by half Kelly, the autocorrelation of the
strategy's own trades, regime age and the ATR percentile. The lane's sheet says so under not_run.

NO LOOK-AHEAD: yesterday's value area is a prior date's prints; every test reads tf bars that have closed and the 1-minute bars the Template has
added (the developing profile stops at the trigger bar's last minute); the structure high / low read bars before the trigger bar and the
trigger bar's own low / high (closed).

REGISTRATION as orb830.py: join_blocks() puts the family into families/blocks.py's BASES and WRAPPED (blocks.py stays byte for byte as it was).
ONE_INSTANCE_PASSES: the lane reads and controls pass by pass (nyam, mid, pm) matched by day, as conti.py does. Tests: engine/tests/test_vabreak.py."""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import numpy as np

import l2sim as S
from l2sim import Template
from families.round1 import NY, OPEN, bar_end, build_va, value_area, value_area_of

END_S = 57480                                       # 15:58 ET, seconds after 00:00
EMA_N = 20


def developing_value_area(st):
    """(VAL, VAH) of the day's RTH prints so far: the Template's completed 1-minute bars from 09:30, each minute's volume at its close,
    through round1.value_area_of (the same 70 % / tick rows rule). None before a minute with volume."""
    rows = [m for m in st.M if m[0] >= OPEN and m[5] > 0]
    if not rows:
        return None
    d = dt.date.fromisoformat(st.day)
    base = S.et_ns(d, "00:00")
    tape = SimpleNamespace(root=st.root, date=d, ts=np.array([base + int(m[0]) * S.NS for m in rows], dtype=np.int64),
                           px=np.array([m[4] for m in rows], dtype=np.float64), size=np.array([m[5] for m in rows], dtype=np.float64))
    return value_area_of(tape)


class VaBreak(Template):
    """va_break (module docstring). State per day: va = yesterday's (VAL, VAH) or None, be = the nominal close second of every tf bar (parallel
    to H, L, O, C, V), i0 = the index of the first RTH bar, ev = EMA(20) of the volumes, took[sd] = the break trade of that side was placed,
    cont[sd] = the structure level the first trade of that side aims at while the leg lives (None: no leg, or it is over)."""
    DEFAULTS = {"buf_pts": 6.0, "vol": "either", "trend": "on", "max_tr": 10}
    SCHEMA = {"buf_pts": ("float", 0.0, 100.0), "vol": ("choice", ("either", "ema", "off")), "trend": ("choice", ("on", "off"))}
    SCREEN_TFS = ("1", "5", "15")
    ONE_INSTANCE_PASSES = NY                         # the session passes this ONE instance stands for (the taught lane reads it)
    FEATURES = ()

    @classmethod
    def prepare(cls, root, workers=1, period="build", **allow):
        return build_va(root, period, workers, **allow)

    def fam_sessions(self):
        return {"t": (OPEN, END_S)}

    def fam_filter(self, ids):
        return ["t"] if "nyam" in ids else []        # the one live pass; mid / pm run nothing (the lane's pass list stays nyam, mid, pm)

    def fam_day(self, ctx):
        self.be, self.i0, self.ev = [], None, None
        self.took, self.cont = {1: False, -1: False}, {1: None, -1: None}
        d1 = self.dl[-1] if self.dl else None
        # self.pdc is None on a contract-roll day: yesterday's prices are another contract -> no value area today
        self.va = value_area(ctx.root, d1["date"]) if d1 and d1.get("date") and self.pdc is not None else None

    def fam_update(self, ctx):
        end = bar_end(self)
        self.be.append(end)
        if self.i0 is None and end - self.tf * 60 >= OPEN:
            self.i0 = len(self.be) - 1
        v = self.V[-1]
        self.ev = v if self.ev is None else self.ev + (v - self.ev) * 2.0 / (EMA_N + 1)
        for sd in (1, -1):                           # the leg is over once a bar reaches its structure level
            ref = self.cont[sd]
            if ref is not None and (self.H[-1] >= ref if sd > 0 else self.L[-1] <= ref):
                self.cont[sd] = None

    def _effort(self) -> bool:
        m = self.p["vol"]
        if m == "off":
            return True
        v = self.V[-1]
        low = v < self.ev
        return low if m == "ema" else (low or v < self.V[-2])

    def _structure(self, sd):
        """-> (dead, level): level = the RTH high (long) / low (short) before the trigger bar; dead = a bar after the nearest valid
        opposite candle at or before that extreme's bar, up to and including the trigger bar, traded beyond that candle's far end."""
        H, L, O, C, i0, j = self.H, self.L, self.O, self.C, self.i0, len(self.H) - 1
        if sd > 0:
            lvl = max(H[i0:j])
            jx = max(k for k in range(i0, j) if H[k] == lvl)
            for k in range(jx, i0 - 1, -1):
                body = O[k] - C[k]
                if body > 0 and body > max(H[k] - O[k], C[k] - L[k]):          # a valid down candle
                    return min(L[k + 1:j + 1]) < L[k], lvl
            return False, lvl
        lvl = min(L[i0:j])
        jx = max(k for k in range(i0, j) if L[k] == lvl)
        for k in range(jx, i0 - 1, -1):
            body = C[k] - O[k]
            if body > 0 and body > max(H[k] - C[k], O[k] - L[k]):              # a valid up candle
                return max(H[k + 1:j + 1]) > H[k], lvl
        return False, lvl

    def _trend(self, sd) -> bool:
        dv = developing_value_area(self)
        return dv is not None and (sum(dv) - sum(self.va)) * sd > 0

    def fam_signal(self, ctx):
        j, i0 = len(self.H) - 1, self.i0
        if self.va is None or i0 is None or j - i0 < 1:
            return
        c, buf = self.C[-1], float(self.p["buf_pts"])
        for sd in (1, -1):
            side = "long" if sd > 0 else "short"
            if not self.allowed(side) or (c - (self.H[-2] if sd > 0 else self.L[-2])) * sd <= 0 or not self._effort():
                continue                             # no engulf, or too much effort
            if self.took[sd]:
                cap = self.cont[sd]
                if cap is None:
                    continue                         # the leg reached its structure level: over
            else:
                lvl = self.va[1] if sd > 0 else self.va[0]
                if (c - lvl) * sd < buf or (self.C[-2] - lvl) * sd >= buf:
                    continue                         # not the bar that breaks the level from under
                if self.p["trend"] == "on" and not self._trend(sd):
                    continue
            dead, hl = self._structure(sd)
            if dead:
                continue
            if not self.took[sd]:
                cap = hl if (hl - c) * sd > 0 else None
            stop_px = self.L[-1] if sd > 0 else self.H[-1]        # the trigger candle's other extreme
            tp = None
            if cap is not None:
                r = self.p["tgt_r"]
                d = self._dist(ctx, c, stop_px)
                tp = cap if r <= 0 else min(c + r * d, cap) if sd > 0 else max(c - r * d, cap)
            o = self._mkt(ctx, side, struct=stop_px, tp_px=tp)
            if o is not None and not self.took[sd]:
                self.took[sd], self.cont[sd] = True, cap
            if o is not None:
                return


# entry windows, ET seconds after 00:00 [first, last]: the smoke's "entries outside the window" count (the second RTH bar of a 5-minute run)
ENTRY_WINDOWS = {"va_break": (OPEN + 5 * 60, END_S - 1)}

FAMILIES = {
    "va_break": (VaBreak, {}, False,
                 "va_break: a tf bar closes at least buf_pts above the PRIOR session's value-area high (9:30-16:00 volume by price) after a bar "
                 "that closed under it, engulfing the previous bar's high on volume under its EMA(20) or under the previous bar's, on a day "
                 "whose developing value area sits higher -> market long, stop at the trigger candle's low, target 2R cut to the day's "
                 "structure high; later engulfing low-effort bars enter again until the structure high is reached; a bar under the "
                 "structure low (the last valid down candle before the day's high) kills it; SHORT = the mirror; flat 15:58",
                 {"rationale": "Buyers who defended the old value area and push price out of its top on a candle that took little volume to do "
                               "it show the sellers there are spent: the move needs no effort, and the traders who sold the pullback have "
                               "their stops just above, so the stop-outs feed it until the day's high.",
                  "complexity": 9,
                  "roots": ("NQ",),
                  "variants": [{"buf_pts": 3.0}, {"buf_pts": 6.0}, {"buf_pts": 9.0}]}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (module docstring, REGISTRATION). Idempotent."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
