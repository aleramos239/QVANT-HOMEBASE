"""jobs.py -- long commands as JOBS (toolkit plan, section 8): `bp.py build ... --wait=S` answers within S seconds; past them
it answers job.state = running and the work goes on in a DETACHED child process; `bp.py job <id> --wait=S` picks the wait
back up, by the id alone, and answers with the ORIGINAL command's own result object once it is there.

    <ideas root>/_jobs/<id>/        the ideas root = --root, else HOMEBASE_IDEAS_ROOT, else ~/.homebase/ideas
        job.json      {id, command, name, args, wait, state queued | running | done | error, progress, pid, exit, the times}
        spec.json     the idea's settings as they were when the job was started (a later edit of the file changes no job)
        result.json   the command's ONE result object, as `bp.py job <id>` prints it
        log.txt       what the child wrote to stderr (the runner's progress, a traceback)
        pid           the child's process id, written by the parent
EVERY JOB IN ONE FOLDER, not in its idea's folder (plan section 3 had <name>/jobs/<id>/): `job <id>` is given no name, and a
job must never make an idea folder -- the app counts a folder there as an idea (homebase/ideastore.py), and `_jobs` is no
idea's name.
The child is this toolkit again (`bp.py _job <folder>`), started in its own session so that it outlives the command that
started it. A command that is refused inside the child ends the job as an error with the reason (exit 2); one that crashes,
or whose process is gone without a word, as an error that says so (exit 1): never a wait for ever.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import sys
import time
import traceback
from pathlib import Path

import judge as J

from . import W
from . import api

ENV = "HOMEBASE_IDEAS_ROOT"
FOLDER = "_jobs"
FINAL = ("done", "error")
ID = re.compile(r"^\d{8}T\d{6}-[0-9a-f]{6}$")
COMMANDS = {"build": api.build}                       # the commands that run as jobs (plan section 8: build, test)


def root(arg=None) -> Path:
    """The ideas root: the argument, else the environment, else the app's own folder (the tests never get that far)."""
    v = arg or os.environ.get(ENV)
    return Path(v).expanduser() if v else Path.home() / ".homebase" / "ideas"


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load(d: Path) -> dict:
    return json.loads((d / "job.json").read_text())


def _save(d: Path, job: dict) -> dict:
    """job.json, whole or not at all (a reader never sees half a file)."""
    tmp = d / f".job.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(job, indent=1))
    os.replace(tmp, d / "job.json")
    return job


def _tag(job: dict) -> dict:
    return {"id": job["id"], "state": job["state"], "progress": job.get("progress") or ""}


def code(r: dict) -> int:
    """The exit code of a result: 0 = done (lines may still fail) · 2 = refused · 1 = crashed."""
    return 0 if r["ok"] else 1 if r.get("crashed") else 2


def new(command: str, name, args: dict, root_, wait=0) -> Path:
    """A job, queued: its folder with job.json (and the spec as it is now). `args` = the command's keyword arguments, JSON."""
    if command not in COMMANDS:
        raise J.Refuse(f"{command} does not run as a job (jobs: {', '.join(COMMANDS)})")
    d = root(root_) / FOLDER / f"{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}-{secrets.token_hex(3)}"
    d.mkdir(parents=True)
    if isinstance(args.get("spec"), dict):
        (d / "spec.json").write_text(json.dumps(args["spec"], indent=1))
    _save(d, {"id": d.name, "command": command, "name": name, "args": args, "wait": wait, "state": "queued", "progress": "", "pid": None, "exit": None,
              "created_utc": _utc()})
    return d


def start(d: Path) -> None:
    """Start the job's child: this toolkit, detached (its own session, no stdin, its words to log.txt)."""
    with open(d / "log.txt", "ab") as log:
        p = subprocess.Popen([sys.executable, str(W / "bp.py"), "_job", str(d)], stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True, cwd=str(W))
    (d / "pid").write_text(str(p.pid))


def work(d) -> int:
    """THE CHILD: run the job's command and leave its result. -> the exit code (code())."""
    d = Path(d)
    job = _save(d, {**_load(d), "state": "running", "pid": os.getpid(), "started_utc": _utc()})
    try:
        r = COMMANDS[job["command"]](**job["args"], progress=lambda msg: _save(d, {**_load(d), "progress": msg}))
    except api.REFUSALS as e:
        r = api.refused(job["command"], str(e), job["name"])
    except Exception as e:  # noqa: BLE001 - whatever it was, the job must end and say so
        with open(d / "log.txt", "a") as log:
            log.write(traceback.format_exc())
        r = {**api.refused(job["command"], f"the job crashed: {type(e).__name__}: {e} (the traceback is in {d / 'log.txt'})", job["name"]), "crashed": True}
        r["text"] = "CRASHED: " + r["error"]
    return _finish(d, r)


def _finish(d: Path, r: dict) -> int:
    job = {**_load(d), "state": "done" if r["ok"] else "error", "finished_utc": _utc(), "exit": code(r)}
    r["job"] = _tag(job)
    tmp = d / f".result.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(r))
    os.replace(tmp, d / "result.json")              # the result first: a job that says it is done has its result
    _save(d, job)
    return job["exit"]


def find(job_id, root_) -> Path:
    """A job's folder by its id alone."""
    d = root(root_) / FOLDER / str(job_id)
    if not ID.match(str(job_id)) or not (d / "job.json").exists():
        raise J.Refuse(f"no job {job_id!r} under {root(root_)}")
    return d


def _alive(d: Path, job: dict) -> bool:
    """Is the job's process still there? (A child of this very process that has ended is reaped first, or it would look alive.)"""
    pid = job.get("pid") or (int((d / "pid").read_text()) if (d / "pid").exists() else None)
    if not pid:
        return True                                 # not started yet
    try:
        os.waitpid(pid, os.WNOHANG)
    except OSError:
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        pass
    return True


def wait(job_id, root_, seconds=None) -> dict:
    """Wait up to `seconds` (None = the wait the job was started with) for a job to end -> its command's result object
    (result.json), or -- still going -- the same object with no lines yet and job.state queued | running."""
    d = find(job_id, root_)
    end = time.monotonic() + float(_load(d).get("wait") or 0 if seconds is None else seconds)
    while True:
        job = _load(d)
        if job["state"] in FINAL:
            return json.loads((d / "result.json").read_text())
        if not _alive(d, job) and _load(d)["state"] not in FINAL:       # looked twice: it may have ended between the two
            r = {**api.refused(job["command"], f"the job's process is gone (killed, or it crashed without a word): see {d / 'log.txt'}", job["name"]), "crashed": True}
            r["text"] = "CRASHED: " + r["error"]
            _finish(d, r)
            continue
        if time.monotonic() >= end:
            r = api.result(job["command"], job["name"], round=job["args"].get("round_"), job=_tag(job))
            r["text"] = f"{job['command']} job {job['id']} is {job['state']}" + (f": {job['progress']}" if job.get("progress") else "")
            r["next"] = f"bp.py job {job['id']} --wait=<seconds> picks the wait back up."
            return r
        time.sleep(0.2)
