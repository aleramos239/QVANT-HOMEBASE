"""The Settings card "Health": GET /api/health (the data watchdog, the tick archive's coverage, which logs exist),
GET /api/logs/{name} (the tail of one log) and GET /api/preopen-check (tools/preopen_check.py, folded into the readiness banner).

Read-only. A log is named by a key of LOGS and nothing else: no path ever comes from the request. Only the end of the file is
read, a line is cut short, and a secret's value (token, password, key, Bearer, a long token-like blob) is masked before it leaves.
A file that is not on this machine (the server has no vpssync.log, no tick job copy) is a plain note, never an error."""
from __future__ import annotations

import asyncio
import datetime as dt
import importlib
import json
import re
import sys
import threading
import time
from pathlib import Path

from fastapi import HTTPException

LOGS = {"service": "Desk", "charts": "Charts", "labrun": "Lab runner", "ticks": "Tick job", "tickpull": "Tick pull",
        "prune": "Tick prune", "tapewarm": "Tape warm", "serversync": "Server sync", "vpssync": "Server updates",
        "vpssync.out": "Server updates (launchd)", "autopull": "Auto pull", "tunnel": "Server tunnel",
        "depthrelay": "Depth relay", "depthtunnel": "Depth tunnel"}
FILES = {k: k if "." in k else k + ".log" for k in LOGS}          # key -> file name in the state folder
TAIL_BYTES = 65536               # the end of a log that is read
LINES_DEFAULT, LINES_MAX, LINE_CHARS = 100, 500, 400
WATCH_STALE_S = 3 * 3600         # the tick job's data watchdog this old has stopped: said, never shown as current
PRE_GAP_S = 30                   # a pre-open run this young is the answer to "run it again"
PRE_DROP = {"desk readiness", "desk mode"}      # the banner already says these itself
LEVEL = {"OK": "ok", "WARN": "warn", "FAIL": "bad"}

_KEY = re.compile(r"""(\w{0,40}(?:token|password|passwd|secret|api[_-]?key|authorization)\w{0,40}["']?\s*[:=]\s*["']?)(?:Bearer\s+)?[^\s"',}&]+""", re.I)
_JWT = re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]*")
_BLOB = re.compile(r"[A-Za-z0-9]{32,}")
MASK_CHARS = 4 * LINE_CHARS      # mask() looks at no more than this of a line: the patterns never see a 64 KB run


def mask(line: str) -> str:
    """A log line with every secret's value replaced by ***. Words stay: 'token renewed at 17:10' is not a secret."""
    return _BLOB.sub("***", _JWT.sub("***", _KEY.sub(r"\1***", line[:MASK_CHARS])))


def _json(path: Path):
    try:
        v = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return v if isinstance(v, dict) else None


def tail(path: Path, lines: int) -> dict | None:
    try:
        with open(path, "rb") as f:
            size = f.seek(0, 2)
            f.seek(max(0, size - TAIL_BYTES))
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    rows = text.splitlines()
    if size > TAIL_BYTES:
        rows = rows[1:]                       # the first line is cut in half
    return {"size": size, "lines": [mask(x)[:LINE_CHARS] for x in rows[-lines:]]}


def _watch(state: Path, now: dt.datetime) -> dict:
    w = _json(state / "data_watch.json")
    try:
        at = dt.datetime.fromisoformat(w["at_utc"])
    except (TypeError, KeyError, ValueError):
        return {"available": False, "reason": "No data check on this machine"}
    markets = []
    for root, m in (w.get("markets") or {}).items():
        state_ = ("closed" if not m.get("open") else "silent" if root in (w.get("silent") or []) else
                  "late" if root in (w.get("late") or []) else "thin" if root in (w.get("thin") or []) else "fine")
        secs = m.get("silent_s") if state_ == "silent" else m.get("late_s") if state_ == "late" else None
        markets.append({"root": root, "state": state_, "minutes": round(secs / 60) if secs else None,
                        "share": round(100 * m["share"]) if state_ == "thin" and m.get("share") is not None else None})
    return {"available": True, "at_utc": w["at_utc"], "stale": (now - at).total_seconds() > WATCH_STALE_S,
            "level": w.get("level"), "line": str(w.get("line") or "").removeprefix("data: "), "markets": markets,
            "refused": len(w.get("refused") or []), "leaving": len(w.get("leaving") or [])}


