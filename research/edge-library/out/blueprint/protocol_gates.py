#!/usr/bin/env python
"""The Institutional Protocol's own in-sample gates, tested on the stored tables.  Written 2026-10-05 for the blueprint.

Same set-up as gate_backtest.py: BUILD stores only (22 Sep 2021 - 2023), no later store opened, no simulation.
Gate on EARLY (22 Sep 2021 - 2022), outcome on LATE (2023), and the reverse. The 1,875 real tables of stages s1 + r1.
Gates fixed here before any number was printed (course synthesis: ~/…/Institutional Protocol/notes/00-PROTOCOL-SYNTHESIS.md):
  floor   the table's average trade (net of all judged variants / their trades) is at least the course's minimum:
          NQ $70 · ES $75 · GC $140 (L08 reference sheet)
  pev     P(EV < 0) under 5 % in-sample, under 10 % out-of-sample. Normal approximation of the bootstrap: P(EV<0) = Phi(-t).
          For one variant t is over its trades; for the table it is the t of the average variant's daily P&L (gate_backtest).
  mcmap   "Monte Carlo heat map": the share of variants whose own P(EV<0) is under 5 %
"""
import csv
import sys
from math import erf, sqrt
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gate_backtest as G   # noqa: E402  (sets the paths, imports judge as G.J and library as G.LB)

J, LB, PER = G.J, G.LB, G.PER
FLOOR = {"NQ": 70.0, "ES": 75.0, "GC": 140.0}
T05, T10 = 1.6449, 1.2816          # Phi(-t) = 5 % and 10 %


def phi(x):
    return 0.5 * (1 + erf(x / sqrt(2)))


def collect():
    base = {r["uid"]: r for r in csv.DictReader((HERE / "gate_units.csv").open()) if r["kind"] == "real"}
    rows = []
    for a in [a for s in ("s1", "r1") for a in J.catalog(s)]:
        try:
            u = J.unit(a)
            st, _ = J.build_store(u)
            ids = [r["id"] for r in LB.judged_rows(J.table(st, u))[0]]
        except J.Refuse:
            continue
        if not ids or u["uid"] not in base:
            continue
        b = base[u["uid"]]
        row = {"uid": u["uid"], "family": u["family"], "root": u["root"]}
        cells = [J.cellx(st, cid, u["sess"], u) for cid in ids]
        for p in ("early", "late"):
            a0, b0 = PER[p]
            green, net, n = 0, 0.0, 0
            for x in cells:
                v = x["net"][(x["date"] >= a0) & (x["date"] <= b0)]
                net, n = net + float(v.sum()), n + len(v)
                if len(v) > 1 and v.std(ddof=1) > 0 and v.mean() / v.std(ddof=1) * sqrt(len(v)) > T05:
                    green += 1
            row.update({f"{p}_mcmap": green / len(ids), f"{p}_avgtrade": net / n if n else 0.0,
                        f"{p}_avg": float(b[f"{p}_avg"]), f"{p}_share": float(b[f"{p}_share"]), f"{p}_t": float(b[f"{p}_t"])})
        rows.append(row)
    return rows


def gates(g):
    heat = lambda r: r[f"{g}_avg"] > 0 and r[f"{g}_share"] > 0.60          # noqa: E731
    floor = lambda r: r[f"{g}_avgtrade"] >= FLOOR[r["root"]]                # noqa: E731
    pev = lambda r: r[f"{g}_t"] > T05                                       # noqa: E731
    return [("plain heat map: over 60 % of variants profitable (for comparison)", heat),
            ("Monte Carlo heat map: over 50 % of variants with P(EV<0) under 5 %", lambda r: r[f"{g}_mcmap"] > 0.50),
            ("Monte Carlo heat map: over 60 %", lambda r: r[f"{g}_mcmap"] > 0.60),
            ("cost floor: average trade at the course's minimum or more", floor),
            ("plain heat map + cost floor", lambda r: heat(r) and floor(r)),
            ("plain heat map + P(EV<0) under 5 %", lambda r: heat(r) and pev(r)),
            ("all three: plain heat map + cost floor + P(EV<0) under 5 %", lambda r: heat(r) and floor(r) and pev(r))]


def report(rows):
    md = ["# The Institutional Protocol's gates on the stored tables (BUILD years only)", "",
          f"{len(rows):,} real tables. Gate in one period, outcome in the other. Floors: NQ $70, ES $75, GC $140 a trade.",
          "\"Course's out-of-sample line\" = profitable, average trade still at the floor, and P(EV<0) under 10 %.", ""]
    for g, o, title in (("early", "late", "Gate on 2021-22, outcome 2023"), ("late", "early", "Reverse: gate on 2023, outcome 2021-22")):
        md += [f"## {title}", "", "| gate | tables (ideas) | profitable after | average trade still at the floor | passes the course's out-of-sample line |",
               "|---|---|---|---|---|"]
        for name, f in gates(g):
            S = [r for r in rows if f(r)]
            if not S:
                md.append(f"| {name} | 0 | – | – | – |")
                continue
            prof = np.mean([r[f"{o}_avg"] > 0 for r in S])
            fl = np.mean([r[f"{o}_avgtrade"] >= FLOOR[r["root"]] for r in S])
            oos = np.mean([r[f"{o}_avg"] > 0 and r[f"{o}_avgtrade"] >= FLOOR[r["root"]] and r[f"{o}_t"] > T10 for r in S])
            ideas = len({(r["family"].split("_")[0], r["root"]) for r in S})
            md.append(f"| {name} | {len(S):,} ({ideas}) | {100 * prof:.0f} % | {100 * fl:.0f} % | {100 * oos:.0f} % |")
        md.append("")
    base = np.mean([r["late_avg"] > 0 and r["late_avgtrade"] >= FLOOR[r["root"]] and r["late_t"] > T10 for r in rows])
    md.append(f"Of all {len(rows):,} tables, {100 * base:.1f} % pass the course's out-of-sample line on 2023 with no gate at all.")
    (HERE / "protocol_gates.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    report(collect())
