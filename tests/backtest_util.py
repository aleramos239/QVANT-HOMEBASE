"""A synthetic NQ archive for runner/API tests: two sessions, one with a hole."""
from __future__ import annotations

import datetime as dt

from homebase.backtest.tape import et_ns
from tests.charts_util import rows, write_archive

D1, D2 = dt.date(2024, 3, 5), dt.date(2024, 3, 6)


def ms(d: dt.date, hms: str) -> int:
    return et_ns(d, hms) // 1_000_000


def nq_archive(base):
    """D1: a full 09:25-16:00 day whose 09:30 long straddle leg wins (+15 pts).
    D2: prints stop at 12:59 — missing 13:00-16:00, so the tester must skip it."""
    day = rows(ms(D1, "09:25:00"), [100.0] * 290, step_ms=1000)                    # to 09:29:50
    day += rows(ms(D1, "09:30:01"), [110.0, 112.0, 126.0], step_ms=1000)
    day += rows(ms(D1, "09:31:00"), [120.0] * 1500, step_ms=15_000)                # to 15:45
    write_archive(base, "NQ", D1, "NQH4", day)
    write_archive(base, "NQ", D2, "NQH4", rows(ms(D2, "09:25:00"), [100.0] * 1284, step_ms=10_000))
    return base
