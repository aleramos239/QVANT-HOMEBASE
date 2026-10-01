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


def test_registry_has_the_v1_strategies_with_schemas():
    assert set(REGISTRY) == {"nq930", "ym930", "nq10am", "gc_nfpcpi", "gc_nfp"}
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


# ---------------------------------------------------------------- rule geometry (2026-09-27)
#
# A run records what the strategy DECIDED, not only what filled: the anchor, both entry offsets,
# each leg's planned bracket, the bracket as it moved to the actual fill, and a " (not filled)"
# mark on the leg that never triggered. Recording only -- every number a run reports is pinned
# byte-identical by tests/test_backtest_golden.py::test_the_2021_2024_research_run_is_byte_identical.

STRADDLE = {"offset_pts": 5.0, "sl_pts": 5.0, "tp_pts": 15.0, "adx_gate": False}


def _geo(res):
    return [(h["name"], h["price"], h["role"]) for h in res.hlines]


def test_straddle_records_the_whole_plan_and_marks_the_leg_that_filled():
    d = dt.date(2024, 12, 31)
    tp = _tape("NQ", d, [("09:29:59", 100.0), ("09:30:01", 106.0), ("09:31", 125.0)])
    res = run_session(NQ930(STRADDLE), tp, Costs())
    t, = res.trades
    assert (t.side, t.entry_price, t.sl, t.tp) == ("long", 106.25, 101.25, 121.25)
    assert _geo(res) == [
        ("anchor", 100.0, "anchor"),
        ("Long entry +5", 105.0, "entry"),
        ("Short entry −5 (not filled)", 95.0, "entry"),
        ("Long SL (planned)", 100.0, "sl"),
        ("Long TP (planned)", 120.0, "tp"),
        ("Short SL (not filled)", 100.0, "sl"),
        ("Short TP (not filled)", 80.0, "tp"),
        ("Long SL", 101.25, "sl"),            # the bracket AS IT MOVED to the fill (desk _move_brackets)
        ("Long TP", 121.25, "tp"),
    ]


def test_straddle_records_the_short_leg_when_that_is_the_one_that_fills():
    d = dt.date(2024, 12, 31)
    tp = _tape("NQ", d, [("09:29:59", 100.0), ("09:30:01", 94.0), ("09:31", 75.0)])
    res = run_session(NQ930(STRADDLE), tp, Costs())
    t, = res.trades
    assert (t.side, t.entry_price, t.sl, t.tp) == ("short", 93.75, 98.75, 78.75)
    assert _geo(res) == [
        ("anchor", 100.0, "anchor"),
        ("Long entry +5 (not filled)", 105.0, "entry"),
        ("Short entry −5", 95.0, "entry"),
        ("Long SL (not filled)", 100.0, "sl"),
        ("Long TP (not filled)", 120.0, "tp"),
        ("Short SL (planned)", 100.0, "sl"),
        ("Short TP (planned)", 80.0, "tp"),
        ("Short SL", 98.75, "sl"),
        ("Short TP", 78.75, "tp"),
    ]


def test_straddle_marks_both_legs_not_filled_on_a_day_neither_triggers():
    d = dt.date(2024, 12, 31)
    tp = _tape("NQ", d, [("09:29:59", 100.0), ("09:30:01", 101.0), ("09:31", 99.0)])
    res = run_session(NQ930(STRADDLE), tp, Costs())
    assert res.trades == []
    assert [n for n, _, _ in _geo(res)] == [
        "anchor", "Long entry +5 (not filled)", "Short entry −5 (not filled)",
        "Long SL (not filled)", "Long TP (not filled)",
        "Short SL (not filled)", "Short TP (not filled)"]


def test_a_skipped_session_records_no_levels_at_all():
    d = dt.date(2024, 12, 31)
    tp = _tape("NQ", d, [("09:30:01", 111.0), ("09:31", 140.0)])       # no print before 09:30
    res = run_session(NQ930(STRADDLE), tp, Costs())
    assert res.skip == "no print before 09:30:00" and res.hlines == []
    res = run_session(NQ930({**STRADDLE, "adx_gate": True}),
                      _tape("NQ", d, [("09:29:59", 100.0), ("09:31", 140.0)]), Costs(),
                      daily=GATE_FIX["bars"][:100])
    assert res.skip and res.hlines == []


def test_the_offset_in_the_label_is_the_strategys_own():
    d = dt.date(2024, 12, 31)
    tp = _tape("NQ", d, [("09:29:59", 100.0), ("09:31", 100.25)])
    res = run_session(NQ930({**STRADDLE, "offset_pts": 12.25}), tp, Costs())
    assert [n for n, _, _ in _geo(res)][1:3] == ["Long entry +12.25 (not filled)",
                                                 "Short entry −12.25 (not filled)"]


def test_gc_inherits_the_geometry_and_names_its_event_day_on_the_anchor():
    d = dt.date(2024, 1, 5)                                            # NFP
    tp = _tape("GC", d, [("08:29:59", 2050.0), ("08:30:00.100", 2052.3), ("08:31", 2058.5)])
    res = run_session(GCNfpCpi(), tp, Costs())
    assert _geo(res)[0] == ("anchor · NFP", 2050.0, "anchor")
    assert [n for n, _, _ in _geo(res)][1:] == [
        "Long entry +2", "Short entry −2 (not filled)",
        "Long SL (planned)", "Long TP (planned)",
        "Short SL (not filled)", "Short TP (not filled)", "Long SL", "Long TP"]


