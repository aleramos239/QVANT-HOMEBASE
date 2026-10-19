"""fvg_odir -- THE FIRST FAIR VALUE GAP WITH THE OPENING HALF HOUR'S DIRECTION (the owner's idea of 2026-10-19), written from his words
before any result: "NQ 15 minute time frame, trade from 10 am until 3 pm, look at the direction of 9:30-10 am and take the first fvg in that
direction, use the middle candle in the fvg as the stop and trade for a 1:1, 1 trade a day". No Level-2 feature is read (FEATURES = ()):
NQ, ES and GC, 1 contract, hold_to = 'day' (flat 15:58 ET).

THE RULE (fixed here, before any run):
  * DIRECTION. The close of the last 1-minute bar that starts in 09:30 .. 10:00 ET minus the open of the first one at or after 09:30
    (Template.mo / mc). Above 0 = up (longs only), below = down (shorts only), 0 or no print = no trade that day. Read at the first tf close
    at or after 10:00, from 1-minute bars that had closed.
  * THE GAP is fvg's (families/fvg.py): three tf bars, bar 1 the oldest. UP: bar 3's low above bar 1's high, near edge bar 3's low, far edge
    bar 1's high; DOWN the mirror. Far to near edge >= max(min_gap x ATR14 of the tf, one tick). Read at bar 3's close.
  * FIRST ONE IN THE DIRECTION. Only gaps whose bar 3 closes AFTER 10:00 and BEFORE 15:00 count (bar 1 and bar 2 may be older), and only
    the side of the direction (an up day ignores down gaps). The first such gap is the day's signal; every later gap is ignored, whether or
    not its order is placed or fills (max_tr 1: one trade a day).
  * pick (the owner, 2026-10-19): first (default, the rule above) | newest = while no trade has filled today, every NEW gap on the side
    cancels the resting order and takes its place (the most recent gap); the first fill ends the day (max_tr 1). With max_tr above 1
    (1 .. 20) the next new gap on the side after a trade has closed is the next entry, until max_tr trades a day (newest only).
  * THE ORDER, `mode` (fvg's): touch = a LIMIT at the near edge (default), mid = a limit at the gap's middle, go = market at bar 3's close.
    A resting limit is cancelled at the first tf close at or after 15:00. The family runs with strict_limit (fvg's).
  * THE STOP (stop_mode struct): the MIDDLE candle's far end -- bar 2's LOW for an up gap, bar 2's HIGH for a down gap. The Template floors
    it at 0.25 ATR and two ticks, as for every family. A bar 2 whose far end is not beyond the entry (it can sit above an up gap's near
    edge) gives no stop: the signal is used and no order is placed.
  * atr1 (the owner, 2026-10-19; default 0 = the middle-candle stop above): > 0 = the stop is atr1 x ATR14 of the 1-MINUTE bars (the mean
    true range of the 14 newest completed minutes at bar 3's close) from the entry, with no 0.25 x tf-ATR floor (two ticks only).
  * THE TARGET is the exit cell's tgt_r (the owner: 1:1). Flat 15:58 ET.
  * WINDOW: ONE instance 09:30 -> 15:58 (vabreak.py's way), so the cap is a DAY cap and a gap may span 11:00 or 13:30.

MY PICKS, NOT THE OWNER'S WORDS (he may change each): direction = 10:00 vs 09:30 price (not the candle colour of a 30-minute bar on another
grid, the same thing on 15 / 30-minute bars); the gap must complete after 10:00; entry at the near edge; an unfilled order dies at 15:00.

NO LOOK-AHEAD: the direction reads 1-minute bars that ended by 10:00, at a close at or after 10:00; the gap, its edges and bar 2 are the three
newest closed tf bars; the order is placed after that close.

REGISTRATION as vabreak.py: join_blocks() puts the family into families/blocks.py's BASES and WRAPPED (blocks.py stays byte for byte).
Tests: engine/tests/test_fvg_odir.py."""
from __future__ import annotations

from l2sim import Template

OPEN, DIR_END, LAST, END_S = 34200, 36000, 54000, 57480     # 09:30, 10:00, 15:00, 15:58 ET, seconds after 00:00
NY = ("nyam", "mid", "pm")
MODES = ("touch", "mid", "go")


