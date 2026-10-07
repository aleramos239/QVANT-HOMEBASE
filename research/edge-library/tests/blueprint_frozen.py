"""blueprint_frozen.py -- what the tests of the freeze (test_blueprint_lock.py) and of the one read (test_blueprint_test.py)
share: a temp folder for everything, an idea that is a LEAD with its code check on file, and a hand-made read of the test days.

TINY RUNS ONLY, on BUILD days: 3 named build days, 2 exit cells, NQ on 15-minute bars, 1 worker, through BP_TEST_RUN
(records.TEST_RUN: the test-only switch that lets a small run count; refused for the app's own idea folder). The lines of a
build are forced to pass where a lead is needed (3 days cannot pass 200 trades); the code check is written by hand in the
shape `bp.py code-check` saves (10 trades cannot be looked at on 3 days).
THE TEST DAYS ARE NEVER RUN for a new idea here: `fake_read` stands in for runner.run_test and writes the three stores of a
read from HAND-MADE trades (dated on test days, priced at nothing real), in the format the real read writes. The one real
read in the tests replays cells whose stores are on disk from the old 2025 / 2026 runs, and prints counts only.
Everything goes to the temp folder: ideas (--root), Lab drafts (HOMEBASE_DRAFTS_DIR), stores, ledger, tester runs.
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

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
import judge as J  # noqa: E402
from blueprint import api as A  # noqa: E402
from blueprint import cli as C  # noqa: E402
from blueprint import freeze as FRZ  # noqa: E402
from blueprint import records as REC  # noqa: E402
from blueprint import rules as R  # noqa: E402
from blueprint import runner as RUN  # noqa: E402

import l2sim as S  # noqa: E402
import library as LB  # noqa: E402
import run_idea as RI  # noqa: E402
import run_menus as RM  # noqa: E402

CARD = {"why": "The first minutes of the New York morning set a range, and a break of it traps the traders who leaned on it.",
        "loser": "traders who faded the opening range",
        "home": {"market": "NQ", "session": "nyam", "bar": "15"},
        "neighbors": ["midday"], "not_here": "the Asian session",          # both in the home's store: ONE tape pass an idea
        "main_setting": "or_min", "sides": "both", "sides_why": "a range can break either way", "loses_when": "a week without a clear direction"}
SETTINGS = {"family": "orb", "params": {"or_min": ["5", "15", "30"]}, "fixed": {}, "filters": [], "exits": "standard", "limits": {}}
DAYS = ["2022-03-15", "2023-03-22", "2025-06-30"]            # two plain build days and the last build day
CELLS = ["atr3-r1", "pts20-r0"]                              # 2 of the 32 exit cells
SAT = dt.datetime(2026, 10, 3, 11, 0, tzinfo=S.ET)           # a Saturday: no desk hours, no window
CONTRACT = ("ok", "command", "name", "status", "phase", "round", "lines", "text", "next", "job", "saved", "error")     # plan section 8
TEST_LINES = [f"4.{i}" for i in range(1, 10)]
HOME = Path.home() / ".homebase"
APP_RUNS = S.REPO / "homebase" / ".state" / "tester" / "runs"
APP_PYTHON = S.REPO / ".venv" / "bin" / "python"
_T: dict = {"keep": tempfile.TemporaryDirectory(prefix="bp_frozen_")}
_T["dir"] = Path(_T["keep"].name).resolve()


def tmp() -> Path:
    return _T["dir"]


OUT, TOUT, LEDGER, TESTER, DRAFTS = tmp() / "runs", tmp() / "runs_test", tmp() / "ledger.csv", tmp() / "tester", tmp() / "drafts"
TINY = {"days": DAYS, "cells": CELLS, "out": str(OUT), "ledger": str(LEDGER), "workers": 1, "draws": 200, "tester": str(TESTER), "test_out": str(TOUT),
        "box": "said", "build_avg_trade": 100.0}      # lines 3.3-3.7 are read, not enforced, on 3 days; the build's average trade a hand-made test is held against
ENV = {"HOMEBASE_IDEAS_ROOT": str(tmp() / "ideas_env"),      # never the real ~/.homebase: every test names its own root ...
       "HOMEBASE_DRAFTS_DIR": str(DRAFTS)}                   # ... and the Lab drafts of all of them go here
IS = A.ideastore()
_KEPT: dict = {}


def _listing(p: Path):
    return sorted(x.name for x in p.iterdir()) if p.exists() else None


PYC = [S.REPO / "homebase" / "backtest" / "__pycache__" / "importrun.cpython-314.pyc", S.REPO / "homebase" / "__pycache__" / "ideastore.cpython-314.pyc"]
BEFORE = {"ideas": _listing(HOME / "ideas"), "drafts": _listing(HOME / "strategies"), "reads": (HOME / "ideas" / "test_reads.jsonl").exists(),
          "runs_bp": _listing(RUN.RUNS), "tests": _listing(RUN.TESTS), "pyc": [p.exists() for p in PYC],
          "ledger": (LB.LEDGER.stat().st_size, LB.LEDGER.stat().st_mtime_ns)}


def env_on() -> None:
    """A test runs with ITS idea folder and Lab drafts in the environment and without the test-run switch (other test
    modules put their own there when they are imported)."""
    _KEPT.update({k: os.environ.get(k) for k in (*ENV, REC.TEST_RUN)})
    os.environ.update(ENV)
    os.environ.pop(REC.TEST_RUN, None)


def env_off() -> None:
    for k, v in _KEPT.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def idea(name: str, card=None, run=None, **top) -> dict:
    return {"name": name, "card": {**CARD, **(card or {})}, "run": {**SETTINGS, **(run or {})}, **top}


@contextlib.contextmanager
def tiny(**more):
    """BP_TEST_RUN is set while the block runs; the runner's clock stands on a Saturday; the workers asked for are used."""
    keep, clock, auto = os.environ.get(REC.TEST_RUN), RUN.clock, RM.auto_workers
    os.environ[REC.TEST_RUN] = json.dumps({**TINY, **more})
    RUN.clock, RM.auto_workers = (lambda: SAT), (lambda n=None: n)
    try:
        yield
    finally:
        RUN.clock, RM.auto_workers = clock, auto
        os.environ.pop(REC.TEST_RUN, None) if keep is None else os.environ.__setitem__(REC.TEST_RUN, keep)


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


