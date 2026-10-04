#!/usr/bin/python3
"""A3 pass 2 for the two LucidPro rule sets + fast-pass metrics (P(pass by day k)) for ALL four firms.
Run: PYTHONPATH=~/ramos-quant-homebase /usr/bin/python3 a3p2_lp.py --stage real|null|fast|shortlist|all [--workers 8]

Reuses a3_pass2 (same 1,719 configs = out/a3p2_rules.csv's (key, sess) set, same stable-cell search, day-matched controls, per-profile null),
registering firms lucidpro = lucid-pro-50k@2026-09-27b ($1,200 soft DLL from the rule file) and lucidpro_nodll = lucid-pro-50k-no-dll@2026-09-27b.
LucidPro grid: micros {10,20,30,40} x day_lock {0,1000,2000} x day_take {0,1500,2000,3000} x day_stop {0,1000,2000} x max_day_tr {1,0} x target_take {0,1}
(576 cells; the rule-file DLL applies automatically through evalcore.walk/race: day_stop 0 or >1200 == the DLL for lucidpro).
Stages: real -> out/a3p2_lucidpro.csv ; null -> rows merged into out/a3p2_null.csv (firm tags lucidpro / lucidpro_nodll) ;
fast -> out/a3p2_fast.csv (P1/P2/P3/P5, bust5, median days, cost per funded at each config x firm's eod-stable and intraday-optimal cell, both breach models) ;
shortlist -> out/shortlist_all.csv (top 40 per firm by eod P5) + out/a3p2_lucidpro_summary.md.
Desk-window rule: no compute 09:06-09:36 ET weekdays between chunks (gate())."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E          # noqa: E402
import screen_analyze as SA   # noqa: E402
import a3_rules as A1         # noqa: E402
import a3_pass2 as A2         # noqa: E402

OUT = E.D / "out"
LP = ("lucidpro", "lucidpro_nodll")
ALL4 = ("lucid", "lucidpro", "lucidpro_nodll", "apex")
E.FIRMS["lucidpro"] = "lucid-pro-50k@2026-09-27b"
E.FIRMS["lucidpro_nodll"] = "lucid-pro-50k-no-dll@2026-09-27b"
_G = {"micros": [10, 20, 30, 40], "day_lock": [0, 1000, 2000], "day_take": [0, 1500, 2000, 3000], "day_stop": [0, 1000, 2000],
      "max_day_tr": [1, 0], "target_take": [0, 1]}
for _f in LP:
    A2.GR[_f] = {k: list(v) for k, v in _G.items()}
A2.FIRMS = LP        # a3_pass2.task_null reads this global (spawned workers re-run this module's import, so they are patched too)
ET = ZoneInfo("America/New_York")
CHUNK = 40


def gate(margin_min=12):
    """Block while the ET clock is in (or within margin_min of) the 09:18-09:36 weekday desk window."""
    while True:
        n = dt.datetime.now(ET)
        lo, hi = n.replace(hour=9, minute=18 - margin_min if margin_min <= 18 else 0, second=0, microsecond=0), n.replace(hour=9, minute=36, second=0, microsecond=0)
        if n.weekday() < 5 and lo <= n < hi:
            s = (hi - n).total_seconds() + 5
            print(f"[gate] {n:%H:%M} ET in/near desk window, sleeping {s:.0f}s", flush=True)
            time.sleep(s)
        else:
            return


def task_real_lp(a):
    return A2.task_real(a)


def task_null_lp(a):
    return A2.task_null(a)


def rd(name):
    return list(csv.DictReader((OUT / name).open()))


def chunked_ckpt(fn, tasks, idf, workers, tag, path):
    """A2.run_ckpt in chunks with the desk-window gate between chunks; returns all rows (resumable)."""
    rows = []
    for i in range(0, max(len(tasks), 1), CHUNK):
        gate()
        rows = A2.run_ckpt(fn, tasks[i:i + CHUNK], idf, workers, f"{tag} chunk{i // CHUNK}", path)
    return rows if tasks else A2.run_ckpt(fn, [], idf, workers, tag, path)


def all_rows_from_ckpt(path):
    rows = []
    for ln in path.read_text().splitlines():
        if ln.strip():
            rows += json.loads(ln)["rows"]
    return rows


# ------------------------------------------------------------------ real / null

def real_tasks(k):
    rules = rd("a3p2_rules.csv")
    ents = {}
    for r in rules:
        if r["model"] == "eod" and r["firm"] == "lucid":
            ents[(r["key"], r["sess"])] = dict(forced=int(r["forced"] or 0), net_le0=int(r["net_le0"] or 0), quick_thr_lucid=r["quick_thr_lucid"], quick_thr_apex=r["quick_thr_apex"])
    q = {(r["key"], r["sess"]): r for r in rd("a3p2_quick.csv")}
    by = defaultdict(list)
    for (key, sess), ex in ents.items():
        by[key].append((sess, LP, ex))
    srcs = {s[3]: s for s in A2.sources()}
    tasks = [(*srcs[kk][:5], sorted(v, key=lambda e: list(E.SESS).index(e[0])), k) for kk, v in by.items()]
    tasks.sort(key=lambda x: -sum(int(q[(x[3], e[0])]["trades"]) for e in x[5]))
    return tasks, len(ents)


def stage_real(a):
    A2.snapshot()
    tasks, n = real_tasks(a.k)
    if a.limit:
        tasks = tasks[: a.limit]
    print(f"real(lucidpro): {sum(len(t[5]) for t in tasks)} configs ({n} in rules.csv) in {len(tasks)} sources", flush=True)
    path = OUT / f"a3p2_lp_real_part{a.suffix}.jsonl"
    chunked_ckpt(task_real_lp, tasks, lambda t: t[3], a.workers, "lp-real", path)
    res = all_rows_from_ckpt(path)
    res.sort(key=lambda x: (x["key"], list(E.SESS).index(x["sess"]), x["firm"], x["model"]))
    A1.write(OUT / f"a3p2_lucidpro{a.suffix}.csv", res)
    print(f"wrote {len(res)} rows", flush=True)


def stage_null(a):
    q = rd("a3p2_quick.csv")
    done = {(r["key"], r["sess"]) for r in rd("a3p2_rules.csv") if r["model"] == "eod" and r["firm"] == "lucid"}
    strata = defaultdict(list)
    for r in q:
        if int(r["trades"]) >= 300 and (r["key"], r["sess"]) in done:
            strata[(r["pool_id"], r["sess"])].append(int(r["trades"]))
    tasks = []
    for (pid, sess), ns in sorted(strata.items()):
        prof = E.profile_from("random", json.loads(pid))
        tasks += [(pid, sess, int(np.median(ns)), rep, a.k, prof) for rep in range(a.reps)]
    if a.limit:
        tasks = tasks[: a.limit]
    print(f"null(lucidpro): {len(tasks)} pseudo-configs", flush=True)
    path = OUT / f"a3p2_lp_null_part{a.suffix}.jsonl"
    chunked_ckpt(task_null_lp, tasks, lambda t: f"{t[0]}|{t[1]}|{t[3]}", a.workers, "lp-null", path)
    res = all_rows_from_ckpt(path)
    if a.limit:
        print("limit run: not merging into a3p2_null.csv")
        return
    old = rd("a3p2_null.csv")
    keep = [r for r in old if r["firm"] not in LP]
    res.sort(key=lambda x: (x["pool_id"], list(E.SESS).index(x["sess"]), x["firm"], x["model"]))
    A1.write(OUT / "a3p2_null.csv", keep + res)
    print(f"a3p2_null.csv: kept {len(keep)} rows, added {len(res)} lucidpro rows", flush=True)


# ------------------------------------------------------------------ fast-pass metrics (all four firms)

def cellof(r, tag="st"):
    return tuple(int(float(r[f"{tag}_{a}"] or 0)) for a in A2.AX)


def fees():
    fj = json.loads(E.PL.shared("fees.json").read_text())
    out = {}
    for f in ALL4:
        rid = E.FIRMS[f]
        out[f] = (float(fj[rid]["eval_fee"]), float(fj[rid].get("activation", 0.0)))
    return out


def detail(o, d):
    ps, bs = o == 1, o == 2
    x = {f"p{k}": float((ps & (d <= k)).mean()) for k in (1, 2, 3, 5)}
    x["bust5"] = float(bs.mean())
    x["bust1"] = float((bs & (d <= 1)).mean())
    x["med_days"] = float(np.median(d[ps])) if ps.any() else float("nan")
    return x, ps


def eval_detail(port, D, f, cell):
    """{model: metrics} for one rule cell (both breach models)."""
    rid, r, dll = SA.firm(f)
    m, dl, dtk, ds, mt, tt = cell
    A = A2.make_A(port, r, dll, *A2.norm_walk(port, m, dl, dtk, ds, mt))
    idx5 = A2.idx5_of(D)
    res = {}
    for mod in A2.MODELS:
        o, d = E.race(idx5, A, r, mod, True, bool(tt))
        res[mod] = detail(o, d)[0]
    return res


def task_fast(a):
    src, fam, tf, key, params, ents = a       # ents: [(sess, {firm: {"eod": cell, "intraday": cell}, ...}, {firm: {"eod": p5, "intraday": xi_p5}})]
    t = A2.load_src(src)
    prof = E.profile_from(fam, dict(params, tf=tf))
    pl = A2.resolve(prof)
    pool = A2.pool_of(pl["srcs"])
    rows = []
    for sess, cells, chk in ents:
        idx = np.flatnonzero(t.sess == E.SESS_CODE[sess])
        cal = SA.cal_for(t, pool)
        port = A2.port_of(t, idx, cal)
        D = len(cal)
        for f, cs in cells.items():
            cache = {}
            for tag, cell in cs.items():
                if cell not in cache:
                    cache[cell] = eval_detail(port, D, f, cell)
                ev = cache[cell]
                row = dict(key=key, sess=sess, firm=f, cellset="eod_stable" if tag == "eod" else "intra_opt", cell=json.dumps(cell))
                for mod in A2.MODELS:
                    for k, v in ev[mod].items():
                        row[f"{mod}_{k}"] = v
                # consistency with the search row (the model the cell was optimised for)
                if chk.get(f, {}).get(tag) is not None:
                    row["check_p5_diff"] = abs(ev[tag]["p5"] - chk[f][tag])
                rows.append(row)
    return rows


def fast_tasks(limit=0):
    tasks_by = defaultdict(list)
    srcs = {s[3]: s for s in A2.sources()}
    rows = rd("a3p2_rules.csv") + rd("a3p2_lucidpro.csv")
    cfg = defaultdict(lambda: defaultdict(dict))
    chk = defaultdict(lambda: defaultdict(dict))
    for r in rows:
        cfg[(r["key"], r["sess"])][r["firm"]][r["model"]] = cellof(r)
        chk[(r["key"], r["sess"])][r["firm"]][r["model"]] = float(r["st_p5"])
    for (key, sess), fc in cfg.items():
        tasks_by[key].append((sess, {f: v for f, v in fc.items() if len(v) == 2}, {f: dict(v) for f, v in chk[(key, sess)].items()}))
    tasks = [(*srcs[k][:5], v) for k, v in tasks_by.items()]
    tasks.sort(key=lambda x: -len(x[5]))
    return tasks[:limit] if limit else tasks


def stage_fast(a):
    tasks = fast_tasks(a.limit)
    print(f"fast: {sum(len(t[5]) for t in tasks)} configs in {len(tasks)} sources", flush=True)
    path = OUT / f"a3p2_fast_part{a.suffix}.jsonl"
    chunked_ckpt(task_fast_w, tasks, lambda t: t[3], a.workers, "fast", path)
    res = all_rows_from_ckpt(path)
    fe = fees()
    for r in res:
        fee, act = fe[r["firm"]]
        for mod in A2.MODELS:
            p = r[f"{mod}_p5"]
            r[f"{mod}_cost_per_funded"] = fee / p + act if p > 0 else float("nan")
    res.sort(key=lambda x: (x["key"], list(E.SESS).index(x["sess"]), ALL4.index(x["firm"]), x["cellset"]))
    A1.write(OUT / f"a3p2_fast{a.suffix}.csv", res)
    d = [r["check_p5_diff"] for r in res if "check_p5_diff" in r]
    print(f"wrote {len(res)} rows; max |P5 - search P5| = {max(d):.2e}", flush=True)


def task_fast_w(a):
    return task_fast(a)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--k", type=int, default=A2.K_CTRL)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--suffix", default="")
    ap.add_argument("--reps", type=int, default=2)
    a = ap.parse_args(argv)
    st = ["real", "null", "fast", "shortlist"] if a.stage == "all" else [a.stage]
    if "real" in st:
        stage_real(a)
    if "null" in st:
        stage_null(a)
    if "fast" in st:
        stage_fast(a)
    if "shortlist" in st:
        import a3p2_lp_summary
        a3p2_lp_summary.main()


if __name__ == "__main__":
    main()
