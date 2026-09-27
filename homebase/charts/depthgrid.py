"""The liquidity heatmap's history (2026-09-27 charts-l2-news-ui plan, Task 3):
the recorded depth files (depth.py's format) read back as a down-sampled grid
for GET /api/depth/history.

    {"t0": ms, "dt_ms": ms, "tick": tick, "prices": [lo, hi] | null,
     "cells": [[t_idx, price_idx, size], ...]}

Column t_idx covers [t0 + t_idx*dt_ms, t0 + (t_idx+1)*dt_ms) and shows the book
in force at its end: the last recorded line before it, held at most HOLD_MS
(the recorder writes only on change, so a longer silence is a recording gap and
stays blank). price = lo + price_idx * tick. At most MAX_COLS columns, never
finer than BIN_MS, never past now, and at most MAX_BYTES of JSON: over it,
each column keeps only its largest levels.

Where it runs (review C1): never in the chart service's process. HistoryPool
hands every request to ONE spawned worker process (child_grid), which keeps the
decoded files cached; a request arriving while another is in the worker is
answered Busy (503), never queued, and a dead worker is replaced on the next
request. Read-only: nothing here writes anywhere.

Inside the worker, DepthHistory decodes a file one gzip member at a time
(parsed, then dropped: no whole-day transient) into int32 arrays, cached per
path while its (inode, mtime, size) holds; a file that only grew decodes just
its new members, a rewritten one (the recorder's torn-tail repair, a new inode)
from the start. The paused windows -- 09:20-09:35 ET (tickfeed's quiet window)
and 08:29:30-08:31:00 ET on weekdays (the data releases) -- are checked before
the request and between members: Paused, answered 503, and the next request
resumes the file where it stopped.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import math
import multiprocessing
import threading
import time
import zlib
from array import array
from bisect import bisect_left
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import Callable, Optional

from ..contracts import tick_size as contract_tick_size
from . import QUIET
from .session import ET, session_date

SUFFIX = ".depth.jsonl.gz"     # depth.py's (not imported: the worker never loads the md feed's modules)

BIN_MS = 1000                  # a file is kept as its last book per second; the finest column
HOLD_MS = 300_000              # a book is held this long past its line, never longer (a gap stays blank)
MAX_COLS = 600
MAX_SPAN_MS = 72 * 3_600_000   # one request covers at most 3 days (a handful of day files)
MAX_BYTES = 2 * 1024 * 1024    # the response's JSON, at most
CACHE_FILES = 4                # decoded files kept in the worker (int32 arrays: ~14 MB for a full NQ day)
RELEASE = (dt.time(8, 29, 30), dt.time(8, 31))   # weekdays: the 08:30 ET data releases
BUSY = "busy — try again in a moment"
_READ_CHUNK = 1 << 16


class Paused(Exception):
    """A paused window: no file is read. The message is the 503's detail."""


class Busy(Exception):
    """The worker is on another request (or was just replaced): 503, never queued."""


def paused_reason(ts_s: float) -> Optional[str]:
    """Why history decoding is paused at epoch time ts_s, or None."""
    t = dt.datetime.fromtimestamp(ts_s, ET)
    if QUIET[0] <= t.time() < QUIET[1]:
        return "paused for the 9:30 window"
    if t.weekday() < 5 and RELEASE[0] <= t.time() < RELEASE[1]:
        return "paused for the 8:30 data release"
    return None


def _members(raw: bytes, base: int = 0):
    """Yield (the text of each complete gzip member, the offset just past it), in
    order, stopping at the first torn one. Chunked, like depth._scan; each member
    is handed out as it is decompressed, never all of them at once."""
    mv, pos, n = memoryview(raw), 0, len(raw)
    while pos < n:
        d, parts = zlib.decompressobj(wbits=31), []
        while not d.eof and pos < n:
            chunk = mv[pos:pos + _READ_CHUNK]
            try:
                parts.append(d.decompress(chunk))
            except zlib.error:
                return
            pos += len(chunk) - len(d.unused_data)
        if not d.eof:
            return
        yield b"".join(parts), base + pos


def _parse_member(raw: bytes) -> list[dict]:
    out = []
    for ln in raw.decode("utf-8", "replace").splitlines():
        try:
            v = json.loads(ln)
        except ValueError:
            continue
        if isinstance(v, dict):
            out.append(v)
    return out


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


