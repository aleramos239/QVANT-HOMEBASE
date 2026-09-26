"""Chart server: replay end-to-end over the websocket, live-mode recording, layouts, errors."""
from __future__ import annotations

import asyncio
import datetime as dt
import queue
import time

from fastapi.testclient import TestClient

from homebase.charts.server import create_app
from homebase.charts.store import read_table
from tests.charts_util import D, rows, session_ms, write_archive

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
