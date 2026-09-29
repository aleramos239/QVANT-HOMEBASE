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

The broker's history window (root cause of the 18:00-20:00 ET hole, found
2026-09-28 in this job's own log and manifests): the md feed serves tick
history from 00:00 UTC of the PREVIOUS UTC day onwards, nothing older.
  * all 19 partial nightly files start at 00:00:00.0xx UTC of their session
    date (00:00:37 at most, for thin markets), and all were recorded after
    00:00 UTC of the day after;
  * the one complete file, NQ 2026-09-24, was finished at 23:10 UTC that same
    day, reaches the 18:00 ET open, and its first tick id is NQ 09-23's last
    id + 1 -- paging across 00:00 UTC works, the cut is not in our requests;
  * every request for a session that ended before 00:00 UTC of the previous
    day came back empty ("no ticks served").
So session D's first hours -- 18:00 ET on D-1 to 00:00 UTC on D, i.e.
18:00-20:00 ET (18:00-19:00 in winter) -- leave the window at 00:00 UTC on
D+1: 20:00 ET (19:00) on D itself, three hours after the close. The rest of D
stays until 00:00 UTC on D+2. The job used to page each session backwards
from the close, one root after another, so it reached those first hours
last, hours after they were gone. Now a session is cut at 00:00 UTC into
segments, and segments are fetched earliest-expiry first (every root's first
hours before any root's long tail), each paged backwards from its own end.

    python -m homebase.ticks                # every segment still to fetch, then the report
    python -m homebase.ticks --date 2026-09-22 --roots NQ,ES
    python -m homebase.ticks --coverage     # only homebase/.state/tick_coverage.json
    python -m homebase.ticks --rescan       # recent manifests' `complete` from their hours
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import datetime as dt
import decimal
import fcntl
import json
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config as config_mod
from . import symbols
from . import tickarchive
from .broker.tradovate_ws import TradovateWS
from .marketdata import MD_DEMO, MD_LIVE
from .paths import state_dir

ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
HISTORY_UTC_DAYS = 2        # the feed serves ticks from 00:00 UTC of the previous UTC day (docstring)
# priority order: if the 08:00 deadline cuts a night short, the important
# ones are done first. The archive's 15 roots (the Massive backfill's too):
# about 880 pages a weekday at PAGE_INTERVAL_S (NQ ~150, ES ~310, ZN ~160, CL ~58,
# RTY ~37, GC ~36, NG ~28, YM ~18, 6E/6J/6B/MBT ~50 together, SI 13, HG 9, BTC 2),
# ~8.8 h of the 14.7 h between 17:20 and the 08:00 deadline; the first hours,
# fetched first, are ~26 pages (~16 min). A night cut short resumes the next one.
ROOTS = ("NQ", "ES", "YM", "RTY", "GC", "SI", "CL", "ZN", "NG", "HG", "6E", "6J", "6B", "BTC", "MBT")
ARCHIVE = Path.home() / "futures_ticks"
PAGE = 4096                 # the feed caps a tick request at about this
MAX_PAGES = 3000            # ~12M ticks — far above any session
SESSION_GRACE_MIN = 5       # record a session this long after its close
LOOKBACK_DAYS = 3           # sessions to check on every run
LIVE_LOOKBACK_DAYS = 30     # live recordings merged into the archive this far back
PAGE_INTERVAL_S = 36.0      # <= 100 requests/hour: the chart service shares this login's 180/hour (its refills <= 60/h + a start-up burst of one getChart per root)
PENALTY_MAX = 6             # give up a session after this many penalties in a row
DEADLINE_ET = dt.time(8, 0)  # never still fetching this close to the open
FIELDS = ("ts_ms", "price", "size", "bid", "ask", "bid_size", "ask_size", "id")


def log(msg: str) -> None:
    print(f"[ticks] {dt.datetime.now(ET).strftime('%H:%M:%S')} {msg}", flush=True)


# ------------------------------------------------------------------ sessions
def always_open(root: str | None) -> bool:
    """CME crypto (BTC, MBT) trades 24/7: a session every day -- the chart
    service's list (homebase.charts.session.ALWAYS_OPEN), so both file a tick
    under the same session."""
    from .charts.session import always_open as open_24_7    # it imports this module
    return open_24_7(root)


def session_bounds(date: dt.date, root: str | None = None) -> tuple[dt.datetime, dt.datetime]:
    """(start, end) as aware ET datetimes: 18:00 the day before -> 17:00; a
    24/7 root's session runs 18:00 -> 18:00 (homebase.charts.session)."""
    start = dt.datetime.combine(date - dt.timedelta(days=1), dt.time(18, 0), ET)
    end = dt.datetime.combine(date, dt.time(18 if always_open(root) else 17, 0), ET)
    return start, end


def is_session_day(date: dt.date, root: str | None = None) -> bool:
    return always_open(root) or date.weekday() < 5


def session_complete(date: dt.date, now: dt.datetime, root: str | None = None) -> bool:
    _, end = session_bounds(date, root)
    return now >= end + dt.timedelta(minutes=SESSION_GRACE_MIN)


def sessions_to_record(now: dt.datetime, days: int = LOOKBACK_DAYS,
                       root: str | None = None) -> list[dt.date]:
    """Complete sessions within the lookback, oldest first."""
    today = now.astimezone(ET).date()
    out = [today - dt.timedelta(days=i) for i in range(days + 1)]
    return sorted(d for d in out if is_session_day(d, root) and session_complete(d, now, root))


def archive_path(root: str, date: dt.date, contract: str, base: Path = ARCHIVE) -> Path:
    return base / root / str(date.year) / f"{date.isoformat()}_{contract}.csv.gz"


def now_et() -> dt.datetime:        # one seam for the tests to move the clock
    return dt.datetime.now(ET)


def history_expiry(t: dt.datetime) -> dt.datetime:
    """The moment the broker stops serving a tick stamped t: 00:00 UTC two
    days after t's UTC date (it serves from 00:00 UTC of the previous day)."""
    d = t.astimezone(UTC).date() + dt.timedelta(days=HISTORY_UTC_DAYS)
    return dt.datetime.combine(d, dt.time(0), UTC)


def utc_segments(start: dt.datetime, end: dt.datetime) -> list[tuple[dt.datetime, dt.datetime]]:
    """[start, end] cut at every 00:00 UTC: each piece leaves the broker's
    history at one moment (history_expiry of its start)."""
    out, s, end = [], start.astimezone(UTC), end.astimezone(UTC)
    while s < end:
        cut = dt.datetime.combine(s.date() + dt.timedelta(days=1), dt.time(0), UTC)
        out.append((s, min(cut, end)))
        s = min(cut, end)
    return out


# ------------------------------------------------------------------ fetching
def price_decimals(tick: float) -> int:
    """Decimals that hold every multiple of `tick` exactly: at least 6 (what the
    archive always used), more for a finer tick -- 6J's 0.0000005 needs 7, and
    rounding its prices to 6 would move every odd half-tick by 5e-7."""
    exp = decimal.Decimal(repr(float(tick))).normalize().as_tuple().exponent if tick else 0
    return max(6, -exp)


def _unpack(packet: dict) -> list[dict]:
    """One chart packet -> tick rows. Prices ride as tick offsets from the
    packet's base price bp; timestamps as ms offsets from bt."""
    bp, bt, ts = packet.get("bp", 0), packet.get("bt", 0), packet.get("ts") or 0.0
    nd = price_decimals(ts)
    rows = []
    for t in packet.get("tks", []) or []:
        rows.append({
            "ts_ms": bt + t.get("t", 0),
            "price": round((bp + t.get("p", 0)) * ts, nd),
            "size": t.get("s"),
            "bid": round((bp + t["b"]) * ts, nd) if t.get("b") is not None else "",
            "ask": round((bp + t["a"]) * ts, nd) if t.get("a") is not None else "",
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
    Raises Penalty on a rate-limit reply (retry with its ticket).

    Only this request's own chart counts. The socket may carry other
    subscriptions too (the chart service pages its gap refills on the socket
    its live Tick charts ride), so packets are kept WITH their subscription
    id and filtered to this getChart's {historicalId, realtimeId} once the
    reply names them (packets can land before the reply does), and only an
    end-of-history for those ids ends the page. On a socket that carries
    nothing else (the nightly job's) this changes nothing."""
    packets: list[dict] = []
    ended: set = set()              # subscription ids whose end-of-history arrived
    mine: set = set()               # this request's ids, known once getChart answers
    done = asyncio.get_running_loop().create_future()

    def on(msg):
        if msg.get("e") != "chart":
            return
        for ch in (msg.get("d") or {}).get("charts", []) or []:
            if ch.get("tks"):
                packets.append(ch)
            if ch.get("eoh"):
                ended.add(ch.get("id"))
                if ch.get("id") in mine and not done.done():
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
        mine.update(int(d[k]) for k in ("historicalId", "realtimeId") if d.get(k) is not None)
        if mine & ended and not done.done():
            done.set_result(True)            # our end-of-history beat the reply
        try:
            await asyncio.wait_for(done, timeout_s)
        except asyncio.TimeoutError:
            if not any(p.get("id") in mine for p in packets):
                raise RuntimeError(f"{contract}: no tick data before timeout")
        rt = (d or {}).get("realtimeId")
        if rt is not None:
            try:
                await ws.request("md/cancelChart", {"subscriptionId": rt})
            except Exception:  # noqa: BLE001 — best effort
                pass
    finally:
        ws.event_handlers.remove(on)
    rows = [r for p in packets if p.get("id") in mine for r in _unpack(p)]
    rows.sort(key=lambda r: (r["ts_ms"], r["id"] or 0))
    return rows


async def fetch_session(ws: TradovateWS, contract: str, start: dt.datetime,
                        end: dt.datetime, page_fn=None,
                        expiry: dt.datetime | None = None) -> tuple[list[dict], dict]:
    """Page backwards from `end` (a session's close, or a segment's end) until
    `start` (or the buffer runs dry). Returns (rows ascending, stats):
    stats["stop"] says why it stopped -- "reached" (a page went past `start`:
    everything in [start, end] is in), "exhausted" (the buffer ran dry first),
    "deadline", "expired" (`expiry` passed mid-fetch: the broker no longer has
    the rest) or "max_pages"."""
    page_fn = page_fn or fetch_page
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    before, seen, rows, pages, penalties = end_ms, set(), [], 0, 0
    last_req, stop, earliest = 0.0, "max_pages", None
    while pages < MAX_PAGES:
        gap = PAGE_INTERVAL_S - (time.monotonic() - last_req)
        if pages and gap > 0:
            await sleep(gap)
        if deadline_passed():                       # checked after the wait: it may cross 08:00
            log(f"{contract}: deadline {DEADLINE_ET} ET — stopping this session here")
            stop = "deadline"
            break
        if expiry is not None and now_et() >= expiry:
            stop = "expired"                        # the broker no longer has the rest
            break
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
            stop = "exhausted"
            break                                   # buffer exhausted
        seen.update(r["id"] for r in page)
        rows.extend(new)
        earliest = page[0]["ts_ms"]
        if earliest < start_ms:
            stop = "reached"
            break                                   # reached the open
        before = earliest if earliest < before else before - 1
    rows.sort(key=lambda r: (r["ts_ms"], r["id"] or 0))
    complete = bool(rows) and rows[0]["ts_ms"] - start_ms < 5 * 60 * 1000  # within 5 min of the open
    return rows, {"pages": pages, "complete": complete, "stop": stop, "earliest_ms": earliest}


def deadline_passed(now: dt.datetime | None = None) -> bool:
    """True from DEADLINE_ET until the 17:00 close: never fetch near the open,
    the trading feed's morning requests must not be starved or penalized."""
    now = now or dt.datetime.now(ET)
    return now.weekday() < 5 and DEADLINE_ET <= now.time() < dt.time(17, 5)


async def sleep(s: float) -> None:      # one seam for the tests to remove the waits
    await asyncio.sleep(s)


# ------------------------------------------------------------------ writing
def store(root: str, date: dt.date, contract: str, path: Path, start: dt.datetime,
          end: dt.datetime, fetched: list[tuple] = (), entry: dict | None = None,
          include_live: bool = True) -> dict | None:
    """Merge fetched rows (tickarchive rows) into the session's archive file --
    with the live recording and whatever the file already holds
    (homebase.tickarchive: merge, never replace). `entry` logs the fetch in the
    manifest. A refused merge leaves every file as it was and is logged; None
    then, or with nothing to write."""
    try:
        return tickarchive.merge_session(
            path, root=root, contract=contract, date=date, start=start, end=end,
            fetched=fetched, fetched_source=entry, include_live=include_live)
    except tickarchive.MergeRefused as e:
        log(f"{root} {date} {contract}: MERGE REFUSED, every file left as it was — {e}")
    except Exception as e:  # noqa: BLE001 — a bad file must not stop the night; the original stays
        log(f"{root} {date} {contract}: MERGE FAILED, the original is untouched — "
            f"{type(e).__name__}: {e}")
    return None


# ------------------------------------------------------------------ token
def _valid_md_tokens(accounts) -> list:
    """[(account id, account, md token, expiry)] for each of `accounts` (config order kept)
    whose md token on disk stays valid 2+ minutes from now."""
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for aid, a in accounts:
        p = state_dir() / f"{aid}.tokens.json"
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text())
            exp = dt.datetime.fromisoformat(str(d.get("expiration_time", "")).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if d.get("md_access_token") and exp > now + dt.timedelta(minutes=2):
            out.append((aid, a, d["md_access_token"], exp))
    return out


def _freshest(cands: list):
    """The candidate whose token expires last (the first of them on a tie): a socket dies
    when its token does, so the freshest carries it furthest -- after the desk's early
    renewal (09:10-09:19:30 ET) that is the renewed token, which lasts past 10:10."""
    return max(cands, key=lambda c: c[3])


def md_token(prefer_live: bool = True, strict: bool = False) -> tuple[str, str]:
    """(md token, env) from an account the desk already logged in — never a
    login of its own (logins are rate-limited and precious). prefer_live
    (the default, for bulk paging) takes the LIVE login first so the demo
    login the 9:30 feed rides stays clean; the chart service may prefer the
    demo (Apex eval) login instead. Within the login taken, the token that
    expires last (_freshest). strict (the nightly job): the preferred login
    or nothing -- never a fallback to the other one."""
    cfg = config_mod.load()
    cands = _valid_md_tokens(sorted(cfg.accounts.items(),
                                    key=lambda kv: kv[1].live != prefer_live))
    if not cands:
        raise RuntimeError("no valid md token on disk — is the desk running and connected?")
    live = cands[0][1].live
    if strict and bool(live) != prefer_live:
        want = "live" if prefer_live else "demo"
        raise RuntimeError(f"no valid {want} md token on disk — the tick archive never pages on the "
                           "other login (the demo login feeds the 9:30 bot); is the live account connected?")
    _, a, tok, _ = _freshest([c for c in cands if c[1].live == live])
    return tok, ("live" if a.live else "demo")


def accounts_by_env() -> dict[str, "str | None"]:
    """{"live": <label>, "demo": <label>} -- the account whose md token is valid on disk RIGHT
    NOW for each env, or None (Task 4 fix round 1, review M2: the app-settings dialog shows this
    next to "Live"/"Apex (demo)" instead of a hard-coded account number, and it also makes a C2
    environment mismatch visible before a switch is even attempted -- a None here means that
    login has no valid token, so a switch to it would fail). Per env the account whose token
    expires last, same rule as md_token's own choice."""
    cfg = config_mod.load()
    cands = _valid_md_tokens(cfg.accounts.items())
    out: dict[str, "str | None"] = {"live": None, "demo": None}
    for env, live in (("live", True), ("demo", False)):
        mine = [c for c in cands if bool(c[1].live) == live]
        if mine:
            aid, a, _, _ = _freshest(mine)
            out[env] = a.label or a.account_name or aid
    return out


async def connect_md(prefer_live: bool = True, strict: bool = False) -> TradovateWS:
    tok, env = md_token(prefer_live, strict)
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
            self.ws = await connect_md(strict=True)      # the live login's budget, never the 9:30 bot's
        return self.ws

    async def close(self) -> None:
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:  # noqa: BLE001
                pass


# ------------------------------------------------------------------ the run
def candidate_dates(now: dt.datetime, days: int = LOOKBACK_DAYS) -> list[dt.date]:
    """Session dates a run looks at, oldest first: the last `days` days and
    today -- today's first hours are over, and fetchable, long before its close."""
    today = now.astimezone(ET).date()
    return [today - dt.timedelta(days=i) for i in range(days, -1, -1)]


def segment_state(prev: dict, s: dt.datetime, e: dt.datetime) -> tuple[bool, int | None]:
    """(done, resume_ms) of segment [s, e] by the archive file's manifest.
    Done once a fetch of it reached its start or ran the broker dry. A fetch
    cut short (the 08:00 deadline, the page cap) paged back from the end
    without a gap, so the next one resumes from the earliest tick it got. A
    nightly file from before fetches were logged ("legacy") paged back from
    the close until the broker ran dry: done from its first tick on."""
    fr, to = s.astimezone(UTC).isoformat(), e.astimezone(UTC).isoformat()
    s_ms, e_ms = int(s.timestamp() * 1000), int(e.timestamp() * 1000)
    resume = None
    for src in tickarchive.prior_sources(prev):
        if src.get("kind") != "history":
            continue
        if src.get("stop") == "legacy":
            lo, hi = src.get("earliest_ms"), tickarchive.ms_of(src.get("to_utc"))
            if lo is not None and hi is not None and lo - s_ms < tickarchive.EDGE_MS and hi >= e_ms:
                return True, None
            continue
        if (src.get("from_utc"), src.get("to_utc")) != (fr, to):
            continue
        if src.get("stop") in ("reached", "exhausted"):
            return True, None
        if src.get("earliest_ms") is not None:
            resume = src["earliest_ms"] if resume is None else min(resume, src["earliest_ms"])
    return False, resume


def plan(roots, dates: list[dt.date], base: Path, now: dt.datetime) -> tuple[dict, list]:
    """The run's work: ({(root, date): session}, [segment jobs]), the jobs in
    fetch order -- earliest expiry first (docstring: every root's first hours
    before any root's long tail), then a session's first segment before its
    later ones, then root priority (ROOTS order), then date. Only segments
    that are over, not fetched yet, and still in the broker's history."""
    rank = {r: i for i, r in enumerate(ROOTS)}
    grace = dt.timedelta(minutes=SESSION_GRACE_MIN)
    sessions, jobs = {}, []
    for date in dates:
        for root in roots:
            if not is_session_day(date, root):
                continue
            start, end = session_bounds(date, root)
            contract = symbols.front_month(root, date)
            path = archive_path(root, date, contract, base)
            prev = tickarchive.load_manifest(path)
            todo, gone = [], []
            for s, e in utc_segments(start, end):
                if now < e + grace:
                    continue                            # not over yet
                done, resume = segment_state(prev, s, e)
                if done:
                    continue
                if now >= history_expiry(s):
                    if now - history_expiry(s) < dt.timedelta(days=1):
                        gone.append((s, e))             # said by the runs of the day it left
                    continue
                todo.append((s, e, resume))
            for s, e in gone:
                log(f"{root} {date} {contract}: {s.astimezone(ET):%m-%d %H:%M}-{e.astimezone(ET):%H:%M} ET "
                    "left the broker's history before it was fetched — only the live recording "
                    "or Massive can fill it")
            if not todo:
                continue
            key = (root, date)
            sessions[key] = {"root": root, "date": date, "contract": contract, "path": path,
                             "start": start, "end": end}
            for s, e, resume in todo:
                jobs.append((history_expiry(s), s > start, rank.get(root, len(rank)), date, key,
                             s, e, resume))
    jobs.sort(key=lambda j: j[:4])
    return sessions, jobs


def _et_span(a: dt.datetime, b: dt.datetime) -> str:
    return f"{a.astimezone(ET):%H:%M}-{b.astimezone(ET):%H:%M} ET"


async def record(roots=ROOTS, dates: list[dt.date] | None = None,
                 base: Path = ARCHIVE, ws: TradovateWS | None = None,
                 now: dt.datetime | None = None) -> list[dict]:
    """Fetch every segment the plan names, merging each into its session's
    archive file as it lands; then merge the live recordings no fetch touched.
    Returns the last manifest written per session."""
    now = now or now_et()
    dates = dates if dates is not None else candidate_dates(now)
    sessions, jobs = plan(roots, dates, base, now)
    written: dict = {}
    if not jobs:
        log("nothing to fetch — every segment is in the archive or gone from the broker")
    else:
        conn = ws if isinstance(ws, MDConn) else MDConn(ws)
        own = ws is None
        grace = dt.timedelta(minutes=SESSION_GRACE_MIN)
        try:
            for expiry, _, _, date, key, s, e, resume in jobs:
                st = sessions[key]
                root, contract = st["root"], st["contract"]
                if deadline_passed():
                    log(f"deadline {DEADLINE_ET} ET — stopping the run here")
                    break
                if now_et() >= expiry:
                    log(f"{root} {date} {contract} {_et_span(s, e)}: left the broker's history "
                        "before its turn")
                    continue
                t0 = time.perf_counter()
                until = e if resume is None else dt.datetime.fromtimestamp(resume / 1000, UTC)
                try:
                    rows, stats = await fetch_session(conn, contract, s, until, expiry=expiry)
                except Exception as ex:  # noqa: BLE001 — one bad symbol must not stop the rest
                    log(f"{root} {date} {contract} {_et_span(s, e)}: FAILED {ex}")
                    continue
                entry = {"kind": "history", "from_utc": s.astimezone(UTC).isoformat(),
                         "to_utc": e.astimezone(UTC).isoformat(), "stop": stats["stop"],
                         "pages": stats["pages"], "earliest_ms": stats["earliest_ms"],
                         **({"resumed_from_ms": resume} if resume is not None else {})}
                over = now_et() >= st["end"] + grace     # the live recording is final
                n = len(rows)
                fetched = [tickarchive.row_of(r) for r in rows]
                del rows                                 # one copy in memory, not two (ES: 1.2M ticks)
                man = store(root, date, contract, st["path"], st["start"], st["end"], fetched, entry,
                            include_live=over)
                del fetched
                if man is not None:
                    written[key] = man
                log(f"{root} {date} {contract} {_et_span(s, e)}: {n:,} ticks, "
                    f"{stats['pages']} pages, {time.perf_counter() - t0:.0f}s ({stats['stop']})"
                    + ("" if man is None else f" — file {man['ticks']:,} ticks"
                       + ("" if man["complete"] else ", PARTIAL")))
        finally:
            if own:
                await conn.close()
    for man in promote_live(roots, base, now_et()):
        written[(man["root"], dt.date.fromisoformat(man["session_date"]))] = man
    return list(written.values())


def promote_live(roots, base: Path, now: dt.datetime, days: int = LIVE_LOOKBACK_DAYS) -> list[dict]:
    """Merge each over-and-done session's live recording the archive file does
    not hold yet -- no fetch needed: a session already gone from the broker,
    or a night the fetch never ran. The live file itself is only read."""
    out = []
    for root in roots:
        for date in sessions_to_record(now, days, root):
            start, end = session_bounds(date, root)
            tag = date.isoformat()
            for lp in sorted((base / root / str(date.year)).glob(f"{tag}_*{tickarchive.LIVE_SUFFIX}")):
                contract = lp.name[len(tag) + 1:-len(tickarchive.LIVE_SUFFIX)]
                path = archive_path(root, date, contract, base)
                if tickarchive.live_merged(tickarchive.load_manifest(path), tickarchive.live_stamp(lp)):
                    continue
                man = store(root, date, contract, path, start, end)
                if man is not None:
                    live = next((s for s in reversed(man["sources"]) if s.get("kind") == "live"), {})
                    log(f"{root} {date} {contract}: live recording merged ({live.get('ticks', 0):,} ticks, "
                        f"{live.get('only_in_live', 0):,} the archive lacked) — file {man['ticks']:,} ticks"
                        + ("" if man["complete"] else ", PARTIAL"))
                    out.append(man)
    return out


@contextlib.contextmanager
def archive_lock(path: Path):
    """One writer of the archive at a time (the nightly run, --rescan, a
    manual fill): an exclusive lock on `path`, never waited for."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(f"another tick-archive run holds {path} — try again when it is done") from None
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def coverage_report(roots, base: Path, sessions: int) -> None:
    """Write homebase/.state/tick_coverage.json and log its summary line; a
    failure here is logged, never raised (the night's data is already written)."""
    from . import tickcoverage                    # it imports this module
    try:
        tickcoverage.write_report(roots, base, now_et(), state_dir() / "tick_coverage.json", sessions)
    except Exception as e:  # noqa: BLE001
        log(f"coverage report failed: {type(e).__name__}: {e}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", help="one session date YYYY-MM-DD (default: every "
                                   "complete session in the last 3 days)")
    ap.add_argument("--roots", default=",".join(ROOTS))
    ap.add_argument("--dir", default=str(ARCHIVE))
    ap.add_argument("--coverage", action="store_true",
                    help="only write homebase/.state/tick_coverage.json (no market data)")
    ap.add_argument("--rescan", action="store_true",
                    help="write each recent front-month file's hour-by-hour coverage into its "
                         "manifest (data files untouched), then the report (no market data)")
    ap.add_argument("--sessions", type=int, default=30, help="sessions per root the report covers")
    a = ap.parse_args(argv)
    roots = tuple(r.strip().upper() for r in a.roots.split(",") if r.strip())
    base = Path(a.dir)
    if a.coverage:
        coverage_report(roots, base, a.sessions)
        return 0
    try:
        with archive_lock(state_dir() / "ticks.lock"):
            if a.rescan:
                from . import tickcoverage
                n = tickcoverage.rescan(roots, base, now_et(), a.sessions)
                log(f"rescan: {n} manifest(s) rewritten with their hour-by-hour coverage")
                coverage_report(roots, base, a.sessions)
                return 0
            dates = [dt.date.fromisoformat(a.date)] if a.date else None
            if deadline_passed():
                log(f"past {DEADLINE_ET} ET on a trading day — the feed's budget is the desk's now; "
                    "run again after 17:05")
                return 0
            try:
                asyncio.run(record(roots, dates, base))
            except Exception as e:  # noqa: BLE001
                log(f"run failed: {e}")
                return 1
            finally:
                coverage_report(roots, base, a.sessions)
    except RuntimeError as e:
        log(str(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
