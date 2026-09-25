"""A trade, and which side started it."""
from __future__ import annotations

from typing import NamedTuple, Optional

BUY, SELL = 1, -1


class Tick(NamedTuple):
    ts_ms: int
    price: float
    size: int
    side: int          # BUY: lifted the ask · SELL: hit the bid
    id: int = 0


def _num(v) -> Optional[float]:
    return None if v is None or v == "" else float(v)


class SideClassifier:
    """Aggressor side per trade. With a sane quote (bid <= ask): at/above the
    ask = buy, at/below the bid = sell. Inside the spread, no quote, or a
    crossed quote (the feed does send bid > ask) -> tick rule: up-tick buy,
    down-tick sell, unchanged -> the previous side. Sequential: feed trades
    in time order; resume from (last_price, last_side) to continue a tape."""

    def __init__(self, last_price: Optional[float] = None, last_side: int = BUY):
        self.last_price = last_price
        self.last_side = last_side

    def side(self, price: float, bid: Optional[float], ask: Optional[float]) -> int:
        if bid is not None and ask is not None and bid <= ask and (price >= ask or price <= bid):
            s = BUY if price >= ask else SELL
        elif self.last_price is None or price == self.last_price:
            s = self.last_side
        else:
            s = BUY if price > self.last_price else SELL
        self.last_price, self.last_side = price, s
        return s


def from_row(row: dict, clf: SideClassifier) -> Tick:
    """A raw tick row (archive CSV strings or the feed's numbers) -> Tick."""
    price = float(row["price"])
    return Tick(int(row["ts_ms"]), price, int(row["size"]),
                clf.side(price, _num(row.get("bid")), _num(row.get("ask"))),
                int(row.get("id") or 0))
