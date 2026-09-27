"""The chart service with the desk link wired in: hello, fan-out, quotes
from the ticks, the proxy. The real desk is never reached (MockTransport)."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import queue

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

from homebase.charts.desk import NO_LINK, DeskLink
from homebase.charts.server import create_app
from tests.charts_util import D, rows, session_ms
from tests.test_charts_server import archive, next_of

KEY = "cd" * 32
BASE_URL = "http://127.0.0.1:8852"      # the Host guard refuses TestClient's default "testserver"
WS_HOST = {"host": "127.0.0.1:8852"}    # base_url is a no-op for websocket_connect (starlette
                                         # hardcodes ws://testserver): the Host header for /ws must
                                         # be passed explicitly instead


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


def live_app(tmp_path, **kw):
    return create_app(roots=["NQ"], base=tmp_path / "ticks", feed_factory=QuietFeed,
                      now_ms=lambda: session_ms(D, 9, 45), state=tmp_path / "state", **kw)


def key_file(tmp_path):
    p = tmp_path / "desk.key"
    p.write_text(KEY)
    return p


def test_without_a_desk_link_the_page_is_told_and_the_proxy_answers_503(tmp_path):
    with TestClient(live_app(tmp_path), base_url=BASE_URL) as c:
        with c.websocket_connect("/ws", headers=WS_HOST) as ws:
            assert ws.receive_json()["type"] == "status"
            assert ws.receive_json() == {"type": "desk", "down": NO_LINK}
        assert c.post("/api/desk/order", json={}).status_code == 503


def test_replay_never_links_to_the_desk(tmp_path):
    called = []
    app = create_app(roots=["NQ"], base=archive(tmp_path), replay=D, speed=50,
                     state=tmp_path / "state", desk_factory=lambda fan: called.append(1))
    with TestClient(app, base_url=BASE_URL) as c:
        assert c.post("/api/desk/order", json={}).status_code == 503
    assert called == []


def test_desk_state_fans_out_to_the_page(tmp_path):
    async def body():
        yield b'event: state\ndata: {"enabled": true, "accounts": [], "bot": {}}\n\n'
        await asyncio.Event().wait()                     # the stream stays open

    def handler(req):
        return httpx.Response(200, content=body(), headers={"content-type": "text/event-stream"})

    kp = key_file(tmp_path)
    app = live_app(tmp_path, desk_factory=lambda fan: DeskLink(
        fan, key_path=kp, transport=httpx.MockTransport(handler)))
    with TestClient(app, base_url=BASE_URL) as c, c.websocket_connect("/ws", headers=WS_HOST) as ws:
        for _ in range(400):
            m = ws.receive_json()
            if m.get("type") == "desk" and m.get("event") == "state":
                break
        else:
            raise AssertionError("no desk state reached the page")
    assert m["data"]["enabled"] is True


def test_quotes_reach_the_page_as_of_the_last_trade(tmp_path):
    with TestClient(live_app(tmp_path), base_url=BASE_URL) as c, c.websocket_connect("/ws", headers=WS_HOST) as ws:
        QuietFeed.last.q.put(("NQ", "NQZ6", rows(session_ms(D, 9, 40), [100.0, 100.25])))
        m = next_of(ws, "quote", limit=400)
    assert m == {"type": "quote", "root": "NQ", "bid": 100.0, "ask": 100.25, "last": 100.25,
                 "ts_ms": session_ms(D, 9, 40) + 1000, "asof": "last_trade"}


def test_proxy_checks_origin_size_and_forwards_with_our_quotes(tmp_path):
    posted = []

    def handler(req):
        if req.method == "GET":
            return httpx.Response(200, content=b'event: state\ndata: {"accounts": [], "bot": {}}\n\n',
                                  headers={"content-type": "text/event-stream"})
        posted.append((req.url.path, req.headers.get("x-homebase-key"), json.loads(req.content)))
        return httpx.Response(200, json={"results": {}})

    kp = key_file(tmp_path)
    app = live_app(tmp_path, desk_factory=lambda fan: DeskLink(
        fan, key_path=kp, transport=httpx.MockTransport(handler)))
    with TestClient(app, base_url=BASE_URL) as c:
        assert c.post("/api/desk/order", json={"x": 1},
                      headers={"origin": "https://evil.example"}).status_code == 403
        assert c.post("/api/desk/bogus", json={}).status_code == 404
        assert c.post("/api/desk/order",
                      content=b"{" + b" " * 5000 + b"}",
                      headers={"content-type": "application/json"}).status_code == 413
        assert c.post("/api/desk/order", content=b"[1]",
                      headers={"content-type": "application/json"}).status_code == 400
        r = c.post("/api/desk/order", json={"client_id": "c", "quotes": {"NQ": {"last": 1}}},
                   headers={"origin": "http://localhost:8852"})
        assert r.status_code == 200 and r.json() == {"results": {}}
    path, key, body = posted[-1]
    assert (path, key) == ("/api/trade/order", KEY)
    assert body == {"client_id": "c", "quotes": {}}           # the page's own quotes are replaced


def test_no_cors_middleware_on_the_chart_service(tmp_path):
    """netguard.origin_allowed (used by the /api/desk proxy and browser_write_ok's
    same-origin rule) ignores an Origin's port, so any page served from an
    allowed host may write -- safe ONLY because this service adds no CORS
    middleware: no page on another origin can ever read the response back."""
    app = live_app(tmp_path)
    assert not any(m.cls is CORSMiddleware for m in app.user_middleware)


from homebase.charts import __main__ as charts_main


def test_the_fake_desk_link_is_refused_outside_replay(tmp_path):
    with pytest.raises(ValueError):
        live_app(tmp_path, fake_desk_factory=lambda fan: None)


@pytest.mark.parametrize("argv", [["--fake-desk", "8859"],                              # no --replay
                                  ["--replay", "2026-09-22", "--fake-desk", "8850"]])   # the real desk's port
def test_the_cli_refuses_a_fake_desk_without_replay_or_on_the_real_port(argv):
    with pytest.raises(SystemExit):
        charts_main.main(argv)


def test_replay_links_to_the_fake_desk_and_sends_it_quotes(tmp_path):
    posted = []

    async def sse_body():
        yield b'event: state\ndata: {"enabled": true, "accounts": [], "bot": {}}\n\n'
        await asyncio.Event().wait()

    def handler(req):
        if req.method == "GET":
            return httpx.Response(200, content=sse_body(), headers={"content-type": "text/event-stream"})
        posted.append(json.loads(req.content))
        return httpx.Response(200, json={"results": {}})

    kp = key_file(tmp_path)
    app = create_app(roots=["NQ"], base=archive(tmp_path), replay=D, speed=50, start_et=dt.time(9, 30),
                     state=tmp_path / "state", fake_desk_factory=lambda fan: DeskLink(
                         fan, key_path=kp, url="http://127.0.0.1:8859", transport=httpx.MockTransport(handler)))
    with TestClient(app, base_url=BASE_URL) as c, c.websocket_connect("/ws", headers=WS_HOST) as ws:
        assert next_of(ws, "quote", limit=2000)["root"] == "NQ"
        assert c.post("/api/desk/order", json={"client_id": "c"}).status_code == 200
    assert "NQ" in posted[-1]["quotes"]
