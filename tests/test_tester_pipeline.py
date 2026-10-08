"""The strategy pipeline in the Lab (chart service, /api/tester/pipeline): the Queue / Book / Guide answer, one idea's
page, and the page's actions -- run through THE SAME tools every chat has (claude_mcp.pipeline_tools), against the
FAKE toolkit of tests/test_claude_mcp_pipeline.py (it answers `pipe` in the real one's JSON and words, and keeps its
state under --root). No tape, no engine, and no runner: the fake's `start` writes a pid down and starts nothing.
Temp folders only: the pipeline root is a temp folder, HOME is a temp folder, and no ~/.homebase/pipeline may appear."""
import json
import sys

import pytest
from fastapi.testclient import TestClient

from homebase.charts import tester_api
from homebase.claude_mcp import pipeline_tools
from tests.test_claude_mcp_pipeline import BOOK, CARD, LABELS, NAME, REAL_HOME, Fake, card, seed
from tests.test_tester_api import EVIL, app

ACTIONS = ("add", "start", "pause", "resume", "approve", "refuse")


@pytest.fixture
def fake(tmp_path, monkeypatch):
    folder = tmp_path / "toolkit"
    folder.mkdir()
    f = Fake(folder)
    monkeypatch.setenv("HOMEBASE_BP", str(f.script))
    monkeypatch.setenv("HOMEBASE_BP_PYTHON", sys.executable)
    return f


@pytest.fixture
def proot(tmp_path, monkeypatch):
    d = tmp_path / "pipeline"
    monkeypatch.setenv("HOMEBASE_PIPELINE_ROOT", str(d))
    return d


@pytest.fixture
def c(tmp_path, monkeypatch, fake, proot):
    real = REAL_HOME / ".homebase" / "pipeline"
    was = real.exists()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))                     # the toolkit child inherits it: never the owner's own folder
    monkeypatch.setattr(tester_api.Slots, "quiet", lambda self: False)      # not the desk's 9:30 window, whenever the tests run
    yield TestClient(app(tmp_path), base_url="http://localhost:8852")
    assert not (tmp_path / "home" / ".homebase" / "pipeline").exists() and real.exists() == was      # no test makes the real folder


def run(c, action, **more):
    headers = more.pop("headers", None)
    return c.post("/api/tester/pipeline/run", json={"action": action, **more}, **({"headers": headers} if headers else {}))


def asked(fake) -> list:
    """The pipeline commands the toolkit was asked, in order: ["list", "book", ...]."""
    return [x["argv"][1] for x in fake.calls() if x["argv"][0] == "pipe"]


# ---------------------------------------------------------------- GET /pipeline

def test_the_queue_the_book_and_the_guide_in_one_answer(c, fake, proot):
    r = c.get("/api/tester/pipeline")
    assert r.status_code == 200 and list(r.json()) == ["runner", "counts", "ideas", "book", "stages"]
    assert r.json() == {"runner": {"running": False, "paused": False}, "counts": dict.fromkeys(LABELS, 0), "ideas": [], "book": [],
                        "stages": pipeline_tools.STAGES}
    assert asked(fake) == ["list", "book"] and not proot.exists(), "two commands of the toolkit, and a look makes no folder"
    for x in fake.calls():
        assert x["argv"][-2:] == [f"--root={proot}", "--json"]              # the PIPELINE's own folder, never the idea folder
    stages = r.json()["stages"]
    assert len(stages) == 8 and [s["n"] for s in stages] == list(range(8)) and all(set(s) == {"n", "name", "words"} for s in stages)
    assert stages[1] == {"n": 1, "name": "Raw heat map", "words": "Does it make money across many stops and targets, with no indicators?"}


