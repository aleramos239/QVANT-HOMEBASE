#!/usr/bin/env python3
"""Stage A screen runner of the NQ Level-2 pilot (SPEC.md "Stage A screen -- pre-registered defaults").

THE SCREEN = for every family of families.REGISTRY x every tf of its class's SCREEN_TFS:
    1 real run          l2sim.run(cls, registered defaults + tf, sess=all, every in-sample session 2021-09-22..2024-12-31,
                        1 NQ, the tester fill law, features=l2sim.L2Features(cls.FEATURES))
    2 C2 null runs      the same call with features=score.C2Features(cls.FEATURES, seed=1 | 2) (feature-shuffle null)
Each run is written as a bundle runs/<key>/ (trades.json + run.json, l2sim.write_bundle: score.py reads the directory) and
appended as ONE row to ledger.csv (stage, key, family, tf, inputs_json, control, seed, trades, net, elapsed_s, finished_utc).
keys: '<family>-tf<tf>' (real), '<family>-tf<tf>-c2s<seed>' (null), '<family>-tf<tf>-stress' (stress).

IDEMPOTENT: a key that already has a ledger row of its stage is skipped. A real run that dropped sessions (strategy error) is
NOT a result: no bundle, a 'screen_error' row (trades / net empty), and its key stays pending until the family is fixed.
THE CAP (SPEC, hard): screening runs <= 400 in total = ledger rows of stage 'screen' + 'gate' + 'screen_error' (each real run 1,
each C2 seed 1, each gate 1). A batch that would pass the cap is REFUSED as a whole before anything runs (logged to
out/screen.log), and `append_row` refuses the single row that would pass it. Gate authors record their runs with
`record_gate(...)` so the same ledger counts them.
COMPUTE WINDOWS: l2sim.wait_compute_window() before every run (and inside l2sim before every session-day). <= 8 workers.
STRESS (`screen.py stress`): the real runs again under l2sim.STRESS (2 ticks, 250 ms), stage 'stress', own keys. It is NOT part
of the screen, never run by `run`, and not counted in the cap (no new config: an execution re-run of a screened one).

    python screen.py status                              counts: registry, plan, done, pending, cap
    python screen.py plan                                the job list (nothing runs)
    python screen.py run    [--only fam[,fam]] [--workers 8] [--max-runs N]
    python screen.py stress [--only fam[,fam]] [--workers 8]
    python screen.py smoke <family> [--tf 5] [--days 10] [--workers 1]
        BUG CHECK for family authors on <= 10 fixed in-sample days: prints counts only (sessions, dropped sessions and their
        error, trades, sides, sessions of the day, entry kinds, both-side evidence, worker parity, C2 null trade count).
        It never prints or stores P&L, exit reasons or win rates, writes no bundle and no ledger row.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import datetime as dt
import fcntl
import json
import sys
import time
from collections import Counter
from pathlib import Path

L = Path(__file__).resolve().parent
if str(L) not in sys.path:
    sys.path.insert(0, str(L))

import l2sim  # noqa: E402

RUNS = L / "runs"
LEDGER = L / "ledger.csv"
LOG = L / "out" / "screen.log"
CAP = 400                                            # SPEC: screening runs <= 400, never relaxed
COLS = ("stage", "key", "family", "tf", "inputs_json", "control", "seed", "trades", "net", "elapsed_s", "finished_utc")
COUNTED = ("screen", "gate", "screen_error")         # the stages that count against the cap
C2_SEEDS = (1, 2)
SMOKE_DAYS = ("2021-10-05", "2022-03-15", "2022-06-13", "2022-11-25", "2023-03-22", "2023-08-09", "2023-12-13", "2024-04-10",
              "2024-07-03", "2024-11-06")          # fixed: early sample (20-day depth still NaN), roll day and roll + 1 (book
#                                                    masked), two half days, an FOMC day, plain days


class CapExceeded(RuntimeError):
    """The run / batch would take the screening-run count past the SPEC cap."""


class RegistryBroken(RuntimeError):
    """families.ERRORS is not empty: a family module failed to import or breaks the contract."""


def _log(msg: str, path=None) -> None:
    line = f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    p = Path(path) if path is not None else LOG
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(line + "\n")


# ------------------------------------------------------------------ ledger

@contextlib.contextmanager
def _locked(path: Path):
    """Exclusive lock for a read-check-append on the ledger (several agents append: screen runner, gate runner)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_name(path.name + ".lock"), "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


