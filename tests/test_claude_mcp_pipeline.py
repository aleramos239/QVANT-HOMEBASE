"""The connector's pipeline tools (homebase.claude_mcp.pipeline_tools): the five tool definitions, the exact command
line each one runs -- `bp.py pipe <sub> ... --root=<the PIPELINE's folder> --json`, through the blueprint tools' one
way to the toolkit -- and what comes back, against a FAKE toolkit: a small script written here that answers `pipe`
in the JSON and the words of the real one (research/edge-library/blueprint/pipe_runner.py) and keeps a small state
of its own under --root. No engine, no tape, no runner: `pipe start` only writes a pid down there.
ONE test at the end runs the same tools against the REAL bp.py (skipped where the research engine's Python is not
installed): add, list, show, pause, resume, a refused yes, the book -- the commands that need no engine run -- so
the fake and the real one cannot drift apart unseen.
Temp folders only: the pipeline root is a temp folder, HOME is a temp folder that must stay empty."""
from __future__ import annotations

import ast
import copy
import json
import os
import pwd
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from homebase import arsenal, ideastore, paths
from homebase.claude_mcp import blueprint_tools, pipeline_tools, protocol, tools
from homebase.claude_mcp.client import Client, ToolError

REPO = Path(__file__).resolve().parent.parent
TOOLKIT = REPO / "research" / "edge-library"
REAL_HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)                      # the real one, whatever HOME says
REAL_PYTHON = REPO / ".venv-research" / "bin" / "python"                # the research engine's (blueprint_tools.toolkit)
NAME = "fvg_open"
CARD = {"name": NAME, "why": "Late buyers chase the first gap after the open.", "loser": "Traders who fade the first move.",   # the toolkit's own example
        "source": "owner", "market": "NQ", "session": "nyam", "sides": "both", "sides_why": "",
        "ways": [{"family": "fvg", "main_setting": "min_gap", "values": ["0.1", "0.25", "0.5"], "fixed": {"mode": "touch"}, "limits": {}}],
        "indicators": [{"block": "trend", "side": "with", "why": "A gap with the trend has more room."}]}
STATUSES = ["queued", "running", "stopped", "code_problem", "awaiting_owner", "book", "refused"]
LABELS = ["Waiting", "Running", "Stopped", "Problem", "Passed", "In the book", "Refused"]
BOOK = {"name": "orb_pre", "label": "stands alone", "family": "orb", "market": "NQ", "session": "pre", "bar": "5", "why": "The 08:30 burst carries on."}

