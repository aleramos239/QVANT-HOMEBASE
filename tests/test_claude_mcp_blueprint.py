"""The connector's blueprint tools (homebase.claude_mcp.blueprint_tools): the nine tool definitions, the exact
command line each one runs, and what comes back -- against a FAKE toolkit: a small script written here that
answers each command with the JSON of the toolkit plan's section 8 (a refusal with exit code 2, a crash, a job
that is still running), and saves a card and a build through homebase.ideastore as the real toolkit does.
Temp folders only: the suite's `ideas_root` and `drafts_dir`, and a temp HOME that must stay empty."""
from __future__ import annotations

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

from homebase import draftstore, ideastore, paths
from homebase.claude_mcp import blueprint_tools, protocol, tools
from homebase.claude_mcp.client import Client, ToolError

REPO = Path(__file__).resolve().parent.parent
NAME = "nq_orb_pre"
CARD = {"why": "the 08:30 burst carries into the open", "loser": "late faders",
        "home": {"market": "GC", "session": "pre", "bar": "15"}, "neighbors": ["GC pre 5", "NQ pre 15"],
        "not_here": "the Asian session", "main_setting": "or_min", "sides": "both",
        "sides_why": "a burst runs either way"}
SETTINGS = {"family": "orb", "params": {"or_min": ["5", "15", "30"]}, "fixed": {"mode": "break"}, "filters": [],
            "exits": "standard", "limits": {"max_tr": 1}}
ACCOUNT = "lucid-pro-50k@2026-09-27b"
# The live orders of an eval in the toolkit's format (research/edge-library/blueprint/evalcard.py, FILLS): a trade,
# then an order that did not trade. FIELDS = its KEYS, in its order; a trade's first eight ([1:9]) are required.
FIELDS = ["status", "entry_time", "exit_time", "side", "size", "entry_price", "exit_price", "net", "exit_reason",
          "entry_slip_ticks", "trigger_price", "replay", "fixed", "note"]
FILLS = [{"entry_time": "2026-10-01T08:45:02-04:00", "exit_time": "2026-10-01T09:12:40-04:00", "side": "long",
          "size": 1, "entry_price": 2655.3, "exit_price": 2657.3, "net": 18.4, "exit_reason": "tp",
          "entry_slip_ticks": 1, "replay": {"entry_time": "2026-10-01T08:45:00-04:00", "exit_reason": "tp"}},
         {"status": "missed", "entry_time": "2026-10-02T08:45:00-04:00", "side": "short"}]

