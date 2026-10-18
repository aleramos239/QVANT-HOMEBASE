"""The global backtest cap (2 processes in desk hours, 4 outside; single runs + grid cells together) and
the override file's quiet windows (no backtest STARTS inside one)."""
from __future__ import annotations

import datetime as dt
import threading
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from homebase.backtest import grid, slots
from homebase.backtest.grid import GridManager
from homebase.backtest.runner import RunManager, read_json, write_json
from homebase.backtest.slots import Slots, in_quiet

ET = ZoneInfo("America/New_York")
MON = dt.date(2026, 9, 28)          # a Monday


def et(d: dt.date, hms: str) -> dt.datetime:
    return dt.datetime.combine(d, dt.time.fromisoformat(hms), ET)


class Clock:
    def __init__(self, t: dt.datetime):
        self.t = t

    def __call__(self) -> dt.datetime:
        return self.t


def test_there_is_no_fixed_quiet_window(monkeypatch, tmp_path):
    monkeypatch.setenv("HOMEBASE_TESTER_SLOTS_FILE", str(tmp_path / "none.json"))   # no override file
    for hms in ("09:19:59", "09:20:00", "09:25:00", "09:34:59", "09:35:00"):
        assert not in_quiet(et(MON, hms))
    assert not in_quiet(dt.datetime(2026, 9, 28, 13, 25, tzinfo=dt.timezone.utc))   # 09:25 ET in September


def test_the_shared_dir_is_per_machine_and_env_overridable(tmp_path, monkeypatch, tester_shared):
    assert slots.shared_dir() == tester_shared
    monkeypatch.delenv("HOMEBASE_TESTER_SHARED")
    assert slots.shared_dir() == Path.home() / ".homebase" / "tester"
    monkeypatch.setenv("HOMEBASE_TESTER_SHARED", str(tmp_path / "x"))
    assert slots.shared_dir() == tmp_path / "x"
    assert Slots().dir == tmp_path / "x" / "slots"
    assert RunManager(tmp_path / "base").slots.dir == tmp_path / "x" / "slots"


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


def test_no_slot_starts_inside_an_override_quiet_window(tmp_path, monkeypatch):
    _ov(tmp_path, monkeypatch, {"quiet": [{"from": "2026-09-28T09:20", "to": "2026-09-28T09:35"}]})
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


def test_first_come_first_served_a_waiting_run_beats_a_greedy_grid_worker(tmp_path):
    """Review #2: a grid worker that releases and re-asks at once goes BEHIND a run already waiting."""
    s = Slots(tmp_path / "slots", cap=1, poll=0.01, clock=Clock(et(MON, "12:00:00")))
    order: list[str] = []
    grid_slot = s.acquire()
    run_got = threading.Event()

    def single_run():
        fh = s.acquire()
        order.append("run")
        run_got.set()
        time.sleep(0.1)
        fh.close()

    t = threading.Thread(target=single_run)
    t.start()
    time.sleep(0.1)                                   # the run is queued behind the grid's slot
    grid_slot.close()
    again = s.acquire()                               # the grid worker asks again immediately
    order.append("grid")
    again.close()
    t.join(2)
    assert order == ["run", "grid"] and run_got.is_set()


def test_waiters_are_served_in_arrival_order_and_dead_tickets_are_skipped(tmp_path):
    s = Slots(tmp_path / "slots", cap=1, poll=0.01, clock=Clock(et(MON, "12:00:00")))
    q = tmp_path / "slots" / "queue"
    q.mkdir(parents=True, exist_ok=True)
    (q / f"{1:020d}-999999-000001").touch()           # a ticket left by a dead process: ignored + removed
    held = s.acquire()
    assert held is not None and not (q / f"{1:020d}-999999-000001").exists()
    order: list[int] = []

    def waiter(k):
        fh = s.acquire()
        order.append(k)
        time.sleep(0.05)
        fh.close()

    ts = []
    for k in range(3):
        ts.append(threading.Thread(target=waiter, args=(k,)))
        ts[-1].start()
        time.sleep(0.05)
    held.close()
    for t in ts:
        t.join(3)
    assert order == [0, 1, 2]
    assert list(q.iterdir()) == []                    # every ticket cleaned up


def test_a_slot_passed_to_a_child_is_held_as_long_as_the_child_lives(tmp_path):
    import subprocess
    import sys
    s = Slots(tmp_path / "slots", cap=1, clock=Clock(et(MON, "12:00:00")))
    fh = s.acquire()
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1.0)"], pass_fds=(fh.fileno(),))
    fh.close()                                        # the parent's copy is gone ...
    assert s.try_acquire() is None                    # ... the child still holds the slot
    child.wait()
    got = s.try_acquire()
    assert got is not None
    got.close()


