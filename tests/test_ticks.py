"""Tick archive: session maths, backwards paging, dedupe, files. No network."""
from __future__ import annotations

import asyncio
import csv
import datetime as dt
import gzip
import json

from homebase import ticks as T
from homebase.symbols import front_month

ET = T.ET


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def test_session_bounds_and_completion():
    start, end = T.session_bounds(dt.date(2026, 9, 21))          # Monday
    assert start == dt.datetime(2026, 9, 20, 18, 0, tzinfo=ET)   # Sunday 18:00
    assert end == dt.datetime(2026, 9, 21, 17, 0, tzinfo=ET)
    assert not T.session_complete(dt.date(2026, 9, 21), dt.datetime(2026, 9, 21, 17, 2, tzinfo=ET))
    assert T.session_complete(dt.date(2026, 9, 21), dt.datetime(2026, 9, 21, 17, 6, tzinfo=ET))
    assert not T.is_session_day(dt.date(2026, 9, 20))            # Sunday


def test_sessions_to_record_skips_weekend_and_todays_open_session():
    now = dt.datetime(2026, 9, 22, 10, 0, tzinfo=ET)             # Tuesday morning
    assert T.sessions_to_record(now) == [dt.date(2026, 9, 21)]   # 19/20 = weekend
    now = dt.datetime(2026, 9, 21, 6, 50, tzinfo=ET)             # Monday morning
    assert T.sessions_to_record(now) == [dt.date(2026, 9, 18)]   # catches Friday
    now = dt.datetime(2026, 9, 22, 17, 10, tzinfo=ET)            # after today's close
    assert T.sessions_to_record(now)[-1] == dt.date(2026, 9, 22)


def test_metal_front_months_by_cycle():
    assert front_month("GC", dt.date(2026, 9, 22)) == "GCZ6"     # Oct is thin: Dec
    assert front_month("GC", dt.date(2026, 11, 25)) == "GCG7"    # rolled to Feb
    assert front_month("SI", dt.date(2026, 9, 22)) == "SIZ6"
    assert front_month("SI", dt.date(2026, 11, 20)) == "SIZ6"
    assert front_month("SI", dt.date(2026, 11, 24)) == "SIH7"
    assert front_month("RTY", dt.date(2026, 9, 22)) == "RTYZ6"
    assert front_month("ES", dt.date(2026, 12, 14)) == "ESH7"
    # verified by volume 2026-09-22: CLX6 307k vs CLV6 11k; NGX6 103k vs
    # NGV6 93k (mid-roll); ZNZ6 2.3M; HGZ6 37k
    assert front_month("CL", dt.date(2026, 9, 22)) == "CLX6"
    assert front_month("CL", dt.date(2026, 9, 10)) == "CLV6"
    assert front_month("CL", dt.date(2026, 12, 20)) == "CLG7"     # Jan crude gone mid-Dec
    assert front_month("NG", dt.date(2026, 9, 22)) == "NGX6"
    assert front_month("NG", dt.date(2026, 9, 10)) == "NGV6"
    assert front_month("ZN", dt.date(2026, 9, 22)) == "ZNZ6"
    assert front_month("ZN", dt.date(2026, 8, 20)) == "ZNU6"
    assert front_month("ZN", dt.date(2026, 11, 24)) == "ZNH7"
    assert front_month("HG", dt.date(2026, 9, 22)) == "HGZ6"
    assert front_month("HG", dt.date(2026, 11, 24)) == "HGH7"


def test_unpack_prices_from_offsets():
    rows = T._unpack({"bp": 123056, "bt": 1_000_000, "ts": 0.25,
                      "tks": [{"t": 5, "p": 2, "s": 3, "b": 1, "a": 2, "bs": 10, "as": 4, "id": 9}]})
    assert rows == [{"ts_ms": 1_000_005, "price": 30764.5, "size": 3, "bid": 30764.25,
                     "ask": 30764.5, "bid_size": 10, "ask_size": 4, "id": 9}]


def _fake_pager(all_rows, page=5):
    """Serves the `page` latest rows at or before before_ms — like the feed."""
    async def pager(ws, contract, before_ms, n=T.PAGE, timeout_s=0, ticket=None):
        cand = [r for r in all_rows if r["ts_ms"] <= before_ms]
        return cand[-page:]
    return pager


class NoWait:
    """Replace the recorder's sleeps; record what it wanted to wait."""

    def __init__(self, monkeypatch):
        self.waits = []

        async def fake(s):
            self.waits.append(round(s, 1))
        monkeypatch.setattr(T, "sleep", fake)
        monkeypatch.setattr(T, "deadline_passed", lambda now=None: False)


