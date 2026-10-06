"""The tick archive's coverage report: homebase/.state/tick_coverage.json.

After every nightly run (and on demand: python -m homebase.ticks --coverage)
each root's last REPORT_SESSIONS sessions are checked hour by hour
(homebase.tickarchive.coverage) and every hole is listed by root, session and
hour, so a hole is visible instead of silent; one summary line goes to the
log. `--rescan` also writes each checked file's coverage into its manifest, so
`complete` there tells the truth for files written before it was computed.

Every session is one of five classes (CLASSES), from its pieces -- its empty
hours, the tick ids missing between its ticks, a late start or an early stop:

  whole        nothing to do;
  filling      the broker's history still has what is missing: until when;
  lost         it has left the broker (ticks.history_expiry): only bought data
               can fill it now ("needs_massive");
  vendor_gap   the bought backfill file itself has no ticks there: nobody can;
  not_a_hole   the exchange's hours, not lost data: an exchange holiday whose
               trades are filed under the next session, and for a 24/7 root the
               17:00 ET hour and the weekend (not_a_hole()).

A session whose pieces differ is filling while the broker still has any of it
(ORDER), and each hole says its own. Before the classes, 61 sessions "needed
Massive" (2026-10-06): 13 were lost, 16 a vendor gap, 32 not a hole -- and 21
sessions missing only tick ids (no empty hour) were not flagged at all. The
report also says what changed since the one before it.

Per session the front contract (homebase.symbols.front_month, the contract the
nightly job records) is looked up under both spellings the archive uses --
the desk's NGX6 and the Massive backfill's NGX26.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from . import symbols
from . import ticks as T
from . import tickarchive as A
from .charts.session import split_by_session

REPORT_SESSIONS = 30
CLASSES = ("whole", "filling", "lost", "vendor_gap", "not_a_hole")
ORDER = ("filling", "lost", "vendor_gap", "not_a_hole")    # a session's class: the first of these any piece of it
                            # has -- filling while the broker still has ANY of it (the fill is at work, there is
                            # a deadline; `why` says what already left), then what is final
SLIVER_MS = 5000            # Massive's edge windows (half a second each side of a gap it fills) adding up to less
                            # than this are no defect: the merge's guard against counting one trade twice
CHANGES_SAID = 12           # the log names this many changes since the previous report, then counts the rest
_CONTRACT = re.compile(r"^([A-Z0-9]+?)([FGHJKMNQUVXZ])(\d{1,2})$")


def contract_key(ticker: str):
    """(root, month, the year's last digit) -- NGX6 and NGX26 alike (a session
    never lists two contracts ten years apart) -- or None for anything else."""
    m = _CONTRACT.match(ticker)
    return (m.group(1), m.group(2), m.group(3)[-1]) if m else None


def same_contract(a: str, b: str) -> bool:
    return contract_key(a) is not None and contract_key(a) == contract_key(b)


def front_files(base: Path, root: str, date: dt.date) -> tuple[list[Path], list[Path]]:
    """(archive files, live files) of the session's front contract, both spellings."""
    front = symbols.front_month(root, date)
    tag = date.isoformat()
    archive, live = [], []
    for p in sorted((base / root / str(date.year)).glob(f"{tag}_*.csv.gz")):
        live_file = p.name.endswith(A.LIVE_SUFFIX)
        contract = p.name[len(tag) + 1:-len(A.LIVE_SUFFIX if live_file else ".csv.gz")]
        if same_contract(contract, front):
            (live if live_file else archive).append(p)
    return archive, live


def _file_coverage(path: Path, man: dict, root: str, date: dt.date, cache: dict,
                   base: Path) -> dict:
    """The file's coverage: its manifest's when that is current (written for
    this very file), else computed from the rows -- memoized in `cache` by
    size and mtime, so a night re-reads only files that changed."""
    st = path.stat()
    cov = man.get("coverage")
    if cov and cov.get("version") == A.COVERAGE_VERSION and man.get("bytes") == st.st_size:
        return cov
    key = str(path.relative_to(base))
    hit = cache.get(key)
    if hit and hit.get("bytes") == st.st_size and hit.get("mtime_ns") == st.st_mtime_ns \
            and hit.get("coverage", {}).get("version") == A.COVERAGE_VERSION:
        return hit["coverage"]
    start, end = T.session_bounds(date, root)
    cov = A.coverage(list(A.iter_rows(path)), root=root, date=date, start=start, end=end,
                     sources=A.prior_sources(man))
    cache[key] = {"bytes": st.st_size, "mtime_ns": st.st_mtime_ns, "coverage": cov}
    return cov


