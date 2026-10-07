"""The blueprint toolkit in the Lab (chart service, /api/tester/blueprint): the page lists THE SAME tools every chat
has (claude_mcp.blueprint_tools.SPECS) and runs them through the same code -- against a FAKE toolkit: a small script
written here that answers in the toolkit's JSON and echoes the command line it was given. No tape, no engine."""
import json
import sys

import pytest
from fastapi.testclient import TestClient

from homebase import ideastore
from homebase.charts import tester_api
from homebase.claude_mcp import blueprint_tools
from tests.test_tester_api import EVIL, app

FAKE = r'''
import json, sys
argv = sys.argv[1:]
if argv[:1] == ["card"] and "bad_name" in argv:
    print(json.dumps({"ok": False, "command": "card", "name": None, "status": None, "phase": 0, "round": None, "lines": [], "text": "REFUSED: no such idea",
                      "next": "", "job": None, "saved": [], "error": "no such idea"}))
    sys.exit(2)
job = {"id": "j1", "state": "running", "progress": "pass 1 of 2"} if argv[:1] == ["build"] and "--wait=0" in argv else None
print(json.dumps({"ok": True, "command": argv[0], "name": None, "status": None, "phase": None, "round": None, "lines": [],
                  "text": "RAN " + " ".join(argv), "next": "", "job": job, "saved": [], "error": None}))
'''


@pytest.fixture
def c(tmp_path, monkeypatch):
    script = tmp_path / "bp.py"
    script.write_text(FAKE, encoding="utf-8")
    monkeypatch.setenv("HOMEBASE_BP", str(script))
    monkeypatch.setenv("HOMEBASE_BP_PYTHON", sys.executable)
    monkeypatch.setattr(tester_api.Slots, "quiet", lambda self: False)      # not the desk's 9:30 window, whenever the tests run
    return TestClient(app(tmp_path), base_url="http://localhost:8852")


def run(c, tool, args=None, **kw):
    return c.post("/api/tester/blueprint/run", json={"tool": tool, **({} if args is None else {"args": args})}, **kw)


def test_the_lab_lists_the_tools_every_chat_has_and_the_ideas_on_file(c):
    r = c.get("/api/tester/blueprint").json()
    assert [t["name"] for t in r["tools"]] == [s["name"] for s in blueprint_tools.SPECS] and len(r["tools"]) == 12
    by = {t["name"]: t for t in r["tools"]}
    for s in blueprint_tools.SPECS:                 # the same definition, split into its phase and its words
        t = by[s["name"]]
        assert t["inputs"] == s["inputSchema"] and s["description"] == f"{t['phase']}: {t['description']}" and t["phase"].startswith("Blueprint")
    assert by["blueprint_build"]["phase"].startswith("Blueprint phase 2, the build") and by["blueprint_portfolio"]["inputs"]["required"] == ["names", "account"]
    assert r["ideas"] == [] and r["wait_s"] == tester_api.LAB_WAIT_S == 20
    ideastore.create("nq_orb_pre")
    got = c.get("/api/tester/blueprint").json()["ideas"]
    assert [i["name"] for i in got] == ["nq_orb_pre"] and got[0]["status"] == "idea"


def test_a_tool_runs_as_a_chat_runs_it_and_answers_in_its_own_words(c, ideas_root):
    r = run(c, "blueprint_status", {"name": "nq_orb_pre"})
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["tool"] == "blueprint_status"
    text = r.json()["text"]
    assert f"RAN status nq_orb_pre --root={ideas_root} --json" in text          # the toolkit's own command line, the app's idea folder
    assert "RAN blocks" in run(c, "blueprint_blocks").json()["text"]              # no arguments at all
    # a refusal of the toolkit is the tool's answer, not a broken request: nothing was changed
    r = run(c, "blueprint_card", {"name": "bad_name", "card": {}, "settings": {}})
    assert r.status_code == 200 and r.json()["ok"] is False and "no such idea" in r.json()["text"]
    r = run(c, "blueprint_status", {"name": "Not A Name"})                        # the connector's own input check
    assert r.status_code == 200 and r.json()["ok"] is False and "name" in r.json()["text"]


def test_a_long_job_answers_with_its_id_after_twenty_seconds_at_most(c):
    for sent, want in ((None, 20), (3600, 20), (5, 5), (0, 0), (True, 20), ("soon", 20)):
        args = {"name": "nq_orb_pre", "reason": "the plain idea", **({} if sent is None else {"wait_s": sent})}
        text = run(c, "blueprint_build", args).json()["text"]
        assert (f"--wait={want}" in text) or (want == 0 and "job j1 is still going" in text), (sent, text)
    going = run(c, "blueprint_build", {"name": "nq_orb_pre", "reason": "the plain idea", "wait_s": 0}).json()["text"]
    assert "is still going" in going and "job_id='j1'" in going                  # the page's "Keep waiting" reads the id off this


def test_what_the_route_refuses(c, monkeypatch):
    assert run(c, "blueprint_nothing").status_code == 400 and "blueprint_blocks" in run(c, "blueprint_nothing").json()["detail"]
    assert run(c, "desk_status").status_code == 400, "only the blueprint tools: nothing of the desk is reachable from here"
    assert c.post("/api/tester/blueprint/run", json={"tool": "blueprint_blocks", "args": []}).status_code == 400
    assert c.post("/api/tester/blueprint/run", json={"tool": "blueprint_blocks", "more": 1}).status_code == 400
    r = run(c, "blueprint_status", {"name": "nq_orb_pre", "nonsense": 1})
    assert r.status_code == 400 and "blueprint_status" in r.json()["detail"]
    assert run(c, "blueprint_blocks", headers=EVIL).status_code == 403            # another site's page cannot run a tool
    assert c.post("/api/tester/blueprint/run", content=json.dumps({"tool": "blueprint_blocks"}), headers={"content-type": "text/plain"}).status_code in (415, 422)
    monkeypatch.setattr(tester_api.Slots, "quiet", lambda self: True)
    r = run(c, "blueprint_blocks")
    assert r.status_code == 409 and "09:20" in r.json()["detail"]
    assert c.get("/api/tester/blueprint").status_code == 200                      # looking is always allowed
