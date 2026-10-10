"""The runner's line to the Desk: the guarded intake of a promoted strategy's orders (Step B, task B4; 2026-10-10).

The Desk (homebase/desk_api.py, labdesk_router) has four routes for the runner and nothing else. DeskClient speaks
three of them, and only when the runner was started with --desk:

    GET  /api/lab/stream       read by run() in a thread of its own: whole snapshots, never an edge (level triggered)
    POST /api/lab/intent       send(): ONE event of one strategy -- its orders, or the runner's own `stop`
    POST /api/lab/heartbeat    beat(): who is hosted, every 5 s, from beats() in a thread of its own

    put(("desk", event, data))     every stream event as it arrives: "state" (every Lab strategy, whole), "strategy"
                                   (one, whole), "heartbeat" (the stream is alive)
    put(("desk_down",))            the stream ended or could not be opened; it is asked again (1 s to 30 s)
    put(("desk_beat", answer))     the Desk's answer to a beat

NOTHING HERE EVER SENDS A REQUEST TWICE. send() is one POST: no retry on a timeout, a dropped connection or an error
answer -- the Desk is armed, and an entry that is sent again is a second order. What may be asked again (a cancel, a
flatten, a stop) is the host's to decide (labrun/host.py), with the entries taken out.

The key (the Desk's lab.key) is read from its file at every request, because the Desk may write a new one when it
starts. It travels in one header and nowhere else: never in a URL, a log line, the store or what send() returns. A key
file that cannot be read means no request leaves: the answer says so (`left` False) and nothing raises.

The threads here only ever put on the runner's queue: an error in one never raises into the runner.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import threading
import time
from pathlib import Path

import httpx

STREAM, INTENT, BEAT = "/api/lab/stream", "/api/lab/intent", "/api/lab/heartbeat"
KEY_HEADER = "X-Homebase-Key"
SEND_S = 5.0                     # one request's answer (the Desk may hold an entry 2 s for the 9:30 orders)
READ_S = 15.0                    # the stream says it is alive every 5 s: this long with nothing and it is down
BACKOFF_S = (1.0, 30.0)
BEAT_S = 5.0
BEAT_FRESH_S = 15.0              # a heartbeat body older than this is not posted: the runner's own thread has stopped
_KEY = re.compile(r"[0-9a-f]{64}")   # what the Desk writes (desk_api.ensure_key)


def log(msg: str) -> None:
    print(f"[labrun] {dt.datetime.now().strftime('%H:%M:%S')} {msg}", file=sys.stderr, flush=True)


class _Down(Exception):
    """The stream cannot be read just now; str(e) is our own words (never the Desk's bytes, never a header)."""


def _failed(left: bool, status: int | None = None, detail: str | None = None) -> dict:
    return {"ok": False, "left": left, "status": status, "detail": detail}


class DeskClient:
    """url: the Desk on this machine (python -m homebase.labrun checks it); key_path: its lab.key; put: the runner's
    queue. transport / sleep / wall: the tests'."""

    def __init__(self, url: str, key_path, put, *, transport=None, sleep=time.sleep, wall=time.monotonic):
        self._key_path, self._put, self._sleep, self._wall = Path(key_path), put, sleep, wall
        self._http = httpx.Client(base_url=url, transport=transport, trust_env=False, follow_redirects=False,
                                  timeout=httpx.Timeout(SEND_S))
        self._said: tuple | None = None              # (the heartbeat body, when the runner last set it)

    def _key(self) -> str | None:
        """The key as the file holds it now; None when it cannot be read or is not a key."""
        try:
            key = self._key_path.read_text(encoding="utf-8").strip()
        except (OSError, ValueError):
            return None
        return key if _KEY.fullmatch(key) else None

    # ---- one request, once
    def _post(self, path: str, body: dict, timeout: float) -> dict:
        key = self._key()
        if key is None:
            return _failed(False)
        try:
            r = self._http.post(path, json=body, headers={KEY_HEADER: key}, timeout=httpx.Timeout(timeout))
        except Exception as e:  # noqa: BLE001 -- a timeout, a refused or dropped connection: no answer
            log(f"desk: {path}: {type(e).__name__}")
            return _failed(True)
        try:
            got = r.json()
        except ValueError:
            got = None
        if r.status_code == 200 and isinstance(got, dict) and got.get("ok") is True:
            return got
        detail = got.get("detail") if isinstance(got, dict) else None
        return _failed(True, r.status_code, detail if isinstance(detail, str) else None)

    def send(self, body: dict, timeout: float = SEND_S) -> dict:
        """One event to the Desk, ONCE. The Desk's answer ({"ok": True, "seq", "results", "brain"}), or
        {"ok": False, "left", "status", "detail"}: `left` False = no request left this process (the key file does not
        read); `status` = the Desk's HTTP status when it answered at all (429: too many, 4xx: refused whole), None
        when no answer came (a timeout, a dropped connection); `detail` its sentence, if it sent one."""
        return self._post(INTENT, body, timeout)

    def beat(self, body: dict, timeout: float = SEND_S) -> dict | None:
        """One heartbeat; the Desk's answer, or None."""
        got = self._post(BEAT, body, timeout)
        return got if got.get("ok") is True else None

    # ---- the heartbeat's own timer
    def say(self, body: dict) -> None:
        """The runner's thread: what the next beats carry. It must keep saying it: a body that is BEAT_FRESH_S old is
        not posted any more, so a runner whose own thread stands still reads "Runner down" on the Desk."""
        self._said = (body, self._wall())

    def beats(self, stop: threading.Event, every: float = BEAT_S) -> None:
        """Its own thread: the latest body, every 5 s -- also while the runner's thread waits for the Desk's answer
        to an event (an event is not a beat). Never raises."""
        while not stop.wait(every):
            try:
                said = self._said
                if said is None or self._wall() - said[1] > BEAT_FRESH_S:
                    continue
                got = self.beat(said[0])
                if got is not None:
                    self._put(("desk_beat", got))
            except Exception as e:  # noqa: BLE001
                log(f"desk: heartbeat: {type(e).__name__}")

    # ---- the stream
    def _once(self, stop: threading.Event) -> bool:
        """One connection. True when it carried anything."""
        key = self._key()
        if key is None:
            raise _Down("the key file does not read")
        got = False
        with self._http.stream("GET", STREAM, headers={KEY_HEADER: key},
                               timeout=httpx.Timeout(10.0, read=READ_S)) as r:
            if r.status_code != 200:
                raise _Down(f"the Desk answered {r.status_code}")
            event = ""
            for line in r.iter_lines():
                if stop.is_set():
                    return got
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data = json.loads(line[5:])
                    if event and isinstance(data, dict):
                        self._put(("desk", event, data))
                        got = True
                elif not line:
                    event = ""
        return got

    def run(self, stop: threading.Event) -> None:
        """Its own thread: the stream, again and again. Never raises, never ends before `stop`."""
        wait = BACKOFF_S[0]
        while not stop.is_set():
            ok = False
            try:
                ok = self._once(stop)
            except Exception as e:  # noqa: BLE001 -- say so (in our own words only), wait, ask again
                log(f"desk: stream: {e if isinstance(e, _Down) else type(e).__name__}")
            if stop.is_set():
                break
            self._put(("desk_down",))
            if ok:                                   # a stream that worked: ask again soon
                wait = BACKOFF_S[0]
                self._sleep(wait)
            else:                                    # each failure in a row waits twice as long
                self._sleep(wait)
                wait = min(wait * 2, BACKOFF_S[1])
