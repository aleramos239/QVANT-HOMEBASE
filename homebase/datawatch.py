"""The data watchdog: is the desk's market data late, thin, silent, or about to be lost?

Run at the end of every tick-archive run (homebase.ticks.run: hourly, on load, 17:20 and 05:30 ET). It
only READS -- the chart service's live recordings and the archive's files, through the run's own cache
of what each file holds (homebase.tickarchive.file_runs) -- never the broker, and it never writes under
the archive. Per market, while its session is under way:

  late     how long after its own time the live recording's newest tick was written. A real-time feed is
           written within a second or two of the trade; the exchange's delayed feed is ten minutes behind
           (login 1552885 from 2026-10-02 08:11 ET: every chart and every recording 600 s late, the chart
           service reporting "connected, no error").
  thin     the share of the published tick ids the live recording received in the last full hour of the
           feed's own clock. The broker numbers a contract's trades with one gap-free counter, so the ids
           the recording skipped are trades it never got (NQ 2026-10-05 09:00-11:00 ET: 20,351 of 128,924).
  silent   nothing written for SILENT_* while the market is open (a market that has just opened is not
           silent for the hour it was closed; exchange holidays are not known).

For the archive: the sessions whose merge was refused and whose files are still as they were, and what is
still missing and leaves the broker's history window within LEAVING_H hours (the fill's own plan).

It writes one small state file, homebase/.state/data_watch.json -- the chart strip, the coverage report
and the connector's data_coverage / desk_readiness read it -- and says one plain line in the job's log on
every run while something is wrong, and once when it is fine again. A healthy desk: not a word.
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
from pathlib import Path

from . import symbols
from . import tickarchive as A
from . import ticks as T
from .charts.session import session_date, session_range_ms

LATE_S = 60                 # written this long after its own time, a market's newest tick is LATE ...
FRESH_S = 2 * 3600          # ... read only off a recording written this recently: an old write says nothing of now
CLOCK_SLACK_MS = 2000       # a file stamped further than this past the job's own clock gives no reading
SILENT_RTH_S = 15 * 60      # regular hours (09:30-16:00 ET): the job's own "the recording stopped" (ticks.STALE_MS)
SILENT_ETH_S = 60 * 60      # any other open hour: thin overnight markets (ZN, NG, HG) idle for minutes
SILENT_247_S = 2 * 3600     # a 24/7 root, and only while the classic market is open (a weekend proves nothing)
LEAVING_H = 6               # what is still missing and leaves the broker within this many hours is named
RTH = (dt.time(9, 30), dt.time(16, 0))
NAMED = 3                   # the line names this many markets / sessions, then counts the rest


def _ms(t: dt.datetime) -> int:
    return int(t.timestamp() * 1000)


def _hm(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, T.ET).strftime("%H:%M")


def under_way(root: str | None, now_ms: int) -> tuple[dt.date, int, int] | None:
    """(session date, open ms, close ms) of root's session if one is under way at now_ms, else None:
    the daily 17:00 hour and the weekend for a classic root; a 24/7 root is always open."""
    d = session_date(now_ms, root)
    s0, s1 = session_range_ms(d, root)
    return (d, s0, s1) if s0 <= now_ms < s1 else None


def silent_after(root: str, now: dt.datetime) -> float:
    """Seconds without a write before root counts as silent at `now` (see the constants)."""
    if T.always_open(root):
        return SILENT_247_S if under_way(None, _ms(now)) else float("inf")
    t = now.astimezone(T.ET)
    return SILENT_RTH_S if t.weekday() < 5 and RTH[0] <= t.time() < RTH[1] else SILENT_ETH_S


def market(root: str, base: Path, now: dt.datetime, cache: dict) -> dict:
    """One market's reading. {"open": False} outside its session."""
    now_ms = _ms(now)
    sess = under_way(root, now_ms)
    if sess is None:
        return {"open": False}
    d, s0, _ = sess
    contract = symbols.front_month(root, d)
    path = T.archive_path(root, d, contract, base)
    fl = A.file_runs(A.live_path(path), cache)
    runs = fl["runs"]
    m = {"open": True, "session": d.isoformat(), "contract": contract, "late_s": None, "silent_s": None,
         "hour_utc": None, "received": None, "published": None, "share": None, "holes": []}
    quiet_ms, late_ms = now_ms - s0, 0
    if runs:
        newest = max(r[3] for r in runs)
        written = fl["mtime_ns"] // 1_000_000
        if written > now_ms + CLOCK_SLACK_MS:            # the clock was set back since: no reading from the stamp
            quiet_ms = min(quiet_ms, now_ms - newest)
        else:
            quiet_ms = min(quiet_ms, now_ms - written)
            if now_ms - written <= FRESH_S * 1000:
                late_ms = max(0, written - newest)
                m["late_s"] = round(late_ms / 1000)
    if quiet_ms / 1000 >= silent_after(root, now):
        m["silent_s"] = round(quiet_ms / 1000)
    # the last full hour on the FEED's clock: a late feed's own hour ends late
    h1 = (now_ms - late_ms) // A.HOUR_MS * A.HOUR_MS
    if h1 - A.HOUR_MS >= s0:
        got = {a: (held, miss) for a, held, miss in A.hours_of(runs, s0, h1)}.get(h1 - A.HOUR_MS)
        if got is not None:
            m.update(hour_utc=A.iso_ms(h1 - A.HOUR_MS), received=got[0], published=got[0] + got[1],
                     share=round(got[0] / (got[0] + got[1]), 3))
        # for today's chart, which reads the recording and the archive file as one: the hours still short
        both = A.union_runs(A.file_runs(path, cache)["runs"], runs)
        for a, b, kind, _ in A.short_hours(A.hours_of(both, s0, h1)):
            if kind == "empty":
                kind = "lost" if now >= T.history_expiry(dt.datetime.fromtimestamp(a / 1000, A.UTC)) else "filling"
            m["holes"].append([a, b, kind])
    return m


