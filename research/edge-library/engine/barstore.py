"""barstore -- ready-made time bars of every market, so a study never rebuilds them from ticks.

FILES   ~/futures_derived/homebase_bars/<ROOT>/<tf>.parquet, tf in TFS (15s 30s 1m 3m 5m 15m 30m 1h 4h): one row per bar that
        has prints -- session (trade date, ISO), t (bar start, ns UTC), o h l c, v. Built from the tester's own tape cache
        (~/futures_derived/homebase_tape: the prints a backtest replays). Bars are anchored at the session open, 18:00 ET, like
        the chart and TradingView (a 4h bar is 18-22, 22-02, ...); for 1h and shorter that is also the engines' build_bars grid.
SEAL    load() hands out only the days the engine would open under `allow` (default: the 3:1 in-sample months, without the days
        the walk-forward skips). Read bars through load(), never the files: they hold every day, test months too.
FRESH   load() first rebuilds any session whose tape is new or changed since the last build (a repaired day), so the files follow
        the tape cache by themselves. `python barstore.py build [ROOT ...]` builds ahead of time (every root by default).

    import barstore as B
    df = B.load("NQ", "15m")                       # in-sample months only
    df["et"] = pd.to_datetime(df.t, utc=True).dt.tz_convert("America/New_York")
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

import numpy as np

import l2sim as S

BARS = Path.home() / "futures_derived" / "homebase_bars"
SEC = 1_000_000_000
TFS = {"15s": 15 * SEC, "30s": 30 * SEC, "1m": 60 * SEC, "3m": 180 * SEC, "5m": 300 * SEC, "15m": 900 * SEC,
       "30m": 1800 * SEC, "1h": 3600 * SEC, "4h": 14400 * SEC}
COLS = ["session", "t", "o", "h", "l", "c", "v"]


def session_open_ns(d: dt.date) -> int:
    """18:00 ET of the evening before trade date d, ns UTC."""
    return int(dt.datetime.combine(d - dt.timedelta(days=1), dt.time(18), S.ET).timestamp()) * SEC


def bars(ts, px, size, anchor: int, step: int) -> tuple:
    """(t, o, h, l, c, v) arrays of the `step`-ns bars of prints in tape order, buckets counted from `anchor`; empty buckets make no bar."""
    if not len(ts):
        return tuple(np.zeros(0, x) for x in (np.int64, np.float64, np.float64, np.float64, np.float64, np.int64))
    k = (ts - anchor) // step
    st = np.flatnonzero(np.concatenate(([True], k[1:] != k[:-1])))
    en = np.concatenate((st[1:], [len(ts)])) - 1
    return (anchor + k[st] * step, px[st], np.maximum.reduceat(px, st), np.minimum.reduceat(px, st), px[en],
            np.add.reduceat(size.astype(np.int64), st))


def _paths(root: str):
    d = BARS / root
    return d, d / "_built.json", {tf: d / f"{tf}.parquet" for tf in TFS}


def update(root: str) -> dict:
    """Rebuild the bars of every session of `root` whose tape file is new or changed (or gone) since the last build -> counts."""
    import pandas as pd
    d, man_p, files = _paths(root)
    tapes = {p.name[:10]: p for p in (S.HB_TAPE / root).glob("*.tape")}
    stamp = {}
    for iso, p in tapes.items():
        st = p.stat()
        stamp[iso] = [st.st_mtime_ns, st.st_size]
    man = json.loads(man_p.read_text()) if man_p.exists() else {}
    if any(not f.exists() for f in files.values()):
        man = {}
    todo = sorted(iso for iso in stamp if man.get(iso) != stamp[iso])
    redo = set(todo) | (set(man) - set(stamp))
    if not redo:
        return {"root": root, "built": 0, "sessions": len(man)}
    new = {tf: [] for tf in TFS}
    for iso in todo:
        day = dt.date.fromisoformat(iso)
        tape = S.read_hb_tape(tapes[iso], root, day)
        if tape is None:                            # not a tape of this root / byte order: no bars, but not retried every load
            continue
        a = session_open_ns(day)
        for tf, step in TFS.items():
            t, o, h, l, c, v = bars(tape.ts, tape.px, tape.size, a, step)
            new[tf].append(pd.DataFrame({"session": iso, "t": t, "o": o, "h": h, "l": l, "c": c, "v": v}))
    d.mkdir(parents=True, exist_ok=True)
    for tf, f in files.items():
        old = pd.read_parquet(f) if f.exists() and man else None
        parts = ([old[~old.session.isin(redo)]] if old is not None else []) + new[tf]
        df = (pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=COLS)).sort_values("t", kind="mergesort")
        tmp = f.with_name(f".{f.stem}.{os.getpid()}.tmp.parquet")
        df.to_parquet(tmp, index=False)
        os.replace(tmp, f)
    tmp = man_p.with_name(f".{man_p.stem}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(stamp))
    os.replace(tmp, man_p)                          # last: a crash before this redoes the same sessions next time
    return {"root": root, "built": len(todo), "sessions": len(stamp)}


def load(root: str, tf: str, allow=S.ALLOW_WF_IS, start=None, end=None, fresh: bool = True):
    """The `tf` bars of `root` as a DataFrame (COLS), only the sessions the engine opens under `allow` (l2sim.check_holdout:
    default the 3:1 in-sample months; S.ALLOW_WF_OOS opens ONE out-of-sample month, give start/end inside it), optionally
    limited to sessions in [start, end] (ISO dates). fresh=True first brings the files up to date with the tape cache."""
    import pandas as pd
    if tf not in TFS:
        raise ValueError(f"tf must be one of {', '.join(TFS)}")
    if fresh:
        update(root)
    f = _paths(root)[2][tf]
    if not f.exists():
        raise FileNotFoundError(f"no bars for {root}: no tapes under {S.HB_TAPE / root}")
    flt = [("session", ">=", str(start))] if start else []
    flt += [("session", "<=", str(end))] if end else []
    df = pd.read_parquet(f, filters=flt or None)
    ok = []
    for iso in df.session.unique():
        try:
            S.check_holdout(iso, allow, root)
            ok.append(iso)
        except S.HoldoutSealed:
            pass
    if allow == S.ALLOW_WF_OOS and len({iso[:7] for iso in ok}) > 1:
        raise S.HoldoutSealed("an out-of-sample call opens ONE month of the 3:1 blocks, never more")
    return df[df.session.isin(ok)].reset_index(drop=True)


if __name__ == "__main__":
    if sys.argv[1:2] != ["build"]:
        sys.exit("usage: python barstore.py build [ROOT ...]")
    for r in sys.argv[2:] or sorted(p.name for p in S.HB_TAPE.iterdir() if p.is_dir()):
        print(update(r), flush=True)
