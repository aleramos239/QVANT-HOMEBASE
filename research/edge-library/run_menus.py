#!/usr/bin/env python3
"""run_menus.py -- the BUILD menus of the edge library (EDGE_SPEC "Variant menu" + "PROPER RE-RUN").

A RUN UNIT = a registered edge-library family x root x tf. For one unit this runs, in ONE tape pass over BUILD
(2021-09-22 .. 2023-12-31, 1 contract, the tester fill law), EVERY menu cell = every registered family-parameter variant x
the 32 exit cells (8 stops x 4 targets), over all seven sessions -- and its nulls.

EXIT CONVENTION (EDGE_SPEC "ORCHESTRATOR DECISIONS 2026-10-03" 1, "flat by 4pm"): EVERY unit and EVERY null runs with the
Template input hold_to = 'day' (HOLD): a trade runs to its stop / target or is flattened at 15:58 ET of its trade date
(13:13 on an equity half day), never at the session end; entries stay inside their session window. A cell of a Template
family is therefore run as SEVEN INDEPENDENT instances in that pass -- one per session, DAY_PASSES = asia, london, pre,
nyam, mid, pm, eve (an instance whose family never trades that session is left out) -- whose trades are merged into the
cell (split offline by entry time): one position at a time PER SESSION, and a trade held from one session never blocks an
entry of another (a judged unit = family x tf x session x root). A time-fired family has its own clock window and is one
instance. (cell_specs(cell, hold="session") is the OLD convention -- three instances, sess 'all' / 'pre' / 'eve', flat at
each session end -- kept for the tester-match gates and regression tests; the 77 BUILD + 13 null stores made with it are
VOID: runs_void/.) JUDGED UNITS: a MIRROR family (tod_drift dir, ib mode, gap mode) is judged as one unit per value of its
mirror axis (library.plateau_units); the store stays one per family x root x tf.

    <family>-<root>-tf<tf>             the unit: N = variants x 32 cells                                  (counts N cells)
    <family>-<root>-tf<tf>-shift       TIME-SHUFFLE NULL of a time-fired family (an input `shift_seed`): the same grid fired
                                       at a seeded random minute within +/- 90 min, seeds 1 and 2; same pass  (2 N NULL cells)
    <family>-<root>-tf<tf>-c2s<seed>   C2 FEATURE-SHUFFLE NULL of a Level-2 family, seeds 1 and 2: the same grid on
                                       score.C2Features; one pass per seed                              (N NULL cells each)
    c1-<root>-tf<tf>                   C1 RANDOM-ENTRY POOL of the root x tf (shared by every family at that tf): l2ref.Random,
                                       p_entry 0.5, seeds 1 and 2, the 32 exit cells; `nulls` command       (64 NULL cells)

Stores go to runs/<key>/ (library.write_unit: run.json with the range + period, cells.npz, table.csv), one row per store to
ledger.csv. IDEMPOTENT: a key that has its store and its ledger row is skipped. HARD CAPS (library.CAPS): a batch that
would pass the 50,000 CANDIDATE-cell cap is refused as a whole before anything runs. NULL / control cells do NOT count
toward that cap (ORCHESTRATOR DECISIONS 6): ledger kind 'null', column null_cells, tracked separately. A pass that dropped
a session by a strategy error writes NO store: a '<stage>_error' ledger row (a candidate grid's cells still count) and the
key stays pending until the family is fixed.
GROUP (EDGE_SPEC "STAGE 2b -- NEW-IDEA ROUND 1"): --group <module> = the library families registered by
engine/families/<module>.py (round1: N1 .. N7). Their declarations live in that module: a family's own exit cells
(`unit_exits`), its information-only AUTHOR cells (`author_cells`: run and stored with 'info': True, counted as candidate cells,
left out of library.plateau), a `prepare(root, workers)` step run once before a unit's pass (va_reclaim: the value-area
cache). NULLS of the group: a bar-based family = the C1 pool of its root x tf (the day- and session-matched random-entry
control with the same exit cell: library.c1_draws); late_mom = the same 15:30 trade with a random direction and the
straddle_tight entries = the same bracket at random minutes (both through `shift_seed`: the '-shift' store of the unit).
GROUP round2 (EDGE_SPEC "STAGE 4 -- EVENT ENTRY VARIANTS", engine/families/round2.py): straddle_wide_0830 / _1000 (W: 36 own
cells each, null = the same bracket at random minutes) and event_dir_0830 / _1000 (D: 7 delays x the 32 menu cells = 224,
null = the same entry with a random direction); all time-fired, so no C1 pool is needed. They run on EVERY BUILD day: the
release-day filter is the analyst's. `plan --group round2` prints the table and the fit under the cap.
COMPUTE: <= 8 worker processes for this project; `--workers` is lowered when the machine is busy (other research jobs) and
l2sim waits out 09:18-09:36 ET on weekdays by itself. BUILD only: nothing here reads PICK or EXAM.

    python run_menus.py plan   [--only fam,fam | --group round1] [--roots NQ,ES,GC]     the units, their cell counts and the cap
                               (nothing runs); with --group: the group's table per family x market + the fit under the cap
    python run_menus.py status [--group round1]
    python run_menus.py run    --family donchian [--roots NQ] [--tf 5,15] [--workers 8] [--no-nulls]
    python run_menus.py run    --group round1 --roots NQ,ES,GC [--workers 8]      every unit of the group; restartable
    python run_menus.py plan   --group round2          /          run --group round2 --roots NQ,ES,GC --workers 8
    python run_menus.py nulls  [--roots NQ,ES,GC] [--tf 1,5,15,30] [--workers 8]        the C1 random pools
    python run_menus.py smoke  <family> [--root NQ] [--tf 5] [--days 10] [--workers 1]
        BUG CHECK for family authors on <= 10 fixed BUILD days: COUNTS ONLY (sessions, dropped sessions and their error,
        trades per cell / session / side, entry kinds, both-side evidence, 1- vs 2-worker parity, the nulls' trade counts).
        Never prints or stores P&L, exit reasons or win rates; writes no store and no ledger row.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

W = Path(__file__).resolve().parent
ENGINE = W / "engine"
for _p in (str(W), str(ENGINE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import l2sim      # noqa: E402
import library    # noqa: E402

PERIOD = "build"
LOG = W / "out" / "run_menus.log"
NULL_SEEDS = (1, 2)
PAPER_CELLS = 824                                  # stage-1 candidate cells booked on paper only (progress.md 2026-10-04: "the 824
#                                                    stage-1 cells were re-booked on paper only"): added to the ledger's count in a plan
C1_P_ENTRY = 0.5                                   # the random pool must hold enough trades per (date, session) to match a member
# 10 fixed BUILD days: early sample, a roll day and roll + 1, two half days, an FOMC day, plain days (the smoke test)
SMOKE_DAYS = ("2021-10-05", "2022-03-15", "2022-06-13", "2022-09-21", "2022-11-25", "2023-03-22", "2023-07-03", "2023-08-09",
              "2023-10-17", "2023-12-13")


class RegistryBroken(RuntimeError):
    """families.ERRORS is not empty: a family module failed to import or breaks the contract."""


def _log(msg: str, path=None) -> None:
    line = f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    p = Path(path) if path is not None else LOG
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(line + "\n")


def busy_workers() -> int:
    """Heavy python processes already running on this machine (CPU > 50 %), ours or another research job's."""
    try:
        out = subprocess.run(["ps", "-Ao", "pid=,pcpu=,command="], capture_output=True, text=True, timeout=10).stdout
    except Exception:                                # noqa: BLE001 - a failed `ps` must not stop a run
        return 0
    n = 0
    for ln in out.splitlines():
        parts = ln.split(None, 2)
        if len(parts) < 3 or int(parts[0]) == os.getpid():
            continue
        try:
            cpu = float(parts[1])
        except ValueError:
            continue
        if cpu > 50.0 and "ython" in parts[2]:
            n += 1
    return n


