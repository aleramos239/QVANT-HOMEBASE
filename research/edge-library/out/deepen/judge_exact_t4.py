"""STAGE 2a, T4 sides that passed (a)-(e) on the stored-trade split: the EXACT judgement on the long-only / short-only re-run
(the family's own `dir` input; runs_deepen/<unit>-<sess>-build-dir<side>). BUILD only.
(c) = the on-disk random-entry pool restricted to the same side (as the stored split); (e) = 4,000 day- and session-matched draws
from a pool of 30 random-entry seeds run with the SAME `dir` and the central variant's exit (the two on-disk seeds alone hold
about 2 same-side trades per day and session: their draws barely differ, so 'beats 99.4 %' would mean nothing).
  python out/deepen/judge_exact_t4.py            -> out/deepen/exact_t4.json (+ jobs_t4_pool.json for sides passing (a)-(d))"""
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
SIDES = [("rsi2-NQ-tf30|eve|", "long"), ("squeeze-NQ-tf30|pm|", "long")]
POOL_SEEDS = list(range(101, 131))


def main():
    us = {r["uid"]: r for r in J.units()}
    out, jobs = {}, []
    for uid, side in SIDES:
        r = us[uid]
        key, sess, root, tf, fam = r["key"], r["sess"], r["root"], str(r["tf"]), r["family"]
        ub, ux = J.load(key), LB.load_unit(f"{key}-{sess}-build-dir{side}", RD)
        assert ux["meta"]["period"] == "build" and ux["meta"]["extra"]["dir"] == side
        base = {t["id"]: t for t in LB.plateau_units(ub, sess)[r.get("label") or ""]}
        tab = [t for t in LB.session_table(ux, sess) if t["id"] in base]
        for t in tab:
            t["dead"] = base[t["id"]]["dead"]
        assert all(int(v) == (1 if side == "long" else -1) for v in np.unique(ux["side"]))
        pl = LB.plateau(tab)
        cm = pl["member"]
        x = LB.unit_cell(ux, cm)
        x = J.masked(x, x["sess"] == LB.SESS_CODE[sess])
        st = LB.stats(x["net"])
        bar = J.BARS[f"c1-{root}"]["bar"]
        pu = J.load(f"c1-{root}-tf{tf}")
        parts = [LB.unit_cell(pu, f"s{sd}_{J.exit_id(cm)}") for sd in (1, 2)]
        pool = {k: np.concatenate([p[k] for p in parts]) for k in ("date", "sess", "net", "side")}
        pm = L.side_mask(side, root, pool["date"], pool["side"])
        c1 = LB.c1_draws(x, {k: v[pm] for k, v in pool.items()}, K=200, seed=LB.default_seed(f"{uid}|{side}|exact", "build"))
        # how far the stored split was from the exact run (same cell)
        xb = LB.unit_cell(ub, cm)
        mb = (xb["sess"] == LB.SESS_CODE[sess]) & L.side_mask(side, root, xb["date"], xb["side"])
        row = {"uid": uid, "side": side, "cells": pl["cells"], "share_pos": pl["share_pos"], "median_net": pl["median_net"],
               "verdicts": pl["verdicts"], "central": cm, "trades": st["trades"], "net": st["net"], "t": st["t"], "bar": bar,
               "ctrl_lift": c1["lift"], "ctrl_p_beat": c1["p_beat"], "ctrl_short": c1["short"], "ctrl_fallback": c1["fallback_share"],
               "a": st["trades"] >= LB.MIN_TRADES, "b": bool(pl["pass"]), "c": bool(c1["lift"] > 0 and c1["short"] == 0),
               "d": bool((st["t"] or 0.0) >= bar),
               "stored_split_same_cell": {"trades": int(mb.sum()), "net": round(float(xb["net"][mb].sum()), 2)},
               "plateau": pl, "years": J.yearly(x, root, LB.calendar("build", root))}
        pk = f"c1-{root}-tf{tf}-{sess}-build-dir{side}-pool{J.exit_id(cm)}"
        if (RD / pk / "run.json").exists():
            up = LB.load_unit(pk, RD)
            pp = {k: up[k] for k in ("date", "sess", "net")}
            keep = pp["sess"] == LB.SESS_CODE[sess]
            e = J.c1_fast(x, {k: v[keep] for k, v in pp.items()}, J.DRAWS, LB.default_seed(f"{uid}|{side}|exact", "build-e"))
            row.update(e_p=e["p_beat"], e_lift=e["lift"], e_mean=e["mean"], e_short=e["short"], e_fallback=e["fallback_share"],
                       e_pool_trades=int(keep.sum()), e=bool(e["p_beat"] >= J.ALPHA and e["short"] == 0))
            row["pass"] = bool(row["a"] and row["b"] and row["c"] and row["d"] and row["e"])
        elif row["a"] and row["b"] and row["c"] and row["d"]:
            jobs.append({"c1": True, "root": root, "tf": tf, "sess": sess, "period": "build", "extra": {"dir": side},
                         "seeds": POOL_SEEDS, "exits": [J.exit_id(cm)], "tag": f"pool{J.exit_id(cm)}",
                         "why": f"30-seed same-side random-entry pool for test (e) of {uid} {side}"})
        else:
            row["e"], row["pass"] = None, False
        out[f"{uid}{side}"] = row
        print(uid, side, "cells", pl["cells"], "share>0", pl["share_pos"], "median", pl["median_net"], "central", cm, "trades", st["trades"],
              "net", st["net"], "t", None if st["t"] is None else round(st["t"], 3), "bar", round(bar, 3), "lift", c1["lift"],
              "p_beat", c1["p_beat"], "| stored split same cell:", row["stored_split_same_cell"],
              "| a b c d e:", row["a"], row["b"], row["c"], row["d"], row.get("e"), "e_p", row.get("e_p"), "PASS" if row.get("pass") else "")
    (HERE / "exact_t4.json").write_text(json.dumps(out, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    (HERE / "jobs_t4_pool.json").write_text(json.dumps(jobs, indent=1))
    print("pool jobs", len(jobs))


if __name__ == "__main__":
    main()
