"""ENGINE OWNER: stage D classes (l2ideas D2 / D3 / D4) under hold_to='day' on the 10 smoke days -- COUNTS ONLY."""
import sys
from pathlib import Path
W = Path(__file__).resolve().parents[2]
for _p in (str(W), str(W / "engine")):
    sys.path.insert(0, _p)
import l2sim as S, run_menus as RM


def main():
    from families import l2ideas as L2
    days = list(RM.SMOKE_DAYS)
    bad = 0
    for name, tf in (("orb_fbook", "5"), ("orb_xbook", "5"), ("donchian_thin", "15"), ("straddle_t_0930_xbook", "30"),
                     ("straddle_t_1800_fbook", "30"), ("straddle_xbook", "30")):
        grid = L2.variant_grid(name, "NQ", tf)[::11][:8]
        res = RM.run_grid(grid, "NQ", features=L2.variant_features(name), workers=1, days=days)
        raw = sum(len(r["trades"]) for r in res)
        for r in res:
            r["trades"] = L2.kept(r["trades"])
        chk = RM.hold_checks(res, "NQ")
        errs = sum(r["skipped_by_error"] for r in res)
        ok = errs == 0 and not any(chk.values())
        bad += not ok
        print(name, tf, "cells", len(grid), "instances", len(RM.cell_specs(grid[0])), "fills", raw, "kept", sum(len(r["trades"]) for r in res),
              chk, "errors", errs, "OK" if ok else "FAIL", flush=True)
    print("ALL OK" if not bad else f"{bad} FAILED")


if __name__ == "__main__":
    main()
