#!/usr/bin/python3
"""A3 pass 2: heat-map cells x session (+ screen configs) with the day_take / target_take rules, both breach models.
Run: PYTHONPATH=~/ramos-quant-homebase /usr/bin/python3 a3_pass2.py --stage quick|real|null|summary|all [--workers 8]

Grids (target_stop always ON; target_take supersedes it when on; 0 = off, max_day_tr 0 = none):
  lucid: micros {10,20,30,40} x day_lock {0,750,1000,1500} x day_take {0,1000,1250,1500} x day_stop {0,1000,2000} x max_day_tr {1,0} x target_take {0,1}   (768)
  apex (UNCONFIRMED): micros {20,40,60,80,100} x day_lock {0,1000,2000} x day_take {0,1500,2000,3000} x day_stop {0,1000,2000,3000} x max_day_tr {1,0} x target_take {0,1} (960)
Stable cell = max of the median P5 over the cell + its +-1-step neighbours on every axis (max_day_tr and target_take are 2-step axes);
lift = P5 - mean P5 of K=10 day-matched controls (same exit-profile pool) at IDENTICAL rules. Per (config, firm) both models are searched
separately (eod row: eod-optimal cell, with the intraday result AT THOSE RULES in xi_*; intraday row: the intraday-optimal cell).
Null (a3p2_null.csv): one pseudo-config per (control pool = exit profile, session) stratum = a random seed run thinned to the stratum's
median real trade count, controls from the other seeds; its stable P5 is the optimised zero-edge baseline, p95 of its stable lift = THR.
Inputs are a frozen snapshot of ledger.csv/jobs.jsonl (out/a3p2_snap_*). Stages: quick (trades/net/quick P5) -> real -> null -> summary.
The quick P5 (Lucid m40/L1000, Apex m100/L1000, eod, target_stop) drops a config-firm from `real` if below the given percentile (--drop-pct)."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import itertools
import json
import shutil
import sys
import time
import zlib
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E          # noqa: E402
import screen_analyze as SA   # noqa: E402
import a3_rules as A1         # noqa: E402

R, OUT = E.D, E.D / "out"
SNAP_L, SNAP_J = OUT / "a3p2_snap_ledger.csv", OUT / "a3p2_snap_jobs.jsonl"
AX = ["micros", "day_lock", "day_take", "day_stop", "max_day_tr", "target_take"]
GR = {
    "lucid": {"micros": [10, 20, 30, 40], "day_lock": [0, 750, 1000, 1500], "day_take": [0, 1000, 1250, 1500],
              "day_stop": [0, 1000, 2000], "max_day_tr": [1, 0], "target_take": [0, 1]},
    "apex": {"micros": [20, 40, 60, 80, 100], "day_lock": [0, 1000, 2000], "day_take": [0, 1500, 2000, 3000],
             "day_stop": [0, 1000, 2000, 3000], "max_day_tr": [1, 0], "target_take": [0, 1]},
}
import os as _os
if _os.environ.get("PP_FLEX_TAKE_EXT") == "1":      # see portfolio.py: a Flex day_take of 1,560-1,600 makes the 2-day pass reachable (1,500 - 1 tick x 40 = $1,450 x 2 < $3,000)
    GR["lucid"] = dict(GR["lucid"], day_take=[0, 1000, 1250, 1500, 1560, 1600])
QUICK = {"lucid": (40, 1000), "apex": (100, 1000)}
MODELS, FIRMS, YEARS = ("eod", "intraday"), ("lucid", "apex"), (2022, 2023, 2024)
K_CTRL = 10
HM_PREFIX = "hm-"


# ------------------------------------------------------------------ data

def snapshot():
    if not SNAP_L.exists():
        shutil.copy(R / "ledger.csv", SNAP_L)
        shutil.copy(R / "jobs.jsonl", SNAP_J)


def resolve(profile):
    return E.resolve_pool(profile, SNAP_L, SNAP_J)


def load_src(src):
    """evalcore TR (research window, per 1 NQ) + per-trade 1-NQ net + year (cached on the TR)."""
    t = E.load(src)
    if not hasattr(t, "net"):
        d = E._src_dir(src)
        rows = json.loads((d if d.is_file() else d / "trades.json").read_text())
        rows = rows if isinstance(rows, list) else rows.get("trades", [])
        rows = [x for x in rows if x["date"] < E.HOLDOUT]
        q = np.array([max(1.0, float(x.get("qty") or 1)) for x in rows])
        t.net = np.array([float(x["net"]) for x in rows]) / q
        t.year = np.array([int(x["date"][:4]) for x in rows], np.int16)
    return t


class P2:
    """Port-like (days of walk tuples + parallel mfe lists) from trade arrays on calendar `cal`."""

    def __init__(self, date, te, tx, side, g, mae, mfe, risk, cal):
        o = np.lexsort((te, date))
        pos = np.searchsorted(cal, date[o])
        self.days, self.mfe = [[] for _ in cal], [[] for _ in cal]
        for j, p in zip(o, pos):
            self.days[p].append((int(te[j]), int(tx[j]), int(side[j]), float(g[j]), float(mae[j]), 10, float(risk[j]), 0))
            self.mfe[p].append(float(mfe[j]))
        self.mx = max((len(d) for d in self.days), default=0)
        self._U = {}

    def U(self, m):
        """Per-day upper bound of any take trigger at m micros: sum of the trades' positive best points."""
        if m not in self._U:
            c = E.cost(m)
            self._U[m] = np.array([sum(max(m * f / 10.0 - c, 0.0) for f in fs) for fs in self.mfe])
        return self._U[m]


