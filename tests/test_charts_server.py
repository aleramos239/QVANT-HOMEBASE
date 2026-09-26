"""Chart server: replay end-to-end over the websocket, live-mode recording, layouts, errors."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import plistlib
import queue
import time
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.testclient import TestClient

from homebase.charts.hub import Hub, Stream
from homebase.charts.server import MAX_DRAWINGS, QUIET, Conn, check_drawings, create_app
from homebase.charts.session import session_range_ms
from homebase.charts.store import read_table
from tests.charts_util import D, ET, rows, session_ms, write_archive

P = D - dt.timedelta(days=1)


def next_of(ws, kind, limit=200):
    for _ in range(limit):
        m = ws.receive_json()
        if m.get("type") == kind:
            return m
    raise AssertionError(f"no {kind!r} message")


def archive(tmp_path):
    base = tmp_path / "ticks"
    write_archive(base, "NQ", P, "NQZ6", rows(session_ms(P, 9, 30), [100.0 + 0.25 * (i % 4) for i in range(120)]))
    write_archive(base, "NQ", D, "NQZ6", rows(session_ms(D, 9, 29), [200.0 + 0.25 * (i % 4) for i in range(240)],
                                              first_id=5000))
    return base


def test_replay_serves_history_then_live_updates(tmp_path):
    app = create_app(roots=["NQ"], base=archive(tmp_path), replay=D, speed=50,
                     start_et=dt.time(9, 30), state=tmp_path / "state")
    with TestClient(app) as client:
        assert client.get("/api/status").json()["mode"] == "replay"
        assert client.get("/api/symbols").json()["roots"] == ["NQ"]
        assert client.get("/").status_code == 200
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"op": "sub", "id": "a", "root": "nq", "spec": "time:60", "studies": ["vwap", "profile"]})
            hist = next_of(ws, "history")
            assert hist["id"] == "a" and hist["bars"][0]["s"] == P.isoformat()
            assert hist["bars"][-1]["s"] == D.isoformat() and "vwap" in hist["studies"]
            assert hist["profile"]["poc"] > 0
            up = next_of(ws, "update")
            assert up["id"] == "a" and (up["closed"] or up["live"])
    assert not list((tmp_path / "ticks").rglob("*.live.csv.gz"))      # replay never records


def test_bad_requests_get_an_error_not_a_crash(tmp_path):
    app = create_app(roots=["NQ"], base=archive(tmp_path), replay=D, speed=1,
                     start_et=dt.time(9, 30), state=tmp_path / "state")
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"op": "sub", "id": "a", "root": "ZZ", "spec": "time:60"})
        assert "not recorded" in next_of(ws, "error")["error"]
        ws.send_json({"op": "sub", "id": "b", "root": "NQ", "spec": "time:0"})
        assert "bad bar type" in next_of(ws, "error")["error"]
        ws.send_json({"op": "sub", "id": "c", "root": "NQ", "spec": "time:60", "studies": ["nope"]})
        assert "unknown study" in next_of(ws, "error")["error"]
        # Ruling 2: make("ema:20:30") (too many args; once a TypeError, a ValueError since
        # FW-I4) must answer with an error and keep the socket alive.
        ws.send_json({"op": "sub", "id": "d", "root": "NQ", "spec": "time:60", "studies": ["ema:20:30"]})
        assert next_of(ws, "error")["id"] == "d"
        ws.send_json({"op": "sub", "id": "e", "root": "NQ", "spec": "time:60"})
        assert next_of(ws, "history")["id"] == "e"
        # Fix round 1, item 3: make("adx:0") (once a ZeroDivisionError, 1.0/n with n=0; a
        # ValueError since FW-I4) answers an error too. And a frame that isn't valid JSON
        # must be ignored, not fatal. The socket must still be usable after both.
        ws.send_json({"op": "sub", "id": "f", "root": "NQ", "spec": "time:60", "studies": ["adx:0"]})
        assert next_of(ws, "error")["id"] == "f"
        ws.send_text("not valid json {")
        ws.send_json({"op": "sub", "id": "g", "root": "NQ", "spec": "time:60"})
        assert next_of(ws, "history")["id"] == "g"


def test_layouts_roundtrip(tmp_path):
    app = create_app(roots=["NQ"], base=archive(tmp_path), replay=D, speed=1,
                     start_et=dt.time(9, 30), state=tmp_path / "state")
    with TestClient(app) as client:
        lay = {"grid": 2, "cells": [{"root": "NQ", "spec": "time:60", "st": {}}]}
        assert client.put("/api/layouts/main", json=lay).status_code == 200
        assert client.get("/api/layouts").json() == {"main": lay}
        client.delete("/api/layouts/main")
        assert client.get("/api/layouts").json() == {}

        # A name with "/" and a space -- exactly what the page's own
        # encodeURIComponent(name) produces and sends. Starlette decodes %2F to "/"
        # before routing, so a single-segment {name} path parameter 404s here;
        # {name:path} is required for any name to round-trip.
        name = "NQ/ES 2x2"
        url = "/api/layouts/" + quote(name, safe="")
        assert client.put(url, json=lay).status_code == 200
        assert client.get("/api/layouts").json() == {name: lay}
        assert client.delete(url).status_code == 200
        assert client.get("/api/layouts").json() == {}


def test_live_mode_records_what_the_feed_delivers(tmp_path):
    q: queue.Queue = queue.Queue()

    class FakeFeed:
        def __init__(self, roots, on_ticks, on_subscribed=None):
            self.on_ticks, self.ws = on_ticks, None

        async def run(self):
            while True:
                try:
                    self.on_ticks(*q.get_nowait())
                except queue.Empty:
                    await asyncio.sleep(0.01)

        def stop(self):
            pass

        def budget_used(self):
            return 0

        def count_request(self):
            pass

        def status(self):
            return {"mode": "live", "connected": True, "error": None, "roots": {},
                    "budget_hour": 0, "reconnects": 0}

    base = tmp_path / "ticks"
    app = create_app(roots=["NQ"], base=base, feed_factory=FakeFeed,
                     now_ms=lambda: session_ms(D, 9, 45), state=tmp_path / "state")
    live = base / "NQ" / "2026" / f"{D}_NQZ6.live.csv.gz"
    with TestClient(app) as client:
        q.put(("NQ", "NQZ6", rows(session_ms(D, 9, 40), [100.0, 100.25])))
        q.put(("NQ", "NQZ6", rows(session_ms(D, 9, 40), [100.0, 100.25])))   # duplicate delivery
        deadline = time.time() + 5
        while not live.exists() and time.time() < deadline:
            time.sleep(0.05)
        st = client.get("/api/status").json()
        assert st["mode"] == "live" and st["recorder"]["error"] is None
    header, recs = read_table(live)
    assert [r[header.index("id")] for r in recs] == ["1", "2"]


def test_refill_budget_is_serialized_and_never_exceeded(tmp_path, monkeypatch):
    """3 roots (re)subscribe at once with 27/60 already spent this hour. Every
    refill must be granted pages from a budget check made AFTER the previous
    refill's spend is visible (never a stale, simultaneous check), so the
    granted pages across all three can never exceed the 33 still available --
    and none of them may ever be mid-flight at the same time as another."""
    calls: list = []
    violations: list = []
    busy = [False]

    async def fake_refill(ws, contract, frm, to, *, max_pages, sleep=None, on_request=None):
        if busy[0]:
            violations.append(contract)
        busy[0] = True
        try:
            await asyncio.sleep(0)          # yield -- a real race would land another call here
            for _ in range(max_pages):
                if on_request:
                    on_request()
            calls.append({"root": contract, "frm": frm, "max_pages": max_pages})
            return [], frm
        finally:
            busy[0] = False

    monkeypatch.setattr("homebase.charts.server.refill", fake_refill)

    class FakeFeed:
        def __init__(self, roots, on_ticks, on_subscribed=None):
            self.on_ticks, self.on_subscribed, self.ws = on_ticks, on_subscribed, None
            self.roots, self.budget = roots, 27

        def count_request(self):
            self.budget += 1

        def budget_used(self):
            return self.budget

        async def run(self):
            for r in self.roots:
                asyncio.create_task(self.on_subscribed(r, r, None))
            while True:
                await asyncio.sleep(0.01)

        def stop(self):
            pass

        def status(self):
            return {"mode": "live", "connected": True, "error": None, "roots": {},
                    "budget_hour": self.budget, "reconnects": 0}

    base = tmp_path / "ticks"
    app = create_app(roots=["NQ", "ES", "YM"], base=base, feed_factory=FakeFeed,
                     now_ms=lambda: session_ms(D, 9, 45), state=tmp_path / "state")
    with TestClient(app):
        deadline = time.time() + 5
        while len(calls) < 2 and time.time() < deadline:
            time.sleep(0.02)
        time.sleep(0.2)          # let the third (budget-exhausted) root finish marking its gap

    assert violations == [], f"refill ran concurrently with itself: {violations}"
    assert len(calls) == 2, calls
    assert sum(c["max_pages"] for c in calls) <= 60 - 27
    skipped = {"NQ", "ES", "YM"} - {c["root"] for c in calls}
    assert len(skipped) == 1, skipped
    root = next(iter(skipped))
    gp = base / root / str(D.year) / f"{D.isoformat()}_{root}.live.gaps"
    assert json.loads(gp.read_text())


def test_refill_coalesces_same_root_requests_while_pending(tmp_path, monkeypatch):
    """A second refill request for a root that already has one pending (queued
    behind another root's in-flight fetch, in this case) must be absorbed into
    it -- one refill runs, covering the SMALLER of the two requested frm's --
    rather than the root being fetched twice."""
    calls: list = []

    async def fake_refill(ws, contract, frm, to, *, max_pages, sleep=None, on_request=None):
        if contract == "ES":
            await asyncio.sleep(0.2)        # occupies the lock while NQ's two calls queue up
        calls.append({"root": contract, "frm": frm})
        return [], frm

    monkeypatch.setattr("homebase.charts.server.refill", fake_refill)

    class FakeFeed:
        def __init__(self, roots, on_ticks, on_subscribed=None):
            self.on_ticks, self.on_subscribed, self.ws = on_ticks, on_subscribed, None

        def count_request(self):
            pass

        def budget_used(self):
            return 0

        async def run(self):
            asyncio.create_task(self.on_subscribed("ES", "ES", None))
            await asyncio.sleep(0.05)       # let ES acquire the lock and enter its fake fetch
            asyncio.create_task(self.on_subscribed("NQ", "NQ", session_ms(D, 9, 40)))
            await asyncio.sleep(0.05)       # let NQ's first call create its pending entry
            asyncio.create_task(self.on_subscribed("NQ", "NQ", session_ms(D, 9, 10)))
            while True:
                await asyncio.sleep(0.01)

        def stop(self):
            pass

        def status(self):
            return {"mode": "live", "connected": True, "error": None, "roots": {},
                    "budget_hour": 0, "reconnects": 0}

    base = tmp_path / "ticks"
    app = create_app(roots=["NQ", "ES"], base=base, feed_factory=FakeFeed,
                     now_ms=lambda: session_ms(D, 9, 45), state=tmp_path / "state")
    with TestClient(app):
        deadline = time.time() + 5
        while len(calls) < 2 and time.time() < deadline:
            time.sleep(0.02)
        time.sleep(0.1)

    nq_calls = [c for c in calls if c["root"] == "NQ"]
    assert len(nq_calls) == 1, f"expected exactly one NQ refill, got {nq_calls}"
    assert nq_calls[0]["frm"] == session_ms(D, 9, 10)


def test_refill_holds_the_quiet_window_while_paging(tmp_path, monkeypatch):
    """refill() paces pages ~21s apart; a refill starting just before 09:20
    must not let ANY page request land inside 09:20-09:35, however many pages
    it takes to page through the window. A fake, instantly-advancing clock
    (driven by the monkeypatched `sleep` seam) simulates real elapsed time
    with no actual wall-clock wait."""
    clock_ms = [session_ms(D, 9, 19, 50)]

    async def fake_sleep(s):
        clock_ms[0] += int(s * 1000)

    monkeypatch.setattr("homebase.charts.server.sleep", fake_sleep)

    request_times: list = []

    async def fake_refill(ws, contract, frm, to, *, max_pages, sleep=None, on_request=None):
        request_times.append(clock_ms[0])                # page 0: no pre-sleep, same as refill()
        for _ in range(1, max_pages):
            await sleep(21)                               # refill()'s own PAGE_INTERVAL_S pacing
            request_times.append(clock_ms[0])
        return [], frm

    monkeypatch.setattr("homebase.charts.server.refill", fake_refill)

    class FakeFeed:
        def __init__(self, roots, on_ticks, on_subscribed=None):
            self.on_ticks, self.on_subscribed, self.ws = on_ticks, on_subscribed, None

        def count_request(self):
            pass

        def budget_used(self):
            return 0

        async def run(self):
            asyncio.create_task(self.on_subscribed("NQ", "NQZ6", session_ms(D, 8, 0)))
            while True:
                await asyncio.sleep(0.01)

        def stop(self):
            pass

        def status(self):
            return {"mode": "live", "connected": True, "error": None, "roots": {},
                    "budget_hour": 0, "reconnects": 0}

    base = tmp_path / "ticks"
    app = create_app(roots=["NQ"], base=base, feed_factory=FakeFeed,
                     now_ms=lambda: clock_ms[0], state=tmp_path / "state")
    with TestClient(app):
        deadline = time.time() + 5
        while len(request_times) < 20 and time.time() < deadline:
            time.sleep(0.02)

    assert len(request_times) == 20

    def in_quiet(ms):
        t = dt.datetime.fromtimestamp(ms / 1000, ET).time()
        return QUIET[0] <= t < QUIET[1]

    assert not any(in_quiet(t) for t in request_times), request_times


def test_flush_runs_even_when_chart_work_raises(tmp_path, monkeypatch):
    """The recorder's flush must not share fate with hub.on_clock()/drain():
    even if chart bookkeeping raises on every pump tick, ticks the feed
    delivered must still land on disk."""

    def boom_drain(self):
        raise RuntimeError("drain boom")

    monkeypatch.setattr(Hub, "drain", boom_drain)

    q: queue.Queue = queue.Queue()

    class FakeFeed:
        def __init__(self, roots, on_ticks, on_subscribed=None):
            self.on_ticks, self.ws = on_ticks, None

        async def run(self):
            while True:
                try:
                    self.on_ticks(*q.get_nowait())
                except queue.Empty:
                    await asyncio.sleep(0.01)

        def stop(self):
            pass

        def budget_used(self):
            return 0

        def count_request(self):
            pass

        def status(self):
            return {"mode": "live", "connected": True, "error": None, "roots": {},
                    "budget_hour": 0, "reconnects": 0}

    base = tmp_path / "ticks"
    app = create_app(roots=["NQ"], base=base, feed_factory=FakeFeed,
                     now_ms=lambda: session_ms(D, 9, 45), state=tmp_path / "state")
    live = base / "NQ" / "2026" / f"{D}_NQZ6.live.csv.gz"
    with TestClient(app):
        q.put(("NQ", "NQZ6", rows(session_ms(D, 9, 40), [100.0, 100.25])))
        deadline = time.time() + 5
        while not live.exists() and time.time() < deadline:
            time.sleep(0.05)
        # Must exist WHILE the app is still running (the pump's periodic flush) --
        # checking only after the `with` block exits would also pass on broken code,
        # since lifespan's shutdown does its own unconditional final flush.
        assert live.exists(), "the live file should appear from the pump's periodic " \
                               "flush, not only from the one at shutdown"

    header, recs = read_table(live)
    assert [r[header.index("id")] for r in recs] == ["1", "2"]


def test_ws_handler_ends_cleanly_after_close_mid_prepare(tmp_path, monkeypatch):
    """A queue-overflow close (Conn._close()) landing while prepare() runs in
    its own worker thread must not spin the receive loop forever. After an
    app-side close, starlette's receive_json()/receive_text() raise a
    RuntimeError SYNCHRONOUSLY (before any await -- checked against
    application_state before ever touching the transport), so a broad
    `except Exception: continue` around that call never yields control back
    to the loop, freezing the pump (and everything else on it) at 100% CPU.
    Reproduces the reviewer's own probe technique (probe_ws_spin.py)."""
    app = create_app(roots=["NQ"], base=archive(tmp_path), replay=D, speed=1,
                     start_et=dt.time(9, 30), state=tmp_path / "state")

    cap: dict = {}
    orig_conn_init = Conn.__init__

    def conn_init(self, ws):
        orig_conn_init(self, ws)
        cap["conn"], cap["loop"] = self, asyncio.get_running_loop()

    monkeypatch.setattr(Conn, "__init__", conn_init)

    orig_prepare = Hub.prepare

    def prepare(self, root, spec, keys):
        # close the socket app-side exactly when the (worker-thread) history
        # build would be running -- a SEND_QUEUE_MAX overflow could land here
        asyncio.run_coroutine_threadsafe(cap["conn"]._close(), cap["loop"]).result(timeout=5)
        return orig_prepare(self, root, spec, keys)

    monkeypatch.setattr(Hub, "prepare", prepare)

    pump_ticks = [0]
    orig_on_clock = Hub.on_clock

    def on_clock(self, now_ms):
        pump_ticks[0] += 1
        return orig_on_clock(self, now_ms)

    monkeypatch.setattr(Hub, "on_clock", on_clock)

    # Safety net for a RED run against a genuinely spinning handler: force a
    # clean disconnect once 1.5s of wall time has passed since the second
    # receive attempt, so a bug here fails this test in bounded time instead
    # of hanging the suite. Wraps BOTH receive_json (what the pre-fix code
    # calls) and receive_text (what the fix calls), sharing one counter, so
    # the same test is meaningful before and after the fix.
    calls = [0]
    marks: dict = {}

    def wrap(orig):
        async def wrapper(self, *a, **k):
            calls[0] += 1
            if calls[0] == 2:
                marks["t0"] = time.perf_counter()
            if "t0" in marks and time.perf_counter() - marks["t0"] > 1.5:
                raise WebSocketDisconnect(4000)
            return await orig(self, *a, **k)
        return wrapper

    monkeypatch.setattr(WebSocket, "receive_json", wrap(WebSocket.receive_json))
    monkeypatch.setattr(WebSocket, "receive_text", wrap(WebSocket.receive_text))

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"op": "sub", "id": "a", "root": "NQ", "spec": "time:60"})
            time.sleep(2.0)

    assert calls[0] < 1000, f"receive spun {calls[0]} times in ~2s -- the handler did not end cleanly"
    assert pump_ticks[0] > 0, "the pump never ticked -- the event loop was starved"


