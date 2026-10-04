#!/usr/bin/python3
"""Part 6: multi-account mixes recomputed from the independent arrays (same start day, one eval per account)."""
import json
import numpy as np
from pathlib import Path
import verify_indep as V

R = Path(__file__).resolve().parent
OUT = R / "out"
res = json.load(open(OUT / "portfolio_results.json"))
multi = json.load(open(OUT / "portfolio_multi_final.json"))["mixes"]
PM = {"lucid": "realized", "lucidpro": "realized", "lucidpro_nodll": "realized", "apex": "intraday", "apex_eod": "intraday"}
cache, CAL = {}, None


def arrays(f, lab):
    global CAL
    k = (f, lab)
    if k not in cache:
        F = res["firms"][f]
        pool = {c["cid"]: c for c in F["pool"]}
        key = {"pf": "portfolio"}.get(lab, lab)
        rep = F["reports"][key]
        members = [(pool[m["name"]]["src"], pool[m["name"]]["sess"], m["micros"]) for m in rep["members"]]
        c = rep["cell"]
        rules = {a: c[a] for a in ("day_lock", "day_take", "day_stop", "max_day_tr", "target_take")}
        sp = V.Spec(f, members, rules, CAL)
        CAL = CAL or sp.cal
        cache[k] = sp.arrays()
    return cache[k]


def mix(accts, which):
    o = np.stack([arrays(f, l)[PM[f] if which == "primary" else which][0] for f, l in accts], 1)
    d = np.stack([arrays(f, l)[PM[f] if which == "primary" else which][1] for f, l in accts], 1)
    ps = o == 1
    return {"p_any5": float(ps.any(1).mean()), "by_day": [float((ps & (d <= k)).any(1).mean()) for k in range(1, 6)], "e_funded": float(ps.sum(1).mean())}


for n, v in multi.items():
    accts = []
    for a in v["accounts"]:
        f, lab = a.split(":", 1)
        accts.append((f, lab))
    prim = mix(accts, "primary")
    eod, intr = mix(accts, "eod"), mix(accts, "intraday")
    base = [tuple(a.split(":", 1)) for a in v["same_strategy_baseline"]["accounts"]]
    bprim = mix(base, "primary")
    rp = v["primary"]
    print(f"N={n}: P(>=1 pass<=5d) mine {prim['p_any5']:.4f} rep {rp['p_any5']:.4f} | eod {eod['p_any5']:.4f} rep {v['eod']['p_any5']:.4f} | intr {intr['p_any5']:.4f} rep {v['intraday']['p_any5']:.4f} | "
          f"by-day {[round(x, 3) for x in prim['by_day']]} rep {[round(x, 3) for x in rp['p_any_by_day']]} | E[funded] {prim['e_funded']:.3f} rep {rp['e_funded']:.3f} | baseline {bprim['p_any5']:.4f} rep {v['same_strategy_baseline']['primary']['p_any5']:.4f}")
