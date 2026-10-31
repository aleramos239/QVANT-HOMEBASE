"""VWAP hunt runner: every line of queue.txt ("run <sheet>" = taught run, then taught wf; "wf <name>" = taught wf only; "rand <name>" = randctl.py run), at most 4 at
once outside desk hours and 2 on weekdays 08:00-16:15 ET; nothing starts 09:15-09:40 ET on weekdays (the engine's no-start window).
Outputs go to logs/ UNREAD (PREREG.md section 1). A job already done (its result file on disk) is skipped, so the runner can restart.

Run: nohup .venv-research/bin/python research/edge-library/out/vwap_hunt_2026-10-20/runq.py &   (progress: progress.log)"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import time
import zoneinfo
from pathlib import Path

HERE = Path(__file__).resolve().parent
EL = HERE.parents[1]
PY = EL.parents[1] / ".venv-research" / "bin" / "python"
ROOT = Path.home() / ".homebase" / "taught"
NY = zoneinfo.ZoneInfo("America/New_York")


def slots(now: dt.datetime) -> int:
    hm, wd = now.hour * 100 + now.minute, now.weekday() < 5
    if wd and 915 <= hm < 940:
        return 0
    return 2 if wd and 800 <= hm < 1615 else 4


SAID = ("Yes: redo the VWAP hunt on hm40 and the fixed 3:1 blocks once feat/hm40-fixed-wf is merged. In-sample table and selection first, "
        "out-of-sample only for the picked boxes on my word.")                      # the owner, 2026-10-20 ~23:20 ET (hm40/PREREG_HM40.md)
SPECS = HERE / "hm40" / "specs"
RUNS_WF = EL / "runs_wf"


def _wf_store(name: str) -> Path:
    sp = json.loads((SPECS / f"{name}.json").read_text())
    return RUNS_WF / f"{name}-{sp['markets'][0]}-tf{sp['bar_sizes'][0]}" / "is" / "cells.npz"


def done(kind: str, name: str) -> bool:
    if kind == "wfr":
        return _wf_store(name).exists()
    if kind == "rand":
        return (ROOT / name / "wf" / "rand_oos.npz").exists()
    if kind == "wf":
        return (ROOT / name / "wf" / "result.json").exists()
    r = ROOT / name / "result.json"
    return r.exists() and not json.loads(r.read_text()).get("smoke") and (ROOT / name / "wf" / "result.json").exists()


def log(msg: str) -> None:
    with open(HERE / "progress.log", "a") as f:
        f.write(f"{dt.datetime.now(NY):%m-%d %H:%M} {msg}\n")


def cmd(kind: str, name: str) -> str:
    run = f"{PY} bp.py taught run taught/{name}.json --workers=3 > {HERE}/logs/run_{name}.log 2>&1"
    wf = f"{PY} bp.py taught wf {name} --workers=3 > {HERE}/logs/wf_{name}.log 2>&1"
    if kind == "wfr":                               # the 3:1 in-sample run of an hm60 spec, a screening pass (no worse-fills stores)
        return f"{PY} bp.py wf run {SPECS}/{name}.json --owner-said='{SAID}' --no-worse --workers=3 > {HERE}/logs/wfis_{name}.log 2>&1"
    if kind == "rand":
        return f"{PY} {HERE}/randctl.py run {name} --workers=3 > {HERE}/logs/rand_{name}.log 2>&1"
    if kind == "wf":
        return wf
    r = ROOT / name / "result.json"
    have = r.exists() and not json.loads(r.read_text()).get("smoke")
    return wf if have else f"{run} && {wf}"


def main() -> None:
    q = [ln.split() for ln in (HERE / (sys.argv[1] if len(sys.argv) > 1 else "queue.txt")).read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    todo = [(k, n) for k, n in q if not done(k, n)]
    log(f"start: {len(todo)} of {len(q)} jobs to do")
    live: dict = {}
    while todo or live:
        for n, (p, t0) in list(live.items()):
            if p.poll() is not None:
                log(f"done {n} exit={p.returncode} {(time.time() - t0) / 60:.1f} min")
                del live[n]
        while todo and len(live) < slots(dt.datetime.now(NY)):
            k, n = todo.pop(0)
            live[n] = (subprocess.Popen(cmd(k, n), shell=True, cwd=EL), time.time())
            log(f"start {k} {n} ({len(todo)} left)")
        time.sleep(20)
    log("queue empty")


if __name__ == "__main__":
    main()
