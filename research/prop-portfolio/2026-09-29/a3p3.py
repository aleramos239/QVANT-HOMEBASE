#!/usr/bin/python3
"""A3 pass 3: the NEW heat-maps (ledger stage 'sizing' keys hm2-* and fp-*) x session x 5 firms x 3 breach models, plus a re-score of the
pass-2 shortlists under the same machinery so candidates.csv is uniform.
Run: PYTHONPATH=~/ramos-quant-homebase /usr/bin/python3 a3p3.py --stage snap|quick|real|null|rescore2|all [--workers 4]

Machinery = a3_pass2 (frozen-snapshot ledger, day-matched controls from the exit-profile pool, stable cell = median of a cell and its +-1-step
neighbours on every axis, rule grids) with: firms lucid, lucidpro, lucidpro_nodll, apex (user rule set, UNCONFIRMED), apex_eod (site-consistent,
UNCONFIRMED); breach models eod / realized / intraday (PRIMARY per firm = evalcore.primary_model: Lucid* realized, Apex* intraday).
Per (config, firm) the search keeps, for every rule cell, P5 under the 3 models and P1/P3 under the primary model, and picks
  p5_eod / p5_realized / p5_intraday : the P5-stable cell of each model,
  speed_p1 / speed_p3                : the stable cell maximising P(pass<=1d) / P(pass<=3d) under the PRIMARY model.
Every picked cell is evaluated under ALL 3 models (P1,P2,P3,P5,bust5,median days) with block-bootstrap CIs, and against K day-matched random
controls at identical rules (lift = edge vs day-matched random = WARNING LABEL, not a filter). One output row per (config, firm, cellset).
Null = pseudo-configs (random seed runs thinned to the stratum's median trade count; controls from the other seeds), same analysis.
Rule grids: lucid / apex as a3_pass2; lucidpro* as a3p2_lp; apex_eod micros {20..60 step 10} x day_lock {0,1000,2000} x day_take {0,1500,2000,3000}
x day_stop {0,500,1000} (the rule-file $1,000 soft DLL applies automatically) x max_day_tr {1,0} x target_take {0,1}.
Desk-window rule: tasks call gate() first (nothing starts 09:06-09:36 ET weekdays)."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import shutil
import sys
import zlib
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E          # noqa: E402
import screen_analyze as SA   # noqa: E402
import a3_rules as A1         # noqa: E402
import a3_pass2 as A2         # noqa: E402
import a3p2_lp as LP          # noqa: E402  (registers lucidpro / lucidpro_nodll rule files + grids as an import side effect)

OUT = E.D / "out"
SNAP_L, SNAP_J = OUT / "a3p3_snap_ledger.csv", OUT / "a3p3_snap_jobs.jsonl"
OLD_L, OLD_J = OUT / "a3p2_snap_ledger.csv", OUT / "a3p2_snap_jobs.jsonl"
FIRMS5 = ("lucid", "lucidpro", "lucidpro_nodll", "apex", "apex_eod")
M3 = ("eod", "realized", "intraday")
CELLSETS = ("p5_eod", "p5_realized", "p5_intraday", "speed_p1", "speed_p3")
A2.GR["apex_eod"] = {"micros": [20, 30, 40, 50, 60], "day_lock": [0, 1000, 2000], "day_take": [0, 1500, 2000, 3000],
                     "day_stop": [0, 500, 1000], "max_day_tr": [1, 0], "target_take": [0, 1]}
A2.SNAP_L, A2.SNAP_J = SNAP_L, SNAP_J          # A2.resolve()/sources() read the pass-3 snapshot (workers re-import this module)
K_CTRL = 10
# pass-3 "new" heat-map keys: NQ = hm2-* + fp-* (hm-* were pass 2); ES has no pass 2 -> its tuning heat-maps hm-* + fp-*
NEW_PFX = ("hm2-", "fp-") if E.PL.NAME == "nq" else ("hm-", "fp-")


def rd(p):
    p = p if isinstance(p, Path) else OUT / p
    return list(csv.DictReader(p.open()))


# ------------------------------------------------------------------ sources / pools

def snapshot():
    if not SNAP_L.exists():
        shutil.copy(E.D / "ledger.csv", SNAP_L)
        shutil.copy(E.D / "jobs.jsonl", SNAP_J)


def sources3():
    """New heat-map cells (keys hm2-*, fp-*) -> [(src, fam, tf, key, params)] from the pass-3 snapshot."""
    out = []
    for r in csv.DictReader(SNAP_L.open()):
        if r["stage"] == "sizing" and r["key"].startswith(NEW_PFX) and r["grid_id"] and r["cell"] != "":
            p = json.loads(r["params_json"])
            fam = r["strategy"].replace(E.DRAFT_PREFIX, "")
            tf = int(p.pop("tf"))
            p.pop("sess", None)
            out.append((f"{r['grid_id']}#{r['cell']}", fam, tf, f"{r['key']}#{r['cell']}", p))
    return out


def sources2():
    """Pass-2 sources (hm-* cells + screen runs), same construction as a3_pass2.sources() on the pass-3 snapshot."""
    return A2.sources()


def resolve(prof, old=False):
    return E.resolve_pool(prof, OLD_L if old else SNAP_L, OLD_J if old else SNAP_J)


# ------------------------------------------------------------------ walk + race (3 models, P1/P3)

def make_A3(port, r, dll, m, dl, dtk, ds, mt):
    """A2.make_A + memoised rewalk (the target_take re-walk is called with identical (day, level) by every breach model)."""
    A = A2.make_A(port, r, dll, m, dl, dtk, ds, mt)
    orig, memo = A.rewalk, {}

    def rw(i, tt):
        k = (i, tt)
        v = memo.get(k)
        if v is None:
            v = memo[k] = orig(i, tt)
        return v

    A.rewalk = rw
    return A


def _pd(o, d):
    ps = o == 1
    return dict(p1=float((ps & (d <= 1)).mean()), p2=float((ps & (d <= 2)).mean()), p3=float((ps & (d <= 3)).mean()), p5=float(ps.mean()),
                bust5=float((o == 2).mean()), med=float(np.median(d[ps])) if ps.any() else float("nan"))


def search3(port, D, f, prim):
    """All rule cells of firm f: P5 + bust5 under 3 models (arrays [3]+shape), P1/P3 under the primary model, #rules. -> dict"""
    g = A2.GR[f]
    rid, r, dll = SA.firm(f)
    shape = tuple(len(g[a]) for a in A2.AX)
    P5, B5 = (np.full((3,) + shape, np.nan) for _ in range(2))
    P1, P3, nr = np.full(shape, np.nan), np.full(shape, np.nan), np.zeros(shape)
    idx5, cache, pk = A2.idx5_of(D), {}, M3.index(prim)
    for ci in np.ndindex(*shape):
        m, dl, dtk, ds, mt, tt = (g[a][i] for a, i in zip(A2.AX, ci))
        nr[ci] = (dl > 0) + (dtk > 0) + (ds > 0) + (mt > 0) + tt
        key = A2.norm_walk(port, m, dl, dtk, ds, mt)
        if key not in cache:
            A = make_A3(port, r, dll, *key)
            res = {}
            for t_ in (0, 1):
                res[t_] = []
                for mod in M3:
                    o, d = E.race(idx5, A, r, mod, True, bool(t_))
                    x = _pd(o, d)
                    res[t_].append((x["p5"], x["bust5"], x["p1"], x["p3"]))
            cache[key] = res
        v = cache[key][tt]
        for k in range(3):
            P5[(k,) + ci], B5[(k,) + ci] = v[k][0], v[k][1]
        P1[ci], P3[ci] = v[pk][2], v[pk][3]
    return dict(P5=P5, B5=B5, P1=P1, P3=P3, nr=nr, walks=len(cache), shape=shape)


