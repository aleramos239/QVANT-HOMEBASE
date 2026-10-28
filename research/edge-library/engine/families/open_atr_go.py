"""open_atr_go -- the first ATR move from the open, followed (the owner's request of 2026-10-25; idea 34 of ideas-100-untried-2026-10-25).
No Level-2 feature is read (FEATURES = ()): NQ, ES and GC, 1 contract, flat 15:58 ET.

    open_atr_go   bar-based 1/5/15/30   nyam; settings k (+ the Template's max_tr, dir)

THE RULE (fixed here, before any run):
  * REFERENCE = the OPEN of the first 1-minute bar from 09:30 ET (a first bar more than 5 minutes late: no reference, no trade that day).
  * A = the Template's ATR(14) of the idea's own tf bars (Wilder, warm since 00:00 ET), the bar just closed included: the same ATR the hm40
    stops use. "14 candle look back" = this ATR on 1-minute bars, or on 5-minute bars.
  * SIGNAL, read at a tf close from 09:30 on: the FIRST close at least k x A away from the reference. Above it = long, below it = short
    (the move is followed). Market order at that close, filled at the next bar's open. One signal a day: later moves are not taken, even
    after the trade has exited (max_tr 1).
  * ENTRIES inside nyam only (a tf close in (09:30, 11:00], never in the last 5 minutes of it: the Template's rule).
  * EXITS. None of its own: the standard table's stop / target cells and the flat time 15:58 ET.
  * SIDES. `dir` is the Template's (both by default); the long and short sides are MIRROR units (families.MIRROR: 'dir').

REGISTRATION as noise.py: join_blocks() puts the family into families/blocks.py's BASES / WRAPPED when this module is imported.
COMPLEXITY 3 = the reference + the distance k x ATR + one trade a day.
Tests: engine/tests/test_open_atr_go.py."""
from __future__ import annotations

from l2sim import Template

TFS = ("1", "5", "15", "30")
OPEN = 34200                                        # 09:30 ET, seconds after 00:00
OPEN_TOL_S = 300                                    # the open's first minute bar may start at most 5 minutes after 09:30


class OpenAtrGo(Template):
    """open_atr_go (module docstring). State per day: ref (the 09:30 open), mi (1-minute bars read), done (the day's one signal was given),
    go (+1 / -1 / 0: the signal of the tf bar that has just closed)."""
    DEFAULTS = {"k": 1.0, "max_tr": 1}
    SCHEMA = {"k": ("float", 0.1, 10.0), "max_tr": ("int", 1, 1)}
    SCREEN_TFS = TFS
    FEATURES = ()

    def fam_filter(self, ids):
        return [s for s in ids if s == "nyam"]

    def fam_day(self, ctx):
        self.mi = 0
        self.ref = None
        self.no_open = False                        # the 09:30 bar came too late: no trade today
        self.done = False
        self.go = 0

    def fam_update(self, ctx):
        self.go = 0
        M = self.M
        for i in range(self.mi, len(M)):
            s = M[i][0]
            if self.ref is None and not self.no_open and s >= OPEN:
                if s - OPEN > OPEN_TOL_S:
                    self.no_open = True
                else:
                    self.ref = M[i][1]
        self.mi = len(M)
        if self.ref is None or self.done or not self.atr or M[-1][0] < OPEN:
            return
        d = self.C[-1] - self.ref
        if abs(d) >= self.p["k"] * self.atr:
            self.go, self.done = (1 if d > 0 else -1), True

    def fam_signal(self, ctx):
        if self.go:
            self._mkt(ctx, "long" if self.go > 0 else "short")


FAMILIES = {
    "open_atr_go": (OpenAtrGo, {}, False,
                    "open_atr_go: the first tf close at least k x ATR(14 tf bars) away from the 09:30 open -> market WITH that move (above = "
                    "long, below = short) at the next bar's open. One trade a day, nyam only, flat 15:58",
                    {"rationale": "A move of one average bar-range per bar-length-times-14 away from the open, before the morning has settled, is "
                                  "forced flow (stops, hedgers, index buyers) that has not finished; the traders who fade it first are on the "
                                  "losing side as it continues.",
                     "complexity": 3,
                     "variants": [{"k": k, "dir": d} for k in (0.5, 1.0, 1.5) for d in ("long", "short")]}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (noise.py, REGISTRATION). Idempotent."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
