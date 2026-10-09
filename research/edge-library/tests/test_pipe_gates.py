"""LOCK of the pipeline's gates (blueprint/pipe_gates.py) -- pipeline plan A, task 4. HAND-MADE TABLES ONLY: the edge of every
number a gate holds a table against.

1. numbers(t): the six raw numbers of a table.
2. raw(t), stage 1: strict / low / fail. Exactly 50 % of the boxes is not "over half", exactly 60 % is not "over 60 %"; an
   average trade exactly at half the floor meets the low bar, a cent under it does not; 299 against 300 trades, 199 against
   200; a strict table under 300 trades is strict (the low bar asks MORE trades than the strict one); a table that meets
   the low share and the strict trades only meets neither bar whole.
3. rank(results): a strict pass before a low pass, then the bigger average trade; a tie = the first; all failed = None.
4. indicator(tf, traw, others), stage 3: each of its six rows failing alone; strict_extra = its rows 4 and 6.
5. reshuffle(t), stage 4: exactly 75 % of the runs, and line 2.8's own number.
6. random(p_beat, tries), stage 4: the bar at 1, 2, 5 and 11 tries -- exactly at it (fails) and just above.
7. No number is typed in the gates: a number changed in pipeline.json changes the gate.
Reads the templates only: no store, no tape, no simulation. Seconds.

  pytest tests/test_pipe_gates.py -q          python tests/test_pipe_gates.py     the same, one line per test
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
import pytest  # noqa: E402

from blueprint import lines as L  # noqa: E402
from blueprint import mc as MC  # noqa: E402
from blueprint import pipe_gates as G  # noqa: E402
from blueprint import pipe_rules as P  # noqa: E402
from blueprint import rules as R  # noqa: E402

FILE = P.FILE

@pytest.fixture
def asked(monkeypatch):
    """The other markets with a bar again (pipeline.json holds none since 2026-10-08: they are shown and ask nothing)."""
    monkeypatch.setattr(G, "others_bar", lambda: 0.5)


def teardown_function(_=None):
    P.FILE = FILE
    P._all.cache_clear()


def boxes(good: int, of: int, avg: float, trades=300, root: str = "NQ", **kw) -> dict:
    """A hand-made heat map on ONE day: `of` boxes, `good` of them profitable (the others lose $100 each), an average trade
    of `avg` over all boxes, `trades` trades a box (one number, or one a box)."""
    n = np.full(of, float(trades)) if np.isscalar(trades) else np.array(trades, float)
    bad = of - good
    made = round(avg * n.sum(), 2) + 100.0 * bad                        # what the profitable boxes make together, to the cent
    each = float(made // good)                                          # whole dollars a box, the last one takes the rest: the sum is exact
    net = np.array([-100.0] * bad + [each] * (good - 1) + [made - each * (good - 1)])
    assert each > 0 and net.sum() == round(avg * n.sum(), 2)
    return {"root": root, "net": net[:, None], "n": n[:, None], **kw}


def sided(t: dict, long=100.0, short=100.0, n_long=50, n_short=50, sides="both") -> dict:
    """The same table with its two sides, as tables._data gives them (all variants together) and its card's `sides`."""
    return {**t, "long": long, "short": short, "n_long": n_long, "n_short": n_short, "sides": sides}


class Draws:
    """Stands in for the generator: hands mc.draw the day counts a test wants, one row per run (tests/test_blueprint_lines.py)."""

    def __init__(self, per_run):
        self.w = np.array(per_run)

    def multinomial(self, n, p, size):
        assert self.w.shape == (size, len(p)) and (self.w.sum(1) == n).all()
        return self.w


def by(rows) -> dict:
    return {r["line"]: r for r in rows}


def marks(rows) -> list:
    return [r["passed"] for r in rows]


# ================================================================ 1. the six numbers

def test_numbers_of_a_table():
    t = {"root": "NQ", "net": np.array([[100.0, 50.0], [-30.0, 10.0], [0.0, 0.0], [40.0, -10.0]]), "n": np.array([[2.0, 1], [1, 1], [0, 0], [3, 0]]),
         "long": 120.0, "short": 40.0, "n_long": 5, "n_short": 3}
    assert G.numbers(t) == {"share": 0.5, "avg_trade": 20.0, "trades": 2.0, "avg_variant": 40.0, "long": 120.0, "short": 40.0}     # a box at $0 is not profitable
    assert G.numbers({**t, "n_short": 0})["short"] is None                                 # a side without a trade has no number (lines.sides)
    r = G.numbers(boxes(1, 2, 50.0, 0))                                                   # no trade: no average trade
    assert r["avg_trade"] is None and r["trades"] == 0.0 and r["long"] is None and r["short"] is None      # a table without its sides: none
    b = boxes(7, 10, 70.0, 200)
    assert G.numbers(b) == {"share": 0.7, "avg_trade": 70.0, "trades": 200.0, "avg_variant": 14000.0, "long": None, "short": None}


# ================================================================ 2. the raw heat map: strict / low / fail

def test_raw_strict_low_and_fail():
    r = G.raw(boxes(7, 10, 70.0, 200))                                                    # every strict number exactly met or just over
    assert r["result"] == "strict" and r["avg_trade"] == 70.0 and [x["line"] for x in r["lines"]] == ["P1.1", "P1.2", "P1.3"]
    assert [x["bar"] for x in r["lines"]] == ["strict"] * 3 and marks(r["lines"]) == [True] * 3
    assert [x["text"] for x in r["lines"]] == ["P1.1 STRICT 70 % of boxes profitable (7 of 10; strict needs over 60 %, low needs over 50 %)",
                                               "P1.2 STRICT average trade $70 (strict needs $70, low needs $35)",
                                               "P1.3 STRICT 200 trades a box (strict needs 200, low needs 300)"]
    assert [x["need"] for x in r["lines"]] == [{"strict": 0.6, "low": 0.5}, {"strict": 70.0, "low": 35.0}, {"strict": 200, "low": 300}]
    assert [x["number"] for x in r["lines"]] == [0.7, 70.0, 200.0] and (r["lines"][0]["profitable"], r["lines"][0]["variants"]) == (7, 10)
    assert r["text"] == "strict pass: the three numbers meet the strict bar"
    r = G.raw(boxes(11, 20, 41.0, 300))                                                   # 55 %, $41, 300 trades: the low bar and no more
    assert r["result"] == "low" and r["avg_trade"] == 41.0 and [x["bar"] for x in r["lines"]] == ["low", "low", "strict"] and marks(r["lines"]) == [True] * 3
    assert r["lines"][1]["text"] == "P1.2 LOW average trade $41 (strict needs $70, low needs $35)"
    assert r["lines"][0]["text"] == "P1.1 LOW 55 % of boxes profitable (11 of 20; strict needs over 60 %, low needs over 50 %)"
    assert r["lines"][2]["meets"] == {"strict": True, "low": True} and r["lines"][0]["meets"] == {"strict": False, "low": True}
    assert r["text"] == "low pass: the three numbers meet the low bar; the strict bar is missed by P1.1, P1.2"
    r = G.raw(boxes(4, 10, 20.0, 150))
    assert r["result"] == "fail" and [x["bar"] for x in r["lines"]] == [None] * 3 and marks(r["lines"]) == [False] * 3
    assert r["lines"][2]["text"] == "P1.3 FAIL 150 trades a box (strict needs 200, low needs 300)"
    assert r["text"] == "fail: the strict bar is missed by P1.1, P1.2, P1.3; the low bar by P1.1, P1.2, P1.3"
    assert G.raw(boxes(8, 10, 90.0, 400))["result"] == "strict"                           # both bars met: strict wins
    for r in (G.raw(boxes(7, 10, 70.0, 200)), G.raw(boxes(7, 10, 50.0, 0)), G.indicator(with_it(), RAW, OTHERS), G.indicator(with_it(trades=0), RAW, []),
              G.reshuffle(boxes(7, 10, 70.0, 200)), G.random(0.96, 2), G.numbers(with_it())):
        assert json.loads(json.dumps(r)) == r                                             # a stage card is a JSON file: plain numbers, no numpy


