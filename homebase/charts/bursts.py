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
"""
from __future__ import annotations

import datetime as dt
import json
import os
from collections import deque
from pathlib import Path
from statistics import median
from typing import Optional
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
WINDOW_MS = 30_000                  # the rolling move window
LOOKBACK_MS = 60 * 60_000           # the median's trailing history
WARMUP_MS = 20 * 60_000             # no verdict before this much history exists for a root
REFRACTORY_MS = 120_000
RATIO_MIN = 4.0
TICKS_MIN = 8.0
DEFAULT_ROOTS = ("NQ", "ES", "YM", "RTY", "GC", "CL", "BTC")
REACTION_ROOTS = ("NQ", "ES", "GC", "CL", "BTC")
REACTION_MARKS = (("m10s", 10_000), ("m1m", 60_000), ("m5m", 300_000))
NEWS_LINK_MS = 3 * 60_000           # near_news(): within +/- 3 minutes


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
    else None. `tick_size` turns a price move into ticks."""

    def __init__(self, tick_size: float):
        self.tick_size = tick_size
        self._win: deque[tuple[int, float]] = deque()       # trades within the last 30 s
        # non-overlapping 30 s buckets [first_price, last_price], keyed by ts_ms // WINDOW_MS,
        # kept for LOOKBACK_MS: the history the median is drawn from
        self._buckets: dict[int, list[float]] = {}
        self._bucket_order: deque[int] = deque()
        self._first_ts: Optional[int] = None
        self._last_fire_ms: Optional[int] = None

    def push(self, ts_ms: int, price: float) -> Optional[dict]:
        if self._first_ts is None:
            self._first_ts = ts_ms
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

        if ts_ms - self._first_ts < WARMUP_MS or len(self._win) < 2:
            return None
        cur_from, cur_to = self._win[0][1], self._win[-1][1]
        move_ticks = abs(cur_to - cur_from) / self.tick_size
        if move_ticks < TICKS_MIN:
            return None
        hist = [abs(v[1] - v[0]) / self.tick_size for k, v in self._buckets.items() if k != bucket]
        if not hist:
            return None
        med = median(hist)
        if med <= 0 or move_ticks / med < RATIO_MIN:
            return None
        if self._last_fire_ms is not None and ts_ms - self._last_fire_ms < REFRACTORY_MS:
            return None
        self._last_fire_ms = ts_ms
        return {"t_ms": ts_ms, "dir": "up" if cur_to > cur_from else "down",
                "move_ticks": round(move_ticks, 3), "ratio": round(move_ticks / med, 3),
                "from_px": cur_from, "to_px": cur_to}


def near_news(burst: dict, news_items: list[dict]) -> list[dict]:
    """News items within +/- 3 minutes of the burst's t_ms, by t_ms OR
    seen_ms (a slow-to-publish item that broke close to the burst still
    counts), earliest first."""
    t = burst["t_ms"]
    out = [it for it in news_items
           if abs(it["t_ms"] - t) <= NEWS_LINK_MS or abs(it["seen_ms"] - t) <= NEWS_LINK_MS]
    out.sort(key=lambda it: it["t_ms"])
    return out


class ReactionTracker:
    """Buffers recent trades for REACTION_ROOTS and, once 5 minutes have
    passed a news item's t_ms, computes its reaction record. `tick_size_of`
    maps a root to its tick size (contracts.tick_size)."""

    def __init__(self, tick_size_of):
        self.tick_size_of = tick_size_of
        self._buf: dict[str, deque[tuple[int, float]]] = {r: deque() for r in REACTION_ROOTS}
        self._pending: list[dict] = []

    def push_tick(self, root: str, ts_ms: int, price: float) -> None:
        buf = self._buf.get(root)
        if buf is None:
            return
        buf.append((ts_ms, price))
        # only ever needed back to the oldest pending item's t_ms (+5m); a
        # generous fixed floor keeps this cheap with nothing pending
        floor = ts_ms - 7 * 60_000
        if self._pending:
            floor = min(floor, self._pending[0]["t_ms"])
        while len(buf) > 1 and buf[0][0] < floor:
            buf.popleft()

    def add_item(self, item: dict) -> None:
        self._pending.append(item)

    def due(self, now_ms: int) -> list[dict]:
        """Pop and compute every item whose +5m mark has now passed."""
        ready, keep = [], []
        for item in self._pending:
            (ready if now_ms >= item["t_ms"] + REACTION_MARKS[-1][1] else keep).append(item)
        self._pending = keep
        return [self._compute(item) for item in ready]

    def _price_at_or_before(self, root: str, ts_ms: int) -> Optional[float]:
        price = None
        for t, p in self._buf.get(root, ()):
            if t <= ts_ms:
                price = p
            else:
                break
        return price

    def _compute(self, item: dict) -> dict:
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


