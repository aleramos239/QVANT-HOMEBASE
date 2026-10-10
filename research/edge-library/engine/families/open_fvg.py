"""open_fvg -- THE FAIR VALUE GAP THROUGH THE OPENING CANDLE as an entry trigger (the owner's request of 2026-10-10), written from its rule
before any result. No Level-2 feature is read (FEATURES = ()): NQ, ES and GC, 1 contract, hold_to = 'day' (flat 15:58 ET). `fvg` buys the
return to any gap of the session; this one takes only the first gap whose push breaks the high or low of the day's opening candle.

    open_fvg   bar-based 1/5/15   the New York day sessions nyam, mid, pm; settings oc_min, min_gap (+ the Template's max_tr, dir)

THE RULE (fixed here, before any run):
  * OPENING CANDLE. The high and the low of the first `oc_min` minutes from 09:30 ET (5 | 15 | 30, default 5), made of the 1-minute bars that
    began in 09:30 .. 09:30 + oc_min (Template.M). They are the day's two levels, read once the candle has ended (at the first tf close at or
    after its end) and kept all day: every session of the day reads the same two. A candle without a print gives no level and no trade.
  * THE GAP is fvg's (families/fvg.py), unchanged. Three tf bars in a row, bar 1 the oldest. An UP gap: bar 3's low is above bar 1's high; its
    NEAR edge is bar 3's low (the side price comes back to first), its FAR edge bar 1's high. A DOWN gap is the mirror: bar 3's high below bar
    1's low; near edge = bar 3's high, far edge = bar 1's low. Read at bar 3's close, on completed bars only. All three bars closed inside the
    idea's session (the third close of a session is the first that can show a gap). Far edge to near edge is at least min_gap x ATR14 of the
    tf at bar 3's close (the Template's ATR, the one fvg reads), and never less than one tick.
  * THROUGH THE LEVEL. The gap COUNTS when its middle bar (bar 2, the push) broke the level, and bar 2 closed after the opening candle has
    ended. An UP gap counts when bar 2 traded at or below the opening candle's high and CLOSED above it (low2 <= high_oc < close2). A DOWN
    gap counts when bar 2 traded at or above the opening candle's low and closed below it (high2 >= low_oc > close2). A close exactly on the
    level is not through it. A gap whose middle bar does not cross the level is nothing, wherever the gap lies.
  * FIRST ONE ONLY. The first gap of the session that counts, on either side, is the day's signal of the idea; with max_tr 1 (the default)
    every later gap is ignored, whether or not the order of the first one could be placed (the side is switched off by dir, a filter says
    no, bar 3 closed on its own edge, the last 5 minutes of the session) and whether or not it ever fills. max_tr can be 1 .. 3: it is the
    number of signals a session. With more than 1, a later counting gap is the next signal once the earlier order is gone and its trade, if
    it filled, is closed; a counting gap that forms while that order still rests or that trade is still open is not a signal and is not
    counted.
  * THE ORDER. At bar 3's close a LIMIT rests at the gap's near edge, WITH the gap (up gap: a buy at bar 3's low; down gap: a sell at bar 3's
    high), as fvg's `touch` mode. A limit fills on a one-tick trade-through, at its price (the engine's limit law), and the family runs with
    strict_limit: a fill print that is already through the stop is a loss. The order stays until (a) it fills, (b) a tf bar of the session
    CLOSES beyond the gap's far edge (strictly below bar 1's high for an up gap, strictly above bar 1's low for a down gap: the gap failed)
    -- it is cancelled at that close -- or (c) the session's last 5 minutes begin (the Template's rule). A newer gap does not replace it.
  * STRUCTURE LEVEL, passed with the order: bar 1's far extreme (up gap: bar 1's LOW; down gap: bar 1's HIGH), the stop these traders use.
    fvg passes the gap's far edge instead (bar 1's high for an up gap): here the stop lies the whole of bar 1 further away.
  * ENTRIES. Inside the idea's session only (a tf close in (start, end], never in the last 5 minutes of it: the Template's rule), one
    position at a time. State is per session: a new session starts with no gap, no order and no signal used; the two levels are the day's.
  * EXITS. None of its own: the standard table's stop / target cells and the flat time 15:58 ET, as every family gets them.
  * SIDES. `dir` is the Template's: both (default), long or short. It decides which orders may be placed, not which gap is the first: with
    dir long a session whose first counting gap is a down gap has no trade (max_tr 1). So with max_tr 1 the trades of dir long and the
    trades of dir short are together exactly the trades of dir both. Not a mirror axis: the variants are the candle's length.

WHAT FOLLOWS FROM IT:
  * Bar 2 closed after the candle ended, and all three bars closed inside the session, so bar 2 and bar 3 always lie after the opening
    candle; only bar 1 can be a part of it. A bar 2 that closed by the candle's end is a piece of the candle and cannot close beyond its
    high or low, so no clock test is needed once the candle is read at its end. The first close that can show a counting gap, in nyam:
        bars 1    bar 1 = the candle's last minute, bar 2 = the first minute after it             09:37 (oc 5), 09:47 (15), 10:02 (30)
        bars 5    oc 5: bar 1 = THE OPENING CANDLE ITSELF (09:30-09:35), bar 2 = 09:35-09:40, bar 3 = 09:40-09:45       09:45
                  oc 15 / 30: bar 1 = the candle's last 5 minutes                                                       09:55 / 10:10
        bars 15   oc 5 / 15: bar 1 = 09:30-09:45 (it holds the 5-minute candle; it is the 15-minute one), bar 2 = 09:45-10:00   10:15
                  oc 30: bar 1 = 09:45-10:00 (the candle's second half), bar 2 = 10:00-10:15                            10:30
    When bar 1 is the opening candle itself the up gap's far edge is the candle's high and the structure level is the candle's low: the
    stop sits on the other side of the opening candle. In mid and pm the levels are hours old and any three bars of the session can be the
    gap (first read at session start + 3 bars).
  * The level is not used up by a cross without a gap, and the gap need not lie on the level: bar 2 must cross it, but the gap's zone (bar
    1's high .. bar 3's low) can be above the level, around it or below it.
  * The order rests at the near edge and the far edge lies beyond it, so price cannot close beyond the far edge without trading through the
    order first: a resting order is filled before its gap can fail. Cancel (b) acts only when price crosses the whole gap inside the order
    delay (the 85 ms after bar 3's close, in which no print can fill the order) and the bar then closes beyond the far edge; without it the
    order would "fill" at the near edge with the market already through the gap. So in practice an order that is not filled rests to the
    session's last 5 minutes, and with max_tr above 1 the next signal comes only after a trade has closed or after a signal that could
    place no order.
  * With max_tr 1 a session gives at most one order and it may never fill. The limit rests on the passive side of the last print only: a
    bar 3 that closes exactly on its own low (up gap) leaves no room for it, and the signal is used all the same.
  * The stop of stop_mode 'struct' is bar 1's far extreme: the gap's height plus bar 1's height away from the entry (the Template floors it
    at 0.25 ATR and two ticks, as for every family).

NO LOOK-AHEAD, where it could hide: (1) the opening candle is read only at a tf close at or after its end, from 1-minute bars that had
closed (the clock of a decision is the clock close of the tf bar, taken from the last 1-minute bar the Template has added: a tf bar whose
last minutes had no print is closed late by the Template, with the next minute's bar not yet added); (2) the gap, its edges, bar 2's cross
and the ATR are read at bar 3's close from the three newest closed bars; (3) the order is placed after that close and the cancel reads the
close of a bar that has just closed.

REGISTRATION. As families/noise.py: families/__init__.py picks this module up by itself (FAMILIES below), and join_blocks() puts the family
into families/blocks.py's BASES / WRAPPED when this module is imported (blocks always imports first: the package loads its modules in name
order) -- blocks.py, one of the files whose hash every store and lock remembers, stays byte for byte as it was.

COMPLEXITY 9 = the opening candle + the gap + inside the session + bar 2 through the level + the first one only + a limit at the near edge +
cancelled at a close beyond the far edge + min_gap + oc_min. Tests: engine/tests/test_open_fvg.py."""
from __future__ import annotations

