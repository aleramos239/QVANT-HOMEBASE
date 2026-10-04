#!/usr/bin/python3
"""Pass-1 style rules search (the SCREEN configs, family x tf x session with >= 300 trades) through the pass-3 machinery:
5 firms (lucid, lucidpro, lucidpro_nodll, apex, apex_eod), take rules (day_take / target_take), 3 breach models (primary per firm =
evalcore.primary_model), day-matched random controls at identical rules, optimised zero-edge null. Pilot-aware (PP_PILOT=es / --pilot es).
Run: PYTHONPATH=~/ramos-quant-homebase PP_PILOT=es /usr/bin/python3 a3p3_screen.py --stage snap|quick|real|null|summary|all [--workers 4]

Outputs (in the pilot's out/): a3p3s_quick.csv, a3p3s_rules.csv (one row per config x firm x cellset), a3p3s_null.csv.
Apex compliance (UNCONFIRMED rule set; flags only, per-config): comp_oco (family places OCO/both-side orders), comp_target (config has a
target: tgt_r > 0 so stop <= 5x target holds at tgt_r >= 0.2; default tgt_r 2.0 is compliant, tod_drift/time exits are not).
Snapshot files are a3p3s_snap_* (separate from a3p3's) so both passes can coexist."""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import zlib
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E          # noqa: E402
import a3_rules as A1         # noqa: E402
import a3p3 as P3             # noqa: E402

OUT = E.D / "out"
SNAP_L, SNAP_J = OUT / "a3p3s_snap_ledger.csv", OUT / "a3p3s_snap_jobs.jsonl"
for _m in (P3, P3.A2):                     # spawned workers re-import this module -> the overrides apply there too
    _m.SNAP_L, _m.SNAP_J = SNAP_L, SNAP_J
OCO_FAMS = {"orb", "straddle", "lon_break", "ib"}   # families that arm BOTH sides at default params (squeeze default bbkc = market entries; ib default mode = break)


def snapshot():
    if not SNAP_L.exists():
        shutil.copy(E.D / "ledger.csv", SNAP_L)
        shutil.copy(E.D / "jobs.jsonl", SNAP_J)


def sources_screen():
    out = {}
    for r in csv.DictReader(SNAP_L.open()):
        if r["stage"] == "screen" and r["run_id"]:
            p = json.loads(r["params_json"])
            out[r["key"]] = (r["run_id"], r["strategy"].replace(E.DRAFT_PREFIX, ""), int(p["tf"]), r["key"], {})
    return list(out.values())


def task_quick(a):
    return P3.task_quick(a)


def task_real(a):
    return P3.task_real3(a)


def task_null(a):
    return P3.task_null3(a)


def rd(name):
    return P3.rd(name)


def stage_quick(a):
    snapshot()
    res = A1.run_pool(task_quick, sources_screen(), a.workers, "quick")
    A1.write(OUT / "a3p3s_quick.csv", sorted(res, key=lambda x: (x["key"], list(E.SESS).index(x["sess"]))))


def decide(a):
    todo = {}
    for r in rd("a3p3s_quick.csv"):
        if int(r["trades"]) >= a.min_trades:
            todo[(r["key"], r["sess"])] = dict(net_le0=int(float(r["net_1nq"]) <= 0), fastpass=0, screen=1,
                                              comp_oco=int(r["fam"] in OCO_FAMS), comp_target=int(r["fam"] != "tod_drift"))
    return todo


def stage_real(a):
    todo = decide(a)
    q = {(r["key"], r["sess"]): r for r in rd("a3p3s_quick.csv")}
    by = defaultdict(list)
    for (key, sess), ex in todo.items():
        by[key].append((sess, P3.FIRMS5, ex))
    srcs = {s[3]: s for s in sources_screen()}
    tasks = [(*srcs[k][:5], sorted(v, key=lambda e: list(E.SESS).index(e[0])), a.k, False) for k, v in by.items()]
    tasks.sort(key=lambda x: -sum(int(q[(x[3], e[0])]["trades"]) for e in x[5]))
    if a.limit:
        tasks = tasks[a.offset: a.offset + a.limit]
    print(f"real: {sum(len(t[5]) for t in tasks)} configs in {len(tasks)} sources", flush=True)
    res = P3.A2.run_ckpt(task_real, tasks, lambda t: t[3], a.workers, "real", OUT / f"a3p3s_real_part{a.suffix}.jsonl")
    P3.write_rows(OUT / f"a3p3s_rules{a.suffix}.csv", res)


def stage_null(a):
    strata = defaultdict(list)
    todo = decide(a)
    for r in rd("a3p3s_quick.csv"):
        if (r["key"], r["sess"]) in todo:
            strata[(r["pool_id"], r["sess"])].append(int(r["trades"]))
    tasks = []
    for (pid, sess), ns in sorted(strata.items()):
        prof = E.profile_from("random", json.loads(pid))
        tasks += [(pid, sess, int(np.median(ns)), rep, a.k, prof) for rep in range(a.reps)]
    if a.limit:
        tasks = tasks[a.offset: a.offset + a.limit]
    print(f"null: {len(tasks)} pseudo-configs (strata = control pool x session)", flush=True)
    res = P3.A2.run_ckpt(task_null, tasks, lambda t: f"{t[0]}|{t[1]}|{t[3]}", a.workers, "null", OUT / f"a3p3s_null_part{a.suffix}.jsonl")
    res.sort(key=lambda x: (x["pool_id"], list(E.SESS).index(x["sess"]), x["key"], P3.FIRMS5.index(x["firm"]), P3.CELLSETS.index(x["cellset"])))
    A1.write(OUT / f"a3p3s_null{a.suffix}.csv", res)
    print(f"wrote {len(res)} null rows", flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--k", type=int, default=P3.K_CTRL)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--min-trades", type=int, default=300)
    ap.add_argument("--suffix", default="")
    a = ap.parse_args(argv)
    st = ["snap", "quick", "real", "null"] if a.stage == "all" else [a.stage]
    if "snap" in st:
        snapshot()
    if "quick" in st:
        stage_quick(a)
    if "real" in st:
        stage_real(a)
    if "null" in st:
        stage_null(a)


if __name__ == "__main__":
    main()
