#!/usr/bin/env python3
"""ENGINE OWNER: pass-time ratio of the new exit convention (seven instances, hold_to day, EARLY_STOP) against the old one
(three instances) on the 10 smoke days, 1 worker. Prints seconds and trade COUNTS only."""
import sys
import time
from pathlib import Path

W = Path(__file__).resolve().parents[2]
for _p in (str(W), str(W / "engine")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import l2sim as S          # noqa: E402
import run_menus as RM     # noqa: E402


def main():
    import families as F
    for name, root, tf in (("donchian", "NQ", "5"), ("vwap_z", "NQ", "30"), ("orb", "ES", "15"), ("straddle_t_0930", "NQ", "30"),
                           ("tod_drift", "NQ", "1")):
        grid = F.unit_grid(name, root, tf)[::2]
        days = [d for d in RM.SMOKE_DAYS if S._date(d) in set(S.sessions(*S.period("build"), root))]
        out = {}
        for hold in ("session", "day"):
            t0 = time.monotonic()
            res = RM.run_grid(grid, root, features=None, workers=1, days=days, hold=hold)
            out[hold] = (round(time.monotonic() - t0, 1), sum(len(r["trades"]) for r in res), len(RM.cell_specs(grid[0], hold)))
        S.EARLY_STOP = False
        t0 = time.monotonic()
        RM.run_grid(grid, root, features=None, workers=1, days=days, hold="day")
        S.EARLY_STOP = True
        full = round(time.monotonic() - t0, 1)
        print(name, root, tf, "cells", len(grid), "| old s/trades/instances", out["session"], "| new", out["day"],
              "| new without early stop s", full, "| ratio new/old", round(out["day"][0] / out["session"][0], 2), flush=True)


if __name__ == "__main__":
    main()
