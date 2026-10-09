"""The strategy pipeline in the Lab (chart service, /api/tester/pipeline): the Queue / Book / Guide answer, one idea's
page, and the page's actions -- the checks and the ONE command of the tool every chat has (claude_mcp.pipeline_tools),
answered in one plain sentence for the page -- against the FAKE toolkit of tests/test_claude_mcp_pipeline.py (it answers
`pipe` in the real one's JSON and words, and keeps its state under --root; `blocks` here in the real one's shape too).
No tape, no engine, and no runner: the fake's `start` writes a pid down and starts nothing.
Temp folders only: the pipeline root is a temp folder, HOME is a temp folder, and no ~/.homebase/pipeline may appear."""
import inspect
import json
import sys

import pytest
from fastapi.testclient import TestClient

from homebase.charts import tester_api
from homebase.claude_mcp import pipeline_tools
from tests.test_claude_mcp_pipeline import BOOK, CARD, FAKE, LABELS, NAME, REAL_HOME, Fake, card, seed
from tests.test_claude_mcp_pipeline import box as toolbox
from tests.test_tester_api import EVIL, app

ACTIONS = ("add", "start", "pause", "resume", "approve", "refuse")
NO_PARTS = {"rules": [], "indicators": [], "sessions": []}
# A small block list in the shape of the real `bp.py blocks --json` (research/edge-library/blueprint/blocklist.py):
# a setting says its values in WORDS, and a family lists the variants the library ran.
BLOCKS = {
    "families": [
        {"name": "fvg", "does": "a three-bar gap forms: a limit rests at its near edge", "why": "not sent", "markets": ["NQ", "ES", "GC"], "bars": ["1", "5", "15"],
         "sessions": ["asia", "nyam", "eve"], "runs": True, "why_not": None, "bracket": False, "mirror": None,
         "settings": [{"name": "min_gap", "default": 0.25, "values": "a number 0 .. 10"}, {"name": "mode", "default": "touch", "values": "touch | mid | go"},
                      {"name": "new_gap", "default": "replace", "values": "replace | stop"}],
         "tried": [{"min_gap": 0.1}, {"min_gap": 0.25, "mode": "touch"}, {"min_gap": 0.5}, {"min_gap": 0.25}]},
        {"name": "donchian", "does": "close beyond the prior n-bar channel", "markets": ["NQ"], "bars": ["15", "30"], "sessions": ["nyam"], "runs": True,
         "settings": [{"name": "n", "default": 20, "values": "a whole number 2 .. 200"}, {"name": "trend_f", "default": False, "values": "true | false"},
                      {"name": "odd", "default": "x", "values": ""}], "tried": [{"n": 10}, {"n": 20}]},
        {"name": "supertrend", "does": "the supertrend flips", "markets": ["NQ", "ES"], "bars": ["1", "5"], "sessions": ["nyam"], "runs": True, "settings": [], "tried": [{}]},
        {"name": "later", "does": "not yet", "markets": ["NQ"], "bars": ["5"], "sessions": ["nyam"], "runs": False, "settings": [], "tried": []}],
    "filters": [
        {"block": "volatility", "side": "high", "words": "only after a wide day", "runs": True, "why_not": None, "markets": ["NQ", "ES", "GC"]},
        {"block": "volatility", "side": "low", "words": "only after a quiet day", "runs": True, "why_not": None, "markets": ["NQ", "ES", "GC"]},
        {"block": "book", "side": "agree", "words": "the book agrees", "runs": True, "why_not": None, "markets": ["NQ"]},
        {"block": "gone", "side": "with", "words": "not yet", "runs": False, "why_not": "later", "markets": ["NQ"]}],
    "sessions": [{"name": "asia", "words": "Asia (00:00-03:00 ET)", "runs": True}, {"name": "nyam", "words": "New York morning (09:30-11:00 ET)", "runs": True}],
    "other_families": ["absorption"], "bars": ["1", "5", "15", "30"]}
MARK = 'if pos[0] != "pipe":'             # where the fake answers a command of the blueprint: `blocks` is answered before it
WITH_BLOCKS = 'if pos[0] == "blocks":\n    out(result("blocks", text="THE BLOCKS", blocks=json.loads(%r)))\n' % json.dumps(BLOCKS)


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