def port_of(t, idx, cal):
    return P2(t.date[idx], t.te[idx], t.tx[idx], t.side[idx], t.g[idx], t.mae[idx], t.mfe[idx], t.risk[idx], cal)


_IDX5 = {}


def idx5_of(D):
    if D not in _IDX5:
        _IDX5[D] = np.arange(D - E.H_EVAL + 1)[:, None] + np.arange(E.H_EVAL)
    return _IDX5[D]


def make_A(port, r, dll, m, dl, dtk, ds, mt):
    """Day walk for one rule set; the target_take re-walk is skipped on days that cannot reach the level (exact)."""
    A = E.walk(port, r["cap_micros"], (int(mt), float(ds), float(dl), 1.0, 1.0, True), want_chk=True, micros=int(m), dll=dll,
               day_take=float(dtk))
    orig, U = A.rewalk, port.U(int(m))

    def rw(i, tt):
        if tt > U[i] + 1e-6:
            return float(A.tot[i]), float(A.worst[i]), bool(A.trd[i]), float(A.wreal[i])
        return orig(i, tt)

    A.rewalk = rw
    return A


def norm_walk(port, m, dl, dtk, ds, mt):
    """Cache key of a walk: rules that cannot matter are zeroed (one trade/day -> max_day_tr, day_lock no-ops)."""
    mt_e = 0 if mt >= port.mx else mt
    dl_e = 0 if (port.mx <= 1 or mt_e == 1) else dl
    if port.mx <= 1:
        mt_e = 0
    return (m, dl_e, dtk, ds, mt_e)


def race_all(A, r, D, tt_list=(0, 1)):
    """{tt: {model: (p5, bust5, med_days, ps)}} for the walk A."""
    idx5, res = idx5_of(D), {}
    for tt in tt_list:
        res[tt] = {}
        for mod in MODELS:
            o, d = E.race(idx5, A, r, mod, True, bool(tt))
            ps = o == 1
            res[tt][mod] = (float(ps.mean()), float((o == 2).mean()), float(np.median(d[ps])) if ps.any() else float("nan"), ps)
    return res


# ------------------------------------------------------------------ search

def search_firm(port, D, f):
    g = GR[f]
    rid, r, dll = SA.firm(f)
    shape = tuple(len(g[a]) for a in AX)
    P, B, MD = (np.full((2,) + shape, np.nan) for _ in range(3))
    nr = np.zeros(shape)
    cache = {}
    for ci in itertools.product(*[range(n) for n in shape]):
        m, dl, dtk, ds, mt, tt = (g[a][i] for a, i in zip(AX, ci))
        nr[ci] = (dl > 0) + (dtk > 0) + (ds > 0) + (mt > 0) + tt
        key = norm_walk(port, m, dl, dtk, ds, mt)
        if key not in cache:
            cache[key] = race_all(make_A(port, r, dll, *key), r, D)
        for k, mod in enumerate(MODELS):
            P[(k,) + ci], B[(k,) + ci], MD[(k,) + ci] = cache[key][tt][mod][:3]
    return P, B, MD, nr, len(cache)


