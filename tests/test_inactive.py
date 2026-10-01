"""A booked strategy never silently does nothing: `inactive_today`, once per day, with why -- and readiness."""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
from zoneinfo import ZoneInfo

from homebase import inactive
from homebase.config import AccountCfg, AppCfg, StrategyCfg, _defaults
from homebase.engine import Engine
from homebase.levels import Geometry
from homebase.rules import RULES
from homebase.server import compute_readiness
from tests.test_engine import Clock, FakeAdapter
from tests.test_leveltimer import FIRE_NYAM, Rig, run

ET = ZoneInfo("America/New_York")
FRI, MON = dt.date(2026, 10, 2), dt.date(2026, 10, 5)
THU = dt.date(2026, 10, 1)
PROP = {"rules": "lucidflex50k", "start_balance": 50000.0, "mode": "eval"}


def cfg_with(name, *, paper=True, prop=None, book=True, **over):
    s = dataclasses.replace(_defaults().strategies[name], **{"enabled": True, **over})
    acct = AccountCfg(keyring_key="k", account_name="A", paper=paper, prop=prop or {})
    return AppCfg(armed=True, accounts={"a": acct}, strategies={name: s},
                  book={name: [{"account": "a", "qty": 4}]} if book else {})


def eng(tmp_path, cfg, hh=8, mm=0):
    return Engine(cfg, {"a": FakeAdapter("a")}, now_fn=Clock(hh + 4, mm), root=tmp_path)


def events(tmp_path, name="inactive_today"):
    p = tmp_path / "journal.jsonl"
    return [e for e in (json.loads(l) for l in p.read_text().splitlines()) if e["event"] == name] if p.exists() else []


# ---- static reasons ------------------------------------------------------------------------------
def test_gc_nfp_booked_is_inactive_off_its_day_and_active_on_it(tmp_path):
    cfg = cfg_with("gc_nfp")
    e = eng(tmp_path, cfg)
    s = cfg.strategies["gc_nfp"]
    assert inactive.static_reason(cfg, e, "gc_nfp", s, THU)[0] == "not_scheduled_today"
    assert inactive.static_reason(cfg, e, "gc_nfp", s, FRI) is None
    assert inactive.static_reason(cfg, e, "gc_nfp", s, MON)[0] == "not_scheduled_today"


def test_unbooked_or_disabled_strategies_are_not_asked(tmp_path):
    cfg = cfg_with("gc_nfp", book=False)
    assert inactive.static_reason(cfg, eng(tmp_path, cfg), "gc_nfp", cfg.strategies["gc_nfp"], THU) is None
    cfg = cfg_with("gc_nfp", enabled=False)
    assert inactive.static_reason(cfg, eng(tmp_path, cfg), "gc_nfp", cfg.strategies["gc_nfp"], THU) is None


def test_levels_real_account_without_the_ack_sits_out(tmp_path):
    cfg = cfg_with("nq_nyam_flex", paper=False)
    e = eng(tmp_path, cfg)
    code, why = inactive.static_reason(cfg, e, "nq_nyam_flex", cfg.strategies["nq_nyam_flex"], MON)
    assert code == "every_account_sits_out" and "ack_open_loss" in why
    cfg = cfg_with("nq_nyam_flex", paper=False, ack_open_loss=True)
    assert inactive.static_reason(cfg, eng(tmp_path, cfg), "nq_nyam_flex", cfg.strategies["nq_nyam_flex"], MON) is None


def test_target_take_without_a_prop_block_sits_out(tmp_path):
    cfg = cfg_with("nq_nyam_pro")                  # day_take 0, target_take: the take IS the account's distance
    code, why = inactive.static_reason(cfg, eng(tmp_path, cfg), "nq_nyam_pro", cfg.strategies["nq_nyam_pro"], MON)
    assert code == "every_account_sits_out" and "no prop block" in why
    cfg = cfg_with("nq_nyam_pro", prop=PROP)
    assert inactive.static_reason(cfg, eng(tmp_path, cfg), "nq_nyam_pro", cfg.strategies["nq_nyam_pro"], MON) is None


def test_a_half_day_and_a_missing_rule_and_a_bad_shape(tmp_path):
    cfg = cfg_with("nq_pm_flex")
    s = cfg.strategies["nq_pm_flex"]
    assert inactive.static_reason(cfg, eng(tmp_path, cfg), "nq_pm_flex", s, dt.date(2026, 11, 27))[0] == "early_close"
    assert inactive.static_reason(cfg, eng(tmp_path, cfg), "nq_pm_flex", s, MON) is None
    bad = StrategyCfg(symbol="NQ", qty=1, offset_pts=0, sl_pts=0, tp_pts=0, enabled=True, self_fire=True, kind="bars", rule="nope")
    cfg = AppCfg(armed=True, accounts={"a": AccountCfg(keyring_key="k", account_name="A")},
                 strategies={"b": bad}, book={"b": [{"account": "a", "qty": 1}]})
    assert inactive.static_reason(cfg, eng(tmp_path, cfg), "b", bad, MON)[0] == "unknown_rule"
    cfg = cfg_with("nq_orb_pro", shape="nope")
    assert inactive.static_reason(cfg, eng(tmp_path, cfg), "nq_orb_pro", cfg.strategies["nq_orb_pro"], MON)[0] == "bad_shape"


