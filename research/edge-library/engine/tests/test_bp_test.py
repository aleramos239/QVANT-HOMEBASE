"""The blueprint TEST switch (BLUEPRINT.md phase 4; out/blueprint/toolkit_plan.md step 8): allow_holdout="bp_test" with NAMED
dates opens 2025-07-01 .. the archive's end and nothing before it -- a build day is refused under it whatever other flag
comes along, and so is a named day outside the named range; it has no range by name; without it the test days are refused
exactly as before; the old periods and switches are what they were (their own locks: test_edge_periods.py,
test_check_period.py, test_bp_build.py). It has ONE caller in the whole code base: blueprint/runner.run_test.

THE TEST DAYS ARE THE PROOF THE OWNER IS SAVING: no new strategy result is produced on them here. A date on or after
2025-07-01 is named where the call must raise BEFORE anything is read, where only file names are listed -- and in ONE
place where something runs: the replay of cells whose 2025-07-01+ stores are ALREADY on disk from the old 2025 and 2026
runs (runs_check2025/, runs_exam2026/), on 2 days of each store, held against those stores trade for trade. Counts only:
no P&L is asserted or printed."""
import ast
import datetime as dt
import json
import re
import sys

import numpy as np
import pytest

import l2ref
import l2sim as S

ROOTS = ["NQ", "ES", "GC"]
DON = (l2ref.Donchian, {"tf": "15"})
BT = "bp_test"


def _has_tape(d, root):
    return (S.tape_path(d, root).exists() if root == "NQ" else S.hb_tape_path(d, root) is not None)


def _no_data(monkeypatch, tmp_path):
    """Every tape, manifest and cache folder of the engine points at an empty directory: a call that must be refused cannot
    read a sealed day even if the seal were broken (it would then return nothing instead of raising, and the test fails)."""
    for name in ("TAPE_DIR", "HB_TAPE", "OWN_TAPE", "ARCHIVE", "CACHE"):
        monkeypatch.setattr(S, name, tmp_path / name)


def test_the_test_starts_the_day_after_the_build_ends_and_has_no_range_by_name():
    assert S.ALLOW_BT == BT and S.BP_TEST_START == dt.date(2025, 7, 1) == S.BP_BUILD[1] + dt.timedelta(days=1)
    for name in ("bp_test", "BP_TEST"):
        with pytest.raises(S.HoldoutSealed, match="no range by name"):      # its end is the session a lock froze: the dates are named
            S.period(name)
    assert BT not in S.PERIODS and S.PERIODS == {"build": S.BUILD, "pick": S.PICK, "insample": S.IN_SAMPLE}
    assert (S.BUILD, S.PICK) == ((dt.date(2021, 9, 22), dt.date(2023, 12, 31)), (dt.date(2024, 1, 1), dt.date(2024, 12, 31)))      # the old ones: untouched
    assert S.CHECK == (dt.date(2025, 1, 1), dt.date(2025, 12, 31)) and S.EXAM_START == S.HOLDOUT_START == dt.date(2025, 1, 1)
    assert S.BP_BUILD == (dt.date(2021, 9, 22), dt.date(2025, 6, 30)) and S.ALLOW_BP == "bp_build" and S.period("bp_build") == S.BP_BUILD


def test_the_switch_is_the_exact_name_and_no_flag_widens_it():
    assert S.allow_level(S.ALLOW_BT) == S.ALLOW_BT and S.allow_level(allow_holdout=BT) == S.ALLOW_BT
    for other in ({"allow_exam": True}, {"allow_check": True}, {"allow_exam": True, "allow_check": True}):
        assert S.allow_level(S.ALLOW_BT, **other) == S.ALLOW_BT              # never the EXAM key (it would open Jan-Jun 2025), never the CHECK year
    for v in (1, "yes", "bt", "test", "BP_TEST", "bp_test ", " bp_test", b"bp_test", ["bp_test"], ("bp_test",), {"bp_test"}, np.True_):
        assert S.allow_level(allow_holdout=v) is False                       # anything but the exact name opens nothing
    assert S.allow_level() is False and S.allow_level(allow_check=True) == S.ALLOW_CHECK      # the old switches: as they were
    assert S.allow_level(allow_holdout=True) is True and S.allow_level(allow_exam=True) is True and S.allow_level(True, False, True) is True
    assert S.allow_level(S.ALLOW_BP) == S.ALLOW_BP and S.allow_level(S.ALLOW_BP, allow_exam=True) == S.ALLOW_BP


