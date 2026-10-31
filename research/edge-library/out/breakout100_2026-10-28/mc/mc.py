"""Monte Carlo luck test of the owner's 18 picked boxes (2026-10-29), on saved trades only (no new month read).
Trades = in-sample months + test months of the box (cells.npz). Day bootstrap 10,000 paths (days with a trade resampled with replacement);
luck test = same bootstrap on trades centred to zero mean: p = share of zero-edge paths with net >= the box's real net (one sided).
Sharpe = traded days only. Worse fills = $10 a trade off (1 tick each side, my stress)."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
W = Path(__file__).resolve().parents[3]
rng = np.random.default_rng(7)
PICK = [("nq_b041_london_kz_bracket", "r_end0400", [(40, "0p5"), (25, "0p75")]),
        ("nq_b033_on_bracket", "r_start0000", [(40, "0p5"), (40, "0p75"), (60, "0p5")]),
        ("nq_b044_squeeze", "sq_typeinside", [(60, t) for t in ("0p5", "0p75", "1", "1p5", "2")]),
        ("nq_b089_ib_break", "ib_min30", [(s, "0p5") for s in (15, 25, 40, 60)] + [(60, t) for t in ("0p75", "1", "1p5", "2")])]
def load(D, cell):
    z = np.load(D / "cells.npz"); t = pd.read_csv(D / "table.csv"); t = t[t.sess == "all"].reset_index(drop=True)
    i = int(t.index[t.cell == cell][0]); s = slice(z["off"][i], z["off"][i + 1])
    return pd.DataFrame({"day": pd.to_datetime(z["entry_ms"][s], unit="ms", utc=True).tz_convert("America/New_York").tz_localize(None).normalize(), "net": z["net"][s]})
def boot(dsum, n=10000):                       # sums of n resampled days
    return dsum[rng.integers(0, len(dsum), (n, len(dsum)))].sum(1)
def read(df):
    d = df.groupby("day").net.agg(["sum", "count"]); ds = d["sum"].to_numpy()
    mu = df.net.mean(); t = mu / (df.net.std(ddof=1) / np.sqrt(len(df))) if len(df) > 2 and df.net.std() > 0 else 0.0
    real = ds.sum(); pw = boot(ds); c = ds - d["count"].to_numpy() * mu         # centred: each trade minus the mean
    p = float((boot(c) >= real).mean())
    sh = float(ds.mean() / ds.std() * np.sqrt(252)) if len(ds) > 2 and ds.std() > 0 else 0.0
    return dict(n=len(df), avg=float(mu), net=float(real), t=float(t), p=p, pos=float((pw > 0).mean()), p5=float(np.percentile(pw, 5)), sharpe=sh)
rows = []
for st, var, cells in PICK:
    for stop, tg in cells:
        cell = f"{var}_pts{stop}-r{tg}"
        i = load(W / f"runs_wf/{st}-NQ-tf5/is", cell)
        o = load(W / f"runs_wf/{st}-NQ-tf5__{cell}/oos", cell)
        a = pd.concat([i, o]); a["yr"] = a.day.dt.year; a["mo"] = a.day.dt.to_period("M")
        A, T, I = read(a), read(o), read(i)
        yrs = a.groupby("yr").net.sum(); mos = a.groupby("mo").net.sum().sort_values(ascending=False); dd = a.groupby("day").net.sum().sort_values(ascending=False)
        w = a.net - 10
        rows.append(dict(idea=st.split("_", 2)[1] + "_" + st.split("_", 2)[2], box=cell, **{f"all_{k}": v for k, v in A.items()}, **{f"test_{k}": v for k, v in T.items()}, **{f"is_{k}": v for k, v in I.items()},
            yrs_green=int((yrs > 0).sum()), yrs=len(yrs), top_year_share=float(yrs.max() / a.net.sum()) if a.net.sum() > 0 else None,
            no3mo=float(a.net.sum() - mos.head(3).sum()), no5day=float(a.net.sum() - dd.head(5).sum()), worse=float(w.sum()), yr_net={int(k): round(float(v)) for k, v in yrs.items()}))
df = pd.DataFrame(rows); df.to_csv(Path(__file__).with_name("mc_results.csv"), index=False); json.dump(rows, open(Path(__file__).with_name("mc_results.json"), "w"), indent=1)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print(df[["idea", "box", "all_n", "all_avg", "all_net", "all_t", "all_p", "all_pos", "all_sharpe"]].round(3).to_string())
print(df[["box", "test_n", "test_net", "test_t", "test_p", "is_t", "yrs_green", "yrs", "top_year_share", "no3mo", "no5day", "worse"]].round(2).to_string())