def auto_workers(asked: int | None = None) -> int:
    """<= 8 for this project and never more than the idle cores (2 are left for the desk)."""
    asked = l2sim.MAX_WORKERS if asked is None else int(asked)
    free = (os.cpu_count() or 4) - 2 - busy_workers()
    return max(1, min(asked, l2sim.MAX_WORKERS, free))


def registry():
    import families
    if families.ERRORS:
        raise RegistryBroken("families registry has errors (fix them first):\n  "
                             + "\n  ".join(f"{k}: {v}" for k, v in families.ERRORS.items()))
    return families


def unit_key(family: str, root: str, tf: str) -> str:
    return f"{family}-{root}-tf{tf}"


HOLD = l2sim.LIBRARY_HOLD                         # 'day': the exit convention of EVERY unit and null (ORCHESTRATOR DECISIONS 1)
DAY_PASSES = ("asia", "london", "pre", "nyam", "mid", "pm", "eve")      # hold_to='day': one independent instance per session
SESS_PASSES = ("all", "pre", "eve")               # hold_to='session' (the OLD convention; gates / regression tests only)


def is_time_fired(cls) -> bool:
    return "shift_seed" in cls.defaults()


def cell_specs(cell: dict, hold: str | None = None) -> list:
    """The run_many specs of ONE menu cell under the exit convention `hold` (default HOLD = 'day').
    'day': a time-fired family = one instance (hold_to day); a Template family = one independent instance per session of
    DAY_PASSES (hold_to day), without the sessions the family itself never trades (its fam_filter: ib in asia, ...).
    'session' (old): one instance / three (sess all, pre, eve), flat at each session end."""
    cls, params = cell["spec"]
    hold = HOLD if hold is None else hold
    if hold == "session":
        return [(cls, params)] if is_time_fired(cls) else [(cls, {**params, "sess": s}) for s in SESS_PASSES]
    if hold != "day":
        raise ValueError(f"hold {hold!r}: 'day' or 'session'")
    if is_time_fired(cls):
        return [(cls, {**params, "hold_to": "day"})]
    specs = [(cls, {**params, "sess": s, "hold_to": "day"}) for s in DAY_PASSES]
    live = [x for x in specs if cls(x[1]).sessions()]
    return live or specs[:1]


