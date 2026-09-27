"""Per-chart Bar Replay inside the LIVE chart service (spec 2026-09-27, Part A).

In-process, no network, no broker; the archive is a tmp dir (never ~/futures_ticks). Time is an injected
wall clock (`wall`), so play/speed are exact."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import queue
import time

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

import homebase.charts.barreplay as br_mod
from homebase.charts.barreplay import FIRST_DATE, MAX_PER_CONN, MAX_PER_SERVER, BarReplay
from homebase.charts.bars import BarSpec, build
from homebase.charts.desk import Fanout, Quotes
from homebase.charts.hub import Hub
from homebase.charts.recorder import LiveRecorder
from homebase.charts.server import MAX_STUDIES, MIN_BAR, create_app
from homebase.charts.session import et_wall_s, session_range_ms
from homebase.charts.store import TickStore
from tests.charts_util import D, ET, rows, session_ms, write_archive, write_gz

P = D - dt.timedelta(days=1)                 # Wednesday: a completed session behind the replay day
N = D + dt.timedelta(days=1)                 # Friday: the LIVE session (the clock is here)
NOW = session_ms(N, 9, 45)
SAT = dt.date(2026, 9, 19)                   # a Saturday: BTC trades 24/7 since 2026-05-30
HOST = {"host": "localhost:8852"}


class FakeConn:
    dead = False

    def __init__(self):
        self.out: list[dict] = []

    def send(self, m: dict) -> None:
        self.out.append(m)

    def of(self, kind: str, cid: str | None = None) -> list[dict]:
        return [m for m in self.out if m.get("type") == kind and (cid is None or m.get("id") == cid)]

    def last(self, kind: str, cid: str | None = None) -> dict:
        got = self.of(kind, cid)
        assert got, f"no {kind!r} for {cid!r} in {[m.get('type') for m in self.out]}"
        return got[-1]


def d_rows():
    """The replay day: 240 trades, 09:29:00 -> 09:32:59, one a second, cycling 200.00 .. 200.75."""
    return rows(session_ms(D, 9, 29), [200.0 + 0.25 * (i % 4) for i in range(240)], first_id=5000)


def archive(tmp_path):
    base = tmp_path / "ticks"
    write_archive(base, "NQ", P, "NQZ6", rows(session_ms(P, 9, 30), [100.0 + 0.25 * (i % 4) for i in range(120)]))
    write_archive(base, "NQ", D, "NQZ6", d_rows())
    return base


def mk(tmp_path, base=None, roots=("NQ",), now=NOW):
    wall = [1000.0]
    r = BarReplay(TickStore(base or archive(tmp_path)), tmp_path / "cache", list(roots), lambda: now,
                  min_bar=MIN_BAR, max_studies=MAX_STUDIES, wall=lambda: wall[0])
    return r, wall


def run(coro):
    return asyncio.run(coro)


def start(r, conn, cid="a", **kw):
    msg = {"op": "replay_start", "id": cid, "root": "NQ", "spec": "time:60",
           "date": D.isoformat(), "start_et": "09:30", "speed": 1, **kw}
    return run(r.start(conn, cid, msg))


def ctl(r, conn, cid="a", **kw):
    return run(r.control(conn, cid, {"op": "replay_ctl", "id": cid, **kw}))


def today_bars(conn, cid="a", day=D):
    """The replay day's bars the page holds now: history, then every update applied."""
    hist = conn.last("history", cid)
    i0 = conn.out.index(hist)
    closed = [b for b in hist["bars"] if b["s"] == day.isoformat()]
    live = closed.pop() if hist["live"] and closed else None
    for m in conn.out[i0 + 1:]:
        if m.get("type") == "update" and m.get("id") == cid:
            closed.extend(m["closed"])
            live = m["live"]
    return closed, live


