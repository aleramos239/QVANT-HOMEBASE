"""Walk-forward, the user's scheme: 1 month to SELECT, the next 3 months to TEST, stepping monthly, on the
research window 2021-01-01 -> 2024-12-31 ONLY (forced here, server-side; a range or holdout is refused).

Steps. Over the window's whole calendar months m_0..m_47, step k selects on m_k and tests on
m_{k+1}..m_{k+3}. A step whose test window would run past the window's last month is dropped (no partial
test windows), so the research window has 45 steps: select 2021-01 .. 2024-09.

Selection. In each selection month every cell of the user's grid (<= 60 cells, the heat-map's own
validation) is scored by the chosen metric (default net $); a cell needs >= min_trades (default 5) trades
that month and a defined metric value to be eligible. The best value wins; ties -- values equal after
rounding to 6 decimals, so float summation noise is a tie -- go to the cell with MORE trades that month,
then to the LOWEST cell index (the grid's own order, last axis fastest). No eligible cell = no pick: that
step sits out (flat, no trades).

Stitching (the ruling on overlap). Monthly steps with 3-month tests overlap: month M is in the test window
of steps M-1, M-2 and M-3. The stitched OOS equity is ONE non-overlapping chain -- steps 0, 3, 6, ... --
each holding its pick for its FULL 3-month test window, which is exactly "select 1 month, run it for 3,
repeat". Its test windows tile 2021-02 .. 2024-10 contiguously, every month once. Every monthly step is
still run and shown in the per-step table (its own 3-month OOS, overlapping -- never summed), and the
other two chains' (phase 1: steps 1, 4, ...; phase 2: steps 2, 5, ...) net is reported next to it so the
choice of phase is visible, never silently picked. The chain is fixed at phase 0 before any result exists.

Execution (the per-month cache). Each cell runs ONCE over the whole research window as an ordinary
heat-map cell (grid.GridManager: the same `runner exec` child, the machine-wide 2-slot cap, FCFS tickets,
no starts 09:20-09:35 ET). Sessions are independent -- a strategy declares it (Strategy.session_independent;
the walk-forward refuses one that does not): its day state resets every session and daily bars come from
the store, not the range -- so a cell's trades inside month m ARE a single run over month m
(tests/test_backtest_walkforward.py pins that on real ticks, gate off and on). A cell skips the full-window
prop sim (request "propsim": false): it would never be shown. When a cell finishes, its per-month stats
are cached in cells/NN/months.json; selection reads only those, and a test leg re-uses the chosen cell's
already-computed trades. 60 cells cost 60 backtests, not 60 x 45.

Looks. Every selection month's grid is a look at every cell: a finished walk-forward adds
cells x steps (e.g. 60 x 45 = 2,700) to the machine-wide looks counter, once, as its result is written.
A cancelled walk-forward, one with a failed cell (no selection is made over a partial grid), or one whose
looks counter is unreadable shows no result and counts nothing. The full-window per-cell results are
never served (no cell bundles, no cell summaries): only selection-month stats of the PICKED cell and
the test legs are shown.

Metrics use the report's own conventions (report.column: net of costs, Sharpe on the weekday grid, a
session the run skipped dropped from that grid).

    <base>/walkforward/<id>/grid.json         the job: axes, costs, walkforward config, per-cell status
    <base>/walkforward/<id>/cells/NN/         a run dir (+ months.json, the per-month cache)
    <base>/walkforward/<id>/result.json       the steps, the stitched equity + stats (when done)
"""
from __future__ import annotations

import datetime as dt
import math
from collections import Counter
from pathlib import Path

from .. import strategies
from . import grid, report
from .discipline import RESEARCH_END, RESEARCH_START
from .grid import FINAL, GridManager, LooksCorrupt, add_look, validate_grid
from .runner import read_json, report_holes, write_json