def _next_session(root: str, date: dt.date) -> dt.date:
    d = date + dt.timedelta(days=1)
    while not T.is_session_day(d, root):
        d += dt.timedelta(days=1)
    return d


def _filed_under_next(base: Path, root: str, date: dt.date) -> bool:
    """A missing session whose trades the next session's file already holds
    (it starts before its own 18:00 open): an exchange holiday, the trades
    filed under the next trade date -- Massive does that (Labor Day 2026)."""
    nxt = _next_session(root, date)
    start, _ = T.session_bounds(nxt, root)
    for p in front_files(base, root, nxt)[0]:
        first = A.ms_of(A.load_manifest(p).get("first_tick_utc"))
        if first is not None and first < start.timestamp() * 1000 - A.HOUR_MS:
            return True
    return False


def gone(t_ms: int, now: dt.datetime | None) -> bool:
    """Has the broker's history already dropped the tick stamped t_ms?"""
    return now is not None and now >= T.history_expiry(dt.datetime.fromtimestamp(t_ms / 1000, A.UTC))


def not_a_hole(root: str, a_ms: int, b_ms: int) -> str | None:
    """Why [a_ms, b_ms) without a tick is the exchange's hours and not lost data, or None. A classic
    root's session never holds such time. A 24/7 root's does: the daily 17:00-18:00 ET hour and the
    weekend (Friday 17:00 -> Sunday 18:00 ET), when CME crypto is halted or trades a handful of
    contracts (BTC 2026-09-23: 3 trades in the 17:00 hour, 77 in the next) -- an hour there without a
    trade proves nothing. Tick ids missing there are still missing trades: they are counted."""
    if split_by_session(None, a_ms, b_ms):
        return None                                   # some of it lies in the classic market's own hours
    t = dt.datetime.fromtimestamp(a_ms / 1000, T.ET)
    return "the 17:00 hour" if t.hour == 17 and b_ms - a_ms <= A.HOUR_MS else "weekend"


def fate(a_ms: int, b_ms: int, now: dt.datetime) -> tuple[float, float, dt.datetime | None]:
    """(hours of [a_ms, b_ms] that have left the broker's history, hours it still has, when it drops the
    first of those). The history is cut at 00:00 UTC (ticks.utc_segments): a stretch across it leaves in
    two parts, a day apart."""
    a, b = (dt.datetime.fromtimestamp(x / 1000, A.UTC) for x in (a_ms, b_ms))
    lost = left = 0.0
    until = None
    for s, e in T.utc_segments(a, b):
        exp, h = T.history_expiry(s), (e - s).total_seconds() / 3600
        if now >= exp:
            lost += h
        else:
            left += h
            until = exp if until is None else min(until, exp)
    return lost, left, until


def _piece(root: str, a_ms: int, b_ms: int, now: dt.datetime, bought: bool = False) -> dict:
    """One stretch without ticks: its class -- not a hole; filling while the broker still has any of
    it (until_utc: when it drops the first part it has); else lost, or a vendor gap in a bought file --
    and, for the tallies, the hours of it that left the broker / are still there (_lost_h, _left_h)."""
    why = not_a_hole(root, a_ms, b_ms)
    if why:
        return {"class": "not_a_hole", "why": why, "_idle_h": (b_ms - a_ms) / A.HOUR_MS}
    lost, left, until = fate(a_ms, b_ms, now)
    out = {"class": "filling" if left else "vendor_gap" if bought else "lost", "_lost_h": lost, "_left_h": left}
    if until is not None:
        out["until_utc"] = until.isoformat()
    return out


def _public(pc: dict) -> dict:
    return {k: v for k, v in pc.items() if not k.startswith("_")}


