"""ifvg -- THE INVERSION FAIR VALUE GAP as an entry trigger (the owner's request of 2026-10-09), written from its rule before any result. No
Level-2 feature is read (FEATURES = ()): NQ, ES and GC, 1 contract, hold_to = 'day' (flat 15:58 ET). Two videos describe it: the "IFVG" entry
(9O6JU5_xTd8) and the "failed gap squeeze" (3LrXQDS187Y), notes in research/edge-library/videos. `fvg` trades WITH a gap; this one trades the
close THROUGH a gap, against it.

    ifvg   bar-based 1/5/15/30   all seven sessions; settings min_gap, age (+ the Template's max_tr, dir)

THE RULE (fixed here, before any run):
  * THE GAP is fvg's (families/fvg.py), unchanged. Three tf bars in a row, bar 1 the oldest. An UP gap: bar 3's low is above bar 1's high; its
    zone is bar 1's high (the lower edge) .. bar 3's low. A DOWN gap is the mirror: bar 3's high below bar 1's low; its zone is bar 3's high ..
    bar 1's low (the upper edge). Read at bar 3's close, on completed bars only. All three bars closed inside the idea's session (the third
    close of a session is the first that can show a gap). The zone is at least min_gap x ATR14 of the tf at bar 3's close high (the Template's
    ATR, the one fvg reads), and never less than one tick.
  * OPEN. A gap is open for the `age` tf bars after bar 3 (bars that printed; the bar after bar 3 is bar 1, bar `age` is the last), and only in
    its own session: a new session and a new day start with no gap. Price trading into the gap, or a wick through it, does not close it:
    only an inversion or its age does.
  * INVERSION, read at a tf close inside the session and never later than it: the bar CLOSES through the whole gap, against it. A close
    strictly below the lower edge of an open UP gap = SHORT. A close strictly above the upper edge of an open DOWN gap = LONG. A close exactly
    on the edge is nothing. The idea: the traders who entered in the gap are all losing at that close and must get out.
  * ONCE. An inverted gap is used up at that close, whether or not an order could be placed (a trade is open, max_tr is reached, the last 5
    minutes of the session, the side is switched off by dir): it never signals again.
  * SEVERAL GAPS. One bar that inverts several gaps of the same side is ONE signal, and all of them are used up. A bar cannot invert an up gap
    and a down gap at once: when the later of the two formed, its bar 3 closed on the open side of the earlier one, so the up gap's lower edge
    is below the down gap's upper edge and no close is under the one and over the other. Were it ever to happen: no trade, both used up.
  * ORDER. A market order placed at that close: it fills at the next bar's open (the first print after the 85 ms placement latency). The gap,
    its edges and its age are made of bars that had closed: nothing later than the signal bar's close is read.
  * ENTRIES. Inside the idea's session only (a tf close in (start, end], never in the last 5 minutes of it: the Template's rule), up to `max_tr`
    a session (default 3), one position at a time.
  * EXITS. None of its own: the standard table's stop / target cells and the flat time 15:58 ET, as every family gets them.
  * SIDES. `dir` is the Template's: both (default), long or short; a one-sided card sets it through limits.dir. It is not a mirror axis here:
    the variants are min_gap.

REGISTRATION. As families/noise.py: families/__init__.py picks this module up by itself (FAMILIES below), and join_blocks() puts the family
into families/blocks.py's BASES / WRAPPED when this module is imported (blocks always imports first: the package loads its modules in name
order) -- blocks.py, one of the files whose hash every store and lock remembers, stays byte for byte as it was.

COMPLEXITY 7 = the gap + inside the session + open for `age` bars + a close through the whole gap -> market against it + once a gap + min_gap +
age. Tests: engine/tests/test_ifvg.py."""
from __future__ import annotations

from l2sim import Template

TFS = ("1", "5", "15", "30")


class Ifvg(Template):
    """ifvg (module docstring). State per session: gaps = the open gaps as (side, near edge, far edge, the bar count at bar 3's close), side
    'long' = an UP gap, as fvg writes it; a close beyond the FAR edge inverts it. go = +1 / -1 / 0: the signal of the tf bar that has just closed."""
    DEFAULTS = {"min_gap": 0.25, "age": 30, "max_tr": 3}
    SCHEMA = {"min_gap": ("float", 0.0, 10.0), "age": ("int", 5, 240), "max_tr": ("int", 1, 5)}
    SCREEN_TFS = TFS
    FEATURES = ()

    def fam_day(self, ctx):
        self.gaps, self.seen, self.go = [], 0, 0

    def fam_session(self, ctx, s):
        self.gaps, self.seen, self.go = [], 0, 0

    def fam_update(self, ctx):
        self.go = 0
        if self.sid is None or self.sn == self.seen:                 # (sn grows only at a close inside the session)
            return
        self.seen = self.sn
        c, n = self.C[-1], self.nb
        sides, still = set(), []
        for g in self.gaps:
            if n - g[3] > self.p["age"]:                             # older than `age` bars: gone
                continue
            if g[0] == "long" and c < g[2]:                          # a close under the whole UP gap
                sides.add(-1)
            elif g[0] == "short" and c > g[2]:                       # a close over the whole DOWN gap
                sides.add(1)
            else:
                still.append(g)
        self.gaps = still
        if len(sides) == 1:
            self.go = sides.pop()
        if self.sn < 3:
            return
        h1, l1, h3, l3 = self.H[-3], self.L[-3], self.H[-1], self.L[-1]          # the gap of the three newest bars: fvg's lines
        g = ("long", l3, h1) if l3 > h1 else ("short", h3, l1) if h3 < l1 else None
        if g is None or abs(g[1] - g[2]) < max(self.p["min_gap"] * self.atr, ctx.tick):
            return
        self.gaps.append((*g, n))

    def fam_signal(self, ctx):
        if self.go:
            self._mkt(ctx, "long" if self.go > 0 else "short")


FAMILIES = {
    "ifvg": (Ifvg, {}, False,
             "ifvg: a fair value gap of the session (fvg's three bars, at least min_gap x ATR high) stays open for `age` bars; a bar that closes "
             "through the whole gap against it inverts it -> market entry at the next bar's open: below an up gap = short, above a down gap = "
             "long. Each gap inverts once; entries inside the idea's session, up to max_tr a session, one position at a time; flat 15:58",
             {"rationale": "Traders who entered inside a fair value gap expected it to hold, so a close through the whole gap leaves all of "
                           "them losing at once and their forced exits push price further the same way, at the cost of whoever still fades "
                           "the move.",
              "complexity": 7,
              "variants": [{"min_gap": 0.1}, {"min_gap": 0.25}, {"min_gap": 0.5}]}),
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
