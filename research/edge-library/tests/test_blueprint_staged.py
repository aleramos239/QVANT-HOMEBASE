"""The STAGED build (blueprint/records.py `run`, runner.run_build(stage=...); the owner, 2026-10-07): the 10-seed random-entry
control is the slow part of a round, so it is run only for an idea that passes every OTHER line.

  stage "units"   the idea's own tables, and every line that needs no random table (2.1, 2.2, 2.4-2.9)
  stage "pools"   the control pools and line 2.3 -- only when stage 1 left no failed line

(a) runner.parts: "units" holds no pool, "pools" holds nothing else, "all" is as it was; a stage that does not exist is refused;
(b) a round with a failed line writes no pool: line 2.3 says "not run" (passed None, skipped), the round fails on the line that failed;
(c) a round whose other lines all pass runs the pool and reads 2.3 against it;
(d) the pool another round wrote is reused (nothing runs twice).
TINY RUNS ONLY (3 named build days, 2 exit cells, NQ 15- and 5-minute bars), the same as tests/test_blueprint_ideas.py.

  pytest tests/test_blueprint_staged.py -q
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
import judge as J  # noqa: E402
import test_blueprint_ideas as TI  # noqa: E402
from blueprint import records as REC  # noqa: E402
from blueprint import runner as RUN  # noqa: E402

NAME = "bps_orb"


@pytest.fixture()
def folders():
    TI.setup_function()
    REC.STAGED = True
    with tempfile.TemporaryDirectory(prefix="bp_staged_") as d:
        d = Path(d)
        yield {"root": d / "ideas", "out": d / "runs", "ledger": d / "ledger.csv", "tester": d / "tester"}
    TI.teardown_function()


def tiny(f):
    return TI.tiny(out=str(f["out"]), ledger=str(f["ledger"]), tester=str(f["tester"]))


def stores(f) -> list:
    return sorted(p.name for p in f["out"].iterdir() if (p / "run.json").exists()) if f["out"].exists() else []


def test_the_stages_of_a_build_are_the_units_the_pools_or_everything():
    sp = RUN.checked({"name": "bps_x", "reason": "Breaks of the opening range trap the traders who leaned on it.", "family": "orb", "markets": ["NQ"],
                      "bar_sizes": ["15", "5"], "sessions": ["nyam"], "params": {"or_min": ["5", "15"]}, "exits": "standard"})
    kinds = lambda st: [p["kind"] for p in RUN.parts(sp, stage=st)]  # noqa: E731
    assert kinds("all") == ["pool", "unit", "pool", "unit"] and kinds("units") == ["unit", "unit"] and kinds("pools") == ["pool", "pool"]
    assert [p["key"] for p in RUN.parts(sp, stage="all")] == [p["key"] for p in RUN.parts(sp)]
    with pytest.raises(J.Refuse, match="stage"):
        RUN.parts(sp, stage="some")


def test_a_round_with_a_failed_line_runs_no_control_pool(folders):
    f = folders
    REC.card(NAME, TI.idea(NAME), f["root"])
    with tiny(f):
        r = REC.build(NAME, TI.REASONS[1], root=f["root"])
    assert stores(f) == [f"{NAME}-NQ-tf15", f"{NAME}-NQ-tf5"]                  # the tables, no c1-... pool
    assert [s["kind"] for s in r["stores"]] == ["unit", "unit"]
    b = TI.by(r)
    assert b["2.3"]["passed"] is None and b["2.3"]["skipped"] is True and "not run" in b["2.3"]["text"]
    assert b["2.8"]["passed"] is None and b["2.8"]["skipped"] is True and "not run" in b["2.8"]["text"]          # the Monte Carlo waits too
    assert r["skipped"] == ["2.3", "2.8"] and "2.3" not in r["not_applicable"] and r["failed"] and not r["passed"]
    assert [x["line"] for x in r["lines"]] == TI.BUILD_LINES                      # every line is still in the result


def test_a_round_whose_other_lines_pass_runs_the_pool_and_reads_2_3(folders):
    f = folders
    REC.card(NAME, TI.idea(NAME), f["root"])
    with tiny(f), TI.passing():
        r = REC.build(NAME, TI.REASONS[1], root=f["root"])
    assert stores(f) == [f"{NAME}-NQ-tf15", f"{NAME}-NQ-tf5", "c1-NQ-tf15", "c1-NQ-tf5"]
    assert [s["kind"] for s in r["stores"]] == ["unit", "unit", "pool", "pool"]
    b = TI.by(r)
    assert b["2.3"].get("skipped") is None and b["2.3"]["controls"]["c1"]["replicates"] == 200 and r["skipped"] == [] and r["passed"]
    # a second round reuses everything on disk: nothing runs twice
    with TI.tiny(out=str(f["out"]), ledger=str(f["ledger"])), TI.passing(), TI.no_engine():       # (no tester: showing the default variant runs the engine again)
        r2 = REC.build(NAME, TI.REASONS[2], root=f["root"])
    assert all(s["skipped"] for s in r2["stores"]) and r2["round"] == 2


def test_a_failed_monte_carlo_stops_the_round_before_the_pools(folders):
    f = folders
    REC.card(NAME, TI.idea(NAME), f["root"])
    keep = REC.LINES
    try:
        with TI.passing():
            REC.LINES = tuple((lambda t, g=g: (lambda r: {**r, "passed": False} if r["line"] == "2.8" and r["passed"] is not None else r)(g(t))) for g in REC.LINES)
            with tiny(f):
                r = REC.build(NAME, TI.REASONS[1], root=f["root"])
    finally:
        REC.LINES = keep
    assert stores(f) == [f"{NAME}-NQ-tf15", f"{NAME}-NQ-tf5"]                  # the Monte Carlo was read and failed: no pool
    b = TI.by(r)
    assert b["2.8"]["passed"] is False and b["2.3"]["passed"] is None and b["2.3"]["skipped"] is True and r["failed"] == ["2.8"]
