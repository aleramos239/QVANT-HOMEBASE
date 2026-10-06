#!/usr/bin/env python
"""Which gate on the early part of BUILD predicted the rest of BUILD?  Written 2026-10-05 for the testing blueprint.

Reads the BUILD stores in runs/ only (22 Sep 2021 - 31 Dec 2023). No 2024 / 2025 / 2026 store is opened; no simulation is run.
EARLY = 22 Sep 2021 - 2022 (the gate period, 15 months) · LATE = 2023 (the outcome year). REVERSE = gate on 2023, outcome on EARLY.
Units: the 1,881 units of stages s1 + r1, and the 168 placebo units (random entries with the same exits, judged as strategies).
The features and the gates below were fixed in this file before any number was printed.

Per unit and period, on the judged table (dead and author cells out, identical trade lists once -- library.judged_rows):
  share   share of variants with net > 0            avg / med   net of the average / median variant
  t, sharpe   of the average variant's daily P&L (a session day without a trade = 0), sharpe annualised with 252 days
  lift_t  bar-based units only, APPROXIMATE: daily (net - control mean per trade x trades), the control being random entries with
          the same exit in the same session and period (c1, every seed in runs/; a placebo unit uses the other seed). judge.py's
          own test (2) matches the random trades day by day and draws coupled tables; this one only removes the control's mean.
"""
import csv
import datetime as dt
import sys
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(W), str(W / "engine")]
import judge as J      # noqa: E402
import library as LB   # noqa: E402

OUT = Path(__file__).resolve().parent


def _o(y, m, d):
    return dt.date(y, m, d).toordinal()


PER = {"early": (_o(2021, 9, 22), _o(2022, 12, 31)), "late": (_o(2023, 1, 1), _o(2023, 12, 31)),
       "y21": (_o(2021, 9, 22), _o(2021, 12, 31)), "y22": (_o(2022, 1, 1), _o(2022, 12, 31)),
       "build": (_o(2021, 9, 22), _o(2023, 12, 31))}
_CAL, _CTL = {}, {}


def cal(root):
    if root not in _CAL:
        _CAL[root] = LB._ordinals(J.calendar("build", root))
    return _CAL[root]


def daily(st, u, ids, c):
    """Net and trade count per (variant, session day)."""
    net, n, lost = np.zeros((len(ids), len(c))), np.zeros((len(ids), len(c))), 0
    for i, cid in enumerate(ids):
        x = J.cellx(st, cid, u["sess"], u)
        k = np.minimum(np.searchsorted(c, x["date"]), len(c) - 1)
        ok = c[k] == x["date"]
        lost += int((~ok).sum())
        np.add.at(net[i], k[ok], x["net"][ok])
        np.add.at(n[i], k[ok], 1)
    return net, n, lost


def stats(net, n, m):
    v, tr, d = net[:, m].sum(1), n[:, m].sum(1), net[:, m].mean(0)
    sd = d.std(ddof=1) if len(d) > 1 else 0.0
    z = float(d.mean() / sd) if sd > 0 else 0.0
    return {"share": float((v > 0).mean()), "avg": float(v.mean()), "med": float(np.median(v)), "trades": float(tr.mean()),
            "t": z * float(np.sqrt(len(d))), "sharpe": z * float(np.sqrt(252))}


def ctl_sums(u):
    """{(exit, period, seed): [net, trades]} of the random-entry control in the unit's session."""
    k = (u["root"], u["tf"], u["sess"])
    if k not in _CTL:
        out = {}
        st, _ = J.find(f"c1-{u['root']}-tf{u['tf']}", "build", lambda r: r["dir"] == LB.RUNS)
        for cell in (st["meta"]["cells"] if st is not None else []):
            e = cell["exit"]
            ek, seed = (e["stop_mode"], float(e["stop_val"]), float(e["tgt_r"])), int(cell["variant"]["seed"])
            x = J.cellx(st, cell["id"], u["sess"])
            for p, (a, b) in PER.items():
                mm = (x["date"] >= a) & (x["date"] <= b)
                s = out.setdefault((ek, p, seed), [0.0, 0])
                s[0] += float(x["net"][mm].sum())
                s[1] += int(mm.sum())
        _CTL[k] = out
    return _CTL[k]


