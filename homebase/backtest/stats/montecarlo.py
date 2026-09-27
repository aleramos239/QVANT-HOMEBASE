"""Monte Carlo over a finished run's trades: how lucky was the one path the backtest showed?

The resampling unit is the DAY (review C2), the same weekday grid the run's own prop eval uses
(``propsim.weekday_grid``: every Mon-Fri from the first to the last session, a 0-trade weekday
included as a flat day). Each day keeps its own trades in their recorded order. A path SHUFFLES the
days (the same days, a different order -- the default) or BOOTSTRAPS them (drawn with replacement).
It never re-simulates fills: the resample only reorders or redraws what the engine already produced.

Per path:
  * max drawdown $, final net $ and the longest losing streak (in trades) -- walked trade by trade
    through the reordered days, so intraday drawdown inside a day still counts;
  * ruin = the path's max drawdown reaching ``floor`` $ (review I1). The default floor is the prop
    rules' trailing max loss, else $2,000;
  * prop pass = ``propsim.engine.run_eval`` on the reordered (day P&L, traded?) sequence, i.e. the
    LucidFlex race itself -- EOD trailing floor, consistency on the largest DAY, min days on traded
    days. It is not a copy.

Work is capped at ``MAX_WORK`` day-steps (days x paths, review I3), and the result reports the
paths actually used. Money is USD, and drawdowns are <= 0 and include the 0 starting peak (the same
convention as ``stats._max_dd``).
"""
from __future__ import annotations

import hashlib
import random
from itertools import accumulate, chain
from operator import sub
from typing import List, Optional, Sequence

from ..propsim import engine, weekday_grid

__all__ = ["run", "MAX_WORK", "MAX_PATHS", "DEFAULT_FLOOR"]

PCTS = (5, 25, 50, 75, 95)
MAX_PATHS = 10_000
MAX_WORK = 2_000_000          # days x paths per call (review I3)
DEFAULT_FLOOR = 2000.0        # $ drawdown = ruin when no prop rules give a trailing max loss


def _quantile(sorted_xs: Sequence[float], q: float):
    """q in [0, 100], linear interpolation over an already-sorted list."""
    if not sorted_xs:
        return None
    if len(sorted_xs) == 1:
        return sorted_xs[0]
    pos = (q / 100.0) * (len(sorted_xs) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_xs) - 1)
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (pos - lo)


def _percentiles(values: List[float]) -> dict:
    xs = sorted(values)
    return {f"p{p}": _quantile(xs, p) for p in PCTS}


def _histogram(dds: List[float], bins: int = 20) -> dict:
    """Equal-width bins over [min(dds), max(dds)]. A degenerate (single-valued) sample gets
    one bin holding every path, rather than a divide-by-zero."""
    lo, hi = min(dds), max(dds)
    if lo == hi:
        return {"edges": [lo, hi], "counts": [len(dds)]}
    width = (hi - lo) / bins
    counts = [0] * bins
    for d in dds:
        i = int((d - lo) / width)
        if i >= bins:      # the max value falls exactly on the last edge
            i = bins - 1
        counts[i] += 1
    edges = [lo + i * width for i in range(bins + 1)]
    return {"edges": edges, "counts": counts}


def _walk(seq: Sequence[float]) -> tuple[float, float]:
    """(max drawdown <= 0, final net) of one path: the worst fall from the running peak (the 0 start
    counts as a peak), and the running sum's end (sequential adds, as the equity curve itself)."""
    if not seq:
        return 0.0, 0.0
    eq = list(accumulate(seq))
    peaks = accumulate(eq, max, initial=0.0)
    next(peaks)
    return min(0.0, min(map(sub, eq, peaks))), eq[-1]


def seed_for(source_id: str) -> int:
    """The default seed for a run (review I2): derived from its id, so reopening the same run shows
    the same numbers."""
    return int.from_bytes(hashlib.sha256(str(source_id).encode()).digest()[:4], "big")


