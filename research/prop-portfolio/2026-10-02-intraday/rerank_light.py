#!/usr/bin/python3
"""Light (single-process) stages of rerank.py: tables, second look, desk algos, summary. Run through rerank.py:
    /usr/bin/python3 rerank.py --stage eval|wf_agg|funded_agg|second|desk|summary|light
Reads R's stored outputs (R/out/*.csv, *.json) and this directory's checkpoints; writes only into ./out.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import csv                              # noqa: E402
import datetime as dt                   # noqa: E402
import json                             # noqa: E402
import zlib                             # noqa: E402
from collections import defaultdict     # noqa: E402
from pathlib import Path                # noqa: E402
from types import SimpleNamespace       # noqa: E402

import numpy as np                      # noqa: E402

RR = None        # the rerank module (set by run)


def _bind(mod):
    global RR, S, E, F, P, A1, A2, A3, FS, WF, ROUT, OUT
    RR = mod
    S, E, F, P, A1, A2, A3, FS, WF, ROUT, OUT = mod.S, mod.E, mod.F, mod.P, mod.A1, mod.A2, mod.A3, mod.FS, mod.WF, mod.ROUT, mod.OUT


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def wcsv(path, rows, first=()):
    cols = list(first)
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {path.name}", flush=True)


def jdump(path, o):
    def d(x):
        if isinstance(x, np.integer):
            return int(x)
        if isinstance(x, np.floating):
            return float(x)
        if isinstance(x, np.ndarray):
            return x.tolist()
        return str(x)
    Path(path).write_text(json.dumps(o, indent=1, default=d))


def manifest():
    return json.loads((ROUT / "holdout_manifest.json").read_text())


# ------------------------------------------------------------------ 1-NQ raw stats of every config (net, PF, t)

def cfg_stats():
    """{(key, sess): dict(trades, net, exp, pf, t, wr, sig)} per 1 NQ on the in-sample window, from R's bundles (cached in out/cfg_stats.json;
    only the missing (key, sess) are computed). sig = crc32 of every entry time + side of the session's trades: two configs with the same
    sig take exactly the same entries (RR.top_eval / top_funded use it so one trade is never listed twice)."""
    cf = OUT / "cfg_stats.json"
    out = {tuple(k.split("|")): v for k, v in json.loads(cf.read_text()).items()} if cf.exists() else {}
    want = defaultdict(set)
    for r in RR.read_rules():
        if "sig" not in out.get((r["key"], r["sess"]), {}):
            want[r["key"]].add(r["sess"])
    if not want:
        return out
    srcs = {s[3]: s for s in A3.sources3()}
    srcs.update({s[3]: s for s in A3.sources2()})
    for i, (key, sesss) in enumerate(sorted(want.items())):
        t = A2.load_src(srcs[key][0])
        for sess in sesss:
            m = t.sess == E.SESS_CODE[sess]
            x = t.net[m]
            n = len(x)
            pos, neg = float(x[x > 0].sum()), float(-x[x < 0].sum())
            sd = float(x.std(ddof=1)) if n > 1 else float("nan")
            out[(key, sess)] = dict(trades=n, net=float(x.sum()), exp=float(x.mean()) if n else None, pf=(pos / neg) if neg > 0 else None,
                                    t=(float(x.mean()) / (sd / np.sqrt(n))) if n > 1 and sd > 0 else None, wr=float((x > 0).mean()) if n else None,
                                    sig=int(zlib.crc32(t.te[m].astype(np.int64).tobytes() + t.side[m].astype(np.int64).tobytes())))
        if i % 100 == 0:
            print(f"cfg_stats {i}/{len(want)}", flush=True)
    jdump(cf, {"|".join(k): v for k, v in out.items()})
    return out


# ------------------------------------------------------------------ eval + null

EVAL_FIRST = ("firm", "rank", "top10", "key", "fam", "tf", "sess", "params", "trades", "net_1nq", "exp_1nq", "pf_1nq", "t_1nq", "med_stop_pts",
              "micros", "day_lock", "day_take", "day_stop", "max_day_tr", "target_take", "stab_intraday_p5", "raw_max_intraday_p5",
              "intraday_p1", "intraday_p2", "intraday_p3", "intraday_p5", "intraday_bust5", "intraday_med", "intraday_ci_lo", "intraday_ci_hi",
              "realized_p1", "realized_p3", "realized_p5", "realized_bust5", "eod_p5", "eod_bust5",
              "ctrl_intraday_p5", "lift_intraday_p5", "ctrl_u_intraday_p5", "lift_u_intraday_p5", "beats_u", "K_u", "max_tr_day", "null_p5_mean", "null_p5_p95", "null_p5_max", "null_lift_p95", "lift_above_null_p95",
              "p5_above_null_max", "passes_60", "any_cell_60", "fee", "evals_per_funded", "cost_per_funded", "holdout_bundle", "pass", "source", "same_trade",
              "fastpass", "pool_flag",
              "net_rules", "exp_at_micros", "p5_2022", "p5_2023", "p5_2024")


def null_ref():
    """Zero-edge reference per firm from R's 407 random pseudo-configs (same intraday-optimised stable-cell search)."""
    by = defaultdict(list)
    for r in csv.DictReader((ROUT / "a3p3_null.csv").open()):
        if r["cellset"] == "p5_intraday":
            by[r["firm"]].append(r)
    ref = {}
    for f, rs in by.items():
        p5 = np.array([fnum(r["intraday_p5"]) for r in rs])
        st = np.array([fnum(r["stab"]) for r in rs])
        lf = np.array([fnum(r["lift_intraday_p5"]) for r in rs])
        ref[f] = dict(n=len(rs), p5_mean=float(p5.mean()), p5_p95=float(np.percentile(p5, 95)), p5_max=float(p5.max()),
                      stab_mean=float(st.mean()), stab_p95=float(np.percentile(st, 95)), stab_max=float(st.max()),
                      lift_p95=float(np.nanpercentile(lf, 95)), lift_mean=float(np.nanmean(lf)),
                      bust_mean=float(np.mean([fnum(r["intraday_bust5"]) for r in rs])))
    return ref


