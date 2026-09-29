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


def test_crypto_rolls_two_days_before_the_last_friday_expiry():
    # BTC/MBT are monthly and expire on the contract month's last Friday; the
    # volume moves 1-3 days before (59 BTC rolls 2021-26, median 1)
    assert front_month("BTC", dt.date(2026, 9, 26)) == "BTCV6"     # Sep expired Fri 25th
    assert front_month("BTC", dt.date(2026, 10, 27)) == "BTCV6"
    assert front_month("BTC", dt.date(2026, 10, 28)) == "BTCX6"    # Oct's last Friday is the 30th
    assert front_month("BTC", dt.date(2026, 12, 22)) == "BTCZ6"
    assert front_month("BTC", dt.date(2026, 12, 23)) == "BTCF7"    # year wrap
    assert front_month("MBT", dt.date(2026, 9, 26)) == "MBTV6"


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
    """Replace the recorder's sleeps; record what it wanted to wait. The job's
    clock (T.now_et) starts at `now` and moves only by those waits."""

    def __init__(self, monkeypatch, now=dt.datetime(2026, 9, 22, 17, 30, tzinfo=ET)):
        self.waits = []
        self.now = now

        async def fake(s):
            self.waits.append(round(s, 1))
            self.now += dt.timedelta(seconds=s)
        monkeypatch.setattr(T, "sleep", fake)
        monkeypatch.setattr(T, "deadline_passed", lambda now=None: False)
        monkeypatch.setattr(T, "now_et", lambda: self.now)


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


def _massive_file(p, ts_ms_list, first_seq=900_000):
    """A Massive backfill file as research/massive_ticks.py writes it: no
    bid/ask, the exchange sequence number as `id`, the ns stamp in ts_ns."""
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(T.FIELDS + ("ts_ns",))
        for i, t in enumerate(ts_ms_list):
            w.writerow((t, "1", 1, "", "", "", "", first_seq + i, t * 1_000_000 + 123))
    p.with_suffix("").with_suffix(".json").write_text(json.dumps(
        {"source": "massive", "complete": True, "ticks": len(ts_ms_list), "bid_ask": False}))


def test_the_brokers_ticks_supersede_a_massive_file_where_they_cover_it(tmp_path, monkeypatch):
    NoWait(monkeypatch)
    start = dt.datetime(2026, 9, 21, 18, 0, tzinfo=ET)
    s = int(start.timestamp() * 1000)
    rows = [{"ts_ms": s + i * 1000, "price": 1.0, "size": 1, "bid": 0.75, "ask": 1.0,
             "bid_size": 1, "ask_size": 1, "id": i} for i in range(20)]

    async def pager(ws, contract, before_ms, n=T.PAGE, timeout_s=0, ticket=None):
        return await _fake_pager(rows, page=50)(ws, contract, before_ms)

    monkeypatch.setattr(T, "fetch_page", pager)
    p = T.archive_path("NQ", dt.date(2026, 9, 22), "NQZ6", tmp_path)
    _massive_file(p, [r["ts_ms"] for r in rows])                # the same 20 trades, from Massive
    out = run(T.record(roots=("NQ",), dates=[dt.date(2026, 9, 22)], base=tmp_path, ws=object()))
    assert len(out) == 1 and out[0]["ticks"] == 20            # the broker's rows, once
    assert out[0]["bid_ask"] and out[0]["source"] == "desk" and out[0]["massive_rows"] == 0
    assert run(T.record(roots=("NQ",), dates=[dt.date(2026, 9, 22)], base=tmp_path,
                        ws=object())) == []                     # fetched: nothing asked again


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

    async def fake_connect(**kw):
        assert kw == {"strict": True}              # the nightly never falls back to the demo login
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


