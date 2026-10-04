"""wimb: imbalance over the WHOLE near ladder (every level kept by l2data's near-book rule, no 10-level cap).

Per side: zero-size slots dropped (order kept), then the best-first prefix that keeps stepping away from the best by
<= 10 points per step (l2data.MAX_GAP) -- identical to l2data._near except the NLEV = 10 cap. wimb = (B - A) / (B + A) over
those levels, at the depth.bin row keyed 09:29:00 ET (the book at the end of minute 09:29, usable at 09:30:00).
cap=10 reproduces the cached imb10 (test in wide_check.py). Only rows keyed < 2024-12-31 17:00 ET are ever read (BinFile guard).
"""
from __future__ import annotations

import datetime as dt
import sys

import numpy as np

L = "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2"
if L not in sys.path:
    sys.path.insert(0, L)
import l2data as D  # noqa: E402

MAX_GAP = D.MAX_GAP


def side_sum(px, sz, descending: bool, cap=None):
    """(total size, n levels) over the near ladder of ONE side of ONE snapshot. cap=None: all levels."""
    px, sz = np.asarray(px, np.float64), np.asarray(sz, np.float64)
    ok = sz > 0
    px, sz = px[ok], sz[ok]                                   # compact populated slots, order kept (best first)
    if len(px) == 0:
        return 0.0, 0
    keep = np.ones(len(px), bool)
    d = np.diff(px)
    step = ((d < 0) if descending else (d > 0)) & (np.abs(d) <= MAX_GAP)
    keep[1:] = np.logical_and.accumulate(step)
    if cap is not None:
        keep[cap:] = False
    return float(sz[keep].sum()), int(keep.sum())


def snapshot_imb(bid, ask, cap=None):
    """bid / ask: (n, 2) arrays [px, sz] best first. Returns (imb, nb, na, B, A); imb NaN unless two-sided."""
    B, nb = side_sum(bid[:, 0], bid[:, 1], True, cap)
    A, na = side_sum(ask[:, 0], ask[:, 1], False, cap)
    bb = [p for p, s in zip(bid[:, 0], bid[:, 1]) if s > 0]
    aa = [p for p, s in zip(ask[:, 0], ask[:, 1]) if s > 0]
    if nb < 1 or na < 1 or not (aa[0] > bb[0]):
        return float("nan"), nb, na, B, A
    return (B - A) / (B + A), nb, na, B, A


def key_0929(d: dt.date) -> int:
    return int(d.strftime("%Y%m%d") + "092900")


def wide_imb_by_date(dates, cap=None, allow_holdout=False):
    """{date: wimb} from the 09:29 depth row of each date (NaN if the row is missing). allow_holdout=True opens the file chain incl. 2025+ rows."""
    bfs = [D.BinFile(p, "depth", True if allow_holdout else False) for p in D.ofb_files("depth", allow_holdout)]
    out, meta = {}, {}
    for d in dates:
        k = key_0929(d); hit = None
        for bf in bfs:
            i, j = bf.bounds(k, k + 1)
            if j > i: hit = (bf, i); break
        if hit is None:
            out[d] = float("nan"); continue
        bf, i = hit
        r = bf.row(i)
        v, nb, na, B, A = snapshot_imb(r["bid"], r["ask"], cap)
        out[d] = v; meta[d] = (nb, na, B, A)
    return out, meta, bfs[0].n
