"""Daily rules (risk.py): day_take / day_lock / target_take, sizing tiers, the eval standing.

The numbers are the desk review's (2026-10-01): 4 NQ = $80 a point, $16 round-trip fee."""
from __future__ import annotations

import math

import pytest

from homebase.backtest.propsim import load_rules
from homebase.risk import (DayBook, DayRules, ceil_to_tick, merge_rules, size_for_profit, standing,
                           take_level, take_points)

TICK, PV, FEE = 0.25, 20.0, 4.0


# ---- take_points: the take price as points from the FILL
@pytest.mark.parametrize("net, qty, pts", [
    (1500, 4, 19.0),        # 1,516 / 80 = 18.95 -> the tick above
    (1000, 4, 12.75),       # 12.7
    (3000, 4, 37.75),       # 37.7
    (600, 4, 7.75),         # 7.7
    (600, 3, 10.25),        # 10.2
    (600, 2, 15.25),        # 15.2
])
def test_take_points_match_the_review(net, qty, pts):
    assert take_points(net, qty, PV, FEE, TICK) == pts


def test_a_take_never_rounds_below_its_net():
    for net in (600, 1000, 1500, 3000, 777, 1234):
        for qty in (1, 2, 3, 4):
            pts = take_points(net, qty, PV, FEE, TICK)
            assert pts * PV * qty - FEE * qty >= net - 1e-9
            assert (pts - TICK) * PV * qty - FEE * qty < net        # and not a tick more than needed
            assert math.isclose(pts / TICK, round(pts / TICK))      # on the tick grid


def test_take_points_refuse_nonsense():
    for args in ((0, 4, PV, FEE, TICK), (600, 0, PV, FEE, TICK), (600, 4, 0, FEE, TICK)):
        with pytest.raises(ValueError):
            take_points(*args)


def test_ceil_to_tick_is_float_safe():
    assert ceil_to_tick(18.95, 0.25) == 19.0
    assert ceil_to_tick(19.0, 0.25) == 19.0          # exactly on the grid stays
    assert ceil_to_tick(0.1 + 0.2, 0.1) == 0.3       # 0.30000000000000004 must not jump a tick


# ---- target_take: copy of evalcore.take_level for one account
FLEX = load_rules("lucid-flex-50k@2026-09-27")
PRO = load_rules("lucid-pro-50k-no-dll@2026-09-27b")


def lvl(r, profit, largest, days):
    return take_level(r["eval_target"], profit, largest, days, min_days=r["eval_min_days"],
                      consistency=r.get("consistency"))


def test_pro_has_no_consistency_and_no_minimum_days():
    assert lvl(PRO, 0, 0, 0) == 3000                     # day 1 can pass: the whole target
    assert lvl(PRO, 1200, 800, 3) == 1800                # what is left
    assert lvl(PRO, 3000, 900, 5) is None                # already past the target: nothing to take


def test_flex_cannot_pass_on_day_one():
    assert lvl(FLEX, 0, 0, 0) is None                    # 2-day minimum: today cannot be the pass


def test_flex_consistency_raises_the_level():
    # 1,500 earned in ONE day: passing needs L with max(1500, L) <= 0.5 * (1500 + L) -> L = 1,500
    assert lvl(FLEX, 1500, 1500, 1) == 1500
    # 2,000 over two days (largest 1,200): the target needs 1,000; consistency needs L >= 2*1200 - 2000 = 400
    assert lvl(FLEX, 2000, 1200, 2) == 1000
    # largest 1,800 of 2,000: consistency needs L >= 3,600 - 2,000 = 1,600 > the target's 1,000
    assert lvl(FLEX, 2000, 1800, 2) == 1600


def test_flex_has_no_level_when_consistency_cannot_hold():
    # largest day 2,900 of 3,000 profit: L must be >= 2*2900 - 3000 = 2,800, but L <= c*profit/(1-c) = 3,000 holds...
    assert lvl(FLEX, 3000, 2900, 4) == 2800
    # profit 100 with largest 100: L >= 100 -> but the cap L <= 0.5*100/0.5 = 100 -> ok, equals the target? target needs 2,900
    assert lvl(FLEX, 100, 100, 1) is None                # the target (2,900) breaks the cap (100): no level