@contextlib.contextmanager
def passing():
    """Every line of the build that is read says PASS while the block runs (a table of 3 days cannot pass on its own)."""
    keep = REC.LINES
    REC.LINES = tuple((lambda t, f=f: (lambda r: r if r["passed"] is None else {**r, "passed": True})(f(t))) for f in keep)
    try:
        yield
    finally:
        REC.LINES = keep


def refused(fn, word: str = "") -> str:
    try:
        fn()
    except (J.Refuse, R.RuleError) as e:
        assert word in str(e), str(e)
        return str(e)
    raise AssertionError(f"not refused ({word})")


def read(p) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def by(r: dict) -> dict:
    return {x["line"]: x for x in r["lines"]}


def tree(d: Path) -> list:
    return sorted(str(p.relative_to(d)) for p in d.rglob("*") if p.is_file())


def run_cli(argv: list, stdin: str = "") -> tuple:
    """The command line in this process -> (exit code, what it printed)."""
    out, keep = io.StringIO(), sys.stdin
    sys.stdin = io.StringIO(stdin)
    try:
        with contextlib.redirect_stdout(out):
            rc = C.main(argv)
    finally:
        sys.stdin = keep
    return rc, out.getvalue()


def bp(argv: list, stdin=None, **env) -> tuple:
    """The front door as the connector starts it: bp.py in its own process -> (exit code, the ONE JSON object)."""
    feed = {"stdin": subprocess.DEVNULL} if stdin is None else {"input": stdin}
    q = subprocess.run([sys.executable, str(W / "bp.py"), *argv], capture_output=True, text=True, timeout=900, cwd=str(W), env={**os.environ, **env}, **feed)
    assert q.stdout.count("\n") == 1, (q.stdout[-600:], q.stderr[-1500:])
    return q.returncode, json.loads(q.stdout)