FAKE = r'''
"""A fake research toolkit that knows `pipe`: the pipeline's commands, in the JSON and the words of the real one."""
import json, os, sys, time

argv = sys.argv[1:]
stdin = sys.stdin.read()
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "calls.jsonl"), "a") as f:
    f.write(json.dumps({"argv": argv, "stdin": stdin, "cwd": os.getcwd(), "python": sys.executable}) + "\n")
pos = [a for a in argv if not a.startswith("--")]
opt = dict((a[2:].split("=", 1) if "=" in a else (a[2:], True)) for a in argv if a.startswith("--"))
root, UTC = opt["root"], "2026-10-08T04:44:21+00:00"


def result(command, name=None, **more):
    r = {"ok": True, "command": command, "name": name, "status": None, "phase": None, "round": None, "lines": [],
         "text": "", "next": "", "job": None, "saved": [], "error": None}
    r.update(more)
    return r


def out(r, code=0):
    print(json.dumps(r))
    sys.exit(code)


if "sleepy" in pos:
    time.sleep(60)
if pos[0] != "pipe":                                    # a command of the blueprint: only its command line is of interest here
    out(result(pos[0], text="RAN " + " ".join(argv)))
sub, name, cmd = pos[1], (pos[2] if len(pos) > 2 else None), "pipe " + pos[1]
file = os.path.join(root, "fake.json")
S = json.load(open(file)) if os.path.exists(file) else {"ideas": {}, "paused": False, "pid": None, "book": []}


def save():                                             # a look makes no folder: only what changes something writes
    os.makedirs(root, exist_ok=True)
    with open(file, "w") as f:
        json.dump(S, f)


def refuse(why, who=None, **more):
    out(result(cmd, who, ok=False, error=why, text="REFUSED: " + why, **more), 2)


def row(line, passed, words):
    return {"line": line, "passed": passed, "number": 1, "need": 1, "text": "%s %s %s" % (line, "PASS" if passed else "FAIL", words)}


def live():
    q = [n for n, i in S["ideas"].items() if i["state"]["status"] in ("queued", "running")]
    return sorted(q, key=lambda n: not S["ideas"][n]["inbox"])


def reached(s):
    return s["stopped_at"] if s["stopped_at"] is not None else s["stage"]


def idea(what):
    if name not in S["ideas"]:
        refuse("no pipeline idea %r under %s" % (name, root), name)
    st = S["ideas"][name]["state"]
    if what and st["status"] != "awaiting_owner":
        refuse("%s is %s: only an idea that passed every stage and waits for the owner (awaiting_owner) is %s" % (name, st["status"], what), name)
    return S["ideas"][name]


if name == "crash_me":
    sys.stderr.write('Traceback (most recent call last):\n  File "bp.py", line 1\nZeroDivisionError: division by zero\n')
    sys.exit(1)

if sub == "add":
    card = json.loads(stdin)
    extra = sorted(set(card) - {"name", "why", "loser", "source", "market", "session", "sides", "sides_why", "ways", "indicators"})
    if extra:
        refuse("unknown fields %s: a pipeline card is {name, why, loser, source, market, session, sides, sides_why, ways, indicators}" % extra)
    who = card.get("name")
    rows = [row("P0.1", bool(card.get("why")), "the reason in one sentence, and who loses" if card.get("why") else "it does not say why it should make money (why, one sentence)"),
            row("P0.2", all(len(w["values"]) == 3 for w in card["ways"]), "%d way to enter" % len(card["ways"])
                if all(len(w["values"]) == 3 for w in card["ways"]) else "way a: min_gap has %d values (need 3, each once)" % len(card["ways"][0]["values"])),
            row("P0.3", True, "%d indicator, each tried alone" % len(card.get("indicators", []))), row("P0.4", True, "both sides")]
    bad = [r["text"] for r in rows if not r["passed"]]
    if bad:
        refuse("the card is not whole: " + "; ".join(bad), who, lines=rows)
    if who in S["ideas"]:
        refuse("a pipeline card named %r is already on file (added %s, status %s): give the new card another name" % (who, UTC, S["ideas"][who]["state"]["status"]))
    sig = json.dumps([card["market"], card["session"], card["sides"], card["ways"]], sort_keys=True)
    for n, i in S["ideas"].items():
        if i["sig"] == sig:
            refuse("%r is the same card as %r, added %s: the same market, session, sides and ways under another name are the same card, "
                   "and a card is run once" % (who, n, UTC))
    st = {"name": who, "status": "queued", "stage": None, "stopped_at": None, "why": "", "tries": 0, "picked": None, "added_utc": UTC,
          "updated_utc": UTC, "source": card["source"], "family": card["ways"][0]["family"]}
    subs = [who + "_a1", who + "_a5"]
    S["ideas"][who] = {"card": dict(card, subs=[{"name": s, "way": 0, "bar": s[-1], "spec": {"name": s}} for s in subs]), "state": st, "stages": {},
                       "sig": sig, "inbox": "inbox" in opt}
    save()
    q = live()
    out(result(cmd, who, status="queued", lines=rows, state=st, subs=subs, saved=[os.path.join(root, "p", who)],
               text="%s is in the queue: place %d of %d%s.\nStage 1 will run 2 heat maps: %s." % (
                   who, q.index(who) + 1, len(q), " (inbox: it goes first)" if "inbox" in opt else "", ", ".join(subs)),
               next="bp.py pipe start runs the queue by itself; bp.py pipe list shows where each idea is."))
if sub == "list":
    q = live()
    ideas = [S["ideas"][n]["state"] for n in q] + [i["state"] for n, i in S["ideas"].items() if n not in q]
    counts = {}
    for s in ideas:
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    text = ["name  family  status  stage  tries  why"] + ["  ".join(str(x) for x in (s["name"], s["family"], s["status"], "-" if reached(s) is None else reached(s),
                                                                                    s["tries"], s["why"])).rstrip() for s in ideas] if ideas else ["no idea is on file"]
    text += ["", "%d idea%s" % (len(ideas), "" if len(ideas) == 1 else "s") + (": " + ", ".join("%d %s" % (v, k) for k, v in counts.items()) if ideas else ""),
             "runner: " + ("working (pid %d)" % S["pid"] if S["pid"] else "not working") + " · queue: " + ("paused" if S["paused"] else "not paused")]
    out(result(cmd, running=bool(S["pid"]), pid=S["pid"], paused=S["paused"], counts=counts, ideas=ideas, text="\n".join(text),
               next="" if S["pid"] or not q else "bp.py pipe start runs the queue."))
if sub == "show":
    i = idea(None)
    st, card = i["state"], i["card"]
    text = ["%s: %s on %s %s, sides %s (source %s)" % (name, st["family"], card["market"], card["session"], card["sides"], st["source"]),
            "why: " + card["why"], "loser: " + card["loser"],
            "status: %s · stage %s · tries %d" % (st["status"], "-" if reached(st) is None else reached(st), st["tries"])]
    if st["why"]:
        text.append("%s: %s" % ("refused" if st["status"] == "refused" else "stopped", st["why"]))
    text += ["stage %s %-4s %s: %s" % (n, {True: "PASS", False: "FAIL"}.get(c["passed"], "n/a"), c["name"], c["text"].splitlines()[0])
             for n, c in sorted(i["stages"].items())]
    out(result(cmd, name, status=st["status"], state=st, card=card, stages=i["stages"], text="\n".join(text),
               next="bp.py pipe approve %s, or bp.py pipe refuse %s --why=TEXT." % (name, name) if st["status"] == "awaiting_owner" else ""))
if sub == "start":
    already = bool(S["pid"])
    if not already:
        S["pid"] = 4242
        save()
    text = "a runner is already working (pid 4242): nothing was started" if already else "the runner is started (pid 4242): it works through the queue by itself"
    out(result(cmd, pid=4242, already=already, paused=S["paused"], text=text + (". The queue is PAUSED: bp.py pipe resume lets it work" if S["paused"] else ""),
               next="bp.py pipe list shows where each idea is."))
if sub in ("pause", "resume"):
    S["paused"] = sub == "pause"
    save()
    text = ("the queue is paused: the runner stops after the stage in hand" if S["paused"] else
            "the queue is not paused: " + ("the runner carries on" if S["pid"] else "no runner is working"))
    out(result(cmd, paused=S["paused"], running=bool(S["pid"]), text=text,
               next="bp.py pipe resume carries on." if S["paused"] else "" if S["pid"] else "bp.py pipe start runs the queue."))
if sub == "approve":
    i = idea("approved")
    S["book"].append(i["stages"]["7"]["book"])
    i["state"]["status"] = "book"
    save()
    where = os.path.join(root, "book", name + ".json")
    out(result(cmd, name, status="book", state=i["state"], saved=[where], text="%s is in the book (%s)" % (name, where)))
if sub == "refuse":
    i = idea("refused")
    why = " ".join(str(opt.get("why") or "").split()) if opt.get("why") is not True else ""
    if not why:
        refuse("refusing %s needs the reason (bp.py pipe refuse %s --why=TEXT): it is kept with the idea" % (name, name), name)
    i["state"].update(status="refused", why=why)
    save()
    out(result(cmd, name, status="refused", state=i["state"], text="%s is refused: %s" % (name, why)))
if sub == "book":
    keys = ("name", "label", "family", "market", "session", "bar")
    text = ["  ".join(keys)] + ["  ".join(str(c.get(k) or "-") for k in keys) for c in S["book"]] if S["book"] else ["the book is empty"]
    out(result(cmd, book=S["book"], text="\n".join(text)))
refuse("pipe %s: no command of the pipeline (add, list, show, start, pause, resume, approve, refuse, book)" % sub)
'''


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """No test here may fall back to the real ~/.homebase: HOME is a temp folder (the toolkit child inherits it),
    nothing may appear in it, and no test makes the real ~/.homebase/pipeline."""
    h, real = tmp_path / "home", REAL_HOME / ".homebase" / "pipeline"
    h.mkdir()
    was = real.exists()
    monkeypatch.setenv("HOME", str(h))
    yield h
    assert not (h / ".homebase").exists() and real.exists() == was


@pytest.fixture
def proot(tmp_path, monkeypatch):
    """The pipeline's own folder for this test: a temp one that is not there yet (HOMEBASE_PIPELINE_ROOT)."""
    d = tmp_path / "pipeline"
    monkeypatch.setenv(pipeline_tools.ENV_ROOT, str(d))
    return d


class Fake:
    def __init__(self, folder: Path):
        self.script = folder / "bp.py"
        self.script.write_text(FAKE, encoding="utf-8")
        self.log = folder / "calls.jsonl"

    def calls(self) -> list[dict]:
        return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []

    def argv(self) -> list[str]:
        return self.calls()[-1]["argv"]


@pytest.fixture
def fake(tmp_path, monkeypatch, proot):
    folder = tmp_path / "toolkit"
    folder.mkdir()
    f = Fake(folder)
    monkeypatch.setenv(blueprint_tools.ENV_BP, str(f.script))
    monkeypatch.setenv(blueprint_tools.ENV_PYTHON, sys.executable)
    return f


def box() -> tools.Toolbox:
    return tools.Toolbox(Client("http://127.0.0.1:1"), sleep=lambda s: None)      # no chart service is ever asked


def rpc(srv, method, params=None, rid=1):
    msg = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params is not None:
        msg["params"] = params
    return srv.handle(msg)


def tail(proot) -> list[str]:
    """What every command line of the pipeline ends with: the PIPELINE's folder, then --json."""
    return [f"--root={proot}", "--json"]


def card(**more) -> dict:
    return {**copy.deepcopy(CARD), **more}


