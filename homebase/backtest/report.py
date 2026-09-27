"""The tester's report: TradingView's performance summary (All / Long / Short) on the
vendored stats (homebase/backtest/stats), plus the desk's own numbers.

Conventions (stated once):
  * every money figure is USD, net of commission and of the slippage already in the
    fill prices; drawdowns and losses keep their negative sign;
  * Sharpe/Sortino basis (amended — see `sharpe_basis`): the vendored stats' own
    `_sharpe` averages DAILY P&L over TRADED days only (flat days not padded), which
    inflates a sparse book — an event strategy trading ~24 days/year reads ~3x too
    high, since the traded-day sample excludes every 0-P&L weekday a real account
    still sits through. The report computes Sharpe/Sortino on the WEEKDAY GRID
    instead: every Mon-Fri from the trades' first to last session date gets a daily
    net (0.0 when nothing traded that day), using the identical grid
    `homebase.backtest.propsim.weekday_grid` builds for the prop-eval Monte Carlo —
    except a date the engine SKIPPED (a strategy error or a coverage/data hole) is
    dropped from the grid entirely rather than counted as a flat day, since it is a
    hole in the record, not a real no-trade session. `sharpe`/`sortino` are this
    grid figure; `sharpe_traded_days` keeps the old traded-days-only number for
    reference. Sortino = mean / sqrt(mean(min(day, 0)^2)) x sqrt(252) over the same
    grid;
  * t-stat = the per-trade mean over its standard error (sample sd / sqrt(n));
  * RR = avg win / |avg loss|, shown as "1:X";
  * % figures are against `capital` (the run's account size, default $50,000):
    net % = net / capital, drawdown % = the worst fall from an equity peak.
    `equity()` is CUMULATIVE NET starting at 0 (not capital-based): it is a
    P&L curve, not an account balance — add `capital` yourself for a balance.

Skips: a session the engine could not trade (a strategy exception, caught and
recorded as `skip = "strategy error: <msg>"`; or a coverage/data gap) never
becomes a trade row, so it is invisible to `column()`/`periods()`. Callers pass
ONLY those holes as `skipped=[{"date", "reason"}, ...]` (runner.report_holes) --
a strategy's own no-trade day (a trend gate) is a real flat 0.0 weekday, never a
hole (review C1) -- and `build` surfaces them loudly rather than let a broken
strategy look like a quiet zero:
`skipped_by_error` counts reasons starting with "strategy error", the rest
(coverage gaps, etc.) are `skipped_by_data`.
"""
from __future__ import annotations

import math

from .propsim import weekday_grid as _propsim_weekday_grid
from .stats.ledger import Trade as LedgerTrade
from .stats.stats import _sharpe, pack

CAP = 999.0


def to_ledger(trades: list[dict]) -> list[LedgerTrade]:
    return [LedgerTrade(entry_ts=t["entry_ns"] // 1_000_000_000, exit_ts=t["exit_ns"] // 1_000_000_000,
                        side=t["side"], qty=t["qty"], pnl=t["net"], runup=t["mfe_usd"],
                        drawdown=t["mae_usd"], cost=t["commission"]) for t in trades]


def rr_label(rr: float | None) -> str:
    if rr is None:
        return "—"
    return "1:∞" if rr >= CAP else f"1:{rr:.2f}"


def daily_pnl(trades: list[dict]) -> list[float]:
    by: dict[str, float] = {}
    for t in trades:
        by[t["date"]] = by.get(t["date"], 0.0) + t["net"]
    return [by[d] for d in sorted(by)]


def weekday_daily_pnl(trades: list[dict], skipped: list[dict] | None = None) -> list[float]:
    """The Sharpe/Sortino day grid (Item 1): the same weekday grid
    `homebase.backtest.propsim.weekday_grid` builds for the prop-eval Monte Carlo —
    every Mon-Fri from these trades' first to last session date, 0.0 net on a
    weekday nothing traded — with every SKIPPED date (a strategy error or a
    coverage/data hole, `skipped=[{"date", "reason"}, ...]`) dropped from the grid
    entirely: a hole in the record is not a real flat trading day."""
    pnls, _flags, dates = _propsim_weekday_grid(trades)
    if not skipped:
        return pnls
    holes = {s["date"] for s in skipped}
    return [p for p, d in zip(pnls, dates) if d not in holes]


def sortino(daily: list[float]) -> float | None:
    if len(daily) < 2:
        return None
    dd = math.sqrt(sum(min(d, 0.0) ** 2 for d in daily) / len(daily))
    if not dd:
        return None
    return sum(daily) / len(daily) / dd * math.sqrt(252.0)


def t_stat(pnls: list[float]) -> float | None:
    n = len(pnls)
    if n < 2:
        return None
    m = sum(pnls) / n
    sd = math.sqrt(sum((p - m) ** 2 for p in pnls) / (n - 1))
    return m / (sd / math.sqrt(n)) if sd else None