def fresh(ticks_rows, spec, upto_ms, root="NQ", tick=0.25):
    """What a from-scratch build of the day's ticks <= upto_ms gives (the replay must equal it)."""
    from homebase.charts.tick import SideClassifier, from_row
    clf = SideClassifier()
    tks = [from_row(x, clf) for x in ticks_rows if x["ts_ms"] <= upto_ms]
    closed, cur = build(tks, spec, tick, root)
    return closed, cur


# ---------------------------------------------------------------- start
def test_start_answers_the_normal_history_cut_at_the_cursor(tmp_path):
    r, _ = mk(tmp_path)
    c = FakeConn()
    assert start(r, c, start_et="09:30", studies=["vwap", "profile"]) is True
    h = c.last("history", "a")
    cursor = session_ms(D, 9, 30)
    assert h["replay"] is True and h["root"] == "NQ" and h["spec"] == "time:60"
    assert h["bars"][0]["s"] == P.isoformat()                          # past sessions come first
    assert all(b["ms"] <= cursor for b in h["bars"])                   # nothing after the cursor
    day = [b for b in h["bars"] if b["s"] == D.isoformat()]
    assert sum(b["v"] for b in day) == 61                             # 09:29:00 .. 09:30:00 inclusive
    assert [s["date"] for s in h["sessions"]] == [P.isoformat(), D.isoformat()]
    assert h["sessions"][-1]["contract"] == "NQZ6"
    assert "vwap" in h["studies"] and h["profile"]["poc"] > 0
    assert len(h["studies"]["vwap"]) == len(h["bars"])
    st = c.last("replay_state", "a")
    assert st == {"type": "replay_state", "id": "a", "date": D.isoformat(), "cursor_ms": cursor,
                  "speed": 1, "playing": False, "done": False}


def test_start_takes_the_charts_own_live_subscription_when_the_message_names_none(tmp_path):
    class Live:                      # the live stream the chart was on (read only)
        root, spec, studies, profile = "NQ", BarSpec("time", 300), {"ema:9": None}, None
    r, _ = mk(tmp_path)
    c = FakeConn()
    msg = {"op": "replay_start", "id": "a", "date": D.isoformat(), "start_et": "09:31", "speed": 5}
    assert run(r.start(c, "a", msg, live=Live())) is True
    h = c.last("history", "a")
    assert h["spec"] == "time:300" and list(h["studies"]) == ["ema:9"]
    msg.pop("date")
    assert run(r.start(FakeConn(), "b", msg)) is False                 # no date, no chart: refused


@pytest.mark.parametrize("why,kw,text", [
    ("before the first archived day", {"date": "2021-09-21"}, "2021-09-22"),
    ("today's live session", {"date": N.isoformat()}, "completed"),
    ("a classic root's Saturday", {"date": SAT.isoformat()}, "no archived"),
    ("no file", {"date": "2026-09-10"}, "no archived"),
    ("bad date", {"date": "24/09/2026"}, "YYYY-MM-DD"),
    ("bad speed", {"speed": 3}, "speed"),
    ("bool speed", {"speed": True}, "speed"),
    ("start in the dead hour", {"start_et": "17:30"}, "outside"),
    ("bad start", {"start_et": "9h30"}, "HH:MM"),
    ("unknown root", {"root": "ZZ"}, "not"),
    ("too fine", {"spec": "tick:10"}, "minimum"),
    ("unknown study", {"studies": ["nope"]}, "unknown study"),
    ("too many studies", {"studies": [f"ema:{n}" for n in range(1, 18)]}, "at most"),
])
def test_start_refuses_what_it_cannot_replay(tmp_path, why, kw, text):
    base = archive(tmp_path)
    write_archive(base, "NQ", dt.date(2021, 9, 21), "NQZ1", rows(session_ms(dt.date(2021, 9, 21), 9, 30), [1.0]))
    r, _ = mk(tmp_path, base=base)
    c = FakeConn()
    assert start(r, c, **kw) is False, why
    err = c.last("replay_error", "a")
    assert err["op"] == "replay_start" and text in err["error"], (why, err)
    assert not c.of("history") and not r.owns(c, "a")


