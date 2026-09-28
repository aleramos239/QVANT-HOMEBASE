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
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketClose

from .. import netguard, symbols
from .. import ticks as T
from ..contracts import tick_size as contract_tick_size
from ..paths import state_dir
from . import DEFAULT_ROOTS, DEPTH_RECORD_ROOTS, QUIET      # QUIET: never refill across the 9:30 fire
from .bars import BarSpec
from .barreplay import BarReplay
from .bursts import REACTION_ROOTS, BurstBook, ReactionBook, configured_roots
from .calendar import Calendar
from .depth import DEPTH_ARCHIVE, Depth, DepthRecorder
from .depthgrid import (MAX_COLS as DEPTH_MAX_COLS, MAX_SPAN_MS as DEPTH_MAX_SPAN_MS, Busy, HistoryPool, Paused,
                        paused_reason)
from .desk import Fanout, Quotes, register as register_desk
from .history import History
from .hub import Hub, Stream
from .news import News
from .paper import ROOT as PAPER_ROOT, STRATEGY_ID as PAPER_ID, BacktestJob, PaperRunner, describe as paper_describe
from .paperbook import DESK_ORIGINS, PaperBooks, _cors, desk_origin_refusal, register as register_paperbook
from .presets import MAX_PRESET_BYTES, PresetsStore
from .recorder import REFILL_MAX_PAGES, LiveRecorder, refill
from .replay import ReplayFeed
from .session import ET, always_open, et_wall_s, session_date, session_range_ms, split_by_session
from .settings_store import MD_CHOICES, SettingsStore
from .store import ARCHIVE, TickStore
from .studies import make
from .tick import SideClassifier, from_row
from .tester_api import tester_router
from .tickfeed import SwitchInProgress, TickFeed

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
# 2026-09-27 draw-tools plan: a drawing's colour (and style.fillColor / style.textColor) may also
# carry opacity, the same shape the chart-settings colours already use (settings.js' fmtColor).
_RGBA_COLOR = re.compile(r"rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(0|1|0?\.\d+)\s*\)")
DRAWING_LINE_STYLES = ("solid", "dashed", "dotted")
DRAWING_LABEL_POS = {"trend": ("above", "below", "middle"), "hline": ("above", "below", "middle"),
                     "rect": ("top", "middle", "bottom")}
# exactly the style fields each drawing type takes (drawstyle.js' FIELDS mirrors this)
DRAWING_STYLE_FIELDS = {
    "trend": {"width", "lineStyle", "extendLeft", "extendRight", "text", "fontSize", "textColor", "bold", "labelPos"},
    "hline": {"width", "lineStyle", "axisLabel", "text", "fontSize", "textColor", "bold", "labelPos"},
    "rect": {"width", "lineStyle", "fillColor", "text", "fontSize", "textColor", "bold", "labelPos"},
    "long": set(), "short": set(),
}
MAX_DRAWING_LABEL_TEXT = 200
# Task 4 app-settings plan, Fix round 1 (review of bdaccbd):
BOT_BUSY_STATUSES = ("placing", "placed", "live", "error")   # C3: trading.BOT_BUSY + "error"
MD_SWITCH_MARGIN_START = dt.time(9, 15)   # I4: a margin before QUIET[0] itself -- a switch's own
                                          # duration is unbounded (connect + up to 11 getChart
                                          # timeouts + p-ticket retries), so QUIET[0] is too late
MD_SWITCH_COOLDOWN_S = 600         # I3: at most one switch ATTEMPT every 10 min
MD_SWITCH_BUDGET_HEADROOM = 120    # I3/N4: refuse a switch once the TARGET login is this close to 180/h
MD_SWITCH_TIMEOUT_S = 600          # N3: the PUT never waits longer than this for the feed


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


def _valid_color(s) -> bool:
    """#RRGGBB, or rgba(r,g,b,a) with r/g/b <= 255 and a in [0,1] (2026-09-27 draw-tools plan:
    widened from hex-only so a drawing's colour can carry opacity, the same shape the chart
    settings' own colours already use -- settings.js' fmtColor)."""
    if not isinstance(s, str):
        return False
    if _HEX_COLOR.fullmatch(s):
        return True
    m = _RGBA_COLOR.fullmatch(s)
    if not m:
        return False
    r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return r <= 255 and g <= 255 and b <= 255


