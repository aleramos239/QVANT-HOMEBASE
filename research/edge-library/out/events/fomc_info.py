"""STAGE 3, INFORMATION ONLY (never judged, never opened on 2024): the tight straddle fired at 14:00 ET on the 19 BUILD days with a
Fed (FOMC) decision. No store existed: the existing family class (round1.StraddleTight) is run with at = 13:59:59 (entries
until 15:00, unfilled legs cancelled after 5 min, flat 15:58) on those days only: 27 cells x NQ, ES, GC, booked as candidate
cells (stage ev_info). Too few trades for any test.  python out/events/fomc_info.py -> out/events/fomc_1400.json"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
W = HERE.parents[1]
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
sys.path.insert(0, str(HERE))
import ev as E  # noqa: E402
import families as F  # noqa: E402
import l2sim as S  # noqa: E402
import library as LB  # noqa: E402
import run_menus as RM  # noqa: E402

RA = W / "runs_events"


def main():
    out = {}
    for root in E.ROOTS:
        key = f"straddle_tight_1400-{root}-tf30-fomc-build"
        cal = LB.calendar("build", root)
        days = [d for d in cal if d in E.days("FOMC")]
        assert days and days[-1] < "2024-01-01"
        if not (RA / key / "run.json").exists():
            grid = F.unit_grid("straddle_tight_1000", root, "30")
            for c in grid:
                k, p = c["spec"]
                c["spec"] = (k, {**p, "at": "13:59:59", "flat": "15:00:00", "hold_to": "day"})
            S.wait_compute_window()
            res = S.run_many([c["spec"] for c in grid], days=days, root=root, workers=RM.auto_workers(4), features=F.features_for("straddle_tight_1000"))
            assert not sum(r["skipped_by_error"] for r in res)
            meta = {"family": "straddle_tight_1400", "tf": "30", "stage": "ev_info", "period": "build", "sess_instance": "pm", "stress": False,
                    "hold_to": "day", "control": "", "days": days, "why": "FOMC 14:00, BUILD FOMC days only, information"}
            LB.write_unit(key, meta, grid, res, RA)
            LB.ledger_add("ev_info", key, "grid", cells=len(grid), family="straddle_tight_1400", root=root, tf="30", period="build", control="",
                          trades=sum(len(r["trades"]) for r in res), elapsed_s=res[0]["elapsed_s"],
                          note="stage 3 information: FOMC 14:00 on the 19 BUILD FOMC days only")
        u = LB.load_unit(key, RA)
        table = LB.session_table(u, "all")
        pl = LB.plateau(table)
        row = {"days": len(days), "cells": pl["cells"], "share_pos": pl["share_pos"], "median_net": pl["median_net"], "central": pl["member"],
               "best_net": pl["best_net"], "worst_net": pl["worst_net"]}
        if pl["member"]:
            st = LB.stats(LB.unit_cell(u, pl["member"])["net"])
            row.update(trades=st["trades"], net=st["net"], t=st["t"], win=st["win"])
        out[root] = row
        print(root, row)
    (HERE / "fomc_1400.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
