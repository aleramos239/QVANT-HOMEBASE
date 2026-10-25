"""avwap_touch_flow -- avwap_touch (families/avwap.py) with the session's order flow on the trade's side.
The owner (2026-10-24), asked which VWAP angle: "VWAP + order flow". Written from the rule below before any result. A new module, so
avwap.py and the stores of its three families keep their code stamps.

THE RULE. avwap_touch exactly (a close `away` ticks from the line arms a LIMIT AT the line, on the side price came from, re-priced at
every tf close, the first touch uses the arm up), plus `cumd`: the limit is placed only when the net aggressor flow (buy minus sell
volume, the flow table engine/flowtab.py) of the whole minutes from 09:30 ET to this tf close points the trade's way (a long needs net
buying):
    cumd = off | with | med | p80    (off, the default: avwap_touch to the trade)
    with  the sign only          med / p80  the share (delta / volume) must also reach the 50th / 80th percentile of |share| of the
                                 same clock window on the 20 trade dates before (15 needed): the candle_sweep CUMD rule, idea C
No flow row, no volume, or a window that is empty (a tf close before 09:31: the Asia, London and pre passes) = no order. The flow
file ends where it ends (flowtab.last_date): days after it never trade with cumd on. Only whole minutes that have ended are read.
Tests: engine/tests/test_avwap_flow.py."""
from __future__ import annotations

import numpy as np

import flowtab

from . import avwap as AV
from . import blocks as B
from .candle_sweep import CDREL_MIN, CDREL_N, CUMD, OPEN930


class AvwapTouchFlow(AV.AvwapTouch):
    """avwap_touch_flow (module docstring)."""
    DEFAULTS = {**AV.AvwapTouch.DEFAULTS, "cumd": "off"}
    SCHEMA = {**AV.AvwapTouch.SCHEMA, "cumd": ("choice", ("off", *CUMD))}

    def share(self, ctx, a, b, iso=None):
        """Delta / volume of the flow table's whole minutes in [a, b) on the trade date (or `iso`); None: an empty window, no flow row, or no volume."""
        w = flowtab.window(ctx.root, iso or self.day, a, b)
        return None if w is None or w[0] <= 0 else w[1] / w[0]

    def flow_ok(self, ctx, side):
        """The session's flow since 09:30 points the trade's way and, unless cumd = with, reaches its quantile of the 20 earlier dates."""
        go, q = (1 if side == "long" else -1), CUMD[self.p["cumd"]]
        b = (self.M[-1][0] // 60 + 1) * 60                         # the clock close of the 1-minute bar that has just closed
        x = self.share(ctx, OPEN930, b)
        if x is None or x * go <= 0:
            return False
        if q is None:
            return True
        ref = [abs(v) for v in (self.share(ctx, OPEN930, b, r["date"]) for r in self.dl[-CDREL_N:]) if v is not None]
        return len(ref) >= CDREL_MIN and x * go >= float(np.quantile(ref, q))

    def place(self, ctx, side, px):
        if self.p["cumd"] == "off" or self.flow_ok(ctx, side):
            super().place(ctx, side, px)


FAMILIES = {
    "avwap_touch_flow": (AvwapTouchFlow, {}, False,
                         "avwap_touch_flow: avwap_touch (a close `away` ticks from an anchored VWAP -> a limit AT the line on the side price "
                         "came from) placed only when the net aggressor flow from 09:30 to this close points the trade's way (cumd: with = "
                         "the sign, med / p80 = also its share reaches that quantile of the 20 earlier dates); no flow = no order; the "
                         "sheet's stop and target; flat 15:58 (the owner, 2026-10-24: VWAP + order flow)",
                         {"rationale": "A pullback to the anchored VWAP while the session's aggressors have been on the same side as the move "
                                       "is where the trend's buyers (or sellers) reload and the ones who faded the extension are run over; "
                                       "without that flow the same touch is only a coin flip around the average price. Who loses: the traders "
                                       "who fade the extension at the line, and the passive side that kept absorbing the flow.",
                          "complexity": 6,
                          "variants": [{"line": "rth", "cumd": "with"}, {"line": "rth", "cumd": "med"}, {"line": "rth", "cumd": "p80"}]}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (as avwap.py): the wrapped class a card runs. Idempotent."""
    for name, entry in FAMILIES.items():
        if not B._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = B._wrap(name, entry[0])
        B.BASES[name] = entry
        B.WRAPPED[name] = cls
        setattr(B, cls.__name__, cls)


join_blocks()
