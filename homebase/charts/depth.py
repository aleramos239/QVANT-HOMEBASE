"""Level 2 for the charts (spec 2026-09-27 charts-depth, Part A): the book
per root, its fan-out to the pages, and its recording.

One md socket. The DOM subscriptions (md/subscribeDOM / md/unsubscribeDOM)
ride the tick feed's EXISTING socket (TickFeed.ws): no new login, no new
socket. Depth watches that attribute, and when the feed reconnects (a new
socket object) it attaches its event handler to the new socket and
subscribes everything again. subscribeDOM is not a getChart, so it is not
counted against the 180 chart requests/hour md budget: nothing here calls
TickFeed.count_request, and nothing here ever asks md/getChart.

Who is subscribed: the roots recorded (DEPTH_RECORD_ROOTS) plus the roots
any page has a chart on; a root nobody watches any more is unsubscribed
LINGER_S after its last viewer left, unless it is recorded. A refused
subscription (an error, an errorText, a p-ticket penalty, or a reply with no
subscriptionId) is that root's status error and is asked again every
RETRY_S, never before a penalty's p-time, and on every reconnect. Inside the
09:20-09:35 ET quiet window (tickfeed.in_quiet) no retry and no new-demand
subscription is sent; they wait for 09:35. A recorded root's first ask and a
re-subscribe after a reconnect still go.

Tradovate sends a FULL snapshot per DOM event, so each event replaces the
book. The event carries only a contractId: the subscribeDOM reply's
subscriptionId is that contractId (the same as for subscribeQuote,
verified live in marketdata.py), so the subscription maps it to the root.
Only that id binds a root: a push for any other contractId is dropped.

To the pages: {"type": "depth", "root", "ts", "bids", "offers"}, the top
WIRE_LEVELS levels each side, at most one message per WIRE_MIN_S per root
(the latest book wins), and only to connections with a chart on that root.
Each root has a desk.Fanout: a bounded outbox per page that never waits; a
page that falls behind drops its queued books and is resynced with the
current one (the Fanout's hello). When the md socket goes, so do the books:
each watched root's pages get an empty one (ts null) at once.

Recording: ~/futures_depth/<ROOT>/<YYYY>/<session date>_<contract>.depth.jsonl.gz,
one gzip member per flush (every FLUSH_S and on shutdown), at most one line
per REC_MIN_S per root and only when the top REC_LEVELS changed:
{"t": ms, "b": [[p, s], ...], "a": [[p, s], ...]}. The file work (gzip,
a torn-tail check of the day file) runs in a worker thread, never on the
event loop. Disk errors go to status and never raise; a failed file is
retried at most every REPAIR_RETRY_S. The recorder refuses any base under ~/futures_ticks.
Replay builds none of this: a replay page gets no depth messages.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import gzip
import json
import math
import os
import time
import zlib
from collections import deque
from pathlib import Path
from typing import Callable, Hashable, Optional

from .. import symbols
from . import parse_depth_roots as parse_roots  # noqa: F401 — re-exported
from .desk import Fanout
from .session import session_date
from .store import ARCHIVE as TICK_ARCHIVE
from .tickfeed import in_quiet

DEPTH_ARCHIVE = Path.home() / "futures_depth"
SUFFIX = ".depth.jsonl.gz"
BOOK_LEVELS = 30          # levels kept per side
WIRE_LEVELS = 20          # levels per side sent to a page
WIRE_MIN_S = 0.1          # <= 10 depth messages a second per root
REC_LEVELS = 10           # levels per side recorded
REC_MIN_S = 0.25          # <= 4 recorded lines a second per root
LINGER_S = 60.0           # a root nobody watches is unsubscribed this long after the last viewer left
RETRY_S = 600.0           # a refused root is asked again this often (and on every reconnect)
FLUSH_S = 30.0            # the recording is flushed this often (and on shutdown)
STEP_S = 0.05             # the depth loop's cadence: coalesced books go out within this of their window
PAGE_QUEUE_MAX = 4        # depth messages held per page per root before it is resynced to the latest
BUFFER_MAX = 50_000       # lines held per file while the disk refuses them (~3.5 h at 4/s); oldest dropped
REPAIR_RETRY_S = 300.0    # a file whose write failed is re-read / re-tried at most this often (not every flush)
GZIP_LEVEL = 6
_EPS = 1e-9               # float slack on the rate windows
_READ_CHUNK = 1 << 16


def _num(v) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        return None
    try:
        x = float(v)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def _levels(raw, best_high: bool) -> list:
    """[[price, size], ...] best first, at most BOOK_LEVELS; malformed or empty levels skipped."""
    out = []
    for lv in raw if isinstance(raw, list) else ():
        if not isinstance(lv, dict):
            continue
        p, s = _num(lv.get("price")), _num(lv.get("size"))
        if p is None or s is None or s <= 0:
            continue
        out.append([p, int(s) if s == int(s) else s])
    out.sort(key=lambda x: x[0], reverse=best_high)
    return out[:BOOK_LEVELS]


def _ts_ms(v, fallback: int) -> int:
    """Tradovate's DOM timestamp (ISO 8601, UTC) as epoch ms; the wall clock if it has none."""
    if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
        return int(v)
    if isinstance(v, str):
        try:
            t = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return fallback
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        return int(t.timestamp() * 1000)
    return fallback


