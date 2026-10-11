"""vwap_touch -- THE FIRST RETURN TO VWAP, bought / sold with a resting limit order AT the VWAP (Robert Rother, IQCapital, video
XWJlBBikUc0, owner's request of 2026-10-11), written from its rule before any result. No Level-2 feature is read (FEATURES = ()): NQ, ES
and GC, 1 contract, hold_to = 'day' (flat 15:58 ET). Rother's rule as he says it: "the market moves away from VWAP, coming back to VWAP,
then we can see a reaction"; a limit order AT the VWAP, moved as the VWAP moves; only the FIRST touch is an A+ trade; if price comes
within 2-3 ticks and bounces he pulls the order; stop 10 ticks, target 10-15 ticks (the exits are the sheet's, not the family's).

    vwap_touch   bar-based 1/5/15/30   every session that ends after the anchor; settings anchor, away, near, max_tr (+ the Template's dir)

THE RULE (fixed here, before any run):
  * VWAP. Volume-weighted (h + l + c) / 3 of the 1-minute bars (the engine's VWAP rule, as noise_band), summed from the ANCHOR:
        us      09:30 ET  (his "US session VWAP", regular trading hours)
        london  03:00 ET  (08:00 London: his "London VWAP"; he gives no clock time)
        day     00:00 ET  (his "day VWAP" starts 18:00 ET, the electronic open. A morning instance of the engine reads the trade date's
                bars from 00:00 ET and not the evening before, so this is the Globex-day VWAP WITHOUT its first six evening hours: said
                on the rule sheet as a difference.)
    The VWAP is the one of the minutes that have ended; a bar's own minute enters it when that minute has ended.
  * AWAY. A 1-minute close at least `away` ticks above the VWAP (the VWAP as of that minute's end) arms a LONG ("price came down to
    VWAP from above: the bounce is up"); a close at least `away` ticks below arms a SHORT. The arm is the side price came FROM, which is
    the same rule in a trend (a pullback to VWAP, with the trend) and in a range (fade it).
  * TOUCH. A 1-minute bar USES THE ARM UP when its range comes within `near` ticks of the VWAP as it stood when that minute began
    (low <= VWAP + near ticks and high >= VWAP - near ticks), whether or not an order was there and whether or not it filled. Rother:
    "if price is within two or three ticks of my order and the market already pulls back, I take the order out: the second or third
    touch is not A+". A used arm trades nothing until a NEW close `away` ticks away arms it again.
  * THE ORDER. At a tf close inside the idea's session, while flat with entries left, with an arm set: a limit order at the VWAP, long
    (arm above) or short (arm below); any order still working is replaced at the new VWAP at that close (he moves the order by hand).
    Placed only when the last print is on the passive side of the VWAP (the Template's limit rule). A limit fills on a ONE-TICK
    trade-through, at its price: a touch to the tick is no fill, the engine's law; the family runs with strict_limit (SCREEN_RUN).
  * ONE POSITION at a time, up to `max_tr` entries a session. A working order dies at the close of the minute that used its arm up.
  * EXITS. None of its own: the sheet's stop and target (the taught lane) or the standard table's cells, and the flat time 15:58 ET.
  * NOT in the rule: which VWAP is "most respected" (each anchor is its own idea), sideways-versus-trend days (no filter), the order-book
    check (Bookmap), the "bad feeling" early exit.

NO LOOK-AHEAD: the VWAP, the arm and the touch are read from 1-minute bars that have ended; an order is placed at a tf close, before the
bar that fills it; the touch is tested against the VWAP BEFORE the touching minute, so the minute cannot move the line it is tested on.

HOW IT SITS IN THE TEMPLATE. As families/ib_touch.py: the bars are read in on_bar (every minute) and in fam_update (at a tf close, before
the Template asks for the order); can_enter does not count the family's own resting order as a reason to stay out (the order must be
re-priced); registration through join_blocks() (blocks.py is not edited).

COMPLEXITY 5 = the VWAP + the arm (away) + the touch that uses it up (near) + a limit AT the line, re-priced + anchor.
Tests: engine/tests/test_vwap_touch.py."""
from __future__ import annotations

from l2sim import Template

ANCHOR_S = {"day": 0, "london": 10800, "us": 34200}     # 00:00 / 03:00 / 09:30 ET, seconds after 00:00 ET of the trade date
TFS = ("1", "5", "15", "30")


