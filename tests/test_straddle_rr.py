"""A straddle's target as a multiple of its stop (StrategyCfg.rr): config.load derives tp_pts, config.json keeps the
key, and POST /api/strategy-rr is the owner's way to change it (not 09:20-09:35 ET, not with orders or a position)."""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest

from homebase import config as desk_config
from homebase.config import StrategyCfg
from tests.levels_util import levels_cfg
from tests.test_server import client  # noqa: F401  (the desk fixture)

ET = ZoneInfo("America/New_York")


@pytest.fixture
def cfg_path(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    monkeypatch.setattr(desk_config, "config_path", lambda: p)
    monkeypatch.setattr(desk_config, "_said", set())
    return p


# ---- config: rr -> tp_pts ------------------------------------------------------------------------------
def test_nq930_ships_a_1_to_3_target_and_gc_nfp_keeps_its_points():
    d = desk_config._defaults().strategies
    assert (d["nq930"].rr, d["nq930"].sl_pts, d["nq930"].tp_pts) == (3.0, 5.0, 15.0)
    assert (d["gc_nfp"].rr, d["gc_nfp"].tp_pts) == (0.0, 7.7)


def test_load_without_a_file_derives_the_target_from_the_stop(cfg_path):
    c = desk_config.load()
    assert c.strategies["nq930"].tp_pts == 15.0 and c.strategies["gc_nfp"].tp_pts == 7.7


def test_load_sets_tp_pts_from_rr_over_the_saved_points(cfg_path):
    cfg_path.write_text(json.dumps({"strategies": {"nq930": {"rr": 2.0, "tp_pts": 99.0}}}))
    s = desk_config.load().strategies["nq930"]
    assert (s.rr, s.tp_pts) == (2.0, 10.0)


def test_load_rounds_the_derived_target_to_four_places(cfg_path):
    cfg_path.write_text(json.dumps({"strategies": {"nq930": {"rr": 2.333333, "sl_pts": 5.0}}}))
    assert desk_config.load().strategies["nq930"].tp_pts == round(5.0 * 2.333333, 4) == 11.6667


def test_rr_zero_uses_tp_pts_as_written(cfg_path):
    cfg_path.write_text(json.dumps({"strategies": {"nq930": {"rr": 0.0, "tp_pts": 20.0},
                                                   "gc_nfp": {"tp_pts": 9.0}}}))
    c = desk_config.load()
    assert (c.strategies["nq930"].rr, c.strategies["nq930"].tp_pts) == (0.0, 20.0)
    assert c.strategies["gc_nfp"].tp_pts == 9.0                       # no rr: a hand-edited target stays


def test_a_config_written_before_rr_gets_the_shipped_1_to_3(cfg_path):
    """The saved 15-point target and the shipped rr 3 agree; a different saved target gives way to rr."""
    cfg_path.write_text(json.dumps({"strategies": {"nq930": {"tp_pts": 15.0}}}))
    assert desk_config.load().strategies["nq930"].tp_pts == 15.0
    cfg_path.write_text(json.dumps({"strategies": {"nq930": {"tp_pts": 20.0}}}))
    assert desk_config.load().strategies["nq930"].tp_pts == 15.0


def test_rr_round_trips_through_save_and_both_loaders(cfg_path):
    c = desk_config.load()
    c.strategies["nq930"].rr = 2.5
    c.strategies["nq930"].tp_pts = 12.5
    desk_config.save(c)
    assert json.loads(cfg_path.read_text())["strategies"]["nq930"]["rr"] == 2.5
    for kw in ({}, {"unknown": "ignore"}):
        s = desk_config.load(**kw).strategies["nq930"]
        assert (s.rr, s.tp_pts) == (2.5, 12.5)


def test_rr_is_a_known_key_so_the_chart_service_does_not_name_it(cfg_path, caplog):
    cfg_path.write_text(json.dumps({"strategies": {"nq930": {"rr": 4.0}}}))
    with caplog.at_level("WARNING", logger="homebase.config"):
        desk_config.load(unknown="ignore")
    assert not [r for r in caplog.records if "rr" in r.getMessage()]


def test_only_a_straddle_takes_its_target_from_rr():
    lv = levels_cfg("lv_atr_take", rr=3.0, sl_pts=5.0, tp_pts=1.0)
    assert desk_config.apply_rr(lv).tp_pts == 1.0
    st = StrategyCfg(symbol="NQ", qty=1, offset_pts=1.0, sl_pts=4.0, tp_pts=1.0, rr=1.5)
    assert desk_config.apply_rr(st).tp_pts == 6.0


# ---- POST /api/strategy-rr ------------------------------------------------------------------------------
def post(c, **body):
    return c.post("/api/strategy-rr", json=body)


def test_a_valid_change_sets_rr_and_the_target_saves_and_journals(client):          # noqa: F811
    r = post(client, strategy="nq930", rr=2)
    assert r.status_code == 200 and r.json() == {"ok": True, "strategy": "nq930", "rr": 2.0, "tp_pts": 10.0}
    s = client.app.state.cfg.strategies["nq930"]
    assert (s.rr, s.tp_pts) == (2.0, 10.0)
    saved = json.loads(desk_config.config_path().read_text())["strategies"]["nq930"]
    assert (saved["rr"], saved["tp_pts"]) == (2.0, 10.0)
    ev = [json.loads(x) for x in (desk_config.config_path().parent / "journal.jsonl").read_text().splitlines()]
    ev, = [e for e in ev if e["event"] == "strategy_rr_changed"]
    assert (ev["strategy"], ev["rr"], ev["tp_pts"], ev["previous"]) == ("nq930", 2.0, 10.0, {"rr": 0.0, "tp_pts": 15.0})
    assert client.get("/api/status").json()["strategies"]["nq930"]["cfg"]["rr"] == 2.0


def test_the_bounds_are_0_25_to_20(client):                                         # noqa: F811
    for rr, code in ((0.25, 200), (20, 200), (0.2, 400), (20.5, 400), (0, 400), (-1, 400)):
        assert post(client, strategy="nq930", rr=rr).status_code == code, rr
    for bad in ("3", None, True, [3], {"x": 1}):
        assert post(client, strategy="nq930", rr=bad).status_code == 400, bad
    assert post(client, strategy="nq930").status_code == 400
    assert client.app.state.cfg.strategies["nq930"].rr == 20.0              # the last good one stands


def test_an_unknown_strategy_is_404(client):                                        # noqa: F811
    assert post(client, strategy="nope", rr=2).status_code == 404
    assert post(client, rr=2).status_code == 404


def test_only_a_straddle_with_a_stop_can_be_changed(client):                         # noqa: F811
    cfg = client.app.state.cfg
    cfg.strategies["lv"] = levels_cfg("lv_atr_take")
    cfg.strategies["nostop"] = dataclasses.replace(cfg.strategies["nq930"], sl_pts=0.0)
    assert post(client, strategy="lv", rr=2).status_code == 400
    assert post(client, strategy="nostop", rr=2).status_code == 400
    assert cfg.strategies["lv"].rr == 0.0 and cfg.strategies["nostop"].rr == 0.0


@pytest.mark.parametrize("hm,code", [((9, 19), 200), ((9, 20), 409), ((9, 34), 409), ((9, 35), 200)])
def test_refused_inside_the_930_window_on_a_weekday(client, hm, code):             # noqa: F811
    client.app.state.engine.now_et = lambda: dt.datetime(2026, 9, 30, *hm, tzinfo=ET)       # a Wednesday
    r = post(client, strategy="nq930", rr=2)
    assert r.status_code == code
    if code == 409:
        assert "09:20-09:35" in r.json()["detail"] and client.app.state.cfg.strategies["nq930"].rr == 0.0


def test_the_weekend_is_not_quiet(client):                                          # noqa: F811
    client.app.state.engine.now_et = lambda: dt.datetime(2026, 10, 3, 9, 30, tzinfo=ET)     # a Saturday
    assert post(client, strategy="nq930", rr=2).status_code == 200


@pytest.mark.parametrize("status", ["placing", "placed", "live", "error"])
def test_refused_while_the_strategy_has_orders_or_a_position_today(client, status):  # noqa: F811
    client.app.state.engine._state("nq930", "main").status = status
    r = post(client, strategy="nq930", rr=2)
    assert r.status_code == 409 and "orders or a position" in r.json()["detail"]
    assert client.app.state.cfg.strategies["nq930"].rr == 0.0


@pytest.mark.parametrize("status", ["idle", "done"])
def test_an_idle_or_finished_day_does_not_block_it(client, status):                 # noqa: F811
    client.app.state.engine._state("nq930", "main").status = status
    assert post(client, strategy="nq930", rr=2).status_code == 200


def test_yesterdays_position_does_not_block_it(client):                             # noqa: F811
    st = client.app.state.engine._state("nq930", "main")
    st.status, st.date = "live", "2026-09-29"
    assert post(client, strategy="nq930", rr=2).status_code == 200


# ---- the display label ------------------------------------------------------------------------------------
def test_status_and_readiness_show_the_label_while_ids_stay_ids(client):            # noqa: F811
    cfg = client.app.state.cfg
    cfg.strategies["nq930"].label = "NQ nine-thirty"
    d = client.get("/api/status").json()
    assert d["strategies"]["nq930"]["cfg"]["label"] == "NQ nine-thirty" and "nq930" in d["strategies"]
    assert cfg.book["nq930"] == [{"account": "main", "qty": 3}]                    # the book keeps the id
    cfg.book["nq930"] = []
    labels = [c["label"] for c in client.get("/api/status").json()["readiness"]["checks"]]
    assert "NQ nine-thirty" in labels and "nq930" not in labels
