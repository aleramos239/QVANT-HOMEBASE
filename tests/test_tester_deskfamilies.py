"""Desk families on the chart service (deskfamilies.py) and their routes. Display only: nothing is run, booked or switched.
The store is written into a temp folder."""
import json

import pytest
from fastapi.testclient import TestClient

from homebase.charts import deskfamilies, deskgroups, tester_api
from homebase.labrun import store
from tests.test_tester_api import EVIL, app

DESK = {"origin": "http://localhost:8850"}


@pytest.fixture
def at(tmp_path, monkeypatch):
    monkeypatch.setenv(store.ENV_ROOT, str(tmp_path / "desklab"))
    return tmp_path


def test_a_strategy_sits_in_one_family_with_its_short_name(at):
    assert deskfamilies.load() == []
    deskfamilies.apply("create", {"name": "  NQ 15m  FVG "})
    deskfamilies.apply("create", {"name": "First 15m"})
    deskfamilies.apply("move", {"strategy": "lab_nq_a", "family": "f1", "short": " 25 pts ·  1.5R "})
    deskfamilies.apply("move", {"strategy": "lab_nq_b", "family": "f1"})
    f = deskfamilies.apply("move", {"strategy": "lab_nq_a", "family": "f2", "short": "1.5R"})
    assert f == [{"id": "f1", "name": "NQ 15m FVG", "members": ["lab_nq_b"], "short": {}},
                 {"id": "f2", "name": "First 15m", "members": ["lab_nq_a"], "short": {"lab_nq_a": "1.5R"}}], "moving takes it out of the first"
    f = deskfamilies.apply("short", {"strategy": "lab_nq_b", "short": "2R"})
    assert f[0]["short"] == {"lab_nq_b": "2R"}
    assert deskfamilies.apply("short", {"strategy": "lab_nq_b", "short": ""})[0]["short"] == {}
    f = deskfamilies.apply("move", {"strategy": "lab_nq_a", "family": None})
    assert f[1]["members"] == [] and f[1]["short"] == {}
    deskfamilies.apply("rename", {"id": "f2", "name": "First 15m follow"})
    assert [x["id"] for x in deskfamilies.apply("delete", {"id": "f1"})] == ["f2"]


@pytest.mark.parametrize("action, body, said", [
    ("create", {"name": ""}, "1 to 40"),
    ("create", {"name": "nq 15m fvg"}, "name already"),
    ("rename", {"id": "f9", "name": "x"}, "not there any more"),
    ("move", {"strategy": "Bad!", "family": "f1"}, "not a strategy"),
    ("move", {"strategy": "lab_nq_a", "family": "f1", "short": "x" * 25}, "up to 24"),
    ("short", {"strategy": "lab_nq_zz", "short": "1R"}, "in no family"),
    ("nope", {}, "unknown"),
])
def test_a_refusal_is_in_words_and_writes_nothing(at, action, body, said):
    deskfamilies.apply("create", {"name": "NQ 15m FVG"})
    before = deskfamilies.path().read_text()
    with pytest.raises(deskgroups.GroupError, match=said):
        deskfamilies.apply(action, body)
    assert deskfamilies.path().read_text() == before


def test_a_bad_file_is_read_forgivingly(at):
    deskfamilies.path().parent.mkdir(parents=True, exist_ok=True)
    deskfamilies.path().write_text("not json")
    assert deskfamilies.load() == []
    deskfamilies.path().write_text(json.dumps({"families": [
        {"id": "f1", "name": "A", "members": ["ok_1", "Bad!", 5, "ok_1"], "short": {"ok_1": "1R", "gone": "x"}},
        "junk", {"id": "f1", "name": "dup"}, {"id": "g2", "name": "not a family id"},
        {"id": "f3", "name": "B", "members": ["ok_1", "ok_2"], "short": "nope"}]}))
    assert deskfamilies.load() == [{"id": "f1", "name": "A", "members": ["ok_1"], "short": {"ok_1": "1R"}},
                                   {"id": "f3", "name": "B", "members": ["ok_2"], "short": {}}]


def test_the_routes_answer_the_desk_page_only(at, monkeypatch):
    monkeypatch.setattr(tester_api, "DESKLAB_AUTO_UNSEEN", False)
    c = TestClient(app(at), base_url="http://localhost:8852")
    assert c.get("/api/tester/deskfamilies", headers=EVIL).status_code == 403
    assert c.get("/api/tester/deskfamilies", headers=DESK).json() == {"families": []}
    assert c.options("/api/tester/deskfamilies/create", headers={"origin": "http://evil.example"}).status_code == 403
    assert c.options("/api/tester/deskfamilies/create", headers=DESK).status_code == 204
    assert c.post("/api/tester/deskfamilies/create", json={"name": "x"}, headers=EVIL).status_code == 403
    assert c.post("/api/tester/deskfamilies/create", json={"name": "FVG"}, headers=DESK).json()["families"][0]["id"] == "f1"
    r = c.post("/api/tester/deskfamilies/create", json={"name": "fvg"}, headers=DESK)
    assert r.status_code == 409 and r.json() == {"ok": False, "detail": "There is a family with that name already."}
    c.post("/api/tester/deskfamilies/move", json={"strategy": "lab_nq_a", "family": "f1", "short": "1R"}, headers=DESK)
    assert c.get("/api/tester/deskfamilies", headers=DESK).json()["families"][0]["members"] == ["lab_nq_a"]
    assert c.post("/api/tester/deskfamilies/wat", json={}, headers=DESK).status_code == 404
