"""LOCK of the mix on the build days (blueprint/pipe_mix.py; `bp.py pipe mix`) -- the owner, 2026-10-10.
HAND-MADE TRADES ONLY (tests/blueprint_synth.py): no tape is read, no engine run is made, nothing is written.

1. The members are decided by a rule, deterministically: an idea with a picked box that has not read the unseen days; no row of its picked
   box's stage cards outside `mix.member_may_fail` failed; its own box holds the edge rows P3.2 P3.3 P3.4 P3.7 RECOMPUTED from its trades
   (an old card may predate a row). Stage 1's rows (the other bar's map) are no row of the box.
2. A long-only idea is read with its card's side (P3.4 "by its card"), not as a two-sided box.
3. The mix is read by the pipeline's own row functions (the same numbers as one box of the same trades); steadiness comes from the days
   together: two boxes that make money on different days have fewer losing months than either.
4. The tail table: what is left without the best 1 / 2 / 5 % of trades; the 5 % is row P3.7's number.
5. It reads the build days only: a store that is not the build days' is refused; the command runs nothing and writes nothing.

  pytest tests/test_pipe_mix.py -q
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pytest

W = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(W), str(Path(__file__).resolve().parent)]
import judge as J  # noqa: E402
from blueprint import pipe_gates as G  # noqa: E402
from blueprint import pipe_mix as M  # noqa: E402
from blueprint import pipe_rules as PR  # noqa: E402

import blueprint_synth as SY  # noqa: E402
import library as LB  # noqa: E402

CAL = SY.weekdays("2024-01-01", "2024-12-31")             # 262 hand-made session days
DAYS = np.array([dt.date.fromisoformat(d).toordinal() for d in CAL])


def packed(rows: list) -> dict:
    return LB.pack(sorted(rows, key=lambda t: (t["exit_ms"], t["entry_ms"])))


def trades(on: list, win: float = 300.0, loss: float = -100.0, every: int = 3, at: str = "09:45") -> dict:
    """One trade on each listed day (indexes of CAL): a win, and every `every`-th a loss."""
    return packed([SY.trade(CAL[i], loss if k % every == every - 1 else win, 2.0, at=at, side="long") for k, i in enumerate(on)])


def idea(name: str, x: dict, failed=(), stopped: int = 4, sides: str = "both", unseen: bool = False) -> dict:
    cards = {1: {"lines": [{"line": "P1.1", "passed": False}]}, 3: {"lines": [{"line": "P3.2", "passed": True}]}}      # stage 1's map row fails: it is not the box's
    if failed:
        cards[stopped] = {"lines": [{"line": k, "passed": False} for k in failed]}
    if unseen:
        cards[6] = {"lines": []}
    return {"name": name, "x": x, "cards": cards, "sides": sides,
            "state": {"name": name, "status": "stopped", "stopped_at": stopped, "picked": {"sub": f"{name}_a5", "bar": "5", "cell": "c", "way": 0}}}


@pytest.fixture
def world(monkeypatch):
    book = {}

    def put(*ideas):
        book.clear()
        book.update({i["name"]: i for i in ideas})
    monkeypatch.setattr(M.PS, "ideas", lambda root=None: [{"name": n} for n in book])
    monkeypatch.setattr(M.PS, "state", lambda n, root=None: book[n]["state"])
    monkeypatch.setattr(M.PS, "stages", lambda n, root=None: book[n]["cards"])
    monkeypatch.setattr(M.PS, "card", lambda n, root=None: {"name": n, "market": "NQ", "session": "nyam", "sides": book[n]["sides"]})
    monkeypatch.setattr(M, "_trades", lambda m, root=None: book[m["name"]]["x"])
    monkeypatch.setattr(M, "_calendar", lambda market: CAL)
    monkeypatch.setitem(M._DAYS, "NQ", DAYS)
    monkeypatch.setattr(M.PP, "odds", lambda x, cal, *a, **k: {"account": {"id": "a", "name": "the account"}, "days": 30, "eval": 0.3, "payout": 0.2, "size": 1,
                                                                 "stress": {"eval": 0.1, "payout": 0.05}})
    return put


# ================================================================ 1. the members

def test_the_rule_admits_an_idea_that_fails_only_steadiness_rows_and_leaves_the_rest_out(world):
    ev, od = list(range(0, 260, 1)), list(range(0, 260, 1))                # 260 trades each: the 200-trade row holds
    world(idea("steady_a", trades(ev), ["P3.8", "P4.1"], sides="long"),
          idea("steady_b", trades(od), ["P3.10"], stopped=3, sides="long"),
          idea("weak_edge", trades(ev), ["P3.7"], stopped=3, sides="long"),          # a failed EDGE row of its card: out
          idea("read_unseen", trades(ev), unseen=True, stopped=6, sides="long"),
          idea("loses_money", packed([SY.trade(CAL[i], -50.0, 2.0, side="long") for i in range(0, 260)]), sides="long"))      # no failed row on a card, but its own trades lose
    by, left = M.members()
    assert [m["name"] for m in by["NQ"]] == ["steady_a", "steady_b"]
    why = {x["name"]: x["why"] for x in left}
    assert set(why) == {"weak_edge", "read_unseen", "loses_money"}
    assert "edge row" in why["weak_edge"] and "P3.7" in why["weak_edge"] and "unseen days" in why["read_unseen"] and "P3.2" in why["loses_money"]
    assert by["NQ"][0]["failed"] == ["P3.8", "P4.1"] and by["NQ"][0]["edge"]["P3.2"] is True, "stage 1's map row is not a row of the picked box"
    assert M.members()[0] == by, "the same members the second time"


def test_an_idea_with_no_picked_box_is_left_out_and_named(world):
    nobox = idea("nobox", trades([0, 1, 2]))
    nobox["state"]["picked"] = {}
    world(nobox)
    by, left = M.members()
    assert by == {} and left == [{"name": "nobox", "why": "no picked box (it stopped before stage 1 chose one)"}]


def test_the_old_cards_are_not_trusted_for_an_edge_row_the_rows_are_read_today(world):
    # a box whose money is in a few big trades: its card (made before P3.7 existed) has no P3.7 row, today's row fails it
    day = list(range(0, 240))
    fat = packed([SY.trade(CAL[i], 3000.0 if i % 40 == 0 else -30.0, 2.0, side="long") for i in day])
    world(idea("fat_tail", fat, stopped=4))
    by, left = M.members()
    assert by == {} and "P3.7" in left[0]["why"] and "today" in left[0]["why"]
    kept, _ = M.members(strict=False)                                      # a person's what-if keeps it, marked
    assert kept["NQ"][0]["admitted"] is False and kept["NQ"][0]["edge"]["P3.7"] is False


# ================================================================ 2. the side of the card

def test_a_long_only_idea_is_read_as_long_only_not_as_a_box_that_has_no_short_side(world):
    x = trades(list(range(0, 260)))
    world(idea("longs", x, sides="long"), idea("both", x, sides="both"))
    by, _ = M.members(strict=False)
    got = {m["name"]: m["edge"]["P3.4"] for m in by["NQ"]}
    assert got == {"both": False, "longs": True}


# ================================================================ 3. the mix is read by the pipeline's own functions

def test_the_mix_of_two_boxes_on_different_days_is_steadier_than_either(world):
    # a: wins in the first half of the year, loses in the second; b: the other way round -- each alone loses half its months
    a = packed([SY.trade(CAL[i], 200.0 if i < 130 else -200.0, 2.0, side="long") for i in range(0, 260, 2)])
    b = packed([SY.trade(CAL[i], -200.0 if i < 130 else 200.0, 2.0, side="long") for i in range(1, 261, 2)])
    world(idea("a", a, sides="long"), idea("b", b, sides="long"))
    r = M.read("NQ", names=["a", "b"])
    sa, sb = r["single"]["a"], r["single"]["b"]
    assert r["mix"]["months_won"] > max(sa["months_won"], sb["months_won"]), (r["mix"], sa, sb)
    assert r["mix"]["trades"] == len(a["net"]) + len(b["net"]) and r["what_if"] is True
    assert r["correlation"]["names"] == ["a", "b"] and len(r["correlation"]["matrix"]) == 2
    got = {x["line"]: x for x in r["rows"]}
    assert {"P3.2", "P3.3", "P3.7", "P3.8", "P3.9", "P3.10", "3.3", "3.8", "P4.1"} <= set(got)
    box = M._box(M._pack([a, b]), DAYS, "NQ", "m", "long")
    assert [x["line"] for x in G.variant_rows(box, [])] == [x["line"] for x in r["rows"][:len(G.variant_rows(box, []))]], "the pipeline's own rows, in its order"
    assert r["note"].startswith("build days only") and "unseen days are not read" in r["note"]


def test_what_is_left_without_the_best_trades_is_the_p3_7_number(world):
    x = packed([SY.trade(CAL[i], 2000.0 if i < 5 else 10.0, 2.0, side="long") for i in range(0, 200)])
    t = M._tail(x)
    k5 = int(round(0.05 * 200))
    assert t["all"] == pytest.approx(float(x["net"].sum()))
    assert t["5 %"] == pytest.approx(float(np.sort(x["net"])[:-k5].sum())) and t["1 %"] > t["2 %"] > t["5 %"]
    row = next(r for r in G.variant_rows(M._box(x, DAYS, "NQ", "t", "long"), []) if r["line"] == "P3.7")
    assert row["number"] == pytest.approx(t["5 %"]), "the table's 5 % is the row's own number"


# ================================================================ 5. the build days only

def test_a_store_that_is_not_the_build_days_is_refused_and_nothing_here_names_the_unseen_days(monkeypatch):
    class Unit(dict):
        pass
    monkeypatch.setattr(M.LB, "load_unit", lambda key, root: {"meta": {"period": "bp_test", "cells": []}})
    monkeypatch.setattr(M.PS, "runs", lambda root=None: Path("."))
    with pytest.raises(J.Refuse) as e:
        M._trades({"name": "x", "sub": "s", "market": "NQ", "bar": "5", "cell": "c"})
    assert "build days" in str(e.value)
    src = Path(M.__file__).read_text()
    assert "run_test" not in src and "runs_test" not in src and "2025-07-01" not in src.replace("2025-07-01 on", "")


def test_the_admission_list_is_pipeline_jsons_and_holds_only_rows_the_mix_takes_over():
    may = PR.need("mix", "member_may_fail")
    assert set(may) == {"P3.8", "P3.9", "P3.10", "P4.1", "3.4", "3.5", "3.6"}
    assert not set(may) & set(M.NEEDS), "no edge row may be handed to the mix"
