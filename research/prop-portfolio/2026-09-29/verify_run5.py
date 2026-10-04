#!/usr/bin/python3
"""Part 5: robustness of the best portfolios to the fill-optimism of the take rules (MFE must exceed the take trigger by b ticks per contract before it
counts as filled) and to the same-ms tie order of members."""
import json, sys
import numpy as np
from pathlib import Path
import verify_indep as V

R = Path(__file__).resolve().parent
OUT = R / "out"
res = json.load(open(OUT / "portfolio_results.json"))
PM = {"lucid": "realized", "lucidpro": "realized", "lucidpro_nodll": "realized", "apex": "intraday", "apex_eod": "intraday"}
rows = {}
CAL = None
for f, F in res["firms"].items():
    pool = {c["cid"]: c for c in F["pool"]}
    for lab in ("single", "portfolio"):
        rep = F["reports"][lab]
        members = [(pool[m["name"]]["src"], pool[m["name"]]["sess"], m["micros"]) for m in rep["members"]]
        c = rep["cell"]
        rules = {k: c[k] for k in ("day_lock", "day_take", "day_stop", "max_day_tr", "target_take")}
        line = {}
        for buf in (0, 1, 2, 4, 8):
            sp = V.Spec(f, members, rules, CAL, take_buf=buf)
            CAL = CAL or sp.cal
            arr = sp.arrays((PM[f], "intraday", "eod"))
            line[buf] = {m: V.metrics(*arr[m]) for m in arr}
        # reversed tie order (members listed in reverse)
        sp = V.Spec(f, members[::-1], rules, CAL)
        arr = sp.arrays((PM[f],))
        tie = V.metrics(*arr[PM[f]])
        rows[f"{f}:{lab}"] = {"buf": line, "tie_reversed": tie}
        m = PM[f]
        print(f"{f:15s} {lab:9s} {m:9s} " + "  ".join(f"b{b}: {line[b][m]['p1']:.2f}/{line[b][m]['p3']:.2f}/{line[b][m]['p5']:.3f}" for b in line)
              + f" | tie-reversed P5 {tie['p5']:.3f} (b0 {line[0][m]['p5']:.3f})", flush=True)
json.dump(rows, open(OUT / "verify_part5.json", "w"), indent=1)
