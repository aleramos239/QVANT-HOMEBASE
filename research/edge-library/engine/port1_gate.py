#!/usr/bin/env python3
"""TESTER-MATCH GATE of the port1 families (families/port1.py: orb, straddle, donchian, squeeze, ib, lon_break, gap).

Replays EVERY screen bundle of the seven families of the old NQ pilot (R/ledger.csv, stage `screen`: one tester run per
family x tf, tf 1 / 5 / 15 / 30, sess all, the draft's default inputs) on l2sim with the ported class, in ONE tape pass,
and compares trade for trade. Gate per bundle (ENGINE.md § 8): >= 99 % of the trades identical on (date, side, entry time
+-1 s, entry price, exit price, exit_reason), total net within 0.5 %, the same skipped days, no session dropped by a
strategy error.

TRADE IDENTITY ONLY. The bundles are the old pilot's in-sample runs (2021-09-22 .. 2024-12-31; a bundle whose range reaches
2025 is refused before its trades are read). No P&L level is printed or stored: only counts, the net DIFFERENCE in dollars
and whether it is inside the 0.5 % gate.

ES (part of the default run): the ES pilot (RE = prop-portfolio/2026-09-30-es) ran the same screen on ES (drafts
pp_es_<fam>, the same template): its 28 screen bundles of the seven families are replayed with root="ES" and the same gate.
GC has no tester bundle (ENGINE.md § 11).

VARIANTS (part of the default run): the screen bundles ran every family at its DEFAULT inputs only. The registered
family-parameter variants (EDGE_SPEC "PROPER RE-RUN" 4 = the first axis of the family's heat-map) are other code paths
(squeeze nr7 / inside, ib fade, gap go, ...), so every cell of the heat-maps those variants come from (R/tune1.jsonl /
tune2.jsonl, stage `sizing`) is replayed too, cell by cell, with the same gate.

Usage: python port1_gate.py [--workers 2] [--only orb,gap] [--no-grids | --no-screen | --no-es]
       -> PORT1_VALIDATION.md + out/port1_gate.json (written only by a full run: no --only, no --no-*)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import edge_validate as EV                      # noqa: E402
import l2sim as S                               # noqa: E402
import sim_validate as V                        # noqa: E402

START, END = V.START, V.END
ID_GATE, NET_GATE = 0.99, 0.5
# family -> {tf: tester run id}: R/ledger.csv, stage `screen`, key screen-<family>-tf<tf> (checked against the ledger at run time)
SCREEN = {
    "orb": {"1": "20260929-213851-draft_pp_orb-783d", "5": "20260929-213851-draft_pp_orb-80f8",
            "15": "20260929-213911-draft_pp_orb-c4b7", "30": "20260929-213952-draft_pp_orb-44e4"},
    "straddle": {"1": "20260929-214012-draft_pp_straddle-bcaf", "5": "20260929-214032-draft_pp_straddle-8463",
                 "15": "20260929-214053-draft_pp_straddle-f941", "30": "20260929-214113-draft_pp_straddle-5d7d"},
    "donchian": {"1": "20260929-214133-draft_pp_donchian-ef00", "5": "20260929-214153-draft_pp_donchian-05b6",
                 "15": "20260929-214214-draft_pp_donchian-6a13", "30": "20260929-214234-draft_pp_donchian-a623"},
    "squeeze": {"1": "20260929-214254-draft_pp_squeeze-91a6", "5": "20260929-214314-draft_pp_squeeze-ecb2",
                "15": "20260929-214335-draft_pp_squeeze-02b3", "30": "20260929-214355-draft_pp_squeeze-d7f2"},
    "ib": {"1": "20260929-215724-draft_pp_ib-e2cb", "5": "20260929-215745-draft_pp_ib-238a",
           "15": "20260929-215805-draft_pp_ib-fced", "30": "20260929-215825-draft_pp_ib-76ec"},
    "gap": {"1": "20260929-215845-draft_pp_gap-f593", "5": "20260929-215905-draft_pp_gap-8936",
            "15": "20260929-215926-draft_pp_gap-c8f8", "30": "20260929-215946-draft_pp_gap-3fe5"},
    "lon_break": {"1": "20260929-220127-draft_pp_lon_break-762e", "5": "20260929-220147-draft_pp_lon_break-8a1a",
                  "15": "20260929-220208-draft_pp_lon_break-f7e2", "30": "20260929-220208-draft_pp_lon_break-1df7"},
}


# the ES pilot's screen runs of the same seven families: RE/ledger.csv, stage `screen` (drafts pp_es_<fam>)
SCREEN_ES = {
    "orb": {"1": "20260930-172524-draft_pp_es_orb-f5f9", "5": "20260930-172525-draft_pp_es_orb-fe82",
            "15": "20260930-172526-draft_pp_es_orb-3514", "30": "20260930-172526-draft_pp_es_orb-7f1b"},
    "straddle": {"1": "20260930-172552-draft_pp_es_straddle-02bd", "5": "20260930-172613-draft_pp_es_straddle-61ee",
                 "15": "20260930-172634-draft_pp_es_straddle-bdb7", "30": "20260930-172655-draft_pp_es_straddle-3074"},
    "donchian": {"1": "20260930-172715-draft_pp_es_donchian-e092", "5": "20260930-172736-draft_pp_es_donchian-fb9b",
                 "15": "20260930-172817-draft_pp_es_donchian-a235", "30": "20260930-172838-draft_pp_es_donchian-8c78"},
    "squeeze": {"1": "20260930-172859-draft_pp_es_squeeze-2d71", "5": "20260930-172920-draft_pp_es_squeeze-fe8c",
                "15": "20260930-172941-draft_pp_es_squeeze-76e5", "30": "20260930-173001-draft_pp_es_squeeze-a102"},
    "ib": {"1": "20260930-175004-draft_pp_es_ib-e705", "5": "20260930-175026-draft_pp_es_ib-c190",
           "15": "20260930-175107-draft_pp_es_ib-1bd5", "30": "20260930-175129-draft_pp_es_ib-78f9"},
    "gap": {"1": "20260930-175210-draft_pp_es_gap-c61e", "5": "20260930-175232-draft_pp_es_gap-5c1d",
            "15": "20260930-175313-draft_pp_es_gap-23ea", "30": "20260930-175354-draft_pp_es_gap-902e"},
    "lon_break": {"1": "20260930-175600-draft_pp_es_lon_break-b0a9", "5": "20260930-175641-draft_pp_es_lon_break-6b7e",
                  "15": "20260930-175702-draft_pp_es_lon_break-9826", "30": "20260930-175743-draft_pp_es_lon_break-3fce"},
}
SCREENS = {"NQ": (SCREEN, "R"), "ES": (SCREEN_ES, "RE")}

# tune key -> (family, tester grid id): the heat-maps whose FIRST axis defines the registered variants (R/ledger.csv, stage
# `sizing`; checked against the ledger at run time). tune1.jsonl = hm-*, tune2.jsonl = hm2-*.
GRIDS = {
    "hm-orb-tf5": ("orb", "20260929-231930-draft_pp_orb-5276"),                      # or_min 5 / 15 / 30
    "hm2-straddle-tf30": ("straddle", "20260930-001526-draft_pp_straddle-67c2"),     # off_atr 0.25 / 0.5 / 1.0
    "hm-donchian-tf15": ("donchian", "20260929-221600-draft_pp_donchian-d8e4"),      # n 10 / 20 / 40 / 60
    "hm2-squeeze-tf1": ("squeeze", "20260930-001527-draft_pp_squeeze-efd0"),         # sq_type bbkc / nr7 / inside
    "hm2-squeeze-tf5": ("squeeze", "20260930-002323-draft_pp_squeeze-b809"),
    "hm-ib-tf30": ("ib", "20260929-224604-draft_pp_ib-cc23"),                        # mode break / fade
    "hm-ib-tf15": ("ib", "20260929-225005-draft_pp_ib-a70e"),
    "hm2-gap-tf15": ("gap", "20260930-094241-draft_pp_gap-8337"),                    # mode fill / go
    "hm2-lon_break-tf5": ("lon_break", "20260930-094842-draft_pp_lon_break-ee12"),   # min_rng_atr 0 / 1 / 2
}


def ledger_grids() -> dict:
    """{tune key: grid id} of R/ledger.csv stage `sizing` (identity columns only)."""
    out = {}
    with (S.R / "ledger.csv").open() as fh:
        for r in csv.DictReader(fh):
            if r["stage"] == "sizing" and r["kind"] == "grid":
                out[r["key"]] = r["grid_id"]
    return out


def grid_cells(key: str) -> list:
    """[(inputs, in-sample trades, coverage)] of every cell of one heat-map; range, costs and engine are checked first."""
    fam, gid = GRIDS[key]
    assert ledger_grids().get(key) == gid, f"{key}: R/ledger.csv says {ledger_grids().get(key)}, the gate {gid}"
    g = json.loads((V.GRIDS / gid / "grid.json").read_text())
    assert g["range"]["end"] < "2025-01-01" and not g["range"].get("holdout"), f"{key}: the grid reaches the exam period"
    cells = []
    for i in range(g["total"]):
        inputs, ref, cov, cost, engine = V.load_bundle(f"{gid}#{i}")
        assert (cost["qty"], cost["commission"], cost["slippage_ticks"], engine) == (1, 4.0, 1.0, "tick-2"), (key, i)
        cells.append((inputs, ref, cov))
    return cells


def grid_gate(key: str, workers: int = 2, days=None) -> dict:
    """One heat-map, every cell in ONE tape pass -> the verdict (counts, the largest net difference, the gate flags)."""
    fam, gid = GRIDS[key]
    cells = grid_cells(key)
    cls = classes()[fam]
    kw = {"days": days} if days is not None else {}
    res = S.run_many([(cls, c[0]) for c in cells], *(() if days is not None else (START, END)), root="NQ", workers=workers, **kw)
    keep = (lambda d: d in set(days)) if days is not None else (lambda d: START <= d <= END)
    rows = [row(fam, c[0]["tf"], f"{gid}#{i}", r, [t for t in c[1] if keep(t["date"])],
                {"skipped": [s for s in c[2]["skipped"] if keep(s["date"])]}) for i, (c, r) in enumerate(zip(cells, res))]
    first = json.loads((V.GRIDS / gid / "grid.json").read_text())["axes"][0]
    return {"key": key, "family": fam, "src": gid, "tf": cells[0][0]["tf"], "axis": first["key"], "values": first["values"],
            "cells": len(rows), "cells_identical": sum(1 for x in rows if x["exact_all_fields"] == x["n_ref"] == x["n_sim"]),
            "cells_pass": sum(1 for x in rows if x["pass"]), "n_ref": sum(x["n_ref"] for x in rows),
            "n_sim": sum(x["n_sim"] for x in rows), "exact_all_fields": sum(x["exact_all_fields"] for x in rows),
            "min_match_rate": min(x["match_rate"] for x in rows), "max_abs_net_diff": max(abs(x["net_diff"]) for x in rows),
            "empty_cells": sum(1 for x in rows if x["n_ref"] == 0), "skipped_by_error": sum(x["skipped_by_error"] for x in rows),
            "elapsed_s": res[0]["elapsed_s"], "pass": all(x["pass"] for x in rows)}


def ledger_ids(root: str = "NQ") -> dict:
    """{(family, tf): run id} of the pilot's ledger.csv (R for NQ, RE for ES), stage `screen` -- the identity columns only
    (no metric column is read)."""
    out = {}
    with ((S.R if root == "NQ" else S.RE) / "ledger.csv").open() as fh:
        for r in csv.DictReader(fh):
            if r["stage"] == "screen" and r["kind"] == "run" and r["key"].startswith("screen-"):
                fam, tf = r["key"][len("screen-"):].rsplit("-tf", 1)
                out[(fam, tf)] = r["run_id"]
    return out


def bundles(only=None, root: str = "NQ") -> list:
    """[(family, tf, run id, inputs, in-sample trades, coverage)] of every screen bundle of the gate, in SCREEN order."""
    led = ledger_ids(root)
    out = []
    for fam, by_tf in SCREENS[root][0].items():
        if only and fam not in only:
            continue
        for tf, rid in by_tf.items():
            assert led.get((fam, tf)) == rid, f"{root} screen-{fam}-tf{tf}: the ledger says {led.get((fam, tf))}, the gate {rid}"
            inputs, ref, cov, r = EV.load_run(rid)
            assert r == root and inputs["tf"] == tf and inputs["sess"] == "all", (rid, r, inputs)
            out.append((fam, tf, rid, inputs, ref, cov))
    return out


def classes() -> dict:
    import families
    assert not families.ERRORS, families.ERRORS
    return {fam: families.REGISTRY[fam][0] for fam in SCREEN}


def row(fam, tf, rid, res, ref, cov) -> dict:
    """One bundle's verdict. Identity counts, the net difference and the gate flags: no P&L level."""
    c = V.compare(res["trades"], ref)
    skips = [s["date"] for s in cov["skipped"] if START <= s["date"] <= END]
    out = {"family": fam, "tf": tf, "src": rid, "n_ref": c["n_ref"], "n_sim": c["n_sim"], "matched": c["matched"],
           "exact_all_fields": c["exact_all_fields"], "match_rate": c["match_rate"], "net_diff": c["net_diff"],
           "net_within_gate": bool(c["net_diff_pct"] <= NET_GATE), "skips_equal": [s["date"] for s in res["skipped"]] == skips,
           "skipped_by_error": res["skipped_by_error"], "sessions": res["sessions"], "used": res["used"],
           "both_sides_sessions": res["both_sides_sessions"]}
    out["pass"] = bool(c["match_rate"] >= ID_GATE and out["net_within_gate"] and out["skips_equal"] and res["skipped_by_error"] == 0)
    return out


