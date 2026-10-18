"""The Settings > Data tab's "Refresh data" button: one click runs the tick archive's repair pass, in a
SEPARATE process (this service also records live ticks, so a fetch that waits out the broker's rate limit
must never sit on its event loop).

    ``python -m homebase.ticks --full``  the hourly/nightly job, by hand, without the daytime page caps (a click
                                    wants everything the broker still has; it stops when the live login's hour
                                 is spent, so the charts keep theirs -- click again to go on): fetches from Tradovate's tick history
                                    exactly what the archive and the live recording lack, for every root
                                    (homebase.ticks.ROOTS), merges it, then rewrites the coverage report

Tradovate only -- no bought data (Massive) is touched. What has already left Tradovate's history window
(it serves from 00:00 UTC of the previous UTC day) cannot be filled by this button; the coverage report
lists it as "lost".

It is the job the launchd schedule already runs (deploy/com.ramosquant.homebase-ticks.plist.template) and
takes the archive's own lock, so a click during the hourly run breaks nothing: the run in progress does the
work and this one ends at once. It never opens an order path -- it only reads the broker's tick history and
writes ~/futures_ticks. It needs the desk's Tradovate login (the md token the desk writes): with none on disk the
click is refused, saying so, rather than "done" with nothing fetched. When the run ends the chart service reloads
every open chart (on_finish), so what it filled shows at once. It never starts 09:20-09:35 ET (it checks
itself), and the button refuses then too, saying why, rather than start a run that does nothing.

    <state>/refresh/status.json   {status: idle|running|done|error|cancelled, step, steps: [{key, label, state, note}],
                                   started, finished, coverage?}
    <state>/refresh/log.txt       the job's output, appended

ONE refresh at a time (start() refuses a second); cancel() ends the running job.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import json
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
NO_LOGIN = ("Tradovate's live login is not connected on the Desk (no valid market-data token), so nothing can be "
            "fetched: reconnect it on the Desk, then refresh")
NO_TOKEN_EXIT = 3       # ticks.NO_TOKEN_EXIT: the job waited for the desk's token and gave up


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def plan(python: str) -> list[dict]:
    """The steps, in order: {key, label, argv}. One: Tradovate's tick history, nothing bought."""
    return [{"key": "broker", "label": "Fetch missing ticks from Tradovate",
             "argv": [python, "-m", "homebase.ticks", "--full"]}]


def coverage_summary(path: Path) -> dict | None:
    """The coverage report's one-line facts (tickcoverage.write_report's `summary`), or None before the first report."""
    rep = read_json(path, None)
    if not isinstance(rep, dict) or not isinstance(rep.get("summary"), dict):
        return None
    return {**rep["summary"], "generated_at_utc": rep.get("generated_at_utc")}


class RefreshManager:
    def __init__(self, base: Path, *, python: str | None = None, cwd: Path | None = None,
                 clock: Callable[[], dt.datetime] | None = None, popen=subprocess.Popen,
                 coverage_path: Path | None = None, lock_path: Path | None = None,
                 md_ready: Callable[[], bool] | None = None, on_finish: Callable[[dict], None] | None = None):
        self.dir = Path(base) / "refresh"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.python, self.cwd = python or sys.executable, Path(cwd) if cwd else repo_root()
        self.clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))
        self.popen = popen
        self.coverage_path = coverage_path or state_dir() / "tick_coverage.json"
        self.lock_path = lock_path or state_dir() / "ticks.lock"
        self.md_ready = md_ready        # () -> is the desk's md token on disk valid? None: not checked
        self.on_finish = on_finish      # (final status) -> None, from the run's thread: the charts reload
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

    def _archive_busy(self) -> bool:
        """True while another tick run (the hourly launchd job) holds the archive lock. A click then would start a
        job that ends at once (it never waits for the lock) and the button would say "Done" having fetched nothing."""
        try:
            with open(self.lock_path, "a") as f:
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return True
                fcntl.flock(f, fcntl.LOCK_UN)
        except OSError:
            return False
        return False

    def _save(self) -> None:
        write_json(self.dir / "status.json", self._status)

    def start(self) -> dict:
        with self._lock:
            if self._status.get("status") == "running":
                raise ValueError("a refresh is already running")
            if in_quiet(self.clock()):
                raise ValueError("not 09:20–09:35 ET on weekdays (the 9:30 window): refresh after 09:35")
            if self.md_ready is not None and not self.md_ready():
                raise ValueError(NO_LOGIN)
            if self._archive_busy():
                raise ValueError("the hourly tick job is already fetching (see homebase/.state/ticks.log); "
                                 "it is the same job, so wait for it to finish, then refresh again")
            steps = plan(self.python)
            self._cancelled = False
            self._status = {"status": "running", "step": steps[0]["key"], "started": _now(),
                            "steps": [{"key": s["key"], "label": s["label"],
                                       "state": "waiting", "note": ""}
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
                if code == NO_TOKEN_EXIT:
                    failed = NO_LOGIN
                    self._set_step(s["key"], "error", "no Tradovate login")
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
            final = json.loads(json.dumps(self._status))
        if self.on_finish is not None:
            try:            # whatever the run filled (a cancelled or failed one too) is on disk: show it
                self.on_finish(final)
            except Exception:  # noqa: BLE001 -- a reload that cannot start never turns a run into a crash
                pass

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