class Book:
    """The latest DOM snapshot of one root."""

    def __init__(self, root: str):
        self.root = root
        self.bids: list = []
        self.offers: list = []
        self.ts: Optional[int] = None          # the snapshot's timestamp, epoch ms
        self.updated: Optional[float] = None   # monotonic time it arrived

    def apply(self, dom: dict, now: float, wall_ms: int) -> None:
        """Replace the book with this snapshot (Tradovate sends full ones)."""
        self.bids = _levels(dom.get("bids"), True)
        self.offers = _levels(dom.get("offers"), False)
        self.ts = _ts_ms(dom.get("timestamp"), wall_ms)
        self.updated = now

    def top(self, n: int) -> tuple[list, list]:
        return [lv[:] for lv in self.bids[:n]], [lv[:] for lv in self.offers[:n]]


# ------------------------------------------------------------------ recording

def _scan(raw: bytes) -> tuple[list[bytes], bool]:
    """(the text of each complete gzip member, in order, up to the first torn
    one; True if the whole file is complete members). Fed in chunks, so a day
    of thousands of members is read in one pass, never re-sliced."""
    mv, pos, n, out = memoryview(raw), 0, len(raw), []
    while pos < n:
        d, parts = zlib.decompressobj(wbits=31), []
        while not d.eof and pos < n:
            chunk = mv[pos:pos + _READ_CHUNK]
            try:
                parts.append(d.decompress(chunk))
            except zlib.error:
                return out, False
            pos += len(chunk) - len(d.unused_data)
        if not d.eof:
            return out, False
        out.append(b"".join(parts))
    return out, True