def test_the_first_archived_day_is_allowed(tmp_path):
    base = archive(tmp_path)
    first = FIRST_DATE
    assert first == dt.date(2021, 9, 22)
    write_archive(base, "NQ", first, "NQZ1", rows(session_ms(first, 9, 30), [1.0, 1.25, 1.5]))
    r, _ = mk(tmp_path, base=base)
    c = FakeConn()
    assert start(r, c, date=first.isoformat(), start_et="09:31") is True
    assert c.last("replay_state")["done"] is True                    # the cursor is past its last trade


# ---------------------------------------------------------------- play / pause / speed / jump
def test_play_advances_speed_times_the_wall_clock(tmp_path):
    r, wall = mk(tmp_path)
    c = FakeConn()
    start(r, c, speed=10, start_et="09:30")
    t0 = session_ms(D, 9, 30)
    ctl(r, c, action="play")
    assert c.last("replay_state")["playing"] is True
    for _ in range(12):                      # 3 s of wall time at the pump's 0.25 s
        wall[0] += 0.25
        r.pump()
    assert r.cursor(c, "a") == t0 + 30_000   # 10x
    ups = c.of("update", "a")
    assert ups and all(u["replay"] is True for u in ups)
    closed, live = today_bars(c)
    want_closed, want_cur = fresh(d_rows(), BarSpec("time", 60), t0 + 30_000)
    assert [(b["ms"], b["v"], b["o"], b["c"], b["d"]) for b in closed] == \
        [(b.t, b.v, b.o, b.c, b.delta) for b in want_closed]
    assert live["v"] == want_cur.v
    # replay_state once a second while playing (not on every pump)
    states = [m for m in c.out if m.get("type") == "replay_state"]
    assert 3 <= len(states) <= 5


def test_pause_speed_and_jump(tmp_path):
    r, wall = mk(tmp_path)
    c = FakeConn()
    start(r, c, speed=5, start_et="09:30")
    t0 = session_ms(D, 9, 30)
    ctl(r, c, action="play")
    wall[0] += 2
    r.pump()
    assert r.cursor(c, "a") == t0 + 10_000
    ctl(r, c, action="pause")
    st = c.last("replay_state")
    assert st["playing"] is False and st["cursor_ms"] == t0 + 10_000
    wall[0] += 5
    r.pump()
    assert r.cursor(c, "a") == t0 + 10_000               # paused: the cursor holds
    ctl(r, c, action="speed", speed=60)
    assert c.last("replay_state")["speed"] == 60
    ctl(r, c, action="play")
    wall[0] += 1
    r.pump()
    assert r.cursor(c, "a") == t0 + 70_000
    ctl(r, c, action="speed", speed=2)                   # a change while playing re-anchors
    wall[0] += 1
    r.pump()
    assert r.cursor(c, "a") == t0 + 72_000
    n_hist = len(c.of("history", "a"))
    ctl(r, c, action="jump", to_et="09:30")                # BACK: a fresh history
    assert len(c.of("history", "a")) == n_hist + 1
    h = c.last("history", "a")
    assert all(b["ms"] <= t0 for b in h["bars"]) and h["replay"] is True
    assert sum(b["v"] for b in h["bars"] if b["s"] == D.isoformat()) == 61
    st = c.last("replay_state")
    assert st["cursor_ms"] == t0 and st["playing"] is True and st["speed"] == 2
    wall[0] += 1
    r.pump()
    assert r.cursor(c, "a") == t0 + 2_000                # still playing, from the jump
    ctl(r, c, action="jump", to_et="09:32")              # forward
    assert r.cursor(c, "a") == session_ms(D, 9, 32)
    ctl(r, c, action="speed", speed=7)
    err = c.last("replay_error")
    assert err["op"] == "replay_ctl" and "speed" in err["error"]
    ctl(r, c, action="jump", to_et="17:30")
    assert "outside" in c.last("replay_error")["error"]
    ctl(r, c, action="warp")
    assert "action" in c.last("replay_error")["error"]