# ================================================================ a lead with its code check on file

def hand_check(name: str, root, key: str, folder=None, looked: bool = True, **more) -> dict:
    """The idea's code check as `bp.py code-check <name> --store=<key> --looked` saves it, written by hand."""
    where = str((OUT if folder is None else Path(folder)) / key)
    marks = {"1.1": True, "1.2": True, "1.3": True, "1.4": True, "1.5": bool(looked), "1.6": None, **more.pop("marks", {})}
    rows = [{"line": k, "passed": v, "number": None, "need": None, "text": f"{k} {'n/a ' if v is None else 'PASS' if v else 'FAIL'} (written by a test)"}
            for k, v in marks.items()]
    r = {**A.result("code-check", name, lines=rows), "source": {"kind": "store", "where": where, "market": "NQ", "lists": 6, "trades": 12},
         "asked": {"store": where}, "passed": all(v is True for k, v in marks.items() if k != "1.6") and marks["1.6"] is not False, **more}
    IS.write_check(name, r, root)
    return r


_LEADS: dict = {}
_OWN: dict = {}                                     # name -> the BP_TEST_RUN settings of a lead that is built on days and a store folder of its own


def settings(name: str) -> dict:
    """What tiny() needs beyond its defaults to work on this lead again (its own build days, store folder and ledger)."""
    return dict(_OWN.get(name) or {})


def lead(name: str = "bpl_orb", card=None, run=None, check: bool = True, **own) -> Path:
    """An ideas root that holds ONE idea as a LEAD (round 1, every build line forced to pass) with its code check on file:
    built once a name, kept as a master folder. -> the master's ideas root (copy it: fresh()). own = BP_TEST_RUN settings
    of its own (days, out, ledger: a store folder holds the pool of ONE set of days)."""
    if name not in _LEADS:
        root = tmp() / "masters" / name
        _OWN[name] = own
        assert REC.card(name, idea(name, card, run), root)["ok"]
        with tiny(**own), passing():
            r = REC.build(name, "the plain idea, as carded", root=root)
        assert r["status"] == "lead" and IS.status(name, root) == "lead", r["text"]
        if check:
            hand_check(name, root, r["home_store"], own.get("out"))
        _LEADS[name] = root
    return _LEADS[name]


# first_bar_mom on NQ, 15-minute bars, midday: one of the OLD SAVED STRATEGIES. Its cells of 2025 and 2026 are on disk from the
# old runs, so it is the one idea whose test days may be replayed here (a handful of days, held against those stores).
FBM = "bpl_fbm"
FBM_CARD = {"why": "A session's first bar that is much larger than usual is momentum ignition, and the traders who fade it are run over.",
            "loser": "traders who fade the first bar of the midday session", "home": {"market": "NQ", "session": "mid", "bar": "15"},
            "neighbors": ["New York morning"], "not_here": "the Asian session", "main_setting": "k", "sides": "both", "sides_why": "the first bar can run either way", "loses_when": "a week without a clear direction"}
FBM_RUN = {"family": "first_bar_mom", "params": {"k": [1.0, 1.5, 2.0]}, "fixed": {}, "filters": [], "exits": "standard", "limits": {}}
FBM_DAYS = ["2021-10-18", "2021-10-22", "2021-10-25"]        # build days on which a variant makes money with normal and with worse fills (so: a default)
REAL_DAYS = ["2025-08-20", "2025-12-17", "2026-03-18", "2026-09-22"]      # 2 test days of each part: the old 2025 and 2026 stores hold every cell of them


