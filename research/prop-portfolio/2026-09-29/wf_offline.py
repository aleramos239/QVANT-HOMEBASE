#!/usr/bin/python3
"""Offline rolling walk-forward of the rule + heat-map-cell search (selection-bias check).
Run: PYTHONPATH=~/ramos-quant-homebase /usr/bin/python3 wf_offline.py --stage run|agg|all [--workers 8] [--kc 5] [--limit N]

Family grid = one heat-map grid (hm-<fam>-tf<tf>) x session that appears in out/shortlist_all.csv, plus the screen configs there
(a screen config is a one-config family grid). Its members = every (key, sess) of out/a3p2_rules.csv in that grid (the pass-2 config set).
Per firm (lucid = LucidFlex, lucidpro, lucidpro_nodll, apex) and breach model (eod | intraday), for test quarters 2022Q3..2024Q4:
  SELECT on the trailing 12 months before Q (attempts must END before Q; data starts 2021-09-22 so 2022Q3 has ~9 months): the
  (heat-map cell, rules cell) maximising the STABLE rolling-start P5 (pass-2 criterion: median of the rules cell and its +-1-step
  neighbours; ties -> fewer rules, smaller size), over the SAME rules grids as pass 2 / a3p2_lp (no coarsening).
  TEST on Q: rolling-start attempts starting in Q (they may run into the next quarter's first days). Stitch -> OOS P5, block CI.
Control: the same procedure on K day-matched random controls (the family's exact per-day/session trade counts, control pool with the
config's exit profile); independent selection per replicate, OOS control P5 = mean over replicates, lift CI = block bootstrap of the
paired per-start difference (real - mean control). Day walks are per-day independent, so one full-window walk per (config, rules cell)
serves every window; only the race start sets differ. Stages: run -> out/wf_offline_part.jsonl (resumable) ; agg -> out/wf_offline.csv +
out/wf_offline_summary.md."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import itertools
import json
import sys
import zlib
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E          # noqa: E402
import screen_analyze as SA   # noqa: E402
import a3_rules as A1         # noqa: E402
import a3_pass2 as A2         # noqa: E402
import a3p2_lp as LP          # noqa: E402  (registers lucidpro / lucidpro_nodll rule files + grids as an import side effect)

OUT = E.D / "out"
PART = OUT / "wf_offline_part.jsonl"
FIRMS = ("lucid", "lucidpro", "lucidpro_nodll", "apex")
FIRM_NAME = {"lucid": "lucid_flex", "lucidpro": "lucidpro", "lucidpro_nodll": "lucidpro_nodll", "apex": "apex", "apex_eod": "apex_eod"}
P3_FIRMS = ("lucid", "lucidpro", "lucidpro_nodll", "apex", "apex_eod")
PART3 = OUT / "wf_offline_p3_part.jsonl"
MODELS = ("eod", "intraday")
QUARTERS = [(y, q) for y in (2022, 2023, 2024) for q in (1, 2, 3, 4) if (y, q) >= (2022, 3)]      # 10 test quarters
KC = 5


def _o(y, m, d=1):
    return dt.date(y, m, d).toordinal()


def q_bounds(y, q):
    m = 3 * (q - 1) + 1
    return _o(y, m), (_o(y, m + 3) if q < 4 else _o(y + 1, 1)), _o(y - 1, m)      # test start, test end (excl), train start


def windows(cal):
    """-> (Wtr [S,Q] float32 normalised train weights, test start-index arrays, oos-period start indices).
    Start i (0..D-5) runs sessions i..i+4. Train: starts in the 12 months before Q whose 5th session is before Q."""
    D = len(cal)
    S = D - E.H_EVAL + 1
    d0, d4 = cal[:S], cal[E.H_EVAL - 1:]
    W = np.zeros((S, len(QUARTERS)))
    tests = []
    for j, (y, q) in enumerate(QUARTERS):
        a, b, lo = q_bounds(y, q)
        tr = (d0 >= lo) & (d4 < a)
        W[:, j] = tr / max(tr.sum(), 1)
        tests.append(np.flatnonzero((d0 >= a) & (d0 < b)))
    oos = np.flatnonzero(d0 >= q_bounds(*QUARTERS[0])[0])
    return W, tests, oos


def search_ps(port, D, f, mods=None):
    """Full pass-2 rules grid for firm f -> (PS[len(mods), cells, S] bool pass flags per rolling start, nr[shape], shape, walks).
    mods: breach models raced (default MODELS); a3_pass2.race_all reads A2.MODELS, set here for the call."""
    mods = tuple(mods or MODELS)
    A2.MODELS = mods
    g = A2.GR[f]
    rid, r, dll = SA.firm(f)
    shape = tuple(len(g[a]) for a in A2.AX)
    S = D - E.H_EVAL + 1
    PS = np.zeros((len(mods), int(np.prod(shape)), S), bool)
    nr = np.zeros(shape)
    cache = {}
    for flat, ci in enumerate(itertools.product(*[range(n) for n in shape])):
        m, dl, dtk, ds, mt, tt = (g[a][i] for a, i in zip(A2.AX, ci))
        nr[ci] = (dl > 0) + (dtk > 0) + (ds > 0) + (mt > 0) + tt
        key = A2.norm_walk(port, m, dl, dtk, ds, mt)
        if key not in cache:
            cache[key] = A2.race_all(A2.make_A(port, r, dll, *key), r, D)
        for k, mod in enumerate(mods):
            PS[k, flat] = cache[key][tt][mod][3]
    return PS, nr, shape, len(cache)


def reduce_cfg(PS, nr, shape, W, tests, oos, mods=None):
    """Per model: full-window stable pick + one stable pick per test quarter (score, cell, train P5, test pass flags)."""
    mods = tuple(mods or MODELS)
    Pf = PS.astype(np.float64)
    train = np.einsum('kcs,sq->kcq', Pf, W)                   # [models, cells, Q]
    full = Pf.mean(-1)                                    # [models, cells]
    o = {}
    for k, mod in enumerate(mods):
        def sel(v):
            sv = A1.stable(v.reshape(shape).astype(float))
            ci = A2.pick(sv, nr)
            return ci, float(sv[ci] - 1e-7 * nr[ci] - 1e-9 * ci[0]), float(sv[ci]), int(np.ravel_multi_index(ci, shape))
        ci, sc, sv, flat = sel(full[k])
        o[mod] = {"full": dict(cell=flat, score=sc, stable=sv, p5=float(full[k, flat]), p5_oos=float(Pf[k, flat, oos].mean())), "q": []}
        for j in range(len(QUARTERS)):
            ci, sc, sv, flat = sel(train[k, :, j])
            o[mod]["q"].append(dict(cell=flat, score=sc, stable=sv, train_p5=float(train[k, flat, j]),
                                    test=PS[k, flat, tests[j]].astype(int).tolist()))
    return o


def pick_across(per_cfg, mods=None):
    """per_cfg: list (config order) of reduce_cfg outputs -> per model {full: {...cfg}, q: [ {...cfg} ]} (best score; first on ties)."""
    res = {}
    for mod in (mods or MODELS):
        bf = max(range(len(per_cfg)), key=lambda c: (per_cfg[c][mod]["full"]["score"], -c))
        res[mod] = {"full": dict(per_cfg[bf][mod]["full"], cfg=bf), "q": []}
        for j in range(len(QUARTERS)):
            b = max(range(len(per_cfg)), key=lambda c: (per_cfg[c][mod]["q"][j]["score"], -c))
            res[mod]["q"].append(dict(per_cfg[b][mod]["q"][j], cfg=b))
    return res


def task(a):
    grid, sess, f, members, kc = a[:5]
    mods = tuple(a[5]) if len(a) > 5 else MODELS          # pass 3: (eod, primary model of the firm)
    if len(a) > 5:
        import a3p3       # noqa: F401  (pass-3 snapshot paths + apex_eod grid; module patches A2 on import, workers included)
    LP.gate()
    ts = {m[3]: A2.load_src(m[0]) for m in members}
    pl = A2.resolve(E.profile_from(members[0][1], dict(members[0][4], tf=members[0][2])))
    pool = A2.pool_of(pl["srcs"])
    cal = SA.cal_for(*ts.values(), pool)
    D = len(cal)
    W, tests, oos = windows(cal)
    sc = E.SESS_CODE[sess]
    out = {"grid": grid, "sess": sess, "firm": f, "members": [m[3] for m in members], "D": D, "n_starts": D - E.H_EVAL + 1, "models": list(mods),
           "test_dates": [[int(cal[i]) for i in tt] for tt in tests], "reps": []}
    ports = {}
    for m in members:
        t = ts[m[3]]
        idx = np.flatnonzero(t.sess == sc)
        ports[m[3]] = [A2.port_of(t, idx, cal)]
        if kc:
            cps, _, _ = A2.ctl_ports(dict(date=t.date[idx], sess=t.sess[idx]), pool, cal, zlib.crc32(f"{m[3]}|{sess}".encode()), kc)
            ports[m[3]] += cps
    for rep in range(kc + 1):                             # rep 0 = the real configs, 1..kc = day-matched controls
        per_cfg, walks = [], 0
        for m in members:
            PS, nr, shape, w = search_ps(ports[m[3]][rep], D, f, mods)
            walks += w
            per_cfg.append(reduce_cfg(PS, nr, shape, W, tests, oos, mods))
        sel = pick_across(per_cfg, mods)
        sel["rep"], sel["walks"] = rep, walks
        for mod in mods:
            for x in [sel[mod]["full"]] + sel[mod]["q"]:
                x["rules"] = [A2.GR[f][ax][i] for ax, i in zip(A2.AX, np.unravel_index(x["cell"], shape))]
        out["reps"].append(sel)
    return [out]


def gather():
    """-> [(grid, sess, members)] : family grids of shortlist_all.csv, members = the pass-2 (key, sess) configs of that grid."""
    sl = {(r["strategy_id"].split("|")[1].split("#")[0], r["sess"]) for r in csv.DictReader((OUT / "shortlist_all.csv").open())}
    srcs = {s[3]: s for s in A2.sources()}
    mem = defaultdict(list)
    for r in csv.DictReader((OUT / "a3p2_rules.csv").open()):
        if r["model"] == "eod" and r["firm"] == "lucid" and (r["key"].split("#")[0], r["sess"]) in sl:
            mem[(r["key"].split("#")[0], r["sess"])].append(srcs[r["key"]])
    for k in mem:
        mem[k].sort(key=lambda s: s[3])
    assert set(mem) == sl, sl - set(mem)
    return sorted(((g, s, m) for (g, s), m in mem.items()), key=lambda x: -len(x[2]))


def gather3(top=12, screen=False):
    """Pass 3: per firm, the `top` family-grid x session sets ranked by the best primary-model P5 of any member (pass-3 configs of out/a3p3_rules.csv,
    cellset p5_<primary>); members = every pass-3 (key, sess) of that grid x session. -> {firm: [(grid, sess, members, best_p5)]}."""
    import a3p3 as P3
    srcs = {s[3]: s for s in P3.sources3()}
    rows = list(csv.DictReader((OUT / "a3p3_rules.csv").open()))
    if screen:         # ES: the screen configs (a3p3_screen.py -> a3p3s_rules.csv) are one-config family grids next to the heat-map grids
        srcs.update({s[3]: s for s in A2.sources() if s[3].startswith("screen-")})
        rows += [r for r in csv.DictReader((OUT / "a3p3s_rules.csv").open())]
    best, mem = defaultdict(dict), defaultdict(set)
    for r in rows:
        gs = (r["key"].split("#")[0], r["sess"])
        mem[gs].add(r["key"])
        if r["cellset"] == f"p5_{E.primary_model(r['firm'])}":
            v = float(r[f"{E.primary_model(r['firm'])}_p5"])
            best[r["firm"]][gs] = max(v, best[r["firm"]].get(gs, -1.0))
    out = {}
    for f in P3_FIRMS:
        top_sets = sorted(best[f].items(), key=lambda kv: (-kv[1], kv[0]))[:top]
        out[f] = [(g, s, sorted((srcs[k] for k in mem[(g, s)]), key=lambda x: x[3]), v) for (g, s), v in top_sets]
    return out


def stage_run(a):
    if a.pass3:
        import a3p3 as P3
        tasks = []
        for f, sets in gather3(a.top, a.screen).items():
            tasks += [(g, s, f, m, a.kc, ("eod", E.primary_model(f))) for g, s, m, _ in sets]
        tasks.sort(key=lambda t: -len(t[3]))
        if a.rev:          # second process working from the lightest end; own part file (agg dedupes by task id)
            tasks = tasks[::-1]
        if a.limit:
            tasks = tasks[: a.limit]
        print(f"wf run (pass 3): {len(tasks)} tasks (firm top-{a.top} family-grid x session), models eod+primary, kc={a.kc}, workers={a.workers}", flush=True)
        A2.run_ckpt(task, tasks, lambda t: f"{t[0]}|{t[1]}|{t[2]}", a.workers, "wf3", PART3.with_name("wf_offline_p3_part_b.jsonl") if a.rev else PART3)
        return
    A2.snapshot()
    tasks = [(g, s, f, m, a.kc) for g, s, m in gather() for f in FIRMS]
    tasks.sort(key=lambda t: -len(t[3]) * (2 if t[4] and t[2] == "apex" else 1))
    if a.limit:
        tasks = tasks[: a.limit]
    print(f"wf run: {len(tasks)} tasks (family-grid x session x firm), kc={a.kc}, workers={a.workers}", flush=True)
    A2.run_ckpt(task, tasks, lambda t: f"{t[0]}|{t[1]}|{t[2]}", a.workers, "wf", PART)


# ------------------------------------------------------------------ aggregate

def stitch(reps_mod, key="test"):
    return np.array([v for q in reps_mod for v in q[key]], float)


def agg_task(o):
    """One task record -> rows (one per model)."""
    years = np.array([dt.date.fromordinal(d).year for q in o["test_dates"] for d in q])
    rows = []
    for mod in o.get("models", MODELS):
        real = o["reps"][0][mod]
        ps = stitch(real["q"])
        ctl = [stitch(r[mod]["q"]) for r in o["reps"][1:]]
        n = len(ps)
        p5 = float(ps.mean())
        lo, hi = E.block_ci([ps])[0]
        row = dict(grid=o["grid"], fam=o["grid"].split("-")[1] if "-" in o["grid"] else o["grid"], sess=o["sess"], firm=FIRM_NAME[o["firm"]], model=mod,
                   n_cfg=len(o["members"]), is_p5=real["full"]["p5"], is_stable=real["full"]["stable"], is_p5_oosperiod=real["full"]["p5_oos"],
                   is_cfg=o["members"][real["full"]["cfg"]], is_rules="/".join(str(x) for x in real["full"]["rules"]),
                   oos_p5=p5, oos_ci_lo=lo, oos_ci_hi=hi, drop=real["full"]["p5"] - p5, n_oos=n)
        if ctl:
            cm = np.mean(ctl, 0)
            cp = [float(c.mean()) for c in ctl]
            dlo, dhi = E.block_ci([ps - cm])[0]
            row.update(ctrl_oos_p5=float(np.mean(cp)), ctrl_oos_sd=float(np.std(cp, ddof=1)) if len(cp) > 1 else float("nan"),
                       oos_lift=p5 - float(np.mean(cp)), lift_ci_lo=dlo, lift_ci_hi=dhi, n_ctrl=len(ctl))
            row["survive"] = int(row["oos_lift"] > 0 and dhi > 0)
            row["survive_strict"] = int(dlo > 0)
        q = real["q"]
        pk = [(x["cfg"], x["cell"]) for x in q]
        tr = len(pk) - 1
        row.update(stab_cfg_change=sum(pk[i][0] != pk[i + 1][0] for i in range(tr)) / tr,
                   stab_rules_change=sum(pk[i][1] != pk[i + 1][1] for i in range(tr)) / tr,
                   stab_pick_change=sum(pk[i] != pk[i + 1] for i in range(tr)) / tr, n_distinct_picks=len(set(pk)),
                   mean_train_p5=float(np.mean([x["train_p5"] for x in q])),
                   train_minus_oos=float(np.mean([x["train_p5"] for x in q])) - p5)
        for y in (2022, 2023, 2024):
            row[f"oos_p5_{y}"] = float(ps[years == y].mean()) if (years == y).any() else float("nan")
            if ctl:
                row[f"ctrl_p5_{y}"] = float(np.mean([c[years == y].mean() for c in ctl])) if (years == y).any() else float("nan")
        rows.append(row)
    return rows


def stage_agg(a):
    files = [PART3, PART3.with_name("wf_offline_p3_part_b.jsonl")] if a.pass3 else [PART]
    recs = {}
    for fp in files:
        for ln in (fp.read_text().splitlines() if fp.exists() else []):
            if ln.strip():
                j = json.loads(ln)
                recs[j["id"] if "id" in j else ln[:80]] = j["rows"][0]
    recs = list(recs.values())
    rows = [r for o in recs for r in agg_task(o)]
    order = {f: i for i, f in enumerate(FIRM_NAME.values())}
    rows.sort(key=lambda r: (order[r["firm"]], r["model"], -r["oos_p5"]))
    if a.pass3:
        A1.write(OUT / "wf_offline_p3.csv", rows)
    else:
        A1.write(OUT / "wf_offline.csv", rows)
        write_summary(rows)
    print(f"wrote {len(rows)} rows", flush=True)


def write_summary(rows):
    f3 = lambda x: f"{x:.2f}".lstrip("0") if x == x else "nan"
    nc = rows[0].get("n_ctrl", 0)
    L = ["# Offline walk-forward of the (heat-map cell, rules) search, test quarters 2022Q3..2024Q4 (wf_offline.py; details wf_offline.csv)",
         "Each quarter SELECTS the (cell, rules) with the best stable rolling-start P5 on the trailing 12 months (attempts end before Q; 2022Q3 has ~9 months),",
         f"TESTS on attempts starting in Q, stitched. Rules grids = pass 2 / a3p2_lp, NOT coarsened. Control = the same selection on {nc} day-matched random controls.",
         "Entry = family-grid/session OOS-P5 (lift vs control OOS); * = survives (lift > 0 and lift CI upper > 0), ** = lift CI lower > 0. Apex UNCONFIRMED."]
    for mod in MODELS:
        for f in FIRM_NAME.values():
            rs = [r for r in rows if r["firm"] == f and r["model"] == mod][:20]
            L.append(f"## {mod} / {f}{' (UNCONFIRMED)' if f == 'apex' else ''} top 20 by OOS P5 (median IS {f3(np.median([r['is_p5'] for r in rs]))})")
            ent = [f"{r['grid'].replace('hm-', '').replace('screen-', 's-')}/{r['sess']} {f3(r['oos_p5'])}({r.get('oos_lift', float('nan')):+.2f})"
                   f"{'**' if r.get('survive_strict') else '*' if r.get('survive') else ''}" for r in rs]
            for i in range(0, len(ent), 4):
                L.append("  " + " | ".join(ent[i:i + 4]))
    by = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        k = f"{r['grid'].replace('hm-', '').replace('screen-', 's-')}/{r['sess']}"
        by[k][0] += 1
        by[k][1] += r.get("survive", 0)
        by[k][2] += r.get("survive_strict", 0)
    L.append("## Families x sessions that survive OOS (rows surviving of 8 = 4 firms x 2 models; strict in brackets)")
    ent = [f"{k} {v[1]}/{v[0]}({v[2]})" for k, v in sorted(by.items(), key=lambda kv: (-kv[1][1], kv[0])) if v[1]]
    for i in range(0, len(ent), 4):
        L.append("  " + " | ".join(ent[i:i + 4]))
    L.append(f"Median IS->OOS drop {np.median([r['drop'] for r in rows]):.3f}; median OOS lift {np.nanmedian([r.get('oos_lift', np.nan) for r in rows]):+.3f}; "
             f"median share of quarter-to-quarter pick changes {np.median([r['stab_pick_change'] for r in rows]):.2f}.")
    (OUT / "wf_offline_summary.md").write_text("\n".join(L) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--kc", type=int, default=KC)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--pass3", action="store_true", help="pass-3 mode: top --top family-grid x session sets per firm of out/a3p3_rules.csv, "
                    "models eod + the firm's primary model, 5 firms; writes out/wf_offline_p3{_part.jsonl,.csv}")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--screen", action="store_true", help="pass 3: also rank the screen configs (a3p3s_rules.csv, one-config grids) next to the heat-map grids (ES)")
    ap.add_argument("--rev", action="store_true", help="pass 3: run the tasks lightest-first into wf_offline_p3_part_b.jsonl (second process)")
    a = ap.parse_args(argv)
    if a.stage in ("run", "all"):
        stage_run(a)
    if a.stage in ("agg", "all"):
        stage_agg(a)


if __name__ == "__main__":
    main()
