#!/usr/bin/env python3
"""STAGE 4 smoke of the round2 families (W straddle_wide, D event_dir at 08:30 / 10:00): the 10 fixed BUILD days per
family on one root. COUNTS ONLY (run_menus.smoke): trades, cells without a trade, exits after the day's flatten, entries
outside every session / outside the family's own window, overlaps, strategy errors, 1- vs 2-worker parity, the nulls' trade
counts; plus the days with a trade per variant (first exit cell). Never a net, win rate or profit factor.
    python out/engine_owner/round2_smoke.py [ROOT]      -> out/engine_owner/round2_smoke_<ROOT>.json + one line per unit"""
import json
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(W))
import run_menus as RM  # noqa: E402


def main(root="NQ"):
    fam = RM.registry()
    rows = []
    days = [d for d in RM.SMOKE_DAYS]
    for name in RM.group_families("round2"):
        o = RM.smoke(name, root, "30", 10, 2)
        grid = fam.unit_grid(name, root, "30")
        nx = len(grid) // o["variants"]
        firsts = grid[::nx]                           # the first exit cell of every variant
        res = RM.run_grid(firsts, root, features=None, workers=2, days=days)
        o["days_with_a_trade_per_variant"] = {RM.l2sim.cell_id(c["variant"]): len({t["date"] for t in r["trades"]})
                                              for c, r in zip(firsts, res)}
        o["max_trades_per_day"] = max([sum(1 for t in r["trades"] if t["date"] == d) for r in res for d in days] or [0])
        o["ok"] = bool(o["ok"] and o["max_trades_per_day"] <= 1)
        rows.append(o)
        print(f"{name:20s} {root} days {o['days']:2d} cells {o['cells']:4d} trades {o['trades_total']:6d} "
              f"(per cell {o['trades_per_cell']['min']}-{o['trades_per_cell']['max']}, empty cells {o['cells_without_trades']}) "
              f"long {o['long']} short {o['short']} sessions {o['by_session']} entry {o['entry_kind']} "
              f"both_sides declared {o['both_sides_declared']} seen {o['both_sides_sessions']} | exit_after_flat "
              f"{o['exit_after_day_flat']} outside_window {o['entry_outside_hours']} no_session {o['entry_in_no_session']} overlap "
              f"{o['overlap_in_session']} errors {o['skipped_by_error']} parity {o['worker_parity']} max/day "
              f"{o['max_trades_per_day']} nulls {o['nulls']} | days with a trade per variant "
              f"{o['days_with_a_trade_per_variant']} ok {o['ok']}", flush=True)
    (Path(__file__).parent / f"round2_smoke_{root}.json").write_text(json.dumps(rows, indent=1, default=str))
    print("ALL OK" if all(r["ok"] for r in rows) else "FAILED: " + ", ".join(r["family"] for r in rows if not r["ok"]))
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:2] or ["NQ"])))
