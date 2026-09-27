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

Read-only: nothing here writes anywhere. Every call is meant for a worker
thread (asyncio.to_thread), and one runs at a time (a lock). A decoded file is
cached per path and reused while its (inode, mtime, size) holds; a file that
only grew (the recorder appends one gzip member per flush) decodes just its new
members, and a rewritten one (the recorder's torn-tail repair, a new inode) is
decoded again. Inside the 09:20-09:35 ET window (`quiet`) no file is read at
all: Paused, which the route answers 503.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import threading
import zlib
from array import array
from bisect import bisect_left
from collections import OrderedDict
from pathlib import Path
from typing import Callable

from .depth import SUFFIX
from .session import session_date

BIN_MS = 1000                  # a file is kept as its last book per second; the finest column
HOLD_MS = 300_000              # a book is held this long past its line, never longer (a gap stays blank)
MAX_COLS = 600
MAX_SPAN_MS = 72 * 3_600_000   # one request covers at most 3 days (a handful of day files)
MAX_BYTES = 2 * 1024 * 1024    # the response's JSON, at most
CACHE_FILES = 4                # decoded files kept (a full NQ day ~ 13 MB of arrays)
_READ_CHUNK = 1 << 16


class Paused(Exception):
    """The 09:20-09:35 ET window: no file is read."""


def _members(raw: bytes) -> tuple[list[bytes], int]:
    """(the text of each complete gzip member in order, up to the first torn
    one; the bytes those complete members take). Chunked, like depth._scan."""
    mv, pos, n, out = memoryview(raw), 0, len(raw), []
    while pos < n:
        d, parts, start = zlib.decompressobj(wbits=31), [], pos
        while not d.eof and pos < n:
            chunk = mv[pos:pos + _READ_CHUNK]
            try:
                parts.append(d.decompress(chunk))
            except zlib.error:
                return out, start
            pos += len(chunk) - len(d.unused_data)
        if not d.eof:
            return out, start
        out.append(b"".join(parts))
    return out, pos


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
        self.off = array("q", [0])
        self.px = array("q")
        self.sz = array("q")

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
                s = int(round(row[1]))
                if s <= 0:
                    continue
                self.px.append(int(round(row[0] / tick)))
                self.sz.append(s)
        self.ts.append(t)
        self.off.append(len(self.px))

    def book_at(self, end: int):
        """The index of the last book strictly before `end`, or -1."""
        return bisect_left(self.ts, end) - 1


class DepthHistory:
    def __init__(self, base: Path, tick_of: Callable[[str], float], quiet: Callable[[], bool] = lambda: False,
                 cache_files: int = CACHE_FILES):
        self.base = Path(base)
        self.tick_of = tick_of
        self.quiet = quiet
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
            raise Paused()
        if f is None or f.ino != st.st_ino or st.st_size < f.pos:
            f = _File(st.st_ino)                          # new, or rewritten: from the start
        with open(path, "rb") as fh:
            fh.seek(f.pos)
            raw = fh.read(max(0, st.st_size - f.pos))
        members, used = _members(raw)
        for m in members:
            for v in _parse_member(m):
                f.add(v, tick)
        f.pos += used                                     # a torn tail is read again once it is whole
        f.mtime, f.size = st.st_mtime_ns, st.st_size
        self._cache[path] = f
        self._cache.move_to_end(path)
        while len(self._cache) > self.cache_files:
            self._cache.popitem(last=False)
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
                raise Paused()
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
