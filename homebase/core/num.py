"""Number checks shared across the desk, the chart service and the Lab runner.

Three finite-number checks exist ON PURPOSE: they agree on every value except an int too large for a float
(|v| > ~1.8e308, which json.loads gives for a 309+ digit literal). Each call site keeps the one it always had.
"""
from __future__ import annotations

import math
from typing import Optional


def finite(v) -> bool:
    """A real, finite int or float (a bool is not one). An int past float range RAISES OverflowError (math.isfinite)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def finite_big_int_ok(v) -> bool:
    """As finite(), but an int past float range is True (it is compared, never converted)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")


def finite_no_overflow(v) -> bool:
    """As finite(), but an int past float range is False instead of raising."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    try:
        return math.isfinite(v)
    except OverflowError:
        return False


def is_int(v) -> bool:
    """An int that is not a bool (6.0 is not one)."""
    return isinstance(v, int) and not isinstance(v, bool)


def float_or_none(v) -> Optional[float]:
    """float(v) for an int or float that is not a bool, else None. NaN and inf pass through; an int past float range raises OverflowError."""
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def to_tick(px: float, tick: float) -> float:
    """px on the nearest tick, rounded to 6 places (float noise off)."""
    return round(round(px / tick) * tick, 6)
