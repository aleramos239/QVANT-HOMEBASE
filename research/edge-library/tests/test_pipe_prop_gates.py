"""LOCK of THE PROP GATES (pipeline.json gates.mode "prop"; the owner, 2026-10-10, after the Matteo Conti interview: "go off what he says").

Only three things ask: the picked box makes money on the build days (average trade above $0, enough trades), its eval odds are prop.eval (40 %) or
more, and it still makes money on the unseen days. Every other line is read, kept and printed as a LABEL (passed None). What is locked here:

1. the rules file: mode "prop" is the shipped default, its numbers lie over `variant`, a file without `gates` (or with "law") reads as it was,
   another word is refused, the eval bar is 40 %, the fees are on file
2. the gates: a floor of $0 is read STRICTLY (a box that nets nothing does not make money); P3.2 and P3.3 ask, every other row of a box is a label that
   keeps what it would have said (`held`); mode "law" is unchanged
3. the pick: _holding keeps the boxes that hold P3.2 / P3.3 and have the eval odds -- the plain row, `>=` the bar -- and counts the rest
4. the lock: labels = the lines read and kept that refuse nothing; a pick that is no survivor of the worse fills is the default all the same
5. the read of the unseen days: oos.test(only=("box",)): the box's own net decides; 4.1-4.9 are kept and labelled; a box that loses is NOT PROVEN
6. the book card: where the box stands (at a new high / in drawdown) and the fee line

  pytest tests/test_pipe_prop_gates.py -q
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blueprint_frozen as F  # noqa: E402

import judge as J  # noqa: E402
import pipe_law  # noqa: E402
from blueprint import freeze as FRZ  # noqa: E402
from blueprint import oos as OOS  # noqa: E402
from blueprint import pipe_gates as G  # noqa: E402
from blueprint import pipe_rules as P  # noqa: E402
from blueprint import pipe_stages as ST  # noqa: E402
from blueprint import records as REC  # noqa: E402
from blueprint import rules as R  # noqa: E402

NAME = "bpl_orb"
REAL = R.T / "pipeline.json"


def setup_function(_=None):
    F.env_on()
    P._all.cache_clear()


def teardown_function(_=None):
    F.env_off()
    P.FILE = REAL
    P._all.cache_clear()


def with_file(edit) -> None:
    """pipeline.json as `edit(copy of the real file)` says, in a temp folder, until teardown_function."""
    p = copy.deepcopy(json.loads(REAL.read_text(encoding="utf-8")))
    edit(p)
    f = Path(tempfile.mkdtemp(prefix="prop_gates_")) / "pipeline.json"
    f.write_text(json.dumps(p), encoding="utf-8")
    P.FILE = f
    P._all.cache_clear()


# ================================================================ 1. the rules file

def test_the_shipped_file_asks_the_prop_gates_and_its_numbers_lie_over_the_variant_block():
    assert P.gates() == "prop" and P.prop_gates() is True and P.need("gates", "mode") == "prop"
    v = P.need("variant")
    assert (v["region_boxes"], v["pick_boxes"], v["floor_part"]) == (1, 1, 0.0)                              # the gates' numbers ...
    assert (v["map_share"], v["region_trades"], v["box_tries"], v["without_best_trades"], v["months_won"]) == (0.5, 200, 5, 0.05, 0.7)      # ... and the file's own, unchanged
    assert P.need("prop", "eval") == 0.4 and P.need("prop", "payout") == 0.5                                # the owner's 40 % eval odds
    assert P.need("prop", "fees") == {"lucid-pro-50k-no-dll@2026-10-11": 140, "lucid-pro-50k@2026-10-11": 115}      # the owner, 2026-09-30
    assert P.floor("NQ", v["floor_part"]) == 0.0                                                            # a floor of nothing: "above $0" is read by the gates
    assert P.need("prop", "account") == "lucid-pro-50k-no-dll@2026-10-11"                                   # LucidPro 50K, no daily limit: open losses count; since 2026-10-11 its OWN payout rule


def test_a_file_without_gates_or_in_mode_law_reads_as_it_was_and_another_word_is_refused():
    with_file(lambda p: p.pop("gates"))
    assert P.gates() == "law" and P.need("variant")["floor_part"] == 1.0 and P.need("variant")["region_boxes"] == 25
    with_file(lambda p: p["gates"].update(mode="law"))
    assert P.gates() == "law" and P.need("variant")["region_boxes"] == 25        # (the block is in the file, and does not apply)
    with_file(lambda p: p["gates"].update(mode="both"))
    with pytest.raises(R.RuleError, match="gates.mode"):
        P.gates()
    law = json.loads(pipe_law.file().read_text(encoding="utf-8"))               # the test fixture of the old file says the same
    assert "gates" not in law and law["prop"]["eval"] == 0.5


# ================================================================ 2. the gates

def box(avg: float, trades: int = 250, root: str = "NQ", sides=("long", "short"), **more) -> dict:
    """One box on ONE day: `trades` trades at an average of `avg` after costs; half of them on each side (the short side loses when `short_loses`)."""
    net = np.array([[avg * trades]])
    return {"root": root, "net": net, "n": np.array([[float(trades)]]), "ids": ["c0"], "unit": "u", "days": None, "sides": "both",
            "long": avg * trades if "short_loses" not in more else avg * trades + 500.0, "short": 0.0 if "short_loses" not in more else -500.0,
            "n_long": trades // 2, "n_short": trades - trades // 2, "trade_net": np.full(trades, avg), "trade_date": np.arange(trades) + 739000}


def rows(b: dict) -> dict:
    return {x["line"]: x for x in G.variant_rows(b, [])}


def test_a_box_makes_money_when_its_average_trade_is_above_nothing_and_has_enough_trades():
    r = rows(box(5.0))
    assert (r["P3.2"]["passed"], r["P3.3"]["passed"]) == (True, True) and "above $0" in r["P3.2"]["text"]
    assert rows(box(0.0))["P3.2"]["passed"] is False                          # a box that nets nothing does not make money: strict
    assert rows(box(-1.0))["P3.2"]["passed"] is False
    assert rows(box(5.0, trades=199))["P3.3"]["passed"] is False and rows(box(5.0, trades=200))["P3.3"]["passed"] is True      # the sample a mean needs


def test_every_other_row_of_a_box_is_a_label_that_keeps_what_it_would_have_said():
    r = rows(box(5.0, short_loses=True))                                      # the short side loses: line 2.6's reading says no
    for line in ("P3.4", "P3.6", "P3.7", "P3.8", "P3.9", "P3.10"):
        x = r[line]
        assert x["passed"] is None and "held" in x and x["label"] in ("HELD", "MISSED", "n/a"), line
    assert r["P3.4"]["held"] is False and r["P3.4"]["label"] == "MISSED" and "(a label, asks nothing)" in r["P3.4"]["text"]
    assert not [x for x in r.values() if x["passed"] is False]                # nothing that asks is missed: the box goes on
    label = G.label({"line": "P3.7", "passed": True, "number": 1, "need": 0, "text": "P3.7 PASS without its best 5 % the box makes $9"})
    assert label["text"] == "P3.7 held (a label, asks nothing) without its best 5 % the box makes $9" and label["held"] is True


def test_in_mode_law_every_row_asks_as_it_always_did():
    with_file(lambda p: p["gates"].update(mode="law"))
    r = rows(box(5.0, short_loses=True))                                      # (law: an average trade of $5 is under the $70 floor)
    assert r["P3.2"]["passed"] is False and r["P3.4"]["passed"] is False and "held" not in r["P3.4"]
    assert G.variant_map({"root": "NQ", "net": np.array([[500.0]]), "n": np.array([[250.0]]), "ids": ["c0"]})["result"] == "fail"


def test_the_map_check_needs_one_box_that_makes_money_and_the_share_of_boxes_is_a_label():
    t = {"root": "NQ", "net": np.array([[500.0], [-100.0], [-100.0], [-100.0]]), "n": np.full((4, 1), 250.0), "ids": ["a", "b", "c", "d"]}
    m = G.variant_map(t)
    assert (m["result"], m["qualifying"], m["cells"]) == ("pass", 1, ["a"])
    assert m["lines"][0]["line"] == "P1.1" and m["lines"][0]["passed"] is None and m["lines"][0]["held"] is False      # 25 % of boxes: a label
    assert m["lines"][1]["passed"] is True and "above $0" in m["lines"][1]["text"]
    nothing = {"root": "NQ", "net": np.array([[0.0], [-5.0]]), "n": np.full((2, 1), 250.0), "ids": ["a", "b"]}
    assert G.variant_map(nothing)["result"] == "fail"                         # no box makes money: the idea stops


def test_the_holding_row_says_what_a_box_has_to_have_in_prop_mode():
    row = G.holding(2, 5, {"eval odds": 3})
    assert row["passed"] is True and "make" in row["text"] and "40 % eval odds or more" in row["text"] and "eval odds by 3" in row["text"]
    assert G.holding(0, 5, {})["passed"] is False


def test_the_reshuffled_runs_of_a_box_read_a_floor_of_nothing_strictly():
    b = {"root": "NQ", "net": np.array([[100.0, -100.0]]), "n": np.array([[10.0, 10.0]])}
    r = G.reshuffle_box(b)
    assert r["line"] == "P4.1" and "above $0" in r["text"] and 0.0 <= r["number"] <= 1.0


# ================================================================ 3. the pick

def test_the_pick_keeps_the_boxes_with_the_eval_odds_and_counts_the_rest(monkeypatch):
    def eval_of(c):
        return {"c0": 0.55, "c1": 0.40, "c2": 0.39, "c3": 0.10}[c]
    monkeypatch.setattr(ST, "_box_rows", lambda t, c, days=None: [] if c != "c4" else [{"line": "P3.2", "passed": False}])
    monkeypatch.setattr(ST, "_odds", lambda t, cells, days=None: {c: {"eval": eval_of(c), "payout": 0.5} for c in cells})
    good, missed = ST._holding({}, ["c0", "c1", "c2", "c3", "c4"])
    assert good == ["c0", "c1"]                                               # 40 % is "40 % or more"; 39 % is not
    assert missed == {"P3.2": 1, "eval odds": 2}
    with_file(lambda p: p["gates"].update(mode="law"))
    good, missed = ST._holding({}, ["c0", "c1", "c2", "c3", "c4"])            # (law: the eval odds are a label of the pick, not a gate of the boxes)
    assert good == ["c0", "c1", "c2", "c3"] and missed == {"P3.2": 1}


# ================================================================ 4. the lock

def test_a_pick_that_is_no_survivor_of_the_worse_fills_is_the_default_when_worse_fills_are_a_label(monkeypatch):
    monkeypatch.setattr(REC, "middle", lambda rows, ids, worse=None: ("c1", ["c1", "c2"]))
    with pytest.raises(J.Refuse, match="not a variant that makes money on build AND on build with worse fills"):
        FRZ._choose([], ["c1", "c2", "c3"], {}, "c3", "NQ ...")
    default, surv, rule = FRZ._choose([], ["c1", "c2", "c3"], {}, "c3", "NQ ...", labels=("3.3", "worse"))
    assert default == "c3" and surv == ["c1", "c2"] and "does NOT make money with worse fills" in rule and "asks nothing" in rule
    with pytest.raises(J.Refuse, match="no judged variant"):                   # (a box the table does not hold is still refused)
        FRZ._choose([], ["c1", "c2"], {}, "zz", "NQ ...", labels=("worse",))


# ================================================================ 5. the unseen days

def test_the_box_alone_decides_the_read_and_the_law_lines_are_kept_as_they_said():
    root, lock = F.frozen(NAME, "gates_pass")
    with F.reading("gates_pass", worse=lambda cell, i, day: -10.0):            # the box makes $150 a day; with worse fills it loses: line 4.5 fails
        r = OOS.test(NAME, confirm=True, root=root, only=("box",))
    b = F.by(r)
    assert b["4.5"]["passed"] is False                                         # what the law would have said is kept ...
    assert (r["verdict"], r["passed"], r["failed"], r["status"]) == ("PROVEN ON HISTORY", True, [], "proven_on_history")      # ... and does not decide
    assert r["gates"]["only"] == ["box"] and r["gates"]["box"] == 1200.0 and "4.5" in r["gates"]["labels"]
    assert "the line asked (box) holds; the box made $1,200 on the test days; not asked, and missed:" in r["text"]
    assert "approved for a real eval" not in r["text"]                         # (that sentence is the law's: every line)
    saved = F.read(root / NAME / "test.json")
    assert saved["gates"] == r["gates"] and [x["line"] for x in saved["lines"]] == F.TEST_LINES


def test_a_box_that_loses_on_the_unseen_days_is_not_proven_and_the_fail_is_final():
    root, lock = F.frozen(NAME, "gates_fail")
    with F.reading("gates_fail", net=lambda cell, i, day: -20.0, worse=lambda cell, i, day: -30.0):
        r = OOS.test(NAME, confirm=True, root=root, only=("box",))
    assert (r["verdict"], r["passed"], r["failed"], r["status"]) == ("NOT PROVEN", False, ["box"], "shelved")
    assert r["gates"]["box"] == -160.0 and "fails box" in r["text"] and "A FAIL IS FINAL" in r["text"]
    with F.reading("gates_fail"), F.no_engine():
        F.refused(lambda: OOS.test(NAME, confirm=True, root=root, only=("box",)), "already on file")


def test_without_the_keyword_every_line_decides_as_the_law_has_it():
    root, lock = F.frozen(NAME, "gates_law")
    with F.reading("gates_law", worse=lambda cell, i, day: -10.0):
        r = OOS.test(NAME, confirm=True, root=root)
    assert r["passed"] is False and "4.5" in r["failed"] and "gates" not in r


# ================================================================ 6. the book card

def test_where_the_box_stands_is_a_new_high_or_a_drawdown_from_its_best():
    days = [739000 + i for i in range(5)]
    up = ST._equity(days, np.array([100.0, -50.0, 80.0, 0.0, 40.0]))           # 100, 50, 130, 130, 170: the last day is the best so far
    assert up["state"] == "at a new high" and up["below_high"] == 0.0 and up["sessions_since_high"] == 0 and up["sessions"] == 5
    down = ST._equity(days, np.array([100.0, 50.0, -80.0, 0.0, -40.0]))        # 100, 150, 70, 70, 30: $120 under its high of 150, two days after... three
    assert down["state"] == "in drawdown" and down["below_high"] == 120.0 and down["sessions_since_high"] == 3
    flat = ST._equity(days, np.array([-10.0, 0.0, 0.0, 0.0, 0.0]))             # never above its start: in drawdown from the $0 it began with
    assert flat["state"] == "in drawdown" and flat["below_high"] == 10.0
    assert ST._equity([], np.array([])) is None


def test_the_fee_line_sets_what_an_eval_costs_against_the_cheque_expected():
    own = "lucid-pro-50k-no-dll@2026-10-11"
    f = ST._fees({own: {"eval": 0.5, "payout": 0.4}, "lucid-flex-50k@2026-09-27": {"eval": 0.5, "payout": 0.4}})
    assert list(f) == [own]                                                    # (an account with no fee on file has no line)
    x = f[own]
    assert (x["fee"], x["evals_per_pass"], x["cost_per_pass"], x["first_cheque"], x["expected_first_cheque"], x["net_per_pass"]) == (140, 2.0, 280.0, 2000, 800.0, 520.0)
    assert "an eval costs $140" in x["text"] and "+$520 a passed account" in x["text"]
    assert ST._fees({own: {"eval": 0.0, "payout": 0.4}}) == {}                 # an account that never passes has no cost per pass to say
