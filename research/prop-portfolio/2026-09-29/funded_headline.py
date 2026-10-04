#!/usr/bin/python3
"""Headline block of the funded search: per variant the top same-config 'eval + funded' picks (E[net $ per eval purchase] = P5 x E$60 - fee - P5 x act), with the
eod / intraday breach bounds, WF OOS, lift and an 'edge-backed' pick (1-contract net > 0, lift > 0, above null p95). Appends nothing; prints md (funded_merge writes the rest).
Run: PYTHONPATH=~/ramos-quant-homebase PP_PILOT=es /usr/bin/python3 funded_headline.py   -> out/funded_headline.md"""
from __future__ import annotations

import csv

import evalcore as E
from funded_merge import EVAL_OF, FEE, LABEL, V

OUT = E.D / "out"


def fl(x, d=None):
    try:
        v = float(x)
        return d if v != v else v
    except (TypeError, ValueError):
        return d


def main():
    fc = [r for r in csv.DictReader((OUT / "funded_candidates.csv").open()) if r["stage"] == "full" and r["status"] == "ok"]
    ev = {(r["key"], r["sess"], r["firm"]): r for r in csv.DictReader((OUT / "candidates.csv").open())}
    L = ["# Funded headline: same-config eval + funded economics (E[net $ per eval purchase] = P5 x E$60 - fee - P5 x act), primary model; bounds = eod / intraday (open-P&L) breach",
         "Columns: eval P5 prim (eod|intraday) | funded P20/P40, median days to 1st payout, E[cheque] | E$40 / E$60 (eod|intraday E$40) | bust before 1st payout | WF OOS E$40 (P40) | lift E$40 vs day-matched random | net/purchase [prim | intraday-bound]"]
    for v in V:
        fee, act = FEE[v]
        rows = []
        for r in fc:
            if r["variant"] != v:
                continue
            if v == "apex" and r["apex_cfg_flags"]:
                continue
            e = ev.get((r["key"], r["sess"], EVAL_OF[v]))
            if not e:
                continue
            p5 = fl(r["eval_p5"], 0.0)
            e60 = fl(r["e_net_60"], 0.0)
            net = p5 * e60 - fee - p5 * act
            ip5 = fl(e.get("intr_p5"), 0.0)
            ie40 = fl(r["alt2_e40"], 0.0) if v != "apex" else fl(r["alt2_e40"], 0.0)
            netb = ip5 * (ie40 * (e60 / fl(r["e_net_40"], 1.0) if fl(r["e_net_40"], 0) else 1.0)) - fee - ip5 * act
            rows.append((net, netb, r, e))
        rows.sort(key=lambda x: -x[0])
        edge = [x for x in rows if fl(x[2]["net_1nq"], 0) > 0 and fl(x[2]["lift_e40"], 0) > 0 and x[2]["above_null_p95"] in ("1", "1.0")]
        L.append(f"## {LABEL[v]} (eval fee ${fee:.0f}, activation ${act:.0f}; rule file via eval firm {EVAL_OF[v]})")

        def line(tag, x):
            net, netb, r, e = x
            return (f"- {tag} {r['fam']}/tf{r['tf']}/{r['sess']} [{r['key']}] eval rules {r['eval_rules']} P5 {fl(r['eval_p5'], 0):.2f} ({fl(e.get('eod_p5'), 0):.2f}|{fl(e.get('intr_p5'), 0):.2f}) | funded {r['e40_stable_cell'].replace(' ', '')} "
                    f"P20/P40 {fl(r['p_pay_20'], 0):.0%}/{fl(r['p_pay_40'], 0):.0%} med {fl(r['med_days_first'], float('nan')):.0f}d chq ${fl(r['e_first_gross'], 0):.0f} | E$40 {fl(r['e_net_40'], 0):.0f} / E$60 {fl(r['e_net_60'], 0):.0f} "
                    f"({fl(r['alt1_e40'], 0):.0f}|{fl(r['alt2_e40'], 0):.0f}) | bust-pre {fl(r['p_bust_pre_first'], 0):.0%} | WF OOS E$40 {fl(r['wf_oos_e_net_40'], float('nan')):.0f} (P40 {fl(r['wf_oos_p_pay_40'], float('nan')):.0%}) "
                    f"| lift {fl(r['lift_e40'], float('nan')):+.0f} | net/purchase {net:+.0f} [{netb:+.0f}] | 1-ct net ${fl(r['net_1nq'], 0):+,.0f}")
        for i, x in enumerate(rows[:3], 1):
            L.append(line(f"{i}.", x))
        if edge:
            L.append(line("edge-backed:", edge[0]))
    (OUT / "funded_headline.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
