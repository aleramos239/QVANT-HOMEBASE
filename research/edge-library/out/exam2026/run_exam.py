"""EXAM (2026) runner of the full out-of-sample (EDGE_SPEC "FULL OUT-OF-SAMPLE FOR THE SAVED STRATEGIES", "RULING BEFORE THE 2025
SCORING"). The same job format and the same grid code as out/check2025/run_check.py (its job_grid / seeded / _same are imported, not
copied): one tape pass per job, the unit's session instance only (hold_to = day).

  python out/exam2026/run_exam.py check <jobs.json>   identity of this runner with the stores on disk, counts only, NO 2026 date:
                                                      10 BUILD days against the BUILD store, 6 days of 2025 against the 2025 store,
                                                      and for a bracket family the 10 BUILD days again WITHOUT the carried evening
                                                      ATR (the EXAM key does not load it for 2026: it must change no trade)
  python out/exam2026/run_exam.py run   <jobs.json>   jobs: [{family, root, tf, sess, period: "exam", stress?, oco?, cells?, c1?,
                                                              shift?, seeds?, unit, why}]

THE SEAL: every job of a list is checked BEFORE anything runs -- period must be "exam" and the job's own family / market / bar size /
session must belong to a unit listed in out/exam2026/allowed.json (members under the rule in force that pass tests (4)-(6) on 2025;
written before the first 2026 run). One job off the list refuses the whole list (Sealed). The dates are 2026-01-01 ..
allowed.json period.end[ROOT] (the last complete session on disk of that market), passed to l2sim.run_many with allow_exam=True --
the only place in this project that passes it.
STORES -> runs_exam2026/<family>-<ROOT>-tf<tf>-<sess>-exam[-stress][-shift]  /  c1-<ROOT>-tf<tf>-<sess>-exam. A control store
holds all 10 seeds (cells s1_<id> .. s10_<id>). Stress = l2sim.STRESS (2 ticks + 250 ms) + Costs(oco_cancel_ms = 100) when the job
says oco (two-sided brackets). LEDGER (cap 80,000 = library.CAPS): menu = kind grid, stage v2_exam; stress = grid, v2_exam_stress;
control = kind null (not capped), null_v2_exam. READ LOG, appended BEFORE the pass: out/exam2026/reads.csv. SANITY of every store ->
out/exam2026/sanity.csv. Counts only: no net, win rate or profit factor is read or printed here."""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

W = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
sys.path.insert(0, str(W / "out" / "check2025"))
import families as F  # noqa: E402
import l2sim as S  # noqa: E402
import library as LB  # noqa: E402
import run_check as RC  # noqa: E402  (job_grid, seeded, _same, _append: the CHECK runner's own code)
import run_menus as RM  # noqa: E402

OUT = W / "out" / "exam2026"
RX = W / "runs_exam2026"                          # where judge.py finds the 2026 stores (their date range lies in 2026)
ALLOWED = OUT / "allowed.json"
READS = OUT / "reads.csv"
SANITY = OUT / "sanity.csv"
START = dt.date(2026, 1, 1)
SEEDS = tuple(range(1, 11))                       # F2: 10 control seeds on every judged period
OCO_MS = RC.OCO_MS
CHECK_DAYS = ("2025-01-14", "2025-03-19", "2025-06-11", "2025-08-20", "2025-10-24", "2025-12-17")
ADDR = re.compile(r"^(?P<family>[A-Za-z0-9_]+)-(?P<root>[A-Z0-9]+)-tf(?P<tf>\d+)-(?P<sess>[a-z]+)$")
SANITY_COLS = RC.SANITY_COLS


class Sealed(PermissionError):
    """A job that is not an EXAM job of an allowed unit: nothing of its list is run."""