from l2sim import Template

OPEN = 34200                                       # 09:30 ET, seconds after 00:00
CANDLES = ("5", "15", "30")                        # minutes of the opening candle
NY = ("nyam", "mid", "pm")


class OpenFvg(Template):
    """open_fvg (module docstring). State per day: end = the second the opening candle ends, och / ocl = its high / low (None until it is
    read, or without a print). State per session: used = the signals so far; edge = (+1 / -1, far edge) of the gap of the latest signal,
    for the cancel. Set at every tf close: raw = the gap this close shows, fvg's (side, near edge, far edge), or None; gap = the SIGNAL
    of this close (side, near edge, far edge, structure level) or None."""
    DEFAULTS = {"oc_min": "5", "min_gap": 0.1, "max_tr": 1}
    SCHEMA = {"oc_min": ("choice", CANDLES), "min_gap": ("float", 0.0, 10.0), "max_tr": ("int", 1, 3)}
    SCREEN_TFS = ("1", "5", "15")
    SCREEN_RUN = {"strict_limit": True}
    FEATURES = ()

    def fam_filter(self, ids):
        return [s for s in ids if s in NY]

    def fam_day(self, ctx):
        self.end = OPEN + int(self.p["oc_min"]) * 60
        self.och = self.ocl = None

    def fam_session(self, ctx, s):
        self.used, self.edge = 0, None

    def fam_update(self, ctx):
        self.raw = self.gap = None
        step = self.tf * 60
        if self.och is None and (self.M[-1][0] // step + 1) * step >= self.end:    # the clock close of this tf bar: the candle has ended
            r = self.rng(OPEN, self.end)
            if r:
                self.och, self.ocl = r
        if self.sid is None:
            return
        self._sync(ctx)
        if self.orders and (self.C[-1] - self.edge[1]) * self.edge[0] < 0:
            self._cancel(ctx)                                        # a close beyond the far edge: the gap failed
        if self.sn < 3:                                              # (sn counts the closes inside the session: every close from its third on is one)
            return
        h1, l1, h3, l3 = self.H[-3], self.L[-3], self.H[-1], self.L[-1]          # the gap of the three newest bars: fvg's lines
        g = ("long", l3, h1) if l3 > h1 else ("short", h3, l1) if h3 < l1 else None
        if g is None or abs(g[1] - g[2]) < max(self.p["min_gap"] * self.atr, ctx.tick):
            return
        self.raw = g
        if self.och is None:
            return
        up = g[0] == "long"
        if not (self.L[-2] <= self.och < self.C[-2] if up else self.H[-2] >= self.ocl > self.C[-2]):
            return                                                   # the middle bar did not break the level
        if self.used >= self.p["max_tr"] or self.orders or not ctx.flat:
            return                                                   # no signal is left, or the earlier order / trade is still there
        self.used += 1
        self.edge = (1 if up else -1, g[2])
        self.gap = (*g, l1 if up else h1)

    def fam_signal(self, ctx):
        if self.gap is not None:
            side, near, _, struct = self.gap
            self._lim(ctx, side, near, struct=struct)


FAMILIES = {
    "open_fvg": (OpenFvg, {}, False,
                 "open_fvg: the first fair value gap of the session (fvg's three bars, at least min_gap x ATR high) whose middle bar breaks "
                 "the high or low of the day's opening candle (the first oc_min minutes from 09:30 ET) -> a limit at the gap's near edge, "
                 "with the break (above the high = buy, below the low = sell); the middle bar trades at the level and closes beyond it; the "
                 "order rests until it fills, a bar closes beyond the gap's far edge or the session's last 5 minutes; the structure level "
                 "is bar 1's far extreme; max_tr signals a session (default 1), one position at a time; nyam / mid / pm; flat 15:58",
                 {"rationale": "A push through the opening candle that leaves a gap shows one side taking control of the open, so the first "
                               "return to that gap meets the orders the push left unfilled, and the losers are the traders on the other "
                               "side of the opening candle who are stopped as it breaks.",
                  "complexity": 9,
                  "variants": [{"oc_min": "5"}, {"oc_min": "15"}, {"oc_min": "30"}]}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (module docstring, REGISTRATION): the wrapped class a card runs, importable by
    name from there (workers import it through the package, which loads this module). Idempotent; a reload of blocks and then of this module
    does it again."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