def cell_of(f, ci):
    return tuple(int(A2.GR[f][a][i]) for a, i in zip(A2.AX, ci))


def eval_cell3(port, D, f, cell):
    rid, r, dll = SA.firm(f)
    m, dl, dtk, ds, mt, tt = cell
    A = make_A3(port, r, dll, *A2.norm_walk(port, m, dl, dtk, ds, mt))
    idx5 = A2.idx5_of(D)
    return {mod: E.race(idx5, A, r, mod, True, bool(tt)) for mod in M3}, A


def cost_bits(m, med_pts):
    c = A2.cost_mix(m, med_pts)
    return c, bool(c == c and c < 0.03)


# ------------------------------------------------------------------ analysis of one config

def analyze3(port, D, ctl_ports, meta, firms, cal_year, cal_news, cfg):
    rows = []
    yrs = cal_year[np.arange(D - E.H_EVAL + 1)]
    for f in firms:
        prim = E.primary_model(f)
        S = search3(port, D, f, prim)
        nr = S["nr"]
        sel, stabv, rawv = {}, {}, {}
        for k, mod in enumerate(M3):
            sv = A1.stable(S["P5"][k])
            sel[f"p5_{mod}"], stabv[f"p5_{mod}"], rawv[f"p5_{mod}"] = A2.pick(sv, nr), sv, float(S["P5"][k].max())
        for nm, key in (("speed_p1", "P1"), ("speed_p3", "P3")):
            sv = A1.stable(S[key])
            sel[nm], stabv[nm], rawv[nm] = A2.pick(sv, nr), sv, float(S[key].max())
        cells = {nm: cell_of(f, ci) for nm, ci in sel.items()}
        ev = {}
        for c in set(cells.values()):
            own, A = eval_cell3(port, D, f, c)
            ctl = [eval_cell3(cp, D, f, c)[0] for cp in ctl_ports] if ctl_ports else []
            ev[c] = (own, A, ctl)
        base = dict(meta, firm=f, primary=prim, cells=int(np.prod(S["shape"])), walks=S["walks"])
        for nm in CELLSETS:
            c = cells[nm]
            own, A, ctl = ev[c]
            row = dict(base, cellset=nm, stab=float(stabv[nm][sel[nm]]), raw_max=rawv[nm], n_rules=int(nr[sel[nm]]))
            for a, val in zip(A2.AX, c):
                row[a] = val
            for mod in M3:
                for kk, vv in _pd(*own[mod]).items():
                    row[f"{mod}_{kk}"] = vv
            o, d = own[prim]
            ps = o == 1
            arrs = [ps & (d <= 1), ps & (d <= 2), ps & (d <= 3), ps]
            for lab, (lo, hi) in zip(("p1", "p2", "p3", "p5"), E.block_ci(arrs)):
                row[f"ci_{lab}_lo"], row[f"ci_{lab}_hi"] = round(lo, 6), round(hi, 6)
            for mod in M3:
                if mod != prim:
                    o2, _ = own[mod]
                    row[f"ci_{mod}_p5_lo"], row[f"ci_{mod}_p5_hi"] = (round(x, 6) for x in E.block_ci([o2 == 1])[0])
            if ctl:
                for mod in M3:
                    cp = np.array([_pd(*x[mod])["p5"] for x in ctl])
                    row[f"ctrl_{mod}_p5"] = float(cp.mean())
                    row[f"lift_{mod}_p5"] = row[f"{mod}_p5"] - row[f"ctrl_{mod}_p5"]
                    if mod == prim:
                        row["ctrl_prim_p5_sd"] = float(cp.std(ddof=1))
                c1 = np.array([[_pd(*x[prim])["p1"], _pd(*x[prim])["p3"]] for x in ctl])
                row["ctrl_prim_p1"], row["ctrl_prim_p3"] = float(c1[:, 0].mean()), float(c1[:, 1].mean())
                row["lift_prim_p1"], row["lift_prim_p3"] = row[f"{prim}_p1"] - row["ctrl_prim_p1"], row[f"{prim}_p3"] - row["ctrl_prim_p3"]
                row["lift_prim_p5"] = row[f"lift_{prim}_p5"]
            for y in A2.YEARS:
                s = yrs == y
                row[f"p5_{y}"] = float(ps[s].mean()) if s.any() else float("nan")
                row[f"net_{y}"] = float(A.tot[cal_year == y].sum())
            wn = cal_news[A2.idx5_of(D)].any(1)
            row["p5_news"], row["p5_nonnews"] = (float(ps[wn].mean()) if wn.any() else float("nan"), float(ps[~wn].mean()) if (~wn).any() else float("nan"))
            row["net_rules"] = float(A.tot.sum())
            m = c[0]
            row["exp_at_micros"], row["net_at_micros"] = cfg["exp"](m), cfg["net"](m)
            row["cost_ratio_mix"], row["cost_pass_mix"] = cost_bits(m, cfg["med_pts"])
            rows.append(row)
    return rows


