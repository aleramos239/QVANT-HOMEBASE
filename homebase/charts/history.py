"""Bars of COMPLETED sessions, fast.

Three caches over the TickStore: a per-session 1-minute bar pickle on disk
(built once from ticks; every time bar >= 1m is resampled from it, so a
60-session daily chart never re-reads ticks), beside it a per-session pickle
of each coarse bar type (15 minutes and up: resampling a session is ~30 ms, a
daily chart reads 250 of them), and an in-memory memo per (root, bar type,
date). Today's session is the hub's job, not this file's.
Thread-safe: the hub calls it from worker threads.

A completed session is not final: the hourly tick job fills its holes and
merges its live recording into the archive for a day or two after its close.
The memo -- and the charts already showing the session -- held the old bars
until the 18:00 roll. Every session built here is WATCHED: changed() stats
its tick files and forgets the ones that moved, so the service can reload
the charts that show them.
"""
from __future__ import annotations

import datetime as dt
import os
import pickle
import threading
from glob import escape as glob_escape
from collections import OrderedDict
from pathlib import Path

from ..contracts import tick_size
from ..paths import state_dir
from .bars import Bar, BarSpec, build, resample
from .session import et_wall_s
from .store import TickStore

M1 = BarSpec("time", 60)
CACHE_VERSION = 2
COARSE_MIN = 900        # time bars this coarse (a whole number of minutes) are also kept per session on disk
MEMO_BARS = 400_000     # bars the memo holds across sessions (about what 256 one-minute sessions were): a weight, not a count --
                        # a daily or weekly chart keeps one bar a session, so its 1,300 sessions stay memoized
                        # (they never fitted 256 entries: every 1D / 1W switch re-read a pickle per session, 1-2 s)
WATCH_DAYS = 35         # sessions this recent are watched for a fill landing in their files (the tick job merges
                        # live recordings 30 days back, ticks.LIVE_LOOKBACK_DAYS); older ones only change by hand


