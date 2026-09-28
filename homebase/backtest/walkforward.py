"""Walk-forward, the user's scheme: 1 month to SELECT, the next N months to TEST, stepping monthly, over
whatever window the request names (the range picker's preset; 2021-01-01 -> 2024-12-31 by default).

Steps. Over the window's whole calendar months m_0..m_k, step k selects on m_k and tests on
m_{k+1}..m_{k+N}. A step whose test window would run past the window's last month is dropped (no partial
test windows), so the research window at N = 3 has 45 steps: select 2021-01 .. 2024-09.

Selection. In each selection month every cell of the user's grid (<= 60 cells, the heat-map's own
validation) is scored by the chosen metric (default net $); a cell needs >= min_trades (default 5) trades
that month and a defined metric value to be eligible. The best value wins; ties -- values equal after
rounding to 6 decimals, so float summation noise is a tie -- go to the cell with MORE trades that month,
then to the LOWEST cell index (the grid's own order, last axis fastest). No eligible cell = no pick: that
step sits out (flat, no trades).

Ratio. N (`test_months`) is the OOS side of the user's 1:1 / 1:2 / 1:3 ratio -- months out-of-sample per
selection month. 1:3 is the default, the scheme this has always run.

Stitching (the ruling on overlap). Monthly steps with N-month tests overlap when N > 1: month M is in the
test window of steps M-1 .. M-N. The stitched OOS equity is ONE non-overlapping chain -- steps 0, N, 2N,
... -- each holding its pick for its FULL N-month test window, which is exactly "select 1 month, run it
for N, repeat". Its test windows tile the OOS months contiguously, every month once. Every monthly step is
still run and shown in the per-step table (its own N-month OOS, overlapping -- never summed), and the
other N-1 chains' (phase 1: steps 1, N+1, ...; and so on) net is reported next to it so the choice of
phase is visible, never silently picked. The chain is fixed at phase 0 before any result exists.

Both sides. The result carries the stitched OUT-of-sample chain and, beside it, the same chain's own
SELECTION months (`stitched_is`) -- the user's "and then OOS for each". The two sides span DIFFERENT
month counts (1 per leg in-sample, N per leg out-of-sample: 15 vs 45 on 2021-2024 at 1:3), so their raw
totals are not comparable: each side also reports `n_months` and `per_month` (net $ and trades per month,
a flat no-pick month counted as a month), and the drop is taken on the per-month net (in $ and as a %
of the in-sample month) and on Sharpe, which is already a rate. `stitched.uncovered` lists the tail months
the chain never tests out-of-sample. The OOS trades travel with the result for the List of trades tab.

Execution (the per-month cache). Each cell runs ONCE over the whole window as an ordinary
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

Compare (1:1 · 1:2 · 1:3 side by side). A job submitted with `compare: true` (and no test_months) runs
the grid ONCE -- the cells are exactly a 1:N job's cells, since a cell always runs over the whole window
whatever the ratio -- then selects and stitches it three times, at 1:1, 1:2 and 1:3, from the same
per-month cache. The three schemes therefore share the window, the grid, the costs, Select-by and
Min-trades by construction, cost 1x the backtests (not 3x), and are one job for cancel / progress /
reload-resume, queued through the same 2-slot cap and the 09:20-09:35 ET pause. Each scheme's full
result is written as result-N.json (the ordinary 1:N result shape, served by `result(id, N)`), and
compare.json holds only their STITCHED OUT-OF-SAMPLE numbers side by side (compare_summary: no
in-sample figure crosses into it). Looks: the three schemes' selections are three separate searches,
so the job counts the SUM of their cells x steps -- the conservative reading. The window must fit a full
1:3 cycle, so no column is ever empty.

Metrics use the report's own conventions (report.column: net of costs, Sharpe on the weekday grid, a
session the run skipped dropped from that grid).

    <base>/walkforward/<id>/grid.json         the job: axes, costs, walkforward config, per-cell status
    <base>/walkforward/<id>/cells/NN/         a run dir (+ months.json, the per-month cache)
    <base>/walkforward/<id>/result.json       the steps, the stitched equity + stats (when done)
    <base>/walkforward/<id>/result-N.json     a compare job: scheme 1:N's result (the same shape)
    <base>/walkforward/<id>/compare.json      a compare job: the three stitched OOS side by side
"""
from __future__ import annotations

import datetime as dt
import math
from collections import Counter
from pathlib import Path

from . import drafthost, report
from .discipline import RESEARCH_END, RESEARCH_START
from .grid import FINAL, GridManager, LooksCorrupt, add_look, validate_grid
from .runner import read_json, report_holes, write_json

