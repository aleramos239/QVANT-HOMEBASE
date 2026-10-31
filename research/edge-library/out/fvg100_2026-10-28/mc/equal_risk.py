"""Full sample (build + test months) of 6 picked fvg_lab boxes at the SAME $ risk per trade (2026-10-29). Saved trades only, no new month read.
Each trade's net is scaled by RISK / (stop pts x $20): fractional contracts, so costs scale too (a proxy; real size is whole micros/minis).
Sharpe/Sortino = daily net of traded days only (same formulas as homebase/backtest/stats._sharpe and report.sortino)."""
import csv, math, sys
from pathlib import Path
import numpy as np, pandas as pd
W = Path(__file__).resolve().parents[3]
RISK = float(sys.argv[1]) if len(sys.argv) > 1 else 500.0
PICK = [(1, "ovw15", "min_gap0p25_pts60-r1"), (2, "open15", "min_gap0p25_pts60-r1"), (5, "ovw15", "min_gap0p25_pts25-r2"),
        (7, "ovw15", "min_gap0p1_pts60-r0p75"), (8, "ovw15", "min_gap0p1_pts25-r1p5"), (9, "open15", "min_gap0p1_pts25-r1p5")]
def tr(z, s):
    return pd.DataFrame({"ms": z["entry_ms"][s], "net": z["net"][s].astype(float), "risk": z["risk"][s].astype(float),
                         "day": pd.to_datetime(z["entry_ms"][s], unit="ms", utc=True).tz_convert("America/New_York").tz_localize(None).normalize()})
def load(idea, box):
    d = W / f"runs_wf/f100_{idea}-NQ-tf15/is"; z = np.load(d / "cells.npz")
    names = [r["cell"] for r in csv.DictReader(open(d / "table.csv")) if r["sess"] == "all"]; i = names.index(box)
    a = tr(z, slice(z["off"][i], z["off"][i + 1])); zo = np.load(W / f"runs_wf/f100_{idea}-NQ-tf15__{box}/oos/cells.npz")
    return pd.concat([a, tr(zo, slice(0, len(zo["net"])))]).sort_values("ms").reset_index(drop=True)
def sharpe(d): m = np.mean(d); sd = np.std(d, ddof=1); return m / sd * math.sqrt(252) if sd else 0.0
def sortino(d): dd = math.sqrt(np.mean(np.minimum(d, 0) ** 2)); return np.mean(d) / dd * math.sqrt(252) if dd else 0.0
out = []
for k, idea, box in PICK:
    a = load(idea, box); a["f"] = RISK / (a.risk * 20.0); a["n"] = a.net * a.f; a["yr"] = a.day.dt.year
    d = a.groupby("day").n.sum(); eq = d.cumsum(); dd = (eq.cummax() - eq).max(); mo = a.groupby(a.day.dt.to_period("M")).n.sum()
    w, l = a.n[a.n > 0], a.n[a.n < 0]; sd = a.n.std(ddof=1)
    out.append(dict(k=k, idea=idea, box=box, trades=len(a), win=(a.n > 0).mean(), avg=a.n.mean(), avg_r=a.n.mean() / RISK, net=a.n.sum(), pf=w.sum() / -l.sum(),
        rr=w.mean() / -l.mean(), t=a.n.mean() / (sd / math.sqrt(len(a))), sharpe=sharpe(d.values), sortino=sortino(d.values), maxdd=dd, worst_day=d.min(), worst_mo=mo.min(),
        mo_green=(mo > 0).mean(), avg_contracts=a.f.mean(), yrs=a.groupby("yr").n.sum().round().astype(int).to_dict(), tr_wk=len(a) / (len(d) / 5 * (len(a.day.unique()) and 1)) if False else len(a) / ((a.day.max() - a.day.min()).days / 7)))
for r in out:
    print("%d %-6s %-24s n %d win %.0f%% RR %.2f avg $%.0f (%.2fR) net $%.0f PF %.2f t %.2f Sharpe %.2f Sortino %.2f maxDD $%.0f worstday $%.0f worstmonth $%.0f mo+ %.0f%% ~%.2f contracts, %.1f tr/wk\n   %s" % (
        r["k"], r["idea"], r["box"], r["trades"], 100 * r["win"], r["rr"], r["avg"], r["avg_r"], r["net"], r["pf"], r["t"], r["sharpe"], r["sortino"], r["maxdd"], r["worst_day"], r["worst_mo"], 100 * r["mo_green"], r["avg_contracts"], r["tr_wk"], r["yrs"]))
