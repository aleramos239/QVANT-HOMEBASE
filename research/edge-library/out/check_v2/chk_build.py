"""CHECKER v2, BUILD: tests (1), (3) for every unit and (2) for every unit with a positive average and >= 50 % positive variants,
with my own code (chk_lib). Reads BUILD stores only. -> chk_build.json
  python chk_build.py"""
import json
import sys
import zlib
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chk_lib as C  # noqa: E402


def my_controls(u):
    if u["src"] in ("ev", "en"):
        return ["days", "shift"]
    if u["src"] == "2a":
        return ["days", "shift" if u["timed"] else "c1"]
    return (["shift"] if u["timed"] else ["c1"]) + (["c2"] if u["l2"] else []) + (["base"] if u["stage_d"] else [])


def sd(uid, what):
    return zlib.crc32(f"checker|{uid}|{what}".encode())


def controls_build(st, u, ids, avg):
    res = {}
    for c in my_controls(u):
        s = sd(u["uid"], c)
        if c == "c1":
            pk = f"c1-{u['root']}-tf{u['tf']}"
            res[c] = C.verdict(avg, C.c1_table(st, u, ids, C.build_store(pk), s), True) if C.exists(pk) else {"pass": False, "why": "no pool"}
        elif c == "shift":
            sk = f"{u['base'] or u['family']}-{u['root']}-tf{u['tf']}-shift"
            res[c] = C.verdict(avg, C.shift_table(C.build_store(sk), u, ids, "build", s), True) if C.exists(sk) else {"pass": False, "why": "no random-minute store"}
        elif c == "c2":
            k1, k2 = f"{u['key']}-c2s1", f"{u['key']}-c2s2"
            res[c] = (C.verdict(avg, C.c2_table(C.build_store(k1), C.build_store(k2), u, ids, "build", s), True)
                      if C.exists(k1) and C.exists(k2) else {"pass": False, "why": "no shuffled-book store"})
        elif c == "base":
            res[c] = C.base_test(st, C.build_store(f"{u['base']}-{u['root']}-tf{u['tf']}"), u, ids)
        elif c == "days":
            res[c] = C.days_test(st, u, ids, s, True)
    return res


def judge_store(job):
    key, us = job
    st = C.build_store(key)
    out = []
    for u in us:
        rows = C.build_rows(st, u)
        ts = C.tstats(rows)
        nb, npk = len(C.scope_days(u, "build")), len(C.scope_days(u, "pick"))
        r = {"uid": u["uid"], "src": u["src"], "cells": ts["cells"], "controls": my_controls(u), "days_build": nb, "days_2024": npk}
        if not ts["cells"]:
            r.update(t1=False, t1_strict=False, t2=None, t3=False, build_pass=False)
            out.append(r)
            continue
        t1 = bool(ts["share"] >= 0.6 - 1e-12 and ts["avg"] > 0)
        reach = ts["avg_trades"] * (1 + npk / nb) if nb else 0.0
        t3 = bool(reach >= 100)
        r.update(share=ts["share"], avg=ts["avg"], median=ts["median"], avg_trades=ts["avg_trades"], t1=t1,
                 t1_strict=bool(ts["share"] > 0.6 + 1e-12 and ts["avg"] > 0), reach=reach, t3=t3)
        t2, det = None, {}
        if ts["avg"] > 0 and ts["share"] >= 0.5:
            det = controls_build(st, u, ts["ids"], ts["avg"])
            t2 = all(v["pass"] for v in det.values())
        r.update(t2=t2, det=det, build_pass=bool(t1 and t2 and t3))
        out.append(r)
    return out


def main():
    us = C.units()
    for u in us:
        assert my_controls(u) == u["controls"], (u["uid"], my_controls(u), u["controls"])
        u.pop("A")
    by = {}
    for u in us:
        by.setdefault(u["key"], []).append(u)
    jobs = sorted(by.items(), key=lambda kv: -len(kv[1]))
    with Pool(8) as pool:
        rows = [r for part in pool.imap_unordered(judge_store, jobs, chunksize=1) for r in part]
    (C.OUT / "chk_build.json").write_text(json.dumps(rows, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    print("units", len(rows), "(1)", sum(r["t1"] for r in rows), "(1)+(3)", sum(r["t1"] and r["t3"] for r in rows),
          "(2) drawn", sum(r["t2"] is not None for r in rows), "pass all three", sum(r["build_pass"] for r in rows))


if __name__ == "__main__":
    main()