def read_depth(path) -> list[dict]:
    """Every line of a depth file's complete members: a torn tail (a crash
    mid-flush) loses only that last flush."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return []
    lines = []
    for member in _scan(raw)[0]:
        for ln in member.decode("utf-8", "replace").splitlines():
            try:
                v = json.loads(ln)
            except ValueError:
                continue
            if isinstance(v, dict):
                lines.append(v)
    return lines


def _under(p: Path, root: Path) -> bool:
    """p is root or inside it, by name (.. collapsed) or once symlinks are
    followed (~/futures_ticks is itself a symlink on the desk machine)."""
    for a, b in ((Path(os.path.abspath(p.expanduser())), Path(os.path.abspath(root.expanduser()))),
                 (p.expanduser().resolve(), root.expanduser().resolve())):
        if a == b or b in a.parents:
            return True
    return False


class DepthRecorder:
    """Buffers lines on the event loop; writes them in a worker thread
    (aflush): the gzip work and a file's first-touch scan (a whole day file,
    ~100 ms / ~100 MB of inflate for 19 MB) never run on the loop. flush()
    is the same, synchronously, for callers without a loop."""

    def __init__(self, base: Path = DEPTH_ARCHIVE, now: Callable[[], float] = time.monotonic):
        self.base = Path(base)
        if _under(self.base, TICK_ARCHIVE):
            raise ValueError(f"depth is never recorded under the tick archive ({TICK_ARCHIVE})")
        self._now = now
        self._buf: dict[Path, deque] = {}
        self._checked: set[Path] = set()        # files repaired (if torn) on first touch in this process
        self._failed: dict[Path, tuple[float, str]] = {}   # path -> (when its write failed, why)
        self.error: Optional[str] = None
        self.written = 0
        self.dropped = 0                        # lines lost to BUFFER_MAX while the disk refused them

    def path(self, root: str, d: dt.date, contract: str) -> Path:
        return self.base / root / str(d.year) / f"{d.isoformat()}_{contract}{SUFFIX}"

    @property
    def buffered(self) -> int:
        return sum(len(q) for q in self._buf.values())

    def add(self, root: str, contract: str, t_ms: int, bids: list, offers: list) -> None:
        p = self.path(root, session_date(int(t_ms), root), contract)
        q = self._buf.setdefault(p, deque())
        if len(q) >= BUFFER_MAX:
            q.popleft()
            self.dropped += 1
        q.append(json.dumps({"t": int(t_ms), "b": bids, "a": offers}, separators=(",", ":")) + "\n")

    @staticmethod
    def _repair(p: Path) -> None:
        """A torn last member (a crash mid-flush) would hide every member
        appended after it: rewrite the file as its complete members before
        appending. A file with none is set aside."""
        if not p.exists():
            return
        members, clean = _scan(p.read_bytes())
        if clean:
            return
        if not members:
            p.rename(p.with_name(p.name + ".corrupt"))
            return
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_bytes(gzip.compress(b"".join(members), compresslevel=GZIP_LEVEL))
        os.replace(tmp, p)

    def _take(self) -> dict[Path, list[str]]:
        """(loop) The buffered lines, handed to one write; add() starts new buffers."""
        batch = {p: list(q) for p, q in self._buf.items() if q}
        self._buf = {}
        return batch

    def _write(self, batch: dict[Path, list[str]], now: float) -> tuple[dict[Path, int], dict[Path, str]]:
        """(thread) One gzip member per file. A file that failed less than
        REPAIR_RETRY_S ago is not touched (no re-read, no write) until then."""
        done, failed = {}, {}
        for p, lines in batch.items():
            f = self._failed.get(p)
            if f is not None and now - f[0] < REPAIR_RETRY_S - _EPS:
                failed[p] = f[1]
                continue
            try:
                if p not in self._checked:
                    self._repair(p)
                    self._checked.add(p)
                p.parent.mkdir(parents=True, exist_ok=True)
                data = gzip.compress("".join(lines).encode(), compresslevel=GZIP_LEVEL)
                with open(p, "ab") as fh:
                    fh.write(data)
            except OSError as e:
                failed[p] = f"{p.name}: {e}"
                self._failed[p] = (now, failed[p])
                self._checked.discard(p)        # maybe a half-written member: repaired before the retry
                continue
            self._failed.pop(p, None)
            done[p] = len(lines)
        return done, failed

    def _finish(self, batch, done, failed) -> int:
        """(loop) Lines not written go back ahead of anything added meanwhile."""
        for p, lines in batch.items():
            if p in done:
                continue
            q = deque(lines)
            q.extend(self._buf.get(p, ()))
            while len(q) > BUFFER_MAX:
                q.popleft()
                self.dropped += 1
            self._buf[p] = q
        self.error = next(iter(failed.values()), None)
        n = sum(done.values())
        self.written += n
        return n

    def flush(self) -> int:
        """Write now, on the calling thread; returns the lines written. Never
        raises on a disk error: it is kept in .error and the lines stay buffered."""
        batch = self._take()
        return self._finish(batch, *self._write(batch, self._now()))

    async def aflush(self) -> int:
        """flush(), with the file work in a worker thread."""
        batch = self._take()
        return self._finish(batch, *(await asyncio.to_thread(self._write, batch, self._now())))

    def status(self) -> dict:
        return {"written": self.written, "buffered": self.buffered, "dropped": self.dropped,
                "error": self.error}


# ------------------------------------------------------------------ the depth feed

class Depth:
    def __init__(self, feed, record_roots=(), *, recorder: Optional[DepthRecorder] = None,
                 now: Callable[[], float] = time.monotonic,
                 wall_ms: Callable[[], int] = lambda: int(time.time() * 1000),
                 sleep=asyncio.sleep, log: Optional[Callable[[str], None]] = None):
        self.feed = feed
        self.record = tuple(dict.fromkeys(r.upper() for r in record_roots))
        self.recorder = recorder
        self._now, self._wall_ms, self._sleep = now, wall_ms, sleep
        self._log = log or (lambda _m: None)
        self.books: dict[str, Book] = {}
        self._ws = None                             # the socket our subscriptions live on
        self.subscribed: dict[str, str] = {}        # root -> contract, on self._ws
        self._contract: dict[str, str] = {}         # root -> the contract its book is recorded under
        self._cid: dict[int, str] = {}              # contractId (the reply's subscriptionId) -> root
        self._inflight: set[str] = set()
        self._resub: set[str] = set()               # subscribed on a socket since lost: re-asked even
                                                    # inside the 09:20-09:35 quiet window
        self.errors: dict[str, str] = {}            # root -> why its subscription was refused
        self._retry_at: dict[str, float] = {}
        self._viewers: dict[Hashable, str] = {}     # (conn, chart id) -> root
        self._count: dict[str, int] = {}            # root -> charts showing it
        self._left_at: dict[str, float] = {}        # root -> when its last viewer left
        self._fans: dict[str, Fanout] = {}
        self._wire_due: set[str] = set()
        self._last_wire: dict[str, float] = {}
        self._rec_due: set[str] = set()
        self._last_rec: dict[str, float] = {}
        self._last_top: dict[str, tuple] = {}
        self._last_flush = now()
        self._tasks: set = set()                    # subscribe / unsubscribe requests in flight
        self._flush_task: Optional[asyncio.Task] = None
        self._flush_lock: Optional[asyncio.Lock] = None
        self._stop = False
        self.error: Optional[str] = None

    # ---- pages

    def message(self, root: str) -> dict:
        b = self.books.get(root)
        if b is None:
            return {"type": "depth", "root": root, "ts": None, "bids": [], "offers": []}
        bids, offers = b.top(WIRE_LEVELS)
        return {"type": "depth", "root": root, "ts": b.ts, "bids": bids, "offers": offers}

    def book_of(self, root: str) -> Optional[dict]:
        """The paper book's read of the latest DOM (paperbook.py, fast-paper): {bids, offers, ts_ms} -- every level
        kept, best first, as copies -- or None when there is none (not subscribed, or the md socket went)."""
        b = self.books.get(root)
        if b is None or b.ts is None:
            return None
        bids, offers = b.top(BOOK_LEVELS)
        return {"bids": bids, "offers": offers, "ts_ms": b.ts}

    def _conn_has(self, conn, root: str) -> bool:
        return any(k[0] is conn and r == root for k, r in self._viewers.items())

    def view(self, key: tuple, root: str, send: Callable[[dict], None], room: Callable[[], bool]) -> None:
        """Chart `key` = (conn, chart id) shows `root`: that page gets its depth."""
        root = root.upper()
        old = self._viewers.get(key)
        if old == root:
            return
        if old is not None:
            self.unview(key)
        conn = key[0]
        attach = not self._conn_has(conn, root)
        self._viewers[key] = root
        self._count[root] = self._count.get(root, 0) + 1
        self._left_at.pop(root, None)
        if attach:
            fan = self._fans.get(root)
            if fan is None:
                fan = self._fans[root] = Fanout(hello=lambda r=root: self.message(r), maxlen=PAGE_QUEUE_MAX)
            fan.attach(conn, send, room)        # greeted with the current book

    def unview(self, key: tuple) -> None:
        root = self._viewers.pop(key, None)
        if root is None:
            return
        self._count[root] -= 1
        if not self._conn_has(key[0], root):
            self._fans[root].detach(key[0])
        if not self._count[root]:
            del self._count[root]
            self._left_at[root] = self._now()

    def drop_conn(self, conn) -> None:
        for key in [k for k in self._viewers if k[0] is conn]:
            self.unview(key)

    # ---- the md socket

    def _root_of(self, cid) -> Optional[str]:
        if isinstance(cid, bool):
            return None
        try:
            return self._cid.get(int(cid))
        except (TypeError, ValueError):
            return None

    def on_event(self, msg: dict) -> None:
        """An md socket event (on the socket reader's loop)."""
        if not isinstance(msg, dict) or msg.get("e") != "md":
            return
        doms = (msg.get("d") or {}).get("doms") if isinstance(msg.get("d"), dict) else None
        if not doms:
            return
        now = self._now()
        for dom in doms:
            if not isinstance(dom, dict):
                continue
            root = self._root_of(dom.get("contractId"))
            if root is None or root not in self.subscribed:
                continue
            book = self.books.get(root)
            if book is None:
                book = self.books[root] = Book(root)
            book.apply(dom, now, self._wall_ms())
            self._wire_due.add(root)
            if self.recorder is not None and root in self.record:
                self._rec_due.add(root)
            self._drain(root, now)

    def _drain(self, root: str, now: float) -> None:
        """Send / record root's latest book if its rate window is open (else it waits for step())."""
        if root in self._wire_due:
            if not self._count.get(root):
                self._wire_due.discard(root)
            elif now - self._last_wire.get(root, -math.inf) >= WIRE_MIN_S - _EPS:
                self._wire_due.discard(root)
                self._last_wire[root] = now
                self._fans[root].publish(self.message(root))
        if root in self._rec_due and now - self._last_rec.get(root, -math.inf) >= REC_MIN_S - _EPS:
            self._rec_due.discard(root)
            book, contract = self.books.get(root), self._contract.get(root)
            if book is None or contract is None or book.ts is None:
                return
            top = book.top(REC_LEVELS)
            if top != self._last_top.get(root):
                self._last_top[root] = top
                self._last_rec[root] = now
                self.recorder.add(root, contract, book.ts, *top)

    def _watch_socket(self) -> None:
        ws = getattr(self.feed, "ws", None)
        if ws is not None and not getattr(ws, "connected", False):
            ws = None
        if ws is self._ws:
            return
        # a new socket (the feed reconnected) or none: nothing is subscribed on it
        lost, self._ws = self._ws, ws
        self._resub |= set(self.subscribed)
        self.subscribed.clear()
        self._cid.clear()
        self._inflight.clear()
        self._retry_at.clear()                  # refused roots are asked again on every reconnect
        self.books.clear()
        self._wire_due.clear()
        self._rec_due.clear()
        if lost is not None:
            # the books went with the socket: no page keeps showing a stale one
            now = self._now()
            for root, fan in self._fans.items():
                if self._count.get(root):
                    self._last_wire[root] = now
                    fan.publish(self.message(root))
        if ws is not None and self.on_event not in ws.event_handlers:
            ws.event_handlers.append(self.on_event)

    def _refuse(self, root: str, why: str, wait: float = RETRY_S) -> None:
        if self.errors.get(root) != why:
            self._log(f"depth {root}: {why}")
        self.errors[root] = why
        self._retry_at[root] = self._now() + max(RETRY_S, wait)

    async def _subscribe(self, ws, root: str) -> None:
        try:
            try:
                contract = (getattr(self.feed, "contracts", None) or {}).get(root) \
                    or symbols.resolve_contract(root)
            except ValueError as e:
                self._refuse(root, f"{root}: no front contract ({e})")
                return
            try:
                d = await ws.request("md/subscribeDOM", {"symbol": contract})
            except Exception as e:  # noqa: BLE001
                if ws is not self._ws or not getattr(ws, "connected", False) \
                        or str(e) == "websocket not connected":
                    return                       # the socket, not the symbol: the reconnect re-subscribes
                self._refuse(root, f"{contract}: {str(e) or 'md/subscribeDOM ' + type(e).__name__}")
                return
            if ws is not self._ws:
                return                           # answered on a socket we already left
            if isinstance(d, dict) and d.get("p-ticket"):
                # a penalty: refused like any other, and never asked again before its p-time
                pt = _num(d.get("p-time")) or 0.0
                self._refuse(root, f"{contract}: penalty (p-ticket, p-time {pt:g} s)", wait=pt)
                return
            if isinstance(d, dict) and d.get("errorText"):
                self._refuse(root, f"{contract}: {d['errorText']}")
                return
            cid = d.get("subscriptionId") if isinstance(d, dict) else None
            if isinstance(cid, bool) or not isinstance(cid, (int, str)) or not str(cid).isdigit():
                # the id is the only way to tell whose book a push is: without it, nothing binds
                self._refuse(root, f"{contract}: no subscriptionId in the subscribeDOM reply {d!r}"[:200])
                return
            self.subscribed[root] = contract
            self._contract[root] = contract
            self._cid[int(cid)] = root
            self._resub.discard(root)
            self.errors.pop(root, None)
            self._retry_at.pop(root, None)
        finally:
            if ws is self._ws:
                self._inflight.discard(root)

    async def _unsubscribe(self, ws, contract: str) -> None:
        try:
            await ws.request("md/unsubscribeDOM", {"symbol": contract})
        except Exception:  # noqa: BLE001 — best effort; the socket may be gone
            pass

    def _spawn(self, coro) -> None:
        t = asyncio.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    def _reconcile(self, now: float) -> None:
        ws = self._ws
        if ws is None:
            return
        want = list(dict.fromkeys([*self.record, *sorted(self._count)]))
        self._resub &= set(want)
        # 09:20-09:35 ET: no retries and no new demand (they wait for 09:35); a recorded
        # root's first ask and a re-subscribe after a reconnect still go
        quiet = in_quiet(self._wall_ms() / 1000)
        for root in want:
            if root in self.subscribed or root in self._inflight or now < self._retry_at.get(root, -math.inf):
                continue
            if quiet and (root in self.errors or (root not in self.record and root not in self._resub)):
                continue
            self._inflight.add(root)
            self._spawn(self._subscribe(ws, root))
        for root in list(self.subscribed):
            if root in self.record or self._count.get(root):
                continue
            left = self._left_at.get(root)
            if left is not None and now - left < LINGER_S - _EPS:
                continue
            contract = self.subscribed.pop(root)
            self._left_at.pop(root, None)
            self._cid = {c: r for c, r in self._cid.items() if r != root}
            self.books.pop(root, None)
            self._wire_due.discard(root)
            self._spawn(self._unsubscribe(ws, contract))

    # ---- the loop

    async def aflush(self) -> None:
        """Write the recording (its file work in a worker thread); one flush at a time."""
        if self.recorder is None:
            return
        if self._flush_lock is None:
            self._flush_lock = asyncio.Lock()
        async with self._flush_lock:
            try:
                await self.recorder.aflush()
            except Exception as e:  # noqa: BLE001 — recording never takes the service down
                self.recorder.error = f"{type(e).__name__}: {e}"

    def step(self) -> None:
        now = self._now()
        self._watch_socket()
        for root in list(self._wire_due | self._rec_due):
            self._drain(root, now)
        for fan in self._fans.values():
            fan.flush()                          # pages whose socket had no room before
        self._reconcile(now)
        if self.recorder is not None and now - self._last_flush >= FLUSH_S - _EPS \
                and (self._flush_task is None or self._flush_task.done()):
            self._last_flush = now
            self._flush_task = asyncio.create_task(self.aflush())

    async def settle(self) -> None:
        """Wait for the requests and the flush in flight (tests)."""
        while self._tasks or (self._flush_task is not None and not self._flush_task.done()):
            pending = list(self._tasks) + ([self._flush_task] if self._flush_task else [])
            await asyncio.gather(*pending, return_exceptions=True)

    async def aclose(self) -> None:
        """Shutdown: stop the loop, cancel the requests in flight, write the recording's last member."""
        self._stop = True
        for t in list(self._tasks):
            t.cancel()
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
        if self._flush_task is not None:
            await asyncio.gather(self._flush_task, return_exceptions=True)
        await self.aflush()

    async def run(self) -> None:
        while not self._stop:
            try:
                self.step()
                self.error = None
            except Exception as e:  # noqa: BLE001 — the depth loop must never die
                if self.error is None:
                    self._log(f"depth: {type(e).__name__}: {e}")
                self.error = f"{type(e).__name__}: {e}"
            await self._sleep(STEP_S)

    def stop(self) -> None:
        self._stop = True

    def status(self) -> dict:
        now = self._now()
        roots = dict.fromkeys([*self.record, *sorted(self._count), *self.subscribed, *self.errors])
        out = {}
        for r in roots:
            b = self.books.get(r)
            out[r] = {"subscribed": r in self.subscribed,
                      "levels": [len(b.bids), len(b.offers)] if b is not None else [0, 0],
                      "age_s": round(now - b.updated, 1) if b is not None and b.updated is not None else None,
                      "error": self.errors.get(r)}
        return out
