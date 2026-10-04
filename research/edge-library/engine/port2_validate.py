#!/usr/bin/env python3
"""TESTER-MATCH GATE of port group 2 (families/port2.py: ema_ribbon, tema_slope, ema_pullback, supertrend, rsi2,
first_bar_mom, tod_drift, mid_fade) -- ENGINE.md 8. Writes PORT2_VALIDATION.md + out/port2_validation.json.

Trade IDENTITY only. The old pilots' IN-SAMPLE tester bundles (2021-09-22 .. 2024-12-31) are replayed and compared trade for
trade; no result is judged, no P&L is printed or written (only counts, match rates and the sim-minus-tester net difference),
nothing dated >= 2025-01-01 is read: only the stages `screen` and `sizing` of R/jobs.jsonl (NQ) and RE/jobs.jsonl (ES) are
taken -- never `holdout`, never a walk-forward -- every bundle's range is asserted to end before 2025 BEFORE its trades are
opened, and rows outside the in-sample window are dropped by the loaders.

  NQ   32 screen runs (8 families x tf 1 / 5 / 15 / 30, default inputs) + every cell of the 16 sizing heat-maps
  ES   32 screen runs + every cell of the 13 sizing heat-maps (ES-pilot drafts pp_es_<fam>: the same family code)
  GC   no GC tester run exists (EDGE_VALIDATION.md "GC"): the ports run on GC with the same code; nothing to match.

Gate per bundle / cell (ENGINE.md 8): >= 99 % of the trades identical on (date, side, entry time +-1 s, entry price, exit
price, exit reason), net within 0.5 %, the same skipped days (runs), no session dropped by a strategy error.

PROVENANCE. Every family x root pass is stamped with the sha256 of families/port2.py and l2sim.py read BEFORE the pass and
checked again AFTER it: a file that changed while a pass ran aborts the gate (nothing is stamped, no report). A resumed run
reuses a finished family x root only when both hashes still match, so the report's hash line is true for EVERY row.
`code_sha()` = the hash of the TRADING code alone (every method's syntax tree, every class attribute, the registered default
inputs): a later edit of registry metadata, comments or docstrings changes the file hash but not the code hash, and the
gate then still stands for the code on disk (tests/test_port2.py checks exactly that).

Usage: python port2_validate.py [--workers 2] [--roots NQ,ES] [--families a,b] [--days N]     (--days: a quick subset, no report)
       python port2_validate.py --fresh        forget the resume file first (a clean, single-hash run)
"""
from __future__ import annotations

import argparse
import ast
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
from families import port2                      # noqa: E402

START, END = V.START, V.END
FAMS = {name: e[0] for name, e in port2.FAMILIES.items()}
PILOTS = {"NQ": (S.R, "draft_pp_"), "ES": (S.RE, "draft_pp_es_")}
STAGES = ("screen", "sizing")                   # in-sample stages only; `holdout` (2025+) and walk-forwards are never opened
ID_GATE, NET_GATE = EV.ID_GATE, EV.NET_GATE
HASHED = ("l2sim.py", "families/port2.py", "port2_validate.py", "sim_validate.py", "edge_validate.py")
MENU_KEYS = ("stop_mode", "stop_val", "tgt_r", "max_tr")      # the old sizing axes: never part of a family-parameter variant


def bundles(root: str, fams=None) -> list:
    """[(key, family, kind 'run' | 'grid', tester id)] of the pilot's in-sample jobs of the eight families, in job order."""
    d, pre = PILOTS[root]
    out = []
    for line in (d / "jobs.jsonl").read_text().splitlines():
        j = json.loads(line)
        fam = j.get("strategy", "")[len(pre):] if j.get("strategy", "").startswith(pre) else None
        if root == "NQ" and fam and fam.startswith("es_"):
            fam = None
        if fam not in FAMS or (fams and fam not in fams) or j.get("stage") not in STAGES or j.get("status") != "done":
            continue
        if j["kind"] not in ("run", "grid"):
            continue
        out.append((j["key"], fam, j["kind"], j["id"]))
    return out


