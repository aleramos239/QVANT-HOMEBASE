"""hurstac -- "Trader Math"'s trend-dip breakout as the video says it (IQCapital, video O4ASr0fh7O8, owner's go 2026-10-11).
Rule sheet: taught/RULE_SHEET_O4ASr0fh7O8_2026-10-11.md. Written from the sheet before any result. No Level-2 feature (FEATURES = ()).

    hurst_ac_break   bar-based 5 / 15 / 30   ONE instance for the ET day (00:00 -> 15:58 ET); the evening session is not run

THE RULE (every number is the sheet's, picks marked P)
  * H  = "Hurst proxy" (P1): over the last `h_win` bars, H = ln( M(k-bar change) / M(1-bar change) ) / (2 ln k) x 100, k = `h_k`, where M is
         the mean SQUARE (about zero, not demeaned: a steady drift is persistence; the demeaned form scores a clean trend 0), clamped 0..100.
         50 = a random walk; above 50 = persistent; a straight line = 100. The k-bar changes are the h_win overlapping close(t) - close(t-k).
  * AC = autocorrelation (P2): the Pearson correlation of the 1-bar close change with the 1-bar close change `ac_lag` bars earlier, over the
         last `ac_win` bars.
  * BREAK = the bar's close is above the highest HIGH of the previous `brk_n` bars (the current bar not counted); short = the mirror
         (below the lowest LOW).
  * SIGNAL (read at a tf close): H > `h_min` AND AC <= `ac_max` AND BREAK. `use_h` / `use_ac` "off" drops that filter: the control the
         owner's question needs ("what do the two filters add to the 5-bar break").
  * ENTRY (P3): a market order at that close, filled at the next bar's first print. ONE position at a time (one instance), no scale-in.
  * ATR (P4): the simple mean of the last `atr_n` true ranges of the tf bars, frozen at the signal bar.
  * EXITS: stop = entry - `stop_atr` x ATR at the fill; target = `tgt_r` x that stop distance (tgt_r 1.25 with stop 4 ATR = 5 ATR: the
         video's 5 x ATR). TRAILING (P5, `trail` on): at every bar close the stop moves to max(stop, highest HIGH since entry - `stop_atr` x ATR
         at entry), never down; it is a resting stop order (fills at the level, or through it on a gap). `hold_to` day: flat 15:58 ET.
  * SIDES (T3): `dir` long (the video shows no short); the mirror exists for a later sheet.
  * HOURS (P6): the window is 00:00 -> 15:58 ET (asia, london, pre, NY: one instance, one position at a time). The engine refuses a window
         across midnight, so the evening 18:00-23:59 is NOT run (a difference from the video's 24-hour chart). The indicators restart at 00:00,
         so the first signal needs `warm` bars (26 at the defaults: 6.5 h of 15-minute bars, first signal 06:30 ET).

REGISTRATION: like noise.py, join_blocks() puts the family into families/blocks.py's BASES / WRAPPED (blocks.py stays byte for byte).
Tests: engine/tests/test_hurstac.py."""
from __future__ import annotations

import math

from l2sim import Template, to_tick

NAME = "hurst_ac_break"
TFS = ("5", "15", "30")
T0_S, END_S = 0, 57480                # 00:00 ET . 15:58 ET (seconds after 00:00 ET of the trade date)
DAY_PASSES = ("asia", "london", "pre", "nyam", "mid", "pm")


def hurst_proxy(C, win: int, k: int):
    """H x 100 from the closes C (oldest first): the variance ratio of k-bar to 1-bar changes over the last `win` bars, or None."""
    n = len(C)
    if win < 3 or k < 2 or n < win + k + 1:
        return None
    d1 = [C[i] - C[i - 1] for i in range(n - win, n)]
    dk = [C[i] - C[i - k] for i in range(n - win, n)]
    v1 = sum(x * x for x in d1) / win               # NOT demeaned: a steady drift is persistence (a perfect trend scores 100)
    vk = sum(x * x for x in dk) / win
    if v1 <= 0 or vk <= 0:
        return None
    h = 0.5 * math.log(vk / v1) / math.log(k)
    return min(100.0, max(0.0, 100.0 * h))


def autocorr(C, win: int, lag: int):
    """Pearson correlation of the 1-bar change with the 1-bar change `lag` bars earlier, over the last `win` bars, or None."""
    n = len(C)
    if win < 3 or lag < 1 or n < win + lag + 1:
        return None
    x = [C[i] - C[i - 1] for i in range(n - win, n)]
    y = [C[i - lag] - C[i - lag - 1] for i in range(n - win, n)]
    mx, my = sum(x) / win, sum(y) / win
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx <= 0 or syy <= 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(sxx * syy)


