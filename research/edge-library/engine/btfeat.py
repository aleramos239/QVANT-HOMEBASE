"""btfeat -- the Level-2 feature table of the blueprint TEST days (NQ), its one-off build, and its loader with the TEST seal.

WHY A MODULE OF ITS OWN. bpfeat.py holds the table of the build days (to 2025-06-30) and carries the BUILD seal; it never names
the test switch. The test days (2025-07-01 .. the vendor's last session) need a table too, or a locked idea with a Level-2 filter
cannot be tested. This module is that table's builder and its loader, and the ONE place outside the engine and blueprint/runner.py
that names the test switch (l2sim.ALLOW_BT): the loader below carries it. Nothing of l2sim.py or l2data.py is edited (the stores'
code hashes stay valid); the feature definitions are l2data.build_features, called as bpfeat calls it.

THE TABLE   cache/l2feat_NQ_test.parquet: every row of the Globex sessions 2025-07-01 .. last_complete_session(), i.e. from the
    evening of 2025-06-30 (18:00 ET, the first test session's own evening rows) to the last session the vendor's depth file
    covers (its last stamp is 2026-07-07 15:59 ET: the file chain ends 2026-07-08). The build half (bpfeat) holds the sessions up
    to 2025-06-30; the two files split at the session date and share no row. Beside it: cache/l2feat_NQ_test.meta.json (first and
    last date, rows, months that failed the snapshot-phase check, how it was made).
THE BUILD   build_test(): (1) the snapshot-phase check of the months 2025-07 .. the last month, persisted in cache/phase_guard.json
    exactly as bpfeat.build_half persists the 2025 first half (l2sim runs a failed month with the 1 s execution guard and refuses a
    month that was never checked); (2) l2data.build_features(IS_START, end, allow_holdout=True) -- one continuous history from the
    first tape session, so the trailing windows are warm and every row is the row a build over any longer range would give; (3) the
    rows of the sessions >= 2025-07-01 are written. An existing file is never overwritten. Features look backwards only (l2data
    docstring: a longer build reproduces a shorter one row for row; only the hindsight masks `in_tape` / `ofb_mismatch`, which look up
    to 32 minutes ahead, may differ in the last minutes of a build's end): verify_end_independent() compares two builds of different
    ends. Building a table is infrastructure: it runs no strategy and computes no performance of any day.
THE LOADER  BtL2Features(columns, switch=ALLOW_BT): l2sim.L2Features with the blueprint TEST switch. Every date goes through
    l2sim.check_holdout under it, so a date before 2025-07-01 raises before a row is read (the build days are never opened by it),
    a date after the table's last date raises too (there is no row to read; the frozen test range ends at last_date()), and the
    only file it reads is the test table. Picklable (workers import it by name).
ONE CALLER  Like the switch itself, this loader is built by blueprint/runner.run_test and nowhere else (a test pins it).
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pandas as pd

import l2data as D
import l2sim as S

TEST_START = S.BP_TEST_START                          # 2025-07-01: the first session of the table
VENDOR_END = dt.date(2026, 7, 8)                      # the vendor's Level-2 history ends here (the file chain's name)
RTH_LAST = 1559                                       # the last stamp of a complete session in the depth file (15:59 ET)
TABLE_NAME = "l2feat_NQ_test.parquet"
META_NAME = "l2feat_NQ_test.meta.json"


def cache_file() -> Path:
    return D.CACHE / TABLE_NAME


def meta_file() -> Path:
    return D.CACHE / META_NAME


def last_complete_session(files=None) -> dt.date:
    """The last Globex session the vendor's depth file chain covers completely: the ET date of its last stamp when that stamp is the
    session's 15:59 (a day cut earlier is incomplete: the session before it is the last), never later than VENDOR_END. Stamps only
    (no market row is read). The 2026-07-08 session has no depth row at all: the chain ends 2026-07-07 15:59."""
    last = 0
    for f in (files if files is not None else D.ofb_files("depth", True)):
        bf = D.BinFile(f, "depth", True)
        if bf.count:
            last = max(last, bf.key(bf.count - 1))
    if not last:
        raise FileNotFoundError("the vendor's depth files are empty")
    ymd, hhmm = last // 10**6, last // 100 % 10000
    d = dt.date(ymd // 10000, ymd // 100 % 100, ymd % 100)
    if hhmm < RTH_LAST:
        d -= dt.timedelta(days=1)
    return min(d, VENDOR_END)


def test_months(end: dt.date) -> list:
    return [str(m) for m in pd.period_range(TEST_START, end, freq="M")]


def build_test(end=None, verbose: bool = True, path=None, phase: bool = True, wait: bool = True) -> dict:
    """Build cache/l2feat_NQ_test.parquet (+ its meta file) for the sessions 2025-07-01 .. `end` (default last_complete_session()) and
    persist the phase check of those months. -> {'path', 'rows', 'first', 'last', 'phase_failed', ...}. Refuses when the file exists.
    `path` / `phase=False` / `wait=False`: tests and the end-independence check write elsewhere, skip the persisted check and the
    compute-window wait; the real build uses none of them."""
    p = Path(path) if path is not None else cache_file()
    if p.exists():
        raise FileExistsError(f"{p} exists: it is never written over")
    end = last_complete_session() if end is None else D._as_date(end)
    if end < TEST_START or end > VENDOR_END:
        raise ValueError(f"end {end}: the table covers {TEST_START} .. {VENDOR_END} at most")
    if wait:
        S.wait_compute_window()
    months = test_months(end)
    ph = D.phase_check(months, allow_holdout=True, raise_on_fail=False, persist=True, verbose=verbose) if phase else {"failed": []}
    if wait:
        S.wait_compute_window()
    df = D.build_features(D.IS_START, end, allow_holdout=True, verbose=verbose)
    df = df[(df["globex_date"] >= TEST_START) & (df["globex_date"] <= end)]    # up to 2025-06-30: the build half's (bpfeat); the evening of
    #                                                                              `end` belongs to the next session: cut, as bpfeat cuts it
    if not len(df) or df["globex_date"].min() < TEST_START or df["date"].max() > end or df["globex_date"].max() > end:
        raise RuntimeError(f"the table reaches {df['date'].min()} .. {df['date'].max()} / sessions {df['globex_date'].min()} .. "
                           f"{df['globex_date'].max()}: nothing is written")
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".{os.getpid()}.tmp")
    df.to_parquet(tmp, compression="zstd")
    os.replace(tmp, p)
    out = {"path": str(p), "rows": int(len(df)), "first": str(df["date"].min()), "last": str(df["date"].max()),
           "first_session": str(df["globex_date"].min()), "last_session": str(df["globex_date"].max()), "end": str(end),
           "months": months, "phase_failed": list(ph["failed"]), "rows_book_ok": int(df["book_ok"].sum()),
           "built_et": pd.Timestamp.now(tz=D.ET).isoformat(timespec="seconds")}
    if path is None:
        m = meta_file()
        tmpm = m.with_name(m.name + f".{os.getpid()}.tmp")
        tmpm.write_text(json.dumps({**out, "path": p.name}, indent=1))     # (the file's name, not the checkout's path)
        os.replace(tmpm, m)
    return out


def verify_end_independent(a: pd.DataFrame, b: pd.DataFrame, tail_min: int = 40) -> dict:
    """Do two builds of different ends agree row for row? `a` = the shorter, `b` = the longer table (same start). Rows of `b` up to
    a's last row must equal a's, column for column (NaN = NaN), except the hindsight masks `ofb_mismatch` / `book_ok` / `in_tape` and
    the features computed on top of them in the last `tail_min` minutes of `a` (their window looks up to 32 minutes ahead).
    -> {'rows', 'checked', 'differing': {column: n rows}}; an empty `differing` = independent."""
    cut = a.index.max()
    b = b[b.index <= cut]
    if not a.index.equals(b.index):
        return {"rows": len(a), "checked": 0, "differing": {"<index>": abs(len(a) - len(b)) or 1}}
    keep = a.index <= cut - pd.Timedelta(minutes=tail_min)
    diff = {}
    for c in a.columns:
        x, y = a.loc[keep, c], b.loc[keep, c]
        same = (x == y) | (x.isna() & y.isna())
        if not bool(same.all()):
            diff[c] = int((~same).sum())
    return {"rows": len(a), "checked": int(keep.sum()), "differing": diff}


def meta() -> dict:
    """The meta file of the table ({} when it is not built)."""
    m = meta_file()
    return json.loads(m.read_text()) if m.exists() else {}


_LAST: dict = {}


def last_date() -> dt.date:
    """The last ET date of the test table (the end of a frozen test range of a Level-2 idea). FileNotFoundError when the table is not
    built. Read from the table's `date` column (cached per process)."""
    p = cache_file()
    if not p.exists():
        raise FileNotFoundError(f"the test days' Level-2 table {p.name} is not built (python engine/btfeat.py)")
    key = (str(p), p.stat().st_mtime_ns)
    if key not in _LAST:
        d = pd.read_parquet(p, columns=["date"])["date"]
        _LAST.clear()
        _LAST[key] = D._as_date(d.max())
    return _LAST[key]


