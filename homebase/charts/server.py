"""The chart service: FastAPI on :8852 — the page, the websocket, layouts, drawings, templates,
status. Its own process; the trading app on :8850 only links to it.

    python -m homebase.charts                      # live, from the md feed
    python -m homebase.charts --replay 2026-09-24  # replay a session, records nothing
"""
from __future__ import annotations

import asyncio
import datetime as dt
from bisect import bisect_left
import json
import math
import os
import re
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .. import netguard, symbols
from ..contracts import tick_size as contract_tick_size
from ..paths import state_dir
from . import DEFAULT_ROOTS, DEPTH_RECORD_ROOTS, QUIET      # QUIET: never refill across the 9:30 fire
from .bars import BarSpec
from .barreplay import BarReplay
from .bursts import REACTION_ROOTS, BurstBook, ReactionBook, configured_roots
from .calendar import Calendar
from .depth import DEPTH_ARCHIVE, Depth, DepthRecorder
from .desk import Fanout, Quotes, register as register_desk
from .history import History
from .hub import Hub, Stream
from .news import News
from .paper import ROOT as PAPER_ROOT, STRATEGY_ID as PAPER_ID, BacktestJob, PaperRunner, describe as paper_describe
from .recorder import REFILL_MAX_PAGES, LiveRecorder, refill
from .replay import ReplayFeed
from .session import ET, always_open, et_wall_s, session_date, session_range_ms, split_by_session
from .store import ARCHIVE, TickStore
from .studies import make
from .tick import SideClassifier, from_row
from .tester_api import tester_router
from .tickfeed import TickFeed

STATIC = Path(__file__).resolve().parent.parent / "static"
PUMP_S = 0.25                 # <= 4 updates a second per chart
STATUS_S = 2.0                # a status to every page this often (the page greys it after 6 s without)
CLOSE_GRACE_MS = 1500         # a time bar closes this long after its end if no tick closed it
ROLL_GRACE_MS = 60_000        # a 24/7 root rolls at 18:00 with no dead hour: its old session's last
                              # prints can reach us after the clock passed 18:00 and are kept this long
REFILL_BUDGET = 60            # this process's own chart requests per hour
SEND_QUEUE_MAX = 400
PAPER_POLL_S = 0.25            # the paper runner is asked this often; it runs at most once a second
TIMEFRAMES = [["5s", "time:5"], ["15s", "time:15"], ["30s", "time:30"], ["1m", "time:60"],
              ["2m", "time:120"], ["3m", "time:180"], ["5m", "time:300"], ["10m", "time:600"],
              ["15m", "time:900"], ["30m", "time:1800"], ["1h", "time:3600"], ["4h", "time:14400"],
              ["1D", "time:86400"], ["500T", "tick:500"], ["1000T", "tick:1000"],
              ["2000V", "volume:2000"], ["10R", "range:10"], ["20R", "range:20"]]
MIN_BAR = {"time": 5, "tick": 100, "volume": 100, "range": 2}   # finer bars cost too much to build/ship
MAX_STUDIES = 16              # per subscription
LOCAL_HOSTS = ("localhost", "127.0.0.1")
MAX_DRAWINGS = 500            # per symbol
DRAWING_POINTS = {"trend": 2, "rect": 2, "hline": 1, "long": 3, "short": 3}
POSITION_QTY_MAX = 10_000     # a long/short box's quantity
MAX_TEMPLATE_BYTES = 16 * 1024   # one chart-settings template, as JSON
MAX_TEMPLATE_NAME = 40
_HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")


def log(msg: str) -> None:
    print(f"[charts] {dt.datetime.now(ET).strftime('%H:%M:%S')} {msg}", flush=True)


async def sleep(s: float) -> None:      # one seam for the tests to remove the waits
    await asyncio.sleep(s)


def origin_ok(origin: str | None, host: str | None) -> bool:
    """May a page from `origin` open /ws on `host`? Browsers apply no CORS
    to websocket handshakes, so without this any site open in the desk
    machine's browser could drive the chart process. Allowed: this
    service's own host, localhost, and no Origin at all (not a browser)."""
    if origin is None:
        return True
    try:
        o, h = urlsplit(origin).hostname, urlsplit("//" + (host or "")).hostname
    except ValueError:                  # e.g. a malformed IPv6 literal
        return False
    return o is not None and (o in LOCAL_HOSTS or o == h)


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _check_position(kind: str, pts: list) -> None:
    """A long/short box: [entry, target, stop], target and stop on the box's right edge (one t)."""
    entry, target, stop = (p["p"] for p in pts)
    if pts[1]["t"] != pts[2]["t"]:
        raise ValueError(f"a {kind}'s target and stop share the box's right edge (the same t)")
    if kind == "long" and not stop < entry < target:
        raise ValueError("a long has stop < entry < target")
    if kind == "short" and not target < entry < stop:
        raise ValueError("a short has target < entry < stop")


