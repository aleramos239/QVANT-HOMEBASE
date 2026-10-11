"""conti_both -- the drift VWAP pullback with BOTH sides in ONE instance, each side with the video's own target
(Matteo Conti, video wm4A6qo0g3I; owner 2026-10-11: "do number 1": long and short run as one strategy).

It is conti.VwapTrendDay (one instance for the day, stop after `max_loss` losing trades in a row, VWAP slope `slope_min` minutes)
with ONE difference: the short side's target is `short_tgt_x` times the long side's. The cell's `tgt_r` x stop is the long target
(stop 80 x 0.5 = 40 points); the short target is that x short_tgt_x (1.25 -> 50 points), the video's "80 to make 40 long, 80 to
make 50 short". Everything the day instance counts is now counted over BOTH sides: the cap of 4 trades a day, one position at a
time, the stop after 2 losing trades in a row.
"""
from __future__ import annotations

import sys

from families.conti import VwapTrendDay
from families.round1 import VwapTrendPull

NAME = "vwap_trend_both"


class VwapTrendBoth(VwapTrendDay):
    """conti.VwapTrendDay with the short target `short_tgt_x` times the long one."""
    DEFAULTS = {**VwapTrendDay.DEFAULTS, "short_tgt_x": 1.25}
    SCHEMA = {**VwapTrendDay.SCHEMA, "short_tgt_x": ("float", 0.25, 4.0)}

    def fam_signal(self, ctx):
        from families.conti import _in_a_row
        if not self.go or not VwapTrendPull.T0 <= self._bar_end() <= VwapTrendPull.T1:
            return
        if _in_a_row(ctx._s.res.trades) >= self.p["max_loss"]:
            return
        if self.go > 0:
            self._mkt(ctx, "long")
            return
        ref, r = self.C[-1], float(self.p["tgt_r"])
        tp = ref - r * float(self.p["short_tgt_x"]) * self._dist(ctx, ref, None) if r > 0 else None
        self._mkt(ctx, "short", tp_px=tp)


FAMILIES = {
    NAME: (VwapTrendBoth, {}, False,
           "CONTI vwap_trend_both: the drift VWAP pullback, long and short in ONE day instance; the short target is short_tgt_x "
           "times the long one (the video: stop 80, target 40 long / 50 short); max 4 trades a day over both sides, stop after "
           "2 losing trades in a row, entries 10:30-15:30 ET. Taught lane only",
           {"rationale": "When price holds above (below) a rising (falling) session VWAP, the day's buyers (sellers) are in profit "
                         "and dips (pops) get bought (sold); the first candle against the trend gives a better price in the "
                         "direction of the day's flow.",
            "complexity": 10,
            "roots": ("NQ",),
            "variants": [{"x": 0.10}]}),
}
ENTRY_WINDOWS = {NAME: (VwapTrendPull.T0, VwapTrendPull.T1 + 59)}


def __getattr__(name: str):
    """B_vwap_trend_both: built on first use, as conti.B_vwap_trend_day (the worker processes unpickle it by this module's name)."""
    if name == "B_" + NAME:
        from families import blocks
        cls = blocks._wrap(NAME, VwapTrendBoth)
        cls.__module__ = __name__
        setattr(sys.modules[__name__], cls.__name__, cls)
        return cls
    raise AttributeError(name)