def _coverage(state: Path) -> dict:
    c = _json(state / "tick_coverage.json")
    if c is None:
        return {"available": False, "reason": "No tick coverage report on this machine"}
    s = c.get("summary") or {}
    roots = {}
    for root, entries in (c.get("roots") or {}).items():
        for e in entries:
            n = roots.setdefault(root, {})
            n[e.get("class")] = n.get(e.get("class"), 0) + 1
    return {"available": True, "at_utc": c.get("generated_at_utc"), "sessions": c.get("sessions_per_root"),
            "classes": s.get("classes") or {}, "filling_hours": (s.get("filling") or {}).get("hole_hours"),
            "until_utc": (s.get("filling") or {}).get("until_utc"), "lost_hours": (s.get("lost") or {}).get("hole_hours"),
            "roots": roots}


def read(state: Path, now: dt.datetime) -> dict:
    """The card's whole answer. Never raises: a missing or odd file is a note."""
    logs = []
    for name, fname in FILES.items():
        try:
            st = (state / fname).stat()
        except OSError:
            continue
        logs.append({"name": name, "label": LOGS[name], "size": st.st_size,
                     "at": dt.datetime.fromtimestamp(st.st_mtime, dt.timezone.utc).isoformat(timespec="seconds")})
    return {"watch": _watch(state, now), "coverage": _coverage(state), "logs": logs}


def run_preopen():
    """tools.preopen_check.run() -- rows (OK|WARN|FAIL, name, detail) -- or None where it cannot run: its power, clock and
    launchd checks are the Mac's, and the server's checkout may not carry tools/."""
    if sys.platform != "darwin":
        return None
    try:
        return importlib.import_module("tools.preopen_check").run()
    except ImportError:
        return None


def register(app, *, state_dir) -> None:
    pre = {"at": 0.0, "checks": None}          # the last pre-open run, shared by every page that asks
    busy = threading.Lock()

    @app.get("/api/health")
    async def health():
        return await asyncio.to_thread(read, state_dir(), dt.datetime.now(dt.timezone.utc))

    @app.get("/api/logs/{name}")
    async def log_tail(name: str, lines: int = LINES_DEFAULT):
        if name not in LOGS:
            raise HTTPException(404, "not a log this page shows")
        got = await asyncio.to_thread(tail, state_dir() / FILES[name], max(1, min(lines, LINES_MAX)))
        if got is None:
            return {"available": False, "name": name, "reason": "No such log on this machine"}
        return {"available": True, "name": name, "label": LOGS[name], **got}

    def _run() -> None:
        if not busy.acquire(blocking=False):
            return                              # another page's run is in flight: its answer lands in the cache
        try:
            rows = run_preopen()
            if rows is None:
                pre.update(at=0.0, checks=None, off=True)
                return
            pre.update(at=time.time(), off=False,
                       checks=[{"level": LEVEL[lvl], "label": n, "detail": d} for lvl, n, d in rows if n not in PRE_DROP])
        except Exception as e:  # noqa: BLE001 -- one failed run is a note on the card, never a broken page
            pre.update(at=time.time(), off=False, checks=[{"level": "warn", "label": "Pre-open check",
                                                           "detail": f"could not run: {type(e).__name__}: {e}"}])
        finally:
            busy.release()

    @app.get("/api/preopen-check")
    async def preopen_check(run: int = 0):
        """The last run (never starts one) -- or, with run=1, a new run unless one finished in the last PRE_GAP_S s."""
        if run and time.time() - pre["at"] > PRE_GAP_S:
            await asyncio.to_thread(_run)
        if pre.get("off"):
            return {"available": False, "reason": "Not on this machine: the pre-open check reads the Mac's clock, power and services"}
        if pre["checks"] is None:
            return {"available": True, "at": None, "age_s": None, "checks": []}
        worst = max((c["level"] for c in pre["checks"]), key=("ok", "warn", "bad").index, default="ok")
        return {"available": True, "at": dt.datetime.fromtimestamp(pre["at"], dt.timezone.utc).isoformat(timespec="seconds"),
                "age_s": round(time.time() - pre["at"]), "worst": worst, "checks": pre["checks"]}
