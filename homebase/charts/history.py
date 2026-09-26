"""Bars of COMPLETED sessions, fast.

Two caches over the TickStore: a per-session 1-minute bar pickle on disk
(built once from ticks; every time bar >= 1m is resampled from it, so a
60-session daily chart never re-reads ticks) and an in-memory memo per
(root, bar type, date). Today's session is the hub's job, not this file's.
Thread-safe: the hub calls it from worker threads.
"""
from __future__ import annotations

import datetime as dt
import os
import pickle
import threading
from collections import OrderedDict
from pathlib import Path

from ..contracts import tick_size
from ..paths import state_dir
from .bars import Bar, BarSpec, build, resample
from .session import et_wall_s
from .store import TickStore

M1 = BarSpec("time", 60)
CACHE_VERSION = 1


class History:
    def __init__(self, store: TickStore, cache_dir: Path | None = None, memo_max: int = 256):
        self.store = store
        self.cache_dir = Path(cache_dir) if cache_dir else state_dir() / "charts" / "cache"
        self.memo: OrderedDict = OrderedDict()
        self.memo_max = memo_max
        self._lock = threading.Lock()
        self._gen = 0           # bumped by clear(): a build that overlapped a clear() is not memoized

    def _from_ticks(self, root: str, spec: BarSpec, d: dt.date) -> list[Bar]:
        s = self.store.load(root, d)
        if s is None:
            return []
        closed, cur = build(s.ticks, spec, tick_size(root), root)
        if cur is not None:
            cur.closed = True
            closed.append(cur)
        return closed

    def minutes(self, root: str, d: dt.date) -> list[Bar]:
        f = self.store.pick(root, d)
        if f is None:
            return []
        cp = self.cache_dir / (f"v{CACHE_VERSION}_{root}_{d.isoformat()}_{f.contract}_"
                               f"{'live' if f.live else 'arch'}.m1.pkl")
        src_ns = None
        try:
            src_ns = f.path.stat().st_mtime_ns          # the source BEFORE its ticks are read
            if cp.stat().st_mtime_ns >= src_ns:
                with open(cp, "rb") as fh:
                    return pickle.load(fh)
        except (OSError, pickle.UnpicklingError, EOFError):
            pass
        bars = self._from_ticks(root, M1, d)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = cp.with_name(cp.name + f".{threading.get_ident()}.tmp")
        with open(tmp, "wb") as fh:
            pickle.dump(bars, fh, protocol=pickle.HIGHEST_PROTOCOL)
        if src_ns is not None:
            # stamped with the source as read: a write that lands mid-build (a
            # refill into an old session) leaves the cache older than its source
            os.utime(tmp, ns=(src_ns, src_ns))
        os.replace(tmp, cp)
        return bars

    def bars(self, root: str, spec: BarSpec, d: dt.date) -> list[Bar]:
        key = (root, spec.key, d)
        with self._lock:
            hit = self.memo.get(key)
            if hit is not None:
                self.memo.move_to_end(key)
                return hit
            gen = self._gen
        out = resample(self.minutes(root, d), spec) if spec.from_minutes else self._from_ticks(root, spec, d)
        with self._lock:
            if gen == self._gen:        # else a clear() landed mid-build: its file may have changed
                self.memo[key] = out
                while len(self.memo) > self.memo_max:
                    self.memo.popitem(last=False)
        return out

    def info(self, root: str, d: dt.date) -> dict:
        """What the page needs to label a session honestly. Cheap: no ticks read."""
        f = self.store.pick(root, d)
        if f is None:
            return {"date": d.isoformat(), "contract": None, "source": None, "approx": False, "gaps": []}
        return {"date": d.isoformat(), "contract": f.contract,
                "source": "live" if f.live else "archive", "approx": not f.bid_ask,
                "gaps": [[et_wall_s(a), et_wall_s(b)] for a, b in self.store.gaps(f)]}

    def clear(self) -> None:
        with self._lock:
            self.memo.clear()
            self._gen += 1