def test_the_guard_opens_from_2025_07_01_and_nothing_before_it():
    for d in ("2025-07-01", "2025-07-02", "2025-12-31", "2026-01-02", "2026-09-22"):
        S.check_holdout(d, S.ALLOW_BT)
    for d in ("2025-06-30", "2025-06-27", "2025-01-02", "2024-12-31", "2023-03-22", "2021-09-22"):
        with pytest.raises(S.HoldoutSealed, match="2025-07-01"):
            S.check_holdout(d, S.ALLOW_BT)
    for d in ("2025-07-01", "2025-12-31", "2026-09-22"):                    # anything but the exact name: sealed as before
        for flag in (False, None, 1, "yes", "bt", "BP_TEST", S.ALLOW_BP):
            with pytest.raises(S.HoldoutSealed):
                S.check_holdout(d, flag)
    S.check_holdout("2025-07-01", S.ALLOW_CHECK)                            # the CHECK switch and the EXAM key: unchanged
    S.check_holdout("2026-01-02", True)
    with pytest.raises(S.HoldoutSealed):
        S.check_holdout("2026-01-02", S.ALLOW_CHECK)
    assert S._seal_end(S.ALLOW_BT) == S._seal_end(True) == dt.date(2026, 12, 31)      # the archive's end: what the test switch seals is its FIRST day
    assert (S._seal_end(S.ALLOW_BP), S._seal_end(S.ALLOW_CHECK), S._seal_end(False), S._seal_end("yes")) == (S.BP_BUILD[1], S.CHECK[1], S.IN_SAMPLE[1], S.IN_SAMPLE[1])


@pytest.mark.parametrize("root", ROOTS)
def test_without_the_switch_the_test_days_are_refused_exactly_as_before(root, monkeypatch, tmp_path):
    _no_data(monkeypatch, tmp_path)
    for fn in (lambda: S.load_tape("2025-07-01", root), lambda: S.sessions("2025-07-01", "2025-07-03", root),
               lambda: S.run(*DON, "2025-07-01", "2025-07-03", root=root, workers=1), lambda: S.run(*DON, days=["2025-07-01"], root=root, workers=1),
               lambda: S.run(*DON, period="bp_build", days=["2025-07-01"], root=root, workers=1),                   # the build switch never opens it
               lambda: S.run(*DON, period="bp_test", days=["2025-07-01"], root=root, workers=1),                    # the name alone is no range
               lambda: S.run(*DON, period="BP_TEST", root=root, workers=1),
               lambda: S.run(*DON, "2025-07-01", "2025-07-03", root=root, workers=1, allow_holdout="BP_TEST"),      # not the exact name
               lambda: S.run(*DON, "2025-07-01", "2025-07-03", root=root, workers=1, allow_holdout=1),
               lambda: S.run(*DON, "2026-01-02", "2026-01-05", root=root, workers=1, allow_check=True),             # the CHECK year ends 2025-12-31
               lambda: S.run(*DON, root=root, workers=1, allow_holdout=S.ALLOW_BT),                                 # the switch WITHOUT named dates: no run
               lambda: S.run(*DON, days=["2025-07-01"], root=root, workers=1, allow_holdout=S.ALLOW_BT),
               lambda: S.run(*DON, "2025-07-01", root=root, workers=1, allow_holdout=S.ALLOW_BT),
               lambda: S.run(*DON, end="2026-09-22", root=root, workers=1, allow_holdout=S.ALLOW_BT)):
        with pytest.raises(S.HoldoutSealed):
            fn()


