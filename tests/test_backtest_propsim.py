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
    """The picker offers exactly three evals -- LucidFlex (the default, confirmed), LucidPro
    with its $1,200 daily limit and LucidPro without it (both partly unconfirmed) -- newest
    version per family; older snapshots stay loadable."""
    ids = {r["id"]: r for r in list_rules()}
    assert set(ids) == {"lucid-flex-50k@2026-09-27", "lucid-pro-50k@2026-09-27b", "lucid-pro-50k-no-dll@2026-09-27b"}
    assert ids["lucid-flex-50k@2026-09-27"] == {"id": "lucid-flex-50k@2026-09-27", "name": "LucidFlex 50K",
                                                "version": "2026-09-27", "confirmed": True}
    assert ids["lucid-pro-50k@2026-09-27b"] == {"id": "lucid-pro-50k@2026-09-27b", "name": "LucidPro 50K · $1,200 daily limit",
                                                "version": "2026-09-27b", "confirmed": True}
    assert ids["lucid-pro-50k-no-dll@2026-09-27b"]["name"] == "LucidPro 50K · no daily loss limit"
    assert load_rules("lucid-pro-50k@2026-09-27")["daily_loss_limit"] is None   # the older Pro still reproduces
    assert DEFAULT_RULES == "lucid-flex-50k@2026-09-27"
    # the superseded snapshot is off the picker but still on disk and still loadable
    assert (RULES_DIR / "lucid-flex-50k@2026-08.json").is_file()
    assert load_rules("lucid-flex-50k@2026-08")["version"] == "2026-08"

    lucid = evaluate(day_trades([500.0] * 5), n_paths=200)
    pro = evaluate(day_trades([500.0] * 5), "lucid-pro-50k@2026-09-27", n_paths=200)
    assert lucid["rules"]["id"] == DEFAULT_RULES and lucid["rules"]["label"] == "LucidFlex 50K"
    assert pro["rules"]["confirmed"] is False
    assert pro["rules"]["label"] == "LucidPro 50K (before the daily limit) · unconfirmed rules"
    assert lucid["caveat"] == pro["caveat"] == CAVEAT
    for bad in ("nope@x", "../lucid-flex-50k@2026-08", "", None):
        with pytest.raises(ValueError, match="prop_rules"):
            load_rules(bad)


def test_the_apex_placeholder_is_gone():
    """Invented numbers are worse than no file: other accounts map onto Flex or Pro."""
    assert not (RULES_DIR / "apex-50k@unconfirmed.json").exists()
    assert not list(RULES_DIR.glob("apex*"))


def test_flex_2026_09_27_reaffirms_the_2026_08_numbers_so_nothing_moves():
    """Account holder, 2026-09-27: Flex DOES have the 50% consistency rule on top of the
    2-day minimum. The new snapshot is a reaffirmation, not a change -- every rule number
    matches 2026-08, so Flex pass rates must be byte-identical across the two files."""
    old = load_rules("lucid-flex-50k@2026-08")
    new = load_rules("lucid-flex-50k@2026-09-27")
    assert new["consistency"] == old["consistency"] == 0.5
    assert new["eval_min_days"] == old["eval_min_days"] == 2
    provenance = {"version", "as_of", "source", "notes", "confirmed", "disclaimer"}
    assert set(new) - provenance == set(old) - provenance
    for k in set(new) - provenance:
        assert new[k] == old[k], k
    assert "2026-09-27" in new["source"] and "consistency" in new["source"]

    pnls = [900.0, -400.0, 0.0, 1800.0, -250.0, 120.0, 2600.0, -700.0]
    before = evaluate(day_trades(pnls), "lucid-flex-50k@2026-08", n_paths=2000)
    after = evaluate(day_trades(pnls), "lucid-flex-50k@2026-09-27", n_paths=2000)
    assert before["headline"] == after["headline"]
    assert before["result"] == after["result"]


def test_pro_is_flex_minus_the_consistency_rule_and_the_minimum_days():
    """Account holder, 2026-09-27: "same as Flex except no consistency rule and no
    minimum days". Everything else is INHERITED and unconfirmed."""
    flex = load_rules(DEFAULT_RULES)
    pro = load_rules("lucid-pro-50k@2026-09-27")
    assert pro["consistency"] is None and pro["eval_min_days"] == 1
    assert pro["confirmed"] is False
    for word in ("2026-09-27", "INHERITED FROM FLEX", "NOT INDEPENDENTLY CONFIRMED"):
        assert word in pro["source"], word
    differ = {"name", "version", "source", "confirmed", "notes", "disclaimer",
              "consistency", "eval_min_days"}
    assert set(pro) - differ == set(flex) - differ
    for k in set(pro) - differ:
        assert pro[k] == flex[k], k


