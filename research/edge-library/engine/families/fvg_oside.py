"""fvg_oside -- THE MOST RECENT FAIR VALUE GAP ON THE SIDE OF THE 09:30 OPEN (the owner's idea of 2026-10-19, the second one), written
from his words before any result: "if we are above the 9:30 open level, we enter on the most recent 5 minute fvg, vice versa for shorts,
use the middle candle extreme as the stop and 1:0.5". fvg_odir's sibling (families/fvg_odir.py): same gap, same stop, same order; only
the side and the choice of gap differ. NQ, ES and GC, 1 contract, hold_to = 'day' (flat 15:58 ET).

THE RULE (fixed here, before any run):
  * SIDE, read at every tf close: that close above the 09:30 open (the open of the first 1-minute bar at or after 09:30) = longs only,
    below = shorts only, equal = nothing.
  * THE GAP is fvg_odir's: three tf bars; UP = bar 3's low above bar 1's high (near edge bar 3's low), DOWN the mirror, size >= one tick;
    read at bar 3's close, which must fall after 09:30 and before 15:00. The newest gap of each side is kept (a newer one replaces it).
  * THE ORDER: a LIMIT at the near edge of the newest gap of the current side. A newer gap moves it; a flip of the side cancels it and
    rests the other side's newest gap (if there is one). A gap whose near edge is not on the passive side of the last print rests nothing.
    One trade a day (max_tr 1); an unfilled order is cancelled at 15:00.
  * THE STOP: the middle candle's far end (bar 2's low up / high down), floored by the Template at 0.25 ATR and two ticks. A middle candle
    whose far end is not beyond the near edge gives no order. THE TARGET: the exit cell's tgt_r (the owner: 0.5). Flat 15:58 ET.

MY PICKS, NOT THE OWNER'S WORDS: side read on the tf close (not tick by tick); entry at the near edge; entries 09:30-15:00; one trade a day.

NO LOOK-AHEAD: the side, the gap and bar 2 are read from closed bars; the order is placed or moved after that close.
Tests: engine/tests/test_fvg_oside.py."""
from __future__ import annotations

from .fvg_odir import LAST, OPEN, FvgOdir


class FvgOside(FvgOdir):
    """fvg_oside (module docstring). State per day: last = {+1 / -1: (near edge, middle candle's far end)}, want = (side, px, struct) to rest
    now or None, placed = the `want` the working order was placed for."""
    DEFAULTS = {"min_gap": 0.0, "mode": "touch", "max_tr": 1}
    SCHEMA = {"min_gap": ("float", 0.0, 10.0)}

    def fam_day(self, ctx):
        self.last, self.want, self.placed = {}, None, None

    def fam_update(self, ctx):
        step = self.tf * 60
        now = (self.M[-1][0] // step + 1) * step     # the clock close of this tf bar
        self._sync(ctx)
        if now >= LAST:
            if self.orders and ctx.flat:
                self._cancel(ctx)                    # an unfilled order dies at 15:00
            self.want = None
            return
        if self.sid is None or now <= OPEN or len(self.H) < 3 or self.n_ent:
            self.want = None
            return
        h1, l1, h3, l3 = self.H[-3], self.L[-3], self.H[-1], self.L[-1]
        for sd, near, far, struct in ((1, l3, h1, self.L[-2]), (-1, h3, l1, self.H[-2])):
            if (near - far) * sd > 0 and abs(near - far) >= max(self.p["min_gap"] * self.atr, ctx.tick):
                self.last[sd] = (near, struct) if (near - struct) * sd > 0 else None
        o = self.mo(OPEN)
        sd = 0 if o is None else (self.C[-1] > o) - (self.C[-1] < o)
        g = self.last.get(sd) if sd else None
        self.want = ("long" if sd > 0 else "short", g[0], g[1]) if g else None
        if self.orders and self.want != self.placed:
            self._cancel(ctx)                        # a newer gap or a flip of the side: the resting order moves

    def fam_signal(self, ctx):
        if self.want is not None and self._lim(ctx, *self.want[:2], struct=self.want[2]) is not None:
            self.placed = self.want


ENTRY_WINDOWS = {"fvg_oside": (OPEN, LAST + 59)}

FAMILIES = {
    "fvg_oside": (FvgOside, {}, False,
                  "fvg_oside: above the 09:30 open -> a limit at the near edge of the most recent up fair value gap, below -> the most recent "
                  "down gap; a newer gap or a flip of the side moves the order; stop at the middle candle's far end (stop_mode struct), "
                  "one trade a day, entries 09:30-15:00, unfilled order cancelled at 15:00; ONE instance 09:30-15:58; flat 15:58",
                  {"rationale": "Price above the open shows buyers in control, and the newest gap on their side is the footprint of orders "
                                "that wanted in and were left unfilled, so the return to it meets that interest while the traders fading "
                                "the open's side pay.",
                   "complexity": 6,
                   "variants": [{"min_gap": 0.0}, {"min_gap": 0.1}, {"min_gap": 0.25}]}),
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
