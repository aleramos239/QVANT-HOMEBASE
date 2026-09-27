"""Parameter heat-map grids: expansion, the 60-cell cap, the forced research window, the
looks counter, the 2-worker pool, cancel, and a cell == a single run with the same params."""
from __future__ import annotations

import json
import subprocess
import threading
import time

import pytest

from homebase.backtest import grid
from homebase.backtest.discipline import DisciplineError
from homebase.backtest.grid import GridManager, expand, validate_grid
from homebase.backtest.runner import RunManager, read_json, write_json
from tests.backtest_util import nq_archive

AXES = [{"key": "offset_pts", "values": [10, 12]}, {"key": "sl_pts", "values": [5, 6]}]


def gbody(**kw):
    return {"strategy": "nq930", "inputs": {"adx_gate": False}, "axes": AXES, **kw}


def wait_grid(m: GridManager, gid: str, s: float = 60.0) -> dict:
    t = time.monotonic() + s
    while time.monotonic() < t:
        st = m.status(gid)
        if st["status"] in ("done", "cancelled"):
            return st
        time.sleep(0.05)
    raise AssertionError(f"grid {gid} stuck at {m.status(gid)['status']}")


# ---------------------------------------------------------------- expansion / validation

def test_expand_is_the_cartesian_product_with_the_last_axis_fastest():
    cells = expand([{"key": "a", "values": [1, 2]}, {"key": "b", "values": ["x", "y", "z"]}])
    assert [c["i"] for c in cells] == list(range(6))
    assert [c["params"] for c in cells] == [{"a": 1, "b": "x"}, {"a": 1, "b": "y"}, {"a": 1, "b": "z"},
                                            {"a": 2, "b": "x"}, {"a": 2, "b": "y"}, {"a": 2, "b": "z"}]
    assert [c["coords"] for c in cells] == [[0, 0], [0, 1], [0, 2], [1, 0], [1, 1], [1, 2]]
    three = expand([{"key": "a", "values": [1, 2]}, {"key": "b", "values": [3]}, {"key": "c", "values": [4, 5]}])
    assert len(three) == 4 and three[3] == {"i": 3, "params": {"a": 2, "b": 3, "c": 5}, "coords": [1, 0, 1]}


def test_validate_grid_resolves_values_and_builds_one_single_run_request_per_cell():
    g = validate_grid(gbody(axes=[{"key": "offset_pts", "values": [10, 12.5]}, {"key": "adx_gate", "values": [False, True]}]))
    assert g["strategy"] == "nq930" and len(g["cells"]) == 4
    assert [a["key"] for a in g["axes"]] == ["offset_pts", "adx_gate"]
    assert g["axes"][0]["values"] == [10.0, 12.5] and g["axes"][0]["label"] == "Entry offset (pts)"
    c = g["cells"][3]
    assert c["params"] == {"offset_pts": 12.5, "adx_gate": True}
    assert c["req"]["inputs"]["offset_pts"] == 12.5 and c["req"]["inputs"]["adx_gate"] is True
    assert (c["req"]["qty"], c["req"]["commission"], c["req"]["slippage_ticks"]) == (1, 4.0, 1.0)


def test_the_cap_is_60_cells():
    ok = validate_grid(gbody(axes=[{"key": "offset_pts", "values": list(range(6))},
                                   {"key": "sl_pts", "values": list(range(1, 11))}]))
    assert len(ok["cells"]) == 60
    with pytest.raises(ValueError, match="61 cells.*60"):
        validate_grid(gbody(axes=[{"key": "offset_pts", "values": list(range(61))},
                                  {"key": "sl_pts", "values": [5]}]))
    with pytest.raises(ValueError, match="64 cells.*60"):
        validate_grid(gbody(axes=[{"key": "offset_pts", "values": list(range(4))},
                                  {"key": "sl_pts", "values": list(range(1, 5))},
                                  {"key": "tp_pts", "values": list(range(1, 5))}]))


@pytest.mark.parametrize("axes,msg", [
    ([{"key": "offset_pts", "values": [10]}], "2 or 3 parameters"),
    ([{"key": k, "values": [1, 2]} for k in ("offset_pts", "sl_pts", "tp_pts", "adx_min")], "2 or 3 parameters"),
    ("offset_pts", "2 or 3 parameters"),
    ([{"key": "offset_pts", "values": [10]}, {"key": "offset_pts", "values": [12]}], "twice"),
    ([{"key": "zz", "values": [1]}, {"key": "sl_pts", "values": [5]}], "unknown input"),
    ([{"key": "offset_pts", "values": []}, {"key": "sl_pts", "values": [5]}], "offset_pts: a list of values"),
    ([{"key": "offset_pts", "values": 10}, {"key": "sl_pts", "values": [5]}], "offset_pts: a list of values"),
    ([{"key": "offset_pts", "values": [10, 10.0]}, {"key": "sl_pts", "values": [5]}], "offset_pts: 10.0 twice"),
    ([{"key": "offset_pts", "values": [10]}, {"key": "sl_pts", "values": [-1]}], "sl_pts"),
    ([{"key": "offset_pts", "values": [10]}, {"key": "adx_gate", "values": ["yes"]}], "adx_gate"),
])
def test_bad_axes_are_refused(axes, msg):
    with pytest.raises(ValueError, match=msg):
        validate_grid(gbody(axes=axes))