def test_fetch_session_pages_back_to_the_open_and_dedupes(tmp_path, monkeypatch):
    NoWait(monkeypatch)
    start = dt.datetime(2026, 9, 21, 18, 0, tzinfo=ET)
    end = dt.datetime(2026, 9, 22, 17, 0, tzinfo=ET)
    s, e = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    # 23 ticks: one before the open, two sharing a millisecond, one after the close
    tss = [s - 1000] + [s + i * 3_600_000 for i in range(20)] + [s + 5 * 3_600_000] + [e + 500]
    rows = [{"ts_ms": t, "price": 1.0, "size": 1, "bid": 0.75, "ask": 1.0,
             "bid_size": 1, "ask_size": 1, "id": i} for i, t in enumerate(tss)]
    rows.sort(key=lambda r: (r["ts_ms"], r["id"]))
    got, stats = run(T.fetch_session(None, "NQZ6", start, end, page_fn=_fake_pager(rows)))
    ids = [r["id"] for r in got]
    assert len(ids) == len(set(ids)) == 21                       # inside the session only
    assert got[0]["ts_ms"] >= s and got[-1]["ts_ms"] <= e
    assert stats["complete"] and stats["pages"] >= 5


def test_fetch_session_marks_partial_when_the_buffer_runs_dry(monkeypatch):
    NoWait(monkeypatch)
    start = dt.datetime(2026, 9, 21, 18, 0, tzinfo=ET)
    end = dt.datetime(2026, 9, 22, 17, 0, tzinfo=ET)
    e = int(end.timestamp() * 1000)
    rows = [{"ts_ms": e - i * 60_000, "price": 1.0, "size": 1, "bid": 0.75, "ask": 1.0,
             "bid_size": 1, "ask_size": 1, "id": i} for i in range(12)]   # last 12 min only
    rows.sort(key=lambda r: r["ts_ms"])
    got, stats = run(T.fetch_session(None, "NQZ6", start, end, page_fn=_fake_pager(rows)))
    assert len(got) == 12 and not stats["complete"]


def test_record_writes_file_and_manifest_then_skips(tmp_path, monkeypatch):
    NoWait(monkeypatch)
    start = dt.datetime(2026, 9, 21, 18, 0, tzinfo=ET)
    s = int(start.timestamp() * 1000)
    rows = [{"ts_ms": s + i * 1000, "price": 30764.0 + i * 0.25, "size": 2,
             "bid": 30763.75 + i * 0.25, "ask": 30764.0 + i * 0.25,
             "bid_size": 5, "ask_size": 3, "id": i} for i in range(50)]
    calls = {"n": 0}
    orig = T.fetch_page

    async def pager(ws, contract, before_ms, n=T.PAGE, timeout_s=0, ticket=None):
        calls["n"] += 1
        return await _fake_pager(rows, page=20)(ws, contract, before_ms)

    T.fetch_page = pager
    try:
        out = run(T.record(roots=("NQ",), dates=[dt.date(2026, 9, 22)],
                           base=tmp_path, ws=object()))
        assert len(out) == 1 and out[0]["ticks"] == 50 and out[0]["contract"] == "NQZ6"
        p = tmp_path / "NQ" / "2026" / "2026-09-22_NQZ6.csv.gz"
        assert p.exists() and json.loads(p.with_suffix("").with_suffix(".json").read_text())["ticks"] == 50
        with gzip.open(p, "rt") as f:
            data = list(csv.DictReader(f))
        assert len(data) == 50 and data[0]["price"] == "30764.0" and data[-1]["id"] == "49"
        assert list(data[0].keys()) == list(T.FIELDS)
        n = calls["n"]
        assert run(T.record(roots=("NQ",), dates=[dt.date(2026, 9, 22)],
                            base=tmp_path, ws=object())) == []
        assert calls["n"] == n                                   # nothing refetched
    finally:
        T.fetch_page = orig


def test_pages_are_paced_to_the_hourly_limit(monkeypatch):
    nw = NoWait(monkeypatch)
    start = dt.datetime(2026, 9, 21, 18, 0, tzinfo=ET)
    end = dt.datetime(2026, 9, 22, 17, 0, tzinfo=ET)
    s = int(start.timestamp() * 1000)
    rows = [{"ts_ms": s + i * 60_000, "price": 1.0, "size": 1, "bid": 0.75, "ask": 1.0,
             "bid_size": 1, "ask_size": 1, "id": i} for i in range(40)]
    got, stats = run(T.fetch_session(None, "NQZ6", start, end, page_fn=_fake_pager(rows, page=10)))
    assert len(got) == 40 and stats["pages"] >= 4
    assert len(nw.waits) >= stats["pages"] - 1                   # a wait between pages
    assert all(w >= T.PAGE_INTERVAL_S - 0.2 for w in nw.waits)   # each about 21 s


