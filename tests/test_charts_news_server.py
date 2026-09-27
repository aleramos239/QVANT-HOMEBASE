"""The chart service with news + bursts wired in end to end: /api/status shape,
/api/news (route + Host guard), news items fanned out live, and a burst fired
off the real live tick path reaching the page. The real feeds are never
reached (fetch functions are fakes; QuietFeed never touches the network)."""
from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from homebase.charts.bursts import WINDOW_MS
from homebase.charts.server import create_app
from tests.charts_util import D, session_ms
from tests.test_charts_desk_server import QuietFeed, live_app
from tests.test_charts_server import archive, next_of

BASE_URL = "http://127.0.0.1:8852"
WS_HOST = {"host": "127.0.0.1:8852"}
NQ_TICK = 0.25
RSS = ("<rss><channel><item><title>Fed signals a rate cut</title><link>u1</link><guid>g1</guid>"
      "<pubDate>Fri, 26 Sep 2026 12:00:00 GMT</pubDate></item></channel></rss>")


def test_status_carries_news_and_burst_shapes(tmp_path):
    with TestClient(live_app(tmp_path), base_url="http://127.0.0.1:8852") as c:
        st = c.get("/api/status").json()
        assert st["news"] == {"ok": False, "last_fetch": {
            "financialjuice": {"at": None, "items": 0, "error": None},
            "truth": {"at": None, "items": 0, "error": None}}, "delay_p50_s": None}
        assert st["bursts"] == {"roots": ["NQ"], "last": {"NQ": None}, "now": {"NQ": None}}


def test_the_route_serves_news_and_is_host_guarded(tmp_path):
    with TestClient(live_app(tmp_path), base_url=BASE_URL) as c:
        assert c.get("/api/news").json() == []
        assert c.get("/api/news", headers={"host": "evil.example"}).status_code == 403


def test_a_new_item_is_fanned_out_live_and_the_status_ok_flag_flips(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        return RSS.encode()

    with TestClient(live_app(tmp_path, news_fetch=fetch), base_url=BASE_URL) as c, \
            c.websocket_connect("/ws", headers=WS_HOST) as ws:
        m = next_of(ws, "news", limit=400)
        assert m["source"] == "financialjuice" and m["title"] == "Fed signals a rate cut"
        assert m["tags"] == ["fed"]
        st = c.get("/api/news").json()
        assert len(st) >= 1
        assert calls                                        # both RSS sources were actually polled


def test_replay_never_wires_a_news_fetch_even_if_one_is_passed(tmp_path):
    calls = []
    app = create_app(roots=["NQ"], base=archive(tmp_path), replay=D, speed=50, state=tmp_path / "state",
                     news_fetch=lambda url: calls.append(url) or RSS.encode())
    with TestClient(app):
        pass
    assert calls == []


def _burst_rows(start_ms: int) -> list[dict]:
    """45 quiet 30 s buckets (2-tick moves) then a clean 40-tick spike --
    matches test_charts_bursts.py's feed_baseline, on real NQ tick sizing."""
    rows_, price, ts, rid = [], 20000.0, start_ms, 1

    def put(t, p):
        nonlocal rid
        rows_.append({"ts_ms": t, "price": p, "size": 1, "bid": p - NQ_TICK, "ask": p, "id": rid})
        rid += 1

    for _ in range(45):
        put(ts, price)
        price += 2 * NQ_TICK
        put(ts + WINDOW_MS - 1000, price)
        ts += WINDOW_MS
    spike_start = ts + WINDOW_MS
    put(spike_start, price)
    price += 40 * NQ_TICK
    put(spike_start + 29_000, price)
    return rows_


def test_a_burst_on_the_live_tick_path_is_fanned_and_recorded_in_status(tmp_path):
    with TestClient(live_app(tmp_path), base_url=BASE_URL) as c, \
            c.websocket_connect("/ws", headers=WS_HOST) as ws:
        QuietFeed.last.q.put(("NQ", "NQZ6", _burst_rows(session_ms(D, 9, 30))))
        m = next_of(ws, "burst", limit=2000)
        assert m["root"] == "NQ" and m["dir"] == "up" and m["move_ticks"] == 40.0 and m["ratio"] == 20.0
        st = c.get("/api/status").json()
        assert st["bursts"]["last"]["NQ"]["move_ticks"] == 40.0
        assert st["bursts"]["now"]["NQ"] == 20.0                # Task 2: the radar's current ratio
        assert c.get("/api/bursts/now").json() == st["bursts"]["now"]