def test_refill_running_gets_a_followup_not_absorbed(tmp_path, monkeypatch):
    """A request for a root whose refill is already RUNNING (holding the
    lock, mid-fetch) must not be absorbed into it: the running fetch's `to`
    was already fixed before the new request existed, so absorbing would
    silently lose whatever the new request needed after that `to`. It must
    become a follow-up instead -- a second fetch, with its own fresh `to`.
    Reproduces the reviewer's probe_coalesce_running.py scenario: refill #1
    (missed 09:40->09:45) is running when the md socket flaps and TickFeed
    resubscribes with since=09:45:30."""
    clock_ms = [session_ms(D, 9, 45)]
    calls: list = []

    async def fake_refill(ws, contract, frm, to, *, max_pages, sleep=None, on_request=None):
        calls.append((contract, frm, to))
        await asyncio.sleep(0.3)          # paging (real time); a flap can land meanwhile
        return [], frm                     # the whole requested stretch was covered

    monkeypatch.setattr("homebase.charts.server.refill", fake_refill)

    class FakeFeed:
        def __init__(self, roots, on_ticks, on_subscribed=None):
            self.on_subscribed, self.ws = on_subscribed, None

        def count_request(self):
            pass

        def budget_used(self):
            return 0

        async def run(self):
            asyncio.create_task(self.on_subscribed("NQ", "NQZ6", session_ms(D, 9, 40)))
            await asyncio.sleep(0.1)               # refill #1 now holds the lock, mid-fetch
            clock_ms[0] = session_ms(D, 9, 46)     # reconnected; last tick seen 09:45:30
            asyncio.create_task(self.on_subscribed("NQ", "NQZ6", session_ms(D, 9, 45, 30)))
            while True:
                await asyncio.sleep(0.01)

        def stop(self):
            pass

        def status(self):
            return {"mode": "live", "connected": True, "error": None, "roots": {},
                    "budget_hour": 0, "reconnects": 0}

    base = tmp_path / "ticks"
    app = create_app(roots=["NQ"], base=base, feed_factory=FakeFeed,
                     now_ms=lambda: clock_ms[0], state=tmp_path / "state")
    with TestClient(app):
        deadline = time.time() + 5
        while len(calls) < 2 and time.time() < deadline:
            time.sleep(0.02)
        time.sleep(0.1)

    assert len(calls) == 2, calls
    assert calls[0] == ("NQZ6", session_ms(D, 9, 40), session_ms(D, 9, 45))
    assert calls[1][0] == "NQZ6" and calls[1][1] == session_ms(D, 9, 45, 30)
    assert calls[1][2] >= session_ms(D, 9, 46)          # fresh `to`, read after it arrived
    gp = base / "NQ" / str(D.year) / f"{D.isoformat()}_NQZ6.live.gaps"
    gaps = json.loads(gp.read_text()) if gp.exists() else []
    lo, hi = session_ms(D, 9, 45, 30), session_ms(D, 9, 46)
    covered = any(a <= lo and b >= hi for _, a, b in calls) or any(a <= lo and b >= hi for a, b in gaps)
    assert covered, "the 09:45:30 -> 09:46:00 stretch was neither fetched nor marked as a gap"


