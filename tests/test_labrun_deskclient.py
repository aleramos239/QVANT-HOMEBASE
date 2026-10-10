"""The runner's line to the Desk (Step B, task B4): one request, once; the key in one header and nowhere else; a stream
reader and a heartbeat timer that never raise. The Desk here is an httpx mock transport: no socket is opened."""
from __future__ import annotations

import json
import threading

import httpx
import pytest

from homebase.labrun.deskclient import BEAT, INTENT, STREAM, DeskClient

URL = "http://127.0.0.1:8859"
KEY = "ab" * 32
EVENT = {"strategy": "lab_pp", "date": "2024-03-05", "mark": ["x", "y"], "seq": 1, "t_ns": 1,
         "state": {"last_price": 1.0, "last_ms": 1, "prices_late": False},
         "intents": [{"op": "cancel", "id": 1}]}
ANSWER = {"ok": True, "seq": 1, "results": [{"op": "cancel", "id": 1, "refused": None, "accounts": {}}], "brain": None}


def sse(*events) -> bytes:
    return b"".join(f"event: {name}\ndata: {json.dumps(data)}\n\n".encode() for name, data in events)


def make(handler, tmp_path, key=KEY, **kw):
    f = tmp_path / "lab.key"
    if key is not None:
        f.write_text(key + "\n")
    got, seen = [], []

    def served(req):
        seen.append(req)
        return handler(req)
    c = DeskClient(URL, f, got.append, transport=httpx.MockTransport(served), **kw)
    return c, got, seen, f


# ---------------------------------------------------------------- one request, once
def test_an_event_is_posted_once_with_the_key_in_its_header_and_the_answer_comes_back(tmp_path):
    c, _, seen, _ = make(lambda req: httpx.Response(200, json=ANSWER), tmp_path)
    assert c.send(EVENT) == ANSWER
    (req,) = seen
    assert (req.method, req.url.path, req.url.host, req.url.port) == ("POST", INTENT, "127.0.0.1", 8859)
    assert req.headers["x-homebase-key"] == KEY and req.headers["host"] == "127.0.0.1:8859"
    assert "origin" not in req.headers and json.loads(req.content) == EVENT          # the runner is not a browser
    assert KEY not in str(req.url) and KEY not in req.content.decode()               # one header, nowhere else


def test_the_key_is_read_again_at_every_request(tmp_path):
    """The Desk may write a new key when it starts: the runner never keeps one."""
    c, _, seen, f = make(lambda req: httpx.Response(200, json=ANSWER), tmp_path)
    c.send(EVENT)
    f.write_text("cd" * 32 + "\n")
    c.send(EVENT)
    assert [r.headers["x-homebase-key"] for r in seen] == [KEY, "cd" * 32]


@pytest.mark.parametrize("key", [None, "", "not a key", "AB" * 32, "ab" * 31, "ab" * 32 + "\nmore"])
def test_a_key_file_that_does_not_read_sends_nothing_and_never_raises(tmp_path, key):
    c, _, seen, _ = make(lambda req: pytest.fail("a request left without a key"), tmp_path, key=key)
    assert c.send(EVENT) == {"ok": False, "left": False, "status": None, "detail": None}
    assert c.beat({"pid": 1, "strategies": {}}) is None and seen == []


def test_a_key_path_that_is_a_folder_is_only_a_key_that_does_not_read(tmp_path):
    c = DeskClient(URL, tmp_path, lambda item: None, transport=httpx.MockTransport(lambda req: pytest.fail("sent")))
    assert c.send(EVENT)["left"] is False


def boom(exc):
    def handler(req):
        raise exc
    return handler


FAILURES = {
    "refused": boom(httpx.ConnectError("refused")),
    "timed out": boom(httpx.ReadTimeout("no answer")),
    "connect timed out": boom(httpx.ConnectTimeout("no answer")),
    "dropped": boom(httpx.RemoteProtocolError("Server disconnected without sending a response.")),
    "write failed": boom(httpx.WriteError("broken pipe")),
    "500": lambda req: httpx.Response(500, text="Internal Server Error"),
    "502": lambda req: httpx.Response(502),
    "503": lambda req: httpx.Response(503, json={"detail": "the runner's key is not available"}),
    "200 that does not read": lambda req: httpx.Response(200, text="<html>"),
    "200 without ok": lambda req: httpx.Response(200, json={"results": []}),
}