def seed(proot: Path, name: str, status: str, **state) -> None:
    """An idea the runner has worked on, written straight into the fake's state: no runner is ever started here."""
    file = proot / "fake.json"
    S = json.loads(file.read_text()) if file.exists() else {"ideas": {}, "paused": False, "pid": None, "book": []}
    stages = {"0": {"stage": 0, "name": "idea card", "passed": True, "result": "pass", "text": "the card is whole",
                    "lines": [{"line": "P0.1", "passed": True, "number": 15, "need": 8, "text": "P0.1 PASS the reason in one sentence, and who loses"}]},
              "1": {"stage": 1, "name": "raw heat map", "passed": status != "stopped", "result": "fail" if status == "stopped" else "strict",
                    "text": f"{name}_a5: 44 % of boxes profitable\nthe other heat map is no better",
                    "lines": [{"line": "P1.1", "passed": status != "stopped", "number": 0.44, "need": 0.6,
                               "text": f"{name}_a5 P1.1 {'FAIL' if status == 'stopped' else 'PASS'} 44 % of boxes profitable (need over 60 %)"}]}}
    if status in ("awaiting_owner", "book"):
        stages["7"] = {"stage": 7, "name": "the owner's look", "passed": None, "result": "awaiting owner", "text": "the book card is ready", "lines": [],
                       "book": {**BOOK, "name": name}}
    st = {"name": name, "status": status, "stage": 1, "stopped_at": None, "why": "", "tries": 2, "picked": None, "added_utc": "2026-10-08T04:44:21+00:00",
          "updated_utc": "2026-10-08T05:10:00+00:00", "source": "claude", "family": "orb", **state}
    S["ideas"][name] = {"card": card(name=name, ways=[{"family": "orb", "main_setting": "or_min", "values": [5, 15, 30], "fixed": {}, "limits": {}}], indicators=[]),
                        "state": st, "stages": stages, "sig": name, "inbox": False}
    proot.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(S))


def texts(o) -> list[str]:
    """Every description a chat reads in a tool definition, the nested ones too."""
    if isinstance(o, dict):
        return [v for k, v in o.items() if k == "description" and isinstance(v, str)] + [t for v in o.values() for t in texts(v)]
    return [t for v in o for t in texts(v)] if isinstance(o, list) else []


def toolkits(rel: str, name: str):
    """A constant of the real toolkit, read from its TEXT (the app never imports research code): `name = <a literal>`."""
    f = TOOLKIT / rel
    if not f.is_file():
        pytest.skip(f"no research toolkit in this checkout ({f})")
    for n in ast.parse(f.read_text(encoding="utf-8")).body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets):
            return n.value
    raise AssertionError(f"{rel} has no {name}")


# ---------------------------------------------------------------- the five tools

REQUIRED = {"pipeline_add": ["card"], "pipeline_status": [], "pipeline_control": ["action"], "pipeline_decide": ["name", "decision"],
            "pipeline_book": []}
INPUTS = {"pipeline_add": ["card", "inbox"], "pipeline_status": ["name"], "pipeline_control": ["action"],
          "pipeline_decide": ["name", "decision", "why"], "pipeline_book": []}
HEAD = {"pipeline_add": "Pipeline, add an idea: ", "pipeline_status": "Pipeline, where things stand: ", "pipeline_control": "Pipeline, the runner: ",
        "pipeline_decide": "Pipeline, the owner's yes or no: ", "pipeline_book": "Pipeline, the book: "}


def test_the_five_tools_their_inputs_and_what_each_requires():
    specs = {s["name"]: s for s in pipeline_tools.SPECS}
    assert list(specs) == list(REQUIRED) and len(specs) == 5
    listed = {s["name"]: s for s in tools.Toolbox().specs()}
    for name, spec in specs.items():
        schema = spec["inputSchema"]
        assert listed[name] is spec and callable(getattr(tools.Toolbox, f"t_{name}"))
        assert schema["required"] == REQUIRED[name] and list(schema["properties"]) == INPUTS[name], name
        assert schema["type"] == "object" and schema["additionalProperties"] is False
        assert spec["description"].startswith(HEAD[name]), name               # each says what it is of, as the blueprint's do
        json.dumps(spec)
    names = tools.Toolbox().names()                                         # after the blueprint's, before the desk's
    assert names[names.index("blueprint_mc") + 1:names.index("desk_status")] == list(REQUIRED) and len(names) == 42
    props = {n: s["inputSchema"]["properties"] for n, s in specs.items()}
    assert props["pipeline_control"]["action"]["enum"] == ["start", "pause", "resume"] == list(pipeline_tools.ACTIONS)
    assert props["pipeline_decide"]["decision"]["enum"] == ["approve", "refuse"] == list(pipeline_tools.DECISIONS)
    assert props["pipeline_add"]["inbox"]["type"] == "boolean" and "Default false." in props["pipeline_add"]["inbox"]["description"]
    for reads in ("pipeline_status", "pipeline_book"):
        assert specs[reads]["description"].endswith("Runs nothing.")
    for status in STATUSES:                                                  # a chat reads the toolkit's own words in the queue
        assert status in specs["pipeline_status"]["description"], status


def test_the_add_tool_teaches_a_chat_how_to_write_a_card():
    spec = pipeline_tools.SPECS[0]
    said, c = spec["description"], spec["inputSchema"]["properties"]["card"]
    for what in ("Call blueprint_blocks first: it lists the entry rules (families) with their settings, and a card uses only those",
                 "ONE market (NQ, ES or GC)", "ONE session (asia, london, pre, nyam, mid or pm)", "sides (both, or long / short with sides_why)",
                 "1 to 3 ways to enter, each a family, ONE main setting of it and EXACTLY 3 values", "A card names NO indicator: none is tried.",
                 "The bars are always 1 and 5 minutes", "a card does not choose them",
                 "The same idea (the same market, session, sides and ways) cannot be added twice, not under another name either.",
                 "Nothing is chosen after the run starts: every choice is on the card.",
                 "A card with a line missing is refused with the lines that fail, and nothing is saved."):
        assert what in said, what
    assert c["required"] == ["name", "why", "loser", "source", "market", "session", "sides", "ways"] and c["additionalProperties"] is False
    p = c["properties"]
    assert list(p) == [*CARD, "ref"], "the card's fields, as the toolkit names them and in its order; ref (which paper / book / course) is optional, last"
    assert p["market"]["enum"] == ["NQ", "ES", "GC"] and p["session"]["enum"] == ["asia", "london", "pre", "nyam", "mid", "pm"]
    assert p["sides"]["enum"] == ["both", "long", "short"] and p["source"]["enum"] == ["owner", "video", "claude", "wiki", "paper", "book", "course"]
    way, ind = p["ways"]["items"], p["indicators"]["items"]
    assert (p["ways"]["minItems"], p["ways"]["maxItems"]) == (1, 3) and (way["properties"]["values"]["minItems"], way["properties"]["values"]["maxItems"]) == (3, 3)
    assert p["indicators"]["maxItems"] == 5 and "minItems" not in p["indicators"]
    assert list(way["properties"]) == list(CARD["ways"][0]) and way["required"] == ["family", "main_setting", "values"]
    assert list(ind["properties"]) == list(CARD["indicators"][0]) == ind["required"]
    assert way["additionalProperties"] is False and ind["additionalProperties"] is False
    assert not re.search(r"\beve\b|\bevening\b", "\n".join(texts(pipeline_tools.SPECS))), "the evening session is not in this version"
    assert set(c["required"]) <= set(CARD) <= set(p), "the card these tests send is in the format"