class TestTableEnds(RuntimeError):
    """A date after the last day the test table covers: there is no Level-2 row to read there."""


class BtL2Features(S.L2Features):
    """l2sim.L2Features for the blueprint TEST range (module docstring). `switch` = S.ALLOW_BT; every date is sealed by
    l2sim.check_holdout under it (before 2025-07-01 raises) and by the table's last date; the rows are the test table's alone."""

    __test__ = False                                  # (not a pytest class)

    def __init__(self, columns, switch=S.ALLOW_BT, lookback_min: int = 360):
        if not (isinstance(switch, str) and switch == S.ALLOW_BT):
            raise S.HoldoutSealed(f"BtL2Features opens the blueprint TEST range only (switch {S.ALLOW_BT!r}), not {switch!r}: the build "
                                  "days' table is bpfeat's")
        self.columns, self.lookback_min, self.allow_holdout, self.mask = tuple(columns), int(lookback_min), switch, True

    def _frame(self):
        key = ("bt", self.columns)
        if key not in S._FRAMES:
            cols = list(dict.fromkeys(list(self.columns) + ["date", "book_ok"]))
            df = pd.read_parquet(cache_file(), columns=cols)
            if len(df) and (df["date"].min() < TEST_START - dt.timedelta(days=1)):
                raise S.HoldoutSealed("the test table holds a row before the test range: it is not read")
            bad = ~df["book_ok"].to_numpy()               # l2data.load_features(mask_bad_book=True), on this file
            for c in df.columns:
                if c in D.BOOK_COLS or c in D.PX_COLS or c in D.RT_COLS:
                    df[c] = df[c].where(~bad)
            S._FRAMES[key] = S.features_from_frame(df, self.columns)
        return S._FRAMES[key]

    def __call__(self, d):
        d = S._date(d)
        S.check_holdout(d, self.allow_holdout)            # before 2025-07-01: raises, before any row is read
        end = last_date()
        if d > end:
            raise TestTableEnds(f"{d} is after the last day of the test days' Level-2 table ({end}): the frozen test range of a "
                                "Level-2 idea ends there")
        return super().__call__(d)

    def __repr__(self) -> str:                        # (a store's fingerprint is made of it)
        return f"BtL2Features({','.join(self.columns)}; {self.allow_holdout})"


if __name__ == "__main__":
    print(json.dumps(build_test(), indent=1))
