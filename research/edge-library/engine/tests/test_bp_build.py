"""The blueprint BUILD switch (BLUEPRINT.md phase 2; out/blueprint/toolkit_plan.md step 3): period="bp_build" runs
2021-09-22..2025-06-30 in ONE pass and nothing later -- a date from 2025-07-01 on is refused under it whatever other flag comes
along; without it 2025 is refused exactly as before; the old periods and switches are what they were (their own locks:
test_edge_periods.py, test_check_period.py). One bp_build run over days of 2021-23, 2024 and the first half of 2025 is trade for
trade what the stores written under the old switches hold. No P&L is asserted. A date after 2025-06-30 is only ever named where
the call must raise BEFORE anything is read."""
import datetime as dt
import json
import sys

import numpy as np
import pytest

import l2ref
import l2sim as S

ROOTS = ["NQ", "ES", "GC"]
DON = (l2ref.Donchian, {"tf": "15"})
BP_RANGE = {"start": "2021-09-22", "end": "2025-06-30", "holdout": True, "period": "bp_build"}
BP_SESSIONS = {"NQ": 948, "ES": 948, "GC": 947}                            # the in-sample sessions (825 / 825 / 824) + 123 of 2025


def _has_tape(d, root):
    return (S.tape_path(d, root).exists() if root == "NQ" else S.hb_tape_path(d, root) is not None)


def _no_data(monkeypatch, tmp_path):
    """Every tape, manifest and cache folder of the engine points at an empty directory: a call that must be refused cannot
    read a sealed day even if the seal were broken (it would then return nothing instead of raising, and the test fails)."""
    for name in ("TAPE_DIR", "HB_TAPE", "OWN_TAPE", "ARCHIVE", "CACHE"):
        monkeypatch.setattr(S, name, tmp_path / name)


def test_the_bp_build_range_is_one_named_period_and_the_old_ones_are_untouched():
    assert S.BP_BUILD == (dt.date(2021, 9, 22), dt.date(2025, 6, 30)) and S.ALLOW_BP == "bp_build"
    assert S.BP_BUILD[0] == S.BUILD[0] and S.BP_BUILD[1] + dt.timedelta(days=1) == dt.date(2025, 7, 1)
    assert S.period("bp_build") == S.BP_BUILD and S.period("BP_BUILD") == S.BP_BUILD and "bp_build" not in S.PERIODS
    assert S.PERIODS == {"build": S.BUILD, "pick": S.PICK, "insample": S.IN_SAMPLE} and S.IN_SAMPLE == (S.BUILD[0], S.PICK[1])
    assert (S.BUILD, S.PICK) == ((dt.date(2021, 9, 22), dt.date(2023, 12, 31)), (dt.date(2024, 1, 1), dt.date(2024, 12, 31)))
    assert S.CHECK == (dt.date(2025, 1, 1), dt.date(2025, 12, 31)) and S.EXAM_START == S.HOLDOUT_START == dt.date(2025, 1, 1)
    assert [S.period_of(*x) for x in (S.BP_BUILD, S.BUILD, S.PICK, S.IN_SAMPLE, S.CHECK)] == ["mixed", "build", "pick", "insample", "check"]


def test_the_switch_is_the_exact_name_and_no_flag_widens_it():
    assert S.allow_level(S.ALLOW_BP) == S.ALLOW_BP and S.allow_level(allow_holdout="bp_build") == S.ALLOW_BP
    for other in ({"allow_exam": True}, {"allow_check": True}, {"allow_exam": True, "allow_check": True}):
        assert S.allow_level(S.ALLOW_BP, **other) == S.ALLOW_BP              # never the EXAM key, never the whole CHECK year
    for v in (1, "yes", "bp", "build", "BP_BUILD", "bp_build ", b"bp_build", ["bp_build"], ("bp_build",), np.True_):
        assert S.allow_level(allow_holdout=v) is False                       # anything but the exact name opens nothing
    assert S.allow_level() is False and S.allow_level(allow_check=True) == S.ALLOW_CHECK      # the old switches: as they were
    assert S.allow_level(allow_holdout=True) is True and S.allow_level(allow_exam=True) is True and S.allow_level(True, False, True) is True
    assert S.allow_level(allow_holdout=S.ALLOW_CHECK) == S.ALLOW_CHECK and S.allow_level(S.ALLOW_CHECK, True) is True


