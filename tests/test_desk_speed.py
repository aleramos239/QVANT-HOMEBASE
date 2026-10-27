"""The Desk's speed fixes (2026-10-26): the same answers, less work on the event loop."""
from __future__ import annotations

import asyncio
import json

import pytest

from homebase.bothistory import JournalCache
from tests.test_server import _write_journal, client  # noqa: F401  (the desk app over fakes, its state in tmp_path)


def _spy_threads(monkeypatch):
    seen, real = [], asyncio.to_thread

    async def spy(fn, *a, **k):
        seen.append(getattr(fn, "__name__", fn))
        return await real(fn, *a, **k)

    monkeypatch.setattr(asyncio, "to_thread", spy)
    return seen


def test_the_first_status_parses_the_journal_in_a_thread_and_the_next_ones_from_the_cache(client, tmp_path,
                                                                                          monkeypatch):
    _write_journal(tmp_path, 300)
    seen = _spy_threads(monkeypatch)
    first = client.get("/api/status")
    assert seen == ["records"]
    assert client.get("/api/status").content == first.content and seen == ["records"]


# ---- /api/journal and /api/strategy-live from the shared JournalCache (whole): the answer of a full read
def _old_records(p):
    """/api/journal's read before the cache: the whole file, each line parsed, objects kept."""
    out = []
    for line in p.read_text().splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def test_whole_is_what_a_full_read_of_the_file_gives_now(tmp_path):
    p, c = tmp_path / "journal.jsonl", JournalCache()
    p.write_text('{"a": 1}\nnot json\n5\n[1]\n{"b": 2}\n')
    recs, odd = c.whole(p)
    assert recs == _old_records(p) == [{"a": 1}, {"b": 2}] and odd is True
    with open(p, "a") as f:
        f.write('{"c": 3}')                                     # a last line whose newline is not written yet
    more, _ = c.whole(p)
    assert more == _old_records(p) == recs + [{"c": 3}] and len(recs) == 2      # the shared list is never changed
    with open(p, "a") as f:
        f.write('\n{"d"')                                       # ...now ended, and a partial one after it
    assert c.whole(p)[0] == _old_records(p) == recs + [{"c": 3}]
    p.write_text('{"e": 5}\n')                                  # shrank: read again from the start
    assert c.whole(p) == ([{"e": 5}], False)
    q = tmp_path / "new.jsonl"
    q.write_text('{"f": 6}\n{"g": 7}\n')
    q.replace(p)                                                # replaced (another inode)
    assert c.whole(p) == ([{"f": 6}, {"g": 7}], False)
    assert c.whole(tmp_path / "missing.jsonl") is None


def test_whole_never_stands_for_a_read_that_would_raise(tmp_path):
    p, c = tmp_path / "journal.jsonl", JournalCache()
    p.write_bytes(b'{"a": 1}\n{"b": "\xff"}\n')
    assert c.records(p) == [{"a": 1}, {"b": "�"}]          # /api/status as before: the byte replaced
    assert c.whole(p) is None                                   # the others read it themselves: read_text raises
    p.write_bytes(b'{"a": 1}\n')
    assert c.whole(p) == ([{"a": 1}], False)
    with open(p, "ab") as f:
        f.write(b'{"b": "\xff"}')                               # a tail that is not UTF-8
    assert c.whole(p) is None


def test_journal_and_strategy_live_answer_byte_for_byte_as_the_full_read(client, tmp_path, monkeypatch):
    _write_journal(tmp_path, 300)
    with open(tmp_path / "journal.jsonl", "a") as f:            # its newline not written yet
        f.write(json.dumps({"et": "2026-07-02T10:00:00", "event": "exit_fill", "strategy": "nq930",
                            "account": "main", "reason": "tp", "fill": 24525.0, "pnl": 777.0}))
    asks = [("/api/journal", {"date": "2026-07-02", "days": 90, "limit": 2000}),
            ("/api/strategy-live", {"strategy": "nq930"})]
    client.get("/api/status")                                   # the cache warm, as on the desk
    got = [client.get(u, params=q).content for u, q in asks]
    assert all(b"777.0" in g for g in got)
    monkeypatch.setattr(JournalCache, "whole", lambda self, path: None)        # the old full read, every time
    assert [client.get(u, params=q).content for u, q in asks] == got


def test_a_line_that_is_not_an_object_still_fails_strategy_live_as_before(client, tmp_path):
    (tmp_path / "journal.jsonl").write_text(
        '{"et": "2026-09-22T09:30:00", "event": "placed", "strategy": "nq930"}\n5\n')
    with pytest.raises(AttributeError):                         # 'int' object has no attribute 'get': a 500
        client.get("/api/strategy-live", params={"strategy": "nq930"})
    assert client.get("/api/journal", params={"date": "2026-09-22"}).json()["count"] == 1

