"""LOCK of the ONE store runner of the blueprint build range (blueprint/runner.py), of `bp.py build <spec>` on that range
(tables.built, api.build) and of the job machinery (blueprint/jobs.py) -- toolkit plan, step 4 and section 8.

(a) THE CLOCK: the default workers inside and outside desk hours come from templates/compute.json and never pass the engine's
    cap; a run with work to do is refused inside the engine's own no-start window (09:18-09:36 ET on weekdays).
(b) THE STORES: 1 worker against 8 (and one day block against blocks of 2 days) gives the same stores, file for file; a tiny
    run in the new mode is trade for trade what the stores on disk hold for the same days (runs/, and the extra control seeds
    in runs_seeds/); the unit, its filter unit and the control pool of one market and bar size share ONE tape pass; a rerun
    does no work; a store written from other inputs is never overwritten; every store has its ledger row.
(c) THE SEAL: a day on or after 2025-07-01 is refused before anything is read; every engine call carries period="bp_build"
    and no other switch; a store whose range ends after 2025-06-30 is refused by the runner and by the reader.
(d) THE LINES: `bp.py build <spec>` prints 2.1-2.8 on the new range with the line functions of the dry run; the random tables
    are drawn by the judge's own functions from the 10 seeds of the pool (held against judge.controls on the old stores).
(e) JOBS: `--wait` hands the work to a detached child process, `bp.py job <id>` (no name: the id finds it) picks the wait
    back up and answers with the build's own result, a refusal comes back at once and never as a job. The command lines are
    the connector's (homebase/claude_mcp/blueprint_tools.py): `build <name> --reason=TEXT --wait=S ... --root=DIR --json`.

TINY RUNS ONLY: 5 named build days (4 of the old build days, so that the stores on disk can be held against them, and
2025-06-30, the last build day), 2 exit cells, ONE market and bar size, at most 8 workers. Every store, ledger row and job
file goes to a temp folder (HOMEBASE_IDEAS_ROOT and HOMEBASE_DRAFTS_DIR point into it too): nothing is written under
runs_bp/, to ledger.csv or to ~/.homebase (the last test looks). No P&L is asserted: counts, identities, the answer's shape.

  pytest tests/test_blueprint_runner.py -q     (about a minute)     python tests/test_blueprint_runner.py     one line per test
"""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
import judge as J  # noqa: E402
from blueprint import api as A  # noqa: E402
from blueprint import cli as C  # noqa: E402
from blueprint import jobs as JOBS  # noqa: E402
from blueprint import rules as R  # noqa: E402
from blueprint import runner as RUN  # noqa: E402
from blueprint import tables as T  # noqa: E402

import l2sim as S  # noqa: E402
import library as LB  # noqa: E402
import run_menus as RM  # noqa: E402

DAYS = ["2022-03-15", "2022-11-25", "2023-03-22", "2023-07-03", "2025-06-30"]      # a plain day, two half days, the last build day
OLD = DAYS[:4]                                              # ... the four that the stores of the old build days hold too
CELLS = ["atr3-r1", "pts20-r0"]                             # 2 of the 32 exit cells
SPEC = {"name": "bpt_orb", "reason": "The first minutes of a session set a range that the rest of the session has to resolve.",
        "family": "orb", "markets": ["NQ"], "bar_sizes": ["15"], "sessions": ["nyam", "mid"], "params": {"or_min": ["5", "15", "30"]},
        "filters": [{"block": "momentum", "side": "with"}], "exits": "standard", "limits": {}}
KEYS = ["c1-NQ-tf15", "bpt_orb-NQ-tf15", "bpt_orb__momentum_with-NQ-tf15"]      # the pool, the unit, its filter unit: one pass
SAT = dt.datetime(2026, 10, 3, 11, 0, tzinfo=S.ET)           # a Saturday: no desk hours, no window
CONTRACT = ("ok", "command", "name", "status", "phase", "round", "lines", "text", "next", "job", "saved", "error")     # plan section 8
REASON = "the first look at the opening range break on the build days"      # line 2.9: every round has its reason, written before the run
HOME = Path.home() / ".homebase"
RESULTS: dict = {}
_T: dict = {"keep": tempfile.TemporaryDirectory(prefix="bp_runner_")}
_T["dir"] = Path(_T["keep"].name).resolve()
os.environ["HOMEBASE_IDEAS_ROOT"] = str(_T["dir"] / "ideas_env")       # never the real ~/.homebase: the idea folder of this module ...
os.environ["HOMEBASE_DRAFTS_DIR"] = str(_T["dir"] / "drafts")          # ... and its Lab drafts


def _listing(p: Path):
    return sorted(x.name for x in p.iterdir()) if p.exists() else None


BEFORE = {"runs_bp": _listing(RUN.RUNS), "ideas": _listing(HOME / "ideas"), "drafts": _listing(HOME / "strategies"),
          "ledger": (LB.LEDGER.stat().st_size, LB.LEDGER.stat().st_mtime_ns)}


def tmp() -> Path:
    """The temp folder of this module (removed when the interpreter ends)."""
    return _T["dir"]


@contextlib.contextmanager
def at(when):
    """The runner's clock stands at `when` (ET)."""
    keep = RUN.clock
    RUN.clock = lambda: when
    try:
        yield
    finally:
        RUN.clock = keep


@contextlib.contextmanager
def rule(**kw):
    keep = dict(J.RULE)
    J.RULE.update(kw)
    try:
        yield
    finally:
        J.RULE.clear()
        J.RULE.update(keep)


@contextlib.contextmanager
def watch():
    """Every tape pass of the runner (its store keys) and every engine call (its keywords) while the block runs."""
    seen, keep = {"passes": [], "calls": []}, (RUN._pass, S.run_many)

    def passed(parts, *a, **k):
        seen["passes"].append([p["key"] for p in parts])
        return keep[0](parts, *a, **k)

    def ran(specs, *a, **k):
        seen["calls"].append({**k, "args": a, "specs": len(specs)})
        return keep[1](specs, *a, **k)

    RUN._pass, S.run_many = passed, ran
    try:
        yield seen
    finally:
        RUN._pass, S.run_many = keep


@contextlib.contextmanager
def no_engine():
    """Nothing may be read: every way into a tape raises while the block runs."""
    names = ("run_many", "load_tape", "sessions", "load_daily")
    keep = {n: getattr(S, n) for n in names}

    def stop(*a, **k):
        raise AssertionError("the engine was asked for data")

    for n in names:
        setattr(S, n, stop)
    try:
        yield
    finally:
        for n, f in keep.items():
            setattr(S, n, f)


def refused(fn, word: str = "") -> str:
    try:
        fn()
    except (J.Refuse, R.RuleError) as e:
        assert word in str(e), str(e)
        return str(e)
    raise AssertionError(f"not refused ({word})")


def built(name: str, **kw) -> tuple:
    """The tiny build `name`, run once: (store folder, ledger file, the runner's rows, what was watched). It gets the
    workers it asks for, however busy the machine is (run_menus.auto_workers would lower them: the clock test covers that)."""
    if name not in _T:
        o, led = tmp() / f"runs_{name}", tmp() / f"ledger_{name}.csv"
        keep = RM.auto_workers
        RM.auto_workers = lambda n=None: n
        try:
            with watch() as seen, at(SAT):
                rows = RUN.run_build(SPEC, out_dir=o, ledger=led, days=DAYS, cells=CELLS, **kw)
        finally:
            RM.auto_workers = keep
        _T[name] = (o, led, rows, seen)
    return _T[name]


def differs(a: Path, b: Path) -> list:
    """What differs between two store folders (nothing = the same store): every array of cells.npz, table.csv byte for
    byte, run.json but for the seconds the pass took."""
    za, zb = np.load(a / "cells.npz"), np.load(b / "cells.npz")
    bad = [] if sorted(za.files) == sorted(zb.files) else ["the fields of cells.npz"]
    bad += [k for k in za.files if k in zb.files and not np.array_equal(za[k], zb[k], equal_nan=True)]
    bad += ["table.csv"] * ((a / "table.csv").read_bytes() != (b / "table.csv").read_bytes())
    ma, mb = (json.loads((p / "run.json").read_text()) for p in (a, b))
    return bad + [f"run.json {k}" for k in sorted(set(ma) | set(mb)) if k != "elapsed_s" and ma.get(k) != mb.get(k)]


