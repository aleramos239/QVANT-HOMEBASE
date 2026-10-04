#!/usr/bin/python3
"""Apex MAE-cut compliance bound (UNCONFIRMED rule set): re-search the top Apex-compliant configs of out/candidates.csv with the size capped so that the
share of trades whose worst open loss reaches the PA negative-P&L floor ($750 = 30% x max(start-of-day profit, $2,500 DD)) is <= 2% (Apex rule:
open loss <= 30% of the start-of-day profit balance; a config that routinely hits it is non-compliant). Rule grid = the firm's pass-3 grid with the
micros axis replaced by the sizes that pass; stable P5 / P1 / P3 under the primary model (intraday), eod bound, vs the unrestricted candidate.
Run: PYTHONPATH=~/ramos-quant-homebase PP_PILOT=es /usr/bin/python3 a3p3_apexmae.py [--top 12] [--workers 3]  ->  out/a3p3_apexmae.csv"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E          # noqa: E402
import screen_analyze as SA   # noqa: E402
import a3_rules as A1         # noqa: E402
import a3_pass2 as A2         # noqa: E402
import a3p3 as P3             # noqa: E402

OUT = E.D / "out"
SIZES = [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30]
FLOOR = 750.0


def task(a):
    firm, fam, tf, key, sess, params, src, free = a
    import json
    P3.LP.gate()
    t = A2.load_src(src)
    mk = t.sess == E.SESS_CODE[sess]
    ok = [m for m in SIZES if (t.mae[mk] * m / 10.0 >= FLOOR).mean() <= 0.02]
    if not ok:
        return [dict(firm=firm, fam=fam, tf=tf, key=key, sess=sess, micros_ok="", note="no size passes", **free)]
    base = dict(P3.A2.GR[firm])
    P3.A2.GR[firm] = dict(base, micros=ok)
    try:
        prof = E.profile_from(fam, dict(json.loads(params), tf=tf))
        pool = A2.pool_of(P3.resolve(prof)["srcs"])
        cal = SA.cal_for(t, pool)
        D = len(cal)
        port = A2.port_of(t, np.flatnonzero(mk), cal)
        prim = E.primary_model(firm)
        S = P3.search3(port, D, firm, prim)
        nr = S["nr"]
        out = dict(firm=firm, fam=fam, tf=tf, key=key, sess=sess, micros_ok=" ".join(map(str, ok)), m_max=max(ok), **free)
        for k, mod in enumerate(P3.M3):
            sv = A1.stable(S["P5"][k])
            ci = A2.pick(sv, nr)
            out[f"{mod}_p5_stable"] = float(sv[ci])
            out[f"{mod}_p5_rawmax"] = float(S["P5"][k].max())
            if mod == prim:
                out["cell"] = " ".join(str(x) for x in P3.cell_of(firm, ci))
                out["bust5"] = float(S["B5"][k][ci])
        for nm, kk in (("p1", "P1"), ("p3", "P3")):
            sv = A1.stable(S[kk])
            out[f"{nm}_stable"] = float(sv[A2.pick(sv, nr)])
            out[f"{nm}_rawmax"] = float(S[kk].max())
        return [out]
    finally:
        P3.A2.GR[firm] = base


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args(argv)
    srcs = {s[3]: s[0] for s in P3.sources3()}
    srcs.update({s[3]: s[0] for s in A2.sources() if s[3].startswith("screen-")})
    cand = list(csv.DictReader((OUT / "candidates.csv").open()))
    tasks = []
    for f in ("apex", "apex_eod"):
        rows = sorted((r for r in cand if r["firm"] == f and r["apex_compliant"] == "1"), key=lambda r: -float(r["p5"]))
        seen = set()
        for r in rows:
            c = (r["fam"], r["tf"], r["sess"], r["key"].split("-")[0])
            if c in seen:
                continue
            seen.add(c)
            free = dict(free_p5=float(r["p5"]), free_micros=r["micros"], free_mae750=r["mae750_share"], free_net1=r["net_1nq"])
            tasks.append((f, r["fam"], int(r["tf"]), r["key"], r["sess"], r["params"], srcs[r["key"]], free))
            if len(seen) == a.top:
                break
    print(f"apexmae: {len(tasks)} configs", flush=True)
    res = A2.run_ckpt(task, tasks, lambda t: f"{t[0]}|{t[3]}|{t[4]}", a.workers, "apexmae", OUT / "a3p3_apexmae_part.jsonl")
    A1.write(OUT / "a3p3_apexmae.csv", res)
    for r in res:
        print(r.get("firm"), r.get("key"), r.get("sess"), "free P5", r.get("free_p5"), "-> compliant P5", r.get("intraday_p5_stable"), "m", r.get("micros_ok"), flush=True)


if __name__ == "__main__":
    main()
