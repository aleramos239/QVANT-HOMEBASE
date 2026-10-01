"""Per-account drawdown tracking.

Prop accounts die on their *own* drawdown limit, not on a copier-wide rule. This
module tracks one account's equity high-water mark and reports how close it is to
breaching its limit, so the engine can flatten and bench that single account
(leaving the others copying) and the dashboard can draw a distance-to-blowup
meter.

Pure logic — no I/O, no broker calls. The engine feeds it an `equity` number
each poll (balance, plus open-trade P&L when the platform reports it) and reads
back a snapshot. Two limit modes:

  - "trailing": drawdown measured from the highest equity ever seen
    (peak − current). Approximates the trailing-threshold drawdown used by Apex
    and Topstep. NOTE: real trailing thresholds often stop trailing once they
    reach the starting balance + target; this tracks the running peak, which is
    conservative (trips at or before the real threshold) — good for safety.
  - "static": drawdown measured from the starting equity (start − current),
    i.e. a fixed daily-loss-style floor.

`limit_usd <= 0` disables tracking (state == "off").

The daily rules (day_take / day_lock / target_take, sizing tiers, the eval standing) are in
homebase.dayrules, re-exported at the bottom of this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Fraction of the limit at which we start warning (drives the amber meter and a
# `account_dd_warning` audit event before the hard trip).
DEFAULT_WARN_RATIO = 0.8


@dataclass
class AccountRisk:
    limit_usd: float = 0.0
    mode: str = "trailing"               # "trailing" | "static"
    warn_ratio: float = DEFAULT_WARN_RATIO
    start_equity: Optional[float] = None  # first equity seen (or a reset value)
    peak_equity: Optional[float] = None   # highest equity seen
    current_equity: Optional[float] = None

    def reset(self, equity: Optional[float] = None) -> None:
        """Re-baseline the peak/start to `equity` (or clear if None).

        Called when an account is re-enabled after a trip, so a fresh session
        doesn't immediately re-trip on the same old high-water mark.
        """
        self.start_equity = equity
        self.peak_equity = equity
        self.current_equity = equity

    def update(self, equity: Optional[float]) -> dict:
        """Record the latest equity and return a snapshot (see `snapshot`)."""
        if equity is not None:
            equity = float(equity)
            self.current_equity = equity
            if self.start_equity is None:
                self.start_equity = equity
            if self.peak_equity is None or equity > self.peak_equity:
                self.peak_equity = equity
        return self.snapshot()

    @property
    def drawdown(self) -> Optional[float]:
        """Current drawdown in USD (>= 0), or None if equity is unknown."""
        if self.current_equity is None:
            return None
        anchor = self.peak_equity if self.mode == "trailing" else self.start_equity
        if anchor is None:
            return None
        return max(0.0, anchor - self.current_equity)

    @property
    def enabled(self) -> bool:
        return self.limit_usd and self.limit_usd > 0

    def _state(self, dd: Optional[float]) -> str:
        if not self.enabled:
            return "off"
        if dd is None:
            return "unknown"
        if dd >= self.limit_usd:
            return "trip"
        if dd >= self.limit_usd * self.warn_ratio:
            return "warn"
        return "ok"

    def snapshot(self) -> dict:
        """A UI/engine-friendly view of where this account stands.

        `distance` is USD of room left before the limit; `pct` is how much of the
        allowance is used (0..1+, clamped at >=0). `state` is one of
        off | unknown | ok | warn | trip.
        """
        dd = self.drawdown
        state = self._state(dd)
        distance = None
        pct = None
        if self.enabled and dd is not None:
            distance = self.limit_usd - dd
            pct = dd / self.limit_usd if self.limit_usd else None
        return {
            "mode": self.mode,
            "limit": self.limit_usd if self.enabled else 0.0,
            "start": self.start_equity,
            "peak": self.peak_equity,
            "current": self.current_equity,
            "drawdown": dd,
            "distance": distance,
            "pct": pct,
            "state": state,
        }

    def tripped(self, equity: Optional[float] = None) -> bool:
        """True if, after optionally updating with `equity`, the limit is breached."""
        if equity is not None:
            self.update(equity)
        return self._state(self.drawdown) == "trip"


# Daily rules (day_take / day_lock / target_take, sizing tiers, the eval standing) live in homebase.dayrules
# and are re-exported here: one place to import "risk" from.
from .dayrules import (LOCK_LOCK, LOCK_TAKE, DayBook, DayRules, ceil_to_tick, merge_rules,  # noqa: E402,F401
                       round_trip_fee, size_for_profit, standing, take_level, take_points)