def pick(v, nr):
    """argmax of v; ties -> fewer active rules, then smaller size."""
    mi = np.arange(v.shape[0]).reshape((-1,) + (1,) * (v.ndim - 1))
    return np.unravel_index(int(np.argmax(v - 1e-7 * nr - 1e-9 * mi)), v.shape)


def cell_vals(f, ci):
    return tuple(GR[f][a][i] for a, i in zip(AX, ci))


def eval_cell(port, D, f, cell):
    """-> {model: (p5, bust5, med_days, ps)} and A for one rule cell."""
    rid, r, dll = SA.firm(f)
    m, dl, dtk, ds, mt, tt = cell
    k = norm_walk(port, m, dl, dtk, ds, mt)
    A = make_A(port, r, dll, *k)
    return race_all(A, r, D, (tt,))[tt], A


# ------------------------------------------------------------------ per-config extras

def cost_mix(m, med_pts):
    """RT cost (commission + 2 ticks) / stop $ risk at the instrument mix of m micros (q NQ minis + r micros)."""
    q, rr = divmod(m, 10)
    if not (med_pts == med_pts and med_pts > 0):
        return float("nan")
    pl = E.PL
    return (q * (4.0 + 2 * pl.TICK_FULL) + rr * (1.0 + 2 * pl.TICK_USD)) / ((q * pl.PV + rr * pl.PV_MICRO) * med_pts)


def extras(ps, A, port, cal_year, cal_news, D, cfg):
    x = {}
    yr = cal_year[np.arange(D - E.H_EVAL + 1)]
    for y in YEARS:
        s = yr == y
        x[f"p5_{y}"] = float(ps[s].mean()) if s.any() else float("nan")
        x[f"net_{y}"] = float(A.tot[cal_year == y].sum())
    wn = cal_news[idx5_of(D)].any(1)
    x["p5_news"], x["p5_nonnews"] = (float(ps[wn].mean()) if wn.any() else float("nan"), float(ps[~wn].mean()) if (~wn).any() else float("nan"))
    x["n_news_starts"] = int(wn.sum())
    x["net_rules"] = float(A.tot.sum())
    return x


