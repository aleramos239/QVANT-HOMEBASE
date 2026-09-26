"""Prop-eval pass rate: the vendored engine's determinism, always-pass / always-bust
ledgers, rule files and the unconfirmed label, and the runner's propsim.json."""
from __future__ import annotations

import datetime as dt
import json

import pytest

from homebase.backtest import propsim
from homebase.backtest.propsim import (CAVEAT, DEFAULT_RULES, RULES_DIR, evaluate, list_rules,
                                       load_rules, weekday_grid)
from homebase.backtest.propsim import propsim as engine
from homebase.backtest.runner import execute, prepare, read_json, validate
from homebase.backtest.tape import TapeStore
from tests.backtest_util import nq_archive

MON = dt.date(2024, 3, 4)


def day_trades(nets, start=MON):
    """One trade per WEEKDAY from `start`, net P&L as given."""
    out, d = [], start
    for n in nets:
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        out.append({"date": d.isoformat(), "net": n})
        d += dt.timedelta(days=1)
    return out


def test_the_vendored_engine_is_deterministic():
    pnls = [350.0, -420.0, 0.0, 610.0, -150.0, 90.0, 0.0, 1200.0, -800.0, 300.0]
    a = engine.run(pnls, n_paths=2000, sweep=(), degradation=(), seed=7)
    b = engine.run(pnls, n_paths=2000, sweep=(), degradation=(), seed=7)
    c = engine.run(pnls, n_paths=2000, sweep=(), degradation=(), seed=8)
    assert a == b
    assert a["eval"]["p"] != c["eval"]["p"] or a["funded"] != c["funded"]
    assert evaluate(day_trades(pnls), n_paths=2000) == evaluate(day_trades(pnls), n_paths=2000)


def test_a_ledger_that_always_passes():
    r = evaluate(day_trades([1000.0] * 10), n_paths=500)
    h = r["headline"]
    assert h["eval_pass_p"] == 1.0 and h["bust_p"] == 0.0 and h["timeout_p"] == 0.0
    assert h["median_days_to_pass"] == 3            # +3,000 on day 3; largest day 1,000 <= 50%
    assert h["eval_pass_ci"][1] == pytest.approx(1.0) and h["eval_pass_ci"][0] > 0.99   # Wilson, n=500
    assert h["funded_payout_p"] == 1.0 and h["funded_expected_cheque"] == 2000.0   # 50% of 5,000, capped


def test_a_ledger_that_always_busts():
    h = evaluate(day_trades([-2500.0] * 10), n_paths=500)["headline"]
    assert h["eval_pass_p"] == 0.0 and h["bust_p"] == 1.0
    assert h["median_days_to_pass"] is None and h["funded_expected_cheque"] == 0.0


def test_the_weekday_grid_fills_no_trade_weekdays_with_zero():
    trades = [{"date": "2024-03-04", "net": 100.0}, {"date": "2024-03-07", "net": -50.0},
              {"date": "2024-03-07", "net": 20.0}, {"date": "2024-03-11", "net": 10.0}]
    pnls, flags, dates = weekday_grid(trades)
    assert dates == ["2024-03-04", "2024-03-05", "2024-03-06", "2024-03-07", "2024-03-08", "2024-03-11"]
    assert pnls == [100.0, 0.0, 0.0, -30.0, 0.0, 10.0]
    assert flags == [True, False, False, True, False, True]
    assert weekday_grid([]) == ([], [], [])


def test_rule_files_and_the_unconfirmed_label():
    ids = {r["id"]: r for r in list_rules()}
    assert ids["lucid-flex-50k@2026-08"]["confirmed"] is True
    assert ids["apex-50k@unconfirmed"] == {"id": "apex-50k@unconfirmed", "name": "Apex 50K",
                                          "version": "unconfirmed", "confirmed": False}
    lucid = evaluate(day_trades([500.0] * 5), n_paths=200)
    apex = evaluate(day_trades([500.0] * 5), "apex-50k@unconfirmed", n_paths=200)
    assert lucid["rules"]["id"] == DEFAULT_RULES and lucid["rules"]["label"] == "LucidFlex 50K"
    assert apex["rules"]["confirmed"] is False
    assert apex["rules"]["label"] == "Apex 50K · unconfirmed rules"
    assert lucid["caveat"] == apex["caveat"] == CAVEAT
    for bad in ("nope@x", "../lucid-flex-50k@2026-08", "", None):
        with pytest.raises(ValueError, match="prop_rules"):
            load_rules(bad)


