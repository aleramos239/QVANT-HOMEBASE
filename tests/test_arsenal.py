"""The arsenal (homebase/arsenal.py): every tool we have in one catalog, derived from the code and the skill folders, saved in the app."""
import json

from homebase import arsenal
from homebase.claude_mcp import tools

RESEARCH = {"groups": [{"id": "filters", "title": "Filters", "words": "w", "items": [{"id": "filter:x", "name": "x", "parts": []}]}], "sources": {}}


def make(tmp_path, monkeypatch, research=lambda: RESEARCH):
    sk = tmp_path / "skills"
    (sk / "demo").mkdir(parents=True)
    (sk / "demo" / "SKILL.md").write_text("---\nname: demo\ndescription: Use when a demo is wanted. More words.\n---\n# demo\n", encoding="utf-8")
    (sk / "demo" / "run.py").write_text("print('hi')\n", encoding="utf-8")
    monkeypatch.setattr(arsenal, "skill_dirs", lambda: [sk])
    monkeypatch.setenv(arsenal.ENV, str(tmp_path / "arsenal.json"))
    return arsenal.build(research)


def items(cat):
    return {i["name"]: i for g in cat["groups"] for i in g["items"]}


def test_every_chat_tool_is_in_it_with_its_definition_and_the_method_that_runs_it(tmp_path, monkeypatch):
    cat = make(tmp_path, monkeypatch)
    got = items(cat)
    assert {s["name"] for s in tools.SPECS} <= set(got), "every tool of the connector, none typed here"
    bt = got["backtest"]
    assert [p["label"] for p in bt["parts"]][:2] == ["What a chat sees: its name, words and inputs", "What it does (Toolbox.t_backtest)"]
    for it in (got[s["name"]] for s in tools.SPECS):
        assert it["parts"] and it["runs"] is None and it["words"], it["name"]
        for p in it["parts"]:
            s = cat["sources"][p["src"]]
            assert s["code"] and p["src"] == f"{s['file']}:{s['start']}-{s['end']}"
    assert {g["id"] for g in cat["groups"] if g["id"] in ("tester", "blueprint", "pipeline", "desk")} == {"tester", "blueprint", "pipeline", "desk"}
    assert "blueprint_blocks" in {i["name"] for g in cat["groups"] if g["id"] == "blueprint" for i in g["items"]}
    assert {i["name"] for g in cat["groups"] if g["id"] == "pipeline" for i in g["items"]} == {s["name"] for s in tools.SPECS if s["name"].startswith("pipeline_")}


def test_skills_and_scripts_are_read_from_their_folders(tmp_path, monkeypatch):
    cat = make(tmp_path, monkeypatch)
    sk = items(cat)["demo"]
    assert sk["words"] == "Use when a demo is wanted." and [p["label"] for p in sk["parts"]] == ["The skill file (SKILL.md)", "run.py"]
    skill_file = cat["sources"][sk["parts"][0]["src"]]
    assert skill_file["plain"] is True and "# demo" in skill_file["code"]
    assert "plain" not in cat["sources"][sk["parts"][1]["src"]]
    assert {"bp.py", "preopen_check.py"} <= set(items(cat)), "the repository's scripts"


def test_a_long_file_is_cut_and_says_so(tmp_path, monkeypatch):
    f = tmp_path / "long.py"
    f.write_text("\n".join(f"x{i} = {i}" for i in range(arsenal.MAX_LINES + 50)) + "\n", encoding="utf-8")
    src = arsenal.Sources()
    s = src.by_id[src.whole(f)]
    assert s["end"] == arsenal.MAX_LINES and "first 500" in s["note"] and s["code"].count("\n") == arsenal.MAX_LINES - 1


def test_a_missing_toolkit_leaves_the_other_tools_and_says_what_is_missing(tmp_path, monkeypatch):
    def broken():
        raise RuntimeError("bp.py is missing")
    cat = make(tmp_path, monkeypatch, broken)
    assert cat["notes"] and "bp.py is missing" in cat["notes"][0] and "backtest" in items(cat)
    assert arsenal.get(broken, path=tmp_path / "a.json")["notes"] and not (tmp_path / "a.json").exists(), "a partial catalog is not saved"


def test_the_catalog_is_saved_and_kept_while_its_files_do_not_change(tmp_path, monkeypatch):
    make(tmp_path, monkeypatch)
    calls = []

    def research():
        calls.append(1)
        return RESEARCH
    path = tmp_path / "a.json"
    first = arsenal.get(research, (1, 1), path)
    assert path.is_file() and json.loads(path.read_text(encoding="utf-8"))["counts"] == first["counts"] and len(calls) == 1
    assert arsenal.get(research, (1, 1), path)["built"] == first["built"] and len(calls) == 1, "same stamp: the saved catalog"
    arsenal.get(research, (2, 1), path)
    assert len(calls) == 2, "the research toolkit changed: built again"
    (tmp_path / "skills" / "demo" / "SKILL.md").write_text("---\nname: demo\ndescription: Changed.\n---\n", encoding="utf-8")
    assert items(arsenal.get(research, (2, 1), path))["demo"]["words"] == "Changed." and len(calls) == 3, "a skill changed: built again"
    assert arsenal.load(tmp_path / "nothing.json") is None


def test_the_blocks_are_read_from_a_named_source_checkout_else_a_clean_worktree_of_main_else_this_one(tmp_path, monkeypatch):
    from homebase.claude_mcp import blueprint_tools as BT
    monkeypatch.delenv(BT.ENV_BP, raising=False)
    monkeypatch.delenv(arsenal.ENV_SRC, raising=False)
    monkeypatch.setattr(arsenal.paths, "repo_root", lambda: tmp_path / "repo")
    assert arsenal.research_bp() == tmp_path / "repo" / "research" / "edge-library" / "bp.py", "nothing else there: the app's own toolkit"
    wt = tmp_path / "repo" / arsenal.SRC_WORKTREE / "research" / "edge-library"
    wt.mkdir(parents=True)
    (wt / "bp.py").write_text("", encoding="utf-8")
    assert arsenal.research_bp() == wt / "bp.py", "a clean worktree of main is read when it is there"
    monkeypatch.setenv(BT.ENV_BP, str(tmp_path / "other" / "bp.py"))
    assert arsenal.research_bp() == tmp_path / "other" / "bp.py", "a toolkit named outright wins over the worktree"
    src = tmp_path / "src" / "research" / "edge-library"
    src.mkdir(parents=True)
    (src / "bp.py").write_text("", encoding="utf-8")
    (src / "blueprint").mkdir()
    (src / "blueprint" / "x.py").write_text("", encoding="utf-8")
    monkeypatch.setenv(arsenal.ENV_SRC, str(tmp_path / "src"))
    assert arsenal.research_bp() == src / "bp.py" and arsenal.research_stamp()[0] == str(src / "bp.py") and arsenal.research_stamp()[2] == 2
