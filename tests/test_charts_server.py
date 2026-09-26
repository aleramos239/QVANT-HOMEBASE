"""Chart server: replay end-to-end over the websocket, live-mode recording, layouts, errors."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import queue
import time

from fastapi.testclient import TestClient

from homebase.charts.hub import Hub
from homebase.charts.server import QUIET, create_app
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
        # Ruling 2: make("ema:20:30") raises TypeError (too many args), not ValueError —
        # the handler must catch it too, answer with an error, and keep the socket alive.
        ws.send_json({"op": "sub", "id": "d", "root": "NQ", "spec": "time:60", "studies": ["ema:20:30"]})
        assert next_of(ws, "error")["id"] == "d"
        ws.send_json({"op": "sub", "id": "e", "root": "NQ", "spec": "time:60"})
        assert next_of(ws, "history")["id"] == "e"
        # Fix round 1, item 3: make("adx:0") raises ZeroDivisionError (1.0/n with n=0) --
        # past (ValueError, TypeError) too. And a frame that isn't valid JSON must be
        # ignored, not fatal. The socket must still be usable after both.
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
    gp = base / root / str(D.year) / f"{D.isoformat()}_{root}.gaps.json"
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
