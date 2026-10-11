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
    """The picker offers one eval per family -- newest version per family (the prop audit's
    corrections of 2026-10-11); older snapshots stay loadable."""
    ids = {r["id"]: r for r in list_rules()}
    assert set(ids) == {"lucid-flex-50k@2026-10-11", "lucid-flex-50k-dll@2026-10-11", "lucid-pro-50k@2026-10-11",
                        "lucid-pro-50k-no-dll@2026-10-11", "topstep-50k@2026-10-11", "apex-legacy-50k@2026-10-11",
                        "apex-eod-50k@2026-10-11", "apex-legacy-300k@2026-10-11"}
    assert ids["lucid-flex-50k@2026-10-11"] == {"id": "lucid-flex-50k@2026-10-11", "name": "LucidFlex 50K",
                                                "version": "2026-10-11", "confirmed": True}
    assert ids["lucid-pro-50k@2026-10-11"] == {"id": "lucid-pro-50k@2026-10-11", "name": "LucidPro 50K · $1,200 daily limit",
                                               "version": "2026-10-11", "confirmed": True}
    assert ids["lucid-pro-50k-no-dll@2026-10-11"]["name"] == "LucidPro 50K · no daily loss limit"
    assert load_rules("lucid-pro-50k@2026-09-27")["daily_loss_limit"] is None   # the older Pro still reproduces
    for old in ("lucid-flex-50k@2026-09-27", "lucid-pro-50k@2026-09-27b", "lucid-pro-50k-no-dll@2026-09-27b",
                "topstep-50k@2026-09-27b", "apex-legacy-300k@2026-09-28"):          # the pipeline's book names these: never edited
        assert load_rules(old)["version"] == old.split("@")[1]
    assert DEFAULT_RULES == "lucid-flex-50k@2026-10-11"
    # the superseded snapshot is off the picker but still on disk and still loadable
    assert (RULES_DIR / "lucid-flex-50k@2026-08.json").is_file()
    assert load_rules("lucid-flex-50k@2026-08")["version"] == "2026-08"

    lucid = evaluate(day_trades([500.0] * 5), n_paths=200)
    pro = evaluate(day_trades([500.0] * 5), "lucid-pro-50k@2026-09-27", n_paths=200)
    assert lucid["rules"]["id"] == DEFAULT_RULES and lucid["rules"]["label"] == "LucidFlex 50K"
    assert pro["rules"]["confirmed"] is False
    assert pro["rules"]["label"] == "LucidPro 50K (before the daily limit) · unconfirmed rules"
    # day_trades is a bare {date, net} ledger: it cannot see inside a day, and both results say so
    assert lucid["caveat"] == pro["caveat"] and lucid["caveat"].startswith(CAVEAT) and "OVERSTATED" in lucid["caveat"]
    assert lucid["breach"] == pro["breach"] == propsim.BREACH_CLOSE and "close_only" not in lucid
    for bad in ("nope@x", "../lucid-flex-50k@2026-08", "", None):
        with pytest.raises(ValueError, match="prop_rules"):
            load_rules(bad)


def test_the_apex_placeholder_is_gone():
    """Invented numbers are worse than no file: the old all-Flex-copy placeholder stays deleted;
    the Apex files that exist now carry the account holder's own numbers (2026-09-27)."""
    assert not (RULES_DIR / "apex-50k@unconfirmed.json").exists()
    assert sorted(p.name for p in RULES_DIR.glob("apex*")) == ["apex-eod-50k@2026-09-27b.json", "apex-eod-50k@2026-10-11.json",
                                                              "apex-legacy-300k@2026-09-28.json", "apex-legacy-300k@2026-10-11.json",
                                                              "apex-legacy-50k@2026-09-27b.json", "apex-legacy-50k@2026-10-11.json"]


