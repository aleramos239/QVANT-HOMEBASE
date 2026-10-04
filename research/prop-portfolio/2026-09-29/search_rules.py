#!/usr/bin/python3
"""Rule grid search on member trades (eod race, rolling 5-day starts, in-sample). Run with /usr/bin/python3.

  search_rules.py RUN[:sess[:micros]] [...] --tag T [--firm lucid|apex|both] [--grid '{"micros":[10,20]}']

Grid axes (defaults in evalcore.GRID): micros (applied to every member) x day_lock x day_stop x max_day_tr
x after_loss x target_stop; 0 = off. Writes R/out/search_<tag>.csv, prints the top 10 by P(pass<=5d) (ties: fewest active rules) and the
top 5 by stability (median P of a cell's one-step grid neighbours; a lone spike with a low stab is noise)."""
import argparse
import csv
import json
import time

import evalcore as E
from evaluate import member

COLS = ["firm", "micros", "day_lock", "day_stop", "max_day_tr", "after_loss", "target_stop", "p_pass", "stab",
        "p_bust", "n_rules", "med_days", "executed", "cost_ratio"]


def fmt(r):
    return " ".join(f"{k}={r[k]:.3f}" if isinstance(r[k], float) else f"{k}={r[k]}" for k in
                    ("firm", "micros", "day_lock", "day_stop", "max_day_tr", "after_loss", "target_stop",
                     "p_pass", "stab", "p_bust"))


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("members", nargs="+")
    a.add_argument("--tag", required=True)
    a.add_argument("--firm", default="both")
    a.add_argument("--grid")
    a.add_argument("--news", default="all")
    a = a.parse_args(argv)
    cfg = {"members": [member(m, a.news) for m in a.members]}
    firms = list(E.FIRMS) if a.firm == "both" else [a.firm]
    t = time.perf_counter()
    rows = E.search(cfg, json.loads(a.grid) if a.grid else None, firms=firms)
    p = E.D / "out" / f"search_{a.tag}.csv"
    p.parent.mkdir(exist_ok=True)
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} cells in {time.perf_counter() - t:.1f}s -> {p}")
    for firm in sorted({r["firm"] for r in rows}):
        fr = [r for r in rows if r["firm"] == firm]
        print(f"-- {firm}: top 10 by p_pass (cells with identical outcomes collapse to the fewest-rules one)")
        seen, k = {}, 0
        for r in sorted(fr, key=lambda r: (-round(r["p_pass"], 4), r["n_rules"], r["p_bust"])):
            sig = (round(r["p_pass"], 6), round(r["p_bust"], 6), r["med_days"], r["executed"], round(r["stab"], 6))
            if sig in seen:
                seen[sig][1] += 1
            elif k < 10:
                seen[sig] = [r, 0]
                k += 1
        for r, dup in seen.values():
            print("  " + fmt(r) + (f"  (+{dup} equivalent)" if dup else ""))
        print(f"-- {firm}: top 5 by stab")
        for r in sorted(fr, key=lambda r: (-round(r["stab"], 4), -r["p_pass"], r["n_rules"]))[:5]:
            print("  " + fmt(r))


if __name__ == "__main__":
    main()
