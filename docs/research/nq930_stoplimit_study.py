"""NQ 9:30 straddle -- Stop-Limit entry study (prereg: 2026-09-27-nq930-stoplimit-entry-study.md).

Replays the desk's live nq930 config through the tester's tick engine on the research
window (2021-2024 only) for the 7 preregistered cells + 2 baseline slippage lines, and
prints / writes the results table. Mirrors homebase.backtest.runner.execute session by
session (half-day clamp, coverage-hole skips, the no-trade reasons fed to the Sharpe
grid). Reads ~/futures_ticks through TapeStore (read-only); writes only --out.

    .venv/bin/python docs/research/nq930_stoplimit_study.py --out docs/research/<name>.json
    PYTHONPATH=<main tree> python ... --baseline-only --dump <file>   # parity vs main's engine
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path

import homebase.config as desk_config
from homebase.backtest import discipline, report
from homebase.backtest.engine import Costs, run_session
from homebase.backtest.tape import TapeStore, coverage_reason, effective_session_window, missing_hours
from homebase.strategies.nq930 import NQ930
from homebase.strategies.straddle import desk_cfg

LIVE_CFG = Path("/Users/ramoscapital/ramos-quant-homebase/homebase/config.json")
EXPECT = {"offset_pts": 5.0, "sl_pts": 5.0, "tp_pts": 15.0, "gated": False,
          "cancel_et": "12:55", "flat_et": "15:55"}
CELLS = [("baseline", 0, 1.0)] + [(f"SL+{n}", n, 1.0) for n in (1, 2, 3, 4, 6, 8)]
SLIP_LINES = [("baseline slip 0", 0, 0.0), ("baseline slip 2", 0, 2.0)]
YEARS = ("2021", "2022", "2023", "2024")
TICK_USD = 5.0                  # NQ 0.25 pt x $20


def sha(trades: list[dict]) -> str:
    return hashlib.sha256(json.dumps(trades, sort_keys=True).encode()).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    ap.add_argument("--baseline-only", action="store_true", help="parity mode: default inputs, slip 1")
    ap.add_argument("--dump", type=Path, help="parity mode: write the baseline trades here")
    a = ap.parse_args(argv)

    desk_config.config_path = lambda: LIVE_CFG          # desk_cfg() reads the LIVE desk file
    cfg = desk_cfg("nq930")
    got = {k: getattr(cfg, k) for k in EXPECT}
    assert got == EXPECT, f"live desk nq930 config moved: {got}"

    rng = discipline.parse_range({"kind": "research"})
    assert rng.end <= dt.date(2024, 12, 31)
    store = TapeStore()
    days = [d for d in store.sessions("NQ", rng.start, rng.end) if rng.includes(d)]
    assert days and max(days) <= dt.date(2024, 12, 31), "2025+ must never load here"

    cells = [("baseline", None, 1.0)] if a.baseline_only else CELLS + SLIP_LINES
    strats = {}
    for name, n, _ in cells:
        s = NQ930({} if n is None else {"entry_limit_ticks": n})
        assert (s.p["offset_pts"], s.p["sl_pts"], s.p["tp_pts"], s.p["adx_gate"]) == (5.0, 5.0, 15.0, False)
        strats[name] = s
    trades = {c[0]: [] for c in cells}
    no_trade = {c[0]: [] for c in cells}
    missed = {c[0]: [] for c in cells}
    skipped: list[dict] = []
    t0 = time.monotonic()
    for i, d in enumerate(days):
        tape = store.load("NQ", d)
        if tape is None:
            skipped.append({"date": d.isoformat(), "reason": "no tape"})
            continue
        window = effective_session_window("NQ", d, NQ930.session_window)
        gaps = missing_hours(tape.ts, d, window)
        if gaps:
            skipped.append({"date": d.isoformat(), "reason": coverage_reason(gaps)})
            continue
        for name, _, slip in cells:
            s = strats[name]
            s.session_window = window
            res = run_session(s, tape, Costs(4.0, slip), qty=1)
            trades[name] += [t.to_dict() for t in res.trades]
            if res.skip:
                no_trade[name].append({"date": d.isoformat(), "reason": res.skip})
            touched = any(getattr(o, "triggered", False) for o in s.entries)   # main has no flag
            if touched and not any(o.status == "filled" for o in s.entries):
                missed[name].append(d.isoformat())
        if i % 100 == 0:
            print(f"  {i}/{len(days)} {d} {time.monotonic() - t0:.0f}s", file=sys.stderr)

    if a.baseline_only:
        a.dump.write_text(json.dumps(trades["baseline"], sort_keys=True))
        print(f"baseline {len(trades['baseline'])} trades sha256 {sha(trades['baseline'])}")
        return 0

    base = {t["date"]: t for t in trades["baseline"]}
    rows = {}
    for name, n, slip in cells:
        tr = trades[name]
        rep = report.build(tr, 50_000.0, skipped=skipped + no_trade[name])
        al = rep["summary"]["all"]
        by_year = {p["period"]: round(p["net"], 2) for p in rep["by_year"]}
        switched = capped = 0
        capped_usd = 0.0
        for t in (tr if slip == 1.0 else []):          # vs the baseline at the same slip only
            b = base.get(t["date"])
            if b is None or (b["side"], b["entry_ns"]) != (t["side"], t["entry_ns"]):
                switched += 1
            elif t["entry_price"] != b["entry_price"]:
                capped += 1
                capped_usd += abs(t["entry_price"] - b["entry_price"]) / 0.25 * TICK_USD
        rows[name] = {
            "entry_limit_ticks": n, "slip_ticks": slip,
            "filled": al["trades"], "missed": len(missed[name]),
            "switched": switched if slip == 1.0 else None,
            "capped_fills": capped if slip == 1.0 else None,
            "capped_entry_usd": round(capped_usd, 2) if slip == 1.0 else None,
            "win_rate": al["win_rate"], "net": round(al["net_profit"], 2),
            "avg_trade": al["avg_trade"], "profit_factor": al["profit_factor"],
            "sharpe": al["sharpe"], "t_stat": al["t_stat"], "max_drawdown": al["max_drawdown"],
            "by_year": by_year, "green_years": sum(1 for y in YEARS if by_year.get(y, 0) > 0),
            "rr_label": al["rr_label"], "trades_sha256": sha(tr),
        }

    b = rows["baseline"]
    for name, n, _ in CELLS[1:]:
        r = rows[name]
        yrs = sum(1 for y in YEARS if r["by_year"].get(y, 0.0) >= b["by_year"].get(y, 0.0))
        r["years_ge_baseline"] = yrs
        r["helps"] = (r["net"] >= b["net"] and r["missed"] <= 0.15 * b["filled"] and yrs >= 3)

    gaps: dict[int, int] = {}               # descriptive: ticks the trigger print sat past the trigger
    for t in trades["baseline"]:
        g = round((t["entry_price"] - t["order_price"]) * (1 if t["side"] == "long" else -1) / 0.25) - 1
        gaps[g] = gaps.get(g, 0) + 1
    out = {"study": "nq930 stop-limit entry", "trigger_gap_ticks": dict(sorted(gaps.items())), "run": dt.datetime.now().isoformat(timespec="seconds"),
           "desk_cfg": got, "window": [str(min(days)), str(max(days))], "sessions": len(days),
           "skipped": len(skipped), "skipped_dates": skipped, "cells": rows}
    if a.out:
        a.out.write_text(json.dumps(out, indent=1, default=str) + "\n")

    print(f"sessions {len(days)} ({min(days)} -> {max(days)}), skipped {len(skipped)}, "
          f"{time.monotonic() - t0:.0f}s")
    print("| cell | filled | missed | switched | capped | WR | net $ | avg $/trade | PF | Sharpe | t | "
          "maxDD $ | green yrs | yrs >= base | helps |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name, _, _ in cells:
        r = rows[name]
        print(f"| {name} | {r['filled']} | {r['missed']} | {r['switched'] if r['switched'] is not None else '-'} | "
              f"{r['capped_fills'] if r['capped_fills'] is not None else '-'} | "
              f"{r['win_rate']:.1f}% | {r['net']:,.0f} | {r['avg_trade']:.2f} | {r['profit_factor']:.2f} | "
              f"{r['sharpe']:.2f} | {r['t_stat']:.2f} | {r['max_drawdown']:,.0f} | {r['green_years']}/4 | "
              f"{r.get('years_ge_baseline', '-')} | {r.get('helps', '-')} |")
    print("trigger-print gap (ticks past the trigger):", out["trigger_gap_ticks"])
    print("by year:")
    for name, _, _ in cells:
        print(f"  {name:16s} " + "  ".join(f"{y} {rows[name]['by_year'].get(y, 0):>9,.0f}" for y in YEARS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