# ------------------------------------------------------------------ tasks

def task_real3(a):
    src, fam, tf, key, params, ents, K, old = a      # ents: [(sess, firms, extra)]
    LP.gate()
    t = A2.load_src(src)
    prof = E.profile_from(fam, dict(params, tf=tf))
    pl = resolve(prof, old)
    pool = A2.pool_of(pl["srcs"])
    rows = []
    for sess, firms, extra in ents:
        m = t.sess == E.SESS_CODE[sess]
        idx = np.flatnonzero(m)
        cal = SA.cal_for(t, pool)
        D = len(cal)
        cy, cn = A2.cal_year_news(cal)
        st, cfg = A2.cfg_stats(t, m)
        port = A2.port_of(t, idx, cal)
        sub = dict(date=t.date[idx], sess=t.sess[idx])
        cps, fb, ctd = A2.ctl_ports(sub, pool, cal, zlib.crc32(f"{key}|{sess}".encode()), K)
        meta = dict(kind="real", fam=fam, tf=tf, sess=sess, key=key, src=src, params=json.dumps(params, sort_keys=True), **st,
                    trade_days=int(sum(1 for d in port.days if d)), ctrl_trade_days=round(ctd, 1), fallback_share=round(fb, 5),
                    pool_exact=pl["exact"], pool_seeds=len(pl["srcs"]), pool_flag=pl["flag"], pool_id=json.dumps(pl["profile"], sort_keys=True), **extra)
        rows += analyze3(port, D, cps, meta, firms, cy, cn, cfg)
    return rows


