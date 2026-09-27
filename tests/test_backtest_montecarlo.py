"""Monte Carlo over a finished run's trades, resampled by DAY (review C2): determinism, known small
cases, the drawdown-floor ruin (I1), the prop race = propsim.engine.run_eval on each resampled day path
(one trade per day == the old trade-level walk; a multi-trade day is LucidFlex's EOD race, not an
intraday one), the day x path work cap (I3), and the timing budget."""
from __future__ import annotations

import datetime as dt
import random
import time

import pytest

from homebase.backtest import propsim
from homebase.backtest.propsim import engine
from homebase.backtest.stats import montecarlo as mc

LUCID = propsim.load_rules(propsim.DEFAULT_RULES)
# A trivial eval any single winning day clears immediately.
RULES_PASS = dict(eval_target=100, eval_min_days=1, consistency=1.0, trailing_mll=1000, lock_at=999_999, lock_floor=0)
# A trailing max loss no path survives.
RULES_BUST = dict(eval_target=100_000, eval_min_days=1, consistency=1.0, trailing_mll=1000, lock_at=999_999, lock_floor=0)


def weekdays(n: int, start=dt.date(2024, 1, 1)) -> list[str]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def daily(nets: list[float]) -> list[dict]:
    """One trade per consecutive weekday (the weekday grid has no empty days)."""
    return [{"date": d, "net": n} for d, n in zip(weekdays(len(nets)), nets)]


def by_day(days: list[list[float]]) -> list[dict]:
    return [{"date": d, "net": n} for d, nets in zip(weekdays(len(days)), days) for n in nets]


PNLS = [50.0, -30.0, 20.0, -10.0, 80.0]
TR = daily(PNLS)


def _old_trade_walk(pnls, *, paths, seed, mode, rules):
    """The pre-fix inline walk (trades as days), kept only as the one-trade-per-day reference."""
    n, rng, work = len(pnls), random.Random(seed), list(pnls)
    dds, finals, streaks, n_pass = [], [], [], 0
    for _ in range(paths):
        work = rng.choices(pnls, k=n) if mode == "bootstrap" else work
        if mode == "shuffle":
            rng.shuffle(work)
        peak = run_eq = worst = 0.0
        cur, mx = 0, 0
        floor, largest, tdays, outcome = -rules["trailing_mll"], 0.0, 0, None
        for p in work:
            run_eq += p
            if run_eq > peak:
                peak = run_eq
                if outcome is None:
                    floor = rules["lock_floor"] if peak >= rules["lock_at"] else peak - rules["trailing_mll"]
            else:
                worst = min(worst, run_eq - peak)
            if p < 0:
                cur += 1
                mx = max(mx, cur)
            else:
                cur = 0
            if outcome is None:
                if p != 0.0:
                    tdays += 1
                largest = max(largest, p)
                if run_eq <= floor:
                    outcome = "bust"
                elif run_eq >= rules["eval_target"] and tdays >= rules["eval_min_days"] and largest <= rules["consistency"] * run_eq:
                    outcome = "pass"
        dds.append(worst)
        finals.append(run_eq)
        streaks.append(mx)
        n_pass += outcome == "pass"
    return dds, finals, streaks, n_pass / paths


def test_all_positive_days_never_draw_down():
    r = mc.run(daily([100.0, 200.0, 300.0]), paths=500, seed=1)
    assert all(v == 0.0 for v in r["drawdown"].values())
    assert r["p_ruin"] == 0.0


def test_shuffle_is_the_default_keeps_the_sum_and_resamples_days():
    r = mc.run(TR, paths=500, seed=2)
    assert r["mode"] == "shuffle" and r["unit"] == "day" and r["n_days"] == 5 and r["n_trades"] == 5
    assert all(v == pytest.approx(sum(PNLS)) for v in r["final_net"].values())


def test_bootstrap_final_net_spreads_over_a_sane_range():
    r = mc.run(TR, paths=3000, seed=3, mode="bootstrap")
    lo, hi = r["final_net"]["p5"], r["final_net"]["p95"]
    assert lo <= r["final_net"]["p50"] <= hi
    assert min(PNLS) * 5 <= lo and hi <= max(PNLS) * 5


