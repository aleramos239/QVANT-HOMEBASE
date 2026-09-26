"""Session tapes for the Strategy Tester.

Source: ~/futures_ticks/<ROOT>/<YYYY>/<date>_<contract>.csv.gz — READ-ONLY, never
written. The front contract of a session is the archive file whose manifest
counts the most ticks (the research rule; a session under MIN_TICKS is a
holiday stub and has no tape). The chart service's own `.live.csv.gz`
recordings are never used.

Cache: one binary file per session, ~/futures_derived/homebase_tape/<ROOT>/<date>.tape,
built on first use (the desk's venv has no pyarrow, so not parquet):
  MAGIC, u32 header length, JSON header {v, root, date, contract, src, src_mtime_ns,
  src_size, n, byteorder, daily: {h, l, c}}, then n x int64 ts_ns, n x float64
  price, n x int32 size. A cache whose source file changed is rebuilt.
Rows keep TAPE ORDER: a stable sort by ts_ns, applied only if the file is not
already sorted (prints sharing a nanosecond keep their row order).

Coverage: any clock hour inside a strategy's session window with zero prints
means the session is skipped and listed ("missing 13:00–15:00 ET").

Half days (Item 2): CME shortens equity-index trading to 13:15 ET on a handful
of sessions a year -- the day after Thanksgiving, and (when they fall on a
weekday) Jul 3 and Dec 24. That empty afternoon is a normal early close, not a
coverage hole: `effective_session_window` clamps a strategy's window to the
early close on those dates so coverage is checked against the shortened day and
the runner's per-session window (which the strategy's flat/cancel times ride)
ends there too -- a flat/cancel time scheduled after the early close simply
never fires, because the session's own last event time already has.
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import json
import os
import sys
import zlib
from array import array
from bisect import bisect_left
from dataclasses import dataclass
from operator import le
from pathlib import Path

from zoneinfo import ZoneInfo

ARCHIVE = Path.home() / "futures_ticks"
CACHE = Path.home() / "futures_derived" / "homebase_tape"
MIN_TICKS = 1000
MAGIC = b"HBTAPE1\n"
CACHE_VERSION = 1
ET = ZoneInfo("America/New_York")


def et_ns(d: dt.date, hhmm: str) -> int:
    """'HH:MM' or 'HH:MM:SS' ET wall clock on calendar day d -> UTC epoch ns."""
    t = dt.time.fromisoformat(hhmm)
    return int(dt.datetime.combine(d, t, tzinfo=ET).timestamp()) * 1_000_000_000


@dataclass
class Tape:
    root: str
    date: dt.date
    contract: str
    ts: array           # 'q' UTC epoch ns, tape order
    px: array           # 'd'
    size: array         # 'q'
    daily: dict         # the whole session's {"h", "l", "c"}


def _inside(p: Path, parent: Path) -> bool:
    try:
        p.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def read_archive_csv(path: Path) -> tuple[array, array, array]:
    """(ts_ns, price, size) in file order. ts_ns falls back to ts_ms * 1e6
    (desk recordings carry ms only). A torn gzip tail keeps what was read."""
    ts, px, sz = array("q"), array("d"), array("i")
    try:
        with gzip.open(path, "rt", newline="") as fh:
            rd = csv.reader(fh)
            head = next(rd, None) or []
            ix = {k: i for i, k in enumerate(head)}
            ip, isz, ims, ins = ix["price"], ix["size"], ix["ts_ms"], ix.get("ts_ns")
            n = len(head)
            for r in rd:
                if len(r) != n or r[0] == head[0]:
                    continue
                t = r[ins] if ins is not None else ""
                ts.append(int(t) if t else int(r[ims]) * 1_000_000)
                px.append(float(r[ip]))
                sz.append(int(r[isz] or 0))
    except (EOFError, zlib.error, OSError):
        pass
    return ts, px, sz


def stable_sorted(ts: array, px: array, sz: array) -> tuple[array, array, array]:
    if all(map(le, ts, ts[1:])):
        return ts, px, sz
    order = sorted(range(len(ts)), key=ts.__getitem__)       # list.sort is stable
    return (array("q", (ts[i] for i in order)), array("d", (px[i] for i in order)),
            array("i", (sz[i] for i in order)))


def missing_hours(ts, d: dt.date, window: tuple[str, str]) -> list[tuple[str, str]]:
    """Runs of clock-hour pieces of the ET window [start, end) with zero prints,
    e.g. [("13:00", "15:00")]. Pieces are cut at every o'clock."""
    t0 = dt.datetime.combine(d, dt.time.fromisoformat(window[0]))
    t1 = dt.datetime.combine(d, dt.time.fromisoformat(window[1]))
    cuts = [t0]
    h = t0.replace(minute=0, second=0) + dt.timedelta(hours=1)
    while h < t1:
        cuts.append(h)
        h += dt.timedelta(hours=1)
    cuts.append(t1)
    out: list[list[str]] = []
    for a, b in zip(cuts, cuts[1:]):
        na, nb = et_ns(d, a.strftime("%H:%M:%S")), et_ns(d, b.strftime("%H:%M:%S"))
        if bisect_left(ts, nb) - bisect_left(ts, na) > 0:
            continue
        sa, sb = a.strftime("%H:%M"), b.strftime("%H:%M")
        if out and out[-1][1] == sa:
            out[-1][1] = sb
        else:
            out.append([sa, sb])
    return [(a, b) for a, b in out]


