"""CHECKER v2, 2024 ON ITS OWN: tests (4), (5), (6), the surviving set and the default, for the units the ANALYST opened on 2024
(out/v2/pick_units.json keys = cells already read). My own code (chk_lib). First asserts that every opened unit passes BUILD
(1)-(3) by MY numbers (chk_build.json). Logs every 2024 store I open in checker_pick_reads.csv.
  python chk_pick.py"""
import csv
import datetime as dt
import json
import sys
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chk_lib as C  # noqa: E402
from chk_build import my_controls, sd  # noqa: E402

RV = C.W / "runs_v2"


def controls_pick(pst, u, ids, avg):
    res = {}
    for c in my_controls(u):
        s = sd(u["uid"], "pick-" + c)
        if c == "c1":
            pu = C.pick_store(f"c1-{u['root']}-tf{u['tf']}-{u['sess']}-pick")
            res[c] = C.verdict(avg, C.c1_table(pst, u, ids, pu, s), False) if pu else {"pass": False, "why": "no 2024 pool"}
        elif c == "shift":
            su = C.pick_store(f"{u['base'] or u['family']}-{u['root']}-tf{u['tf']}-{u['sess']}-pick-shift")
            res[c] = C.verdict(avg, C.shift_table(su, u, ids, "pick", s), False) if su else {"pass": False, "why": "no 2024 random-minute store"}
        elif c == "c2":
            s1, s2 = (C.pick_store(f"{u['key']}-{u['sess']}-pick-c2s{k}") for k in (1, 2))
            res[c] = C.verdict(avg, C.c2_table(s1, s2, u, ids, "pick", s), False) if s1 and s2 else {"pass": False, "why": "no 2024 shuffled-book store"}
        elif c == "base":
            bs = C.pick_store(f"{u['base']}-{u['root']}-tf{u['tf']}-{u['sess']}-pick")
            res[c] = C.base_test(pst, bs, u, ids) if bs else {"pass": False, "why": "no 2024 base store"}
        elif c == "days":
            res[c] = C.days_test(pst, u, ids, s, False)
    return res


