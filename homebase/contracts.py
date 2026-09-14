"""Futures contract specs — point value and tick size per root.

Used by the shadow ledger (to turn a price move into a dollar P&L) and by the
protective-bracket math (to turn a stop/target distance in *ticks* into an
absolute price). Keyed by the Tradovate-native root, since canonical symbols in
this app are Tradovate-native (see `symbols.py`).

`point_value` is USD per 1.00 of price movement, per single contract. So the
realized P&L of closing `qty` contracts is::

    pnl = (exit_price - entry_price) * point_value * qty        # for a long
        = (entry_price - exit_price) * point_value * qty        # for a short

`tick_value` (the dollar value of one minimum tick) falls out as
``point_value * tick_size``.

Only the contracts prop traders actually trade are enumerated. An unknown root
returns a spec with ``known=False`` and ``point_value=None`` so callers can
degrade gracefully (track the position in *points* and flag the dollar figure
as unavailable) rather than reporting a wrong number.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# root -> (point_value_usd, tick_size)
# point_value = USD per 1.00 price move, per contract.
_SPECS: dict[str, tuple[float, float]] = {
    # --- equity index (CME) ---
    "ES": (50.0, 0.25),    "MES": (5.0, 0.25),     # S&P 500 e-mini / micro
    "NQ": (20.0, 0.25),    "MNQ": (2.0, 0.25),     # Nasdaq-100 e-mini / micro
    "YM": (5.0, 1.0),      "MYM": (0.5, 1.0),      # Dow e-mini / micro
    "RTY": (50.0, 0.10),   "M2K": (5.0, 0.10),     # Russell 2000 e-mini / micro
    "NKD": (5.0, 5.0),                              # Nikkei 225 ($)
    # --- energy (NYMEX) ---
    "CL": (1000.0, 0.01),  "MCL": (100.0, 0.01),   # WTI crude full / micro
    "QM": (500.0, 0.025),                           # crude e-mini
    "NG": (10000.0, 0.001), "MNG": (2500.0, 0.001),  # natural gas / micro
    "RB": (42000.0, 0.0001),                        # RBOB gasoline
    "HO": (42000.0, 0.0001),                        # heating oil
    # --- metals (COMEX) ---
    "GC": (100.0, 0.10),   "MGC": (10.0, 0.10),    # gold full / micro
    "SI": (5000.0, 0.005), "SIL": (1000.0, 0.005),  # silver full / micro
    "HG": (25000.0, 0.0005), "MHG": (2500.0, 0.0005),  # copper full / micro
    "PL": (50.0, 0.10),    "PA": (100.0, 0.10),    # platinum / palladium
    # --- interest rates (CBOT) ---
    "ZB": (1000.0, 1.0 / 32.0),    # 30y T-bond  (32nds)
    "ZN": (1000.0, 1.0 / 64.0),    # 10y T-note  (half-32nds)
    "ZF": (1000.0, 1.0 / 128.0),   # 5y T-note   (quarter-32nds)
    "ZT": (2000.0, 1.0 / 256.0),   # 2y T-note
    # --- FX (CME) ---
    "6E": (125000.0, 0.00005), "M6E": (12500.0, 0.0001),   # euro / micro
    "6B": (62500.0, 0.0001),   "6A": (100000.0, 0.0001),   # pound / aussie
    "6C": (100000.0, 0.00005), "6J": (12500000.0, 0.0000005),  # cad / yen
    "6S": (125000.0, 0.0001),  "6N": (100000.0, 0.0001),   # franc / kiwi
    # --- agriculture (CBOT, quoted in cents/bushel) ---
    "ZC": (50.0, 0.25), "ZW": (50.0, 0.25), "ZS": (50.0, 0.25),  # corn/wheat/soy
    # --- crypto (CME) ---
    "MBT": (0.1, 5.0),   # micro bitcoin ($0.10 per $1 of BTC)
    "MET": (0.1, 0.5),   # micro ether
}

_ROOT_RE = re.compile(r"^([A-Z0-9]+?)([FGHJKMNQUVXZ])(\d{1,2})$")


@dataclass(frozen=True)
class ContractSpec:
    root: str
    point_value: Optional[float]   # USD per 1.00 price move; None if unknown
    tick_size: float
    known: bool = True

    @property
    def tick_value(self) -> Optional[float]:
        if self.point_value is None:
            return None
        return self.point_value * self.tick_size


# Sensible fallback tick for an unknown root, so tick math still produces a
# round-ish price. P&L stays None (unknown) so it's never silently wrong.
_UNKNOWN = ContractSpec(root="?", point_value=None, tick_size=0.25, known=False)


def root_of(symbol: str) -> str:
    """Extract the root from a Tradovate-native symbol or a bare root.

    'ESH26' -> 'ES', 'MNQM6' -> 'MNQ', 'ES' -> 'ES'. Best-effort: strips a
    trailing <month-letter><year-digits> suffix when present.
    """
    s = str(symbol or "").strip().upper()
    m = _ROOT_RE.match(s)
    if m:
        return m.group(1)
    return s


def spec_for(symbol: str) -> ContractSpec:
    """ContractSpec for a symbol or root; `known=False` spec if unrecognized."""
    root = root_of(symbol)
    pv_ts = _SPECS.get(root)
    if pv_ts is None:
        return _UNKNOWN
    point_value, tick_size = pv_ts
    return ContractSpec(root=root, point_value=point_value, tick_size=tick_size)


def point_value(symbol: str) -> Optional[float]:
    """USD per 1.00 price move for one contract, or None if the root is unknown."""
    return spec_for(symbol).point_value


def tick_size(symbol: str) -> float:
    return spec_for(symbol).tick_size


def realized_pnl(symbol: str, side: str, qty: int,
                 entry_price: float, exit_price: float) -> Optional[float]:
    """Dollar P&L of closing `qty` of a position opened on `side` ('Buy'|'Sell').

    Returns None when the contract's point value is unknown (caller should treat
    the dollar figure as unavailable). A 'Buy' (long) profits when price rises.
    """
    pv = point_value(symbol)
    if pv is None or entry_price is None or exit_price is None:
        return None
    move = (exit_price - entry_price) if side.lower() == "buy" else (entry_price - exit_price)
    return move * pv * abs(int(qty))


def ticks_to_delta(symbol: str, ticks: float) -> float:
    """Price distance for `ticks` minimum increments. 4 ticks of ES -> 1.00."""
    return float(ticks) * tick_size(symbol)


def round_to_tick(symbol: str, price: float) -> float:
    """Snap a price to the contract's tick grid (avoids 'invalid price' rejects)."""
    ts = tick_size(symbol)
    if not ts:
        return float(price)
    return round(round(float(price) / ts) * ts, 10)
