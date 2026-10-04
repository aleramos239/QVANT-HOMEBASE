"""STAGE 2a runner (the same single-session instance as out/admit/run_admit.py; stores under runs_deepen/<key>/).
  python out/deepen/run_deepen.py check <jobs.json>   identity with the BUILD store on 10 BUILD days (dir = both jobs; counts only)
  python out/deepen/run_deepen.py run   <jobs.json>
job: {family, root, tf, sess, period, why, extra?: {"dir": "long"}, stress?: bool, cells?: [ids]}            a CANDIDATE grid
     {c1: true, root, tf, sess, period, why, extra?, seeds?: [..], exits?: [exit ids]}                      a random-entry control
Ledger: candidate grids = kind `grid` (stage deepen_build / deepen_pick / deepen_stress: they count against the 40,000 cap);
random-entry controls = kind `null` (stage null_deepen). Every PICK job is appended to out/deepen/pick_reads.csv BEFORE it runs.
Restartable: a job whose store exists is skipped. EXAM is never named (l2sim would raise)."""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
W = HERE.parents[1]
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
sys.path.insert(0, str(W / "out" / "admit"))
import families as F  # noqa: E402
import l2sim as S  # noqa: E402
import library as LB  # noqa: E402
import run_menus as RM  # noqa: E402

RD = W / "runs_deepen"
READS = HERE / "pick_reads.csv"
CAP_USED_BEFORE = 34808                      # the orchestrator's count (33,984 in ledger.csv + 824 re-booked PICK / stress cells)


def job_key(j: dict) -> str:
    fam = f"c1-{j['root']}-tf{j['tf']}" if j.get("c1") else f"{j['family']}-{j['root']}-tf{j['tf']}"
    ex = j.get("extra") or {}
    return "-".join(x for x in (fam, j["sess"], j["period"], f"dir{ex['dir']}" if ex.get("dir") else "",
                                "stress" if j.get("stress") else "", j.get("tag") or "") if x)


def job_grid(j: dict) -> tuple:
    ex = j.get("extra") or {}
    if j.get("c1"):
        import l2ref
        cls, feats, timed, grid = None, None, False, []
        exits = [(xi, x) for xi, x in enumerate(S.menu(j["root"])) if not j.get("exits") or S.cell_id(x) in set(j["exits"])]
        for sd in (j.get("seeds") or RM.NULL_SEEDS):
            for xi, x in exits:
                grid.append({"id": f"s{sd}_{S.cell_id(x)}", "variant": {"seed": sd}, "exit": x, "vi": sd - 1, "xi": xi,
                             "spec": (l2ref.Random, {"tf": str(j["tf"]), "p_entry": RM.C1_P_ENTRY, "seed": sd, **x})})
    else:
        grid = F.unit_grid(j["family"], j["root"], j["tf"])
        cls = F.REGISTRY[j["family"]][0]
        feats = F.features_for(j["family"])
        timed = RM.is_time_fired(cls)
        if j.get("cells") is not None:
            keep = set(j["cells"])
            grid = [c for c in grid if c["id"] in keep]
    for c in grid:
        k, p = c["spec"]
        c["spec"] = (k, {**p, **ex, "hold_to": "day"} if timed else {**p, "sess": j["sess"], **ex, "hold_to": "day"})
    return grid, cls, feats, timed


def run_job(j: dict, days=None) -> tuple:
    grid, cls, feats, timed = job_grid(j)
    kw = dict(S.STRESS) if j.get("stress") else {}
    if cls is not None:
        kw.update(getattr(cls, "SCREEN_RUN", {}))
    specs = [c["spec"] for c in grid]
    S.wait_compute_window()
    if days is None:
        res = S.run_many(specs, period=j["period"], root=j["root"], workers=RM.auto_workers(), features=feats, **kw)
    else:
        res = S.run_many(specs, days=list(days), root=j["root"], workers=RM.auto_workers(4), features=feats, **kw)
    if not timed:
        for r in res:
            r["trades"] = [t for t in r["trades"] if S.session_of(t["entry_ms"]) == j["sess"]]
    return grid, res