def test_a_seed_is_deterministic():
    a, b, c = (mc.run(TR, paths=1000, seed=s) for s in (42, 42, 43))
    assert a == b and a != c
    assert a["seed"] == 42


def test_one_trade_per_day_equals_the_old_trade_level_walk():
    rng = random.Random(9)
    nets = [round(rng.uniform(-900, 1200), 2) or 1.0 for _ in range(60)]
    for mode in ("shuffle", "bootstrap"):
        r = mc.run(daily(nets), paths=400, seed=11, mode=mode, rules=LUCID)
        dds, finals, streaks, p_pass = _old_trade_walk(nets, paths=400, seed=11, mode=mode, rules=LUCID)
        assert r["p_prop_pass"] == p_pass, mode
        assert r["drawdown"] == mc._percentiles(dds)
        assert r["final_net"] == mc._percentiles(finals)
        assert r["losing_streak"] == mc._percentiles([float(s) for s in streaks])


def test_a_multi_trade_day_races_lucidflex_end_of_day_not_intraday():
    """Review C2: a day of [-2,100, +2,200] is +$100 at the close. LucidFlex trails END OF DAY, so it
    never busts; the old trade-level walk busted every path that drew the -2,100 first."""
    tr = by_day([[-2100.0, 2200.0], [1500.0], [1500.0]])
    r = mc.run(tr, paths=300, seed=5, rules=LUCID)
    assert r["p_prop_pass"] == 1.0                       # every day order passes at +$3,100
    # ... and equals run_eval on the very day orders the MC drew
    rng, idx, passes = random.Random(5), [0, 1, 2], 0
    pnls, flags, _ = propsim.weekday_grid(tr)
    for _ in range(300):
        rng.shuffle(idx)
        passes += engine.run_eval([(pnls[i], flags[i]) for i in idx], LUCID)["outcome"] == "pass"
    assert r["p_prop_pass"] == passes / 300
    _, _, _, old = _old_trade_walk([-2100.0, 2200.0, 1500.0, 1500.0], paths=300, seed=5, mode="shuffle", rules=LUCID)
    assert old < 1.0                                    # the bug this replaces


def test_consistency_is_judged_on_the_day_not_the_trade():
    """Two +$1,600 trades are ONE $3,200 day: more than 50% of a $3,400 total, so LucidFlex never passes."""
    r = mc.run(by_day([[1600.0, 1600.0], [100.0], [100.0]]), paths=200, seed=1, rules=LUCID)
    assert r["p_prop_pass"] == 0.0


def test_zero_trade_weekdays_are_days_of_the_race():
    tr = [{"date": "2024-01-01", "net": 100.0}, {"date": "2024-01-05", "net": 100.0}]   # Mon, Fri
    r = mc.run(tr, paths=50, seed=1, rules=RULES_PASS)
    assert r["n_days"] == 5 and r["n_trades"] == 2 and r["p_prop_pass"] == 1.0
    assert mc.run(daily([-2000.0, 100.0]), paths=100, seed=1, rules=RULES_BUST)["p_prop_pass"] == 0.0
    assert mc.run(TR, paths=100, seed=1)["p_prop_pass"] is None


def test_ruin_is_the_drawdown_reaching_the_floor():
    """[-600, -600, +1,500] by day: DD reaches $1,000 only when the two losses are adjacent (2 of 3 orders)."""
    r = mc.run(daily([-600.0, -600.0, 1500.0]), paths=6000, seed=7, floor=1000.0)
    assert r["floor"] == 1000.0 and r["p_ruin"] == pytest.approx(2 / 3, abs=0.03)
    assert mc.run(daily([-600.0, -600.0, 1500.0]), paths=500, seed=7, floor=1200.01)["p_ruin"] == 0.0


def test_the_default_floor_is_the_rules_trailing_max_loss_else_2000():
    assert mc.run(TR, paths=10, seed=1)["floor"] == 2000.0
    assert mc.run(TR, paths=10, seed=1, rules={**LUCID, "trailing_mll": 2500})["floor"] == 2500.0


