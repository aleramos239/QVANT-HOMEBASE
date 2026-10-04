"""STAGE 2b, INFORMATION ONLY (not a test): every round 1 unit's heat map on QUIET days (prior-day range at or below its 20-day
median) and on ACTIVE days (above), BUILD only, labels from out/deepen/labels.py (daily bars dated before the trade date).
Writes out/admit_r1/quiet_active.csv."""
import csv
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
sys.path.insert(0, str(W / "out" / "deepen"))
import labels as LBL  # noqa: E402
import library as LB  # noqa: E402

OUT = W / "out" / "admit_r1"


def one(key):
    u = LB.load_unit(key)
    assert u["meta"]["period"] == "build"
    root = u["meta"]["root"]
    cells = u["meta"]["cells"]
    axis = LB.mirror_axis(u)
    sessions = ["all"] if u["meta"]["family"] == "straddle_tight_0930" else LB.unit_sessions(u)
    base = {s: {t["id"]: t for t in LB.session_table(u, s)} for s in sessions}
    rows = []
    for sess in sessions:
        for side in ("vol_lo", "vol_hi"):
            tab = []
            for i, c in enumerate(cells):
                x = LB.unit_cell(u, i)
                m = LBL.side_mask(side, root, x["date"], x["side"])
                if sess != "all":
                    m &= x["sess"] == LB.SESS_CODE[sess]
                st = LB.stats(x["net"][m])
                b = base[sess][c["id"]]
                tab.append({"id": c["id"], "vi": c["vi"], "xi": c["xi"], "net": st["net"], "trades": st["trades"], "t": st["t"], "dead": b["dead"],
                            "info": b["info"], "sig": LB.trade_sig(x, m), "stop_mode": b["stop_mode"], "tgt_r": b["tgt_r"],
                            "label": f"{axis}={c['variant'][axis]}" if axis else ""})
            for label in sorted({t["label"] for t in tab}):
                sub = [t for t in tab if t["label"] == label]
                pl = LB.plateau(sub)
                rows.append({"uid": f"{key}|{sess}|{label}", "side": side, "cells": pl["cells"], "share_pos": pl["share_pos"], "median_net": pl["median_net"],
                             "v60": pl["verdicts"]["60"], "v70": pl["verdicts"]["70"], "v80": pl["verdicts"]["80"],
                             "trades_med": int(np.median([t["trades"] for t in sub if not t["dead"] and not t["info"]] or [0]))})
    return rows


def main():
    keys = sorted({r["key"] for r in csv.DictReader((OUT / "build_units.csv").open())})
    with Pool(8) as pool:
        rows = [r for part in pool.imap_unordered(one, keys, chunksize=1) for r in part]
    rows.sort(key=lambda r: (r["uid"], r["side"]))
    with (OUT / "quiet_active.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("rows", len(rows))


if __name__ == "__main__":
    main()
