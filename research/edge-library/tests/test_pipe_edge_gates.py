"""LOCK of THE EDGE GATES (pipeline.json gates.mode "edge"; the owner, 2026-10-18: one pipeline, judged by the strategy's own numbers at one
contract, no prop simulator; docs/superpowers/specs/2026-10-18-one-pipeline-two-tags-design.md).

The stops: the picked box makes money on the build days (average trade above $0, enough trades), its win rate is at or above the breakeven of its
REALIZED reward-to-risk plus edge.wr_cushion (row P3.15, again on the unseen days as P6.3), it still makes money on the unseen days and the map beats
95 % of the random tables there. Every other line is read, kept and printed as a LABEL (passed None). What is locked here:

1. the rules file: mode "edge" is the shipped default, its numbers lie over `variant`, a file without `gates` (or with "law") reads as it was,
   another word ("prop" among them, retired) is refused, the edge block is checked
2. the gates: a floor of $0 is read STRICTLY; P3.2, P3.3 and P3.15 ask, every other row of a box is a label; mode "law" is unchanged
3. P3.15: breakeven = 1 / (1 + realized R:R); +3 points; no losing trade passes, no winning trade fails
4. the pick: _holding keeps the boxes that hold the rows that ask, and reads no prop odds
5. the lock and the read of the unseen days (as before)
6. the book card: the shown numbers, the tag (live / live+prop), where the box stands

  pytest tests/test_pipe_edge_gates.py -q
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
    f = Path(tempfile.mkdtemp(prefix="edge_gates_")) / "pipeline.json"
    f.write_text(json.dumps(p), encoding="utf-8")
    P.FILE = f
    P._all.cache_clear()


# ================================================================ 1. the rules file

def test_the_shipped_file_asks_the_edge_gates_and_its_numbers_lie_over_the_variant_block():
    assert P.gates() == "edge" and P.edge_gates() is True and P.need("gates", "mode") == "edge"
    v = P.need("variant")
    assert (v["region_boxes"], v["pick_boxes"], v["floor_part"]) == (1, 1, 0.0)                              # the gates' numbers ...
    assert (v["map_share"], v["region_trades"], v["box_tries"], v["without_best_trades"], v["months_won"]) == (0.5, 200, 5, 0.05, 0.7)      # ... and the file's own, unchanged
    assert P.need("edge", "wr_cushion") == 0.03 and P.need("edge", "prop") == {"sharpe": 1.0, "months_positive": 0.6}   # the owner's +3 points; the Live + Prop bars
    assert P.floor("NQ", v["floor_part"]) == 0.0                                                            # a floor of nothing: "above $0" is read by the gates
    assert P.winlane("nq_ib_break_nyam_wl_a5-NQ-tf5") == "off"                                              # no win-rate lane rows in edge mode
    for k in ("portfolio", "mix", "funded"):
        refused = False
        try:
            P.need(k)
        except R.RuleError:
            refused = True
        assert refused, k


def test_the_edge_block_is_checked_when_the_file_loads():
    with_file(lambda p: p["edge"].pop("wr_cushion"))
    with pytest.raises(R.RuleError, match="wr_cushion"):
        P.gates()
    with_file(lambda p: p["edge"]["prop"].update(months_positive=1.5))
    with pytest.raises(R.RuleError, match="months_positive"):
        P.gates()


def test_a_file_without_gates_or_in_mode_law_reads_as_it_was_and_another_word_is_refused():
    with_file(lambda p: p.pop("gates"))
    assert P.gates() == "law" and P.need("variant")["floor_part"] == 1.0 and P.need("variant")["region_boxes"] == 25
    with_file(lambda p: p["gates"].update(mode="law"))
    assert P.gates() == "law" and P.need("variant")["region_boxes"] == 25        # (the block is in the file, and does not apply)
    for word in ("both", "prop"):                                               # (mode "prop", the 40 % eval odds of 2026-10-10, is retired)
        with_file(lambda p: p["gates"].update(mode=word))
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
    r = rows({**box(5.0, short_loses=True), "ids": ["x_pct0p2-r0p5"]})                  # the short side loses: line 2.6's reading says no
    for line in ("P3.4", "P3.6", "P3.7", "P3.8", "P3.9", "P3.10"):
        x = r[line]
        assert x["passed"] is None and "held" in x and x["label"] in ("HELD", "MISSED", "n/a"), line
    assert r["P3.4"]["held"] is False and r["P3.4"]["label"] == "MISSED" and "(a label, asks nothing)" in r["P3.4"]["text"]
    assert not [x for x in r.values() if x["passed"] is False]                # nothing that asks is missed: the box goes on
    assert r["P3.15"]["passed"] is True                                       # (every trade wins: no losing trade, the row passes)
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


def test_the_holding_row_says_what_a_box_has_to_have_in_edge_mode():
    row = G.holding(2, 5, {"P3.15": 3})
    assert row["passed"] is True and "make" in row["text"] and "breakeven of their reward-to-risk" in row["text"] and "P3.15 by 3" in row["text"]
    assert "eval odds" not in row["text"] and G.holding(0, 5, {})["passed"] is False


# ================================================================ 3. row P3.15: the win rate against its realized reward-to-risk

def test_p315_asks_three_points_over_the_breakeven_of_the_realized_reward_to_risk():
    t = [200.0] * 53 + [-100.0] * 47                                          # R:R 2.0 -> breakeven 33.3 %, need 36.3 %; 53 % wins
    r = G.wr_rr(np.array(t))
    assert r["line"] == "P3.15" and r["passed"] is True and r["rr"] == 2.0 and abs(r["breakeven"] - 1 / 3) < 1e-9 and abs(r["need"] - (1 / 3 + 0.03)) < 1e-9
    assert "realized reward-to-risk of 2.00" in r["text"] and "breakeven 33.33 %" in r["text"] and "+3 points" in r["text"]
    at = [100.0] * 53 + [-100.0] * 47                                         # R:R 1.0 -> need 53 %: 53 wins of 100 is exactly at the bar
    assert G.wr_rr(np.array(at))["passed"] is True
    under = [100.0] * 52 + [-100.0] * 48                                      # 52 %: profitable, but one point under the cushion
    assert G.wr_rr(np.array(under))["passed"] is False and sum(under) > 0


def test_p315_reads_the_realized_reward_to_risk_not_the_title():
    t = [50.0] * 60 + [-100.0] * 40                                           # a 1R title with wins cut to half: R:R 0.5, breakeven 66.7 %
    r = G.wr_rr(np.array(t))
    assert r["passed"] is False and r["rr"] == 0.5 and abs(r["breakeven"] - 2 / 3) < 1e-9


def test_p315_with_no_losing_trade_passes_and_with_no_winning_trade_fails():
    assert G.wr_rr(np.array([10.0, 20.0]))["passed"] is True and "no losing trade" in G.wr_rr(np.array([10.0, 20.0]))["text"]
    assert G.wr_rr(np.array([-10.0, 0.0]))["passed"] is False and "no winning trade" in G.wr_rr(np.array([-10.0, 0.0]))["text"]
    assert G.wr_rr(np.array([]))["passed"] is False and G.wr_rr(None)["passed"] is False
    assert G.wr_rr(np.array([10.0, 0.0]))["number"] == 0.5                    # a trade that nets nothing is not a win (as P3.11)


def test_p315_asks_in_edge_mode_only():
    b = box(5.0)
    b["trade_net"] = np.array([5.0] * 100 + [-10.0] * 150)                    # wins 40 % at R:R 0.5: far under its breakeven
    assert rows(b)["P3.15"]["passed"] is False
    with_file(lambda p: p["gates"].update(mode="law"))
    assert "P3.15" not in rows(b)


def test_the_reshuffled_runs_of_a_box_read_a_floor_of_nothing_strictly():
    b = {"root": "NQ", "net": np.array([[100.0, -100.0]]), "n": np.array([[10.0, 10.0]])}
    r = G.reshuffle_box(b)
    assert r["line"] == "P4.1" and "above $0" in r["text"] and 0.0 <= r["number"] <= 1.0


# ================================================================ 4. the pick

def test_the_pick_keeps_the_boxes_that_hold_and_reads_no_prop_odds(monkeypatch):
    monkeypatch.setattr(ST, "_box_rows", lambda t, c, days=None: [] if c != "c4" else [{"line": "P3.15", "passed": False}])
    good, missed = ST._holding({}, ["c0", "c1", "c2", "c3", "c4"])
    assert good == ["c0", "c1", "c2", "c3"] and missed == {"P3.15": 1} and not hasattr(ST, "_odds")
    rows_ = [{"id": "a", "net": 300.0, "trades": 10}, {"id": "b", "net": 100.0, "trades": 10}, {"id": "c", "net": 0.0, "trades": 0}]
    assert ST._avg(rows_, ["a", "b", "c"]) == {"a": (30.0,), "b": (10.0,), "c": (float("-inf"),)}


# ================================================================ 5. the lock

def test_a_pick_that_is_no_survivor_of_the_worse_fills_is_the_default_when_worse_fills_are_a_label(monkeypatch):
    monkeypatch.setattr(REC, "middle", lambda rows, ids, worse=None: ("c1", ["c1", "c2"]))
    with pytest.raises(J.Refuse, match="not a variant that makes money on build AND on build with worse fills"):
        FRZ._choose([], ["c1", "c2", "c3"], {}, "c3", "NQ ...")
    default, surv, rule = FRZ._choose([], ["c1", "c2", "c3"], {}, "c3", "NQ ...", labels=("3.3", "worse"))
    assert default == "c3" and surv == ["c1", "c2"] and "does NOT make money with worse fills" in rule and "asks nothing" in rule
    with pytest.raises(J.Refuse, match="no judged variant"):                   # (a box the table does not hold is still refused)
        FRZ._choose([], ["c1", "c2"], {}, "zz", "NQ ...", labels=("worse",))


# ================================================================ 6. the unseen days

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


# ================================================================ 7. the book card

def test_where_the_box_stands_is_a_new_high_or_a_drawdown_from_its_best():
    days = [739000 + i for i in range(5)]
    up = ST._equity(days, np.array([100.0, -50.0, 80.0, 0.0, 40.0]))           # 100, 50, 130, 130, 170: the last day is the best so far
    assert up["state"] == "at a new high" and up["below_high"] == 0.0 and up["sessions_since_high"] == 0 and up["sessions"] == 5
    down = ST._equity(days, np.array([100.0, 50.0, -80.0, 0.0, -40.0]))        # 100, 150, 70, 70, 30: $120 under its high of 150, two days after... three
    assert down["state"] == "in drawdown" and down["below_high"] == 120.0 and down["sessions_since_high"] == 3
    flat = ST._equity(days, np.array([-10.0, 0.0, 0.0, 0.0, 0.0]))             # never above its start: in drawdown from the $0 it began with
    assert flat["state"] == "in drawdown" and flat["below_high"] == 10.0
    assert ST._equity([], np.array([])) is None


def _x(net, days):
    """One box's trades as judge.cellx hands them over: one trade a day on `days` (ordinals), held 60 s, no open loss."""
    n = len(net)
    return {"net": np.asarray(net, np.float64), "date": np.asarray(days[:n], np.int64), "entry_ms": np.full(n, 1_700_000_000_000), "dur_s": np.full(n, 60),
            "mae": np.zeros(n), "side": np.ones(n), "sess": np.zeros(n), "reason": np.zeros(n), "risk": np.full(n, 100.0)}


