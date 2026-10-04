#!/usr/bin/python3
"""Builds out/a3_summary.md (<= 70 lines) from out/a3_rules_screen.csv, a3_null.csv, a3_baseline.csv."""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
OUT = Path(__file__).resolve().parent / "out"
FIRMS = ("lucid", "apex")
MODELS = ("eod", "intraday")


def rd(name):
    return list(csv.DictReader((OUT / name).open()))


def f(x, k):
    return float(x[k])


def cell(x, tag="st"):
    al = "-" if float(x[f"{tag}_after_loss"]) == 1.0 else ".5"
    g = lambda k: (str(int(float(x[f"{tag}_{k}"]))) if float(x[f"{tag}_{k}"]) else "-")
    return f"m{g('micros')} L{g('day_lock')} S{g('day_stop')} T{g('max_day_tr')} A{al}"


def main():
    real, null, base = rd("a3_rules_screen.csv"), rd("a3_null.csv"), rd("a3_baseline.csv")
    L = []
    ncfg = len({(r["fam"], r["tf"], r["sess"]) for r in real})
    nn = len({(r["tf"], r["sess"], r["rep"]) for r in null})
    ncell = sum(int(r["cells"]) for r in real if r["model"] == "eod")
    L.append("# A3 rules search (in-sample 2021-09-22..2024-12-31, offline; APEX = UNCONFIRMED rules)")
    L.append(f"Tested: {ncfg} configs (>=300 trades) x 2 firms = {ncell:,} config-rule cells (lucid 960 + apex 1,440 per config, full grid, no coarse-to-fine), "
             f"each raced under eod + intraday breach ({2 * ncell:,} evals); null {nn} pseudo-configs ({sum(int(r['cells']) for r in null if r['model']=='eod'):,} cells); K=10 day-matched controls per lift.")
    L.append("Stable cell = max of median P5 over the cell + its +-1-step neighbours on every axis; lift = P5 - mean control P5 at identical rules. Cell key: m=micros L=day_lock S=day_stop T=max_day_tr A=after_loss (- = off).")
    thr = {}
    L.append("## Null threshold (95th pct of stable lift over random pseudo-configs; thinned random seeds, controls from other seeds)")
    L.append("firm model | null n mean med p95(THR) max | real n, lift>0, lift>THR (null expects ~5%) | real max lift")
    for fm in FIRMS:
        for md in MODELS:
            nl = np.array([f(r, "st_lift") for r in null if r["firm"] == fm and r["model"] == md])
            rl = np.array([f(r, "st_lift") for r in real if r["firm"] == fm and r["model"] == md])
            t = float(np.percentile(nl, 95))
            thr[(fm, md)] = t
            L.append(f"{fm:5s} {md:8s} | {len(nl)} {nl.mean():+.3f} {np.median(nl):+.3f} {t:+.3f} {nl.max():+.3f} | {len(rl)}, {int((rl > 0).sum())}, {int((rl > t).sum())} | {rl.max():+.3f}")
    L.append("## Optimised zero-edge baseline (best STABLE P5 a random strategy reaches with the same search)")
    L.append("firm model | thinned pseudo-configs (300-2500 tr): mean p95 max | natural-frequency seed runs: mean max (n) [random | tod_drift-profile]")
    for fm in FIRMS:
        for md in MODELS:
            npc = np.array([f(r, "st_p5") for r in null if r["firm"] == fm and r["model"] == md])
            b = {p: np.array([f(r, "st_p5") for r in base if r["firm"] == fm and r["model"] == md and r["fam"] == p]) for p in ("random", "random-tod")}
            s = " | ".join(f"{b[p].mean():.3f} {b[p].max():.3f} ({len(b[p])})" for p in b)
            L.append(f"{fm:5s} {md:8s} | {npc.mean():.3f} {np.percentile(npc, 95):.3f} {npc.max():.3f} | {s}")
    by = {(r["fam"], r["tf"], r["sess"], r["firm"], r["model"]): r for r in real}
    for fm in FIRMS:
        rows = sorted([r for r in real if r["firm"] == fm and r["model"] == "eod"], key=lambda r: -f(r, "st_lift"))[:20]
        L.append(f"## Top 20 {fm.upper()}{' (UNCONFIRMED)' if fm == 'apex' else ''} by eod stable lift (* = above THR {thr[(fm, 'eod')]:+.3f}); intraday alongside")
        L.append("fam/tf/sess n | eod stable cell | P5 [CI] bust5 days | ctrl lift | intra P5 lift (bust5)")
        for r in rows:
            i = by[(r["fam"], r["tf"], r["sess"], fm, "intraday")]
            mark = "*" if f(r, "st_lift") > thr[(fm, "eod")] else " "
            L.append(f"{mark}{r['fam']}/{r['tf']}/{r['sess']} {r['trades']} | {cell(r)} | {f(r,'st_p5'):.3f} [{f(r,'st_ci_lo'):.3f},{f(r,'st_ci_hi'):.3f}] {f(r,'st_bust5'):.2f} {f(r,'st_med_days'):.0f}d | {f(r,'st_lift'):+.3f} | {f(i,'st_p5'):.3f} {f(i,'st_lift'):+.3f} ({f(i,'st_bust5'):.2f})")
    L.append("## Configs above THR by family / tf / session")
    for fm in FIRMS:
        for md in MODELS:
            ab = [r for r in real if r["firm"] == fm and r["model"] == md and f(r, "st_lift") > thr[(fm, md)]]
            parts = []
            for lab in ("fam", "tf", "sess"):
                c = Counter(r[lab] for r in ab)
                parts.append(f"{lab}: " + (", ".join(f"{a}:{b}" for a, b in c.most_common()) or "none"))
            L.append(f"{fm} {md} [total {len(ab)}] " + parts[0])
            L.append(f"  {parts[1]}; {parts[2]}")
    (OUT / "a3_summary.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(len(L), "lines")


if __name__ == "__main__":
    main()
