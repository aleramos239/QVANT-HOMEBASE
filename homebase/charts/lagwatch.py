"""Names what holds the chart service when it stops answering.

On 2026-10-11 ~22:25 the Charts page went black ("chart service unreachable") for a minute or two with the
process at 99% CPU and 4.5-5 GB resident, then recovered by itself. Nothing in the log said what ran. This
watches the event loop from a plain thread: the loop re-arms a timer every BEAT_S; when that timer is late by
more than LAG_S, every thread's stack is written to the log (idle pool workers left out), at most once per
QUIET_S. It reads frames and never touches the loop, so it cannot make a stall worse.
"""
from __future__ import annotations

import sys
import threading
import time
import traceback
from typing import Callable

BEAT_S = 0.5
LAG_S = 3.0
QUIET_S = 60.0
DEPTH = 8                   # innermost frames kept per thread
_IDLE_FILES = ("threading.py", "queue.py", "selectors.py", "_base_events.py")


def _where(fs: traceback.FrameSummary) -> str:
    name = fs.filename.replace("\\", "/")
    for marker in ("/homebase/", "/site-packages/", "/lib/python3"):
        if marker in name:
            name = name.split(marker, 1)[1]
            break
    return f"{name}:{fs.lineno} {fs.name}"


def snapshot(skip_ident: int | None = None) -> list[str]:
    """One line per busy thread: its name, then its innermost frames (outermost first)."""
    names = {t.ident: t.name for t in threading.enumerate()}
    lines = []
    for ident, frame in sys._current_frames().items():
        if ident == skip_ident:
            continue
        stack = traceback.extract_stack(frame)
        if not stack:
            continue
        top = stack[-1]
        if top.filename.endswith(_IDLE_FILES) and ident != threading.main_thread().ident:
            continue                # a worker parked on its queue / a lock
        req = _request_path(frame)
        lines.append(f"{names.get(ident, ident)}{' [' + req + ']' if req else ''}: "
                     + " > ".join(_where(f) for f in stack[-DEPTH:]))
    return lines


def _request_path(frame) -> str | None:
    """The HTTP request a thread is serving, if one of its frames holds a Starlette `request`: the stack of a
    response being encoded is all framework code, so without this a stall does not say which route it was."""
    while frame is not None:
        try:
            r = frame.f_locals.get("request")
            scope = getattr(r, "scope", None)
            if isinstance(scope, dict) and scope.get("type") == "http":
                q = scope.get("query_string", b"")
                return f"{scope.get('method', '?')} {scope.get('path', '?')}" + (f"?{q.decode('latin-1')[:80]}" if q else "")
        except Exception:  # noqa: BLE001
            pass
        frame = frame.f_back
    return None


def start(loop, log: Callable[[str], None], *, lag_s: float = LAG_S, beat_s: float = BEAT_S,
          quiet_s: float = QUIET_S) -> threading.Thread:
    """Arm the beat on `loop` and start the watching thread (a daemon: it never blocks a stop)."""
    seen = [time.monotonic()]

    def beat() -> None:
        seen[0] = time.monotonic()
        loop.call_later(beat_s, beat)

    loop.call_soon_threadsafe(beat)

    def watch() -> None:
        last = -quiet_s
        me = threading.get_ident()
        while True:
            time.sleep(beat_s / 2)
            if loop.is_closed():
                return
            if not loop.is_running():       # stopped (shutdown, a test's client): no beat is due
                seen[0] = time.monotonic()
                continue
            now = time.monotonic()
            lag = now - seen[0] - beat_s
            if lag > lag_s and now - last >= quiet_s:
                last = now
                try:
                    log(f"event loop late by {lag:.1f} s -- busy threads:")
                    for ln in snapshot(me):
                        log("  " + ln)
                except Exception:  # noqa: BLE001 — a diagnostic must never raise
                    pass

    t = threading.Thread(target=watch, name="lagwatch", daemon=True)
    t.start()
    return t