def analyze2(port, D, ctl_ports, meta, firms, cal_year, cal_news, cfg):
    """cfg = dict(g, mfe arrays for expectancy at micros: exp(m) callable, med_pts, ...). -> row dicts."""
    rows = []
    for f in firms:
        P, B, MD, nr, walks = search_firm(port, D, f)
        chosen = {}
        base = dict(meta, firm=f, cells=int(np.prod(P.shape[1:])), walks=walks)
        for k, mod in enumerate(MODELS):
            v = P[k]
            sv = A1.stable(v)
            st, rw = pick(sv, nr), pick(v, nr)
            sub = (slice(None), slice(None), 0, slice(None), slice(None), 0)      # pass-1-like sub-grid: no day_take, no target_take
            nst = pick(A1.stable(v[sub]), nr[sub])
            chosen[mod] = dict(st=st, rw=rw, sv=sv, v=v, nst_p5=float(v[sub][nst]), nrw_p5=float(v[sub].max()))
        cells = {mod: cell_vals(f, chosen[mod]["st"]) for mod in MODELS}
        ev = {}
        for c in set(cells.values()):
            own, A = eval_cell(port, D, f, c)
            ctl = [eval_cell(cp, D, f, c)[0] for cp in ctl_ports] if ctl_ports else []
            ev[c] = (own, A, ctl)
        for k, mod in enumerate(MODELS):
            c, ch = cells[mod], chosen[mod]
            own, A, ctl = ev[c]
            p5, b5, md, ps = own[mod]
            row = dict(base, model=mod, rw_p5=float(ch["v"][ch["rw"]]), st_p5=p5, st_bust5=b5, st_med_days=md,
                       st_stab_med=float(ch["sv"][ch["st"]]), st_n_rules=int(nr[ch["st"]]), notake_st_p5=ch["nst_p5"], notake_rw_p5=ch["nrw_p5"])
            assert abs(p5 - float(ch["v"][ch["st"]])) < 1e-9, (p5, ch["v"][ch["st"]])
            for a, val in zip(AX, c):
                row[f"st_{a}"] = val
            for a, val in zip(AX, cell_vals(f, ch["rw"])):
                row[f"rw_{a}"] = val
            row["st_ci_lo"], row["st_ci_hi"] = (round(x, 6) for x in E.block_ci([ps])[0])
            cp = np.array([[x[mod][0], x[mod][1]] for x in ctl]) if ctl else None
            if cp is not None:
                row["st_ctrl_p5"], row["st_ctrl_sd"], row["st_ctrl_bust5"] = float(cp[:, 0].mean()), float(cp[:, 0].std(ddof=1)), float(cp[:, 1].mean())
                row["st_lift"] = p5 - row["st_ctrl_p5"]
            if mod == "eod":                                       # the same rules under the intraday breach model
                ip5, ib5, imd, ips = own["intraday"]
                row.update(xi_p5=ip5, xi_bust5=ib5, xi_med_days=imd)
                row["xi_ci_lo"], row["xi_ci_hi"] = (round(x, 6) for x in E.block_ci([ips])[0])
                if cp is not None:
                    ic = np.array([x["intraday"][0] for x in ctl])
                    row["xi_ctrl_p5"] = float(ic.mean())
                    row["xi_lift"] = ip5 - row["xi_ctrl_p5"]
                for y in YEARS:
                    s = cal_year[np.arange(D - E.H_EVAL + 1)] == y
                    row[f"xi_p5_{y}"] = float(ips[s].mean()) if s.any() else float("nan")
            row.update(extras(ps, A, port, cal_year, cal_news, D, cfg))
            m = c[0]
            row["exp_at_micros"], row["net_at_micros"] = cfg["exp"](m), cfg["net"](m)
            row["cost_ratio_mix"] = cost_mix(m, cfg["med_pts"])
            row["cost_pass_mix"] = bool(row["cost_ratio_mix"] == row["cost_ratio_mix"] and row["cost_ratio_mix"] < 0.03)
            rows.append(row)
    return rows


# ------------------------------------------------------------------ tasks

_POOLS = {}


def pool_of(srcs):
    k = tuple(srcs)
    if k not in _POOLS:
        _POOLS[k] = E.concat_tr([load_src(s) for s in srcs])
    return _POOLS[k]


def cal_year_news(cal):
    dts = [dt.date.fromordinal(int(o)) for o in cal]
    nd = E.news_days()
    return np.array([d.year for d in dts]), np.array([int(o) in nd for o in cal])


def cfg_stats(t, m):
    """1-NQ stats of the session subset (boolean mask m) + the size-dependent helpers."""
    idx = np.flatnonzero(m)
    net = t.net[idx]
    rk = t.risk[idx]
    med = float(np.nanmedian(rk)) if np.isfinite(rk).any() else float("nan")
    st = dict(trades=int(len(idx)), net_1nq=float(net.sum()), exp_1nq=float(net.mean()) if len(idx) else float("nan"), med_stop_pts=med)
    for y in (2021,) + YEARS:
        st[f"net1_{y}"] = float(net[t.year[idx] == y].sum())
    g = t.g[idx]
    return st, dict(med_pts=med, exp=lambda mm: float((mm * g / 10.0 - E.cost(mm)).mean()) if len(g) else float("nan"),
                    net=lambda mm: float((mm * g / 10.0 - E.cost(mm)).sum()))


