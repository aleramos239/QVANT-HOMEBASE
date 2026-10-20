"""LOCK of the taught lane's 3:1 walk-forward (blueprint/taught_wf.py; the owner, 2026-10-19). The walk itself is pipe_wf's (test_pipe_wf.py);
this locks what taught_wf adds: the test days' random pool in judge.pool_arrays' shape, and whole months only. No engine.

  pytest tests/test_taught_wf.py -q
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(HERE), str(HERE / "engine")]

from blueprint import taught_wf as W  # noqa: E402


def _x(dates, ms, net):
    return {"date": np.array(dates, np.int64), "entry_ms": np.array(ms, np.int64), "net": np.array(net, np.float64)}


def test_the_pool_is_sorted_by_date_with_its_cumulative_net_and_one_slot_per_entry():
    d, n, c, cs = W._pool({1: _x([5, 3, 5], [20, 10, 10], [1.0, 2.0, 3.0]), 2: _x([3], [5], [4.0])})
    assert list(d) == [3, 3, 5, 5] and sorted(n[:2]) == [2.0, 4.0] and list(n[2:]) == [3.0, 1.0]       # day 5: entry 10 before 20
    assert list(cs) == [0.0, *np.cumsum(n)] and len(set(c.tolist())) == 4


def test_the_test_days_stop_at_the_last_whole_month(monkeypatch):
    days = [dt.date(2026, 9, 29), dt.date(2026, 9, 30), dt.date(2026, 10, 1), dt.date(2026, 10, 16)]
    monkeypatch.setattr(W.RUN, "test_range", lambda m: {"start": "2026-09-29", "end": "2026-10-16"})
    monkeypatch.setattr(W.S, "sessions", lambda a, b, m, allow_holdout=None: days)
    assert W._test_days("NQ", dt.date(2026, 10, 19)) == ["2026-09-29", "2026-09-30"]