def _seed_of(k):
    return int(k.rsplit("-s", 1)[1])


def task_null3(a):
    pool_id, sess, n_req, rep, K, prof = a
    LP.gate()
    pl = resolve(prof)
    seeds = list(zip(pl["keys"], pl["srcs"]))
    if len(seeds) < 2:
        return []
    ident = f"null3|{pool_id}|{sess}|{rep}"
    rg = np.random.default_rng(zlib.crc32(ident.encode()))
    for i in rg.permutation(len(seeds)):
        t = A2.load_src(seeds[i][1])
        cand = np.flatnonzero(t.sess == E.SESS_CODE[sess])
        if len(cand) >= 300:
            break
    else:
        return []
    n = min(int(n_req), len(cand))
    sel = np.sort(rg.choice(cand, n, replace=False))
    pool = A2.pool_of([s for j, (k2, s) in enumerate(seeds) if j != i])
    cal = SA.cal_for(t, pool)
    D = len(cal)
    cy, cn = A2.cal_year_news(cal)
    st, cfg = A2.cfg_stats(t, np.isin(np.arange(t.n), sel))
    port = A2.port_of(t, sel, cal)
    cps, fb, ctd = A2.ctl_ports(dict(date=t.date[sel], sess=t.sess[sel]), pool, cal, zlib.crc32(ident.encode()), K)
    meta = dict(kind="null", fam="random", tf=prof["tf"], sess=sess, key=f"null|{pool_id}|{rep}", pool_id=pool_id, pool_flag=pl["flag"], n_req=int(n_req),
                seed=_seed_of(seeds[i][0]), trade_days=int(sum(1 for d in port.days if d)), ctrl_trade_days=round(ctd, 1), fallback_share=round(fb, 5),
                pool_seeds=len(seeds) - 1, **st)
    return analyze3(port, D, cps, meta, FIRMS5, cy, cn, cfg)


# ------------------------------------------------------------------ stages

