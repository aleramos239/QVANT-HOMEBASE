#!/usr/bin/python3
"""Pass 3 + pass 2 -> out/candidates.csv (one row per (config, firm)) and out/a3p3_summary.md (<= 70 lines).
Run: PYTHONPATH=~/ramos-quant-homebase /usr/bin/python3 a3p3_merge.py [--rows a3p3_rules.csv --rows2 a3p3_rescore2.csv --null a3p3_null.csv]

Inputs: out/a3p3_rules.csv (pass 3: hm2-*/fp-* cells), out/a3p3_rescore2.csv (pass-2 shortlist configs re-scored with the pass-3 analysis),
out/a3p3_null.csv (pseudo-configs), out/wf_offline_p3.csv (pass-3 offline walk-forward, eod + primary model) and out/wf_offline.csv (pass 2, eod + intraday).
Per (config, firm): the primary-model columns are taken at the P5-stable cell of the PRIMARY model (Lucid* realized, Apex* intraday); `sp1_*` / `sp3_*` = the
SPEED cells (stable cell maximising P1 / P3 under the primary model), each with its eod and intraday bound. Null flags compare the lift against the p95 of the
null lift of the same firm, metric and control-pool group (atr = ATR-stop pools, fp = points-stop fast-pass pools, tod = time-exit pools)."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E  # noqa: E402
import a3_pass2 as A2  # noqa: E402

OUT = E.D / "out"
FIRMS5 = ("lucid", "lucidpro", "lucidpro_nodll", "apex", "apex_eod")
M3 = ("eod", "realized", "intraday")
UNCONF = {"apex", "apex_eod"}
OCO_FAMS = {"orb", "straddle", "lon_break", "ib"}
ABBR = {"lucid": "FLX", "lucidpro": "LP+", "lucidpro_nodll": "LP0", "apex": "APX", "apex_eod": "AEOD"}
NAME = {"lucid": "Lucid Flex", "lucidpro": "LucidPro+DLL", "lucidpro_nodll": "LucidPro noDLL", "apex": "Apex (user set, UNCONFIRMED)", "apex_eod": "Apex EOD (site, UNCONFIRMED)"}
WF_FIRM = {"lucid": "lucid_flex", "lucidpro": "lucidpro", "lucidpro_nodll": "lucidpro_nodll", "apex": "apex", "apex_eod": "apex_eod"}


def rd(p):
    p = p if isinstance(p, Path) else OUT / p
    return list(csv.DictReader(p.open())) if p.exists() else []


def fl(x, d=float("nan")):
    try:
        return float(x) if x not in ("", None) else d
    except ValueError:
        return d


def group_of(pool_id):
    try:
        p = json.loads(pool_id)
    except Exception:
        return "atr"
    if p.get("stop_mode") == "pts":
        return "fp"
    if p.get("exit_bars", 0) and p.get("tgt_r", 1) == 0:
        return "tod"
    return "atr"


def rules_str(r, pre=""):
    g = lambda k: (str(int(fl(r.get(pre + k), 0))) if fl(r.get(pre + k), 0) else "-")
    return f"m{g('micros')} L{g('day_lock')} K{g('day_take')} S{g('day_stop')} T{g('max_day_tr')} {'TT' if fl(r.get(pre + 'target_take'), 0) else 'tt-'}"


def fees():
    fj = json.loads(E.PL.shared("fees.json").read_text())
    return {f: (float(fj[E.firm_rules(f)[0]]["eval_fee"]), float(fj[E.firm_rules(f)[0]].get("activation", 0.0))) for f in FIRMS5}


def null_stats(null):
    """{(firm, group, metric): dict(n, mean, p95, max, lift_p95)}; metric in p1 (speed_p1), p3 (speed_p3), p5_<model> (cellset p5_<model>)."""
    acc = defaultdict(lambda: ([], []))
    for r in null:
        f, g, prim = r["firm"], group_of(r["pool_id"]), E.primary_model(r["firm"])
        if r["cellset"] == "speed_p1":
            acc[(f, g, "p1")][0].append(fl(r[f"{prim}_p1"])), acc[(f, g, "p1")][1].append(fl(r["lift_prim_p1"]))
        elif r["cellset"] == "speed_p3":
            acc[(f, g, "p3")][0].append(fl(r[f"{prim}_p3"])), acc[(f, g, "p3")][1].append(fl(r["lift_prim_p3"]))
        elif r["cellset"].startswith("p5_"):
            mod = r["cellset"][3:]
            acc[(f, g, f"p5_{mod}")][0].append(fl(r[f"{mod}_p5"])), acc[(f, g, f"p5_{mod}")][1].append(fl(r[f"lift_{mod}_p5"]))
    out = {}
    for k, (v, lf) in acc.items():
        v, lf = np.array(v), np.array(lf)
        lf = lf[~np.isnan(lf)]
        out[k] = dict(n=len(v), mean=float(v.mean()), p95=float(np.percentile(v, 95)), max=float(v.max()),
                      lift_p95=float(np.percentile(lf, 95)) if len(lf) else float("nan"), lift_mean=float(lf.mean()) if len(lf) else float("nan"))
    return out


def nstat(ns, f, g, m):
    """Null stat with a fallback to the pooled groups when the group has < 20 pseudo-configs."""
    s = ns.get((f, g, m))
    if s and s["n"] >= 20:
        return s
    vs = [v for (ff, gg, mm), v in ns.items() if ff == f and mm == m]
    if not vs:
        return None
    n = sum(v["n"] for v in vs)
    return dict(n=n, mean=float(np.average([v["mean"] for v in vs], weights=[v["n"] for v in vs])), p95=float(np.mean([v["p95"] for v in vs])),
                max=max(v["max"] for v in vs), lift_p95=float(np.mean([v["lift_p95"] for v in vs])), lift_mean=float(np.mean([v["lift_mean"] for v in vs])))


def wf_index():
    """{(grid, sess, firm): {model: row}} per source: p3 (eod + primary) and p2 (eod + intraday)."""
    idx = {}
    for src, name in ((2, "wf_offline.csv"), (3, "wf_offline_p3.csv")):
        for r in rd(name):
            idx.setdefault((r["grid"], r["sess"], r["firm"]), {})[(src, r["model"])] = r
    return idx


def build(rows, null, wf, fee, ns):
    by = defaultdict(dict)
    for r in rows:
        by[(r["key"], r["sess"], r["firm"])][r["cellset"]] = r
    out = []
    for (key, sess, firm), cs in by.items():
        prim = E.primary_model(firm)
        c = cs.get(f"p5_{prim}")
        if c is None:
            continue
        g = group_of(c["pool_id"])
        grid = key.split("#")[0]
        p2 = c.get("pass2") == "1" or c.get("screen") == "1"      # pass 2 = configs of an earlier pass re-scored (NQ shortlist; ES screen configs)
        row = dict(**{"pass": 2 if p2 else 3}, firm=firm, unconfirmed=int(firm in UNCONF), config=f"{c['fam']}|{key}|{sess}", fam=c["fam"], tf=c["tf"], sess=sess, key=key,
                   grid=grid, params=c["params"], pool_group=g, pool_exact=c["pool_exact"], pool_flag=c["pool_flag"], fastpass=c.get("fastpass", ""),
                   trades=int(fl(c["trades"])), net_1nq=fl(c["net_1nq"]), exp_1nq=fl(c["exp_1nq"]), med_stop_pts=fl(c["med_stop_pts"]), primary_model=prim)
        row.update(rules=rules_str(c), **{k: int(fl(c[k])) for k in ("micros", "day_lock", "day_take", "day_stop", "max_day_tr", "target_take")})
        for k in ("p1", "p2", "p3", "p5"):
            row[f"{k}"] = fl(c[f"{prim}_{k}"])
            row[f"{k}_ci_lo"], row[f"{k}_ci_hi"] = fl(c[f"ci_{k}_lo"]), fl(c[f"ci_{k}_hi"])
        row["bust5"], row["med_days"] = fl(c[f"{prim}_bust5"]), fl(c[f"{prim}_med"])
        for mod, tag in (("eod", "eod"), ("intraday", "intr")):
            for k in ("p1", "p3", "p5", "bust5"):
                row[f"{tag}_{k}"] = fl(c[f"{mod}_{k}"])
        row["eod_p5_ci_lo"], row["eod_p5_ci_hi"] = fl(c.get("ci_eod_p5_lo")), fl(c.get("ci_eod_p5_hi"))
        row["intr_p5_ci_lo"], row["intr_p5_ci_hi"] = fl(c.get("ci_intraday_p5_lo")), fl(c.get("ci_intraday_p5_hi"))
        row["lift_p5"], row["ctrl_p5"], row["ctrl_p5_sd"] = fl(c["lift_prim_p5"]), fl(c[f"ctrl_{prim}_p5"]), fl(c["ctrl_prim_p5_sd"])
        row["lift_eod_p5"], row["lift_intr_p5"] = fl(c["lift_eod_p5"]), fl(c["lift_intraday_p5"])
        s5 = nstat(ns, firm, g, f"p5_{prim}")
        row["null_p5_mean"], row["null_p5_p95"], row["null_p5_max"], row["null_lift_p95"] = (s5["mean"], s5["p95"], s5["max"], s5["lift_p95"]) if s5 else (float("nan"),) * 4
        row["above_null_lift"] = int(bool(s5) and row["lift_p5"] > s5["lift_p95"])
        row["p5_gt_null_max"] = int(bool(s5) and row["p5"] > s5["max"])
        for sp, k in (("speed_p1", "p1"), ("speed_p3", "p3")):
            s = cs.get(sp)
            tag = "sp1" if k == "p1" else "sp3"
            if s is None:
                continue
            row[f"{tag}_rules"] = rules_str(s)
            row[f"{tag}_{k}"], row[f"{tag}_{k}_ci_lo"], row[f"{tag}_{k}_ci_hi"] = fl(s[f"{prim}_{k}"]), fl(s[f"ci_{k}_lo"]), fl(s[f"ci_{k}_hi"])
            row[f"{tag}_p5"], row[f"{tag}_bust5"] = fl(s[f"{prim}_p5"]), fl(s[f"{prim}_bust5"])
            row[f"{tag}_eod_{k}"], row[f"{tag}_intr_{k}"] = fl(s[f"eod_{k}"]), fl(s[f"intraday_{k}"])
            row[f"{tag}_lift_{k}"] = fl(s[f"lift_prim_{k}"])
            sn = nstat(ns, firm, g, k)
            row[f"{tag}_null_{k}_max"], row[f"{tag}_null_{k}_p95"] = (sn["max"], sn["p95"]) if sn else (float("nan"),) * 2
            row[f"{tag}_above_null_lift"] = int(bool(sn) and row[f"{tag}_lift_{k}"] > sn["lift_p95"])
            row[f"{tag}_exp_at_micros"] = fl(s["exp_at_micros"])
        row["exp_at_micros"], row["net_at_micros"] = fl(c["exp_at_micros"]), fl(c["net_at_micros"])
        row["cost_ratio_mix"], row["cost_rule_pass"] = fl(c["cost_ratio_mix"]), c["cost_pass_mix"]
        fe, act = fee[firm]
        for tag, p in (("", row["p5"]), ("_eod", row["eod_p5"]), ("_intr", row["intr_p5"])):
            row[f"cost_per_funded{tag}"] = fe / p + act if p and p > 0 else float("nan")
        row["evals_per_funded"] = 1 / row["p5"] if row["p5"] > 0 else float("nan")
        for y in (2022, 2023, 2024):
            row[f"p5_{y}"] = fl(c[f"p5_{y}"])
        ny = [fl(c.get(f"net1_{y}"), 0.0) for y in (2021, 2022, 2023, 2024)]
        for y, v in zip((2021, 2022, 2023, 2024), ny):
            row[f"net1_{y}"] = v
        row["pos_years"] = int(sum(v > 0 for v in ny))
        fl_ = []
        if row["net_1nq"] <= 0:
            fl_.append("NET<=0")
        elif max(ny) / row["net_1nq"] > 0.6:
            fl_.append("ONE_YEAR")
        if c["pool_exact"] != "True":
            fl_.append("NEAREST_POOL")
        if not row["above_null_lift"]:
            fl_.append("NO_EDGE_VS_RANDOM")
        if row["cost_rule_pass"] != "True":
            fl_.append("COST_RULE_FAIL")
        row["flags"] = ";".join(fl_)
        try:
            tg = float(json.loads(c["params"]).get("tgt_r", 0.0 if c["fam"] == "tod_drift" else 2.0))
        except Exception:
            tg = float("nan")
        row["comp_oco"] = int(c["fam"] not in OCO_FAMS)          # Apex: no OCO / both-side orders (1 = compliant)
        row["comp_target"] = int(tg == tg and tg >= 0.2)         # Apex: stop <= 5x target needs a target with tgt_r >= 0.2
        row["apex_compliant"] = row["comp_oco"] * row["comp_target"]
        # Apex PA 30% negative-P&L (MAE) rule, proxy: share of the config's trades whose worst open loss at the chosen size reaches the $750 floor
        # (30% x max(start-of-day profit, $2,500 DD)); the compliance gate wants this share <= 2%. Threshold-as-stop proxy: a day_stop >= $2,000.
        try:
            tt_ = A2.load_src(c["src"])
            mk = tt_.sess == E.SESS_CODE[sess]
            row["mae750_share"] = float((tt_.mae[mk] * row["micros"] / 10.0 >= 750.0).mean()) if mk.any() else float("nan")
        except Exception:
            row["mae750_share"] = float("nan")
        row["apex_mae_ok"] = int(row["mae750_share"] <= 0.02)
        row["apex_thr_stop"] = int(row["day_stop"] >= 2000)
        for mname, key_ in (("wf_p3", 3), ("wf_p2", 2)):
            w = wf.get((grid, sess, WF_FIRM[firm]))
            if not w:
                continue
            wp, we = w.get((key_, prim)), w.get((key_, "eod"))
            if wp or we:
                row["wf_source"] = f"pass{key_}"
                if wp:
                    row["wf_oos_p5"], row["wf_oos_lift"], row["wf_is_p5"] = fl(wp["oos_p5"]), fl(wp.get("oos_lift")), fl(wp["is_p5"])
                    row["wf_oos_ci_lo"], row["wf_oos_ci_hi"] = fl(wp["oos_ci_lo"]), fl(wp["oos_ci_hi"])
                    row["wf_survive"], row["wf_survive_strict"] = wp.get("survive", ""), wp.get("survive_strict", "")
                if we:
                    row["wf_oos_eod_p5"], row["wf_oos_eod_lift"] = fl(we["oos_p5"]), fl(we.get("oos_lift"))
                row["wf_n_cfg"], row["wf_model"] = (wp or we)["n_cfg"], prim if wp else "eod"
                break
        out.append(row)
    return out


def write_csv(path, rows):
    cols = []
    for r in rows:
        cols += [c for c in r if c not in cols]
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: (round(r[c], 6) if isinstance(r.get(c), float) else r.get(c, "")) for c in cols})


def p3(x):
    return f"{x:.2f}".lstrip("0") if x == x else "nan"


def cid(r):
    return f"{r['fam']}/{r['key'].replace('hm2-', '').replace('hm-', '').replace('screen-', 's-').split('-tf')[-1] if False else r['key']}|{r['sess']}"


def short(r):
    k = r["key"].replace("hm2-", "").replace("hm-", "h-").replace("screen-", "s-")
    return f"{k}|{r['sess']}"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", default="a3p3_rules.csv")
    ap.add_argument("--rows2", default="a3p3_rescore2.csv" if E.PL.NAME == "nq" else "a3p3s_rules.csv")
    ap.add_argument("--null", default="a3p3_null.csv")
    ap.add_argument("--null2", default="" if E.PL.NAME == "nq" else "a3p3s_null.csv")
    a = ap.parse_args(argv)
    rows = rd(a.rows) + rd(a.rows2)
    null = rd(a.null) + (rd(a.null2) if a.null2 else [])
    ns = null_stats(null)
    cand = build(rows, null, wf_index(), fees(), ns)
    cand.sort(key=lambda r: (FIRMS5.index(r["firm"]), -r["p5"], -r["p3"]))
    write_csv(OUT / "candidates.csv", cand)
    print(f"candidates.csv: {len(cand)} rows ({sum(1 for r in cand if r['pass'] == 3)} pass 3, {sum(1 for r in cand if r['pass'] == 2)} pass 2)")
    write_summary(cand, rows, null, ns, a)


def write_summary(cand, rows, null, ns, a):
    L = []
    is2 = lambda r: r.get("pass2") == "1" or r.get("screen") == "1"
    n3 = len({(r["key"], r["sess"]) for r in rows if not is2(r)})
    n2 = len({(r["key"], r["sess"]) for r in rows if is2(r)})
    cells = {"lucid": 768, "lucidpro": 576, "lucidpro_nodll": 576, "apex": 960, "apex_eod": 720}
    R_ = E.PL.ROOT
    if R_ == "NQ":
        hdr = "# A3 pass 3: new heat-maps hm2-* (16 family grids + tod_drift tf15/30) and fp-* (fast-pass pts stops x small targets), 2021-09-22..2024-12-31 in-sample"
        cfgs = f"Configs (>=300 tr; hm2 also net>0 at 1 NQ, fp not): {n3} pass-3 + {n2} pass-2 shortlist re-scored; "
    else:
        hdr = (f"# A3 pass 3 ({R_}): tuned heat-maps hm-* (13 family x tf grids) and fast-pass fp-* (pts stops x small targets), plus the {R_} screen configs re-scored "
               f"(a3p3s), 2021-09-22..2024-12-31 in-sample")
        cfgs = f"Configs (>=300 tr, ALL incl. net<=0 at 1 {R_}): {n3} tuned/fast-pass + {n2} screen; "
    L.append(hdr)
    L.append(cfgs + f"rule cells per config {sum(cells.values())} ({'+'.join(str(v) for v in cells.values())}) x 3 breach models; "
             f"null {len({(r['key'], r['sess']) for r in null})} pseudo-configs (5 firms x 5 cellsets each; fp/atr/tod pool groups). Primary model: Lucid* realized, Apex* intraday; eod = optimistic bound. APEX both sets UNCONFIRMED.")
    L.append("Edge lift vs day-matched random (K=10, identical rules) = WARNING LABEL, not a filter. flags: NET<=0, ONE_YEAR (>60% of 1-contract net in one year), NEAREST_POOL, NO_EDGE_VS_RANDOM (lift <= null p95), COST_RULE_FAIL.")
    L.append("## Null (zero-edge random pseudo-configs, stable-cell optimum): P5 at each model's own stable cell, P1 / P3 at the primary-model speed cells: mean / p95 / max (lift p95)")
    for f in FIRMS5:
        prim = E.primary_model(f)
        parts = []
        for m, lab in (("p5_eod", "P5eod"), ("p5_realized", "P5rlz"), ("p5_intraday", "P5int"), ("p1", f"P1{prim[:3]}"), ("p3", f"P3{prim[:3]}")):
            xs = [v for (ff, g, mm), v in ns.items() if ff == f and mm == m]
            if xs:
                n = sum(v["n"] for v in xs)
                mean = np.average([v["mean"] for v in xs], weights=[v["n"] for v in xs])
                parts.append(f"{lab} {p3(mean)}/{p3(np.mean([v['p95'] for v in xs]))}/{p3(max(v['max'] for v in xs))}({p3(np.mean([v['lift_p95'] for v in xs]))})")
        L.append(f"{NAME[f]} n={n if xs else 0}: " + " ; ".join(parts))
    L.append("## Best in-sample per firm (primary model; [eod|intraday] bounds). P1 = speed cell max P(pass<=1d), P3 = speed cell max P(pass<=3d), P5 = P5-stable cell")
    for f in FIRMS5:
        cf = [r for r in cand if r["firm"] == f]
        if not cf:
            continue
        b5 = max(cf, key=lambda r: r["p5"])
        b1 = max((r for r in cf if "sp1_p1" in r), key=lambda r: r["sp1_p1"])
        b3 = max((r for r in cf if "sp3_p3" in r), key=lambda r: r["sp3_p3"])
        L.append(f"{NAME[f]}: P1 {p3(b1['sp1_p1'])} [{p3(b1['sp1_eod_p1'])}|{p3(b1['sp1_intr_p1'])}] bust5 {p3(b1['sp1_bust5'])} {short(b1)} {b1['sp1_rules']} lift {b1['sp1_lift_p1']:+.2f} | "
                 f"P3 {p3(b3['sp3_p3'])} [{p3(b3['sp3_eod_p3'])}|{p3(b3['sp3_intr_p3'])}] {short(b3)} {b3['sp3_rules']} lift {b3['sp3_lift_p3']:+.2f} | "
                 f"P5 {p3(b5['p5'])} [{p3(b5['eod_p5'])}|{p3(b5['intr_p5'])}] {short(b5)} bust5 {p3(b5['bust5'])} lift {b5['lift_p5']:+.2f} {b5['flags']}")
    L.append("## Fast-pass structures (fp-*: pts stop x small target, both directions) vs null: best real P1 / P3 / P5 (primary) vs null mean/p95/max of the same fp-pool group; expectancy/trade after costs at the chosen size")
    for f in FIRMS5:
        cf = [r for r in cand if r["firm"] == f and r["pass"] == 3 and r["key"].startswith("fp-")]
        if not cf:
            continue
        b1 = max((r for r in cf if "sp1_p1" in r), key=lambda r: r["sp1_p1"])
        b3 = max((r for r in cf if "sp3_p3" in r), key=lambda r: r["sp3_p3"])
        b5 = max(cf, key=lambda r: r["p5"])
        nn = {m: nstat(ns, f, "fp", m) for m in ("p1", "p3", f"p5_{E.primary_model(f)}")}
        g = lambda m: f"{p3(nn[m]['mean'])}/{p3(nn[m]['p95'])}/{p3(nn[m]['max'])}" if nn[m] else "na"
        pr = E.primary_model(f)
        L.append(f"{NAME[f]} (n={len(cf)}): P1 {p3(b1['sp1_p1'])} vs null {g('p1')} ({short(b1)} {b1['sp1_rules']}, net<=0 {'Y' if b1['net_1nq'] <= 0 else 'N'}) | "
                 f"P3 {p3(b3['sp3_p3'])} vs {g('p3')} ({short(b3)}) | P5 {p3(b5['p5'])} vs {g('p5_' + pr)} ({short(b5)}, exp ${b5['exp_at_micros']:+.0f}/tr @m{b5['micros']}, lift {b5['lift_p5']:+.2f}, {b5['flags']})")
    L.append("## Top 8 per firm by primary-model P5 (one per family grid x session; Apex firms: Apex-compliant only = no OCO family, target tgt_r>=0.2): id | rules | P1/P3/P5 [P5 CI] bust5 | eod P5 | intr P5 | lift | WF OOS P5 (lift) | flags")
    for f in FIRMS5:
        seen, top = set(), []
        for r in (x for x in cand if x["firm"] == f and (f not in UNCONF or x["apex_compliant"])):
            k = (r["grid"], r["sess"])
            if k in seen:
                continue
            seen.add(k)
            top.append(r)
            if len(top) == 8:
                break
        for r in top:
            wf = f" WF {p3(r['wf_oos_p5'])}({r['wf_oos_lift']:+.2f})" if "wf_oos_p5" in r and r.get("wf_oos_p5") == r.get("wf_oos_p5") else ""
            L.append(f"{ABBR[f]} {short(r)} {r['rules']} | {p3(r['p1'])}/{p3(r['p3'])}/{p3(r['p5'])} [{p3(r['p5_ci_lo'])},{p3(r['p5_ci_hi'])}] b{p3(r['bust5'])} | {p3(r['eod_p5'])} | {p3(r['intr_p5'])} | {r['lift_p5']:+.2f}{wf} | {r['flags']}" + (f" | mae750 {r['mae750_share']:.0%}{' THR_STOP' if r['apex_thr_stop'] else ''}" if f in UNCONF else ""))
    L.append(f"## Positive-expectancy bias (funded use): best primary P5 among configs with net > 0 at 1 {E.PL.ROOT} (before rules), one per family/tf/session; exp = $/trade after costs at the chosen size")
    for f in FIRMS5:
        seen, top = set(), []
        for r in (x for x in cand if x["firm"] == f and x["net_1nq"] > 0 and (f not in UNCONF or x["apex_compliant"])):
            k = (r["fam"], r["tf"], r["sess"])
            if k in seen:
                continue
            seen.add(k)
            top.append(r)
            if len(top) == 3:
                break
        L.append(f"{ABBR[f]}: " + " | ".join(f"{short(r)} {r['rules']} P5 {p3(r['p5'])} [eod {p3(r['eod_p5'])} intr {p3(r['intr_p5'])}] net1 ${r['net_1nq']:+.0f} exp ${r['exp_at_micros']:+.0f}/tr lift {r['lift_p5']:+.2f}" for r in top))
    L.append("## Offline walk-forward (top-12 family-grid x session sets per firm, quarterly re-selection on trailing 12m; eod / primary model; OOS lift vs same-procedure random controls)")
    for f in FIRMS5:
        w = [r for r in rd("wf_offline_p3.csv") if r["firm"] == WF_FIRM[f]]
        pr = E.primary_model(f)
        wp, we = [r for r in w if r["model"] == pr], [r for r in w if r["model"] == "eod"]
        if wp:
            b = max(wp, key=lambda r: fl(r["oos_p5"]))
            L.append(f"{ABBR[f]} {pr}: median OOS P5 {p3(np.median([fl(r['oos_p5']) for r in wp]))} (IS {p3(np.median([fl(r['is_p5']) for r in wp]))}), lift>0 {sum(fl(r['oos_lift']) > 0 for r in wp)}/{len(wp)}, "
                     f"lift CI>0 {sum(r['survive_strict'] == '1' for r in wp)}; median IS->OOS drop {np.median([fl(r['drop']) for r in wp]):+.3f}; eod median OOS P5 {p3(np.median([fl(r['oos_p5']) for r in we]))}; best {b['grid'].replace('hm2-', '')}/{b['sess']} OOS {p3(fl(b['oos_p5']))} ({fl(b['oos_lift']):+.2f})")
    am = rd("a3p3_apexmae.csv")
    if am:
        L.append("## Apex MAE-cut compliance bound (UNCONFIRMED): size capped so <= 2% of trades reach the $750 PA negative-P&L floor; top Apex-compliant configs re-searched (a3p3_apexmae.py)")
        for f in ("apex", "apex_eod"):
            xs = [r for r in am if r["firm"] == f and r.get("intraday_p5_stable") not in (None, "")]
            if xs:
                b = max(xs, key=lambda r: fl(r["intraday_p5_stable"]))
                L.append(f"{ABBR[f]}: {len(xs)} configs, unrestricted best P5 {p3(max(fl(r['free_p5']) for r in xs))} -> MAE-compliant stable P5 median {p3(np.median([fl(r['intraday_p5_stable']) for r in xs]))} / max {p3(fl(b['intraday_p5_stable']))} "
                         f"({b['key']}|{b['sess']}, size <= {b['m_max']} micros; P1 max {p3(max(fl(r['p1_rawmax']) for r in xs))}); at the unrestricted sizes {p3(np.median([fl(r['free_mae750']) for r in xs]))} (median) of trades hit the floor -> Apex is not workable on ES at eval size.")
    wfj = E.PL.DIR / "wf_es.jsonl"
    if wfj.exists():
        ks = [json.loads(x)["key"] for x in wfj.read_text().splitlines() if x.strip()]
        L.append(f"## Tester walk-forwards submitted via hb.py ({len(ks)}/15, ES cap): " + ", ".join(k.replace("wf-", "") for k in ks))
    L.append("Notes: Lucid Flex needs >=2 trading days (consistency cushion) so P1 is structurally 0; P1/P3 cells maximise speed and often carry bust5 >= .5; WF = top-12 family-grid x session sets per firm of the tuned grids + screen configs (one-config grids). "
             "WF lift CAVEAT: controls use the grid's FIRST member exit profile (an fp grid = 3-pt stop x 0.25R target, control P5 ~0; hm grids = stop 1 ATR x 0.5R), so multi-cell/fp lifts (+0.3..+0.4) are inflated: read OOS P5 and the IS->OOS drop; the in-sample lift (K=10 matched controls) is the edge label.")
    (OUT / "a3p3_summary.md").write_text("\n".join(L) + "\n")
    print(f"a3p3_summary.md: {len(L)} lines")


if __name__ == "__main__":
    main()