def test_the_shown_numbers_are_size_free_and_read_off_the_box_trades():
    import datetime as dt
    days = [dt.date(2025, 7, 1).toordinal() + i for i in range(60)]
    net = ([200.0, -100.0] * 30)                                              # 50 % wins at R:R 2: +$3,000 over 60 days
    cal = [dt.date.fromordinal(d).isoformat() for d in days]
    n = ST._edge_numbers(_x(net, days), cal)
    assert (n["trades"], n["days"], n["win_rate"], n["realized_rr"], n["net"]) == (60, 60, 0.5, 2.0, 3000.0)
    assert abs(n["breakeven_wr"] - 1 / 3) < 1e-9 and n["avg_r"] == 0.5 and n["net_per_year"] == 3000.0 / 60 * 252
    assert n["sharpe"] > 0 and n["months_positive"] == 1.0 and 1.0 <= n["worst_drawdown_r"] < 1.1 and n["month_wr"]["months"] == 2      # (the open loss counts the round-trip cost)
    flat = ST._edge_numbers(_x([10.0] * 5, days), cal[:5])
    assert flat["sharpe"] is None and flat["realized_rr"] is None              # no spread, no losing trade: no number, no crash


def test_the_tag_is_live_plus_prop_only_when_sharpe_and_months_both_hold():
    assert ST._tag({"sharpe": 1.0, "months_positive": 0.6}) == "live+prop"     # both at the bar: "or more"
    assert ST._tag({"sharpe": 0.99, "months_positive": 0.9}) == "live"
    assert ST._tag({"sharpe": 2.0, "months_positive": 0.59}) == "live"
    assert ST._tag({"sharpe": None, "months_positive": 1.0}) == "live" and ST._tag({}) == "live"


