"""Daily tick archive: every trade (price, size, bid/ask at the trade) for
each root's front month, one gzip CSV per session, filed under
~/futures_ticks/<ROOT>/<YYYY>/<session-date>_<contract>.csv.gz + a .json
manifest.

The broker's md feed serves tick history only ~1-2 days back, so this runs
daily after the 17:00 ET session close and fetches the whole session by
paging backwards from the close (about 4,096 ticks a page). A run is
idempotent: sessions already on disk are skipped, so a run that was missed
(laptop asleep) catches up on the next one, as long as the buffer still
reaches. A session is recorded only once it is over.

The feed allows 180 chart requests per hour per login (learned 2026-09-22:
a 116-page burst drew "Rate limit exceeded" penalties for the next hour).
So pages are paced (~170/hour), a penalty reply is honored (wait p-time,
resend with its p-ticket), the run stops at a hard deadline before the
open, and it spends the LIVE login's md budget so the demo login that
drives the 9:30 feed is never penalized.

Session date D = 18:00 ET on D-1 -> 17:00 ET on D (Mon's starts Sunday).

    python -m homebase.ticks                # every complete, missing session
    python -m homebase.ticks --date 2026-09-22 --roots NQ,ES
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import gzip
import json
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config as config_mod
from . import symbols
from .broker.tradovate_ws import TradovateWS
from .marketdata import MD_DEMO, MD_LIVE
from .paths import state_dir

ET = ZoneInfo("America/New_York")
# priority order: if the 08:00 deadline cuts a night short, the important
# ones are done first
ROOTS = ("NQ", "ES", "YM", "RTY", "GC", "SI", "CL", "ZN", "NG", "HG")
ARCHIVE = Path.home() / "futures_ticks"
PAGE = 4096                 # the feed caps a tick request at about this
MAX_PAGES = 3000            # ~12M ticks — far above any session
SESSION_GRACE_MIN = 5       # record a session this long after its close
LOOKBACK_DAYS = 3           # sessions to check on every run
PAGE_INTERVAL_S = 21.0      # <= 171 requests/hour against the 180/hour limit
PENALTY_MAX = 6             # give up a session after this many penalties in a row
DEADLINE_ET = dt.time(8, 0)  # never still fetching this close to the open
FIELDS = ("ts_ms", "price", "size", "bid", "ask", "bid_size", "ask_size", "id")


def log(msg: str) -> None:
    print(f"[ticks] {dt.datetime.now(ET).strftime('%H:%M:%S')} {msg}", flush=True)


# ------------------------------------------------------------------ sessions
def session_bounds(date: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """(start, end) as aware ET datetimes: 18:00 the day before -> 17:00."""
    start = dt.datetime.combine(date - dt.timedelta(days=1), dt.time(18, 0), ET)
    end = dt.datetime.combine(date, dt.time(17, 0), ET)
    return start, end


def is_session_day(date: dt.date) -> bool:
    return date.weekday() < 5


def session_complete(date: dt.date, now: dt.datetime) -> bool:
    _, end = session_bounds(date)
    return now >= end + dt.timedelta(minutes=SESSION_GRACE_MIN)


def sessions_to_record(now: dt.datetime, days: int = LOOKBACK_DAYS) -> list[dt.date]:
    """Complete sessions within the lookback, oldest first."""
    today = now.astimezone(ET).date()
    out = [today - dt.timedelta(days=i) for i in range(days + 1)]
    return sorted(d for d in out if is_session_day(d) and session_complete(d, now))


def archive_path(root: str, date: dt.date, contract: str, base: Path = ARCHIVE) -> Path:
    return base / root / str(date.year) / f"{date.isoformat()}_{contract}.csv.gz"


# ------------------------------------------------------------------ fetching
def _unpack(packet: dict) -> list[dict]:
    """One chart packet -> tick rows. Prices ride as tick offsets from the
    packet's base price bp; timestamps as ms offsets from bt."""
    bp, bt, ts = packet.get("bp", 0), packet.get("bt", 0), packet.get("ts") or 0.0
    rows = []
    for t in packet.get("tks", []) or []:
        rows.append({
            "ts_ms": bt + t.get("t", 0),
            "price": round((bp + t.get("p", 0)) * ts, 6),
            "size": t.get("s"),
            "bid": round((bp + t["b"]) * ts, 6) if t.get("b") is not None else "",
            "ask": round((bp + t["a"]) * ts, 6) if t.get("a") is not None else "",
            "bid_size": t.get("bs", ""),
            "ask_size": t.get("as", ""),
            "id": t.get("id"),
        })
    return rows


