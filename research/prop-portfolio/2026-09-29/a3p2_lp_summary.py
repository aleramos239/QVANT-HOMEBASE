#!/usr/bin/python3
"""Builds out/shortlist_all.csv (top 40 per firm x 4 firms, ranked by eod P5) and out/a3p2_lucidpro_summary.md (<= 60 lines)
from a3p2_rules.csv + a3p2_lucidpro.csv + a3p2_null.csv + a3p2_fast.csv."""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a3_rules as A1  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
ALL4 = ("lucid", "lucidpro", "lucidpro_nodll", "apex")
LP = ("lucidpro", "lucidpro_nodll")
MODELS = ("eod", "intraday")
NAME = {"lucid": "Lucid Flex", "lucidpro": "LucidPro+DLL", "lucidpro_nodll": "LucidPro noDLL", "apex": "Apex (UNCONFIRMED)"}
TOPN = 40


def rd(n):
    return list(csv.DictReader((OUT / n).open()))


def f(x, k, d=float("nan")):
    v = x.get(k, "")
    return float(v) if v not in ("", None) else d


def rules_str(r, tag="st"):
    g = lambda k: (str(int(f(r, f"{tag}_{k}"))) if f(r, f"{tag}_{k}") else "-")
    return f"m{g('micros')} L{g('day_lock')} K{g('day_take')} S{g('day_stop')} T{g('max_day_tr')} {'TT' if f(r, f'{tag}_target_take') else 'tt-'}"


