"""The tick stream the Lab strategy runner reads: GET /api/labrun/ticks on the chart service (Server-Sent Events).

Read-only. The fan-out (TickFan) is tested by itself -- an endless response cannot run in TestClient -- and through
the app wherever the stream is made to end (the service is stopping) or the app is driven as plain ASGI."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import signal

import pytest
import uvicorn
from fastapi.testclient import TestClient

from homebase.charts import server
from homebase.charts.server import TIMEFRAMES, TickFan, create_app
from homebase.charts.store import read_table
from homebase.charts.tick import Tick
from tests.charts_util import D, rows, session_ms, write_archive, write_gz

OK = {"host": "127.0.0.1:8852"}
T0 = session_ms(D, 9, 29)


def parse(chunks) -> list:
    """[(event, data), ...] from the SSE text; a data event with no name is ("", data)."""
    out = []
    for block in "".join(chunks).split("\n\n"):
        if not block:
            continue
        name, data = "", None
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:])
        out.append((name, data))
    return out


def prints(events, root="NQ") -> list:
    return [r for name, d in events if name == "" and d["root"] == root for r in d["rows"]]


def tape(n, start=T0, step=1000) -> list:
    return [Tick(start + i * step, 100.0 + i, 1 + i % 3, 1, i + 1) for i in range(n)]


def fan_of(tapes: dict, now=lambda: 1_000, **kw) -> TickFan:
    return TickFan(now, tapes.get, **kw)


async def take(gen, n) -> list:
    return [await asyncio.wait_for(gen.__anext__(), 2.0) for _ in range(n)]


async def until(gen, name) -> list:
    """Everything up to and including the first `name` event."""
    out = []
    while True:
        out.append(await asyncio.wait_for(gen.__anext__(), 2.0))
        if parse(out[-1:])[0][0] == name:
            return out


# ---------------------------------------------------------------- the fan-out by itself
def test_the_backlog_comes_first_then_live_once_then_the_clock_and_the_live_batches():
    """No clock before the backlog is complete: a clock ahead of its prints would make the runner fire events "with
    no print" whose prints are still on their way (review C1)."""
    async def go():
        t = tape(5)
        fan = fan_of({"NQ": t})
        gen = fan.stream(["NQ"], 0, clock_s=60)
        head = await until(gen, "clock")
        fan.publish("NQ", [{"ts_ms": T0 + 9000, "price": "250.25", "size": "4"}, {"ts_ms": T0 + 9000, "price": 250.5, "size": 2}])
        fan.publish("ES", [{"ts_ms": 1, "price": 1.0, "size": 1}])               # a market it did not ask for
        fan.publish("NQ", [{"ts_ms": T0 + 9500, "price": 251.0, "size": 1}])
        live = await take(gen, 2)
        await gen.aclose()
        return parse(head), parse(live), len(fan.readers)

    head, live, readers = asyncio.run(go())
    assert [n for n, _ in head] == ["", "live", "clock"] and head[2][1] == {"now_ms": 1_000}
    assert head[0][1] == {"root": "NQ", "rows": [[T0 + i * 1000, 100.0 + i, 1 + i % 3] for i in range(5)]}
    assert live == [("", {"root": "NQ", "rows": [[T0 + 9000, 250.25, 4], [T0 + 9000, 250.5, 2]]}),
                    ("", {"root": "NQ", "rows": [[T0 + 9500, 251.0, 1]]})]
    assert readers == 0                                                      # closed: no longer fanned out to


def test_nothing_is_missing_and_nothing_comes_twice_across_the_seam(monkeypatch):
    """Prints that land while the backlog is being read (several thread hops here) are in the live part, once."""
    monkeypatch.setattr(server, "LABRUN_CHUNK", 3)

    async def go():
        t = tape(10)
        fan = fan_of({"NQ": t})
        gen = fan.stream(["NQ"], 0, clock_s=60)
        out = await take(gen, 1)                                             # the first backlog rows
        for i in range(10, 14):                                              # as the service does: the tape, then the fan-out
            tk = Tick(T0 + i * 1000, 100.0 + i, 1, 1, i + 1)
            t.append(tk)
            fan.publish("NQ", [{"ts_ms": tk.ts_ms, "price": tk.price, "size": tk.size}])
        out += await until(gen, "clock")
        out += await take(gen, 4)
        await gen.aclose()
        return parse(out)

    ev = asyncio.run(go())
    names = [n for n, _ in ev]
    assert names[:6] == ["", "", "", "", "live", "clock"] and names.count("live") == 1 and names.count("clock") == 1
    assert [len(d["rows"]) for n, d in ev[:4]] == [3, 3, 3, 1]               # at most LABRUN_CHUNK rows an event
    assert [r[0] for r in prints(ev)] == [T0 + i * 1000 for i in range(14)]


