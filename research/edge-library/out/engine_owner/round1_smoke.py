#!/usr/bin/env python3
"""STAGE 2b smoke of the round1 families: 10 fixed BUILD days per family x tf on one root. COUNTS ONLY (run_menus.smoke):
trades, cells without a trade, exits after the day's flatten, entries outside every session / outside the family's own
window, overlaps, strategy errors, 1- vs 2-worker parity, the nulls' trade counts. Never a net, win rate or profit factor.
    python out/engine_owner/round1_smoke.py [ROOT]      -> out/engine_owner/round1_smoke_<ROOT>.json + one line per unit"""
import json
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(W))
import run_menus as RM  # noqa: E402


def main(root="NQ"):
    fam = RM.registry()
    rows = []
    for name in RM.group_families("round1"):
        for tf in fam.REGISTRY[name][0].SCREEN_TFS:
            o = RM.smoke(name, root, tf, 10, 2)
            rows.append(o)
            print(f"{name:20s} {root} tf{tf:3s} days {o['days']:2d} cells {o['cells']:4d} trades {o['trades_total']:6d} "
                  f"(per cell {o['trades_per_cell']['min']}-{o['trades_per_cell']['max']}, empty cells {o['cells_without_trades']}) "
                  f"long {o['long']} short {o['short']} sessions {o['by_session']} | exit_after_flat {o['exit_after_day_flat']} "
                  f"outside_window {o['entry_outside_hours']} no_session {o['entry_in_no_session']} overlap {o['overlap_in_session']} "
                  f"errors {o['skipped_by_error']} parity {o['worker_parity']} nulls {o['nulls']} ok {o['ok']}", flush=True)
    (Path(__file__).parent / f"round1_smoke_{root}.json").write_text(json.dumps(rows, indent=1, default=str))
    print("ALL OK" if all(r["ok"] for r in rows) else "FAILED: " + ", ".join(f"{r['family']}-tf{r['tf']}" for r in rows if not r["ok"]))
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:2] or ["NQ"])))
