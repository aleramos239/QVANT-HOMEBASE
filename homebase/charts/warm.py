"""Warm the chart service's 1-minute bar cache ahead of time, so a deep
scroll-back or a 250-session daily chart never waits on raw ticks:

    python -m homebase.charts.warm --roots NQ,ES --since 2021-09-22

For every COMPLETED session of each root in the tick archive (today's is
still being written), build the per-session 1-minute pickle the charts
resample from, skipping sessions already built and current. Read-only on the
archive (~/futures_ticks); writes only the cache (<state>/charts/cache).
Not scheduled: run it by hand.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

from . import DEFAULT_ROOTS
from .history import History
from .session import session_date
from .store import ARCHIVE, TickStore


def warm(roots, since: dt.date | None = None, *, base: Path = ARCHIVE, cache_dir: Path | None = None,
         today: dt.date | None = None, out=print) -> dict:
    """Build each missing or stale 1-minute cache; {"built": n, "skipped": m}. cache_dir None: the service's."""
    history = History(TickStore(base), cache_dir=cache_dir)
    built = skipped = 0
    for root in roots:
        last = today or session_date(int(time.time() * 1000), root)
        dates = [d for d in history.store.sessions(root) if d < last and (since is None or d >= since)]
        for i, d in enumerate(dates, 1):
            if history.cached(root, d):
                skipped += 1
                continue
            t0 = time.monotonic()
            n = len(history.minutes(root, d))
            built += 1
            out(f"{root} {d.isoformat()}: {n} one-minute bars in {time.monotonic() - t0:.1f}s ({i}/{len(dates)})")
        out(f"{root}: {len(dates)} sessions checked")
    return {"built": built, "skipped": skipped}


def parse_args(argv):
    p = argparse.ArgumentParser(prog="python -m homebase.charts.warm",
                                description="Build the charts' 1-minute bar cache ahead of time.")
    p.add_argument("--roots", default=list(DEFAULT_ROOTS),
                   type=lambda s: [r.strip().upper() for r in s.split(",") if r.strip()],
                   help="comma-separated roots (default: the chart service's)")
    p.add_argument("--since", type=dt.date.fromisoformat, default=None,
                   help="the first session, YYYY-MM-DD (default: the archive's first)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    a = parse_args(sys.argv[1:] if argv is None else argv)
    r = warm(a.roots, a.since)
    print(f"done: {r['built']} built, {r['skipped']} already current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
