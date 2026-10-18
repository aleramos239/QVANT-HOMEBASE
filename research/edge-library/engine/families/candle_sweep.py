"""candle_sweep -- THE PREVIOUS CANDLE SWEPT AND CLOSED BACK as an entry trigger (the owner's idea of 2026-10-17), written from his words
before any result: "on the 15 minute timeframe we look at the previous candle; if we sweep its high or low, then close back inside within
it, we enter: sweep the previous candle's low, reverse and close higher within the body = long, vice versa short; stop at the candle
extreme, 1 : 0.5". No Level-2 feature is read (FEATURES = ()): NQ, ES and GC, 1 contract, hold_to = 'day' (flat 15:58 ET).

    candle_sweep   bar-based 1/5/15/30   all seven sessions; setting back (+ the Template's max_tr, dir)

THE RULE (fixed here, before any run):
  * BARS. The instance's own tf bars (the owner's bar is 15 minutes): the bar that has just closed (THIS bar) and the one before it (the
    PREVIOUS bar) of the same instance, from 00:00 ET of the trade date (an evening idea: from 18:00 of the evening before). The previous bar
    may lie before the session start: it is simply the bar before. A clock slot without a print makes no bar, so after a hole the previous bar
    is the last bar that traded.
  * SWEEP. THIS bar's low is strictly below the PREVIOUS bar's low (a long setup); its high strictly above the previous high (a short setup).
  * BACK. Read at THIS bar's close, strictly: `back` = where the close must come back to, for a long (the short is the mirror)
        range   above the previous bar's low (back inside its range)
        body    above the bottom of the previous bar's body, min(open, close) (the owner's words: "close higher within the body")
        far     above the top of the previous bar's body, max(open, close)
    A close past the far side of the body counts for `body` too: the owner's "within" is read as "back into it", not "and no further".
  * BOTH. A bar that swept both sides and qualifies both ways (it closed back inside both) is no trade.
  * ORDER. A market order placed at that close: it fills at the next bar's open (the first print after the 85 ms placement latency).
    Its structure level is THIS bar's extreme: its low for a long, its high for a short ("stop at the candle extreme"): stop_mode 'struct'
    takes it (the distance from the signal close to it, floored at 0.25 ATR like every structure stop, re-priced to the fill); the standard
    table's stops ignore it.
  * ENTRIES. Inside the idea's session only (a tf close in (start, end], never in the last 5 minutes of it: the Template's rule), up to
    `max_tr` a session (default 20: the owner gave no cap), one position at a time: a signal while a trade is open is not taken.
  * EXITS. None of its own: the stop / target cell and the flat time 15:58 ET.
  * SIDES. `dir` is the Template's: both (default), long or short; a one-sided card sets it through limits.dir.

NO LOOK-AHEAD, where it could hide: the test reads the two tf bars that have closed (O / H / L / C of each), nothing after them; the
decision's clock is the tf bar's close, taken from the last 1-minute bar the Template has added.

REGISTRATION. As families/sfp.py: families/__init__.py picks this module up by itself (FAMILIES below) and join_blocks() puts the family
into families/blocks.py's BASES / WRAPPED when this module is imported; blocks.py stays byte for byte as it was.

COMPLEXITY 4 = the previous bar + beyond its high / low + a close back to `back` -> market against it + both at once = no trade.
Tests: engine/tests/test_candle_sweep.py."""
from __future__ import annotations

from l2sim import Template

BACKS = ("range", "body", "far")


def signal(po, ph, pl, pc, h, l, c, back):
    """+1 long / -1 short / 0: THIS bar (h, l, c) against the PREVIOUS bar (po, ph, pl, pc) (module docstring, THE RULE)."""
    lo_line = {"range": pl, "body": min(po, pc), "far": max(po, pc)}[back]
    hi_line = {"range": ph, "body": max(po, pc), "far": min(po, pc)}[back]
    long = l < pl and c > lo_line
    short = h > ph and c < hi_line
    return 0 if long == short else (1 if long else -1)


class CandleSweep(Template):
    """candle_sweep (module docstring). go = +1 / -1 / 0: the signal of the tf bar that has just closed."""
    DEFAULTS = {"back": "body", "max_tr": 20}
    SCHEMA = {"back": ("choice", BACKS), "max_tr": ("int", 1, 20)}
    SCREEN_TFS = ("1", "5", "15", "30")
    FEATURES = ()

    def fam_day(self, ctx):
        self.go = 0

    def fam_update(self, ctx):
        self.go = 0
        if self.nb < 2:
            return
        O, H, L, C = self.O, self.H, self.L, self.C
        self.go = signal(O[-2], H[-2], L[-2], C[-2], H[-1], L[-1], C[-1], self.p["back"])

    def fam_signal(self, ctx):
        if self.go > 0:
            self._mkt(ctx, "long", struct=self.L[-1])
        elif self.go < 0:
            self._mkt(ctx, "short", struct=self.H[-1])


FAMILIES = {
    "candle_sweep": (CandleSweep, {}, False,
                     "candle_sweep: a tf bar trades beyond the previous bar's low (high) and closes back above (below) a line of that bar -- "
                     "back = range: its low (high); body: the bottom (top) of its body; far: the top (bottom) of its body -> market entry "
                     "against the sweep at the next bar's open: long after a swept low, short after a swept high; both at once = no trade; "
                     "structure level = the sweeping bar's own extreme; entries inside the idea's session, up to max_tr a session, one "
                     "position at a time; flat 15:58",
                     {"rationale": "Stops and breakout orders sit just beyond the last candle's high and low; a bar that runs them and closes "
                                   "back inside fills those traders at the extreme and leaves no one to push further, so their exits carry "
                                   "price back the other way.",
                      "complexity": 4,
                      "variants": [{"back": "range"}, {"back": "body"}, {"back": "far"}]}),
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
