"""disp_oside -- A DISPLACEMENT CANDLE AGAINST THE SIDE OF THE 09:30 OPEN (the owner's idea of 2026-10-19, the third one), written from his
words before any result: "use 9:30, if we are above 9:30 open level then short and if we are below then long, pretty much enter when we get
displacement, 1 trade a day, 30 point stop, try 1:0.5, 0.75, 1, 1.5. For displacement the body of the candle must be larger than the body of
the previous candle and has to close above the wick of the previous candle". fvg_oside's sibling (families/fvg_oside.py): same one instance,
same 09:30 open, the other way round (a fade of the side). No Level-2 feature. NQ, ES and GC, 1 contract, hold_to = 'day' (flat 15:58 ET).

THE RULE (fixed here, before any run):
  * SIDE, read at every tf close: that close below the 09:30 open (the open of the first 1-minute bar at or after 09:30) = longs only,
    above = shorts only, equal = nothing.
  * DISPLACEMENT, two tf bars, bar 1 the older: bar 2's body |close - open| larger than bar 1's body, and UP: bar 2 green and its close above
    bar 1's high; DOWN: bar 2 red and its close below bar 1's low. Read at bar 2's close, which must fall after 09:30 and before 15:00.
  * ENTRY: the first displacement on the side -> a market order at its close. One trade a day (max_tr 1).
  * STOP and TARGET: the exit cell's (the owner: 30 points; 1:0.5, 0.75, 1, 1.5). Flat 15:58 ET. The structure level passed with the
    order is the close -/+ ATR(14) of the tf bars (the owner, 2026-10-19: "use atr 14 as the stop"): stop_mode struct = a 1-ATR stop,
    stop_mode pts ignores it. stop_at candle (the owner, 2026-10-19: "use the displacement candle extreme as the stop") passes the
    displacement candle's low (long) / high (short) instead; the Template floors it at 0.25 ATR and two ticks.

MY PICKS, NOT THE OWNER'S WORDS: side read on the displacement candle's close (not tick by tick); entry at that close (market); entries
09:30-15:00; bar 1 may be the 09:25 bar.

NO LOOK-AHEAD: the side and both bars are read from closed bars; the order goes in after that close.
Tests: engine/tests/test_disp_oside.py."""
from __future__ import annotations

from .fvg_odir import LAST, OPEN, FvgOdir


class DispOside(FvgOdir):
    """disp_oside (module docstring). State per day: want = the side to enter now, or None."""
    DEFAULTS = {"stop_at": "atr", "max_tr": 1}
    SCHEMA = {"stop_at": ("choice", ("atr", "candle"))}
    SCREEN_RUN = {}

    def fam_day(self, ctx):
        self.want = None

    def fam_update(self, ctx):
        self.want = None
        step = self.tf * 60
        now = (self.M[-1][0] // step + 1) * step     # the clock close of this tf bar
        self._sync(ctx)
        if self.sid is None or now <= OPEN or now >= LAST or len(self.C) < 2 or self.n_ent:
            return
        o = self.mo(OPEN)
        if o is None:
            return
        o1, h1, l1, c1 = self.O[-2], self.H[-2], self.L[-2], self.C[-2]
        o2, c2 = self.O[-1], self.C[-1]
        if abs(c2 - o2) <= abs(c1 - o1):
            return
        if c2 < o and c2 > o2 and c2 > h1:
            self.want = "long"
        elif c2 > o and c2 < o2 and c2 < l1:
            self.want = "short"

    def fam_signal(self, ctx):
        if self.want is not None:
            sd = 1 if self.want == "long" else -1
            if self.p["stop_at"] == "candle":
                struct = self.L[-1] if sd > 0 else self.H[-1]
            else:
                struct = self.C[-1] - sd * self.atr
            self._mkt(ctx, self.want, struct=struct)


ENTRY_WINDOWS = {"disp_oside": (OPEN, LAST + 59)}

FAMILIES = {
    "disp_oside": (DispOside, {}, False,
                   "disp_oside: below the 09:30 open -> long on the first up displacement (body larger than the previous bar's, close above "
                   "its high), above the open -> short on the first down displacement; market at the close, one trade a day, entries "
                   "09:30-15:00; ONE instance 09:30-15:58; flat 15:58",
                   {"rationale": "Price away from the open is stretched, and a candle that out-sizes the one before and closes through its "
                                 "wick shows the other side stepping in hard, so the move back toward the open pays.",
                    "complexity": 4,
                    "variants": [{}]}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED, as fvg_odir.py does. Idempotent."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