def test_refill_rechecks_quiet_window_after_the_lock(tmp_path, monkeypatch):
    """The pre-lock _quiet_wait() can be stale by the time the lock is
    actually granted (another root's fetch can run long enough to cross into
    09:20); page 0 has no pre-sleep of its own. Reproduces the reviewer's
    probe_quiet_after_lock.py: ES sends page 0 at 09:19:58 and releases the
    lock at 09:20:01; the queued NQ refill must not then send its own page 0
    at 09:20:01."""
    clock_ms = [session_ms(D, 9, 19, 58)]

    async def fake_sleep(s):
        clock_ms[0] += int(s * 1000)

    monkeypatch.setattr("homebase.charts.server.sleep", fake_sleep)

    reqs: list = []

    async def fake_refill(ws, contract, frm, to, *, max_pages, sleep=None, on_request=None):
        reqs.append((contract, clock_ms[0]))          # page 0: refill() sends it with no pre-sleep
        await asyncio.sleep(0.05)                       # real yield: the other root queues on the lock
        clock_ms[0] += 3000                              # round trip + unpack; one page covered the gap
        return [], frm

    monkeypatch.setattr("homebase.charts.server.refill", fake_refill)

    class FakeFeed:
        def __init__(self, roots, on_ticks, on_subscribed=None):
            self.on_subscribed, self.ws = on_subscribed, None

        def count_request(self):
            pass

        def budget_used(self):
            return 0

        async def run(self):
            asyncio.create_task(self.on_subscribed("ES", "ESZ6", session_ms(D, 9, 19, 0)))
            asyncio.create_task(self.on_subscribed("NQ", "NQZ6", session_ms(D, 9, 19, 0)))
            while True:
                await asyncio.sleep(0.01)

        def stop(self):
            pass

        def status(self):
            return {"mode": "live", "connected": True, "error": None, "roots": {},
                    "budget_hour": 0, "reconnects": 0}

    app = create_app(roots=["ES", "NQ"], base=tmp_path / "ticks", feed_factory=FakeFeed,
                     now_ms=lambda: clock_ms[0], state=tmp_path / "state")
    with TestClient(app):
        deadline = time.time() + 5
        while len(reqs) < 2 and time.time() < deadline:
            time.sleep(0.02)
        time.sleep(0.1)

    assert len(reqs) == 2, reqs

    def in_quiet(ms):
        t = dt.datetime.fromtimestamp(ms / 1000, ET).time()
        return QUIET[0] <= t < QUIET[1]

    assert not any(in_quiet(ms) for _, ms in reqs), reqs


