"""Burst detector + reaction log (spec `docs/superpowers/specs/2026-09-27-charts-news-design.md`,
Part A #2/#3): pure, testable cores fed one tick at a time from the live tick
path (server.py's `on_live`, the same rows `hub.on_ticks` gets), plus the
append-only storage both write to.

`BurstDetector` (one per root) tracks a rolling 30 s |last-first| move and
compares it with the median 30 s move of its trailing 60 minutes; a burst
fires at 4x the median AND at least 8 ticks, then a 120 s refractory holds
that root quiet. `near_news()` links a fired burst to nearby headlines.
`ReactionTracker` remembers every news item and, once 5 minutes have passed
its `t_ms`, measures how far NQ/ES/GC/CL/BTC moved at +10s/+1m/+5m.

Storage lives in its own `bursts/` and `reactions/` subfolders below the
news folder (never loose files beside news's own `<date>.jsonl` day files --
see news.py's docstring for why that separation matters), one file per ET
day, `<date>.jsonl` (no prefix needed once the folder says what it is).
"""
from __future__ import annotations

import bisect
import datetime as dt
import os
from collections import deque
from pathlib import Path
from statistics import median
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from . import _jsonl

ET = ZoneInfo("America/New_York")
WINDOW_MS = 30_000                  # the rolling move window
LOOKBACK_MS = 60 * 60_000           # the median's trailing history
WARMUP_MS = 20 * 60_000             # no verdict before this much LIVE (populated-bucket) history exists
WARMUP_BUCKETS = WARMUP_MS // WINDOW_MS    # 40 non-empty 30s buckets actually inside the lookback
REFRACTORY_MS = 120_000
RATIO_MIN = 4.0
TICKS_MIN = 8.0
DEFAULT_ROOTS = ("NQ", "ES", "YM", "RTY", "GC", "CL", "BTC")
REACTION_ROOTS = ("NQ", "ES", "GC", "CL", "BTC")
REACTION_MARKS = (("m10s", 10_000), ("m1m", 60_000), ("m5m", 300_000))
NEWS_LINK_MS = 3 * 60_000           # near_news(): within +/- 3 minutes
RECENT_KEEP_MS = NEWS_LINK_MS       # how long a fired burst stays eligible for a late-arriving headline


def configured_roots(env: Optional[str] = None) -> tuple[str, ...]:
    """HOMEBASE_BURST_ROOTS (comma list) or DEFAULT_ROOTS."""
    raw = env if env is not None else os.environ.get("HOMEBASE_BURST_ROOTS")
    if not raw:
        return DEFAULT_ROOTS
    roots = tuple(r.strip().upper() for r in raw.split(",") if r.strip())
    return roots or DEFAULT_ROOTS


class BurstDetector:
    """One root's rolling-window burst rule. Feed it trades in time order via
    `push(ts_ms, price)`; it returns a burst record the instant one fires,
    else None. `tick_size` turns a price move into ticks.

    Warm-up (review fix): a verdict needs at least WARMUP_BUCKETS (40) non-
    empty 30 s buckets actually inside the trailing 60-minute lookback --
    not just "some time has passed since the very first tick ever seen".
    A halt (the 17:00-18:00 maintenance break, a feed drop) empties most or
    all of those buckets, so the root re-earns its warm-up after a gap,
    exactly like a brand-new root would.

    `ratio_now()` (Task 2, the burst radar): the same move_ticks/median this
    root would be judged on right now, cached from the last `push()` --
    unlike a fired burst, it is not gated by TICKS_MIN, RATIO_MIN or the
    refractory window, so the radar can show a calm 0.6x as well as a firing
    6x. None before warm-up (or with fewer than 2 ticks in the live window),
    same as a verdict would be."""

    def __init__(self, tick_size: float):
        self.tick_size = tick_size
        self._win: deque[tuple[int, float]] = deque()       # trades within the last 30 s
        # non-overlapping 30 s buckets [first_price, last_price], keyed by ts_ms // WINDOW_MS,
        # kept for LOOKBACK_MS: the history the median (and the warm-up count) is drawn from
        self._buckets: dict[int, list[float]] = {}
        self._bucket_order: deque[int] = deque()
        self._last_fire_ms: Optional[int] = None
        self._last_ratio: Optional[float] = None

    def push(self, ts_ms: int, price: float) -> Optional[dict]:
        self._win.append((ts_ms, price))
        while self._win and self._win[0][0] <= ts_ms - WINDOW_MS:
            self._win.popleft()
        bucket = ts_ms // WINDOW_MS
        b = self._buckets.get(bucket)
        if b is None:
            self._buckets[bucket] = [price, price]
            self._bucket_order.append(bucket)
        else:
            b[1] = price
        cutoff = (ts_ms - LOOKBACK_MS) // WINDOW_MS
        while self._bucket_order and self._bucket_order[0] < cutoff:
            self._buckets.pop(self._bucket_order.popleft(), None)

        hist = [abs(v[1] - v[0]) / self.tick_size for k, v in self._buckets.items() if k != bucket]
        if len(hist) < WARMUP_BUCKETS or len(self._win) < 2:
            self._last_ratio = None
            return None                                     # not enough LIVE history in the lookback yet
        cur_from, cur_to = self._win[0][1], self._win[-1][1]
        move_ticks = abs(cur_to - cur_from) / self.tick_size
        med = median(hist)
        self._last_ratio = round(move_ticks / med, 3) if med > 0 else None
        if move_ticks < TICKS_MIN:
            return None
        if med <= 0 or move_ticks / med < RATIO_MIN:
            return None
        if self._last_fire_ms is not None and ts_ms - self._last_fire_ms < REFRACTORY_MS:
            return None
        self._last_fire_ms = ts_ms
        return {"t_ms": ts_ms, "dir": "up" if cur_to > cur_from else "down",
                "move_ticks": round(move_ticks, 3), "ratio": round(move_ticks / med, 3),
                "from_px": cur_from, "to_px": cur_to}

    def ratio_now(self) -> Optional[float]:
        return self._last_ratio


