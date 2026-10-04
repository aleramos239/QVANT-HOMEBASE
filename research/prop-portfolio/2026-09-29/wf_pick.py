#!/usr/bin/python3
"""Choose the 15 tester walk-forward candidates of a pilot from out/candidates.csv (a3p3_merge.py) and write the hb.py job file.
Run: PYTHONPATH=~/ramos-quant-homebase PP_PILOT=es /usr/bin/python3 wf_pick.py [--n 15] [--pos 5] [--top 12] [--write wf_es.jsonl]

Selection (as the NQ walk-forwards were chosen: top configs by primary P5 and by P1/P3 across firms, distinct family/tf/session, positive-expectancy
bias for the funded use):
  1. per firm: the top --top distinct (family, tf, session, mode) configs by primary-model P5, by speed P1 (P3 for Lucid Flex, whose P1 is structurally 0);
     Apex firms (UNCONFIRMED) only Apex-compliant rows (no OCO/both-side family, target tgt_r >= 0.2);
  2. score = sum over firm lists of (top - rank); the best n - pos by score take the first slots (distinct family/tf/session; the fast-pass (fp) and
     ATR variants of one family/tf/session may both appear, as NQ's tod_drift-tf5-mid and -mid-fp did, at most 3 fp variants);
  3. the last --pos slots go to the best POSITIVE-EXPECTANCY configs (net > 0 at 1 contract before rules, ranked by their best primary P5 across firms)
     not already chosen: the funded account needs a real edge, not only payoff shape.
Walk-forward spec: tester walk-forward (param pick on 1 month by t_stat, test 3 months, stitched OOS at 1 contract), same axes as NQ; fast-pass variants
use the pilot's points grid (ES stop pts {3,6,10,15} x tgt_r {.25,.4,.6,1}; NQ {10,20,30,45})."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E  # noqa: E402

OUT = E.D / "out"
FIRMS5 = ("lucid", "lucidpro", "lucidpro_nodll", "apex", "apex_eod")
UNCONF = {"apex", "apex_eod"}
STOPX = [1.0, 2.0, 3.0]
TGTX = [0.5, 1.0, 2.0, 3.0]
FAM_AXES = {
    "orb": ("or_min", ["5", "15", "30"]), "tema_slope": ("n", [10, 20, 40]), "vwap_band": ("band", [1.5, 2.0, 2.5, 3.0]),
    "donchian": ("n", [10, 20, 40]), "first_bar_mom": ("k", [1.0, 1.5, 2.0]), "rsi2": ("th", [5.0, 10.0, 15.0]),
    "straddle": ("off_atr", [0.25, 0.5, 1.0]), "squeeze": ("sq_type", ["bbkc", "nr7", "inside"]), "vwap_flip": ("hold", [1, 2, 3]),
    "vwap_z": ("zth", [1.5, 2.0, 2.5, 3.0]), "ema_pullback": ("max_tr", [1, 3]),
}
FP_STOP = {"nq": [10.0, 20.0, 30.0, 45.0], "es": [3.0, 6.0, 10.0, 15.0]}
FP_TGT = [0.25, 0.4, 0.6, 1.0]


def fl(x, d=float("nan")):
    try:
        return float(x) if x not in ("", None) else d
    except ValueError:
        return d


def mode_of(r):
    return "fp" if r["key"].startswith("fp-") else "atr"


def cid(r):
    return (r["fam"], int(r["tf"]), r["sess"], mode_of(r))


def spec(c):
    fam, tf, sess, mode = c
    key = f"wf-{fam}-tf{tf}-{sess}" + ("-fp" if mode == "fp" else "")
    inputs = {"tf": str(tf), "sess": sess}
    if mode == "fp":
        inputs["stop_mode"] = "pts"
        if fam == "tod_drift":
            inputs["exit_bars"] = 0
        axes = [{"key": "stop_val", "values": FP_STOP[E.PL.NAME if E.PL.NAME in FP_STOP else "nq"]}, {"key": "tgt_r", "values": FP_TGT}]
    elif fam == "tod_drift":
        axes = [{"key": "off_min", "values": [0, 15, 30, 60]}, {"key": "exit_bars", "values": [6, 12, 24]}, {"key": "dir", "values": ["long", "short"]}]
    elif fam in FAM_AXES:
        axes = [{"key": FAM_AXES[fam][0], "values": FAM_AXES[fam][1]}, {"key": "stop_val", "values": STOPX}, {"key": "tgt_r", "values": TGTX}]
    else:
        axes = [{"key": "stop_val", "values": STOPX}, {"key": "tgt_r", "values": TGTX}]
    n = 1
    for a in axes:
        n *= len(a["values"])
    job = {"kind": "walkforward", "stage": "wf", "range": {"preset": "2021-2024"}, "costs": {"qty": 1}, "prop_rules": "lucid-flex-50k@2026-09-27",
           "ratio": 3, "metric": "t_stat", "min_trades": 5, "key": key, "strategy": f"{E.DRAFT_PREFIX}{fam}", "inputs": inputs, "axes": axes, "max_cells": n}
    if E.PL.NAME != "nq":
        job["pilot"] = E.PL.NAME
    return job


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=15)
    ap.add_argument("--pos", type=int, default=5)
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--max-fp", type=int, default=3)
    ap.add_argument("--max-fam-tf", type=int, default=2)
    ap.add_argument("--max-fam", type=int, default=3)
    ap.add_argument("--write", default="")
    a = ap.parse_args(argv)
    cand = list(csv.DictReader((OUT / "candidates.csv").open()))
    score, why = defaultdict(float), defaultdict(list)
    best_p5 = {}
    for f in FIRMS5:
        rows = [r for r in cand if r["firm"] == f and (f not in UNCONF or r.get("apex_compliant") == "1")]
        speed = "sp3_p3" if f == "lucid" else "sp1_p1"
        for lab, col in (("P5", "p5"), (speed[4:6].upper() if f != "lucid" else "P3", speed)):
            seen, k = set(), 0
            for r in sorted(rows, key=lambda r: -fl(r.get(col), -1)):
                c = cid(r)
                if c in seen or fl(r.get(col), -1) < 0:
                    continue
                seen.add(c)
                score[c] += a.top - k
                why[c].append(f"{f}:{lab}#{k + 1}")
                k += 1
                if k == a.top:
                    break
    posyrs = {}
    for r in cand:                              # best primary P5 across firms (for the positive-expectancy ranking)
        if fl(r["net_1nq"], 0) > 0 and fl(r["exp_at_micros"], 0) > 0:
            c = cid(r)
            if fl(r["p5"], -1) > best_p5.get(c, -1):
                best_p5[c], posyrs[c] = fl(r["p5"], -1), int(fl(r.get("pos_years"), 0))
    first, fam_tf_sess, nfp, fam_n, fam_tf_n = [], set(), 0, defaultdict(int), defaultdict(int)
    for c, sc in sorted(score.items(), key=lambda kv: (-kv[1], kv[0])):
        if len(first) >= a.n - a.pos:
            break
        if c in first:
            continue
        if c[3] == "fp" and nfp >= a.max_fp:
            continue
        # one config per (family, tf, session) unless the other is the fp variant (NQ precedent)
        if (c[0], c[1], c[2], "x") in fam_tf_sess and c[3] != "fp":
            continue
        if fam_tf_n[(c[0], c[1])] >= a.max_fam_tf or fam_n[c[0]] >= a.max_fam:     # breadth: <= 2 sessions per family x tf, <= 3 configs per family
            continue
        fam_tf_n[(c[0], c[1])] += 1
        fam_n[c[0]] += 1
        first.append(c)
        fam_tf_sess.add((c[0], c[1], c[2], "x") if c[3] != "fp" else (c[0], c[1], c[2], "fp"))
        nfp += c[3] == "fp"
    pos = []
    for c, v in sorted(best_p5.items(), key=lambda kv: (-min(posyrs[kv[0]], 3), -kv[1], kv[0])):      # >= 3 positive years first, then P5
        if len(pos) >= a.pos:
            break
        if c in first or any(c[:3] == x[:3] and c[3] == x[3] for x in first):
            continue
        if c[3] == "fp":
            continue
        pos.append(c)
    chosen = first + pos
    jobs = [spec(c) for c in chosen]
    for c, j in zip(chosen, jobs):
        tag = "POS-EXP" if c in pos else "RANK"
        print(f"{j['key']:42s} {tag:8s} score {score.get(c, 0):5.0f} bestP5(net>0) {best_p5.get(c, float('nan')):.3f} posyrs {posyrs.get(c, -1)} {','.join(why.get(c, [])[:6])}")
    if a.write:
        Path(a.write).write_text("\n".join(json.dumps(j) for j in jobs) + "\n")
        print(f"wrote {len(jobs)} jobs -> {a.write}")
    return chosen


if __name__ == "__main__":
    main()
