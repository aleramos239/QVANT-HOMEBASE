"""CME session maths for the chart engine (and later the backtester).

Session D runs 18:00 ET on D-1 -> 17:00 ET on D (Monday's opens Sunday
18:00) — the convention of homebase.ticks.session_bounds, reused here. A
24/7 root (CME crypto since 2026-05-30) has a session EVERY day, weekends
included: 18:00 ET on D-1 -> 18:00 ET on D. The open is 18:00 either way,
so bar anchoring, the ETH VWAP reset and the levels read the same.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from zoneinfo import ZoneInfo

from ..ticks import session_bounds

ET = ZoneInfo("America/New_York")
RTH_OPEN = dt.time(9, 30)
_DAY = dt.timedelta(days=1)


ALWAYS_OPEN = frozenset({"BTC", "MBT", "ETH", "MET"})   # CME crypto: 24/7 since 2026-05-30


def always_open(root: str | None) -> bool:
    return (root or "").upper() in ALWAYS_OPEN


def session_date(ts_ms: int, root: str | None = None) -> dt.date:
    """The session a trade at ts_ms belongs to. Classic roots file a weekend
    print into Monday; 24/7 roots have their own weekend sessions."""
    t = dt.datetime.fromtimestamp(ts_ms / 1000, ET)
    d = t.date() + _DAY if t.time() >= dt.time(18, 0) else t.date()
    if not always_open(root):
        while d.weekday() >= 5:
            d += _DAY
    return d


@lru_cache(maxsize=4096)
def session_range_ms(d: dt.date, root: str | None = None) -> tuple[int, int]:
    """(open, close) of session d in epoch ms."""
    if always_open(root):
        s = dt.datetime.combine(d - _DAY, dt.time(18, 0), ET)
        e = dt.datetime.combine(d, dt.time(18, 0), ET)
    else:
        s, e = session_bounds(d)
    return int(s.timestamp() * 1000), int(e.timestamp() * 1000)


def split_by_session(root: str | None, a_ms: int, b_ms: int) -> list[tuple[dt.date, int, int]]:
    """[a_ms, b_ms) cut into (session date, start, end) pieces, oldest first,
    each clipped to its session. Time in no session (a classic root's 17:00
    hour and weekend) is in no piece."""
    out = []
    d = session_date(a_ms, root)
    while True:
        s0, s1 = session_range_ms(d, root)
        if s0 >= b_ms:
            return out
        if max(a_ms, s0) < min(b_ms, s1):
            out.append((d, max(a_ms, s0), min(b_ms, s1)))
        nxt = dt.datetime.combine(d, dt.time(18, 0), ET)      # the next session opens at 18:00 on d
        d = session_date(int(nxt.timestamp() * 1000), root)


def is_rth(ts_ms: int, session: str) -> bool:
    """True from 09:30 ET on the session's own calendar day."""
    t = dt.datetime.fromtimestamp(ts_ms / 1000, ET)
    return t.date().isoformat() == session and t.time() >= RTH_OPEN


@lru_cache(maxsize=65536)
def _et_offset_s(hour: int) -> int:
    return int(dt.datetime.fromtimestamp(hour * 3600, ET).utcoffset().total_seconds())


def et_wall_s(ts_ms: int) -> int:
    """ts as ET wall-clock seconds — for a chart axis that displays UTC."""
    s = ts_ms // 1000
    return s + _et_offset_s(s // 3600)
