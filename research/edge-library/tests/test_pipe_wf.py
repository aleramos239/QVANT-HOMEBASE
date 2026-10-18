"""LOCK of STAGE 6 AS A 3:1 WALK-FORWARD (blueprint/pipe_wf.py; the owner, 2026-10-18).

1. months: the calendar's months, a first month that starts after its 7th day left out
2. holds: a box on a window needs an average trade above $0, enough trades and row P3.15
3. walk: BLOCKS (the owner, 2026-10-18): pick on 3 months, trade the 4th, the next block starts after it -- the MIDDLE box by average
   trade of those that hold, never the best; no box holds = the month stands aside; `next` = the pick on the last 3 whole months
4. stitch: each month's pick, in that month only (no look-ahead: a month's trades never come from a box picked on it)
5. against_random and rows: the stitched net against its random draws; P6.1-P6.4
No store, no engine. Under a second.

  pytest tests/test_pipe_wf.py -q
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import judge as J  # noqa: E402
from blueprint import pipe_wf as WF  # noqa: E402

MS = ["2022-01", "2022-02", "2022-03", "2022-04", "2022-05"]
MS9 = [f"2022-{m:02d}" for m in range(1, 10)]


def box(per_month: dict) -> dict:
    """One box: per month a list of trade nets, each trade on the 10th of its month (one day: enough for the tests)."""
    d, n = [], []
    for m, nets in per_month.items():
        y, mo = map(int, m.split("-"))
        d += [dt.date(y, mo, 10).toordinal()] * len(nets)
        n += list(nets)
    x = {"date": np.array(d, np.int64), "net": np.array(n, np.float64), "entry_ms": np.zeros(len(n)), "dur_s": np.full(len(n), 60), "mae": np.zeros(len(n))}
    x["month"] = WF._month(x["date"])
    return x


def win(k: int, w: float = 100.0, lo: float = -50.0) -> list:
    """k trades a month: 60 % winners of $w, 40 % losers of $lo (R:R 2, breakeven 33 %: holds P3.15)."""
    return [w] * (k * 6 // 10) + [lo] * (k - k * 6 // 10)


ROWS = [{"id": f"c{i}", "net": 0.0, "trades": 0, "vi": 0, "xi": i} for i in range(5)]


def test_months_drop_a_first_month_that_starts_late():
    assert WF.months(["2021-09-22", "2021-09-23", "2021-10-01", "2021-11-02"]) == ["2021-10", "2021-11"]
    assert WF.months(["2021-09-01", "2021-10-01"]) == ["2021-09", "2021-10"]
    assert WF.months([]) == []


def test_a_box_holds_on_a_window_with_money_trades_and_p315():
    assert WF.holds(win(20), 15) is True
    assert WF.holds(win(10), 15) is False                                     # too few trades
    assert WF.holds([10.0] * 20 + [-30.0] * 10, 15) is False                  # loses money
    assert WF.holds([10.0] * 52 + [-10.0] * 48, 15) is False                  # profitable, under breakeven + 3 points


def test_each_month_is_traded_by_the_middle_pick_of_the_three_months_before_it():
    a = box({m: win(20, 200.0) for m in MS})                                  # the best box
    b = box({m: win(20, 100.0) for m in MS})                                  # the middle one
    c = box({m: win(20, 50.0, -20.0) for m in MS})
    got = WF.walk({"c0": a, "c1": b, "c2": c}, ROWS, MS, 3, 15, "2022-06-02")
    assert [(p["month"], p["window"], p["cell"]) for p in got["picks"]] == [("2022-04", MS[0:3], "c1")]          # one block in 5 months
    assert got["next"] == {"month": "2022-06", "window": MS[2:5], "cell": "c1", "stale": False}


def test_blocks_do_not_overlap_three_in_then_one_out_on_repeat():
    a = box({m: win(20) for m in MS9})
    got = WF.walk({"c0": a}, ROWS, MS9, 3, 15, "2022-10-02", 4)
    assert [(p["window"], p["month"]) for p in got["picks"]] == [(MS9[0:3], "2022-04"), (MS9[4:7], "2022-08")]      # Jan-Mar -> Apr, May-Jul -> Aug
    used = [m for p in got["picks"] for m in [*p["window"], p["month"]]]
    assert len(used) == len(set(used))                                        # no month is both in- and out-of-sample


def test_a_month_with_no_box_that_holds_stands_aside_and_a_pick_reads_only_its_window():
    a = box({"2022-01": win(20), "2022-02": win(20), "2022-03": win(20), "2022-04": [-500.0] * 20, "2022-05": win(20)})
    got = WF.walk({"c0": a}, ROWS, MS, 3, 15, "2022-05-20")
    assert [p["cell"] for p in got["picks"]] == ["c0"]                        # the block Jan-Mar -> Apr
    assert WF.walk({"c0": a}, ROWS, MS, 3, 15, "2022-05-20", 1)["picks"][1]["cell"] is None      # a window that loses (Feb-Apr) picks nothing: it stands aside
    assert got["next"] == {"month": "2022-05", "window": MS[1:4], "cell": None, "stale": False}     # today in May: the window is Feb..Apr
    assert WF.walk({"c0": a}, ROWS, MS, 3, 15, "2022-09-01")["next"]["month"] == "2022-06" and WF.walk({"c0": a}, ROWS, MS, 3, 15, "2022-09-01")["next"]["stale"] is True      # data ends in May: the pick is for June, said stale
    x = WF.stitch({"c0": a}, got["picks"])
    assert float(x["net"].sum()) == -10000.0 and len(x["net"]) == 20         # April's trades only: the month it was picked FOR, never May's


def test_stitched_record_against_random_draws_and_the_four_rows():
    a = box({m: win(20) for m in MS})
    picks = [{"month": "2022-04", "cell": "c0_x1"}, {"month": "2022-05", "cell": None}]
    boxes = {"c0_x1": a}
    d = np.array(sorted(a["date"]), np.int64)
    pool_ = (d, np.full(len(d), -5.0), np.arange(len(d)), np.r_[0.0, np.cumsum(np.full(len(d), -5.0))])
    beat = WF.against_random(boxes, picks, lambda xid, m: pool_, J.block_seeds(7), 400, float(a["net"][a["month"] == "2022-04"].sum()), real=10)
    assert beat["p_beat"] == 1.0 and beat["replicates"] == 400
    x = WF.stitch(boxes, picks)
    r = {row["line"]: row for row in WF.rows(x, beat, 200)}
    assert (r["P6.1"]["passed"], r["P6.2"]["passed"], r["P6.3"]["passed"], r["P6.4"]["passed"]) == (True, True, True, False)      # 20 trades of 200
    assert WF.rows(WF.stitch(boxes, [{"month": "2022-04", "cell": None}]), None, 200)[1]["passed"] is None      # nothing traded: no random tables
