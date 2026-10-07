"""The Settings > Data tab's "Refresh data" button: one click runs the tick archive's repair pass
and then fills what it cannot, in a SEPARATE process (this service also records live ticks, so a
fetch that waits out the broker's rate limit must never sit on its event loop).

  1. ``python -m homebase.ticks``                                  the hourly/nightly job, by hand: fetches from
                                                                   the broker's history exactly what the archive
                                                                   and the live recording lack, merges it, then
                                                                   rewrites the coverage report
  2. ``python -m homebase.ticks --fill-from-massive --holes``      the holes the broker no longer has, from the
                                                                   bought flat files -- only when the Massive
                                                                   credentials are in this service's environment;
                                                                   otherwise the step is skipped and says so

Both are the jobs the launchd schedule already runs (deploy/com.ramosquant.homebase-ticks.plist.template) and
both take the archive's own lock, so a click during the hourly run waits for nothing and breaks nothing: the run
in progress does the work and step 1 ends at once. Neither opens an order path -- they only read the broker's
tick history and write ~/futures_ticks. Step 1 never starts 09:20-09:35 ET (it checks itself), and the button
refuses then too, saying why, rather than start a run that does nothing.

    <state>/refresh/status.json   {status: idle|running|done|error|cancelled, step, steps: [{key, label, state, note}],
                                   started, finished, coverage?}
    <state>/refresh/log.txt       both steps' output, appended

ONE refresh at a time (start() refuses a second); cancel() ends the running step.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request

from ..paths import repo_root, state_dir
from .export import in_quiet, read_json, write_json
from .tester_api import host_ok

FINAL = ("done", "error", "cancelled")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def massive_ready(env=None) -> bool:
    """Are the flat-file credentials in the environment? (tickmassive's own rule; never read or printed here.)"""
    env = os.environ if env is None else env
    return bool(env.get("MASSIVE_S3_KEY") and env.get("MASSIVE_S3_SECRET"))


def plan(python: str, env=None) -> list[dict]:
    """The steps, in order: {key, label, argv, skip?} -- `skip` is why a step will not run."""
    steps = [{"key": "broker", "label": "Fetch missing ticks from the broker",
              "argv": [python, "-m", "homebase.ticks"]},
             {"key": "massive", "label": "Fill the older holes from Massive",
              "argv": [python, "-m", "homebase.ticks", "--fill-from-massive", "--holes"]}]
    if not massive_ready(env):
        steps[1]["skip"] = "Massive credentials are not set for this service"
    return steps


def coverage_summary(path: Path) -> dict | None:
    """The coverage report's one-line facts (tickcoverage.write_report's `summary`), or None before the first report."""
    rep = read_json(path, None)
    if not isinstance(rep, dict) or not isinstance(rep.get("summary"), dict):
        return None
    return {**rep["summary"], "generated_at_utc": rep.get("generated_at_utc")}


class RefreshManager:
    def __init__(self, base: Path, *, python: str | None = None, cwd: Path | None = None,
                 clock: Callable[[], dt.datetime] | None = None, popen=subprocess.Popen,
                 env=None, coverage_path: Path | None = None):
        self.dir = Path(base) / "refresh"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.python, self.cwd = python or sys.executable, Path(cwd) if cwd else repo_root()
        self.clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))
        self.popen, self.env = popen, env
        self.coverage_path = coverage_path or state_dir() / "tick_coverage.json"
        self._lock = threading.Lock()
        self._proc = None
        self._cancelled = False
        self._status = self._recover()

    def _recover(self) -> dict:
        st = read_json(self.dir / "status.json", None)
        if not isinstance(st, dict):
            return {"status": "idle"}
        if st.get("status") == "running":      # a previous service process died mid-run: never "running" forever
            st.update(status="error", note="interrupted (the chart service restarted)", finished=_now())
            write_json(self.dir / "status.json", st)
        return st

    def status(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._status))

    def _save(self) -> None:
        write_json(self.dir / "status.json", self._status)

    def start(self) -> dict:
        with self._lock:
            if self._status.get("status") == "running":
                raise ValueError("a refresh is already running")
            if in_quiet(self.clock()):
                raise ValueError("not 09:20–09:35 ET on weekdays (the 9:30 window): refresh after 09:35")
            steps = plan(self.python, self.env)
            self._cancelled = False
            self._status = {"status": "running", "step": steps[0]["key"], "started": _now(),
                            "steps": [{"key": s["key"], "label": s["label"],
                                       "state": "skipped" if s.get("skip") else "waiting", "note": s.get("skip", "")}
                                      for s in steps]}
            self._save()
        threading.Thread(target=self._run, args=(steps,), daemon=True).start()
        return self.status()

    def _set_step(self, key: str, state: str, note: str = "") -> None:
        with self._lock:
            for s in self._status["steps"]:
                if s["key"] == key:
                    s["state"], s["note"] = state, note
            self._status["step"] = key
            self._save()

    def _run(self, steps: list[dict]) -> None:
        failed = ""
        with open(self.dir / "log.txt", "ab") as log:
            for s in steps:
                if s.get("skip"):
                    continue
                with self._lock:
                    if self._cancelled:
                        break
                self._set_step(s["key"], "running")
                log.write(f"\n=== {_now()} {s['label']}: {' '.join(s['argv'])}\n".encode())
                log.flush()
                try:
                    proc = self.popen(s["argv"], cwd=self.cwd, stdout=log, stderr=subprocess.STDOUT)
                    with self._lock:
                        self._proc = proc
                    code = proc.wait()
                except OSError as e:
                    code = -1
                    log.write(f"could not start: {e}\n".encode())
                with self._lock:
                    self._proc = None
                    cancelled = self._cancelled
                if cancelled:
                    self._set_step(s["key"], "cancelled")
                    break
                if code:
                    failed = f"{s['label']} failed (exit {code}) -- see {self.dir / 'log.txt'}"
                    self._set_step(s["key"], "error", f"exit {code}")
                    break
                self._set_step(s["key"], "done")
        with self._lock:
            self._status["status"] = ("cancelled" if self._cancelled else "error" if failed else "done")
            if failed:
                self._status["note"] = failed
            self._status["finished"] = _now()
            cov = coverage_summary(self.coverage_path)
            if cov:
                self._status["coverage"] = cov
            self._save()

    def cancel(self) -> dict:
        with self._lock:
            if self._status.get("status") != "running":
                return json.loads(json.dumps(self._status))
            self._cancelled = True
            proc = self._proc
        if proc is not None:
            proc.terminate()
        return self.status()


def refresh_router(write_ok: Callable[[Request], None], state: Path | None = None, **kw) -> APIRouter:
    """GET reads the status; POSTs also pass `write_ok` (the service's Origin + Host write guard)."""
    mgr = RefreshManager(Path(state) if state else state_dir() / "charts", **kw)
    r = APIRouter(prefix="/api/refresh", dependencies=[Depends(host_ok)])

    @r.get("")
    def status():
        return mgr.status()

    @r.post("")
    def start(request: Request):
        write_ok(request)
        try:
            return mgr.start()
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @r.post("/cancel")
    def cancel(request: Request):
        write_ok(request)
        return mgr.cancel()

    r.manager = mgr
    return r
