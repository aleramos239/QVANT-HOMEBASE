"""Live metrics per strategy, aggregated straight from the journal.

Only REAL events count: entry_fill (slippage vs anchor) and exit_fill
(gross P&L the engine computed at exit). Dry runs never appear here —
the live strip earns itself trade by trade.
"""
from __future__ import annotations

import json
from pathlib import Path


def live_metrics(journal_path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not journal_path.exists():
        return out
    for line in journal_path.read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        name = r.get("strategy")
        if not name:
            continue
        m = out.setdefault(name, {"trades": 0, "wins": 0, "net": 0.0,
                                  "slips": [], "days": set()})
        if r.get("event") == "entry_fill" and r.get("fill_vs_anchor") is not None:
            m["slips"].append(abs(float(r["fill_vs_anchor"])))
        if r.get("event") == "exit_fill" and r.get("pnl") is not None:
            pnl = float(r["pnl"])
            m["trades"] += 1
            m["wins"] += 1 if pnl > 0 else 0
            m["net"] += pnl
            m["days"].add(str(r.get("et", ""))[:10])
    for name, m in out.items():
        n = m.pop("trades")
        slips = m.pop("slips")
        wins = m.pop("wins")
        days = m.pop("days")
        out[name] = {
            "trades": n,
            "win_rate": (round(100.0 * wins / n, 1) if n else None),
            "net": round(m["net"], 2),
            "avg_trade": (round(m["net"] / n, 2) if n else None),
            "avg_slip_pts": (round(sum(slips) / len(slips), 3) if slips else None),
            "days": len(days),
        }
    return out
