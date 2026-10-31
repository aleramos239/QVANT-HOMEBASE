"""Monte Carlo luck test of the named passed boxes of ideas 15-16 and 23 (2026-10-30), saved trades only (no new month read).
Trades = in-sample months + test months of the box (cells.npz). Day bootstrap 10,000 paths; luck test = same bootstrap on trades
centred to zero mean, p = share of zero-edge paths with net >= real net (one sided). Sharpe = traded days only. Worse fills = $10 a trade off."""
import json
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; W = HERE.parents[1]
rng = np.random.default_rng(7)
STOPS = {"atr": [0.5, 1, 1.5, 2], "pts": [15, 25, 40, 60]}; TG = [0.5, 0.75, 1, 1.5, 2]
G = json.load(open(HERE / "oos_grid.json"))
def tg(x): return ("%g" % x).replace(".", "p")
def cellname(om, sm, sv, t): return f"off_min{om}_{sm}{tg(sv)}-r{tg(t)}"
def passed(n):
    g = {tuple(map(float, (k.split("|")[0], 0, k.split("|")[2], k.split("|")[3]))) + (k.split("|")[1],): v for k, v in G[n].items()}
    ok = lambda om, sm, sv, t: (om, 0.0, float(sv), float(t), sm) in g and "o_net" in g[(om, 0.0, float(sv), float(t), sm)] and g[(om, 0.0, float(sv), float(t), sm)]["is_net"] > 0 and g[(om, 0.0, float(sv), float(t), sm)]["o_net"] > 0
    out = set()
    for (om, _, sv, t, sm) in g:
        om = int(om); si, ti = STOPS[sm].index(sv if sm == "atr" else int(sv)), TG.index(t)
        if ok(om, sm, sv, t) and all(ok(om, sm, STOPS[sm][a], TG[c]) for a in range(max(0, si - 1), min(4, si + 2)) for c in range(max(0, ti - 1), min(5, ti + 2))):
            out.add((om, sm, STOPS[sm][si], t))
    return out
def load(D, cell):
    z = np.load(D / "cells.npz"); t = pd.read_csv(D / "table.csv"); t = t[t.sess == "all"].reset_index(drop=True)
    i = int(t.index[t.cell == cell][0]); s = slice(z["off"][i], z["off"][i + 1])
    return pd.DataFrame({"day": pd.to_datetime(z["entry_ms"][s], unit="ms", utc=True).tz_convert("America/New_York").tz_localize(None).normalize(), "net": z["net"][s], "side": z["side"][s]})
def boot(ds, n=10000): return ds[rng.integers(0, len(ds), (n, len(ds)))].sum(1)
def dd_paths(ds, n=3000):
    p = ds[rng.integers(0, len(ds), (n, len(ds)))].cumsum(1); return np.percentile((p - np.maximum.accumulate(np.maximum(p, 0), 1)).min(1), [50, 5])
def read(df):
    d = df.groupby("day").net.agg(["sum", "count"]); ds = d["sum"].to_numpy(); mu = df.net.mean()
    t = mu / (df.net.std(ddof=1) / np.sqrt(len(df))) if len(df) > 2 and df.net.std() > 0 else 0.0
    real = ds.sum(); pw = boot(ds); c = ds - d["count"].to_numpy() * mu
    p = float((boot(c) >= real).mean()); dd50, dd5 = dd_paths(ds)
    sh = float(ds.mean() / ds.std() * np.sqrt(252)) if len(ds) > 2 and ds.std() > 0 else 0.0
    return dict(n=len(df), avg=float(mu), net=float(real), t=float(t), p=p, pos=float((pw > 0).mean()), p5=float(np.percentile(pw, 5)), sharpe=sh, dd50=float(dd50), dd5=float(dd5))
PICK = []
p1, p2 = passed("i15_16_close_loc_follow"), passed("i23_new_high_long")
want1 = {(5, "pts", 15, t) for t in TG} | {(5, "pts", 25, t) for t in (1, 1.5, 2)} | {b for b in p1 if b[0] == 60 and b[1] == "pts"}
want2 = {b for b in p2 if b[0] in (5, 60)}
print("named i15_16 boxes NOT in the passed set:", sorted(want1 - p1)); want1 &= p1
PICK = [("i15_16_close_loc_follow", sorted(want1)), ("i23_new_high_long", sorted(want2))]
print({n: len(b) for n, b in PICK})
rows = []
for n, boxes in PICK:
    for om, sm, sv, t in boxes:
        cell = cellname(om, sm, sv, t)
        i = load(W / f"runs_wf/{n}-NQ-tf5/is", cell); o = load(W / f"runs_wf/{n}-NQ-tf5__{cell}/oos", cell)
        a = pd.concat([i, o]); a["yr"] = a.day.dt.year; a["mo"] = a.day.dt.to_period("M")
        A, T, I = read(a), read(o), read(i)
        yrs = a.groupby("yr").net.sum(); mos = a.groupby("mo").net.sum().sort_values(ascending=False); dd = a.groupby("day").net.sum().sort_values(ascending=False)
        rows.append(dict(idea=n, box=cell, **{f"all_{k}": v for k, v in A.items()}, **{f"test_{k}": v for k, v in T.items()}, **{f"is_{k}": v for k, v in I.items()},
            yrs_green=int((yrs > 0).sum()), yrs=len(yrs), top_year_share=float(yrs.max() / a.net.sum()) if a.net.sum() > 0 else None,
            no3mo=float(a.net.sum() - mos.head(3).sum()), no5day=float(a.net.sum() - dd.head(5).sum()), worse=float((a.net - 10).sum()),
            long_net=float(a.net[a.side > 0].sum()), short_net=float(a.net[a.side < 0].sum()), yr_net={int(k): round(float(v)) for k, v in yrs.items()}))
df = pd.DataFrame(rows); df.to_csv(HERE / "mc_eve_results.csv", index=False); json.dump(rows, open(HERE / "mc_eve_results.json", "w"), indent=1)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); pd.set_option("display.max_rows", 200)
print(df[["idea", "box", "all_n", "all_net", "all_t", "all_p", "all_pos", "all_p5", "all_dd50", "all_dd5"]].round(3).to_string())
print(df[["box", "is_t", "is_p", "test_n", "test_net", "test_t", "test_p", "yrs_green", "top_year_share", "no3mo", "worse", "long_net", "short_net"]].round(3).to_string())