def test_play_to_the_end_is_done_and_stops(tmp_path):
    r, wall = mk(tmp_path)
    c = FakeConn()
    start(r, c, speed=60, start_et="09:32")
    ctl(r, c, action="play")
    wall[0] += 2
    r.pump()
    st = c.last("replay_state")
    assert st["done"] is True and st["playing"] is False
    closed, live = today_bars(c)
    assert sum(b["v"] for b in closed) + (live["v"] if live else 0) == 240
    ctl(r, c, action="step")                             # nothing left: harmless
    assert c.last("replay_state")["done"] is True


# ---------------------------------------------------------------- step
@pytest.mark.parametrize("spec", ["time:60", "time:15", "tick:100", "range:2", "volume:100"])
def test_step_advances_exactly_one_bar(tmp_path, spec):
    r, _ = mk(tmp_path)
    c = FakeConn()
    start(r, c, spec=spec, speed="bar", start_et="09:29")
    bs = BarSpec.parse(spec)
    n0 = len(today_bars(c)[0])
    for k in range(1, 3 if bs.kind in ("tick", "volume") else 4):   # 240 trades: two 100-trade bars
        ctl(r, c, action="step")
        closed, live = today_bars(c)
        assert len(closed) == n0 + k, (spec, k)
        cur = r.cursor(c, "a")
        want_closed, want_cur = fresh(d_rows(), bs, cur)
        if bs.kind == "time" and want_cur is not None and want_cur.t + bs.size * 1000 <= cur:
            want_closed, want_cur = want_closed + [want_cur], None    # the clock closed it
        assert [(b["ms"], b["v"], b["h"], b["l"]) for b in closed] == \
            [(b.t, b.v, b.h, b.l) for b in want_closed], (spec, k)
    assert c.last("replay_state")["playing"] is False


def test_step_on_a_time_chart_lands_on_the_bar_end(tmp_path):
    r, _ = mk(tmp_path)
    c = FakeConn()
    start(r, c, speed="bar", start_et="09:30")            # 09:30 bar holds one trade so far
    ctl(r, c, action="step")
    assert r.cursor(c, "a") == session_ms(D, 9, 31)
    closed, _ = today_bars(c)
    assert closed[-1]["ms"] == session_ms(D, 9, 30) and closed[-1]["v"] == 60


def test_bar_speed_plays_one_bar_a_second_and_step_pauses_a_play(tmp_path):
    r, wall = mk(tmp_path)
    c = FakeConn()
    start(r, c, speed="bar", start_et="09:29")
    ctl(r, c, action="play")
    for _ in range(8):
        wall[0] += 0.25
        r.pump()
    assert r.cursor(c, "a") == session_ms(D, 9, 31)       # two bars in two seconds
    ctl(r, c, speed=10, action="speed")
    ctl(r, c, action="step")
    assert c.last("replay_state")["playing"] is False


# ---------------------------------------------------------------- stop / limits
def test_stop_returns_the_chart_to_live(tmp_path):
    r, wall = mk(tmp_path)
    c = FakeConn()
    start(r, c)
    ctl(r, c, action="play")
    assert r.stop(c, "a") is True
    assert c.out[-1] == {"type": "reset", "id": "a"}        # the page resubscribes: live again
    st = c.last("replay_state")
    assert st["stopped"] is True and st["playing"] is False
    assert not r.owns(c, "a") and r.count() == 0
    n = len(c.out)
    wall[0] += 5
    r.pump()
    assert len(c.out) == n                                  # nothing more for it
    assert r.stop(c, "a") is False


