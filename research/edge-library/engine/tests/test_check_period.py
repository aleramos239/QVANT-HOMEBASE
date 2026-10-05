"""The CHECK period (EDGE_SPEC "PERIODS AMENDED", 2026-10-04): 2025 is opened by allow_check=True and by nothing else; a date
from 2026-01-01 on is still refused under that flag; with no flag 2025 is refused exactly as before; BUILD and 2024 are
untouched (a few days of one family, trade for trade against the stores written before the change). No P&L is asserted."""
import datetime as dt
import json

import numpy as np
import pytest

import l2ref
import l2sim as S

ROOTS = ["NQ", "ES", "GC"]


def _has_tape(d, root):
    return (S.tape_path(d, root).exists() if root == "NQ" else S.hb_tape_path(d, root) is not None)


def test_check_is_one_year_and_the_exam_starts_right_after_it():
    assert S.CHECK == (dt.date(2025, 1, 1), dt.date(2025, 12, 31)) and S.CHECK[0] == S.HOLDOUT_START == S.EXAM_START
    assert S.PICK[1] < S.CHECK[0] and S.CHECK[1] + dt.timedelta(days=1) == dt.date(2026, 1, 1)
    assert S.period("check") == S.CHECK and S.period("CHECK") == S.CHECK and "check" not in S.PERIODS
    with pytest.raises(S.HoldoutSealed):
        S.period("exam")
    assert [S.period_of(*x) for x in (S.CHECK, ("2025-03-03", "2025-03-07"), ("2026-01-02", "2026-03-01"), ("2025-12-01", "2026-01-02"),
                                      ("2024-12-01", "2025-01-10"), S.BUILD, S.PICK)] == ["check", "check", "exam", "exam", "mixed", "build", "pick"]


def test_the_switch_is_the_literal_true_only():
    assert S.allow_level() is False and S.allow_level(allow_check=True) == S.ALLOW_CHECK
    assert S.allow_level(allow_holdout=True) is True and S.allow_level(allow_exam=True) is True
    assert S.allow_level(True, False, True) is True                       # the EXAM key is not narrowed by the check flag
    for v in (1, "yes", "True", "exam", [True], np.True_):
        assert S.allow_level(allow_check=v) is False and S.allow_level(allow_holdout=v) is False


def test_the_guard_opens_2025_and_nothing_later():
    for d in ("2025-01-01", "2025-01-02", "2025-06-16", "2025-12-31", "2021-09-22", "2024-12-31"):
        S.check_holdout(d, S.ALLOW_CHECK)
    for d in ("2026-01-01", "2026-01-02", "2026-07-08", "2027-03-01"):
        with pytest.raises(S.HoldoutSealed, match="2026"):
            S.check_holdout(d, S.ALLOW_CHECK)
    for d in ("2025-01-01", "2025-06-16", "2025-12-31", "2026-01-02"):       # no flag / a non-literal flag: as before
        for flag in (False, None, 1, "yes", "True"):
            with pytest.raises(S.HoldoutSealed):
                S.check_holdout(d, flag)
    S.check_holdout("2026-01-02", True)                                     # the EXAM key itself is unchanged


@pytest.mark.parametrize("root", ROOTS)
def test_default_refuses_2025_exactly_as_before(root):
    for fn in (lambda: S.load_tape("2025-01-02", root), lambda: S.sessions("2024-12-01", "2025-01-10", root),
               lambda: S.sessions(*S.CHECK, root), lambda: S.run(l2ref.Donchian, {"tf": "15"}, period="check", root=root, workers=1),
               lambda: S.run(l2ref.Donchian, {"tf": "15"}, "2025-02-03", "2025-02-05", root=root, workers=1),
               lambda: S.run(l2ref.Donchian, {"tf": "15"}, days=["2025-02-03"], root=root, workers=1),
               lambda: S.run(l2ref.Donchian, {"tf": "15"}, "2025-02-03", "2025-02-05", root=root, workers=1, allow_check=1),
               lambda: S.build_tapes(root, "2024-12-01", "2025-01-10") if root != "NQ" else S.check_exam("2025-01-02")):
        with pytest.raises(S.HoldoutSealed):
            fn()


