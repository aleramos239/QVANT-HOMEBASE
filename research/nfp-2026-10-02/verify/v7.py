"""Clock test: when does the 08:30 reaction appear in the tick files, per instrument (same source)?"""
import datetime as dt, numpy as np, pandas as pd
from pathlib import Path
from v1 import et_ns, nfp_dates
R = Path.home() / "futures_ticks"
def first_move(root, d, thresh):
    best = None
    for f in (R / root / str(d.year)).glob(f"{d:%Y-%m-%d}_*.csv.gz"):
        df = pd.read_csv(f, usecols=["ts_ns", "price", "size"])
        df = df[(df.ts_ns >= et_ns(d, 8, 29)) & (df.ts_ns < et_ns(d, 8, 31))]
        if best is None or df["size"].sum() > best["size"].sum(): best = df
    if best is None or len(best) < 50: return None
    t0 = et_ns(d, 8, 30)
    ts, px = best.ts_ns.to_numpy(), best.price.to_numpy()
    k = np.searchsorted(ts, t0, side="left") - 1
    if k < 0: return None
    a = px[k]
    post = np.flatnonzero((ts >= t0) & (np.abs(px - a) >= thresh))
    # also count ticks in the first 1s vs next
    n0 = int(((ts >= t0) & (ts < t0 + 1_000_000_000)).sum()); n1 = int(((ts >= t0 + 1_000_000_000) & (ts < t0 + 2_000_000_000)).sum())
    first_tick = (ts[ts >= t0][0] - t0) / 1e6 if (ts >= t0).any() else None
    return ((ts[post[0]] - t0) / 1e6 if len(post) else None, first_tick, n0, n1)
dates = [d for d in nfp_dates() if dt.date(2023, 1, 1) <= d <= dt.date(2026, 9, 30)][:60:4]
print("date | GC first >=2pt move ms, first tick ms, ticks[0-1s), [1-2s) | ES first >=4pt ms,..| NQ first >= 10pt")
for d in dates:
    row = []
    for root, th in (("GC", 2.0), ("ES", 3.0), ("NQ", 12.0)):
        try: row.append(first_move(root, d, th))
        except Exception as e: row.append(str(e)[:20])
    print(d, row)
