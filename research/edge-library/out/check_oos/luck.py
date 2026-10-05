"""How often does a NO-EDGE table pass a year's tests (4)-(6)? Each control seed on disk (random minute / random entries, same
exits, same days) is judged as if it were the strategy: (4) average and median variant > 0; (5) average > the mean of the OTHER
seeds (+ for a day filter: per trade better on the filter days than on all days); (6) average still > 0 after the real unit's own
stress cost per trade (average - stressed average, per trade) x the placebo's trades. Only stores the analyst already read."""
import json, glob
import numpy as np
import chk as C
R = {}
for f in sorted(glob.glob("res/*.json")):
    r = json.load(open(f)); R[r["unit"]] = r
out = {}
tot = {"check": [0, 0], "exam": [0, 0], "pick": [0, 0]}
for k, u in enumerate(C.UNITS):
    a = C.addr(u); r = R[a]
    fam, root, tf, sess, grp = u
    days = C.event_days(grp) if grp else None
    timed = fam.startswith("straddle")
    bst, brec, rows, judged, cnt = C.build_table(u, days)
    ids = [x["id"] for x in judged]
    for per in ("pick", "check", "exam"):
        if per not in r:
            continue
        y = r[per]
        h = (y["avg"] - y["stress_avg"]) / max(1.0, y["avg_trades"])           # the real unit's stress cost per trade
        if timed:
            S = C.shift_seeds(u, per, ids)
            tabs = {sd: [C.cell(C.load(rr), pre + i, None, days) for i in ids] for sd, (rr, pre) in S.items()}
            tabs_all = {sd: [C.cell(C.load(rr), pre + i, None, None) for i in ids] for sd, (rr, pre) in S.items()} if grp else None
        else:
            xids = sorted({i.rsplit("_", 1)[-1] for i in ids})
            S = C.c1_seeds(u, per, xids)
            tabs = {sd: [C.cell(C.load(rr), pre + x, sess, None) for x in xids] for sd, (rr, pre) in S.items()}
            tabs_all = None
        avg = {sd: float(np.mean([x["net"].sum() for x in t])) for sd, t in tabs.items()}
        med = {sd: float(np.median([x["net"].sum() for x in t])) for sd, t in tabs.items()}
        ntr = {sd: float(np.mean([len(x["net"]) for x in t])) for sd, t in tabs.items()}
        npass = n4 = n45 = 0
        for sd in tabs:
            t4 = avg[sd] > 0 and med[sd] > 0
            t5 = avg[sd] > np.mean([v for s2, v in avg.items() if s2 != sd])
            if grp:
                tn = sum(x["net"].sum() for x in tabs[sd]); tc = sum(len(x["net"]) for x in tabs[sd])
                an = sum(x["net"].sum() for x in tabs_all[sd]); ac = sum(len(x["net"]) for x in tabs_all[sd])
                t5 = t5 and tc > 0 and (tn / tc) > (an / max(1, ac))
            t6 = avg[sd] - h * ntr[sd] > 0
            n4 += t4; n45 += (t4 and t5); npass += (t4 and t5 and t6)
        out[f"{a}|{per}"] = {"seeds": len(tabs), "pass4": n4, "pass45": n45, "pass456": npass, "stress_cost_per_trade": h}
        tot[per][0] += npass; tot[per][1] += len(tabs)
        print(a.ljust(38), per.ljust(5), "seeds", len(tabs), "pass (4):", n4, " (4)+(5):", n45, " (4)-(6):", npass, " stress cost/trade $", round(h, 1), flush=True)
for per, (p, n) in tot.items():
    print(per, "placebo tables passing (4)-(6):", p, "of", n, "=", round(p / max(1, n), 3))
json.dump(out, open("luck.json", "w"), indent=1, default=float)