def task_quick(a):
    src, fam, tf, key, params = a
    t = load_src(src)
    prof = E.profile_from(fam, dict(params, tf=tf))
    pl = resolve(prof)
    cal = SA.cal_for(t)
    D = len(cal)
    out = []
    for sess in E.SESS:
        m = t.sess == E.SESS_CODE[sess]
        st, _ = cfg_stats(t, m)
        row = dict(fam=fam, tf=tf, key=key, src=src, sess=sess, **st, pool_id=json.dumps(pl["profile"], sort_keys=True),
                   pool_exact=pl["exact"], pool_flag=pl["flag"])
        if st["trades"] >= 300:
            port = port_of(t, np.flatnonzero(m), cal)
            for f in FIRMS:
                rid, r, dll = SA.firm(f)
                mm, dl = QUICK[f]
                A = make_A(port, r, dll, *norm_walk(port, mm, dl, 0, 0, 0))
                o, _ = E.race(idx5_of(D), A, r, "eod", True, False)
                row[f"q_{f}"] = float((o == 1).mean())
        out.append(row)
    return out


def ctl_ports(sub, pool, cal, seed, K):
    c = E.daymatched_controls(SimpleNamespace(date=sub["date"], sess=sub["sess"], n=len(sub["date"])), pool, K=K, seed=seed, mask=None,
                              carry=("side", "g", "mae", "mfe", "risk", "sess"))
    ports = [P2(x["date"], x["te"], x["tx"], x["side"], x["g"], x["mae"], x["mfe"], x["risk"], cal) for x in c]
    return ports, float(np.mean([x["fb_share"] for x in c])), float(np.mean([len(set(x["date"].tolist())) for x in c]))


def task_real(a):
    src, fam, tf, key, params, ents, K = a          # ents: [(sess, firms, extra meta)]
    t = load_src(src)
    prof = E.profile_from(fam, dict(params, tf=tf))
    pl = resolve(prof)
    pool = pool_of(pl["srcs"])
    rows = []
    for sess, firms, extra in ents:
        m = t.sess == E.SESS_CODE[sess]
        idx = np.flatnonzero(m)
        cal = SA.cal_for(t, pool)
        D = len(cal)
        cy, cn = cal_year_news(cal)
        st, cfg = cfg_stats(t, m)
        port = port_of(t, idx, cal)
        sub = dict(date=t.date[idx], sess=t.sess[idx])
        cps, fb, ctd = ctl_ports(sub, pool, cal, zlib.crc32(f"{key}|{sess}".encode()), K)
        meta = dict(kind="real", fam=fam, tf=tf, sess=sess, key=key, src=src, params=json.dumps(params, sort_keys=True), **st,
                    trade_days=int(sum(1 for d in port.days if d)), ctrl_trade_days=round(ctd, 1), fallback_share=round(fb, 5),
                    pool_exact=pl["exact"], pool_seeds=len(pl["srcs"]), pool_flag=pl["flag"],
                    pool_id=json.dumps(pl["profile"], sort_keys=True), **extra)
        rows += analyze2(port, D, cps, meta, firms, cy, cn, cfg)
    return rows


def _seed_of(k):
    return int(k.rsplit("-s", 1)[1])


def task_null(a):
    pool_id, sess, n_req, rep, K, prof = a
    pl = resolve(prof)
    seeds = list(zip(pl["keys"], pl["srcs"]))
    if len(seeds) < 2:
        return []
    ident = f"null2|{pool_id}|{sess}|{rep}"
    rg = np.random.default_rng(zlib.crc32(ident.encode()))
    for i in rg.permutation(len(seeds)):
        t = load_src(seeds[i][1])
        cand = np.flatnonzero(t.sess == E.SESS_CODE[sess])
        if len(cand) >= 300:
            break
    else:
        return []
    n = min(int(n_req), len(cand))
    sel = np.sort(rg.choice(cand, n, replace=False))
    pool = pool_of([s for j, (k2, s) in enumerate(seeds) if j != i])
    cal = SA.cal_for(t, pool)
    D = len(cal)
    cy, cn = cal_year_news(cal)
    st, cfg = cfg_stats(t, np.isin(np.arange(t.n), sel))
    port = port_of(t, sel, cal)
    cps, fb, ctd = ctl_ports(dict(date=t.date[sel], sess=t.sess[sel]), pool, cal, zlib.crc32(ident.encode()), K)
    meta = dict(kind="null", fam="random", tf=prof["tf"], sess=sess, key=f"null|{pool_id}|{rep}", pool_id=pool_id, pool_flag=pl["flag"], n_req=int(n_req),
                seed=_seed_of(seeds[i][0]), trade_days=int(sum(1 for d in port.days if d)), ctrl_trade_days=round(ctd, 1), fallback_share=round(fb, 5),
                pool_seeds=len(seeds) - 1, **st)
    return analyze2(port, D, cps, meta, FIRMS, cy, cn, cfg)


