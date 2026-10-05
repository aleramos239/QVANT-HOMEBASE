"""ADMISSION v2, step 1 (BUILD only): tests (1)-(3) at TABLE level for every stored unit (method: v2.py docstring).
Reads runs/ (BUILD stores; every store's period is asserted). Reads no 2024 / 2025+ P&L (2024 enters as a COUNT of calendar days).
Test (2) is computed for every unit whose average variant is positive and whose share of positive variants is >= 50 % (so the
near-misses of test (1) are known); other units fail (1) and their control is not drawn.
  python out/v2/judge_build.py  -> out/v2/build_units.csv / build_units.json"""
from __future__ import annotations

import csv
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v2 as V  # noqa: E402

LB = V.LB


def controls_build(st: dict, u: dict, ts: dict) -> dict:
    """Every control of the unit on BUILD -> {name: verdict dict}."""
    ids, avg, res = ts["ids"], ts["avg_net"], {}
    for c in u["controls"]:
        sd = V.seed_of(u["uid"], f"build-{c}")
        if c == "c1":
            pk = f"c1-{u['root']}-tf{u['tf']}"
            res[c] = V.verdict(avg, V.c1_table(st, u, ids, V.store(pk, period="build"), sd), True) if V.has(pk) else {"pass": False, "why": "no pool"}
        elif c == "shift":
            sk = f"{u['base'] or u['family']}-{u['root']}-tf{u['tf']}-shift"
            res[c] = V.verdict(avg, V.shift_table(V.store(sk, period="build"), u, ids, "build", sd), True) if V.has(sk) else {"pass": False, "why": "no random-minute store"}
        elif c == "c2":
            k1, k2 = f"{u['key']}-c2s1", f"{u['key']}-c2s2"
            if V.has(k1) and V.has(k2):
                res[c] = V.verdict(avg, V.c2_table(V.store(k1, period="build"), V.store(k2, period="build"), u, ids, "build", sd), True)
            else:
                res[c] = {"pass": False, "why": "no shuffled-book store on disk"}
        elif c == "base":
            bk = f"{u['base']}-{u['root']}-tf{u['tf']}"
            res[c] = V.base_test(st, V.store(bk, period="build"), u, ids)
        elif c == "days":
            res[c] = V.days_test(st, u, ids, sd, True)
    return res


def judge_store(job: tuple) -> list:
    key, us = job
    st = V.store(key, period="build")
    out = []
    for u in us:
        rows = V.table(st, u)
        ts = V.table_stats(rows)
        nb, npk = len(V.scope_days(u, "build")), len(V.scope_days(u, "pick"))
        r = {"uid": u["uid"], "src": u["src"], "key": key, "family": u["family"], "root": u["root"], "tf": u["tf"], "sess": u["sess"],
             "label": u["label"], "group": u["group"] or "", "side": u["side"] or "", "timed": u["timed"], "l2": u["l2"],
             "stage_d": u["stage_d"], "weak": u["weak"], "penalty": u["penalty"], "controls": "+".join(u["controls"]),
             "cells": ts["cells"], "dead": ts["dead"], "dup": ts["dup"], "share_pos": ts["share_pos"], "avg_net": ts["avg_net"],
             "median_net": ts["median_net"], "avg_trades": ts["avg_trades"], "days_build": nb, "days_2024": npk}
        if not ts["cells"]:
            r.update(t1=False, t2=None, t3=False, build_pass=False, fail="1,3")
            out.append(r)
            continue
        r["v60"], r["v70"], r["v80"] = ts["v60"], ts["v70"], ts["v80"]
        r["exact60"] = abs(ts["share_pos"] - 0.6) < 1e-9
        t1 = bool(ts["share_pos"] >= V.SHARE - 1e-12 and ts["avg_net"] > 0)
        reach = ts["avg_trades"] * (1.0 + npk / nb) if nb else 0.0
        t3 = bool(reach >= LB.MIN_TRADES)
        r.update(t1=t1, t3=t3, reach_trades=round(reach, 1),
                 reach_old_rule=round(ts["avg_trades"] + npk, 1) if (u["group"] or u["side"]) else "")
        t2, det = None, {}
        if ts["avg_net"] > 0 and ts["share_pos"] >= 0.5:
            det = controls_build(st, u, ts)
            t2 = all(v["pass"] for v in det.values())
            for c, v in det.items():
                r[f"{c}_pass"] = v["pass"]
                for k in ("lift", "p_beat", "ctl_mean", "lift_per_trade", "per_trade", "unfiltered_per_trade", "base_per_trade", "fallback_share", "why"):
                    if k in v:
                        r[f"{c}_{k}"] = v[k]
            xs = [V.cellx(st, cid, u["sess"], u) for cid in ts["ids"]]
            r["fast_profit_share"] = V.fast_share(xs)["fast_profit_share"]
        r.update(t2=t2, build_pass=bool(t1 and t2 and t3),
                 fail=",".join(n for n, ok in (("1", t1), ("2", bool(t2)), ("3", t3)) if not ok), detail=json.dumps(det))
        out.append(r)
    return out


def main():
    us = V.units()
    by: dict = {}
    for u in us:
        by.setdefault(u["key"], []).append(u)
    jobs = sorted(by.items(), key=lambda kv: -len(kv[1]))
    with Pool(8) as pool:
        rows = [r for part in pool.imap_unordered(judge_store, jobs, chunksize=1) for r in part]
    order = {u["uid"]: i for i, u in enumerate(us)}
    rows.sort(key=lambda r: order[r["uid"]])
    assert len(rows) == len(us)
    cols = []
    for r in rows:
        cols += [c for c in r if c not in cols and c != "detail"]
    with (V.OUT / "build_units.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    (V.OUT / "build_units.json").write_text(json.dumps(rows, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    for src in ("s1", "r1", "ev", "en", "2a"):
        R = [r for r in rows if r["src"] == src]
        print(src, "units", len(R), "| (1)", sum(r["t1"] for r in R), "| (1)+(3)", sum(r["t1"] and r["t3"] for r in R),
              "| (2) drawn", sum(r["t2"] is not None for r in R), "| (1)+(2)", sum(bool(r["t1"] and r["t2"]) for r in R),
              "| all three", sum(r["build_pass"] for r in R), flush=True)
    for r in rows:
        if r["build_pass"]:
            print("PASS", r["uid"], "cells", r["cells"], "share", round(r["share_pos"], 3), "avg", round(r["avg_net"]), "trades", round(r["avg_trades"]),
                  {k: r[k] for k in r if k.endswith(("_lift", "_p_beat", "_lift_per_trade"))})


if __name__ == "__main__":
    main()