class History:
    def __init__(self, store: TickStore, cache_dir: Path | None = None, memo_max: int = 4096, known=None,
                 memo_bars: int = MEMO_BARS):
        self.store = store
        self.known = known      # charts.known.Known: the tick job's coverage report, for each session's holes
        self.cache_dir = Path(cache_dir) if cache_dir else state_dir() / "charts" / "cache"
        self.memo: OrderedDict = OrderedDict()
        self.memo_max = memo_max
        self.memo_bars = memo_bars
        self._weight = 0        # the memo's bars (+1 an entry, so an empty session still counts)
        self._lock = threading.Lock()
        self._gen = 0           # bumped by clear(): a build that overlapped a clear() is not memoized
        self._built: dict = {}  # (root, date) -> its tick files' stamp when its bars were first built: changed()

    def _from_ticks(self, root: str, spec: BarSpec, d: dt.date) -> list[Bar]:
        s = self.store.load(root, d)
        if s is None:
            return []
        closed, cur = build(s.ticks, spec, tick_size(root), root)
        if cur is not None:
            cur.closed = True
            closed.append(cur)
        return closed

    def _cache_file(self, root: str, d: dt.date, f) -> Path:
        return self.cache_dir / (f"v{CACHE_VERSION}_{root}_{d.isoformat()}_{f.contract}_"
                                 f"{'live' if f.live else 'arch'}{'+arch' if f.merge_with else ''}.m1.pkl")

    @staticmethod
    def _src_ns(f) -> int:
        """The newest mtime of the file(s) a session's ticks come from (a live file unioned with its
        incomplete archive has two: a repair landing in either one must rebuild the cache)."""
        ns = f.path.stat().st_mtime_ns
        return max(ns, f.merge_with.stat().st_mtime_ns) if f.merge_with else ns

    def cached(self, root: str, d: dt.date) -> bool:
        """Is session d's 1-minute cache built and current (no older than its tick file)? True with no file."""
        f = self.store.pick(root, d)
        if f is None:
            return True
        try:
            return self._cache_file(root, d, f).stat().st_mtime_ns >= self._src_ns(f)
        except OSError:
            return False

    def minutes(self, root: str, d: dt.date) -> list[Bar]:
        f = self.store.pick(root, d)
        if f is None:
            return []
        cp = self._cache_file(root, d, f)
        src_ns = None
        try:
            src_ns = self._src_ns(f)                        # the source BEFORE its ticks are read
            if cp.stat().st_mtime_ns >= src_ns:
                with open(cp, "rb") as fh:
                    return pickle.load(fh)
        except (OSError, pickle.UnpicklingError, EOFError):
            pass
        bars = self._from_ticks(root, M1, d)
        self._keep(cp, bars, src_ns)
        return bars

    def recount(self, root: str, d: dt.date) -> bool:
        """Give session d's cached bars the aggressive order counts (bars.Bar.ords_b / ords_s) when they were cached
        before those existed: its 1-minute file is rebuilt from the ticks and every coarse file beside it is
        resampled from the new minutes (a coarse file keeps its source's stamp, so it would otherwise stay "fresh"
        and uncounted). False: nothing to do (counted already, no cache, or no ticks)."""
        f = self.store.pick(root, d)
        if f is None:
            return False
        cp = self._cache_file(root, d, f)
        try:
            with open(cp, "rb") as fh:
                old = pickle.load(fh)
        except (OSError, pickle.UnpicklingError, EOFError):
            return False                                    # no cache: the next read builds it, counted
        if not old or old[0].ords_b >= 0:
            return False
        src_ns = self._src_ns(f)
        bars = self._from_ticks(root, M1, d)
        if not bars:
            return False
        self._keep(cp, bars, src_ns)
        stem = cp.name[:-len(".m1.pkl")]
        for coarse in self.cache_dir.glob(glob_escape(stem) + ".t*.pkl"):
            tail = coarse.name[len(stem) + 2:-len(".pkl")]  # ".t900.pkl" -> "900"
            if tail.isdigit():
                self._keep(coarse, resample(bars, BarSpec("time", int(tail))), src_ns)
        return True

    def _keep(self, cp: Path, bars: list[Bar], src_ns: int | None) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = cp.with_name(cp.name + f".{threading.get_ident()}.tmp")
        with open(tmp, "wb") as fh:
            pickle.dump(bars, fh, protocol=pickle.HIGHEST_PROTOCOL)
        if src_ns is not None:
            # stamped with the source as read: a write that lands mid-build (a
            # refill into an old session) leaves the cache older than its source
            os.utime(tmp, ns=(src_ns, src_ns))
        os.replace(tmp, cp)

    def _coarse(self, root: str, spec: BarSpec, d: dt.date) -> list[Bar]:
        """A coarse time bar type of session d (15 minutes and up), kept on disk beside the 1-minute cache under the same
        freshness rule. Resampling 1,400 one-minute bars costs ~30 ms and loading them ~25 ms, so a 250-session daily
        chart was ~14 s of work against the 2 s subscribe budget; from this file a session is a fraction of a ms."""
        f = self.store.pick(root, d)
        if f is None:
            return []
        cp = self._cache_file(root, d, f)
        cp = cp.with_name(cp.name.replace(".m1.pkl", f".t{spec.size}.pkl"))
        src_ns = None
        try:
            src_ns = self._src_ns(f)                        # the source BEFORE its ticks are read
            if cp.stat().st_mtime_ns >= src_ns:
                with open(cp, "rb") as fh:
                    return pickle.load(fh)
        except (OSError, pickle.UnpicklingError, EOFError):
            pass
        out = resample(self.minutes(root, d), spec)
        self._keep(cp, out, src_ns)
        return out

    def bars(self, root: str, spec: BarSpec, d: dt.date, memo: bool = True) -> list[Bar]:
        """Session d's bars of this type. memo=False (scroll-back): a memoized session is used, but a new
        build is not kept, so a deep scroll-back never evicts the open charts' sessions."""
        key = (root, spec.key, d)
        with self._lock:
            hit = self.memo.get(key)
            if hit is not None:
                self.memo.move_to_end(key)
                return hit
            gen = self._gen
        self.watch(root, d)                                 # the files BEFORE their ticks are read
        if spec.from_minutes and spec.size >= COARSE_MIN:
            out = self._coarse(root, spec, d)
        elif spec.from_minutes:
            out = resample(self.minutes(root, d), spec)
        else:
            out = self._from_ticks(root, spec, d)
        if memo:
            with self._lock:
                if gen == self._gen:        # else a clear() landed mid-build: its file may have changed
                    if key in self.memo:
                        self._weight -= len(self.memo[key]) + 1
                    self.memo[key] = out
                    self._weight += len(out) + 1
                    while len(self.memo) > 1 and (len(self.memo) > self.memo_max or self._weight > self.memo_bars):
                        _, old = self.memo.popitem(last=False)
                        self._weight -= len(old) + 1
        return out

    def info(self, root: str, d: dt.date) -> dict:
        """What the page needs to label a session honestly. Cheap: no ticks read. `holes` (only when it has
        any): the session's known holes from the tick job's coverage report, [[start_ms, end_ms, kind], ...]
        with kind lost | filling | thin (charts.known) -- the page draws them as wide as the time they cover."""
        f = self.store.pick(root, d)
        if f is None:
            return {"date": d.isoformat(), "contract": None, "source": None, "approx": False, "gaps": []}
        out = {"date": d.isoformat(), "contract": f.contract,
               "source": "live" if f.live else "archive", "approx": not f.bid_ask,
               "gaps": [[et_wall_s(a), et_wall_s(b)] for a, b in self.store.gaps(f)]}
        holes = self.known.holes(root, d) if self.known is not None else []
        if holes:
            out["holes"] = holes
        return out

    def watch(self, root: str, d: dt.date, later: bool = False) -> None:
        """From now on changed() reports session d when its tick files are no longer as they are now. A
        session already watched keeps its first stamp: what was built from the older files is still shown.
        later (the event loop, at the 18:00 roll): no directory listing here -- the next changed() takes the
        files as it finds them."""
        if (root, d) not in self._built:
            stamp = None if later else self.store.stamps(root, [d])[d]
            with self._lock:
                self._built.setdefault((root, d), stamp)

    def changed(self) -> list[tuple[str, dt.date]]:
        """Worker thread. The watched sessions whose tick files are not as they were when their bars were
        built (a fill rewrote the archive file, a live recording was merged into a new one), oldest first.
        Each is forgotten -- its memoized bars dropped, watched again from its next build -- so it is
        reported once. One directory listing per root and year; sessions over WATCH_DAYS behind the newest
        watched one are dropped unasked."""
        with self._lock:
            watched = dict(self._built)
        if not watched:
            return []
        cut = max(d for _, d in watched) - dt.timedelta(days=WATCH_DAYS)
        by_root: dict = {}
        for (root, d) in watched:
            if d >= cut:
                by_root.setdefault(root, []).append(d)
        now = {(root, d): stamp for root, dates in by_root.items()
               for d, stamp in self.store.stamps(root, dates).items()}
        moved = {k for k, stamp in now.items() if watched[k] is not None and stamp != watched[k]}
        drop = moved | {k for k in watched if k[1] < cut}
        fresh = {k: stamp for k, stamp in now.items() if watched[k] is None}     # watch(later=True): from here on
        if drop or fresh:
            with self._lock:
                for k in drop:
                    self._built.pop(k, None)
                for k, stamp in fresh.items():
                    if k in self._built and self._built[k] is None:
                        self._built[k] = stamp
                if moved:
                    for k in [k for k in self.memo if (k[0], k[2]) in moved]:
                        self._weight -= len(self.memo.pop(k)) + 1
                    self._gen += 1
        return sorted(moved)

    def clear(self) -> None:
        """Drop the memoized bars (the 18:00 roll, a refill into an older session). What is watched stays:
        the charts open now still show those sessions."""
        with self._lock:
            self.memo.clear()
            self._weight = 0
            self._gen += 1
