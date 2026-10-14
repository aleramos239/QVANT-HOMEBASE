"""tapeflow -- the desk's per-trade tape (flow_tape), read for the three TAPE BLOCKS of batch 6 (families/blocks.py): fpstack, vprof, press.

SOURCE   ~/futures_derived/flow_tape/<ROOT>/<year>/<session date>.parquet: one row per print of the Globex day [18:00 ET D-1, 17:00 ET D)
         -- ts_ns, price, size, side (+1 the buyer paid the ask, -1 / 0 the seller hit the bid), order (the aggressor order's number).
         It is the table the chart's footprint, profile and pressure read live (homebase/charts/bars.py): the definitions below are
         the chart's own, so a strategy that uses one draws what it tests.
LAW      a decision at T reads the prints BEFORE T of the day it is replaying and no other day; the engine seals every day it replays.
         A date without a file has no signal (the filter blocks the entry on both sides, as every block without a signal).
         The file ends where the flow table ends (flowtab.last_date): the blocks sit in blocks.FLOW_BLOCKS for the test-range cap.

FOOTPRINT STACK  (chart: flowmath.js imbalances + stackedRuns, footprint defaults: ratio 3, stack 3, one tick per row)
         In the window of one tf bar: per tick row, sells at the bid and buys at the ask. A BUY imbalance at row k: buys(k) > 0 and
         buys(k) >= 3 x max(sells(k - 1), 1); a SELL imbalance at k: sells(k) > 0 and sells(k) >= 3 x max(buys(k + 1), 1) (diagonal). A
         stack = 3 or more rows IN A ROW that all carry one side's imbalance. +1 = a buy stack and no sell stack, -1 = a sell stack and
         no buy stack, None = none, or both.
PROFILE  (chart: profile, 70 % value area, flowmath.js valueArea) the volume per tick row of the day's tape from the session's start up
         to the decision. POC = the busiest row (the lowest on a tie); the value area starts at the POC and takes the heavier of the next
         two rows above / below until 70 % of the volume is covered.
PRESSURE (chart: studies_flow.Pressure, n = 5 bars) the tf bars of the day, each as four parts (buy, sell): the aggressors' volume;
         big prints (a print of >= 10 contracts AND >= 8 x the session's average print so far); sweeps (a run of one side's prints in
         one millisecond that spans 2 ticks or more, its volume); orders (the runs of one side's prints in one millisecond, counted).
         Each part is summed with the weight keep = 1 - 2 / (n + 1) per bar back, and read as 100 x (buy - sell) / (buy + sell + SHRINK)
         (SHRINK = 0, 30, 30, 20); the blend weighs volume 3 and the others 1 over the parts that have anything. The session restarts
         it (the file's first print). A bar keeps only its 60 largest sweeps (bars.py SW_CAP; ties: earlier, then lower, then sell).
         One difference from the live chart: a run of prints in one millisecond that straddles two bars belongs to the bar of its
         first print (the chart splits it when it is a new Bar object).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

from flowtab import _midnight_utc
from l2sim import SPECS

TAPE = Path.home() / "futures_derived" / "flow_tape"
IMB_RATIO, STACK_ROWS = 3.0, 3                      # footprint defaults of the chart (catalog.js)
VA_PCT = 70.0                                       # the chart's value area
BIG_MIN, BIG_REL, SWEEP_TICKS = 10, 8.0, 2          # bars.py BIG_MIN / SWEEP_TICKS, studies_flow.Pressure.BIG_REL
SW_CAP = 60                                         # bars.py SW_CAP: a bar keeps only its 60 largest sweeps
WEIGHT, SHRINK = (3.0, 1.0, 1.0, 1.0), (0.0, 30.0, 30.0, 20.0)
PRESS_N = 5                                         # the chart's default "bars weighed together"
LEAN = 10.0                                         # |pressure| below this reads "Even": no direction (the chart's first band)


def tick_of(root: str) -> float:
    return SPECS[root][1]


@lru_cache(maxsize=12)
def day(root: str, iso: str):
    """{'t': int64 epoch ms, 's': epoch s, 'k': tick row, 'q': size, 'b': bool buyer}, sorted by time, or None: no file for that date."""
    p = TAPE / root / iso[:4] / f"{iso}.parquet"
    if not p.exists():
        return None
    import pandas as pd
    df = pd.read_parquet(p, columns=["ts_ns", "price", "size", "side"]).sort_values("ts_ns", kind="mergesort")
    t = df["ts_ns"].to_numpy(np.int64) // 1_000_000
    k = np.rint(df["price"].to_numpy(np.float64) / tick_of(root)).astype(np.int64)
    return {"t": t, "s": t // 1000, "k": k, "q": df["size"].to_numpy(np.int64), "b": df["side"].to_numpy(np.int8) > 0, "base": _midnight_utc(iso)}


def _slice(d, a: int, b: int):
    """The index range of the prints in [a, b) seconds after 00:00 ET of the trade date."""
    i = int(np.searchsorted(d["s"], d["base"] + a, side="left"))
    j = int(np.searchsorted(d["s"], d["base"] + b, side="left"))
    return i, j


def _rows(d, i: int, j: int):
    """(ticks ascending, sells at each, buys at each) of the prints [i, j)."""
    k, q, b = d["k"][i:j], d["q"][i:j], d["b"][i:j]
    ks, inv = np.unique(k, return_inverse=True)
    return ks, np.bincount(inv, weights=np.where(b, 0, q), minlength=len(ks)), np.bincount(inv, weights=np.where(b, q, 0), minlength=len(ks))


def _run(keys, need: int) -> bool:
    """Do the sorted tick keys hold `need` consecutive ones?"""
    n = 0
    for x, y in zip(keys, keys[1:]):
        n = n + 1 if y == x + 1 else 0
        if n + 1 >= need:
            return True
    return need <= 1 and len(keys) > 0


def stack_dir(root: str, iso: str, a: int, b: int, ratio: float = IMB_RATIO, rows: int = STACK_ROWS):
    """+1 | -1 | None: the stacked imbalances of the prints in [a, b) seconds after 00:00 ET (see FOOTPRINT STACK)."""
    d = day(root, iso)
    if d is None:
        return None
    i, j = _slice(d, a, b)
    if j <= i:
        return None
    ks, sell, buy = _rows(d, i, j)
    pos = {int(k): n for n, k in enumerate(ks)}
    bi, si = [], []
    for n, k in enumerate(ks):
        k = int(k)
        lo, hi = pos.get(k - 1), pos.get(k + 1)
        if buy[n] > 0 and buy[n] >= ratio * max(sell[lo] if lo is not None else 0.0, 1.0):
            bi.append(k)
        if sell[n] > 0 and sell[n] >= ratio * max(buy[hi] if hi is not None else 0.0, 1.0):
            si.append(k)
    up, dn = _run(bi, max(2, rows)), _run(si, max(2, rows))
    return 1 if up and not dn else -1 if dn and not up else None


def value_area(ks, vol, pct: float = VA_PCT):
    """(poc, vah, val) of rows `ks` (ascending ticks) with volume `vol`, as flowmath.js valueArea."""
    at = int(np.argmax(vol))
    want = float(vol.sum()) * min(100.0, max(1.0, pct)) / 100.0
    lo = hi = at
    got, n = float(vol[at]), len(vol)
    while got < want and (lo > 0 or hi < n - 1):
        up = vol[hi + 1] + (vol[hi + 2] if hi + 2 < n else 0.0) if hi < n - 1 else -1.0
        dn = vol[lo - 1] + (vol[lo - 2] if lo - 2 >= 0 else 0.0) if lo > 0 else -1.0
        if up >= dn and up >= 0:
            hi += 1
            got += vol[hi]
            if got < want and hi < n - 1:
                hi += 1
                got += vol[hi]
        elif dn >= 0:
            lo -= 1
            got += vol[lo]
            if got < want and lo > 0:
                lo -= 1
                got += vol[lo]
        else:
            break
    return int(ks[at]), int(ks[hi]), int(ks[lo])


def profile(root: str, iso: str, b: int):
    """(poc, vah, val) in PRICE of the day's tape up to second `b` after 00:00 ET, or None: no file, no volume."""
    d = day(root, iso)
    if d is None:
        return None
    i, j = _slice(d, -10**6, b)
    if j <= i:
        return None
    ks, sell, buy = _rows(d, i, j)
    poc, vah, val = value_area(ks, sell + buy)
    t = tick_of(root)
    return poc * t, vah * t, val * t