# ---- sizing
TIERS = [[0, 2], [1000, 3], [2000, 4]]


@pytest.mark.parametrize("profit, qty", [(-500, 2), (0, 2), (999.99, 2), (1000, 3), (1999, 3), (2000, 4), (5000, 4)])
def test_pm_sizes_by_profit(profit, qty):
    assert size_for_profit(TIERS, profit, 4) == qty


def test_the_book_caps_the_tier_and_no_tiers_means_the_book():
    assert size_for_profit(TIERS, 5000, 3) == 3
    assert size_for_profit([], 5000, 4) == 4
    assert size_for_profit(TIERS, float("-inf"), 4) == 2          # unknown standing: the smallest


# ---- the eval standing from the daily balance record
def test_standing_counts_winning_days_from_balance_changes():
    bal = {"2026-09-28": 50000, "2026-09-29": 50800, "2026-09-30": 50600, "2026-10-01": 52000}
    assert standing(bal, "2026-10-01") == (800.0, 2)           # 9-29 +800, 9-30 -200; today is not counted
    assert standing(bal, "2026-10-01", seed_largest=1000, seed_days=3) == (1000.0, 5)
    assert standing({}, "2026-10-01") == (0.0, 0)


# ---- the account's day
def test_day_take_stops_the_day_once_closed_pnl_reaches_it():
    rules, b = DayRules(day_take=1500), DayBook("a", "2026-10-02")
    assert b.record_close(900, rules) is None and not b.locked
    assert b.record_close(700, rules) == "day_take" and b.locked == "day_take"


def test_day_lock_is_closed_pnl_only():
    rules, b = DayRules(day_lock=750), DayBook("a", "2026-10-02")
    assert b.take_hit(10_000, rules) is False                       # no take configured: open P&L is ignored
    assert b.record_close(749, rules) is None
    assert b.record_close(1, rules) == "day_lock"


def test_day_take_wins_over_day_lock_when_both_hold():
    b = DayBook("a", "2026-10-02")
    assert b.record_close(1600, DayRules(day_take=1500, day_lock=750)) == "day_take"


def test_take_hit_is_closed_plus_open_net():
    rules, b = DayRules(day_take=1500), DayBook("a", "2026-10-02", closed_net=400)
    assert not b.take_hit(1099.99, rules)
    assert b.take_hit(1100, rules)
    b.locked = "day_take"
    assert not b.take_hit(5000, rules)                              # already taken


def test_target_take_uses_the_lower_of_the_two_levels():
    b = DayBook("a", "2026-10-02", target_level=1000)
    assert b.take_net(DayRules(day_take=1500, target_take=True)) == 1000
    assert b.take_net(DayRules(day_take=800, target_take=True)) == 800
    assert b.take_net(DayRules(day_take=1500, target_take=False)) == 1500     # a funded account ignores the level
    assert b.take_net(DayRules(target_take=True)) == 1000
    assert DayBook("a", "d").take_net(DayRules(target_take=True)) is None     # no level today: no take from it


def test_a_target_take_close_locks_the_account_at_the_level():
    b = DayBook("a", "2026-10-02", target_level=1000)
    assert b.record_close(1000.5, DayRules(target_take=True)) == "day_take"


def test_merge_takes_the_tightest_rule():
    m = merge_rules([DayRules(1500, 750, False), DayRules(600, 0, True), DayRules(0, 300, False)])
    assert m == DayRules(day_take=600, day_lock=300, target_take=True)
    assert merge_rules([]) == DayRules() and not DayRules().any


def test_the_book_round_trips_through_json():
    b = DayBook("a", "2026-10-02", closed_net=12.5, locked="day_lock", prepared=True, target_level=900.0)
    assert DayBook.from_dict(b.to_dict()) == b
    assert DayBook.from_dict({**b.to_dict(), "future_field": 1}) == b       # a newer file never breaks an older desk
