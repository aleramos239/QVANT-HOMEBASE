"""ORCHESTRATOR RULING 2026-10-04: the 08:30 NQ straddle, news days only, on 2024 (whole menu, same split).
Judged: (a) BUILD + 2024 trades of the BUILD central variant >= 100; the 2024 table must pass the heat map; surviving set under
2 ticks + 250 ms; the BUILD central variant must itself be positive in 2024 and under stress (no moved default).
  python out/deepen/judge_pick_0830.py        -> out/deepen/pick_0830.json (+ jobs_stress_0830.json when the table passes)"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import judge_pick_sides as P  # noqa: E402
import judge_sides as J  # noqa: E402
import library as LB  # noqa: E402

UID, SIDE = "straddle_t_0830-NQ-tf30|pre|", "news_only"


def main():
    T = P.tables(UID, SIDE, False)
    pb, pp = LB.plateau(T["build"]), LB.plateau(T["pick"])
    tb, tp = {t["id"]: t for t in T["build"]}, {t["id"]: t for t in T["pick"]}
    cm = pb["member"]
    both = [i for i in tb if not tb[i]["dead"] and tb[i]["net"] > 0 and tp[i]["net"] > 0]
    xb, xp = P.cell(T["ub"], cm, T["sess"], SIDE, T["root"]), P.cell(T["up"], cm, T["sess"], SIDE, T["root"])
    sb_, sp_ = LB.stats(xb["net"]), LB.stats(xp["net"])
    n_all = sb_["trades"] + sp_["trades"]
    out = {"uid": UID, "side": SIDE, "build": pb, "pick": pp, "central": cm, "both_positive": both,
           "central_build": sb_, "central_pick": sp_, "trades_build_plus_pick": n_all, "a": n_all >= LB.MIN_TRADES,
           "pick_table_pass": bool(pp["pass"]), "central_pick_positive": bool(sp_["net"] > 0)}
    sh = pp["shares"]
    print(f"BUILD side: share>0 {pb['share_pos']} median {pb['median_net']} central {cm} trades {sb_['trades']} net {sb_['net']} t {sb_['t']:.3f}")
    print(f"2024 side: plateau {'PASS' if pp['pass'] else 'fail'} share>0 {pp['share_pos']} of {pp['cells']} median {pp['median_net']} "
          f"(60/70/80 {pp['verdicts']}) by stop { {k: v['share_pos'] for k, v in sh['by_stop'].items()} } "
          f"by target { {k: v['share_pos'] for k, v in sh['by_target'].items()} }")
    print(f"central on 2024: trades {sp_['trades']} net {sp_['net']} t {sp_['t']} win {sp_['win']} | BUILD + 2024 trades {n_all} (a: {out['a']}) | "
          f"both-positive cells {len(both)} of {pb['cells']}")
    jobs = []
    if pp["pass"] and both:
        for per in ("build", "pick"):
            jobs.append({"family": "straddle_t_0830", "root": "NQ", "tf": "30", "sess": "pre", "period": per, "stress": True, "cells": both,
                         "why": f"stress (2 ticks + 250 ms) of the both-positive cells of {UID} {SIDE} (orchestrator ruling)"})
    (HERE / "pick_0830.json").write_text(json.dumps(out, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    (HERE / "jobs_stress_0830.json").write_text(json.dumps(jobs, indent=1))
    print("stress jobs", len(jobs))


if __name__ == "__main__":
    main()