FAKE = r'''
"""A fake blueprint toolkit: canned answers in the JSON of the toolkit plan, section 8."""
import json, os, sys, time
sys.path.insert(0, "@REPO@")
from homebase import ideastore

argv = sys.argv[1:]
stdin = sys.stdin.read()
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "calls.jsonl"), "a") as f:
    f.write(json.dumps({"argv": argv, "stdin": stdin, "cwd": os.getcwd(), "python": sys.executable}) + "\n")
cmd = argv[0]
pos = [a for a in argv[1:] if not a.startswith("--")]
opt = dict((a[2:].split("=", 1) if "=" in a else (a[2:], True)) for a in argv[1:] if a.startswith("--"))
name, root = (pos[0] if pos else None), opt.get("root")


def lines(phase, n, fail=(), na=()):
    out = []
    for i in range(1, n + 1):
        k = "%d.%d" % (phase, i)
        passed = None if k in na else k not in fail
        mark = "n/a " if passed is None else "PASS" if passed else "FAIL"
        out.append({"line": k, "passed": passed, "number": 41.0, "need": 70.0, "text": "%s %s words about %s" % (k, mark, k)})
    return out


def result(command, **more):
    r = {"ok": True, "command": command, "name": name, "status": "idea", "phase": None, "round": None, "lines": [],
         "text": "", "next": "", "job": None, "saved": [], "error": None}
    r.update(more)
    return r


def out(r, code=0):
    print(json.dumps(r, indent=1))
    sys.exit(code)


if name == "refuse_me":
    why = "no card on file for refuse_me: write it first"
    out(result(cmd, ok=False, status=None, error=why, text="REFUSED: " + why, next="Write the card: blueprint_card."), 2)
if name == "soft_refusal":
    out(result(cmd, ok=False, status=None, error="round 6: the blueprint allows 5"), 0)
if name == "crash_me":
    sys.stderr.write('Traceback (most recent call last):\n  File "bp.py", line 1\nZeroDivisionError: division by zero\n')
    sys.exit(1)
if name == "garbage_out":
    print("hello, this is not the agreed JSON")
    sys.exit(0)
if name == "usage_error":
    sys.stderr.write("usage: bp.py [-h] {card,build} ...\nbp.py: error: unrecognized arguments: --looked\n")
    sys.exit(2)
if name == "sleepy":
    time.sleep(60)
if name == "noisy_ok":
    print("a warning some library printed on stdout")
    out(result(cmd, phase=3, text="locked all the same"))

if cmd == "blocks":
    out(result(cmd, status=None, text="THE BLOCKS: what an idea can be built from without writing code\n"
               "ENTRY TRIGGERS (settings.family; ONE an idea): 1 runs on the build days\n  orb  the opening range breaks\n"
               "WHAT VERSION 1 REFUSES\n  the evening session: it comes later",
               next="Write the idea card from these blocks: bp.py card <name> --spec=-",
               blocks={"refused": [{"what": "the evening session", "why": "it comes later"}]}, counts={"families": 1, "refused": 1}))
if cmd == "card":
    spec = json.loads(stdin)
    ideastore.create(name, root, exist_ok=True)
    ideastore.write_card(name, "Why: %s\nWho loses: %s" % (spec["card"]["why"], spec["card"]["loser"]), root)
    ideastore.write_spec(name, dict(spec, version=1), root)
    ls = lines(0, 6)
    d = ideastore.idea_dir(name, root)
    out(result(cmd, phase=0, lines=ls, text="\n".join(x["text"] for x in ls), next="Run the code check: blueprint_code_check.",
               saved=[str(d / "card.md"), str(d / "spec.json")]))
if cmd == "code-check":
    ls = lines(1, 6, fail=() if "looked" in opt else ("1.5",))
    out(result(cmd, phase=1, lines=ls, text="Trades to look at on the chart: 1, 2, 3, 4, 5, 17, 40, 77, 102, 140.",
               next="Look at those 10 trades, then call it again with looked."))
if cmd == "build":
    if name == "slow_idea":
        out(result(cmd, phase=2, round=1, job={"id": "job-slow_idea-1", "state": "running", "progress": "table 3 of 12"}))
    good = name == "good_idea"
    ls = lines(2, 9, fail=() if good else ("2.2",), na=("2.7",))
    r = result(cmd, status="lead" if good else "idea", phase=2, round=1, lines=ls,
               text="\n".join(x["text"] for x in ls[:3]), next="Lock it: blueprint_lock." if good else "Round 2 needs a reason.",
               job={"id": "job-x", "state": "done", "progress": "done"})
    if ideastore.exists(name, root):
        n = len(ideastore.rounds(name, root)) + 1
        ideastore.write_reason(name, n, opt["reason"], root)
        ideastore.write_build(name, n, dict(r, round=n), root)
    out(r)
if cmd == "job":
    jid, who = pos[0], "slow_idea"
    if jid == "job-stuck":
        out(result("build", name=who, phase=2, round=1, job={"id": jid, "state": "running", "progress": "table 9 of 12"}))
    if jid == "job-broken":
        out(result("build", name=who, phase=2, round=1, error="the engine stopped: no tape for 2024-03-06",
                   job={"id": jid, "state": "error", "progress": "table 9 of 12"}))
    if jid.startswith("job-test"):
        out(result("test", name="nq_orb_pre", status="proven_on_history", phase=4, lines=lines(4, 7),
                   text="PROVEN ON HISTORY", job={"id": jid, "state": "done", "progress": "done"}))
    out(result("build", name=who, status="lead", phase=2, round=1, lines=lines(2, 9, na=("2.7",)), text="all nine lines read",
               next="Lock it: blueprint_lock.", job={"id": jid, "state": "done", "progress": "done"}))
if cmd == "lock":
    out(result(cmd, status="lead", phase=3, text="Locked. Hash 9f2c41aa, default v2_s3_t2, test days 2025-07-01 .. 2026-09-30.",
               next="The one out-of-sample test, when the owner says so: blueprint_test."))
if cmd == "test":
    if "confirm" not in opt:
        out(result(cmd, ok=False, status=None, error="the one read needs --confirm"), 2)
    if name == "slow_test":
        out(result(cmd, status="lead", phase=4, job={"id": "job-test-7", "state": "queued", "progress": ""}))
    out(result(cmd, status="proven_on_history", phase=4, lines=lines(4, 7), text="PROVEN ON HISTORY",
               next="Before the eval is bought: blueprint_sim."))
if cmd == "sim":
    out(result(cmd, status="proven_on_history", phase=5, lines=lines(5, 4),
               text="account %s, %s attempts, fee budget $%s" % (opt["account"], opt["attempts"], opt["fee-budget"])))
if cmd == "eval-card":
    n = len(json.loads(stdin)["fills"]) if "fills" in opt else 0
    ls = [dict(x, text=x["text"].replace("words about", "not judged yet:")) if x["passed"] is None else x
          for x in lines(6, 8, na=("6.4", "6.5", "6.6", "6.8"))]
    out(result(cmd, status="proven_on_history", phase=6, lines=ls,
               text="%d live fills read for %s" % (n, opt.get("account", "the account of the sim saved last"))))
if cmd == "status":
    out(result(cmd, status=None, text=("%s: idea, phase 2, round 1" % name) if name else "2 ideas\nnq_orb_pre: idea\ngood_idea: lead"))
out(result(cmd, ok=False, status=None, error="unknown command " + cmd), 2)
'''


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """No test here may fall back to the real ~/.homebase: HOME is a temp folder (the toolkit child inherits
    it), and nothing may appear in it."""
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    yield h
    assert not (h / ".homebase").exists()


class Fake:
    def __init__(self, folder: Path):
        self.script = folder / "bp.py"
        self.script.write_text(FAKE.replace("@REPO@", str(REPO)), encoding="utf-8")
        self.log = folder / "calls.jsonl"

    def calls(self) -> list[dict]:
        return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []

    def argv(self) -> list[str]:
        return self.calls()[-1]["argv"]


@pytest.fixture
def fake(tmp_path, monkeypatch):
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


def tail(ideas_root) -> list[str]:
    """What every command line ends with: the idea folder, then --json."""
    return [f"--root={ideas_root}", "--json"]


# ---------------------------------------------------------------- the nine tools

REQUIRED = {"blueprint_blocks": [], "blueprint_card": ["name", "card", "settings"], "blueprint_code_check": ["name"],
            "blueprint_build": ["name"], "blueprint_lock": ["name"], "blueprint_test": ["name", "confirm"],
            "blueprint_sim": ["name", "account", "attempts", "fee_budget"], "blueprint_eval_card": ["name"],
            "blueprint_status": []}
INPUTS = {"blueprint_blocks": [], "blueprint_card": ["name", "card", "settings"],
          "blueprint_code_check": ["name", "store", "trades_file", "run_id", "looked"],
          "blueprint_build": ["name", "reason", "wait_s", "job_id"], "blueprint_lock": ["name"],
          "blueprint_test": ["name", "confirm", "wait_s", "job_id"],
          "blueprint_sim": ["name", "account", "attempts", "fee_budget"],
          "blueprint_eval_card": ["name", "fills", "account"], "blueprint_status": ["name", "job_id"]}