def read_ledger(path=None) -> list:
    p = Path(path) if path is not None else LEDGER
    if not p.exists() or p.stat().st_size == 0:
        return []
    with p.open(newline="") as fh:
        return list(csv.DictReader(fh))


def cap_used(rows: list) -> int:
    return sum(1 for r in rows if r.get("stage") in COUNTED)


def append_row(row: dict, path=None, cap: int = CAP) -> dict:
    """Append one run to the ledger under a lock. Refuses (CapExceeded) a counted row past the cap, and a second row for a
    (stage, key) that is already there. Missing columns are written empty; finished_utc defaults to now."""
    p = Path(path) if path is not None else LEDGER
    row = {**{c: "" for c in COLS}, **row}
    unknown = sorted(set(row) - set(COLS))
    if unknown:
        raise ValueError(f"unknown ledger columns {unknown}; the columns are {COLS}")
    if not row["stage"] or not row["key"]:
        raise ValueError("a ledger row needs a stage and a key")
    row["finished_utc"] = row["finished_utc"] or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with _locked(p):
        rows = read_ledger(p)
        if row["stage"] in COUNTED and cap_used(rows) + 1 > cap:
            raise CapExceeded(f"screening-run cap reached: {cap_used(rows)} of {cap} used; {row['key']} refused")
        if not row["stage"].endswith("_error") and any(r["stage"] == row["stage"] and r["key"] == row["key"] for r in rows):
            raise ValueError(f"ledger already holds a '{row['stage']}' row for {row['key']}")
        new = not p.exists() or p.stat().st_size == 0
        with p.open("a", newline="") as fh:
            w = csv.DictWriter(fh, COLS)
            if new:
                w.writeheader()
            w.writerow(row)
    return row


def record_gate(key: str, family: str, inputs: dict, trades: int, net: float, elapsed_s: float = 0.0, tf: str = "",
                control: str = "", seed="", path=None, cap: int = CAP) -> dict:
    """For the gate runner (G1-G3 on the approved picks; SPEC: each gate counts 1 screening run, its C2 nulls 1 each):
    one 'gate' row in the same ledger, under the same cap."""
    return append_row({"stage": "gate", "key": key, "family": family, "tf": tf, "inputs_json": json.dumps(inputs, sort_keys=True),
                       "control": control, "seed": seed, "trades": int(trades), "net": round(float(net), 2),
                       "elapsed_s": round(float(elapsed_s), 2)}, path, cap)


# ------------------------------------------------------------------ jobs

def registry(strict: bool = True) -> dict:
    import families
    if strict and families.ERRORS:
        raise RegistryBroken("families registry has errors (fix them first):\n  "
                             + "\n  ".join(f"{k}: {v}" for k, v in families.ERRORS.items()))
    return families.REGISTRY


def job_key(family: str, tf: str, control: str = "", seed="", stage: str = "screen") -> str:
    return f"{family}-tf{tf}" + (f"-{control}s{seed}" if control else "") + ("-stress" if stage == "stress" else "")


