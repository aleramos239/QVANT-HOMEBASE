"""Recorder: dedupe, per-session files, crash safety, gaps; refill paging."""
from __future__ import annotations

import asyncio
import datetime as dt
import gzip
import json
import os
import time

from homebase import ticks as T
from homebase.charts import recorder as recorder_module
from homebase.charts.recorder import LiveRecorder, refill
from homebase.charts.store import TickStore, read_table
from tests.charts_util import D, rows, session_ms, write_archive

M = session_ms(D, 9, 30)


def run(coro):
    return asyncio.run(coro)


async def nosleep(_s):
    return None


def later(monkeypatch, s=recorder_module.REPAIR_RETRY_S):
    """Run the recorder's clock s seconds ahead of real time."""
    monkeypatch.setattr(recorder_module, "monotonic", lambda: time.monotonic() + s)


def test_append_dedupes_and_flush_writes_a_readable_file(tmp_path):
    rec = LiveRecorder(tmp_path)
    r = rows(M, [100.0, 100.25, 100.5])
    assert len(rec.append("NQ", "NQZ6", r[:2])) == 2
    assert len(rec.append("NQ", "NQZ6", r)) == 1          # r0, r1 already held
    assert rec.buffered == 3
    assert rec.flush() == 3 and rec.buffered == 0
    rec.append("NQ", "NQZ6", rows(M + 5_000, [101.0], first_id=4))
    rec.flush()
    s = TickStore(tmp_path).load("NQ", D)
    assert [t.id for t in s.ticks] == [1, 2, 3, 4] and s.source == "live"


def test_rows_file_by_their_own_session(tmp_path):
    rec = LiveRecorder(tmp_path)
    nxt = D + dt.timedelta(days=1)
    rec.append("NQ", "NQZ6", rows(session_ms(D, 16, 59), [1.0]) + rows(session_ms(nxt, 18, 1), [2.0], first_id=9))
    rec.flush()
    assert rec.path("NQ", D, "NQZ6").exists() and rec.path("NQ", nxt, "NQZ6").exists()


def test_a_restart_remembers_ids_and_the_last_tick(tmp_path):
    rec = LiveRecorder(tmp_path)
    rec.append("NQ", "NQZ6", rows(M, [100.0, 100.25]))
    rec.flush()
    again = LiveRecorder(tmp_path)
    assert again.last_ts("NQ", D, "NQZ6") == M + 1000
    assert again.append("NQ", "NQZ6", rows(M, [100.0, 100.25])) == []


def test_a_torn_first_member_is_set_aside(tmp_path):
    rec = LiveRecorder(tmp_path)
    p = rec.path("NQ", D, "NQZ6")
    p.parent.mkdir(parents=True)
    p.write_bytes(gzip.compress(b"ts_ms,price,size,bid,ask,bid_size,ask_size,id\n1,2,3,,,,,4\n")[:12])
    assert rec.append("NQ", "NQZ6", rows(M, [100.0])) != []
    rec.flush()
    assert p.with_name(p.name + ".corrupt").exists()
    header, recs = read_table(p)
    assert header and len(recs) == 1