class HurstAcBreak(Template):
    """hurst_ac_break (module docstring)."""
    DEFAULTS = {"h_min": 50.0, "ac_max": -0.1, "h_win": 20, "h_k": 5, "ac_win": 20, "ac_lag": 5, "brk_n": 5, "atr_n": 20,
                "stop_atr": 4.0, "use_h": "on", "use_ac": "on", "trail": "on",
                "stop_mode": "struct", "tgt_r": 1.25, "dir": "long", "max_tr": 20, "hold_to": "day"}
    SCHEMA = {"h_min": ("float", 0.0, 100.0), "ac_max": ("float", -1.0, 1.0), "h_win": ("int", 5, 100), "h_k": ("int", 2, 20),
              "ac_win": ("int", 5, 100), "ac_lag": ("int", 1, 20), "brk_n": ("int", 1, 50), "atr_n": ("int", 2, 100),
              "stop_atr": ("float", 0.5, 20.0), "use_h": ("choice", ("on", "off")), "use_ac": ("choice", ("on", "off")),
              "trail": ("choice", ("on", "off"))}
    SCREEN_TFS = TFS
    FEATURES = ()
    ONE_INSTANCE_PASSES = DAY_PASSES                 # ONE instance stands for every pass: the taught lane reads this

    # ---- the one window
    def fam_sessions(self):
        return {"t": (T0_S, END_S)}

    def fam_filter(self, ids):
        return ["t"] if "nyam" in ids else []        # the one live pass; the lane's pass list stays asia .. eve

    def fam_day(self, ctx):
        self.sig_atr = None
        self.trk = None                              # (id of the position being trailed, highest high / lowest low since entry)

    # ---- the signal
    def _warm(self) -> int:
        p = self.p
        return max(p["h_win"] + p["h_k"] + 1, p["ac_win"] + p["ac_lag"] + 1, p["brk_n"] + 1, p["atr_n"])

    def read(self):
        """(H, AC, BREAK side +1 / -1 / 0, ATR) of the bar that has just closed; any may be None while not warm."""
        p, C = self.p, self.C
        if len(C) < self._warm():
            return None, None, 0, None
        H = hurst_proxy(C, p["h_win"], p["h_k"])
        AC = autocorr(C, p["ac_win"], p["ac_lag"])
        n = p["brk_n"]
        hi, lo = max(self.H[-1 - n:-1]), min(self.L[-1 - n:-1])
        brk = 1 if C[-1] > hi else (-1 if C[-1] < lo else 0)
        atr = sum(self.TR[-p["atr_n"]:]) / p["atr_n"]
        return H, AC, brk, atr

    def fam_signal(self, ctx):
        p = self.p
        H, AC, brk, atr = self.read()
        if brk == 0 or atr is None or atr <= 0:
            return
        if p["use_h"] == "on" and (H is None or not H > p["h_min"]):
            return
        if p["use_ac"] == "on" and (AC is None or not AC <= p["ac_max"]):
            return
        side = "long" if brk > 0 else "short"
        if not self.allowed(side):
            return
        self.sig_atr = atr
        ref = self.C[-1]
        self._mkt(ctx, side, struct=ref - brk * p["stop_atr"] * atr)

    # ---- the trailing stop
    def _manage(self, ctx):
        done = super()._manage(ctx)
        if done or ctx.flat or self.fill_ns is None or self.p["trail"] != "on" or self.sig_atr is None:
            return done
        s = ctx._s
        if not s.positions:
            return done
        pos = s.positions[0]
        sl = pos.sl
        if sl is None or sl.status != "working":
            return done
        sd = pos.side
        if self.trk is None or self.trk[0] != id(pos):
            self.trk = (id(pos), pos.entry_px)
        ext = self.trk[1]
        ext = max(ext, self.H[-1]) if sd > 0 else min(ext, self.L[-1])
        self.trk = (id(pos), ext)
        level = to_tick(ext - sd * self.p["stop_atr"] * self.sig_atr, s.tick)
        if (level - sl.price) * sd > 0:
            sl.price = level
        return done


FAMILIES = {
    NAME: (HurstAcBreak, {}, False,
           "hurst_ac_break: Hurst proxy > h_min, autocorrelation (lag ac_lag over ac_win bars) <= ac_max and a close beyond the previous brk_n bars' "
           "high / low -> market with the break; stop stop_atr x ATR(atr_n) trailing with the highest high, target tgt_r x the stop; ONE instance "
           "for the ET day (00:00 -> 15:58 ET). Taught lane: the video O4ASr0fh7O8 as taught",
           {"rationale": "A market that keeps moving one way (persistent) and has just pulled back a little (negative short-lag autocorrelation) "
                         "resumes its direction when it breaks the last few bars' extreme: the pullback's holders are the ones squeezed, and a "
                         "wide trailing stop lets the winners run.",
            "complexity": 7,
            "variants": [{"h_min": 50.0}]}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (as noise.py does); idempotent."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