def _rc():
    """out/check2025/run_check.py: the runner that wrote the 10-seed controls of 2025; its `seeded` and `_same` are the house's."""
    p = str(W / "out" / "check2025")
    if p not in sys.path:
        sys.path.insert(0, p)
    import run_check
    return run_check


def bare(u: dict, ids: list, sess=None) -> tuple:
    """Cells of a loaded store as the bare run results run_check._same compares (entry time and net of each trade), one
    session only when `sess` is named."""
    res = []
    for cid in ids:
        x = LB.unit_cell(u, cid)
        m = np.ones(len(x["net"]), bool) if sess is None else x["sess"] == LB.SESS_CODE[sess]
        res.append({"trades": [{"entry_ms": int(e), "net": float(n)} for e, n in zip(x["entry_ms"][m], x["net"][m])]})
    return [{"id": c} for c in ids], res


def ledger(path) -> list:
    return [(r["stage"], r["key"], r["kind"], r["period"], int(r["cells"]), int(r["null_cells"])) for r in LB.read_ledger(path)]


# ================================================================ (a) the clock

def test_workers_and_the_no_start_window(monkeypatch):
    monkeypatch.setattr(S, "OPEN_WINDOW", (dt.time(9, 18), dt.time(9, 36)))            # off since 2026-10-07 (l2sim.OPEN_WINDOW): put back here
    c = R.template("compute")
    assert c["workers"] == {"desk_hours": 4, "other": 12} and c["desk_hours_et"] == ["08:00", "16:15"] and c["workers"]["other"] <= 12
    assert c["no_start_et"] == ["09:18", "09:36"] and c["block_days"] >= 1
    assert " ".join(c["text"].split()) in " ".join((W / "out" / "blueprint" / "toolkit_plan.md").read_text().split())
    tue = lambda h, m: dt.datetime(2026, 10, 6, h, m, tzinfo=S.ET)  # noqa: E731
    got = [RUN.default_workers(t) for t in (tue(7, 59), tue(8, 0), tue(12, 0), tue(16, 14), tue(16, 15), tue(23, 0), SAT)]
    assert got == [min(n, S.MAX_WORKERS) for n in (12, 4, 4, 4, 12, 12, 12)], got
    with at(tue(12, 0)):
        assert RUN.default_workers() == min(4, S.MAX_WORKERS)
    for t in (tue(9, 17), tue(9, 36), tue(15, 0), dt.datetime(2026, 10, 3, 9, 20, tzinfo=S.ET)):       # outside the window; a Saturday
        RUN.may_start(t)
    for t in (tue(9, 18), tue(9, 25), tue(9, 35)):
        assert S.compute_window_end(t) is not None                              # the engine's own window: one definition
        assert "09:36" in refused(lambda t=t: RUN.may_start(t), "09:18-09:36")
    # a run with work to do is refused inside the window before anything is read; nothing is left behind
    o, led = tmp() / "runs_window", tmp() / "ledger_window.csv"
    with at(tue(9, 20)), watch() as seen:
        refused(lambda: RUN.run_build(SPEC, out_dir=o, ledger=led, days=DAYS, cells=CELLS), "09:18-09:36")
    assert seen["calls"] == [] and not led.exists() and not list(o.glob("*/run.json"))
    # the workers a pass gets: the number asked -- or the default of the hour -- lowered to what the machine has free
    # (run_menus.auto_workers, as the other runners); the pass itself is stopped here before it reads anything
    class Stop(Exception):
        pass

    def stop(parts, root, days, workers, *a, **k):
        raise Stop(workers)

    keep, asked = (RM.auto_workers, RUN._pass), []
    RM.auto_workers, RUN._pass = (lambda n=None: asked.append(n) or 3), stop
    try:
        for when, workers, want in ((tue(12, 0), None, 4), (SAT, None, 12), (tue(12, 0), 8, 8), (SAT, 2, 2)):
            with at(when), no_engine():
                try:
                    RUN.run_build(SPEC, workers=workers, out_dir=o, ledger=led, days=DAYS, cells=CELLS)
                    raise AssertionError("the pass was not reached")
                except Stop as e:
                    assert e.args == (3,) and asked[-1] == min(want, S.MAX_WORKERS), (when, workers, asked, e.args)
    finally:
        RM.auto_workers, RUN._pass = keep
    assert not led.exists() and not list(o.glob("*/run.json"))


# ================================================================ (b) the stores

def test_one_tape_pass_per_market_and_bar_size_and_a_ledger_row_per_store():
    o, led, rows, seen = built("a", workers=1)
    assert seen["passes"] == [KEYS] and len(seen["calls"]) == 1                 # pool + unit + filter unit: ONE pass, one day block
    assert [(r["key"], r["kind"], r["cells"], r["skipped"], r["ok"]) for r in rows] == \
        [(KEYS[0], "pool", 20, False, True), (KEYS[1], "unit", 6, False, True), (KEYS[2], "filter", 6, False, True)]
    assert all(Path(r["path"]) == o / r["key"] and (o / r["key"] / "cells.npz").exists() and r["trades"] > 0 for r in rows)
    assert ledger(led) == [("null_bp", KEYS[0], "null", "bp_build", 0, 20), ("bp_build", KEYS[1], "grid", "bp_build", 6, 0),
                           ("bp_build", KEYS[2], "grid", "bp_build", 6, 0)]
    assert LB.read_ledger(led)[0]["seed"] == "1-10" and all(int(r["trades"]) > 0 for r in LB.read_ledger(led))
    rg = R.template("ranges")["build"]
    for k in KEYS:
        m = json.loads((o / k / "run.json").read_text())
        assert m["range"] == {"start": rg["start"], "end": rg["end"], "holdout": True, "period": "bp_build"} and m["period"] == "bp_build"
        assert m["days"] == DAYS and m["hold_to"] == "day" and m["coverage"]["sessions"] == len(DAYS) and len(m["inputs_hash"]) == 16
        assert set(m["code"]) >= {"l2sim.py", "l2ref.py"} and all(len(v) == 16 for v in m["code"].values())
        assert all(c["skipped_by_error"] == 0 for c in m["cells"])
    pool, unit, filt = (json.loads((o / k / "run.json").read_text()) for k in KEYS)
    assert (pool["stage"], pool["control"], pool["family"], pool["seeds"], pool["sessions"]) == ("null_bp", "c1", "random", list(range(1, 11)), list(RM.DAY_PASSES))
    assert [c["id"] for c in pool["cells"]] == [f"s{sd}_{x}" for sd in range(1, 11) for x in CELLS]
    assert (unit["stage"], unit["idea"], unit["family"], unit["sessions"], unit["filter"]) == ("bp_build", "bpt_orb", "orb", ["nyam", "mid"], None)
    assert [c["id"] for c in unit["cells"]] == [f"or_min{v}_{x}" for v in ("5", "15", "30") for x in CELLS] == [c["id"] for c in filt["cells"]]
    assert filt["filter"]["block"] == "momentum" and "code" in filt and "families/blocks.py" in unit["code"]
    assert pool["inputs_hash"] != unit["inputs_hash"] != filt["inputs_hash"]
    # the pool's cells: FIRST the 10-seed grid of the 2025 controls (out/check2025/run_check.py: seeded(RM.c1_grid, ...)), its 32 exits a seed,
    # THEN the 16 small-target cells of every seed (BLUEPRINT.md version 1.1): 48 exits a seed
    full = RUN.pool_part("NQ", "15")
    ref = _rc().seeded(RM.c1_grid, range(1, 11), "NQ", "15")
    assert [(c["id"], c["spec"]) for c in full["grid"][:320]] == [(c["id"], c["spec"]) for c in ref] and full["cells"] == 480 and full["key"] == KEYS[0]
    small = full["grid"][320:]
    assert {c["exit"]["tgt_r"] for c in small} == {0.5, 0.75} and [c["variant"]["seed"] for c in small] == [s for s in range(1, 11) for _ in range(16)]
    assert all(c["spec"][1]["seed"] == c["variant"]["seed"] and c["id"] == f"s{c['variant']['seed']}_{S.cell_id(c['exit'])}" for c in small)
    assert [c["exit"] for c in small[:16]] == R.exit_menu("NQ")[32:] and [c["xi"] for c in small[:16]] == list(range(32, 48))
    RESULTS["test_one_tape_pass_per_market_and_bar_size_and_a_ledger_row_per_store"] = (3, 3, "stores of one pass, each with its ledger row")


