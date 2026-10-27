"""The 3:1 block walk-forward's fixed layout: the house-law dates and the block steps. Stdlib only and imports nothing of
homebase, so discipline, wfmonths and walkforward all import it at the top (it used to sit in those three, which imported
each other inside functions to dodge the loop). Each name is re-exported where it lived: discipline.HOLDOUT_START,
walkforward.steps, ... still work."""
from __future__ import annotations

import datetime as dt

RESEARCH_START = dt.date(2021, 9, 22)       # the build days: from the archive's first session ...
RESEARCH_END = dt.date(2025, 6, 30)
HOLDOUT_START = dt.date(2025, 7, 1)         # ... and the test days, from here to the latest data

SELECT_MONTHS = 1
TEST_MONTHS = 3            # the default OOS side of the ratio (1:3); 1 and 2 are the other choices
ROLL_SELECT = 3            # the 3:1 scheme (owner, 2026-10-18): select on 3 months, test the next 1 ...
ROLL_STEP = 4              # ... then the next block: BLOCKS, ALWAYS the default -- a month is in OR out (owner, 2026-10-18)
STEP_MONTHS = 1


def step_of(select_months: int, step_months: int | None = None) -> int:
    if select_months != ROLL_SELECT:
        return STEP_MONTHS
    return ROLL_STEP if step_months is None else step_months


def steps(months: list[str], test_months: int = TEST_MONTHS, select_months: int = SELECT_MONTHS,
          step_months: int | None = None) -> list[dict]:
    """Step k selects on months[k : k+select_months] and tests on the next `test_months`; a partial last
    window is dropped. `select` is the month ('2021-10'); at 3:1 it is the label '2021-10 → 2021-12' and
    `select_ms` holds the months, and the steps are BLOCKS (k = 0, 4, 8, ...: Jan-Mar -> Apr, May-Jul -> Aug)."""
    n = len(months) - select_months - test_months + 1
    out = []
    for k in range(0, max(n, 0), step_of(select_months, step_months)):
        sel = months[k:k + select_months]
        s = {"k": k, "select": sel[0], "test": months[k + select_months:k + select_months + test_months]}
        if len(sel) > 1:
            s.update(select=f"{sel[0]} → {sel[-1]}", select_ms=sel)
        out.append(s)
    return out
