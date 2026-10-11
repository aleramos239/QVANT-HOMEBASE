"""Book history for the charts: the recorded depth files + the tick archive, replayed through BookTracker.

GET /api/book/history answers from here. Like depthgrid.py it never runs in the chart service's process:
BookPool hands every request to ONE spawned worker (child_book), one request at a time (a second one while it
is busy is Busy, 503, never queued). Read-only: nothing here writes anywhere.

A session is replayed whole (the tracker needs the day's start for its trailing median), then cached by the
depth file's (inode, size, mtime). A file still growing (today's) is replayed again at most every
TODAY_TTL_S. The answer is the window cut out of that: samples averaged to `step`, and the episodes that
overlap it.
"""
from __future__ import annotations

import datetime as dt
import heapq
import json
import time
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from ..contracts import tick_size as contract_tick_size
from .bookflow import BookTracker
from .depthgrid import (BUSY, Busy, DepthHistory, HistoryPool, Paused, _members, _parse_member,  # noqa: F401
                        _worker_reason, _OFFSET_MS)
from .session import session_range_ms
from .store import TickStore

MAX_SPAN_MS = 48 * 3_600_000       # a window is at most two sessions
MAX_POINTS = 20_000                # samples per response, after averaging
MAX_EPISODES = 6_000
TODAY_TTL_S = 20.0
CACHE_DAYS = 4
REORDER_MS = 60_000                # a stray older depth line is put back in order up to this far; older is dropped


