"""ib_touch -- THE FIRST TOUCH OF THE MORNING RANGE, faded with a resting limit order (the owner's request of 2026-10-10), written from its rule
before any result. No Level-2 feature is read (FEATURES = ()): NQ, ES and GC, 1 contract, hold_to = 'day' (flat 15:58 ET). `ib_n` in mode fade
waits for a tf close beyond the range and a close back inside, and then trades at market; this one has its orders AT the edges before price
gets there and trades the first return to an edge, at the edge.

    ib_touch   bar-based 1/5/15/30   the New York day sessions (nyam, mid, pm); settings ib_min, max_tr (+ the Template's dir)

THE RULE (fixed here, before any run):
  * RANGE. ib_n's (families/blocks.py IbN; restated here because that file is not edited, and the tests hold the two equal): the high and the
    low of the 1-minute bars inside the first `ib_min` minutes from 09:30 ET (5 | 15 | 30 | 60, default 60). It is read once the last minute
    of it has ended. A day without a print in those minutes has no range and no trade. New York day sessions only (nyam, mid, pm), as ib_n:
    an instance of any other session never trades.
  * THE ORDERS. A limit SELL at the range high and a limit BUY at the range low, at the edge itself (no offset). They are placed at a tf close
    inside the idea's session (a close in (start, end], never in the last 5 minutes of it: the Template's rule), from the first such close at
    or after the range's end, while the instance is flat and has entries left: every edge that is not used up and has no working order gets
    its order at that close. An order is placed only when the last print is on the inside of its edge (the Template's limit rule: strictly
    below the high for the sell, strictly above the low for the buy) and its side is allowed (dir, a filter block); an edge that could not
    get its order is asked again at the next tf close. An order rests until it fills, its edge is used up, or the session's entries end (5
    minutes before the session's end).
  * TWO ORDERS AT ONCE. The engine holds a limit on each side at once, so the rule is run as written (nothing is approximated by one moving
    order): the two are one OCO pair, as the brackets of orb / ib_n, and the fill of one cancels the other on that print.
  * FIRST TOUCH ONLY. An edge is USED UP by the first 1-minute bar that starts at or after the range's end and trades AT OR BEYOND it (a high
    at or above the range high; a low at or below the range low), read when that minute has ended -- whether or not an order was there to
    fill: before the idea's session began, while a trade was open, after max_tr was reached, in the last 5 minutes, with the side switched
    off by dir, or with the order there and only touched (a limit fills on a one-tick trade-through, the engine's limit law: a touch to the
    tick is no fill). A used edge never gets an order again that day, and an order still working at a used edge is cancelled at that
    minute's close: the order lives through the minute of the first touch and no longer.
  * ONE POSITION at a time. While a trade is open no entry order works (the other order went on the fill); if price reaches the other edge
    meanwhile, that edge is used up too. After the trade has ended the other edge, when it is still unused, gets its order back at the next
    tf close (max_tr 2).
  * A BAR THAT REACHES BOTH EDGES. The tape decides: the edge reached first is traded, its fill cancels the other order, and the other edge
    is used up by the same bar. One trade, both edges gone.
  * EXITS. None of its own: the standard table's stop / target cells and the flat time 15:58 ET, as every family gets them. No structure level
    is passed with the order (the trader uses a small fixed stop): stop_mode struct falls back to the ATR stop, and the range stop (rng)
    is refused, as for every family without an entry in blocks.HEIGHTS. The family runs with strict_limit (SCREEN_RUN, as fvg): a fill print
    that is already through the stop is a loss, not a hold -- a limit entry with a small stop needs that.
  * SETTINGS. ib_min 5 | 15 | 30 | 60 (default 60); max_tr 1 | 2 a session (default 2 = one per edge; with 1 the first edge traded is the
    only trade); dir is the Template's: both (default), long = the buy at the low only, short = the sell at the high only. Not a mirror
    axis: the variants are the range length (15 / 30 / 60).
  * WHAT FOLLOWS FROM IT.
      - The orders of a nyam idea rest from the range's end to 10:55 (the session ends 11:00 and its entries end 5 minutes before): with
        ib_min 60 that is 10:30-10:55, 25 minutes; with 30 it is 10:00-10:55, with 15 09:45-10:55, with 5 09:35-10:55.
      - A mid idea (11:00-13:30) gets its first orders at the first tf close after 11:00 (11:01 on 1-minute bars, 11:05 on 5, 11:15, 11:30),
        a pm idea (13:30-15:58) at 13:31 / 13:35 / 13:45 / 14:00 -- and only at an edge price has not been back to since the range ended.
      - The bar size decides only WHEN orders are placed (and the ATR and the filters, as everywhere): the touch is read on 1-minute bars
        at every bar size. With 30-minute bars and ib_min 15 the range ends 09:45 and the first orders go in at 10:00; an edge reached in
        between is used up before it ever had an order. On 1-minute bars the orders go in at the range's end itself.
      - A range that ends on its own high (low) has the last print on that edge: no sell (buy) is placed at the range's end; it is placed
        at the next tf close if the edge is still unused then.
      - At most one trade an edge a day, so at most two trades a day, also over several sessions (hold_to session, sess all).

NO LOOK-AHEAD, where it could hide: (1) the range is read only when its last minute has ended, by the clock of the 1-minute bars themselves
(a tf bar that the Template closes late, after a hole in the tape, does not make the range early: the minute that is not added yet is not
read. ib_n in mode fade takes the wall clock there, so on such a day -- one is built in the tests, none is among the real days read there
-- its range can miss its last minute; on every other day the two ranges are the same); (2) a touch is read from 1-minute bars that have
ended; (3) an order is placed at a tf close, before the bar that fills it: the fill is the engine's, on a later print, after the 85 ms
placement latency; (4) a cancel acts from the minute close it is decided at.

HOW IT SITS IN THE TEMPLATE. Orders are placed in fam_signal, at a tf close, as in every family. Two things are the family's own: on_bar
reads every 1-minute bar after the Template has (the touch, and the cancel at a used edge, are by the minute at every bar size), and
can_enter does not count the family's own resting order as a reason to stay out (the Template's rule keeps a family with a working order
from placing another; here the other edge's order must be able to go in beside it). Nothing else of the Template is changed.

REGISTRATION. As families/noise.py: families/__init__.py picks this module up by itself (FAMILIES below), and join_blocks() puts the family
into families/blocks.py's BASES / WRAPPED when this module is imported (blocks always imports first: the package loads its modules in name
order) -- blocks.py, one of the files whose hash every store and lock remembers, stays byte for byte as it was.

COMPLEXITY 6 = the range + NY sessions only + a limit at each edge from the range's end + the first touch uses an edge up, with or without an
order + the two orders are one pair: one position + ib_min. Tests: engine/tests/test_ib_touch.py."""
from __future__ import annotations

