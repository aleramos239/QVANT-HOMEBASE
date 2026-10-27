"""Who started each print -- the aggressor side of a tape (owner, 2026-10-24: live delta for the Desk).

order_sides(ts, px)                      -> array('b'): +1 buy, -1 sell, 0 unknown (only before the first price change)
quote_sides(src, n)                      -> array('b') by the quote rule, when the archive file recorded quotes; else None
split_delta(ts, size, side, lo, hi, bars) gives each bar `buy` / `sell` volume (Strategy.needs_delta)

THE RULE is the flow builder's (research/flow.py, ~/futures_derived/flow_tape, the data every delta idea of the research engine was
tested on), restated here because that builder is gone. For a file the desk recorded WITH quotes (bid / ask on most prints: the
desk's own recordings since 2026-09-23) the builder used the quotes, and so does the chart service live (homebase/charts/tick.py: at
or above the ask = buy, at or below the bid = sell, else the tick rule): quote_sides does the same, so the tester, the earlier days a
Desk strategy compares with and the live bars are one measure. For the rest (order_sides): prints that share one ts_ns are ONE
aggressor order. An order that walks price (its last print differs from its first) took that way: up = buy. Otherwise the tick rule
against the previous order's last price; unchanged = the previous order's side, carried forward. It matched flow_tape print for
print on 30 random NQ days (2026-10-24).
"""
from __future__ import annotations

import csv
import gzip
import zlib
from array import array
from bisect import bisect_left
from pathlib import Path

from ..core.tick import SideClassifier

PEEK = 1000                                    # data rows read to tell a quoted file from one without quotes


def order_sides(ts, px) -> array:
    """The side of every print of a tape in time order (module docstring)."""
    n = len(ts)
    out = array("b", bytes(n))
    i, last_px, last_sd = 0, None, 0
    while i < n:
        j, t = i + 1, ts[i]
        while j < n and ts[j] == t:
            j += 1
        p0, p1 = px[i], px[j - 1]
        if p1 != p0:
            sd = 1 if p1 > p0 else -1
        elif last_px is None:
            sd = 0
        elif p0 != last_px:
            sd = 1 if p0 > last_px else -1
        else:
            sd = last_sd
        if sd:
            for k in range(i, j):
                out[k] = sd
        last_px, last_sd, i = p1, sd, j
    return out


def quote_sides(src: Path, n: int) -> array | None:
    """The sides of the n prints of a tape made from archive file `src`, by the chart service's quote rule in the file's order and
    then put in the tape's order (TapeStore's stable sort by ts) -- or None: the file's first PEEK prints are not mostly quoted
    (most of the archive: the backfill has no quotes), or it no longer lines up with the tape. Rows are read as read_archive_csv
    reads them, so the k-th row kept is the k-th print of the tape before its sort."""
    ts, sides, quoted, rows = [], array("b"), 0, 0
    clf = SideClassifier()
    try:
        with gzip.open(src, "rt", newline="") as fh:
            rd = csv.reader(fh)
            head = next(rd, None) or []
            ix = {k: i for i, k in enumerate(head)}
            if "bid" not in ix or "ask" not in ix:
                return None
            ip, isz, ims, ins, ib, ia, w = ix["price"], ix["size"], ix["ts_ms"], ix.get("ts_ns"), ix["bid"], ix["ask"], len(head)
            for r in rd:
                if len(r) != w or r[0] == head[0]:
                    continue
                t = r[ins] if ins is not None else ""
                ts.append(int(t) if t else int(r[ims]) * 1_000_000)
                b, a = (float(r[ib]) if r[ib] else None), (float(r[ia]) if r[ia] else None)
                quoted += b is not None and a is not None
                rows += 1
                if rows == PEEK and quoted * 2 < rows:
                    return None
                sides.append(clf.side(float(r[ip]), b, a))
    except (EOFError, zlib.error, OSError):
        pass
    if not rows or quoted * 2 < rows or len(sides) != n:
        return None
    if any(ts[i] > ts[i + 1] for i in range(len(ts) - 1)):           # the tape is the stable sort of these rows by ts
        order = sorted(range(len(ts)), key=ts.__getitem__)
        sides = array("b", (sides[i] for i in order))
    return sides


def split_delta(ts, size, side, lo: int, hi: int, bars: list) -> None:
    """Give each bar `buy` / `sell`: the volume of its prints in [start_ns, end_ns) by `side` (prints of side 0 count for
    neither). Set as plain attributes, as engine.split_flow does, so a bar's fields, `asdict` and equality stay as they were."""
    k = lo
    for b in bars:
        k0 = bisect_left(ts, b.start_ns, k, hi)
        k1 = bisect_left(ts, b.end_ns, k0, hi)
        buy = sell = 0
        for j in range(k0, k1):
            s = side[j]
            if s > 0:
                buy += size[j]
            elif s < 0:
                sell += size[j]
        b.buy, b.sell = buy, sell
        k = k1
