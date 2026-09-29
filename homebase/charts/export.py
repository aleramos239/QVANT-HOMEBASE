"""Data export for the charts page (Settings -> Data tab): candles, ticks, level 1 quotes and
level 2 depth snapshots, streamed to a CSV(.gz) file in a SEPARATE process -- this service also
records live ticks and depth, so a heavy export must never stall its event loop (GOTCHAS:
"nothing heavy on the event loop... a full-day depth decode stalled the loop 14x until it moved
to its own process").

    <state>/export/jobs/<id>/
        request.json     the validated request
        status.json       {id, status, phase, sessions_done, sessions_total, rows, pid, updated,
                           error?, result?: {path, name, rows, bytes}}
        log.txt           the child's stdout/stderr (an uncaught crash, never the page)

status: queued -> running -> done | error | cancelled. ONE export at a time: submit() refuses a
second while one is active (spec: "One export at a time"), never queues a second one silently.
The child is `python -m homebase.charts.export exec <job_dir>`, launched by ExportManager from a
background thread with its own interpreter -- never in this process, exactly the pattern
homebase.backtest.runner uses for tester runs (see RunManager there), simplified: no slots, no
sandbox (export reads only local archives, never strategy code).

Output: <out_dir>/<ROOT>_<type>[_<tf>]_<from>_<to>.csv[.gz], <out_dir> = $HB_EXPORT_DIR or
~/Downloads. A unique name is chosen if the target exists ("name (2).csv"); the file is built at
a `.part` sibling and only renamed onto the real name on success, so a cancelled or crashed job
never leaves a half-written file under the name the page shows.

Row sources, all read-only (never opens a broker/market-data connection, never writes under
~/futures_ticks or ~/futures_depth):
  candles/ticks/level1   TickStore (store.py) picks the session file (front month = the busiest
                         file, TickStore.pick -- the SAME rule History/the live chart use, so an
                         export's candles match what the chart showed) or one named contract
                         (TickStore.files); read_table + ticks_from_table (also store.py) do the
                         parsing/dedup/side-classification -- nothing here reimplements them.
  candles                bars.build(), the chart's own bar builder, on that session's ticks.
  level2                 depth.read_depth() over ~/futures_depth's per-session snapshot file.
One session's ticks (or one day's depth file) are held in memory at a time, never a whole range.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import json
import os
import re
import secrets
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Iterator

from fastapi import APIRouter, Depends, HTTPException, Request

from ..contracts import tick_size as contract_tick_size
from ..paths import repo_root, state_dir
from . import QUIET
from .bars import BarSpec, build as build_bars
from .depth import DEPTH_ARCHIVE, read_depth
from .session import ET, always_open
from .store import ARCHIVE, TickStore, read_table, ticks_from_table
from .tester_api import host_ok

# The full archive: futures_ticks/README.md's "Roots: NQ ES YM RTY GC SI HG ZN CL NG 6E 6J 6B BTC MBT."
ROOTS = ("NQ", "ES", "YM", "RTY", "GC", "SI", "HG", "ZN", "CL", "NG", "6E", "6J", "6B", "BTC", "MBT")
DEPTH_ROOTS = ("NQ", "ES")             # level 2 is recorded for these only (charts-depth design)
TYPES = ("candles", "ticks", "level1", "level2")   # level3 is validated and refused, never listed as choosable
# label -> BarSpec key. The export's own list (the task spec), independent of the live chart's
# TIMEFRAMES (server.py) -- a batch build off disk has no MIN_BAR streaming-cost floor.
TIMEFRAMES = [("1s", "time:1"), ("5s", "time:5"), ("15s", "time:15"), ("30s", "time:30"),
              ("1m", "time:60"), ("3m", "time:180"), ("5m", "time:300"), ("15m", "time:900"),
              ("30m", "time:1800"), ("1h", "time:3600"), ("4h", "time:14400"), ("1D", "time:86400")]
TIMEFRAME_KEY = dict(TIMEFRAMES)
RTH_START, RTH_END = dt.time(9, 30), dt.time(16, 0)
L2_LEVELS_MAX = 10
FINAL = {"done", "error", "cancelled"}
JOB_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{8}$")
_CONTRACT_RE = re.compile(r"[A-Z0-9]{2,12}")


# ------------------------------------------------------------------------- availability / coverage

def expected_sessions(root: str, d0: dt.date, d1: dt.date) -> list[dt.date]:
    """Calendar dates in [d0, d1] this root holds a session on: every day for a 24/7 root
    (session.always_open), Monday-Friday for a classic one. A plain listing -- no file read."""
    if d1 < d0:
        d0, d1 = d1, d0
    open247 = always_open(root)
    out, d = [], d0
    while d <= d1:
        if open247 or d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def list_contracts(store: TickStore, root: str) -> list[str]:
    """Every distinct contract on disk for `root`, sorted -- a filename scan, no content read."""
    out = set()
    for p in (store.base / root).glob("*/*.csv.gz"):
        tag = p.name[:10]
        try:
            dt.date.fromisoformat(tag)
        except ValueError:
            continue
        out.add(p.name[len(tag) + 1:].split(".")[0])
    return sorted(out)


def tick_range(store: TickStore, root: str) -> tuple[str, str] | None:
    ds = store.sessions(root)
    return (ds[0].isoformat(), ds[-1].isoformat()) if ds else None


def quotes_range(store: TickStore, root: str) -> tuple[str, str] | None:
    """The bid/ask-bearing range: desk recordings only (from 2026-09-22, futures_ticks/README.md),
    always the MOST RECENT sessions -- so this walks backward from today and stops at the first
    session with no quotes, rather than scanning the whole 5-year archive."""
    start = end = None
    for d in reversed(store.sessions(root)):
        f = store.pick(root, d)
        if f is None or not f.bid_ask:
            break
        start = d
        if end is None:
            end = d
    return (start.isoformat(), end.isoformat()) if start else None


def depth_sessions(depth_base: Path, root: str) -> list[dt.date]:
    ds = set()
    for p in (Path(depth_base) / root).glob("*/*.depth.jsonl.gz"):
        try:
            ds.add(dt.date.fromisoformat(p.name[:10]))
        except ValueError:
            continue
    return sorted(ds)


def depth_range(depth_base: Path, root: str) -> tuple[str, str] | None:
    ds = depth_sessions(depth_base, root)
    return (ds[0].isoformat(), ds[-1].isoformat()) if ds else None


def depth_file(depth_base: Path, root: str, d: dt.date) -> Path | None:
    """The session's depth file -- ranked by size (a roll day can list BOTH the outgoing and the
    incoming contract; only one of them was actually subscribed and has any real depth in it).
    The same cheap-signal rule TickStore uses to rank a manifest-less (live) tick file: never a
    decode just to pick, and never merely the alphabetically last name."""
    matches = (Path(depth_base) / root / str(d.year)).glob(f"{d.isoformat()}_*.depth.jsonl.gz")

    def size(p: Path) -> int:
        try:
            return p.stat().st_size
        except OSError:
            return -1

    return max(matches, key=lambda p: (size(p), p.name), default=None)


def _pick_file(store: TickStore, root: str, d: dt.date, contract: str):
    if contract == "front":
        return store.pick(root, d)
    return next((f for f in store.files(root, d) if f.contract == contract), None)


def missing_ticks(store: TickStore, root: str, dates, contract: str = "front") -> list[str]:
    return [d.isoformat() for d in dates if _pick_file(store, root, d, contract) is None]


def missing_depth(depth_base: Path, root: str, dates) -> list[str]:
    return [d.isoformat() for d in dates if depth_file(depth_base, root, d) is None]


def session_gaps(store: TickStore, root: str, dates, contract: str = "front") -> dict:
    """{date: [[start_ms, end_ms], ...]} for sessions with a KNOWN gap -- free (TickStore.gaps
    reads the live recorder's small sidecar file, never decodes ticks), so only a live-recorded
    session ever reports one; an archive-complete session reports none (finding one there would
    need a full decode, not "cheap" -- GOTCHAS)."""
    out = {}
    for d in dates:
        f = _pick_file(store, root, d, contract)
        if f is None:
            continue
        g = store.gaps(f)
        if g:
            out[d.isoformat()] = g
    return out


# ------------------------------------------------------------------------------------ row shaping

def _in_rth(ts_ms: int) -> bool:
    t = dt.datetime.fromtimestamp(ts_ms / 1000, ET).time()
    return RTH_START <= t < RTH_END


class TsFmt:
    """How a row's timestamp is written: ET or UTC, ISO-with-ms or epoch ms; and whether a row
    outside 09:30-16:00 ET is dropped (RTH is always ET-defined, whatever the output timezone)."""

    def __init__(self, tz: str, ts_format: str, rth: bool):
        self.zone = ET if tz == "et" else dt.timezone.utc
        self.epoch = ts_format == "epoch"
        self.rth = rth

    def fmt(self, ms: int):
        if self.epoch:
            return ms
        return dt.datetime.fromtimestamp(ms / 1000, self.zone).isoformat(timespec="milliseconds")

    def keep(self, ms: int) -> bool:
        return not self.rth or _in_rth(ms)


def columns(kind: str, levels: int = 10) -> list[str]:
    if kind == "candles":
        return ["time", "open", "high", "low", "close", "volume"]
    if kind == "ticks":
        return ["time", "price", "size", "bid", "ask", "bid_size", "ask_size"]
    if kind == "level1":
        return ["time", "bid", "bid_size", "ask", "ask_size", "last", "last_size"]
    if kind == "level2":
        # paired per level (price, size), bids then asks -- matches iter_level2's row order exactly
        cols = ["time"]
        for i in range(1, levels + 1):
            cols += [f"bid_px_{i}", f"bid_sz_{i}"]
        for i in range(1, levels + 1):
            cols += [f"ask_px_{i}", f"ask_sz_{i}"]
        return cols
    raise ValueError(f"no columns for {kind!r}")


def _ordered(header: list[str], recs: list[list[str]], live: bool) -> list[list[str]]:
    """A live file's rows, deduped by id and re-sorted by (time, id) -- store.ticks_from_table's
    own live-refill rule, replicated here (not imported) because this keeps every raw column
    (bid_size/ask_size), which ticks_from_table's Tick objects drop."""
    if not live:
        return recs
    idx = {k: i for i, k in enumerate(header)}
    iid = idx.get("id")
    if iid is None:
        return recs
    seen: set[str] = set()
    uniq = []
    for r in recs:
        k = r[iid]
        if k and k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    it = idx["ts_ms"]
    return sorted(uniq, key=lambda r: (int(r[it]), int(r[iid] or 0)))


def _opt_f(r: list[str], i: int | None):
    if i is None or r[i] in (None, ""):
        return ""
    return float(r[i])


def _opt_i(r: list[str], i: int | None):
    if i is None or r[i] in (None, ""):
        return ""
    return int(float(r[i]))


def iter_candles(store: TickStore, root: str, d: dt.date, contract: str, spec: BarSpec,
                 ts: TsFmt) -> Iterator[tuple]:
    f = _pick_file(store, root, d, contract)
    if f is None:
        return
    header, recs = read_table(f.path)
    session_ticks, _ = ticks_from_table(header, recs, live=f.live)
    closed, cur = build_bars(session_ticks, spec, contract_tick_size(root), root)
    if cur is not None:              # the session is over: its developing bar is done (history.py's own rule)
        cur.closed = True
        closed.append(cur)
    for b in closed:
        if ts.keep(b.t):
            yield (ts.fmt(b.t), b.o, b.h, b.l, b.c, b.v)


def iter_ticks(store: TickStore, root: str, d: dt.date, contract: str, ts: TsFmt) -> Iterator[tuple]:
    f = _pick_file(store, root, d, contract)
    if f is None:
        return
    header, recs = read_table(f.path)
    recs = _ordered(header, recs, f.live)
    idx = {k: i for i, k in enumerate(header)}
    it, ip, isz = idx["ts_ms"], idx["price"], idx["size"]
    ib, ia, ibs, iaz = idx.get("bid"), idx.get("ask"), idx.get("bid_size"), idx.get("ask_size")
    for r in recs:
        tms = int(r[it])
        if not ts.keep(tms):
            continue
        yield (ts.fmt(tms), float(r[ip]), int(r[isz]), _opt_f(r, ib), _opt_f(r, ia),
               _opt_i(r, ibs), _opt_i(r, iaz))


def iter_level1(store: TickStore, root: str, d: dt.date, contract: str, ts: TsFmt) -> Iterator[tuple]:
    """Quote-at-trade, from desk recordings only (from 2026-09-22): a Massive-backfill session
    (SessionFile.bid_ask False) is skipped whole, cheaply -- that flag is manifest metadata, read
    before any tick content."""
    f = _pick_file(store, root, d, contract)
    if f is None or not f.bid_ask:
        return
    header, recs = read_table(f.path)
    recs = _ordered(header, recs, f.live)
    idx = {k: i for i, k in enumerate(header)}
    it, ip, isz = idx["ts_ms"], idx["price"], idx["size"]
    ib, ia, ibs, iaz = idx.get("bid"), idx.get("ask"), idx.get("bid_size"), idx.get("ask_size")
    for r in recs:
        b, a = _opt_f(r, ib), _opt_f(r, ia)
        if b == "" and a == "":              # no quote recorded for this particular trade
            continue
        tms = int(r[it])
        if not ts.keep(tms):
            continue
        yield (ts.fmt(tms), b, _opt_i(r, ibs), a, _opt_i(r, iaz), float(r[ip]), int(r[isz]))


def iter_level2(depth_base: Path, root: str, d: dt.date, levels: int, ts: TsFmt) -> Iterator[tuple]:
    p = depth_file(depth_base, root, d)
    if p is None:
        return
    for row in read_depth(p):
        tms = row.get("t")
        if not isinstance(tms, (int, float)):
            continue
        tms = int(tms)
        if not ts.keep(tms):
            continue
        b, a = row.get("b") or [], row.get("a") or []
        out = [ts.fmt(tms)]
        out += [v for i in range(levels) for v in (b[i] if i < len(b) else ["", ""])]
        out += [v for i in range(levels) for v in (a[i] if i < len(a) else ["", ""])]
        yield tuple(out)


# ------------------------------------------------------------------------------------ validation

def _date(v, name: str) -> dt.date:
    if not isinstance(v, str):
        raise ValueError(f'{name}: "YYYY-MM-DD"')
    try:
        return dt.date.fromisoformat(v)
    except ValueError:
        raise ValueError(f'{name}: "YYYY-MM-DD"') from None


def validate(body: dict) -> dict:
    """The request, normalized -- or ValueError with the one sentence the dialog shows."""
    if not isinstance(body, dict):
        raise ValueError("expected a JSON object")
    root = str(body.get("root", "")).strip().upper()
    if root not in ROOTS:
        raise ValueError(f"root: one of {', '.join(ROOTS)}")
    kind = str(body.get("type", "")).strip().lower()
    if kind == "level3":
        raise ValueError("Level 3 (order-by-order) isn't in Tradovate's feed, so it is never recorded")
    if kind not in TYPES:
        raise ValueError(f"type: one of {', '.join(TYPES)}")
    if kind == "level2" and root not in DEPTH_ROOTS:
        raise ValueError(f"level 2 is recorded for {', '.join(DEPTH_ROOTS)} only")
    raw_contract = str(body.get("contract") or "front").strip()
    if raw_contract.lower() == "front":
        contract = "front"
    else:
        contract = raw_contract.upper()
        if not _CONTRACT_RE.fullmatch(contract):
            raise ValueError('contract: "front", or a contract code such as NQZ6')
    timeframe = None
    if kind == "candles":
        timeframe = str(body.get("timeframe", "")).strip()
        if timeframe not in TIMEFRAME_KEY:
            raise ValueError(f"timeframe: one of {', '.join(k for k, _ in TIMEFRAMES)}")
    start = _date(body.get("start"), "start")
    end = _date(body.get("end"), "end")
    if end < start:
        raise ValueError("end must not be before start")
    hours = body.get("hours", "full")
    if hours not in ("full", "rth"):
        raise ValueError("hours: full or rth")
    tz = body.get("tz", "et")
    if tz not in ("et", "utc"):
        raise ValueError("tz: et or utc")
    ts_format = body.get("ts_format", "iso")
    if ts_format not in ("iso", "epoch"):
        raise ValueError("ts_format: iso or epoch")
    fmt = body.get("format", "csv")
    if fmt not in ("csv", "gz"):
        raise ValueError("format: csv or gz")
    levels = None
    if kind == "level2":
        levels = body.get("levels", 10)
        if isinstance(levels, bool) or not isinstance(levels, int) or not 1 <= levels <= L2_LEVELS_MAX:
            raise ValueError(f"levels: a whole number 1-{L2_LEVELS_MAX}")
    return {"root": root, "type": kind, "contract": contract, "timeframe": timeframe,
            "start": start.isoformat(), "end": end.isoformat(), "hours": hours, "tz": tz,
            "ts_format": ts_format, "format": fmt, "levels": levels}


# ---------------------------------------------------------------------------------- output naming

def export_dir() -> Path:
    v = os.environ.get("HB_EXPORT_DIR")
    return Path(v).expanduser() if v else Path.home() / "Downloads"


def output_name(req: dict) -> str:
    bits = [req["root"], req["type"]]
    if req["type"] == "candles":
        bits.append(req["timeframe"])
    bits += [req["start"], req["end"]]
    return "_".join(bits) + (".csv.gz" if req["format"] == "gz" else ".csv")


def unique_path(dir_: Path, name: str) -> Path:
    """`name`, or "name (2).csv"/".csv.gz" etc. if it already exists in dir_."""
    p = dir_ / name
    if not p.exists():
        return p
    if name.endswith(".csv.gz"):
        stem, suffix = name[: -len(".csv.gz")], ".csv.gz"
    else:
        stem, suffix = name[: -len(".csv")], ".csv"
    n = 2
    while True:
        cand = dir_ / f"{stem} ({n}){suffix}"
        if not cand.exists():
            return cand
        n += 1


# -------------------------------------------------------------------------------------- the write

def run_export(req: dict, archive: Path, depth_base: Path, out_path: Path,
               on_progress: Callable[[int, int, int], None] = lambda done, total, rows: None) -> dict:
    """Streams every row straight to out_path (the caller picks the path -- a `.part` sibling
    while running is the CLI's job, not this function's, so a test can call this directly and
    just look at the file it asked for). Holds one session's ticks (or one day's depth file) at a
    time; never the whole range. Returns {"rows": total, "sessions_total": n}."""
    store = TickStore(archive)
    root, kind = req["root"], req["type"]
    dates = expected_sessions(root, dt.date.fromisoformat(req["start"]), dt.date.fromisoformat(req["end"]))
    ts = TsFmt(req["tz"], req["ts_format"], req["hours"] == "rth")
    levels = req.get("levels") or L2_LEVELS_MAX
    cols = columns(kind, levels)
    spec = BarSpec.parse(TIMEFRAME_KEY[req["timeframe"]]) if kind == "candles" else None
    opener = gzip.open if req["format"] == "gz" else open
    rows = 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with opener(out_path, "wt", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for i, d in enumerate(dates):
            if kind == "candles":
                it = iter_candles(store, root, d, req["contract"], spec, ts)
            elif kind == "ticks":
                it = iter_ticks(store, root, d, req["contract"], ts)
            elif kind == "level1":
                it = iter_level1(store, root, d, req["contract"], ts)
            else:
                it = iter_level2(depth_base, root, d, levels, ts)
            for row in it:
                w.writerow(row)
                rows += 1
            on_progress(i + 1, len(dates), rows)
    return {"rows": rows, "sessions_total": len(dates)}


# ---------------------------------------------------------------------------------- job bookkeeping

def default_base() -> Path:
    return state_dir() / "charts" / "export"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, data) -> None:
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":"), default=str))
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _alive(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def in_quiet(now: dt.datetime) -> bool:
    """09:20-09:35 ET on a weekday -- the 9:30 bot's window (GOTCHAS: "Nothing new starts in it:
    no backtest, no heavy decode..."); a multi-session export is exactly that heavy a decode."""
    t = (now if now.tzinfo else now.replace(tzinfo=ET)).astimezone(ET)
    return t.weekday() < 5 and QUIET[0] <= t.time() < QUIET[1]


class ExportManager:
    """The chart service's handle on export jobs (thread-safe; no asyncio). One at a time."""

    def __init__(self, base: Path, *, archive: Path = ARCHIVE, depth_base: Path = DEPTH_ARCHIVE,
                python: str = sys.executable, out_dir: Path | None = None,
                clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(ET)):
        self.base = Path(base)
        self.jobs = self.base / "jobs"
        self.jobs.mkdir(parents=True, exist_ok=True)
        self.archive, self.depth_base, self.python = Path(archive), Path(depth_base), python
        self.out_dir = Path(out_dir) if out_dir else export_dir()
        self.clock = clock
        self._lock = threading.Lock()
        self._active: tuple[str, subprocess.Popen] | None = None
        self._cancelled: set[str] = set()
        self._recover()

    def _recover(self) -> None:
        """Jobs a previous service process left queued/running are dead now (the chart service
        restarted): never shown as stuck forever."""
        for st_path in self.jobs.glob("*/status.json"):
            st = read_json(st_path, {}) or {}
            if st.get("status") in ("queued", "running") and not _alive(st.get("pid")):
                st.update(status="error", error="interrupted (the chart service restarted)", updated=_now())
                write_json(st_path, st)

    def dir(self, jid: str) -> Path:
        if not JOB_ID_RE.match(jid or "") or not (self.jobs / jid).is_dir():
            raise KeyError(jid)
        return self.jobs / jid

    def submit(self, body: dict) -> str:
        req = validate(body)
        with self._lock:
            if self._active is not None:
                raise ValueError("an export is already running — wait for it, or cancel it, first")
            if in_quiet(self.clock()):
                raise ValueError("not 09:20–09:35 ET on weekdays (the 9:30 window): export after 09:35")
            jid = f"{dt.datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(4)}"
            d = self.jobs / jid
            d.mkdir(parents=True)
            try:
                write_json(d / "request.json", {**req, "id": jid, "created": _now()})
                write_json(d / "status.json", {"id": jid, "status": "queued", "phase": "queued",
                                               "sessions_done": 0, "sessions_total": 0, "rows": 0,
                                               "updated": _now()})
                proc = self._launch(d)
            except BaseException:
                import shutil
                shutil.rmtree(d, ignore_errors=True)
                raise
            self._active = (jid, proc)
        threading.Thread(target=self._watch, args=(jid, proc), daemon=True).start()
        return jid

    def _launch(self, job_dir: Path) -> subprocess.Popen:
        log = open(job_dir / "log.txt", "ab")
        argv = [self.python, "-m", "homebase.charts.export", "exec", str(job_dir),
                "--archive", str(self.archive), "--depth-base", str(self.depth_base),
                "--out-dir", str(self.out_dir)]
        try:
            proc = subprocess.Popen(argv, cwd=repo_root(), stdout=log, stderr=subprocess.STDOUT)
        except BaseException:
            log.close()
            raise
        proc.hb_log = log
        return proc

    def _watch(self, jid: str, proc: subprocess.Popen) -> None:
        try:
            code = proc.wait()
        finally:
            proc.hb_log.close()
        with self._lock:
            if self._active is not None and self._active[0] == jid:
                self._active = None
            cancelled = jid in self._cancelled
            self._cancelled.discard(jid)
        if cancelled:
            return                              # cancel() already wrote the final status
        d = self.jobs / jid
        st = read_json(d / "status.json", {}) or {}
        if st.get("status") not in FINAL:
            tail = ""
            log_path = d / "log.txt"
            if log_path.exists():
                tail = log_path.read_text(errors="replace")[-800:]
            st.update(status="error", error=f"export exited {code}: {tail}".strip(), updated=_now())
            write_json(d / "status.json", st)

    def status(self, jid: str) -> dict:
        return read_json(self.dir(jid) / "status.json", {}) or {}

    def active(self) -> dict:
        """The running job, or else the most recently submitted one (job ids sort chronologically)
        -- so reopening Settings can reattach to it: its Cancel/progress if still running, or its
        Done/error line if it already finished. {} when there has never been a job."""
        with self._lock:
            active = self._active
        if active is not None:
            return self.status(active[0])
        dirs = sorted(p.name for p in self.jobs.iterdir() if JOB_ID_RE.match(p.name))
        return self.status(dirs[-1]) if dirs else {}

    def cancel(self, jid: str) -> dict:
        d = self.dir(jid)
        with self._lock:
            st = read_json(d / "status.json", {}) or {}
            if st.get("status") in FINAL:
                return st
            if self._active is None or self._active[0] != jid:
                raise ValueError("this export was not started by this chart service")
            proc = self._active[1]
            self._cancelled.add(jid)
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        with self._lock:
            if self._active is not None and self._active[0] == jid:
                self._active = None
        st = read_json(d / "status.json", {}) or {}
        if st.get("status") == "done":
            return st                           # it finished before the signal landed
        tmp = st.get("tmp_path")
        if tmp:
            Path(tmp).unlink(missing_ok=True)   # never leave a half-written file under the page's nose
        st.update(status="cancelled", phase="cancelled", updated=_now())
        write_json(d / "status.json", st)
        return st

    def shutdown(self) -> None:
        """Chart-service shutdown: an export this manager launched must never be left orphaned."""
        with self._lock:
            active = self._active
        if active is not None:
            try:
                self.cancel(active[0])
            except ValueError:
                pass

    def reveal(self, jid: str) -> Path:
        st = self.status(jid)
        if st.get("status") != "done":
            raise ValueError("that export has no finished file yet")
        path = (st.get("result") or {}).get("path")
        if not path or not Path(path).is_file():
            raise ValueError("that file is gone")
        return Path(path)


# --------------------------------------------------------------------------------------- the CLI

def _exec(job_dir: Path, archive: Path, depth_base: Path, out_dir: Path) -> int:
    """`python -m homebase.charts.export exec <job_dir>`: the child ExportManager launches. Writes
    status.json as it goes (so the page can poll progress) and only ever touches out_dir."""
    st_path = job_dir / "status.json"
    req = read_json(job_dir / "request.json", {}) or {}
    st = read_json(st_path, {}) or {}
    st.update(status="running", phase="running", pid=os.getpid(), updated=_now())
    write_json(st_path, st)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    final = unique_path(out_dir, output_name(req))
    part = final.with_name(final.name + ".part")
    st["tmp_path"] = str(part)
    write_json(st_path, st)

    def progress(done: int, total: int, rows: int) -> None:
        st.update(status="running", phase="running", sessions_done=done, sessions_total=total,
                  rows=rows, updated=_now())
        write_json(st_path, st)

    try:
        result = run_export(req, archive, depth_base, part, progress)
    except Exception as e:                      # noqa: BLE001 -- reported to status.json, never a bare crash
        part.unlink(missing_ok=True)
        st.update(status="error", error=f"{type(e).__name__}: {e}", updated=_now())
        write_json(st_path, st)
        return 1
    os.replace(part, final)
    st.pop("tmp_path", None)
    st.update(status="done", phase="done", sessions_done=result["sessions_total"],
              sessions_total=result["sessions_total"], rows=result["rows"], updated=_now(),
              result={"path": str(final), "name": final.name, "rows": result["rows"],
                      "bytes": final.stat().st_size})
    write_json(st_path, st)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m homebase.charts.export")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("exec", help="run a prepared job dir (the chart service uses this)")
    ex.add_argument("job_dir", type=Path)
    ex.add_argument("--archive", type=Path, default=ARCHIVE)
    ex.add_argument("--depth-base", type=Path, default=DEPTH_ARCHIVE)
    ex.add_argument("--out-dir", type=Path, default=None)
    a = ap.parse_args(argv)
    if a.cmd == "exec":
        return _exec(a.job_dir, a.archive, a.depth_base, a.out_dir if a.out_dir else export_dir())
    return 2


# ------------------------------------------------------------------------------------- the router

def export_router(write_ok: Callable[[Request], None], archive: Path, depth_base: Path,
                  state: Path | None = None, out_dir: Path | None = None,
                  reveal_run: Callable | None = None) -> APIRouter:
    """GET routes read the archive straight from FastAPI's threadpool (plain `def`, like
    tester_api's -- never on the event loop); POSTs also pass `write_ok` (the service's Origin +
    Host write guard, the same one every other write route here uses)."""
    base = Path(state) if state else default_base()
    mgr = ExportManager(base, archive=archive, depth_base=depth_base, out_dir=out_dir)
    store = TickStore(archive)
    run_cmd = reveal_run or subprocess.run
    r = APIRouter(prefix="/api/export", dependencies=[Depends(host_ok)])

    @r.get("/schema")
    def schema():
        return {"roots": list(ROOTS), "depth_roots": list(DEPTH_ROOTS),
                "timeframes": [k for k, _ in TIMEFRAMES], "types": [*TYPES, "level3"]}

    @r.get("/active")
    def active():
        """The running job, or else the most recent one -- so the Data tab can reattach to it
        (Cancel, progress, or a Done/error line) after Settings is closed and reopened."""
        return mgr.active()

    @r.get("/meta")
    def meta(root: str, type: str):
        root = root.upper()
        if root not in ROOTS:
            raise HTTPException(404, f"{root!r} is not an export root")
        if type in ("candles", "ticks"):
            return {"range": list(tick_range(store, root) or ()) or None, "contracts": list_contracts(store, root)}
        if type == "level1":
            return {"range": list(quotes_range(store, root) or ()) or None, "contracts": list_contracts(store, root)}
        if type == "level2":
            rng = depth_range(depth_base, root) if root in DEPTH_ROOTS else None
            return {"range": list(rng) if rng else None, "contracts": []}
        return {"range": None, "contracts": []}

    @r.get("/coverage")
    def coverage(root: str, type: str, start: str, end: str, contract: str = "front"):
        root = root.upper()
        if root not in ROOTS:
            raise HTTPException(404, f"{root!r} is not an export root")
        try:
            d0, d1 = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
        except ValueError:
            raise HTTPException(400, 'start/end: "YYYY-MM-DD"') from None
        dates = expected_sessions(root, d0, d1)
        if type == "level2":
            missing, hours = missing_depth(depth_base, root, dates), {}
        else:
            missing, hours = missing_ticks(store, root, dates, contract), session_gaps(store, root, dates, contract)
        return {"sessions_total": len(dates), "missing": missing, "missing_hours": hours}

    @r.post("/start")
    def start(request: Request, body: dict):
        write_ok(request)
        try:
            return {"id": mgr.submit(body)}
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    def known(jid: str) -> Path:
        try:
            return mgr.dir(jid)
        except KeyError:
            raise HTTPException(404, f"no export {jid!r}") from None

    @r.get("/{jid}")
    def status(jid: str):
        known(jid)
        return mgr.status(jid)

    @r.post("/{jid}/cancel")
    def cancel(jid: str, request: Request):
        write_ok(request)
        known(jid)
        try:
            return mgr.cancel(jid)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @r.post("/{jid}/reveal")
    def reveal(jid: str, request: Request):
        write_ok(request)
        known(jid)
        try:
            path = mgr.reveal(jid)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None
        run_cmd(["open", "-R", str(path)], check=False)
        return {"ok": True, "path": str(path)}

    r.manager = mgr
    return r


if __name__ == "__main__":
    raise SystemExit(main())