@pytest.fixture
def blocks(fake):
    """The fake toolkit also answers `blocks`, as the real one does (the plain fake only says "RAN blocks ...")."""
    assert FAKE.count(MARK) == 1
    fake.script.write_text(FAKE.replace(MARK, WITH_BLOCKS + MARK), encoding="utf-8")
    return fake


def run(c, action, **more):
    headers = more.pop("headers", None)
    return c.post("/api/tester/pipeline/run", json={"action": action, **more}, **({"headers": headers} if headers else {}))


def asked(fake) -> list:
    """The pipeline commands the toolkit was asked, in order: ["list", "book", ...]."""
    return [x["argv"][1] for x in fake.calls() if x["argv"][0] == "pipe"]


# ---------------------------------------------------------------- GET /pipeline

def test_the_queue_the_book_and_the_guide_in_one_answer(c, fake, proot):
    r = c.get("/api/tester/pipeline")
    assert r.status_code == 200 and list(r.json()) == ["runner", "counts", "ideas", "book", "stages", "rules", "indicators", "sessions"]
    assert r.json() == {"runner": {"running": False, "paused": False}, "counts": dict.fromkeys(LABELS, 0), "ideas": [], "book": [],
                        "stages": pipeline_tools.STAGES, **NO_PARTS}, "a toolkit whose `blocks` carries no block list: empty lists, and the Queue all the same"
    assert asked(fake) == ["list", "book"] and not proot.exists(), "two commands of the pipeline, and a look makes no folder"
    assert [x["argv"][0] for x in fake.calls()] == ["pipe", "pipe", "blocks"]
    for x in fake.calls():
        assert x["argv"][-2:] == [f"--root={proot}", "--json"]              # the PIPELINE's own folder, never the idea folder
    stages = r.json()["stages"]
    assert len(stages) == 8 and [s["n"] for s in stages] == list(range(8)) and all(set(s) == {"n", "name", "words"} for s in stages)
    assert stages[1] == {"n": 1, "name": "Raw heat map", "words": "Does a region of the map make money, and does a box in it pass every build line of a box?"}


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
    monkeypatch.setattr(tester_api._Blueprint, "_bp", lambda self, args, **kw: (seen.append((args[args[0] == "pipe"], kw.get("timeout"))), real(self, args, **kw))[1])
    c.get("/api/tester/pipeline")
    run(c, "add", card=CARD)
    c.get(f"/api/tester/pipeline/idea/{NAME}")
    run(c, "pause")
    assert pipeline_tools.LOOK_S == 20.0 < pipeline_tools.SHORT_S == 300.0
    assert seen == [("list", 20.0), ("book", 20.0), ("blocks", 20.0), ("add", 300.0), ("show", 20.0), ("pause", 300.0)]


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

def test_each_action_runs_the_command_of_the_tool_a_chat_has_and_answers_in_one_plain_sentence(c, fake, proot):
    r = run(c, "add", card=CARD)
    assert r.status_code == 200 and r.json() == {"ok": True, "text": "fvg_open is in the Queue, place 1 of 1."}
    assert fake.argv() == ["pipe", "add", "--spec=-", f"--root={proot}", "--json"] and json.loads(fake.calls()[-1]["stdin"]) == CARD
    r = run(c, "add", card=card(name="orb_pre", session="pre"), inbox=True)
    assert r.json() == {"ok": True, "text": "orb_pre is in the Queue, place 1 of 2."} and "--inbox" in fake.argv()
    assert run(c, "add", card=card(name="orb_mid", session="mid"), inbox=False).json() == {"ok": True, "text": "orb_mid is in the Queue, place 3 of 3."}
    assert "--inbox" not in fake.argv()
    assert run(c, "pause").json() == {"ok": True, "text": "Paused. It stops after the stage it is on."}
    assert run(c, "resume").json() == {"ok": True, "text": "It is not paused any more."}, "no runner is working: nothing carries on yet"
    assert run(c, "start").json() == {"ok": True, "text": "Testing has started."}
    assert fake.argv() == ["pipe", "start", f"--root={proot}", "--json"], "the toolkit's own start: this service spawns nothing itself"
    assert run(c, "start").json() == {"ok": True, "text": "Testing is already on."}
    assert run(c, "pause").json()["ok"] is True and run(c, "start").json() == {"ok": True, "text": "Testing is already on. It is paused: press Resume."}
    assert run(c, "resume").json() == {"ok": True, "text": "Testing carries on."}
    seed(proot, "orb_one", "awaiting_owner")
    seed(proot, "orb_two", "awaiting_owner")
    assert run(c, "approve", name="orb_one").json() == {"ok": True, "text": "orb_one is in the Book."}
    assert run(c, "refuse", name="orb_two", why="too  few trades").json() == {"ok": True, "text": "orb_two is refused: too few trades"}
    assert fake.argv() == ["pipe", "refuse", "orb_two", "--why=too few trades", f"--root={proot}", "--json"]
    assert asked(fake) == ["add", "add", "add", "pause", "resume", "start", "start", "pause", "start", "resume", "approve", "refuse"], "one command an action"