def jobs(reg: dict | None = None, stage: str = "screen", only=None) -> list:
    """The job list, in run order: per family (by name) x tf: the real run, then the C2 nulls (not for 'stress')."""
    reg = registry() if reg is None else reg
    out = []
    for fam in sorted(reg):
        if only and fam not in only:
            continue
        cls, inputs = reg[fam][0], reg[fam][1]
        for tf in cls.SCREEN_TFS:
            params = {**inputs, "tf": str(tf), "sess": "all"}          # = families.screen_inputs(fam, tf)
            variants = [("", "")] + ([] if stage == "stress" else [("c2", s) for s in C2_SEEDS])
            for control, seed in variants:
                out.append({"stage": stage, "key": job_key(fam, tf, control, seed, stage), "family": fam, "tf": str(tf),
                            "inputs": params, "control": control, "seed": seed})
    if only:
        missing = sorted(set(only) - set(reg))
        if missing:
            raise KeyError(f"not registered: {missing}; registered: {sorted(reg)}")
    return out


def done_keys(rows: list, stage: str) -> set:
    return {r["key"] for r in rows if r["stage"] == stage}


def _features(cls, control: str, seed):
    if not control:
        return l2sim.L2Features(cls.FEATURES)
    if control != "c2":
        raise ValueError(f"unknown control {control!r}")
    import score
    return score.C2Features(cls.FEATURES, seed=int(seed))


def run_job(job: dict, reg: dict, *, workers: int = l2sim.MAX_WORKERS, days=None, runs_dir=None, ledger=None, cap: int = CAP,
            log=None) -> dict:
    """Run ONE job and record it. -> the ledger row. `days` (a subset of sessions) is for tests only and is refused for the
    stages that count ('screen' / 'gate'): a screen run is every in-sample session."""
    stage = job["stage"]
    if days is not None and stage in COUNTED + ("stress",):
        raise ValueError("a screen / stress run covers every in-sample session: `days` is for test stages only")
    cls, _, both, notes = reg[job["family"]]
    workers = max(1, min(int(workers), l2sim.MAX_WORKERS))
    kw = dict(getattr(cls, "SCREEN_RUN", {}))
    if stage == "stress":
        kw.update(l2sim.STRESS)
    if stage in COUNTED:                                 # never start a run the ledger could not take
        used = cap_used(read_ledger(ledger))
        if used + 1 > cap:
            raise CapExceeded(f"screening-run cap reached: {used} of {cap} used; {job['key']} refused")
    l2sim.wait_compute_window()
    res = l2sim.run(cls, job["inputs"], features=_features(cls, job["control"], job["seed"]), workers=workers,
                    **({} if days is None else {"days": list(days)}), **kw)
    base = {"stage": stage, "key": job["key"], "family": job["family"], "tf": job["tf"],
            "inputs_json": json.dumps(res["meta"]["inputs"], sort_keys=True), "control": job["control"], "seed": job["seed"],
            "elapsed_s": res["elapsed_s"]}
    if res["skipped_by_error"]:
        err = next(n["reason"] for n in res["no_trade"] if n["reason"].startswith(l2sim.ERROR_PREFIX))
        _log(f"ERROR {job['key']}: {res['skipped_by_error']} of {res['sessions']} sessions dropped ({err}); no bundle written", log)
        return append_row({**base, "stage": stage + "_error"}, ledger, cap)
    res["meta"] = {**res["meta"], "screen": {"stage": stage, "family": job["family"], "tf": job["tf"], "control": job["control"],
                                             "seed": job["seed"], "both_sides_declared": both, "notes": notes,
                                             "features": list(cls.FEATURES), "run_kw": kw}}
    l2sim.write_bundle(res, (Path(runs_dir) if runs_dir is not None else RUNS) / job["key"], run_id=job["key"])
    return append_row({**base, "trades": len(res["trades"]), "net": round(sum(t["net"] for t in res["trades"]), 2)}, ledger, cap)


