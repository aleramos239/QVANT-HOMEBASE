"""The tick archive's files: read, merge, verify, write. One gzip CSV + a .json
manifest per root / session / contract, ~/futures_ticks/<ROOT>/<YYYY>/.

Merge, never replace. A session's archive file is the UNION of every source
the desk has for it:
  * the broker's tick history (homebase.ticks, the nightly fetch),
  * the chart service's live recording, <date>_<contract>.live.csv.gz (only
    ever read here: it is never rewritten, moved or deleted),
  * the archive file already on disk (an earlier fetch, a Massive backfill).

Broker rows (history and live alike) carry the broker's tick id: one counter
per contract, gap-free, the same in the history and the live stream. Checked
2026-09-28 on the archive itself: every nightly file's ids are contiguous
(n == last - first + 1, 21 files, 5.3M ticks), NQ 09-24's first id is 09-23's
last + 1, and ES's live 09-28 recording starts at id 10,114,406, the id after
the 09-25 history file's last tick. So broker rows merge BY ID: a tick either
source has is kept once, with the bid/ask of whichever source has them. What
is already on disk wins a disagreement (the archive file, then the live
recording, then a fresh fetch): a written tick is never rewritten. A tick id
that comes back with a different time, price or size is a conflict: the
on-disk version stays and it is counted; more than CONFLICTS_REFUSED refuse
the merge (the originals stay).

A Massive row (it has `ts_ns`) carries no broker id -- its `id` is the
exchange channel's sequence number, repeated across the price levels of one
match -- and it is one row per match and price level where the broker sends
one per fill (2.4x the rows, the same volume hour by hour: NG 2026-09-22). So
a Massive row is kept only where no broker tick is within MASSIVE_GUARD_MS of
it: only in a stretch the broker's data does not cover. The two stamp the
same trade 1 ms apart typically, 416 ms at worst (3,052 isolated NG trades,
2026-09-28); the guard is five times that. Rows within the guard of a broker
tick are the same trades as those ticks, or a hole's edge: never counted twice.

Written atomically: a temporary file beside the target, read back and checked
(every broker tick id of every source present, the Massive row count, the
order) before it replaces the original, then the manifest the same way.
"""
from __future__ import annotations

import bisect
import csv
import datetime as dt
import gzip
import io
import json
import os
import zlib
from array import array
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

UTC = dt.timezone.utc
# the archive's columns: the broker's (homebase.ticks.FIELDS) + Massive's ns stamp
COLS = ("ts_ms", "price", "size", "bid", "ask", "bid_size", "ask_size", "id", "ts_ns")
BROKER_COLS = COLS[:8]
TS, PX, SZ, BID, ASK, BIDSZ, ASKSZ, ID, TSNS = range(9)
LIVE_SUFFIX = ".live.csv.gz"            # = homebase.charts.store.LIVE_SUFFIX (a test holds them equal)
MASSIVE_GUARD_MS = 2000
CONFLICTS_REFUSED = 5                   # more same-id disagreements than this: refuse, change nothing
SOURCES_KEPT = 40                       # the manifest's merge log keeps this many entries


class MergeRefused(RuntimeError):
    """The merge would not be exact (conflicting ids, an unreadable original):
    nothing is written and the original stays."""


# ------------------------------------------------------------------ rows
def text(v) -> str:
    """A value as the archive writes it: '' for none, else str() -- exactly
    what csv.DictWriter wrote for the broker's floats and ints."""
    return "" if v is None or v == "" else str(v)


def row_of(d: dict) -> tuple:
    """A broker tick (homebase.ticks._unpack) -> the archive's 9-column row."""
    return tuple(text(d.get(k)) for k in BROKER_COLS) + ("",)


def is_massive(r: tuple) -> bool:
    return bool(r[TSNS])


def read_header(path: Path) -> list[str]:
    try:
        with gzip.open(path, "rt", newline="") as fh:
            return next(csv.reader(fh), None) or []
    except (EOFError, zlib.error, OSError):
        return []