def test_runner_exec_takes_its_own_slot_unless_it_inherited_one(tmp_path, monkeypatch):
    from homebase.backtest import runner
    from tests.backtest_util import nq_archive
    monkeypatch.setattr(runner.os, "nice", lambda n: 0)      # exec renices itself; not the test process
    archive = nq_archive(tmp_path / "ticks")
    rid = runner.prepare({"strategy": "nq930", "inputs": {"adx_gate": False}, "range": {"kind": "research"}}, tmp_path)
    d = tmp_path / "runs" / rid
    argv = ["exec", str(d), "--archive", str(archive), "--cache", str(tmp_path / "cache")]
    # a child the managers launched inherited its slot: no second slot
    inherited = Slots(clock=Clock(et(MON, "09:19:00"))).try_acquire()
    assert runner.main(argv + ["--slot-fd", str(inherited.fileno())]) == 0
    inherited.close()
    assert read_json(d / "status.json")["status"] == "done"
    # a bare exec waits for a free slot like everything else
    monkeypatch.setattr(slots, "et_now", lambda: et(MON, "12:00:00"))
    hog = [Slots().try_acquire(), Slots().try_acquire()]
    rid2 = runner.prepare({"strategy": "nq930", "inputs": {"adx_gate": False}, "range": {"kind": "research"}}, tmp_path)
    d2 = tmp_path / "runs" / rid2
    out: list = []
    t = threading.Thread(target=lambda: out.append(runner.main(["exec", str(d2), "--archive", str(archive),
                                                                "--cache", str(tmp_path / "cache")])))
    t.start()
    time.sleep(0.8)
    assert out == [] and read_json(d2 / "status.json")["status"] == "queued"
    for h in hog:
        h.close()
    t.join(20)
    assert out == [0] and read_json(d2 / "status.json")["status"] == "done"


# ---------------------------------------------------------------- fake children for both managers

class Live:
    def __init__(self):
        self.lock, self.now, self.peak, self.release = threading.Lock(), 0, 0, threading.Event()
        self.started: list[str] = []


class FakeChild:
    def __init__(self, argv, live: Live, kw: dict | None = None):
        if kw is not None:
            fd = int(argv[argv.index("--slot-fd") + 1])
            assert kw.get("pass_fds") == (fd,), "the child must hold its own slot"
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
    monkeypatch.setattr(grid.subprocess, "Popen", lambda argv, **kw: FakeChild(argv, lv, kw))
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


RUN = {"strategy": "nq930", "inputs": {"adx_gate": False}, "range": {"kind": "research"}}


def _ids(live):
    return [Path(d).name for d in live.started]


def test_single_runs_take_free_slots_side_by_side_and_the_next_waits_its_turn(tmp_path, live):
    clock = Clock(et(MON, "12:00:00"))                                  # desk hours: the cap is 2
    runs = RunManager(tmp_path, slots=Slots(tmp_path / "slots", clock=clock, poll=0.01))
    a, b, c = runs.submit(RUN), runs.submit(RUN), runs.submit(RUN)
    assert until(lambda: live.now == 2)
    time.sleep(0.2)
    assert live.now == 2 and _ids(live) == [a, b]                       # two at once, first come first served
    assert runs.status(c)["status"] == "queued" and runs.status(c)["queue_position"] == 1
    assert "queue_position" not in runs.status(a) and "queue_position" not in runs.status(b)
    live.release.set()
    assert until(lambda: all(runs.status(r)["status"] == "done" for r in (a, b, c)), 10)
    assert live.peak == 2 and _ids(live) == [a, b, c]


def test_off_hours_four_single_runs_run_at_once_and_never_more(tmp_path, live):
    clock = Clock(et(MON, "20:00:00"))
    runs = RunManager(tmp_path, slots=Slots(tmp_path / "slots", clock=clock, poll=0.01))
    rids = [runs.submit(RUN) for _ in range(6)]
    assert until(lambda: live.now == 4)
    time.sleep(0.2)
    assert live.now == 4 and _ids(live) == rids[:4]
    live.release.set()
    assert until(lambda: all(runs.status(r)["status"] == "done" for r in rids), 10)
    assert live.peak == 4


def test_cancelling_one_of_two_running_runs_stops_only_that_one(tmp_path, live):
    clock = Clock(et(MON, "12:00:00"))
    runs = RunManager(tmp_path, slots=Slots(tmp_path / "slots", clock=clock, poll=0.01))
    a, b = runs.submit(RUN), runs.submit(RUN)
    assert until(lambda: live.now == 2)
    assert runs.cancel(a)["status"] == "cancelled" and live.now == 1
    live.release.set()
    assert until(lambda: runs.status(b)["status"] == "done", 10)
    assert until(lambda: not runs._procs)
    assert runs.status(a)["status"] == "cancelled"                      # its worker did not overwrite it


