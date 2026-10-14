"""GET /api/book/history: the recorded depth files + the tick archive replayed through BookTracker (bookhist.py),
behind the same host guard, paused windows and 503-while-busy as /api/depth/history. Synthetic files in tmp dirs."""
from __future__ import annotations

import gzip
import json
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from homebase.charts import bookhist
from homebase.charts.bookhist import MAX_SPAN_MS
from homebase.charts.server import create_app
from tests.charts_util import D, rows, session_ms, write_archive
from tests.test_charts_desk_server import QuietFeed

T0 = session_ms(D, 10, 0)
TICK = 0.25
BASE_URL = "http://127.0.0.1:8852"


def levels(bid, big=None):
    big = big or {}
    return ([[bid - i * TICK, big.get(("b", i), 10)] for i in range(10)],
            [[bid + TICK + i * TICK, big.get(("a", i), 10)] for i in range(10)])


def write_day(tmp_path):
    lines = []
    for s in range(60):
        b, a = levels(100.0, {("b", 2): 300} if 20 <= s < 30 else None)
        lines.append({"t": T0 + s * 1000, "b": b, "a": a})
    p = tmp_path / "depth" / "NQ" / str(D.year) / f"{D.isoformat()}_NQZ6.depth.jsonl.gz"
    p.parent.mkdir(parents=True)
    p.write_bytes(gzip.compress("".join(json.dumps(x) + "\n" for x in lines).encode()))
    prints = rows(T0 + 25_000, [99.5] * 4, step_ms=100, size=160, spread=0.25, first_id=1, sides=[-1] * 4)
    write_archive(tmp_path / "ticks", "NQ", D, "NQZ6", prints)


def app_at(tmp_path, now_ms):
    return create_app(roots=["NQ"], base=tmp_path / "ticks", feed_factory=QuietFeed, now_ms=lambda: now_ms,
                      state=tmp_path / "state", depth_base=tmp_path / "depth",
                      depth_executor=lambda: ThreadPoolExecutor(max_workers=1))


def test_the_route_serves_samples_and_the_traded_episode(tmp_path):
    write_day(tmp_path)
    bookhist._BOOKS.clear()
    app = app_at(tmp_path, T0 + 3_600_000)
    with TestClient(app, base_url=BASE_URL) as c:
        r = c.get("/api/book/history", params={"root": "nq", "from_ms": T0, "to_ms": T0 + 60_000})
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
        body = r.json()
        assert body["tick"] == TICK and body["step"] == 1000 and len(body["samples"]) == 60
        ep = [e for e in body["episodes"] if e["p"] == 99.5]
        assert len(ep) == 1 and ep[0]["s"] == "b" and ep[0]["tr"] == 640 and ep[0]["end"] == "traded"


def test_the_route_refuses_bad_hosts_roots_and_ranges(tmp_path):
    write_day(tmp_path)
    app = app_at(tmp_path, T0 + 3_600_000)
    with TestClient(app, base_url=BASE_URL) as c:
        ok = {"root": "NQ", "from_ms": T0, "to_ms": T0 + 1000}
        assert c.get("/api/book/history", params=ok, headers={"host": "evil.example"}).status_code == 403
        assert c.get("/api/book/history", params={**ok, "root": "ZZ"}).status_code == 404
        for bad in ({"root": "NQ"}, {"root": "NQ", "from_ms": "x", "to_ms": T0}, {"root": "NQ", "from_ms": -1, "to_ms": T0},
                    {"root": "NQ", "from_ms": T0, "to_ms": T0},
                    {"root": "NQ", "from_ms": T0 - MAX_SPAN_MS - 1, "to_ms": T0},
                    {"root": "NQ", "from_ms": T0, "to_ms": T0 + 3_600_000 + 86_400_001}):
            assert c.get("/api/book/history", params=bad).status_code == 400, bad


def test_the_route_answers_503_in_the_paused_windows(tmp_path):
    write_day(tmp_path)
    for now, why in ((session_ms(D, 8, 30, 10), "paused for the 8:30 data release"),):
        app = app_at(tmp_path, now)
        with TestClient(app, base_url=BASE_URL) as c:
            r = c.get("/api/book/history", params={"root": "NQ", "from_ms": T0 - 3_600_000, "to_ms": T0})
            assert r.status_code == 503 and r.json()["detail"] == why


def test_the_route_is_not_paused_in_the_930_window(tmp_path):
    """09:20-09:35 ET is no longer a paused window for book history (2026-10-12): a request at 09:25 is served."""
    write_day(tmp_path)
    app = app_at(tmp_path, session_ms(D, 9, 25))
    with TestClient(app, base_url=BASE_URL) as c:
        r = c.get("/api/book/history", params={"root": "NQ", "from_ms": T0 - 3_600_000, "to_ms": T0})
        assert r.status_code != 503, r.text


