"""ADMISSION v2, step 2b: 2024 ON ITS OWN for every unit that passed (1)-(3) on BUILD (method: v2.py docstring).
  python out/v2/judge_pick.py pick     tests (4) and (5) -> pick_units.json, jobs_stress_pick.json (whole menu, 2024, stress)
  python out/v2/judge_pick.py stress   test (6) -> jobs_stress_build.json (BUILD stress of the variants positive in BUILD,
                                       2024 and 2024 stress)
  python out/v2/judge_pick.py final    surviving sets, the default (middle survivor by BUILD net), the final verdict -> final.json
2024 tables use the BUILD dead flags. A 2024 store holds every live, non-author variant of the unit."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v2 as V  # noqa: E402

LB = V.LB


def passers() -> list:
    B = {r["uid"]: r for r in json.loads((V.OUT / "build_units.json").read_text())}
    return [(u, B[u["uid"]]) for u in V.units() if B[u["uid"]]["build_pass"]]


def table_on(st: dict, u: dict, ref_rows: list) -> list:
    """The unit's table on another store (2024, stress, a control): the BUILD rows' ids, flags and order; net / trades / sig
    from `st` (the unit's session and day filter)."""
    out = []
    for r in ref_rows:
        if r["id"] not in st["_idx"]:
            assert r.get("dead") or r.get("info"), (r["id"], st["meta"].get("key"))
            continue
        x = V.cellx(st, r["id"], u["sess"], u)
        s = LB.stats(x["net"])
        out.append({**{k: r.get(k) for k in ("id", "vi", "xi", "stop_mode", "tgt_r", "dead", "info")}, "net": s["net"], "trades": s["trades"],
                    "t": s["t"], "sig": LB.trade_sig(x)})
    return out


def pick_store(key: str, dirs=None):
    for d in (dirs or V.PICK_DIRS):
        if (d / key / "run.json").exists():
            return V.store(key, d, "pick")
    return None


def controls_pick(pst: dict, u: dict, ts: dict) -> dict:
    ids, avg, res = ts["ids"], ts["avg_net"], {}
    for c in u["controls"]:
        sd = V.seed_of(u["uid"], f"pick-{c}")
        if c == "c1":
            pu = pick_store(f"c1-{u['root']}-tf{u['tf']}-{u['sess']}-pick")
            res[c] = V.verdict(avg, V.c1_table(pst, u, ids, pu, sd), False) if pu else {"pass": False, "why": "no 2024 pool"}
        elif c == "shift":
            su = pick_store(f"{u['base'] or u['family']}-{u['root']}-tf{u['tf']}-{u['sess']}-pick-shift")
            res[c] = V.verdict(avg, V.shift_table(su, u, ids, "pick", sd), False) if su else {"pass": False, "why": "no 2024 random-minute store"}
        elif c == "c2":
            s1, s2 = (pick_store(f"{u['key']}-{u['sess']}-pick-c2s{k}") for k in (1, 2))
            res[c] = V.verdict(avg, V.c2_table(s1, s2, u, ids, "pick", sd), False) if s1 and s2 else {"pass": False, "why": "no 2024 shuffled-book store"}
        elif c == "base":
            bs = pick_store(f"{u['base']}-{u['root']}-tf{u['tf']}-{u['sess']}-pick")
            res[c] = V.base_test(pst, bs, u, ids) if bs else {"pass": False, "why": "no 2024 base store"}
        elif c == "days":
            res[c] = V.days_test(pst, u, ids, sd, False)
    return res


def menu_ids(bst: dict, u: dict) -> list:
    return [r["id"] for r in V.base_rows(bst, u) if not r.get("info") and not r.get("dead")]


def do_pick() -> None:
    out, groups = {}, {}
    for u, b in passers():
        bst = V.store(u["key"], period="build")
        brows = V.table(bst, u)
        pst = pick_store(f"{u['key']}-{u['sess']}-pick")
        assert pst is not None, u["uid"]
        prows = table_on(pst, u, brows)
        ts = V.table_stats(prows)
        t4 = bool(ts["cells"] and ts["avg_net"] > 0 and ts["median_net"] > 0)
        det = controls_pick(pst, u, ts) if ts["cells"] else {}
        t5 = bool(det) and all(v["pass"] for v in det.values())
        tr = b["avg_trades"] + ts["avg_trades"]
        xs = [V.cellx(pst, cid, u["sess"], u) for cid in ts["ids"]]
        o = {"uid": u["uid"], "store": str(pst["meta"].get("key")), "cells": ts["cells"], "share_pos": ts["share_pos"], "avg_net": ts["avg_net"],
             "median_net": ts["median_net"], "avg_trades": ts["avg_trades"], "v60": ts.get("v60"), "v70": ts.get("v70"), "v80": ts.get("v80"),
             "t4": t4, "t5": t5, "controls": det, "trades_build_plus_2024": round(tr, 1), "t3_final": bool(tr >= LB.MIN_TRADES),
             "fast_profit_share": V.fast_share(xs)["fast_profit_share"] if xs else None}
        out[u["uid"]] = o
        lifts = {c: (v.get("lift", v.get("lift_per_trade"))) for c, v in det.items()}
        print(f"{u['uid']:42s} 2024: share>0 {ts['share_pos']:.3f} avg {ts['avg_net']:9.0f} median {ts['median_net']:9.0f} trades {ts['avg_trades']:6.1f} "
              f"| (4) {'PASS' if t4 else 'fail'} (5) {'PASS' if t5 else 'fail'} {lifts} | BUILD+2024 trades {tr:.0f}", flush=True)
        if t4 and t5:
            g = groups.setdefault((u["key"], u["sess"]), {"u": u, "ids": set(), "uids": [], "oco": bool(bst["meta"].get("both_sides_declared"))})
            g["ids"] |= set(menu_ids(bst, u))
            g["uids"].append(u["uid"])
    jobs = [{"family": g["u"]["family"], "root": g["u"]["root"], "tf": g["u"]["tf"], "sess": sess, "period": "pick", "stress": True,
             "oco": g["oco"], "cells": sorted(g["ids"]),
             "why": f"v2 test (6): 2 ticks + 250 ms{' + 100 ms late sibling cancel' if g['oco'] else ''}, whole menu of {', '.join(g['uids'])}"}
            for (key, sess), g in sorted(groups.items())]
    (V.OUT / "pick_units.json").write_text(json.dumps(out, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    (V.OUT / "jobs_stress_pick.json").write_text(json.dumps(jobs, indent=1))
    n = len(out)
    print(f"opened on 2024: {n} | (4) {sum(o['t4'] for o in out.values())} | (5) {sum(o['t5'] for o in out.values())} | (4)+(5) "
          f"{sum(o['t4'] and o['t5'] for o in out.values())} | stress jobs {len(jobs)}, cells {sum(len(j['cells']) for j in jobs)}")


def do_stress() -> None:
    P = json.loads((V.OUT / "pick_units.json").read_text())
    groups = {}
    for u, b in passers():
        o = P[u["uid"]]
        if not (o["t4"] and o["t5"]):
            continue
        bst = V.store(u["key"], period="build")
        brows = V.table(bst, u)
        pst = pick_store(f"{u['key']}-{u['sess']}-pick")
        sst = pick_store(f"{u['key']}-{u['sess']}-pick-stress", [V.RV])
        assert sst is not None, u["uid"]
        ts = V.table_stats(table_on(sst, u, brows))
        o.update(stress_avg_net=ts["avg_net"], stress_median_net=ts["median_net"], stress_share_pos=ts["share_pos"],
                 t6=bool(ts["cells"] and ts["avg_net"] > 0), oco_cancel_ms=sst["meta"].get("oco_cancel_ms", 0))
        net = lambda s, cid: float(V.cellx(s, cid, u["sess"], u)["net"].sum())  # noqa: E731
        ids = V.table_stats(brows)["ids"]
        cand = [c for c in ids if net(bst, c) > 0 and net(pst, c) > 0 and net(sst, c) > 0]
        o["survive_before_build_stress"] = cand
        print(f"{u['uid']:42s} 2024 stress: avg {ts['avg_net']:9.0f} (base {o['avg_net']:9.0f}) share>0 {ts['share_pos']:.3f} | (6) "
              f"{'PASS' if o['t6'] else 'fail'} | variants positive in BUILD, 2024 and 2024 stress: {len(cand)} of {len(ids)}", flush=True)
        if o["t6"] and cand:
            g = groups.setdefault((u["key"], u["sess"]), {"u": u, "ids": set(), "uids": [], "oco": bool(bst["meta"].get("both_sides_declared"))})
            g["ids"] |= set(cand)
            g["uids"].append(u["uid"])
    jobs = [{"family": g["u"]["family"], "root": g["u"]["root"], "tf": g["u"]["tf"], "sess": sess, "period": "build", "stress": True,
             "oco": g["oco"], "cells": sorted(g["ids"]), "why": f"v2 surviving set: BUILD stress of {', '.join(g['uids'])}"}
            for (key, sess), g in sorted(groups.items())]
    (V.OUT / "pick_units.json").write_text(json.dumps(P, indent=1))
    (V.OUT / "jobs_stress_build.json").write_text(json.dumps(jobs, indent=1))
    print(f"(6) passes {sum(bool(o.get('t6')) for o in P.values())} | BUILD stress jobs {len(jobs)}, cells {sum(len(j['cells']) for j in jobs)}")


def do_final() -> None:
    P = json.loads((V.OUT / "pick_units.json").read_text())
    out = {}
    for u, b in passers():
        o = P[u["uid"]]
        r = {"uid": u["uid"], "name": V.member_name(u), "t4": o["t4"], "t5": o["t5"], "t6": bool(o.get("t6")), "t3_final": o["t3_final"],
             "survivors": [], "default": None, "admit": False}
        if o["t4"] and o["t5"] and o.get("t6") and o.get("survive_before_build_stress"):
            bst = V.store(u["key"], period="build")
            brows = {x["id"]: x for x in V.table(bst, u)}
            bs = V.store(f"{u['key']}-{u['sess']}-build-stress", V.RV, "build")
            net = lambda s, cid: float(V.cellx(s, cid, u["sess"], u)["net"].sum())  # noqa: E731
            surv = [c for c in o["survive_before_build_stress"] if net(bs, c) > 0]
            order = sorted(surv, key=lambda c: (round(brows[c]["net"], 2), brows[c]["vi"], brows[c]["xi"]))
            r["survivors"] = order
            if order:
                r["default"] = order[(len(order) - 1) // 2]
                r["default_build_net"] = brows[r["default"]]["net"]
            r["admit"] = bool(order and o["t3_final"])
        r["failed"] = [k for k, ok in (("4", r["t4"]), ("5", r["t5"]), ("6", r["t6"]), ("3 (BUILD + 2024 trades)", r["t3_final"]),
                                       ("no surviving variant", bool(r["survivors"]) or not (r["t4"] and r["t5"] and r["t6"]))) if not ok]
        out[u["uid"]] = r
        print(f"{u['uid']:42s} {'ADMIT' if r['admit'] else 'no   '} survivors {len(r['survivors']):3d} default {r['default']} failed {r['failed']}")
    (V.OUT / "final.json").write_text(json.dumps(out, indent=1))
    print("pass all six:", sum(r["admit"] for r in out.values()), "of", len(out))


if __name__ == "__main__":
    {"pick": do_pick, "stress": do_stress, "final": do_final}[sys.argv[1]]()