def merge(parts: list) -> dict:
    """The results of one cell's instances -> ONE result: the trades of all of them in (exit, entry) order; coverage of the
    day pass (its first day instance); a trade date the 'eve' instance had to skip is listed in eve_skipped."""
    if len(parts) == 1:
        return parts[0]
    eves = [r for r in parts if r["meta"]["inputs"].get("sess") == "eve"]
    days = [r for r in parts if r["meta"]["inputs"].get("sess") != "eve"]
    base = (days or parts)[0]
    passes = [r["meta"]["inputs"].get("sess") for r in parts]
    out = dict(base)
    out["trades"] = sorted((t for r in parts for t in r["trades"]), key=lambda t: (t["exit_ms"], t["entry_ms"]))
    out["no_trade"] = [n for r in parts for n in r["no_trade"]]
    out["skipped_by_error"] = sum(r["skipped_by_error"] for r in parts)
    out["unrealistic_winners"] = sum(r.get("unrealistic_winners", 0) for r in parts)
    out["both_sides_sessions"] = max(r.get("both_sides_sessions") or 0 for r in parts)
    out["eve_skipped"] = list(eves[0]["skipped"]) if eves and days else list(base.get("eve_skipped", []))
    out["meta"] = {**base["meta"], "inputs": {**base["meta"]["inputs"], "sess": "+".join(passes)},
                   "segments": (["eve"] if eves else []) + (["day"] if days else []), "passes": passes}
    return out


def run_grid(grid: list, root: str, *, features, workers: int, days=None, kw=None, hold: str | None = None) -> list:
    """ONE tape pass for a grid: every cell's instances together -> one merged result per cell, in grid order.
    hold: the exit convention (default HOLD = 'day'; 'session' = the old one, tests only)."""
    specs, cut = [], [0]
    for c in grid:
        specs += cell_specs(c, hold)
        cut.append(len(specs))
    kw = dict(kw or {})
    res = (l2sim.run_many(specs, period=PERIOD, root=root, workers=workers, features=features, **kw) if days is None else
           l2sim.run_many(specs, days=list(days), root=root, workers=workers, features=features, **kw))
    return [merge(res[a:b]) for a, b in zip(cut, cut[1:])]


def shift_grid(grid: list) -> list:
    """The time-shuffle null of a time-fired unit: every cell of the grid again with shift_seed = 1 and 2."""
    out = []
    for sd in NULL_SEEDS:
        for c in grid:
            cls, params = c["spec"]
            out.append({"id": f"s{sd}_{c['id']}", "variant": {**c["variant"], "shift_seed": sd}, "exit": c["exit"], "vi": c["vi"],
                        "xi": c["xi"], "spec": (cls, {**params, "shift_seed": sd})})
    return out


def c1_grid(root: str, tf: str) -> list:
    """The C1 random-entry pool of a root x tf: l2ref.Random x seeds x the 32 exit cells."""
    import l2ref
    out = []
    for sd in NULL_SEEDS:
        for xi, x in enumerate(l2sim.menu(root)):
            v = {"seed": sd}
            out.append({"id": f"s{sd}_{l2sim.cell_id(x)}", "variant": v, "exit": x, "vi": sd - 1, "xi": xi,
                        "spec": (l2ref.Random, {"tf": str(tf), "sess": "all", "p_entry": C1_P_ENTRY, "seed": sd, **x})})
    return out


def units(only=None, roots=None, tfs=None) -> list:
    """Every unit of the registered edge-library families, in the EDGE_SPEC order of work: NQ first, then ES, then GC."""
    fam = registry()
    out = []
    for root in (roots or ("NQ", "ES", "GC")):
        for name in sorted(fam.LIBRARY):
            if only and name not in only:
                continue
            lib, cls = fam.LIBRARY[name], fam.REGISTRY[name][0]
            if root not in lib["roots"]:
                continue
            for tf in cls.SCREEN_TFS:
                if tfs and str(tf) not in tfs:
                    continue
                grid = fam.unit_grid(name, root, tf)      # variants x exit cells (+ the information-only author cells)
                n = len(grid)
                nulls = (2 * n if is_time_fired(cls) else 0) + (2 * n if lib["l2"] else 0)
                out.append({"key": unit_key(name, root, tf), "family": name, "root": root, "tf": str(tf), "cells": n,
                            "info_cells": sum(1 for c in grid if c.get("info")), "null_cells": nulls, "time_fired": is_time_fired(cls), "l2": lib["l2"], "mirror": lib.get("mirror"),
                            "weak": lib["weak"]})
    if only:
        missing = sorted(set(only) - set(fam.LIBRARY))
        if missing:
            raise KeyError(f"not edge-library families: {missing}; registered: {sorted(fam.LIBRARY)}")
    return out