PHASE = {"blueprint_blocks": "Blueprint, before the card",
         "blueprint_card": "Blueprint phase 0, the idea card", "blueprint_code_check": "Blueprint phase 1, the code check",
         "blueprint_build": "Blueprint phase 2, the build", "blueprint_lock": "Blueprint phase 3, the freeze",
         "blueprint_test": "Blueprint phase 4, the out-of-sample test",
         "blueprint_sim": "Blueprint phase 5, before the eval is bought", "blueprint_eval_card": "Blueprint phase 6, the eval",
         "blueprint_status": "Blueprint, any phase"}


def texts(o) -> list[str]:
    """Every description a chat reads in a tool definition, the nested ones too."""
    if isinstance(o, dict):
        return [v for k, v in o.items() if k == "description" and isinstance(v, str)] + [t for v in o.values() for t in texts(v)]
    return [t for v in o for t in texts(v)] if isinstance(o, list) else []


def test_the_nine_tools_their_inputs_and_what_each_requires():
    specs = {s["name"]: s for s in blueprint_tools.SPECS}
    assert list(specs) == list(REQUIRED) and len(specs) == 9
    listed = {s["name"]: s for s in tools.Toolbox().specs()}
    for name, spec in specs.items():
        schema = spec["inputSchema"]
        assert listed[name] is spec and callable(getattr(tools.Toolbox, f"t_{name}"))
        assert schema["required"] == REQUIRED[name], name
        assert list(schema["properties"]) == INPUTS[name], name            # the inputs of the plan, section 4 (+ --account)
        assert schema["type"] == "object" and schema["additionalProperties"] is False
        assert spec["description"].startswith(PHASE[name]), name               # each says which phase it is
        json.dumps(spec)
    card = specs["blueprint_card"]["inputSchema"]["properties"]["card"]
    assert card["required"] == ["why", "loser", "home", "neighbors", "not_here", "main_setting", "sides", "sides_why"]
    assert card["properties"]["home"]["required"] == ["market", "session", "bar"]
    settings = specs["blueprint_card"]["inputSchema"]["properties"]["settings"]
    assert settings["properties"]["exits"]["enum"] == ["standard"] and settings["properties"]["filters"]["maxItems"] == 2
    for long_one in ("blueprint_build", "blueprint_test"):
        wait = specs[long_one]["inputSchema"]["properties"]["wait_s"]
        assert (wait["minimum"], wait["maximum"]) == (0, tools.MAX_WAIT_S) and f"default {tools.DEFAULT_WAIT_S}" in wait["description"]
    assert (blueprint_tools.DEFAULT_WAIT_S, blueprint_tools.MAX_WAIT_S) == (tools.DEFAULT_WAIT_S, tools.MAX_WAIT_S)


def test_the_test_tool_says_the_test_days_are_read_once_and_asks_for_an_explicit_yes():
    spec = next(s for s in blueprint_tools.SPECS if s["name"] == "blueprint_test")
    assert "READ ONCE" in spec["description"] and "2025-07-01" in spec["description"]
    confirm = spec["inputSchema"]["properties"]["confirm"]
    assert confirm["type"] == "boolean" and "once" in confirm["description"].lower()
    assert "confirm" in spec["inputSchema"]["required"]


def test_the_blocks_tool_takes_nothing_and_says_to_call_it_before_writing_a_card():
    spec = blueprint_tools.SPECS[0]
    assert spec["name"] == "blueprint_blocks" and spec["inputSchema"]["properties"] == {}
    said = spec["description"]
    assert "Call this before writing an idea card (blueprint_card)." in said and said.endswith("Runs nothing.")
    for what in ("everything an idea can be built from without writing code", "entry triggers", "filters",
                 "standard exit table", "sessions", "bar sizes", "markets with their cost floors",
                 "Monte Carlo settings", "size steps", "what version 1 of the toolkit refuses"):
        assert what in said, what


def test_no_tool_text_offers_what_version_1_of_the_toolkit_refuses():
    """The toolkit's version 1 (research/edge-library/blueprint/blocklist.py REFUSED, records.py) refuses a home of
    "all", the evening session, and limits.trail_atr / limits.exit_bars. The card's description says so in one
    sentence; no other text of these tools names one of them."""
    spec = next(s for s in blueprint_tools.SPECS if s["name"] == "blueprint_card")
    card, settings = (spec["inputSchema"]["properties"][k] for k in ("card", "settings"))
    home = card["properties"]["home"]
    assert home["description"].startswith("0.3 Its home: ONE market, session and bar size")
    assert [home["properties"][k]["description"] for k in ("market", "session", "bar")] == [
        "NQ, ES or GC.", "asia, london, pre, nyam, mid or pm.", "The bar size in minutes (5, 15, ...)."]
    assert settings["properties"]["limits"]["description"] == "Optional: max_tr (entries per session), dir."
    refuses = ('Version 1 also refuses a home of "all" (it judges ONE home table: the others are neighbors), the '
               "evening session, and limits.trail_atr / limits.exit_bars (exits of their own): blueprint_blocks lists "
               "everything it refuses.")
    assert spec["description"].endswith(refuses)
    said = "\n".join(texts(blueprint_tools.SPECS))
    assert said.count(refuses) == 1
    for gone in (r'"all"', r"\bor all\b", r"\beve\b", r"\bevening\b", r"exit_bars", r"trail_atr"):
        assert not re.search(gone, said.replace(refuses, "")), gone