def task_quick(a):
    src, fam, tf, key, params = a
    t = A2.load_src(src)
    pl = resolve(E.profile_from(fam, dict(params, tf=tf)))
    out = []
    for sess in E.SESS:
        st, _ = A2.cfg_stats(t, t.sess == E.SESS_CODE[sess])
        out.append(dict(fam=fam, tf=tf, key=key, src=src, sess=sess, **st, pool_id=json.dumps(pl["profile"], sort_keys=True),
                        pool_exact=pl["exact"], pool_flag=pl["flag"]))
    return out


def stage_quick(a):
    snapshot()
    srcs = sources3()
    res = A1.run_pool(task_quick, srcs, a.workers, "quick3")
    A1.write(OUT / "a3p3_quick.csv", sorted(res, key=lambda x: (x["key"], list(E.SESS).index(x["sess"]))))


def decide(a):
    """quick -> {(key, sess): extra} of pass-3 configs to run: >= 300 trades; hm2-* also need net > 0 at 1 NQ unless --all-hm2 (flagged)."""
    todo, skipped = {}, defaultdict(int)
    for r in rd("a3p3_quick.csv"):
        n, net = int(r["trades"]), float(r["net_1nq"])
        fp = r["key"].startswith("fp-")
        if n < 300:
            skipped["lt300"] += 1
            continue
        if not fp and net <= 0 and not a.all_hm2:
            skipped["hm2_net_le0"] += 1
            continue
        todo[(r["key"], r["sess"])] = dict(net_le0=int(net <= 0), fastpass=int(fp))
    return todo, dict(skipped)


def stage_real(a):
    todo, skipped = decide(a)
    q = {(r["key"], r["sess"]): r for r in rd("a3p3_quick.csv")}
    by = defaultdict(list)
    for (key, sess), ex in todo.items():
        by[key].append((sess, FIRMS5, ex))
    srcs = {s[3]: s for s in sources3()}
    tasks = [(*srcs[k][:5], sorted(v, key=lambda e: list(E.SESS).index(e[0])), a.k, False) for k, v in by.items()]
    tasks.sort(key=lambda x: -sum(int(q[(x[3], e[0])]["trades"]) for e in x[5]))
    if a.shard:
        i, n = (int(x) for x in a.shard.split("/"))
        tasks = tasks[i::n]
    if a.limit:
        tasks = tasks[a.offset: a.offset + a.limit]
    print(f"real3: {sum(len(t[5]) for t in tasks)} configs in {len(tasks)} sources; skipped {skipped}", flush=True)
    res = A2.run_ckpt(task_real3, tasks, lambda t: t[3], a.workers, "real3", OUT / f"a3p3_real_part{a.suffix}.jsonl")
    write_rows(OUT / f"a3p3_rules{a.suffix}.csv", res)


def write_rows(path, res):
    res.sort(key=lambda x: (x.get("key", ""), list(E.SESS).index(x["sess"]), FIRMS5.index(x["firm"]), CELLSETS.index(x["cellset"])))
    A1.write(path, res)
    print(f"wrote {len(res)} rows -> {path.name}", flush=True)


def stage_null(a):
    strata = defaultdict(list)
    todo = decide(a)[0]
    for r in rd("a3p3_quick.csv"):
        if (r["key"], r["sess"]) in todo:
            strata[(r["pool_id"], r["sess"])].append(int(r["trades"]))
    if a.with_pass2:
        for r in rd("a3p3_rescore2_cfgs.csv"):
            strata[(r["pool_id"], r["sess"])].append(int(r["trades"]))
    tasks = []
    for (pid, sess), ns in sorted(strata.items()):
        prof = E.profile_from("random", json.loads(pid))
        tasks += [(pid, sess, int(np.median(ns)), rep, a.k, prof) for rep in range(a.reps)]
    if a.shard:
        i, n = (int(x) for x in a.shard.split("/"))
        tasks = tasks[i::n]
    if a.limit:
        tasks = tasks[a.offset: a.offset + a.limit]
    print(f"null3: {len(tasks)} pseudo-configs (strata = control pool x session)", flush=True)
    res = A2.run_ckpt(task_null3, tasks, lambda t: f"{t[0]}|{t[1]}|{t[3]}", a.workers, "null3", OUT / f"a3p3_null_part{a.suffix}.jsonl")
    res.sort(key=lambda x: (x["pool_id"], list(E.SESS).index(x["sess"]), FIRMS5.index(x["firm"]), CELLSETS.index(x["cellset"])))
    A1.write(OUT / f"a3p3_null{a.suffix}.csv", res)
    print(f"wrote {len(res)} null rows", flush=True)


