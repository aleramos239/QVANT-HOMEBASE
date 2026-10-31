"""Amendment K's ONE RULE (PREREG_HM40.md): the stack of 8-12 NQ New York rules, from the in-sample months only.

    stack_pick.py      -> STACK.md, stack.json (written; nothing is run, no test month is read)
S1 NQ, bars 5 / 15, NY sessions, group NY . S2 idea average > 0 . S3 > 50 % of the store's NY boxes positive . S4 wide exits only
(ATR x2, own x1 / 1.5 / 2, 60 pts; target 1.5R / 2R) . S5 C1-C9 (J) and worse fills > 0 (else C2) . S6 the lower middle by average
trade . S7 one store per idea x family (larger S3 share; tie 15m) . S8 by S3 share until >= 8 rules and >= 5 a day; <= 12; stop at
10 a day once 8."""
from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

os.environ.setdefault("HOMEBASE_WF_LAST", "2026-05")
import hmread as HR  # noqa: E402

HERE = Path(__file__).resolve().parent
WIDE = {("atr", 2.0), ("own", 1.0), ("own", 1.5), ("own", 2.0), ("pts", 60.0)}
TARGETS = {1.5, 2.0}


def wide(r) -> bool:
    s = r["settings"]
    return (s["stop_mode"], float(s["stop_val"])) in WIDE and float(s["tgt_r"]) in TARGETS


def main() -> None:
    specs = [json.loads(p.read_text()) for p in sorted((HERE / "specs").glob("*.json"))]
    rows, fam = [], {}
    for sp in specs:
        got = HR.read_store(sp)
        for r in got:
            r["family"] = sp["family"]
        rows += got
        fam[sp["name"]] = sp
    by_idea = defaultdict(list)
    for r in rows:
        if r.get("trades"):
            by_idea[r["idea"]].append(r["avg"])
    idea_avg = {i: float(np.mean(v)) for i, v in by_idea.items()}
    for r in rows:
        r["chosen"], r["first_fail"] = HR.chosen(r, idea_avg)
    stores = defaultdict(list)
    for r in rows:
        sp = fam[r["spec"]]
        if (r["market"] == "NQ" and str(r["tf"]) in ("5", "15") and r["group"] == "NY" and r.get("trades")      # S1
                and idea_avg[r["idea"]] > 0):                                                                    # S2
            stores[r["store"]].append(r)
    cand = []
    for st, rs in stores.items():
        share = sum(r["avg"] > 0 for r in rs) / len(rs)
        if share <= 0.5:                                                                                         # S3
            continue
        ok = [r for r in rs if wide(r) and r["chosen"]
              and ((r["worse_net"] > 0) if r.get("worse_net") is not None else r["net_tick"] > 0)]               # S4 + S5
        if not ok:
            continue
        ok.sort(key=lambda r: (r["avg"], r["box"]))
        p = ok[(len(ok) - 1) // 2]                                                                               # S6
        cand.append({**{k: p[k] for k in ("store", "spec", "idea", "family", "tf", "box", "group", "trades", "per_day", "avg", "win",
                                          "be", "margin", "net", "net_tick", "recent_avg", "blocks_pos", "block_t", "cal_pos",
                                          "rand", "worse_net", "settings")},
                     "share": round(share, 4), "eligible": len(ok), "boxes": len(rs)})
    best = {}
    for c in cand:                                                                                               # S7
        k = (c["idea"], c["family"])
        o = best.get(k)
        if o is None or (c["share"], c["tf"] == "15") > (o["share"], o["tf"] == "15"):
            best[k] = c
    order = sorted(best.values(), key=lambda c: (-c["share"], -c["per_day"]))
    stack, day = [], 0.0
    for c in order:                                                                                              # S8
        if len(stack) >= 12 or (len(stack) >= 8 and day >= 5):     # 8+ rules and 5+ a day: full (so 10 a day with 8+ is too)
            break
        stack.append(c)
        day += c["per_day"]
    L = ["# The stack (Amendment K's one rule; in-sample months only; nothing read from a test month)", "",
         f"{len(cand)} stores passed S1-S6; {len(best)} after S7; the stack takes {len(stack)} (S8), "
         f"{day:.2f} in-sample trades a day in total.", "",
         "| # | Idea | Store | Family | Bars | Box | Trades/day | Avg $ | Win | Break-even | Margin | Recent avg $ | Blocks + | Block t | "
         "Months + | Share of boxes + | Eligible versions |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, c in enumerate(stack, 1):
        L.append(f"| {i} | {c['idea']} | {c['store']} | {c['family']} | {c['tf']}m | {c['box']} | {c['per_day']:.2f} | {c['avg']:,.0f} | "
                 f"{c['win'] * 100:.1f} % | {(c['be'] or 0) * 100:.1f} % | {c['margin']:+.1f} | {c['recent_avg']:,.0f} | {c['blocks_pos']}/14 | "
                 f"{c['block_t']:.2f} | {c['cal_pos']}/9 | {c['share'] * 100:.0f} % | {c['eligible']} |")
    L += ["", "Not taken (passed S1-S7, after the stack filled):", ""]
    L += [f"- {c['store']} {c['box']}: share {c['share'] * 100:.0f} %, {c['per_day']:.2f} a day, avg ${c['avg']:,.0f}" for c in order[len(stack):]]
    (HERE / "STACK.md").write_text("\n".join(L) + "\n")
    (HERE / "stack.json").write_text(json.dumps({"stack": stack, "rest": order[len(stack):], "idea_avg": idea_avg}, indent=1, default=str))
    print("\n".join(L))


if __name__ == "__main__":
    main()
