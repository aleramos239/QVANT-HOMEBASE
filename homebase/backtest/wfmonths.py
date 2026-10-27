"""The months of the 3:1 block walk-forward, from the tester's own data (the layout of research/edge-library/blueprint/wfmonths.py).

Data: the market's archived sessions from its first WHOLE month (its first session on the month's 1st or 2nd weekday) to the
last month the data runs past (a month counts when it is before today's month and the market has a complete session after its
last day: a fresh month's still-filling days never count it). A GAPPY DAY IS SKIPPED (the owner, 2026-10-21: "Skip those days"): a session from 2025-07-01 on whose
front-contract manifest is not `complete` is in no in-sample and no test day list (Range.includes refuses it); its month still
counts. Blocks: 3 in-sample months, then 1 out-of-sample month, the next block
after it (Oct-Dec 2021 -> Jan 2022, Feb-Apr -> May, ...); a trailing part-block is in no block. File names and manifests
only: no tape is opened. tests/test_wfmonths_parity.py checks it against the research module.

  calendar(root, store=None) -> the session dates of the whole months, less the skipped ones
  skipped(root, store=None)  -> the gappy sessions the walk-forward skips
  blocks(root, store=None)   -> [{"i", "is": [3 months], "oos": month}]
"""
from __future__ import annotations

import datetime as dt
import functools
import json

from .tape import TapeStore
from .wflayout import HOLDOUT_START, RESEARCH_START, steps      # steps: the Lab's own 3:1 block layout (select 3, test 1, step 4)


def _complete(store: TapeStore, root: str, d: dt.date) -> bool:
    """The `complete` flag of the session's front contract (the manifest with the most ticks: TapeStore.pick's rule)."""
    best = (-1, False)
    for man in store.manifests(root, d):
        try:
            m = json.loads(man.read_text())
            n = int(m.get("ticks") or 0)
        except (OSError, ValueError, TypeError, AttributeError):
            continue
        if n > best[0]:
            best = (n, m.get("complete") is True)
    return best[1]


@functools.lru_cache(maxsize=None)
def _calendar(root: str, archive: str, today: str) -> tuple:
    """(the used session dates of the whole months, the skipped sessions)."""
    store = TapeStore(archive=archive)
    with store.listing():                           # each year folder listed once, not once a session
        days = store.sessions(root, RESEARCH_START, dt.date.fromisoformat(today))
        bad = frozenset(d for d in days if d >= HOLDOUT_START and not _complete(store, root, d))
    use = [d for d in days if d not in bad]
    cut = min(today[:7], use[-1].isoformat()[:7] if use else today[:7])     # a month counts only when a complete session follows it
    return tuple(d for d in use if d.isoformat()[:7] < cut), bad


def _scan(root: str, store: TapeStore | None) -> tuple:
    return _calendar(root, str((store or TapeStore()).archive), dt.date.today().isoformat())


def calendar(root: str, store: TapeStore | None = None) -> list:
    return list(_scan(root, store)[0])


def skipped(root: str, store: TapeStore | None = None) -> frozenset:
    return _scan(root, store)[1]


def _whole(first: dt.date) -> bool:
    """A first session on the month's first or second weekday (one holiday, as Jan 1) = a whole month."""
    return sum(dt.date(first.year, first.month, k).weekday() < 5 for k in range(1, first.day + 1)) <= 2


def blocks(root: str, store: TapeStore | None = None) -> list:
    cal = calendar(root, store)
    ms = sorted({d.isoformat()[:7] for d in cal})
    if ms and not _whole(cal[0]):
        ms = ms[1:]
    return [{"i": i, "is": s["select_ms"], "oos": s["test"][0]} for i, s in enumerate(steps(ms, 1, 3))]
