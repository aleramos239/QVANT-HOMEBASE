#!/usr/bin/env python
"""Does a Monte Carlo step after the heat map help?  Written 2026-10-05 for the blueprint (owner's question).

Owner's proposal: once a table's heat map is approved, run Monte Carlo on it, and it must STILL meet the requirements before the
out-of-sample test. Tested here the same way as the other gates: BUILD stores only (22 Sep 2021 - 2023), gate on one part, outcome on
the other, 1,875 real tables. No later store is opened; no simulation of trades is run.
Monte Carlo = 1,000 reshuffled histories per table: whole days drawn with replacement, the same days for every variant of the table
(so the table keeps its own co-movement). In each reshuffled history the two requirements that can be re-read are re-read:
  heat   more than 60 % of variants profitable and the average variant profitable
  floor  the table's average trade at the cost floor (NQ $70, ES $75, GC $140)
"still meets the requirements in X % of the runs" = the share of reshuffled histories in which BOTH hold.
The gates (50 / 75 / 90 %) were fixed here before any number was printed.
"""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gate_backtest as G   # noqa: E402

J, LB, PER = G.J, G.LB, G.PER
FLOOR = {"NQ": 70.0, "ES": 75.0, "GC": 140.0}
B = 1000


def collect():
    rng = np.random.default_rng(20261005)
    rows = []
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
        row = {"uid": u["uid"], "family": u["family"], "root": u["root"]}
        fl = FLOOR[u["root"]]
        for p in ("early", "late"):
            m = (c >= PER[p][0]) & (c <= PER[p][1])
            x, k = net[:, m], n[:, m]
            D = x.shape[1]
            v, tr = x.sum(1), k.sum()
            row[f"{p}_heat"] = bool(v.mean() > 0 and (v > 0).mean() > 0.60)
            row[f"{p}_avg"] = float(v.mean())
            row[f"{p}_floor"] = bool(tr > 0 and v.sum() / tr >= fl)
            w = rng.multinomial(D, np.full(D, 1.0 / D), size=B).T.astype(float)      # days x runs: how often each day is drawn
            tot, cnt = x @ w, (k @ w).sum(0)                                          # variants x runs, runs
            heat = (tot.mean(0) > 0) & ((tot > 0).mean(0) > 0.60)
            floor = np.divide(tot.sum(0), cnt, out=np.full(B, -np.inf), where=cnt > 0) >= fl
            row[f"{p}_mc_both"] = float((heat & floor).mean())
            row[f"{p}_mc_heat"] = float(heat.mean())
            row[f"{p}_mc_profit"] = float((tot.mean(0) > 0).mean())
        rows.append(row)
    return rows


def gates(g):
    base = lambda r: r[f"{g}_heat"] and r[f"{g}_floor"]            # noqa: E731
    return [("heat map alone (for comparison)", lambda r: r[f"{g}_heat"]),
            ("heat map + cost floor, no Monte Carlo (the current build line)", base),
            ("… and still meets both in 50 % of the reshuffled runs", lambda r: base(r) and r[f"{g}_mc_both"] >= 0.50),
            ("… in 75 % of the runs", lambda r: base(r) and r[f"{g}_mc_both"] >= 0.75),
            ("… in 90 % of the runs", lambda r: base(r) and r[f"{g}_mc_both"] >= 0.90),
            ("heat map + profitable in 95 % of the runs (the course's P(EV<0) under 5 %)", lambda r: r[f"{g}_heat"] and r[f"{g}_mc_profit"] >= 0.95),
            ("heat map stays majority-green in 75 % of the runs (a Monte Carlo heat map)", lambda r: r[f"{g}_heat"] and r[f"{g}_mc_heat"] >= 0.75)]


def report(rows):
    md = ["# A Monte Carlo step after the heat map — tested on the stored tables (BUILD years only)", "",
          f"{len(rows):,} real tables. 1,000 reshuffled histories each (whole days, drawn with replacement, the same days for all variants).", ""]
    for g, o, title in (("early", "late", "Gate on 2021-22, outcome 2023"), ("late", "early", "Reverse: gate on 2023, outcome 2021-22")):
        md += [f"## {title}", "", "| gate | tables (ideas) | profitable after | heat map + cost floor again after |", "|---|---|---|---|"]
        for name, f in gates(g):
            S = [r for r in rows if f(r)]
            if not S:
                md.append(f"| {name} | 0 | – | – |")
                continue
            ideas = len({(r["family"].split("_")[0], r["root"]) for r in S})
            md.append(f"| {name} | {len(S):,} ({ideas}) | {100 * np.mean([r[f'{o}_avg'] > 0 for r in S]):.0f} % | "
                      f"{100 * np.mean([r[f'{o}_heat'] and r[f'{o}_floor'] for r in S]):.0f} % |")
        md.append("")
    (HERE / "mc_gates.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    report(collect())
