"""The tick archive's coverage report: homebase/.state/tick_coverage.json.

After every nightly run (and on demand: python -m homebase.ticks --coverage)
each root's last REPORT_SESSIONS sessions are checked hour by hour
(homebase.tickarchive.coverage) and every hole is listed by root, session and
hour, so a hole is visible instead of silent; one summary line goes to the
log. `--rescan` also writes each checked file's coverage into its manifest, so
`complete` there tells the truth for files written before it was computed.

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

REPORT_SESSIONS = 30
_CONTRACT = re.compile(r"^([A-Z0-9]+?)([FGHJKMNQUVXZ])(\d{1,2})$")


def same_contract(a: str, b: str) -> bool:
    """NGX6 == NGX26: root, month and the year's last digit (a session never
    lists two contracts ten years apart)."""
    ma, mb = _CONTRACT.match(a), _CONTRACT.match(b)
    return bool(ma and mb) and (ma.group(1), ma.group(2), ma.group(3)[-1]) == \
        (mb.group(1), mb.group(2), mb.group(3)[-1])


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


def session_entry(base: Path, root: str, date: dt.date, cache: dict) -> dict:
    """One session's line in the report."""
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
        entry.update(status="missing", flags=["filed_under_next_session"]
                     if _filed_under_next(base, root, date) else [])
        return entry
    entry.update({k: cov[k] for k in ("holes", "hole_hours", "missing_ids", "head_ok", "tail_ok",
                                      "early_close_et")})
    others = [q.name for q in archive + live if q != p]
    if others:
        entry["other_files"] = others
    return entry


def report_sessions(root: str, now: dt.datetime, n: int = REPORT_SESSIONS) -> list[dt.date]:
    """The root's last n sessions that are over, newest first."""
    return sorted(T.sessions_to_record(now, 2 * n + 7, root), reverse=True)[:n]


def build_report(roots, base: Path, now: dt.datetime, n: int = REPORT_SESSIONS,
                 cache: dict | None = None) -> dict:
    cache = {} if cache is None else cache
    out = {r: [session_entry(base, r, d, cache) for d in report_sessions(r, now, n)] for r in roots}
    es = [e for es in out.values() for e in es]
    summary = {"roots": len(out), "sessions": len(es),
               **{s: sum(1 for e in es if e["status"] == s)
                  for s in ("complete", "partial", "live_only", "missing")},
               "hole_hours": round(sum(e.get("hole_hours", 0) for e in es), 2),
               "missing_ids": sum(e.get("missing_ids", 0) for e in es)}
    return {"generated_at_utc": A.now_utc(), "archive": str(base), "sessions_per_root": n,
            "summary": summary, "not_modelled": A.NOT_MODELLED, "roots": out}


def summary_line(rep: dict, path: Path) -> str:
    s = rep["summary"]
    return (f"coverage, last {rep['sessions_per_root']} sessions x {s['roots']} roots: "
            f"{s['complete']} complete, {s['partial']} partial ({s['hole_hours']:g} hole-hours, "
            f"{s['missing_ids']:,} missing tick ids), {s['live_only']} live-only, "
            f"{s['missing']} missing -> {path}")


def write_report(roots, base: Path, now: dt.datetime, path: Path, n: int = REPORT_SESSIONS) -> dict:
    """Build the report, write it (and its cache beside it) atomically, log the line."""
    cache_path = path.with_name(path.stem + ".cache.json")
    try:
        cache = json.loads(cache_path.read_text())
    except (OSError, ValueError):
        cache = {}
    rep = build_report(roots, base, now, n, cache)
    path.parent.mkdir(parents=True, exist_ok=True)
    A.atomic_write(path, (json.dumps(rep, indent=1) + "\n").encode())
    A.atomic_write(cache_path, json.dumps(cache).encode())
    T.log(summary_line(rep, path))
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
