# VENDORED from ONYX TRADING onyx/report/stats.py at commit 6ceffe2 (git -C "/Users/ramoscapital/ONYX TRADING" show 6ceffe2:onyx/report/stats.py).
# Do not edit here: re-vendor instead. Stdlib only.
"""The strategy report card — every metric, computed over canonical trades.

One function does the work: :func:`pack` turns a list of ``ledger.Trade`` into a
flat metric dict. :func:`report` applies it to the splits that matter (combined
/ long / short, each of those per year and pooled) and adds the equity curve.

Conventions, stated once:

- **Money is USD** and already net of whatever costs the source applied. There
  is no points/USD duality here — that lives in ``onyx.lab.metrics`` for the
  engine's points-denominated path; a ledger is dollars by the time it lands.
- **Sharpe is annualized from DAILY P&L**: ``mean/sd(sample) * sqrt(252)``, the
  same convention as ``onyx.lab.metrics.sharpe_annual``, so numbers here are
  comparable to every prior finding in this repo. Days are UTC calendar days
  that had a trade; flat days are not padded in. Fewer than 2 days -> 0.0.
- A trade lands on its **exit** day/year (realization), matching
  ``onyx.lab.metrics``'s period breakdown.
- ``avg_loss`` / ``largest_loss`` keep their negative sign; ``smallest_loss`` is
  the least-negative loss. ``payoff_ratio`` = avg_win / |avg_loss|.
- **Streaks** count consecutive winners / losers over the ledger in time order.
  A scratch (pnl == 0) is neither: it breaks both runs and starts neither. Each
  run is reported twice — in TRADES (``*_streak_avg``) and in DOLLARS
  (``*_streak_pnl_*``). The dollar figure is the one that sizes a drawdown: a
  4-trade losing run matters for what it costs, not for being 4 trades long.
- **Run-up / drawdown** come in two flavours and both are reported because they
  answer different questions:
  ``trade_runup``/``trade_drawdown`` are per-trade excursions while the position
  was open (MFE/MAE, only when the source recorded them); ``max_runup`` /
  ``max_drawdown`` are peak-to-trough moves of the cumulative EQUITY CURVE.
- **avg_r_multiple** is only computed when the ledger records what each trade
  risked. Without it the field is ``None`` and ``payoff_ratio`` is the honest
  stand-in — a win/loss ratio is not an R multiple and is not labelled as one.
"""
from __future__ import annotations

import math
import time
from typing import Dict, List, Optional, Sequence

from .ledger import Trade

__all__ = ["pack", "report", "equity_curve", "bootstrap_ev"]

_CAP = 999.0  # no-downside cap, mirrors onyx.lab.metrics / backtest.py


def _mean(v: Sequence[float]) -> Optional[float]:
    return (sum(v) / len(v)) if v else None


def equity_curve(trades: List[Trade]) -> List[float]:
    """Cumulative USD after each trade, starting at 0.0."""
    eq, run = [0.0], 0.0
    for t in trades:
        run += t.pnl
        eq.append(run)
    return eq


def _max_dd(eq: List[float]) -> float:
    peak, worst = float("-inf"), 0.0
    for v in eq:
        peak = max(peak, v)
        worst = min(worst, v - peak)
    return worst  # negative or 0.0


def _max_runup(eq: List[float]) -> float:
    trough, best = float("inf"), 0.0
    for v in eq:
        trough = min(trough, v)
        best = max(best, v - trough)
    return best


