"""The chart service: FastAPI on :8852 — the page, the websocket, layouts,
status. Its own process; the trading app on :8850 only links to it.

    python -m homebase.charts                      # live, from the md feed
    python -m homebase.charts --replay 2026-09-24  # replay a session, records nothing
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

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


def log(msg: str) -> None:
    print(f"[charts] {dt.datetime.now(ET).strftime('%H:%M:%S')} {msg}", flush=True)


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

    async def _refill(root: str, contract: str, since_ms: int | None) -> None:
        """After a (re)subscribe: fetch what the socket missed, within budget."""
        d = session_date(clock())
        s0, _ = session_range_ms(d)
        frm = since_ms if since_ms is not None else (start_last.get(root) or s0)
        while QUIET[0] <= dt.datetime.fromtimestamp(clock() / 1000, ET).time() < QUIET[1]:
            await asyncio.sleep(15)
        to = clock()
        if to - frm < 2000:
            return
        rows: list[dict] = []
        reached = to
        if feed.budget_used() + REFILL_MAX_PAGES <= REFILL_BUDGET:
            try:
                rows, reached = await refill(feed.ws, contract, frm, to, on_request=feed.count_request)
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

    # the feed is built AFTER reseed/_refill exist (it takes _refill as its
    # callback); every function above only touches feed/hub/clock when called
    if replay:
        feed = ReplayFeed(store, roots, replay, lambda r, c, rows: hub.on_ticks(r, rows),
                          speed=speed, start_et=start_et)
        clock = feed.now_ms
    else:
        clock = now_ms or (lambda: int(time.time() * 1000))

        def on_live(root: str, contract: str, rows: list[dict]) -> None:
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
            try:
                hub.on_clock(clock() - CLOSE_GRACE_MS)
                for (conn, cid), msg in hub.drain():
                    conn.send({**msg, "id": cid})
                wall = time.monotonic()
                if recorder is not None and wall - last_flush >= 1.0:
                    recorder.flush()
                    last_flush = wall
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

    @app.get("/api/layouts")
    async def get_layouts():
        return read_layouts()

    @app.put("/api/layouts/{name}")
    async def put_layout(name: str, request: Request):
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("cells"), list):
            raise HTTPException(400, "a layout is {grid, cells: [...]}")
        all_ = read_layouts()
        all_[name] = body
        layouts_path.write_text(json.dumps(all_, indent=2))
        return {"ok": True}

    @app.delete("/api/layouts/{name}")
    async def delete_layout(name: str):
        all_ = read_layouts()
        all_.pop(name, None)
        layouts_path.write_text(json.dumps(all_, indent=2))
        return {"ok": True}

    @app.websocket("/ws")
    async def ws_endpoint(sock: WebSocket):
        await sock.accept()
        conn = Conn(sock)
        conns.add(conn)
        conn.send({"type": "status", **status()})
        try:
            while True:
                msg = await sock.receive_json()
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
                    keys = [str(k) for k in msg.get("studies") or []]
                    for k in keys:
                        if k != "profile":
                            make(k)
                except (ValueError, TypeError) as e:
                    conn.send({"type": "error", "id": cid, "error": str(e)})
                    continue
                hub.unsubscribe((conn, cid))
                s = hub.streams.get((root, spec.key))
                if s is None:
                    s = hub.attach(await asyncio.to_thread(hub.prepare, root, spec, keys))
                for k in keys:
                    s.add_study(k)
                hub.subscribe(s, (conn, cid))
                conn.send({"type": "history", "id": cid, **s.payload(bool(msg.get("fp", True)))})
        except WebSocketDisconnect:
            pass
        finally:
            conns.discard(conn)
            hub.drop_conn(conn)
            conn.task.cancel()

    return app