def test_raw_share_of_boxes_is_over_not_at():
    r = G.raw(boxes(5, 10, 100.0, 300))                                                   # exactly 50 %: not "over half"
    assert r["result"] == "fail" and r["lines"][0]["number"] == 0.5 and r["lines"][0]["passed"] is False and r["lines"][0]["bar"] is None
    assert r["lines"][0]["text"] == "P1.1 FAIL 50 % of boxes profitable (5 of 10; strict needs over 60 %, low needs over 50 %)"
    assert marks(r["lines"]) == [False, True, True] and r["text"] == "fail: the strict bar is missed by P1.1; the low bar by P1.1"
    r = G.raw(boxes(51, 100, 100.0, 300))                                                 # 51 %: over half
    assert r["result"] == "low" and r["lines"][0]["bar"] == "low"
    r = G.raw(boxes(6, 10, 100.0, 300))                                                   # exactly 60 %: not "over 60 %" -> the low bar
    assert r["result"] == "low" and r["lines"][0]["number"] == 0.6 and r["lines"][0]["bar"] == "low" and r["lines"][0]["passed"] is True
    assert G.raw(boxes(6, 10, 100.0, 299))["result"] == "fail"                            # ... and the low bar asks 300 trades
    assert G.raw(boxes(61, 100, 100.0, 200))["result"] == "strict"
    assert G.raw(boxes(72, 144, 100.0, 300))["result"] == "fail" and G.raw(boxes(73, 144, 100.0, 300))["result"] == "low"      # a real heat map: 144 boxes
    assert G.raw(boxes(86, 144, 100.0, 300))["result"] == "low" and G.raw(boxes(87, 144, 100.0, 300))["result"] == "strict"


def test_raw_average_trade_is_at_or_above():
    r = G.raw(boxes(11, 20, 35.0, 300))                                                   # exactly half the floor: "at" passes the low bar
    assert r["result"] == "low" and r["avg_trade"] == 35.0 and r["lines"][1]["bar"] == "low" and r["lines"][1]["passed"] is True
    assert r["lines"][1]["text"] == "P1.2 LOW average trade $35 (strict needs $70, low needs $35)"
    r = G.raw(boxes(11, 20, 34.99, 300))                                                  # a cent under: the text shows the cents
    assert r["result"] == "fail" and r["avg_trade"] < 35.0 and r["lines"][1]["passed"] is False and r["lines"][1]["bar"] is None
    assert r["lines"][1]["text"] == "P1.2 FAIL average trade $34.99 (strict needs $70, low needs $35)"
    r = G.raw(boxes(7, 10, 70.0, 200))                                                    # exactly the full floor: strict
    assert r["result"] == "strict" and r["lines"][1]["bar"] == "strict"
    r = G.raw(boxes(7, 10, 69.99, 200))                                                   # a cent under the full floor: the low bar, which asks 300 trades
    assert r["result"] == "fail" and r["lines"][1]["bar"] == "low" and r["lines"][1]["text"] == "P1.2 LOW average trade $69.99 (strict needs $70, low needs $35)"
    assert G.raw(boxes(7, 10, 69.99, 300))["result"] == "low"
    r = G.raw(boxes(11, 20, 37.5, 300, root="ES"))                                        # each market its own floor: ES $75 -> $37.50
    assert r["result"] == "low" and r["lines"][1]["need"] == {"strict": 75.0, "low": 37.5}
    assert r["lines"][1]["text"] == "P1.2 LOW average trade $37.50 (strict needs $75, low needs $37.50)"
    assert G.raw(boxes(11, 20, 37.0, 300, root="ES"))["result"] == "fail"
    assert G.raw(boxes(11, 20, 37.0, 300, root="ES"))["lines"][1]["text"] == "P1.2 FAIL average trade $37 (strict needs $75, low needs $37.50)"
    assert G.raw(boxes(11, 20, 70.0, 300, root="GC"))["result"] == "low" and G.raw(boxes(11, 20, 69.0, 300, root="GC"))["result"] == "fail"
    assert G.raw(boxes(7, 10, 140.0, 200, root="GC"))["result"] == "strict" and G.raw(boxes(7, 10, 139.0, 200, root="GC"))["result"] == "fail"
    r = G.raw(boxes(7, 10, 50.0, 0))                                                      # no trade: no average trade, nothing met
    assert r["result"] == "fail" and r["avg_trade"] is None and r["lines"][1]["number"] is None and r["lines"][1]["passed"] is False
    assert r["lines"][1]["text"] == "P1.2 FAIL no trade (strict needs $70, low needs $35)"
    try:
        G.raw(boxes(7, 10, 70.0, 200, root="CL"))                                         # a market the law names no floor for
    except R.RuleError as e:
        assert "CL" in str(e)
    else:
        raise AssertionError("a market without a floor was judged")


