"""open_atr_go_x -- two more variants of open_atr_go (families/open_atr_go.py), the owner's request of 2026-10-26.

    open_atr_go_gvwap   open_atr_go + the 18:00 ET (Globex open) VWAP: LONG needs the tf close at least k x A above the 09:30 open AND above the
                        VWAP anchored at 18:00 ET of the evening before (avwap.Line 'globex', the toolkit's one); SHORT the mirror. A close beyond
                        the band on the wrong side of that VWAP gives nothing and the wait goes on; the first close that has both is the day's signal.
    open_atr_go_ema     open_atr_go + two EMAs of the idea's own tf closes, 9 and 24 (warm since 00:00 ET): LONG needs the close at least k x A above
                        the open AND close > EMA9 > EMA24; SHORT the mirror (close < EMA9 < EMA24). Same waiting rule.

Entries, exits, sides as open_atr_go. REGISTRATION as noise.py (join_blocks). Complexity 4 each.
Tests: engine/tests/test_open_atr_go.py."""
from __future__ import annotations

from .avwap import Line
from .open_atr_go import OPEN, OPEN_TOL_S, OpenAtrGo


class _Gated(OpenAtrGo):
    """open_atr_go with one extra condition `ok(side)` that a close must meet to give the day's signal."""

    def ok(self, side: int) -> bool:
        raise NotImplementedError

    def fam_update(self, ctx):
        self.go = 0
        M = self.M
        for i in range(self.mi, len(M)):
            self.feed(M[i])
            if self.ref is None and not self.no_open and M[i][0] >= OPEN:
                if M[i][0] - OPEN > OPEN_TOL_S:
                    self.no_open = True
                else:
                    self.ref = M[i][1]
        self.mi = len(M)
        if self.ref is None or self.done or not self.atr or M[-1][0] < OPEN:
            return
        d = self.C[-1] - self.ref
        side = 1 if d > 0 else -1
        if abs(d) >= self.p["k"] * self.atr and self.ok(side):
            self.go, self.done = side, True

    def feed(self, m) -> None:
        pass


class OpenAtrGoGvwap(_Gated):
    def fam_day(self, ctx):
        super().fam_day(ctx)
        self.ln = Line("globex", ctx.root, self.day, self.dl, self.ROLLS)

    def feed(self, m) -> None:
        self.ln.feed(m)

    def ok(self, side: int) -> bool:
        w = self.ln.value()
        return w is not None and (self.C[-1] - w) * side > 0


class OpenAtrGoEma(_Gated):
    def spans_used(self):
        return (9, 24)

    def ok(self, side: int) -> bool:
        c, a, b = self.C[-1], self.E[9], self.E[24]
        return (c - a) * side > 0 and (a - b) * side > 0


FAMILIES = {
    "open_atr_go_gvwap": (OpenAtrGoGvwap, {}, False,
                          "open_atr_go_gvwap: the first tf close at least k x ATR(14 tf bars) away from the 09:30 open AND on the same side of the "
                          "VWAP anchored at 18:00 ET -> market WITH that move at the next bar's open. One trade a day, nyam only, flat 15:58",
                          {"rationale": "A move one ATR away from the open that price also holds beyond the whole Globex day's average price shows "
                                        "buyers or sellers in control of the full session, while a spike that falls back through that VWAP is "
                                        "the noise that the fade-traders win.",
                           "complexity": 4,
                           "variants": [{"k": k} for k in (0.5, 1.0, 1.5)]}),
    "open_atr_go_ema": (OpenAtrGoEma, {}, False,
                        "open_atr_go_ema: the first tf close at least k x ATR(14 tf bars) away from the 09:30 open AND stacked with the trend "
                        "(close > EMA9 > EMA24 for a long, the mirror for a short) -> market WITH that move. One trade a day, nyam only, flat 15:58",
                        {"rationale": "A first push away from the open that goes with the short-term trend (price above a rising fast average "
                                      "above the slow one) is a continuation of flow already under way, while a push against the trend is the "
                                      "counter-trend spike the trend followers sell into.",
                         "complexity": 4,
                         "variants": [{"k": k} for k in (0.5, 1.0, 1.5)]}),
}


def join_blocks() -> None:
    """Put the families into families/blocks.py's BASES and WRAPPED (noise.py, REGISTRATION). Idempotent."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
