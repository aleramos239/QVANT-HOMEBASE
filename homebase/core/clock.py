"""Clock and time-text helpers. ET is the one America/New_York zone (ZoneInfo caches it: the same object everywhere)."""
from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def utc_iso() -> str:
    """Now in UTC, ISO to the second: '2026-10-26T14:03:09+00:00'."""
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def epoch_ms(t: dt.datetime) -> int:
    """An aware datetime as epoch ms, truncated toward zero (int())."""
    return int(t.timestamp() * 1000)


def et_hms(ns: int) -> str:
    """Epoch ns as 'HH:MM:SS' ET; whole seconds by floor division (never rounded up)."""
    return dt.datetime.fromtimestamp(ns // 1_000_000_000, ET).strftime("%H:%M:%S")


def is_hhmm(v) -> bool:
    """A str '00:00'..'23:59', two digits each side."""
    return isinstance(v, str) and HHMM.fullmatch(v) is not None


def hhmm_minutes(hhmm: str) -> int:
    """'HH:MM' -> minutes after midnight. No check: give it a valid is_hhmm() string."""
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


# ---- the Desk day: 18:00 ET (the futures session's open) to 17:00 ET the next day (the close; 17:00-18:00 is the halt)
DESK_OPEN = "18:00"
DESK_CLOSE = "17:00"


def desk_minutes(hhmm: str) -> int:
    """'HH:MM' ET -> minutes into the Desk day: 18:00 = 0, midnight = 360, 09:30 = 930, 16:55 = 1375, 17:00 = 1380
    (the close; 17:01-17:59, the halt, read 1381-1439). Any two clock times of one Desk day order by it, across
    midnight. No check: give it a valid is_hhmm() string."""
    return (hhmm_minutes(hhmm) - hhmm_minutes(DESK_OPEN)) % 1440


def window_minutes(w) -> tuple[int, int] | None:
    """A session window as (start, end) minutes into the Desk day of its date: ["HH:MM", "HH:MM"] on the date itself,
    or ["-HH:MM", "HH:MM"] opening the evening before (labrun reads both). None when it does not read or does not fit
    one Desk day: an evening start before 18:00, a same-day start at/after 17:00, an end after 17:00, or end <= start."""
    if not (isinstance(w, (list, tuple)) and len(w) == 2 and isinstance(w[0], str) and is_hhmm(w[1])):
        return None
    eve = w[0].startswith("-")
    a = w[0][1:] if eve else w[0]
    if not is_hhmm(a) or (a < DESK_OPEN if eve else a >= DESK_CLOSE) or w[1] > DESK_CLOSE:     # (the end is on the date)
        return None
    s, e = desk_minutes(a), desk_minutes(w[1])
    return (s, e) if s < e else None