@pytest.mark.parametrize("case", list(FAILURES))
def test_whatever_fails_exactly_one_request_left_and_nothing_raises(tmp_path, case):
    """The Desk is armed: send() never asks twice. What may be asked again is the host's to decide."""
    c, _, seen, _ = make(FAILURES[case], tmp_path)
    got = c.send(EVENT)
    assert got["ok"] is False and got["left"] is True and len(seen) == 1
    assert got["status"] in (None, 200, 500, 502, 503)


def test_a_refusal_carries_the_desks_status_and_its_sentence(tmp_path):
    c, _, _, _ = make(lambda req: httpx.Response(429, json={"detail": "Too many orders at once."}), tmp_path)
    assert c.send(EVENT) == {"ok": False, "left": True, "status": 429, "detail": "Too many orders at once."}
    c, _, _, _ = make(lambda req: httpx.Response(401, json={"detail": ["not", "a", "sentence"]}), tmp_path)
    assert c.send(EVENT) == {"ok": False, "left": True, "status": 401, "detail": None}


def test_the_send_has_its_own_timeout(tmp_path):
    seen = []

    def handler(req):
        seen.append(req.extensions["timeout"])
        return httpx.Response(200, json=ANSWER)
    c, _, _, _ = make(handler, tmp_path)
    c.send(EVENT)
    c.send(EVENT, timeout=1.5)
    assert [t["read"] for t in seen] == [5.0, 1.5] and [t["connect"] for t in seen] == [5.0, 1.5]


# ---------------------------------------------------------------- the heartbeat
def test_a_beat_is_posted_to_the_heartbeat_route_and_its_answer_comes_back(tmp_path):
    answer = {"ok": True, "armed": True, "strategies": {"lab_pp": {"enabled": True, "killed": False, "stopped": None}}}
    c, _, seen, _ = make(lambda req: httpx.Response(200, json=answer), tmp_path)
    body = {"pid": 7, "strategies": {"lab_pp": {"state": "running", "why": None, "mode": "desk"}}}
    assert c.beat(body) == answer
    assert seen[0].url.path == BEAT and json.loads(seen[0].content) == body and seen[0].headers["x-homebase-key"] == KEY
    c, _, _, _ = make(lambda req: httpx.Response(409, json={"detail": "Lab strategies are switched off on this Desk."}), tmp_path)
    assert c.beat(body) is None


class Ticks:
    """threading.Event's wait, counted: the timer's thread without the wait. It stops after `n` rounds."""

    def __init__(self, n):
        self.n, self.waits = n, []

    def wait(self, s):
        self.waits.append(s)
        return len(self.waits) > self.n


def test_the_timer_posts_the_latest_body_every_five_seconds_and_hands_the_answer_on(tmp_path):
    answer = {"ok": True, "armed": False, "strategies": {}}
    c, got, seen, _ = make(lambda req: httpx.Response(200, json=answer), tmp_path)
    stop = Ticks(3)
    c.beats(stop)                                                            # nothing said yet: nothing is posted
    assert seen == [] and stop.waits == [5.0] * 4
    c.say({"pid": 1, "strategies": {"lab_a": {"state": "waiting", "why": None, "mode": "shadow"}}})
    c.say({"pid": 1, "strategies": {"lab_a": {"state": "running", "why": None, "mode": "shadow"}}})
    c.beats(Ticks(2))
    assert [json.loads(r.content)["strategies"]["lab_a"]["state"] for r in seen] == ["running", "running"]
    assert got == [("desk_beat", answer)] * 2


def test_a_runner_whose_own_thread_stands_still_stops_beating(tmp_path):
    """The Desk calls a strategy "Runner down" by its beats alone: a timer that went on for ever would hide a hung
    runner. What the runner said 15 s ago is not posted any more."""
    wall = [100.0]
    c, got, seen, _ = make(lambda req: httpx.Response(200, json={"ok": True, "strategies": {}}), tmp_path,
                           wall=lambda: wall[0])
    c.say({"pid": 1, "strategies": {}})
    wall[0] = 115.0
    c.beats(Ticks(1))
    assert len(seen) == 1
    wall[0] = 115.1
    c.beats(Ticks(3))
    assert len(seen) == 1 and len(got) == 1


def test_a_beat_that_fails_never_ends_the_timer(tmp_path):
    c, got, seen, _ = make(boom(httpx.ConnectError("refused")), tmp_path)
    c.say({"pid": 1, "strategies": {}})
    c.beats(Ticks(3))
    assert len(seen) == 3 and got == []


