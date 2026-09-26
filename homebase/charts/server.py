"""The chart service: FastAPI on :8852 — the page, the websocket, layouts,
status. Its own process; the trading app on :8850 only links to it.

    python -m homebase.charts                      # live, from the md feed
    python -m homebase.charts --replay 2026-09-24  # replay a session, records nothing
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
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
from . import DEFAULT_ROOTS
from .bars import BarSpec
from .history import History
from .hub import Hub
from .recorder import REFILL_MAX_PAGES, LiveRecorder, refill
from .replay import ReplayFeed
from .session import ET, et_wall_s, session_date, session_range_ms
from .store import ARCHIVE, TickStore
from .studies import make
from .tick import SideClassifier, from_row
from .tickfeed import TickFeed

STATIC = Path(__file__).resolve().parent.parent / "static"
PUMP_S = 0.25                 # <= 4 updates a second per chart
CLOSE_GRACE_MS = 1500         # a time bar closes this long after its end if no tick closed it
REFILL_BUDGET = 60            # this process's own chart requests per hour
QUIET = (dt.time(9, 20), dt.time(9, 35))    # never refill across the 9:30 fire
SEND_QUEUE_MAX = 400
TIMEFRAMES = [["5s", "time:5"], ["15s", "time:15"], ["30s", "time:30"], ["1m", "time:60"],
              ["2m", "time:120"], ["3m", "time:180"], ["5m", "time:300"], ["10m", "time:600"],
              ["15m", "time:900"], ["30m", "time:1800"], ["1h", "time:3600"], ["4h", "time:14400"],
              ["1D", "time:86400"], ["500T", "tick:500"], ["1000T", "tick:1000"],
              ["2000V", "volume:2000"], ["10R", "range:10"], ["20R", "range:20"]]
MIN_BAR = {"time": 5, "tick": 100, "volume": 100, "range": 2}   # finer bars cost too much to build/ship
MAX_STUDIES = 16              # per subscription
LOCAL_HOSTS = ("localhost", "127.0.0.1")


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
               now_ms=None, state: Path | None = None) -> FastAPI:
    roots = [r.upper() for r in roots]
    sd = Path(state) if state else state_dir() / "charts"
    sd.mkdir(parents=True, exist_ok=True)
    layouts_path = sd / "layouts.json"
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
        d = session_date(clock())
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
        d = session_date(clock())
        s0, _ = session_range_ms(d)
        # never page back past this session's open: a `since` from the previous
        # session (a weekend straggler, a drop before the 17:00 close) would
        # file that session's ticks as its live file
        frm = max(since_ms if since_ms is not None else (start_last.get(root) or s0), s0)
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
                    recorder.append(root, contract, rows)
                    if reached > frm:
                        recorder.mark_gap(root, d, contract, frm, reached)
                    log(f"{root}: refilled {len(rows)} ticks"
                        + (f", gap {(reached - frm) / 1000:.0f}s marked" if reached > frm else ""))
                    reseed(root)
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
            today = session_date(clock())
            rows = [r for r in rows if session_date(int(r["ts_ms"])) >= today]
            hub.on_ticks(root, recorder.append(root, contract, rows))

        feed = (feed_factory or TickFeed)(roots, on_live, on_subscribed=_refill)
    hub = Hub(history, clock)

    def status() -> dict:
        st = dict(feed.status())
        st["recorder"] = None if recorder is None else {
            "written": recorder.written, "buffered": recorder.buffered, "error": recorder.error}
        st["streams"] = len(hub.streams)
        st["clients"] = len(conns)
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
                if wall - last_status >= 2.0:
                    last_status = wall
                    st = {"type": "status", **status()}
                    for c in list(conns):
                        c.send(st)
            except Exception as e:  # noqa: BLE001 — the pump must never die
                log(f"pump: {type(e).__name__}: {e}")

    @asynccontextmanager
    async def lifespan(_app):
        if replay:
            for r, rs in feed.load().items():
                clf = SideClassifier()
                hub.start_today(r, replay, [from_row(x, clf) for x in rs], {
                    "date": replay.isoformat(), "contract": feed.contracts.get(r),
                    "source": "replay", "approx": False, "gaps": []})
        else:
            d = session_date(clock())
            for r in roots:
                start_last[r] = recorder.last_ts(r, d, symbols.resolve_contract(r))
                reseed(r)
        tasks = [asyncio.create_task(pump()), asyncio.create_task(feed.run())]
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
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "charts.html")

    @app.get("/api/status")
    async def api_status():
        return status()

    @app.get("/api/symbols")
    async def api_symbols():
        return {"roots": roots, "timeframes": TIMEFRAMES}

    def read_layouts() -> dict:
        try:
            return json.loads(layouts_path.read_text())
        except (OSError, ValueError):
            return {}

    def write_layouts(all_: dict) -> None:
        """Via a temp file + atomic rename: a crash or a full disk mid-write
        must never tear layouts.json (torn, it reads back as {} and the next
        save would wipe every layout)."""
        tmp = layouts_path.with_name(layouts_path.name + ".tmp")
        tmp.write_text(json.dumps(all_, indent=2))
        os.replace(tmp, layouts_path)

    @app.get("/api/layouts")
    async def get_layouts():
        return read_layouts()

    @app.put("/api/layouts/{name:path}")
    async def put_layout(name: str, request: Request):
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("cells"), list):
            raise HTTPException(400, "a layout is {grid, cells: [...]}")
        all_ = read_layouts()
        all_[name] = body
        write_layouts(all_)
        return {"ok": True}

    @app.delete("/api/layouts/{name:path}")
    async def delete_layout(name: str):
        all_ = read_layouts()
        all_.pop(name, None)
        write_layouts(all_)
        return {"ok": True}

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
