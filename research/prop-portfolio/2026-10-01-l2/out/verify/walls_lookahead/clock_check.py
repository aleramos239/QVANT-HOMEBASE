"""Independent ABSOLUTE-clock check of what the wall families read (verifier). In-sample days, one process, no P&L.

(1) ofb_tick's own lagged columns (a separate pipeline): every print in [T, T + 60 s) carries prev_best_bid / prev_best_ask =
    the last COMPLETED minute at that print. They must equal the bid_px / ask_px of the row ctx.feat serves at a decision at
    T (the row with usable_at == T) -- never the row usable at T + 60 s.
(2) tape-vs-anchor distance: the last print before usable_at + delta against [bid_px, ask_px] of the row. The snapshot
    instant is where the distance is smallest; it must be at delta <= 0 (the book is not newer than the decision).
"""
import datetime as dt
import sys

sys.dont_write_bytecode = True
L = "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2"
sys.path.insert(0, L)
import numpy as np
import pyarrow.parquet as pq

import l2data as D
import l2sim as S

NS = 10**9
DAYS = ["2021-11-10", "2022-03-14", "2022-08-17", "2023-05-18", "2023-07-03", "2023-11-06", "2024-02-14", "2024-09-18",
        "2024-12-05"]
DELTAS = [-120, -60, -10, -3, -1.5, -1.0, -0.7, -0.5, -0.3, -0.1, 0.0, 0.1, 0.3, 0.5, 1.0, 3.0, 10, 60]
tot = {x: [0.0, 0] for x in DELTAS}
agree = {"same": [0, 0], "next": [0, 0], "prev": [0, 0]}
for iso in DAYS:
    d = dt.date.fromisoformat(iso)
    S.check_holdout(d)
    t = pq.ParquetFile(S.tape_path(d)).read(columns=["ts_ns", "price", "prev_best_bid", "prev_best_ask"])
    ts, px = t["ts_ns"].to_numpy(), t["price"].to_numpy()
    pb, pa = t["prev_best_bid"].to_numpy(zero_copy_only=False), t["prev_best_ask"].to_numpy(zero_copy_only=False)
    df = D.load_features(d - dt.timedelta(days=1), d, columns=["bid_px", "ask_px", "t_utc"])
    df = df[df["book_ok"]]
    ua = df.index.as_unit("ns").asi8
    lo, hi = S.et_ns(d, "00:00"), S.et_ns(d, "16:00")
    keep = (ua >= lo) & (ua <= hi)
    ua, bid, ask = ua[keep], df["bid_px"].to_numpy()[keep], df["ask_px"].to_numpy()[keep]
    row = {int(u): i for i, u in enumerate(ua)}
    # (1) the print's own "last completed minute" anchors vs the row usable at the print's minute boundary / +-60 s
    m = (ts >= lo) & (ts < hi) & np.isfinite(pb) & np.isfinite(pa)
    tb = ts[m] - ts[m] % (60 * NS)                                       # decision boundary T at or before the print
    for name, shift in (("same", 0), ("next", 60 * NS), ("prev", -60 * NS)):
        i = np.array([row.get(int(x) + shift, -1) for x in np.unique(tb)])
        look = dict(zip(np.unique(tb).tolist(), i.tolist()))
        ii = np.array([look[int(x)] for x in tb])
        ok = ii >= 0
        eq = (np.abs(bid[ii[ok]] - pb[m][ok]) < 1e-6) & (np.abs(ask[ii[ok]] - pa[m][ok]) < 1e-6)
        agree[name][0] += int(eq.sum())
        agree[name][1] += int(ok.sum())
    # (2) distance of the last print before usable_at + delta to [bid, ask]
    for dl in DELTAS:
        j = np.searchsorted(ts, ua + int(dl * NS), side="left") - 1
        ok = j >= 0
        p = px[j[ok]]
        dist = np.maximum(np.maximum(bid[ok] - p, p - ask[ok]), 0.0)
        tot[dl][0] += float(dist.sum())
        tot[dl][1] += int(ok.sum())
print("(1) prints whose prev_best_bid/ask equal the row usable at T (same) / at T+60 s (next = the minute still forming) / T-60 s:")
for k, (a, b) in agree.items():
    print(f"   {k:5s} {a:>9,d} of {b:>9,d} = {a / max(b, 1):.4%}")
print("(2) mean distance (pts) of the last print before usable_at + delta to [bid_px, ask_px]:")
for dl in DELTAS:
    s, n = tot[dl]
    print(f"   delta {dl:>7.1f} s  {s / n:.4f}  (n={n})")
