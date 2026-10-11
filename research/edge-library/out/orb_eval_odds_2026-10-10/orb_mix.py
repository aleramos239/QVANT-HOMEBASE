"""Read-only: the 30-day eval odds of several stored ORB boxes traded TOGETHER on one account (propodds.together), both rows."""
import sys, json, os, itertools
ROOT = "/Users/ramoscapital/ramos-quant-homebase/research/edge-library"
sys.path.insert(0, ROOT); os.chdir(ROOT)
import numpy as np
import judge as J
from blueprint import pipe_stages as S, tables as T, pipe_rules as PR, propodds as PO
P = PO.app(); r = P.load_rules(PR.need("prop", "account")); N = 30
ev, fu = PO.steps(r)
members = {"orb930": ("nq_orb_stops", "nq_orb_stops_a5"), "ib_mid": ("nq_ib_break_mid", "nq_ib_break_mid_a5"),
           "pm_long": ("nq_pm_follow_long", "nq_pm_follow_long_a5"), "str0830": ("nq_0830_straddle", "nq_0830_straddle_a1"),
           "mid_long": ("nq_or_mid_long", "nq_or_mid_long_a5")}
tabs = {}
for k, (name, sub) in members.items():
    kw = S._kw(name, {}); spec, plan, specs = S._idea(sub, kw); t = S._table(specs[0], plan, kw)
    tabs[k] = (t, T.build_days(t["_u"], kw["days"]))
main = {"orb930": "or_min15", "ib_mid": "ib_min60", "pm_long": "or_min30", "str0830": "off_atr0p5", "mid_long": "or_min30"}   # the middle setting of each
def cell(k, ex):
    t, cal = tabs[k]; c = f"{main[k]}_{ex}"
    assert c in t["ids"], (c, t["ids"][:5])
    return J.cellx(t["_st"], c, t["_u"]["sess"], t["_u"])
def odds(cells, cal):
    best = {"raw": (0, 0), "worse": (0, 0)}
    for size in ev:
        if size * len(cells) > r["cap_micros"]: break
        net, traded, opn, _ = PO.days(PO.together(cells, size, r, cal), r, cal)
        idx = PO.draws(len(net), P.N_PATHS, max(N, PO.horizon(r)), P.SEED)[:, :N]
        for kk, (a, o) in {"raw": (net, opn), "worse": PO.worse(net, traded, opn)}.items():
            e = PO.eval_walk(a[idx], traded[idx], o[idx], r)
            p = float(((e["outcome"] == PO.PASS) & (e["day"] <= N)).mean())
            if p > best[kk][0]: best[kk] = (p, size)
    return best
cal = sorted(set.intersection(*[set(map(str, c)) for _, c in tabs.values()]))
print("shared days", len(cal))
for ex in ("pts45-r2", "pts45-r3", "pts45-r0", "pts30-r2", "atr3-r2", "atr3-r0", "pts45-r1"):
    for combo in (("orb930",), ("orb930", "ib_mid"), ("orb930", "pm_long"), ("orb930", "ib_mid", "pm_long"), ("orb930", "ib_mid", "pm_long", "str0830"), ("orb930", "mid_long", "pm_long", "str0830")):
        cs = [cell(k, ex) for k in combo]
        b = odds(cs, cal)
        tot = sum(float(c["net"].sum()) for c in cs)
        print(f"{ex:9s} {'+'.join(combo):36s} net/contract ${tot:9.0f}  raw30 {b['raw'][0]:.3f}@{b['raw'][1]} each   worse30 {b['worse'][0]:.3f}@{b['worse'][1]} each", flush=True)
