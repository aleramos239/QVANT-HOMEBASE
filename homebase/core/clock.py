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
