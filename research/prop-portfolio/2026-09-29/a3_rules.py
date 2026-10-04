#!/usr/bin/python3
"""A3 offline sizing + daily-rule search on the screen configs, with a day-matched control lift, an optimised zero-edge
baseline and a multiple-testing null threshold. Run: PYTHONPATH=~/ramos-quant-homebase /usr/bin/python3 a3_rules.py

  a3_rules.py [--stage real|null|base|summary|all] [--workers 8] [--k 10] [--limit N] [--reps 5] [--min-trades 300]

Grid per firm (target_stop always ON; 0 = off, max_day_tr 0 = none):
  lucid: micros {10,20,30,40} x day_lock {0,750,1000,1250,1500} x day_stop {0,500,750,1000,1500,2000} x max_day_tr {1,2,3,0} x after_loss {1,.5}
  apex (UNCONFIRMED): micros {10,20,40,60,80,100} x day_lock {0,1000,1500,2000,3000} x day_stop {0,500,1000,1500,2000,3000} x same
Objective P(pass<=5d), rolling starts (evalcore.race). BOTH breach models ('eod' primary = Homebase, 'intraday' sensitivity)
come out of the same day walk. FULL grid, no coarse-to-fine (960 lucid + 1440 apex cells per config; exact-duplicate walks are
cached: max_day_tr >= max trades/day is a no-op, and with <=1 trade/day max_day_tr/day_lock/after_loss are no-ops).
Per config x firm x model: RAW best cell (max P5; ties fewer rules, smaller size) and STABLE best cell (max of the median P5 over the
cell and its +-1-step neighbours on every axis; its own P5 is reported), CI (moving-block bootstrap over start days), bust5,
median days, lift at IDENTICAL rules vs K day-matched controls (P5 - mean control P5; evalcore.daymatched_controls).
Baseline (a3_baseline.csv): the same search on each random-control seed run itself at natural frequency, per tf x session x profile.
Null (a3_null.csv): pseudo-configs = one random seed thinned to n in [300,2500] trades, controls day-matched from the OTHER seeds.
Outputs: out/a3_rules_screen.csv, out/a3_null.csv, out/a3_baseline.csv, out/a3_summary.md."""
from __future__ import annotations

import argparse
import csv
import itertools
import re
import sys
import time
import zlib
from multiprocessing import get_context
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E          # noqa: E402
import screen_analyze as SA   # noqa: E402

R, OUT = E.D, E.D / "out"
NO = [1, 2, 3, 0]
GRIDS = {
    "lucid": {"micros": [10, 20, 30, 40], "day_lock": [0, 750, 1000, 1250, 1500], "day_stop": [0, 500, 750, 1000, 1500, 2000],
              "max_day_tr": NO, "after_loss": [1.0, 0.5]},
    "apex": {"micros": [10, 20, 40, 60, 80, 100], "day_lock": [0, 1000, 1500, 2000, 3000], "day_stop": [0, 500, 1000, 1500, 2000, 3000],
             "max_day_tr": NO, "after_loss": [1.0, 0.5]},
}
AX = ["micros", "day_lock", "day_stop", "max_day_tr", "after_loss"]
MODELS = ("eod", "intraday")
FIRMS = ("lucid", "apex")
K_CTRL = 10


# ------------------------------------------------------------------ search

def _port(days):
    return SA._Port(days)


def eval_cell(days, D, f, cell):
    """One rule cell -> {model: (p5, bust5, med_days, pass_bool[starts])}."""
    rid, r, dll = SA.firm(f)
    idx5 = np.arange(D - E.H_EVAL + 1)[:, None] + np.arange(E.H_EVAL)
    m, dl, ds, mt, al = cell
    A = E.walk(_port(days), r["cap_micros"], (int(mt), float(ds), float(dl), float(al), 1.0, True), want_chk=True, micros=int(m), dll=dll)
    res = {}
    for mod in MODELS:
        o, d = E.race(idx5, A, r, mod, True)
        ps = o == 1
        res[mod] = (float(ps.mean()), float((o == 2).mean()), float(np.median(d[ps])) if ps.any() else float("nan"), ps)
    return res