def _id_hours(path: Path, root: str, date: dt.date, cache: dict, base: Path) -> list:
    """[[hour_start_ms, ids held, ids missing], ...] for the hours of the file that miss tick ids
    (tickarchive.hours_of over its id runs), memoized in `cache` by the file's size and mtime. Where a
    Massive row stands in for a gap the ids still count here: the session's own `missing_ids` (which
    leaves those out) stays the total, these hours only say where and in what share."""
    st = path.stat()
    key = str(path.relative_to(base)) + "#hours"
    hit = cache.get(key)
    if hit and hit.get("bytes") == st.st_size and hit.get("mtime_ns") == st.st_mtime_ns:
        return hit["hours"]
    start, end = T.session_bounds(date, root)
    hours = [h for h in A.hours_of(A.file_runs(path, {})["runs"], int(start.timestamp() * 1000),
                                   int(end.timestamp() * 1000)) if h[2]]
    cache[key] = {"bytes": st.st_size, "mtime_ns": st.st_mtime_ns, "hours": hours}
    return hours


def _n(n: float, word: str) -> str:
    """"2 hole-hours", "1 tick id", "1,116,024 tick ids", "2.5 hole-hours"."""
    n = int(n) if n == int(n) else n
    return f"{n:,} {word}" + ("" if n == 1 else "s")


def _amount(hours: float, ids: int) -> tuple[str, bool]:
    """("2 hole-hours and 500 tick ids", plural?) -- "" when there is neither."""
    hours = round(hours, 2)
    parts = ([_n(hours, "hole-hour")] if hours else []) + ([_n(ids, "tick id")] if ids else [])
    return " and ".join(parts), len(parts) > 1 or (hours or ids) != 1


def _until(iso: str) -> str:
    return f"{dt.datetime.fromisoformat(iso).astimezone(T.ET):%m-%d %H:%M} ET"


def classify(entry: dict, root: str, date: dt.date, now: dt.datetime, man: dict, path: Path,
             cache: dict, base: Path) -> None:
    """entry's class (CLASSES; ORDER when its pieces differ), its plain-words `why`, `until_utc` while
    the broker has any of it, and needs_massive (the class is lost) -- from its pieces: each hole
    (classed in place), the tick ids missing between its ticks, a late start or an early stop (`edges`),
    Massive's unfilled edges. `hours` and `ids`: its hole-hours and missing ids by what became of them
    (lost / filling / vendor_gap / not_a_hole); `thin`: the hours short of tickarchive.THIN_SHARE of
    their ids, for the chart."""
    start, end = T.session_bounds(date, root)
    s_ms, e_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    bought = man.get("source") == "massive" or any(x.get("kind") == "massive" for x in A.prior_sources(man))
    seen: list[dict] = []                               # every piece
    holes = []
    for h in entry["holes"]:
        pc = _piece(root, A.ms_of(h["start_utc"]), A.ms_of(h["end_utc"]), now, bought)
        seen.append(pc)
        holes.append({**h, **_public(pc), "needs_massive": pc["class"] == "lost"})
    entry["holes"] = holes
    hours = {"lost": 0.0 if bought else sum(pc.get("_lost_h", 0) for pc in seen),
             "filling": sum(pc.get("_left_h", 0) for pc in seen),
             "vendor_gap": sum(pc.get("_lost_h", 0) for pc in seen) if bought else 0.0,
             "not_a_hole": sum(pc.get("_idle_h", 0) for pc in seen)}
    close = e_ms
    if entry.get("early_close_et"):
        close = min(e_ms, int(dt.datetime.combine(date, dt.time.fromisoformat(entry["early_close_et"]),
                                                  T.ET).timestamp() * 1000))
    edges = []
    for at, ok, a, b in (("open", entry["head_ok"], s_ms, s_ms + A.EDGE_MS),
                         ("close", entry["tail_ok"], close - A.EDGE_MS, close)):
        if not ok and not any(h["at"] == at for h in holes):    # ticks start late / stop early, no empty hour there
            pc = _piece(root, a, b, now)
            seen.append(pc)
            edges.append({"at": at, **_public(pc)})
    ids = {"lost": 0, "filling": 0}
    if entry["missing_ids"]:
        by_hour = _id_hours(path, root, date, cache, base)
        there = [(a, m) for a, _, m in by_hour if not gone(a, now)]
        ids["filling"] = round(entry["missing_ids"] * sum(m for _, m in there) / sum(m for _, _, m in by_hour)) \
            if by_hour else (0 if gone(e_ms, now) else entry["missing_ids"])
        ids["lost"] = entry["missing_ids"] - ids["filling"]
        if ids["lost"]:
            seen.append({"class": "lost"})
        if ids["filling"]:
            seen.append({"class": "filling", "until_utc": min(
                (T.history_expiry(dt.datetime.fromtimestamp(a / 1000, A.UTC)) for a, _ in there),
                default=T.history_expiry(end)).isoformat()})
        thin = [{"from_et": f"{dt.datetime.fromtimestamp(a / 1000, T.ET):%H:%M}",
                 "to_et": f"{dt.datetime.fromtimestamp(b / 1000, T.ET):%H:%M}",
                 "start_utc": A.iso_ms(a), "end_utc": A.iso_ms(b), "missing_ids": miss,
                 "class": "lost" if gone(b - 1, now) else "filling"}       # ids are missing whatever the hour
                for a, b, kind, miss in A.short_hours(by_hour) if kind == "thin"]
        if thin:
            entry["thin"] = thin
    sliver = entry["massive_edge_ms"] >= SLIVER_MS
    kinds = {pc["class"] for pc in seen} | ({"lost"} if sliver else set())
    entry["class"] = next((c for c in ORDER if c in kinds), "whole")
    untils = [pc["until_utc"] for pc in seen if pc.get("until_utc")]
    if untils:
        entry["until_utc"] = min(untils)
    entry["needs_massive"] = entry["class"] == "lost"
    for k, v in (("hours", {c: round(h, 2) for c, h in hours.items() if round(h, 2)}),
                 ("ids", {c: n for c, n in ids.items() if n}), ("edges", edges)):
        if v:
            entry[k] = v
    # ---- why, in plain words: what is final first, then what the broker still has
    said = []
    gone_txt, plural = _amount(hours["lost"], ids["lost"])
    if gone_txt:
        said.append(f"{gone_txt} {'have' if plural else 'has'} left the broker")
    vendor = [h for h in holes if h["class"] == "vendor_gap"]
    if vendor:
        said.append("the bought file itself has no ticks "
                    + ", ".join(f"{h['from_et']}-{h['to_et']}" for h in vendor) + " ET")
    said += [f"the {e['at']} has left the broker" for e in edges if e["class"] == "lost"]
    if sliver:
        said.append(f"{entry['massive_edge_ms'] / 1000:g} s at the edges of bought rows cannot be filled")
    left_txt, plural = _amount(hours["filling"], ids["filling"])
    if left_txt:
        said.append(f"the rest is at the broker until {_until(min(untils))}" if said else
                    f"{left_txt} {'are' if plural else 'is'} still at the broker, until {_until(min(untils))}")
    said += [f"the {e['at']} is still at the broker, until {_until(e['until_utc'])}"
             for e in edges if e["class"] == "filling"]
    if entry["class"] == "not_a_hole":
        said = list(dict.fromkeys(pc["why"] for pc in seen if pc.get("why")))
    if said:
        entry["why"] = "; ".join(said)