def test_bad_bodies_are_refused():
    for bad, msg in (("x", "JSON object"), (gbody(extra=1), "unknown field"), (gbody(strategy="zz"), "unknown strategy"),
                     (gbody(inputs=[1]), "inputs"), (gbody(qty=0), "qty"), (gbody(prop_rules="nope@1"), "prop_rules")):
        with pytest.raises(ValueError, match=msg):
            validate_grid(bad)


def test_the_window_is_forced_to_the_research_window_2021_2024():
    for g in (validate_grid(gbody()), validate_grid(gbody(range={"kind": "research"}))):
        assert g["range"]["start"] == "2021-01-01" and g["range"]["end"] == "2024-12-31"
        for c in g["cells"]:
            assert c["req"]["range"]["kind"] == "research"
            assert (c["req"]["range"]["start"], c["req"]["range"]["end"]) == ("2021-01-01", "2024-12-31")
            assert c["req"]["holdout"] is None
    for rng in ({"kind": "custom", "start": "2024-01-01", "end": "2025-06-30"},
                {"kind": "custom", "start": "2022-01-01", "end": "2023-12-31"},
                {"kind": "is_months"}, {"kind": "research", "end": "2025-06-30"}):
        with pytest.raises(DisciplineError, match="research window 2021–2024 only"):
            validate_grid(gbody(range=rng))
    with pytest.raises(DisciplineError, match="research window 2021–2024 only"):
        validate_grid(gbody(holdout={"reason": "peek"}))


# ---------------------------------------------------------------- the looks counter

def test_looks_persist_per_strategy(tmp_path):
    p = tmp_path / "tester" / "looks.json"
    assert grid.read_looks(p) == {}
    assert grid.add_look(p, "nq930") == 1
    assert grid.add_look(p, "nq930") == 2
    assert grid.add_look(p, "ym930") == 1
    assert json.loads(p.read_text()) == {"nq930": 2, "ym930": 1}
    assert grid.read_looks(p) == {"nq930": 2, "ym930": 1}          # a fresh read, e.g. after a restart
    p.write_text("{torn")
    assert grid.read_looks(p) == {}                                # never crashes the page on a bad file
    p.write_text(json.dumps({"nq930": 5, "bad": "x", "neg": -1}))
    assert grid.read_looks(p) == {"nq930": 5}


# ---------------------------------------------------------------- the manager, with a fake child

class FakeChild:
    """Stands in for `python -m homebase.backtest.runner exec <cell> --no-lock`: blocks until released,
    then writes what a finished run leaves behind (status done + a run.json)."""
    live = 0
    peak = 0
    lock = threading.Lock()

    def __init__(self, argv, release: threading.Event, net: float):
        self.cdir = argv[argv.index("exec") + 1]
        self.argv, self.release, self.net, self.pid = argv, release, net, 4242
        self._done = threading.Event()
        with FakeChild.lock:
            FakeChild.live += 1
            FakeChild.peak = max(FakeChild.peak, FakeChild.live)

    def wait(self, timeout=None):
        if not self._done.is_set():
            if not self.release.wait(timeout if timeout is not None else 30):
                raise subprocess.TimeoutExpired("fake", timeout)
            self._finish(ok=True)
        return 0

    def _finish(self, ok: bool):
        if self._done.is_set():
            return
        from pathlib import Path
        d = Path(self.cdir)
        req = read_json(d / "request.json")
        if ok:
            allc = {"net_profit": self.net, "sharpe": 1.5, "trades": 3, "win_rate": 66.7, "profit_factor": 2.0,
                    "max_drawdown": -100.0, "t_stat": 1.1, "avg_trade": self.net / 3}
            write_json(d / "run.json", {"id": req["id"], "report": {"summary": {"all": allc}, "skipped_by_error": 0},
                                        "coverage": {"sessions": 2, "used": 1}})
            write_json(d / "status.json", {"id": req["id"], "status": "done"})
        with FakeChild.lock:
            FakeChild.live -= 1
        self._done.set()

    def terminate(self):
        self._finish(ok=False)

    def kill(self):
        self._finish(ok=False)


@pytest.fixture
def fake(monkeypatch):
    FakeChild.live = FakeChild.peak = 0
    release = threading.Event()
    spawned: list[FakeChild] = []

    def popen(argv, **kw):
        ch = FakeChild(argv, release, net=100.0 * (len(spawned) + 1))
        spawned.append(ch)
        return ch

    monkeypatch.setattr(grid.subprocess, "Popen", popen)
    return release, spawned


