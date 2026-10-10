"""The store of promoted Lab strategies: what the runner hosts and what the Desk page shows (2026-10-09).

Promote writes ONE file, a frozen copy of the draft's code with its settings and its backtest's headline numbers; the
runner reads it and writes down what the strategy would have done. A record is never code that runs here, and nothing in
this module talks to a service. Remove deletes the record only: the days and the journal stay as the history.

    <root>/<name>.json                  the promoted strategy        root = HOMEBASE_DESKLAB_ROOT, else ~/.homebase/desklab
    <root>/<name>/days/<YYYY-MM-DD>.json   one day summary (written whole by the runner)
    <root>/<name>/journal.jsonl         the runner's notes, one JSON line each
    <root>/runner.json                  the runner's heartbeat
    <root>/<name>.desk.json             the DESK's sidecar (Step B): {"mark": [sha256, promoted_utc], "limits": {...} | None,
                                        "book": [{"account", "qty"}], "written_utc"}. Written by the desk process only
                                        (the runner and the chart service read it); listing() skips it (its stem is not
                                        a strategy name)

    <root>/desk.lock                    the ONE desk that owns the sidecars holds a flock on it for its whole life
                                        (desk_lock); a second desk on this store reads only

One writer at a time, across processes, for put, set_enabled, remove and put_desk: write_lock() is a flock on the root
folder itself (no lock file for it).

The record carries, besides the code and the run's numbers, `session_window` (["09:25", "16:00"]) and `bar_minutes` (0 =
none) from the draft's static meta, and the `commission` and `slippage_ticks` that backtest ran with (the runner's
would-be fills and the daily match use them; None = the tester's defaults). A day summary carries `promoted_utc` (the
record's, copied when the day starts: a day file is final for its date only for the promotion that wrote it), `match`
({"ok": bool | None, "text"}: the daily match against the tester, labrun/match.py) and, only for a day made from prints
already held (catch-up), `rebuilt: true`.

Stdlib only, and it imports nothing else of homebase: the desk process reads this store (Step B), and the desk must
never load the draft helper (tests/test_claude_drafts.py). The name rule is the drafts' own, kept here as a copy that a
test holds equal to draftstore.NAME_RE.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")        # a draft's name (draftstore.NAME_RE: tests pin them equal)
ENV_ROOT = "HOMEBASE_DESKLAB_ROOT"
RUNNER_FILE = "runner.json"              # the heartbeat sits beside the records, so a strategy may not be called "runner"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HEADLINE = (("net", "net_profit"), ("trades", "trades"), ("win_rate", "win_rate"), ("profit_factor", "profit_factor"),
            ("max_drawdown", "max_drawdown"))        # our key, the report summary's key
DEFAULT_WINDOW = ["09:25", "16:00"]      # the Strategy's own session_window
DESK_SUFFIX = ".desk.json"               # the desk's sidecar beside the record
DESK_LOCK = "desk.lock"                  # held by the one desk that owns this store's sidecars


def root(arg=None) -> Path:
    v = arg or os.environ.get(ENV_ROOT)
    return Path(v).expanduser() if v else Path.home() / ".homebase" / "desklab"


def _name(name) -> str:
    if not isinstance(name, str) or not NAME_RE.fullmatch(name) or f"{name}.json" == RUNNER_FILE:
        raise ValueError("name: a Lab strategy's name -- a-z, 0-9 and '_' (a letter first)")
    return name


def _file(name, at=None) -> Path:
    return root(at) / f"{_name(name)}.json"


def _desk_file(name, at=None) -> Path:
    return root(at) / f"{_name(name)}{DESK_SUFFIX}"


_held = threading.local()                # this thread's locks: {root: depth}, so a writer may call another writer


@contextlib.contextmanager
def write_lock(at=None, wait_s: float | None = None):
    """One writer at a time in this store, across processes and threads (flock on the root folder). A thread that
    holds it may take it again (Promote checks the sidecar, then writes the record, under one lock). wait_s None waits
    for its turn; a number gives up after that long with TimeoutError -- for a caller that must not stand still."""
    d = root(at)
    held = _held.__dict__.setdefault("roots", {})
    key = str(d)
    if key in held:
        held[key] += 1
        try:
            yield
        finally:
            held[key] -= 1
        return
    d.mkdir(parents=True, exist_ok=True)
    fd = os.open(d, os.O_RDONLY)
    try:
        if wait_s is None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        else:
            until = time.monotonic() + wait_s
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= until:
                        raise TimeoutError("the Lab store is being written by another process") from None
                    time.sleep(0.005)
        held[key] = 1
        try:
            yield
        finally:
            del held[key]
    finally:
        os.close(fd)                                 # closing the file gives the lock back


def _write(f: Path, obj) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f".{f.name}.tmp")
    tmp.write_text(json.dumps(obj), encoding="utf-8")
    os.replace(tmp, f)                               # whole or not at all


def _read(f: Path) -> dict | None:
    try:
        got = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


def snapshot(name: str, source: str, meta: dict, bundle: dict, run_id: str, notes: list,
             now: dt.datetime | None = None) -> dict:
    """What is kept when a draft is promoted: its text as it was backtested, the settings and size of that run, and the
    run's headline numbers and costs (from the bundle's run.json: inputs, qty, range, commission, slippage_ticks,
    report.summary.all), and the window and bar size the page shows (the static meta's; the Strategy defaults when the
    draft does not say). It lands switched OFF, also when it replaces one that was on: the owner turns it on, on the
    Desk."""
    now = now or dt.datetime.now(dt.timezone.utc)
    run = bundle.get("run") or {}
    summary = (((run.get("report") or {}).get("summary") or {}).get("all")) or {}
    return {"name": name, "id": f"draft_{name}", "label": meta.get("name") or name, "root": meta.get("root"), "source": source,
            "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(), "params": dict(run.get("inputs") or {}),
            "qty": run.get("qty"),
            "run": {"id": run_id, "range": run.get("range"), **{ours: summary.get(theirs) for ours, theirs in HEADLINE}},
            "notes": list(notes), "promoted_utc": now.isoformat(timespec="seconds"), "enabled": False,
            "commission": run.get("commission"), "slippage_ticks": run.get("slippage_ticks"),
            "session_window": list(meta.get("session_window") or DEFAULT_WINDOW), "bar_minutes": meta.get("bar_minutes") or 0}


def put(rec: dict, at=None) -> dict:
    f = _file(rec.get("name"), at)
    with write_lock(at):
        _write(f, rec)
    return rec


def get(name: str, at=None) -> dict | None:
    return _read(_file(name, at))


def remove(name: str, at=None) -> bool:
    """True when it was on the Desk. Only the record goes: the days and the journal are the history. A file that is not
    there is not an error: the page may be a step behind. The desk's sidecar is not touched: it is the desk's."""
    f = _file(name, at)
    with write_lock(at):
        try:
            f.unlink()
            return True
        except FileNotFoundError:
            return False


def listing(at=None) -> list:
    """Every promoted strategy, the latest promoted first; a file that does not read is left out."""
    d = root(at)
    out = []
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        if NAME_RE.fullmatch(f.stem) and f.name != RUNNER_FILE:
            got = get(f.stem, at)
            if got is not None and got.get("name") == f.stem:
                out.append(got)
    return sorted(out, key=lambda s: str(s.get("promoted_utc") or ""), reverse=True)


def mark_of(rec: dict) -> list:
    """What names ONE promotion of a record: its code and the moment it was promoted (see same_promotion)."""
    return [rec.get("sha256"), rec.get("promoted_utc")]


def set_enabled(name: str, on: bool, at=None, mark=None, wait_s: float | None = None) -> dict | None:
    """The switch. None when the strategy is not on the Desk, or -- with a `mark` -- when the record is no longer that
    promotion (it was promoted again since the caller looked): nothing is written then. Read and write under one lock,
    so a Promote at the same instant is never half undone. wait_s: see write_lock."""
    f = _file(name, at)
    with write_lock(at, wait_s):
        rec = _read(f)
        if rec is None or (mark is not None and list(mark) != mark_of(rec)):
            return None
        rec = {**rec, "enabled": bool(on)}
        _write(f, rec)
        return rec


def get_desk(name: str, at=None) -> dict | None:
    """The desk's sidecar for a promoted strategy; None when there is none or it does not read."""
    return _read(_desk_file(name, at))


