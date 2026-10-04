#!/usr/bin/env python3
"""RUN AGENT sanity for the round1 (stage 2b) BUILD stores. Counts and coverage only; NO P&L column is read or written.
Reuses sanity.rows() (same checks as the stage-1 table) and keeps the round1 families only -> out/run_agent/run_table_round1.csv."""
import csv, sys
from collections import Counter, defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sanity  # noqa: E402
import library  # noqa: E402

FAMS = ("vwap_trend_pull", "va_reclaim", "orb_confirm", "late_mom", "open_fade", "vol_spike_break", "straddle_tight")
rs = [r for r in sanity.rows() if r["family"].startswith(FAMS)]
cols = []
for r in rs:
    for k in r:
        if k not in cols:
            cols.append(k)
with (HERE / "run_table_round1.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, cols); w.writeheader(); w.writerows(rs)
agg = defaultdict(lambda: [0, 0, 0, 0])
for r in rs:
    a = agg[(r["family"], r["root"], r["stage"])]
    a[0] += 1; a[1] += r["cells"]; a[2] += r["null_cells"]; a[3] += r["trades"]
print("stores", len(rs), "build", sum(r["stage"] == "build" for r in rs), "null", sum(r["stage"] == "null" for r in rs))
print("cells", sum(r["cells"] for r in rs), "null_cells", sum(r["null_cells"] for r in rs), "trades", sum(r["trades"] for r in rs))
print("no store on disk:", [r["key"] for r in rs if not r.get("store")])
print("period != build:", [r["key"] for r in rs if r.get("period") != "build"])
print("range set:", Counter(r.get("range") for r in rs))
print("skipped_by_error total:", sum(r.get("skipped_by_error") or 0 for r in rs))
print("trades_no_session total:", sum(r.get("trades_no_session") or 0 for r in rs), [r["key"] for r in rs if r.get("trades_no_session")])
print("unrealistic_winners total:", sum(r.get("unrealistic_winners") or 0 for r in rs))
print("both_sides_ok False:", [r["key"] for r in rs if r.get("both_sides_ok") is False])
by = defaultdict(set)
for r in rs:
    by[r["root"]].add((r["sessions"], r["used"], r["skipped"], r["eve_skipped"]))
for k, v in sorted(by.items()):
    print("sessions (calendar, used, skipped, eve_skipped)", k, sorted(v))
cw = [(r["key"], r["cells_without_trades"]) for r in rs if r.get("cells_without_trades")]
print("cells without a trade:", sum(c for _, c in cw), "in", len(cw), "stores")
for k, c in cw:
    print("  ", k, c)
print("exec_guard set:", [r["key"] for r in rs if r.get("exec_guard")][:5])
print("ledger", library.ledger_used(), "caps", library.CAPS)
