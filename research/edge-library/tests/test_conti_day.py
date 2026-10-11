"""LOCK of `engine/families/conti.py`: vwap_trend_day, the "drift VWAP pullback" the way the video says it (owner answers 2026-10-10).

It is round1.VwapTrendPull (N1) with three differences, and the tests say exactly which:
  1. ONE instance for the whole window 10:30 -> 15:58, so its cap of 4 trades and its loss stop count over the DAY;
  2. the stop after `max_loss` losing trades IN A ROW (N1: any two);
  3. the VWAP slope read `slope_min` (15) MINUTES back on every bar size (N1: 3 bars = 45 minutes on 15-minute bars).
The run against N1 on build days: on a day where N1's three passes never overlap and no signal falls on a pass boundary
(10:55 / 11:00 / 13:25 / 13:30, where N1 has no entry because its passes end), the day instance's trades ARE N1's.

  pytest tests/test_conti_day.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import l2sim as S  # noqa: E402
import run_menus as RM  # noqa: E402
from blueprint import taught as TT  # noqa: E402

RM.registry()
from families import conti  # noqa: E402
from families.round1 import VwapTrendPull  # noqa: E402

SHEETS = W / "taught"
EQUAL_DAYS = ["2023-03-07", "2023-03-10", "2023-03-13", "2023-03-16", "2023-03-24", "2024-06-04", "2024-06-12"]


def test_the_family_is_registered_and_the_registry_is_clean():
    import families
    assert not families.ERRORS, families.ERRORS
    assert families.REGISTRY[conti.NAME][0] is conti.VwapTrendDay
    assert families.MODULE_OF[conti.NAME] == "conti"


def test_the_slope_is_fifteen_minutes_on_every_bar_size():
    for tf, bars in (("1", 15), ("5", 3), ("15", 1)):
        f = conti.VwapTrendDay({"tf": tf, "sess": "nyam", "hold_to": "day"})
        f.tf = int(tf)                                       # the engine sets it when the day starts
        f.fam_day(None)
        assert f.SLOPE == bars
    n1 = VwapTrendPull({"tf": "15", "sess": "nyam", "hold_to": "day"})
    assert n1.SLOPE == 3                                     # N1 itself is unchanged: 45 minutes on 15-minute bars


def test_one_instance_stands_for_the_three_passes():
    assert conti.VwapTrendDay({"tf": "5", "sess": "nyam", "hold_to": "day"}).sessions() == ["t"]
    assert conti.VwapTrendDay({"tf": "5", "sess": "mid", "hold_to": "day"}).sessions() == []
    assert conti.VwapTrendDay({"tf": "5", "sess": "pm", "hold_to": "day"}).sessions() == []
    assert conti.VwapTrendDay.ONE_INSTANCE_PASSES == ("nyam", "mid", "pm")


def test_the_loss_stop_counts_losses_in_a_row():
    L, G = {"net": -5.0}, {"net": 5.0}
    assert conti._in_a_row([]) == 0
    assert conti._in_a_row([L, G]) == 0
    assert conti._in_a_row([L, G, L]) == 1
    assert conti._in_a_row([G, L, L]) == 2
    assert conti._in_a_row([L, L, G, L]) == 1


def test_the_two_day_sheets_on_file_are_whole():
    for side in ("long", "short"):
        c = TT.check(SHEETS / f"conti_day_{side}.json")
        assert c["ok"], c
        p = c["plan"]
        assert p["family"] == "vwap_trend_day" and p["bars"] == ["1", "5", "15"] and p["one_instance"] == ["nyam", "mid", "pm"]
        assert p["settings"] == {"x": 0.1, "max_loss": 2, "slope_min": 15}
        assert p["exits"]["max_trades"] == 4 and p["exits"]["stop_pts"] == 80
        assert p["exits"]["target_pts"] == (40 if side == "long" else 50)
        assert p["window"]["text"] == "10:30-15:30"


def test_the_day_instance_is_n1_where_n1_has_no_overlap_and_no_boundary():
    ex = {"stop_mode": "pts", "stop_val": 80.0, "tgt_r": 0.5, "exit_bars": 0, "max_tr": 20, "max_loss": 20}
    n1 = [(VwapTrendPull, {"tf": "5", "sess": s, "hold_to": "day", **ex}) for s in ("nyam", "mid", "pm")]
    day = [(conti.VwapTrendDay, {"tf": "5", "sess": "nyam", "hold_to": "day", **ex})]
    r = S.run_many(n1 + day, days=EQUAL_DAYS, root="NQ", workers=2, features=None)
    a = RM.merge(r[:3])["trades"]
    b = r[3]["trades"]
    key = lambda t: (t["date"], t["entry_ms"], t["side"], t["exit_ms"], t["exit_reason"])      # noqa: E731
    assert a and sorted(map(key, a)) == sorted(map(key, b))


def test_the_both_sides_instance_takes_the_videos_target_by_side_and_one_day_cap():
    from families import conti_both
    ex = {"stop_mode": "pts", "stop_val": 80.0, "tgt_r": 0.5, "exit_bars": 0, "max_tr": 4, "max_loss": 2, "dir": "both"}
    r = S.run_many([(conti_both.VwapTrendBoth, {"tf": "5", "sess": "nyam", "hold_to": "day", **ex})], days=EQUAL_DAYS, root="NQ", workers=2, features=None)
    t = r[0]["trades"]
    assert {x["side"] for x in t} == {"long", "short"}
    for x in t:
        want = 40.0 if x["side"] == "long" else 50.0
        assert abs(abs(x["tp"] - x["entry_price"]) - want) < 1e-6, x
        assert abs(abs(x["sl"] - x["entry_price"]) - 80.0) < 1e-6, x
    per_day: dict = {}
    for x in t:
        per_day[x["date"]] = per_day.get(x["date"], 0) + 1
    assert max(per_day.values()) <= 4
    longs = S.run_many([(conti_both.VwapTrendBoth, {"tf": "5", "sess": "nyam", "hold_to": "day", **{**ex, "dir": "long"}})], days=EQUAL_DAYS, root="NQ", workers=2, features=None)
    days_only = S.run_many([(conti.VwapTrendDay, {"tf": "5", "sess": "nyam", "hold_to": "day", **{**ex, "dir": "long"}})], days=EQUAL_DAYS, root="NQ", workers=2, features=None)
    key = lambda x: (x["date"], x["entry_ms"], x["side"], x["exit_ms"])      # noqa: E731
    assert sorted(map(key, longs[0]["trades"])) == sorted(map(key, days_only[0]["trades"]))      # the long side is the day instance's own
