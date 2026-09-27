"""Live news feed (spec `docs/superpowers/specs/2026-09-27-charts-news-design.md`, Part A #1):
FinancialJuice RSS + Trump's Truth Social RSS (trumpstruth.org), polled on a
floor, tagged by keyword, kept per ET calendar day, served by time range.

Same shape as calendar.py: the fetch function is injected (tests never touch
the network), a floor keeps polling polite even across a restart, and a bad
or oversized response is a failure that keeps what we already had. A day
file is appended to in O(1) (`_jsonl.append`: open in append mode, write one
line, flush -- never a whole-file rewrite); `state.json` (the per-source
poll floor) is small and rewritten atomically instead (temp + rename).
`poll()`'s network + disk I/O run in a worker thread (server.py's
`asyncio.to_thread`); `self._lock` is held only for the brief in-memory
bookkeeping around that I/O, so a page's GET (`items()`/`near()`/`status()`,
also on `self._lock`) can never be stalled by a slow disk or network call.
"""
from __future__ import annotations

import bisect
import datetime as dt
import hashlib
import re
import ssl
import statistics
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET_tree
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from . import _jsonl

ET = ZoneInfo("America/New_York")
POLL_S = 60             # never faster: be a polite client
TIMEOUT_S = 10
MAX_RESPONSE_BYTES = 2_000_000
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/128.0 Safari/537.36")
RETENTION_DAYS = 90
QUERY_MAX = 500
DAY_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.jsonl$")     # anchored: a sibling bursts-/reactions- file never matches


@dataclass(frozen=True)
class Source:
    name: str
    url: str


FINANCIALJUICE = Source("financialjuice", "https://www.financialjuice.com/feed.ashx?xy=rss")
TRUMPSTRUTH = Source("truth", "https://trumpstruth.org/feed")
SOURCES = (FINANCIALJUICE, TRUMPSTRUTH)

# keyword -> tag, longest-match-first isn't needed: every hit just adds its tag
TAGS: dict[str, tuple[str, ...]] = {
    "war": ("war", "strike", "missile", "attack", "military", "troops", "ceasefire", "nuclear"),
    "tariff": ("tariff", "trade deal", "duties", "sanctions"),
    "fed": ("fed", "powell", "fomc", "rate cut", "rate hike", "interest rate"),
    "china": ("china",),
    "iran": ("iran",),
    "russia": ("russia",),
    "oil": ("oil", "opec", "crude"),
    "data": ("cpi", "nfp", "payrolls", "gdp", "pce", "jobless"),
    "breaking": ("breaking", "urgent", "flash"),
}