def test_the_eval_card_states_the_fills_format_as_the_toolkit_reads_it():
    """research/edge-library/blueprint/evalcard.py, FILLS: a trade says its first eight fields and may say the
    others; an order that did not trade is {status: missed | rejected}; a field that is not listed is refused.
    The account is the toolkit's own option (--account), and optional as it is there."""
    spec = next(s for s in blueprint_tools.SPECS if s["name"] == "blueprint_eval_card")
    props = spec["inputSchema"]["properties"]
    assert props["fills"]["type"] == "array" and "oldest first" in props["fills"]["description"]
    trade, lost = props["fills"]["items"]["anyOf"]
    assert list(trade["properties"]) == FIELDS and trade["required"] == FIELDS[1:9]
    assert trade["properties"]["status"]["enum"] == ["filled"]
    assert list(lost["properties"]) == ["status", "entry_time", "side", "replay", "fixed", "note"]
    assert lost["required"] == ["status"] and lost["properties"]["status"]["enum"] == ["missed", "rejected"]
    assert trade["additionalProperties"] is False and lost["additionalProperties"] is False
    replay = trade["properties"]["replay"]
    assert list(replay["properties"]) == ["entry_time", "exit_reason", "no_trade"] and lost["properties"]["replay"] is replay
    assert trade["properties"]["size"] == {"type": "integer", "minimum": 1,
                                           "description": "Micros traded: a whole number from 1 (stage A is 1)."}
    for f in FILLS:                                                     # the fills these tests send are in the format
        shape = lost if "status" in f else trade
        assert set(shape["required"]) <= set(f) <= set(shape["properties"]), f
    said = spec["description"]
    assert ("A TRADE (an order that filled and is flat again) must say entry_time, exit_time, side, size, entry_price, "
            "exit_price, net and exit_reason; entry_slip_ticks (or trigger_price), replay, fixed and note are "
            "optional.") in said
    assert ('AN ORDER THAT DID NOT TRADE where the test did is {"status": "missed" | "rejected"}, with entry_time, '
            "side and replay when they are known. A field that is not listed is refused.") in said
    assert props["account"]["type"] == "string" and "Left out: the card's own" in props["account"]["description"]


def test_every_chat_is_told_to_use_them():
    srv = protocol.Server(box())
    init = rpc(srv, "initialize", {"protocolVersion": "2025-06-18"})["result"]
    assert ("For a strategy idea use the blueprint_* tools (card, code check, build, lock, test, sim, eval card): "
            "they save everything in the app.") in init["instructions"]
    assert init["serverInfo"]["version"] == protocol.SERVER_VERSION == "1.4.0"
    listed = [t["name"] for t in rpc(srv, "tools/list")["result"]["tools"]]
    assert listed[listed.index("blueprint_blocks"):listed.index("blueprint_status") + 1] == list(REQUIRED)


def test_every_chat_is_told_their_order_and_that_the_lab_groups_fill_themselves():
    text = rpc(protocol.Server(box()), "initialize", {"protocolVersion": "2025-06-18"})["result"]["instructions"]
    assert ("Their order: blueprint_blocks (what an idea can be built from), blueprint_card, blueprint_code_check, "
            "blueprint_build, blueprint_lock, blueprint_test (once), blueprint_sim, blueprint_eval_card, with "
            "blueprint_status at any time; they file each idea under its Lab group themselves, so set_group is not "
            "needed for it.") in text
    at = [text.index(name) for name in REQUIRED]                        # the order the tools are listed in
    assert at == sorted(at) and len(set(at)) == 9


# ---------------------------------------------------------------- where the toolkit is

def test_the_toolkit_is_where_the_plan_says_and_both_paths_can_be_moved(monkeypatch, home, tmp_path):
    monkeypatch.delenv(blueprint_tools.ENV_BP, raising=False)
    monkeypatch.delenv(blueprint_tools.ENV_PYTHON, raising=False)
    assert blueprint_tools.toolkit() == (str(home / "ONYX TRADING" / ".venv" / "bin" / "python"),
                                         str(paths.repo_root() / "research" / "edge-library" / "bp.py"))
    monkeypatch.setenv("HOMEBASE_BP", str(tmp_path / "x" / "bp.py"))
    monkeypatch.setenv("HOMEBASE_BP_PYTHON", "/opt/py/bin/python3")
    assert blueprint_tools.toolkit() == ("/opt/py/bin/python3", str(tmp_path / "x" / "bp.py"))
    assert (blueprint_tools.ENV_BP, blueprint_tools.ENV_PYTHON) == ("HOMEBASE_BP", "HOMEBASE_BP_PYTHON")


def test_a_missing_toolkit_is_a_plain_error_that_says_it_is_not_installed_yet(monkeypatch, tmp_path, fake):
    monkeypatch.setenv("HOMEBASE_BP", str(tmp_path / "nowhere" / "bp.py"))
    with pytest.raises(ToolError, match="not installed yet") as e:
        box().call("blueprint_status", {})
    assert str(tmp_path / "nowhere" / "bp.py") in str(e.value) and "Traceback" not in str(e.value)
    monkeypatch.setenv("HOMEBASE_BP", str(fake.script))
    monkeypatch.setenv("HOMEBASE_BP_PYTHON", str(tmp_path / "nowhere" / "python"))
    with pytest.raises(ToolError, match="not installed yet"):
        box().call("blueprint_lock", {"name": NAME})
    res = rpc(protocol.Server(box()), "tools/call", {"name": "blueprint_status", "arguments": {}})["result"]
    assert res["isError"] is True and "not installed yet" in res["content"][0]["text"]
    assert fake.calls() == []


# ---------------------------------------------------------------- the command line each tool runs