def test_the_cards_limits_and_names_are_the_toolkits_own():
    """What the schema types -- the limits, the fields, the name -- is held against the toolkit's files, read as TEXT."""
    f = TOOLKIT / "blueprint" / "templates" / "pipeline.json"
    if not f.is_file():
        pytest.skip(f"no research toolkit in this checkout ({f})")
    lim = json.loads(f.read_text(encoding="utf-8"))["card"]
    p = pipeline_tools.SPECS[0]["inputSchema"]["properties"]["card"]["properties"]
    vals = p["ways"]["items"]["properties"]["values"]
    assert [p["ways"]["minItems"], p["ways"]["maxItems"]] == lim["ways"] and vals["minItems"] == vals["maxItems"] == lim["values"]
    assert [0, p["indicators"]["maxItems"]] == lim["indicators"] and lim["bars"] == ["1", "5"]
    assert p["market"]["enum"] == lim["markets"] and p["session"]["enum"] == lim["sessions"]
    lit = lambda rel, name: ast.literal_eval(toolkits(rel, name))  # noqa: E731
    assert list(p) == [*lit("blueprint/pipe_card.py", "KEYS"), *lit("blueprint/pipe_card.py", "OPTIONAL")] and p["source"]["enum"] == list(lit("blueprint/pipe_card.py", "SOURCES"))
    assert list(p["ways"]["items"]["properties"]) == list(lit("blueprint/pipe_card.py", "WAY_KEYS"))
    assert list(p["indicators"]["items"]["properties"]) == list(lit("blueprint/pipe_card.py", "IND_KEYS"))
    assert toolkits("blueprint/pipe_store.py", "NAME").args[0].value == pipeline_tools.NAME_RE.pattern
    assert list(lit("blueprint/pipe_store.py", "STATUS")) == STATUSES == list(pipeline_tools.LABELS)
    assert [s.lower() for s in (x["name"] for x in pipeline_tools.STAGES)] == list(lit("blueprint/pipe_runner.py", "NAMES"))
    assert lit("blueprint/pipe_store.py", "ENV") == pipeline_tools.ENV_ROOT
    assert set(lit("blueprint/pipe_runner.py", "SUBS")) == {"add", "list", "show", "book", "rerun", "pick", "luck", "near", *pipeline_tools.ACTIONS, *pipeline_tools.DECISIONS}      # (rerun, pick, luck, near: the command line only; the luck count is the last line of the book)


def test_the_decide_tool_says_it_is_used_only_on_the_owners_word():
    spec = next(s for s in pipeline_tools.SPECS if s["name"] == "pipeline_decide")
    assert ("USE IT ONLY ON THE OWNER'S WORD: show him the idea first (pipeline_status with its name), and call this only "
            "after he has said yes or no in chat -- never on your own judgment.") in spec["description"]
    assert "Refused for an idea in any other status." in spec["description"]
    why = spec["inputSchema"]["properties"]["why"]
    assert "needed to refuse" in why["description"] and "why" not in spec["inputSchema"]["required"]
    control = next(s for s in pipeline_tools.SPECS if s["name"] == "pipeline_control")
    assert control["description"].endswith("No stage can be skipped and no pass line can be changed from here.")


def test_every_chat_is_told_about_the_pipeline():
    srv = protocol.Server(box())
    init = rpc(srv, "initialize", {"protocolVersion": "2025-06-18"})["result"]
    assert ("The strategy pipeline tests idea cards by itself, stage by stage: pipeline_add (one card; blueprint_blocks "
            "first), pipeline_control (start / pause / resume its runner), pipeline_status (the queue, or one idea in "
            "full), pipeline_book, and pipeline_decide (approve / refuse an idea that passed, only on the owner's word). ") in init["instructions"]
    assert init["serverInfo"]["version"] == protocol.SERVER_VERSION == "1.6.0"
    listed = {t["name"]: t for t in rpc(srv, "tools/list")["result"]["tools"]}
    assert set(REQUIRED) <= set(listed) and all(listed[n]["inputSchema"] == s["inputSchema"] for n, s in ((s["name"], s) for s in pipeline_tools.SPECS))


def test_the_arsenal_lists_them_as_the_pipelines_tools_with_their_definitions():
    heads, items = arsenal.chat_tools(arsenal.Sources())
    assert [h[0] for h in heads] == ["tester", "blueprint", "pipeline", "desk"] and [i["name"] for i in items["pipeline"]] == list(REQUIRED)
    assert not {i["name"] for k in ("tester", "blueprint", "desk") for i in items[k]} & set(REQUIRED)
    add = items["pipeline"][0]
    assert add["sub"] == "Pipeline, add an idea" and add["words"].startswith("put ONE idea card in the queue of the strategy pipeline")
    assert [p["label"] for p in add["parts"]][:2] == ["What a chat sees: its name, words and inputs", "What it does (Toolbox.t_pipeline_add)"]
    assert "It calls PipelineMixin._pipe" in [p["label"] for p in add["parts"]]


# ---------------------------------------------------------------- the words the Lab's pages show

def test_every_status_has_the_pages_word_and_an_unknown_one_is_shown_as_it_is():
    assert pipeline_tools.LABELS == dict(zip(STATUSES, LABELS))
    assert [pipeline_tools.label(s) for s in STATUSES] == LABELS and pipeline_tools.label("parked") == "parked"
    got = pipeline_tools.rows([{"name": "a", "status": "awaiting_owner", "why": ""}, {"name": "b", "status": "code_problem"}, "not a row"])
    assert got == [{"name": "a", "status": "awaiting_owner", "why": "", "label": "Passed"}, {"name": "b", "status": "code_problem", "label": "Problem"}]
    assert pipeline_tools.rows(None) == []
    n = pipeline_tools.counts([{"status": "queued"}, {"status": "queued"}, {"status": "book"}, {"status": "parked"}])
    assert list(n) == [*LABELS, "parked"] and n == {**dict.fromkeys(LABELS, 0), "Waiting": 2, "In the book": 1, "parked": 1}
    assert pipeline_tools.counts([]) == dict.fromkeys(LABELS, 0)


def test_the_eight_stages_are_written_once_a_plain_sentence_each():
    S = pipeline_tools.STAGES
    assert [s["n"] for s in S] == list(range(8)) and all(list(s) == ["n", "name", "words"] for s in S)
    assert [s["name"] for s in S] == ["Idea card", "Raw heat map", "Machine check", "Indicators", "Proof", "Pick one box and lock", "Unseen days",
                                      "The owner's look"]
    assert S[1]["words"] == "Does a region of the map make money, and does a box in it pass every build line of a box?"
    assert S[3]["words"] == "Does the picked variant make money on its side(s), even without its best trades?" and S[4]["words"] == "Does the picked variant hold up against luck?"      # variant mode, 2026-10-08
    assert S[5]["words"] == "Does the picked stop and target hold up on its own, so the rule can be frozen?"
    for s in S:
        assert s["words"][0].isupper() and s["words"][-1] in "?." and len(s["words"].split()) >= 6, s
        assert not re.search(r"sub-idea|signature|\bstore\b|stage card|P\d\.\d|\bOOS\b|Monte Carlo", s["words"] + s["name"]), s    # no jargon on the page


# ---------------------------------------------------------------- where the pipeline is, and the one way to the toolkit

