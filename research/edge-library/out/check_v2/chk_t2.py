"""CHECKER v2, BUILD test (2) looked at harder, my own code. For every unit the first pass drew a control for:
 a) c1 with K = 4000 coupled table draws (20 batches of 200, my seeds) -> a p that does not move with the seed;
 b) the SAME test with the thinness of the control put back in. The analyst's draws only shuffle what is inside 2 seeds:
    - shift / c2 (2 seeds mixed by day): day-mix sd = sigma / sqrt(2), and the centre (mean of 2 seeds) is itself off by
      sigma / sqrt(2). A fresh random table minus that centre has sd = sigma * sqrt(1.5) = day-mix sd * sqrt(3).
    - c1 (k trades a day drawn from the n pool slots of that day, no replacement): draw variance k S^2 (1 - k/n); a fresh
      random table minus the pool centre has k S^2 (1 + k/n). Summed over days from the slot values themselves.
    z_fair = lift / fair sd, p_fair = Phi(z_fair).
BUILD stores only.   python chk_t2.py"""
import json
import math
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chk_lib as C  # noqa: E402
from chk_build import my_controls, sd  # noqa: E402


def phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def c1_fair(st, u, ids, pu, seeds=(1, 2)):
    """Analytic day-by-day variance of the coupled table draw (as drawn) and of a fresh random table minus the pool centre."""
    sess, dm = u["sess"], C.day_filter(u)
    xids = sorted({c.rsplit("_", 1)[-1] for c in ids})
    mem = {c: C.cell(st, c, sess, dm)["date"].astype(np.int64) for c in ids}
    pool_days = [C.cell(pu, f"s{s}_{x}", sess)["date"].astype(np.int64) for x in xids for s in seeds if f"s{s}_{x}" in pu["idx"]]
    days = np.unique(np.concatenate(pool_days + list(mem.values()) + [np.zeros(0, np.int64)]))
    R = C._max_rank(pu, sess, xids, seeds)
    D, S, V = len(days), len(seeds) * R, len(ids)
    Y = np.zeros((D, S))            # table-level value of slot s on day d (every variant trading that day takes slot s)
    ok = np.ones((D, S), bool)
    ksum = np.zeros(D)
    nvar = np.zeros(D)
    for x in xids:
        M = C._pool_matrix(pu, sess, x, seeds, days, R)
        cnt = np.zeros(D)           # number of this exit's variants trading on day d ; trades of those variants
        for c in ids:
            if c.rsplit("_", 1)[-1] != x:
                continue
            ud, kk = np.unique(mem[c], return_counts=True)
            di = np.searchsorted(days, ud)
            cnt[di] += 1
            ksum[di] += kk
            nvar[di] += 1
        use = cnt > 0
        ok[use] &= ~np.isnan(M[use])
        Y[use] += cnt[use, None] * np.nan_to_num(M[use]) / V
    act = nvar > 0
    k = np.where(act, ksum / np.maximum(nvar, 1), 0.0)
    n = ok.sum(axis=1).astype(float)
    Ym = np.where(ok, Y, np.nan)
    with np.errstate(invalid="ignore"):
        S2 = np.nanvar(Ym, axis=1, ddof=1)
    est = act & (n >= 2) & np.isfinite(S2)
    S2f = np.where(est, S2, np.nan)
    imp = float(np.nanmean(S2f[act])) if est.any() else 0.0
    S2u = np.where(est, S2, imp)
    kk_ = np.minimum(k, n)
    drawn = np.where(act & est, k * S2u * np.clip(1 - kk_ / np.maximum(n, 1), 0, None), 0.0).sum()
    fair = np.where(act, k * S2u * (1 + np.where(est, kk_ / np.maximum(n, 1), 1.0)), 0.0).sum()
    return {"sd_drawn_formula": float(np.sqrt(drawn)), "sd_fair": float(np.sqrt(fair)), "n_on_trade_days": float(n[act].mean()) if act.any() else 0.0,
            "k_on_trade_days": float(k[act].mean()) if act.any() else 0.0, "days_traded": int(act.sum()), "days_no_spread": int((act & ~est).sum())}


def one(job):
    key, us = job
    st = C.build_store(key)
    out = []
    for u in us:
        ts = C.tstats(C.build_rows(st, u))
        r = {"uid": u["uid"], "src": u["src"], "avg": ts["avg"], "share": ts["share"], "det": {}}
        for c in my_controls(u):
            if c == "c1":
                pk = f"c1-{u['root']}-tf{u['tf']}"
                if not C.exists(pk):
                    continue
                pu = C.build_store(pk)
                dr = np.concatenate([C.c1_table(st, u, ts["ids"], pu, sd(u["uid"], f"c1-big-{b}"))["draws"] for b in range(20)])
                f = c1_fair(st, u, ts["ids"], pu)
                lift = ts["avg"] - float(dr.mean())
                r["det"][c] = {"K": len(dr), "lift": lift, "p_beat": float((ts["avg"] > dr).mean()), "sd_drawn": float(dr.std(ddof=1)), **f,
                               "z_drawn": lift / float(dr.std(ddof=1)), "z_fair": lift / f["sd_fair"] if f["sd_fair"] > 0 else None,
                               "p_fair": phi(lift / f["sd_fair"]) if f["sd_fair"] > 0 else None}
            elif c in ("shift", "c2"):
                if c == "shift":
                    sk = f"{u['base'] or u['family']}-{u['root']}-tf{u['tf']}-shift"
                    if not C.exists(sk):
                        continue
                    m = C.shift_table(C.build_store(sk), u, ts["ids"], "build", 1, )
                else:
                    k1, k2 = f"{u['key']}-c2s1", f"{u['key']}-c2s2"
                    if not (C.exists(k1) and C.exists(k2)):
                        continue
                    m = C.c2_table(C.build_store(k1), C.build_store(k2), u, ts["ids"], "build", 1)
                if not m.get("ok"):
                    continue
                lift = ts["avg"] - m["mean"]
                sdf = m["sd_exact"] * math.sqrt(3)
                r["det"][c] = {"lift": lift, "raw": m["raw"], "p_beat": float((ts["avg"] > m["draws"]).mean()), "sd_drawn": m["sd_exact"], "sd_fair": sdf,
                               "z_drawn": lift / m["sd_exact"] if m["sd_exact"] > 0 else None, "z_fair": lift / sdf if sdf > 0 else None,
                               "p_fair": phi(lift / sdf) if sdf > 0 else None, "beats_both_seeds": bool(ts["avg"] > max(m["raw"]))}
        out.append(r)
    return out


def main():
    B = {r["uid"]: r for r in json.loads((C.OUT / "chk_build.json").read_text())}
    us = [u for u in C.units() if B[u["uid"]]["t2"] is not None]
    for u in us:
        u.pop("A")
    by = {}
    for u in us:
        by.setdefault(u["key"], []).append(u)
    with Pool(8) as pool:
        rows = [r for part in pool.imap_unordered(one, sorted(by.items()), chunksize=1) for r in part]
    (C.OUT / "chk_t2.json").write_text(json.dumps(rows))
    print("units", len(rows))


if __name__ == "__main__":
    main()
