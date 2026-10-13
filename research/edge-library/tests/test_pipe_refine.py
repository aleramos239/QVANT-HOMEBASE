"""test_pipe_refine.py -- the refiner (pipe_refine.py): one move a round, a reason, a counted line, build days only."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
import judge as J  # noqa: E402
from blueprint import pipe_refine as RF  # noqa: E402


def test_one_move_a_round():
    with pytest.raises(J.Refuse):
        RF._parse([], [], "both")
    with pytest.raises(J.Refuse):
        RF._parse(["regime=er", "days=nonews"], [], "both")


def test_a_regime_is_a_gate_with_textbook_numbers_and_can_be_tuned():
    kind, fixed, words = RF._parse(["regime=er"], ["g_lvl=0.4"], "both")
    assert kind == "regime" and fixed["gate"] == "er" and fixed["g_n"] == 10 and fixed["g_lvl"] == 0.4 and fixed["g_side"] == "with"
    kind, fixed, _ = RF._parse(["indicator=rsi"], [], "both")
    assert fixed["gate"] == "rsi" and fixed["g_lvl"] == 10.0


def test_what_a_move_may_not_be():
    for bad in (["regime=rsi"], ["indicator=er"], ["days=all"], ["days=blue"], ["window=9-11"], ["sides=both"], ["sides=long"]):
        with pytest.raises(J.Refuse):
            RF._parse(bad, [], "long")
    with pytest.raises(J.Refuse):
        RF._parse(["days=nonews"], ["g_n=5"], "both")        # --set fine-tunes a gate only


def test_window_and_days_and_sides():
    assert RF._parse(["window=09:30-11:30"], [], "both")[1] == {"w_start": "09:30", "w_end": "11:30"}
    assert RF._parse(["days=nonews"], [], "both")[1] == {"days": "nonews"}
    assert RF._parse(["sides=short"], [], "both")[1] == {"sides": "short"}


def test_child_names_keep_the_cards_limit():
    n = RF.child_name("x" * 34, 3)
    assert n.endswith("_r3") and len(n) == 34 and RF.child_name("nq_a", 2) == "nq_a_r2"


def test_a_missed_row_points_at_the_moves_worth_a_look():
    assert RF._hints(["P3.12"])[0] == "days" and RF._hints(["P1.3"])[0] == "regime"
    assert RF._hints(["Z9.9"]) == list(RF.KINDS)