def test_the_pipeline_has_a_folder_of_its_own_that_can_be_moved(monkeypatch, home, tmp_path):
    monkeypatch.delenv("HOMEBASE_PIPELINE_ROOT", raising=False)
    assert pipeline_tools.pipeline_root() == home / ".homebase" / "pipeline"
    monkeypatch.setenv("HOMEBASE_PIPELINE_ROOT", str(tmp_path / "elsewhere"))
    assert pipeline_tools.pipeline_root() == tmp_path / "elsewhere" != ideastore.ideas_root()
    assert pipeline_tools.ENV_ROOT == "HOMEBASE_PIPELINE_ROOT" and not (tmp_path / "elsewhere").exists(), "asking where it is makes no folder"


def test_each_tool_runs_its_command_in_the_pipelines_own_folder(fake, proot, ideas_root):
    b, end = box(), tail(proot)
    b.call("pipeline_add", {"card": CARD})
    assert fake.argv() == ["pipe", "add", "--spec=-", *end] and json.loads(fake.calls()[-1]["stdin"]) == CARD
    b.call("pipeline_add", {"card": card(name="orb_pre", session="pre"), "inbox": True})
    assert fake.argv() == ["pipe", "add", "--spec=-", "--inbox", *end]
    b.call("pipeline_add", {"card": card(name="orb_mid", session="mid"), "inbox": False})
    assert fake.argv() == ["pipe", "add", "--spec=-", *end]
    b.call("pipeline_status", {})
    assert fake.argv() == ["pipe", "list", *end] and fake.calls()[-1]["stdin"] == ""
    b.call("pipeline_status", {"name": NAME})
    assert fake.argv() == ["pipe", "show", NAME, *end]
    for action in ("pause", "resume", "start"):                              # (the fake's start writes a pid down: no runner)
        b.call("pipeline_control", {"action": action})
        assert fake.argv() == ["pipe", action, *end]
    seed(proot, "orb_one", "awaiting_owner")
    seed(proot, "orb_two", "awaiting_owner")
    b.call("pipeline_decide", {"name": "orb_one", "decision": "approve"})
    assert fake.argv() == ["pipe", "approve", "orb_one", *end]
    b.call("pipeline_decide", {"name": "orb_two", "decision": "refuse", "why": "  too few\n trades for me "})
    assert fake.argv() == ["pipe", "refuse", "orb_two", "--why=too few trades for me", *end]
    b.call("pipeline_book", {})
    assert fake.argv() == ["pipe", "book", *end]
    for call in fake.calls():                                       # the toolkit's own folder, the engine's Python, the PIPELINE's root
        assert call["cwd"] == os.path.realpath(fake.script.parent) and call["python"] == sys.executable
        assert call["argv"][-2:] == end and call["argv"][0] == "pipe" and f"--root={ideas_root}" not in call["argv"]
    b.call("blueprint_status", {})                                  # the same way to the toolkit: a blueprint command still gets the idea folder
    assert fake.argv() == ["status", f"--root={ideas_root}", "--json"]
    assert pipeline_tools.PipelineMixin._pipe.__qualname__ and "_bp" not in vars(pipeline_tools.PipelineMixin), "no second way to the toolkit"
    assert "subprocess" not in Path(pipeline_tools.__file__).read_text(encoding="utf-8")


def test_an_option_cannot_be_smuggled_in_through_a_name_or_a_reason(fake, proot):
    b = box()
    for bad in ("--root=/", "-x", "Bad Name", "", "../x", "a", "x" * 35, 7, None, ["fvg_open"]):
        for tool, more in (("pipeline_status", {}), ("pipeline_decide", {"decision": "approve"}),
                           ("pipeline_decide", {"decision": "refuse", "why": "no"})):
            if bad is None and tool == "pipeline_status":
                continue                                                    # (no name there = the whole queue)
            with pytest.raises(ToolError, match="name"):
                b.call(tool, {"name": bad, **more})
    assert fake.calls() == []
    seed(proot, "orb_one", "awaiting_owner")
    text = b.call("pipeline_decide", {"name": "orb_one", "decision": "refuse", "why": "--json --root=/ -x"})
    assert fake.argv() == ["pipe", "refuse", "orb_one", "--why=--json --root=/ -x", *tail(proot)]       # one argument, whatever it says
    assert text.splitlines() == ["Pipeline refuse · orb_one · Refused", "orb_one is refused: --json --root=/ -x"]


def test_inputs_that_do_not_read_are_refused_before_anything_starts(fake):
    b = box()
    bad_calls = [
        ("pipeline_add", {}, "card"), ("pipeline_add", {"card": "why: it works"}, "card: an object"),
        ("pipeline_add", {"card": [CARD]}, "card: an object"), ("pipeline_add", {"card": CARD, "inbox": "yes"}, "inbox: true or false"),
        ("pipeline_add", {"card": CARD, "inbox": 1}, "inbox: true or false"), ("pipeline_add", {"card": CARD, "start": True}, "start"),
        ("pipeline_status", {"name": NAME, "job_id": "j"}, "job_id"),
        ("pipeline_control", {}, "action"), ("pipeline_control", {"action": "stop"}, "action: start, pause or resume"),
        ("pipeline_control", {"action": "_loop"}, "action: start, pause or resume"), ("pipeline_control", {"action": ["start"]}, "action: start"),
        ("pipeline_control", {"action": "start", "stage": 5}, "stage"),
        ("pipeline_decide", {"name": NAME}, "decision"), ("pipeline_decide", {"name": NAME, "decision": "yes"}, "decision: approve or refuse"),
        ("pipeline_decide", {"name": NAME, "decision": True}, "decision: approve or refuse"),
        ("pipeline_decide", {"name": NAME, "decision": "refuse"}, "why: the owner's reason"),
        ("pipeline_decide", {"name": NAME, "decision": "refuse", "why": "   "}, "why: the owner's reason"),
        ("pipeline_decide", {"name": NAME, "decision": "refuse", "why": 7}, "why: the owner's reason"),
        ("pipeline_decide", {"name": NAME, "decision": "approve", "force": True}, "force"),
        ("pipeline_book", {"name": NAME}, "name")]
    for tool, args, msg in bad_calls:
        with pytest.raises(ToolError, match=msg):
            b.call(tool, args)
    assert fake.calls() == []


# ---------------------------------------------------------------- what comes back: the toolkit's own words

def test_a_card_goes_in_the_queue_and_the_same_idea_is_refused_under_any_name(fake, proot):
    b = box()
    assert b.call("pipeline_add", {"card": CARD}).splitlines() == [
        "Pipeline add · fvg_open · Waiting", "fvg_open is in the queue: place 1 of 1.", "Stage 1 will run 2 heat maps: fvg_open_a1, fvg_open_a5."]
    with pytest.raises(ToolError) as e:
        b.call("pipeline_add", {"card": card(name="fvg_again", why="The same card in other words, eight of them.")})
    assert str(e.value).splitlines() == [
        "Refused (pipeline add): 'fvg_again' is the same card as 'fvg_open', added 2026-10-08T04:44:21+00:00: the same market, session, sides and "
        "ways under another name are the same card, and a card is run once", "Nothing was run."]
    assert isinstance(e.value, blueprint_tools.Refused)
    with pytest.raises(ToolError, match=r"Refused \(pipeline add\): a pipeline card named 'fvg_open' is already on file .* give the new card another name"):
        b.call("pipeline_add", {"card": card(session="pm")})
    text = b.call("pipeline_add", {"card": card(name="orb_pre", session="pre"), "inbox": True})
    assert "orb_pre is in the queue: place 1 of 2 (inbox: it goes first)." in text.splitlines()
    assert list(json.loads((proot / "fake.json").read_text())["ideas"]) == ["fvg_open", "orb_pre"], "a refused card left nothing"
    res = rpc(protocol.Server(b), "tools/call", {"name": "pipeline_add", "arguments": {"card": CARD}})["result"]
    assert res["isError"] is True and res["content"][0]["text"].startswith("Refused (pipeline add): a pipeline card named 'fvg_open'")