def coverage_reason(gaps: list[tuple[str, str]]) -> str:
    return "missing " + ", ".join(f"{a}–{b}" for a, b in gaps) + " ET"


# ---- half days (Item 2) ----
# CME's published holiday calendar (cmegroup.com/tools-information/holiday-calendar.html)
# shortens equity-index trading (ES/MES, NQ/MNQ, YM/MYM, RTY/M2K, NKD) to 13:15 ET on:
#   * the day after Thanksgiving (always a Friday: the 4th Thursday of November + 1 day);
#   * Dec 24, when it falls on a weekday (a weekend Dec 24 is simply not a trading day);
#   * Jul 3, when it falls on a weekday, OR -- when Jul 3 is a weekend day -- whichever
#     weekday actually carries the reduced session ahead of the Jul 4th long weekend.
#     2021 is the only such case in this window: Jul 4, 2021 was a Sunday (the holiday was
#     observed Monday Jul 5), so the reduced session fell on the preceding Friday, Jul 2;
#     in 2022 Jul 4 fell on a Monday, so Jul 1 (Friday) was an ordinary full session and
#     there was no separate half day that year.
EQUITY_INDEX_ROOTS = {"ES", "MES", "NQ", "MNQ", "YM", "MYM", "RTY", "M2K", "NKD"}
EQUITY_EARLY_CLOSE_ET = "13:15"

_JULY_HALF_DAY_OR_OBSERVED: dict[int, dt.date | None] = {
    2021: dt.date(2021, 7, 2), 2022: None, 2023: dt.date(2023, 7, 3),
    2024: dt.date(2024, 7, 3), 2025: dt.date(2025, 7, 3), 2026: dt.date(2026, 7, 3),
}


def _thanksgiving_friday(year: int) -> dt.date:
    """The day after the 4th Thursday of November."""
    nov1 = dt.date(year, 11, 1)
    first_thu = nov1 + dt.timedelta(days=(3 - nov1.weekday()) % 7)
    return first_thu + dt.timedelta(weeks=3, days=1)


def _build_early_closes(years) -> frozenset[dt.date]:
    out = set()
    for y in years:
        out.add(_thanksgiving_friday(y))
        dec24 = dt.date(y, 12, 24)
        if dec24.weekday() < 5:
            out.add(dec24)
        jul = _JULY_HALF_DAY_OR_OBSERVED.get(y)
        if jul is not None:
            out.add(jul)
    return frozenset(out)


EARLY_CLOSES = _build_early_closes(range(2021, 2027))    # the research window + a margin


def early_close_et(root: str, d: dt.date) -> str | None:
    """The ET wall-clock time trading ends on an early-close session for `root`, or
    None on an ordinary day (or a root/asset class this calendar has no time for)."""
    if d in EARLY_CLOSES and root in EQUITY_INDEX_ROOTS:
        return EQUITY_EARLY_CLOSE_ET
    return None


def effective_session_window(root: str, d: dt.date, window: tuple[str, str]) -> tuple[str, str]:
    """`window` clamped to an early close: on a half day an equity-index root's
    session ends at `early_close_et` instead of its ordinary close. Coverage is
    checked against this shortened window (the empty afternoon is not a hole), and
    the runner also feeds it to the engine as that day's session_window, so a
    flat/cancel time scheduled past the early close never fires."""
    close = early_close_et(root, d)
    return (window[0], close) if close is not None and close < window[1] else window


