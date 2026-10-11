"""conti -- the taught lane's "Drift VWAP pullback" as the video says it (Matteo Conti, video wm4A6qo0g3I, owner answers 2026-10-10).

It is `round1.VwapTrendPull` (family N1) with the three differences the owner asked for, and nothing else:

  * ONE instance for the whole day. N1 runs as three independent session passes (nyam / mid / pm), so its cap of 4 trades and its
    stop after 2 losses count inside each pass. Here ONE instance holds the window 10:30 -> 15:58 (entries 10:30 -> 15:30, flat
    15:58; it opens at 10:29:59 so the bar that closes at 10:30 counts): the cap of 4 trades is a DAY cap, one position at a time holds for the whole day, a loss stop counts over the day.
  * "2 losses" = 2 losing trades IN A ROW (the video: "if you have two consecutive trades that are losing trades for the day, we
    stop trading it"). N1 counts any 2 losing trades of the pass.
  * "VWAP higher than 15 minutes ago": the slope is read `slope_min` MINUTES back (15), whatever the bar size. N1 reads it 3 bars
    back, which is 45 minutes on 15-minute bars. On 1-minute bars: 15 bars; on 5-minute bars: 3 bars; on 15-minute bars: 1 bar.

The state, the trigger and the rest are N1's, read from the same code: VWAP = volume-weighted (h + l + c) / 3 of the 1-minute bars
from 09:30; LONG state at a tf close: close > VWAP, VWAP > VWAP `slope_min` minutes ago, close >= x % above the close 60 minutes
ago; trigger = the first down bar of a pullback while the state holds -> market long; SHORT = the mirror.

The family is the SAME class as N1 for everything but those three lines, so `tests/test_taught.py` checks it against N1: with the
losses-in-a-row stop and the per-day cap switched off, its trades are those of the three N1 passes (tf 5, where 3 bars = 15 min).
"""
from __future__ import annotations

import sys

from families.round1 import NY, VwapTrendPull

NAME = "vwap_trend_day"
T0_S, FLAT_WINDOW_END_S = 37799, 57480              # the window opens 1 s before 10:30 ET so that the bar closing AT 10:30 is inside it (N1: T0 <= bar_end)


def _in_a_row(trades) -> int:
    """How many losing trades end the list of closed trades (net < 0 after costs), counted backwards from the last."""
    n = 0
    for t in reversed(trades):
        if t["net"] >= 0:
            break
        n += 1
    return n


class VwapTrendDay(VwapTrendPull):
    """The drift VWAP pullback over ONE day instance, stop after `max_loss` losing trades in a row, VWAP slope `slope_min` minutes."""
    DEFAULTS = {**VwapTrendPull.DEFAULTS, "slope_min": 15}
    SCHEMA = {**VwapTrendPull.SCHEMA, "slope_min": ("int", 1, 120)}
    SCREEN_TFS = ("1", "5", "15")
    ONE_INSTANCE_PASSES = NY                         # the session passes this ONE instance stands for (the taught lane reads it)

    def fam_sessions(self):
        return {"t": (T0_S, FLAT_WINDOW_END_S)}

    def fam_filter(self, ids):
        return ["t"] if "nyam" in ids else []        # the one live pass; mid / pm run nothing (the lane's pass list stays nyam, mid, pm)

    def fam_day(self, ctx):
        super().fam_day(ctx)
        self.SLOPE = max(1, int(self.p["slope_min"]) // int(self.tf))

    def fam_signal(self, ctx):
        if not self.go or not VwapTrendPull.T0 <= self._bar_end() <= VwapTrendPull.T1:
            return
        if _in_a_row(ctx._s.res.trades) >= self.p["max_loss"]:
            return                                   # stop for the day after max_loss losing trades in a row
        if self.p["auth"] != "on":
            self._mkt(ctx, "long" if self.go > 0 else "short")
        elif self.go > 0:
            self._mkt(ctx, "long", tp_px=self.C[-1] + self.AUTH["long"])
        else:
            self._mkt(ctx, "short", tp_px=self.C[-1] - self.AUTH["short"])

    def _bar_end(self) -> int:
        from families.round1 import bar_end
        return bar_end(self)


FAMILIES = {
    NAME: (VwapTrendDay, {}, False,
           "CONTI vwap_trend_day: close above a rising 09:30 VWAP (up over the last slope_min minutes) and up >= X % over 60 min, "
           "first down bar -> market long (mirror short); ONE instance for the day, entries 10:30-15:30 ET, max 4 trades a day and "
           "stop after 2 losing trades in a row. Taught lane only: the video's own cell is stop 80 pts, target 40 long / 50 short",
           {"rationale": "When price holds above a rising session VWAP, the day's buyers are in profit and dips get bought; the "
                         "first candle against the trend gives a better price in the direction of the day's flow.",
            "complexity": 9,
            "roots": ("NQ",),
            "variants": [{"x": 0.10}]}),
}
ENTRY_WINDOWS = {NAME: (VwapTrendPull.T0, VwapTrendPull.T1 + 59)}


def __getattr__(name: str):
    """B_vwap_trend_day: the blocks-wrapped class the taught lane runs, built on first use. It lives HERE (the worker
    processes unpickle a class by this module's name), not in families/blocks.py, which is hashed into every store's code stamp."""
    if name == "B_" + NAME:
        from families import blocks                  # imported late: blocks reads the other family modules
        cls = blocks._wrap(NAME, VwapTrendDay)
        cls.__module__ = __name__
        setattr(sys.modules[__name__], cls.__name__, cls)
        return cls
    raise AttributeError(name)
