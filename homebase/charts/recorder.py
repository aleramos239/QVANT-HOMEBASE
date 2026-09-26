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
import zlib
from pathlib import Path

from .. import ticks as T
from .session import session_date
from .store import ARCHIVE, LIVE_SUFFIX, gaps_path, read_table

REFILL_MAX_PAGES = 20


class LiveRecorder:
    def __init__(self, base: Path = ARCHIVE):
        self.base = Path(base)
        self._buf: dict[Path, list[dict]] = {}
        self._seen: dict[Path, set[int]] = {}
        self._last: dict[Path, int] = {}
        self._needs_repair: set[Path] = set()
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
        process, and again before a flush that previously failed on it.
        A file that already decompresses end-to-end is left untouched; a
        torn tail is repaired by rewriting the file as one clean member
        holding every record read_table can still recover; a file with no
        readable header at all (the first member itself torn) is set
        aside as before."""
        if not p.exists():
            return
        try:
            gzip.decompress(p.read_bytes())
            return                            # decompresses cleanly end-to-end: nothing to do
        except (EOFError, zlib.error, gzip.BadGzipFile, OSError):
            pass
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
        self._repair(p)
        header, recs = read_table(p)
        seen = set()
        if header:
            ii, it = header.index("id"), header.index("ts_ms")
            seen = {int(r[ii]) for r in recs if r[ii]}
            if recs:
                self._last[p] = max(int(r[it]) for r in recs)
        self._seen[p] = seen
        return seen

    def append(self, root: str, contract: str, rows: list[dict]) -> list[dict]:
        """Buffer the rows not held yet; returns exactly those."""
        new = []
        for r in rows:
            ts = int(r["ts_ms"])
            p = self.path(root, session_date(ts), contract)
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

    def flush(self) -> int:
        n, failed = 0, None
        for p, rows in self._buf.items():
            if not rows:
                continue
            try:
                if p in self._needs_repair:    # a previous flush here left a torn tail
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
                self._needs_repair.add(p)
                continue
            self._needs_repair.discard(p)
            n += len(rows)
            rows.clear()
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
