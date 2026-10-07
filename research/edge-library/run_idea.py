#!/usr/bin/env python3
"""run_idea.py -- IDEAS AS SETTINGS: an idea = a JSON spec built from tested blocks (engine/families/blocks.py), not new code.

SPEC  ideas/specs/<name>.json
    {"name": "r3_orb",                      = the file name; lower-case letters, digits, '_' (no '__')
     "reason": "...",                       REQUIRED, plain words, written before any test: why should this make money
     "family": "orb",                       the entry type: a bar-based library family (blocks.WRAPPED)
     "markets": ["NQ", "ES", "GC"],
     "bar_sizes": ["5", "15"],
     "sessions": ["nyam", "mid", "pm"],     of asia london pre nyam mid pm eve; one independent instance per session
     "params": {"or_min": ["5", "15"]},     the MAIN parameter values: every combination = one variant (a heat-map row)
     "fixed": {"mode": "break"},            optional: family inputs held at one value
     "filters": [{"block": "news", "side": "yes"}, ...],     each entry = ONE separate filter unit (blocks.FILTERS);
                                            the book block is NQ only and is left out on the other markets
     "exits": "extended",                   "standard" = the 32-cell menu | "extended" = + the new stops and targets (78; 60
                                            for a family without a structure)
     "filter_exits": "standard",            optional: the menu of the FILTER units (default: the same as "exits")
     "limits": {"max_tr": 1, "dir": "both"}}  optional: max_tr (entries per session), dir, exit_bars, trail_atr

UNITS  one BASE unit per market x bar size, key <name>-<ROOT>-tf<tf>, and one FILTER unit per filter entry, key
    <name>__<block>_<side>-<ROOT>-tf<tf>. A unit = every variant x every exit cell, each cell run as one instance per session
    with hold_to = day (flat 15:58 ET), 1 contract: the library's convention (run_menus). Stores: runs/<key>/ (the library's
    BUILD stores, the format of library.write_unit; run.json `family` = the entry family, `idea` = the spec name, `filter`);
    one ledger row per store (stage `build`, kind `grid`: CANDIDATE cells, counted against the cap). judge.py addresses a
    unit as <key>-<session>; `catalog` writes the CSV `judge.py table --stage <file>` reads.
CONTROLS (stage `null`, never capped; all in runs/)
    c1-<ROOT>-tf<tf>           the standard C1 pool (64 cells): random entries, the 32 standard exit cells -- run if missing
    c1x-<ROOT>-tf<tf>          the same random entries with the extended menu's other cells that need no structure (56 cells,
                               ids s<seed>_<exit id> as in the C1 pool)
    <name>__c1r-<ROOT>-tf<tf>  range stops: random entries that carry the idea's own structure height (blocks.CONTROLS), one
                               per structure parameter value x seeds 1, 2 x the 18 range cells, the idea's sessions
                               (ids s<seed>_<structure inputs>_<exit id>)
    <key>-c2s1, <key>-c2s2     a BOOK filter unit only (NQ): the same grid on a shuffled book (score.C2Features, seeds 1, 2)
    A filter unit uses the same random pools: the judge matches by day and session, so a day filter is matched by itself.
CAP  80,000 candidate cells (library.CAPS still says 50,000: the cap is handed to the ledger calls, as out/v2/run_v2.py did).
    `plan` and `build` refuse a spec that does not fit: ledger + the cells booked on paper + the spec's cells still to run.

    python run_idea.py plan   <spec> [<spec> ...]          units, candidate cells, null cells, the cap (nothing runs)
    python run_idea.py build  <spec> [--workers 8]         BUILD menus + controls; restartable (a stored key is skipped)
    python run_idea.py status <spec> [<spec> ...]          pending keys
    python run_idea.py catalog <spec> [...] [--out FILE]   key,sess rows of every unit x session (for judge.py table --stage)
    python run_idea.py smoke  <spec> [--root NQ] [--tf 5] [--days 5] [--workers 2]     bug check, COUNTS ONLY, nothing stored
<spec> = a name (ideas/specs/<name>.json), a path, or a pattern in quotes ('r3_*').
P&L-BLIND: nothing here prints or reads a net, a win rate or a profit factor; judging is another tool's job.
BUILD only (2021-09-22 .. 2023-12-31). <= 8 workers (l2sim.MAX_WORKERS); l2sim waits out 09:18-09:36 ET by itself.
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
import time
from pathlib import Path

W = Path(__file__).resolve().parent
ENGINE = W / "engine"
for _p in (str(W), str(ENGINE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import l2sim as S      # noqa: E402
import library as LB   # noqa: E402
import run_menus as RM  # noqa: E402

SPECS = W / "ideas" / "specs"
RUNS = LB.RUNS                                         # the library's BUILD stores: what judge.py reads
LOG = W / "out" / "run_idea.log"
CAPS = {"runs": 2000, "cells": 80000, "wfs": 40}       # the candidate cap of this stage (module docstring)
PERIOD = RM.PERIOD
KEYS = ("name", "reason", "family", "markets", "bar_sizes", "sessions", "params", "fixed", "filters", "exits", "filter_exits",
        "limits")
REQUIRED = ("name", "reason", "family", "markets", "bar_sizes", "sessions", "params", "exits")
LIMIT_KEYS = ("max_tr", "dir", "exit_bars", "trail_atr")
C1_P_ENTRY = RM.C1_P_ENTRY


class SpecError(ValueError):
    """An idea spec that breaks the format (the message names the field)."""


def _blocks():
    fam = RM.registry()
    from families import blocks
    return fam, blocks


def _reserved(blocks) -> set:
    own = {k for sides in blocks.FILTERS.values() for inp in sides.values() for k in inp}
    return {"tf", "sess", "hold_to", "stop_mode", "stop_val", "tgt_r", "f_depth", "f_book", "x_book", "f_thin", *own, *LIMIT_KEYS}


def spec_paths(args: list) -> list:
    out = []
    for a in args:
        p = Path(a)
        if any(ch in a for ch in "*?["):
            hits = sorted(SPECS.glob(a if a.endswith(".json") else a + ".json"))
            if not hits:
                raise SpecError(f"no spec matches {a!r} in {SPECS}")
            out += hits
        else:
            out.append(p if p.suffix == ".json" else SPECS / f"{a}.json")
    return out


def load_spec(path) -> dict:
    """Read and check ONE spec. -> the spec with defaults filled in (fixed, filters, limits, filter_exits) and `variants`."""
    path = Path(path)
    try:
        sp = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise SpecError(f"{path}: {e}") from None
    return check_spec(sp, path.stem)


def check_spec(sp: dict, stem: str | None = None) -> dict:
    fam, blocks = _blocks()
    if not isinstance(sp, dict):
        raise SpecError("a spec is a JSON object")
    unknown, missing = sorted(set(sp) - set(KEYS)), [k for k in REQUIRED if k not in sp]
    if unknown or missing:
        raise SpecError(f"unknown fields {unknown}, missing fields {missing}; the fields are {KEYS}")
    name = sp["name"]
    if not (isinstance(name, str) and re.fullmatch(r"[a-z][a-z0-9_]*", name) and "__" not in name):
        raise SpecError(f"name {name!r}: lower-case letters, digits and '_' (no '__'); it becomes the store key")
    if name in fam.REGISTRY or name.startswith("c1"):
        raise SpecError(f"name {name!r} is a family name or a control prefix: its stores would collide with theirs")
    if stem is not None and stem != name:
        raise SpecError(f"name {name!r} must be the file name ({stem}.json)")
    reason = sp["reason"]
    if not (isinstance(reason, str) and len(reason.split()) >= 8):
        raise SpecError("reason is REQUIRED: plain words (>= 8 of them), written before any test -- why should this make money")
    family = sp["family"]
    if family not in blocks.WRAPPED:
        raise SpecError(f"family {family!r}: one of {sorted(blocks.WRAPPED)}")
    cls, lib = blocks.WRAPPED[family], fam.library(family)

    def _list(key, allowed, what):
        v = sp[key]
        if not (isinstance(v, list) and v and len(set(map(str, v))) == len(v) and all(str(x) in allowed for x in v)):
            raise SpecError(f"{key} {v!r}: a non-empty list without repeats out of {what} {tuple(allowed)}")
        return [str(x) for x in v]

    markets = _list("markets", lib["roots"], "the family's markets")
    tfs = _list("bar_sizes", cls.SCREEN_TFS, "the family's bar sizes")
    sessions = _list("sessions", RM.DAY_PASSES, "the sessions")
    reserved, inputs = _reserved(blocks), cls.defaults()
    params, fixed, limits = sp["params"], sp.get("fixed", {}), sp.get("limits", {})
    if not (isinstance(params, dict) and all(isinstance(v, list) and v for v in params.values())):
        raise SpecError("params: {input: [values, ...]} (an empty object = the family's defaults only)")
    if not isinstance(fixed, dict) or not isinstance(limits, dict):
        raise SpecError("fixed and limits are objects {input: value}")
    for what, keys in (("params", params), ("fixed", fixed)):
        bad = sorted(k for k in keys if k in reserved or k not in inputs)
        if bad:
            raise SpecError(f"{what} {bad}: not inputs of {family} that a spec may set here (its own inputs: "
                            f"{sorted(k for k in inputs if k not in reserved and k not in S.Template.DEFAULTS)}; exits, filters, sessions "
                            "and limits have their own fields)")
    if set(params) & set(fixed):
        raise SpecError(f"{sorted(set(params) & set(fixed))}: in params AND in fixed")
    bad = sorted(set(limits) - set(LIMIT_KEYS))
    if bad:
        raise SpecError(f"limits {bad}: one of {LIMIT_KEYS}")
    for key in ("exits", "filter_exits"):
        if sp.get(key, "standard") not in ("standard", "extended", "blueprint"):      # 'blueprint': set by blueprint/runner.py only (its 48-cell table)
            raise SpecError(f"{key} {sp.get(key)!r}: 'standard' or 'extended'")
    filters = []

    def one(f):
        if not (isinstance(f, dict) and set(f) == {"block", "side"}):
            raise SpecError(f"filter {f!r}: an object {{'block': ..., 'side': ...}}")
        if f["block"] not in blocks.FILTERS or f["side"] not in blocks.FILTERS[f["block"]]:
            raise SpecError(f"filter {f!r}: blocks and sides are { {b: tuple(s) for b, s in blocks.FILTERS.items()} }")
        return (f["block"], f["side"])
    for f in sp.get("filters", []):
        if isinstance(f, dict) and set(f) == {"all"}:             # two filters ON TOGETHER: {"all": [{block, side}, {block, side}]} (a unit of its own)
            ps = [one(x) for x in f["all"]] if isinstance(f["all"], list) else None
            if not ps or not 2 <= len(ps) <= blocks.MAX_FILTERS or len({b for b, _ in ps}) < len(ps):
                raise SpecError(f"filter {f!r}: 2 to {blocks.MAX_FILTERS} filters of different blocks")
            fl = blocks.combine(ps)
        else:
            fl = one(f)
        if fl in filters:
            raise SpecError(f"filter {f!r} is listed twice")
        filters.append(fl)
    for fl in [x for x in filters if blocks.COMBO in x[0]]:      # a combined unit needs each of its filters alone to hold it against
        for single in blocks.parts(fl):
            if single not in filters:
                filters.insert(filters.index(fl), single)
    variants = [dict(zip(params, combo)) for combo in itertools.product(*params.values())]
    out = {"name": name, "reason": reason.strip(), "family": family, "markets": markets, "bar_sizes": tfs, "sessions": sessions,
           "params": params, "fixed": dict(fixed), "filters": filters, "exits": sp["exits"],
           "filter_exits": sp.get("filter_exits", sp["exits"]), "limits": dict(limits), "variants": variants}
    try:
        dead = [s for s in sessions if not cls({**fixed, **limits, **variants[0], "tf": tfs[0], "sess": s}).sessions()]
    except ValueError as e:
        raise SpecError(f"fixed / limits / params: {e}") from None
    if dead:
        raise SpecError(f"sessions {dead}: {family} never trades there (its own session filter)")
    for root in markets:                                # every cell must be a legal set of inputs before anything runs
        for u in spec_units(out, roots=[root], tfs=tfs[:1]):
            for c in u["grid"]:
                try:
                    c["spec"][0]({**c["spec"][1], "sess": sessions[0], "hold_to": RM.HOLD})
                except ValueError as e:
                    raise SpecError(f"{u['key']} cell {c['id']}: {e}") from None
    return out


def unit_key(spec: dict, root: str, tf: str, filt=None) -> str:
    return f"{spec['name']}{'__' + '_'.join(filt) if filt else ''}-{root}-tf{tf}"           # a combined filter: name__ote+pdz_in+with-NQ-tf5


def spec_units(spec: dict, roots=None, tfs=None) -> list:
    """Every candidate unit of a spec, in run order (market, bar size, base then filters):
    [{key, root, tf, filter (block, side) | None, exits, grid, cells, book}]."""
    _, blocks = _blocks()
    cls, family = blocks.WRAPPED[spec["family"]], spec["family"]
    out = []
    for root in (roots or spec["markets"]):
        for tf in (tfs or spec["bar_sizes"]):
            for filt in [None] + list(spec["filters"]):
                if filt and blocks.reads(filt, blocks.L2_BLOCKS) and root not in S.L2_ROOTS:
                    continue                             # Level 2 is NQ only: no such unit on the other markets
                kind = spec["filter_exits"] if filt else spec["exits"]
                base = {**spec["fixed"], **spec["limits"], **(blocks.filter_inputs(*filt, root) if filt else {}),
                        "tf": str(tf), "sess": "all"}
                grid = S.menu_grid(cls, base, root, spec["variants"], blocks.exits(kind, root, family))
                out.append({"key": unit_key(spec, root, tf, filt), "root": root, "tf": str(tf), "filter": filt, "exits": kind,
                            "grid": grid, "cells": len(grid), "book": bool(filt and blocks.reads(filt, blocks.L2_BLOCKS))})
    return out


def struct_variants(spec: dict) -> list:
    """The distinct values of the STRUCTURE inputs over the spec's variants (the inputs the family's height reads): the
    range-stop control needs one random pool per structure, not per variant."""
    _, blocks = _blocks()
    keys = blocks.HEIGHTS[spec["family"]][2]
    out = []
    for v in spec["variants"]:
        pv = {k: {**spec["fixed"], **v}[k] for k in keys if k in v or k in spec["fixed"]}
        if pv not in out:
            out.append(pv)
    return out


def spec_controls(spec: dict, roots=None, tfs=None) -> list:
    """The control stores a spec needs: [{key, kind 'c1' | 'c1x' | 'c1r' | 'c2', root, tf, cells, grid, sessions, seed}]."""
    _, blocks = _blocks()
    import l2ref
    family = spec["family"]
    ext = "extended" in (spec["exits"], spec["filter_exits"] if spec["filters"] else spec["exits"])
    out = []
    for root in (roots or spec["markets"]):
        for tf in (tfs or spec["bar_sizes"]):
            tf = str(tf)
            out.append({"key": f"c1-{root}-tf{tf}", "kind": "c1", "root": root, "tf": tf, "cells": 64})
            if ext:
                menu = blocks.menu_extended(root, rng=True)
                idx = {S.cell_id(x): i for i, x in enumerate(menu)}
                extra = [x for x in menu[32:] if x["stop_mode"] != "rng"]
                gx = [{"id": f"s{sd}_{S.cell_id(x)}", "variant": {"seed": sd}, "exit": x, "vi": sd - 1, "xi": idx[S.cell_id(x)],
                       "spec": (l2ref.Random, {"tf": tf, "sess": "all", "p_entry": C1_P_ENTRY, "seed": sd, **x})}
                      for sd in RM.NULL_SEEDS for x in extra]
                out.append({"key": f"c1x-{root}-tf{tf}", "kind": "c1x", "root": root, "tf": tf, "cells": len(gx), "grid": gx,
                            "sessions": list(RM.DAY_PASSES)})
            if ext and family in blocks.HEIGHTS:
                ctl, svs = blocks.CONTROLS[family], struct_variants(spec)
                gr = [{"id": "_".join(k for k in (f"s{sd}", S.cell_id(pv) if pv else "", S.cell_id(x)) if k),
                       "variant": {**pv, "seed": sd}, "exit": x, "vi": pi * len(RM.NULL_SEEDS) + sd - 1, "xi": idx[S.cell_id(x)],
                       "spec": (ctl, {"tf": tf, "sess": "all", "p_entry": C1_P_ENTRY, "seed": sd, **pv, **x})}
                      for pi, pv in enumerate(svs) for sd in RM.NULL_SEEDS for x in menu if x["stop_mode"] == "rng"]
                out.append({"key": f"{spec['name']}__c1r-{root}-tf{tf}", "kind": "c1r", "root": root, "tf": tf, "cells": len(gr),
                            "grid": gr, "sessions": list(spec["sessions"])})
            for u in spec_units(spec, [root], [tf]):     # a book filter unit: + the same grid on a shuffled book, two seeds
                if u["book"]:
                    out += [{"key": f"{u['key']}-c2s{sd}", "kind": "c2", "root": root, "tf": tf, "cells": u["cells"], "grid": u["grid"],
                             "sessions": list(spec["sessions"]), "seed": sd, "unit": u} for sd in RM.NULL_SEEDS]
    return out


def cell_specs(cell: dict, sessions: list) -> list:
    """The run_many specs of ONE cell: one independent instance per session of the spec (hold_to = day), without the
    sessions the class never trades -- run_menus.cell_specs restricted to the spec's sessions."""
    cls, params = cell["spec"]
    specs = [(cls, {**params, "sess": s, "hold_to": RM.HOLD}) for s in sessions]
    live = [x for x in specs if cls(x[1]).sessions()]
    return live or specs[:1]