def fbm() -> Path:
    return lead(FBM, FBM_CARD, FBM_RUN, days=FBM_DAYS, out=str(tmp() / "runs_fbm"), ledger=str(tmp() / "ledger_fbm.csv"))


def fresh(name: str = "bpl_orb", label: str = "a", *others) -> Path:
    """A copy of the master root of `name` (and of `others`) for one test to change: the stores are shared, read-only."""
    root = tmp() / "ideas" / label
    if root.exists():
        shutil.rmtree(root)
    for n in (name, *others):
        shutil.copytree(lead(n) / n, root / n)
    return root


def frozen(name: str = "bpl_orb", label: str = "f", *others) -> tuple:
    """fresh(), then frozen: -> (the ideas root, the lock)."""
    root = fresh(name, label, *others)
    with tiny(**settings(name)):
        r = FRZ.lock(name, root)
    return root, r["lock"]


# ================================================================ a hand-made read of the test days

TEST_DAYS = ["2025-07-08", "2025-09-17", "2025-11-12", "2025-12-16", "2026-02-11", "2026-04-15", "2026-06-17", "2026-08-19"]      # 4 in each part


def _trade(day: str, k: int, net: float, hhmm: str = "10:00") -> dict:
    ms = S.et_ns(dt.date.fromisoformat(day), hhmm) // 1_000_000 + 1000 * k
    return {"date": day, "entry_ms": ms, "exit_ms": ms + 60_000, "net": float(net), "side": "long" if k % 2 == 0 else "short", "qty": 1, "exit_reason": "tp",
            "entry_price": 20000.0, "exit_price": 20000.0 + net / 20.0, "sl": 19990.0, "mae_usd": 0.0, "gross": float(net) + 4.0, "commission": 4.0}


def _result(trades: list, rng: dict, period: str) -> dict:
    return {"trades": trades, "sessions": len(TEST_DAYS), "used": len(TEST_DAYS), "skipped": [], "no_trade": [], "elapsed_s": 0.0, "skipped_by_error": 0,
            "meta": {"inputs": {}, "engine": "hand-made", "root": "NQ", "range": {"start": rng["start"], "end": rng["end"], "holdout": True, "period": period}}}


