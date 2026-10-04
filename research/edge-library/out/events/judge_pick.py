"""STAGE 3, step 2 (2024): every unit that passed ALL of (a)-(e) on BUILD, whole menu on 2024 with the SAME day filter.
  table must pass (b) (BUILD dead flags); the BUILD central variant must be positive in 2024 (no moved default);
  controls on 2024 (a missing control = a fail): the same bracket at a random minute on the same days (lift > 0), and the
  non-event-day lift per trade (printed; the BUILD test (c) again, information on 2024).
2024 stores: E1 NQ / GC = runs_admit_r1/ (ALREADY READ in stage 2b on all days: SECOND LOOK; re-read logged), E3 GC = runs_events/.
Every read is appended to out/events/pick_reads.csv BEFORE the store is opened.
  python out/events/judge_pick.py -> out/events/pick_judgement.json (+ jobs_stress.json for stress cells not on disk)"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ev as E  # noqa: E402
import judge_build as JB  # noqa: E402
import library as LB  # noqa: E402

W = E.W
READS = HERE / "pick_reads.csv"
STORES = {"straddle_tight_0830": (W / "runs_admit_r1", "pre"), "straddle_tight_1000": (W / "runs_events", "nyam"),
          "straddle_t_0830": (W / "runs_deepen", "pre")}


def log_read(key, fam, root, sess, what, cells, why):
    with READS.open("a", newline="") as fh:
        csv.writer(fh).writerow([dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), key, fam, root, JB.TF, sess, what, cells, why])


def pick_key(fam, root, sess, sfx=""):
    return f"{fam}-{root}-tf{JB.TF}-{sess}-pick{sfx}"


def main():
    units = [r for r in json.loads((HERE / "build_units.json").read_text()) if r["pass"]]
    out, jobs = {}, []
    for r in units:
        fam, root, sess, g, uid, cm = r["family"], r["root"], r["sess"], r["group"], r["uid"], r["central"]
        rd, _ = STORES[fam]
        second = bool(r["second_look"])
        if second:
            log_read(pick_key(fam, root, sess), fam, root, sess, "whole menu (stored; re-read with a day filter)", r["plateau"]["cells_all"],
                     f"BUILD passer {uid}: 2024 on the group's days. SECOND LOOK: {r['second_look']}")
            log_read(pick_key(fam, root, sess, "-shift"), fam, root, sess, "random-minute control (stored; re-read with a day filter)",
                     2 * r["plateau"]["cells_all"], f"random-minute control of {uid} on 2024 (SECOND LOOK)")
        ub = JB.load(r["key"])
        up = JB.load(pick_key(fam, root, sess), rd)
        assert ub["meta"]["period"] == "build" and up["meta"]["period"] == "pick"
        base = LB.plateau_units(ub, sess)[""]
        dead = {t["id"]: t["dead"] for t in base}
        tb = JB.side_table(ub, sess, base, g)
        tp = JB.side_table(up, sess, base, g)
        for t in tp:
            t["dead"] = dead[t["id"]]
        pb, pp = LB.plateau(tb), LB.plateau(tp)
        assert pb["member"] == cm, (uid, pb["member"], cm)
        db, dp = {t["id"]: t for t in tb}, {t["id"]: t for t in tp}
        both = [i for i in db if not db[i]["dead"] and db[i]["net"] > 0 and dp[i]["net"] > 0]
        clock = "A" if E.GROUP_TIME[g] == "08:30" else "C"
        xs = JB.cell(up, cm, sess, g)
        xn = JB.cell(up, cm, sess, clock, invert=True)
        st, sn = LB.stats(xs["net"]), LB.stats(xn["net"])
        mean_e = st["net"] / st["trades"] if st["trades"] else 0.0
        mean_n = sn["net"] / sn["trades"] if sn["trades"] else 0.0
        sc = JB.shift_control(fam, root, cm, g, "pick", rd, pick_key(fam, root, sess, "-shift"))
        cal = LB.calendar("pick", root)
        res = {"uid": uid, "family": fam, "root": root, "sess": sess, "group": g, "central": cm, "second_look": r["second_look"],
               "build": pb, "pick": pp, "both_positive": both, "central_pick": st, "pick_table_pass": bool(pp["pass"]),
               "central_pick_positive": bool(st["net"] > 0), "trades_build_plus_pick": r["trades"] + st["trades"],
               "a": bool(r["trades"] + st["trades"] >= LB.MIN_TRADES),
               "nonevent_pick": {"trades": sn["trades"], "net": sn["net"], "mean": round(mean_n, 2), "lift_mean": round(mean_e - mean_n, 2)},
               "shift_pick": {"nets": sc["nets"], "mean": round(sc["mean"], 2), "lift": round(st["net"] - sc["mean"], 2), "trades": sc["trades"]},
               "central_pick_rank": sorted((t["net"] for t in tp if not t["dead"]), reverse=True).index(dp[cm]["net"]) + 1,
               "years_pick": JB.yearly(xs, root, cal)}
        res["go_stress"] = bool(res["pick_table_pass"] and res["central_pick_positive"])
        out[uid] = res
        sh = pp["shares"]
        print(f"{uid} central {cm} | BUILD share>0 {pb['share_pos']} median {pb['median_net']} | 2024 table {'PASS' if pp['pass'] else 'fail'} "
              f"share>0 {pp['share_pos']} of {pp['cells']} median {pp['median_net']} (60/70/80 {pp['verdicts']}) "
              f"by target { {k: v['share_pos'] for k, v in sh['by_target'].items()} } | central 2024: trades {st['trades']} net {st['net']} "
              f"t {st['t']} win {st['win']} (rank {res['central_pick_rank']} of {pp['cells']}) | non-event lift/trade {res['nonevent_pick']['lift_mean']} "
              f"| random-minute lift {res['shift_pick']['lift']} (control {res['shift_pick']['mean']}) | BUILD + 2024 trades "
              f"{res['trades_build_plus_pick']} | both-positive {len(both)} of {pb['cells']} | {'SECOND LOOK' if second else 'first look'}")
        if res["go_stress"]:
            for per in ("build", "pick"):
                key = f"{fam}-{root}-tf{JB.TF}-{sess}-{per}-stress"
                have = (rd / key / "run.json").exists() and cm in {c["id"] for c in json.loads((rd / key / "run.json").read_text())["cells"]}
                if not have:
                    jobs.append({"family": fam, "root": root, "tf": JB.TF, "sess": sess, "period": per, "stress": True, "cells": [cm],
                                 "why": f"stress (2 ticks + 250 ms) of the BUILD central variant of {uid}"})
    seen, uniq = set(), []
    for j in jobs:
        k = (j["family"], j["root"], j["period"], tuple(j["cells"]))
        if k not in seen:
            seen.add(k)
            uniq.append(j)
    (HERE / "pick_judgement.json").write_text(json.dumps(out, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    (HERE / "jobs_stress.json").write_text(json.dumps(uniq, indent=1))
    print("stress jobs", len(uniq))


if __name__ == "__main__":
    main()