def put_desk(name: str, obj: dict, at=None, wait_s: float | None = None) -> dict:
    """Written by the desk process only. wait_s: see write_lock."""
    f = _desk_file(name, at)
    with write_lock(at, wait_s):
        _write(f, obj)
    return obj


def remove_desk(name: str, at=None) -> bool:
    f = _desk_file(name, at)
    with write_lock(at):
        try:
            f.unlink()
            return True
        except FileNotFoundError:
            return False


def desk_names(at=None) -> list:
    """The names that have a sidecar, whether or not their record is still there."""
    d = root(at)
    out = []
    for f in sorted(d.glob("*" + DESK_SUFFIX)) if d.is_dir() else []:
        name = f.name[:-len(DESK_SUFFIX)]
        if NAME_RE.fullmatch(name) and f"{name}.json" != RUNNER_FILE:
            out.append(name)
    return out


def desk_lock(at=None) -> int | None:
    """Take this store for ONE desk: an exclusive flock on <root>/desk.lock, never waited for. Returns the open file
    (keep it for as long as the desk lives: the lock ends with desk_unlock or with the process), or None when another
    desk -- another process, or another holder in this one -- has it, or the file cannot be opened."""
    d = root(at)
    try:
        d.mkdir(parents=True, exist_ok=True)
        fd = os.open(d / DESK_LOCK, os.O_CREAT | os.O_RDWR, 0o600)
    except OSError:
        return None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except OSError:
        os.close(fd)
        return None