def classify_missing(entry: dict, root: str, date: dt.date, now: dt.datetime, holiday: bool) -> None:
    """A session with no file at all: an exchange holiday or a 24/7 root's weekend (not a hole), else
    lost or filling like any stretch."""
    start, end = T.session_bounds(date, root)
    s_ms, e_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    if holiday:
        entry.update({"class": "not_a_hole", "why": "exchange holiday: its trades are filed under the next session"})
    else:
        pc = _piece(root, s_ms, e_ms, now)
        entry["class"] = pc["class"]
        if pc.get("until_utc"):
            entry["until_utc"] = pc["until_utc"]
        hours = {k: round(pc.get(h, 0), 2) for k, h in (("lost", "_lost_h"), ("filling", "_left_h"))}
        if any(hours.values()):                           # every hour of it is a hole-hour
            entry["hours"] = {k: v for k, v in hours.items() if v}
        if pc["class"] == "not_a_hole":
            entry["why"] = pc["why"]
        elif pc["class"] == "lost":
            entry["why"] = "nothing recorded, and it has left the broker"
        elif pc["_lost_h"]:
            entry["why"] = f"nothing recorded: part has left the broker, the rest is there until {_until(pc['until_utc'])}"
        else:
            entry["why"] = f"nothing recorded: still at the broker, until {_until(pc['until_utc'])}"
    entry["needs_massive"] = entry["class"] == "lost"