def ctl_mu(u, st, ids, p):
    """Control mean net per trade for each variant's exit in period p, or None when an exit has no control."""
    S, mus = ctl_sums(u), []
    for cid in ids:
        e = st["meta"]["cells"][st["_idx"][cid]].get("exit") or {}
        if not {"stop_mode", "stop_val", "tgt_r"} <= set(e):
            return None
        ek = (e["stop_mode"], float(e["stop_val"]), float(e["tgt_r"]))
        tot = [v for (k, pp, seed), v in S.items() if k == ek and pp == p and seed != u["placebo"]]
        nn = sum(v[1] for v in tot)
        if not nn:
            return None
        mus.append(sum(v[0] for v in tot) / nn)
    return np.array(mus)


def lift(net, n, m, mus):
    L = net[:, m] - mus[:, None] * n[:, m]
    d, tr = L.mean(0), n[:, m].sum()
    sd = d.std(ddof=1) if len(d) > 1 else 0.0
    return {"lift": float(L.sum() / len(net)), "lift_pt": float(L.sum() / tr) if tr else 0.0,
            "lift_t": float(d.mean() / sd * np.sqrt(len(d))) if sd > 0 else 0.0}


def collect():
    rows, skipped = [], []
    addrs = [(a, "real") for s in ("s1", "r1") for a in J.catalog(s)] + [(a, "placebo") for a in J.catalog("placebo")]
    for a, kind in addrs:
        try:
            u = J.unit(a)
            st, _ = J.build_store(u)
            ids = [r["id"] for r in LB.judged_rows(J.table(st, u))[0]]
        except J.Refuse as e:
            skipped.append((a, str(e)[:80]))
            continue
        if not ids:
            skipped.append((a, "no judged variant"))
            continue
        c = cal(u["root"])
        net, n, lost = daily(st, u, ids, c)
        row = {"addr": u["addr"], "uid": u["uid"], "kind": kind, "family": u["family"], "root": u["root"], "tf": u["tf"], "sess": u["sess"],
               "timed": int(u["timed"]), "l2": int(u["l2"]), "cells": len(ids), "off_calendar_trades": lost}
        with_ctl = ("c1" in u["controls"]) and not u["filter"]
        for p, (a0, b0) in PER.items():
            m = (c >= a0) & (c <= b0)
            row.update({f"{p}_{k}": v for k, v in stats(net, n, m).items()})
            mus = ctl_mu(u, st, ids, p) if with_ctl else None
            row.update({f"{p}_{k}": v for k, v in (lift(net, n, m, mus) if mus is not None else
                                                    {"lift": None, "lift_pt": None, "lift_t": None}).items()})
        rows.append(row)
    return rows, skipped


# ---------------------------------------------------------------- the gates (fixed before any number was printed)

def heat(r, g, bar):
    return r[f"{g}_avg"] > 0 and r[f"{g}_share"] > bar


def gates(g):
    G = [("every table (no gate)", lambda r: True),
         ("average variant profitable", lambda r: r[f"{g}_avg"] > 0),
         ("heat map: over 60 % of variants profitable", lambda r: heat(r, g, 0.60)),
         ("heat map: over 80 %", lambda r: heat(r, g, 0.80)),
         ("heat map: every variant profitable", lambda r: heat(r, g, 0.999)),
         ("over 60 % + Sharpe of the average variant 1 or more", lambda r: heat(r, g, 0.60) and r[f"{g}_sharpe"] >= 1),
         ("over 60 % + Sharpe 2 or more", lambda r: heat(r, g, 0.60) and r[f"{g}_sharpe"] >= 2),
         ("over 60 % + t 2 or more", lambda r: heat(r, g, 0.60) and r[f"{g}_t"] >= 2),
         ("over 60 % + t 3 or more", lambda r: heat(r, g, 0.60) and r[f"{g}_t"] >= 3),
         ("over 60 % + beats random entries (lift t 2 or more)",
          lambda r: heat(r, g, 0.60) and r[f"{g}_lift_t"] is not None and r[f"{g}_lift_t"] >= 2),
         ("over 60 % + beats random entries (lift t 3 or more)",
          lambda r: heat(r, g, 0.60) and r[f"{g}_lift_t"] is not None and r[f"{g}_lift_t"] >= 3),
         ("over 60 % + half or more of the idea's other tables also pass", lambda r: heat(r, g, 0.60) and r[f"{g}_breadth"] >= 0.5)]
    if g == "early":
        G.insert(5, ("over 60 % + profitable in 2021 and in 2022 separately",
                     lambda r: heat(r, g, 0.60) and r["y21_avg"] > 0 and r["y22_avg"] > 0))
    return G


