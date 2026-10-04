#!/usr/bin/env python3
"""Build the value-area cache of va_reclaim (N2) for BUILD: engine/cache/va70_<ROOT>.json. Prices and sizes only, no trade.
    python out/engine_owner/round1_va.py [NQ ES GC]      (run_menus.run_unit does the same through VaReclaim.prepare)"""
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(W))
import run_menus as RM  # noqa: E402

if __name__ == "__main__":
    fam = RM.registry()
    from families import round1
    for root in (sys.argv[1:] or ["NQ", "ES", "GC"]):
        out = round1.build_va(root, "build", RM.auto_workers(8))
        have = round1.json.loads(Path(out["path"]).read_text())
        print(root, out, "dates without a value area:", sum(1 for v in have.values() if v is None), flush=True)
