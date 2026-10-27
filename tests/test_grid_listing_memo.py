"""/grids and /walkforwards keep each grid.json's row and read the file again only when it changed (2026-10-26): the rows
are the ones a fresh read gives."""
from __future__ import annotations

import threading

import pytest

from homebase.backtest import grid, runner, walkforward
from homebase.backtest.runner import write_json

A, B = "20261026-100000-draft_a-aaaa", "20261026-110000-draft_b-bbbb"


@pytest.fixture(autouse=True)
def settled(monkeypatch):
    """Files count as settled at once here (the 2 s rule is tested with the run listings)."""
    monkeypatch.setattr(runner, "SETTLED_NS", 0)


def manager(cls, root):
    m = object.__new__(cls)                       # no __init__: nothing recovered, nothing written
    m.grids, m._lock, m._live = root, threading.Lock(), {}
    return m


def reads(monkeypatch):
    seen = []
    real = grid.read_json

    def counting(path, default=None):
        seen.append(path.parent.name)
        return real(path, default)
    monkeypatch.setattr(grid, "read_json", counting)
    return seen


def test_a_grid_row_is_read_again_only_when_its_file_changed(tmp_path, monkeypatch):
    (tmp_path / A).mkdir()
    (tmp_path / B).mkdir()
    write_json(tmp_path / A / "grid.json", {"id": A, "strategy": "draft_a", "status": "done", "axes": [{"key": "stop"}],
                                            "walkforward": {"metric": "net", "test_months": 1}})
    (tmp_path / B / "grid.json").write_text("{half")                      # being written: never kept
    gm, wm = manager(grid.GridManager, tmp_path), manager(walkforward.WalkForwardManager, tmp_path)
    row = {"id": A, "strategy": "draft_a", "created": None, "status": "done", "done": None, "total": None, "axes": ["stop"]}
    first = gm.list()
    assert first == [row]
    assert wm.list() == [{**row, "metric": "net", "compare": False, "test_months": 1,
                          "select_months": walkforward.SELECT_MONTHS, "scheme": "pick"}]
    seen = reads(monkeypatch)
    first[0]["axes"].append("x")                                           # a caller's copy changes nothing kept
    assert gm.list() == [row]
    wm.list()
    assert seen == [B, B]                                                  # only the half-written one is read again
    seen.clear()
    write_json(tmp_path / B / "grid.json", {"id": B, "strategy": "draft_b", "status": "running", "axes": [],
                                            "walkforward": {"compare": True, "scheme": "fixed"}})
    got = wm.list()
    assert [g["id"] for g in got] == [B, A] and got[0]["compare"] is True and got[0]["scheme"] == "fixed"
    assert seen == [B, B]                                                  # its row and its walk-forward part, once each
    gm._live[A] = {"id": A, "strategy": "draft_a", "status": "running", "axes": []}
    assert gm.list()[1]["status"] == "running"                             # this manager's own job: from memory, as before