def http_get(url: str) -> bytes:
    """One GET as a browser sends it, 10 s timeout, at most MAX_RESPONSE_BYTES
    (a feed answering with more is a failure, not a giant buffer in memory)."""
    import certifi   # noqa: PLC0415 — only the live service ever fetches

    ctx = ssl.create_default_context(cafile=certifi.where())
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, */*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S, context=ctx) as r:
        data = r.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError(f"response over {MAX_RESPONSE_BYTES} bytes")
    return data


def _text(el: Optional[ET_tree.Element]) -> str:
    return (el.text or "").strip() if el is not None else ""


def _local(tag: str) -> str:
    """An element's tag without its XML namespace (Atom feeds are namespaced)."""
    return tag.rpartition("}")[2]


def _parsed_date_ms(text: str) -> Optional[int]:
    """RFC-822 (`pubDate`) or ISO-8601 (`updated`/`published`) -> epoch ms, or
    None for anything unparseable (an item with no usable date is skipped)."""
    text = text.strip()
    if not text:
        return None
    for parser in (parsedate_to_datetime, dt.datetime.fromisoformat):
        try:
            when = parser(text)
        except (ValueError, TypeError, IndexError):
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=dt.timezone.utc)
        return int(when.timestamp() * 1000)
    return None


def parse_rss(raw: bytes) -> list[dict]:
    """An RSS 2.0 (`<item>`) or Atom (`<entry>`) feed -> [{title, url, guid,
    t_ms}], oldest field missing or unparseable date -> the item is skipped
    (never the whole feed). ValueError on XML that doesn't parse at all."""
    try:
        root = ET_tree.fromstring(raw)
    except ET_tree.ParseError as e:
        raise ValueError(f"bad XML: {e}") from None
    out = []
    for entry in root.iter():
        if _local(entry.tag) not in ("item", "entry"):
            continue
        by_local = {_local(c.tag): c for c in entry}
        title = _text(by_local.get("title"))
        link_el = by_local.get("link")
        link = _text(link_el) or (link_el.get("href") if link_el is not None else "") or ""
        guid = _text(by_local.get("guid")) or _text(by_local.get("id")) or link
        date_text = _text(by_local.get("pubDate")) or _text(by_local.get("published")) or _text(by_local.get("updated"))
        t_ms = _parsed_date_ms(date_text)
        if not title or not guid or t_ms is None:
            continue
        out.append({"title": title, "url": link, "guid": guid, "t_ms": t_ms})
    return out


def tag(source: str, title: str) -> list[str]:
    """Case-insensitive keyword groups -> the tags a headline gets. Every
    Truth Social post is tagged `trump` regardless of its title; any source's
    title containing "trump" gets it too."""
    low = title.lower()
    tags = [name for name, words in TAGS.items() if any(w in low for w in words)]
    if source == TRUMPSTRUTH.name or "trump" in low:
        tags.append("trump")
    # stable, de-duplicated order (dict.fromkeys keeps first occurrence)
    return list(dict.fromkeys(tags))


def _id(source: str, guid_or_link: str, title: str) -> str:
    return hashlib.sha256(f"{source}|{guid_or_link}|{title}".encode()).hexdigest()[:24]


def _day_key(seen_ms: int) -> str:
    return dt.datetime.fromtimestamp(seen_ms / 1000, ET).date().isoformat()


class News:
    """Polls SOURCES on their floor, tags + dedups + stores each new item,
    and serves them back by time range. `fetch` is injected (None: never
    fetches, matching Calendar and "no fetch in replay"). Items for the
    trailing `retention_days` are kept in memory (they're small); older day
    files are deleted.

    Bursts and reactions are NOT stored in this folder (they live in their
    own `bursts/`/`reactions/` subfolders, owned by bursts.py) -- `_load()`'s
    glob is non-recursive and DAY_FILE is fully anchored, so even a stray
    misnamed file directly in this folder can't be read back as a headline.
    """

    def __init__(self, folder, fetch: Optional[Callable[[str], bytes]] = None, now=time.time,
                 sources=SOURCES, retention_days: int = RETENTION_DAYS):
        self.folder = Path(folder)
        self.fetch = fetch
        self.now = now
        self.sources = sources
        self.retention_days = retention_days
        self.folder.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()          # poll() runs off-thread (asyncio.to_thread); routes read live
        self._last_try: dict[str, float] = {s.name: 0.0 for s in sources}
        self.last_fetch: dict[str, dict] = {s.name: {"at": None, "items": 0, "error": None} for s in sources}
        self._by_day: dict[str, list[dict]] = {}
        self._seen: set[str] = set()
        self._by_t: list[dict] = []            # sorted by t_ms, for near()'s bisect
        self._by_seen: list[dict] = []         # sorted by seen_ms, for near()'s bisect
        self._load()

    # -- persistence -----------------------------------------------------

    def _state_path(self) -> Path:
        return self.folder / "state.json"

    def _load_state(self) -> None:
        st = _jsonl.read_json(self._state_path())
        for name, ts in (st.get("last_try") or {}).items():
            if name in self._last_try:
                try:
                    self._last_try[name] = float(ts)
                except (TypeError, ValueError):
                    pass

    def _save_state(self, last_try: dict) -> None:
        """Write state.json from a caller-supplied snapshot. Pure disk I/O,
        touches no shared state -- callers run this OUTSIDE self._lock."""
        _jsonl.write_json(self._state_path(), {"last_try": last_try})

    def _load(self) -> None:
        """Runs once, single-threaded, in __init__ (before any other thread
        can hold a reference to self) -- safe to mix disk I/O with the
        in-memory build here, unlike poll()'s ongoing prune below."""
        self._load_state()
        cutoff = dt.datetime.fromtimestamp(self.now(), ET).date() - dt.timedelta(days=self.retention_days)
        for p in list(self.folder.glob("*.jsonl")):
            m = DAY_FILE.match(p.name)
            if m and dt.date.fromisoformat(m.group(1)) < cutoff:
                p.unlink(missing_ok=True)
        for p in sorted(self.folder.glob("*.jsonl")):
            m = DAY_FILE.match(p.name)
            if not m:
                continue
            items = _jsonl.read_all(p)
            self._by_day[m.group(1)] = items
            for it in items:
                if "id" not in it:
                    continue
                self._seen.add(it["id"])
                bisect.insort(self._by_t, it, key=lambda r: r["t_ms"])
                bisect.insort(self._by_seen, it, key=lambda r: r["seen_ms"])

    def _prune_memory(self) -> list[str]:
        """Drop day keys older than retention_days from the in-memory
        structures only, and return them -- the caller deletes their files
        AFTER releasing self._lock (see poll()). Caller holds self._lock."""
        cutoff = dt.datetime.fromtimestamp(self.now(), ET).date() - dt.timedelta(days=self.retention_days)
        dropped = [k for k in self._by_day if dt.date.fromisoformat(k) < cutoff]
        if not dropped:
            return []
        for k in dropped:
            del self._by_day[k]
        keep_ids = {it["id"] for items in self._by_day.values() for it in items}
        self._by_t = [r for r in self._by_t if r["id"] in keep_ids]
        self._by_seen = [r for r in self._by_seen if r["id"] in keep_ids]
        return dropped

    def _delete_days(self, days: list[str]) -> None:
        """Pure disk I/O (file deletion), no shared state -- run OUTSIDE
        self._lock."""
        for day in days:
            (self.folder / f"{day}.jsonl").unlink(missing_ok=True)

    # -- polling -----------------------------------------------------------

    def wait_s(self, source: str) -> float:
        """Seconds until `source` may be polled again."""
        with self._lock:
            return max(0.0, self._last_try.get(source, 0.0) + POLL_S - self.now())

    def poll(self) -> list[dict]:
        """One pass: every source past its 60 s floor is fetched once. Returns
        the newly stored items (already deduped, tagged, and on disk), oldest
        first. Without a fetch function nothing is ever fetched (replay).
        Meant to run in a worker thread (it blocks on network + disk I/O).

        Lock discipline (review fix round 2): `self._lock` is held ONLY for
        the fast in-memory bookkeeping -- reading/updating `_last_try`,
        `last_fetch`, `_seen`, `_by_day`, `_by_t`, `_by_seen`. Every disk
        write (state.json, a day file's append, an old day file's delete)
        happens AFTER the lock is released, using a snapshot/list captured
        while it was held. `items()`/`near()`/`status()` only ever need the
        same short lock, so a slow disk (or a monkeypatched slow one in
        tests) can never stall them."""
        if self.fetch is None:
            return []
        new = []
        now = self.now()
        for src in self.sources:
            with self._lock:
                if now - self._last_try[src.name] < POLL_S:
                    continue
                self._last_try[src.name] = now
                last_try_snapshot = dict(self._last_try)
            self._save_state(last_try_snapshot)                  # disk I/O: outside the lock
            try:
                items = parse_rss(self.fetch(src.url))          # network I/O: outside the lock
            except Exception as e:  # noqa: BLE001 — one source's failure never stops the others
                with self._lock:
                    self.last_fetch[src.name] = {**self.last_fetch[src.name],
                                                 "error": f"{type(e).__name__}: {e}"[:200]}
                continue
            to_write: list[tuple[str, dict]] = []
            with self._lock:
                self.last_fetch[src.name] = {"at": int(now * 1000), "items": len(items), "error": None}
                for raw_item in items:
                    rec_id = _id(src.name, raw_item["guid"], raw_item["title"])
                    if rec_id in self._seen:
                        continue
                    seen_ms = int(now * 1000)
                    # a bad feed's future-dated pubDate must never outrun when we actually saw it
                    # (it would break the reaction tracker's "+5m after t_ms" scheduling)
                    t_ms = min(raw_item["t_ms"], seen_ms)
                    rec = {"id": rec_id, "source": src.name, "t_ms": t_ms, "seen_ms": seen_ms,
                           "title": raw_item["title"], "url": raw_item["url"],
                           "tags": tag(src.name, raw_item["title"])}
                    self._seen.add(rec_id)
                    day = _day_key(seen_ms)
                    self._by_day.setdefault(day, []).append(rec)
                    bisect.insort(self._by_t, rec, key=lambda r: r["t_ms"])
                    bisect.insort(self._by_seen, rec, key=lambda r: r["seen_ms"])
                    new.append(rec)
                    to_write.append((day, rec))
            for day, rec in to_write:                             # disk I/O: outside the lock
                _jsonl.append(self.folder / f"{day}.jsonl", rec)
        if new:
            with self._lock:
                dropped_days = self._prune_memory()
            self._delete_days(dropped_days)                        # disk I/O: outside the lock
        return new

    # -- reads ---------------------------------------------------------

    def items(self, frm: int, to: int, tags: Optional[list[str]] = None,
              sources: Optional[list[str]] = None) -> list[dict]:
        """Stored items with frm <= t_ms < to, newest first, capped at
        QUERY_MAX. `tags`/`sources` (any case) keep only a matching item."""
        want_tags = {t.lower() for t in tags} if tags else None
        want_src = {s.lower() for s in sources} if sources else None
        with self._lock:
            lo = bisect.bisect_left(self._by_t, frm, key=lambda r: r["t_ms"])
            hi = bisect.bisect_left(self._by_t, to, key=lambda r: r["t_ms"])
            candidates = list(self._by_t[lo:hi])
        out = []
        for it in candidates:
            if want_src is not None and it["source"].lower() not in want_src:
                continue
            if want_tags is not None and not (want_tags & {t.lower() for t in it["tags"]}):
                continue
            out.append(it)
        out.sort(key=lambda it: it["t_ms"], reverse=True)
        return out[:QUERY_MAX]

    def near(self, t_ms: int, window_ms: int) -> list[dict]:
        """Items within +/- window_ms of t_ms, by t_ms OR seen_ms, via two
        sorted indices + bisect (never a scan of everything kept). Used by
        the burst detector's near_news() -- which itself re-checks both
        fields, so a slightly generous union here is fine."""
        with self._lock:
            lo1 = bisect.bisect_left(self._by_t, t_ms - window_ms, key=lambda r: r["t_ms"])
            hi1 = bisect.bisect_right(self._by_t, t_ms + window_ms, key=lambda r: r["t_ms"])
            lo2 = bisect.bisect_left(self._by_seen, t_ms - window_ms, key=lambda r: r["seen_ms"])
            hi2 = bisect.bisect_right(self._by_seen, t_ms + window_ms, key=lambda r: r["seen_ms"])
            a, b = self._by_t[lo1:hi1], self._by_seen[lo2:hi2]
        seen_ids: set[str] = set()
        out = []
        for r in a + b:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                out.append(r)
        return out

    def delay_p50_s(self) -> Optional[float]:
        """Median seen_ms - t_ms across everything kept, in seconds."""
        with self._lock:
            delays = [(it["seen_ms"] - it["t_ms"]) / 1000 for it in self._by_t]
        return statistics.median(delays) if delays else None

    def status(self) -> dict:
        with self._lock:
            last_fetch = {k: dict(v) for k, v in self.last_fetch.items()}
        return {"ok": any(v["error"] is None and v["at"] is not None for v in last_fetch.values()),
                "last_fetch": last_fetch, "delay_p50_s": self.delay_p50_s()}