def check(jobs: list) -> int:
    bad = 0
    for j in jobs:
        if j.get("c1") or (j.get("extra") or {}).get("dir"):
            continue
        key = f"{j['family']}-{j['root']}-tf{j['tf']}"
        u = LB.load_unit(key)
        a, b = S.period("build")
        have = {d.isoformat() for d in S.sessions(a, b, j["root"])}
        days = [d for d in RM.SMOKE_DAYS if d in have]
        grid, res = run_job({**j, "period": "build", "stress": False}, days=days)
        ords = np.array([dt.date.fromisoformat(d).toordinal() for d in days])
        n = diff = 0
        for c, r in zip(grid, res):
            x = LB.unit_cell(u, c["id"])
            m = np.isin(x["date"], ords) & (x["sess"] == LB.SESS_CODE[j["sess"]])
            mine = sorted((t["entry_ms"], round(t["net"], 2)) for t in r["trades"])
            ref = sorted(zip(x["entry_ms"][m].tolist(), np.round(x["net"][m], 2).tolist()))
            n += len(ref)
            diff += mine != ref
        bad += diff
        print(f"check {key} {j['sess']}: {len(days)} days, {len(grid)} cells, {n} stored trades, cells that differ: {diff}", flush=True)
    return bad


def run(jobs: list) -> None:
    RD.mkdir(exist_ok=True)
    for j in jobs:
        key = job_key(j)
        if (RD / key / "run.json").exists():
            print("skip", key, flush=True)
            continue
        grid, _, _, _ = job_grid(j)
        cand = not j.get("c1")
        if cand:
            used = CAP_USED_BEFORE + sum(int(r["cells"] or 0) for r in LB.read_ledger() if r["stage"].startswith("deepen"))
            if used + len(grid) > LB.CAPS["cells"]:
                raise LB.CapExceeded(f"{key}: {used} used + {len(grid)} > cap {LB.CAPS['cells']}")
        if j["period"] == "pick":
            new = not READS.exists()
            with READS.open("a", newline="") as fh:
                w = csv.writer(fh)
                if new:
                    w.writerow(["utc", "key", "family", "root", "tf", "sess", "what", "cells", "why"])
                w.writerow([dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), key, j.get("family", "random"), j["root"], j["tf"],
                            j["sess"], "stress" if j.get("stress") else ("c1 control" if j.get("c1") else "whole menu"), len(grid),
                            j.get("why", "")])
        t0 = time.monotonic()
        grid, res = run_job(j)
        errs = sum(r["skipped_by_error"] for r in res)
        if errs:
            print("ERROR", key, "sessions dropped by a strategy error; no store", flush=True)
            continue
        stage = "null_deepen" if not cand else ("deepen_stress" if j.get("stress") else f"deepen_{j['period']}")
        meta = {"family": j.get("family", "random"), "tf": str(j["tf"]), "stage": stage, "period": j["period"], "sess_instance": j["sess"],
                "stress": bool(j.get("stress")), "hold_to": "day", "extra": j.get("extra") or {}, "why": j.get("why", ""),
                "control": "c1" if j.get("c1") else ("stress" if j.get("stress") else "")}
        LB.write_unit(key, meta, grid, res, RD)
        LB.ledger_add(stage, key, "grid" if cand else "null", cells=len(grid), family=meta["family"], root=j["root"], tf=str(j["tf"]),
                      period=j["period"], control=meta["control"], trades=sum(len(r["trades"]) for r in res), elapsed_s=res[0]["elapsed_s"],
                      note=f"stage 2a: session {j['sess']} only" + (f", dir {meta['extra']['dir']}" if meta["extra"].get("dir") else ""))
        print(f"done {key}: {len(grid)} cells, {sum(len(r['trades']) for r in res)} trades, wall {time.monotonic() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    mode, path = sys.argv[1], sys.argv[2]
    jobs = json.loads(Path(path).read_text())
    if mode == "check":
        sys.exit(1 if check(jobs) else 0)
    run(jobs)
