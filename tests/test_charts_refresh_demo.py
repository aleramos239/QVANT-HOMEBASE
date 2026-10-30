"""Refresh data on a demo-only Mac (2026-10-30, owner: "i want it to fill the gaps when i click the button").

The click used to be refused there (the tick job would take the live md seat from the server). Now the chart service
refetches the gaps marked in today's recording over its own socket -- a refill that failed while the socket was down
is never retried by the feed (NQ 2026-10-30 14:53-15:06 ET) -- then tickpull copies the server's finished days."""
from __future__ import annotations

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from homebase.charts import refresh as R
from homebase.charts import store as S
from homebase.charts.recorder import LiveRecorder
from homebase.charts.server import create_app
from homebase.charts.store import read_table
from tests.charts_util import D, rows, session_ms, write_gz
from tests.test_charts_refresh import manager, wait_final


@pytest.fixture
def demo_only(monkeypatch):
    monkeypatch.setenv("HOMEBASE_CHARTS_MD_ONLY", "demo")


def test_a_demo_only_mac_refetches_its_own_gaps_then_copies_the_servers_files(tmp_path, demo_only):
    m, calls = manager(tmp_path, local_fill=lambda: "Gaps refetched: NQ 1 filled.", md_ready=lambda: False)
    m.start()
    st = wait_final(m)
    assert st["status"] == "done" and st["note"] == "Gaps refetched: NQ 1 filled."
    assert calls == [[str(tmp_path / "deploy/linux/tickpull.sh")]]                 # never homebase.ticks here
    assert [x["state"] for x in st["steps"]] == ["done", "done"]


def test_a_failed_refetch_is_the_runs_error_and_nothing_is_copied(tmp_path, demo_only):
    def boom():
        raise RuntimeError("websocket not connected")
    m, calls = manager(tmp_path, local_fill=boom)
    m.start()
    st = wait_final(m)
    assert st["status"] == "error" and "websocket not connected" in st["note"] and calls == []


def test_a_demo_only_machine_without_a_refetch_still_refuses(tmp_path, demo_only):
    m, calls = manager(tmp_path)
    with pytest.raises(ValueError, match="demo login only"):
        m.start()
    assert calls == []


def test_replace_gap_swaps_one_marker_and_leaves_a_moved_one_alone(tmp_path):
    rec = LiveRecorder(tmp_path)
    rec.mark_gap("NQ", D, "NQZ6", 1, 5)
    rec.mark_gap("NQ", D, "NQZ6", 10, 20)
    rec.replace_gap("NQ", D, "NQZ6", [10, 20], [[10, 12]])
    rec.replace_gap("NQ", D, "NQZ6", [1, 5], [])
    rec.replace_gap("NQ", D, "NQZ6", [7, 8], [])                       # not there: nothing changes
    gp = tmp_path / "NQ" / str(D.year) / f"{D.isoformat()}_NQZ6.live.gaps"
    assert json.loads(gp.read_text()) == [[10, 12]]


class IdleFeed:
    def __init__(self, roots, on_ticks, on_subscribed=None):
        self.ws = None

    def count_request(self):
        pass

    def budget_used(self):
        return 0

    async def run(self):
        while True:
            await asyncio.sleep(0.01)

    def stop(self):
        pass

    def status(self):
        return {"mode": "live", "connected": True, "error": None, "roots": {}, "budget_hour": 0, "reconnects": 0}


class Done:
    def wait(self):
        return 0


