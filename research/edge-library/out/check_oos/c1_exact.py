"""Exact expectation of the random-entry control mean (no Monte Carlo): for every variant and date with n trades, n x the mean
net of that date's pool for the same exit (all pool trades when the pool has <= n; shortfall = mean of the nearest dates' pool)."""
import json, sys
import numpy as np
import chk as C
out = {}
for k in (7, 8, 9, 10, 11, 12):
    u = C.UNITS[k]
    sess = u[3]
    bst, brec, rows, judged, cnt = C.build_table(u, None)
    ids = [r["id"] for r in judged]
    xids = sorted({i.rsplit("_", 1)[-1] for i in ids})
    for period in ("build", "pick", "check", "exam"):
        recs = [brec] if period == "build" else C.base_rec(u, period)
        if not recs:
            continue
        yst = C.load(recs[0])
        S = C.c1_seeds(u, period, xids)
        tot = 0.0; fb = 0; ntr = 0
        pools = {}
        for xid in xids:
            d = np.concatenate([C.cell(C.load(r), pre + xid, sess)["date"].astype(np.int64) for sd, (r, pre) in sorted(S.items())])
            n = np.concatenate([C.cell(C.load(r), pre + xid, sess)["net"].astype(float) for sd, (r, pre) in sorted(S.items())])
            ud, inv, cnt_ = np.unique(d, return_inverse=True, return_counts=True)
            sm = np.zeros(len(ud)); np.add.at(sm, inv, n)
            pools[xid] = (ud, cnt_, sm)
        nets = []
        for cid in ids:
            x = C.cell(yst, cid, sess)
            nets.append(float(x["net"].sum()))
            vd, vk = np.unique(x["date"].astype(np.int64), return_counts=True)
            ud, cn, sm = pools[cid.rsplit("_", 1)[-1]]
            ntr += int(vk.sum())
            for dte, kk in zip(vd, vk):
                j = np.searchsorted(ud, dte)
                own = cn[j] if j < len(ud) and ud[j] == dte else 0
                if own >= kk:
                    tot += kk * sm[j] / own
                    continue
                if own:
                    tot += sm[j]
                need = kk - own
                ok = ud != dte
                dist = np.abs(ud[ok] - dte)
                o = np.argsort(dist, kind="stable")
                cum = np.cumsum(cn[ok][o])
                cut = dist[o][min(int(np.searchsorted(cum, need, "left")), len(o) - 1)]
                m = dist <= cut
                tot += need * sm[ok][m].sum() / cn[ok][m].sum()
                fb += need
        avg = float(np.mean(nets))
        ctl = tot / len(ids)
        out[f"{C.addr(u)}|{period}"] = {"avg": avg, "ctl_mean_exact": ctl, "lift_exact": avg - ctl, "seeds": sorted(S), "fallback_share": fb / max(1, ntr)}
        print(C.addr(u), period, "avg", round(avg, 1), "exact control mean", round(ctl, 1), "exact lift", round(avg - ctl, 1), "seeds", len(S), "fallback", round(fb / max(1, ntr), 4), flush=True)
json.dump(out, open("c1_exact.json", "w"), indent=1)