def test_apex_legacy_300k_is_the_account_holders_numbers():
    """Account holder 2026-09-28: $20,000 target, $7,500 EOD trail locking at +$100 once the EOD
    peak reaches +$7,600, no daily loss limit, 35 minis; min days / consistency as the Legacy 50K."""
    r = load_rules("apex-legacy-300k@2026-09-28")
    assert (r["account_size"], r["eval_target"], r["trailing_mll"], r["lock_at"], r["lock_floor"]) == \
        (300000, 20000, 7500, 7600, 100)
    assert r["daily_loss_limit"] is None and r["consistency"] is None and r["eval_min_days"] == 1
    assert r["cap_micros"] == 350 and r["confirmed"] is False
    one_win = engine.run_eval([20000.0], r)
    assert one_win["outcome"] == "pass" and one_win["day"] == 1
    assert engine.run_eval([-7490.0, 0.0], r)["outcome"] == "timeout"      # $10 above the floor survives
    assert engine.run_eval([-7500.0], r)["outcome"] == "bust"              # touching the floor busts


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
    flex = load_rules("lucid-flex-50k@2026-09-27")
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
    assert 0.0 <= p["headline"]["eval_pass_p"] <= 1.0 and p["caveat"].startswith(CAVEAT)
    # the engine's ledger carries mae_usd: the run's own prop eval counts open losses and keeps the close-only reading beside it
    assert p["breach"] == propsim.BREACH_OPEN and "OVERSTATED" not in p["caveat"] and 0.0 <= p["close_only"]["eval_pass_p"] <= 1.0


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
    assert evaluate(ledger, DEFAULT_RULES, n_paths=300)["caveat"].startswith(CAVEAT)


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


def test_a_dip_past_the_limit_is_a_stop_even_when_the_trade_then_wins():
    """Lucid stops you the MOMENT the day reaches -$1,200, closed trades plus the open one. The
    engine's tick-level mae_usd shows the dip: a trade that sat at -1,300 then hit +3,000 is a
    -1,200 day; with -200 already banked, a -1,100 dip (-1,108 with its commission) is enough."""
    pro = load_rules("lucid-pro-50k@2026-09-27b")
    ledger = [{"date": "2024-03-04", "net": 3000.0, "mae_usd": 1300.0, "commission": 8.0},
              {"date": "2024-03-05", "net": -200.0, "mae_usd": 250.0, "commission": 8.0},
              {"date": "2024-03-05", "net": 2500.0, "mae_usd": 1100.0, "commission": 8.0},
              {"date": "2024-03-05", "net": 400.0, "mae_usd": 0.0, "commission": 8.0},
              {"date": "2024-03-06", "net": 900.0, "mae_usd": 1100.0, "commission": 8.0}]
    got = propsim.limit_trades(ledger, pro)
    assert [(t["date"], t["net"], t.get("dll_stop", False)) for t in got] == [
        ("2024-03-04", -1200.0, True), ("2024-03-05", -200.0, False), ("2024-03-05", -1000.0, True),
        ("2024-03-06", 900.0, False)]
    res = evaluate(ledger, "lucid-pro-50k@2026-09-27b", n_paths=200)
    assert res["dll_stopped_days"] == 2 and "OVERSTATED" not in res["caveat"]   # MAE present: nothing hidden
    assert res["breach"] == propsim.BREACH_OPEN
    # the same ledger without the limit is untouched
    assert propsim.limit_trades(ledger, load_rules("lucid-pro-50k-no-dll@2026-09-27b")) is ledger


def test_a_ledger_without_mae_is_flagged_as_overstated():
    ledger = day_trades([-1500.0, 800.0, 900.0])            # bare {date, net}: blind to intraday
    pro = evaluate(ledger, "lucid-pro-50k@2026-09-27b", n_paths=200)
    assert "OVERSTATED" in pro["caveat"]
    no = evaluate(ledger, "lucid-pro-50k-no-dll@2026-09-27b", n_paths=200)
    # without a daily limit the bare ledger is still blind to an open loss at the drawdown floor
    assert "dll_stopped_days" not in no and no["breach"] == propsim.BREACH_CLOSE and "OVERSTATED" in no["caveat"]


def test_monte_carlo_ruin_agrees_with_the_daily_limit():
    """p_ruin and the drawdowns walk the same capped days as p_prop_pass: one -2,500 day among
    wins is ruin against the $2,000 floor without the limit, never with it (-1,200)."""
    from homebase.backtest.stats import montecarlo
    ledger = day_trades([-2500.0, 900.0, 900.0, 900.0])
    dll = montecarlo.run(ledger, rules=load_rules("lucid-pro-50k@2026-09-27b"), paths=200, seed=1)
    no = montecarlo.run(ledger, rules=load_rules("lucid-pro-50k-no-dll@2026-09-27b"), paths=200, seed=1)
    assert no["p_ruin"] == 1.0 and dll["p_ruin"] == 0.0