def group_families(group: str) -> list:
    """The edge-library families registered by engine/families/<group>.py (round1 = EDGE_SPEC stage 2b, N1 .. N7; round2 =
    EDGE_SPEC stage 4, W straddle_wide and D event_dir at 08:30 / 10:00)."""
    fam = registry()
    names = sorted(n for n in fam.LIBRARY if fam.MODULE_OF[n] == group)
    if not names:
        raise KeyError(f"no edge-library family is registered by families/{group}.py; modules: {sorted(set(fam.MODULE_OF.values()))}")
    return names


def group_plan(group: str, roots=None, ledger=None, runs_dir=None) -> dict:
    """The plan of a group: per family x market the run units, candidate cells (author cells included: they are run), the
    author cells among them, the unit's own null cells (the '-shift' store) and its control; the C1 pools it needs
    (have / missing); and the fit under the candidate cap (ledger used + the group's cells still to run)."""
    fam = registry()
    us = units(group_families(group), roots)
    rows = []
    for name in sorted({u["family"] for u in us}):
        cls = fam.REGISTRY[name][0]
        for root in dict.fromkeys(u["root"] for u in us):
            sub = [u for u in us if u["family"] == name and u["root"] == root]
            if not sub:
                continue
            grid = fam.unit_grid(name, root, sub[0]["tf"])
            rows.append({"family": name, "root": root, "units": len(sub), "tfs": ",".join(u["tf"] for u in sub),
                         "cells": sum(u["cells"] for u in sub), "info_cells": sum(u["info_cells"] for u in sub),
                         "null_cells": sum(u["null_cells"] for u in sub), "instances_per_cell": len(cell_specs(grid[0])),
                         "control": "own null store '-shift' (shift_seed 1, 2)" if is_time_fired(cls) else "C1 pool of the root x tf",
                         "pending_cells": sum(u["cells"] for u in sub if not done(u["key"], runs_dir, ledger))})
    pools = sorted({(u["root"], u["tf"]) for u in us if not u["time_fired"]})
    missing = [f"c1-{r}-tf{t}" for r, t in pools if not done(f"c1-{r}-tf{t}", runs_dir, ledger, "null")]
    in_file = library.ledger_used(path=ledger)["cells"]
    used = in_file + PAPER_CELLS                       # what the project has used: the ledger file + the cells booked on paper
    cap = library.CAPS["cells"]
    cells, pend = sum(r["cells"] for r in rows), sum(r["pending_cells"] for r in rows)
    return {"group": group, "rows": rows, "run_units": len(us), "candidate_cells": cells, "info_cells": sum(r["info_cells"] for r in rows),
            "unit_null_cells": sum(r["null_cells"] for r in rows), "c1_pools_needed": len(pools), "c1_pools_missing": missing,
            "c1_null_cells_to_run": 64 * len(missing), "ledger_cells_used": used, "ledger_file_cells": in_file, "paper_cells": PAPER_CELLS, "pending_cells": pend, "cap": cap,
            "cells_after": used + pend, "fits": used + pend <= cap, "cap_left_after": cap - used - pend, "hold_to": HOLD}


def done(key: str, runs_dir=None, ledger=None, stage: str = "build") -> bool:
    d = (Path(runs_dir) if runs_dir is not None else library.RUNS) / key
    return (d / "run.json").exists() and (d / "cells.npz").exists() and library.ledger_has(key, stage, ledger)


def _pass(key: str, grid: list, root: str, *, features, workers: int, meta: dict, stage: str, runs_dir, ledger, log,
          days=None, run_kw=None) -> dict:
    """One tape pass over BUILD for a grid -> its store + its ledger row (the cells count even when the pass failed)."""
    t0 = time.monotonic()
    kw = dict(run_kw or {})
    res = run_grid(grid, root, features=features, workers=workers, days=days, kw=kw)
    return _record(key, grid, res, root, meta, stage, kw, runs_dir, ledger, log, workers, time.monotonic() - t0)


