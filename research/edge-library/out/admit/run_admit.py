"""ADMIT stage runner (plan: progress.md 2026-10-04 04:33 ET, C / D / H). One tape pass per job, the passing session's instance
only (hold_to = day), stores under runs_admit/<key>/, ledger rows kind `null` (stage null_pick / null_stress: tracked, uncapped).
  python out/admit/run_admit.py check   <jobs.json>     identity of this runner with the BUILD store on 10 BUILD days (counts only)
  python out/admit/run_admit.py run     <jobs.json>     jobs: [{family, root, tf, sess, period, stress?, cells?, c1?, c2_seed?, shift?}]
Every PICK job is appended to out/admit/pick_reads.csv BEFORE it runs. EXAM is never named (l2sim would raise)."""
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

OUT = W / "out" / "admit"
RA = W / "runs_admit"
READS = OUT / "pick_reads.csv"


def job_key(j: dict) -> str:
    fam = f"c1-{j['root']}-tf{j['tf']}" if j.get("c1") else f"{j['family']}-{j['root']}-tf{j['tf']}"
    return "-".join(x for x in (fam, j["sess"], j["period"], "stress" if j.get("stress") else "",
                                "shift" if j.get("shift") else "", f"c2s{j['c2_seed']}" if j.get("c2_seed") else "") if x)


def job_grid(j: dict) -> tuple:
    """(grid, cls, features): the unit's WHOLE registered grid (or the named cells) as the ONE-session instance run_menus used."""
    if j.get("c1"):
        grid, cls, feats = RM.c1_grid(j["root"], j["tf"]), None, None
    else:
        grid = F.unit_grid(j["family"], j["root"], j["tf"])
        cls = F.REGISTRY[j["family"]][0]
        feats = F.features_for(j["family"], c2_seed=j.get("c2_seed")) if j.get("c2_seed") else F.features_for(j["family"])
        if j.get("shift"):
            grid = RM.shift_grid(grid)
    if j.get("cells") is not None:
        keep = set(j["cells"])
        grid = [c for c in grid if c["id"] in keep or c["id"].split("_", 1)[-1] in keep and j.get("shift")]
    timed = cls is not None and RM.is_time_fired(cls)
    for c in grid:
        k, p = c["spec"]
        c["spec"] = (k, {**p, "hold_to": "day"} if timed else {**p, "sess": j["sess"], "hold_to": "day"})
    return grid, cls, feats, timed


def run_job(j: dict, days=None) -> list:
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
        if j.get("c1"):
            key = f"c1-{j['root']}-tf{j['tf']}"
        else:
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
    RA.mkdir(exist_ok=True)
    for j in jobs:
        key = job_key(j)
        if (RA / key / "run.json").exists():
            print("skip", key, flush=True)
            continue
        if j["period"] == "pick":
            new = not READS.exists()
            with READS.open("a", newline="") as fh:
                w = csv.writer(fh)
                if new:
                    w.writerow(["utc", "key", "family", "root", "tf", "sess", "what", "why"])
                w.writerow([dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), key, j.get("family", "random"), j["root"], j["tf"],
                            j["sess"], "stress" if j.get("stress") else ("c1 control" if j.get("c1") else "whole menu"), j.get("why", "")])
        t0 = time.monotonic()
        grid, res = run_job(j)
        errs = sum(r["skipped_by_error"] for r in res)
        if errs:
            print("ERROR", key, "sessions dropped by a strategy error; no store", flush=True)
            continue
        meta = {"family": j.get("family", "random"), "tf": str(j["tf"]), "stage": "null_stress" if j.get("stress") else "null_pick",
                "period": j["period"], "sess_instance": j["sess"], "stress": bool(j.get("stress")), "hold_to": "day",
                "control": "c1" if j.get("c1") else ("stress" if j.get("stress") else "pick")}
        LB.write_unit(key, meta, grid, res, RA)
        LB.ledger_add(meta["stage"], key, "null", cells=len(grid), family=meta["family"], root=j["root"], tf=str(j["tf"]), period=j["period"],
                      control=meta["control"], trades=sum(len(r["trades"]) for r in res), elapsed_s=res[0]["elapsed_s"],
                      note=f"admit: session {j['sess']} only")
        print(f"done {key}: {len(grid)} cells, {sum(len(r['trades']) for r in res)} trades, wall {time.monotonic() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    mode, path = sys.argv[1], sys.argv[2]
    jobs = json.loads(Path(path).read_text())
    if mode == "check":
        sys.exit(1 if check(jobs) else 0)
    run(jobs)
