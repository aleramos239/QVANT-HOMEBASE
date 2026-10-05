"""ADMISSION v2 PLACEBO: the whole v2 procedure on the random-entry stores. Nothing here is a strategy: every pass is luck.
A placebo unit = the random-entry table (32 exit cells) of ONE seed of runs/c1-<root>-tf<tf> in ONE session; its c1 control is the
OTHER seed's pool (one seed, not two: the unit's own trades cannot be its control). 3 markets x 4 bar sizes x 7 sessions x 2 seeds
= 168 units. Same tests, same code (v2.py), same thresholds.
  python out/v2/placebo.py build            tests (1)-(3) on BUILD -> placebo_build.csv, jobs_placebo_pick.json
  python out/v2/placebo.py pick             tests (4)-(5) on 2024 (random stores run on 2024: control cells) -> jobs_placebo_stress.json
  python out/v2/placebo.py stress           test (6) + the surviving set -> placebo.csv, placebo_counts.json"""
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
ROOTS, TFS = ("NQ", "ES", "GC"), ("1", "5", "15", "30")


def punits() -> list:
    return [{"uid": f"placebo-c1-{r}-tf{tf}|{s}|seed{sa}", "key": f"c1-{r}-tf{tf}", "root": r, "tf": tf, "sess": s, "sa": sa,
             "sb": 2 if sa == 1 else 1, "label": "", "group": None, "side": None, "family": "random"}
            for r in ROOTS for tf in TFS for s in LB.SESS7 for sa in (1, 2)]


def ptable(st: dict, u: dict, dead_from=None) -> list:
    rows = [dict(r) for r in LB.session_table(st, u["sess"]) if r["id"].startswith(f"s{u['sa']}_")]
    alive = {r["vi"] for r in rows if r["trades"]}
    for r in rows:
        r["dead"] = r["vi"] not in alive if dead_from is None else dead_from.get(r["id"], False)
    return rows


def judge(st: dict, u: dict, period: str, need_p: bool, dead_from=None) -> dict:
    rows = ptable(st, u, dead_from)
    ts = V.table_stats(rows)
    out = {"cells": ts["cells"], "share_pos": ts["share_pos"], "avg_net": ts["avg_net"], "median_net": ts["median_net"],
           "avg_trades": ts["avg_trades"], "ids": ts["ids"], "dead": {r["id"]: r["dead"] for r in rows}}
    if ts["cells"] and ts["avg_net"] > 0 and (not need_p or ts["share_pos"] >= 0.5):
        c = V.c1_table(st, u, ts["ids"], st, V.seed_of(u["uid"], f"{period}-c1"), seeds=(u["sb"],))
        out["c1"] = V.verdict(ts["avg_net"], c, need_p)
    return out