def test_a_click_refetches_the_posted_gaps_lands_them_and_unmarks_them(tmp_path, demo_only, monkeypatch):
    """A gap Tradovate has posted is asked again, its ticks land in the recording and its marker goes; one inside the
    last ~45 min (not posted in full yet) stays for a later click."""
    base = tmp_path / "ticks"
    rec = base / "NQ" / str(D.year) / f"{D.isoformat()}_NQZ6.live.csv.gz"
    write_gz(rec, rows(session_ms(D, 9, 59), [100.0], first_id=1) + rows(session_ms(D, 10, 6), [101.0], first_id=50))
    old, recent = [session_ms(D, 10, 0), session_ms(D, 10, 5)], [session_ms(D, 11, 30), session_ms(D, 11, 31)]
    gp = rec.parent / f"{D.isoformat()}_NQZ6.live.gaps"
    gp.write_text(json.dumps([old, recent]))
    asked: list = []

    async def fake_refill(ws, contract, frm, to, *, max_pages, sleep=None, on_request=None):
        asked.append((contract, frm, to))
        return rows(session_ms(D, 10, 1), [100.5, 100.75], first_id=10), frm        # the whole stretch

    monkeypatch.setattr("homebase.charts.server.refill", fake_refill)
    pulled: list = []

    def popen(argv, **kw):
        pulled.append(argv)
        return Done()

    app = create_app(roots=["NQ"], base=base, feed_factory=IdleFeed, now_ms=lambda: session_ms(D, 12, 0),
                     state=tmp_path / "state", refresh_kw={"popen": popen})
    with TestClient(app, base_url="http://127.0.0.1:8852") as c:
        deadline = time.time() + 10
        st = c.get("/api/refresh").json()
        while st.get("status") != "done" and time.time() < deadline:
            if st.get("status") in ("idle", "error"):           # the repair loop (and its event loop) may not be up yet
                c.post("/api/refresh")
            time.sleep(0.05)
            st = c.get("/api/refresh").json()
    assert st["status"] == "done", st
    assert st["note"] == "Gaps refetched: NQ 1 filled, 1 left."
    assert asked == [("NQZ6", old[0] - 1, old[1] + 1)]                              # only the posted gap
    assert len(pulled) == 1 and pulled[0][-1].endswith("tickpull.sh")
    assert json.loads(gp.read_text()) == [recent]
    header, recs = read_table(rec)
    assert {int(r[header.index("id")]) for r in recs} >= {1, 10, 11, 50}      # flushed by the reseed


def test_ids_unbroken_across_a_gap_means_every_trade_is_held():
    from homebase.core.tick import Tick
    t = [Tick(1000, 1.0, 1, 1, 7), Tick(5000, 1.0, 1, 1, 8), Tick(9000, 1.0, 1, 1, 9)]
    assert S.ids_unbroken(t, 2000, 8000)                       # 7 before, 8 inside, 9 after
    assert not S.ids_unbroken(t[:1] + t[2:], 2000, 8000)       # 8 missing
    assert not S.ids_unbroken(t, 500, 8000)                    # nothing before the gap to vouch from
    assert not S.ids_unbroken(t, 2000, 9500)                   # nothing after it


@pytest.mark.parametrize("now_ms", [0, 150 * 60_000])          # 18:30 ET: the session closed, the next began
def test_a_click_clears_a_marker_whose_trades_are_all_held_with_tradovate_down(tmp_path, demo_only, monkeypatch, now_ms):
    """GC 2026-10-30: the server's copied file held every trade of each marked gap, Tradovate's demo socket refused
    (HTTP 502), and a click filled nothing. Unbroken ids across the gap clear its marker with no fetch."""
    base = tmp_path / "ticks"
    rec = base / "NQ" / str(D.year) / f"{D.isoformat()}_NQZ6.live.csv.gz"
    write_gz(rec, rows(session_ms(D, 9, 59), [100.0], first_id=1) + rows(session_ms(D, 10, 2), [100.5], first_id=2)
             + rows(session_ms(D, 10, 6), [101.0], first_id=3))
    gp = rec.parent / f"{D.isoformat()}_NQZ6.live.gaps"
    gp.write_text(json.dumps([[session_ms(D, 10, 0), session_ms(D, 10, 5)]]))

    async def down(*a, **kw):
        raise RuntimeError("websocket not connected")

    monkeypatch.setattr("homebase.charts.server.refill", down)
    app = create_app(roots=["NQ"], base=base, feed_factory=IdleFeed,
                     state=tmp_path / "state", refresh_kw={"popen": lambda argv, **kw: Done()}, now_ms=lambda: session_ms(D, 16, 0) + now_ms)
    with TestClient(app, base_url="http://127.0.0.1:8852") as c:
        deadline = time.time() + 10
        st = c.get("/api/refresh").json()
        while st.get("status") != "done" and time.time() < deadline:
            if st.get("status") in ("idle", "error"):
                c.post("/api/refresh")
            time.sleep(0.05)
            st = c.get("/api/refresh").json()
    assert st["note"] == "Gaps refetched: NQ 1 filled.", st
    assert json.loads(gp.read_text()) == []
