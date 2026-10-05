"""ADMISSION v2: the tables of out/v2_summary.md and out/v2_members.md, from build_units.json / pick_units.json / final.json /
members.json / placebo_counts.json. Prints markdown fragments; writes out/v2/counts.json and out/v2/closest.csv."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v2 as V  # noqa: E402

SRC = {"s1": "stage 1 (incl. 81 Level 2 variants)", "r1": "new-idea round 1", "ev": "event straddles", "en": "stage 4 event entries", "2a": "stage 2a day-filter sides"}


def money(v):
    return "n/a" if v is None else (f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}")


def main():
    B = json.loads((V.OUT / "build_units.json").read_text())
    P = json.loads((V.OUT / "pick_units.json").read_text())
    F = json.loads((V.OUT / "final.json").read_text())
    counts = {}
    print("| store | units | (1) | (1)+(3) | (1)+(2)+(3) = 2024 opened | (4) | (4)+(5) | (4)+(5)+(6) | all six, saved |")
    print("|---|---|---|---|---|---|---|---|---|")
    tot = [0] * 8
    for s, nm in SRC.items():
        R = [r for r in B if r["src"] == s]
        ids = [r["uid"] for r in R if r["build_pass"]]
        row = [len(R), sum(r["t1"] for r in R), sum(r["t1"] and r["t3"] for r in R), len(ids), sum(P[i]["t4"] for i in ids),
               sum(P[i]["t4"] and P[i]["t5"] for i in ids), sum(bool(P[i]["t4"] and P[i]["t5"] and P[i].get("t6")) for i in ids),
               sum(F[i]["admit"] for i in ids)]
        counts[s] = row
        tot = [a + b for a, b in zip(tot, row)]
        print(f"| {nm} | " + " | ".join(str(x) for x in row) + " |")
    print("| **all** | " + " | ".join(f"**{x}**" for x in tot) + " |")
    counts["all"] = tot
    counts["t2_alone"] = {"drawn": sum(r["t2"] is not None for r in B), "pass": sum(bool(r["t2"]) for r in B)}
    counts["only5"] = sum(1 for o in P.values() if o["t5"] and not o["t4"])
    counts["by_root_build_pass"] = {r_: sum(1 for r in B if r["build_pass"] and r["root"] == r_) for r_ in ("NQ", "ES", "GC")}
    counts["by_root_units"] = {r_: sum(1 for r in B if r["root"] == r_) for r_ in ("NQ", "ES", "GC")}
    (V.OUT / "counts.json").write_text(json.dumps(counts, indent=1))
    print("\ncounts", json.dumps({k: v for k, v in counts.items() if k not in SRC}))
    # closest misses
    close = []
    for r in B:
        det = json.loads(r["detail"]) if r.get("detail") else {}
        if r["build_pass"]:
            o, f = P[r["uid"]], F[r["uid"]]
            if f["admit"]:
                continue
            fails = [k for k, ok in (("4", o["t4"]), ("5", o["t5"]), ("6", o.get("t6", True) if (o["t4"] and o["t5"]) else True)) if not ok]
            lifts = {c: v.get("lift", v.get("lift_per_trade")) for c, v in o["controls"].items()}
            close.append({"uid": r["uid"], "stage": "2024", "failed": "+".join(fails) or ",".join(f["failed"]), "n_failed": len(fails) or 1,
                          "build": f"{100 * r['share_pos']:.0f} % of {r['cells']}, avg {money(r['avg_net'])}",
                          "detail": f"2024: {100 * o['share_pos']:.0f} % positive, avg {money(o['avg_net'])}, median {money(o['median_net'])}, lift {lifts}"
                                    + (f", stress avg {money(o.get('stress_avg_net'))}" if o.get("stress_avg_net") is not None else "")})
        elif r["t2"] is not None:
            fails = [k for k, ok in (("1", r["t1"]), ("2", bool(r["t2"])), ("3", r["t3"])) if not ok]
            if len(fails) == 1:
                ps = {c: (v.get("p_beat"), v.get("lift", v.get("lift_per_trade"))) for c, v in det.items()}
                close.append({"uid": r["uid"], "stage": "BUILD", "failed": fails[0], "n_failed": 1,
                              "build": f"{100 * r['share_pos']:.0f} % of {r['cells']}, avg {money(r['avg_net'])}",
                              "detail": f"controls (share beaten, lift) {ps}; trades {r['avg_trades']:.0f} (reach {r.get('reach_trades')})"})
    with (V.OUT / "closest.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, ["uid", "stage", "failed", "n_failed", "build", "detail"])
        w.writeheader()
        w.writerows(close)
    print("\n2024-stage misses with ONE failed test:")
    for c in close:
        if c["stage"] == "2024" and c["n_failed"] == 1:
            print(" ", c["uid"], "| failed", c["failed"], "|", c["build"], "|", c["detail"])
    print("\nBUILD misses with one failed test:", sum(1 for c in close if c["stage"] == "BUILD"), {k: sum(1 for c in close if c["stage"] == "BUILD" and c["failed"] == k) for k in "123"})
    # the 20 closest stage-1 near-misses (out/near_misses.md section B order)
    nm = [r for r in csv.DictReader((V.W / "out" / "admit" / "near_misses.csv").open()) if r["fail"] == "bar"][:20]
    bu = {r["uid"]: r for r in B}
    print("\nthe 20 (first 20 of near_misses.md section B):")
    for r in nm:
        b = bu[r["uid"]]
        if b["build_pass"]:
            o, f = P[r["uid"]], F[r["uid"]]
            res = "MEMBER" if f["admit"] else "passes BUILD; 2024 fails " + ",".join(k for k, ok in (("4", o["t4"]), ("5", o["t5"]), ("6", o.get("t6", True))) if not ok)
        else:
            det = json.loads(b["detail"]) if b.get("detail") else {}
            res = "fails BUILD " + b["fail"] + " " + str({c: v.get("p_beat") for c, v in det.items()}) + f" reach {b.get('reach_trades')}"
        print(" ", r["uid"], "->", res)
    if (V.OUT / "members.json").exists():
        M = json.loads((V.OUT / "members.json").read_text())
        print("\n| idea | market | session | bar | variants (saved) | avg trades | 2021* | 2022 | 2023 | 2024 | win | PF | max DD | <= 5 s | flags |")
        print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for m in M["members"]:
            a = {r["period"]: r for r in m["avg_rows"]}
            c = a["combined"]
            fl = []
            for f in m["flags"]:
                fl.append("WEAK" if f.startswith("WEAK") else "PENALTY 2025-26" if f.startswith("2025-26 penalty") else "EXAM = 2nd look" if f.startswith("2025-26 was")
                          else "2ND LOOK 2024" if f.startswith("SECOND LOOK") else "THIN CONTROL" if f.startswith("thin") else "FAST > 50 %" if f.startswith("FAST")
                          else "exactly 60 %" if f.startswith("exactly") else "tilted control" if f.startswith("one-direction") else f[:20])
            print(f"| {m['idea']} `{m['name']}` | {m['root']} | {m['sess']} | {m['tf']} | {m['variants_judged']} ({m['survivors']}) | {c['trades']:.0f} | "
                  f"{money(a['2021']['net'])} | {money(a['2022']['net'])} | {money(a['2023']['net'])} | {money(a['2024']['net'])} | {100 * c['win']:.0f} % | "
                  f"{c['pf']:.2f} | {money(c['max_dd'])} | {100 * (m['fast_avg']['all']['fast_profit_share'] or 0):.0f} % | {', '.join(fl)} |")
        print("\ngroups", json.dumps(M["groups"]))
        print("moved", M["moved_v1_only"])
        for p in M["pairs"]:
            if p["linked"] or p["same_side"] >= 0.6:
                print("  pair", p)
    if (V.OUT / "placebo_counts.json").exists():
        print("\nplacebo", (V.OUT / "placebo_counts.json").read_text())


if __name__ == "__main__":
    main()