def _daily(trades: List[Trade]) -> List[float]:
    """USD per UTC day that traded, date order. Timeless ledgers -> []."""
    if any(t.exit_ts is None for t in trades):
        return []
    by: Dict[int, float] = {}
    for t in trades:
        by[t.exit_ts // 86400] = by.get(t.exit_ts // 86400, 0.0) + t.pnl
    return [by[d] for d in sorted(by)]


def _sharpe(daily: List[float]) -> float:
    n = len(daily)
    if n < 2:
        return 0.0
    m = sum(daily) / n
    sd = math.sqrt(sum((d - m) ** 2 for d in daily) / (n - 1))
    return (m / sd) * math.sqrt(252.0) if sd else 0.0


def _streaks(pnls: List[float]) -> Dict[str, Optional[float]]:
    """Consecutive win runs and loss runs, in trades AND in dollars.

    Scratches break both. ``loss_streak_pnl_*`` keeps its negative sign, so the
    worst run is the most-negative one (``min``), matching ``largest_loss``.
    """
    wins: List[int] = []
    losses: List[int] = []
    win_usd: List[float] = []
    loss_usd: List[float] = []
    run, tot, sign = 0, 0.0, 0
    for p in pnls + [0.0]:  # sentinel flushes the final run
        s = 1 if p > 0 else (-1 if p < 0 else 0)
        if s != sign:
            if sign > 0 and run:
                wins.append(run)
                win_usd.append(tot)
            elif sign < 0 and run:
                losses.append(run)
                loss_usd.append(tot)
            run, tot, sign = 0, 0.0, s
        if s:
            run += 1
            tot += p
    return {
        "win_streak_max": max(wins) if wins else None,
        "win_streak_min": min(wins) if wins else None,
        "win_streak_avg": _mean(wins),
        "win_streak_pnl_avg": _mean(win_usd),
        "win_streak_pnl_best": max(win_usd) if win_usd else None,
        "loss_streak_max": max(losses) if losses else None,
        "loss_streak_min": min(losses) if losses else None,
        "loss_streak_avg": _mean(losses),
        "loss_streak_pnl_avg": _mean(loss_usd),
        "loss_streak_pnl_worst": min(loss_usd) if loss_usd else None,
    }


def pack(trades: List[Trade]) -> dict:
    """The full metric row for one set of trades (order = time order)."""
    n = len(trades)
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_win, gross_loss = sum(wins), abs(sum(losses))
    net = sum(pnls)

    eq = equity_curve(trades)
    daily = _daily(trades)
    avg_win, avg_loss = _mean(wins), _mean(losses)

    if avg_win is not None and avg_loss:
        payoff = avg_win / abs(avg_loss)
    elif avg_win is not None and not losses:
        payoff = _CAP
    else:
        payoff = None

    if gross_loss:
        pf = gross_win / gross_loss
    else:
        pf = _CAP if gross_win > 0 else 0.0

    qtys = [t.qty for t in trades if t.qty is not None]
    runups = [t.runup for t in trades if t.runup is not None]
    dds = [t.drawdown for t in trades if t.drawdown is not None]
    rs = [t.pnl / t.risk for t in trades if t.risk]

    out = {
        "n_trades": n,
        "net": net,
        "gross_profit": gross_win,
        "gross_loss": -gross_loss,
        "win_rate": (len(wins) / n) if n else 0.0,
        "n_wins": len(wins),
        "n_losses": len(losses),
        "n_scratch": n - len(wins) - len(losses),
        "profit_factor": pf,
        "expectancy": (net / n) if n else 0.0,
        "sharpe": _sharpe(daily),
        "n_days": len(daily),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "largest_win": max(wins) if wins else None,
        "largest_loss": min(losses) if losses else None,
        "smallest_win": min(wins) if wins else None,
        "smallest_loss": max(losses) if losses else None,
        "payoff_ratio": payoff,
        "avg_r_multiple": _mean(rs),
        "max_drawdown": _max_dd(eq),
        "max_runup": _max_runup(eq),
        "trade_runup_avg": _mean(runups),
        "trade_runup_max": max(runups) if runups else None,
        "trade_drawdown_avg": _mean(dds),
        "trade_drawdown_max": max(dds) if dds else None,
        "qty_avg": _mean(qtys),
        "qty_max": max(qtys) if qtys else None,
        "qty_min": min(qtys) if qtys else None,
    }
    out.update(_streaks(pnls))
    return out


RUNGS = (0.5, 1.0, 2.0, 4.0)


def _at_rung(trades: List[Trade], k: float) -> List[Trade]:
    """Re-price every trade as if friction had been ``k`` times what it was.

    ``pnl`` is already net of ``cost`` at 1x, so the 1x cost is added back and
    k times it taken out: ``pnl + (1 - k) * cost``.
    """
    return [Trade(
        entry_ts=t.entry_ts, exit_ts=t.exit_ts, side=t.side, qty=t.qty,
        pnl=t.pnl + (1.0 - k) * t.cost,
        runup=t.runup, drawdown=t.drawdown, risk=t.risk, cost=t.cost * k,
    ) for t in trades]


def cost_ladder(trades: List[Trade], rungs=RUNGS) -> dict:
    """Net edge at each friction multiple, plus the rung the edge dies on.

    Every trade must carry ``cost`` (see ``ledger.apply_cost``) — a ladder built
    on a guessed cost basis is worse than no ladder.

    The breakeven multiple is CLOSED FORM, not bisected: total P&L at rung k is
    ``N + (1 - k) * C`` for net ``N`` and total 1x friction ``C``, which is
    linear in k, so it crosses zero exactly once, at ``k = 1 + N / C``.

    IMPORTANT — this is a LOWER BOUND on the damage. It subtracts money and
    nothing else. Real added friction also moves fills: wider slippage changes
    which limits get hit and where stops fill, so trades appear and disappear.
    ``onyx.lab.costcurve.slip_stress`` re-runs the strategy and captures that
    path-dependence; this ladder cannot, and will read too kind whenever fill
    quality is what degrades.

    Win rate is recomputed per rung, not carried over: added friction flips
    marginal winners into losers, and that flip is most of what the ladder is
    for.
    """
    if any(t.cost is None for t in trades):
        n = sum(1 for t in trades if t.cost is None)
        raise ValueError(
            "cost ladder needs a cost on every trade: %d of %d have none. "
            "Supply one with ledger.apply_cost()." % (n, len(trades))
        )
    total_cost = sum(t.cost for t in trades)
    net = sum(t.pnl for t in trades)

    steps = []
    for k in rungs:
        p = pack(_at_rung(trades, k))
        steps.append({
            "mult": k,
            "net": p["net"],
            "expectancy": p["expectancy"],
            "profit_factor": p["profit_factor"],
            "sharpe": p["sharpe"],
            "win_rate": p["win_rate"],
            "max_drawdown": p["max_drawdown"],
            "alive": p["net"] > 0,
        })

    breakeven = (1.0 + net / total_cost) if total_cost > 0 else None
    dies_at = None
    for s in steps:
        if not s["alive"]:
            dies_at = s["mult"]
            break

    return {
        "rungs": steps,
        "total_cost_1x": total_cost,
        "gross": net + total_cost,
        "cost_share_of_gross": (total_cost / (net + total_cost))
                               if (net + total_cost) > 0 else None,
        "breakeven_mult": breakeven,
        "dies_at_rung": dies_at,
        "survives_all": all(s["alive"] for s in steps),
    }


def _year(t: Trade) -> Optional[int]:
    ts = t.exit_ts if t.exit_ts is not None else t.entry_ts
    return time.gmtime(ts).tm_year if ts is not None else None


def _splits(trades: List[Trade]) -> dict:
    return {
        "combined": pack(trades),
        "long": pack([t for t in trades if t.side == "long"]),
        "short": pack([t for t in trades if t.side == "short"]),
    }


def bootstrap_ev(pnls: Sequence[float], sims: int = 10_000,
                 seed: int = 20260801) -> Optional[dict]:
    """Bootstrap 95% CI on EV $/trade + P(EV <= 0) — the IP notebook's edge
    inference, ported. Resamples the trade P&Ls with replacement ``sims``
    times; the spread of the resampled means is the uncertainty of the edge.

    Read: if the CI's lower bound is above zero the edge is statistically
    real on this sample; P(EV <= 0) is the chance the edge is an illusion
    (course yardsticks: < 5% good, > 10% do not trade). Caveat inherited from
    the notebook: a resample cannot produce a loss larger than any in the log,
    so real tail risk is fatter than this shows.
    """
    import random
    import statistics as _st
    if not pnls:
        return None
    rng = random.Random(seed)
    n = len(pnls)
    means = sorted(sum(rng.choices(pnls, k=n)) / n for _ in range(sims))
    q = _st.quantiles(means, n=40, method="inclusive")   # 2.5% steps
    return {
        "ev": sum(pnls) / n,
        "lo": q[0], "hi": q[38],                          # 2.5th / 97.5th pct
        "p_le_zero": sum(1 for m in means if m <= 0) / sims,
        "n": n, "sims": sims,
    }


def wr_stability(trades: List[Trade], min_month_n: int = 5) -> Optional[dict]:
    """Is the win rate one coin or several? Overdispersion of monthly WR.

    Even a constant-p strategy wobbles month to month by luck alone
    (binomial noise ~ sqrt(p*q/n)). phi compares the observed chi-square
    across months to its luck-only expectation (df): phi ~ 1 means the
    monthly win rates look like ONE coin (steady); phi >> 1 means the coin
    itself changes with the regime. Verdict: <=1.3 steady · <=2.0 wobbly ·
    >2.0 regime-driven. Months with fewer than ``min_month_n`` trades are
    excluded. Also reports the worst rolling 3-calendar-month WR — the
    stretch you would actually have to sit through.
    """
    months: Dict[tuple, List[float]] = {}
    for t in trades:
        ts = t.exit_ts if t.exit_ts is not None else t.entry_ts
        if ts is None or t.pnl is None:
            continue
        g = time.gmtime(ts)
        months.setdefault((g.tm_year, g.tm_mon), []).append(t.pnl)
    used = {k: v for k, v in months.items() if len(v) >= min_month_n}
    if len(used) < 3:
        return None
    wins = {k: sum(1 for p_ in v if p_ > 0) for k, v in used.items()}
    ns = {k: len(v) for k, v in used.items()}
    tot_w, tot_n = sum(wins.values()), sum(ns.values())
    p_hat = tot_w / tot_n
    if p_hat <= 0.0 or p_hat >= 1.0:
        return None
    chi2 = sum((wins[k] - ns[k] * p_hat) ** 2 / (ns[k] * p_hat * (1 - p_hat))
               for k in used)
    df = len(used) - 1
    phi = chi2 / df if df else 0.0
    wrs = {k: wins[k] / ns[k] for k in used}
    keys = sorted(used)
    worst3, worst3_n = None, 0
    for i in range(len(keys) - 2):
        kk = keys[i:i + 3]
        w3 = sum(wins[k] for k in kk)
        n3 = sum(ns[k] for k in kk)
        wr3 = w3 / n3
        if worst3 is None or wr3 < worst3:
            worst3, worst3_n = wr3, n3
    verdict = "steady" if phi <= 1.3 else ("wobbly" if phi <= 2.0
                                           else "regime-driven")
    return {
        "phi": phi, "verdict": verdict, "months": len(used),
        "excluded": len(months) - len(used),
        "wr_min": min(wrs.values()), "wr_max": max(wrs.values()),
        "wr_all": p_hat, "worst3": worst3, "worst3_n": worst3_n,
    }


def report(trades: List[Trade]) -> dict:
    """Full report: pooled splits, per-year splits, and the equity curve.

    ``by_year`` is empty for a timeless ledger (a bare P&L list has no dates);
    the pooled block is still valid, and ``dated`` says which case you are in.
    """
    trades = sorted(trades, key=lambda t: (t.exit_ts is None,
                                           t.exit_ts if t.exit_ts is not None else 0))
    years: Dict[int, List[Trade]] = {}
    for t in trades:
        y = _year(t)
        if y is not None:
            years.setdefault(y, []).append(t)

    eq = equity_curve(trades)
    ladder = None
    ladder_by_year = {}
    if trades and all(t.cost is not None for t in trades):
        ladder = cost_ladder(trades)
        # Per-year too: a strategy can clear 4x pooled while the newest era
        # dies at 2x, and the era rule says the newest era is what counts.
        ladder_by_year = {y: cost_ladder(years[y]) for y in sorted(years)}

    return {
        "dated": bool(years),
        "n_trades": len(trades),
        "bootstrap": bootstrap_ev([t.pnl for t in trades]),
        "wr_stability": wr_stability(trades),
        "pooled": _splits(trades),
        "by_year": {y: _splits(years[y]) for y in sorted(years)},
        "cost_ladder": ladder,
        "cost_ladder_by_year": ladder_by_year,
        "equity": eq,
        "equity_ts": [t.exit_ts for t in trades],
        "has_qty": any(t.qty is not None for t in trades),
        "has_risk": any(t.risk for t in trades),
        "has_excursions": any(t.runup is not None for t in trades),
    }
