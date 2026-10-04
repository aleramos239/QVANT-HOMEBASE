"""/api/trade/* (key + no-Origin + local Host), the SSE stream (incl. the P2
pause and disconnects), /api/chart-trading, the Kill, the key file. No
network, no broker: TradeAdapter fakes."""
from __future__ import annotations

import asyncio
import os
import plistlib
import re
import stat
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import homebase.config as config_mod
from homebase.config import AccountCfg, AppCfg, ChartTradingCfg, StrategyCfg
from homebase.desk_api import ensure_key, event_stream, host_is_local, trade_router
from homebase.server import create_app
from tests.trading_util import NQC, TradeAdapter, journal, mkdesk, run

ACTIONS = ("order", "modify", "cancel", "exits", "cancel-symbol", "flatten", "reverse")
DESK = "http://127.0.0.1:8850"


@pytest.fixture()
def desk_client(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.engine.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.server.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.secrets_store.state_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    # the real clock would pause the views at 09:29:50-09:30:30 ET: never flake then
    monkeypatch.setattr("homebase.trading.ChartDesk._views_paused", lambda self: False)
    cfg = AppCfg(armed=False,
                 accounts={"a1": AccountCfg(keyring_key="k", account_name="A1", label="A1")},
                 book={},                                  # nothing booked: never bot-locked
                 strategies={"nq930": StrategyCfg(symbol="NQ", qty=3, offset_pts=10.0,
                                                  sl_pts=5.0, tp_pts=15.0, enabled=True)},
                 chart_trading=ChartTradingCfg(enabled=True))
    adapters = {"a1": TradeAdapter("a1")}
    app = create_app(cfg, adapters, background=False)
    # the desk as its pages and the chart service reach it (P4: a local Host only)
    with TestClient(app, base_url=DESK) as c:
        c.app, c.adapters, c.tmp = app, adapters, tmp_path
        c.key = (tmp_path / "desk.key").read_text().strip()
        c.H = {"X-Homebase-Key": c.key}
        yield c


# --- the key -----------------------------------------------------------------------
def test_the_key_file_is_created_0600_with_a_hex_key(desk_client):
    p = desk_client.tmp / "desk.key"
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    assert re.fullmatch(r"[0-9a-f]{64}", desk_client.key)


def test_an_existing_key_is_kept_and_tightened(tmp_path):
    p = tmp_path / "desk.key"
    p.write_text("ab" * 32 + "\n")
    os.chmod(p, 0o644)
    assert ensure_key(p) == ("ab" * 32, None)
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_a_corrupt_key_never_raises(tmp_path):
    p = tmp_path / "desk.key"
    p.write_text("nope")
    key, err = ensure_key(p)
    assert key is None and "desk.key does not hold a desk key" in err


# --- the gate on every trade route -------------------------------------------------------
def test_every_trade_route_needs_the_key_and_refuses_browsers(desk_client):
    c = desk_client
    routes = [("get", "/api/trade/state"), ("get", "/api/trade/stream")] + \
             [("post", f"/api/trade/{a}") for a in ACTIONS]
    for m, url in routes:
        assert getattr(c, m)(url).status_code == 401, url
        assert getattr(c, m)(url, headers={"X-Homebase-Key": "0" * 64}).status_code == 401, url
        assert getattr(c, m)(url, headers={**c.H, "Origin": "http://127.0.0.1:8850"}).status_code == 403, url


def test_every_trade_route_refuses_a_rebinding_host_even_with_the_key(desk_client):
    """DNS rebinding (P4): evil.example resolving to 127.0.0.1 reaches the
    desk with Host: evil.example — refused whatever else the request holds."""
    c = desk_client
    routes = [("get", "/api/trade/state"), ("get", "/api/trade/stream")] + \
             [("post", f"/api/trade/{a}") for a in ACTIONS]
    for m, url in routes:
        for host in ("evil.example:8850", "127.0.0.1.evil.example", "localhost.evil.example:8850"):
            r = getattr(c, m)(url, headers={**c.H, "host": host})
            assert r.status_code == 403, (url, host)
    assert c.adapters["a1"].orders == []
    assert c.get("/api/trade/state", headers={**c.H, "host": "localhost:8850"}).status_code == 200


def test_the_trade_routes_have_no_page_to_serve_a_rebound_origin(desk_client):
    c = desk_client
    r = c.post("/api/trade/order", headers={**c.H, "host": "evil.example:8850",
                                           "origin": "http://evil.example:8850"},
               json={"client_id": "x", "accounts": ["a1"], "root": "NQ", "side": "Buy",
                     "qty": 1, "type": "Market"})
    assert r.status_code == 403 and c.adapters["a1"].orders == []


@pytest.mark.parametrize("host,ok", [
    ("127.0.0.1", True), ("127.0.0.1:8850", True), ("localhost", True), ("localhost:8852", True),
    ("LOCALHOST:8850", True),
    (None, False), ("", False), ("evil.example", False), ("evil.example:8850", False),
    ("127.0.0.1.evil.example", False), ("localhost.evil.example", False),
    ("127.0.0.2:8850", False), ("[::1]:8850", False), ("localhost:", False),
    ("localhost:88500", False), ("localhost:8850 ", False), ("user@localhost", False),
    ("127.0.0.1:8850/x", False), ("0.0.0.0:8850", False),
])
def test_host_is_local_is_exact(host, ok):
    assert host_is_local(host) is ok


def test_state_is_the_cached_snapshot(desk_client):
    d = desk_client.get("/api/trade/state", headers=desk_client.H).json()
    assert d["enabled"] is True and d["accounts"][0]["id"] == "a1" and "bot" in d


def test_the_fixture_never_pauses_whatever_the_clock(desk_client):
    """The desk_client never flakes at 09:29:50-09:30:30 ET (Task 5 review)."""
    import datetime as dt
    from zoneinfo import ZoneInfo
    at_930 = dt.datetime(2026, 9, 28, 9, 30, 0, tzinfo=ZoneInfo("America/New_York"))
    desk_client.app.state.engine._now = lambda: at_930       # a Monday, inside the window
    assert desk_client.app.state.desk.views_paused() is False
    assert desk_client.post("/api/chart-trading", json={"max_order_qty": 4}).status_code == 200


def test_state_answers_503_in_the_930_pause(desk_client, monkeypatch):
    c = desk_client
    monkeypatch.setattr(c.app.state.desk, "_views_paused", lambda: True)
    r = c.get("/api/trade/state", headers=c.H)
    assert (r.status_code, r.json()) == (503, {"error": "paused around the 9:30 fire"})
    assert c.get("/api/trade/state").status_code == 401          # the gate still comes first
    monkeypatch.setattr(c.app.state.desk, "_views_paused", lambda: False)
    assert c.get("/api/trade/state", headers=c.H).status_code == 200


def test_order_route_validates_then_answers_per_account(desk_client):
    c = desk_client
    good = {"client_id": "c", "accounts": ["a1"], "root": "NQ", "side": "Buy", "qty": 1,
            "type": "Market"}
    assert c.post("/api/trade/order", headers=c.H, json={**good, "side": "Up"}).status_code == 400
    r = c.post("/api/trade/order", headers=c.H, json=good)
    assert r.status_code == 200 and r.json()["results"]["a1"]["ok"] is True
    assert c.adapters["a1"].orders[-1].symbol == NQC
    assert c.post("/api/trade/order", headers=c.H, content=b"x" * 20000).status_code == 413
    assert c.post("/api/trade/order", headers=c.H, content=b"not json").status_code == 400


def test_there_is_no_tunneled_hook_app_any_more(desk_client):
    assert not hasattr(desk_client.app.state, "hook_app")      # webhook removed 2026-09-27


# --- the desk page's switch ----------------------------------------------------------------
def test_settings_route_is_same_origin_json_only(desk_client):
    c = desk_client
    assert c.post("/api/chart-trading", content='{"enabled": false}',
                  headers={"content-type": "text/plain"}).status_code == 415
    assert c.post("/api/chart-trading", json={"enabled": False},
                  headers={"origin": "https://evil.example"}).status_code == 403
    r = c.post("/api/chart-trading", json={"enabled": False, "max_position_qty": 8},
               headers={"origin": DESK})
    assert r.status_code == 200 and r.json()["chart_trading"]["max_position_qty"] == 8
    assert c.get("/api/status").json()["chart_trading"] == \
        {"enabled": False, "max_order_qty": 10, "max_position_qty": 8}
    assert c.post("/api/chart-trading", json={"max_order_qty": 0}).status_code == 400


def test_settings_route_refuses_a_rebinding_host_even_with_a_matching_origin(desk_client):
    """The old Origin check compared Origin to Host — a rebound page has
    both = evil.example. P4: the Host itself must be local."""
    c = desk_client
    for h in ({"host": "evil.example:8850", "origin": "http://evil.example:8850"},
              {"host": "evil.example", "origin": "http://evil.example"},
              {"host": "evil.example:8850"}):
        r = c.post("/api/chart-trading", json={"max_position_qty": 3}, headers=h)
        assert r.status_code == 403, h
    assert c.get("/api/status").json()["chart_trading"]["max_position_qty"] == 20
    assert not any(e["event"] == "chart_trading_set" for e in journal(c.tmp))
    r = c.post("/api/chart-trading", json={"max_position_qty": 3},
               headers={"host": "localhost:8850", "origin": "http://localhost:8850"})
    assert r.status_code == 200


def test_kill_switches_chart_trading_off(desk_client):
    c = desk_client
    c.post("/api/kill", json={})                             # as the page sends it
    assert c.get("/api/status").json()["chart_trading"]["enabled"] is False
    assert any(e["event"] == "chart_trading_set" and e.get("cause") == "kill"
               for e in journal(c.tmp))
    good = {"client_id": "k", "accounts": ["a1"], "root": "NQ", "side": "Buy", "qty": 1,
            "type": "Market"}
    assert c.post("/api/trade/order", headers=c.H, json=good).json()["results"]["a1"]["error"] \
        == "chart trading is off — switch it on on the desk page"


# --- the SSE stream (the generator directly: an endless response cannot run in TestClient) --
def test_stream_sends_state_first_then_events_in_order_and_heartbeats(tmp_path):
    desk, *_ = mkdesk(tmp_path)

    async def go():
        gen = event_stream(desk, heartbeat_s=0.05)
        first = await gen.__anext__()
        desk.publish("fill", {"n": 1})
        desk.publish("result", {"n": 2})
        second, third = await gen.__anext__(), await gen.__anext__()
        hb = await gen.__anext__()
        await gen.aclose()
        return first, second, third, hb, len(desk._subs)

    first, second, third, hb, subs = run(go())
    assert first.startswith("event: state\ndata: {") and first.endswith("\n\n")
    assert second == 'event: fill\ndata: {"n": 1}\n\n'
    assert third == 'event: result\ndata: {"n": 2}\n\n'
    assert hb.startswith("event: heartbeat\ndata: {")
    assert subs == 0                                        # unsubscribed on close


def test_stream_ends_when_the_reader_was_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.trading.SUB_QUEUE_MAX", 2)
    desk, *_ = mkdesk(tmp_path)

    async def go():
        gen = event_stream(desk, heartbeat_s=5)
        await gen.__anext__()
        for i in range(4):
            desk.publish("fill", {"i": i})
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

    run(go())


def test_stream_ends_with_a_marker_when_the_pause_holds_too_much(tmp_path):
    """More than HELD_MAX events held in the pause: the stream ends with an
    SSE comment (no parser turns it into an event), the reader is dropped,
    and the client reconnects for a fresh state."""
    from homebase.desk_api import HELD_MAX
    assert HELD_MAX == 200
    desk, eng, ads, clock, *_ = mkdesk(tmp_path)

    async def go():
        gen = event_stream(desk, heartbeat_s=5, poll_s=0.01)
        await gen.__anext__()                                # the state
        clock.set_et(9, 30)
        for i in range(HELD_MAX):
            desk.publish("result", {"i": i})
        nxt = asyncio.ensure_future(gen.__anext__())
        await asyncio.sleep(0.1)
        assert not nxt.done()                                # 200 held: still open
        desk.publish("result", {"i": HELD_MAX})              # the 201st
        end = await asyncio.wait_for(nxt, 1.0)
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
        return end, len(desk._subs)

    end, subs = run(go())
    assert end.startswith(":") and end.endswith("\n\n") and "\nevent:" not in end
    assert "data:" not in end and subs == 0


def _count_snapshots(desk) -> list:
    calls: list = []
    snap = desk.snapshot

    def counted():
        calls.append(desk.engine.now_et().time())
        return snap()
    desk.snapshot = counted
    return calls


def test_stream_obeys_the_930_pause_but_fills_still_flow(tmp_path):
    """P2: 09:29:50-09:30:30 ET no view is built or serialized for the
    stream; a fill goes out at once; what was held (a state -> a FRESH state,
    then the results in order) goes out when the pause ends."""
    desk, eng, ads, clock, *_ = mkdesk(tmp_path)
    calls = _count_snapshots(desk)
    seen: dict = {}

    async def go():
        gen = event_stream(desk, heartbeat_s=5, poll_s=0.01)
        first = await gen.__anext__()                        # 11:00: the state goes out
        clock.set_et(9, 30)                                  # inside the pause
        assert desk.views_paused()
        desk.publish("result", {"n": 1})
        desk.publish("state", {"stale": True})               # e.g. a Kill in the window
        desk.publish("account", {"id": "a1", "stale": True})
        desk.publish("fill", {"n": 2})
        desk.publish("result", {"n": 3})
        fill = await gen.__anext__()                         # the fill does not wait

        def unpause():
            seen["snapshots_in_pause"] = len(calls)
            clock.set_et(9, 31)
        asyncio.get_running_loop().call_later(0.05, unpause)
        rest = [await gen.__anext__() for _ in range(3)]
        await gen.aclose()
        return first, fill, rest

    first, fill, rest = run(go())
    assert first.startswith("event: state\n")
    assert fill == 'event: fill\ndata: {"n": 2}\n\n'
    assert seen["snapshots_in_pause"] == 1                   # only the 11:00 one
    assert rest[0].startswith("event: state\ndata: {") and '"accounts"' in rest[0] \
        and "stale" not in rest[0]                           # a fresh state, not the held one
    assert rest[1:] == ['event: result\ndata: {"n": 1}\n\n', 'event: result\ndata: {"n": 3}\n\n']
    assert len(calls) == 2


def test_stream_opened_in_the_pause_sends_its_first_state_after_it(tmp_path):
    desk, eng, ads, clock, *_ = mkdesk(tmp_path, et=(9, 30))
    calls = _count_snapshots(desk)
    seen: dict = {}

    async def go():
        gen = event_stream(desk, heartbeat_s=5, poll_s=0.01)
        desk.publish("fill", {"n": 1})                       # the state will carry the desk's fills

        def unpause():
            seen["snapshots_in_pause"] = len(calls)
            clock.set_et(9, 31)
        asyncio.get_running_loop().call_later(0.05, unpause)
        first = await gen.__anext__()
        desk.publish("fill", {"n": 2})
        second = await gen.__anext__()
        await gen.aclose()
        return first, second

    first, second = run(go())
    assert seen["snapshots_in_pause"] == 0
    assert first.startswith("event: state\ndata: {")
    assert second == 'event: fill\ndata: {"n": 2}\n\n'


def test_stream_keeps_its_heartbeat_through_the_pause(tmp_path):
    desk, eng, ads, clock, *_ = mkdesk(tmp_path, et=(9, 30))

    async def go():
        gen = event_stream(desk, heartbeat_s=0.03, poll_s=0.01)
        hb = await gen.__anext__()
        await gen.aclose()
        return hb, len(desk._subs)

    hb, subs = run(go())
    assert hb.startswith("event: heartbeat\n") and subs == 0


# --- the stream over ASGI: disconnects and shutdown never hang ---------------------------
KEY = "ab" * 32


def _stream_app(desk) -> FastAPI:
    app = FastAPI()
    app.state.desk_key = KEY
    app.include_router(trade_router(desk), prefix="/api/trade")
    return app


def _scope(spec: str) -> dict:
    return {"type": "http", "asgi": {"version": "3.0", "spec_version": spec},
            "http_version": "1.1", "method": "GET", "scheme": "http",
            "path": "/api/trade/stream", "raw_path": b"/api/trade/stream", "root_path": "",
            "query_string": b"", "client": ("127.0.0.1", 50000), "server": ("127.0.0.1", 8850),
            "headers": [(b"host", b"127.0.0.1:8850"), (b"x-homebase-key", KEY.encode())]}


@pytest.mark.parametrize("spec", ["2.3", "2.4"])
def test_a_client_disconnect_ends_its_stream_and_its_generator(tmp_path, spec):
    desk, *_ = mkdesk(tmp_path)
    app = _stream_app(desk)

    async def go():
        gone = asyncio.Event()
        sent: list = []
        asked = 0

        async def receive():
            nonlocal asked
            asked += 1
            if asked == 1:
                return {"type": "http.request", "body": b"", "more_body": False}
            await gone.wait()
            return {"type": "http.disconnect"}

        async def send(msg):
            sent.append(msg)
            if msg["type"] == "http.response.body" and msg.get("body"):
                assert len(desk._subs) == 1
                gone.set()                                   # the client goes away

        await asyncio.wait_for(app(_scope(spec), receive, send), 2.0)
        return sent, len(desk._subs)

    sent, subs = run(go())
    assert sent[0]["type"] == "http.response.start" and sent[0]["status"] == 200
    assert sent[1]["body"].startswith(b"event: state\n")
    assert subs == 0                                         # the generator ran its finally


def test_a_client_that_never_reads_blocks_nothing_and_shutdown_ends_it(tmp_path):
    """The socket's buffer is full (send never returns) and no disconnect
    ever comes: publish() still never blocks, and the cancel uvicorn sends
    at --timeout-graceful-shutdown ends the request and closes the generator."""
    desk, *_ = mkdesk(tmp_path)
    app = _stream_app(desk)

    async def go():
        stuck = asyncio.Event()
        asked = 0

        async def receive():
            nonlocal asked
            asked += 1
            if asked == 1:
                return {"type": "http.request", "body": b"", "more_body": False}
            await asyncio.Event().wait()                     # never disconnects

        async def send(msg):
            if msg["type"] == "http.response.body" and msg.get("body"):
                stuck.set()
                await asyncio.Event().wait()                 # never drains

        task = asyncio.create_task(app(_scope("2.3"), receive, send))
        await asyncio.wait_for(stuck.wait(), 2.0)
        for i in range(20):
            desk.publish("fill", {"i": i})                   # sync, never waits on the reader
        subs_while_stuck = len(desk._subs)
        task.cancel()                                        # what the graceful timeout does
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1.0)
        return subs_while_stuck, len(desk._subs)

    stuck_subs, subs = run(go())
    assert stuck_subs == 1 and subs == 0


def test_the_desk_service_bounds_its_graceful_shutdown():
    """An open SSE stream would hold uvicorn's graceful shutdown forever."""
    p = Path(__file__).resolve().parent.parent / "deploy" / "com.ramosquant.homebase.plist.template"
    args = plistlib.loads(p.read_bytes())["ProgramArguments"]
    i = args.index("--timeout-graceful-shutdown")
    assert args[i + 1] == "5"