def search_firm(days, D, f):
    """Full grid -> P[model, M, L, S, T, A], B, MD arrays + n_rules + distinct-walk count."""
    g = GRIDS[f]
    rid, r, dll = SA.firm(f)
    idx5 = np.arange(D - E.H_EVAL + 1)[:, None] + np.arange(E.H_EVAL)
    shape = tuple(len(g[a]) for a in AX)
    P, B, MD = (np.full((2,) + shape, np.nan) for _ in range(3))
    nr = np.zeros(shape)
    port = _port(days)
    mx = max((len(d) for d in days), default=0)
    cache, walks = {}, 0
    for ci in itertools.product(*[range(n) for n in shape]):
        m, dl, ds, mt, al = (g[a][i] for a, i in zip(AX, ci))
        nr[ci] = (dl > 0) + (ds > 0) + (mt > 0) + (al != 1.0)
        mt_e, dl_e, al_e = (0 if mt >= mx else mt), dl, al
        if mx <= 1:
            mt_e, dl_e, al_e = 0, 0, 1.0
        key = (m, dl_e, ds, mt_e, al_e)
        if key not in cache:
            A = E.walk(port, r["cap_micros"], (mt_e, float(ds), float(dl_e), float(al_e), 1.0, True), want_chk=True, micros=m, dll=dll)
            walks += 1
            v = []
            for mod in MODELS:
                o, d = E.race(idx5, A, r, mod, True)
                ps = o == 1
                v.append((float(ps.mean()), float((o == 2).mean()), float(np.median(d[ps])) if ps.any() else float("nan")))
            cache[key] = v
        for k in range(2):
            P[(k,) + ci], B[(k,) + ci], MD[(k,) + ci] = cache[key][k]
    return P, B, MD, nr, walks


def stable(v):
    """Median of the cell and its +-1-step neighbours on every axis (v: 5-D)."""
    st = [v]
    for ax in range(v.ndim):
        for s in (-1, 1):
            w = np.full_like(v, np.nan)
            dst, src = [slice(None)] * v.ndim, [slice(None)] * v.ndim
            dst[ax], src[ax] = (slice(0, -1), slice(1, None)) if s == 1 else (slice(1, None), slice(0, -1))
            w[tuple(dst)] = v[tuple(src)]
            st.append(w)
    return np.nanmedian(np.stack(st), 0)


def pick(v, nr, f):
    """argmax of v; ties -> fewer active rules, then smaller size. -> 5-tuple of indices."""
    mi = np.arange(v.shape[0]).reshape(-1, 1, 1, 1, 1)
    sc = v - 1e-7 * nr - 1e-9 * mi
    return np.unravel_index(int(np.argmax(sc)), v.shape)


def cell_vals(f, ci):
    g = GRIDS[f]
    return tuple(g[a][i] for a, i in zip(AX, ci))


# ------------------------------------------------------------------ one config -> rows

def analyze(days, D, ctl_days, meta, cells_out=None):
    """days: config day lists; ctl_days: list of control day lists (or None for the baseline). -> list of row dicts."""
    rows = []
    for f in FIRMS:
        P, B, MD, nr, walks = search_firm(days, D, f)
        ncell = int(np.prod(P.shape[1:]))
        for k, mod in enumerate(MODELS):
            raw = pick(P[k], nr, f)
            stb = pick(stable(P[k]), nr, f)
            sv = stable(P[k])
            row = dict(meta, firm=f, model=mod, cells=ncell, walks=walks)
            cellsel = {"rw": raw, "st": stb}
            evs = {}
            for tag, ci in cellsel.items():
                c = cell_vals(f, ci)
                for a, v in zip(AX, c):
                    row[f"{tag}_{a}"] = v
                row[f"{tag}_p5"] = float(P[(k,) + ci])
                row[f"{tag}_bust5"] = float(B[(k,) + ci])
                row[f"{tag}_med_days"] = float(MD[(k,) + ci])
                row[f"{tag}_n_rules"] = int(nr[ci])
                evs[tag] = c
            row["st_stab_med"] = float(sv[stb])
            row["rw_stab_med"] = float(sv[raw])
            o = eval_cell(days, D, f, evs["st"])[mod][3]
            row["st_ci_lo"], row["st_ci_hi"] = (round(x, 6) for x in E.block_ci([o])[0])
            assert abs(row["st_p5"] - o.mean()) < 1e-9, (row["st_p5"], o.mean())
            if ctl_days:
                for tag in ("rw", "st"):
                    pc = np.array([eval_cell(cd, D, f, evs[tag])[mod][:2] for cd in ctl_days])
                    row[f"{tag}_ctrl_p5"], row[f"{tag}_ctrl_sd"] = float(pc[:, 0].mean()), float(pc[:, 0].std(ddof=1))
                    row[f"{tag}_ctrl_bust5"] = float(pc[:, 1].mean())
                    row[f"{tag}_lift"] = row[f"{tag}_p5"] - row[f"{tag}_ctrl_p5"]
            rows.append(row)
    return rows


