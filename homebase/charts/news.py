"""Live news feed (spec `docs/superpowers/specs/2026-09-27-charts-news-design.md`, Part A #1):
FinancialJuice RSS + Trump's Truth Social RSS (trumpstruth.org), polled on a
floor, tagged by keyword, kept per ET calendar day, served by time range.

Same shape as calendar.py: the fetch function is injected (tests never touch
the network), a floor keeps polling polite even across a restart, a bad or
oversized response is a failure that keeps what we already had, and storage
is a plain file written atomically (temp + rename) so a crash mid-write can
never tear it.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import ssl
import statistics
import time
import urllib.request
import xml.etree.ElementTree as ET_tree
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
POLL_S = 60             # never faster: be a polite client
TIMEOUT_S = 10
MAX_RESPONSE_BYTES = 2_000_000
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/128.0 Safari/537.36")
RETENTION_DAYS = 90
QUERY_MAX = 500
DAY_FILE = re.compile(r"(\d{4}-\d{2}-\d{2})\.jsonl$")


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


def _append_jsonl(path: Path, obj: dict) -> None:
    """Append one JSON line, atomically (temp file with the whole day's
    content + the new line, then rename): a torn write can never leave a
    line half-written for the next reader."""
    line = json.dumps(obj)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    prior = path.read_text() if path.exists() else ""
    tmp.write_text(prior + line + "\n")
    os.replace(tmp, path)


def _read_jsonl(path: Path) -> list[dict]:
    out = []
    try:
        text = path.read_text()
    except OSError:
        return out
    for line in text.splitlines():
        try:
            v = json.loads(line)
        except ValueError:
            continue
        if isinstance(v, dict):
            out.append(v)
    return out


class News:
    """Polls SOURCES on their floor, tags + dedups + stores each new item,
    and serves them back by time range. `fetch` is injected (None: never
    fetches, matching Calendar and "no fetch in replay"). Items for the
    trailing `retention_days` are kept in memory (they're small); older day
    files are deleted."""

    def __init__(self, folder, fetch: Optional[Callable[[str], bytes]] = None, now=time.time,
                 sources=SOURCES, retention_days: int = RETENTION_DAYS):
        self.folder = Path(folder)
        self.fetch = fetch
        self.now = now
        self.sources = sources
        self.retention_days = retention_days
        self.folder.mkdir(parents=True, exist_ok=True)
        self._last_try: dict[str, float] = {s.name: 0.0 for s in sources}
        self.last_fetch: dict[str, dict] = {s.name: {"at": None, "items": 0, "error": None} for s in sources}
        self._by_day: dict[str, list[dict]] = {}
        self._seen: set[str] = set()
        self._load()

    def _load(self) -> None:
        self._prune(write=False)
        for p in sorted(self.folder.glob("*.jsonl")):
            m = DAY_FILE.search(p.name)
            if not m:
                continue
            items = _read_jsonl(p)
            self._by_day[m.group(1)] = items
            self._seen.update(it["id"] for it in items if "id" in it)

    def _prune(self, write: bool = True) -> None:
        """Delete day files (and drop them from memory) older than
        retention_days, judged against `now()`."""
        cutoff = dt.datetime.fromtimestamp(self.now(), ET).date() - dt.timedelta(days=self.retention_days)
        for p in list(self.folder.glob("*.jsonl")):
            m = DAY_FILE.search(p.name)
            if m and dt.date.fromisoformat(m.group(1)) < cutoff:
                p.unlink(missing_ok=True)
                self._by_day.pop(m.group(1), None)
        if write:
            self._by_day = {k: v for k, v in self._by_day.items() if dt.date.fromisoformat(k) >= cutoff}

    def wait_s(self, source: str) -> float:
        """Seconds until `source` may be polled again."""
        return max(0.0, self._last_try.get(source, 0.0) + POLL_S - self.now())

    def poll(self) -> list[dict]:
        """One pass: every source past its 60 s floor is fetched once. Returns
        the newly stored items (already deduped, tagged, and on disk), oldest
        first. Without a fetch function nothing is ever fetched (replay)."""
        if self.fetch is None:
            return []
        new = []
        now = self.now()
        for src in self.sources:
            if now - self._last_try[src.name] < POLL_S:
                continue
            self._last_try[src.name] = now
            try:
                items = parse_rss(self.fetch(src.url))
            except Exception as e:  # noqa: BLE001 — one source's failure never stops the others
                self.last_fetch[src.name] = {**self.last_fetch[src.name],
                                             "error": f"{type(e).__name__}: {e}"[:200]}
                continue
            self.last_fetch[src.name] = {"at": int(now * 1000), "items": len(items), "error": None}
            for raw_item in items:
                rec_id = _id(src.name, raw_item["guid"], raw_item["title"])
                if rec_id in self._seen:
                    continue
                rec = {"id": rec_id, "source": src.name, "t_ms": raw_item["t_ms"], "seen_ms": int(now * 1000),
                       "title": raw_item["title"], "url": raw_item["url"], "tags": tag(src.name, raw_item["title"])}
                self._seen.add(rec_id)
                day = _day_key(rec["seen_ms"])
                self._by_day.setdefault(day, []).append(rec)
                _append_jsonl(self.folder / f"{day}.jsonl", rec)
                new.append(rec)
        if new:
            self._prune()
        return new

    def items(self, frm: int, to: int, tags: Optional[list[str]] = None,
              sources: Optional[list[str]] = None) -> list[dict]:
        """Stored items with frm <= t_ms < to, newest first, capped at
        QUERY_MAX. `tags`/`sources` (any case) keep only a matching item."""
        want_tags = {t.lower() for t in tags} if tags else None
        want_src = {s.lower() for s in sources} if sources else None
        out = []
        for day_items in self._by_day.values():
            for it in day_items:
                if not frm <= it["t_ms"] < to:
                    continue
                if want_src is not None and it["source"].lower() not in want_src:
                    continue
                if want_tags is not None and not (want_tags & {t.lower() for t in it["tags"]}):
                    continue
                out.append(it)
        out.sort(key=lambda it: it["t_ms"], reverse=True)
        return out[:QUERY_MAX]

    def delay_p50_s(self) -> Optional[float]:
        """Median seen_ms - t_ms across everything kept, in seconds."""
        delays = [(it["seen_ms"] - it["t_ms"]) / 1000 for items in self._by_day.values() for it in items]
        return statistics.median(delays) if delays else None

    def status(self) -> dict:
        return {"ok": any(v["error"] is None and v["at"] is not None for v in self.last_fetch.values()),
                "last_fetch": dict(self.last_fetch), "delay_p50_s": self.delay_p50_s()}