def test_a_failed_subscribe_leaves_no_orphaned_stream_or_pending_update(tmp_path, monkeypatch):
    """If s.payload() raises AFTER hub.subscribe() has already registered the
    sub, it must not stay registered -- otherwise the pump keeps sending
    `update`s for an id that only ever received `error`, never `history`."""
    orig_payload = Stream.payload
    calls = [0]

    def payload(self, fp=True):
        calls[0] += 1
        if calls[0] == 1:
            raise RuntimeError("payload boom")
        return orig_payload(self, fp)

    monkeypatch.setattr(Stream, "payload", payload)

    sent: list = []
    orig_send = Conn.send

    def send(self, msg):
        sent.append(dict(msg))
        return orig_send(self, msg)

    monkeypatch.setattr(Conn, "send", send)

    app = create_app(roots=["NQ"], base=archive(tmp_path), replay=D, speed=50,
                     start_et=dt.time(9, 30), state=tmp_path / "state")
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"op": "sub", "id": "a", "root": "NQ", "spec": "time:60"})
        assert next_of(ws, "error")["id"] == "a"
        ws.send_json({"op": "sub", "id": "b", "root": "NQ", "spec": "time:60"})
        assert next_of(ws, "history")["id"] == "b"
        time.sleep(0.6)

    assert not any(m.get("type") == "update" and m.get("id") == "a" for m in sent), sent