def run_all(stage: str = "screen", *, only=None, workers: int = l2sim.MAX_WORKERS, max_runs: int | None = None, reg: dict | None = None,
            days=None, runs_dir=None, ledger=None, cap: int = CAP, log=None) -> dict:
    """Run every pending job of the stage. -> {"ran": [...keys], "skipped": [...already done], "errors": [...], "refused": n}.
    The whole batch is refused (nothing runs, CapExceeded) when used + pending would pass the cap."""
    reg = registry() if reg is None else reg
    plan = jobs(reg, stage, only)
    done = done_keys(read_ledger(ledger), stage)
    todo = [j for j in plan if j["key"] not in done]
    if max_runs is not None:
        todo = todo[:max(0, int(max_runs))]
    out = {"ran": [], "skipped": [j["key"] for j in plan if j["key"] in done], "errors": [], "refused": 0}
    if stage in COUNTED:
        used = cap_used(read_ledger(ledger))
        if used + len(todo) > cap:
            out["refused"] = len(todo)
            _log(f"REFUSED: {len(todo)} pending {stage} runs + {used} used would pass the cap of {cap} screening runs; nothing was run",
                 log)
            raise CapExceeded(f"{used} used + {len(todo)} pending > cap {cap}")
    _log(f"{stage}: {len(plan)} jobs planned, {len(out['skipped'])} done, {len(todo)} to run, workers {workers}", log)
    for j in todo:
        t0 = time.monotonic()
        row = run_job(j, reg, workers=workers, days=days, runs_dir=runs_dir, ledger=ledger, cap=cap, log=log)
        (out["errors"] if row["stage"].endswith("_error") else out["ran"]).append(j["key"])
        _log(f"{row['stage']} {j['key']}: {row['trades'] or 0} trades, {row['elapsed_s']} s (wall {time.monotonic() - t0:.0f} s)", log)
    return out


# ------------------------------------------------------------------ status / smoke

def status(ledger=None) -> dict:
    import families
    rows = read_ledger(ledger)
    plan = jobs(families.REGISTRY, "screen")
    done = done_keys(rows, "screen")
    by = Counter((r["stage"], r["control"] or "real") for r in rows)
    return {"families": len(families.REGISTRY), "registry_errors": dict(families.ERRORS),
            "family_tfs": {f: list(e[0].SCREEN_TFS) for f, e in sorted(families.REGISTRY.items())},
            "planned": len(plan), "done": sum(j["key"] in done for j in plan),
            "pending": [j["key"] for j in plan if j["key"] not in done],
            "ledger_rows": len(rows), "by_stage_control": {f"{a}/{b}": n for (a, b), n in sorted(by.items())},
            "cap": CAP, "cap_used": cap_used(rows), "cap_left": CAP - cap_used(rows),
            "cap_after_pending": cap_used(rows) + sum(j["key"] not in done for j in plan)}


