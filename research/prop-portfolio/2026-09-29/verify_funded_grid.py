#!/usr/bin/python3
"""Independent check of one funded config's FULL grid search + quarterly walk-forward (funded_search.analyze): re-runs every grid cell with the
independent walk / lifecycle (verify_funded_indep), recomputes the neighbour-median stability, the e40_stable argmax (ties: fewer rules, then
first cell) and the walk-forward (trailing 12 months of starts whose whole horizon lies before the quarter -> next quarter, stitched OOS) and
compares with the row in out/funded_candidates.csv.   Usage: verify_funded_grid.py <variant> [rank]"""
import datetime as dt
import itertools
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
import evalcore as E            # noqa: E402
import funded as F              # noqa: E402  (grid definition + make_spec ONLY)
import funded_search as FS      # noqa: E402  (candidate loader only)
import verify_funded_indep as V # noqa: E402

AX = ("micros", "day_take", "day_lock", "day_stop", "max_day_tr", "policy")
H = 60


def per_start(kind, W, T, model, dll, nS):
    class S:
        n_days = W.n_days
        get = staticmethod(W.get)
    first, g1, n40, n60, bust, cuts, ex = (np.zeros(nS) for _ in range(7))
    for s in range(nS):
        b, pays, cu, e_ = V.ref_life(kind, S, s, H, T, model, dll=dll)
        bust[s], cuts[s], ex[s] = b, cu, e_
        if pays:
            first[s], g1[s] = pays[0][0], pays[0][1]
            n40[s] = sum(p[2] for p in pays if p[0] <= 40)
            n60[s] = sum(p[2] for p in pays if p[0] <= H)
    return dict(first=first, g1=g1, n40=n40, n60=n60, bust=bust, cuts=cuts, ex=ex)


def stab(vec, shape):
    x = np.asarray(vec).reshape(shape)
    out = np.zeros(shape)
    for ix in itertools.product(*[range(n) for n in shape]):
        nb = []
        for ax in range(len(shape)):
            for d in (-1, 1):
                j = list(ix)
                j[ax] += d
                if 0 <= j[ax] < shape[ax]:
                    nb.append(x[tuple(j)])
        out[ix] = np.median(nb) if nb else x[ix]
    return out.reshape(-1)