def run_grid(grid: list, sessions: list, root: str, *, features, workers: int, days=None, kw=None) -> list:
    """ONE tape pass for a grid (run_menus.run_grid with the spec's sessions) -> one merged result per cell."""
    specs, cut = [], [0]
    for c in grid:
        specs += cell_specs(c, sessions)
        cut.append(len(specs))
    kw = dict(kw or {})
    res = (S.run_many(specs, period=PERIOD, root=root, workers=workers, features=features, **kw) if days is None else
           S.run_many(specs, days=list(days), root=root, workers=workers, features=features, **kw))
    return [RM.merge(res[a:b]) for a, b in zip(cut, cut[1:])]


def done(key: str, stage: str, runs_dir=None, ledger=None) -> bool:
    return RM.done(key, RUNS if runs_dir is None else runs_dir, ledger, stage)


def _features(unit: dict):
    _, blocks = _blocks()
    return S.L2Features(blocks.BOOK_COLS) if unit.get("book") else None


def _record(key, grid, res, root, meta, stage, kw, runs_dir, ledger, log, workers, wall) -> dict:
    """run_menus._record with this stage's cap handed to the ledger."""
    errs = sum(r["skipped_by_error"] for r in res)
    base = dict(family=meta.get("family", ""), root=root, tf=meta.get("tf", ""), period=PERIOD, control=meta.get("control", ""),
                seed=meta.get("seed", ""), elapsed_s=res[0]["elapsed_s"], path=ledger, caps=CAPS)
    kind = "null" if stage == "null" else "grid"
    if errs:
        bad = next(r for r in res if r["skipped_by_error"])
        why = next(n["reason"] for n in bad["no_trade"] if n["reason"].startswith(S.ERROR_PREFIX))
        RM._log(f"ERROR {key}: sessions dropped by a strategy error ({why}); no store written", log)
        LB.ledger_add(stage + "_error", key, kind, cells=len(grid), note=why[:200], **base)
        return {"key": key, "ok": False, "cells": len(grid), "error": why}
    LB.write_unit(key, {**meta, "stage": stage, "period": PERIOD, "run_kw": kw, "hold_to": RM.HOLD}, grid, res, runs_dir)
    LB.ledger_add(stage, key, kind, cells=len(grid), trades=sum(len(r["trades"]) for r in res), note=meta.get("note", ""), **base)
    RM._log(f"{stage} {key}: {len(grid)} cells, {sum(len(r['trades']) for r in res)} trades, {res[0]['elapsed_s']} s "
            f"(wall {wall:.0f} s, {workers} workers)", log)
    return {"key": key, "ok": True, "cells": len(grid)}