CEILING = {  # driftless walk, no costs: P(reach the pass before the max loss)
    "lucid": (16 / 49, "Flex: 2 days minimum and no day > 50% of profit -> twice +$1,500 before -$2,000 = (4/7)^2 = 33%"),
    "lucidpro": (0.40, "Pro: +$3,000 before -$2,000 = 2000 / 5000 = 40% (the $1,200 daily limit only slows it)"),
    "lucidpro_nodll": (0.40, "Pro noDLL: +$3,000 before -$2,000 = 40%"),
    "apex": (0.40, "user set: +$3,000 before -$2,000 = 40%"),
    "apex_eod": (0.40, "+$3,000 before -$2,000 = 40%"),
}


def p2_reference(tops):
    """R's own pass-2 intraday rows (a3p2_rules.csv / a3p2_lucidpro.csv, model intraday): (a) check of the extension rows computed here against
    them, (b) the pass-2 configs still NOT ranked (net <= 0 at 1 NQ: R's candidate filter) -> their best stored intraday P5 per firm and how
    many of them have a stored stable P5 above the firm's 10th listed pick."""
    ext = {(r["key"], r["sess"], r["firm"]): r for r in RR.jl(OUT / "eval_p2x_part.jsonl")}
    left = RR.p2x_keys(False).keys() - RR.p2x_keys().keys()
    tenth = {f: t[-1]["stab_intraday_p5"] for f, t in tops.items()}
    worst, n, mx, mst, above = 0.0, 0, defaultdict(float), defaultdict(float), defaultdict(int)
    for fn in ("a3p2_rules.csv", "a3p2_lucidpro.csv"):
        for r in csv.DictReader((ROUT / fn).open()):
            if r["model"] != "intraday":
                continue
            k = (r["key"], r["sess"], r["firm"])
            if k in ext:
                n += 1
                worst = max(worst, abs(fnum(r["st_p5"]) - fnum(ext[k]["intraday_p5"])), abs(fnum(r["st_stab_med"]) - fnum(ext[k]["stab"])))
            elif k[:2] in left:
                mx[r["firm"]] = max(mx[r["firm"]], fnum(r["rw_p5"]))
                mst[r["firm"]] = max(mst[r["firm"]], fnum(r["st_stab_med"]))
                above[r["firm"]] += int(fnum(r["st_stab_med"]) > tenth.get(r["firm"], 9.0))
    return dict(ext_rows_checked=n, ext_max_abs_diff_vs_R_pass2=worst, not_ranked=len(left), not_ranked_why="net <= 0 at 1 NQ (R's candidate filter)",
                not_ranked_max_any_cell_p5=dict(mx), not_ranked_max_stable_p5=dict(mst), not_ranked_above_10th={f: above[f] for f in mx})