def test_a_partial_capture_never_shortens_a_full_backfill_file(tmp_path, monkeypatch):
    """The broker still had only the session's last 12 minutes: the Massive
    file's other trades all stay, the broker's rows take over where they are."""
    NoWait(monkeypatch)
    start, end = T.session_bounds(dt.date(2026, 9, 22))
    s, e = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    rows = [{"ts_ms": e - i * 60_000, "price": 1.0, "size": 1, "bid": 0.75, "ask": 1.0,
             "bid_size": 1, "ask_size": 1, "id": 5000 + i} for i in range(12)]   # last 12 min only
    rows.sort(key=lambda r: r["ts_ms"])

    async def pager(ws, contract, before_ms, n=T.PAGE, timeout_s=0, ticket=None):
        return await _fake_pager(rows, page=50)(ws, contract, before_ms)

    monkeypatch.setattr(T, "fetch_page", pager)
    p = T.archive_path("NQ", dt.date(2026, 9, 22), "NQZ6", tmp_path)
    massive = list(range(s, e + 1, 60_000))                     # a trade a minute, the whole session
    _massive_file(p, massive)
    out = run(T.record(roots=("NQ",), dates=[dt.date(2026, 9, 22)], base=tmp_path, ws=object()))
    with gzip.open(p, "rt") as f:
        got = list(csv.DictReader(f))
    broker = [r for r in got if not r["ts_ns"]]
    kept = [r for r in got if r["ts_ns"]]
    assert [int(r["id"]) for r in broker] == [5000 + i for i in range(11, -1, -1)]
    assert {int(r["ts_ms"]) for r in kept} == {t for t in massive if t < rows[0]["ts_ms"] - 2000}
    assert len(got) == out[0]["ticks"] == len(massive)          # every trade once, none lost
    assert not out[0]["bid_ask"] and out[0]["massive_rows"] == len(kept)


# ------------------------------------------------ the broker's history window (root cause of the
# 18:00-20:00 ET hole: T's docstring)
UTC = dt.timezone.utc


class HistoryWindow:
    """A fake md history with the broker's window: a request is served only
    the ticks stamped at or after 00:00 UTC of the PREVIOUS UTC day by the
    job's clock -- at most `page` of them, the latest at or before before_ms."""

    def __init__(self, nw, ticks, page):
        self.nw, self.ticks, self.page, self.asked = nw, ticks, page, []

    async def pager(self, ws, contract, before_ms, n=T.PAGE, timeout_s=0, ticket=None):
        self.asked.append((contract, before_ms))
        today = self.nw.now.astimezone(UTC).date()
        edge = dt.datetime.combine(today - dt.timedelta(days=1), dt.time(0), UTC)
        edge_ms = int(edge.timestamp() * 1000)
        return [r for r in self.ticks[contract] if edge_ms <= r["ts_ms"] <= before_ms][-self.page:]


def _minute_ticks(date, first_id=1):
    """One tick a minute through session `date` (18:00 ET the day before -> 17:00 ET)."""
    start, end = T.session_bounds(date)
    s, e = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    return [{"ts_ms": t, "price": 1.0, "size": 1, "bid": 0.75, "ask": 1.0, "bid_size": 1,
             "ask_size": 1, "id": first_id + i} for i, t in enumerate(range(s, e, 60_000))]


def _et(ms):
    return dt.datetime.fromtimestamp(ms / 1000, ET)


def test_the_fake_window_reproduces_the_hole_the_old_order_left(monkeypatch):
    """The archive's failure, replayed: paged back from the close one root
    after another from 17:20 ET, the later roots reach their 18:00-20:00 ET
    after 20:00 ET (00:00 UTC), when the broker has already dropped them --
    and the capture starts at exactly 20:00 ET, like every partial file."""
    d = dt.date(2026, 9, 24)
    nw = NoWait(monkeypatch, now=dt.datetime(2026, 9, 24, 17, 20, tzinfo=ET))
    broker = HistoryWindow(nw, {c: _minute_ticks(d) for c in ("NQZ6", "ESZ6", "YMZ6")}, page=10)
    start, end = T.session_bounds(d)
    firsts = []
    for c in ("NQZ6", "ESZ6", "YMZ6"):
        rows, _ = run(T.fetch_session(None, c, start, end, page_fn=broker.pager))
        firsts.append(_et(rows[0]["ts_ms"]).strftime("%H:%M"))
    assert firsts == ["18:00", "20:00", "20:00"]


