"""One read API over the tick files, for charts (and later backtests).

Two kinds of file live side by side under ~/futures_ticks/<ROOT>/<YYYY>/:
  <date>_<contract>.csv.gz       the nightly archive (manifest .json beside
                                 it; Massive backfills carry no bid/ask)
  <date>_<contract>.live.csv.gz  the chart service's own live recording
                                 (+ <date>_<contract>.live.gaps)

Per session ONE contract is used (on a roll day the one with the most ticks),
and per contract: complete archive alone > live + incomplete archive > either
alone. The last case is a UNION, deduped by tick id with tickarchive.merge's
rules (the archive's version wins a disagreement, quotes are kept where either
has them): the hourly repair job files the ticks a dead Mac never recorded into
the incomplete archive, and the live file alone would leave that hole on the
chart until the nightly merge. Read-only -- nothing here ever writes a file.
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import json
import re
import threading
import zlib
from bisect import bisect_left
from dataclasses import dataclass, field, replace
from pathlib import Path

from .. import tickarchive as TA
from .tick import SideClassifier, Tick

ARCHIVE = Path.home() / "futures_ticks"
LIVE_SUFFIX = ".live.csv.gz"


@dataclass(frozen=True)
class SessionFile:
    path: Path
    contract: str
    live: bool
    complete: bool
    ticks: int            # manifest count (archive) or file size (live): ranking only
    bid_ask: bool         # False for a Massive backfill (sides are tick-rule only)
    merge_with: Path | None = None   # a live file's incomplete archive of the same contract: load() returns both, unioned


@dataclass
class Session:
    root: str
    date: dt.date
    contract: str
    source: str                            # "archive" | "live"
    ticks: list[Tick]
    bid_ask: bool                          # False -> buy/sell split is approximate
    gaps: list = field(default_factory=list)   # [[start_ms, end_ms], ...]


def read_table(path: Path) -> tuple[list[str], list[list[str]]]:
    """(header, records) of a gzip CSV that may hold several gzip members
    (the live recorder appends one per flush) and may end in a member torn
    by a crash — the torn tail is dropped, never raised."""
    header: list[str] = []
    recs: list[list[str]] = []
    try:
        with gzip.open(path, "rt", newline="") as fh:
            rd = csv.reader(fh)
            header = next(rd, None) or []
            n = len(header)
            for rec in rd:
                if len(rec) == n and rec[0] != header[0]:
                    recs.append(rec)
    except (EOFError, zlib.error, OSError):
        pass
    return header, recs


def gaps_path(path: Path) -> Path:
    """<date>_<contract>.live.gaps (a JSON list). Deliberately NOT *.json:
    research loaders glob <ROOT>/*/*.json as the archive's manifests."""
    stem = path.name.replace(LIVE_SUFFIX, "").replace(".csv.gz", "")
    return path.with_name(stem + ".live.gaps")


def ticks_from_table(header: list[str], recs: list[list[str]],
                     live: bool = False) -> tuple[list[Tick], bool]:
    """Classified ticks + whether the file carries quotes. A live file is
    deduped by id and re-sorted by (time, id) first: a gap refill appends
    OLDER ticks after newer ones. (list.sort is stable.)

    homebase.charts.export._ordered() re-implements exactly this dedup/sort rule over the RAW
    rows (this function's Tick objects drop bid_size/ask_size, which export needs) -- keep the
    two in lock-step; tests/test_charts_export.py's test_ordered_matches_ticks_from_table pins
    them against the same fixture."""
    if not header:
        return [], False
    ix = {k: i for i, k in enumerate(header)}
    it, ip, isz = ix["ts_ms"], ix["price"], ix["size"]
    ib, ia, iid = ix.get("bid"), ix.get("ask"), ix.get("id")
    if live and iid is not None:
        seen: set[str] = set()
        uniq = []
        for r in recs:
            k = r[iid]
            if k and k in seen:
                continue
            seen.add(k)
            uniq.append(r)
        recs = sorted(uniq, key=lambda r: (int(r[it]), int(r[iid] or 0)))
    clf = SideClassifier()
    out: list[Tick] = []
    quotes = False
    for r in recs:
        b = r[ib] if ib is not None else ""
        a = r[ia] if ia is not None else ""
        if b and a:
            quotes = True
        p = float(r[ip])
        out.append(Tick(int(r[it]), p, int(r[isz]),
                        clf.side(p, float(b) if b else None, float(a) if a else None),
                        int(r[iid]) if iid is not None and r[iid] else 0))
    return out, quotes


_CONTRACT = re.compile(r"^([A-Z0-9]+?)([FGHJKMNQUVXZ])(\d{1,2})$")


def _key(contract: str) -> str:
    """One name per contract: the desk writes NGX6, the Massive backfill NGX26."""
    m = _CONTRACT.match(contract)
    return f"{m.group(1)}{m.group(2)}{m.group(3)[-1]}" if m else contract


def _stamp(p: Path) -> tuple[int, int] | None:
    try:
        st = p.stat()
    except OSError:
        return None
    return st.st_size, st.st_mtime_ns


def _root_of(p: Path) -> str:
    return p.parent.parent.name


def _date_of(p: Path) -> dt.date:
    return dt.date.fromisoformat(p.name[:10])


def splice_tail(loaded: list[Tick], current, since_ms: int) -> list[Tick]:
    """`loaded` (the session as the files hold it) plus the ticks of `current` (the hub's live tape)
    at/after since_ms that it lacks -- by tick id, or by (time, price, size) for an id-less tick.
    For the live service: the files were read in a worker thread, so the ticks that arrived
    meanwhile (and the recorder's unflushed second) exist only on the tape. Older tape ticks are
    all on disk already; `loaded` is returned as is when nothing is missing."""
    cur = list(current)
    i = len(cur)
    while i > 0 and cur[i - 1].ts_ms >= since_ms:
        i -= 1
    tail = cur[i:]
    if not tail:
        return loaded
    j = bisect_left(loaded, since_ms, key=lambda t: t.ts_ms)
    have_id = {t.id for t in loaded[j:] if t.id}
    have_key = {(t.ts_ms, t.price, t.size) for t in loaded[j:] if not t.id}
    extra = []
    for t in tail:
        if t.id:
            if t.id in have_id:
                continue
            have_id.add(t.id)
        else:
            k = (t.ts_ms, t.price, t.size)
            if k in have_key:
                continue
            have_key.add(k)
        extra.append(t)
    if not extra:
        return loaded
    return loaded[:j] + sorted(loaded[j:] + extra, key=lambda t: (t.ts_ms, t.id))


class TickStore:
    MERGE_MEMO = 2          # a merged session is ~150 bytes a tick: keep only the newest couple

    def __init__(self, base: Path = ARCHIVE):
        self.base = Path(base)
        self._merged: dict[tuple, Session] = {}     # (both files' path+size+mtime) -> the union, oldest first
        self._merged_lock = threading.Lock()
        self.merge_refused: dict[str, str] = {}     # live file name -> why its union was not used (visibility/tests)

    def files(self, root: str, d: dt.date) -> list[SessionFile]:
        tag = d.isoformat()
        out = []
        for p in sorted((self.base / root / str(d.year)).glob(f"{tag}_*.csv.gz")):
            contract = p.name[len(tag) + 1:].split(".")[0]
            if p.name.endswith(LIVE_SUFFIX):
                try:
                    size = p.stat().st_size
                except OSError:
                    continue                      # vanished between glob() and here
                out.append(SessionFile(p, contract, True, False, size, True))
                continue
            man: dict = {}
            try:
                man = json.loads(p.with_name(p.name[:-len(".csv.gz")] + ".json").read_text())
            except (OSError, ValueError):
                pass
            try:
                ticks = int(man.get("ticks") or p.stat().st_size)
            except OSError:
                continue                          # vanished between glob() and here
            out.append(SessionFile(p, contract, False, bool(man.get("complete")),
                                   ticks, bool(man.get("bid_ask", True))))
        return out

    def pick(self, root: str, d: dt.date) -> SessionFile | None:
        """The session's contract first -- the one whose archive counts the most
        ticks (a contract only the live recorder has ranks after every archived
        one) -- then that contract's best file: complete archive > live >
        incomplete archive. So a front month whose manifest honestly says
        "incomplete" (an hour missing) never loses to a thin back month that
        happens to be complete."""
        fs = self.files(root, d)
        if not fs:
            return None

        def rank(c):
            arch = [f.ticks for f in fs if _key(f.contract) == c and not f.live]
            return (1, max(arch)) if arch else (0, max(f.ticks for f in fs if _key(f.contract) == c))
        contract = max(sorted({_key(f.contract) for f in fs}), key=rank)
        fs = [f for f in fs if _key(f.contract) == contract]
        done = [f for f in fs if not f.live and f.complete]
        if done:
            return max(done, key=lambda f: f.ticks)
        live = [f for f in fs if f.live]
        part = [f for f in fs if not f.live]
        if live:
            f = max(live, key=lambda f: f.ticks)
            if part:
                return replace(f, merge_with=max(part, key=lambda a: a.ticks).path)
            return f
        return max(part, key=lambda f: f.ticks) if part else None

    def archive_stamp(self, root: str, d: dt.date) -> tuple | None:
        """(name, size, mtime_ns) of every non-live tick file of session d, sorted; None if there
        is none. Cheap (a glob and stats): the live service compares it to learn that the hourly
        repair job (or the nightly merge) rewrote an archive file under a session it already holds."""
        out = []
        for f in self.files(root, d):
            if f.live:
                continue
            st = _stamp(f.path)
            if st is not None:
                out.append((f.path.name, *st))
        return tuple(sorted(out)) or None

    def sessions(self, root: str) -> list[dt.date]:
        ds = set()
        for p in (self.base / root).glob("*/*.csv.gz"):
            try:
                ds.add(dt.date.fromisoformat(p.name[:10]))
            except ValueError:
                continue
        return sorted(ds)

    def gaps(self, f: SessionFile) -> list:
        if not f.live:
            return []
        try:
            return json.loads(gaps_path(f.path).read_text())
        except (OSError, ValueError):
            return []

    def _union(self, f: SessionFile) -> Session | None:
        """f (live) unioned with its incomplete archive, cached by both files' (size, mtime).
        None when tickarchive.merge refuses (the two are not one id space): the caller then
        uses the live file alone, exactly as before."""
        arch = f.merge_with
        a, b = _stamp(arch), _stamp(f.path)          # BEFORE the read: a write that lands mid-read re-misses next time
        if a is None or b is None:
            return None
        key = (str(arch), a, str(f.path), b)
        with self._merged_lock:
            hit = self._merged.get(key)
        if hit is not None:
            return hit
        try:
            m = TA.merge([("archive", TA.iter_rows(arch)), ("live", TA.iter_rows(f.path))])
        except (TA.MergeRefused, ValueError) as e:
            self.merge_refused[f.path.name] = str(e)
            return None
        self.merge_refused.pop(f.path.name, None)
        ticks, quotes = ticks_from_table(list(TA.COLS), m.rows, live=True)
        sess = Session(_root_of(f.path), _date_of(f.path), f.contract, "live", ticks, quotes, [])
        with self._merged_lock:
            self._merged[key] = sess
            while len(self._merged) > self.MERGE_MEMO:
                self._merged.pop(next(iter(self._merged)))
        return sess

    def load(self, root: str, d: dt.date) -> Session | None:
        """The session's ticks. READ-ONLY. A live file with an incomplete archive beside it comes
        back as their union (see the module docstring); .ticks of a cached union is shared between
        callers -- treat it as immutable (list(...) before changing)."""
        f = self.pick(root, d)
        if f is None:
            return None
        if f.live and f.merge_with is not None:
            u = self._union(f)
            if u is not None:
                return replace(u, gaps=self.gaps(f))      # gaps are tiny and change on their own
        header, recs = read_table(f.path)
        ticks, quotes = ticks_from_table(header, recs, live=f.live)
        return Session(root, d, f.contract, "live" if f.live else "archive",
                       ticks, quotes, self.gaps(f))