def test_overlapping_positions_and_a_broken_mae_are_flagged():
    ledger = [{"date": "2024-03-04", "net": 500.0, "mae_usd": 700.0, "commission": 4.0, "entry_ms": 2, "exit_ms": 5},
              {"date": "2024-03-04", "net": 300.0, "mae_usd": 700.0, "commission": 4.0, "entry_ms": 1, "exit_ms": 9},
              {"date": "2024-03-05", "net": 900.0, "mae_usd": 100.0, "commission": 4.0, "entry_ms": 1, "exit_ms": 2},
              {"date": "2024-03-05", "net": 900.0, "mae_usd": 100.0, "commission": 4.0, "entry_ms": 3, "exit_ms": 4}]
    assert propsim.overlap_days(ledger) == 1
    res = evaluate(ledger, "lucid-pro-50k@2026-09-27b", n_paths=100)
    assert res["dll_overlap_days"] == 1 and "OVERSTATED" in res["caveat"]
    nan = [{"date": "2024-03-04", "net": 3000.0, "mae_usd": float("nan"), "commission": 4.0}]
    assert propsim.limit_trades(nan, load_rules("lucid-pro-50k@2026-09-27b"))[0]["net"] == 3000.0
    assert "OVERSTATED" in evaluate(nan, "lucid-pro-50k@2026-09-27b", n_paths=50)["caveat"]


def test_the_account_holders_other_evals():
    """2026-09-27: Flex + a $1,200 daily limit; Topstep = Flex with no daily limit and a 5-mini cap;
    Apex Legacy = $3,000 / $2,000 EOD trail locking at $50,100, 10 minis, no consistency, 1 day;
    Apex EOD = the same with a $1,000 daily limit and 6 minis. Apex payout terms are placeholders,
    so both Apex files stay unconfirmed."""
    flex = load_rules(DEFAULT_RULES)
    fd = load_rules("lucid-flex-50k-dll@2026-09-27b")
    assert fd["daily_loss_limit"] == 1200 and fd["consistency"] == 0.5 and fd["eval_min_days"] == 2
    top = load_rules("topstep-50k@2026-09-27b")
    assert top["cap_micros"] == 50 and top["daily_loss_limit"] is None
    same = ("eval_target", "trailing_mll", "lock_at", "lock_floor", "consistency", "eval_min_days", "win_day",
            "payout_win_days", "payout_share", "payout_cap", "max_payout_profit")
    assert all(top[k] == flex[k] == fd[k] for k in same)
    for rid, cap, dll in (("apex-legacy-50k@2026-09-27b", 100, None), ("apex-eod-50k@2026-09-27b", 60, 1000)):
        a = load_rules(rid)
        assert (a["eval_target"], a["trailing_mll"], a["lock_at"], a["lock_floor"]) == (3000, 2000, 2100, 100)
        assert a["consistency"] is None and a["eval_min_days"] == 1
        assert a["cap_micros"] == cap and a["daily_loss_limit"] == dll and a["confirmed"] is False
        assert engine.run_eval([3100.0], a)["outcome"] == "pass"          # one day, no consistency
    eod = load_rules("apex-eod-50k@2026-09-27b")
    legacy = load_rules("apex-legacy-50k@2026-09-27b")
    assert engine.run_eval([-2500.0], eod)["outcome"] == "timeout"        # stopped at -1,000 for the day
    assert engine.run_eval([-2500.0], legacy)["outcome"] == "bust"        # no daily limit: through the $2,000 trail


# ---------------------------------------------------------------- the prop audit, 2026-10-11

PRO_OWN, PRO_OWN_FREE = "lucid-pro-50k@2026-10-11", "lucid-pro-50k-no-dll@2026-10-11"