def test_each_tool_runs_its_command_as_the_contract_has_it(fake, ideas_root):
    b, end = box(), tail(ideas_root)
    b.call("blueprint_blocks", {})
    assert fake.argv() == ["blocks", *end] and fake.calls()[-1]["stdin"] == ""
    b.call("blueprint_card", {"name": NAME, "card": CARD, "settings": SETTINGS})
    assert fake.argv() == ["card", NAME, "--spec=-", *end]
    assert json.loads(fake.calls()[-1]["stdin"]) == {"name": NAME, "card": CARD, "run": SETTINGS}
    b.call("blueprint_code_check", {"name": NAME})
    assert fake.argv() == ["code-check", NAME, *end]
    b.call("blueprint_code_check", {"name": NAME, "store": "orb-GC-tf15"})
    assert fake.argv() == ["code-check", NAME, "--store=orb-GC-tf15", *end]
    b.call("blueprint_code_check", {"name": NAME, "trades_file": "/tmp/x/my trades.json", "looked": True})
    assert fake.argv() == ["code-check", NAME, "--trades=/tmp/x/my trades.json", "--looked", *end]
    b.call("blueprint_code_check", {"name": NAME, "run_id": "20261006-010203-draft_nq_orb_pre-abcd", "looked": False})
    assert fake.argv() == ["code-check", NAME, "--run-id=20261006-010203-draft_nq_orb_pre-abcd", *end]
    b.call("blueprint_build", {"name": NAME, "reason": "the plain idea, as carded"})
    assert fake.argv() == ["build", NAME, "--reason=the plain idea, as carded", "--wait=120", *end]
    b.call("blueprint_build", {"name": "slow_idea", "job_id": "job-slow_idea-1", "wait_s": 30})
    assert fake.argv() == ["job", "job-slow_idea-1", "--wait=30", *end]
    b.call("blueprint_lock", {"name": NAME})
    assert fake.argv() == ["lock", NAME, *end]
    b.call("blueprint_test", {"name": NAME, "confirm": True})
    assert fake.argv() == ["test", NAME, "--confirm", "--wait=120", *end]
    b.call("blueprint_test", {"name": NAME, "confirm": True, "job_id": "job-test-7", "wait_s": 0})
    assert fake.argv() == ["job", "job-test-7", "--wait=0", *end]
    b.call("blueprint_sim", {"name": NAME, "account": ACCOUNT, "attempts": 3, "fee_budget": 345})
    assert fake.argv() == ["sim", NAME, f"--account={ACCOUNT}", "--attempts=3", "--fee-budget=345", *end]
    b.call("blueprint_eval_card", {"name": NAME})
    assert fake.argv() == ["eval-card", NAME, *end] and fake.calls()[-1]["stdin"] == ""
    b.call("blueprint_eval_card", {"name": NAME, "fills": FILLS})
    assert fake.argv() == ["eval-card", NAME, "--fills=-", *end]
    assert json.loads(fake.calls()[-1]["stdin"]) == {"fills": FILLS}
    b.call("blueprint_eval_card", {"name": NAME, "account": ACCOUNT})                 # the account, as sim passes it
    assert fake.argv() == ["eval-card", NAME, f"--account={ACCOUNT}", *end] and fake.calls()[-1]["stdin"] == ""
    b.call("blueprint_eval_card", {"name": NAME, "fills": FILLS, "account": ACCOUNT})
    assert fake.argv() == ["eval-card", NAME, f"--account={ACCOUNT}", "--fills=-", *end]
    assert json.loads(fake.calls()[-1]["stdin"]) == {"fills": FILLS}
    b.call("blueprint_status", {})
    assert fake.argv() == ["status", *end]
    b.call("blueprint_status", {"name": NAME})
    assert fake.argv() == ["status", NAME, *end]
    b.call("blueprint_status", {"job_id": "job-stuck"})
    assert fake.argv() == ["job", "job-stuck", "--wait=0", *end]
    for call in fake.calls():                                       # the toolkit's own folder, the engine's Python
        assert call["cwd"] == os.path.realpath(fake.script.parent) and call["python"] == sys.executable
        assert call["argv"][-2:] == end


def test_the_wait_is_the_testers_own_default_and_cap(fake, ideas_root):
    b = box()
    for asked, sent in ((None, 120), (0, 0), (45, 45), (99_999, 3600), (-5, 0)):
        b.call("blueprint_build", {"name": NAME, "reason": "r", **({} if asked is None else {"wait_s": asked})})
        assert f"--wait={sent}" in fake.argv()


def test_an_option_cannot_be_smuggled_in_through_a_name_an_id_or_a_reason(fake, ideas_root):
    b = box()
    for bad in ("--stored", "-x", "nq930", "Bad Name", "", "../x"):
        for tool, more in (("blueprint_lock", {}), ("blueprint_build", {"reason": "r"}), ("blueprint_status", {}),
                           ("blueprint_test", {"confirm": True})):
            with pytest.raises(ToolError, match="name"):
                b.call(tool, {"name": bad, **more})
    for bad in ("--root=/", "-j", "", "a b", 7):
        with pytest.raises(ToolError, match="job_id"):
            b.call("blueprint_build", {"name": NAME, "job_id": bad})
        with pytest.raises(ToolError, match="job_id"):
            b.call("blueprint_status", {"job_id": bad})
    assert fake.calls() == []
    b.call("blueprint_build", {"name": NAME, "reason": "-5 ticks: a tighter stop --json"})
    assert fake.argv() == ["build", NAME, "--reason=-5 ticks: a tighter stop --json", "--wait=120", *tail(ideas_root)]
    b.call("blueprint_code_check", {"name": NAME, "store": "--looked"})
    assert fake.argv() == ["code-check", NAME, "--store=--looked", *tail(ideas_root)]
    b.call("blueprint_eval_card", {"name": NAME, "account": "--fills=-"})
    assert fake.argv() == ["eval-card", NAME, "--account=--fills=-", *tail(ideas_root)]


