"""Parameter heat-map grids: one strategy, 2 or 3 inputs with value lists, at most 60 cells,
on the research window 2021-01-01 -> 2024-12-31 ONLY (forced here, server-side).

Every cell is an ordinary tester run -- the request `runner.validate()` builds for a single run
with the same params, executed by the same `runner exec` child (`--no-lock`: the grid's own
2-worker pool bounds it, not the one-run flock) -- so a cell's report IS the single run's.

    <base> = homebase/.state/tester
      looks.json                 {strategy: finished grid cells ever run}   (the looks counter)
      grids/<id>/grid.json       the grid: axes, base inputs, costs, per-cell status + summary
      grids/<id>/cells/NN/       a run dir exactly as runs/<id>/ (request, status, run, trades, ...)

Looks: a cell counts once, when it finishes with numbers (status done) -- a cancelled or
never-started cell was never seen. At a 5% level ~looks/20 cells read "significant" by luck.
The chart service owns a GridManager: cells go FIFO through a pool of WORKERS threads, each
waiting on its own child process, so the service's event loop never runs a backtest. A cell
starts only once it holds a machine-wide backtest slot (slots.py: 2 at once shared with single
runs, none starting 09:20-09:35 ET on weekdays -- the grid then reads `paused`).
"""
from __future__ import annotations

import copy
import datetime as dt
import itertools
import secrets
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path

from .. import strategies
from ..paths import repo_root
from . import runner
from .discipline import DisciplineError, parse_range
from .runner import RUN_ID, _now, read_json, write_json
from .slots import QUIET_MSG, Slots
from .tape import ARCHIVE, CACHE

MAX_CELLS = 60
WORKERS = 2
FIELDS = {"strategy", "inputs", "axes", "range", "qty", "commission", "slippage_ticks", "capital", "prop_rules"}
RESEARCH_ONLY = "the heat-map runs on the research window 2021–2024 only"
SUMMARY_KEYS = ("net_profit", "sharpe", "trades", "win_rate", "profit_factor", "max_drawdown", "t_stat",
                "avg_trade")
FINAL = {"done", "error", "cancelled"}
INTERRUPTED = "interrupted (the chart service restarted)"


def expand(axes: list[dict]) -> list[dict]:
    """[{key, values}, ...] -> the cells [{i, params, coords}], the last axis varying fastest."""
    ranges = [range(len(a["values"])) for a in axes]
    return [{"i": i, "params": {a["key"]: a["values"][j] for a, j in zip(axes, coords)}, "coords": list(coords)}
            for i, coords in enumerate(itertools.product(*ranges))]


def _research_only(body: dict) -> None:
    if "holdout" in body:
        raise DisciplineError(f"{RESEARCH_ONLY} (no holdout)")
    rng = body.get("range")
    if rng is None:
        return
    if not (isinstance(rng, dict) and rng.get("kind") == "research" and set(rng) <= {"kind"}):
        raise DisciplineError(RESEARCH_ONLY)


def validate_grid(body) -> dict:
    """The grid as it will run: resolved axes + one single-run request per cell. ValueError
    (DisciplineError for the window) with a message for the page on anything refused."""
    if not isinstance(body, dict):
        raise ValueError("the body is a JSON object")
    _research_only(body)
    extra = sorted(set(body) - FIELDS)
    if extra:
        raise ValueError(f"unknown field(s): {', '.join(extra)}")
    cls = strategies.get(str(body.get("strategy", "")))
    base = body.get("inputs")
    if base is not None and not isinstance(base, dict):
        raise ValueError("inputs: a JSON object")
    axes_in = body.get("axes")
    if not isinstance(axes_in, list) or not 2 <= len(axes_in) <= 3:
        raise ValueError("axes: 2 or 3 parameters, each {key, values}")
    schema = {i.key: i for i in cls.inputs()}
    keys = [a.get("key") if isinstance(a, dict) else None for a in axes_in]
    for k in keys:
        if k not in schema:
            raise ValueError(f"unknown input {k!r}")
    if len(set(keys)) != len(keys):
        raise ValueError("axes: a parameter appears twice")
    base = {k: v for k, v in (base or {}).items() if k not in keys}
    axes = []
    for a in axes_in:
        k, vals = a["key"], a.get("values")
        if not isinstance(vals, list) or not vals:
            raise ValueError(f"{k}: a list of values")
        resolved = [strategies.resolve_inputs(cls.inputs(), {**base, k: v})[k] for v in vals]
        for j, v in enumerate(resolved):
            if v in resolved[:j]:
                raise ValueError(f"{k}: {v!r} twice")
        axes.append({"key": k, "label": schema[k].label, "type": schema[k].type, "values": resolved})
    n = 1
    for a in axes:
        n *= len(a["values"])
    if n > MAX_CELLS:
        raise ValueError(f"{n} cells: a grid is at most {MAX_CELLS}")
    common = {k: body[k] for k in ("qty", "commission", "slippage_ticks", "capital", "prop_rules") if k in body}
    cells = []
    for c in expand(axes):
        req = runner.validate({"strategy": cls.id, "inputs": {**base, **c["params"]}, "range": {"kind": "research"},
                               **common})
        cells.append({**c, "req": req})
    first = cells[0]["req"]
    return {"strategy": cls.id, "strategy_name": cls.name, "axes": axes,
            "base": {k: v for k, v in first["inputs"].items() if k not in keys},
            "range": parse_range({"kind": "research"}).to_dict(),
            **{k: first[k] for k in ("qty", "commission", "slippage_ticks", "capital", "prop_rules")},
            "cells": cells}


