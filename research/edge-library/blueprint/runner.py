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
"""
from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import hashlib
import json
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
      exits other than the standard table (line 0.2; the control pool holds its 32 cells and no other)
      a Level 2 filter (the engine does not open its feature table for the build range)
      a family with a `prepare` step of its own (va_reclaim: its value-area cache and its tape reads know the old build
      days only, so 2025 would raise inside a worker; the engine has to open it first)."""
    if isinstance(spec, (str, Path)):
        try:
            spec = json.loads(Path(spec).read_text())
        except (OSError, ValueError) as e:
            raise J.Refuse(f"spec file {spec}: {e}") from None
    try:
        sp = spec if isinstance(spec, dict) and "variants" in spec else RI.check_spec(spec)      # (run_idea's own check is not run twice)
    except (RI.SpecError, RM.RegistryBroken) as e:
        raise J.Refuse(str(e)) from None
    blocks = _blocks()
    if (sp["exits"], sp["filter_exits"]) != ("standard", "standard"):
        raise J.Refuse(f"{sp['name']}: a build runs the standard exit table only (BLUEPRINT.md line 0.2), not exits {sp['exits']!r} / {sp['filter_exits']!r}")
    l2 = [f"{b} {s}" for b, s in sp["filters"] if b in blocks.L2_BLOCKS]
    if l2:
        raise J.Refuse(f"{sp['name']}: filter {l2[0]} reads Level 2, which the engine does not open for the build range")
    if getattr(blocks.WRAPPED[sp["family"]], "prepare", None) is not None:
        raise J.Refuse(f"{sp['name']}: family {sp['family']} builds its own cache for the old build days only and reads tapes without the "
                       "build switch: it cannot run on the build range until the engine opens it")
    return sp