def test_the_pages_sentences_and_the_chat_tools_texts_are_two_things(fake, proot):
    """page_said reads the toolkit's RESULT; a chat's tool still says the toolkit's text (tests/test_claude_mcp_pipeline.py)."""
    said = pipeline_tools.page_said
    assert said("add", {"name": "x", "text": "x is in the queue: place 2 of 7 (inbox: it goes first).\nStage 1 will run 2 heat maps"}) == "x is in the Queue, place 2 of 7."
    assert said("add", {"name": "x", "text": "filed"}) == "x is in the Queue."
    assert said("start", {"already": False, "paused": False, "pid": 9}) == "Testing has started."
    assert said("start", {"already": False, "paused": True}) == "Testing has started. It is paused: press Resume."
    assert said("resume", {"running": True}) == "Testing carries on." and said("pause", {"paused": True}) == "Paused. It stops after the stage it is on."
    assert said("approve", {"name": "x", "text": "x is in the book (/Users/a/.homebase/pipeline/book/x.json)"}) == "x is in the Book."
    assert said("refuse", {"name": "x", "state": {"why": "too thin (bp.py pipe list)"}}) == "x is refused: too thin"
    b = toolbox()
    assert b.t_pipeline_add(CARD).splitlines()[0] == "Pipeline add · fvg_open · Waiting", "the chat tool's text is as it was"
    assert b.t_pipeline_control("pause") == "Pipeline pause\nthe queue is paused: the runner stops after the stage in hand"
    assert b.pipeline_do("resume") == "It is not paused any more."


def test_plain_takes_out_the_command_line_and_the_folders_and_nothing_else():
    plain = pipeline_tools.plain
    assert plain("refusing x needs the reason (bp.py pipe refuse x --why=TEXT): it is kept with the idea") == "refusing x needs the reason: it is kept with the idea"
    assert plain("block 'nope' is no filter block (`bp.py blocks` lists them)") == "block 'nope' is no filter block"
    assert plain("x is in the book (/Users/a b/.homebase/pipeline/book/x.json)".replace("a b", "ab")) == "x is in the book"
    assert plain("no pipeline idea 'nope' under /tmp/t/pipeline") == "no pipeline idea 'nope' under pipeline"
    assert plain("~/.homebase/pipeline/seen.jsonl holds a line that does not read (line 3): mend it first") == "seen.jsonl holds a line that does not read (line 3): mend it first"
    assert plain("The queue is PAUSED: bp.py pipe resume lets it work") == "The queue is PAUSED:"
    for same in ("orb_2_a5 P1.1 FAIL 44 % of boxes profitable (need over 60 %)", "a5: 44 % of boxes\nthe other heat map is no better", "NQ/ES and/or 1/2, 09:20/09:35",
                 "way a: min_gap has 1 values (need 3, each once)", ""):
        assert plain(same) == same, same
    assert plain(None) == ""
    assert pipeline_tools.page_refusal("Refused (pipeline add): the card is not whole: P0.3 FAIL block 'nope' is no filter block (`bp.py blocks` lists them)\n"
                                       "Nothing was run.\nNext: bp.py pipe list shows where each idea is.") == "the card is not whole: P0.3 FAIL block 'nope' is no filter block"
    assert pipeline_tools.page_refusal("") == "It was refused."