def test_raw_trades_a_box():
    assert G.raw(boxes(11, 20, 41.0, 300))["result"] == "low"                             # 300: "300+"
    r = G.raw(boxes(11, 20, 41.0, 299))                                                   # 299: under the low bar's count, and the table is not strict
    assert r["result"] == "fail" and r["lines"][2]["number"] == 299.0 and r["lines"][2]["bar"] == "strict" and r["lines"][2]["passed"] is True
    assert r["lines"][2]["text"] == "P1.3 STRICT 299 trades a box (strict needs 200, low needs 300)"
    assert r["text"] == "fail: the strict bar is missed by P1.1, P1.2; the low bar by P1.3"        # no row is under both bars, and the table still fails
    half = boxes(11, 20, 41.0, [299] * 10 + [300] * 10)                                   # the mean over the boxes: 299.5 is not 300
    assert G.numbers(half)["trades"] == 299.5 and G.raw(half)["result"] == "fail" and "299.50 trades a box" in G.raw(half)["lines"][2]["text"]
    assert G.raw(boxes(11, 20, 41.0, [0] * 10 + [600] * 10))["result"] == "low"           # ... the mean, not every box
    assert G.raw(boxes(7, 10, 70.0, 200))["result"] == "strict"                           # 200: "200+"
    r = G.raw(boxes(7, 10, 70.0, 199))
    assert r["result"] == "fail" and r["lines"][2]["passed"] is False and r["lines"][2]["bar"] is None and marks(r["lines"]) == [True, True, False]
    r = G.raw(boxes(7, 10, 70.0, 250))                                                    # STRICT, AND UNDER THE LOW BAR'S 300 TRADES: strict wins
    assert r["result"] == "strict" and r["lines"][2]["meets"] == {"strict": True, "low": False} and r["lines"][2]["bar"] == "strict"
    assert r["text"] == "strict pass: the three numbers meet the strict bar"


def test_a_strict_table_meets_the_laws_own_lines():
    for t in (boxes(7, 10, 70.0, 200), boxes(87, 144, 70.0, 200), boxes(61, 100, 140.0, 250, root="GC")):
        assert G.raw(t)["result"] == "strict" and L.heat(t)["passed"] and L.floor(t)["passed"] and L.trades(t)["passed"]      # 2.1, 2.2, 2.4
    for t in (boxes(6, 10, 70.0, 200), boxes(7, 10, 69.99, 200), boxes(7, 10, 70.0, 199)):                                  # and one line of the law missed: not strict
        assert G.raw(t)["result"] != "strict" and not (L.heat(t)["passed"] and L.floor(t)["passed"] and L.trades(t)["passed"])
    t = boxes(87, 144, 83.0, 217)                                                         # and the numbers are the law's, each under its own line
    assert [x["number"] for x in G.raw(t)["lines"]] == [L.heat(t)["number"], L.floor(t)["number"], L.trades(t)["number"]]


# ================================================================ 3. which heat map moves on

def test_rank_strict_before_low_then_the_bigger_average_trade():
    strict, low, fail = (lambda a, tr=200: G.raw(boxes(7, 10, a, tr))), (lambda a: G.raw(boxes(11, 20, a, 300))), G.raw(boxes(4, 10, 500.0, 900))
    assert [strict(80.0)["result"], low(60.0)["result"], fail["result"]] == ["strict", "low", "fail"]
    assert G.rank([low(69.0), strict(70.0)]) == 1                                         # a strict pass before a low pass ...
    assert G.rank([low(69.0), strict(70.0), low(68.0)]) == 1
    assert G.rank([strict(70.0), strict(90.0), strict(80.0)]) == 1                        # ... then the biggest average trade
    assert G.rank([low(40.0), low(60.0), low(50.0)]) == 1
    assert G.rank([fail, low(40.0), strict(71.0), strict(75.0), low(69.0)]) == 3          # a failed table never, whatever its average trade
    assert G.rank([strict(80.0), strict(80.0)]) == 0 and G.rank([low(50.0), fail, low(50.0)]) == 0      # a tie: the first
    assert G.rank([fail, strict(80.0), strict(80.0, 250)]) == 1
    assert G.rank([fail, fail]) is None and G.rank([]) is None and G.rank([fail, low(36.0)]) == 1
    assert G.rank([G.raw(boxes(7, 10, 50.0, 0)), fail]) is None                           # no trade: failed, its missing average trade is never compared


# ================================================================ 4. one indicator on the heat map

RAW = boxes(11, 20, 40.0, 300)                              # the raw heat map of a low pass: 55 % of boxes, $40 a trade
OTHERS = [100.0, -5.0]                                      # the same idea on the other two markets: one of them profitable


def with_it(good=14, avg=80.0, trades=200, **side) -> dict:
    """The heat map with one indicator: by default it passes every row (70 % of 20 boxes, $80 a trade, 200 trades a box)."""
    return sided(boxes(good, 20, avg, trades), **side)


def test_indicator_all_six_rows(asked):
    rows = G.indicator(with_it(), RAW, OTHERS)
    assert [r["line"] for r in rows] == ["P3.1", "P3.2", "P3.3", "P3.4", "P3.5", "P3.6"] and marks(rows) == [True] * 6
    assert [r["text"] for r in rows] == [
        "P3.1 PASS 70 % of boxes profitable (14 of 20; need over 60 %)",
        "P3.2 PASS average trade $80 (need $70)",
        "P3.3 PASS 200 trades a box (need 200)",
        "P3.4 PASS long $100, short $100, all variants together (need both above $0)",
        "P3.5 PASS average trade $80 with it, $40 without; 70 % of boxes profitable with it, 55 % without (need both higher)",
        "P3.6 PASS 1 of 2 other-market heat maps profitable, 50 % (need 50 % or more)"]
    assert [r["number"] for r in rows] == [0.7, 80.0, 200.0, 100.0, 80.0, 0.5] and [r["need"] for r in rows] == [0.6, 70.0, 200, 0, 40.0, 0.5]
    assert (rows[4]["share"], rows[4]["raw_share"], rows[4]["raw_avg_trade"]) == (0.7, 0.55, 40.0)