def test_apex_placeholders_are_the_lucidflex_numbers_until_confirmed():
    apex = json.loads((RULES_DIR / "apex-50k@unconfirmed.json").read_text())
    lucid = load_rules(DEFAULT_RULES)
    assert apex["confirmed"] is False and "PLACEHOLDER" in apex["source"]
    assert set(apex) >= set(lucid) - {"source", "as_of", "notes", "disclaimer", "payout_ladder"}
    for k in apex["placeholder_fields"]:
        assert apex[k] == lucid[k], k


def test_no_trades_is_a_skip_not_a_crash():
    r = evaluate([], n_paths=10)
    assert r["skipped"].startswith("no trades") and "headline" not in r


def test_the_runner_writes_propsim_json_and_validates_the_rule_set(tmp_path, monkeypatch):
    monkeypatch.setattr(propsim, "N_PATHS", 300)
    assert validate({"strategy": "nq930"})["prop_rules"] == DEFAULT_RULES
    with pytest.raises(ValueError, match="prop_rules"):
        validate({"strategy": "nq930", "prop_rules": "zz@1"})
    store = TapeStore(nq_archive(tmp_path / "ticks"), tmp_path / "cache")
    rid = prepare({"strategy": "nq930", "inputs": {"adx_gate": False}, "prop_rules": "apex-50k@unconfirmed",
                   "range": {"kind": "custom", "start": "2024-03-01", "end": "2024-03-31"}}, tmp_path / "t")
    meta = execute(tmp_path / "t" / "runs" / rid, store)
    p = read_json(tmp_path / "t" / "runs" / rid / "propsim.json")
    assert meta["prop_rules"] == "apex-50k@unconfirmed"
    assert p["rules"]["label"] == "Apex 50K · unconfirmed rules" and p["n_paths"] == 300
    assert p["grid"] == {"first": "2024-03-05", "last": "2024-03-05", "weekdays": 1, "trade_days": 1}
    assert 0.0 <= p["headline"]["eval_pass_p"] <= 1.0 and p["caveat"] == CAVEAT


def test_a_malformed_rule_file_never_loses_the_run_bundle(tmp_path, monkeypatch):
    """A rule file missing a key the engine requires (e.g. trailing_mll) must not throw
    away trades/equity/plots/run.json -- it degrades to an error recorded in propsim.json,
    the run still finishes `done`."""
    monkeypatch.setattr(propsim, "N_PATHS", 300)
    bad_dir = tmp_path / "rules"
    bad_dir.mkdir()
    broken = load_rules(DEFAULT_RULES)
    del broken["trailing_mll"]                              # a key the engine requires
    (bad_dir / "broken-rules@t1.json").write_text(json.dumps(broken))
    monkeypatch.setattr(propsim, "RULES_DIR", bad_dir)

    store = TapeStore(nq_archive(tmp_path / "ticks"), tmp_path / "cache")
    rid = prepare({"strategy": "nq930", "inputs": {"adx_gate": False}, "prop_rules": "broken-rules@t1",
                   "range": {"kind": "custom", "start": "2024-03-01", "end": "2024-03-31"}}, tmp_path / "t")
    run_dir = tmp_path / "t" / "runs" / rid
    meta = execute(run_dir, store)

    assert meta["propsim_error"] is True
    for name in ("trades.json", "equity.json", "plots.json", "propsim.json", "run.json"):
        assert (run_dir / name).is_file(), name
    st = read_json(run_dir / "status.json")
    assert st["status"] == "done"
    p = read_json(run_dir / "propsim.json")
    assert p["error"].startswith("KeyError") and "trailing_mll" in p["error"]
    assert p["rules"] == {"name": "LucidFlex 50K", "confirmed": True, "label": "LucidFlex 50K"}