SELECT_MONTHS = 1
TEST_MONTHS = 3
STEP_MONTHS = 1
METRICS = {"net_profit": "Net $", "sharpe": "Sharpe", "profit_factor": "Profit factor", "t_stat": "t-stat"}
DEFAULT_METRIC = "net_profit"
DEFAULT_MIN_TRADES = 5
MAX_MIN_TRADES = 1000
RESEARCH_ONLY = "the walk-forward runs on the research window 2021–2024 only"
STAT_KEYS = ("net_profit", "trades", "win_rate", "profit_factor", "sharpe", "max_drawdown", "avg_trade", "t_stat",
             "skipped_by_error")
TIE_BREAK = "best metric (equal to 6 decimals = a tie) → more trades that month → lowest cell index"
STITCH_RULE = ("steps 0, 3, 6, … (phase 0), each holding its pick for its full 3-month test window: "
               "the test windows tile the OOS months once each, never overlapping")


# ---------------------------------------------------------------- the pure part

def month_list(start: dt.date, end: dt.date) -> list[str]:
    """Every calendar month lying wholly inside [start, end], as 'YYYY-MM'."""
    out = []
    y, m = start.year, start.month
    if start.day != 1:
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    while True:
        first = dt.date(y, m, 1)
        nxt = dt.date(y + 1, 1, 1) if m == 12 else dt.date(y, m + 1, 1)
        if nxt - dt.timedelta(days=1) > end:
            return out
        out.append(first.strftime("%Y-%m"))
        y, m = nxt.year, nxt.month


def steps(months: list[str]) -> list[dict]:
    """Step k selects on months[k] and tests on the next TEST_MONTHS; a partial last window is dropped."""
    n = len(months) - SELECT_MONTHS - TEST_MONTHS + 1
    return [{"k": k, "select": months[k], "test": months[k + SELECT_MONTHS:k + SELECT_MONTHS + TEST_MONTHS]}
            for k in range(0, max(n, 0), STEP_MONTHS)]


def chain(n_steps: int, phase: int = 0) -> list[int]:
    """The non-overlapping stitched chain: every TEST_MONTHS-th step starting at `phase`."""
    return list(range(phase, n_steps, TEST_MONTHS))


def to_ns(t: dict) -> dict:
    """A trades.json row (entry_ms/exit_ms) back to the engine shape report.* reads."""
    return {**t, "entry_ns": t["entry_ms"] * 1_000_000, "exit_ns": t["exit_ms"] * 1_000_000}


def _stats(trades_ms: list[dict], skipped: list[dict], capital: float) -> dict:
    tr = sorted((to_ns(t) for t in trades_ms), key=lambda t: (t["exit_ns"], t["entry_ns"]))
    col = report.column(tr, capital, skipped)
    out = {k: col[k] for k in STAT_KEYS if k != "skipped_by_error"}
    out["skipped_by_error"] = sum(1 for s in skipped if s["reason"].startswith("strategy error"))
    return out


def _in(months: set[str], rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["date"][:7] in months]


def month_stats(trades_ms: list[dict], skipped: list[dict], capital: float, months: list[str]) -> dict:
    """{month: stats} -- each month exactly as report.column reads a run over that month alone."""
    return {m: _stats(_in({m}, trades_ms), _in({m}, skipped), capital) for m in months}


def _run_skipped(run: dict) -> list[dict]:
    """The sessions a run's report treats as holes -- exactly runner.report_holes, so a month slice
    equals a single run over that month."""
    cov = run.get("coverage") or {}
    return report_holes(cov.get("skipped") or [], cov.get("no_trade") or [])


def cell_months(cdir: Path, months: list[str]) -> dict:
    """A finished cell dir's per-month stats (the months.json cache content)."""
    run = read_json(Path(cdir) / "run.json")
    return month_stats(read_json(Path(cdir) / "trades.json") or [], _run_skipped(run), run["capital"], months)


def _rounded(v) -> float | None:
    if v is None or isinstance(v, bool) or not isinstance(v, (int, float)) or math.isnan(v):
        return None
    return round(float(v), 6)