def test_the_guard_opens_to_2025_06_30_and_nothing_later():
    for d in ("2021-09-22", "2023-12-29", "2024-12-31", "2025-01-02", "2025-06-27", "2025-06-30"):
        S.check_holdout(d, S.ALLOW_BP)
    for d in ("2025-07-01", "2025-07-02", "2025-12-31", "2026-01-02", "2026-09-22", "2027-03-01"):
        with pytest.raises(S.HoldoutSealed, match="2025-06-30"):
            S.check_holdout(d, S.ALLOW_BP)
    for d in ("2025-01-02", "2025-06-30", "2025-07-01"):                    # anything but the exact name: sealed as before
        for flag in (False, None, 1, "yes", "bp", "BP_BUILD"):
            with pytest.raises(S.HoldoutSealed):
                S.check_holdout(d, flag)
    assert S._seal_end(S.ALLOW_BP) == S.BP_BUILD[1] and S._seal_end(S.ALLOW_CHECK) == S.CHECK[1]
    assert S._seal_end(False) == S._seal_end("yes") == S.IN_SAMPLE[1]


@pytest.mark.parametrize("root", ROOTS)
def test_without_the_switch_2025_is_refused_exactly_as_before(root):
    for fn in (lambda: S.load_tape("2025-06-30", root), lambda: S.sessions(*S.period("bp_build"), root),      # the range's name alone opens nothing
               lambda: S.run(*DON, *S.BP_BUILD, root=root, workers=1), lambda: S.run(*DON, days=["2025-06-30"], root=root, workers=1),
               lambda: S.run(*DON, period="build", days=["2025-06-30"], root=root, workers=1),
               lambda: S.run(*DON, days=["2025-06-30"], root=root, workers=1, allow_holdout="BP_BUILD"),
               lambda: S.run(*DON, days=["2025-06-30"], root=root, workers=1, allow_holdout=1)):
        with pytest.raises(S.HoldoutSealed):
            fn()


@pytest.mark.parametrize("root", ROOTS)
def test_everything_that_reaches_2025_07_01_raises_before_it_reads(root, monkeypatch, tmp_path):
    _no_data(monkeypatch, tmp_path)
    assert S.load_tape("2025-06-30", root, allow_holdout=S.ALLOW_BP) is None and S.sessions(*S.BP_BUILD, root, allow_holdout=S.ALLOW_BP) == []
    for fn in (lambda: S.load_tape("2025-07-01", root, allow_holdout=S.ALLOW_BP),
               lambda: S.load_tape("2025-07-01", root, allow_holdout=S.ALLOW_BP, allow_exam=True, allow_check=True),
               lambda: S.sessions("2025-06-01", "2025-07-01", root, allow_holdout=S.ALLOW_BP),
               lambda: S.sessions("2025-07-01", "2025-07-02", root, allow_holdout=S.ALLOW_BP, allow_exam=True),
               lambda: S.run(*DON, period="bp_build", days=["2025-06-30", "2025-07-01"], root=root, workers=1),
               lambda: S.run(*DON, period="bp_build", days=["2026-01-02"], root=root, workers=1),
               lambda: S.run(*DON, period="bp_build", days=["2025-07-01"], root=root, workers=1, allow_exam=True),      # the EXAM key
               lambda: S.run(*DON, period="BP_BUILD", days=["2025-07-01"], root=root, workers=1, allow_holdout=True),   # does not widen it,
               lambda: S.run(*DON, period="bp_build", days=["2025-07-01"], root=root, workers=1, allow_check=True),     # nor the CHECK flag
               lambda: S.run(*DON, "2025-06-27", "2025-07-01", root=root, workers=1, allow_holdout=S.ALLOW_BP),
               lambda: S.run_many([DON], "2021-09-22", "2026-12-31", root=root, workers=1, allow_holdout=S.ALLOW_BP),
               lambda: S.run_many([DON], days=["2025-07-01"], root=root, workers=1, allow_holdout=S.ALLOW_BP, allow_exam=True),
               lambda: S._run_days(([DON], root, ["2025-07-01"], S.Costs(), 1, S.ALLOW_BP, None, None, None, False)),       # the worker itself
               lambda: S._atr_one(("2025-07-01", root, S.ALLOW_BP)),
               lambda: S.build_daily(root, "2025-06-01", "2025-07-01", workers=1, allow_holdout=S.ALLOW_BP)):
        with pytest.raises(S.HoldoutSealed):
            fn()