def test_limits_per_connection_and_per_server(tmp_path):
    r, _ = mk(tmp_path)
    a, b, x = FakeConn(), FakeConn(), FakeConn()
    assert MAX_PER_CONN == 4 and MAX_PER_SERVER == 8
    for i in range(4):
        assert start(r, a, cid=f"a{i}") is True
    assert start(r, a, cid="a4") is False
    assert "4" in a.last("replay_error", "a4")["error"]
    assert start(r, a, cid="a0", start_et="09:31") is True    # restarting one of them is no fifth
    for i in range(4):
        assert start(r, b, cid=f"b{i}") is True
    assert start(r, x, cid="x0") is False
    assert "8" in x.last("replay_error", "x0")["error"]
    r.drop_conn(a)                                           # a disconnect ends its streams
    assert r.count() == 4 and r.count(a) == 0
    assert start(r, x, cid="x0") is True


def test_a_stream_holds_one_session_of_ticks(tmp_path):
    r, _ = mk(tmp_path)
    c = FakeConn()
    start(r, c)
    assert r.tick_count(c, "a") == 240


# ---------------------------------------------------------------- data edge cases
def test_a_session_with_a_missing_hour_plays_with_its_gaps_marked(tmp_path):
    base = tmp_path / "ticks"
    write_archive(base, "NQ", P, "NQZ6", rows(session_ms(P, 9, 30), [100.0] * 10))
    before = rows(session_ms(D, 9, 29), [200.0 + 0.25 * (i % 4) for i in range(180)], first_id=1)
    after = rows(session_ms(D, 10, 31), [201.0 + 0.25 * (i % 4) for i in range(120)], first_id=1000)
    live = write_gz(base / "NQ" / "2026" / f"{D}_NQZ6.live.csv.gz", before + after)
    hole = [session_ms(D, 9, 32), session_ms(D, 10, 31)]
    (live.parent / f"{D}_NQZ6.live.gaps").write_text(json.dumps([hole]))
    r, wall = mk(tmp_path, base=base)
    c = FakeConn()
    start(r, c, start_et="09:31", speed="bar")
    h = c.last("history")
    assert h["sessions"][-1]["gaps"] == [[et_wall_s(hole[0]), et_wall_s(hole[1])]]
    assert h["sessions"][-1]["source"] == "live"
    ctl(r, c, action="step")                                  # closes 09:31
    ctl(r, c, action="step")                                  # nothing trades 09:32-10:31: the next bar is 10:31
    assert r.cursor(c, "a") == session_ms(D, 10, 32)
    closed, _ = today_bars(c)
    assert [b["ms"] for b in closed][-2:] == [session_ms(D, 9, 31), session_ms(D, 10, 31)]
    ctl(r, c, action="speed", speed=60)
    ctl(r, c, action="play")
    wall[0] += 3
    r.pump()
    closed, live_bar = today_bars(c)
    assert not [b for b in closed if hole[0] <= b["ms"] < hole[1]]
    assert sum(b["v"] for b in closed) + (live_bar["v"] if live_bar else 0) == 300


def test_a_24_7_root_replays_its_saturday_session(tmp_path):
    base = tmp_path / "ticks"
    fri_eve = rows(int(dt.datetime(2026, 9, 18, 20, 0, tzinfo=ET).timestamp() * 1000), [60000.0, 60005.0])
    sat = rows(int(dt.datetime(2026, 9, 19, 9, 30, tzinfo=ET).timestamp() * 1000),
               [60010.0 + 5 * (i % 3) for i in range(180)], first_id=10)
    write_gz(base / "BTC" / "2026" / f"{SAT}_BTCV6.live.csv.gz", fri_eve + sat)
    r, _ = mk(tmp_path, base=base, roots=("NQ", "BTC"))
    c = FakeConn()
    assert start(r, c, root="BTC", date=SAT.isoformat(), start_et="09:31", speed="bar") is True
    h = c.last("history")
    assert {b["s"] for b in h["bars"]} == {SAT.isoformat()}
    assert h["bars"][0]["ms"] == fri_eve[0]["ts_ms"]         # Friday 20:00 opens Saturday's session
    assert sum(b["v"] for b in h["bars"]) == 2 + 61
    ctl(r, c, action="step")
    assert r.cursor(c, "a") == int(dt.datetime(2026, 9, 19, 9, 32, tzinfo=ET).timestamp() * 1000)
    s0, s1 = session_range_ms(SAT, "BTC")
    assert start(r, c, cid="b", root="BTC", date=SAT.isoformat(), start_et="17:30") is True   # no dead hour
    assert r.cursor(c, "b") < s1


