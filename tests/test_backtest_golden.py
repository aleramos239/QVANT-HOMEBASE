"""Golden parity: the tester's nq930 reproduces the research replay trade by trade.

The expectations come from research/nq_930_straddle_ticks.py's own replay_day on
21 pinned 2022-2024 sessions (tests/fixtures/make_nq930_golden.py regenerates
them). This test reads the real archive, READ-ONLY; the tape cache goes to
pytest's tmp dir. Skipped on a machine without ~/futures_ticks/NQ.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from homebase.backtest.engine import Costs, run_session
from homebase.backtest.tape import TapeStore, missing_hours
from homebase.strategies.nq930 import NQ930

ARCHIVE = Path.home() / "futures_ticks"
FIX = json.loads((Path(__file__).parent / "fixtures" / "nq930_golden.json").read_text())
REASON = {"TP": "tp", "SL": "sl", "FLAT": "time"}

pytestmark = pytest.mark.skipif(not (ARCHIVE / "NQ").is_dir(), reason="needs ~/futures_ticks/NQ")


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    return TapeStore(ARCHIVE, tmp_path_factory.mktemp("tape"))


@pytest.fixture(autouse=True)
def frozen_desk_defaults(monkeypatch, tmp_path):
    # cancel 12:55 / flat 15:55 come from the desk config: pin the frozen defaults
    monkeypatch.setattr("homebase.config.config_path", lambda: tmp_path / "absent.json")


def test_fixture_covers_every_fill_case():
    cats = {c["category"] for c in FIX["cases"]}
    assert {"tp_long", "tp_short", "sl_long", "sl_short", "gap_entry", "sl_gap",
            "no_fill", "time_exit", "slip0_tp", "slip0_sl"} <= cats
    assert len(FIX["cases"]) >= 20
    assert FIX["commission"] == 4.0 and FIX["placement_ms"] == NQ930.placement_ms == 85


@pytest.mark.parametrize("case", FIX["cases"], ids=lambda c: f"{c['date']}-{c['category']}")
def test_engine_reproduces_research_trade_by_trade(store, case):
    d = dt.date.fromisoformat(case["date"])
    tape = store.load("NQ", d)
    assert tape is not None and tape.contract == case["contract"]
    assert missing_hours(tape.ts, d, NQ930.session_window) == []
    strat = NQ930({"offset_pts": case["offset"], "sl_pts": case["sl"], "tp_pts": case["tp"],
                   "adx_gate": False})
    res = run_session(strat, tape, Costs(FIX["commission"], case["slip_ticks"]), qty=1)
    assert res.skip is None, f"golden session {case['date']} was skipped: {res.skip}"
    assert [h["price"] for h in res.hlines if h["name"] == "anchor"] == [case["anchor"]]
    if not case["filled"]:
        assert res.trades == []
        return
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.side == case["side"]
    assert t.entry_price == case["entry_price"]
    assert abs(t.entry_ns - case["entry_ns"]) <= 1_000      # research stores ts as float64
    assert t.exit_reason == REASON[case["why"]]
    assert t.exit_price == case["exit_price_spec"]
    assert t.net == pytest.approx(case["net_spec"], abs=0.005)