class Penalty(Exception):
    """The feed answered with a rate-limit ticket instead of data."""

    def __init__(self, d: dict):
        super().__init__(str(d.get("p-message") or "rate limited"))
        self.ticket = d.get("p-ticket")
        self.wait_s = float(d.get("p-time") or 1)


async def fetch_page(ws: TradovateWS, contract: str, before_ms: int,
                     n: int = PAGE, timeout_s: float = 20.0,
                     ticket: str | None = None) -> list[dict]:
    """Up to n ticks ending at `before_ms` (inclusive), oldest first.
    Raises Penalty on a rate-limit reply (retry with its ticket)."""
    packets, done = [], asyncio.get_running_loop().create_future()

    def on(msg):
        if msg.get("e") != "chart":
            return
        for ch in (msg.get("d") or {}).get("charts", []) or []:
            if ch.get("tks"):
                packets.append(ch)
            if ch.get("eoh") and not done.done():
                done.set_result(True)

    ws.event_handlers.append(on)
    try:
        d = await ws.request("md/getChart", {
            "symbol": contract,
            "chartDescription": {"underlyingType": "Tick", "elementSize": 1,
                                 "elementSizeUnit": "UnderlyingUnits",
                                 "withHistogram": False},
            "timeRange": {
                "closestTimestamp": dt.datetime.fromtimestamp(
                    before_ms / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                "asMuchAsElements": n},
            **({"p-ticket": ticket} if ticket else {})})
        if isinstance(d, dict) and d.get("p-ticket"):
            raise Penalty(d)
        if not isinstance(d, dict) or d.get("realtimeId") is None:
            raise RuntimeError(f"{contract}: getChart refused: {d!r}")
        try:
            await asyncio.wait_for(done, timeout_s)
        except asyncio.TimeoutError:
            if not packets:
                raise RuntimeError(f"{contract}: no tick data before timeout")
        rt = (d or {}).get("realtimeId")
        if rt is not None:
            try:
                await ws.request("md/cancelChart", {"subscriptionId": rt})
            except Exception:  # noqa: BLE001 — best effort
                pass
    finally:
        ws.event_handlers.remove(on)
    rows = [r for p in packets for r in _unpack(p)]
    rows.sort(key=lambda r: (r["ts_ms"], r["id"] or 0))
    return rows


async def fetch_session(ws: TradovateWS, contract: str, start: dt.datetime,
                        end: dt.datetime, page_fn=None) -> tuple[list[dict], dict]:
    """Page backwards from the session close until the open (or the buffer
    runs dry). Returns (rows ascending, stats)."""
    page_fn = page_fn or fetch_page
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    before, seen, rows, pages, penalties = end_ms, set(), [], 0, 0
    last_req = 0.0
    while pages < MAX_PAGES:
        if deadline_passed():
            log(f"{contract}: deadline {DEADLINE_ET} ET — stopping this session here")
            break
        gap = PAGE_INTERVAL_S - (time.monotonic() - last_req)
        if pages and gap > 0:
            await sleep(gap)
        last_req = time.monotonic()
        if isinstance(ws, MDConn):
            sock = await ws.ensure()
        else:
            sock = ws
        try:
            page = await page_fn(sock, contract, before)
            penalties = 0
        except (RuntimeError, ConnectionError, OSError) as e:
            if isinstance(ws, MDConn) and "not connected" in str(e) and pages < MAX_PAGES:
                await sleep(2)                      # rebuilt on the next loop
                continue
            raise
        except Penalty as pen:
            penalties += 1
            if penalties > PENALTY_MAX:
                raise RuntimeError(f"{contract}: {penalties} penalties in a row — {pen}")
            log(f"{contract}: {pen} — waiting {pen.wait_s + 1:.0f}s, resending with its ticket")
            await sleep(pen.wait_s + 1)
            try:
                page = await page_fn(sock, contract, before, ticket=pen.ticket)
            except Penalty as again:
                await sleep(max(60.0, again.wait_s))    # budget gone: rest a minute
                continue
        pages += 1
        new = [r for r in page if r["id"] not in seen and r["ts_ms"] >= start_ms
               and r["ts_ms"] < end_ms + 1]
        if not page or not any(r["id"] not in seen for r in page):
            break                                   # buffer exhausted
        seen.update(r["id"] for r in page)
        rows.extend(new)
        earliest = page[0]["ts_ms"]
        if earliest < start_ms:
            break                                   # reached the open
        before = earliest if earliest < before else before - 1
    rows.sort(key=lambda r: (r["ts_ms"], r["id"] or 0))
    complete = bool(rows) and rows[0]["ts_ms"] - start_ms < 5 * 60 * 1000  # within 5 min of the open
    return rows, {"pages": pages, "complete": complete}


def deadline_passed(now: dt.datetime | None = None) -> bool:
    """True from DEADLINE_ET until the 17:00 close: never fetch near the open,
    the trading feed's morning requests must not be starved or penalized."""
    now = now or dt.datetime.now(ET)
    return now.weekday() < 5 and DEADLINE_ET <= now.time() < dt.time(17, 5)


async def sleep(s: float) -> None:      # one seam for the tests to remove the waits
    await asyncio.sleep(s)


# ------------------------------------------------------------------ writing
def write_session(rows: list[dict], path: Path, *, root: str, contract: str,
                  date: dt.date, start: dt.datetime, end: dt.datetime,
                  stats: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt", newline="", compresslevel=6) as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)
    spreads = [r["ask"] - r["bid"] for r in rows
               if isinstance(r["bid"], float) and isinstance(r["ask"], float)]
    inside = sum(1 for r in rows if isinstance(r["bid"], float) and isinstance(r["ask"], float)
                 and r["bid"] <= r["price"] <= r["ask"])
    iso = lambda ms: dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat()  # noqa: E731
    manifest = {
        "root": root, "contract": contract, "session_date": date.isoformat(),
        "session_start_utc": start.astimezone(dt.timezone.utc).isoformat(),
        "session_end_utc": end.astimezone(dt.timezone.utc).isoformat(),
        "ticks": len(rows),
        "first_tick_utc": iso(rows[0]["ts_ms"]) if rows else None,
        "last_tick_utc": iso(rows[-1]["ts_ms"]) if rows else None,
        "complete": stats.get("complete", False), "pages": stats.get("pages"),
        "median_spread": (sorted(spreads)[len(spreads) // 2] if spreads else None),
        "trade_inside_bid_ask_pct": (round(100 * inside / len(spreads), 1) if spreads else None),
        "bytes": path.stat().st_size, "fields": list(FIELDS),
        "recorded_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    path.with_suffix("").with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


# ------------------------------------------------------------------ token
def md_token() -> tuple[str, str]:
    """(md token, env) from an account the desk already logged in — never a
    login of its own (logins are rate-limited and precious). The LIVE login
    first: bulk paging spends that login's 180/hour md budget, and the demo
    login (the one the 9:30 feed rides) stays clean."""
    cfg = config_mod.load()
    now = dt.datetime.now(dt.timezone.utc)
    for aid, a in sorted(cfg.accounts.items(), key=lambda kv: not kv[1].live):
        p = state_dir() / f"{aid}.tokens.json"
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text())
            exp = dt.datetime.fromisoformat(str(d.get("expiration_time", "")).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if d.get("md_access_token") and exp > now + dt.timedelta(minutes=2):
            return d["md_access_token"], ("live" if a.live else "demo")
    raise RuntimeError("no valid md token on disk — is the desk running and connected?")


async def connect_md() -> TradovateWS:
    tok, env = md_token()
    ws = TradovateWS(tok, env)
    ws.url = MD_LIVE if env == "live" else MD_DEMO
    await ws.connect()
    await ws.authorize()
    return ws


class MDConn:
    """The md socket for a whole run. A run of several hours outlives the
    token it started with: the socket then closes and, without this, every
    later session fails "websocket not connected" (2026-09-22 17:20 run:
    GC, SI and all of that day's sessions lost). ensure() rebuilds the
    socket on the freshest token on disk (the desk renews it)."""

    def __init__(self, ws: TradovateWS | None = None):
        self.ws = ws
        self.reconnects = 0

    async def ensure(self) -> TradovateWS:
        if self.ws is None or not getattr(self.ws, "connected", True):
            if self.ws is not None:
                self.reconnects += 1
                log(f"md socket down — reconnecting ({self.reconnects})")
                try:
                    await self.ws.close()
                except Exception:  # noqa: BLE001
                    pass
            self.ws = await connect_md()
        return self.ws

    async def close(self) -> None:
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:  # noqa: BLE001
                pass


# ------------------------------------------------------------------ the run
async def record(roots=ROOTS, dates: list[dt.date] | None = None,
                 base: Path = ARCHIVE, ws: TradovateWS | None = None,
                 now: dt.datetime | None = None) -> list[dict]:
    now = now or dt.datetime.now(ET)
    dates = dates if dates is not None else sessions_to_record(now)
    todo = []
    for date in dates:
        for root in roots:
            contract = symbols.front_month(root, date)
            path = archive_path(root, date, contract, base)
            if path.exists() and not from_massive(path):
                continue                  # our own (bid/ask) recording stays
            todo.append((date, root, contract, path))
    if not todo:
        log("nothing to record — every complete session is on disk")
        return []
    conn = ws if isinstance(ws, MDConn) else MDConn(ws)
    own = ws is None
    done = []
    try:
        for date, root, contract, path in todo:
            start, end = session_bounds(date)
            t0 = time.perf_counter()
            try:
                rows, stats = await fetch_session(conn, contract, start, end)
            except Exception as e:  # noqa: BLE001 — one bad symbol must not stop the rest
                log(f"{root} {date} {contract}: FAILED {e}")
                continue
            if not rows:
                log(f"{root} {date} {contract}: no ticks served (buffer gone or holiday) — skipped")
                continue
            m = write_session(rows, path, root=root, contract=contract, date=date,
                              start=start, end=end, stats=stats)
            done.append(m)
            log(f"{root} {date} {contract}: {m['ticks']:,} ticks, {m['bytes'] / 1e6:.1f} MB, "
                f"{stats['pages']} pages, {time.perf_counter() - t0:.0f}s"
                + ("" if m["complete"] else " — PARTIAL (buffer did not reach the open)"))
    finally:
        if own:
            await conn.close()
    return done


def from_massive(path: Path) -> bool:
    """True if the file on disk came from the Massive backfill (no bid/ask):
    the recorder's own capture is richer and may replace it."""
    m = path.with_suffix("").with_suffix(".json")
    try:
        return json.loads(m.read_text()).get("source") == "massive"
    except (OSError, ValueError):
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", help="one session date YYYY-MM-DD (default: every "
                                   "complete session in the last 3 days)")
    ap.add_argument("--roots", default=",".join(ROOTS))
    ap.add_argument("--dir", default=str(ARCHIVE))
    a = ap.parse_args(argv)
    roots = tuple(r.strip().upper() for r in a.roots.split(",") if r.strip())
    dates = [dt.date.fromisoformat(a.date)] if a.date else None
    if dates and not session_complete(dates[0], dt.datetime.now(ET)):
        log(f"session {dates[0]} is not over yet (ends 17:00 ET) — nothing to do")
        return 0
    if deadline_passed():
        log(f"past {DEADLINE_ET} ET on a trading day — the feed's budget is the desk's now; "
            "run again after 17:05")
        return 0
    try:
        asyncio.run(record(roots, dates, Path(a.dir)))
    except Exception as e:  # noqa: BLE001
        log(f"run failed: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