def test_the_actual_path_says_how_many_resamples_it_is_worse_than():
    """[-300, -300, +700]: DD -600 when the losses are adjacent (2 of 3 orders), -300 otherwise. The
    recorded order (adjacent) is worse than the ~1/3 of paths that split them; ties never count."""
    r = mc.run(daily([-300.0, -300.0, 700.0]), paths=6000, seed=5)
    assert r["actual"]["max_dd"] == -600.0 and r["actual"]["worse_than_pct"] == pytest.approx(100 / 3, abs=2.0)
    best = mc.run(daily([-300.0, 700.0, -300.0]), paths=2000, seed=5)
    assert best["actual"]["max_dd"] == -300.0 and best["actual"]["worse_than_pct"] == 0.0


def test_histogram_never_divides_by_zero_on_a_degenerate_sample():
    r = mc.run(daily([100.0]), paths=10, seed=1)
    assert r["histogram"] == {"edges": [0.0, 0.0], "counts": [10]}
    assert sum(mc.run(daily([100.0, -200.0]), paths=50, seed=1)["histogram"]["counts"]) == 50


def test_bad_inputs_raise():
    with pytest.raises(ValueError, match="no trades"):
        mc.run([])
    for bad in (0, 10_001):
        with pytest.raises(ValueError, match="paths"):
            mc.run(TR, paths=bad)
    with pytest.raises(ValueError, match="mode"):
        mc.run(TR, mode="bogus")
    with pytest.raises(ValueError, match="floor"):
        mc.run(TR, floor=0)


def test_work_is_capped_at_two_million_day_steps_and_the_paths_used_are_reported():
    tr = daily([random.Random(i).uniform(-100, 150) for i in range(1000)])
    r = mc.run(tr, paths=10_000, seed=1)
    assert r["paths"] == 2000 and r["paths_requested"] == 10_000 and r["capped"] is True
    assert r["n_days"] * r["paths"] <= mc.MAX_WORK
    small = mc.run(TR, paths=5000, seed=1)
    assert small["paths"] == 5000 and small["capped"] is False


def test_a_typical_run_finishes_under_a_second():
    """~4 years of weekdays, ~1 trade on 70% of them, the LucidFlex race on: the route's typical call."""
    rng = random.Random(0)
    tr = [{"date": d, "net": rng.uniform(-300.0, 400.0)} for d in weekdays(1040) if rng.random() < 0.7]
    t0 = time.perf_counter()
    r = mc.run(tr, paths=5000, seed=1, rules=LUCID)
    assert time.perf_counter() - t0 < 1.0 and r["n_days"] * r["paths"] <= mc.MAX_WORK


# ---------------------------------------------------------------- rereview: horizon + trade-aware work cap

def test_the_prop_race_is_the_first_horizon_days_so_bootstrap_matches_the_runs_own_prop_sim():
    """propsim.evaluate races HORIZON (250) i.i.d. weekday draws; a bootstrap MC path over a longer grid
    must race only its first 250 days, or the MC tile reads friendlier than the prop tile above it."""
    rng = random.Random(4)                  # a slow edge: without the horizon ~99% pass, with it ~67%
    tr = [{"date": d, "net": rng.choice([-200.0, 150.0, 220.0])} for d in weekdays(700) if rng.random() < 0.25]
    want = propsim.evaluate(tr, rules=LUCID)["headline"]["eval_pass_p"]
    got = mc.run(tr, paths=2800, seed=3, mode="bootstrap", rules=LUCID)
    assert got["n_days"] > 2 * propsim.HORIZON and got["paths"] == 2800      # a grid well past the horizon
    assert 0.1 < want < 0.9                                   # a race with room to move either way
    assert got["p_prop_pass"] == pytest.approx(want, abs=0.035)   # ~4 SE at 2,800 vs 20,000 paths


def test_the_work_cap_counts_trades_as_well_as_days():
    tr = by_day([[10.0, -5.0, 3.0, -2.0, 1.0]] * 1000)          # 1,000 days x 5 trades
    r = mc.run(tr, paths=10_000, seed=1)
    assert r["n_trades"] == 5000 and r["paths"] == mc.MAX_WORK // 5000 and r["capped"] is True
