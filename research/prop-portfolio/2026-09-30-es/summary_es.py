#!/usr/bin/python3
"""Writes out/a3_es_summary.md from out/a3p3s_rules.csv + a3p3s_null.csv (+ NQ a3p2 screen rows for the ES-vs-NQ comparison).
Run: /usr/bin/python3 summary_es.py"""
import csv
import json
from pathlib import Path

import numpy as np

RE = Path(__file__).resolve().parent
OUT = RE / "out"
NQ = RE.parent / "2026-09-29" / "out"
FIRMS = ["lucid", "lucidpro", "lucidpro_nodll", "apex", "apex_eod"]
APEX = ("apex", "apex_eod")


def rd(p):
    return list(csv.DictReader(p.open()))


R, N = rd(OUT / "a3p3s_rules.csv"), rd(OUT / "a3p3s_null.csv")
F = lambda r, k: float(r[k]) if r.get(k, "") not in ("", None) else float("nan")
pv = lambda r, m: F(r, f"{r['primary']}_{m}")          # primary-model metric of a row
cfg = lambda r: f"{r['fam']}/{r['tf']}/{r['sess']}"
comp = lambda r: r["comp_oco"] == "0" and r["comp_target"] == "1"
rules = lambda r: f"{r['micros']}mc lock{r['day_lock']} take{r['day_take']} stop{r['day_stop']} mx{r['max_day_tr']} tt{r['target_take']}"

thr, nullst = {}, {}
for f in FIRMS:
    ns = [r for r in N if r["firm"] == f and r["cellset"] == "p5_" + r["primary"]]
    lifts = [F(r, "lift_prim_p5") for r in ns]
    thr[f] = float(np.nanpercentile(lifts, 95))
    v = [pv(r, "p5") for r in ns]
    nullst[f] = (float(np.mean(v)), float(np.max(v)), len(ns))

L = []
L.append("# ES a3 pass-1 style rules search (screen configs, take rules, 5 firms, primary breach models)")
L.append(f"Configs: {len({(r['key'], r['sess']) for r in R})} family x tf x session with >= 300 trades (80 screen runs, tf 1/5/15/30, sess all split offline), "
         f"{len(R)} rows = config x firm x cellset. Null: {len(N)} rows ({len(N) // 25} pseudo-configs). Machinery = a3p3 (a3p3_screen.py): "
         "rule grid per firm incl. day_take / target_take, stable cell (median of +-1-step neighbours), K=10 day-matched random controls at identical rules, "
         "moving-block CI. PRIMARY model: Lucid* = realized, Apex* = intraday (Apex UNCONFIRMED everywhere). Research window 2021-09-22..2024-12-31, no 2025+.")
L.append("Apex compliance filter applied to apex / apex_eod rankings: comp_oco=0 (no OCO / both-side orders: orb, straddle, lon_break, ib excluded) and "
         "comp_target=1 (has a target so stop <= 5x target: tod_drift time-exit excluded). Non-compliant rows stay in the CSV, flagged. "
         "The 30% MAE rule / threshold-as-stop are not modelled in this screen pass.")
L.append("## Null (optimised zero-edge random, stable P5 at primary model) and lift threshold")
for f in FIRMS:
    L.append(f"- {f} ({[r for r in R if r['firm'] == f][0]['primary']}): null mean {nullst[f][0]:.3f}, max {nullst[f][1]:.3f} (n={nullst[f][2]}); "
             f"lift p95 threshold {thr[f]:+.3f}")
