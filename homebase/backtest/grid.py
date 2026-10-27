"""Parameter heat-map grids: one strategy, 2 or 3 inputs with value lists, at most `max_cells`
(the page's own Max cells box; 120 by default -- hm40 x 3 values -- 400 the hard ceiling),
over whatever window the request names (the range picker's preset; the build days by default).

Every cell is an ordinary tester run -- the request `runner.validate()` builds for a single run
with the same params, executed by the same `runner exec` child (`--no-lock`: the grid's own
2-worker pool bounds it, not the one-run flock) -- so a cell's report IS the single run's.

    <shared> = slots.shared_dir() = ~/.homebase/tester   (per machine: every checkout counts here)
      looks.json                 {strategy: finished grid cells ever run}   (the looks counter)
    <base> = homebase/.state/tester                     (per checkout)
      grids/<id>/grid.json       the grid: axes, base inputs, costs, per-cell status + summary
      grids/<id>/cells/NN/       a run dir exactly as runs/<id>/ (request, status, run, trades, ...)

Looks: a cell counts once, when it finishes with numbers (status done) -- a cancelled or
never-started cell was never seen. At a 5% level ~looks/20 cells read "significant" by luck.
The counter is never reset silently: a looks.json that does not parse (or holds anything but
{name: count >= 0}) is copied to looks.json.bak and REFUSED -- no grid starts until a person
fixes or removes it. Writes are fsync'd tmp + rename under a cross-process flock (looks.lock).
A checkout-local <base>/looks.json from before the counter moved is summed in once and renamed
looks.json.migrated.
The chart service owns a GridManager: cells go FIFO through a pool of WORKERS threads, each
waiting on its own child process, so the service's event loop never runs a backtest. A cell
starts only once it holds a machine-wide backtest slot (slots.py: 2 at once shared with single
runs, none starting in a quiet window of the tester's override file -- the grid then reads `paused`).
"""
from __future__ import annotations

import copy
import datetime as dt
import fcntl
import itertools
import json
import os
import shutil
import secrets
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path

from .. import draftstore, strategies
from . import controls as ctlmod, drafthost, runner
from .discipline import WF_OOS_ONLY, parse_range
from .runner import RUN_ID, _now, _settled, _stamp, read_json, write_json
from .slots import NO_BACKTESTS, QUIET_MSG, Slots, backtests_off, shared_dir
from .tape import ARCHIVE, CACHE

DEFAULT_MAX_CELLS = 120     # what a body without Max cells gets: the 40 hm40 exit cells x 3 values
HARD_MAX_CELLS = 400        # ... and the most it, or any other client, may ask for
WORKERS = 4                 # cell threads; each still needs a machine slot (slots.cap_at)
FIELDS = {"strategy", "inputs", "axes", "range", "qty", "commission", "slippage_ticks", "capital",
          "max_cells", "prop_rules", "controls"}
CTL = "ctl."                # an axis key that names a RUN SETTING (backtest/controls.py) rather than a strategy input
SUMMARY_KEYS = ("net_profit", "sharpe", "trades", "win_rate", "profit_factor", "max_drawdown", "t_stat",
                "avg_trade")
FINAL = {"done", "error", "cancelled"}
INTERRUPTED = "interrupted (the chart service restarted)"

# hm40 (the owner, 2026-10-20): 8 stops x 5 targets, ATR stops first, targets inner. ATR = 14 bars of the strategy's own
# bar size; "own" = x the strategy's own stop distance, floored at 0.25 x that ATR, then 2 ticks.
STOP = "stop"               # the virtual run setting behind the `ctl.stop` axis: "atr:<x>" or "own:<x>"
HM40_AXES = [{"key": "ctl.stop", "values": ["atr:0.5", "atr:1", "atr:1.5", "atr:2", "own:0.5", "own:1", "own:1.5", "own:2"]},
             {"key": "ctl.target_rr", "values": [0.5, 0.75, 1, 1.5, 2]}]