def test_bp_caches_are_their_own_files_and_hold_nothing_after_2025_06_30():
    assert S._daily_path("NQ", S.ALLOW_BP).name == "daily_NQ_bp.json" and S._atr_path("NQ", S.ALLOW_BP).name == "eve_atr30_NQ_bp.json"
    assert S._daily_path("NQ", False).name == "daily_NQ.json" and S._daily_path("NQ", True).name == "daily_NQ_holdout.json"      # the old files
    assert S._daily_path("NQ", S.ALLOW_CHECK).name == "daily_NQ_check.json" and S._daily_path("NQ", "yes").name == "daily_NQ.json"
    assert S._atr_path("NQ").name == "eve_atr30_NQ.json" and S._atr_path("NQ", True).name == "eve_atr30_NQ_check.json"
    base = S.load_daily("NQ")
    assert base and base[-1]["date"] <= "2024-12-31"                        # the in-sample file never holds a 2025 row
    if S._daily_path("NQ", S.ALLOW_BP).exists():
        rows = S.load_daily("NQ", S.ALLOW_BP, build=False)
        assert rows[-1]["date"] <= "2025-06-30" and [r for r in rows if r["date"] < "2025"] == base
        doc = json.loads(S._daily_path("NQ", S.ALLOW_BP).read_text())
        assert doc["end"] == "2025-06-30" and doc["rows"][-1]["date"] <= "2025-06-30"
    if S._atr_path("NQ", S.ALLOW_BP).exists():
        own = json.loads(S._atr_path("NQ", S.ALLOW_BP).read_text())
        assert "2025-01-01" <= min(own) and max(own) <= "2025-06-30"
        a = S.load_eve_atr("NQ", build=False, allow_holdout=S.ALLOW_BP)
        assert max(a) <= "2025-06-30" and {k: v for k, v in a.items() if k < "2025"} == S.load_eve_atr("NQ", build=False)
    assert max(S.load_eve_atr("NQ", build=False)) <= "2024-12-31"            # ... nor does the in-sample ATR file
    with pytest.raises(S.HoldoutSealed):                                    # Level-2 features: not opened for it
        S.L2Features(["imb10"], allow_holdout=S.ALLOW_BP)
    with pytest.raises(S.HoldoutSealed):
        S.L2Features(["imb10"])("2025-06-30")


@pytest.mark.parametrize("root", ["ES", "GC"])
def test_the_daily_bars_of_the_other_roots_end_on_2025_06_30_under_their_own_memo_key(root):
    had = (root, True) in S._DAILY_MEMO
    rows = S.load_daily(root, S.ALLOW_BP)
    assert rows and rows[-1]["date"] <= "2025-06-30" and [r for r in rows if r["date"] < "2025"] == S.load_daily(root)
    assert (root, S.ALLOW_BP) in S._DAILY_MEMO and ((root, True) in S._DAILY_MEMO) == had      # never the EXAM key's entry


@pytest.mark.parametrize("root", ROOTS)
def test_a_run_that_ends_2025_06_30_is_accepted_and_one_that_reaches_2025_07_01_raises(root, monkeypatch, tmp_path):
    days = ["2025-06-26", "2025-06-27", "2025-06-30"]
    if not all(_has_tape(d, root) for d in days):
        pytest.skip(f"no 2025 tape for {root} on this machine")
    assert S.load_tape(days[-1], root, allow_holdout=S.ALLOW_BP) is not None
    assert [d.isoformat() for d in S.sessions(days[0], days[-1], root, allow_holdout=S.ALLOW_BP)] == days
    cal = S.sessions(*S.period("bp_build"), root, allow_holdout=S.ALLOW_BP)
    assert cal[0] == S.BP_BUILD[0] and cal[-1] == S.BP_BUILD[1] and len(cal) == BP_SESSIONS[root]
    r = S.run(*DON, period="bp_build", days=days, root=root, workers=1)
    assert r["sessions"] == 3 and r["skipped_by_error"] == 0 and not r["skipped"]
    assert r["meta"]["range"] == BP_RANGE and r["meta"]["days_subset"]
    assert r["trades"] and all(t["date"] in days for t in r["trades"])
    lo, hi = S.et_ns(dt.date(2025, 6, 25), "18:00") // 1_000_000, S.et_ns(dt.date(2025, 6, 30), "18:00") // 1_000_000
    assert all(lo <= t["entry_ms"] <= t["exit_ms"] < hi for t in r["trades"])              # nothing after the last build session
    same = S.run(*DON, days[0], days[-1], root=root, workers=1, allow_holdout=S.ALLOW_BP)   # named dates that end 2025-06-30
    assert same["meta"]["range"] == {"start": days[0], "end": days[-1], "holdout": True, "period": "bp_build"}
    assert [(t["entry_ms"], t["net"]) for t in same["trades"]] == [(t["entry_ms"], t["net"]) for t in r["trades"]]
    _no_data(monkeypatch, tmp_path)
    for fn in (lambda: S.run(*DON, days[0], "2025-07-01", root=root, workers=1, allow_holdout=S.ALLOW_BP),
               lambda: S.run(*DON, period="bp_build", days=days + ["2025-07-01"], root=root, workers=1)):
        with pytest.raises(S.HoldoutSealed, match="2025-06-30"):
            fn()