# ------------------------------------------------------------------ tasks

_POOLS, _TS = {}, {}


def _pool_srcs(tf, tod=False):
    fam = "tod_drift" if tod else "random"
    res = E.resolve_pool(E.profile_from(fam, {"tf": tf}))
    return res


def _pool(srcs):
    k = tuple(srcs)
    if k not in _POOLS:
        _POOLS[k] = E.concat_tr([E.load(s) for s in srcs])
    return _POOLS[k]


def _ts_of(src):
    if src not in _TS:
        t = E.load(src)
        z = np.zeros(t.n)
        _TS[src] = SA.TS(t.date, t.te, t.tx, t.side, t.g, t.mae, t.risk, z, t.sess, np.zeros(t.n, np.int16))
    return _TS[src]


def _sub(ts, sel):
    z = np.zeros(int(len(sel)))
    return SA.TS(ts.date[sel], ts.te[sel], ts.tx[sel], ts.side[sel], ts.g[sel], ts.mae[sel], ts.risk[sel], z, ts.sess[sel], np.zeros(len(sel), np.int16))


def _ctl_days(cfgts, pool, cal, D, seed, K):
    ctl = E.daymatched_controls(cfgts, pool, K=K, seed=seed, mask=None)
    out = []
    for c in ctl:
        n = len(c["date"])
        t = SA.TS(c["date"], c["te"], c["tx"], c["side"], c["g"], c["mae"], c["risk"], np.zeros(n), c["sess"], np.zeros(n, np.int16))
        out.append(t.days(np.ones(t.n, bool), cal))
    return out, float(np.mean([c["fb_share"] for c in ctl])), float(np.mean([len(set(c["date"].tolist())) for c in ctl]))


def task_real(a):
    row, K = a
    fam, tf, sess = row["fam"], int(row["tf"]), row["sess"]
    ts = SA.load_ts(row["run_id"])
    m = ts.sess == E.SESS_CODE[sess]
    res = E.resolve_pool(E.profile_from(fam, {"tf": tf}))
    pool = _pool(res["srcs"])
    cal = SA.cal_for(ts, pool)
    D = len(cal)
    sub = _sub(ts, np.flatnonzero(m))
    days = sub.days(np.ones(sub.n, bool), cal)
    ctl, fb, ctd = _ctl_days(sub, pool, cal, D, zlib.crc32(f"{fam}|{tf}|{sess}".encode()), K)
    meta = dict(kind="real", fam=fam, tf=tf, sess=sess, trades=sub.n, trade_days=int(sum(1 for d in days if d)), ctrl_trade_days=round(ctd, 1),
                fallback_share=round(fb, 5), pool_exact=res["exact"], pool_seeds=len(res["srcs"]))
    return analyze(days, D, ctl, meta)


def _seed_of(key):
    return int(re.search(r"-s(\d+)$", key).group(1))


