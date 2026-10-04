#!/usr/bin/python3
"""Part 4: independent walk of pass 3's top fast-pass configs per firm (and the best overall speed cells), vs the candidates.csv numbers."""
import csv, json, re, sys, time
import numpy as np
from pathlib import Path
import verify_indep as V

R = Path(__file__).resolve().parent
OUT = R / "out"
rows = list(csv.DictReader(open(OUT / "candidates.csv")))
led = {"3": list(csv.DictReader(open(OUT / "a3p3_snap_ledger.csv"))), "2": list(csv.DictReader(open(OUT / "a3p2_snap_ledger.csv")))}


def src_of(r):
    """key -> tester source, from the ledger snapshot of the row's pass (own lookup); also confirms the params recorded there."""
    key = r["key"]
    for x in led[r["pass"]]:
        if "#" in key:
            k, c = key.split("#")
            if x["key"] == k and x["cell"] == c and x["grid_id"] and x["stage"] == "sizing":
                p = json.loads(x["params_json"])
                cp = json.loads(r["params"])
                cp2 = {a: b for a, b in cp.items()}
                pp = {a: b for a, b in p.items() if a not in ("tf", "sess")}
                ok = all(abs(float(pp.get(a, 0)) - float(b)) < 1e-9 if isinstance(b, (int, float)) else pp.get(a) == b for a, b in cp2.items() if a in pp)
                return f"{x['grid_id']}#{c}", ok
        elif x["stage"] == "screen" and x["key"] == key and x["run_id"]:
            return x["run_id"], True
    return None, False


def parse(s):
    m = re.match(r"m(\d+) L(\S+) K(\S+) S(\S+) T(\S+) (TT|tt-)", s)
    n, L, K, S, T, tt = m.groups()
    f = lambda v: 0 if v == "-" else int(v)
    return int(n), {"day_lock": f(L), "day_take": f(K), "day_stop": f(S), "max_day_tr": f(T), "target_take": 1 if tt == "TT" else 0}


FIRMS = ["lucid", "lucidpro", "lucidpro_nodll", "apex", "apex_eod"]
PM = {"lucid": "realized", "lucidpro": "realized", "lucidpro_nodll": "realized", "apex": "intraday", "apex_eod": "intraday"}
sel = []
for f in FIRMS:
    fr = [r for r in rows if r["firm"] == f]
    for pool, tag in ((([r for r in fr if r["fastpass"] == "1"]), "fp"), (fr, "all")):
        for keyf, name in (("sp1_p1", "P1"), ("sp3_p3", "P3"), ("p5", "P5")):
            top = sorted(pool, key=lambda r: -float(r[keyf] or 0))[:2 if tag == "fp" else 1]
            for r in top:
                sel.append((f, tag, name, r))
seen, out = set(), []
CAL = None
for f, tag, name, r in sel:
    k = (f, r["config"], r["pass"])
    src, ok = src_of(r)
    if src is None:
        print("UNRESOLVED", f, r["config"]); continue
    sess = r["sess"]
    cells = {"P5": (int(r["micros"]), {a: int(r[a]) for a in ("day_lock", "day_take", "day_stop", "max_day_tr", "target_take")}),
             "P1": parse(r["sp1_rules"]), "P3": parse(r["sp3_rules"])}
    rep = {"P5": {"p5": float(r["p5"]), "p1": float(r["p1"]), "p3": float(r["p3"]), "eod_p5": float(r["eod_p5"]), "intr_p5": float(r["intr_p5"]), "bust5": float(r["bust5"])},
           "P1": {"p1": float(r["sp1_p1"] or 0), "bust5": float(r["sp1_bust5"] or 0)}, "P3": {"p3": float(r["sp3_p3"] or 0), "bust5": float(r["sp3_bust5"] or 0)}}
    rec = {"firm": f, "pick": f"{tag}:{name}", "config": r["config"], "pass": r["pass"], "sess": sess, "fastpass": r["fastpass"], "ledger_params_match": ok, "cells": {}}
    for cn in ("P1", "P3", "P5"):
        n, rules = cells[cn]
        sp = V.Spec(f, [(src, sess, n)], rules, CAL)
        CAL = CAL or sp.cal
        arr = sp.arrays()
        mm = {m: V.metrics(*arr[m]) for m in V.MODELS}
        pm = PM[f]
        d = {"micros": n, "rules": rules, "mine": mm, "reported": rep[cn]}
        # diffs
        diffs = []
        for kk, v in rep[cn].items():
            if kk == "bust5":
                diffs.append(abs(mm[pm]["bust5"] - v))
            elif kk in ("p1", "p3", "p5"):
                diffs.append(abs(mm[pm][kk] - v))
            elif kk == "eod_p5":
                diffs.append(abs(mm["eod"]["p5"] - v))
            elif kk == "intr_p5":
                diffs.append(abs(mm["intraday"]["p5"] - v))
        d["maxdiff"] = max(diffs)
        # raw net of the single member at 1 NQ and under the cell's rules
        d["net_rules"] = sum(sp.day(i).tot for i in range(sp.D))
        d["raw_net"] = V.member_nets(sp)[0]
        d["raw_overlap"] = V.raw_overlap(sp)["max_concurrent_micros"]
        # year concentration of net under rules
        import datetime as dt
        yn = {}
        for i, o in enumerate(sp.cal):
            y = dt.date.fromordinal(o).year
            yn[y] = yn.get(y, 0.0) + sp.day(i).tot
        d["year_net"] = {int(y): round(v) for y, v in yn.items()}
        rec["cells"][cn] = d
    out.append(rec)
    c = rec["cells"]
    print(f"{f:14s} {tag:3s}:{name} {r['config'][:42]:42s} {sess:6s} | " + " | ".join(
        f"{cn} m{c[cn]['micros']} P{cn[1]}={c[cn]['mine'][PM[f]]['p'+cn[1]]:.3f}(rep {list(c[cn]['reported'].values())[0]:.3f}) eod/intr P5 {c[cn]['mine']['eod']['p5']:.2f}/{c[cn]['mine']['intraday']['p5']:.2f} diff {c[cn]['maxdiff']:.4f}" for cn in ("P1", "P3", "P5")), flush=True)
json.dump(out, open(OUT / "verify_part4.json", "w"), indent=1, default=str)
