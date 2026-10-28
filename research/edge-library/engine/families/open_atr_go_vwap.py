"""open_atr_go_vwap -- open_atr_go (families/open_atr_go.py) with the 09:30 VWAP added (the owner, 2026-10-26: "Add 9:30 vwap").

    open_atr_go_vwap   bar-based 1/5/15/30   nyam; settings k (+ the Template's max_tr, dir)

THE RULE: as open_atr_go (reference = the 09:30 open, A = ATR(14) of the idea's own tf bars), plus the VWAP since 09:30 (volume-weighted
(h + l + c) / 3 of the 1-minute bars, the bar just closed included, the engine's VWAP rule as noise_band): LONG needs the tf close at least
k x A above the reference AND above the VWAP; SHORT the mirror. A close beyond the band on the wrong side of the VWAP gives nothing and the
wait goes on; the FIRST close that has both gives the day's one signal. Entries, exits, sides as open_atr_go.
REGISTRATION as noise.py (join_blocks). Complexity 4 = open_atr_go + the VWAP.
Tests: engine/tests/test_open_atr_go.py."""
from __future__ import annotations

from .open_atr_go import OPEN, OPEN_TOL_S, OpenAtrGo


class OpenAtrGoVwap(OpenAtrGo):
    """State on top of open_atr_go: vv / vp, the VWAP sums since 09:30."""

    def fam_day(self, ctx):
        super().fam_day(ctx)
        self.vv = self.vp = 0.0

    def fam_update(self, ctx):
        self.go = 0
        M = self.M
        for i in range(self.mi, len(M)):
            s, o, h, l, c, v = M[i]
            if s < OPEN:
                continue
            if self.ref is None and not self.no_open:
                if s - OPEN > OPEN_TOL_S:
                    self.no_open = True
                else:
                    self.ref = o
            if self.ref is not None and v > 0:
                self.vv += v
                self.vp += v * (h + l + c) / 3.0
        self.mi = len(M)
        if self.ref is None or self.done or not self.atr or self.vv <= 0 or M[-1][0] < OPEN:
            return
        c, w, d = self.C[-1], self.vp / self.vv, self.C[-1] - self.ref
        if abs(d) >= self.p["k"] * self.atr and (c > w if d > 0 else c < w):
            self.go, self.done = (1 if d > 0 else -1), True


FAMILIES = {
    "open_atr_go_vwap": (OpenAtrGoVwap, {}, False,
                         "open_atr_go_vwap: the first tf close at least k x ATR(14 tf bars) away from the 09:30 open AND on the same side of the "
                         "09:30 VWAP -> market WITH that move at the next bar's open. One trade a day, nyam only, flat 15:58",
                         {"rationale": "A move one ATR away from the open that price also holds beyond the day's average price shows buyers or "
                                       "sellers who paid up and stayed in control, while a spike that falls back through the VWAP is the "
                                       "noise that the fade-traders win.",
                          "complexity": 4,
                          "variants": [{"k": k} for k in (0.5, 1.0, 1.5)]}),
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