def breadth(rows, g):
    """Share of the idea's OTHER tables (same family and market, other bar sizes / sessions / modes) that pass the 60 % heat map."""
    by = {}
    for r in rows:
        by.setdefault((r["kind"], r["family"], r["root"]), []).append(r)
    for grp in by.values():
        p = [heat(r, g, 0.60) for r in grp]
        for r, mine in zip(grp, p):
            r[f"{g}_breadth"] = (sum(p) - mine) / (len(grp) - 1) if len(grp) >= 4 else 0.0


def spearman(a, b):
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def outcome(sel, o):
    if not sel:
        return ["0", "–", "–", "–", "–", "–"]
    L = [r for r in sel if r[f"{o}_lift"] is not None]
    return [f"{len(sel):,}", f"{100 * np.mean([r[f'{o}_avg'] > 0 for r in sel]):.0f} %",
            f"{100 * np.mean([heat(r, o, 0.60) for r in sel]):.0f} %",
            f"{np.median([r[f'{o}_sharpe'] for r in sel]):+.2f}", f"${np.mean([r[f'{o}_avg'] for r in sel]):+,.0f}",
            f"{100 * np.mean([r[f'{o}_lift'] > 0 for r in L]):.0f} % of {len(L):,}" if L else "–"]


def report(rows, skipped):
    md = ["# Which gate predicted the next period? — the gates tested on the stored tables (BUILD years only)", "",
          "EARLY = 22 Sep 2021 - 2022 · LATE = 2023. Read: of the tables that pass the gate in the first period, how many made money in the other.",
          f"Tables: {sum(r['kind'] == 'real' for r in rows):,} real, {sum(r['kind'] == 'placebo' for r in rows)} random-entry (placebo). Skipped: {len(skipped)}.", ""]
    for g, o, title in (("early", "late", "Gate on 2021-22, outcome 2023"), ("late", "early", "Reverse: gate on 2023, outcome 2021-22")):
        breadth(rows, g)
        for kind in ("real", "placebo"):
            R = [r for r in rows if r["kind"] == kind]
            md += [f"## {title} — {kind} tables", "",
                   "| gate | tables passing | average variant profitable after | passes the 60 % heat map again | median Sharpe after | mean net after | beats random after |",
                   "|---|---|---|---|---|---|---|"]
            for name, f in gates(g):
                md.append("| " + " | ".join([name] + outcome([r for r in R if f(r)], o)) + " |")
            a, b = np.array([r[f"{g}_sharpe"] for r in R]), np.array([r[f"{o}_sharpe"] for r in R])
            md += ["", f"Rank correlation of the Sharpe in the gate period with the Sharpe after: {spearman(a, b):+.2f} ({len(R):,} tables).", ""]
            if kind == "real":
                q = np.quantile(a, np.linspace(0, 1, 11))
                md += ["| tenth of tables by Sharpe in the gate period | Sharpe range | profitable after | median Sharpe after |", "|---|---|---|---|"]
                for i in range(10):
                    s = [r for r in R if (q[i] <= r[f"{g}_sharpe"] <= q[i + 1] if i == 9 else q[i] <= r[f"{g}_sharpe"] < q[i + 1])]
                    md.append(f"| {i + 1} | {q[i]:+.2f} to {q[i + 1]:+.2f} | {100 * np.mean([r[f'{o}_avg'] > 0 for r in s]):.0f} % | "
                              f"{np.median([r[f'{o}_sharpe'] for r in s]):+.2f} |")
                md.append("")
    (OUT / "gate_backtest.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


def main():
    rows, skipped = collect()
    keys = list(rows[0].keys())
    with (OUT / "gate_units.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    for a, why in skipped[:10]:
        print("skipped", a, why)
    report(rows, skipped)


if __name__ == "__main__":
    main()
