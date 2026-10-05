"""CHECKER v2: donchian-NQ-tf30|nyam| (v1 member, demoted). The analyst's 200 draws gave 93.5 % on test (2); 4000 draws give 96.0 %.
Its 2024 menu, 2024 random pool and stress stores are on disk since v1 (runs_admit, read by the analyst then; the 2024 menu was
read again in v2 as the base of donchian_thin). Tests (4)-(6) from those stores only -- no new 2024 cell is run or read."""
import csv, datetime as dt, json, sys, zlib
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import chk_lib as C
RA = C.W / "runs_admit"
uid = "donchian-NQ-tf30|nyam|"
u = {x["uid"]: x for x in C.units()}[uid]; u.pop("A")
bst = C.build_store(u["key"]); brows = C.build_rows(bst, u); bts = C.tstats(brows)
pst = C.pick_store(f"{u['key']}-{u['sess']}-pick", [RA]); prow = C.rows_on(pst, u, brows); pts = C.tstats(prow)
t4 = bool(pts["avg"] > 0 and pts["median"] > 0)
pu = C.pick_store(f"c1-{u['root']}-tf{u['tf']}-{u['sess']}-pick", [RA])
dr = np.concatenate([C.c1_table(pst, u, pts["ids"], pu, zlib.crc32(f"checker|{uid}|pick-c1|{b}".encode()))["draws"] for b in range(20)])
lift = pts["avg"] - float(dr.mean()); t5 = bool(lift > 0)
sst = C.pick_store(f"{u['key']}-{u['sess']}-pick-stress", [RA])
have = [r for r in brows if r["id"] in sst["idx"]]
sts = C.tstats(C.rows_on(sst, u, have))  # v1 ran stress on a subset of cells only: NOT the whole-menu test (6)
bs = C.load(f"{u['key']}-{u['sess']}-build-stress", RA)
net = lambda s, c: float(C.cell(s, c, u["sess"])["net"].sum()) if c in s["idx"] else None
cand = [c for c in bts["ids"] if net(bst, c) > 0 and (net(pst, c) or 0) > 0 and (net(sst, c) or 0) > 0]
surv = [c for c in cand if c in bs["idx"] and net(bs, c) > 0]
out = {"uid": uid, "build": {"cells": bts["cells"], "share": bts["share"], "avg": bts["avg"], "avg_trades": bts["avg_trades"]},
       "y2024": {"cells": pts["cells"], "share": pts["share"], "avg": pts["avg"], "median": pts["median"], "avg_trades": pts["avg_trades"]},
       "t4": t4, "lift_2024": lift, "p_2024": float((pts["avg"] > dr).mean()), "t5": t5,
       "stress_meta": {k: sst["meta"].get(k) for k in ("stress", "oco_cancel_ms", "period")}, "stress_cells": sts["cells"], "stress_avg_2024": sts.get("avg"),
       "t6": None, "stress_note": "v1 stress store holds only part of the menu; test (6) needs a whole-menu 2024 stress run (not run by me)", "both_sides_declared": bst["meta"].get("both_sides_declared"),
       "cand": len(cand), "cand_not_in_build_stress": len([c for c in cand if c not in bs["idx"]]), "survivors": len(surv),
       "build_stress_meta": {k: bs["meta"].get(k) for k in ("stress", "oco_cancel_ms", "period")}, "build_stress_cells": len(bs["meta"]["cells"])}
print(json.dumps(out, indent=1))
(C.OUT / "chk_donchian30.json").write_text(json.dumps(out, indent=1))
with (C.OUT / "checker_pick_reads.csv").open("a", newline="") as fh:
    w = csv.writer(fh)
    for d, k in C.READS:
        w.writerow([dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), d, k, "chk_donchian30.py: v1 member's 2024 stores on disk since v1 (already read by the analyst in v1; menu re-read in v2 as a base control)"])