def run(
    trades: Sequence[dict],
    *,
    paths: int = 5000,
    seed: Optional[int] = None,
    mode: str = "shuffle",
    rules: Optional[dict] = None,
    floor: Optional[float] = None,
    bins: int = 20,
) -> dict:
    """Resample ``trades`` ({date, net}, in recorded order) by day, ``paths`` times (capped at
    MAX_WORK // days).

    ``mode``: "shuffle" (a permutation of the days, so every path's final net is identical) or
    "bootstrap" (days drawn with replacement). ``rules``: a loaded prop-rules dict; when given, each
    path races ``engine.run_eval`` and ``p_prop_pass`` is the pass fraction (None without rules).
    ``floor``: the ruin drawdown in $ (> 0); by default the rules' ``trailing_mll``, else DEFAULT_FLOOR.

    Returns:
      * the p5..p95 of max drawdown $, final net $ and the losing streak (trades);
      * ``p_ruin`` = P(max DD >= floor), and ``p_prop_pass``;
      * a max-DD histogram;
      * ``actual``: the recorded order's own max DD, plus ``worse_than_pct``, the % of resampled
        paths whose DD is strictly less bad (ties never count, review M2).
    """
    if not trades:
        raise ValueError("no trades: nothing to resample")
    if mode not in ("shuffle", "bootstrap"):
        raise ValueError('mode: "shuffle" or "bootstrap"')
    if not 1 <= paths <= MAX_PATHS:
        raise ValueError(f"paths: 1 to {MAX_PATHS:,}")
    if floor is None:
        floor = float(rules["trailing_mll"]) if rules and rules.get("trailing_mll") else DEFAULT_FLOOR
    if isinstance(floor, bool) or not isinstance(floor, (int, float)) or not 0 < floor < 1e12:
        raise ValueError("floor: a drawdown in $ above 0")
    floor = float(floor)

    pnls, flags, dates = weekday_grid(list(trades))
    at = {d: i for i, d in enumerate(dates)}
    day_nets: List[list] = [[] for _ in dates]
    for t in trades:
        day_nets[at[t["date"]]].append(float(t["net"]))
    sig = ["".join("L" if x < 0 else "W" for x in nets) for nets in day_nets]
    n = len(dates)
    used = max(1, min(paths, MAX_WORK // n))
    rng = random.Random(seed)

    dds: List[float] = []
    finals: List[float] = []
    streaks: List[float] = []
    n_ruin = n_pass = 0
    idx = list(range(n))
    for _ in range(used):
        if mode == "shuffle":
            rng.shuffle(idx)            # cumulative, like the pre-fix walk: 1 trade/day reproduces it exactly
            order = idx
        else:
            order = rng.choices(range(n), k=n)
        seq = list(chain.from_iterable(map(day_nets.__getitem__, order)))
        dd, final = _walk(seq)
        dds.append(dd)
        finals.append(final)
        streaks.append(float(max(map(len, "".join(map(sig.__getitem__, order)).split("W")))))
        if -dd >= floor:
            n_ruin += 1
        if rules is not None and engine.run_eval(zip(map(pnls.__getitem__, order), map(flags.__getitem__, order)),
                                                 rules)["outcome"] == "pass":
            n_pass += 1

    actual = _walk([float(t["net"]) for t in trades])[0]
    return {
        "unit": "day", "paths": used, "paths_requested": paths, "capped": used < paths,
        "mode": mode, "seed": seed, "n_trades": len(trades), "n_days": n,
        "drawdown": _percentiles(dds),
        "final_net": _percentiles(finals),
        "losing_streak": _percentiles(streaks),
        "floor": floor, "p_ruin": n_ruin / used,
        "p_prop_pass": (n_pass / used) if rules is not None else None,
        "histogram": _histogram(dds, bins),
        "actual": {"max_dd": actual, "worse_than_pct": 100.0 * sum(1 for d in dds if d > actual) / used},
    }
