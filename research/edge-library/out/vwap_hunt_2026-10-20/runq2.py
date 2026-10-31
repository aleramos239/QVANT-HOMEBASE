"""Portfolio hunt runner v2 (restart-safe, editable while it runs; the review of 2026-10-21 folded in).

- Re-reads queue_hm.txt every loop. Kinds: "wfr <spec>" = the 3:1 in-sample screening run of hm40/specs/<spec>.json (no worse fills);
  "wfw <spec>" = that store's worse-fills pass; "oos <store> <box>" = the picked box's test months, under the owner's standing word;
  "roos <store>" = the random entries on those test months (hm40/oosrand.py). A malformed line is logged once and skipped.
- A job is skipped when done (its store / read on disk; for "oos" also a claim in the one-read log), already running on the machine, or
  FAILED before (logs/<kind>_<name>.failed: a job that exits non-zero is never started again; the line stays for a person to see).
- Slots count every heavy research process on the machine (any chat's): 4 at once outside desk hours, 2 on weekdays 08:00-16:15 ET, none
  started 09:15-09:40 ET. Every job runs with HOMEBASE_WF_LAST=2026-05: the hunt's 14 blocks cannot grow while it runs.
- It never stops on an empty queue: every 10 minutes it runs hm40/advance.py, which adds the next steps (worse fills, test months,
  random entries) to the queue.

Run: nohup .venv-research/bin/python research/edge-library/out/vwap_hunt_2026-10-20/runq2.py &   (progress: progress.log)"""
from __future__ import annotations

import datetime as dt
import json
import os
import shlex
import subprocess
import time
import zoneinfo
from pathlib import Path

import runq as Q

HERE = Path(__file__).resolve().parent
NY = zoneinfo.ZoneInfo("America/New_York")
OOS_SAID = ("for now you can manually and discretionally pick the box and continue, i give you permission or freedom to continue without me, "
            "so yes standing word you pick by the written rule log every read and report when finished")   # the owner, 2026-10-20 ~23:45 ET
WHO = "claude: the owner's standing word of 2026-10-20 (PREREG_HM40 s4 / Amendment B rule)"
PIN = "2026-05"
KINDS = {"wfr": 1, "wfw": 1, "oos": 2, "roos": 1}
HEAVY = ("taught run", "taught wf", "wf run", "wf oos", " build", " test ", "randctl.py run", "oosrand.py", "bp.py _job ", "bp.py pools")
ADVANCE_EVERY = 600


def _ps() -> list:
    return [ln for ln in subprocess.run(["ps", "-Ao", "command"], capture_output=True, text=True).stdout.splitlines()
            if not ln.startswith("/bin/sh") and ("bp.py" in ln or "randctl.py" in ln or "oosrand.py" in ln)]


def running() -> list:
    return [ln for ln in _ps() if ("bp.py wf " in ln and ("hm40/specs/" in ln or " oos " in ln)) or "oosrand.py" in ln]


def heavy() -> int:
    return sum(1 for ln in _ps() if any(h in ln for h in HEAVY))


def key(kind: str, args: list) -> str:
    return {"wfr": f"hm40/specs/{args[0]}.json", "wfw": f"hm40/specs/{args[0]}.json", "roos": f"oosrand.py {args[0]}"}.get(kind, f" oos {args[0]} ")


def failed_file(kind: str, args: list) -> Path:
    return HERE / "logs" / f"{kind}_{args[0]}.failed"


def done(kind: str, args: list) -> bool:
    if failed_file(kind, args).exists():
        return True
    if kind == "wfr":
        return Q._wf_store(args[0]).exists()
    if kind == "wfw":
        sp = json.loads((Q.SPECS / f"{args[0]}.json").read_text())
        home = Q.RUNS_WF / f"{args[0]}-{sp['markets'][0]}-tf{sp['bar_sizes'][0]}"
        return all((home / f"is-{s}-worse" / "cells.npz").exists() for s in sp["sessions"])
    if kind == "oos":
        if (Q.RUNS_WF / args[0] / "oos" / "cells.npz").exists():
            return True
        import sys
        sys.path.insert(0, str(Q.EL))
        from blueprint import reads as RD
        return bool(RD.wf_oos_on_file(args[0], args[1]))             # claimed: a read is never run twice (stopped = a used read)
    return (Q.RUNS_WF / args[0] / "oos-rand.npz").exists()