def hm40_axes(cls) -> list[dict]:
    """HM40_AXES for this strategy: its 20 ATR cells only when it sets no stop of its own (never own cells turned into ATR)."""
    stops = HM40_AXES[0]["values"] if getattr(cls, "own_stop", False) else HM40_AXES[0]["values"][:4]
    return [{"key": HM40_AXES[0]["key"], "values": list(stops)}, dict(HM40_AXES[1], values=list(HM40_AXES[1]["values"]))]


def stop_value(v) -> str:
    """A `ctl.stop` value, as "atr:<x>" (x the ATR) or "own:<x>" (x the strategy's own stop), x written short."""
    mode, _, x = v.partition(":") if isinstance(v, str) else ("", "", "")
    field = {"atr": "stop_atr", "own": "stop_own_mult"}.get(mode)
    try:
        num = float(x)
    except ValueError:
        num = None
    if field is None or num is None or num != num:
        raise ValueError(f"Stop: {v!r} is not atr:<x> or own:<x>")
    lo, hi = max(ctlmod.SPEC[field][2], 1e-9), ctlmod.SPEC[field][3]
    if not lo <= num <= hi:
        raise ValueError(f"Stop: {v!r} must be within [{ctlmod.SPEC[field][2]:g}, {hi:g}]")
    return f"{mode}:{num:g}"


def stop_controls(v: str, atr_minutes: int = 0) -> dict:
    """The run settings of one `ctl.stop` value (the controller's rulings for hm40, 2026-10-20): the ATR of the strategy's
    own bar (0), or of 5-minute bars for a strategy with no single bar size."""
    mode, _, x = stop_value(v).partition(":")
    if mode == "atr":
        return {"stop_mode": "atr", "stop_atr": float(x), "atr_minutes": atr_minutes, "atr_period": 14}
    return {"stop_mode": "own", "stop_own_mult": float(x), "own_floor": True, "atr_minutes": atr_minutes, "atr_period": 14}


def stop_atr_minutes(cls) -> int:
    return 0 if getattr(cls, "bar_minutes", 0) else 5


def _max_cells(v) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= HARD_MAX_CELLS:
        raise ValueError(f"max_cells: a whole number 1 to {HARD_MAX_CELLS}")
    return v


def expand(axes: list[dict]) -> list[dict]:
    """[{key, values}, ...] -> the cells [{i, params, coords}], the last axis varying fastest."""
    ranges = [range(len(a["values"])) for a in axes]
    return [{"i": i, "params": {a["key"]: a["values"][j] for a, j in zip(axes, coords)}, "coords": list(coords)}
            for i, coords in enumerate(itertools.product(*ranges))]


def _ctl_cells(base_ctl: dict, params: dict, atr_minutes: int = 0) -> dict:
    """One cell's run settings: the base, then the cell's own axis values. A number that only means something under
    one mode (stop points under "fixed") switches that mode on unless the base or another axis already picked
    one; a mode already set to something else is refused, in words."""
    raw = dict(base_ctl)
    chosen = {k[len(CTL):]: v for k, v in params.items() if k.startswith(CTL)}
    stop = chosen.pop(STOP, None)
    raw.update(chosen)
    if stop is not None:                        # the stop axis sets the whole stop, whatever the base said
        raw.update(stop_controls(stop, atr_minutes))
    for num, (mode, name) in ctlmod.IMPLIES.items():
        if num not in chosen or not chosen[num] or mode in chosen:
            continue
        cur = raw.get(mode, "own")
        if cur in ("own", name):
            raw[mode] = name
        else:
            raise ValueError(f"{ctlmod.LABELS[num]}: needs {ctlmod.LABELS[mode].lower()} = {name}, "
                             f"but it is set to {cur}")
    return raw


