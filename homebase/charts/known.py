"""What the tick job knows about the data, for the charts.

The hourly tick job (homebase.ticks -- another process) writes two small files beside its log:

  tick_coverage.json   every hole of the last sessions, classed (homebase.tickcoverage): lost, filling,
                       vendor gap, not a hole -- and the hours short of their tick ids (`thin`);
  data_watch.json      the data watchdog's reading (homebase.datawatch): is the live feed late, thin, silent.

Both are only READ here, off the event loop: refresh() stats them on the service's repair poll and parses
the one that moved. The chart draws a session's holes as bands as wide as the time they cover (History.info
hands them to the page with each session), and the status strip says the feed's state.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .. import ticks as T

KIND = {"lost": "lost", "vendor_gap": "lost", "filling": "filling"}     # a hole's class -> the band the page draws:
                                                                        # grey (nobody has it) or amber (the broker does)
WATCH_STALE_S = 3 * 3600        # a watchdog reading this old is not now (the job has stopped finishing runs)


def _stamp(p: Path) -> tuple | None:
    try:
        st = p.stat()
    except OSError:
        return None
    return st.st_size, st.st_mtime_ns


def _load(p: Path) -> dict:
    try:
        got = json.loads(p.read_text())
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


def _ms(iso: str) -> int:
    return int(dt.datetime.fromisoformat(iso).timestamp() * 1000)


def holes_of(report: dict) -> tuple[dict, dict]:
    """({(root, ISO session date): [[start_ms, end_ms, kind], ...]}, {root: the newest session date in the
    report}) -- kind "lost" | "filling" | "thin", in time order. A session with no file at all has no chart
    session to carry its band: it rides in front of the NEXT session of the root that has one, and under
    (root, None) when it is the newest (the session under way then carries it). A report written before
    the classes existed gives nothing."""
    out: dict = {}
    last: dict = {}
    for root, entries in (report.get("roots") or {}).items():
        waiting: list = []
        for e in sorted((x for x in entries if isinstance(x, dict) and x.get("session")), key=lambda x: x["session"]):
            last[root] = e["session"]
            try:
                if e.get("status") == "missing":
                    if e.get("class") in KIND:
                        s, end = T.session_bounds(dt.date.fromisoformat(e["session"]), root)
                        waiting.append([int(s.timestamp() * 1000), int(end.timestamp() * 1000), KIND[e["class"]]])
                    continue
                mine = waiting + [[_ms(h["start_utc"]), _ms(h["end_utc"]), KIND[h["class"]]]
                                  for h in e.get("holes") or [] if h.get("class") in KIND] \
                    + [[_ms(h["start_utc"]), _ms(h["end_utc"]), "thin"] for h in e.get("thin") or []]
            except (KeyError, TypeError, ValueError):
                continue                    # an entry this code cannot read draws nothing
            waiting = []
            if mine:
                out[(root, e["session"])] = sorted(mine)
        if waiting:
            out[(root, None)] = waiting
    return out, last


class Known:
    def __init__(self, coverage: Path, watch: Path):
        self.coverage, self.watch_path = Path(coverage), Path(watch)
        self._stamps: dict = {}             # path -> (size, mtime_ns) as last read
        self._holes: dict = {}              # holes_of()
        self._last: dict = {}
        self.watch: dict = {}               # the watchdog's reading as written

    def refresh(self) -> set[str]:
        """Worker thread (or start-up). Read again whichever file moved since the last look. Returns the
        roots whose holes are no longer what the charts were told: theirs reload."""
        changed: set[str] = set()
        st = _stamp(self.coverage)
        if st != self._stamps.get("coverage"):
            self._stamps["coverage"] = st
            holes, last = holes_of(_load(self.coverage))
            changed = {k[0] for k in set(holes) | set(self._holes) if holes.get(k) != self._holes.get(k)}
            self._holes, self._last = holes, last
        st = _stamp(self.watch_path)
        if st != self._stamps.get("watch"):
            self._stamps["watch"] = st
            self.watch = _load(self.watch_path)
        return changed

    def holes(self, root: str, d: dt.date) -> list:
        """Session d's known holes as the page draws them: [[start_ms, end_ms, kind], ...]."""
        iso = d.isoformat()
        after = self._holes.get((root, None), []) if iso > self._last.get(root, iso) else []
        return after + self._holes.get((root, iso), [])

    def today(self, root: str, d: dt.date | None, tape_ms: int | None, now_ms: int) -> list:
        """The hours of the session under way that are short of their tick ids, as the watchdog read them
        (its markets' `holes`: [[start_ms, end_ms, kind], ...]) -- only from a reading of this very session,
        not stale, and taken AFTER the chart last built today's tape (tape_ms). The watchdog reads the files
        at the end of the tick job's run; the chart reloads the tape the minute a fill lands, during it: an
        older reading would still call the hour just repaired thin. No tint rather than a wrong one."""
        w = self.watch
        m = (w.get("markets") or {}).get(root) or {}
        try:
            at = dt.datetime.fromisoformat(w["at_utc"]).timestamp() * 1000
        except (KeyError, TypeError, ValueError):
            return []
        if d is None or tape_ms is None or m.get("session") != d.isoformat() or at <= tape_ms \
                or now_ms - at > WATCH_STALE_S * 1000:
            return []
        return [list(h) for h in m.get("holes") or [] if isinstance(h, list) and len(h) == 3]

    def data(self, now_ms: int) -> dict | None:
        """The watchdog's reading for the status message (the strip): its line, which markets are late /
        thin / silent, how old it is -- stale past WATCH_STALE_S. None before the first reading."""
        w = self.watch
        try:
            age = round(now_ms / 1000 - dt.datetime.fromisoformat(w["at_utc"]).timestamp())
        except (KeyError, TypeError, ValueError):
            return None
        return {"at_utc": w["at_utc"], "age_s": age, "stale": age > WATCH_STALE_S, "level": w.get("level"),
                "line": w.get("line"), "late_s": w.get("late_s"),
                **{k: list(w.get(k) or []) for k in ("late", "thin", "silent")},
                **{k: len(w.get(k) or []) for k in ("refused", "leaving")}}
