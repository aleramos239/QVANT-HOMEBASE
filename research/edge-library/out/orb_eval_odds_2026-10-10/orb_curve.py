"""Read-only: for a few stored ORB boxes, the odds to pass the eval within N trading days (both rows, best size at each N)."""
import sys, os
ROOT = "/Users/ramoscapital/ramos-quant-homebase/research/edge-library"
sys.path.insert(0, ROOT); os.chdir(ROOT)
import numpy as np
import judge as J
from blueprint import pipe_stages as S, tables as T, pipe_rules as PR, propodds as PO
P = PO.app(); r = P.load_rules(PR.need("prop", "account")); ev, fu = PO.steps(r)
H = PO.horizon(r); NS = [30, 45, 60, 90, 120, 180, H]
print("horizon", H, "sizes", ev)
boxes = [("nq_orb_stops", "nq_orb_stops_a5", c) for c in ("or_min15_pts45-r0", "or_min15_pts45-r3", "or_min15_atr3-r2", "or_min30_pts45-r2", "or_min15_pts45-r1")] + \
        [("nq_ib_break_mid", "nq_ib_break_mid_a5", "ib_min60_pts45-r2"), ("nq_pm_follow_long", "nq_pm_follow_long_a5", "or_min30_pts45-r3")]
for name, sub, c in boxes:
    kw = S._kw(name, {}); spec, plan, specs = S._idea(sub, kw); t = S._table(specs[0], plan, kw); cal = T.build_days(t["_u"], kw["days"])
    x = J.cellx(t["_st"], c, t["_u"]["sess"], t["_u"])
    res = {k: {n: (0, 0, 0) for n in NS} for k in ("raw", "worse")}
    for size in ev:
        net, traded, opn, _ = PO.days(PO.ledger(x, size, r), r, cal)
        idx = PO.draws(len(net), P.N_PATHS, H, P.SEED)
        for k, (a, o) in {"raw": (net, opn), "worse": PO.worse(net, traded, opn)}.items():
            e = PO.eval_walk(a[idx], traded[idx], o[idx], r)
            for n in NS:
                p = float(((e["outcome"] == PO.PASS) & (e["day"] <= n)).mean())
                b = float(((e["outcome"] == PO.BUST) & (e["day"] <= n)).mean())
                if p > res[k][n][0]: res[k][n] = (p, size, b)
    print(f"\n{sub} {c}: {len(x['net'])} trades, avg ${np.mean(x['net']):.0f}, win {np.mean(x['net']>0):.0%}")
    for k in res:
        print(f"  {k:5s} " + "  ".join(f"{n}d {res[k][n][0]:.0%}@{res[k][n][1]}(bust {res[k][n][2]:.0%})" for n in NS), flush=True)