def check_drawings(body) -> list:
    """The page's drawings for one symbol, validated and stripped to what
    the page draws: [{id, type, points: [{t?, p}], color?, qty?}]. A long /
    short position is [entry, target, stop] with target and stop on the
    box's right edge (same t), stop < entry < target (long) or target <
    entry < stop (short), and an optional qty 1-10000 (kept for positions
    only). ValueError (with a message for the page) on anything else."""
    if not isinstance(body, list) or len(body) > MAX_DRAWINGS:
        raise ValueError(f"drawings are a list of at most {MAX_DRAWINGS}")
    out = []
    for d in body:
        if not isinstance(d, dict):
            raise ValueError("each drawing is an object")
        did, kind, pts = d.get("id"), d.get("type"), d.get("points")
        if not isinstance(did, str) or not 1 <= len(did) <= 40:
            raise ValueError("id: a string of 1-40 characters")
        n = DRAWING_POINTS.get(kind)
        if n is None:
            raise ValueError("type: trend, hline, rect, long or short")
        if not isinstance(pts, list) or len(pts) != n or not all(isinstance(p, dict) for p in pts):
            raise ValueError(f"a {kind} has exactly {n} point(s)")
        clean = []
        for p in pts:
            if not _finite(p.get("p")):
                raise ValueError("a point's p is a finite number")
            if kind == "hline":
                clean.append({"p": p["p"]})
                continue
            t = p.get("t")
            if not isinstance(t, int) or isinstance(t, bool):
                raise ValueError("a point's t is an integer (epoch ms)")
            clean.append({"t": t, "p": p["p"]})
        item = {"id": did, "type": kind, "points": clean}
        if kind in ("long", "short"):
            _check_position(kind, clean)
            if "qty" in d:
                q = d["qty"]
                if not isinstance(q, int) or isinstance(q, bool) or not 1 <= q <= POSITION_QTY_MAX:
                    raise ValueError(f"qty: a whole number from 1 to {POSITION_QTY_MAX}")
                item["qty"] = q
        if "color" in d:
            if not isinstance(d["color"], str) or not _HEX_COLOR.fullmatch(d["color"]):
                raise ValueError("color: #RRGGBB")
            item["color"] = d["color"]
        out.append(item)
    return out


def check_template_name(name) -> str:
    """A chart-settings template's name: 1-40 characters, no / \\ .. and no
    control characters (it rides in the URL path). ValueError otherwise."""
    if not isinstance(name, str) or not 1 <= len(name) <= MAX_TEMPLATE_NAME:
        raise ValueError(f"a template name has 1-{MAX_TEMPLATE_NAME} characters")
    if "/" in name or "\\" in name or ".." in name or any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise ValueError("a template name has no / \\ .. or control characters")
    return name


def _no_constant(c: str):
    """json.loads hook: NaN / Infinity are not JSON (the page's r.json() could not read them back)."""
    raise ValueError(f"{c} is not JSON")


class RevalidatedFiles(StaticFiles):
    """The page's files keep their URLs across builds, so a browser must never
    pair a new charts.html with a heuristically cached old app.js: every
    response says no-cache (always revalidate). The ETag / Last-Modified
    304 answer still keeps a reload cheap."""

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["cache-control"] = "no-cache"
        return resp


