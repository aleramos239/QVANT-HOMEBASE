"""The book relay (depthrelay.py, 2026-10-19): the Mac's live Level 2 book on the server's charts. RelaySocket as the
md socket Depth subscribes on, and the route end to end: a server app (relay in) gets the book a Mac app's page socket
sends, through /ws/depth-in. Fakes only: no broker, no network."""
from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient

from homebase.charts.depth import Depth
from homebase.charts.depthrelay import RelayFeed, RelaySocket
from tests.charts_util import D, rows, session_ms, write_archive
from tests.test_charts_depth import NQ, FakeWS, ladder, subs
from tests.test_charts_depth_server import LiveFeed, wait_for


H = {"host": "127.0.0.1:8852"}       # a loopback Host, as the pusher sends through its tunnel


def book(root="NQ", ts=1_000, bid=200.0, ask=200.25):
    return {"type": "depth", "root": root, "ts": ts, "bids": [[bid, 5], [bid - 0.25, 7]], "offers": [[ask, 4]]}


def test_the_relay_socket_answers_subscribes_and_turns_books_into_dom_pushes():
    s = RelaySocket()
    assert not s.connected
    got = []
    s.event_handlers.append(got.append)
    s.push(book())                                       # nobody subscribed NQ yet: dropped
    assert got == []
    r = asyncio.run(s.request("md/subscribeDOM", {"symbol": NQ}))
    assert r == {"subscriptionId": 1, "mode": "RealTime"}
    assert asyncio.run(s.request("md/subscribeDOM", {"symbol": NQ}))["subscriptionId"] == 1   # one id per root
    s.push(book())
    assert got == [{"e": "md", "d": {"doms": [{"contractId": 1, "timestamp": 1_000,
                                               "bids": [{"price": 200.0, "size": 5}, {"price": 199.75, "size": 7}],
                                               "offers": [{"price": 200.25, "size": 4}]}]}}]
    s.push({**book(), "ts": None})                       # the Mac lost its book: this one goes through empty
    assert got[-1]["d"]["doms"][0]["bids"] == [] and got[-1]["d"]["doms"][0]["offers"] == []


def test_depth_on_the_relay_has_a_book_only_while_a_pusher_is_attached():
    async def go():
        feed = RelayFeed()
        d = Depth(feed, ("NQ",), wall_ms=lambda: 5_000)
        d.step()
        assert d.subscribed == {}                        # no pusher: disconnected, nothing asked
        feed.ws.pushers = 1
        d.step()
        await d.settle()
        assert d.subscribed == {"NQ": NQ}
        feed.ws.push(book(ts=4_000))
        assert d.books["NQ"].bids == [[200.0, 5], [199.75, 7]] and d.books["NQ"].offers == [[200.25, 4]]
        feed.ws.pushers = 0                              # the pusher went: the book goes with it
        d.step()
        assert d.books == {} and d.subscribed == {}
    asyncio.run(go())


def test_the_pusher_subscribes_a_chart_per_root_and_forwards_only_books():
    from homebase.charts.depthrelay import pump
    sent_src, sent_dst = [], []

    class Sock:
        def __init__(self, frames, sent):
            self.frames, self.sent = frames, sent

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def send(self, raw):
            self.sent.append(raw)

        def __aiter__(self):
            return self._it()

        async def _it(self):
            for f in self.frames:
                yield f
    frames = [json.dumps({"type": "status"}), json.dumps({"type": "history", "id": "relay-NQ", "bars": []}),
              json.dumps(book()), json.dumps({"type": "bar", "id": "relay-NQ", "note": "depth"})]
    socks = {"src": Sock(frames, sent_src), "dst": Sock([], sent_dst)}
    opened = []
    asyncio.run(pump("src", "dst", ["NQ", "ES"], connect=lambda url, **kw: socks[url], on_open=lambda: opened.append(1)))
    assert [json.loads(x) for x in sent_src] == [{"op": "sub", "id": "relay-NQ", "root": "NQ", "spec": "time:60"},
                                                 {"op": "sub", "id": "relay-ES", "root": "ES", "spec": "time:60"}]
    assert sent_dst == [json.dumps(book())] and opened == [1]


