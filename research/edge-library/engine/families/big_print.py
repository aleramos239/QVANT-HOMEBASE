"""big_print -- the BIG ORDER as an entry trigger (the owner's request of 2026-10-12): when an order of more than `lots` contracts is
filled, enter with it. One trade a day from 09:30. NQ, ES and GC, 1 contract, bar-based, 1-minute bars only.

    big_print   bar-based 1   all seven sessions; setting lots = the size the order must be ABOVE (+ the Template's max_tr, dir)

THE RULE (fixed here before any run):
  * ORDER. The largest aggressor order of a whole minute, with its side: the desk's own tick archive (engine/flowtab.py, the `big` series
    the bigorder filter block reads). An order is the prints that share one exchange stamp, so a 40-lot order that fills in four prints is
    one 40-lot order. Its side is the aggressor's: a buy order lifts the offer = LONG, a sell order hits the bid = SHORT.
  * SIGNAL. At a 1-minute bar's close, that minute's largest order is strictly ABOVE `lots` (25 means 26 or more) -> its side.
  * ORDER PLACED. A market order at that close: it fills at the next bar's open (the first print after the 85 ms placement latency).
  * ENTRIES. Inside the idea's session only (a close in (start, end], never in the last 5 minutes of it: the Template's rule). For the
    nyam session the first possible decision is the close of 09:31, from the minute 09:30:00-09:30:59. Up to `max_tr` a session (default
    1), one position at a time. EXITS: none of its own; the sheet's stop and target and the flat time 15:58 ET.

SAID OUT LOUD: the flow file is per MINUTE, so the order is known at the close of its minute and the entry is the next bar's open: up to
a minute after the order, never at the order. A minute holds one largest order: a bigger order of the other side in the same minute hides
a smaller one, and two orders of the same size are not told apart. The side is an estimate (flowtab: 99.5 % of the minutes agree with the
vendor's delta on the top quartile of |delta|).

NO LOOK-AHEAD, where it could hide: the order of a minute is read at that minute's close, nothing later (flowtab's law: a minute is
complete at +60 s); the clock of a decision is the bar's clock close, taken from the last 1-minute bar the Template has added.

REGISTRATION. As families/ddiv.py: families/__init__.py picks this module up by itself (FAMILIES below) and join_blocks() puts the family
into families/blocks.py's BASES / WRAPPED when this module is imported; blocks.py stays byte for byte as it was.

COMPLEXITY 2 = the largest order of the minute is above `lots` + its side. Tests: engine/tests/test_big_print.py."""
from __future__ import annotations

import flowtab
from l2sim import Template


class BigPrint(Template):
    """big_print (module docstring). State per instance: go = +1 / -1 / 0: the signal of the 1-minute bar that has just closed."""
    DEFAULTS = {"lots": 25, "max_tr": 1}
    SCHEMA = {"lots": ("int", 1, 500), "max_tr": ("int", 1, 20)}
    SCREEN_TFS = ("1",)
    FEATURES = ()

    def fam_day(self, ctx):
        if self.tf != 1:
            raise ValueError("big_print reads one minute of flow: 1-minute bars only")
        self.go = 0

    def fam_update(self, ctx):
        self.go = 0
        now = (self.M[-1][0] // 60 + 1) * 60          # the clock close of the minute that has just closed, seconds after 00:00 ET
        w = flowtab.window(ctx.root, self.day, now - 60, now)
        if w is not None and abs(w[3]) > self.p["lots"]:
            self.go = 1 if w[3] > 0 else -1

    def fam_signal(self, ctx):
        if self.go:
            self._mkt(ctx, "long" if self.go > 0 else "short")


FAMILIES = {
    "big_print": (BigPrint, {}, False,
                  "big_print: the largest aggressor order of a whole minute (prints sharing one exchange stamp) is above `lots` contracts at "
                  "a 1-minute close -> a market entry WITH its side (a buy order = long, a sell order = short) at the next bar's open; "
                  "entries inside the idea's session, up to max_tr a session (default 1), one position at a time; flat 15:58",
                  {"rationale": "An aggressor who pays the spread for a size well above the usual order wants the position now and "
                                "is not the one being picked off; the move he starts carries on while the market absorbs his size, "
                                "and the passive side that sold to him is the one left on the wrong side.",
                   "complexity": 2,
                   "variants": [{"lots": 15}, {"lots": 25}, {"lots": 40}]}),
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