class _File:
    """One depth file as arrays: its last book per BIN_MS (times ascending),
    each level as (tick index, size)."""

    def __init__(self, ino: int):
        self.ino, self.mtime, self.size, self.pos = ino, None, None, 0
        self.ts = array("q")
        self.off = array("i", [0])
        self.px = array("i")                      # tick index: NQ at 30,000 is 120,000, far inside int32
        self.sz = array("i")

    def add(self, v: dict, tick: float) -> None:
        t = v.get("t")
        if not _finite(t):
            return
        t = int(t)
        if self.ts:
            if t < self.ts[-1]:
                return                                   # keep the times sorted: a stray older line is dropped
            if t // BIN_MS == self.ts[-1] // BIN_MS:     # same second: the later book replaces it
                start = self.off[-2]
                del self.px[start:], self.sz[start:]
                self.ts.pop()
                self.off.pop()
        for side in ("b", "a"):
            lv = v.get(side)
            for row in lv if isinstance(lv, list) else ():
                if not isinstance(row, list) or len(row) < 2 or not _finite(row[0]) or not _finite(row[1]):
                    continue
                s, px = int(round(row[1])), int(round(row[0] / tick))
                if s <= 0 or s >= 2 ** 31 or abs(px) >= 2 ** 31:
                    continue
                self.px.append(px)
                self.sz.append(s)
        self.ts.append(t)
        self.off.append(len(self.px))

    def book_at(self, end: int):
        """The index of the last book strictly before `end`, or -1."""
        return bisect_left(self.ts, end) - 1