SELECT_MONTHS = 1
TEST_MONTHS = 3            # the default OOS side of the ratio (1:3); 1 and 2 are the other choices
RATIOS = (1, 2, 3)
STEP_MONTHS = 1
METRICS = {"net_profit": "Net $", "sharpe": "Sharpe", "profit_factor": "Profit factor", "t_stat": "t-stat"}
DEFAULT_METRIC = "net_profit"
DEFAULT_MIN_TRADES = 5
MAX_MIN_TRADES = 1000
STAT_KEYS = ("net_profit", "trades", "win_rate", "profit_factor", "sharpe", "max_drawdown", "avg_trade", "t_stat",
             "skipped_by_error")
TIE_BREAK = "best metric (equal to 6 decimals = a tie) → more trades that month → lowest cell index"


def ratio(v) -> int:
    """A walk-forward ratio's OOS side: exactly the int 1, 2 or 3 (2.0 and True are not ratios)."""
    if type(v) is not int or v not in RATIOS:
        raise ValueError(f"test_months: one of {', '.join(str(x) for x in RATIOS)} (the 1:N walk-forward ratio)")
    return v


def stitch_rule(test_months: int = TEST_MONTHS) -> str:
    seq = ", ".join(str(k * test_months) for k in range(3))
    return (f"steps {seq}, … (phase 0), each holding its pick for its full {test_months}-month test window: "
            "the test windows tile the OOS months once each, never overlapping")


STITCH_RULE = stitch_rule()


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


def steps(months: list[str], test_months: int = TEST_MONTHS) -> list[dict]:
    """Step k selects on months[k] and tests on the next `test_months`; a partial last window is dropped."""
    n = len(months) - SELECT_MONTHS - test_months + 1
    return [{"k": k, "select": months[k], "test": months[k + SELECT_MONTHS:k + SELECT_MONTHS + test_months]}
            for k in range(0, max(n, 0), STEP_MONTHS)]


def chain(n_steps: int, phase: int = 0, test_months: int = TEST_MONTHS) -> list[int]:
    """The non-overlapping stitched chain: every `test_months`-th step starting at `phase`."""
    return list(range(phase, n_steps, test_months))


def to_ns(t: dict) -> dict:
    """A trades.json row (entry_ms/exit_ms) back to the engine shape report.* reads."""
    return {**t, "entry_ns": t["entry_ms"] * 1_000_000, "exit_ns": t["exit_ms"] * 1_000_000}