def test_penalty_is_honored_and_resent_with_its_ticket(monkeypatch):
    nw = NoWait(monkeypatch)
    start = dt.datetime(2026, 9, 21, 18, 0, tzinfo=ET)
    end = dt.datetime(2026, 9, 22, 17, 0, tzinfo=ET)
    s = int(start.timestamp() * 1000)
    rows = [{"ts_ms": s + i * 60_000, "price": 1.0, "size": 1, "bid": 0.75, "ask": 1.0,
             "bid_size": 1, "ask_size": 1, "id": i} for i in range(6)]
    seen = []

    async def pager(ws, contract, before_ms, n=T.PAGE, timeout_s=0, ticket=None):
        seen.append(ticket)
        if ticket is None and len(seen) == 1:
            raise T.Penalty({"p-ticket": "TKT", "p-time": 1,
                             "p-message": "Rate limit exceeded: more than 180 requests per hour"})
        return await _fake_pager(rows, page=10)(ws, contract, before_ms)

    got, stats = run(T.fetch_session(None, "NQZ6", start, end, page_fn=pager))
    assert len(got) == 6
    assert seen[:2] == [None, "TKT"] and 2.0 in nw.waits         # waited p-time + 1, resent


def test_deadline_stops_a_fetch_before_the_open(monkeypatch):
    real = T.deadline_passed
    assert real(dt.datetime(2026, 9, 22, 8, 30, tzinfo=ET))               # trading day
    assert not real(dt.datetime(2026, 9, 22, 17, 30, tzinfo=ET))          # after the close
    assert not real(dt.datetime(2026, 9, 22, 5, 45, tzinfo=ET))           # early catch-up
    assert not real(dt.datetime(2026, 9, 20, 9, 0, tzinfo=ET))            # Sunday
    monkeypatch.setattr(T, "deadline_passed", lambda now=None: True)
    start = dt.datetime(2026, 9, 21, 18, 0, tzinfo=ET)
    end = dt.datetime(2026, 9, 22, 17, 0, tzinfo=ET)
    got, stats = run(T.fetch_session(None, "NQZ6", start, end, page_fn=_fake_pager([])))
    assert got == [] and stats["pages"] == 0


def test_recorder_replaces_a_massive_file_but_keeps_its_own(tmp_path, monkeypatch):
    NoWait(monkeypatch)
    start = dt.datetime(2026, 9, 21, 18, 0, tzinfo=ET)
    s = int(start.timestamp() * 1000)
    rows = [{"ts_ms": s + i * 1000, "price": 1.0, "size": 1, "bid": 0.75, "ask": 1.0,
             "bid_size": 1, "ask_size": 1, "id": i} for i in range(20)]

    async def pager(ws, contract, before_ms, n=T.PAGE, timeout_s=0, ticket=None):
        return await _fake_pager(rows, page=50)(ws, contract, before_ms)

    monkeypatch.setattr(T, "fetch_page", pager)
    p = T.archive_path("NQ", dt.date(2026, 9, 22), "NQZ6", tmp_path)
    p.parent.mkdir(parents=True)
    p.write_bytes(b"massive")
    p.with_suffix("").with_suffix(".json").write_text(json.dumps({"source": "massive"}))
    out = run(T.record(roots=("NQ",), dates=[dt.date(2026, 9, 22)], base=tmp_path, ws=object()))
    assert len(out) == 1 and out[0]["ticks"] == 20            # replaced
    assert run(T.record(roots=("NQ",), dates=[dt.date(2026, 9, 22)], base=tmp_path,
                        ws=object())) == []                     # ours now: kept


def test_session_fetch_survives_a_dead_socket(monkeypatch):
    """A run of hours outlives its token: the socket closes and a page
    raises 'websocket not connected'. The connection holder must rebuild
    the socket and the fetch must carry on from the same page."""
    NoWait(monkeypatch)
    start = dt.datetime(2026, 9, 21, 18, 0, tzinfo=ET)
    end = dt.datetime(2026, 9, 22, 17, 0, tzinfo=ET)
    s = int(start.timestamp() * 1000)
    rows = [{"ts_ms": s + i * 60_000, "price": 1.0, "size": 1, "bid": 0.75, "ask": 1.0,
             "bid_size": 1, "ask_size": 1, "id": i} for i in range(30)]

    class Sock:
        def __init__(self, alive=True):
            self.connected = alive

        async def close(self):
            self.connected = False

    built = []

    async def fake_connect():
        built.append(Sock())
        return built[-1]

    monkeypatch.setattr(T, "connect_md", fake_connect)
    conn = T.MDConn(Sock())
    calls = {"n": 0}

    async def pager(ws, contract, before_ms, n=T.PAGE, timeout_s=0, ticket=None):
        calls["n"] += 1
        if calls["n"] == 2:                       # the token expired mid-run
            ws.connected = False
            raise RuntimeError("websocket not connected")
        return await _fake_pager(rows, page=10)(ws, contract, before_ms)

    got, stats = run(T.fetch_session(conn, "NQZ6", start, end, page_fn=pager))
    assert len(got) == 30 and conn.reconnects == 1 and len(built) == 1