def build() -> None:
    rows, jobs = [], []
    for u in punits():
        st = V.store(u["key"], period="build")
        j = judge(st, u, "build", True)
        nb, npk = len(V.scope_days(u, "build")), len(V.scope_days(u, "pick"))
        t1 = bool(j["cells"] and j["share_pos"] >= V.SHARE - 1e-12 and j["avg_net"] > 0)
        t3 = bool(j["avg_trades"] * (1 + npk / nb) >= LB.MIN_TRADES)
        t2 = bool(j.get("c1", {}).get("pass"))
        rows.append({"uid": u["uid"], "root": u["root"], "tf": u["tf"], "sess": u["sess"], "seed": u["sa"], "cells": j["cells"],
                     "share_pos": j["share_pos"], "avg_net": j["avg_net"], "avg_trades": j["avg_trades"], "t1": t1, "t2": t2, "t3": t3,
                     "lift": j.get("c1", {}).get("lift"), "p_beat": j.get("c1", {}).get("p_beat"), "build_pass": t1 and t2 and t3})
    with (V.OUT / "placebo_build.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    seen = set()
    for r in rows:
        if r["build_pass"] and (r["root"], r["tf"], r["sess"]) not in seen:
            seen.add((r["root"], r["tf"], r["sess"]))
            jobs.append({"c1": True, "root": r["root"], "tf": r["tf"], "sess": r["sess"], "period": "pick",
                         "why": "v2 PLACEBO: random-entry store of a placebo unit that passed BUILD (a control, no candidate)"})
    (V.OUT / "jobs_placebo_pick.json").write_text(json.dumps(jobs, indent=1))
    for root in ROOTS:
        R = [r for r in rows if r["root"] == root]
        print(root, "placebo units", len(R), "| (1)", sum(r["t1"] for r in R), "| (1)+(3)", sum(r["t1"] and r["t3"] for r in R),
              "| (1)+(2)+(3)", sum(r["build_pass"] for r in R))
    print("BUILD passers", [r["uid"] for r in rows if r["build_pass"]], "| pick jobs", len(jobs))


def find(key: str):
    d = V.find_pick(key)
    return None if d is None else V.store(key, d, "pick")


def pick() -> None:
    B = [r for r in csv.DictReader((V.OUT / "placebo_build.csv").open()) if r["build_pass"] == "True"]
    U = {u["uid"]: u for u in punits()}
    out, jobs, seen = [], [], set()
    for r in B:
        u = U[r["uid"]]
        bst = V.store(u["key"], period="build")
        dead = {x["id"]: x["dead"] for x in ptable(bst, u)}
        pst = V.store(f"{u['key']}-{u['sess']}-pick", V.RV, "pick")
        j = judge(pst, u, "pick", False, dead)
        t4 = bool(j["cells"] and j["avg_net"] > 0 and j["median_net"] > 0)
        t5 = bool(j.get("c1", {}).get("pass"))
        out.append({"uid": u["uid"], "t4": t4, "t5": t5, "avg_net_2024": j["avg_net"], "median_net_2024": j["median_net"],
                    "share_pos_2024": j["share_pos"], "lift_2024": j.get("c1", {}).get("lift"), "avg_trades_2024": j["avg_trades"]})
        if t4 and t5 and (u["root"], u["tf"], u["sess"]) not in seen:
            seen.add((u["root"], u["tf"], u["sess"]))
            for per in ("pick", "build"):
                jobs.append({"c1": True, "root": u["root"], "tf": u["tf"], "sess": u["sess"], "period": per, "stress": True,
                             "why": "v2 PLACEBO: stress of a random-entry store (a control, no candidate)"})
    (V.OUT / "placebo_pick.json").write_text(json.dumps(out, indent=1))
    (V.OUT / "jobs_placebo_stress.json").write_text(json.dumps(jobs, indent=1))
    print("placebo on 2024:", len(out), "opened | (4)", sum(o["t4"] for o in out), "| (4)+(5)", sum(o["t4"] and o["t5"] for o in out), "| stress jobs", len(jobs))


def stress() -> None:
    B = {r["uid"]: r for r in csv.DictReader((V.OUT / "placebo_build.csv").open())}
    P = {o["uid"]: o for o in json.loads((V.OUT / "placebo_pick.json").read_text())}
    U = {u["uid"]: u for u in punits()}
    rows = []
    for uid, b in B.items():
        r = dict(b)
        p = P.get(uid)
        r.update(opened_2024=bool(p), t4=bool(p and p["t4"]), t5=bool(p and p["t5"]), t6=False, survivors=0, passed=False)
        if p and p["t4"] and p["t5"]:
            u = U[uid]
            bst = V.store(u["key"], period="build")
            dead = {x["id"]: x["dead"] for x in ptable(bst, u)}
            ps = V.store(f"{u['key']}-{u['sess']}-pick-stress", V.RV, "pick")
            bs = V.store(f"{u['key']}-{u['sess']}-build-stress", V.RV, "build")
            pst = V.store(f"{u['key']}-{u['sess']}-pick", V.RV, "pick")
            ts = V.table_stats(ptable(ps, u, dead))
            r["t6"] = bool(ts["cells"] and ts["avg_net"] > 0)
            net = lambda s, cid: float(V.cellx(s, cid, u["sess"])["net"].sum())  # noqa: E731
            ids = [x["id"] for x in ptable(bst, u) if not x["dead"]]
            r["survivors"] = sum(1 for c in ids if net(bst, c) > 0 and net(pst, c) > 0 and net(bs, c) > 0 and net(ps, c) > 0)
            tr = float(b["avg_trades"]) + float(p["avg_trades_2024"])
            r["passed"] = bool(r["t6"] and r["survivors"] > 0 and tr >= LB.MIN_TRADES)
        rows.append(r)
    with (V.OUT / "placebo.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    c = {"units": len(rows), "t1": sum(r["t1"] == "True" for r in rows), "build_pass": sum(r["build_pass"] == "True" for r in rows),
         "t4": sum(r["t4"] for r in rows), "t4_t5": sum(r["t4"] and r["t5"] for r in rows), "t6": sum(r["t6"] for r in rows),
         "all_six": sum(r["passed"] for r in rows), "passers": [r["uid"] for r in rows if r["passed"]]}
    (V.OUT / "placebo_counts.json").write_text(json.dumps(c, indent=1))
    print(json.dumps(c))


if __name__ == "__main__":
    {"build": build, "pick": pick, "stress": stress}[sys.argv[1]]()