def test_every_roots_first_hours_are_fetched_before_the_broker_drops_them(tmp_path, monkeypatch):
    d = dt.date(2026, 9, 24)
    nw = NoWait(monkeypatch, now=dt.datetime(2026, 9, 24, 17, 20, tzinfo=ET))
    broker = HistoryWindow(nw, {c: _minute_ticks(d) for c in ("NQZ6", "ESZ6", "YMZ6")}, page=10)
    monkeypatch.setattr(T, "fetch_page", broker.pager)
    out = run(T.record(roots=("NQ", "ES", "YM"), dates=[d], base=tmp_path, ws=object()))
    assert sorted(m["contract"] for m in out) == ["ESZ6", "NQZ6", "YMZ6"]
    for m in out:
        assert m["ticks"] == 23 * 60 and m["complete"]
        assert m["first_tick_utc"] == "2026-09-23T22:00:00+00:00"          # the 18:00 ET open
    assert nw.now > dt.datetime(2026, 9, 24, 20, 0, tzinfo=ET)            # the run went past 00:00 UTC
    midnight = int(dt.datetime(2026, 9, 24, 0, 0, tzinfo=UTC).timestamp() * 1000)
    first_tail = next(i for i, (c, b) in enumerate(broker.asked) if b > midnight)
    assert {c for c, _ in broker.asked[:first_tail]} == {"NQZ6", "ESZ6", "YMZ6"}   # heads first


def test_the_plan_orders_segments_by_when_they_leave_the_broker(tmp_path):
    now = dt.datetime(2026, 9, 24, 17, 20, tzinfo=ET)              # Thursday, after the close
    sessions, jobs = T.plan(("NQ", "ES"), [dt.date(2026, 9, 23), dt.date(2026, 9, 24)], tmp_path, now)
    got = [(root, date.day, s.astimezone(ET).strftime("%d %H:%M"), e.astimezone(ET).strftime("%d %H:%M"))
           for _, _, _, date, (root, _), s, e, _ in jobs]
    assert got == [
        # gone at 20:00 ET today: the 24th's first hours, then what is left of the 23rd
        ("NQ", 24, "23 18:00", "23 20:00"), ("ES", 24, "23 18:00", "23 20:00"),
        ("NQ", 23, "22 20:00", "23 17:00"), ("ES", 23, "22 20:00", "23 17:00"),
        # gone at 20:00 ET tomorrow
        ("NQ", 24, "23 20:00", "24 17:00"), ("ES", 24, "23 20:00", "24 17:00"),
    ]
    assert sum(1 for j in jobs if j[4] == ("NQ", dt.date(2026, 9, 23))) == 1   # its 18:00-20:00 ET is gone


def test_a_session_already_gone_asks_nothing_and_says_so_the_hour_it_goes(tmp_path, monkeypatch, capsys):
    nw = NoWait(monkeypatch, now=dt.datetime(2026, 9, 25, 20, 30, tzinfo=ET))   # the 24th left at 20:00
    broker = HistoryWindow(nw, {"NQZ6": _minute_ticks(dt.date(2026, 9, 24))}, page=10)
    monkeypatch.setattr(T, "fetch_page", broker.pager)
    assert run(T.record(roots=("NQ",), dates=[dt.date(2026, 9, 24)], base=tmp_path, ws=object())) == []
    assert broker.asked == [] and "needs Massive" in capsys.readouterr().out
    nw.now = dt.datetime(2026, 9, 26, 17, 20, tzinfo=ET)                          # a day later: quiet
    assert run(T.record(roots=("NQ",), dates=[dt.date(2026, 9, 24)], base=tmp_path, ws=object())) == []
    assert capsys.readouterr().out == ""


