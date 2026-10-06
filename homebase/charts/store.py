"""One read API over the tick files, for charts (and later backtests).

Two kinds of file live side by side under ~/futures_ticks/<ROOT>/<YYYY>/:
  <date>_<contract>.csv.gz       the nightly archive (manifest .json beside
                                 it; Massive backfills carry no bid/ask)
  <date>_<contract>.live.csv.gz  the chart service's own live recording
                                 (+ <date>_<contract>.live.gaps)

Per session ONE contract is used (on a roll day the one with the most ticks),
and per contract: complete archive alone > live + incomplete archive > either
alone. The last case is a UNION: the live file as it always was, plus the
archive's ticks whose tick ids it lacks (the live version of a shared id stays):
the hourly repair job files the ticks a dead Mac never recorded into
the incomplete archive, and the live file alone would leave that hole on the
chart until the nightly merge. Read-only -- nothing here ever writes a file.
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import json
import os
import re
import threading
import zlib
from bisect import bisect_left
from operator import itemgetter
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


_TIME_ID = itemgetter(0, 4)        # Tick's (ts_ms, id)

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
    MERGE_MEMO = 4          # parsed incomplete archives kept (each is small)

    def __init__(self, base: Path = ARCHIVE):
        self.base = Path(base)
        self._archive_memo: dict[tuple, tuple] = {}     # (archive path, (size, mtime)) -> its parsed ticks, oldest first
        self._merged_lock = threading.Lock()

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

    def stamps(self, root: str, dates) -> dict:
        """{date: ((name, size, mtime_ns), ...)} of every tick file -- archive and live -- of each of root's
        `dates` (() for a date with none), from ONE listing per year folder. History.changed() compares them
        to learn that a fill rewrote (or created) a file under a past session a chart already holds."""
        want = {d.isoformat(): d for d in dates}
        out: dict = {d: [] for d in want.values()}
        for year in {d.year for d in want.values()}:
            try:
                with os.scandir(self.base / root / str(year)) as it:
                    for e in it:
                        d = want.get(e.name[:10])
                        if d is None or not e.name.endswith(".csv.gz"):
                            continue
                        try:
                            st = e.stat()
                        except OSError:
                            continue                  # vanished between the listing and here
                        out[d].append((e.name, st.st_size, st.st_mtime_ns))
            except OSError:
                continue
        return {d: tuple(sorted(v)) for d, v in out.items()}

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
            gaps = json.loads(gaps_path(f.path).read_text())
        except (OSError, ValueError):
            return []
        if f.merge_with is not None and gaps:
            gaps = self._minus_archive(f.merge_with, gaps)
        return gaps

    @staticmethod
    def _minus_archive(arch: Path, gaps: list) -> list:
        """The live file's gap markers minus the stretches the incomplete archive's manifest vouches
        for (tickarchive.verified_spans: the broker's history served in full there). A marker stays
        exactly where ticks are still missing; with no readable manifest every marker stays."""
        try:
            spans = TA.verified_spans(TA.prior_sources(TA.load_manifest(arch)))
            if not spans:
                return gaps
            out = []
            for a, b in gaps:
                out.extend([x, y] for x, y in TA.uncovered(spans, int(a), int(b)))
            return out
        except (TypeError, ValueError, KeyError):
            return gaps

    def _archive_side(self, arch: Path) -> tuple | None:
        """(ticks, tick-id set, any quotes) of an incomplete archive file, parsed once per (size, mtime)
        of THAT file: the live file changes every second, the archive only when the repair job
        writes it. The memo is tiny (an archive is a fraction of a live file)."""
        st = _stamp(arch)                               # BEFORE the read: a write landing mid-read re-misses next time
        if st is None:
            return None
        key = (str(arch), st)
        with self._merged_lock:
            hit = self._archive_memo.get(key)
        if hit is not None:
            return hit
        header, recs = read_table(arch)
        ticks, quotes = ticks_from_table(header, recs, live=True)
        side = (ticks, {t.id for t in ticks if t.id}, quotes)
        with self._merged_lock:
            self._archive_memo[key] = side
            while len(self._archive_memo) > self.MERGE_MEMO:
                self._archive_memo.pop(next(iter(self._archive_memo)))
        return side

    def _with_archive(self, f: SessionFile, ticks: list[Tick], quotes: bool) -> tuple[list[Tick], bool]:
        """The live file's ticks plus the incomplete archive's ticks whose ids the live file lacks
        (the live version of a shared id stays; an archive row without an id -- a Massive fill -- is
        added only where the live file has nothing within MASSIVE_NEAR_MS), sorted by (time, id).
        Nothing to add -> `ticks` itself, untouched."""
        side = self._archive_side(f.merge_with)
        if side is None:
            return ticks, quotes
        a_ticks, a_ids, a_quotes = side
        live_ids = {t.id for t in ticks if t.id}
        new = []
        for t in a_ticks:
            if t.id:
                if t.id not in live_ids:
                    new.append(t)
            else:
                i = bisect_left(ticks, t.ts_ms - TA.MASSIVE_EDGE_MS, key=lambda x: x.ts_ms)
                if i >= len(ticks) or ticks[i].ts_ms > t.ts_ms + TA.MASSIVE_EDGE_MS:
                    new.append(t)
        if not new:
            return ticks, quotes
        return sorted(ticks + new, key=_TIME_ID), quotes or a_quotes

    def load(self, root: str, d: dt.date) -> Session | None:
        """The session's ticks. READ-ONLY. A live file with an incomplete archive beside it comes
        back with the archive's ticks it lacks added (see the module docstring); the live side is
        read exactly as it always was and the archive side is cached by the archive's own stamp."""
        f = self.pick(root, d)
        if f is None:
            return None
        header, recs = read_table(f.path)
        ticks, quotes = ticks_from_table(header, recs, live=f.live)
        if f.live and f.merge_with is not None:
            ticks, quotes = self._with_archive(f, ticks, quotes)
        return Session(root, d, f.contract, "live" if f.live else "archive",
                       ticks, quotes, self.gaps(f))