def allowed() -> dict:
    if not ALLOWED.exists():
        raise Sealed(f"{ALLOWED} does not exist: no unit may be run on 2026")
    a = json.loads(ALLOWED.read_text())
    menus, pools = set(), set()
    for addr in a["units"]:
        m = ADDR.match(addr.split("@")[0])
        if not m:
            raise Sealed(f"allowed.json: {addr!r} is not <family>-<ROOT>-tf<tf>-<session>[@filter]")
        menus.add((m["family"], m["root"], m["tf"], m["sess"]))
        if not RM.is_time_fired(F.REGISTRY[m["family"]][0]):
            pools.add((m["root"], m["tf"], m["sess"]))             # a bar-based unit's random-entry pool
    return {"menus": menus, "pools": pools, "end": {r: dt.date.fromisoformat(d) for r, d in a["period"]["end"].items()}, "units": a["units"]}


def guard(j: dict, a: dict | None = None) -> None:
    a = a or allowed()
    if j.get("period") != "exam":
        raise Sealed(f"{j.get('unit')}: period {j.get('period')!r} -- this runner runs EXAM jobs only")
    tf = str(j["tf"])
    ok = (j["root"], tf, j["sess"]) in a["pools"] if j.get("c1") else (j.get("family"), j["root"], tf, j["sess"]) in a["menus"]
    if not ok or j["root"] not in a["end"]:
        what = f"c1-{j['root']}-tf{tf}-{j['sess']}" if j.get("c1") else f"{j.get('family')}-{j['root']}-tf{tf}-{j['sess']}"
        raise Sealed(f"{what} is not a unit on out/exam2026/allowed.json: 2026 stays sealed for it")


def job_key(j: dict) -> str:
    fam = f"c1-{j['root']}-tf{j['tf']}" if j.get("c1") else f"{j['family']}-{j['root']}-tf{j['tf']}"
    return "-".join(x for x in (fam, j["sess"], "exam", "stress" if j.get("stress") else "", "shift" if j.get("shift") else "") if x)


def job_kind(j: dict) -> str:
    return RC.job_kind(j)


def with_seeds(j: dict) -> dict:
    """A control job always carries the 10 seeds (one store holds them all)."""
    return {**j, "seeds": list(SEEDS)} if job_kind(j) == "control" else j


def run_kw(j: dict, cls) -> dict:
    kw = dict(S.STRESS) if j.get("stress") else {}
    if j.get("stress") and j.get("oco"):
        kw["costs"] = S.Costs(oco_cancel_ms=OCO_MS)
    if cls is not None:
        kw.update(getattr(cls, "SCREEN_RUN", {}))
    return kw


def keep_session(j: dict, res: list, timed: bool) -> int:
    outside = 0
    if not timed:
        for r in res:
            keep = [t for t in r["trades"] if S.session_of(t["entry_ms"]) == j["sess"]]
            outside += len(r["trades"]) - len(keep)
            r["trades"] = keep
    else:
        outside = sum(S.session_of(t["entry_ms"]) is None for r in res for t in r["trades"])
    return outside


def run_job(j: dict, a: dict, workers: int | None = None) -> tuple:
    guard(j, a)
    grid, cls, timed = RC.job_grid(with_seeds(j))
    S.wait_compute_window()
    res = S.run_many([c["spec"] for c in grid], START, a["end"][j["root"]], root=j["root"], workers=RM.auto_workers(workers),
                     allow_exam=True, **run_kw(j, cls))               # the EXAM key: named dates, allowed unit, this stage only
    return grid, res, keep_session(j, res, timed)


def sanity(j: dict, res: list, outside: int, end: dt.date) -> dict:
    end_ms = S.et_ns(end + dt.timedelta(days=1), "00:00") // 1_000_000
    dates = [t["date"] for r in res for t in r["trades"]]
    return {"sessions": res[0]["sessions"], "used_min": min(r["used"] for r in res), "used_max": max(r["used"] for r in res),
            "skipped_sessions": max(len(r["skipped"]) for r in res), "skipped_by_error": sum(r["skipped_by_error"] for r in res),
            "outside_session": outside, "cells_no_trade": sum(not r["trades"] for r in res), "trades": len(dates),
            "trades_outside_period": sum(not (START.isoformat() <= d <= end.isoformat()) for d in dates),
            "after_period_end": sum(t["entry_ms"] >= end_ms or t["exit_ms"] >= end_ms for r in res for t in r["trades"]),
            "eve_skipped": max(len(r.get("eve_skipped", [])) for r in res),
            "first_trade_date": min(dates) if dates else "", "last_trade_date": max(dates) if dates else ""}