def test_a_winter_session_loses_one_hour_at_19_et(tmp_path):
    """Standard time: 00:00 UTC is 19:00 ET, so only 18:00-19:00 ET sits in the
    earlier UTC day, and it leaves the broker at 19:00 ET on the session day."""
    start, end = T.session_bounds(dt.date(2026, 12, 15))
    segs = T.utc_segments(start, end)
    assert [(s.astimezone(ET).strftime("%H:%M"), e.astimezone(ET).strftime("%H:%M")) for s, e in segs] \
        == [("18:00", "19:00"), ("19:00", "17:00")]
    assert T.history_expiry(segs[0][0]) == dt.datetime(2026, 12, 15, 19, 0, tzinfo=ET)
    assert T.history_expiry(segs[1][0]) == dt.datetime(2026, 12, 16, 19, 0, tzinfo=ET)


def test_a_segment_that_expires_mid_fetch_stops_asking(monkeypatch):
    nw = NoWait(monkeypatch, now=dt.datetime(2026, 9, 24, 19, 58, tzinfo=ET))
    d = dt.date(2026, 9, 24)
    broker = HistoryWindow(nw, {"NQZ6": _minute_ticks(d)}, page=10)
    start, _ = T.session_bounds(d)
    mid = T.utc_segments(*T.session_bounds(d))[0][1]
    rows, stats = run(T.fetch_session(None, "NQZ6", start, mid, page_fn=broker.pager,
                                      expiry=T.history_expiry(start)))
    assert stats["stop"] == "expired" and len(broker.asked) == 4     # 19:58, +36 s x 3 < 20:00
    assert 0 < len(rows) < 120


# ------------------------------------------------ merge, never replace (the nightly side)
def _write_live(p, rows):
    """The chart service's live recording: header + rows, one gzip member per flush."""
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "ab") as f:
        body = "".join(",".join("" if r[k] in (None, "") else str(r[k]) for k in T.FIELDS) + "\n"
                       for r in rows)
        f.write(gzip.compress(((",".join(T.FIELDS) + "\n") if f.tell() == 0 else "").encode()
                              + body.encode()))


def _ids(p):
    with gzip.open(p, "rt") as f:
        return [int(r["id"]) for r in csv.DictReader(f)]


def test_the_night_run_merges_the_live_recording_that_holds_the_lost_hours(tmp_path, monkeypatch):
    """The 05:30 run the morning after: the broker has only 20:00 ET on; the live
    recording has the whole session but a restart lost 11 ticks. Only those 11
    and the close are asked for; the file: both, every tick once -- and the live
    file is left as it was."""
    d = dt.date(2026, 9, 24)
    nw = NoWait(monkeypatch, now=dt.datetime(2026, 9, 25, 5, 30, tzinfo=ET))
    ticks = _minute_ticks(d)
    broker = HistoryWindow(nw, {"NQZ6": ticks}, page=100)
    monkeypatch.setattr(T, "fetch_page", broker.pager)
    path = T.archive_path("NQ", d, "NQZ6", tmp_path)
    lp = path.with_name("2026-09-24_NQZ6.live.csv.gz")
    lost = {r["id"] for r in ticks[600:611]}                 # 04:00 ET: a restart dropped 11 ticks
    _write_live(lp, [r for r in ticks if r["id"] not in lost])
    live_bytes = lp.read_bytes()
    out = run(T.record(roots=("NQ",), dates=[d], base=tmp_path, ws=object()))
    assert _ids(path) == [r["id"] for r in ticks]            # 18:00 from live, 04:00 from the broker
    assert lp.read_bytes() == live_bytes
    m = out[0]
    assert m["complete"] and m["ticks"] == len(ticks)
    assert [(x["kind"], x.get("why")) for x in m["sources"]] == [("history", "11 ticks"), ("live", None),
                                                                ("history", "the close")]
    assert len(broker.asked) == 2                            # one page each: the gap, the close


