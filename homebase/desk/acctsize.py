"""The size ONE booked account sends for a Lab entry (per-account settings 2, owner 2026-10-29). Pure arithmetic:
imports nothing of the desk, so labdesk (and anything else) may import it.

A row with no `size` is the strategy's own: its `qty`, or for an own_size strategy the order's own size up to it.
A set row wins over the strategy's own size: `contracts` = exactly `qty`; `risk` = round(risk_usd / (stop x point
value)), rounded down when that puts more than 10 % over, never more dollars than the strategy's max_risk_usd. Both
are held to the row's `most`, or -- with the box removed -- to BACKSTOP_MINIS minis' worth. Not one contract, or a
stop that cannot be measured: (None, ROW_NO_SIZE), that account sits the trade out (fail closed)."""
from __future__ import annotations

import math

ROW_NO_SIZE = "No contract fits this account's risk for this stop."
BACKSTOP_MINIS = 10                      # an order with no Most contracts box: at most 10 minis' worth (100 micros)
OVER_MOST = 1.10                         # an order never rounds up to more than 10 % over its dollars at risk


def row_size(row: dict, dists: list, pv: float, full_pv: float, own_qty: int | None,
             cap_usd: float) -> tuple[int | None, str | None]:
    """(contracts, None) or (None, ROW_NO_SIZE). `dists`: the stop distance of each leg (a pair: both, the wider
    sizes it); `pv`: a point of the contract the orders go to; `full_pv`: a point of the mini; `own_qty`: the
    order's own size (own_size strategies) or None; `cap_usd`: the strategy's max_risk_usd (0 = not set)."""
    size = row.get("size")
    if size is None:
        q = int(row["qty"])
        return (q if own_qty is None else min(q, int(own_qty))), None
    try:
        if not pv or not full_pv:
            return None, ROW_NO_SIZE
        top = int(row["most"]) if row.get("most") is not None else max(1, int(BACKSTOP_MINIS * full_pv / pv))
        if size == "contracts":
            n = int(row["qty"])
        elif size == "risk":
            dist = max(dists)
            if not (math.isfinite(dist) and dist > 0):
                return None, ROW_NO_SIZE
            per, risk = dist * pv, float(row["risk_usd"])
            n = round(risk / per)
            if n * per > risk * OVER_MOST:       # rounding up a big contract (1 NQ at $1,660 for $1,000) goes down
                n = int(risk // per)
            if cap_usd and cap_usd > 0:
                n = min(n, int(cap_usd // per))
        else:
            return None, ROW_NO_SIZE
    except (TypeError, ValueError, KeyError, ArithmeticError):
        return None, ROW_NO_SIZE
    return (None, ROW_NO_SIZE) if n < 1 else (min(n, top), None)


def most_default(pv: float, full_pv: float) -> int:
    """The Most contracts box's first value: 20 when the orders go to a micro, 2 when they go to a mini."""
    return 20 if pv < full_pv else 2