def test_inputs_that_do_not_read_are_refused_before_anything_starts(fake):
    b = box()
    bad_calls = [
        ("blueprint_card", {"name": NAME, "card": "why: it works", "settings": SETTINGS}, "card"),
        ("blueprint_card", {"name": NAME, "card": CARD, "settings": ["orb"]}, "settings"),
        ("blueprint_code_check", {"name": NAME, "store": "a", "run_id": "b"}, "one of"),
        ("blueprint_code_check", {"name": NAME, "store": 7}, "store"),
        ("blueprint_code_check", {"name": NAME, "looked": "yes"}, "looked"),
        ("blueprint_build", {"name": NAME}, "reason"),
        ("blueprint_build", {"name": NAME, "reason": "   "}, "reason"),
        ("blueprint_build", {"name": NAME, "reason": "r", "wait_s": "soon"}, "wait_s"),
        ("blueprint_sim", {"name": NAME, "account": "", "attempts": 3, "fee_budget": 345}, "account"),
        ("blueprint_sim", {"name": NAME, "account": ACCOUNT, "attempts": 0, "fee_budget": 345}, "attempts"),
        ("blueprint_sim", {"name": NAME, "account": ACCOUNT, "attempts": 1.5, "fee_budget": 345}, "attempts"),
        ("blueprint_sim", {"name": NAME, "account": ACCOUNT, "attempts": True, "fee_budget": 345}, "attempts"),
        ("blueprint_sim", {"name": NAME, "account": ACCOUNT, "attempts": 3, "fee_budget": -1}, "fee_budget"),
        ("blueprint_sim", {"name": NAME, "account": ACCOUNT, "attempts": 3, "fee_budget": "a lot"}, "fee_budget"),
        ("blueprint_eval_card", {"name": NAME, "fills": {"net": 1}}, "fills"),
        ("blueprint_eval_card", {"name": NAME, "fills": ["a fill"]}, "fills"),
        ("blueprint_eval_card", {"name": NAME, "account": ""}, "account"),
        ("blueprint_eval_card", {"name": NAME, "fills": FILLS, "account": 7}, "account"),
        ("blueprint_blocks", {"name": NAME}, "name"),
        ("blueprint_status", {"name": NAME, "job_id": "job-1"}, "either"),
        ("blueprint_lock", {}, "name"), ("blueprint_lock", {"name": NAME, "force": True}, "force")]
    for tool, args, msg in bad_calls:
        with pytest.raises(ToolError, match=msg):
            b.call(tool, args)
    assert fake.calls() == []


def test_the_one_read_needs_an_explicit_yes(fake, ideas_root):
    b = box()
    with pytest.raises(ToolError, match="confirm"):
        b.call("blueprint_test", {"name": NAME})                              # left out
    for no in (False, None, "yes", 1, "true"):
        with pytest.raises(ToolError, match="read ONCE") as e:
            b.call("blueprint_test", {"name": NAME, "confirm": no})
        assert "confirm" in str(e.value)
    with pytest.raises(ToolError, match="read ONCE"):                          # not even to wait on a job
        b.call("blueprint_test", {"name": NAME, "confirm": False, "job_id": "job-test-7"})
    assert fake.calls() == []                                                  # nothing was started
    text = b.call("blueprint_test", {"name": NAME, "confirm": True})
    assert "--confirm" in fake.argv() and "PROVEN ON HISTORY" in text and "Lines: 7 passed · 0 FAILED" in text
    assert len(fake.calls()) == 1


# ---------------------------------------------------------------- what comes back

def test_the_answer_is_the_toolkits_text_plus_every_pass_fail_line(fake, ideas_root, drafts_dir):
    assert box().call("blueprint_blocks", {}).splitlines() == [                 # the list as the toolkit wrote it
        "Blueprint blocks", "THE BLOCKS: what an idea can be built from without writing code",
        "ENTRY TRIGGERS (settings.family; ONE an idea): 1 runs on the build days", "  orb  the opening range breaks",
        "WHAT VERSION 1 REFUSES", "  the evening session: it comes later",
        "Next: Write the idea card from these blocks: bp.py card <name> --spec=-"]
    text = box().call("blueprint_build", {"name": NAME, "reason": "the plain idea, as carded"})
    out = text.splitlines()
    assert out[0] == "Blueprint build · nq_orb_pre · IDEA · phase 2 · round 1"
    for i in range(1, 10):                                                      # each line once: the text had three
        mark = "FAIL" if i == 2 else "n/a " if i == 7 else "PASS"
        assert out.count(f"2.{i} {mark} words about 2.{i}") == 1, i
    assert "Lines: 7 passed · 1 FAILED (2.2) · 1 not judged or does not apply (2.7)" in out
    assert out[-1] == "Next: Round 2 needs a reason."
    assert list(drafts_dir.iterdir()) == [] and list(ideas_root.iterdir()) == []   # not an idea on file: no Lab copy
    text = box().call("blueprint_code_check", {"name": NAME})
    assert "Trades to look at on the chart: 1, 2, 3, 4, 5, 17, 40, 77, 102, 140." in text
    assert "1.5 FAIL words about 1.5" in text and "Lines: 5 passed · 1 FAILED (1.5)" in text
    assert "Lines: 6 passed · 0 FAILED" in box().call("blueprint_code_check", {"name": NAME, "looked": True})
    text = box().call("blueprint_lock", {"name": NAME})
    assert text.splitlines()[0] == "Blueprint lock · nq_orb_pre · LEAD · phase 3" and "Hash 9f2c41aa" in text
    assert "Lines:" not in text and "Next: The one out-of-sample test, when the owner says so: blueprint_test." in text
    text = box().call("blueprint_sim", {"name": NAME, "account": ACCOUNT, "attempts": 3, "fee_budget": 345.5})
    assert f"account {ACCOUNT}, 3 attempts, fee budget $345.5" in text and "PROVEN ON HISTORY · phase 5" in text
    assert "2 live fills read" in box().call("blueprint_eval_card", {"name": NAME, "fills": FILLS})
    assert f"0 live fills read for {ACCOUNT}" in box().call("blueprint_eval_card", {"name": NAME, "account": ACCOUNT})
    text = box().call("blueprint_eval_card", {"name": NAME})
    assert "0 live fills read" in text and "6.4 n/a  not judged yet: 6.4" in text.splitlines()   # the line's own words
    assert "Lines: 4 passed · 0 FAILED · 4 not judged or do not apply (6.4, 6.5, 6.6, 6.8)" in text.splitlines()
    assert box().call("blueprint_status", {}).splitlines() == ["Blueprint status", "2 ideas", "nq_orb_pre: idea",
                                                               "good_idea: lead"]
    assert "locked all the same" in box().call("blueprint_lock", {"name": "noisy_ok"})   # a stray line before the JSON


