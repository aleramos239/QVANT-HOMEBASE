"""Daily rules: day_take / day_lock / target_take, the sizing tiers and the eval standing (spec 2026-10-01).

Pure logic, no I/O -- the engine feeds it the closed P&L of the day and the open P&L at the latest price.  It
lives in its own module (re-exported by homebase.risk) because the
tester's strategies need the same numbers and must not import the desk's risk module (the chart service lists
strategies in-process; tests/test_charts_paper.py keeps the order path out of it).  From the research
(evalcore._walk_day, take_level):

  day_take X   the day's open + closed P&L, net of the round-trip fee, reaches X  ->  flatten the account's
               open positions, cancel entries, no more trades today.  With ONE trade a day it is a
               take-profit at the fill +/- take_points(X) (the broker-side limit); the engine's price
               watcher is the backstop when the limit does not fill.
  day_lock Y   a trade CLOSES and the day's closed P&L is >= Y  ->  no new entry today (open P&L is
               ignored).  Inert with one trade a day.
  target_take  EVAL only: X is the smallest day P&L that passes the eval today (take_level), per account,
               set each morning.  The lower of day_take and that level wins.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Optional

LOCK_TAKE = "day_take"
LOCK_LOCK = "day_lock"


@dataclass(frozen=True)
class DayRules:
    day_take: float = 0.0        # $ net, 0 = off
    day_lock: float = 0.0        # $ closed, 0 = off
    target_take: bool = False    # eval: take = the account's remaining distance to pass

    @property
    def any(self) -> bool:
        return bool(self.day_take or self.day_lock or self.target_take)


def merge_rules(rules) -> DayRules:
    """One account runs several strategies: the tightest (lowest positive) take and
    lock, and target_take if any of them asks for it."""
    takes = [r.day_take for r in rules if r.day_take > 0]
    locks = [r.day_lock for r in rules if r.day_lock > 0]
    return DayRules(min(takes) if takes else 0.0, min(locks) if locks else 0.0,
                    any(r.target_take for r in rules))


def ceil_to_tick(x: float, tick: float) -> float:
    """x rounded UP onto the tick grid (a take that must net at least X never rounds down)."""
    return round(math.ceil(x / tick - 1e-9) * tick, 6)


def round_trip_fee(qty: int, fee_per_contract: float) -> float:
    return float(qty) * float(fee_per_contract)


def take_points(net_usd: float, qty: int, point_value: float, fee_per_contract: float,
                tick: float) -> float:
    """Points from the FILL to the take price at which `qty` contracts net at least
    `net_usd` after the round-trip fee.  4 NQ ($80/pt, $16 fee): $1,500 -> 18.95 -> 19.0."""
    if qty <= 0 or point_value <= 0 or net_usd <= 0:
        raise ValueError("take_points needs a positive take, qty and point value")
    return ceil_to_tick((net_usd + round_trip_fee(qty, fee_per_contract))
                        / (point_value * qty), tick)


def take_level(target: float, profit: float, largest: float, days: int, *,
               min_days: int = 1, consistency=None):
    """target_take's X: the smallest P&L today at which the account PASSES today (None: there is none).
    profit + L >= target; days + 1 >= min_days; and with a consistency rule c,
    max(largest, L) <= c * (profit + L) -- if the target alone would break it, L rises until it holds,
    and when even that cannot hold (L > c*profit/(1-c)) there is no level today.
    Copy of evalcore.take_level for one account."""
    L = float(target) - float(profit)
    if consistency is not None:
        c = float(consistency)
        L = max(L, float(largest) / c - float(profit))
        cap = c * profit / (1.0 - c) if c < 1.0 else math.inf
        if L > cap + 1e-9:
            return None
    if days + 1 < int(min_days):
        return None
    return L if L > 0 else None


def size_for_profit(tiers, profit: float, cap: int) -> int:
    """Contracts by EOD profit: tiers [[min_profit, qty], ...] -- the highest tier whose
    min_profit <= profit (below the first: the first), never above `cap`.  No tiers: `cap`."""
    rows = sorted((float(a), int(b)) for a, b in (tiers or []))
    if not rows:
        return int(cap)
    qty = rows[0][1]
    for lo, q in rows:
        if profit >= lo:
            qty = q
    return max(0, min(int(cap), qty))


def standing(balances: dict, today: str, *, seed_largest: float = 0.0, seed_days: int = 0):
    """(largest winning day, trading days) from the daily closing balances {date: balance} of the days
    BEFORE `today` -- each day's P&L is the balance change from the previous recorded day.  The first
    recorded day has no baseline (seeds carry what came before the recording)."""
    prev, largest, days = None, float(seed_largest), int(seed_days)
    for d in sorted(balances):
        if d >= today:
            break
        b = float(balances[d])
        if prev is not None and abs(b - prev) > 0.005:
            days += 1
            largest = max(largest, b - prev)
        prev = b
    return largest, days


@dataclass
class DayBook:
    """One account's day: closed P&L (net of fees), whether it is stopped for the day, and the
    morning's eval standing.  The engine persists it (a restart keeps the day)."""
    account: str
    date: str
    closed_net: float = 0.0
    closes: int = 0
    locked: Optional[str] = None            # None | "day_take" | "day_lock": no new entries today
    prepared: bool = False                  # the morning standing below was read
    morning_profit: Optional[float] = None  # EOD profit before today (balance - start balance)
    largest_day: float = 0.0
    days: int = 0
    target_level: Optional[float] = None    # target_take's X today (None: none)

    def record_close(self, net: float, rules: DayRules) -> Optional[str]:
        """A trade closed with `net` $ (after its fee).  Returns the lock reason if this close LOCKED the
        day (day_take wins over day_lock when both hold), else None."""
        self.closed_net = round(self.closed_net + float(net), 2)
        self.closes += 1
        if self.locked:
            return None
        take = self.take_net(rules)
        if take is not None and self.closed_net >= take - 1e-9:
            self.locked = LOCK_TAKE
        elif rules.day_lock and self.closed_net >= rules.day_lock - 1e-9:
            self.locked = LOCK_LOCK
        return self.locked

    def take_net(self, rules: DayRules) -> Optional[float]:
        """The net day P&L that takes the day: the lower of day_take and (target_take) today's level."""
        c = [x for x in (rules.day_take or None,
                         self.target_level if rules.target_take else None) if x]
        return min(c) if c else None

    def take_hit(self, open_net: float, rules: DayRules) -> bool:
        """closed + open (both net of fees) has reached the take.  Never on a locked day (already taken)."""
        take = self.take_net(rules)
        return take is not None and not self.locked and self.closed_net + open_net >= take - 1e-9

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DayBook":
        keys = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in keys})