def test_a_null_consistency_disables_the_check_and_0_5_still_blocks():
    """propsim.run_eval must treat `consistency: null` as "no consistency check" --
    and must still enforce it when the ruleset carries 0.5."""
    flex, pro = load_rules(DEFAULT_RULES), load_rules("lucid-pro-50k@2026-09-27")

    # one dominant day (2,900 of 3,100 = 93.5% > 50%): Flex refuses to pass, Pro passes
    dominant = [2900.0, 200.0]
    assert engine.run_eval(dominant, flex)["outcome"] == "timeout"
    pro_out = engine.run_eval(dominant, pro)
    assert pro_out["outcome"] == "pass" and pro_out["day"] == 2

    # Pro has no minimum days either: +$3,100 on day 1 is a pass; Flex needs a 2nd day
    assert engine.run_eval([3100.0], pro) == dict(outcome="pass", day=1, trade_days=1, max_dd=0.0)
    assert engine.run_eval([3100.0], flex)["outcome"] == "timeout"

    # a balanced pair clears Flex's 50% (1,600 of 3,200 = exactly 50%)
    assert engine.run_eval([1600.0, 1600.0], flex)["outcome"] == "pass"


def test_no_trades_is_a_skip_not_a_crash():
    r = evaluate([], n_paths=10)
    assert r["skipped"].startswith("no trades") and "headline" not in r


def test_the_runner_writes_propsim_json_and_validates_the_rule_set(tmp_path, monkeypatch):
    monkeypatch.setattr(propsim, "N_PATHS", 300)
    assert validate({"strategy": "nq930"})["prop_rules"] == DEFAULT_RULES
    with pytest.raises(ValueError, match="prop_rules"):
        validate({"strategy": "nq930", "prop_rules": "zz@1"})
    store = TapeStore(nq_archive(tmp_path / "ticks"), tmp_path / "cache")
    rid = prepare({"strategy": "nq930", "inputs": {"adx_gate": False}, "prop_rules": "lucid-pro-50k@2026-09-27",
                   "range": {"kind": "custom", "start": "2024-03-01", "end": "2024-03-31"}}, tmp_path / "t")
    meta = execute(tmp_path / "t" / "runs" / rid, store)
    p = read_json(tmp_path / "t" / "runs" / rid / "propsim.json")
    assert meta["prop_rules"] == "lucid-pro-50k@2026-09-27"
    assert p["rules"]["label"] == "LucidPro 50K (before the daily limit) · unconfirmed rules" and p["n_paths"] == 300
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


def test_lucidpro_account_holder_numbers_and_the_removable_daily_limit():
    """Account holder, 2026-09-27: LucidPro 50K = $50,000, target $3,000, max loss $2,000,
    daily loss limit $1,200 (removable), max size 4 minis / 40 micros. The two new files
    differ ONLY in the daily limit (and name/notes)."""
    dll = load_rules("lucid-pro-50k@2026-09-27b")
    no = load_rules("lucid-pro-50k-no-dll@2026-09-27b")
    for r in (dll, no):
        assert (r["account_size"], r["eval_target"], r["trailing_mll"], r["cap_micros"]) == (50000, 3000, 2000, 40)
        assert r["consistency"] is None and r["eval_min_days"] == 1 and r["confirmed"] is True
    assert dll["daily_loss_limit"] == 1200 and no["daily_loss_limit"] is None
    differ = {"name", "notes", "daily_loss_limit"}
    assert {k: v for k, v in dll.items() if k not in differ} == {k: v for k, v in no.items() if k not in differ}


