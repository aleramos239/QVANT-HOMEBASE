"""CHECK-year (2025) runner + the F2 extra control seeds (EDGE_SPEC "PERIODS AMENDED" and "ADMISSION v2 -- CHECKER FIXES" F2).
A copy of out/v2/run_v2.py with the same job format: one tape pass per job, the unit's session instance only (hold_to = day).

  python out/check2025/run_check.py check <jobs.json>   identity of this runner with the stores on disk, counts only: 10 BUILD days
                                                        against the BUILD store and 6 days of 2024 against the 2024 store
  python out/check2025/run_check.py run   <jobs.json>   jobs: [{family, root, tf, sess, period, stress?, oco?, cells?, c1?, shift?,
                                                                seeds?, unit, why}]

period: 'build' | 'pick' | 'check'. 'check' = 2025-01-01..2025-12-31 through l2sim's CHECK switch (allow_check=True); nothing here
can reach 2026 (l2sim raises HoldoutSealed for a 2026 date under the check flag, and there is no other flag in this file).
STORES -- key = out/v2/run_v2.job_key: <family>-<ROOT>-tf<tf>-<sess>-<period>[-stress][-shift]  /  c1-<ROOT>-tf<tf>-<sess>-<period>
  period check, no `seeds`   -> runs_check2025/<key>           the 2025 menu, its stress, its 2-seed control (cells s1_<id>, s2_<id>)
  `seeds` given (3 .. 10)    -> runs_seeds/<key>-s3to10        F2: the SAME control with the extra seeds (cells s3_<id> .. s10_<id>),
                                                               on build / pick / check; run.json "extends" = the 2-seed store it adds to
  (a build / pick job without `seeds` is out/v2/run_v2.py's and is refused here)
Stress = l2sim.STRESS (2 ticks + 250 ms) + Costs(oco_cancel_ms = 100) when the job says oco (two-sided brackets, v2 part C).
LEDGER (cap 80,000 passed as `caps`, as run_v2): the 2025 menu = kind grid, stage v2_check; its stress = grid, v2_check_stress;
a control = kind null (not capped): null_v2_check (2 seeds on 2025), null_f2_<period> (seeds 3 .. 10).
READ LOGS, appended BEFORE the pass: every 2025 store -> out/check2025/reads.csv; a 2024 store -> out/v2/pick_reads.csv too.
SANITY of every store -> out/check2025/sanity.csv. Counts only: no net, win rate or profit factor is read or printed here."""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
import families as F  # noqa: E402
import l2sim as S  # noqa: E402
import library as LB  # noqa: E402
import run_menus as RM  # noqa: E402

OUT = W / "out" / "check2025"
RC = W / "runs_check2025"                         # where judge.py looks for the 2025 stores (its PERIODS table)
RS = W / "runs_seeds"                             # F2: seeds 3 .. 10 of a control, any period
READS = OUT / "reads.csv"
PICK_READS = W / "out" / "v2" / "pick_reads.csv"
SANITY = OUT / "sanity.csv"
CAPS = {"runs": 2000, "cells": 80000, "wfs": 40}  # v2 part D: candidate cap 80,000
OCO_MS = 100
PICK_DIRS = [W / "runs_v2", W / "runs_admit", W / "runs_admit_r1", W / "runs_deepen", W / "runs_events"]
PICK_DAYS = ("2024-01-09", "2024-03-15", "2024-06-12", "2024-09-18", "2024-11-29", "2024-12-18")
SANITY_COLS = ("utc", "store", "unit", "period", "kind", "seeds", "cells", "sessions", "used_min", "used_max", "skipped_sessions",
               "skipped_by_error", "outside_session", "cells_no_trade", "trades", "trades_outside_period", "after_period_end",
               "eve_skipped", "first_trade_date", "last_trade_date", "wall_s")


def job_key(j: dict) -> str:
    fam = f"c1-{j['root']}-tf{j['tf']}" if j.get("c1") else f"{j['family']}-{j['root']}-tf{j['tf']}"
    sd = sorted(int(x) for x in j["seeds"]) if j.get("seeds") else None
    return "-".join(x for x in (fam, j["sess"], j["period"], "stress" if j.get("stress") else "", "shift" if j.get("shift") else "",
                                f"s{sd[0]}to{sd[-1]}" if sd else "") if x)


def job_dir(j: dict) -> Path:
    if j.get("seeds"):
        return RS
    if j["period"] == "check":
        return RC
    raise ValueError(f"{job_key(j)}: a build / pick job without `seeds` belongs to out/v2/run_v2.py")