@lru_cache(maxsize=16)
def _pressure_day(root: str, iso: str, step: int):
    """{bar close second: the blended pressure (-100..100) or None} of every step-second bar of the day, bars on the epoch grid."""
    d = day(root, iso)
    if d is None or len(d["t"]) == 0:
        return {}
    t, s, k, q, b = d["t"], d["s"], d["k"], d["q"], d["b"]
    n = len(t)
    new = np.ones(n, bool)                          # a run = the same millisecond and the same side
    new[1:] = (t[1:] != t[:-1]) | (b[1:] != b[:-1])
    start = np.flatnonzero(new)
    g_id = np.cumsum(new) - 1
    g_n = np.diff(np.append(start, n))
    g_kmin = np.minimum.reduceat(k, start)
    g_kmax = np.maximum.reduceat(k, start)
    g_vol = np.add.reduceat(q, start)
    g_buy = b[start]
    g_sweep = (g_n >= 2) & (g_kmax - g_kmin >= SWEEP_TICKS)
    g_t = s[start]
    g_ms = t[start]
    keep = 1.0 - 2.0 / (PRESS_N + 1)
    acc, pn, pv = np.zeros(8), 0, 0
    out = {}
    bar0 = int(s[0]) // step
    bar1 = int(s[-1]) // step
    pi = gi = 0
    for bar in range(bar0, bar1 + 1):
        end = (bar + 1) * step
        pj = int(np.searchsorted(s, end, side="left"))
        gj = int(np.searchsorted(g_t, end, side="left"))
        if pj > pi:
            qb, bb = q[pi:pj], b[pi:pj]
            pn, pv = pn + (pj - pi), pv + int(qb.sum())
            floor = max(float(BIG_MIN), BIG_REL * pv / pn)
            big = qb >= floor
            gb, gv, gsw = g_buy[gi:gj], g_vol[gi:gj], g_sweep[gi:gj]
            if gsw.sum() > SW_CAP:                  # the chart's cap: the 60 largest (size down, then time, from, to, side up)
                at = np.flatnonzero(gsw)
                o = np.lexsort((gb[at], g_kmax[gi:gj][at], g_kmin[gi:gj][at], g_ms[gi:gj][at], -gv[at]))[:SW_CAP]
                gsw = np.zeros(gj - gi, bool)
                gsw[at[o]] = True
            parts = np.array([qb[bb].sum(), qb[~bb].sum(), qb[big & bb].sum(), qb[big & ~bb].sum(),
                              gv[gsw & gb].sum(), gv[gsw & ~gb].sum(), gb.sum(), (~gb).sum()], np.float64)
        else:
            parts = np.zeros(8)
        acc = acc * keep + parts
        num = den = 0.0
        for i, w in enumerate(WEIGHT):
            bsum, ssum = acc[2 * i], acc[2 * i + 1]
            if bsum + ssum > 0:
                num, den = num + w * 100.0 * (bsum - ssum) / (bsum + ssum + SHRINK[i]), den + w
        out[end] = num / den if den else None
        pi, gi = pj, gj
    return out


def pressure(root: str, iso: str, b: int, tf: int):
    """The blended pressure (-100..100) after the tf-minute bar that closes at second `b` after 00:00 ET, or None (no file / no print)."""
    d = day(root, iso)
    if d is None:
        return None
    return _pressure_day(root, iso, tf * 60).get(d["base"] + b)


def pressure_dir(root: str, iso: str, b: int, tf: int):
    """+1 | -1 | None: the sign of the pressure when it is a lean (|p| >= LEAN, the chart's 'Buyers lean' / 'Sellers lean')."""
    p = pressure(root, iso, b, tf)
    return None if p is None or abs(p) < LEAN else 1 if p > 0 else -1