def test_a_soft_daily_limit_caps_the_day_and_the_account_survives():
    """Hitting the limit stops you for the day (soft): the day's loss is capped at
    -$1,200 and the account carries on -- it is not a bust by itself."""
    dll = load_rules("lucid-pro-50k@2026-09-27b")
    no = load_rules("lucid-pro-50k-no-dll@2026-09-27b")
    # -1,900 then +3,200: without the limit that is -1,900 + 3,200 = 1,300 (no pass yet);
    # with it the first day costs only 1,200, so the account stands at +2,000 -> +3,000 needs one more
    assert engine.run_eval([-1900.0, 3200.0], no) == dict(outcome="timeout", day=2, trade_days=2, max_dd=1900.0)
    assert engine.run_eval([-1900.0, 3200.0], dll) == dict(outcome="timeout", day=2, trade_days=2, max_dd=1200.0)
    assert engine.run_eval([-1900.0, 3200.0, 1000.0], dll)["outcome"] == "pass"
    # a -2,500 day busts the $2,000 max loss without the limit; with it the day stops at -1,200
    assert engine.run_eval([-2500.0], no)["outcome"] == "bust"
    assert engine.run_eval([-2500.0], dll)["outcome"] == "timeout"
    # two limit days in a row still bust (-2,400 through the -2,000 floor)
    assert engine.run_eval([-2500.0, -2500.0], dll) == dict(outcome="bust", day=2, trade_days=2, max_dd=2400.0)
    # losses inside the limit and all wins are untouched
    assert engine.run_eval([-800.0, 4000.0], dll) == engine.run_eval([-800.0, 4000.0], no)
    # the funded account gets the same cap
    assert engine.run_funded([-2500.0], no)["bust_at"] == 1
    assert engine.run_funded([-2500.0], dll)["bust_at"] is None


def test_flex_is_unchanged_by_the_daily_limit_code():
    """Flex carries `daily_loss_limit: null`: limit_trades hands back the very same ledger, and
    the eval/funded races give exactly what a limit-free Pro file gives on the same days."""
    flex, no = load_rules(DEFAULT_RULES), load_rules("lucid-pro-50k-no-dll@2026-09-27b")
    assert flex["daily_loss_limit"] is None
    ledger = day_trades([-2500.0, 400.0, -1900.0, 3200.0])
    assert propsim.limit_trades(ledger, flex) is ledger
    for path in ([-2500.0], [-1900.0, 3200.0, 1000.0], [2900.0, 200.0, 50.0], [1600.0, 1600.0]):
        assert engine.run_eval(path, flex) == engine.run_eval(path, dict(flex, daily_loss_limit=None))
        assert engine.run_funded(path, flex) == engine.run_funded(path, dict(flex, daily_loss_limit=None))
    assert evaluate(ledger, DEFAULT_RULES, n_paths=300)["caveat"] == CAVEAT


def test_a_bad_daily_limit_is_refused_not_guessed():
    flex = load_rules(DEFAULT_RULES)
    for bad in (-1200, "1200", True):
        with pytest.raises(ValueError, match="daily_loss_limit"):
            engine.run_eval([-500.0] * 3, dict(flex, daily_loss_limit=bad))
    assert engine.run_eval([-2500.0], dict(flex, daily_loss_limit=0))["outcome"] == "bust"   # 0 = no limit


def test_limit_trades_stops_the_day_at_the_limit():
    """Trade level: the crossing trade is cut to exactly the limit and the day's later trades never
    happen -- so -1,300 then +500 is a -1,200 day, not -800."""
    pro = load_rules("lucid-pro-50k@2026-09-27b")
    ledger = [{"date": "2024-03-04", "net": -1300.0}, {"date": "2024-03-04", "net": 500.0},
              {"date": "2024-03-05", "net": -700.0}, {"date": "2024-03-05", "net": -700.0},
              {"date": "2024-03-05", "net": 900.0}, {"date": "2024-03-06", "net": -300.0}]
    got = [(t["date"], t["net"]) for t in propsim.limit_trades(ledger, pro)]
    assert got == [("2024-03-04", -1200.0), ("2024-03-05", -700.0), ("2024-03-05", -500.0), ("2024-03-06", -300.0)]


def test_the_result_warns_when_a_single_trade_breaks_the_limit():
    ledger = day_trades([-1500.0, 800.0, 900.0])
    pro = evaluate(ledger, "lucid-pro-50k@2026-09-27b", n_paths=200)
    assert pro["dll_trades_over"] == 1 and "OVERSTATED" in pro["caveat"]
    no = evaluate(ledger, "lucid-pro-50k-no-dll@2026-09-27b", n_paths=200)
    assert "dll_trades_over" not in no and no["caveat"] == CAVEAT


def test_monte_carlo_ruin_agrees_with_the_daily_limit():
    """p_ruin and the drawdowns walk the same capped days as p_prop_pass: one -2,500 day among
    wins is ruin against the $2,000 floor without the limit, never with it (-1,200)."""
    from homebase.backtest.stats import montecarlo
    ledger = day_trades([-2500.0, 900.0, 900.0, 900.0])
    dll = montecarlo.run(ledger, rules=load_rules("lucid-pro-50k@2026-09-27b"), paths=200, seed=1)
    no = montecarlo.run(ledger, rules=load_rules("lucid-pro-50k-no-dll@2026-09-27b"), paths=200, seed=1)
    assert no["p_ruin"] == 1.0 and dll["p_ruin"] == 0.0