class QueueFeed:
    """A live feed the test drives: every item put on `q` is delivered to
    on_ticks; `delivered` counts the ones that were."""

    def __init__(self, q, delivered):
        self.q, self.delivered = q, delivered

    def __call__(self, roots, on_ticks, on_subscribed=None):
        self.on_ticks, self.ws = on_ticks, None
        return self

    async def run(self):
        while True:
            try:
                self.on_ticks(*self.q.get_nowait())
                self.delivered.append(1)
            except queue.Empty:
                await asyncio.sleep(0.01)

    def stop(self):
        pass

    def budget_used(self):
        return 0

    def count_request(self):
        pass

    def status(self):
        return {"mode": "live", "connected": True, "error": None, "roots": {},
                "budget_hour": 0, "reconnects": 0}


def test_a_previous_session_print_is_neither_recorded_nor_charted(tmp_path):
    """Weekend start (the first install): the subscribe's one historical
    trade is Friday's last print. It used to file a 1-tick Friday live file
    (which store.pick prefers to an INCOMPLETE archive, permanently) and
    roll the charts back to Friday (Friday = one bar of one lot). A chart
    opened afterwards must show Friday's whole session, and nothing may be
    recorded."""
    thu, fri = dt.date(2026, 9, 24), dt.date(2026, 9, 25)
    sat_10 = int(dt.datetime(2026, 9, 26, 10, 0, tzinfo=ET).timestamp() * 1000)
    base = tmp_path / "ticks"
    write_archive(base, "NQ", thu, "NQZ6", rows(session_ms(thu, 9, 30), [100.0 + 0.25 * (i % 4) for i in range(600)]))
    fri_rows = rows(session_ms(fri, 9, 30), [200.0 + 0.25 * (i % 4) for i in range(600)], first_id=5000)
    write_archive(base, "NQ", fri, "NQZ6", fri_rows, complete=False)
    q: queue.Queue = queue.Queue()
    delivered: list = []
    app = create_app(roots=["NQ"], base=base, feed_factory=QueueFeed(q, delivered),
                     now_ms=lambda: sat_10, state=tmp_path / "state")
    with TestClient(app) as client:
        q.put(("NQ", "NQZ6", [dict(fri_rows[-1], id=987_654_321)]))    # a Tradovate id
        deadline = time.time() + 5
        while not delivered and time.time() < deadline:
            time.sleep(0.02)
        assert delivered
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"op": "sub", "id": "a", "root": "NQ", "spec": "time:60"})
            hist = next_of(ws, "history")
    fri_bars = [b for b in hist["bars"] if b["s"] == fri.isoformat()]
    assert len(fri_bars) == 10 and sum(b["v"] for b in fri_bars) == 600
    assert not list(base.rglob("*.live.csv.gz"))


