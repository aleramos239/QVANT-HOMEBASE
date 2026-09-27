"""The machine-wide backtest budget: at most CAP backtest processes at once -- single tester runs
and heat-map cells together -- and none STARTS in the QUIET window (09:20-09:35 ET, weekdays),
because the live desk's 9:30 bot shares the machine. A run already going keeps going; anything
queued waits until 09:35.

A slot is an exclusive flock on <base>/slots/<k>.lock, held by whoever launched the child until
it exits. flock is per open file, so every holder of the same directory -- the RunManager, the
GridManager, a script run in another process -- shares one cap.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import time
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
CAP = 2
QUIET = (dt.time(9, 20), dt.time(9, 35))      # [start, end) ET, Mon-Fri
QUIET_MSG = "paused for the 9:30 window"
QUIET_REFUSAL = f"{QUIET_MSG}: no backtest starts 09:20–09:35 ET on weekdays"


def et_now() -> dt.datetime:
    return dt.datetime.now(ET)


def in_quiet(now: dt.datetime) -> bool:
    t = now.astimezone(ET) if now.tzinfo else now
    return t.weekday() < 5 and QUIET[0] <= t.time() < QUIET[1]


class Slots:
    def __init__(self, d: Path, *, cap: int = CAP, clock: Callable[[], dt.datetime] | None = None, poll: float = 0.5):
        # clock None: the module's et_now, looked up at each call (the test suite pins it outside QUIET)
        self.dir, self.cap, self.poll = Path(d), cap, poll
        self.clock = clock or (lambda: et_now())
        self.dir.mkdir(parents=True, exist_ok=True)

    def quiet(self) -> bool:
        return in_quiet(self.clock())

    def try_acquire(self):
        """An open file holding a slot (close() it to release), or None: the cap is full or it's QUIET."""
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

    def acquire(self, cancelled: Callable[[], bool] = lambda: False):
        """Wait for a slot outside the QUIET window; None once `cancelled()` turns true."""
        while not cancelled():
            fh = self.try_acquire()
            if fh is not None:
                return fh
            time.sleep(self.poll)
        return None