@pytest.mark.parametrize("root", ROOTS)
def test_everything_that_reaches_a_build_day_raises_before_it_reads(root, monkeypatch, tmp_path):
    _no_data(monkeypatch, tmp_path)
    # what the switch opens answers (with nothing: the folders are empty) ...
    assert S.load_tape("2025-07-01", root, allow_holdout=S.ALLOW_BT) is None and S.sessions("2025-07-01", "2026-09-22", root, allow_holdout=S.ALLOW_BT) == []
    assert S.sessions("2025-07-01", "2026-09-22", root, allow_holdout=S.ALLOW_BT, allow_exam=True, allow_check=True) == []
    # ... and everything that touches a day before 2025-07-01 raises, whatever comes along
    for fn in (lambda: S.load_tape("2025-06-30", root, allow_holdout=S.ALLOW_BT),
               lambda: S.load_tape("2025-06-30", root, allow_holdout=S.ALLOW_BT, allow_exam=True, allow_check=True),
               lambda: S.load_tape("2024-03-15", root, allow_holdout=S.ALLOW_BT),                                    # a day ANY other call may read
               lambda: S.sessions("2025-06-30", "2025-07-02", root, allow_holdout=S.ALLOW_BT),
               lambda: S.sessions("2021-09-22", "2026-09-22", root, allow_holdout=S.ALLOW_BT, allow_exam=True),
               lambda: S.sessions("2021-09-22", "2023-12-31", root, allow_holdout=S.ALLOW_BT),
               lambda: S.run(*DON, "2025-06-30", "2025-07-02", root=root, workers=1, allow_holdout=S.ALLOW_BT),
               lambda: S.run(*DON, "2025-06-30", "2025-07-02", root=root, workers=1, allow_holdout=S.ALLOW_BT, allow_exam=True),      # the EXAM key
               lambda: S.run(*DON, "2025-01-02", "2025-12-31", root=root, workers=1, allow_holdout=S.ALLOW_BT, allow_check=True),     # does not widen it, nor the CHECK flag
               lambda: S.run(*DON, period="check", root=root, workers=1, allow_holdout=S.ALLOW_BT),
               lambda: S.run(*DON, "2025-07-01", "2025-07-03", days=["2025-06-30", "2025-07-01"], root=root, workers=1, allow_holdout=S.ALLOW_BT),
               lambda: S.run(*DON, "2025-07-01", "2025-07-03", days=["2024-03-15"], root=root, workers=1, allow_holdout=S.ALLOW_BT),
               lambda: S.run_many([DON], "2021-09-22", "2026-12-31", root=root, workers=1, allow_holdout=S.ALLOW_BT),
               lambda: S._run_days(([DON], root, ["2025-06-30"], S.Costs(), 1, S.ALLOW_BT, None, None, None, False)),         # the worker itself
               lambda: S._atr_one(("2025-06-30", root, S.ALLOW_BT)), lambda: S._tapes_one(("2025-06-30", root, S.ALLOW_BT)),
               lambda: S.build_daily(root, "2025-06-01", "2025-07-02", workers=1, allow_holdout=S.ALLOW_BT),
               lambda: S.build_tapes("ES" if root == "NQ" else root, "2025-06-01", "2025-07-02", allow_holdout=S.ALLOW_BT)):
        with pytest.raises(S.HoldoutSealed, match="2025-07-01"):
            fn()
    # a named day outside the NAMED range: the range a lock froze is the whole of a test run
    for days in (["2025-07-08"], ["2025-07-02", "2026-01-02"]):
        with pytest.raises(S.HoldoutSealed, match="outside the named range"):
            S.run(*DON, "2025-07-01", "2025-07-03", days=days, root=root, workers=1, allow_holdout=S.ALLOW_BT)
    # with the build's period the build's seal wins, whatever switch came along: no test day
    with pytest.raises(S.HoldoutSealed, match="2025-06-30"):
        S.run(*DON, period="bp_build", days=["2025-07-01"], root=root, workers=1, allow_holdout=S.ALLOW_BT)
    # the tape builder takes the test switch and nothing else by that keyword; never the EXAM key
    for fn in (lambda: S._tapes_one(("2025-07-01", root, True)), lambda: S._tapes_one(("2025-07-01", root)), lambda: S._tapes_one(("2026-01-02", root, S.ALLOW_CHECK)),
               lambda: S.build_tapes("ES" if root == "NQ" else root, "2025-07-01", "2025-07-02", allow_holdout=True),
               lambda: S.build_tapes("ES" if root == "NQ" else root, "2025-07-01", "2025-07-02", allow_holdout="yes")):
        with pytest.raises(S.HoldoutSealed):
            fn()
    assert S.build_tapes("ES" if root == "NQ" else root, "2025-07-01", "2025-07-02", workers=1, allow_holdout=S.ALLOW_BT) == {"built": 0, "cached": 0, "no tape": 0}