def test_a_live_recording_is_merged_even_when_nothing_is_left_to_fetch(tmp_path, monkeypatch, capsys):
    d = dt.date(2026, 9, 24)
    nw = NoWait(monkeypatch, now=dt.datetime(2026, 9, 28, 5, 30, tzinfo=ET))   # long gone from the broker
    broker = HistoryWindow(nw, {"NQZ6": []}, page=100)
    monkeypatch.setattr(T, "fetch_page", broker.pager)
    ticks = _minute_ticks(d)
    path = T.archive_path("NQ", d, "NQZ6", tmp_path)
    lp = path.with_name("2026-09-24_NQZ6.live.csv.gz")
    _write_live(lp, ticks[:100])
    cache = {}
    out = run(T.record(roots=("NQ",), base=tmp_path, ws=object(), cache=cache))
    today = int(T.session_bounds(dt.date(2026, 9, 28))[0].timestamp() * 1000)
    assert all(b >= today for c, b in broker.asked)          # only today's session was asked for
    assert len(out) == 1 and _ids(path) == [r["id"] for r in ticks[:100]]
    assert "live recording merged (100 ticks, 100 the archive lacked)" in capsys.readouterr().out
    asked = len(broker.asked)
    for _ in range(2):   # the broker's one empty reply is asked once more (review 9), then believed
        nw.now = dt.datetime(2026, 9, 28, 5, 30, tzinfo=ET)  # the same moment: nothing new has happened
        assert run(T.record(roots=("NQ",), base=tmp_path, ws=object(), cache=cache)) == []   # already in
    assert len(broker.asked) == 2 * asked
    _write_live(lp, ticks[100:130])                            # the recorder appended
    out = run(T.record(roots=("NQ",), base=tmp_path, ws=object(), cache=cache))
    assert _ids(path) == [r["id"] for r in ticks[:130]] and out[0]["ticks"] == 130


def test_the_0530_run_fills_what_the_live_recording_missed_without_merging_it_yet(tmp_path, monkeypatch):
    """05:30, today's session under way: the chart service recorded 18:00-18:04
    and stopped (the machine slept). The broker's ticks since then are fetched
    into the archive file; the live file, still being written, is merged only
    after the close -- and the evening asks for nothing it already has."""
    d = dt.date(2026, 9, 24)
    nw = NoWait(monkeypatch, now=dt.datetime(2026, 9, 24, 5, 30, tzinfo=ET))
    ticks = _minute_ticks(d)
    broker = HistoryWindow(nw, {"NQZ6": ticks}, page=100)
    monkeypatch.setattr(T, "fetch_page", broker.pager)
    path = T.archive_path("NQ", d, "NQZ6", tmp_path)
    _write_live(path.with_name("2026-09-24_NQZ6.live.csv.gz"), ticks[:5])
    out = run(T.record(roots=("NQ",), dates=[d], base=tmp_path, ws=object()))
    got = _ids(path)                     # the archive: 18:00 (the open, checked) and 18:04-05:25 fetched
    assert set(got) | {r["id"] for r in ticks[:5]} == {r["id"] for r in ticks[:686]}      # up to 05:25
    assert {x["kind"] for x in out[0]["sources"]} == {"history"} and not out[0]["complete"]
    early = len(broker.asked)
    nw.now = dt.datetime(2026, 9, 24, 17, 20, tzinfo=ET)      # after the close: the rest, and the live file
    out = run(T.record(roots=("NQ",), dates=[d], base=tmp_path, ws=object()))
    assert _ids(path) == [r["id"] for r in ticks] and out[0]["complete"]
    assert "live" in [x["kind"] for x in out[0]["sources"]]
    midnight = int(dt.datetime(2026, 9, 24, 0, 0, tzinfo=UTC).timestamp() * 1000)
    assert all(b > midnight for c, b in broker.asked[early:])   # the evening asked no 18:00-20:00 again