class DepthHistory:
    def __init__(self, base: Path, tick_of: Callable[[str], float], quiet: Callable[[], bool] = lambda: False,
                 cache_files: int = CACHE_FILES, reason: Callable[[], Optional[str]] = lambda: None):
        self.base = Path(base)
        self.tick_of = tick_of
        self.quiet = quiet
        self.reason = lambda: reason() or "paused for the 9:30 window"
        self.cache_files = cache_files
        self._cache: OrderedDict[Path, _File] = OrderedDict()
        self._lock = threading.Lock()

    # ---- files

    def files(self, root: str, frm: int, to: int) -> list[Path]:
        """The day file of each session touching [frm, to), oldest first. A
        session with two contracts' files (a roll day) takes the larger."""
        out = []
        d, last = session_date(frm, root), session_date(to - 1, root)
        while d <= last:
            found = [p for p in (self.base / root / str(d.year)).glob(f"{d.isoformat()}_*{SUFFIX}") if p.is_file()]
            if found:
                out.append(max(found, key=lambda p: (p.stat().st_size, p.name)))
            d += dt.timedelta(days=1)
        return out

    def _load(self, path: Path, tick: float) -> _File:
        st = path.stat()
        f = self._cache.get(path)
        if f is not None and (f.ino, f.mtime, f.size) == (st.st_ino, st.st_mtime_ns, st.st_size):
            self._cache.move_to_end(path)
            return f
        if self.quiet():
            raise Paused(self.reason())
        if f is None or f.ino != st.st_ino or st.st_size < f.pos:
            f = _File(st.st_ino)                          # new, or rewritten: from the start
        self._cache[path] = f                             # kept even if paused part-way: the next call resumes
        self._cache.move_to_end(path)
        while len(self._cache) > self.cache_files:
            self._cache.popitem(last=False)
        with open(path, "rb") as fh:
            fh.seek(f.pos)
            raw = fh.read(max(0, st.st_size - f.pos))
        for text, end in _members(raw, f.pos):
            if self.quiet():
                raise Paused(self.reason())
            for v in _parse_member(text):
                f.add(v, tick)
            f.pos = end                                   # a torn tail is read again once it is whole
        f.mtime, f.size = st.st_mtime_ns, st.st_size
        return f

    # ---- the grid

    def grid(self, root: str, frm: int, to: int, cols: int, now_ms: int | None = None) -> bytes:
        """The grid as JSON bytes. ValueError: a bad root or range. Paused: the 9:30 window."""
        if not root.isalnum():
            raise ValueError(f"bad root {root!r}")
        frm, to = int(frm), int(to)
        if to <= frm:
            raise ValueError("to_ms must be after from_ms")
        if to - frm > MAX_SPAN_MS:
            raise ValueError(f"at most {MAX_SPAN_MS // 3_600_000} h per request")
        tick = float(self.tick_of(root))
        cols = max(1, min(MAX_COLS, int(cols)))
        step = max(BIN_MS, -(-(to - frm) // cols))
        if now_ms is not None:
            to = min(to, int(now_ms))
        columns = []                                      # per column: [(tick index, size), ...]
        with self._lock:                                  # (the cached arrays grow under it, too)
            if self.quiet():
                raise Paused(self.reason())
            loaded = [self._load(p, tick) for p in self.files(root, frm, to)] if to > frm else []
            n = -(-(to - frm) // step) if to > frm else 0
            for c in range(n):
                end = min(frm + (c + 1) * step, to)
                levels = []
                for f in reversed(loaded):               # later sessions hold later times
                    i = f.book_at(end)
                    if i < 0:
                        continue
                    if end - f.ts[i] <= HOLD_MS:
                        a, b = f.off[i], f.off[i + 1]
                        levels = list(zip(f.px[a:b], f.sz[a:b]))
                    break
                columns.append(levels)
        return _encode(frm, step, tick, columns)


def _encode(t0: int, step: int, tick: float, columns: list[list[tuple[int, int]]]) -> bytes:
    """The JSON, at most MAX_BYTES: over it, every column keeps only its k
    largest levels, k halved until it fits."""
    k = max((len(c) for c in columns), default=0)
    while True:
        cols = columns if k >= max((len(c) for c in columns), default=0) else \
            [sorted(c, key=lambda x: -x[1])[:k] for c in columns]
        idx = [p for c in cols for p, _ in c]
        body = {"t0": t0, "dt_ms": step, "tick": tick, "prices": None, "cells": []}
        if idx:
            lo, hi = min(idx), max(idx)
            body["prices"] = [round(lo * tick, 10), round(hi * tick, 10)]
            body["cells"] = [[ci, p - lo, s] for ci, c in enumerate(cols) for p, s in c]
        raw = json.dumps(body, separators=(",", ":")).encode()
        if len(raw) <= MAX_BYTES or k == 0:
            return raw
        k //= 2


# ------------------------------------------------------------------ the worker process

_HIST: dict[str, DepthHistory] = {}      # (in the worker) base -> its DepthHistory and cache
_OFFSET_MS = [0.0]                       # (in the worker) the service clock minus the wall clock, per request


def _worker_reason() -> Optional[str]:
    return paused_reason((time.time() * 1000 + _OFFSET_MS[0]) / 1000)


def child_grid(base: str, root: str, frm: int, to: int, cols: int, now_ms: int, offset_ms: float) -> bytes:
    """(the worker) DepthHistory.grid with the worker's own cache; the paused
    windows by the service's clock (offset_ms: tests and a replay's wall)."""
    _OFFSET_MS[0] = offset_ms
    h = _HIST.get(base)
    if h is None:
        h = _HIST[base] = DepthHistory(Path(base), contract_tick_size,
                                       quiet=lambda: _worker_reason() is not None, reason=_worker_reason)
    return h.grid(root, frm, to, cols, now_ms=now_ms)


def _spawn_pool():
    return ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))


class HistoryPool:
    """(the service) One worker process, started on the first request, one
    request at a time: a second one while the worker is busy is Busy, never
    queued. A worker that died is shut down and replaced on the next request."""

    def __init__(self, base: Path, executor_factory: Callable[[], object] = _spawn_pool):
        self.base = str(base)
        self._factory = executor_factory
        self._ex = None
        self._busy = False

    async def grid(self, root: str, frm: int, to: int, cols: int, now_ms: int, offset_ms: float = 0.0) -> bytes:
        if self._busy:
            raise Busy(BUSY)
        self._busy = True
        try:
            if self._ex is None:
                self._ex = self._factory()
            ex = self._ex
            try:
                fut = ex.submit(child_grid, self.base, root, frm, to, cols, now_ms, offset_ms)
                return await asyncio.wrap_future(fut)
            except BrokenProcessPool:
                if self._ex is ex:
                    self._ex = None
                ex.shutdown(wait=False, cancel_futures=True)
                raise Busy(BUSY) from None
        finally:
            self._busy = False

    def shutdown(self) -> None:
        ex, self._ex = self._ex, None
        if ex is not None:
            ex.shutdown(wait=False, cancel_futures=True)
