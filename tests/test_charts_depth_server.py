"""Level 2 in the chart service (spec 2026-09-27 charts-depth, Part A):
the /api/status depth block, depth to a page with a chart on the root, the
shutdown flush, and no depth at all in replay. Fakes only: no broker."""
from __future__ import annotations

import asyncio
import datetime as dt
import queue
import time

from fastapi.testclient import TestClient

from homebase.charts.depth import read_depth
from tests.charts_util import D, rows, session_ms, write_archive
from tests.test_charts_depth import NQ, FakeWS, ladder, subs


class LiveFeed:
    """A live feed for create_app with a fake md socket, delivering no ticks."""

    def __init__(self, ws):
        self.ws = ws
        self.q: queue.Queue = queue.Queue()     # callables run on the service's loop (the md reader's thread)

    def __call__(self, roots, on_ticks, on_subscribed=None):
        self.contracts = {}
        return self

    async def run(self):
        while True:
            try:
                self.q.get_nowait()()
            except queue.Empty:
                await asyncio.sleep(0.01)

    def stop(self):
        pass

    def budget_used(self):
        return 0

    def count_request(self):
        raise AssertionError("depth must never count against the chart budget")

    def status(self):
        return {"mode": "live", "connected": True, "error": None, "roots": {},
                "budget_hour": 0, "reconnects": 0}


def wait_for(cond, timeout=5.0):
    deadline = time.time() + timeout
    while not cond() and time.time() < deadline:
        time.sleep(0.02)
    assert cond()


def test_status_carries_the_depth_block_and_pages_get_depth(tmp_path):
    from homebase.charts.server import create_app
    base = tmp_path / "ticks"
    write_archive(base, "NQ", D, "NQZ6", rows(session_ms(D, 9, 29), [200.0 + 0.25 * (i % 4) for i in range(60)]))
    ws = FakeWS()
    feed = LiveFeed(ws)
    app = create_app(roots=["NQ", "ES"], base=base, feed_factory=feed,
                     now_ms=lambda: session_ms(D, 9, 45), state=tmp_path / "state",
                     depth_roots=("NQ",), depth_base=tmp_path / "depth")
    with TestClient(app) as client:
        wait_for(lambda: subs(ws) == [NQ])
        st = client.get("/api/status").json()
        assert st["depth"]["NQ"] == {"subscribed": True, "levels": [0, 0], "age_s": None, "error": None}
        with client.websocket_connect("/ws", headers={"host": "localhost:8852"}) as page:
            page.send_json({"op": "sub", "id": "a", "root": "NQ", "spec": "time:60"})
            for _ in range(50):
                if page.receive_json().get("type") == "history":
                    break
            feed.q.put(lambda: ws.push(111, ladder(200.0, 25), ladder(200.25, 18, down=False)))
            for _ in range(200):
                m = page.receive_json()
                if m.get("type") == "depth" and m.get("ts") is not None:
                    break
            assert m["root"] == "NQ" and len(m["bids"]) == 20 and len(m["offers"]) == 18
            st = client.get("/api/status").json()
            d = st["depth"]["NQ"]
            assert d["subscribed"] and d["levels"] == [25, 18] and d["age_s"] is not None
            assert st["depth_recorder"]["error"] is None
        # ES is charted but not recorded: nobody asked for it, never subscribed
        assert subs(ws) == [NQ]
    # shutdown flushed the recording
    assert len(read_depth(tmp_path / "depth" / "NQ" / "2026" / f"{D}_{NQ}.depth.jsonl.gz")) == 1


def test_replay_makes_no_depth_subscriptions(tmp_path, monkeypatch):
    from homebase.charts import server

    def boom(*a, **k):
        raise AssertionError("replay must not build the depth feed")
    monkeypatch.setattr(server, "Depth", boom)
    base = tmp_path / "ticks"
    write_archive(base, "NQ", D, "NQZ6", rows(session_ms(D, 9, 29), [200.0 + 0.25 * (i % 4) for i in range(60)]))
    app = server.create_app(roots=["NQ"], base=base, replay=D, speed=1, start_et=dt.time(9, 30),
                            state=tmp_path / "state", depth_base=tmp_path / "depth")
    with TestClient(app) as client:
        st = client.get("/api/status").json()
        assert st["depth"] == {} and st["depth_recorder"] is None
    assert not (tmp_path / "depth").exists()