# ---- identity: ONE bp_build run over days of all three stretches, trade for trade against the stores on disk -----------------
BUILD_DAYS = ("2021-10-05", "2022-06-13", "2023-03-22", "2023-07-03")       # early sample, an NQ roll day, a plain day, a half day
PICK_DAYS = ("2024-01-09", "2024-09-18", "2024-12-18", "2024-12-31")        # ... and the last day before the old seal
H1_DAYS = ("2025-01-02", "2025-03-27", "2025-06-16", "2025-06-30")          # the first day behind it, a GC roll day, the NQ / ES roll
#                                                                             day, the last day of the blueprint BUILD
UNITS = [("orb", "NQ", "15", "pre", "runs_v2", ("or_min5_atr1p5-r2", "or_min30_pts20-r0")),                 # bar-based, NQ daily file
         ("first_bar_mom", "ES", "15", "mid", "runs_v2", ("k1_atr3-r1", "k1_pts5-r0")),                     # daily bars from tape headers
         ("straddle_t_1800", "NQ", "30", "eve", "runs_v2", ("offatr0p5_atr1p5-r2", "offptsB_pct0p2-r0")),   # evening, carried ATR30, pdc
         ("straddle_tight_0830", "GC", "30", "pre", "runs_admit_r1", ("offA_pts1-r2", "offC_pts2-r1"))]     # clock-time, GC


def _runner():
    """out/check2025/run_check.py, the runner that wrote the 2025 stores: its job_grid and its comparison _same are reused."""
    p = S.W / "out" / "check2025"
    if not (p / "run_check.py").exists():
        pytest.skip("out/check2025/run_check.py is not on this machine")
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
    import run_check
    return run_check


@pytest.mark.parametrize("family,root,tf,sess,pick_dir,cells", UNITS)
def test_one_bp_build_run_is_trade_for_trade_what_the_three_stores_hold(family, root, tf, sess, pick_dir, cells):
    import library as LB
    RC = _runner()
    key = f"{family}-{root}-tf{tf}"
    stores = [("runs", key, BUILD_DAYS), (pick_dir, f"{key}-{sess}-pick", PICK_DAYS), ("runs_check2025", f"{key}-{sess}-check", H1_DAYS)]
    for d, k, ds in stores:
        if not (LB.W / d / k / "run.json").exists() or not all(_has_tape(x, root) for x in ds):
            pytest.skip(f"store {d}/{k} or one of its tapes is not on this machine")
    grid, cls, timed = RC.job_grid({"family": family, "root": root, "tf": tf, "sess": sess, "cells": list(cells)})
    days = [x for _, _, ds in stores for x in ds]
    res = S.run_many([c["spec"] for c in grid], period="bp_build", days=days, root=root, workers=2, **getattr(cls, "SCREEN_RUN", {}))
    assert {c["id"] for c in grid} == set(cells)
    for r in res:
        assert r["sessions"] == len(days) and r["skipped_by_error"] == 0 and r["meta"]["range"] == BP_RANGE
        assert all(t["date"] in days for t in r["trades"])                    # every trade falls into one of the three comparisons
        if not timed:                                                         # the unit's session instance only, as the runner keeps it
            r["trades"] = [t for t in r["trades"] if S.session_of(t["entry_ms"]) == sess]
    for d, k, ds in stores:
        part = [{**r, "trades": [t for t in r["trades"] if t["date"] in ds]} for r in res]
        n_cells, n, diff = RC._same(grid, part, LB.load_unit(k, LB.W / d), ds, sess, True)
        assert (n_cells, diff) == (len(cells), 0) and n > 0, f"{d}/{k}: {diff} of {n_cells} cells differ ({n} stored trades on {len(ds)} days)"