def stage_of(j: dict) -> str:
    return ("null_" if job_kind(j) == "control" else "") + "v2_exam" + ("_stress" if j.get("stress") else "")


def seeds_txt(j: dict) -> str:
    return f"{SEEDS[0]}-{SEEDS[-1]}" if job_kind(j) == "control" else ""


def book(j: dict, key: str, cells: int, trades: int, elapsed, control: str) -> None:
    stage = stage_of(j)
    if LB.ledger_has(key, stage):
        return
    kind = "grid" if job_kind(j) != "control" else "null"
    LB.ledger_add(stage, key, kind, cells=cells, caps=LB.CAPS, family=j.get("family", "random"), root=j["root"], tf=str(j["tf"]),
                  period="exam", control=control, seed=seeds_txt(j), trades=trades, elapsed_s=elapsed,
                  note=f"{RX.name}/{key}: session {j['sess']} only; EXAM 2026, allow_exam=True"
                  + (f"; oco_cancel_ms {OCO_MS}" if (j.get("stress") and j.get("oco")) else ""))


def run(jobs: list) -> None:
    a = allowed()
    for j in jobs:                                  # the whole list is checked first: one job off the list and nothing runs
        guard(j, a)
    for j in jobs:
        key, kind = job_key(j), job_kind(j)
        control = "c1" if j.get("c1") else ("shift" if j.get("shift") else ("stress" if j.get("stress") else "exam"))
        end = a["end"][j["root"]]
        if (RX / key / "run.json").exists():        # ONE read per unit: a store on disk is never run again
            m = json.loads((RX / key / "run.json").read_text())
            book(j, key, len(m["cells"]), sum(c["trades"] for c in m["cells"]), m.get("elapsed_s"), control)
            print("skip", f"{RX.name}/{key}", flush=True)
            continue
        n_cells = len(RC.job_grid(with_seeds(j))[0])
        if kind != "control":
            LB.ledger_check(cells=n_cells, caps=LB.CAPS)             # refused as a whole BEFORE the pass if it would pass the cap
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        RC._append(READS, ["utc", "unit", "store", "cells", "period", "kind", "seeds", "why"],
                   [now, j.get("unit", ""), f"{RX.name}/{key}", n_cells, f"exam (2026-01-01..{end})", kind, seeds_txt(j), j.get("why", "")])
        t0 = time.monotonic()
        grid, res, outside = run_job(j, a)
        sn = sanity(j, res, outside, end)
        if sn["skipped_by_error"]:
            print("ERROR", key, "sessions dropped by a strategy error; no store", flush=True)
            continue
        if sn["trades_outside_period"] or sn["after_period_end"]:
            print("ERROR", key, "a trade is dated outside the period; no store", flush=True)
            continue
        wall = round(time.monotonic() - t0)
        meta = {"family": j.get("family", "random"), "tf": str(j["tf"]), "stage": stage_of(j), "period": "exam", "sess_instance": j["sess"],
                "stress": bool(j.get("stress")), "oco_cancel_ms": OCO_MS if (j.get("stress") and j.get("oco")) else 0, "hold_to": "day",
                "control": control, "unit": j.get("unit"), "sanity": sn, "allow_exam": True}
        if kind == "control":
            meta["seeds"] = list(SEEDS)
        RX.mkdir(exist_ok=True)
        LB.write_unit(key, meta, grid, res, RX)
        book(j, key, len(grid), sn["trades"], res[0]["elapsed_s"], control)
        RC._append(SANITY, SANITY_COLS, [now, f"{RX.name}/{key}", j.get("unit", ""), "exam", kind, seeds_txt(j), len(grid)]
                   + [sn[c] for c in SANITY_COLS[7:-1]] + [wall])
        print(f"done {RX.name}/{key}: {len(grid)} cells, {sn['trades']} trades, sessions {sn['sessions']}, used {sn['used_min']}-{sn['used_max']}, "
              f"errors {sn['skipped_by_error']}, outside session {sn['outside_session']}, cells without a trade {sn['cells_no_trade']}, "
              f"wall {wall} s", flush=True)