def test_one_worker_against_eight_and_day_blocks_give_identical_stores():
    a, _, _, sa = built("a", workers=1)
    b, _, _, sb = built("b", workers=8)                     # 8 workers asked: the engine starts one per day of a block at most (5 here)
    c, _, _, sc = built("c", workers=2, block=2)            # the same pass cut into blocks of 2 days
    assert sb["passes"] == sc["passes"] == [KEYS] and [sorted(x["days"]) for x in sb["calls"]] == [DAYS]
    assert [sorted(x["days"]) for x in sc["calls"]] == [DAYS[:2], DAYS[2:4], DAYS[4:]]
    assert [x["workers"] for x in sa["calls"]] == [1] and [x["workers"] for x in sb["calls"]] == [8] and [x["workers"] for x in sc["calls"]] == [2] * 3
    bad = {(how, k): differs(a / k, o / k) for how, o in (("8 workers", b), ("day blocks", c)) for k in KEYS}
    assert not any(bad.values()), bad
    n = sum(int(c["trades"]) for k in KEYS for c in json.loads((a / k / "run.json").read_text())["cells"])
    assert n > 500
    RESULTS["test_one_worker_against_eight_and_day_blocks_give_identical_stores"] = (len(KEYS), len(KEYS), f"stores, {n:,} trades")