L.append("## Best stable P(pass<=5d) per firm (primary model; P1/P3 at that same cell; lift vs day-matched random at identical rules)")
for f in FIRMS:
    rs = [r for r in R if r["firm"] == f and r["cellset"] == "p5_" + r["primary"] and (f not in APEX or comp(r))]
    rs.sort(key=lambda r: -pv(r, "p5"))
    above = [r for r in rs if F(r, "lift_prim_p5") > thr[f]]
    pos = [r for r in above if F(r, "net_rules") > 0]
    L.append(f"### {f}{' (compliant only)' if f in APEX else ''}: {len(rs)} configs, {len(above)} above null-lift threshold, {len(pos)} of those net>0 under the rules")
    L.append("| config | n | net1 | P5 | P1 | P3 | bust5 | lift | P5 eod/real/intra | rules |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in rs[:6]:
        L.append(f"| {cfg(r)}{'*' if F(r, 'lift_prim_p5') > thr[f] else ''} | {r['trades']} | {F(r, 'net_1nq'):+.0f} | {pv(r, 'p5'):.3f} | {pv(r, 'p1'):.3f} | {pv(r, 'p3'):.3f} | "
                 f"{pv(r, 'bust5'):.3f} | {F(r, 'lift_prim_p5'):+.3f} | {F(r, 'eod_p5'):.2f}/{F(r, 'realized_p5'):.2f}/{F(r, 'intraday_p5'):.2f} | {rules(r)} |")
L.append("(* = lift above that firm's null p95 threshold)")
L.append("## Speed: best P(pass<=1d) and P(pass<=3d) at the speed-optimal stable cell (primary model)")
for f in FIRMS:
    for cs, m in (("speed_p1", "p1"), ("speed_p3", "p3")):
        rs = [r for r in R if r["firm"] == f and r["cellset"] == cs and (f not in APEX or comp(r))]
        rs.sort(key=lambda r: -pv(r, m))
        r = rs[0]
        L.append(f"- {f} {m.upper()}: {pv(r, m):.3f} {cfg(r)} (P5 {pv(r, 'p5'):.3f}, bust5 {pv(r, 'bust5'):.3f}, lift P5 {F(r, 'lift_prim_p5'):+.3f}) {rules(r)}")
L.append("## Expectancy check (funded needs positive expectancy): configs >= 300 trades with net > 0 at 1 ES (before daily rules)")
seen = {}
for r in R:
    if F(r, "net_1nq") > 0:
        seen[(r["fam"], r["tf"], r["sess"])] = r
for k, r in sorted(seen.items(), key=lambda kv: -F(kv[1], "net_1nq")):
    L.append(f"- {k[0]}/{k[1]}/{k[2]}: n={r['trades']} net1 ${F(r, 'net_1nq'):+.0f} exp1 ${F(r, 'exp_1nq'):+.1f}/trade, by year 21/22/23/24: "
             f"{F(r, 'net1_2021'):+.0f}/{F(r, 'net1_2022'):+.0f}/{F(r, 'net1_2023'):+.0f}/{F(r, 'net1_2024'):+.0f}")
L.append("## ES vs NQ (same machinery; NQ = pass-2 screen configs, eod model stable P5, Lucid Flex / Apex user set)")
nqr = [r for r in rd(NQ / "a3p2_rules.csv") if r["key"].startswith("screen-") and r["model"] == "eod"]
nqn = [r for r in rd(NQ / "a3p2_null.csv") if r["model"] == "eod"]
for f, nm in (("lucid", "lucid"), ("apex", "apex")):
    a = [float(r["st_p5"]) for r in nqr if r["firm"] == f]
    b = [F(r, "eod_p5") for r in R if r["firm"] == nm and r["cellset"] == "p5_eod"]
    na = [float(r["st_p5"]) for r in nqn if r["firm"] == f]
    nb = [F(r, "eod_p5") for r in N if r["firm"] == nm and r["cellset"] == "p5_eod"]
    L.append(f"- {f}: stable P5(eod) median/max  NQ {np.median(a):.3f}/{max(a):.3f} (n={len(a)})  vs  ES {np.median(b):.3f}/{max(b):.3f} (n={len(b)}); "
             f"null mean/max NQ {np.mean(na):.3f}/{max(na):.3f}  ES {np.mean(nb):.3f}/{max(nb):.3f}")
(OUT / "a3_es_summary.md").write_text("\n".join(L) + "\n")
print("\n".join(L))
