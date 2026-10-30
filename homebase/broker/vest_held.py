"""Vest held stop entries, the loss-floor guard and the slippage cap (pure parts; the adapter wires them in vest.py).

Vest has no stop orders for entries: Homebase holds them here and fires a market order when the CME price trades the
level. The book is saved whole on every change (`homebase/.state/vest_held_<account>.json`), with the day-start equity
of the daily loss floor beside it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ..core.jsonio import read_dict, write_json
from .paper import root_of

if TYPE_CHECKING:
    from ..data.feed import Bar

PRICE_ROOT = {"MNQ": "NQ"}          # one price: an MNQ entry fires off NQ pushes and the other way round


def _proot(root: str) -> str:
    return PRICE_ROOT.get(root, root)


@dataclass
class HeldEntry:
    id: str
    symbol: str
    side: str                        # "Buy" | "Sell"
    qty: int                         # contracts
    level: float                     # CME price
    sl_pts: float
    tp_pts: Optional[float]
    day: str                         # desk day (rolls at 18:00 ET)
    oco_group: Optional[str]


def reached(side: str, level: float, price: float) -> bool:
    return price >= level if side == "Buy" else price <= level


class HeldBook:
    def __init__(self, path: Path):
        self.path = path
        d = read_dict(path)
        self.entries: list[HeldEntry] = []
        for e in d.get("entries") or []:
            try:
                self.entries.append(HeldEntry(**e))
            except TypeError:        # an unreadable row is never fired
                continue
        self.day_start: dict = d.get("day_start") or {}
        self._last: dict[str, tuple] = {}            # price root -> (bar start, high, low, close) of the last push

    def save(self) -> None:
        write_json(self.path, {"entries": [asdict(e) for e in self.entries], "day_start": self.day_start})

    def get(self, id: str) -> Optional[HeldEntry]:
        return next((e for e in self.entries if e.id == id), None)

    def add(self, e: HeldEntry) -> None:
        self.entries.append(e)
        self.save()

    def drop(self, id: str) -> Optional[HeldEntry]:
        e = self.get(id)
        if e is not None:
            self.entries.remove(e)
            self.save()
        return e

    def drop_group(self, group: Optional[str]) -> list[HeldEntry]:
        out = [e for e in self.entries if group is not None and e.oco_group == group]
        if out:
            self.entries = [e for e in self.entries if e not in out]
            self.save()
        return out

    def last_close(self, root: str) -> Optional[float]:
        last = self._last.get(_proot(root))
        return last[3] if last else None

    def crossed(self, root: str, bar: "Bar") -> list[HeldEntry]:
        """Entries this push trades: a Buy when the high rises to the level (a higher high than the last push of the
        same bar, or a new bar's high), a Sell on the low. Nearest to where price stood first, at most one per
        oco_group. Nothing is removed here (the caller drops what it fires or skips)."""
        r = _proot(root)
        last = self._last.get(r)
        self._last[r] = (bar.ts, bar.h, bar.l, bar.c)
        same = last is not None and last[0] == bar.ts
        ref = last[3] if same else bar.o
        hits = [e for e in self.entries if _proot(root_of(e.symbol)) == r and (
            (e.side == "Buy" and bar.h >= e.level and not (same and bar.h <= last[1])) or
            (e.side == "Sell" and bar.l <= e.level and not (same and bar.l >= last[2])))]
        out, groups = [], set()
        for e in sorted(hits, key=lambda e: abs(e.level - ref)):
            if e.oco_group is None or e.oco_group not in groups:
                out.append(e)
                groups.add(e.oco_group)
        return out

    def restore(self, today: str, last_price: float) -> list[HeldEntry]:
        """After a restart: keep only today's entries whose level the price has not reached."""
        keep = [e for e in self.entries if e.day == today and not reached(e.side, e.level, last_price)]
        if len(keep) != len(self.entries):
            self.entries = keep
            self.save()
        return list(keep)


def floor_room(equity: float, floors: dict, open_risk: float) -> Optional[float]:
    """Dollars a new entry may risk above the higher of the two floors (max drawdown; day-start equity - daily loss).
    None = no floor known, or a daily limit with no day-start equity: refuse (fail closed)."""
    lines = []
    if (floors or {}).get("max_drawdown_equity") is not None:
        lines.append(float(floors["max_drawdown_equity"]))
    if (floors or {}).get("daily_loss") is not None:
        if floors.get("day_start_equity") is None:
            return None
        lines.append(float(floors["day_start_equity"]) - float(floors["daily_loss"]))
    return equity - open_risk - max(lines) if lines else None


def slip_ok(level: float, perp_price: float, side: str, sl_pts: float, slip_frac: float) -> bool:
    """False when NQ-PERP is already more than `slip_frac` of the stop distance past the level."""
    past = perp_price - level if side == "Buy" else level - perp_price
    return past <= sl_pts * slip_frac