def validate_grid(body, min_axes: int = 2) -> dict:
    """The grid as it will run: resolved axes + one single-run request per cell, all over the
    body's own range (the build days when it names none). An axis is a strategy input (its own key) or a
    run setting (`ctl.<field>`, backtest/controls.py); `controls` in the body are the settings every cell shares.
    ValueError (DisciplineError for a malformed window) with a message for the page on anything refused."""
    if not isinstance(body, dict):
        raise ValueError("the body is a JSON object")
    extra = sorted(set(body) - FIELDS)
    if extra:
        raise ValueError(f"unknown field(s): {', '.join(extra)}")
    draft = drafthost.snapshot(body.get("strategy")) if draftstore.is_draft_id(body.get("strategy")) else None
    cls = draft[0] if draft else strategies.get(str(body.get("strategy", "")))   # a draft: its STUB, never its code
    base = body.get("inputs")
    if base is not None and not isinstance(base, dict):
        raise ValueError("inputs: a JSON object")
    axes_in = body.get("axes", [] if min_axes == 0 else None)
    if not isinstance(axes_in, list) or not min_axes <= len(axes_in) <= 3:
        raise ValueError("axes: 2 or 3 parameters, each {key, values}" if min_axes else "axes: up to 3 parameters, each {key, values}")
    schema = {i.key: i for i in cls.inputs()}
    keys = [a.get("key") if isinstance(a, dict) else None for a in axes_in]
    for k in keys:
        if isinstance(k, str) and k.startswith(CTL):
            if k[len(CTL):] not in ctlmod.SPEC and k[len(CTL):] != STOP:
                raise ValueError(f"unknown run setting {k[len(CTL):]!r}")
        elif k not in schema:
            raise ValueError(f"unknown input {k!r}")
    if len(set(keys)) != len(keys):
        raise ValueError("axes: a parameter appears twice")
    base = {k: v for k, v in (base or {}).items() if k not in keys}
    base_ctl_in = body.get("controls")
    if base_ctl_in is not None and not isinstance(base_ctl_in, dict):
        raise ValueError("controls: a JSON object")
    base_ctl = {}
    for k, v in (base_ctl_in or {}).items():          # each field alone: a mode may still be waiting for its axis number
        if k not in ctlmod.SPEC:
            raise ValueError(f"controls: unknown field(s): {k}")
        base_ctl[k] = ctlmod.coerce(k, v)
    base_ctl = {k: v for k, v in base_ctl.items() if f"{CTL}{k}" not in keys}
    axes = []
    for a in axes_in:
        k, vals = a["key"], a.get("values")
        if not isinstance(vals, list) or not vals:
            raise ValueError(f"{k}: a list of values")
        if k == CTL + STOP:
            resolved = [stop_value(v) for v in vals]
            atr = "ATR" if stop_atr_minutes(cls) == 0 else f"ATR({stop_atr_minutes(cls)}m)"
            if len(set(resolved)) != len(resolved):
                raise ValueError("Stop: a value twice")
            if not getattr(cls, "own_stop", False) and any(v.startswith("own:") for v in resolved):
                raise ValueError(f"{cls.name or cls.id} sets no stop of its own: its heat map takes the ATR stops only (atr:<x>)")
            axes.append({"key": k, "label": "Stop", "type": "choice", "ctl": True, "values": resolved,
                         "value_labels": [f"{atr if v.startswith('atr') else 'own'} x{v.partition(':')[2]}" for v in resolved]})
            continue
        if k.startswith(CTL):
            f = k[len(CTL):]
            resolved = [ctlmod.coerce(f, v) for v in vals]
            for j, v in enumerate(resolved):
                if v in resolved[:j]:
                    raise ValueError(f"{ctlmod.LABELS[f]}: {v!r} twice")
            axes.append({"key": k, "label": ctlmod.LABELS[f], "type": ctlmod.SPEC[f][0], "ctl": True,
                         "values": resolved, "value_labels": [ctlmod.value_label(f, v) for v in resolved]})
            continue
        resolved = [strategies.resolve_inputs(cls.inputs(), {**base, k: v})[k] for v in vals]
        for j, v in enumerate(resolved):
            if v in resolved[:j]:
                raise ValueError(f"{k}: {v!r} twice")
        axes.append({"key": k, "label": schema[k].label, "type": schema[k].type, "values": resolved})
    cap = _max_cells(body.get("max_cells", DEFAULT_MAX_CELLS))
    n = 1
    for a in axes:
        n *= len(a["values"])
    if n > cap:
        raise ValueError(f"{n} cells: this grid is capped at {cap} (raise Max cells, up to {HARD_MAX_CELLS})")
    common = {k: body[k] for k in ("qty", "commission", "slippage_ticks", "capital", "prop_rules") if k in body}
    rng = parse_range(body.get("range"))         # DisciplineError on a malformed window; nothing else refuses
    if rng.kind == "wf_oos":
        raise ValueError(WF_OOS_ONLY)
    cells = []
    for c in expand(axes):
        sreq = {"strategy": cls.id, "inputs": {**base, **{k: v for k, v in c["params"].items() if not k.startswith(CTL)}},
                "range": body.get("range"), **common}
        raw_ctl = _ctl_cells(base_ctl, c["params"], stop_atr_minutes(cls))
        if raw_ctl:
            sreq["controls"] = raw_ctl
        try:
            req = runner.validate(sreq, draft=draft)
        except ValueError as e:
            if raw_ctl and str(e).startswith("controls"):    # name the cell, so a person can tell which one
                where = ", ".join(f"{a['label']} {a['value_labels'][j] if a.get('value_labels') else a['values'][j]}"
                                  for a, j in zip(axes, c["coords"]))
                raise ValueError(f"{e} (cell: {where})") from None
            raise
        cells.append({**c, "req": req})
    first = cells[0]["req"]
    return {"strategy": cls.id, "strategy_name": cls.name, "axes": axes,
            "base": {k: v for k, v in first["inputs"].items() if k not in keys},
            "controls": base_ctl,
            "range": rng.to_dict(), "max_cells": cap,
            **{k: first[k] for k in ("qty", "commission", "slippage_ticks", "capital", "prop_rules")},
            "cells": cells}


