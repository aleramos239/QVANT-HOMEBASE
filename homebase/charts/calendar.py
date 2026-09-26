"""The economic calendar on the charts (spec §6): ForexFactory's weekly feed,
fetched on a timer, kept per week on disk so past weeks accumulate, served
to the page by time range and countries.

Source: FF_URL, the CURRENT week only (Sunday to Saturday, ET); fields title,
country, date (ISO with its ET offset), impact (High | Medium | Low | Holiday
| Non-Economic), forecast, previous. ForexFactory blocks aggressive polling:
at most one request per 30 minutes (the floor survives restarts: the last
try is on disk), otherwise a fetch an hour, with a browser User-Agent and a
10 s timeout. A failed fetch keeps the last good data and says why in
/api/status. The fetch function is injected (tests pass their own); without
one nothing is ever fetched.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import ssl
import time
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
EVERY_S = 3600          # a good fetch is refreshed an hour later
MIN_GAP_S = 1800        # never two requests within 30 minutes (a failed one is retried at this floor)
TIMEOUT_S = 10
MAX_RESPONSE_BYTES = 2_000_000   # a feed answering with more than this is treated as a failure, never buffered whole
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/128.0 Safari/537.36")
IMPACTS = ("High", "Medium", "Low", "Holiday", "Non-Economic")
ET = ZoneInfo("America/New_York")
WEEK_FILES = "????-??-??.json"


def http_get(url: str) -> bytes:
    """One GET as a browser sends it, 10 s timeout. certifi's CA bundle: a python.org build ships none. Reads at
    most MAX_RESPONSE_BYTES: a feed answering with more (never expected from ForexFactory's own weekly JSON) is a
    failure, not a giant buffer kept in memory."""
    import certifi   # noqa: PLC0415 — declared in requirements.txt; only the live service ever fetches

    ctx = ssl.create_default_context(cafile=certifi.where())
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S, context=ctx) as r:
        data = r.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError(f"response over {MAX_RESPONSE_BYTES} bytes")
    return data


def _text(v) -> str:
    return "" if v is None else str(v).strip()


def parse(raw) -> list[dict]:
    """The feed's events as [{t_ms, title, country, impact, forecast, previous}], by time (the feed's order
    within one time). An item without a title, an ISO date with an offset or a known impact is skipped, never
    the whole week. Country codes are upper-case ("All" -> "ALL"). ValueError when the feed is not a list."""
    if not isinstance(raw, list):
        raise ValueError("the feed is not a list of events")
    out = []
    for ev in raw:
        if not isinstance(ev, dict):
            continue
        title, impact = _text(ev.get("title")), _text(ev.get("impact"))
        try:
            when = dt.datetime.fromisoformat(_text(ev.get("date")))
        except ValueError:
            continue
        if not title or impact not in IMPACTS or when.tzinfo is None:
            continue
        out.append({"t_ms": int(when.timestamp() * 1000), "title": title, "country": _text(ev.get("country")).upper(),
                    "impact": impact, "forecast": _text(ev.get("forecast")), "previous": _text(ev.get("previous"))})
    out.sort(key=lambda e: e["t_ms"])
    return out


def week_start(t_ms: int) -> dt.date:
    """The ForexFactory week (Sunday to Saturday, ET) an instant falls in, named by its Sunday."""
    d = dt.datetime.fromtimestamp(t_ms / 1000, ET).date()
    return d - dt.timedelta(days=(d.weekday() + 1) % 7)


def _write_json(path: Path, data) -> None:
    """Via a temp file + atomic rename: a torn file would read back empty."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    os.replace(tmp, path)


class Calendar:
    """The feed, fetched on a timer, kept per week at <folder>/<week-start>.json, served by range."""

    def __init__(self, folder: Path, fetch=None, now=time.time):
        self.folder = Path(folder)
        self.fetch = fetch          # url -> bytes; None: never fetch (the stored weeks are still served)
        self.now = now
        self.weeks: dict[str, list[dict]] = {}
        self.ok, self.fetched_at, self.error, self.last_try = False, None, None, 0.0
        self.folder.mkdir(parents=True, exist_ok=True)
        for p in sorted(self.folder.glob(WEEK_FILES)):
            try:
                v = json.loads(p.read_text())
            except (OSError, ValueError):
                continue
            if isinstance(v, list):
                self.weeks[p.stem] = v
        try:
            st = json.loads((self.folder / "state.json").read_text())
            self.ok, self.fetched_at, self.error = bool(st.get("ok")), st.get("fetched_at"), st.get("error")
            self.last_try = float(st.get("last_try") or 0)
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def _save_state(self) -> None:
        _write_json(self.folder / "state.json", {"ok": self.ok, "fetched_at": self.fetched_at,
                                                  "error": self.error, "last_try": self.last_try})

    def wait_s(self) -> float:
        """Seconds until the next fetch is due: an hour after a good one, 30 minutes after a failed one."""
        return max(0.0, self.last_try + (EVERY_S if self.ok else MIN_GAP_S) - self.now())

    def refresh(self) -> bool:
        """One fetch (run it in a worker thread: it may block 10 s). Refused (False) without a fetch function
        or within 30 minutes of the last try. A good week replaces its file; a failure keeps the last good data
        and records why."""
        now = self.now()
        if self.fetch is None or now - self.last_try < MIN_GAP_S:
            return False
        self.last_try = now
        self._save_state()          # the floor holds even if this process dies mid-fetch
        try:
            events = parse(json.loads(self.fetch(FF_URL)))
            if not events:
                raise ValueError("the feed has no events")
        except Exception as e:  # noqa: BLE001 — any failure keeps the last good week
            self.ok, self.error = False, f"{type(e).__name__}: {e}"[:200]
            self._save_state()
            return False
        week = week_start(events[0]["t_ms"]).isoformat()
        self.weeks[week] = events
        _write_json(self.folder / f"{week}.json", events)
        self.ok, self.error, self.fetched_at = True, None, int(now * 1000)
        self._save_state()
        return True

    def events(self, frm: int, to: int, countries=None) -> list[dict]:
        """Every stored week's events with frm <= t_ms < to (and a country in `countries`, any case), by time."""
        want = {str(c).upper() for c in countries} if countries else None
        seen, out = set(), []
        for week in sorted(self.weeks):
            for e in self.weeks[week]:
                t = e.get("t_ms") if isinstance(e, dict) else None
                key = (t, e.get("country"), e.get("title")) if t is not None else None
                if not isinstance(t, int) or key in seen or not frm <= t < to:
                    continue
                if want is not None and str(e.get("country", "")).upper() not in want:
                    continue
                seen.add(key)
                out.append(e)
        out.sort(key=lambda e: e["t_ms"])
        return out

    def status(self) -> dict:
        return {"ok": self.ok, "fetched_at": self.fetched_at, "error": self.error}