def pick(by_cell: dict, metric: str, min_trades: int) -> int | None:
    """The winning cell index of one selection month ({i: stats | None}), None when nobody qualifies.
    Deterministic: TIE_BREAK."""
    best = None
    for i, s in by_cell.items():
        if not s or (s.get("trades") or 0) < min_trades:
            continue
        v = _rounded(s.get(metric))
        if v is None:
            continue
        key = (-v, -(s.get("trades") or 0), i)
        if best is None or key < best[0]:
            best = (key, i)
    return None if best is None else best[1]


def compute(cells: list[dict], months: list[str], *, trades_of, metric: str, min_trades: int,
            capital: float) -> dict:
    """cells: [{i, params, months: {m: stats}}]; trades_of(i) -> (trades_ms, skipped) of a PICKED cell."""
    st = steps(months)
    params = {c["i"]: c["params"] for c in cells}
    cache: dict[int, tuple[list, list]] = {}

    def leg(i: int, ms: list[str]) -> tuple[list, list]:
        if i not in cache:
            cache[i] = trades_of(i)
        tr, sk = cache[i]
        return _in(set(ms), tr), _in(set(ms), sk)

    rows, prev = [], None
    for s in st:
        i = pick({c["i"]: c["months"].get(s["select"]) for c in cells}, metric, min_trades)
        row = {"k": s["k"], "select": s["select"], "test": [s["test"][0], s["test"][-1]], "cell": i,
               "params": params[i] if i is not None else None, "is": None, "oos": None, "stitched": False,
               "changed": None}
        if i is not None:
            row["is"] = next(c["months"][s["select"]] for c in cells if c["i"] == i)
            row["oos"] = _stats(*leg(i, s["test"]), capital)
        if s["k"] > 0:
            row["changed"] = (i != prev) if (i is not None and prev is not None) else None
        rows.append(row)
        prev = i

    def stitched(phase: int) -> tuple[list, list, list[str]]:
        tr, sk, covered = [], [], []
        for k in chain(len(st), phase):
            covered += st[k]["test"]
            if rows[k]["cell"] is not None:
                t, s = leg(rows[k]["cell"], st[k]["test"])
                tr += t
                sk += s
        return tr, sk, covered

    tr0, sk0, covered0 = stitched(0)
    for k in chain(len(st), 0):
        rows[k]["stitched"] = True
    trades_ns = sorted((to_ns(t) for t in tr0), key=lambda t: (t["exit_ns"], t["entry_ns"]))
    phases = []
    for p in range(TEST_MONTHS):
        tr, sk, _ = (tr0, sk0, None) if p == 0 else stitched(p)
        s = _stats(tr, sk, capital)
        phases.append({"phase": p, "steps": len(chain(len(st), p)), "net_profit": s["net_profit"],
                       "trades": s["trades"], "sharpe": s["sharpe"]})

    picks = [r["cell"] for r in rows]
    pairs = [(a, b) for a, b in zip(picks, picks[1:]) if a is not None and b is not None]
    counts = Counter(p for p in picks if p is not None)
    top = min(counts.items(), key=lambda kv: (-kv[1], kv[0])) if counts else None
    return {
        "scheme": {"select_months": SELECT_MONTHS, "test_months": TEST_MONTHS, "step_months": STEP_MONTHS,
                   "metric": metric, "metric_label": METRICS.get(metric, metric), "min_trades": min_trades,
                   "tie_break": TIE_BREAK, "stitch": STITCH_RULE},
        "window": {"start": months[0] if months else None, "end": months[-1] if months else None},
        "n_cells": len(cells), "n_steps": len(st), "looks": len(cells) * len(st),
        "steps": rows,
        "stitched": {"stats": _stats(tr0, sk0, capital), "equity": report.equity(trades_ns),
                     "months": covered0, "legs": chain(len(st), 0)},
        "phases": phases,
        "stability": {"changes": sum(1 for a, b in pairs if a != b), "pairs": len(pairs), "distinct": len(counts),
                      "no_pick": sum(1 for p in picks if p is None),
                      "top": {"cell": top[0], "count": top[1]} if top else None},
        "skipped_by_error": sum(r["oos"]["skipped_by_error"] for r in rows if r["oos"]),
    }