def parts(pattern):
    rows = []
    for p in sorted(OUT.glob(pattern)):
        for ln in p.read_text().splitlines():
            if ln.strip():
                rows += json.loads(ln)["rows"]
    return rows


def stage_merge(a):
    """Join the shards' part files -> a3p3_rules.csv (new heat-maps), a3p3_rescore2.csv (pass-2 configs), a3p3_null.csv."""
    real = parts("a3p3_real_part*.jsonl")
    write_rows(OUT / "a3p3_rules.csv", real)
    write_rows(OUT / "a3p3_rescore2.csv", parts("a3p3_rescore2_part*.jsonl"))
    nl = parts("a3p3_null_part*.jsonl")
    nl.sort(key=lambda x: (x["pool_id"], list(E.SESS).index(x["sess"]), x["key"], FIRMS5.index(x["firm"]), CELLSETS.index(x["cellset"])))
    A1.write(OUT / "a3p3_null.csv", nl)
    print(f"wrote {len(nl)} null rows", flush=True)


def stage_rescore2(a):
    """Pass-2 shortlist configs (shortlist_all.csv top-40/firm + top intraday-optimum configs per firm) through the pass-3 analysis."""
    keep = set()
    for r in rd("shortlist_all.csv"):
        keep.add((r["strategy_id"].split("|")[1], r["sess"]))
    for f in ("lucid", "apex"):
        rs = [r for r in rd("a3p2_rules.csv") if r["firm"] == f and r["model"] == "intraday" and int(r["trades"]) >= 300 and float(r["net_1nq"]) > 0]
        rs.sort(key=lambda r: -float(r["st_p5"]))
        keep |= {(r["key"], r["sess"]) for r in rs[:40]}
    q = {(r["key"], r["sess"]): r for r in rd("a3p2_quick.csv")}
    srcs = {s[3]: s for s in sources2()}
    by = defaultdict(list)
    for (key, sess) in sorted(keep):
        by[key].append((sess, FIRMS5, dict(net_le0=int(float(q[(key, sess)]["net_1nq"]) <= 0), fastpass=0, pass2=1)))
    tasks = [(*srcs[k][:5], v, a.k, True) for k, v in by.items()]
    A1.write(OUT / "a3p3_rescore2_cfgs.csv", [dict(key=k, sess=s, trades=q[(k, s)]["trades"], pool_id=q[(k, s)]["pool_id"]) for k, s in sorted(keep)])
    print(f"rescore2: {len(keep)} pass-2 configs in {len(tasks)} sources", flush=True)
    res = A2.run_ckpt(task_real3, tasks, lambda t: t[3], a.workers, "rescore2", OUT / f"a3p3_rescore2_part{a.suffix}.jsonl")
    write_rows(OUT / f"a3p3_rescore2{a.suffix}.csv", res)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--k", type=int, default=K_CTRL)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--suffix", default="")
    ap.add_argument("--shard", default="", help="i/n: run tasks[i::n] (separate --suffix per shard; `merge` joins the part files)")
    ap.add_argument("--all-hm2", action="store_true", help="also run hm2 cells with net <= 0")
    ap.add_argument("--with-pass2", action="store_true", help="null strata also cover the rescored pass-2 configs")
    a = ap.parse_args(argv)
    st = ["snap", "quick", "real", "null", "rescore2"] if a.stage == "all" else [a.stage]
    if "snap" in st:
        snapshot()
    if "quick" in st:
        stage_quick(a)
    if "real" in st:
        stage_real(a)
    if "rescore2" in st:
        stage_rescore2(a)
    if "merge" in st:
        stage_merge(a)
    if "null" in st:
        stage_null(a)


if __name__ == "__main__":
    main()