def run_unit(family: str, root: str, tf: str, *, workers: int | None = None, nulls: bool = True, runs_dir=None, ledger=None,
             log=None, days=None) -> list:
    """Run ONE unit over BUILD: its menu grid (+ the time-shuffle null of a time-fired family in the same pass; + the two C2
    passes of a Level-2 family). -> [{key, ok, cells} | {key, skipped: True}]. `days` is for tests only."""
    fam = registry()
    lib, (cls, inputs, both, notes) = fam.library(family), fam.REGISTRY[family]
    grid = fam.unit_grid(family, root, tf)
    key = unit_key(family, root, tf)
    plan = [(key, grid, None, "build", {})]
    if nulls and is_time_fired(cls):
        plan.append((key + "-shift", shift_grid(grid), None, "null", {"control": "shift"}))
    if nulls and lib["l2"]:
        for sd in NULL_SEEDS:
            plan.append((f"{key}-c2s{sd}", grid, sd, "null", {"control": "c2", "seed": sd}))
    todo = [x for x in plan if not done(x[0], runs_dir, ledger, x[3])]
    out = [{"key": x[0], "skipped": True} for x in plan if x not in todo]
    if not todo:
        return out
    library.ledger_check(cells=sum(len(x[1]) for x in todo if x[3] == "build"), path=ledger)      # the unit's CANDIDATE cells fit
    workers = auto_workers(workers)                                                                #   (nulls are not capped), or nothing runs
    prep = getattr(cls, "prepare", None)
    if prep is not None and days is None:             # a family's one-off cache, built in THIS process before the tape pass
        l2sim.wait_compute_window()
        _log(f"prepare {family} {root}: {prep(root, workers=workers)}", log)
    meta = {"family": family, "tf": str(tf), "both_sides_declared": both, "notes": lib.get("notes") or notes,
            "rationale": lib["rationale"], "complexity": lib["complexity"], "weak": lib["weak"], "penalty": lib["penalty"],
            "penalty_sess": lib.get("penalty_sess"), "second_look": lib.get("second_look"), "mirror": lib.get("mirror"),
            "variants": lib["variants"]}
    kw = dict(getattr(cls, "SCREEN_RUN", {}))
    # the unit and its time-shuffle null share ONE tape pass (no features differ); a C2 null needs its own loader
    same = [x for x in todo if x[2] is None]
    if same:
        joined = [c for x in same for c in x[1]]
        l2sim.wait_compute_window()
        t0 = time.monotonic()
        res = run_grid(joined, root, features=fam.features_for(family), workers=workers, days=days, kw=kw)
        k = 0
        for skey, sgrid, _, stage, extra in same:
            part = res[k:k + len(sgrid)]
            k += len(sgrid)
            out.append(_record(skey, sgrid, part, root, {**meta, **extra}, stage, kw, runs_dir, ledger, log, workers,
                               time.monotonic() - t0))
    for skey, sgrid, sd, stage, extra in [x for x in todo if x[2] is not None]:
        l2sim.wait_compute_window()
        out.append(_pass(skey, sgrid, root, features=fam.features_for(family, c2_seed=sd), workers=workers,
                         meta={**meta, **extra}, stage=stage, runs_dir=runs_dir, ledger=ledger, log=log, days=days, run_kw=kw))
    return out


def _record(key, grid, res, root, meta, stage, kw, runs_dir, ledger, log, workers, wall) -> dict:
    errs = sum(r["skipped_by_error"] for r in res)
    base = dict(family=meta.get("family", ""), root=root, tf=meta.get("tf", ""), period=PERIOD, control=meta.get("control", ""),
                seed=meta.get("seed", ""), elapsed_s=res[0]["elapsed_s"], path=ledger)
    kind = "null" if stage == "null" else "grid"      # a null / control grid is tracked in null_cells: not capped (decision 6)
    if errs:
        bad = next(r for r in res if r["skipped_by_error"])
        why = next(n["reason"] for n in bad["no_trade"] if n["reason"].startswith(l2sim.ERROR_PREFIX))
        _log(f"ERROR {key}: sessions dropped by a strategy error ({why}); no store written", log)
        library.ledger_add(stage + "_error", key, kind, cells=len(grid), note=why[:200], **base)
        return {"key": key, "ok": False, "cells": len(grid), "error": why}
    library.write_unit(key, {**meta, "stage": stage, "period": PERIOD, "run_kw": kw, "hold_to": HOLD}, grid, res, runs_dir)
    library.ledger_add(stage, key, kind, cells=len(grid), trades=sum(len(r["trades"]) for r in res), **base)
    _log(f"{stage} {key}: {len(grid)} cells, {sum(len(r['trades']) for r in res)} trades, {res[0]['elapsed_s']} s "
         f"(wall {wall:.0f} s, {workers} workers)", log)
    return {"key": key, "ok": True, "cells": len(grid)}