def test_indicator_each_row_failing_alone(asked):
    def failed(tf, traw=RAW, others=OTHERS):
        return [r["line"] for r in G.indicator(tf, traw, others) if r["passed"] is not True]

    assert failed(with_it()) == []
    r = by(G.indicator(with_it(good=12), RAW, OTHERS))["P3.1"]                            # exactly 60 %: not "over 60 %" (and still over the raw 55 %)
    assert failed(with_it(good=12)) == ["P3.1"] and r["text"] == "P3.1 FAIL 60 % of boxes profitable (12 of 20; need over 60 %)"
    assert failed(with_it(good=13)) == []
    r = by(G.indicator(with_it(avg=69.99), RAW, OTHERS))["P3.2"]                          # a cent under the FULL floor: no half floor here
    assert failed(with_it(avg=69.99)) == ["P3.2"] and r["text"] == "P3.2 FAIL average trade $69.99 (need $70)"
    assert failed(with_it(avg=70.0)) == []
    r = by(G.indicator(with_it(trades=199), RAW, OTHERS))["P3.3"]
    assert failed(with_it(trades=199)) == ["P3.3"] and r["text"] == "P3.3 FAIL 199 trades a box (need 200)"
    assert failed(with_it(short=-1.0)) == ["P3.4"] and failed(with_it(long=0.0)) == ["P3.4"]              # a side at $0 makes no money
    assert failed(with_it(n_short=0)) == ["P3.4"]                                         # both sides by its card: a side without a trade made none
    assert failed(with_it(avg=80.0), boxes(11, 20, 80.0, 300)) == ["P3.5"]                # the same average trade as the raw table: not higher
    assert failed(with_it(avg=80.0), boxes(11, 20, 79.99, 300)) == []
    assert "average trade $80.00 with it, $79.99 without" in by(G.indicator(with_it(), boxes(11, 20, 79.99, 300), OTHERS))["P3.5"]["text"]
    assert failed(with_it(good=14), boxes(14, 20, 40.0, 300)) == ["P3.5"]                 # the same share of boxes: not higher
    assert failed(with_it(good=14), boxes(15, 20, 40.0, 300)) == ["P3.5"] and failed(with_it(good=14), boxes(13, 20, 40.0, 300)) == []
    r = by(G.indicator(with_it(), boxes(14, 20, 90.0, 300), OTHERS))["P3.5"]
    assert r["passed"] is False and r["text"] == "P3.5 FAIL average trade $80 with it, $90 without; 70 % of boxes profitable with it, 70 % without (need both higher)"
    assert failed(with_it(), others=[100.0, -5.0, -5.0]) == ["P3.6"]                      # 1 of 3 other markets
    assert failed(with_it(), others=[0.0]) == ["P3.6"] and failed(with_it(), others=[0.0, 0.01]) == []   # $0 is not profitable; exactly half is enough
    assert failed(with_it(), others=[100.0]) == [] and failed(with_it(), others=[-1.0, -1.0]) == ["P3.6"]
    r = by(G.indicator(with_it(), RAW, [100.0, -5.0, -5.0]))["P3.6"]
    assert r["text"] == "P3.6 FAIL 1 of 3 other-market heat maps profitable, 33.33 % (need 50 % or more)" and (r["profitable"], r["tables"]) == (1, 3)


def test_indicator_one_sided_no_other_market_and_no_trade(asked):
    rows = by(G.indicator(with_it(sides="long", short=0.0, n_short=0), RAW, OTHERS))      # a one-sided idea: its side
    assert rows["P3.4"]["passed"] is True and rows["P3.4"]["text"] == "P3.4 PASS long only by its card: $100, all variants together (need above $0)"
    assert by(G.indicator(with_it(sides="long", long=-1.0, n_short=0), RAW, OTHERS))["P3.4"]["passed"] is False
    assert by(G.indicator(with_it(sides="short", long=0.0, n_long=0, short=5.0), RAW, OTHERS))["P3.4"]["passed"] is True
    r = by(G.indicator(with_it(sides="long", short=900.0), RAW, OTHERS))["P3.4"]          # a trade on the other side is not the card's rule (line 2.6)
    assert r["passed"] is False and "50 short trades are not the card's rule" in r["text"]
    for t in (with_it(), with_it(short=-1.0), with_it(sides="long", n_short=0), with_it(sides="long")):
        a, b = by(G.indicator(t, RAW, OTHERS))["P3.4"], L.sides(t)                        # P3.4 IS line 2.6's reading, under its own number
        assert (a["passed"], a["number"], a["need"]) == (b["passed"], b["number"], b["need"]) and a["text"] == "P3.4" + b["text"][3:] and b["line"] == "2.6"
    r = by(G.indicator(with_it(), RAW, []))["P3.6"]                                       # no other market runs this idea: the row does not apply
    assert r["passed"] is None and r["number"] is None and r["need"] == 0.5 and "no other market runs this idea" in r["text"] and r["text"].startswith("P3.6 n/a ")
    rows = G.indicator(with_it(trades=0), RAW, OTHERS)                                    # no trade with the indicator: no average trade to hold up
    assert marks(rows) == [True, False, False, True, False, True] and by(rows)["P3.2"]["text"] == "P3.2 FAIL no trade (need an average trade of $70)"
    assert by(rows)["P3.5"]["text"] == "P3.5 FAIL no trade with it, $40 without; 70 % of boxes profitable with it, 55 % without (need both higher)"
    gc = by(G.indicator(sided(boxes(14, 20, 139.0, 200, root="GC")), RAW, OTHERS))["P3.2"]         # each market its own floor
    assert gc["passed"] is False and gc["text"] == "P3.2 FAIL average trade $139 (need $140)"


def test_strict_extra_is_rows_4_and_6(asked):
    for t, others in ((with_it(), OTHERS), (with_it(short=-1.0), OTHERS), (with_it(), [-1.0, -1.0]), (with_it(sides="short", n_long=0), []), (with_it(short=0.0), [])):
        full = by(G.indicator(t, RAW, others))
        assert G.strict_extra(t, others) == [full["P3.4"], full["P3.6"]]
    assert marks(G.strict_extra(with_it(), OTHERS)) == [True, True] and marks(G.strict_extra(with_it(short=-1.0), [])) == [False, None]
    assert marks(G.strict_extra(sided(boxes(1, 20, 5.0, 3)), [5.0])) == [True, True]       # only these two: the table's own share and floor are stage 1's


# ================================================================ 5. the reshuffled runs

