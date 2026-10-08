"""runner.py -- THE ONE STORE RUNNER of the blueprint build range (toolkit plan, step 4; BLUEPRINT.md phase 2).

For an idea spec in the format of run_idea.py it runs, on 2021-09-22 .. 2025-06-30 and on nothing later:
    <name>-<ROOT>-tf<tf>                    the idea's whole settings table: the values of its main setting x the 32 exit cells of
                                            the standard table, one instance per session of the spec (hold = day, 1 contract)
    <name>__<block>_<side>-<ROOT>-tf<tf>    the same table with ONE filter on: each filter of the spec is its own unit (line 2.7)
    c1-<ROOT>-tf<tf>                        THE CONTROL POOL of a market and bar size: random entries with the same 32 exit cells,
                                            10 seeds (control.json), all seven sessions. Written once; every later idea reuses it.
Stores go to runs_bp/ in the library's format (library.write_unit: run.json, cells.npz, table.csv), each covering the whole
range, each with its ledger row (stage bp_build = candidate cells, counted against the cap; null_bp = a pool, not capped).

ONE TAPE PASS per market and bar size: the pool (when it is missing), the unit and its filter units are replayed together,
so every session's tape is read once. The pass is cut into BLOCKS OF DAYS (compute.json): a 10-seed pool makes about 5,000
trades a day, and 45 months of them as the engine's rows would not fit beside the desk. Every block is packed at once
(library.pack) and the blocks are joined in day order -- every trade is flat by 15:58 of its own trade date, so that IS the
order of one long pass (checked block by block). The stores are the same for any block size and any number of workers.

A STORE IS NEVER WRITTEN TWICE. run.json keeps `inputs_hash`, the fingerprint of what was asked (every cell with its class
and inputs, its sessions, the range, the hold, the run options). A store with the same fingerprint is skipped: a rerun does
no work. A store with another fingerprint is REFUSED, not written over: a changed idea is a new round with its own name.
`code` keeps sha256/16 of the engine and family files that wrote the store (after a change to the code the earlier trade
list is reproduced exactly before a new run counts: line 1.6, checks.reproduced).

THE SEAL. Every engine call carries period="bp_build", the engine's own switch that raises from 2025-07-01 on, and no other
switch. Named days (a smoke run, the tests) are checked here first (seal); a store whose range is not inside the build days
is refused (guard), by this module and by every reader.
THE MACHINE. Workers: compute.json (8, or 4 while the desk trades), never more than l2sim.MAX_WORKERS, lowered when the
machine is busy (run_menus.auto_workers). No run STARTS in the engine's no-compute window (09:18-09:36 ET on weekdays). One
run at a time per store folder (a lock file).

    run_build(spec, workers, out_dir)       an idea: what is missing of its pools, units and filter units -> one row per store
    run_pools(roots, tfs, workers, out_dir) the control pools alone (bp.py pools)
    run_worse(spec, key, sess, ...)         the freeze: the WORSE-FILLS TABLE of one unit and session on the build range
                                            (<key>-<session>-worse; stage bp_build_worse: its cells count against the cap)

THE TEST DAYS (2025-07-01 on) have their own section at the end of this file, and ONE function that opens them: run_test,
for a frozen idea whose read is CLAIMED in the app's one-read log. Everything above it carries the build switch and the
build's seal, as before; test_range() reads file names and manifests only.
"""
from __future__ import annotations

import contextlib
import csv
import datetime as dt
import fcntl
import hashlib
import json
import shutil
import sys
import time
from functools import lru_cache
from pathlib import Path

import numpy as np

import judge as J
import l2sim as S
import library as LB
import run_idea as RI
import run_menus as RM

from . import W
from . import rules as R

PERIOD = S.ALLOW_BP                                 # 'bp_build': the range's name AND the engine's switch for it
RUNS = W / "runs_bp"                                # the stores of the blueprint ranges (the old stores stay where they are)
STAGE = {"unit": "bp_build", "pool": "null_bp"}     # ledger stages: a unit's cells are candidate cells, a pool's are not
WORSE = "bp_build_worse"                            # ... and so are the cells of a worse-fills table (the freeze runs it: run_worse)
LOCK = "runner.lock"                                # held while a run writes to a store folder (beside its runner.log)


def clock() -> dt.datetime:
    """Now, New York time (the tests set it)."""
    return dt.datetime.now(S.ET)


def default_workers(at=None) -> int:
    """The workers of a run that names none: compute.json -- fewer while the desk trades -- and never more than the engine's cap."""
    c, at = R.template("compute"), (at or clock()).astimezone(S.ET)
    a, b = (dt.time.fromisoformat(x) for x in c["desk_hours_et"])
    desk = at.weekday() < 5 and a <= at.time() < b
    return max(1, min(c["workers"]["desk_hours" if desk else "other"], S.MAX_WORKERS))


def may_start(at=None) -> None:
    """Refuse to START a heavy run inside the engine's no-compute window (l2sim.compute_window_end: the one definition; a run
    that is already going waits it out by itself)."""
    end = S.compute_window_end((at or clock()).astimezone(S.ET))
    if end is not None:
        a, b = R.template("compute")["no_start_et"]
        raise J.Refuse(f"nothing heavy starts {a}-{b} ET on weekdays (the desk's open): start it after {end:%H:%M} ET")


# ================================================================ the seal

def seal(days) -> list:
    """THE SEAL on named days -> their ISO dates in order. A day outside the build range is refused here, before anything is
    read: from the day after it on, the days belong to the out-of-sample test."""
    rg, test = R.template("ranges")["build"], R.template("ranges")["test"]["start"]
    try:
        out = sorted({S._date(d).isoformat() for d in days})
    except (TypeError, ValueError):
        raise J.Refuse(f"days {days!r}: ISO dates (2024-03-15) inside {rg['start']} .. {rg['end']}") from None
    bad = [d for d in out if not rg["start"] <= d <= rg["end"]]
    if bad or not out:
        raise J.Refuse(f"{bad[0] if bad else 'no day'}: a build reads {rg['start']} .. {rg['end']} only ({test} on is the out-of-sample test)")
    return out


def guard(meta: dict, where: str) -> dict:
    """THE SEAL on a store (its run.json): its whole range lies inside the build days, or it is refused -- not skipped, not
    read. A store that ends after them holds test days."""
    rg, r = R.template("ranges")["build"], meta.get("range") or {}
    a, b = str(r.get("start") or ""), str(r.get("end") or "")
    if not (a and rg["start"] <= a <= b <= rg["end"]):
        raise J.Refuse(f"store {where} covers {a or '?'} .. {b or '?'}: a build reads stores inside {rg['start']} .. {rg['end']} only")
    return meta


# ================================================================ what an idea asks for

def _blocks():
    RM.registry()
    from families import blocks
    return blocks