def iter_rows(path: Path):
    """Every row of an archive or live file as the 9 archive columns (missing
    ones ''), streamed. A live file holds one gzip member per flush and may end
    in a member torn by a crash: the torn tail is dropped, never raised
    (homebase.charts.store.read_table's rule); a repeated header is skipped."""
    try:
        with gzip.open(path, "rt", newline="") as fh:
            rd = csv.reader(fh)
            header = next(rd, None) or []
            n = len(header)
            pos = [header.index(c) if c in header else None for c in COLS]
            for rec in rd:
                if len(rec) != n or rec == header:
                    continue
                yield tuple(rec[i] if i is not None else "" for i in pos)
    except (EOFError, zlib.error, OSError):
        return


def read_rows(path: Path) -> tuple[list[str], list[tuple]]:
    """(header, rows) -- iter_rows, held in memory."""
    return read_header(path), list(iter_rows(path))


def sort_key(r: tuple):
    m = is_massive(r)
    return (int(r[TS]), m, int(r[TSNS]) if m else 0, int(r[ID] or 0))


# ------------------------------------------------------------------ merge
@dataclass
class Merged:
    rows: list[tuple]                   # the file's content, in file order
    ids: set = field(default_factory=set)   # every broker tick id in it
    massive: int = 0                    # rows from Massive
    stats: dict = field(default_factory=dict)


def _near(sorted_ts: list[int], ts: int, guard: int) -> bool:
    i = bisect.bisect_left(sorted_ts, ts - guard)
    return i < len(sorted_ts) and sorted_ts[i] <= ts + guard


def merge(sources, massive_new: list[tuple] = (), guard_ms: int = MASSIVE_GUARD_MS) -> Merged:
    """The union of `sources` ([(name, rows)], the first -- on disk -- wins a disagreement;
    rows may be a stream, read once) plus `massive_new` (Massive rows offered
    to fill holes). Module docstring for the rules; raises MergeRefused when
    the ids disagree too often."""
    by_id: dict[int, tuple] = {}
    noid: Counter = Counter()           # broker rows without an id: union of the per-source counts
    massive_old: list[tuple] = []
    per_source: dict[str, set] = {}
    read: dict[str, int] = {}
    conflicts: list[int] = []
    overlap = quotes_filled = quote_disagreements = 0
    for name, rows in sources:
        mine: set = per_source.setdefault(name, set())
        here: Counter = Counter()
        n = 0
        for r in rows:
            n += 1
            if is_massive(r):
                massive_old.append(r)
                continue
            if not r[ID]:
                here[r] += 1
                continue
            k = int(r[ID])
            mine.add(k)
            have = by_id.get(k)
            if have is None:
                by_id[k] = r
                continue
            overlap += 1
            if (int(have[TS]), float(have[PX]), int(have[SZ])) != (int(r[TS]), float(r[PX]), int(r[SZ])):
                conflicts.append(k)
                continue                                    # the first source's version stays
            if not (have[BID] and have[ASK]) and r[BID] and r[ASK]:
                by_id[k] = have[:BID] + r[BID:ID] + have[ID:]
                quotes_filled += 1
            elif (have[BID] and have[ASK] and r[BID] and r[ASK]
                  and (float(have[BID]), float(have[ASK])) != (float(r[BID]), float(r[ASK]))):
                quote_disagreements += 1
        read[name] = read.get(name, 0) + n
        for k, c in here.items():
            noid[k] = max(noid[k], c)
    if len(conflicts) > CONFLICTS_REFUSED:
        raise MergeRefused(f"{len(conflicts)} tick ids disagree between sources (time/price/size), "
                           f"e.g. {conflicts[:5]} -- not one id space; nothing merged")
    broker = list(by_id.values()) + [r for r, n in noid.items() for _ in range(n)]
    broker_ts = sorted(int(r[TS]) for r in broker)
    kept_old = [r for r in massive_old if not _near(broker_ts, int(r[TS]), guard_ms)]
    have_m = Counter((int(r[TSNS]), float(r[PX]), int(r[SZ])) for r in massive_old)
    added, near_broker, duplicates = [], 0, 0
    for r in massive_new:
        if _near(broker_ts, int(r[TS]), guard_ms):
            near_broker += 1
            continue
        k = (int(r[TSNS]), float(r[PX]), int(r[SZ]))
        if have_m[k] > 0:
            have_m[k] -= 1                                  # this very row is on file already
            duplicates += 1
            continue
        added.append(r)
    rows = broker + kept_old + added
    rows.sort(key=sort_key)
    ids = set(by_id)
    only = {n: len(s - set().union(*(o for m, o in per_source.items() if m != n)))
            for n, s in per_source.items()}
    stats = {"broker_ticks": len(broker), "massive_rows": len(kept_old) + len(added),
             "read": read, "only_in": only,
             "id_overlap": overlap, "id_conflicts": len(conflicts), "conflict_ids": conflicts[:10],
             "quotes_filled": quotes_filled, "quote_disagreements": quote_disagreements,
             "massive_dropped_near_broker": len(massive_old) - len(kept_old)}
    if massive_new:
        stats.update({"massive_offered": len(massive_new), "massive_added": len(added),
                      "massive_skipped_near_broker": near_broker, "massive_already_on_file": duplicates})
    return Merged(rows, ids, len(kept_old) + len(added), stats)


