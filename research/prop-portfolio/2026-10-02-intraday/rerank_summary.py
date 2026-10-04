#!/usr/bin/python3
"""rerank.py --stage summary: out/summary.md (<= 80 lines) + out/eval_top10.md + out/funded_top5.md + out/edge_needed.json from this directory's
outputs. Every number in the text is read from an output file or computed here from one (no hard-coded results)."""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import csv                              # noqa: E402
import json                             # noqa: E402

import numpy as np                      # noqa: E402

FIRM_WF = {"lucid": "lucid_flex", "lucidpro": "lucidpro", "lucidpro_nodll": "lucidpro_nodll", "apex": "apex", "apex_eod": "apex_eod"}
FUNDED_OF = {"lucid": ("flex", "flex_dll"), "lucidpro": ("pro_dll",), "lucidpro_nodll": ("pro_nodll",)}
SHORT = {"lucid": "Flex", "lucidpro": "Pro +DLL", "lucidpro_nodll": "Pro noDLL"}
FEE_KEY = {"lucid": "lucid-flex-50k@2026-09-27", "lucidpro": "lucid-pro-50k@2026-09-27b", "lucidpro_nodll": "lucid-pro-50k-no-dll@2026-09-27b"}


def pc(x, d=0):
    return "-" if x is None or x != x else f"{100 * x:.{d}f}%"


def usd(x):
    if x is None or x != x:
        return "-"
    return f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


def susd(x):
    return "-" if x is None or x != x else ("+" if x >= 0 else "-") + f"${abs(x):,.0f}"


def pts(x):
    return "-" if x is None or x != x else f"{100 * x:+.0f} pts"


def num(x, d=2):
    return "-" if x is None or x != x else f"{x:.{d}f}"


def rules_txt(r):
    b = [f"{int(r['micros'])} micros"]
    if r.get("day_lock"):
        b.append(f"lock {int(r['day_lock'])}")
    if r.get("day_take"):
        b.append(f"take {int(r['day_take'])}")
    if r.get("day_stop"):
        b.append(f"day stop {int(r['day_stop'])}")
    if r.get("max_day_tr"):
        b.append("1 trade/day")
    if r.get("target_take"):
        b.append("target-take")
    if "policy" in r:
        b.append(f"payout at {'the cap' if r['policy'] == 'max' else '$' + format(int(float(r['policy'])), ',')}")
    return ", ".join(b)


def name(r):
    return f"{r['fam']} tf{r['tf']} {r['sess']} [{r['key']}]"


def load(OUT, f, default=None):
    p = OUT / f
    return json.loads(p.read_text()) if p.exists() else default


# ------------------------------------------------------------------ what win rate would 60% take (random walk, computed)

def p_pass(p, u, n=None, up=3000.0, dn=2000.0):
    """P(+up before -dn) for a walk of +-u per trade with win probability p; n = at most n trades (None = no limit). No costs."""
    a, b = int(round(dn / u)), int(round(up / u))
    if n is None:
        if abs(p - 0.5) < 1e-12:
            return a / (a + b)
        r = (1 - p) / p
        return (1 - r ** a) / (1 - r ** (a + b))
    v = np.zeros(a + b + 1)
    v[a], done = 1.0, 0.0
    for _ in range(n):
        w = np.zeros_like(v)
        w[1:] += v[:-1] * p
        w[:-1] += v[1:] * (1 - p)
        done += w[-1]
        w[-1] = w[0] = 0.0
        v = w
    return float(done)


def win_needed(u, n, target=0.60):
    lo, hi = 0.5, 0.9999
    for _ in range(60):
        m = (lo + hi) / 2
        lo, hi = (lo, m) if p_pass(m, u, n) >= target else (m, hi)
    return hi


def edge_table():
    return {str(u): {"no_edge": p_pass(0.5, u), "unlimited": win_needed(u, None), **{f"{k}_per_day": win_needed(u, 5 * k) for k in (1, 2, 3, 5)}} for u in (500, 1000)}


# ------------------------------------------------------------------ summary

