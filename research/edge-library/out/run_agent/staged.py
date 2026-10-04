#!/usr/bin/env python3
"""RUN AGENT: stage D (EDGE_SPEC D2 / D3 / D4 on the breakout bases), by the rule pre-declared in progress.md (14:58 ET).

    python staged.py seal     the seal table (base unit x session: plateau pass) of the 36 stage D names -> staged.json
    python staged.py grids    step 1: the variant grids (nulls=False) of every (name, tf) whose base passed in >= 1 session
    python staged.py nulls    step 2: the two C2 grid nulls of every variant whose OWN BUILD plateau passes in >= 1 base-pass session
    python staged.py cuts     the ES / GC cuts that stage D needs -> cuts.json (GC then ES; mid_fade, rsi2, tema_slope, ...)

Budget (2026-10-03, nulls outside the cap): 40,000 - 28,608 candidate cells of the base plan = 11,392; the C2 null passes are
tracked as null cells (uncapped), so only the variant GRIDS count here. No cuts are needed. A pass that does not fit stops the
step (rc 3) and everything after it is listed as NOT RUN (cap). Only pass flags of library.plateau are used.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
W = HERE.parents[1]
for p in (str(W), str(W / "engine")):
    if p not in sys.path:
        sys.path.insert(0, p)

BASE_PLAN = 28608          # 2026-10-03: candidate cells only; null / control cells are NOT capped (EDGE_SPEC decision 6)
CAP = 40000
LOW_PRIOR = ["mid_fade", "rsi2", "tema_slope", "ema_ribbon", "supertrend", "pinbar", "gap"]
LOW_CELLS = {"mid_fade": 128, "rsi2": 384, "tema_slope": 384, "ema_ribbon": 128, "supertrend": 128, "pinbar": 384, "gap": 256}
BUDGET = CAP - BASE_PLAN           # 11,392: all 36 stage D grids (8,160 cells at most) fit without any cut
BASES = [f"straddle_t_{t}" for t in ("1800", "2000", "0000", "0200", "0300", "0830", "0930", "1105", "1330")] + ["orb", "straddle", "donchian"]
OPTS = ("fbook", "xbook", "thin")
STATE = HERE / "staged.json"
CUTS = HERE / "cuts.json"


def order() -> list:
    import families
    out = []
    for b in BASES:
        for tf in families.REGISTRY[b][0].SCREEN_TFS:
            for o in OPTS:
                out.append((f"{b}_{o}", str(tf)))
    return out


def used_cells() -> int:
    """Stage D cells already in the ledger (grids + C2 nulls, failed passes included)."""
    import library
    from families import l2ideas as L
    names = set(L.STAGE_D)
    return sum(int(r["cells"] or 0) for r in library.read_ledger() if r["family"] in names)


def seal() -> dict:
    from families import l2ideas as L
    rows = []
    for name, tf in order():
        try:
            s = L.base_sessions(name, tf)
            err = None
        except L.StageDSealed as e:
            s, err = [], str(e)
        rows.append({"name": name, "tf": tf, "base_pass_sessions": s, "cells": len(L.variant_grid(name, "NQ", tf)), "sealed": err})
    return {"rows": rows}


def save(doc: dict) -> None:
    STATE.write_text(json.dumps(doc, indent=1))


def load() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else seal()


def grids() -> int:
    from families import l2ideas as L
    import library
    doc = seal()
    rc = 0
    for r in doc["rows"]:
        r.setdefault("grid", None)
        if r["sealed"] or not r["base_pass_sessions"]:
            r["grid"] = "not run: base passed no session" if not r["sealed"] else "not run: no base store"
            continue
        key = L.variant_key(r["name"], "NQ", r["tf"])
        if library.ledger_has(key, "build"):
            r["grid"] = "done"
            continue
        if rc == 3 or used_cells() + r["cells"] > BUDGET:
            r["grid"] = "NOT RUN (cap)"
            rc = 3
            continue
        out = L.run_variant(r["name"], r["tf"], nulls=False, workers=8)
        ok = all(o.get("ok", True) for o in out)
        r["grid"] = "done" if ok else f"ERROR {out}"
        save(doc)
    doc["grid_cells_used"] = used_cells()
    save(doc)
    return rc


def nulls() -> int:
    from families import l2ideas as L
    import library
    doc = load()
    rc = 0
    for r in doc["rows"]:
        r["own_pass_sessions"], r["c2"] = [], None
        if r.get("grid") != "done":
            continue
        r["own_pass_sessions"] = [s for s in r["base_pass_sessions"]
                                  if library.plateau(L.variant_table(r["name"], r["tf"], s))["pass"]]
        if not r["own_pass_sessions"]:
            r["c2"] = "not run: the variant's own plateau passed in no base-pass session"
            continue
        key = L.variant_key(r["name"], "NQ", r["tf"])
        if all(library.ledger_has(f"{key}-c2s{sd}", "null") for sd in L.C2_SEEDS):
            r["c2"] = "done"
            continue
        # C2 null cells are ledger kind 'null' (null_cells), NOT capped (2026-10-03): no budget test here
        out = L.run_variant(r["name"], r["tf"], nulls=True, workers=8)
        r["c2"] = "done" if all(o.get("ok", True) for o in out) else f"ERROR {out}"
        save(doc)
    doc["cells_used"] = used_cells()
    save(doc)
    return rc


def cuts() -> int:
    doc = load()
    used = used_cells()
    need = max(0, used - (CAP - BASE_PLAN))
    cut, freed = [], 0
    for root in ("GC", "ES"):
        for f in LOW_PRIOR:
            if freed >= need:
                break
            cut.append({"family": f, "root": root, "cells": LOW_CELLS[f]})
            freed += LOW_CELLS[f]
    out = {"stage_d_cells": used, "left_before_cuts": CAP - BASE_PLAN, "needed": need, "freed": freed, "cut": cut,
           "rule": "GC before ES; mid_fade, rsi2, tema_slope, ema_ribbon, supertrend, pinbar, gap; only as many as needed"}
    CUTS.write_text(json.dumps(out, indent=1))
    doc["cuts"] = out
    save(doc)
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "seal":
        d = seal()
        save(d)
        for r in d["rows"]:
            print(r["name"], r["tf"], r["cells"], r["base_pass_sessions"], r["sealed"] or "")
        sys.exit(0)
    sys.exit({"grids": grids, "nulls": nulls, "cuts": cuts}[cmd]())
