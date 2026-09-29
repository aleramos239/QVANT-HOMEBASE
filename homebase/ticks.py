"""Tick archive: every trade (price, size, bid/ask at the trade) for each
root's front month, one gzip CSV per session, filed under
~/futures_ticks/<ROOT>/<YYYY>/<session-date>_<contract>.csv.gz + a .json
manifest.

Two things feed it. The chart service records every tick as it happens
(<date>_<contract>.live.csv.gz). This job -- run every hour, at load, and at
17:20 / 05:30 (deploy/com.ramosquant.homebase-ticks.plist.template) -- fetches
from the broker's tick history exactly what the archive file and the live
recording lack, and merges all of it into the archive file
(homebase.tickarchive: merge, never replace). What is missing is found by the
broker's tick id, one gap-free counter per contract: the ticks between two
runs of consecutive ids (a restart, a dead battery), an open or a close no
fetch has vouched for yet, a recording that stopped, or the whole session
when nothing was recorded (missing()). A run with nothing to do says nothing.

The feed allows 180 chart requests per hour per login (learned 2026-09-22:
a 116-page burst drew "Rate limit exceeded" penalties for the next hour).
So pages are paced (<= 100/hour: the chart service shares the login). At
night (outside 08:00-17:05 ET on weekdays) a run goes on until done or 08:00
and waits out a penalty (p-time, then its p-ticket); by day a run spends at
most DAY_PAGES pages, never runs 09:20-09:35 ET, and a penalty or a refused
connection ends it until the next run. The job's requests plus the chart
service's (it publishes them, charts/md_usage.json) stay under SHARED_MD_CAP
an hour. Only the LIVE login's md budget is spent -- never the demo (Apex)
login the 9:30 feed rides.

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
last, hours after they were gone. Now every missing stretch is cut at 00:00
UTC into pieces, fetched earliest-expiry first (every root's first hours
before any root's long tail), each paged backwards from its own end.

    python -m homebase.ticks                # fetch and merge whatever is missing (hourly)
    python -m homebase.ticks --date 2026-09-22 --roots NQ,ES
    python -m homebase.ticks --coverage     # only homebase/.state/tick_coverage.json
    python -m homebase.ticks --rescan       # recent manifests' `complete` from their hours
    python -m homebase.ticks --fill-from-massive --holes --dry-run   # manual: homebase.tickmassive
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
from .charts import QUIET as CHARTS_QUIET
from .marketdata import MD_DEMO, MD_LIVE
from .paths import state_dir

ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
HISTORY_UTC_DAYS = 2        # the feed serves ticks from 00:00 UTC of the previous UTC day (docstring)
# priority order: if the 08:00 deadline cuts a night short, the important
# ones are done first. The archive's 15 roots (the Massive backfill's too).
# Budget: with the live recording, a session costs its two edge pages plus a
# page or so per gap -- ~30-100 pages a night for all 15. With nothing recorded
# live, a weekday is ~880 pages (NQ ~150, ES ~310, ZN ~160, CL ~58, RTY ~37,
# GC ~36, NG ~28, YM ~18, 6E/6J/6B/MBT ~50 together, SI 13, HG 9, BTC 2):
# ~8.8 h at PAGE_INTERVAL_S of the 14.7 h between 17:20 and 08:00, the first
# hours (~26 pages, ~16 min) first. What a night leaves, the next runs take.
ROOTS = ("NQ", "ES", "YM", "RTY", "GC", "SI", "CL", "ZN", "NG", "HG", "6E", "6J", "6B", "BTC", "MBT")
ARCHIVE = Path.home() / "futures_ticks"
PAGE = 4096                 # the feed caps a tick request at about this
MAX_PAGES = 3000            # ~12M ticks — far above any session
SESSION_GRACE_MIN = 5       # record a session this long after its close
LOOKBACK_DAYS = 3           # sessions to check on every run
LIVE_LOOKBACK_DAYS = 30     # live recordings merged into the archive this far back
PAGE_INTERVAL_S = 36.0      # <= 100 requests/hour: the chart service shares this login's 180/hour (its refills <= 60/h + a start-up burst of one getChart per root)
PENALTY_MAX = 6             # give up a session after this many penalties in a row
DEADLINE_ET = dt.time(8, 0)  # a night run stops here; daytime runs are capped (DAY_PAGES)
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
                        expiry: dt.datetime | None = None, *, max_pages: int | None = None,
                        deadline: bool = True, halt=None,
                        penalty_stop: bool = False) -> tuple[list[dict], dict]:
    """Page backwards from `end` (a session's close, or a gap's end) until
    `start` (or the buffer runs dry). Returns (rows ascending, stats):
    stats["stop"] says why it stopped -- "reached" (a page went past `start`:
    everything in [start, end] is in), "exhausted" (the buffer ran dry first),
    "deadline" (08:00 ET, when `deadline`), "halted" (`halt()` said so),
    "expired" (`expiry` passed mid-fetch: the broker no longer has the rest)
    or "max_pages". penalty_stop: a rate-limit reply raises Penalty at once
    instead of being waited out (the daytime pass backs off to its next run)."""
    page_fn = page_fn or fetch_page
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    before, seen, rows, pages, penalties = end_ms, set(), [], 0, 0
    stop, earliest = "max_pages", None
    pacer = ws if isinstance(ws, MDConn) else Pacer()   # one run's socket paces EVERY request it sends
    cap = MAX_PAGES if max_pages is None else min(MAX_PAGES, max_pages)
    while pages < cap:
        await pacer.pace()
        if deadline and deadline_passed():          # checked after the wait: it may cross 08:00
            log(f"{contract}: deadline {DEADLINE_ET} ET — stopping this session here")
            stop = "deadline"
            break
        if halt is not None and halt():
            stop = "halted"
            break
        if expiry is not None and now_et() >= expiry:
            stop = "expired"                        # the broker no longer has the rest
            break
        pacer.sent()
        if isinstance(ws, MDConn):
            sock = await ws.ensure()
        else:
            sock = ws
        try:
            page = await page_fn(sock, contract, before)
            penalties = 0
        except (RuntimeError, ConnectionError, OSError) as e:
            if isinstance(ws, MDConn) and "not connected" in str(e) and ws.dropped < DROPS_MAX:
                ws.dropped += 1                     # rebuilt on the next loop, after a backoff
                await sleep(5 * 2 ** (ws.dropped - 1))
                continue
            raise
        except Penalty as pen:
            if penalty_stop:
                raise
            penalties += 1
            if penalties > PENALTY_MAX:
                raise RuntimeError(f"{contract}: {penalties} penalties in a row — {pen}")
            log(f"{contract}: {pen} — waiting {pen.wait_s + 1:.0f}s, resending with its ticket")
            await sleep(pen.wait_s + 1)
            pacer.sent()
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
REFUSED = "_refused"            # cache key: sessions whose merge was refused, with their files' stamps


def files_stamp(path: Path) -> list:
    """What the archive file and its live recording are right now (size, mtime)."""
    return [tickarchive.live_stamp(path), tickarchive.live_stamp(tickarchive.live_path(path))]


def refused_still(cache: dict | None, root: str, date: dt.date, path: Path) -> bool:
    """Was this session's merge refused, and are its files still exactly as then?
    Then it is left alone (no fetch, no merge) until someone changes them."""
    got = (cache or {}).get(REFUSED, {}).get(f"{root} {date}")
    return bool(got) and got.get("stamp") == files_stamp(path)


def store(root: str, date: dt.date, contract: str, path: Path, start: dt.datetime,
          end: dt.datetime, fetched: list[tuple] = (), entry: dict | None = None,
          include_live: bool = True, cache: dict | None = None) -> dict | None:
    """Merge fetched rows (tickarchive rows) into the session's archive file --
    with the live recording and whatever the file already holds
    (homebase.tickarchive: merge, never replace). `entry` logs the fetch in the
    manifest. A refused or failed merge leaves every file as it was, is logged,
    and is remembered in `cache` with the files' stamps, so the next runs do
    not fetch the same ticks again for nothing; None then, or with nothing to
    write."""
    try:
        return tickarchive.merge_session(
            path, root=root, contract=contract, date=date, start=start, end=end,
            fetched=fetched, fetched_source=entry, include_live=include_live)
    except Exception as e:  # noqa: BLE001 — a bad file must not stop the night; the original stays
        what = "MERGE REFUSED" if isinstance(e, tickarchive.MergeRefused) else "MERGE FAILED"
        log(f"{root} {date} {contract}: {what}, every file left as it was — {type(e).__name__}: {e} "
            "(left alone until its files change)")
        if cache is not None:
            cache.setdefault(REFUSED, {})[f"{root} {date}"] = {
                "stamp": files_stamp(path), "why": f"{type(e).__name__}: {e}", "at": tickarchive.now_utc()}
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


DROPS_MAX = 3                   # a socket found dead mid-fetch is rebuilt this often a run (5, 10, 20 s apart)


class Pacer:
    """At most one chart request per PAGE_INTERVAL_S, across every fetch that
    shares it (MDConn: the whole run -- a job's first page included). Timed by
    now_et(), so the tests' clock drives it too; a clock that jumps back never
    makes it wait more than one interval."""

    def __init__(self):
        self.last: float | None = None

    async def pace(self) -> None:
        if self.last is not None:
            gap = PAGE_INTERVAL_S - (now_et().timestamp() - self.last)
            if gap > 0:
                await sleep(min(gap, PAGE_INTERVAL_S))

    def sent(self) -> None:
        self.last = now_et().timestamp()


SHARED_MD_CAP = 150             # the live login's 180 chart requests/h, less a margin: the job's and
                                # the chart service's together (it publishes its own: charts/md_usage.json)


class BudgetSpent(RuntimeError):
    """The live login's hour is spent (with the chart service's requests): a daytime run stops."""


class Budget:
    """The live login's chart requests in the last hour -- this job's (`own`,
    epoch seconds, kept across runs in the runs cache) plus the chart
    service's, as it publishes them. Before each request: under SHARED_MD_CAP
    it goes; over it a daytime run stops (BudgetSpent), a night run waits for
    the oldest request to age out."""

    def __init__(self, own: list, charts_usage: Path | None = None, day: bool = False):
        self.own, self.charts_usage, self.day = own, charts_usage, day

    def _charts(self) -> list[float]:
        if self.charts_usage is None:
            return []
        try:
            return [float(t) for t in json.loads(self.charts_usage.read_text())["requests"].get("live", [])]
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return []

    def used(self) -> list[float]:
        cut = now_et().timestamp() - 3600
        self.own[:] = [t for t in self.own if t > cut]
        return sorted(self.own + [t for t in self._charts() if t > cut])

    async def room(self) -> None:
        while True:
            used = self.used()
            if len(used) < SHARED_MD_CAP:
                return
            if self.day:
                raise BudgetSpent(f"{len(used)} live-login chart requests in the last hour with the "
                                  "chart service's")
            wait = max(30.0, used[len(used) - SHARED_MD_CAP] + 3600 - now_et().timestamp())
            log(f"the live login's hour is spent ({len(used)} requests with the chart service's) — "
                f"waiting {wait:.0f}s")
            await sleep(wait)

    def sent(self) -> None:
        self.own.append(now_et().timestamp())


class MDConn(Pacer):
    """The md socket for a whole run. A run of several hours outlives the
    token it started with: the socket then closes and, without this, every
    later session fails "websocket not connected" (2026-09-22 17:20 run:
    GC, SI and all of that day's sessions lost). ensure() rebuilds the
    socket on the freshest token on disk (the desk renews it)."""

    def __init__(self, ws: TradovateWS | None = None, budget: Budget | None = None):
        super().__init__()
        self.ws = ws
        self.reconnects = 0
        self.dropped = 0            # sockets found dead mid-fetch this run (DROPS_MAX, then the run stops)
        self.budget = budget

    async def pace(self) -> None:
        await super().pace()
        if self.budget is not None:
            await self.budget.room()

    def sent(self) -> None:
        super().sent()
        if self.budget is not None:
            self.budget.sent()

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


# ------------------------------------------------------------------ what is missing
# Every run -- hourly, on load, and at 17:20 / 05:30 (deploy plist) -- looks at
# what the archive file and the live recording of each recent session hold, as
# runs of consecutive broker tick ids (tickarchive.file_runs), and fetches only
# what lies outside them: the ticks between two runs (a restart, a dead
# battery), an open or a close no history fetch has vouched for yet, a
# recording that stopped, or the whole session when nothing was recorded.
# A stretch the broker was already asked for in full is never asked again.
STALE_MS = 15 * 60 * 1000       # a running session's recording this far behind the clock has stopped
DAY_PAGES = 45                  # a daytime run's pages: the chart service keeps most of the login's 180/h
QUIET = CHARTS_QUIET            # 09:20-09:35 ET, around the 9:30 fire: not one request (the charts' own)
_EMPTY = {"runs": []}
ASKED = "_asked"                # cache key: stretches the broker had nothing for, and no file holds
MD_USED = "_md"                 # cache key: this job's chart requests in the last hour (epoch s)
EMPTY_ONCE = "_empty"           # cache key: stretches that got ONE empty reply (a second, later, vouches)


def in_quiet(now: dt.datetime) -> bool:
    t = now.astimezone(ET)
    return t.weekday() < 5 and QUIET[0] <= t.time() < QUIET[1]


def _ms(t: dt.datetime) -> int:
    return int(t.timestamp() * 1000)


def _utc(ms: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(ms / 1000, UTC)


def candidate_dates(now: dt.datetime, days: int = LOOKBACK_DAYS) -> list[dt.date]:
    """Session dates a run looks at, oldest first: the last `days` days, today
    and tomorrow -- a session is under way from 18:00 the evening before, and
    its hours are fetchable as soon as they are over."""
    today = now.astimezone(ET).date()
    return [today - dt.timedelta(days=i) for i in range(days, -2, -1)]


def missing(root: str, date: dt.date, base: Path, now: dt.datetime, cache: dict,
            prev_last: int | None = None) -> tuple[list, dict]:
    """([(from_ms, to_ms, why)], info): what session `date` lacks so far. The
    open is proven by the previous session's last tick id + 1 (prev_last) or a
    history fetch; the close (once the session is over) by a history fetch."""
    start, end = session_bounds(date, root)
    s_ms, e_ms, now_ms = _ms(start), _ms(end), _ms(now)
    grace = SESSION_GRACE_MIN * 60_000
    over = now_ms >= e_ms + grace
    horizon = e_ms if over else min(e_ms, now_ms - grace)
    contract = symbols.front_month(root, date)
    path = archive_path(root, date, contract, base)
    info = {"root": root, "date": date, "contract": contract, "path": path, "start": start,
            "end": end, "over": over, "last_id": None}
    if horizon <= s_ms or refused_still(cache, root, date, path):
        return [], info
    fa = tickarchive.file_runs(path, cache) if path.exists() else _EMPTY
    fl = tickarchive.file_runs(tickarchive.live_path(path), cache)
    runs = tickarchive.union_runs(fa["runs"], fl["runs"])
    # Massive rows do not count: while the broker still has a stretch, its ticks (with bid/ask)
    # are fetched and take over (tickarchive.merge); a stretch it no longer has is not a job
    spans = tickarchive.merge_spans(
        tickarchive.verified_spans(tickarchive.prior_sources(tickarchive.load_manifest(path)))
        + [tuple(x) for x in cache.get(ASKED, {}).get(f"{root} {date}", [])])
    gaps = []
    if not runs:
        gaps.append((s_ms, horizon, "nothing recorded"))
    else:
        info["last_id"] = runs[-1][1]
        if prev_last is None or runs[0][0] != prev_last + 1:
            gaps.append((s_ms, runs[0][2], "the open"))
        for r0, r1 in zip(runs, runs[1:]):
            gaps.append((r0[3], r1[2], f"{r1[0] - r0[1] - 1:,} ticks"))
        if over:
            gaps.append((runs[-1][3], e_ms, "the close"))
        elif horizon - runs[-1][3] > STALE_MS:
            gaps.append((runs[-1][3], horizon, "the recording stopped"))
    return [(x, y, why) for a, b, why in gaps for x, y in tickarchive.uncovered(spans, a, b)], info


def plan(roots, dates: list[dt.date], base: Path, now: dt.datetime,
         cache: dict | None = None) -> tuple[dict, list]:
    """The run's work: ({(root, date): session info}, [jobs]), each job a piece
    of a missing stretch within one UTC day (it leaves the broker's history at
    one moment), in fetch order -- earliest expiry first (the module docstring:
    every root's first hours before any root's long tail), a session's open
    before its later pieces, root priority (ROOTS order), date. A piece already
    gone from the broker is not a job: it is said once, the hour it goes (the
    coverage report marks it "needs Massive")."""
    cache = {} if cache is None else cache
    rank = {r: i for i, r in enumerate(ROOTS)}
    sessions, jobs = {}, []
    for root in roots:
        prev = None
        for date in sorted(dates):
            if not is_session_day(date, root):
                continue
            front = symbols.front_month(root, date)
            gaps, info = missing(root, date, base, now, cache,
                                 prev_last=prev[1] if prev and prev[0] == front else None)
            prev = (front, info["last_id"]) if info["last_id"] is not None else None
            key = (root, date)
            s_ms = _ms(info["start"])
            for a, b, why in gaps:
                if b <= a and why in ("the open", "the close"):
                    continue                # the edge tick sits on the boundary: nothing lies between
                for s, e in (utc_segments(_utc(a), _utc(b)) if b > a else [(_utc(a), _utc(b))]):
                    exp = history_expiry(s)
                    if now >= exp:
                        if now - exp < dt.timedelta(minutes=70):
                            log(f"{root} {date} {info['contract']} {_et_span(s, e)} ({why}): left the "
                                "broker's history before it was fetched — needs Massive")
                        continue
                    sessions[key] = info
                    jobs.append((exp, _ms(s) > s_ms, rank.get(root, len(rank)), date, key, s, e, why))
    jobs.sort(key=lambda j: (j[0], j[1], j[2], j[3], j[5]))
    return sessions, jobs


def _et_span(a: dt.datetime, b: dt.datetime) -> str:
    return f"{a.astimezone(ET):%m-%d %H:%M:%S}-{b.astimezone(ET):%H:%M:%S} ET"


async def record(roots=ROOTS, dates: list[dt.date] | None = None,
                 base: Path = ARCHIVE, ws: TradovateWS | None = None,
                 now: dt.datetime | None = None, *, cache: dict | None = None,
                 day: bool | None = None, charts_usage: Path | None = None) -> list[dict]:
    """Fetch what the plan names, merging each piece into its session's archive
    file as it lands, then merge the live recordings no fetch touched. At night
    (outside 08:00-17:05 ET on weekdays) it runs until done or 08:00 and waits
    out a rate-limit reply; by day it spends at most DAY_PAGES pages, never
    inside 09:20-09:35 ET, and a rate-limit reply or a refused connection ends
    it until the next run. Says nothing when there is nothing to do. Returns
    the last manifest written per session."""
    now = now or now_et()
    day = deadline_passed(now) if day is None else day
    cache = {} if cache is None else cache
    dates = dates if dates is not None else candidate_dates(now)
    sessions, jobs = plan(roots, dates, base, now, cache)
    written: dict = {}
    if jobs:
        conn = ws if isinstance(ws, MDConn) else MDConn(ws, Budget(cache.setdefault(MD_USED, []),
                                                                    charts_usage, day))
        own = ws is None
        budget = DAY_PAGES if day else None
        grace = dt.timedelta(minutes=SESSION_GRACE_MIN)
        try:
            for expiry, _, _, date, key, s, e, why in jobs:
                st = sessions[key]
                root, contract = st["root"], st["contract"]
                if in_quiet(now_et()) or (budget is not None and budget <= 0):
                    break
                if not day and deadline_passed():
                    log(f"deadline {DEADLINE_ET} ET — the daytime runs take it from here")
                    break
                if now_et() >= expiry:
                    log(f"{root} {date} {contract} {_et_span(s, e)}: left the broker's history before its turn")
                    continue
                t0 = time.perf_counter()
                try:
                    rows, stats = await fetch_session(
                        conn, contract, s, e, expiry=expiry, max_pages=budget, deadline=not day,
                        halt=lambda: in_quiet(now_et()), penalty_stop=day)
                except Penalty as pen:
                    log(f"rate-limited ({pen}) — backing off until the next run")
                    break
                except BudgetSpent as bs:
                    log(f"{bs} — the next run goes on")
                    break
                except Exception as ex:  # noqa: BLE001 — one bad symbol must not stop the night
                    log(f"{root} {date} {contract} {_et_span(s, e)}: FAILED {ex}")
                    if day or not str(ex).startswith(f"{contract}:"):
                        break      # the connection (no token, a 429/502, no network): the next run retries
                    continue
                if budget is not None:
                    budget -= stats["pages"]
                entry = {"kind": "history", "from_utc": s.astimezone(UTC).isoformat(),
                         "to_utc": e.astimezone(UTC).isoformat(), "why": why, "stop": stats["stop"],
                         "pages": stats["pages"], "earliest_ms": stats["earliest_ms"]}
                empty = stats["stop"] == "exhausted" and stats["earliest_ms"] is None
                if empty:           # the broker answered nothing at all: believed the second time only
                    once = cache.setdefault(EMPTY_ONCE, {})
                    k = f"{root} {_ms(s)} {date}"
                    if once.pop(k, None) is not None:
                        entry["confirmed"] = True
                    else:
                        once[k] = tickarchive.now_utc()
                over = now_et() >= st["end"] + grace     # the live recording is final
                n = len(rows)
                fetched = [tickarchive.row_of(r) for r in rows]
                del rows                                 # one copy in memory, not two (ES: 1.2M ticks)
                man = store(root, date, contract, st["path"], st["start"], st["end"], fetched, entry,
                            include_live=over, cache=cache)
                del fetched
                if man is not None:
                    written[key] = man
                elif n == 0 and stats["stop"] in ("reached", "exhausted") and (not empty or entry.get("confirmed")):
                    # nothing there and no file to log it in: remember it, never ask again
                    lo = s if stats["stop"] == "reached" or stats["earliest_ms"] is None \
                        else _utc(stats["earliest_ms"])
                    cache.setdefault(ASKED, {}).setdefault(f"{root} {date}", []).append([_ms(lo), _ms(e)])
                log(f"{root} {date} {contract} {_et_span(s, e)} ({why}): {n:,} ticks, "
                    f"{stats['pages']} pages, {time.perf_counter() - t0:.0f}s ({stats['stop']})"
                    + ("" if man is None else f" — file {man['ticks']:,} ticks"
                       + ("" if man["complete"] else ", PARTIAL")))
        finally:
            if own:
                await conn.close()
    for man in promote_live(roots, base, now_et(), cache=cache):
        written[(man["root"], dt.date.fromisoformat(man["session_date"]))] = man
    return list(written.values())


def promote_live(roots, base: Path, now: dt.datetime, days: int = LIVE_LOOKBACK_DAYS,
                 cache: dict | None = None) -> list[dict]:
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
                if tickarchive.live_merged(tickarchive.load_manifest(path), tickarchive.live_stamp(lp)) \
                        or refused_still(cache, root, date, path):
                    continue
                man = store(root, date, contract, path, start, end, cache=cache)
                if man is not None:
                    live = next((s for s in reversed(man["sources"]) if s.get("kind") == "live"), {})
                    log(f"{root} {date} {contract}: live recording merged ({live.get('ticks', 0):,} ticks, "
                        f"{live.get('only_in_live', 0):,} the archive lacked) — file {man['ticks']:,} ticks"
                        + ("" if man["complete"] else ", PARTIAL"))
                    out.append(man)
    return out


class Busy(RuntimeError):
    """Another tick-archive run holds the lock."""


@contextlib.contextmanager
def archive_lock(path: Path):
    """One writer of the archive at a time (a run, --rescan, a manual fill):
    an exclusive lock on `path`, never waited for."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Busy(f"another tick-archive run holds {path} — try again when it is done") from None
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


REPORT_EVERY = dt.timedelta(hours=12)    # a run with nothing to do still refreshes the report this often


def coverage_report(roots, base: Path, sessions: int) -> None:
    """Write homebase/.state/tick_coverage.json and log its summary line; a
    failure here is logged, never raised (the run's data is already written)."""
    from . import tickcoverage                    # it imports this module
    try:
        tickcoverage.write_report(roots, base, now_et(), state_dir() / "tick_coverage.json", sessions)
    except Exception as e:  # noqa: BLE001
        log(f"coverage report failed: {type(e).__name__}: {e}")


def report_due(path: Path) -> bool:
    try:
        age = dt.datetime.now(UTC) - dt.datetime.fromtimestamp(path.stat().st_mtime, UTC)
    except OSError:
        return True
    return age >= REPORT_EVERY


def load_cache(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def prune_cache(cache: dict, now: dt.datetime, days: int = LIVE_LOOKBACK_DAYS + 5) -> None:
    """Forget files and sessions older than the live lookback (the cache only
    speeds up the runs; anything dropped is simply read again)."""
    cut = (now.astimezone(ET).date() - dt.timedelta(days=days)).isoformat()
    for k in [k for k in cache if not k.startswith("_") and (Path(k).name[:10] < cut or not Path(k).exists())]:
        del cache[k]
    for key in (ASKED, REFUSED, EMPTY_ONCE):
        d = cache.get(key, {})
        for k in [k for k in d if k.split(" ")[-1] < cut]:
            del d[k]


def fill_from_massive(a, roots, base: Path) -> int:
    from . import tickmassive                     # it imports this module
    dates = [dt.date.fromisoformat(x.strip()) for x in a.dates.split(",") if x.strip()] if a.dates else None
    kw = dict(dates=dates, since=dt.date.fromisoformat(a.since), include_fetchable=a.include_fetchable,
              raw=Path(a.raw_dir))
    try:
        if a.dry_run:
            tickmassive.fill(roots, base, now_et(), dry_run=True, **kw)
            return 0
        with archive_lock(state_dir() / "ticks.lock"):
            tickmassive.fill(roots, base, now_et(), **kw)
            coverage_report(roots, base, a.sessions)
    except Exception as e:  # noqa: BLE001 — Refused, the lock, the network: said, never a key in it
        log(f"massive: {type(e).__name__}: {e}")
        return 1
    return 0


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
    fm = ap.add_argument_group("Massive gap-fill (manual, off by default; homebase.tickmassive)")
    fm.add_argument("--fill-from-massive", action="store_true",
                    help="fill the archive from Massive flat files (env MASSIVE_S3_KEY / MASSIVE_S3_SECRET)")
    fm.add_argument("--holes", action="store_true",
                    help="every session since --since the coverage check finds missing or holed, "
                         "once the broker no longer has it")
    fm.add_argument("--dates", help="these session dates instead, YYYY-MM-DD[,YYYY-MM-DD...]")
    fm.add_argument("--since", default="2026-09-22", help="--holes: the first session to look at")
    fm.add_argument("--include-fetchable", action="store_true",
                    help="--holes: also what the broker's history still has")
    fm.add_argument("--dry-run", action="store_true",
                    help="list every file, hour and MB it would touch; download and write nothing")
    fm.add_argument("--raw-dir", default=str(Path.home() / "massive_raw"),
                    help="Massive's raw files, kept here (research/massive_ticks.py's layout)")
    a = ap.parse_args(argv)
    roots = tuple(r.strip().upper() for r in a.roots.split(",") if r.strip())
    base = Path(a.dir)
    if a.coverage:
        coverage_report(roots, base, a.sessions)
        return 0
    if a.fill_from_massive:
        if a.holes == bool(a.dates):
            ap.error("--fill-from-massive needs exactly one of --holes or --dates")
        return fill_from_massive(a, roots, base)
    if a.rescan:
        from . import tickcoverage
        try:
            with archive_lock(state_dir() / "ticks.lock"):
                n = tickcoverage.rescan(roots, base, now_et(), a.sessions)
                log(f"rescan: {n} manifest(s) rewritten with their hour-by-hour coverage")
                coverage_report(roots, base, a.sessions)
        except Busy as e:
            log(str(e))
            return 1
        return 0
    return run(roots, [dt.date.fromisoformat(a.date)] if a.date else None, base, a.sessions)


def run(roots, dates, base: Path, sessions: int = 30) -> int:
    """One run of the job (launchd: hourly, on load, 17:20 and 05:30): fetch
    and merge whatever is missing (record), then the coverage report when the
    run changed something or the last report is REPORT_EVERY old. Silent when
    there is nothing to do; never inside 09:20-09:35 ET; a run already in
    progress (the lock) is left to it."""
    if in_quiet(now_et()):
        return 0
    cache_path = state_dir() / "tick_runs.json"
    rc = 0
    try:
        with archive_lock(state_dir() / "ticks.lock"):
            cache = load_cache(cache_path)
            written: list = []
            try:
                written = asyncio.run(record(roots, dates, base, cache=cache,
                                             charts_usage=state_dir() / "charts" / "md_usage.json"))
            except Exception as e:  # noqa: BLE001
                log(f"run failed: {type(e).__name__}: {e}")
                rc = 1
            finally:
                try:
                    prune_cache(cache, now_et())
                    tickarchive.atomic_write(cache_path, json.dumps(cache).encode())
                except OSError as e:
                    log(f"could not save {cache_path.name}: {e}")
                if written or rc or report_due(state_dir() / "tick_coverage.json"):
                    coverage_report(roots, base, sessions)
    except Busy:
        return 0                                  # the run in progress does the work
    return rc


if __name__ == "__main__":
    sys.exit(main())
