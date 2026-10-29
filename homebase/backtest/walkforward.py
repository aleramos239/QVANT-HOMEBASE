"""Walk-forward: `fixed` 3:1 blocks only (the owner, 2026-10-25). Rolling and `pick` (below) are RETIRED: their code stays so
old jobs on file still read, and validate_wf refuses to start them (OLD_SCHEMES opens them for their own tests only).

FIXED (the owner, 2026-10-20; spec docs/superpowers/specs/2026-10-20-heatmap-40-and-fixed-box-walkforward-design.md 4.2-4.5).
Every cell of the grid (the hm40 exit cells when the body sends no axes) runs ONCE, as set, on the in-sample months of the
market's 3:1 blocks (range wf_is: 3 months in, the next 1 out, then the next block). No code picks a cell: result.json is
{"scheme": "fixed", "blocks": [{i, is}], "cells": [{i, params, is: <the in-sample table's numbers>, blocks: [{i, is, trades,
win_rate, net}]}]} -- the per-cell in-sample records ARE the product here, so the old rule below ("the full-window per-cell
results are never served") does not apply to `fixed`. The test months are not run, not stored and not named in it.
    pick(id, cell)             the owner's pick: lock.json, written once (another cell is refused)
    oos(id, cell, owner_said)  only the picked cell, only on his words (verbatim, non-empty), once: the claim
                               (oos-claim.json + a line in the machine-wide <shared>/wf-oos-reads.jsonl) is written BEFORE any
                               test month runs; a box (strategy, code stamp, settings, market) read in ANY walk-forward is
                               refused, never read twice;
                               then the cell runs on each test month (range wf_oos, one month a run) as its own job under
                               <base>/walkforward-oos/<job>/; oos_view() reads it back (oos.json once it is over).
Rolling (step_months 1, RETIRED 2026-10-25) was an opt-in: the pick windows step a month, every cell still fixed; its cells run on every
window's pick months (all but the last month), so a test month there is a later window's pick month: it has no unseen
test months and oos() refuses it. Looks: the table counts each cell once.

PICK (RETIRED 2026-10-25) -- the user's old scheme: 1 month to SELECT, the next N months to TEST, stepping monthly, over
whatever window the request names (the range picker's preset; the build days, 2021-09-22 -> 2025-06-30,
by default). A body with no scheme that sends test_months / select_months / compare / metric / min_trades, or a range other
than wf_is, is this one.

Steps. Over the window's whole calendar months m_0..m_k, step k selects on m_k and tests on
m_{k+1}..m_{k+N}. A step whose test window would run past the window's last month is dropped (no partial
test windows), so the build days (whole months 2021-10 .. 2025-06) at N = 3 have 42 steps: select
2021-10 .. 2025-03.

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
month counts (1 per leg in-sample, N per leg out-of-sample: 14 vs 42 on the build days at 1:3), so their raw
totals are not comparable: each side also reports `n_months` and `per_month` (net $ and trades per month,
a flat no-pick month counted as a month), and the drop is taken on the per-month net (in $ and as a %
of the in-sample month) and on Sharpe, which is already a rate. `stitched.uncovered` lists the tail months
the chain never tests out-of-sample. The OOS trades travel with the result for the List of trades tab.

Execution (the per-month cache). Each cell runs ONCE over the whole window as an ordinary
heat-map cell (grid.GridManager: the same `runner exec` child, the machine-wide 2-slot cap, FCFS tickets,
no starts in a quiet window of the override file). Sessions are independent -- a strategy declares it (Strategy.session_independent;
the walk-forward refuses one that does not): its day state resets every session and daily bars come from
the store, not the range -- so a cell's trades inside month m ARE a single run over month m
(tests/test_backtest_walkforward.py pins that on real ticks, gate off and on). A cell skips the full-window
prop sim (request "propsim": false): it would never be shown. When a cell finishes, its per-month stats
are cached in cells/NN/months.json; selection reads only those, and a test leg re-uses the chosen cell's
already-computed trades. 60 cells cost 60 backtests, not 60 x 42.

Looks. Every selection month's grid is a look at every cell: a finished walk-forward adds
cells x steps (e.g. 60 x 42 = 2,520) to the machine-wide looks counter, once, as its result is written.
A cancelled walk-forward, one with a failed cell (no selection is made over a partial grid), or one whose
looks counter is unreadable shows no result and counts nothing. The full-window per-cell results are
never served (no cell bundles, no cell summaries): only selection-month stats of the PICKED cell and
the test legs are shown.

Compare (1:1 · 1:2 · 1:3 side by side). A job submitted with `compare: true` (and no test_months) runs
the grid ONCE -- the cells are exactly a 1:N job's cells, since a cell always runs over the whole window
whatever the ratio -- then selects and stitches it three times, at 1:1, 1:2 and 1:3, from the same
per-month cache. The three schemes therefore share the window, the grid, the costs, Select-by and
Min-trades by construction, cost 1x the backtests (not 3x), and are one job for cancel / progress /
reload-resume, queued through the same 2-slot cap and the override file's quiet windows. Each scheme's full
result is written as result-N.json (the ordinary 1:N result shape, served by `result(id, N)`), and
compare.json holds only their STITCHED OUT-OF-SAMPLE numbers side by side (compare_summary: no
in-sample figure crosses into it). Looks: a month's pick depends only on that month's grid, so the
three schemes make IDENTICAL picks -- one search, over 1:1's selection months (a superset of 1:2's and
1:3's). The job counts cells x the 1:1 steps, times CHOICE_PENALTY (3): choosing the best-looking ratio
from the table is itself a selection, made on out-of-sample numbers. The window must fit a full 1:3
cycle, so no column is ever empty.

Metrics use the report's own conventions (report.column: net of costs, Sharpe on the days that traded only).

    <base>/walkforward/<id>/grid.json         the job: axes, costs, walkforward config, per-cell status
    <base>/walkforward/<id>/cells/NN/         a run dir (+ months.json, the per-month cache)
    <base>/walkforward/<id>/result.json       the steps, the stitched equity + stats (when done)
    <base>/walkforward/<id>/result-N.json     a compare job: scheme 1:N's result (the same shape)
    <base>/walkforward/<id>/compare.json      a compare job: the three stitched OOS side by side
    <base>/walkforward/<id>/lock.json         a fixed job: the owner's pick
    <base>/walkforward/<id>/oos-claim.json    a fixed job: the test-month read, claimed (his words, who, when, code)
    <base>/walkforward/<id>/oos.json          a fixed job: the picked cell's test-month record, once the read is over
"""
from __future__ import annotations

