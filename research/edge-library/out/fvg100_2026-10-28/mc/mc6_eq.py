"""Monte Carlo luck test of the 6 picked fvg_lab boxes at EQUAL $ risk per trade (default $500; trade net x RISK / (stop pts x $20)), build + test months
together, saved trades only. Same method and bar as mc6.py: day bootstrap 10,000 paths, zero-edge luck p (trades centred), Sharpe traded days only,
worse fills = $10 a trade off at 1 contract, scaled by the same factor. Bar: combined p <= 0.0083, test alone p <= 0.10, 4/6 years, no year over half, worse fills > 0."""
import csv, json, sys
from pathlib import Path
import numpy as np, pandas as pd
W = Path(__file__).resolve().parents[3]; RISK = float(sys.argv[1]) if len(sys.argv) > 1 else 500.0
rng = np.random.default_rng(7)
PICK = [(1, "ovw15", "min_gap0p25_pts60-r1"), (2, "open15", "min_gap0p25_pts60-r1"), (5, "ovw15", "min_gap0p25_pts25-r2"),
        (7, "ovw15", "min_gap0p1_pts60-r0p75"), (8, "ovw15", "min_gap0p1_pts25-r1p5"), (9, "open15", "min_gap0p1_pts25-r1p5")]
def tr(z, s):
    f = RISK / (z["risk"][s].astype(float) * 20.0)
    return pd.DataFrame({"day": pd.to_datetime(z["entry_ms"][s], unit="ms", utc=True).tz_convert("America/New_York").tz_localize(None).normalize(),
                         "net": z["net"][s].astype(float) * f, "f": f})
def load_is(idea, box):
    d = W / f"runs_wf/f100_{idea}-NQ-tf15/is"; z = np.load(d / "cells.npz")
    names = [r["cell"] for r in csv.DictReader(open(d / "table.csv")) if r["sess"] == "all"]; i = names.index(box)
    return tr(z, slice(z["off"][i], z["off"][i + 1]))
def load_oos(idea, box):
    z = np.load(W / f"runs_wf/f100_{idea}-NQ-tf15__{box}/oos/cells.npz"); return tr(z, slice(0, len(z["net"])))
def boot(ds, n=10000): return ds[rng.integers(0, len(ds), (n, len(ds)))].sum(1)
def read(df):
    d = df.groupby("day").net.agg(["sum", "count"]); ds = d["sum"].to_numpy(); mu = df.net.mean()
    t = mu / (df.net.std(ddof=1) / np.sqrt(len(df))); real = ds.sum(); pw = boot(ds); c = ds - d["count"].to_numpy() * mu
    return dict(n=len(df), avg=float(mu), net=float(real), t=float(t), p=float((boot(c) >= real).mean()), pos=float((pw > 0).mean()),
                p5=float(np.percentile(pw, 5)), p50=float(np.percentile(pw, 50)), sharpe=float(ds.mean() / ds.std() * np.sqrt(252)))
rows = []
for k, idea, box in PICK:
    i, o = load_is(idea, box), load_oos(idea, box); a = pd.concat([i, o]); a["yr"] = a.day.dt.year; a["mo"] = a.day.dt.to_period("M")
    yrs = a.groupby("yr").net.sum(); mos = a.groupby("mo").net.sum().sort_values(ascending=False); dd = a.groupby("day").net.sum().sort_values(ascending=False)
    A, T, I = read(a), read(o), read(i)
    rows.append(dict(k=k, idea=idea, box=box, all=A, test=T, ins=I, yrs_green=int((yrs > 0).sum()), yrs=len(yrs), top_year=float(yrs.max() / a.net.sum()),
        yr_net={int(y): round(float(v)) for y, v in yrs.items()}, no3mo=float(a.net.sum() - mos.head(3).sum()), no5day=float(a.net.sum() - dd.head(5).sum()),
        worse=float((a.net - 10 * a.f).sum())))
json.dump(rows, open(Path(__file__).with_name("mc6_eq.json"), "w"), indent=1)
for r in rows:
    A, T, I = r["all"], r["test"], r["ins"]
    print("%d %s %s | all n%d avg $%.0f net $%.0f t%.2f p%.4f pos%.3f P5 $%.0f med $%.0f sh%.2f | test n%d net $%.0f t%.2f p%.3f | IS t%.2f p%.4f | yrs %d/%d top %.2f %s | no3mo $%.0f no5day $%.0f worse $%.0f" % (
        r["k"], r["idea"], r["box"], A["n"], A["avg"], A["net"], A["t"], A["p"], A["pos"], A["p5"], A["p50"], A["sharpe"], T["n"], T["net"], T["t"], T["p"], I["t"], I["p"],
        r["yrs_green"], r["yrs"], r["top_year"], r["yr_net"], r["no3mo"], r["no5day"], r["worse"]))