def checked(spec) -> dict:
    """An idea spec -- a dict, or the path of its JSON file (any file name: the idea's record names it) -> the spec as
    run_idea.check_spec fills it in. Refused: what run_idea refuses, and what the build range cannot run:
      exits other than the standard table (line 0.2; the control pool holds its 48 cells and no other). The card says
      "standard"; the engine is handed the blueprint's table (EXITS: the 32 cells of the old library, then the small targets)
      a Level 2 filter on another market than NQ (Level 2 exists for NQ only)
      a family with a `prepare` step of its own (va_reclaim: its value-area cache and its tape reads know the old build
      days only, so 2025 would raise inside a worker; the engine has to open it first)."""
    if isinstance(spec, (str, Path)):
        try:
            spec = json.loads(Path(spec).read_text())
        except (OSError, ValueError) as e:
            raise J.Refuse(f"spec file {spec}: {e}") from None
    try:
        done = isinstance(spec, dict) and "variants" in spec
        sp = spec if done else RI.check_spec(spec)   # (run_idea's own check is not run twice)
    except (RI.SpecError, RM.RegistryBroken) as e:
        raise J.Refuse(str(e)) from None
    blocks = _blocks()
    if (sp["exits"], sp["filter_exits"]) not in (("standard", "standard"), (EXITS, EXITS), (OPEN, OPEN)):
        raise J.Refuse(f"{sp['name']}: a build runs the standard exit table (BLUEPRINT.md line 0.2) or the owner's session-anchored table "
                       f"(exits {OPEN!r}), not exits {sp['exits']!r} / {sp['filter_exits']!r}")
    if (sp["exits"], sp["filter_exits"]) not in ((EXITS, EXITS), (OPEN, OPEN)):               # the blueprint's standard table (a copy: the caller's spec stays as it was)
        sp = {**sp, "exits": EXITS, "filter_exits": EXITS}
    l2 = [f"{b} {s}" for b, s in sp["filters"] if b in blocks.L2_BLOCKS]
    if l2 and any(m != "NQ" for m in sp["markets"]):
        raise J.Refuse(f"{sp['name']}: filter {l2[0]} reads Level 2, which exists for NQ only, not for {next(m for m in sp['markets'] if m != 'NQ')}")
    for b, _ in sp["filters"]:
        ok = blocks.BLOCK_MARKETS.get(b)
        if ok and any(m not in ok for m in sp["markets"]):
            raise J.Refuse(f"{sp['name']}: filter {b} compares {ok[0]} with {ok[1]}: it runs on {' and '.join(ok)} only, not on "
                           f"{next(m for m in sp['markets'] if m not in ok)}")
    if getattr(blocks.WRAPPED[sp["family"]], "prepare", None) is not None:
        raise J.Refuse(f"{sp['name']}: family {sp['family']} builds its own cache for the old build days only and reads tapes without the "
                       "build switch: it cannot run on the build range until the engine opens it")
    return sp


EXITS = "blueprint"                                 # the engine's name of the blueprint's exit table (families/blocks.menu_blueprint: 48 cells)
OPEN = "open"                                       # the owner's session-anchored table (families/blocks.menu_open: 60 cells; fvg_first_nq, 2026-10-06)
L2 = "bp_l2"                                        # a store's run option `features`: the Level-2 table of the build range (bpfeat.BpL2Features)


def _kw(family: str, filt=None) -> dict:
    """The run options of a store of `family`: the family's own (SCREEN_RUN) and, for a unit whose filter reads Level 2, the
    marker of the build range's Level-2 table (`_engine` turns it into the loader: a store's run.json stays plain JSON)."""
    blocks = _blocks()
    kw = dict(getattr(blocks.WRAPPED[family], "SCREEN_RUN", {}))
    if filt and filt[0] in blocks.L2_BLOCKS:
        kw["features"] = L2
    return kw


def _levels():
    RM.registry()
    import levels
    return levels


def bar_roots(root, family, filt) -> list:
    """The markets whose 5-minute bar cache a unit reads: the `liq` trigger and the level / swept filters (the swing level) read their own, SMT both."""
    RM.registry()
    import zones
    return zones.prep_roots(root, family, filt)


