"""Frequency, daily-P&L correlation and shared trades of the 6 picked fvg_lab boxes (2026-10-29), full sample at $500 risk. Saved trades only."""
import csv, itertools
from pathlib import Path
import numpy as np, pandas as pd
W = Path(__file__).resolve().parents[3]; RISK = 500.0
PICK = [(1, "ovw15", "min_gap0p25_pts60-r1"), (2, "open15", "min_gap0p25_pts60-r1"), (5, "ovw15", "min_gap0p25_pts25-r2"),
        (7, "ovw15", "min_gap0p1_pts60-r0p75"), (8, "ovw15", "min_gap0p1_pts25-r1p5"), (9, "open15", "min_gap0p1_pts25-r1p5")]
def tr(z, s, part):
    ms = z["entry_ms"][s]
    return pd.DataFrame({"ms": ms, "side": z["side"][s], "part": part, "net": z["net"][s].astype(float) * RISK / (z["risk"][s].astype(float) * 20.0),
        "day": pd.to_datetime(ms, unit="ms", utc=True).tz_convert("America/New_York").tz_localize(None).normalize()})
def load(idea, box):
    d = W / f"runs_wf/f100_{idea}-NQ-tf15/is"; z = np.load(d / "cells.npz")
    names = [r["cell"] for r in csv.DictReader(open(d / "table.csv")) if r["sess"] == "all"]; i = names.index(box)
    zo = np.load(W / f"runs_wf/f100_{idea}-NQ-tf15__{box}/oos/cells.npz")
    return pd.concat([tr(z, slice(z["off"][i], z["off"][i + 1]), "is"), tr(zo, slice(0, len(zo["net"])), "oos")]).sort_values("ms").reset_index(drop=True)
T = {k: load(i, b) for k, i, b in PICK}
alld = sorted(set().union(*[set(t.day) for t in T.values()])); span = (alld[-1] - alld[0]).days / 7.0
print("FREQUENCY (full sample, in-sample + test months)")
print("box | trades | per week | traded days | share of all days that have a trade | trades on a traded day | days with 2+ | max/day")
for k, t in T.items():
    c = t.groupby("day").size(); print("%d | %d | %.1f | %d | %.0f%% | %.2f | %.0f%% | %d" % (k, len(t), len(t) / span, len(c), 100 * len(c) / len(alld), c.mean(), 100 * (c > 1).mean(), c.max()))
print("(%d trading days seen across the six boxes, %s to %s)" % (len(alld), alld[0].date(), alld[-1].date()))
def dpnl(t): return t.groupby("day").net.sum().reindex(alld, fill_value=0.0)
D = pd.DataFrame({k: dpnl(t) for k, t in T.items()})
print("\nDAILY P&L CORRELATION (all days, $0 when no trade)"); print(D.corr().round(2).to_string())
both = {}
print("\nDAILY P&L CORRELATION, only days BOTH boxes traded")
M = pd.DataFrame(index=T, columns=T, dtype=float)
for a, b in itertools.product(T, T):
    ds = sorted(set(T[a].day) & set(T[b].day)); M.loc[a, b] = np.corrcoef(T[a].groupby("day").net.sum().loc[ds], T[b].groupby("day").net.sum().loc[ds])[0, 1]
print(M.round(2).to_string())
def key(t): return set(zip(t.ms.tolist()))
print("\nSAME TRADE (same entry timestamp & side) as % of the row box's trades")
S = pd.DataFrame(index=T, columns=T, dtype=float)
for a, b in itertools.product(T, T):
    ka, kb = set(zip(T[a].ms, T[a].side)), set(zip(T[b].ms, T[b].side)); S.loc[a, b] = 100 * len(ka & kb) / len(ka)
print(S.round(0).to_string())
print("\nSAME DAY traded, as % of the row box's traded days")
Y = pd.DataFrame(index=T, columns=T, dtype=float)
for a, b in itertools.product(T, T):
    da, db = set(T[a].day), set(T[b].day); Y.loc[a, b] = 100 * len(da & db) / len(da)
print(Y.round(0).to_string())
print("\nSAME DAY AND SAME DIRECTION, as % of the row box's traded days")
Z = pd.DataFrame(index=T, columns=T, dtype=float)
for a, b in itertools.product(T, T):
    ga, gb = T[a].groupby("day").side.first(), T[b].groupby("day").side.first(); ds = ga.index.intersection(gb.index)
    Z.loc[a, b] = 100 * (ga.loc[ds] == gb.loc[ds]).sum() / len(ga)
print(Z.round(0).to_string())
print("\nBLOCK (4 distinct): worst day if all 4 distinct strategies lose the same day -- see below")
