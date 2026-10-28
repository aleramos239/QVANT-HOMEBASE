"""The blueprint toolkit in the Lab (chart service, /api/tester/blueprint): the page lists THE SAME tools every chat
has (claude_mcp.blueprint_tools.SPECS) and runs them through the same code -- against a FAKE toolkit: a small script
written here that answers in the toolkit's JSON and echoes the command line it was given. No tape, no engine."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from homebase.store import ideastore
from homebase.charts import tester_api
from homebase.claude_mcp import blueprint_tools
from tests.test_tester_api import EVIL, app

FAKE = r'''
import json, sys
argv = sys.argv[1:]
if argv[:1] == ["status"] and "bad_name" in argv:
    print(json.dumps({"ok": False, "command": "card", "name": None, "status": None, "phase": 0, "round": None, "lines": [], "text": "REFUSED: no such idea",
                      "next": "", "job": None, "saved": [], "error": "no such idea"}))
    sys.exit(2)
if argv[:1] == ["blockcode"]:
    import pathlib
    log = pathlib.Path(__file__).with_name("hits.log")
    log.write_text(log.read_text() + "x" if log.exists() else "x")
    print(json.dumps({"ok": True, "command": "blockcode", "name": None, "status": None, "phase": None, "round": None, "lines": [], "text": "", "next": "", "job": None, "saved": [],
                      "error": None, "counts": {"filters": len(log.read_text())}, "sources": {"x.py:1-2": {"file": "x.py", "start": 1, "end": 2, "code": "a\nb"}},
                      "groups": [{"id": "filters", "title": "Filters", "words": "", "items": [{"id": "filter:f", "name": "f", "parts": [{"label": "L", "src": "x.py:1-2"}]}]}]}))
    sys.exit(0)
if argv[:1] == ["status"] and not [a for a in argv[1:] if not a.startswith("--")]:      # every idea on file (the board)
    print(json.dumps({"ok": True, "command": "status", "name": None, "status": None, "phase": None, "round": None, "lines": [], "text": "2 ideas", "next": "",
                      "job": None, "saved": [], "error": None, "ideas": [
                          {"name": "nq_a", "status": "idea", "phase": 0, "round": None, "group": "Ideas", "runs": [], "job": None, "wf": {"stage": "table"}, "next": "table is next"},
                          {"name": "nq_b", "status": "idea", "phase": 0, "round": None, "group": "Ideas", "runs": [], "job": None, "wf": {"stage": "test", "box": "k1_own1-r1"}, "next": "test months next"}]}))
    sys.exit(0)
print(json.dumps({"ok": True, "command": argv[0], "name": None, "status": None, "phase": None, "round": None, "lines": [],
                  "text": "RAN " + " ".join(argv), "next": "", "job": None, "saved": [], "error": None}))
'''


@pytest.fixture
def c(tmp_path, monkeypatch):
    script = tmp_path / "bp.py"
    script.write_text(FAKE, encoding="utf-8")
    monkeypatch.setenv("HOMEBASE_BP", str(script))
    monkeypatch.setenv("HOMEBASE_BP_PYTHON", sys.executable)
    monkeypatch.setenv("HOMEBASE_ARSENAL", str(tmp_path / "arsenal.json"))      # never the owner's own file
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
        if s["name"] == "blueprint_wf_oos":         # the owner's exact words (2026-10-20): no phase in front, shown whole
            assert t["phase"] == t["description"] == s["description"] and t["inputs"] == s["inputSchema"]
            continue
        assert t["inputs"] == s["inputSchema"] and s["description"] == f"{t['phase']}: {t['description']}" and t["phase"].startswith("Blueprint")
    assert by["blueprint_wf"]["phase"].startswith("Blueprint, the 3:1 walk-forward") and by["blueprint_portfolio"]["inputs"]["required"] == ["names", "account"]
    assert "blueprint_build" not in by and "blueprint_test" not in by and "blueprint_lock" not in by    # retired (the owner, 2026-10-25)
    assert r["ideas"] == []
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
    r = run(c, "blueprint_status", {"name": "bad_name"})
    assert r.status_code == 200 and r.json()["ok"] is False and "no such idea" in r.json()["text"]
    r = run(c, "blueprint_status", {"name": "Not A Name"})                        # the connector's own input check
    assert r.status_code == 200 and r.json()["ok"] is False and "name" in r.json()["text"]


WRITES = {"blueprint_card", "blueprint_code_check", "blueprint_sim", "blueprint_portfolio", "blueprint_eval_card",
          "blueprint_wf", "blueprint_wf_pick", "blueprint_wf_oos"}


def test_a_page_can_only_look_a_heat_map_a_pick_or_the_test_months_start_from_a_chat(c, tmp_path):
    """S1: the route runs only the tools that read what is saved. Every other tool is refused before the toolkit is started,
    whatever owner_said a page puts in."""
    assert set(tester_api.BP_PAGE_TOOLS) == {"blueprint_blocks", "blueprint_status", "blueprint_heatmap", "blueprint_mc"}
    assert {s["name"] for s in blueprint_tools.SPECS} - set(tester_api.BP_PAGE_TOOLS) == WRITES       # a new tool is refused until listed
    said = {"owner_said": "run it"}
    for tool, args in {"blueprint_wf_oos": {"name": "nq_orb_pre", "box": 1, **said}, "blueprint_wf": {"name": "nq_orb_pre", **said},
                       "blueprint_wf_pick": {"name": "nq_orb_pre", "box": 1}, "blueprint_card": {"name": "x1", "card": {}, "settings": {}},
                       "blueprint_code_check": {"name": "nq_orb_pre", "looked": True}, "blueprint_eval_card": {"name": "nq_orb_pre"},
                       "blueprint_sim": {"name": "nq_orb_pre", "account": "a", "attempts": 1, "fee_budget": 1},
                       "blueprint_portfolio": {"names": ["a1", "b1"], "account": "a"}}.items():
        r = run(c, tool, args)
        assert r.status_code == 403 and r.json()["detail"].startswith(f"{tool} cannot be run from a page: here you can only look"), tool
    assert run(c, "blueprint_heatmap", {"name": "nq_orb_pre"}).json()["text"].endswith("\nRAN heatmap nq_orb_pre --root=" + str(ideastore.ideas_root()) + " --json")
    assert run(c, "blueprint_mc", {"name": "nq_orb_pre"}).json()["text"].endswith("\nRAN mc nq_orb_pre --root=" + str(ideastore.ideas_root()) + " --json")


def test_the_pipeline_refuses_while_it_is_switched_off(tmp_path, monkeypatch):
    """Row S1 (safety #52): with ~/.homebase/pipeline/DISABLED on file (a temp HOME), the REAL toolkit's `bp.py pipe` and the
    Lab's pipeline routes refuse. Read-only: the toolkit refuses before it reads or runs anything, and only looks are asked
    (list, book, pause, mode off). Skipped where the research toolkit is not installed (HOMEBASE_BP / HOMEBASE_BP_PYTHON name it)."""
    python, script = blueprint_tools.toolkit()
    if not Path(script).is_file() or shutil.which(python) is None:
        pytest.skip("the research toolkit (bp.py) is not installed here")
    home = tmp_path / "home"
    proot = home / ".homebase" / "pipeline"
    proot.mkdir(parents=True)
    (proot / "DISABLED").write_text("off\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("HOMEBASE_PIPELINE_ROOT", raising=False)
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setattr(tester_api.Slots, "quiet", lambda self: False)
    for sub in (["list"], ["book"]):
        p = subprocess.run([python, script, "pipe", *sub, f"--root={proot}", "--json"], capture_output=True, text=True, timeout=60,
                           cwd=str(Path(script).parent), stdin=subprocess.DEVNULL, env={**os.environ})
        got = json.loads(p.stdout)
        assert got["ok"] is False and "the pipeline is OFF" in got["error"], (sub, p.stdout, p.stderr)
    c = TestClient(app(tmp_path), base_url="http://localhost:8852")
    r = c.get("/api/tester/pipeline")
    assert r.status_code == 503 and "the pipeline is OFF" in r.json()["detail"]
    assert "the pipeline is OFF" in c.get("/api/tester/pipeline/idea/nq_x").json()["detail"]
    for path, body in (("/api/tester/pipeline/run", {"action": "pause"}), ("/api/tester/pipeline/mode", {"mode": "off"})):
        r = c.post(path, json=body)
        assert r.status_code == 200 and r.json()["ok"] is False and "the pipeline is OFF" in r.json()["text"], (path, r.json())
    assert sorted(x.name for x in proot.iterdir()) == ["DISABLED"]       # nothing was written beside the switch


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
    assert r.status_code == 409 and "quiet window" in r.json()["detail"]
    assert c.get("/api/tester/blueprint").status_code == 200                      # looking is always allowed


def test_the_lab_lists_the_arsenal_and_keeps_the_answer_until_a_file_it_is_made_from_changes(c, tmp_path):
    r = c.get("/api/tester/arsenal")
    assert r.status_code == 200
    got = r.json()
    by = {g["id"]: g for g in got["groups"]}
    assert by["filters"]["items"][0]["parts"][0]["src"] in got["sources"], "the research toolkit's blocks, as its command answered"
    assert {"tester", "blueprint", "desk", "skills", "scripts"} <= set(by) and got["notes"] == []
    names = {i["name"] for g in got["groups"] for i in g["items"]}
    assert {"backtest", "blueprint_blocks", "desk_status"} <= names, "every chat tool is in it"
    hits = lambda: len((tmp_path / "hits.log").read_text())  # noqa: E731 -- how often the fake toolkit was asked
    assert c.get("/api/tester/arsenal").status_code == 200 and hits() == 1, "unchanged files: the kept answer, the toolkit is not asked again"
    (tmp_path / "blueprint").mkdir()
    (tmp_path / "blueprint" / "new_block.py").write_text("x = 1\n", encoding="utf-8")
    assert c.get("/api/tester/arsenal").status_code == 200 and hits() == 2, "a new file in the toolkit: built again"


def test_the_arsenal_is_saved_in_the_app_and_a_missing_toolkit_leaves_the_other_tools_and_says_so(c, monkeypatch, tmp_path):
    saved = tmp_path / "arsenal.json"
    c.get("/api/tester/arsenal")
    assert json.loads(saved.read_text(encoding="utf-8"))["counts"]["tester"] > 0
    monkeypatch.setenv("HOMEBASE_BP", str(tmp_path / "nowhere" / "bp.py"))
    r = c.get("/api/tester/arsenal")
    assert r.status_code == 200 and any("not installed" in n for n in r.json()["notes"])
    assert {g["id"] for g in r.json()["groups"]} >= {"tester", "blueprint", "desk"}
    assert c.get("/api/tester/arsenal", headers={"host": "evil.example"}).status_code == 403


# ---- the idea board and the three steps of a saved idea (WP5) ---------------------------------------------------------------

def step(c, **body):
    return c.post("/api/tester/blueprint/step", json=body)


@pytest.fixture
def steps_on(monkeypatch):
    monkeypatch.setattr(tester_api.slots, "backtests_off", lambda: False)      # a Mac: not the trading server's marker


def test_the_board_lists_every_idea_with_its_stage_and_says_whether_this_machine_runs(c, steps_on, monkeypatch):
    r = c.get("/api/tester/blueprint/board")
    assert r.status_code == 200 and [(i["name"], i["wf"]["stage"]) for i in r.json()["ideas"]] == [("nq_a", "table"), ("nq_b", "test")]
    assert r.json()["machine_runs"] is True and c.get("/api/tester/blueprint/board", headers={"host": "evil.example"}).status_code == 403
    monkeypatch.setattr(tester_api.slots, "backtests_off", lambda: True)
    assert c.get("/api/tester/blueprint/board").json()["machine_runs"] is False           # the server only shows


def test_the_board_says_why_when_the_toolkit_is_missing(c, monkeypatch, tmp_path):
    monkeypatch.setenv("HOMEBASE_BP", str(tmp_path / "nowhere" / "bp.py"))
    r = c.get("/api/tester/blueprint/board")
    assert r.status_code == 503 and "not installed" in r.json()["detail"]


def test_a_step_starts_nothing_without_the_owners_own_words(c, steps_on, tmp_path):
    for body in ({"step": "table", "name": "nq_a"}, {"step": "table", "name": "nq_a", "owner_said": "   "},
                 {"step": "pick", "name": "nq_a", "box": 3}, {"step": "oos", "name": "nq_b", "box": "k1_own1-r1", "reads_test_months_once": True},
                 {"step": "table", "name": "nq_a", "owner_said": "x" * 401}):
        r = step(c, **body)
        assert r.status_code == 400 and "Nothing was started" in r.json()["detail"], body
    assert not (tmp_path / "hits.log").exists()


def test_the_test_months_need_the_extra_confirm_and_a_box(c, steps_on):
    r = step(c, step="oos", name="nq_b", box="k1_own1-r1", owner_said="run the test months of nq_b")
    assert r.status_code == 400 and "test months once" in r.json()["detail"]
    r = step(c, step="oos", name="nq_b", owner_said="run it", reads_test_months_once=True)
    assert r.status_code == 200 and r.json()["ok"] is False and "box" in r.json()["text"]       # the tool's own refusal


def test_each_step_runs_the_tool_a_chat_runs_with_the_words_as_typed(c, steps_on, ideas_root):
    said = "  run the table of nq_a, yes "
    r = step(c, step="table", name="nq_a", owner_said=said)
    assert r.status_code == 200 and r.json()["ok"] is True
    assert f"RAN wf run nq_a --owner-said={said} --wait=45" in r.json()["text"]       # verbatim: not trimmed
    ideastore.create("nq_b")
    r = step(c, step="pick", name="nq_b", box=7, owner_said="box 7")
    assert r.json()["ok"] is True and f"RAN wf pick nq_b 7 --root={ideas_root}" in r.json()["text"]
    log = [json.loads(x) for x in (ideastore.idea_dir("nq_b") / "log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(x["event"] == "pick_said" and x["said"] == "box 7" and x["box"] == 7 for x in log)      # his words stay with the pick
    r = step(c, step="oos", name="nq_b", box="k1_own1-r1", owner_said="read the test months", reads_test_months_once=True)
    assert r.json()["ok"] is True and "RAN wf oos nq_b k1_own1-r1 --owner-said=read the test months --wait=45" in r.json()["text"]


def test_a_step_is_refused_on_the_server_in_a_quiet_window_and_for_bad_input(c, steps_on, monkeypatch):
    ok = dict(step="table", name="nq_a", owner_said="go")
    assert step(c, **{**ok, "step": "heatmap"}).status_code == 400 and step(c, **{**ok, "more": 1}).status_code == 400
    assert c.post("/api/tester/blueprint/step", json=ok, headers=EVIL).status_code == 403
    assert step(c, **{**ok, "name": "Not A Name"}).json()["ok"] is False
    monkeypatch.setattr(tester_api.Slots, "quiet", lambda self: True)
    assert step(c, **ok).status_code == 409 and "quiet window" in step(c, **ok).json()["detail"]
    monkeypatch.setattr(tester_api.Slots, "quiet", lambda self: False)
    monkeypatch.setattr(tester_api.slots, "backtests_off", lambda: True)
    r = step(c, **ok)
    assert r.status_code == 409 and "does not run backtests" in r.json()["detail"]


def test_the_page_route_still_only_looks(c):
    assert set(tester_api.BP_PAGE_TOOLS) == {"blueprint_blocks", "blueprint_status", "blueprint_heatmap", "blueprint_mc"}