# ---------------------------------------------------------------- the looks counter

class LooksCorrupt(ValueError):
    """looks.json exists but is not {name: count >= 0}. Shown to the user; never auto-repaired."""


def _valid_looks(d) -> bool:
    return isinstance(d, dict) and all(isinstance(k, str) and type(v) is int and v >= 0 for k, v in d.items())


def read_looks(path: Path) -> dict[str, int]:
    """{} when the file does not exist; LooksCorrupt (after keeping a .bak copy) when it does not parse."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {}
    try:
        d = json.loads(raw)
    except ValueError:
        d = None
    if not _valid_looks(d):
        bak = path.with_name(path.name + ".bak")
        shutil.copyfile(path, bak)
        raise LooksCorrupt(f"the looks counter {path} is unreadable (kept a copy as {bak.name}): fix or "
                           "remove it -- it is never reset silently, and no grid runs until then")
    return d


def _write_durable(path: Path, data) -> None:
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, separators=(",", ":"), sort_keys=True))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    dfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


class _looks_lock:
    """The cross-process lock for a looks.json read-modify-write (every checkout shares the file)."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(path.with_name("looks.lock"), "a")

    def __enter__(self):
        fcntl.flock(self.fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        self.fh.close()


def add_look(path: Path, strategy: str, n: int = 1) -> int:
    """+n looks for `strategy`; the new total. LooksCorrupt (file untouched) when it is unreadable."""
    path = Path(path)
    with _looks_lock(path):
        looks = read_looks(path)
        looks[strategy] = looks.get(strategy, 0) + n
        _write_durable(path, looks)
        return looks[strategy]


def migrate_looks(local: Path, shared: Path) -> bool:
    """Sum a checkout-local looks.json into the shared one, once (the local file is renamed
    .migrated). False (both files untouched) when either is unreadable."""
    local, shared = Path(local), Path(shared)
    if not local.exists():
        return False
    with _looks_lock(shared):
        try:
            mine, theirs = read_looks(local), read_looks(shared)
        except LooksCorrupt:
            return False
        for k, v in mine.items():
            theirs[k] = theirs.get(k, 0) + v
        _write_durable(shared, theirs)
        os.replace(local, local.with_name(local.name + ".migrated"))
    return True


# ---------------------------------------------------------------- the manager

def _summary(run: dict | None) -> dict:
    rep = (run or {}).get("report") or {}
    allc = (rep.get("summary") or {}).get("all") or {}
    cov = (run or {}).get("coverage") or {}
    return {**{k: allc.get(k) for k in SUMMARY_KEYS}, "skipped_by_error": rep.get("skipped_by_error", 0),
            "sessions": cov.get("sessions"), "used": cov.get("used")}


_ON_FILE: dict = {}                 # (path, fn) -> (the file's stamp, fn's answer): GridManager._on_file
_ON_FILE_LOCK = threading.Lock()


def _grid_row(g: dict):
    """A grid's /grids row, None for an empty grid.json."""
    if not g:
        return None
    return {"id": g["id"], "strategy": g.get("strategy"), "created": g.get("created"),
            "status": g.get("status"), "done": g.get("done"), "total": g.get("total"),
            "axes": [a["key"] for a in g.get("axes", [])]}


class GridManager:
    """The chart service's handle on heat-map grids (thread-safe; no asyncio).

    Subclass hooks (walkforward.WalkForwardManager): SUBDIR (where its jobs live), COUNT_CELL_LOOKS
    (a heat-map cell is a look the moment it finishes; a walk-forward counts its own), _validate,
    _cell_finished / _cell_summary (per finished cell), _finish_grid and _after_cell (the job's end)."""

    SUBDIR = "grids"
    COUNT_CELL_LOOKS = True

    def __init__(self, base: Path, *, archive: Path = ARCHIVE, cache: Path = CACHE,
                 python: str = sys.executable, workers: int = WORKERS, slots: Slots | None = None,
                 shared: Path | None = None):
        self.base, self.grids = Path(base), Path(base) / self.SUBDIR
        self.shared = Path(shared) if shared is not None else shared_dir()
        self.looks_path = self.shared / "looks.json"
        self.archive, self.cache, self.python, self.workers = Path(archive), Path(cache), python, workers
        self.grids.mkdir(parents=True, exist_ok=True)
        self.slots = slots or Slots(self.shared / "slots")
        migrate_looks(self.base / "looks.json", self.looks_path)
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
            if g.get("status") not in FINAL:
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

    def _validate(self, body) -> dict:
        return validate_grid(body)

    def submit(self, body) -> str:
        if backtests_off():                    # heat maps and walk-forwards (WalkForwardManager) too
            raise ValueError(NO_BACKTESTS)
        g = self._validate(body)
        read_looks(self.looks_path)            # LooksCorrupt (a ValueError -> 400): no grid runs uncounted
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
        try:
            st["looks"] = read_looks(self.looks_path).get(st.get("strategy"), 0)
        except LooksCorrupt as e:
            st["looks"], st["looks_error"] = None, str(e)
        if (st.get("status") not in FINAL and any(c.get("status") == "queued" for c in st.get("cells", []))
                and self.slots.quiet()):
            st["paused"] = QUIET_MSG
        return st

    def status(self, gid: str) -> dict:
        self.dir(gid)
        with self._lock:
            return self._view(gid)

    @staticmethod
    def _on_file(path: Path, fn):
        """fn(the JSON at `path`, {} when it does not read), kept until the file changes (its stamp, taken before the read;
        a file there that did not read, or written in the last 2 s, is never kept)."""
        stamp, key = _stamp(path), (str(path), fn.__module__, fn.__qualname__)
        with _ON_FILE_LOCK:
            hit = _ON_FILE.get(key)
        if hit is not None and hit[0] == stamp:
            return copy.deepcopy(hit[1])
        got = read_json(path, None)
        val = fn(got or {})
        if (got is not None or stamp is None) and _settled(stamp):
            with _ON_FILE_LOCK:
                _ON_FILE[key] = (stamp, copy.deepcopy(val))
        return val

    def list(self, limit: int = 20) -> list[dict]:
        out = []
        for d in sorted((p for p in self.grids.iterdir() if RUN_ID.match(p.name)), key=lambda p: p.name,
                        reverse=True)[:limit]:
            with self._lock:
                row = _grid_row(copy.deepcopy(self._live[d.name])) if d.name in self._live else \
                    self._on_file(d / "grid.json", _grid_row)
            if row is not None:
                out.append(row)
        return out

    def cell_dir(self, gid: str, i: int) -> Path:
        cdir = self.dir(gid) / "cells" / f"{int(i):02d}"
        if not cdir.is_dir():
            raise KeyError(f"{gid}/{i}")
        return cdir

    def cell_bundle(self, gid: str, i: int, plots: bool = True) -> dict:
        return runner.read_bundle(self.cell_dir(gid, i), plots)

    def cell_bundle_bytes(self, gid: str, i: int) -> bytes:
        return runner.read_bundle_bytes(self.cell_dir(gid, i))

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
            # a slot first (the global cap, a quiet window of the override file); let go if the queue empties meanwhile
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
                st.setdefault("started", _now())
                self._save(gid)
                try:              # the child holds the slot too; a DRAFT's runs sandboxed (runner.launch)
                    proc = runner.launch(cdir, self.python, self.archive, self.cache, slot, ("--no-lock",))
                except (OSError, ValueError) as e:
                    slot.close()
                    cell.update(status="error", error=f"could not start the runner: {e}")
                    self._finish_grid(st)
                    self._save(gid)
                    after = self._after_cell(gid, st)
                    if after is not None:
                        threading.Thread(target=after, daemon=True).start()
                    continue
                self._procs[(gid, i)] = proc
            try:
                code, timed_out = runner.wait_proc(proc)
            finally:
                slot.close()                    # always: a killed draft's whole group is gone by now
                runner.finish_proc(proc)
            rs = read_json(cdir / "status.json", {}) or {}
            if timed_out:
                rs = {**rs, "status": "error", "error": timed_out}
            run = read_json(cdir / "run.json") if rs.get("status") == "done" else None
            hook_error = None
            if run is not None:
                try:
                    self._cell_finished(cdir, run)
                except Exception as e:  # noqa: BLE001 -- the cell reads as an error, never a silent gap
                    hook_error = f"{type(e).__name__}: {e}"
            with self._cv:
                self._procs.pop((gid, i), None)
                if run is not None and hook_error is None:   # it finished with numbers (even if a cancel raced it)
                    cell.update(status="done", summary=self._cell_summary(run))
                    if self.COUNT_CELL_LOOKS:
                        try:
                            add_look(self.looks_path, st["strategy"])
                        except LooksCorrupt as e:   # refused at submit; broken mid-grid: say so, never reset
                            st["looks_error"] = str(e)
                elif hook_error is not None:
                    cell.update(status="error", error=hook_error)
                elif cell["status"] != "cancelled":
                    tail = (cdir / "log.txt").read_text(errors="replace")[-600:]
                    cell.update(status="error", error=rs.get("error") or f"runner exited {code}: {tail}")
                self._finish_grid(st)
                self._save(gid)
                after = self._after_cell(gid, st)
            if after is not None:
                after()

    def _idle(self) -> bool:
        with self._lock:
            return self._stopping or not self._q

    @staticmethod
    def _finish_grid(st: dict) -> None:           # under the lock
        if st["status"] != "cancelled" and all(c["status"] in FINAL for c in st["cells"]):
            st["status"] = "done"

    # ---- subclass hooks (the heat-map's own behaviour below)

    def _cell_finished(self, cdir: Path, run: dict) -> None:
        """A cell finished with numbers (a worker thread, outside the lock)."""

    def _cell_summary(self, run: dict) -> dict:
        return _summary(run)

    def _after_cell(self, gid: str, st: dict):   # under the lock
        """A callable to run once the lock is released (None: nothing)."""
        return None


def _stop(proc) -> None:
    runner.stop_proc(proc)          # a draft's whole process group; a built-in's child as before
