"""The Desk's speed fixes (2026-10-26): the same answers, less work on the event loop."""
from __future__ import annotations

import asyncio
import json

import pytest

from homebase import equity
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


# ---- equity.jsonl: only the lines appended since the last read are parsed; the answer is a full parse's
def _full_parse(p):
    """equity._days before 2026-10-26: every line, from the start, on every change of the file."""
    days = {}
    for line in p.read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("equity") is not None:
            days.setdefault(r.get("account"), {})[r["date"]] = float(r["equity"])
    return days


def _same_as_a_full_parse(p):
    got = equity._days(p)
    want = _full_parse(p)
    assert got == want and list(got) == list(want) and all(list(got[a]) == list(want[a]) for a in want)
    return got


def _line(account, date, eq):
    return json.dumps({"date": date, "account": account, "equity": eq}) + "\n"


def test_equity_appends_rotation_truncation_and_a_repeated_date_answer_as_a_full_parse(tmp_path, monkeypatch):
    p = tmp_path / "equity.jsonl"
    p.write_text(_line("A", "2026-10-01", 100.0) + _line("B", "2026-10-01", 5.0) + "not json\n")
    first = _same_as_a_full_parse(p)
    parsed = []
    real = equity._fold
    monkeypatch.setattr(equity, "_fold", lambda days, text: parsed.append(text) or real(days, text))
    with open(p, "a") as f:
        f.write(_line("A", "2026-10-01", 101.0) + _line("A", "2026-10-02", 102.0))       # a repeated date: the last wins
    got = _same_as_a_full_parse(p)
    assert got["A"] == {"2026-10-01": 101.0, "2026-10-02": 102.0} and first["A"] == {"2026-10-01": 100.0}
    assert parsed == [_line("A", "2026-10-01", 101.0) + _line("A", "2026-10-02", 102.0)]   # only what was added
    with open(p, "a") as f:
        f.write(_line("C", "2026-10-02", 7.0)[:-1])                    # its newline not written yet
    assert _same_as_a_full_parse(p)["C"] == {"2026-10-02": 7.0}
    with open(p, "a") as f:
        f.write('\n{"date": "2026-10-03", "acc')                       # ...now whole, and the next one half written
    _same_as_a_full_parse(p)
    with open(p, "a") as f:
        f.write('ount": "C", "equity": 8.0}\n')
    assert _same_as_a_full_parse(p)["C"] == {"2026-10-02": 7.0, "2026-10-03": 8.0}
    p.write_text(_line("A", "2026-10-01", 1.0))                        # truncated
    assert _same_as_a_full_parse(p) == {"A": {"2026-10-01": 1.0}}
    q = tmp_path / "new.jsonl"
    q.write_text(_line("Z", "2026-10-05", 9.0) + _line("A", "2026-10-01", 1.0))
    q.replace(p)                                                        # rotated: another file at the path
    assert _same_as_a_full_parse(p) == {"Z": {"2026-10-05": 9.0}, "A": {"2026-10-01": 1.0}}
    text = p.read_text()
    p.write_text(text.replace("9.0", "3.0") + _line("Z", "2026-10-06", 4.0))   # rewritten in place, and longer
    assert _same_as_a_full_parse(p)["Z"] == {"2026-10-05": 3.0, "2026-10-06": 4.0}


def test_a_line_that_raised_before_still_raises_and_the_reader_keeps_nothing_half_read(tmp_path):
    p = tmp_path / "equity.jsonl"
    p.write_text(_line("A", "2026-10-01", 100.0))
    before = _same_as_a_full_parse(p)
    with open(p, "a") as f:
        f.write(_line("A", "2026-10-02", 101.0) + "5\n")              # JSON, not an object: .get raises
    with pytest.raises(AttributeError) as now:
        equity._days(p)
    with pytest.raises(AttributeError) as then:
        _full_parse(p)
    assert str(now.value) == str(then.value) and before == {"A": {"2026-10-01": 100.0}}
    with pytest.raises(AttributeError):
        equity._days(p)                                                 # every time, as before
    p.write_text(_line("A", "2026-10-01", 100.0) + _line("A", "2026-10-02", 101.0))
    assert _same_as_a_full_parse(p)["A"] == {"2026-10-01": 100.0, "2026-10-02": 101.0}

