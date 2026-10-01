"""Price-action rules: a rule turns closed bars into a Signal (or nothing).

A rule runs every time a bar of its strategy's timeframe closes, with the
closed history (oldest first, the just-closed bar last) and the ET clock.
It returns ONE bracketed entry: side, entry type (Market now, or a Stop at
a price), an absolute stop and an absolute target. The engine does the
rest — accounts, sizing from the book, fills, the 15:55 flat.

Registered by name in RULES; a strategy's config names its rule.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Signal:
    side: str                          # "Buy" | "Sell"
    entry: str = "Market"              # "Market" | "Stop"
    entry_price: Optional[float] = None   # Stop trigger (Market: None)
    sl_px: float = 0.0                 # absolute stop
    tp_px: float = 0.0                 # absolute target (from the reference price)
    ref_px: Optional[float] = None     # the price the rule sized SL/TP from
    tp_rr: Optional[float] = None      # if set, TP is re-derived from the FILL:
                                       # fill +/- tp_rr * |fill - sl|
    note: dict = field(default_factory=dict)


def _to_tick(px: float, tick: float) -> float:
    return round(round(px / tick) * tick, 6)


RULES: dict[str, Callable] = {}      # the desk ships no bar rule today; kind "bars" and the feed stay