def fake_read(net=lambda cell, i, day: 150.0, worse=lambda cell, i, day: 60.0, pool=lambda seed, cell, day: -5.0, days=None, seeds=None, seen=None,
              fail=None, period: str = "bp_test"):
    """A stand-in for runner.run_test (same arguments, same answer) that reads NOTHING: it writes the three stores of a
    read -- the locked variants, the same with worse fills, the idea's 10-seed pool -- from hand-made trades, one a cell
    and day in the home session, whose nets the caller's functions give. Like the real one it refuses without a claimed
    read. seen = a list that gets what was on file when it was called; fail = raise this instead of writing."""
    made = list(TEST_DAYS if days is None else days)

    def run_test(name, rd, spec, key, sess, variants, store, end, workers=None, out_dir=None, *, ideas=None, ledger=None, days=None, block=None,
                 progress=None, dry=False, keep=()):
        out, start = Path(out_dir), R.template("ranges")["test"]["start"]
        u = next(x for x in RI.spec_units(spec) if x["key"] == key)
        K, rng = RUN.test_keys(key, store, u["root"], u["tf"], sess), {"start": start, "end": end}
        rows = [{"key": K[k], "kind": kind, "root": u["root"], "tf": u["tf"], "cells": 0, "stage": "hand-made", "path": str(out / K[k]), "inputs_hash": "0" * 16,
                 "skipped": (out / K[k] / "run.json").exists(), "ok": None, "trades": None} for k, kind in (("pool", "pool"), ("table", "unit"), ("worse", "worse"))]
        if dry:
            return {"stores": rows, "calendar": None, "trades": {}}
        days = made if days is None else sorted(days)
        line = IS.read_on_file(name, root=ideas)
        if seen is not None:
            seen.append({"line": line, "test_json": (IS.idea_dir(name, ideas) / "test.json").exists(), "stores": _listing(out)})
        if not (line and line.get("state") == "claimed" and line.get("lock") == rd["lock"]):
            raise J.Refuse(f"no claimed read of the test days is on file for {name}")
        if fail is not None:
            raise fail
        hour = {"nyam": "10:00", "mid": "12:00", "pre": "08:45", "pm": "14:00"}[sess]
        grid = [c for c in u["grid"] if c["id"] in set(variants)]
        more = {"period": period, "calendar": days, "read": {"name": name, "version": rd["version"], "lock": rd["lock"]}, "inputs_hash": "0" * 16,
                "sessions": [sess], "sess_instance": sess, "family": spec["family"], "idea": name}
        kept: dict = {c: [] for c in keep}
        for which, fn in (("table", net), ("worse", worse)):
            res = []
            for c in grid:
                t = [_trade(d, i, fn(c["id"], i, d), hour) for i, d in enumerate(days) if fn(c["id"], i, d) is not None]
                if which == "table" and c["id"] in kept:
                    kept[c["id"]] = t
                res.append(_result(t, rng, period))
            LB.write_unit(K[which], {**more, "stage": which, "both_sides_declared": True, **({"worse": RUN.worse_kw(True)} if which == "worse" else {})}, grid, res, out)
        sd = list(range(1, R.template("control")["seeds"] + 1)) if seeds is None else list(seeds)
        pgrid = RUN._seeded(RM.c1_grid, sd, u["root"], u["tf"])
        res = [_result([_trade(d, k, pool(c["variant"]["seed"], c["id"], d), hour) for d in days for k in (0, 1)], rng, period) for c in pgrid]
        LB.write_unit(K["pool"], {**more, "stage": "pool", "family": "random", "control": "c1", "seeds": sd}, pgrid, res, out)
        for r in rows:
            r.update(skipped=False, ok=True)
        return {"stores": rows, "calendar": days, "trades": kept}

    return run_test


@contextlib.contextmanager
def reading(label: str = "", **kw):
    """runner.run_test is fake_read(**kw) while the block runs, and BP_TEST_RUN is set: the stores of the read go to a temp
    folder of their own (`label`: a root that reads an idea another root has read needs another folder)."""
    keep = RUN.run_test
    RUN.run_test = fake_read(**kw)
    try:
        with tiny(test_out=str(read_out(label))):
            yield
    finally:
        RUN.run_test = keep


def read_out(label: str = "") -> Path:
    return tmp() / f"runs_test_{label}" if label else TOUT


def clean() -> None:
    """Nothing was written outside the temp folder: ~/.homebase, runs_bp/, runs_bp_test/, ledger.csv, the app's tester."""
    assert _listing(HOME / "ideas") == BEFORE["ideas"] and _listing(HOME / "strategies") == BEFORE["drafts"], "a test wrote into ~/.homebase"
    assert (HOME / "ideas" / "test_reads.jsonl").exists() == BEFORE["reads"], "a test wrote the app's own one-read log"
    assert _listing(tmp() / "ideas_env") is None                                 # the environment's idea folder was never needed
    assert _listing(RUN.TESTS) == BEFORE["tests"], "a test wrote into runs_bp_test/"
    assert not [k for k in (_listing(RUN.RUNS) or []) if k.startswith("bpl_")], "a test wrote into runs_bp/"
    assert not [r["key"] for r in LB.read_ledger() if r["key"].startswith("bpl_")], "a test wrote into ledger.csv"
    assert not [k for k in (_listing(APP_RUNS) or []) if "draft_bpl_" in k], "a test wrote into the app's tester runs"
    assert [p.exists() for p in PYC] == BEFORE["pyc"], "bytecode was written into homebase/"
