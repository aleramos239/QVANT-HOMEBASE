"""ddiv -- DELTA DIVERGENCE as an entry trigger (the owner's request of 2026-10-11): the chart's `ddiv` study (homebase/charts/studies_flow.py),
traded at the close that confirms it. Written from that study's rule before any result. NQ, ES and GC, 1 contract, bar-based 1 / 5 / 15.

    ddiv   bar-based 1/5/15   all seven sessions; setting n = bars each side (+ the Template's max_tr, dir)

THE RULE (the chart study's, fixed here before any run):
  * SESSION. The Globex session: 18:00 ET of the evening before the trade date. Its cumulative delta (buy volume minus sell volume of the
    aggressors, the desk's own tick archive, engine/flowtab.py -- the same flow file the delta filter blocks read) is the sum of the whole
    minutes since 18:00; a tf bar's value is the sum up to its CLOSE.
  * SWING. A tf bar of the instance is a swing HIGH when its high is strictly above the highs of the `n` bars before it and of the `n` bars
    after it; a swing LOW is the mirror with the lows. It is KNOWN only when the n-th bar after it has closed.
  * DIVERGENCE. At that close, with the previous swing high of the instance (price, cumulative delta at its bar):
        a higher swing high on a LOWER cumulative delta  = bearish  -> SHORT
        a lower swing low on a HIGHER cumulative delta   = bullish  -> LONG
    Every swing replaces the previous one of its kind, signal or not. A swing without a previous one of its kind gives no signal.
  * BOTH at one close (the swing bar was a swing high and a swing low) = no trade.
  * ORDER. A market order placed at that close: it fills at the next bar's open (the first print after the 85 ms placement latency).
    The arrow of the chart is drawn on the swing bar, n bars earlier: it can only be traded here, at the confirming close.
  * ENTRIES. Inside the idea's session only (a tf close in (start, end], never in the last 5 minutes of it: the Template's rule), up to
    `max_tr` a session, one position at a time. EXITS: none of its own; the sheet's stop and target and the flat time 15:58 ET.

WHERE IT DIFFERS FROM THE CHART, said out loud: an instance of a day session (asia, london, pre, nyam, mid, pm) holds the day's 1-minute
bars from 00:00 ET only, so its swing memory starts at 00:00 (the chart's starts at 18:00); the evening instance starts at 18:00 as the chart
does. The cumulative delta always counts from 18:00, as the chart's does. A swing whose cumulative delta has no flow row is skipped (no
signal, the previous swing is kept).

NO LOOK-AHEAD, where it could hide: (1) a swing needs the n bars AFTER it, so it is used only from the n-th bar's close on; (2) the
cumulative delta of a bar reads the whole minutes before that bar's close, nothing later (flowtab's law: a minute is complete at +60 s);
(3) the clock of a decision is the tf bar's clock close, taken from the last 1-minute bar the Template has added.

REGISTRATION. As families/sfp.py: families/__init__.py picks this module up by itself (FAMILIES below) and join_blocks() puts the family
into families/blocks.py's BASES / WRAPPED when this module is imported; blocks.py stays byte for byte as it was.

COMPLEXITY 6 = the n-bar swing, known n bars late + the cumulative delta at it + a higher high on a lower delta (mirror) + once a swing
+ both at once = no trade + n. Tests: engine/tests/test_ddiv.py."""
from __future__ import annotations

import flowtab
from l2sim import Template

GLOBEX_START = -6 * 3600                           # 18:00 ET of the evening before, seconds after 00:00 ET of the trade date


class Ddiv(Template):
    """ddiv (module docstring). State per instance: cum = the cumulative delta at each tf bar's close (None: no flow row), ph / pl = the
    previous swing high / low as (price, cum) or None, go = +1 / -1 / 0: the signal of the tf bar that has just closed."""
    DEFAULTS = {"n": 5, "max_tr": 10}
    SCHEMA = {"n": ("int", 1, 50), "max_tr": ("int", 1, 20)}
    SCREEN_TFS = ("1", "5", "15")
    FEATURES = ()

    def fam_day(self, ctx):
        self.cum = []
        self.ph = self.pl = None
        self.go = 0

    def fam_update(self, ctx):
        self.go = 0
        step = self.tf * 60
        now = (self.M[-1][0] // step + 1) * step      # the clock close of the tf bar that has just closed, seconds after 00:00 ET
        w = flowtab.window(ctx.root, self.day, GLOBEX_START, now)
        self.cum.append(None if w is None else w[1])  # len(cum) == nb: one value for every tf bar of the instance
        n, nb = self.p["n"], self.nb
        if nb < 2 * n + 1:
            return
        k = nb - 1 - n                                # the swing candidate: n bars after it have closed
        c = self.cum[k]
        if c is None:
            return
        H, L = self.H, self.L
        hi = H[k] > max(H[k - n:k]) and H[k] > max(H[k + 1:])
        lo = L[k] < min(L[k - n:k]) and L[k] < min(L[k + 1:])
        bear = hi and self.ph is not None and H[k] > self.ph[0] and c < self.ph[1]
        bull = lo and self.pl is not None and L[k] < self.pl[0] and c > self.pl[1]
        if hi:
            self.ph = (H[k], c)                       # every swing replaces the previous one of its kind, signal or not
        if lo:
            self.pl = (L[k], c)
        if bear != bull:                              # both at one close = no trade
            self.go = -1 if bear else 1

    def fam_signal(self, ctx):
        if self.go:
            self._mkt(ctx, "long" if self.go > 0 else "short")


FAMILIES = {
    "ddiv": (Ddiv, {}, False,
             "ddiv: a swing high / low of the instance's own tf bars (n bars each side, known n bars later) against the session's cumulative "
             "delta (buy minus sell volume of the aggressors since 18:00 ET) at that bar: a higher swing high on a lower cumulative delta = "
             "SHORT, a lower swing low on a higher cumulative delta = LONG, market entry at the confirming close (the next bar's open); "
             "entries inside the idea's session, up to max_tr a session, one position at a time; flat 15:58",
             {"rationale": "A push to a new extreme that the aggressive orders did not carry is a push made by passive orders and thin "
                           "follow-through; the traders who bought the high are left holding it when the buying stops, and their exits "
                           "carry price back.",
              "complexity": 6,
              "variants": [{"n": 3}, {"n": 5}, {"n": 8}]}),
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