def test_a_card_that_is_not_whole_is_refused_with_the_lines_that_fail(fake, proot):
    half = card(name="half_card", why="")
    half["ways"][0]["values"] = ["0.1"]
    with pytest.raises(ToolError) as e:
        box().call("pipeline_add", {"card": half})
    assert str(e.value).splitlines() == [
        "Refused (pipeline add): the card is not whole: P0.1 FAIL it does not say why it should make money (why, one sentence); "
        "P0.2 FAIL way a: min_gap has 1 values (need 3, each once)", "Nothing was run."]
    with pytest.raises(ToolError, match=r"Refused \(pipeline add\): unknown fields \['bars'\]: a pipeline card is \{name, why, loser"):
        box().call("pipeline_add", {"card": card(bars=["1"])})
    assert not proot.exists(), "nothing was saved: not even the pipeline's folder"


def test_no_tool_text_carries_the_toolkits_command_line_or_its_json(fake, proot):
    """The toolkit's `next` names its own command line (bp.py pipe ...), which no chat and no page has: it is left out."""
    b = box()
    said = [b.call("pipeline_add", {"card": CARD}), b.call("pipeline_status", {}), b.call("pipeline_status", {"name": NAME}),
            b.call("pipeline_control", {"action": "pause"}), b.call("pipeline_control", {"action": "resume"}), b.call("pipeline_control", {"action": "start"}),
            b.call("pipeline_book", {})]
    for text in said:
        assert "bp.py" not in text and "Next:" not in text and '{"' not in text and '"ok"' not in text, text
        assert text.startswith("Pipeline ")


def test_the_queue_and_one_idea_in_full(fake, proot):
    b = box()
    assert b.call("pipeline_status", {}).splitlines() == ["Pipeline list", "no idea is on file", "", "0 ideas", "runner: not working · queue: not paused"]
    assert not proot.exists(), "a look makes no folder"
    b.call("pipeline_add", {"card": CARD})
    seed(proot, "orb_stop", "stopped", stopped_at=1, why="orb_stop_a5 P1.1 FAIL 44 % of boxes profitable (need over 60 %)")
    assert b.call("pipeline_status", {}).splitlines() == [
        "Pipeline list", "name  family  status  stage  tries  why", "fvg_open  fvg  queued  -  0",
        "orb_stop  orb  stopped  1  2  orb_stop_a5 P1.1 FAIL 44 % of boxes profitable (need over 60 %)", "",
        "2 ideas: 1 queued, 1 stopped", "runner: not working · queue: not paused"]
    assert b.call("pipeline_status", {"name": NAME}).splitlines() == [
        "Pipeline show · fvg_open · Waiting", "fvg_open: fvg on NQ nyam, sides both (source owner)", "why: Late buyers chase the first gap after the open.",
        "loser: Traders who fade the first move.", "status: queued · stage - · tries 0",
        "way a: fvg, min_gap 0.1 / 0.25 / 0.5 (mode touch)", "indicator 1: trend with -- A gap with the trend has more room."]
    out = b.call("pipeline_status", {"name": "orb_stop"}).splitlines()
    assert out[0] == "Pipeline show · orb_stop · Stopped" and "status: stopped · stage 1 · tries 2" in out
    assert "stopped: orb_stop_a5 P1.1 FAIL 44 % of boxes profitable (need over 60 %)" in out
    assert "stage 1 FAIL raw heat map: orb_stop_a5: 44 % of boxes profitable" in out and "way a: orb, or_min 5 / 15 / 30" in out
    assert out[-4:] == ["stage 0, its lines:", "  P0.1 PASS the reason in one sentence, and who loses", "stage 1, its lines:",
                        "  orb_stop_a5 P1.1 FAIL 44 % of boxes profitable (need over 60 %)"], "every stage's lines, with their numbers"
    with pytest.raises(blueprint_tools.Refused, match=rf"Refused \(pipeline show\): no pipeline idea 'nope' under {re.escape(str(proot))}"):
        b.call("pipeline_status", {"name": "nope"})


def test_the_runner_is_started_paused_and_carries_on(fake, proot):
    b = box()
    assert b.call("pipeline_control", {"action": "pause"}).splitlines() == ["Pipeline pause", "the queue is paused: the runner stops after the stage in hand"]
    assert b.call("pipeline_status", {}).splitlines()[-1] == "runner: not working · queue: paused"
    assert b.call("pipeline_control", {"action": "resume"}).splitlines() == ["Pipeline resume", "the queue is not paused: no runner is working"]
    assert b.call("pipeline_control", {"action": "start"}).splitlines() == ["Pipeline start", "the runner is started (pid 4242): it works through the queue by itself"]
    assert b.call("pipeline_control", {"action": "start"}).splitlines() == ["Pipeline start", "a runner is already working (pid 4242): nothing was started"]
    assert b.call("pipeline_status", {}).splitlines()[-1] == "runner: working (pid 4242) · queue: not paused"
    assert b.call("pipeline_control", {"action": "resume"}).splitlines()[1] == "the queue is not paused: the runner carries on"
    assert [c["argv"][1] for c in fake.calls()] == ["pause", "list", "resume", "start", "start", "list", "resume"], "one command a call, nothing else"


def test_the_owners_yes_or_no_is_only_for_an_idea_that_passed_every_stage(fake, proot):
    b = box()
    b.call("pipeline_add", {"card": CARD})
    for decision, more, word in (("approve", {}, "approved"), ("refuse", {"why": "not for me"}, "refused")):
        with pytest.raises(blueprint_tools.Refused) as e:
            b.call("pipeline_decide", {"name": NAME, "decision": decision, **more})
        assert str(e.value).splitlines() == [
            f"Refused (pipeline {decision}): fvg_open is queued: only an idea that passed every stage and waits for the owner (awaiting_owner) is {word}",
            "Nothing was run."]
    with pytest.raises(ToolError, match=r"Refused \(pipeline approve\): no pipeline idea 'nope'"):
        b.call("pipeline_decide", {"name": "nope", "decision": "approve"})
    assert b.call("pipeline_book", {}).splitlines() == ["Pipeline book", "the book is empty"]
    seed(proot, "orb_one", "awaiting_owner")
    seed(proot, "orb_two", "awaiting_owner")
    assert b.call("pipeline_status", {"name": "orb_one"}).splitlines()[0] == "Pipeline show · orb_one · Passed"
    n = len(fake.calls())
    with pytest.raises(ToolError, match="why: the owner's reason for refusing it"):
        b.call("pipeline_decide", {"name": "orb_two", "decision": "refuse"})
    assert len(fake.calls()) == n, "a refusal without his reason starts nothing"
    assert b.call("pipeline_decide", {"name": "orb_one", "decision": "approve", "why": "he said yes"}).splitlines() == [
        "Pipeline approve · orb_one · In the book", f"orb_one is in the book ({proot / 'book' / 'orb_one.json'})"]
    assert fake.argv() == ["pipe", "approve", "orb_one", *tail(proot)], "a reason is not read for a yes"
    assert b.call("pipeline_decide", {"name": "orb_two", "decision": "refuse", "why": "too few trades"}).splitlines() == [
        "Pipeline refuse · orb_two · Refused", "orb_two is refused: too few trades"]
    assert b.call("pipeline_book", {}).splitlines() == ["Pipeline book", "name  label  family  market  session  bar", "orb_one  stands alone  orb  NQ  pre  5"]
    with pytest.raises(ToolError, match="orb_one is book: only an idea that passed every stage"):
        b.call("pipeline_decide", {"name": "orb_one", "decision": "approve"})       # a yes is said once


