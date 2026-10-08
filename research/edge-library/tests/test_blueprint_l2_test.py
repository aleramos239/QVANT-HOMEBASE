"""A LEVEL 2 IDEA IS LOCKED AND TESTED (BLUEPRINT.md section 2, "what version 1 refuses"; engine/btfeat.py = the test days' Level 2 table).

  (a) THE TEST RANGE of a Level 2 idea ends where the table ends (runner.test_range's `cap`, the way a delta idea's ends where the
      flow file ends); a table that ends before the second part of the test leaves no range; no table = a refusal that says so.
  (b) THE FREEZE no longer refuses a Level 2 filter: it locks it (on build days, nothing of 2025-07-01 on is opened) and freezes the
      range up to the table's last day -- NQ only, still.
  (c) THE RUNNER (runner.run_test): a Level 2 unit is run with the test table's loader (BtL2Features, the test seal) and with nothing
      else; the other stores of the read take no features; a store's run.json keeps a plain marker; refused: a range that ends after
      the table, no table.
No test day is read: the engine is a stub that records what it was asked, and the table of the loader is never opened.
  pytest tests/test_blueprint_l2_test.py -q
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blueprint_frozen as F  # noqa: E402

import judge as J  # noqa: E402
from blueprint import freeze as FRZ  # noqa: E402
from blueprint import records as REC  # noqa: E402
from blueprint import runner as RUN  # noqa: E402

import l2sim as S  # noqa: E402
import run_idea as RI  # noqa: E402

import bpfeat  # noqa: E402
import btfeat  # noqa: E402

NAME = "bpl_book"
RUN_L2 = {"filters": [{"block": "book", "side": "agree"}]}
IS = F.IS


def setup_function(_=None):
    F.env_on()


def teardown_function(_=None):
    F.env_off()


# ================================================================ (a) the test range

def _archive(base: Path, days: dict, tapes) -> None:
    for d, ok in days.items():
        f = base / "ticks" / "NQ" / d[:4] / f"{d}_NQZ5.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"root": "NQ", "contract": "NQZ5", "session_date": d, "ticks": 5000, "complete": ok}))
    for d in tapes:
        f = base / "tape" / "NQ" / d[:4] / d[5:7] / f"{d}.parquet"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("")


@contextlib.contextmanager
def _disk(base: Path):
    keep = (S.ARCHIVE, S.TAPE_DIR, S.HB_TAPE, S.OWN_TAPE)
    S.ARCHIVE, S.TAPE_DIR, S.HB_TAPE, S.OWN_TAPE = base / "ticks", base / "tape", base / "hb", base / "own"
    try:
        yield
    finally:
        S.ARCHIVE, S.TAPE_DIR, S.HB_TAPE, S.OWN_TAPE = keep


DAYS = ["2025-07-01", "2025-07-02", "2025-12-31", "2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]


def test_the_test_range_of_a_level_2_idea_ends_where_the_table_ends():
    base = F.tmp() / "archive_l2"
    _archive(base, {d: True for d in DAYS}, DAYS)
    with _disk(base), F.no_engine():
        plain = RUN.test_range("NQ")
        assert plain["end"] == "2026-01-07" and plain["sessions"] == 7 and "capped_by_filter" not in plain
        r = RUN.test_range("NQ", dt.date(2026, 1, 5))                   # the table's last day: the range stops there ...
        assert (r["end"], r["sessions"]) == ("2026-01-05", 5) and r["capped_by_filter"] == {"data_ends": "2026-01-05", "sessions_left_out": 2}
        assert [p["sessions"] for p in r["parts"]] == [3, 2] and r["parts"][1]["end"] == "2026-01-05"
        assert RUN.test_range("NQ", "2026-01-05") == r                  # (a date as ISO text too)
        assert RUN.test_range("NQ", dt.date(2027, 1, 1)) == plain       # a table that outlasts the archive caps nothing
        F.refused(lambda: RUN.test_range("NQ", dt.date(2025, 6, 30)), "ends 2025-06-30, before the first test day")
        F.refused(lambda: RUN.test_range("NQ", dt.date(2025, 12, 31)), "Jan-Sep 2026 would have no session")      # line 4.1 reads both parts


def test_the_freeze_takes_the_end_of_the_range_from_the_filters_data(monkeypatch):
    base = F.tmp() / "archive_l2_freeze"
    _archive(base, {d: True for d in DAYS}, DAYS)
    last = {"l2": dt.date(2026, 1, 6)}
    monkeypatch.setattr(btfeat, "last_date", lambda: last["l2"])
    monkeypatch.setattr(FRZ.flowtab, "last_date", lambda market: dt.date(2026, 1, 5))
    assert FRZ._reads("book_agree") == {"flow": False, "l2": True} and FRZ._reads("wall_clear")["l2"] and FRZ._reads("stack_with")["l2"]
    assert FRZ._reads("delta_with") == {"flow": True, "l2": False} and FRZ._reads("ema20_above") == {"flow": False, "l2": False} and FRZ._reads(None) == {"flow": False, "l2": False}
    with _disk(base), F.no_engine():
        assert FRZ._range("NQ", True)["end"] == "2026-01-07"                                  # no data limit: the archive's end
        assert FRZ._range("NQ", True, l2=True)["end"] == "2026-01-06"                         # the Level 2 table's last day
        assert FRZ._range("NQ", True, flow=True)["end"] == "2026-01-05"                       # the flow file's
        assert FRZ._range("NQ", True, flow=True, l2=True)["end"] == "2026-01-05"              # both: the earlier of the two
        last["l2"] = dt.date(2026, 1, 2)
        assert FRZ._range("NQ", True, flow=True, l2=True)["end"] == "2026-01-02"
    monkeypatch.undo()                                                                       # the real last_date ... and no table: the freeze says so
    monkeypatch.setattr(btfeat, "cache_file", lambda: F.tmp() / "no_such_table.parquet")
    btfeat._LAST.clear()
    with _disk(base), F.no_engine():
        why = F.refused(lambda: FRZ._range("NQ", True, l2=True), "not built")
        assert "btfeat.py" in why
        assert FRZ._range("NQ", False, l2=True)["none"] and FRZ._range("NQ", False, l2=True)["end"] is None      # a neighbor without a range is said in its place


# ================================================================ (b) the freeze

def test_a_level_2_idea_is_locked_and_its_range_ends_with_the_table(monkeypatch):
    if not btfeat.cache_file().exists():
        pytest.skip("the test days' Level 2 table is not built here (python engine/btfeat.py)")
    master = F.lead(NAME, run=RUN_L2)
    root = F.tmp() / "ideas" / "l2lock"
    import shutil
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(master / NAME, root / NAME)
    calls = []
    keep = S.run_many

    def watched(specs, *a, **k):
        calls.append({"args": [str(x) for x in a], "allow_holdout": k.get("allow_holdout"), "period": k.get("period"), "days": k.get("days")})
        return keep(specs, *a, **k)

    monkeypatch.setattr(S, "run_many", watched)
    with F.tiny(**F.settings(NAME)):
        r = FRZ.lock(NAME, root)
    lock = r["lock"]
    assert lock["home"]["filter"] and lock["home"]["filter"].startswith("book")
    rng = lock["test_range"]["NQ"]
    assert rng["start"] == "2025-07-01" and rng["end"] <= btfeat.last_date().isoformat() and rng["sessions"] > 200
    assert rng["end"] == btfeat.last_date().isoformat() or rng.get("capped_by_filter")        # ends with the table (a session before it may be the archive's last)
    assert all(c["days"] and max(c["days"]) <= "2025-06-30" and c["period"] == RUN.PERIOD for c in calls), calls     # the freeze ran on build days only
    assert (r["status"], r["phase"]) == ("lead", 3) and (root / NAME / "lock.json").exists()          # frozen: phase 3, its lock on file
    assert FRZ.verify(lock, REC._spec(NAME, REC._json(root / NAME / "spec.json"))) == []


# ================================================================ (c) the runner

class Stop(Exception):
    pass


def _spec():
    sp = RUN.checked({"name": "bpl_l2run", "reason": F.CARD["why"], "family": "orb", "markets": ["NQ"], "bar_sizes": ["15"], "sessions": ["nyam"], "params": {"or_min": ["5", "15"]},
                      "exits": "standard", "filters": [{"block": "book", "side": "agree"}], "limits": {}})
    u = next(x for x in RI.spec_units(sp) if x["filter"])
    return sp, u


def _stub(calls):
    def run_many(specs, a, b, days=None, root=None, workers=1, allow_holdout=None, **kw):
        calls.append({"n": len(specs), "args": [str(a), str(b)], "days": list(days), "root": root, "allow_holdout": allow_holdout, **kw})
        return [{"trades": [], "skipped_by_error": 0, "no_trade": [], "elapsed_s": 0.0, "meta": {"inputs": {"sess": "nyam"}}} for _ in specs]
    return run_many


def test_run_test_hands_a_level_2_unit_the_test_tables_loader(monkeypatch, tmp_path):
    sp, u = _spec()
    key, sess = u["key"], "nyam"
    cells = [c["id"] for c in u["grid"]][:2]
    root = tmp_path / "ideas"
    root.mkdir()
    end = "2026-01-07"
    IS.claim_read("bpl_l2run", version=1, lock="ab" * 8, rng={"start": "2025-07-01", "end": end}, root=root)
    table = tmp_path / "t.parquet"
    pd.DataFrame({"date": [dt.date(2026, 1, 7)]}).to_parquet(table)                     # a table that ends 2026-01-07 (only its last date is read here)
    monkeypatch.setattr(btfeat, "cache_file", lambda: table)
    btfeat._LAST.clear()
    calls = []
    monkeypatch.setattr(S, "run_many", _stub(calls))
    monkeypatch.setattr(S, "sessions", lambda a, b, root, **k: [dt.date(2025, 7, 1), dt.date(2025, 7, 2)])
    out, led = tmp_path / "runs_test", tmp_path / "ledger.csv"
    with F.tiny():
        res = RUN.run_test("bpl_l2run", {"version": 1, "lock": "ab" * 8}, sp, key, sess, cells, "bpl_l2run", end, 1, out, ideas=root, ledger=led, days=["2025-07-01", "2025-07-02"])
    assert res["calendar"] == ["2025-07-01", "2025-07-02"] and len(res["stores"]) == 3
    K = RUN.test_keys(key, "bpl_l2run", "NQ", "15", sess)
    byk = {}
    for c in calls:
        assert c["allow_holdout"] == S.ALLOW_BT == "bp_test" and c["root"] == "NQ" and c["args"] == ["2025-07-01", end]
        byk.setdefault(type(c.get("features")).__name__, []).append(c)
    assert sorted(byk) == ["BtL2Features", "NoneType"] and len(byk["BtL2Features"]) == 2 and len(byk["NoneType"]) == 1          # the table + its worse fills; the pool takes none
    for c in byk["BtL2Features"]:
        f = c["features"]
        assert f.allow_holdout == S.ALLOW_BT and f.columns == tuple(RUN._blocks().BOOK_COLS) and not isinstance(f, bpfeat.BpL2Features)
    assert [c.get("slip_ticks") for c in byk["BtL2Features"]] == [None, 2.0]                                      # the table, then the same cells with worse fills
    # the stores keep the plain marker, JSON all through (a store's run.json is never a pickled object)
    marks = {k: json.loads((out / K[k] / "run.json").read_text())["run_kw"] for k in ("table", "worse", "pool")}
    assert marks["table"] == {"features": RUN.L2T} and marks["worse"]["features"] == RUN.L2T == "bt_l2" and "features" not in marks["pool"] and RUN.L2T != RUN.L2


def test_run_test_refuses_a_level_2_unit_the_table_does_not_cover(monkeypatch, tmp_path):
    sp, u = _spec()
    cells = [c["id"] for c in u["grid"]][:2]
    root = tmp_path / "ideas"
    root.mkdir()
    IS.claim_read("bpl_l2run", version=1, lock="ab" * 8, rng={"start": "2025-07-01", "end": "2026-09-22"}, root=root)
    asked = []
    monkeypatch.setattr(S, "run_many", _stub(asked))

    def go(end, **kw):
        with F.tiny():
            return RUN.run_test("bpl_l2run", {"version": 1, "lock": "ab" * 8}, sp, u["key"], "nyam", cells, "bpl_l2run", end, 1, tmp_path / "out", ideas=root,
                                ledger=tmp_path / "led.csv", days=["2025-07-01"], **kw)

    monkeypatch.setattr(btfeat, "cache_file", lambda: tmp_path / "not_built.parquet")
    btfeat._LAST.clear()
    assert "not built" in F.refused(lambda: go("2026-01-07", dry=True), "is not built")                    # no table: refused before anything is asked
    table = tmp_path / "t.parquet"
    pd.DataFrame({"date": [dt.date(2026, 7, 7)]}).to_parquet(table)
    monkeypatch.setattr(btfeat, "cache_file", lambda: table)
    btfeat._LAST.clear()
    why = F.refused(lambda: go("2026-09-22", dry=True), "no later than the last day")                 # a range that outlasts the table
    assert "2026-07-07" in why
    assert go("2026-07-07", dry=True)["calendar"] is None and asked == []                              # ... one that ends with it is taken (a preflight)
    # NQ only: a Level 2 filter on another market never reaches the runner (checked() refuses the spec)
    F.refused(lambda: RUN.checked({"name": "bpl_l2es", "reason": F.CARD["why"], "family": "orb", "markets": ["ES"], "bar_sizes": ["15"], "sessions": ["nyam"], "params": {},
                                   "exits": "standard", "filters": [{"block": "book", "side": "agree"}]}), "NQ only")