def test_reshuffle_is_line_2_8_under_its_own_number():
    def split(a, b):                                                    # `a` runs draw day 0 twice, `b` runs draw day 1 twice
        return Draws([[2, 0]] * a + [[0, 2]] * b)

    t = {"root": "NQ", "net": np.array([[100.0, -500.0]] * 3), "n": np.ones((3, 2))}      # day 0: every box +$100 a trade; day 1: -$500
    r = G.reshuffle(t, split(750, 250))                                 # exactly 75 % of the runs: "or more"
    assert r["line"] == "P4.1" and r["passed"] is True and r["number"] == 0.75 and r["need"] == 0.75 == P.need("proof", "reshuffle") and r["runs"] == 1000
    assert r["text"] == "P4.1 PASS over 60 % of boxes profitable and an average trade of $70 or more both hold in 75 % of 1,000 reshuffled runs (need 75 % or more)"
    r = G.reshuffle(t, split(749, 251))
    assert r["passed"] is False and r["number"] == 0.749 and "74.9 %" in r["text"] and r["text"].startswith("P4.1 FAIL ")
    low = {"root": "NQ", "net": np.array([[60.0, -500.0]] * 3), "n": np.ones((3, 2))}     # every box green in every run, $60 a trade: the FULL floor, not half
    assert G.reshuffle(low, split(1000, 0))["number"] == 0.0 and G.reshuffle({**low, "root": "ES"}, split(1000, 0))["passed"] is False
    edge = {"root": "NQ", "net": np.array([[500.0, -500.0]] * 3 + [[-90.0, -500.0]] * 2), "n": np.ones((5, 2))}      # 3 of 5 boxes green = exactly 60 %: the STRICT share
    assert G.reshuffle(edge, split(1000, 0))["number"] == 0.0
    mix = {"root": "NQ", "net": np.array([[300.0, 0.0], [300.0, 0.0], [0.0, 300.0]]), "n": np.ones((3, 2))}          # the same days for every box
    assert G.reshuffle(mix, split(600, 400))["number"] == 0.6
    for x, w in ((t, split(750, 250)), (t, split(749, 251)), (low, split(1000, 0)), (edge, split(1000, 0)), (mix, split(600, 400))):
        a, b = G.reshuffle(x, w), L.monte(x, w)                         # line 2.8's own computation, number for number
        assert (a["passed"], a["number"], a["need"], a["runs"]) == (b["passed"], b["number"], b["need"], b["runs"])
    net = np.random.default_rng(7).normal(50, 400, (6, 40)).round()     # the real draws: the fixed seed, the same number every time
    real = {"root": "NQ", "net": net, "n": np.ones((6, 40))}
    assert G.reshuffle(real)["number"] == G.reshuffle(real)["number"] == G.reshuffle(real, MC.generator())["number"] == L.monte(real)["number"]
    assert G.reshuffle({**real, "net": np.abs(net) + 70})["number"] == 1.0 and G.reshuffle({**real, "net": -np.abs(net)})["number"] == 0.0


# ================================================================ 6. the random bar

def test_random_bar_at_1_2_5_and_11_tries():
    for tries, bar in ((1, 0.95), (2, 0.975), (5, 0.99), (11, 1 - 0.05 / 11)):
        assert P.random_bar(tries) == bar
        at, over = G.random(bar, tries), G.random(float(np.nextafter(bar, 1.0)), tries)
        assert at["passed"] is False and over["passed"] is True, tries              # exactly at the bar: not "better than"
        assert at["line"] == "P4.2" and at["need"] == bar and at["number"] == bar and at["tries"] == tries
        assert G.random(bar - 0.0001, tries)["passed"] is False and G.random(bar + 0.0001, tries)["passed"] is True
    assert G.random(0.95, 1)["text"] == "P4.2 FAIL beats 95 % of the random heat maps on try 1 (need above 95 % = 100 - 5 / 1 try)"
    assert G.random(0.9501, 1)["text"] == "P4.2 PASS beats 95.01 % of the random heat maps on try 1 (need above 95 % = 100 - 5 / 1 try)"
    assert G.random(0.975, 2)["text"] == "P4.2 FAIL beats 97.5 % of the random heat maps on try 2 (need above 97.5 % = 100 - 5 / 2 tries)"
    assert G.random(0.9901, 5)["text"] == "P4.2 PASS beats 99.01 % of the random heat maps on try 5 (need above 99 % = 100 - 5 / 5 tries)"
    r = G.random(0.995, 11)                                             # 99.5 % at 11 tries: under 99.5455 %, and the text tells them apart
    assert r["passed"] is False and r["text"] == "P4.2 FAIL beats 99.5 % of the random heat maps on try 11 (need above 99.5455 % = 100 - 5 / 11 tries)"
    r = G.random(0.9955, 11)                                            # the judge's four decimals: 99.55 % is above 99.5455 %
    assert r["passed"] is True and r["text"] == "P4.2 PASS beats 99.55 % of the random heat maps on try 11 (need above 99.5455 % = 100 - 5 / 11 tries)"
    assert G.random(0.9954, 11)["passed"] is False and G.random(0.97, 2)["passed"] is False and G.random(0.97, 1)["passed"] is True      # every try raises the bar
    assert G.random(1.0, 10 ** 6)["passed"] is True and G.random(0.96, 0)["need"] == 0.95 and G.random(0.96, 0)["passed"] is True       # no try yet: the first bar
    r = G.random(None, 3)                                               # no random heat map was read: nothing beaten
    assert r["passed"] is False and r["number"] is None and r["text"].startswith("P4.2 FAIL no random heat maps to hold it against (need above 98.3333 %")


# ================================================================ 7. every number is read from pipeline.json

def test_a_number_changed_in_the_file_changes_the_gate():
    edge, strict = boxes(5, 10, 100.0, 300), boxes(7, 10, 70.0, 250)
    assert G.raw(edge)["result"] == "fail" and G.raw(strict)["result"] == "strict" and G.random(0.96, 1)["passed"] is True
    p = copy.deepcopy(json.loads(FILE.read_text(encoding="utf-8")))
    p["raw"]["low"].update(share=0.4, floor_part=0.25, trades=250)      # the pipeline's own numbers: the law does not carry them
    p["indicator"].update(floor_part=1.5, other_markets=0.75)
    with tempfile.TemporaryDirectory() as tmp:
        P.FILE = Path(tmp) / "pipeline.json"
        P.FILE.write_text(json.dumps(p), encoding="utf-8")
        P._all.cache_clear()
        r = G.raw(edge)
        assert r["result"] == "low" and r["lines"][0]["need"] == {"strict": 0.6, "low": 0.4} and r["lines"][1]["need"] == {"strict": 70.0, "low": 17.5}
        assert "low needs over 40 %" in r["lines"][0]["text"] and "low needs $17.50" in r["lines"][1]["text"] and "low needs 250" in r["lines"][2]["text"]
        assert G.raw(boxes(5, 10, 17.5, 250))["result"] == "low" and G.raw(boxes(5, 10, 17.5, 249))["result"] == "fail"
        rows = by(G.indicator(with_it(avg=104.99), RAW, [1.0, 1.0, -1.0, -1.0]))
        assert rows["P3.2"]["passed"] is False and rows["P3.2"]["need"] == 105.0 and rows["P3.6"]["passed"] is False and rows["P3.6"]["need"] == 0.75
        assert by(G.indicator(with_it(avg=105.0), RAW, [1.0, 1.0, 1.0, -1.0]))["P3.6"]["passed"] is True
    teardown_function()
    assert G.raw(edge)["result"] == "fail" and by(G.indicator(with_it(), RAW, OTHERS))["P3.2"]["need"] == 70.0
    src = (W / "blueprint" / "pipe_gates.py").read_text(encoding="utf-8").split('"""', 2)[2]      # the code under the docstring: no gate number in it
    for number in ("0.5", "0.6", "0.75", "0.05", "200", "300", "70", "140", "0.95"):
        assert number not in src, f"{number} is typed in pipe_gates.py"