def session_entry(base: Path, root: str, date: dt.date, cache: dict,
                  now: dt.datetime | None = None) -> dict:
    """One session's line in the report. With `now` it is classed (CLASSES; classify): every hole --
    and a missing session -- says whether the broker's history still has it, and until when;
    "needs_massive": it is lost, only bought data can fill it now."""
    archive, live = front_files(base, root, date)
    entry = {"session": date.isoformat(), "contract": symbols.front_month(root, date)}
    best = None
    for p in archive:
        man = A.load_manifest(p)
        cov = _file_coverage(p, man, root, date, cache, base)
        rank = (cov["complete"], man.get("ticks") or 0)
        if best is None or rank > best[0]:
            best = (rank, p, man, cov)
    if best is not None:
        _, p, man, cov = best
        entry.update(status="complete" if cov["complete"] else "partial", file=str(p.relative_to(base)),
                     ticks=man.get("ticks"), source=man.get("source", "desk"),
                     bid_ask=man.get("bid_ask", True))
    elif live:
        p = live[0]
        cov = _file_coverage(p, {}, root, date, cache, base)
        entry.update(status="live_only", file=str(p.relative_to(base)))
    else:
        holiday = _filed_under_next(base, root, date)
        entry.update(status="missing", flags=["filed_under_next_session"] if holiday else [])
        if now is not None:                       # an exchange holiday has nothing anywhere to fill
            classify_missing(entry, root, date, now, holiday)
        return entry
    entry.update({k: cov.get(k, 0) for k in ("holes", "hole_hours", "missing_ids", "massive_edge_ms",
                                             "head_ok", "tail_ok", "early_close_et")})
    if now is not None:
        classify(entry, root, date, now, man if best is not None else {}, p, cache, base)
    others = [q.name for q in archive + live if q != p]
    if others:
        entry["other_files"] = others
    return entry


def report_sessions(root: str, now: dt.datetime, n: int = REPORT_SESSIONS) -> list[dt.date]:
    """The root's last n sessions that are over, newest first."""
    return sorted(T.sessions_to_record(now, 2 * n + 7, root), reverse=True)[:n]


def build_report(roots, base: Path, now: dt.datetime, n: int = REPORT_SESSIONS,
                 cache: dict | None = None, watch: dict | None = None) -> dict:
    """The report. `watch`: the data watchdog's last reading (homebase.datawatch), carried as it is."""
    cache = {} if cache is None else cache
    out = {r: [session_entry(base, r, d, cache, now) for d in report_sessions(r, now, n)] for r in roots}
    es = [e for es in out.values() for e in es]
    untils = [e["until_utc"] for e in es if e.get("until_utc")]
    summary = {"roots": len(out), "sessions": len(es),
               **{s: sum(1 for e in es if e["status"] == s)
                  for s in ("complete", "partial", "live_only", "missing")},
               "hole_hours": round(sum(e.get("hole_hours", 0) for e in es), 2),
               "missing_ids": sum(e.get("missing_ids", 0) for e in es),
               "needs_massive": sum(1 for e in es if e.get("needs_massive")),
               "classes": {c: sum(1 for e in es if e.get("class") == c) for c in CLASSES},
               # what became of the hole-hours and the missing ids, over every session: still at the broker
               # (until when the first of it goes), or gone from it
               "filling": {"hole_hours": round(sum(e.get("hours", {}).get("filling", 0) for e in es), 2),
                           "missing_ids": sum(e.get("ids", {}).get("filling", 0) for e in es),
                           "until_utc": min(untils) if untils else None},
               "lost": {"hole_hours": round(sum(e.get("hours", {}).get("lost", 0) for e in es), 2),
                        "missing_ids": sum(e.get("ids", {}).get("lost", 0) for e in es)}}
    return {"generated_at_utc": now.astimezone(A.UTC).isoformat(timespec="seconds"), "archive": str(base),
            "sessions_per_root": n, "summary": summary, **({"watch": watch} if watch else {}),
            "not_modelled": A.NOT_MODELLED, "roots": out}


def summary_line(rep: dict, path: Path) -> str:
    s = rep["summary"]
    c = s["classes"]
    f = s["filling"]
    return (f"coverage, last {rep['sessions_per_root']} sessions x {s['roots']} roots: {c['whole']} whole, "
            f"{c['filling']} filling"
            + (f" ({f['hole_hours']:g} hole-hours, {f['missing_ids']:,} tick ids at the broker until "
               f"{_until(f['until_utc'])})" if f["until_utc"] else "")
            + f", {c['lost']} lost ({s['lost']['hole_hours']:g} hole-hours, {s['lost']['missing_ids']:,} tick ids), "
            f"{c['vendor_gap']} vendor gap, {c['not_a_hole']} not a hole -> {path}")


