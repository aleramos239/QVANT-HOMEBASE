#!/usr/bin/env python3
"""TESTER-MATCH GATE of port group 3 (families/port3.py: vwap_band, vwap_z, vwap_flip, pinbar, sweep_rev) -- ENGINE.md 8.

Every in-sample tester bundle of the five families in the old pilots is replayed on l2sim and compared trade for trade:
  NQ (R = prop-portfolio/2026-09-29)      the 20 screen runs (every family x tf 1 / 5 / 15 / 30, default inputs, sess all)
                                          + every cell of their 9 sizing heat-maps (the family-parameter axis x exits,
                                          ATR and fixed-point stops)
  ES (RE = prop-portfolio/2026-09-30-es)  the 20 ES screen runs + every cell of the 6 ES sizing heat-maps
  GC                                      no GC tester bundle exists (EDGE_VALIDATION.md "GC"): not matched, flagged.
Gate per bundle / cell: >= 99 % identical trades (date, side, entry time +- 1 s, entry price, exit price, exit reason),
net within 0.5 %, the same skipped days, no session dropped by a strategy error. Also: every REGISTERED family-parameter
variant must be one of the matched NQ heat-map cells' values.

Trade IDENTITY only. Bundle ids are read from R / RE jobs.jsonl by key, stages `screen` and `sizing` ONLY (never `holdout`,
`wf`, `calib`); a bundle whose range reaches 2025 is refused and every row outside 2021-09-22 .. 2024-12-31 is dropped
before anything reads it (edge_validate.load_run / sim_validate.load_bundle). No bundle P&L is printed or stored: only
counts and the sim-minus-tester net difference.

Usage: python port3_validate.py [--workers 2] [--roots NQ,ES]      -> PORT3_VALIDATION.md + out/port3_validation.json
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
import edge_validate as EV                      # noqa: E402
import families                                 # noqa: E402
import l2sim as S                               # noqa: E402
import sim_validate as V                        # noqa: E402

FAMS = ("vwap_band", "vwap_z", "vwap_flip", "pinbar", "sweep_rev")
TFS = ("1", "5", "15", "30")
PILOT = {"NQ": S.R, "ES": S.RE}
STAGES = {"run": "screen", "grid": "sizing"}       # the only stages this gate may read
ID_GATE, NET_GATE = EV.ID_GATE, EV.NET_GATE        # 0.99, 0.5 %
START, END = V.START, V.END
SHA_FILES = ("families/port3.py", "l2sim.py", "l2ref.py", "port3_validate.py")
KEEP = ("n_ref", "n_sim", "matched", "exact_all_fields", "match_rate", "exact_rate", "net_diff", "net_diff_pct")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def shas() -> dict:
    return {f: sha(HERE / f) for f in SHA_FILES}


def bundles(root: str) -> dict:
    """{"runs": [(key, family, tf, run id)], "grids": [(key, family, grid id)]} of the five families, from the pilot's
    jobs.jsonl (last `done` line per key), stages screen / sizing only."""
    jobs = {}
    for line in (PILOT[root] / "jobs.jsonl").read_text().splitlines():
        if line.strip():
            j = json.loads(line)
            if j.get("status") == "done":
                jobs[j["key"]] = j
    runs, grids = [], []
    for fam in FAMS:
        for tf in TFS:
            j = jobs.get(f"screen-{fam}-tf{tf}")
            if j is not None:
                assert j["stage"] == STAGES["run"] and j["kind"] == "run", j["key"]
                runs.append((j["key"], fam, tf, j["id"]))
        for key, j in sorted(jobs.items()):
            if j["kind"] == "grid" and j["stage"] == STAGES["grid"] and key.split("-")[1:2] == [fam]:
                grids.append((key, fam, j["id"]))
    return {"runs": runs, "grids": grids}


def _row(c: dict, extra: dict) -> dict:
    out = {k: c[k] for k in KEEP}
    out.update(extra)
    out["pass"] = bool(c["match_rate"] >= ID_GATE and c["net_diff_pct"] <= NET_GATE and extra.get("skipped_by_error", 0) == 0
                       and extra.get("skips_equal", True))
    return out


def runs_gate(root: str, runs: list, workers: int) -> list:
    """All screen runs of a root in ONE tape pass."""
    loaded = [EV.load_run(rid) for _, _, _, rid in runs]
    for (key, fam, tf, rid), (inputs, ref, cov, r) in zip(runs, loaded):
        assert r == root and inputs["tf"] == tf and inputs["sess"] == "all", (key, r, inputs)
    res = S.run_many([(families.REGISTRY[fam][0], ld[0]) for (_, fam, _, _), ld in zip(runs, loaded)], START, END, root=root,
                     workers=workers)
    out = []
    for (key, fam, tf, rid), (inputs, ref, cov, _), r in zip(runs, loaded, res):
        skips = [s["date"] for s in r["skipped"]] == [s["date"] for s in cov["skipped"] if START <= s["date"] <= END]
        out.append(_row(V.compare(r["trades"], ref), {"id": key, "root": root, "family": fam, "tf": tf, "src": rid,
                                                      "skips_equal": skips, "skipped_by_error": r["skipped_by_error"],
                                                      "both_sides_sessions": r["both_sides_sessions"], "elapsed_s": r["elapsed_s"]}))
    return out


def grid_gate(root: str, key: str, fam: str, gid: str, workers: int) -> dict:
    g = json.loads((V.GRIDS / gid / "grid.json").read_text())
    assert g["range"]["end"] < "2025-01-01" and not g["range"].get("holdout"), f"{gid}: the grid reaches the exam period"
    cells = [V.load_bundle(f"{gid}#{i}") for i in range(g["total"])]
    assert all(c[3] == {"qty": 1, "commission": 4.0, "slippage_ticks": 1.0} and c[4] == "tick-2" for c in cells), gid
    res = S.run_many([(families.REGISTRY[fam][0], c[0]) for c in cells], START, END, root=root, workers=workers)
    cmp_ = [V.compare(r["trades"], c[1]) for r, c in zip(res, cells)]
    axis = g["axes"][0]
    out = {"id": key, "root": root, "family": fam, "src": gid, "cells": g["total"], "tf": cells[0][0]["tf"],
           "stop_mode": cells[0][0]["stop_mode"], "axes": [{"key": a["key"], "values": a["values"]} for a in g["axes"]],
           "first_axis": {"key": axis["key"], "values": axis["values"]},
           "cells_identical": sum(1 for c in cmp_ if c["exact_all_fields"] == c["n_ref"] == c["n_sim"]),
           "n_ref": sum(c["n_ref"] for c in cmp_), "n_sim": sum(c["n_sim"] for c in cmp_),
           "matched": sum(c["matched"] for c in cmp_), "exact_all_fields": sum(c["exact_all_fields"] for c in cmp_),
           "min_match_rate": min(c["match_rate"] for c in cmp_), "max_net_diff_pct": max(c["net_diff_pct"] for c in cmp_),
           "max_abs_net_diff": max(abs(c["net_diff"]) for c in cmp_), "skipped_by_error": sum(r["skipped_by_error"] for r in res),
           "elapsed_s": res[0]["elapsed_s"]}
    out["pass"] = bool(out["min_match_rate"] >= ID_GATE and out["max_net_diff_pct"] <= NET_GATE and out["skipped_by_error"] == 0)
    return out


def variants_covered(grids: list) -> dict:
    """Every registered family-parameter variant must be a first-axis value of a MATCHED NQ heat-map of its family."""
    out = {}
    for fam in FAMS:
        reg = families.library(fam)["variants"]
        seen = {}
        for g in grids:
            if g["family"] == fam and g["pass"] and g["first_axis"]["key"] not in ("stop_val", "tgt_r"):
                seen.setdefault(g["first_axis"]["key"], set()).update(g["first_axis"]["values"])
        miss = [v for v in reg if not all(k in seen and val in seen[k] for k, val in v.items())]
        out[fam] = {"variants": reg, "matched_axis": {k: sorted(v, key=str) for k, v in seen.items()}, "missing": miss,
                    "pass": not miss}
    return out


def render(out: dict) -> str:
    L = ["# PORT3_VALIDATION — families/port3.py (vwap_band, vwap_z, vwap_flip, pinbar, sweep_rev) vs the Homebase Strategy Tester", "",
         f"Generated {out['when']} by `port3_validate.py` (sha256/16: " + ", ".join(f"{k} {v}" for k, v in out["sha"].items()) + ").",
         "Raw: `out/port3_validation.json`. In-sample bundles of the old pilots only (2021-09-22 → 2024-12-31; stages `screen` and "
         "`sizing`), trade IDENTITY only; nothing dated ≥ 2025-01-01 and no `holdout` bundle was read; no bundle P&L is shown.", "",
         f"## Verdict: {'ALL GATES PASS' if out['pass'] else 'A GATE FAILED'}",
         f"Gate per bundle / cell: ≥ {ID_GATE * 100:.0f} % identical trades (date, side, entry time ± 1 s, entry price, exit price, exit "
         f"reason), net within {NET_GATE} %, the same skipped days, no session dropped by an error.", ""]
    for root in ("NQ", "ES"):
        g = out["roots"].get(root)
        if g is None:
            continue
        L += [f"## {root} — screen runs (default inputs, sess all): {'PASS' if all(x['pass'] for x in g['runs']) else 'FAIL'}",
              "| bundle | tester trades | sim trades | all-20-fields identical | match rate | net diff $ | skipped days equal | pass |",
              "|---|---|---|---|---|---|---|---|"]
        for x in g["runs"]:
            L.append(f"| {x['id']} | {x['n_ref']} | {x['n_sim']} | {x['exact_all_fields']} | {x['match_rate'] * 100:.2f}% | "
                     f"{x['net_diff']:+.2f} | {x['skips_equal']} | {x['pass']} |")
        L += ["", f"## {root} — every cell of the sizing heat-maps: {'PASS' if all(x['pass'] for x in g['grids']) else 'FAIL'}",
              "| heat-map | tf | axes | cells | cells 100% identical | tester trades | sim trades | all-fields identical | worst cell match | "
              "max abs net diff $ | pass |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for x in g["grids"]:
            axes = " × ".join(f"{a['key']} {a['values']}" for a in x["axes"]) + (" (pts stops)" if x["stop_mode"] == "pts" else "")
            L.append(f"| {x['id']} | {x['tf']} | {axes} | {x['cells']} | {x['cells_identical']} | {x['n_ref']} | {x['n_sim']} | "
                     f"{x['exact_all_fields']} | {x['min_match_rate'] * 100:.2f}% | {x['max_abs_net_diff']:.2f} | {x['pass']} |")
        L.append("")
    if "variants" in out:
        L += ["## Registered family-parameter variants are tester-matched (NQ heat-maps)",
              "| family | registered variants | matched first-axis values | missing | pass |", "|---|---|---|---|---|"]
        for fam, v in out["variants"].items():
            L.append(f"| {fam} | {v['variants']} | {v['matched_axis']} | {v['missing'] or '—'} | {v['pass']} |")
        L.append("")
    L += ["## Not covered by a tester bundle (flag)",
          "* **GC**: no GC tester run exists (EDGE_VALIDATION.md \"GC\"); the five families run on GC with the same code, validated by "
          "construction only.",
          "* **`pre` / `eve` sessions, `stop_mode=\"pct\"`**: the tester cannot run them; their proof is internal "
          "(`tests/test_port3.py`: session windows, no look-ahead, worker parity; `tests/test_edge_template.py`).",
          "* `vwap_flip` `anchor=\"rth\"` and `f_trend` / `f_vwap` / `trail_atr` were never run in the tester for these families and are "
          "not menu variants.", "",
          "## Reproduce", '`"~/ONYX TRADING/.venv/bin/python" port3_validate.py --workers 2` in `engine/` (re-run after ANY change to '
          "`families/port3.py`, `l2sim.py` or `l2ref.py`; `tests/test_port3.py` fails when `families/port3.py` no longer has the sha above).", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="port3_validate.py")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--roots", default="NQ,ES")
    a = ap.parse_args(argv)
    assert not families.ERRORS, families.ERRORS
    out = {"when": dt.datetime.now(S.ET).strftime("%Y-%m-%d %H:%M ET"), "sha": shas(), "range": [START, END], "roots": {}}
    for root in [r for r in a.roots.split(",") if r]:
        b = bundles(root)
        S.wait_compute_window()
        runs = runs_gate(root, b["runs"], a.workers)
        print(root, "runs", sum(x["pass"] for x in runs), "/", len(runs), "pass", flush=True)
        grids = []
        for key, fam, gid in b["grids"]:
            S.wait_compute_window()
            grids.append(grid_gate(root, key, fam, gid, a.workers))
            print(root, key, "PASS" if grids[-1]["pass"] else "FAIL", f"{grids[-1]['cells_identical']}/{grids[-1]['cells']} cells identical",
                  flush=True)
        out["roots"][root] = {"runs": runs, "grids": grids, "pass": all(x["pass"] for x in runs + grids)}
    if "NQ" in out["roots"]:
        out["variants"] = variants_covered(out["roots"]["NQ"]["grids"])
    out["sha_end"] = shas()                          # a file edited while the gate ran makes the report stale
    out["pass"] = bool(all(g["pass"] for g in out["roots"].values()) and all(v["pass"] for v in out.get("variants", {}).values())
                       and out["sha_end"] == out["sha"])
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out" / "port3_validation.json").write_text(json.dumps(out, indent=1, default=str))
    (HERE / "PORT3_VALIDATION.md").write_text(render(out))
    print("ALL GATES PASS" if out["pass"] else "A GATE FAILED")
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
