"""The per-minute volume of the trade dates before a date: what a strategy reads as `ctx.minute_volume`
(Strategy.needs_minute_volume, 2026-10-21) -- the feed an RVOL rule compares a bar's volume with.

    minutes(tape)                           -> array('q') [NMIN]: ONE tape's volume per ET clock minute
    deltas(tape)                            -> array('q') [NMIN]: its buy minus sell volume per minute (backtest/sides.py)
    prior(store, root, d, n, cache=None, delta=False)
                                            -> [{"date": "YYYY-MM-DD", "vol": None or [NMIN numbers]}, ...], oldest first;
                                               delta=True (Strategy.needs_delta) adds "delta": None or [NMIN numbers]

vol[i] = the volume traded in the ET minute that starts at 18:00 ET of the evening before the date + i minutes (index 0 =
18:00 the evening before, NMIN - 1 = 16:59 ET of the date), every print of that date's own tape, whatever its contract (no roll
stop, unlike ctx.hourly). The research engine's minute-volume cache, the same minutes and the same sums
(research/edge-library/engine/families/blocks.py MIN0 / NMIN / minute_volume).

The dates are ctx.daily's calendar: the n trade dates before d that have a daily bar (store.daily, as runner.execute and
labrun/host.daily_bars read them), whether or not the strategy needs_daily. vol None = that date's tape did not load. Today's
minutes are never in it: nothing of d or after is read. At most MAX_SESSIONS dates.
"""
from __future__ import annotations

import datetime as dt
from array import array
from bisect import bisect_left

from .tape import et_ns

MIN_NS = 60 * 1_000_000_000
MIN0, NMIN = -360, 1380                 # minutes after 00:00 ET of index 0 (18:00 the evening before), minutes kept (to 17:00)
MAX_SESSIONS = 30
LOOKBACK = dt.timedelta(days=60)        # calendar days searched for MAX_SESSIONS dates


def minutes(tape) -> array:
    """The tape's volume per ET clock minute, index 0 = 18:00 ET of the evening before tape.date. The tape is in time order
    (TapeStore's stable sort), so each minute is one slice."""
    t0 = et_ns(tape.date, "00:00") + MIN0 * MIN_NS            # the engine's origin: 00:00 ET of the date - 6 h
    cut = [bisect_left(tape.ts, t0 + i * MIN_NS) for i in range(NMIN + 1)]
    sz = tape.size
    return array("q", (sum(sz[a:b]) for a, b in zip(cut, cut[1:])))


def _cuts(tape) -> list:
    t0 = et_ns(tape.date, "00:00") + MIN0 * MIN_NS            # the engine's origin: 00:00 ET of the date - 6 h
    return [bisect_left(tape.ts, t0 + i * MIN_NS) for i in range(NMIN + 1)]


def deltas(tape) -> array:
    """The tape's buy minus sell volume per ET clock minute (the minutes of minutes()), by its prints' sides (Tape.sides)."""
    cut, sz, sd = _cuts(tape), tape.size, tape.sides()
    return array("q", (sum(sz[j] * sd[j] for j in range(a, b)) for a, b in zip(cut, cut[1:])))


def prior(store, root: str, d: dt.date, n: int, cache: dict | None = None, delta: bool = False) -> list[dict]:
    """The minute volume of the n trade dates before d, oldest first (module docstring); delta=True: each row also carries
    "delta". store: a TapeStore (sessions / daily / load). cache: {date: (file stamp, volume, delta or None)} kept by the caller
    across days."""
    n = max(0, min(int(n), MAX_SESSIONS))
    if not n:
        return []
    cache = {} if cache is None else cache
    out: list[dict] = []
    for x in reversed([s for s in store.sessions(root, d - LOOKBACK, d) if s < d]):
        if len(out) == n:
            break
        hit = cache.get(x)
        if hit is None and store.daily(root, x) is None:
            continue                                 # no daily bar: not a date of ctx.daily
        stamp = _stamp(store, root, x)
        if hit is not None and stamp is not None and hit[0] == stamp and (not delta or hit[2] is not None):
            v, dl = hit[1], hit[2]
        else:
            tape = store.load(root, x) if stamp is not None else None
            v = minutes(tape) if tape is not None else None
            dl = deltas(tape) if delta and tape is not None else None
            if v is not None:                        # a date whose tape did not load is read again next time (not cached)
                cache[x] = (stamp, v, dl)
        row = {"date": x.isoformat(), "vol": None if v is None else v.tolist()}
        if delta:
            row["delta"] = None if dl is None else dl.tolist()
        out.append(row)
    return out[::-1]


def _stamp(store, root: str, x: dt.date):
    """The identity of date x's archive file (name, mtime, size: TapeStore._fresh's test), or None without one. A cached day
    is used only while its file is unchanged: the tick job keeps merging a session's file for a day or two after its close."""
    got = store.pick(root, x)
    if got is None:
        return None
    st = got[0].stat()
    return got[0].name, st.st_mtime_ns, st.st_size