# ------------------------------------------------------------------ driver

def sources():
    """Heat-map cells (snapshot ledger, keys hm-*) + screen runs -> [(src, fam, tf, key, params)]."""
    out = []
    for r in csv.DictReader(SNAP_L.open()):
        if r["stage"] == "sizing" and r["key"].startswith(HM_PREFIX) and r["grid_id"] and r["cell"] != "":
            p = json.loads(r["params_json"])
            fam = r["strategy"].replace(E.DRAFT_PREFIX, "")
            tf = int(p.pop("tf"))
            p.pop("sess", None)
            out.append((f"{r['grid_id']}#{r['cell']}", fam, tf, f"{r['key']}#{r['cell']}", p))
    scr = {}
    for r in csv.DictReader(SNAP_L.open()):
        if r["stage"] == "screen" and r["run_id"]:
            p = json.loads(r["params_json"])
            scr[r["key"]] = (r["run_id"], r["strategy"].replace(E.DRAFT_PREFIX, ""), int(p["tf"]), r["key"], {})
    out += list(scr.values())
    return out


def pass1_forced():
    """Pass-1 configs above their null threshold (either firm/model): {(fam,tf,sess)}."""
    null = list(csv.DictReader((OUT / "a3_null.csv").open()))
    real = list(csv.DictReader((OUT / "a3_rules_screen.csv").open()))
    thr = {(f, m): float(np.percentile([float(r["st_lift"]) for r in null if r["firm"] == f and r["model"] == m], 95)) for f in FIRMS for m in MODELS}
    return {(r["fam"], int(r["tf"]), r["sess"]) for r in real if float(r["st_lift"]) > thr[(r["firm"], r["model"])]}


def run_ckpt(fn, tasks, idf, workers, tag, path):
    """Resumable pool: each finished task's rows are appended to a jsonl checkpoint (task id -> rows); done ids are skipped."""
    from multiprocessing import get_context
    done, rows = set(), []
    if path.exists():
        for ln in path.read_text().splitlines():
            if ln.strip():
                j = json.loads(ln)
                done.add(j["id"])
                rows += j["rows"]
    todo = [t for t in tasks if idf(t) not in done]
    print(f"[{tag}] {len(done)} tasks already done, {len(todo)} to run", flush=True)
    t0 = time.time()
    with get_context("spawn").Pool(workers, maxtasksperchild=20) as pl, path.open("a") as fh:
        for i, (t, x) in enumerate(pl.imap_unordered(_wrap(fn), todo, chunksize=1), 1):
            fh.write(json.dumps({"id": idf(t), "rows": x}) + "\n")
            fh.flush()
            rows += x
            if i % 10 == 0 or i == len(todo):
                print(f"[{tag}] {i}/{len(todo)} tasks {time.time() - t0:.0f}s", flush=True)
    return rows


class _wrap:
    def __init__(self, fn):
        self.fn = fn

    def __call__(self, t):
        return t, self.fn(t)


def rd(name):
    return list(csv.DictReader((OUT / name).open()))


def stage_quick(a):
    snapshot()
    srcs = sources()
    res = A1.run_pool(task_quick, srcs[: a.limit or None], a.workers, "quick")
    A1.write(OUT / "a3p2_quick.csv", sorted(res, key=lambda x: (x["key"], list(E.SESS).index(x["sess"]))))


