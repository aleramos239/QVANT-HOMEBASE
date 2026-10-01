"""config.json carries the "levels" strategies and the accounts' prop standing; old files still load."""
from __future__ import annotations

import json

import pytest

from homebase import config as desk_config
from homebase.config import AccountCfg, StrategyCfg

NAMES = ("nq_nyam_flex", "nq_nyam_pro", "nq_orb_pro", "nq_pm_flex")


@pytest.fixture
def cfg_path(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    monkeypatch.setattr(desk_config, "config_path", lambda: p)
    return p


def test_the_four_strategies_ship_off_unbooked_and_unacknowledged():
    d = desk_config._defaults()
    for n in NAMES:
        s = d.strategies[n]
        assert s.kind == "levels" and not s.enabled and not s.shadow and not s.ack_open_loss
        assert s.symbol == "NQ" and s.qty == 4 and s.fee_rt == 4.0 and s.sl_atr == 3.0
        assert n not in d.book


def test_the_specs_numbers():
    s = {n: desk_config._defaults().strategies[n] for n in NAMES}
    f, p, o, m = (s[n] for n in NAMES)
    assert (f.shape, f.fire_et, f.atr_tf, f.off_atr, f.day_take, f.target_take) == ("atr_straddle", "09:30:00", 30, 0.25, 1500.0, True)
    assert (f.cancel_et, f.flat_et, f.accept_from_et, f.accept_until_et) == ("10:55", "11:00", "09:29", "09:31")
    assert (p.day_take, p.target_take, p.fire_et, p.off_atr) == (0.0, True, "09:30:00", 0.25)
    assert (o.shape, o.fire_et, o.atr_tf, o.or_min, o.day_take, o.cancel_et, o.flat_et) == \
        ("orb", "11:05:00", 5, 5, 1000.0, "13:25", "13:30")
    assert (m.shape, m.fire_et, m.atr_tf, m.off_atr, m.day_take, m.cancel_et, m.flat_et) == \
        ("atr_straddle", "13:30:00", 30, 1.0, 600.0, "15:53", "15:58")
    assert m.size_tiers == [[0, 2], [1000, 3], [2000, 4]] and m.skip_early_close and o.skip_early_close
    assert not f.skip_early_close            # flat at 11:00: a half day is an ordinary morning


def test_the_existing_strategies_are_untouched():
    d = desk_config._defaults().strategies["nq930"]
    assert (d.kind, d.day_take, d.day_lock, d.target_take, d.fee_rt, d.size_tiers) == ("straddle", 0.0, 0.0, False, 4.0, [])
    assert (d.offset_pts, d.sl_pts, d.tp_pts, d.cancel_et, d.flat_et) == (10.0, 5.0, 15.0, "12:55", "15:55")


def test_a_saved_config_round_trips(cfg_path):
    c = desk_config.load()
    c.accounts["eval1"] = AccountCfg(keyring_key="k", account_name="E1",
                                     prop={"rules": "lucid-pro-50k-no-dll@2026-09-27b", "start_balance": 50000,
                                           "largest_day": 0, "days": 0})
    c.strategies["nq_nyam_pro"].enabled = True
    c.book["nq_nyam_pro"] = [{"account": "eval1", "qty": 4}]
    desk_config.save(c)
    back = desk_config.load()
    assert back.accounts["eval1"].prop["start_balance"] == 50000
    assert back.strategies["nq_nyam_pro"].enabled and back.strategies["nq_nyam_pro"].target_take
    assert back.strategies["nq_pm_flex"].size_tiers == [[0, 2], [1000, 3], [2000, 4]]
    assert desk_config.assignments(back, "nq_nyam_pro") == [{"account": "eval1", "qty": 4}]


def test_a_config_written_before_these_fields_still_loads(cfg_path):
    cfg_path.write_text(json.dumps({
        "armed": True,
        "accounts": {"main": {"keyring_key": "k", "account_name": "M"}},
        "book": {"nq930": [{"account": "main", "qty": 3}]},
        "strategies": {"nq930": {"symbol": "NQ", "qty": 3, "offset_pts": 10.0, "sl_pts": 5.0, "tp_pts": 15.0,
                                 "enabled": True}}}))
    c = desk_config.load()
    assert c.armed and c.accounts["main"].prop == {} and c.strategies["nq930"].day_take == 0.0
    assert set(NAMES) <= set(c.strategies)                       # the new strategies appear, off
    assert isinstance(c.strategies["nq_pm_flex"], StrategyCfg)