def test_an_open_loss_at_the_floor_fails_the_account_whatever_the_day_closes_at():
    """Open losses count (account holder 2026-10-02): a day is (P&L, traded, worst open loss). From a
    flat start the floor is -$2,000: a day that dipped $2,000 is a bust though it closed UP."""
    flex, pro = load_rules(DEFAULT_RULES), load_rules(PRO_OWN_FREE)
    assert engine.run_eval([(500.0, True, 2000.0)], flex) == dict(outcome="bust", day=1, trade_days=1, max_dd=2000.0)
    assert engine.run_eval([(500.0, True, 1999.99)], flex)["outcome"] == "timeout"
    assert engine.run_eval([(500.0, True)], flex) == engine.run_eval([500.0], flex) == engine.run_eval([(500.0, True, 0.0)], flex)
    # the floor trails the end-of-day peak, and the next day's worst point is held against THAT floor
    assert engine.run_eval([(1000.0, True, 0.0), (200.0, True, 2000.0)], flex)["outcome"] == "bust"
    assert engine.run_eval([(1000.0, True, 0.0), (200.0, True, 1999.0)], flex)["outcome"] == "timeout"
    # the breach comes before the close: a day that would have passed is a bust when it touched the floor first
    assert engine.run_eval([(3000.0, True, 1500.0)], pro)["outcome"] == "pass"
    assert engine.run_eval([(3000.0, True, 2000.0)], pro)["outcome"] == "bust"
    f = engine.run_funded([(900.0, True, 2000.0)] + [(900.0, True, 0.0)] * 4, flex)
    assert f == dict(payout_at=None, cheque=None, max_payout_at=None, bust_at=1)


def test_day_opens_is_the_days_worst_open_point():
    """realised so far - (mae + commission of every trade open then), at each entry; capped at the soft
    daily limit; None when a trade has no mae_usd."""
    flex, pro = load_rules(DEFAULT_RULES), load_rules(PRO_OWN)
    t = lambda d, a, b, net, mae: {"date": d, "entry_ms": a, "exit_ms": b, "net": net, "mae_usd": mae, "commission": 4.0}  # noqa: E731
    ledger = [t("2024-03-04", 10, 20, 300.0, 100.0),      # alone: 104 down at worst
              t("2024-03-04", 30, 40, -500.0, 600.0),     # after +300 banked: 300 - 604 = -304
              t("2024-03-05", 10, 50, 900.0, 700.0),      # two open at once: their open losses add
              t("2024-03-05", 20, 30, 100.0, 400.0),
              t("2024-03-07", 10, 20, 50.0, 0.0)]
    _, _, dates = weekday_grid(ledger)
    assert dates == ["2024-03-04", "2024-03-05", "2024-03-06", "2024-03-07"]
    assert propsim.day_opens(ledger, dates, flex) == [304.0, 1108.0, 0.0, 4.0]
    deep = [t("2024-03-04", 10, 20, 2500.0, 1900.0)]
    assert propsim.day_opens(deep, ["2024-03-04"], flex) == [1904.0]
    assert propsim.day_opens(deep, ["2024-03-04"], pro) == [1200.0]          # the day was closed at the limit
    assert propsim.day_opens(ledger + [{"date": "2024-03-08", "net": 5.0}], dates + ["2024-03-08"], flex) is None
    # no entry / exit times: one after the other, in ledger order
    bare = [{"date": "2024-03-04", "net": 300.0, "mae_usd": 100.0, "commission": 4.0},
            {"date": "2024-03-04", "net": -500.0, "mae_usd": 600.0, "commission": 4.0}]
    assert propsim.day_opens(bare, ["2024-03-04"], flex) == [304.0]


def test_the_tile_counts_open_losses_and_keeps_the_close_only_reading_beside_it():
    """Every day wins $1,600 after sitting $2,500 under water: on the close alone that passes every
    time; with open losses counted the first day fails every account."""
    ledger = [{**t, "mae_usd": 2500.0, "commission": 4.0} for t in day_trades([1600.0] * 6)]
    r = evaluate(ledger, PRO_OWN_FREE, n_paths=200)
    assert r["breach"] == propsim.BREACH_OPEN == "open losses count"
    assert (r["headline"]["eval_pass_p"], r["headline"]["bust_p"]) == (0.0, 1.0)
    assert (r["close_only"]["eval_pass_p"], r["close_only"]["bust_p"]) == (1.0, 0.0)
    assert "Open losses count" in r["caveat"] and "pass 100.0%" in r["caveat"] and "OVERSTATED" not in r["caveat"]
    calm = evaluate([{**t, "mae_usd": 50.0, "commission": 4.0} for t in day_trades([1600.0] * 6)], PRO_OWN_FREE, n_paths=200)
    assert calm["headline"]["eval_pass_p"] == calm["close_only"]["eval_pass_p"] == 1.0
    bare = evaluate(day_trades([1600.0] * 6), PRO_OWN_FREE, n_paths=200)       # no mae_usd: the old reading, and it says so
    assert bare["breach"] == propsim.BREACH_CLOSE and "close_only" not in bare and "OVERSTATED" in bare["caveat"]
    from homebase.backtest.stats import montecarlo
    rules = load_rules(PRO_OWN_FREE)
    assert montecarlo.run(ledger, paths=50, seed=1, rules=rules)["p_prop_pass"] == 0.0
    assert montecarlo.run(ledger, paths=50, seed=1, rules=rules)["prop_breach"] == propsim.BREACH_OPEN
    soft = montecarlo.run(day_trades([1600.0] * 6), paths=50, seed=1, rules=rules)
    assert (soft["p_prop_pass"], soft["prop_breach"]) == (1.0, propsim.BREACH_CLOSE)
    assert montecarlo.run(ledger, paths=50, seed=1)["prop_breach"] is None


