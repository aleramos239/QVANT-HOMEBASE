"""CHECKER v2: c1 control, fair spread with each exit cell's own slot count. Per day d: slot vectors z[x, s] (exit x, slot s;
slots = seed x n-th entry). cov[x, x'] = sample covariance over the slots both exits have (>= 2; else that pair's average
over the other days). Table weight c[x] = sum over the unit's variants with exit x of sqrt(trades that day) / V.
  var_rep    = c' cov c                       (spread of a FRESH random table)
  var_centre = c' (cov * N / (n n')) c        (how far the 2-seed pool average can sit from the truth)
  z_rep = lift / sqrt(sum var_rep) ; z_fair = lift / sqrt(sum var_rep + var_centre).   BUILD stores only."""
import json, math, sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import chk_lib as C


def phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def fair(st, u, ids, pu, seeds=(1, 2)):
    sess, dm = u["sess"], C.day_filter(u)
    xids = sorted({c.rsplit("_", 1)[-1] for c in ids})
    xi = {x: i for i, x in enumerate(xids)}
    mem = {c: C.cell(st, c, sess, dm)["date"].astype(np.int64) for c in ids}
    pool_days = [C.cell(pu, f"s{s}_{x}", sess)["date"].astype(np.int64) for x in xids for s in seeds if f"s{s}_{x}" in pu["idx"]]
    days = np.unique(np.concatenate(pool_days + list(mem.values()) + [np.zeros(0, np.int64)]))
    R = C._max_rank(pu, sess, xids, seeds)
    D, X, V = len(days), len(xids), len(ids)
    Z = np.stack([C._pool_matrix(pu, sess, x, seeds, days, R) for x in xids])        # [X, D, S]
    cw = np.zeros((X, D))
    for c in ids:
        ud, kk = np.unique(mem[c], return_counts=True)
        cw[xi[c.rsplit("_", 1)[-1]], np.searchsorted(days, ud)] += np.sqrt(kk) / V
    act = np.flatnonzero(cw.sum(axis=0) > 0)
    val = (~np.isnan(Z)).astype(float)
    Z0 = np.nan_to_num(Z)
    covs = np.full((len(act), X, X), np.nan)
    Ns = np.zeros((len(act), X, X))
    for j, d in enumerate(act):
        v, z = val[:, d, :], Z0[:, d, :]
        N = v @ v.T
        P = z @ z.T                              # sum over common slots of z_x z_x' (zeros where either is missing)
        Sx = z @ v.T                             # sum of z_x over slots x' also has
        with np.errstate(invalid="ignore", divide="ignore"):
            cov = (P - Sx * Sx.T / N) / (N - 1)
        cov[N < 2] = np.nan
        covs[j], Ns[j] = cov, N
    with np.errstate(invalid="ignore"):
        mean_cov = np.nanmean(covs, axis=0)
    mean_cov = np.nan_to_num(mean_cov)
    vr = vc = 0.0
    nlist, imputed = [], 0
    for j, d in enumerate(act):
        cov = np.where(np.isnan(covs[j]), mean_cov, covs[j])
        imputed += int(np.isnan(covs[j]).all())
        n = np.diag(Ns[j])
        w = cw[:, d]
        with np.errstate(invalid="ignore", divide="ignore"):
            share = np.where((n[:, None] * n[None, :]) > 0, Ns[j] / (n[:, None] * n[None, :]), 1.0)
        vr += float(w @ cov @ w)
        vc += float(w @ (cov * share) @ w)
        nlist.append(float((n * (w > 0)).sum() / max(1, (w > 0).sum())))
    return {"sd_rep": math.sqrt(max(vr, 0)), "sd_fair": math.sqrt(max(vr + vc, 0)), "slots_per_exit_on_trade_days": float(np.mean(nlist)) if nlist else 0.0,
            "days_traded": int(len(act)), "days_all_imputed": imputed}


def one(job):
    key, us = job
    st = C.build_store(key)
    out = []
    for u in us:
        ts = C.tstats(C.build_rows(st, u))
        pk = f"c1-{u['root']}-tf{u['tf']}"
        f = fair(st, u, ts["ids"], C.build_store(pk))
        out.append({"uid": u["uid"], "avg": ts["avg"], **f})
    return out


if __name__ == "__main__":
    T = {r["uid"]: r for r in json.loads((C.OUT / "chk_t2.json").read_text())}
    us = [u for u in C.units() if u["uid"] in T and "c1" in T[u["uid"]]["det"]]
    for u in us:
        u.pop("A")
    by = {}
    for u in us:
        by.setdefault(u["key"], []).append(u)
    with Pool(8) as pool:
        rows = [r for part in pool.imap_unordered(one, sorted(by.items()), chunksize=1) for r in part]
    for r in rows:
        d = T[r["uid"]]["det"]["c1"]
        r.update(lift=d["lift"], p_drawn=d["p_beat"], sd_drawn=d["sd_drawn"], z_drawn=d["z_drawn"], z_rep=d["lift"] / r["sd_rep"] if r["sd_rep"] else None,
                 z_fair=d["lift"] / r["sd_fair"] if r["sd_fair"] else None)
        r["p_rep"] = phi(r["z_rep"]) if r["z_rep"] is not None else None
        r["p_fair"] = phi(r["z_fair"]) if r["z_fair"] is not None else None
    (C.OUT / "chk_t2b.json").write_text(json.dumps(rows))
    print("units", len(rows))
