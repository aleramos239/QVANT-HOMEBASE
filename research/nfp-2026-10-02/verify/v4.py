import pandas as pd, numpy as np, datetime as dt
from v2 import *
from nfp_lib import CACHE
mine = run(2.0, 3.7, 7.6, 4.0, e_slip=1, s_slip=1).set_index("date")
mineB = run(2.0, 5.0, 7.6, 4.0, e_slip=1, s_slip=1).set_index("date")
for part, a, b in (("IS", 10, 19), ("HO", 0, 1)):
    g = pd.read_csv(CACHE / f"grid_{part}.csv.gz")
    for cell, m, nm in ((a, mine, "A"), (b, mineB, "B")):
        h = g[(g.cell == cell) & (g.model == "M1") & (g.event == "NFP")].copy()
        h["d"] = pd.to_datetime(h.date).dt.date
        h = h.set_index("d")
        j = h.join(m[["net", "out"]], rsuffix="_me", how="left")
        diff = (j.net - j.net_me).abs()
        print(part, nm, "their NFP n", len(h), "matched", int(j.net_me.notna().sum()), "net diff>$1:", int((diff > 1).sum()), "outcome mismatches:", int((j.why != j.out).sum()))
        bad = j[(diff > 1) | (j.why != j.out)]
        if len(bad): print(bad[["net", "net_me", "why", "out"]])
