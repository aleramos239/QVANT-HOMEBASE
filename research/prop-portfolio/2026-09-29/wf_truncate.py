#!/usr/bin/python3
"""Look-ahead audit of the portfolio walk-forward: for each test quarter, DROP every trade and session dated on/after the test-quarter start
(calendar, member trade sets, controls irrelevant), re-run the selection for that quarter on the truncated data and compare the picks with the
picks stored by the full-data run (and a fresh full-data run).

  fixed   : P.wf_fixed on truncated bases (member SET fixed = the final portfolio; micros + rules re-selected)
  reselect: P.greedy on truncated bases (whole search re-run; passes=1 like run_wf_reselect)
Usage: wf_truncate.py fixed|reselect firm[,firm] [--quarters 2022Q3,...] [--workers 3] [--full-check]
"""
import argparse, json, sys, time, datetime as dt
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E
import portfolio as P
import portfolio_final as PF

OUT = P.OUT
QS = [f"{y}Q{q}" for y, q in P.QUARTERS]


def trunc_ctx(fname, j, pool):
    """Truncated calendar + Bases for quarter index j. -> (ctx_t, {name: Base_t}, a)"""
    a, b, lo = P.q_bounds(*P.QUARTERS[j])
    cal_full = P.Ctx.calendar(np.concatenate([E.load(c["src"]).date for c in pool]))
    cal_t = cal_full[cal_full < a]
    ctx = P.Ctx(cal_t, PF.L3, PF.J3, 10)
    bases = {}
    for c in pool:
        tr = E.load(c["src"])
        m = E._sess_mask(tr, c.get("sess", "all")) & (tr.date < a)
        bases[c["cid"]] = P.Base(c["cid"], cal_t, tr.date[m], tr.te[m], tr.tx[m], tr.side[m], tr.g[m], tr.mae[m], tr.mfe[m], tr.risk[m], meta=c)
    return ctx, bases, a


def task(args):
    mode, fname, j, passes = args
    t0 = time.time()
    fm = P.firm(fname)
    pool = PF.build_pool(fname)
    ctx, bases, a = trunc_ctx(fname, j, pool)
    Wt, tests_t, _ = P.wf_windows(ctx.cal)
    out = {"firm": fname, "quarter": QS[j], "mode": mode, "cal_days": int(ctx.D), "last_day": dt.date.fromordinal(int(ctx.cal[-1])).isoformat(),
           "train_starts": int((Wt[:, j] > 0).sum())}
    plist = [bases[c["cid"]] for c in pool]
    if mode == "fixed":
        src = json.loads((OUT / f"portfolio_{fname}_final.json").read_text())
        mem = src["reports"]["portfolio"]["members"]
        mb = [bases[m["name"]] for m in mem]
        r = P.wf_fixed(ctx, fm, mb, [m["micros"] for m in mem], Wt, tests_t)
        pk = r["picks"][j]
        out["pick"] = {"micros": pk["micros"], "cell": pk["cell"], "train_stable": pk["train_stable"], "train_p5": pk["train_p5"]}
        st = json.loads((OUT / f"portfolio_wffixed_{fname}_final.json").read_text())["portfolio_fixed"]["picks"][j]
        out["stored"] = {"micros": st["micros"], "cell": st["cell"], "train_stable": st["train_stable"], "train_p5": st["train_p5"]}
    else:
        sc = P.Scorer(ctx, fm, W=Wt[:, [j]])
        g = P.greedy(ctx, sc, plist, q=0, passes=passes)
        h = g["final"]
        out["pick"] = {"members": [list(x) for x in h["members"]], "cell": h["cell"], "train_stable": h["stable"], "train_p5": h["p5"]}
        st = json.loads((OUT / f"portfolio_wfres_{fname}_final.json").read_text())["portfolio_reselect"]["picks"][j]
        out["stored"] = {"members": st["members"], "cell": st["cell"], "train_stable": st["train_stable"], "train_p5": st["train_p5"]}
        out["evals"] = sc.evals
    p, s = out["pick"], out["stored"]
    key = "micros" if mode == "fixed" else "members"
    out["same_set"] = p[key] == s[key]
    out["same_cell"] = p["cell"] == s["cell"]
    out["same_score"] = abs(p["train_stable"] - s["train_stable"]) < 1e-6 and abs(p["train_p5"] - s["train_p5"]) < 1e-6
    out["identical"] = out["same_set"] and out["same_cell"] and out["same_score"]
    out["secs"] = time.time() - t0
    print(json.dumps({k: v for k, v in out.items() if k not in ("pick", "stored")}), flush=True)
    if not out["identical"]:
        print("   DIFF pick  ", json.dumps(p), "\n   DIFF stored", json.dumps(s), flush=True)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["fixed", "reselect"])
    ap.add_argument("firms")
    ap.add_argument("--quarters", default="")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--passes", type=int, default=1)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    qs = [QS.index(q) for q in a.quarters.split(",")] if a.quarters else list(range(len(QS)))
    jobs = [(a.mode, f, j, a.passes) for f in a.firms.split(",") for j in qs]
    import multiprocessing as mp
    res = []
    with mp.get_context("spawn").Pool(min(a.workers, 4, len(jobs))) as pool:
        for r in pool.imap_unordered(task, jobs):
            res.append(r)
    tag = f"{a.mode}_{a.firms.replace(',', '+')}{a.tag}"
    (OUT / f"wf_truncate_{tag}.json").write_text(json.dumps(res, indent=1, default=str))
    print("IDENTICAL", sum(r["identical"] for r in res), "/", len(res))
