"""first5_follow -- the 09:30 candle followed at its close, a doji decided by the gap (owner idea nq_first5_follow, 2026-10-27).

win_candle (families/flex.py) with every rule as it is -- the tf candle that opens at `start` (09:30), green long / red short at its close,
structure stop = its other extreme -- plus one rule where win_candle trades nothing: a DOJI (close == open) goes long when today's open is
above the prior close (the Template's `pdc`: the last print of the previous trade date), short when below, none when equal or when `pdc`
is unknown (a contract-roll day). One trade a session, flat 15:58. Tests: engine/tests/test_first5_follow.py.
"""
from __future__ import annotations

from . import flex as FX
from . import orb830 as _orb830                       # noqa: F401 -- installs the exits "own" hook the structure stop needs
from .candle930 import MODES


class First5Follow(FX.WinCandle):
    """first5_follow (module docstring): win_candle, and a doji traded the way of the gap."""

    def fam_signal(self, ctx):
        o, h, l, c = self.O[-1], self.H[-1], self.L[-1], self.C[-1]
        if c != o or FX._bar_end(self) != self._plan()[1]:
            return super().fam_signal(ctx)
        if self.pdc is None or o == self.pdc:
            return
        side = "long" if o > self.pdc else "short"
        self._mkt(ctx, side, struct=l if side == "long" else h)


FAMILIES = {
    "first5_follow": (First5Follow, {}, False,
                      "first5_follow: the tf candle that opens at `start` (09:30 default) is followed at its close: green long, red short; a doji "
                      "goes long when the open is above the prior close, short when below; stop at the candle's other extreme; one trade a "
                      "session, flat 15:58",
                      {"rationale": "The opening candle is the first vote of the cash session; following it rides the side that had to act, and "
                                    "the stop at its other extreme is where that reading is wrong. A doji has no vote, so the overnight gap decides.",
                       "complexity": 3,
                       "variants": [{"start": "09:30"}]}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED, as candle930 does. Idempotent."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        cls.SCHEMA = {"stop_mode": ("choice", tuple(blocks.Blocks.SCHEMA["stop_mode"][1]) + MODES)}
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
