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
    monkeypatch.setattr(desk_config, "_said", set())           # what a reader already named in the log: per test
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


def test_load_drops_removed_strategies_and_their_book_rows(cfg_path, caplog):
    """A strategy with no shipped default (ym930, nq10am, nq_open_*) leaves config.json on load: its entry
    and its book rows vanish, a booking on a kept strategy stays, and the drop is logged."""
    cfg_path.write_text(json.dumps({
        "accounts": {"a1": {"keyring_key": "k", "account_name": "A1"}},
        "strategies": {"nq930": {"qty": 3}, "ym930": {"qty": 1}, "nq_open_long": {"qty": 1}},
        "book": {"nq930": [{"account": "a1", "qty": 2}], "ym930": [],
                 "nq_open_long": [{"account": "a1", "qty": 35}], "nq10am": [{"account": "a1", "qty": 1}]}}))
    with caplog.at_level("WARNING", logger="homebase.config"):
        cfg = desk_config.load()
    assert not {"ym930", "nq10am", "nq_open_long", "nq_open_short"} & set(cfg.strategies)
    assert cfg.book == {"nq930": [{"account": "a1", "qty": 2}]}
    said = " ".join(r.getMessage() for r in caplog.records)
    assert "ym930" in said and "nq_open_long" in said and "nq10am" in said and "35" not in said
    saved = json.loads(cfg_path.read_text())
    assert "ym930" not in saved["strategies"] and "nq_open_long" not in saved["book"]


# ---- a key this code does not know (2026-10-01: the desk, restarted on new code, wrote accounts with a "prop"
# key; the chart service, still on the older code, raised on every reconnect for two hours)
NEWER = {"accounts": {"a1": {"keyring_key": "k", "account_name": "A1", "live": True, "margin_tier": {"secret": 7}}},
         "strategies": {"nq930": {"qty": 3, "new_switch": True}},
         "book": {"nq930": [{"account": "a1", "qty": 2}]}}


def test_the_desk_still_refuses_a_file_it_only_half_understands(cfg_path):
    """Unchanged, on purpose: the unknown key may be a safety switch (shadow, only_dates), and the desk
    rewrites this file -- it would erase the key."""
    cfg_path.write_text(json.dumps(NEWER))
    before = cfg_path.read_bytes()
    with pytest.raises(TypeError, match="margin_tier"):
        desk_config.load()
    assert cfg_path.read_bytes() == before


def test_a_reader_leaves_out_the_key_it_does_not_know_and_names_it_once(cfg_path, caplog):
    cfg_path.write_text(json.dumps(NEWER))
    before = cfg_path.read_bytes()
    with caplog.at_level("WARNING", logger="homebase.config"):
        cfg = desk_config.load(unknown="ignore")
        desk_config.load(unknown="ignore")
    a = cfg.accounts["a1"]
    assert (a.keyring_key, a.account_name, a.live, a.prop) == ("k", "A1", True, {})
    assert cfg.strategies["nq930"].qty == 3 and cfg.book == {"nq930": [{"account": "a1", "qty": 2}]}
    said = [r.getMessage() for r in caplog.records]
    assert len(said) == 2 and "margin_tier" in said[0] and "new_switch" in said[1]      # each key once, not per load
    assert "secret" not in " ".join(said) and "7" not in " ".join(said)                  # the key, never its value
    assert cfg_path.read_bytes() == before


def test_a_reader_that_left_a_key_out_never_rewrites_the_file(cfg_path, caplog):
    """load() cleans a removed strategy out of the file. A reader that understood only part of the file must not:
    its copy of the settings lacks the key it left out, and writing it back would erase that key."""
    body = {**NEWER, "strategies": {**NEWER["strategies"], "ym930": {"qty": 1}}}
    cfg_path.write_text(json.dumps(body))
    before = cfg_path.read_bytes()
    with caplog.at_level("WARNING", logger="homebase.config"):
        cfg = desk_config.load(unknown="ignore")
    assert "ym930" not in cfg.strategies and cfg_path.read_bytes() == before
    assert any("not rewritten" in r.getMessage() for r in caplog.records)
    del body["accounts"]["a1"]["margin_tier"], body["strategies"]["nq930"]["new_switch"]
    cfg_path.write_text(json.dumps(body))                          # nothing unknown: the reader cleans it as ever
    desk_config.load(unknown="ignore")
    assert "ym930" not in json.loads(cfg_path.read_text())["strategies"]


def test_with_nothing_unknown_both_ways_of_loading_give_the_same_settings(cfg_path):
    from dataclasses import asdict
    c = desk_config.load()
    c.accounts["eval1"] = AccountCfg(keyring_key="k", account_name="E1", prop={"rules": "x", "start_balance": 50000})
    c.strategies["nq_nyam_pro"].enabled = True
    c.book["nq_nyam_pro"] = [{"account": "eval1", "qty": 4}]
    desk_config.save(c)
    assert asdict(desk_config.load()) == asdict(desk_config.load(unknown="ignore"))


def test_the_chart_service_and_the_tick_job_find_their_login_in_a_file_with_a_key_they_do_not_know(
        cfg_path, tmp_path, monkeypatch):
    import datetime as dt

    from homebase import ticks as T
    cfg_path.write_text(json.dumps(NEWER))
    monkeypatch.setattr(T, "state_dir", lambda: tmp_path)
    exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat()
    (tmp_path / "a1.tokens.json").write_text(json.dumps({"md_access_token": "tok", "expiration_time": exp}))
    assert T.md_token() == ("tok", "live") and T.accounts_by_env() == {"live": "A1", "demo": None}