def desk_unlock(fd) -> None:
    with contextlib.suppress(OSError, TypeError):
        os.close(fd)


def booked(name: str, at=None) -> bool:
    """True while the desk's sidecar holds book rows: accounts are assigned to this strategy on the Desk."""
    side = get_desk(name, at)
    return bool(side and isinstance(side.get("book"), list) and side["book"])


def same_promotion(day, rec: dict) -> bool:
    """A day file written for THIS promotion of the record: the same code, promoted at the same moment (promoting
    again, even the same code, is a new one). A day file from before promoted_utc was kept is judged by its code
    alone. The one place that says so: the runner (what is final, what is matched) and the Desk's list both ask it."""
    return (isinstance(day, dict) and day.get("sha256") == rec.get("sha256")
            and day.get("promoted_utc") in (None, rec.get("promoted_utc")))


def day_path(name: str, date: str, at=None) -> Path:
    if not isinstance(date, str) or not DATE_RE.fullmatch(date):
        raise ValueError("date: YYYY-MM-DD")
    return root(at) / _name(name) / "days" / f"{date}.json"


def put_day(name: str, summary: dict, at=None) -> None:
    _write(day_path(name, summary.get("date"), at), summary)


def get_day(name: str, date: str, at=None) -> dict | None:
    return _read(day_path(name, date, at))


def days(name: str, n: int = 10, at=None) -> list:
    """The newest n day summaries, newest first (by file name); a file that does not read is left out."""
    d = root(at) / _name(name) / "days"
    out = []
    for f in sorted(d.glob("*.json"), reverse=True) if d.is_dir() else []:
        if DATE_RE.fullmatch(f.stem):
            got = _read(f)
            if got is not None:
                out.append(got)
                if len(out) >= n:
                    break
    return out


def journal(name: str, line: dict, at=None) -> None:
    f = root(at) / _name(name) / "journal.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")


def put_runner(status: dict, at=None) -> None:
    _write(root(at) / RUNNER_FILE, status)


def get_runner(at=None) -> dict | None:
    return _read(root(at) / RUNNER_FILE)
