"""relcandle -- THE RELEASE CANDLE OF A DATA-RELEASE DAY, written down once (owner 2026-10-15: "the second of CPI / PPI bursts the way the
first one did"). The open layer's `rel_dir` reads it for the FIRST release of a week to say which side the SECOND release may trade.

  candle    = price just BEFORE the release (the last print at or before 08:30:00 ET) -> the last print at or before 08:30:00 + m minutes
              (m = 1, 5, 15 or 30). Its direction is the sign of the move: up +1, down -1, no change 0. No tape that day: None.
  where     cache/relcandle_<ROOT>.npz, one row a calendar date: `p0` and `p1 p5 p15 p30` (NaN = the day has no tape). A family run reads
            the FILE ONLY, never a tape of another day, so a run needs no seal switch of its own for a first-release day.
  filling   `build(root, dates, allow_holdout=...)` loads each date's tape under the seal switch it is given (the blueprint BUILD switch
            ALLOW_BP stops at 2025-06-30; a later date raises HoldoutSealed) and merges the rows into the file. Nothing else writes it.
  missing   a date the file does not hold RAISES RelCandleMissing (a code problem, never a quiet "no trade": the unseen days would read as a
            fail). A date the file holds with no tape is a known gap: the direction is None and the day is not traded.

  python -I engine/relcandle.py NQ 2021-09-22 2025-06-30     fills every CPI / PPI date of the range (the BUILD days) from the tapes
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import sys
from pathlib import Path

import numpy as np

MINUTES = (1, 5, 15, 30)
_COLS = ("p0",) + tuple(f"p{m}" for m in MINUTES)
_MEM: dict = {}                                       # root -> (mtime, {iso: {col: float}})


class RelCandleMissing(KeyError):
    """The date has no row in the release-candle file (build it, from the build days only)."""


def _path(root: str) -> Path:
    import l2sim as S
    return S.CACHE / f"relcandle_{root}.npz"


def _read(root: str) -> dict:
    p = _path(root)
    m = p.stat().st_mtime_ns if p.exists() else 0
    if root not in _MEM or _MEM[root][0] != m:
        rows: dict = {}
        if m:
            z = np.load(p)
            for i, d in enumerate(z["dates"].tolist()):
                rows[d] = {c: float(z[c][i]) for c in _COLS}
        _MEM[root] = (m, rows)
    return _MEM[root][1]


def candle_of(tape, minutes=MINUTES) -> dict:
    """{col: price} of one tape: the last print at or before 08:30:00 and at or before 08:30:00 + m minutes (NaN: none)."""
    import l2sim as S
    t0 = S.et_ns(tape.date, "08:30")
    out = {}
    for col, t in (("p0", t0), *((f"p{m}", t0 + m * 60 * 1_000_000_000) for m in minutes)):
        k = int(np.searchsorted(tape.ts, t, side="right")) - 1
        out[col] = float(tape.px[k]) if k >= 0 else float("nan")
    return out


def direction(root: str, iso: str, minutes: int):
    """+1 / -1 / 0 (no change) of the release candle of `iso`; None when that day has no tape. Raises RelCandleMissing."""
    if minutes not in MINUTES:
        raise ValueError(f"rel_min {minutes!r}: one of {MINUTES}")
    row = _read(root).get(iso)
    if row is None:
        raise RelCandleMissing(f"{root} {iso}: no release candle in {_path(root).name} -- build it: python -I engine/relcandle.py {root} <from> <to> "
                               "(build days only)")
    a, b = row["p0"], row[f"p{minutes}"]
    if np.isnan(a) or np.isnan(b):
        return None
    return 1 if b > a else -1 if b < a else 0


def release_dates(start: str, end: str, types=("CPI", "PPI")) -> list:
    """The 08:30 CPI / PPI dates of [start, end] (cache/events.csv)."""
    import flexind as FI
    with FI.EVENTS.open(newline="") as fh:
        return sorted({r["date"] for r in csv.DictReader(fh) if r["type"] in types and r["time_et"] == "08:30" and start <= r["date"] <= end})


def build(root: str, dates, allow_holdout=None) -> dict:
    """Fill the rows of `dates` (ISO) from their tapes under `allow_holdout` (default: the blueprint BUILD switch) -> {'path', 'rows', 'added'}."""
    import l2sim as S
    allow = S.ALLOW_BP if allow_holdout is None else allow_holdout
    have = {d: dict(r) for d, r in _read(root).items()}
    added = 0
    for iso in dates:
        if iso in have:
            continue
        tape = S.load_tape(iso, root, allow_holdout=allow)          # a date past the switch's range raises HoldoutSealed
        have[iso] = candle_of(tape) if tape is not None and len(tape.ts) else {c: float("nan") for c in _COLS}
        added += 1
    p = _path(root)
    if added:
        ds = sorted(have)
        tmp = p.with_name(f".{p.stem}.{os.getpid()}.tmp.npz")
        np.savez_compressed(tmp, dates=np.array(ds), **{c: np.array([have[d][c] for d in ds], float) for c in _COLS})
        os.replace(tmp, p)
        _MEM.pop(root, None)
    return {"path": str(p), "rows": len(have), "added": added}


if __name__ == "__main__":
    root, a, b = sys.argv[1:4]
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    print(build(root, release_dates(a, b)))