def load(root: str, items: list) -> list:
    """-> [{'key', 'family', 'kind', 'src', 'cell', 'inputs', 'ref', 'skipped'}] one row per run / heat-map cell."""
    rows = []
    for key, fam, kind, tid in items:
        if kind == "run":
            inputs, ref, cov, r = EV.load_run(tid)                    # asserts range end < 2025 and not holdout, before the trades
            assert r == root, (key, r)
            rows.append({"key": key, "family": fam, "kind": kind, "src": tid, "cell": None, "inputs": inputs, "ref": ref,
                         "skipped": [s["date"] for s in cov["skipped"] if START <= s["date"] <= END]})
        else:
            g = json.loads((V.GRIDS / tid / "grid.json").read_text())
            assert g["range"]["end"] < "2025-01-01" and not g["range"].get("holdout"), f"{key}: the heat-map reaches the exam period"
            for i in range(g["total"]):
                inputs, ref, cov, cost, engine = V.load_bundle(f"{tid}#{i}")      # asserts the cell's range end < 2025
                assert (cost["qty"], cost["commission"], cost["slippage_ticks"], engine) == (1, 4.0, 1.0, "tick-2"), (key, i)
                rows.append({"key": key, "family": fam, "kind": kind, "src": tid, "cell": i, "inputs": inputs, "ref": ref,
                             "skipped": [s["date"] for s in cov["skipped"] if START <= s["date"] <= END]})
    return rows


def gate_family(root: str, fam: str, items: list, workers: int, days=None) -> list:
    """ONE tape pass over every bundle / cell of one family on one root -> one summary dict per tester job."""
    rows = load(root, items)
    kw = {"days": days} if days else {}
    res = S.run_many([(FAMS[fam], r["inputs"]) for r in rows], *(() if days else (START, END)), root=root, workers=workers, **kw)
    keep = set(days) if days else None
    out = {}
    for r, x in zip(rows, res):
        ref = [t for t in r["ref"] if keep is None or t["date"] in keep]
        c = V.compare(x["trades"], ref)
        o = out.setdefault(r["key"], {"key": r["key"], "root": root, "family": fam, "kind": r["kind"], "src": r["src"], "cells": 0,
                                      "cells_identical": 0, "n_ref": 0, "n_sim": 0, "matched": 0, "exact_all_fields": 0,
                                      "min_match_rate": 1.0, "max_net_diff_pct": 0.0, "max_abs_net_diff": 0.0, "skipped_by_error": 0,
                                      "skips_equal": True, "both_sides_sessions": 0, "elapsed_s": x["elapsed_s"],
                                      "first_unmatched": None, "variant_cells": {}})
        same = c["exact_all_fields"] == c["n_ref"] == c["n_sim"]
        o["cells"] += 1
        o["cells_identical"] += int(same)
        vid = variant_of(fam, r["inputs"])
        if vid is not None:                                               # this run / cell IS a registered variant of the family
            v = o["variant_cells"].setdefault(vid, {"cells": 0, "identical": 0, "trades": 0})
            v["cells"] += 1
            v["identical"] += int(same)
            v["trades"] += c["n_ref"]
        for k in ("n_ref", "n_sim", "matched", "exact_all_fields"):
            o[k] += c[k]
        rate = 1.0 if c["n_ref"] == c["n_sim"] == 0 else c["match_rate"]          # an empty cell on both sides is identical
        o["min_match_rate"] = min(o["min_match_rate"], rate)
        o["max_net_diff_pct"] = max(o["max_net_diff_pct"], c["net_diff_pct"])
        o["max_abs_net_diff"] = max(o["max_abs_net_diff"], abs(c["net_diff"]))
        o["skipped_by_error"] += x["skipped_by_error"]
        o["both_sides_sessions"] += x["both_sides_sessions"]
        if keep is None:
            o["skips_equal"] = o["skips_equal"] and [s["date"] for s in x["skipped"]] == r["skipped"]
        if o["first_unmatched"] is None and (c["unmatched_ref"] or c["unmatched_sim"]):
            pick = lambda t: {k: t.get(k) for k in ("date", "side", "entry_ms", "entry_price", "exit_price", "exit_reason")}   # noqa: E731
            o["first_unmatched"] = {"cell": r["cell"], "inputs": r["inputs"], "ref": [pick(t) for t in c["unmatched_ref"][:3]],
                                    "sim": [pick(t) for t in c["unmatched_sim"][:3]]}
    for o in out.values():
        o["pass"] = bool(o["min_match_rate"] >= ID_GATE and o["max_net_diff_pct"] <= NET_GATE and o["skips_equal"]
                         and o["skipped_by_error"] == 0 and o["both_sides_sessions"] == 0 and (o["n_ref"] > 0 or keep is not None))
    return list(out.values())


