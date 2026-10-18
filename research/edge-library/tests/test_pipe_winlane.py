"""test_pipe_winlane.py -- the win-rate lane (pipeline.json `winlane`, owner 2026-10-12): rows P3.11 (win rate) and P3.12 (months at a win-rate floor).
Off by default and then invisible; "label" prints the rows and asks nothing; "ask" makes a box that misses either one unpickable."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
import pytest  # noqa: E402

from blueprint import pipe_gates as G  # noqa: E402
from blueprint import pipe_rules as P  # noqa: E402
from blueprint import rules as R  # noqa: E402

day = lambda y, m, d: dt.date(y, m, d).toordinal()          # noqa: E731


@pytest.fixture
def lane(tmp_path):
    """lane("ask") points the rules file at a copy of the shipped pipeline.json with winlane.mode set; the file and the cache are put back."""
    keep = P.FILE
    d = json.loads((R.T / "pipeline.json").read_text(encoding="utf-8"))

    def use(mode, **numbers):
        d["winlane"] = {**d["winlane"], "mode": mode, "cards": [], "max_target_r": 1.0, **numbers}       # (no cards: the lane is on every unit; the retired WR file's target cap)
        f = tmp_path / "pipeline.json"
        f.write_text(json.dumps(d), encoding="utf-8")
        P.FILE = f
        P._all.cache_clear()
    yield use
    P.FILE = keep
    P._all.cache_clear()


def months(plan: dict, per: int = 20, year: int = 2024) -> dict:
    """A trade list: plan = {month: wins out of `per` trades}; one trade a day, the wins first."""
    d, t = [], []
    for m, wins in plan.items():
        for i in range(per):
            d.append(day(year, m, 1 + i)); t.append(100.0 if i < wins else -100.0)
    return {"trade_date": np.array(d, np.int64), "trade_net": np.array(t)}


def rows(b) -> dict:
    return {r["line"]: r for r in G.winlane(b)}


def test_the_shipped_lane_is_off_on_every_card_and_prints_nothing(lane):
    """One pipeline since 2026-10-18: the win rate is SHOWN on the book card (the edge numbers), the lane asks nothing and prints no row."""
    for unit in ("nq_ib_break_nyam_wl_a5-NQ-tf5", "nq_donch_first_nyam_slow_a5-NQ-tf5", None):
        assert P.winlane(unit) == "off"
    lane("off")
    assert P.winlane() == "off" and G.winlane(months({1: 14})) == []


def test_a_lane_with_no_cards_is_on_every_unit(lane):
    lane("label")
    assert P.winlane() == "label" and P.winlane("anything_a5-NQ-tf5") == "label"
    lane("ask", cards=["x"])
    assert P.winlane("x_a5") == "ask" and P.winlane("x_a5-NQ-tf5") == "ask" and P.winlane("xy_a5-NQ-tf5") == "off" and P.winlane("x_a5y") == "off"


def test_cards_that_are_not_a_list_of_names_are_refused(lane):
    with pytest.raises(R.RuleError, match="winlane.cards"):
        lane("ask", cards="nq_ib_break_nyam_wl")
        P.winlane()


def test_a_word_the_lane_does_not_know_is_refused(lane):
    with pytest.raises(R.RuleError, match="winlane.mode"):
        lane("sometimes")
        P.winlane()


def test_label_mode_prints_both_rows_and_asks_nothing(lane):
    lane("label")
    r = rows({**months({m: 14 for m in range(1, 11)}), "ids": ["x_pct0p2-r0p5"]})        # 70 % in every month, a half-stop target
    assert list(r) == ["P3.11", "P3.12", "P3.13"]
    assert all(x["passed"] is None for x in r.values()) and all(x["held"] is True for x in r.values())
    bad = rows(months({m: 8 for m in range(1, 11)}))                # 40 %: both missed, still only a label
    assert all(x["passed"] is None and x["held"] is False for x in bad.values())


def test_ask_mode_win_rate_is_seventy_percent_or_more(lane):
    lane("ask")
    at = rows(months({m: 14 for m in range(1, 4)}))                 # exactly 70 %
    assert (at["P3.11"]["passed"], at["P3.11"]["number"]) == (True, 0.7)
    assert at["P3.11"]["text"] == "P3.11 PASS win rate 70 % on 60 trades (need 70 % or more)"
    below = rows(months({1: 14, 2: 14, 3: 13}))                     # 41 of 60 = 68.3 %
    assert below["P3.11"]["passed"] is False


def test_ask_mode_a_trade_that_nets_nothing_is_not_a_win(lane):
    lane("ask")
    b = months({1: 14, 2: 14})
    b["trade_net"][:6] = 0.0                                        # six of the wins net exactly $0
    assert rows(b)["P3.11"]["number"] == pytest.approx(22 / 40)


def test_ask_mode_months_share_at_the_floor(lane):
    lane("ask")
    eleven_good = {m: 14 for m in range(1, 12)} | {12: 4}           # 11 months at 70 %, one at 20 %: 91.7 % of the months
    r = rows(months(eleven_good))["P3.12"]
    assert (r["passed"], round(r["number"], 4)) == (True, 0.9167)
    assert r["text"] == "P3.12 PASS 11 of 12 months at 60 % wins or better, 91.67 % (need 90 % or more); worst month 2024-12 at 20 %"
    two_bad = {m: 14 for m in range(1, 11)} | {11: 4, 12: 6}        # two bad months: 83.3 %
    assert rows(months(two_bad))["P3.12"]["passed"] is False
    edge = rows(months({m: 12 for m in range(1, 13)}))["P3.12"]     # every month exactly 60 %: the floor itself counts
    assert edge["passed"] is True and edge["number"] == 1.0


def test_ask_mode_thin_months_are_left_out_and_said(lane):
    lane("ask")
    b = months({m: 14 for m in range(1, 6)})
    b2 = months({6: 1}, per=3)                                      # June: 3 trades, one win: left out, not a bad month
    both = {k: np.concatenate([b[k], b2[k]]) for k in b}
    r = rows(both)["P3.12"]
    assert r["passed"] is True and r["text"].endswith("; 1 month under 10 trades left out")
    none = rows(months({1: 1}, per=4))["P3.12"]                     # no month has 10 trades: the row does not apply
    assert none["passed"] is None and none["text"] == "P3.12 n/a  no month has 10 trades: the row does not apply"   # (n/a rows print two spaces, as lines._row makes them)


def test_without_a_list_of_trades_the_rows_do_not_apply(lane):
    lane("ask")
    r = {x["line"]: x for x in G.winlane({})}
    assert r["P3.11"]["passed"] is None and r["P3.12"]["passed"] is None


def test_in_variant_rows_the_lane_adds_nothing_when_off_and_two_rows_when_on(lane):
    import test_pipe_gates as T
    one = T.sided(T.boxes(1, 1, 80.0, 200))
    box = {**one, **months({m: 14 for m in range(1, 11)})}
    lane("off")
    base = [r["line"] for r in G.variant_rows(box, [])]
    assert "P3.11" not in base and base[-4:] == ["P3.8", "P3.9", "P3.10", "P3.15"]           # (edge mode: P3.15 last)
    lane("ask")
    on = [r["line"] for r in G.variant_rows(box, [])]
    assert on == base[:-1] + ["P3.11", "P3.12", "P3.13", "P3.15"]
    lane("label")
    marks = {r["line"]: r["passed"] for r in G.variant_rows(box, [])}
    assert marks["P3.11"] is None and marks["P3.12"] is None                    # a label asks nothing


def test_p313_asks_for_a_target_of_at_most_the_cap_read_from_the_box_id(lane):
    lane("ask")
    one = lambda cell: {r["line"]: r for r in G._low_target({"ids": [cell]}, P.need("winlane"))}["P3.13"]   # noqa: E731
    assert one("ib_min30_pct0p2-r0p5")["passed"] is True and one("k0p3_atr3-r0p75")["passed"] is True
    assert one("ib_min60_atr3-r3")["passed"] is False and one("x-r1p5")["passed"] is False
    assert one("x-rnone")["passed"] is False and one("")["passed"] is False               # no target in R = no low target
    lane("ask", max_target_r=None)
    assert G._low_target({"ids": ["x-r3"]}, P.need("winlane")) == []                       # no cap in the file = no row