class TapeStore:
    def __init__(self, archive: Path = ARCHIVE, cache: Path = CACHE, min_ticks: int = MIN_TICKS):
        self.archive, self.cache, self.min_ticks = Path(archive), Path(cache), min_ticks
        if _inside(self.cache, self.archive):
            raise ValueError(f"the tape cache may never live under the tick archive ({self.archive})")

    def sessions(self, root: str, start: dt.date, end: dt.date) -> list[dt.date]:
        """Weekday session dates in [start, end] that have any archive manifest."""
        out = set()
        for y in range(start.year, end.year + 1):
            for man in (self.archive / root / str(y)).glob("*.json"):
                try:
                    d = dt.date.fromisoformat(man.name[:10])
                except ValueError:
                    continue
                if start <= d <= end and d.weekday() < 5:
                    out.add(d)
        return sorted(out)

    def pick(self, root: str, d: dt.date) -> tuple[Path, str] | None:
        """(csv.gz path, contract) of the session's front contract, or None."""
        best, best_n = None, 0
        for man in sorted((self.archive / root / str(d.year)).glob(f"{d.isoformat()}_*.json")):
            try:
                n = int(json.loads(man.read_text())["ticks"])
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if n > best_n:
                best, best_n = man, n
        if best is None or best_n < self.min_ticks:
            return None
        gz = best.with_name(best.name[:-len(".json")] + ".csv.gz")
        return (gz, best.name[len("YYYY-MM-DD_"):-len(".json")]) if gz.exists() else None

    def cache_path(self, root: str, d: dt.date) -> Path:
        return self.cache / root / f"{d.isoformat()}.tape"

    def _header(self, p: Path) -> dict | None:
        try:
            with open(p, "rb") as f:
                if f.read(len(MAGIC)) != MAGIC:
                    return None
                n = int.from_bytes(f.read(4), "little")
                return json.loads(f.read(n))
        except (OSError, ValueError):
            return None

    def _fresh(self, head: dict | None, src: Path) -> bool:
        if not head or head.get("v") != CACHE_VERSION or head.get("byteorder") != sys.byteorder:
            return False
        st = src.stat()
        return head.get("src") == src.name and head.get("src_mtime_ns") == st.st_mtime_ns \
            and head.get("src_size") == st.st_size

    def cached(self, root: str, d: dt.date) -> bool:
        got = self.pick(root, d)
        return got is not None and self._fresh(self._header(self.cache_path(root, d)), got[0])

    def build(self, root: str, d: dt.date) -> Path | None:
        got = self.pick(root, d)
        if got is None:
            return None
        src, contract = got
        st = src.stat()
        ts, px, sz = stable_sorted(*read_archive_csv(src))
        if not ts:
            return None
        head = {"v": CACHE_VERSION, "root": root, "date": d.isoformat(), "contract": contract,
                "src": src.name, "src_mtime_ns": st.st_mtime_ns, "src_size": st.st_size,
                "n": len(ts), "byteorder": sys.byteorder,
                "daily": {"h": max(px), "l": min(px), "c": px[-1]}}
        p = self.cache_path(root, d)
        if _inside(p, self.archive):
            raise ValueError("refusing to write under the tick archive")
        p.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(head).encode()
        tmp = p.with_name(p.name + f".{os.getpid()}.tmp")
        with open(tmp, "wb") as f:
            f.write(MAGIC)
            f.write(len(raw).to_bytes(4, "little"))
            f.write(raw)
            ts.tofile(f)
            px.tofile(f)
            sz.tofile(f)
        os.replace(tmp, p)
        return p

    def load(self, root: str, d: dt.date) -> Tape | None:
        got = self.pick(root, d)
        if got is None:
            return None
        p = self.cache_path(root, d)
        if not self._fresh(self._header(p), got[0]):
            if self.build(root, d) is None:
                return None
        with open(p, "rb") as f:
            f.read(len(MAGIC))
            head = json.loads(f.read(int.from_bytes(f.read(4), "little")))
            n = head["n"]
            ts, px, sz = array("q"), array("d"), array("i")
            ts.fromfile(f, n)
            px.fromfile(f, n)
            sz.fromfile(f, n)
        return Tape(root, d, head["contract"], ts, px, sz, head["daily"])

    def daily(self, root: str, d: dt.date) -> dict | None:
        """The session's whole-day {"date", "h", "l", "c"} (builds the cache if needed)."""
        got = self.pick(root, d)
        if got is None:
            return None
        p = self.cache_path(root, d)
        head = self._header(p)
        if not self._fresh(head, got[0]):
            if self.build(root, d) is None:
                return None
            head = self._header(p)
        return {"date": d.isoformat(), **head["daily"]}


def _warm_one(args) -> str:
    archive, cache, root, d = args
    s = TapeStore(Path(archive), Path(cache))
    if not s.cached(root, d):
        s.build(root, d)
    return d.isoformat()


def main(argv: list[str] | None = None) -> None:
    """python -m homebase.backtest.tape warm NQ 2021-01-01 2024-12-31 [--jobs 4]"""
    import argparse
    from concurrent.futures import ProcessPoolExecutor
    ap = argparse.ArgumentParser(prog="python -m homebase.backtest.tape")
    ap.add_argument("cmd", choices=["warm"])
    ap.add_argument("root")
    ap.add_argument("start", type=dt.date.fromisoformat)
    ap.add_argument("end", type=dt.date.fromisoformat)
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args(argv)
    store = TapeStore()
    days = store.sessions(a.root.upper(), a.start, a.end)
    jobs = [(str(store.archive), str(store.cache), a.root.upper(), d) for d in days]
    with ProcessPoolExecutor(max_workers=max(1, a.jobs)) as ex:
        for i, d in enumerate(ex.map(_warm_one, jobs), 1):
            if i % 50 == 0 or i == len(jobs):
                print(f"{i}/{len(jobs)} {d}", flush=True)


if __name__ == "__main__":
    main()