import calendar
import datetime as dt
import json
import math
import os
from collections import Counter
from pathlib import Path

from . import drafthost, report, wfmonths
from .discipline import HOLDOUT_START, RESEARCH_END, RESEARCH_START, parse_range
from .grid import FINAL, GridManager, LooksCorrupt, _looks_lock, add_look, hm40_axes, validate_grid
from .runner import _now, read_json, report_holes, write_json
from .wflayout import ROLL_SELECT, ROLL_STEP, SELECT_MONTHS, STEP_MONTHS, TEST_MONTHS, step_of, steps  # noqa: F401 (re-exported)

RATIOS = (1, 2, 3)
ROLL_STEPS = (4, 1)        # 4 = blocks; 1 = rolling, only when the owner picks it (the Lab's Range, or asking Claude)
METRICS = {"net_profit": "Net $", "sharpe": "Sharpe", "profit_factor": "Profit factor", "t_stat": "t-stat"}
DEFAULT_METRIC = "net_profit"
DEFAULT_MIN_TRADES = 5
MAX_MIN_TRADES = 1000
HOLDOUT = HOLDOUT_START.strftime("%Y-%m")     # the first unseen month
STAT_KEYS = ("net_profit", "trades", "win_rate", "profit_factor", "sharpe", "max_drawdown", "avg_trade", "t_stat",
             "rr", "rr_label", "skipped_by_error")
TIE_BREAK = "best metric (equal to 6 decimals = a tie) → more trades that month → lowest cell index"
SCHEMES = ("fixed", "pick")
# The owner, 2026-10-25: in-sample and out-of-sample are ONLY the 3:1 blocks, every cell fixed. The pick scheme (1:1 / 1:2 / 1:3, the
# code's own pick) and rolling (step 1) start no more; their code stays below so the old jobs on file still read. The one pick-path
# body still allowed is the Desk's own: 3 in, 1 out, blocks, no axes (a promoted strategy as set, nothing searched), and only while
# the Desk starts its own (tester_api.DESKLAB_AUTO_UNSEEN, off since S4).
OLD_SCHEMES = False        # TEST ONLY: True lets the old code's own tests start a pick / rolling job
RETIRED = ("only the 3:1 block walk-forward runs (the owner, 2026-10-25): every cell fixed on the in-sample months of the 3:1 blocks; "
           "rolling and the pick scheme (1:1 / 1:2 / 1:3, the code's own pick) are retired -- send it with scheme fixed, no step_months")
DESK_31_OFF = "The Desk 3:1 run is off: nothing starts the Desk card's walk-forward now."   # S4: DESKLAB_AUTO_UNSEEN is off
PICK_FIELDS = ("test_months", "select_months", "compare", "metric", "min_trades")   # the old scheme's own fields
LOCK, CLAIM, OOS = "lock.json", "oos-claim.json", "oos.json"
READS_LOG = "wf-oos-reads.jsonl"     # in the shared folder (slots.shared_dir), beside the looks counter
STOPPED = "stopped: the read is used, no record"


def ratio(v) -> int:
    """A walk-forward ratio's OOS side: exactly the int 1, 2 or 3 (2.0 and True are not ratios)."""
    if type(v) is not int or v not in RATIOS:
        raise ValueError(f"test_months: one of {', '.join(str(x) for x in RATIOS)} (the 1:N walk-forward ratio)")
    return v


def select_window(select_months, test_months: int) -> int:
    """The selection side: 1 (the 1:N schemes), or ROLL_SELECT for 3:1 -- which tests exactly 1 month."""
    if type(select_months) is not int or select_months not in (SELECT_MONTHS, ROLL_SELECT):
        raise ValueError(f"select_months: {SELECT_MONTHS} or {ROLL_SELECT} (the 3:1 walk-forward)")
    if select_months == ROLL_SELECT and test_months != 1:
        raise ValueError(f"select_months {ROLL_SELECT} is the 3:1 walk-forward: it tests 1 month (test_months 1)")
    return select_months


def ratio_label(test_months: int, select_months: int = SELECT_MONTHS) -> str:
    return f"{select_months}:{test_months}"


def step_window(step_months, select_months: int) -> int:
    """3:1's step: 4 (blocks, the default) or 1 (rolling); the 1:N schemes always step a month."""
    if step_months is None:
        return step_of(select_months)
    if select_months != ROLL_SELECT:
        if step_months != STEP_MONTHS:
            raise ValueError("step_months: only the 3:1 walk-forward steps by blocks")
        return STEP_MONTHS
    if type(step_months) is not int or step_months not in ROLL_STEPS:
        raise ValueError("step_months: 4 (blocks) or 1 (rolling) for the 3:1 walk-forward")
    return step_months


def stitch_rule(test_months: int = TEST_MONTHS, select_months: int = SELECT_MONTHS, step_months: int | None = None) -> str:
    if select_months == ROLL_SELECT and step_of(select_months, step_months) == 1:
        return ("rolling: pick on the last 3 months, trade the next 1, step a month -- every month after the first 3 is "
                "traded on a pick made before it; the picking windows overlap")
    if select_months == ROLL_SELECT:
        return ("blocks: 3 months to pick, the next 1 to trade, then the next block -- every month is in-sample or "
                "out-of-sample, never both")
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


def chain(n_steps: int, phase: int = 0, test_months: int = TEST_MONTHS) -> list[int]:
    """The non-overlapping stitched chain: every `test_months`-th step starting at `phase`."""
    return list(range(phase, n_steps, test_months))


def to_ns(t: dict) -> dict:
    """A trades.json row (entry_ms/exit_ms) back to the engine shape report.* reads."""
    return {**t, "entry_ns": t["entry_ms"] * 1_000_000, "exit_ns": t["exit_ms"] * 1_000_000}


def _stats(trades_ms: list[dict], skipped: list[dict], capital: float) -> dict:
    tr = sorted((to_ns(t) for t in trades_ms), key=lambda t: (t["exit_ns"], t["entry_ns"]))
    col = report.column(tr, capital)
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


