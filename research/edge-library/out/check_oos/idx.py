"""CHECKER OOS: index of EVERY store under runs*/ (incl. runs_void): range, control, seeds, file time, min/max trade date.
Own code; reads run.json + cells.npz only."""
import json, datetime as dt, os, sys
from pathlib import Path
import numpy as np
W = Path("/Users/ramoscapital/ramos-quant-homebase/research/edge-library")
out = []
for d in sorted(p for p in W.glob("runs*") if p.is_dir()):
    for p in sorted(d.glob("*/run.json")):
        try:
            m = json.loads(p.read_text())
        except Exception as e:
            out.append({"dir": d.name, "key": p.parent.name, "error": str(e)}); continue
        rg = m.get("range") or {}
        z = np.load(p.parent / "cells.npz")
        date = z["date"]
        ent = z["entry_ms"]
        r = {"dir": d.name, "key": p.parent.name, "start": str(rg.get("start") or ""), "end": str(rg.get("end") or ""),
             "period": m.get("period"), "stage": m.get("stage"), "control": m.get("control"), "family": m.get("family"), "root": m.get("root"),
             "tf": str(m.get("tf")), "sess": m.get("sess_instance"), "stress": bool(m.get("stress")), "oco": m.get("oco_cancel_ms") or 0,
             "seed": m.get("seed"), "ncells": len(m.get("cells") or []), "ntrades": int(len(date)),
             "min_date": dt.date.fromordinal(int(date.min())).isoformat() if len(date) else "",
             "max_date": dt.date.fromordinal(int(date.max())).isoformat() if len(date) else "",
             "max_entry_utc": dt.datetime.utcfromtimestamp(int(ent.max()) / 1000).isoformat() if len(ent) else "",
             "mtime_run": dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
             "mtime_npz": dt.datetime.fromtimestamp((p.parent / "cells.npz").stat().st_mtime).isoformat(timespec="seconds"),
             "holdout": rg.get("holdout"), "allow_exam": m.get("allow_exam"), "skipped": (m.get("coverage") or {}).get("skipped"),
             "sessions": (m.get("coverage") or {}).get("sessions"), "used": (m.get("coverage") or {}).get("used")}
        out.append(r)
(Path(__file__).parent / "idx.json").write_text(json.dumps(out, indent=0))
print(len(out), "stores")
from collections import Counter
print(Counter(r["dir"] for r in out))
late = [r for r in out if (r.get("max_date") or "") >= "2026-01-01" or (r.get("end") or "") >= "2026-01-01" or (r.get("max_entry_utc") or "") >= "2026-01-01"]
print("stores touching 2026:", len(late))
for r in late:
    print(" ", r["dir"], r["key"], r["start"], r["end"], r["min_date"], r["max_date"], r["mtime_npz"])
l25 = [r for r in out if not ((r.get("max_date") or "") >= "2026-01-01") and ((r.get("max_date") or "") >= "2025-01-01" or (r.get("end") or "") >= "2025-01-01")]
print("stores touching 2025 (not 2026):", len(l25))
print(Counter(r["dir"] for r in l25))
