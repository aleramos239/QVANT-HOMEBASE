"""Tester runs: validated, each in its OWN process, into a run bundle.

    <base> = homebase/.state/tester
      spends.jsonl              the record of runs that read the test days (discipline.py; never a gate)
      runs/.lock                held (flock) only by a `runner exec` started by hand without --no-lock
      runs/<id>/request.json    the validated request
      runs/<id>/status.json     {status, phase, done, total, error?, pid?, updated}
      runs/<id>/log.txt         the child's stdout/stderr
      runs/<id>/run.json        meta + inputs + range + coverage + report   (when done)
      runs/<id>/trades.json | equity.json | plots.json                      (when done)
      runs/<id>/propsim.json    the prop-eval Monte Carlo on the run's daily net P&L (when done)

status: queued -> running -> done | error | cancelled. The chart service owns a
RunManager (submit / status / cancel / runs / bundle) that launches
`python -m homebase.backtest.runner exec <run_dir> --no-lock` with its own interpreter,
FIFO — never in the service's event loop — and only once it holds one of the
machine-wide backtest slots (slots.py: 2 at once in desk hours, 4 outside them, shared
with the heat-map's cells; none starting 09:20-09:35 ET on weekdays; a request in that
window is refused, a run already queued waits and its status reads `paused`). Runs
that each hold a slot run side by side. A script run
(`python -m homebase.backtest.runner run --strategy nq930 ...`) executes in the
script's process, holding a slot of its own, and writes into the same runs dir, so the
page lists it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import re
import resource
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from bisect import bisect_left
from collections import deque
from pathlib import Path

from .. import draftstore, strategies
from . import drafthost, sandbox
from ..paths import repo_root, state_dir
from . import discipline, propsim, report
from .engine import ENGINE_VERSION, Costs, run_session
from .slots import QUIET_MSG, QUIET_REFUSAL, Slots, held
from .tape import ARCHIVE, CACHE, OverlayTapeStore, TapeStore, coverage_reason, effective_session_window, missing_hours

RUN_ID = re.compile(r"^\d{8}-\d{6}-[a-z0-9_]+-[0-9a-f]{4}$")
FIELDS = {"strategy", "inputs", "range", "qty", "commission", "slippage_ticks", "capital",
          "prop_rules"}
FINAL = {"done", "error", "cancelled"}
PROGRESS_S = 0.5
DAILY_LOOKBACK = dt.timedelta(days=400)     # > 250 sessions of daily bars for the ADX gate


def default_base() -> Path:
    return state_dir() / "tester"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, data) -> None:
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":"), default=str))
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _num(body: dict, key: str, default: float, lo: float, hi: float, integer: bool = False):
    v = body.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        raise ValueError(f"{key}: expected a number")
    if integer and float(v) != int(v):
        raise ValueError(f"{key}: expected a whole number")
    if not lo <= v <= hi:
        raise ValueError(f"{key}: must be within [{lo:g}, {hi:g}]")
    return int(v) if integer else float(v)


def validate(body, *, draft: tuple | None = None) -> dict:
    """The request as the engine will run it. ValueError (DisciplineError is one)
    with a message for the page on anything the schema refuses. No range is refused for
    the dates it reads (2026-09-27): only a malformed one fails."""
    if not isinstance(body, dict):
        raise ValueError("the body is a JSON object")
    extra = sorted(set(body) - FIELDS)
    if extra:
        raise ValueError(f"unknown field(s): {', '.join(extra)}")
    # Item 7: a non-dict `inputs` (a list, a string, a number, ...) must fail the
    # same controlled way as any other bad field -- ValueError -> 400 -- rather
    # than let resolve_inputs()'s `dict(values or {})` throw an uncaught TypeError
    # (a bare int/bool/list) or a ValueError with a confusing message (a string) that
    # would otherwise bubble up as a 500.
    if "inputs" in body and body["inputs"] is not None and not isinstance(body["inputs"], dict):
        raise ValueError("inputs: a JSON object")
    sid = str(body.get("strategy", ""))
    src = None
    if draftstore.is_draft_id(sid):
        # a DRAFT: validated against a STUB built from its text (drafthost) -- its code never runs here --
        # and refused outright when the sandbox its backtest must run in is not working (fail closed)
        sandbox.require()
        cls, src = draft if draft is not None else drafthost.snapshot(sid)
    else:
        cls = strategies.get(sid)
    inputs = strategies.resolve_inputs(cls.inputs(), body.get("inputs") or {})
    rng = discipline.parse_range(body.get("range"))
    prop_rules_id = body.get("prop_rules", propsim.DEFAULT_RULES)
    prop_rules_data = propsim.load_rules(prop_rules_id)     # ValueError "prop_rules: one of ..." when unknown
    # Item 4 (provenance): the resolved runtime config -- cancel/flat times, the
    # nq10am rule config, anything else read from config.json at call time -- so
    # the bundle stays reproducible even after config.json later changes.
    strategy_config = cls(inputs).provenance()
    req = {"strategy": cls.id, "inputs": inputs, "range": rng.to_dict(),
            "strategy_config": strategy_config,
            "qty": _num(body, "qty", 1, 1, 100, integer=True),
            "commission": _num(body, "commission", 4.00, 0.0, 100.0),
            "slippage_ticks": _num(body, "slippage_ticks", 1.0, 0.0, 20.0),
            "capital": _num(body, "capital", 50_000.0, 1.0, 1e9),
            "prop_rules": prop_rules_id, "prop_rules_data": prop_rules_data}
    return drafthost.stamp(req, src) if src is not None else req


def prepare(body, base: Path) -> str:
    """Validate, create runs/<id>/ (request + queued status), and record the run in the
    spend log when its range reads the test days (a record, never a gate)."""
    req = validate(body)
    now = dt.datetime.now()
    rid = f"{now:%Y%m%d-%H%M%S}-{req['strategy']}-{secrets.token_hex(2)}"
    d = base / "runs" / rid
    d.mkdir(parents=True)
    try:
        write_json(d / "request.json", {**req, "id": rid, "created": _now()})
        write_json(d / "status.json", {"id": rid, "status": "queued", "phase": "queued",
                                       "done": 0, "total": 0, "updated": _now()})
    except BaseException:
        shutil.rmtree(d, ignore_errors=True)    # never leave a run folder the page would list as "queued" forever
        raise
    _record(base / "spends.jsonl", req, rid)    # None before the test days; a failed write never fails the run
    return rid


def _record(path: Path, req: dict, rid: str) -> None:
    """The spend log is a RECORD, never a gate -- not even by accident: a write that fails (a full
    disk, a permissions slip, a directory where the file should be) is logged once to stderr (the
    child's log.txt) and the run carries on."""
    try:
        discipline.record(path, strategy=req["strategy"], inputs=req["inputs"],
                          rng=discipline.parse_range(req["range"]), run_id=rid)
    except OSError as e:
        print(f"tester: could not append to the spend log {path}: {e} (the run continues)",
              file=sys.stderr, flush=True)


# no-trade reasons that are holes in the record, not the strategy choosing to sit out: a crash, and
# "no print before <fire>" -- the tape had no price at the fire time (a data hole, rereview)
HOLE_REASONS = ("strategy error", "no print before")


def report_holes(skipped: list[dict], no_trade: list[dict]) -> list[dict]:
    """The sessions the report drops from its Sharpe weekday grid: real holes only -- a coverage/data
    gap (`skipped`), a strategy crash ("strategy error: ...") or no print at the fire time ("no print
    before ..."). A strategy's OWN no-trade reason (a trend gate) is a real flat day the account sat through: it stays on the
    grid as 0.0 (review C1 -- dropping it inflated a gated strategy's Sharpe ~1.5x). The coverage block
    still lists every no-trade day for display."""
    return list(skipped) + [n for n in no_trade if n["reason"].startswith(HOLE_REASONS)]


def _run_propsim(trades: list[dict], req: dict) -> tuple[dict, bool]:
    """The prop-eval Monte Carlo never costs the run its bundle: a malformed rule file
    (e.g. one missing a key the engine requires) is caught here, not left to blow up
    `execute()` before trades/equity/plots/run.json are written. Passes the rules dict
    `validate()` already loaded (`req["prop_rules_data"]`) so evaluate() need not re-read
    the file, and reuses it to label the error when evaluate() still fails past that point.
    """
    try:
        prop = propsim.evaluate(trades, req["prop_rules"], n_paths=propsim.N_PATHS,
                                rules=req.get("prop_rules_data"))
        return prop, False
    except Exception as e:  # noqa: BLE001 — a bad rule file must not sink the whole run
        prop: dict = {"error": f"{type(e).__name__}: {e}"}
        r = req.get("prop_rules_data")
        if r:
            confirmed = r.get("confirmed") is not False
            prop["rules"] = {"name": r.get("name"), "confirmed": confirmed,
                             "label": r.get("name") if confirmed else f"{r.get('name')} · unconfirmed rules"}
        return prop, True


def execute(run_dir: Path, store: TapeStore) -> dict:
    """Run one prepared request to a bundle (in THIS process). Returns run.json."""
    req = read_json(run_dir / "request.json")
    cls = strategies.get(req["strategy"])
    rng = discipline.stored_range(req["range"])     # the request's OWN dates, even if the default has moved since
    if rng.holdout:
        # Item 5 (the record's edge): prepare() already logged this run for the ordinary
        # path, but a hand-edited request.json (e.g. a range widened into the test days after
        # prepare() ran, then `runner exec` invoked on it directly) never went through
        # prepare() at all -- record it here exactly once per run id, never a second time
        # for the normal path. This still only WRITES: the run proceeds either way.
        spends_path = run_dir.parent.parent / "spends.jsonl"
        if not any(s.get("run_id") == req["id"] for s in discipline.spends(spends_path)):
            _record(spends_path, req, req["id"])
    strat = cls(req["inputs"])             # one instance: on_session resets its day state
    days = [d for d in store.sessions(cls.root, rng.start, rng.end)
            if rng.includes(d) and strat.trades_on(d)]
    status = {"id": req["id"], "status": "running", "phase": "run", "done": 0, "total": len(days),
              "pid": os.getpid(), "started": _now(), "updated": _now()}
    write_json(run_dir / "status.json", status)

    dailies: list[dict] = []
    if strat.needs_daily():
        status["phase"] = "daily bars"
        write_json(run_dir / "status.json", status)
        for d in store.sessions(cls.root, rng.start - DAILY_LOOKBACK, rng.end):
            bar = store.daily(cls.root, d)
            if bar is not None:
                dailies.append(bar)
    daily_dates = [b["date"] for b in dailies]

    costs = Costs(req["commission"], req["slippage_ticks"])
    trades, skipped, no_trade, hlines = [], [], [], []
    plots: dict[str, list] = {}
    last = 0.0
    for i, d in enumerate(days):
        if time.monotonic() - last >= PROGRESS_S:
            status.update(done=i, phase="run" if store.cached(cls.root, d) else "building cache",
                          updated=_now())
            write_json(run_dir / "status.json", status)
            last = time.monotonic()
        tape = store.load(cls.root, d)
        if tape is None:
            skipped.append({"date": d.isoformat(), "reason": "no tape"})
            continue
        # Item 2: a CME half day shortens the session -- clamp the window BEFORE
        # checking coverage (the empty afternoon is an early close, not a hole),
        # and feed the same clamped window to the engine so the day's flat/cancel
        # times past the early close never fire.
        window = effective_session_window(cls.root, d, cls.session_window)
        gaps = missing_hours(tape.ts, d, window)
        if gaps:
            skipped.append({"date": d.isoformat(), "reason": coverage_reason(gaps)})
            continue
        strat.session_window = window
        prior = dailies[:bisect_left(daily_dates, d.isoformat())]
        res = run_session(strat, tape, costs, qty=req["qty"], daily=prior)
        trades += [t.to_dict() for t in res.trades]
        if res.skip:
            no_trade.append({"date": d.isoformat(), "reason": res.skip})
        for k, pts in res.plots.items():
            plots.setdefault(k, []).extend(pts)
        hlines += res.hlines

    by_reason: dict[str, int] = {}
    for s in skipped:
        by_reason[s["reason"]] = by_reason.get(s["reason"], 0) + 1
    # Only real holes (a coverage gap or a strategy crash) leave the report's Sharpe grid, and a
    # crash still reads loudly as skipped_by_error (carried from Task 5/6 review); a strategy's own
    # no-trade day is a flat 0.0 there (review C1). coverage.no_trade keeps every reason for display.
    rep = report.build(trades, req["capital"], skipped=report_holes(skipped, no_trade))
    status.update(phase="prop sim", done=len(days), updated=_now())
    write_json(run_dir / "status.json", status)
    if req.get("propsim", True):
        prop, prop_error = _run_propsim(trades, req)
    else:                                   # a walk-forward cell: its full-window prop sim is never shown
        prop, prop_error = {"skipped": "not run (a walk-forward cell)"}, False
    meta = {"id": req["id"], "created": req["created"], "finished": _now(),
            "engine": ENGINE_VERSION, "fill_law": "tick replay",
            "strategy": {"id": cls.id, "name": cls.name, "root": cls.root},
            "inputs": req["inputs"], "strategy_config": req.get("strategy_config", {}),
            "range": req["range"], "qty": req["qty"],
            "commission": req["commission"], "slippage_ticks": req["slippage_ticks"],
            # `holdout`: this run READ the test days — a fact on the report, not a permission.
            # `holdout_reason` is retired (always null) and kept only so a bundle keeps its shape.
            "capital": req["capital"], "holdout": rng.holdout, "holdout_reason": None,
            "prop_rules": req["prop_rules"], "propsim_error": prop_error,
            "coverage": {"sessions": len(days), "used": len(days) - len(skipped),
                         "skipped": skipped, "skipped_by_reason": by_reason, "no_trade": no_trade,
                         "skipped_by_error": rep["skipped_by_error"],
                         "skipped_by_data": rep["skipped_by_data"]},
            "report": rep}
    trades.sort(key=lambda t: (t["exit_ns"], t["entry_ns"]))
    write_json(run_dir / "equity.json", report.equity(trades))       # needs ts_ns; ms conversion is last
    write_json(run_dir / "trades.json", report.to_ms(trades))        # Item 6: entry_ns/exit_ns -> _ms
    write_json(run_dir / "plots.json", {"plots": plots, "hlines": hlines})
    write_json(run_dir / "propsim.json", prop)
    write_json(run_dir / "run.json", meta)
    status.update(status="done", phase="done", done=len(days), updated=_now())
    write_json(run_dir / "status.json", status)
    return meta


def _locked(runs: Path):
    runs.mkdir(parents=True, exist_ok=True)
    fh = open(runs / ".lock", "a")
    fcntl.flock(fh, fcntl.LOCK_EX)          # a `runner exec` started by hand without --no-lock
    return fh


def exec_run(run_dir: Path, store: TapeStore, lock: bool = True) -> int:
    """lock=False: a run that holds a machine-wide slot (a page run, a script run, a heat-map cell) --
    the slots bound it, not the runs dir's flock."""
    fh = _locked(run_dir.parent) if lock else None
    try:
        execute(run_dir, store)
        return 0
    except Exception as e:  # noqa: BLE001 — the page must see why
        st = read_json(run_dir / "status.json", {}) or {}
        st.update(status="error", error=f"{type(e).__name__}: {e}", updated=_now())
        write_json(run_dir / "status.json", st)
        raise
    finally:
        if fh is not None:
            fh.close()


def read_bundle(d: Path) -> dict:
    """A finished run dir (runs/<id>/ or a grid cell) as the page loads it."""
    st = read_json(d / "status.json", {}) or {}
    if st.get("status") != "done":
        raise ValueError(f"run {d.name} is {st.get('status')}, not done")
    return {"run": read_json(d / "run.json"), "trades": read_json(d / "trades.json"),
            "equity": read_json(d / "equity.json"), "plots": read_json(d / "plots.json"),
            "propsim": read_json(d / "propsim.json")}


class RunManager:
    """The chart service's handle on tester runs (thread-safe; no asyncio)."""

    def __init__(self, base: Path, *, archive: Path = ARCHIVE, cache: Path = CACHE,
                 python: str = sys.executable, slots: Slots | None = None):
        self.base, self.runs = Path(base), Path(base) / "runs"
        self.archive, self.cache, self.python = Path(archive), Path(cache), python
        self.slots = slots or Slots()          # the per-machine slots (slots.shared_dir())
        self.runs.mkdir(parents=True, exist_ok=True)
        self._q: deque[str] = deque()
        self._procs: dict[str, subprocess.Popen] = {}     # run id -> its child, while it runs
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._recover()

    def _recover(self) -> None:
        """Runs a previous service process left queued/running are dead now."""
        for st_path in self.runs.glob("*/status.json"):
            st = read_json(st_path, {}) or {}
            if st.get("status") in ("queued", "running") and not _alive(st.get("pid")):
                st.update(status="error", error="interrupted (the chart service restarted)",
                          updated=_now())
                write_json(st_path, st)

    def dir(self, rid: str) -> Path:
        if not RUN_ID.match(rid or "") or not (self.runs / rid).is_dir():
            raise KeyError(rid)
        return self.runs / rid

    def submit(self, body) -> str:
        if self.slots.quiet():
            raise ValueError(QUIET_REFUSAL)
        rid = prepare(body, self.base)
        with self._lock:
            self._q.append(rid)
            if self._thread is None:
                self._thread = threading.Thread(target=self._loop, name="tester-runs", daemon=True)
                self._thread.start()
        self._wake.set()
        return rid

    def status(self, rid: str) -> dict:
        st = read_json(self.dir(rid) / "status.json", {}) or {}
        with self._lock:
            if rid in self._q:
                st["queue_position"] = list(self._q).index(rid) + 1
        if st.get("status") == "queued" and self.slots.quiet():
            st["paused"] = QUIET_MSG
        return st

    def cancel(self, rid: str) -> dict:
        d = self.dir(rid)
        with self._lock:
            st = read_json(d / "status.json", {}) or {}
            if st.get("status") in FINAL:
                return st                       # finished (or already cancelled): leave it
            if rid in self._q:
                self._q.remove(rid)
                proc = None
            elif rid in self._procs:
                proc = self._procs[rid]
                self._cancelled.add(rid)        # the worker must not report its exit as an error
            else:
                raise ValueError("this run was not started by the chart service (stop it where it runs)")
        if proc is not None:
            stop_proc(proc)
        st = read_json(d / "status.json", {}) or {}
        if st.get("status") == "done":
            return st                           # it finished before the signal landed
        st.update(status="cancelled", phase="cancelled", updated=_now())
        write_json(d / "status.json", st)
        return st

    def shutdown(self) -> None:
        """Chart-service shutdown: a run this manager launched must never be
        left orphaned. Terminates whatever is currently in flight via the
        same terminate/kill path as cancel(); a no-op if nothing is running."""
        with self._lock:
            rids = list(self._procs)
        for rid in rids:
            try:
                self.cancel(rid)
            except ValueError:
                pass

    def runs_list(self, limit: int = 50) -> list[dict]:
        out = []
        for d in sorted((p for p in self.runs.iterdir() if RUN_ID.match(p.name)),
                        key=lambda p: p.name, reverse=True)[:limit]:
            req = read_json(d / "request.json", {}) or {}
            st = read_json(d / "status.json", {}) or {}
            meta = read_json(d / "run.json", {}) or {}
            allc = ((meta.get("report") or {}).get("summary") or {}).get("all") or {}
            out.append({"id": d.name, "strategy": req.get("strategy"), "created": req.get("created"),
                        "status": st.get("status"), "range": req.get("range"),
                        "holdout": bool((req.get("range") or {}).get("holdout")), "trades": allc.get("trades"),
                        "net_profit": allc.get("net_profit")})
        return out

    def bundle(self, rid: str) -> dict:
        return read_bundle(self.dir(rid))

    def _head(self) -> str | None:
        with self._lock:
            return self._q[0] if self._q else None

    def _loop(self) -> None:
        while True:
            self._wake.wait()
            with self._lock:
                if not self._q:
                    self._wake.clear()
                    continue
                rid = self._q[0]
            # a slot first (the global cap, the QUIET window); give up if the run is cancelled meanwhile
            slot = self.slots.acquire(cancelled=lambda: self._head() != rid)
            if slot is None:
                continue
            with self._lock:
                if not self._q or self._q[0] != rid:
                    slot.close()
                    continue
                self._q.popleft()
                d = self.runs / rid
                try:              # --no-lock: the slot it holds bounds it, as a heat-map cell's does
                    proc = launch(d, self.python, self.archive, self.cache, slot, ("--no-lock",))
                except (OSError, ValueError) as e:
                    slot.close()
                    st = read_json(d / "status.json", {}) or {}
                    st.update(status="error", error=f"could not start the runner: {e}", updated=_now())
                    write_json(d / "status.json", st)
                    continue
                self._procs[rid] = proc
            # its own thread waits for it: this loop goes on to the next run, which takes the next free slot
            threading.Thread(target=self._finish, args=(rid, d, proc, slot), name=f"tester-run-{rid}",
                             daemon=True).start()

    def _finish(self, rid: str, d: Path, proc: subprocess.Popen, slot) -> None:
        """Wait for one launched run; write its final status when the child did not."""
        try:
            code, timed_out = wait_proc(proc)
        finally:
            slot.close()                    # always: a killed draft's whole group is gone by now
            finish_proc(proc)
        with self._lock:
            self._procs.pop(rid, None)
            if rid in self._cancelled:
                return                      # cancel() writes the final status
        st = read_json(d / "status.json", {}) or {}
        if timed_out:
            st.update(status="error", error=timed_out, updated=_now())
            write_json(d / "status.json", st)
        elif st.get("status") not in FINAL:
            tail = (d / "log.txt").read_text(errors="replace")[-600:]
            st.update(status="error", error=f"runner exited {code}: {tail}", updated=_now())
            write_json(d / "status.json", st)


# ---------------------------------------------------------------- launching a backtest child

def launch(run_dir: Path, python: str, archive: Path, cache: Path, slot, extra: tuple = ()) -> subprocess.Popen:
    """Start `runner exec <run_dir>` holding `slot`. A built-in strategy's child starts exactly as it always
    has. A DRAFT's (its request.json carries draft_source) starts inside the macOS sandbox (sandbox.py +
    draft.sb: no network, writes only to its run dir and a private tmp dir that also holds its own tape
    cache), with a minimal env, in its OWN process group (stop_proc kills the whole group), and is refused
    when the sandbox is not working (fail closed)."""
    req = read_json(Path(run_dir) / "request.json", {}) or {}
    argv = [python, "-m", "homebase.backtest.runner", "exec", str(run_dir), *extra,
            "--archive", str(archive), "--cache", str(cache), "--slot-fd", str(slot.fileno())]
    draft = drafthost.is_draft_req(req)
    tmp = None
    if draft:
        sandbox.require()
        tmp = sandbox.private_tmp()
        argv += ["--private-cache", str(tmp / "tape")]
    log = open(Path(run_dir) / "log.txt", "ab")
    try:
        if draft:
            proc = subprocess.Popen(
                sandbox.command(argv, sandbox.params(run_dir=run_dir, archive=archive, cache=cache, tmp=tmp,
                                                     python=python)),
                cwd=tmp, env=sandbox.env(tmp), stdout=log, stderr=subprocess.STDOUT,
                pass_fds=(slot.fileno(),), start_new_session=True)
        else:
            proc = subprocess.Popen(      # the child holds the slot too: it lives as long as the backtest
                argv, cwd=repo_root(), stdout=log, stderr=subprocess.STDOUT, pass_fds=(slot.fileno(),))
    except BaseException:
        log.close()
        if tmp is not None:
            sandbox.drop_tmp(tmp)
        raise
    proc.hb_draft, proc.hb_tmp, proc.hb_log = draft, tmp, log
    return proc


def wait_proc(proc: subprocess.Popen) -> tuple[int, str | None]:
    """(exit code, None) -- or, for a DRAFT past its wall clock (sandbox.DRAFT_TIMEOUT_S), its whole process
    group killed and (code, the reason)."""
    if not getattr(proc, "hb_draft", False):
        return proc.wait(), None
    try:
        return proc.wait(timeout=sandbox.DRAFT_TIMEOUT_S), None
    except subprocess.TimeoutExpired:
        stop_proc(proc)
        return proc.returncode, (f"timed out: a draft backtest may run at most "
                                 f"{sandbox.DRAFT_TIMEOUT_S / 60:g} minutes (the run was stopped)")


def stop_proc(proc: subprocess.Popen) -> None:
    """Terminate a backtest child (cancel / timeout / shutdown). A draft's is killed as a process GROUP, so
    nothing it started survives holding the inherited slot fd."""
    if getattr(proc, "hb_draft", False):
        for sig, wait_s in ((signal.SIGTERM, 10), (signal.SIGKILL, 10)):
            try:
                os.killpg(proc.pid, sig)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                proc.wait(timeout=wait_s)
                break
            except subprocess.TimeoutExpired:
                continue
        try:
            os.killpg(proc.pid, signal.SIGKILL)      # the group's stragglers, even after the leader exited
        except (ProcessLookupError, PermissionError):
            pass
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def finish_proc(proc: subprocess.Popen) -> None:
    log = getattr(proc, "hb_log", None)
    if log is not None:
        log.close()
    if getattr(proc, "hb_tmp", None) is not None:
        sandbox.drop_tmp(proc.hb_tmp)


def _register_draft(run_dir: Path) -> None:
    """A `runner exec` child whose request carries a DRAFT's source snapshot registers it into this
    child's own strategies.REGISTRY -- the exact code that was validated, not the file as it is now."""
    req = read_json(Path(run_dir) / "request.json", {}) or {}
    src = req.get("draft_source")
    if isinstance(src, str) and draftstore.is_draft_id(req.get("strategy")):
        drafthost.register_source(draftstore.name_of(req["strategy"]), src)


def _alive(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kv(s: str) -> tuple[str, object]:
    k, _, v = s.partition("=")
    try:
        return k, json.loads(v)
    except ValueError:
        return k, v


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m homebase.backtest.runner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("exec", help="run a prepared run dir (the chart service uses this)")
    ex.add_argument("run_dir", type=Path)
    ex.add_argument("--no-lock", action="store_true",
                    help="a run that holds a backtest slot (a page run, a heat-map cell): the slots bound it")
    ex.add_argument("--private-cache", type=Path, default=None,
                    help="a DRAFT run (sandboxed): read the shared --cache, build any missing tape here")
    ex.add_argument("--slot-fd", type=int, default=None,
                    help="an inherited backtest slot (the chart service passes it); without one, exec "
                         "takes its own slot and refuses the 09:20-09:35 ET window")
    run = sub.add_parser("run", help="validate + run in this process (scripts, the assistant)")
    run.add_argument("--strategy", required=True)
    run.add_argument("--input", action="append", default=[], help="key=value (JSON value)")
    run.add_argument("--range", default="research", help="research | is_months | START:END")
    run.add_argument("--qty", type=int, default=1)
    run.add_argument("--commission", type=float, default=4.00)
    run.add_argument("--slippage-ticks", type=float, default=1.0)
    run.add_argument("--capital", type=float, default=50_000.0)
    run.add_argument("--base", type=Path, default=None)
    for p in (ex, run):
        p.add_argument("--archive", type=Path, default=ARCHIVE)
        p.add_argument("--cache", type=Path, default=CACHE)
    a = ap.parse_args(argv)
    store = TapeStore(a.archive, a.cache)
    if a.cmd == "exec":
        slot = None
        if a.slot_fd is None or not held(a.slot_fd):
            slots = Slots()
            if slots.quiet():
                print(QUIET_REFUSAL, file=sys.stderr)
                return 2
            slot = slots.acquire()
        try:
            os.nice(5)      # on top of the chart job's own nice 5: a backtest never competes with the desk
            req = read_json(Path(a.run_dir) / "request.json", {}) or {}
            if drafthost.is_draft_req(req):
                # a DRAFT's code runs only here, and only inside the sandbox the chart service put us in
                if os.environ.get("HOMEBASE_SANDBOXED") != "1":
                    print("refused: a draft strategy runs only inside the backtest sandbox", file=sys.stderr)
                    return 2
                cpu = int(sandbox.DRAFT_TIMEOUT_S)
                resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
                if a.private_cache is not None:
                    store = OverlayTapeStore(a.archive, a.cache, a.private_cache)
                _register_draft(a.run_dir)
            return exec_run(a.run_dir, store, lock=not a.no_lock)
        finally:
            if slot is not None:
                slot.close()
    if a.range in ("research", "is_months"):
        rng = {"kind": a.range}
    else:
        s, _, e = a.range.partition(":")
        rng = {"kind": "custom", "start": s, "end": e}
    body = {"strategy": a.strategy, "inputs": dict(_kv(x) for x in a.input), "range": rng,
            "qty": a.qty, "commission": a.commission, "slippage_ticks": a.slippage_ticks,
            "capital": a.capital}
    base = a.base or default_base()
    slots = Slots()
    if slots.quiet():
        print(QUIET_REFUSAL, file=sys.stderr)
        return 2
    rid = prepare(body, base)
    t0 = time.monotonic()
    slot = slots.acquire()
    try:
        exec_run(base / "runs" / rid, store, lock=False)
    finally:
        slot.close()
    meta = read_json(base / "runs" / rid / "run.json")
    s = meta["report"]["summary"]["all"]
    print(f"{rid}: {s['trades']} trades, net ${s['net_profit']:,.2f}, WR {s['win_rate'] or 0:.1f}%, "
          f"PF {s['profit_factor'] or 0:.2f}, Sharpe {s['sharpe']:.2f}, t {s['t_stat'] or 0:.2f}, "
          f"skipped {len(meta['coverage']['skipped'])}, {time.monotonic() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