def test_what_the_labs_pages_read(fake, proot):
    """Not tools: the Queue / Book / Guide answer and one idea's page, as the routes hand them on."""
    b = box()
    got = b.pipeline_state()
    assert list(got) == ["runner", "counts", "ideas", "book", "stages"] and [c["argv"][:2] for c in fake.calls()] == [["pipe", "list"], ["pipe", "book"]]
    assert got == {"runner": {"running": False, "paused": False}, "counts": dict.fromkeys(LABELS, 0), "ideas": [], "book": [], "stages": pipeline_tools.STAGES}
    b.call("pipeline_add", {"card": CARD})
    for i, status in enumerate(STATUSES[2:]):
        seed(proot, f"orb_{i}", status, stopped_at=1 if status in ("stopped", "code_problem") else None)
    b.call("pipeline_control", {"action": "pause"})
    b.call("pipeline_control", {"action": "start"})
    got = b.pipeline_state()
    assert got["runner"] == {"running": True, "paused": True}
    assert got["counts"] == {"Waiting": 1, "Running": 0, "Stopped": 1, "Problem": 1, "Passed": 1, "In the book": 1, "Refused": 1}
    assert [(r["name"], r["status"], r["label"]) for r in got["ideas"]] == [
        ("fvg_open", "queued", "Waiting"), ("orb_0", "stopped", "Stopped"), ("orb_1", "code_problem", "Problem"), ("orb_2", "awaiting_owner", "Passed"),
        ("orb_3", "book", "In the book"), ("orb_4", "refused", "Refused")]
    assert set(got["ideas"][1]) == {"name", "status", "stage", "stopped_at", "why", "tries", "picked", "added_utc", "updated_utc", "source", "family", "label"}
    one = b.pipeline_idea("orb_0")
    assert list(one) == ["card", "state", "stages"] and "subs" not in one["card"] and one["card"]["ways"][0]["family"] == "orb"
    assert one["state"]["label"] == "Stopped" and one["state"]["stopped_at"] == 1
    assert one["stages"] == [
        {"n": 0, "name": "Idea card", "passed": True, "result": "pass", "text": "the card is whole",
         "lines": [{"line": "P0.1", "passed": True, "text": "P0.1 PASS the reason in one sentence, and who loses"}]},
        {"n": 1, "name": "Raw heat map", "passed": False, "result": "fail", "text": "orb_0_a5: 44 % of boxes profitable\nthe other heat map is no better",
         "lines": [{"line": "P1.1", "passed": False, "text": "orb_0_a5 P1.1 FAIL 44 % of boxes profitable (need over 60 %)"}]}]
    assert [s["n"] for s in b.pipeline_idea("orb_2")["stages"]] == [0, 1, 7] and b.pipeline_idea("orb_2")["stages"][-1]["passed"] is None
    assert "subs" in json.loads((proot / "fake.json").read_text())["ideas"]["fvg_open"]["card"] and "subs" not in b.pipeline_idea(NAME)["card"]
    with pytest.raises(blueprint_tools.Refused):
        b.pipeline_idea("nope")
    with pytest.raises(ToolError, match="name"):
        b.pipeline_idea("--root=/")


# ---------------------------------------------------------------- a toolkit that is not there, crashes or never answers

def test_a_missing_toolkit_is_the_blueprint_tools_plain_error(monkeypatch, tmp_path, fake):
    monkeypatch.setenv("HOMEBASE_BP_PYTHON", str(tmp_path / "nowhere" / "python"))
    for tool, args in (("pipeline_status", {}), ("pipeline_add", {"card": CARD}), ("pipeline_control", {"action": "start"}), ("pipeline_book", {})):
        with pytest.raises(ToolError, match="The blueprint toolkit is not installed yet: its Python") as e:
            box().call(tool, args)
        assert not isinstance(e.value, blueprint_tools.Refused) and "Traceback" not in str(e.value)
    monkeypatch.setenv("HOMEBASE_BP_PYTHON", sys.executable)
    monkeypatch.setenv("HOMEBASE_BP", str(tmp_path / "nowhere" / "bp.py"))
    res = rpc(protocol.Server(box()), "tools/call", {"name": "pipeline_status", "arguments": {}})["result"]
    assert res["isError"] is True and "not installed yet" in res["content"][0]["text"] and str(tmp_path / "nowhere" / "bp.py") in res["content"][0]["text"]
    with pytest.raises(ToolError, match="not installed yet"):
        box().pipeline_state()
    assert fake.calls() == []


def test_a_crash_or_a_toolkit_that_never_answers_names_the_command_in_its_two_words(fake, proot):
    b = box()
    with pytest.raises(ToolError, match=r"crashed \(exit 1\) on `pipe show`") as e:
        b.call("pipeline_status", {"name": "crash_me"})
    assert "ZeroDivisionError: division by zero" in str(e.value) and not isinstance(e.value, blueprint_tools.Refused)
    t0 = time.monotonic()
    with pytest.raises(ToolError) as e:
        b._bp(["pipe", "show", "sleepy"], timeout=0.4, root=proot)
    assert str(e.value) == "The blueprint toolkit did not answer `pipe show` within 0.4 s and was stopped." and time.monotonic() - t0 < 20
    with pytest.raises(ToolError, match=r"did not answer `status` within 0.4 s and was stopped. blueprint_status shows whether a job is still running."):
        b._bp(["status", "sleepy"], timeout=0.4)                             # a blueprint command: as it was
    assert blueprint_tools._command(["pipe", "list"]) == "pipe list" and blueprint_tools._command(["lock", "pipe"]) == "lock"


# ---------------------------------------------------------------- nothing here leaves the temp folders

def test_no_test_can_reach_the_real_pipeline_folder(fake, proot, home):
    real = REAL_HOME / ".homebase"
    for used in (pipeline_tools.pipeline_root(), fake.script, Path.home()):
        assert real not in Path(used).resolve().parents and Path(used).resolve() != real
    assert pipeline_tools.pipeline_root() == proot
    b = box()
    b.call("pipeline_add", {"card": CARD})
    b.call("pipeline_status", {})
    b.pipeline_state()
    for call in fake.calls():                                                   # the toolkit is always told where
        assert f"--root={proot}" in call["argv"]
    assert sorted(p.name for p in proot.iterdir()) == ["fake.json"] and not (home / ".homebase").exists()


