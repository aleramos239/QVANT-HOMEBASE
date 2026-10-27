"""A history / scroll-back message's text made a piece at a time (routes/ws.py encode_in_steps) is byte for byte what
starlette's send_json makes of it, everything but its sealed bars is read when the writer takes it (as send_json read
it), and it goes out in its place in the socket's queue."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import math

from fastapi.testclient import TestClient

import homebase.charts.routes.ws as ws_mod
from homebase.charts.bars import Bar
from homebase.charts.routes.ws import Big, Conn, encode_in_steps, history_message
from homebase.charts.server import create_app
from tests.test_charts_hub import D, open_stream, setup, ticks_of
from tests.test_charts_server import archive, next_of


def send_json_text(msg) -> str:      # starlette WebSocket.send_json
    return json.dumps(msg, separators=(",", ":"), ensure_ascii=False)


def test_encode_in_steps_is_send_json_byte_for_byte(monkeypatch):
    bars = [{"t": 1.5, "fp": [[1.25, 2, 3]]}, [], {}, "é✓\u2028", math.nan, -0.0]
    studies = {"vwap": [None, math.nan, math.inf, -0.0]}
    cases = [       # (what is sent, made fresh each round: its iterators are read once; what send_json was sent)
        (lambda: {}, {}),
        (lambda: {"type": "history", "id": "c1", "bars": []}, {"type": "history", "id": "c1", "bars": []}),
        (lambda: {"type": "history", "id": "c1", "bars": iter([])}, {"type": "history", "id": "c1", "bars": []}),
        (lambda: Big({"type": "history", "bars": iter(bars), "live": True}, [{"c": math.inf}]),
         {"type": "history", "bars": [*bars, {"c": math.inf}], "live": True}),
        (lambda: Big({"type": "history", "bars": iter([])}, [{"c": 1}]), {"type": "history", "bars": [{"c": 1}]}),
        (lambda: {"type": "older", "id": "é✓", "before": 1, "bars": iter(bars), "studies": studies, "done": True,
                  "text": "a\"b\\c\n "},
         {"type": "older", "id": "é✓", "before": 1, "bars": bars, "studies": studies, "done": True,
          "text": "a\"b\\c\n "}),
        (lambda: {"x": [1, [2, [3]], {"k": [4]}], "y": None, "z": [math.nan]},
         {"x": [1, [2, [3]], {"k": [4]}], "y": None, "z": [math.nan]}),
        (lambda: {1: "int key", "a": [1]}, {1: "int key", "a": [1]}),     # a key json turns to text: the one-call path
        (lambda: Big({"bars": iter([1]), None: 2}, [3]), {"bars": [1, 3], None: 2}),
        (lambda: {"t": (1, 2)}, {"t": (1, 2)}),                            # a tuple is a list to json
    ]
    for step in (ws_mod.STEP_S, 0.0):               # 0: the loop is let in after every item
        monkeypatch.setattr(ws_mod, "STEP_S", step)
        for sent, want in cases:
            assert asyncio.run(encode_in_steps(sent())) == send_json_text(want), want


def test_a_history_message_is_its_payloads_send_json_text(tmp_path, monkeypatch):
    monkeypatch.setattr(ws_mod, "STEP_S", 0.0)
    hub, today, _ = setup(tmp_path)
    hub.start_today("NQ", D, ticks_of(today[:60]), {"date": D.isoformat(), "contract": "NQZ6",
                                                    "source": "live", "approx": False, "gaps": []})
    s = open_stream(hub, keys=("vwap", "cumdelta", "profile"))
    assert s.builder.cur is not None and len(s.bars) > 1      # closed bars and a live one
    for fp, big, flow in [(True, True, True), (False, True, False), (True, False, True), (False, False, False)]:
        want = send_json_text({"type": "history", "id": "c1", **s.payload(fp, big, flow)})
        m = history_message("c1", s.payload(fp, big, flow))
        assert len(m.tail) == 1                               # the live bar: made when the writer takes it
        assert asyncio.run(encode_in_steps(m)) == want
    p = {"bars": [{"c": 1}, {"c": 2}], "live": False}         # no live bar: every bar is a sealed one
    m = history_message("c2", p)
    assert m.tail == [] and asyncio.run(encode_in_steps(m)) == send_json_text({"type": "history", "id": "c2", **p})


def test_a_closed_bar_that_fails_to_wire_answers_an_error_and_the_page_goes_on(tmp_path, monkeypatch):
    """Bar.wire raising on a sealed bar (in ws_endpoint, as before) answers that chart an error, leaves it unsubscribed,
    and the socket keeps serving: the next sub gets its history."""
    orig, armed = Bar.wire, [True]

    def wire(self, *a, **k):
        if armed[0] and self.closed:
            armed[0] = False
            raise AttributeError("wire boom")
        return orig(self, *a, **k)
    monkeypatch.setattr(Bar, "wire", wire)
    app = create_app(roots=["NQ"], base=archive(tmp_path), replay=D, speed=50, start_et=dt.time(9, 30),
                     state=tmp_path / "state")
    with TestClient(app, base_url="http://127.0.0.1:8852") as client, \
            client.websocket_connect("/ws", headers={"host": "localhost:8852"}) as ws:
        ws.send_json({"op": "sub", "id": "a", "root": "NQ", "spec": "time:60"})
        assert next_of(ws, "error") == {"type": "error", "id": "a", "error": "wire boom"}
        ws.send_json({"op": "sub", "id": "b", "root": "NQ", "spec": "time:60"})
        seen = []
        for _ in range(200):
            m = ws.receive_json()
            seen.append((m.get("type"), m.get("id")))
            if seen[-1] == ("history", "b"):
                break
        assert seen[-1] == ("history", "b"), seen
        assert ("update", "a") not in seen and ("history", "a") not in seen, seen   # "a" was left unsubscribed


def test_all_but_the_sealed_bars_is_read_when_the_writer_takes_the_message(monkeypatch):
    monkeypatch.setattr(ws_mod, "STEP_S", 0.0)

    async def run():
        sessions, live = [{"d": 1}], {"c": 1, "big": [[1]]}

        async def beside():                     # the pump and the feed, while the bars' text is being made
            await asyncio.sleep(0)
            sessions.append({"d": 2})
            live["big"].append([2])
        task = asyncio.ensure_future(beside())
        text = await encode_in_steps(Big({"bars": iter(range(20)), "sessions": sessions}, [live]))
        await task
        return text
    assert asyncio.run(run()) == '{"bars":[' + ",".join(map(str, range(20))) + ',{"c":1,"big":[[1]]}],"sessions":[{"d":1}]}'


class FakeWS:
    def __init__(self):
        self.out: list = []

    async def send_json(self, m):
        self.out.append(send_json_text(m))

    async def send_text(self, t):
        self.out.append(t)


def test_conn_sends_a_big_message_in_its_place_in_the_queue_and_lets_the_loop_in(monkeypatch):
    monkeypatch.setattr(ws_mod, "STEP_S", 0.0)

    async def run():
        ws, other = FakeWS(), []
        conn = Conn(ws)

        async def beside():                  # other loop work, while the big text is being made
            for i in range(3):
                other.append(len(ws.out))
                await asyncio.sleep(0)
        conn.send({"type": "a"})
        conn.send(Big({"type": "history", "id": "c", "bars": iter([{"i": i} for i in range(50)])}, [{"i": 50}]))
        conn.send({"type": "update", "id": "c"})
        conn.send(Big({"type": "older", "id": "c", "bars": iter([])}))
        await asyncio.gather(beside(), *(asyncio.sleep(0) for _ in range(3)))
        for _ in range(500):
            if len(ws.out) == 4:
                break
            await asyncio.sleep(0)
        conn.task.cancel()
        return ws.out, other
    out, other = asyncio.run(run())
    assert out == ['{"type":"a"}', '{"type":"history","id":"c","bars":[' + ",".join(f'{{"i":{i}}}' for i in range(51)) + "]}",
                   '{"type":"update","id":"c"}', '{"type":"older","id":"c","bars":[]}']
    assert other[-1] <= 1, other             # it ran while the history was still being made


def test_a_big_text_no_longer_lets_the_loop_in_once_its_queue_is_half_full(monkeypatch):
    monkeypatch.setattr(ws_mod, "STEP_S", 0.0)

    async def run():
        other = asyncio.ensure_future(asyncio.sleep(0))      # other loop work, waiting for its turn
        text = await encode_in_steps({"bars": iter(range(100))}, room=lambda: False)
        return text, other.done()
    text, other_ran = asyncio.run(run())
    assert text == '{"bars":[' + ",".join(map(str, range(100))) + "]}" and not other_ran
