"""POST /api/tester/show: Claude's "show on chart" -- guards, validation, and the /ws broadcast."""
from __future__ import annotations

import datetime as dt
import time

from fastapi.testclient import TestClient

from homebase.charts.server import create_app
from tests.backtest_util import D1, nq_archive

RUN = {"strategy": "nq930", "inputs": {"adx_gate": False},
       "range": {"kind": "custom", "start": "2024-03-01", "end": "2024-03-31"}}
WS = {"host": "127.0.0.1:8852"}
LOCAL = {"origin": "http://127.0.0.1:8852"}


def client(tmp_path):
    app = create_app(roots=["NQ"], base=nq_archive(tmp_path / "ticks"), replay=D1, speed=1,
                     start_et=dt.time(9, 30), state=tmp_path / "state")
    return TestClient(app, base_url="http://127.0.0.1:8852")


def done_run(c) -> str:
    rid = c.post("/api/tester/run", json=RUN).json()["id"]
    t = time.monotonic() + 30
    while c.get(f"/api/tester/run/{rid}").json()["status"] not in ("done", "error", "cancelled"):
        assert time.monotonic() < t
        time.sleep(0.05)
    return rid


def recv_type(ws, kind, n=50):
    for _ in range(n):
        m = ws.receive_json()
        if m.get("type") == kind:
            return m
    raise AssertionError(f"no {kind} message")


def test_show_broadcasts_to_every_open_backtest_page_and_not_to_charts(tmp_path):
    """2026-09-28 three-tabs plan: the Strategy Tester lives on the Backtest tab only now, so
    show_on_chart targets connections that identified themselves as /ws?page=backtest -- never a
    plain /ws (Charts tab) connection, even though it is also open."""
    with client(tmp_path) as c:
        rid = done_run(c)
        with c.websocket_connect("/ws", headers=WS) as charts_page, \
             c.websocket_connect("/ws?page=backtest", headers=WS) as bt_a, \
             c.websocket_connect("/ws?page=backtest", headers=WS) as bt_b:
            r = c.post("/api/tester/show", json={"run_id": rid, "focus": {"trade_index": 0}}, headers=LOCAL)
            assert r.status_code == 200 and r.json() == {"ok": True, "pages": 2, "run_id": rid,
                                                         "focus": {"trade_index": 0}}
            for ws in (bt_a, bt_b):
                assert recv_type(ws, "tester_show") == {"type": "tester_show", "run_id": rid,
                                                        "focus": {"trade_index": 0}}
            # the Charts-tab connection is untouched by the broadcast: still just its own initial status
            assert charts_page.receive_json()["type"] == "status"


def test_show_with_no_page_open_says_zero(tmp_path):
    with client(tmp_path) as c:
        rid = done_run(c)
        r = c.post("/api/tester/show", json={"run_id": rid})      # no Origin at all: not a browser, allowed
        assert r.status_code == 200 and r.json()["pages"] == 0


def test_show_validates_the_run_and_the_focus(tmp_path):
    with client(tmp_path) as c:
        rid = done_run(c)
        assert c.post("/api/tester/show", json={"run_id": "20240101-000000-nq930-abcd"}).status_code == 404
        assert c.post("/api/tester/show", json={"run_id": "../../etc"}).status_code == 404
        assert c.post("/api/tester/show", json={"grid_id": "20240101-000000-nq930-abcd", "cell": 0}).status_code == 404
        for bad in ({}, {"run_id": rid, "grid_id": "x", "cell": 0}, {"grid_id": "x"}, {"run_id": rid, "extra": 1},
                    {"run_id": rid, "focus": {"trade_index": -1}}, {"run_id": rid, "focus": {"date": "03/05/2024"}},
                    {"run_id": rid, "focus": {"trade_index": 0, "date": "2024-03-05"}},
                    {"run_id": rid, "focus": {"trade_index": True}}, {"run_id": rid, "focus": {"price": 1}}):
            assert c.post("/api/tester/show", json=bad).status_code in (400, 404), bad
        ok = c.post("/api/tester/show", json={"run_id": rid, "focus": {"date": "2024-03-05"}})
        assert ok.status_code == 200 and ok.json()["focus"] == {"date": "2024-03-05"}


def test_show_refuses_a_run_that_is_not_done(tmp_path):
    with client(tmp_path) as c:
        rid = done_run(c)
        st = tmp_path / "state" / "tester" / "runs" / rid / "status.json"
        st.write_text('{"status": "running"}')
        r = c.post("/api/tester/show", json={"run_id": rid})
        assert r.status_code == 409 and "running" in r.json()["detail"]


def test_show_is_json_only_and_behind_the_host_and_origin_guards(tmp_path):
    with client(tmp_path) as c:
        rid = done_run(c)
        body = f'{{"run_id": "{rid}"}}'
        assert c.post("/api/tester/show", content=body, headers={"content-type": "text/plain"}).status_code == 415
        assert c.post("/api/tester/show", content=body).status_code == 415          # no content type at all
        assert c.post("/api/tester/show", json={"run_id": rid},
                      headers={"origin": "https://evil.example"}).status_code == 403
        assert c.post("/api/tester/show", json={"run_id": rid}, headers={"host": "evil.example"}).status_code == 403
        assert c.post("/api/tester/show", json={"run_id": rid},
                      headers={"host": "evil.example", "origin": "http://evil.example"}).status_code == 403


def test_show_is_refused_in_the_930_window(tmp_path, monkeypatch):
    from homebase.backtest import slots
    with client(tmp_path) as c:
        rid = done_run(c)
        monkeypatch.setattr(slots, "et_now", lambda: dt.datetime(2026, 9, 28, 9, 29, tzinfo=slots.ET))
        r = c.post("/api/tester/show", json={"run_id": rid}, headers=LOCAL)
        assert r.status_code == 409 and "09:20" in r.json()["detail"]
        monkeypatch.setattr(slots, "et_now", lambda: dt.datetime(2026, 9, 27, 9, 29, tzinfo=slots.ET))  # a Sunday
        assert c.post("/api/tester/show", json={"run_id": rid}, headers=LOCAL).status_code == 200


def test_focus_date_is_strictly_yyyy_mm_dd(tmp_path):
    with client(tmp_path) as c:
        rid = done_run(c)
        for bad in ("20240304", "2024-W10-1", "2024-3-4", "2024-02-30", 20240304):
            assert c.post("/api/tester/show", json={"run_id": rid, "focus": {"date": bad}}).status_code == 400, bad
