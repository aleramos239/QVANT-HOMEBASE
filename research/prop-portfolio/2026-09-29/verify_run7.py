#!/usr/bin/python3
"""Part 7: stitched OOS P5 of the stored walk-forward picks (fixed-set and reselect) recomputed with the independent walk; each quarter's start days
are those whose first session lies in the quarter; the quarter's pick (members, micros, rules cell) comes from the stored WF files."""
import json, datetime as dt
import numpy as np
from pathlib import Path
import verify_indep as V

R = Path(__file__).resolve().parent
OUT = R / "out"
res = json.load(open(OUT / "portfolio_results.json"))
PM = {"lucid": "realized", "lucidpro": "realized", "lucidpro_nodll": "realized", "apex": "intraday", "apex_eod": "intraday"}
Q = [(y, q) for y in (2022, 2023, 2024) for q in (1, 2, 3, 4) if (y, q) >= (2022, 3)]
cache, CAL = {}, None


def bounds(y, q):
    m = 3 * (q - 1) + 1
    return dt.date(y, m, 1).toordinal(), (dt.date(y, m + 3, 1) if q < 4 else dt.date(y + 1, 1, 1)).toordinal()


def run(f, members, cell, cal):
    key = (f, tuple(members), tuple(sorted(cell.items())))
    if key not in cache:
        rules = {k: cell[k] for k in ("day_lock", "day_take", "day_stop", "max_day_tr", "target_take")}
        sp = V.Spec(f, list(members), rules, cal)
        cache[key] = sp.arrays((PM[f],))[PM[f]]
    return cache[key]


out = {}
for f, F in res["firms"].items():
    pool = {c["cid"]: c for c in F["pool"]}
    mem_of = lambda name: (pool[name]["src"], pool[name]["sess"])
    sp0 = V.Spec(f, [(pool[F["reports"]["single"]["members"][0]["name"]]["src"], pool[F["reports"]["single"]["members"][0]["name"]]["sess"], 10)], {}, CAL)
    CAL = CAL or sp0.cal
    cal = np.array(CAL)
    S = len(cal) - 4
    wf = json.load(open(OUT / f"portfolio_wffixed_{f}_final.json"))
    wr = json.load(open(OUT / f"portfolio_wfres_{f}_final.json"))["portfolio_reselect"]
    row = {}
    for lab in ("single", "best2", "portfolio"):
        rep = F["reports"][lab]
        names = [m["name"] for m in rep["members"]]
        flags, oos_idx = [], []
        for j, (y, q) in enumerate(Q):
            a, b = bounds(y, q)
            idx = np.flatnonzero((cal[:S] >= a) & (cal[:S] < b))
            pk = wf[f"{lab}_fixed"]["picks"][j]
            mem = [(*mem_of(n), mi) for n, mi in zip(names, pk["micros"])]
            o, d = run(f, mem, pk["cell"], CAL)
            flags.append((o[idx] == 1).astype(float))
        x = np.concatenate(flags)
        row[f"{lab}_fixed"] = {"mine": float(x.mean()), "stored": wf[f"{lab}_fixed"]["oos_p5"], "n": int(len(x))}
    flags = []
    for j, (y, q) in enumerate(Q):
        a, b = bounds(y, q)
        idx = np.flatnonzero((cal[:S] >= a) & (cal[:S] < b))
        pk = wr["picks"][j]
        mem = [(*mem_of(n), mi) for n, mi in pk["members"]]
        o, d = run(f, mem, pk["cell"], CAL)
        flags.append((o[idx] == 1).astype(float))
    x = np.concatenate(flags)
    row["reselect"] = {"mine": float(x.mean()), "stored": wr["oos_p5"], "n": int(len(x))}
    out[f] = row
    print(f"{f:15s} " + "  ".join(f"{k}: mine {v['mine']:.4f} stored {v['stored']:.4f} (n={v['n']})" for k, v in row.items()), flush=True)
json.dump(out, open(OUT / "verify_part7.json", "w"), indent=1)
