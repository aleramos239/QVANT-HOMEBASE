"""The global backtest cap (2 processes, single runs + grid cells together) and the QUIET window
(no backtest STARTS 09:20-09:35 ET on weekdays: the live desk shares the machine)."""
from __future__ import annotations

import datetime as dt
import threading
import time
from zoneinfo import ZoneInfo

import pytest

from homebase.backtest import grid, slots
from homebase.backtest.grid import GridManager
from homebase.backtest.runner import RunManager, read_json, write_json
from homebase.backtest.slots import QUIET_MSG, Slots, in_quiet

ET = ZoneInfo("America/New_York")
MON = dt.date(2026, 9, 28)          # a Monday


def et(d: dt.date, hms: str) -> dt.datetime:
    return dt.datetime.combine(d, dt.time.fromisoformat(hms), ET)


class Clock:
    def __init__(self, t: dt.datetime):
        self.t = t

    def __call__(self) -> dt.datetime:
        return self.t


def test_the_quiet_window_is_0920_to_0935_et_on_weekdays():
    assert not in_quiet(et(MON, "09:19:59"))
    assert in_quiet(et(MON, "09:20:00"))
    assert in_quiet(et(MON, "09:34:59"))
    assert not in_quiet(et(MON, "09:35:00"))
    assert in_quiet(et(MON + dt.timedelta(days=4), "09:25:00"))           # Friday
    assert not in_quiet(et(MON + dt.timedelta(days=5), "09:25:00"))       # Saturday
    assert not in_quiet(et(MON - dt.timedelta(days=1), "09:25:00"))       # Sunday
    # an aware clock in another zone is converted to ET first: 13:25 UTC in September = 09:25 ET
    assert in_quiet(dt.datetime(2026, 9, 28, 13, 25, tzinfo=dt.timezone.utc))
    assert QUIET_MSG == "paused for the 9:30 window"


def test_two_slots_shared_by_every_holder_of_the_same_dir(tmp_path):
    clock = Clock(et(MON, "12:00:00"))
    a, b = Slots(tmp_path / "slots", clock=clock), Slots(tmp_path / "slots", clock=clock)
    s1, s2 = a.try_acquire(), b.try_acquire()
    assert s1 is not None and s2 is not None
    assert a.try_acquire() is None and b.try_acquire() is None           # the cap is global, not per manager
    s1.close()
    s3 = b.try_acquire()
    assert s3 is not None
    s2.close(); s3.close()


def test_no_slot_starts_inside_the_quiet_window(tmp_path):
    clock = Clock(et(MON, "09:25:00"))
    s = Slots(tmp_path / "slots", clock=clock, poll=0.01)
    assert s.quiet() and s.try_acquire() is None
    got: list = []
    t = threading.Thread(target=lambda: got.append(s.acquire()))
    t.start()
    time.sleep(0.1)
    assert got == []                                                     # still waiting
    clock.t = et(MON, "09:35:00")
    t.join(2)
    assert got and got[0] is not None
    got[0].close()
    stop = threading.Event()
    clock.t = et(MON, "09:30:00")
    stop.set()
    assert s.acquire(cancelled=stop.is_set) is None                      # a cancelled waiter gives up


def test_a_single_run_request_inside_the_quiet_window_is_refused(tmp_path):
    m = RunManager(tmp_path, slots=Slots(tmp_path / "slots", clock=Clock(et(MON, "09:21:00"))))
    with pytest.raises(ValueError, match=QUIET_MSG):
        m.submit({"strategy": "nq930", "range": {"kind": "research"}})
    assert not any((tmp_path / "runs").glob("2*"))                     # nothing prepared


# ---------------------------------------------------------------- fake children for both managers

class Live:
    def __init__(self):
        self.lock, self.now, self.peak, self.release = threading.Lock(), 0, 0, threading.Event()
        self.started: list[str] = []