# ------------------------------------------------------------------ write
def atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def verify(path: Path, m: Merged, fields: tuple) -> None:
    """Read `path` back (streamed) and hold it to `m`: the header, the row
    count, every broker tick id, the Massive row count, time order. Raises
    MergeRefused."""
    problems = []
    header = read_header(path)
    if tuple(header) != fields:
        problems.append(f"header {header}")
    n = massive = 0
    got: set = set()
    last, ordered = None, True
    for r in iter_rows(path):
        n += 1
        ts = int(r[TS])
        ordered = ordered and (last is None or last <= ts)
        last = ts
        if is_massive(r):
            massive += 1
        elif r[ID]:
            got.add(int(r[ID]))
    if n != len(m.rows):
        problems.append(f"{n} rows read back, {len(m.rows)} written")
    if got != m.ids:
        problems.append(f"{len(m.ids - got)} tick ids missing, {len(got - m.ids)} extra")
    if massive != m.massive:
        problems.append("Massive row count differs")
    if not ordered:
        problems.append("rows out of time order")
    if problems:
        raise MergeRefused(f"{path.name} did not verify: " + "; ".join(problems))


def write_rows(path: Path, m: Merged) -> tuple[str, ...]:
    """Write `m` over `path` atomically: a temporary file beside it, fsynced,
    read back and verified, then renamed over the original (which stays
    untouched until then). Broker-only files keep the broker's 8 columns;
    a file with Massive rows adds `ts_ns`, set exactly on those rows."""
    fields = COLS if m.massive else BROKER_COLS
    n = len(fields)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".merge.tmp")
    try:
        with open(tmp, "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=6) as gz:
                with io.TextIOWrapper(gz, newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(fields)
                    w.writerows(r[:n] for r in m.rows)
            raw.flush()
            os.fsync(raw.fileno())
        verify(tmp, m, fields)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return fields


# ------------------------------------------------------------------ manifest
def manifest_path(path: Path) -> Path:
    return path.with_name(path.name[:-len(".csv.gz")] + ".json")


def load_manifest(path: Path) -> dict:
    try:
        return json.loads(manifest_path(path).read_text())
    except (OSError, ValueError):
        return {}


def iso_ms(ms: int | None) -> str | None:
    return dt.datetime.fromtimestamp(ms / 1000, UTC).isoformat() if ms is not None else None


def now_utc() -> str:
    return dt.datetime.now(UTC).isoformat(timespec="seconds")


def ms_of(iso: str | None) -> int | None:
    return int(dt.datetime.fromisoformat(iso).timestamp() * 1000) if iso else None


def prior_sources(prev: dict) -> list[dict]:
    """A manifest's merge log. One written before merges were logged gets one
    entry saying what the file was: a Massive backfill, or a nightly fetch --
    which paged back from the close until the broker ran dry, so it covered
    everything from its first tick to the close ("legacy")."""
    if "sources" in prev:
        return list(prev["sources"])
    if not prev:
        return []
    if prev.get("source") == "massive":
        return [{"kind": "massive", "file": prev.get("source_file"), "rows": prev.get("ticks"),
                 "at_utc": prev.get("recorded_at_utc")}]
    return [{"kind": "history", "stop": "legacy", "to_utc": prev.get("session_end_utc"),
             "earliest_ms": ms_of(prev.get("first_tick_utc")), "ticks": prev.get("ticks"),
             "pages": prev.get("pages"), "at_utc": prev.get("recorded_at_utc")}]


# ------------------------------------------------------------------ what a file holds, by tick id
# The broker's tick id is one gap-free counter per contract (module docstring),
# so a file's broker ticks are fully described by RUNS of consecutive ids,
# [id_lo, id_hi, ts_lo, ts_hi]: whatever lies between two runs is missing,
# exactly (id_lo of the next - id_hi - 1 ticks, between ts_hi and ts_lo).
def union_runs(a: list, b: list) -> list:
    """Two run lists as one: overlapping or adjacent runs joined."""
    out: list = []
    for r in sorted([list(x) for x in a] + [list(x) for x in b]):
        if out and r[0] <= out[-1][1] + 1:
            last = out[-1]
            if r[1] > last[1]:
                last[1], last[3] = r[1], r[3]
        else:
            out.append(r)
    return out


def runs_of(pairs) -> list:
    """[(id, ts), ...] in any order -> runs of consecutive ids."""
    out: list = []
    for i, t in sorted(pairs):
        if out and i <= out[-1][1]:
            continue                            # the same id again
        if out and i == out[-1][1] + 1:
            out[-1][1], out[-1][3] = i, t
        else:
            out.append([i, i, t, t])
    return out


def _complete_members(data: bytes) -> tuple[bytes, int]:
    """The text of every whole gzip member in `data` and where the last one
    ends: a member torn by a write in progress (the live recorder appends one a
    second) is left for next time. Fed 4 KB at a time, so a day's ~57k members
    decode in one linear pass."""
    mv, n, pos, out = memoryview(data), len(data), 0, []
    while pos < n:
        d, parts, start = zlib.decompressobj(wbits=31), [], pos
        while not d.eof and pos < n:
            chunk = mv[pos:pos + 4096]
            try:
                parts.append(d.decompress(chunk))
            except zlib.error:
                return b"".join(out), start
            pos += len(chunk)
        if not d.eof:
            return b"".join(out), start
        pos -= len(d.unused_data)
        out.extend(parts)
    return b"".join(out), pos


def _scan_text(text: bytes, header: list | None) -> tuple[list, list]:
    """(header, [(id, ts)] of the broker rows) of CSV text; rows without the
    header's width are skipped (a Massive row, with ts_ns, has no broker id)."""
    rd = csv.reader(io.StringIO(text.decode("utf-8", "replace")))
    if header is None:
        header = next(rd, None) or []
    ix = {c: i for i, c in enumerate(header)}
    it, iid, ins, n = ix.get("ts_ms"), ix.get("id"), ix.get("ts_ns"), len(header)
    pairs = []
    if it is None or iid is None:
        return header, pairs
    for r in rd:
        if len(r) != n or r == header or not r[iid] or (ins is not None and r[ins]):
            continue
        pairs.append((int(r[iid]), int(r[it])))
    return header, pairs


def file_runs(path: Path, cache: dict) -> dict:
    """{"runs": [[id_lo, id_hi, ts_lo, ts_hi], ...]} of an archive or live
    file, memoized in `cache` (JSON-able). A file that only grew since (a live
    recording: one gzip member appended a second) is read from where the last
    read ended; anything else is read whole again."""
    try:
        st = path.stat()
    except OSError:
        return {"runs": []}
    key = str(path)
    c = cache.get(key)
    if c and c.get("ino") == st.st_ino and c.get("mtime_ns") == st.st_mtime_ns and c.get("size") == st.st_size:
        return c
    grow = bool(c and c.get("ino") == st.st_ino and c.get("offset", 0) <= st.st_size and c.get("header"))
    offset = c["offset"] if grow else 0
    with open(path, "rb") as f:
        f.seek(offset)
        text, used = _complete_members(f.read())
    header, pairs = _scan_text(text, c["header"] if grow else None)
    out = {"ino": st.st_ino, "size": st.st_size, "mtime_ns": st.st_mtime_ns, "offset": offset + used,
           "header": header, "runs": union_runs(c["runs"] if grow else [], runs_of(pairs))}
    cache[key] = out
    return out


# ------------------------------------------------------------------ coverage
COVERAGE_VERSION = 1
HOUR_MS = 3_600_000
EDGE_MS = 5 * 60 * 1000             # ticks this close to the open / the close count as reaching it
NOT_MODELLED = (
    "Known: the 17:00-18:00 ET break, weekends, CME crypto trading 24/7 (BTC, MBT), and the "
    "equity-index 13:15 ET half days (homebase.backtest.tape.early_close_et). NOT known: full-day "
    "exchange holidays and holiday halts (e.g. 13:00 ET on Thanksgiving, Labor Day, July 4), and "
    "early closes of non-equity roots -- a 'close' hole, or a missing weekday session, may be the "
    "exchange's schedule rather than lost data. A missing session whose trades the next session's "
    "file already holds is flagged 'filed_under_next_session'.")


def merge_spans(spans) -> list[tuple[int, int]]:
    """[lo, hi] stretches, sorted, overlapping or touching ones joined."""
    out: list[list[int]] = []
    for lo, hi in sorted(spans):
        if out and lo <= out[-1][1]:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return [(a, b) for a, b in out]


def uncovered(spans, a: int, b: int) -> list[tuple[int, int]]:
    """The parts of [a, b] no span (merged, sorted) covers; a single instant
    (a == b) is either covered or itself."""
    if a == b:
        return [] if covers(spans, a, a) else [(a, a)]
    out, x = [], a
    for lo, hi in spans:
        if hi <= x or lo >= b:
            continue
        if lo > x:
            out.append((x, lo))
        x = max(x, hi)
        if x >= b:
            break
    if x < b:
        out.append((x, b))
    return out


def verified_spans(sources: list[dict]) -> list[tuple[int, int]]:
    """[lo, hi] ms stretches the broker's history served in full, merged, from
    the merge log: a fetch paged back without a gap from where it started down
    to its earliest tick -- or to the start of the stretch it was asked for
    when it went past it ("reached") or found nothing older ("exhausted": the
    stretch lies inside the broker's window, so there is nothing older in it).
    A fetch cut short vouches only for what it paged through."""
    spans = []
    for s in sources:
        if s.get("kind") != "history" or not s.get("to_utc"):
            continue
        hi = s.get("resumed_from_ms") or ms_of(s["to_utc"])
        if s.get("stop") in ("reached", "exhausted") and s.get("from_utc"):
            lo = ms_of(s["from_utc"])
        elif s.get("earliest_ms") is not None:
            lo = s["earliest_ms"]
        else:
            continue
        spans.append((lo, hi))
    return merge_spans(spans)


def covers(spans, a: int, b: int) -> bool:
    """Is [a, b] inside one verified span?"""
    return any(lo <= a and b <= hi for lo, hi in spans)



def coverage(rows: list[tuple], *, root: str, date: dt.date, start: dt.datetime, end: dt.datetime,
             sources: list[dict] = ()) -> dict:
    """Hour-by-hour coverage of one session file (rows in file order).

    Expected hours: every clock hour from the open to the close (18:00 ET ->
    17:00 ET, the 17:00-18:00 break outside it; weekends have no session; a
    known equity-index half day ends at 13:15 ET). A HOLE is an expected hour
    without a single tick, unless it is proven quiet: the broker's ticks just
    before and after it have consecutive ids (nothing traded in between) --
    or, at an end of the file where there is no tick on one side, a history
    fetch that covered it in full found nothing. MISSING_IDS: broker
    ids skipped inside the file where no Massive row stands in for them.
    head_ok / tail_ok: a tick within 5 min of the open / close, or a history
    fetch covering it. Complete = ticks, no hole, no missing id, both ends."""
    from .backtest.tape import early_close_et          # stdlib-only; the repo's half-day calendar
    if any(int(a[TS]) > int(b[TS]) for a, b in zip(rows, rows[1:])):
        rows = sorted(rows, key=sort_key)               # a live file: refills append older rows
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    close = early_close_et(root, date)
    stop_ms = end_ms
    if close is not None:
        stop_ms = min(end_ms, int(dt.datetime.combine(date, dt.time.fromisoformat(close),
                                                      start.tzinfo).timestamp() * 1000))
    ts = array("q")
    b_ts, b_id, m_ts = array("q"), array("q"), array("q")
    for r in rows:
        t = int(r[TS])
        ts.append(t)
        if is_massive(r):
            m_ts.append(t)
        elif r[ID]:
            b_ts.append(t)
            b_id.append(int(r[ID]))
    spans = verified_spans(list(sources))
    buckets = []
    a = start_ms
    while a < stop_ms:
        b = min(a + HOUR_MS, stop_ms)
        buckets.append((a, b, bisect.bisect_left(ts, b) - bisect.bisect_left(ts, a)))
        a += HOUR_MS
    holes, quiet = [], 0
    for a, b, n in buckets:
        if n:
            continue
        i = bisect.bisect_left(b_ts, a)
        if 0 < i < len(b_ts):                   # broker ticks on both sides: their ids decide
            proven = b_id[i] == b_id[i - 1] + 1
        else:                                   # at an end of the file: a fetch that covered it
            proven = covers(spans, a, b)
        if proven:
            quiet += 1
            continue
        if holes and holes[-1][1] == a:
            holes[-1][1] = b
        else:
            holes.append([a, b])
    missing = 0
    for k in range(1, len(b_id)):
        gap = b_id[k] - b_id[k - 1] - 1
        if gap > 0:
            j = bisect.bisect_right(m_ts, b_ts[k - 1])
            if not (j < len(m_ts) and m_ts[j] < b_ts[k]):
                missing += gap                              # no Massive row stands in for them
    first = ts[0] if ts else None
    last = ts[-1] if ts else None
    head_ok = first is not None and (first - start_ms < EDGE_MS or covers(spans, start_ms, start_ms))
    tail_ok = last is not None and (stop_ms - last < EDGE_MS or covers(spans, end_ms, end_ms))
    et = start.tzinfo

    def hhmm(ms):
        return dt.datetime.fromtimestamp(ms / 1000, et).strftime("%H:%M")
    return {
        "version": COVERAGE_VERSION,
        "expected_hours": len(buckets), "hours_with_ticks": sum(1 for *_, n in buckets if n),
        "quiet_hours": quiet,
        "holes": [{"from_et": hhmm(a), "to_et": hhmm(b), "start_utc": iso_ms(a), "end_utc": iso_ms(b),
                   "hours": round((b - a) / HOUR_MS, 2),
                   "at": "open" if a == start_ms else "close" if b == stop_ms else "inside"}
                  for a, b in holes],
        "hole_hours": round(sum(b - a for a, b in holes) / HOUR_MS, 2),
        "missing_ids": missing, "head_ok": head_ok, "tail_ok": tail_ok,
        "early_close_et": close,
        "complete": bool(ts) and not holes and missing == 0 and head_ok and tail_ok,
    }


def build_manifest(*, root: str, contract: str, date: dt.date, start: dt.datetime, end: dt.datetime,
                   m: Merged, fields: tuple, path: Path, prev: dict, new_sources: list[dict]) -> dict:
    broker = [r for r in m.rows if not is_massive(r)]
    quoted = [r for r in broker if r[BID] and r[ASK]]
    spreads = sorted(float(r[ASK]) - float(r[BID]) for r in quoted)
    inside = sum(1 for r in quoted if float(r[BID]) <= float(r[PX]) <= float(r[ASK]))
    first = int(m.rows[0][TS]) if m.rows else None
    last = int(m.rows[-1][TS]) if m.rows else None
    sources = (prior_sources(prev) + new_sources)[-SOURCES_KEPT:]
    cov = coverage(m.rows, root=root, date=date, start=start, end=end, sources=sources)
    return {
        "root": root, "contract": contract, "session_date": date.isoformat(),
        "session_start_utc": start.astimezone(UTC).isoformat(),
        "session_end_utc": end.astimezone(UTC).isoformat(),
        "ticks": len(m.rows),
        "first_tick_utc": iso_ms(first), "last_tick_utc": iso_ms(last),
        "complete": cov["complete"],
        "source": "massive" if not broker else "desk",
        "bid_ask": bool(broker) and not m.massive,
        "broker_ticks": len(broker), "massive_rows": m.massive,
        "first_id": min(m.ids) if m.ids else None, "last_id": max(m.ids) if m.ids else None,
        "pages": sum(s.get("pages") or 0 for s in sources if s.get("kind") == "history"),
        "median_spread": spreads[len(spreads) // 2] if spreads else None,
        "trade_inside_bid_ask_pct": round(100 * inside / len(quoted), 1) if quoted else None,
        "coverage": cov,
        "sources": sources,
        "merge": m.stats,
        "bytes": path.stat().st_size, "fields": list(fields),
        "recorded_at_utc": now_utc(),
    }


def write_manifest(path: Path, man: dict) -> None:
    atomic_write(manifest_path(path), (json.dumps(man, indent=2) + "\n").encode())


# ------------------------------------------------------------------ one session
def live_path(path: Path) -> Path:
    """The chart service's live recording beside an archive file."""
    return path.with_name(path.name[:-len(".csv.gz")] + LIVE_SUFFIX)


def live_stamp(p: Path) -> dict | None:
    try:
        st = p.stat()
    except OSError:
        return None
    return {"file": p.name, "bytes": st.st_size, "mtime_ns": st.st_mtime_ns}


def live_merged(prev: dict, stamp: dict | None) -> bool:
    """Is this very live file (name, size, mtime) already in the archive file?"""
    return stamp is not None and any(
        s.get("kind") == "live" and all(s.get(k) == stamp[k] for k in ("file", "bytes", "mtime_ns"))
        for s in prev.get("sources", []))


def merge_session(path: Path, *, root: str, contract: str, date: dt.date, start: dt.datetime,
                  end: dt.datetime, fetched: list[tuple] = (), fetched_source: dict | None = None,
                  include_live: bool = True, massive_new: list[tuple] = (),
                  massive_source: dict | None = None, only_if_added: bool = False) -> dict | None:
    """Merge whatever this session has -- `fetched` broker rows, the live
    recording (if `include_live`), the archive file on disk, `massive_new` --
    into its archive file. Returns the new manifest, or None when there is
    nothing at all (or, with only_if_added, when neither Massive nor the live
    file adds anything: the file is left as it is). Raises MergeRefused
    (nothing written) if the file on disk cannot be read or the ids disagree."""
    prev = load_manifest(path)
    sources: list = []                  # (name, rows), on disk first: it wins a disagreement
    new_sources: list[dict] = []
    if fetched_source is not None:
        new_sources.append({**fetched_source, "ticks": len(fetched), "at_utc": now_utc()})
    if path.exists():
        if not read_header(path):
            raise MergeRefused(f"{path.name} is on disk but unreadable -- left as it is")
        sources.append(("archive", iter_rows(path)))
    lp = live_path(path)
    stamp = live_stamp(lp) if include_live else None      # taken BEFORE the read: a row appended
    if stamp is not None and not live_merged(prev, stamp):  # meanwhile makes the next run merge again
        sources.append(("live", iter_rows(lp)))
        new_sources.append({"kind": "live", **stamp, "at_utc": now_utc()})
    if fetched:
        sources.append(("history", fetched))
    if not sources and not massive_new:
        return None
    m = merge(sources, massive_new)
    if not m.rows:
        return None
    if only_if_added and not m.stats.get("massive_added") and not fetched \
            and not any(s.get("kind") == "live" for s in new_sources):
        return None
    if massive_source is not None:
        new_sources.append({**massive_source, "rows_added": m.stats.get("massive_added", 0),
                            "at_utc": now_utc()})
    for s in new_sources:
        if s.get("kind") == "live":
            s["ticks"] = m.stats["read"].get("live", 0)
            s["only_in_live"] = m.stats["only_in"].get("live", 0)
    fields = write_rows(path, m)
    man = build_manifest(root=root, contract=contract, date=date, start=start, end=end, m=m,
                         fields=fields, path=path, prev=prev, new_sources=new_sources)
    write_manifest(path, man)
    return man