def _stats(trades_ms: list[dict], skipped: list[dict], capital: float, months: list[str] | None = None) -> dict:
    """`months`: a stitched chain's covered months -- its Sharpe day grid spans exactly those months
    (a flat no-pick month at either end is a flat stretch, not outside the record)."""
    tr = sorted((to_ns(t) for t in trades_ms), key=lambda t: (t["exit_ns"], t["entry_ns"]))
    col = report.column(tr, capital, skipped, months)
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
            capital: float, test_months: int = TEST_MONTHS) -> dict:
    """cells: [{i, params, months: {m: stats}}]; trades_of(i) -> (trades_ms, skipped) of a PICKED cell."""
    st = steps(months, test_months)
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

    def stitched(phase: int, side: str = "test") -> tuple[list, list, list[str]]:
        """`side` "test" = the chain's out-of-sample legs; "select" = the very months those picks
        were chosen on, so both sides of the same chain can be read against each other."""
        tr, sk, covered = [], [], []
        for k in chain(len(st), phase, test_months):
            ms = st[k]["test"] if side == "test" else [st[k]["select"]]
            covered += ms
            if rows[k]["cell"] is not None:
                t, s = leg(rows[k]["cell"], ms)
                tr += t
                sk += s
        return tr, sk, covered

    tr0, sk0, covered0 = stitched(0)
    tri, ski, coveredi = stitched(0, "select")
    for k in chain(len(st), 0, test_months):
        rows[k]["stitched"] = True
    trades_ns = sorted((to_ns(t) for t in tr0), key=lambda t: (t["exit_ns"], t["entry_ns"]))
    phases = []
    for p in range(test_months):
        tr, sk, cov = (tr0, sk0, covered0) if p == 0 else stitched(p)
        s = _stats(tr, sk, capital, cov)
        phases.append({"phase": p, "steps": len(chain(len(st), p, test_months)), "net_profit": s["net_profit"],
                       "trades": s["trades"], "sharpe": s["sharpe"]})

    picks = [r["cell"] for r in rows]
    pairs = [(a, b) for a, b in zip(picks, picks[1:]) if a is not None and b is not None]
    counts = Counter(p for p in picks if p is not None)
    top = min(counts.items(), key=lambda kv: (-kv[1], kv[0])) if counts else None
    oos, ins = _stats(tr0, sk0, capital, covered0), _stats(tri, ski, capital, coveredi)

    def per_month(stats: dict, n: int) -> dict | None:
        return None if not n else {"net_profit": round((stats["net_profit"] or 0.0) / n, 2),
                                   "trades": round((stats["trades"] or 0) / n, 4)}

    pm_oos, pm_is = per_month(oos, len(covered0)), per_month(ins, len(coveredi))
    d_pm = None if pm_oos is None or pm_is is None else round(pm_oos["net_profit"] - pm_is["net_profit"], 2)
    tested = set(covered0)
    return {
        "scheme": {"select_months": SELECT_MONTHS, "test_months": test_months, "step_months": STEP_MONTHS,
                   "ratio": f"1:{test_months}",
                   "metric": metric, "metric_label": METRICS.get(metric, metric), "min_trades": min_trades,
                   "tie_break": TIE_BREAK, "stitch": stitch_rule(test_months)},
        "window": {"start": months[0] if months else None, "end": months[-1] if months else None},
        "n_cells": len(cells), "n_steps": len(st), "looks": len(cells) * len(st),
        "steps": rows,
        "stitched": {"stats": oos, "equity": report.equity(trades_ns), "trades": report.to_ms(trades_ns),
                     "months": covered0, "legs": chain(len(st), 0, test_months),
                     "n_months": len(covered0), "per_month": pm_oos,
                     "uncovered": [m for m in months[SELECT_MONTHS:] if m not in tested] if st else []},
        "stitched_is": {"stats": ins, "months": coveredi, "n_months": len(coveredi), "per_month": pm_is},
        # the drop is PER MONTH: the two sides' totals span different month counts (review I2)
        "drop": {"net_profit_per_month": d_pm,
                 "pct": None if d_pm is None or not pm_is["net_profit"]
                 else round(d_pm / abs(pm_is["net_profit"]) * 100, 2),
                 "sharpe": None if oos["sharpe"] is None or ins["sharpe"] is None
                 else round(oos["sharpe"] - ins["sharpe"], 4)},
        "phases": phases,
        "stability": {"changes": sum(1 for a, b in pairs if a != b), "pairs": len(pairs), "distinct": len(counts),
                      "no_pick": sum(1 for p in picks if p is None),
                      "top": {"cell": top[0], "count": top[1]} if top else None},
        "skipped_by_error": sum(r["oos"]["skipped_by_error"] for r in rows if r["oos"]),
    }


def _legs(r: dict) -> dict:
    """The stitched chain's legs (its steps): how many, how many had no pick, how many made money
    out-of-sample. A no-pick leg is flat -- counted as a leg, never as a profitable one."""
    legs = [row for row in r["steps"] if row["stitched"]]
    picked = [row for row in legs if row["oos"] is not None]
    prof = sum(1 for row in picked if (row["oos"]["net_profit"] or 0) > 0)
    return {"n": len(legs), "no_pick": len(legs) - len(picked), "profitable": prof,
            "pct_profitable": round(prof / len(legs) * 100, 2) if legs else None,
            "first_select": legs[0]["select"] if legs else None, "last_select": legs[-1]["select"] if legs else None}


COMPARE_NOTE = ("Same window, grid, costs, Select-by and Min-trades for all three. A longer test length "
                "re-selects less often — one pick every N months, held for N months — so it has fewer "
                "selection points and trades further from the month each pick was made on; and each stitched "
                "out-of-sample chain covers slightly different months (see each scheme's span). "
                "Out-of-sample only: no in-sample number is shown here.")


