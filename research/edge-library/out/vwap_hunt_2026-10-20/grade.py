"""VWAP hunt 2026-10-20: the PASS BAR on out-of-sample months (PREREG.md section 5). Reads oos.json, is.json, selection.json.

    grade.py          P1, P2, P4, P5, P6 for every version; the chosen versions that pass them all -> rand_queue.txt (randctl run)
    grade.py --p3     + P3 (randctl line) for those candidates -> grade.json, VERSIONS.md, VERSIONS.csv, the pass list
P3 is computed only where it can still matter (chosen + every other line passed): PREREG.md section 5."""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ORDER = ("P1", "P2", "P3", "P4", "P5", "P6")


def label(r: dict) -> str:
    c = r["cell"]
    return c.replace("pts", "").replace("-r", " x") if c.startswith("pts") else c


def main(argv: list) -> None:
    sel = json.loads((HERE / "selection.json").read_text())
    if not sel["frozen"]:
        raise SystemExit("grade: SELECTION.md is not frozen")
    chosen = {tuple(x) for x in sel["chosen"]}
    oos = {(r["store"], r["cell"], r["group"]): r for r in json.loads((HERE / "oos.json").read_text())}
    iss = {(r["store"], r["cell"], r["group"]): r for r in json.loads((HERE / "is.json").read_text())}
    by_idea = defaultdict(list)
    for r in oos.values():
        if r.get("trades"):
            by_idea[r["idea"]].append(r)
    idea_avg = {i: sum(r["avg"] for r in rs) / len(rs) for i, rs in by_idea.items()}
    idea_pooled = {i: sum(r["net"] for r in rs) / max(1, sum(r["trades"] for r in rs)) for i, rs in by_idea.items()}
    p3 = json.loads((HERE / "p3.json").read_text()) if (HERE / "p3.json").exists() else {}
    rows, cands = [], []
    for k, r in sorted(oos.items(), key=lambda kv: (kv[1]["idea"], kv[0])):
        i = iss.get(k, {})
        g = {"key": k, "idea": r["idea"], "store": k[0], "cell": k[1], "group": k[2], "chosen": k in chosen, "is": i, "oos": r}
        if not r.get("trades"):
            g.update(first="no trade", passed=False)
            rows.append(g)
            continue
        b = {"P1": bool(r["p1"]), "P2": r["net"] > 0 and r["net_tick"] > 0, "P4": r["trades"] >= 200,
             "P5": r.get("fresh_trades", 0) > 0 and r.get("fresh_net", 0) > 0, "P6": idea_avg[r["idea"]] > 0}
        key = "|".join(k)
        b["P3"] = p3[key]["pass"] if key in p3 else None
        g["bars"] = b
        others = all(b[x] for x in ("P1", "P2", "P4", "P5", "P6"))
        if g["chosen"] and others and key not in p3:
            cands.append(k)
        g["first"] = next((x for x in ORDER if b[x] is False), None if b["P3"] is not None else ("P3 not run" if not others or not g["chosen"] else "P3 pending"))
        g["passed"] = g["chosen"] and all(b[x] is True for x in ORDER)
        g["would"] = (not g["chosen"]) and others
        rows.append(g)
    (HERE / "rand_queue.txt").write_text("".join(f"rand {s}\n" for s in sorted({k[0] for k in cands})))
    (HERE / "rand_cands.json").write_text(json.dumps([list(k) for k in cands], indent=1))
    (HERE / "grade.json").write_text(json.dumps({"idea_avg_oos": idea_avg, "idea_pooled_oos": idea_pooled, "rows": [{**g, "key": list(g["key"])} for g in rows]},
                                                indent=1, default=str))
    # every version, one line each
    cols = ["idea", "store", "bars", "cell", "group", "chosen", "is_per_day", "is_avg", "is_win", "is_need", "oos_trades", "oos_per_day", "oos_avg",
            "oos_win", "oos_need", "oos_net", "oos_net_tick", "fresh_net", "fresh_trades", "P1", "P2", "P3", "P4", "P5", "P6", "passed", "first", "would"]
    with open(HERE / "VERSIONS.csv", "w", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        for g in rows:
            i, o, b = g["is"], g["oos"], g.get("bars", {})
            w.writerow({"idea": g["idea"], "store": g["store"], "bars": o.get("bars"), "cell": g["cell"], "group": g["group"], "chosen": g["chosen"],
                        "is_per_day": i.get("per_day"), "is_avg": i.get("avg"), "is_win": i.get("win"), "is_need": i.get("need"),
                        "oos_trades": o.get("trades"), "oos_per_day": o.get("per_day"), "oos_avg": o.get("avg"), "oos_win": o.get("win"),
                        "oos_need": o.get("need"), "oos_net": o.get("net"), "oos_net_tick": o.get("net_tick"), "fresh_net": o.get("fresh_net"),
                        "fresh_trades": o.get("fresh_trades"), **{x: b.get(x) for x in ORDER}, "passed": g["passed"], "first": g["first"],
                        "would": g.get("would")})
    n_read = sum(1 for g in rows if g["oos"].get("trades"))
    print(f"versions read (OOS trades > 0): {n_read}; chosen: {len(chosen)}; P3 candidates now: {len(cands)}; passes: {sum(g['passed'] for g in rows)}")
    print("idea average version OOS (avg trade): " + ", ".join(f"{i}: ${v:,.1f}" for i, v in sorted(idea_avg.items())))


if __name__ == "__main__":
    main(sys.argv[1:])
