"""The chart service's own tick recording, and the gap refill.

Every raw tick row the live feed delivers is appended to
~/futures_ticks/<ROOT>/<YYYY>/<date>_<contract>.live.csv.gz as one gzip
member per flush (about once a second): a crash loses at most the
unflushed second, and the reader drops a torn tail. Rows are deduped by
tick id, so a refill that overlaps what we hold writes nothing twice.
"""
from __future__ import annotations

import asyncio
import csv
import datetime as dt
import gzip
import io
import json
import os
import time
import zlib
from pathlib import Path

from .. import ticks as T
from .session import session_date
from .store import ARCHIVE, LIVE_SUFFIX, gaps_path, read_table

REFILL_MAX_PAGES = 20
REPAIR_RETRY_S = 30.0       # a file whose write or repair failed is retried at most this often


def monotonic() -> float:           # one seam for the tests to move the clock
    return time.monotonic()


def _inflates_cleanly(p: Path) -> bool:
    """True if every gzip member of p decompresses. Streamed a MB at a
    time: gzip.decompress() is pathological on the recorder's one-member-
    per-second day files (10.5 s for one NQ day of 57k members, 0.46 s
    streamed), and this runs on the event loop."""
    try:
        with gzip.open(p, "rb") as fh:
            while fh.read(1 << 20):
                pass
    except (EOFError, zlib.error, gzip.BadGzipFile, OSError):
        return False
    return True


class LiveRecorder:
    def __init__(self, base: Path = ARCHIVE):
        self.base = Path(base)
        self._buf: dict[Path, list[dict]] = {}
        self._seen: dict[Path, set[int]] = {}
        self._last: dict[Path, int] = {}
        # path -> (monotonic time of its last failed write or repair, the error).
        # Such a file is retried (repair, then its buffered rows) at most every
        # REPAIR_RETRY_S: each attempt re-reads the whole day's file on the loop.
        self._needs_repair: dict[Path, tuple[float, str]] = {}
        self._newest: dt.date | None = None      # the newest session appended to
        self.error: str | None = None
        self.written = 0

    def path(self, root: str, d: dt.date, contract: str) -> Path:
        return self.base / root / str(d.year) / f"{d.isoformat()}_{contract}{LIVE_SUFFIX}"

    @property
    def buffered(self) -> int:
        return sum(len(v) for v in self._buf.values())

    def _repair(self, p: Path) -> None:
        """A crash (or a write whose OSError we caught) can tear the LAST
        gzip member instead of the first: read_table stops recovering at
        the first tear, so that would silently hide every good member
        appended after it too -- far past the one unflushed second we
        promise to lose. Called on the first touch of a path in this
        process, and again before a flush that previously failed on it
        (at most every REPAIR_RETRY_S, see flush).
        A file that already decompresses end-to-end is left untouched; a
        torn tail is repaired by rewriting the file as one clean member
        holding every record read_table can still recover; a file with no
        readable header at all (the first member itself torn) is set
        aside as before."""
        if not p.exists():
            return
        if _inflates_cleanly(p):
            return                            # decompresses cleanly end-to-end: nothing to do
        header, recs = read_table(p)
        if not header:                        # first member torn by a crash: set it aside
            p.rename(p.with_name(p.name + ".corrupt"))
            return
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(header)
        w.writerows(recs)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_bytes(gzip.compress(out.getvalue().encode()))
        os.replace(tmp, p)                    # atomic: a crash here still leaves p intact

    def _open(self, p: Path) -> set[int]:
        seen = self._seen.get(p)
        if seen is not None:
            return seen
        try:
            self._repair(p)
        except OSError as e:
            # the disk is still full (or whatever else ails it): behave like
            # a failed flush rather than crash ingestion -- read whatever
            # read_table can still recover from the untouched original file,
            # and let a later flush() (already guarded) retry the repair.
            self.error = f"{p.name}: {e}"
            self._needs_repair[p] = (monotonic(), self.error)
        header, recs = read_table(p)
        seen = set()
        if header:
            ii, it = header.index("id"), header.index("ts_ms")
            seen = {int(r[ii]) for r in recs if r[ii]}
            if recs:
                self._last[p] = max(int(r[it]) for r in recs)
        self._seen[p] = seen
        return seen

    def _forget_before(self, keep: dt.date) -> None:
        """A new session started: drop the per-file state of sessions older
        than the previous one (`keep`). One NQ session's tick ids alone are
        ~40 MB, and a KeepAlive process would otherwise hold every day's. A
        file whose rows still wait for the disk keeps its state (until a
        later session start); _open() re-reads a dropped file if a refill
        ever needs it again."""
        for p in {*self._seen, *self._last, *self._buf, *self._needs_repair}:
            if self._buf.get(p) or dt.date.fromisoformat(p.name[:10]) >= keep:
                continue
            self._seen.pop(p, None)
            self._last.pop(p, None)
            self._buf.pop(p, None)
            self._needs_repair.pop(p, None)

    def append(self, root: str, contract: str, rows: list[dict]) -> list[dict]:
        """Buffer the rows not held yet; returns exactly those."""
        new = []
        for r in rows:
            ts = int(r["ts_ms"])
            d = session_date(ts, root)
            if self._newest is None or d > self._newest:
                if self._newest is not None:
                    self._forget_before(self._newest)
                self._newest = d
            p = self.path(root, d, contract)
            seen = self._open(p)
            tid = r.get("id")
            if tid not in (None, ""):
                if int(tid) in seen:
                    continue
                seen.add(int(tid))
            self._buf.setdefault(p, []).append(r)
            if ts > self._last.get(p, 0):
                self._last[p] = ts
            new.append(r)
        return new

    def last_ts(self, root: str, d: dt.date, contract: str) -> int | None:
        p = self.path(root, d, contract)
        self._open(p)
        return self._last.get(p)

    def _waiting(self, p: Path, now: float) -> str | None:
        """The last error of a failed file whose retry is not due yet."""
        failed_at, why = self._needs_repair.get(p, (None, None))
        return why if failed_at is not None and now - failed_at < REPAIR_RETRY_S else None

    def flush(self) -> int:
        n, failed, now = 0, None, monotonic()
        for p in list(self._needs_repair):
            if self._buf.get(p):
                continue                       # has rows to write: repaired alongside them, below
            if why := self._waiting(p, now):
                failed = why                   # retried once REPAIR_RETRY_S has passed
                continue
            try:
                self._repair(p)
            except OSError as e:
                failed = f"{p.name}: {e}"      # still torn; retried in REPAIR_RETRY_S
                self._needs_repair[p] = (now, failed)
                continue
            del self._needs_repair[p]
        for p, rows in self._buf.items():
            if not rows:
                continue
            if why := self._waiting(p, now):
                failed = why                   # rows stay buffered until the retry is due
                continue
            try:
                if p in self._needs_repair:    # a previous attempt here failed: maybe a torn tail
                    self._repair(p)
                p.parent.mkdir(parents=True, exist_ok=True)
                out = io.StringIO()
                w = csv.DictWriter(out, fieldnames=T.FIELDS, extrasaction="ignore")
                if not p.exists():
                    w.writeheader()
                w.writerows(rows)
                with open(p, "ab") as fh:
                    fh.write(gzip.compress(out.getvalue().encode()))
            except OSError as e:
                failed = f"{p.name}: {e}"      # rows stay buffered; the feed keeps running
                self._needs_repair[p] = (now, failed)
                continue
            self._needs_repair.pop(p, None)
            n += len(rows)
            rows.clear()
        if failed is None and self._needs_repair:
            # defensive: every failed path above was retried or reported as
            # waiting this call, but never report "healthy" while one is torn
            failed = f"{next(iter(self._needs_repair)).name}: still needs repair"
        self.error = failed
        self.written += n
        return n

    def mark_gap(self, root: str, d: dt.date, contract: str, start_ms: int, end_ms: int) -> None:
        gp = gaps_path(self.path(root, d, contract))
        try:
            gaps = json.loads(gp.read_text())
        except (OSError, ValueError):
            gaps = []
        gaps.append([int(start_ms), int(end_ms)])
        gp.parent.mkdir(parents=True, exist_ok=True)
        gp.write_text(json.dumps(gaps))