def test_scroll_back_on_a_replay_chart_never_reaches_past_the_replay_day(tmp_path):
    r, _ = mk(tmp_path)
    c = FakeConn()
    start(r, c)
    first = c.last("history")["bars"][0]["ms"]

    async def go():
        assert r.ask_older(c, "a", first) is True
        for _ in range(200):
            if c.of("older"):
                return
            await asyncio.sleep(0.01)
    run(go())
    o = c.last("older")
    assert o["id"] == "a" and o["replay"] is True and o["done"] is True and o["bars"] == []
    assert r.ask_older(c, "zz", first) is False


# ---------------------------------------------------------------- through the service
class QuietFeed:
    """A live feed that delivers only what the test queues. No network."""
    last = None

    def __init__(self, roots, on_ticks, on_subscribed=None):
        self.on_ticks, self.ws, self.q = on_ticks, None, queue.Queue()
        QuietFeed.last = self

    async def run(self):
        while True:
            try:
                self.on_ticks(*self.q.get_nowait())
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


def next_of(ws, kind, cid=None, limit=400):
    for _ in range(limit):
        m = ws.receive_json()
        if m.get("type") == kind and (cid is None or m.get("id") == cid):
            return m
    raise AssertionError(f"no {kind!r}")


def live_app(tmp_path):
    return create_app(roots=["NQ"], base=archive(tmp_path), feed_factory=QuietFeed,
                      now_ms=lambda: NOW, state=tmp_path / "state")


def test_isolation_the_live_hub_recorder_quotes_and_desk_never_see_a_replay(tmp_path, monkeypatch):
    hubs: list = []
    orig_init = Hub.__init__

    def hub_init(self, *a, **k):
        orig_init(self, *a, **k)
        hubs.append(self)
    monkeypatch.setattr(Hub, "__init__", hub_init)
    seen = {"hub": [], "quotes": [], "recorder": [], "desk": []}
    for cls, name, key in ((Quotes, "note", "quotes"), (LiveRecorder, "append", "recorder"),
                           (Fanout, "publish", "desk")):
        orig = getattr(cls, name)

        def spy(self, *a, _o=orig, _k=key, **k):
            seen[_k].append(a)
            return _o(self, *a, **k)
        monkeypatch.setattr(cls, name, spy)
    orig_on_ticks = Hub.on_ticks

    def on_ticks(self, root, rows_):
        if self is hubs[0]:
            seen["hub"].append(list(rows_))
        return orig_on_ticks(self, root, rows_)
    monkeypatch.setattr(Hub, "on_ticks", on_ticks)
    monkeypatch.setattr(br_mod, "wall_s", lambda: 0.0)

    base = tmp_path / "ticks"
    with TestClient(live_app(tmp_path)) as client, client.websocket_connect("/ws", headers=HOST) as ws:
        live_hub = hubs[0]
        ws.send_json({"op": "sub", "id": "live", "root": "NQ", "spec": "time:60"})
        next_of(ws, "history", "live")
        ws.send_json({"op": "sub", "id": "r", "root": "NQ", "spec": "time:60"})
        next_of(ws, "history", "r")
        ws.send_json({"op": "replay_start", "id": "r", "date": D.isoformat(), "start_et": "09:30",
                      "speed": 60})
        h = next_of(ws, "history", "r")
        assert h["replay"] is True and h["bars"][-1]["s"] == D.isoformat()
        # the replay chart left the live stream; the live chart is still on it
        assert [k[1] for s in live_hub.streams.values() for k in s.subs] == ["live"]
        ws.send_json({"op": "replay_ctl", "id": "r", "action": "step"})
        up = next_of(ws, "update", "r")
        assert up["replay"] is True
        # a live print reaches the live chart only
        QuietFeed.last.q.put(("NQ", "NQZ6", rows(session_ms(N, 9, 44), [300.0], first_id=77)))
        live_up = next_of(ws, "update", "live")
        assert (live_up["live"] or {}).get("c") == 300.0
        ws.send_json({"op": "replay_ctl", "id": "r", "action": "jump", "to_et": "09:32"})
        next_of(ws, "history", "r")
        ws.send_json({"op": "replay_stop", "id": "r"})
        assert next_of(ws, "reset", "r") == {"type": "reset", "id": "r"}
        assert [k[1] for s in live_hub.streams.values() for k in s.subs] == ["live"]
    replay_ms = {x["ts_ms"] for x in d_rows()}
    for key, calls in seen.items():
        for a in calls:
            rs = a[-1] if key != "desk" else []
            assert not [x for x in rs if isinstance(x, dict) and x.get("ts_ms") in replay_ms], key
    assert seen["desk"] == []
    assert all(len(rs) == 1 and rs[0]["price"] == 300.0 for rs in seen["hub"])
    assert not list(base.rglob(f"{D}_*.live.csv.gz"))          # the replayed day was never recorded
    assert len(hubs) >= 2 and all(h is not live_hub for h in hubs[1:])


