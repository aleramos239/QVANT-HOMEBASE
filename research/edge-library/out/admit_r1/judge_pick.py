"""STAGE 2b ADMIT, step 2: the 2024 heat map of every BUILD passer (copy of out/admit/judge_pick.py + the time-fired control).
PICK tables use the BUILD dead flags. Writes out/admit_r1/pick_judgement.json and jobs_stress.json (cells positive in both
periods + the BUILD central cell, for the units whose 2024 table passes)."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

W = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
import library as LB  # noqa: E402

OUT = W / "out" / "admit_r1"
RA = W / "runs_admit_r1"


def sess_cell(u, cid, sess):
    x = LB.unit_cell(u, cid)
    m = x["sess"] == LB.SESS_CODE[sess]
    return {k: v[m] for k, v in x.items()}


def main():
    d = pd.read_csv(OUT / "build_units.csv")
    out, jobs = {}, []
    for r in d[d.build_pass == True].to_dict("records"):  # noqa: E712
        key, sess, root, tf, fam, timed = r["key"], r["sess"], r["root"], str(r["tf"]), r["family"], bool(r["timed"])
        ub, up = LB.load_unit(key), LB.load_unit(f"{key}-{sess}-pick", RA)
        assert up["meta"]["period"] == "pick" and ub["meta"]["period"] == "build"
        tb = {t["id"]: t for t in LB.session_table(ub, sess)}
        tp = LB.session_table(up, sess)
        for t in tp:
            t["dead"] = tb[t["id"]]["dead"]
        pb, pp = LB.plateau(list(tb.values())), LB.plateau(tp)
        tpd = {t["id"]: t for t in tp}
        both = [i for i in tb if not tb[i]["dead"] and not tb[i].get("info") and tb[i]["net"] > 0 and tpd[i]["net"] > 0]
        cm = pb["member"]
        assert cm == r["member"]
        x = sess_cell(up, cm, sess)
        st = LB.stats(x["net"])
        if timed:
            su = LB.load_unit(f"{key}-{sess}-pick-shift", RA)
            nets = [float(LB.unit_cell(su, f"s{sd}_{cm}")["net"].sum()) for sd in (1, 2)]
            ctrl = {"ctrl": "shift", "c1_lift": round(st["net"] - float(np.mean(nets)), 2), "c1_p_beat": None, "c1_short": 0, "ctrl_nets": nets}
        else:
            xid = cm.rsplit("_", 1)[-1]
            pu = LB.load_unit(f"c1-{root}-tf{tf}-{sess}-pick", RA)
            parts = [LB.unit_cell(pu, f"s{sd}_{xid}") for sd in (1, 2)]
            pool = {k: np.concatenate([p[k] for p in parts]) for k in ("date", "sess", "net")}
            c1 = LB.c1_draws(x, pool, K=200, seed=LB.default_seed(r["uid"], "pick"))
            ctrl = {"ctrl": "c1", "c1_lift": c1["lift"], "c1_p_beat": c1["p_beat"], "c1_short": c1["short"], "c1_fallback": round(c1["fallback_share"], 4)}
        out[r["uid"]] = {"key": key, "sess": sess, "family": fam, "root": root, "tf": tf, "timed": timed, "build": pb, "pick": pp,
                         "both_positive": both, "central": cm, "central_pick": {**st, **ctrl},
                         "exact60_pick": abs((pp["share_pos"] or 0) - 0.6) < 1e-9}
        sh = pp["shares"]
        print(f"{r['uid']}: PICK plateau {'PASS' if pp['pass'] else 'fail'} share>0 {pp['share_pos']} median {pp['median_net']} "
              f"(60/70/80: {pp['verdicts']}) by stop { {k: v['share_pos'] for k, v in sh['by_stop'].items()} } "
              f"by target { {k: v['share_pos'] for k, v in sh['by_target'].items()} } | central {cm}: pick net {st['net']} trades {st['trades']} "
              f"t {st['t']} control lift {ctrl['c1_lift']} p_beat {ctrl['c1_p_beat']} | both-positive cells {len(both)} of {pb['cells']} judged")
        if pp["pass"]:
            cells = sorted(set(both) | {cm})
            for per in ("build", "pick"):
                jobs.append({"family": fam, "root": root, "tf": tf, "sess": sess, "period": per, "stress": True, "cells": cells,
                             "why": f"stress of the both-positive cells (+ the BUILD central cell) of {r['uid']}"})
    (OUT / "pick_judgement.json").write_text(json.dumps(out, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    (OUT / "jobs_stress.json").write_text(json.dumps(jobs, indent=1))
    print("stress jobs", len(jobs), "cells", sum(len(j["cells"]) for j in jobs))


if __name__ == "__main__":
    main()
