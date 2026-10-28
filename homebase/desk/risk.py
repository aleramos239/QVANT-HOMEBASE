"""The daily rules (day_take / day_lock / target_take, sizing tiers, the eval standing) are in
homebase.dayrules, re-exported at the bottom of this module.
"""
from __future__ import annotations

# Daily rules (day_take / day_lock / target_take, sizing tiers, the eval standing) live in homebase.dayrules
# and are re-exported here: one place to import "risk" from.
from .dayrules import (LOCK_LOCK, LOCK_TAKE, DayBook, DayRules, ceil_to_tick, merge_rules,  # noqa: E402,F401
                       round_trip_fee, size_for_profit, standing, take_level, take_points)


def prop_room(rules: dict, start: float, eod: dict, today: str, balance: float, day_pnl: float) -> dict:
    """What a prop account may still lose (read-only; nothing here refuses an order).  `rules` is a propsim rule file,
    `eod` the desk's {date: end-of-day balance}.  The floor trails the best EOD balance by trailing_mll and locks at
    start + lock_floor (the rule files' model: an intraday trail is not modelled).  daily = the day's loss limit plus
    today's closed P&L (None: no daily limit); drawdown = balance - floor; contracts = cap_micros / 10 minis.
    The balance is cash: the page takes the open loss off these two."""
    peak = max([start] + [float(v) for d, v in eod.items() if d < today])
    floor = peak - float(rules["trailing_mll"])
    if rules.get("lock_floor") is not None:
        floor = min(floor, start + float(rules["lock_floor"]))
    dll, cap = rules.get("daily_loss_limit"), rules.get("cap_micros")
    return {"daily": None if dll is None else float(dll) + day_pnl, "drawdown": balance - floor,
            "contracts": None if cap is None else int(cap) // 10}
