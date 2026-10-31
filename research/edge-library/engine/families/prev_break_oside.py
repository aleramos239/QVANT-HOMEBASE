"""prev_break_oside -- the previous candle's high / low broken, only on the side of the 09:30 open (owner idea 1 of ideas-100-simple, 2026-10-28).

A tf bar CLOSES strictly above the previous bar's high = long, strictly below its low = short (candle_sweep mode break), and only when that
close is on the same side of the day's 09:30 open (the open of the first 1-minute bar at or after 09:30 ET): a long needs close > open, a short
close < open; equal = no trade. Market entry at the close. The STRUCTURE LEVEL (the stop's own cell) is the PREVIOUS bar's other end: a long's
stop is its low, a short's its high (candle_sweep's break uses THIS bar's extreme instead). Entries inside the idea's session, up to per_day
a session, one position at a time, flat 15:58. Tests: engine/tests/test_prev_break_oside.py.
"""
from __future__ import annotations

from .candle_sweep import CandleSweep

OPEN930 = 34200                                       # 09:30 ET in seconds after 00:00


class PrevBreakOside(CandleSweep):
    """prev_break_oside (module docstring)."""
    DEFAULTS = {**CandleSweep.DEFAULTS, "mode": "break", "per_day": 20}
    SCHEMA = {**CandleSweep.SCHEMA, "per_day": ("int", 1, 20)}                 # the main setting: entries a session (it sets max_tr)

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self.p["max_tr"] = self.p["per_day"]

    def open930(self):
        """The open of the first 1-minute bar at or after 09:30 ET today, or None before it exists."""
        return next((m[1] for m in self.M if m[0] >= OPEN930), None)

    def fam_signal(self, ctx):
        if self.nb < 2:
            return
        h, l, c = self.H[-2], self.L[-2], self.C[-1]
        o = self.open930()
        if o is None:
            return
        if c > h and c > o:
            self._mkt(ctx, "long", struct=l)
        elif c < l and c < o:
            self._mkt(ctx, "short", struct=h)


FAMILIES = {
    "prev_break_oside": (PrevBreakOside, {}, False,
                         "prev_break_oside: a tf bar closes beyond the previous bar's high (low) while the close is above (below) the 09:30 open "
                         "-> market long (short) at the close; structure stop = the previous bar's other end (own stop = its distance x 0.5 / 1 / "
                         "1.5 / 2); entries inside the idea's session, up to per_day entries a session, one position at a time; flat 15:58",
                         {"rationale": "A close through the last candle's high or low runs the stops and breakout orders resting there; on the side "
                                       "the day has already voted for (the 09:30 open) that push has the day's flow behind it, and the stop sits "
                                       "where the broken candle is taken back.",
                          "complexity": 3,
                          "variants": [{"per_day": 1}, {"per_day": 3}, {"per_day": 20}]}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED, as first5_follow does. Idempotent."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