def stage_eval():
    rows = RR.read_rules()
    st = cfg_stats()
    sigs = {k: v["sig"] for k, v in st.items()}
    ref = null_ref()
    ho = set(manifest()["configs"])
    lift_u = {(r["kind"], r["key"], r["sess"], r["fv"]): r for r in RR.jl(OUT / "lift_u.jsonl")}
    out, tops = [], {}
    for f in RR.FIRMS5:
        top = RR.top_eval(rows, f, sigs=sigs)
        topk = {(r["key"], r["sess"]) for r in top}
        rs = sorted((r for r in rows if r["firm"] == f), key=lambda r: (-fnum(r["stab"]), -fnum(r["intraday_p5"]), r["key"]))
        nr = ref[f]
        prim_intr = E.primary_model(f) == "intraday"
        fee = RR.FEE.get(f)
        for i, r in enumerate(rs, 1):
            s = st[(r["key"], r["sess"])]
            p5 = fnum(r["intraday_p5"])
            o = dict(firm=f, rank=i, top10=int((r["key"], r["sess"]) in topk), key=r["key"], fam=r["fam"], tf=r["tf"], sess=r["sess"], params=r["params"],
                     trades=int(float(r["trades"])), net_1nq=fnum(r["net_1nq"]), exp_1nq=fnum(r["exp_1nq"]), pf_1nq=s["pf"], t_1nq=s["t"],
                     med_stop_pts=fnum(r["med_stop_pts"]), stab_intraday_p5=fnum(r["stab"]), raw_max_intraday_p5=fnum(r["raw_max"]),
                     intraday_ci_lo=fnum(r["ci_p5_lo" if prim_intr else "ci_intraday_p5_lo"]),
                     intraday_ci_hi=fnum(r["ci_p5_hi" if prim_intr else "ci_intraday_p5_hi"]),
                     null_p5_mean=nr["p5_mean"], null_p5_p95=nr["p5_p95"], null_p5_max=nr["p5_max"], null_lift_p95=nr["lift_p95"],
                     lift_above_null_p95=int(fnum(r["lift_intraday_p5"]) > nr["lift_p95"]), p5_above_null_max=int(p5 > nr["p5_max"]),
                     passes_60=int(p5 >= RR.CRITERION), any_cell_60=int(fnum(r["raw_max"]) >= RR.CRITERION), fee=fee,
                     evals_per_funded=(1 / p5) if p5 > 0 else None, cost_per_funded=(fee / p5) if fee and p5 > 0 else None,
                     holdout_bundle=int(r["key"] in ho), source="pass-2 extension (this run)" if r.get("p2x") else "pilot pass 2 (rescored)" if r["pass2"] else "pilot pass 3",
                     same_trade=";".join(r.get("same_trade", [])), **{"pass": 2 if r["pass2"] else 3})
            for k in ("micros", "day_lock", "day_take", "day_stop", "max_day_tr", "target_take"):
                o[k] = int(float(r[k]))
            for k in ("intraday_p1", "intraday_p2", "intraday_p3", "intraday_p5", "intraday_bust5", "intraday_med", "realized_p1", "realized_p3",
                      "realized_p5", "realized_bust5", "eod_p5", "eod_bust5", "ctrl_intraday_p5", "lift_intraday_p5", "net_rules", "exp_at_micros",
                      "p5_2022", "p5_2023", "p5_2024"):
                o[k] = fnum(r[k])
            o["fastpass"], o["pool_flag"] = r.get("fastpass"), r.get("pool_flag")
            out.append(o)
        tops[f] = [o for o in out if o["firm"] == f and o["top10"]]
        for o in tops[f]:          # the reported picks against the UNBIASED day-matched control (rerank.py --stage lift with RR_CTRL=overlap), replicate by replicate
            x = lift_u.get(("eval", o["key"], o["sess"], f))
            if x and abs(x["own"] - o["intraday_p5"]) < 1e-6:          # R's CSV stores 6 decimals
                o.update(ctrl_u_intraday_p5=x["ctrl"], lift_u_intraday_p5=x["lift"], beats_u=x["beats"], K_u=x["K"], max_tr_day=x["max_tr_day"])
        fo = [o for o in out if o["firm"] == f]
        print(f"{f}: {len(fo)} configs; best stable intraday P5 {tops[f][0]['stab_intraday_p5']:.3f} (own {tops[f][0]['intraday_p5']:.3f}); own P5 >= 60%: "
              f"{sum(o['passes_60'] for o in fo)}; any cell >= 60%: {sum(o['any_cell_60'] for o in fo)}; max own P5 {max(o['intraday_p5'] for o in fo):.3f}; "
              f"max any cell {max(o['raw_max_intraday_p5'] for o in fo):.3f}; top-10 from the extension: {sum(1 for o in tops[f] if o['source'].startswith('pass-2 ext'))}; "
              f"twins dropped from the top 10: {sum(len(o['same_trade'].split(';')) for o in tops[f] if o['same_trade'])}; "
              f"null mean/p95/max {nr['p5_mean']:.3f}/{nr['p5_p95']:.3f}/{nr['p5_max']:.3f}", flush=True)
    wcsv(OUT / "eval_intraday.csv", out, EVAL_FIRST)
    cfgs = {(r["key"], r["sess"]) for r in rows}

    def mx(f, k):
        return max(o[k] for o in out if o["firm"] == f)
    jdump(OUT / "eval_top.json", {"top": tops, "null": ref, "ceiling": {k: {"p": v[0], "why": v[1]} for k, v in CEILING.items()},
                                  "n_configs": len(cfgs), "n_pilot": len({(r["key"], r["sess"]) for r in rows if not r.get("p2x")}),
                                  "n_ext": len({(r["key"], r["sess"]) for r in rows if r.get("p2x")}),
                                  "grids": {f: A2.GR[f] for f in RR.FIRMS5},
                                  "max_raw": {f: mx(f, "raw_max_intraday_p5") for f in RR.FIRMS5}, "max_own": {f: mx(f, "intraday_p5") for f in RR.FIRMS5},
                                  "n_own_60": {f: sum(o["passes_60"] for o in out if o["firm"] == f) for f in RR.FIRMS5},
                                  "n_any_cell_60": {f: sum(o["any_cell_60"] for o in out if o["firm"] == f) for f in RR.FIRMS5},
                                  "p2_reference": p2_reference(tops)})


# ------------------------------------------------------------------ verification of the stored rows

def stage_verify_agg():
    new = {(r["key"], r["sess"], r["firm"]): r for r in RR.jl(OUT / "verify_part.jsonl")}
    old = {(r["key"], r["sess"], r["firm"]): r for r in RR.read_rules()}
    keys = ("micros", "day_lock", "day_take", "day_stop", "max_day_tr", "target_take", "stab", "intraday_p1", "intraday_p3", "intraday_p5",
            "intraday_bust5", "realized_p5", "eod_p5", "lift_intraday_p5")
    worst, bad = 0.0, []
    for k, r in new.items():
        o = old[k]
        for c in keys:
            d = abs(fnum(r[c]) - fnum(o[c]))
            worst = max(worst, d)
            if d > 1e-6:      # R's CSV stores 6 decimals
                bad.append((k, c, r[c], o[c]))
    res = dict(n=len(new), max_abs_diff=worst, mismatches=len(bad), examples=bad[:10])
    jdump(OUT / "verify.json", res)
    print("verify:", res, flush=True)
    return res


# ------------------------------------------------------------------ walk-forward table

def grid_tpd(recs):
    """{(grid, sess): most trades on one day over the grid's members} (cached in out/wf_grid_max_trades_per_day.json). 1 = one trade a day:
    R's day-matched control is exact there; above 1 its no-overlap test biases it (see rerank.py, control switch)."""
    cf = OUT / "wf_grid_max_trades_per_day.json"
    d = {tuple(k.split("|")): v for k, v in json.loads(cf.read_text()).items()} if cf.exists() else {}
    srcs = None
    for (g, s, f), o in recs.items():
        if (g, s) not in d:
            if srcs is None:
                srcs = {x[3]: x for x in A3.sources3()}
                srcs.update({x[3]: x for x in A3.sources2()})
            d[(g, s)] = RR.max_trades_per_day([srcs[k] for k in o["members"]], s)
    jdump(cf, {"|".join(k): v for k, v in d.items()})
    return d