def compare_summary(results: dict) -> dict:
    """{N: compute(..., test_months=N)} -> the three STITCHED OUT-OF-SAMPLE results side by side.
    Deliberately built from `stitched` alone (never `stitched_is` / `drop` / per-step `is`), so an
    in-sample number cannot leak into the comparison."""
    ns = sorted(results)
    if not ns:
        raise ValueError("compare: no schemes")
    first = results[ns[0]]
    for n in ns:
        r = results[n]
        if r["window"] != first["window"] or r["n_cells"] != first["n_cells"] or \
                {k: r["scheme"][k] for k in ("metric", "min_trades", "select_months", "step_months")} != \
                {k: first["scheme"][k] for k in ("metric", "min_trades", "select_months", "step_months")}:
            raise ValueError("compare: the schemes do not share one window / grid / selection rule")
    cols = []
    for n in ns:
        r, so = results[n], results[n]["stitched"]
        ms = so["months"]
        cols.append({"test_months": n, "ratio": f"1:{n}", "n_steps": r["n_steps"], "looks": r["looks"],
                     "stats": so["stats"], "per_month": so["per_month"], "n_months": so["n_months"],
                     "span": [ms[0], ms[-1]] if ms else None, "uncovered": so["uncovered"],
                     "legs": _legs(r), "equity": so["equity"]})
    sc = first["scheme"]
    return {"compare": True, "window": first["window"], "n_cells": first["n_cells"],
            "scheme": {k: sc[k] for k in ("select_months", "step_months", "metric", "metric_label", "min_trades",
                                          "tie_break")},
            "schemes": cols, "looks": sum(c["looks"] for c in cols), "note": COMPARE_NOTE}


def compare_scheme(start: str | None = None, end: str | None = None) -> dict:
    """scheme() for a compare job: each ratio's step count, and their sum (= looks per cell)."""
    by = {n: scheme(start, end, n) for n in RATIOS}
    base = by[TEST_MONTHS]
    return {**base, "compare": True, "test_months": None, "n_steps": sum(v["n_steps"] for v in by.values()),
            "n_steps_by": {str(n): v["n_steps"] for n, v in by.items()},
            "runnable": all(v["n_steps"] for v in by.values())}


