"""The machine-wide backtest budget: at most CAP backtest processes at once (CAP_OFF_HOURS outside
desk hours, weekdays 08:00-16:15 ET -- a run holding a higher slot when desk hours begin finishes;
no new one takes it) -- single tester runs,
heat-map cells and script runs together, from EVERY checkout on this machine -- and none STARTS
in the QUIET window (09:20-09:35 ET, weekdays), because the live desk's 9:30 bot shares the
machine. A run already going keeps going; anything queued waits until 09:35.

State lives in one fixed per-machine dir, `shared_dir()` = ~/.homebase/tester (the env var
HOMEBASE_TESTER_SHARED overrides it; the test suite always points it at a tmp dir):

  slots/<k>.lock      a slot = an exclusive flock on one of these CAP files
  slots/queue/<t>     a waiter's ticket: "<ns>-<pid>-<seq>"; the oldest live ticket goes first
  looks.json          the heat-map looks counter (grid.py)

First come, first served: a waiter takes a ticket and only the oldest live ticket may take a
free slot, so a grid worker that releases and immediately re-asks queues BEHIND a run that was
already waiting. A ticket whose pid is dead is removed. The launcher passes the slot's fd to its
child (Popen pass_fds + `runner exec --slot-fd N`): flock belongs to the open file, so the lock
lives exactly as long as the backtest process, even if the launcher dies first.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import threading
import time
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
CAP = 2                                        # during desk hours (weekdays 08:00-16:15 ET)
CAP_OFF_HOURS = 4                              # evenings, nights and weekends: the desk is idle
DESK_HOURS = (dt.time(8, 0), dt.time(16, 15))  # [start, end) ET, Mon-Fri (covers the 08:30 GC event bot)
QUIET = (dt.time(9, 20), dt.time(9, 35))      # [start, end) ET, Mon-Fri
QUIET_MSG = "paused for the 9:30 window"
QUIET_REFUSAL = f"{QUIET_MSG}: no backtest starts 09:20–09:35 ET on weekdays"
ENV = "HOMEBASE_TESTER_SHARED"
OVERRIDE_ENV = "HOMEBASE_TESTER_SLOTS_FILE"


def shared_dir() -> Path:
    v = os.environ.get(ENV)
    return Path(v) if v else Path.home() / ".homebase" / "tester"


def et_now() -> dt.datetime:
    return dt.datetime.now(ET)


def override_path() -> Path:
    v = os.environ.get(OVERRIDE_ENV)
    return Path(v) if v else Path.home() / ".homebase" / "tester_slots.json"


_ov_cache: list = [None, None, {}]      # [path, (mtime_ns, size), parsed]


def _et(v) -> dt.datetime:
    d = dt.datetime.fromisoformat(str(v))
    return d if d.tzinfo else d.replace(tzinfo=ET)


def override() -> dict:
    """The runtime override file (no restart needed; re-read only when it changes on disk):
      {"cap": 4, "until": "2026-10-05T08:00",                       # cap for ALL hours until then
       "quiet": [{"from": "2026-10-02T08:15", "to": "2026-10-02T08:45"}]}   # extra no-start windows
    Times without an offset are ET. Missing or broken file = no override."""
    p = override_path()
    try:
        st = p.stat()
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        _ov_cache[:] = [str(p), None, {}]
        return {}
    if _ov_cache[0] == str(p) and _ov_cache[1] == key:
        return _ov_cache[2]
    try:
        raw = json.loads(p.read_text())
        out: dict = {}
        if raw.get("cap") is not None and raw.get("until"):
            out["cap"], out["until"] = max(1, int(raw["cap"])), _et(raw["until"])
        out["quiet"] = [(_et(w["from"]), _et(w["to"])) for w in raw.get("quiet", [])]
    except Exception:
        out = {}
    _ov_cache[:] = [str(p), key, out]
    return out


def cap_at(now: dt.datetime) -> int:
    """The machine-wide cap in force at `now`: the override's cap until its `until`; else CAP while
    the desk trades, CAP_OFF_HOURS otherwise."""
    t = now.astimezone(ET) if now.tzinfo else now.replace(tzinfo=ET)
    ov = override()
    if "cap" in ov and t < ov["until"]:
        return ov["cap"]
    desk = t.weekday() < 5 and DESK_HOURS[0] <= t.time() < DESK_HOURS[1]
    return CAP if desk else CAP_OFF_HOURS


def quiet_end(now: dt.datetime) -> dt.datetime | None:
    """When the no-start window containing `now` ends (default 09:20-09:35 weekdays plus the
    override's windows, chained), or None if `now` is not quiet."""
    t = now.astimezone(ET) if now.tzinfo else now.replace(tzinfo=ET)
    wins = [(a, b) for a, b in override().get("quiet", [])]
    if t.weekday() < 5:
        wins.append((dt.datetime.combine(t.date(), QUIET[0], ET), dt.datetime.combine(t.date(), QUIET[1], ET)))
    end = None
    moved = True
    while moved:
        moved = False
        for a, b in wins:
            if a <= t < b and (end is None or b > end):
                end, t, moved = b, b, True
    return end


def in_quiet(now: dt.datetime) -> bool:
    return quiet_end(now) is not None


_seq_lock = threading.Lock()
_last = [0, 0]      # [ns, seq]: tickets from this process are strictly increasing


def _ticket_name() -> str:
    with _seq_lock:
        ns = max(time.time_ns(), _last[0] + 1)
        _last[0], _last[1] = ns, _last[1] + 1
        return f"{ns:020d}-{os.getpid()}-{_last[1]:06d}"


def _alive(pid: int) -> bool:
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class Slots:
    def __init__(self, d: Path | None = None, *, cap: int | None = None,
                 clock: Callable[[], dt.datetime] | None = None, poll: float = 0.5):
        # d None: the per-machine slots dir. clock None: the module's et_now, looked up at each call.
        # cap None: the time-of-day cap (cap_at); a number pins it (tests).
        self.dir = Path(d) if d is not None else shared_dir() / "slots"
        self.fixed_cap, self.poll = cap, poll
        self.clock = clock or (lambda: et_now())
        self.queue = self.dir / "queue"
        self.queue.mkdir(parents=True, exist_ok=True)

    def quiet(self) -> bool:
        return in_quiet(self.clock())

    @property
    def cap(self) -> int:
        return self.fixed_cap if self.fixed_cap is not None else cap_at(self.clock())

    def try_acquire(self):
        """An open file holding a slot (close() it to release), or None: the cap is full or it's
        QUIET. Ignores the waiting line -- acquire() is the fair way in."""
        if self.quiet():
            return None
        for k in range(self.cap):
            fh = open(self.dir / f"{k}.lock", "a")
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fh
            except BlockingIOError:
                fh.close()
        return None

    def _head(self) -> str | None:
        """The oldest ticket whose process is alive (dead ones are removed)."""
        for name in sorted(os.listdir(self.queue)):
            try:
                pid = int(name.split("-")[1])
            except (IndexError, ValueError):
                pid = -1
            if pid > 0 and _alive(pid):
                return name
            try:
                (self.queue / name).unlink()
            except FileNotFoundError:
                pass
        return None

    def acquire(self, cancelled: Callable[[], bool] = lambda: False):
        """Wait in line for a slot outside the QUIET window; None once `cancelled()` turns true."""
        me = _ticket_name()
        (self.queue / me).touch()
        try:
            while not cancelled():
                if self._head() == me:
                    fh = self.try_acquire()
                    if fh is not None:
                        return fh
                time.sleep(self.poll)
            return None
        finally:
            try:
                (self.queue / me).unlink()
            except FileNotFoundError:
                pass


def held(fd: int) -> bool:
    """True when `fd` is an open file this process inherited (a slot passed by its launcher)."""
    try:
        os.fstat(fd)
        return True
    except OSError:
        return False