def wf_records():
    """{(grid, sess, firm): dict(o=task record with VALID control replicates only, src=label, ctrl=why the control is valid or '' when it is not,
    pilot=the record as stored)} for the Lucid firms, intraday model. A control is valid when (a) every member's control comes from its own
    exit-profile pool (this run's task_wf, or a one-config grid of R's) AND (b) it is unbiased: the grid trades once a day (R's draw is exact)
    or its control replicates were re-drawn without the overlap test (wf_intraday_u_part.jsonl, RR_CTRL=overlap)."""
    raw = {}
    for ln in (ROUT / "wf_offline_part.jsonl").read_text().splitlines():
        if ln.strip():
            o = json.loads(ln)["rows"][0]
            if o["firm"] in RR.LUCID and "intraday" in o.get("models", WF.MODELS):
                raw[(o["grid"], o["sess"], o["firm"])] = (o, "R: pass-2 grid (wf_offline)", len(o["members"]) == 1)
    for fn, lab in (("wf_intraday_part.jsonl", "new: pass-3 grid"), ("wf_intraday_p2_part.jsonl", "new: the pilot's pass-2 grid re-walked"),
                    ("wf_intraday_p2_part_b.jsonl", "new: the pilot's pass-2 grid re-walked")):
        fp = OUT / fn
        for ln in (fp.read_text().splitlines() if fp.exists() else []):
            if ln.strip():
                o = json.loads(ln)["rows"][0]
                raw[(o["grid"], o["sess"], o["firm"])] = (o, lab, True)
    un = {}
    fp = OUT / "wf_intraday_u_part.jsonl"
    for ln in (fp.read_text().splitlines() if fp.exists() else []):
        if ln.strip():
            o = json.loads(ln)["rows"][0]
            un[(o["grid"], o["sess"], o["firm"])] = o
    tpd = grid_tpd({k: v[0] for k, v in raw.items()})
    recs = {}
    for k, (o, lab, own) in raw.items():
        real = o["reps"][0]
        if k in un:
            u = un[k]
            assert [q["test"] for q in u["reps"][0]["intraday"]["q"]] == [q["test"] for q in real["intraday"]["q"]], k      # same real configs, same picks
            ctl, why = u["reps"][1:], "own pool, re-drawn without the overlap test"
        elif own and tpd[(k[0], k[1])] <= 1:
            ctl, why = o["reps"][1:], "own pool, one trade a day (R's draw is exact)"
        else:
            ctl, why = [], ""
        recs[k] = dict(o=dict(o, reps=[real] + ctl, models=["intraday"]), src=lab, ctrl=why, pilot=o, tpd=tpd[(k[0], k[1])], own=own)
    return recs


def stage_wf_agg():
    rows = []
    for k, r in wf_records().items():
        row = next(x for x in WF.agg_task(r["o"]) if x["model"] == "intraday")
        pil = next(x for x in WF.agg_task(dict(r["pilot"])) if x["model"] == "intraday")
        row.update(source=r["src"], ctrl_valid=int(bool(r["ctrl"])), ctrl_kind=r["ctrl"] or ("not used: " + ("first member's pool; " if not r["own"] else "")
                                                                                             + ("more than one trade a day, R's no-overlap draw is biased" if r["tpd"] > 1 else "")).rstrip("; "),
                   max_trades_per_day=r["tpd"], pilot_ctrl_oos_p5=pil.get("ctrl_oos_p5"), pilot_oos_lift=pil.get("oos_lift"))
        rows.append(row)
    for fn, lab in (("wf_offline.csv", "R: pass-2 grids (wf_offline.csv)"), ("wf_offline_p3.csv", "R: pass-3 grids (wf_offline_p3.csv)")):
        for r in csv.DictReader((ROUT / fn).open()):
            if r["model"] == "intraday" and r["firm"] in ("apex", "apex_eod"):          # reference only: R's rows, R's control (not re-checked here)
                r = dict({k: (fnum(v) if k not in ("grid", "fam", "sess", "firm", "model", "is_cfg", "is_rules") else v) for k, v in r.items()}, source=lab)
                r.update(ctrl_valid=0, ctrl_kind="not used: R's control as stored (first member's pool / no-overlap draw)", pilot_ctrl_oos_p5=r.get("ctrl_oos_p5"),
                         pilot_oos_lift=r.get("oos_lift"))
                for k in ("ctrl_oos_p5", "oos_lift", "lift_ci_lo", "lift_ci_hi", "survive", "survive_strict"):
                    r[k] = float("nan")
                rows.append(r)
    order = {f: i for i, f in enumerate(WF.FIRM_NAME.values())}
    rows.sort(key=lambda r: (order[r["firm"]], -r["oos_p5"]))
    wcsv(OUT / "wf_intraday.csv", rows, ("firm", "model", "grid", "sess", "source", "n_cfg", "is_p5", "is_stable", "oos_p5", "oos_ci_lo", "oos_ci_hi", "drop",
                                         "ctrl_oos_p5", "oos_lift", "lift_ci_lo", "lift_ci_hi", "ctrl_valid", "ctrl_kind", "max_trades_per_day", "pilot_ctrl_oos_p5",
                                         "pilot_oos_lift", "survive", "survive_strict", "is_cfg", "is_rules"))
    summ = {}
    for f in order:
        rs = [r for r in rows if r["firm"] == f]
        if not rs:
            continue
        b = rs[0]
        ok = [r for r in rs if r["ctrl_valid"]]
        summ[f] = dict(n=len(rs), oos_p5_median=float(np.median([r["oos_p5"] for r in rs])), oos_p5_best=b["oos_p5"], best=f"{b['grid']}/{b['sess']}",
                       best_ci=[b["oos_ci_lo"], b["oos_ci_hi"]], best_lift=b.get("oos_lift"), best_lift_ci=[b.get("lift_ci_lo"), b.get("lift_ci_hi")],
                       is_p5_median=float(np.median([r["is_p5"] for r in rs])), drop_median=float(np.median([r["drop"] for r in rs])),
                       n_ctrl_valid=len(ok), lift_median=float(np.median([r["oos_lift"] for r in ok])) if ok else None,
                       ctrl_oos_median=float(np.median([r["ctrl_oos_p5"] for r in ok])) if ok else None,
                       ctrl_oos_max=float(np.max([r["ctrl_oos_p5"] for r in ok])) if ok else None,
                       survive=int(sum(r.get("survive", 0) for r in ok)), strict=int(sum(r.get("survive_strict", 0) for r in ok)),
                       n_ge_60=int(sum(r["oos_p5"] >= 0.6 for r in rs)), n_one_trade=int(sum(1 for r in ok if r.get("max_trades_per_day", 9) <= 1)),
                       top5=[dict(grid=r["grid"], sess=r["sess"], oos_p5=r["oos_p5"], lift=r.get("oos_lift"), is_p5=r["is_p5"], strict=r.get("survive_strict")) for r in rs[:5]])
        print(f, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in summ[f].items() if k != "top5"}, flush=True)
    summ["nested"] = wf_nested()
    jdump(OUT / "wf_summary.json", summ)
    return summ