def test_the_server_gets_the_macs_book_from_its_page_socket(tmp_path):
    from homebase.charts.server import create_app
    base = tmp_path / "ticks"
    write_archive(base, "NQ", D, "NQZ6", rows(session_ms(D, 9, 29), [200.0 + 0.25 * (i % 4) for i in range(60)]))
    mac_ws = FakeWS()
    mac_feed = LiveFeed(mac_ws)
    kw = dict(roots=["NQ"], base=base, now_ms=lambda: session_ms(D, 9, 45), depth_roots=("NQ",))
    mac = create_app(feed_factory=mac_feed, state=tmp_path / "mac", depth_base=tmp_path / "mac-depth", **kw)
    srv = create_app(feed_factory=LiveFeed(FakeWS()), state=tmp_path / "srv", depth_base=tmp_path / "srv-depth",
                     depth_relay_in=True, **kw)
    with TestClient(mac, base_url="http://127.0.0.1:8852") as m, TestClient(srv, base_url="http://127.0.0.1:8852") as s:
        wait_for(lambda: subs(mac_ws) == [NQ])
        # a browser (any Origin) is refused; the Mac (no relay in) takes no pushes at all
        for c, hdr in ((s, {**H, "origin": "http://127.0.0.1:8852"}), (m, H)):
            try:
                with c.websocket_connect("/ws/depth-in", headers=hdr) as w:
                    w.receive_text()
                raise AssertionError("/ws/depth-in accepted it")
            except AssertionError:
                raise
            except Exception:  # noqa: BLE001 — closed with 1008
                pass
        assert s.get("/api/status").json()["depth"]["NQ"]["subscribed"] is False
        with m.websocket_connect("/ws", headers=H) as page, s.websocket_connect("/ws/depth-in", headers=H) as inn:
            page.send_json({"op": "sub", "id": "relay-NQ", "root": "NQ", "spec": "time:60"})   # what the pusher sends
            wait_for(lambda: s.get("/api/status").json()["depth"]["NQ"]["subscribed"])
            for _ in range(50):
                if page.receive_json().get("type") == "history":
                    break
            mac_feed.q.put(lambda: mac_ws.push(111, ladder(200.0, 25), ladder(200.25, 18, down=False)))
            for _ in range(200):
                msg = page.receive_json()
                if msg.get("type") == "depth" and msg.get("ts") is not None:
                    break
            inn.send_json(msg)                           # and what it forwards
            wait_for(lambda: s.get("/api/status").json()["depth"]["NQ"]["levels"] == [20, 18])
        wait_for(lambda: s.get("/api/status").json()["depth"]["NQ"]["subscribed"] is False)   # pusher gone: no book


def test_one_machine_holds_the_live_login_the_server():
    """The owner, 2026-10-19 ("can we switch that around"): the always-on server's charts hold the live login (Level 2);
    the Mac's run demo-only and take the server's book. Both on live kicked each other off every ~5 min."""
    import plistlib
    from pathlib import Path
    deploy = Path(__file__).resolve().parent.parent / "deploy"
    mac = plistlib.loads((deploy / "com.ramosquant.homebase-charts.plist.template").read_bytes())["EnvironmentVariables"]
    assert mac == {"HOMEBASE_CHARTS_MD": "demo", "HOMEBASE_CHARTS_MD_ONLY": "demo", "HOMEBASE_DEPTH_RELAY_IN": "1"}
    srv = [ln for ln in (deploy / "linux" / "homebase-charts.service").read_text().splitlines() if ln.startswith("Environment=")]
    assert srv == ["Environment=HOMEBASE_CHARTS_MD=live"]
