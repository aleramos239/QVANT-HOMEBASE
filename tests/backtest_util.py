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


# ---- the parity archive: a synthetic NQ tape spread over 2021-2024 -----------------
# Used by the 2021-2024 byte-parity pin (tests/test_tester_range_parity.py): a 2021-01-01 ->
# 2024-12-31 run over it must produce the SAME bundle before and after the tester's range rework.
WIN_DAYS = [dt.date(2021, 3, 2), dt.date(2022, 6, 15), dt.date(2023, 9, 20), dt.date(2024, 3, 5)]
LOSS_DAYS = [dt.date(2021, 7, 14), dt.date(2022, 11, 9), dt.date(2023, 2, 8), dt.date(2024, 8, 21)]
HOLE_DAYS = [dt.date(2021, 5, 12), dt.date(2024, 3, 6)]
FLAT_DAYS = [dt.date(2022, 1, 5), dt.date(2023, 6, 7)]
OUTSIDE_DAYS = [dt.date(2020, 6, 10), dt.date(2025, 2, 12), dt.date(2026, 4, 8)]   # never in 2021-2024


def _contract(d: dt.date) -> str:
    return f"NQ{'HMUZ'[(d.month - 1) // 3]}{d.year % 10}"


def _win_day(d: dt.date) -> list[dict]:
    day = rows(ms(d, "09:25:00"), [100.0] * 290, step_ms=1000)                 # to 09:29:50
    day += rows(ms(d, "09:30:01"), [110.0, 112.0, 126.0], step_ms=1000)        # long fills, then TP
    return day + rows(ms(d, "09:31:00"), [120.0] * 1500, step_ms=15_000)       # to 15:45


def _loss_day(d: dt.date) -> list[dict]:
    day = rows(ms(d, "09:25:00"), [100.0] * 290, step_ms=1000)
    day += rows(ms(d, "09:30:01"), [110.0, 108.0, 104.0], step_ms=1000)        # long fills, then SL
    return day + rows(ms(d, "09:31:00"), [106.0] * 1500, step_ms=15_000)


def _flat_day(d: dt.date) -> list[dict]:
    return rows(ms(d, "09:25:00"), [100.0] * 1790, step_ms=15_000)             # neither stop is ever touched


def _hole_day(d: dt.date) -> list[dict]:
    return rows(ms(d, "09:25:00"), [100.0] * 1284, step_ms=10_000)             # prints stop at 12:59


def multiyear_archive(base):
    """Winners, losers, flat days and coverage holes across 2021-2024, plus sessions
    outside it (2020, 2025, 2026) so a range that reaches past 2024 has data to read."""
    for d in WIN_DAYS + OUTSIDE_DAYS:
        write_archive(base, "NQ", d, _contract(d), _win_day(d))
    for d in LOSS_DAYS:
        write_archive(base, "NQ", d, _contract(d), _loss_day(d))
    for d in FLAT_DAYS:
        write_archive(base, "NQ", d, _contract(d), _flat_day(d))
    for d in HOLE_DAYS:
        write_archive(base, "NQ", d, _contract(d), _hole_day(d))
    return base