def test_the_server_runs_a_pipeline_tool_over_stdio(fake, proot):
    """python -m homebase.claude_mcp end to end: the child of a pipeline tool never gets the server's stdin either."""
    p = subprocess.Popen([sys.executable, "-m", "homebase.claude_mcp"], cwd=REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, env={**os.environ, "HOMEBASE_CHARTS_URL": "http://127.0.0.1:1"})
    answers: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: [answers.put(json.loads(x)) for x in p.stdout], daemon=True).start()

    def ask(rid, name, args):
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": rid, "method": "tools/call", "params": {"name": name, "arguments": args}}) + "\n")
        p.stdin.flush()
        return answers.get(timeout=20)["result"]

    try:
        got = ask(1, "pipeline_add", {"card": CARD})
        assert got["isError"] is False and got["content"][0]["text"].startswith("Pipeline add · fvg_open · Waiting\nfvg_open is in the queue: place 1 of 1.")
        got = ask(2, "pipeline_status", {})
        assert got["isError"] is False and "1 idea: 1 queued" in got["content"][0]["text"]
        got = ask(3, "pipeline_decide", {"name": NAME, "decision": "approve"})
        assert got["isError"] is True and got["content"][0]["text"].startswith("Refused (pipeline approve): fvg_open is queued")
    finally:
        p.stdin.close()
        try:
            p.wait(timeout=20)
        except subprocess.TimeoutExpired:
            p.kill()
    assert [c["stdin"] for c in fake.calls()] == [json.dumps(CARD), "", ""]


# ---------------------------------------------------------------- the REAL toolkit: the commands that need no engine run

@pytest.mark.skipif(not REAL_PYTHON.is_file() or not (TOOLKIT / "bp.py").is_file(),
                    reason="needs the research toolkit and its Python (<repo>/.venv-research)")
def test_the_real_toolkit_answers_these_tools_as_the_fake_does(monkeypatch, proot, home, ideas_root, drafts_dir):
    """Each tool end to end against research/edge-library/bp.py, in the temp pipeline root: a card in, the same card
    refused under another name, a card that is not whole, the queue, one idea, pause / resume, a yes that is refused,
    the empty book -- and what the Lab's pages read. NEVER `start`: no runner is spawned, nothing is run."""
    monkeypatch.setenv(blueprint_tools.ENV_PYTHON, str(REAL_PYTHON))
    monkeypatch.setenv(blueprint_tools.ENV_BP, str(TOOLKIT / "bp.py"))
    b = box()
    assert b.call("pipeline_status", {}).splitlines() == ["Pipeline list", "no idea is on file", "", "0 ideas", "runner: not working · queue: not paused"]
    assert b.call("pipeline_book", {}).splitlines() == ["Pipeline book", "the book is empty"] and not proot.exists()
    assert b.call("pipeline_add", {"card": CARD}).splitlines() == [
        "Pipeline add · fvg_open · Waiting", "fvg_open is in the queue: place 1 of 1.", "Stage 1 will run 2 heat maps: fvg_open_a1, fvg_open_a5."]
    with pytest.raises(blueprint_tools.Refused, match=r"Refused \(pipeline add\): 'fvg_again' is the same card as 'fvg_open', added .*: the same market, "
                                                      r"session, sides and ways under another name are the same card, and a card is run once\nNothing was run\."):
        b.call("pipeline_add", {"card": card(name="fvg_again", why="The same card in other words, eight of them.")})
    half = card(name="half_card", why="", indicators=[{"block": "nope", "side": "with", "why": "x"}])
    half["ways"][0]["values"] = ["0.1"]
    with pytest.raises(blueprint_tools.Refused) as e:
        b.call("pipeline_add", {"card": half})
    assert str(e.value).splitlines() == [
        "Refused (pipeline add): the card is not whole: P0.1 FAIL it does not say why it should make money (why, one sentence); "
        "P0.2 FAIL way a: min_gap has 1 values (need 3, each once); P0.3 FAIL indicator 1: block 'nope' is no filter block (`bp.py blocks` lists them)",
        "Nothing was run."]
    with pytest.raises(blueprint_tools.Refused, match=r"unknown fields \['bars'\]: a pipeline card is \{name, why, loser"):
        b.call("pipeline_add", {"card": card(name="with_bars", bars=["1"])})
    text = b.call("pipeline_add", {"card": card(name="fvg_pm", session="pm", indicators=[]), "inbox": True})
    assert "fvg_pm is in the queue: place 1 of 2 (inbox: it goes first)." in text.splitlines()
    out = b.call("pipeline_status", {}).splitlines()
    assert out[0] == "Pipeline list" and out[1].split() == ["name", "family", "status", "stage", "tries", "why"]
    assert [ln.split() for ln in out[2:4]] == [["fvg_pm", "fvg", "queued", "-", "0"], ["fvg_open", "fvg", "queued", "-", "0"]]
    assert out[-2:] == ["2 ideas: 2 queued", "runner: not working · queue: not paused"]
    assert b.call("pipeline_status", {"name": NAME}).splitlines() == [
        "Pipeline show · fvg_open · Waiting", "fvg_open: fvg on NQ nyam, sides both (source owner)", "why: Late buyers chase the first gap after the open.",
        "loser: Traders who fade the first move.", "status: queued · stage - · tries 0",
        "way a: fvg, min_gap 0.1 / 0.25 / 0.5 (mode touch)", "indicator 1: trend with -- A gap with the trend has more room."]
    with pytest.raises(blueprint_tools.Refused, match=r"Refused \(pipeline show\): no pipeline idea 'nope' under "):
        b.call("pipeline_status", {"name": "nope"})
    assert b.call("pipeline_control", {"action": "pause"}).splitlines() == ["Pipeline pause", "the queue is paused: the runner stops after the stage in hand"]
    assert b.call("pipeline_status", {}).splitlines()[-1] == "runner: not working · queue: paused"
    assert b.pipeline_state()["runner"] == {"running": False, "paused": True}
    assert b.call("pipeline_control", {"action": "resume"}).splitlines() == ["Pipeline resume", "the queue is not paused: no runner is working"]
    for decision, more, word in (("approve", {}, "approved"), ("refuse", {"why": "not for me"}, "refused")):
        with pytest.raises(blueprint_tools.Refused) as e:
            b.call("pipeline_decide", {"name": NAME, "decision": decision, **more})
        assert str(e.value).splitlines() == [
            f"Refused (pipeline {decision}): fvg_open is queued: only an idea that passed every stage and waits for the owner (awaiting_owner) is {word}",
            "Nothing was run."]
    got = b.pipeline_state()
    assert list(got) == ["runner", "counts", "ideas", "book", "stages"] and got["runner"] == {"running": False, "paused": False} and got["book"] == []
    assert got["counts"] == {**dict.fromkeys(LABELS, 0), "Waiting": 2} and [(r["name"], r["label"]) for r in got["ideas"]] == [("fvg_pm", "Waiting"), ("fvg_open", "Waiting")]
    assert set(got["ideas"][0]) == {"name", "status", "stage", "stopped_at", "why", "tries", "picked", "added_utc", "updated_utc", "source", "family", "label"}
    one = b.pipeline_idea(NAME)
    assert one["card"] == CARD and one["stages"] == [] and one["state"] == {**got["ideas"][1]}
    assert sorted(p.name for p in proot.iterdir()) == ["order.jsonl", "p", "seen.jsonl"], "no runner was started: no lock, no log, no pid"
    assert sorted(p.name for p in (proot / "p").iterdir()) == ["fvg_open", "fvg_pm"] and list(ideas_root.iterdir()) == [] and list(drafts_dir.iterdir()) == []
    assert paths.repo_root() == REPO
