"""CONTROLS of the edge library (EDGE_SPEC E): the C1 random-entry control (port of R/families/random.py, tester-matched), the
day- and session-matched draws, the best-of-nulls bar. The time-shuffle null is in test_edge_clock.py, C2 in test_score_c2.py.
Identity, counts and arithmetic only."""
import json

import numpy as np
import pytest

import l2ref
import l2sim as S
import library as LB
import sim_validate as V

RUNS = S.REPO / "homebase" / ".state" / "tester" / "runs"
R_CTRL = "20260929-220631-draft_pp_random-bb39"            # R ctrl-random-tf5-s1: tf 5, p_entry 0.1, seed 1, sess all (in-sample)
R_GRID = "20260930-113916-draft_pp_random-b6f5"            # R fpctrl-random-tf30-s21: stop pts 10 / 20 / 30 / 45 x tgt_r (16 cells)


def test_random_port_reproduces_the_pilots_control_bundle_on_one_quarter():
    run = json.loads((RUNS / R_CTRL / "run.json").read_text())
    assert run["range"]["end"] < "2025-01-01" and not run["range"]["holdout"] and run["strategy"]["id"] == "draft_pp_random"
    a, b = "2022-04-01", "2022-06-30"
    ref = [t for t in json.loads((RUNS / R_CTRL / "trades.json").read_text()) if a <= t["date"] <= b]
    res = S.run(l2ref.Random, run["inputs"], a, b, workers=1)
    c = V.compare(res["trades"], ref)
    assert c["n_ref"] > 500 and c["n_sim"] == c["n_ref"] == c["matched"] == c["exact_all_fields"] and c["net_diff"] == 0.0
    assert res["skipped_by_error"] == 0 and res["both_sides_sessions"] == 0


def test_random_port_reproduces_a_fixed_point_stop_cell_of_the_control_heat_map():
    inputs, ref, cov, cost, engine = V.load_bundle(f"{R_GRID}#5")
    assert inputs["stop_mode"] == "pts" and inputs["p_entry"] == 0.5 and engine == "tick-2"
    a, b = "2023-01-03", "2023-02-28"
    ref = [t for t in ref if a <= t["date"] <= b]
    c = V.compare(S.run(l2ref.Random, inputs, a, b, workers=1)["trades"], ref)
    assert c["n_ref"] > 150 and c["n_sim"] == c["n_ref"] == c["exact_all_fields"]


def test_random_stream_is_keyed_by_seed_date_and_session_not_by_the_trade_path():
    days = ["2023-03-14", "2023-03-15", "2023-03-16"]
    all5 = S.run(l2ref.Random, {"tf": "5", "sess": "all", "p_entry": 0.5}, days=days, workers=1)["trades"]
    nyam = S.run(l2ref.Random, {"tf": "5", "sess": "nyam", "p_entry": 0.5}, days=days, workers=1)["trades"]
    assert nyam == [t for t in all5 if S.session_of(t["entry_ms"]) == "nyam"] and 6 <= len(nyam) <= 9     # max_tr 3 x 3 days
    other = S.run(l2ref.Random, {"tf": "5", "sess": "nyam", "p_entry": 0.5, "seed": 2}, days=days, workers=1)["trades"]
    assert [t["entry_ms"] for t in other] != [t["entry_ms"] for t in nyam]
    wide = S.run(l2ref.Random, {"tf": "5", "sess": "nyam", "p_entry": 0.5, "stop_val": 3.0, "tgt_r": 0.0}, days=days, workers=1)["trades"]
    assert wide[0]["entry_ms"] == nyam[0]["entry_ms"] and wide[0]["side"] == nyam[0]["side"]              # same first draw, other exits


def test_best_of_nulls_is_the_95th_percentile_of_each_null_replicates_best_cell():
    rng = np.random.default_rng(7)
    batch = [{f"c{k}": float(v) for k, v in enumerate(rng.normal(0, 1, 32))} for _ in range(40)]
    out = LB.best_of_nulls(batch)
    best = sorted(max(r.values()) for r in batch)
    assert out["bar"] == pytest.approx(float(np.percentile(best, 95))) and out["nulls"] == 40 and not out["thin"] and out["stat"] == "t"
    assert out["best"] == [round(b, 4) for b in best] and out["bar"] > float(np.median(best)) and out["bar"] <= best[-1]
    assert LB.best_of_nulls([list(r.values()) for r in batch])["bar"] == pytest.approx(out["bar"])       # sequences work too
    assert LB.best_of_nulls(batch[:5])["thin"] and LB.best_of_nulls(batch, q=50)["bar"] == pytest.approx(float(np.median(best)))
    # replicates of per-cell net ARRAYS are reduced with the cell statistic (t of the per-trade net)
    nets = [{"a": np.array([10.0, -5.0, 20.0, 1.0]), "b": np.array([-3.0, -2.0, -8.0])}, {"a": np.array([1.0, 2.0, 3.0, 4.0]), "b": np.zeros(0)}]
    got = LB.best_of_nulls(nets)
    t = lambda x: float(np.mean(x) / (np.std(x, ddof=1) / np.sqrt(len(x))))      # noqa: E731
    assert got["best"] == sorted([round(t(nets[0]["a"]), 4), round(t(nets[1]["a"]), 4)]) and LB.cell_stat(np.zeros(0)) == 0.0
    assert LB.best_of_nulls(nets, stat="net")["best"] == [10.0, 26.0]
    with pytest.raises(ValueError):
        LB.best_of_nulls([])
    # a real edge clears the bar, the null's own median cell does not
    assert 5.0 > out["bar"] > float(np.median([v for r in batch for v in r.values()]))


def _arr(rows):
    """rows: (date ordinal, session code, net)"""
    return {"date": np.array([r[0] for r in rows], np.int32), "sess": np.array([r[1] for r in rows], np.int8),
            "net": np.array([r[2] for r in rows], np.float64)}


def test_c1_draws_are_matched_by_day_and_session():
    member = _arr([(100, 4, 50.0), (100, 4, 30.0), (101, 2, -20.0), (103, 4, 40.0)])
    pool = _arr([(100, 4, 1.0), (100, 4, 2.0), (100, 4, 3.0), (100, 2, 1000.0), (101, 2, 10.0), (101, 4, 500.0), (102, 4, 7.0),
                 (104, 4, 9.0), (105, 4, 11.0)])
    out = LB.c1_draws(member, pool, K=400, seed=3)
    # day 100 pm: 2 of {1, 2, 3}; day 101 nyam: the one 10; day 103 pm: none that day -> the nearest pm dates (102 and 104)
    assert set(np.round(out["nets"], 6)) == {a + 10 + c for a in (3.0, 4.0, 5.0) for c in (7.0, 9.0)}
    assert out["short"] == 0 and out["fallback_share"] == 0.25 and out["pool_trades"] == 9
    assert out["member_net"] == 100.0 and out["lift"] == pytest.approx(100.0 - out["mean"], abs=0.011) and out["p_beat"] == 1.0
    assert np.array_equal(out["nets"], LB.c1_draws(member, pool, K=400, seed=3)["nets"])                # seeded
    assert not np.array_equal(out["nets"], LB.c1_draws(member, pool, K=400, seed=4)["nets"])
    lone = LB.c1_draws(_arr([(100, 0, 5.0)]), pool, K=10)        # a session the pool never trades: cannot be matched -> short
    assert lone["short"] == 1 and (lone["nets"] == 0).all()
    assert LB.default_seed("x", "build") != LB.default_seed("x", "pick") and LB.default_seed("x", "build") == LB.default_seed("x", "build")