def _near(a_ms: int, item: dict) -> bool:
    """Is `item` within +/- NEWS_LINK_MS of a_ms, by t_ms OR seen_ms?"""
    return abs(item["t_ms"] - a_ms) <= NEWS_LINK_MS or abs(item["seen_ms"] - a_ms) <= NEWS_LINK_MS


def near_news(burst: dict, news_items: list[dict]) -> list[dict]:
    """News items within +/- 3 minutes of the burst's t_ms, by t_ms OR
    seen_ms (a slow-to-publish item that broke close to the burst still
    counts), earliest first."""
    out = [it for it in news_items if _near(burst["t_ms"], it)]
    out.sort(key=lambda it: it["t_ms"])
    return out


class ReactionTracker:
    """Buffers recent trades for REACTION_ROOTS and, once 5 minutes have
    passed a news item's t_ms, computes its reaction record. `tick_size_of`
    maps a root to its tick size (contracts.tick_size). Price lookups use
    bisect over an append-only per-root list (O(log n), not a linear scan)."""

    def __init__(self, tick_size_of):
        self.tick_size_of = tick_size_of
        self._buf: dict[str, list[tuple[int, float]]] = {r: [] for r in REACTION_ROOTS}
        self._pending: list[dict] = []

    def push_tick(self, root: str, ts_ms: int, price: float) -> None:
        buf = self._buf.get(root)
        if buf is None:
            return
        buf.append((ts_ms, price))
        # only ever needed back to the oldest pending item's t_ms; a generous
        # fixed floor keeps this cheap with nothing pending
        floor = ts_ms - 7 * 60_000
        if self._pending:
            floor = min(floor, self._pending[0]["t_ms"])
        cut = bisect.bisect_left(buf, floor, key=lambda tp: tp[0])
        if cut > 1:                    # keep one stale entry as the carry-forward baseline
            del buf[:cut - 1]

    def add_item(self, item: dict) -> None:
        self._pending.append(item)

    def due_items(self, now_ms: int) -> list[dict]:
        """News items whose +5m mark has passed -- NOT removed yet (the
        caller removes one only once it's safely durable; see ReactionBook)."""
        return [it for it in self._pending if now_ms >= it["t_ms"] + REACTION_MARKS[-1][1]]

    def discard(self, item: dict) -> None:
        self._pending = [it for it in self._pending if it["id"] != item["id"]]

    def due(self, now_ms: int) -> list[dict]:
        """Compute-and-remove every item whose +5m mark has passed (for
        direct, storage-free testing of the math; ReactionBook uses
        due_items()/compute()/discard() instead so a failed write can't
        lose an item)."""
        out = []
        for item in self.due_items(now_ms):
            out.append(self.compute(item))
            self.discard(item)
        return out

    def _price_at_or_before(self, root: str, ts_ms: int) -> Optional[float]:
        buf = self._buf.get(root) or []
        i = bisect.bisect_right(buf, ts_ms, key=lambda tp: tp[0]) - 1
        return buf[i][1] if i >= 0 else None

    def compute(self, item: dict) -> dict:
        roots = {}
        for root in REACTION_ROOTS:
            base = self._price_at_or_before(root, item["t_ms"])
            if base is None:
                roots[root] = {label: None for label, _ in REACTION_MARKS}
                continue
            ts = self.tick_size_of(root)
            marks = {}
            for label, delta_ms in REACTION_MARKS:
                p = self._price_at_or_before(root, item["t_ms"] + delta_ms)
                if p is None:
                    marks[label] = None
                else:
                    pts = p - base
                    marks[label] = {"pts": round(pts, 5), "ticks": round(pts / ts, 3) if ts else None}
            roots[root] = marks
        return {"id": item["id"], "source": item["source"], "title": item["title"], "tags": item["tags"],
                "t_ms": item["t_ms"], "seen_ms": item["seen_ms"],
                "delay_s": round((item["seen_ms"] - item["t_ms"]) / 1000, 3), "roots": roots}


def day_key(ts_ms: int) -> str:
    return dt.datetime.fromtimestamp(ts_ms / 1000, ET).date().isoformat()


