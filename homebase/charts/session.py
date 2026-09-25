"""CME session maths for the chart engine (and later the backtester).

Session D runs 18:00 ET on D-1 -> 17:00 ET on D (Monday's opens Sunday
18:00) — the convention of homebase.ticks.session_bounds, reused here.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from zoneinfo import ZoneInfo

from ..ticks import session_bounds

ET = ZoneInfo("America/New_York")
RTH_OPEN = dt.time(9, 30)
_DAY = dt.timedelta(days=1)


def session_date(ts_ms: int) -> dt.date:
    """The session a trade at ts_ms belongs to."""
    t = dt.datetime.fromtimestamp(ts_ms / 1000, ET)
    d = t.date() + _DAY if t.time() >= dt.time(18, 0) else t.date()
    while d.weekday() >= 5:
        d += _DAY
    return d


@lru_cache(maxsize=4096)
def session_range_ms(d: dt.date) -> tuple[int, int]:
    """(open, close) of session d in epoch ms."""
    s, e = session_bounds(d)
    return int(s.timestamp() * 1000), int(e.timestamp() * 1000)


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
