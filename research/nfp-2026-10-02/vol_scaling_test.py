"""IS-only: does the best target distance T (pts) rise with the event volatility V? Same-fill replays on 2021-10..2024-12 GC.
P(win) = hit TP (nets $3,000) before the SL ($1,500 = T/2 in pts-equivalent). Offset fixed at 2 pts (pts) and at 0.15 V (vol). Slip model P2."""
import pickle, numpy as np, pandas as pd, sys
from nfp_lib import *
from grid import vprev, SKIP_FIRST
I = pickle.load(open(CACHE / "tapes_IS.pkl", "rb"))
ev, T = I["events"], I["tapes"]
V = vprev("GC", ev, T)
rows = []
Ns = [40, 32, 27, 24, 20, 16, 12, 10, 8, 6]
for d, tag in ev:
    if d not in V or ("GC", d) not in T: continue
    P = prep(d, *T[("GC", d)])
    for N in Ns:
        pv, comm = 10.0 * N, 1.5 * N
        sl, tp = bracket(pv, comm, 0.1, 1500, 3000)
        for om, off in (("pts2", 2.0), ("vol.15", max(0.1, round(0.15 * V[d] / 0.1) * 0.1))):
            net, why = replay(P, off, sl, tp, 0.1, pv, comm, 2, 2, True)
            rows.append((d, V[d], N, tp, om, net, why))
df = pd.DataFrame(rows, columns="d V N T om net why".split())
df["tercile"] = pd.qcut(df.groupby("d").V.transform("first"), 3, labels=["lowV", "midV", "highV"])
df["win"] = df.net >= 2999.99
print(df.groupby("tercile").V.agg(["min", "median", "max"]).round(1))
for om in ("pts2", "vol.15"):
    t = df[df.om == om].pivot_table(index="T", columns="tercile", values="win", aggfunc="mean", observed=True).round(2)
    t["all"] = df[df.om == om].groupby("T").win.mean().round(2); print("offset", om); print(t)