def prune_old(folder: Path, now_ms: int, retention_days: int) -> None:
    """Delete `<date>.jsonl` files older than retention_days."""
    cutoff = dt.datetime.fromtimestamp(now_ms / 1000, ET).date() - dt.timedelta(days=retention_days)
    for p in Path(folder).glob("????-??-??.jsonl"):
        try:
            d = dt.date.fromisoformat(p.stem)
        except ValueError:
            continue
        if d < cutoff:
            p.unlink(missing_ok=True)


class BurstBook:
    """Runs one BurstDetector per configured root off the live tick path,
    stores every fired burst (linked to nearby news) to
    `<folder>/bursts/<date>.jsonl`, and remembers each root's last burst for
    `/api/status`. `news_near(t_ms, window_ms)` (News.near, a bisect lookup)
    is called only on the rare tick that actually fires a burst -- never on
    every tick."""

    def __init__(self, folder, roots, tick_size_of, news_near: Callable[[int, int], list[dict]],
                retention_days: int = 90):
        self.folder = Path(folder) / "bursts"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.roots = tuple(roots)
        self.news_near = news_near
        self.retention_days = retention_days
        self._detectors = {r: BurstDetector(tick_size_of(r)) for r in self.roots}
        self.last: dict[str, Optional[dict]] = {r: None for r in self.roots}
        self._recent: list[dict] = []   # bursts still eligible for a late-arriving headline (link_news())

    def _path_for(self, t_ms: int) -> Path:
        return self.folder / f"{day_key(t_ms)}.jsonl"

    def push(self, root: str, ts_ms: int, price: float) -> Optional[dict]:
        det = self._detectors.get(root)
        if det is None:
            return None
        fired = det.push(ts_ms, price)
        if fired is None:
            return None
        near = self.news_near(fired["t_ms"], NEWS_LINK_MS)
        rec = {"root": root, **fired, "near_news": near_news(fired, near)}
        self.last[root] = rec
        _jsonl.append(self._path_for(rec["t_ms"]), rec)
        prune_old(self.folder, ts_ms, self.retention_days)
        self._recent.append(rec)
        self._prune_recent(ts_ms)
        return rec

    def _prune_recent(self, ref_ms: int) -> None:
        cutoff = ref_ms - RECENT_KEEP_MS
        self._recent = [r for r in self._recent if r["t_ms"] >= cutoff]

    def link_news(self, item: dict) -> list[dict]:
        """A news item just arrived (review #4): attach it to any
        already-fired, still-recent burst within +/- 3 minutes, update that
        burst's stored `near_news`, and return the updated records (the
        caller fans each as a `burst_update`)."""
        self._prune_recent(item["t_ms"])
        updated = []
        for rec in self._recent:
            if not _near(rec["t_ms"], item):
                continue
            if any(n["id"] == item["id"] for n in rec["near_news"]):
                continue
            rec["near_news"] = sorted(rec["near_news"] + [item], key=lambda it: it["t_ms"])
            self._rewrite(rec)
            updated.append(rec)
        return updated

    def _rewrite(self, rec: dict) -> None:
        path = self._path_for(rec["t_ms"])
        lines = _jsonl.read_all(path)
        for i, line in enumerate(lines):
            if line.get("root") == rec["root"] and line.get("t_ms") == rec["t_ms"]:
                lines[i] = rec
                break
        else:
            lines.append(rec)          # shouldn't happen (the burst was just written), but never silently drop it
        _jsonl.write_all(path, lines)

    def now(self) -> dict[str, Optional[float]]:
        """Every configured root's CURRENT ratio (Task 2, the burst radar strip): the same
        move_ticks/median a fired burst is judged on, live and un-gated (so a quiet 0.6x shows
        too, not just a firing 4x+), or None before that root has warmed up. Cheap: each
        detector's ratio is cached from its own last `push()`, nothing is recomputed here."""
        return {r: d.ratio_now() for r, d in self._detectors.items()}

    def status(self) -> dict:
        return {"roots": list(self.roots), "last": dict(self.last), "now": self.now()}


class ReactionBook:
    """Wraps ReactionTracker with storage: every reaction record it computes
    is appended to `<folder>/reactions/<date>.jsonl` (dated by the news
    item's t_ms, ET). No route reads this in Part A — research reads the
    files directly. A news item is only removed from the pending queue
    (`ReactionTracker.discard`) once its write has actually succeeded, so a
    transient disk failure retries next time rather than losing the item."""

    def __init__(self, folder, tick_size_of, retention_days: int = 90):
        self.folder = Path(folder) / "reactions"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self.tracker = ReactionTracker(tick_size_of)

    def push_tick(self, root: str, ts_ms: int, price: float) -> None:
        self.tracker.push_tick(root, ts_ms, price)

    def add_item(self, item: dict) -> None:
        self.tracker.add_item(item)

    def flush_due(self, now_ms: int) -> list[dict]:
        done = []
        for item in self.tracker.due_items(now_ms):
            rec = self.tracker.compute(item)
            _jsonl.append(self.folder / f"{day_key(rec['t_ms'])}.jsonl", rec)   # raises -> item stays pending
            self.tracker.discard(item)
            done.append(rec)
        if done:
            prune_old(self.folder, now_ms, self.retention_days)
        return done