def test_a_refill_never_pages_back_past_the_session_open(tmp_path, monkeypatch):
    """A reconnect's `since` can be the previous session's last tick (a
    weekend straggler, a socket that dropped before the 17:00 close). The
    refill starts at the current session's open: paging back into the
    previous session would file its ticks as that session's live file."""
    calls: list = []

    async def fake_refill(ws, contract, frm, to, *, max_pages, sleep=None, on_request=None):
        calls.append(frm)
        return [], frm

    monkeypatch.setattr("homebase.charts.server.refill", fake_refill)

    class FakeFeed:
        def __init__(self, roots, on_ticks, on_subscribed=None):
            self.on_subscribed, self.ws = on_subscribed, None

        def count_request(self):
            pass

        def budget_used(self):
            return 0

        async def run(self):
            asyncio.create_task(self.on_subscribed("NQ", "NQZ6", session_ms(P, 16, 0)))
            while True:
                await asyncio.sleep(0.01)

        def stop(self):
            pass

        def status(self):
            return {"mode": "live", "connected": True, "error": None, "roots": {},
                    "budget_hour": 0, "reconnects": 0}

    app = create_app(roots=["NQ"], base=tmp_path / "ticks", feed_factory=FakeFeed,
                     now_ms=lambda: session_ms(D, 9, 45), state=tmp_path / "state")
    with TestClient(app):
        deadline = time.time() + 5
        while not calls and time.time() < deadline:
            time.sleep(0.02)
    assert calls == [session_range_ms(D)[0]]                 # 18:00 ET the evening before D


def replay_app(tmp_path):
    return create_app(roots=["NQ"], base=archive(tmp_path), replay=D, speed=1,
                      start_et=dt.time(9, 30), state=tmp_path / "state")


def test_ws_refuses_a_page_from_another_site(tmp_path):
    """Browsers apply no CORS to websocket handshakes: any page open in the
    desk machine's browser could open /ws and queue chart work. A handshake
    whose Origin is neither this service's host nor localhost is refused; no
    Origin at all (not a browser: scripts, tests) is allowed."""
    with TestClient(replay_app(tmp_path)) as client:
        for origin in ("https://evil.example", "http://testserver.evil.example", "null"):
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/ws", headers={"origin": origin}) as ws:
                    ws.receive_json()
        for origin in ("http://testserver", "http://localhost:3000", "http://127.0.0.1:8852"):
            with client.websocket_connect("/ws", headers={"origin": origin}) as ws:
                assert ws.receive_json()["type"] == "status"
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json()["type"] == "status"


def first_answer(ws, cid, limit=200):
    """The history or error that answers subscription `cid`."""
    for _ in range(limit):
        m = ws.receive_json()
        if m.get("id") == cid and m.get("type") in ("history", "error"):
            return m
    raise AssertionError(f"no answer for {cid!r}")


def test_subscriptions_are_bounded(tmp_path):
    """tick:1 cost ~4 s of payload on the event loop and ~185 MB of JSON per
    session, and study counts were unbounded. Bars finer than time:5 /
    tick:100 / volume:100 / range:2, or more than 16 studies, answer an
    error (the page shows it in the chart)."""
    with TestClient(replay_app(tmp_path)) as client, client.websocket_connect("/ws") as ws:
        for spec in ("time:4", "tick:99", "volume:99", "range:1", "tick:1"):
            ws.send_json({"op": "sub", "id": spec, "root": "NQ", "spec": spec})
            m = first_answer(ws, spec)
            assert m["type"] == "error" and "minimum" in m["error"], m
        emas = [f"ema:{n}" for n in range(1, 18)]
        ws.send_json({"op": "sub", "id": "17", "root": "NQ", "spec": "time:60", "studies": emas})
        assert first_answer(ws, "17")["type"] == "error"
        ws.send_json({"op": "sub", "id": "long", "root": "NQ", "spec": "time:60", "studies": ["sma:1001"]})
        assert first_answer(ws, "long")["type"] == "error"
        ws.send_json({"op": "sub", "id": "16", "root": "NQ", "spec": "tick:100", "studies": emas[:16]})
        assert first_answer(ws, "16")["type"] == "history"
        for spec in ("time:5", "volume:100", "range:2"):
            ws.send_json({"op": "sub", "id": spec, "root": "NQ", "spec": spec})
            assert first_answer(ws, spec)["type"] == "history"


