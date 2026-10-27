"""The "Backtest metrics" record of a strategy (StrategyCfg.metrics, display-only) and /api/research-equity.

The desk ships no strategy since 2026-10-20 (nq930 and gc_nfp, the two that carried a record and an equity
artifact, are Lab strategies now), so the tests that pinned their records and artifacts are gone. What stays:
the endpoint's answer for a strategy it does not know, and config.load's overlay of a saved metrics copy on a
shipped one (a pointer the defaults gained later, a saved pointer, a corrected record with a higher "rev"),
run on a stand-in shipped strategy."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import homebase.config as config_mod
from homebase.server import create_app

# ---- the endpoint ----------------------------------------------------------------------------------
@pytest.fixture
def desk(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.desk.engine.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.server.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.store.secrets_store.state_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    app = create_app(config_mod._defaults(), {}, background=False)        # disarmed, no account, nothing booked
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        yield c


def test_research_equity_has_nothing_for_an_unknown_strategy(desk):
    assert desk.get("/api/research-equity", params={"strategy": "nope"}).json() == {"points": None}


# ---- config.json must not hide the pointer -------------------------------------------------------------
SHIPPED = {"source": "a shipped research record", "rows": {"trades": "10", "WR": "50%"}, "rev": 3,
           "caveat": "a caveat", "equity_file": "s1_equity.json"}


@pytest.fixture
def cfg_path(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "config_path", lambda: p)
    monkeypatch.setattr(config_mod, "_defaults", lambda: config_mod.AppCfg(strategies={"s1": config_mod.StrategyCfg(
        symbol="NQ", qty=3, offset_pts=5.0, sl_pts=5.0, tp_pts=15.0, metrics=json.loads(json.dumps(SHIPPED)))}))
    return p


def test_a_config_saved_before_the_pointer_still_gets_it(cfg_path):
    """config.json holds each strategy's whole metrics dict (save() writes it).  One written before equity_file
    existed must not shadow the default's pointer after a restart; what the file does say stays."""
    m = {k: v for k, v in SHIPPED.items() if k != "equity_file"}
    m["source"] = "edited by hand"
    cfg_path.write_text(json.dumps({"armed": False, "strategies": {"s1": {"qty": 3, "enabled": False, "metrics": m}}}))
    cfg = config_mod.load()
    assert cfg.strategies["s1"].metrics["equity_file"] == "s1_equity.json"
    assert cfg.strategies["s1"].metrics["source"] == "edited by hand"                  # the file's own keys win
    assert cfg.strategies["s1"].metrics["rows"] == SHIPPED["rows"]
    config_mod.save(cfg)                                                   # and the next save carries the pointer
    assert json.loads(cfg_path.read_text())["strategies"]["s1"]["metrics"]["equity_file"] == "s1_equity.json"
    assert config_mod.load().strategies["s1"].metrics["source"] == "edited by hand"


def test_a_saved_pointer_wins_over_the_default(cfg_path):
    cfg_path.write_text(json.dumps({"strategies": {"s1": {"metrics": {"rev": 3, "equity_file": ""}}}}))
    cfg = config_mod.load()
    assert cfg.strategies["s1"].metrics["equity_file"] == ""              # switched off by hand: stays off
    assert cfg.strategies["s1"].metrics["caveat"] == "a caveat"           # the rest comes from the defaults


def test_a_saved_strategy_without_metrics_keeps_the_defaults(cfg_path):
    cfg_path.write_text(json.dumps({"strategies": {"s1": {"qty": 2}}}))
    cfg = config_mod.load()
    assert cfg.strategies["s1"].qty == 2
    assert cfg.strategies["s1"].metrics == SHIPPED


def test_a_corrected_record_replaces_the_copy_saved_before_the_correction(cfg_path):
    """A shipped record carries "rev"; a saved copy with a lower rev is the stale text and must not shadow the
    correction."""
    stale = {**SHIPPED, "rows": {**SHIPPED["rows"], "WR": "old"}, "caveat": "old"}
    stale.pop("rev")
    cfg_path.write_text(json.dumps({"strategies": {"s1": {"qty": 4, "enabled": True, "metrics": stale}}}))
    cfg = config_mod.load()
    assert cfg.strategies["s1"].metrics == SHIPPED
    assert cfg.strategies["s1"].enabled is True and cfg.strategies["s1"].qty == 4   # only the record changes
    config_mod.save(cfg)
    cfg.strategies["s1"].metrics["source"] = "edited by hand"             # a later hand edit (same rev) still wins
    config_mod.save(cfg)
    assert config_mod.load().strategies["s1"].metrics["source"] == "edited by hand"