def scheme() -> dict:
    """What the page needs before a job exists (review M5: the step count comes from here, not a
    client constant)."""
    st = steps(month_list(RESEARCH_START, RESEARCH_END))
    return {"n_steps": len(st), "first_select": st[0]["select"], "last_select": st[-1]["select"],
            "select_months": SELECT_MONTHS, "test_months": TEST_MONTHS, "step_months": STEP_MONTHS,
            "metrics": [[k, v] for k, v in METRICS.items()], "default_metric": DEFAULT_METRIC,
            "default_min_trades": DEFAULT_MIN_TRADES, "max_min_trades": MAX_MIN_TRADES}


# ---------------------------------------------------------------- validation

def _min_trades(v) -> int:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or float(v) != int(v):
        raise ValueError("min_trades: a whole number")
    if not 1 <= v <= MAX_MIN_TRADES:
        raise ValueError(f"min_trades: must be within [1, {MAX_MIN_TRADES}]")
    return int(v)


def validate_wf(body) -> dict:
    """The heat-map grid (validate_grid: <= 60 cells, 2-3 axes, research window) + the walk-forward's
    own fields. ValueError / DisciplineError with a message for the page."""
    if not isinstance(body, dict):
        raise ValueError("the body is a JSON object")
    grid._research_only(body, RESEARCH_ONLY)
    b = dict(body)
    metric = b.pop("metric", DEFAULT_METRIC)
    if not isinstance(metric, str) or metric not in METRICS:
        raise ValueError(f"metric: one of {', '.join(METRICS)}")
    min_trades = _min_trades(b.pop("min_trades", DEFAULT_MIN_TRADES))
    g = validate_grid(b)
    if not getattr(strategies.get(g["strategy"]), "session_independent", False):
        raise ValueError(f"{g['strategy']}: not flagged session-independent, so a month cannot be sliced "
                         "out of one full-window run -- the walk-forward refuses it")
    for c in g["cells"]:
        c["req"]["propsim"] = False          # the full-window prop sim is never shown here (review M4)
    months = month_list(RESEARCH_START, RESEARCH_END)
    g["walkforward"] = {"metric": metric, "metric_label": METRICS[metric], "min_trades": min_trades,
                        "select_months": SELECT_MONTHS, "test_months": TEST_MONTHS, "step_months": STEP_MONTHS,
                        "months": months, "n_steps": len(steps(months)), "tie_break": TIE_BREAK,
                        "stitch": STITCH_RULE}
    return g


# ---------------------------------------------------------------- the manager

def _eta(st: dict, progress: float) -> float | None:
    started = st.get("started")
    if not started or not 0 < progress < 1:
        return None
    try:
        t0 = dt.datetime.fromisoformat(started)
    except ValueError:
        return None
    elapsed = (dt.datetime.now(dt.timezone.utc) - t0).total_seconds()
    return max(0.0, elapsed / progress * (1 - progress))


