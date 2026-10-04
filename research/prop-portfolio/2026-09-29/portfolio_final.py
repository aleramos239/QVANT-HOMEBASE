#!/usr/bin/python3
"""Stage B final: portfolio search on the MERGED candidate pool (out/candidates.csv, passes 2+3) for the 5 firms.

Builds on portfolio.py (engine untouched). Adds: pool builder from candidates.csv, exact member specs, risk-scale curve, day-by-day
pass/bust distribution, news vs non-news P5, member correlation, WF (fixed-set + re-selected variants) on the new pool, merge into
out/portfolio_results.json + out/portfolio_summary.md.

Run: PYTHONPATH=~/ramos-quant-homebase /usr/bin/python3 portfolio_final.py run|wf|multi|merge [--firms ..] [--workers 4] [--obj p5|fast] [--tag _final]
(<= 4 workers; portfolio.gate() pauses every uncached grid evaluation inside 09:18-09:36 ET on weekdays).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E            # noqa: E402
import portfolio as P           # noqa: E402

OUT = P.OUT
CAND = OUT / "candidates.csv"
L3, J3 = OUT / "a3p3_snap_ledger.csv", OUT / "a3p3_snap_jobs.jsonl"
L2, J2 = P.SNAP_L, P.SNAP_J             # pass-2 snapshot (NQ a3p2; ES a3p3s)
SCALES = (0.25, 0.5, 0.75, 1.0, 1.25)
TAG = "_final"
MIXES = {2: {"lucid": 1, "apex": 1},
         3: {"lucid": 1, "lucidpro": 1, "apex": 1},
         4: {"lucid": 2, "lucidpro": 1, "apex": 1},
         5: {"lucid": 2, "lucidpro": 2, "apex": 1},
         6: {"lucid": 2, "lucidpro": 1, "lucidpro_nodll": 1, "apex": 1, "apex_eod": 1}}


# ------------------------------------------------------------------ pool from candidates.csv

def _f(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def build_pool(fname: str, top: int = 25, per_group: int = 2, near_gap: float = 0.03, near_max: int = 15, cand=CAND) -> list:
    """Candidate dicts of a firm from the merged candidates table (one row per config x session, best rules cell of the firm):
      top     : `top` rows by primary P5 (column p5);
      wf      : configs whose family-grid x session survived the offline WF (lift > 0 and lift CI upper > 0): the best `per_group` per
                grid x session (representatives: the WF is per grid, so near-identical parameter variants add nothing);
      near    : near-misses (P5 within `near_gap` of the top-`top` cut) with positive lift vs day-matched random, best per fam x tf x sess.
    Dedup on (key, sess). Pass-2 configs carry their pass-2 control pool (resolved against the pass-2 snapshot)."""
    rows = sorted([r for r in csv.DictReader(cand.open()) if r["firm"] == fname], key=lambda r: -_f(r["p5"]))
    if os.environ.get("PP_APEX_COMPLIANT") == "1" and fname in ("apex", "apex_eod"):      # Apex: no OCO / both-side orders, stop <= 5x target, threshold never a stop
        rows = [r for r in rows if r.get("apex_compliant") == "1" and r.get("apex_thr_stop") in ("0", "")]
    src3, src2 = P.sources(L3), P.sources(L2)
    sel: dict = {}

    def add(r, how):
        k = (r["key"], r["sess"])
        if k in sel:
            sel[k]["how"] += "+" + how
            return
        d = (src2 if r["pass"] == "2" and r["key"] in src2 else src3).get(r["key"])
        if d is None:
            return
        c = dict(cid=f"{r['key']}|{r['sess']}", key=r["key"], sess=r["sess"], how=how, cand_p5=_f(r["p5"]), cand_pass=r["pass"], **d)
        if r["pass"] == "2":
            pl = E.resolve_pool(E.profile_from(c["fam"], dict(c["params"], tf=c["tf"])), L2, J2)
            if pl["srcs"]:
                c["ctrl_srcs"] = list(pl["srcs"])
        sel[k] = c

    for r in rows[:top]:
        add(r, "top")
    thr = _f(rows[top - 1]["p5"]) if len(rows) >= top else 0.0
    g = defaultdict(list)
    for r in rows:
        if r["wf_survive"] == "1":
            g[(r["grid"], r["sess"])].append(r)
    for v in g.values():
        for r in v[:per_group]:
            add(r, "wf")
    seen, n = defaultdict(int), 0
    for r in rows:
        if _f(r["p5"]) < thr - near_gap or n >= near_max:
            break
        if _f(r["lift_p5"]) > 0 and (r["key"], r["sess"]) not in sel and seen[(r["fam"], r["tf"], r["sess"])] < 1:
            seen[(r["fam"], r["tf"], r["sess"])] += 1
            add(r, "near")
            n += 1
    return list(sel.values())


def make_ctx(fnames=P.FIRM_ALL, top: int = 25, K: int = 10, ledger=None, jobs=None):
    """-> (ctx, {firm: [Base]}) on the merged pool. Replaces portfolio.make_ctx (same return shape)."""
    pools = {f: build_pool(f) for f in fnames}
    allc = {c["cid"]: c for p in pools.values() for c in p}
    trs = {cid: E.load(c["src"]) for cid, c in allc.items()}
    cal = P.Ctx.calendar(np.concatenate([t.date for t in trs.values()]) if trs else ())
    ctx = P.Ctx(cal, L3, J3, K)
    return ctx, {f: [ctx.base(c) for c in pools[f]] for f in fnames}


# ------------------------------------------------------------------ exact member specs

def member_spec(ctx: P.Ctx, b: P.Base, n: int, fm: P.Firm) -> dict:
    c = ctx.cands[b.name]
    params = dict(c["params"])
    prof = E.profile_from(c["fam"], dict(params, tf=c["tf"]))
    return {"strategy_id": c["key"], "config": c["cid"], "tester_strategy": f"{E.DRAFT_PREFIX}{c['fam']}", "family": c["fam"], "tf": c["tf"], "sess": c["sess"],
            "micros": int(n), "stop_mode": prof["stop_mode"], "stop_val": prof["stop_val"], "tgt_r": prof["tgt_r"],
            "exit_bars": prof["exit_bars"], "trail_atr": prof["trail_atr"], "max_tr": prof["max_tr"],
            "family_params": {k: v for k, v in params.items() if k not in ("stop_mode", "stop_val", "tgt_r", "exit_bars", "trail_atr", "max_tr")},
            "tester_inputs": dict({"tf": str(c["tf"]), "sess": "all"}, **params),
            "session_filter_offline": c["sess"], "trade_source": c["src"], "pool": c["how"], "candidate_pass": c.get("cand_pass"),
            "note": "trades come from a tester run at sess=all and are split by entry session offline (strategy is session-independent); "
                    "micros = micro contracts per signal (MNQ / MES); size cost = floor(n/10)*$4 + (n mod 10)*$1 round trip"}


def rules_spec(fm: P.Firm, cell: dict) -> dict:
    r = fm.r
    return {"rule_file": fm.rid, "unconfirmed": not fm.confirmed, "primary_breach_model": fm.prim, "models_reported": list(P.MODELS),
            "daily_rules": {"day_lock_usd": cell["day_lock"] or None, "day_take_usd": cell["day_take"] or None, "day_stop_usd": cell["day_stop"] or None,
                            "max_day_tr": (None if not cell["max_day_tr"] else cell["max_day_tr"]), "target_take": bool(cell["target_take"]),
                            "meaning": {"day_lock": "stop for the day once a trade CLOSES with day P&L >= X", "day_take": "flatten all and stop at day P&L >= X (MFE-based, pessimistic order)",
                                        "day_stop": "trade closes at -Y and stop for the day when day P&L + worst point <= -Y",
                                        "max_day_tr": "max entries per day across the portfolio", "target_take": "stop for the day once the eval pass condition is reached"}},
            "firm_rules": {"name": r.get("name"), "eval_target": r.get("eval_target"), "trailing_mll_eod": r.get("trailing_mll"), "lock_at_profit": r.get("lock_at"),
                           "lock_floor_profit": r.get("lock_floor"), "consistency": r.get("consistency"), "eval_min_days": r.get("eval_min_days"),
                           "soft_daily_loss_limit": fm.dll or None, "cap_micros": fm.cap, "flat_by_et": r.get("flat_by_et")},
            "eval_fee_assumed": fm.fee, "activation_assumed": fm.activation}


# ------------------------------------------------------------------ extras of one report

def _by_day(o, d) -> dict:
    ps, bs = o == 1, o == 2
    return {"pass_on_day": [float((ps & (d == k)).mean()) for k in range(1, 6)], "pass_by_day": [float((ps & (d <= k)).mean()) for k in range(1, 6)],
            "bust_on_day": [float((bs & (d == k)).mean()) for k in range(1, 6)], "bust_by_day": [float((bs & (d <= k)).mean()) for k in range(1, 6)],
            "neither_5d": float((o == 0).mean())}


def news_split(ctx: P.Ctx, res: dict, ci: int) -> dict:
    nd = E.news_days()
    cal_news = np.array([int(x) in nd for x in ctx.cal])
    wn = cal_news[ctx.idx5].any(1)
    out = {"n_starts_with_news_in_window": int(wn.sum()), "n_starts_without": int((~wn).sum())}
    for m in P.MODELS:
        ps = res[m][0][ci] == 1
        bs = res[m][0][ci] == 2
        out[m] = {"p5_news": float(ps[wn].mean()) if wn.any() else None, "p5_nonnews": float(ps[~wn].mean()) if (~wn).any() else None,
                  "bust5_news": float(bs[wn].mean()) if wn.any() else None, "bust5_nonnews": float(bs[~wn].mean()) if (~wn).any() else None}
    return out


def risk_curve(ctx: P.Ctx, fm: P.Firm, members, ci: int, scales=SCALES) -> list:
    """P5 / bust5 (+P1/P3) vs total micros scale (every member x scale, rounded, >= 1, clipped to the firm cap). fixed = the portfolio's rules
    cell unchanged; reopt = rules re-optimised (stable P5 argmax over the full grid, primary model) at that size."""
    out = []
    for s in scales:
        P.gate()
        ms = [(b, int(min(fm.cap, max(1, round(n * s))))) for b, n in members]
        clipped = any(round(n * s) > fm.cap for _, n in members)
        pv = P.PV(ms, ctx.D)
        res = P.grid_outcomes(ctx, fm, pv, P.MODELS)
        row = {"scale": s, "micros": [int(n) for _, n in ms], "total_micros": int(sum(n for _, n in ms)), "cap_clipped": bool(clipped),
               "static_cap_ok": bool(P.feasible(fm, ms)), "trades": pv.n_trades}
        for tag, cc in (("fixed", ci), ("reopt", None)):
            if cc is None:
                F = (res[fm.prim][0] == 1).astype(float).mean(1)
                st = P.stable(F.reshape(fm.shape)).reshape(-1)
                cc = int(np.argmax(st - 1e-7 * fm.nr - 1e-9 * np.arange(fm.ncell)))
            d = {"cell": fm.cell_dict(cc)}
            for m in P.MODELS:
                o, dd = res[m][0][cc], res[m][1][cc]
                d[m] = {k: v for k, v in P._detail(o, dd, 0).items()}
            d["headline"] = d[fm.prim]
            row[tag] = d
        out.append(row)
    return out


def extras(ctx: P.Ctx, fm: P.Firm, members, ci: int) -> dict:
    res = P.grid_outcomes(ctx, fm, P.PV(members, ctx.D), P.MODELS, cells=[ci])
    x = {"by_day": {m: _by_day(res[m][0][ci], res[m][1][ci]) for m in P.MODELS}, "news": news_split(ctx, res, ci),
         "risk_curve": risk_curve(ctx, fm, members, ci), "specs": [member_spec(ctx, b, n, fm) for b, n in members],
         "rules_spec": rules_spec(fm, fm.cell_dict(ci))}
    if len(members) > 1:
        cm = P.corr_matrix([b for b, _ in members])
        C = cm["corr"]
        iu = np.triu_indices(len(members), 1)
        x["member_corr"] = {"names": cm["names"], "daily_pnl_corr": np.round(C, 3).tolist(), "pair_mean": float(C[iu].mean()), "pair_max": float(C[iu].max()),
                            "dd_day_overlap": np.round(cm["dd_overlap"], 3).tolist(), "lose_day_overlap": np.round(cm["lose_overlap"], 3).tolist(),
                            "multi_dd_share": cm["multi_dd_share"]}
    return x


# ------------------------------------------------------------------ one firm: search + reports + extras (phase A)

def run_firm_final(fname: str, obj: str = "p5", tag: str = TAG, passes: int = 3, boots: int = 2000, extra_singles: int = 3, verbose: bool = True) -> dict:
    t0 = time.time()
    fm = P.firm(fname)
    ctx, pools = make_ctx((fname,))
    pool = pools[fname]
    sc = P.Scorer(ctx, fm, obj=obj)
    g = P.greedy(ctx, sc, pool, verbose=verbose, passes=passes)
    single = g["single"]
    ref = {"label": P._lab(single["_m"]), "stable": single["stable"], "p5": single["p5"]}
    items = [("single", single)] + ([("best2", g["best2"])] if g["best2"] else []) + [("portfolio", g["final"])]
    rep, arrs = {}, {}
    for lab, h in items:
        rep[lab] = P.report(ctx, fm, h["_m"], h["ci"], True, boots, ref_single=None if lab == "single" else ref)
        rep[lab].pop("series", None)
        rep[lab]["search"] = {"stable_score": h["stable"], "adj_score": h["adj"], "objective": obj,
                              "forced_to_3": any(x.get("forced") for x in g["history"]) and len(h["members"]) >= 3}
        rep[lab]["extras"] = extras(ctx, fm, h["_m"], h["ci"])
        arrs[lab] = P.spec_arrays(ctx, fm, h["_m"], h["ci"])
    if len(g["final"]["members"]) < 3:
        rep["portfolio"]["flags"].append("FEWER_THAN_3_MEMBERS: no feasible 3rd member under the guards (cap / net-share); this is the best 2-member")
    if any(h.get("forced") for h in g["history"]):
        rep["portfolio"]["flags"].append("FORCED_TO_3: 3rd member added with gain <= 0.005 (stop rule overridden for the >=3 guard)")
    rep["portfolio"]["vs_single"]["delta_stable"] = g["final"]["stable"] - single["stable"]
    if "best2" in rep:
        rep["best2"]["vs_single"]["delta_stable"] = g["best2"]["stable"] - single["stable"]
    seen, specs = {b.name for b, _ in single["_m"]}, []
    for adj, name, n, ci, st, p in g["singles"]:
        if name in seen or len(specs) >= extra_singles:
            continue
        seen.add(name)
        specs.append((f"single:{name}@{n}", [(ctx.bases[name], n)], ci, st, p))
    for lab, ms, ci, st, p in specs:
        arrs[lab] = P.spec_arrays(ctx, fm, ms, ci)
        rep[lab] = {"members": [{"name": b.name, "micros": n} for b, n in ms], "cell": fm.cell_dict(ci), "search": {"stable_score": st, "p5": p},
                    "specs": [member_spec(ctx, b, n, fm) for b, n in ms]}
    res = {"firm": fname, "rules_id": fm.rid, "primary": fm.prim, "unconfirmed": not fm.confirmed, "objective": obj,
           "pool": [{k: c.get(k) for k in ("cid", "src", "fam", "tf", "sess", "how", "cand_p5", "cand_pass")} for c in (ctx.cands[b.name] for b in pool)],
           "pool_size": len(pool), "history": [P._clean(h) for h in g["history"]], "singles_top": [(a, nm, n, st, p) for a, nm, n, ci, st, p in g["singles"]],
           "reports": rep, "evals": g["evals"], "secs": time.time() - t0, "calendar_sessions": ctx.D, "starts": ctx.S,
           "fee": {"eval_fee": fm.fee, "activation": fm.activation, "assumption": True}}
    (OUT / f"portfolio_{fname}{tag}.json").write_text(json.dumps(res, indent=1, default=P._js))
    np.savez_compressed(OUT / f"portfolio_{fname}{tag}.npz", **{f"{lab}|{m}|{k}": a[m][i] for lab, a in arrs.items() for m in P.MODELS
                                                                 for i, k in enumerate(("o", "d"))})
    if verbose:
        print(P.brief(res).replace("PRELIMINARY ", ""), flush=True)
    return res



# ------------------------------------------------------------------ >= 3 members when the plain greedy ends with fewer (phase A2)

def search_ge3(ctx: P.Ctx, sc: P.Scorer, pool: list, fm: P.Firm, n_starts: int = 4, start_micros=(20, 30, 10), passes: int = 2, verbose: bool = True):
    """The plain greedy starts from the best single at max size; a dominant member then breaks the net-share guard for every 3rd member.
    Retry greedy from other starts (top single bases x smaller micros, guards ON). If none reaches 3 members, retry with the net-share guard
    relaxed (flagged SHARE_GUARD_RELAXED; the actual shares are in the report). -> (history entry | None, info dict)."""
    singles = {}
    for b in pool:
        for n in fm.micros:
            adj, ci, st, p = P._adj(sc, [(b, n)])
            if b.name not in singles or adj > singles[b.name][0]:
                singles[b.name] = (adj, n)
    tops = sorted(singles.items(), key=lambda kv: -kv[1][0])[:n_starts]
    byname = {b.name: b for b in pool}
    info = {"attempts": []}
    for relaxed in (False, True):
        orig = P.share_ok
        if relaxed:
            P.share_ok = lambda m, upto=None: True
        try:
            best = None
            for name, (adj0, n0) in tops:
                for n in [m for m in start_micros if m <= fm.cap and m != n0] + [n0]:
                    try:
                        g = P.greedy(ctx, sc, pool, start=[(byname[name], n)], passes=passes, force_min=3)
                        h = g["final"]
                    except (IndexError, ValueError):
                        continue
                    if len(h["members"]) >= 3 and (best is None or h["adj"] > best["adj"]):
                        best = h
                    info["attempts"].append({"start": f"{name}@{n}", "members": h["members"], "adj": h["adj"]})
                    if verbose:
                        print(f"[{fm.name}] ge3 start {name}@{n} -> {len(h['members'])} members adj {h['adj']:.3f}", flush=True)
        finally:
            P.share_ok = orig
        if best is not None:
            info["share_guard_relaxed"] = relaxed
            return best, info
    return None, info


def run_fix3(fname: str, tag: str = TAG, obj: str = "p5", boots: int = 2000, verbose: bool = True, n_starts: int = 4):
    """Replace 'portfolio' of a saved firm result by the best >= 3-member set (the old 2-member stays as 'portfolio_2member_greedy')."""
    jp = OUT / f"portfolio_{fname}{tag}.json"
    res = json.loads(jp.read_text())
    fm = P.firm(fname)
    ctx, pools = make_ctx((fname,))
    pool = pools[fname]
    sc = P.Scorer(ctx, fm, obj=obj)
    h, info = search_ge3(ctx, sc, pool, fm, n_starts=n_starts, verbose=verbose)
    res["ge3_search"] = {k: v for k, v in info.items()}
    if h is None:
        res["ge3_search"]["result"] = "no >=3-member set found even with the share guard relaxed"
        jp.write_text(json.dumps(res, indent=1, default=P._js))
        return res
    ref = res["reports"]["single"]
    ref_single = {"label": "single", "stable": ref["search"]["stable_score"], "p5": ref["headline"]["p5"]}
    r = P.report(ctx, fm, h["_m"], h["ci"], True, boots, ref_single=ref_single)
    r.pop("series", None)
    r["search"] = {"stable_score": h["stable"], "adj_score": h["adj"], "objective": obj, "forced_to_3": True, "via": "search_ge3"}
    r["extras"] = extras(ctx, fm, h["_m"], h["ci"])
    if info.get("share_guard_relaxed"):
        r["flags"].append("SHARE_GUARD_RELAXED: no 3-member set satisfies 'no member > 50% of raw net'; shares are in members[].net_share")
    r["flags"].append("GE3_SEARCH: best >=3-member set from greedy restarts (plain greedy ended with 2 members)")
    res["reports"]["portfolio_2member_greedy"] = res["reports"].get("portfolio")
    res["reports"]["portfolio"] = r
    arrs = P.spec_arrays(ctx, fm, h["_m"], h["ci"])
    npz = dict(np.load(OUT / f"portfolio_{fname}{tag}.npz"))
    for m in P.MODELS:
        for i, k in enumerate(("o", "d")):
            npz[f"portfolio|{m}|{k}"] = arrs[m][i]
    np.savez_compressed(OUT / f"portfolio_{fname}{tag}.npz", **npz)
    jp.write_text(json.dumps(res, indent=1, default=P._js))
    if verbose:
        print(P.brief({"firm": fname, "rules_id": fm.rid, "unconfirmed": not fm.confirmed, "primary": fm.prim, "evals": sc.evals, "secs": 0,
                       "reports": {"portfolio": r}}).replace("PRELIMINARY ", ""), flush=True)
    return res

# ------------------------------------------------------------------ WF (phases B and C)

def _wf_ctx(fname):
    fm = P.firm(fname)
    ctx, pools = make_ctx((fname,))
    W, tests, oos = P.wf_windows(ctx.cal)
    return fm, ctx, pools[fname], W, tests, oos


def run_wf_fixed(fname: str, tag: str = TAG, kc: int = 5, boots: int = 2000, labs=("single", "best2", "portfolio"), wait: bool = True):
    """Fixed-set WF for single / best2 / portfolio of the saved search (waits for the search file)."""
    jp = OUT / f"portfolio_{fname}{tag}.json"
    while wait and not jp.exists():
        time.sleep(30)
    time.sleep(1)
    src = json.loads(jp.read_text())
    fm, ctx, pool, W, tests, oos = _wf_ctx(fname)
    byname = {b.name: b for b in pool}
    wp = OUT / f"portfolio_wffixed_{fname}{tag}.json"
    res = json.loads(wp.read_text()) if (wp.exists() and tuple(labs) != ("single", "best2", "portfolio")) else {}
    res.update({"firm": fname, "primary": fm.prim, "oos_starts": int(len(oos)), "quarters": [f"{y}Q{q}" for y, q in P.QUARTERS]})
    t0 = time.time()
    for lab in labs:
        if lab not in src["reports"]:
            continue
        members = [(byname[m["name"]], m["micros"]) for m in src["reports"][lab]["members"]]
        res[f"{lab}_fixed"] = P.wf_fixed_with_controls(ctx, fm, members, W, tests, oos, kc=kc, boots=boots)
        x = res[f"{lab}_fixed"]
        print(f"[{fname}] wf {lab} fixed: OOS P5 {x['oos_p5']:.3f} ctrl {x.get('ctrl_oos_p5', float('nan')):.3f} lift {x.get('lift', float('nan')):+.3f} ({time.time()-t0:.0f}s)", flush=True)
    wp.write_text(json.dumps(res, indent=1, default=P._js))
    return res


def run_wf_reselect(fname: str, tag: str = TAG, kc: int = 5, passes: int = 1, boots: int = 2000):
    fm, ctx, pool, W, tests, oos = _wf_ctx(fname)
    t0 = time.time()
    x = P.wf_reselect(ctx, fm, pool, W, tests, oos, kc=kc, passes=passes, boots=boots, verbose=True)
    x["secs"] = time.time() - t0
    (OUT / f"portfolio_wfres_{fname}{tag}.json").write_text(json.dumps({"firm": fname, "primary": fm.prim, "portfolio_reselect": x}, indent=1, default=P._js))
    print(f"[{fname}] wf reselect: OOS P5 {x['oos_p5']:.3f} ctrl {x['ctrl_oos_p5']:.3f} lift {x['lift']:+.3f} ({x['secs']:.0f}s)", flush=True)
    return x


def _task(a):
    kind, f, kw = a
    return {"A": run_firm_final, "FX": run_wf_fixed, "RS": run_wf_reselect, "G3": run_fix3}[kind](f, **kw)


# ------------------------------------------------------------------ multi-account

def run_multi(firms=P.FIRM_ALL, tag: str = TAG):
    mixes = {n: c for n, c in MIXES.items() if all(f in firms for f in c)}
    r = P.run_multi(firms, mixes, tag=tag)
    for n, m in r["mixes"].items():
        p = m["primary"]
        print(f"N={n} {m['counts']}: P(>=1 pass<=5d)={p['p_any5']:.3f} eod {m['eod']['p_any5']:.3f} intra {m['intraday']['p_any5']:.3f} "
              f"by-day {[round(x, 2) for x in p['p_any_by_day']]} E[funded]={p['e_funded']:.2f} cost={p['total_eval_cost']:.0f} $/funded={p['cost_per_funded']}")
    return r


# ------------------------------------------------------------------ CLI

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pool", "run", "multi", "fix3", "fx", "rs"])
    ap.add_argument("--firms", default=",".join(P.FIRM_ALL))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--obj", default="p5", choices=list(P.OBJECTIVES))
    ap.add_argument("--tag", default=TAG)
    ap.add_argument("--no-wf", action="store_true")
    ap.add_argument("--n-starts", type=int, default=4)
    ap.add_argument("--labs", default="single,best2,portfolio")
    ap.add_argument("--passes", type=int, default=3)
    a = ap.parse_args(argv)
    firms = [f for f in a.firms.split(",") if f]
    if a.cmd == "pool":
        for f in firms:
            p = build_pool(f)
            print(f, len(p), {h: sum(1 for c in p if c["how"].startswith(h)) for h in ("top", "wf", "near")})
    elif a.cmd == "run":
        import multiprocessing as mp
        tasks = [("A", f, dict(obj=a.obj, tag=a.tag, passes=a.passes)) for f in firms]
        if not a.no_wf:
            tasks += [("RS", f, dict(tag=a.tag)) for f in firms] + [("FX", f, dict(tag=a.tag)) for f in firms]
        with mp.get_context("spawn").Pool(min(a.workers, 4, len(tasks))) as pool:
            for _ in pool.imap_unordered(_task, tasks):
                pass
    elif a.cmd == "fx":
        import multiprocessing as mp
        with mp.get_context("spawn").Pool(min(a.workers, 4, len(firms))) as pool:
            for _ in pool.imap_unordered(_task, [("FX", f, dict(tag=a.tag, labs=tuple(a.labs.split(",")), wait=False)) for f in firms]):
                pass
    elif a.cmd == "rs":
        import multiprocessing as mp
        with mp.get_context("spawn").Pool(min(a.workers, 4, len(firms))) as pool:
            for _ in pool.imap_unordered(_task, [("RS", f, dict(tag=a.tag)) for f in firms]):
                pass
    elif a.cmd == "fix3":
        import multiprocessing as mp
        with mp.get_context("spawn").Pool(min(a.workers, 4, len(firms))) as pool:
            for _ in pool.imap_unordered(_task, [("G3", f, dict(tag=a.tag, obj=a.obj, n_starts=a.n_starts)) for f in firms]):
                pass
    else:
        run_multi(tuple(firms), a.tag)


if __name__ == "__main__":
    main()