def test_a_fetch_cut_short_by_the_deadline_resumes_where_it_stopped(tmp_path, monkeypatch):
    d = dt.date(2026, 9, 24)
    nw = NoWait(monkeypatch, now=dt.datetime(2026, 9, 24, 17, 20, tzinfo=ET))
    ticks = _minute_ticks(d)
    broker = HistoryWindow(nw, {"NQZ6": ticks}, page=100)
    monkeypatch.setattr(T, "fetch_page", broker.pager)
    tripped = {"on": False, "armed": True}

    def deadline(now=None):             # 08:00 comes three pages into the long tail
        if tripped["armed"] and len(broker.asked) >= 6:
            tripped.update(on=True, armed=False)
        return tripped["on"]
    monkeypatch.setattr(T, "deadline_passed", deadline)
    run(T.record(roots=("NQ",), dates=[d], base=tmp_path, ws=object()))
    tripped["on"] = False               # the next evening
    path = T.archive_path("NQ", d, "NQZ6", tmp_path)
    man = json.loads(path.with_suffix("").with_suffix(".json").read_text())
    cut = man["sources"][-1]
    assert cut["stop"] == "deadline" and cut["earliest_ms"] is not None
    asked = len(broker.asked)
    run(T.record(roots=("NQ",), dates=[d], base=tmp_path, ws=object()))
    assert broker.asked[asked] == ("NQZ6", cut["earliest_ms"])   # resumed, not restarted
    assert _ids(path) == [r["id"] for r in ticks]


class ChartSocket:
    """An md socket with TradovateWS's dispatch semantics: every chart
    packet goes to every event handler, and packets for a getChart can land
    BEFORE its reply resolves. `before`/`after` are the packets delivered
    around the getChart reply; each packet is a dict of the charts array."""

    def __init__(self, reply, before=(), after=()):
        self.event_handlers, self.sent = [], []
        self.reply, self.before, self.after = reply, list(before), list(after)

    def emit(self, ch):
        for h in list(self.event_handlers):
            h({"e": "chart", "d": {"charts": [ch]}})

    async def request(self, ep, body=""):
        self.sent.append((ep, body))
        if ep == "md/cancelChart":
            return {}
        for ch in self.before:
            self.emit(ch)
        loop = asyncio.get_running_loop()
        for ch in self.after:
            loop.call_soon(self.emit, ch)
        return self.reply


def _pkt(cid, bp, ts_list, first_id):
    return {"id": cid, "bp": bp, "bt": ts_list[0], "ts": 0.25,
            "tks": [{"t": t - ts_list[0], "p": 0, "s": 1, "b": -1, "a": 0, "id": first_id + i}
                    for i, t in enumerate(ts_list)]}


def test_fetch_page_on_its_own_socket_returns_the_page_oldest_first():
    """The nightly job's case: the socket carries only this page's chart."""
    t0 = 1_790_000_000_000
    ws = ChartSocket({"historicalId": 11, "realtimeId": 11},
                     after=[_pkt(11, 80_000, [t0 + 2000, t0 + 3000], 3),
                            _pkt(11, 80_000, [t0, t0 + 1000], 1),
                            {"id": 11, "eoh": True}])
    got = asyncio.run(T.fetch_page(ws, "NQZ6", t0 + 3000, timeout_s=1))
    assert [r["id"] for r in got] == [1, 2, 3, 4] and got[0]["price"] == 20_000.0
    assert ws.sent[-1] == ("md/cancelChart", {"subscriptionId": 11})
    assert ws.event_handlers == []