# ---- once a day, restarts included -----------------------------------------------------------------
def test_the_sweep_journals_once_and_a_restart_does_not_repeat(tmp_path):
    cfg = cfg_with("gc_nfp")
    e = eng(tmp_path, cfg)
    now = dt.datetime.combine(THU, dt.time(8, 0), tzinfo=ET)
    assert [r[:2] for r in inactive.sweep(cfg, e, now)] == [("gc_nfp", "not_scheduled_today")]
    assert inactive.sweep(cfg, e, now) == []
    ev, = events(tmp_path)
    assert ev["strategy"] == "gc_nfp" and ev["code"] == "not_scheduled_today" and "2026-10-02" in ev["reason"]
    e2 = eng(tmp_path, cfg)                                       # a desk restart the same day
    assert inactive.sweep(cfg, e2, now) == [] and len(events(tmp_path)) == 1
    assert e2.inactive_today("gc_nfp")


def test_nothing_on_the_nfp_morning_and_nothing_at_the_weekend(tmp_path):
    cfg = cfg_with("gc_nfp")
    e = eng(tmp_path, cfg)
    assert inactive.sweep(cfg, e, dt.datetime.combine(FRI, dt.time(8, 0), tzinfo=ET)) == []
    assert inactive.sweep(cfg, e, dt.datetime.combine(dt.date(2026, 10, 3), dt.time(8, 0), tzinfo=ET)) == []
    assert events(tmp_path) == []


def test_a_bar_rule_that_gave_no_signal_says_so_when_its_window_closes(tmp_path, monkeypatch):
    monkeypatch.setitem(RULES, "quiet", lambda bars, now, cfg: None)
    s = StrategyCfg(symbol="NQ", qty=1, offset_pts=0, sl_pts=0, tp_pts=0, enabled=True, self_fire=True, kind="bars", rule="quiet",
                    accept_from_et="09:29", accept_until_et="09:31")
    cfg = AppCfg(armed=True, accounts={"a": AccountCfg(keyring_key="k", account_name="A")},
                 strategies={"b": s}, book={"b": [{"account": "a", "qty": 1}]})
    e = eng(tmp_path, cfg)
    assert inactive.sweep(cfg, e, dt.datetime.combine(MON, dt.time(9, 30), tzinfo=ET)) == []   # still inside
    got = inactive.sweep(cfg, e, dt.datetime.combine(MON, dt.time(9, 32), tzinfo=ET))
    assert [g[:2] for g in got] == [("b", "no_signal")]
    # a strategy whose rule DID signal today is not reported
    (tmp_path / "x").mkdir()
    e2 = eng(tmp_path / "x", cfg)
    e2._signalled.add((e2._today(), "b"))
    assert inactive.sweep(cfg, e2, dt.datetime.combine(MON, dt.time(9, 32), tzinfo=ET)) == []


# ---- readiness ------------------------------------------------------------------------------------------
def readiness(cfg, e, day, hh=8, mm=0):
    ok = {"a": {"connected": True}}
    return compute_readiness(dt.datetime.combine(day, dt.time(hh, mm), tzinfo=ET), cfg, e, ok)["checks"]


def test_readiness_shows_a_booked_strategy_that_will_not_trade(tmp_path):
    cfg = cfg_with("gc_nfp")
    e = eng(tmp_path, cfg)
    for day in (THU, FRI):                         # off its day: expected, journaled only; on it: fine
        assert not [c for c in readiness(cfg, e, day) if c["label"] == "gc_nfp" and "inactive" in c["detail"]]
    cfg = cfg_with("nq_nyam_flex", paper=False)
    e = eng(tmp_path, cfg)
    c, = [c for c in readiness(cfg, e, MON) if c["label"] == "nq_nyam_flex"]
    assert c["level"] == "warn" and "ack_open_loss" in c["detail"]


# ---- the day's own reasons, from the level timer ------------------------------------------------
def test_a_roll_and_a_missed_day_and_a_half_day_each_say_inactive_once(tmp_path, monkeypatch):
    (tmp_path / "roll").mkdir()
    r = Rig(tmp_path / "roll", monkeypatch)
    r.tick(8, 55, 5)
    r.feed(FIRE_NYAM - 35 * 60 + 5, FIRE_NYAM)
    r.front = "NQH7"
    r.clock.s = FIRE_NYAM + 0.05
    run(r.lt.tick())
    run(r.lt.tick())
    ev, = r.events("inactive_today")
    assert (ev["strategy"], ev["code"]) == ("nq_nyam_flex", "contract_changed")
    assert r.eng.inactive_today("nq_nyam_flex")

    (tmp_path / "miss").mkdir()
    m = Rig(tmp_path / "miss", monkeypatch)
    m.md.fail_history = True
    m.day_to_the_fire()
    m.tick(9, 31, 1)
    codes = [e["code"] for e in m.events("inactive_today")]
    assert codes == ["missed"] and "no coverage" in m.events("inactive_today")[0]["reason"]

    (tmp_path / "half").mkdir()
    from tests.test_atrbars import FIRE_PM
    h = Rig(tmp_path / "half", monkeypatch, "nq_pm_flex", fire_s=FIRE_PM, date=dt.date(2026, 11, 27))
    h.tick(12, 55, 5)
    assert [e["code"] for e in h.events("inactive_today")] == ["early_close"]


def test_the_engine_says_why_when_every_account_sat_out_at_the_fire(tmp_path):
    cfg = cfg_with("nq_nyam_pro")                   # a paper account with no prop block: target_take has no level
    e = Engine(cfg, {"a": FakeAdapter("a")}, now_fn=Clock(13, 30), root=tmp_path)   # 09:30 ET
    geo = Geometry("atr_straddle", 30010.0, 29990.0, 60.0, 20.0, 30, anchor=30000.0, last_px=30000.0)
    res = run(e.handle_levels("nq_nyam_pro", geo))
    assert res["ok"] is False and res["reason"] == "every account sat out"
    ev, = events(tmp_path)
    assert ev["code"] == "every_account_sat_out" and "target_take" in ev["reason"]
    assert e.inactive_today("nq_nyam_pro") and events(tmp_path, "levels_refused")
