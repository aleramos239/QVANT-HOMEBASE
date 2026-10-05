"""Compare own recomputation (res/*.json) with the analyst's out/exam2026/oos.json. Prints every number that differs."""
import json, glob
from pathlib import Path
W = Path("/Users/ramoscapital/ramos-quant-homebase/research/edge-library")
A = {x["unit"]: x for x in json.loads((W / "out/exam2026/oos.json").read_text())}
M = {}
for f in sorted(glob.glob("res/*.json")):
    r = json.load(open(f)); M[r["unit"]] = r
bad = 0
def chk(u, what, mine, theirs, tol=0.006):
    global bad
    if mine is None and theirs is None: return
    try:
        ok = abs(float(mine) - float(theirs)) <= tol
    except Exception:
        ok = mine == theirs
    if not ok:
        bad += 1
        print(f"DIFF {u} {what}: mine {mine} analyst {theirs}")
rows = []
for u, m in M.items():
    a = A[u]
    chk(u, "default", m["default"], a["default"]); chk(u, "variants", m["build"]["cells"], a["variants"]); chk(u, "saved", len(m["survivors"]), a["saved"])
    chk(u, "build share_pos", m["build"]["share_pos"], a["build"]["share_pos"], 1e-9); chk(u, "build avg", m["build"]["avg"], a["build"]["avg_net"])
    for per, key in (("pick", "pick"), ("check", "check"), ("exam", "exam")):
        if per not in m:
            if a.get(key): print("ANALYST HAS", u, per, "I do not")
            continue
        x, y = m[per], a.get(key)
        if not y: print("MISSING in analyst", u, per); continue
        for k1, k2 in (("cells", "cells"), ("positive", "positive"), ("avg", "avg_net"), ("median", "median_net"), ("avg_trades", "avg_trades"), ("stress_avg", "stress_avg_net")):
            chk(u, f"{per} {k1}", x.get(k1), y.get(k2))
        for t in ("t4", "t5", "t6"):
            chk(u, f"{per} {t}", x[t], y[t])
        if per != "pick":
            chk(u, f"{per} verdict", x["verdict"], y["verdict"])
            chk(u, f"{per} default net", x["default"]["net"], y["default_net"]); chk(u, f"{per} default stress", x["default"].get("stress_net"), y["default_stress_net"])
            chk(u, f"{per} saved_profitable", x["saved_profitable"], y["saved_profitable"])
        f = x["fast"]["lt5"]
        chk(u, f"{per} fast winners share", None if f["winners_share"] is None else round(f["winners_share"], 4), y["fast_profit_share"], 6e-5)
        chk(u, f"{per} fast net share", None if f["net_share"] is None else round(f["net_share"], 4), y["fast_net_share"], 6e-5)
        for c, v in x["controls"].items():
            w = y["controls"].get(c)
            rows.append((u, per, c, round(v["lift"], 1), w.get("lift", w.get("lift_per_trade")), round(v["p_beat"], 4), w.get("p_beat"), v["pass"], w["pass"], len(v.get("seeds", [])) or "", w.get("seeds", "")))
            if v["pass"] != w["pass"]:
                bad += 1; print("DIFF control pass", u, per, c, v["pass"], w["pass"])
    for c, v in m["build"]["controls"].items():
        w = a["build"]["controls"].get(c)
        rows.append((u, "build", c, round(v["lift"], 1), w.get("lift", w.get("lift_per_trade")), round(v["p_beat"], 4), w.get("p_beat"), v["pass"], w["pass"], len(v.get("seeds", [])) or "", w.get("seeds", "")))
        if v["pass"] != w["pass"]:
            bad += 1; print("DIFF control pass", u, "build", c, v["pass"], w["pass"])
    for y in ("2021", "2022", "2023", "2024", "2025", "2026"):
        if y in m["avg_by_year"]:
            ar = a["avg_rows"].get(y) or a["avg_rows"].get(int(y)) if isinstance(a["avg_rows"], dict) else None
            chk(u, f"avg variant {y}", round(m["avg_by_year"][y], 2), ar["net"] if ar else None, 0.02)
        if m.get("default_by_year") and y in m["default_by_year"]:
            dr = a["default_rows"].get(y) if isinstance(a["default_rows"], dict) else None
            chk(u, f"default {y}", m["default_by_year"][y], dr["net"] if dr else None, 0.02)
print("differences:", bad)
print("\ncontrol table: unit, period, control, lift mine / analyst, p mine / analyst, pass mine / analyst, seeds")
for r in rows:
    flag = "  <-- lift differs > $100" if abs(r[3] - r[4]) > 100 else ""
    print(*r, flag)