def test_fetch_page_on_a_shared_socket_keeps_only_its_own_chart():
    """The chart service pages history on the md socket its live Tick
    subscriptions ride: another root's resubscribe delivers its latest trade
    and an end-of-history, and live ticks keep flowing, while this page is in
    flight. Only this getChart's ids may land in the page, and only ITS
    end-of-history may end it (a foreign one used to cut the page short and
    hand its rows to the next root's page)."""
    t0 = 1_790_000_000_000
    other = 77                                               # e.g. ES's live subscription
    ws = ChartSocket(
        {"historicalId": 11, "realtimeId": 12},
        before=[_pkt(other, 23_200, [t0 + 500], 900),        # another root's latest trade
                {"id": other, "eoh": True},                  # ... and its end-of-history
                _pkt(11, 80_000, [t0, t0 + 1000], 1)],       # ours, ahead of the reply
        after=[_pkt(other, 23_200, [t0 + 2500], 901),        # another root's live tick
               _pkt(11, 80_000, [t0 + 2000, t0 + 3000], 3),  # the rest of ours
               _pkt(12, 80_000, [t0 + 4000], 5),             # ours, on the realtime id
               {"id": 11, "eoh": True}])
    got = asyncio.run(T.fetch_page(ws, "NQZ6", t0 + 3000, timeout_s=1))
    assert [r["id"] for r in got] == [1, 2, 3, 4, 5]         # no foreign row, none missing
    assert {r["price"] for r in got} == {20_000.0}
    assert ws.sent[-1] == ("md/cancelChart", {"subscriptionId": 12})


# ------------------------------------------------------------------ all 15 archive roots (item D)
def test_the_archive_records_all_fifteen_roots_in_priority_order():
    assert T.ROOTS == ("NQ", "ES", "YM", "RTY", "GC", "SI", "CL", "ZN", "NG", "HG",
                       "6E", "6J", "6B", "BTC", "MBT")


def test_fx_is_quarterly_and_crypto_monthly():
    # 6E/6J/6B: H M U Z, rolled a week before the 3rd Friday (FX expires the Monday
    # before the 3rd Wednesday, so never a dying contract). Checked 2026-09-28 against
    # the Massive files' tick counts 2025-26: 6E and 6J agree every session; 6B's
    # volume moved one day earlier twice (2026-06-11, 09-10).
    for r in ("6E", "6J", "6B"):
        assert front_month(r, dt.date(2026, 9, 10)) == f"{r}U6"
        assert front_month(r, dt.date(2026, 9, 11)) == f"{r}Z6"
        assert front_month(r, dt.date(2026, 12, 11)) == f"{r}H7"
    # BTC/MBT: every month, rolled two days before the last-Friday expiry
    for r in ("BTC", "MBT"):
        assert front_month(r, dt.date(2026, 10, 27)) == f"{r}V6"
        assert front_month(r, dt.date(2026, 10, 28)) == f"{r}X6"


def test_crypto_sessions_run_18_to_18_every_day_like_the_live_recorder():
    from homebase.charts.session import session_date, session_range_ms
    sat = dt.date(2026, 9, 26)
    start, end = T.session_bounds(sat, "BTC")
    assert (start, end) == (dt.datetime(2026, 9, 25, 18, 0, tzinfo=ET), dt.datetime(2026, 9, 26, 18, 0, tzinfo=ET))
    assert session_range_ms(sat, "BTC") == (int(start.timestamp() * 1000), int(end.timestamp() * 1000))
    assert session_date(int(end.timestamp() * 1000) - 1, "BTC") == sat
    assert T.is_session_day(sat, "MBT") and not T.is_session_day(sat, "NQ")
    assert T.session_bounds(dt.date(2026, 9, 25), "NQ")[1].hour == 17


def test_a_weekend_run_fetches_crypto_only(tmp_path):
    now = dt.datetime(2026, 9, 27, 5, 30, tzinfo=ET)                   # Sunday morning
    _, jobs = T.plan(T.ROOTS, T.candidate_dates(now), tmp_path, now)
    got = sorted({(key[0], key[1].isoformat()) for *_, key, s, e, r in jobs})
    # Friday's session ended at 18:00 Fri, Saturday's at 18:00 Sat; Sunday's first
    # hours (18:00-20:00 Sat) are over: all still in the broker's two UTC days
    assert got == [("BTC", "2026-09-26"), ("BTC", "2026-09-27"), ("MBT", "2026-09-26"), ("MBT", "2026-09-27")]


