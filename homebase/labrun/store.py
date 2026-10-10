"""The store of promoted Lab strategies: what the runner hosts and what the Desk page shows (2026-10-09).

Promote writes ONE file, a frozen copy of the draft's code with its settings and its backtest's headline numbers; the
runner reads it and writes down what the strategy would have done. A record is never code that runs here, and nothing in
this module talks to a service. Remove deletes the record only: the days and the journal stay as the history.

    <root>/<name>.json                  the promoted strategy        root = HOMEBASE_DESKLAB_ROOT, else ~/.homebase/desklab
    <root>/<name>/days/<YYYY-MM-DD>.json   one day summary (written whole by the runner)
    <root>/<name>/journal.jsonl         the runner's notes, one JSON line each
    <root>/runner.json                  the runner's heartbeat

Stdlib only (draftstore, for the name rule, is too).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path

from ..draftstore import NAME_RE

ENV_ROOT = "HOMEBASE_DESKLAB_ROOT"
RUNNER_FILE = "runner.json"              # the heartbeat sits beside the records, so a strategy may not be called "runner"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HEADLINE = (("net", "net_profit"), ("trades", "trades"), ("win_rate", "win_rate"), ("profit_factor", "profit_factor"),
            ("max_drawdown", "max_drawdown"))        # our key, the report summary's key


def root(arg=None) -> Path:
    v = arg or os.environ.get(ENV_ROOT)
    return Path(v).expanduser() if v else Path.home() / ".homebase" / "desklab"


def _name(name) -> str:
    if not isinstance(name, str) or not NAME_RE.fullmatch(name) or f"{name}.json" == RUNNER_FILE:
        raise ValueError("name: a Lab strategy's name -- a-z, 0-9 and '_' (a letter first)")
    return name


def _file(name, at=None) -> Path:
    return root(at) / f"{_name(name)}.json"


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
    run's headline numbers (from the bundle's run.json: inputs, qty, range, report.summary.all)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    run = bundle.get("run") or {}
    summary = (((run.get("report") or {}).get("summary") or {}).get("all")) or {}
    return {"name": name, "id": f"draft_{name}", "label": meta.get("name") or name, "root": meta.get("root"), "source": source,
            "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(), "params": dict(run.get("inputs") or {}),
            "qty": run.get("qty"),
            "run": {"id": run_id, "range": run.get("range"), **{ours: summary.get(theirs) for ours, theirs in HEADLINE}},
            "notes": list(notes), "promoted_utc": now.isoformat(timespec="seconds"), "enabled": True}


def put(rec: dict, at=None) -> dict:
    _write(_file(rec.get("name"), at), rec)
    return rec


def get(name: str, at=None) -> dict | None:
    return _read(_file(name, at))


def remove(name: str, at=None) -> bool:
    """True when it was on the Desk. Only the record goes: the days and the journal are the history. A file that is not
    there is not an error: the page may be a step behind."""
    try:
        _file(name, at).unlink()
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


def set_enabled(name: str, on: bool, at=None) -> dict | None:
    rec = get(name, at)
    if rec is None:
        return None
    return put({**rec, "enabled": bool(on)}, at)


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
