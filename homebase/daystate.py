"""A (strategy, account) day as the desk writes it down, and the words both halves of the engine share.

DayState is one strategy's one trade on one account for one day (kind straddle, levels, bars or lab). The order
words (WORKING, TERMINAL), the kill poll and the two "check it" sentences are read by engine.py and engine_lab.py
alike; they live here so neither imports the other.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

WORKING = {"Working", "PendingNew", "Pending", "Suspended", "PendingReplace"}
TERMINAL = {"Filled", "Canceled", "Rejected", "Expired"}    # an order that can never fill (more)
KILL_POLL_S, KILL_POLL_N = 0.25, 12     # the kill waits up to 3 s for its entry cancels to settle
MARKET_OUT_FAILED = "check it — market-out reported failure; verify the position"
PLACING_UNKNOWN = "placement outcome unknown after a restart — check the broker"


def _hhmm(s: str) -> dt.time:
    h, m = s.split(":")
    return dt.time(int(h), int(m))


def _to_tick(px: float, tick: float) -> float:
    return round(round(px / tick) * tick, 6)


@dataclass
class DayState:
    strategy: str
    account: str
    date: str
    qty: int = 0
    status: str = "idle"               # idle|placing|placed|live|done|error
    upper_id: Optional[str] = None
    lower_id: Optional[str] = None
    upper_px: Optional[float] = None
    lower_px: Optional[float] = None
    entry_side: Optional[str] = None
    entry_anchor: Optional[float] = None
    entry_fill: Optional[float] = None
    exit_reason: Optional[str] = None
    exit_fill: Optional[float] = None
    pnl: Optional[float] = None        # gross $, set at exit
    note: str = ""
    entry_qty: int = 0                 # entry contracts filled so far
    exit_qty: int = 0                  # contracts out again so far (exit fills)
    sl_px: Optional[float] = None      # bars strategies: absolute stop / target
    tp_px: Optional[float] = None
    tp_rr: Optional[float] = None      # bars: TP re-derived from the fill at this RR
    up_sl_id: Optional[str] = None     # each leg's OSO stop / target order,
    up_tp_id: Optional[str] = None     # re-priced to the actual fill
    dn_sl_id: Optional[str] = None
    dn_tp_id: Optional[str] = None
    brackets_moved: bool = False
    # kind "levels": this account's geometry today (points from the trigger / the fill), set at placement
    sl_pts: Optional[float] = None
    sl_sell_pts: Optional[float] = None   # the sell leg's stop distance when it differs from sl_pts (levels.leg_stop)
    tp_pts: Optional[float] = None
    take_usd: Optional[float] = None   # the net $ the take is sized for (None: the fallback target)
    take_src: str = ""                 # day_take | target_take | fallback
    take_px: Optional[float] = None    # the take price the broker-side limit rests at (from the fill)
