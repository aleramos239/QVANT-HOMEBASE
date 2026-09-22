"""Cross-platform futures symbol mapping.

Each broker names the same contract differently. The leader emits its native
symbol; every follower translates it to its own platform's format.

  Tradovate:    root + month-letter + year-digit(s)   e.g. "ESH6", "MNQM26"
  NinjaTrader:  "root MM-YY"                           e.g. "ES 03-26"
  ProjectX:     "CON.F.US.<root>.<L><YY>"              e.g. "CON.F.US.EP.H26"

CME futures month codes: F G H J K M N Q U V X Z (Jan..Dec, skipping I/L/O).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

MONTH_CODES = "FGHJKMNQUVXZ"                       # index 0 == January
CODE_TO_MONTH = {c: i + 1 for i, c in enumerate(MONTH_CODES)}
MONTH_TO_CODE = {i + 1: c for i, c in enumerate(MONTH_CODES)}

# Roots that ProjectX (TopstepX) names differently from CME/Tradovate.
# Only the differences are listed; anything not here passes through unchanged.
PROJECTX_ROOT = {"ES": "EP", "NQ": "ENQ"}
PROJECTX_ROOT_INVERSE = {v: k for k, v in PROJECTX_ROOT.items()}

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


def to_canonical(symbol: str) -> str:
    """Normalize a Tradovate-native symbol to a stable canonical key with a
    2-digit year, so the same contract always compares equal regardless of how
    it was written. 'ESH6' and 'ESH26' both -> 'ESH26'."""
    root, month, year = parse_tradovate_symbol(symbol)
    return f"{root}{MONTH_TO_CODE[month]}{year % 100:02d}"


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
# Metals trade a different cycle and roll ahead of first notice (the last
# business day before the contract month), not on a 3rd Friday. The active
# months by volume (verified 2026-09-22: GCZ6 124k vs GCV6 4k; SIZ6 33k):
METALS = {"GC": (2, 4, 6, 8, 12), "MGC": (2, 4, 6, 8, 12),
          "SI": (3, 5, 7, 9, 12), "SIL": (3, 5, 7, 9, 12)}
METALS_ROLL_DAY = 24               # of the month BEFORE the contract month


def _third_friday(year: int, month: int):
    from datetime import date, timedelta
    d = date(year, month, 15)          # 3rd Friday is always the 15th-21st
    return d + timedelta(days=(4 - d.weekday()) % 7)


def front_month(root: str, today=None) -> str:
    """Front contract for a root, e.g. front_month("NQ") -> "NQZ6".
    Index roots: quarterlies, rolled one week before the 3rd-Friday expiry
    (the volume roll). Metals: their own cycle, rolled on the 24th of the
    month before the contract month. Never a dying contract."""
    from datetime import date, timedelta
    today = today or date.today()
    year = today.year
    cycle = METALS.get(root.upper(), QUARTERLY)
    for _ in range(3):                 # scan up to ~15 months ahead
        for m in cycle:
            if (year, m) < (today.year, today.month):
                continue
            if root.upper() in METALS:
                py, pm = (year, m - 1) if m > 1 else (year - 1, 12)
                still_front = today < date(py, pm, METALS_ROLL_DAY)
            else:
                still_front = today < _third_friday(year, m) - timedelta(days=7)
            if still_front:
                return f"{root}{MONTH_TO_CODE[m]}{year % 10}"
        year += 1
    raise ValueError(f"no front month found for {root!r}")
    """Tradovate-native -> NinjaTrader instrument string. 'ESH6' -> 'ES 03-26'."""
    root, month, year = parse_tradovate_symbol(symbol)
    return f"{root} {month:02d}-{year % 100:02d}"


_NINJATRADER_RE = re.compile(r"^([A-Z0-9]+)\s+(\d{2})-(\d{2})$")


def from_ninjatrader(instrument: str) -> str:
    """NinjaTrader instrument -> canonical Tradovate-native. 'ES 03-26' -> 'ESH26'.
    Raises ValueError if unrecognized."""
    m = _NINJATRADER_RE.match(instrument.strip().upper())
    if not m:
        raise ValueError(f"not a NinjaTrader instrument: {instrument!r}")
    root, mm, yy = m.group(1), int(m.group(2)), m.group(3)
    if not 1 <= mm <= 12:
        raise ValueError(f"bad month in NinjaTrader instrument: {instrument!r}")
    return f"{root}{MONTH_TO_CODE[mm]}{yy}"


def to_projectx(symbol: str) -> str:
    """Tradovate-native -> ProjectX contractId. 'ESH6' -> 'CON.F.US.EP.H26'."""
    root, month, year = parse_tradovate_symbol(symbol)
    px_root = PROJECTX_ROOT.get(root, root)
    return f"CON.F.US.{px_root}.{MONTH_TO_CODE[month]}{year % 100:02d}"


_PROJECTX_RE = re.compile(r"^CON\.F\.US\.([A-Z0-9]+)\.([FGHJKMNQUVXZ])(\d{2})$")


def from_projectx(contract_id: str) -> str:
    """ProjectX contractId -> canonical (Tradovate-native, 2-digit year).
    'CON.F.US.EP.H26' -> 'ESH26'. Raises ValueError if unrecognized."""
    m = _PROJECTX_RE.match(contract_id.strip().upper())
    if not m:
        raise ValueError(f"not a ProjectX contractId: {contract_id!r}")
    px_root, code, yy = m.group(1), m.group(2), m.group(3)
    root = PROJECTX_ROOT_INVERSE.get(px_root, px_root)
    return f"{root}{code}{yy}"


# Mini <-> micro contract families (CME index / commodity / FX). Lets an account
# copy the leader's instrument as its mini or micro sibling. Only families with a
# real sibling are listed; anything else has no micro (force-micro -> skip).
MINI_MICRO = {"ES": "MES", "NQ": "MNQ", "YM": "MYM", "RTY": "M2K", "CL": "MCL",
              "NG": "MNG", "GC": "MGC", "SI": "SIL", "HG": "MHG", "6E": "M6E"}
MICRO_MINI = {v: k for k, v in MINI_MICRO.items()}


def family_root(root: str, klass: str):
    """Map a contract root to the requested size class.

    klass "micro": mini root -> its micro; already-micro -> unchanged; a product
    with no micro -> None (caller skips the copy). klass "mini": micro root -> its
    mini; anything else -> unchanged (already the standard/mini size). klass
    "as_leader" (or anything else): unchanged."""
    r = (root or "").upper()
    if klass == "micro":
        if r in MINI_MICRO:
            return MINI_MICRO[r]
        if r in MICRO_MINI:
            return r
        return None
    if klass == "mini":
        return MICRO_MINI.get(r, r)
    return r


def swap_root(symbol: str, new_root: str) -> str:
    """Rebuild a Tradovate-native symbol with a different root, preserving the
    month code and year digits. 'NQH26' + 'MNQ' -> 'MNQH26'. A symbol that isn't a
    parseable futures contract is returned unchanged."""
    m = _TRADOVATE_RE.match(str(symbol or "").strip().upper())
    if not m:
        return symbol
    return f"{new_root}{m.group(2)}{m.group(3)}"