def test_a_refusal_of_the_toolkit_is_the_answer_in_its_own_words(c, fake, proot):
    run(c, "add", card=CARD)
    r = run(c, "add", card=card(name="fvg_again"))
    assert r.status_code == 200 and r.json() == {"ok": False, "text": (
        "'fvg_again' is the same card as 'fvg_open', added 2026-10-08T04:44:21+00:00: the same market, session, sides and ways "
        "under another name are the same card, and a card is run once")}, "the reason as the toolkit wrote it, and no more"
    half = card(name="half_card", why="")
    r = run(c, "add", card=half)
    assert r.json() == {"ok": False, "text": "the card is not whole: P0.1 FAIL it does not say why it should make money (why, one sentence)"}
    r = run(c, "approve", name=NAME)
    assert r.status_code == 200 and r.json() == {"ok": False, "text": "fvg_open is queued: only an idea that passed every stage and waits for the owner "
                                                                      "(awaiting_owner) is approved"}
    assert run(c, "refuse", name=NAME, why="no").json()["ok"] is False
    assert run(c, "approve", name="nope").json() == {"ok": False, "text": "no pipeline idea 'nope' under pipeline"}, "a path is cut to its last name"
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
    assert body.count("box.pipeline_do(") == 1 and "box.t_" not in body and "_bp(" not in body and "_pipe(" not in body and "subprocess" not in src
    do = inspect.getsource(pipeline_tools.PipelineMixin.pipeline_do)
    assert do.count("self._pipe(") == 3 and "_bp(" not in do, "one command an action: the tool's own"
    for check, tool in (("_card_ok(", "t_pipeline_add"), ("_action_ok(", "t_pipeline_control"), ("_decided(", "t_pipeline_decide")):
        assert check in do and check in inspect.getsource(getattr(pipeline_tools.PipelineMixin, tool)), f"the page makes the checks of {tool}"
    for tool in ("blueprint_status", "desk_status", "pipeline_status"):
        assert run(c, tool).status_code == 400


# ---------------------------------------------------------------- what the add-idea form is built from

