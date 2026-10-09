"""LOCK of the pipeline's views (blueprint/pipe_view.py): the picked box's equity curve and its executions.

1. curve reads the PICKED cell's trades only, by day: the day's net, the running total, and the numbers a person asks first.
2. A Book card reads its unseen-days store; an idea still in the queue reads its build store; no pick, no store -> refused.
3. executions hands the same trades (time, side, net, exit reason) to the app's execrun, once: a second call answers the same run.
A temp folder each test: nothing is written under ~/.homebase or in the repo. No engine, no tape.

  pytest tests/test_pipe_view.py -q
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
import judge as J  # noqa: E402
from blueprint import pipe_view as V  # noqa: E402

D = [dt.date(2025, 7, 1), dt.date(2025, 7, 1), dt.date(2025, 7, 2), dt.date(2025, 7, 7)]


def ms(d: dt.date, h: int, m: int, extra: int = 85) -> int:
    return int(dt.datetime(d.year, d.month, d.day, h, m, tzinfo=dt.timezone.utc).timestamp() * 1000) + extra


def store(folder: Path, cells: dict):
    """A store with the given cells: {cell id: [(date, entry_ms, dur_s, net, side, reason)]}."""
    folder.mkdir(parents=True)
    off, cols = [0], {k: [] for k in ("date", "entry_ms", "dur_s", "net", "side", "reason", "risk")}
    for rows in cells.values():
        for d, e, dur, net, side, reason in rows:
            cols["date"].append(d.toordinal()); cols["entry_ms"].append(e); cols["dur_s"].append(dur); cols["net"].append(net)
            cols["side"].append(side); cols["reason"].append(reason); cols["risk"].append(30.0)
        off.append(len(cols["net"]))
    np.savez(folder / "cells.npz", off=np.array(off, np.int64), date=np.array(cols["date"], np.int32), entry_ms=np.array(cols["entry_ms"], np.int64),
             dur_s=np.array(cols["dur_s"], np.int32), net=np.array(cols["net"], np.float64), side=np.array(cols["side"], np.int8),
             reason=np.array(cols["reason"], np.int8), risk=np.array(cols["risk"], np.float32))
    (folder / "run.json").write_text(json.dumps({"cells": [{"id": c} for c in cells], "inputs_hash": "h1"}))


PICKED = [(D[0], ms(D[0], 15, 1), 600, 500.0, 1, 1), (D[1], ms(D[1], 16, 0), 60, -200.0, 1, 0),
          (D[2], ms(D[2], 15, 30), 900, -300.0, 1, 0), (D[3], ms(D[3], 15, 5), 1200, 1000.0, 1, 2)]
OTHER = [(D[0], ms(D[0], 15, 1), 600, -9999.0, 1, 0)]


def idea(root: Path, name="nq_x", status="book", picked=True, test=True, build=False):
    d = root / "p" / name
    d.mkdir(parents=True)
    (d / "card.json").write_text(json.dumps({"name": name, "market": "NQ", "session": "mid", "bar": "1", "sides": "long"}))
    (d / "state.json").write_text(json.dumps({"status": status, "picked": {"sub": f"{name}_a1", "bar": "1", "cell": "pick"} if picked else {}}))
    if test:
        store(root / "runs_test" / f"{name}_a1-NQ-tf1-mid-test", {"other": OTHER, "pick": PICKED})
    if build:
        store(root / "runs" / f"{name}_a1-NQ-tf1", {"pick": PICKED[:2], "other": OTHER})
    return name


def test_curve_is_the_picked_cells_trades_by_day_with_the_first_numbers():
    with tempfile.TemporaryDirectory() as t:
        r = V.curve(idea(Path(t)), t)
        assert r["ok"] and r["period"] == "test" and r["cell"] == "pick" and r["idea"] == "nq_x_a1"
        assert (r["trades"], r["days"], r["net"]) == (4, 3, 1000.0)                # the other cell's -9999 is not read
        assert r["curve"] == [["2025-07-01", 300.0, 300.0], ["2025-07-02", -300.0, 0.0], ["2025-07-07", 1000.0, 1000.0]]
        assert r["win_rate"] == 0.5 and r["avg_trade"] == 250.0 and r["profit_factor"] == 3.0
        assert (r["avg_win"], r["avg_loss"]) == (750.0, -250.0)
        assert (r["best_day"], r["worst_day"], r["max_drawdown"]) == (1000.0, -300.0, 300.0)
        assert (r["start"], r["end"], r["market"], r["session"]) == ("2025-07-01", "2025-07-07", "NQ", "mid")
        assert not (Path(t) / "runs").exists()                                    # a view makes no folder


def test_a_queued_idea_reads_its_build_store_and_a_book_card_its_unseen_days():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        idea(root, "nq_q", status="running", test=True, build=True)               # not in the book yet: the build days, even with a test store
        r = V.curve("nq_q", t)
        assert r["period"] == "build" and r["trades"] == 2 and r["net"] == 300.0
        idea(root, "nq_b", status="book", test=True, build=True)
        assert V.curve("nq_b", t)["period"] == "test"


def test_no_pick_or_no_store_is_refused_in_plain_words():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        idea(root, "nq_nopick", picked=False)
        with pytest.raises(J.Refuse, match="no picked box yet"):
            V.curve("nq_nopick", t)
        idea(root, "nq_nostore", test=False)
        with pytest.raises(J.Refuse, match="no stored trades"):
            V.curve("nq_nostore", t)
        with pytest.raises(J.Refuse):
            V.curve("nq_missing", t)


def test_executions_hands_the_picked_trades_to_the_app_once(monkeypatch):
    calls = []

    class P:
        returncode, stderr = 0, ""
        stdout = 'x\n{"run_id": "20261009-000000-pipe_nq_x-abcd", "priced": 4, "of": 4}\n'

    def fake_run(argv, **kw):
        calls.append((argv, json.loads(Path(argv[argv.index("homebase.backtest.execrun") + 1]).read_text())))
        (Path(argv[argv.index("--base") + 1]) / "runs" / "20261009-000000-pipe_nq_x-abcd").mkdir(parents=True)
        (Path(argv[argv.index("--base") + 1]) / "runs" / "20261009-000000-pipe_nq_x-abcd" / "run.json").write_text("{}")
        return P()

    monkeypatch.setattr(V.subprocess, "run", fake_run)
    with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as tester:
        name = idea(Path(t))
        r = V.executions(name, t, tester=tester)
        assert (r["run_id"], r["trades"], r["of"], r["fresh"], r["period"]) == ("20261009-000000-pipe_nq_x-abcd", 4, 4, True, "test")
        argv, body = calls[0]
        assert argv[argv.index("--strategy") + 1] == "pipe_nq_x" and argv[argv.index("--root") + 1] == "NQ"
        assert (argv[argv.index("--start") + 1], argv[argv.index("--end") + 1], argv[argv.index("--sessions") + 1]) == ("2025-07-01", "2025-07-07", "3")
        assert body["trades"][0] == {"date": "2025-07-01", "entry_ms": PICKED[0][1], "dur_s": 600, "side": 1, "net": 500.0, "reason": "tp"}
        assert [x["reason"] for x in body["trades"]] == ["tp", "sl", "sl", "time"]
        again = V.executions(name, t, tester=tester)
        assert again["run_id"] == r["run_id"] and again["fresh"] is False and len(calls) == 1      # found again: nothing new is written
        # the run folder gone (the tester was cleared): it is written again
        import shutil
        shutil.rmtree(Path(tester) / "runs")
        assert V.executions(name, t, tester=tester)["fresh"] is True and len(calls) == 2
