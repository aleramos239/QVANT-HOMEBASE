"""Tick-tape filters for the two-account 9:30 test (2 NQ, 50-pt stop), in-sample days only.

T1 premarket delta imbalance: |tick-rule delta| / volume, 08:30-09:29:59 (tape has no aggressor flag: uptick = buy, like the tester)
T3 big prints: count of prints >= 20 lots, 08:30-09:29:59, vs the prior 20 in-sample days' average
T4 tape speed: prints per minute 09:20-09:29:59, vs the prior 20 in-sample days' average
Usage: python straddle_930_study/pair_tick_filters.py   (features cached in straddle_930_study/tickfeat.csv)
"""
from __future__ import annotations

import datetime as dt
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "engine"))
sys.path.insert(0, str(HERE))
import l2sim as S  # noqa: E402
import pair_filters as P  # noqa: E402

CACHE = HERE / "tickfeat.csv"
BIG = 20


def one(d: str):
    tp = S.load_tape(d, "NQ", allow_holdout=S.ALLOW_WF_IS)
    if tp is None:
        return d, np.nan, np.nan, np.nan, np.nan
    day = dt.date.fromisoformat(d)
    a, b, c = (np.searchsorted(tp.ts, S.et_ns(day, x)) for x in ("08:30", "09:20", "09:30"))
    px, sz = tp.px[a:c], tp.size[a:c]
    if len(px) < 2:
        return d, np.nan, np.nan, np.nan, np.nan
    step = np.sign(np.diff(px, prepend=px[0]))
    side = pd.Series(np.where(step == 0, np.nan, step)).ffill().fillna(0).to_numpy()   # zero tick keeps the last side
    delta = float((side * sz).sum())
    return d, delta, float(sz.sum()), int((sz >= BIG).sum()), (c - b) / 10.0


def features(days):
    if CACHE.exists():
        f = pd.read_csv(CACHE, index_col=0)
        if set(days) <= set(f.index):
            return f
    with Pool(8) as pool:
        rows = pool.map(one, days, chunksize=8)
    f = pd.DataFrame(rows, columns=["date", "delta", "vol", "big", "ppm"]).set_index("date").sort_index()
    f.to_csv(CACHE)
    return f


def main():
    pairs = P.paired()
    days = sorted(pairs["1:1.5"].index)
    f = features(days)
    f["imb"] = f.delta.abs() / f.vol
    f["big_rel"] = f.big / f.big.rolling(20).mean().shift(1)
    f["ppm_rel"] = f.ppm / f.ppm.rolling(20).mean().shift(1)
    print("days", len(days), "no tape", int(f.vol.isna().sum()))
    q = lambda s: [-np.inf] + list(s.quantile([.2, .4, .6, .8]).values) + [np.inf]
    lab = ["lowest 20%", "20-40%", "40-60%", "60-80%", "highest 20%"]
    P.table("T1. Premarket delta imbalance |delta| / volume", "imb", q(f.imb), lab, f, pairs)
    print("   cutoffs:", ", ".join(f"{x:.3f}" for x in q(f.imb)[1:-1]))
    P.table("T1 split: trade only imbalance >= 0.017 (top 60%)", "imb", [-np.inf, .017, np.inf],
            ["skip (< 0.017)", "trade (>= 0.017)"], f, pairs)
    P.table("T3. Big prints (>= 20 lots) 08:30-09:29 vs 20-day avg", "big_rel", q(f.big_rel), lab, f, pairs)
    print("   cutoffs:", ", ".join(f"{x:.2f}x" for x in q(f.big_rel)[1:-1]))
    P.table("T4. Prints per minute 09:20-09:29 vs 20-day avg", "ppm_rel", q(f.ppm_rel), lab, f, pairs)
    print("   cutoffs:", ", ".join(f"{x:.2f}x" for x in q(f.ppm_rel)[1:-1]))


if __name__ == "__main__":
    main()
