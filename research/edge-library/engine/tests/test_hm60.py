"""hm60 (the owner, 2026-10-20 23:45 ET: add fixed-point stops to the heat map): hm40's cells, then 4 fixed stops (NQ 15 / 25 / 40 / 60
points; ES 4 / 6 / 10 / 15; GC 2.5 / 4 / 6.5 / 10) x hm40's 5 targets = 60 cells, 40 for a family with no structure level. hm40 stays the
default of the 3:1 walk-forward; a spec runs hm60 when it says so. Its random pool holds the fixed-point cells; a fixed-point box is held
against random entries at the SAME fixed stop."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

from families import blocks

W = Path(__file__).resolve().parents[2]
if str(W) not in sys.path:
    sys.path.insert(0, str(W))
from blueprint import hmwf as H  # noqa: E402
from blueprint import rules as R  # noqa: E402
from blueprint import runner as RUN  # noqa: E402
from test_hmwf import SPEC, wf  # noqa: E402,F401  (the fixture: the 3:1 months of a tiny calendar, a fake engine)

PTS = {"NQ": [15.0, 25.0, 40.0, 60.0], "ES": [4.0, 6.0, 10.0, 15.0], "GC": [2.5, 4.0, 6.5, 10.0]}


@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_hm60_is_hm40_then_the_fixed_stops(root):
    m, h = blocks.menu_hm60(root, own=True), blocks.menu_hm40(root, own=True)
    assert len(m) == 60 and m[:40] == h
    assert [(c["stop_mode"], c["stop_val"]) for c in m[40::5]] == [("pts", v) for v in PTS[root]]
    assert [c["tgt_r"] for c in m[40:45]] == [.5, .75, 1., 1.5, 2.]
    assert blocks.menu_hm60(root, own=False) == blocks.menu_hm40(root, own=False) + m[40:]
    assert len({str(c) for c in m}) == 60


def test_hm60_by_family_and_the_rules_reader():
    assert len(blocks.exits("hm60", "NQ", "candle_sweep")) == 60 and len(blocks.exits("hm60", "NQ", "vwap_z")) == 40
    assert R.exit_cells("hm60", "NQ") == blocks.menu_hm60("NQ", own=True)
    assert json.loads((W / "blueprint" / "templates" / "exit_menu.json").read_text())["hm60"]["cells"] == 60


def test_the_pool_of_hm60_holds_the_fixed_stop_cells():
    g = RUN.c1_grid_hm60("NQ", "15")
    ex = {(c["exit"]["stop_mode"], c["exit"]["stop_val"]) for c in g}
    assert ("pts", 25.0) in ex and ("atr", 1.0) in ex and not any(m == "own" for m, _ in ex)
    assert RUN.pool_key("NQ", "15", RUN.HM60) == "c1f-NQ-tf15" and RUN.pool_key("NQ", "15", RUN.HM40) == "c1h-NQ-tf15"


def test_a_spec_runs_hm40_unless_it_asks_for_hm60():
    assert H._spec({**SPEC})["exits"] == RUN.HM40
    assert H._spec({**SPEC, "exits": "hm60"})["exits"] == RUN.HM60


def test_a_fixed_point_box_is_held_against_the_same_fixed_stop(monkeypatch):
    cell = {"id": "ema1h0_pts25-r1", "exit": {"stop_mode": "pts", "stop_val": 25.0, "tgt_r": 1.0}}
    pool = {"meta": {"cells": [{"id": "s1_pts25-r1", "exit": {"stop_mode": "pts", "stop_val": 25.0, "tgt_r": 1.0}},
                               {"id": "s1_atr1-r1", "exit": {"stop_mode": "atr", "stop_val": 1.0, "tgt_r": 1.0}}]}}
    rows = [{"net": np.array([-10.0, -30.0]), "sess": np.array([4, 4])}, {"net": np.array([500.0]), "sess": np.array([4])}]
    monkeypatch.setattr(H.LB, "unit_cell", lambda p, i: rows[i])
    share, vs = H._beats({"net": np.array([0.0, 10.0])}, cell, pool, [4])
    assert (share, vs) == (1.0, "pts25-r1")            # only the same fixed-point cell is the yardstick, not the ATR one


def test_run_is_on_hm60_runs_60_boxes_a_value_and_its_own_pool(wf):
    r = H.run_is({**SPEC, "exits": "hm60"}, workers=1, ledger=wf["ledger"])
    assert r["boxes"] == 180
    rows = H.is_table("hwt_sweep")
    assert len(rows) == 180 and any(x["box"].endswith("pts25-r1") for x in rows)
    pt = next(x for x in rows if x["box"] == "ema1h50_pts25-r1")
    assert pt["random_vs"] == "pts25-r1"