def task_null(a):
    tf, sess, rep, tod, K, nmin = a
    res = _pool_srcs(tf, tod)
    seeds = list(zip(res["keys"], res["srcs"]))
    ident = f"null|{'tod' if tod else 'rand'}|{tf}|{sess}|{rep}"
    rg = np.random.default_rng(zlib.crc32(ident.encode()))
    order = rg.permutation(len(seeds))
    want = int(round(np.exp(rg.uniform(np.log(nmin), np.log(2500)))))
    for i in order:
        key, src = seeds[i]
        ts = _ts_of(src)
        cand = np.flatnonzero(ts.sess == E.SESS_CODE[sess])
        if len(cand) >= nmin:
            break
    else:
        return []
    n = min(want, len(cand))
    sel = np.sort(rg.choice(cand, n, replace=False))
    cfg = _sub(ts, sel)
    pool = _pool([s for j, (k2, s) in enumerate(seeds) if j != i])
    cal = SA.cal_for(cfg, pool)
    D = len(cal)
    days = cfg.days(np.ones(cfg.n, bool), cal)
    ctl, fb, ctd = _ctl_days(cfg, pool, cal, D, zlib.crc32(ident.encode()), K)
    meta = dict(kind="null", fam="random-tod" if tod else "random", tf=tf, sess=sess, trades=cfg.n, trade_days=int(sum(1 for d in days if d)),
                ctrl_trade_days=round(ctd, 1), fallback_share=round(fb, 5), pool_exact=True, pool_seeds=len(seeds) - 1,
                rep=rep, seed=_seed_of(key), n_req=want)
    return analyze(days, D, ctl, meta)


def task_base(a):
    tf, sess, tod, j = a
    res = _pool_srcs(tf, tod)
    key, src = res["keys"][j], res["srcs"][j]
    ts = _ts_of(src)
    m = np.flatnonzero(ts.sess == E.SESS_CODE[sess])
    if len(m) < 30:
        return []
    cfg = _sub(ts, m)
    cal = SA.cal_for(cfg)
    D = len(cal)
    days = cfg.days(np.ones(cfg.n, bool), cal)
    meta = dict(kind="base", fam="random-tod" if tod else "random", tf=tf, sess=sess, trades=cfg.n, trade_days=int(sum(1 for d in days if d)), seed=_seed_of(key))
    return analyze(days, D, None, meta)


# ------------------------------------------------------------------ driver

def write(path, rows):
    cols = []
    for r in rows:
        cols += [c for c in r if c not in cols]
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: (round(r[c], 6) if isinstance(r.get(c), float) else r.get(c, "")) for c in cols})


def run_pool(fn, tasks, workers, tag):
    t0, out = time.time(), []
    with get_context("spawn").Pool(workers) as pl:
        for i, x in enumerate(pl.imap_unordered(fn, tasks, chunksize=1), 1):
            out += x
            if i % 10 == 0 or i == len(tasks):
                print(f"[{tag}] {i}/{len(tasks)} tasks {time.time() - t0:.0f}s", flush=True)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--k", type=int, default=K_CTRL)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--min-trades", type=int, default=300)
    ap.add_argument("--suffix", default="")
    a = ap.parse_args(argv)
    stages = ["real", "null", "base", "summary"] if a.stage == "all" else [a.stage]
    lim = (lambda x: x[:a.limit]) if a.limit else (lambda x: x)
    if "real" in stages:
        rows = [r for r in csv.DictReader((OUT / "screen_table.csv").open()) if r["trades"] and int(r["trades"]) >= a.min_trades]
        rows.sort(key=lambda r: -int(r["trades"]))
        res = run_pool(task_real, lim([(r, a.k) for r in rows]), a.workers, "real")
        res.sort(key=lambda x: (x["fam"], x["tf"], list(E.SESS).index(x["sess"]), x["firm"], x["model"]))
        write(OUT / f"a3_rules_screen{a.suffix}.csv", res)
    if "null" in stages:
        tasks = [(tf, s, rep, False, a.k, a.min_trades) for rep in range(a.reps) for tf in (1, 5, 15, 30) for s in E.SESS]
        res = run_pool(task_null, lim(tasks), a.workers, "null")
        res.sort(key=lambda x: (x["tf"], list(E.SESS).index(x["sess"]), x["rep"], x["firm"], x["model"]))
        write(OUT / f"a3_null{a.suffix}.csv", res)
    if "base" in stages:
        tasks = []
        for tod in (False, True):
            for tf in (1, 5, 15, 30):
                n = len(_pool_srcs(tf, tod)["srcs"])
                tasks += [(tf, s, tod, j) for s in E.SESS for j in range(n)]
        res = run_pool(task_base, lim(tasks), a.workers, "base")
        res.sort(key=lambda x: (x["fam"], x["tf"], list(E.SESS).index(x["sess"]), x["seed"], x["firm"], x["model"]))
        write(OUT / f"a3_baseline{a.suffix}.csv", res)
    if "summary" in stages:
        import a3_summary
        a3_summary.main()


if __name__ == "__main__":
    main()