def test_a_sub_or_a_disconnect_ends_the_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(br_mod, "wall_s", lambda: 0.0)
    made: list = []
    orig = BarReplay.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        made.append(self)
    monkeypatch.setattr(BarReplay, "__init__", init)
    with TestClient(live_app(tmp_path)) as client:
        with client.websocket_connect("/ws", headers=HOST) as ws:
            ws.send_json({"op": "replay_start", "id": "r", "root": "NQ", "spec": "time:60",
                          "date": D.isoformat(), "start_et": "09:30", "speed": 1})
            assert next_of(ws, "history", "r")["replay"] is True
            assert made[0].count() == 1
            ws.send_json({"op": "sub", "id": "r", "root": "NQ", "spec": "time:60"})
            h = next_of(ws, "history", "r")
            assert "replay" not in h and h["sessions"][-1]["date"] == N.isoformat()
            assert made[0].count() == 0
            ws.send_json({"op": "replay_start", "id": "r2", "root": "NQ", "spec": "time:60",
                          "date": D.isoformat(), "start_et": "09:30", "speed": 1})
            next_of(ws, "history", "r2")
            ws.send_json({"op": "replay_start", "id": "bad", "root": "NQ", "spec": "time:60",
                          "date": N.isoformat(), "start_et": "09:30", "speed": 1})
            assert next_of(ws, "replay_error", "bad")["op"] == "replay_start"
            assert made[0].count() == 1
        deadline = time.time() + 5
        while made[0].count() and time.time() < deadline:
            time.sleep(0.02)
        assert made[0].count() == 0


def test_replay_is_only_websocket_ops_behind_the_host_allowlist(tmp_path):
    app = live_app(tmp_path)
    assert not [r for r in app.routes if "replay" in getattr(r, "path", "")]
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws", headers={"origin": "http://evil.example:8852",
                                                          "host": "evil.example:8852"}) as ws:
                ws.send_json({"op": "replay_start", "id": "r", "root": "NQ", "spec": "time:60",
                              "date": D.isoformat(), "start_et": "09:30", "speed": 1})
                ws.receive_json()


def test_the_module_imports_nothing_that_trades_or_records():
    src = open(br_mod.__file__).read()
    for name in ("desk", "recorder", "tickfeed", "Quotes", "Fanout", "LiveRecorder", "tradovate"):
        assert f"import {name}" not in src and f".{name} import" not in src, name
