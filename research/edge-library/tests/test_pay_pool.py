"""LOCK of the payout pipeline's pool and slots, and of its rotation rule (blueprint/pay_pool.py, blueprint/pay_rotate.py).
HAND-MADE TRADES ONLY (tests/blueprint_synth.py): no tape is read, no engine run is made.

1. A trade counts for a slot only when it is entered AND closed inside it; a box belongs to the slot most of its trades are inside.
2. A day of a box at one micro: its P&L, its worst open loss, the highest point of its closed trades, its trade count.
3. A box's target says what kind it is; no target is a kind of its own.
4. IN FORM is read from the days before, never from the day itself; the first choice trades when it is in form, else the first reserve
   that is, else nobody.
5. The evening's read is saved; a notice is written only when what trades changes.

  pytest tests/test_pay_pool.py -q
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pytest

W = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(W), str(Path(__file__).resolve().parent)]
import blueprint_synth as SY  # noqa: E402
import library as LB  # noqa: E402
from blueprint import pay_pool as PP  # noqa: E402
from blueprint import pay_rotate as RO  # noqa: E402
from blueprint import pipe_store as PS  # noqa: E402

CAL = SY.weekdays("2024-01-01", "2024-03-29")
DAYS = np.array([dt.date.fromisoformat(d).toordinal() for d in CAL])


def packed(rows: list) -> dict:
    return LB.pack(sorted(rows, key=lambda t: (t["exit_ms"], t["entry_ms"])))


# ================================================================ 1. the slots

def test_a_trade_counts_for_a_slot_only_when_it_is_entered_and_closed_inside_it():
    x = packed([SY.trade(CAL[0], 10, at="09:45", mins=30),          # day: inside
                SY.trade(CAL[1], 10, at="15:50", mins=10),          # day: closed on the slot's last second, inside
                SY.trade(CAL[2], 10, at="15:50", mins=30),          # entered in the day slot, closed after it: out
                SY.trade(CAL[3], 10, at="08:30", mins=20),          # the night slot
                SY.trade(CAL[4], 10, at="09:26", mins=2),           # between two slots: out
                SY.trade(CAL[5], 10, at="20:30", mins=60)])         # the evening slot
    slot, keep, share = PP.fits(x)
    assert slot == "day" and keep.tolist() == [True, True, False, False, False, False] and share == pytest.approx(2 / 6)
    assert PP.fits(x, "night")[1].tolist() == [False, False, False, True, False, False]
    assert PP.fits(x, "evening")[1].tolist() == [False, False, False, False, False, True]
    assert PP.fits(packed([SY.trade(CAL[0], 10, at="16:30", mins=5)]))[0] is None


# ================================================================ 2. a day at one micro

def test_a_day_at_one_micro_its_money_its_worst_open_loss_and_its_high():
    x = packed([SY.trade(CAL[0], 20.0, 5.0, at="09:45", mins=10), SY.trade(CAL[0], -50.0, 60.0, at="10:30", mins=10), SY.trade(CAL[0], 10.0, 2.0, at="11:30", mins=5),
                SY.trade(CAL[2], -30.0, 40.0, at="09:45", mins=10)])
    d = PP.daily(x, np.ones(4, bool), DAYS)
    assert d["net"][:3].tolist() == pytest.approx([-20.0, 0.0, -30.0]) and d["n"][:3].tolist() == [3, 0, 1]
    assert d["up"][0] == pytest.approx(20.0) and d["up"][2] == 0.0                   # the day was $20 up after its first trade; a losing day was never up
    cost = LB.MICRO_RT_USD
    assert d["open"][0] == pytest.approx(60.0 + cost - 20.0) and d["open"][2] == pytest.approx(40.0 + cost)       # $20 in hand when the second trade was $60 under
    kept = PP.daily(x, np.array([True, False, True, True]), DAYS)
    assert kept["net"][0] == pytest.approx(30.0) and kept["n"][0] == 2


# ================================================================ 3. a box's target

def test_a_boxs_target_says_what_kind_it_is():
    kind = lambda r: PP.geometry({"exit": {"stop_mode": "pts", "stop_val": 30, "tgt_r": r}})["kind"]  # noqa: E731
    assert [kind(r) for r in (0.0, 0.5, 0.99, 1.0, 1.5, 2.0, 3.0)] == ["none", "tight", "tight", "even", "even", "wide", "wide"]
    assert PP.geometry({"exit": {"stop_mode": "pts", "stop_val": 30, "tgt_r": 0.5}}) == {"stop": "30 pts", "target_r": 0.5, "kind": "tight"}


# ================================================================ 4. in form

def naive(net, lookback, within):
    eq, out = np.cumsum(net), []
    for t in range(len(net)):
        if t < within:
            out.append(True)
            continue
        out.append(any(eq[j] >= eq[max(0, j - lookback + 1):j + 1].max() for j in range(t - within, t)))
    return np.array(out)


def test_in_form_is_read_from_the_days_before_never_from_the_day_itself():
    rng = np.random.default_rng(4)
    for lookback, within in ((3, 1), (5, 2), (20, 5), (60, 20)):
        net = rng.normal(0, 1, 200)
        got = RO.form(net, lookback, within)
        assert (got == naive(net, lookback, within)).all()
        other = net.copy()
        other[150:] = -50.0                                                 # what happens from day 150 on ...
        assert (RO.form(other, lookback, within)[:151] == got[:151]).all()   # ... changes nothing up to and including day 150's flag
    falling = RO.form(-np.ones(30), 5, 3)
    assert falling[:3].all() and not falling[4:].any()                      # always lower: after the first days it is never at a high


def test_the_first_in_form_trades_and_nobody_when_none_is():
    a, b = np.array([True, False, False, True]), np.array([True, True, False, False])
    assert RO.pick([a, b]).tolist() == [0, 1, -1, 0]
    day = lambda v: {k: np.full(4, v) for k in ("net", "open", "up", "n")}  # noqa: E731
    assert RO.rotated([day(1.0), day(10.0)], [a, b])["net"].tolist() == [1.0, 10.0, 0.0, 1.0]


# ================================================================ 5. the evening

def test_the_evening_is_saved_and_a_notice_is_written_only_when_what_trades_changes(tmp_path, monkeypatch):
    monkeypatch.setenv(PS.ENV, str(tmp_path / "env_root"))
    root = tmp_path / "pipeline"
    (root / "payout").mkdir(parents=True)
    the_set = {"built_utc": "t", "sets": {"lucid-pro": {"account_name": "LucidPro", "rotation": {"lookback": 3, "within": 1}, "slots": {
        "evening": None, "day": {"name": "first", "bench": [{"name": "reserve"}]}}}}}
    (root / "payout" / "set.json").write_text(json.dumps(the_set))
    up, down = np.ones(10), -np.ones(10)
    book = {"first": up, "reserve": up}
    series = lambda name: (book[name], "2024-03-29")  # noqa: E731
    one = RO.evening(root, series)
    assert one["kind"] == "set" and one["text"] == "Tonight's set (results through 2024-03-29). LucidPro: day first"     # the empty evening slot is no news
    assert RO.evening(root, series) is None                                  # the same set: no notice
    book["first"] = down
    two = RO.evening(root, series)
    assert two["kind"] == "switch" and two["text"].endswith("LucidPro: day reserve") and two["slots"]["lucid-pro"]["day"]["in_form"] == {"first": False, "reserve": True}
    book["reserve"] = down
    assert RO.evening(root, series)["text"].endswith("LucidPro: day stand down")
    assert [n["kind"] for n in RO.notices(root)] == ["set", "switch", "switch"]
    assert json.loads((root / "payout" / "tonight.json").read_text())["slots"]["lucid-pro"]["day"]["trades"] is None
