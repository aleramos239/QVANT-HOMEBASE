"""One read API over the tick files, for charts (and later backtests).

Two kinds of file live side by side under ~/futures_ticks/<ROOT>/<YYYY>/:
  <date>_<contract>.csv.gz       the nightly archive (manifest .json beside
                                 it; Massive backfills carry no bid/ask)
  <date>_<contract>.live.csv.gz  the chart service's own live recording
                                 (+ <date>_<contract>.live.gaps)

Per session ONE file is used, never a merge (Massive and Tradovate ids are
different spaces): complete archive > live > incomplete archive; on a roll
day the contract with the most ticks wins.
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import json
import re
import zlib
from dataclasses import dataclass, field
from pathlib import Path

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


class TickStore:
    def __init__(self, base: Path = ARCHIVE):
        self.base = Path(base)

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
        for group in ([f for f in fs if not f.live and f.complete],
                      [f for f in fs if f.live],
                      [f for f in fs if not f.live]):
            if group:
                return max(group, key=lambda f: f.ticks)
        return None

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

    def load(self, root: str, d: dt.date) -> Session | None:
        f = self.pick(root, d)
        if f is None:
            return None
        header, recs = read_table(f.path)
        ticks, quotes = ticks_from_table(header, recs, live=f.live)
        return Session(root, d, f.contract, "live" if f.live else "archive",
                       ticks, quotes, self.gaps(f))