def check_style(kind: str, style) -> dict:
    """A drawing's optional visual style, stripped to exactly the fields that type takes (junk, a
    field the type does not carry, or one with a wrong type/range/length fails the whole PUT --
    fail closed, never silently dropped): width 1-4 and lineStyle solid/dashed/dotted (trend,
    hline, rect); extendLeft/extendRight (trend only); fillColor (rect only); axisLabel (hline
    only); text (<= 200 characters), fontSize 10-28, textColor, bold and labelPos (trend/hline:
    above/below/middle; rect: top/middle/bottom) on trend, hline and rect. long/short take no style
    object (DRAWING_STYLE_FIELDS[kind] is empty for them: any key at all raises). ValueError (with
    a message for the page) on anything outside this."""
    if not isinstance(style, dict):
        raise ValueError("style: an object")
    allowed = DRAWING_STYLE_FIELDS.get(kind, set())
    for key in style:
        if key not in allowed:
            raise ValueError(f"style.{key} does not apply to a {kind}")
    out = {}
    if "width" in style:
        w = style["width"]
        if not isinstance(w, int) or isinstance(w, bool) or not 1 <= w <= 4:
            raise ValueError("style.width: a whole number from 1 to 4")
        out["width"] = w
    if "lineStyle" in style:
        if style["lineStyle"] not in DRAWING_LINE_STYLES:
            raise ValueError("style.lineStyle: solid, dashed or dotted")
        out["lineStyle"] = style["lineStyle"]
    for key in ("extendLeft", "extendRight", "axisLabel", "bold"):
        if key in style:
            if not isinstance(style[key], bool):
                raise ValueError(f"style.{key}: true or false")
            out[key] = style[key]
    if "fillColor" in style:
        if not _valid_color(style["fillColor"]):
            raise ValueError("style.fillColor: #RRGGBB or rgba(r,g,b,a)")
        out["fillColor"] = style["fillColor"]
    if "text" in style:
        t = style["text"]
        if not isinstance(t, str) or len(t) > MAX_DRAWING_LABEL_TEXT:
            raise ValueError(f"style.text: a string of at most {MAX_DRAWING_LABEL_TEXT} characters")
        out["text"] = t
    if "fontSize" in style:
        fs = style["fontSize"]
        if not isinstance(fs, int) or isinstance(fs, bool) or not 10 <= fs <= 28:
            raise ValueError("style.fontSize: a whole number from 10 to 28")
        out["fontSize"] = fs
    if "textColor" in style:
        if not _valid_color(style["textColor"]):
            raise ValueError("style.textColor: #RRGGBB or rgba(r,g,b,a)")
        out["textColor"] = style["textColor"]
    if "labelPos" in style:
        choices = DRAWING_LABEL_POS.get(kind, ())
        if style["labelPos"] not in choices:
            raise ValueError(f"style.labelPos: {', '.join(choices)}")
        out["labelPos"] = style["labelPos"]
    return out


def check_drawings(body) -> list:
    """The page's drawings for one symbol, validated and stripped to what
    the page draws: [{id, type, points: [{t?, p}], color?, qty?, locked?,
    style?}]. A long / short position is [entry, target, stop] with target
    and stop on the box's right edge (same t), stop < entry < target (long)
    or target < entry < stop (short), and an optional qty 1-10000 (kept for
    positions only). `style` (2026-09-27 draw-tools plan) is per-type --
    see check_style. ValueError (with a message for the page) on anything
    else."""
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
            if not _valid_color(d["color"]):
                raise ValueError("color: #RRGGBB or rgba(r,g,b,a)")
            item["color"] = d["color"]
        if "locked" in d:
            if not isinstance(d["locked"], bool):
                raise ValueError("locked: true or false")
            item["locked"] = d["locked"]
        if "style" in d:
            style = check_style(kind, d["style"])
            if style:
                item["style"] = style
        out.append(item)
    return out


