#!/usr/bin/env python3
"""RUN AGENT sanity table of the BUILD stores (counts and coverage only; NO P&L column is read or written).

    python sanity.py            -> out/run_agent/run_table.csv + a printed summary (per root / stage: units, cells, trades; flags)
Per store: cells, trades, sessions of the calendar / used / skipped / evenings skipped, sessions (of the seven) that hold a
trade, cells without a trade, skipped_by_error, both-sides declaration vs the simulator's evidence, exec guard, wall-clock.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
W = HERE.parents[1]
for p in (str(W), str(W / "engine")):
    if p not in sys.path:
        sys.path.insert(0, p)
import library  # noqa: E402


def rows() -> list:
    led = library.read_ledger()
    wall = {}
    f = HERE / "driver.jsonl"
    if f.exists():
        for ln in f.read_text().splitlines():
            r = json.loads(ln)
            if "wall_s" in r:
                wall[r["tag"]] = r["wall_s"]
    out = []
    for r in led:
        key = r["key"]
        row = {"key": key, "stage": r["stage"], "family": r["family"], "root": r["root"], "tf": r["tf"], "control": r["control"],
               "cells": int(r["cells"] or 0), "null_cells": int(r.get("null_cells") or 0), "trades": int(r["trades"] or 0), "pass_s": r["elapsed_s"], "wall_s": wall.get(key, ""),
               "note": r["note"]}
        d = library.RUNS / key
        if r["stage"].endswith("_error") or not (d / "run.json").exists():
            row.update(store=False)
            out.append(row)
            continue
        m = json.loads((d / "run.json").read_text())
        z = np.load(d / "cells.npz")
        sess = Counter(int(s) for s in z["sess"])
        cov = m["coverage"]
        cells = m["cells"]
        bs = max((c.get("both_sides_sessions") or 0) for c in cells)
        row.update(store=True, period=m.get("period"), range=f"{m['range']['start']}..{m['range']['end']}",
                   sessions=cov["sessions"], used=cov["used"], skipped=len(cov["skipped"]), eve_skipped=len(cov.get("eve_skipped") or []),
                   sess_with_trades="+".join(library.SESS7[s] for s in sorted(sess) if s >= 0),
                   trades_no_session=sess.get(-1, 0),
                   cells_without_trades=sum(1 for c in cells if not c["trades"]),
                   skipped_by_error=sum(c.get("skipped_by_error", 0) for c in cells),
                   unrealistic_winners=sum(c.get("unrealistic_winners", 0) for c in cells),
                   both_sides_declared=m.get("both_sides_declared"), both_sides_sessions_max=bs,
                   both_sides_ok=bool(m.get("both_sides_declared") or bs == 0) if "both_sides_declared" in m else "",
                   features="+".join(m.get("features") or []), loader=m.get("features_loader") or "",
                   exec_guard=json.dumps(m.get("exec_guard")) if m.get("exec_guard") else "",
                   base_pass_sessions="+".join(m.get("base_pass_sessions") or []))
        out.append(row)
    return out


def main() -> int:
    rs = rows()
    cols = []
    for r in rs:
        for k in r:
            if k not in cols:
                cols.append(k)
    with (HERE / "run_table.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        w.writerows(rs)
    agg = defaultdict(lambda: [0, 0, 0, 0])
    for r in rs:
        a = agg[(r["root"], r["stage"])]
        a[0] += 1
        a[1] += r["cells"]
        a[2] += r["trades"]
        a[3] += r["null_cells"]
    for k in sorted(agg):
        print(k, dict(zip(("stores", "cells", "trades", "null_cells"), agg[k])))
    used = library.ledger_used()
    print("ledger", used, "caps", library.CAPS)
    flags = [r for r in rs if not r.get("store") or r.get("skipped_by_error") or r.get("both_sides_ok") is False
             or r.get("trades_no_session") or r.get("period") != "build" or r.get("skipped")]
    print("flags", len(flags))
    for r in flags:
        print(" ", {k: r.get(k) for k in ("key", "stage", "store", "skipped_by_error", "both_sides_ok", "trades_no_session", "period",
                                         "skipped", "note")})
    return 0


if __name__ == "__main__":
    sys.exit(main())
