"""The chart service: FastAPI on :8852 — the page, the websocket, layouts, drawings, templates,
status. Its own process; the trading app on :8850 only links to it.

    python -m homebase.charts                      # live, from the md feed
    python -m homebase.charts --replay 2026-09-24  # replay a session, records nothing
"""
from __future__ import annotations

import asyncio
import datetime as dt
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

from .. import symbols
from ..paths import state_dir
from . import DEFAULT_ROOTS, QUIET      # QUIET: never refill across the 9:30 fire
from .bars import BarSpec
from .calendar import Calendar
from .history import History
from .hub import Hub
from .recorder import REFILL_MAX_PAGES, LiveRecorder, refill
from .replay import ReplayFeed
from .session import ET, always_open, et_wall_s, session_date, session_range_ms, split_by_session
from .store import ARCHIVE, TickStore
from .studies import make
from .tick import SideClassifier, from_row
from .tickfeed import TickFeed

STATIC = Path(__file__).resolve().parent.parent / "static"
PUMP_S = 0.25                 # <= 4 updates a second per chart
STATUS_S = 2.0                # a status to every page this often (the page greys it after 6 s without)
CLOSE_GRACE_MS = 1500         # a time bar closes this long after its end if no tick closed it
ROLL_GRACE_MS = 60_000        # a 24/7 root rolls at 18:00 with no dead hour: its old session's last
                              # prints can reach us after the clock passed 18:00 and are kept this long
REFILL_BUDGET = 60            # this process's own chart requests per hour
SEND_QUEUE_MAX = 400
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
               now_ms=None, state: Path | None = None, calendar_fetch=None) -> FastAPI:
    roots = [r.upper() for r in roots]
    sd = Path(state) if state else state_dir() / "charts"
    sd.mkdir(parents=True, exist_ok=True)
    layouts_path = sd / "layouts.json"
    drawings_path = sd / "drawings.json"
    templates_path = sd / "templates.json"
    # ForexFactory's calendar; calendar_fetch None never fetches (tests); python -m homebase.charts passes http_get
    cal = Calendar(sd / "calendar", fetch=calendar_fetch)
    store = TickStore(base)
    history = History(store, cache_dir=sd / "cache")
    recorder = None if replay else LiveRecorder(base)
    conns: set[Conn] = set()
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

    # the feed is built AFTER reseed/_refill exist (it takes _refill as its
    # callback); every function above only touches feed/hub/clock when called
    if replay:
        feed = ReplayFeed(store, roots, replay, lambda r, c, rows: hub.on_ticks(r, rows),
                          speed=speed, start_et=start_et)
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
            hub.on_ticks(root, recorder.append(root, contract, rows))

        feed = (feed_factory or TickFeed)(roots, on_live, on_subscribed=_refill)
    hub = Hub(history, clock)
    chart_error: list[str | None] = [None]     # the pump's chart work, failing right now

    def status() -> dict:
        st = dict(feed.status())
        if chart_error[0] and not st.get("error"):
            st["error"] = f"charts: {chart_error[0]}"   # the charts are frozen: say so
        st["recorder"] = None if recorder is None else {
            "written": recorder.written, "buffered": recorder.buffered, "error": recorder.error}
        st["streams"] = len(hub.streams)
        st["clients"] = len(conns)
        st["calendar"] = cal.status()
        return st

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
        log(f"up — {'replay ' + replay.isoformat() if replay else 'live'} · {', '.join(roots)}")
        try:
            yield
        finally:
            feed.stop()
            for t in tasks:
                t.cancel()
            if recorder is not None:
                recorder.flush()

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

    @app.get("/api/calendar")
    async def api_calendar(request: Request):
        q = request.query_params
        try:
            frm, to = int(q.get("from", 0)), int(q.get("to", 2 ** 62))
        except ValueError:
            raise HTTPException(400, "from / to: epoch ms") from None
        countries = [c.strip() for c in q.get("countries", "").split(",") if c.strip()]
        return cal.events(frm, to, countries or None)

    @app.websocket("/ws")
    async def ws_endpoint(sock: WebSocket):
        if not origin_ok(sock.headers.get("origin"), sock.headers.get("host")):
            await sock.close(code=1008)     # before accept(): the handshake is refused (403)
            return
        await sock.accept()
        conn = Conn(sock)
        conns.add(conn)
        conn.send({"type": "status", **status()})
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
                    hub.unsubscribe((conn, cid))
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
                try:
                    hub.unsubscribe((conn, cid))
                    s = hub.streams.get((root, spec.key))
                    if s is None:
                        s = hub.attach(await asyncio.to_thread(hub.prepare, root, spec, keys))
                    for k in keys:
                        s.add_study(k)
                    hub.subscribe(s, (conn, cid))
                    conn.send({"type": "history", "id": cid, **s.payload(bool(msg.get("fp", True)))})
                except Exception as e:  # noqa: BLE001 — an unexpected failure building the
                                        # stream must not drop every chart on the page either
                    log(f"sub {cid} ({root} {spec.key}): {type(e).__name__}: {e}\n{traceback.format_exc()}")
                    conn.send({"type": "error", "id": cid, "error": str(e)})
                    # never leave this id subscribed to a stream it only got an
                    # error for (the pump would keep sending it `update`s for
                    # an id that never got `history`), and never leave a
                    # freshly attached, now-subscriberless stream in hub.streams
                    hub.unsubscribe((conn, cid))
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
            hub.drop_conn(conn)
            conn.task.cancel()

    return app
