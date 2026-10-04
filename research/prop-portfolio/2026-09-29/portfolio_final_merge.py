#!/usr/bin/python3
"""Merge the per-firm Stage-B outputs into out/portfolio_results.json (full), out/portfolio_summary.md (<= 80 lines) and
out/portfolio_members.md (every parameter of every member + shared rules, per firm). Read-only on the per-firm files.
Run: PYTHONPATH=~/ramos-quant-homebase /usr/bin/python3 portfolio_final_merge.py [--tag _final] [--fast-tag _finalfast]"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import portfolio as P

OUT = P.OUT
FIRMS = P.FIRM_ALL
NAMES = {"lucid": "Lucid Flex", "lucidpro": "LucidPro+DLL", "lucidpro_nodll": "LucidPro noDLL", "apex": "Apex user-set (UNCONFIRMED)",
         "apex_eod": "Apex EOD site-set (UNCONFIRMED)"}


def _rj(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def load_tag(tag: str) -> dict:
    res = {}
    for f in FIRMS:
        s = _rj(OUT / f"portfolio_{f}{tag}.json")
        if not s:
            continue
        fx = _rj(OUT / f"portfolio_wffixed_{f}{tag}.json") or {}
        rs = _rj(OUT / f"portfolio_wfres_{f}{tag}.json") or {}
        for lab in ("single", "best2", "portfolio"):
            if lab in s["reports"] and f"{lab}_fixed" in fx:
                s["reports"][lab]["wf_fixed"] = fx[f"{lab}_fixed"]
        s["wf_reselect"] = rs.get("portfolio_reselect")
        res[f] = s
    return res


def _sq(x, n=3):
    return "-" if x is None else f"{x:.{n}f}"


def line(f: str, lab: str, r: dict, prim: str) -> str:
    h = r["headline"]
    ci = h.get("ci_p5") or [float("nan")] * 2
    lf = (r.get("lift") or {}).get(prim, {})
    lci = lf.get("ci") or [float("nan")] * 2
    wf = r.get("wf_fixed") or {}
    c = r["cell"]
    mem = " + ".join(f"{m['name'].split('|')[0]}|{m['name'].split('|')[1]}@{m['micros']}" for m in r["members"])
    return (f"- {lab}: P1/2/3/5 {h['p1']:.2f}/{h['p2']:.2f}/{h['p3']:.2f}/{h['p5']:.3f} [{ci[0]:.2f},{ci[1]:.2f}] bust5 {h['bust5']:.2f} | "
            f"eod {r['eod']['p5']:.2f} rlz {r['realized']['p5']:.2f} intra {r['intraday']['p5']:.2f} | lift {lf.get('lift', float('nan')):+.3f} "
            f"[{lci[0]:+.2f},{lci[1]:+.2f}] | " + (f"WFfix {_sq(wf.get('oos_p5'), 2)} ({wf.get('lift', float('nan')):+.2f}) | " if wf else "") +
            f"L{c['day_lock']} K{c['day_take']} S{c['day_stop']} T{c['max_day_tr']} TT{c['target_take']} | {mem}")


def summary(res: dict, multi: dict, fast: dict) -> str:
    L = [f"# Stage B portfolio results ({dt.date.today()}; in-sample 2021-09-22..2024-12-31; primary model Lucid*=realized, Apex*=intraday; "
         "Apex sets UNCONFIRMED; fees assumed)",
         "Pool per firm = top-25 by primary P5 + best-2 per WF-surviving family-grid x session + near-misses with lift>0 (<=15) from out/candidates.csv. "
         "Objective = stable P5 (median of a rules cell and its neighbours). Format: P1/2/3/5 [CI P5] bust5 | eod/realized/intraday P5 | lift vs day-matched random [CI] "
         "| WF fixed-set OOS P5 (lift) | rules L=lock K=take S=stop T=max-tr TT=target-take | members id|session@micros."]
    for f, s in res.items():
        prim = s["primary"]
        L.append(f"## {NAMES[f]} ({s['rules_id']}) pool {s['pool_size']}, {s['evals']} evals")
        rp = s["reports"]
        for lab in ("single", "best2", "portfolio"):
            if lab in rp:
                L.append(line(f, lab, rp[lab], prim))
        pf = rp["portfolio"]
        ex = pf.get("extras", {})
        wr = s.get("wf_reselect") or {}
        bd = ex.get("by_day", {}).get(prim, {})
        nw = ex.get("news", {}).get(prim, {})
        rc = {r["scale"]: r for r in ex.get("risk_curve", [])}
        cm = ex.get("member_corr", {})
        w = pf.get("walk", {})
        L.append(f"  WF reselect OOS P5 {_sq(wr.get('oos_p5'), 3)} lift {wr.get('lift', float('nan')):+.3f} [{(wr.get('lift_ci') or [float('nan')]*2)[0]:+.2f},"
                 f"{(wr.get('lift_ci') or [float('nan')]*2)[1]:+.2f}] (upper bound) | news P5 {_sq(nw.get('p5_news'), 2)} vs non-news {_sq(nw.get('p5_nonnews'), 2)} | "
                 f"corr mean {_sq(cm.get('pair_mean'), 2)} max {_sq(cm.get('pair_max'), 2)} | conflicts {w.get('opposite_conflicts_executed')} "
                 f"max conc {w.get('max_concurrent_micros')}/{P.firm(f).cap} cap-viol {w.get('cap_violations')}")
        L.append("  by day pass/bust: " + " ".join(f"d{k+1} {bd['pass_on_day'][k]:.2f}/{bd['bust_on_day'][k]:.2f}" for k in range(5)) if bd else "  by day: n/a")
        L.append("  risk x0.25/.5/.75/1/1.25 (P5 bust5, rules fixed | re-opt): " + "; ".join(
            f"{sc}x {rc[sc]['fixed']['headline']['p5']:.2f} {rc[sc]['fixed']['headline']['bust5']:.2f} | {rc[sc]['reopt']['headline']['p5']:.2f} {rc[sc]['reopt']['headline']['bust5']:.2f}"
            for sc in (0.25, 0.5, 0.75, 1.0, 1.25) if sc in rc))
        exe = pf.get("exec")
        if exe:
            L.append("  executed under the shared rules (entries / net $): " + " ; ".join(
                f"{m['name'].split('|')[0]}|{m['name'].split('|')[1]}@{m['micros']} {m['executed']} / {m['net']:+,.0f}" for m in exe["members"])
                + f" | top member share of positive executed P&L {exe['max_net_share']:.0%}" if exe.get("max_net_share") is not None else "")
        L.append(f"  flags: {'; '.join(pf.get('flags', [])) or 'none'}")
    if multi:
        L.append("## Multi-account (same start day, one eval each; primary model, [eod/intraday]); in-sample greedy mixes")
        for n, m in multi["mixes"].items():
            p = m["primary"]
            L.append(f"- N={n} {m['counts']}: P(>=1 pass<=5d) {p['p_any5']:.3f} [{m['eod']['p_any5']:.2f}/{m['intraday']['p_any5']:.2f}] by-day "
                     f"{[round(x, 2) for x in p['p_any_by_day'][:3]]} E[funded] {p['e_funded']:.2f} cost ${p['total_eval_cost']:.0f} ${(p['cost_per_funded'] or 0):.0f}/funded; "
                     f"same-strategy baseline {m['same_strategy_baseline']['primary']['p_any5']:.3f}")
    if fast:
        L.append("## 'fast' objective (mean of P1,P2,P3,P5) portfolios")
        for f, s in fast.items():
            L.append(line(f, NAMES[f] + " fast-portfolio", s["reports"]["portfolio"], s["primary"]))
    return "\n".join(L)


def members_md(res: dict) -> str:
    L = ["# Exact members and shared rules per firm (Stage B final)", "Every member = tester run of `tester_strategy` with `tester_inputs` (sess=all; "
         "session split offline), trades of the listed session, sized at `micros` MNQ. Shared rules apply to the merged trade stream.", ""]
    for f, s in res.items():
        for lab in ("single", "best2", "portfolio"):
            r = s["reports"].get(lab)
            if not r:
                continue
            L.append(f"## {NAMES[f]} - {lab}  (P5 {r['headline']['p5']:.3f}, model {s['primary']})")
            L.append("rules: " + json.dumps(r["extras"]["rules_spec"]["daily_rules"]["meaning"] and {k: v for k, v in r["extras"]["rules_spec"]["daily_rules"].items() if k != 'meaning'}) +
                     f" | rule file {r['extras']['rules_spec']['rule_file']} | firm {json.dumps(r['extras']['rules_spec']['firm_rules'])}")
            for sp in r["extras"]["specs"]:
                L.append(f"- {sp['strategy_id']}|{sp['sess']}: {sp['tester_strategy']} tf={sp['tf']} micros={sp['micros']} stop_mode={sp['stop_mode']} stop_val={sp['stop_val']} "
                         f"tgt_r={sp['tgt_r']} exit_bars={sp['exit_bars']} trail_atr={sp['trail_atr']} max_tr={sp['max_tr']} family_params={json.dumps(sp['family_params'])} "
                         f"inputs={json.dumps(sp['tester_inputs'])} source={sp['trade_source']}")
            L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="_final")
    ap.add_argument("--fast-tag", default="_finalfast")
    a = ap.parse_args(argv)
    res, fast = load_tag(a.tag), load_tag(a.fast_tag)
    multi = _rj(OUT / f"portfolio_multi{a.tag}.json")
    multi_fast = _rj(OUT / f"portfolio_multi{a.fast_tag}.json")
    full = {"generated": dt.datetime.now().isoformat(timespec="seconds"), "window": "2021-09-22..2024-12-31 (research window; holdout untouched)",
            "notes": ["primary model Lucid*=realized, Apex*=intraday; eod / realized / intraday always reported",
                      "Apex sets UNCONFIRMED; fees are assumptions (R/fees.json); apex_eod rules grid defined by the research (no earlier search)",
                      "lift = P5(real) - P5(day-matched random control portfolio, same micros and rules): warning label, not a filter",
                      "WF fixed-set: member SET from the full-window search (look-ahead); WF reselect: whole search re-run per quarter, lift vs same-params controls is an upper bound; "
                      "the reselect search's net-share guard now sees only sessions before each test quarter (look-ahead fixed 2026-09-30; picks audited by wf_truncate.py), the candidate POOL is still ranked on the full window",
                      "exec: per-member executed entries / net P&L under the shared rules (portfolio.exec_stats); raw 50% net guard is on standalone P&L, see flags DEAD_MEMBERS / EXEC_NET_SHARE / NEGATIVE_EXEC_MEMBER",
                      "risk curve: every member's micros x scale (rounded, >=1, clipped to the firm cap); 'fixed' keeps the portfolio's rules cell, 'reopt' re-optimises rules",
                      "multi-account mixes are in-sample greedy slot fillings of the per-firm specs"],
            "firms": res, "multi_account": multi, "fast_objective": {"firms": fast, "multi_account": multi_fast}}
    (OUT / "portfolio_results.json").write_text(json.dumps(full, indent=1, default=P._js))
    txt = summary(res, multi, fast)
    (OUT / "portfolio_summary.md").write_text(txt + "\n")
    (OUT / "portfolio_members.md").write_text(members_md(res) + "\n")
    print(txt)
    print(len(txt.splitlines()), "summary lines")


if __name__ == "__main__":
    main()