class FakeChild:
    def __init__(self, argv, live: Live):
        self.d = argv[argv.index("exec") + 1]
        self.live, self.pid = live, 4242
        with live.lock:
            live.now += 1
            live.peak = max(live.peak, live.now)
            live.started.append(self.d)
        self._done = False

    def wait(self, timeout=None):
        if not self._done:
            self.live.release.wait(30)
            self._end(True)
        return 0

    def _end(self, ok):
        if self._done:
            return
        from pathlib import Path
        d = Path(self.d)
        rid = read_json(d / "request.json")["id"]
        if ok:
            write_json(d / "run.json", {"id": rid, "report": {"summary": {"all": {"net_profit": 1.0}}}})
            write_json(d / "status.json", {"id": rid, "status": "done"})
        with self.live.lock:
            self.live.now -= 1
        self._done = True

    def terminate(self):
        self._end(False)

    kill = terminate


@pytest.fixture
def live(monkeypatch):
    lv = Live()
    monkeypatch.setattr(grid.subprocess, "Popen", lambda argv, **kw: FakeChild(argv, lv))
    return lv


def until(cond, s=5.0):
    t = time.monotonic() + s
    while time.monotonic() < t:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


GRID = {"strategy": "nq930", "inputs": {"adx_gate": False},
        "axes": [{"key": "offset_pts", "values": [10, 11]}, {"key": "sl_pts", "values": [5, 6]}]}


def test_single_runs_and_grid_cells_share_one_cap_of_two(tmp_path, live):
    clock = Clock(et(MON, "12:00:00"))
    runs = RunManager(tmp_path, slots=Slots(tmp_path / "slots", clock=clock, poll=0.01))
    grids = GridManager(tmp_path, slots=Slots(tmp_path / "slots", clock=clock, poll=0.01))
    rid = runs.submit({"strategy": "nq930", "inputs": {"adx_gate": False}, "range": {"kind": "research"}})
    gid = grids.submit(GRID)
    assert until(lambda: live.now == 2)
    time.sleep(0.2)
    assert live.now == 2 and len(live.started) == 2                     # the rest wait for a slot
    live.release.set()
    assert until(lambda: grids.status(gid)["status"] == "done" and runs.status(rid)["status"] == "done", 10)
    assert live.peak == 2 and len(live.started) == 5


def test_a_grid_queued_in_the_quiet_window_waits_and_resumes_at_0935(tmp_path, live):
    clock = Clock(et(MON, "09:19:00"))
    grids = GridManager(tmp_path, slots=Slots(tmp_path / "slots", clock=clock, poll=0.01))
    live.release.set()
    clock.t = et(MON, "09:25:00")
    gid = grids.submit(GRID)                                            # a grid may queue; its cells wait
    time.sleep(0.3)
    st = grids.status(gid)
    assert live.started == [] and st["status"] == "queued" and st["paused"] == QUIET_MSG
    assert all(c["status"] == "queued" for c in st["cells"])
    clock.t = et(MON, "09:35:00")
    assert until(lambda: grids.status(gid)["status"] == "done")
    st = grids.status(gid)
    assert len(live.started) == 4 and "paused" not in st and st["looks"] == 4


def test_a_single_run_queued_before_0920_does_not_start_until_0935(tmp_path, live):
    clock = Clock(et(MON, "09:19:59"))
    s = Slots(tmp_path / "slots", clock=clock, poll=0.01)
    hog = [s.try_acquire(), s.try_acquire()]                            # both slots busy at 09:19:59
    runs = RunManager(tmp_path, slots=s)
    rid = runs.submit({"strategy": "nq930", "inputs": {"adx_gate": False}, "range": {"kind": "research"}})
    clock.t = et(MON, "09:22:00")
    for h in hog:
        h.close()                                                       # slots free, but it's the quiet window
    time.sleep(0.3)
    st = runs.status(rid)
    assert live.started == [] and st["status"] == "queued" and st["paused"] == QUIET_MSG
    live.release.set()
    clock.t = et(MON, "09:35:01")
    assert until(lambda: runs.status(rid)["status"] == "done")
    assert "paused" not in runs.status(rid)


def test_the_default_clock_is_the_module_clock_read_at_each_call(tmp_path, monkeypatch):
    s = Slots(tmp_path / "slots")
    monkeypatch.setattr(slots, "et_now", lambda: et(MON, "09:30:00"))
    assert s.quiet()
    monkeypatch.setattr(slots, "et_now", lambda: et(MON, "09:36:00"))
    assert not s.quiet()