def test_since_ms_cuts_the_backlog_and_each_market_has_its_own():
    async def go():
        fan = fan_of({"NQ": tape(6), "ES": tape(3, start=T0 + 500)})
        gen = fan.stream(["NQ", "ES", "GC"], T0 + 2000, clock_s=60)          # GC: no tape yet
        out = await until(gen, "live")
        await gen.aclose()
        return parse(out)

    ev = asyncio.run(go())
    assert [r[0] for r in prints(ev)] == [T0 + i * 1000 for i in range(2, 6)]      # ts_ms >= since_ms, oldest first
    assert [r[0] for r in prints(ev, "ES")] == [T0 + 2500]


def test_the_clock_ticks_every_second_and_is_the_services_own():
    async def go():
        now = [5_000]
        fan = fan_of({}, now=lambda: now[0])
        gen = fan.stream(["NQ"], 0, clock_s=0.2)
        first = await until(gen, "clock")                                    # live, then the clock at once
        now[0] = 6_000
        second = await take(gen, 1)
        fan.publish("NQ", [{"ts_ms": 1, "price": 1.0, "size": 1}])
        third = await take(gen, 1)
        now[0] = 7_000
        fourth = await take(gen, 1)
        await gen.aclose()
        return parse(first + second + third + fourth)

    ev = asyncio.run(go())
    assert ev == [("live", {}), ("clock", {"now_ms": 5_000}), ("clock", {"now_ms": 6_000}),
                  ("", {"root": "NQ", "rows": [[1, 1.0, 1]]}), ("clock", {"now_ms": 7_000})]


def test_a_reader_that_falls_behind_is_dropped_and_the_others_go_on(monkeypatch):
    monkeypatch.setattr(server, "LABRUN_QUEUE_MAX", 3)

    async def go():
        fan = fan_of({})
        slow, fast = fan.stream(["NQ"], 0, clock_s=60), fan.stream(["NQ"], 0, clock_s=60)
        await until(slow, "live")
        await until(fast, "clock")
        got = []
        for i in range(6):                                                   # the slow one reads nothing
            fan.publish("NQ", [{"ts_ms": i, "price": 1.0, "size": 1}])
            got += await take(fast, 1)
        n = len(fan.readers)
        left = [x async for x in slow]                                       # its stream ends: it will ask again
        await fast.aclose()
        return parse(got), left, n

    got, left, readers = asyncio.run(go())
    assert [r[0] for r in prints(got)] == list(range(6))                     # the fast reader missed nothing
    assert prints(parse(left)) == [] and readers == 1


def test_the_stream_ends_when_the_service_is_told_to_stop():
    """An endless response would hold the server's shutdown open for good, and the lifespan's clean-up with it."""
    async def go():
        stop = [False]
        fan = fan_of({"NQ": tape(2)}, stopping=lambda: stop[0])
        gen = fan.stream(["NQ"], 0, clock_s=0.05)
        out = await until(gen, "clock")
        out += await take(gen, 1)
        stop[0] = True
        rest = [x async for x in gen]
        return parse(out), rest, len(fan.readers)

    ev, rest, readers = asyncio.run(go())
    assert [n for n, _ in ev] == ["", "live", "clock", "clock"] and len(rest) <= 1 and readers == 0


