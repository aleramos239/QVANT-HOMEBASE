"""STAGE 2a, PICK: the 2024 heat map of every side that passed (a)-(e) on BUILD, with the SAME split. The PICK table uses the
BUILD dead flags (as out/admit/judge_pick.py). Writes out/deepen/pick_judgement.json and jobs_stress.json (cells positive in both
periods, only for a side whose 2024 table passes)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import judge_sides as J  # noqa: E402
import labels as L  # noqa: E402
import library as LB  # noqa: E402

RD = J.W / "runs_deepen"
# (uid, side, exact re-run with the family's dir input?)
CANDS = [("donchian-NQ-tf5|nyam|", "vol_lo", False), ("rsi2-NQ-tf30|eve|", "long", True)]


def tables(uid: str, side: str, exact: bool, stress: bool = False) -> dict:
    """{'build': table, 'pick': table, 'ub', 'up', 'filter'}: the side's tables in both periods (stress=True: the stressed stores)."""
    r = {x["uid"]: x for x in J.units()}[uid]
    key, sess, root = r["key"], r["sess"], r["root"]
    base = LB.plateau_units(J.load(key), sess)[r.get("label") or ""]
    dead = {t["id"]: t["dead"] for t in base}
    sfx = "-stress" if stress else ""
    if exact:
        ub = LB.load_unit(f"{key}-{sess}-build-dir{side}{sfx}", RD)
        up = LB.load_unit(f"{key}-{sess}-pick-dir{side}{sfx}", RD)
        flt = None                                           # the store already holds that side only
    else:
        ub = LB.load_unit(f"{key}-{sess}-build-stress", RD) if stress else J.load(key)
        up = LB.load_unit(f"{key}-{sess}-pick{sfx}", RD)
        flt = side
    assert ub["meta"]["period"] == "build" and up["meta"]["period"] == "pick"
    out = {}
    for per, u in (("build", ub), ("pick", up)):
        ids = {c["id"] for c in u["meta"]["cells"]}
        rows = [t for t in base if t["id"] in ids]
        tab = J.side_table(u, sess, rows, flt, root)
        for t in tab:
            t["dead"] = dead[t["id"]]
        out[per] = tab
    out.update(ub=ub, up=up, filter=flt, sess=sess, root=root, key=key, tf=str(r["tf"]), family=r["family"])
    return out


def cell(u, cid, sess, flt, root):
    x = LB.unit_cell(u, cid)
    m = x["sess"] == LB.SESS_CODE[sess]
    if flt:
        m = m & L.side_mask(flt, root, x["date"], x["side"])
    return J.masked(x, m)


def main():
    out, jobs = {}, []
    for uid, side, exact in CANDS:
        T = tables(uid, side, exact)
        pb, pp = LB.plateau(T["build"]), LB.plateau(T["pick"])
        tb, tp = {t["id"]: t for t in T["build"]}, {t["id"]: t for t in T["pick"]}
        both = [i for i in tb if not tb[i]["dead"] and tb[i]["net"] > 0 and tp[i]["net"] > 0]
        cm = pb["member"]
        x = cell(T["up"], cm, T["sess"], T["filter"], T["root"])
        st = LB.stats(x["net"])
        pu = LB.load_unit(f"c1-{T['root']}-tf{T['tf']}-{T['sess']}-pick", RD)
        parts = [LB.unit_cell(pu, f"s{sd}_{J.exit_id(cm)}") for sd in (1, 2)]
        pool = {k: np.concatenate([p[k] for p in parts]) for k in ("date", "sess", "net", "side")}
        pm = L.side_mask(side, T["root"], pool["date"], pool["side"])
        c1 = LB.c1_draws(x, {k: v[pm] for k, v in pool.items()}, K=200, seed=LB.default_seed(f"{uid}|{side}", "pick"))
        out[f"{uid}{side}"] = {"uid": uid, "side": side, "exact": exact, "key": T["key"], "sess": T["sess"], "root": T["root"], "tf": T["tf"],
                               "family": T["family"], "build": pb, "pick": pp, "both_positive": both, "central": cm,
                               "central_pick": {**st, "c1_lift": c1["lift"], "c1_p_beat": c1["p_beat"], "c1_short": c1["short"],
                                                "c1_fallback": round(c1["fallback_share"], 4)}}
        sh = pp["shares"]
        print(f"{uid} {side}: BUILD share>0 {pb['share_pos']} median {pb['median_net']} central {cm} ({pb['member_net']}) | "
              f"PICK plateau {'PASS' if pp['pass'] else 'fail'} share>0 {pp['share_pos']} median {pp['median_net']} (60/70/80 {pp['verdicts']}) "
              f"by stop { {k: v['share_pos'] for k, v in sh['by_stop'].items()} } by target { {k: v['share_pos'] for k, v in sh['by_target'].items()} } | "
              f"central on PICK: net {st['net']} trades {st['trades']} t {st['t']} c1 lift {c1['lift']} p_beat {c1['p_beat']} short {c1['short']} | "
              f"both-positive cells {len(both)} of {pb['cells']} judged")
        if pp["pass"] and both:
            r = {x["uid"]: x for x in J.units()}[uid]
            for per in ("build", "pick"):
                jobs.append({"family": r["family"], "root": r["root"], "tf": str(r["tf"]), "sess": r["sess"], "period": per, "stress": True,
                             "cells": both, **({"extra": {"dir": side}} if exact else {}),
                             "why": f"stress (2 ticks + 250 ms) of the both-positive cells of {uid} {side}"})
    (HERE / "pick_judgement.json").write_text(json.dumps(out, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    (HERE / "jobs_stress.json").write_text(json.dumps(jobs, indent=1))
    print("stress jobs", len(jobs))


if __name__ == "__main__":
    main()
