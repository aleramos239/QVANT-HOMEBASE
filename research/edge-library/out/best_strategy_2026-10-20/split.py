"""Read-only: split a taught cell's build-day trades by trade number of the day, entry hour, side and stop size, by year."""
import sys, json, os, datetime as dt
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from combo import load
name = sys.argv[1]
lab, x = load(name)
d = np.asarray(x["date"]); t = np.asarray(x["entry_ms"]); n = np.asarray(x["net"], float)
order = np.lexsort((t, d)); d, t, n = d[order], t[order], n[order]
risk = np.asarray(x["risk"], float)[order] if "risk" in x else None
num = np.zeros(len(d), int)
for i in range(1, len(d)):
    num[i] = num[i-1] + 1 if d[i] == d[i-1] else 0
yr = np.array([dt.date.fromordinal(int(v)).year for v in d])
import zoneinfo
ny = zoneinfo.ZoneInfo("America/New_York")
hr = np.array([dt.datetime.fromtimestamp(ms / 1000, ny).hour for ms in t])
def row(lbl, m):
    if m.sum() == 0: return
    ys = " ".join(f"{y}:{n[m & (yr==y)].mean():+5.0f}({(m & (yr==y)).sum()})" for y in sorted(set(yr)) if (m & (yr==y)).sum())
    print(f"  {lbl:14s} n={m.sum():5d} avg={n[m].mean():+7.1f} net={n[m].sum():+9.0f} win={(n[m]>0).mean():.3f} | {ys}")
print(lab, "trades", len(n), "keys", list(x.keys()))
print("by trade number of the day"); [row(f"trade {k+1}", num == k) for k in range(num.max() + 1)]
print("by entry hour (ET)"); [row(f"{h:02d}:00", hr == h) for h in sorted(set(hr))]
if "mae" in x:
    pass
print("by year"); [row(str(y), yr == y) for y in sorted(set(yr))]
