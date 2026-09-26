"""Strategy contract + parity with the desk: defaults = the desk's geometry, legs = engine._legs."""
from __future__ import annotations

import datetime as dt
import json
from array import array
from dataclasses import asdict
from pathlib import Path

import pytest

from homebase import config as desk_config
from homebase import timer
from homebase.backtest.engine import Costs, run_session, to_tick
from homebase.backtest.tape import Tape, et_ns
from homebase.engine import Engine
from homebase.gate import trend_gate
from homebase.strategies import REGISTRY, catalog, get
from homebase.strategies.gc_nfpcpi import GCNfpCpi, calendar
from homebase.strategies.nq10am import NQ10am
from homebase.strategies.nq930 import NQ930
from homebase.strategies.straddle import GATE_BARS, MIN_GATE_BARS
from homebase.strategies.ym930 import YM930

GATE_FIX = json.loads((Path(__file__).parent / "fixture_gate_nq2024.json").read_text())


@pytest.fixture(autouse=True)
def desk_file(monkeypatch, tmp_path):
    """Every test reads the desk config from a temp path (absent = frozen defaults)."""
    p = tmp_path / "config.json"
    monkeypatch.setattr(desk_config, "config_path", lambda: p)
    return p


def test_registry_has_the_four_v1_strategies_with_schemas():
    assert set(REGISTRY) == {"nq930", "ym930", "nq10am", "gc_nfpcpi"}
    cat = {c["id"]: c for c in catalog()}
    assert cat["nq930"]["root"] == "NQ" and cat["gc_nfpcpi"]["root"] == "GC"
    assert {i["key"] for i in cat["nq930"]["inputs"]} == {"offset_pts", "sl_pts", "tp_pts",
                                                         "adx_gate", "adx_min"}
    assert cat["nq10am"]["inputs"] == []
    with pytest.raises(ValueError, match="unknown strategy"):
        get("nope")


@pytest.mark.parametrize("cls", [NQ930, YM930])
def test_straddle_defaults_equal_the_desk_geometry(cls):
    cfg = desk_config.load().strategies[cls.desk_key]
    s = cls()
    assert (s.p["offset_pts"], s.p["sl_pts"], s.p["tp_pts"]) == (cfg.offset_pts, cfg.sl_pts, cfg.tp_pts)
    assert s.p["adx_gate"] == cfg.gated and s.p["adx_min"] == 20.0
    assert s.times() == ["09:30:00", cfg.cancel_et, cfg.flat_et] == ["09:30:00", "12:55", "15:55"]
    assert cls.root == cfg.symbol and s.placement_ms == 85


def test_defaults_follow_the_desk_config_file(desk_file):
    desk_file.write_text(json.dumps({"strategies": {"nq930": {"offset_pts": 5.0, "gated": False,
                                                              "flat_et": "15:50"}}}))
    s = NQ930()
    assert s.p["offset_pts"] == 5.0 and s.p["adx_gate"] is False and s.flat_et == "15:50"


# Item 4 (provenance): every strategy's runtime config -- as it actually resolved,
# not just its `inputs` -- must be reproducible from what a run stores.

@pytest.mark.parametrize("cls", [NQ930, YM930])
def test_desk_straddle_provenance_carries_times_and_the_full_desk_cfg(cls, desk_file):
    desk_file.write_text(json.dumps({"strategies": {cls.desk_key: {"flat_et": "15:50"}}}))
    cfg = desk_config.load().strategies[cls.desk_key]
    s = cls()
    prov = s.provenance()
    assert (prov["fire"], prov["cancel_et"], prov["flat_et"]) == ("09:30:00", cfg.cancel_et, "15:50")
    assert prov["desk_cfg"] == asdict(cfg)


def test_gc_provenance_carries_its_own_times_with_no_desk_cfg():
    prov = GCNfpCpi().provenance()
    assert prov == {"fire": "08:30:00", "cancel_et": "08:45", "flat_et": "09:55"}


def test_nq10am_provenance_carries_the_rule_and_the_full_desk_cfg(desk_file):
    desk_file.write_text(json.dumps({"strategies": {"nq10am": {"flat_et": "15:50"}}}))
    cfg = desk_config.load().strategies["nq10am"]
    prov = NQ10am().provenance()
    assert prov["flat_et"] == "15:50" == cfg.flat_et
    assert prov["rule"] == "nq_10am_continuation" == cfg.rule
    assert prov["desk_cfg"] == asdict(cfg)


@pytest.mark.parametrize("cls", [NQ930, YM930])
@pytest.mark.parametrize("anchor", [18250.0, 18250.25, 41000.0, 99.75])
def test_legs_equal_the_desk_engine_legs(cls, anchor):
    cfg = desk_config.load().strategies[cls.desk_key]
    s = cls()
    desk = Engine._legs(cfg, anchor + cfg.offset_pts, anchor - cfg.offset_pts, 2)
    ours = s.legs(anchor)
    assert [(("long" if r.side == "Buy" else "short"), r.price, r.stop_price, r.tp_price) for r in desk] \
        == [(g.side, g.trigger, g.sl, g.tp) for g in ours]
    assert all(r.order_type == "Stop" for r in desk)