def test_a_failed_layout_write_leaves_the_saved_layouts_intact(tmp_path, monkeypatch):
    """layouts.json was rewritten in place: a crash or a full disk mid-write
    left it torn, it read back as {}, and the next save wiped every layout.
    Writes go to a temp file that atomically replaces the old one."""
    lay = {"grid": 2, "cells": [{"root": "NQ", "spec": "time:60", "st": {}}]}
    real_write_text = Path.write_text

    def torn(self, data, *a, **k):
        real_write_text(self, data[: len(data) // 2], *a, **k)
        raise OSError(28, "No space left on device")

    with TestClient(replay_app(tmp_path)) as client:
        assert client.put("/api/layouts/main", json=lay).status_code == 200
        with monkeypatch.context() as m:
            m.setattr(Path, "write_text", torn)
            with pytest.raises(OSError):
                client.put("/api/layouts/other", json=lay)
            with pytest.raises(OSError):
                client.delete("/api/layouts/main")
        assert client.get("/api/layouts").json() == {"main": lay}


def test_status_keeps_flowing_and_says_so_while_chart_work_fails(tmp_path, monkeypatch):
    """The status broadcast shared the pump's try with on_clock/drain: a
    persistent chart failure froze every page's status strip on its last
    (green) message. It runs in its own try, and names the failure."""
    def boom_drain(self):
        raise RuntimeError("drain boom")

    monkeypatch.setattr(Hub, "drain", boom_drain)
    monkeypatch.setattr("homebase.charts.server.STATUS_S", 0.05)
    sent: list = []
    orig_send = Conn.send

    def send(self, msg):
        sent.append(dict(msg))
        return orig_send(self, msg)

    monkeypatch.setattr(Conn, "send", send)
    with TestClient(replay_app(tmp_path)) as client, client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "status"        # the one sent on connect
        time.sleep(0.8)
    statuses = [m for m in sent if m.get("type") == "status"]
    assert len(statuses) >= 3, statuses
    assert "drain boom" in (statuses[-1].get("error") or ""), statuses[-1]


def test_a_refill_that_changed_nothing_does_not_reload_the_charts(tmp_path, monkeypatch):
    """Every token-expiry reconnect refills each root. A refill that added no
    tick and marked no gap must not reseed: that resets and reloads every
    open chart of the root for nothing."""
    seeds: list = []
    orig_start_today = Hub.start_today

    def start_today(self, root, d, ticks, info=None):
        seeds.append(root)
        return orig_start_today(self, root, d, ticks, info)

    monkeypatch.setattr(Hub, "start_today", start_today)
    calls: list = []

    async def fake_refill(ws, contract, frm, to, *, max_pages, sleep=None, on_request=None):
        calls.append(frm)
        got = [] if len(calls) == 1 else rows(session_ms(D, 9, 44), [100.0], first_id=42)
        return got, frm                                      # the stretch is covered either way

    monkeypatch.setattr("homebase.charts.server.refill", fake_refill)

    class FakeFeed:
        def __init__(self, roots, on_ticks, on_subscribed=None):
            self.on_subscribed, self.ws = on_subscribed, None

        def count_request(self):
            pass

        def budget_used(self):
            return 0

        async def run(self):
            await self.on_subscribed("NQ", "NQZ6", session_ms(D, 9, 40))    # nothing was missed
            await self.on_subscribed("NQ", "NQZ6", session_ms(D, 9, 43))    # one tick was missed
            while True:
                await asyncio.sleep(0.01)

        def stop(self):
            pass

        def status(self):
            return {"mode": "live", "connected": True, "error": None, "roots": {},
                    "budget_hour": 0, "reconnects": 0}

    app = create_app(roots=["NQ"], base=tmp_path / "ticks", feed_factory=FakeFeed,
                     now_ms=lambda: session_ms(D, 9, 45), state=tmp_path / "state")
    with TestClient(app):
        deadline = time.time() + 5
        while len(calls) < 2 and time.time() < deadline:
            time.sleep(0.02)
        time.sleep(0.2)
    assert len(calls) == 2
    assert seeds == ["NQ", "NQ"]                             # startup + the refill that added a tick


def test_the_charts_job_yields_the_cpu_to_the_trading_app():
    """At 09:30 the trading process must win the CPU over chart work: the
    charts launchd job runs at nice 5."""
    tpl = Path(__file__).resolve().parent.parent / "deploy" / "com.ramosquant.homebase-charts.plist.template"
    job = plistlib.loads(tpl.read_bytes().replace(b"__REPO__", b"/repo"))
    assert job["Label"] == "com.ramosquant.homebase-charts" and job.get("Nice") == 5


TREND = {"id": "d1", "type": "trend", "color": "#2962FF",
         "points": [{"t": 1790000000000, "p": 30900.25}, {"t": 1790000600000, "p": 30950.0}]}
HLINE = {"id": "d2", "type": "hline", "points": [{"p": 30925.5}]}
RECT = {"id": "d3", "type": "rect",
        "points": [{"t": 1790000000000, "p": 30900}, {"t": 1790000300000, "p": 30880.75}]}


def test_drawings_roundtrip_per_root(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "drawings.json").write_text(json.dumps({"ES": [HLINE]}))   # another root's drawings
    with TestClient(replay_app(tmp_path)) as client:
        assert client.get("/api/drawings/NQ").json() == []
        r = client.put("/api/drawings/NQ", json=[TREND, HLINE, RECT])
        assert r.status_code == 200 and r.json() == {"ok": True, "count": 3}
        assert client.get("/api/drawings/NQ").json() == [TREND, HLINE, RECT]
        assert client.get("/api/drawings/nq").json() == [TREND, HLINE, RECT]
        assert json.loads((state / "drawings.json").read_text()) == {"ES": [HLINE], "NQ": [TREND, HLINE, RECT]}
        assert client.put("/api/drawings/NQ", json=[]).status_code == 200
        assert client.get("/api/drawings/NQ").json() == []
        assert client.get("/api/drawings/ZZ").status_code == 404
        assert client.put("/api/drawings/ZZ", json=[]).status_code == 404


def test_drawings_keep_only_what_the_page_draws():
    """Unknown keys are dropped; a horizontal line keeps only its price."""
    body = [{"id": "a", "type": "hline", "points": [{"p": 1.5, "t": 7, "x": 1}], "junk": True},
            {"id": "b", "type": "trend", "points": [{"t": 1, "p": 2, "q": 0}, {"t": 3, "p": 4}]}]
    assert check_drawings(body) == [{"id": "a", "type": "hline", "points": [{"p": 1.5}]},
                                    {"id": "b", "type": "trend", "points": [{"t": 1, "p": 2}, {"t": 3, "p": 4}]}]


H1 = {"id": "a", "type": "hline", "points": [{"p": 1}]}
BAD = [
    ("not a list", {"id": "x"}),
    ("item not an object", ["x"]),
    ("id missing", [{"type": "hline", "points": [{"p": 1}]}]),
    ("id empty", [{**H1, "id": ""}]),
    ("id too long", [{**H1, "id": "x" * 41}]),
    ("id not a string", [{**H1, "id": 7}]),
    ("unknown type", [{**H1, "type": "fib"}]),
    ("trend with one point", [{"id": "a", "type": "trend", "points": [{"t": 1, "p": 1}]}]),
    ("hline with two points", [{**H1, "points": [{"p": 1}, {"p": 2}]}]),
    ("points not a list", [{**H1, "points": {"p": 1}}]),
    ("point not an object", [{**H1, "points": [1]}]),
    ("t missing", [{"id": "a", "type": "rect", "points": [{"p": 1}, {"t": 2, "p": 2}]}]),
    ("t a float", [{"id": "a", "type": "trend", "points": [{"t": 1.5, "p": 1}, {"t": 2, "p": 2}]}]),
    ("t a bool", [{"id": "a", "type": "trend", "points": [{"t": True, "p": 1}, {"t": 2, "p": 2}]}]),
    ("p missing", [{**H1, "points": [{}]}]),
    ("p a string", [{**H1, "points": [{"p": "1"}]}]),
    ("p a bool", [{**H1, "points": [{"p": False}]}]),
    ("p not finite", [{**H1, "points": [{"p": float("inf")}]}]),
    ("colour a name", [{**H1, "color": "red"}]),
    ("colour too short", [{**H1, "color": "#12345"}]),
]


@pytest.mark.parametrize("why,body", BAD, ids=[b[0] for b in BAD])
def test_check_drawings_refuses_malformed_bodies(why, body):
    with pytest.raises(ValueError):
        check_drawings(body)


def test_check_drawings_caps_the_list():
    assert len(check_drawings([H1] * MAX_DRAWINGS)) == MAX_DRAWINGS
    with pytest.raises(ValueError):
        check_drawings([H1] * (MAX_DRAWINGS + 1))


def test_a_bad_drawings_body_is_a_400_and_saves_nothing(tmp_path):
    with TestClient(replay_app(tmp_path)) as client:
        assert client.put("/api/drawings/NQ", json=[H1]).status_code == 200
        r = client.put("/api/drawings/NQ", json=[{**H1, "type": "fib"}])
        assert r.status_code == 400 and "type" in r.json()["detail"]
        nan = '[{"id": "a", "type": "hline", "points": [{"p": NaN}]}]'
        assert client.put("/api/drawings/NQ", content=nan,
                          headers={"content-type": "application/json"}).status_code == 400
        assert client.put("/api/drawings/NQ", content="not json",
                          headers={"content-type": "application/json"}).status_code == 400
        assert client.get("/api/drawings/NQ").json() == [H1]


def test_browser_writes_from_another_site_are_refused(tmp_path):
    """Any page open in the desk machine's browser could otherwise rewrite
    or delete saved layouts and drawings (same rule as the /ws handshake)."""
    lay = {"grid": 2, "cells": [{"root": "NQ", "spec": "time:60", "indicators": []}]}
    evil = {"origin": "https://evil.example"}
    with TestClient(replay_app(tmp_path)) as client:
        assert client.put("/api/layouts/main", json=lay, headers=evil).status_code == 403
        assert client.put("/api/drawings/NQ", json=[H1], headers=evil).status_code == 403
        assert client.put("/api/layouts/main", json=lay).status_code == 200            # no Origin: not a browser
        assert client.delete("/api/layouts/main", headers=evil).status_code == 403
        assert client.get("/api/layouts").json() == {"main": lay}
        assert client.get("/api/drawings/NQ").json() == []
        for ok in ("http://localhost:8852", "http://127.0.0.1:8852", "http://testserver"):
            assert client.put("/api/drawings/NQ", json=[H1], headers={"origin": ok}).status_code == 200
        assert client.delete("/api/layouts/main", headers={"origin": "http://localhost:8852"}).status_code == 200


def test_a_failed_drawings_write_leaves_the_saved_drawings_intact(tmp_path, monkeypatch):
    real_write_text = Path.write_text

    def torn(self, data, *a, **k):
        real_write_text(self, data[: len(data) // 2], *a, **k)
        raise OSError(28, "No space left on device")

    with TestClient(replay_app(tmp_path)) as client:
        assert client.put("/api/drawings/NQ", json=[H1]).status_code == 200
        with monkeypatch.context() as m:
            m.setattr(Path, "write_text", torn)
            with pytest.raises(OSError):
                client.put("/api/drawings/NQ", json=[TREND])
        assert client.get("/api/drawings/NQ").json() == [H1]
