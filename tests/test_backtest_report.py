"""The report on a hand-computed four-trade ledger."""
from __future__ import annotations

import datetime as dt
import math

import pytest

from homebase.backtest.report import build, equity, rr_label, sortino, t_stat


def _weekday_grid(by_date: dict[str, float]) -> list[float]:
    """An independent re-implementation of the weekday grid (not the code under
    test) used to hand-check `report.build`'s Sharpe/Sortino basis."""
    d0, d1 = dt.date.fromisoformat(min(by_date)), dt.date.fromisoformat(max(by_date))
    days = {(d0 + dt.timedelta(i)).isoformat() for i in range((d1 - d0).days + 1)
            if (d0 + dt.timedelta(i)).weekday() < 5} | set(by_date)
    return [by_date.get(d, 0.0) for d in sorted(days)]


def tr(date, side, net, hms_ns, seconds=60.0, bars=2, comm=4.0):
    day = {"2024-01-02": 1704205800, "2024-01-03": 1704292200, "2024-02-05": 1707143400}[date]
    t0 = (day + hms_ns) * 1_000_000_000
    return {"date": date, "side": side, "qty": 1, "entry_ns": t0, "exit_ns": t0 + int(seconds * 1e9),
            "net": net, "gross": net + comm, "commission": comm, "mfe_usd": 100.0, "mae_usd": 50.0,
            "seconds": seconds, "bars": bars}


LEDGER = [tr("2024-01-02", "long", 296.0, 60), tr("2024-01-02", "short", -104.0, 600, seconds=120, bars=3),
          tr("2024-01-03", "long", -204.0, 60), tr("2024-02-05", "short", 196.0, 60)]


def test_all_column_hand_computed():
    a = build(LEDGER, capital=50_000.0)["summary"]["all"]
    assert a["net_profit"] == 184.0 and a["net_profit_pct"] == pytest.approx(0.368)
    assert (a["gross_profit"], a["gross_loss"], a["commission_paid"]) == (492.0, -308.0, 16.0)
    assert a["profit_factor"] == pytest.approx(492 / 308)
    assert (a["trades"], a["wins"], a["losses"], a["win_rate"]) == (4, 2, 2, 50.0)
    assert (a["avg_trade"], a["avg_win"], a["avg_loss"]) == (46.0, 246.0, -154.0)
    assert a["rr"] == pytest.approx(246 / 154) and a["rr_label"] == "1:1.60"
    assert (a["largest_win"], a["largest_loss"]) == (296.0, -204.0)
    assert a["max_drawdown"] == -308.0 and a["max_runup"] == 296.0
    assert a["max_drawdown_pct"] == pytest.approx(-308 / 50_296 * 100)
    assert a["max_consec_losses"] == 2
    assert a["avg_seconds_in_trade"] == 75.0 and a["avg_bars_in_trade"] == 2.25
    daily = [192.0, -204.0, 196.0]                       # by session date (traded days only)
    m = sum(daily) / 3
    sd = math.sqrt(sum((d - m) ** 2 for d in daily) / 2)
    assert a["sharpe_traded_days"] == pytest.approx(m / sd * math.sqrt(252)) and a["days"] == 3
    # Item 1: the report's headline sharpe/sortino run on the weekday grid (every
    # Mon-Fri between the first and last trade date, 0.0 on a day nothing traded),
    # not the traded-days-only sample -- the traded-days figure is inflated because
    # it excludes every weekday the "account" sat flat.
    grid = _weekday_grid({"2024-01-02": 192.0, "2024-01-03": -204.0, "2024-02-05": 196.0})
    gm = sum(grid) / len(grid)
    gsd = math.sqrt(sum((d - gm) ** 2 for d in grid) / (len(grid) - 1))
    gdd = math.sqrt(sum(min(d, 0.0) ** 2 for d in grid) / len(grid))
    assert a["sharpe"] == pytest.approx(gm / gsd * math.sqrt(252))
    assert a["sortino"] == pytest.approx(gm / gdd * math.sqrt(252))
    assert a["t_stat"] == pytest.approx(46.0 / (math.sqrt(170000 / 3) / 2))


def test_long_and_short_columns_split_the_ledger():
    s = build(LEDGER)["summary"]
    assert (s["long"]["trades"], s["long"]["net_profit"]) == (2, 92.0)
    assert (s["short"]["trades"], s["short"]["net_profit"]) == (2, 92.0)
    assert s["long"]["largest_loss"] == -204.0 and s["short"]["largest_win"] == 196.0