class Conn:
    """One browser socket. Sends go through a bounded queue drained by a
    writer task, so one slow page can never stall the pump; a page that
    falls SEND_QUEUE_MAX messages behind is disconnected (it reconnects)."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.q: asyncio.Queue = asyncio.Queue(maxsize=SEND_QUEUE_MAX)
        self.dead = False
        self.task = asyncio.create_task(self._writer())

    def send(self, msg: dict) -> None:
        if self.dead:
            return
        try:
            self.q.put_nowait(msg)
        except asyncio.QueueFull:
            self.dead = True
            self.task.cancel()
            asyncio.create_task(self._close())

    async def _close(self) -> None:
        try:
            await self.ws.close()
        except Exception:  # noqa: BLE001
            pass

    async def _writer(self) -> None:
        try:
            while True:
                await self.ws.send_json(await self.q.get())
        except Exception:  # noqa: BLE001 — socket gone; the handler cleans up
            self.dead = True


def create_app(*, roots=DEFAULT_ROOTS, base: Path = ARCHIVE, replay: dt.date | None = None,
               speed: float = 10.0, start_et: dt.time = dt.time(9, 25), feed_factory=None,
               now_ms=None, state: Path | None = None, calendar_fetch=None,
               desk_factory=None, fake_desk_factory=None, news_fetch=None, depth_roots=None,
               depth_base: Path | None = None, paper_day: bool = False,
               paper_backtest=None) -> FastAPI:
    if paper_day and not replay:
        raise ValueError("paper_day forces a REPLAYED date to be an event day: it needs replay")
    roots = [r.upper() for r in roots]
    sd = Path(state) if state else state_dir() / "charts"
    sd.mkdir(parents=True, exist_ok=True)
    layouts_path = sd / "layouts.json"
    drawings_path = sd / "drawings.json"
    templates_path = sd / "templates.json"
    # ForexFactory's calendar; calendar_fetch None never fetches (tests); python -m homebase.charts passes http_get
    cal = Calendar(sd / "calendar", fetch=calendar_fetch)
    # news.py: no fetching in replay mode, whatever the caller passes (a replayed price must never
    # look like it triggered a burst/reaction against a headline that broke long after that session)
    news_fetch = None if replay else news_fetch
    news_dir = sd / "news"
    news = News(news_dir, fetch=news_fetch)
    # bursts/reactions live in their own subfolders below news_dir (never loose files beside
    # news's own <date>.jsonl day files -- see news.py's docstring); news.near() is a bisect
    # lookup, called only on the rare tick that actually fires a burst, never on every tick
    burst_book = BurstBook(news_dir, [r for r in configured_roots() if r in roots], contract_tick_size, news.near)
    reaction_book = ReactionBook(news_dir, contract_tick_size)
    store = TickStore(base)
    history = History(store, cache_dir=sd / "cache")
    # forward PAPER test of the GC NFP+CPI straddle (paper.py): never an order; live only,
    # or a replay forced by --paper-day, which never reads or writes the forward runs.jsonl;
    # paper_backtest (python -m homebase.charts passes paper.spawn_backtest) computes the
    # cached 2021-2024 comparison once, via BacktestJob (never 08:00-10:00 ET, 15 min cap).
    # busy: the final run waits while GC's gap refill runs (up to 10:30 ET)
    paper = PaperRunner(None if replay else sd / "paper", cal,
                        enabled=PAPER_ROOT in roots and (not replay or paper_day),
                        force_day=replay if paper_day else None, persist=not replay, replay=bool(replay),
                        backtest_file=sd / "paper" / "backtest.json",
                        busy=lambda: PAPER_ROOT in refill_running or PAPER_ROOT in refill_pending, log=log)
    paper_job: list = []
    recorder = None if replay else LiveRecorder(base)
    conns: set[Conn] = set()
    quotes = Quotes()                     # bid/ask per root for the Buy/Sell buttons (desk.py)
    desk_fan = Fanout()                   # desk events fanned out to every page, bounded per page

    def fan(msg: dict) -> None:
        for c in list(conns):
            c.send(msg)

    if fake_desk_factory is not None and not replay:
        raise ValueError("fake_desk_factory is for replay only: a fake desk never runs beside the live feed")
    # the desk link: never in replay (a replayed price must never reach an order); a replay may link to the
    # FAKE desk only (browser checks, python -m homebase.charts --replay … --fake-desk PORT)
    if replay:
        link = fake_desk_factory(desk_fan.publish) if fake_desk_factory is not None else None
    else:
        link = desk_factory(desk_fan.publish) if desk_factory is not None else None
    if link is not None:
        desk_fan.hello = link.hello
    start_last: dict[str, int | None] = {}
    refill_lock = asyncio.Lock()          # one refill fetches at a time, across every root
    refill_pending: dict[str, dict] = {}  # root -> {frm, contract} while WAITING for the lock
    refill_running: set[str] = set()      # roots whose runner loop is alive (waiting or fetching)

    def reseed(root: str) -> None:
        """Rebuild today's tape for root from disk (after a refill). Runs on
        the loop and blocks it for a second or two — rare, and this process
        places no orders."""
        if recorder is not None:
            recorder.flush()
        d = session_date(clock(), root)
        sess = store.load(root, d)
        ticks = sess.ticks if sess else []
        hub.start_today(root, d, ticks, {
            "date": d.isoformat(), "contract": sess.contract if sess else symbols.resolve_contract(root),
            "source": "live", "approx": bool(sess and ticks and not sess.bid_ask),
            "gaps": [[et_wall_s(a), et_wall_s(b)] for a, b in (sess.gaps if sess else [])]})
        if root == PAPER_ROOT:
            try:        # a restart mid-window (or a gap refill) rebuilds the paper tape from the recording
                w = paper.window_ms(clock())    # [08:20, 09:56) on an event day, else None: O(log n) slice
                if w is not None:
                    i = bisect_left(ticks, w[0], key=lambda t: t.ts_ms)
                    j = bisect_left(ticks, w[1], lo=i, key=lambda t: t.ts_ms)
                    paper.seed(clock(), ((t.ts_ms * 1_000_000, t.price, t.size) for t in ticks[i:j]),
                               gaps=sess.gaps if sess else [])
            except Exception as e:  # noqa: BLE001 — paper work must never break the charts
                log(f"paper seed: {type(e).__name__}: {e}")

    async def _quiet_wait() -> None:
        while QUIET[0] <= dt.datetime.fromtimestamp(clock() / 1000, ET).time() < QUIET[1]:
            await sleep(15)

    async def _paced_sleep(s: float) -> None:
        """Passed to refill() as its own inter-page/penalty pacing hook: after
        every such pause, also hold until the clock clears the 9:30 fire.
        refill() paces slowly enough (~21s/page, longer after a penalty) that
        a run started just before 09:20 would otherwise keep paging deep into
        the quiet window — the one-time pre-check below only covers page 1."""
        await sleep(s)
        await _quiet_wait()

    async def _refill(root: str, contract: str, since_ms: int | None) -> None:
        """After a (re)subscribe: fetch what the socket missed, within
        budget. Serialized behind one lock, so the budget check made just
        before spending is never stale across roots (concurrent (re)connects
        can no longer all pass a check based on the same unspent number).

        Coalesced per root, but only while the request is still WAITING for
        the lock (widens it: the smaller frm, the latest contract — one
        fetch ends up covering both). A request that arrives once that
        root's refill is already RUNNING (holding the lock, mid-fetch)
        cannot be absorbed into it — that fetch's `to` was already fixed
        before this new request existed, so anything the new request needs
        after that `to` would otherwise be silently lost. Instead it becomes
        a follow-up: the same coroutine that started the run loops to pick
        it up once the current fetch finishes, with a fresh frm/contract/to
        of its own. Either way, no root ever runs two fetches concurrently."""
        d = session_date(clock(), root)
        s0, _ = session_range_ms(d, root)
        # The floor. A classic root never pages back past this session's open:
        # a `since` from the previous session (a weekend straggler, a drop
        # before the 17:00 close) would file that session's ticks as its live
        # file, which store.pick prefers to an incomplete archive -- and the
        # time between (the 17:00 hour, the weekend) trades nothing. A 24/7
        # root has no dead hour at its 18:00 roll and no nightly archive (its
        # live file is its only recording): a drop at 17:40 that is back at
        # 18:05 must still fetch 17:40-18:00, so its floor is the PREVIOUS
        # session's open (at most one session back). The recorder files each
        # row, and mark_gap below each missing piece, under its own session.
        floor = session_range_ms(d - dt.timedelta(days=1), root)[0] if always_open(root) else s0
        frm = max(since_ms if since_ms is not None else (start_last.get(root) or s0), floor)
        if root == PAPER_ROOT:
            paper.note_gap(frm, clock(), "reconnect")   # a hole until this refill resolves it
        waiting = refill_pending.get(root)
        if waiting is not None:
            waiting["frm"] = min(waiting["frm"], frm)
            waiting["contract"] = contract
            return
        refill_pending[root] = {"frm": frm, "contract": contract}
        if root in refill_running:
            return                      # a runner is already active for this root; it
                                         # will pick up this follow-up itself once it loops
        refill_running.add(root)
        try:
            while root in refill_pending:
                entry = refill_pending[root]
                await _quiet_wait()                     # covers page 1 (later pages: _paced_sleep)
                async with refill_lock:
                    del refill_pending[root]            # now RUNNING: a new request becomes a follow-up
                    await _quiet_wait()                 # may have queued past 09:20 for the lock
                    frm, contract = entry["frm"], entry["contract"]
                    to = clock()
                    if to - frm < 2000:
                        continue
                    rows: list[dict] = []
                    reached = to
                    pages = min(REFILL_MAX_PAGES, REFILL_BUDGET - feed.budget_used())
                    if pages > 0:
                        try:
                            rows, reached = await refill(feed.ws, contract, frm, to, max_pages=pages,
                                                           sleep=_paced_sleep, on_request=feed.count_request)
                        except Exception as e:  # noqa: BLE001 — the missing stretch becomes a marked gap
                            log(f"{root}: refill failed: {e}")
                    else:
                        log(f"{root}: refill skipped — md budget {feed.budget_used()}/h")
                    added = recorder.append(root, contract, rows)
                    if reached > frm:
                        for gd, a, b in split_by_session(root, frm, reached):
                            recorder.mark_gap(root, gd, contract, a, b)
                    log(f"{root}: refilled {len(rows)} ticks"
                        + (f", gap {(reached - frm) / 1000:.0f}s marked" if reached > frm else ""))
                    if added or reached > frm:
                        reseed(root)            # else nothing changed: no reload for every open chart
                        oldest = min((int(r["ts_ms"]) for r in added), default=None)
                        if oldest is not None and session_date(oldest, root) < session_date(clock(), root):
                            # rows landed in an older session (a 24/7 root's tail before its
                            # 18:00 roll), now on disk (reseed flushed): drop its memoized bars
                            history.clear()
        finally:
            refill_running.discard(root)
            refill_pending.pop(root, None)   # never leave a follow-up orphaned if we exit abnormally
            if root == PAPER_ROOT:
                paper.clear_pending()       # the reseeds above carried what could not be filled

    def paper_ticks(root: str, rows: list[dict]) -> None:
        if not rows:
            return
        try:
            paper.note_alive(int(rows[-1]["ts_ms"]))    # any root: the md socket is alive
            if root == PAPER_ROOT:
                paper.on_ticks(rows)
        except Exception as e:  # noqa: BLE001 — paper work must never break the live tick path
            log(f"paper ticks: {type(e).__name__}: {e}")

    # the feed is built AFTER reseed/_refill exist (it takes _refill as its
    # callback); every function above only touches feed/hub/clock when called
    if replay:
        def on_replay(root: str, contract: str, rows: list[dict]) -> None:
            if link is not None:
                quotes.note(root, rows)
            hub.on_ticks(root, rows)
            paper_ticks(root, rows)

        feed = ReplayFeed(store, roots, replay, on_replay, speed=speed, start_et=start_et)
        clock = feed.now_ms
    else:
        clock = now_ms or (lambda: int(time.time() * 1000))

        def on_live(root: str, contract: str, rows: list[dict]) -> None:
            # a print from an older session than the clock's (the one historical
            # trade a weekend subscribe returns) is neither recorded nor charted:
            # it would file a 1-tick stub for that session, which store.pick
            # prefers to an incomplete archive. Refill rows never come this way.
            # A 24/7 root has no dead hour at its 18:00 roll: its old session's
            # last prints stay acceptable for ROLL_GRACE_MS after it.
            now = clock()
            if always_open(root):
                now -= ROLL_GRACE_MS
            today = session_date(now, root)
            rows = [r for r in rows if session_date(int(r["ts_ms"]), root) >= today]
            quotes.note(root, rows)
            kept = recorder.append(root, contract, rows)
            hub.on_ticks(root, kept)
            paper_ticks(root, kept)
            if kept:
                try:
                    if root in burst_book.roots:
                        for r in kept:
                            fired = burst_book.push(root, int(r["ts_ms"]), float(r["price"]))
                            if fired is not None:
                                fan({"type": "burst", **fired})
                    if root in REACTION_ROOTS:
                        for r in kept:
                            reaction_book.push_tick(root, int(r["ts_ms"]), float(r["price"]))
                    reaction_book.flush_due(int(kept[-1]["ts_ms"]))
                except Exception as e:  # noqa: BLE001 — burst/reaction work must never break the live tick path
                    log(f"news/bursts ({root}): {type(e).__name__}: {e}")

        feed = (feed_factory or TickFeed)(roots, on_live, on_subscribed=_refill)
    # Level 2 rides the live feed's own md socket; replay builds none of it (no
    # subscriptions, no depth messages). Recorded: the depth roots this service charts.
    depth = None
    if not replay:
        rec_roots = [r for r in (DEPTH_RECORD_ROOTS if depth_roots is None else depth_roots)
                     if r.upper() in roots]
        depth = Depth(feed, rec_roots, log=log,
                      recorder=DepthRecorder(depth_base or DEPTH_ARCHIVE) if rec_roots else None)
    hub = Hub(history, clock)
    # per-chart Bar Replay: its own hubs over its own History memo; never the live hub, recorder, desk or quotes
    replays = BarReplay(store, sd / "cache", roots, lambda: clock(), min_bar=MIN_BAR,
                        max_studies=MAX_STUDIES, log=log)
    chart_error: list[str | None] = [None]     # the pump's chart work, failing right now

    def status() -> dict:
        st = dict(feed.status())
        if chart_error[0] and not st.get("error"):
            st["error"] = f"charts: {chart_error[0]}"   # the charts are frozen: say so
        st["recorder"] = None if recorder is None else {
            "written": recorder.written, "buffered": recorder.buffered, "error": recorder.error}
        st["depth"] = {} if depth is None else depth.status()
        st["depth_recorder"] = None if depth is None or depth.recorder is None else depth.recorder.status()
        if depth is not None and depth.error and not st.get("error"):
            st["error"] = f"depth: {depth.error}"
        st["streams"] = len(hub.streams)
        st["clients"] = len(conns)
        st["calendar"] = cal.status()
        st["news"] = news.status()
        st["bursts"] = burst_book.status()
        return st

    async def paper_loop() -> None:
        """The paper runner: run_session in a worker thread, at most once a second, only inside
        its window on an event day (PaperRunner.due decides); every change goes to every page."""
        while True:
            await asyncio.sleep(PAPER_POLL_S)       # not the `sleep` seam: tests patch it to 0
            try:
                now = clock()
                if paper.due(now):
                    msg = await asyncio.to_thread(paper.step, now)
                    if msg is not None:
                        fan(msg)
            except Exception as e:  # noqa: BLE001 — the paper runner must never take the service down
                log(f"paper: {type(e).__name__}: {e}")

    older_busy: set = set()     # (conn, chart id, stream identity) with a scroll-back chunk being built --
                                # keyed by the STREAM (not just conn/cid) so a fresh subscription after an
                                # interval switch is never blocked by the old stream's still-running chunk
    older_tasks: set = set()    # the answering tasks, referenced until they finish

    def ask_older(conn: Conn, cid: str, before) -> None:
        """A chart scrolled back to its first bar ({"op": "older", "id", "before": that bar's ms}): build the
        next chunk of older sessions off the loop and answer {"type": "older", "id", "before", "bars",
        "studies", "repair", "sessions", "done"}, or with an "error" (the page waits, then may ask again).
        One at a time per chart+stream; it never touches the broker. A request that lands while the
        previous one for the same chart+stream is still building answers {"error": "busy"} rather than
        being silently dropped, so the page can retry instead of the chart losing scroll-back forever."""
        s = hub.stream_of((conn, cid))
        if s is None or not isinstance(before, int) or isinstance(before, bool):
            conn.send({"type": "older", "id": cid, "before": before,
                       "error": "not subscribed" if s is None else "before: the first bar's time (epoch ms)"})
            return
        key = (conn, cid, id(s))
        if key in older_busy:
            conn.send({"type": "older", "id": cid, "before": before, "error": "busy"})
            return
        older_busy.add(key)
        task = asyncio.create_task(answer_older(conn, cid, key, s, before))
        older_tasks.add(task)
        task.add_done_callback(older_tasks.discard)

    async def answer_older(conn: Conn, cid: str, key: tuple, s: Stream, before: int) -> None:
        try:
            ans = await asyncio.to_thread(hub.older, s, before)
        except Exception as e:  # noqa: BLE001 — a failed chunk is the page's to retry, never the socket's end
            log(f"older {cid} ({s.root} {s.spec.key}): {type(e).__name__}: {e}")
            ans = {"error": str(e) or type(e).__name__}
        finally:
            older_busy.discard(key)
        conn.send({"type": "older", "id": cid, "before": before, **ans})

    async def pump() -> None:
        last_flush = last_status = 0.0
        while True:
            await asyncio.sleep(PUMP_S)
            wall = time.monotonic()
            if recorder is not None and wall - last_flush >= 1.0:
                try:
                    recorder.flush()
                except Exception as e:  # noqa: BLE001 — recording must not depend on chart work below
                    log(f"pump flush: {type(e).__name__}: {e}")
                last_flush = wall
            try:
                hub.on_clock(clock() - CLOSE_GRACE_MS)
                for (conn, cid), msg in hub.drain():
                    conn.send({**msg, "id": cid})
                for m in quotes.drain():
                    fan(m)
                desk_fan.flush()
                replays.pump()
                chart_error[0] = None
            except Exception as e:  # noqa: BLE001 — the pump must never die
                chart_error[0] = f"{type(e).__name__}: {e}"
                log(f"pump: {chart_error[0]}")
            if wall - last_status >= STATUS_S:
                # its own try: a persistent chart failure above must not freeze
                # every page's status strip on its last (green) message
                last_status = wall
                try:
                    st = {"type": "status", **status()}
                    for c in list(conns):
                        c.send(st)
                except Exception as e:  # noqa: BLE001
                    log(f"pump status: {type(e).__name__}: {e}")

    async def news_loop() -> None:
        """The two news feeds, each on its own 60 s floor (News.poll() enforces
        it per source); never faster, and never at all without news_fetch
        (replay, or a test that passes none)."""
        while True:
            try:
                for item in await asyncio.to_thread(news.poll):
                    fan({"type": "news", **item})
                    reaction_book.add_item(item)
                    for updated in burst_book.link_news(item):    # a headline that arrived after its burst
                        fan({"type": "burst_update", **updated})
            except Exception as e:  # noqa: BLE001 — the news feed must never take the service down
                log(f"news: {type(e).__name__}: {e}")
            await asyncio.sleep(5.0)

    async def calendar_loop() -> None:
        """The calendar at startup, then hourly (30 min after a failure); never faster: FF blocks polling."""
        while True:
            try:
                await asyncio.to_thread(cal.refresh)
            except Exception as e:  # noqa: BLE001 — the calendar must never take the service down
                log(f"calendar: {type(e).__name__}: {e}")
            await asyncio.sleep(max(cal.wait_s(), 60.0))    # not the `sleep` seam: tests patch it to 0

    @asynccontextmanager
    async def lifespan(_app):
        if replay:
            for r, rs in feed.load().items():
                if r == PAPER_ROOT:
                    try:        # --paper-day: the session so far, like a live restart's reseed
                        w = paper.window_ms(clock())
                        if w is not None:
                            i = bisect_left(rs, w[0], key=lambda x: int(x["ts_ms"]))
                            j = bisect_left(rs, w[1], lo=i, key=lambda x: int(x["ts_ms"]))
                            paper.seed(clock(), ((int(x["ts_ns"]) if x.get("ts_ns") else int(x["ts_ms"]) * 1_000_000,
                                                  float(x["price"]), int(x.get("size") or 0)) for x in rs[i:j]))
                    except Exception as e:  # noqa: BLE001 — paper work must never break the charts
                        log(f"paper seed: {type(e).__name__}: {e}")
                clf = SideClassifier()
                hub.start_today(r, replay, [from_row(x, clf) for x in rs], {
                    "date": replay.isoformat(), "contract": feed.contracts.get(r),
                    "source": "replay", "approx": False, "gaps": []})
        else:
            for r in roots:
                d, contract = session_date(clock(), r), symbols.resolve_contract(r)
                last = recorder.last_ts(r, d, contract)
                if last is None and always_open(r):
                    # just past a 24/7 root's 18:00 roll: resume from the old session's tail
                    last = recorder.last_ts(r, d - dt.timedelta(days=1), contract)
                start_last[r] = last
                reseed(r)
        tasks = [asyncio.create_task(pump()), asyncio.create_task(feed.run())]
        if calendar_fetch is not None:
            tasks.append(asyncio.create_task(calendar_loop()))
        if news_fetch is not None:
            tasks.append(asyncio.create_task(news_loop()))
        if link is not None:
            tasks.append(asyncio.create_task(link.run()))
        if depth is not None:
            tasks.append(asyncio.create_task(depth.run()))
        if paper.enabled:
            tasks.append(asyncio.create_task(paper_loop()))
        if paper_backtest is not None:
            job = BacktestJob(sd / "paper", paper_backtest, clock, log)
            paper_job.append(job)

            async def backtest_job() -> None:
                try:
                    await job.run()
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001 — the comparison is optional
                    log(f"paper backtest: {type(e).__name__}: {e}")

            tasks.append(asyncio.create_task(backtest_job()))
        log(f"up — {'replay ' + replay.isoformat() if replay else 'live'} · {', '.join(roots)}")
        try:
            yield
        finally:
            feed.stop()
            if depth is not None:
                depth.stop()
            if link is not None:
                link.stop()             # stop() alone can't interrupt a blocked read; the
                                         # cancel below (link.run() is in `tasks`) does that
            for t in tasks:
                t.cancel()
            if recorder is not None:
                recorder.flush()
            if depth is not None:
                await depth.aclose()    # cancels its requests in flight; the recording's last member
            tester.manager.shutdown()   # never leave a runner child orphaned
            for job in paper_job:       # nor the paper comparison's (terminated and reaped)
                job.stop()

    app = FastAPI(title="Homebase Charts", lifespan=lifespan)
    app.mount("/static", RevalidatedFiles(directory=STATIC), name="static")

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "charts.html", headers={"cache-control": "no-cache"})

    @app.get("/api/status")
    async def api_status():
        return status()

    @app.get("/api/symbols")
    async def api_symbols():
        return {"roots": roots, "timeframes": TIMEFRAMES}

    def read_json(path: Path) -> dict:
        try:
            v = json.loads(path.read_text())
        except (OSError, ValueError):
            return {}
        return v if isinstance(v, dict) else {}

    def write_json(path: Path, data: dict) -> None:
        """Via a temp file + atomic rename: a crash or a full disk mid-write
        must never tear the file (torn, it reads back as {} and the next
        save would wipe everything in it)."""
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, path)

    def browser_write_ok(request: Request) -> None:
        """Browsers send a cross-site PUT/DELETE after a preflight that this
        app never answers, but a simple no-CORS request could still reach
        us; refuse any write from a page that is not this service's own
        (same rule as the /ws handshake)."""
        if not origin_ok(request.headers.get("origin"), request.headers.get("host")):
            raise HTTPException(403, "writes from another site are refused")

    def known_root(root: str) -> str:
        r = root.upper()
        if r not in roots:
            raise HTTPException(404, f"{root!r} is not a charted symbol")
        return r

    register_desk(app, link=link, quotes=quotes, browser_write_ok=browser_write_ok)
    tester = tester_router(browser_write_ok, base, Path(state) / "tester" if state else None)
    app.include_router(tester)

    @app.get("/api/layouts")
    async def get_layouts():
        return read_json(layouts_path)

    @app.put("/api/layouts/{name:path}")
    async def put_layout(name: str, request: Request):
        browser_write_ok(request)
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("cells"), list):
            raise HTTPException(400, "a layout is {grid, cells: [...]}")
        all_ = read_json(layouts_path)
        all_[name] = body
        write_json(layouts_path, all_)
        return {"ok": True}

    @app.delete("/api/layouts/{name:path}")
    async def delete_layout(name: str, request: Request):
        browser_write_ok(request)
        all_ = read_json(layouts_path)
        all_.pop(name, None)
        write_json(layouts_path, all_)
        return {"ok": True}

    @app.get("/api/drawings/{root}")
    async def get_drawings(root: str):
        return read_json(drawings_path).get(known_root(root), [])

    @app.put("/api/drawings/{root}")
    async def put_drawings(root: str, request: Request):
        browser_write_ok(request)
        r = known_root(root)
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "the body is not JSON") from None
        try:
            clean = check_drawings(body)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        all_ = read_json(drawings_path)
        all_[r] = clean
        write_json(drawings_path, all_)
        return {"ok": True, "count": len(clean)}

    @app.get("/api/templates")
    async def get_templates():
        return read_json(templates_path)

    @app.put("/api/templates/{name:path}")
    async def put_template(name: str, request: Request):
        browser_write_ok(request)
        try:
            check_template_name(name)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        raw = await request.body()
        if len(raw) > MAX_TEMPLATE_BYTES:
            raise HTTPException(400, f"a template is at most {MAX_TEMPLATE_BYTES // 1024} KB of JSON")
        try:
            body = json.loads(raw, parse_constant=_no_constant)
        except ValueError:
            raise HTTPException(400, "the body is not JSON") from None
        if not isinstance(body, dict):
            raise HTTPException(400, "a template is a JSON object of chart settings")
        all_ = read_json(templates_path)
        all_[name] = body
        write_json(templates_path, all_)
        return {"ok": True}

    @app.delete("/api/templates/{name:path}")
    async def delete_template(name: str, request: Request):
        browser_write_ok(request)
        all_ = read_json(templates_path)
        all_.pop(name, None)
        write_json(templates_path, all_)
        return {"ok": True}

    @app.get("/api/paper/strategies")
    async def paper_strategies():
        return [paper_describe()]

    @app.get("/api/paper/history")
    async def paper_history(strategy: str = PAPER_ID):
        if strategy != PAPER_ID:
            raise HTTPException(404, f"no paper strategy {strategy!r}")
        return paper.history()

    @app.get("/api/calendar")
    async def api_calendar(request: Request):
        q = request.query_params
        try:
            frm, to = int(q.get("from", 0)), int(q.get("to", 2 ** 62))
        except ValueError:
            raise HTTPException(400, "from / to: epoch ms") from None
        countries = [c.strip() for c in q.get("countries", "").split(",") if c.strip()]
        return cal.events(frm, to, countries or None)

    @app.get("/api/news")
    async def api_news(request: Request):
        bad = netguard.refusal(request.method, request.scope["headers"], netguard.allowlist())
        if bad is not None:
            raise HTTPException(*bad)
        q = request.query_params
        try:
            frm, to = int(q.get("from", 0)), int(q.get("to", 2 ** 62))
        except ValueError:
            raise HTTPException(400, "from / to: epoch ms") from None
        tags = [t.strip() for t in q.get("tags", "").split(",") if t.strip()]
        sources = [s.strip() for s in q.get("sources", "").split(",") if s.strip()]
        return news.items(frm, to, tags or None, sources or None)

    @app.websocket("/ws")
    async def ws_endpoint(sock: WebSocket):
        if not origin_ok(sock.headers.get("origin"), sock.headers.get("host")):
            await sock.close(code=1008)     # before accept(): the handshake is refused (403)
            return
        if not netguard.host_allowed(sock.headers.get("host"), netguard.allowlist()):
            # origin_ok() alone waves through a DNS-rebinding page: it is
            # served AS the attacker's own hostname, so its Origin and Host
            # both read e.g. evil.example and satisfy origin_ok's Origin==Host
            # rule. This service now carries balances, positions and orders
            # for every account, so the Host header itself must also be on
            # netguard's shared allowlist (loopback only here -- this
            # process has no cfg.allowed_hosts of its own) before the
            # handshake is accepted.
            await sock.close(code=1008)
            return
        await sock.accept()
        conn = Conn(sock)
        conns.add(conn)
        conn.send({"type": "status", **status()})
        if paper.current is not None:
            conn.send(paper.current)            # the paper run's state, like every later change
        def room() -> bool:
            return not conn.dead and conn.q.qsize() < SEND_QUEUE_MAX // 2

        desk_fan.attach(conn, conn.send, room)
        try:
            while True:
                # Only a framing/decoding problem is swallowed here. Receiving
                # itself is NOT wrapped in a broad except: after an app-side
                # close (Conn._close(), on a SEND_QUEUE_MAX overflow), starlette
                # raises WebSocketDisconnect OR a RuntimeError SYNCHRONOUSLY --
                # before any await -- so a broad `except Exception: continue`
                # around the receive call would never yield control back to the
                # loop, spinning it at 100% CPU forever instead of ending here.
                try:
                    raw = await sock.receive_text()
                except (WebSocketDisconnect, RuntimeError):
                    raise
                except Exception:  # noqa: BLE001 — a non-text (binary) frame is skipped
                    continue
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                op, cid = msg.get("op"), str(msg.get("id", ""))
                if op == "unsub":
                    replays.stop(conn, cid, notify=False)
                    hub.unsubscribe((conn, cid))
                    if depth is not None:
                        depth.unview((conn, cid))
                    continue
                if op == "older":
                    if not replays.ask_older(conn, cid, msg.get("before")):
                        ask_older(conn, cid, msg.get("before"))
                    continue
                if op == "replay_start":
                    if await replays.start(conn, cid, msg, live=hub.stream_of((conn, cid))):
                        hub.unsubscribe((conn, cid))    # the chart leaves the live stream
                    continue
                if op == "replay_ctl":
                    await replays.control(conn, cid, msg)
                    continue
                if op == "replay_stop":
                    replays.stop(conn, cid)
                    continue
                if op != "sub":
                    continue
                try:
                    root = str(msg.get("root", "")).upper()
                    if root not in roots:
                        raise ValueError(f"{root!r} is not recorded (have {', '.join(roots)})")
                    spec = BarSpec.parse(msg.get("spec", ""))
                    if spec.size < MIN_BAR[spec.kind]:
                        raise ValueError(f"{spec.key} is too fine for the live charts "
                                         f"(minimum {spec.kind}:{MIN_BAR[spec.kind]})")
                    studies = msg.get("studies") or []
                    if len(studies) > MAX_STUDIES:
                        raise ValueError(f"{len(studies)} studies on one chart (at most {MAX_STUDIES})")
                    keys = [str(k) for k in studies]
                    for k in keys:
                        if k != "profile":
                            make(k)     # ValueError on an unknown study or a length outside 1..1000
                except Exception as e:  # noqa: BLE001 — a malformed sub (bad root/spec/study, too
                                        # fine, too many) answers an error, never kills the connection
                    conn.send({"type": "error", "id": cid, "error": str(e)})
                    continue
                s = None
                replays.stop(conn, cid, notify=False)   # a sub on a replaying chart returns it to live
                try:
                    hub.unsubscribe((conn, cid))
                    s = hub.streams.get((root, spec.key))
                    if s is None:
                        s = hub.attach(await asyncio.to_thread(hub.prepare, root, spec, keys))
                    for k in keys:
                        s.add_study(k)
                    hub.subscribe(s, (conn, cid))
                    conn.send({"type": "history", "id": cid, **s.payload(bool(msg.get("fp", True)))})
                    if depth is not None:
                        depth.view((conn, cid), root, conn.send, room)   # after `history`: depth follows it
                except Exception as e:  # noqa: BLE001 — an unexpected failure building the
                                        # stream must not drop every chart on the page either
                    log(f"sub {cid} ({root} {spec.key}): {type(e).__name__}: {e}\n{traceback.format_exc()}")
                    conn.send({"type": "error", "id": cid, "error": str(e)})
                    # never leave this id subscribed to a stream it only got an
                    # error for (the pump would keep sending it `update`s for
                    # an id that never got `history`), and never leave a
                    # freshly attached, now-subscriberless stream in hub.streams
                    hub.unsubscribe((conn, cid))
                    if depth is not None:
                        depth.unview((conn, cid))
                    if s is not None and not s.subs and hub.streams.get(s.key) is s:
                        del hub.streams[s.key]
                    continue
        except (WebSocketDisconnect, RuntimeError):
            # RuntimeError: starlette raises this on the receive loop if Conn's
            # writer already closed the socket out from under us (SEND_QUEUE_MAX
            # overflow) -- same clean-up as an ordinary client disconnect.
            pass
        finally:
            conns.discard(conn)
            desk_fan.detach(conn)
            if depth is not None:
                depth.drop_conn(conn)
            hub.drop_conn(conn)
            replays.drop_conn(conn)
            conn.task.cancel()

    return app
