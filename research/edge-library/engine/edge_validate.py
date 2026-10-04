#!/usr/bin/env python3
"""EDGE VALIDATION GATES of the edge-library engine (run after every engine change; writes EDGE_VALIDATION.md +
out/edge_validation.json). Trade IDENTITY only: bundles of the old pilots' in-sample window (2021-09-22 .. 2024-12-31) are
replayed and compared trade for trade; no result is judged, nothing dated >= 2025-01-01 is read.

  NQ      the L2 pilot's SIM VALIDATION GATE again (sim_validate: 7 approved picks + every cell of the 3 source heat-maps):
          must stay 100 % with every new option off.
  ES      ES-pilot (RE) tester bundles: 3 screen runs (straddle tf30, orb tf5, donchian tf15) + every cell of 4 sizing
          heat-maps. Gate: each >= 99 % identical trades and net within 0.5 %.
  RANDOM  the C1 control port (l2ref.Random) against R / RE control bundles: 1 NQ run, 1 NQ heat-map (fixed-point stops
          10 / 20 / 30 / 45), 1 ES run. Gate as ES.
  CLOCK   the new clock path: l2ref.StraddleT fired at 03:00 / 09:30 / 13:30 (flat 08:25 / 11:00 / 15:58, no early cancel)
          against the existing l2ref.Straddle (london / nyam / pm), 4 exit cells each, NQ and ES: identical trade lists.

Usage: python edge_validate.py [--workers 4] [--skip nq,es,random,clock]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import l2ref                                    # noqa: E402
import l2sim as S                               # noqa: E402
import sim_validate as V                        # noqa: E402

RUNS = S.REPO / "homebase" / ".state" / "tester" / "runs"
START, END = V.START, V.END
ES_RUNS = [("es-screen-straddle-tf30", "straddle", "20260930-172655-draft_pp_es_straddle-3074"),
           ("es-screen-orb-tf5", "orb", "20260930-172525-draft_pp_es_orb-fe82"),
           ("es-screen-donchian-tf15", "donchian", "20260930-172817-draft_pp_es_donchian-a235")]
ES_GRIDS = [("es-fp-straddle-tf30", "straddle", "20260930-222614-draft_pp_es_straddle-63a3"),
            ("es-fp-orb-tf5", "orb", "20260930-222431-draft_pp_es_orb-4755"),
            ("es-hm-donchian-tf15", "donchian", "20260930-193841-draft_pp_es_donchian-c0eb"),
            ("es-hm-straddle-tf15", "straddle", "20260930-203531-draft_pp_es_straddle-e3cd")]
RANDOM_RUNS = [("nq-ctrl-random-tf5-s1", "NQ", "20260929-220631-draft_pp_random-bb39"),
               ("es-ctrl-random-tf15-s1", "ES", "20260930-180647-draft_pp_es_random-ae33")]
RANDOM_GRIDS = [("nq-fpctrl-random-tf30-s21", "NQ", "20260930-113916-draft_pp_random-b6f5")]
CLOCK = [("03:00", "08:25", "london"), ("09:30", "11:00", "nyam"), ("13:30", "15:58", "pm")]
CLOCK_EXITS = [{"stop_mode": "atr", "stop_val": 1.5, "tgt_r": 2.0}, {"stop_mode": "atr", "stop_val": 3.0, "tgt_r": 0.0},
               {"stop_mode": "pts", "stop_val": 20.0, "tgt_r": 1.0}, {"stop_mode": "pct", "stop_val": 0.10, "tgt_r": 3.0}]
FAMS = dict(l2ref.FAMILIES, random=l2ref.Random)
ID_GATE, NET_GATE = 0.99, 0.5


def load_run(rid: str):
    """(inputs, in-sample trades, coverage, root) of a tester RUN bundle; its range is checked BEFORE the trades are read."""
    d = RUNS / rid
    run = json.loads((d / "run.json").read_text())
    assert run["range"]["end"] < "2025-01-01" and not run["range"].get("holdout"), f"{rid}: the bundle reaches the exam period"
    assert (run["qty"], run["commission"], run["slippage_ticks"], run["engine"]) == (1, 4.0, 1.0, "tick-2"), rid
    trades = [t for t in json.loads((d / "trades.json").read_text()) if START <= t["date"] <= END]
    return run["inputs"], trades, run["coverage"], run["strategy"]["root"]


def _row(name, c, extra=None) -> dict:
    out = {"id": name, **{k: c[k] for k in ("n_ref", "n_sim", "matched", "exact_all_fields", "match_rate", "exact_rate", "net_diff",
                                             "net_diff_pct")}}
    out["pass"] = bool(c["match_rate"] >= ID_GATE and c["net_diff_pct"] <= NET_GATE)
    out.update(extra or {})
    return out


def one_run(name, fam, rid, workers) -> dict:
    inputs, ref, cov, root = load_run(rid)
    res = S.run(FAMS[fam], inputs, START, END, root=root, workers=workers)
    out = _row(name, V.compare(res["trades"], ref), {"root": root, "family": fam, "src": rid, "elapsed_s": res["elapsed_s"],
                                                     "skipped_by_error": res["skipped_by_error"]})
    out["skips_equal"] = [s["date"] for s in res["skipped"]] == [s["date"] for s in cov["skipped"] if START <= s["date"] <= END]
    out["pass"] = bool(out["pass"] and out["skips_equal"] and res["skipped_by_error"] == 0)
    return out


def one_grid(name, fam, gid, root, workers) -> dict:
    n = json.loads((V.GRIDS / gid / "grid.json").read_text())["total"]
    cells = [V.load_bundle(f"{gid}#{i}") for i in range(n)]
    res = S.run_many([(FAMS[fam], c[0]) for c in cells], START, END, root=root, workers=workers)
    cmp_ = [V.compare(r["trades"], c[1]) for r, c in zip(res, cells)]
    return {"id": name, "root": root, "family": fam, "src": gid, "cells": n, "elapsed_s": res[0]["elapsed_s"],
            "cells_identical": sum(1 for c in cmp_ if c["exact_all_fields"] == c["n_ref"] == c["n_sim"]),
            "n_ref": sum(c["n_ref"] for c in cmp_), "n_sim": sum(c["n_sim"] for c in cmp_),
            "exact_all_fields": sum(c["exact_all_fields"] for c in cmp_), "min_match_rate": min(c["match_rate"] for c in cmp_),
            "max_net_diff_pct": max(c["net_diff_pct"] for c in cmp_), "max_abs_net_diff": max(abs(c["net_diff"]) for c in cmp_),
            "skipped_by_error": sum(r["skipped_by_error"] for r in res),
            "pass": bool(min(c["match_rate"] for c in cmp_) >= ID_GATE and max(c["net_diff_pct"] for c in cmp_) <= NET_GATE
                         and not any(r["skipped_by_error"] for r in res))}


def nq_gate(workers) -> dict:
    picks = [V.one(*cfg, workers=workers) for cfg in V.GATE + V.EXTRA]
    for o in picks:
        for k in ("all", "pick"):
            o[k].pop("unmatched_ref", None), o[k].pop("unmatched_sim", None)
    grids = V.grid_sweep(workers)
    ok = (all(o["all"]["exact_rate"] == 1.0 and o["pick"]["exact_rate"] == 1.0 and o["all"]["net_diff"] == 0.0 and o["gate_pass"]
              for o in picks) and all(g["cells_identical"] == g["cells"] and g["max_abs_net_diff"] == 0.0 for g in grids))
    return {"picks": picks, "grids": grids, "pass": bool(ok)}


def es_gate(workers) -> dict:
    runs = [one_run(n, f, r, workers) for n, f, r in ES_RUNS]
    grids = [one_grid(n, f, g, "ES", workers) for n, f, g in ES_GRIDS]
    return {"runs": runs, "grids": grids, "pass": all(x["pass"] for x in runs + grids)}


def random_gate(workers) -> dict:
    runs = [one_run(n, "random", r, workers) for n, _, r in RANDOM_RUNS]
    grids = [one_grid(n, "random", g, root, workers) for n, root, g in RANDOM_GRIDS]
    return {"runs": runs, "grids": grids, "pass": all(x["pass"] for x in runs + grids)}


def clock_gate(workers) -> dict:
    rows = []
    for root in ("NQ", "ES"):
        specs, tags = [], []
        for at, flat, sess in CLOCK:
            for x in CLOCK_EXITS:
                x = dict(x) if root == "NQ" or x["stop_mode"] != "pts" else {**x, "stop_val": 5.0}
                specs.append((l2ref.Straddle, {"tf": "30", "sess": sess, "off_atr": 0.5, **x}))
                specs.append((l2ref.StraddleT, {"at": at, "flat": flat, "cancel_min": 0, "off_mode": "atr", "off_val": 0.5, "max_tr": 3, **x}))
                tags.append((at, sess, S.cell_id(x)))
        res = S.run_many(specs, START, END, root=root, workers=workers)
        for k, (at, sess, cid) in enumerate(tags):
            a, b = res[2 * k], res[2 * k + 1]
            rows.append({"root": root, "at": at, "sess": sess, "exit": cid, "trades_straddle": len(a["trades"]),
                         "trades_clock": len(b["trades"]), "identical": a["trades"] == b["trades"],
                         "skips_equal": a["skipped"] == b["skipped"], "errors": a["skipped_by_error"] + b["skipped_by_error"]})
    return {"rows": rows, "pass": all(r["identical"] and r["skips_equal"] and r["errors"] == 0 and r["trades_clock"] > 400 for r in rows)}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def render(out: dict) -> str:
    L = [f"# EDGE_VALIDATION — the edge-library engine vs the Homebase Strategy Tester", "",
         f"Generated {out['when']} by `edge_validate.py` (code sha256/16: {out['sha']}). Raw: `out/edge_validation.json`.",
         "In-sample bundles of the old pilots only (2021-09-22 → 2024-12-31), trade IDENTITY only; nothing dated ≥ 2025-01-01 was read.", "",
         f"## Verdict: {'ALL GATES PASS' if out['pass'] else 'A GATE FAILED'}", ""]
    if "nq" in out:
        g = out["nq"]
        L += [f"## NQ — the SIM VALIDATION GATE again, every new option off: {'PASS (100 %)' if g['pass'] else 'FAIL'}",
              "| config | scope | tester trades | sim trades | all-20-fields identical | net diff $ |", "|---|---|---|---|---|---|"]
        for o in g["picks"]:
            for k in ("all", "pick"):
                c = o[k]
                L.append(f"| {o['id']} | {'all sessions' if k == 'all' else o['pick_session']} | {c['n_ref']} | {c['n_sim']} | "
                         f"{c['exact_rate'] * 100:.2f}% | {c['net_diff']:+.2f} |")
        L += ["", "| heat-map | cells | cells 100% identical | tester trades | sim trades | max abs net diff $ |", "|---|---|---|---|---|---|"]
        for x in g["grids"]:
            L.append(f"| {x['family']} {x['grid']} | {x['cells']} | {x['cells_identical']} | {x['trades_ref']} | {x['trades_sim']} | "
                     f"{x['max_abs_net_diff']:.2f} |")
        L.append("")
    for key, title in (("es", "ES — the ES pilot's tester bundles (tester tape cache, $50 / pt, tick 0.25, $4 RT, 1 tick slip)"),
                       ("random", "RANDOM — the C1 control port (l2ref.Random) vs the pilots' control bundles")):
        if key not in out:
            continue
        g = out[key]
        L += [f"## {title}: {'PASS' if g['pass'] else 'FAIL'}", f"Gate: ≥ {ID_GATE * 100:.0f} % identical trades and net within {NET_GATE} % per bundle / cell.",
              "| bundle | root | tester trades | sim trades | all-20-fields identical | match rate | net diff % | skipped days equal | pass |",
              "|---|---|---|---|---|---|---|---|---|"]
        for x in g["runs"]:
            L.append(f"| {x['id']} | {x['root']} | {x['n_ref']} | {x['n_sim']} | {x['exact_all_fields']} | {x['match_rate'] * 100:.2f}% | "
                     f"{x['net_diff_pct']:.3f} | {x['skips_equal']} | {x['pass']} |")
        L += ["", "| heat-map | root | cells | cells 100% identical | tester trades | sim trades | all-fields identical | worst cell match | "
              "max net diff % | pass |", "|---|---|---|---|---|---|---|---|---|---|"]
        for x in g["grids"]:
            L.append(f"| {x['id']} | {x['root']} | {x['cells']} | {x['cells_identical']} | {x['n_ref']} | {x['n_sim']} | "
                     f"{x['exact_all_fields']} | {x['min_match_rate'] * 100:.2f}% | {x['max_net_diff_pct']:.3f} | {x['pass']} |")
        L.append("")
    if "clock" in out:
        g = out["clock"]
        L += [f"## CLOCK — StraddleT (the Globex-clock path) vs the existing Straddle: {'PASS (identical)' if g['pass'] else 'FAIL'}",
              "| root | fire time | = session | exit cell | Straddle trades | StraddleT trades | identical lists | skipped days equal |",
              "|---|---|---|---|---|---|---|---|"]
        for r in g["rows"]:
            L.append(f"| {r['root']} | {r['at']} | {r['sess']} | {r['exit']} | {r['trades_straddle']} | {r['trades_clock']} | "
                     f"{r['identical']} | {r['skips_equal']} |")
        L.append("")
    L += ["## GC", "No GC run exists in `homebase/.state/tester` (runs / grids / walk-forwards hold NQ and ES only), so GC cannot be matched "
          "against the tester. It rests on: the tape (a session built with the tester's own `TapeStore` code is byte-identical to the "
          "tester's cached file), the same engine code that matches NQ and ES 100 %, tick / point arithmetic unit tests ($100 / pt, "
          "tick 0.10) and an independent replay (`research/nfp-2026-10-02/nfp_lib.py`, 5 BUILD NFP days: same entries, TP / SL exits to "
          "the cent except where nfp_lib's exact float comparison misses a print AT the stop by float noise). "
          "`tests/test_edge_roots.py`. **FLAG: GC is validated by construction, not by a tester bundle.**", "",
          "## Reproduce", '`"~/ONYX TRADING/.venv/bin/python" edge_validate.py --workers 4` and `-m pytest` in this directory.', ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="edge_validate.py")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--skip", default="")
    a = ap.parse_args(argv)
    skip = {x for x in a.skip.split(",") if x}
    out = {"when": dt.datetime.now(S.ET).strftime("%Y-%m-%d %H:%M ET"),
           "sha": ", ".join(f"{f} {sha(HERE / f)}" for f in ("l2sim.py", "l2ref.py", "edge_validate.py"))}
    for key, fn in (("nq", nq_gate), ("es", es_gate), ("random", random_gate), ("clock", clock_gate)):
        if key in skip:
            continue
        S.wait_compute_window()
        out[key] = fn(a.workers)
        print(key, "PASS" if out[key]["pass"] else "FAIL", flush=True)
    out["pass"] = all(out[k]["pass"] for k in ("nq", "es", "random", "clock") if k in out)
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out" / "edge_validation.json").write_text(json.dumps(out, indent=1, default=str))
    (HERE / "EDGE_VALIDATION.md").write_text(render(out))
    print("ALL GATES PASS" if out["pass"] else "A GATE FAILED")
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
