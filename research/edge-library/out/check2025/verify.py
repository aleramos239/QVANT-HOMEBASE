"""After the runs: counts and equality checks of every store this stage wrote (no P&L is read). Prints a summary and writes
out/check2025/stores.csv (store, period, kind, seeds, cells, trades, sessions, used, date range of the trades)."""
import csv
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
sys.path.insert(0, str(W / "out" / "check2025"))
import library as LB  # noqa: E402
import run_check as RC  # noqa: E402

RANGE = {"build": ("2021-09-22", "2023-12-31"), "pick": ("2024-01-01", "2024-12-31"), "check": ("2025-01-01", "2025-12-31")}
jobs = []
for f in ("menus_A", "menus_B", "controls2_A", "controls2_B", "extra_seeds_A", "extra_seeds_B"):
    jobs += json.loads((W / "out" / "check2025" / f"jobs_{f}.json").read_text())
rows, bad, missing = [], [], []
for j in jobs:
    d, key = RC.job_dir(j), RC.job_key(j)
    if not (d / key / "run.json").exists():
        missing.append(f"{d.name}/{key}")
        continue
    u = LB.load_unit(key, d)
    m = u["meta"]
    a, b = RANGE[j["period"]]
    grid = RC.job_grid(j)[0]
    ids = [c["id"] for c in m["cells"]]
    dates = u["date"]
    lo = dt.date.fromordinal(int(dates.min())).isoformat() if len(dates) else ""
    hi = dt.date.fromordinal(int(dates.max())).isoformat() if len(dates) else ""
    last_ms = int((u["entry_ms"] + u["dur_s"].astype(np.int64) * 1000).max()) if len(dates) else 0
    end_ms = int(dt.datetime.fromisoformat(b).replace(tzinfo=RC.S.ET).timestamp() * 1000) + 86_400_000
    seeds = sorted({int(i.split("_", 1)[0][1:]) for i in ids}) if RC.job_kind(j) == "control" else []
    want_seeds = sorted(int(x) for x in (j.get("seeds") or (1, 2))) if RC.job_kind(j) == "control" else []
    checks = {"range": (m["range"]["start"], m["range"]["end"]) == (a, b), "cells": ids == [c["id"] for c in grid],
              "trade dates in period": (not len(dates)) or (a <= lo and hi <= b), "nothing after the period end": last_ms < end_ms,
              "errors 0": sum(c["skipped_by_error"] for c in m["cells"]) == 0, "seeds": seeds == want_seeds,
              "session instance": m.get("sess_instance") == j["sess"], "stress flag": bool(m.get("stress")) == bool(j.get("stress")),
              "oco": int(m.get("oco_cancel_ms") or 0) == (RC.OCO_MS if (j.get("stress") and j.get("oco")) else 0),
              "ledger row": LB.ledger_has(key, RC.stage_of(j))}
    if RC.job_kind(j) != "control" or j.get("c1"):       # a bar-based store / a pool holds its session's trades only
        if not (j.get("family") and RC.RM.is_time_fired(RC.F.REGISTRY[j["family"]][0])):
            checks["one session"] = bool((u["sess"] == LB.SESS_CODE[j["sess"]]).all())
    for k, ok in checks.items():
        if not ok:
            bad.append(f"{d.name}/{key}: {k}")
    rows.append({"store": f"{d.name}/{key}", "unit": j.get("unit", ""), "period": j["period"], "kind": RC.job_kind(j),
                 "seeds": f"{seeds[0]}-{seeds[-1]}" if seeds else "", "cells": len(ids), "trades": int(len(dates)),
                 "sessions": m["coverage"]["sessions"], "used": m["coverage"]["used"], "cells_no_trade": sum(c["trades"] == 0 for c in m["cells"]),
                 "skipped_by_error": sum(c["skipped_by_error"] for c in m["cells"]), "outside_session": m.get("sanity", {}).get("outside_session"),
                 "first_trade_date": lo, "last_trade_date": hi, "ledger_stage": RC.stage_of(j)})
with (W / "out" / "check2025" / "stores.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print("jobs", len(jobs), "stores on disk", len(rows), "missing", missing)
print("failed checks:", bad if bad else "none")
agg = {}
for r in rows:
    k = (r["kind"], r["period"], r["seeds"])
    x = agg.setdefault(k, {"stores": 0, "cells": 0, "trades": 0, "cells_no_trade": 0, "errors": 0, "outside": 0, "used": set(), "max_date": ""})
    x["stores"] += 1; x["cells"] += r["cells"]; x["trades"] += r["trades"]; x["cells_no_trade"] += r["cells_no_trade"]
    x["errors"] += r["skipped_by_error"]; x["outside"] += r["outside_session"] or 0; x["used"].add(f"{r['used']}/{r['sessions']}")
    x["max_date"] = max(x["max_date"], r["last_trade_date"])
for k, x in sorted(agg.items()):
    print(k, {**x, "used": sorted(x["used"])})
led = LB.read_ledger()
mine = [r for r in led if r["stage"] in ("v2_check", "v2_check_stress", "null_v2_check", "null_f2_build", "null_f2_pick", "null_f2_check")
        or (r["stage"] == "v2_stress" and r["key"] == "donchian-NQ-tf30-nyam-pick-stress")]
by = {}
for r in mine:
    x = by.setdefault(r["stage"], [0, 0, 0])
    x[0] += 1; x[1] += int(r["cells"] or 0); x[2] += int(r["null_cells"] or 0)
print("ledger rows of this stage (rows, candidate cells, control cells):", by)
print("ledger totals:", LB.ledger_used(led), "control cells", LB.ledger_nulls(led), "| candidate cap", RC.CAPS["cells"], "left", RC.CAPS["cells"] - LB.ledger_used(led)["cells"])
reads = list(csv.DictReader((W / "out" / "check2025" / "reads.csv").open()))
on_disk_2025 = {r["store"] for r in rows if r["period"] == "check"}
print("reads.csv rows", len(reads), "distinct stores", len({r["store"] for r in reads}), "2025 stores on disk not in reads.csv:", sorted(on_disk_2025 - {r["store"] for r in reads}))
late = [str(p.parent) for dd in (RC.RC, RC.RS) for p in dd.glob("*/run.json") if json.loads(p.read_text())["range"]["end"] > "2025-12-31"]
print("stores whose range ends after 2025-12-31:", late if late else "none")