def job_kind(j: dict) -> str:
    return "control" if (j.get("c1") or j.get("shift")) else ("stress" if j.get("stress") else "base")


def seeded(fn, seeds, *a):
    """run_menus.shift_grid / c1_grid with other seeds: the same code, NULL_SEEDS swapped for the call."""
    old = RM.NULL_SEEDS
    RM.NULL_SEEDS = tuple(int(s) for s in seeds)
    try:
        return fn(*a)
    finally:
        RM.NULL_SEEDS = old


def job_grid(j: dict) -> tuple:
    seeds = tuple(j.get("seeds") or RM.NULL_SEEDS)
    if j.get("seeds") and not (j.get("c1") or j.get("shift")):
        raise ValueError("`seeds` is for a control job (c1 / shift)")
    if j.get("c1"):
        grid, cls = seeded(RM.c1_grid, seeds, j["root"], j["tf"]), None
    else:
        if F.features_for(j["family"]) is not None:
            raise ValueError(f"{j['family']}: a Level-2 family is not run here (a CHECK run takes no features)")
        grid = F.unit_grid(j["family"], j["root"], j["tf"])
        cls = F.REGISTRY[j["family"]][0]
        if j.get("shift"):
            grid = seeded(RM.shift_grid, seeds, grid)
    if j.get("cells") is not None:
        keep = set(j["cells"])
        grid = [c for c in grid if c["id"] in keep or (j.get("shift") and c["id"].split("_", 1)[-1] in keep)]
    timed = cls is not None and RM.is_time_fired(cls)
    for c in grid:
        k, p = c["spec"]
        c["spec"] = (k, {**p, "hold_to": "day"} if timed else {**p, "sess": j["sess"], "hold_to": "day"})
    return grid, cls, timed


def run_job(j: dict, days=None, workers: int | None = None) -> tuple:
    grid, cls, timed = job_grid(j)
    kw = dict(S.STRESS) if j.get("stress") else {}
    if j.get("stress") and j.get("oco"):
        kw["costs"] = S.Costs(oco_cancel_ms=OCO_MS)
    if cls is not None:
        kw.update(getattr(cls, "SCREEN_RUN", {}))
    specs = [c["spec"] for c in grid]
    S.wait_compute_window()
    if days is None:
        if j["period"] == "check":
            kw["allow_check"] = True                 # the ONLY seal switch this file ever passes: 2025, never 2026
        res = S.run_many(specs, period=j["period"], root=j["root"], workers=RM.auto_workers(workers), **kw)
    else:
        res = S.run_many(specs, days=list(days), root=j["root"], workers=RM.auto_workers(workers or 4), **kw)
    outside = 0
    if not timed:
        for r in res:
            keep = [t for t in r["trades"] if S.session_of(t["entry_ms"]) == j["sess"]]
            outside += len(r["trades"]) - len(keep)
            r["trades"] = keep
    else:
        outside = sum(S.session_of(t["entry_ms"]) is None for r in res for t in r["trades"])
    return grid, res, outside


def sanity(j: dict, res: list, outside: int) -> dict:
    a, b = S.period(j["period"])
    end_ms = S.et_ns(b + dt.timedelta(days=1), "00:00") // 1_000_000
    dates = [t["date"] for r in res for t in r["trades"]]
    return {"sessions": res[0]["sessions"], "used_min": min(r["used"] for r in res), "used_max": max(r["used"] for r in res),
            "skipped_sessions": max(len(r["skipped"]) for r in res), "skipped_by_error": sum(r["skipped_by_error"] for r in res),
            "outside_session": outside, "cells_no_trade": sum(not r["trades"] for r in res), "trades": len(dates),
            "trades_outside_period": sum(not (a.isoformat() <= d <= b.isoformat()) for d in dates),
            "after_period_end": sum(t["entry_ms"] >= end_ms or t["exit_ms"] >= end_ms for r in res for t in r["trades"]),
            "eve_skipped": max(len(r.get("eve_skipped", [])) for r in res),
            "first_trade_date": min(dates) if dates else "", "last_trade_date": max(dates) if dates else ""}


def _append(path: Path, header, row) -> None:
    new = not path.exists() or path.stat().st_size == 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(header)
        w.writerow(row)


def stage_of(j: dict) -> str:
    if j.get("seeds"):
        return f"null_f2_{j['period']}"
    return ("null_" if job_kind(j) == "control" else "") + "v2_check" + ("_stress" if j.get("stress") else "")


