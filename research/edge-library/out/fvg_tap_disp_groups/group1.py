"""Group 1 (owner, 2026-10-28): 31 boxes of nq_fvg60_d5_atr_g18_out saved to the side, NOT a pick / lock. Writes group1.csv beside it.
Run from research/edge-library:  PYTHONPATH=.:engine ~/ramos-quant-homebase/.venv-research/bin/python out/fvg_tap_disp_groups/group1.py"""
import json, csv, sys, types
import numpy as np
from pathlib import Path
src = Path("out/daily_ideas_heatmaps_2026-10-26/make.py").read_text().replace("idea\\'s own stop", "idea&#39;s own stop")
hm = types.ModuleType("hm"); hm.__file__ = "make.py"; exec(compile(src, "d", "exec"), hm.__dict__)
T = (0.5, 0.75, 1, 1.5, 2)
WANT = {(1, "own", 1): T[:3], (1.5, "own", 2): T[2:], (1.5, "atr", 2): T, (2, "atr", 2): T,
        **{(2, "own", s): T for s in (1, 1.5, 2)}}
CARD = sys.argv[1] if len(sys.argv) > 1 else "nq_fvg60_d5_atr_g18_out"
d = f"runs_wf/{CARD}-NQ-tf5/is/"
run, z = json.load(open(d + "run.json")), np.load(d + "cells.npz")
off, net = z["off"], z["net"]
rows = []
for i, cl in enumerate(run["cells"]):
    e, k = cl["exit"], cl["variant"]["k"]
    if e["tgt_r"] not in WANT.get((k, e["stop_mode"], e["stop_val"]), ()):
        continue
    a, b = int(off[i]), int(off[i + 1])
    m = hm.L.metrics({kk: z[kk][a:b] for kk in z.files if kk != "off"})
    rows.append([cl["id"], k, e["stop_mode"], e["stop_val"], e["tgt_r"], m["trades"], round(m["net"]), round(m["win"], 3), round(m["pf"], 2), round(m["t"], 2)])
with open(f"out/fvg_tap_disp_groups/group1_{CARD}.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["box", "k", "stop", "stop_x", "target_R", "trades", "net_usd", "win", "pf", "t"]); w.writerows(rows)
print(len(rows), "boxes; net", sum(r[6] for r in rows), "green", sum(r[6] > 0 for r in rows))
for r in rows: print(r)