def test_the_stop_signal_is_read_where_this_uvicorn_keeps_it():
    """server_stopping() reads uvicorn's own flag through the SIGTERM handler it installs. Pinned here: a uvicorn that
    moves either must fail this test, not leave the chart service unable to stop."""
    import inspect
    srv = uvicorn.Server(uvicorn.Config(app=lambda *a: None))
    assert "signal.signal(sig, self.handle_exit)" in inspect.getsource(uvicorn.Server.capture_signals)
    assert signal.SIGTERM in uvicorn.server.HANDLED_SIGNALS
    assert server.server_stopping(lambda sig: srv.handle_exit) is False
    srv.handle_exit(signal.SIGTERM, None)
    assert server.server_stopping(lambda sig: srv.handle_exit) is True
    assert server.server_stopping() is False                                # no server here: the default handler
    assert server.server_stopping(lambda sig: signal.SIG_DFL) is False


@pytest.mark.parametrize("spec", ["2.3", "2.4"])
def test_a_reader_that_hangs_up_leaves_the_fan_out_at_once(spec):
    """Whichever way the server learns of it: a disconnect message (ASGI 2.3, uvicorn's) or a send that fails (2.4)."""
    async def go():
        fan = fan_of({"NQ": tape(2)})
        resp = server._TickStream(fan.stream(["NQ"], 0, clock_s=60), media_type="text/event-stream")
        sent, gone = [], asyncio.Event()

        async def receive():
            await gone.wait()
            return {"type": "http.disconnect"}

        async def send(msg):
            if gone.is_set():
                raise OSError("the client is gone")
            sent.append(msg)

        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": spec}}
        task = asyncio.create_task(resp(scope, receive, send))
        await wait_for(lambda: len(sent) == 4)                               # the headers, the rows, live, the clock
        attached = len(fan.readers)
        gone.set()
        fan.publish("NQ", [{"ts_ms": 1, "price": 1.0, "size": 1}])
        await asyncio.wait([task], timeout=2.0)
        return attached, len(fan.readers), task.done()

    assert asyncio.run(go()) == (1, 0, True)


def test_publish_never_raises():
    fan = fan_of({})

    class Broken:
        roots = {"NQ"}
        dropped = False

        @property
        def q(self):
            raise RuntimeError("boom")

    fan.readers.add(Broken())
    fan.publish("NQ", [{"ts_ms": 1, "price": 1.0, "size": 1}])              # logged, never raised into the tick path
    fan.publish("NQ", [])


# ---------------------------------------------------------------- through the app
def replay_app(tmp_path, roots=("NQ",)):
    base = tmp_path / "ticks"
    write_archive(base, "NQ", D, "NQZ6", rows(T0, [200.0 + 0.25 * (i % 4) for i in range(240)], first_id=5000))
    return create_app(roots=list(roots), base=base, replay=D, speed=1, start_et=dt.time(9, 30), state=tmp_path / "state")


@pytest.mark.parametrize("headers", [
    {"host": "evil.example"}, {"host": "127.0.0.1.nip.io:8852"}, {"host": "[::1]:8852"},
    {**OK, "origin": "https://evil.example"}, {**OK, "origin": "http://127.0.0.1:8852"},
    {"host": "localhost:8852", "origin": "http://localhost:8852"}, {**OK, "origin": "null"}])
def test_only_this_machine_and_never_a_browser(tmp_path, headers):
    with TestClient(replay_app(tmp_path), base_url="http://127.0.0.1:8852") as c:
        r = c.get("/api/labrun/ticks?roots=NQ", headers=headers)
        assert r.status_code == 403 and "access-control-allow-origin" not in r.headers


def test_the_route_serves_the_replayed_session_so_far_then_ends_when_the_service_stops(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "server_stopping", lambda *a: True)          # so the response ends: TestClient can read it
    with TestClient(replay_app(tmp_path), base_url="http://127.0.0.1:8852") as c:
        r = c.get("/api/labrun/ticks?roots=nq,ZZ,NQ&since_ms=" + str(T0 + 30_000), headers={"host": "localhost:8852"})
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["cache-control"] == "no-cache" and "access-control-allow-origin" not in r.headers
        ev = parse([r.text])
        assert [n for n, _ in ev] == ["", "live", "clock"]
        assert abs(ev[2][1]["now_ms"] - session_ms(D, 9, 30)) < 5_000        # the replay's clock, not the wall's
        got = prints(ev)                                                     # 09:29:30 up to where the replay is
        assert [x[0] for x in got] == [T0 + i * 1000 for i in range(30, 30 + len(got))] and 30 <= len(got) <= 45
        assert got[0] == [T0 + 30_000, 200.5, 1]
        assert c.get("/api/labrun/ticks?since_ms=x", headers=OK).status_code == 422
        none = parse([c.get("/api/labrun/ticks", headers=OK).text])           # no market asked for: the clock only
        assert [n for n, _ in none] == ["live", "clock"]


