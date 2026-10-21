"""wfmonths.py -- THE MONTHS OF THE 3:1 BLOCK WALK-FORWARD (docs/superpowers/specs/2026-10-20-heatmap-40-and-fixed-box-walkforward-design.md 4.1).

Data: the market's sessions from its first WHOLE month to the last month its complete sessions run past (the month of the first
session that is not complete -- runner.test_range "stops" -- and the month under way are out). Blocks: 3 in-sample months, then
1 out-of-sample month, the next block starts after it (Oct-Dec 2021 -> Jan 2022, Feb-Apr -> May, ...). Every month is in-sample or
out-of-sample, never both; the partial first month, the month under way and a trailing part-block are in no block.

  calendar(root)          -> ISO session dates of the whole months (file names and manifests only: no tape is opened)
  blocks(root, last=None) -> [{"i", "is": [3 months], "oos": month}]   (last = the last whole month to use; default the calendar's)
  is_days(root)           -> the session dates of every in-sample month
  oos_days(root, month)   -> the session dates of ONE out-of-sample month
  month_sets(root)        -> (in-sample months, out-of-sample months), memoised: what the engine's switches open

The engine's switches (l2sim.ALLOW_WF_IS / ALLOW_WF_OOS) open exactly these months."""
from __future__ import annotations

import datetime as dt
import functools
import os

import l2sim as S

from . import pipe_wf as WF


@functools.lru_cache(maxsize=None)
def _sessions(root: str, today: str) -> tuple:
    """(the session dates, the first session that is not complete or None)."""
    from . import runner as RUN
    from . import taught_wf as TW                   # its _test_days = the test days of the complete sessions, before today's month
    build = [d.isoformat() for d in S.sessions(*S.BP_BUILD, root, allow_holdout=S.ALLOW_BP)]
    return tuple(build + TW._test_days(root, dt.date.fromisoformat(today))), RUN.test_range(root)["stops"]


def calendar(root: str) -> list:
    today = dt.date.today().isoformat()
    days, stops = _sessions(root, today)
    cut = min(today[:7], (stops or today)[:7])      # a month counts only when the complete sessions run past it
    return [d for d in days if d[:7] < cut]


def _whole(first: str) -> bool:
    """A first session on the month's first or second weekday (one holiday, as Jan 1) = a whole month."""
    d = dt.date.fromisoformat(first)
    return sum(dt.date(d.year, d.month, k).weekday() < 5 for k in range(1, d.day + 1)) <= 2


PIN_ENV = "HOMEBASE_WF_LAST"                       # a fixed last test month (YYYY-MM) for a hunt that must not grow mid-way (2026-10-21)


def blocks(root: str, last: str | None = None) -> list:
    last = last or os.environ.get(PIN_ENV) or None
    cal = calendar(root)
    ms = WF.months(cal)
    if ms and ms[0] == min(cal)[:7] and not _whole(min(cal)):    # months() keeps a month that starts on its 3rd..7th: not whole here
        ms = ms[1:]
    ms = [m for m in ms if last is None or m <= last]
    picks = WF.walk({}, [], ms, 3, 0, "9999-12", step=4)["picks"]   # the layout only: no box, no pick
    return [{"i": i, "is": p["window"], "oos": p["month"]} for i, p in enumerate(picks)]


@functools.lru_cache(maxsize=None)
def _sets(root: str, today: str, pin=None) -> tuple:
    bl = blocks(root)
    return frozenset(m for b in bl for m in b["is"]), frozenset(b["oos"] for b in bl)


def month_sets(root: str) -> tuple:
    return _sets(root, dt.date.today().isoformat(), os.environ.get(PIN_ENV) or None)


def is_days(root: str) -> list:
    ms = month_sets(root)[0]
    return [d for d in calendar(root) if d[:7] in ms]


def oos_days(root: str, month: str) -> list:
    if month not in month_sets(root)[1]:
        raise ValueError(f"{month} is not a test month of the {root} blocks")
    return [d for d in calendar(root) if d[:7] == month]
