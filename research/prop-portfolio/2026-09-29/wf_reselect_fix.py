#!/usr/bin/python3
"""Recompute the walk-forward 'reselect' outputs WITHOUT the look-ahead of the net-share guard.
Per-quarter picks come from wf_truncate.py reselect runs (search re-run on data truncated at the test-quarter start); the OOS flags, the day-matched
control lift and the CIs come from portfolio.wf_reselect(picks_override=...) on the full calendar (test quarters need their own data).
Usage: wf_reselect_fix.py firm[,firm]   (reads out/wf_truncate_reselect_*.json; writes out/portfolio_wfres_<firm>_final.json, originals kept in out/pre_verify/)"""
import json, sys, shutil, time, glob
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import portfolio as P
import portfolio_final as PF

OUT = P.OUT
(OUT / "pre_verify").mkdir(exist_ok=True)
QS = [f"{y}Q{q}" for y, q in P.QUARTERS]


def truncated_picks(f):
    picks = {}
    for p in sorted(glob.glob(str(OUT / "wf_truncate_reselect*.json"))):
        for r in json.loads(Path(p).read_text()):
            if r["firm"] == f:
                picks[r["quarter"]] = r["pick"]
    return picks


for f in sys.argv[1].split(","):
    picks = truncated_picks(f)
    missing = [q for q in QS if q not in picks]
    if missing:
        print(f, "missing quarters", missing); continue
    fm, ctx, pool, W, tests, oos = PF._wf_ctx(f)
    t0 = time.time()
    x = P.wf_reselect(ctx, fm, pool, W, tests, oos, kc=5, passes=1, boots=2000, picks_override=[picks[q] for q in QS])
    x["secs"] = time.time() - t0
    x["note"] = "picks from searches re-run on data truncated at each test-quarter start (share guard sees no test-period P&L); pool is still chosen on the full window"
    dst = OUT / f"portfolio_wfres_{f}_final.json"
    bak = OUT / "pre_verify" / dst.name
    if not bak.exists():
        shutil.copy(dst, bak)
    old = json.loads(bak.read_text())["portfolio_reselect"]
    dst.write_text(json.dumps({"firm": f, "primary": fm.prim, "portfolio_reselect": x}, indent=1, default=P._js))
    print(f"[{f}] reselect OOS P5 {old['oos_p5']:.4f} -> {x['oos_p5']:.4f} | ctrl {old['ctrl_oos_p5']:.3f} -> {x['ctrl_oos_p5']:.3f} | lift {old['lift']:+.3f} {old['lift_ci']} -> {x['lift']:+.3f} {x['lift_ci']} "
          f"| picks changed {sum([tuple(map(tuple, a['members'])), a['cell']] != [tuple(map(tuple, b['members'])), b['cell']] for a, b in zip(old['picks'], x['picks']))}/{len(QS)}", flush=True)
