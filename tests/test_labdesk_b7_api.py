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


def test_the_tail_keeps_a_refusal_between_the_bookkeeping_lines(client):
    """B7 N3: only lab_event / lab_event_done leave the tail; a lab_refused among them stays."""
    write_journal(client.tmp, mixed(10) + [{"event": "lab_refused", "strategy": LAB, "text": "It is off."}] + mixed(10))
    tail = client.get("/api/status").json()["journal"]
    assert [r["text"] for r in tail if r["event"] == "lab_refused"] == ["It is off."]
    assert not [r for r in tail if r["event"] in BOOK]


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


# ================================================================ 3: the flatten answer's per-account ok
def test_flatten_and_turn_off_answers_ok_for_each_account_and_keeps_its_steps(client):
    client.post("/api/lab/intent", headers=client.H, json=event(client, [entry()]))
    st = client.app.state.engine.states[f"{LAB}@a1"]
    fill_entry(client.app.state.engine, client.adapters["a1"], st, 110.25)
    r = client.post("/api/strategy-flatten", json={"strategy": LAB}).json()
    assert r["ok"] is True and r["enabled"] is False
    assert isinstance(r["results"]["a1"], list) and r["results"]["a1"][0] == "market Sell 1: ok"     # as the page reads it today
    assert set(r) == {"ok", "enabled", "results"}                                  # nothing to check: the answer it always was
    assert client.app.state.labdesk.flatten_view(LAB, r["results"]) == {"a1": {"ok": True, "steps": r["results"]["a1"]}}


def test_a_flatten_that_leaves_something_to_check_says_so_for_that_account(client):
    client.post("/api/lab/intent", headers=client.H, json=event(client, [entry()]))
    st = client.app.state.engine.states[f"{LAB}@a1"]
    client.adapters["a1"].stuck.add(st.upper_id)                                   # the broker accepts the cancel; the order stays
    r = client.post("/api/strategy-flatten", json={"strategy": LAB}).json()
    assert r["check"] == ["a1"] and set(r) == {"ok", "enabled", "results", "check"}
    assert any(s.startswith("check it") for s in r["results"]["a1"])               # its steps are kept as they were


def test_the_check_list_never_fails_a_flatten_that_is_done(client, monkeypatch):
    client.post("/api/lab/intent", headers=client.H, json=event(client, [entry()]))

    def boom(*a):
        raise RuntimeError("the view blew up")
    monkeypatch.setattr(client.app.state.labdesk, "flatten_view", boom)
    r = client.post("/api/strategy-flatten", json={"strategy": LAB})
    assert r.status_code == 200 and set(r.json()) == {"ok", "enabled", "results"}


def test_the_flatten_answer_of_every_other_kind_is_what_it_was(client):
    eng = client.app.state.engine
    client.app.state.cfg.book["nq930"] = [{"account": "a1", "qty": 1}]
    bot = eng._state("nq930", "a1")
    bot.status, bot.qty, bot.entry_side, bot.entry_qty = "live", 1, "Buy", 1
    client.adapters["a1"].net = 1
    r = client.post("/api/strategy-flatten", json={"strategy": "nq930"})
    assert r.json() == {"ok": True, "enabled": False, "results": {"a1": r.json()["results"]["a1"]}}
    assert r.json()["results"]["a1"][0] == "market Sell 1: ok"
    client.adapters["a1"].fail_market = True                                       # ... also when it could not get out
    bot.status = "live"
    r = client.post("/api/strategy-flatten", json={"strategy": "nq930"}).json()
    assert set(r) == {"ok", "enabled", "results"} and "check" not in r