def chain_months(months: list[str], test_months: int) -> list[str]:
    """The months the phase-0 stitched chain tests out-of-sample -- fixed by the scheme, not the picks."""
    st = steps(months, test_months)
    return [m for k in chain(len(st), 0, test_months) for m in st[k]["test"]]


def compute(cells: list[dict], months: list[str], *, trades_of, metric: str, min_trades: int,
            capital: float, test_months: int = TEST_MONTHS, shared_months: list[str] | None = None,
            select_months: int = SELECT_MONTHS, step_months: int | None = None) -> dict:
    """cells: [{i, params, months: {m: stats}}]; trades_of(i) -> (trades_ms, skipped) of a PICKED cell
    (at 3:1 of every cell: a 3-month window is scored on its own trades, as one run over those months).

    3:1 (select_months 3, test_months 1): every step is in the chain. Blocks (step 4, the default): no two windows
    share a month, so the in-sample side is the selection months' own record. Rolling (step 1, only when asked for):
    the windows overlap (a month sits in up to 3), so the in-sample side's Sharpe is the legs' mean, its drawdown the
    worst leg's, and it has no curve -- overlapping legs added together would mean nothing.

    `shared_months` (a compare job): also the stitched chain restricted to those months, under the
    key `stitched_shared` -- the caller pops it, so the ordinary result shape is unchanged."""
    st = steps(months, test_months, select_months, step_months)
    rolling = select_months == ROLL_SELECT and step_of(select_months, step_months) == 1
    params = {c["i"]: c["params"] for c in cells}
    cache: dict[int, tuple[list, list]] = {}

    def leg(i: int, ms: list[str]) -> tuple[list, list]:
        if i not in cache:
            cache[i] = trades_of(i)
        tr, sk = cache[i]
        return _in(set(ms), tr), _in(set(ms), sk)

    def scores(sel_ms: list[str]) -> dict:
        if select_months == SELECT_MONTHS:
            return {c["i"]: c["months"].get(sel_ms[0]) for c in cells}
        return {c["i"]: _stats(*leg(c["i"], sel_ms), capital) for c in cells}

    rows, prev = [], None
    for s in st:
        by_cell = scores(s.get("select_ms", [s["select"]]))
        i = pick(by_cell, metric, min_trades) if len(cells) > 1 else cells[0]["i"]     # one cell: nothing to choose
        row = {"k": s["k"], "select": s["select"], "test": [s["test"][0], s["test"][-1]], "cell": i,
               "params": params[i] if i is not None else None, "is": None, "oos": None, "stitched": False,
               "changed": None}
        if i is not None:
            row["is"] = by_cell[i]
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
            ms = st[k]["test"] if side == "test" else st[k].get("select_ms", [st[k]["select"]])
            covered += ms
            if rows[k]["cell"] is not None:
                t, s = leg(rows[k]["cell"], ms)
                tr += t
                sk += s
        return tr, sk, covered

    # the pick for the month after the window: chosen on its last whole months, not tested yet (the Desk's notice)
    nxt = None
    if len(months) >= select_months:
        last = months[-select_months:]
        y, m = map(int, last[-1].split("-"))
        j = pick(scores(last), metric, min_trades) if len(cells) > 1 else cells[0]["i"]
        nxt = {"select": last[0] if len(last) == 1 else f"{last[0]} → {last[-1]}", "select_ms": last,
               "for": f"{y + m // 12}-{m % 12 + 1:02d}", "cell": j, "params": params[j] if j is not None else None}

    tr0, sk0, covered0 = stitched(0)
    tri, ski, coveredi = stitched(0, "select")
    for k in chain(len(st), 0, test_months):
        rows[k]["stitched"] = True
    trades_ns = sorted((to_ns(t) for t in tr0), key=lambda t: (t["exit_ns"], t["entry_ns"]))
    phases = []
    for p in range(test_months):
        tr, sk, _ = (tr0, sk0, covered0) if p == 0 else stitched(p)
        s = _stats(tr, sk, capital)
        phases.append({"phase": p, "steps": len(chain(len(st), p, test_months)), "net_profit": s["net_profit"],
                       "trades": s["trades"], "sharpe": s["sharpe"]})

    picks = [r["cell"] for r in rows]
    pairs = [(a, b) for a, b in zip(picks, picks[1:]) if a is not None and b is not None]
    counts = Counter(p for p in picks if p is not None)
    top = min(counts.items(), key=lambda kv: (-kv[1], kv[0])) if counts else None
    oos, ins = _stats(tr0, sk0, capital), _stats(tri, ski, capital)
    tri_ns = sorted((to_ns(t) for t in tri), key=lambda t: (t["exit_ns"], t["entry_ns"]))
    if rolling:                                 # overlapping windows: each leg's own Sharpe / drawdown
        legs_is = [rows[k]["is"] for k in chain(len(st), 0, test_months) if rows[k]["is"]]
        sh = [x["sharpe"] for x in legs_is if x["sharpe"] is not None]
        dd = [x["max_drawdown"] for x in legs_is if x["max_drawdown"] is not None]
        ins["sharpe"] = round(sum(sh) / len(sh), 4) if sh else None
        ins["max_drawdown"] = max(dd, key=abs) if dd else None

    def per_month(stats: dict, n: int) -> dict | None:
        return None if not n else {"net_profit": round((stats["net_profit"] or 0.0) / n, 2),
                                   "trades": round((stats["trades"] or 0) / n, 4)}

    pm_oos, pm_is = per_month(oos, len(covered0)), per_month(ins, len(coveredi))

    def _side(ms: list[str]) -> dict:
        st_ = _stats(_in(set(ms), tr0), _in(set(ms), sk0), capital)
        return {"stats": st_, "months": ms, "n_months": len(ms), "per_month": per_month(st_, len(ms))}
    d_pm = None if pm_oos is None or pm_is is None else round(pm_oos["net_profit"] - pm_is["net_profit"], 2)
    tested = set(covered0)
    extra = {}
    if shared_months is not None:
        sh = set(shared_months)
        cov = [m for m in covered0 if m in sh]
        trs, sks = _in(sh, tr0), _in(sh, sk0)
        s_st = _stats(trs, sks, capital)
        # a leg only partly inside the shared months counts as ONE step, judged on its shared months alone
        n_leg = no_pick = prof = partial = 0
        for k in chain(len(st), 0, test_months):
            ms = [m for m in st[k]["test"] if m in sh]
            if not ms:
                continue
            n_leg += 1
            partial += len(ms) < len(st[k]["test"])
            if rows[k]["cell"] is None:
                no_pick += 1
            elif sum(t["net"] for t in leg(rows[k]["cell"], ms)[0]) > 0:
                prof += 1
        tns = sorted((to_ns(t) for t in trs), key=lambda t: (t["exit_ns"], t["entry_ns"]))
        extra["stitched_shared"] = {
            "months": cov, "n_months": len(cov), "span": [cov[0], cov[-1]] if cov else None, "stats": s_st,
            "per_month": per_month(s_st, len(cov)), "equity": report.equity(tns),
            "legs": {"n": n_leg, "no_pick": no_pick, "profitable": prof, "partial": partial,
                     "pct_profitable": round(prof / n_leg * 100, 2) if n_leg else None}}
    return {**extra,
        "scheme": {"select_months": select_months, "test_months": test_months, "step_months": step_of(select_months, step_months),
                   "rolling": rolling,
                   "ratio": ratio_label(test_months, select_months),
                   "metric": metric, "metric_label": METRICS.get(metric, metric), "min_trades": min_trades,
                   "tie_break": TIE_BREAK, "stitch": stitch_rule(test_months, select_months, step_months)},
        "window": {"start": months[0] if months else None, "end": months[-1] if months else None},
        "n_cells": len(cells), "n_steps": len(st), "looks": len(cells) * len(st),
        "steps": rows, "next": nxt,
        "stitched": {"stats": oos, "equity": report.equity(trades_ns), "trades": report.to_ms(trades_ns),
                     "months": covered0, "legs": chain(len(st), 0, test_months),
                     "n_months": len(covered0), "per_month": pm_oos,
                     "uncovered": [m for m in months[select_months:] if m not in tested
                                   and m not in {x for s_ in st for x in s_.get("select_ms", ())}] if st else []},
        "stitched_is": {"stats": ins, "months": coveredi, "n_months": len(coveredi), "per_month": pm_is,
                        "equity": None if rolling else report.equity(tri_ns),
                        "trades": None if rolling else report.to_ms(tri_ns)},     # blocks: the in-sample months' own trades (the Desk's prop sim)
        # the stitched out-of-sample record cut at the test days' start: its build-days months and its unseen-days months
        "split": {side: _side(ms) for side, ms in (("build", [m for m in covered0 if m < HOLDOUT]),
                                                   ("unseen", [m for m in covered0 if m >= HOLDOUT]))},
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


def _spread(vals) -> dict | None:
    v = [x for x in vals if x is not None]
    return None if not v else {"min": min(v), "max": max(v), "mean": round(sum(v) / len(v), 4), "n": len(v)}


PHASE_WARNING = "the start month moves these more than the ratio does"


CHOICE_PENALTY = len(RATIOS)   # picking one of the three ratios off the table is a 3-way selection


def compare_looks(n_cells: int, months: list[str]) -> int:
    """One search (the picks are identical across schemes) over 1:1's selection months, x the ratio choice."""
    return n_cells * len(steps(months, min(RATIOS))) * CHOICE_PENALTY


COMPARE_NOTE = ("Same window, grid, costs, Select-by and Min-trades for all three. A longer test length "
                "re-selects less often — one pick every N months, held for N months — so it has fewer "
                "selection points and trades further from the month each pick was made on; and each stitched "
                "out-of-sample chain covers slightly different months (see each scheme's span). "
                "Out-of-sample only: no in-sample number is shown here. But picking the best-looking ratio "
                "from this table is itself a selection made on out-of-sample data — the chosen column is no "
                "longer a clean out-of-sample result (the looks count a ×3 penalty for that choice).")


def compare_results(cells: list[dict], months: list[str], *, trades_of, metric: str, min_trades: int,
                    capital: float, ratios=RATIOS) -> tuple[dict, dict]:
    """({N: the ordinary 1:N result}, the side-by-side summary). The shared block is every metric on
    the months ALL the schemes' stitched chains test (the shortest span, 1:3's), so the columns cover
    identical months; the full spans stay beside it."""
    shared = sorted(set.intersection(*(set(chain_months(months, n)) for n in ratios)))
    per = {n: compute(cells, months, trades_of=trades_of, metric=metric, min_trades=min_trades, capital=capital,
                      test_months=n, shared_months=shared) for n in ratios}
    blocks = {n: per[n].pop("stitched_shared") for n in per}
    return per, compare_summary(per, blocks, shared)


def compare_summary(results: dict, shared_blocks: dict | None = None, shared_months: list[str] | None = None) -> dict:
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
        cols.append({"test_months": n, "ratio": f"1:{n}", "n_steps": r["n_steps"],
                     "stats": so["stats"], "per_month": so["per_month"], "n_months": so["n_months"],
                     "span": [ms[0], ms[-1]] if ms else None, "uncovered": so["uncovered"],
                     "legs": _legs(r), "equity": so["equity"],
                     # the headline is phase 0; the chains started 1 .. N-1 months later are as valid
                     "phases": r["phases"],
                     "phase_spread": {"net_profit": _spread(p["net_profit"] for p in r["phases"]),
                                      "sharpe": _spread(p["sharpe"] for p in r["phases"])},
                     "shared": (shared_blocks or {}).get(n)})
    def gap(nets):
        return None if not nets else round(max(nets) - min(nets), 2)
    gap_full = gap([c["stats"]["net_profit"] or 0.0 for c in cols])
    gap_shared = gap([c["shared"]["stats"]["net_profit"] or 0.0 for c in cols if c.get("shared")]) \
        if all(c.get("shared") for c in cols) else None
    widest = max(((c["phase_spread"]["net_profit"] or {}).get("max", 0) - (c["phase_spread"]["net_profit"] or {}).get("min", 0))
                 for c in cols)
    sc = first["scheme"]
    return {"compare": True, "window": first["window"], "n_cells": first["n_cells"],
            "scheme": {k: sc[k] for k in ("select_months", "step_months", "metric", "metric_label", "min_trades",
                                          "tie_break")},
            "schemes": cols, "note": COMPARE_NOTE,
            # the picks are the same in every scheme: one search over the most selection months, x3 for the choice
            "looks": first["n_cells"] * max(r["n_steps"] for r in results.values()) * CHOICE_PENALTY,
            "looks_basis": {"cells": first["n_cells"], "select_months": max(r["n_steps"] for r in results.values()),
                            "choice_penalty": CHOICE_PENALTY},
            "shared_months": None if shared_months is None else {
                "months": shared_months, "n": len(shared_months),
                "span": [shared_months[0], shared_months[-1]] if shared_months else None},
            # the phase spread (full-span chains) against EITHER headline gap; the quoted gap prefers the
            # shared-months one, the default view
            "phase_check": _phase_check(round(widest, 2), gap_shared, gap_full)}


def _phase_check(widest: float, gap_shared: float | None, gap_full: float) -> dict:
    over_shared = gap_shared is not None and widest > gap_shared
    quoted = "shared" if over_shared else ("full" if widest > gap_full else None)
    return {"widest_phase_spread": widest, "gap_shared": gap_shared, "gap_full": gap_full,
            "warning": PHASE_WARNING if quoted else None, "gap_quoted": quoted,
            "gap_quoted_value": {"shared": gap_shared, "full": gap_full}.get(quoted)}


def compare_scheme(start: str | None = None, end: str | None = None) -> dict:
    """scheme() for a compare job: the 1:1 selection months (one search -- the picks are identical across
    schemes), each ratio's step count, and the x3 choice penalty (looks per cell = n_steps x penalty)."""
    by = {n: scheme(start, end, n) for n in RATIOS}
    base = by[TEST_MONTHS]
    n1 = by[min(RATIOS)]["n_steps"]
    return {**base, "compare": True, "test_months": None, "n_steps": n1, "choice_penalty": CHOICE_PENALTY,
            "looks_per_cell": n1 * CHOICE_PENALTY,
            "n_steps_by": {str(n): v["n_steps"] for n, v in by.items()},
            "runnable": all(v["n_steps"] for v in by.values())}


def scheme(start: str | None = None, end: str | None = None, test_months: int = TEST_MONTHS,
           select_months: int = SELECT_MONTHS, step_months: int | None = None) -> dict:
    """What the page needs before a job exists (review M5: the step count comes from here, not a
    client constant) -- for the ratio and window the picker currently shows. A window too short
    for one full cycle reports 0 steps rather than failing: the page says so in its own words."""
    n = ratio(test_months)                       # an invalid ratio is a 400, never silently 1:3 (review M4)
    sel = select_window(select_months, n)
    step = step_window(step_months, sel)
    s = dt.date.fromisoformat(start) if start else RESEARCH_START
    e = dt.date.fromisoformat(end) if end else RESEARCH_END
    st = steps(month_list(s, e), n, sel, step)
    return {"n_steps": len(st), "first_select": st[0]["select"] if st else None,
            "last_select": st[-1]["select"] if st else None,
            "select_months": sel, "test_months": n, "step_months": step,
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
    sch = b.pop("scheme", None)
    if sch is None:     # fixed is the default; an old body (the pick's own fields, or a window of its own) keeps its scheme
        own_window = isinstance(b.get("range"), dict) and b["range"].get("kind") != "wf_is"
        sch = "pick" if own_window or any(k in b for k in PICK_FIELDS) else "fixed"
    if sch not in SCHEMES:
        raise ValueError("scheme: fixed (every cell as set; the owner picks one) or pick (the code picks a cell each window)")
    if sch == "fixed":
        return validate_fixed(b)
    compare = b.pop("compare", False)
    if type(compare) is not bool:
        raise ValueError("compare: true or false")
    if compare and "test_months" in b:
        raise ValueError("compare runs 1:1, 1:2 and 1:3 together: send it without test_months")
    test_months = ratio(b.pop("test_months", TEST_MONTHS))
    select_months = b.pop("select_months", SELECT_MONTHS)
    if compare and select_months != SELECT_MONTHS:
        raise ValueError("compare runs 1:1, 1:2 and 1:3 together: send it without select_months")
    select_months = select_window(select_months, test_months)
    step_months = step_window(b.pop("step_months", None), select_months)
    # Only the Desk's own run of a promoted strategy as set stays: 3 months in, the next 1 out, blocks, no axes (nothing searched)
    if not OLD_SCHEMES and (compare or (select_months, test_months, step_months) != (3, 1, 4) or b.get("axes")):
        raise ValueError(RETIRED)
    said = b.pop("owner_said", None)
    if not OLD_SCHEMES:              # that body's stitched result is the test months: only the Desk's own start sends it (S4)
        from ..charts import tester_api      # noqa: PLC0415 -- the Desk's switch lives there (the tests patch it there)
        # or the owner's typed words (2026-10-28: "add a path that starts the Desk card's 3:1 run only on my typed words")
        if not tester_api.DESKLAB_AUTO_UNSEEN and not (isinstance(said, str) and said.strip() and len(said) <= tester_api.BP_SAID_MAX):
            raise ValueError(DESK_31_OFF)
    if isinstance(b.get("range"), dict) and b["range"].get("kind") == "is_months":
        raise ValueError("a walk-forward steps whole calendar months, so it cannot run on IS months only "
                         "(Jan/Apr/Jul/Oct): pick a continuous window")
    if isinstance(b.get("range"), dict) and b["range"].get("kind") in ("wf_is", "wf_oos"):
        raise ValueError("this walk-forward picks its own months: the 3:1 block months (wf_is / wf_oos) are for "
                         "single runs: pick a continuous window")
    metric = b.pop("metric", DEFAULT_METRIC)
    if not isinstance(metric, str) or metric not in METRICS:
        raise ValueError(f"metric: one of {', '.join(METRICS)}")
    min_trades = _min_trades(b.pop("min_trades", DEFAULT_MIN_TRADES))
    g = validate_grid(b, min_axes=0)      # 0-3 axes: none = one cell, the strategy as set; one = the best of its values
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
                            "n_steps": by[min(RATIOS)], "choice_penalty": CHOICE_PENALTY,
                            "looks_per_cell": by[min(RATIOS)] * CHOICE_PENALTY,
                            "n_steps_by": {str(n): v for n, v in by.items()},
                            "tie_break": TIE_BREAK, "stitch": "; ".join(f"1:{n}: {stitch_rule(n)}" for n in RATIOS)}
        return g
    st = steps(months, test_months, select_months, step_months)
    if not st:
        raise ValueError(f"{g['range']['label']} at {ratio_label(test_months, select_months)}: too short for one "
                         f"full walk-forward cycle ({select_months} selection month(s) + {test_months} test month(s) "
                         "of whole calendar months)")
    g["walkforward"] = {"metric": metric, "metric_label": METRICS[metric], "min_trades": min_trades,
                        "select_months": select_months, "test_months": test_months, "step_months": step_months,
                        "months": months, "n_steps": len(st), "tie_break": TIE_BREAK,
                        "stitch": stitch_rule(test_months, select_months, step_months)}
    return g


def _month_end(m: str) -> str:
    y, mo = map(int, m.split("-"))
    return f"{m}-{calendar.monthrange(y, mo)[1]:02d}"


def _next_month(m: str) -> str:
    y, mo = map(int, m.split("-"))
    return f"{y + mo // 12}-{mo % 12 + 1:02d}"


def validate_fixed(b: dict) -> dict:
    """The fixed scheme (module docstring): the grid on the 3:1 in-sample months, nothing to pick by code."""
    bad = [k for k in PICK_FIELDS if k in b]
    if bad:
        raise ValueError(f"{', '.join(bad)}: the fixed walk-forward picks nothing (the owner picks a cell): send it without them")
    step = b.pop("step_months", ROLL_STEP)
    if step != ROLL_STEP and not OLD_SCHEMES:
        raise ValueError(RETIRED)
    if type(step) is not int or step not in ROLL_STEPS:
        raise ValueError("step_months: 4 (blocks) or 1 (rolling)")
    rng = b.get("range")
    if rng is not None and not (isinstance(rng, dict) and rng.get("kind") == "wf_is"):
        raise ValueError("the fixed walk-forward runs on the 3:1 in-sample months: send it without a range")
    cls = drafthost.resolve(b.get("strategy"))
    bl = wfmonths.blocks(cls.root)
    if not bl:
        raise ValueError(f"{cls.root}: no whole 3:1 block of months on disk yet")
    if step == ROLL_STEP:
        layout = [{"i": x["i"], "is": list(x["is"])} for x in bl]
        b["range"] = {"kind": "wf_is", "root": cls.root}
    else:                                  # rolling: the same months, the pick windows step a month
        ms = sorted({m for x in bl for m in (*x["is"], x["oos"])})
        layout = [{"i": k, "is": st["select_ms"]} for k, st in enumerate(steps(ms, 1, ROLL_SELECT, 1))]
        b["range"] = {"kind": "custom", "start": f"{ms[0]}-01", "end": _month_end(ms[-2]), "root": cls.root}    # root: skip its gappy days
    b.setdefault("axes", hm40_axes(cls))
    g = validate_grid(b, min_axes=0)
    if not getattr(cls, "session_independent", False):
        raise ValueError(f"{g['strategy']}: not flagged session-independent, so a month cannot be sliced "
                         "out of one run -- the walk-forward refuses it")
    for c in g["cells"]:
        c["req"]["propsim"] = False
    g["walkforward"] = {"scheme": "fixed", "step_months": step, "rolling": step == 1, "root": cls.root,
                        "months": sorted({m for x in layout for m in x["is"]}), "blocks": layout, "n_blocks": len(layout),
                        "stitch": stitch_rule(1, ROLL_SELECT, step), "own_stop": bool(getattr(cls, "own_stop", False))}
    return g


def _pct(a, n):
    return round(a / n * 100, 4) if n else None


def is_numbers(trades_ms: list[dict], skipped: list[dict], capital: float, months: list[str]) -> dict:
    """One record's numbers (spec 4.3) at 1 contract after costs, rates in %: report.column's own (net, PF, daily Sharpe,
    max drawdown, win rate), and the rest from the same trades. Month win rates count months of 3 trades or more;
    months_pos counts the months with trades (research hmwf's rule)."""
    tr = sorted((to_ns(t) for t in trades_ms), key=lambda t: (t["exit_ns"], t["entry_ns"]))
    col = report.column(tr, capital)
    rr = col["rr"]
    be = 100 / (1 + rr) if rr else None
    by: dict[str, list[float]] = {}
    for t in trades_ms:
        by.setdefault(t["date"][:7], []).append(t["net"])
    wr = [sum(x > 0 for x in v) / len(v) * 100 for v in by.values() if len(v) >= 3]
    wdays = sum(1 for m in months for d in range(1, calendar.monthrange(*map(int, m.split("-")))[1] + 1)
                if dt.date(*map(int, m.split("-")), d).weekday() < 5)
    al = abs(col["avg_loss"]) if col["avg_loss"] else None
    return {"win_rate": col["win_rate"], "breakeven": be,
            "wr_minus_be": None if be is None or col["win_rate"] is None else col["win_rate"] - be,
            "trades": col["trades"], "per_week": round(col["trades"] / (wdays / 5), 4) if wdays else None,
            "avg_trade": col["avg_trade"], "avg_r": col["avg_trade"] / al if col["avg_trade"] is not None and al else None,
            "net": col["net_profit"], "pf": col["profit_factor"], "sharpe": col["sharpe"], "max_dd": col["max_drawdown"],
            "months_pos": _pct(sum(sum(v) > 0 for v in by.values()), len(by)),
            "months_wr60": _pct(sum(w >= 60 for w in wr), len(wr)), "worst_month_wr": min(wr) if wr else None,
            "long_net": round(sum(t["net"] for t in trades_ms if t["side"] == "long"), 2),
            "short_net": round(sum(t["net"] for t in trades_ms if t["side"] == "short"), 2),
            "skipped_by_error": sum(1 for x in skipped if x["reason"].startswith("strategy error"))}


def _block_row(i, ms_key: str, ms: list[str], tr: list[dict]) -> dict:
    t = _in(set(ms), tr)
    return {"i": i, ms_key: ms if ms_key == "is" else ms[0], "trades": len(t),
            "win_rate": _pct(sum(x["net"] > 0 for x in t), len(t)), "net": round(sum(x["net"] for x in t), 2)}


def fixed_result(cells: list[dict], cfg: dict, *, trades_of, capital: float) -> dict:
    """result.json of a fixed job: every cell's in-sample record and its block rows. No test month is in it."""
    ms, out = cfg["months"], []
    for c in cells:
        tr, sk = trades_of(c["i"])
        tr, sk = _in(set(ms), tr), _in(set(ms), sk)
        out.append({"i": c["i"], "params": c["params"], "is": is_numbers(tr, sk, capital, ms),
                    "blocks": [_block_row(b["i"], "is", b["is"], tr) for b in cfg["blocks"]]})
    return {"scheme": "fixed", "step_months": cfg["step_months"], "rolling": cfg["rolling"], "stitch": cfg["stitch"],
            "window": {"start": ms[0], "end": ms[-1]}, "months": ms, "blocks": cfg["blocks"],
            "n_cells": len(cells), "looks": len(cells), "cells": out}


def _write_once(path: Path, data: dict) -> dict | None:
    """data written at `path` in one step, never over a file on file (two at once: one wins); None when it was there."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(3).hex()}")
    tmp.write_text(json.dumps(data, separators=(",", ":")))
    try:
        os.link(tmp, path)
    except FileExistsError:
        return None
    finally:
        tmp.unlink()
    return data


class _OosReads(GridManager):
    """The test-month runs of a picked cell (one job a read, one wf_oos month a cell). Built and refused by
    WalkForwardManager.oos, never by a body from outside."""

    SUBDIR = "walkforward-oos"
    COUNT_CELL_LOOKS = False

    def _validate(self, body) -> dict:
        return body


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
        self.reads = _OosReads(self.base, archive=self.archive, cache=self.cache, python=self.python,
                               workers=self.workers, slots=self.slots, shared=self.shared)

    def shutdown(self) -> None:
        super().shutdown()
        self.reads.shutdown()

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

                if cfg.get("scheme") == "fixed":
                    per = None
                    result = fixed_result(ins, cfg, trades_of=trades_of, capital=capital)
                elif cfg.get("compare"):
                    per, result = compare_results(ins, cfg["months"], trades_of=trades_of, metric=cfg["metric"],
                                                  min_trades=cfg["min_trades"], capital=capital,
                                                  ratios=tuple(cfg.get("ratios") or RATIOS))
                else:
                    per = None
                    result = compute(ins, cfg["months"], trades_of=trades_of, metric=cfg["metric"],
                                     min_trades=cfg["min_trades"], capital=capital,
                                     test_months=cfg.get("test_months", TEST_MONTHS),
                                     select_months=cfg.get("select_months", SELECT_MONTHS),
                                     step_months=cfg.get("step_months"))
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
        if cfg.get("scheme") == "fixed":
            if test_months is not None:
                raise ValueError(f"walk-forward {gid} is a fixed one: it has no 1:N scheme")
            res = read_json(d / "result.json")
            res["lock"] = read_json(d / LOCK)
            if (d / CLAIM).exists():                # only once the owner said to run the test months
                res["oos"] = self.oos_view(gid)
            return res
        if test_months is not None and ratio(test_months) != cfg.get("test_months", TEST_MONTHS):
            raise ValueError(f"walk-forward {gid} is {ratio_label(cfg.get('test_months', TEST_MONTHS), cfg.get('select_months', SELECT_MONTHS))}, "
                             f"not 1:{test_months}")
        return read_json(d / "result.json")

    def compare(self, gid: str) -> dict:
        """A compare job's side-by-side stitched out-of-sample summary."""
        d, cfg = self._done(gid)
        if not cfg.get("compare"):
            raise ValueError(f"walk-forward {gid} is a single 1:{cfg.get('test_months', TEST_MONTHS)} run, not a comparison")
        return read_json(d / "compare.json")

    def cell_bundle(self, gid: str, i: int) -> dict:
        raise KeyError(f"{gid}/{i}: a walk-forward's full-window cells are never served")

    # ---- a fixed job: the owner's pick, then the test months on his word

    def _fixed(self, gid: str) -> tuple[Path, dict, dict]:
        d, cfg = self._done(gid)
        if cfg.get("scheme") != "fixed":
            raise ValueError(f"walk-forward {gid} is not a fixed one: the code picked its cells, there is nothing to pick")
        return d, cfg, read_json(d / "result.json")

    @staticmethod
    def _cell(res: dict, cell) -> dict:
        hit = next((c for c in res["cells"] if c["i"] == cell), None) if type(cell) is int else None
        if hit is None:
            raise ValueError(f"cell: one of the table's cells, 0 to {len(res['cells']) - 1}")
        return hit

    def pick(self, gid: str, cell, who: str = "owner") -> dict:
        """THE OWNER'S PICK: lock.json, written once. The same cell again: the lock on file; another: refused."""
        d, cfg, res = self._fixed(gid)
        c = self._cell(res, cell)
        req = read_json(d / "cells" / f"{cell:02d}" / "request.json") or {}
        lock = {"cell": cell, "params": c["params"], "code": req.get("draft_sha256") or req.get("strategy"),
                "at": _now(), "who": who}
        if _write_once(d / LOCK, lock) is None:
            was = read_json(d / LOCK) or {}
            if was.get("cell") != cell:
                raise ValueError(f"cell {was.get('cell')} is picked already ({was.get('at')}, {was.get('who')}): "
                                 "the pick is locked")
            return was
        return lock

    def oos(self, gid: str, cell, owner_said, who: str = "owner") -> dict:
        """THE TEST MONTHS of the picked cell, on the owner's words, once (module docstring). Every refusal comes first;
        then the claim; only then a test month runs. -> oos_view()."""
        d, cfg, res = self._fixed(gid)
        lock = read_json(d / LOCK)
        if lock is None:
            raise ValueError(f"walk-forward {gid}: no cell is picked yet: the owner picks one first, then says to run it")
        if not isinstance(owner_said, str) or not owner_said.strip():
            raise ValueError("the test months run only on the owner's word (owner_said is empty)")
        self._cell(res, cell)
        if cell != lock["cell"]:
            raise ValueError(f"cell {cell}: the picked cell is {lock['cell']}: only it runs")
        if cfg.get("rolling"):
            raise ValueError("a rolling walk-forward has no unseen test months (each one is a later window's pick month, "
                             "already run): read the blocks instead")
        if (d / CLAIM).exists():
            raise ValueError(f"walk-forward {gid} cell {cell}: its test months are read already: shown, never run again")
        req = read_json(d / "cells" / f"{cell:02d}" / "request.json") or {}
        base = {k: v for k, v in req.items() if k not in ("id", "created")}
        months = [_next_month(b["is"][-1]) for b in cfg["blocks"]]
        runs = [{"i": j, "params": {"month": m}, "coords": [j],
                 "req": {**base, "range": parse_range({"kind": "wf_oos", "root": cfg["root"], "month": m}).to_dict()}}
                for j, m in enumerate(months)]
        claim = {"walkforward": gid, "strategy": req.get("strategy"), "cell": cell, "params": lock["params"],
                 "code": lock.get("code"), "root": cfg["root"], "owner_said": owner_said, "who": who, "at": _now(),
                 "settings": {"inputs": req.get("inputs"), "controls": req.get("controls") or {}}}   # the whole box, not the axes
        box = lambda x: (x.get("strategy"), x.get("code"), x.get("settings"), x.get("root"))   # noqa: E731 -- a box, not a job
        log = self.shared / READS_LOG          # the machine-wide one-read log (every checkout), checked and added to at once
        with _looks_lock(log):
            try:
                seen = [json.loads(x) for x in log.read_text().splitlines() if x.strip()]
            except FileNotFoundError:
                seen = []
            was = next((x for x in seen if box(x) == box(claim)), None)
            if was is not None:
                raise ValueError(f"its test months were read on {str(was.get('at'))[:10]} in walk-forward {was.get('walkforward')}: "
                                 "shown there, never run again")
            if _write_once(d / CLAIM, claim) is None:
                raise ValueError(f"walk-forward {gid} cell {cell}: its test months are read already: shown, never run again")
            with open(log, "a", encoding="utf-8") as fh:     # written before any test month runs
                fh.write(json.dumps(claim) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        try:
            oid = self.reads.submit({"strategy": req.get("strategy"), "walkforward": gid, "cell": cell, "cells": runs})
        except Exception as e:  # noqa: BLE001 -- claimed: the read is used, and says why
            write_json(d / OOS, {"state": "stopped", "say": STOPPED, "cell": cell, "error": f"{type(e).__name__}: {e}"})
            raise ValueError(f"the test months of cell {cell} did not start ({e}): the read is used, never run again") from e
        write_json(d / "oos-job.json", {"id": oid})
        return self.oos_view(gid)

    def oos_view(self, gid: str) -> dict:
        """The read of a fixed job: {"state": "none"} before one; queued/running with progress; "done" with the record
        (the in-sample table's columns) and one row a block; "stopped" when it did not finish (it is not run again)."""
        d = self.dir(gid)
        got = read_json(d / OOS)
        if got is not None:
            return got
        claim = read_json(d / CLAIM)
        if claim is None:
            return {"state": "none"}
        oid = (read_json(d / "oos-job.json") or {}).get("id")
        if not oid:                             # claimed, its job never written: a restart between the two
            age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(claim["at"])).total_seconds()
            if age < 60:
                return {"state": "queued", "cell": claim["cell"]}
            out = {"state": "stopped", "say": STOPPED, "cell": claim["cell"], "error": "the read did not start"}
            write_json(d / OOS, out)
            return out
        st = self.reads.status(oid)
        if st.get("status") not in FINAL:
            return {"state": st.get("status"), "cell": claim["cell"], "job": oid, "done": st.get("done"), "total": st.get("total")}
        bad = [c for c in st["cells"] if c["status"] != "done"]
        if st["status"] != "done" or bad:
            out = {"state": "stopped", "say": STOPPED, "cell": claim["cell"], "job": oid,
                   "error": (bad[0].get("error") if bad else None) or st.get("error") or st["status"]}
        else:
            cfg = (read_json(d / "grid.json") or {}).get("walkforward") or {}
            tr, sk, months = [], [], []
            for c in st["cells"]:
                cdir = self.reads.cell_dir(oid, c["i"])
                tr += read_json(cdir / "trades.json") or []
                sk += _run_skipped(read_json(cdir / "run.json"))
                months.append(c["params"]["month"])
            capital = (read_json(d / "grid.json") or {}).get("capital", 50_000.0)
            out = {"state": "done", "cell": claim["cell"], "job": oid, "params": claim["params"], "months": months,
                   "record": is_numbers(tr, sk, capital, months),
                   "blocks": [_block_row(b["i"], "oos", [m], tr) for b, m in zip(cfg["blocks"], months)],
                   "equity": report.equity(sorted((to_ns(t) for t in tr), key=lambda t: (t["exit_ns"], t["entry_ns"]))),
                   "owner_said": claim["owner_said"], "at": claim["at"]}
        write_json(d / OOS, out)
        return out

    def same_done(self, body) -> str | None:
        """The newest FINISHED job that Run with this body would only repeat: the same settings, months and boxes, each box's
        run request the same to its code (the Lab shows it on opening a strategy instead of running it again). None: no such job."""
        norm = lambda x: json.loads(json.dumps(x, default=str))  # noqa: E731
        g = norm(self._validate(body))
        want = [c["req"] for c in g.pop("cells")]
        for d in sorted((p for p in self.grids.iterdir() if f"-{g['strategy']}-" in p.name), key=lambda p: p.name, reverse=True):
            st = read_json(d / "grid.json", {}) or {}
            if st.get("status") != "done" or len(st.get("cells") or []) != len(want) or any(st.get(k) != v for k, v in g.items()):
                continue
            got = [read_json(d / "cells" / f"{i:02d}" / "request.json", {}) or {} for i in range(len(want))]
            if all({k: v for k, v in r.items() if k not in ("id", "created")} == w for r, w in zip(got, want)):
                return d.name
        return None

    def list(self, limit: int = 20) -> list[dict]:
        out = super().list(limit)
        for g in out:
            g.update(self._on_file(self.grids / g["id"] / "grid.json", _wf_row))
        return out


def _wf_row(j: dict) -> dict:
    """What a walk-forward's /walkforwards row adds to its grid's."""
    w = j.get("walkforward") or {}
    return {"metric": w.get("metric"), "compare": bool(w.get("compare")), "test_months": w.get("test_months"),
            "select_months": w.get("select_months", SELECT_MONTHS), "scheme": w.get("scheme", "pick")}