def main():
    B = {r["uid"]: r for r in json.loads((C.OUT / "chk_build.json").read_text())}
    AP = json.loads((C.W / "out" / "v2" / "pick_units.json").read_text())
    AF = json.loads((C.W / "out" / "v2" / "final.json").read_text())
    U = {u["uid"]: u for u in C.units()}
    mine_pass = {uid for uid, r in B.items() if r["build_pass"]}
    print("analyst opened", len(AP), "| my BUILD passers", len(mine_pass), "| opened but not my passer", sorted(set(AP) - mine_pass),
          "| my passer not opened", sorted(mine_pass - set(AP)))
    out = {}
    for uid in AP:
        u = U[uid]
        bst = C.build_store(u["key"])
        brows = C.build_rows(bst, u)
        bts = C.tstats(brows)
        pst = C.pick_store(f"{u['key']}-{u['sess']}-pick")
        assert pst is not None, uid
        prow = C.rows_on(pst, u, brows)
        pts = C.tstats(prow)
        # the same test with the BUILD-judged variants kept one for one (no 2024 de-duplication)
        pn = {r["id"]: r["net"] for r in prow}
        fix = np.array([pn[c] for c in bts["ids"] if c in pn])
        missing = [c for c in bts["ids"] if c not in pn]
        t4 = bool(pts["cells"] and pts["avg"] > 0 and pts["median"] > 0)
        det = controls_pick(pst, u, pts["ids"], pts["avg"]) if pts["cells"] else {}
        t5 = bool(det) and all(v["pass"] for v in det.values())
        o = {"uid": uid, "cells_2024": pts["cells"], "cells_build": bts["cells"], "missing_in_2024": missing, "share": pts.get("share"), "avg": pts.get("avg"),
             "median": pts.get("median"), "avg_trades": pts.get("avg_trades"), "t4": t4, "t5": t5, "det": det,
             "fix_avg": float(fix.mean()) if len(fix) else None, "fix_median": float(np.median(fix)) if len(fix) else None,
             "fix_share": float((fix > 0).mean()) if len(fix) else None,
             "trades_all": B[uid]["avg_trades"] + pts.get("avg_trades", 0.0), "oco_declared": bool(bst["meta"].get("both_sides_declared")),
             "both_sides_sessions_build": int(sum(c.get("both_sides_sessions", 0) for c in bst["meta"]["cells"]))}
        o["t3_final"] = bool(o["trades_all"] >= 100)
        skey = f"{u['key']}-{u['sess']}-pick-stress"
        if (RV / skey / "run.json").exists():
            # a stress store is opened only if the analyst's own (4) and (5) passed (he ran it only then)
            sst = C.pick_store(skey, [RV])
            m = sst["meta"]
            sts = C.tstats(C.rows_on(sst, u, brows))
            o.update(stress_avg=sts.get("avg"), stress_share=sts.get("share"), t6=bool(sts["cells"] and sts["avg"] > 0),
                     stress_meta={"stress": m.get("stress"), "oco_cancel_ms": m.get("oco_cancel_ms"), "cells": len(m["cells"])})
            net = lambda s, cid, dm=C.day_filter(u): float(C.cell(s, cid, u["sess"], dm)["net"].sum()) if cid in s["idx"] else None  # noqa: E731
            cand = [c for c in bts["ids"] if net(bst, c) > 0 and (net(pst, c) or 0) > 0 and (net(sst, c) or 0) > 0]
            bkey = f"{u['key']}-{u['sess']}-build-stress"
            if t4 and t5 and o["t6"] and cand and (RV / bkey / "run.json").exists():
                bs = C.stress_build_store(bkey)
                o["build_stress_meta"] = {"stress": bs["meta"].get("stress"), "oco_cancel_ms": bs["meta"].get("oco_cancel_ms")}
                not_run = [c for c in cand if c not in bs["idx"]]
                surv = [c for c in cand if c in bs["idx"] and net(bs, c) > 0]
                br = {r["id"]: r for r in brows}
                order = sorted(surv, key=lambda c: (round(br[c]["net"], 2), br[c]["vi"], br[c]["xi"]))
                o.update(survivors=order, cand_not_in_build_stress=not_run, default=order[(len(order) - 1) // 2] if order else None,
                         best=order[-1] if order else None)
        else:
            o["t6"] = None
        o["admit"] = bool(t4 and t5 and o.get("t6") and o.get("survivors") and o["t3_final"])
        out[uid] = o
        a, f = AP[uid], AF[uid]
        flags = []
        if a["t4"] != t4:
            flags.append("t4 differs")
        if a["t5"] != t5:
            flags.append("t5 differs")
        if bool(f["t6"]) != bool(o.get("t6")):
            flags.append("t6 differs")
        if f["admit"] != o["admit"]:
            flags.append("ADMIT differs")
        if f.get("default") != o.get("default"):
            flags.append(f"default differs {f.get('default')} vs {o.get('default')}")
        if sorted(f.get("survivors") or []) != sorted(o.get("survivors") or []):
            flags.append("survivors differ")
        if abs(a["avg_net"] - pts.get("avg", 0)) > 0.01 or abs(a["median_net"] - pts.get("median", 0)) > 0.01:
            flags.append("avg/median differ")
        o["flags"] = flags
        lifts = {c: v.get("lift", (round(v["per_trade"] - v.get("unfiltered_per_trade", v.get("base_per_trade", 0)), 2) if "per_trade" in v else None)) for c, v in det.items()}
        print(f"{uid:44s} cells {pts['cells']:3d} share {pts.get('share', 0):.3f} avg {pts.get('avg', 0):9.0f} med {pts.get('median', 0):9.0f} "
              f"(4){'P' if t4 else 'f'} (5){'P' if t5 else 'f'} {lifts} (6){o.get('t6')} stress {o.get('stress_avg')} surv {len(o.get('survivors') or [])} "
              f"def {o.get('default')} admit {o['admit']} {flags}", flush=True)
    (C.OUT / "chk_pick.json").write_text(json.dumps(out, indent=1))
    print("mine: (4)", sum(o["t4"] for o in out.values()), "(4)+(5)", sum(o["t4"] and o["t5"] for o in out.values()),
          "+(6)", sum(bool(o["t4"] and o["t5"] and o.get("t6")) for o in out.values()), "admit", sum(o["admit"] for o in out.values()))
    new = not (C.OUT / "checker_pick_reads.csv").exists()
    with (C.OUT / "checker_pick_reads.csv").open("a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["utc", "dir", "key", "what"])
        for d, k in C.READS:
            w.writerow([dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), d, k, "chk_pick.py: tests (4)-(6) re-judged from the store (already read by the analyst)"])


if __name__ == "__main__":
    main()