def _append_jsonl(path: Path, obj: dict) -> None:
    """Same atomic append as news.py: temp file with the day's prior content
    plus the new line, then rename."""
    line = json.dumps(obj)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    prior = path.read_text() if path.exists() else ""
    tmp.write_text(prior + line + "\n")
    os.replace(tmp, path)


def day_key(ts_ms: int) -> str:
    return dt.datetime.fromtimestamp(ts_ms / 1000, ET).date().isoformat()


def prune_old(folder: Path, prefix: str, now_ms: int, retention_days: int) -> None:
    """Delete `<prefix>-<date>.jsonl` files older than retention_days."""
    cutoff = dt.datetime.fromtimestamp(now_ms / 1000, ET).date() - dt.timedelta(days=retention_days)
    for p in Path(folder).glob(f"{prefix}-????-??-??.jsonl"):
        try:
            d = dt.date.fromisoformat(p.stem[len(prefix) + 1:])
        except ValueError:
            continue
        if d < cutoff:
            p.unlink(missing_ok=True)


class BurstBook:
    """Runs one BurstDetector per configured root off the live tick path,
    stores every fired burst (linked to nearby news) to
    `<folder>/bursts-<date>.jsonl`, and remembers each root's last burst for
    `/api/status`."""

    def __init__(self, folder, roots, tick_size_of, retention_days: int = 90):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.roots = tuple(roots)
        self.retention_days = retention_days
        self._detectors = {r: BurstDetector(tick_size_of(r)) for r in self.roots}
        self.last: dict[str, Optional[dict]] = {r: None for r in self.roots}

    def push(self, root: str, ts_ms: int, price: float, news_items: list[dict]) -> Optional[dict]:
        det = self._detectors.get(root)
        if det is None:
            return None
        fired = det.push(ts_ms, price)
        if fired is None:
            return None
        rec = {"root": root, **fired, "near_news": near_news(fired, news_items)}
        self.last[root] = rec
        _append_jsonl(self.folder / f"bursts-{day_key(ts_ms)}.jsonl", rec)
        prune_old(self.folder, "bursts", ts_ms, self.retention_days)
        return rec

    def status(self) -> dict:
        return {"roots": list(self.roots), "last": dict(self.last)}


class ReactionBook:
    """Wraps ReactionTracker with storage: every reaction record it computes
    is appended to `<folder>/reactions-<date>.jsonl` (dated by the news
    item's t_ms, ET). No route reads this in Part A — research reads the
    files directly."""

    def __init__(self, folder, tick_size_of, retention_days: int = 90):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self.tracker = ReactionTracker(tick_size_of)

    def push_tick(self, root: str, ts_ms: int, price: float) -> None:
        self.tracker.push_tick(root, ts_ms, price)

    def add_item(self, item: dict) -> None:
        self.tracker.add_item(item)

    def flush_due(self, now_ms: int) -> list[dict]:
        recs = self.tracker.due(now_ms)
        for rec in recs:
            _append_jsonl(self.folder / f"reactions-{day_key(rec['t_ms'])}.jsonl", rec)
        if recs:
            prune_old(self.folder, "reactions", now_ms, self.retention_days)
        return recs