def smoke(family: str, tf: str | None = None, n_days: int = 10, workers: int = 1, reg: dict | None = None) -> dict:
    """Bug check of ONE family on <= 10 fixed in-sample days (SMOKE_DAYS), <= 2 workers. Returns / prints COUNTS only: no P&L,
    no exit reasons, no win rate; nothing is written. Checks: inputs accepted, no dropped session, no look-ahead abort,
    the declared both_sides against the simulator's evidence, 1-worker == 2-worker trades, the C2 null runs."""
    reg = registry(strict=False) if reg is None else reg
    if family not in reg:
        import families
        raise KeyError(f"{family!r} is not registered; registered {sorted(reg)}; errors {families.ERRORS}")
    cls, inputs, both, _ = reg[family]
    tf = str(tf or cls.SCREEN_TFS[0])
    days = list(SMOKE_DAYS[:max(1, min(int(n_days), len(SMOKE_DAYS)))])
    workers = max(1, min(int(workers), 2))
    params = {**inputs, "tf": tf, "sess": "all"}
    kw = dict(getattr(cls, "SCREEN_RUN", {}))
    l2sim.wait_compute_window()
    res = l2sim.run(cls, params, features=l2sim.L2Features(cls.FEATURES), days=days, workers=workers, **kw)
    tr = res["trades"]
    out = {"family": family, "tf": tf, "days": len(days), "sessions": res["sessions"], "used": res["used"],
           "skipped_by_error": res["skipped_by_error"],
           "errors": [n for n in res["no_trade"] if n["reason"].startswith(l2sim.ERROR_PREFIX)][:3],
           "trades": len(tr), "long": sum(t["side"] == "long" for t in tr), "short": sum(t["side"] == "short" for t in tr),
           "by_session": dict(Counter(l2sim.session_of(t["entry_ms"]) or "none" for t in tr)),
           "by_day": dict(Counter(t["date"] for t in tr)),
           "entry_kind": {"market": sum(t["order_price"] is None for t in tr), "resting": sum(t["order_price"] is not None for t in tr)},
           "both_sides_declared": both, "both_sides_sessions": res["both_sides_sessions"],
           "both_sides_ok": bool(both or res["both_sides_sessions"] == 0), "exec_guard": res["meta"]["exec_guard"]}
    other = l2sim.run(cls, params, features=l2sim.L2Features(cls.FEATURES), days=days, workers=3 - workers, **kw)
    out["worker_parity"] = other["trades"] == tr
    import score
    null = l2sim.run(cls, params, features=score.C2Features(cls.FEATURES, seed=1), days=days, workers=workers, **kw)
    out["c2_null"] = {"trades": len(null["trades"]), "skipped_by_error": null["skipped_by_error"],
                      "same_trades_as_real": [{k: t[k] for k in ("entry_ms", "side")} for t in null["trades"]]
                      == [{k: t[k] for k in ("entry_ms", "side")} for t in tr]}
    out["ok"] = bool(out["skipped_by_error"] == 0 and out["both_sides_ok"] and out["worker_parity"]
                     and null["skipped_by_error"] == 0)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="screen.py", description="Stage A screen runner (see the module docstring)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("plan")
    for name in ("run", "stress"):
        r = sub.add_parser(name)
        r.add_argument("--only", default="", help="comma list of family names")
        r.add_argument("--workers", type=int, default=l2sim.MAX_WORKERS)
        r.add_argument("--max-runs", type=int, default=None)
    s = sub.add_parser("smoke")
    s.add_argument("family")
    s.add_argument("--tf", default=None)
    s.add_argument("--days", type=int, default=len(SMOKE_DAYS))
    s.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    if a.cmd == "status":
        st = status()
        print(f"families {st['families']}  registry errors {len(st['registry_errors'])}")
        for k, v in st["registry_errors"].items():
            print(f"  ERROR {k}: {v}")
        for f, tfs in st["family_tfs"].items():
            print(f"  {f}: tf {','.join(tfs)}")
        print(f"screen jobs planned {st['planned']}  done {st['done']}  pending {len(st['pending'])}")
        print(f"ledger rows {st['ledger_rows']}  " + "  ".join(f"{k} {v}" for k, v in st["by_stage_control"].items()))
        print(f"cap {st['cap_used']} of {st['cap']} used, {st['cap_left']} left; after the pending runs: {st['cap_after_pending']}"
              + ("  ** OVER THE CAP: run would be refused **" if st["cap_after_pending"] > st["cap"] else ""))
        return 0
    if a.cmd == "plan":
        for j in jobs(registry(), "screen"):
            print(j["key"], json.dumps(j["inputs"], sort_keys=True))
        return 0
    if a.cmd == "smoke":
        o = smoke(a.family, a.tf, a.days, a.workers)
        print(json.dumps(o, indent=1))
        return 0 if o["ok"] else 1
    only = [x for x in a.only.split(",") if x] or None
    try:
        out = run_all("screen" if a.cmd == "run" else "stress", only=only, workers=a.workers, max_runs=a.max_runs)
    except (CapExceeded, RegistryBroken) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in out.items()}))
    return 1 if out["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