@lru_cache(maxsize=None)
def _sha(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def code(family=None) -> dict:
    """sha256/16 of the code that makes a store's trades: the engine and the random entries (a pool), + the blocks and the
    family's own module (a unit). Kept in run.json; the fingerprint of the INPUTS is another thing (fingerprint)."""
    files = ["l2sim.py", "l2ref.py"] + ([] if family is None else ["families/blocks.py", f"families/{RM.registry().MODULE_OF[family]}.py"])
    if family is not None:
        files += ["flowtab.py", "bpfeat.py", "levels.py", "zones.py"]          # the delta blocks, the Level-2 blocks, the liquidity levels and the zone blocks readers
    return {f: _sha(str(S.L / f)) for f in dict.fromkeys(files)}


def _seeded(fn, seeds, *a):
    """out/check2025/run_check.py `seeded`: run_menus.c1_grid with other seeds -- the function that made the 10-seed controls
    of 2025, not a copy of it."""
    p = str(W / "out" / "check2025")
    if p not in sys.path:
        sys.path.insert(0, p)
    import run_check
    return run_check.seeded(fn, seeds, *a)


def _part(key, kind, root, tf, grid, sessions, cells, meta, family=None, kw=None, filt=None) -> dict:
    """One store to be: its grid (`cells` = keep these exit cells only: a smoke run), the engine instances of every cell
    (run_idea.cell_specs: one per session the class trades), its run.json meta."""
    if cells is not None:
        grid = [c for c in grid if S.cell_id(c["exit"]) in set(cells)]
        if not grid:
            raise J.Refuse(f"{key}: none of the exit cells {sorted(set(cells))} is in the standard table")
    return {"key": key, "kind": kind, "root": root, "tf": str(tf), "grid": grid, "cells": len(grid), "sessions": list(sessions), "meta": meta,
            "family": family, "kw": dict(kw or {}), "filter": filt, "runs": [RI.cell_specs(c, list(sessions)) for c in grid]}


def pool_key(root: str, tf, exits: str = EXITS) -> str:
    """The store of a control pool: c1-NQ-tf5 for the standard table, c1o-NQ-tf5 for the session-anchored one (the same random
    entries, the other exit cells)."""
    return f"c1o-{root}-tf{tf}" if exits == OPEN else f"c1-{root}-tf{tf}"


def c1_grid(root: str, tf: str) -> list:
    """run_menus.c1_grid ON THE BLUEPRINT'S TABLE: the 32 standard cells of every seed (run_menus' own rows), then the
    small-target cells of every seed, with the pool's ids (s<seed>_<exit id>) and the cell's place in the table as `xi`.
    Read with run_menus.NULL_SEEDS as it is when called, so _seeded() hands it the 10 seeds like the function it extends."""
    import l2ref
    old, menu = RM.c1_grid(root, tf), _blocks().menu_blueprint(root)
    n = len(S.menu(root))
    return old + [{"id": f"s{sd}_{S.cell_id(x)}", "variant": {"seed": sd}, "exit": x, "vi": sd - 1, "xi": n + k,
                   "spec": (l2ref.Random, {"tf": str(tf), "sess": "all", "p_entry": RM.C1_P_ENTRY, "seed": sd, **x})}
                  for sd in RM.NULL_SEEDS for k, x in enumerate(menu[n:])]


def c1_grid_open(root: str, tf: str) -> list:
    """The control pool on the SESSION-ANCHORED table: the random entries of every seed (run_menus.NULL_SEEDS as it is when
    called, so _seeded() hands it the 10 seeds) x the 60 cells of blocks.menu_open, with the pool's ids (s<seed>_<exit id>)
    and the cell's place in the table as `xi`. The class is blocks.CONTROL_OPEN: l2ref.Random that takes the anchored stops."""
    blocks = _blocks()
    return [{"id": f"s{sd}_{S.cell_id(x)}", "variant": {"seed": sd}, "exit": x, "vi": sd - 1, "xi": k,
             "spec": (blocks.CONTROL_OPEN, {"tf": str(tf), "sess": "all", "p_entry": RM.C1_P_ENTRY, "seed": sd, **x})}
            for sd in RM.NULL_SEEDS for k, x in enumerate(blocks.menu_open(root))]


def pool_part(root: str, tf, cells=None, exits: str = EXITS) -> dict:
    """THE CONTROL POOL of a market and bar size: l2ref.Random (p_entry 0.5) x the seeds of control.json x the 48 exit cells
    of the blueprint's table (c1_grid, seeded) -- or, for an idea on the session-anchored table, its 60 cells (c1_grid_open),
    in the store c1o-<market>-tf<bar> -- every cell in all seven sessions."""
    import l2ref
    if root not in S.MENU_STOP_PTS or str(tf) not in l2ref.Random.SCREEN_TFS:
        raise J.Refuse(f"no control pool for market {root!r} and bar size {tf!r}: markets {sorted(S.MENU_STOP_PTS)}, bar sizes {l2ref.Random.SCREEN_TFS}")
    seeds = list(range(1, R.template("control")["seeds"] + 1))
    meta = {"family": "random", "tf": str(tf), "control": "c1", "p_entry": RM.C1_P_ENTRY, "seeds": seeds, "sessions": list(RM.DAY_PASSES),
            "note": f"{len(seeds)}-seed random-entry pool of the build range, all sessions: the control of every idea at this market and bar size"}
    grid = _seeded(c1_grid_open if exits == OPEN else c1_grid, seeds, root, str(tf))
    return _part(pool_key(root, tf, exits), "pool", root, tf, grid, RM.DAY_PASSES, cells, meta)


STAGES = ("all", "units", "pools")                  # what a build runs: everything · the idea's own tables only · the control pools only


def parts(spec: dict, cells=None, stage: str = "all") -> list:
    """Every store an idea needs, in run order: per market and bar size its control pool, its unit, its filter units.
    stage "units" leaves the control pools out (the owner, 2026-10-07: the 10-seed control is run only for an idea that passes
    every other line, never for one that has failed already); "pools" holds the control pools only."""
    if stage not in STAGES:
        raise J.Refuse(f"stage {stage!r}: one of {', '.join(STAGES)}")
    out = []
    for root in spec["markets"]:
        for tf in spec["bar_sizes"]:
            if stage != "units":
                out.append(pool_part(root, tf, cells, spec["exits"]))
            for u in ([] if stage == "pools" else RI.spec_units(spec, [root], [tf])):
                out.append(_part(u["key"], "filter" if u["filter"] else "unit", root, tf, u["grid"], spec["sessions"], cells, RI.unit_meta(spec, u),
                                 spec["family"], _kw(spec["family"], u["filter"]), u["filter"]))
    return out


def worse_kw(two_sided: bool) -> dict:
    """THE WORSE FILLS of line 4.5 as the run options of a store (costs.json `worse`, held to the engine's own STRESS by the
    rules test): 2 ticks of slippage and 250 ms of latency, + the 100 ms late cancel of the other side for a TWO-SIDED
    bracket (a family that rests entry orders on both sides: its `both_sides` in the registry)."""
    w = R.template("costs")["worse"]
    return {"slip_ticks": w["slip_ticks"], "latency_ms": w["latency_ms"], **({"oco_cancel_ms": w["oco_cancel_ms"]} if two_sided else {})}


def worse_words(kw: dict) -> str:
    """Those fills in words: `2 ticks + 250 ms + a 100 ms late cancel`."""
    return f"{kw['slip_ticks']:g} ticks + {kw['latency_ms']:g} ms" + (f" + a {kw['oco_cancel_ms']:g} ms late cancel" if kw.get("oco_cancel_ms") else "")


def _engine(kw: dict) -> dict:
    """A store's run options as the engine takes them: the late cancel is a field of its Costs, not a keyword of a run."""
    kw = dict(kw)
    if kw.get("features") == L2:
        import bpfeat
        kw["features"] = bpfeat.BpL2Features(_blocks().BOOK_COLS)
    oco = kw.pop("oco_cancel_ms", 0)
    return {**kw, "costs": S.Costs(oco_cancel_ms=int(oco))} if oco else kw


def _stage(p: dict) -> str:
    """The ledger stage of a store to be: its own when it names one (a worse-fills table), else the pool's or the unit's."""
    return p.get("stage") or STAGE["pool" if p["kind"] == "pool" else "unit"]


def worse_key(key: str, sess: str) -> str:
    return f"{key}-{sess}-worse"


def worse_part(spec: dict, key: str, sess: str, cells=None) -> dict:
    """THE WORSE-FILLS TABLE of ONE unit of an idea in ONE session, on the build range: the unit's own grid (`key`: the plain
    unit, or the unit with its one filter on), the session's instance only, run with worse_kw -> the store
    <key>-<session>-worse. Its cells are the unit's cells again: candidate cells of the ledger."""
    u = next((u for u in RI.spec_units(spec) if u["key"] == key), None)
    if u is None or sess not in spec["sessions"]:
        raise J.Refuse(f"{key} in session {sess}: not a table of {spec['name']}")
    blocks = _blocks()
    two = bool(blocks.BASES[spec["family"]][2])
    kw = {**_kw(spec["family"], u["filter"]), **worse_kw(two)}
    meta = {**RI.unit_meta(spec, u), "sessions": [sess], "sess_instance": sess, "worse_of": key, "worse": worse_kw(two),
            "note": f"idea {spec['name']}: {key} in session {sess} with worse fills ({worse_words(worse_kw(two))})"}
    return {**_part(worse_key(key, sess), "worse", u["root"], u["tf"], u["grid"], [sess], cells, meta, spec["family"], kw, u["filter"]), "stage": WORSE}


def run_worse(spec, key: str, sess: str, workers=None, out_dir=None, *, ledger=None, days=None, cells=None, progress=None, block=None, dry=False) -> list:
    """Run the worse-fills table of one unit and session on the build range when it is not stored (run_build's arguments
    and rows; kind 'worse'). The freeze picks the default variant among the variants that make money on build AND here."""
    sp = checked(spec)
    return _run([worse_part(sp, key, sess, cells)], workers, out_dir, ledger, days, cells, progress, block, dry, f"idea {sp['name']}, worse fills")


def fingerprint(part: dict, days=None, period: str = PERIOD, span=None) -> str:
    """The INPUTS of a store as 16 hex digits: every cell with its class, its inputs and the sessions it is run in; the
    range (and the named days of a smoke run); the hold; the run options. Two stores with one fingerprint were asked for
    the same trades. (period, span: a store of the test days names its switch and the dates its lock froze.)"""
    cells = [[c["id"], f"{c['spec'][0].__module__}.{c['spec'][0].__qualname__}", c["spec"][1], [x[1]["sess"] for x in one]]
             for c, one in zip(part["grid"], part["runs"])]
    doc = {"period": period, "days": days, "hold": RM.HOLD, "kw": part["kw"], "cells": cells, **({"span": list(span)} if span else {})}
    return hashlib.sha256(json.dumps(doc, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ================================================================ the run

def run_build(spec, workers=None, out_dir=None, *, ledger=None, days=None, cells=None, progress=None, block=None, dry=False, stage: str = "all") -> list:
    """Run what is missing of an idea on the build range: its control pools, its units and its filter units, ONE tape pass
    per market and bar size. -> one row per store, in run order:
      {key, kind 'pool' | 'unit' | 'filter', root, tf, cells, stage, path, inputs_hash, skipped, ok, trades, code_same}
    skipped = the store was there with the same inputs (no work); ok False = sessions were dropped by a strategy error: no
    store, an error row in the ledger. Refused before anything runs: module docstring.
    spec = ONE spec, or A LIST of specs that are one idea (an idea's record: one spec per market and bar size, each with
    the sessions its card names there; records.engine): checked, refused and run as a whole.
    workers None = default_workers(). out_dir None = runs_bp/, ledger None = ledger.csv. `days` + `cells` = A SMOKE RUN on
    named build days and a few exit cells (the tests): it needs its own out_dir and ledger. progress = a callable told what
    the run is doing. dry = every check, no run: the rows of what is there and what would run (ok None)."""
    sps = [checked(s) for s in (spec if isinstance(spec, list) else [spec])]
    todo = list({p["key"]: p for sp in sps for p in parts(sp, cells, stage)}.values())      # (a pool two specs share is one store)
    return _run(todo, workers, out_dir, ledger, days, cells, progress, block, dry, f"idea {sps[0]['name']}")


def cell_trades(spec, key: str, cell: str, sess: str, days=None, workers: int = 1) -> list:
    """THE FULL TRADE ROWS of ONE cell of a unit in ONE session, run again on the build range (or on the named days of a
    smoke run): a store keeps a trade's time, net and stop distance, not its prices, and a chart needs the prices. The
    same engine call as the pass that wrote the store, for one instance -- so it is the same trades (the caller holds them
    against the store). Nothing is written and nothing is booked: no new cell is tried. Refused: a key or a cell that is
    not the spec's; a strategy error."""
    sp = checked(spec)
    u = next((u for u in RI.spec_units(sp) if u["key"] == key), None)
    c = next((c for c in u["grid"] if c["id"] == cell), None) if u else None
    if c is None:
        raise J.Refuse(f"{key} cell {cell}: not a cell of {sp['name']}")
    days = seal([d.isoformat() for d in S.sessions(*S.period(PERIOD), u["root"], allow_holdout=PERIOD)] if days is None else days)
    res = RM.merge(S.run_many(RI.cell_specs(c, [sess]), period=PERIOD, days=days, root=u["root"], workers=max(1, min(int(workers), S.MAX_WORKERS)),
                              **_engine(_kw(sp["family"], u["filter"]))))
    if res["skipped_by_error"]:
        raise J.Refuse(f"{key} cell {cell}: sessions were dropped by a strategy error")
    return [t for t in res["trades"] if S.session_of(t["entry_ms"]) == sess]


def run_pools(roots, tfs, workers=None, out_dir=None, *, ledger=None, days=None, cells=None, progress=None, block=None, dry=False) -> list:
    """The control pools of the markets x bar sizes named, one tape pass each (run_build's arguments and rows)."""
    return _run([pool_part(r, tf, cells) for r in roots for tf in tfs], workers, out_dir, ledger, days, cells, progress, block, dry, "control pools")


def _where(out: Path, key: str) -> str:
    return f"{out.name}/{key}"


def _grown(p: dict, m: dict, days) -> bool:
    """THE EXIT TABLE GREW WITH THE LAW (BLUEPRINT.md version 1.1: the small targets): is the store on disk, run.json `m`,
    this very store with FEWER CELLS -- the same class, inputs, sessions, days and run options for every cell it holds, and
    nothing in it that is not asked for now? Then p["more"] = the cells still to run and p["stored"] = m: the pass runs
    those only and _record joins them to the store (its trades stay as they are). Anything else is another store."""
    have = [c["id"] for c in m.get("cells") or []]
    by = {c["id"]: i for i, c in enumerate(p["grid"])}
    if not have or len(have) >= len(p["grid"]) or any(c not in by for c in have):
        return False
    sub = {**p, "grid": [p["grid"][by[c]] for c in have], "runs": [p["runs"][by[c]] for c in have]}
    if fingerprint(sub, days) != m.get("inputs_hash"):
        return False
    held = set(have)
    p["stored"], p["more"] = m, [i for i, c in enumerate(p["grid"]) if c["id"] not in held]
    return True


def _stored(p: dict, out: Path, days=None) -> bool:
    """Is this store on disk with the same inputs? A store of other inputs, or one that is not inside the build days, is
    refused: it is never skipped as if it were the one asked for, and never written over. (A store of the same inputs that
    holds only part of the cells asked for is not "on disk": _grown.)"""
    f = out / p["key"] / "run.json"
    if not f.exists() or not (f.parent / "cells.npz").exists():
        return False
    m = guard(json.loads(f.read_text()), _where(out, p["key"]))
    if m.get("inputs_hash") != p["hash"] and _grown(p, m, days):
        return False                                # the table grew with the law: the store's cells stay, the missing ones are run (p["more"])
    if m.get("inputs_hash") != p["hash"]:
        raise J.Refuse(f"store {_where(out, p['key'])} was written from other inputs ({m.get('inputs_hash') or 'no fingerprint'}; asked now: {p['hash']}) "
                       "and is never written over: a changed idea is a new round with its own name (for example <name>_r2), and a control pool "
                       "changes only with the law")
    p["stored"] = m
    return True


@contextlib.contextmanager
def _alone(out: Path):
    """One run at a time per store folder (the machine has 8 workers for this project, not 8 per run)."""
    out.mkdir(parents=True, exist_ok=True)
    with open(out / LOCK, "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise J.Refuse(f"another run is writing to {out}: one heavy run at a time (bp.py job <id> shows a job)") from None
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


@contextlib.contextmanager
def _stores(out: Path, keys, wait=(), say=None, poll: float = 5.0):
    """Exclusive locks on the named stores of a folder, taken in sorted order (two runs cannot wait on each other), held to the
    end of the block. Runs of DIFFERENT ideas go side by side (the owner, 2026-10-07: several chats test several ideas at once);
    only a store two runs both want is one at a time. A store in `wait` (a control pool, which runs of every idea at a market
    and bar size share) is waited for: when the run that holds it is done it is on disk, and this one skips it. Any other store
    that is held is another run of the same idea: refused."""
    out.mkdir(parents=True, exist_ok=True)
    fhs, told = [], set()
    try:
        for key in sorted(dict.fromkeys(keys)):
            fh = open(out / f"{key}.lock", "w")
            fhs.append(fh)
            while True:
                try:
                    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if key not in wait:
                        raise J.Refuse(f"another run is writing {out.name}/{key}: one run of a store at a time (bp.py job <id> shows a job)") from None
                    if say is not None and key not in told:
                        told.add(key)
                        say(f"waiting for {key}: another run is writing it (when it is done this run reads it from disk)")
                    time.sleep(poll)
        yield
    finally:
        for fh in fhs:
            try:
                fcntl.flock(fh, fcntl.LOCK_UN)
            finally:
                fh.close()


@contextlib.contextmanager
def _prep(out: Path):
    """The shared cache files of a build (minute volume, 5-minute bars) are built by one run at a time: the others wait here."""
    with open(out / "prep.lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _row(p: dict, out: Path, **more) -> dict:
    return {"key": p["key"], "kind": p["kind"], "root": p["root"], "tf": p["tf"], "cells": p["cells"], "stage": _stage(p),
            "path": str(out / p["key"]), "inputs_hash": p["hash"], **more}


def _run(todo, workers, out_dir, ledger, days, cells, progress, block, dry, who) -> list:
    if (days is not None or cells is not None) and (days is None or out_dir is None or ledger is None):
        raise J.Refuse("a run on named days (or on some exit cells only) is a smoke run: it takes named days, its own store folder and its own "
                       "ledger file, and never writes into runs_bp/ or ledger.csv")
    if workers is not None and not 1 <= int(workers) <= S.MAX_WORKERS:
        raise J.Refuse(f"workers {workers}: 1 .. {S.MAX_WORKERS}")
    days = None if days is None else seal(days)
    out = RUNS if out_dir is None else Path(out_dir)
    for p in todo:
        p["hash"] = fingerprint(p, days)
        p["have"] = _stored(p, out, days)
    pend = [p for p in todo if not p["have"]]
    if pend:
        may_start()
        for root in dict.fromkeys(p["root"] for p in pend if p["root"] != "NQ" and days is None):
            miss = [d.isoformat() for d in S.sessions(*S.period(PERIOD), root, allow_holdout=PERIOD) if S.hb_tape_path(d, root) is None]
            if miss:
                raise J.Refuse(f"{len(miss)} sessions of {root} on the build range have no tape yet (first {miss[0]}): build them first (engine/l2sim.py build_tapes)")
        cand = sum(p["cells"] if p.get("more") is None else len(p["more"]) for p in pend if p["kind"] != "pool")
        try:
            if cand:
                LB.ledger_check(cells=cand + RM.PAPER_CELLS, path=ledger, caps=RI.CAPS)      # refused as a whole, before any pass
        except LB.CapExceeded as e:
            raise J.Refuse(f"the candidate-cell cap of the ledger (the stores' cells count against it, the pools' do not): {e}") from None
    rows = {p["key"]: _row(p, out, skipped=True, ok=True, trades=_trades(p["stored"]), code_same=p["stored"].get("code") == code(p["family"]))
            for p in todo if p["have"]}
    unbooked = [p for p in todo if p["have"] and not LB.ledger_has(p["key"], _stage(p), ledger)]
    if dry or not (pend or unbooked):               # nothing to write: no lock is taken (a reader never waits for a run)
        if dry and pend and out.exists():
            with _stores(out, [p["key"] for p in pend if p["kind"] != "pool"]):      # ... but a job is not started on a store another run is writing
                pass
        return [rows.get(p["key"]) or _row(p, out, skipped=False, ok=None, trades=None) for p in todo]
    out.mkdir(parents=True, exist_ok=True)
    say = _talk(out, progress)
    with _stores(out, [p["key"] for p in pend + unbooked], wait={p["key"] for p in pend + unbooked if p["kind"] == "pool"}, say=say):
        for p in [p for p in pend if _stored(p, out, days)]:            # a pool another run wrote while this one waited for it
            p["have"] = True
            rows[p["key"]] = _row(p, out, skipped=True, ok=True, trades=_trades(p["stored"]), code_same=p["stored"].get("code") == code(p["family"]))
        pend = [p for p in pend if not p["have"]]
        for p in unbooked:                          # a store without its ledger row (a run that died between the two): booked, not run again
            _book(p, len(p["stored"]["cells"]), _trades(p["stored"]), p["stored"].get("elapsed_s"), ledger, out)
        if pend:
            n = RM.auto_workers(default_workers() if workers is None else int(workers))
            with _prep(out):                                            # the caches below are shared files: one run builds them at a time
                for root in dict.fromkeys(p["root"] for p in pend if p["filter"] and p["filter"][0] in ("volume", "rvol") and days is None):
                    S.wait_compute_window()                                 # the volume block's minute-volume cache, opened for the build range
                    say(f"volume block {root}: {_blocks().build_minvol(root, PERIOD, n, allow_holdout=PERIOD)}")
                for root in dict.fromkeys(x for p in pend for x in bar_roots(p["root"], p["family"], p["filter"])):
                    S.wait_compute_window()                                 # the swing level's 5-minute bars, opened for the build range
                    say(f"swing bars {root}: {_levels().build_bars_cache(root, PERIOD, n, allow_holdout=PERIOD)}")
            groups: dict = {}
            for p in pend:
                groups.setdefault((p["root"], p["tf"], json.dumps(p["kw"], sort_keys=True)), []).append(p)
            for i, ((root, tf, _), group) in enumerate(groups.items(), 1):
                t0 = time.monotonic()
                head = f"{who}: pass {i} of {len(groups)}, {root} {tf}-minute bars ({' + '.join(p['key'] for p in group)}; {n} workers)"
                say(head)
                res = _pass(group, root, days, n, group[0]["kw"], block, lambda msg, head=head: say(f"{head}: {msg}"))
                for p, r in zip(group, res):
                    rows[p["key"]] = _record(p, r, days, out, ledger, say, n, time.monotonic() - t0)
    return [rows[p["key"]] for p in todo]


def _trades(meta: dict) -> int:
    return sum(int(c["trades"]) for c in meta["cells"])


def _talk(out: Path, progress):
    """What the run is doing: to the caller (a job keeps it as its progress), to stderr and to <store folder>/runner.log.
    Never to stdout: a command prints ONE JSON object there."""
    def say(msg: str) -> None:
        line = f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} {msg}"
        print(line, file=sys.stderr, flush=True)
        with (out / "runner.log").open("a") as fh:
            fh.write(line + "\n")
        if progress is not None:
            progress(msg)
    return say


class _Packed:
    """Stands in for a cell's trade list when its store is written: the trades are packed already (library.pack, block by
    block)."""

    def __init__(self, packs: list):
        self.x = {k: (np.concatenate([p[k] for p in packs]) if packs else np.zeros(0, LB.DTYPES[k])) for k in LB.FIELDS}

    def __len__(self) -> int:
        return len(self.x["net"])


class _Cell:
    """One cell of a tape pass over its day blocks: its trades packed block by block, its counts added up."""
    SUMS = ("sessions", "used", "skipped_by_error", "unrealistic_winners", "both_sides_sessions", "elapsed_s")
    LISTS = ("skipped", "no_trade", "eve_skipped")

    def __init__(self, first=None, last=None):
        self.packs, self.meta, self.last = [], None, -1
        self.n, self.rows = dict.fromkeys(self.SUMS, 0), {k: [] for k in self.LISTS}
        self.span = (first, S.BP_BUILD[1].toordinal() if last is None else last)      # the trade dates (ordinals) the pass may hand back: to the build's end, unless told

    def add(self, r: dict) -> None:
        t = r["trades"]
        if t:
            if t[0]["exit_ms"] < self.last:            # r's trades are in (exit, entry) order: its first one ends first
                raise RuntimeError("a trade of an earlier day block ends after one of a later block: the blocks cannot be joined in order")
            self.last = t[-1]["exit_ms"]
            self.packs.append(LB.pack(t))
        self.meta = self.meta or r["meta"]
        for k in self.SUMS:
            self.n[k] += r.get(k) or 0
        for k in self.LISTS:
            self.rows[k] += r.get(k) or []

    def result(self) -> dict:
        t, (first, last) = _Packed(self.packs), self.span
        if len(t) and (int(t.x["date"].max()) > last or (first is not None and int(t.x["date"].min()) < first)):
            raise RuntimeError("the engine handed back a trade dated outside the range of the pass: nothing is stored")
        return {**self.n, **self.rows, "elapsed_s": round(self.n["elapsed_s"], 2), "meta": self.meta, "trades": t}


def _pass(parts_: list, root: str, days, workers: int, kw: dict, block, say) -> list:
    """ONE TAPE PASS for the stores of one market and bar size: every instance of every cell of every part, block of days
    after block of days (module docstring). -> per part, one merged result per cell (run_menus.merge) with its trades
    packed. Instances that carry state from day to day would not stand a cut: such a pass is one block."""
    specs, cut = [], [0]
    for p in parts_:
        for one in (p["runs"] if p.get("more") is None else [p["runs"][i] for i in p["more"]]):      # (a store that grew: its missing cells only)
            specs += one
            cut.append(len(specs))
    days = seal([d.isoformat() for d in S.sessions(*S.period(PERIOD), root, allow_holdout=PERIOD)] if days is None else days)     # the law's range, again
    step = max(1, int(block or R.template("compute")["block_days"])) if all(getattr(c, "session_independent", False) for c, _ in specs) else len(days)
    acc = [_Cell() for _ in cut[1:]]
    for k in range(0, len(days), step):
        say(f"days {k + 1}-{min(k + step, len(days))} of {len(days)} ({len(specs)} instances)")
        res = S.run_many(specs, period=PERIOD, days=days[k:k + step], root=root, workers=workers, **_engine(kw))
        for a, i, j in zip(acc, cut, cut[1:]):
            a.add(RM.merge(res[i:j]))
    out, k = [], 0
    for p in parts_:
        n = p["cells"] if p.get("more") is None else len(p["more"])
        out.append([a.result() for a in acc[k:k + n]])
        k += n
    return out


def _write(key: str, meta: dict, grid: list, res: list, out: Path) -> Path:
    """library.write_unit for trades that are packed already: its `pack` is swapped for the call (as run_check.seeded swaps
    the seeds), so the store is written by the library's own code, in the library's own format."""
    keep = LB.pack
    LB.pack = lambda t: t.x if isinstance(t, _Packed) else keep(t)
    try:
        return LB.write_unit(key, meta, grid, res, out)
    finally:
        LB.pack = keep


def _book(p: dict, cells: int, trades: int, elapsed, ledger, out: Path, stage=None, note=None, period: str = PERIOD) -> None:
    """The store's ledger row, once (the way run_idea books a store: a pool is a null grid, a unit a candidate grid)."""
    stage, m = stage or _stage(p), p["meta"]
    if not stage.endswith("_error") and LB.ledger_has(p["key"], stage, ledger):
        return
    seeds = m.get("seeds")
    LB.ledger_add(stage, p["key"], "null" if p["kind"] == "pool" else "grid", cells=cells, trades=trades, family=m.get("family", ""), root=p["root"],
                  tf=p["tf"], period=period, control=m.get("control", ""), seed=f"{seeds[0]}-{seeds[-1]}" if seeds else "", elapsed_s=elapsed,
                  note=note or f"{_where(out, p['key'])}: {m.get('note') or ''}"[:200], path=ledger, caps=RI.CAPS)


def _record(p: dict, res: list, days, out: Path, ledger, say, workers: int, wall: float) -> dict:
    """A part's results -> its store and its ledger row. A pass that dropped a session by a strategy error writes NO store:
    an error row (a unit's cells still count), and the key stays to be run once the family is fixed."""
    n = sum(len(r["trades"]) for r in res)
    if sum(r["skipped_by_error"] for r in res):
        why = next(x["reason"] for r in res for x in r["no_trade"] if x["reason"].startswith(S.ERROR_PREFIX))
        say(f"ERROR {p['key']}: sessions dropped by a strategy error ({why}); no store written")
        _book(p, p["cells"], n, res[0]["elapsed_s"], ledger, out, _stage(p) + "_error", why[:200])
        return _row(p, out, skipped=False, ok=False, trades=n, error=why)
    stage = _stage(p)
    if p.get("more") is not None:                   # the table grew with the law: the store keeps its cells and gets the new ones
        was = _join(p, res, out)
        _book({**p, "key": p["key"]}, len(p["more"]), n, res[0]["elapsed_s"], ledger, out, f"{stage}_more",
              f"{_where(out, p['key'])}: + {len(p['more'])} cells of the grown exit table (BLUEPRINT.md version 1.1); it held {was}")
        say(f"{stage} {p['key']}: + {len(p['more'])} cells ({was} -> {p['cells']}), {n:,} trades more, {res[0]['elapsed_s']} s of tape (wall {wall:.0f} s, {workers} workers)")
        return _row(p, out, skipped=False, ok=True, trades=n, code_same=p["stored"].get("code") == code(p["family"]), grown=len(p["more"]))
    _write(p["key"], {**p["meta"], "stage": stage, "period": PERIOD, "run_kw": p["kw"], "hold_to": RM.HOLD, "inputs_hash": p["hash"],
                      "code": code(p["family"]), **({"days": days} if days else {})}, p["grid"], res, out)
    _book(p, p["cells"], n, res[0]["elapsed_s"], ledger, out)
    say(f"{stage} {p['key']}: {p['cells']} cells, {n:,} trades, {res[0]['elapsed_s']} s of tape (wall {wall:.0f} s, {workers} workers)")
    return _row(p, out, skipped=False, ok=True, trades=n, code_same=True)


def _join(p: dict, res: list, out: Path) -> int:
    """A STORE WHOSE TABLE GREW (_grown): its cells and trades stay byte for byte, the cells just run are put behind them
    (library.write_unit's format: cells.npz = `off` + one flat array per field, run.json `cells`, table.csv), and run.json
    takes the fingerprint of the whole table and says what was added and when. Written beside the store and moved over
    it in one step, as the library writes a store. -> how many cells it held before."""
    key, m = p["key"], p["stored"]
    u = LB.load_unit(key, out)
    if [c["id"] for c in u["meta"]["cells"]] != [c["id"] for c in m["cells"]] or len(u["off"]) != len(m["cells"]) + 1:
        raise RuntimeError(f"{_where(out, key)} changed on disk during the pass: nothing is joined")
    new = [p["grid"][i] for i in p["more"]]
    packs = [r["trades"].x for r in res]
    off = np.concatenate([u["off"], int(u["off"][-1]) + np.cumsum([len(x["net"]) for x in packs], dtype=np.int64)])
    arrays = {k: np.concatenate([u[k], *[x[k] for x in packs]]).astype(LB.DTYPES[k], copy=False) for k in LB.FIELDS}
    cells = [{"id": c["id"], "vi": c["vi"], "xi": c["xi"], "variant": c["variant"], "exit": c["exit"], "inputs": r["meta"]["inputs"], "trades": len(r["trades"]),
              "both_sides_sessions": r.get("both_sides_sessions"), "skipped_by_error": r.get("skipped_by_error", 0),
              "unrealistic_winners": r.get("unrealistic_winners", 0)} for c, r in zip(new, res)]
    doc = {**m, "cells": [*m["cells"], *cells], "inputs_hash": p["hash"], "exits": EXITS if "exits" in m else m.get("exits"),
           "grown": [*(m.get("grown") or []), {"utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "cells": len(cells), "from": len(m["cells"]),
                                                 "was": m.get("inputs_hash"), "code": code(p["family"]), "elapsed_s": res[0]["elapsed_s"] if res else 0.0}]}
    if "exits" not in m:
        doc.pop("exits")
    d = out / key
    tmp = d.with_name(d.name + ".tmp")
    tmp.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(tmp / "cells.npz", off=off, **arrays)
    (tmp / "run.json").write_text(json.dumps(doc, indent=1, default=str))
    rows = LB.unit_table({"meta": doc, "off": off, **arrays})
    with (tmp / "table.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0]) if rows else ["cell"])
        w.writeheader()
        w.writerows(rows)
    shutil.rmtree(d)
    tmp.rename(d)
    return len(m["cells"])


# ================================================================ the test days (BLUEPRINT.md phase 4): what a lock freezes, and THE ONE READ
#
# The out-of-sample test reads 2025-07-01 .. a market's last complete session ONCE, for a frozen idea. What is run on those
# days, for the idea's home table and nothing else (lines 4.1-4.9 read no other table):
#     <unit key>-<session>-test          the LOCKED variants (the lock's variant list), the home session's instance
#     <unit key>-<session>-test-worse    the same cells with worse fills (line 4.5)
#     <store>__c1-<ROOT>-tf<tf>-<session>-test    the idea's own random-entry pool: 10 seeds x the 32 exit cells, that session
# into runs_bp_test/ (TESTS). Each store covers the frozen range, names the read it belongs to (`read`: the idea, its
# version, its lock) and the session days that were replayed (`calendar`): a reader needs no engine call to know them.
# run_test is THE ONLY CALLER of the engine's switch for those days, and it runs nothing unless the read is in the app's
# one-read log as CLAIMED (homebase/ideastore.py: the read is logged before the pass, as in out/exam2026/run_exam.py).

TESTS = W / "runs_bp_test"


def test_keys(key: str, store: str, root: str, tf, sess: str) -> dict:
    """The store keys of an idea's test: its locked variants, the same with worse fills, its own random-entry pool."""
    return {"table": f"{key}-{sess}-test", "worse": f"{key}-{sess}-test-worse", "pool": f"{store}__c1-{root}-tf{tf}-{sess}-test"}


def _front(root: str, start: dt.date) -> dict:
    """{session date: is it complete} for every archived weekday session of a market from `start` on, by the manifest of
    its FRONT contract (the one that counts the most ticks: the tester's rule). Manifests only: no tick is read."""
    best: dict = {}
    for ydir in sorted(p for p in (S.ARCHIVE / root).glob("*") if p.is_dir() and p.name.isdigit() and int(p.name) >= start.year):
        for f in ydir.glob("*.json"):
            try:
                d = dt.date.fromisoformat(f.name[:10])
                m = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            if d >= start and d.weekday() < 5 and isinstance(m, dict) and (d not in best or int(m.get("ticks") or 0) > best[d][0]):
                best[d] = (int(m.get("ticks") or 0), m.get("complete") is True)
    return {d: ok for d, (_, ok) in best.items()}


def test_range(root: str, cap=None) -> dict:
    """THE TEST RANGE OF A MARKET as a lock freezes it: the first test day (ranges.json) .. the market's LAST COMPLETE
    SESSION ON DISK = the last session of the unbroken run of complete sessions from that day on. A session is complete
    when the archive says so (the `complete` flag of its front-contract manifest) and -- NQ, which the engine replays from
    its ofb_tick tapes -- its tape is there. Read off file names and manifests: no tape and no price is opened, and the
    engine's seal is not asked. -> {start, end, sessions, parts [{name, start, end, sessions}], no_tape (sessions of the
    range that have no tape yet: ES and GC tapes are built from the archive, by the read itself), stops (the first session
    that is not complete, or None)}. Refused: no complete session, or a part of the test without one (line 4.1 reads both)."""
    rg = R.template("ranges")["test"]
    start = S._date(rg["start"])
    done = _front(root, start)
    cap = None if cap is None else S._date(cap)       # the last date a FILTER's data reaches (delta blocks: the flow file's end)
    tapes = None
    if root == "NQ":
        tapes = set()
        for f in (S.TAPE_DIR / root).glob("*/*/*.parquet"):
            try:
                tapes.add(dt.date.fromisoformat(f.name[:10]))
            except ValueError:
                continue
    good, stops = [], None
    for d in sorted(set(done) | {x for x in (tapes or ()) if x >= start and x.weekday() < 5}):
        if not (done.get(d) and (tapes is None or d in tapes)):
            stops = d
            break
        good.append(d)
    if not good:
        raise J.Refuse(f"{root} has no complete session on disk from {start} on" + (f" (the first one, {stops}, is not complete)" if stops else "")
                       + ": there is no test range to freeze")
    cut = [d for d in good if cap is not None and d > cap]
    good = [d for d in good if cap is None or d <= cap]
    if not good:
        raise J.Refuse(f"{root}: the data of the idea's filter ends {cap}, before the first test day {start}: there is no test range to freeze")
    end, parts = good[-1], []
    for p in rg["parts"]:
        a, b = S._date(p["start"]), (end if p["end"] == "latest" else min(end, S._date(p["end"])))
        parts.append({"name": p["name"], "start": a.isoformat(), "end": b.isoformat(), "sessions": sum(a <= d <= b for d in good)})
    empty = [p["name"] for p in parts if not p["sessions"]]
    if empty:
        raise J.Refuse(f"the complete sessions of {root} on disk end {end}: {empty[0]} would have no session, and line 4.1 reads both parts of the test"
                       + (f" (the first session that is not complete: {stops})" if stops else ""))
    return {"start": start.isoformat(), "end": end.isoformat(), "sessions": len(good), "parts": parts,
            "no_tape": 0 if root == "NQ" else sum(S.hb_tape_path(d, root) is None for d in good), "stops": None if stops is None else stops.isoformat(),
            **({"capped_by_filter": {"data_ends": cap.isoformat(), "sessions_left_out": len(cut)}} if cut else {})}


def guard_test(meta: dict, where: str, start: str, end: str, lock=None) -> dict:
    """THE SEAL on a store of the test days (its run.json): it was written by the engine's test switch (the period it says
    is the one the engine put on its range, and not the build's), it covers exactly the frozen range, and -- when `lock` is
    given -- it belongs to the read of that lock. Anything else is refused: not skipped, not read."""
    r, read = meta.get("range") or {}, meta.get("read") or {}
    if not (meta.get("period") and meta.get("period") == r.get("period") != PERIOD and (r.get("start"), r.get("end")) == (start, end)):
        raise J.Refuse(f"store {where} covers {r.get('start') or '?'} .. {r.get('end') or '?'} (period {meta.get('period')!r}): not a store of the test days "
                       f"{start} .. {end}")
    if lock is not None and read.get("lock") != lock:
        raise J.Refuse(f"store {where} belongs to the read of another lock ({read.get('lock') or 'none'}; this one: {lock}): it is not read")
    return meta


def run_test(name: str, read: dict, spec, key: str, sess: str, variants: list, store: str, end: str, workers=None, out_dir=None, *, ideas=None,
             ledger=None, days=None, block=None, progress=None, dry: bool = False, keep=()) -> dict:
    """THE ONE READ OF THE TEST DAYS for a frozen idea: its locked variants, the same with worse fills and its own 10-seed
    random-entry pool, on the session days of the frozen range (the first test day .. `end`), home session only.
      name, read      the idea and its read {version, lock}: the line the app's one-read log must hold as CLAIMED
      spec, key, sess the engine's settings of the home's store (run_idea's format), the unit's store key (with its one
                      filter on, when the rule has one) and the home session
      variants, store the lock's variant list (cells of that unit) and the store name of the frozen round
      end             the frozen last session of the market (lock.json test_range)
      days            TEST OF THE PLUMBING ONLY: named days of the range, into an out_dir and a ledger of their own
      keep            cells whose FULL trade rows are handed back (a store keeps no prices; the default variant is shown)
      dry             every refusal that needs no read, and nothing else: no claim is asked for, nothing is opened
    -> {"stores": [one row a store, as run_build's], "calendar": [the session days replayed], "trades": {cell: [rows]}}.
    THE ORDER: every refusal first; then the claim is looked up (no claimed read = refused, nothing is opened); only then
    the engine's switch is used -- for the session list, for a missing ES / GC tape (built from the archive, the tester's
    own code), for the passes. A store that is on disk is never run again. A strategy error in a pass writes no store and
    ends the read: it stays on file."""
    sw = getattr(S, "ALLOW_BT", None)               # THE SWITCH OF THE TEST DAYS: named here and nowhere else in this project
    if sw is None:
        raise J.Refuse("the engine has no switch for the test days (engine/l2sim.py): the out-of-sample test cannot run on this checkout")
    sp = checked(spec)
    u = next((x for x in RI.spec_units(sp) if x["key"] == key), None)
    if u is None or sess not in sp["sessions"]:
        raise J.Refuse(f"{key} in session {sess}: not a table of {sp['name']}")
    if u["filter"] and u["filter"][0] in _blocks().L2_BLOCKS:
        raise J.Refuse(f"{key}: a Level 2 filter cannot be tested yet: the vendor's Level 2 history ends 2026-07-08 and the test days' table is not built")
    root, tf, first = u["root"], u["tf"], R.template("ranges")["test"]["start"]
    try:
        a, b = S._date(first), S._date(end)
        named = None if days is None else sorted({S._date(d).isoformat() for d in days})
    except (TypeError, ValueError):
        raise J.Refuse(f"the test range {first} .. {end!r} (days {days!r}): ISO dates") from None
    off = [end] if b < a else ["no day"] if named == [] else [d for d in named or [] if not a.isoformat() <= d <= b.isoformat()]
    if off:
        raise J.Refuse(f"{off[0]}: the test of {name} reads {a} .. {end} only (the range its lock froze)")
    if named is not None and (out_dir is None or ledger is None):
        raise J.Refuse("a read of named test days is a test of the plumbing: it takes its own store folder and its own ledger file, and never writes "
                       f"into {TESTS.name}/ or ledger.csv")
    if workers is not None and not 1 <= int(workers) <= S.MAX_WORKERS:
        raise J.Refuse(f"workers {workers}: 1 .. {S.MAX_WORKERS}")
    want = list(dict.fromkeys(variants))
    grid = [c for c in u["grid"] if c["id"] in set(want)]
    if not want or len(grid) != len(want):
        raise J.Refuse(f"{key}: " + (f"{next(c for c in want if c not in {x['id'] for x in grid})} is not a cell of the unit" if want else "no variant to run")
                       + ": the lock's variant list names the cells of the read")
    blocks, K = _blocks(), test_keys(key, store, root, tf, sess)
    base, worse = dict(getattr(blocks.WRAPPED[sp["family"]], "SCREEN_RUN", {})), worse_kw(bool(blocks.BASES[sp["family"]][2]))
    seeds, um = list(range(1, R.template("control")["seeds"] + 1)), {**RI.unit_meta(sp, u), "sessions": [sess], "sess_instance": sess}
    stage = {"table": sw, "worse": f"{sw}_worse", "pool": f"null_{sw}"}      # the ledger stages of the read
    todo = [{**_part(K["pool"], "pool", root, tf, _seeded(c1_grid, seeds, root, str(tf)), [sess], None,
                     {"family": "random", "tf": str(tf), "control": "c1", "p_entry": RM.C1_P_ENTRY, "seeds": seeds, "sessions": [sess], "sess_instance": sess,
                      "idea": name, "note": f"idea {name}: its {len(seeds)}-seed random-entry pool of the test days, session {sess}"}), "stage": stage["pool"]},
            {**_part(K["table"], "filter" if u["filter"] else "unit", root, tf, grid, [sess], None,
                     {**um, "note": f"idea {name}: the locked variants on the test days, session {sess}"}, sp["family"], base, u["filter"]), "stage": stage["table"]},
            {**_part(K["worse"], "worse", root, tf, grid, [sess], None,
                     {**um, "worse_of": K["table"], "worse": worse, "note": f"idea {name}: the locked variants on the test days with worse fills "
                                                                            f"({worse_words(worse)}), session {sess}"},
                     sp["family"], {**base, **worse}, u["filter"]), "stage": stage["worse"]}]
    out, span = (TESTS if out_dir is None else Path(out_dir)), (a.isoformat(), b.isoformat())
    for p in todo:
        p["hash"], f = fingerprint(p, named, sw, span), out / p["key"] / "run.json"
        p["have"] = f.exists() and (f.parent / "cells.npz").exists()
        if p["have"]:
            p["stored"] = guard_test(json.loads(f.read_text()), _where(out, p["key"]), *span, read.get("lock"))
            if p["stored"].get("inputs_hash") != p["hash"]:
                raise J.Refuse(f"store {_where(out, p['key'])} was written from other inputs ({p['stored'].get('inputs_hash') or 'no fingerprint'}; asked "
                               f"now: {p['hash']}) and is never written over")
    pend = [p for p in todo if not p["have"]]
    if pend:
        may_start()
        try:
            LB.ledger_check(cells=sum(p["cells"] for p in pend if p["kind"] != "pool") + RM.PAPER_CELLS, path=ledger, caps=RI.CAPS)
        except LB.CapExceeded as e:
            raise J.Refuse(f"the candidate-cell cap of the ledger (the cells of a test count against it, its pool's do not): {e}") from None
    rows = {p["key"]: _row(p, out, skipped=True, ok=True, trades=_trades(p["stored"]), code_same=p["stored"].get("code") == code(p["family"]))
            for p in todo if p["have"]}
    if dry:
        if pend and out.exists():
            with _alone(out):                       # a read is not claimed into a folder another run is writing to
                pass
        return {"stores": [rows.get(p["key"]) or _row(p, out, skipped=False, ok=None, trades=None) for p in todo], "calendar": None, "trades": {}}
    # ---- THE CLAIM: nothing of the test days is opened unless the read is in the one-read log, claimed and not yet judged
    from . import api                               # (api imports this module: looked up when the read is run)
    line = api.ideastore().read_on_file(name, root=ideas)
    if not (line and line.get("state") == "claimed" and (line.get("version"), line.get("lock")) == (read.get("version"), read.get("lock"))):
        raise J.Refuse(f"no claimed read of the test days is on file for {name} (lock {read.get('lock')}): the read is written to the log BEFORE the pass "
                       f"(bp.py test {name} --confirm), and a read that was judged is over")
    kept: dict = {c: [] for c in keep}
    with _alone(out):
        say = _talk(out, progress)
        n = RM.auto_workers(default_workers() if workers is None else int(workers))
        if root != "NQ" and pend:                   # a session the tester never cached: its tape, from the archive (file for file the tester's)
            S.wait_compute_window()
            for x, y in ([(a, b)] if named is None else [(d, d) for d in named]):
                say(f"tapes of {root} {x} .. {y}: {S.build_tapes(root, x, y, workers=n, allow_holdout=sw)}")
        cal = [d.isoformat() for d in S.sessions(a, b, root, allow_holdout=sw)]
        run_days = cal if named is None else named
        if [d for d in run_days if d not in cal]:
            raise J.Refuse(f"{[d for d in run_days if d not in cal][0]} is no session of {root} in {span[0]} .. {span[1]}")
        more = {"calendar": run_days, "read": {"name": name, "version": read.get("version"), "lock": read.get("lock"), "claimed_utc": line.get("utc")},
                **({"days": named} if named else {})}
        for p in todo:                              # a store without its ledger row (a run that died between the two): booked, not run again
            if p["have"]:
                _book(p, len(p["stored"]["cells"]), _trades(p["stored"]), p["stored"].get("elapsed_s"), ledger, out, period=sw)
        if pend and u["filter"] and u["filter"][0] in ("volume", "rvol"):
            S.wait_compute_window()                 # the volume block's minute-volume cache, opened for the frozen range
            say(f"volume block {root}: {blocks.build_minvol(root, (a, b), n, allow_holdout=sw)}")
        if pend:
            for rt in bar_roots(root, sp["family"], u["filter"]):
                S.wait_compute_window()             # the 5-minute bars (swing level, SMT), opened for the frozen range
                say(f"swing bars {rt}: {_levels().build_bars_cache(rt, (a, b), n, allow_holdout=sw)}")
        groups: dict = {}
        for p in pend:
            groups.setdefault(json.dumps(p["kw"], sort_keys=True), []).append(p)
        for i, group in enumerate(groups.values(), 1):
            t0, specs, cut, who = time.monotonic(), [], [0], []
            for p in group:
                for c, one in zip(p["grid"], p["runs"]):
                    specs += one
                    cut.append(len(specs))
                    who.append((p["key"], c["id"]))
            step = max(1, int(block or R.template("compute")["block_days"])) if all(getattr(c, "session_independent", False) for c, _ in specs) else len(run_days)
            acc = [_Cell(a.toordinal(), b.toordinal()) for _ in who]
            head = f"test of {name}: pass {i} of {len(groups)}, {root} {tf}-minute bars ({' + '.join(p['key'] for p in group)}; {n} workers)"
            say(head)
            for k in range(0, len(run_days), step):
                say(f"{head}: days {k + 1}-{min(k + step, len(run_days))} of {len(run_days)} ({len(specs)} instances)")
                res = S.run_many(specs, a, b, days=run_days[k:k + step], root=root, workers=n, allow_holdout=sw, **_engine(group[0]["kw"]))
                for cell, (pk, cid), x, y in zip(acc, who, cut, cut[1:]):
                    r = RM.merge(res[x:y])
                    if pk == K["table"] and cid in kept:
                        kept[cid] += [t for t in r["trades"] if S.session_of(t["entry_ms"]) == sess]
                    cell.add(r)
            k = 0
            for p in group:
                res, k = [c.result() for c in acc[k:k + p["cells"]]], k + p["cells"]
                cnt = sum(len(r["trades"]) for r in res)
                if sum(r["skipped_by_error"] for r in res):
                    why = next(x["reason"] for r in res for x in r["no_trade"] if x["reason"].startswith(S.ERROR_PREFIX))
                    _book(p, p["cells"], cnt, res[0]["elapsed_s"], ledger, out, p["stage"] + "_error", why[:200], period=sw)
                    raise J.Refuse(f"{p['key']}: sessions of the test days were dropped by a strategy error ({why}): no store was written")
                _write(p["key"], {**p["meta"], "stage": p["stage"], "period": sw, "run_kw": p["kw"], "hold_to": RM.HOLD, "inputs_hash": p["hash"],
                                  "code": code(p["family"]), **more}, p["grid"], res, out)
                _book(p, p["cells"], cnt, res[0]["elapsed_s"], ledger, out, period=sw)
                say(f"{p['stage']} {p['key']}: {p['cells']} cells, {cnt:,} trades, {res[0]['elapsed_s']} s of tape (wall {time.monotonic() - t0:.0f} s, {n} workers)")
                rows[p["key"]] = _row(p, out, skipped=False, ok=True, trades=cnt, code_same=True)
    return {"stores": [rows[p["key"]] for p in todo], "calendar": run_days, "trades": kept}