def main():
    v = sys.argv[1]
    rank = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    kind, dll = {"flex": ("flex", 0.0), "flex_dll": ("flex", 1200.0), "pro_dll": ("pro", 1200.0), "pro_nodll": ("pro", 0.0), "apex": ("apex", 0.0)}[v]
    df = pd.read_csv(E.D / "out" / "funded_candidates.csv", low_memory=False)
    r = V.top_rows(df, v, rank + 1)[rank]
    c = {x["cid"]: x for x in FS.load_cands()}[r["cid"]]
    cal = sorted({dt.date.fromisoformat(d).toordinal() for d in E.tape_sessions("2021-01-01", "2024-12-31")})
    days, _ = V.day_trades(c["src"], c["sess"], cal)
    S = FS.spec(v)
    g = FS.grid_of(S, None)
    shape = tuple(len(g[a]) for a in AX)
    model = "pess" if kind == "apex" else "realized"
    nS = len(cal) - H + 1
    cells, A = [], {k: [] for k in ("first", "g1", "n40", "n60", "bust", "cuts", "ex")}
    for combo in itertools.product(*[range(len(g[a])) for a in AX[:5]]):
        mi, tk, dl, ds, mt = (g[a][i] for a, i in zip(AX[:5], combo))
        W = V.RefWalk(days, mi, dict(day_take=tk, day_lock=dl, day_stop=ds, max_day_tr=mt), 0.5)
        for pi, T in enumerate(g["policy"]):
            a = per_start(kind, W, T, model, dll, nS)
            cells.append(combo + (pi,))
            for k in A:
                A[k].append(a[k])
    A = {k: np.array(x) for k, x in A.items()}
    nr = np.array([sum(bool(g[a][c_[i]]) for i, a in ((1, "day_take"), (2, "day_lock"), (3, "day_stop"), (4, "max_day_tr"))) for c_ in cells])

    def okm(sel):
        if kind != "apex":
            return np.ones(len(cells), bool)
        return A["cuts"][:, sel].sum(1) / np.maximum(A["ex"][:, sel].sum(1), 1) <= 0.02

    def agg(sel):
        e40 = A["n40"][:, sel].mean(1)
        return e40

    allS = np.arange(nS)
    e40 = agg(allS)
    st = stab(e40, shape)
    sc = np.where(okm(allS), np.minimum(e40, st), -np.inf)
    order = np.lexsort((np.arange(len(cells)), nr, -sc))
    i = int(order[0])
    cd = {a: g[a][ix] for a, ix in zip(AX, cells[i])}
    name = f"m{cd['micros']} K{cd['day_take']} L{cd['day_lock']} S{cd['day_stop']} T{cd['max_day_tr']} P{cd['policy']}"
    print(f"[{v}] {r['cid']}: independent argmax cell {name} score {sc[i]:.4f} e40 {e40[i]:.4f}   csv cell {r['e40_stable_cell']} score {r['score_e_net_40']:.4f}",
          "OK" if name == r["e40_stable_cell"] and abs(sc[i] - r["score_e_net_40"]) < 1e-6 else "MISMATCH")
    # other picks
    first = A["first"]
    p20 = ((first > 0) & (first <= 20)).mean(1)
    sp20 = np.where(okm(allS), np.minimum(p20, stab(p20, shape)), -np.inf)
    j = int(np.lexsort((np.arange(len(cells)), nr, -sp20))[0])
    cd2 = {a: g[a][ix] for a, ix in zip(AX, cells[j])}
    n2 = f"m{cd2['micros']} K{cd2['day_take']} L{cd2['day_lock']} S{cd2['day_stop']} T{cd2['max_day_tr']} P{cd2['policy']}"
    print(f"   p20_stable independent {n2} ({sp20[j]:.4f}) csv {r.get('p20_stable_cell')} ({r.get('p20_stable_p20')})", "OK" if n2 == r.get("p20_stable_cell") else "MISMATCH")
    # walk-forward
    dts = [dt.date.fromordinal(o) for o in cal]
    q, qs = FS.WF_FIRST, []
    while q <= dts[-1]:
        nq = dt.date(q.year + (q.month == 10), (q.month + 2) % 12 + 1, 1)
        qs.append((q, nq))
        q = nq
    picks, tsel, tcell = [], [], []
    for (q0, q1) in qs:
        tst = [s for s, d in enumerate(dts) if q0 <= d < q1 and s < nS]
        if len(tst) < 20:
            continue
        i0 = next(s for s, d in enumerate(dts) if d >= q0)
        lo = q0 - dt.timedelta(days=365)
        trs = [s for s, d in enumerate(dts) if d >= lo and s + H <= i0]
        if len(trs) < 60:
            continue
        e = A["n40"][:, trs].mean(1)
        scq = np.where(okm(np.array(trs)), np.minimum(e, stab(e, shape)), -np.inf)
        ci = int(np.lexsort((np.arange(len(cells)), nr, -scq))[0])
        cdq = {a: g[a][ix] for a, ix in zip(AX, cells[ci])}
        picks.append(f"{q0.year}Q{(q0.month - 1) // 3 + 1}:m{cdq['micros']} K{cdq['day_take']} L{cdq['day_lock']} S{cdq['day_stop']} T{cdq['max_day_tr']} P{cdq['policy']}")
        tsel.append(np.array(tst))
        tcell.append(ci)
    fi = np.concatenate([first[ci, ts] for ci, ts in zip(tcell, tsel)])
    n40 = np.concatenate([A["n40"][ci, ts] for ci, ts in zip(tcell, tsel)])
    bu = np.concatenate([A["bust"][ci, ts] for ci, ts in zip(tcell, tsel)])
    oos = dict(wf_oos_e_net_40=n40.mean(), wf_oos_p_pay_20=((fi > 0) & (fi <= 20)).mean(), wf_oos_p_bust_pre_first=((bu > 0) & ~(fi > 0)).mean())
    print("   WF picks match:", ";".join(picks) == (r["wf_picks"] if isinstance(r["wf_picks"], str) else ""), "| n_test", len(fi), "csv", r["wf_n_test_starts"])
    for k, x in oos.items():
        print(f"   {k}: indep {x:.6f} csv {float(r[k]):.6f}", "OK" if abs(x - float(r[k])) < 1e-6 else "MISMATCH")


if __name__ == "__main__":
    main()
