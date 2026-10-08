"""What the desk ships (nq930, gc_nfp), the "levels" kind's fields and the accounts' prop standing in config.json;
old files still load."""
from __future__ import annotations

import json

import pytest

from dataclasses import asdict

from homebase import config as desk_config
from homebase.config import AccountCfg, StrategyCfg
from tests.levels_util import NAMES, levels_cfg


@pytest.fixture
def cfg_path(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    monkeypatch.setattr(desk_config, "config_path", lambda: p)
    monkeypatch.setattr(desk_config, "_said", set())           # what a reader already named in the log: per test
    return p


def test_the_desk_ships_only_nq930_and_gc_nfp():
    d = desk_config._defaults()
    assert set(d.strategies) == {"nq930", "gc_nfp"}
    assert not set(NAMES) & set(d.strategies) and not set(NAMES) & set(d.book)
    assert not hasattr(desk_config, "levels_reference")          # the four NQ levels algos are gone, not just unshipped


def test_gc_nfp_is_one_gold_setup_for_nfp_and_cpi_days(cfg_path):
    """2026-10-08: one strategy, id gc_nfp, shown as GC_NFP/CPI; six BLS dates (NFP + CPI), sorted; off and unbooked."""
    for c in (desk_config._defaults(), desk_config.load()):                  # shipped defaults, and as the desk loads them
        s = c.strategies["gc_nfp"]
        assert (s.kind, s.symbol, s.qty, s.offset_pts, s.sl_pts, s.tp_pts, s.rr) == ("straddle", "GC", 4, 2.0, 5.0, 7.7, 0.0)
        assert (s.fire_et, s.cancel_et, s.flat_et, s.accept_from_et, s.accept_until_et) == \
            ("08:29:59", "08:45", "09:55", "08:29", "08:31")
        assert s.only_dates == ["2026-10-02", "2026-10-14", "2026-11-06", "2026-11-10", "2026-12-04", "2026-12-10"]
        assert s.only_dates == sorted(s.only_dates) and len(s.only_dates) == 6
        assert s.label == "GC_NFP/CPI" and s.self_fire
        assert not s.enabled and not s.shadow and "gc_nfp" not in c.book
        assert c.strategies["nq930"].label == ""                             # no label: the page shows the id


def test_a_label_round_trips_and_is_a_known_key(cfg_path, caplog):
    c = desk_config.load()
    c.strategies["gc_nfp"].label = "Gold releases"
    desk_config.save(c)
    assert json.loads(cfg_path.read_text())["strategies"]["gc_nfp"]["label"] == "Gold releases"
    for kw in ({}, {"unknown": "ignore"}):
        assert desk_config.load(**kw).strategies["gc_nfp"].label == "Gold releases"
    assert not [r for r in caplog.records if "label" in r.getMessage()]       # not named as an unknown key
    cfg_path.write_text(json.dumps({"strategies": {"gc_nfp": {"qty": 4}}}))   # a file written before the field
    assert desk_config.load().strategies["gc_nfp"].label == "GC_NFP/CPI"


def test_a_levels_config_survives_its_own_dict():
    """The kind's fields (take rules, size tiers) are all StrategyCfg fields: asdict -> StrategyCfg is lossless."""
    for n in NAMES:
        s = levels_cfg(n)
        assert s.kind == "levels" and not s.enabled and StrategyCfg(**asdict(s)) == s
    assert levels_cfg("lv_atr_target").target_take
    assert levels_cfg("lv_atr_tiers").size_tiers == [[0, 2], [1000, 3], [2000, 4]]


def test_the_existing_strategies_are_untouched():
    d = desk_config._defaults().strategies["nq930"]
    assert (d.kind, d.day_take, d.day_lock, d.target_take, d.fee_rt, d.size_tiers) == ("straddle", 0.0, 0.0, False, 4.0, [])
    assert (d.offset_pts, d.sl_pts, d.tp_pts, d.cancel_et, d.flat_et) == (5.0, 5.0, 15.0, "12:55", "15:55")


def test_a_saved_config_round_trips(cfg_path):
    c = desk_config.load()
    c.accounts["eval1"] = AccountCfg(keyring_key="k", account_name="E1",
                                     prop={"rules": "lucid-pro-50k-no-dll@2026-09-27b", "start_balance": 50000,
                                           "largest_day": 0, "days": 0})
    c.strategies["gc_nfp"].enabled = True
    c.book["gc_nfp"] = [{"account": "eval1", "qty": 4}]
    desk_config.save(c)
    back = desk_config.load()
    assert back.accounts["eval1"].prop["start_balance"] == 50000
    assert back.strategies["gc_nfp"].enabled
    assert desk_config.assignments(back, "gc_nfp") == [{"account": "eval1", "qty": 4}]


def test_a_config_written_before_these_fields_still_loads(cfg_path):
    cfg_path.write_text(json.dumps({
        "armed": True,
        "accounts": {"main": {"keyring_key": "k", "account_name": "M"}},
        "book": {"nq930": [{"account": "main", "qty": 3}]},
        "strategies": {"nq930": {"symbol": "NQ", "qty": 3, "offset_pts": 10.0, "sl_pts": 5.0, "tp_pts": 15.0,
                                 "enabled": True}}}))
    c = desk_config.load()
    assert c.armed and c.accounts["main"].prop == {} and c.strategies["nq930"].day_take == 0.0
    assert set(c.strategies) == {"nq930", "gc_nfp"}              # the shipped ones appear; gc_nfp off
    assert isinstance(c.strategies["gc_nfp"], StrategyCfg) and not c.strategies["gc_nfp"].enabled


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


def test_a_levels_strategy_and_its_book_rows_leave_the_desk_file_on_load(cfg_path):
    """2026-10-08: the four NQ levels algos are no longer shipped, so a file that still holds one is cleaned."""
    cfg_path.write_text(json.dumps({
        "accounts": {"a1": {"keyring_key": "k", "account_name": "A1"}},
        "strategies": {"nq930": {"qty": 3}, "nq_nyam_flex": {"qty": 4, "enabled": True}},
        "book": {"nq930": [{"account": "a1", "qty": 2}], "nq_nyam_flex": [{"account": "a1", "qty": 4}]}}))
    cfg = desk_config.load()
    assert set(cfg.strategies) == {"nq930", "gc_nfp"} and cfg.book == {"nq930": [{"account": "a1", "qty": 2}]}
    saved = json.loads(cfg_path.read_text())
    assert "nq_nyam_flex" not in saved["strategies"] and "nq_nyam_flex" not in saved["book"]


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
    c = desk_config.load()
    c.accounts["eval1"] = AccountCfg(keyring_key="k", account_name="E1", prop={"rules": "x", "start_balance": 50000})
    c.strategies["gc_nfp"].enabled = True
    c.book["gc_nfp"] = [{"account": "eval1", "qty": 4}]
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
