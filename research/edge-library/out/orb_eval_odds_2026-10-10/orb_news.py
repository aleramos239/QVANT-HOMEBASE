"""Read-only: the stored 08:30 breakout boxes (gold and NQ pre-market ORB / straddle), on 08:30 RELEASE DAYS ONLY (build days):
trades, win rate, average trade, and the 30-day eval odds on both rows. Runs no backtest."""
import sys, os, json
ROOT = "/Users/ramoscapital/ramos-quant-homebase/research/edge-library"
sys.path.insert(0, ROOT); os.chdir(ROOT)
import numpy as np
import judge as J
from blueprint import pipe_stages as S, tables as T, pipe_rules as PR, propodds as PO
P = PO.app(); r = P.load_rules(PR.need("prop", "account")); ev, fu = PO.steps(r); N = 30; H = PO.horizon(r)
def odds(x, cal):
    best = {"raw": (0, 0), "worse": (0, 0), "raw_any": (0, 0), "worse_any": (0, 0)}
    for size in ev:
        net, traded, opn, _ = PO.days(PO.ledger(x, size, r), r, cal)
        idx = PO.draws(len(net), P.N_PATHS, H, P.SEED)
        for k, (a, o) in {"raw": (net, opn), "worse": PO.worse(net, traded, opn)}.items():
            e = PO.eval_walk(a[idx], traded[idx], o[idx], r)
            p = float(((e["outcome"] == PO.PASS) & (e["day"] <= N)).mean()); q = float((e["outcome"] == PO.PASS).mean())
            if p > best[k][0]: best[k] = (p, size)
            if q > best[k + "_any"][0]: best[k + "_any"] = (q, size)
    return best
out = []
for item in sys.argv[2:]:
    name, sub, grp = item.split(":")
    ords = J.event_ords(grp)
    kw = S._kw(name, {}); spec, plan, specs = S._idea(sub, kw); t = S._table(specs[0], plan, kw); cal = T.build_days(t["_u"], kw["days"])
    for c in t["ids"]:
        x = J.cellx(t["_st"], c, t["_u"]["sess"], t["_u"])
        m = np.isin(np.asarray(x["date"], np.int64), ords)
        if m.sum() < 100: continue
        xs = {k: (np.asarray(v)[m] if hasattr(v, "__len__") and len(v) == len(m) else v) for k, v in x.items()}
        if xs["net"].mean() <= 0: continue
        b = odds(xs, cal)
        out.append({"sub": sub, "grp": grp, "cell": c, "n": int(m.sum()), "avg": float(xs["net"].mean()), "win": float((xs["net"] > 0).mean()),
                    "all_avg": float(np.mean(x["net"])), **{k: v[0] for k, v in b.items()}, **{k + "_size": v[1] for k, v in b.items()}})
    print(sub, grp, "done", len(t["ids"]), flush=True)
json.dump(out, open(sys.argv[1], "w"))
out.sort(key=lambda r: -r["worse"])
for r_ in out[:30]:
    print(f"{r_['sub']:20s} {r_['grp']} {r_['cell']:24s} n={r_['n']:4d} win={r_['win']:.2f} avg=${r_['avg']:6.0f} raw30={r_['raw']:.2f}@{r_['raw_size']} worse30={r_['worse']:.2f}@{r_['worse_size']} | no limit raw {r_['raw_any']:.2f}@{r_['raw_any_size']} worse {r_['worse_any']:.2f}@{r_['worse_any_size']}")