def test_a_root_with_no_recorded_depth_is_an_empty_window_not_an_error(tmp_path):
    app = app_at(tmp_path, T0 + 3_600_000)
    with TestClient(app, base_url=BASE_URL) as c:
        r = c.get("/api/book/history", params={"root": "NQ", "from_ms": T0, "to_ms": T0 + 60_000})
        assert r.status_code == 200 and r.json()["samples"] == [] and r.json()["episodes"] == []


def test_a_page_gets_bookflow_right_after_history_and_then_the_live_samples(tmp_path):
    from tests.test_charts_depth import FakeWS, ladder
    from tests.test_charts_depth_server import LiveFeed, wait_for
    ws = FakeWS()
    feed = LiveFeed(ws)
    write_archive(tmp_path / "ticks", "NQ", D, "NQZ6", rows(session_ms(D, 9, 29), [200.0 + 0.25 * (i % 4) for i in range(60)]))
    clk = [session_ms(D, 9, 45)]            # the service's clock: depth throttles its lines by it, so it must move
    app = create_app(roots=["NQ"], base=tmp_path / "ticks", feed_factory=feed, now_ms=lambda: clk[0],
                     state=tmp_path / "state", depth_roots=("NQ",), depth_base=tmp_path / "depth")
    with TestClient(app, base_url=BASE_URL) as client:
        wait_for(lambda: len(ws.sent) > 0)
        with client.websocket_connect("/ws", headers={"host": "localhost:8852"}) as page:
            page.send_json({"op": "sub", "id": "a", "root": "NQ", "spec": "time:60"})
            seen = []
            for _ in range(100):
                seen.append(page.receive_json().get("type"))
                if "bookflow" in seen:
                    break
            assert "history" in seen and seen.index("history") < seen.index("bookflow")
            for sec in (0, 1, 2, 3):
                feed.q.put(lambda s=sec: (clk.__setitem__(0, session_ms(D, 9, 45, s)),
                                          ws.push(111, ladder(200.0, 25, size=5 + s), ladder(200.25, 18, down=False),   # top 10 must differ
                                                  ts=f"2026-09-24T13:45:0{s}.000Z")))
            got = []
            for _ in range(400):
                m = page.receive_json()
                if m.get("type") == "bookflow" and m.get("samples"):
                    got = m["samples"]
                    break
            assert got and m["root"] == "NQ" and not m.get("reset")


def test_a_book_line_late_by_less_than_the_grace_does_not_make_a_second_sample_for_its_second(tmp_path):
    """The pump's flush runs behind the clock by CLOSE_GRACE_MS (like the hub's bar close): a line stamped in second S
    that arrives 1.5 s of wall time after S began must land in S's one sample, not re-open S after it was committed."""
    import time
    from tests.test_charts_depth import FakeWS, ladder
    from tests.test_charts_depth_server import LiveFeed, wait_for
    ws = FakeWS()
    feed = LiveFeed(ws)
    write_archive(tmp_path / "ticks", "NQ", D, "NQZ6", rows(session_ms(D, 9, 29), [200.0 + 0.25 * (i % 4) for i in range(60)]))
    s0 = session_ms(D, 9, 45)
    clk = [s0]

    def push(at_ms, stamp_ms, size):
        def go():
            clk[0] = at_ms
            iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(stamp_ms // 1000)) + f".{stamp_ms % 1000:03d}Z"
            ws.push(111, ladder(200.0, 25, size=size), ladder(200.25, 18, down=False), ts=iso)
        feed.q.put(go)

    app = create_app(roots=["NQ"], base=tmp_path / "ticks", feed_factory=feed, now_ms=lambda: clk[0],
                     state=tmp_path / "state", depth_roots=("NQ",), depth_base=tmp_path / "depth")
    with TestClient(app, base_url=BASE_URL) as client:
        wait_for(lambda: len(ws.sent) > 0)
        with client.websocket_connect("/ws", headers={"host": "localhost:8852"}) as page:
            page.send_json({"op": "sub", "id": "a", "root": "NQ", "spec": "time:60"})
            while page.receive_json().get("type") != "bookflow":
                pass
            push(s0 + 100, s0 + 100, 25)           # opens second S
            time.sleep(0.6)
            clk[0] = s0 + 1500                     # S is over; without a grace the pump's flush commits it here
            time.sleep(0.6)
            push(s0 + 1750, s0 + 900, 26)          # a line stamped in S arrives 1.75 s on: inside the grace
            time.sleep(0.6)
            clk[0] = s0 + 4000                     # now S is well past its grace: the pump commits it, once
            time.sleep(0.9)
        with client.websocket_connect("/ws", headers={"host": "localhost:8852"}) as page:
            page.send_json({"op": "sub", "id": "b", "root": "NQ", "spec": "time:60"})
            m = {}
            while m.get("type") != "bookflow":
                m = page.receive_json()
    ts = [r[0] for r in m["samples"]]
    assert s0 in ts and len(ts) == len(set(ts)), ts