def test_the_test_caches_are_their_own_files_and_hold_nothing_before_2025_07_01():
    assert S._daily_path("NQ", S.ALLOW_BT).name == "daily_NQ_bt.json" and S._atr_path("NQ", S.ALLOW_BT).name == "eve_atr30_NQ_bt.json"
    assert S._daily_path("NQ", False).name == "daily_NQ.json" and S._daily_path("NQ", True).name == "daily_NQ_holdout.json"      # the old files
    assert S._daily_path("NQ", S.ALLOW_CHECK).name == "daily_NQ_check.json" and S._daily_path("NQ", S.ALLOW_BP).name == "daily_NQ_bp.json"
    assert S._daily_path("NQ", "yes").name == "daily_NQ.json" and S._atr_path("NQ").name == "eve_atr30_NQ.json"
    assert S._atr_path("NQ", True).name == "eve_atr30_NQ_check.json" and S._atr_path("NQ", S.ALLOW_BP).name == "eve_atr30_NQ_bp.json"
    if S._daily_path("NQ", S.ALLOW_BT).exists() and S._daily_path("NQ", S.ALLOW_BP).exists():
        doc = json.loads(S._daily_path("NQ", S.ALLOW_BT).read_text())
        assert doc["start"] == "2025-07-01" and doc["rows"] and min(r["date"] for r in doc["rows"]) >= "2025-07-01"
        rows, bp = S.load_daily("NQ", S.ALLOW_BT, build=False), S.load_daily("NQ", S.ALLOW_BP, build=False)
        assert rows[:len(bp)] == bp and bp[-1]["date"] <= "2025-06-30" < rows[len(bp)]["date"]              # the build's bars (prior data), then its own days
        assert [r["date"] for r in rows] == sorted({r["date"] for r in rows}) and rows[len(bp):] == sorted(doc["rows"], key=lambda r: r["date"])
        assert S.load_daily("NQ", S.ALLOW_BP, build=False)[-1]["date"] <= "2025-06-30" and S.load_daily("NQ")[-1]["date"] <= "2024-12-31"      # ... and no other file got a row
    if S._atr_path("NQ", S.ALLOW_BT).exists():
        own = json.loads(S._atr_path("NQ", S.ALLOW_BT).read_text())
        assert min(own) >= "2025-07-01"
        a = S.load_eve_atr("NQ", build=False, allow_holdout=S.ALLOW_BT)
        assert {k: v for k, v in a.items() if k < "2025-07-01"} == S.load_eve_atr("NQ", build=False, allow_holdout=S.ALLOW_BP)
    assert max(S.load_eve_atr("NQ", build=False)) <= "2024-12-31"            # the in-sample ATR file: as it was
    with pytest.raises(S.HoldoutSealed):                                    # Level-2 features: not opened for it
        S.L2Features(["imb10"], allow_holdout=S.ALLOW_BT)
    with pytest.raises(S.HoldoutSealed):
        S.L2Features(["imb10"])("2025-07-01")


def test_the_session_list_of_the_test_days_is_file_names_only(monkeypatch):
    for name in ("load_tape", "read_hb_tape", "read_hb_header"):            # no tape and no header may be opened for a list of dates
        monkeypatch.setattr(S, name, lambda *a, **k: (_ for _ in ()).throw(AssertionError("a tape was opened")))
    for root in ROOTS:
        cal = S.sessions("2025-07-01", "2026-09-22", root, allow_holdout=S.ALLOW_BT)
        if not cal:
            continue
        assert cal[0] >= S.BP_TEST_START and cal == sorted(set(cal)) and all(d.weekday() < 5 for d in cal) and cal[-1] <= dt.date(2026, 9, 22)
        assert cal == S.sessions("2025-07-01", "2026-09-22", root, allow_exam=True)       # the same dates the EXAM key lists: one calendar


def test_the_tape_builder_is_reached_for_a_test_day_under_the_test_switch_only(monkeypatch, tmp_path):
    """ES / GC replay tapes in the tester's format; a session the tester never cached is built from the archive by the
    tester's own code (here: a stand-in that only notes what it was asked for -- nothing is read, nothing is built)."""
    import types
    _no_data(monkeypatch, tmp_path)
    asked = []

    class OverlayTapeStore:
        def __init__(self, *folders):
            self.folders = folders

        def build(self, root, d):
            asked.append((root, d.isoformat()))
            return object()

    stub = types.ModuleType("homebase.backtest.tape")
    stub.OverlayTapeStore = OverlayTapeStore
    monkeypatch.setitem(sys.modules, "homebase.backtest.tape", stub)
    assert S._tapes_one(("2025-07-01", "ES", S.ALLOW_BT)) == ("2025-07-01", "built") and asked == [("ES", "2025-07-01")]
    for args in (("2025-06-30", "ES", S.ALLOW_BT), ("2024-03-15", "ES", S.ALLOW_BT),            # a build day under the test switch
                 ("2025-07-01", "ES", True), ("2025-07-01", "ES", 1), ("2025-07-01", "ES"),     # a test day under the EXAM key, or under nothing
                 ("2026-01-02", "ES", S.ALLOW_CHECK), ("2025-07-01", "ES", "BP_TEST"), ("2025-07-01", "ES", S.ALLOW_BP)):
        with pytest.raises(S.HoldoutSealed):
            S._tapes_one(args)
    assert asked == [("ES", "2025-07-01")]                                   # ... none of them reached the builder
    assert S._tapes_one(("2025-12-31", "ES", S.ALLOW_CHECK)) == ("2025-12-31", "built")       # the CHECK switch: as before
    assert S._tapes_one(("2024-03-15", "ES")) == ("2024-03-15", "built") and len(asked) == 3   # ... and an in-sample day needs none