class Feed:
    """A live feed the test drives by hand, on the service's own loop."""

    def __init__(self, cap):
        self.cap = cap

    def __call__(self, roots, on_ticks, on_subscribed=None):
        self.cap["on_ticks"], self.ws = on_ticks, None
        return self

    async def run(self):
        while True:
            await asyncio.sleep(3600)

    def stop(self):
        pass

    def budget_used(self):
        return 0

    def count_request(self):
        pass

    def status(self):
        return {"mode": "live", "connected": True, "error": None, "roots": {}, "budget_hour": 0, "reconnects": 0}


def live_app(tmp_path, cap):
    base = tmp_path / "ticks"
    write_gz(base / "NQ" / "2026" / f"{D}_NQZ6.live.csv.gz", rows(session_ms(D, 9, 40), [100.0, 100.25, 100.5], first_id=100))
    return create_app(roots=["NQ"], base=base, feed_factory=Feed(cap), now_ms=lambda: session_ms(D, 9, 45),
                      state=tmp_path / "state"), base


async def asgi_get(app, path: str, query: str, sent: list, gate: asyncio.Event | None = None):
    """The app as plain ASGI: the response's messages land in `sent` as they are sent. Cancel the task to hang up.
    gate: while it is cleared the reader takes nothing more (a client that stopped reading)."""
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
             "path": path, "raw_path": path.encode(), "query_string": query.encode(), "root_path": "",
             "headers": [(b"host", b"127.0.0.1:8852")], "client": ("127.0.0.1", 50000), "server": ("127.0.0.1", 8852)}
    gone = asyncio.Event()

    async def receive():
        await gone.wait()
        return {"type": "http.disconnect"}

    async def send(msg):
        if gate is not None:
            await gate.wait()
        sent.append(msg)

    await app(scope, receive, send)


def body(sent) -> list:
    return parse([m.get("body", b"").decode() for m in sent if m["type"] == "http.response.body"])


async def wait_for(pred, s=3.0):
    end = asyncio.get_running_loop().time() + s
    while not pred():
        assert asyncio.get_running_loop().time() < end, "timed out"
        await asyncio.sleep(0.01)


def test_live_prints_reach_the_reader_once_and_the_tick_path_never_depends_on_it(tmp_path, monkeypatch):
    cap: dict = {}
    app, base = live_app(tmp_path, cap)
    monkeypatch.setattr(server, "LABRUN_QUEUE_MAX", 4)
    t = session_ms(D, 9, 44)

    async def go():
        async with app.router.lifespan_context(app):
            sent, stuck, gate = [], [], asyncio.Event()
            gate.set()
            task = asyncio.create_task(asgi_get(app, "/api/labrun/ticks", "roots=NQ&since_ms=0", sent))
            idle = asyncio.create_task(asgi_get(app, "/api/labrun/ticks", f"roots=NQ&since_ms={t}", stuck, gate))
            await wait_for(lambda: all(any(n == "live" for n, _ in body(x)) for x in (sent, stuck)))
            first = body(sent)
            gate.clear()                                                     # the second reader stops reading
            for i in range(8):
                cap["on_ticks"]("NQ", "NQZ6", rows(t + i * 1000, [101.0 + i], first_id=200 + i))
                await wait_for(lambda: len(prints(body(sent))) == 3 + i + 1)  # the first one keeps up
            gate.set()
            await asyncio.wait_for(idle, 3.0)                                # dropped: its stream ended by itself
            # and a fan-out that raises outright never breaks the tick path
            monkeypatch.setattr(TickFan, "publish", lambda self, root, rows_: 1 / 0)
            cap["on_ticks"]("NQ", "NQZ6", rows(t + 9000, [110.0], first_id=300))
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            return first, body(sent), body(stuck)

    first, ev, late = asyncio.run(go())
    assert [n for n, _ in first[:2]] == ["", "live"]                         # the backlog: what was recorded before
    got = prints(ev)
    assert [x[0] for x in got] == [session_ms(D, 9, 40) + i * 1000 for i in range(3)] + [t + i * 1000 for i in range(8)]
    assert got[3] == [t, 101.0, 1] and len(prints(late)) < 8                 # none missing, none twice; the slow one: cut
    header, recs = read_table(base / "NQ" / "2026" / f"{D}_NQZ6.live.csv.gz")
    assert [r[header.index("id")] for r in recs][-9:] == [str(200 + i) for i in range(8)] + ["300"]   # all recorded