def gate(workers: int = 2, only=None, start=START, end=END, days=None, root: str = "NQ") -> list:
    """Replay the screen bundles of one root (all of them in ONE tape pass) -> one verdict row per bundle. start / end /
    days narrow the replay AND the reference rows alike (the tests use 10 days)."""
    bs = bundles(only, root)
    cls = classes()
    kw = {"days": days} if days is not None else {}
    res = S.run_many([(cls[fam], inputs) for fam, _, _, inputs, _, _ in bs], *(() if days is not None else (start, end)),
                     root=root, workers=workers, **kw)
    keep = (lambda d: d in set(days)) if days is not None else (lambda d: start <= d <= end)
    rows = []
    for (fam, tf, rid, inputs, ref, cov), r in zip(bs, res):
        cov = {"skipped": [s for s in cov["skipped"] if keep(s["date"])]}
        rows.append(row(fam, tf, rid, r, [t for t in ref if keep(t["date"])], cov))
        rows[-1].update(elapsed_s=r["elapsed_s"], root=root)
    return rows


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def render(out: dict) -> str:
    L = ["# PORT1_VALIDATION — families/port1.py vs the Homebase Strategy Tester (the old NQ pilot's screen bundles)", "",
         f"Generated {out['when']} by `port1_gate.py` (code sha256/16: {out['sha']}). Raw: `out/port1_gate.json`.",
         "In-sample screen bundles of the old pilot (2021-09-22 → 2024-12-31), trade IDENTITY only: no P&L level is printed "
         "or stored (only the net difference); nothing dated ≥ 2025-01-01 was read.", "",
         f"## Verdict: {'ALL 7 FAMILIES PASS (NQ and ES)' if out['pass'] else 'A GATE FAILED'}", "",
         f"Gate per bundle: ≥ {ID_GATE * 100:.0f} % of the trades identical on (date, side, entry time ±1 s, entry price, exit "
         f"price, exit_reason), net within {NET_GATE} %, the same skipped days, no session dropped by a strategy error. "
         "'all-20-fields identical' also needs qty, order price, sl, tp, gross, commission, net, MAE / MFE, bars, seconds and "
         "both timestamps to be equal.", ""]
    for root, (_, pilot) in SCREENS.items():
        rows = [x for x in out["rows"] if x["root"] == root]
        if not rows:
            continue
        L += [f"## {root} — the screen bundles of {'the old NQ pilot (R)' if root == 'NQ' else 'the ES pilot (RE)'}: "
              f"{'PASS' if all(x['pass'] for x in rows) else 'FAIL'}", "",
              "| family | tf | tester run | tester trades | sim trades | matched | all-20-fields identical | match rate | net diff $ | "
              "net within 0.5 % | skipped days equal | error sessions | pass |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for x in rows:
            L.append(f"| {x['family']} | {x['tf']} | {x['src']} | {x['n_ref']} | {x['n_sim']} | {x['matched']} | {x['exact_all_fields']} | "
                     f"{x['match_rate'] * 100:.2f}% | {x['net_diff']:+.2f} | {x['net_within_gate']} | {x['skips_equal']} | "
                     f"{x['skipped_by_error']} | {x['pass']} |")
        L += ["", "| family | bundles | tester trades | sim trades | all-20-fields identical | pass |", "|---|---|---|---|---|---|"]
        for fam in SCREEN:
            xs = [x for x in rows if x["family"] == fam]
            if xs:
                L.append(f"| {fam} | {len(xs)} | {sum(x['n_ref'] for x in xs)} | {sum(x['n_sim'] for x in xs)} | "
                         f"{sum(x['exact_all_fields'] for x in xs)} | {all(x['pass'] for x in xs)} |")
        L += ["", f"Sessions per bundle: {rows[0]['sessions']} in the range, {rows[0]['used']} used. One tape pass, "
              f"{out['workers']} worker process(es), {rows[0]['elapsed_s']} s.", ""]
    L += [
          "## The registered variants (NQ) — every cell of the heat-maps they come from",
          "The screen bundles ran each family at its DEFAULT inputs (or_min 15, off_atr 0.5, n 20, sq_type bbkc, ib break, gap "
          "fill, min_rng_atr 0; ATR 1.5 stop, 2R). The registered family-parameter variants are the first axis of these "
          "heat-maps (R/tune1.jsonl = hm-*, R/tune2.jsonl = hm2-*); each cell = one variant x stop_val {1, 2, 3} ATR x tgt_r "
          "{0.5, 1, 2, 3}, replayed with the ported class and compared with the same gate.", "",
          "| heat-map | family | tf | first axis = the variants | cells | cells 100 % identical | cells pass | tester trades | sim trades | "
          "all-20-fields identical | worst cell match | max abs net diff $ | cells without a trade | pass |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for g in out["grids"]:
        L.append(f"| {g['key']} | {g['family']} | {g['tf']} | {g['axis']} {g['values']} | {g['cells']} | {g['cells_identical']} | "
                 f"{g['cells_pass']} | {g['n_ref']} | {g['n_sim']} | {g['exact_all_fields']} | {g['min_match_rate'] * 100:.2f}% | "
                 f"{g['max_abs_net_diff']:.2f} | {g['empty_cells']} | {g['pass']} |")
    L += ["", "## What the gate cannot cover",
          "* Sessions `pre` and `eve`, the `pct` stop and the menu's fixed-point stops on these seven families were never run "
          "in the tester (the fixed-point path itself is tester-matched for orb, straddle, donchian and the random control: "
          "EDGE_VALIDATION.md). GC runs the same class bodies and has no tester bundle: validated by construction only "
          "(ENGINE.md § 11). On ES the non-default variants of squeeze, ib, gap and lon_break have no tester heat-map.",
          "* The heat-maps cover each variant at ONE or TWO tfs (the tf of the old tuning run), the screen bundles every tf at "
          "the default variant: a (non-default variant, tf) pair outside these is the same code, not a separate tester run.", "",
          "## Reproduce", '`"~/ONYX TRADING/.venv/bin/python" port1_gate.py --workers 2`', ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="port1_gate.py")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--only", default="")
    ap.add_argument("--no-grids", action="store_true")
    ap.add_argument("--no-screen", action="store_true")
    ap.add_argument("--no-es", action="store_true")
    a = ap.parse_args(argv)
    only = {x for x in a.only.split(",") if x} or None
    rows = ([] if a.no_screen else gate(a.workers, only)) + ([] if a.no_es else gate(a.workers, only, root="ES"))
    for x in rows:
        print(f"{x['root']} {x['family']:10s} tf{x['tf']:3s} tester {x['n_ref']:6d} sim {x['n_sim']:6d} identical {x['exact_all_fields']:6d} "
              f"match {x['match_rate'] * 100:6.2f}% net diff {x['net_diff']:+.2f} skips_equal {x['skips_equal']} "
              f"errors {x['skipped_by_error']} {'PASS' if x['pass'] else 'FAIL'}", flush=True)
    grids = []
    for key, (fam, _) in GRIDS.items():
        if a.no_grids or (only and fam not in only):
            continue
        g = grid_gate(key, a.workers)
        grids.append(g)
        print(f"{key:18s} {g['axis']} {g['values']} cells {g['cells']} identical {g['cells_identical']} tester {g['n_ref']} sim "
              f"{g['n_sim']} all-fields {g['exact_all_fields']} worst match {g['min_match_rate'] * 100:.2f}% max |net diff| "
              f"{g['max_abs_net_diff']:.2f} errors {g['skipped_by_error']} {g['elapsed_s']} s {'PASS' if g['pass'] else 'FAIL'}", flush=True)
    full = only is None and not a.no_grids and not a.no_screen and not a.no_es
    out = {"when": dt.datetime.now(S.ET).strftime("%Y-%m-%d %H:%M ET"), "workers": a.workers,
           "sha": ", ".join(f"{p.name} {sha(p)}" for p in (HERE / "families" / "port1.py", HERE / "l2sim.py", HERE / "l2ref.py",
                                                            Path(__file__).resolve())),
           "rows": rows, "grids": grids, "elapsed_s": rows[0]["elapsed_s"] if rows else 0.0,
           "pass": bool(rows or grids) and all(x["pass"] for x in rows + grids)}
    if full:
        (HERE / "out").mkdir(exist_ok=True)
        (HERE / "out" / "port1_gate.json").write_text(json.dumps(out, indent=1))
        (HERE / "PORT1_VALIDATION.md").write_text(render(out))
    print("PORT1 GATE", "PASS" if out["pass"] else "FAIL", f"({len(rows)} screen bundles, {len(grids)} heat-maps"
          f"{'' if full else '; partial run: nothing written'})")
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
