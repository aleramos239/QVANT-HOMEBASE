"""Synthetic tick sessions for the chart-engine tests (no network, no real archive)."""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import io
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
D = dt.date(2026, 9, 24)                     # a Thursday session
FIELDS = ["ts_ms", "price", "size", "bid", "ask", "bid_size", "ask_size", "id"]


def session_ms(d: dt.date, hh: int, mm: int, ss: int = 0) -> int:
    """Epoch ms of an ET wall time in session d (hh >= 18 is the evening before)."""
    day = d - dt.timedelta(days=1) if hh >= 18 else d
    return int(dt.datetime.combine(day, dt.time(hh, mm, ss), ET).timestamp() * 1000)


def rows(start_ms: int, prices, step_ms: int = 1000, size=1, spread: float = 0.25,
         first_id: int = 1, sides=None) -> list[dict]:
    """One trade per price, step_ms apart. sides[i] = +1 trades at the ask,
    -1 at the bid (default: at the ask). size: int or a list per trade."""
    out = []
    for i, p in enumerate(prices):
        s = sides[i] if sides else 1
        bid, ask = (p - spread, p) if s > 0 else (p, p + spread)
        out.append({"ts_ms": start_ms + i * step_ms, "price": p,
                    "size": size[i] if isinstance(size, list) else size,
                    "bid": bid, "ask": ask, "bid_size": 5, "ask_size": 5, "id": first_id + i})
    return out


def write_gz(path: Path, rows_: list[dict], fields=FIELDS) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows_)
    path.write_bytes(gzip.compress(buf.getvalue().encode()))
    return path


def write_archive(base: Path, root: str, d: dt.date, contract: str, rows_: list[dict],
                  complete: bool = True, bid_ask: bool = True) -> Path:
    p = Path(base) / root / str(d.year) / f"{d.isoformat()}_{contract}.csv.gz"
    write_gz(p, rows_)
    man = {"root": root, "contract": contract, "session_date": d.isoformat(),
           "ticks": len(rows_), "complete": complete}
    if not bid_ask:
        man["bid_ask"] = False
    p.with_name(p.name[:-len(".csv.gz")] + ".json").write_text(json.dumps(man))
    return p


def weekdays_before(d: dt.date, n: int) -> list[dt.date]:
    """The n weekdays before d, oldest first (a classic root files weekend prints into Monday)."""
    out, x = [], d
    while len(out) < n:
        x -= dt.timedelta(days=1)
        if x.weekday() < 5:
            out.append(x)
    return out[::-1]
