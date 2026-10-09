"""execrun: a research-engine trade list that has times, sides and nets but NO PRICES, written as a finished tester run.

The research engine's store keeps a trade's entry time, how long it lasted, its side and its net -- not its prices. A chart needs
prices, so this prices each trade from the tape's 1-minute bars (the chart service's own cache, read only) and hands the rows to
importrun, which writes the run:

    entry_price   the OPEN of the minute the engine filled in: its market entries go at the next bar's open
    exit_price    the entry price plus the trade's own net in points (side x (net + the round-turn cost) / point value)
                  -- so the run's net, which is the engine's, is never touched, and a stop or a target sits where it did

A trade whose minute has no bar is left out and counted (`of` - `priced`). Nothing is replayed and no tick is read.

    python -m homebase.backtest.execrun TRADES.json --strategy pipe_<name> --root NQ [--name ...] [--start D --end D]
        [--sessions N] [--note ...] [--base DIR]        -> the last line is {"run_id", "priced", "of"}
TRADES.json = {"trades": [{date: YYYY-MM-DD, entry_ms, dur_s, side: 1 | -1 | "long" | "short", net, reason}]}
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from . import importrun
from ..contracts import point_value

COMMISSION = 4.00                  # $ a round turn: importrun's own default
MINUTE_MS = 60_000


def priced(trades: list, opens: dict, pv: float, commission: float = COMMISSION) -> list:
    """importrun rows from `trades` and `opens` = {session date: {minute epoch ms: open}}; trades without a bar are left out."""
    rows = []
    for t in trades:
        ent = int(t["entry_ms"])
        px = (opens.get(t["date"]) or {}).get(ent - ent % MINUTE_MS)
        if px is None:
            continue
        side = 1 if t["side"] in (1, "long") else -1
        net = float(t["net"])
        rows.append({"date": t["date"], "side": "long" if side > 0 else "short", "qty": 1, "entry_ms": ent,
                     "exit_ms": ent + int(t["dur_s"]) * 1000, "entry_price": float(px),
                     "exit_price": round(float(px) + side * (net + commission) / pv, 4), "net": net, "commission": commission,
                     "exit_reason": str(t.get("reason") or "")})
    return rows


def minute_opens(root: str, dates, base=None) -> dict:
    """{date: {minute epoch ms: open}} from the 1-minute bar cache (History.minutes; read only)."""
    from ..charts.history import History
    from ..charts.store import TickStore
    h = History(TickStore(base)) if base else History(TickStore())
    out = {}
    for d in sorted(set(dates)):
        try:
            out[d] = {int(b.t): float(b.o) for b in h.minutes(root, dt.date.fromisoformat(d))}
        except (OSError, ValueError, KeyError):
            out[d] = {}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m homebase.backtest.execrun")
    ap.add_argument("trades")
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--name")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--sessions", type=int)
    ap.add_argument("--note", default="")
    ap.add_argument("--base")
    a = ap.parse_args(argv)
    raw = json.loads(Path(a.trades).read_text(encoding="utf-8"))
    trades = raw["trades"] if isinstance(raw, dict) else raw
    rows = priced(trades, minute_opens(a.root, [t["date"] for t in trades]), float(point_value(a.root)))
    if not rows:
        print(f"none of the {len(trades)} trades could be priced from the 1-minute bars (is the tick archive there?)", file=sys.stderr)
        return 2
    rid = importrun.write_run(rows, strategy=a.strategy, root=a.root, name=a.name, start=a.start, end=a.end, sessions=a.sessions,
                              note=a.note, base=Path(a.base) if a.base else None)
    print(json.dumps({"run_id": rid, "priced": len(rows), "of": len(trades)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
