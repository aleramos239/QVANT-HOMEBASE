"""Read-only: the 30-day eval odds of every box of stored ORB heat maps (build days). Runs no backtest."""
import sys, json, time, os
ROOT = "/Users/ramoscapital/ramos-quant-homebase/research/edge-library"
sys.path.insert(0, ROOT); os.chdir(ROOT)
import numpy as np
import judge as J
from blueprint import pipe_stages as S, pipe_prop as PP, pipe_store as PS, tables as T, pipe_rules as PR

names = sys.argv[2].split(",")
acct = sys.argv[1] if sys.argv[1] != "-" else None
out = []
for name in names:
    st1 = PS.stages(name, None).get(1)
    if not st1: print("no stage 1", name); continue
    kw = S._kw(name, {})
    for tb in st1["tables"]:
        sub = tb["sub"]
        t0 = time.time()
        try:
            spec, plan, specs = S._idea(sub, kw)
            t = S._table(specs[0], plan, kw)
        except Exception as e:
            import traceback; traceback.print_exc(); continue
        cal = T.build_days(t["_u"], kw["days"])
        rows = {r["id"]: r for r in J.table(t["_st"], t["_u"])}
        for c in t["ids"]:
            x = J.cellx(t["_st"], c, t["_u"]["sess"], t["_u"])
            n = len(x["net"])
            if n < 100: continue
            o = PP.odds(x, cal, acct)
            out.append({"sub": sub, "cell": c, "n": n, "avg": float(np.mean(x["net"])), "net": float(np.sum(x["net"])),
                        "eval": o["eval"], "size": o["size"], "payout": o["payout"], "psize": o["payout_size"]})
        print(sub, len(t["ids"]), "boxes", round(time.time() - t0, 1), "s", flush=True)
json.dump(out, open(sys.argv[3], "w"))
out.sort(key=lambda r: -r["eval"])
for r in out[:25]:
    print(f"{r['sub']:24s} {r['cell']:28s} n={r['n']:5d} avg=${r['avg']:7.1f} eval={r['eval']:.3f} @{r['size']} payout={r['payout']:.3f} @{r['psize']}")