if __name__ == "__main__":
    import time
    rc = 0
    for name, t in [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]:
        t0 = time.monotonic()
        try:
            t()
            print(f"PASS {name} ({time.monotonic() - t0:.1f} s)", flush=True)
        except AssertionError as e:
            rc = 1
            print(f"FAIL {name}\n{e}", flush=True)
        finally:
            teardown_function()
    sys.exit(rc)


def test_the_other_markets_are_shown_and_ask_nothing_when_the_file_holds_no_bar():
    """The owner, 2026-10-08: "the same idea could work on another market, but not the exact same" -- no bar in pipeline.json."""
    assert G.others_bar() is None
    t = with_it()
    for others, said in (([-1.0, -1.0], "P3.6 n/a  0 of 2 other-market heat maps profitable, 0 % (shown: the other markets ask nothing of an idea)"),
                         ([5.0, -1.0], "P3.6 n/a  1 of 2 other-market heat maps profitable, 50 % (shown: the other markets ask nothing of an idea)"),
                         ([], "P3.6 n/a  no other market runs this idea (shown: the other markets ask nothing of an idea)")):
        r = G.strict_extra(t, others)[1]
        assert (r["line"], r["passed"], r["need"], r["text"]) == ("P3.6", None, None, said), r
        assert [x for x in G.indicator(t, RAW, others) if x["line"] == "P3.6"][0]["passed"] is None


# ================================================================ 8. VARIANT MODE (the owner, 2026-10-08): the map gets a loose check, ONE picked box gets the hard rules

def grid(avg, trades, of=None, root: str = "NQ", days: int = 1, **kw) -> dict:
    """A hand-made heat map, one box a number of `avg` (the average trade of each box) and `trades` (its trades): ids c0, c1, ..."""
    avg, trades = np.asarray(avg, float), np.asarray(trades, float)
    avg, trades = np.broadcast_to(avg, np.broadcast(avg, trades).shape).copy(), np.broadcast_to(trades, np.broadcast(avg, trades).shape).copy()
    net = (avg * trades).round(2)
    return {"root": root, "net": net[:, None] / days * np.ones((1, days)), "n": trades[:, None] / days * np.ones((1, days)), "ids": [f"c{i}" for i in range(len(net))], **kw}


def test_variant_map_check_is_loose_share_and_a_region_at_the_floor():
    """Stage 1 in variant mode: over `map_share` of the boxes profitable AND at least `region_boxes` boxes with an average trade at the floor
    and `region_trades` trades. One level: "pass" or "fail"."""
    need = P.need("variant")
    k, of = need["region_boxes"], 40
    avg = [70.0] * k + [-5.0] * (of - k)                                  # exactly 25 boxes at $70 (the floor, "at or above"), 15 losing boxes
    t = grid(avg, [200] * of)
    r = G.variant_map(t)
    assert r["result"] == "pass" and r["qualifying"] == k == len(r["cells"]) and r["cells"] == [f"c{i}" for i in range(k)]
    assert [x["line"] for x in r["lines"]] == ["P1.1", "P1.2"] and marks(r["lines"]) == [True, True] and r["avg_trade"] is not None
    assert r["lines"][0]["number"] == 25 / 40 and r["lines"][0]["need"] == need["map_share"]
    assert r["lines"][1]["number"] == k and r["lines"][1]["need"] == k
    assert r["lines"][0]["text"] == "P1.1 PASS 62.5 % of boxes profitable (25 of 40; need over 50 %)"
    assert r["lines"][1]["text"] == f"P1.2 PASS {k} of 40 boxes have an average trade of $70 or more with 200 or more trades (need at least {k})"
    assert r["text"] == f"pass: over 50 % of boxes profitable and {k} boxes at the floor with enough trades"
    one_less = G.variant_map(grid([70.0] * (k - 1) + [-5.0] * (of - k + 1), [200] * of))        # 24 boxes: not enough, "at least 25"
    assert one_less["result"] == "fail" and marks(one_less["lines"]) == [True, False] and one_less["qualifying"] == k - 1
    assert one_less["lines"][1]["text"] == f"P1.2 FAIL {k - 1} of 40 boxes have an average trade of $70 or more with 200 or more trades (need at least {k})"
    assert one_less["text"] == "fail: P1.2 is missed"
    cent = G.variant_map(grid([69.99] * k + [-5.0] * (of - k), [200] * of))                     # a cent under the floor: not at the floor
    assert cent["qualifying"] == 0 and cent["result"] == "fail"
    few = G.variant_map(grid([70.0] * k + [-5.0] * (of - k), [199] * k + [200] * (of - k)))       # 199 trades: one under
    assert few["qualifying"] == 0
    half = G.variant_map(grid([70.0] * 25 + [-5.0] * 25, [200] * 50))                              # exactly 50 % profitable: not "over" half
    assert half["lines"][0]["passed"] is False and half["lines"][0]["number"] == 0.5 and half["result"] == "fail" and half["qualifying"] == 25
    assert half["lines"][0]["text"] == "P1.1 FAIL 50 % of boxes profitable (25 of 50; need over 50 %)"
    both = G.variant_map(grid([10.0] * 30 + [-5.0] * 10, [200] * 40))                             # profitable boxes, none at the floor
    assert marks(both["lines"]) == [True, False] and both["qualifying"] == 0
    assert G.variant_map(grid([70.0] * 40, [0] * 40))["qualifying"] == 0                          # no trade is no average trade
    es, gc = G.variant_map(grid([75.0] * 30, [200] * 30, root="ES")), G.variant_map(grid([139.0] * 30, [300] * 30, root="GC"))      # each market its own floor
    assert es["qualifying"] == 30 and gc["qualifying"] == 0


