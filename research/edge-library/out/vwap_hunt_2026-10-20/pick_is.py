"""VWAP hunt 2026-10-20: the SELECTION on in-sample months only (PREREG.md section 4) -> SELECTION.md + is_table.csv.

    pick_is.py          draft (SELECTION.md says DRAFT; the OOS reader refuses)
    pick_is.py --freeze  the same, frozen: the line FROZEN, the time and the sha256 of is.json. After this no OOS number exists yet;
                        `versions.py oos` may run.
Reads is.json only (versions.py is)."""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
NEED_PER_DAY = 0.66
P_NEED = 0.95


def chosen(r: dict, idea_avg: dict) -> tuple:
    """(C1..C6 as booleans, the first failed or None)."""
    if not r.get("trades"):
        return {}, "no trade"
    c = {"C1": bool(r["p1"]),
         "C2": r["net"] > 0 and r["net_tick"] > 0,
         "C3": bool(r["rand"]["pass"]) and (r.get("rand_side") is None or bool(r["rand_side"]["pass"])),
         "C4": (r["per_day"] or 0) >= NEED_PER_DAY,
         "C5": r["late_trades"] > 0 and r["late_net"] > 0,
         "C6": idea_avg[r["idea"]] > 0}
    return c, next((k for k, v in c.items() if not v), None)


def main(argv: list) -> None:
    rows = json.loads((HERE / "is.json").read_text())
    by_idea = defaultdict(list)
    for r in rows:
        if r.get("trades"):
            by_idea[r["idea"]].append(r)
    idea_avg = {i: sum(r["avg"] for r in rs) / len(rs) for i, rs in by_idea.items()}
    idea_net = {i: sum(r["net"] for r in rs) / len(rs) for i, rs in by_idea.items()}
    out, picks = [], []
    for r in rows:
        c, first = chosen(r, idea_avg) if r.get("trades") else ({}, "no trade")
        r = {**r, **c, "chosen": first is None, "first_fail": first}
        out.append(r)
        if first is None:
            picks.append(r)
    picks.sort(key=lambda r: (-(r["win"] - r["need"]), -r["avg"]))
    with open(HERE / "is_table.csv", "w", newline="") as f:
        cols = ["idea", "store", "bars", "family", "dir", "cell", "group", "trades", "per_day", "net", "avg", "win", "need", "net_tick", "late_net",
                "late_trades", "p_rand", "p_rand_side", "C1", "C2", "C3", "C4", "C5", "C6", "chosen", "first_fail"]
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        for r in out:
            w.writerow({**r, "p_rand": (r.get("rand") or {}).get("p_beat"), "p_rand_side": (r.get("rand_side") or {}).get("p_beat")})
    fails = defaultdict(lambda: defaultdict(int))
    for r in out:
        fails[r["idea"]][r["first_fail"] or "chosen"] += 1
    frozen = "--freeze" in argv
    sha = hashlib.sha256((HERE / "is.json").read_bytes()).hexdigest()[:16]
    n_v = sum(1 for r in out if r.get("trades"))
    L = [f"# VWAP hunt 2026-10-20: SELECTION (in-sample months only) -- {'FROZEN' if frozen else 'DRAFT, not frozen'}", "",
         f"Rule: PREREG.md section 4. Source: is.json (sha256 {sha}), {len({r['store'] for r in out})} stores, {n_v} versions with in-sample "
         f"trades ({len(out) - n_v} with none). Full table: is_table.csv. No out-of-sample number had been computed when this was written.", "",
         "## Each idea on in-sample months", "",
         "| Idea | Versions | Avg version: avg trade | Avg version: net | Chosen | First failed line (count) |", "|---|---|---|---|---|---|"]
    for i in sorted(by_idea):
        f = ", ".join(f"{k} {v}" for k, v in sorted(fails[i].items()) if k != "chosen")
        L.append(f"| {i} | {len(by_idea[i])} | ${idea_avg[i]:,.1f} | ${idea_net[i]:,.0f} | {fails[i].get('chosen', 0)} | {f} |")
    L += ["", f"## The chosen versions ({len(picks)}), ranked by win minus need, then average trade", "",
          "| # | Idea | Store | Cell | Group | Trades/day | Avg $ | Win | Need | +1 tick net | Random | 2025-07+ IS net |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, r in enumerate(picks, 1):
        rs = f"{r['rand']['p_beat'] * 100:.1f} %" + (f" / side {r['rand_side']['p_beat'] * 100:.1f} %" if r.get("rand_side") else "")
        L.append(f"| {k} | {r['idea']} | {r['store']} | {r['cell']} | {r['group']} | {r['per_day']:.2f} | {r['avg']:,.1f} | {r['win'] * 100:.1f} % | "
                 f"{r['need'] * 100:.1f} % | ${r['net_tick']:,.0f} | {rs} | ${r['late_net']:,.0f} ({r['late_trades']}) |")
    if frozen:
        L += ["", f"FROZEN {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} (is.json sha256 {sha}). Only the versions above can pass; "
              "every other version's out-of-sample record is read for the idea averages and the luck count only."]
    (HERE / "SELECTION.md").write_text("\n".join(L) + "\n")
    (HERE / "selection.json").write_text(json.dumps({"frozen": frozen, "sha": sha, "chosen": [[r["store"], r["cell"], r["group"]] for r in picks],
                                                     "idea_avg_is": idea_avg}, indent=1))
    print("\n".join(L[:12 + len(by_idea)]))
    print(f"chosen: {len(picks)}")


if __name__ == "__main__":
    main(sys.argv[1:])
