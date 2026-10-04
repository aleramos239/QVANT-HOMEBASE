#!/usr/bin/python3
"""Part 1: independent recompute of every reported portfolio (single/best2/portfolio, main + fast objective) vs portfolio_results.json + npz."""
import json, sys, time
import numpy as np
from pathlib import Path
import verify_indep as V
import evalcore as E

R = Path(__file__).resolve().parent
OUT = R / "out"
res = json.load(open(OUT / "portfolio_results.json"))
firms = sys.argv[1].split(",") if len(sys.argv) > 1 else list(res["firms"])
out = {}
CAL = None
for fam, tag, node in (("main", "_final", res["firms"]), ("fast", "_finalfast", res["fast_objective"]["firms"])):
    for f in firms:
        F = node[f]
        pool = {c["cid"]: c for c in F["pool"]}
        npz = np.load(OUT / f"portfolio_{f}{tag}.npz")
        for lab in ("single", "best2", "portfolio"):
            rep = F["reports"].get(lab)
            if not rep or "cell" not in rep:
                continue
            members = [(pool[m["name"]]["src"], pool[m["name"]]["sess"], m["micros"]) for m in rep["members"]]
            c = rep["cell"]
            rules = {"day_lock": c["day_lock"], "day_take": c["day_take"], "day_stop": c["day_stop"], "max_day_tr": c["max_day_tr"], "target_take": c["target_take"]}
            t0 = time.time()
            sp = V.Spec(f, members, rules, CAL)
            if CAL is None:
                CAL = sp.cal
            arr = sp.arrays()
            rowout = {"firm": f, "set": fam, "lab": lab, "members": [(m["name"], m["micros"]) for m in rep["members"]], "rules": rules, "D": sp.D}
            worst = 0.0
            for m in V.MODELS:
                mine = V.metrics(*arr[m])
                rep_m = rep[m]
                rowout[m] = {"mine": mine, "reported": {k: rep_m[k] for k in mine}}
                for k in mine:
                    worst = max(worst, abs(mine[k] - rep_m[k]))
                if f"{lab}|{m}|o" in npz:
                    o, d = npz[f"{lab}|{m}|o"], npz[f"{lab}|{m}|d"]
                    rowout[m]["attempt_mismatch"] = int(((o != arr[m][0]) | (d != arr[m][1])).sum())
            rowout["max_abs_diff"] = worst
            rowout["calendar_ok"] = sp.D == F["calendar_sessions"]
            out[f"{fam}:{f}:{lab}"] = rowout
            print(f"{fam:4s} {f:15s} {lab:9s} D={sp.D} maxdiff={worst:.5f} attempt_mismatch=" + ",".join(str(rowout[m].get('attempt_mismatch')) for m in V.MODELS) + f" ({time.time()-t0:.0f}s)", flush=True)
json.dump(out, open(OUT / "verify_part1.json", "w"), indent=1, default=str)