# ---- identity: cells whose test-day stores are ALREADY on disk, replayed under the test switch, trade for trade ---------------
H2_DAYS = ("2025-08-20", "2025-12-17")                                      # two days of Jul-Dec 2025 (the 2025 stores hold the whole year)
Y26_DAYS = ("2026-03-18", "2026-09-22")                                     # two days of 2026, the last one the archive's last complete session
UNITS = [("orb", "NQ", "15", "pre", False, ("or_min5_atr1p5-r2", "or_min30_pts20-r0"), False),              # bar-based, NQ daily file, a two-sided bracket
         ("first_bar_mom", "NQ", "15", "mid", True, ("k1_atr3-r1", "k2_pts20-r0"), False),                  # ... with a 2026 store too
         ("first_bar_mom", "ES", "15", "mid", False, ("k1_atr3-r1", "k1_pts5-r0"), False),                  # daily bars from tape headers
         ("straddle_tight_0830", "GC", "30", "pre", True, ("offA_pts1-r2", "offC_pts2-r1"), False),         # clock-time, GC
         ("first_bar_mom", "NQ", "15", "mid", True, ("k1_atr3-r1", "k2_pts20-r0"), True)]                   # the same cells with worse fills


def _runner():
    """out/check2025/run_check.py, the runner that wrote the 2025 stores: its job_grid and its comparison _same are reused."""
    p = S.W / "out" / "check2025"
    if not (p / "run_check.py").exists():
        pytest.skip("out/check2025/run_check.py is not on this machine")
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
    import run_check
    return run_check


@pytest.mark.parametrize("family,root,tf,sess,exam,cells,stress", UNITS)
def test_a_test_run_is_trade_for_trade_what_the_stores_of_the_old_runs_hold(family, root, tf, sess, exam, cells, stress):
    import library as LB
    RC = _runner()
    key, tag = f"{family}-{root}-tf{tf}", ("-stress" if stress else "")
    stores = [("runs_check2025", f"{key}-{sess}-check{tag}", H2_DAYS)] + ([("runs_exam2026", f"{key}-{sess}-exam{tag}", Y26_DAYS)] if exam else [])
    for d, k, ds in stores:
        if not (LB.W / d / k / "run.json").exists() or not all(_has_tape(x, root) for x in ds):
            pytest.skip(f"store {d}/{k} or one of its tapes is not on this machine")
    grid, cls, timed = RC.job_grid({"family": family, "root": root, "tf": tf, "sess": sess, "cells": list(cells)})
    days = sorted(x for _, _, ds in stores for x in ds)
    kw = {**(dict(S.STRESS) if stress else {}), **getattr(cls, "SCREEN_RUN", {})}
    res = S.run_many([c["spec"] for c in grid], "2025-07-01", days[-1], days=days, root=root, workers=2, allow_holdout=S.ALLOW_BT, **kw)
    assert {c["id"] for c in grid} == set(cells)
    for r in res:
        assert r["sessions"] == len(days) and r["skipped_by_error"] == 0
        assert r["meta"]["range"] == {"start": "2025-07-01", "end": days[-1], "holdout": True, "period": BT} and r["meta"]["days_subset"]
        assert all(t["date"] in days for t in r["trades"])                    # every trade falls into one of the comparisons
        if not timed:                                                         # the unit's session instance only, as the runner keeps it
            r["trades"] = [t for t in r["trades"] if S.session_of(t["entry_ms"]) == sess]
    total = 0
    for d, k, ds in stores:
        part = [{**r, "trades": [t for t in r["trades"] if t["date"] in ds]} for r in res]
        n_cells, n, diff = RC._same(grid, part, LB.load_unit(k, LB.W / d), ds, sess, True)
        assert (n_cells, diff) == (len(cells), 0) and n > 0, f"{d}/{k}: {diff} of {n_cells} cells differ ({n} stored trades on {len(ds)} days)"
        total += n
    print(f"identity {key} {sess}{' worse fills' if stress else ''}: {len(cells)} cells x {len(stores)} stores, {len(days)} days, {total} stored trades, 0 cells differ")


