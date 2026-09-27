"""Monte Carlo over a trade P&L list: determinism, known small cases, ruin, prop-pass reuse,
and the 10,000-path / 1,000-trade performance budget."""
from __future__ import annotations

import random
import time

import pytest

from homebase.backtest.stats import montecarlo as mc

PNLS = [50.0, -30.0, 20.0, -10.0, 80.0]

# A trivial eval any single winning trade clears immediately.
RULES_PASS = dict(eval_target=100, eval_min_days=1, consistency=1.0,
                   trailing_mll=1000, lock_at=999_999, lock_floor=0)
# A trailing max loss no path can survive its first trade.
RULES_BUST = dict(eval_target=100_000, eval_min_days=1, consistency=1.0,
                   trailing_mll=1000, lock_at=999_999, lock_floor=0)


def test_all_positive_trades_never_draw_down():
    r = mc.run([100.0, 200.0, 300.0], paths=500, seed=1)
    assert all(v == 0.0 for v in r["drawdown"].values())
    assert r["p_ruin"] == 0.0     # defaults: never dips into the red


def test_shuffle_is_the_default_and_keeps_the_sum():
    r = mc.run(PNLS, paths=500, seed=2)
    assert r["mode"] == "shuffle"
    assert all(v == pytest.approx(sum(PNLS)) for v in r["final_net"].values())


def test_bootstrap_final_net_spreads_over_a_sane_range():
    r = mc.run(PNLS, paths=3000, seed=3, mode="bootstrap")
    lo, hi = r["final_net"]["p5"], r["final_net"]["p95"]
    assert lo <= r["final_net"]["p50"] <= hi
    n = len(PNLS)
    assert min(PNLS) * n <= lo and hi <= max(PNLS) * n


def test_a_seed_is_deterministic():
    a = mc.run(PNLS, paths=1000, seed=42)
    b = mc.run(PNLS, paths=1000, seed=42)
    c = mc.run(PNLS, paths=1000, seed=43)
    assert a == b
    assert a != c


def test_ruin_probability_matches_the_closed_form_for_a_symmetric_case():
    """[-1000, 500, 500] from a $1,000 balance: shuffled, -1000 lands first in exactly 1 of 3
    equally-likely slots (the two 500s are interchangeable) -- and only that slot ever touches
    the $0 floor. P(ruin) -> 1/3."""
    r = mc.run([-1000.0, 500.0, 500.0], paths=6000, seed=7, starting_balance=1000.0, ruin_threshold=0.0)
    assert r["p_ruin"] == pytest.approx(1 / 3, abs=0.03)


def test_ruin_is_never_trivially_certain_from_the_pre_trade_baseline():
    """The pre-trade starting point (cumulative P&L 0.0) must not itself count as a ruin just
    because starting_balance and ruin_threshold both default to 0 -- only the path AFTER a
    trade can breach the floor."""
    r = mc.run([10.0, 20.0, 30.0], paths=200, seed=1)
    assert r["p_ruin"] == 0.0
    r2 = mc.run([-50.0, 100.0], paths=2000, seed=1)
    assert 0.0 < r2["p_ruin"] < 1.0


def test_prop_pass_reuses_the_propsim_day_race():
    always_pass = mc.run([100.0, 100.0], paths=300, seed=1, rules=RULES_PASS)
    assert always_pass["p_prop_pass"] == 1.0
    always_bust = mc.run([-2000.0, 100.0], paths=300, seed=1, rules=RULES_BUST)
    assert always_bust["p_prop_pass"] == 0.0
    no_rules = mc.run(PNLS, paths=100, seed=1)
    assert no_rules["p_prop_pass"] is None


def test_the_actual_recorded_order_ranks_inside_its_own_distribution():
    r = mc.run(PNLS, paths=1000, seed=5)
    assert r["actual"]["max_dd"] <= 0.0
    assert 0.0 <= r["actual"]["percentile"] <= 100.0


def test_histogram_never_divides_by_zero_on_a_degenerate_sample():
    r = mc.run([100.0], paths=10, seed=1)
    assert r["histogram"] == {"edges": [0.0, 0.0], "counts": [10]}
    r2 = mc.run([100.0, 200.0], paths=50, seed=1)
    assert sum(r2["histogram"]["counts"]) == 50


def test_bad_inputs_raise():
    with pytest.raises(ValueError, match="no trades"):
        mc.run([])
    with pytest.raises(ValueError, match="paths"):
        mc.run(PNLS, paths=0)
    with pytest.raises(ValueError, match="paths"):
        mc.run(PNLS, paths=10_001)
    with pytest.raises(ValueError, match="mode"):
        mc.run(PNLS, mode="bogus")


def test_ten_thousand_paths_on_a_thousand_trades_finishes_under_two_seconds():
    rng = random.Random(0)
    big = [rng.uniform(-100.0, 150.0) for _ in range(1000)]
    t0 = time.perf_counter()
    mc.run(big, paths=10_000, seed=1)
    assert time.perf_counter() - t0 < 2.0
