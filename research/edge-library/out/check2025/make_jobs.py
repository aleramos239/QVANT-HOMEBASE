"""The job lists of the CHECK-year read (2025) and of the F2 extra control seeds 3 .. 10 (EDGE_SPEC "PERIODS AMENDED",
"ADMISSION v2 -- CHECKER FIXES"). Writes out/check2025/jobs_*.json for run_check.py (and one list for out/v2/run_v2.py).
A unit's menu = the live cells of its BUILD table in its session (judge.menu_ids: not dead, not an author cell)."""
import json
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
import library as LB  # noqa: E402

OUT = W / "out" / "check2025"
SEEDS = list(range(3, 11))
# (family, root, tf, sess, the members / units it serves)
UNITS = [("straddle_t_0830", "NQ", "30", "pre", "member straddle_t_0830_NQ_tf30_pre"),
         ("straddle_tight_0830", "NQ", "30", "pre", "members straddle_tight_0830_NQ_tf30_pre + _evA + _evB (all-days store)"),
         ("straddle_tight_0830", "GC", "30", "pre", "members straddle_tight_0830_GC_tf30_pre_evA + _evB (all-days store)"),
         ("straddle_tight_1000", "NQ", "30", "nyam", "member straddle_tight_1000_NQ_tf30_nyam_evC (all-days store)"),
         ("straddle_tight_1000", "GC", "30", "nyam", "member straddle_tight_1000_GC_tf30_nyam_evC (all-days store)"),
         ("first_bar_mom", "NQ", "30", "mid", "member first_bar_mom_NQ_tf30_mid"),
         ("first_bar_mom", "NQ", "15", "mid", "member first_bar_mom_NQ_tf15_mid"),
         ("first_bar_mom", "ES", "15", "mid", "member first_bar_mom_ES_tf15_mid"),
         ("orb", "NQ", "15", "pre", "member orb_NQ_tf15_pre"),
         ("straddle_t_1800", "NQ", "30", "eve", "member straddle_t_1800_NQ_tf30_eve"),
         ("tema_slope", "NQ", "30", "eve", "member tema_slope_NQ_tf30_eve"),
         ("donchian", "NQ", "30", "nyam", "pending 15th member donchian_NQ_tf30_nyam")]
# C1 pools on BUILD only, for the three pending units (2024 and 2025 stay closed for them)
BUILD_ONLY_C1 = [("NQ", "5", "pm", "pending vol_spike_break-NQ-tf5-pm and donchian-NQ-tf5-pm (BUILD re-judge only)")]
PENDING_SHARED = {("NQ", "30", "mid"): " + pending vwap_z-NQ-tf30-mid (BUILD re-judge only)"}


def unit_info(fam, root, tf, sess):
    u = LB.load_unit(f"{fam}-{root}-tf{tf}")
    rows = LB.plateau_units(u, sess)[""]
    ids = sorted(r["id"] for r in rows if not r.get("info") and not r.get("dead"))
    timed = any("shift_seed" in (c.get("inputs") or {}) for c in u["meta"]["cells"][:1])
    return ids, bool(u["meta"].get("both_sides_declared")), timed


def main():
    menus, ctl2, extra, ident, don = [], [], [], [], []
    c1_seen = {}
    for fam, root, tf, sess, who in UNITS:
        ids, oco, timed = unit_info(fam, root, tf, sess)
        unit = f"{fam}-{root}-tf{tf}-{sess}"
        base = {"family": fam, "root": root, "tf": tf, "sess": sess, "unit": unit}
        menus.append({**base, "period": "check", "cells": ids, "why": f"CHECK 2025, whole menu ({len(ids)} variants): {who}"})
        menus.append({**base, "period": "check", "stress": True, "oco": oco, "cells": ids,
                      "why": f"CHECK 2025, whole menu under stress (2 ticks + 250 ms{' + 100 ms late cancel' if oco else ''}): {who}"})
        ident += [{**base, "period": "check", "cells": ids}, {**base, "period": "check", "stress": True, "oco": oco, "cells": ids}]
        if timed:
            sh = {**base, "shift": True, "cells": ids}
            ctl2.append({**sh, "period": "check", "why": f"CHECK 2025, random-minute control (seeds 1, 2): {who}"})
            ident.append({**sh, "period": "check"})
            for per in ("check", "pick", "build"):
                extra.append({**sh, "period": per, "seeds": SEEDS, "why": f"F2: random-minute control, seeds 3-10, {per}: {who}"})
        else:
            c1_seen.setdefault((root, tf, sess), []).append(who)
        if fam == "donchian":
            don.append({**base, "period": "pick", "stress": True, "oco": oco, "cells": ids,
                        "why": "F1 pending: the whole-menu 2024 stress of donchian NQ 30-min morning (54 of its 64 variants were on disk in runs_admit; "
                               "all 64 in one pass, the 54 compared trade for trade)"})
    for (root, tf, sess), who in c1_seen.items():
        c1 = {"c1": True, "root": root, "tf": tf, "sess": sess, "unit": f"c1-{root}-tf{tf}-{sess}"}
        w = "; ".join(who) + PENDING_SHARED.get((root, tf, sess), "")
        ctl2.append({**c1, "period": "check", "why": f"CHECK 2025, random-entry pool (seeds 1, 2): {w}"})
        ident.append({**c1, "period": "check"})
        for per in ("check", "pick", "build"):
            extra.append({**c1, "period": per, "seeds": SEEDS, "why": f"F2: random-entry pool, seeds 3-10, {per}: {w}"})
    for root, tf, sess, who in BUILD_ONLY_C1:
        c1 = {"c1": True, "root": root, "tf": tf, "sess": sess, "unit": f"c1-{root}-tf{tf}-{sess}"}
        extra.append({**c1, "period": "build", "seeds": SEEDS, "why": f"F2: random-entry pool, seeds 3-10, build: {who}"})
        ident.append({**c1, "period": "build", "build_only": True})
    order = {"check": 0, "pick": 1, "build": 2}
    extra.sort(key=lambda j: order[j["period"]])
    for name, jobs in (("menus", menus), ("controls2", ctl2), ("extra_seeds", extra)):
        for chain, roots in (("A", ("NQ",)), ("B", ("ES", "GC"))):
            sub = [j for j in jobs if j["root"] in roots]
            (OUT / f"jobs_{name}_{chain}.json").write_text(json.dumps(sub, indent=1))
            print(f"jobs_{name}_{chain}.json: {len(sub)} jobs")
    (OUT / "jobs_identity.json").write_text(json.dumps(ident, indent=1))
    (OUT / "jobs_donchian_pick_stress.json").write_text(json.dumps(don, indent=1))
    print("identity", len(ident), "| donchian 2024 stress cells", len(don[0]["cells"]))


if __name__ == "__main__":
    main()
