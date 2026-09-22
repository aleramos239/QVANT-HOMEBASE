"""Price-action rules: a rule turns closed bars into a Signal (or nothing).

A rule runs every time a bar of its strategy's timeframe closes, with the
closed history (oldest first, the just-closed bar last) and the ET clock.
It returns ONE bracketed entry: side, entry type (Market now, or a Stop at
a price), an absolute stop and an absolute target. The engine does the
rest — accounts, sizing from the book, fills, the 15:55 flat.

Registered by name in RULES; a strategy's config names its rule.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from .contracts import tick_size
from .feed import Bar

ET = ZoneInfo("America/New_York")


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


def nq_10am_continuation(bars: list[Bar], now_et: dt.datetime, cfg) -> Optional[Signal]:
    """The 10am candidate (spec 2026-09-06, UNVALIDATED — shadow only):
    the 09:30-10:00 ET 30-minute candle; closed up -> long, down -> short,
    doji -> none; only when the close sits in the candle's top (long) /
    bottom (short) quarter; enter at the 10:00 open (market on the 09:59
    bar's close); stop = the candle's opposite extreme; target = 0.75 x the
    stop distance (RR 1:0.75), re-derived from the actual fill."""
    if not bars:
        return None
    last = bars[-1]
    t = last.ts.astimezone(ET)
    if (t.hour, t.minute) != (9, 59) or last.minutes != 1:
        return None                                  # fires once, on the 09:59 close
    day = t.date()
    candle = [b for b in bars
              if (bt := b.ts.astimezone(ET)).date() == day
              and dt.time(9, 30) <= bt.time() < dt.time(10, 0)]
    if len(candle) < 25:                             # the candle must be nearly whole
        return None
    o, c = candle[0].o, candle[-1].c
    h, l = max(b.h for b in candle), min(b.l for b in candle)
    rng = h - l
    if rng <= 0 or c == o:
        return None                                  # doji / flat
    tick = tick_size(cfg.symbol) or 0.25
    stats = {"candle_o": o, "candle_h": h, "candle_l": l, "candle_c": c,
             "range": round(rng, 4), "bars": len(candle),
             "close_pos": round((c - l) / rng, 3)}
    if c > o:
        if c < l + 0.75 * rng:
            return None                              # close not in the top quarter
        sl, ref = l, c
        tp = ref + 0.75 * (ref - sl)
        return Signal("Buy", "Market", None, _to_tick(sl, tick), _to_tick(tp, tick),
                      ref_px=ref, tp_rr=0.75, note=stats)
    if c > h - 0.75 * rng:
        return None                                  # close not in the bottom quarter
    sl, ref = h, c
    tp = ref - 0.75 * (sl - ref)
    return Signal("Sell", "Market", None, _to_tick(sl, tick), _to_tick(tp, tick),
                  ref_px=ref, tp_rr=0.75, note=stats)


RULES: dict[str, Callable] = {
    "nq_10am_continuation": nq_10am_continuation,
}
