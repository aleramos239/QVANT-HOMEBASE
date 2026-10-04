"""Futures contract symbols, as Tradovate names them.

  Tradovate:    root + month-letter + year-digit(s)   e.g. "ESH6", "MNQM26"

CME futures month codes: F G H J K M N Q U V X Z (Jan..Dec, skipping I/L/O).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

MONTH_CODES = "FGHJKMNQUVXZ"                       # index 0 == January
CODE_TO_MONTH = {c: i + 1 for i, c in enumerate(MONTH_CODES)}
MONTH_TO_CODE = {i + 1: c for i, c in enumerate(MONTH_CODES)}

_TRADOVATE_RE = re.compile(r"^([A-Z0-9]+?)([FGHJKMNQUVXZ])(\d{1,2})$")


def _resolve_year(digits: str) -> int:
    """Expand a 1- or 2-digit contract year to a full year near today."""
    now = datetime.now(timezone.utc).year
    if len(digits) >= 2:
        return 2000 + int(digits[-2:])
    d = int(digits)
    base = now - (now % 10)        # start of current decade, e.g. 2020
    year = base + d
    if year < now - 1:             # a digit pointing into the recent past rolls forward
        year += 10
    return year


def parse_tradovate_symbol(symbol: str) -> tuple[str, int, int]:
    """('ESH6') -> ('ES', 3, 2026). Raises ValueError on an unrecognized symbol."""
    m = _TRADOVATE_RE.match(symbol.strip().upper())
    if not m:
        raise ValueError(f"not a Tradovate futures symbol: {symbol!r}")
    root, code, year_digits = m.group(1), m.group(2), m.group(3)
    return root, CODE_TO_MONTH[code], _resolve_year(year_digits)


def to_tradovate(symbol: str) -> str:
    """Normalize any accepted spelling to Tradovate's native ORDER form, which
    uses a SINGLE year digit for near-dated contracts: 'MNQM26' and 'MNQM6' both
    -> 'MNQM6'. Tradovate's order/placeorder rejects the 2-digit year, so every
    symbol handed to its WebSocket must pass through here first. A symbol that
    isn't a recognizable futures contract is returned unchanged (defensive — the
    adapter must not mangle anything unexpected)."""
    try:
        root, month, year = parse_tradovate_symbol(symbol)
    except (ValueError, TypeError, AttributeError):
        return symbol
    return f"{root}{MONTH_TO_CODE[month]}{year % 10}"


def resolve_contract(symbol: str) -> str:
    """Canonical root OR explicit contract -> a TRADABLE Tradovate contract.

    "NQ" -> "NQZ6" (front month), "NQZ6" -> "NQZ6" (unchanged).
    Order endpoints need a real contract: a bare product root is rejected
    with a generic "Access is denied", which looks exactly like a
    permissions problem and is not one.
    """
    s = to_tradovate(symbol)
    if not any(ch.isdigit() for ch in s):
        s = front_month(s)
    return s


QUARTERLY = (3, 6, 9, 12)
MONTHLY = tuple(range(1, 13))
# Roots that do not roll on a 3rd Friday: (active months, roll day). The
# contract stays front while today < that day of the month BEFORE its
# contract month. Verified by volume 2026-09-22: GCZ6 124k vs GCV6 4k;
# SIZ6 33k; HGZ6 37k vs HGH7 1k; ZNZ6 2.3M vs ZNH7 2; CLX6 307k vs CLV6 11k
# (Oct crude expires ~the 22nd of Sept, volume leaves it a week earlier);
# NGX6 103k vs NGV6 93k mid-roll on the 22nd.
CYCLE_ROLL = {
    "GC": ((2, 4, 6, 8, 12), 24), "MGC": ((2, 4, 6, 8, 12), 24),
    "SI": ((3, 5, 7, 9, 12), 24), "SIL": ((3, 5, 7, 9, 12), 24),
    "HG": ((3, 5, 7, 9, 12), 24), "MHG": ((3, 5, 7, 9, 12), 24),
    "ZN": (QUARTERLY, 24), "ZB": (QUARTERLY, 24), "ZF": (QUARTERLY, 24),
    "CL": (MONTHLY, 15), "MCL": (MONTHLY, 15),
    "NG": (MONTHLY, 22), "MNG": (MONTHLY, 22),
}


def _third_friday(year: int, month: int):
    from datetime import date, timedelta
    d = date(year, month, 15)          # 3rd Friday is always the 15th-21st
    return d + timedelta(days=(4 - d.weekday()) % 7)


# CME crypto: monthly contracts expiring on the contract month's LAST Friday;
# the volume moves to the next month 1-3 days before (59 BTC rolls 2021-26,
# median 1). Front while today < that Friday minus this many days.
LAST_FRIDAY_ROLL = {"BTC": 2, "MBT": 2, "ETH": 2, "MET": 2}


def _last_friday(year: int, month: int):
    from datetime import date, timedelta
    d = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)   # the month's last day
    return d - timedelta(days=(d.weekday() - 4) % 7)


def front_month(root: str, today=None) -> str:
    """Front contract for a root, e.g. front_month("NQ") -> "NQZ6".
    Index roots: quarterlies, rolled one week before the 3rd-Friday expiry
    (the volume roll). CYCLE_ROLL roots (metals, treasuries, energy): their
    own months, rolled on a fixed day of the month before the contract
    month. Crypto (LAST_FRIDAY_ROLL): monthly, rolled `lead` days before the
    last-Friday expiry. Never a dying contract."""
    from datetime import date, timedelta
    today = today or date.today()
    lead = LAST_FRIDAY_ROLL.get(root.upper())
    if lead is not None:
        y, m = today.year, today.month
        for _ in range(3):
            if today < _last_friday(y, m) - timedelta(days=lead):
                return f"{root}{MONTH_TO_CODE[m]}{y % 10}"
            y, m = (y, m + 1) if m < 12 else (y + 1, 1)
        raise ValueError(f"no front month found for {root!r}")
    year = today.year
    cycle, roll_day = CYCLE_ROLL.get(root.upper(), (QUARTERLY, None))
    for _ in range(3):                 # scan up to ~15 months ahead
        for m in cycle:
            if (year, m) < (today.year, today.month):
                continue
            if roll_day is not None:
                py, pm = (year, m - 1) if m > 1 else (year - 1, 12)
                still_front = today < date(py, pm, roll_day)
            else:
                still_front = today < _third_friday(year, m) - timedelta(days=7)
            if still_front:
                return f"{root}{MONTH_TO_CODE[m]}{year % 10}"
        year += 1
    raise ValueError(f"no front month found for {root!r}")