from l2sim import Template

OPEN = 34200                                       # 09:30 ET, seconds after 00:00
IB_MINS = ("5", "15", "30", "60")                  # minutes of the range (ib_n's choices)
NY = ("nyam", "mid", "pm")
SIDE = {-1: "short", 1: "long"}                    # the side of the order that trades an edge: -1 = the high (sold), 1 = the low (bought)


class IbTouch(Template):
    """ib_touch (module docstring). State per day: end = the range's end (seconds after 00:00 ET), hi / lo = the range (None until it has
    ended), mi = the 1-minute bars already read for a touch, used = {-1: the high is used up, 1: the low is used up}."""
    DEFAULTS = {"ib_min": "60", "max_tr": 2}
    SCHEMA = {"ib_min": ("choice", IB_MINS), "max_tr": ("int", 1, 2)}
    SCREEN_TFS = ("1", "5", "15", "30")
    SCREEN_RUN = {"strict_limit": True}
    FEATURES = ()

    def fam_filter(self, ids):
        return [s for s in ids if s in NY]

    def fam_day(self, ctx):
        self.end = OPEN + int(self.p["ib_min"]) * 60
        self.hi = self.lo = None
        self.mi = 0
        self.used = {-1: False, 1: False}

    def _touch(self, ctx):
        """Read the 1-minute bars that have ended since the last call: the range once its last minute is in (ib_n's lines: rng(OPEN, end)),
        then every minute from the range's end on for a touch; an order still working at a used edge is cancelled."""
        M = self.M
        if self.hi is None:
            if M[-1][0] + 60 < self.end:                # the last minute bar added ends before the range does
                return
            r = self.rng(OPEN, self.end)
            if r is None:
                return
            self.hi, self.lo = r
        for i in range(self.mi, len(M)):
            s, _, h, l, _, _ = M[i]
            if s >= self.end:
                if h >= self.hi:
                    self.used[-1] = True
                if l <= self.lo:
                    self.used[1] = True
        self.mi = len(M)
        for r in self.orders:
            if self.used[r[0].side]:
                ctx.cancel(r[0])                        # (nothing happens to an order that is not working any more)

    def on_bar(self, ctx, bar):
        super().on_bar(ctx, bar)
        self._touch(ctx)                                # every 1-minute close, not only the tf closes (and the minute a late tf close could not see)

    def fam_update(self, ctx):
        self._touch(ctx)                                # at a tf close: before the Template asks for the orders

    def can_enter(self, ctx):
        """The Template's rule, but this family's own resting order does not stand in the way of the other edge's order."""
        self._sync(ctx)
        rest, self.orders = self.orders, []
        ok = super().can_enter(ctx)
        self.orders = rest
        return ok

    def fam_signal(self, ctx):
        if self.hi is None:
            return
        work = {r[0].side: r[0] for r in self.orders if r[0].status == "working"}
        for sd, px in ((-1, self.hi), (1, self.lo)):
            if not self.used[sd] and sd not in work:
                o = self._lim(ctx, SIDE[sd], px)
                if o is not None:
                    work[sd] = o
        if len(work) == 2:
            ctx.oco(work[-1], work[1])                  # one pair: the fill of one cancels the other on that print


FAMILIES = {
    "ib_touch": (IbTouch, {}, True,
                 "ib_touch: the high and low of the first ib_min minutes from 09:30 (5 / 15 / 30 / 60), NY sessions only; from the range's end "
                 "a limit sell rests at the range high and a limit buy at the range low (one OCO pair, placed at a tf close inside the idea's "
                 "session) -> the FIRST return to an edge is faded at the edge; an edge is used up by the first 1-minute bar that trades at or "
                 "beyond it after the range's end, with or without an order there, and never trades again that day; up to max_tr a session "
                 "(2 = one an edge), one position at a time; flat 15:58",
                 {"rationale": "The first return to the edge of the morning range meets the resting orders of everyone who watched that level "
                               "form, so the first test is the one most likely to hold; the losers are the breakout traders who hit the "
                               "edge first.",
                  "complexity": 6,
                  "variants": [{"ib_min": "15"}, {"ib_min": "30"}, {"ib_min": "60"}]}),
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