def changes(prev: dict, rep: dict) -> list[str]:
    """What moved since the previous report, in plain words, newest session first within each root: a
    session whose class changed, one still filling that has less (or more) missing, and a session new to
    the report that is not whole. A previous report without classes (written before they existed) is not
    compared."""
    was = {(r, e.get("session")): e for r, es in (prev.get("roots") or {}).items() for e in es}
    if not any("class" in e for e in was.values()):
        return []
    out = []
    for r, es in rep["roots"].items():
        for e in es:
            day, old = e["session"][5:], was.get((r, e["session"]))
            if old is None or "class" not in old:
                if e["class"] in ("filling", "lost", "vendor_gap"):
                    out.append(f"{r} {day} new: {e['class'].replace('_', ' ')}"
                               + (f" until {_until(e['until_utc'])}" if e["class"] == "filling" else ""))
            elif old["class"] != e["class"]:
                out.append(f"{r} {day} {old['class'].replace('_', ' ')} -> {e['class'].replace('_', ' ')}")
            elif e["class"] == "filling":
                a = (old.get("hole_hours", 0), old.get("missing_ids", 0))
                b = (e.get("hole_hours", 0), e.get("missing_ids", 0))
                if a != b:
                    moved = ([f"{a[0]:g} -> {b[0]:g} hole-hours"] if a[0] != b[0] else []) \
                        + ([f"{a[1]:,} -> {b[1]:,} tick ids"] if a[1] != b[1] else [])
                    out.append(f"{r} {day} filling: " + ", ".join(moved))
    return out


def write_report(roots, base: Path, now: dt.datetime, path: Path, n: int = REPORT_SESSIONS,
                 watch: dict | None = None) -> dict:
    """Build the report, write it (and its cache beside it) atomically, log the line -- and, in a
    second line, what changed since the report it replaces (`changes`; nothing moved: not a word)."""
    cache_path = path.with_name(path.stem + ".cache.json")
    try:
        cache = json.loads(cache_path.read_text())
    except (OSError, ValueError):
        cache = {}
    try:
        prev = json.loads(path.read_text())
    except (OSError, ValueError):
        prev = {}
    rep = build_report(roots, base, now, n, cache, watch)
    rep["changes"] = changes(prev, rep) if isinstance(prev, dict) else []
    rep["previous_generated_at_utc"] = prev.get("generated_at_utc") if isinstance(prev, dict) else None
    path.parent.mkdir(parents=True, exist_ok=True)
    A.atomic_write(path, (json.dumps(rep, indent=1) + "\n").encode())
    A.atomic_write(cache_path, json.dumps(cache).encode())
    T.log(summary_line(rep, path))
    if rep["changes"]:
        more = len(rep["changes"]) - CHANGES_SAID
        T.log(f"coverage changes since {_until(rep['previous_generated_at_utc'])[6:]}: "
              + "; ".join(rep["changes"][:CHANGES_SAID]) + (f"; and {more} more" if more > 0 else ""))
    return rep


def rescan(roots, base: Path, now: dt.datetime, n: int = REPORT_SESSIONS) -> int:
    """Write each front-contract file's hour-by-hour coverage into its manifest
    (and `complete` from it) for the last n sessions -- the data files are not
    touched. Returns how many manifests changed."""
    changed = 0
    for root in roots:
        for date in report_sessions(root, now, n):
            for p in front_files(base, root, date)[0]:
                man = A.load_manifest(p)
                if not man:
                    continue                      # no manifest: nothing to correct, the report lists it
                cov = _file_coverage(p, man, root, date, {}, base)
                if man.get("coverage") == cov and man.get("complete") == cov["complete"]:
                    continue
                man.update(coverage=cov, complete=cov["complete"], bytes=p.stat().st_size,
                           coverage_checked_at_utc=A.now_utc())
                A.write_manifest(p, man)
                changed += 1
                if not cov["complete"]:
                    T.log(f"{root} {date} {p.name}: complete -> False "
                          f"({cov['hole_hours']:g} hole-hours, {cov['missing_ids']} missing ids)")
    return changed