def test_a_refusal_is_said_plainly_and_is_the_tools_error(fake):
    b = box()
    with pytest.raises(ToolError) as e:
        b.call("blueprint_lock", {"name": "refuse_me"})
    assert str(e.value).splitlines() == ["Refused (blueprint lock): no card on file for refuse_me: write it first",
                                         "Nothing was run.", "Next: Write the card: blueprint_card."]
    res = rpc(protocol.Server(b), "tools/call", {"name": "blueprint_build", "arguments": {"name": "refuse_me",
                                                                                         "reason": "r"}})["result"]
    assert res["isError"] is True and res["content"][0]["text"].startswith("Refused (blueprint build): no card on file")
    with pytest.raises(ToolError, match=r"Refused \(blueprint lock\): bp.py: error: unrecognized arguments: --looked"):
        b.call("blueprint_lock", {"name": "usage_error"})                     # exit 2 without the JSON (a usage error)
    with pytest.raises(ToolError, match=r"Refused \(blueprint lock\): round 6: the blueprint allows 5"):
        b.call("blueprint_lock", {"name": "soft_refusal"})                    # ok false wins over the exit code


def test_a_crash_or_an_answer_that_is_not_the_contracts_is_an_error_that_says_so(fake):
    b = box()
    with pytest.raises(ToolError, match=r"crashed \(exit 1\)") as e:
        b.call("blueprint_lock", {"name": "crash_me"})
    assert "ZeroDivisionError: division by zero" in str(e.value)
    with pytest.raises(ToolError, match="not the agreed JSON") as e:
        b.call("blueprint_lock", {"name": "garbage_out"})
    assert "hello, this is not the agreed JSON" in str(e.value)


# ---------------------------------------------------------------- long commands: the job id

def test_a_long_build_returns_its_job_and_the_same_tool_keeps_waiting(fake, ideas_root):
    b = box()
    text = b.call("blueprint_build", {"name": "slow_idea", "reason": "the plain idea", "wait_s": 5})
    assert text == ("Blueprint build · slow_idea · IDEA · phase 2 · round 1: job job-slow_idea-1 is still going "
                    "(running · table 3 of 12). Call blueprint_build(name='slow_idea', job_id='job-slow_idea-1') "
                    "to keep waiting.")
    text = b.call("blueprint_build", {"name": "slow_idea", "job_id": "job-slow_idea-1"})        # no reason: it is on file
    assert fake.argv() == ["job", "job-slow_idea-1", "--wait=120", *tail(ideas_root)]
    assert text.splitlines()[0] == "Blueprint build · slow_idea · LEAD · phase 2 · round 1"
    assert "Lines: 8 passed · 0 FAILED · 1 not judged or does not apply (2.7)" in text
    assert "Next: Lock it: blueprint_lock." in text
    text = b.call("blueprint_build", {"name": "slow_idea", "job_id": "job-stuck", "wait_s": 0})
    assert "job job-stuck is still going (running · table 9 of 12)" in text and "job_id='job-stuck'" in text
    with pytest.raises(ToolError, match="job job-broken failed: the engine stopped: no tape for 2024-03-06"):
        b.call("blueprint_build", {"name": "slow_idea", "job_id": "job-broken"})
    assert "job job-stuck is still going" in b.call("blueprint_status", {"job_id": "job-stuck"})


def test_a_long_test_says_how_to_keep_waiting_without_reading_again(fake):
    text = box().call("blueprint_test", {"name": "slow_test", "confirm": True, "wait_s": 0})
    assert "job job-test-7 is still going (queued)" in text
    assert "Call blueprint_test(name='slow_test', confirm=true, job_id='job-test-7') to keep waiting" in text
    assert "nothing is read again" in text
    assert "PROVEN ON HISTORY" in box().call("blueprint_test", {"name": NAME, "confirm": True, "job_id": "job-test-7"})


def test_a_toolkit_that_never_answers_is_stopped(fake):
    b = box()
    b._bp_grace_s = 0.4
    t0 = time.monotonic()
    with pytest.raises(ToolError, match="did not answer"):
        b.call("blueprint_build", {"name": "sleepy", "reason": "r", "wait_s": 0})
    assert time.monotonic() - t0 < 20


# ---------------------------------------------------------------- everything is saved in the app