def decide(a):
    """quick.csv -> {(key, sess): (firms, extra)} of configs to run."""
    q = rd("a3p2_quick.csv")
    forced = pass1_forced()
    scr_key = lambda r: r["key"].startswith("screen-")
    thr = {}
    for f in FIRMS:
        v = [float(r[f"q_{f}"]) for r in q if r.get(f"q_{f}", "") != ""]
        thr[f] = float(np.percentile(v, a.drop_pct)) if a.drop_pct else -1.0
    todo, dropped = {}, defaultdict(int)
    for r in q:
        n = int(r["trades"])
        fs = (r["fam"], int(r["tf"]), r["sess"])
        isf = scr_key(r) and fs in forced
        net = float(r["net_1nq"])
        if n < 300 and not isf:
            continue
        if scr_key(r) and net <= 0 and not isf:
            continue
        firms = tuple(f for f in FIRMS if isf or r.get(f"q_{f}", "") == "" or float(r[f"q_{f}"]) >= thr[f])
        for f in FIRMS:
            if f not in firms:
                dropped[f] += 1
        if firms:
            todo[(r["key"], r["sess"])] = (firms, dict(forced=int(isf), net_le0=int(net <= 0), quick_thr_lucid=round(thr["lucid"], 4), quick_thr_apex=round(thr["apex"], 4)))
    return todo, dict(dropped), thr


def stage_real(a):
    todo, dropped, thr = decide(a)
    q = {(r["key"], r["sess"]): r for r in rd("a3p2_quick.csv")}
    by = defaultdict(list)
    for (key, sess), (firms, extra) in todo.items():
        by[key].append((sess, firms, extra))
    srcs = {s[3]: s for s in sources()}
    tasks = [(*srcs[k][:5], sorted(v, key=lambda e: list(E.SESS).index(e[0])), a.k) for k, v in by.items()]
    tasks.sort(key=lambda x: -sum(int(q[(x[3], e[0])]["trades"]) for e in x[5]))
    if a.limit:
        tasks = tasks[: a.limit]
    print(f"real: {sum(len(t[5]) for t in tasks)} configs in {len(tasks)} sources; per-firm drops (quick P5 < p{a.drop_pct}) {dropped} thr {thr}", flush=True)
    res = run_ckpt(task_real, tasks, lambda t: t[3], a.workers, "real", OUT / f"a3p2_real_part{a.suffix}.jsonl")
    res.sort(key=lambda x: (x["key"], list(E.SESS).index(x["sess"]), x["firm"], x["model"]))
    A1.write(OUT / f"a3p2_rules{a.suffix}.csv", res)


def stage_null(a):
    q = rd("a3p2_quick.csv")
    done = {(r["key"], r["sess"]) for r in rd("a3p2_rules.csv") if r["model"] == "eod"} if (OUT / "a3p2_rules.csv").exists() else None
    strata = defaultdict(list)
    for r in q:
        if int(r["trades"]) >= 300 and (done is None or (r["key"], r["sess"]) in done):
            strata[(r["pool_id"], r["sess"])].append(int(r["trades"]))
    tasks = []
    for (pid, sess), ns in sorted(strata.items()):
        prof = E.profile_from("random", json.loads(pid))
        tasks += [(pid, sess, int(np.median(ns)), rep, a.k, prof) for rep in range(a.reps)]
    if a.limit:
        tasks = tasks[: a.limit]
    print(f"null: {len(tasks)} pseudo-configs (strata = control pool x session)", flush=True)
    res = run_ckpt(task_null, tasks, lambda t: f"{t[0]}|{t[1]}|{t[3]}", a.workers, "null", OUT / f"a3p2_null_part{a.suffix}.jsonl")
    res.sort(key=lambda x: (x["pool_id"], list(E.SESS).index(x["sess"]), x["firm"], x["model"]))
    A1.write(OUT / f"a3p2_null{a.suffix}.csv", res)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--k", type=int, default=K_CTRL)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--drop-pct", type=float, default=0.0)
    ap.add_argument("--suffix", default="")
    ap.add_argument("--reps", type=int, default=2)
    a = ap.parse_args(argv)
    st = ["quick", "real", "null", "summary"] if a.stage == "all" else [a.stage]
    if "quick" in st:
        stage_quick(a)
    if "real" in st:
        stage_real(a)
    if "null" in st:
        stage_null(a)
    if "summary" in st:
        import a3p2_summary
        a3p2_summary.main()


if __name__ == "__main__":
    main()
