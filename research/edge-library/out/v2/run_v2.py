"""ADMISSION v2 runner (copy of out/admit_r1/run_admit.py). One tape pass per job, the unit's session instance only (hold_to =
day), stores under runs_v2/<key>/. Ledger (cap 80,000, v2 part D): a candidate menu on 2024 or under stress = kind `grid`
(stage v2_pick / v2_stress); a control (C1 pool, random-minute / random-direction store) = kind `null` (stage null_v2_pick /
null_v2_stress / null_v2_build: uncapped).
  python out/v2/run_v2.py check <jobs.json>   identity of this runner with the BUILD store on 10 BUILD days (counts only)
  python out/v2/run_v2.py run   <jobs.json>   jobs: [{family, root, tf, sess, period, stress?, cells?, c1?, shift?, why}]
Stress = l2sim.STRESS (2 ticks + 250 ms) + Costs(oco_cancel_ms = 100) when the job says oco (two-sided brackets, v2 part C).
Every PICK job is appended to out/v2/pick_reads.csv BEFORE it runs. EXAM is never named (l2sim would raise)."""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
import families as F  # noqa: E402
import l2sim as S  # noqa: E402
import library as LB  # noqa: E402
import run_menus as RM  # noqa: E402
from families import l2ideas as L2I  # noqa: E402

OUT = W / "out" / "v2"
RA = W / "runs_v2"
READS = OUT / "pick_reads.csv"
CAPS = {"runs": 2000, "cells": 80000, "wfs": 40}
OCO_MS = 100


def job_key(j: dict) -> str:
    fam = f"c1-{j['root']}-tf{j['tf']}" if j.get("c1") else f"{j['family']}-{j['root']}-tf{j['tf']}"
    return "-".join(x for x in (fam, j["sess"], j["period"], "stress" if j.get("stress") else "", "shift" if j.get("shift") else "",
                                f"c2s{j['c2_seed']}" if j.get("c2_seed") else "") if x)


def job_grid(j: dict) -> tuple:
    if j.get("c1"):
        grid, cls, feats = RM.c1_grid(j["root"], j["tf"]), None, None
    elif j["family"] in L2I.STAGE_D:                 # a Level 2 filter / exit variant: the base's grid with the option on
        grid = L2I.variant_grid(j["family"], j["root"], j["tf"])
        cls = grid[0]["spec"][0]
        feats = L2I.variant_features(j["family"], j.get("c2_seed"))
    else:
        grid = F.unit_grid(j["family"], j["root"], j["tf"])
        cls = F.REGISTRY[j["family"]][0]
        feats = F.features_for(j["family"], c2_seed=j.get("c2_seed")) if j.get("c2_seed") else F.features_for(j["family"])
        if j.get("shift"):
            grid = RM.shift_grid(grid)
    if j.get("cells") is not None:
        keep = set(j["cells"])
        grid = [c for c in grid if c["id"] in keep or (j.get("shift") and c["id"].split("_", 1)[-1] in keep)]
    timed = cls is not None and RM.is_time_fired(cls)
    for c in grid:
        k, p = c["spec"]
        c["spec"] = (k, {**p, "hold_to": "day"} if timed else {**p, "sess": j["sess"], "hold_to": "day"})
    return grid, cls, feats, timed


def run_job(j: dict, days=None) -> tuple:
    grid, cls, feats, timed = job_grid(j)
    kw = dict(S.STRESS) if j.get("stress") else {}
    if j.get("stress") and j.get("oco"):
        kw["costs"] = S.Costs(oco_cancel_ms=OCO_MS)
    if cls is not None:
        kw.update(getattr(cls, "SCREEN_RUN", {}))
    specs = [c["spec"] for c in grid]
    S.wait_compute_window()
    if days is None:
        res = S.run_many(specs, period=j["period"], root=j["root"], workers=RM.auto_workers(), features=feats, **kw)
    else:
        res = S.run_many(specs, days=list(days), root=j["root"], workers=RM.auto_workers(4), features=feats, **kw)
    if not j.get("c1") and j["family"] in L2I.STAGE_D:
        for r in res:
            r["trades"] = L2I.kept(r["trades"])       # a trade the Level 2 filter refused never reaches a store
    if not timed:
        for r in res:
            r["trades"] = [t for t in r["trades"] if S.session_of(t["entry_ms"]) == j["sess"]]
    return grid, res