def thin(m: dict) -> bool:
    return bool(m.get("published")) and m["published"] >= A.THIN_MIN_IDS and m["share"] < A.THIN_SHARE


def refused(base: Path, cache: dict, now: dt.datetime) -> list[dict]:
    """Sessions whose merge was refused and whose files are still exactly as then (ticks.refused_still)."""
    out = []
    for key, got in sorted((cache.get(T.REFUSED) or {}).items()):
        root, _, day = key.partition(" ")
        try:
            date = dt.date.fromisoformat(day)
            path = T.archive_path(root, date, symbols.front_month(root, date), base)
        except (ValueError, KeyError):
            continue
        if T.refused_still(cache, root, date, path):
            out.append({"root": root, "session": day, "why": got.get("why"), "at_utc": got.get("at"),
                        "broker_has_it": now < T.history_expiry(T.session_bounds(date, root)[1])})
    return out


def leaving(roots, base: Path, now: dt.datetime, cache: dict, hours: float = LEAVING_H) -> list[dict]:
    """What the fill would still fetch (ticks.plan) and the broker drops within `hours`."""
    _, jobs = T.plan(roots, T.candidate_dates(now), base, now, cache, quiet=True)
    soon = now + dt.timedelta(hours=hours)
    return [{"root": key[0], "session": key[1].isoformat(), "from_utc": s.isoformat(), "to_utc": e.isoformat(),
             "why": why, "leaves_utc": exp.isoformat()}
            for exp, _, _, _, key, s, e, why in jobs if exp <= soon]


def _named(items: list[str]) -> str:
    more = len(items) - NAMED
    return ", ".join(items[:NAMED]) + (f" and {more} more" if more > 0 else "")


def words(st: dict) -> str:
    """The state in one plain line."""
    mk, parts = st["markets"], []
    if st["late"] and st["late_s"] >= LATE_S:               # the feed itself: most markets are behind
        parts.append(f"the live feed is {round(st['late_s'] / 60)} min late ({len(st['late'])} of "
                     f"{sum(1 for m in mk.values() if m.get('late_s') is not None)} markets)")
    elif st["late"]:
        parts.append(_named([f"{r} {round(mk[r]['late_s'] / 60)} min late" for r in st["late"]]))
    if st["thin"]:
        r = st["thin"][0]
        h = A.ms_of(mk[r]["hour_utc"])
        parts.append(f"thin: {r} got {round(100 * mk[r]['share'])}% of its ticks {_hm(h)}-{_hm(h + A.HOUR_MS)} ET"
                     + (f" ({len(st['thin'])} markets thin)" if len(st["thin"]) > 1 else ""))
    if st["silent"]:
        parts.append(_named([f"{r} silent {round(mk[r]['silent_s'] / 60)} min" for r in st["silent"]]))
    if st["leaving"]:
        first = min(dt.datetime.fromisoformat(x["leaves_utc"]) for x in st["leaving"])
        names = list(dict.fromkeys(f"{x['root']} {x['session'][5:]}" for x in st["leaving"]))
        n = len(st["leaving"])
        parts.append(f"{n} missing stretch{'es leave' if n > 1 else ' leaves'} the broker by "
                     f"{first.astimezone(T.ET):%H:%M} ET ({_named(names)})")
    if st["refused"]:
        n = len(st["refused"])
        parts.append(f"{n} merge{'s' if n > 1 else ''} refused ("
                     + _named([f"{x['root']} {x['session'][5:]}" for x in st["refused"]]) + ")")
    return "data: " + ("; ".join(parts) or "fine")


def check(roots, base: Path, now: dt.datetime, cache: dict) -> dict:
    """The whole reading (JSON-able). level: "fine" | "warn"."""
    mk = {r: market(r, base, now, cache) for r in roots}
    lates = [m["late_s"] for m in mk.values() if m.get("late_s") is not None]
    st = {"at_utc": now.astimezone(A.UTC).isoformat(timespec="seconds"),
          "late_s": statistics.median(lates) if lates else None,      # the feed's: one odd market does not move it
          "late": [r for r, m in mk.items() if (m.get("late_s") or 0) >= LATE_S],
          "thin": [r for r, m in mk.items() if thin(m)],
          "silent": [r for r, m in mk.items() if m.get("silent_s") is not None],
          "markets": mk, "refused": refused(base, cache, now), "leaving": leaving(roots, base, now, cache)}
    st["level"] = "warn" if any(st[k] for k in ("late", "thin", "silent", "refused", "leaving")) else "fine"
    st["line"] = words(st)
    return st


def load(path: Path) -> dict:
    try:
        got = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


def run(roots, base: Path, now: dt.datetime, cache: dict, path: Path) -> dict:
    """check(), written to `path` atomically; its line to the job's log while something is wrong, and
    once when it is fine again."""
    was = load(path).get("level")
    st = check(roots, base, now, cache)
    path.parent.mkdir(parents=True, exist_ok=True)
    A.atomic_write(path, (json.dumps(st, indent=1) + "\n").encode())
    if st["level"] != "fine":
        T.log(st["line"])
    elif was not in (None, "fine"):
        T.log("data: fine again")
    return st
