"""Read-only: the best release-day 08:30 boxes (gold ORB, NQ straddle) and the NQ 09:30 ORB TOGETHER on one account. The boxes are the
best of their maps, picked after the fact: an optimistic ceiling, not a strategy."""
import sys, os
ROOT = "/Users/ramoscapital/ramos-quant-homebase/research/edge-library"
sys.path.insert(0, ROOT); os.chdir(ROOT)
import numpy as np
import judge as J
from blueprint import pipe_stages as S, tables as T, pipe_rules as PR, propodds as PO
P = PO.app(); r = P.load_rules(PR.need("prop", "account")); ev, fu = PO.steps(r); H = PO.horizon(r)
def get(name, sub, c, grp=None):
    kw = S._kw(name, {}); spec, plan, specs = S._idea(sub, kw); t = S._table(specs[0], plan, kw)
    x = J.cellx(t["_st"], c, t["_u"]["sess"], t["_u"])
    if grp:
        m = np.isin(np.asarray(x["date"], np.int64), J.event_ords(grp))
        x = {k: (np.asarray(v)[m] if hasattr(v, "__len__") and len(v) == len(m) else v) for k, v in x.items()}
    return x, set(map(str, T.build_days(t["_u"], kw["days"])))
G, cg = get("gc_orb_pre", "gc_orb_pre_a1", "or_min5_pct0p1-r2", "A")
Nq, cn = get("nq_0830_straddle", "nq_0830_straddle_a1", "off_atr1_atr1p5-r3", "A")
O, co = get("nq_orb_stops", "nq_orb_stops_a5", "or_min15_pts45-r0")
cal = sorted(cg & cn & co)
for label, cs in (("gold 08:30 ORB, release days", [G]), ("NQ 08:30 straddle, release days", [Nq]), ("both 08:30", [G, Nq]), ("both 08:30 + NQ 09:30 ORB", [G, Nq, O])):
    best = {}
    for size in ev:
        if size * len(cs) > r["cap_micros"]: break
        net, traded, opn, _ = PO.days(PO.together(cs, size, r, cal), r, cal)
        idx = PO.draws(len(net), P.N_PATHS, H, P.SEED)
        for k, (a, o) in {"raw": (net, opn), "worse": PO.worse(net, traded, opn)}.items():
            e = PO.eval_walk(a[idx], traded[idx], o[idx], r)
            for n in (30, 60, 90, H):
                p = float(((e["outcome"] == PO.PASS) & (e["day"] <= n)).mean())
                if p > best.get((k, n), (0, 0))[0]: best[(k, n)] = (p, size)
    print(f"{label:34s} " + " | ".join(f"{k} " + " ".join(f"{n}d {best[(k, n)][0]:.0%}@{best[(k, n)][1]}" for n in (30, 60, 90, H)) for k in ("raw", "worse")), flush=True)