def wf_nested():
    """NESTED eval walk-forward: each test quarter pick the family grid (and, inside it, the config + rules: that part is the stored record) with
    the best TRAINING score across all walked grids of the firm, and take that pick's test-quarter result. No grid is chosen by its own
    out-of-sample result. The same selection is run on the day-matched random controls (replicates 1..5) over the grids whose control is valid
    (own pool and unbiased, see wf_records). Remaining leak: the set of walked grids was itself shortlisted on the full sample (top 12 pass-3
    grids by in-sample P5 + the pilot's 24 pass-2 grids)."""
    recs = wf_records()
    out = {}
    for f in RR.LUCID:
        rs = {k: v["o"] for k, v in recs.items() if k[2] == f}

        def nested(keys, rep):
            fl, picks = [], []
            for j in range(len(WF.QUARTERS)):
                b = max(keys, key=lambda k: (rs[k]["reps"][rep]["intraday"]["q"][j]["score"], k))
                q = rs[b]["reps"][rep]["intraday"]["q"][j]
                fl += q["test"]
                picks.append(dict(q="%dQ%d" % WF.QUARTERS[j], grid=b[0], sess=b[1], cfg=rs[b]["members"][q["cfg"]], rules=q["rules"],
                                  train_p5=q["train_p5"], test_p5=float(np.mean(q["test"])) if q["test"] else None, n_test=len(q["test"])))
            return np.array(fl, float), picks

        allk, okk = sorted(rs), sorted(k for k in rs if len(rs[k]["reps"]) > 1)
        real, picks = nested(allk, 0)
        o = dict(n_grids=len(allk), oos_p5=float(real.mean()), oos_ci=list(E.block_ci([real])[0]), n_starts=int(len(real)), picks=picks,
                 train_p5_mean=float(np.mean([x["train_p5"] for x in picks])))
        if okk:
            r2, _ = nested(okk, 0)
            kc = min(len(rs[k]["reps"]) for k in okk) - 1
            cs = [nested(okk, rep) for rep in range(1, kc + 1)]
            cp = [float(c[0].mean()) for c in cs]
            o.update(n_grids_ctrl=len(okk), oos_p5_ctrl_grids=float(r2.mean()), oos_ci_ctrl_grids=list(E.block_ci([r2])[0]), ctrl_reps=kc,
                     ctrl_oos_p5=float(np.mean(cp)), ctrl_oos_min=float(min(cp)), ctrl_oos_max=float(max(cp)), lift_ctrl_grids=float(r2.mean() - np.mean(cp)),
                     ctrl_picks_rep1=cs[0][1])
        out[f] = o
        print(f"nested eval WF {f}: {o['n_grids']} grids, OOS P5 {o['oos_p5']:.3f} CI {o['oos_ci'][0]:.3f}-{o['oos_ci'][1]:.3f} (train {o['train_p5_mean']:.3f}); "
              f"valid-control grids {o.get('n_grids_ctrl')}: real {o.get('oos_p5_ctrl_grids', float('nan')):.3f} vs random same selection {o.get('ctrl_oos_p5', float('nan')):.3f} "
              f"[{o.get('ctrl_oos_min', float('nan')):.3f}..{o.get('ctrl_oos_max', float('nan')):.3f}]", flush=True)
    return out


def wf_of(rows, firm_name, key, sess):
    """WF row of the family grid x session that contains config `key` (grid = key before '#')."""
    g = key.split("#")[0]
    for r in rows:
        if r["firm"] == firm_name and r["grid"] == g and r["sess"] == sess:
            return r
    return None


# ------------------------------------------------------------------ funded table

def top_funded(rows, v, k=5, cap=2, sigs=None):
    """R's funded_merge.top_list: by the stable score, <= cap per (family, session); the same trade (identical entries, identical result at the
    reported cell) never fills a second slot (sigs = entry signatures, see cfg_stats)."""
    rs = sorted((r for r in rows if r["variant"] == v and r.get("status") == "ok"), key=lambda r: -r["score_e_net_40"])
    out, cnt, seen = [], defaultdict(int), set()
    for r in rs:
        g = (r["fam"], r["sess"])
        sig = (sigs[(r["key"], r["sess"])] if sigs else (g, r["tf"]), r["sess"], round(r["e_net_40"], 1), round(r["p_pay_20"], 4), round(r["e_net_60"], 1))
        if sig in seen or cnt[g] >= cap:
            continue
        seen.add(sig)
        cnt[g] += 1
        out.append(r)
        if len(out) >= k:
            break
    return out


