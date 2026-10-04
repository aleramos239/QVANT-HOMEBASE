#!/usr/bin/python3
"""Builds out/a3p2_summary.md (<= 80 lines) and out/shortlist.csv from out/a3p2_rules.csv + a3p2_null.csv (+ pass-1 files for the comparison)."""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a3_rules as A1  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
FIRMS, MODELS = ("lucid", "apex"), ("eod", "intraday")
SUF = ""


def rd(n):
    return list(csv.DictReader((OUT / n).open()))


def f(x, k, d=float("nan")):
    v = x.get(k, "")
    return float(v) if v not in ("", None) else d


def rules_str(r, tag="st"):
    g = lambda k: (str(int(f(r, f"{tag}_{k}"))) if f(r, f"{tag}_{k}") else "-")
    return f"m{g('micros')} L{g('day_lock')} K{g('day_take')} S{g('day_stop')} T{g('max_day_tr')} {'TT' if f(r, f'{tag}_target_take') else 'tt-'}"


def main(suffix=SUF):
    real, null = rd(f"a3p2_rules{suffix}.csv"), rd(f"a3p2_null{suffix}.csv")
    p1r, p1n = rd("a3_rules_screen.csv"), rd("a3_null.csv")
    L = []
    cfgs = {(r["key"], r["sess"]) for r in real}
    ncell = {fm: sum(int(r["cells"]) for r in real if r["firm"] == fm and r["model"] == "eod") for fm in FIRMS}
    nnull = len({(r["key"], r["sess"]) for r in null})
    nfam = Counter(r["fam"] for r in {(r["key"], r["sess"]): r for r in real}.values())
    L.append("# A3 pass 2: heat-map cells x session + screen configs, with day_take / target_take (in-sample 2021-09-22..2024-12-31; APEX = UNCONFIRMED)")
    L.append(f"Multiple-testing count: {len(cfgs)} configs ({sum(1 for k in cfgs if k[0].startswith('hm-'))} heat-map cell x session, {sum(1 for k in cfgs if k[0].startswith('screen-'))} screen) x rule cells: "
             f"lucid {ncell['lucid']:,} + apex {ncell['apex']:,} = {sum(ncell.values()):,} config-rule cells, each raced eod + intraday ({2 * sum(ncell.values()):,} evals); "
             f"null {nnull} pseudo-configs ({sum(int(r['cells']) for r in null if r['model'] == 'eod'):,} cells). Lift = P5 - mean of K=10 day-matched controls at identical rules.")
    L.append("Grids: Lucid m{10,20,30,40} x L{-,750,1000,1500} x K(day_take){-,1000,1250,1500} x S{-,1000,2000} x T{1,-} x TT(target_take){off,on}; Apex m{20..100} x L{-,1000,2000} x K{-,1500,2000,3000} x S{-,1000,2000,3000} x T{1,-} x TT. target_stop always on (TT supersedes).")
    L.append("Stable cell = max over cells of the median P5 of the cell + its +-1-step neighbours (all 6 axes). eod row = eod-optimal rules (xi = same rules under intraday breach); intraday row = its own optimum.")
    thr = {}
    L.append("## Null (pseudo-configs = random seed runs thinned to the stratum's median trade count, one per exit-profile x session, x2 reps; controls from the other seeds)")
    L.append("firm model | null n mean p95(THR) MAX | real n, lift>0, lift>THR (null expects ~5%), max real lift | null stable P5 mean p95 max")
    for fm in FIRMS:
        for md in MODELS:
            nl = np.array([f(r, "st_lift") for r in null if r["firm"] == fm and r["model"] == md])
            n5 = np.array([f(r, "st_p5") for r in null if r["firm"] == fm and r["model"] == md])
            rl = np.array([f(r, "st_lift") for r in real if r["firm"] == fm and r["model"] == md])
            t = float(np.percentile(nl, 95))
            thr[(fm, md)] = t
            L.append(f"{fm:5s} {md:8s} | {len(nl)} {nl.mean():+.3f} {t:+.3f} {nl.max():+.3f} | {len(rl)}, {int((rl > 0).sum())}, {int((rl > t).sum())} ({(rl > t).mean() * 100:.0f}%), {rl.max():+.3f} | {n5.mean():.3f} {np.percentile(n5, 95):.3f} {n5.max():.3f}")
    # ---- what the take rules bought
    L.append("## Effect of day_take / target_take (pass-1-like sub-grid = no take rules vs full grid), and vs pass 1")
    L.append("firm model | real mean stable P5 no-take -> full | null mean stable P5 no-take -> full | best real P5 (net>0, >=300tr) | pass-1 best (screen) | null max pass-1 -> pass-2 | null mean pass-1 -> pass-2")
    p1b = {}
    for fm in FIRMS:
        for md in MODELS:
            rr = [r for r in real if r["firm"] == fm and r["model"] == md]
            nn = [r for r in null if r["firm"] == fm and r["model"] == md]
            ok = [r for r in rr if f(r, "net_1nq") > 0 and int(r["trades"]) >= 300]
            p1 = [f(r, "st_p5") for r in p1r if r["firm"] == fm and r["model"] == md]
            p1nn = [f(r, "st_p5") for r in p1n if r["firm"] == fm and r["model"] == md]
            m = lambda rows, k: np.mean([f(r, k) for r in rows])
            L.append(f"{fm:5s} {md:8s} | {m(rr, 'notake_st_p5'):.3f} -> {m(rr, 'st_p5'):.3f} | {m(nn, 'notake_st_p5'):.3f} -> {m(nn, 'st_p5'):.3f} | "
                     f"{max(f(r, 'st_p5') for r in ok):.3f} | {max(p1):.3f} | {max(p1nn):.3f} -> {max(f(r, 'st_p5') for r in nn):.3f} | {np.mean(p1nn):.3f} -> {m(nn, 'st_p5'):.3f}")
    for fm in FIRMS:
        rr = [r for r in real if r["firm"] == fm and r["model"] == "eod"]
        L.append(f"{fm} eod chosen cells using: day_take {np.mean([f(r, 'st_day_take') > 0 for r in rr]) * 100:.0f}%, target_take {np.mean([f(r, 'st_target_take') > 0 for r in rr]) * 100:.0f}%, "
                 f"day_lock {np.mean([f(r, 'st_day_lock') > 0 for r in rr]) * 100:.0f}%, day_stop {np.mean([f(r, 'st_day_stop') > 0 for r in rr]) * 100:.0f}%, max_day_tr=1 {np.mean([f(r, 'st_max_day_tr') == 1 for r in rr]) * 100:.0f}%")
    fo = {(r["key"], r["sess"]): r for r in real if r.get("forced") == "1"}
    L.append(f"Pass-1 above-null-threshold screen configs always kept: {len(fo)} ({sum(1 for r in fo.values() if r['net_le0'] == '1')} with net<=0 at 1 NQ, flagged net_le0; excluded from the shortlist by the net>0 filter). Quick-P5 dropping not needed (no config-firm dropped).")
    # ---- shortlist
    base = defaultdict(list)
    for r in null:
        if r["model"] == "eod":
            base[(r["firm"], r["pool_id"], r["sess"])].append(f(r, "st_p5"))
    ibase = defaultdict(list)
    for r in null:
        if r["model"] == "intraday":
            ibase[(r["firm"], r["pool_id"], r["sess"])].append(f(r, "st_p5"))
    io = {(r["firm"], r["key"], r["sess"]): r for r in real if r["model"] == "intraday"}
    sl = []
    for fm in FIRMS:
        c = [r for r in real if r["firm"] == fm and r["model"] == "eod" and f(r, "st_lift") > thr[(fm, "eod")] and f(r, "xi_lift") > 0
             and int(r["trades"]) >= 300 and f(r, "net_1nq") > 0]
        c.sort(key=lambda r: -f(r, "st_lift"))
        for i, r in enumerate(c[:40], 1):
            b = (fm, r["pool_id"], r["sess"])
            p = json.loads(r["params"])
            sl.append({
                "firm": fm + ("(UNCONFIRMED)" if fm == "apex" else ""), "rank": i, "strategy_id": f"{r['fam']}|{r['key']}|{r['sess']}", "fam": r["fam"], "tf": r["tf"], "sess": r["sess"],
                "src": r["src"], "params": r["params"], "stop_val": p.get("stop_val", 1.5), "tgt_r": p.get("tgt_r", 0.0 if r["fam"] == "tod_drift" else 2.0),
                "micros": int(f(r, "st_micros")), "day_lock": int(f(r, "st_day_lock")), "day_take": int(f(r, "st_day_take")), "day_stop": int(f(r, "st_day_stop")),
                "max_day_tr": int(f(r, "st_max_day_tr")), "target_take": int(f(r, "st_target_take")), "rules": rules_str(r),
                "p5_eod": f(r, "st_p5"), "ci_lo_eod": f(r, "st_ci_lo"), "ci_hi_eod": f(r, "st_ci_hi"), "bust5_eod": f(r, "st_bust5"), "med_days_eod": f(r, "st_med_days"),
                "p5_intra": f(r, "xi_p5"), "ci_lo_intra": f(r, "xi_ci_lo"), "ci_hi_intra": f(r, "xi_ci_hi"), "bust5_intra": f(r, "xi_bust5"),
                "lift_eod": f(r, "st_lift"), "lift_intra": f(r, "xi_lift"), "ctrl_p5_eod": f(r, "st_ctrl_p5"), "thr_eod": thr[(fm, "eod")],
                "baseline_p5_eod": float(np.mean(base[b])) if b in base else float("nan"), "baseline_p5_intra": float(np.mean(ibase[b])) if b in ibase else float("nan"),
                "p5_2022": f(r, "p5_2022"), "p5_2023": f(r, "p5_2023"), "p5_2024": f(r, "p5_2024"),
                "net_2022": f(r, "net_2022"), "net_2023": f(r, "net_2023"), "net_2024": f(r, "net_2024"),
                "p5_news": f(r, "p5_news"), "p5_nonnews": f(r, "p5_nonnews"), "trades": int(r["trades"]), "net_1nq": f(r, "net_1nq"), "exp_1nq": f(r, "exp_1nq"),
                "exp_at_micros": f(r, "exp_at_micros"), "cost_ratio_mix": f(r, "cost_ratio_mix"), "cost_pass_mix": r["cost_pass_mix"], "med_stop_pts": f(r, "med_stop_pts"),
                "intra_opt_rules": rules_str(io[(fm, r["key"], r["sess"])]), "intra_opt_p5": f(io[(fm, r["key"], r["sess"])], "st_p5"),
                "intra_opt_lift": f(io[(fm, r["key"], r["sess"])], "st_lift"), "intra_opt_bust5": f(io[(fm, r["key"], r["sess"])], "st_bust5"),
                "notake_st_p5": f(r, "notake_st_p5"), "pool_flag": r["pool_flag"]})
    A1.write(OUT / "shortlist.csv", sl)
    for fm in FIRMS:
        s = [x for x in sl if x["firm"].startswith(fm)]
        L.append(f"## Shortlist {fm.upper()}{' (UNCONFIRMED)' if fm == 'apex' else ''}: {len(s)} configs (eod lift > THR {thr[(fm, 'eod')]:+.3f}, intraday lift > 0 at the same rules, >=300 tr, net>0); top 10")
        L.append("id | rules | eod P5 [CI] bust5 | intra P5 (lift) | lift eod | base | 22/23/24 P5 | tr")
        for x in s[:10]:
            L.append(f"{x['strategy_id']} | {x['rules']} | {x['p5_eod']:.3f} [{x['ci_lo_eod']:.3f},{x['ci_hi_eod']:.3f}] {x['bust5_eod']:.2f} | {x['p5_intra']:.3f} ({x['lift_intra']:+.3f}) | "
                     f"{x['lift_eod']:+.3f} | {x['baseline_p5_eod']:.3f} | {x['p5_2022']:.2f}/{x['p5_2023']:.2f}/{x['p5_2024']:.2f} | {x['trades']}")
    for fm in FIRMS:
        s = [x for x in sl if x["firm"].startswith(fm)]
        L.append(f"{fm}: shortlist median intraday-model P5 at the eod rules {np.median([x['p5_intra'] for x in s]):.3f} vs eod {np.median([x['p5_eod'] for x in s]):.3f} (eod-optimal rules lean on EOD-only breach); "
                 f"intraday-optimal rules for the same configs: median P5 {np.median([x['intra_opt_p5'] for x in s]):.3f}")
        ri = sorted([r for r in real if r["firm"] == fm and r["model"] == "intraday" and f(r, "st_lift") > thr[(fm, "intraday")] and int(r["trades"]) >= 300 and f(r, "net_1nq") > 0], key=lambda r: -f(r, "st_lift"))
        L.append(f"## Best {fm} INTRADAY-model configs (own optimum, lift > THR_intra {thr[(fm, 'intraday')]:+.3f}, net>0): {len(ri)}; top 5")
        for r in ri[:5]:
            L.append(f"{r['fam']}|{r['key']}|{r['sess']} | {rules_str(r)} | intra P5 {f(r, 'st_p5'):.3f} [{f(r, 'st_ci_lo'):.3f},{f(r, 'st_ci_hi'):.3f}] bust5 {f(r, 'st_bust5'):.2f} lift {f(r, 'st_lift'):+.3f} | {int(r['trades'])} tr")
    L.append("## Shortlist composition (family / tf / session)")
    for fm in FIRMS:
        s = [x for x in sl if x["firm"].startswith(fm)]
        L.append(f"{fm}: fam {dict(Counter(x['fam'] for x in s).most_common(8))} tf {dict(Counter(x['tf'] for x in s))} sess {dict(Counter(x['sess'] for x in s))}")
    L.append("Caveats: single in-sample window, holdout untouched; take rules assume the trade's MFE was reached before its exit (pessimistic vs MAE/day_stop); 1 pseudo-config per stratum x2 reps; P5 windows overlap (block-bootstrap CI); "
             "Apex payout/rules UNCONFIRMED; nearest-profile pools (tod_drift exit_bars != 6) are flagged in pool_flag; cost_pass_mix uses RT cost < 3% of the median stop risk at the config's NQ/micro mix.")
    (OUT / f"a3p2_summary{suffix}.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(len(L), "lines")


if __name__ == "__main__":
    main()
