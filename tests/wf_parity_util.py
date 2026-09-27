"""A deterministic walk-forward input for the 1:3 parity pin (tests/test_walkforward_parity.py).

Three cells, 14 months (2022-01 .. 2023-02), each month's trades a fixed function of (cell, month),
so every selection month has a real winner, some months have no eligible cell, and a strategy-error
session sits inside a test leg. Kept free of anything the rework added, so the SAME code runs under
the pre-change commit bb7e6a5 to capture the fixture."""
from __future__ import annotations

import datetime as dt

MONTHS = [f"{y}-{m:02d}" for y, m in [(2022, m) for m in range(1, 13)] + [(2023, 1), (2023, 2)]]
CAPITAL = 50_000.0


def _weekdays(month: str, n: int) -> list[str]:
    d = dt.date.fromisoformat(month + "-01")
    out = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def _trade(date: str, net: float) -> dict:
    d = dt.date.fromisoformat(date)
    ms = int(dt.datetime(d.year, d.month, d.day, 14, 30, tzinfo=dt.timezone.utc).timestamp() * 1000)
    return {"date": date, "side": "long", "qty": 1, "entry_ms": ms, "entry_price": 100.0, "exit_ms": ms + 60_000,
            "exit_price": 101.0, "exit_reason": "tp", "order_price": 100.0, "sl": 95.0, "tp": 110.0,
            "gross": net + 4.0, "commission": 4.0, "net": net, "mae_pts": -1.0, "mfe_pts": 2.0,
            "mae_usd": -20.0, "mfe_usd": 40.0, "bars": 1, "seconds": 60.0}


def cell_trades(i: int) -> list[dict]:
    out = []
    for k, m in enumerate(MONTHS):
        n = 3 + (i + k) % 5                      # 3..7 trades: some months fall under min_trades 5
        nets = [((i * 37 + k * 53 + j * 71) % 400) - 180.0 for j in range(n)]
        out += [_trade(d, v) for d, v in zip(_weekdays(m, n), nets)]
    return out


SKIPPED = {1: [{"date": "2022-05-10", "reason": "strategy error: boom"}], 0: [], 2: []}


def compute_input(wf):
    """(cells, trades_of) for wf.compute, built with the module under test's own month_stats."""
    tr = {i: cell_trades(i) for i in range(3)}
    cells = [{"i": i, "params": {"offset_pts": 10.0 + i}, "months": wf.month_stats(tr[i], SKIPPED[i], CAPITAL, MONTHS)}
             for i in range(3)]
    return cells, (lambda i: (tr[i], SKIPPED[i]))
