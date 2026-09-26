"""Recorder: dedupe, per-session files, crash safety, gaps; refill paging."""
from __future__ import annotations

import asyncio
import datetime as dt
import gzip

from homebase import ticks as T
from homebase.charts.recorder import LiveRecorder, refill
from homebase.charts.store import TickStore, read_table
from tests.charts_util import D, rows, session_ms

M = session_ms(D, 9, 30)


def run(coro):
    return asyncio.run(coro)


async def nosleep(_s):
    return None


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


def test_a_failed_flush_keeps_the_rows(tmp_path):
    blocker = tmp_path / "NQ"
    blocker.write_text("not a directory")
    rec = LiveRecorder(tmp_path)
    rec.append("NQ", "NQZ6", rows(M, [100.0]))
    assert rec.flush() == 0 and rec.error and rec.buffered == 1
    blocker.unlink()
    assert rec.flush() == 1 and rec.error is None


def test_mark_gap_is_read_back_by_the_store(tmp_path):
    rec = LiveRecorder(tmp_path)
    rec.append("NQ", "NQZ6", rows(M, [100.0]))
    rec.flush()
    rec.mark_gap("NQ", D, "NQZ6", 1, 2)
    rec.mark_gap("NQ", D, "NQZ6", 3, 4)
    assert TickStore(tmp_path).load("NQ", D).gaps == [[1, 2], [3, 4]]


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