def test_the_rules_the_indicators_and_the_sessions_off_one_blocks_call_for_the_life_of_the_service(c, blocks, proot, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(tester_api, "pipe_clock", lambda: now[0])
    got = c.get("/api/tester/pipeline").json()
    assert list(got) == ["runner", "counts", "ideas", "book", "stages", "rules", "indicators", "sessions"]
    assert [r["name"] for r in got["rules"]] == ["fvg", "donchian", "supertrend"], "a rule that does not run yet is not sent"
    fvg = got["rules"][0]
    assert list(fvg) == ["name", "words", "markets", "sessions", "bars", "settings"], "only what the form needs"
    assert (fvg["words"], fvg["markets"], fvg["sessions"], fvg["bars"]) == ("a three-bar gap forms: a limit rests at its near edge", ["NQ", "ES", "GC"],
                                                                         ["asia", "nyam", "eve"], ["1", "5", "15"])
    assert fvg["settings"] == [
        {"name": "min_gap", "kind": "number", "min": 0, "max": 10, "choices": [], "default": 0.25, "tried": [0.1, 0.25, 0.5]},
        {"name": "mode", "kind": "choice", "min": None, "max": None, "choices": ["touch", "mid", "go"], "default": "touch", "tried": ["touch"]},
        {"name": "new_gap", "kind": "choice", "min": None, "max": None, "choices": ["replace", "stop"], "default": "replace", "tried": []}]
    assert got["rules"][1]["settings"] == [
        {"name": "n", "kind": "whole", "min": 2, "max": 200, "choices": [], "default": 20, "tried": [10, 20]},
        {"name": "trend_f", "kind": "bool", "min": None, "max": None, "choices": [], "default": False, "tried": []},
        {"name": "odd", "kind": "text", "min": None, "max": None, "choices": [], "default": "x", "tried": []}], "words it cannot read: text, never a guess"
    assert got["rules"][2]["settings"] == []
    assert got["indicators"] == [
        {"block": "volatility", "sides": [{"side": "high", "words": "only after a wide day"}, {"side": "low", "words": "only after a quiet day"}], "markets": ["NQ", "ES", "GC"]},
        {"block": "book", "sides": [{"side": "agree", "words": "the book agrees"}], "markets": ["NQ"]}]
    assert got["sessions"] == [{"name": "asia", "words": "Asia (00:00-03:00 ET)"}, {"name": "nyam", "words": "New York morning (09:30-11:00 ET)"}]
    assert blocks.argv() == ["blocks", f"--root={proot}", "--json"] and not proot.exists()
    for _ in range(3):                                                      # past the two seconds: the Queue is asked again, the block list never
        now[0] += 5.0
        assert c.get("/api/tester/pipeline").json()["rules"] == got["rules"]
    assert [x["argv"][0] for x in blocks.calls()].count("blocks") == 1 and asked(blocks) == ["list", "book"] * 4
    assert run(c, "add", card=CARD).json()["ok"] is True and "rules" in c.get("/api/tester/pipeline").json()
    assert [x["argv"][0] for x in blocks.calls()].count("blocks") == 1


def test_a_toolkit_that_cannot_list_its_blocks_leaves_the_form_its_text_fields_and_the_queue_whole(c, fake, proot, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(tester_api, "pipe_clock", lambda: now[0])
    real = tester_api._Blueprint._bp

    def bp(self, args, **kw):
        if args[0] == "blocks":
            raise tester_api.ToolError("The blueprint toolkit crashed (exit 1) on `blocks`: boom")
        return real(self, args, **kw)
    monkeypatch.setattr(tester_api._Blueprint, "_bp", bp)
    r = c.get("/api/tester/pipeline")
    assert r.status_code == 200 and {k: r.json()[k] for k in NO_PARTS} == NO_PARTS and r.json()["stages"] == pipeline_tools.STAGES
    monkeypatch.setattr(tester_api._Blueprint, "_bp", real)                 # it answers again: a failure was not kept
    fake.script.write_text(FAKE.replace(MARK, 'if pos[0] == "blocks":\n    out(result("blocks", blocks={"families": [{"name": "orb", "runs": True}]}))\n' + MARK), encoding="utf-8")
    now[0] += 5.0
    assert [x["name"] for x in c.get("/api/tester/pipeline").json()["rules"]] == ["orb"]
    assert pipeline_tools.parts(None) == NO_PARTS and pipeline_tools.parts({"families": "x", "filters": [7]}) == NO_PARTS
    assert pipeline_tools.parts({"families": [{"name": "orb"}]})["rules"] == [{"name": "orb", "words": "", "markets": [], "sessions": [], "bars": [], "settings": []}]


def test_every_text_of_an_idea_is_plain_for_the_page(c, fake, proot):
    seed(proot, "orb_done", "awaiting_owner", stage=7, why="it waits (bp.py pipe approve orb_done, or bp.py pipe refuse orb_done --why=TEXT)")
    file = proot / "fake.json"
    S = json.loads(file.read_text())
    S["ideas"]["orb_done"]["stages"]["7"]["text"] = "orb_done waits for the owner's look: 9 of 12 months won (bp.py pipe approve orb_done, or bp.py pipe refuse orb_done --why=TEXT)"
    S["ideas"]["orb_done"]["stages"]["1"]["lines"][0]["text"] = "P1.1 PASS 61 % of boxes (need over 60 %), table /tmp/runs/orb_done_a5-NQ-tf5"
    S["ideas"]["orb_done"]["stages"]["7"]["book"]["stages"] = {"6": {"passed": True, "result": "proven on history", "text": "PROVEN (bp.py pipe show orb_done)"}}
    file.write_text(json.dumps(S))
    got = c.get("/api/tester/pipeline/idea/orb_done").json()
    assert got["stages"][-1]["text"] == "orb_done waits for the owner's look: 9 of 12 months won" and got["state"]["why"] == "it waits"
    assert got["stages"][1]["lines"][0]["text"] == "P1.1 PASS 61 % of boxes (need over 60 %), table orb_done_a5-NQ-tf5"
    assert c.get("/api/tester/pipeline").json()["ideas"][0]["why"] == "it waits"
    assert run(c, "approve", name="orb_done").json() == {"ok": True, "text": "orb_done is in the Book."}
    assert c.get("/api/tester/pipeline").json()["book"][0]["stages"] == {"6": {"passed": True, "result": "proven on history", "text": "PROVEN"}}