def check(jobs: list) -> int:
    bad, seen = 0, set()
    for j in jobs:
        key = f"c1-{j['root']}-tf{j['tf']}" if j.get("c1") else f"{j['family']}-{j['root']}-tf{j['tf']}" + ("-shift" if j.get("shift") else "") + (
            f"-c2s{j['c2_seed']}" if j.get("c2_seed") else "")
        if (key, j["sess"]) in seen:
            continue
        seen.add((key, j["sess"]))
        u = LB.load_unit(key)
        a, b = S.period("build")
        have = {d.isoformat() for d in S.sessions(a, b, j["root"])}
        days = [d for d in RM.SMOKE_DAYS if d in have]
        grid, res = run_job({**j, "period": "build", "stress": False}, days=days)
        ords = np.array([dt.date.fromisoformat(d).toordinal() for d in days])
        idx = {c["id"]: i for i, c in enumerate(u["meta"]["cells"])}
        n = diff = 0
        for c, r in zip(grid, res):
            x = LB.unit_cell(u, idx[c["id"]])
            m = np.isin(x["date"], ords)
            if not j.get("shift"):
                m &= x["sess"] == LB.SESS_CODE[j["sess"]]
            mine = sorted((t["entry_ms"], round(t["net"], 2)) for t in r["trades"])
            ref = sorted(zip(x["entry_ms"][m].tolist(), np.round(x["net"][m], 2).tolist()))
            n += len(ref)
            diff += mine != ref
        bad += diff
        print(f"check {key} {j['sess']}: {len(days)} days, {len(grid)} cells, {n} stored trades, cells that differ: {diff}", flush=True)
    return bad


def run(jobs: list) -> None:
    RA.mkdir(exist_ok=True)
    for j in jobs:
        key = job_key(j)
        if (RA / key / "run.json").exists():
            print("skip", key, flush=True)
            continue
        cand = not (j.get("c1") or j.get("shift") or j.get("c2_seed"))
        n_cells = len(job_grid(j)[0])
        what = ("stress " if j.get("stress") else "") + ("c1 control" if j.get("c1") else ("random-minute / random-direction control" if j.get("shift") else ("shuffled-book control" if j.get("c2_seed") else "whole menu")))
        if j["period"] == "pick":
            new = not READS.exists()
            with READS.open("a", newline="") as fh:
                w = csv.writer(fh)
                if new:
                    w.writerow(["utc", "key", "family", "root", "tf", "sess", "what", "cells", "why"])
                w.writerow([dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), key, j.get("family", "random"), j["root"], j["tf"],
                            j["sess"], what, n_cells, j.get("why", "")])
        t0 = time.monotonic()
        grid, res = run_job(j)
        errs = sum(r["skipped_by_error"] for r in res)
        if errs:
            print("ERROR", key, "sessions dropped by a strategy error; no store", flush=True)
            continue
        stage = ("" if cand else "null_") + "v2_" + ("stress" if j.get("stress") else j["period"])
        meta = {"family": j.get("family", "random"), "tf": str(j["tf"]), "stage": stage, "period": j["period"], "sess_instance": j["sess"],
                "stress": bool(j.get("stress")), "oco_cancel_ms": OCO_MS if (j.get("stress") and j.get("oco")) else 0, "hold_to": "day",
                "control": "c1" if j.get("c1") else ("shift" if j.get("shift") else ("c2" if j.get("c2_seed") else ("stress" if j.get("stress") else "pick")))}
        LB.write_unit(key, meta, grid, res, RA)
        LB.ledger_add(stage, key, "grid" if cand else "null", cells=len(grid), caps=CAPS, family=meta["family"], root=j["root"], tf=str(j["tf"]),
                      period=j["period"], control=meta["control"], trades=sum(len(r["trades"]) for r in res), elapsed_s=res[0]["elapsed_s"],
                      note=f"admission v2: session {j['sess']} only" + (f"; oco_cancel_ms {OCO_MS}" if meta["oco_cancel_ms"] else ""))
        print(f"done {key}: {len(grid)} cells, {sum(len(r['trades']) for r in res)} trades, wall {time.monotonic() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    mode, path = sys.argv[1], sys.argv[2]
    jobs = json.loads(Path(path).read_text())
    if mode == "check":
        sys.exit(1 if check(jobs) else 0)
    run(jobs)