def seeds_txt(j: dict) -> str:
    if job_kind(j) != "control":
        return ""
    s = sorted(int(x) for x in (j.get("seeds") or RM.NULL_SEEDS))
    return f"{s[0]}-{s[-1]}"


def extends(j: dict) -> str:
    """The 2-seed store a `seeds` store adds to (BUILD: the unit's all-session store in runs/; a year: <key> of that year)."""
    if j["period"] == "build":
        return "runs/" + (f"c1-{j['root']}-tf{j['tf']}" if j.get("c1") else f"{j['family']}-{j['root']}-tf{j['tf']}-shift")
    key = job_key({k: v for k, v in j.items() if k != "seeds"})
    if j["period"] == "check":
        return f"runs_check2025/{key}"
    return next((f"{d.name}/{key}" for d in PICK_DIRS if (d / key / "run.json").exists()), f"runs_v2/{key}")


def book(j: dict, key: str, stage: str, cells: int, trades: int, elapsed, control: str) -> None:
    if LB.ledger_has(key, stage):
        return
    kind = "grid" if job_kind(j) != "control" else "null"
    where = job_dir(j).name
    LB.ledger_add(stage, key, kind, cells=cells, caps=CAPS, family=j.get("family", "random"), root=j["root"], tf=str(j["tf"]),
                  period=j["period"], control=control, seed=seeds_txt(j), trades=trades, elapsed_s=elapsed,
                  note=f"{where}/{key}: session {j['sess']} only" + (f"; oco_cancel_ms {OCO_MS}" if (j.get("stress") and j.get("oco")) else "")
                  + ("; F2 extra seeds of " + extends(j) if j.get("seeds") else ""))


def run(jobs: list) -> None:
    for j in jobs:
        key, d, kind, stage = job_key(j), job_dir(j), job_kind(j), stage_of(j)
        control = "c1" if j.get("c1") else ("shift" if j.get("shift") else ("stress" if j.get("stress") else j["period"]))
        if (d / key / "run.json").exists():
            m = json.loads((d / key / "run.json").read_text())
            book(j, key, stage, len(m["cells"]), sum(c["trades"] for c in m["cells"]), m.get("elapsed_s"), control)
            print("skip", f"{d.name}/{key}", flush=True)
            continue
        n_cells = len(job_grid(j)[0])
        if kind != "control":
            LB.ledger_check(cells=n_cells, caps=CAPS)            # refused as a whole BEFORE the pass if it would pass the cap
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        what = ("stress " if j.get("stress") else "") + ("c1 control" if j.get("c1") else (
            "random-minute / random-direction control" if j.get("shift") else "whole menu")) + (f", seeds {seeds_txt(j)}" if kind == "control" else "")
        if j["period"] == "check":
            _append(READS, ["utc", "unit", "store", "cells", "period", "kind", "seeds", "why"],
                    [now, j.get("unit", ""), f"{d.name}/{key}", n_cells, "check (2025)", kind, seeds_txt(j), j.get("why", "")])
        elif j["period"] == "pick":
            _append(PICK_READS, ["utc", "key", "family", "root", "tf", "sess", "what", "cells", "why"],
                    [now, f"{d.name}/{key}", j.get("family", "random"), j["root"], j["tf"], j["sess"], what, n_cells, j.get("why", "")])
        t0 = time.monotonic()
        grid, res, outside = run_job(j)
        sn = sanity(j, res, outside)
        if sn["skipped_by_error"]:
            print("ERROR", key, "sessions dropped by a strategy error; no store", flush=True)
            continue
        if sn["trades_outside_period"] or sn["after_period_end"]:
            print("ERROR", key, "a trade is dated outside the period; no store", flush=True)
            continue
        wall = round(time.monotonic() - t0)
        meta = {"family": j.get("family", "random"), "tf": str(j["tf"]), "stage": stage, "period": j["period"], "sess_instance": j["sess"],
                "stress": bool(j.get("stress")), "oco_cancel_ms": OCO_MS if (j.get("stress") and j.get("oco")) else 0, "hold_to": "day",
                "control": control, "unit": j.get("unit"), "sanity": sn}
        if kind == "control":
            meta["seeds"] = sorted(int(x) for x in (j.get("seeds") or RM.NULL_SEEDS))
        if j.get("seeds"):
            meta["extends"] = extends(j)
        d.mkdir(exist_ok=True)
        LB.write_unit(key, meta, grid, res, d)
        book(j, key, stage, len(grid), sn["trades"], res[0]["elapsed_s"], control)
        _append(SANITY, SANITY_COLS, [now, f"{d.name}/{key}", j.get("unit", ""), j["period"], kind, seeds_txt(j), len(grid)]
                + [sn[c] for c in SANITY_COLS[7:-1]] + [wall])
        print(f"done {d.name}/{key}: {len(grid)} cells, {sn['trades']} trades, sessions {sn['sessions']}, used {sn['used_min']}-{sn['used_max']}, "
              f"errors {sn['skipped_by_error']}, outside session {sn['outside_session']}, cells without a trade {sn['cells_no_trade']}, "
              f"wall {wall} s", flush=True)