def test_variant_map_ranks_by_the_number_of_qualifying_boxes():
    def res(q, at, result="pass"):
        return {"result": result, "qualifying": q, "avg_trade": at}

    assert G.rank([res(30, 50.0), res(40, 10.0)]) == 1                          # more boxes at the floor first, whatever the average trade
    assert G.rank([res(30, 50.0), res(30, 60.0)]) == 1                          # a tie: the bigger average trade
    assert G.rank([res(30, 50.0), res(30, 50.0)]) == 0                          # a tie again: the first
    assert G.rank([res(0, None, "fail"), res(26, 40.0)]) == 1 and G.rank([res(0, None, "fail"), res(40, 4.0, "fail")]) is None
    assert G.rank([]) is None
    assert G.rank([{"result": "strict", "avg_trade": 80.0}, {"result": "low", "avg_trade": 90.0}]) == 0      # the old results rank the old way


def test_variant_rows_are_the_picked_box_floor_trades_sides_and_the_shown_markets():
    def box(avg=70.0, trades=200, long=100.0, short=100.0, n_long=100, n_short=100, sides="both", root="NQ"):
        return {"root": root, "net": np.array([[avg * trades]]), "n": np.array([[float(trades)]]), "long": long, "short": short, "n_long": n_long,
                "n_short": n_short, "sides": sides}

    rows = G.variant_rows(box(), [3.0, -4.0])
    assert [x["line"] for x in rows] == ["P3.2", "P3.3", "P3.4", "P3.6", "P3.7", "P3.8", "P3.9", "P3.10"] and marks(rows) == [True, True, True, None, None, None, None, None]
    assert rows[0]["text"] == "P3.2 PASS average trade $70 (need $70)" and rows[0]["number"] == 70.0 and rows[0]["need"] == 70.0
    assert rows[1]["text"] == "P3.3 PASS 200 trades (need 200)" and rows[1]["number"] == 200.0 and rows[1]["need"] == P.need("variant", "region_trades")
    assert rows[3]["passed"] is None and rows[3]["need"] is None                         # the other markets: shown, never False
    assert by(G.variant_rows(box(avg=69.99), []))["P3.2"]["passed"] is False and by(G.variant_rows(box(avg=69.99), []))["P3.2"]["text"] == "P3.2 FAIL average trade $69.99 (need $70)"
    assert by(G.variant_rows(box(trades=199, avg=100.0), []))["P3.3"]["passed"] is False
    assert by(G.variant_rows(box(root="GC", avg=139.0), []))["P3.2"]["passed"] is False and by(G.variant_rows(box(root="GC", avg=140.0), []))["P3.2"]["passed"] is True
    assert by(G.variant_rows(box(short=-1.0), []))["P3.4"]["passed"] is False and by(G.variant_rows(box(n_short=0, short=0.0), []))["P3.4"]["passed"] is False      # both: each side
    assert by(rows)["P3.4"]["text"] == "P3.4 PASS long $100, short $100 (need both above $0)"          # (one box: no "all variants together")
    one = by(G.variant_rows(box(sides="long", n_short=0, short=0.0), []))["P3.4"]
    assert one["passed"] is True and one["text"] == "P3.4 PASS long only by its card: $100 (need above $0)"
    bad = by(G.variant_rows(box(sides="long", short=5.0), []))["P3.4"]
    assert bad["passed"] is False                                                          # a trade on the other side is not the card's rule
    none = G.variant_rows({**box(), "net": np.array([[0.0]]), "n": np.array([[0.0]])}, [])    # a box without a trade
    assert marks(none)[:2] == [False, False] and by(none)["P3.2"]["text"] == "P3.2 FAIL no trade (need an average trade of $70)"
    assert G.strict_extra(box(), [3.0, -4.0])[1] == rows[3] and {**G.strict_extra(box(), [3.0, -4.0])[0], "text": rows[2]["text"]} == rows[2]


def test_reshuffle_box_is_the_boxes_average_trade_at_the_floor_in_three_quarters_of_the_runs():
    def split(a, b):
        return Draws([[2, 0]] * a + [[0, 2]] * b)

    b = {"root": "NQ", "net": np.array([[100.0, -500.0]]), "n": np.ones((1, 2))}        # day 0: +$100 a trade; day 1: -$500
    r = G.reshuffle_box(b, split(750, 250))
    assert r["line"] == "P4.1" and r["passed"] is True and r["number"] == 0.75 == r["need"] == P.need("proof", "reshuffle") and r["runs"] == 1000
    assert r["text"] == "P4.1 PASS the box's average trade is $70 or more in 75 % of 1,000 reshuffled runs (need 75 % or more)"
    r = G.reshuffle_box(b, split(749, 251))
    assert r["passed"] is False and r["number"] == 0.749 and r["text"].startswith("P4.1 FAIL ") and "74.9 %" in r["text"]
    assert G.reshuffle_box({**b, "net": np.array([[60.0, -500.0]])}, split(1000, 0))["number"] == 0.0        # $60 a trade is under the floor in every run
    assert G.reshuffle_box({**b, "root": "ES", "net": np.array([[74.0, -500.0]])}, split(1000, 0))["number"] == 0.0
    net = np.random.default_rng(7).normal(80, 400, (1, 60)).round()
    real = {"root": "NQ", "net": net, "n": np.ones((1, 60))}
    assert G.reshuffle_box(real)["number"] == G.reshuffle_box(real, MC.generator())["number"] == G.reshuffle_box(real)["number"]      # the fixed seed
    assert G.reshuffle_box({**real, "n": np.zeros((1, 60))})["number"] == 0.0                              # no trade in a run is no average trade
    tot, cnt = MC.reshuffle(net, np.ones((1, 60)))
    assert G.reshuffle_box(real)["number"] == float((tot[0] / cnt >= 70.0).mean())                      # the same runs as line 2.8's, read for the one box


def test_random_text_says_what_it_was_held_against():
    assert G.random(0.9501, 1)["text"] == "P4.2 PASS beats 95.01 % of the random heat maps on try 1 (need above 95 % = 100 - 5 / 1 try)"      # unchanged
    r = G.random(0.97, 2, "random entries of the same box")
    assert r["text"] == "P4.2 FAIL beats 97 % of the random entries of the same box on try 2 (need above 97.5 % = 100 - 5 / 2 tries)" and r["passed"] is False
    assert G.random(None, 2, "random entries of the same box")["text"].startswith("P4.2 FAIL no random entries of the same box to hold it against")