def test_the_new_stores_equal_the_stores_on_disk():
    o = built("a", workers=1)[0]
    RC, ords = _rc(), np.array([dt.date.fromisoformat(d).toordinal() for d in OLD])
    last = dt.date.fromisoformat(DAYS[-1]).toordinal()
    cells = trades = 0

    def fields(new, old, cid, sess):                         # every packed field of one cell, one session, the four old days
        x, y = LB.unit_cell(new, cid), LB.unit_cell(old, cid)
        mx, my = (np.isin(z["date"], ords) & ((z["sess"] == LB.SESS_CODE[sess]) if sess else True) for z in (x, y))
        return [k for k in LB.FIELDS if not np.array_equal(x[k][mx], y[k][my], equal_nan=True)]

    # the unit against runs/orb-NQ-tf15, session by session (the old store holds all seven sessions of each cell)
    new, old = LB.load_unit(KEYS[1], o), LB.load_unit("orb-NQ-tf15")
    ids = [c["id"] for c in new["meta"]["cells"]]
    for sess in SPEC["sessions"]:
        grid, res = bare(new, ids, sess)
        for r in res:
            r["trades"] = [t for t in r["trades"] if t["entry_ms"] < S.et_ns(dt.date(2025, 1, 1), "00:00") // 1_000_000]
        k, n, diff = RC._same(grid, res, old, OLD, sess, True)
        assert (k, diff) == (len(ids), 0) and n >= len(ids) * 3, (sess, k, n, diff)
        assert not any(fields(new, old, c, sess) for c in ids)
        cells, trades = cells + k, trades + n
    # the pool: seeds 1 and 2 against runs/c1-NQ-tf15 (all sessions), seeds 3 .. 10 against the extra seeds of runs_seeds/ (mid)
    new = LB.load_unit(KEYS[0], o)
    for old, seeds, sess in ((LB.load_unit("c1-NQ-tf15"), (1, 2), None), (LB.load_unit("c1-NQ-tf15-mid-build-s3to10", W / "runs_seeds"), range(3, 11), "mid")):
        ids = [f"s{sd}_{x}" for sd in seeds for x in CELLS]
        grid, res = bare(new, ids, sess)
        for r in res:
            r["trades"] = [t for t in r["trades"] if t["entry_ms"] < S.et_ns(dt.date(2025, 1, 1), "00:00") // 1_000_000]
        k, n, diff = RC._same(grid, res, old, OLD, sess, sess is not None)
        assert (k, diff) == (len(ids), 0) and n >= len(ids) * 4, (k, n, diff)
        assert not any(fields(new, old, c, sess) for c in ids)
        cells, trades = cells + k, trades + n
    # the new range: the last build day is run, and nothing after it is in a store
    for key in KEYS:
        u = LB.load_unit(key, o)
        assert set(np.unique(u["date"]).tolist()) <= set(ords.tolist()) | {last}
    assert (new["date"] == last).sum() > 0 and new["entry_ms"].max() < S.et_ns(dt.date(2025, 6, 30), "17:00") // 1_000_000
    RESULTS["test_the_new_stores_equal_the_stores_on_disk"] = (cells, cells, f"cell-sessions, {trades} stored trades on {len(OLD)} days")


def test_a_rerun_does_no_work_and_other_inputs_are_never_written_over():
    o, led, rows, _ = built("a", workers=1)
    stamp = {k: (o / k / "cells.npz").stat().st_mtime_ns for k in KEYS}
    with watch() as seen, at(SAT), no_engine():                                 # the same inputs: every store is skipped, no tape is opened
        again = RUN.run_build(SPEC, out_dir=o, ledger=led, days=DAYS, cells=CELLS, workers=8)
    assert seen["passes"] == [] and [(r["key"], r["skipped"]) for r in again] == [(k, True) for k in KEYS] and len(LB.read_ledger(led)) == 3
    assert [r["inputs_hash"] for r in again] == [r["inputs_hash"] for r in rows]
    with at(dt.datetime(2026, 10, 6, 9, 20, tzinfo=S.ET)), no_engine():           # nothing to do: the no-start window does not matter
        assert all(r["skipped"] for r in RUN.run_build(SPEC, out_dir=o, ledger=led, days=DAYS, cells=CELLS))
    # a store whose ledger row is missing is booked again, not run again
    led2 = tmp() / "ledger_again.csv"
    with at(SAT), no_engine():
        RUN.run_build(SPEC, out_dir=o, ledger=led2, days=DAYS, cells=CELLS)
    assert ledger(led2) == ledger(led)
    # other inputs under the same name: refused, the stores stay as they are
    with at(SAT), no_engine():
        for other in (dict(cells=CELLS[:1]), dict(days=DAYS[:3]), dict(spec={**SPEC, "params": {"or_min": ["5", "15"]}}),
                      dict(spec={**SPEC, "sessions": ["nyam"]}), dict(spec={**SPEC, "limits": {"max_tr": 1}})):
            kw = {"spec": SPEC, "days": DAYS, "cells": CELLS, **other}
            word = refused(lambda kw=kw: RUN.run_build(kw["spec"], out_dir=o, ledger=led, days=kw["days"], cells=kw["cells"]), "other inputs")
            assert f"{o.name}/" in word
    assert {k: (o / k / "cells.npz").stat().st_mtime_ns for k in KEYS} == stamp and len(LB.read_ledger(led)) == 3
    # a run on named days never goes to runs_bp/ or to the real ledger
    with no_engine():
        refused(lambda: RUN.run_build(SPEC, days=DAYS, cells=CELLS), "named days")
        refused(lambda: RUN.run_build(SPEC, out_dir=o, days=DAYS), "named days")
        refused(lambda: RUN.run_build(SPEC, out_dir=o, ledger=led, cells=CELLS), "named days")


def test_a_store_whose_table_grew_keeps_its_cells_and_gets_the_new_ones():
    """BLUEPRINT.md version 1.1: the exit table got the small targets. A store that holds the cells of the table as it was
    is not another store: its missing cells are run, in one pass, and joined to it; what it held stays byte for byte."""
    o, led, small = tmp() / "runs_grow", tmp() / "ledger_grow.csv", ["atr3-r0p5", "pts20-r0p75"]      # 2 of the 16 small-target cells
    with at(SAT):
        first = RUN.run_build(SPEC, out_dir=o, ledger=led, days=DAYS, cells=CELLS, workers=1)          # the table as it was
    was = {k: LB.load_unit(k, o) for k in KEYS}
    with watch() as seen, at(SAT):
        grown = RUN.run_build(SPEC, out_dir=o, ledger=led, days=DAYS, cells=CELLS + small, workers=1)
    assert len(seen["passes"]) == 1 and [(r["key"], r["skipped"], r["ok"]) for r in grown] == [(k, False, True) for k in KEYS]
    assert [r["grown"] for r in grown] == [20, 6, 6] and [r["cells"] for r in grown] == [40, 12, 12]   # 10 seeds x 2 · 3 values x 2 · the same with the filter
    assert seen["calls"][0]["specs"] < sum(len(x) for p in RUN.parts(RUN.checked(SPEC), CELLS + small) for x in p["runs"])     # the missing cells only
    with at(SAT):
        whole = RUN.run_build(SPEC, out_dir=tmp() / "runs_grow_whole", ledger=tmp() / "ledger_grow_whole.csv", days=DAYS, cells=CELLS + small, workers=1)
    assert [r["inputs_hash"] for r in grown] == [r["inputs_hash"] for r in whole] != [r["inputs_hash"] for r in first]
    for k, a in zip(KEYS, first):
        u, w, doc = LB.load_unit(k, o), LB.load_unit(k, tmp() / "runs_grow_whole"), F_read(o / k / "run.json")
        n = len(was[k]["meta"]["cells"])
        assert [c["id"] for c in u["meta"]["cells"]][:n] == [c["id"] for c in was[k]["meta"]["cells"]] and u["meta"]["cells"][:n] == was[k]["meta"]["cells"]
        assert all(np.array_equal(u[f][:len(was[k][f])], was[k][f]) for f in LB.FIELDS) and np.array_equal(u["off"][:n + 1], was[k]["off"])      # what it held: untouched
        assert {c["id"] for c in u["meta"]["cells"]} == {c["id"] for c in w["meta"]["cells"]} and len(u["off"]) == len(u["meta"]["cells"]) + 1
        for c in w["meta"]["cells"]:                                                # every cell, old and new: the trades of a store run whole
            x, y = LB.unit_cell(u, c["id"]), LB.unit_cell(w, c["id"])
            assert all(np.array_equal(x[f], y[f], equal_nan=f in ("mae", "risk")) for f in LB.FIELDS), (k, c["id"])
        assert {c["id"]: (c["vi"], c["xi"], c["exit"], c["trades"]) for c in u["meta"]["cells"]} == {c["id"]: (c["vi"], c["xi"], c["exit"], c["trades"]) for c in w["meta"]["cells"]}
        assert doc["inputs_hash"] == grown[KEYS.index(k)]["inputs_hash"] and [(g["cells"], g["from"], g["was"]) for g in doc["grown"]] == [(len(u["meta"]["cells"]) - n, n, a["inputs_hash"])]
        assert (o / k / "table.csv").exists() and not (o / (k + ".tmp")).exists()
    rows = LB.read_ledger(led)
    assert [(r["stage"], r["key"]) for r in rows] == [("null_bp", KEYS[0]), ("bp_build", KEYS[1]), ("bp_build", KEYS[2]),
                                                     ("null_bp_more", KEYS[0]), ("bp_build_more", KEYS[1]), ("bp_build_more", KEYS[2])]
    assert [int(r["cells"]) + int(r["null_cells"]) for r in rows[3:]] == [20, 6, 6]              # only the new cells are booked, the pool's as null cells
    with watch() as seen, at(SAT), no_engine():                                    # grown: now it is the store asked for
        assert all(r["skipped"] for r in RUN.run_build(SPEC, out_dir=o, ledger=led, days=DAYS, cells=CELLS + small)) and seen["passes"] == []
    with at(SAT), no_engine():                                                     # fewer cells than it holds, or other days: still another store
        refused(lambda: RUN.run_build(SPEC, out_dir=o, ledger=led, days=DAYS, cells=CELLS), "other inputs")
        refused(lambda: RUN.run_build(SPEC, out_dir=o, ledger=led, days=DAYS[:3], cells=CELLS + small + ["pct0p1-r0p5"]), "other inputs")


def F_read(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_what_stops_a_run_and_what_a_failed_pass_leaves():
    import fcntl
    import run_idea as RI
    a, led_a, _, _ = built("a", workers=1)
    o, led = tmp() / "runs_stop", tmp() / "ledger_stop.csv"
    kw = dict(out_dir=o, ledger=led, days=DAYS, cells=CELLS)
    # ONE run at a time per STORE (since 2026-10-07: runs of other ideas go side by side); a reader of what is stored never waits for it
    o.mkdir()
    units = [q["key"] for q in RUN.parts(RUN.checked(SPEC), CELLS) if q["kind"] != "pool"]
    with open(o / f"{units[0]}.lock", "w") as held, open(a / f"{units[0]}.lock", "w") as held_a:
        fcntl.flock(held, fcntl.LOCK_EX)
        fcntl.flock(held_a, fcntl.LOCK_EX)
        with at(SAT), no_engine():
            refused(lambda: RUN.run_build(SPEC, **kw), "another run is writing")
            refused(lambda: RUN.run_build(SPEC, dry=True, **kw), "another run is writing")       # ... so no job is started into it
            assert all(r["skipped"] for r in RUN.run_build(SPEC, out_dir=a, ledger=led_a, days=DAYS, cells=CELLS))
    # the candidate cells of an idea count against the ledger's cap (a pool's do not): refused as a whole, before any pass
    LB.ledger_add("build", "filler", "grid", cells=RI.CAPS["cells"] - RM.PAPER_CELLS - 11, path=led, caps=RI.CAPS)
    with at(SAT), no_engine():
        refused(lambda: RUN.run_build(SPEC, **kw), "cap")                       # 12 cells asked, 11 left
        assert [r["ok"] for r in RUN.run_pools(["NQ"], ["15"], dry=True, **kw)] == [None]       # a pool alone still fits
    assert not list(o.glob("*/run.json")) and len(LB.read_ledger(led)) == 1
    # a pass that dropped a session by a strategy error writes NO store: an error row in the ledger, the key stays to be run
    o2, led2 = tmp() / "runs_err", tmp() / "ledger_err.csv"
    keep = RUN._pass

    def broken(parts, *a_, **k_):
        res = keep(parts, *a_, **k_)
        for r in [r for part, rs in zip(parts, res) if part["key"] == KEYS[1] for r in rs]:      # the unit's cells: a session dropped by a crash in the family
            r["skipped_by_error"], r["no_trade"] = 1, [{"date": DAYS[0], "reason": f"{S.ERROR_PREFIX}: ValueError: planted"}]
        return res

    try:
        RUN._pass = broken
        with at(SAT):
            rows = RUN.run_build(SPEC, out_dir=o2, ledger=led2, days=DAYS, cells=CELLS, workers=1)
    finally:
        RUN._pass = keep
    assert [(r["key"], r["ok"]) for r in rows] == [(KEYS[0], True), (KEYS[1], False), (KEYS[2], True)] and "planted" in rows[1]["error"]
    assert sorted(x.parent.name for x in o2.glob("*/run.json")) == sorted([KEYS[0], KEYS[2]])
    assert [(x["stage"], x["key"], x["kind"], int(x["cells"])) for x in LB.read_ledger(led2)] == \
        [("null_bp", KEYS[0], "null", 0), ("bp_build_error", KEYS[1], "grid", 6), ("bp_build", KEYS[2], "grid", 6)]
    with at(SAT), no_engine():                              # the build says so and reads no line off half an idea
        try:
            RUN._pass = lambda *a_, **k_: (_ for _ in ()).throw(AssertionError("run again"))
            assert [r["skipped"] for r in RUN.run_build(SPEC, out_dir=o2, ledger=led2, days=DAYS, cells=CELLS, dry=True)] == [True, False, True]
        finally:
            RUN._pass = keep
    with at(SAT):
        try:
            RUN._pass = broken
            refused(lambda: A.build(SPEC, reason=REASON, out=o2, ledger=led2, days=DAYS, cells=CELLS, workers=1), "strategy error")
        finally:
            RUN._pass = keep
    assert len(LB.read_ledger(led2)) == 4 and LB.read_ledger(led2)[-1]["stage"] == "bp_build_error"


# ================================================================ (c) the seal

def test_nothing_on_or_after_2025_07_01_is_read():
    rg = R.template("ranges")
    assert RUN.PERIOD == S.ALLOW_BP == "bp_build" and (rg["build"]["start"], rg["build"]["end"]) == tuple(d.isoformat() for d in S.BP_BUILD)
    assert rg["test"]["start"] == "2025-07-01" and RUN.RUNS == W / "runs_bp" and RUN.STAGE == {"unit": "bp_build", "pool": "null_bp"}
    o, led = tmp() / "runs_seal", tmp() / "ledger_seal.csv"
    with no_engine(), at(SAT):                                                  # refused BEFORE anything is read
        for days in (DAYS + ["2025-07-01"], ["2025-07-01"], ["2025-12-31"], ["2026-09-22"], ["2021-09-21"], ["2025-06-30", "2025-07-02"]):
            refused(lambda days=days: RUN.run_build(SPEC, out_dir=o, ledger=led, days=days, cells=CELLS), "2025-06-30")
            refused(lambda days=days: RUN.run_pools(["NQ"], ["15"], out_dir=o, ledger=led, days=days, cells=CELLS), "2025-06-30")
        assert RUN.seal(["2021-09-22", "2025-06-30"]) == ["2021-09-22", "2025-06-30"] and not led.exists() and not list(o.glob("*/run.json"))
    # every engine call of a real run: the build switch by its name, the named days, no other switch
    calls = built("a", workers=1)[3]["calls"] + built("b", workers=8)[3]["calls"] + built("c", workers=2, block=2)[3]["calls"]
    assert len(calls) == 5
    for c in calls:
        assert c["period"] == "bp_build" and c["root"] == "NQ" and set(c["days"]) <= set(DAYS) and c["args"] == ()
        assert not any(c.get(k) for k in ("allow_holdout", "allow_exam", "allow_check", "start", "end", "features", "costs", "slip_ticks", "latency_ms"))
    with no_engine():                                                           # the engine itself would refuse too
        try:
            S.check_holdout("2025-07-01", RUN.PERIOD)
            raise AssertionError("the engine's seal is open")
        except S.HoldoutSealed:
            pass
    # a store whose range ends after 2025-06-30: refused by the runner (it is not skipped, not read) and by the reader
    a = built("a", workers=1)[0]
    late = tmp() / "runs_late"
    shutil.copytree(a, late)
    m = json.loads((late / KEYS[1] / "run.json").read_text())
    (late / KEYS[1] / "run.json").write_text(json.dumps({**m, "range": {**m["range"], "end": "2025-12-31"}}))
    with no_engine(), at(SAT):
        refused(lambda: RUN.run_build(SPEC, out_dir=late, ledger=led, days=DAYS, cells=CELLS), "2025-06-30")
        refused(lambda: T.built(RUN.checked(SPEC), out_dir=late, days=DAYS), "2025-06-30")
    for bad in ({"range": {"start": "2021-09-22", "end": "2025-07-01"}}, {"range": {"start": "2025-01-01", "end": "2025-12-31"}},
                {"range": {"start": "2026-01-01", "end": "2026-09-30"}}, {"range": None}, {}, {"range": {"start": "", "end": ""}},
                {"range": {"start": "2021-01-04", "end": "2023-12-31"}}):
        refused(lambda bad=bad: RUN.guard(bad, "x/y"), "2025-06-30")
    assert RUN.guard(m, "x/y") is m and RUN.guard({"range": {"start": "2021-09-22", "end": "2023-12-31"}}, "x/y")
    # ... and a store that holds a trade dated after the range, whatever its run.json says
    lie = tmp() / "runs_lie"
    shutil.copytree(a, lie)
    z = dict(np.load(lie / KEYS[1] / "cells.npz"))
    z["date"][-1] = dt.date(2025, 7, 1).toordinal()
    np.savez_compressed(lie / KEYS[1] / "cells.npz", **z)
    with at(SAT):
        refused(lambda: T.built(RUN.checked(SPEC), out_dir=lie, days=DAYS), "dated after")


def test_specs_the_build_range_cannot_run_are_refused():
    with no_engine():
        refused(lambda: RUN.checked({**SPEC, "exits": "extended"}), "standard")
        RUN.checked({**SPEC, "filters": [{"block": "book", "side": "agree"}]})                          # Level 2 on NQ is taken (built, locked and tested)
        refused(lambda: RUN.checked({**SPEC, "markets": ["NQ", "ES"], "filters": [{"block": "book", "side": "agree"}]}), "NQ only")
        assert RUN.checked({**SPEC, "family": "va_reclaim", "params": {"d_atr": [0.25, 0.5]}})["family"] == "va_reclaim"          # taken: its cache is built per range
        refused(lambda: RUN.checked({**SPEC, "end": "2025-07-01"}), "unknown fields")
        refused(lambda: RUN.checked({**SPEC, "family": "no_such_family"}), "family")
        refused(lambda: RUN.checked({k: v for k, v in SPEC.items() if k != "reason"}), "reason")
        refused(lambda: RUN.checked(["not", "a", "spec"]), "JSON object")
    sp = RUN.checked(SPEC)
    assert sp["name"] == "bpt_orb" and sp["filters"] == [("momentum", "with")] and len(sp["variants"]) == 3
    assert RUN.checked(sp) is sp                                                # run_idea's check is not run twice ...
    assert (sp["exits"], sp["filter_exits"]) == ("blueprint", "blueprint") and SPEC["exits"] == "standard"      # the card's "standard" is the blueprint's 48-cell table; the caller's spec stays
    refused(lambda: RUN.checked({**sp, "exits": "extended"}), "standard")       # ... but what the build range cannot run is refused however the spec came
    path = tmp() / "any_name.json"                                              # a spec file may have any name (the idea's record names it)
    path.write_text(json.dumps(SPEC))
    assert RUN.checked(path)["name"] == "bpt_orb" and RUN.checked(str(path))["variants"] == sp["variants"]
    refused(lambda: RUN.checked(tmp() / "missing.json"), "missing.json")


# ================================================================ (d) the lines on the new range

def test_the_random_tables_are_the_judges_from_a_hand_built_seed_map():
    """The judge finds control seeds through its own index of the four old periods; a store of the new range is outside all
    of them, so the toolkit hands judge.c1_table a seed map it builds itself. On the OLD stores both ways are open: the
    hand-built map must give judge.controls' numbers, draw for draw."""
    with rule(draws=200):
        u = J.unit("first_bar_mom-NQ-tf15-mid")
        st, _ = J.build_store(u)
        ts = J.table_stats(J.table(st, u))
        ref = J.controls(st, u, ts, "build")["c1"]
        need = sorted({i.rsplit("_", 1)[-1] for i in ts["ids"]})
        a, b = T.pool_seeds(W / "runs", "c1-NQ-tf15", need), T.pool_seeds(W / "runs_seeds", "c1-NQ-tf15-mid-build-s3to10", need)
        assert (sorted(a), sorted(b)) == ([1, 2], list(range(3, 11))) and a[1][1] == "s1_" and b[10][1] == "s10_"
        mine = T.against_random(st, u, ts, {**a, **b}, "build-c1")
        two = T.against_random(st, u, ts, a, "build-c1")
    assert ref["seeds"] == mine["seeds"] == list(range(1, 11)) and mine["real_replicates"] == 10 and mine["thin"] is False
    assert mine == {k: ref[k] for k in mine} and set(ref) - set(mine) == {"two_seed"}, (mine, ref)
    assert {k: two[k] for k in ("pass", "lift", "p_beat")} == ref["two_seed"] and two["thin"] is True and two["seeds"] == [1, 2]
    # fewer seeds than the law asks: the build refuses (the old 2-seed pool is not a blueprint pool)
    with rule(draws=200):
        refused(lambda: T.pool_seeds(W / "runs", "c1-NQ-tf15", need, R.template("control")["seeds"]), "2 of the 10 seeds")
    assert sorted(T.pool_seeds(built("a", workers=1)[0], KEYS[0], CELLS, 10)) == list(range(1, 11))


def _run(argv: list) -> tuple:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = C.main(argv)
    return rc, out.getvalue()


def test_build_prints_the_lines_on_the_new_range():
    from blueprint import lines as L
    o, led, _, _ = built("a", workers=1)
    kw = dict(reason=REASON, out=o, ledger=led, days=DAYS, cells=CELLS)
    with rule(draws=200), at(SAT), no_engine():             # everything is stored: the lines are read, nothing runs
        r = A.build(SPEC, **kw)                              # the home = the spec's first market, bar size and session
        f = A.build(SPEC, name="bpt_orb", home="NQ-tf15-mid", filt="momentum_with", round_=2, **kw)
        t = T.built(RUN.checked(SPEC), out_dir=o, days=DAYS)
    assert list(r)[:len(CONTRACT)] == list(CONTRACT)
    assert [r[k] for k in ("ok", "command", "name", "status", "phase", "round", "job", "saved", "error")] == [True, "build", "bpt_orb", None, 2, 1, None, [], None]
    assert (r["unit"], r["home"], r["filter"], r["reason"], r["spec"]) == ("bpt_orb-NQ-tf15-nyam", "NQ-tf15-nyam", None, REASON, "bpt_orb")
    assert r["smoke"] is True and r["dry_run"] is True      # a run on named days never counts (the idea store reads `dry_run`)
    assert [x["line"] for x in r["lines"]] == ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9"] == [x["line"] for x in f["lines"]]
    assert all(set(x) >= {"line", "passed", "number", "need", "text"} and x["text"].startswith(x["line"] + " ") for x in r["lines"])
    assert r["lines"] == [fn({**t, "reason": REASON}) for fn in (*L.BUILD, L.rounds)]       # the line functions of the dry run, + 2.9
    assert json.loads(json.dumps(r, default=lambda x: 1 / 0)) == json.loads(json.dumps(r))      # JSON-ready as it is
    assert r["days"] == {"start": "2021-09-22", "end": "2025-06-30", "months": 45, "sessions": 5, "named": DAYS}
    assert r["table"] == {"store": f"{o.name}/{KEYS[1]}", "variants": 6, "dead": 0, "duplicates": 0}
    assert [(s["key"], s["skipped"]) for s in r["stores"]] == [(k, True) for k in KEYS]
    by = {x["line"]: x for x in r["lines"]}
    # 2.1, 2.2, 2.4, 2.6 straight from the store's own trades in the home session
    u = LB.load_unit(KEYS[1], o)
    xs = [LB.unit_cell(u, c["id"]) for c in u["meta"]["cells"]]
    xs = [{k: v[x["sess"] == LB.SESS_CODE["nyam"]] for k, v in x.items()} for x in xs]
    net, n = np.array([float(x["net"].sum()) for x in xs]), np.array([len(x["net"]) for x in xs])
    assert by["2.1"]["number"] == float((net > 0).mean()) and by["2.1"]["variants"] == 6 and by["2.4"]["number"] == float(n.mean())
    assert abs(by["2.2"]["number"] - net.sum() / n.sum()) < 1e-9 and "on_pace" not in by["2.4"]
    assert (by["2.6"]["n_long"] + by["2.6"]["n_short"]) == int(n.sum()) == int(t["n"].sum()) and t["net"].shape == (6, 5)
    # 2.3: the judge's random tables from the pool's 10 seeds; 2.5: the spec's other table; 2.7: no filter in the plain unit
    c1 = by["2.3"]["controls"]["c1"]
    assert (by["2.3"]["seeds"], by["2.3"]["thin"], by["2.3"]["round"], by["2.3"]["need"]) == (10, False, 1, 0.95)
    assert c1["seeds"] == list(range(1, 11)) and c1["stores"] == {f"{o.name}/{KEYS[0]}": list(range(1, 11))} and c1["replicates"] == 200
    assert (by["2.5"]["tables"], by["2.7"]["passed"], by["2.8"]["runs"]) == (1, None, 1000) and r["not_applicable"] == ["2.7"]
    assert r["failed"] == [x["line"] for x in r["lines"] if x["passed"] is False] and r["passed"] is (not r["failed"])
    # 2.9: the round and its reason, written before the run
    assert by["2.9"] == {"line": "2.9", "passed": True, "number": 1, "need": 5, "reason": REASON,
                         "text": f"2.9 PASS round 1 of at most 5, its reason written before the run: {REASON}"}
    assert L.rounds({"round": 5, "reason": "x"})["passed"] is True and L.rounds({"round": 1})["passed"] is False
    assert L.rounds({"round": 2, "reason": "  "})["text"] == "2.9 FAIL round 2 of at most 5: no reason was written before the run"
    refused(lambda: L.rounds({"round": 6, "reason": "x"}), "6")
    # the filter unit in round 2: held against the plain table (2.7) and against the bar of its round
    by = {x["line"]: x for x in f["lines"]}
    assert (f["unit"], f["home"], f["filter"], f["round"]) == ("bpt_orb__momentum_with-NQ-tf15-mid", "NQ-tf15-mid", "momentum_with", 2)
    assert f["table"]["store"] == f"{o.name}/{KEYS[2]}" and by["2.3"]["need"] == 0.975 and by["2.3"]["round"] == 2 and by["2.9"]["number"] == 2
    assert by["2.7"]["passed"] is not None and by["2.7"]["filters"][0]["name"] == "filter momentum with against the plain version"
    assert set(by["2.7"]["filters"][0]) == {"name", "avg_trade", "plain_avg_trade", "p_beat"} and f["not_applicable"] == []
    # text: no DRY RUN label; a run on named days says so and is never a verdict
    lines = r["text"].split("\n")
    assert "DRY RUN" not in r["text"] and lines[0] == "SMOKE RUN on 5 named days of the build range (2021-09-22 .. 2025-06-30): never a blueprint verdict."
    assert lines[1] == f"bpt_orb-NQ-tf15-nyam · round 1 · 6 variants · 5 session days · store {o.name}/{KEYS[1]}"
    assert lines[2:11] == [x["text"] for x in r["lines"]] and lines[11].startswith("RESULT of the smoke run: ") and len(lines) == 12
    assert A.headline({"start": "2021-09-22", "end": "2025-06-30", "months": 45, "sessions": 948, "named": None}) == \
        "BUILD 2021-09-22 .. 2025-06-30 (45 months, 948 session days)."
    # the command line as the connector writes it (--opt=value, the idea's name first): text, and ONE JSON object; refusals exit 2
    spec = tmp() / "spec.json"
    spec.write_text(json.dumps(SPEC))
    argv = ["build", "bpt_orb", f"--spec-file={spec}", f"--reason={REASON}", f"--out={o}", f"--ledger={led}", "--days=" + ",".join(DAYS), "--cells=" + ",".join(CELLS)]
    with rule(draws=200), at(SAT), no_engine():
        rc, txt = _run(argv)
        rj, js = _run(argv + ["--home=NQ-tf15-mid", "--filter=momentum_with", "--round=2", f"--root={tmp() / 'ideas'}", "--json"])
        assert rc == 0 and txt.rstrip("\n") == r["text"] and rj == 0 and json.loads(js) == json.loads(json.dumps(f)) and js.count("\n") == 1 and js.isascii()
        n = 0
        for more, word in ((["--home=ES-tf15-nyam"], "not a table of the spec"), (["--home=NQ-tf15-pm"], "not a table of the spec"),
                           (["--home=nonsense"], "<ROOT>-tf<tf>-<session>"), (["--filter=news_yes"], "not a filter of the spec"),
                           (["--round=6"], "6"), (["--round=0"], "0"), (["--workers=0"], "workers"), (["--no-such-option"], "unrecognized"),
                           (["--reason= "], "--reason"), (["--stored=x"], "not both")):
            rc, js = _run(argv + more + ["--json"])
            d = json.loads(js)
            assert rc == 2 and list(d) == list(CONTRACT) and d["ok"] is False and word in d["error"] and (d["lines"], d["job"], d["command"]) == ([], None, "build"), d
            n += 1
        gone = [x for x in argv if not x.startswith("--reason")]
        for argv2, word in ((gone, "--reason"), (["build", "bpt_orb", f"--reason={REASON}"], "--spec-file"), (["build"], "the idea's name"),
                            (["build", "bpt_orb", f"--spec-file={tmp() / 'none.json'}", f"--reason={REASON}"], "none.json"),
                            (["build", "other_idea"] + argv[2:], "bpt_orb"), (argv[:4] + ["--days=" + ",".join(DAYS)], "named days"),
                            (argv + ["--days=2025-07-01"], "2025-06-30")):
            rc, txt = _run(argv2)
            assert rc == 2 and txt.startswith("REFUSED: ") and word in txt, (argv2, txt)
            n += 1
    assert not (tmp() / "ideas").exists()                   # a build in the foreground makes no job and no idea folder
    RESULTS["test_build_prints_the_lines_on_the_new_range"] = (2 + n, 2 + n, "2 units through the lines, the refusals")


def test_the_control_pools_command():
    keys = [f"c1-{r}-tf{tf}" for r in ("NQ", "ES", "GC") for tf in ("1", "5", "15", "30")]
    parts = [RUN.pool_part(r, tf) for r in ("NQ", "ES", "GC") for tf in ("1", "5", "15", "30")]
    assert [p["key"] for p in parts] == keys and all(p["cells"] == 480 and p["kind"] == "pool" and p["sessions"] == list(RM.DAY_PASSES) for p in parts)
    assert all([c["exit"] for c in p["grid"][:32]] + [c["exit"] for c in p["grid"][320:336]] == R.exit_menu(p["root"]) for p in parts)
    o, led, _, _ = built("a", workers=1)
    with watch() as seen, at(SAT), no_engine():             # the pool the tiny build wrote is the one later ideas reuse: nothing runs
        r = A.pools(["NQ"], ["15"], out=o, ledger=led, days=DAYS, cells=CELLS)
    assert seen["passes"] == [] and r["ok"] and r["command"] == "pools" and r["saved"] == [] and [(s["key"], s["skipped"]) for s in r["stores"]] == [(KEYS[0], True)]
    assert list(r)[:len(CONTRACT)] == list(CONTRACT) and "c1-NQ-tf15: already stored" in r["text"]
    with no_engine():
        refused(lambda: A.pools(["NQ", "CL"], ["15"], out=o, ledger=led, days=DAYS, cells=CELLS), "CL")
        refused(lambda: A.pools(["NQ"], ["7"], out=o, ledger=led, days=DAYS, cells=CELLS), "7")
        rc, txt = _run(["pools", "--roots", "NQ", "--tf", "15", "--out", str(o), "--ledger", str(led), "--days", "2025-07-01", "--cells", CELLS[0]])
    assert rc == 2 and "2025-06-30" in txt


# ================================================================ (e) jobs

def bp(argv: list, **env) -> tuple:
    """The front door as the connector starts it: bp.py in its own process, in its own folder, stdin closed -> (exit code,
    the one JSON object)."""
    q = subprocess.run([sys.executable, str(W / "bp.py"), *argv], capture_output=True, text=True, timeout=600, cwd=str(W),
                       stdin=subprocess.DEVNULL, env={**os.environ, **env})
    assert q.stdout.count("\n") == 1, (q.stdout[-600:], q.stderr[-1200:])
    return q.returncode, json.loads(q.stdout)


def test_the_job_flow():
    if S.compute_window_end() is not None:
        import pytest
        pytest.skip("no heavy run starts 09:18-09:36 ET on weekdays")
    root, o, led, spec = tmp() / "ideas_job", tmp() / "runs_job", tmp() / "ledger_job.csv", tmp() / "job_spec.json"
    spec.write_text(json.dumps(SPEC))
    head = ["build", "bpt_orb", f"--spec-file={spec}", f"--reason={REASON}"]
    more = [f"--out={o}", f"--ledger={led}", "--days=" + ",".join(DAYS), "--cells=" + ",".join(CELLS), "--workers=2"]
    last = [f"--root={root}", "--json"]                     # the connector's shape: --root and --json come last
    # a refusal comes back at once and never as a job
    rc, d = bp([*head, "--wait=0", *more[:2], "--days=2025-06-30,2025-07-01", *more[3:], *last])
    assert rc == 2 and d["ok"] is False and d["job"] is None and "2025-06-30" in d["error"] and not root.exists()
    # start with no wait: the answer is the job, the work goes on in a detached child
    rc, d = bp([*head, "--wait=0", *more, *last])
    assert rc == 0 and list(d) == list(CONTRACT) and (d["ok"], d["command"], d["name"], d["phase"], d["round"], d["lines"], d["error"]) == (True, "build", "bpt_orb", 2, 1, [], None)
    jid = d["job"]["id"]
    jd = root / "_jobs" / jid                               # every job in ONE folder: `job <id>` gets no name, and no idea folder is made
    assert d["job"]["state"] in ("queued", "running") and set(d["job"]) == {"id", "state", "progress"} and jid in d["next"] and jid in d["text"]
    assert json.loads((jd / "job.json").read_text())["command"] == "build" and json.loads((jd / "spec.json").read_text()) == SPEC
    assert sorted(x.name for x in root.iterdir()) == ["_jobs"]
    # pick the wait back up until it is done: by the id alone (the root may also come from the environment)
    for _ in range(30):
        rc, d = bp(["job", jid, "--wait=20", "--json"], HOMEBASE_IDEAS_ROOT=str(root))
        if d["job"]["state"] not in ("queued", "running"):
            break
    assert rc == 0 and d["job"]["state"] == "done" and d["job"]["id"] == jid and d["ok"] and d["command"] == "build" and d["name"] == "bpt_orb", d
    assert [x["line"] for x in d["lines"]] == ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9"] and d["unit"] == "bpt_orb-NQ-tf15-nyam"
    assert sorted(d["saved"]) == sorted(str(o / k) for k in KEYS) and all((Path(p) / "cells.npz").exists() for p in d["saved"])
    job = json.loads((jd / "job.json").read_text())
    assert job["state"] == "done" and job["exit"] == 0 and (jd / "result.json").exists() and (jd / "log.txt").exists()
    assert json.loads((jd / "result.json").read_text()) == d and len(LB.read_ledger(led)) == 3
    a = built("a", workers=1)[0]
    assert not any(differs(a / k, o / k) for k in KEYS)       # the child's stores are the stores of the direct run
    by = {x["line"]: x for x in d["lines"]}
    assert by["2.3"]["seeds"] == 10 and by["2.3"]["controls"]["c1"]["replicates"] == R.template("control")["draws"] == 4000
    assert by["2.9"]["reason"] == REASON and d["dry_run"] is True and d["smoke"] is True
    # asked again (the status tool sends --wait=0): the same answer; a second build with a long wait finds everything
    # stored and is done inside the wait
    rc, again = bp(["job", jid, "--wait=0", *last])
    assert rc == 0 and again == d
    rc, d2 = bp([*head, "--wait=300", *more, *last])
    assert rc == 0 and d2["job"]["state"] == "done" and d2["job"]["id"] != jid and d2["saved"] == [] and d2["lines"] == d["lines"]
    assert len(list((root / "_jobs").iterdir())) == 2
    # without --wait the command works in the foreground: no job
    rc, d3 = bp([*head, *more, *last])
    assert rc == 0 and d3["job"] is None and d3["lines"] == d["lines"] and len(list((root / "_jobs").iterdir())) == 2
    # an unknown job is refused; a job whose process is gone is an error (exit 1), not a wait for ever
    for bad in ("nope", "../x", jid + "x"):
        rc, e = bp(["job", bad, "--wait=0", *last])
        assert rc == 2 and e["ok"] is False and e["command"] == "job" and "no job" in e["error"]
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    dead = root / "_jobs" / "20260101T000000-dead00"
    dead.mkdir()
    (dead / "job.json").write_text(json.dumps({**job, "id": dead.name, "state": "running", "pid": gone.pid, "exit": None, "progress": "pass 1 of 1"}))
    rc, e = bp(["job", dead.name, "--wait=5", *last])
    assert rc == 1 and e["ok"] is False and e["job"]["state"] == "error" and e["job"]["id"] == dead.name and "gone" in e["error"] and e["command"] == "build"
    assert _listing(tmp() / "ideas_env") is None and _listing(tmp() / "drafts") is None       # no idea folder, no Lab draft was made
    assert _listing(Path(os.environ["HOMEBASE_IDEAS_ROOT"])) is None and _listing(Path(os.environ["HOMEBASE_DRAFTS_DIR"])) is None
    RESULTS["test_the_job_flow"] = (3, 3, "builds through the front door: one as a job, one done inside its wait, one in the foreground")


def test_the_job_folder_and_its_state():
    root = tmp() / "ideas_unit"
    keep = os.environ.pop("HOMEBASE_IDEAS_ROOT")              # (a temp folder: this module's, or another test module's)
    try:
        assert JOBS.root() == HOME / "ideas" and JOBS.root(root) == root        # the app's own folder (only named here) unless told
        os.environ["HOMEBASE_IDEAS_ROOT"] = str(tmp() / "ideas_env")
        assert JOBS.root() == tmp() / "ideas_env" and JOBS.root(root) == root and JOBS.root(str(root)) == root      # the argument, else the environment
    finally:
        os.environ["HOMEBASE_IDEAS_ROOT"] = keep
    # the child's side, in this process: a command that is refused ends the job as an error with the reason (exit 2)
    d = JOBS.new("build", "bpt_orb", {"spec": {**SPEC, "exits": "extended"}, "reason": REASON, "out": str(tmp() / "x"), "ledger": str(tmp() / "x.csv")}, root, wait=7)
    job = json.loads((d / "job.json").read_text())
    assert (job["state"], job["command"], job["name"], job["wait"], job["id"]) == ("queued", "build", "bpt_orb", 7, d.name) and d.parent == root / "_jobs"
    assert JOBS.work(d) == 2
    job, res = json.loads((d / "job.json").read_text()), json.loads((d / "result.json").read_text())
    assert (job["state"], job["exit"]) == ("error", 2) and res["ok"] is False and "standard" in res["error"] and res["job"]["state"] == "error"
    r = JOBS.wait(d.name, root, 0)
    assert r == res and list(r)[:len(CONTRACT)] == list(CONTRACT) and JOBS.code(r) == 2
    # a command that crashes: the job is an error with the last line of the traceback (exit 1)
    d = JOBS.new("build", "bpt_orb", {"spec": SPEC, "reason": REASON, "no_such_argument": 1}, root, wait=0)
    assert JOBS.work(d) == 1
    r = JOBS.wait(d.name, root, 0)
    assert r["ok"] is False and r["job"]["state"] == "error" and "no_such_argument" in r["error"] and JOBS.code(r) == 1
    assert "Traceback" in (d / "log.txt").read_text()
    for bad in ("20990101T000000-abcdef", "nope", "", "../_jobs/" + d.name):
        refused(lambda bad=bad: JOBS.wait(bad, root, 0), "no job")
    assert JOBS.code({"ok": True}) == 0 and JOBS.code({"ok": False}) == 2 and JOBS.code({"ok": False, "crashed": True}) == 1


# ================================================================ two filters at once

SPEC2 = {**SPEC, "name": "bpt_two", "filters": [{"all": [{"block": "momentum", "side": "with"}, {"block": "news", "side": "no"}]}]}


def test_two_filters_run_alone_and_together_and_line_27_holds_the_pair_against_each():
    """A card that names two filters runs the plain table, each filter alone and both on (one tape pass); line 2.7 compares the pair with
    the plain table and with each filter alone, and each filter alone with the plain table: five comparisons, the pair's name says so."""
    sp = RUN.checked(SPEC2)
    assert sp["filters"] == [("momentum", "with"), ("news", "no"), ("momentum+news", "with+no")]        # the singles are added before the pair
    o, led = tmp() / "runs_two", tmp() / "ledger_two.csv"
    keep = RM.auto_workers
    RM.auto_workers = lambda n=None: n
    try:
        with watch() as seen, at(SAT):
            rows = RUN.run_build(SPEC2, out_dir=o, ledger=led, days=DAYS, cells=CELLS, workers=1)
    finally:
        RM.auto_workers = keep
    keys = sorted(r["key"] for r in rows)
    assert keys == ["bpt_two-NQ-tf15", "bpt_two__momentum+news_with+no-NQ-tf15", "bpt_two__momentum_with-NQ-tf15", "bpt_two__news_no-NQ-tf15", "c1-NQ-tf15"], keys
    assert len(seen["passes"]) == 1 and sorted(seen["passes"][0]) == keys                                # ONE tape pass for all five stores
    with rule(draws=200), at(SAT), no_engine():
        t = T.built(sp, out_dir=o, days=DAYS, filt="momentum+news_with+no")
    names = [f["name"] for f in t["filters"]]
    assert len(names) == 5 and names[0].startswith("both filters momentum with and news no against the plain version"), names
    assert sum("alone against the plain version" in n for n in names) == 2 and sum(n.startswith("both filters against") for n in names) == 2
    from blueprint import lines as L
    row = L.filter_alone({**t, "reason": REASON})
    assert row["line"] == "2.7" and len(row["filters"]) == 5 and row["passed"] in (True, False)
    # the pair's blocks must differ, and at most two
    for bad in ([{"block": "news", "side": "no"}, {"block": "news", "side": "yes"}], [{"block": "news", "side": "no"}, {"block": "momentum", "side": "with"}, {"block": "volume", "side": "high"}]):
        try:
            RUN.checked({**SPEC, "filters": [{"all": bad}]})
            raise AssertionError("a pair of one block, or three filters, must be refused")
        except J.Refuse as e:
            assert "different blocks" in str(e) or "filters of" in str(e), e
    RESULTS["test_two_filters_run_alone_and_together_and_line_27_holds_the_pair_against_each"] = (5, 5, "stores of a two-filter rule, one pass; line 2.7 reads five comparisons")


# ================================================================ nothing outside the temp folder

def test_nothing_was_written_outside_the_temp_folder():
    assert _listing(RUN.RUNS) == BEFORE["runs_bp"], "a test wrote into runs_bp/"
    assert _listing(HOME / "ideas") == BEFORE["ideas"] and _listing(HOME / "strategies") == BEFORE["drafts"], "a test wrote into ~/.homebase"
    assert (LB.LEDGER.stat().st_size, LB.LEDGER.stat().st_mtime_ns) == BEFORE["ledger"], "a test wrote into ledger.csv"


if __name__ == "__main__":
    import time
    rc = 0
    for name, t in [(k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)]:
        t0 = time.monotonic()
        try:
            t()
            ok, n, note = RESULTS.get(name, ("", "", ""))
            print(f"PASS {name}" + (f": {ok} of {n}" if n else "") + (f" -- {note}" if note else "") + f" ({time.monotonic() - t0:.0f} s)", flush=True)
        except AssertionError as e:
            rc = 1
            print(f"FAIL {name} ({time.monotonic() - t0:.0f} s)\n{e}", flush=True)
        except BaseException as e:                          # pytest.skip
            if type(e).__name__ != "Skipped":
                raise
            print(f"SKIP {name} ({e})", flush=True)
    sys.exit(rc)