def test_lucidpro_pays_on_its_own_rule_not_lucidflexs():
    """Lucid's payouts page (2026-10-11): no winning-days rule; cycle profit >= $500, largest day <= 40%
    of it, paid only from the profit above the $2,100 buffer, at least $500 and at most $2,000."""
    pro, old = load_rules(PRO_OWN_FREE), load_rules("lucid-pro-50k-no-dll@2026-09-27b")
    assert (pro["payout_min_profit"], pro["payout_consistency"], pro["payout_buffer"], pro["payout_min"], pro["payout_cap"],
            pro["max_payout_profit"]) == (500, 0.4, 2100, 500, 2000, 4100)
    assert pro["win_day"] is None and pro["payout_win_days"] is None and pro["payout_share"] is None and pro["scaling_micros"] is None
    eval_keys = ("eval_target", "eval_min_days", "consistency", "trailing_mll", "lock_at", "lock_floor", "daily_loss_limit", "cap_micros")
    assert all(pro[k] == old[k] for k in eval_keys)                           # the eval is the account holder's, unchanged
    for path in ([3100.0], [-2500.0], [900.0, -400.0, 2600.0], [1600.0, 1600.0]):
        assert engine.run_eval(path, pro) == engine.run_eval(path, old)
    # three even days reach +$2,700: $600 above the buffer, largest day a third of the profit -> a $600 cheque on day 3
    assert engine.run_funded([900.0] * 3, pro) == dict(payout_at=3, cheque=600.0, max_payout_at=None, bust_at=None)
    # ... and five reach +$4,500: the full $2,000, the maximum payout. No day had to be a "winning day" of $150
    assert engine.run_funded([900.0] * 5, pro) == dict(payout_at=3, cheque=600.0, max_payout_at=5, bust_at=None)
    # +$2,599 is $499 above the buffer: under the $500 minimum request
    assert engine.run_funded([900.0, 900.0, 799.0], pro)["payout_at"] is None
    # one day is more than 40% of the profit: nothing is paid until the others catch up
    lumpy = engine.run_funded([3000.0, 600.0, 600.0, 600.0, 2700.0], pro)     # 3000 of 4800 = 62% ... of 7500 = 40%
    assert lumpy == dict(payout_at=5, cheque=2000.0, max_payout_at=5, bust_at=None)
    # LucidFlex's rule on the same days pays at five $150 days whatever their shape -- the 2026-09-27b file's mistake
    assert engine.run_funded([3000.0, 600.0, 600.0, 600.0, 2700.0], old)["payout_at"] == 5
    assert engine.run_funded([3000.0, 600.0, 600.0, 600.0, 300.0], old)["max_payout_at"] == 5
    assert engine.run_funded([3000.0, 600.0, 600.0, 600.0, 300.0], pro)["max_payout_at"] is None
    res = evaluate(day_trades([900.0] * 8), PRO_OWN_FREE, n_paths=100)["result"]
    assert res["series"]["win_day_rate"] is None and res["funded"]["payout_p"] == 1.0


