"""Monte Carlo over a finished run's trade P&L: how lucky was the one path the backtest showed?

Resamples the trade-level P&L list thousands of times -- by SHUFFLING it (same trades, a
different order; the default) or by BOOTSTRAPPING it (drawn with replacement, so a path can
repeat or drop a trade) -- and reports the spread of outcomes: percentiles of max drawdown,
final net and the longest losing streak, the odds of ruin, and (reusing the prop-eval engine's
own day-race, ``homebase.backtest.propsim.propsim.run_eval``) the odds of passing a prop eval
on that path. It never re-simulates fills: a resample only reorders/redraws the P&L numbers the
engine already produced (the house fill law is unchanged).

Every path is one straight pass over the resampled list, computing drawdown/streak/prop-pass
together (`_walk`) so a 10,000-path x 1,000-trade call — the API route's own ceiling — stays
comfortably under its 2s budget: see ``tests/test_backtest_montecarlo.py``'s own timing test.

Convention: money is USD, matching ``stats.py``; drawdowns are <= 0. ``ruin_threshold`` is an
absolute EQUITY floor (``starting_balance + cumulative P&L``, checked AFTER each trade, never
against the pre-trade starting point itself), default 0.0 -- with the run's own capital as
``starting_balance``, that is "lost the whole starting balance"; a bare P&L list
(``starting_balance`` left at its 0.0 default) makes it "cumulative P&L ever went to zero or
below" instead, which is the honest reading when there is no account size to lose.
"""
from __future__ import annotations

import random
from typing import List, Optional, Sequence

__all__ = ["run"]

PCTS = (5, 25, 50, 75, 95)


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


def _actual_path(pnls: Sequence[float]) -> float:
    """Max drawdown $ of the trades IN THEIR RECORDED ORDER -- the backtest's one real path,
    read against the resampled distribution to say how lucky (or not) it was."""
    peak = worst = run = 0.0
    for p in pnls:
        run += p
        if run > peak:
            peak = run
        else:
            worst = min(worst, run - peak)
    return worst


def _percentile_rank(sorted_xs: Sequence[float], x: float) -> float:
    """% of the sample <= x (0..100) -- bisect_right over an already-sorted list."""
    import bisect
    if not sorted_xs:
        return 0.0
    return 100.0 * bisect.bisect_right(sorted_xs, x) / len(sorted_xs)


def run(
    pnls: Sequence[float],
    *,
    paths: int = 5000,
    seed: Optional[int] = None,
    mode: str = "shuffle",
    starting_balance: float = 0.0,
    rules: Optional[dict] = None,
    ruin_threshold: float = 0.0,
    bins: int = 20,
) -> dict:
    """Resample ``pnls`` (one float per trade, recorded order) ``paths`` times.

    ``mode``: "shuffle" (without replacement -- a permutation; every path's final net is
    IDENTICAL, since it is the same trades reordered) or "bootstrap" (with replacement, via
    ``random.choices`` -- final net varies path to path). "shuffle" is the default: it asks
    "how lucky was the ORDER", not "what if the edge itself were different sized".

    ``rules``: a loaded prop-rules dict (``propsim.load_rules(...)``'s own shape, the LucidFlex
    contract: ``eval_target``/``eval_min_days``/``consistency``/``trailing_mll``/``lock_at``/
    ``lock_floor``). When given, each path also races ``propsim.run_eval`` treating every
    (resampled) trade as one day; ``p_prop_pass`` is the pass fraction. ``None`` skips it
    (``p_prop_pass`` comes back ``None``) -- exactly the callers that never ran a prop eval on
    this ledger in the first place.

    Returns percentiles (p5/p25/p50/p75/p95) of max drawdown $, final net $ and the longest
    losing streak (trades); ``p_ruin``; ``p_prop_pass``; a max-DD histogram; and ``actual`` --
    the recorded-order path's own max DD and where it ranks in the resampled distribution
    (headline text: "the backtest's actual path: DD -$X (percentile P)").
    """
    if not pnls:
        raise ValueError("no trades: nothing to resample")
    if mode not in ("shuffle", "bootstrap"):
        raise ValueError('mode: "shuffle" or "bootstrap"')
    if not 1 <= paths <= 10_000:
        raise ValueError("paths: 1 to 10,000")

    pnls = [float(p) for p in pnls]
    n = len(pnls)
    rng = random.Random(seed)

    r = rules or {}
    eval_target = r.get("eval_target")
    eval_min_days = r.get("eval_min_days")
    consistency = r.get("consistency")
    trailing_mll = r.get("trailing_mll")
    lock_at = r.get("lock_at")
    lock_floor = r.get("lock_floor")

    dds: List[float] = []
    finals: List[float] = []
    streaks: List[int] = []
    n_ruin = 0
    n_pass = 0
    work = list(pnls)
    for _ in range(paths):
        work = rng.choices(pnls, k=n) if mode == "bootstrap" else work
        if mode == "shuffle":
            rng.shuffle(work)

        peak = run_eq = worst = 0.0
        min_eq = float("inf")   # post-trade only (see module docstring): the pre-trade
                                 # baseline of 0.0 is not itself a ruin, whatever the floor is
        cur_loss, max_loss = 0, 0
        floor = -trailing_mll if rules else None
        largest_win_day = 0.0
        trade_days = 0
        outcome = None if rules else "skip"

        for p in work:
            run_eq += p
            if run_eq > peak:
                peak = run_eq
                if outcome is None:
                    floor = lock_floor if peak >= lock_at else peak - trailing_mll
            else:
                d = run_eq - peak
                if d < worst:
                    worst = d
            if run_eq < min_eq:
                min_eq = run_eq
            if p < 0:
                cur_loss += 1
                max_loss = max(max_loss, cur_loss)
            else:
                cur_loss = 0
            if outcome is None:
                if p != 0.0:
                    trade_days += 1
                if p > largest_win_day:
                    largest_win_day = p
                if run_eq <= floor:
                    outcome = "bust"
                elif (run_eq >= eval_target and trade_days >= eval_min_days
                      and largest_win_day <= consistency * run_eq):
                    outcome = "pass"

        dds.append(worst)
        finals.append(run_eq)
        streaks.append(max_loss)
        if starting_balance + min_eq <= ruin_threshold:
            n_ruin += 1
        if outcome == "pass":
            n_pass += 1

    actual_dd = _actual_path(pnls)
    return {
        "paths": paths, "mode": mode, "seed": seed, "n_trades": n,
        "drawdown": _percentiles(dds),
        "final_net": _percentiles(finals),
        "losing_streak": _percentiles([float(s) for s in streaks]),
        "p_ruin": n_ruin / paths,
        "p_prop_pass": (n_pass / paths) if rules else None,
        "histogram": _histogram(dds, bins),
        "actual": {"max_dd": actual_dd, "percentile": _percentile_rank(sorted(dds), actual_dd)},
    }