def exp_max_z(n):
    """E[max of n independent standard normals] (asymptotic)."""
    a = np.sqrt(2 * np.log(n))
    return float(a - (np.log(np.log(n)) + np.log(4 * np.pi)) / (2 * a))


def stage_funded_agg():
    s1 = {(r["cid"], r["variant"]): r for r in RR.jl(OUT / "funded_s1.jsonl")}
    s1.update({(r["cid"], r["variant"]): r for r in RR.jl(OUT / "funded_nwf.jsonl")})        # same coarse row (task_s1i) + the pass-2 extension configs
    s2 = {(r["cid"], r["variant"]): r for fn in ("funded_s2.jsonl", "funded_s2b.jsonl") for r in RR.jl(OUT / fn)}
    nul = [r for r in RR.jl(OUT / "funded_null.jsonl") if r.get("status") == "ok"]
    ho = set(manifest()["configs"])
    nref = {}

    def st(x):
        x = np.asarray(x, float)
        return (float(x.mean()), float(np.percentile(x, 95)), float(x.max())) if len(x) else (None, None, None)

    n_univ = len({k[0] for k in s1})
    for v in RR.LV:
        ns = [r for r in nul if r["variant"] == v]
        sc = np.array([r["score_e_net_40"] for r in ns])
        sm, sp, sx = st(sc)
        em, ep, ex = st([r["e_net_40"] for r in ns])
        wm, wp, wx = st([r["wf_oos_e_net_40"] for r in ns if r.get("wf_oos_e_net_40") is not None])
        pm, _, px = st([r["p_pay_40"] for r in ns])
        cs = np.array([r["e_net_40"] for (cid, vv), r in s1.items() if vv == v and r.get("e_net_40") is not None])
        nref[v] = dict(n=len(ns), score_mean=sm, score_sd=float(sc.std(ddof=1)), score_p95=sp, score_max=sx, e40_mean=em, e40_p95=ep, e40_max=ex, p40_mean=pm, p40_max=px,
                       wf_n=sum(1 for r in ns if r.get("wf_oos_e_net_40") is not None), wf_mean=wm, wf_p95=wp, wf_max=wx,
                       # like-for-like reference for a pick that is the best of n_univ configs: the expected best of n_univ INDEPENDENT zero-edge draws
                       # (normal approximation from the 30 pseudo-configs; an upper reference, the real configs are far from independent)
                       n_universe=n_univ, exp_best_of_universe=float(sm + sc.std(ddof=1) * exp_max_z(n_univ)),
                       real_coarse_mean=float(cs.mean()), real_coarse_p95=float(np.percentile(cs, 95)), real_coarse_max=float(cs.max()))
    rows, tops = [], {}
    lift_u = {(r["kind"], r["key"], r["sess"], r["fv"]): r for r in RR.jl(OUT / "lift_u.jsonl")}
    full = list(s2.values())
    cst = cfg_stats()
    sigs = {k: x["sig"] for k, x in cst.items()}
    for v in RR.LV:
        top = top_funded(full, v, sigs=sigs)
        tk = {r["cid"] for r in top}
        rs = sorted((r for r in full if r["variant"] == v and r.get("status") == "ok"), key=lambda r: -r["score_e_net_40"])
        tops[v] = []
        for i, r in enumerate(rs, 1):
            o = dict(variant=v, rank=i, top5=int(r["cid"] in tk), stage="full", cid=r["cid"], key=r["key"], fam=r["fam"], tf=r["tf"], sess=r["sess"],
                     trades=r["trades"], net_1nq=r["net_1nq"], model=r["model"], cell=FS.cellname(r), null_score_p95=nref[v]["score_p95"],
                     above_null_p95=(int(r["score_e_net_40"] > nref[v]["score_p95"]) if nref[v]["score_p95"] is not None else None), null_wf_max=nref[v]["wf_max"],
                     wf_above_null_wf_max=(int(r["wf_oos_e_net_40"] > nref[v]["wf_max"]) if r.get("wf_oos_e_net_40") is not None and nref[v]["wf_max"] is not None else None),
                     holdout_bundle=int(r["key"] in ho), pf_1nq=cst[(r["key"], r["sess"])]["pf"], t_1nq=cst[(r["key"], r["sess"])]["t"],
                     ctrl_pool="nearest" if r.get("pool_flag") else "exact")
            o.update({k: x for k, x in r.items() if k not in o})
            x = lift_u.get(("funded", r["key"], r["sess"], v))
            if x and abs(x["own"] - r["e_net_40"]) < 1e-6:          # unbiased day-matched control at the pick's cell (rerank.py --stage lift, RR_CTRL=overlap)
                o.update(ctrl_u_e40=x["ctrl"], lift_u_e40=x["lift"], beats_u=x["beats"], K_u=x["K"], max_tr_day=x["max_tr_day"])
            rows.append(o)
            if r["cid"] in tk:
                tops[v].append(o)
        for (cid, vv), r in s1.items():
            if vv == v and (cid, v) not in s2 and r.get("e_net_40") is not None:
                rows.append(dict(variant=v, stage="coarse", cid=cid, model=r["model"], cell=r.get("cell"), **{k: r.get(k) for k in FS.MET}))
        b = tops[v][0] if tops[v] else None
        if b:
            print(f"{v}: best stable E$40 {b['score_e_net_40']:.0f} (own {b['e_net_40']:.0f}, rules-only WF {b.get('wf_oos_e_net_40')}) {b['cid']} {b['cell']}; "
                  f"null score mean/p95/max {nref[v]['score_mean']:.0f}/{nref[v]['score_p95']:.0f}/{nref[v]['score_max']:.0f}, expected best of {n_univ} independent "
                  f"zero-edge draws {nref[v]['exp_best_of_universe']:.0f}; n full {len(rs)}", flush=True)
    wcsv(OUT / "funded_intraday.csv", rows, ("variant", "rank", "top5", "stage", "cid", "fam", "tf", "sess", "trades", "net_1nq", "model", "cell", "micros", "day_take",
                                             "day_lock", "day_stop", "max_day_tr", "policy", "score_e_net_40", "e_net_40", "e40_ci_lo", "e40_ci_hi", "e_net_60",
                                             "p_pay_20", "p_pay_40", "p_pay_60", "med_days_first", "p_bust_pre_first", "e_cheque_if_paid", "ctrl_e40", "lift_e40", "ctrl_u_e40", "lift_u_e40", "beats_u",
                                             "wf_oos_e_net_40", "wf_oos_p_pay_40", "wf_oos_med_days_first", "wf_oos_p_bust_pre_first", "is_e40_on_test_starts",
                                             "realized_e40", "realized_p40", "eod_e40", "null_score_p95", "above_null_p95", "null_wf_max", "wf_above_null_wf_max",
                                             "holdout_bundle"))
    # rules-only walk-forward summary over each variant's top 10 by the stable score (R's funded_wf convention). NOT out-of-sample for the config:
    # the config was chosen on the whole sample, only its rules cell is re-picked each quarter. The nested walk-forward (nwf_agg) is the honest one.
    wfs = {}
    for v in RR.LV:
        t10 = [r for r in top_funded(full, v, 10, sigs=sigs) if r.get("wf_oos_e_net_40") is not None]
        if t10:
            oo = np.array([r["wf_oos_e_net_40"] for r in t10])
            wfs[v] = dict(n=len(t10), oos_e40_median=float(np.median(oo)), oos_e40_best=float(oo.max()),
                          is_same_starts_median=float(np.median([r["is_e40_on_test_starts"] for r in t10])),
                          oos_p40_median=float(np.median([r["wf_oos_p_pay_40"] for r in t10])),
                          oos_bust_median=float(np.median([r["wf_oos_p_bust_pre_first"] for r in t10])),
                          above_null_wf_max=int(sum(r["wf_oos_e_net_40"] > (nref[v]["wf_max"] or 0) for r in t10)))
    jdump(OUT / "funded_top.json", {"top": tops, "null": nref, "wf_top10": wfs, "n_full": {v: sum(1 for r in full if r["variant"] == v) for v in RR.LV},
                                    "n_universe": n_univ, "grid": {k: (list(x) if x else x) for k, x in F.GRID.items()}})
    return tops, nref, wfs