@pytest.mark.parametrize("root", ROOTS)
def test_the_check_flag_refuses_everything_that_touches_2026(root):
    for fn in (lambda: S.load_tape("2026-01-02", root, allow_check=True), lambda: S.load_tape("2026-01-02", root, allow_holdout=S.ALLOW_CHECK),
               lambda: S.sessions("2025-12-01", "2026-01-02", root, allow_check=True),
               lambda: S.sessions("2026-01-01", "2026-01-02", root, allow_check=True),
               lambda: S.run(l2ref.Donchian, {"tf": "15"}, "2025-12-29", "2026-01-02", root=root, workers=1, allow_check=True),
               lambda: S.run(l2ref.Donchian, {"tf": "15"}, days=["2025-12-31", "2026-01-02"], root=root, workers=1, allow_check=True),
               lambda: S.run_many([(l2ref.Donchian, {"tf": "15"})], "2025-01-02", "2026-12-31", root=root, workers=1, allow_check=True),
               lambda: S.build_tapes(root, "2025-12-01", "2026-01-02", allow_check=True) if root != "NQ" else S.check_holdout("2026-01-02", S.ALLOW_CHECK),
               lambda: S._tapes_one(("2026-01-02", root, S.ALLOW_CHECK)), lambda: S._atr_one(("2026-01-02", root, S.ALLOW_CHECK)),
               lambda: S._tapes_one(("2025-01-02", root)), lambda: S._tapes_one(("2025-01-02", root, True))):    # the builder: never the EXAM key
        with pytest.raises(S.HoldoutSealed):
            fn()


def test_check_caches_are_their_own_files_and_hold_nothing_from_2026():
    assert S._daily_path("NQ", False).name == "daily_NQ.json" and S._daily_path("NQ", True).name == "daily_NQ_holdout.json"
    assert S._daily_path("NQ", S.ALLOW_CHECK).name == "daily_NQ_check.json" and S._daily_path("NQ", "yes").name == "daily_NQ.json"
    assert S._atr_path("NQ").name == "eve_atr30_NQ.json" and S._atr_path("NQ", True).name == "eve_atr30_NQ_check.json"
    assert S._seal_end(False) == S.IN_SAMPLE[1] and S._seal_end(S.ALLOW_CHECK) == S.CHECK[1] and S._seal_end("yes") == S.IN_SAMPLE[1]
    base = S.load_daily("NQ")
    assert base and base[-1]["date"] <= "2024-12-31"                        # the in-sample file never holds a 2025 row
    assert max(S.load_eve_atr("NQ", build=False)) <= "2024-12-31"
    if S._daily_path("NQ", S.ALLOW_CHECK).exists():
        rows = S.load_daily("NQ", S.ALLOW_CHECK, build=False)
        assert rows[-1]["date"] <= "2025-12-31" and [r for r in rows if r["date"] < "2025"] == base
        assert json.loads(S._daily_path("NQ", S.ALLOW_CHECK).read_text())["end"] == "2025-12-31"
    if S._atr_path("NQ", True).exists():
        a = S.load_eve_atr("NQ", build=False, allow_holdout=S.ALLOW_CHECK)
        assert "2025-12-31" >= max(a) > "2025" and min(json.loads(S._atr_path("NQ", True).read_text())) >= "2025-01-01"
    with pytest.raises(S.HoldoutSealed):                                    # Level-2 features: not opened for CHECK
        S.L2Features(["imb10"], allow_holdout=S.ALLOW_CHECK)
    with pytest.raises(S.HoldoutSealed):                                    # a features loader without the EXAM key refuses 2025
        S.L2Features(["imb10"])("2025-02-03")


