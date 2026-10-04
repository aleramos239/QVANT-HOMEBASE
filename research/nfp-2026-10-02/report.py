"""Tables for results.md (IS = selection window, HO = spent-window check of the frozen finalists)."""
import numpy as np, pandas as pd
from nfp_lib import *
pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 300)
sI = pd.read_csv(CACHE / "summary_IS.csv"); sH = pd.read_csv(CACHE / "summary_HO.csv")
gI = pd.read_csv(CACHE / "grid_IS.csv.gz"); gH = pd.read_csv(CACHE / "grid_HO.csv.gz")
mH = pd.read_csv(CACHE / "cells_HO.csv", index_col="cell")
NAMES = {10: "A", 19: "B", 1: "C", 15: "D", 274: "E"}   # IS cell ids
H_ID = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}
print("=== slippage sensitivity: P(win)=P(pass this event) / P(bust) / P(<=4-event pass) / mean net per event")
for nm in ("A", "B", "C"):
    for st in ("ALL", "NFP"):
        for part, s, cid in (("IS", sI, {v: k for k, v in NAMES.items()}[nm]), ("HO", sH, H_ID[nm])):
            t = s[(s.cell == cid) & (s.set == st)].set_index("model").loc[["M0", "M1", "P1", "P2", "P4"]]
            print(nm, st, part, "n", int(t.n.iloc[0]), " | ".join(f"{m}: {r.p_win:.2f}/{r.p_bust1:.2f}/{r.p_pass_h:.2f}/${r.mean_net:,.0f}" for m, r in t.iterrows()))
print("\n=== by year, A and B, P(win) M1 | P2 (n)")
for nm, cI, cH in (("A", 10, 0), ("B", 19, 1)):
    for part, g, cid in (("IS", gI, cI), ("HO", gH, cH)):
        h = g[g.cell == cid].copy(); h["y"] = h.date.str[:4]
        out = []
        for y, hy in h.groupby("y"):
            a = hy[hy.model == "M1"]; b = hy[hy.model == "P2"]
            out.append(f"{y}: {np.mean(a.net >= 2999.99):.2f}|{np.mean(b.net >= 2999.99):.2f} (n{len(a)}, bust {np.mean(b.net <= -2000):.2f})")
        print(nm, part, " ; ".join(out))
print("\n=== A on the high-vol 2026 events only (V_prev>=30)")
V = pd.read_json(CACHE / "vprev_HO.json")["GC"] if False else None
import json
v = json.load(open(CACHE / "vprev_HO.json"))["GC"]
h = gH[gH.cell == 0].copy(); h["V"] = h.date.map(v)
for lo, hi in ((0, 25), (25, 1e9)):
    for m in ("M1", "P2"):
        x = h[(h.model == m) & (h.V >= lo) & (h.V < hi)]
        print(f"V_prev {lo}-{hi:g} {m}: n {len(x)}  P(win) {np.mean(x.net >= 2999.99):.2f}  P(bust) {np.mean(x.net <= -2000):.2f}  mean net ${x.net.mean():,.0f}")
x = h[(h.model == "M1")]
print(x[x.date >= "2026-01-01"][["date", "event", "net", "why", "off_pts", "sl_pts", "tp_pts"]].to_string(index=False))
print("\n=== comparison instruments, IS only, max size, SL1500/3000 one-shot, pooled NFP+CPI (best offset by smoothed M1/P2 mean)")
for r in ("GC", "NQ", "ES", "SI"):
    g = sI[(sI.root == r) & (sI.set == "ALL") & (sI.tp_usd == 3000) & (sI.sl_usd == 1500) & (sI.model.isin(["M1", "P2"]))]
    g = g[g.unit.str.startswith("4x") | g.unit.str.startswith("40x")]
    best = g.groupby(["unit", "offmode", "off"]).p_win.mean().sort_values(ascending=False).head(2)
    for (u, om, o), _ in best.items():
        for m in ("M1", "P2"):
            t = g[(g.unit == u) & (g.offmode == om) & (g.off == o) & (g.model == m)].iloc[0]
            print(f"{r} {u} off {o}{'V' if om=='vol' else 'pt'} {m}: n {int(t.n)} P(pass) {t.p_win:.2f} [{t.p_win_lo:.2f},{t.p_win_hi:.2f}] bust {t.p_bust1:.2f} pass<=4ev {t.p_pass_h:.2f} meannet ${t.mean_net:,.0f}")
print("\n=== diversification: P(at least one of several evals passes) IS pooled, M1 / P2, GC 4x SL1500, offsets 1,2,3 (3 evals, one each)")
for m in ("M1", "P2"):
    wins = {}
    for o in (1.0, 2.0, 3.0, 5.0):
        c = sI[(sI.root == "GC") & (sI.unit == "4xGC") & (sI.offmode == "pts") & (sI.off == o) & (sI.sl_usd == 1500) & (sI.tp_usd == 3000)].cell.iloc[0]
        h = gI[(gI.cell == c) & (gI.model == m)].set_index("date").net >= 2999.99
        wins[o] = h
    W = pd.DataFrame(wins)
    print(m, "each:", W.mean().round(2).to_dict(), " any of off{1,2,3}:", round(W[[1.0, 2.0, 3.0]].any(axis=1).mean(), 3), " all three:", round(W[[1.0, 2.0, 3.0]].all(axis=1).mean(), 3), " corr(1,2):", round(W[1.0].corr(W[2.0]), 2))