def test_a_weekday_evening_fetches_every_roots_first_hours_first(tmp_path):
    now = dt.datetime(2026, 9, 29, 17, 20, tzinfo=ET)
    _, jobs = T.plan(T.ROOTS, [dt.date(2026, 9, 29)], tmp_path, now)
    heads = [key[0] for *_, key, s, e, r in jobs[:15]]
    assert heads == list(T.ROOTS)                                     # every root's 18:00-20:00 ET first
    assert all(s == T.session_bounds(dt.date(2026, 9, 29), key[0])[0] for *_, key, s, e, r in jobs[:15])
    tails = [key[0] for *_, key, s, e, r in jobs[15:]]
    assert tails == list(T.ROOTS)          # then the rest -- BTC/MBT's up to now, their session runs to 18:00
    btc = [e for *_, key, s, e, r in jobs if key[0] == "BTC"][-1]
    assert btc.astimezone(ET).strftime("%H:%M") == "17:15"


def test_6j_prices_keep_their_seventh_decimal():
    rows = T._unpack({"bp": 13785, "bt": 0, "ts": 5e-07,
                      "tks": [{"t": 0, "p": 0, "s": 1, "b": -1, "a": 0, "id": 1},
                              {"t": 1, "p": 1, "s": 2, "b": 0, "a": 1, "id": 2}]})
    assert [r["price"] for r in rows] == [0.0068925, 0.006893]
    assert (rows[0]["bid"], rows[0]["ask"]) == (0.006892, 0.0068925)
    assert T.price_decimals(0.25) == T.price_decimals(0.015625) == 6 and T.price_decimals(5e-07) == 7


def test_the_night_job_never_falls_back_to_the_login_the_930_bot_rides(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import pytest
    cfg = SimpleNamespace(accounts={"demo1": SimpleNamespace(live=False),
                                    "live1": SimpleNamespace(live=True)})
    monkeypatch.setattr(T.config_mod, "load", lambda: cfg)
    monkeypatch.setattr(T, "state_dir", lambda: tmp_path)
    exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat()
    (tmp_path / "demo1.tokens.json").write_text(json.dumps({"md_access_token": "tok-demo", "expiration_time": exp}))
    assert T.md_token() == ("tok-demo", "demo")          # the chart service may still fall back
    with pytest.raises(RuntimeError, match="never pages on the other login"):
        T.md_token(strict=True)
    (tmp_path / "live1.tokens.json").write_text(json.dumps({"md_access_token": "tok-live", "expiration_time": exp}))
    assert T.md_token(strict=True) == ("tok-live", "live")


def test_a_socket_that_keeps_dying_is_rebuilt_three_times_a_run_then_given_up(monkeypatch):
    """Review 8: 'websocket not connected' was retried every 2 s without end."""
    nw = NoWait(monkeypatch, now=dt.datetime(2026, 9, 24, 21, 0, tzinfo=ET))

    class Sock:
        connected = True

        async def close(self):
            pass

    async def fake_connect(**kw):
        return Sock()
    monkeypatch.setattr(T, "connect_md", fake_connect)
    calls = []

    async def dead(ws, contract, before_ms, n=T.PAGE, timeout_s=0, ticket=None):
        calls.append(before_ms)
        raise RuntimeError("websocket not connected")
    start, end = T.session_bounds(dt.date(2026, 9, 24))
    conn = T.MDConn(Sock())
    import pytest
    with pytest.raises(RuntimeError, match="not connected"):
        run(T.fetch_session(conn, "NQZ6", start, end, page_fn=dead))
    assert len(calls) == T.DROPS_MAX + 1 and conn.dropped == T.DROPS_MAX
    assert [w for w in nw.waits if w in (5.0, 10.0, 20.0)] == [5.0, 10.0, 20.0]