def run_c1(root: str, tf: str, *, workers: int | None = None, runs_dir=None, ledger=None, log=None, days=None) -> dict:
    """The C1 random-entry pool of a root x tf over BUILD (64 cells), once."""
    key = f"c1-{root}-tf{tf}"
    if done(key, runs_dir, ledger, "null"):
        return {"key": key, "skipped": True}
    grid = c1_grid(root, tf)                           # 64 NULL cells: tracked, not capped
    l2sim.wait_compute_window()
    return _pass(key, grid, root, features=None, workers=auto_workers(workers), meta={"family": "random", "tf": str(tf), "control": "c1",
                                                                                      "p_entry": C1_P_ENTRY},
                 stage="null", runs_dir=runs_dir, ledger=ledger, log=log, days=days)


def tapes_ready(root: str) -> list:
    """BUILD sessions of a non-NQ root that have an archive manifest but no tape yet (run `engine/l2sim.py tapes <ROOT>`)."""
    if root == "NQ":
        return []
    a, b = l2sim.period(PERIOD)
    return [d.isoformat() for d in l2sim.sessions(a, b, root) if l2sim.hb_tape_path(d, root) is None]


def smoke(family: str, root: str = "NQ", tf: str | None = None, n_days: int = 10, workers: int = 1) -> dict:
    """BUG CHECK of one family on <= 10 fixed BUILD days: counts only, nothing written (see the module docstring)."""
    import families as fam
    if family not in fam.REGISTRY:
        raise KeyError(f"{family!r} is not registered; registered {sorted(fam.REGISTRY)}; errors {fam.ERRORS}")
    lib = fam.library(family)
    cls, inputs, both, _ = fam.REGISTRY[family]
    tf = str(tf or cls.SCREEN_TFS[0])
    days = [d for d in SMOKE_DAYS if l2sim._date(d) in set(l2sim.sessions(*l2sim.period(PERIOD), root))][:max(1, min(int(n_days), 10))]
    grid = fam.unit_grid(family, root, tf)
    kw = dict(getattr(cls, "SCREEN_RUN", {}))
    workers = max(1, min(int(workers), 2))
    feats = fam.features_for(family)
    l2sim.wait_compute_window()
    res = run_grid(grid, root, features=feats, workers=workers, days=days, kw=kw)
    tr = [t for r in res for t in r["trades"]]
    errs = [n for r in res for n in r["no_trade"] if n["reason"].startswith(l2sim.ERROR_PREFIX)]
    out = {"family": family, "root": root, "tf": tf, "days": len(days), "cells": len(grid), "variants": len(lib["variants"]),
           "sessions": res[0]["sessions"], "used": res[0]["used"], "eve_skipped": len(res[0].get("eve_skipped", [])),
           "skipped_by_error": sum(r["skipped_by_error"] for r in res), "errors": errs[:3],
           "trades_total": len(tr), "trades_per_cell": {"min": min(len(r["trades"]) for r in res), "max": max(len(r["trades"]) for r in res)},
           "cells_without_trades": sum(1 for r in res if not r["trades"]),
           "long": sum(t["side"] == "long" for t in tr), "short": sum(t["side"] == "short" for t in tr),
           "by_session": dict(Counter(l2sim.session_of(t["entry_ms"]) or "none" for t in tr)),
           "by_stop_mode": dict(Counter(c["exit"]["stop_mode"] for c, r in zip(grid, res) for _ in r["trades"])),
           "entry_kind": {"market": sum(t["order_price"] is None for t in tr), "resting": sum(t["order_price"] is not None for t in tr)},
           "both_sides_declared": both, "both_sides_sessions": max(r["both_sides_sessions"] for r in res),
           "segments": res[0]["meta"]["segments"], "hold_to": HOLD,
           "instances_per_cell": len(cell_specs(grid[0])), **hold_checks(res, root)}
    win = getattr(sys.modules[cls.__module__], "ENTRY_WINDOWS", {}).get(family)       # the family's written entry window, ET seconds
    out["entry_hours"] = None if win is None else [l2sim._hms(win[0]), l2sim._hms(win[1])]
    out["entry_outside_hours"] = 0 if win is None else sum(1 for t in tr if not win[0] <= _et_sec(t["entry_ms"]) <= win[1])
    out["both_sides_ok"] = bool(both or out["both_sides_sessions"] == 0)
    sub = grid[:8]                                     # worker parity on the first 8 cells
    a = run_grid(sub, root, features=feats, workers=1, days=days, kw=kw)
    b = run_grid(sub, root, features=feats, workers=2, days=days, kw=kw)
    out["worker_parity"] = all(x["trades"] == y["trades"] for x, y in zip(a, b))
    nulls = {}
    if is_time_fired(cls):
        sh = run_grid(shift_grid(sub), root, features=feats, workers=workers, days=days, kw=kw)
        nulls["shift"] = {"trades": sum(len(r["trades"]) for r in sh), "skipped_by_error": sum(r["skipped_by_error"] for r in sh)}
    if lib["l2"]:
        c2 = run_grid(sub, root, features=fam.features_for(family, c2_seed=1), workers=workers, days=days, kw=kw)
        nulls["c2"] = {"trades": sum(len(r["trades"]) for r in c2), "skipped_by_error": sum(r["skipped_by_error"] for r in c2)}
    out["nulls"] = nulls
    out["ok"] = bool(out["skipped_by_error"] == 0 and out["both_sides_ok"] and out["worker_parity"]
                     and out["exit_after_day_flat"] == 0 and out["overlap_in_session"] == 0 and out["entry_in_no_session"] == 0
                     and out["entry_outside_hours"] == 0
                     and all(v["skipped_by_error"] == 0 for v in nulls.values()))
    return out