def test_the_other_routes_answer_as_before(tmp_path):
    app = replay_app(tmp_path)
    labrun = [(r.path, sorted(r.methods)) for r in app.routes if "labrun" in getattr(r, "path", "")]
    assert labrun == [("/api/labrun/ticks", ["GET"])]                        # ONE new route, read-only
    with TestClient(app, base_url="http://127.0.0.1:8852") as c:
        assert c.get("/api/symbols").json() == {"roots": ["NQ"], "timeframes": TIMEFRAMES}
        st = c.get("/api/status").json()
        assert st["mode"] == "replay" and not [k for k in st if "labrun" in k]
        assert c.post("/api/labrun/ticks", headers=OK).status_code == 405


# ---------------------------------------------------------------- end to end: the chart service's stream to a day file
def test_the_real_stream_feeds_the_runner(tmp_path, monkeypatch):
    """The chart service (a replay, built in-process) -> its SSE stream -> the tick client -> the runner -> the child
    -> the store. The stream is made to end (the service is stopping), so the test client can hand it over whole."""
    from homebase.labrun import store
    from homebase.labrun.host import Runner
    from homebase.labrun.tickclient import TickClient
    from tests.test_labrun_host import MARKET_930, plain, rec
    import threading
    monkeypatch.setattr(server, "server_stopping", lambda *a: True)
    base, t0 = tmp_path / "ticks", session_ms(D, 9, 20)                      # a tape that begins before the window does
    write_archive(base, "NQ", D, "NQZ6", rows(t0, [200.0 + 0.25 * (i % 4) for i in range(720)], first_id=5000))
    app = server.create_app(roots=["NQ"], base=base, replay=D, speed=1, start_et=dt.time(9, 30), state=tmp_path / "state")
    source = MARKET_930.replace('"09:30:00", "15:55"', '"09:29:30", "15:55"').replace('== "09:30:00"', '== "09:29:30"')
    at_ = tmp_path / "desklab"
    store.put(rec(source), at_)
    got, stop = [], threading.Event()
    with TestClient(app, base_url="http://127.0.0.1:8852") as c:
        TickClient("http://127.0.0.1:8852", lambda: ["NQ"], got.append, transport=c._transport,
                   sleep=lambda s: stop.set()).run(stop)
    assert [x[0] for x in got] == ["connect", "ticks", "live", "clock"]      # the whole session, then live, then the clock
    assert abs(got[-1][1] - session_ms(D, 9, 30)) < 5_000
    held = [r for x in got if x[0] == "ticks" for r in x[2]]
    assert [r[0] for r in held][:60] == [t0 + i * 1000 for i in range(60)] and held[1] == [t0 + 1000, 200.25, 1]
    r = Runner(at=at_, source="http://127.0.0.1:8852", spawn=plain, deadline_s=2.0, daily=lambda root, d: [])
    try:
        for item in got:
            r.take(item)
        r.sync()
        s = store.get_day("lab_x", D.isoformat(), at_)
        assert s["state"] == "running" and s["orders"] == [
            {"t": "09:29:30", "text": "Buy at market, stop 190.25", "refused": None}]
        r.beat()
        assert store.get_runner(at_)["hosting"] == ["lab_x"]
    finally:
        r.close()