def test_the_pool_runs_at_most_two_cells_at_once_and_counts_one_look_per_finished_cell(tmp_path, fake):
    release, spawned = fake
    m = GridManager(tmp_path, archive=tmp_path / "a", cache=tmp_path / "c")
    gid = m.submit(gbody(axes=[{"key": "offset_pts", "values": [10, 11, 12]}, {"key": "sl_pts", "values": [5, 6]}]))
    t = time.monotonic() + 5
    while len(spawned) < 2 and time.monotonic() < t:
        time.sleep(0.01)
    time.sleep(0.2)
    assert len(spawned) == 2 and FakeChild.live == 2            # two in flight, four queued
    st = m.status(gid)
    assert st["status"] == "running" and st["total"] == 6
    assert sorted(c["status"] for c in st["cells"]) == ["queued"] * 4 + ["running"] * 2
    assert st["looks"] == 0
    for ch in spawned:
        assert "--no-lock" in ch.argv and ch.argv[ch.argv.index("--archive") + 1] == str(tmp_path / "a")
    release.set()
    st = wait_grid(m, gid)
    assert st["status"] == "done" and st["done"] == 6 and FakeChild.peak == 2
    assert all(c["status"] == "done" and c["summary"]["sharpe"] == 1.5 for c in st["cells"])
    assert sorted(c["summary"]["net_profit"] for c in st["cells"]) == [100.0 * k for k in range(1, 7)]
    assert st["looks"] == 6 and grid.read_looks(tmp_path / "looks.json") == {"nq930": 6}
    # the state is on disk: a new manager (a restarted service) reads the finished grid back
    m2 = GridManager(tmp_path)
    assert m2.status(gid)["status"] == "done" and m2.status(gid)["looks"] == 6
    assert m2.list()[0]["id"] == gid


def test_cancel_drops_queued_cells_stops_running_ones_and_counts_no_look_for_them(tmp_path, fake):
    release, spawned = fake
    m = GridManager(tmp_path)
    gid = m.submit(gbody())
    t = time.monotonic() + 5
    while len(spawned) < 2 and time.monotonic() < t:
        time.sleep(0.01)
    st = m.cancel(gid)
    assert st["status"] == "cancelled"
    assert [c["status"] for c in st["cells"]] == ["cancelled"] * 4
    time.sleep(0.2)
    assert len(spawned) == 2                                   # nothing queued was started after the cancel
    assert m.status(gid)["looks"] == 0 and grid.read_looks(tmp_path / "looks.json") == {}
    assert m.cancel(gid)["status"] == "cancelled"              # idempotent


def test_a_grid_left_running_by_a_dead_service_reads_as_interrupted(tmp_path, fake):
    release, spawned = fake
    m = GridManager(tmp_path)
    gid = m.submit(gbody())
    t = time.monotonic() + 5
    while len(spawned) < 2 and time.monotonic() < t:
        time.sleep(0.01)
    m2 = GridManager(tmp_path)                                  # a new service over the same state dir
    st = m2.status(gid)
    assert st["status"] == "cancelled" and "restarted" in st["error"]
    assert all(c["status"] in ("cancelled", "error") for c in st["cells"])
    release.set()
    m.shutdown()


def test_unknown_grids_and_cells(tmp_path):
    m = GridManager(tmp_path)
    for bad in ("nope", "../../etc", "20260927-120000-nq930-abcd"):
        with pytest.raises(KeyError):
            m.status(bad)
    with pytest.raises(KeyError):
        m.cell_bundle("20260927-120000-nq930-abcd", 0)


# ---------------------------------------------------------------- a cell == a single run (real children)

def test_every_cell_equals_a_single_run_with_the_same_params(tmp_path):
    archive, cache = nq_archive(tmp_path / "ticks"), tmp_path / "cache"
    m = GridManager(tmp_path / "state", archive=archive, cache=cache)
    gid = m.submit(gbody(axes=[{"key": "offset_pts", "values": [10, 12]}, {"key": "tp_pts", "values": [15, 30]}]))
    st = wait_grid(m, gid, s=120)
    assert st["status"] == "done" and [c["status"] for c in st["cells"]] == ["done"] * 4
    nets = {c["summary"]["net_profit"] for c in st["cells"]}
    assert len(nets) > 1, "the synthetic day should separate at least two cells"

    runs = RunManager(tmp_path / "state", archive=archive, cache=cache)
    for cell in st["cells"]:
        rid = runs.submit({"strategy": "nq930", "inputs": {"adx_gate": False, **cell["params"]},
                           "range": {"kind": "research"}})
        t = time.monotonic() + 60
        while runs.status(rid).get("status") not in ("done", "error", "cancelled") and time.monotonic() < t:
            time.sleep(0.05)
        assert runs.status(rid)["status"] == "done"
        single, got = runs.bundle(rid), m.cell_bundle(gid, cell["i"])
        assert got["run"]["report"] == single["run"]["report"]
        assert got["run"]["inputs"] == single["run"]["inputs"]
        assert got["run"]["range"] == single["run"]["range"]
        assert got["run"]["coverage"] == single["run"]["coverage"]
        for k in ("trades", "equity", "plots", "propsim"):
            assert got[k] == single[k], k
        allc = single["run"]["report"]["summary"]["all"]
        for k, v in cell["summary"].items():
            if k in allc:
                assert v == allc[k], k