def test_the_other_corrected_files():
    """LucidFlex: a $500 minimum request. Topstep: 55% consistency, the floor locks at the start
    balance. Apex EOD: 30 calendar days (21 weekdays) and its own payout rule. Apex Legacy: the
    numbers are the account holder's, the name says what the file is."""
    flex, was = load_rules(DEFAULT_RULES), load_rules("lucid-flex-50k@2026-09-27")
    assert flex["payout_min"] == 500 and flex["flat_by_et"] == "16:45" and {k: v for k, v in flex.items() if k in was and was[k] != v}.keys() == {
        "version", "as_of", "source", "notes", "flat_by_et", "payout_ladder"}
    small = [200.0] * 4 + [-300.0, 200.0]              # five $200 days, +$700: half of it is under the $500 minimum
    assert engine.run_funded(small, was)["cheque"] == 350.0 and engine.run_funded(small, flex)["payout_at"] is None
    assert engine.run_funded([200.0] * 5, flex)["cheque"] == 500.0
    top = load_rules("topstep-50k@2026-10-11")
    assert (top["consistency"], top["lock_at"], top["lock_floor"], top["payout_min"], top["confirmed"]) == (0.55, 2000, 0, 125, False)
    assert engine.run_eval([1650.0, 1350.0], top)["outcome"] == "pass"         # 1,650 of 3,000 = 55%
    assert engine.run_eval([1700.0, 1300.0], top)["outcome"] == "timeout"      # 56.7%: the target rises, keep trading
    assert engine.run_eval([1700.0, 1300.0, 100.0], top)["outcome"] == "pass"  # 1,700 / 0.55 = 3,091 <= 3,100
    assert engine.run_eval([2500.0, -2400.0], top)["outcome"] == "timeout"     # locked at $50,000: +$100 is above it
    assert engine.run_eval([2500.0, -2500.0], top)["outcome"] == "bust"
    eod = load_rules("apex-eod-50k@2026-10-11")
    assert eod["max_days"] == 21 and eod["confirmed"] is False
    slow = evaluate(day_trades([100.0] * 40), "apex-eod-50k@2026-10-11", n_paths=50)      # +$100 a day needs 30 days: out of time
    assert slow["headline"]["eval_pass_p"] == 0.0 and slow["headline"]["timeout_p"] == 1.0
    assert evaluate(day_trades([100.0] * 40), "apex-eod-50k@2026-09-27b", n_paths=50)["headline"]["eval_pass_p"] == 1.0
    assert engine.run_funded([700.0] * 5, eod)["cheque"] == 1400.0             # +$3,500: $1,400 above the safety net
    assert engine.run_funded([700.0] * 6, eod)["max_payout_at"] == 6           # +$4,200: the $1,500 cap
    assert engine.run_funded([240.0] * 20, eod)["payout_at"] is None           # no day reaches $250
    for rid, old in (("apex-legacy-50k@2026-10-11", "apex-legacy-50k@2026-09-27b"), ("apex-legacy-300k@2026-10-11", "apex-legacy-300k@2026-09-28")):
        a, b = load_rules(rid), load_rules(old)
        assert a["name"].endswith("holder's EOD reading, not Apex's rule") and a["confirmed"] is False
        assert "intraday" in a["notes"][0] and {k for k in a if a[k] != b[k]} == {"name", "version", "as_of", "source", "notes", "disclaimer"}


def test_the_close_only_reading_is_of_the_same_paths_and_never_below():
    """close_only walks the very paths the open-loss number walked, so it can only be friendlier -- and the
    main stream is untouched by it: with no open loss on any day the two readings are one."""
    import random
    rnd = random.Random(4)
    nets = [round(rnd.gauss(40.0, 700.0), 2) for _ in range(160)]
    deep = [{**t, "mae_usd": max(-t["net"], 0.0) + abs(rnd.gauss(0.0, 900.0)), "commission": 4.0} for t in day_trades(nets)]
    flat = [{**t, "mae_usd": 0.0, "commission": 0.0} for t in day_trades(nets)]
    for rid in (DEFAULT_RULES, PRO_OWN, PRO_OWN_FREE):
        a, b, bare = evaluate(deep, rid, n_paths=1500), evaluate(flat, rid, n_paths=1500), evaluate(day_trades(nets), rid, n_paths=1500)
        assert a["close_only"]["eval_pass_p"] > a["headline"]["eval_pass_p"] and a["close_only"]["funded_payout_p"] >= a["headline"]["funded_payout_p"]
        assert a["close_only"]["bust_p"] < a["headline"]["bust_p"]
        if not load_rules(rid)["daily_loss_limit"]:           # (a daily limit reads the MAE too: only without one is the flat ledger the bare one)
            assert b["headline"] == bare["headline"]
            assert (b["close_only"]["eval_pass_p"], b["close_only"]["funded_payout_p"]) == (b["headline"]["eval_pass_p"], b["headline"]["funded_payout_p"])
            assert a["close_only"]["eval_pass_p"] == pytest.approx(bare["headline"]["eval_pass_p"], abs=0.04)