def variant_of(fam: str, inputs: dict) -> str | None:
    """The id of the REGISTERED family-parameter variant a tester run / heat-map cell was run with ('default' for {}), or
    None when its family inputs are not a registered variant (e.g. tod_drift exit_bars 12, or a value off the first axis).
    The old sizing axes (stop, target, max_tr) are ignored: the menu owns them."""
    cls, base, lib = port2.FAMILIES[fam][0], port2.FAMILIES[fam][1], port2.FAMILIES[fam][4]
    own = {k for c in cls.__mro__ if c not in S.Template.__mro__ for k in c.__dict__.get("DEFAULTS", {})} - set(MENU_KEYS)
    d = {**cls.defaults(), **base}
    for v in lib["variants"]:
        want = {**{k: d[k] for k in own}, **v}
        if all(inputs.get(k, d[k]) == val for k, val in want.items()):
            return S.cell_id(v) if v else "default"
    return None


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def shas() -> dict:
    return {f: sha(HERE / f) for f in HASHED}


def _no_doc(body: list) -> list:
    first = body[0] if body else None
    is_doc = isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) and isinstance(first.value.value, str)
    return body[1:] if is_doc else body


def code_sha(path: Path | None = None) -> str:
    """sha256/16 of the TRADING code of families/port2.py: for each registered family its class -- every method's syntax
    tree (docstrings dropped), every class attribute's value, its bases -- and its registered default inputs + both_sides.
    Registry metadata (notes, rationale, complexity, variants, weak, penalty), the module's helper functions, comments and
    docstrings are NOT part of it: none of them can change a trade."""
    tree = ast.parse((path or HERE / "families" / "port2.py").read_text())
    nodes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    h = hashlib.sha256()
    for name, entry in port2.FAMILIES.items():
        cls, inputs, both = entry[:3]
        node = nodes[cls.__name__]
        h.update(f"{name}|{cls.__name__}|{[b.__module__ + '.' + b.__name__ for b in cls.__bases__]}|".encode())
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                item.body = _no_doc(item.body)
                h.update(ast.dump(item).encode())
        attrs = sorted((k, repr(v)) for k, v in vars(cls).items() if not k.startswith("__") and not callable(v))
        h.update(repr(attrs).encode())
        h.update(json.dumps([inputs, both], sort_keys=True).encode())
    return h.hexdigest()[:16]