# ---- ONE caller ---------------------------------------------------------------------------------------------------------------
USE = re.compile(r"ALLOW_BT|BP_TEST_START|[\"']bp_test[\"']")
SKIP = ("tests", "__pycache__", ".venv", "venv", "node_modules", ".git", ".pytest_cache", "cache")


def _code_files() -> list:
    """Every Python file of the edge library and of the app, tests and store folders aside."""
    out = []
    for base in (S.W, S.REPO / "homebase"):
        for p in base.rglob("*.py"):
            rel = p.relative_to(base).parts
            if any(x in SKIP or x.startswith("runs") for x in rel[:-1]) or rel[-1].startswith("test_"):
                continue
            out.append(p)
    return out


def test_the_switch_has_one_caller_in_the_whole_code_base():
    files = _code_files()
    assert len(files) > 100 and S.L / "l2sim.py" in files and S.W / "blueprint" / "runner.py" in files and S.W / "judge.py" in files
    hits = {p: [i for i, ln in enumerate(p.read_text(errors="ignore").splitlines(), 1) if USE.search(ln)] for p in files}
    hits = {p: v for p, v in hits.items() if v}
    assert set(hits) == {S.L / "l2sim.py", S.L / "btfeat.py", S.W / "blueprint" / "runner.py"}, sorted(str(p) for p in hits)      # the engine, the Level-2 test loader, and ONE module outside it
    # btfeat (the test days' Level-2 table) names the switch for its own loader, and that loader is made by run_test alone -- the build's bpfeat never names it
    assert S.L / "bpfeat.py" in files and not USE.search((S.L / "bpfeat.py").read_text())
    made = sorted(str(p.relative_to(S.W)) for p in files if p != S.L / "btfeat.py" and "BtL2Features(" in p.read_text(errors="ignore"))
    assert made == ["blueprint/runner.py"], made
    # ... and in that module every mention lies inside ONE function: run_test
    src = (S.W / "blueprint" / "runner.py").read_text()
    fn = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "run_test"]
    assert len(fn) == 1 and all(fn[0].lineno <= i <= fn[0].end_lineno for i in hits[S.W / "blueprint" / "runner.py"]), hits[S.W / "blueprint" / "runner.py"]
    body = ast.get_source_segment(src, fn[0])
    assert 'getattr(S, "ALLOW_BT", None)' in body and body.count("allow_holdout=sw") == 5          # the session list, a missing tape, the volume cache, the swing bars, the passes
    assert "read_on_file" in body and body.index("read_on_file") < body.index("allow_holdout=sw")   # ... each AFTER the claimed read was looked up
    assert body.count("BtL2Features(") == 1 and body.index("read_on_file") < body.index("BtL2Features(")      # the Level-2 test loader: made here, after the claim
    # run_test itself is called by the test command alone (blueprint/oos.py), and by nothing else
    callers = sorted(str(p.relative_to(S.W)) for p in files if p.is_relative_to(S.W) and re.search(r"\brun_test\(", p.read_text(errors="ignore")))
    assert callers == ["blueprint/oos.py", "blueprint/runner.py"], callers
    # the toolkit itself passes TWO switches and no other: the build's (by its name) and, inside run_test, the test's -- never the
    # EXAM key and never the CHECK flag, which open days of the test range too (2025-01-01 on / the whole of 2025)
    toolkit = [p for p in files if p.is_relative_to(S.W / "blueprint") or p == S.W / "bp.py"]
    assert len(toolkit) > 10 and sorted({m for p in toolkit for m in re.findall(r"allow_holdout\s*=\s*([A-Za-z_.\"']+)", p.read_text())}) == ["PERIOD", "RUN.PERIOD", "sw"]
    assert not [str(p) for p in toolkit if re.search(r"allow_exam|allow_check|ALLOW_CHECK|check_holdout\([^)]*,\s*True\)", p.read_text())]
