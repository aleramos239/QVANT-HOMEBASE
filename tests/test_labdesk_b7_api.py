"""Step B, task B7: the follow-ups that need the desk's own routes (/api/status, /api/strategy-flatten). The real
desk app on fake adapters: no network, no broker, a temp state folder and store."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from homebase.server import JOURNAL_TAIL
from tests.labdesk_util import LAB, entry
from tests.test_engine_lab import fill_entry
from tests.test_labdesk_api import DESK, client, event, jl, make_app, paths  # noqa: F401 -- the fixtures

BOOK = ("lab_event", "lab_event_done")


def write_journal(tmp, rows):
    with open(tmp / "journal.jsonl", "a") as f:
        for r in rows:
            f.write(json.dumps({"ts": 1.0, "et": "2026-09-14T10:00:00-04:00", **r}) + "\n")


def mixed(n):
    """n ordinary lines, each followed by an event's two bookkeeping lines."""
    rows = []
    for i in range(n):
        rows += [{"event": "note", "i": i}, {"event": "lab_event", "strategy": LAB, "seq": i},
                 {"event": "lab_event_done", "strategy": LAB, "seq": i}]
    return rows


# ================================================================ 2: the page's journal tail without the intake's bookkeeping
def test_the_status_tail_leaves_the_intakes_bookkeeping_out_and_keeps_its_length(client):
    write_journal(client.tmp, mixed(100))
    client.post("/api/lab/intent", headers=client.H, json=event(client, [entry()]))
    tail = client.get("/api/status").json()["journal"]
    assert len(tail) == JOURNAL_TAIL == 60 and not [r for r in tail if r["event"] in BOOK]
    file_rows = [json.loads(x) for x in (client.tmp / "journal.jsonl").read_text().splitlines()]
    assert sum(1 for r in file_rows if r["event"] in BOOK) == 202                  # they all stay in the file
    assert tail == [r for r in file_rows if r["event"] not in BOOK][-60:][::-1]    # the newest sixty OTHER lines, newest first
    assert {"lab_round", "placed"} <= {r["event"] for r in tail}                   # a Lab line that is not bookkeeping shows


def test_a_journal_with_no_bookkeeping_line_reads_as_it_always_did(client):
    write_journal(client.tmp, [{"event": "note", "i": i} for i in range(90)])
    file_rows = [json.loads(x) for x in (client.tmp / "journal.jsonl").read_text().splitlines()]
    assert client.get("/api/status").json()["journal"] == file_rows[-60:][::-1]


def test_a_desk_with_the_lab_side_off_shows_its_tail_exactly_as_before(paths):
    app, _ = make_app(lab=False)
    with TestClient(app, base_url=DESK) as c:
        write_journal(paths, mixed(100))                                           # (left by a day the Lab side was on)
        file_rows = [json.loads(x) for x in (paths / "journal.jsonl").read_text().splitlines()]
        tail = c.get("/api/status").json()["journal"]
        assert tail == file_rows[-60:][::-1] and sum(1 for r in tail if r["event"] in BOOK) == 40