class FvgOdir(Template):
    """fvg_odir (module docstring). State per day: dir = +1 / -1 / 0 (no trade) / None (not read yet), used = the day's signal is taken,
    gap = this close's signal (side, entry, structure level) or None."""
    DEFAULTS = {"min_gap": 0.0, "mode": "touch", "pick": "first", "atr1": 0.0, "max_tr": 1}
    SCHEMA = {"min_gap": ("float", 0.0, 10.0), "mode": ("choice", MODES), "pick": ("choice", ("first", "newest")),
              "atr1": ("float", 0.0, 20.0)}
    SCREEN_TFS = ("1", "5", "15", "30")
    SCREEN_RUN = {"strict_limit": True}
    ONE_INSTANCE_PASSES = NY                         # the session passes this ONE instance stands for (the taught lane reads it)
    FEATURES = ()

    def fam_sessions(self):
        return {"t": (OPEN, END_S)}

    def fam_filter(self, ids):
        return ["t"] if "nyam" in ids else []        # the one live pass; mid / pm run nothing

    def fam_day(self, ctx):
        self.dir, self.used, self.gap = None, False, None

    def fam_update(self, ctx):
        self.gap = None
        step = self.tf * 60
        now = (self.M[-1][0] // step + 1) * step     # the clock close of this tf bar
        if self.dir is None and now >= DIR_END:
            o, c = self.mo(OPEN), self.mc(OPEN, DIR_END)
            self.dir = 0 if o is None or c is None else (c > o) - (c < o)
        if now >= LAST:
            if self.orders and ctx.flat:
                self._cancel(ctx)                    # an unfilled order dies at 15:00
            return
        if self.sid is None or not self.dir or now <= DIR_END or len(self.H) < 3:
            return
        self._sync(ctx)
        newest = self.p["pick"] == "newest"
        if self.used and not (newest and ctx.flat and self.n_ent < self.p["max_tr"]):
            return
        h1, l1, h3, l3 = self.H[-3], self.L[-3], self.H[-1], self.L[-1]
        up = self.dir > 0
        near, far = (l3, h1) if up else (h3, l1)
        if (near - far) * self.dir <= 0 or abs(near - far) < max(self.p["min_gap"] * self.atr, ctx.tick):
            return
        if newest and self.orders:
            self._cancel(ctx)                        # the most recent gap takes over the resting order
        self.used = True
        px = {"touch": near, "mid": (near + far) / 2.0, "go": self.C[-1]}[self.p["mode"]]
        struct = self.L[-2] if up else self.H[-2]   # the middle candle's far end
        if self.p["atr1"] > 0:
            a1 = self.atr1m()
            struct = None if a1 is None else px - self.dir * self.p["atr1"] * a1
        if struct is None:
            return
        if (px - struct) * self.dir > 0:
            self.gap = ("long" if up else "short", px, struct)

    def atr1m(self):
        """The mean true range of the 14 newest completed 1-minute bars (15 needed), or None."""
        m = self.M[-15:]
        if len(m) < 15:
            return None
        return sum(max(b[2], a[4]) - min(b[3], a[4]) for a, b in zip(m, m[1:])) / 14.0

    def _dist(self, ctx, ref, struct):
        if self.p["atr1"] > 0 and struct is not None:
            return max(abs(ref - struct), 2 * ctx.tick)          # the owner's ATR stop: no tf-ATR floor
        return super()._dist(ctx, ref, struct)

    def fam_signal(self, ctx):
        if self.gap is None:
            return
        side, px, struct = self.gap
        if self.p["mode"] == "go":
            self._mkt(ctx, side, struct=struct)
        else:
            self._lim(ctx, side, px, struct=struct)


ENTRY_WINDOWS = {"fvg_odir": (DIR_END, LAST + 59)}

FAMILIES = {
    "fvg_odir": (FvgOdir, {}, False,
                 "fvg_odir: the 09:30-10:00 move sets the day's side; the first fair value gap on that side completed between 10:00 and "
                 "15:00 -> a limit at its near edge (touch; mid / go), stop at the middle candle's far end (stop_mode struct), one trade a "
                 "day, an unfilled order cancelled at 15:00; ONE instance 09:30-15:58; flat 15:58",
                 {"rationale": "The opening half hour shows which side took control of the day, and the first gap on that side is the "
                               "footprint of orders that wanted in and were left unfilled, so the return to it meets that interest while "
                               "the traders fading the day's direction pay.",
                  "complexity": 6,
                  "variants": [{"min_gap": 0.0}, {"min_gap": 0.1}, {"min_gap": 0.25}]}),
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
