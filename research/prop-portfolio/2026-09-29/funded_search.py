#!/usr/bin/python3
"""NQ funded search over out/candidates.csv configs (pass 2 + pass 3, >= 300 trades; deduped to unique (source cell, session)).

Run: PYTHONPATH=~/ramos-quant-homebase /usr/bin/python3 funded_search.py --stage s1|pick|s2|null|merge [--workers 4]

Variants (funded rule sets): flex (no DLL), flex_dll (soft $1,200, ASSUMED), pro_dll (soft $1,200), pro_nodll, apex (Apex PA, UNCONFIRMED,
compliance-filtered: OCO / both-side families, no target or stop > 5x target, MAE-rule cuts > 2% of trades are excluded).
Stage s1: coarse grid (128-192 cells, policies 500 / max) on every config x variant -> screen. pick: top K per variant by coarse raw E$40.
Stage s2: full funded.GRID on the picked pairs: e40_stable cell (score = min(own, median of +-1-step neighbours), ties fewer rules),
e40_raw / p20_stable / speed picks, alt breach models at the e40_stable cell, K day-matched random controls at that cell (lift), block-bootstrap CI,
and the offline quarterly walk-forward (select cell+rules+policy on the trailing 12 months of start days, test the next quarter, stitch).
Stage null: pseudo-configs (random-control seed runs thinned to a candidate stratum's trade count) through the same full search + walk-forward.
The day walks / lifecycles are funded.py's (memoised DaySrc, funded.simulate); this module only adds per-start arrays so one grid pass serves
the full-sample search and every walk-forward window. Desk-window rule: funded.desk_window_wait() before every cell.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import itertools
import json
import os
import sys
import time
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E          # noqa: E402
import funded as F            # noqa: E402
import a3p3 as A3             # noqa: E402
import a3_pass2 as A2         # noqa: E402
import screen_analyze as SA   # noqa: E402

OUT = E.D / "out"
H = F.H_LIFE
# FS_VARIANTS=pro_dll[,...] (env, inherited by the spawn workers; CLI --variants) restricts s1 / null to those variants (re-runs after a rule fix)
ONLY = set(filter(None, os.environ.get("FS_VARIANTS", "").split(","))) or None
VARIANTS = {"flex": ("flex", None), "flex_dll": ("flex", 1200), "pro_dll": ("pro", 1200), "pro_nodll": ("pro", 0), "apex": ("apex", None)}
AXES = F.AXES
K_PICK = 150
K_CTRL = 8
N_NULL = 60
CUT_OK = 0.02
MODELS_ALT = {"lucid": ("realized", "eod", "intraday"), "apex": ("pess", "nat", "opt")}
WF_FIRST = dt.date(2022, 10, 1)       # first test quarter start (12 months trailing selection window from the 2021-09-22 data start)

GRID_COARSE = {"micros": None, "day_take": [0, 250, 600, 1000], "day_lock": [0, 600], "day_stop": [0, 600], "max_day_tr": [1, 0],
               "policy": [500, "max"]}
MICROS_COARSE = {"lucid": [20, 40], "apex": [30, 50, 100]}


def spec(v):
    f, d = VARIANTS[v]
    return F.make_spec(f, d)


def kind(v):
    return "apex" if v == "apex" else "lucid"


def grid_of(S, g):
    g = {**F.GRID, **(g or {})}
    g["micros"] = [m for m in (g["micros"] or F.default_micros(S)) if m <= S.cap]
    return g


# ------------------------------------------------------------------ candidates

def load_cands():
    import pandas as pd
    d = pd.read_csv(OUT / "candidates.csv", low_memory=False)
    srcs = {s[3]: s for s in A3.sources3()}
    srcs.update({s[3]: s for s in A3.sources2()})
    fi = json.loads(E.PL.shared("family_inputs.json").read_text())
    cands = {}
    for r in d.to_dict("records"):
        k = (r["key"], r["sess"])
        c = cands.get(k)
        if c is None:
            src, fam, tf, key, params = srcs[r["key"]]
            prof = E.profile_from(fam, dict(params, tf=tf))
            dflt = {row[0]: row[2] for row in fi.get(fam, []) if len(row) > 3}
            inputs = {**{a: b for a, b in dflt.items() if a in ("sq_type", "mode")}, **params, "tgt_r": prof["tgt_r"]}
            c = cands[k] = dict(cid=f"{r['key']}|{r['sess']}", key=r["key"], sess=r["sess"], src=src, fam=fam, tf=tf, params=params, prof=prof,
                                trades=int(r["trades"]), net_1nq=float(r["net_1nq"]), fastpass=int(r["fastpass"]), pool_group=r["pool_group"],
                                apex_cfg_flags=F.apex_flags(fam, inputs, None, None), eval={})
        c["eval"][r["firm"]] = {k2: r[k2] for k2 in ("p5", "p5_ci_lo", "p5_ci_hi", "primary_model", "rules", "med_days", "bust5", "wf_oos_p5", "wf_oos_lift",
                                                      "wf_source", "lift_p5", "flags", "cost_per_funded", "evals_per_funded")}
    out = sorted(cands.values(), key=lambda c: -c["trades"])
    return out


def build_cfg_port(c):
    t = A2.load_src(c["src"])
    pl = A3.resolve(c["prof"])
    pool = A2.pool_of(pl["srcs"])
    cal = SA.cal_for(t, pool)
    idx = np.flatnonzero(t.sess == E.SESS_CODE[c["sess"]])
    return t, pl, pool, cal, idx, A2.port_of(t, idx, cal)


# ------------------------------------------------------------------ per-start grid

FIELDS = ("first", "g1", "n1", "n40", "n60", "bust", "npay", "cuts", "ex")


def start_arrays(res):
    """attempt tuples -> per-start arrays."""
    n = len(res)
    a = {k: np.zeros(n, np.float64) for k in FIELDS}
    for i, (b, pays, cuts, ex) in enumerate(res):
        a["bust"][i], a["cuts"][i], a["ex"][i], a["npay"][i] = b, cuts, ex, len(pays)
        if pays:
            a["first"][i], a["g1"][i], a["n1"][i] = pays[0]
            a["n40"][i] = sum(p[2] for p in pays if p[0] <= 40)
            a["n60"][i] = sum(p[2] for p in pays if p[0] <= H)
    return a


def grid_arrays(P, S, g, model=None, H_=H, starts=None):
    """All cells of grid g -> (combos list of (ix tuple incl. policy idx), dict field -> array [ncell, nstart]). desk window honoured."""
    src_events = S.kind == "apex"
    cells, cols = [], {k: [] for k in FIELDS}
    for combo in itertools.product(*[range(len(g[a])) for a in AXES[:5]]):
        F.desk_window_wait()
        mi, tk, dl, ds, mt = (g[a][i] for a, i in zip(AXES[:5], combo))
        src = F.DaySrc(P, {"day_take": tk, "day_lock": dl, "day_stop": ds, "max_day_tr": mt}, mi, events=src_events)
        for pi, T in enumerate(g["policy"]):
            a = start_arrays(F.lifecycle(S, src, T, H_, model, starts))
            cells.append(combo + (pi,))
            for k in FIELDS:
                cols[k].append(a[k])
    return cells, {k: np.array(v) for k, v in cols.items()}


def agg(A, sel, H_=H):
    """Aggregate per-start arrays A[field] ([ncell, nstart]) over the start-index selection sel -> dict of [ncell] arrays (F.metrics semantics)."""
    first, g1, n1 = A["first"][:, sel], A["g1"][:, sel], A["n1"][:, sel]
    paid = first > 0
    cnt = paid.sum(1)
    out = {"p_pay_20": ((first > 0) & (first <= 20)).mean(1), "p_pay_40": ((first > 0) & (first <= 40)).mean(1), "p_pay_60": paid.mean(1),
           "e_first_gross": g1.mean(1), "e_first_net": n1.mean(1), "e_net_40": A["n40"][:, sel].mean(1), "e_net_60": A["n60"][:, sel].mean(1),
           "p_bust_pre_first": ((A["bust"][:, sel] > 0) & ~paid).mean(1), "p_bust_any": (A["bust"][:, sel] > 0).mean(1),
           "e_npay_60": A["npay"][:, sel].mean(1)}
    med = np.full(len(first), np.nan)
    chq = np.full(len(first), np.nan)
    for i in np.flatnonzero(cnt):
        med[i] = np.median(first[i][paid[i]])
        chq[i] = g1[i][paid[i]].mean()
    out["med_days_first"], out["e_cheque_if_paid"] = med, chq
    ex = A["ex"][:, sel].sum(1)
    out["cut_share"] = np.where(ex > 0, A["cuts"][:, sel].sum(1) / np.maximum(ex, 1), 0.0)
    return out


def shape_of(g):
    return tuple(len(g[a]) for a in AXES)


def stability(v, shape):
    """Median of the +-1-step neighbours on every axis (missing neighbours ignored) of the per-cell vector v (cells in itertools.product order)."""
    x = v.reshape(shape)
    st = []
    for ax in range(x.ndim):
        for d in (-1, 1):
            y = np.full_like(x, np.nan)
            src = [slice(None)] * x.ndim
            dst = [slice(None)] * x.ndim
            if d == 1:
                src[ax], dst[ax] = slice(1, None), slice(0, -1)
            else:
                src[ax], dst[ax] = slice(0, -1), slice(1, None)
            y[tuple(dst)] = x[tuple(src)]
            st.append(y)
    with np.errstate(all="ignore"):
        s = np.nanmedian(np.stack(st), axis=0)
    return np.where(np.isnan(s), x, s).reshape(-1)


def nrules(g, cells):
    return np.array([sum(bool(x) for x in (g["day_take"][c[1]], g["day_lock"][c[2]], g["day_stop"][c[3]], g["max_day_tr"][c[4]])) for c in cells])


def pick(score, nr, ok):
    """index of max score among ok cells, ties fewer rules, then first."""
    idx = np.flatnonzero(ok & ~np.isnan(score))
    if not len(idx):
        return None
    o = np.lexsort((idx, nr[idx], -score[idx]))
    return int(idx[o[0]])


def cell_dict(g, cell):
    mi, tk, dl, ds, mt, pi = (g[a][i] for a, i in zip(AXES, cell))
    return dict(micros=mi, day_take=tk, day_lock=dl, day_stop=ds, max_day_tr=mt, policy=pi)


def cellname(d):
    return f"m{d['micros']} K{d['day_take']} L{d['day_lock']} S{d['day_stop']} T{d['max_day_tr']} P{d['policy']}"


MET = ("p_pay_20", "p_pay_40", "p_pay_60", "med_days_first", "e_first_gross", "e_first_net", "e_cheque_if_paid", "e_net_40", "e_net_60",
       "p_bust_pre_first", "p_bust_any", "e_npay_60")


def row_at(M, i, pre=""):
    return {pre + k: (None if M[k][i] != M[k][i] else float(M[k][i])) for k in MET}


# ------------------------------------------------------------------ walk-forward (per-start arrays -> stitched OOS)

def quarters(cal):
    dts = [dt.date.fromordinal(int(o)) for o in cal]
    out, q = [], WF_FIRST
    while q <= dts[-1]:
        nq = dt.date(q.year + (q.month == 10), (q.month + 2) % 12 + 1, 1)
        out.append((q, nq))
        q = nq
    return dts, out


def walk_forward(A, g, cells, nr, ok_fn, cal, S, H_=H, train_days=365):
    """A: per-start arrays of the full grid. For each test quarter: select on the trailing 12 months (starts whose whole horizon lies before the
    quarter), test on starts inside the quarter (horizon may run on). -> dict(stitched metrics, per-quarter picks)."""
    dts, qs = quarters(cal)
    nS = A["first"].shape[1]
    shape = shape_of(g)
    picks, test_sel, test_cell = [], [], []
    for (q0, q1) in qs:
        tstarts = [s for s, d in enumerate(dts) if q0 <= d < q1 and s < nS]
        if len(tstarts) < 20:
            continue
        i0 = next(s for s, d in enumerate(dts) if d >= q0)
        lo = q0 - dt.timedelta(days=train_days)
        trs = [s for s, d in enumerate(dts) if d >= lo and s + H_ <= i0]
        if len(trs) < 60:
            continue
        M = agg(A, np.array(trs), H_)
        score = np.minimum(M["e_net_40"], stability(M["e_net_40"], shape))
        ci = pick(score, nr, ok_fn(M))
        if ci is None:
            continue
        picks.append(dict(q=f"{q0.year}Q{(q0.month - 1) // 3 + 1}", cell=cellname(cell_dict(g, cells[ci])), n_train=len(trs), n_test=len(tstarts),
                          train_e40=float(M["e_net_40"][ci]), micros=cell_dict(g, cells[ci])["micros"]))
        test_sel.append(np.array(tstarts))
        test_cell.append(ci)
    if not picks:
        return None
    sub = {k: np.concatenate([A[k][ci, ts] for ci, ts in zip(test_cell, test_sel)])[None, :] for k in FIELDS}
    M = agg(sub, np.arange(sub["first"].shape[1]), H_)
    out = {"n_test_starts": int(sub["first"].shape[1]), "quarters": len(picks), "picks": picks,
           "n_distinct_cells": len({p["cell"] for p in picks}), "train_e40_mean": float(np.mean([p["train_e40"] for p in picks]))}
    out.update({"oos_" + k: (None if M[k][0] != M[k][0] else float(M[k][0])) for k in MET + ("cut_share",)})
    out["test_cells"], out["test_sel"] = test_cell, test_sel
    return out


# ------------------------------------------------------------------ analysis of one (config, variant)

def block_ci(x, block=60, boots=500, seed=7):
    x = np.asarray(x, float)
    n = len(x)
    if n < 2:
        return None, None
    nb = -(-n // block)
    rg = np.random.default_rng(seed)
    st = rg.integers(0, max(1, n - block + 1), size=(boots, nb))
    idx = (st[:, :, None] + np.arange(block)[None, None, :]).reshape(boots, -1)[:, :n]
    m = x[idx].mean(1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def analyze(P, S, v, g, *, ctl_ports=None, do_wf=True, model=None):
    """Full grid for one (portfolio, variant) -> (row dict, wf dict)."""
    cells, A = grid_arrays(P, S, g, model)
    nS = A["first"].shape[1]
    allS = np.arange(nS)
    M = agg(A, allS)
    shape = shape_of(g)
    nr = nrules(g, cells)
    apex = S.kind == "apex"
    ok = (M["cut_share"] <= CUT_OK) if apex else np.ones(len(cells), bool)
    sc = {k: np.minimum(M[k], stability(M[k], shape)) for k in ("e_net_40", "p_pay_20")}
    stab = {k: stability(M[k], shape) for k in ("e_net_40", "p_pay_20")}
    sel = {"e40_stable": pick(sc["e_net_40"], nr, ok), "e40_raw": pick(M["e_net_40"], nr, ok), "p20_stable": pick(sc["p_pay_20"], nr, ok),
           "p20_raw": pick(M["p_pay_20"], nr, ok)}
    spd = ok & (M["p_pay_60"] >= 0.5) & ~np.isnan(M["med_days_first"])
    sp_idx = np.flatnonzero(spd)
    sel["speed"] = int(sp_idx[np.lexsort((-M["e_net_40"][sp_idx], M["med_days_first"][sp_idx]))[0]]) if len(sp_idx) else None
    prim = S.primary
    row = dict(variant=v, model=prim, grid_cells=len(cells), compliant_cells=int(ok.sum()), n_starts=nS)
    for nm, i in sel.items():
        if i is None:
            row[nm + "_cell"] = None
            continue
        row[nm + "_cell"] = cellname(cell_dict(g, cells[i]))
        if nm in ("e40_raw", "p20_stable", "p20_raw", "speed"):
            row[nm + "_e40"], row[nm + "_p20"], row[nm + "_p60"], row[nm + "_med"] = (float(M[k][i]) for k in ("e_net_40", "p_pay_20", "p_pay_60", "med_days_first"))
    i = sel["e40_stable"]
    if i is None:
        row["status"] = "no_compliant_cell" if apex else "no_cell"
        return row, None
    row["status"] = "ok"
    row.update(cell_dict(g, cells[i]))
    row["n_rules"] = int(nr[i])
    row.update(row_at(M, i))
    row["stab_e_net_40"], row["score_e_net_40"] = float(stab["e_net_40"][i]), float(sc["e_net_40"][i])
    row["cut_share"] = float(M["cut_share"][i])
    row["e40_ci_lo"], row["e40_ci_hi"] = block_ci(A["n40"][i])
    # alt breach models at the chosen cell
    cd = cell_dict(g, cells[i])
    src = F.DaySrc(P, {"day_take": cd["day_take"], "day_lock": cd["day_lock"], "day_stop": cd["day_stop"], "max_day_tr": cd["max_day_tr"]}, cd["micros"],
                   events=apex)
    alts = MODELS_ALT[kind(v)]
    for j, m in enumerate(alts[1:], 1):
        mm = F.metrics(F.lifecycle(S, src, cd["policy"], H, m), H)
        row[f"alt{j}_model"], row[f"alt{j}_e40"], row[f"alt{j}_p40"], row[f"alt{j}_p_bust_pre"] = m, mm["e_net_40"], mm["p_pay_40"], mm["p_bust_pre_first"]
    if ctl_ports:
        ce = []
        for cp in ctl_ports:
            cs = F.DaySrc(cp, {"day_take": cd["day_take"], "day_lock": cd["day_lock"], "day_stop": cd["day_stop"], "max_day_tr": cd["max_day_tr"]}, cd["micros"],
                          events=apex)
            mm = F.metrics(F.lifecycle(S, cs, cd["policy"], H, model), H)
            ce.append((mm["e_net_40"], mm["p_pay_40"]))
        ce = np.array(ce)
        row["ctrl_e40"], row["ctrl_e40_sd"], row["ctrl_p40"] = float(ce[:, 0].mean()), float(ce[:, 0].std(ddof=1)), float(ce[:, 1].mean())
        row["lift_e40"] = row["e_net_40"] - row["ctrl_e40"]
    wf = None
    if do_wf:
        wf = walk_forward(A, g, cells, nr, (lambda Mx: Mx["cut_share"] <= CUT_OK) if apex else (lambda Mx: np.ones(len(Mx["cut_share"]), bool)),
                          CAL_HOLDER[0], S)
        if wf:
            # the in-sample cell on the same test starts (look-ahead reference only)
            ts = np.concatenate(wf["test_sel"])
            row["is_e40_on_test_starts"] = float(A["n40"][i, ts].mean())
            for k in ("test_cells", "test_sel"):
                wf.pop(k)
            for k in ("n_test_starts", "quarters", "n_distinct_cells", "train_e40_mean") + tuple("oos_" + k for k in MET + ("cut_share",)):
                row["wf_" + k] = wf[k]
    return row, wf


CAL_HOLDER: list = []


def lift_ports(c, t, pool, cal, idx, K):
    sub = dict(date=t.date[idx], sess=t.sess[idx])
    cps, fb, ctd = A2.ctl_ports(sub, pool, cal, zlib.crc32(f"fund|{c['cid']}".encode()), K)
    return cps


# ------------------------------------------------------------------ tasks

def gate():
    F.desk_window_wait()


def cfg_meta(c):
    return dict(cid=c["cid"], key=c["key"], sess=c["sess"], fam=c["fam"], tf=c["tf"], params=json.dumps(c["params"], sort_keys=True), trades=c["trades"],
                net_1nq=c["net_1nq"], fastpass=c["fastpass"], pool_group=c["pool_group"])


def task_s1(c):
    gate()
    t, pl, pool, cal, idx, P = build_cfg_port(c)
    rows = []
    for v in VARIANTS:
        if ONLY and v not in ONLY:
            continue
        if v == "apex" and c["apex_cfg_flags"]:
            continue
        S = spec(v)
        g = grid_of(S, {**GRID_COARSE, "micros": MICROS_COARSE[kind(v)]})
        cells, A = grid_arrays(P, S, g)
        M = agg(A, np.arange(A["first"].shape[1]))
        ok = (M["cut_share"] <= CUT_OK) if S.kind == "apex" else np.ones(len(cells), bool)
        nr = nrules(g, cells)
        i = pick(M["e_net_40"], nr, ok)
        r = dict(cid=c["cid"], variant=v, cells=len(cells), compliant=int(ok.sum()))
        if i is not None:
            r.update(row_at(M, i))
            r["cell"] = cellname(cell_dict(g, cells[i]))
            r["cut_share"] = float(M["cut_share"][i])
        rows.append(r)
    return rows


def task_s2(a):
    c, variants = a
    gate()
    t, pl, pool, cal, idx, P = build_cfg_port(c)
    CAL_HOLDER[:] = [cal]
    cps = lift_ports(c, t, pool, cal, idx, K_CTRL)
    mae = {}
    rows = []
    for v in variants:
        S = spec(v)
        g = grid_of(S, None)
        row, wf = analyze(P, S, v, g, ctl_ports=cps)
        row.update(cfg_meta(c))
        if S.kind == "apex":
            row["mae_over_limit_share"] = F.mae_over_limit_share(P, row.get("micros"), S.half, S.mae_min) if row.get("micros") else None
            row["apex_flags"] = ";".join(F.apex_flags(c["fam"], {**c["params"], "tgt_r": c["prof"]["tgt_r"]}, {"day_stop": row.get("day_stop")},
                                                     row.get("cut_share")))
        if wf:
            row["wf_picks"] = ";".join(f"{p['q']}:{p['cell']}" for p in wf["picks"])
        rows.append(row)
    return rows


def pseudo_port(st):
    """Null pseudo-config: one random-control seed run's session trades thinned to n, on the pool's calendar."""
    pool_id, sess, n_req, rep, prof = st
    pl = A3.resolve(prof)
    seeds = list(zip(pl["keys"], pl["srcs"]))
    ident = f"fnull|{pool_id}|{sess}|{rep}"
    rg = np.random.default_rng(zlib.crc32(ident.encode()))
    t = None
    for i in rg.permutation(len(seeds)):
        t = A2.load_src(seeds[i][1])
        cand = np.flatnonzero(t.sess == E.SESS_CODE[sess])
        if len(cand) >= 300:
            break
    else:
        return None
    n = min(int(n_req), len(cand))
    sel = np.sort(rg.choice(cand, n, replace=False))
    pool = A2.pool_of([s for j, (k2, s) in enumerate(seeds) if j != i]) if len(seeds) > 1 else A2.pool_of([seeds[i][1]])
    cal = SA.cal_for(t, pool)
    return A2.port_of(t, sel, cal), cal, n, seeds[i][0]


def task_null(a):
    nid, st = a
    gate()
    r = pseudo_port(st)
    if r is None:
        return []
    P, cal, n, seed = r
    CAL_HOLDER[:] = [cal]
    rows = []
    for v in VARIANTS:
        if ONLY and v not in ONLY:
            continue
        S = spec(v)
        g = grid_of(S, None)
        row, wf = analyze(P, S, v, g, ctl_ports=None, do_wf=(nid < N_NULL_WF))
        row.update(dict(cid=f"null{nid}", kind="null", sess=st[1], trades=n, seed=seed, pool_id=st[0], tgt_r=st[4]["tgt_r"]))
        if wf:
            row["wf_picks"] = ";".join(f"{p['q']}:{p['cell']}" for p in wf["picks"])
        rows.append(row)
    return rows


N_NULL_WF = 20


# ------------------------------------------------------------------ stages

def rd(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]


def stage_s1(a):
    cs = load_cands()
    print(f"{len(cs)} unique configs; {sum(1 for c in cs if c['apex_cfg_flags'])} apex-noncompliant at config level", flush=True)
    if a.limit:
        cs = cs[a.offset:a.offset + a.limit]
    A2.run_ckpt(task_s1, cs, lambda c: c["cid"], a.workers, "s1", OUT / f"funded_s1{a.suffix}.jsonl")


def stage_pick(a):
    rows = [r for x in rd(OUT / f"funded_s1{a.suffix}.jsonl") for r in x["rows"]]
    by = {}
    for r in rows:
        if r.get("e_net_40") is not None:
            by.setdefault(r["variant"], []).append(r)
    sel = {}
    for v, rs in by.items():
        rs.sort(key=lambda r: -r["e_net_40"])
        for r in rs[:a.k]:
            sel.setdefault(r["cid"], []).append(v)
        print(v, "screened", len(rs), "top-K e40 >=", round(rs[min(a.k, len(rs)) - 1]["e_net_40"], 1), "max", round(rs[0]["e_net_40"], 1))
    (OUT / f"funded_pick{a.suffix}.json").write_text(json.dumps(sel))
    print(len(sel), "configs,", sum(len(v) for v in sel.values()), "pairs selected", flush=True)


def stage_s2(a):
    sel = json.loads((OUT / f"funded_pick{a.suffix}.json").read_text())
    cs = {c["cid"]: c for c in load_cands()}
    tasks = [(cs[k], v) for k, v in sel.items()]
    tasks.sort(key=lambda t: -t[0]["trades"] * len(t[1]))
    if a.shard:
        i, n = (int(x) for x in a.shard.split("/"))
        tasks = tasks[i::n]
    if a.limit:
        tasks = tasks[a.offset:a.offset + a.limit]
    print(f"s2: {len(tasks)} configs, {sum(len(t[1]) for t in tasks)} pairs", flush=True)
    A2.run_ckpt(task_s2, tasks, lambda t: t[0]["cid"], a.workers, "s2", OUT / f"funded_s2{a.suffix}.jsonl")


def stage_null(a):
    cs = load_cands()
    rg = np.random.default_rng(20260930)
    strata = []
    for rep in range(a.n_null):
        c = cs[int(rg.integers(len(cs)))]
        pid = json.dumps(A3.resolve(c["prof"])["profile"], sort_keys=True)
        strata.append((pid, c["sess"], c["trades"], rep, E.profile_from("random", json.loads(pid))))
    tasks = [(i, s) for i, s in enumerate(strata)]
    print(f"null: {len(tasks)} pseudo-configs", flush=True)
    A2.run_ckpt(task_null, tasks, lambda t: f"null{t[0]}", a.workers, "null", OUT / f"funded_null{a.suffix}.jsonl")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--k", type=int, default=K_PICK)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--shard", default="")
    ap.add_argument("--suffix", default="")
    ap.add_argument("--n-null", type=int, default=N_NULL)
    ap.add_argument("--variants", default="")
    a = ap.parse_args(argv)
    if a.variants:                                      # restrict s1 / null to these variants (spawn workers read the env var)
        os.environ["FS_VARIANTS"] = a.variants
        global ONLY
        ONLY = set(a.variants.split(","))
    {"s1": stage_s1, "pick": stage_pick, "s2": stage_s2, "null": stage_null}[a.stage](a)


if __name__ == "__main__":
    main()
