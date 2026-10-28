"""open_atr_go_gvwap_ema -- open_atr_go with BOTH extra conditions of families/open_atr_go_x.py (the owner, 2026-10-26: "add the ema's to the
vwap combine them"): the first tf close at least k x ATR(14) from the 09:30 open that is also on the right side of the 18:00 ET VWAP AND stacked
with the EMAs (long: close > EMA9 > EMA24; short: the mirror). A close that has the distance but not both gives nothing and the wait goes on.
REGISTRATION as noise.py (join_blocks). Complexity 5. Tests: engine/tests/test_open_atr_go.py."""
from __future__ import annotations

from .open_atr_go_x import OpenAtrGoEma, OpenAtrGoGvwap


class OpenAtrGoGvwapEma(OpenAtrGoGvwap):
    spans_used = OpenAtrGoEma.spans_used

    def ok(self, side: int) -> bool:
        return OpenAtrGoGvwap.ok(self, side) and OpenAtrGoEma.ok(self, side)


FAMILIES = {
    "open_atr_go_gvwap_ema": (OpenAtrGoGvwapEma, {}, False,
                              "open_atr_go_gvwap_ema: the first tf close at least k x ATR(14 tf bars) away from the 09:30 open, on the right side of "
                              "the 18:00 ET VWAP and stacked with the trend (close > EMA9 > EMA24 for a long, the mirror for a short) -> market WITH "
                              "that move. One trade a day, nyam only, flat 15:58",
                              {"rationale": "A first push away from the open that the whole Globex day's average price and the short-term trend "
                                            "both back shows buyers or sellers in control at every horizon, while a push against either is the "
                                            "counter-trend spike that trend followers sell into.",
                               "complexity": 5,
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
