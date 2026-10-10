"""The runner's tick client: the chart service's read-only stream, and nothing else (2026-10-09).

GET /api/labrun/ticks on the chart service (homebase/charts/server.py, TickFan) is Server-Sent Events: the backlog, then
`live`, then the live batches and a clock every second. TickClient reads it in its own thread and hands what it carries
to the runner (labrun/host.py). This is the only connection the runner process opens.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import threading
import time

import httpx

from ..backtest.tape import ET

STREAM = "/api/labrun/ticks"
BACKOFF_S = (1.0, 30.0)


def log(msg: str) -> None:
    print(f"[labrun] {dt.datetime.now(ET).strftime('%H:%M:%S')} {msg}", file=sys.stderr, flush=True)


def _midnight_ms(now_ms: int) -> int:
    d = dt.datetime.fromtimestamp(now_ms / 1000, ET).date()
    return int(dt.datetime.combine(d, dt.time(0), ET).timestamp() * 1000)


class _Again(Exception):
    """Ask the stream again, at once."""


class TickClient:
    """Reads GET /api/labrun/ticks (Server-Sent Events) and hands put() what it carries: ("clock", now_ms) and
    ("ticks", root, [[ts_ms, price, size], ...]). It reconnects with back-off (1 s to 30 s), asks for since_ms = 00:00
    ET today on the first connect and the oldest of its newest-print times after that, and never takes a print twice:
    per market, a row older than its newest time is dropped, and of the rows AT its newest time the first k are
    dropped, k being how many it already holds at that millisecond. The only connection this process opens."""

    def __init__(self, url: str, roots, put, *, transport=None, sleep=time.sleep, wall_ms=lambda: int(time.time() * 1000)):
        self._roots, self._put, self._sleep = roots, put, sleep
        self._http = httpx.Client(base_url=url, transport=transport, trust_env=False, follow_redirects=False,
                                  timeout=httpx.Timeout(10.0, read=15.0))   # the stream's clock ticks every second
        self._day = _midnight_ms(wall_ms())          # 00:00 ET of the day it asks for
        self._newest: dict[str, list] = {}           # root -> [its newest print's ms, how many it holds at that ms]
        self._skip: dict[str, int] = {}              # root -> rows at that ms still to drop on this connection

    def reconnected(self) -> None:
        self._skip = {r: n for r, (_, n) in self._newest.items()}

    def fresh(self, root: str, rows) -> list:
        """The rows not held yet."""
        ms, n = self._newest.get(root, (-1, 0))
        skip = self._skip.get(root, 0)
        out = []
        for r in rows:
            t = r[0]
            if t < ms:
                continue
            if t > ms:
                ms, n, skip = t, 0, 0
            elif skip:
                skip -= 1
                continue
            n += 1
            out.append(r)
        self._newest[root], self._skip[root] = [ms, n], skip
        return out

    def since_ms(self, roots) -> int:
        return min([self._newest[r][0] if r in self._newest else self._day for r in roots], default=self._day)

    def _once(self, stop: threading.Event) -> bool:
        """One connection. True when it carried anything."""
        roots = self._roots()
        self.reconnected()
        got = False
        with self._http.stream("GET", STREAM, params={"roots": ",".join(roots), "since_ms": self.since_ms(roots)}) as r:
            if r.status_code != 200:
                raise ValueError(f"the chart service answered {r.status_code}")
            event = ""
            for line in r.iter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    if stop.is_set():
                        return got
                    if self._roots() != roots:
                        raise _Again()
                    self._on(event, json.loads(line[5:]))
                    got = True
                elif not line:
                    event = ""
        return got

    def _on(self, event: str, data: dict) -> None:
        if event == "clock":
            day = _midnight_ms(data["now_ms"])
            earlier, self._day = day < self._day, day
            if earlier:                              # a replayed session: another timeline, asked again from ITS
                self._newest.clear()                 # midnight (what is held from the later day says nothing here)
                raise _Again()
            self._put(("clock", data["now_ms"]))
        elif not event:
            rows = self.fresh(data["root"], data["rows"])
            if rows:
                self._put(("ticks", data["root"], rows))

    def run(self, stop: threading.Event) -> None:
        wait = BACKOFF_S[0]
        while not stop.is_set():
            try:
                ok = self._once(stop)
            except _Again:
                continue
            except Exception as e:  # noqa: BLE001 -- the reader's thread must never end: say so, wait, ask again
                ok = False
                log(f"stream: {type(e).__name__}: {e}")
            if stop.is_set():
                break
            if ok:                                   # a stream that worked: try again soon
                wait = BACKOFF_S[0]
                self._sleep(wait)
            else:                                    # each failure in a row waits twice as long
                self._sleep(wait)
                wait = min(wait * 2, BACKOFF_S[1])