# ------------------------------------------------------------------ nested funded walk-forward (config + rules re-picked each quarter)

def spearman(x, y):
    rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y))
    return float(np.corrcoef(rx, ry)[0, 1])


def stage_nwf_agg(top=5):
    """Phase 1 (no out/funded_nwf_ctl.jsonl for the current picks): per account type and test quarter rank every config by its TRAINING score
    (stable E$40 of its best coarse cell on the trailing 12 months) -> out/funded_nwf_picks.json, the jobs of rerank.py --stage nwf_ctl.
    Phase 2: stitch the picks' test quarters (top 1 and the mean of the top `top` distinct trades), block-bootstrap CI, and the same starts for
    the day-matched random controls -> out/funded_nwf.json + out/funded_nwf.csv."""
    recs = RR.jl(OUT / "funded_nwf.jsonl")
    sigs = {k: x.get("sig") for k, x in cfg_stats().items()}
    for c in RR.all_cands():                     # entry signatures of configs that only the funded universe holds
        sigs.setdefault((c["key"], c["sess"]), c["cid"])
    res, jobs, csvrows = {}, defaultdict(list), []
    for v in RR.LV:
        byq = defaultdict(list)
        for r in recs:
            if r["variant"] == v:
                for q in r["q"]:
                    byq[q["q"]].append((r["cid"], q))
        qs, uni_sum, uni_n, rho = [], 0.0, 0, []
        for lab in sorted(byq):
            xs = sorted(byq[lab], key=lambda t: (-t[1]["score"], t[0]))
            uni_sum += sum(q["sum_n40"] for _, q in xs)
            uni_n += sum(q["n_test"] for _, q in xs)
            rho.append(spearman(np.array([q["score"] for _, q in xs]), np.array([q["sum_n40"] / q["n_test"] for _, q in xs])))
            picks, seen = [], set()
            for cid, q in xs:
                key, sess = cid.split("|")
                sg = (sigs[(key, sess)], sess, round(q["sum_n40"], 2), q["n_pay40"])
                if sg in seen:
                    continue
                seen.add(sg)
                picks.append((cid, q))
                if len(picks) >= top:
                    break
            qs.append(dict(q=lab, n_cfg=len(xs), picks=[dict(cid=cid, cell=FS.cellname(q["cd"]), cd=q["cd"], train_score=q["score"], train_e40=q["train_e40"],
                                                             test_e40=q["sum_n40"] / q["n_test"], n_test=q["n_test"], p_pay_40=q["n_pay40"] / q["n_test"],
                                                             p_bust_pre=q["n_bust_pre"] / q["n_test"]) for cid, q in picks],
                           universe_test_e40=float(np.mean([q["sum_n40"] / q["n_test"] for _, q in xs])), rank_corr=rho[-1]))
            for cid, q in picks:
                jobs[cid].append([v, lab, q["cd"]])
        res[v] = dict(quarters=qs, universe_mean_e40=uni_sum / uni_n, rank_corr_mean=float(np.mean(rho)), n_cfg=len({r["cid"] for r in recs if r["variant"] == v}))
    jdump(OUT / "funded_nwf_picks.json", jobs)
    # controls: the unbiased draw (RR_CTRL=overlap -> funded_nwf_ctl_u.jsonl) is the headline; R's own control (no overlap) is kept next to it
    ctl = {(r["cid"], r["variant"], r["q"], r["cell"]): r for r in RR.jl(OUT / "funded_nwf_ctl_u.jsonl")}
    ctl_r = {(r["cid"], r["variant"], r["q"], r["cell"]): r for r in RR.jl(OUT / "funded_nwf_ctl.jsonl")}
    need = {(cid, v, lab, FS.cellname(cd)) for cid, js in jobs.items() for v, lab, cd in js}
    if not (need <= set(ctl) and need <= set(ctl_r)):
        print(f"nwf_agg phase 1: {len(need)} picks written to funded_nwf_picks.json; run `rerank.py --stage nwf_ctl` with and without RR_CTRL=overlap, "
              "then this stage again", flush=True)
        return None
    for v in RR.LV:
        o = res[v]

        def series(k):
            """Per test start (in date order): mean over the first k picks of the quarter of (pick $ in 40 days, control $ in 40 days)."""
            real, con, paid, bust = [], [], [], []
            for q in o["quarters"]:
                rs = [ctl[(p["cid"], v, q["q"], p["cell"])] for p in q["picks"][:k]]
                n = min(len(r["n40"]) for r in rs)
                real += list(np.mean([r["n40"][:n] for r in rs], 0))
                con += list(np.mean([r["ctl_n40"][:n] for r in rs], 0))
                paid += list(np.mean([[1.0 if 0 < f <= 40 else 0.0 for f in r["first"][:n]] for r in rs], 0))
                bust += list(np.mean([[1.0 if (b > 0 and not f > 0) else 0.0 for b, f in zip(r["bust"][:n], r["first"][:n])] for r in rs], 0))
            return np.array(real), np.array(con), float(np.mean(paid)), float(np.mean(bust))

        for k, nm in ((1, "top1"), (top, f"top{top}")):
            real, con, pp, pb = series(k)
            lo, hi = FS.block_ci(real)
            dlo, dhi = FS.block_ci(real - con)
            cr = np.array([x for q in o["quarters"] for x in np.mean([ctl_r[(p["cid"], v, q["q"], p["cell"])]["ctl_n40"][:min(len(ctl_r[(pp_["cid"], v, q["q"], pp_["cell"])]["ctl_n40"]) for pp_ in q["picks"][:k])]
                                                                      for p in q["picks"][:k]], 0)])
            o[nm] = dict(e40=float(real.mean()), ci=[lo, hi], p_pay_40=pp, p_bust_pre=pb, ctrl_e40=float(con.mean()), lift=float((real - con).mean()),
                         lift_ci=[dlo, dhi], n_starts=int(len(real)), train_e40=float(np.mean([p["train_e40"] for q in o["quarters"] for p in q["picks"][:k]])),
                         ctrl_e40_R_no_overlap=float(cr.mean()))
        for q in o["quarters"]:
            for i, pk in enumerate(q["picks"], 1):
                c = ctl[(pk["cid"], v, q["q"], pk["cell"])]
                pk["ctrl_e40"], pk["pool_flag"] = float(np.mean(c["ctl_e40"])), c.get("pool_flag")
                csvrows.append(dict(variant=v, quarter=q["q"], rank=i, cid=pk["cid"], cell=pk["cell"], train_score=pk["train_score"], train_e40=pk["train_e40"],
                                    test_e40=pk["test_e40"], test_ctrl_e40=pk["ctrl_e40"], n_test=pk["n_test"], p_pay_40=pk["p_pay_40"], p_bust_pre=pk["p_bust_pre"],
                                    n_cfg_ranked=q["n_cfg"], universe_test_e40=q["universe_test_e40"], rank_corr_train_test=q["rank_corr"],
                                    ctrl_pool="nearest" if pk["pool_flag"] else "exact"))
        t1, tk = o["top1"], o[f"top{top}"]
        print(f"nested funded WF {v}: {o['n_cfg']} configs, {len(o['quarters'])} quarters; top-1 ${t1['e40']:.0f} (CI {t1['ci'][0]:.0f}..{t1['ci'][1]:.0f}; train ${t1['train_e40']:.0f}) "
              f"vs random same rules ${t1['ctrl_e40']:.0f}; top-{top} ${tk['e40']:.0f} (CI {tk['ci'][0]:.0f}..{tk['ci'][1]:.0f}) vs random ${tk['ctrl_e40']:.0f} "
              f"(lift CI {tk['lift_ci'][0]:.0f}..{tk['lift_ci'][1]:.0f}; R's no-overlap control ${tk['ctrl_e40_R_no_overlap']:.0f}); average config ${o['universe_mean_e40']:.0f}; "
              f"rank corr train->test {o['rank_corr_mean']:+.3f}", flush=True)
    wcsv(OUT / "funded_nwf.csv", csvrows)
    jdump(OUT / "funded_nwf.json", res)
    return res


def run(stage, mod):
    _bind(mod)
    import rerank_light2 as R2
    R2._bind(mod, sys.modules[__name__])
    st = {"eval": stage_eval, "verify_agg": stage_verify_agg, "wf_agg": stage_wf_agg, "funded_agg": stage_funded_agg, "nwf_agg": stage_nwf_agg,
          "second": R2.stage_second, "desk": R2.stage_desk, "ctrl_bias": R2.stage_ctrl_bias, "summary": R2.stage_summary}
    if stage == "light":
        for nm in ("eval", "verify_agg", "wf_agg", "funded_agg", "nwf_agg", "second", "desk", "ctrl_bias", "summary"):
            print(f"=== {nm}", flush=True)
            st[nm]()
        return
    if stage not in st:
        raise SystemExit(f"unknown stage {stage!r}")
    st[stage]()