def _et_sec(entry_ms: int) -> int:
    a = dt.datetime.fromtimestamp(entry_ms / 1000, l2sim.ET)
    return a.hour * 3600 + a.minute * 60 + a.second


def hold_checks(res: list, root: str) -> dict:
    """COUNTS that must be 0 under hold_to='day' (bug checks, no P&L): trades that end after their trade date's flatten
    minute (15:58 ET, 13:13 on an equity half day: nothing is open across 17:00), trades of one cell-session that overlap
    (one position at a time per session), entries outside every session."""
    late = over = none = 0
    for r in res:
        last: dict = {}
        for t in sorted(r["trades"], key=lambda t: t["entry_ms"]):
            d = l2sim._date(t["date"])
            late += t["exit_ms"] >= l2sim.et_ns(d, l2sim.day_flat(d, root)) // 1_000_000 + 60_000
            sess = l2sim.session_of(t["entry_ms"])
            none += sess is None
            k = (t["date"], sess)
            over += last.get(k, 0) > t["entry_ms"]
            last[k] = max(last.get(k, 0), t["exit_ms"])
    return {"exit_after_day_flat": int(late), "overlap_in_session": int(over), "entry_in_no_session": int(none)}


def plan_totals(us: list) -> dict:
    """Plan size of a list of units(): candidate cells (they count toward the 50,000 cap) and null cells (tracked apart:
    the time-shuffle / C2 nulls of the units + one C1 pool of 64 cells per root x tf that holds a unit)."""
    pools = sorted({(u["root"], u["tf"]) for u in us})
    c1 = sum(len(c1_grid(root, tf)) for root, tf in pools)
    cand = sum(u["cells"] for u in us)
    mirror = [u for u in us if u.get("mirror")]
    return {"run_units": len(us), "candidate_cells": cand, "unit_null_cells": sum(u["null_cells"] for u in us),
            "c1_pools": len(pools), "c1_null_cells": c1, "null_cells": sum(u["null_cells"] for u in us) + c1,
            "mirror_run_units": len(mirror), "cap": library.CAPS["cells"], "cap_left_after": library.CAPS["cells"] - cand,
            "hold_to": HOLD, "instances_per_template_cell": len(DAY_PASSES)}


