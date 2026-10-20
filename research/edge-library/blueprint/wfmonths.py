"""wfmonths.py -- THE MONTHS OF THE 3:1 BLOCK WALK-FORWARD (docs/superpowers/specs/2026-10-20-heatmap-40-and-fixed-box-walkforward-design.md 4.1).

Data: the market's sessions from its first WHOLE month to the last whole month of its complete sessions. Blocks: 3 in-sample months, then
1 out-of-sample month, the next block starts after it (Oct-Dec 2021 -> Jan 2022, Feb-Apr -> May, ...). Every month is in-sample or
out-of-sample, never both; the partial first month, the month under way and a trailing part-block are in no block.

  calendar(root)          -> ISO session dates (file names only: no tape is opened)
  blocks(root, last=None) -> [{"i", "is": [3 months], "oos": month}]   (last = the last whole month to use; default the calendar's)
  is_days(root)           -> the session dates of every in-sample month
  oos_days(root, month)   -> the session dates of ONE out-of-sample month

The engine's switches (l2sim.ALLOW_WF_IS / ALLOW_WF_OOS) open exactly these months."""
from __future__ import annotations

import datetime as dt
import functools

import l2sim as S

from . import pipe_wf as WF


@functools.lru_cache(maxsize=None)
def _calendar(root: str, today: str) -> tuple:
    from . import taught_wf as TW                   # its _test_days = the test days to the last WHOLE month of the complete sessions
    build = [d.isoformat() for d in S.sessions(*S.BP_BUILD, root, allow_holdout=S.ALLOW_BP)]
    return tuple(build + TW._test_days(root, dt.date.fromisoformat(today)))


def calendar(root: str) -> list:
    return list(_calendar(root, dt.date.today().isoformat()))


def _whole(first: str) -> bool:
    """A first session on the month's first or second weekday (one holiday, as Jan 1) = a whole month."""
    d = dt.date.fromisoformat(first)
    return sum(dt.date(d.year, d.month, k).weekday() < 5 for k in range(1, d.day + 1)) <= 2


def blocks(root: str, last: str | None = None) -> list:
    cal = calendar(root)
    ms = WF.months(cal)
    if ms and ms[0] == min(cal)[:7] and not _whole(min(cal)):    # months() keeps a month that starts on its 3rd..7th: not whole here
        ms = ms[1:]
    ms = [m for m in ms if last is None or m <= last]
    picks = WF.walk({}, [], ms, 3, 0, "9999-12", step=4)["picks"]   # the layout only: no box, no pick
    return [{"i": i, "is": p["window"], "oos": p["month"]} for i, p in enumerate(picks)]


def is_days(root: str) -> list:
    ms = {m for b in blocks(root) for m in b["is"]}
    return [d for d in calendar(root) if d[:7] in ms]


def oos_days(root: str, month: str) -> list:
    if month not in {b["oos"] for b in blocks(root)}:
        raise ValueError(f"{month} is not a test month of the {root} blocks")
    return [d for d in calendar(root) if d[:7] == month]