def drawdown_pct(trades: list[dict], capital: float) -> float:
    eq = peak = capital
    worst = 0.0
    for t in trades:
        eq += t["net"]
        peak = max(peak, eq)
        worst = min(worst, (eq - peak) / peak * 100.0 if peak > 0 else 0.0)
    return worst


def column(trades: list[dict], capital: float, skipped: list[dict] | None = None) -> dict:
    p = pack(to_ledger(trades))
    n = p["n_trades"]
    daily = daily_pnl(trades)
    grid = weekday_daily_pnl(trades, skipped)
    return {
        "net_profit": p["net"], "net_profit_pct": p["net"] / capital * 100.0,
        "gross_profit": p["gross_profit"], "gross_loss": p["gross_loss"],
        "commission_paid": sum(t["commission"] for t in trades),
        "max_drawdown": p["max_drawdown"], "max_drawdown_pct": drawdown_pct(trades, capital),
        "max_runup": p["max_runup"],
        "profit_factor": p["profit_factor"] if n else None,
        "trades": n, "wins": p["n_wins"], "losses": p["n_losses"],
        "win_rate": p["win_rate"] * 100.0 if n else None,
        "avg_trade": p["expectancy"] if n else None,
        "avg_win": p["avg_win"], "avg_loss": p["avg_loss"],
        "rr": p["payoff_ratio"], "rr_label": rr_label(p["payoff_ratio"]),
        "largest_win": p["largest_win"], "largest_loss": p["largest_loss"],
        "avg_seconds_in_trade": sum(t["seconds"] for t in trades) / n if n else None,
        "avg_bars_in_trade": sum(t["bars"] for t in trades) / n if n else None,
        "max_consec_losses": p["loss_streak_max"] or 0,
        "sharpe": _sharpe(grid), "sortino": sortino(grid),
        "sharpe_traded_days": _sharpe(daily),
        "t_stat": t_stat([t["net"] for t in trades]),
        "expectancy": p["expectancy"] if n else None,
        "days": len(daily),
    }


def summary(trades: list[dict], capital: float, skipped: list[dict] | None = None) -> dict:
    return {"all": column(trades, capital, skipped),
            "long": column([t for t in trades if t["side"] == "long"], capital, skipped),
            "short": column([t for t in trades if t["side"] == "short"], capital, skipped)}


def periods(trades: list[dict], width: int, skipped: list[dict] | None = None) -> list[dict]:
    """width 4 = years, 7 = months (prefixes of the session date)."""
    groups: dict[str, list[dict]] = {}
    for t in trades:
        groups.setdefault(t["date"][:width], []).append(t)
    skipped = skipped or []
    out = []
    for k in sorted(groups):
        g = groups[k]
        p = pack(to_ledger(g))
        g_skipped = [s for s in skipped if s["date"][:width] == k]
        out.append({"period": k, "trades": p["n_trades"], "net": p["net"],
                    "win_rate": p["win_rate"] * 100.0, "profit_factor": p["profit_factor"],
                    "max_drawdown": p["max_drawdown"],
                    "sharpe": _sharpe(weekday_daily_pnl(g, g_skipped)),
                    "avg_trade": p["expectancy"]})
    return out


def to_ms(trades: list[dict]) -> list[dict]:
    """Item 6: trades.json is JS-facing -- `entry_ns`/`exit_ns` (int64 epoch
    nanoseconds, e.g. ~1.7e18 for a 2024 date) blow past Number.MAX_SAFE_INTEGER
    (2**53 ~= 9e15) and are not safe to round-trip through JSON in a browser.
    Replaces them with `entry_ms`/`exit_ms`; `ts_ns` stays internal to the
    engine/report and is never written to the bundle."""
    out = []
    for t in trades:
        d = dict(t)
        d["entry_ms"] = d.pop("entry_ns") // 1_000_000
        d["exit_ms"] = d.pop("exit_ns") // 1_000_000
        out.append(d)
    return out


def equity(trades: list[dict]) -> dict:
    t_ms, eq, dd = [], [], []
    run = peak = 0.0
    for t in trades:
        run += t["net"]
        peak = max(peak, run)
        t_ms.append(t["exit_ns"] // 1_000_000)
        eq.append(round(run, 2))
        dd.append(round(run - peak, 2))
    return {"t_ms": t_ms, "equity": eq, "drawdown": dd}


def build(trades: list[dict], capital: float = 50_000.0, skipped: list[dict] | None = None) -> dict:
    trades = sorted(trades, key=lambda t: (t["exit_ns"], t["entry_ns"]))
    skipped = skipped or []
    by_error = sum(1 for s in skipped if s["reason"].startswith("strategy error"))
    return {"capital": capital, "summary": summary(trades, capital, skipped),
            "by_year": periods(trades, 4, skipped), "by_month": periods(trades, 7, skipped),
            "skipped": skipped, "skipped_by_error": by_error,
            "skipped_by_data": len(skipped) - by_error,
            "sharpe_basis": "weekday grid (daily net incl. 0-trade weekdays, ×√252)"}