def status(ledger=None, runs_dir=None, only=None) -> dict:
    us = units(only)
    used = library.ledger_used(path=ledger)
    pend = [u for u in us if not done(u["key"], runs_dir, ledger)]
    return {"units": len(us), "done": len(us) - len(pend), "pending": [u["key"] for u in pend],
            "pending_cells": sum(u["cells"] for u in pend), "pending_null_cells": sum(u["null_cells"] for u in pend),
            "used": used, "null_cells_run": library.ledger_nulls(path=ledger), "caps": library.CAPS,
            "left": {k: library.CAPS[k] - used[k] for k in used}, "hold_to": HOLD,
            "over_cap_after_pending": used["cells"] + sum(u["cells"] for u in pend) > library.CAPS["cells"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="run_menus.py", description="BUILD menus of the edge library (see the module docstring)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "status"):
        s = sub.add_parser(name)
        s.add_argument("--only", default="")
        s.add_argument("--roots", default="")
        s.add_argument("--group", default="", help="a family module of engine/families (round1, round2): only its families")
    r = sub.add_parser("run")
    r.add_argument("--family", default="", help="comma list of edge-library family names")
    r.add_argument("--group", default="", help="every family registered by engine/families/<group>.py (round1, round2)")
    r.add_argument("--roots", default="NQ")
    r.add_argument("--tf", default="")
    r.add_argument("--workers", type=int, default=l2sim.MAX_WORKERS)
    r.add_argument("--no-nulls", action="store_true")
    n = sub.add_parser("nulls")
    n.add_argument("--roots", default="NQ")
    n.add_argument("--tf", default="1,5,15,30")
    n.add_argument("--workers", type=int, default=l2sim.MAX_WORKERS)
    s = sub.add_parser("smoke")
    s.add_argument("family")
    s.add_argument("--root", default="NQ")
    s.add_argument("--tf", default=None)
    s.add_argument("--days", type=int, default=10)
    s.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    csv_ = lambda x: [v for v in x.split(",") if v]          # noqa: E731
    try:
        if a.cmd == "smoke":
            o = smoke(a.family, a.root.upper(), a.tf, a.days, a.workers)
            print(json.dumps(o, indent=1))
            return 0 if o["ok"] else 1
        if a.cmd == "plan" and a.group:
            g = group_plan(a.group, [x.upper() for x in csv_(a.roots)] or None)
            print(f"{'family':20s} {'root':4s} {'units':>5s} {'tfs':10s} {'cells':>6s} {'author':>6s} {'own null':>8s} {'inst/cell':>9s}  control")
            for r in g["rows"]:
                print(f"{r['family']:20s} {r['root']:4s} {r['units']:5d} {r['tfs']:10s} {r['cells']:6d} {r['info_cells']:6d} "
                      f"{r['null_cells']:8d} {r['instances_per_cell']:9d}  {r['control']}")
            print(f"group {g['group']}: {g['run_units']} run units, {g['candidate_cells']} CANDIDATE cells ({g['info_cells']} of them "
                  f"information-only author cells) + {g['unit_null_cells']} own NULL cells (not capped); C1 pools needed "
                  f"{g['c1_pools_needed']}, missing {g['c1_pools_missing'] or 'none'} ({g['c1_null_cells_to_run']} null cells to run)")
            print(f"cap: {g['ledger_cells_used']} candidate cells used (ledger.csv {g['ledger_file_cells']} + {g['paper_cells']} booked on "
                  f"paper) + {g['pending_cells']} still to run = "
                  f"{g['cells_after']} of {g['cap']} -> {'FITS' if g['fits'] else 'DOES NOT FIT'} ({g['cap_left_after']} left)")
            return 0 if g["fits"] else 2
        if a.cmd == "plan":
            us = units(csv_(a.only) or None, [x.upper() for x in csv_(a.roots)] or None)
            for u in us:
                print(f"{u['key']:34s} cells {u['cells']:5d}  null cells {u['null_cells']:5d}"
                      f"{'  time-fired' if u['time_fired'] else ''}{'  L2' if u['l2'] else ''}"
                      f"{'  MIRROR ' + u['mirror'] + ' (one judged unit per value)' if u.get('mirror') else ''}"
                      f"{'  WEAK' if u.get('weak') else ''}")
            t = plan_totals(us)
            used = library.ledger_used()
            print(f"{t['run_units']} run units (hold_to = {HOLD}): {t['candidate_cells']} CANDIDATE cells of the {t['cap']} cap "
                  f"({t['cap_left_after']} left for stage D) + {t['null_cells']} NULL cells, not capped ({t['unit_null_cells']} "
                  f"time-shuffle / C2 + {t['c1_pools']} C1 pools x 64 = {t['c1_null_cells']}); ledger: {used['cells']} candidate "
                  f"cells used, {library.ledger_nulls()} null cells run")
            return 0
        if a.cmd == "status":
            print(json.dumps(status(only=group_families(a.group) if a.group else None), indent=1))
            return 0
        roots = [x.upper() for x in csv_(a.roots)]
        for root in roots:
            miss = tapes_ready(root)
            if miss:
                print(f"REFUSED: {len(miss)} BUILD sessions of {root} have no tape yet (first {miss[0]}): run "
                      f"`python engine/l2sim.py tapes {root}` first", file=sys.stderr)
                return 2
        out = []
        if a.cmd == "nulls":
            for root in roots:
                for tf in csv_(a.tf):
                    out.append(run_c1(root, tf, workers=a.workers))
        else:
            fam = registry()
            names = csv_(a.family) + (group_families(a.group) if a.group else [])
            if not names:
                print("REFUSED: run needs --family or --group", file=sys.stderr)
                return 2
            if a.group:                                # the bar-based units' control: the C1 pool of every root x tf they use
                for root, tf in sorted({(u["root"], u["tf"]) for u in units(group_families(a.group), roots) if not u["time_fired"]}):
                    out.append(run_c1(root, tf, workers=a.workers))        # skipped when the pool is already stored
            for root in roots:
                for name in names:
                    cls = fam.REGISTRY[name][0]
                    for tf in (csv_(a.tf) or cls.SCREEN_TFS):
                        if str(tf) in cls.SCREEN_TFS and root in fam.library(name)["roots"]:
                            out += run_unit(name, root, str(tf), workers=a.workers, nulls=not a.no_nulls)
        print(json.dumps(out))
        return 1 if any(o.get("ok") is False for o in out) else 0
    except (library.CapExceeded, RegistryBroken) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