def test_variant_numbers_are_read_from_the_file_and_typed_nowhere():
    t = grid([70.0] * 20 + [-5.0] * 20, [200] * 40)
    assert G.variant_map(t)["result"] == "fail"                                            # 20 boxes of the 25 the file asks for
    p = copy.deepcopy(json.loads(FILE.read_text(encoding="utf-8")))
    p["variant"].update(region_boxes=20, region_trades=250, floor_part=0.5, map_share=0.4)
    with tempfile.TemporaryDirectory() as tmp:
        P.FILE = Path(tmp) / "pipeline.json"
        P.FILE.write_text(json.dumps(p), encoding="utf-8")
        P._all.cache_clear()
        assert G.variant_map(grid([35.0] * 20 + [-5.0] * 20, [250] * 40))["result"] == "pass"
        assert G.variant_map(grid([35.0] * 20 + [-5.0] * 20, [249] * 40))["result"] == "fail"
        assert by(G.variant_rows({"root": "NQ", "net": np.array([[35.0 * 250]]), "n": np.array([[250.0]]), "sides": "long", "long": 1.0, "short": 0.0,
                                  "n_long": 250, "n_short": 0}, []))["P3.2"]["passed"] is True
    teardown_function()
    assert G.variant_map(t)["result"] == "fail"


def test_variant_rows_p3_7_the_box_must_make_money_without_its_best_5_percent_of_trades():
    """Owner-approved 2026-10-09: two of the four ideas that failed the unseen days (both VWAP pullbacks) earned over 100 % of their profit from their
    best 5 % of trades. The box's own trades (`trade_net`, 1 contract after costs) without the best 5 % must still be above $0; no list of trades = the row does not apply."""
    one = sided(boxes(1, 1, 80.0, 200))
    rows = {r["line"]: r for r in G.variant_rows({**one, "trade_net": np.array([1000.0] * 10 + [-10.0] * 190)}, [])}      # 10 big wins, 190 small losses: lives on the best 5 %
    assert rows["P3.7"]["passed"] is False and rows["P3.7"]["number"] == -1900.0 and rows["P3.7"]["need"] == 0
    assert rows["P3.7"]["text"].startswith("P3.7 FAIL without its best 5 % of trades (10 of 200)")
    spread = np.array([100.0] * 120 + [-20.0] * 80)                                                                           # an even spread: still positive without the best 10
    rows = {r["line"]: r for r in G.variant_rows({**one, "trade_net": spread}, [])}
    assert rows["P3.7"]["passed"] is True and rows["P3.7"]["need"] == 0 and rows["P3.7"]["number"] == float(np.sort(spread)[:-10].sum())
    rows = {r["line"]: r for r in G.variant_rows(one, [])}                                                                    # no trade list (a hand-made table)
    assert rows["P3.7"]["passed"] is None and "no list of the box's trades" in rows["P3.7"]["text"]
    with_number = dict(json.loads(FILE.read_text(encoding="utf-8")))
    assert with_number["variant"]["without_best_trades"] == 0.05


def test_variant_rows_p3_8_to_p3_10_the_box_must_be_consistent_month_by_month_and_day_by_day():
    """Owner-approved 2026-10-09. On the build days of the five ideas that were read on the unseen days, the two that held (months won 76 % and 73 %,
    best month 8 % of the profit, longest losing-day streak 8 and 6) were separated from the three that lost (55-65 %, 12-15 %, 10-14): the thresholds
    were chosen after seeing that outcome, so they are a hypothesis (pipeline.json variant.months_won / best_month_share / losing_day_streak)."""
    import datetime as dt
    day = lambda y, m, d: dt.date(y, m, d).toordinal()                       # noqa: E731
    one = sided(boxes(1, 1, 80.0, 200))
    dates, nets = [], []                                                      # 10 months of 20 trading days, one trade a day; months 3, 6 and 9 lose $50 a day, the others win $100
    for mth in range(10):
        for dd in range(20):
            dates.append(day(2024, 1 + mth, 1 + dd)); nets.append(100.0 if mth not in (2, 5, 8) else -50.0)
    box = {**one, "trade_date": np.array(dates, np.int64), "trade_net": np.array(nets)}
    got = G.variant_rows(box, [])
    rows = {r["line"]: r for r in got}
    assert [r["line"] for r in got][-3:] == ["P3.8", "P3.9", "P3.10"]
    assert (rows["P3.8"]["passed"], rows["P3.8"]["number"], rows["P3.8"]["need"]) == (True, 0.7, 0.7)                       # exactly 70 % of the months won: enough
    assert rows["P3.8"]["text"] == "P3.8 PASS 7 of 10 months won, 70 % (need 70 % or more)"
    assert rows["P3.9"]["passed"] is False and abs(rows["P3.9"]["number"] - 1 / 7) < 1e-9 and rows["P3.9"]["need"] == 0.1  # the best month is 1/7 of the winning months' profit
    assert rows["P3.9"]["text"].startswith("P3.9 FAIL best month 2024-01 is 14.29 % of the profit of the months won (need 10 % or less)")
    assert (rows["P3.10"]["passed"], rows["P3.10"]["number"], rows["P3.10"]["need"]) == (False, 20, 8)                       # a whole losing month in a row: 20 losing days
    assert rows["P3.10"]["text"] == "P3.10 FAIL longest run of losing days: 20 (need 8 or fewer)"
    few = {**box, "trade_net": np.array([-50.0 if (i // 20) in (1, 2, 4, 5, 8) else 100.0 for i in range(200)])}            # 5 losing months of 10
    assert {r["line"]: r for r in G.variant_rows(few, [])}["P3.8"]["passed"] is False
    flat = {**one, "trade_date": np.array([day(2024, 1 + i % 10, 1 + i // 10) for i in range(200)], np.int64), "trade_net": np.full(200, 10.0)}
    r = {x["line"]: x for x in G.variant_rows(flat, [])}                                                                    # 10 equal months: the best is exactly 10 %: enough
    assert r["P3.8"]["passed"] is True and r["P3.9"]["passed"] is True and r["P3.10"]["passed"] is True and r["P3.10"]["number"] == 0
    none = {x["line"]: x for x in G.variant_rows(one, [])}                                                                  # no list of trades: the rows do not apply
    assert all(none[k]["passed"] is None for k in ("P3.8", "P3.9", "P3.10")) and "no list of the box's trades" in none["P3.8"]["text"]
    streak = np.array([-1.0 if 5 <= i % 30 < 15 else 10.0 for i in range(60)])                                             # 10 losing days in a row each 30
    sbox = {**one, "trade_date": np.arange(day(2024, 1, 1), day(2024, 1, 1) + 60, dtype=np.int64), "trade_net": streak}
    r = {x["line"]: x for x in G.variant_rows(sbox, [])}
    assert r["P3.10"]["passed"] is False and r["P3.10"]["number"] == 10
    v = dict(json.loads(FILE.read_text(encoding="utf-8")))["variant"]
    assert (v["months_won"], v["best_month_share"], v["losing_day_streak"]) == (0.7, 0.1, 8)