# ---------------------------------------------------------------- the looks counter

def read_looks(path: Path) -> dict[str, int]:
    d = read_json(Path(path), {})
    if not isinstance(d, dict):
        return {}
    return {k: v for k, v in d.items() if isinstance(v, int) and not isinstance(v, bool) and v >= 0}


def add_look(path: Path, strategy: str, n: int = 1) -> int:
    """+n looks for `strategy`; the new total. Callers serialize (GridManager holds its lock)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    looks = read_looks(path)
    looks[strategy] = looks.get(strategy, 0) + n
    write_json(path, looks)
    return looks[strategy]


# ---------------------------------------------------------------- the manager

def _summary(run: dict | None) -> dict:
    rep = (run or {}).get("report") or {}
    allc = (rep.get("summary") or {}).get("all") or {}
    cov = (run or {}).get("coverage") or {}
    return {**{k: allc.get(k) for k in SUMMARY_KEYS}, "skipped_by_error": rep.get("skipped_by_error", 0),
            "sessions": cov.get("sessions"), "used": cov.get("used")}


class GridManager:
    """The chart service's handle on heat-map grids (thread-safe; no asyncio)."""

    def __init__(self, base: Path, *, archive: Path = ARCHIVE, cache: Path = CACHE,
                 python: str = sys.executable, workers: int = WORKERS, slots: Slots | None = None):
        self.base, self.grids = Path(base), Path(base) / "grids"
        self.looks_path = self.base / "looks.json"
        self.archive, self.cache, self.python, self.workers = Path(archive), Path(cache), python, workers
        self.grids.mkdir(parents=True, exist_ok=True)
        self.slots = slots or Slots(self.base / "slots")
        self._q: deque[tuple[str, int]] = deque()
        self._procs: dict[tuple[str, int], subprocess.Popen] = {}
        self._live: dict[str, dict] = {}          # grids this process started (the rest are read from disk)
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._threads: list[threading.Thread] = []
        self._stopping = False
        self._recover()

    def _recover(self) -> None:
        """Grids a previous service process left unfinished are dead now."""
        for p in self.grids.glob("*/grid.json"):
            g = read_json(p, {}) or {}
            if g.get("status") in ("queued", "running"):
                for c in g.get("cells", []):
                    if c.get("status") == "queued":
                        c["status"] = "cancelled"
                    elif c.get("status") == "running":
                        c.update(status="error", error=INTERRUPTED)
                g.update(status="cancelled", error=INTERRUPTED, updated=_now())
                write_json(p, g)

    def dir(self, gid: str) -> Path:
        if not RUN_ID.match(gid or "") or not (self.grids / gid / "grid.json").is_file():
            raise KeyError(gid)
        return self.grids / gid

    def all_looks(self) -> dict[str, int]:
        with self._lock:
            return read_looks(self.looks_path)

    def submit(self, body) -> str:
        g = validate_grid(body)
        gid = f"{dt.datetime.now():%Y%m%d-%H%M%S}-{g['strategy']}-{secrets.token_hex(2)}"
        d = self.grids / gid
        cells = []
        for c in g.pop("cells"):
            cdir = d / "cells" / f"{c['i']:02d}"
            cdir.mkdir(parents=True)
            rid = f"{gid}-c{c['i']:02d}"
            write_json(cdir / "request.json", {**c["req"], "id": rid, "created": _now()})
            write_json(cdir / "status.json", {"id": rid, "status": "queued", "phase": "queued", "done": 0,
                                              "total": 0, "updated": _now()})
            cells.append({"i": c["i"], "params": c["params"], "coords": c["coords"], "status": "queued"})
        state = {"id": gid, **g, "created": _now(), "updated": _now(), "status": "queued",
                 "total": len(cells), "done": 0, "cells": cells}
        with self._cv:
            self._live[gid] = state
            self._save(gid)
            self._q.extend((gid, c["i"]) for c in cells)
            while len(self._threads) < self.workers:
                t = threading.Thread(target=self._work, name=f"tester-grid-{len(self._threads)}", daemon=True)
                self._threads.append(t)
                t.start()
            self._cv.notify_all()
        return gid

    def _save(self, gid: str) -> None:          # under the lock
        st = self._live[gid]
        st["done"] = sum(1 for c in st["cells"] if c["status"] in FINAL)
        st["updated"] = _now()
        write_json(self.grids / gid / "grid.json", st)

    def _view(self, gid: str) -> dict:        # under the lock
        st = self._live.get(gid)
        st = copy.deepcopy(st) if st is not None else (read_json(self.grids / gid / "grid.json", {}) or {})
        st["looks"] = read_looks(self.looks_path).get(st.get("strategy"), 0)
        if (st.get("status") not in FINAL and any(c.get("status") == "queued" for c in st.get("cells", []))
                and self.slots.quiet()):
            st["paused"] = QUIET_MSG
        return st

    def status(self, gid: str) -> dict:
        self.dir(gid)
        with self._lock:
            return self._view(gid)

    def list(self, limit: int = 20) -> list[dict]:
        out = []
        for d in sorted((p for p in self.grids.iterdir() if RUN_ID.match(p.name)), key=lambda p: p.name,
                        reverse=True)[:limit]:
            with self._lock:
                g = copy.deepcopy(self._live[d.name]) if d.name in self._live else read_json(d / "grid.json", {})
            if not g:
                continue
            out.append({"id": g["id"], "strategy": g.get("strategy"), "created": g.get("created"),
                        "status": g.get("status"), "done": g.get("done"), "total": g.get("total"),
                        "axes": [a["key"] for a in g.get("axes", [])]})
        return out

    def cell_bundle(self, gid: str, i: int) -> dict:
        cdir = self.dir(gid) / "cells" / f"{int(i):02d}"
        if not cdir.is_dir():
            raise KeyError(f"{gid}/{i}")
        return runner.read_bundle(cdir)

    def cancel(self, gid: str) -> dict:
        self.dir(gid)
        with self._cv:
            st = self._live.get(gid)
            if st is None or st["status"] in FINAL:
                return self._view(gid)
            self._q = deque(x for x in self._q if x[0] != gid)
            procs = [p for (g, _), p in self._procs.items() if g == gid]
            for c in st["cells"]:
                if c["status"] in ("queued", "running"):
                    c["status"] = "cancelled"
            st["status"] = "cancelled"
            self._save(gid)
        for p in procs:
            _stop(p)
        return self.status(gid)

    def shutdown(self) -> None:
        """Chart-service shutdown: stop every child this manager launched; nothing is orphaned."""
        with self._cv:
            self._stopping = True
            live = [g for g, st in self._live.items() if st["status"] not in FINAL]
            self._cv.notify_all()
        for gid in live:
            self.cancel(gid)

    def _work(self) -> None:
        while True:
            with self._cv:
                while not self._q and not self._stopping:
                    self._cv.wait()
                if self._stopping:
                    return
            # a slot first (the global cap, the QUIET window); let go if the queue empties meanwhile
            slot = self.slots.acquire(cancelled=self._idle)
            if slot is None:
                continue
            with self._cv:
                if self._stopping or not self._q:
                    slot.close()
                    continue
                gid, i = self._q.popleft()
                st = self._live[gid]
                cell = st["cells"][i]
                cdir = self.grids / gid / "cells" / f"{i:02d}"
                cell["status"] = "running"
                st["status"] = "running"
                self._save(gid)
                log = open(cdir / "log.txt", "ab")
                try:
                    proc = subprocess.Popen(
                        [self.python, "-m", "homebase.backtest.runner", "exec", str(cdir), "--no-lock",
                         "--archive", str(self.archive), "--cache", str(self.cache)],
                        cwd=repo_root(), stdout=log, stderr=subprocess.STDOUT)
                except OSError as e:
                    slot.close()
                    log.close()
                    cell.update(status="error", error=f"could not start the runner: {e}")
                    self._finish_grid(st)
                    self._save(gid)
                    continue
                self._procs[(gid, i)] = proc
            try:
                code = proc.wait()
            finally:
                slot.close()
            log.close()
            rs = read_json(cdir / "status.json", {}) or {}
            run = read_json(cdir / "run.json") if rs.get("status") == "done" else None
            with self._cv:
                self._procs.pop((gid, i), None)
                if run is not None:                 # it finished with numbers (even if a cancel raced it)
                    cell.update(status="done", summary=_summary(run))
                    add_look(self.looks_path, st["strategy"])
                elif cell["status"] != "cancelled":
                    tail = (cdir / "log.txt").read_text(errors="replace")[-600:]
                    cell.update(status="error", error=rs.get("error") or f"runner exited {code}: {tail}")
                self._finish_grid(st)
                self._save(gid)

    def _idle(self) -> bool:
        with self._lock:
            return self._stopping or not self._q

    @staticmethod
    def _finish_grid(st: dict) -> None:           # under the lock
        if st["status"] != "cancelled" and all(c["status"] in FINAL for c in st["cells"]):
            st["status"] = "done"


def _stop(proc) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