def test_every_idea_carries_the_pages_label_and_the_counts_are_by_label(c, fake, proot, monkeypatch):
    monkeypatch.setattr(tester_api, "PIPE_CACHE_S", 0.0)
    assert run(c, "add", card=CARD).json()["ok"] is True
    for i, status in enumerate(pipeline_tools.LABELS):
        if status != "queued":
            seed(proot, f"orb_{i}", status, why="orb_2_a5 P1.1 FAIL 44 % of boxes profitable (need over 60 %)" if status == "stopped" else "",
                 stopped_at=1 if status in ("stopped", "code_problem") else None)
    seed(proot, "orb_new", "parked")                                        # a status this version of the app does not know yet
    assert run(c, "approve", name="orb_4").json()["ok"] is True and run(c, "pause").json()["ok"] is True and run(c, "start").json()["ok"] is True
    got = c.get("/api/tester/pipeline").json()
    assert got["runner"] == {"running": True, "paused": True}
    assert [(i["name"], i["status"], i["label"]) for i in got["ideas"]] == [
        ("fvg_open", "queued", "Waiting"), ("orb_1", "running", "Running"), ("orb_2", "stopped", "Stopped"), ("orb_3", "code_problem", "Problem"),
        ("orb_4", "book", "In the book"), ("orb_5", "book", "In the book"), ("orb_6", "refused", "Refused"), ("orb_new", "parked", "parked")]
    assert got["counts"] == {"Waiting": 1, "Running": 1, "Stopped": 1, "Problem": 1, "Passed": 0, "In the book": 2, "Refused": 1, "parked": 1}
    row = got["ideas"][2]                                                   # the toolkit's own row, with the label beside it
    assert set(row) == {"name", "status", "stage", "stopped_at", "why", "tries", "picked", "added_utc", "updated_utc", "source", "family", "label"}
    assert (row["stopped_at"], row["why"], row["family"]) == (1, "orb_2_a5 P1.1 FAIL 44 % of boxes profitable (need over 60 %)", "orb")
    assert got["book"] == [{**BOOK, "name": "orb_4"}], "the book cards as the toolkit keeps them"