# ================================================================ 8. stage 6 is the 3:1 walk-forward (2026-10-18)

def test_stage_6_decides_by_the_walk_forward_and_keeps_the_reads_lines_as_labels(monkeypatch):
    lock = "L1"
    read = {"lock": lock, "passed": False, "lines": [{"line": "4.4", "passed": False, "number": 0.5, "need": 0.95, "text": "4.4 FAIL beats 50 %"}],
            "range": {"start": "2025-07-01", "end": "2026-09-22"}, "relatives": [], "gates": {"only": ["box", "4.4"], "box": -10.0}}
    five = {"picked": {"sub": "s", "cell": "c1", "bar": "5"}, "tries": 1, "locked": {"default": "c1", "lock": lock}}
    monkeypatch.setattr(ST, "_before", lambda name, ctx, n: five)
    monkeypatch.setattr(ST, "_kw", lambda name, ctx: {"root": None, "out": None, "ledger": None, "days": None, "cells": None, "workers": None, "draws": None})
    monkeypatch.setattr(ST.REC, "_json", lambda p: read)
    monkeypatch.setattr(ST.REC, "_carded", lambda sub, root: Path("/nowhere"))

    def walk(rows_ok):
        out = [{"line": k, "passed": ok, "number": 1, "need": 0, "text": f"{k} {'PASS' if ok else 'FAIL'} x"} for k, ok in zip(("P6.1", "P6.2", "P6.3", "P6.4"), rows_ok)]
        return {"rows": out, "passed": all(rows_ok), "months": ["2022-01", "2026-09"], "stood_aside": [], "picks": [{"month": "2022-01", "cell": "c1"}],
                "next": {"month": "2026-10", "window": [], "cell": "c2"}, "random": {"p_beat": 0.97}, "split": {}}
    monkeypatch.setattr(ST, "_walk", lambda sub, kw, ctx: walk((True, True, True, True)))
    c = ST.stage6("wf_idea", {})
    assert (c["passed"], c["result"]) == (True, "proven on history") and c["walkforward"]["next"]["cell"] == "c2"
    assert [r["line"] for r in c["lines"][:4]] == ["P6.1", "P6.2", "P6.3", "P6.4"] and c["lines"][4]["passed"] is None      # the read's 4.4: a label
    assert "the pick for 2026-10: c2" in c["text"]
    monkeypatch.setattr(ST, "_walk", lambda sub, kw, ctx: walk((True, False, True, True)))
    c = ST.stage6("wf_idea", {})
    assert (c["passed"], c["result"]) == (False, "not proven") and "fails P6.2" in c["text"]