def scheme(start: str | None = None, end: str | None = None, test_months: int = TEST_MONTHS) -> dict:
    """What the page needs before a job exists (review M5: the step count comes from here, not a
    client constant) -- for the ratio and window the picker currently shows. A window too short
    for one full cycle reports 0 steps rather than failing: the page says so in its own words."""
    n = ratio(test_months)                       # an invalid ratio is a 400, never silently 1:3 (review M4)
    s = dt.date.fromisoformat(start) if start else RESEARCH_START
    e = dt.date.fromisoformat(end) if end else RESEARCH_END
    st = steps(month_list(s, e), n)
    return {"n_steps": len(st), "first_select": st[0]["select"] if st else None,
            "last_select": st[-1]["select"] if st else None,
            "select_months": SELECT_MONTHS, "test_months": n, "step_months": STEP_MONTHS,
            "ratios": list(RATIOS), "default_test_months": TEST_MONTHS,
            "window": {"start": s.isoformat(), "end": e.isoformat()},
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
    """The heat-map grid (validate_grid: <= 60 cells, 2-3 axes, its own range) + the walk-forward's
    own fields. ValueError / DisciplineError with a message for the page."""
    if not isinstance(body, dict):
        raise ValueError("the body is a JSON object")
    b = dict(body)
    compare = b.pop("compare", False)
    if type(compare) is not bool:
        raise ValueError("compare: true or false")
    if compare and "test_months" in b:
        raise ValueError("compare runs 1:1, 1:2 and 1:3 together: send it without test_months")
    test_months = ratio(b.pop("test_months", TEST_MONTHS))
    if isinstance(b.get("range"), dict) and b["range"].get("kind") == "is_months":
        raise ValueError("a walk-forward steps whole calendar months, so it cannot run on IS months only "
                         "(Jan/Apr/Jul/Oct): pick a continuous window")
    metric = b.pop("metric", DEFAULT_METRIC)
    if not isinstance(metric, str) or metric not in METRICS:
        raise ValueError(f"metric: one of {', '.join(METRICS)}")
    min_trades = _min_trades(b.pop("min_trades", DEFAULT_MIN_TRADES))
    g = validate_grid(b)
    if not getattr(drafthost.resolve(g["strategy"]), "session_independent", False):   # a draft: its stub
        raise ValueError(f"{g['strategy']}: not flagged session-independent, so a month cannot be sliced "
                         "out of one full-window run -- the walk-forward refuses it")
    for c in g["cells"]:
        c["req"]["propsim"] = False          # the full-window prop sim is never shown here (review M4)
    months = month_list(dt.date.fromisoformat(g["range"]["start"]), dt.date.fromisoformat(g["range"]["end"]))
    if compare:
        by = {n: len(steps(months, n)) for n in RATIOS}
        if not all(by.values()):
            raise ValueError(f"{g['range']['label']}: too short to compare -- 1:{max(RATIOS)} needs one full cycle "
                             f"({SELECT_MONTHS} selection month + {max(RATIOS)} test months of whole calendar months)")
        g["walkforward"] = {"metric": metric, "metric_label": METRICS[metric], "min_trades": min_trades,
                            "select_months": SELECT_MONTHS, "test_months": None, "compare": True,
                            "ratios": list(RATIOS), "step_months": STEP_MONTHS, "months": months,
                            "n_steps": sum(by.values()), "n_steps_by": {str(n): v for n, v in by.items()},
                            "tie_break": TIE_BREAK, "stitch": "; ".join(f"1:{n}: {stitch_rule(n)}" for n in RATIOS)}
        return g
    st = steps(months, test_months)
    if not st:
        raise ValueError(f"{g['range']['label']} at 1:{test_months}: too short for one full walk-forward cycle "
                         f"({SELECT_MONTHS} selection month + {test_months} test month(s) of whole calendar months)")
    g["walkforward"] = {"metric": metric, "metric_label": METRICS[metric], "min_trades": min_trades,
                        "select_months": SELECT_MONTHS, "test_months": test_months, "step_months": STEP_MONTHS,
                        "months": months, "n_steps": len(st), "tie_break": TIE_BREAK,
                        "stitch": stitch_rule(test_months)}
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
    """Walk-forward jobs: a heat-map grid over the job's window (its own dir, no per-cell looks),
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
        want, got = g.get("range") or {}, run.get("range") or {}
        if want and (got.get("kind"), got.get("start"), got.get("end")) != (want.get("kind"), want.get("start"), want.get("end")):
            raise ValueError("a walk-forward cell ran outside the job's own window")
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
        result, err, per = None, None, None
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

                if cfg.get("compare"):
                    per = {n: compute(ins, cfg["months"], trades_of=trades_of, metric=cfg["metric"],
                                      min_trades=cfg["min_trades"], capital=capital, test_months=n)
                           for n in cfg.get("ratios") or RATIOS}
                    result = compare_summary(per)
                else:
                    per = None
                    result = compute(ins, cfg["months"], trades_of=trades_of, metric=cfg["metric"],
                                     min_trades=cfg["min_trades"], capital=capital,
                                     test_months=cfg.get("test_months", TEST_MONTHS))
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
                if per is not None:                 # the schemes first: compare.json existing means all three do
                    for n, r in per.items():
                        write_json(d / f"result-{n}.json", r)
                    write_json(d / "compare.json", result)
                else:
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

    def _done(self, gid: str) -> tuple[Path, dict]:
        d = self.dir(gid)
        st = self.status(gid)
        if st.get("status") != "done":
            raise ValueError(f"walk-forward {gid} is {st.get('status')}, not done")
        return d, st.get("walkforward") or {}

    def result(self, gid: str, test_months: int | None = None) -> dict:
        """A 1:N job's result; for a compare job, scheme 1:`test_months`'s (the same shape).
        ValueError when not done, or when the ratio does not belong to this job."""
        d, cfg = self._done(gid)
        if cfg.get("compare"):
            if test_months is None:
                raise ValueError(f"walk-forward {gid} is a 1:1 · 1:2 · 1:3 comparison: ask for one scheme "
                                 "(test_months=1|2|3), or for the comparison itself")
            n = ratio(test_months)
            if n not in (cfg.get("ratios") or RATIOS):
                raise ValueError(f"walk-forward {gid} has no 1:{n} scheme")
            return read_json(d / f"result-{n}.json")
        if test_months is not None and ratio(test_months) != cfg.get("test_months", TEST_MONTHS):
            raise ValueError(f"walk-forward {gid} is 1:{cfg.get('test_months', TEST_MONTHS)}, not 1:{test_months}")
        return read_json(d / "result.json")

    def compare(self, gid: str) -> dict:
        """A compare job's side-by-side stitched out-of-sample summary."""
        d, cfg = self._done(gid)
        if not cfg.get("compare"):
            raise ValueError(f"walk-forward {gid} is a single 1:{cfg.get('test_months', TEST_MONTHS)} run, not a comparison")
        return read_json(d / "compare.json")

    def cell_bundle(self, gid: str, i: int) -> dict:
        raise KeyError(f"{gid}/{i}: a walk-forward's full-window cells are never served")

    def list(self, limit: int = 20) -> list[dict]:
        out = super().list(limit)
        for g in out:
            j = read_json(self.grids / g["id"] / "grid.json", {}) or {}
            g["metric"] = (j.get("walkforward") or {}).get("metric")
            g["compare"] = bool((j.get("walkforward") or {}).get("compare"))
            g["test_months"] = (j.get("walkforward") or {}).get("test_months")
        return out
