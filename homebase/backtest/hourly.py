"""The 1-hour closes of the sessions before a date: what a strategy reads as `ctx.hourly` (Strategy.needs_hourly, 2026-10-18).

A strategy carries nothing from one day to the next (session_independent), so an indicator of 1-hour closes that runs on across
days (the owner's 1-hour EMA 50) reads the earlier sessions from here, at its session start, in the tester (backtest/runner.py)
and on the Desk (labrun/host.py) alike.

    session_hours(tape)                     -> [[end_ns, close], ...] of ONE session, oldest first
    prior(store, root, d, n, cache=None)    -> the same for the n sessions before d, oldest first

A 1-hour close = the last print of a whole ET clock hour; an hour without a print makes none (the 17:00-18:00 break is no hour).
A session = 18:00 ET of the evening before its date to 17:00 of the date (the archive's session, its tape). Only COMPLETE earlier
sessions are given -- never today's hours: a strategy builds those from its own bars. The sessions are today's contract's: going back,
the first session of another contract ends the list (a roll day gets none). Today's contract is the archive's front contract of d,
or, while d has no archive file yet (the Desk, early in the day), the newest earlier session's. At most MAX_SESSIONS; a date with no
tape is passed over.

Nothing after d is read: every session given ended at 17:00 of a date before d.
"""
from __future__ import annotations

import datetime as dt
from bisect import bisect_left

from .tape import et_ns

HOUR_NS = 3600 * 1_000_000_000
MAX_SESSIONS = 30
LOOKBACK = dt.timedelta(days=60)            # calendar days searched for MAX_SESSIONS sessions


def session_hours(tape) -> list[list]:
    """[[end_ns, close], ...]: the whole ET hours of the tape's session (18:00 the evening before -> 17:00), oldest first."""
    d, ts, px = tape.date, tape.ts, tape.px
    t0, t1 = et_ns(d - dt.timedelta(days=1), "18:00"), et_ns(d, "17:00")
    out, h = [], t0 - t0 % HOUR_NS
    while h < t1:
        end = h + HOUR_NS
        i0, i1 = bisect_left(ts, max(h, t0)), bisect_left(ts, min(end, t1))
        if i1 > i0 and end <= t1:
            out.append([end, float(px[i1 - 1])])
        h = end
    return out


def prior(store, root: str, d: dt.date, n: int, cache: dict | None = None) -> list[list]:
    """The 1-hour closes of the n complete sessions before d of d's contract, oldest first (module docstring).
    store: a TapeStore (sessions / pick / load). cache: {date: (contract, hours)} kept by the caller across days."""
    n = max(0, min(int(n), MAX_SESSIONS))
    if not n:
        return []
    cache = {} if cache is None else cache
    today = store.pick(root, d)
    want = today[1] if today else None
    taken: list[list] = []
    for x in reversed([s for s in store.sessions(root, d - LOOKBACK, d) if s < d]):
        if len(taken) == n:
            break
        if x not in cache:
            got = store.pick(root, x)
            if got is None:
                continue                             # no tape that day: passed over
            tape = store.load(root, x)
            cache[x] = (got[1], session_hours(tape) if tape is not None else None)
        contract, hours = cache[x]
        if hours is None:
            continue
        if want is None:
            want = contract                          # d not in the archive yet: the newest earlier session's contract
        if contract != want:
            break                                    # another contract: the list ends at the roll
        taken.append(hours)
    return [h for s in reversed(taken) for h in s]