def test_a_card_makes_the_record_draft_and_each_new_status_files_it_in_its_group(fake, ideas_root, drafts_dir):
    b = box()
    text = b.call("blueprint_card", {"name": "good_idea", "card": CARD, "settings": SETTINGS})
    assert text.splitlines()[0] == "Blueprint card · good_idea · IDEA · phase 0"
    assert 'Lab: draft_good_idea is now in the group "Ideas".' in text.splitlines()
    assert f"Saved: {ideas_root / 'good_idea' / 'card.md'}, {ideas_root / 'good_idea' / 'spec.json'}" in text
    draft = (drafts_dir / "good_idea.py").read_text(encoding="utf-8")
    assert draft.startswith(ideastore.BLOCK_START) and "#   Why: the 08:30 burst carries into the open" in draft
    assert draftstore.static_meta(draft)["root"] == "GC"
    assert draftstore.read_groups() == {"groups": ["Ideas"], "members": {"draft_good_idea": "Ideas"}}
    text = b.call("blueprint_build", {"name": "good_idea", "reason": "the plain idea, as carded"})
    assert 'Lab: draft_good_idea is now in the group "Leads".' in text.splitlines()
    assert ideastore.read_idea("good_idea")["status"] == "lead" and ideastore.read_idea("good_idea")["group"] == "Leads"
    assert draftstore.read_groups()["members"] == {"draft_good_idea": "Leads"}
    assert (drafts_dir / "good_idea.py").read_text().splitlines()[1] == "# good_idea · LEAD · phase 2 · round 1"
    assert (ideas_root / "good_idea" / "rounds" / "1" / "reason.txt").read_text() == "the plain idea, as carded\n"
    assert "Lab:" not in b.call("blueprint_status", {"name": "good_idea"})        # nothing new: the Lab is left alone
    assert "Lab:" not in b.call("blueprint_lock", {"name": "good_idea"})


def test_a_groups_file_that_does_not_read_is_reported_and_the_phase_still_answers(fake, drafts_dir):
    (drafts_dir / "groups.json").write_text("{not json")
    b = box()
    text = b.call("blueprint_card", {"name": "good_idea", "card": CARD, "settings": SETTINGS})
    assert "Lines: 6 passed · 0 FAILED" in text                                # the card went through
    [note] = [ln for ln in text.splitlines() if ln.startswith("Lab:")]
    assert "group was not updated" in note and "groups.json" in note
    assert (drafts_dir / "groups.json").read_text() == "{not json" and (drafts_dir / "good_idea.py").is_file()
    res = rpc(protocol.Server(b), "tools/call", {"name": "blueprint_build", "arguments": {
        "name": "good_idea", "reason": "the plain idea"}})["result"]
    assert res["isError"] is False and "groups.json" in res["content"][0]["text"]
    (drafts_dir / "groups.json").unlink()
    assert 'Lab: draft_good_idea is now in the group "Leads".' in b.call("blueprint_status", {"name": "good_idea"})


def test_a_status_the_saved_results_do_not_bear_out_is_said(fake, ideas_root):
    """The first line is the toolkit's word; the status in the app is read off the saved results alone. When
    the two differ the answer says so -- here the fake claims a pass it never saved."""
    b = box()
    b.call("blueprint_card", {"name": NAME, "card": CARD, "settings": SETTINGS})
    text = b.call("blueprint_test", {"name": NAME, "confirm": True})
    assert text.splitlines()[0] == "Blueprint test · nq_orb_pre · PROVEN ON HISTORY · phase 4"
    assert "Lab: the saved results read IDEA, not PROVEN ON HISTORY." in text.splitlines()
    assert ideastore.read_idea(NAME)["status"] == "idea" and draftstore.read_groups()["members"] == {
        "draft_nq_orb_pre": "Ideas"}


# ---------------------------------------------------------------- nothing here leaves the temp folders

def test_no_test_can_reach_the_real_homebase_folder(fake, ideas_root, drafts_dir, home):
    real = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".homebase"                 # the real one, whatever HOME says
    for used in (ideastore.ideas_root(), draftstore.drafts_dir(), fake.script, Path.home()):
        assert real not in Path(used).resolve().parents and Path(used).resolve() != real
    assert (ideastore.ideas_root(), draftstore.drafts_dir()) == (ideas_root, drafts_dir)
    b = box()
    b.call("blueprint_card", {"name": "good_idea", "card": CARD, "settings": SETTINGS})
    b.call("blueprint_status", {})
    for call in fake.calls():                                                   # the toolkit is always told where
        assert f"--root={ideas_root}" in call["argv"]
    assert not (home / ".homebase").exists()


def test_the_server_runs_the_toolkit_over_stdio_and_keeps_its_own_stdin(fake, ideas_root):
    """python -m homebase.claude_mcp end to end, one request at a time. The toolkit child reads its stdin to the
    end: handed the server's (the JSON-RPC stream, still open) it would wait on it forever, and eat what follows."""
    p = subprocess.Popen([sys.executable, "-m", "homebase.claude_mcp"], cwd=REPO, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                         env={**os.environ, "HOMEBASE_CHARTS_URL": "http://127.0.0.1:1"})
    answers: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: [answers.put(json.loads(x)) for x in p.stdout], daemon=True).start()

    def ask(rid, method, params=None):
        msg = {"jsonrpc": "2.0", "id": rid, "method": method, **({} if params is None else {"params": params})}
        p.stdin.write(json.dumps(msg) + "\n")
        p.stdin.flush()
        return answers.get(timeout=20)

    try:
        assert ask(1, "initialize", {"protocolVersion": "2025-06-18"})["result"]["serverInfo"]["name"] == "homebase"
        got = ask(2, "tools/call", {"name": "blueprint_status", "arguments": {}})
        assert got["id"] == 2 and got["result"]["isError"] is False and "2 ideas" in got["result"]["content"][0]["text"]
        got = ask(3, "tools/call", {"name": "blueprint_lock", "arguments": {"name": "refuse_me"}})
        assert got["id"] == 3 and got["result"]["isError"] is True
        assert got["result"]["content"][0]["text"].startswith("Refused (blueprint lock)")
        assert ask(4, "ping") == {"jsonrpc": "2.0", "id": 4, "result": {}}
        got = ask(5, "tools/call", {"name": "blueprint_blocks", "arguments": {}})
        assert got["id"] == 5 and got["result"]["isError"] is False
        assert got["result"]["content"][0]["text"].startswith("Blueprint blocks\nTHE BLOCKS: what an idea can be built")
    finally:
        p.stdin.close()
        try:
            p.wait(timeout=20)
        except subprocess.TimeoutExpired:
            p.kill()
    assert [c["stdin"] for c in fake.calls()] == ["", "", ""]