def test_a_restart_repairs_a_torn_later_member(tmp_path):
    rec = LiveRecorder(tmp_path)
    rec.append("NQ", "NQZ6", rows(M, [100.0, 100.25]))
    rec.flush()                                              # member 1: ids 1, 2 (good)
    rec.append("NQ", "NQZ6", rows(M + 2_000, [100.5, 100.75], first_id=3))
    rec.flush()                                              # member 2: ids 3, 4 (good)
    p = rec.path("NQ", D, "NQZ6")
    torn = gzip.compress(f"{M + 5_000},101.0,1,,,,,5\n".encode())
    with open(p, "ab") as fh:
        fh.write(torn[: len(torn) // 2])                     # crash mid third flush (id 5 lost)

    again = LiveRecorder(tmp_path)
    again.append("NQ", "NQZ6", rows(M + 8_000, [102.0], first_id=6))
    again.flush()

    s = TickStore(tmp_path).load("NQ", D)
    assert [t.id for t in s.ticks] == [1, 2, 3, 4, 6]


def test_a_failing_repair_on_open_degrades_like_a_failing_flush(tmp_path, monkeypatch):
    rec = LiveRecorder(tmp_path)
    rec.append("NQ", "NQZ6", rows(M, [100.0, 100.25]))
    rec.flush()                                              # member 1: ids 1, 2 (good)
    rec.append("NQ", "NQZ6", rows(M + 2_000, [100.5, 100.75], first_id=3))
    rec.flush()                                              # member 2: ids 3, 4 (good)
    p = rec.path("NQ", D, "NQZ6")
    torn = gzip.compress(f"{M + 5_000},101.0,1,,,,,5\n".encode())
    with open(p, "ab") as fh:
        fh.write(torn[: len(torn) // 2])                     # a torn third member (crash)

    def fail_replace(*a, **kw):
        raise OSError(28, "No space left on device")

    with monkeypatch.context() as m:
        m.setattr(os, "replace", fail_replace)               # the disk is still full on restart

        by_last_ts = LiveRecorder(tmp_path)
        assert by_last_ts.last_ts("NQ", D, "NQZ6") == M + 3_000  # doesn't raise
        assert by_last_ts.error is not None

        again = LiveRecorder(tmp_path)
        assert again.append("NQ", "NQZ6", rows(M + 8_000, [102.0], first_id=6)) != []
        assert again.error is not None
        assert again.buffered == 1

        assert again.flush() == 0 and again.buffered == 1 and again.error is not None

    later(monkeypatch)                                       # the retry is due (REPAIR_RETRY_S)
    assert again.flush() == 1 and again.error is None        # the disk recovers
    s = TickStore(tmp_path).load("NQ", D)
    assert [t.id for t in s.ticks] == [1, 2, 3, 4, 6]


def test_flush_retries_a_pending_repair_with_no_buffered_rows(tmp_path, monkeypatch):
    setup = LiveRecorder(tmp_path)
    setup.append("NQ", "NQZ6", rows(M, [100.0, 100.25]))
    setup.flush()                                            # member 1: ids 1, 2 (good)
    setup.append("NQ", "NQZ6", rows(M + 2_000, [100.5, 100.75], first_id=3))
    setup.flush()                                            # member 2: ids 3, 4 (good)
    nq_p = setup.path("NQ", D, "NQZ6")
    torn = gzip.compress(f"{M + 5_000},101.0,1,,,,,5\n".encode())
    with open(nq_p, "ab") as fh:
        fh.write(torn[: len(torn) // 2])                     # a torn third member (crash)

    def fail_replace(*a, **kw):
        raise OSError(28, "No space left on device")

    rec = LiveRecorder(tmp_path)                             # fresh: no cached state for the NQ path

    with monkeypatch.context() as m:
        m.setattr(os, "replace", fail_replace)

        assert rec.last_ts("NQ", D, "NQZ6") == M + 3_000      # repair fails; nothing buffered for NQ
        assert rec.error is not None
        assert rec.buffered == 0

        rec.append("ES", "ESZ6", rows(M, [4_500.0]))          # an unrelated, healthy contract
        assert rec.flush() == 1                               # the ES row is written
        assert rec.error is not None                          # the NQ path is still torn -- must not clear

    later(monkeypatch)                                        # the retry is due (REPAIR_RETRY_S)
    assert rec.flush() == 0                                   # nothing buffered; only a pending repair to retry
    assert rec.error is None
    assert not rec._needs_repair
    gzip.decompress(nq_p.read_bytes())                        # now one clean member, no torn tail
    s = TickStore(tmp_path).load("NQ", D)
    assert [t.id for t in s.ticks] == [1, 2, 3, 4]


def test_a_failed_write_mid_member_is_repaired_on_the_retry(tmp_path, monkeypatch):
    rec = LiveRecorder(tmp_path)
    rec.append("NQ", "NQZ6", rows(M, [100.0, 100.25]))
    rec.flush()                                              # member 1: ids 1, 2 (good)
    rec.append("NQ", "NQZ6", rows(M + 2_000, [100.5], first_id=3))

    real_open = open

    class HalfWrite:
        """Writes half its bytes to the real file, then blows up -- like a
        disk-full write that a moment later has room again."""

        def __init__(self, path, mode):
            self._fh = real_open(path, mode)

        def write(self, data):
            self._fh.write(data[: len(data) // 2])
            raise OSError("simulated disk full")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._fh.close()
            return False

    with monkeypatch.context() as m:
        m.setattr(recorder_module, "open", lambda p, mode: HalfWrite(p, mode), raising=False)
        assert rec.flush() == 0 and rec.error and rec.buffered == 1

    later(monkeypatch)                                       # the retry is due (REPAIR_RETRY_S)
    assert rec.flush() == 1 and rec.error is None
    s = TickStore(tmp_path).load("NQ", D)
    assert [t.id for t in s.ticks] == [1, 2, 3]


def test_a_failed_flush_keeps_the_rows(tmp_path, monkeypatch):
    blocker = tmp_path / "NQ"
    blocker.write_text("not a directory")
    rec = LiveRecorder(tmp_path)
    rec.append("NQ", "NQZ6", rows(M, [100.0]))
    assert rec.flush() == 0 and rec.error and rec.buffered == 1
    blocker.unlink()
    later(monkeypatch)                                       # the retry is due (REPAIR_RETRY_S)
    assert rec.flush() == 1 and rec.error is None


def test_mark_gap_is_read_back_by_the_store(tmp_path):
    rec = LiveRecorder(tmp_path)
    rec.append("NQ", "NQZ6", rows(M, [100.0]))
    rec.flush()
    rec.mark_gap("NQ", D, "NQZ6", 1, 2)
    rec.mark_gap("NQ", D, "NQZ6", 3, 4)
    assert TickStore(tmp_path).load("NQ", D).gaps == [[1, 2], [3, 4]]


def test_the_gaps_sidecar_is_never_taken_for_an_archive_manifest(tmp_path):
    """Research loaders (research/flow.py) glob <ROOT>/*/*.json as the
    nightly archive's manifests and call .get() on each: a gaps list saved
    as .json broke load_flow for that root after the first marked gap."""
    write_archive(tmp_path, "NQ", D - dt.timedelta(days=1), "NQZ6", rows(M, [1.0]))
    rec = LiveRecorder(tmp_path)
    rec.append("NQ", "NQZ6", rows(M, [100.0]))
    rec.flush()
    rec.mark_gap("NQ", D, "NQZ6", 1, 2)
    manifests = list((tmp_path / "NQ").glob("*/*.json"))
    assert all(isinstance(json.loads(m.read_text()), dict) for m in manifests)
    assert len(manifests) == 1
    assert rec.path("NQ", D, "NQZ6").with_name(f"{D}_NQZ6.live.gaps").exists()


def pager(all_rows, page=3, penalty_first=False):
    calls = []

    async def page_fn(ws, contract, before, ticket=None):
        calls.append((before, ticket))
        if penalty_first and len(calls) == 1:
            raise T.Penalty({"p-ticket": "tk", "p-time": 1})
        return [r for r in all_rows if r["ts_ms"] <= before][-page:]
    return page_fn, calls


def test_refill_covers_the_gap_oldest_first():
    rs = rows(M, [100 + 0.25 * i for i in range(10)])
    fn, _ = pager(rs)
    got, reached = run(refill(None, "NQZ6", M + 2000, M + 9000, page_fn=fn, sleep=nosleep))
    assert [r["ts_ms"] for r in got] == [M + i * 1000 for i in range(3, 9)]
    assert reached <= M + 2000


def test_refill_stops_at_the_page_cap_and_reports_the_rest():
    rs = rows(M, [100 + 0.25 * i for i in range(10)])
    fn, calls = pager(rs)
    counted = []
    got, reached = run(refill(None, "NQZ6", M + 2000, M + 9000, page_fn=fn, sleep=nosleep,
                              max_pages=2, on_request=lambda: counted.append(1)))
    assert [r["ts_ms"] for r in got] == [M + i * 1000 for i in range(5, 9)]
    assert reached == M + 5000 and len(calls) == 2 and len(counted) == 2


def test_refill_honors_a_penalty_ticket():
    rs = rows(M, [100.0, 100.25, 100.5])
    fn, calls = pager(rs, penalty_first=True)
    got, _ = run(refill(None, "NQZ6", M - 1, M + 3000, page_fn=fn, sleep=nosleep))
    assert calls[1][1] == "tk" and len(got) == 3


def torn_day_file(tmp_path):
    """A live file whose last member a crash tore (ids 1-4 intact)."""
    setup = LiveRecorder(tmp_path)
    setup.append("NQ", "NQZ6", rows(M, [100.0, 100.25, 100.5, 100.75]))
    setup.flush()
    p = setup.path("NQ", D, "NQZ6")
    torn = gzip.compress(f"{M + 5_000},101.0,1,,,,,5\n".encode())
    with open(p, "ab") as fh:
        fh.write(torn[: len(torn) // 2])
    return p


def test_the_clean_check_streams_instead_of_inflating_the_whole_file(tmp_path, monkeypatch):
    """gzip.decompress() on the recorder's one-member-per-second day file is
    pathological (10.5 s for one NQ day of 57k members; 0.46 s streamed) and
    ran on the event loop at startup and on every flush while a write failed."""
    def whole_file(*a, **k):
        raise AssertionError("the clean check inflated the whole file in one call")

    rec = LiveRecorder(tmp_path)
    for i in range(50):                                      # 50 flushes = 50 gzip members
        rec.append("NQ", "NQZ6", rows(M + i * 1000, [100.0], first_id=i + 1))
        rec.flush()
    p = rec.path("NQ", D, "NQZ6")
    before = p.read_bytes()
    monkeypatch.setattr(gzip, "decompress", whole_file)
    LiveRecorder(tmp_path).last_ts("NQ", D, "NQZ6")          # first touch: the clean check
    assert p.read_bytes() == before                          # clean: left untouched
    torn = torn_day_file(tmp_path / "torn")
    LiveRecorder(tmp_path / "torn").last_ts("NQ", D, "NQZ6")
    assert [t.id for t in TickStore(tmp_path / "torn").load("NQ", D).ticks] == [1, 2, 3, 4]
    assert gzip.open(torn).read()                            # repaired: one clean member


def test_a_failing_repair_is_retried_at_most_every_30_s(tmp_path, monkeypatch):
    """Disk full: every attempt re-reads the whole day's file on the event
    loop. A file whose repair (or write) failed waits REPAIR_RETRY_S before
    the next attempt -- rows stay buffered and the error stays visible."""
    torn_day_file(tmp_path)
    attempts = []
    real_repair = LiveRecorder._repair

    def counting_repair(self, p):
        attempts.append(p.name)
        return real_repair(self, p)

    def full(*a, **k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(LiveRecorder, "_repair", counting_repair)
    with monkeypatch.context() as m:
        m.setattr(os, "replace", full)
        rec = LiveRecorder(tmp_path)
        assert rec.append("NQ", "NQZ6", rows(M + 8_000, [102.0], first_id=6)) != []
        assert len(attempts) == 1                            # first touch: tried, failed
        for _ in range(29):                                  # a flush a second, for 29 s
            assert rec.flush() == 0 and rec.buffered == 1
            assert "No space left" in rec.error
        assert len(attempts) == 1
        later(m)
        assert rec.flush() == 0 and len(attempts) == 2       # 30 s on: tried again, still full
        assert rec.flush() == 0 and len(attempts) == 2
    later(monkeypatch, 2 * recorder_module.REPAIR_RETRY_S)   # the disk has room again
    assert rec.flush() == 1 and rec.error is None and len(attempts) == 3
    assert [t.id for t in TickStore(tmp_path).load("NQ", D).ticks] == [1, 2, 3, 4, 6]