def depth_lines(path: Path):
    """(ts_ms, bids, offers) of each complete line of a depth file, in time order, one at a time (a day's lines
    are never all in memory). A line that arrives out of order is put back in place when it is less than
    REORDER_MS late; a later one is dropped, as DepthHistory drops a stray older line."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return
    heap, seq, hi, last = [], 0, None, None
    for text, _end in _members(raw):
        for v in _parse_member(text):
            t, b, a = v.get("t"), v.get("b"), v.get("a")
            if not (isinstance(t, (int, float)) and not isinstance(t, bool) and isinstance(b, list) and isinstance(a, list)):
                continue
            t = int(t)
            if last is not None and t < last:
                continue
            heapq.heappush(heap, (t, seq, b, a))
            seq += 1
            hi = t if hi is None else max(hi, t)
            while heap and heap[0][0] <= hi - REORDER_MS:
                last, _, hb, ha = heapq.heappop(heap)
                yield last, hb, ha
    while heap:
        t, _, b, a = heapq.heappop(heap)
        yield t, b, a


def replay_day(lines, ticks: list, tick_size: float, finished: bool) -> tuple[list, dict]:
    """(sample rows, {episode id: episode}) of one session: the lines (any iterable, in time order) and the
    prints in time order, a book before a print with the same stamp."""
    tr = BookTracker(tick_size)
    samples: list = []
    eps: dict = {}

    def take(evs):
        for e in evs:
            if e["k"] == "sample":
                samples.append(e["row"])
            else:
                eps[e["id"]] = {k: v for k, v in e.items() if k != "k"}

    # heapq.merge is lazy and, on a tie, yields the earlier iterable first: the book line goes before the print
    for x in heapq.merge(((t, 0, b, a) for t, b, a in lines), ((tk.ts_ms, 1, tk) for tk in ticks),
                         key=lambda x: x[0]):
        if x[1] == 0:
            take(tr.on_book(x[0], x[2], x[3]))
        else:
            tk = x[2]
            take(tr.on_print(tk.ts_ms, tk.price, tk.size, tk.side))
    take(tr.finish() if finished else tr.flush(10 ** 18))
    return samples, eps


def _average(rows: list, step: int) -> list:
    """Rows [t, b10, a10, i1, i5, i10, micro, spread] averaged inside `step` ms buckets (the bucket's start
    as t); micro and spread are averaged over the rows that have them."""
    if step <= 1000:
        return rows
    out, cur, acc = [], None, []

    def put():
        if not acc:
            return
        cols = list(zip(*acc))
        mean = lambda xs: (lambda v: round(sum(v) / len(v), 4) if v else None)([x for x in xs if x is not None])
        out.append([cur, *[mean(c) for c in cols[1:]]])

    for r in rows:
        b = r[0] - r[0] % step
        if b != cur:
            put()
            cur, acc = b, []
        acc.append(r)
    put()
    return out


class BookHistory:
    def __init__(self, depth_base: Path, tick_base: Path, quiet=lambda: None, tick_of=contract_tick_size,
                 now=time.time):
        self.depth = DepthHistory(depth_base, tick_of)
        self.ticks = TickStore(tick_base)
        self.tick_of = tick_of
        self.quiet = quiet
        self._now = now
        self._cache: OrderedDict = OrderedDict()   # path -> (stamp, computed_at, samples, episodes)

    def _day(self, root: str, path: Path, d: dt.date, tick: float, now_ms: int):
        st = path.stat()
        stamp = (st.st_ino, st.st_size, st.st_mtime_ns)
        hit = self._cache.get(path)
        now_s = self._now()
        if hit is not None and (hit[0] == stamp or now_s - hit[1] < TODAY_TTL_S):
            self._cache.move_to_end(path)
            return hit[2], hit[3]
        why = self.quiet()
        if why:
            raise Paused(why)
        s = self.ticks.load(root, d)
        ticks = s.ticks if s is not None else []
        finished = session_range_ms(d, root)[1] <= now_ms
        samples, eps = replay_day(depth_lines(path), ticks, tick, finished)
        self._cache[path] = (stamp, now_s, samples, eps)
        while len(self._cache) > CACHE_DAYS:
            self._cache.popitem(last=False)
        return samples, eps

    def window(self, root: str, frm: int, to: int, now_ms: int) -> bytes:
        if not root.isalnum():
            raise ValueError(f"bad root {root!r}")
        frm, to = int(frm), int(to)
        if to <= frm:
            raise ValueError("to_ms must be after from_ms")
        if to - frm > MAX_SPAN_MS:
            raise ValueError(f"at most {MAX_SPAN_MS // 3_600_000} h per request")
        why = self.quiet()                                 # paused windows answer 503 even from the cache
        if why:
            raise Paused(why)
        to = min(to, int(now_ms))
        tick = float(self.tick_of(root))
        rows: list = []
        eps: dict = {}
        if to > frm:
            for path in self.depth.files(root, frm, to):
                d = dt.date.fromisoformat(path.name[:10])
                s, e = self._day(root, path, d, tick, now_ms)
                rows.extend(r for r in s if frm <= r[0] < to)
                for k, v in e.items():
                    if v["t0"] < to and (v["t1"] is None or v["t1"] >= frm):
                        eps[k] = v
        raw = -(-(to - frm) // MAX_POINTS)
        step = max(1000, -(-raw // 1000) * 1000)           # whole seconds, at most MAX_POINTS samples
        rows = _average(rows, step)
        out = sorted(eps.values(), key=lambda v: v["t0"])
        for i, v in enumerate(out):                        # nothing later than `to`: a level still standing then is open
            if v["t1"] is None or v["t1"] > to:
                out[i] = {**v, "t1": None, "end": "open", "ab": None if v["ab"] is None or v["ab"] > to else v["ab"]}
        if len(out) > MAX_EPISODES:
            out = sorted(sorted(out, key=lambda v: -v["r"])[:MAX_EPISODES], key=lambda v: v["t0"])
        return json.dumps({"tick": tick, "step": step, "t0": frm, "t1": to, "samples": rows, "episodes": out},
                          separators=(",", ":")).encode()


# ------------------------------------------------------------------ the worker process

_BOOKS: dict[tuple, BookHistory] = {}    # (in the worker) (depth base, tick base) -> its BookHistory and cache


def child_book(depth_base: str, tick_base: str, root: str, frm: int, to: int, now_ms: int, offset_ms: float) -> bytes:
    """(the worker) BookHistory.window with the worker's own cache; the paused windows by the service's clock."""
    _OFFSET_MS[0] = offset_ms
    key = (depth_base, tick_base)
    h = _BOOKS.get(key)
    if h is None:
        h = _BOOKS[key] = BookHistory(Path(depth_base), Path(tick_base), quiet=_worker_reason)
    return h.window(root, frm, to, now_ms)


class BookPool(HistoryPool):
    """(the service) HistoryPool's one worker, one request at a time, Busy while it is on another, for the book."""

    def __init__(self, depth_base: Path, tick_base: Path, executor_factory=None):
        super().__init__(depth_base, *([executor_factory] if executor_factory else []))
        self.tick_base = str(tick_base)

    async def window(self, root: str, frm: int, to: int, now_ms: int, offset_ms: float = 0.0) -> bytes:
        return await self._run(child_book, self.base, self.tick_base, root, frm, to, now_ms, offset_ms)