def test_year_and_month_tables():
    r = build(LEDGER)
    assert [(y["period"], y["trades"], y["net"]) for y in r["by_year"]] == [("2024", 4, 184.0)]
    assert [(m["period"], m["trades"], m["net"]) for m in r["by_month"]] == [("2024-01", 3, -12.0),
                                                                             ("2024-02", 1, 196.0)]


def test_equity_and_drawdown_series():
    e = equity(LEDGER)
    assert e["equity"] == [296.0, 192.0, -12.0, 184.0]
    assert e["drawdown"] == [0.0, -104.0, -308.0, -112.0]
    assert e["t_ms"][0] == LEDGER[0]["exit_ns"] // 1_000_000


def test_empty_and_degenerate_ledgers():
    a = build([])["summary"]["all"]
    assert a["trades"] == 0 and a["win_rate"] is None and a["profit_factor"] is None
    assert a["rr_label"] == "—" and a["sharpe"] == 0.0 and a["t_stat"] is None
    assert a["sharpe_traded_days"] == 0.0
    assert rr_label(999.0) == "1:∞" and rr_label(0.75) == "1:0.75"
    assert sortino([10.0, 20.0]) is None and t_stat([5.0]) is None and t_stat([3.0, 3.0]) is None


def test_sharpe_basis_is_the_weekday_grid():
    assert build(LEDGER)["sharpe_basis"] == "weekday grid (daily net incl. 0-trade weekdays, ×√252)"


def _trade(date: str, net: float) -> dict:
    d = dt.date.fromisoformat(date)
    t0 = int(dt.datetime.combine(d, dt.time(9, 30)).timestamp()) * 1_000_000_000
    return {"date": date, "side": "long", "qty": 1, "entry_ns": t0, "exit_ns": t0 + 60_000_000_000,
            "net": net, "gross": net + 4.0, "commission": 4.0, "mfe_usd": 0.0, "mae_usd": 0.0,
            "seconds": 60.0, "bars": 1}


def test_sharpe_weekday_grid_vs_traded_days_ratio_on_a_sparse_ledger():
    """Item 1: a sparse book (one trade a week, like an event straddle) reads an
    inflated Sharpe on traded days alone -- the expected ratio between the two
    bases, hand-verified independently of report.py's own weekday-grid helper."""
    ledger = [_trade("2022-01-03", 300.0), _trade("2022-01-10", -100.0),
              _trade("2022-01-17", 300.0), _trade("2022-01-24", -100.0)]
    a = build(ledger)["summary"]["all"]
    grid = _weekday_grid({"2022-01-03": 300.0, "2022-01-10": -100.0,
                          "2022-01-17": 300.0, "2022-01-24": -100.0})
    assert len(grid) == 16 and a["days"] == 4
    traded = [300.0, -100.0, 300.0, -100.0]
    tm = sum(traded) / 4
    tsd = math.sqrt(sum((d - tm) ** 2 for d in traded) / 3)
    gm = sum(grid) / len(grid)
    gsd = math.sqrt(sum((d - gm) ** 2 for d in grid) / (len(grid) - 1))
    assert a["sharpe_traded_days"] == pytest.approx(tm / tsd * math.sqrt(252))
    assert a["sharpe"] == pytest.approx(gm / gsd * math.sqrt(252))
    assert a["sharpe_traded_days"] > a["sharpe"] > 0             # traded-days-only is inflated
    assert a["sharpe_traded_days"] / a["sharpe"] == pytest.approx(1.9494, rel=1e-3)


def test_skipped_sessions_are_reported_loudly():
    """Amendment: the engine turns any strategy exception into a session skip
    (reason "strategy error: ..."). The report must surface skips loudly and
    split the count between strategy errors and everything else (coverage, etc)."""
    skipped = [
        {"date": "2024-01-04", "reason": "strategy error: division by zero"},
        {"date": "2024-01-05", "reason": "strategy error: KeyError('x')"},
        {"date": "2024-01-08", "reason": "missing 13:00-15:00 ET"},
    ]
    r = build(LEDGER, capital=50_000.0, skipped=skipped)
    assert r["skipped"] == skipped
    assert r["skipped_by_error"] == 2
    assert r["skipped_by_data"] == 1


def test_skipped_defaults_to_empty():
    r = build(LEDGER)
    assert r["skipped"] == [] and r["skipped_by_error"] == 0 and r["skipped_by_data"] == 0
