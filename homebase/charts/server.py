"""The chart service: FastAPI on :8852 — the page, the websocket, layouts, drawings, templates,
status. Its own process; the trading app on :8850 only links to it.

    python -m homebase.charts                      # live, from the md feed
    python -m homebase.charts --replay 2026-09-24  # replay a session, records nothing
"""
from __future__ import annotations

import asyncio
import datetime as dt
import fcntl
from bisect import bisect_left
import json
import math
import os
import re
import signal
import threading
import time
import traceback
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketClose

from .. import netguard, symbols
from ..data import ticks as T
from ..contracts import tick_size as contract_tick_size
from ..paths import state_dir
from . import DEFAULT_ROOTS, DEPTH_RECORD_ROOTS
from .bars import BarSpec
from .barreplay import BarReplay
from .bookhist import MAX_SPAN_MS as BOOK_MAX_SPAN_MS, BookPool
from .booklive import BookLive
from .bursts import REACTION_ROOTS, BurstBook, ReactionBook, configured_roots
from .calendar import Calendar
from .depth import DEPTH_ARCHIVE, Depth, DepthRecorder
from .depthrelay import RelayFeed
from .depthgrid import (MAX_COLS as DEPTH_MAX_COLS, MAX_SPAN_MS as DEPTH_MAX_SPAN_MS, Busy, HistoryPool, Paused,
                        paused_reason)
from .desk import Fanout, Quotes, register as register_desk
from .export import export_router
from .refresh import refresh_router
from .history import History
from .hub import Hub, Stream
from .known import Known
from . import lagwatch
from .news import News
from .paper import ROOT as PAPER_ROOT, STRATEGY_ID as PAPER_ID, BacktestJob, PaperRunner, describe as paper_describe
from .paperbook import DESK_ORIGINS, PaperBooks, _cors, desk_origin_refusal, is_paper_id, register as register_paperbook
from .exitrunner import ExitRunner, register as register_exitrunner
from .pineapi import routes as pine_routes
from .presets import MAX_PRESET_BYTES, PresetsStore
from .recorder import REFILL_MAX_PAGES, LiveRecorder, refill
from .replay import ReplayFeed
from .session import ET, always_open, et_wall_s, session_date, session_range_ms, split_by_session
from .settings_store import CLOCK_CHOICES, MD_CHOICES, SettingsStore, md_only
from .store import ARCHIVE, TickStore, splice_tail
from .studies import make
from .tapelive import TapeLive
from .tick import SideClassifier, from_row
from .tester_api import tester_router
from .tickfeed import MD_ENVS, SwitchInProgress, TickFeed, session_contract
from . import routes
# moved to routes/ (2026-10-26 split): still importable from here, as tests and callers do
from .routes.common import LOCAL_HOSTS, browser_write_ok, origin_ok, read_json, read_json_list, write_json  # noqa: F401
from .routes.drawings import (  # noqa: F401
    DRAWING_CAPS, DRAWING_LABEL_ALIGN, DRAWING_LABEL_POS, DRAWING_LINE_STYLES, DRAWING_POINTS, DRAWING_STYLE_BOOLS,
    DRAWING_STYLE_FIELDS, DRAWING_VIS_MAX_S, FIB_MAX, FIB_MIN, MAX_DRAWING_LABEL_TEXT, MAX_DRAWING_WIDTH, MAX_DRAWINGS,
    MAX_FIB_LEVELS, MAX_TEMPLATE_BYTES, MAX_TEMPLATE_NAME, POSITION_QTY_MAX, _BOX_POS, _HEX_COLOR, _LINE_POS, _POS_FIELDS,
    _RGBA_COLOR, _TEXT_FIELDS, _check_levels, _check_position, _finite, _no_constant, _valid_color, check_alert,
    check_drawings, check_style, check_template_name, check_vis)
from .routes.pages import TIMEFRAMES, _TickStream  # noqa: F401
from .routes.settings import (BOT_BUSY_STATUSES, MD_SWITCH_BUDGET_HEADROOM, MD_SWITCH_COOLDOWN_S)  # noqa: F401
from .routes.ws import SEND_QUEUE_MAX, Conn  # noqa: F401

STATIC = Path(__file__).resolve().parent.parent / "static"
PUMP_S = 0.25                 # <= 4 updates a second per chart
PAPER_PUSH_GAP_S = 0.05       # a PAPER account change reaches the pages at once, at most one push per 50 ms
STATUS_S = 2.0                # a status to every page this often (the page greys it after 6 s without)
CLOSE_GRACE_MS = 1500         # a time bar closes this long after its end if no tick closed it
ROLL_GRACE_MS = 60_000        # a 24/7 root rolls at 18:00 with no dead hour: its old session's last
                              # prints can reach us after the clock passed 18:00 and are kept this long
REFILL_BUDGET = 60            # this process's own chart requests per hour
REFILL_RESERVE = 30           # ... and this many more, for NQ and ES only (the 180/h login is shared with the tick job: cap 150)
REFILL_FIRST = ("NQ", "ES")
WARM_EVERY_S = 120.0          # the Desk results pre-warm repeats this often (saved runs only; a run already scored is a cache hit)
REPAIR_POLL_S = 60.0           # how often today's archive files are stat'ed for a repair that landed (a stat per root)
PAST_REDRAW_S = 600.0          # a root's charts reload for a repaired PAST session at most this often: a fill lands piece
                               # by piece (a merge every few minutes), and each reload rebuilds every chart of the root
