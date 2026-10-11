"""Read-only: for the stored ORB boxes that make money, the eval odds within 30 days on BOTH rows (as tested / live is worse)
and win rate. Runs no backtest."""
import sys, json, os
ROOT = "/Users/ramoscapital/ramos-quant-homebase/research/edge-library"
sys.path.insert(0, ROOT); os.chdir(ROOT)
import numpy as np
import judge as J
from blueprint import pipe_stages as S, pipe_store as PS, tables as T, pipe_rules as PR, propodds as PO
P = PO.app(); r = P.load_rules(PR.need("prop", "account")); N = 30
ev, fu = PO.steps(r)
def both(x, cal):
    best = {"raw": (0, 0), "worse": (0, 0), "raw_any": (0, 0)}
    for size in ev:
        net, traded, opn, _ = PO.days(PO.ledger(x, size, r), r, cal)
        idx = PO.draws(len(net), P.N_PATHS, max(N, PO.horizon(r)), P.SEED)
        for k, (a, o) in {"raw": (net, opn), "worse": PO.worse(net, traded, opn)}.items():
            e = PO.eval_walk(a[idx[:, :N]], traded[idx[:, :N]], o[idx[:, :N]], r)
            p = float(((e["outcome"] == PO.PASS) & (e["day"] <= N)).mean())
            if p > best[k][0]: best[k] = (p, size)
            if k == "raw":
                e = PO.eval_walk(a[idx], traded[idx], o[idx], r)
                p = float((e["outcome"] == PO.PASS).mean())
                if p > best["raw_any"][0]: best["raw_any"] = (p, size)
    return best
out = []
for item in sys.argv[2:]:
    name, sub = item.split(":")
    kw = S._kw(name, {})
    spec, plan, specs = S._idea(sub, kw)
    t = S._table(specs[0], plan, kw)
    cal = T.build_days(t["_u"], kw["days"])
    for c in t["ids"]:
        x = J.cellx(t["_st"], c, t["_u"]["sess"], t["_u"])
        n = len(x["net"])
        if n < 200 or np.mean(x["net"]) < 35: continue
        b = both(x, cal)
        out.append({"sub": sub, "cell": c, "n": n, "avg": float(np.mean(x["net"])), "win": float((x["net"] > 0).mean()), **{k: v[0] for k, v in b.items()}, **{k + "_size": v[1] for k, v in b.items()}})
    print(sub, "done", flush=True)
json.dump(out, open(sys.argv[1], "w"))
out.sort(key=lambda r: -r["raw"])
for r in out[:15]:
    print(f"{r['sub']:22s} {r['cell']:24s} n={r['n']:4d} avg=${r['avg']:6.1f} win={r['win']:.2f} raw30={r['raw']:.3f}@{r['raw_size']} worse30={r['worse']:.3f}@{r['worse_size']} raw_nolimit={r['raw_any']:.3f}@{r['raw_any_size']}")
