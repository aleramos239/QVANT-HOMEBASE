#!/usr/bin/env python
"""Dry run: the build checklist of BLUEPRINT.md applied to the 1,875 stored tables.  Written 2026-10-05.

BUILD stores only (22 Sep 2021 - 2023, 27 months). No later store is opened; no simulation of trades is run.
The stored build is 27 months; the blueprint's build will be 45 months (to Jun 2025). So the 200-trade line is shown two ways:
200 on the stored 27 months, and "on pace" = 120 on 27 months (200 x 27 / 45).
Lines, in this order (each one applied on top of the ones before):
  1 heat      more than 60 % of variants profitable and the average variant profitable
  2 floor     average trade (net of all variants / their trades) at NQ $70 · ES $75 · GC $140
  3 trades    average variant: on pace for 200 trades
  4 sides     long and short each make money (all variants together); a table with one side only is judged on that side
  5 neighbors half or more of the idea's other tables (same family and market) have a profitable average variant
  6 random    beats 95 % of random tables: test (2) of the judge as stored in out/v2/build_units.csv
  7 monte     still meets lines 1 and 2 in 75 % of 1,000 reshuffled histories (whole days, with replacement)
"""
import csv
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gate_backtest as G   # noqa: E402

J, LB, PER, W = G.J, G.LB, G.PER, G.W
FLOOR = {"NQ": 70.0, "ES": 75.0, "GC": 140.0}
B = 1000


def collect():
    rng = np.random.default_rng(20261005)
    v2 = {r["uid"]: r for r in csv.DictReader((W / "out" / "v2" / "build_units.csv").open())}
    rows, sides_seen = [], set()
    for a in [a for s in ("s1", "r1") for a in J.catalog(s)]:
        try:
            u = J.unit(a)
            st, _ = J.build_store(u)
            ids = [r["id"] for r in LB.judged_rows(J.table(st, u))[0]]
        except J.Refuse:
            continue
        if not ids:
            continue
        c = G.cal(u["root"])
        net, n, _ = G.daily(st, u, ids, c)
        fl = FLOOR[u["root"]]
        v, tr = net.sum(1), n.sum()
        lng = sht = 0.0
        nl = ns = 0
        for cid in ids:
            x = J.cellx(st, cid, u["sess"], u)
            sides_seen.update(np.unique(x["side"]).tolist())
            up = x["side"] > 0
            lng, sht = lng + float(x["net"][up].sum()), sht + float(x["net"][~up].sum())
            nl, ns = nl + int(up.sum()), ns + int((~up).sum())
        D = net.shape[1]
        w = rng.multinomial(D, np.full(D, 1.0 / D), size=B).T.astype(float)
        with np.errstate(all="ignore"):                       # numpy 2.0 on macOS warns in matmul; checked against einsum
            tot, cnt = net @ w, (n @ w).sum(0)
        heat_b = (tot.mean(0) > 0) & ((tot > 0).mean(0) > 0.60)
        floor_b = np.divide(tot.sum(0), cnt, out=np.full(B, -np.inf), where=cnt > 0) >= fl
        t2 = v2.get(u["uid"], {}).get("t2", "")
        rows.append({"uid": u["uid"], "addr": u["addr"], "family": u["family"], "root": u["root"],
                     "heat": bool(v.mean() > 0 and (v > 0).mean() > 0.60), "avg": float(v.mean()), "share": float((v > 0).mean()),
                     "avgtrade": float(v.sum() / tr) if tr else 0.0, "floor": bool(tr > 0 and v.sum() / tr >= fl),
                     "trades": float(n.sum(1).mean()), "long": lng, "short": sht, "n_long": nl, "n_short": ns,
                     "sides": bool((lng > 0 or nl == 0) and (sht > 0 or ns == 0)),
                     "random": t2 == "True", "random_drawn": t2 in ("True", "False"),
                     "monte": float((heat_b & floor_b).mean())})
    by = {}
    for r in rows:
        by.setdefault((r["family"], r["root"]), []).append(r)
    for grp in by.values():
        ok = [r["avg"] > 0 for r in grp]
        for r, mine in zip(grp, ok):
            r["neighbors"] = (sum(ok) - mine) / (len(grp) - 1) if len(grp) > 1 else 0.0
    return rows, sides_seen


def main():
    rows, sides_seen = collect()
    steps = [("1. Heat map: over 60 % of variants profitable", lambda r: r["heat"]),
             ("2. + average trade at the cost floor", lambda r: r["floor"]),
             ("3. + on pace for 200 trades (120 on the stored 27 months)", lambda r: r["trades"] >= 120),
             ("4. + long and short each make money", lambda r: r["sides"]),
             ("5. + half or more of its neighbor tables profitable", lambda r: r["neighbors"] >= 0.5),
             ("6. + beats 95 % of random tables", lambda r: r["random"]),
             ("7. + Monte Carlo: still meets 1 and 2 in 75 % of reshuffled runs", lambda r: r["monte"] >= 0.75)]
    md = ["# Dry run: the build checklist on the 1,875 stored tables (BUILD = 22 Sep 2021 - 2023)", "",
          f"Side codes found in the stores: {sorted(sides_seen)} (long = above 0).", "",
          "| line (each on top of the ones before) | tables left | ideas left |", "|---|---|---|",
          f"| all stored tables | {len(rows):,} | {len({(r['family'].split('_')[0], r['root']) for r in rows})} |"]
    S = rows
    for name, f in steps:
        S = [r for r in S if f(r)]
        md.append(f"| {name} | {len(S):,} | {len({(r['family'].split('_')[0], r['root']) for r in S})} |")
    md += ["", "Each line on its own (how many of the 1,875 tables pass that one line alone):", "",
           "| line | tables passing it alone |", "|---|---|"]
    for name, f in steps:
        md.append(f"| {name.split('. ', 1)[1].lstrip('+ ')} | {sum(1 for r in rows if f(r)):,} |")
    md.append(f"| 200 trades on the stored 27 months (instead of on pace) | {sum(1 for r in rows if r['trades'] >= 200):,} |")
    md += ["", "Tables that pass every line:", ""]
    for r in S:
        md.append(f"- `{r['addr']}` — average trade ${r['avgtrade']:.0f}, {r['trades']:.0f} trades, {100 * r['share']:.0f} % of variants "
                  f"profitable, long ${r['long'] / max(1, 1):,.0f} / short ${r['short']:,.0f} (all variants), Monte Carlo {100 * r['monte']:.0f} %")
    if not S:
        md.append("- none")
    six = [r for r in rows if all(f(r) for _, f in steps[:6])]
    md += ["", "Tables that pass lines 1-6 (before the Monte Carlo line):", ""]
    for r in six:
        md.append(f"- `{r['addr']}` — average trade ${r['avgtrade']:.0f}, {r['trades']:.0f} trades, Monte Carlo {100 * r['monte']:.0f} %")
    if not six:
        md.append("- none")
    (HERE / "funnel.md").write_text("\n".join(md) + "\n")
    with (HERE / "funnel_units.csv").open("w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    print("\n".join(md))


if __name__ == "__main__":
    main()