def render(out: dict) -> str:
    rows = out["rows"]
    L = ["# PORT2_VALIDATION — port group 2 (families/port2.py) vs the Homebase Strategy Tester", "",
         f"Generated {out['when']} by `port2_validate.py`, {out['workers']} worker processes. Raw: `out/port2_validation.json`.",
         "File sha256/16, read before every family x root pass and checked after it (the SAME for every row below): "
         + ", ".join(f"`{f}` {h}" for f, h in out["sha"].items()) + f". Trading-code hash of `families/port2.py` (classes + "
         f"registered default inputs; metadata and docstrings excluded): **{out['code_sha']}**.",
         "In-sample bundles of the old pilots only (2021-09-22 → 2024-12-31; stages `screen` and `sizing` of R / RE `jobs.jsonl`), trade "
         "IDENTITY only: no P&L is shown; nothing dated ≥ 2025-01-01 was read (no `holdout` stage bundle, no walk-forward).", "",
         f"## Verdict: {'ALL GATES PASS' if out['pass'] else 'A GATE FAILED'}",
         f"Gate per bundle / heat-map cell: ≥ {ID_GATE * 100:.0f} % identical trades (date, side, entry time ±1 s, entry price, exit price, "
         f"exit reason), net within {NET_GATE} %, the same skipped days, no session dropped by a strategy error, no both-side session.", "",
         "| family | root | bundles | runs + cells | 100 % identical (all 20 fields) | tester trades | sim trades | all-fields identical | "
         "worst match | max net diff % | pass |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for root in out["roots"]:
        for fam in FAMS:
            xs = [r for r in rows if r["root"] == root and r["family"] == fam]
            if not xs:
                continue
            L.append(f"| {fam} | {root} | {len(xs)} | {sum(r['cells'] for r in xs)} | {sum(r['cells_identical'] for r in xs)} | "
                     f"{sum(r['n_ref'] for r in xs)} | {sum(r['n_sim'] for r in xs)} | {sum(r['exact_all_fields'] for r in xs)} | "
                     f"{min(r['min_match_rate'] for r in xs) * 100:.2f}% | {max(r['max_net_diff_pct'] for r in xs):.3f} | "
                     f"{all(r['pass'] for r in xs)} |")
    L += ["", "## Every bundle",
          "| bundle | root | family | kind | cells | cells 100 % identical | tester trades | sim trades | all-fields identical | worst match | "
          "max net diff % | skipped days equal | pass |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['key']} | {r['root']} | {r['family']} | {r['kind']} | {r['cells']} | {r['cells_identical']} | {r['n_ref']} | "
                 f"{r['n_sim']} | {r['exact_all_fields']} | {r['min_match_rate'] * 100:.2f}% | {r['max_net_diff_pct']:.3f} | "
                 f"{r['skips_equal']} | {r['pass']} |")
    L += ["", "## Every registered family-parameter variant was matched",
          "Tester runs / heat-map cells whose family inputs ARE a registered variant (the old sizing axes stop / target / max_tr aside), "
          "NQ + ES. A variant without a tester cell would rest on code identity alone.", "",
          "| family | variant | tester runs + cells | 100 % identical | tester trades |", "|---|---|---|---|---|"]
    for fam, vs in out["variants"].items():
        for v in vs:
            L.append(f"| {fam} | {v['id']} | {v['cells']} | {v['identical']} | {v['trades']} |")
    bad = [r for r in rows if r["first_unmatched"]]
    if bad:
        L += ["", "## First unmatched trades (identity fields only)"]
        for r in bad:
            L.append(f"* `{r['key']}` ({r['root']}): `{json.dumps(r['first_unmatched'], default=str)}`")
    L += ["", "## Coverage of this gate",
          "* Inputs exercised by a tester bundle: tf 1 / 5 / 15 / 30, `stop_mode` atr and pts, `stop_val`, `tgt_r`, `max_tr` 1 / 3, "
          "tema_slope `n`, rsi2 `th`, first_bar_mom `k`, tod_drift `off_min` / `exit_bars` / `dir`. NOT exercised by any bundle: "
          "`stop_mode` struct and pct, `trail_atr`, rsi2 `trend_f`, mid_fade `k` other than 0.3, the sessions `pre` / `eve` "
          "(the tester cannot run them), root GC (no GC tester run exists).",
          "* Those paths are covered by `tests/test_port2.py` instead: an INDEPENDENT oracle (numpy, straight from the prints, no "
          "Template) of every family's first signal in all seven sessions on NQ, ES and GC, with the entry print, the stop and "
          "the target checked for the atr, pts and pct stop modes; plus the no-look-ahead and worker-identity tests. GC members "
          "stay flagged (ENGINE.md 11.1): no GC tester bundle exists.",
          "* `mid_fade` reads the daily ATR (`datr()`): the bundles cover it for the full-window run; a run that starts later has a "
          "longer daily history than a tester run of the same sub-range would (SIM_VALIDATION.md, coverage).", "",
          "## Reproduce", '`"~/ONYX TRADING/.venv/bin/python" port2_validate.py --fresh --workers 2` in `engine/` (one tape pass per family '
          "and root; without `--fresh` a finished family x root with unchanged hashes is not replayed).",
          ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="port2_validate.py")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--roots", default="NQ,ES")
    ap.add_argument("--families", default="")
    ap.add_argument("--days", type=int, default=0, help="quick subset: the first N in-sample sessions of 2023-03 (no report written)")
    ap.add_argument("--fresh", action="store_true", help="forget the resume file: every family x root is replayed")
    a = ap.parse_args(argv)
    roots = [r for r in a.roots.split(",") if r]
    fams = [f for f in a.families.split(",") if f] or list(FAMS)
    partial = (HERE / "out" / "port2_validation.partial.jsonl")
    (HERE / "out").mkdir(exist_ok=True)
    full = not a.days and set(fams) == set(FAMS)
    start = shas()                                                  # the code this gate is about: it may not change under it
    stamp = start["families/port2.py"] + start["l2sim.py"]
    if a.fresh and full and partial.exists():
        partial.unlink()
    done = {}
    if full and partial.exists():                                   # resume: a family x root that finished is not replayed
        for line in partial.read_text().splitlines():
            r = json.loads(line)
            if r.get("sha") == stamp:
                done.setdefault((r["root"], r["family"]), []).append(r)
    rows = []
    for root in roots:
        days = [d.isoformat() for d in S.sessions("2023-03-01", "2023-03-31", root)][:a.days] if a.days else None
        for fam in fams:
            items = bundles(root, [fam])
            if not items:
                continue
            if (root, fam) in done:
                got = done[(root, fam)]
            else:
                S.wait_compute_window()
                got = gate_family(root, fam, items, a.workers, days)
                now = shas()
                if now != start:                                    # the workers of this pass may have imported other code
                    changed = sorted(f for f in HASHED if now[f] != start[f])
                    print(f"ABORTED: {changed} changed while the gate was running ({root} {fam} is not stamped, no report). "
                          "Re-run: finished passes whose hashes still match are reused.", file=sys.stderr)
                    return 3
                if full:
                    with partial.open("a") as f:
                        for r in got:
                            f.write(json.dumps({**r, "sha": stamp}, default=str) + "\n")
            rows += got
            print(f"{root} {fam}: {len(got)} bundles, {sum(r['cells'] for r in got)} runs + cells, "
                  f"{sum(r['cells_identical'] for r in got)} identical, trades tester {sum(r['n_ref'] for r in got)} sim "
                  f"{sum(r['n_sim'] for r in got)} exact {sum(r['exact_all_fields'] for r in got)}, "
                  f"{'PASS' if all(r['pass'] for r in got) else 'FAIL'} ({got[0]['elapsed_s']} s)", flush=True)
    ok = bool(rows) and all(r["pass"] for r in rows)
    if not full or set(roots) != {"NQ", "ES"}:
        print("subset run:", "all pass" if ok else "A GATE FAILED", "(no report written)")
        for r in rows:
            if not r["pass"]:
                print(json.dumps({k: r[k] for k in ("key", "root", "cells", "cells_identical", "n_ref", "n_sim", "matched",
                                                    "min_match_rate", "skips_equal", "skipped_by_error", "first_unmatched")}, default=str))
        return 0 if ok else 1
    variants = {}
    for fam in FAMS:                                                # every registered variant: matched by >= 1 tester run / cell
        vs = []
        for v in port2.FAMILIES[fam][4]["variants"]:
            vid = S.cell_id(v) if v else "default"
            hit = [r["variant_cells"][vid] for r in rows if r["family"] == fam and vid in r.get("variant_cells", {})]
            vs.append({"id": vid, "variant": v, "cells": sum(h["cells"] for h in hit), "identical": sum(h["identical"] for h in hit),
                       "trades": sum(h["trades"] for h in hit)})
        variants[fam] = vs
    v_ok = all(v["cells"] >= 1 and v["identical"] == v["cells"] and v["trades"] > 0 for vs in variants.values() for v in vs)
    out = {"when": dt.datetime.now(S.ET).strftime("%Y-%m-%d %H:%M ET"), "roots": roots, "rows": rows, "pass": bool(ok and v_ok),
           "range": [START, END], "workers": a.workers, "sha": start, "sha_end": shas(), "code_sha": code_sha(),
           "row_stamps": sorted({r.get("sha", stamp) for r in rows}), "variants": variants, "variants_pass": v_ok}
    if out["sha_end"] != start or out["row_stamps"] != [stamp]:
        print("ABORTED: the code changed under the gate, or a row carries another hash (no report written)", file=sys.stderr)
        return 3
    (HERE / "out" / "port2_validation.json").write_text(json.dumps(out, indent=1, default=str))
    (HERE / "PORT2_VALIDATION.md").write_text(render(out))
    print("ALL GATES PASS" if out["pass"] else "A GATE FAILED")
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