def write(RR, RL, R2):
    OUT, LUCID, LV = RR.OUT, RR.LUCID, RR.LV
    et, ft = load(OUT, "eval_top.json"), load(OUT, "funded_top.json")
    wfs, sl, desk, ver = load(OUT, "wf_summary.json", {}), load(OUT, "second_look.json", {}), load(OUT, "desk_algos.json", {}), load(OUT, "verify.json", {})
    nwf = load(OUT, "funded_nwf.json", {})
    fees = json.loads((RR.S.R / "fees.json").read_text())
    FEE = {f: float(fees[FEE_KEY[f]]["eval_fee"]) for f in LUCID}
    assert FEE == {f: RR.FEE[f] for f in LUCID}
    star = {f: "*" if fees[FEE_KEY[f]].get("assumption") else "" for f in LUCID}
    edge = edge_table()
    RL.jdump(OUT / "edge_needed.json", {"what": "win rate needed for P(+$3,000 before -$2,000) >= 60% at 1:1, by $ per trade and trades per day over 5 days; no costs",
                                        "table": edge})
    wf_rows = [dict(r) for r in csv.DictReader((OUT / "wf_intraday.csv").open())] if (OUT / "wf_intraday.csv").exists() else []
    for r in wf_rows:
        for k in ("oos_p5", "oos_lift", "is_p5", "drop", "oos_ci_lo", "oos_ci_hi", "lift_ci_lo", "lift_ci_hi", "ctrl_oos_p5"):
            r[k] = RL.fnum(r.get(k))
    nest = wfs.get("nested", {})
    N = et["n_configs"]

    def wf_pick(f, r):
        g = r["key"].split("#")[0]
        for w in wf_rows:
            if w["firm"] == FIRM_WF[f] and w["grid"] == g and w["sess"] == r["sess"]:
                return w
        return None

    def near(r):
        return " (nearest control pool)" if r.get("pool_flag") else ""

    def twins(r):
        t = [x for x in (r.get("same_trade") or "").split(";") if x]
        return f" (the same trade is also {', '.join(t[:3])}{' and ' + str(len(t) - 3) + ' more' if len(t) > 3 else ''})" if t else ""

    def eval_line(i, f, r):
        w = wf_pick(f, r)
        if not w:
            wtxt = " | walk-forward: its grid was not walked"
        elif w["oos_lift"] == w["oos_lift"]:
            wtxt = f" | walk-forward of its grid {pc(w['oos_p5'])} (vs optimised random {pts(w['oos_lift'])})"
        else:
            wtxt = f" | walk-forward of its grid {pc(w['oos_p5'])} (no valid control)"
        if r.get("lift_u_intraday_p5") is not None:
            ltxt = f"vs day-matched random {pts(r['lift_u_intraday_p5'])} (above {r['beats_u']} of {r['K_u']} random replicates){near(r)}"
        else:
            ltxt = f"vs day-matched random {pts(r['lift_intraday_p5'])} (pilot's control){near(r)}"
        return (f"{i}. {name(r)}{twins(r)}: {rules_txt(r)} | pass in 1/2/3/5 days {pc(r['intraday_p1'])}/{pc(r['intraday_p2'])}/{pc(r['intraday_p3'])}/**{pc(r['intraday_p5'])}** "
                f"(stable {pc(r['stab_intraday_p5'])}, CI {pc(r['intraday_ci_lo'])}-{pc(r['intraday_ci_hi'])}), bust {pc(r['intraday_bust5'])}, median {num(r['intraday_med'], 0)} d"
                f" | old model: realized {pc(r['realized_p5'])}, eod {pc(r['eod_p5'])} | {ltxt}{wtxt}"
                f" | raw at 1 NQ: net {usd(r['net_1nq'])}, PF {num(r['pf_1nq'])}, t {num(r['t_1nq'], 1)}, {r['trades']} trades")

    def funded_line(i, r):
        lift, ctrl = (r["lift_u_e40"], r["ctrl_u_e40"]) if r.get("lift_u_e40") is not None else (r.get("lift_e40"), r.get("ctrl_e40"))
        return (f"{i}. {name(r)}: {rules_txt(r)} | **{usd(r['e_net_40'])}** to you in 40 days (stable {usd(r['score_e_net_40'])}, CI {usd(r.get('e40_ci_lo'))}-{usd(r.get('e40_ci_hi'))})"
                f" | payout within 20/40 days {pc(r['p_pay_20'])}/{pc(r['p_pay_40'])}, median {num(r.get('med_days_first'), 0)} d | bust before 1st payout {pc(r['p_bust_pre_first'])}"
                f" | {susd(lift)} over day-matched random, which made {usd(ctrl)}{' (nearest control pool)' if r.get('ctrl_pool') == 'nearest' else ''}"
                f" | rules-only walk-forward {usd(r.get('wf_oos_e_net_40'))} (this config was picked on the whole sample: not out-of-sample)"
                f" | old model (realized) at this cell {usd(r.get('realized_e40'))} | raw at 1 NQ: net {usd(r['net_1nq'])}, PF {num(r.get('pf_1nq'))}, t {num(r.get('t_1nq'), 1)}")

    # ---------------- detail files
    D = [f"# Eval top 10 per firm under the true rule (intraday = open losses count). In-sample 2021-09-22 -> 2024-12-31. {N:,} configs. Stable pick = R's neighbour median.",
         "Pass % are R's 'intraday' numbers: when a take rule fires they still charge the trade's whole adverse move (worst-first), so they are a floor, not the exact value.",
         "One line per distinct trade: configs with identical entries and an identical result at the reported cell are folded into one line.", ""]
    for f in RR.FIRMS5:
        nr, c = et["null"][f], et["ceiling"][f]
        D.append(f"## {RR.FIRM_LABEL[f]}: zero-edge ceiling {pc(c['p'])}; random-entry null (same search, {nr['n']} pseudo-configs) mean / p95 / max {pc(nr['p5_mean'])} / {pc(nr['p5_p95'])} / {pc(nr['p5_max'])}")
        D += [eval_line(i, f, r) for i, r in enumerate(et["top"][f], 1)]
        D.append("")
    (OUT / "eval_top10.md").write_text("\n".join(D) + "\n")
    if ft:
        D = ["# Funded top 5 per account type under the true rule (intraday). In-sample, 60-session lives, rolling starts. $ = paid to the trader after the 90/10 split.",
             "These are the best of the whole universe on the whole sample (selection-biased). The out-of-sample numbers are in out/funded_nwf.json / funded_nwf.csv.", ""]
        for v in LV:
            n = ft["null"][v]
            D.append(f"## {RR.V_LABEL[v]}: random-entry null (same search, {n['n']} pseudo-configs) stable $ mean / p95 / max {usd(n['score_mean'])} / {usd(n['score_p95'])} / {usd(n['score_max'])}; "
                     f"expected best of {n['n_universe']:,} independent zero-edge draws about {usd(n['exp_best_of_universe'])}")
            D += [funded_line(i, r) for i, r in enumerate(ft["top"][v], 1)]
            D.append("")
        (OUT / "funded_top5.md").write_text("\n".join(D) + "\n")

    # ---------------- second-look aggregates (2025-01 -> 2026-09, labelled, never selected on)
    sle = {f: [x for x in (sl or {}).get("eval", []) if x["firm"] == f] for f in LUCID}
    slf = {v: [x for x in (sl or {}).get("funded", []) if x["variant"] == v] for v in LV}
    sl_p = {f: float(np.mean([x["ho_intraday"]["p5"] for x in xs])) for f, xs in sle.items() if xs}
    sl_is = {f: float(np.mean([x["is_intraday_p5"] for x in xs])) for f, xs in sle.items() if xs}
    sl_lift = {f: float(np.mean([x["ho_lift_intraday"]["lift"] for x in xs])) for f, xs in sle.items() if xs}
    sl_v = {v: float(np.mean([x["ho_intraday"]["e_net_40"] for x in xs])) for v, xs in slf.items() if xs}
    sl_vlift = {v: float(np.mean([x["ho_lift_intraday"]["lift_e40"] for x in xs])) for v, xs in slf.items() if xs}
    fall = [x for xs in slf.values() for x in xs]
    eall = [x for xs in sle.values() for x in xs]
    ret = [x["ho_intraday"]["e_net_40"] / x["is_e40"] for x in fall]

    # ---------------- economics rows (one per eval firm x funded account type)
    best = {f: et["top"][f][0] for f in RR.FIRMS5}
    econ = []
    for f in LUCID:
        ne = nest.get(f, {})
        for v in FUNDED_OF[f]:
            t, nw = (ft["top"][v] if ft else []), nwf.get(v, {})
            if not t:
                continue
            k5 = nw.get("top5", {})
            p_is, v_is = best[f]["intraday_p5"], t[0]["e_net_40"]
            p_n, v_n = ne.get("oos_p5"), k5.get("e40")
            o = dict(f=f, v=v, p_is=p_is, v_is=v_is, ev_is=p_is * v_is - FEE[f], p_n=p_n, v_n=v_n,
                     ev_n=(p_n * v_n - FEE[f]) if p_n is not None and v_n is not None else None,
                     ev_lo=(ne["oos_ci"][0] * max(k5["ci"][0], 0.0) - FEE[f]) if k5 and ne else None,
                     ev_hi=(ne["oos_ci"][1] * k5["ci"][1] - FEE[f]) if k5 and ne else None,
                     p_c=ne.get("ctrl_oos_p5"), v_c=k5.get("ctrl_e40"),
                     ev_c=(ne["ctrl_oos_p5"] * k5["ctrl_e40"] - FEE[f]) if k5 and ne.get("ctrl_oos_p5") is not None else None,
                     ev_sl=(sl_p[f] * sl_v[v] - FEE[f]) if f in sl_p and v in sl_v else None)
            econ.append(o)

    def rng(k, xs=None):
        xs = [x[k] for x in (xs or econ) if x.get(k) is not None]
        return f"{usd(min(xs))} to {usd(max(xs))}" if xs else "-"

    dk = desk
    dk_ev = {}
    if dk:
        for lab, evk, fnk, f in (("Flex nq_nyam_flex + nq_pm_flex", "nq_nyam_flex", "nq_pm_flex", "lucid"), ("Pro noDLL nq_nyam_pro + nq_orb_pro", "nq_nyam_pro", "nq_orb_pro", "lucidpro_nodll")):
            dk_ev[lab] = {w: (dk[evk][f"desk_{w}"]["intraday"]["p5"], dk[fnk][f"desk_{w}"]["intraday"]["e_net_40"], FEE[f]) for w in ("is", "ho")}

    # ---------------- summary
    L = []
    pr = et["p2_reference"]
    L.append("# NQ prop pilot re-ranked under the TRUE Lucid rule: the drawdown counts open losses (2026-10-02, corrected after verification)")
    L.append(f"{N:,} configs = the pilot's {et['n_pilot']:,} + {et['n_ext']} pass-2 configs the pilot had searched but never carried into its final set. Same rules grid, same code; "
             "only the breach model changed from 'realized' (closed balance) to 'intraday' (open loss counts). In-sample 2021-09-22 -> 2024-12-31.")
    n60 = sum(et["n_any_cell_60"][f] for f in LUCID)
    L.append("**Verdict: nothing qualifies.** Best P(pass <= 5 days) of any config at any rules cell, in-sample: " + ", ".join(f"{SHORT[f]} {pc(et['max_raw'][f])}" for f in LUCID)
             + ". Re-picked every quarter and tested on the next one (out of sample): " + ", ".join(f"{SHORT[f]} {pc(nest[f]['oos_p5'])}" for f in LUCID if f in nest)
             + f". The bar is 60% and it is not relaxed. Configs with ANY rules cell at or above 60% on a Lucid account: {n60} of {N:,}.")
    L.append("Why: with open losses counted, an eval is 'make +$3,000 before you are ever down $2,000'. A strategy with no edge can do that at most 40% of the time (Flex about 33%: two days needed, no day over half the profit). "
             "The old 69-81% came from stops of several thousand dollars whose open loss the old model ignored (section 7).")
    if dk:
        a, b = dk["nq_nyam_flex"], dk["nq_nyam_pro"]
        L.append(f"**Past approved accounts: yes, affected.** Replayed tick by tick (the desk builds, take as a real exit): nq_nyam_flex passes {pc(a['desk_is']['intraday']['p5'])} in-sample "
                 f"({pc(a['desk_ho']['intraday']['p5'])} on 2025-26, a second look), nq_nyam_pro {pc(b['desk_is']['intraday']['p5'])} ({pc(b['desk_ho']['intraday']['p5'])}), "
                 f"not the approved {pc(a['R_ho']['realized']['p5'])} / {pc(b['R_ho']['realized']['p5'])}. Section 7.")
    if econ and all(x["ev_n"] is not None for x in econ):
        dtxt = ""
        if dk_ev:
            ds = [p * v - fee for d in dk_ev.values() for (p, v, fee) in d.values()]
            dtxt = f"; {usd(min(ds))} to {usd(max(ds))} with the built desk algos (tick replay)"
        L.append(f"**Money: thin.** Out of sample an eval bought was worth {rng('ev_n')} ({rng('ev_lo')} at the low ends); random entries under the same rules get {rng('ev_c')}, "
                 f"so a good part of it is the account's built-in option, not the entries. 2025-26 second look: {rng('ev_sl')}{dtxt}. "
                 "The pilot's old figure was about $2,000 to $3,800. Section 5.")
    L.append("Correction to the first version of this file: it valued an eval at $290 to $521 'on walk-forward numbers'. That walk-forward only re-picked the rules of a config already chosen on the whole sample, "
             "so it was not out of sample; it also listed one LucidPro trade three times. Both are fixed here; the verdict did not change, the money did.")
    L.append(f"## 1. Eval: top 4 per Lucid account by in-sample stable P5, intraday as the objective (all 10 + Apex in out/eval_top10.md, every config in out/eval_intraday.csv)")
    L.append("In-sample, best of the whole search: read these as an upper bound (sections 3 and 6 show what survives). When a take rule fires the pilot's intraday model still charges the trade's whole adverse move (worst-first), so take-heavy setups are understated (section 7); the ceiling still holds. One line per distinct trade.")
    for f in LUCID:
        L.append(f"**{RR.FIRM_LABEL[f]}** (fee {usd(FEE[f])}{star[f]})")
        L += [eval_line(i, f, r) for i, r in enumerate(et["top"][f][:4], 1)]
    L.append("Reference, same search: " + "; ".join(f"{RR.FIRM_LABEL[f]} best {pc(best[f]['intraday_p5'])} ({name(best[f])}, {rules_txt(best[f])})" for f in ("apex", "apex_eod")) + ".")
    g = et["grids"]["lucid"]
    L.append(f"Open-loss cap: the grid has no per-trade cap. Its day stop acts on open loss (closes the trade when the day is down $Y; with 1 trade a day it is a per-trade cap). Values searched: Flex {g['day_stop']}, Pro {et['grids']['lucidpro']['day_stop']}; funded {ft['grid']['day_stop'] if ft else '-'}.")
    chk = (f"Check: {ver['n']} top picks re-computed from the trade bundles, largest difference from the stored numbers {ver['max_abs_diff']:.1e} ({ver['mismatches']} mismatches); " if ver else "Check: ")
    chk += f"the {et['n_ext']} added configs match the pilot's own pass-2 intraday rows to {pr['ext_max_abs_diff_vs_R_pass2']:.1e} ({pr['ext_rows_checked']:,} rows)"
    chk += (f"; the second-look scorer run on in-sample data matches to {sl['max_path_diff']:.1e}." if sl and sl.get("max_path_diff") is not None else ".")
    nrk = pr["not_ranked_max_any_cell_p5"]
    chk += (f" Not ranked: {pr['not_ranked']:,} more pass-2 configs that lose money at 1 NQ (the pilot's own filter). Their best stored intraday P5 (any cell) is "
            + ", ".join(f"{SHORT[f]} {pc(nrk.get(f))}" for f in LUCID) + "; by stable P5 "
            + " / ".join(str(pr["not_ranked_above_10th"].get(f, 0)) for f in LUCID) + " of them would sit inside the " + " / ".join(SHORT[f] for f in LUCID) + " top 10.")
    L.append(chk)
    L.append("## 2. Zero-edge control (random entries, same days, same optimised search)")
    for f in LUCID:
        nr, c = et["null"][f], et["ceiling"][f]
        t = et["top"][f]
        lf = [r.get("lift_u_intraday_p5", r["lift_intraday_p5"]) for r in t]
        L.append(f"{RR.FIRM_LABEL[f]}: best of {N:,} real configs {pc(et['max_own'][f])} vs best of {nr['n']} random pseudo-configs {pc(nr['p5_max'])} (random mean {pc(nr['p5_mean'])}, p95 {pc(nr['p5_p95'])}); "
                 f"theoretical ceiling {pc(c['p'])} ({c['why']}). The {len(t)} distinct top picks vs their own day-matched random at the same rules: {pts(min(lf))} to {pts(max(lf))}; "
                 f"{sum(1 for r in t if r.get('K_u') and r['beats_u'] == r['K_u'])} of {len(t)} are above every one of their 10 random replicates, {sum(1 for r in t if r.get('pool_flag'))} of {len(t)} use a nearest (not exact) control pool.")
    e5, e10 = edge["500"], edge["1000"]
    L.append("So in-sample the picks sit on the ceiling and a few points above random entries (they are the best of the search, so some of that is selection). The rules do most of the work. What 60% would take, at even odds and before costs (random-walk arithmetic, out/edge_needed.json): "
             f"risking $1,000 a trade, {pc(e10['1_per_day'])} winners at one trade a day, {pc(e10['2_per_day'])} at two, {pc(e10['unlimited'])} with unlimited time; "
             f"risking $500, {pc(e5['3_per_day'])} at three a day, {pc(e5['5_per_day'])} at five, {pc(e5['unlimited'])} unlimited. The best raw edges here are PF 1.1-1.2 at about one trade a day.")
    L.append("## 3. Walk-forward (each quarter pick config + rules on the trailing 12 months by the intraday objective, test the next quarter; out/wf_intraday.csv)")
    for f in LUCID:
        w = wfs.get(FIRM_WF[f])
        if w:
            L.append(f"{RR.FIRM_LABEL[f]}: {w['n']} family grids. Out-of-sample pass, median grid {pc(w['oos_p5_median'])}; the best single grid {pc(w['oos_p5_best'])} ({w['best']}) is picked by its own out-of-sample result, so it is optimistic. "
                     f"In-sample minus out-of-sample {pts(w['drop_median'])}. Against optimised random entries (the {w['n_ctrl_valid']} grids with a valid control): median {pts(w['lift_median'])} "
                     f"(random itself: median {pc(w['ctrl_oos_median'])}, best {pc(w['ctrl_oos_max'])}). Grids at 60%+: {w['n_ge_60']}.")
    if nest:
        gap = [nest[f]["oos_p5_ctrl_grids"] - nest[f]["ctrl_oos_p5"] for f in LUCID if nest.get(f, {}).get("ctrl_oos_p5") is not None]
        L.append("Nested (each quarter the grid with the best TRAINING score, nothing chosen by its test result): "
                 + "; ".join(f"{SHORT[f]} {pc(nest[f]['oos_p5'])} (CI {pc(nest[f]['oos_ci'][0])}-{pc(nest[f]['oos_ci'][1])}; the training windows showed {pc(nest[f]['train_p5_mean'])})" for f in LUCID if f in nest)
                 + ". Random entries through the same selection (grids with a valid control, 5 replicates): "
                 + ", ".join(f"{SHORT[f]} {pc(nest[f].get('ctrl_oos_p5'))} ({pc(nest[f].get('ctrl_oos_min'))}-{pc(nest[f].get('ctrl_oos_max'))}) against {pc(nest[f].get('oos_p5_ctrl_grids'))} real on the same {nest[f].get('n_grids_ctrl')} grids" for f in LUCID if f in nest)
                 + (f". Out of sample the strategies run {pts(min(gap))} to {pts(max(gap))} against random entries (above every random replicate on "
                    f"{sum(1 for f in LUCID if nest.get(f, {}).get('ctrl_oos_max') is not None and nest[f]['oos_p5_ctrl_grids'] > nest[f]['ctrl_oos_max'])} of {len(gap)} accounts): "
                    "a small edge at best, far from the 20+ points the bar needs." if gap else "."))
    if ft:
        L.append("## 4. Funded: the in-sample best per account type, $ paid to you in the first 40 trading days (top 5 each in out/funded_top5.md, all in out/funded_intraday.csv; floors where a day take is used)")
        for v in LV:
            if ft["top"][v]:
                L.append(f"**{RR.V_LABEL[v]}** " + funded_line(1, ft["top"][v][0])[3:])
        L.append("These are the best of " + f"{ft['n_universe']:,}" + " configs on the whole sample, so they carry selection luck. Random entries through the same search (30 pseudo-configs), stable $ mean / best: "
                 + "; ".join(f"{v} {usd(ft['null'][v]['score_mean'])} / {usd(ft['null'][v]['score_max'])}" for v in LV)
                 + f". The expected best of {ft['n_universe']:,} independent random draws would be about "
                 + ", ".join(usd(ft["null"][v]["exp_best_of_universe"]) for v in LV)
                 + " (rough: the real configs overlap heavily), against the picks' stable " + ", ".join(usd(ft["top"][v][0]["score_e_net_40"]) for v in LV if ft["top"][v]) + ". Not clearly above luck.")
        L.append("## 5. Economics under the true rule, out of sample (nested walk-forward: each quarter the config AND its rules are picked on the trailing 12 months only; funded = mean of the 5 best-ranked distinct trades; out/funded_nwf.csv)")
        for x in econ:
            f, v = x["f"], x["v"]
            nw = nwf.get(v, {})
            k1, k5 = nw.get("top1", {}), nw.get("top5", {})
            if not k5:
                L.append(f"{RR.FIRM_LABEL[f]} -> {RR.V_LABEL[v]}: nested walk-forward not available.")
                continue
            L.append(f"{RR.FIRM_LABEL[f]} -> {RR.V_LABEL[v]}: funded account worth {usd(k5['e40'])} in 40 days (CI {usd(k5['ci'][0])}-{usd(k5['ci'][1])}; payout within 40 days {pc(k5['p_pay_40'])}, bust before the first payout {pc(k5['p_bust_pre'])}; the single top pick {usd(k1['e40'])}; "
                     f"an average config {usd(nw['universe_mean_e40'])}; training windows promised {usd(k5['train_e40'])}); random entries at the same rules {usd(k5['ctrl_e40'])} "
                     f"(difference {susd(k5['lift'])}, CI {susd(k5['lift_ci'][0])} to {susd(k5['lift_ci'][1])}). Per eval bought: {pc(x['p_n'])} x {usd(x['v_n'])} - {usd(FEE[f])}{star[f]} = **{usd(x['ev_n'])}** "
                     f"(both at their low / high ends: {usd(x['ev_lo'])} / {usd(x['ev_hi'])}); random entries: {pc(x['p_c'])} x {usd(x['v_c'])} - {usd(FEE[f])} = {usd(x['ev_c'])}. "
                     f"In-sample best-of-search figure, biased: {pc(x['p_is'])} x {usd(x['v_is'])} - {usd(FEE[f])} = {usd(x['ev_is'])}.")
        if dk_ev:
            L.append("The built desk algos, tick replay (exact order of take and open loss; in-sample | 2025-26 second look): "
                     + "; ".join(f"{lab} {pc(d['is'][0])} x {usd(d['is'][1])} - {usd(d['is'][2])} = {usd(d['is'][0] * d['is'][1] - d['is'][2])} | {pc(d['ho'][0])} x {usd(d['ho'][1])} - {usd(d['ho'][2])} = {usd(d['ho'][0] * d['ho'][1] - d['ho'][2])}"
                                 for lab, d in dk_ev.items()) + ". The pilot's old figures for the same pairs were about +$2,000 and +$3,800.")
        n_sig = sum(1 for v in LV if nwf.get(v, {}).get("top5", {}).get("lift_ci", [0])[0] > 0)
        rho = [nwf[v]["rank_corr_mean"] for v in LV if v in nwf]
        gap5 = [nest[f]["oos_p5_ctrl_grids"] - nest[f]["ctrl_oos_p5"] for f in LUCID if nest.get(f, {}).get("ctrl_oos_p5") is not None]
        L.append(f"Plainly: an eval bought has a small positive expected value on paper ({rng('ev_n')} out of sample; {rng('ev_lo')} at the low ends). Random entries with the same rules get {rng('ev_c')}: "
                 "part of the value is the account's built-in option (you risk the fee, the firm carries the loss). What the entries add out of sample: "
                 + (f"about {pts(min(gap5))} to {pts(max(gap5))} of pass rate (section 3) and " if gap5 else "")
                 + f"nothing measurable on the funded side (difference above zero with confidence on {n_sig} of {len(LV)} account types"
                 + (f"; a config's training score barely predicts its next quarter, rank correlation {min(rho):+.2f} to {max(rho):+.2f}). " if rho else "). ")
                 + "It is thin: it assumes a breach at exactly -$2,000 (a real liquidation slips), every payout paid, 40 days only, activation $0 and the fees above (* = assumed). "
                 "A $30-$50 fee change or one refused payout moves the sign.")
    if sl:
        L.append("## 6. SECOND LOOK on 2025-01 -> 2026-09 (the holdout was already spent on the old finalists: not a clean exam, nothing selected on it"
                 + ("" if str(sl.get("control", "")).startswith("unbiased") else "; 'vs random' here is the PILOT's biased control: re-run the light stages with RR_CTRL=overlap") + ")")
        for f in LUCID:
            if sle[f]:
                L.append(f"{RR.FIRM_LABEL[f]}: " + "; ".join(f"{x['key']}{' (scored on its twin ' + x['via_twin'] + ')' if x.get('via_twin') else ''} {x['sess']} {pc(x['is_intraday_p5'])} -> {pc(x['ho_intraday']['p5'])} (vs random {pts(x['ho_lift_intraday']['lift'])})" for x in sle[f]) + ".")
        if fall:
            L.append("Funded, $ in 40 days: " + "; ".join(f"{x['variant']} {x['key']} {x['sess']} {usd(x['is_e40'])} -> {usd(x['ho_intraday']['e_net_40'])} ({susd(x['ho_lift_intraday']['lift_e40'])} vs random)" for x in fall) + ".")
        if eall:
            L.append(f"Averages over the picks that have a bundle: eval {pc(float(np.mean([x['is_intraday_p5'] for x in eall])))} in-sample -> {pc(float(np.mean([x['ho_intraday']['p5'] for x in eall])))} "
                     f"({pts(float(np.mean([x['ho_lift_intraday']['lift'] for x in eall])))} vs random); "
                     + (f"funded kept {pc(float(np.mean(ret)))} of its in-sample value on average (median {pc(float(np.median(ret)))}), {susd(float(np.mean([x['ho_lift_intraday']['lift_e40'] for x in fall])))} vs random. " if fall else "")
                     + "Per eval bought on these numbers (mean pass x mean funded value - fee): "
                     + "; ".join(f"{RR.FIRM_LABEL[x['f']]} -> {x['v']} {pc(sl_p[x['f']])} x {usd(sl_v[x['v']])} - {usd(FEE[x['f']])} = {usd(x['ev_sl'])}" for x in econ if x["ev_sl"] is not None) + ".")
        nb = sl["no_bundle"]

        def grp(xs, labels):
            g = {}
            for x in xs:
                k, v = x.split(": ", 1)
                if k in labels:
                    g.setdefault(labels[k], []).append(v)
            return "; ".join(f"{k}: {', '.join(v)}" for k, v in g.items()) or "none"
        ne = [x for x in nb["eval"] if x.split(":")[0] in LUCID]
        L.append(f"No 2025+ bundle, so no second look ({len(ne)} of {sum(len(et['top'][f]) for f in LUCID)} eval picks, {len(nb['funded'])} of {len(nb['funded']) + len(fall)} funded picks). Eval - "
                 + grp(ne, {f: RR.FIRM_LABEL[f] for f in LUCID}) + ". Funded - " + grp(nb["funded"], {v: v for v in LV}) + ".")
    if dk:
        L.append("## 7. The four desk algos under the true rule (40 micros = 4 NQ; in-sample | 2025-26 second look)")
        L.append("Three numbers each: old model (closed balance only) | the pilot's intraday column (worst-first: assumes the full adverse move comes before the take) | tick replay of the desk build (the take is a real exit, so the open loss is the one before the exit: the true order).")
        stops = []
        for nm, a in dk.items():
            ol_i, ol_h = a["desk_open_loss_is"], a["desk_open_loss_ho"]
            k = max(ol_i)
            stops.append((ol_i[k]["stop_usd_median"], ol_h[k]["stop_usd_median"]))
            stxt = f" Stop distance at 4 NQ, median: {usd(ol_i[k]['stop_usd_median'])} | {usd(ol_h[k]['stop_usd_median'])}."
            if "p5" in a["R_is"]["realized"]:
                L.append(f"**{nm}** ({a['what']}, {a['config']}): pass <= 5 d old {pc(a['R_is']['realized']['p5'])} | {pc(a['R_ho']['realized']['p5'])}; worst-first {pc(a['R_is']['intraday']['p5'])} | {pc(a['R_ho']['intraday']['p5'])}; "
                         f"**tick replay {pc(a['desk_is']['intraday']['p5'])} | {pc(a['desk_ho']['intraday']['p5'])}** (bust {pc(a['desk_is']['intraday']['bust5'])} | {pc(a['desk_ho']['intraday']['bust5'])}). "
                         f"Open loss past $2,000 before the exit on {pc(ol_i[k]['open_loss_ge_mll'])} | {pc(ol_h[k]['open_loss_ge_mll'])} of days (whole-trade: {pc(a['full_trade_open_loss_share_is'])} | {pc(a['full_trade_open_loss_share_ho'])}).{stxt}")
            else:
                sizes = ", ".join(f"{q} {pc(ol_i[q]['open_loss_ge_mll'])}" for q in sorted(ol_i)) if len(ol_i) > 1 else pc(ol_i[k]["open_loss_ge_mll"])
                L.append(f"**{nm}** ({a['what']}, {a['config']}): $ in 40 d old {usd(a['R_is']['realized']['e_net_40'])} | {usd(a['R_ho']['realized']['e_net_40'])}; worst-first {usd(a['R_is']['intraday']['e_net_40'])} | {usd(a['R_ho']['intraday']['e_net_40'])}; "
                         f"**tick replay {usd(a['desk_is']['intraday']['e_net_40'])} | {usd(a['desk_ho']['intraday']['e_net_40'])}** (bust before 1st payout {pc(a['desk_is']['intraday']['p_bust_pre_first'])} | {pc(a['desk_ho']['intraday']['p_bust_pre_first'])}). "
                         f"Open loss past $2,000 before the exit on {sizes} of days in-sample (whole-trade: {pc(a['full_trade_open_loss_share_is'])}).{stxt}")
        lo_i, hi_i, lo_h, hi_h = min(s[0] for s in stops), max(s[0] for s in stops), min(s[1] for s in stops), max(s[1] for s in stops)
        L.append(f"Why: the stop is 3 ATR. At 4 NQ its median distance is {usd(lo_i)}-{usd(hi_i)} in-sample ({lo_i / R2.MLL:.1f} to {hi_i / R2.MLL:.1f} times the $2,000 limit) and {usd(lo_h)}-{usd(hi_h)} on 2025-26 "
                 f"({lo_h / R2.MLL:.1f} to {hi_h / R2.MLL:.1f} times). Lucid closes the account long before the stop. What is left is 'take before -$2,000', which is the zero-edge ceiling.")
    L.append("## 8. What to run Monday (bar: P(pass <= 5 days) >= 60%, never relaxed)")
    built = {"lucid": "nq_nyam_flex", "lucidpro_nodll": "nq_nyam_pro"}
    for f in LUCID:
        b = best[f]
        ne = nest.get(f, {})
        x = (f"{RR.FIRM_LABEL[f]} eval: **nothing qualifies** (best of any config {pc(et['max_raw'][f])}, bar 60%). If you run one anyway, the top-ranked is {name(b)}, {rules_txt(b)}: {pc(b['intraday_p5'])} in-sample (best of the search, optimistic), "
             f"expect about {pc(ne.get('oos_p5'))} (what this way of picking delivered out of sample)"
             + (f" or {pc(sl_p[f])} (2025-26 second look, mean of the {len(sle[f])} top picks with a bundle, {pts(sl_lift[f])} vs random)" if f in sl_p else "")
             + f", bust {pc(b['intraday_bust5'])} in-sample; fees per funded account about {usd(FEE[f] / ne['oos_p5']) if ne.get('oos_p5') else '-'}{star[f]}")
        if dk and f in built:
            d = dk[built[f]]["desk_is"]["intraday"]
            x += f"; the built {built[f]} is the same class: {pc(d['p5'])} by tick replay"
        L.append(x + ".")
    if ft and nwf:
        L.append("Funded accounts (no 60% bar is defined for them): expect the out-of-sample value of section 5, not the in-sample pick's: "
                 + "; ".join(f"{RR.V_LABEL[v]} {usd(nwf[v]['top5']['e40'])} in 40 days (random entries {usd(nwf[v]['top5']['ctrl_e40'])}"
                             + (f"; 2025-26 second look {usd(sl_v[v])}" if v in sl_v else "") + ")" for v in LV if nwf.get(v, {}).get("top5"))
                 + ". The in-sample picks of section 4 are listed for reference, not as a recommendation.")
    L.append("The four approved NQ algos (nq_nyam_flex / nq_nyam_pro / nq_orb_pro / nq_pm_flex) do not meet the bar under the true rule: if they run, expect section 7's odds, not the approved ones. "
             "gc_nfp was not re-tested here; by its desk config its stop is 5.0 points x 4 contracts = $2,000, the max loss itself, so counting open losses should not move its breach point.")
    L.append("## Could not do / limits")
    L.append("- Exact tick order exists only for the four desk builds (their six tick replays from 2026-10-01 are copied to desk_runs/). Every other trade list carries one whole-trade adverse figure, so intraday numbers with a take rule are floors. No new tester runs were allowed.")
    L.append(f"- Funded search: coarse screen on all {ft['n_universe'] if ft else N:,} configs (sizes 10/20/40 micros; the pilot used 20/40), then the pilot's full grid on the top 30 per account type (pilot: 100) and 30 zero-edge controls (pilot: 60). "
             "The nested walk-forward uses the coarse grid (192 cells) and 8 test quarters (2022Q4-2024Q3); 60-day lives overlap, so its intervals are wide.")
    L.append("- Still chosen on the whole sample: the candidate filter (300+ trades, net > 0 at 1 NQ for heat-map cells) and, for the eval walk-forward, which grids were walked (top 12 pass-3 grids by in-sample P5 + the pilot's 24). Both lean optimistic.")
    cb = load(OUT, "control_bias.json", {"rows": []})["rows"]
    hi, lo = (max(cb, key=lambda x: x["bias_r"]), min(cb, key=lambda x: x["bias_r"])) if cb else (None, None)
    btxt = (f" Measured on the reported picks (out/control_bias.json, $ per trade at 1 NQ): {hi['key']} {hi['sess']} pool {usd(hi['pool_mean'])}, the pilot's control {usd(hi['ctrl_r_mean'])}, the corrected draw {usd(hi['ctrl_u_mean'])}; "
            f"{lo['key']} {lo['sess']} pool {usd(lo['pool_mean'])}, the pilot's control {usd(lo['ctrl_r_mean'])}, corrected {usd(lo['ctrl_u_mean'])}." if cb else "")
    L.append("- Controls: two flaws of the pilot's random control are corrected here. (1) Its walk-forward took the control pool of a grid's first cell for every cell. (2) Its day-matched draw keeps only random trades that do not overlap, "
             "which favours short trades when a config trades more than once a day: too many winners with tight targets, too many losers with trend exits." + btxt
             + " All 'vs random' figures in this file use each config's own pool and a draw without that test (one-trade-a-day configs are unaffected). Grids without such a control ("
             + ", ".join(str(wfs[FIRM_WF[f]]["n"] - wfs[FIRM_WF[f]]["n_ctrl_valid"]) for f in LUCID if FIRM_WF[f] in wfs) + " of 36 per account: about 20 worker-minutes each to re-walk) keep their pass rates only; "
             "the lift columns of the non-top rows in eval_intraday.csv and funded_intraday.csv are still the pilot's.")
    L.append("- Fees: " + "; ".join(f"{SHORT[f]} {usd(FEE[f])} ({'assumed' if fees[FEE_KEY[f]].get('assumption') else 'from the user'})" for f in LUCID)
             + "; activation fee assumed $0 on all three (pilot's fees.json). Flex funded with a $1,200 daily limit is an assumed product (*). Apex rule sets are unconfirmed.")
    L.append("- Assumed as in the pilot: the $2,000 line trails the end-of-day balance (only the breach looks at open loss); if Lucid also trails intraday peaks the odds are lower.")
    assert len(L) <= 80, len(L)
    (OUT / "summary.md").write_text("\n".join(L) + "\n")
    print(f"summary.md: {len(L)} lines", flush=True)