def test_shutdown_stops_every_running_single_run(tmp_path, live):
    clock = Clock(et(MON, "12:00:00"))
    runs = RunManager(tmp_path, slots=Slots(tmp_path / "slots", clock=clock, poll=0.01))
    a, b = runs.submit(RUN), runs.submit(RUN)
    assert until(lambda: live.now == 2)
    runs.shutdown()
    assert live.now == 0 and runs.status(a)["status"] == runs.status(b)["status"] == "cancelled"
    live.release.set()


def test_the_default_clock_is_the_module_clock_read_at_each_call(tmp_path, monkeypatch):
    s = Slots(tmp_path / "slots")
    monkeypatch.setattr(slots, "et_now", lambda: et(MON, "12:00:00"))
    assert s.cap == 2                                                    # desk hours
    monkeypatch.setattr(slots, "et_now", lambda: et(MON, "20:00:00"))
    assert s.cap == 4


def test_the_cap_is_two_in_desk_hours_and_four_off_hours(tmp_path):
    from homebase.backtest.slots import cap_at
    assert cap_at(et(MON, "08:00:00")) == 2 and cap_at(et(MON, "16:14:59")) == 2
    assert cap_at(et(MON, "07:59:59")) == 4 and cap_at(et(MON, "16:15:00")) == 4
    assert cap_at(et(MON + dt.timedelta(days=5), "12:00:00")) == 4        # Saturday
    clock = Clock(et(MON, "20:00:00"))
    s = Slots(tmp_path / "slots", clock=clock)
    held = [s.try_acquire() for _ in range(4)]
    assert all(h is not None for h in held) and s.try_acquire() is None
    clock.t = et(MON + dt.timedelta(days=1), "10:00:00")                  # desk hours: only slots 0-1 are handed out
    for h in held:
        h.close()
    a, b = s.try_acquire(), s.try_acquire()
    assert a is not None and b is not None and s.try_acquire() is None
    a.close(); b.close()
    assert Slots(tmp_path / "slots", cap=1, clock=clock).cap == 1           # a pinned cap wins


# ---- runtime override (~/.homebase/tester_slots.json) ----
import json   # noqa: E402

FRI = dt.date(2026, 10, 2)


def _ov(tmp_path, monkeypatch, body):
    f = tmp_path / "ov.json"
    f.write_text(json.dumps(body))
    monkeypatch.setenv("HOMEBASE_TESTER_SLOTS_FILE", str(f))
    return f


def test_override_raises_the_cap_in_desk_hours_until_its_end(tmp_path, monkeypatch):
    assert slots.cap_at(et(MON, "11:00")) == 2
    _ov(tmp_path, monkeypatch, {"cap": 4, "until": "2026-10-05T08:00"})
    assert slots.cap_at(et(FRI, "11:00")) == 4
    assert slots.cap_at(et(dt.date(2026, 10, 5), "07:59:59")) == 4
    assert slots.cap_at(et(dt.date(2026, 10, 5), "08:00")) == 2          # expired: back to the default
    assert slots.cap_at(et(dt.date(2026, 10, 5), "20:00")) == 4


def test_override_quiet_window_blocks_starts(tmp_path, monkeypatch):
    _ov(tmp_path, monkeypatch, {"quiet": [{"from": "2026-10-02T08:15", "to": "2026-10-02T08:45"}]})
    assert not in_quiet(et(FRI, "08:14:59"))
    assert in_quiet(et(FRI, "08:15"))
    assert in_quiet(et(FRI, "08:44:59"))
    assert not in_quiet(et(FRI, "08:45"))
    assert not in_quiet(et(FRI, "09:25"))                                # no fixed 09:20-09:35 rule any more
    assert not in_quiet(et(MON + dt.timedelta(days=7 + 4), "08:30"))     # other days unaffected
    assert Slots(tmp_path / "s", clock=Clock(et(FRI, "08:30"))).try_acquire() is None


def test_override_is_reread_when_the_file_changes_and_ignored_when_broken(tmp_path, monkeypatch):
    f = _ov(tmp_path, monkeypatch, {"cap": 4, "until": "2026-10-05T08:00"})
    assert slots.cap_at(et(FRI, "11:00")) == 4
    f.write_text(json.dumps({"cap": 3, "until": "2026-10-05T08:00", "x": "pad"}))
    assert slots.cap_at(et(FRI, "11:00")) == 3
    f.write_text("{not json")
    assert slots.cap_at(et(FRI, "11:00")) == 2
    f.unlink()
    assert slots.cap_at(et(FRI, "11:00")) == 2