@lru_cache(maxsize=None)
def _sha(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def code(family=None) -> dict:
    """sha256/16 of the code that makes a store's trades: the engine and the random entries (a pool), + the blocks and the
    family's own module (a unit). Kept in run.json; the fingerprint of the INPUTS is another thing (fingerprint)."""
    files = ["l2sim.py", "l2ref.py"] + ([] if family is None else ["families/blocks.py", f"families/{RM.registry().MODULE_OF[family]}.py"])
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


def pool_key(root: str, tf) -> str:
    return f"c1-{root}-tf{tf}"


def pool_part(root: str, tf, cells=None) -> dict:
    """THE CONTROL POOL of a market and bar size: l2ref.Random (p_entry 0.5) x the seeds of control.json x the 32 exit cells
    (run_menus.c1_grid, seeded), every cell in all seven sessions."""
    import l2ref
    if root not in S.MENU_STOP_PTS or str(tf) not in l2ref.Random.SCREEN_TFS:
        raise J.Refuse(f"no control pool for market {root!r} and bar size {tf!r}: markets {sorted(S.MENU_STOP_PTS)}, bar sizes {l2ref.Random.SCREEN_TFS}")
    seeds = list(range(1, R.template("control")["seeds"] + 1))
    meta = {"family": "random", "tf": str(tf), "control": "c1", "p_entry": RM.C1_P_ENTRY, "seeds": seeds, "sessions": list(RM.DAY_PASSES),
            "note": f"{len(seeds)}-seed random-entry pool of the build range, all sessions: the control of every idea at this market and bar size"}
    return _part(pool_key(root, tf), "pool", root, tf, _seeded(RM.c1_grid, seeds, root, str(tf)), RM.DAY_PASSES, cells, meta)


def parts(spec: dict, cells=None) -> list:
    """Every store an idea needs, in run order: per market and bar size its control pool, its unit, its filter units."""
    kw = dict(getattr(_blocks().WRAPPED[spec["family"]], "SCREEN_RUN", {}))
    out = []
    for root in spec["markets"]:
        for tf in spec["bar_sizes"]:
            out.append(pool_part(root, tf, cells))
            for u in RI.spec_units(spec, [root], [tf]):
                out.append(_part(u["key"], "filter" if u["filter"] else "unit", root, tf, u["grid"], spec["sessions"], cells, RI.unit_meta(spec, u),
                                 spec["family"], kw, u["filter"]))
    return out


def fingerprint(part: dict, days=None) -> str:
    """The INPUTS of a store as 16 hex digits: every cell with its class, its inputs and the sessions it is run in; the
    range (and the named days of a smoke run); the hold; the run options. Two stores with one fingerprint were asked for
    the same trades."""
    cells = [[c["id"], f"{c['spec'][0].__module__}.{c['spec'][0].__qualname__}", c["spec"][1], [x[1]["sess"] for x in one]]
             for c, one in zip(part["grid"], part["runs"])]
    doc = {"period": PERIOD, "days": days, "hold": RM.HOLD, "kw": part["kw"], "cells": cells}
    return hashlib.sha256(json.dumps(doc, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ================================================================ the run

def run_build(spec, workers=None, out_dir=None, *, ledger=None, days=None, cells=None, progress=None, block=None, dry=False) -> list:
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
    todo = list({p["key"]: p for sp in sps for p in parts(sp, cells)}.values())      # (a pool two specs share is one store)
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
                              **dict(getattr(_blocks().WRAPPED[sp["family"]], "SCREEN_RUN", {}))))
    if res["skipped_by_error"]:
        raise J.Refuse(f"{key} cell {cell}: sessions were dropped by a strategy error")
    return [t for t in res["trades"] if S.session_of(t["entry_ms"]) == sess]


def run_pools(roots, tfs, workers=None, out_dir=None, *, ledger=None, days=None, cells=None, progress=None, block=None, dry=False) -> list:
    """The control pools of the markets x bar sizes named, one tape pass each (run_build's arguments and rows)."""
    return _run([pool_part(r, tf, cells) for r in roots for tf in tfs], workers, out_dir, ledger, days, cells, progress, block, dry, "control pools")


def _where(out: Path, key: str) -> str:
    return f"{out.name}/{key}"


def _stored(p: dict, out: Path) -> bool:
    """Is this store on disk with the same inputs? A store of other inputs, or one that is not inside the build days, is
    refused: it is never skipped as if it were the one asked for, and never written over."""
    f = out / p["key"] / "run.json"
    if not f.exists() or not (f.parent / "cells.npz").exists():
        return False
    m = guard(json.loads(f.read_text()), _where(out, p["key"]))
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


def _row(p: dict, out: Path, **more) -> dict:
    return {"key": p["key"], "kind": p["kind"], "root": p["root"], "tf": p["tf"], "cells": p["cells"], "stage": STAGE["pool" if p["kind"] == "pool" else "unit"],
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
        p["have"] = _stored(p, out)
    pend = [p for p in todo if not p["have"]]
    if pend:
        may_start()
        for root in dict.fromkeys(p["root"] for p in pend if p["root"] != "NQ" and days is None):
            miss = [d.isoformat() for d in S.sessions(*S.period(PERIOD), root, allow_holdout=PERIOD) if S.hb_tape_path(d, root) is None]
            if miss:
                raise J.Refuse(f"{len(miss)} sessions of {root} on the build range have no tape yet (first {miss[0]}): build them first (engine/l2sim.py build_tapes)")
        cand = sum(p["cells"] for p in pend if p["kind"] != "pool")
        try:
            if cand:
                LB.ledger_check(cells=cand + RM.PAPER_CELLS, path=ledger, caps=RI.CAPS)      # refused as a whole, before any pass
        except LB.CapExceeded as e:
            raise J.Refuse(f"the candidate-cell cap of the ledger (the stores' cells count against it, the pools' do not): {e}") from None
    rows = {p["key"]: _row(p, out, skipped=True, ok=True, trades=_trades(p["stored"]), code_same=p["stored"].get("code") == code(p["family"]))
            for p in todo if p["have"]}
    unbooked = [p for p in todo if p["have"] and not LB.ledger_has(p["key"], STAGE["pool" if p["kind"] == "pool" else "unit"], ledger)]
    if dry or not (pend or unbooked):               # nothing to write: no lock is taken (a reader never waits for a run)
        if dry and pend and out.exists():
            with _alone(out):                       # ... but a job is not started into a folder another run is writing to
                pass
        return [rows.get(p["key"]) or _row(p, out, skipped=False, ok=None, trades=None) for p in todo]
    with _alone(out):
        say = _talk(out, progress)
        for p in unbooked:                          # a store without its ledger row (a run that died between the two): booked, not run again
            _book(p, len(p["stored"]["cells"]), _trades(p["stored"]), p["stored"].get("elapsed_s"), ledger, out)
        if pend:
            n = RM.auto_workers(default_workers() if workers is None else int(workers))
            for root in dict.fromkeys(p["root"] for p in pend if p["filter"] and p["filter"][0] == "volume" and days is None):
                S.wait_compute_window()                                 # the volume block's minute-volume cache, opened for the build range
                say(f"volume block {root}: {_blocks().build_minvol(root, PERIOD, n, allow_holdout=PERIOD)}")
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

    def __init__(self):
        self.packs, self.meta, self.last = [], None, -1
        self.n, self.rows = dict.fromkeys(self.SUMS, 0), {k: [] for k in self.LISTS}

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
        t = _Packed(self.packs)
        if len(t) and int(t.x["date"].max()) > S.BP_BUILD[1].toordinal():
            raise RuntimeError("the engine handed back a trade dated after the build range: nothing is stored")
        return {**self.n, **self.rows, "elapsed_s": round(self.n["elapsed_s"], 2), "meta": self.meta, "trades": t}


def _pass(parts_: list, root: str, days, workers: int, kw: dict, block, say) -> list:
    """ONE TAPE PASS for the stores of one market and bar size: every instance of every cell of every part, block of days
    after block of days (module docstring). -> per part, one merged result per cell (run_menus.merge) with its trades
    packed. Instances that carry state from day to day would not stand a cut: such a pass is one block."""
    specs, cut = [], [0]
    for p in parts_:
        for one in p["runs"]:
            specs += one
            cut.append(len(specs))
    days = seal([d.isoformat() for d in S.sessions(*S.period(PERIOD), root, allow_holdout=PERIOD)] if days is None else days)     # the law's range, again
    step = max(1, int(block or R.template("compute")["block_days"])) if all(getattr(c, "session_independent", False) for c, _ in specs) else len(days)
    acc = [_Cell() for _ in cut[1:]]
    for k in range(0, len(days), step):
        say(f"days {k + 1}-{min(k + step, len(days))} of {len(days)} ({len(specs)} instances)")
        res = S.run_many(specs, period=PERIOD, days=days[k:k + step], root=root, workers=workers, **kw)
        for a, i, j in zip(acc, cut, cut[1:]):
            a.add(RM.merge(res[i:j]))
    out, k = [], 0
    for p in parts_:
        out.append([a.result() for a in acc[k:k + p["cells"]]])
        k += p["cells"]
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


def _book(p: dict, cells: int, trades: int, elapsed, ledger, out: Path, stage=None, note=None) -> None:
    """The store's ledger row, once (the way run_idea books a store: a pool is a null grid, a unit a candidate grid)."""
    stage, m = stage or STAGE["pool" if p["kind"] == "pool" else "unit"], p["meta"]
    if not stage.endswith("_error") and LB.ledger_has(p["key"], stage, ledger):
        return
    seeds = m.get("seeds")
    LB.ledger_add(stage, p["key"], "null" if p["kind"] == "pool" else "grid", cells=cells, trades=trades, family=m.get("family", ""), root=p["root"],
                  tf=p["tf"], period=PERIOD, control=m.get("control", ""), seed=f"{seeds[0]}-{seeds[-1]}" if seeds else "", elapsed_s=elapsed,
                  note=note or f"{_where(out, p['key'])}: {m.get('note') or ''}"[:200], path=ledger, caps=RI.CAPS)


def _record(p: dict, res: list, days, out: Path, ledger, say, workers: int, wall: float) -> dict:
    """A part's results -> its store and its ledger row. A pass that dropped a session by a strategy error writes NO store:
    an error row (a unit's cells still count), and the key stays to be run once the family is fixed."""
    n = sum(len(r["trades"]) for r in res)
    if sum(r["skipped_by_error"] for r in res):
        why = next(x["reason"] for r in res for x in r["no_trade"] if x["reason"].startswith(S.ERROR_PREFIX))
        say(f"ERROR {p['key']}: sessions dropped by a strategy error ({why}); no store written")
        _book(p, p["cells"], n, res[0]["elapsed_s"], ledger, out, STAGE["pool" if p["kind"] == "pool" else "unit"] + "_error", why[:200])
        return _row(p, out, skipped=False, ok=False, trades=n, error=why)
    stage = STAGE["pool" if p["kind"] == "pool" else "unit"]
    _write(p["key"], {**p["meta"], "stage": stage, "period": PERIOD, "run_kw": p["kw"], "hold_to": RM.HOLD, "inputs_hash": p["hash"],
                      "code": code(p["family"]), **({"days": days} if days else {})}, p["grid"], res, out)
    _book(p, p["cells"], n, res[0]["elapsed_s"], ledger, out)
    say(f"{stage} {p['key']}: {p['cells']} cells, {n:,} trades, {res[0]['elapsed_s']} s of tape (wall {wall:.0f} s, {workers} workers)")
    return _row(p, out, skipped=False, ok=True, trades=n, code_same=True)
