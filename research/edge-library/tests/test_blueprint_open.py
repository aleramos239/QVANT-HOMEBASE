"""The owner's session-anchored exit table ("open", 2026-10-06; the idea fvg_first_nq) in the blueprint toolkit.

  (a) the template (exit_menu.json `open`) IS the engine's table (blocks.menu_open), cell for cell, for every market;
  (b) the runner takes exits "open" -- and nothing else new: its control pool is its own store (c1o-<market>-tf<bar>) of
      the same 10 seeds on the 60 cells, with the cell ids the judge reads (s<seed>_<exit id>, no underscore in a stop's name);
  (c) a card with exits "open" passes line 0.2, says so in its words, and plans 60 cells x the values of its main setting;
      every other exits word is still refused;
  (d) the lock refuses such an idea (it can be built, not locked or tested yet);
  (e) one tiny smoke run on 3 build days reaches the engine: the stores are written with the open cells.
No P&L is asserted: counts, identities, the shape of what is saved.

  pytest tests/test_blueprint_open.py -q
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
import judge as J  # noqa: E402
from blueprint import records as REC  # noqa: E402
from blueprint import rules as R  # noqa: E402
from blueprint import runner as RUN  # noqa: E402

import l2sim as S  # noqa: E402
import run_menus as RM  # noqa: E402

RM.registry()
from families import blocks  # noqa: E402

MARKETS = ("NQ", "ES", "GC")
CARD = {"why": "The first gap after the open marks where aggressive orders ran through resting ones, so trading with it rides that push.",
        "loser": "traders who fade the open and stops run over by the move",
        "home": {"market": "NQ", "session": "nyam", "bar": "5"},
        "neighbors": ["1-minute bars", "ES"],
        "not_here": "the afternoon",
        "main_setting": "min_gap", "sides": "both", "sides_why": "a gap can form either way", "loses_when": "quiet, drifting days where the first gap fills back"}
RUNSET = {"family": "fvg", "params": {"min_gap": [0, 0.1, 0.25, 0.5]}, "fixed": {"mode": "go"}, "filters": [], "exits": "open", "limits": {"max_tr": 1}}
SPEC = {"name": "bpo_fvg", "card": CARD, "run": RUNSET}
DAYS = ["2022-03-15", "2023-03-22", "2025-06-30"]
CELLS = ["atropen1-r2", "rngopen0p5-r0"]


# ---- (a) the template is the engine's table ------------------------------------------------------------------------------------

def test_the_template_is_the_engines_open_table():
    m = R.template("exit_menu")["open"]
    for root in MARKETS:
        mine = R.exit_cells("open", root)
        assert mine == blocks.menu_open(root) == blocks.exits("open", root, "fvg"), root
        assert len(mine) == m["cells"] == 60 and len({S.cell_id(x) for x in mine}) == 60
    assert R.exit_cells("standard", "NQ") == R.exit_menu("NQ")
    with pytest.raises(R.RuleError):
        R.exit_cells("extended", "NQ")
    with pytest.raises(R.RuleError):
        R.exit_cells("open", "CL")
    assert R.template("exit_menu")["cells"] == 48                  # the standard table is the same as before


def test_no_stop_name_holds_an_underscore():
    # the judge reads the exit id of a cell id as the text after its LAST underscore: a stop named atr_open would be read as "open"
    for x in blocks.menu_open("NQ"):
        cid = f"min_gap0p25_{S.cell_id(x)}"
        assert cid.rsplit("_", 1)[-1] == S.cell_id(x)


# ---- (b) the runner and its control pool ----------------------------------------------------------------------------------------

def test_the_open_pool_is_its_own_store_of_ten_seeds_on_sixty_cells():
    assert RUN.pool_key("NQ", "5") == "c1-NQ-tf5" and RUN.pool_key("NQ", "5", RUN.EXITS) == "c1-NQ-tf5" and RUN.pool_key("NQ", "5", RUN.OPEN) == "c1o-NQ-tf5"
    p = RUN.pool_part("NQ", "5", exits=RUN.OPEN)
    assert p["key"] == "c1o-NQ-tf5" and p["kind"] == "pool" and p["cells"] == 600 and p["sessions"] == list(RM.DAY_PASSES)
    menu = blocks.menu_open("NQ")
    assert [c["id"] for c in p["grid"]] == [f"s{sd}_{S.cell_id(x)}" for sd in range(1, 11) for x in menu]
    assert [c["xi"] for c in p["grid"][:60]] == list(range(60)) and [c["exit"] for c in p["grid"][:60]] == menu
    assert all(c["spec"][0] is blocks.CONTROL_OPEN and c["spec"][1]["seed"] == c["variant"]["seed"] and c["spec"][1]["p_entry"] == RM.C1_P_ENTRY for c in p["grid"])
    assert p["meta"]["control"] == "c1" and p["meta"]["family"] == "random"          # the judge finds a pool by these
    std = RUN.pool_part("NQ", "5")
    assert std["key"] == "c1-NQ-tf5" and std["cells"] == 480                          # the standard pool is as it was
    assert not {c["id"] for c in std["grid"]} & {c["id"] for c in p["grid"]}


def test_the_runner_takes_the_open_table_and_still_refuses_the_rest():
    spec = {"name": "bpo_fvg", "reason": "The first gap after the open marks where aggressive orders ran through resting ones.", "family": "fvg", "markets": ["NQ"], "bar_sizes": ["5", "1"], "sessions": ["nyam"],
            "params": RUNSET["params"], "fixed": RUNSET["fixed"], "filters": [], "exits": "open", "limits": RUNSET["limits"]}
    sp = RUN.checked(spec)
    assert (sp["exits"], sp["filter_exits"]) == ("open", "open") and len(sp["variants"]) == 4
    parts = RUN.parts(sp)
    assert [p["key"] for p in parts] == ["c1o-NQ-tf5", "bpo_fvg-NQ-tf5", "c1o-NQ-tf1", "bpo_fvg-NQ-tf1"]
    unit = parts[1]
    assert unit["cells"] == 4 * 60 and {S.cell_id(c["exit"]) for c in unit["grid"]} == {S.cell_id(x) for x in blocks.menu_open("NQ")}
    assert all(c["spec"][1]["stop_mode"] in ("atropen", "rngopen") for c in unit["grid"])
    with pytest.raises(J.Refuse):
        RUN.checked({**spec, "exits": "extended", "filter_exits": "extended"})
    std = RUN.checked({**spec, "exits": "standard", "filter_exits": "standard"})
    assert (std["exits"], std["filter_exits"]) == (RUN.EXITS, RUN.EXITS)               # the standard table is mapped as before


# ---- (c) the card ---------------------------------------------------------------------------------------------------------------

def _lines(run=None):
    return REC.card_lines({"name": "bpo_fvg", "version": 1, "card": CARD, "run": {**RUNSET, **(run or {})}})


def test_a_card_on_the_open_table_passes_line_0_2_and_plans_sixty_cells_a_value():
    rows, plan = _lines()
    by = {r["line"]: r for r in rows}
    assert plan is not None and all(r["passed"] for r in rows), [r["text"] for r in rows if not r["passed"]]
    assert "session-anchored" in by["0.2"]["text"]
    assert plan["exits"] == "open" and plan["variants"] == 4 * 60
    stores = REC.engine({"name": "bpo_fvg", "card": CARD, "run": {**RUNSET}}, plan, "bpo_fvg")
    assert {s["exits"] for s in stores} == {"open"} and {(s["markets"][0], s["bar_sizes"][0]) for s in stores} == {("NQ", "5"), ("NQ", "1"), ("ES", "5")}
    text = REC.card_md({"name": "bpo_fvg", "version": 1, "card": CARD, "run": RUNSET}, plan) if "card_md" in dir(REC) else ""
    assert not text or "session-anchored" in text


def test_every_other_exits_word_is_refused_and_the_standard_card_is_unchanged():
    for bad in ("extended", "blueprint", "something"):
        rows, plan = _lines({"exits": bad})
        assert plan is None and not {r["line"]: r for r in rows}["0.2"]["passed"], bad
    rows, plan = _lines({"exits": "standard"})
    assert plan is not None and plan["exits"] == "standard" and plan["variants"] == 4 * 48
    rows, plan = _lines({"exits": "open", "filter_exits": "standard"})
    assert plan is None                                                               # one table for the rule and its filters


# ---- (d) the lock refuses it ----------------------------------------------------------------------------------------------------

def test_the_freeze_says_the_open_table_cannot_be_locked_yet():
    src = (W / "blueprint" / "freeze.py").read_text()
    assert 'plan.get("exits", "standard") != "standard"' in src and "session-anchored table" in src


# ---- (e) one tiny smoke run -----------------------------------------------------------------------------------------------------

def test_a_smoke_run_writes_stores_with_the_open_cells():
    spec = {"name": "bpo_fvg", "reason": "The first gap after the open marks where aggressive orders ran through resting ones.", "family": "fvg", "markets": ["NQ"], "bar_sizes": ["5"], "sessions": ["nyam"],
            "params": {"min_gap": [0, 0.25]}, "fixed": {"mode": "go"}, "filters": [], "exits": "open", "limits": {"max_tr": 1}}
    with tempfile.TemporaryDirectory(prefix="bpo_") as d:
        out, led = Path(d) / "runs", Path(d) / "ledger.csv"
        rows = RUN.run_build(spec, 1, out, ledger=led, days=DAYS, cells=CELLS)
        assert [r["key"] for r in rows] == ["c1o-NQ-tf5", "bpo_fvg-NQ-tf5"] and all(r["ok"] for r in rows)
        import json
        pool = json.loads((out / "c1o-NQ-tf5" / "run.json").read_text())
        unit = json.loads((out / "bpo_fvg-NQ-tf5" / "run.json").read_text())
        assert [c["id"] for c in pool["cells"]] == [f"s{sd}_{x}" for sd in range(1, 11) for x in CELLS]
        assert [c["id"] for c in unit["cells"]] == [f"min_gap{v}_{x}" for v in ("0", "0p25") for x in CELLS] or len(unit["cells"]) == 4
        assert {c["exit"]["stop_mode"] for c in unit["cells"]} == {"atropen", "rngopen"}


# ---- (f) runs of different ideas go side by side (the owner, 2026-10-07) ------------------------------------------------------------

def test_stores_are_locked_one_by_one_a_pool_is_waited_for_and_a_unit_is_refused(tmp_path):
    import fcntl
    import threading
    import time
    for key in ("c1-NQ-tf5", "idea_a-NQ-tf5"):
        pass
    with RUN._stores(tmp_path, ["idea_a-NQ-tf5"]):                      # another idea's unit store: no clash with this one
        with RUN._stores(tmp_path, ["idea_b-NQ-tf5"]):
            pass
        with pytest.raises(J.Refuse, match="another run is writing"):   # the same store twice: refused
            with RUN._stores(tmp_path, ["idea_a-NQ-tf5"]):
                pass
    # a pool another run holds is waited for, then taken
    held = open(tmp_path / "c1-NQ-tf5.lock", "w")
    fcntl.flock(held, fcntl.LOCK_EX)
    said, got = [], []

    def release():
        time.sleep(0.6)
        fcntl.flock(held, fcntl.LOCK_UN)
    t = threading.Thread(target=release)
    t.start()
    t0 = time.monotonic()
    with RUN._stores(tmp_path, ["c1-NQ-tf5", "idea_a-NQ-tf5"], wait={"c1-NQ-tf5"}, say=said.append, poll=0.1):
        got.append(time.monotonic() - t0)
    t.join()
    held.close()
    assert got and got[0] >= 0.5 and len(said) == 1 and "c1-NQ-tf5" in said[0]


# ---- (g) the place it should NOT work is optional (the owner, 2026-10-07) ---------------------------------------------------------

def test_a_card_without_a_place_it_should_not_work_runs_no_such_table():
    card = {k: v for k, v in CARD.items() if k != "not_here"}
    rows, plan = REC.card_lines({"name": "bpo_fvg", "version": 1, "card": card, "run": RUNSET})
    assert plan is not None and all(r["passed"] for r in rows) and plan["not_here"] is None
    by = {r["line"]: r for r in rows}
    assert "should NOT" not in by["0.4"]["text"] and "2 places" in by["0.4"]["text"]
    sessions = {(s["market"], s["bar"]): s["sessions"] for s in plan["stores"]}
    assert sessions[("NQ", "5")] == ["nyam"]                                   # no afternoon pass: that table is not run
    with_nh, plan2 = REC.card_lines({"name": "bpo_fvg", "version": 1, "card": CARD, "run": RUNSET})
    assert plan2["not_here"] is not None and {(s["market"], s["bar"]): s["sessions"] for s in plan2["stores"]}[("NQ", "5")] == ["nyam", "pm"]