def unit_meta(spec: dict, unit: dict) -> dict:
    fam, blocks = _blocks()
    lib, entry = fam.library(spec["family"]), blocks.BASES[spec["family"]]
    axis = lib.get("mirror") if lib.get("mirror") in spec["params"] else None
    f = unit["filter"]
    return {"family": spec["family"], "idea": spec["name"], "tf": unit["tf"], "rationale": spec["reason"],
            "filter": None if f is None else {"block": f[0], "side": f[1], "plain": blocks.plain(f)},
            "exits": unit["exits"], "sessions": spec["sessions"], "variants": spec["variants"], "fixed": spec["fixed"],
            "limits": spec["limits"], "both_sides_declared": entry[2], "notes": lib.get("notes") or entry[3],
            "complexity": lib["complexity"] + (1 if f else 0), "weak": lib["weak"], "penalty": lib["penalty"],
            "penalty_sess": lib.get("penalty_sess"), "second_look": lib.get("second_look"), "mirror": axis,
            "note": f"idea {spec['name']}" + (f": filter {f[0]} {f[1]}" if f else "")}


def plan(specs: list, ledger=None, runs_dir=None) -> dict:
    """The plan of one or more specs: rows per spec x market, the controls, and the fit under the cap."""
    rows, ctl, pend = [], {}, 0
    for sp in specs:
        us = spec_units(sp)
        for root in sp["markets"]:
            sub = [u for u in us if u["root"] == root]
            p = sum(u["cells"] for u in sub if not done(u["key"], "build", runs_dir, ledger))
            pend += p
            rows.append({"spec": sp["name"], "family": sp["family"], "root": root, "units": len(sub),
                         "base_units": sum(1 for u in sub if not u["filter"]), "filter_units": sum(1 for u in sub if u["filter"]),
                         "cells": sum(u["cells"] for u in sub), "pending_cells": p,
                         "instances": sum(len(cell_specs(u["grid"][0], sp["sessions"])) * u["cells"] for u in sub)})
        for c in spec_controls(sp):
            ctl.setdefault(c["key"], {**{k: c[k] for k in ("key", "kind", "root", "tf", "cells")},
                                      "done": done(c["key"], "null", runs_dir, ledger)})
    in_file = LB.ledger_used(path=ledger)["cells"]
    used = in_file + RM.PAPER_CELLS
    cells = sum(r["cells"] for r in rows)
    null_all, null_todo = sum(c["cells"] for c in ctl.values()), sum(c["cells"] for c in ctl.values() if not c["done"])
    return {"rows": rows, "controls": list(ctl.values()), "units": sum(r["units"] for r in rows),
            "base_units": sum(r["base_units"] for r in rows), "filter_units": sum(r["filter_units"] for r in rows),
            "candidate_cells": cells, "pending_cells": pend, "instances": sum(r["instances"] for r in rows),
            "null_cells": null_all, "null_cells_to_run": null_todo, "ledger_file_cells": in_file, "paper_cells": RM.PAPER_CELLS,
            "used": used, "cap": CAPS["cells"], "cells_after": used + pend, "fits": used + pend <= CAPS["cells"],
            "cap_left_after": CAPS["cells"] - used - pend}