def main():
    real = rd("a3p2_rules.csv") + rd("a3p2_lucidpro.csv")
    null = rd("a3p2_null.csv")
    fast = {(r["key"], r["sess"], r["firm"], r["cellset"]): r for r in rd("a3p2_fast.csv")}
    fees = json.loads((OUT.parent / "fees.json").read_text())
    fee_of = {"lucid": "lucid-flex-50k@2026-09-27", "lucidpro": "lucid-pro-50k@2026-09-27b", "lucidpro_nodll": "lucid-pro-50k-no-dll@2026-09-27b",
              "apex": "apex-legacy-50k@2026-09-27b"}
    thr = {}
    for fm in ALL4:
        for md in MODELS:
            nl = np.array([f(r, "st_lift") for r in null if r["firm"] == fm and r["model"] == md])
            thr[(fm, md)] = float(np.percentile(nl, 95))
    base = defaultdict(list)
    for r in null:
        if r["model"] == "eod":
            base[(r["firm"], r["pool_id"], r["sess"])].append(f(r, "st_p5"))
    by = {(r["firm"], r["key"], r["sess"], r["model"]): r for r in real}
    sl = []
    for fm in ALL4:
        c = [r for r in real if r["firm"] == fm and r["model"] == "eod" and int(r["trades"]) >= 300 and f(r, "net_1nq") > 0]
        c.sort(key=lambda r: (-f(r, "st_p5"), -f(r, "st_lift")))
        for i, r in enumerate(c[:TOPN], 1):
            k, s = r["key"], r["sess"]
            e, io = fast[(k, s, fm, "eod_stable")], fast[(k, s, fm, "intra_opt")]
            ir = by[(fm, k, s, "intraday")]
            b = base.get((fm, r["pool_id"], s))
            row = {"firm": fm, "unconfirmed": int(fm == "apex"), "rank_eod_p5": i, "strategy_id": f"{r['fam']}|{k}|{s}", "fam": r["fam"], "tf": r["tf"], "sess": s,
                   "src": r["src"], "params": r["params"], "trades": int(r["trades"]), "net_1nq": f(r, "net_1nq"), "rules_eod": rules_str(r)}
            for a in ("micros", "day_lock", "day_take", "day_stop", "max_day_tr", "target_take"):
                row[a] = int(f(r, f"st_{a}"))
            row.update({"eod_p1": f(e, "eod_p1"), "eod_p2": f(e, "eod_p2"), "eod_p3": f(e, "eod_p3"), "eod_p5": f(e, "eod_p5"), "eod_ci_lo": f(r, "st_ci_lo"), "eod_ci_hi": f(r, "st_ci_hi"),
                        "eod_bust5": f(e, "eod_bust5"), "eod_med_days": f(e, "eod_med_days"), "eod_cost_per_funded": f(e, "eod_cost_per_funded"),
                        "lift_eod": f(r, "st_lift"), "ctrl_p5_eod": f(r, "st_ctrl_p5"), "thr_eod": thr[(fm, "eod")], "above_null_thr": int(f(r, "st_lift") > thr[(fm, "eod")]),
                        "null_base_p5_eod": float(np.mean(b)) if b else float("nan"),
                        "intra_same_p1": f(e, "intraday_p1"), "intra_same_p2": f(e, "intraday_p2"), "intra_same_p3": f(e, "intraday_p3"), "intra_same_p5": f(e, "intraday_p5"),
                        "intra_same_bust5": f(e, "intraday_bust5"), "intra_same_lift": f(r, "xi_lift"), "intra_same_cost_per_funded": f(e, "intraday_cost_per_funded"),
                        "intra_opt_rules": rules_str(ir), "intra_opt_p1": f(io, "intraday_p1"), "intra_opt_p2": f(io, "intraday_p2"), "intra_opt_p3": f(io, "intraday_p3"),
                        "intra_opt_p5": f(io, "intraday_p5"), "intra_opt_bust5": f(io, "intraday_bust5"), "intra_opt_med_days": f(io, "intraday_med_days"),
                        "intra_opt_lift": f(ir, "st_lift"), "intra_opt_above_thr": int(f(ir, "st_lift") > thr[(fm, "intraday")]),
                        "intra_opt_cost_per_funded": f(io, "intraday_cost_per_funded"), "intra_opt_eod_p5": f(io, "eod_p5"),
                        "p5_2022": f(r, "p5_2022"), "p5_2023": f(r, "p5_2023"), "p5_2024": f(r, "p5_2024"), "cost_pass_mix": r["cost_pass_mix"], "med_stop_pts": f(r, "med_stop_pts"),
                        "pool_flag": r["pool_flag"], "forced": r.get("forced", "")})
            sl.append(row)
    A1.write(OUT / "shortlist_all.csv", sl)

    # ------------------------------------------------------------ summary
    L = []
    lp = [r for r in real if r["firm"] in LP and r["model"] == "eod"]
    ncfg = len({(r["key"], r["sess"]) for r in lp})
    ncell = {fm: sum(int(r["cells"]) for r in lp if r["firm"] == fm) for fm in LP}
    nnull = len({(r["key"], r["sess"]) for r in null if r["firm"] == "lucidpro"})
    L.append("# A3 pass 2 for LucidPro 50K (+DLL $1,200 soft / no DLL) and fast-pass metrics for all four firms (in-sample 2021-09-22..2024-12-31; holdout untouched; Apex UNCONFIRMED)")
    L.append(f"Same {ncfg} configs / stable-cell / day-matched-control (K=10) / per-profile null method as pass 2. Grid m{{10,20,30,40}} x L{{-,1000,2000}} x K{{-,1500,2000,3000}} x S{{-,1000,2000}} x T{{1,-}} x TT{{off,on}} = 576 cells/firm; "
             f"multiple-testing count {sum(ncell.values()):,} config-rule cells ({ncell['lucidpro']:,} DLL + {ncell['lucidpro_nodll']:,} noDLL), each raced eod + intraday; null {nnull} pseudo-configs. Rule-file DLL applies automatically (day_stop 0/2000 == $1,200 on +DLL).")
    L.append("Rankings: eod P5 = P(pass <= 5 sessions), rolling starts, at the eod-stable cell (eod breach = Homebase). intra = intraday-breach sensitivity. Lift = P5 - day-matched control (warning label, not a filter); flag = lift > null p95.")
    L.append("## Null (zero-edge pseudo-configs: random seed runs thinned to each stratum's trade count; optimised over the same grid)")
    L.append("firm model | null n mean-lift p95(THR) max | real n, lift>THR (null expects ~5%), max real lift | null stable P5 mean p95 max")
    for fm in ALL4:
        for md in MODELS:
            nl = np.array([f(r, "st_lift") for r in null if r["firm"] == fm and r["model"] == md])
            n5 = np.array([f(r, "st_p5") for r in null if r["firm"] == fm and r["model"] == md])
            rl = np.array([f(r, "st_lift") for r in real if r["firm"] == fm and r["model"] == md])
            t = thr[(fm, md)]
            L.append(f"{fm:14s} {md:8s} | {len(nl)} {nl.mean():+.3f} {t:+.3f} {nl.max():+.3f} | {len(rl)}, {int((rl > t).sum())} ({(rl > t).mean() * 100:.0f}%), {rl.max():+.3f} | {n5.mean():.3f} {np.percentile(n5, 95):.3f} {n5.max():.3f}")
    L.append("## Effect of the take rules (day_take/target_take) on LucidPro: mean stable P5 no-take sub-grid -> full grid (real | null)")
    for fm in LP:
        for md in MODELS:
            rr = [r for r in real if r["firm"] == fm and r["model"] == md]
            nn = [r for r in null if r["firm"] == fm and r["model"] == md]
            m = lambda rows, k: np.mean([f(r, k) for r in rows])
            L.append(f"{fm:14s} {md:8s} | real {m(rr, 'notake_st_p5'):.3f} -> {m(rr, 'st_p5'):.3f} | null {m(nn, 'notake_st_p5'):.3f} -> {m(nn, 'st_p5'):.3f}")
    for fm in LP:
        rr = [r for r in real if r["firm"] == fm and r["model"] == "eod"]
        L.append(f"{fm} eod chosen cells: day_take {np.mean([f(r, 'st_day_take') > 0 for r in rr]) * 100:.0f}%, target_take {np.mean([f(r, 'st_target_take') > 0 for r in rr]) * 100:.0f}%, day_lock {np.mean([f(r, 'st_day_lock') > 0 for r in rr]) * 100:.0f}%, "
                 f"day_stop {np.mean([f(r, 'st_day_stop') > 0 for r in rr]) * 100:.0f}%, max_day_tr=1 {np.mean([f(r, 'st_max_day_tr') == 1 for r in rr]) * 100:.0f}%, micros=40 {np.mean([f(r, 'st_micros') == 40 for r in rr]) * 100:.0f}%")
    L.append("## Best fast-pass numbers per firm (configs with >=300 tr and net>0; each metric's max over configs, at that config's own P5-optimised cell; eod = eod cell/eod breach, intra = intraday-optimal cell/intraday breach)")
    L.append("firm | eod best P1 P3 P5 | intra best P1 P3 P5 | null stable P5 mean/max eod, intra | cheapest cost per funded eod, intra ($)")
    for fm in ALL4:
        ok = {(r["key"], r["sess"]) for r in real if r["firm"] == fm and r["model"] == "eod" and int(r["trades"]) >= 300 and f(r, "net_1nq") > 0}
        e = [x for (k, s, ff, cs), x in fast.items() if ff == fm and cs == "eod_stable" and (k, s) in ok]
        i = [x for (k, s, ff, cs), x in fast.items() if ff == fm and cs == "intra_opt" and (k, s) in ok]
        nm = lambda md, fn: fn([f(r, "st_p5") for r in null if r["firm"] == fm and r["model"] == md])
        L.append(f"{fm:14s} | {max(f(x, 'eod_p1') for x in e):.3f} {max(f(x, 'eod_p3') for x in e):.3f} {max(f(x, 'eod_p5') for x in e):.3f} | {max(f(x, 'intraday_p1') for x in i):.3f} {max(f(x, 'intraday_p3') for x in i):.3f} "
                 f"{max(f(x, 'intraday_p5') for x in i):.3f} | {nm('eod', np.mean):.3f}/{nm('eod', max):.3f}, {nm('intraday', np.mean):.3f}/{nm('intraday', max):.3f} | "
                 f"{min(f(x, 'eod_cost_per_funded') for x in e if f(x, 'eod_p5') > 0):.0f}, {min(f(x, 'intraday_cost_per_funded') for x in i if f(x, 'intraday_p5') > 0):.0f}")
    for fm in LP:
        L.append(f"## Top 5 {NAME[fm]} by eod P5 (fee ${fees[fee_of[fm]]['eval_fee']:.0f}; cost per funded = fee/P5 under the 5-day policy) | flag ! = lift <= null p95")
        L.append("id | rules | eod P1/P2/P3/P5 bust5 | lift | intra P5 same rules | intra-opt P5 (rules) | $/funded eod, intra")
        for x in [s for s in sl if s["firm"] == fm][:5]:
            L.append(f"{x['strategy_id']} | {x['rules_eod']} | {x['eod_p1']:.2f}/{x['eod_p2']:.2f}/{x['eod_p3']:.2f}/{x['eod_p5']:.2f} {x['eod_bust5']:.2f} | {x['lift_eod']:+.3f}{'' if x['above_null_thr'] else '!'} | "
                     f"{x['intra_same_p5']:.2f} | {x['intra_opt_p5']:.2f} ({x['intra_opt_rules']}) | {x['eod_cost_per_funded']:.0f}, {x['intra_same_cost_per_funded']:.0f}")
    L.append("Shortlist counts above null p95 (eod lift) among each firm's top 40 by eod P5: " + ", ".join(f"{fm} {sum(x['above_null_thr'] for x in sl if x['firm'] == fm)}/40" for fm in ALL4))
    L.append("Caveats: single in-sample window, holdout untouched; take rules assume the trade's MFE was reached before its exit; shortlist_all ranks by eod P5 (not lift): the eod breach model lets intraday drawdowns recover, so eod P5 "
             "overstates what an intraday-trailing rule would allow (see intra columns); a large share of high-P5 configs is explained by the zero-edge null (compare null max P5); P5 windows overlap (block-bootstrap CI); "
             "null P1/P3 not computed; LucidPro activation assumed $0; Apex UNCONFIRMED.")
    L.append("Reading P1/P2/P3: cells are chosen for P5, not for speed. A day_take <= the $3,000 target flattens a day just below target (take fill at the MFE touch, less 1 tick/contract), so those cells need >= 2 days (P1 = 0); "
             "Lucid Flex has a 2-day minimum (P1 = 0 always). Fast-pass-optimal cells (max P1/P3) were not searched separately.")
    (OUT / "a3p2_lucidpro_summary.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(len(L), "lines")


if __name__ == "__main__":
    main()