def test_the_answer_is_kept_for_two_seconds_and_a_change_from_the_page_is_seen_at_once(c, fake, proot, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(tester_api, "pipe_clock", lambda: now[0])           # the route's own clock, stood still
    assert tester_api.PIPE_CACHE_S == 2.0
    first = c.get("/api/tester/pipeline").json()
    for _ in range(3):
        assert c.get("/api/tester/pipeline").json() == first
    assert asked(fake) == ["list", "book"], "four looks, one pair of commands"
    assert run(c, "add", card=CARD).json()["ok"] is True
    got = c.get("/api/tester/pipeline").json()                              # the page's own change is never hidden by the kept answer
    assert [i["name"] for i in got["ideas"]] == [NAME] and asked(fake) == ["list", "book", "add", "list", "book"]
    assert run(c, "approve", name=NAME).json()["ok"] is False               # a refusal changed nothing: the next look is still a new one
    assert c.get("/api/tester/pipeline").json() == got and asked(fake)[-3:] == ["approve", "list", "book"]
    c.get("/api/tester/pipeline")
    assert asked(fake)[-3:] == ["approve", "list", "book"]
    n = len(asked(fake))
    now[0] += 1.9
    c.get("/api/tester/pipeline")
    assert len(asked(fake)) == n, "inside the two seconds: the kept answer"
    now[0] += 0.2
    c.get("/api/tester/pipeline")
    assert asked(fake)[n:] == ["list", "book"], "past them: asked again"


def test_a_toolkit_that_is_not_installed_is_said_in_its_own_words(c, fake, monkeypatch, tmp_path):
    now = [1000.0]
    monkeypatch.setattr(tester_api, "pipe_clock", lambda: now[0])
    monkeypatch.setenv("HOMEBASE_BP", str(tmp_path / "nowhere" / "bp.py"))
    r = c.get("/api/tester/pipeline")
    assert r.status_code == 503 and "not installed yet" in r.json()["detail"] and str(tmp_path / "nowhere" / "bp.py") in r.json()["detail"]
    assert c.get(f"/api/tester/pipeline/idea/{NAME}").status_code == 503
    monkeypatch.setenv("HOMEBASE_BP", str(fake.script))
    assert c.get("/api/tester/pipeline").status_code == 503 and fake.calls() == [], "kept for the two seconds as an answer is: pages behind a toolkit " \
                                                                                  "that is down never each start it again"
    now[0] += 2.0
    assert c.get("/api/tester/pipeline").status_code == 200 and asked(fake) == ["list", "book"]
    monkeypatch.setenv("HOMEBASE_BP", str(tmp_path / "nowhere" / "bp.py"))
    r = run(c, "pause")                                                     # an action answers as a tool does: ok false, its words
    assert r.status_code == 200 and r.json() == {"ok": False, "text": r.json()["text"]} and "not installed yet" in r.json()["text"]
    assert c.get("/api/tester/pipeline").status_code == 503, "and the look after an action is a new one"


def test_a_look_never_waits_as_long_as_a_tool_may(c, fake, proot, monkeypatch):
    """A page asks every few seconds: its two reads are stopped after pipeline_tools.LOOK_S, not after a tool's 300 s."""
    seen = []
    real = tester_api._Blueprint._bp
    monkeypatch.setattr(tester_api._Blueprint, "_bp", lambda self, args, **kw: (seen.append((args[1], kw.get("timeout"))), real(self, args, **kw))[1])
    c.get("/api/tester/pipeline")
    run(c, "add", card=CARD)
    c.get(f"/api/tester/pipeline/idea/{NAME}")
    run(c, "pause")
    assert pipeline_tools.LOOK_S == 20.0 < pipeline_tools.SHORT_S == 300.0
    assert seen == [("list", 20.0), ("book", 20.0), ("add", 300.0), ("show", 20.0), ("pause", 300.0)]


# ---------------------------------------------------------------- GET /pipeline/idea/{name}

def test_one_idea_its_card_its_state_and_every_stage_it_went_through(c, fake, proot):
    run(c, "add", card=CARD)
    r = c.get(f"/api/tester/pipeline/idea/{NAME}")
    assert r.status_code == 200 and list(r.json()) == ["card", "state", "stages"]
    assert r.json()["card"] == CARD and r.json()["stages"] == [], "the card as it was added: the toolkit's own heat-map specs are not sent"
    assert r.json()["state"]["status"] == "queued" and r.json()["state"]["label"] == "Waiting"
    seed(proot, "orb_stop", "stopped", stopped_at=1, why="orb_stop_a5 P1.1 FAIL 44 % of boxes profitable (need over 60 %)")
    seed(proot, "orb_done", "awaiting_owner", stage=7)
    got = c.get("/api/tester/pipeline/idea/orb_stop").json()
    assert (got["state"]["label"], got["state"]["stopped_at"], got["state"]["why"]) == ("Stopped", 1, "orb_stop_a5 P1.1 FAIL 44 % of boxes profitable (need over 60 %)")
    assert got["stages"] == [
        {"n": 0, "name": "Idea card", "passed": True, "result": "pass", "text": "the card is whole",
         "lines": [{"line": "P0.1", "passed": True, "text": "P0.1 PASS the reason in one sentence, and who loses"}]},
        {"n": 1, "name": "Raw heat map", "passed": False, "result": "fail", "text": "orb_stop_a5: 44 % of boxes profitable\nthe other heat map is no better",
         "lines": [{"line": "P1.1", "passed": False, "text": "orb_stop_a5 P1.1 FAIL 44 % of boxes profitable (need over 60 %)"}]}]
    for s in got["stages"]:
        assert list(s) == ["n", "name", "passed", "result", "text", "lines"]
    done = c.get("/api/tester/pipeline/idea/orb_done").json()
    assert done["state"]["label"] == "Passed" and [(s["n"], s["name"], s["passed"], s["result"]) for s in done["stages"]] == [
        (0, "Idea card", True, "pass"), (1, "Raw heat map", True, "strict"), (7, "The owner's look", None, "awaiting owner")]
    assert fake.argv() == ["pipe", "show", "orb_done", f"--root={proot}", "--json"]


def test_a_name_that_is_not_on_file_is_a_404(c, fake, proot):
    r = c.get("/api/tester/pipeline/idea/nope")
    assert r.status_code == 404 and "no pipeline idea 'nope'" in r.json()["detail"] and asked(fake) == ["show"]
    for bad in ("Bad Name", "--root=x", "a", "x" * 35, "..%2F..%2Fetc"):   # no name of an idea: the toolkit is not even asked
        assert c.get(f"/api/tester/pipeline/idea/{bad}").status_code == 404, bad
    assert asked(fake) == ["show"]
    assert c.get("/api/tester/pipeline/idea/nope", headers={"host": "evil.example"}).status_code == 403


# ---------------------------------------------------------------- POST /pipeline/run

def test_each_action_runs_the_tool_a_chat_has_and_answers_in_its_words(c, fake, proot):
    r = run(c, "add", card=CARD)
    assert r.status_code == 200 and r.json() == {"ok": True, "text": "Pipeline add · fvg_open · Waiting\nfvg_open is in the queue: place 1 of 1.\n"
                                                                     "Stage 1 will run 2 heat maps: fvg_open_a1, fvg_open_a5."}
    assert fake.argv() == ["pipe", "add", "--spec=-", f"--root={proot}", "--json"] and json.loads(fake.calls()[-1]["stdin"]) == CARD
    r = run(c, "add", card=card(name="orb_pre", session="pre"), inbox=True)
    assert "orb_pre is in the queue: place 1 of 2 (inbox: it goes first)." in r.json()["text"] and "--inbox" in fake.argv()
    assert run(c, "add", card=card(name="orb_mid", session="mid"), inbox=False).json()["ok"] is True and "--inbox" not in fake.argv()
    assert run(c, "pause").json() == {"ok": True, "text": "Pipeline pause\nthe queue is paused: the runner stops after the stage in hand"}
    assert run(c, "resume").json() == {"ok": True, "text": "Pipeline resume\nthe queue is not paused: no runner is working"}
    assert run(c, "start").json() == {"ok": True, "text": "Pipeline start\nthe runner is started (pid 4242): it works through the queue by itself"}
    assert fake.argv() == ["pipe", "start", f"--root={proot}", "--json"], "the toolkit's own start: this service spawns nothing itself"
    seed(proot, "orb_one", "awaiting_owner")
    seed(proot, "orb_two", "awaiting_owner")
    assert run(c, "approve", name="orb_one").json() == {"ok": True, "text": f"Pipeline approve · orb_one · In the book\norb_one is in the book ({proot / 'book' / 'orb_one.json'})"}
    assert run(c, "refuse", name="orb_two", why="too few trades").json() == {"ok": True, "text": "Pipeline refuse · orb_two · Refused\norb_two is refused: too few trades"}
    assert fake.argv() == ["pipe", "refuse", "orb_two", "--why=too few trades", f"--root={proot}", "--json"]
    assert asked(fake) == ["add", "add", "add", "pause", "resume", "start", "approve", "refuse"], "one command an action"


def test_a_refusal_of_the_toolkit_is_the_answer_in_its_own_words(c, fake, proot):
    run(c, "add", card=CARD)
    r = run(c, "add", card=card(name="fvg_again"))
    assert r.status_code == 200 and r.json() == {"ok": False, "text": (
        "Refused (pipeline add): 'fvg_again' is the same card as 'fvg_open', added 2026-10-08T04:44:21+00:00: the same market, session, sides and ways "
        "under another name are the same card, and a card is run once\nNothing was run.")}
    half = card(name="half_card", why="")
    r = run(c, "add", card=half)
    assert r.json()["ok"] is False and "the card is not whole: P0.1 FAIL it does not say why it should make money" in r.json()["text"]
    r = run(c, "approve", name=NAME)
    assert r.status_code == 200 and r.json()["ok"] is False
    assert r.json()["text"].startswith("Refused (pipeline approve): fvg_open is queued: only an idea that passed every stage and waits for the owner")
    assert run(c, "refuse", name=NAME, why="no").json()["ok"] is False and run(c, "approve", name="nope").json()["ok"] is False
    r = run(c, "approve", name="Not A Name")                                # the connector's own input check
    assert r.status_code == 200 and r.json()["ok"] is False and r.json()["text"].startswith("name: an idea's name")
    assert [i["name"] for i in c.get("/api/tester/pipeline").json()["ideas"]] == [NAME], "nothing was changed"


def test_what_the_route_refuses(c, fake, proot):
    post = lambda body, **kw: c.post("/api/tester/pipeline/run", json=body, **kw)  # noqa: E731
    bad = [{}, {"action": "run"}, {"action": "_loop"}, {"action": "show", "name": NAME}, {"action": ["start"]}, {"action": None},
           {"action": "add"}, {"action": "add", "card": "why: it works"}, {"action": "add", "card": [CARD]}, {"action": "add", "card": CARD, "inbox": "yes"},
           {"action": "add", "card": CARD, "inbox": None}, {"action": "add", "card": CARD, "name": NAME}, {"action": "add", "card": CARD, "stage": 5},
           {"action": "start", "name": NAME}, {"action": "pause", "why": "x"}, {"action": "resume", "card": CARD}, {"action": "start", "once": True},
           {"action": "approve"}, {"action": "approve", "name": 7}, {"action": "approve", "name": NAME, "why": "he said yes"},
           {"action": "approve", "name": NAME, "force": True}, {"action": "refuse", "name": NAME}, {"action": "refuse", "name": NAME, "why": "  "},
           {"action": "refuse", "name": NAME, "why": 7}, {"action": "refuse", "why": "no"}, {"action": "refuse", "name": NAME, "why": "no", "card": CARD}]
    for body in bad:
        r = post(body)
        assert r.status_code == 400 and r.json()["detail"] == tester_api.PIPE_SHAPE, body
    for action in ACTIONS:
        assert action in tester_api.PIPE_SHAPE and action in tester_api.PIPE_KEYS
    assert list(tester_api.PIPE_KEYS) == list(ACTIONS)
    assert post({"action": "pause"}, headers=EVIL).status_code == 403            # another site's page cannot touch the queue
    assert post({"action": "pause"}, headers={"host": "evil.example"}).status_code == 403
    assert c.post("/api/tester/pipeline/run", content=json.dumps({"action": "pause"}), headers={"content-type": "text/plain"}).status_code in (415, 422)
    assert fake.calls() == [] and not proot.exists(), "nothing reached the toolkit"
    assert c.get("/api/tester/pipeline").status_code == 200 and c.get("/api/tester/pipeline", headers={"host": "evil.example"}).status_code == 403


def test_nothing_that_can_start_heavy_work_is_started_from_the_page_in_the_930_window(c, fake, proot, monkeypatch):
    seed(proot, "orb_one", "awaiting_owner")
    seed(proot, "orb_two", "awaiting_owner")
    monkeypatch.setattr(tester_api.Slots, "quiet", lambda self: True)
    for action, more in (("add", {"card": CARD}), ("start", {}), ("resume", {})):
        r = run(c, action, **more)
        assert r.status_code == 409 and "09:20" in r.json()["detail"] and "09:35" in r.json()["detail"], action
    assert fake.calls() == [] and tester_api.PIPE_QUIET == ("add", "start", "resume")
    assert run(c, "add", card="not a card").status_code == 400, "a bad shape is a bad shape at any hour"
    assert run(c, "pause").json()["ok"] is True, "the owner can always pause"
    assert run(c, "approve", name="orb_one").json()["ok"] is True and run(c, "refuse", name="orb_two", why="not now").json()["ok"] is True
    assert c.get("/api/tester/pipeline").status_code == 200 and c.get("/api/tester/pipeline/idea/orb_one").status_code == 200      # looking is always allowed
    assert asked(fake) == ["pause", "approve", "refuse", "list", "book", "show"]


def test_the_page_runs_the_tools_and_nothing_else(c):
    """The route knows six actions and each is a tool of pipeline_tools: no stage can be skipped and no pass line
    changed from the page, and nothing of the desk is reachable from here."""
    src = tester_api.Path(tester_api.__file__).read_text(encoding="utf-8")
    body = src[src.index('@r.post("/pipeline/run")'):src.index('@r.post("/show")')]
    assert set(tester_api.PIPE_KEYS) == {"add", *pipeline_tools.ACTIONS, *pipeline_tools.DECISIONS}
    assert body.count("box.t_pipeline_") == 3 and "_bp(" not in body and "_pipe(" not in body and "subprocess" not in src
    for tool in ("blueprint_status", "desk_status", "pipeline_status"):
        assert run(c, tool).status_code == 400