# ---------------------------------------------------------------- identity with the stores on disk (counts only)

def _same(grid, res, u, days, sess, by_sess: bool) -> tuple:
    ords = np.array([dt.date.fromisoformat(d).toordinal() for d in days])
    idx = {c["id"]: i for i, c in enumerate(u["meta"]["cells"])}
    n = diff = cells = 0
    for c, r in zip(grid, res):
        if c["id"] not in idx:
            continue
        x = LB.unit_cell(u, idx[c["id"]])
        m = np.isin(x["date"], ords)
        if by_sess:
            m &= x["sess"] == LB.SESS_CODE[sess]
        mine = sorted((t["entry_ms"], round(t["net"], 2)) for t in r["trades"])
        ref = sorted(zip(x["entry_ms"][m].tolist(), np.round(x["net"][m], 2).tolist()))
        cells += 1
        n += len(ref)
        diff += mine != ref
    return cells, n, diff


def check(jobs: list) -> int:
    bad, seen = 0, set()
    for j in jobs:
        j2 = {k: v for k, v in j.items() if k != "seeds"}          # the code path of the extra seeds, on the seeds the stores hold
        tag = (job_key({**j2, "period": "x"}), bool(j.get("stress")))
        if tag in seen:
            continue
        seen.add(tag)
        bkey = f"c1-{j['root']}-tf{j['tf']}" if j.get("c1") else f"{j['family']}-{j['root']}-tf{j['tf']}" + ("-shift" if j.get("shift") else "")
        if not j.get("stress"):                                    # BUILD: the unit's all-session store
            u = LB.load_unit(bkey)
            have = {d.isoformat() for d in S.sessions(*S.period("build"), j["root"])}
            days = [d for d in RM.SMOKE_DAYS if d in have]
            grid, res, _ = run_job({**j2, "period": "build"}, days=days)
            cells, n, diff = _same(grid, res, u, days, j["sess"], not j.get("shift"))
            bad += diff + (cells == 0)
            print(f"check BUILD runs/{bkey} {j['sess']}: {len(days)} days, {cells} cells, {n} stored trades, cells that differ: {diff}", flush=True)
        if j.get("build_only"):                                    # a pending unit's pool: 2024 stays closed for it
            continue
        pkey = job_key({**j2, "period": "pick"})
        dirs = [W / "runs_v2"] if j.get("stress") else PICK_DIRS
        pd = next((d for d in dirs if (d / pkey / "run.json").exists()), None)
        if pd is None:
            print(f"check 2024 {pkey}: no 2024 store on disk (nothing to compare)", flush=True)
            continue
        u = LB.load_unit(pkey, pd)
        if j.get("stress") and int(u["meta"].get("oco_cancel_ms") or 0) != (OCO_MS if j.get("oco") else 0):
            print(f"check 2024 {pd.name}/{pkey}: stored with another oco_cancel_ms (not compared)", flush=True)
            continue
        have = {d.isoformat() for d in S.sessions(*S.period("pick"), j["root"])}
        days = [d for d in PICK_DAYS if d in have]
        grid, res, _ = run_job({**j2, "period": "pick"}, days=days)
        cells, n, diff = _same(grid, res, u, days, j["sess"], not j.get("shift"))
        bad += diff + (cells == 0)
        print(f"check 2024 {pd.name}/{pkey}: {len(days)} days, {cells} cells, {n} stored trades, cells that differ: {diff}", flush=True)
    print("IDENTITY", "FAILED" if bad else "OK", flush=True)
    return bad


if __name__ == "__main__":
    mode, path = sys.argv[1], sys.argv[2]
    jobs = json.loads(Path(path).read_text())
    if mode == "check":
        sys.exit(1 if check(jobs) else 0)
    run(jobs)