def test_gate_constants_equal_the_desk_timer():
    assert (MIN_GATE_BARS, GATE_BARS) == (timer.MIN_GATE_BARS, timer.GATE_BARS)


def _tape(root, d, rows):
    ts, px = array("q"), array("d")
    for t, p in rows:
        hms, _, ms = t.partition(".")
        ts.append(et_ns(d, hms) + int(ms or 0) * 1_000_000)
        px.append(p)
    return Tape(root, d, "X", ts, px, array("i", [1] * len(ts)), {})


def test_trend_gate_runs_on_completed_daily_bars():
    d = dt.date(2024, 12, 31)
    tp = _tape("NQ", d, [("09:29:59", 100.0), ("09:30:01", 111.0), ("09:31", 140.0)])
    s = NQ930({"adx_gate": True})
    res = run_session(s, tp, Costs(), daily=GATE_FIX["bars"][:100])
    assert res.trades == [] and "unknown" in res.skip
    ok, adx = trend_gate(GATE_FIX["bars"][-GATE_BARS:])
    assert ok is True
    res = run_session(NQ930({"adx_gate": True}), tp, Costs(), daily=GATE_FIX["bars"])
    assert len(res.trades) == 1
    res = run_session(NQ930({"adx_gate": True, "adx_min": 30.0}), tp, Costs(), daily=GATE_FIX["bars"])
    assert res.trades == [] and res.skip.startswith("trend gate: ADX 22.42")


def test_gc_defaults_are_the_research_spec_and_it_trades_nfp_cpi_days_only():
    s = GCNfpCpi()
    assert (s.p["offset_pts"], s.p["sl_pts"], s.p["tp_pts"], s.p["events"]) == (2.0, 3.0, 6.0, "NFP+CPI")
    assert s.times() == ["08:30:00", "08:45", "09:55"] and s.session_window == ("08:20", "09:56")
    cal = calendar()
    assert cal[dt.date(2024, 1, 5)] == {"NFP"} and cal[dt.date(2024, 1, 11)] == {"CLAIMS", "CPI"}
    assert s.trades_on(dt.date(2024, 1, 5)) and s.trades_on(dt.date(2024, 1, 11))
    assert not s.trades_on(dt.date(2024, 1, 12))                    # PPI only
    assert not GCNfpCpi({"events": "NFP"}).trades_on(dt.date(2024, 1, 11))
    assert max(cal) >= dt.date(2026, 9, 1)                          # 2025-26 events for holdout runs


def test_gc_trade_through_the_engine():
    d = dt.date(2024, 1, 5)
    tp = _tape("GC", d, [("08:29:59", 2050.0), ("08:30:00.100", 2052.3), ("08:31", 2058.5)])
    t, = run_session(GCNfpCpi(), tp, Costs()).trades
    assert t.side == "long" and t.entry_price == 2052.4 and t.tp == 2058.4
    assert t.exit_reason == "tp" and t.net == round(6.0 * 100 - 4.0, 2)


def test_nq10am_uses_the_desk_rule_and_config():
    cfg = desk_config.load().strategies["nq10am"]
    s = NQ10am()
    assert s.rule.__name__ == cfg.rule == "nq_10am_continuation"
    assert s.bar_minutes == cfg.bar_minutes == 1 and s.times() == [cfg.flat_et]


def test_nq10am_trades_the_rule_signal_at_the_10am_open():
    d = dt.date(2024, 3, 5)
    rows = [(f"09:{30 + i}:10", 100.0 + i) for i in range(30)]       # 30 rising 1-min bars
    rows += [("10:00:00.090", 130.0), ("10:10", 200.0)]
    t, = run_session(NQ10am(), _tape("NQ", d, rows), Costs()).trades
    assert t.side == "long" and t.entry_price == 130.25              # market + 1 tick slip
    assert t.sl == 100.0                                            # the candle's low, absolute
    assert t.tp == to_tick(130.25 + 0.75 * (130.25 - 100.0), 0.25) == 153.0   # RR 1:0.75 from the FILL
    assert t.exit_reason == "tp"


def test_no_print_before_fire_skips_cleanly_not_a_strategy_error():
    """Engine amendment: a strategy exception now skips with 'strategy error: <msg>'.
    The straddles must not rely on that path -- they check ctx.last_price
    themselves and skip with a clean reason at the event time."""
    d = dt.date(2024, 12, 31)
    tp = _tape("NQ", d, [("09:30:01", 111.0), ("09:31", 140.0)])   # no print before 09:30:00
    res = run_session(NQ930({"adx_gate": False}), tp, Costs())
    assert res.trades == []
    assert res.skip == "no print before 09:30:00"
    assert not res.skip.startswith("strategy error")