@pytest.mark.parametrize("root", ROOTS)
def test_2025_runs_with_the_flag_and_every_trade_is_dated_2025(root):
    days = ["2025-02-03", "2025-02-04", "2025-02-05"]
    if not all(_has_tape(d, root) for d in days):
        pytest.skip(f"no 2025 tape for {root} on this machine")
    assert S.load_tape(days[0], root, allow_check=True) is not None
    assert [d.isoformat() for d in S.sessions(days[0], days[-1], root, allow_check=True)] == days
    r = S.run(l2ref.Donchian, {"tf": "15"}, days[0], days[-1], root=root, workers=1, allow_check=True)
    assert r["sessions"] == 3 and r["skipped_by_error"] == 0 and not r["skipped"]
    assert r["meta"]["range"] == {"start": days[0], "end": days[-1], "holdout": True, "period": "check"}
    assert r["trades"] and all(days[0] <= t["date"] <= days[-1] for t in r["trades"])
    lo, hi = S.et_ns(dt.date(2025, 2, 2), "18:00") // 1_000_000, S.et_ns(dt.date(2025, 2, 5), "18:00") // 1_000_000
    assert all(lo <= t["entry_ms"] < hi for t in r["trades"])
    same = S.run(l2ref.Donchian, {"tf": "15"}, days=days, root=root, workers=1, allow_holdout=S.ALLOW_CHECK)
    assert [(t["entry_ms"], t["net"]) for t in same["trades"]] == [(t["entry_ms"], t["net"]) for t in r["trades"]]


def test_the_last_check_day_runs_and_the_first_exam_day_does_not():
    if not _has_tape("2025-12-31", "NQ"):
        pytest.skip("no 2025 tape on this machine")
    r = S.run(l2ref.Donchian, {"tf": "15"}, "2025-12-30", "2025-12-31", workers=1, allow_check=True)
    assert r["sessions"] == 2 and r["meta"]["range"]["period"] == "check"
    with pytest.raises(S.HoldoutSealed):
        S.run(l2ref.Donchian, {"tf": "15"}, "2025-12-30", "2026-01-01", workers=1, allow_check=True)


# ---- BUILD and 2024 are unchanged: one family, a few days, trade for trade against the stores on disk ----------------
BUILD_DAYS = ("2022-03-15", "2022-09-21", "2023-07-03", "2023-12-13")
PICK_DAYS = ("2024-01-09", "2024-06-12", "2024-09-18", "2024-12-18")


def _stored(u, cid, days, sess, lb):
    idx = {c["id"]: i for i, c in enumerate(u["meta"]["cells"])}
    x = lb.unit_cell(u, idx[cid])
    m = np.isin(x["date"], [dt.date.fromisoformat(d).toordinal() for d in days]) & (x["sess"] == lb.SESS_CODE[sess])
    return sorted(zip(x["entry_ms"][m].tolist(), np.round(x["net"][m], 2).tolist()))


@pytest.mark.parametrize("period,days,runs,key", [("build", BUILD_DAYS, "runs", "orb-NQ-tf15"), ("pick", PICK_DAYS, "runs_v2", "orb-NQ-tf15-pre-pick")])
def test_build_and_2024_are_trade_for_trade_what_the_stores_hold(period, days, runs, key):
    import families as F
    import library as LB
    if not (LB.W / runs / key / "run.json").exists():
        pytest.skip(f"store {runs}/{key} is not on this machine")
    u = LB.load_unit(key, LB.W / runs)
    grid = F.unit_grid("orb", "NQ", "15")[::8]                               # 12 of the 96 cells
    specs = [(c["spec"][0], {**c["spec"][1], "sess": "pre", "hold_to": "day"}) for c in grid]
    res = S.run_many(specs, days=list(days), root="NQ", workers=2)
    n = 0
    for c, r in zip(grid, res):
        assert r["skipped_by_error"] == 0 and r["meta"]["range"]["period"] == "insample"
        mine = sorted((t["entry_ms"], round(t["net"], 2)) for t in r["trades"] if S.session_of(t["entry_ms"]) == "pre")
        ref = _stored(u, c["id"], days, "pre", LB)
        assert mine == ref, f"{key} cell {c['id']}: {len(mine)} trades now, {len(ref)} in the store"
        n += len(ref)
    assert n > 0
