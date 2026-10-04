"""Independent verification sim (written fresh, shares no code with nfp_lib.py). Raw GC ticks -> NFP straddle."""
import csv, datetime as dt, json, gzip, sys, pickle
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd
ET = ZoneInfo("America/New_York"); UTC = dt.timezone.utc
ARCH = Path.home() / "futures_ticks" / "GC"
CAL = Path.home() / "ramos-quant-homebase/homebase/strategies/data/gc_0830_redfolder_days_2021_2026.csv"
OUT = Path("/private/tmp/claude-501/-Users-ramoscapital-Library-Application-Support-Claude-scratch-workspaces-bede25d7-4e1b-4b3e-b8ef-70c7ef831e62-9ebb0405-7969-47e0-923d-777091be95f0-scratch-2026-09-30-896b12/db1f7d1a-1c40-4988-9502-1482f7a31fc2/scratchpad/v_nfp.pkl")

def et_ns(d, h, m, s=0):
    return int(dt.datetime(d.year, d.month, d.day, h, m, s, tzinfo=ET).astimezone(UTC).timestamp() * 1_000_000_000)

def nfp_dates():
    out = []
    for r in csv.DictReader(open(CAL)):
        if "NFP" in r["tag"].split("+"):
            out.append(dt.date.fromisoformat(r["date"]))
    return out

def load(d):
    t0, t1 = et_ns(d, 8, 0), et_ns(d, 10, 0)
    best = None
    for f in (ARCH / str(d.year)).glob(f"{d:%Y-%m-%d}_*.csv.gz"):
        df = pd.read_csv(f, usecols=["ts_ns", "price", "size"])
        df = df[(df.ts_ns >= t0) & (df.ts_ns < t1)]
        # front = most volume in the window
        v = int(df["size"].sum())
        if best is None or v > best[0]:
            best = (v, f.name, df.reset_index(drop=True))
    return best

if __name__ == "__main__":
    res = {}
    for d in nfp_dates():
        if d < dt.date(2021, 1, 1): continue
        b = load(d)
        if b is None: print(d, "NO DATA"); continue
        res[d] = b
        ts = b[2].ts_ns.to_numpy(); px = b[2].price.to_numpy()
        t830 = et_ns(d, 8, 30)
        # timing check: 1-second window with the largest range between 08:20 and 08:40
        sel = (ts >= et_ns(d, 8, 20)) & (ts < et_ns(d, 8, 40))
        tsel, psel = ts[sel], px[sel]
        sec = (tsel - t830) // 1_000_000_000
        g = pd.DataFrame({"s": sec, "p": psel}).groupby("s").p.agg(lambda x: x.max() - x.min())
        peak = int(g.idxmax()) if len(g) else None
        print(d, b[1], "vol", b[0], "ticks", len(ts), "pre-830 last", psel[tsel < t830][-1] if (tsel < t830).any() else None, "max-1s-range sec offset", peak, round(g.max(), 1) if len(g) else None)
    pickle.dump(res, open(OUT, "wb"))