def print_plan(p: dict) -> None:
    print(f"{'spec':22s} {'family':16s} {'mkt':3s} {'units':>5s} {'base':>4s} {'filter':>6s} {'cells':>7s} {'to run':>7s} {'instances':>9s}")
    for r in p["rows"]:
        print(f"{r['spec']:22s} {r['family']:16s} {r['root']:3s} {r['units']:5d} {r['base_units']:4d} {r['filter_units']:6d} "
              f"{r['cells']:7d} {r['pending_cells']:7d} {r['instances']:9d}")
    kinds = {}
    for c in p["controls"]:
        k = kinds.setdefault(c["kind"], [0, 0, 0])
        k[0] += 1
        k[1] += c["cells"]
        k[2] += 0 if c["done"] else 1
    print(f"TOTAL {p['units']} units ({p['base_units']} base + {p['filter_units']} filter): {p['candidate_cells']} CANDIDATE cells "
          f"({p['instances']} session instances), {p['pending_cells']} still to run")
    print("controls (NULL cells, not capped): " + "; ".join(f"{k} {n} stores / {cells} cells ({miss} to run)"
                                                             for k, (n, cells, miss) in sorted(kinds.items()))
          + f" -> {p['null_cells']} null cells, {p['null_cells_to_run']} to run")
    print(f"cap: {p['used']} candidate cells used (ledger.csv {p['ledger_file_cells']} + {p['paper_cells']} booked on paper) + "
          f"{p['pending_cells']} still to run = {p['cells_after']} of {p['cap']} -> {'FITS' if p['fits'] else 'DOES NOT FIT'} "
          f"({p['cap_left_after']} left)")


