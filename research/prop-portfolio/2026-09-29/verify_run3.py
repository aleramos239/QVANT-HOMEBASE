#!/usr/bin/python3
"""Part 3: control portfolio audit. Rebuild each best portfolio's day-matched control portfolios (portfolio.Ctx.controls, trade generation as is),
check they carry the SAME micros / sessions / rules cell and the same trades-per-day-and-session as the real members, and recompute the controls'
P5 and the lift with the INDEPENDENT walk."""
import json, sys, time
import numpy as np
from pathlib import Path
import verify_indep as V
import evalcore as E
import portfolio as P
import portfolio_final as PF

R = Path(__file__).resolve().parent
OUT = R / "out"
res = json.load(open(OUT / "portfolio_results.json"))
firms = sys.argv[1].split(",") if len(sys.argv) > 1 else list(res["firms"])
labs = sys.argv[2].split(",") if len(sys.argv) > 2 else ["portfolio"]
rows = {}
for f in firms:
    F = res["firms"][f]
    ctx, pools = PF.make_ctx((f,))
    byname = {b.name: b for b in pools[f]}
    pool = {c["cid"]: c for c in F["pool"]}
    for lab in labs:
        rep = F["reports"].get(lab)
        if not rep or "lift" not in rep:
            continue
        t0 = time.time()
        mem = rep["members"]
        c = rep["cell"]
        rules = {k: c[k] for k in ("day_lock", "day_take", "day_stop", "max_day_tr", "target_take")}
        real_b = [byname[m["name"]] for m in mem]
        ctrls = [ctx.controls(b) for b in real_b]
        K = min(len(x) for x in ctrls)
        cal = [int(x) for x in ctx.cal]
        # structure checks
        struct = {"K": K, "same_micros": True, "per_day_session_counts_equal": True, "ctrl_trades": [], "real_trades": [b.n for b in real_b],
                  "pool_flags": rep["lift"].get("pool_flag")}
        rb = []
        for b in real_b:
            rb.append({})
            for d in b.d:
                rb[-1][int(d)] = rb[-1].get(int(d), 0) + 1
        for k in range(K):
            for mi, cc in enumerate(ctrls):
                cb = cc[k]
                cnt = {}
                for d in cb.d:
                    cnt[int(d)] = cnt.get(int(d), 0) + 1
                if cnt != rb[mi]:
                    # allowed shortfall: control may have fewer trades on a day only if the pool is short
                    short = sum(max(0, rb[mi].get(d, 0) - cnt.get(d, 0)) for d in rb[mi]); extra = sum(max(0, cnt.get(d, 0) - rb[mi].get(d, 0)) for d in cnt)
                    struct.setdefault("count_diffs", []).append((k, mi, short, extra))
                    struct["per_day_session_counts_equal"] = False
        # independent P5 of the K controls (identical micros + rules by construction of the Spec call below)
        cp = {m: [] for m in V.MODELS}
        for k in range(K):
            members = []
            for mi, cc in enumerate(ctrls):
                cb = cc[k]
                trades = [(int(cal[int(cb.d[i])]), int(cb.te[i]), int(cb.tx[i]), int(cb.side[i]), float(cb.g[i]), float(cb.mae[i]), float(cb.mfe[i])) for i in range(cb.n)]
                members.append((trades, "all", mem[mi]["micros"]))
            sp = V.Spec(f, members, rules, cal)
            arr = sp.arrays()
            for m in V.MODELS:
                cp[m].append((arr[m][0] == 1).astype(float))
        # real
        members = [(pool[m["name"]]["src"], pool[m["name"]]["sess"], m["micros"]) for m in mem]
        sp = V.Spec(f, members, rules, cal)
        arr = sp.arrays()
        out = {"struct": struct}
        for m in V.MODELS:
            real = (arr[m][0] == 1).astype(float)
            cm = np.mean(np.stack(cp[m]), 0)
            out[m] = {"real_p5": float(real.mean()), "ctrl_p5": float(cm.mean()), "lift": float((real - cm).mean()),
                      "reported_real": rep["lift"][m]["real_p5"], "reported_ctrl": rep["lift"][m]["ctrl_p5"], "reported_lift": rep["lift"][m]["lift"]}
        rows[f"{f}:{lab}"] = out
        d = max(abs(out[m][a] - out[m][b]) for m in V.MODELS for a, b in (("real_p5", "reported_real"), ("ctrl_p5", "reported_ctrl"), ("lift", "reported_lift")))
        print(f"{f:15s} {lab:9s} K={K} same_counts={struct['per_day_session_counts_equal']} maxdiff vs reported={d:.5f} flags={struct['pool_flags']} "
              + " ".join(f"{m}:lift {out[m]['lift']:+.3f}" for m in V.MODELS) + f" ({time.time()-t0:.0f}s)", flush=True)
        if "count_diffs" in struct:
            print("    count diffs (k, member, short, extra):", struct["count_diffs"][:6], flush=True)
json.dump(rows, open(OUT / "verify_part3.json", "w"), indent=1, default=str)