class VwapTouch(Template):
    """vwap_touch (module docstring). State per day: vv / vp (VWAP sums from the anchor), mi (the 1-minute bars read), arm (+1 long: price
    came from above; -1 short; 0 none)."""
    DEFAULTS = {"anchor": "day", "away": 24, "near": 3, "max_tr": 5}   # the broadest anchor: the taught lane asks which sessions the defaults trade
    SCHEMA = {"anchor": ("choice", tuple(ANCHOR_S)), "away": ("int", 2, 400), "near": ("int", 0, 20), "max_tr": ("int", 1, 20)}
    SCREEN_TFS = TFS
    SCREEN_RUN = {"strict_limit": True}
    FEATURES = ()

    def fam_filter(self, ids):
        """Only the sessions that end after the anchor: the line does not exist before it (the evening never runs)."""
        a = ANCHOR_S[self.p["anchor"]]
        return [s for s in ids if self.S[s][1] > a and self.S[s][0] >= 0]

    def fam_day(self, ctx):
        self.vv = self.vp = 0.0
        self.mi = 0
        self.arm = 0

    def vwap(self):
        return self.vp / self.vv if self.vv > 0 else None

    def _read(self, ctx):
        """Read the 1-minute bars that have ended since the last call: the touch (against the VWAP before the minute), then the minute
        enters the VWAP, then the arm (against the VWAP after it)."""
        M = self.M
        a = ANCHOR_S[self.p["anchor"]]
        tk = ctx._s.tick
        away, near = self.p["away"] * tk, self.p["near"] * tk
        touched = False
        for i in range(self.mi, len(M)):
            s, _, h, l, c, v = M[i]
            if s < a:
                continue
            w0 = self.vwap()
            if w0 is not None and l <= w0 + near and h >= w0 - near:
                self.arm = 0                         # the first touch is used up (filled or not)
                touched = True
            if v > 0:
                self.vv += v
                self.vp += v * (h + l + c) / 3.0
            w1 = self.vwap()
            if w1 is not None:
                if c >= w1 + away:
                    self.arm = 1
                elif c <= w1 - away:
                    self.arm = -1
        self.mi = len(M)
        if touched:
            for r in self.orders:
                ctx.cancel(r[0])                     # an order that is not working any more is left alone by the engine

    def on_bar(self, ctx, bar):
        super().on_bar(ctx, bar)
        self._read(ctx)                              # every 1-minute close, not only the tf closes

    def fam_update(self, ctx):
        self._read(ctx)                              # at a tf close: before the Template asks for the order

    def can_enter(self, ctx):
        """The Template's rule, but this family's own resting order does not stand in the way of its re-pricing."""
        self._sync(ctx)
        rest, self.orders = self.orders, []
        ok = super().can_enter(ctx)
        self.orders = rest
        return ok

    def fam_signal(self, ctx):
        w = self.vwap()
        keep = [r for r in self.orders if r[0].status != "working"]
        for r in self.orders:
            if r[0].status == "working":
                ctx.cancel(r[0])                     # re-priced at this close (or dropped when the arm is gone)
        self.orders = keep
        if w is None or not self.arm:
            return
        self._lim(ctx, "long" if self.arm > 0 else "short", w)


FAMILIES = {
    "vwap_touch": (VwapTouch, {}, False,
                   "vwap_touch: price closes at least `away` ticks from the VWAP (anchor us 09:30 / london 03:00 / day 00:00 ET) -> a limit "
                   "order AT the VWAP, re-priced at every tf close, to fade back toward the side price came from; the arm is used up by the "
                   "first 1-minute bar that comes within `near` ticks of the VWAP, filled or not; one position at a time, up to max_tr a "
                   "session; the sheet's own stop and target; flat 15:58 (Rother, IQCapital, XWJlBBikUc0)",
                   {"rationale": "The first return to VWAP meets the resting orders of the execution algorithms that benchmark to it, so the "
                                 "first test is the one most likely to hold; the losers are those who chase the move away from it.",
                    "complexity": 5,
                    "variants": [{"anchor": "day"}, {"anchor": "london"}, {"anchor": "us"}]}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (as ib_touch / noise): the wrapped class a card runs, importable by name
    from there. Idempotent."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
