"""Audit 2026-10-27 (feed group): the chart service hands the Lab runner the prints a reconnect's refill found, keeps a refill
reserve for NQ/ES, and reads the day's tape for a refill off the event loop."""
from __future__ import annotations

import asyncio
import datetime as dt
import threading
import time

from fastapi.testclient import TestClient

from homebase.charts import server
from homebase.charts.server import TickFan, create_app
from homebase.core.tick import Tick
from tests.charts_util import D, rows, session_ms
from tests.test_charts_labrun_stream import parse, fan_of, take


def test_a_refill_batch_reaches_the_reader_as_its_own_event():
    async def go():
        fan = fan_of({"NQ": []})
        gen = fan.stream(["NQ"], 0, clock_s=60)
        await take(gen, 2)                                        # live + clock
        fan.publish_refill("NQ", [Tick(5, 100.0, 2, 1, 9)])
        fan.publish_refill("ES", [Tick(5, 1.0, 1, 1, 9)])         # not its market
        got = await take(gen, 1)
        await gen.aclose()
        return parse(got)
    assert asyncio.run(go()) == [("refill", {"root": "NQ", "rows": [[5, 100.0, 2, 1]]})]


class RefillFeed:
    def __init__(self, roots, on_ticks, on_subscribed=None):
        self.on_subscribed, self.ws, self.roots = on_subscribed, None, roots

    def count_request(self):
        pass

    def budget_used(self):
        return 0

    async def run(self):
        asyncio.create_task(self.on_subscribed("NQ", "NQZ6", session_ms(D, 9, 40)))
        while True:
            await asyncio.sleep(0.01)

    def stop(self):
        pass

    def status(self):
        return {"mode": "live", "connected": True, "error": None, "roots": {}, "budget_hour": 0, "reconnects": 0}


def test_the_refilled_prints_are_published_to_the_runner_and_the_load_is_off_the_loop(tmp_path, monkeypatch):
    got, loop_thread, load_threads = [], [], []
    miss = rows(session_ms(D, 9, 41), [100.0, 100.25, 100.5], first_id=70)

    async def fake_refill(ws, contract, frm, to, *, max_pages, sleep=None, on_request=None):
        return miss, to

    monkeypatch.setattr(server, "refill", fake_refill)
    monkeypatch.setattr(TickFan, "publish_refill", lambda self, root, ticks: got.append((root, [t.ts_ms for t in ticks])))
    real_load = server.TickStore.load

    def load(self, root, d):
        load_threads.append(threading.current_thread())
        return real_load(self, root, d)
    monkeypatch.setattr(server.TickStore, "load", load)
    app = create_app(roots=["NQ"], base=tmp_path / "ticks", feed_factory=RefillFeed,
                     now_ms=lambda: session_ms(D, 9, 45), state=tmp_path / "state")
    with TestClient(app):
        deadline = time.time() + 5
        while not got and time.time() < deadline:
            time.sleep(0.02)
    assert got == [("NQ", [int(r["ts_ms"]) for r in miss])]
    assert any(t is not threading.main_thread() for t in load_threads[1:] or load_threads)


def test_nq_and_es_keep_a_refill_reserve_the_others_do_not_get(tmp_path, monkeypatch):
    calls = []

    async def fake_refill(ws, contract, frm, to, *, max_pages, sleep=None, on_request=None):
        calls.append((contract, max_pages))
        return [], frm

    monkeypatch.setattr("homebase.charts.server.refill", fake_refill)

    class Feed(RefillFeed):
        def budget_used(self):
            return 70                                             # past the 60/h everyone else gets

        async def run(self):
            asyncio.create_task(self.on_subscribed("NQ", "NQZ6", session_ms(D, 9, 40)))
            asyncio.create_task(self.on_subscribed("YM", "YMZ6", session_ms(D, 9, 40)))
            while True:
                await asyncio.sleep(0.01)

    app = create_app(roots=["NQ", "YM"], base=tmp_path / "ticks", feed_factory=Feed,
                     now_ms=lambda: session_ms(D, 9, 45), state=tmp_path / "state")
    with TestClient(app):
        deadline = time.time() + 5
        while not calls and time.time() < deadline:
            time.sleep(0.02)
        time.sleep(0.2)
    assert [c for c, _ in calls] == ["NQZ6"] and calls[0][1] == 20


def test_a_reseed_does_not_apply_the_old_session_over_a_hub_that_rolled_during_its_reads(tmp_path, monkeypatch):
    clock_ms = [session_ms(D + dt.timedelta(days=1), 18, 5)]            # the hub starts on the NEXT session (after the 18:00 roll)
    applied, loads = [], []
    miss = rows(session_ms(D, 9, 41), [100.0, 100.25], first_id=70)

    async def fake_refill(ws, contract, frm, to, *, max_pages, sleep=None, on_request=None):
        return miss, to

    class Feed(RefillFeed):
        async def run(self):
            clock_ms[0] = session_ms(D, 9, 45)    # the refill runs while the clock names session D
            asyncio.create_task(self.on_subscribed("NQ", "NQZ6", session_ms(D, 9, 40)))
            while True:
                await asyncio.sleep(0.01)

    real_load, real_splice = server.TickStore.load, server.splice_tail

    def load(self, root, d):
        loads.append(d)
        if d == D:
            clock_ms[0] = session_ms(D + dt.timedelta(days=1), 18, 5)    # the roll lands while the files are read
        return real_load(self, root, d)

    def splice(*a, **kw):
        applied.append(1)
        return real_splice(*a, **kw)
    monkeypatch.setattr(server, "refill", fake_refill)
    monkeypatch.setattr(server.TickStore, "load", load)
    monkeypatch.setattr(server, "splice_tail", splice)
    app = create_app(roots=["NQ"], base=tmp_path / "ticks", feed_factory=Feed, now_ms=lambda: clock_ms[0],
                     state=tmp_path / "state")
    with TestClient(app):
        deadline = time.time() + 5
        while D not in loads and time.time() < deadline:
            time.sleep(0.02)
        time.sleep(0.3)
    assert loads and applied == []               # the stale session was not spliced onto the hub
