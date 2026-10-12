import asyncio
import threading
import time

from homebase.charts import lagwatch


def _blocking_work(seconds: float) -> None:
    time.sleep(seconds)


def test_a_stalled_loop_logs_the_busy_threads_once():
    lines: list[str] = []

    async def run():
        lagwatch.start(asyncio.get_running_loop(), lines.append, lag_s=0.3, beat_s=0.05, quiet_s=30)
        await asyncio.sleep(0.2)            # beating: no report
        assert lines == []
        _blocking_work(1.0)                 # the loop thread stalls
        await asyncio.sleep(0.2)

    asyncio.run(run())
    assert lines and lines[0].startswith("event loop late by ")
    assert any("_blocking_work" in ln for ln in lines[1:])      # the stack names what held the loop
    assert sum(ln.startswith("event loop late") for ln in lines) == 1   # one report per quiet window


def test_a_healthy_loop_logs_nothing():
    lines: list[str] = []

    async def run():
        lagwatch.start(asyncio.get_running_loop(), lines.append, lag_s=0.3, beat_s=0.05, quiet_s=30)
        await asyncio.sleep(0.6)

    asyncio.run(run())
    assert lines == []


def test_snapshot_skips_the_given_thread_and_parked_workers():
    stop = threading.Event()
    t = threading.Thread(target=stop.wait, name="parked")
    t.start()
    try:
        time.sleep(0.05)
        out = lagwatch.snapshot(skip_ident=threading.get_ident())
        assert not any(ln.startswith("parked:") for ln in out)
    finally:
        stop.set()
        t.join()


def test_snapshot_names_the_request_a_thread_is_serving():
    class _Req:
        scope = {"type": "http", "method": "GET", "path": "/api/some/route", "query_string": b"a=1"}

    seen = threading.Event()

    def handler(request):                    # a framework frame holding `request`, busy in its own code
        seen.set()
        time.sleep(0.6)

    t = threading.Thread(target=handler, args=(_Req(),), name="serving")
    t.start()
    try:
        seen.wait(2)
        out = lagwatch.snapshot(skip_ident=threading.get_ident())
    finally:
        t.join()
    mine = [ln for ln in out if ln.startswith("serving [GET /api/some/route?a=1]")]
    assert mine
