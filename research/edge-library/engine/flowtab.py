"""flowtab -- the per-minute order flow of the desk's own tick archive, read for the DELTA FILTER BLOCKS (families/blocks.py).

SOURCE   ~/futures_derived/flow_1m/<ROOT>.parquet (the ONYX builder research/flow.py: one row per traded minute of the Globex
         day [17:00 ET D-1, 17:00 ET D), every root). Per minute: volume, buy_vol / sell_vol / delta (the aggressor side is an
         ESTIMATE: quote-side where the desk recorded bid and ask, else prints grouped by their identical exchange stamp, a
         one-level order signed by the tick rule; measured against the vendor's delta on NQ 2022-24: minute sign 88.6 % in RTH,
         99.5 % on the top quartile of |delta|, correlation 0.945), sweep_buy_vol / sweep_sell_vol (aggressor orders that walked
         two price levels or more: their side is certain) and the largest aggressor order of the minute with its side.
DAY GRID the engine's minute grid of a trade date: index 0 = 18:00 ET of the evening before .. NMIN - 1 = 16:59 (the grid of
         blocks.minute_volume). Every series is kept as prefix sums, so the net of ANY clock window is two reads.
LAW      a minute M is complete at M + 60 s: a decision at T reads the minutes before T and no other. A date without flow rows,
         or a window without volume, has no signal: the filter blocks the entry on both sides (as every block without a signal).
SEAL     nothing here opens a date: the engine seals every day it replays (check_holdout) and a block asks for the day it is
         replaying and the days BEFORE it. The file holds later dates too (it is the archive's whole flow) and they are never read.
REFRESH  the file ends at the day the builder last ran (`python research/flow.py` in ONYX TRADING); a test day after that has no
         rows, so its delta filters have no signal: `last_date(root)` says where the file ends, the lock and the test read it.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path

import numpy as np

FLOW = Path.home() / "futures_derived" / "flow_1m"
MIN0, NMIN = -360, 1380                             # as blocks.py: index 0 = 18:00 ET of the evening before
SERIES = ("volume", "delta", "sweep", "big")        # the prefix-summed series of a day
COLS = ["t_utc", "session", "volume", "delta", "sweep_buy_vol", "sweep_sell_vol", "big_order", "big_order_side"]


@lru_cache(maxsize=None)
def _table(root: str) -> dict:
    """{session ISO date: int64 [4, NMIN + 1] prefix sums of volume, delta, net sweep volume, signed biggest order} of one root.
    Read once per process."""
    import pandas as pd
    p = FLOW / f"{root}.parquet"
    if not p.exists():
        return {}
    df = pd.read_parquet(p, columns=COLS).sort_values("t_utc", kind="mergesort")
    sess = df["session"].astype(str).to_numpy()
    t = df["t_utc"].to_numpy(np.int64)
    rows = np.stack([df["volume"].to_numpy(np.int64), df["delta"].to_numpy(np.int64),
                     (df["sweep_buy_vol"] - df["sweep_sell_vol"]).to_numpy(np.int64),
                     (df["big_order"].to_numpy(np.int64) * df["big_order_side"].to_numpy(np.int64))])
    cut = np.flatnonzero(np.concatenate(([True], sess[1:] != sess[:-1], [True])))
    out = {}
    for a, b in zip(cut[:-1], cut[1:]):
        iso = sess[a]
        base = _midnight_utc(iso)                   # 00:00 ET of the session date, UTC seconds
        k = (t[a:b] - base) // 60 - MIN0
        ok = (k >= 0) & (k < NMIN)
        day = np.zeros((len(SERIES), NMIN), np.int64)
        day[:, k[ok]] = rows[:, a:b][:, ok]
        out[iso] = np.concatenate((np.zeros((len(SERIES), 1), np.int64), np.cumsum(day, axis=1)), axis=1)
    return out


def _midnight_utc(iso: str) -> int:
    from zoneinfo import ZoneInfo
    d = dt.date.fromisoformat(iso)
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=ZoneInfo("America/New_York")).timestamp())


def day(root: str, iso: str):
    """The prefix sums [4, NMIN + 1] of trade date `iso`, or None when the file has no row of that date."""
    return _table(root).get(iso)


def last_date(root: str):
    """The last session date of a root's flow file (ISO), or None."""
    t = _table(root)
    return max(t) if t else None


def window(root: str, iso: str, a: int, b: int):
    """(volume, delta, net sweep, signed biggest order) of the completed minutes in the clock window [a, b) -- seconds after
    00:00 ET of the trade date `iso`, whole minutes -- or None: no flow for that date, or the window is empty / outside the day."""
    c = day(root, iso)
    i, j = a // 60 - MIN0, b // 60 - MIN0
    if c is None or not 0 <= i < j <= NMIN:
        return None
    return tuple(int(x) for x in c[:, j] - c[:, i])
