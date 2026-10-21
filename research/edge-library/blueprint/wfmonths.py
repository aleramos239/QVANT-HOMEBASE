"""wfmonths.py -- THE MONTHS OF THE 3:1 BLOCK WALK-FORWARD (docs/superpowers/specs/2026-10-20-heatmap-40-and-fixed-box-walkforward-design.md 4.1).

Data: the market's sessions from its first WHOLE month to the last month its data runs past (a month counts when it is before
today's month and the market has a used -- complete -- session after its last day: a fresh month's still-filling days never
count it). A GAPPY DAY IS SKIPPED (the owner, 2026-10-21:
"Skip those days"): from 2025-07-01 on, a session whose front-contract manifest is not `complete` (runner._front) -- or, NQ, that has
no tape the engine can replay (its ofb_tick parquet or the Lab's .tape, load_tape's lookup) -- is in no in-sample and no out-of-sample
day list and the switches refuse it; its month still counts. Blocks: 3 in-sample months, then
1 out-of-sample month, the next block starts after it (Oct-Dec 2021 -> Jan 2022, Feb-Apr -> May, ...). Every month is in-sample or
out-of-sample, never both; the partial first month, the month under way and a trailing part-block are in no block.

  calendar(root)          -> ISO session dates of the whole months (file names and manifests only: no tape is opened)
  blocks(root, last=None) -> [{"i", "is": [3 months], "oos": month}]   (last = the last whole month to use; default the calendar's)
  is_days(root)           -> the session dates of every in-sample month
  oos_days(root, month)   -> the session dates of ONE out-of-sample month
  month_sets(root)        -> (in-sample months, out-of-sample months), memoised: what the engine's switches open
  skipped(root)           -> the ISO dates of the gappy sessions the walk-forward skips

The engine's switches (l2sim.ALLOW_WF_IS / ALLOW_WF_OOS) open exactly these months, less the skipped days."""
from __future__ import annotations

import datetime as dt
import functools
import os

import l2sim as S

from . import pipe_wf as WF


@functools.lru_cache(maxsize=None)
def _sessions(root: str, today: str) -> tuple:
    """(the sessions the walk-forward uses, the last of them, the skipped sessions)."""
    from . import runner as RUN
    build = [d.isoformat() for d in S.sessions(*S.BP_BUILD, root, allow_holdout=S.ALLOW_BP)]
    end = dt.date.fromisoformat(today)
    done = RUN._front(root, S.BP_BUILD[1] + dt.timedelta(days=1))   # {date: complete} by the front contract's manifest, after the build days
    seen = sorted(d for d in done if d <= end)      # (every tape is built from an archive session: its manifest names it)
    use = [d for d in seen if done.get(d) and (root != "NQ" or S.tape_path(d, root).exists() or S.hb_tape_path(d, root) is not None)]
    days = build + [d.isoformat() for d in use]
    return tuple(days), max(days, default=None), frozenset(d.isoformat() for d in seen) - set(days)


def calendar(root: str) -> list:
    today = dt.date.today().isoformat()
    days, last, _ = _sessions(root, today)
    cut = min(today[:7], (last or today)[:7])       # a month counts only when a used session follows it
    return [d for d in days if d[:7] < cut]


def skipped(root: str) -> frozenset:
    return _sessions(root, dt.date.today().isoformat())[2]


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