def check_template_name(name) -> str:
    """A chart-settings template's name: 1-40 characters, no / \\ .. and no
    control characters (it rides in the URL path), and not "." on its own
    (the browser resolves /api/templates/. as a path step, landing on the
    list route rather than this name). ValueError otherwise."""
    if not isinstance(name, str) or not 1 <= len(name) <= MAX_TEMPLATE_NAME:
        raise ValueError(f"a template name has 1-{MAX_TEMPLATE_NAME} characters")
    if name == ".":
        raise ValueError('a template name cannot be "."')
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
               paper_backtest=None, depth_executor=None, md_connect=None) -> FastAPI:
    if paper_day and not replay:
        raise ValueError("paper_day forces a REPLAYED date to be an event day: it needs replay")
    roots = [r.upper() for r in roots]
    sd = Path(state) if state else state_dir() / "charts"
    sd.mkdir(parents=True, exist_ok=True)
    layouts_path = sd / "layouts.json"
    layout_order_path = sd / "layout_order.json"   # 2026-09-27 layout-tabs: the tab strip's left-to-right order
    drawings_path = sd / "drawings.json"
    templates_path = sd / "templates.json"
    presets_store = PresetsStore(sd / "presets.json")   # 2026-09-27 draw-tools plan: generic, drawing + (later) indicator
    # Task 4, 2026-09-27 app-settings plan: the market-data login choice (more app-wide settings
    # land in the same file later). MD_ENV is the default until the user picks one.
    settings_store = SettingsStore(sd / "settings.json")
    last_md_switch_attempt = [0.0]   # epoch s of the last PUT /api/settings that actually switched (I3 cooldown)
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
    # the PAPER account (paperbook.py, Task 2): the page trades it like a desk account; the backtester's fill law
    # on the live prints below, persisted to paper/book.jsonl. Live only -- a replay has none (its routes answer
    # 503), so a replayed price never fills it and never touches the saved book. It never reaches the desk.
    # Task 2b: several paper accounts, each its own book (the first, "paper", keeps paper/book.jsonl untouched)
    book = None if replay else PaperBooks(sd / "paper", roots=roots, clock_ms=lambda: clock(), log=log)
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
            feed = TickFeed(roots, on_live, on_subscribed=_refill, **feed_kwargs)
        else:
            feed = feed_factory(roots, on_live, on_subscribed=_refill)
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
                if book is not None and book.dirty:
                    fan(book.message())         # the PAPER account changed: every page, like a desk account event
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
            depth_pool.shutdown()       # the depth history worker (depthgrid.HistoryPool), if it ever started
            tester.manager.shutdown()   # never leave a runner child orphaned
            tester.grids.shutdown()     # ... nor a heat-map cell's
            tester.wfs.shutdown()       # ... nor a walk-forward cell's
            for job in paper_job:       # nor the paper comparison's (terminated and reaped)
                job.stop()

    app = FastAPI(title="Homebase Charts", lifespan=lifespan)
    app.add_middleware(HostGuard)   # M4: the Host allowlist on every /api/* route and /ws
    app.mount("/static", RevalidatedFiles(directory=STATIC), name="static")

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "charts.html", headers={"cache-control": "no-cache"})

    @app.get("/api/status")
    async def api_status(request: Request, response: Response):
        """Desk-settings plan: also answers the desk page's origin (the last switch error and
        any md login mismatch feed the Settings dialog there) -- same exact-origin CORS as
        /api/settings and the paper-account routes; everything else stays same-origin."""
        bad = desk_origin_refusal(request.headers)
        if bad is not None:
            raise HTTPException(*bad)
        _cors(response, request)
        return status()

    @app.get("/api/bursts/now")
    async def api_bursts_now():
        # Task 2, the burst radar strip: every streamed root's current ratio, for the page's
        # first paint before its /ws status (which carries the same thing every STATUS_S) lands.
        # Reads BurstBook's own cached per-root ratio -- no new md request, no event-loop work.
        return burst_book.now()

    @app.get("/api/symbols")
    async def api_symbols():
        return {"roots": roots, "timeframes": TIMEFRAMES}

    def read_json(path: Path) -> dict:
        try:
            v = json.loads(path.read_text())
        except (OSError, ValueError):
            return {}
        return v if isinstance(v, dict) else {}

    def write_json(path: Path, data: dict | list) -> None:
        """Via a temp file + atomic rename: a crash or a full disk mid-write
        must never tear the file (torn, it reads back as {} and the next
        save would wipe everything in it)."""
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, path)

    def read_json_list(path: Path) -> list:
        try:
            v = json.loads(path.read_text())
        except (OSError, ValueError):
            return []
        return v if isinstance(v, list) else []

    def browser_write_ok(request: Request) -> None:
        """Browsers send a cross-site PUT/DELETE after a preflight that this
        app never answers, but a simple no-CORS request could still reach
        us; refuse any write from a page that is not this service's own
        (same rule as the /ws handshake).

        Desk-settings plan: /api/settings' PUT and /api/paper/accounts*'s
        writes now ALSO answer the desk page's exact origin with a CORS
        header, so "no CORS request could still reach us" is no longer true
        for those two routes specifically -- they add their own exact-origin
        check (desk_origin_refusal) and only emit the header for that exact
        match, in front of this same-origin check, rather than loosening it."""
        if not origin_ok(request.headers.get("origin"), request.headers.get("host")):
            raise HTTPException(403, "writes from another site are refused")

    def known_root(root: str) -> str:
        r = root.upper()
        if r not in roots:
            raise HTTPException(404, f"{root!r} is not a charted symbol")
        return r

    def bot_placing() -> bool:
        """True while the desk reports ANY account working a bot -- trading.py's own BOT_BUSY =
        ("placing", "placed", "live"), plus "error" (cheap to include, and an account in a state
        this process cannot make sense of should read as busy, not idle). Review C3: the desk
        pauses its OWN view publishing for the entire "placing" span (trading.py's
        _views_paused), so this process's DeskLink.state never actually holds "placing" -- it
        jumps idle -> placed directly. Blocking on "placed"/"live" too is what makes this a real
        guard rather than a state this process can never observe.

        Fail closed (review C3): a link that is CONFIGURED but whose state is unknown (never
        received one) or reports `down` reads as busy -- an md switch is optional work, and it
        must never fire blind into a desk this process has lost contact with. `link is None`
        (replay, or no desk link at all) is the one case that is genuinely never busy."""
        if link is None:
            return False
        if link.state is None or link.down is not None:
            return True
        strategies = (link.state.get("bot") or {}).get("strategies") or {}
        return any(a.get("status") in BOT_BUSY_STATUSES
                  for s in strategies.values()
                  for a in (s.get("accounts") or {}).values())

    def md_switch_refused() -> str | None:
        """None, or the one sentence the Settings dialog shows: refused from MD_SWITCH_MARGIN
        (a margin before the 09:20 quiet window itself -- review I4: a switch's own connect +
        up to 11 x 15 s getChart timeouts + p-ticket retries has no bounded duration, so the
        window's OWN start is too late a check) through 09:35 ET on a weekday, or while the desk
        reports a bot actually working (any status, any strategy -- not just today's booked
        ones)."""
        t = dt.datetime.fromtimestamp(clock() / 1000, ET)
        if t.weekday() < 5 and MD_SWITCH_MARGIN_START <= t.time() < QUIET[1]:
            return "Not while the 9:30 bot is working — try after 09:35."
        if bot_placing():
            return "Not while the 9:30 bot is working — try after 09:35."
        return None

    register_desk(app, link=link, quotes=quotes, browser_write_ok=browser_write_ok)
    register_paperbook(app, books=book, browser_write_ok=browser_write_ok)
    def fan_count(msg: dict) -> int:      # POST /api/tester/show: tell every page, say how many there were
        fan(msg)
        return len(conns)

    tester = tester_router(browser_write_ok, base, Path(state) / "tester" if state else None, notify=fan_count)
    app.include_router(tester)

    @app.get("/api/settings")
    async def get_settings(request: Request, response: Response):
        """{"md": ..., "accounts": {"live": "···885"|None, "demo": "···021"|None}}. `accounts`
        (review M2) is read from the desk's own config + token files at request time, masked to
        the last 3 characters -- never the settings file, never hard-coded (the Apex login has
        already changed once). None means that login currently has no valid md token, i.e. a
        switch to it would fail (this also surfaces a C2 mismatch before it's ever attempted).

        Desk-settings plan (2026-09-27): answers the desk page's origin too (paperbook's exact-
        origin CORS, extended to this route -- everything else on this service stays same-origin)."""
        bad = desk_origin_refusal(request.headers)
        if bad is not None:
            raise HTTPException(*bad)
        _cors(response, request)
        d = settings_store.get()
        if getattr(feed, "switch_in_progress", False):
            d["md"] = feed.md_env   # the file already names the target; the feed is not there yet
        try:
            accts = T.accounts_by_env()
        except Exception:  # noqa: BLE001 — a broken config must never break the dialog, only omit the note
            accts = {"live": None, "demo": None}
        d["accounts"] = {env: (f"···{label[-3:]}" if label and len(label) > 3 else label)
                         for env, label in accts.items()}
        return d

    @app.options("/api/settings")
    async def settings_preflight(request: Request):
        """The desk page's CORS preflight for PUT /api/settings -- allowed for DESK_ORIGINS only
        (anything else: no allow-origin header, so the browser never sends the write)."""
        o = request.headers.get("origin")
        if o not in DESK_ORIGINS:
            return JSONResponse({"detail": "origin not allowed"}, status_code=403)
        return Response(status_code=204, headers={
            "access-control-allow-origin": o, "vary": "Origin", "access-control-allow-methods": "PUT",
            "access-control-allow-headers": "content-type", "access-control-max-age": "600"})

    @app.put("/api/settings")
    async def put_settings(request: Request):
        """{"md": "live"|"demo"}: switches the chart feed's md login in place (TickFeed.switch_md)
        and persists the choice (written first, put back if the switch fails). JSON-only (like the desk proxy) on top
        of the Host check every /api/* route already gets from HostGuard.

        Refused, in order: a bad body (400); replay, which has no switchable feed (503); a switch
        already in flight (409, TickFeed's own SwitchInProgress); a cooldown since the last
        ATTEMPT, successful or not (429, review I3 -- a switch costs roughly 2 requests per root,
        subscribe plus its gap refill, so unthrottled clicking can spend the whole hourly budget
        in under ten); the TARGET login too close to its own hourly budget to afford one
        switch's worth of requests (429); the 09:20-09:35 ET weekday window or a bot working
        (423). Any OTHER failure -- a bad connect, an environment mismatch, every root refused,
        the window opening mid-switch -- is TickFeed's own RuntimeError (502); nothing else is
        allowed to reach this route as an unhandled 500. A feed that has not answered in
        MD_SWITCH_TIMEOUT_S is 504; the switch still finishes and keeps the file right.

        Desk-settings plan: the exact-origin check (desk_origin_refusal) plus CORS (_cors) wrap
        the whole thing, like paperbook's account-write routes -- a refusal AFTER that check is
        still readable by the desk page, never just "unreachable"."""
        bad = desk_origin_refusal(request.headers)
        if bad is not None:
            raise HTTPException(*bad)
        try:
            result = await do_put_settings(request)
        except HTTPException as e:
            return _cors(JSONResponse({"detail": e.detail}, status_code=e.status_code), request)
        return _cors(JSONResponse(result), request)

    async def do_put_settings(request: Request) -> dict:
        bad = netguard.refusal(request.method, request.scope["headers"], netguard.allowlist())
        if bad is not None:
            raise HTTPException(*bad)
        browser_write_ok(request)
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "the body is not JSON") from None
        if not isinstance(body, dict) or body.get("md") not in MD_CHOICES:
            raise HTTPException(400, f"""a settings update is {{"md": {' or '.join(MD_CHOICES)}}}""")
        md = body["md"]
        if not hasattr(feed, "switch_md"):
            raise HTTPException(503, "the market-data login can't be switched here (replay)")
        if getattr(feed, "switch_in_progress", False):
            # before the no-op path: its write would overwrite the file the switch in flight
            # already wrote, and a landing switch would then disagree with it
            raise HTTPException(409, "a market-data login switch is already in progress")
        if md == getattr(feed, "md_env", None):
            settings_store.set_md(md)   # already on it -- still make the file agree
            return settings_store.get()
        now_s = clock() / 1000
        since_last = now_s - last_md_switch_attempt[0]
        if since_last < MD_SWITCH_COOLDOWN_S:
            wait = int(MD_SWITCH_COOLDOWN_S - since_last)
            raise HTTPException(429, f"switching logins is limited to once every "
                                     f"{MD_SWITCH_COOLDOWN_S // 60:.0f} minutes — try again in {wait}s")
        if feed.budget_used(md) + 2 * len(roots) > MD_SWITCH_BUDGET_HEADROOM:
            # N4: the switch's getCharts and gap refills are spent on the login switched TO
            raise HTTPException(429, f"the {md} login is close to its hourly market-data budget "
                                     "— try again after it resets")
        reason = md_switch_refused()
        if reason:
            raise HTTPException(423, reason)
        last_md_switch_attempt[0] = now_s   # counts the ATTEMPT, whatever it ends up doing
        previous_md = feed.md_env

        async def switch_and_save() -> None:
            """The file is written FIRST (a write failure then switches nothing) and put back
            if the switch fails -- so the file, status() and the dialog never disagree, and no
            second switch is ever needed to undo one (re-review M-d). Runs as its own task: a
            PUT that times out or is dropped does not cut the bookkeeping short."""
            try:
                settings_store.set_md(md)
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(f"could not save the setting ({type(e).__name__}: {e}) — "
                                   "nothing was switched") from None
            try:
                await feed.switch_md(md)
            except BaseException:
                try:
                    settings_store.set_md(previous_md)
                except Exception as e:  # noqa: BLE001
                    log(f"md switch failed AND the setting could not be put back: {e}")
                raise

        job = asyncio.ensure_future(switch_and_save())
        job.add_done_callback(lambda t: t.cancelled() or t.exception())   # never "never retrieved"
        try:
            await asyncio.wait_for(asyncio.shield(job), MD_SWITCH_TIMEOUT_S)
        except asyncio.TimeoutError:
            raise HTTPException(504, "the market-data switch is taking too long — its outcome "
                                     "will show in Settings") from None
        except SwitchInProgress as e:
            raise HTTPException(409, str(e)) from None
        except RuntimeError as e:
            raise HTTPException(502, str(e)) from None
        except Exception as e:  # noqa: BLE001 — belt & suspenders: this route must never 500
            raise HTTPException(502, f"{type(e).__name__}: {e}") from None
        return settings_store.get()

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

    @app.post("/api/layouts/{name:path}/rename")
    async def rename_layout(name: str, request: Request):
        """One atomic dict-key move plus the same temp-file+rename write as every other layouts.json
        write (write_json) -- never a client-side PUT-new-then-DELETE-old, which would leave two copies
        on disk (and no way to tell which is live) if the DELETE leg failed after a successful PUT.
        A crash or a full disk here lands exactly like any other write_json failure: the file on disk is
        untouched (see test_a_failed_rename_leaves_the_saved_layouts_untouched), never half-renamed."""
        browser_write_ok(request)
        body = await request.json()
        new = body.get("to") if isinstance(body, dict) else None
        if not isinstance(new, str) or not new:
            raise HTTPException(400, "a rename is {to: <new name>}")
        # the browser resolves /api/layouts/. and /.. as path steps: the PUT/DELETE route would miss it
        if new in (".", ".."):
            raise HTTPException(400, "“.” and “..” cannot be layout names")
        all_ = read_json(layouts_path)
        if name not in all_:
            raise HTTPException(404, f"{name!r} is not a saved layout")
        if new == name:
            return {"ok": True}
        if new in all_:
            raise HTTPException(409, f"a layout named {new!r} already exists")
        all_[new] = all_.pop(name)
        write_json(layouts_path, all_)
        return {"ok": True}

    @app.get("/api/layout-order")
    async def get_layout_order():
        # a distinct path from /api/layouts/{name:path} on purpose -- sharing the prefix would make
        # "order" just another layout name under that route, whichever one FastAPI matched first
        return read_json_list(layout_order_path)

    @app.put("/api/layout-order")
    async def put_layout_order(request: Request):
        browser_write_ok(request)
        body = await request.json()
        if not isinstance(body, list) or not all(isinstance(x, str) for x in body):
            raise HTTPException(400, "a layout order is a list of names")
        write_json(layout_order_path, body)
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

    # 2026-09-27 draw-tools plan: a generic named-preset store, by "kind" ("drawing:<tool>" today,
    # "indicator:<tool>" once the indicator dialog reuses it). Same write guard, same atomic write,
    # same body-size cap and JSON-object-only rule as templates above.
    @app.get("/api/presets/{kind}")
    async def get_presets(kind: str):
        try:
            return presets_store.list(kind)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @app.put("/api/presets/{kind}/{name:path}")
    async def put_preset(kind: str, name: str, request: Request):
        browser_write_ok(request)
        raw = await request.body()
        if len(raw) > MAX_PRESET_BYTES:
            raise HTTPException(400, f"a preset is at most {MAX_PRESET_BYTES // 1024} KB of JSON")
        try:
            body = json.loads(raw, parse_constant=_no_constant)
        except ValueError:
            raise HTTPException(400, "the body is not JSON") from None
        if not isinstance(body, dict):
            raise HTTPException(400, "a preset is a JSON object")
        try:
            presets_store.put(kind, name, body)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return {"ok": True}

    @app.delete("/api/presets/{kind}/{name:path}")
    async def delete_preset(kind: str, name: str, request: Request):
        browser_write_ok(request)
        try:
            presets_store.delete(kind, name)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
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

    # the liquidity heatmap's history (depthgrid.py): the recorded depth files as a down-sampled grid, built
    # in ONE spawned worker process (never this process, never the default thread pool), one request at a
    # time (busy -> 503, never queued), <= 2 MB, never past now (a replay's own clock in a replay: no
    # look-ahead), and never decoded 09:20-09:35 ET or 08:29:30-08:31 ET on weekdays, by the wall clock
    # (the service's clock when live, so tests can place it)
    def depth_wall_ms() -> float:
        return time.time() * 1000 if replay else clock()

    depth_pool = HistoryPool(depth_base or DEPTH_ARCHIVE,
                             **({"executor_factory": depth_executor} if depth_executor else {}))

    @app.get("/api/depth/history")
    async def api_depth_history(request: Request):
        q = request.query_params
        root = known_root(q.get("root", ""))
        now = clock()
        try:
            frm, to = int(q["from_ms"]), int(q["to_ms"])
            cols = int(q.get("cols", DEPTH_MAX_COLS // 2))
        except (KeyError, ValueError):
            raise HTTPException(400, "from_ms / to_ms: epoch ms; cols: a whole number") from None
        if frm < 0 or to > now + 86_400_000 or to <= frm or to - frm > DEPTH_MAX_SPAN_MS:
            raise HTTPException(400, f"0 <= from_ms < to_ms <= now + 1 day, "
                                     f"at most {DEPTH_MAX_SPAN_MS // 3_600_000} h apart")
        wall = depth_wall_ms()
        why = paused_reason(wall / 1000)
        if why:
            raise HTTPException(503, why)
        try:
            body = await depth_pool.grid(root, frm, to, cols, now, wall - time.time() * 1000)
        except (Busy, Paused) as e:
            raise HTTPException(503, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return Response(body, media_type="application/json")

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
        if book is not None:
            conn.send(book.message(clear=False))   # the PAPER account as it stands (every other page keeps its update)
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