def build(spec: dict, workers: int | None = None, runs_dir=None, ledger=None, log=None, days=None, roots=None, tfs=None) -> list:
    """Run ONE spec over BUILD: the controls it still needs, then every unit (base, then filters). Restartable: a key with
    its store and its ledger row is skipped. Refused as a whole when its pending candidate cells do not fit under the cap.
    `days`, `runs_dir`, `ledger`, `roots`, `tfs` are for tests."""
    _, blocks = _blocks()
    log = LOG if log is None else log
    rd = RUNS if runs_dir is None else Path(runs_dir)
    us, cs = spec_units(spec, roots, tfs), spec_controls(spec, roots, tfs)
    todo = [u for u in us if not done(u["key"], "build", rd, ledger)]
    out = [{"key": u["key"], "skipped": True} for u in us if u not in todo]
    LB.ledger_check(cells=sum(u["cells"] for u in todo) + RM.PAPER_CELLS, path=ledger, caps=CAPS)
    for root in dict.fromkeys(u["root"] for u in us):
        miss = RM.tapes_ready(root)
        if miss:
            raise RuntimeError(f"{len(miss)} BUILD sessions of {root} have no tape yet (first {miss[0]}): run "
                               f"`python engine/l2sim.py tapes {root}` first")
    workers = RM.auto_workers(workers)
    for c in cs:                                         # the controls first: a unit is judged against them
        if done(c["key"], "null", rd, ledger):
            out.append({"key": c["key"], "skipped": True})
            continue
        if c["kind"] == "c1":
            out.append(RM.run_c1(c["root"], c["tf"], workers=workers, runs_dir=rd, ledger=ledger, log=log, days=days))
            continue
        S.wait_compute_window()
        t0 = time.monotonic()
        if c["kind"] == "c2":                           # the unit's own grid, the book rows of a random other session
            import score
            ckw = dict(getattr(blocks.WRAPPED[spec["family"]], "SCREEN_RUN", {}))
            res = run_grid(c["grid"], c["sessions"], c["root"], features=score.C2Features(blocks.BOOK_COLS, seed=c["seed"]),
                           workers=workers, days=days, kw=ckw)
            meta = {**unit_meta(spec, c["unit"]), "control": "c2", "seed": c["seed"]}
        else:
            ckw = {}
            res = run_grid(c["grid"], c["sessions"], c["root"], features=None, workers=workers, days=days)
            meta = {"family": "random" if c["kind"] == "c1x" else spec["family"], "tf": c["tf"], "control": c["kind"],
                    "p_entry": C1_P_ENTRY, "sessions": c["sessions"],
                    "note": "extended-menu random pool" if c["kind"] == "c1x" else f"idea {spec['name']}: range-stop random pool"}
        out.append(_record(c["key"], c["grid"], res, c["root"], meta, "null", ckw, rd, ledger, log, workers, time.monotonic() - t0))
    cls = blocks.WRAPPED[spec["family"]]
    kw = dict(getattr(cls, "SCREEN_RUN", {}))
    import levels as LV
    import zones as Z
    volume_ready, swing_ready = set(), set()
    prep = getattr(cls, "prepare", None)               # a family's own one-off cache (va_reclaim), as run_menus.run_unit
    if prep is not None and days is None:
        for root in dict.fromkeys(u["root"] for u in todo):
            S.wait_compute_window()
            RM._log(f"prepare {spec['family']} {root}: {prep(root, workers=workers)}", log)
    for u in todo:
        if u["filter"] and blocks.reads(u["filter"], ("volume", "rvol")) and u["root"] not in volume_ready and days is None:
            S.wait_compute_window()
            RM._log(f"prepare volume block {u['root']}: {blocks.build_minvol(u['root'], PERIOD, workers)}", log)
            volume_ready.add(u["root"])
        for rt in (x for x in Z.prep_roots(u["root"], spec["family"], u["filter"]) if x not in swing_ready):
            S.wait_compute_window()
            RM._log(f"prepare 5-minute bars {rt}: {LV.build_bars_cache(rt, PERIOD, workers)}", log)
            swing_ready.add(rt)
        S.wait_compute_window()
        t0 = time.monotonic()
        res = run_grid(u["grid"], spec["sessions"], u["root"], features=_features(u), workers=workers, days=days, kw=kw)
        out.append(_record(u["key"], u["grid"], res, u["root"], unit_meta(spec, u), "build", kw, rd, ledger, log, workers,
                           time.monotonic() - t0))
    return out