def cmd(kind: str, args: list) -> str:
    n = args[0]
    q = shlex.quote                                  # every argument quoted (an apostrophe in the words broke the first two reads' commands)
    if kind == "wfr":
        return f"{Q.PY} bp.py wf run {q(f'{Q.SPECS}/{n}.json')} --owner-said={q(Q.SAID)} --no-worse --workers=3 > {q(f'{HERE}/logs/wfis_{n}.log')} 2>&1"
    if kind == "wfw":
        return f"{Q.PY} bp.py wf run {q(f'{Q.SPECS}/{n}.json')} --owner-said={q(Q.SAID)} --workers=3 > {q(f'{HERE}/logs/wfw_{n}.log')} 2>&1"
    if kind == "roos":
        return f"{Q.PY} {q(f'{HERE}/hm40/oosrand.py')} {q(n)} --workers=3 > {q(f'{HERE}/logs/roos_{n}.log')} 2>&1"
    return (f"{Q.PY} bp.py wf oos {q(n)} {q(args[1])} --owner-said={q(OOS_SAID)} --who={q(WHO)} --workers=3 "
            f"> {q(f'{HERE}/logs/oos_{n}.log')} 2>&1")


def main() -> None:
    Q.log("runq2 start (review fixes 2026-10-21)")
    live: dict = {}
    bad_lines: set = set()
    last_adv = 0.0
    env = {**os.environ, "HOMEBASE_WF_LAST": PIN}
    while True:
        try:
            for n, (p, t0, k, a) in list(live.items()):
                if p.poll() is not None:
                    Q.log(f"done {n} exit={p.returncode} {(time.time() - t0) / 60:.1f} min")
                    if p.returncode != 0:
                        failed_file(k, a).write_text(f"exit {p.returncode} at {dt.datetime.now(NY):%m-%d %H:%M}\n")
                        Q.log(f"FAILED {k} {n}: not started again (logs/{failed_file(k, a).name})")
                    del live[n]
            if time.time() - last_adv > ADVANCE_EVERY:
                last_adv = time.time()
                r = subprocess.run([str(Q.PY), str(HERE / "hm40" / "advance.py")], capture_output=True, text=True, env=env)
                msg = (r.stdout.strip().splitlines() or ["(no output)"])
                Q.log("advance: " + " | ".join(msg[-6:]) + (f" ERR {r.stderr.strip()[-300:]}" if r.returncode else ""))
            q = []
            for ln in (HERE / "queue_hm.txt").read_text().splitlines():
                t = ln.split()
                if not t or ln.strip().startswith("#"):
                    continue
                if t[0] not in KINDS or len(t) - 1 != KINDS[t[0]]:
                    if ln not in bad_lines:
                        bad_lines.add(ln)
                        Q.log(f"queue line skipped (unknown kind or arguments): {ln!r}")
                    continue
                q.append((t[0], t[1:]))
            procs = running()
            todo = []
            for k, a in q:
                name = f"{k} {' '.join(a)}"
                try:
                    if name in live or any(key(k, a) in p for p in procs) or done(k, a):
                        continue
                except (OSError, KeyError, ValueError, IndexError) as e:
                    if name not in bad_lines:
                        bad_lines.add(name)
                        Q.log(f"queue line skipped ({type(e).__name__}: {e}): {name}")
                    continue
                todo.append((k, a))
            cap = Q.slots(dt.datetime.now(NY))
            if (HERE / "CAP").exists():              # a lower cap for tonight (the Mac also hosts the shadow runner; it died at load 9 on 10-21)
                cap = min(cap, int((HERE / "CAP").read_text().strip() or cap))
            free = cap - max(len(procs), heavy())
            for k, a in todo[:max(0, free)]:
                name = f"{k} {' '.join(a)}"
                live[name] = (subprocess.Popen(cmd(k, a), shell=True, cwd=Q.EL, env=env), time.time(), k, a)
                Q.log(f"start {name} ({len(todo) - 1} left)")
                procs.append(key(k, a))
        except Exception as e:                       # noqa: BLE001 - the runner must not die on one bad turn
            Q.log(f"runner error: {type(e).__name__}: {e}")
        time.sleep(30)


if __name__ == "__main__":
    main()
