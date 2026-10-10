"""Step B (B1): config.json never holds a Lab strategy. save() leaves kind-lab strategies and their book rows out, a
config with none is written byte for byte as before (the golden file was written by save() as it was BEFORE this change:
tests/fixtures/config_no_lab.golden.json), and the after-save hooks can never break a save."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from homebase import config as desk_config
from homebase import labcfg
from homebase.config import AccountCfg, AppCfg, ChartTradingCfg
from homebase.labrun import store

GOLDEN = Path(__file__).parent / "fixtures" / "config_no_lab.golden.json"


def golden_cfg() -> AppCfg:
    """What the desk holds on an ordinary day: the shipped strategies, three accounts (a live one, a prop one, a paper
    one), two books, chart trading on, an allowed host, armed."""
    c = desk_config._defaults()
    for s in c.strategies.values():
        desk_config.apply_rr(s)
    c.armed = True
    c.accounts = {"main": AccountCfg(keyring_key="tv:live:me", account_name="MAIN1", live=True, label="Main"),
                  "eval1": AccountCfg(keyring_key="tv:demo:apex", account_name="APEX-1", label="Éval 1",
                                      prop={"rules": "lucid-pro-50k@2026-09-27b", "start_balance": 50000, "largest_day": 0, "days": 0}),
                  "paper-5": AccountCfg(paper=True, label="five (paper)", account_name="five")}
    c.book = {"nq930": [{"account": "main", "qty": 3}, {"account": "paper-5", "qty": 1}], "gc_nfp": [{"account": "eval1", "qty": 4}]}
    c.strategies["gc_nfp"].enabled = True
    c.chart_trading = ChartTradingCfg(enabled=True, max_order_qty=5, max_position_qty=10)
    c.allowed_hosts = ["desk.tailnet.ts.net", "100.64.0.7"]
    return c


def lab_rec(name="pp_orb", **kw):
    return {"name": name, "id": f"draft_{name}", "label": "PP ORB", "root": "NQ", "source": "class X: pass\n", "sha256": "ab",
            "params": {}, "qty": 1, "run": {"id": "r1"}, "notes": [], "promoted_utc": "2026-10-09T12:00:00+00:00", "enabled": True,
            "commission": 2.5, "slippage_ticks": 1.0, "session_window": ["09:25", "16:00"], "bar_minutes": 5, **kw}


@pytest.fixture
def cfg_path(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    monkeypatch.setattr(desk_config, "config_path", lambda: p)
    monkeypatch.setattr(desk_config, "_said", set())
    monkeypatch.setattr(desk_config, "_after_save", [])                         # each test names its own hooks
    return p


def with_lab(cfg):
    store.put(lab_rec())
    store.put_desk("pp_orb", {"mark": ["ab", "2026-10-09T12:00:00+00:00"], "book": [{"account": "main", "qty": 1}], "written_utc": "x",
                              "limits": {"max_trades_day": 2, "max_qty": 1, "max_risk_usd": 300, "last_entry_et": "11:00", "flat_et": "15:55"}})
    assert labcfg.overlay(cfg)["added"] == ["lab_pp_orb"]
    return cfg


def test_a_config_with_no_lab_strategy_is_written_byte_for_byte_as_before(cfg_path):
    desk_config.save(golden_cfg())
    assert cfg_path.read_bytes() == GOLDEN.read_bytes()


def test_the_same_bytes_with_the_desks_hook_registered_and_an_empty_store(cfg_path, desklab_root):
    desk_config._after_save.append(labcfg.persist_all)
    cfg = golden_cfg()
    labcfg.overlay(cfg)                                                          # nothing promoted
    desk_config.save(cfg)
    assert cfg_path.read_bytes() == GOLDEN.read_bytes() and list(desklab_root.iterdir()) == []


def test_a_lab_strategy_and_its_book_rows_never_reach_config_json(cfg_path):
    cfg = with_lab(golden_cfg())
    assert cfg.strategies["lab_pp_orb"].kind == "lab" and cfg.book["lab_pp_orb"] == [{"account": "main", "qty": 1}]
    desk_config.save(cfg)
    assert cfg_path.read_bytes() == GOLDEN.read_bytes()                          # the file is what it is without the Lab strategy
    assert "lab_" not in cfg_path.read_text()
    assert cfg.strategies["lab_pp_orb"].kind == "lab" and cfg.book["lab_pp_orb"] == [{"account": "main", "qty": 1}]   # memory untouched


def test_a_book_key_left_behind_by_a_lab_strategy_never_reaches_config_json(cfg_path):
    cfg = golden_cfg()
    cfg.book["lab_gone_one"] = [{"account": "main", "qty": 1}]                   # its strategy is no longer in the config
    desk_config.save(cfg)
    assert cfg_path.read_bytes() == GOLDEN.read_bytes()


def test_the_old_load_finds_nothing_gone_in_a_file_saved_with_a_lab_strategy(cfg_path, caplog):
    desk_config.save(with_lab(golden_cfg()))
    before = cfg_path.read_bytes()
    with caplog.at_level(logging.WARNING, logger="homebase.config"):
        back = desk_config.load()
        desk_config.load(unknown="ignore")                                       # the chart service's and the tick job's way in
    assert not [r for r in caplog.records if "dropped" in r.getMessage() or "left out" in r.getMessage()]
    assert cfg_path.read_bytes() == before                                       # and load() had nothing to clean
    assert set(back.strategies) == {"nq930", "gc_nfp"} and set(back.book) == {"nq930", "gc_nfp"}
    assert json.loads(before)["book"]["nq930"] == [{"account": "main", "qty": 3}, {"account": "paper-5", "qty": 1}]


def test_no_shipped_strategy_is_named_like_a_lab_strategy():
    d = desk_config._defaults()
    assert not [n for n in d.strategies if n.startswith(labcfg.PREFIX)]
    assert not [n for n, s in d.strategies.items() if s.kind == labcfg.LAB]


def test_the_after_save_hooks_get_the_config_that_was_saved_after_the_file_is_whole(cfg_path):
    seen = []
    desk_config._after_save.append(lambda c: seen.append((c, cfg_path.read_bytes())))
    cfg = golden_cfg()
    desk_config.save(cfg)
    assert len(seen) == 1 and seen[0][0] is cfg and seen[0][1] == GOLDEN.read_bytes()


def test_a_hook_that_raises_never_breaks_a_save_and_the_others_still_run(cfg_path, caplog):
    ran = []

    def boom(c):
        raise RuntimeError("the store is on fire")
    desk_config._after_save.extend([boom, lambda c: ran.append(True)])
    with caplog.at_level(logging.WARNING, logger="homebase.config"):
        desk_config.save(golden_cfg())                                           # does not raise
    assert cfg_path.read_bytes() == GOLDEN.read_bytes() and ran == [True]
    assert any("after-save" in r.getMessage() and "on fire" in r.getMessage() for r in caplog.records)


def test_with_no_hook_registered_a_save_is_what_it_always_was(cfg_path):
    assert desk_config._after_save == []
    desk_config.save(golden_cfg())
    assert cfg_path.read_bytes() == GOLDEN.read_bytes() and not list(cfg_path.parent.glob("*.tmp"))


def test_the_desks_hook_writes_the_sidecar_when_the_lab_book_changes(cfg_path):
    desk_config._after_save.append(labcfg.persist_all)
    cfg = with_lab(golden_cfg())
    desk_config.save(cfg)
    assert store.get_desk("pp_orb")["written_utc"] == "x"                        # nothing changed: the sidecar is not rewritten
    cfg.book["lab_pp_orb"] = [{"account": "main", "qty": 1}, {"account": "eval1", "qty": 1}]
    desk_config.save(cfg)
    got = store.get_desk("pp_orb")
    assert got["book"] == [{"account": "main", "qty": 1}, {"account": "eval1", "qty": 1}] and got["written_utc"] != "x"
    assert cfg_path.read_bytes() == GOLDEN.read_bytes()
    # an account that leaves the desk (server._drop_account_locked: unbook everywhere, then save) leaves the sidecar too
    cfg.book["lab_pp_orb"] = [r for r in cfg.book["lab_pp_orb"] if r["account"] != "eval1"]
    desk_config.save(cfg)
    assert store.get_desk("pp_orb")["book"] == [{"account": "main", "qty": 1}]
