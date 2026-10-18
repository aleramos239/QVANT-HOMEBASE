"""The Lab's group builder (the owner, 2026-10-18): several strategies, each at its own size, judged as ONE account.

For each member its latest finished BUILD-DAYS run is used (never an unseen-days run: those are read once, by the
blueprint, for a locked strategy). Its trades are scaled by the member's size (x0.5, x2 ...: every dollar field), the
members are cut to the days ALL their runs cover, and then:
  * each member's own numbers and the group's (deskgroups.summarize: net, trades, win rate, PF, drawdown, days, the
    daily curve, days two or more traded together);
  * how alike their days are: the Pearson correlation of every pair's daily P&L (a day one did not trade counts 0),
    on the days of the window, and how many days both traded;
  * the prop sim on the merged ledger is the route's (tester_api: _rescore), on the rule set the page picks.
Pure: no file is read or written here.
"""
from __future__ import annotations

import math
from typing import Optional

from . import deskgroups

BUILD_END = "2025-06-30"            # the build days end here (BLUEPRINT); a run that reaches past it is not a build run
MONEY = ("net", "gross", "commission", "mae_usd", "mfe_usd")
SIZE_MIN, SIZE_MAX = 0.1, 20.0
MIN_SHARED_DAYS = 20                # fewer days than this: no correlation is given


def build_run(runs: list[dict]) -> Optional[dict]:
    """The newest finished run on the build days (ends by BUILD_END, no holdout), or None."""
    for r in runs:
        rg = r.get("range") or {}
        if r.get("status") == "done" and not r.get("holdout") and isinstance(rg.get("end"), str) and rg["end"] <= BUILD_END \
                and isinstance(rg.get("start"), str):
            return r
    return None


def scaled(trades: list[dict], k: float) -> list[dict]:
    """The trades at k times the size: every dollar field times k (prices, times and counts unchanged)."""
    out = []
    for t in trades:
        if not isinstance(t, dict):
            continue
        u = dict(t)
        for f in MONEY:
            if isinstance(u.get(f), (int, float)) and not isinstance(u.get(f), bool):
                u[f] = round(u[f] * k, 4)
        out.append(u)
    return out


def window(ranges: list[dict]) -> Optional[tuple[str, str]]:
    """The days every run covers: (latest start, earliest end), or None when they do not overlap."""
    a, b = max(r["start"] for r in ranges), min(r["end"] for r in ranges)
    return (a, b) if a <= b else None


def daily(trades: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for t in trades:
        out[t["date"]] = out.get(t["date"], 0.0) + float(t["net"])
    return out


def pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy), 3)


def correlation(named: list[tuple[str, list[dict]]]) -> dict:
    """{names, matrix: [[r or None]], both: [[days both traded]]}: daily P&L on every day any member traded (0 for a
    member that did not); None when fewer than MIN_SHARED_DAYS days or a member never varies."""
    by = [daily(t) for _, t in named]
    days = sorted(set().union(*[set(d) for d in by])) if by else []
    m, both = [], []
    for i, a in enumerate(by):
        row, brow = [], []
        for j, b in enumerate(by):
            brow.append(sum(1 for d in days if d in a and d in b))
            if i == j:
                row.append(1.0)
                continue
            xs, ys = [a.get(d, 0.0) for d in days], [b.get(d, 0.0) for d in days]
            row.append(pearson(xs, ys) if len(days) >= MIN_SHARED_DAYS else None)
        m.append(row)
        both.append(brow)
    return {"names": [n for n, _ in named], "matrix": m, "both": both, "days": len(days)}


def mix(members: list[dict]) -> dict:
    """members: [{name, size, run (its runs_list row), trades}] -> {window, members: [{name, size, run, summary}],
    group: summary, correlation, ledger (the merged, scaled ledger for the prop sim)}."""
    win = window([m["run"]["range"] for m in members])
    if win is None:
        raise ValueError("these runs share no days: run each on the same build days")
    a, b = win
    named = []
    for m in members:
        t = [x for x in scaled(m["trades"], m["size"]) if isinstance(x.get("date"), str) and a <= x["date"] <= b]
        named.append((m["name"], t))
    ledger, owners = deskgroups.merged(named)
    out = []
    for m, (_, t) in zip(members, named):
        s = deskgroups.summarize(t)
        out.append({"name": m["name"], "size": m["size"], "run": m["run"]["id"], "summary": s})
    return {"window": {"start": a, "end": b}, "members": out, "group": deskgroups.summarize(ledger, owners),
            "correlation": correlation(named), "ledger": ledger}
