"""bpfeat -- the Level-2 feature table of the blueprint ranges (NQ), and the one-off build of its 2025 first half.

WHY A MODULE OF ITS OWN. The engine's own loader (l2sim.L2Features) stops at 2024-12-31 and refuses every switch string: its
seal is the old three-period law. The blueprint build range runs to 2025-06-30 (BLUEPRINT.md section 2), so the book filter blocks
need 2025-01-01 .. 2025-06-30 too. Nothing of l2sim.py or l2data.py is edited (the stores' code hashes stay valid); this module
adds the table's second half and a loader that carries the blueprint's own seal.

THE BUILD HALF   build_half(): l2data.build_features(IS_START, 2025-06-30, allow_holdout=True) -- the feature builder reads the
    vendor's depth and hist rows keyed up to the end of 2025-06-30 ET and no later (key_hi = the key of 2025-07-01 00:00) --
    keeps the rows of Globex sessions up to 2025-06-30 (the evening of 2025-06-30 belongs to the 2025-07-01 session: the first
    TEST day: its rows are cut) and writes cache/l2feat_NQ_2025.parquet. Features look backwards only, so a longer build later
    reproduces these rows (l2data docstring). The same call persists the snapshot-phase check of 2025-01 .. 2025-06 in
    cache/phase_guard.json: l2sim runs a failed month with the 1 s execution guard, and refuses a month that was never checked.
    An existing file is never overwritten (a bigger build is written by the test's own call, not by this one).
THE LOADER       BpL2Features(columns, switch): l2sim.L2Features with the blueprint switch (ALLOW_BP; the test days' switch is
    not opened by this module): every date goes through l2sim.check_holdout, so a date after the switch's range
    raises before a row is read, and the table it reads is cut at the range's end. Picklable (workers import it by name).
"""
from __future__ import annotations

import datetime as dt
import os

import pandas as pd

import l2data as D
import l2sim as S

BUILD_END = S.BP_BUILD[1]                           # 2025-06-30
BUILD_MONTHS = [f"2025-{m:02d}" for m in range(1, 7)]


def cache_file() -> "os.PathLike":
    return D.cache_path(2025)


def build_half(verbose: bool = True) -> dict:
    """Build cache/l2feat_NQ_2025.parquet for 2025-01-01 .. 2025-06-30 and persist the phase check of those months.
    -> {'path', 'rows', 'first', 'last', 'phase_failed'}. Refuses when the file exists."""
    p = cache_file()
    if p.exists():
        raise FileExistsError(f"{p} exists: it is never written over (a longer build is the test's own call)")
    ph = D.phase_check(BUILD_MONTHS, allow_holdout=True, raise_on_fail=False, persist=True, verbose=verbose)
    df = D.build_features(D.IS_START, BUILD_END, allow_holdout=True, verbose=verbose)
    df = df[df["globex_date"] <= BUILD_END]          # the evening of 2025-06-30 is the first TEST session's
    df = df[pd.DatetimeIndex(pd.to_datetime(df["date"])).year == 2025]       # 2021 .. 2024 stay as they are
    if not len(df) or df["date"].max() > BUILD_END or df["globex_date"].max() > BUILD_END:
        raise RuntimeError(f"the table reaches {df['date'].max()} / {df['globex_date'].max()}: nothing is written")
    tmp = p.with_name(p.name + f".{os.getpid()}.tmp")
    df.to_parquet(tmp, compression="zstd")
    os.replace(tmp, p)
    return {"path": str(p), "rows": int(len(df)), "first": str(df["date"].min()), "last": str(df["date"].max()),
            "phase_failed": ph["failed"]}


class BpL2Features(S.L2Features):
    """l2sim.L2Features for a blueprint range (module docstring). `switch` = S.ALLOW_BP; every date is sealed by
    l2sim.check_holdout under it, and the table is cut at the range's end."""

    def __init__(self, columns, switch=S.ALLOW_BP, lookback_min: int = 360):
        if switch != S.ALLOW_BP:
            raise S.HoldoutSealed(f"BpL2Features opens the blueprint BUILD range only (switch {S.ALLOW_BP!r}), not {switch!r}: the test days' "
                                  "table is built by the test's own call")
        self.columns, self.lookback_min, self.allow_holdout, self.mask = tuple(columns), int(lookback_min), switch, True

    def _frame(self):
        key = ("bp", self.columns)
        if key not in S._FRAMES:
            df = D.load_features(S.TABLE_START, BUILD_END, allow_holdout=True, columns=list(self.columns), mask_bad_book=True)
            S._FRAMES[key] = S.features_from_frame(df, self.columns)
        return S._FRAMES[key]

    def __repr__(self) -> str:                       # (a store's fingerprint is made of it)
        return f"BpL2Features({','.join(self.columns)}; {self.allow_holdout})"


if __name__ == "__main__":
    print(build_half())