def status(specs: list, runs_dir=None, ledger=None) -> dict:
    us = [u for sp in specs for u in spec_units(sp)]
    pend = [u["key"] for u in us if not done(u["key"], "build", runs_dir, ledger)]
    ctl = {c["key"]: c for sp in specs for c in spec_controls(sp)}
    miss = [k for k in ctl if not done(k, "null", runs_dir, ledger)]
    return {"units": len(us), "done": len(us) - len(pend), "pending": pend, "controls": len(ctl), "controls_pending": miss}


def catalog(specs: list) -> list:
    """[(key, session)] of every candidate unit x session of the specs: the rows of a judge.py catalog CSV."""
    return [(u["key"], s) for sp in specs for u in spec_units(sp) for s in sp["sessions"]]


def smoke(spec: dict, root: str | None = None, tf: str | None = None, n_days: int = 5, workers: int = 2) -> dict:
    """BUG CHECK of a spec on <= 10 fixed BUILD days: every unit and control of ONE market x bar size, COUNTS ONLY (cells,
    session instances, trades, cells without a trade, dropped sessions, seconds). Nothing is stored or booked."""
    _, blocks = _blocks()
    root, tf = root or spec["markets"][0], str(tf or spec["bar_sizes"][0])
    have = {d.isoformat() for d in S.sessions(*S.period(PERIOD), root)}
    days = [d for d in RM.SMOKE_DAYS if d in have][:max(1, min(int(n_days), 10))]
    workers = max(1, min(int(workers), S.MAX_WORKERS))
    cls = blocks.WRAPPED[spec["family"]]
    kw = dict(getattr(cls, "SCREEN_RUN", {}))
    rows = []
    jobs = [(u["key"], u["grid"], spec["sessions"], _features(u), kw) for u in spec_units(spec, [root], [tf])]
    for c in spec_controls(spec, [root], [tf]):
        if c["kind"] == "c2":
            import score
            jobs.append((c["key"], c["grid"], c["sessions"], score.C2Features(blocks.BOOK_COLS, seed=c["seed"]), kw))
        elif c["kind"] != "c1":
            jobs.append((c["key"], c["grid"], c["sessions"], None, {}))
    for key, grid, sessions, feats, k in jobs:
        S.wait_compute_window()
        t0 = time.monotonic()
        res = run_grid(grid, sessions, root, features=feats, workers=workers, days=days, kw=k)
        errs = [n["reason"] for r in res for n in r["no_trade"] if n["reason"].startswith(S.ERROR_PREFIX)]
        rows.append({"key": key, "cells": len(grid), "instances": len(cell_specs(grid[0], sessions)) * len(grid),
                     "trades": sum(len(r["trades"]) for r in res), "cells_without_trades": sum(1 for r in res if not r["trades"]),
                     "skipped_by_error": sum(r["skipped_by_error"] for r in res), "first_error": errs[:1],
                     "sessions": res[0]["sessions"], "used": res[0]["used"], "seconds": round(time.monotonic() - t0, 1),
                     **RM.hold_checks(res, root)})
    ok = all(r["skipped_by_error"] == 0 and r["exit_after_day_flat"] == 0 and r["overlap_in_session"] == 0
             and r["entry_in_no_session"] == 0 for r in rows)
    return {"spec": spec["name"], "root": root, "tf": tf, "days": len(days), "workers": workers, "rows": rows, "ok": ok}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="run_idea.py", description="ideas as settings (see the module docstring)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "status", "catalog"):
        s = sub.add_parser(name)
        s.add_argument("specs", nargs="+")
        if name == "catalog":
            s.add_argument("--out", default="")
    b = sub.add_parser("build")
    b.add_argument("spec")
    b.add_argument("--workers", type=int, default=S.MAX_WORKERS)
    s = sub.add_parser("smoke")
    s.add_argument("spec")
    s.add_argument("--root", default=None)
    s.add_argument("--tf", default=None)
    s.add_argument("--days", type=int, default=5)
    s.add_argument("--workers", type=int, default=2)
    a = ap.parse_args(argv)
    try:
        if a.cmd in ("plan", "status", "catalog"):
            specs = [load_spec(p) for p in spec_paths(a.specs)]
            if a.cmd == "catalog":
                text = "key,sess\n" + "".join(f"{k},{s}\n" for k, s in catalog(specs))
                if a.out:
                    Path(a.out).write_text(text)
                    print(f"{len(catalog(specs))} units x sessions -> {a.out}")
                else:
                    sys.stdout.write(text)
                return 0
            if a.cmd == "status":
                print(json.dumps(status(specs), indent=1))
                return 0
            p = plan(specs)
            print_plan(p)
            return 0 if p["fits"] else 2
        spec = load_spec(spec_paths([a.spec])[0])
        if a.cmd == "smoke":
            o = smoke(spec, a.root and a.root.upper(), a.tf, a.days, a.workers)
            print(json.dumps(o, indent=1))
            return 0 if o["ok"] else 1
        out = build(spec, a.workers)
        print(json.dumps(out))
        return 1 if any(o.get("ok") is False for o in out) else 0
    except (SpecError, LB.CapExceeded, RM.RegistryBroken, RuntimeError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