# ---------------------------------------------------------------- identity with the stores on disk (counts only; no 2026 date)

def _days_run(j: dict, days: list, **flags) -> tuple:
    grid, cls, timed = RC.job_grid(with_seeds(j))
    res = S.run_many([c["spec"] for c in grid], days=list(days), root=j["root"], workers=RM.auto_workers(4), **run_kw(j, cls), **flags)
    return grid, res, keep_session(j, res, timed), cls


def check(jobs: list) -> int:
    a = allowed()
    for j in jobs:
        guard(j, a)
    bad = 0
    for j in jobs:
        key = job_key(j)
        by_sess = not j.get("shift")
        bkey = f"c1-{j['root']}-tf{j['tf']}" if j.get("c1") else f"{j['family']}-{j['root']}-tf{j['tf']}" + ("-shift" if j.get("shift") else "")
        if not j.get("stress"):                                    # BUILD: the unit's all-session store (seeds 1, 2 of a control)
            u = LB.load_unit(bkey)
            have = {d.isoformat() for d in S.sessions(*S.period("build"), j["root"])}
            days = [d for d in RM.SMOKE_DAYS if d in have]
            grid, res, _, cls = _days_run(j, days)
            cells, n, diff = RC._same(grid, res, u, days, j["sess"], by_sess)
            bad += diff + (cells == 0)
            print(f"check BUILD runs/{bkey} {j['sess']}: {len(days)} days, {cells} cells, {n} stored trades, cells that differ: {diff}", flush=True)
            if cls is not None and getattr(cls, "ATR_CARRY", False):   # what the EXAM key does on 2026: no carried evening ATR
                real = S.load_eve_atr
                S.load_eve_atr = lambda *x, **k: {}
                try:
                    grid, res, _, _ = _days_run(j, days)
                finally:
                    S.load_eve_atr = real
                cells, n, diff = RC._same(grid, res, u, days, j["sess"], by_sess)
                bad += diff + (cells == 0)
                print(f"check BUILD runs/{bkey} {j['sess']} WITHOUT the carried evening ATR: {cells} cells, {n} stored trades, cells that differ: {diff}", flush=True)
        ckey = key.replace("-exam", "-check")                      # 2025: the CHECK store(s) of the same job
        for d_, k_ in ((W / "runs_check2025", ckey), (W / "runs_seeds", ckey + "-s3to10")):
            if not (d_ / k_ / "run.json").exists():
                continue
            u = LB.load_unit(k_, d_)
            if j.get("stress") and int(u["meta"].get("oco_cancel_ms") or 0) != (OCO_MS if j.get("oco") else 0):
                print(f"check 2025 {d_.name}/{k_}: stored with another oco_cancel_ms (not compared)", flush=True)
                continue
            have = {d.isoformat() for d in S.sessions(*S.CHECK, j["root"], allow_check=True)}
            days = [d for d in CHECK_DAYS if d in have]
            grid, res, _, _ = _days_run(j, days, allow_check=True)
            cells, n, diff = RC._same(grid, res, u, days, j["sess"], by_sess)
            bad += diff + (cells == 0)
            print(f"check 2025 {d_.name}/{k_}: {len(days)} days, {cells} cells, {n} stored trades, cells that differ: {diff}", flush=True)
    print("IDENTITY", "FAILED" if bad else "OK", flush=True)
    return bad


if __name__ == "__main__":
    mode, path = sys.argv[1], sys.argv[2]
    jobs = json.loads(Path(path).read_text())
    if mode == "check":
        sys.exit(1 if check(jobs) else 0)
    run(jobs)
