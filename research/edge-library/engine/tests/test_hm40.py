"""hm40 (the owner, 2026-10-20): the default heat map = 4 ATR stops + 4 own stops x 5 targets = 40 cells; the `own` stop = the family's
structure distance x the multiplier (floored at 0.25 ATR); a family that passes no structure level gets the 20 ATR cells only."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import l2sim as S
from families import blocks
from test_blocks import D, DAILY, minute_tape, rand_bars

W = Path(__file__).resolve().parents[2]
if str(W) not in sys.path:
    sys.path.insert(0, str(W))
from blueprint import rules as R  # noqa: E402


def test_hm40_has_40_cells_in_order():
    m = blocks.menu_hm40("NQ", own=True)
    assert len(m) == 40
    assert [(c["stop_mode"], c["stop_val"]) for c in m[::5]] == [("atr", .5), ("atr", 1.), ("atr", 1.5), ("atr", 2.), ("own", .5), ("own", 1.), ("own", 1.5), ("own", 2.)]
    assert [c["tgt_r"] for c in m[:5]] == [.5, .75, 1., 1.5, 2.]
    assert blocks.menu_hm40("NQ", own=False) == m[:20]


def test_hm40_without_structure_has_20_cells():
    assert len(blocks.exits("hm40", "NQ", "straddle")) == 20 and len(blocks.exits("hm40", "NQ", "candle_sweep")) == 40
    assert "candle_sweep" in blocks.STRUCT_FAMILIES and "straddle" not in blocks.STRUCT_FAMILIES


def test_hm40_is_the_json_table_and_rules_reads_it():
    j = json.loads((W / "blueprint" / "templates" / "exit_menu.json").read_text())["hm40"]
    assert j["cells"] == 40 == len(R.exit_cells("hm40", "NQ"))
    assert R.exit_cells("hm40", "NQ") == blocks.menu_hm40("NQ", own=True)


def test_own_cell_id():
    assert S.cell_id({"stop_mode": "own", "stop_val": 1.5, "tgt_r": 0.75}) == "own1p5-r0p75"
    ids = [S.cell_id(c) for c in blocks.menu_hm40("ES", own=True)]
    assert len(set(ids)) == 40 and ids[0] == "atr0p5-r0p5" and ids[-1] == "own2-r2"


def _dist(cls, mult):
    st = cls({"stop_mode": "own", "stop_val": mult})
    st.atr = 8.0
    return st._dist(SimpleNamespace(tick=0.25), 100.0, 90.0)


def test_own_stop_is_struct_distance_times_mult_floored():   # ref 100, struct 90, atr 8: 1.5 -> 15; 0.1 -> floor 2.0
    for cls in (S.Template, blocks.WRAPPED["candle_sweep"]):
        assert _dist(cls, 1.5) == 15.0 and _dist(cls, 0.1) == 2.0, cls


class NoStruct(S.Template):
    """One market long at the first tf close of the session, with no structure level."""
    def fam_day(self, ctx):
        self.fired = False

    def fam_signal(self, ctx):
        if not self.fired:
            self.fired = True
            self._mkt(ctx, "long")


P = {"tf": "5", "sess": "nyam", "tgt_r": 1.0}


def test_own_stop_without_struct_places_no_order(monkeypatch):          # a signal with struct=None in an own cell: no order, counted
    bars = rand_bars(1020, 7, step=3.0)                  # 00:00-17:00: the whole nyam window
    monkeypatch.setattr(S, "load_tape", lambda d, root, **kw: minute_tape(bars, "00:00", d=D))
    monkeypatch.setattr(S, "load_daily", lambda root, *a, **kw: list(DAILY))
    own, atr = S.run_many([(NoStruct, {**P, "stop_mode": "own", "stop_val": 1.0}), (NoStruct, {**P, "stop_mode": "atr", "stop_val": 1.0})],
                          days=[D], root="NQ", workers=1, on_error="raise")
    assert own["trades"] == [] and own["skipped_by_reason"] == {"own stop: no structure level": 1}
    assert len(atr["trades"]) == 1 and atr["skipped_by_reason"] == {}


def test_old_tables_unchanged():
    assert len(blocks.menu_blueprint("NQ")) == 48 and blocks.exits("blueprint", "NQ", "candle_sweep") == blocks.menu_blueprint("NQ")