# ---------------------------------------------------------------- the stream
def reader(bodies, tmp_path, key=KEY):
    """A client whose stream answers with `bodies` in turn (bytes: a 200 stream; an int: that status; an exception:
    raised). It is stopped in the wait that follows the last one."""
    stop, slept = threading.Event(), []
    n = [0]

    def handler(req):
        assert req.method == "GET" and req.url.path == STREAM and req.url.query == b""
        body = bodies[n[0]]
        n[0] += 1
        if isinstance(body, Exception):
            raise body
        if isinstance(body, int):
            return httpx.Response(body)
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    def sleep(s):
        slept.append(s)
        if n[0] == len(bodies):
            stop.set()
    c, got, seen, f = make(handler, tmp_path, key=key, sleep=sleep)
    return c, got, seen, slept, stop


def test_the_stream_hands_on_every_snapshot_then_says_it_is_down_and_asks_again(tmp_path):
    state = {"date": "2024-03-05", "armed": True, "strategies": {"lab_pp": {"strategy": "lab_pp"}}}
    one = {"strategy": "lab_pp", "brain": {"flat": True}}
    c, got, seen, slept, stop = reader([sse(("state", state), ("strategy", one), ("heartbeat", {"ts": 1.5})),
                                        sse(("state", state))], tmp_path)
    c.run(stop)
    assert got == [("desk", "state", state), ("desk", "strategy", one), ("desk", "heartbeat", {"ts": 1.5}),
                   ("desk_down",), ("desk", "state", state), ("desk_down",)]
    assert slept == [1.0, 1.0]                                               # a stream that worked: asked again soon
    assert all(r.headers["x-homebase-key"] == KEY and "origin" not in r.headers and KEY not in str(r.url) for r in seen)


def test_a_desk_that_is_not_there_is_asked_again_with_a_back_off_up_to_thirty_seconds(tmp_path):
    c, got, seen, slept, stop = reader([httpx.ConnectError("refused")] * 3 + [503, 401, 409, 500, sse()], tmp_path)
    c.run(stop)
    assert slept == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0]
    assert got == [("desk_down",)] * 8


def test_a_key_that_does_not_read_opens_no_stream(tmp_path):
    stop, slept = threading.Event(), []

    def sleep(s):
        slept.append(s)
        if len(slept) == 3:
            stop.set()
    c, got, seen, _ = make(lambda req: pytest.fail("a stream was opened without a key"), tmp_path, key=None, sleep=sleep)
    c.run(stop)
    assert seen == [] and got == [("desk_down",)] * 3 and slept == [1.0, 2.0, 4.0]


def test_a_surprise_in_the_stream_never_ends_the_reader_and_never_reaches_the_runner(tmp_path):
    good = {"strategy": "lab_pp"}
    c, got, _, slept, stop = reader([b"event: strategy\ndata: not json\n\n", b"event: strategy\ndata: [1, 2]\n\n",
                                     b"data: {\"no\": \"event name\"}\n\n", b": end: dropped\n\n",
                                     httpx.ReadTimeout("silent for 15 s"), sse(("strategy", good))], tmp_path)
    c.run(stop)
    assert [x for x in got if x[0] == "desk"] == [("desk", "strategy", good)]
    assert got.count(("desk_down",)) == 6 and slept == [1.0, 2.0, 4.0, 8.0, 16.0, 1.0]


def test_the_stream_gives_up_on_fifteen_seconds_of_silence(tmp_path):
    seen = []
    stop = threading.Event()

    def handler(req):
        seen.append(req.extensions["timeout"])
        return httpx.Response(200, content=sse())
    c, _, _, _ = make(handler, tmp_path, sleep=lambda s: stop.set())
    c.run(stop)
    assert seen[0]["read"] == 15.0


def test_a_reader_that_is_told_to_stop_stops_and_says_nothing_more(tmp_path):
    stop = threading.Event()

    def handler(req):
        stop.set()
        return httpx.Response(200, content=sse(("strategy", {"strategy": "lab_pp"})))
    c, got, _, _ = make(handler, tmp_path, sleep=lambda s: pytest.fail("it waited after the stop"))
    c.run(stop)
    assert got == []


# ---------------------------------------------------------------- the key stays in its header
def test_the_key_is_never_logged_and_never_returned(tmp_path, capfd):
    for case in FAILURES:
        c, got, seen, _ = make(FAILURES[case], tmp_path)
        out = c.send(EVENT)
        assert KEY not in json.dumps(out)
    c, got, seen, slept, stop = reader([httpx.ConnectError("refused"), 401, b"event: state\ndata: {bad\n\n", sse()], tmp_path)
    c.run(stop)
    c.say({"pid": 1, "strategies": {}})
    c.beats(Ticks(1))
    err = capfd.readouterr()
    assert "[labrun]" in err.err and "desk: stream" in err.err               # it did log
    assert KEY not in err.err and KEY not in err.out and KEY not in repr(got)