class WalkForwardManager(GridManager):
    """Walk-forward jobs: a heat-map grid over the research window (its own dir, no per-cell looks),
    then selection + stitching once every cell is done."""

    SUBDIR = "walkforward"
    COUNT_CELL_LOOKS = False

    def __init__(self, *a, **kw):
        self._claimed: set[str] = set()
        super().__init__(*a, **kw)

    def _validate(self, body) -> dict:
        return validate_wf(body)

    def _cell_finished(self, cdir: Path, run: dict) -> None:
        # the per-month cache; the months come from the job itself
        g = read_json(Path(cdir).parent.parent / "grid.json", {}) or {}
        months = (g.get("walkforward") or {}).get("months") or month_list(RESEARCH_START, RESEARCH_END)
        if (run.get("range") or {}).get("kind") != "research":
            raise ValueError("a walk-forward cell ran outside the research window")
        write_json(Path(cdir) / "months.json", cell_months(cdir, months))

    def _cell_summary(self, run: dict) -> dict:
        rep = (run or {}).get("report") or {}
        cov = (run or {}).get("coverage") or {}
        return {"sessions": cov.get("sessions"), "used": cov.get("used"),
                "skipped_by_error": rep.get("skipped_by_error", 0)}    # never the full-window P&L

    def _finish_grid(self, st: dict) -> None:       # under the lock
        if st["status"] in ("queued", "running") and all(c["status"] in FINAL for c in st["cells"]):
            st["status"] = "selecting"

    def _after_cell(self, gid: str, st: dict):      # under the lock
        if st["status"] == "selecting" and gid not in self._claimed:
            self._claimed.add(gid)
            return lambda: self._stitch(gid)
        return None

    def _stitch(self, gid: str) -> None:
        d = self.grids / gid
        with self._lock:
            st = self._live[gid]
            if st["status"] != "selecting":
                return
            cells = [dict(c) for c in st["cells"]]
            cfg = st["walkforward"]
            capital = st["capital"]
        bad = [c for c in cells if c["status"] != "done"]
        result, err = None, None
        if bad:
            err = (f"{len(bad)} of {len(cells)} cells did not finish (first: cell {bad[0]['i']}: "
                   f"{bad[0].get('error') or bad[0]['status']}) -- no selection over a partial grid, no looks counted")
        else:
            try:
                ins = []
                for c in cells:
                    ms = read_json(d / "cells" / f"{c['i']:02d}" / "months.json")
                    if not isinstance(ms, dict):
                        raise ValueError(f"cell {c['i']}: the per-month cache is missing")
                    ins.append({"i": c["i"], "params": c["params"], "months": ms})

                def trades_of(i: int):
                    cdir = d / "cells" / f"{i:02d}"
                    return read_json(cdir / "trades.json") or [], _run_skipped(read_json(cdir / "run.json"))

                result = compute(ins, cfg["months"], trades_of=trades_of, metric=cfg["metric"],
                                 min_trades=cfg["min_trades"], capital=capital)
            except Exception as e:  # noqa: BLE001 -- the page must see why
                err = f"selection failed: {type(e).__name__}: {e}"
        with self._cv:
            if st["status"] != "selecting":        # cancelled meanwhile: nothing shown, nothing counted
                return
            if result is not None:
                try:
                    add_look(self.looks_path, st["strategy"], result["looks"])
                except LooksCorrupt as e:           # never shown uncounted
                    err, result = f"the looks counter is unreadable, so the result is withheld: {e}", None
                    st["looks_error"] = str(e)
            if result is not None:
                write_json(d / "result.json", result)
                st.update(status="done", looks_added=result["looks"])
            else:
                st.update(status="error", error=err)
            self._save(gid)

    def _view(self, gid: str) -> dict:              # under the lock
        st = super()._view(gid)
        cells = st.get("cells") or []
        frac = 0.0
        for c in cells:
            if c.get("status") in FINAL:
                frac += 1
            elif c.get("status") == "running":
                cs = read_json(self.grids / gid / "cells" / f"{c['i']:02d}" / "status.json", {}) or {}
                if cs.get("total"):
                    frac += min(1.0, (cs.get("done") or 0) / cs["total"])
        prog = frac / len(cells) if cells else 0.0
        st["progress"] = 1.0 if st.get("status") == "done" else round(prog, 4)
        st["eta_s"] = None if st.get("paused") or st.get("status") in FINAL else _eta(st, prog)
        return st

    def result(self, gid: str) -> dict:
        d = self.dir(gid)
        st = self.status(gid)
        if st.get("status") != "done":
            raise ValueError(f"walk-forward {gid} is {st.get('status')}, not done")
        return read_json(d / "result.json")

    def cell_bundle(self, gid: str, i: int) -> dict:
        raise KeyError(f"{gid}/{i}: a walk-forward's full-window cells are never served")

    def list(self, limit: int = 20) -> list[dict]:
        out = super().list(limit)
        for g in out:
            j = read_json(self.grids / g["id"] / "grid.json", {}) or {}
            g["metric"] = (j.get("walkforward") or {}).get("metric")
        return out