REPAIR_SPLICE_MS = 600_000     # the hub tape's ticks this recent (before a repair load began) may still be unflushed/new
PAPER_POLL_S = 0.25            # the paper runner is asked this often; it runs at most once a second
LABRUN_QUEUE_MAX = 2000        # live batches a reader of /api/labrun/ticks may fall behind before it is dropped
LABRUN_CHUNK = 5000            # backlog rows in one of its events
LABRUN_CLOCK_S = 1.0           # its clock event, which is also its heartbeat
MIN_BAR = {"time": 5, "tick": 100, "volume": 100, "range": 2}   # finer bars cost too much to build/ship
MAX_STUDIES = 16              # per subscription
MD_SWITCH_TIMEOUT_S = 600          # N3: the PUT never waits longer than this for the feed (routes/settings.py reads it here)


def tick_job_running() -> bool:
    """True while the tick job (hourly, or a Refresh) holds its lock: homebase.ticks.archive_lock."""
    try:
        with open(state_dir() / "ticks.lock", "a") as f:
            fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)   # released at close; the job never waits for it
    except BlockingIOError:
        return True
    except OSError:
        pass
    return False



def log(msg: str) -> None:
    print(f"[charts] {dt.datetime.now(ET).strftime('%H:%M:%S')} {msg}", flush=True)


async def sleep(s: float) -> None:      # one seam for the tests to remove the waits
    await asyncio.sleep(s)



class HostGuard:
    """Final review M4: ONE Host check, netguard's shared allowlist (loopback
    only here -- this process has no allowed_hosts of its own), on EVERY
    /api/* request (GET included: layouts and templates carry a chart's trade
    accounts and algo) and on every websocket handshake (/ws), as the desk's
    own desk_api.WriteGuard does. A DNS-rebound page arrives with Host:
    evil.example and satisfies origin_ok's Origin==Host rule, so the Host
    itself must be checked. Writes keep their own Origin (browser_write_ok) and
    -- on the desk proxy -- JSON checks behind this. Pure ASGI: what passes goes
    straight through (the page and /static are left alone)."""

    def __init__(self, app, allowed: frozenset | None = None):
        self.app, self.allowed = app, allowed if allowed is not None else netguard.allowlist()

    def _refused(self, scope) -> bool:
        # method "GET": netguard.refusal() then checks the Host only (exactly one, on the allowlist)
        return netguard.refusal("GET", scope["headers"], self.allowed) is not None

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "websocket" and self._refused(scope):
            await WebSocketClose(code=1008, reason="host not allowed")(scope, receive, send)
            return
        path = scope.get("path", "")
        if scope["type"] == "http" and (path == "/api" or path.startswith("/api/")) and self._refused(scope):
            await JSONResponse({"detail": "host not allowed"}, 403)(scope, receive, send)
            return
        await self.app(scope, receive, send)


class RevalidatedFiles(StaticFiles):
    """The page's files keep their URLs across builds, so a browser must never
    pair a new charts.html with a heuristically cached old app.js: every
    response says no-cache (always revalidate). The ETag / Last-Modified
    304 answer still keeps a reload cheap."""

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["cache-control"] = "no-cache"
        return resp


def server_stopping(getsignal=signal.getsignal) -> bool:
    """True once this process was told to stop. uvicorn waits for every open response before it runs the lifespan's
    clean-up, and has no timeout here (python -m homebase.charts): a response that never ends would hold the
    shutdown open for good -- no last recorder flush, backtest children left running. So the one endless response
    of this service (TickFan.stream) asks, and ends. Read-only: uvicorn's own flag, through the SIGTERM handler it
    installs (Server.handle_exit; tests/test_charts_labrun_stream.py pins both). No uvicorn: False."""
    return bool(getattr(getattr(getsignal(signal.SIGTERM), "__self__", None), "should_exit", False))


def _sse(data, event: str = "") -> str:
    return (f"event: {event}\n" if event else "") + f"data: {json.dumps(data, separators=(',', ':'))}\n\n"


def _backlog_rows(root: str, tape: list, i: int, j: int) -> str:
    """Worker thread: one backlog event from today's tape (a list of Tick that only ever grows at its end)."""
    return _sse({"root": root, "rows": [[t.ts_ms, t.price, t.size, t.side] for t in tape[i:j]]})


def _live_rows(root: str, ticks: list, event: str = "") -> str:
    """One live batch: the hub's classified prints (charts/tick.py Tick), in the order it took them. event "refill": the
    prints a reconnect's gap fill found, OLDER than what the reader already holds (it must take them, not drop them)."""
    return _sse({"root": root, "rows": [[t.ts_ms, t.price, t.size, t.side] for t in ticks]}, event)


class _TickReader:
    __slots__ = ("roots", "q", "dropped")

    def __init__(self, roots):
        self.roots = frozenset(roots)
        self.q: asyncio.Queue = asyncio.Queue(maxsize=LABRUN_QUEUE_MAX)
        self.dropped = False