async def refill(ws, contract: str, from_ms: int, to_ms: int, *, page_fn=None,
                 sleep=asyncio.sleep, max_pages: int = REFILL_MAX_PAGES,
                 on_request=None) -> tuple[list[dict], int]:
    """Tick rows in (from_ms, to_ms), paging backwards from to_ms at the
    archive job's pace. Returns (rows oldest first, reached_ms): reached_ms
    <= from_ms means the whole gap is covered; otherwise [from_ms,
    reached_ms) is still missing (page cap hit, or the broker's buffer ran
    dry). A second penalty in a row raises — the caller marks the gap."""
    page_fn = page_fn or T.fetch_page
    rows: list[dict] = []
    seen: set = set()
    before = reached = to_ms
    for i in range(max_pages):
        if i:
            await sleep(T.PAGE_INTERVAL_S)
        if on_request:
            on_request()
        try:
            page = await page_fn(ws, contract, before)
        except T.Penalty as pen:
            await sleep(pen.wait_s + 1)
            if on_request:
                on_request()
            page = await page_fn(ws, contract, before, ticket=pen.ticket)
        fresh = [r for r in page if r["id"] not in seen]
        if not fresh:
            break
        seen.update(r["id"] for r in fresh)
        rows.extend(r for r in fresh if from_ms < r["ts_ms"] < to_ms)
        reached = min(reached, page[0]["ts_ms"])
        if reached <= from_ms:
            break
        before = page[0]["ts_ms"]
    rows.sort(key=lambda r: (r["ts_ms"], r["id"] or 0))
    return rows, reached