def test_nq10am_records_signal_stop_target_and_plots_its_gate():
    d = dt.date(2024, 3, 5)
    rows = [(f"09:{30 + i}:10", 100.0 + i) for i in range(30)]
    rows += [("10:00:00.090", 130.0), ("10:10", 200.0)]
    res = run_session(NQ10am(), _tape("NQ", d, rows), Costs())
    assert _geo(res) == [("signal", 129.0, "entry"), ("stop", 100.0, "sl"), ("target", 150.75, "tp")]
    assert list(res.plots) == ["Close position", "Top quarter", "Bottom quarter"]
    [[_, pos]] = res.plots["Close position"]
    assert pos == 1.0                                                   # the 09:59 close IS the high
    assert [v for _, v in res.plots["Top quarter"]] == [0.75]
    assert [v for _, v in res.plots["Bottom quarter"]] == [0.25]


def test_nq10am_plots_the_gate_even_on_a_day_the_gate_refuses():
    d = dt.date(2024, 3, 5)
    rows = [(f"09:{30 + i}:10", 100.0 + i) for i in range(29)] + [("09:59:10", 100.5)]
    rows += [("10:00:00.090", 100.0), ("10:10", 100.0)]
    res = run_session(NQ10am(), _tape("NQ", d, rows), Costs())
    assert res.trades == [] and res.hlines == []
    [[_, pos]] = res.plots["Close position"]
    assert pos == round(0.5 / 28.0, 4)                                  # close near the LOW: no long


# ---------------------------------------------------------------- display only: the gate on the chart (2026-09-29)
#
# The straddle plots the ADX reading its gate judged (and the line it judged it against) once per
# session, at the fire. Plots and level timestamps are DISPLAY: nothing a run trades or reports may
# move because of them. The proof is a run with every plot/hline call turned into a no-op -- the
# pre-change behaviour -- compared trade for trade and number for number.

def _gate_day(min_adx, gate=True):
    d = dt.date(2024, 12, 31)
    tp = _tape("NQ", d, [("09:29:59", 100.0), ("09:30:01", 111.0), ("09:31", 140.0), ("09:40", 90.0)])
    return run_session(NQ930({**STRADDLE, "adx_gate": gate, "adx_min": min_adx}), tp, Costs(),
                       daily=GATE_FIX["bars"])


def test_straddle_plots_the_adx_its_gate_judged_and_the_threshold_it_judged_it_against():
    ok, adx = trend_gate(GATE_FIX["bars"][-GATE_BARS:], 20.0)
    for min_adx in (20.0, 99.0):                       # a gate that lets the day trade, and one that refuses it
        res = _gate_day(min_adx)
        fire = et_ns(dt.date(2024, 12, 31), "09:30:00") // 1_000_000
        assert res.plots == {"ADX(14)": [[fire, adx]], "ADX gate min": [[fire, min_adx]]}
    assert _gate_day(99.0).skip and _gate_day(99.0).trades == []
    assert _gate_day(20.0, gate=False).plots == {}     # gate off: nothing to show, nothing plotted


def test_the_adx_gate_is_not_plotted_when_it_cannot_be_read():
    d = dt.date(2024, 12, 31)
    tp = _tape("NQ", d, [("09:29:59", 100.0), ("09:31", 140.0)])
    res = run_session(NQ930({"adx_gate": True}), tp, Costs(), daily=GATE_FIX["bars"][:100])
    assert res.plots == {} and "unknown" in res.skip


def test_a_level_records_when_it_was_placed_and_where_its_session_window_ends():
    d = dt.date(2024, 12, 31)
    tp = _tape("NQ", d, [("09:29:59", 100.0), ("09:30:01", 106.0), ("09:31", 125.0)])
    res = run_session(NQ930(STRADDLE), tp, Costs())
    fire, close = (et_ns(d, t) // 1_000_000 for t in ("09:30:00", "16:00"))
    fill = et_ns(d, "09:30:01") // 1_000_000
    by = {h["name"]: h["t_ms"] for h in res.hlines}
    assert by["anchor"] == fire and by["Long SL (planned)"] == fire     # placed at the fire...
    assert by["Long SL"] == by["Long TP"] == fill                       # ...the moved bracket exists from the fill
    assert {h["end_ms"] for h in res.hlines} == {close}                 # ...and all are drawn to the window's close


def _strip_display(monkeypatch):
    """The engine as it was before this change: plots and levels recorded nowhere."""
    from homebase.backtest import engine
    monkeypatch.setattr(engine.Ctx, "plot", lambda self, *a, **k: None)
    monkeypatch.setattr(engine.Ctx, "hline", lambda self, name, price, role="level": {"name": name})


@pytest.mark.parametrize("gate,min_adx", [(True, 20.0), (True, 99.0), (False, 20.0)])
def test_plots_and_level_stamps_never_move_a_trade_or_a_number(monkeypatch, gate, min_adx):
    from homebase.backtest import report
    with_display = _gate_day(min_adx, gate)
    _strip_display(monkeypatch)
    without = _gate_day(min_adx, gate)
    assert without.plots == {} and with_display.plots == ({} if not gate else with_display.plots)
    ledger = lambda r: json.dumps([t.to_dict() for t in r.trades], sort_keys=True)     # noqa: E731
    assert ledger(with_display) == ledger(without)
    assert with_display.skip == without.skip
    rep = lambda r: json.dumps(report.build([t.to_dict() for t in r.trades], 50_000.0), sort_keys=True, default=str)  # noqa: E731
    assert rep(with_display) == rep(without)