class TickFan:
    """The prints of this service as a read-only stream for the Lab strategy runner (GET /api/labrun/ticks, Server-
    Sent Events). Rows are [ts_ms, price, size, side]: side as the hub classified the print (+1 at the ask, -1 at the bid;
    charts/tick.py), so a Desk strategy reads the delta the charts show. publish() is called from the tick path and costs it one queue put per reader: nothing is copied,
    encoded or awaited there, and it cannot raise. A reader that falls LABRUN_QUEUE_MAX batches behind is dropped
    (its stream ends; it asks again with since_ms). clock: the service's (the replay's, in a replay). tape_of(root):
    today's tape, the hub's list of Tick, or None."""

    def __init__(self, clock, tape_of, stopping=None):
        self.clock, self.tape_of = clock, tape_of
        self.stopping = stopping or (lambda: server_stopping())
        self.readers: set = set()

    def publish(self, root: str, rows: list) -> None:
        if not rows or not self.readers:
            return
        try:
            for rd in list(self.readers):
                if root in rd.roots:
                    try:
                        rd.q.put_nowait((root, rows))
                    except asyncio.QueueFull:
                        rd.dropped = True
                        self.readers.discard(rd)
        except Exception as e:  # noqa: BLE001 — a reader must never break the live tick path
            log(f"labrun ticks: {type(e).__name__}: {e}")

    def publish_refill(self, root: str, rows: list) -> None:
        """publish() for the prints a gap refill added after the fact: an `event: refill` batch."""
        if not rows or not self.readers:
            return
        for rd in list(self.readers):
            if root in rd.roots:
                try:
                    rd.q.put_nowait((root, rows, "refill"))
                except asyncio.QueueFull:
                    rd.dropped = True
                    self.readers.discard(rd)

    async def stream(self, roots: list, since_ms: int, clock_s: float | None = None):
        """The backlog -- each market's prints of the current session with ts_ms >= since_ms, oldest first, at most
        LABRUN_CHUNK rows an event, built in a worker thread; then the prints that queued up behind it; `event: live`
        once; then `event: clock` {"now_ms"} at once and every clock_s, and the live batches as they arrive. Rows are
        [ts_ms, price, size, side].

        A `live` or a clock is NEVER sent while prints that arrived before it are still queued for this reader: the
        runner takes `live` for "the tape is whole" and fires an event "with no print" off the clock, so either one
        ahead of its prints would act on a tape that is a queue short. A reader that was dropped gets neither: its
        stream just ends."""
        clock_s = LABRUN_CLOCK_S if clock_s is None else clock_s
        loop = asyncio.get_running_loop()
        rd = _TickReader(roots)
        # The live queue first, then how far each tape goes -- in ONE turn of the loop, the turn the tick path cannot
        # interleave with: a print is in a tape below `n` (the backlog) or is fanned out after this line (the queue).
        # None is missing and none comes twice.
        self.readers.add(rd)
        backlog = [(r, t, len(t)) for r in roots if (t := self.tape_of(r))]
        try:
            for root, tape, n in backlog:
                i = bisect_left(tape, since_ms, 0, n, key=lambda t: t.ts_ms)
                while i < n:
                    if rd.dropped:
                        return
                    j = min(i + LABRUN_CHUNK, n)
                    yield await asyncio.to_thread(_backlog_rows, root, tape, i, j)
                    i = j
            live, ticked = False, -math.inf
            while not rd.dropped:
                if ticked > -math.inf and self.stopping():
                    return
                if not rd.q.empty():                 # prints first, always
                    yield _live_rows(*rd.q.get_nowait())
                    continue
                # the queue is empty in THIS turn of the loop: nothing that arrived before now is still unsent
                if not live:
                    live = True
                    yield _sse({}, "live")
                    continue
                if loop.time() >= ticked + clock_s:
                    ticked = loop.time()
                    yield _sse({"now_ms": self.clock()}, "clock")
                    continue
                try:
                    yield _live_rows(*await asyncio.wait_for(rd.q.get(), ticked + clock_s - loop.time()))
                except asyncio.TimeoutError:
                    continue
        finally:
            self.readers.discard(rd)


class Throttle:
    """fn() soon after kick(), at most once every `gap_s` (fast-paper: the PAPER accounts' push). The first kick
    after a quiet spell runs it on the loop's next turn -- never inside the caller, so the tick path and a POST
    return first; a kick inside the gap schedules ONE trailing run at the gap's end, which every later kick joins.
    No running loop (a direct call from a test): nothing is scheduled -- the pump's own check is the backstop."""

    def __init__(self, fn, gap_s: float):
        self.fn, self.gap_s = fn, gap_s
        self.last = -math.inf           # when fn last ran (time.monotonic, the asyncio loop's own clock)
        self.handle = None              # its scheduled run, while one is pending

    def kick(self) -> None:
        if self.handle is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        wait = self.last + self.gap_s - time.monotonic()
        self.handle = loop.call_later(wait, self._run) if wait > 0 else loop.call_soon(self._run)

    def _run(self) -> None:
        self.handle = None
        self.last = time.monotonic()
        self.fn()


def create_app(*, roots=DEFAULT_ROOTS, base: Path = ARCHIVE, replay: dt.date | None = None,
               speed: float = 10.0, start_et: dt.time = dt.time(9, 25), feed_factory=None,
               now_ms=None, state: Path | None = None, calendar_fetch=None,
               desk_factory=None, fake_desk_factory=None, news_fetch=None, depth_roots=None,
               depth_base: Path | None = None, paper_day: bool = False,
               paper_backtest=None, depth_executor=None, md_connect=None, refresh_kw: dict | None = None,
               depth_relay_in: bool | None = None) -> FastAPI:
    if paper_day and not replay:
        raise ValueError("paper_day forces a REPLAYED date to be an event day: it needs replay")
    roots = app_roots = [r.upper() for r in roots]
    sd = Path(state) if state else state_dir() / "charts"
    sd.mkdir(parents=True, exist_ok=True)
    layouts_path = sd / "layouts.json"
    layout_order_path = sd / "layout_order.json"   # 2026-09-27 layout-tabs: the tab strip's left-to-right order
    # 2026-09-28 three-tabs plan: the Backtest tab's own chart layouts, a separate namespace from the
    # Charts tab's above -- drawings/settings/templates/presets stay shared (unchanged, below).
    bt_layouts_path = sd / "layouts_backtest.json"
    bt_layout_order_path = sd / "layout_order_backtest.json"
    drawings_path = sd / "drawings.json"
    templates_path = sd / "templates.json"
    presets_store = PresetsStore(sd / "presets.json")   # 2026-09-27 draw-tools plan: generic, drawing + (later) indicator
    # Task 4, 2026-09-27 app-settings plan: the market-data login choice (more app-wide settings
    # land in the same file later). MD_ENV is the default until the user picks one.
    settings_store = SettingsStore(sd / "settings.json")
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
    # what the tick job knows (charts/known.py): its coverage report's holes for the chart, its data watchdog's
    # reading for the strip -- two files it writes beside its log (homebase/.state; a test's own state folder)
    kd = Path(state) if state else state_dir()
    known = Known(kd / "tick_coverage.json", kd / "data_watch.json")
    history = History(store, cache_dir=sd / "cache", known=known)
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
    quotes = Quotes()                     # bid/ask per root for the Buy/Sell buttons (desk.py) -- and, while fresh,
                                          # a PAPER market order's price when the live book can't take it (quote_of)

    def push_paper() -> None:
        """The PAPER accounts to every page, when they changed. Run by paper_push only: at once on a change, at most
        one push per PAPER_PUSH_GAP_S; the pump's dirty check is the backstop. (fan and book: defined below.)"""
        try:
            if book is not None and book.dirty:
                fan(book.message())
        except Exception as e:  # noqa: BLE001 — a push must never take the service down
            log(f"paper push: {type(e).__name__}: {e}")

    paper_push = Throttle(push_paper, PAPER_PUSH_GAP_S)

    def depth_book(root: str):
        """The live Level 2 book of `root` for a PAPER market fill (depth.py), or None. (depth: defined below.)"""
        return None if depth is None else depth.book_of(root)

    # the PAPER account (paperbook.py, Task 2): the page trades it like a desk account; the backtester's fill law
    # on the live prints below, persisted to paper/book.jsonl. Live only -- a replay has none (its routes answer
    # 503), so a replayed price never fills it and never touches the saved book. It never reaches the desk.
    # Task 2b: several paper accounts, each its own book (the first, "paper", keeps paper/book.jsonl untouched)
    # fast-paper: a Market fills at once against the live book (book_of), else the quote (quote_of), for all of its
    # size or not at all; every change is pushed at once (on_change)
    book = None if replay else PaperBooks(sd / "paper", roots=roots, clock_ms=lambda: clock(), log=log,
                                          quote_of=quotes.quote_of, book_of=depth_book, on_change=paper_push.kick)
    recorder = None if replay else LiveRecorder(base)

    # the server's breakeven / trailing-stop runner (exitrunner.py, the owner 2026-10-18): live only, like the book
    def runner_views() -> dict:
        out = {a["id"]: a for a in ((link.state or {}).get("accounts") or []) if isinstance(a, dict)} if link is not None else {}
        out.update({v["id"]: v for v in (book.views() if book is not None else [])})
        return out

    def runner_last(root: str):
        q = quotes.snapshot().get(root) or {}
        fresh = q.get("last") is not None and q.get("ts_ms") is not None and clock() - q["ts_ms"] <= 10_000
        return q["last"] if fresh else None

    async def runner_send(action: str, body: dict) -> dict:
        ids = body.get("accounts") or [body.get("account")]
        if all(is_paper_id(x) for x in ids):
            if book is None:
                return {"detail": "no paper book"}
            try:
                return book.act(action, body)
            except Exception as e:  # noqa: BLE001 — the runner records it on the arm
                return {"detail": str(e)}
        if link is None:
            return {"detail": "no desk link"}
        _status, data = await link.post(action, {**body, "quotes": quotes.snapshot()})
        return data

    runner = None if replay else ExitRunner(sd / "exit_arms.json", views=runner_views, last_of=runner_last,
                                            send=runner_send, clock=lambda: clock() / 1000.0, log=log)
    conns: set[Conn] = set()
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

    repair_seen: dict[str, tuple | None] = {}   # root -> the archive files' stamp today's tape was built from
    today_seeded: dict[str, int] = {}           # root -> when (clock ms) today's tape was last built from the files

    def reseed(root: str) -> None:
        """Rebuild today's tape for root from disk (after a refill). Runs on
        the loop and blocks it for a second or two — rare, and this process
        places no orders."""
        if recorder is not None:
            recorder.flush()
        d = session_date(clock(), root)
        repair_seen[root] = store.archive_stamp(root, d)    # BEFORE the read: a repair landing mid-load re-triggers
        sess = store.load(root, d)
        _apply_today(root, d, sess)

    async def reseed_async(root: str) -> list:
        """reseed() with the big read in a worker thread: the loop keeps serving the md heartbeat, the exit runner and the
        order relay meanwhile (a 2.4M-tick day blocks it seconds). What the hub tape took while the files were read
        is spliced back on, as _repair_check does. Returns the hub's tape ticks of the rebuilt session."""
        if recorder is not None:
            recorder.flush()
        d = session_date(clock(), root)
        t0 = clock()
        stamp = await asyncio.to_thread(store.archive_stamp, root, d)
        sess = await asyncio.to_thread(store.load, root, d)
        if hub.today_date.get(root) not in (d, None) and session_date(clock(), root) != d:
            return hub.today.get(root, [])      # the 18:00 roll landed during the reads: d is the old session, the hub has moved on
        cur = hub.today.get(root, ()) if hub.today_date.get(root) == d else ()
        ticks = splice_tail(sess.ticks if sess else [], cur, t0 - REPAIR_SPLICE_MS)
        repair_seen[root] = stamp
        _apply_today(root, d, sess, ticks)
        return hub.today.get(root, [])

    def _apply_today(root: str, d: dt.date, sess, ticks=None) -> None:
        """Hand a loaded session (store.load's; `ticks` overrides its tape) to the hub and the paper runner."""
        if ticks is None:
            ticks = sess.ticks if sess else []
        today_seeded[root] = clock()
        holes = known.holes(root, d)        # a session before it that was never recorded (History.info)
        hub.start_today(root, d, ticks, {
            "date": d.isoformat(), "contract": sess.contract if sess else session_contract(root, clock() / 1000),
            "source": "live", "approx": bool(sess and ticks and not sess.bid_ask),
            "gaps": [[et_wall_s(a), et_wall_s(b)] for a, b in (sess.gaps if sess else [])],
            **({"holes": holes} if holes else {})})
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

    async def _repair_check(root: str) -> None:
        """The hourly repair job fills a session's missing stretch (a Mac that was off) into the
        ARCHIVE file; the chart reads the live file plus that archive (store.load's union), but today's
        tape was built at startup. When the archive files' stamp moved, load the union in a worker
        thread (the big read never touches the loop), splice onto it whatever the hub tape holds that
        the files do not yet (the last second's unflushed ticks), and reseed the hub with the result --
        what a gap refill already does. Only on a change: a stat per poll, a read per repair.
        The session is the one the charts HOLD, not the clock's: after 18:00 with no tick yet (a weekend, a feed
        that is down) the clock names the next session while the charts still show the one that closed, and a
        fill landing in its files then reached them only at the roll (2026-10-16's hole, all weekend)."""
        d = hub.today_date.get(root) or session_date(clock(), root)
        stamp = await asyncio.to_thread(store.archive_stamp, root, d)
        if stamp is None or stamp == repair_seen.get(root):
            return
        if tick_job_running():
            return      # it rewrites the file page by page: one reload when it is done, not one a page
        t0 = clock()
        sess = await asyncio.to_thread(store.load, root, d)
        if sess is None or hub.today_date.get(root) != d:
            return                                  # the session rolled meanwhile: the next poll decides
        ticks = splice_tail(sess.ticks, hub.today.get(root, ()), t0 - REPAIR_SPLICE_MS)
        repair_seen[root] = stamp
        log(f"{root}: repaired archive picked up -- tape {len(hub.today.get(root, ()))} -> {len(ticks)} ticks")
        _apply_today(root, d, sess, ticks)

    past_due: set[str] = set()                  # roots with a repaired past session their open charts still show as it was
    past_reset_at: dict[str, float] = {}        # root -> when (time.monotonic) its charts last reloaded for one
    refresh_kick: dict = {}                     # {"loop", "ev"} while repair_loop runs: a finished Refresh data run wakes it

    def after_refresh(_status: dict) -> None:
        """The Refresh data button's run ended (on its own thread): the repair loop's next turn starts now and reloads
        EVERY open chart from the files -- the memo dropped, no PAST_REDRAW_S wait -- so what the run filled shows
        at once, whatever session it landed in."""
        loop, ev = refresh_kick.get("loop"), refresh_kick.get("ev")
        if loop is not None and ev is not None:
            loop.call_soon_threadsafe(ev.set)

    async def _past_check() -> None:
        """The same for a PAST session: the tick job goes on filling a session's files for a day or two after
        its close, and history.bars -- and every chart already showing the session -- kept the old bars until
        the 18:00 roll. History.changed() (a directory listing per root, in a worker thread) names the watched
        sessions whose files moved and drops their memoized bars; every chart of such a root reloads (a chart
        may hold the session through scroll-back) -- at most once per PAST_REDRAW_S a root, a later piece
        waiting its turn, and never across the 9:30 fire. So do the charts of a root whose known holes are no
        longer what the tick job's coverage report says (Known.refresh, the same worker thread)."""
        for root, _ in await asyncio.to_thread(history.changed):
            past_due.add(root)
        past_due.update(r for r in await asyncio.to_thread(known.refresh) if r in roots)
        for root in sorted(past_due):
            if time.monotonic() - past_reset_at.get(root, -math.inf) < PAST_REDRAW_S:
                continue
            past_due.discard(root)
            past_reset_at[root] = time.monotonic()
            held = [s for s in hub.streams.values() if s.root == root]
            for s in held:
                s.reset = True
            if held:
                log(f"{root}: a past session's files changed -- {len(held)} chart stream(s) reload")

    async def repair_loop() -> None:
        kick = refresh_kick["ev"] = asyncio.Event()
        refresh_kick["loop"] = asyncio.get_running_loop()
        while True:
            with suppress(asyncio.TimeoutError):    # not the `sleep` seam: tests patch it to 0
                await asyncio.wait_for(kick.wait(), REPAIR_POLL_S)
            if kick.is_set():                       # Refresh data finished: every chart, now
                kick.clear()
                history.clear()
                past_reset_at.clear()
                past_due.update(roots)
                log("Refresh data finished -- every open chart reloads from the files")
            for root in roots:
                try:
                    await _repair_check(root)
                except Exception as e:  # noqa: BLE001 — the repair pickup must never take the service down
                    log(f"{root}: repair pickup: {type(e).__name__}: {e}")
            try:
                await _past_check()
            except Exception as e:  # noqa: BLE001 — nor this one
                log(f"past sessions: repair pickup: {type(e).__name__}: {e}")

    async def _paced_sleep(s: float) -> None:
        """Passed to refill() as its own inter-page/penalty pacing hook."""
        await sleep(s)

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
                async with refill_lock:
                    del refill_pending[root]            # now RUNNING: a new request becomes a follow-up
                    frm, contract = entry["frm"], entry["contract"]
                    to = clock()
                    if to - frm < 2000:
                        continue
                    rows: list[dict] = []
                    reached = to
                    fd = feed_other if feed_other is not None and root in feed_other.roots else feed
                    # NQ/ES (what the Lab strategies trade) keep a reserve the others cannot spend
                    pages = min(REFILL_MAX_PAGES, REFILL_BUDGET + (REFILL_RESERVE if root in REFILL_FIRST else 0)
                                - fd.budget_used())
                    if pages > 0:
                        try:
                            rows, reached = await refill(fd.ws, contract, frm, to, max_pages=pages,
                                                           sleep=_paced_sleep, on_request=fd.count_request)
                        except Exception as e:  # noqa: BLE001 — the missing stretch becomes a marked gap
                            log(f"{root}: refill failed: {e}")
                    else:
                        log(f"{root}: refill skipped — md budget {fd.budget_used()}/h")
                    added = recorder.append(root, contract, rows)
                    if reached > frm:
                        for gd, a, b in split_by_session(root, frm, reached):
                            recorder.mark_gap(root, gd, contract, a, b)
                    log(f"{root}: refilled {len(rows)} ticks"
                        + (f", gap {(reached - frm) / 1000:.0f}s marked" if reached > frm else ""))
                    if added or reached > frm:
                        tape = await reseed_async(root)   # else nothing changed: no reload for every open chart
                        if added and tape:
                            # the runner never saw these (its stream carried only the live prints): ship them as a refill
                            ids = {int(r["id"]) for r in added if r.get("id") not in (None, "")}
                            keys = {(int(r["ts_ms"]), float(r["price"]), int(r["size"])) for r in added}
                            lo = bisect_left(tape, min(int(r["ts_ms"]) for r in added), key=lambda t: t.ts_ms)
                            tick_fan.publish_refill(root, [t for t in tape[lo:] if t.id in ids or (t.ts_ms, t.price, t.size) in keys])
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

    # the Lab strategy runner's read-only tick stream (GET /api/labrun/ticks); hub and clock: defined below
    tick_fan = TickFan(lambda: clock(), lambda root: hub.today.get(root))

    fan_new: dict[str, list] = {}               # root -> the hub's classified prints of the delivery in hand (fan_tap)

    def fan_tap(root: str, tk) -> None:         # a hub tap: called for each print the hub keeps, after its side is known
        fan_new.setdefault(root, []).append(tk)

    def labrun_ticks(root: str, rows: list[dict]) -> None:
        try:
            tick_fan.publish(root, fan_new.pop(root, []))     # the prints hub.on_ticks just took, with their sides
        except Exception as e:  # noqa: BLE001 — the runner's stream must never break the live tick path
            log(f"labrun ticks: {type(e).__name__}: {e}")

    # the feed is built AFTER reseed/_refill exist (it takes _refill as its
    # callback); every function above only touches feed/hub/clock when called
    feed_other = None           # the second md login's socket (settings "md_other_roots"), live only
    if replay:
        def on_replay(root: str, contract: str, rows: list[dict]) -> None:
            if link is not None:
                quotes.note(root, rows)
            hub.on_ticks(root, rows)
            paper_ticks(root, rows)
            labrun_ticks(root, rows)

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
            labrun_ticks(root, kept)
            if kept:
                try:
                    book.on_ticks(root, kept)
                except Exception as e:  # noqa: BLE001 — the paper book must never break the live tick path
                    log(f"paper book ({root}): {type(e).__name__}: {e}")
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

        if feed_factory is None:
            # the default TickFeed only: a caller's own feed_factory (tests, mostly) keeps its
            # existing signature -- it never reads app settings and was never asked to
            feed_kwargs = {"md_env": settings_store.get()["md"]}
            if md_connect is not None:   # tests: a fake connect_env, never a real login
                feed_kwargs["connect_env"] = md_connect
            elif settings_store.md_account():
                # a login nobody opens by hand (settings "md_account"): the feed and its recycle
                # take that account's md token while it is valid, else the freshest, as before
                pin = settings_store.md_account()

                async def _pinned_connect(env, _pin=pin):
                    return await T.connect_md(prefer_live=(env == "live"), account=_pin)
                feed_kwargs["connect_env"] = _pinned_connect
                feed_kwargs["fresh_token"] = lambda prefer_live, _pin=pin: T.md_token(prefer_live, account=_pin)
            if recorder is not None:     # the early rebuild's swap: a gap marker, no refill
                feed_kwargs["on_gap"] = recorder.mark_gap_span
            # two logins at once: the markets named in settings ("md_other_roots") ride a second
            # socket on the OTHER login (the live login has CME only; the eval logins carry CBOT and
            # COMEX too, without Level 2). Read at start-up; none named = one socket, as before.
            # Level 2 (Depth) stays on the main socket for every root. Only the main socket's
            # requests are published below: right while the main login is the live one.
            other = [r for r in settings_store.other_roots() if r in roots]
            if other and len(other) < len(roots):
                other_env = next(e for e in MD_ENVS if e != feed_kwargs["md_env"])
                feed_other = TickFeed(other, on_live, on_subscribed=_refill,
                                      **{**feed_kwargs, "md_env": other_env})
            # the tick archive job shares the live login's 180/h: it reads this and subtracts it
            feed_kwargs["usage_path"] = sd / "md_usage.json"
            feed = TickFeed([r for r in roots if feed_other is None or r not in other],
                            on_live, on_subscribed=_refill, **feed_kwargs)
        else:
            feed = feed_factory(roots, on_live, on_subscribed=_refill)
    # Level 2 rides the live feed's own md socket; replay builds none of it (no
    # subscriptions, no depth messages). Recorded: the depth roots this service charts.
    # HOMEBASE_DEPTH_RELAY_IN=1 (the server): the book comes from the Mac's charts, pushed to /ws/depth-in (depthrelay.py)
    depth, relay = None, None
    if depth_relay_in is None:
        depth_relay_in = os.environ.get("HOMEBASE_DEPTH_RELAY_IN") == "1"
    if not replay:
        rec_roots = [r for r in (DEPTH_RECORD_ROOTS if depth_roots is None else depth_roots)
                     if r.upper() in roots]
        relay = RelayFeed() if depth_relay_in else None
        depth = Depth(relay or feed, rec_roots, log=log, wall_ms=lambda: int(clock()),    # the service's clock, like the tick hub
                      recorder=DepthRecorder(depth_base or DEPTH_ARCHIVE) if rec_roots else None)
    hub = Hub(history, clock)
    hub.log = log
    # Time & Sales (tapelive.py): the hub's own today list to the pages that opened the panel ({"op": "tape"}), read
    # by the pump after hub.drain(); nothing on the tick path
    tapelive = TapeLive(lambda r: hub.today.get(r), lambda r: hub.today_date.get(r))
    # the book indicators' live side (booklive.py): the same book lines the recorder writes and the hub's classified
    # prints, through one BookTracker per root; live service only (a replay has no book)
    booklive = BookLive(log=log)
    if depth is not None:
        depth.tap = booklive.on_book
        hub.taps.append(booklive.on_tick)
    hub.taps.append(fan_tap)                    # the runner's stream: the hub's classified prints (labrun_ticks)
    # per-chart Bar Replay: its own hubs over its own History memo; never the live hub, recorder, desk or quotes
    replays = BarReplay(store, sd / "cache", roots, lambda: clock(), min_bar=MIN_BAR,
                        max_studies=MAX_STUDIES, log=log, known=known)
    chart_error: list[str | None] = [None]     # the pump's chart work, failing right now

    def status() -> dict:
        st = dict(feed.status())
        if feed_other is not None:      # the second login's markets: in the one list, its state beside it
            o = feed_other.status()
            st["roots"] = {**st["roots"], **o["roots"]}
            st["md_other"] = {"md": o["md"], "roots": list(feed_other.roots), "connected": o["connected"],
                              "error": o["error"], "md_mismatch": o["md_mismatch"]}
            why = o["error"] or o["md_mismatch"]
            if why and not st.get("error"):
                st["error"] = f"{' '.join(feed_other.roots)} ({o['md']} login): {why}"
        if chart_error[0] and not st.get("error"):
            st["error"] = f"charts: {chart_error[0]}"   # the charts are frozen: say so
        st["recorder"] = None if recorder is None else {
            "written": recorder.written, "buffered": recorder.buffered, "error": recorder.error}
        st["depth"] = {} if depth is None else depth.status()
        st["depth_recorder"] = None if depth is None or depth.recorder is None else depth.recorder.status()
        if depth is not None and depth.error and not st.get("error"):
            st["error"] = f"depth: {depth.error}"
        for r, x in (st.get("roots") or {}).items():     # how far behind the wall the root's newest print came in
            if isinstance(x, dict):
                x["late_s"] = round(hub.lag_ms[r] / 1000, 1) if r in hub.lag_ms else None
        st["data"] = None if replay else known.data(clock())    # the tick job's data watchdog, as last read
        if st["data"] is not None:      # ... and today's hours it found short of their ids, per root (Known.today)
            st["data"]["today"] = {r: h for r in roots
                                   if (h := known.today(r, hub.today_date.get(r), today_seeded.get(r), clock()))}
        st["streams"] = len(hub.streams)
        st["clients"] = len(conns)
        st["calendar"] = cal.status()
        st["news"] = news.status()
        st["bursts"] = burst_book.status()
        st["paper"] = None if book is None else book.status()
        if book is not None and book.broken and not st.get("error"):
            st["error"] = f"paper: {book.broken}"   # loud: the page's status strip shows it
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
                tapelive.flush()                # the tape rows the bars above were built from
                for m in quotes.drain():
                    fan(m)
                desk_fan.flush()                # only a page that had no room: a desk event goes out as it arrives
                booklive.flush(clock() - CLOSE_GRACE_MS)   # the seconds a quiet book never closed itself; a line
                                                           # stamped in S can arrive after S+1 s (like a bar's close)
                if book is not None and book.dirty:
                    paper_push.kick()           # the backstop: a PAPER change nothing announced still reaches every page
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
        known.refresh()                 # two small files, before anything is served; then on the repair poll
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
                holes = known.holes(r, replay)
                hub.start_today(r, replay, [from_row(x, clf) for x in rs], {
                    "date": replay.isoformat(), "contract": feed.contracts.get(r),
                    "source": "replay", "approx": False, "gaps": [], **({"holes": holes} if holes else {})})
        else:
            for r in roots:
                d = session_date(clock(), r)
                contract = session_contract(r, clock() / 1000)
                last = recorder.last_ts(r, d, contract)
                if last is None and always_open(r):
                    # just past a 24/7 root's 18:00 roll: resume from the old session's tail
                    last = recorder.last_ts(r, d - dt.timedelta(days=1), contract)
                start_last[r] = last
                reseed(r)
        tasks = [asyncio.create_task(pump()), asyncio.create_task(feed.run())]
        if feed_other is not None:
            tasks.append(asyncio.create_task(feed_other.run()))
        if not replay:
            tasks.append(asyncio.create_task(repair_loop()))
        if calendar_fetch is not None:
            tasks.append(asyncio.create_task(calendar_loop()))
        if news_fetch is not None:
            tasks.append(asyncio.create_task(news_loop()))
        if link is not None:
            tasks.append(asyncio.create_task(link.run()))
        if runner is not None:
            tasks.append(asyncio.create_task(runner.run()))
        if depth is not None:
            tasks.append(asyncio.create_task(depth.run()))
        if paper.enabled:
            tasks.append(asyncio.create_task(paper_loop()))
        # HOMEBASE_CHARTS_NO_BACKTEST=1 (the 2 GB VPS): no backtest work here -- the Mac does it (the owner, 2026-10-20)
        no_backtest = os.environ.get("HOMEBASE_CHARTS_NO_BACKTEST") == "1"
        if paper_backtest is not None and not no_backtest:
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
        # the Desk's first results ask is ~16 prop sims cold (25-90 s); done here, once, in a daemon thread (never blocks
        # a stop), it is a cache hit. Saved runs only: nothing is started.
        def warm_desklab() -> None:
            while True:             # a new run is scored here within WARM_EVERY_S, not on the Desk's next ask
                tester.warm()
                time.sleep(WARM_EVERY_S)

        if not no_backtest:     # off: the Desk's results cards compute on ask instead
            threading.Thread(target=warm_desklab, name="desklab-warm", daemon=True).start()
        lagwatch.start(asyncio.get_running_loop(), log)     # a stall of the loop names its busy threads in the log
        try:
            yield
        finally:
            feed.stop()
            if feed_other is not None:
                feed_other.stop()
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
            depth_pool.shutdown()       # the depth history worker (depthgrid.HistoryPool), if it ever started
            book_pool.shutdown()        # ... and the book history worker (bookhist.BookPool)
            tester.manager.shutdown()   # never leave a runner child orphaned
            tester.grids.shutdown()     # ... nor a heat-map cell's
            tester.wfs.shutdown()       # ... nor a walk-forward cell's
            export_rt.manager.shutdown()  # nor a data-export child
            refresh_rt.manager.cancel()   # nor a data refresh's (its writes are atomic: stopping it loses nothing)
            for job in paper_job:       # nor the paper comparison's (terminated and reaped)
                job.stop()

    app = FastAPI(title="Homebase Charts", lifespan=lifespan)
    app.add_middleware(HostGuard)   # M4: the Host allowlist on every /api/* route and /ws
    app.mount("/static", RevalidatedFiles(directory=STATIC), name="static")

    routes.pages.register(app, STATIC=STATIC, status=status, burst_book=burst_book, app_roots=app_roots,
                          tick_fan=tick_fan)


    def known_root(root: str) -> str:
        r = root.upper()
        if r not in roots:
            raise HTTPException(404, f"{root!r} is not a charted symbol")
        return r

    register_desk(app, link=link, quotes=quotes, browser_write_ok=browser_write_ok)
    register_paperbook(app, books=book, browser_write_ok=browser_write_ok)
    register_exitrunner(app, runner=runner, browser_write_ok=browser_write_ok)
    def fan_count(msg: dict) -> int:
        """The tester router's only notify callback: progress/grid updates and POST /api/tester/show.
        2026-09-28 three-tabs plan: the Strategy Tester lives on the Backtest tab only now, so this
        targets Backtest-tab connections only (conn.page == "backtest", set from /ws?page=backtest) --
        show_on_chart's "no chart page is open" refusal is accurate again once Backtest, not Charts,
        is what must be open."""
        bt = [c for c in conns if c.page == "backtest"]
        for c in bt:
            c.send(msg)
        return len(bt)

    tester = tester_router(browser_write_ok, base, Path(state) / "tester" if state else None, notify=fan_count,
                           live_roots=roots)      # Promote to Desk asks for live prices: the markets THIS service streams
    app.include_router(tester)

    export_rt = export_router(browser_write_ok, base, depth_base or DEPTH_ARCHIVE,
                              Path(state) / "export" if state else None)
    app.include_router(export_rt)

    refresh_rt = refresh_router(browser_write_ok, Path(state) if state else None, **{
        "md_ready": lambda: bool(T.accounts_by_env()["live"]),     # the live login's md token: the fill pages on no other
        "on_finish": after_refresh, **(refresh_kw or {})})
    app.include_router(refresh_rt)
    app.include_router(pine_routes())      # the Pine runtime and the owner's scripts (~/.homebase/pine)

    routes.settings.register(app, settings_store=settings_store, feed=feed, clock=clock, roots=roots, link=link, log=log,
                             md_switch_timeout_s=lambda: MD_SWITCH_TIMEOUT_S)
    routes.layouts.register(app, route_prefix="/api", layouts_path=layouts_path, layout_order_path=layout_order_path)
    routes.layouts.register(app, route_prefix="/api/bt", layouts_path=bt_layouts_path,
                            layout_order_path=bt_layout_order_path)

    routes.drawings.register(app, drawings_path=drawings_path, templates_path=templates_path, presets_store=presets_store,
                             known_root=known_root)
    routes.events.register(app, paper=paper, cal=cal, news=news)

    # the liquidity heatmap's and the book indicators' histories (routes/depthbook.py): their workers live here, the
    # lifespan shuts them down
    depth_pool = HistoryPool(depth_base or DEPTH_ARCHIVE,
                             **({"executor_factory": depth_executor} if depth_executor else {}))
    book_pool = BookPool(depth_base or DEPTH_ARCHIVE, base, depth_executor)
    routes.depthbook.register(app, known_root=known_root, clock=clock, replay=replay, depth_pool=depth_pool,
                              book_pool=book_pool)
    routes.ws.register(app, relay=relay, conns=conns, status=status, paper=paper, desk_fan=desk_fan, book=book,
                       replays=replays, hub=hub, depth=depth, booklive=booklive, tapelive=tapelive, roots=roots,
                       MIN_BAR=MIN_BAR, MAX_STUDIES=MAX_STUDIES, log=log)

    return app
