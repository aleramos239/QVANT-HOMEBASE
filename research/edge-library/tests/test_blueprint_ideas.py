"""LOCK of the idea's record (blueprint/records.py; `bp.py card`, `bp.py build <name> --reason=...`, `bp.py status`) -- toolkit
plan, steps 5 and 6: the idea card (phase 0), the build with its counted rounds (phase 2), every result saved in the app.

(a) THE CARD: a whole card passes lines 0.1-0.7 and is saved through the app's idea store (card.md, spec.json, the record
    draft in the Lab, filed under Ideas). Every missing line is refused with its number; so are exits that are not the
    standard table, more than 2 filters, a field the card does not have. A refused card writes nothing.
(b) FROM A CARD TO THE TABLES: the home table = the card's market, session and bar size; its neighbors (line 2.5) = the places
    the card names, each a table of its own; the place it should NOT work is run and shown, and no line reads it; a
    one-sided card is judged on that side (2.6).
(c) THE BUILD WITH ROUNDS: round n = the builds on file + 1; the reason is on disk BEFORE anything runs (a run that fails
    leaves it there); the round's settings and its result are saved, every line 2.1-2.9 in it; the bar of 2.3 rises round by
    round (95, 97.5, 98.3, 98.75, 99 %); a round that changes the base settings gets its own stores, a filter does not, and
    no store is written twice. Refused before anything runs: no card, no reason, round 6, a control pool with fewer than 10
    seeds, any day from 2025-07-01 on, a frozen idea.
(d) THE STATUS: idea -> lead when every line passes, -> shelved after a failed round 5 (read off the saved results by the
    app's idea store); the Lab draft's block and group follow.
(e) IN THE APP: the default variant (the middle of the variants profitable on build) is run again for its prices, held
    against its store trade for trade, and written as a finished tester run through homebase/backtest/importrun.py.
(f) THE COMMANDS as the connector writes them (`card <name> --spec=-` with the card on stdin, `build <name> --reason=TEXT
    --wait=S`, `status [<name>]`, `job <id>`; `--root=DIR --json` last) -- and THE CONNECTOR ITSELF, the app's own
    blueprint_card / blueprint_build / blueprint_status against this toolkit (skipped when the app's Python is not there).

TINY RUNS ONLY: 3 named build days, 2 exit cells, NQ on 15- and 5-minute bars, 1 worker. A run on named days is a SMOKE RUN
and is never saved; the tests need small runs that are SAVED, so they set BP_TEST_RUN (records.TEST_RUN), the test-only
switch that hands a build its days, cells, store folder and ledger and lets the result count. It is refused for the app's
own idea folder. No P&L is asserted: counts, identities, the shape of what is saved. Lines are forced to pass where a test
needs a lead (a table of 3 days cannot pass 200 trades).
Everything goes to a temp folder: the ideas (--root), the Lab drafts (HOMEBASE_DRAFTS_DIR), the stores, the ledger, the
tester's runs. Nothing is written under runs_bp/, to ledger.csv, to ~/.homebase or to the app's tester (the last test looks).

  pytest tests/test_blueprint_ideas.py -q     (about half a minute)     python tests/test_blueprint_ideas.py     + the connector's answers
"""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
import judge as J  # noqa: E402
from blueprint import api as A  # noqa: E402
from blueprint import cli as C  # noqa: E402
from blueprint import jobs as JOBS  # noqa: E402
from blueprint import lines as L  # noqa: E402
from blueprint import records as REC  # noqa: E402
from blueprint import rules as R  # noqa: E402
from blueprint import runner as RUN  # noqa: E402

import l2sim as S  # noqa: E402
import library as LB  # noqa: E402
import run_menus as RM  # noqa: E402

NAME = "bpi_orb"
CARD = {"why": "The first minutes of the New York morning set a range, and a break of it traps the traders who leaned on it.",
        "loser": "traders who faded the opening range",
        "home": {"market": "NQ", "session": "nyam", "bar": "15"},
        "neighbors": ["midday", "5-minute bars"],             # the next session on the same bars; the next bar size
        "not_here": "the Asian session",
        "main_setting": "or_min", "sides": "both", "sides_why": "a range can break either way", "loses_when": "a week without a clear direction"}
SETTINGS = {"family": "orb", "params": {"or_min": ["5", "15", "30"]}, "fixed": {}, "filters": [], "exits": "standard", "limits": {}}
DAYS = ["2022-03-15", "2023-03-22", "2025-06-30"]            # two plain days and the last build day
CELLS = ["atr3-r1", "pts20-r0"]                              # 2 of the 32 exit cells
SAT = dt.datetime(2026, 10, 3, 11, 0, tzinfo=S.ET)           # a Saturday: no desk hours, no window
CONTRACT = ("ok", "command", "name", "status", "phase", "round", "lines", "text", "next", "job", "saved", "error")     # plan section 8
BUILD_LINES = [f"2.{i}" for i in range(1, 10)]
BARS = [0.95, 0.975, 0.983, 0.9875, 0.99]                    # line 2.3, rounds 1 .. 5
HOME = Path.home() / ".homebase"
APP_RUNS = S.REPO / "homebase" / ".state" / "tester" / "runs"
APP_PYTHON = S.REPO / ".venv" / "bin" / "python"
RESULTS: dict = {}
_T: dict = {"keep": tempfile.TemporaryDirectory(prefix="bp_ideas_")}
_T["dir"] = Path(_T["keep"].name).resolve()
ENV = {"HOMEBASE_IDEAS_ROOT": str(_T["dir"] / "ideas_env"),             # never the real ~/.homebase: every test names its own root ...
       "HOMEBASE_DRAFTS_DIR": str(_T["dir"] / "drafts")}                # ... and the Lab drafts of all of them go here
_KEPT: dict = {}


def setup_function(_=None):
    """Every test of this module runs with ITS idea folder and ITS Lab drafts in the environment, and without the test-run
    switch (the other test modules put their own folders there when they are imported: whichever came last would win)."""
    _KEPT.update({k: os.environ.get(k) for k in (*ENV, REC.TEST_RUN)})
    os.environ.update(ENV)
    os.environ.pop(REC.TEST_RUN, None)


def teardown_function(_=None):
    for k, v in _KEPT.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def _listing(p: Path):
    return sorted(x.name for x in p.iterdir()) if p.exists() else None


PYC = [S.REPO / "homebase" / "backtest" / "__pycache__" / "importrun.cpython-314.pyc", S.REPO / "homebase" / "__pycache__" / "ideastore.cpython-314.pyc"]
BEFORE = {"ideas": _listing(HOME / "ideas"), "drafts": _listing(HOME / "strategies"), "pyc": [p.exists() for p in PYC]}


def tmp() -> Path:
    return _T["dir"]


OUT, LEDGER, TESTER, DRAFTS = tmp() / "runs", tmp() / "ledger.csv", tmp() / "tester", tmp() / "drafts"
TINY = {"days": DAYS, "cells": CELLS, "out": str(OUT), "ledger": str(LEDGER), "workers": 1, "draws": 200}
IS = A.ideastore()


def idea(name: str = NAME, card=None, run=None, **top) -> dict:
    """The idea's spec as the connector sends it ({name, card, run}), with what a test changes."""
    return {"name": name, "card": {**CARD, **(card or {})}, "run": {**SETTINGS, **(run or {})}, **top}


@contextlib.contextmanager
def tiny(**more):
    """BP_TEST_RUN is set while the block runs: a build takes its days, cells, store folder and ledger from it and COUNTS.
    The runner's clock stands on a Saturday and the workers asked for are the workers used."""
    keep, clock, auto = os.environ.get(REC.TEST_RUN), RUN.clock, RM.auto_workers
    os.environ[REC.TEST_RUN] = json.dumps({**TINY, **more})
    RUN.clock, RM.auto_workers = (lambda: SAT), (lambda n=None: n)
    try:
        yield
    finally:
        RUN.clock, RM.auto_workers = clock, auto
        os.environ.pop(REC.TEST_RUN, None) if keep is None else os.environ.__setitem__(REC.TEST_RUN, keep)


@contextlib.contextmanager
def no_engine():
    """Nothing may be read: every way into a tape raises while the block runs."""
    names = ("run_many", "load_tape", "sessions", "load_daily")
    keep = {n: getattr(S, n) for n in names}

    def stop(*a, **k):
        raise AssertionError("the engine was asked for data")

    for n in names:
        setattr(S, n, stop)
    try:
        yield
    finally:
        for n, f in keep.items():
            setattr(S, n, f)


@contextlib.contextmanager
def passing():
    """Every line of the build that is read says PASS while the block runs (a table of 3 days cannot pass on its own)."""
    keep = REC.LINES
    REC.LINES = tuple((lambda t, f=f: (lambda r: r if r["passed"] is None else {**r, "passed": True})(f(t))) for f in keep)
    try:
        yield
    finally:
        REC.LINES = keep


def refused(fn, word: str = "") -> str:
    try:
        fn()
    except (J.Refuse, R.RuleError) as e:
        assert word in str(e), str(e)
        return str(e)
    raise AssertionError(f"not refused ({word})")


def tree(d: Path) -> list:
    return sorted(str(p.relative_to(d)) for p in d.rglob("*") if p.is_file())


def read(p: Path) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def by(r: dict) -> dict:
    return {x["line"]: x for x in r["lines"]}


def plain(r: dict) -> dict:
    """A result as JSON has it (numpy numbers as plain ones), the way it is saved and printed."""
    return json.loads(json.dumps(r, default=lambda o: o.tolist()))


def stores(out: Path = OUT) -> list:
    return sorted(p.parent.name for p in out.glob("*/run.json"))


def draft(name: str) -> list:
    return (DRAFTS / f"{name}.py").read_text(encoding="utf-8").splitlines()


def group(name: str):
    return read(DRAFTS / "groups.json")["members"].get(f"draft_{name}")


def _run(argv: list, stdin: str = "") -> tuple:
    """The command line in this process -> (exit code, what it printed)."""
    out, keep = io.StringIO(), sys.stdin
    sys.stdin = io.StringIO(stdin)
    try:
        with contextlib.redirect_stdout(out):
            rc = C.main(argv)
    finally:
        sys.stdin = keep
    return rc, out.getvalue()


def bp(argv: list, stdin=None, **env) -> tuple:
    """The front door as the connector starts it: bp.py in its own process, in its own folder -> (exit code, the ONE JSON
    object)."""
    feed = {"stdin": subprocess.DEVNULL} if stdin is None else {"input": stdin}
    q = subprocess.run([sys.executable, str(W / "bp.py"), *argv], capture_output=True, text=True, timeout=900, cwd=str(W), env={**os.environ, **env}, **feed)
    assert q.stdout.count("\n") == 1, (q.stdout[-600:], q.stderr[-1500:])
    return q.returncode, json.loads(q.stdout)


# ================================================================ the life of idea A (run once, stage by stage)

ROOT = tmp() / "ideas"
REASONS = {1: "the plain opening range break, as carded", 2: "momentum should keep the breaks that run and drop the ones that stall",
           3: "one entry a session: the second break of a morning is the tired one", 4: "the same rule read once more"}
_A: dict = {}


def life(upto: int) -> dict:
    """Idea A up to a stage, each stage run once: 0 = the card · 1 = round 1 (plain; its default variant goes to the tester)
    · 2 = round 2, a filter added · 3 = round 3, a base setting changed · 4 = round 4, every line forced to pass."""
    snap = lambda: {"tree": tree(ROOT / NAME), "idea": IS.read_idea(NAME, ROOT), "draft": draft(NAME), "group": group(NAME)}  # noqa: E731
    if 0 not in _A:
        _A[0] = REC.card(NAME, idea(), ROOT)
        _A["snap0"] = snap()
    if upto >= 1 and 1 not in _A:
        with tiny(tester=str(TESTER)):
            _A[1] = REC.build(NAME, REASONS[1], root=ROOT)
        _A["snap1"] = snap()
        _A["stamp"] = {k: (OUT / k / "cells.npz").stat().st_mtime_ns for k in stores()}
    if upto >= 2 and 2 not in _A:
        _A["card2"] = REC.card(NAME, idea(run={"filters": [{"block": "momentum", "side": "with"}]}), ROOT)
        with tiny():
            _A[2] = REC.build(NAME, REASONS[2], root=ROOT)
    if upto >= 3 and 3 not in _A:
        _A["card3"] = REC.card(NAME, idea(run={"limits": {"max_tr": 1}}), ROOT)
        with tiny():
            _A[3] = REC.build(NAME, REASONS[3], root=ROOT)
    if upto >= 4 and 4 not in _A:
        with tiny(), passing(), no_engine():
            _A[4] = REC.build(NAME, REASONS[4], root=ROOT)
    return _A


# ================================================================ (a) the card

def test_a_whole_card_passes_and_is_saved_in_the_app():
    r, snap = life(0)[0], life(0)["snap0"]
    d = ROOT / NAME
    assert list(r)[:len(CONTRACT)] == list(CONTRACT)
    assert [r[k] for k in ("ok", "command", "name", "status", "phase", "round", "job", "error")] == [True, "card", NAME, "idea", 0, None, None, None]
    assert [x["line"] for x in r["lines"]] == [f"0.{i}" for i in range(1, 8)] and all(x["passed"] is True for x in r["lines"])
    assert all(set(x) >= {"line", "passed", "number", "need", "text"} and x["text"].startswith(f"{x['line']} PASS ") for x in r["lines"])
    b = by(r)
    assert (b["0.1"]["number"], b["0.1"]["need"]) == (1, R.need("0.1")) and CARD["why"] in b["0.1"]["text"] and CARD["loser"] in b["0.1"]["text"]
    assert (b["0.2"]["number"], b["0.2"]["need"]) == (0, R.need("0.2")) and "orb" in b["0.2"]["text"] and "standard" in b["0.2"]["text"]
    assert "NQ" in b["0.3"]["text"] and "15-minute" in b["0.3"]["text"] and "New York morning" in b["0.3"]["text"]
    assert b["0.4"]["number"] == 2 and "NOT" in b["0.4"]["text"] and (b["0.5"]["number"], b["0.5"]["need"]) == (3, R.need("0.5"))
    assert "or_min" in b["0.5"]["text"] and "5, 15, 30" in b["0.5"]["text"] and "both" in b["0.6"]["text"] and CARD["sides_why"] in b["0.6"]["text"]
    # the folder: the card in plain words (its six lines), the spec as the plan has it, the first idea.json
    assert snap["tree"] == sorted([".lock", "idea.json", "card.md", "spec.json", "log.jsonl"])
    card = (d / "card.md").read_text(encoding="utf-8")
    assert [ln[:3] for ln in card.splitlines() if ln[:2] == "0."] == [f"0.{i}" for i in range(1, 8)]
    assert CARD["why"] in card and CARD["loser"] in card and "or_min" in card and "the Asian session" in card and "standard" in card
    spec = read(d / "spec.json")
    assert list(spec) == ["name", "version", "card", "run"] and (spec["name"], spec["version"]) == (NAME, 1)
    assert spec["card"] == CARD and spec["run"] == SETTINGS
    got = snap["idea"]
    assert (got["status"], got["phase"], got["round"], got["runs"], got["group"]) == ("idea", 0, None, [], "Ideas")
    assert sorted(r["saved"]) == sorted([str(d / "card.md"), str(d / "spec.json"), str(DRAFTS / f"{NAME}.py")])
    # the Lab: a record draft with the card block on top, filed under Ideas
    head = snap["draft"]
    assert head[0].startswith(IS.BLOCK_START) and head[1] == f"# {NAME} · IDEA · phase 0" and IS.BLOCK_END in head
    assert all(f"#   {ln}".rstrip() in head for ln in card.splitlines() if ln.strip()) and snap["group"] == "Ideas"
    assert r["lab"] == {"filed": "Ideas", "notes": []} and "Lab: draft_bpi_orb is filed under Ideas." in r["text"].split("\n")
    # the text: each line as pass or fail, then what a build will run, in plain words
    lines = r["text"].split("\n")
    assert lines[1:8] == [x["text"] for x in r["lines"]] and "\n" not in r["next"] and "bp.py build" in r["next"]
    for word in ("HOME", "NEIGHBOR", "NOT HERE", "2.5", "2.6", "no line reads it", "bpi_orb-NQ-tf15", "bpi_orb-NQ-tf5"):
        assert word in r["text"], word
    assert json.loads(json.dumps(r, default=lambda x: 1 / 0)) == json.loads(json.dumps(r))      # JSON-ready as it is


BAD = [  # (what the card says, the line that fails, a word of the reason)
    ({"card": {"why": ""}}, "0.1", "why it should make money"), ({"card": {"loser": "   "}}, "0.1", "losing side"),
    ({"card": {"why": "A range breaks. Then the trapped side has to cover."}}, "0.1", "2 sentences"),
    ({"run": {"family": "no_such_family"}}, "0.2", "entry trigger"), ({"run": {"exits": "extended"}}, "0.2", "standard"),
    ({"run": {"filters": [{"block": "momentum", "side": "with"}, {"block": "news", "side": "no"}, {"block": "volume", "side": "high"}]}}, "0.2", "at most 2"),
    ({"run": {"filters": [{"block": "book", "side": "agree"}]}, "card": {"neighbors": ["ES"]}}, "0.2", "Level 2"),
    ({"run": {"filters": [{"block": "momentum", "side": "with"}, {"block": "momentum", "side": "against"}]}}, "0.2", "one block"),
    ({"run": {"limits": {"trail_atr": 2.0}}}, "0.2", "standard"), ({"run": {"limits": {"exit_bars": 6}}}, "0.2", "standard"),
    ({"run": {"fixed": {"no_such_input": 1}}}, "0.2", "no_such_input"),
    ({"card": {"home": {"market": "NQ", "session": "nyam"}}}, "0.3", "bar"), ({"card": {"home": {"market": "CL", "session": "nyam", "bar": "15"}}}, "0.3", "CL"),
    ({"card": {"home": {"market": "NQ", "session": "nyam", "bar": "7"}}}, "0.3", "7"),
    ({"card": {"home": {"market": "NQ", "session": "all", "bar": "15"}}}, "0.3", "ONE home table"),
    ({"card": {"neighbors": []}}, "0.4", "where else"), ({"card": {"not_here": ""}}, "0.4", "NOT"),
    ({"card": {"neighbors": ["somewhere nice"]}}, "0.4", "somewhere"), ({"card": {"neighbors": ["NQ nyam 15"]}}, "0.4", "home"),
    ({"card": {"neighbors": ["midday", "mid"]}}, "0.4", "twice"), ({"card": {"not_here": "asia and london"}}, "0.4", "ONE place"),
    ({"card": {"not_here": "midday"}}, "0.4", "also"), 
    ({"card": {"main_setting": "n"}}, "0.5", "or_min"), ({"run": {"params": {"or_min": ["5", "15"]}}}, "0.5", "2 values"),
    ({"run": {"params": {"or_min": ["5", "15", "30", "45", "60"]}}}, "0.5", "5 values"),
    ({"run": {"params": {"or_min": ["5", "15", "30"], "max_tr": [1, 2]}}}, "0.5", "ONE setting"),
    ({"card": {"sides": "up"}}, "0.6", "both"), ({"card": {"sides_why": ""}}, "0.6", "why"), ({"card": {"loses_when": " "}}, "0.7", "when it should lose"),
    ({"card": {"sides": "long"}, "run": {"limits": {"dir": "short"}}}, "0.6", "dir")]


def test_every_missing_line_is_refused_and_named():
    root = tmp() / "ideas_bad"
    for changes, line, word in BAD:
        r = REC.card("bpi_bad", idea("bpi_bad", **changes), root)
        b = by(r)
        assert r["ok"] is False and list(r) == list(CONTRACT), changes                     # a refusal: the agreed keys and no other
        assert [x["line"] for x in r["lines"]] == [f"0.{i}" for i in range(1, 8)], changes
        assert b[line]["passed"] is False and word in b[line]["text"] and b[line]["text"].startswith(f"{line} FAIL "), (changes, b[line]["text"])
        assert [k for k, x in b.items() if x["passed"] is False] == [line], (changes, [x["text"] for x in r["lines"]])      # its own line, no other
        assert line in r["error"] and word in r["error"] and r["text"].split("\n")[-1] == "REFUSED: " + r["error"], r["error"]
        assert r["status"] is None and r["saved"] == [] and JOBS.code(r) == 2
    # two lines missing: both are named
    r = REC.card("bpi_bad", idea("bpi_bad", card={"why": "", "sides_why": ""}), root)
    assert "0.1" in r["error"] and "0.6" in r["error"] and [x["passed"] for x in r["lines"]] == [False, True, True, True, True, False, True]
    # what is no card at all is refused too: a field the card does not have (a date least of all), another idea's name
    for bad, word in ((idea("bpi_bad", run={"end": "2025-07-01"}), "end"), (idea("bpi_bad", card={"start": "2021-01-01"}), "start"),
                      (idea("bpi_bad", when="2026"), "when"), (idea("bpi_other"), "bpi_other"), ({"name": "bpi_bad"}, "card"),
                      ({"name": "bpi_bad", "card": CARD, "run": "orb"}, "settings"), ("not a card", "JSON object")):
        refused(lambda bad=bad: REC.card("bpi_bad", bad, root), word)
    for name, word in (("orb", "family"), ("c1x", "c1"), ("bpi_orb_r2", "_r2"), ("Bad Name", "name"), ("x", "name"), ("draft_x", "reserved")):
        refused(lambda name=name: REC.card(name, idea(name), root), word)
    assert not root.exists() and not (DRAFTS / "bpi_bad.py").exists()            # a refused card writes nothing
    RESULTS["test_every_missing_line_is_refused_and_named"] = (len(BAD), len(BAD), "cards with one line missing, each refused on its own line")


def test_the_card_can_be_written_again_until_a_round_binds_it():
    root = tmp() / "ideas_again"
    first = REC.card("bpi_again", idea("bpi_again"), root)
    again = REC.card("bpi_again", idea("bpi_again", card={"neighbors": ["midday", "afternoon"]}), root)       # before any run: the card is corrected
    assert first["ok"] and again["ok"] and read(root / "bpi_again" / "spec.json")["card"]["neighbors"] == ["midday", "afternoon"]
    assert "afternoon" in (root / "bpi_again" / "card.md").read_text() and again["lab"]["filed"] is None        # filed once
    # a round on file: the settings may still change (the next round runs them), the entry trigger may not -- that is a new idea
    IS.write_reason("bpi_again", 1, "a first look", root)
    IS.write_round_spec("bpi_again", 1, {**idea("bpi_again"), "round": 1}, root)
    assert REC.card("bpi_again", idea("bpi_again", run={"limits": {"max_tr": 1}}), root)["ok"] is True
    word = refused(lambda: REC.card("bpi_again", idea("bpi_again", run={"family": "donchian", "params": {"n": [10, 20, 40]}}, card={"main_setting": "n"}), root), "new idea")
    assert "donchian" in word and read(root / "bpi_again" / "spec.json")["run"]["family"] == "orb"
    # frozen (lock.json): nothing changes any more
    IS.write_lock("bpi_again", {"hash": "0123abcd"}, root)
    refused(lambda: REC.card("bpi_again", idea("bpi_again"), root), "frozen")
    with tiny():
        refused(lambda: REC.build("bpi_again", "one more try", root=root), "frozen")


# ================================================================ (b) from a card to the tables

def test_the_card_names_the_tables():
    rows, p = REC.card_lines(idea())
    assert all(x["passed"] for x in rows)
    assert p["home"] == {"market": "NQ", "session": "nyam", "bar": "15", "table": "NQ-tf15-nyam", "said": "home"}
    assert [(x["table"], x["said"]) for x in p["neighbors"]] == [("NQ-tf15-mid", "midday"), ("NQ-tf5-nyam", "5-minute bars")]
    assert (p["not_here"]["table"], p["not_here"]["said"]) == ("NQ-tf15-asia", "the Asian session")
    assert p["stores"] == [{"market": "NQ", "bar": "15", "sessions": ["asia", "nyam", "mid"]}, {"market": "NQ", "bar": "5", "sessions": ["nyam"]}]
    assert (p["sides"], p["filters"], p["main_setting"], p["values"], p["variants"]) == ("both", [], "or_min", ["5", "15", "30"], 144)
    # the engine's settings of each store: run_idea's format, checked by run_idea and by the runner of the build range
    specs = REC.engine(idea(), p, NAME)
    assert [(s["name"], s["markets"], s["bar_sizes"], s["sessions"]) for s in specs] == [(NAME, ["NQ"], ["15"], ["asia", "nyam", "mid"]), (NAME, ["NQ"], ["5"], ["nyam"])]
    assert all(s["family"] == "orb" and s["exits"] == "standard" and s["params"] == SETTINGS["params"] and CARD["why"] in s["reason"] for s in specs)
    assert [RUN.checked(s)["name"] for s in specs] == [NAME, NAME] and REC.engine(idea(), p, "bpi_orb_r2")[0]["name"] == "bpi_orb_r2"
    # places in the card's own words: a market, a session or a bar size; what is not said is the home's
    home = {"market": "GC", "session": "pre", "bar": "15"}
    for said, table in (("GC pre 5", "GC-tf5-pre"), ("NQ pre 15", "NQ-tf15-pre"), ("the Asian session", "GC-tf15-asia"), ("asia", "GC-tf15-asia"),
                        ("ES", "ES-tf15-pre"), ("30-minute bars", "GC-tf30-pre"), ("tf5", "GC-tf5-pre"), ("1m", "GC-tf1-pre"), ("gold, London", "GC-tf15-london"),
                        ("New York morning", "GC-tf15-nyam"), ("the afternoon on 5 min bars", "GC-tf5-pm"), ("ES midday 30 minutes", "ES-tf30-mid")):
        assert REC.place(said, home)["table"] == table, said
    for said, word in (("somewhere nice", "somewhere"), ("", "names no place"), ("asia and london", "ONE place"), ("NQ ES", "ONE place"), ("5 15", "ONE place"),
                       ("NQ 08:30", "08:30")):
        try:
            REC.place(said, home)
            raise AssertionError(f"read as a place: {said!r}")
        except ValueError as e:
            assert word in str(e), (said, str(e))
    # sister markets and other bar sizes are stores of their own; a one-sided card runs one side only
    rows, p = REC.card_lines(idea(card={"neighbors": ["ES", "GC pre-market 30m"], "sides": "long", "sides_why": "the index drifts up"}))
    assert all(x["passed"] for x in rows) and [x["table"] for x in p["neighbors"]] == ["ES-tf15-nyam", "GC-tf30-pre"] and p["sides"] == "long"
    assert p["stores"] == [{"market": "NQ", "bar": "15", "sessions": ["asia", "nyam"]}, {"market": "ES", "bar": "15", "sessions": ["nyam"]},
                           {"market": "GC", "bar": "30", "sessions": ["pre"]}]
    assert all(s["limits"] == {"dir": "long"} for s in REC.engine(idea(card={"sides": "long"}), p, NAME))
    rows, p = REC.card_lines(idea(run={"filters": [{"block": "momentum", "side": "with"}]}))
    assert p["filters"] == ["momentum_with"] and "momentum with" in by({"lines": rows})["0.2"]["text"] and by({"lines": rows})["0.2"]["number"] == 1
    # a place the entry trigger never trades in is no neighbor (ib_n: New York sessions only)
    ib = idea(run={"family": "ib_n", "params": {"ib_min": ["5", "15", "30"]}, "fixed": {"mode": "break"}}, card={"main_setting": "ib_min", "not_here": "London"})
    rows, p = REC.card_lines(ib)
    assert p is None and [x["line"] for x in rows if x["passed"] is False] == ["0.4"] and "never trades" in by({"lines": rows})["0.4"]["text"]


def test_line_2_6_follows_the_cards_sides():
    t = {"long": 500.0, "short": -80.0, "n_long": 30, "n_short": 12}
    assert L.sides(t)["passed"] is False and L.sides({**t, "sides": "both"})["passed"] is False
    r = L.sides({**t, "short": 0.0, "n_short": 0, "sides": "long"})             # one-sided by its card: judged on that side
    assert r["passed"] is True and r["number"] == 500.0 and r["text"] == "2.6 PASS long only by its card: $500, all variants together (need above $0)"
    r = L.sides({**t, "long": -5.0, "short": 0.0, "n_short": 0, "sides": "long"})
    assert r["passed"] is False and r["text"].startswith("2.6 FAIL long only by its card: -$5")
    r = L.sides({**t, "sides": "long"})                                          # ... and a trade on the other side is not the card's rule
    assert r["passed"] is False and "12 short trades" in r["text"] and "long only by its card" in r["text"]
    r = L.sides({"long": 500.0, "short": 0.0, "n_long": 30, "n_short": 0, "sides": "both"})      # both sides by its card: a side without a trade made no money
    assert r["passed"] is False and r["text"] == "2.6 FAIL long $500, short: no trade, all variants together (need both above $0)"
    assert L.sides({"long": 500.0, "short": 0.0, "n_long": 30, "n_short": 0})["passed"] is True      # no card (a dry run): as before
    assert L.sides({"long": 0.0, "short": 0.0, "n_long": 0, "n_short": 0, "sides": "short"})["text"] == "2.6 FAIL no trade"


# ================================================================ (c) the build with rounds

def test_what_a_build_refuses_before_anything_runs():
    root = tmp() / "ideas_refuse"
    with tiny(), no_engine():
        refused(lambda: REC.build("bpi_none", "a reason", root=root), "no card")
        assert "--spec-file" in refused(lambda: REC.build("bpi_none", "a reason", root=root), "bp.py card") and not root.exists()
        IS.create("bpi_bare", root)                                              # an idea folder without its card
        refused(lambda: REC.build("bpi_bare", "a reason", root=root), "no card")
        REC.card("bpi_ref", idea("bpi_ref"), root)
        for empty in ("", "   ", None):
            refused(lambda empty=empty: REC.build("bpi_ref", empty, root=root), "--reason")
        refused(lambda: REC.build("Bad Name", "a reason", root=root), "name")
    # any day from 2025-07-01 on
    for days in (DAYS + ["2025-07-01"], ["2025-07-01"], ["2026-09-22"]):
        with tiny(days=days), no_engine():
            assert "2025-07-01" in refused(lambda: REC.build("bpi_ref", "a reason", root=root), "2025-06-30")
    # a control pool with fewer than the 10 seeds the law asks for
    thin = tmp() / "runs_thin"
    grid = [{"id": f"s{sd}_{c}", "vi": sd - 1, "xi": i, "variant": {"seed": sd}, "exit": {}} for sd in (1, 2) for i, c in enumerate(CELLS)]
    res = [{"trades": [], "sessions": 3, "used": 3, "skipped": [], "no_trade": [], "elapsed_s": 0.0, "skipped_by_error": 0,
            "meta": {"inputs": {}, "engine": "hand-made", "root": "NQ",
                     "range": {"start": "2021-09-22", "end": "2025-06-30", "holdout": True, "period": "bp_build"}}} for _ in grid]
    LB.write_unit("c1-NQ-tf15", {"family": "random", "control": "c1", "tf": "15", "seeds": [1, 2], "period": "bp_build", "days": DAYS}, grid, res, thin)
    with tiny(out=str(thin)), no_engine():
        word = refused(lambda: REC.build("bpi_ref", "a reason", root=root), "2 of the 10 seeds")
        assert "c1-NQ-tf15" in word
    # one build of an idea at a time: a job of it that is still at work
    jd = root / "_jobs" / "20260101T000000-abc123"
    jd.mkdir(parents=True)
    (jd / "job.json").write_text(json.dumps({"id": jd.name, "command": "build", "name": "bpi_ref", "state": "running", "pid": os.getpid(), "args": {}}))
    with tiny(), no_engine():
        assert jd.name in refused(lambda: REC.build("bpi_ref", "a reason", root=root), "still running")
    (jd / "job.json").write_text(json.dumps({"id": jd.name, "command": "build", "name": "bpi_ref", "state": "done", "pid": os.getpid(), "args": {}}))
    assert JOBS.running("bpi_ref", root) is None and JOBS.running("bpi_other", root) is None
    # the test-only switch is never taken for the app's own idea folder
    with tiny(), no_engine():
        refused(lambda: REC.build("bpi_ref", "a reason", root=HOME / "ideas"), REC.TEST_RUN)
    assert tree(root / "bpi_ref") == sorted([".lock", "idea.json", "card.md", "spec.json", "log.jsonl"]) and stores(thin) == ["c1-NQ-tf15"]
    assert IS.rounds("bpi_ref", root) == [] and IS.read_idea("bpi_ref", root)["phase"] == 0      # no refusal left a reason, a round or a store


def test_the_reason_is_on_disk_before_anything_runs():
    root = tmp() / "ideas_reason"
    REC.card("bpi_why", idea("bpi_why"), root)
    d, keep, seen = root / "bpi_why", RUN.run_build, []

    def failing(specs, *a, dry=False, **k):
        if dry:
            return keep(specs, *a, dry=True, **k)
        seen.append(((d / "rounds" / "1" / "reason.txt").read_text(), read(d / "rounds" / "1" / "spec.json")["round"], stores(tmp() / "runs_reason")))
        raise J.Refuse("planted: the run fails")

    try:
        RUN.run_build = failing
        with tiny(out=str(tmp() / "runs_reason"), ledger=str(tmp() / "ledger_reason.csv")), no_engine():
            refused(lambda: REC.build("bpi_why", "  the first reason,\n written before the run ", root=root), "planted")
    finally:
        RUN.run_build = keep
    assert seen == [("the first reason, written before the run\n", 1, [])]         # on disk when the run started, and nothing was stored yet
    assert (d / "rounds" / "1" / "reason.txt").read_text() == "the first reason, written before the run\n"
    assert not (d / "rounds" / "1" / "build.json").exists() and IS.rounds("bpi_why", root) == [1] and IS.status("bpi_why", root) == "idea"
    got = IS.read_idea("bpi_why", root)
    assert (got["phase"], got["round"]) == (2, 1)
    # a round without a result is not a round that was used: the next build is round 1 again, with its own reason
    with tiny(out=str(tmp() / "runs_reason"), ledger=str(tmp() / "ledger_reason.csv")), no_engine():
        kw = REC.start("bpi_why", "the second reason", root=root)
    assert (kw["round_"], kw["counted"], kw["reason"]) == (1, True, "the second reason")
    assert (d / "rounds" / "1" / "reason.txt").read_text() == "the second reason\n" and IS.rounds("bpi_why", root) == [1]


def test_round_one_runs_what_is_missing_and_saves_everything():
    a = life(1)
    r, d, snap = a[1], ROOT / NAME, a["snap1"]
    assert list(r)[:len(CONTRACT)] == list(CONTRACT)
    assert [r[k] for k in ("ok", "command", "name", "phase", "round", "job", "error")] == [True, "build", NAME, 2, 1, None, None]
    assert (r["counted"], r["dry_run"], r["smoke"], r["test_run"]) == (True, False, True, True)
    assert (r["store"], r["home"], r["unit"], r["filter"], r["bar"], r["reason"]) == (NAME, "NQ-tf15-nyam", "bpi_orb-NQ-tf15-nyam", None, 0.95, REASONS[1])
    # what was missing was run: the pool and the idea's table of each market and bar size the card names, ONE pass each
    assert stores() == ["bpi_orb-NQ-tf15", "bpi_orb-NQ-tf5", "c1-NQ-tf15", "c1-NQ-tf5"]
    assert [(s["key"], s["kind"], s["skipped"], s["ok"]) for s in r["stores"]] == [("c1-NQ-tf15", "pool", False, True), ("bpi_orb-NQ-tf15", "unit", False, True),
                                                                                  ("c1-NQ-tf5", "pool", False, True), ("bpi_orb-NQ-tf5", "unit", False, True)]
    m15, m5 = read(OUT / "bpi_orb-NQ-tf15" / "run.json"), read(OUT / "bpi_orb-NQ-tf5" / "run.json")
    assert (m15["sessions"], m5["sessions"], m15["days"], m15["period"], m15["idea"]) == (["asia", "nyam", "mid"], ["nyam"], DAYS, "bp_build", NAME)
    assert [(x["stage"], x["key"]) for x in LB.read_ledger(LEDGER)] == [("null_bp", "c1-NQ-tf15"), ("bp_build", "bpi_orb-NQ-tf15"), ("null_bp", "c1-NQ-tf5"),
                                                                       ("bp_build", "bpi_orb-NQ-tf5")]
    # every line of the law, 2.1 to 2.9, is in the result: null = it does not apply, and its text says why
    b = by(r)
    assert [x["line"] for x in r["lines"]] == BUILD_LINES and all(x["text"].startswith(x["line"] + " ") for x in r["lines"])
    assert b["2.7"]["passed"] is None and "no filter" in b["2.7"]["text"] and r["not_applicable"] == ["2.7"]
    assert (b["2.3"]["need"], b["2.3"]["round"], b["2.3"]["seeds"], b["2.3"]["thin"]) == (0.95, 1, 10, False)
    assert b["2.9"] == {"line": "2.9", "passed": True, "number": 1, "need": 5, "reason": REASONS[1],
                        "text": f"2.9 PASS round 1 of at most 5, its reason written before the run: {REASONS[1]}"}
    assert r["failed"] == [x["line"] for x in r["lines"] if x["passed"] is False] and r["passed"] is (not r["failed"])
    # 2.5 is read on the neighbors the CARD names (not on every other table of the store); the place it should NOT work is
    # run and shown, and no line reads it
    assert [(n["table"], n["said"], n["store"]) for n in r["neighbors"]] == [("NQ-tf15-mid", "midday", "runs/bpi_orb-NQ-tf15"),
                                                                             ("NQ-tf5-nyam", "5-minute bars", "runs/bpi_orb-NQ-tf5")]
    assert (r["not_here"]["table"], r["not_here"]["said"]) == ("NQ-tf15-asia", "the Asian session")
    avg = lambda key, sess: J.table_stats(LB.plateau_units(LB.load_unit(key, OUT), sess)[""])  # noqa: E731
    for n, (key, sess) in zip(r["neighbors"] + [r["not_here"]], (("bpi_orb-NQ-tf15", "mid"), ("bpi_orb-NQ-tf5", "nyam"), ("bpi_orb-NQ-tf15", "asia"))):
        ts = avg(key, sess)
        assert (n["variants"], n["avg_net"], n["profitable"]) == (ts["cells"], ts["avg_net"], bool(ts["avg_net"] is not None and ts["avg_net"] > 0)), n
    own = [n for n in r["neighbors"] if not n["copy"]]             # a neighbor that is the home table's trades again counts once: not at all
    k = sum(n["profitable"] for n in own)
    assert (b["2.5"]["tables"], b["2.5"]["profitable"], b["2.5"]["number"]) == (len(own), k, k / len(own) if own else 0.0)
    assert b["2.5"]["copies"] == [n["said"] for n in r["neighbors"] if n["copy"]] and len(own) + len(b["2.5"]["copies"]) == 2
    assert (b["2.6"]["n_long"] + b["2.6"]["n_short"]) > 0 and r["sides"] == "both" and r["table"]["variants"] == 6 and r["notes"] == []
    # the folder: the reason, the round's settings (the card as it stood, the store name, the tables), the result
    assert snap["tree"] == sorted([".lock", "idea.json", "card.md", "spec.json", "log.jsonl", "rounds/1/reason.txt", "rounds/1/spec.json", "rounds/1/build.json"])
    assert (d / "rounds/1/reason.txt").read_text() == REASONS[1] + "\n"
    rs = read(d / "rounds/1/spec.json")
    assert (rs["round"], rs["store"], rs["card"], rs["run"]) == (1, NAME, CARD, SETTINGS) and rs["plan"]["home"]["table"] == "NQ-tf15-nyam"
    saved = read(d / "rounds/1/build.json")
    assert saved["lines"] == plain(r)["lines"] and (saved["round"], saved["bar"], saved["dry_run"], saved["ok"], saved["job"]) == (1, 0.95, False, True, None)
    assert saved["next"] == r["next"] and saved["status"] == r["status"] and str(d / "rounds/1/build.json") in r["saved"]
    assert sorted(r["saved"]) == sorted([str(OUT / k) for k in stores()] + [str(d / f"rounds/1/{f}") for f in ("reason.txt", "spec.json", "build.json")])
    # the status is the app's reading of what is saved; idea.json and the Lab follow
    got, status = snap["idea"], "lead" if r["passed"] else "idea"
    assert r["status"] == status == got["status"] == saved["status"] and (got["phase"], got["round"], got["next"]) == (2, 1, r["next"])
    assert [x["line"] for x in got["lines"]] == BUILD_LINES and snap["group"] == IS.group_for(status)
    head = snap["draft"]
    assert head[1] == f"# {NAME} · {status.upper()} · phase 2 · round 1" and "# LATEST VERDICT" in head and f"#   {b['2.9']['text']}" in head
    # the text: the lines, the status and the next step in one sentence
    text = r["text"].split("\n")
    assert text[0] == f"TEST RUN on 3 named days of the build range (2021-09-22 .. 2025-06-30): it counts only because {REC.TEST_RUN} is set."
    assert text[1].startswith(f"{NAME} · round 1 of at most 5 · random bar 95 % · home NQ New York morning 15-minute bars")
    assert text[2:11] == [x["text"] for x in r["lines"]]
    for word in ("NEIGHBOR", "NOT HERE", "no line reads it", "RESULT", f"STATUS: {status.upper()} · phase 2 · round 1"):
        assert word in r["text"], word
    assert r["next"] and "\n" not in r["next"] and r["next"].count(". ") == 0
    RESULTS["test_round_one_runs_what_is_missing_and_saves_everything"] = (4, 4, "stores in 2 tape passes; 9 lines saved")


def test_a_filter_keeps_the_stores_and_a_changed_base_setting_gets_its_own():
    a = life(3)
    f, c, d = a[2], a[3], ROOT / NAME
    # round 2 adds a filter: the plain stores are the ones of round 1 (no store is written twice), the filter's are new
    assert (f["round"], f["store"], f["bar"], f["filter"], f["unit"]) == (2, NAME, 0.975, "momentum_with", "bpi_orb__momentum_with-NQ-tf15-nyam")
    assert [(s["key"], s["skipped"]) for s in f["stores"]] == [("c1-NQ-tf15", True), ("bpi_orb-NQ-tf15", True), ("bpi_orb__momentum_with-NQ-tf15", False),
                                                               ("c1-NQ-tf5", True), ("bpi_orb-NQ-tf5", True), ("bpi_orb__momentum_with-NQ-tf5", False)]
    b = by(f)
    assert [x["line"] for x in f["lines"]] == BUILD_LINES and f["not_applicable"] == [] and b["2.3"]["need"] == 0.975 and b["2.9"]["number"] == 2
    assert b["2.7"]["passed"] is not None and b["2.7"]["filters"][0]["name"] == "filter momentum with against the plain version"
    assert [n["store"] for n in f["neighbors"]] == ["runs/bpi_orb__momentum_with-NQ-tf15", "runs/bpi_orb__momentum_with-NQ-tf5"]      # its neighbors wear the filter too
    assert f["table"]["store"] == "runs/bpi_orb__momentum_with-NQ-tf15" and read(d / "rounds/2/spec.json")["store"] == NAME
    # round 3 changes a base setting (one entry a session): its own stores, under its own name
    assert (c["round"], c["store"], c["bar"], c["filter"], c["unit"]) == (3, "bpi_orb_r3", 0.983, None, "bpi_orb_r3-NQ-tf15-nyam")
    assert [(s["key"], s["skipped"]) for s in c["stores"]] == [("c1-NQ-tf15", True), ("bpi_orb_r3-NQ-tf15", False), ("c1-NQ-tf5", True), ("bpi_orb_r3-NQ-tf5", False)]
    assert read(OUT / "bpi_orb_r3-NQ-tf15" / "run.json")["limits"] == {"max_tr": 1} and read(d / "rounds/3/spec.json")["run"]["limits"] == {"max_tr": 1}
    assert stores() == ["bpi_orb-NQ-tf15", "bpi_orb-NQ-tf5", "bpi_orb__momentum_with-NQ-tf15", "bpi_orb__momentum_with-NQ-tf5", "bpi_orb_r3-NQ-tf15", "bpi_orb_r3-NQ-tf5",
                        "c1-NQ-tf15", "c1-NQ-tf5"]
    assert {k: (OUT / k / "cells.npz").stat().st_mtime_ns for k in a["stamp"]} == a["stamp"]          # the stores of round 1 were never touched again
    assert IS.rounds(NAME, ROOT) == [1, 2, 3] and [read(d / f"rounds/{n}/build.json")["bar"] for n in (1, 2, 3)] == BARS[:3]
    assert [(d / f"rounds/{n}/reason.txt").read_text() for n in (1, 2, 3)] == [REASONS[n] + "\n" for n in (1, 2, 3)]
    assert read(d / "rounds/1/spec.json")["run"] == SETTINGS                     # what round 1 ran with stays on file as it was
    # a rule with two filters: the plain table, each filter alone and BOTH on are run (the card's engine spec lists all three)
    root = tmp() / "ideas_two"
    two = idea("bpi_two", run={"filters": [{"block": "momentum", "side": "with"}, {"block": "news", "side": "no"}]})
    assert REC.card("bpi_two", two, root)["ok"] is True
    sp = REC._spec("bpi_two", two)
    plan = REC.card_lines(sp)[1]
    assert REC.rule_filter(plan) == "momentum+news_with+no" and plan["filters"] == ["momentum_with", "news_no"]
    es = REC.engine(sp, plan, "bpi_two")[0]
    assert es["filters"][-1] == {"all": sp["run"]["filters"]} and len(es["filters"]) == 3
    checked = RUN.checked(es)
    assert [f for f in checked["filters"]] == [("momentum", "with"), ("news", "no"), ("momentum+news", "with+no")]
    RESULTS["test_a_filter_keeps_the_stores_and_a_changed_base_setting_gets_its_own"] = (3, 3, "rounds of one idea: plain, + a filter, a changed base setting")


def test_the_store_name_of_a_round():
    """A store is never written twice, so a round takes the first name under which nothing on disk was written from other
    inputs: the earlier rounds' names, then <idea> (round 1) or <idea>_r<n>, then that name + b, c ..."""
    sp, out = REC._spec("bpi_sfx", idea("bpi_sfx")), tmp() / "runs_names"
    p = REC.card_lines(sp)[1]
    name = lambda n, earlier=(): REC._store("bpi_sfx", n, sp, p, list(earlier), out, DAYS, CELLS)  # noqa: E731
    assert (name(1), name(2), name(3, ["bpi_sfx_r2", "bpi_sfx"])) == ("bpi_sfx", "bpi_sfx_r2", "bpi_sfx_r2")      # nothing on disk
    for key in ("bpi_sfx-NQ-tf15", "bpi_sfx_r2-NQ-tf5"):                         # stores of other inputs under two of the names
        (out / key).mkdir(parents=True)
        (out / key / "run.json").write_text(json.dumps({"inputs_hash": "0" * 16}))
    assert (name(1), name(2), name(2, ["bpi_sfx"]), name(3, ["bpi_sfx_r2", "bpi_sfx"])) == ("bpi_sfx_r1b", "bpi_sfx_r2b", "bpi_sfx_r2b", "bpi_sfx_r3")
    part = next(x for x in RUN.parts(RUN.checked(REC.engine(sp, p, "bpi_sfx")[0]), CELLS) if x["key"] == "bpi_sfx-NQ-tf15")
    (out / "bpi_sfx-NQ-tf15" / "run.json").write_text(json.dumps({"inputs_hash": RUN.fingerprint(part, DAYS)}))
    assert (name(1), name(2, ["bpi_sfx"])) == ("bpi_sfx", "bpi_sfx")             # the same inputs: the same stores, read again
    for bad in ("bpi_sfx_r2", "bpi_sfx_r1b", "nq_orb_r5"):                       # ... and no idea is named like the stores of a later round
        refused(lambda bad=bad: REC.card(bad, idea(bad), tmp() / "ideas_names"), "later round")


def test_every_line_passing_makes_a_lead():
    a = life(4)
    r = a[4]
    assert (r["round"], r["store"], r["bar"], r["passed"], r["failed"], r["status"]) == (4, "bpi_orb_r3", 0.9875, True, [], "lead")
    assert all(s["skipped"] for s in r["stores"])                                # the same settings as round 3: nothing ran again
    assert IS.status(NAME, ROOT) == "lead" and IS.read_idea(NAME, ROOT)["group"] == "Leads" == group(NAME) and r["lab"]["filed"] == "Leads"
    assert draft(NAME)[1] == f"# {NAME} · LEAD · phase 2 · round 4" and f"STATUS: LEAD · phase 2 · round 4" in r["text"]
    assert "Lab: draft_bpi_orb is filed under Leads." in r["text"].split("\n")
    log = [json.loads(x) for x in (ROOT / NAME / "log.jsonl").read_text().splitlines()]
    assert [(x["was"], x["now"]) for x in log if x["event"] == "status"][-1] == ("idea", "lead")
    # the code check is not on file: that is the next step, before the freeze
    assert "code-check" in r["next"] and "bpi_orb_r3-NQ-tf15" in r["next"] and r["code_check"] == {"on_file": False, "passed": None}
    IS.write_check(NAME, {"ok": True, "command": "code-check", "passed": True, "lines": []}, ROOT)
    assert "lock" in REC.status(NAME, ROOT)["next"]


def test_rounds_are_counted_the_bar_rises_and_round_six_is_refused():
    root, name = tmp() / "ideas_five", "bpi_five"
    REC.card(name, idea(name, card={"neighbors": ["midday"], "sides": "long", "sides_why": "the index drifts up"}), root)      # one store; one side
    got = []
    for n in range(1, 6):
        with tiny():
            with contextlib.ExitStack() as stack:
                if n > 1:
                    stack.enter_context(no_engine())                             # the same settings: every store is there, nothing runs again
                r = REC.build(name, f"reason of round {n}", root=root)
        b = by(r)
        got.append((r["round"], r["bar"], b["2.3"]["need"], b["2.9"]["number"], r["store"]))
        assert r["passed"] is False and "2.4" in r["failed"]                     # 3 days: never 200 trades
        assert "long only by its card" in b["2.6"]["text"] and b["2.6"]["n_short"] == 0 and r["sides"] == "long"      # judged on the card's side
        assert len(r["notes"]) == 1 and "tilted control" in r["notes"][0] and f"NOTE: {r['notes'][0]}." in r["text"].split("\n")
        assert r["status"] == IS.status(name, root) == ("idea" if n < 5 else "shelved")
        assert (f"round {n + 1}" in r["next"] and f"{100 * BARS[n]:g} %" in r["next"]) if n < 5 else ("SHELVED" in r["next"])
    assert got == [(n, BARS[n - 1], BARS[n - 1], n, name) for n in range(1, 6)] and BARS == [R.need("2.3", n) for n in range(1, 6)]
    assert IS.rounds(name, root) == [1, 2, 3, 4, 5] and all((root / name / f"rounds/{n}/build.json").is_file() for n in range(1, 6))
    assert stores() and [k for k in stores() if k.startswith(name)] == [f"{name}-NQ-tf15"] and read(OUT / f"{name}-NQ-tf15" / "run.json")["limits"] == {"dir": "long"}
    assert IS.read_idea(name, root)["group"] == "Shelved" == group(name) and draft(name)[1] == f"# {name} · SHELVED · phase 2 · round 5"
    with tiny(), no_engine():
        word = refused(lambda: REC.build(name, "a sixth try", root=root), "round 6")
    assert "5" in word and IS.rounds(name, root) == [1, 2, 3, 4, 5] and not (root / name / "rounds" / "6").exists()
    rc, txt = _run(["build", name, "--reason=a sixth try", f"--root={root}", "--json"])
    d = json.loads(txt)
    assert rc == 2 and d["ok"] is False and "round 6" in d["error"] and (d["command"], d["name"], d["lines"]) == ("build", name, [])
    RESULTS["test_rounds_are_counted_the_bar_rises_and_round_six_is_refused"] = (5, 5, "rounds, then the sixth refused")


def test_a_run_on_named_days_is_a_smoke_run_and_saves_nothing():
    root, name = tmp() / "ideas_smoke", "bpi_orb"                                # idea A's name and settings: its stores are there
    life(1)
    REC.card(name, idea(name), root)
    was = tree(root / name)
    keep, RUN.clock = RUN.clock, lambda: SAT
    try:
        with no_engine():
            r = REC.build(name, "a look at the plumbing", root=root, days=DAYS, cells=CELLS, out=str(OUT), ledger=str(LEDGER))
            rc, txt = _run(["build", name, "--reason=a look at the plumbing", "--days=" + ",".join(DAYS), "--cells=" + ",".join(CELLS), f"--out={OUT}",
                            f"--ledger={LEDGER}", f"--root={root}", "--json"])
    finally:
        RUN.clock = keep
    assert (r["counted"], r["dry_run"], r["smoke"], r["round"], r["status"], r["saved"]) == (False, True, True, 1, "idea", [])
    assert [x["line"] for x in r["lines"]] == BUILD_LINES and "no verdict" in r["next"] and r.get("test_run") is None
    assert tree(root / name) == was and IS.rounds(name, root) == [] and IS.read_idea(name, root)["phase"] == 0
    d = json.loads(txt)
    assert rc == 0 and d["dry_run"] is True and d["lines"] == plain(r)["lines"] and tree(root / name) == was
    # named days take their own store folder and ledger (the runner's rule): never runs_bp/ or ledger.csv
    with no_engine():
        refused(lambda: REC.build(name, "a look", root=root, days=DAYS, cells=CELLS), "named days")
    # the options of the one-table build belong to --spec-file: an idea's record says its own home, filter and round
    for opt in ("--home=NQ-tf15-mid", "--filter=momentum_with", "--round=2"):
        rc, txt = _run(["build", name, "--reason=x", opt, f"--root={root}"])
        assert rc == 2 and "--spec-file" in txt, txt


# ================================================================ (e) the default variant, in the app

def test_the_default_is_the_middle_survivor():
    rows = [{"id": "a", "net": 50.0, "vi": 0, "xi": 0}, {"id": "b", "net": -10.0, "vi": 0, "xi": 1}, {"id": "c", "net": 300.0, "vi": 1, "xi": 0},
            {"id": "d", "net": 120.0, "vi": 1, "xi": 1}, {"id": "e", "net": 0.0, "vi": 2, "xi": 0}, {"id": "f", "net": 80.0, "vi": 2, "xi": 1}]
    ids = [x["id"] for x in rows]
    assert REC.middle(rows, ids) == ("f", ["a", "f", "d", "c"])                  # 4 survivors by net: the lower of the two middle ones; never the best
    assert REC.middle(rows, ["a", "c", "d"]) == ("d", ["a", "d", "c"]) and REC.middle(rows, ["b", "e"]) == (None, [])
    assert REC.middle(rows[:1], ["a"]) == ("a", ["a"])
    tie = [{"id": "x", "net": 10.0, "vi": 1, "xi": 0}, {"id": "y", "net": 10.0, "vi": 0, "xi": 3}, {"id": "z", "net": 10.0, "vi": 0, "xi": 1}]
    assert REC.middle(tie, ["x", "y", "z"]) == ("y", ["z", "y", "x"])            # equal nets: the variant order decides
    assert "middle" in J.TIE_RULE


def test_the_default_variant_is_shown_in_the_app():
    a = life(1)
    r, d = a[1], a[1]["default"]
    st = J.store({"dir": OUT, "key": "bpi_orb-NQ-tf15"})
    rows = {x["id"]: x for x in LB.plateau_units(st, "nyam")[""]}
    cell, surv = REC.middle(list(rows.values()), J.table_stats(list(rows.values()))["ids"])
    if cell is None:                                                             # no variant made money on the 3 days: nothing to show, and it says so
        assert d == {"cell": None, "survivors": 0, "trades": None, "run_id": None, "note": d["note"]} and "no variant" in d["note"] and a["snap1"]["idea"]["runs"] == []
        cell = sorted(rows)[0]                                                   # ... the same steps then, for a cell named here
        d = REC.show(NAME, 1, RUN.checked(REC.engine(idea(), read(ROOT / NAME / "rounds/1/spec.json")["plan"], NAME)[0]), "bpi_orb-NQ-tf15", cell, "nyam", st,
                     DAYS, len(surv), ROOT, str(TESTER))
    else:
        assert (d["cell"], d["survivors"]) == (cell, len(surv)) and a["snap1"]["idea"]["runs"] == [d["run_id"]]
        assert f"tester run {d['run_id']}" in r["text"] and d["cell"] in r["text"]
    # the run is a finished run of the tester: listed under the idea's Lab draft, marked as imported, the engine's own trades
    assert d["run_id"] and d["note"] is None, d
    run = TESTER / "runs" / d["run_id"]
    meta, trades = read(run / "run.json"), json.loads((run / "trades.json").read_text())
    assert (meta["strategy"]["id"], meta["strategy"]["root"], meta["imported"]["source"]) == ("draft_bpi_orb", "NQ", "research engine")
    assert NAME in meta["strategy"]["name"] and d["cell"] in meta["strategy"]["name"] and "round 1" in meta["imported"]["note"]
    assert (meta["range"]["start"], meta["range"]["end"], meta["coverage"]["sessions"]) == (DAYS[0], DAYS[-1], len(DAYS))
    x = J.cellx(st, d["cell"], "nyam")
    assert len(trades) == d["trades"] == len(x["net"]) > 0 and abs(sum(t["net"] for t in trades) - float(x["net"].sum())) < 0.01
    assert sorted(t["entry_ms"] for t in trades) == sorted(int(v) for v in x["entry_ms"]) and all(t["entry_price"] > 0 and t["exit_price"] > 0 for t in trades)
    assert read(run / "status.json")["status"] == "done" and not [p.name for p in (TESTER / "runs").iterdir() if p.name[0] == "."]      # whole, or not there
    # an idea folder that was moved never writes the app's own tester: without a folder for the runs nothing is shown, and it says so
    other = life(3)[3]["default"]
    assert other["run_id"] is None and (other["cell"] is None or "--tester" in other["note"])
    # a variant whose trades do not come out as its store has them is not shown (after a change to the code: line 1.6)
    keep = RUN.cell_trades
    try:
        RUN.cell_trades = lambda *a_, **k_: keep(*a_, **k_)[:-1]
        bad = REC.show(NAME, 1, RUN.checked(REC.engine(idea(), read(ROOT / NAME / "rounds/1/spec.json")["plan"], NAME)[0]), "bpi_orb-NQ-tf15", d["cell"], "nyam", st, DAYS,
                       1, ROOT, str(TESTER))
    finally:
        RUN.cell_trades = keep
    assert bad["run_id"] is None and "1.6" in bad["note"] and len(list((TESTER / "runs").iterdir())) == len({d["run_id"], a[1]["default"]["run_id"]} - {None})


# ================================================================ (d) the status command

def test_status_one_line_an_idea_or_the_full_record_of_one():
    life(4)
    r = REC.status(None, ROOT)
    assert list(r)[:len(CONTRACT)] == list(CONTRACT)
    assert [r[k] for k in ("ok", "command", "name", "status", "phase", "round", "lines", "job")] == [True, "status", None, None, None, None, [], None]
    assert [(i["name"], i["status"], i["phase"], i["round"]) for i in r["ideas"]] == [(NAME, "lead", 2, 4)]
    lines = r["text"].split("\n")
    assert lines[0].startswith("1 idea") and lines[1].startswith(f"{NAME}: LEAD · phase 2 · round 4 of 5 · next: ") and len(lines) == 2
    one = REC.status(NAME, ROOT)
    assert [one[k] for k in ("ok", "command", "name", "status", "phase", "round")] == [True, "status", NAME, "lead", 2, 4]
    assert [x["line"] for x in one["lines"]] == BUILD_LINES and all(set(x) >= {"line", "passed", "number", "need", "text"} for x in one["lines"])
    rec = one["record"]
    assert rec["idea"] == IS.read_idea(NAME, ROOT) and rec["card"] == (ROOT / NAME / "card.md").read_text() and rec["spec"] == read(ROOT / NAME / "spec.json")
    assert rec["log"][0]["event"] == "created" and ("idea", "lead") in [(x.get("was"), x.get("now")) for x in rec["log"]] and rec["job"] is None
    assert [(x["round"], x["bar"], x["reason"], x["store"], x["passed"]) for x in rec["rounds"]] == [
        (1, 0.95, REASONS[1], NAME, life(1)[1]["passed"]), (2, 0.975, REASONS[2], NAME, life(2)[2]["passed"]),
        (3, 0.983, REASONS[3], "bpi_orb_r3", life(3)[3]["passed"]), (4, 0.9875, REASONS[4], "bpi_orb_r3", True)]
    for word in (f"{NAME} · LEAD · phase 2 · round 4 of 5", "CARD", "0.1 ", "ROUNDS", REASONS[2], "random bar 97.5 %", "LATEST VERDICT", "2.9 PASS"):
        assert word in one["text"], word
    assert one["next"] and "\n" not in one["next"]
    # an empty folder, an idea that is not there
    assert REC.status(None, tmp() / "ideas_nowhere")["ideas"] == [] and "No idea" in REC.status(None, tmp() / "ideas_nowhere")["text"]
    refused(lambda: REC.status("bpi_nobody", ROOT), "no idea")
    assert not (tmp() / "ideas_nowhere").exists()


# ================================================================ (f) the commands, as the connector writes them

def test_the_commands_in_this_process():
    root, name = tmp() / "ideas_cmd", "bpi_cmd"
    last = [f"--root={root}", "--json"]
    rc, js = _run(["card", name, "--spec=-", *last], json.dumps(idea(name)))
    d = json.loads(js)
    assert rc == 0 and js.count("\n") == 1 and js.isascii() and list(d)[:len(CONTRACT)] == list(CONTRACT)
    assert (d["command"], d["name"], d["phase"], d["status"]) == ("card", name, 0, "idea")
    assert d["lines"] == plain(REC.card(name, idea(name), root))["lines"] and d["plan"]["home"]["table"] == "NQ-tf15-nyam"
    rc, txt = _run(["card", name, "--spec=-", f"--root={root}"], json.dumps(idea(name)))                      # a person: the text, then the next step
    assert rc == 0 and txt.split("\n")[1].startswith("0.1 PASS ") and txt.rstrip("\n").split("\n")[-1].startswith("NEXT: ")
    path = tmp() / "card_cmd.json"
    path.write_text(json.dumps(idea(name)))
    assert _run(["card", name, f"--spec={path}", *last])[0] == 0                                              # ... or from a file
    # refusals: exit 2, the one object, the missing line named; a person reads every line as pass or fail
    rc, js = _run(["card", name, "--spec=-", *last], json.dumps(idea(name, card={"not_here": ""})))
    d = json.loads(js)
    assert rc == 2 and d["ok"] is False and "0.4" in d["error"] and [x["passed"] for x in d["lines"]] == [True, True, True, False, True, True, True]
    rc, txt = _run(["card", name, "--spec=-", f"--root={root}"], json.dumps(idea(name, card={"not_here": ""})))
    assert rc == 2 and [ln[:8] for ln in txt.split("\n")[1:7]] == ["0.1 PASS", "0.2 PASS", "0.3 PASS", "0.4 FAIL", "0.5 PASS", "0.6 PASS"] and "REFUSED: " in txt
    n = 0
    for argv, stdin, word in ((["card", name, "--spec=-"], "", "stdin"), (["card", name, "--spec=-"], "{not json", "JSON"), (["card", name], "", "--spec"),
                              (["card", name, f"--spec={tmp() / 'no_card.json'}"], "", "no_card.json"), (["card", "--spec=-"], json.dumps(idea(name)), "name"),
                              (["card", "bpi_other", "--spec=-"], json.dumps(idea(name)), "bpi_other"), (["status", "bpi_nobody"], "", "no idea"),
                              (["build", "bpi_nobody", "--reason=x"], "", "no card"), (["build", name], "", "--reason"), (["lock", name], "", "no build on file"),
                              (["test", name, "--confirm"], "", "not frozen"), (["test", name], "", "not frozen")):
        rc, js = _run([*argv, *last], stdin)
        d = json.loads(js)
        assert rc == 2 and list(d) == list(CONTRACT) and d["ok"] is False and word in d["error"] and d["command"] == argv[0], (argv, d)
        n += 1
    # status: every idea, one idea
    rc, js = _run(["status", *last])
    d = json.loads(js)
    assert rc == 0 and d["command"] == "status" and [i["name"] for i in d["ideas"]] == [name] and d["name"] is None
    rc, js = _run(["status", name, *last])
    assert rc == 0 and json.loads(js)["status"] == "idea" and json.loads(js)["record"]["spec"]["name"] == name
    rc, txt = _run(["status", f"--root={root}"])
    assert rc == 0 and txt.split("\n")[1].startswith(f"{name}: IDEA · phase 0 · next: ")
    RESULTS["test_the_commands_in_this_process"] = (6 + n, 6 + n, "answers and refusals")


def test_the_command_lines_of_the_connector():
    """bp.py in its own process, with the connector's exact command lines: the card on stdin, the build as a job, the job
    picked up by its id, the status. The tiny run comes from BP_TEST_RUN in the environment, as it would for the app."""
    if S.compute_window_end() is not None:
        import pytest
        pytest.skip("no heavy run starts 09:18-09:36 ET on weekdays")
    life(1)                                                                      # idea A's stores: this idea has its name and settings, so nothing runs twice
    root, name = tmp() / "ideas_conn", NAME
    last = [f"--root={root}", "--json"]
    env = {REC.TEST_RUN: json.dumps({**TINY, "tester": str(tmp() / "tester_conn")})}
    rc, d = bp(["card", name, "--spec=-", *last], json.dumps(idea(name)))
    assert rc == 0 and list(d)[:len(CONTRACT)] == list(CONTRACT) and (d["ok"], d["command"], d["status"], d["phase"]) == (True, "card", "idea", 0)
    rc, e = bp(["card", name, "--spec=-", *last], json.dumps(idea(name, run={"exits": "extended"})))
    assert rc == 2 and e["ok"] is False and "0.2" in e["error"]
    rc, e = bp(["build", name, "--wait=0", *last], **env)                         # a refusal comes back at once, never as a job
    assert rc == 2 and e["job"] is None and "--reason" in e["error"] and not (root / "_jobs").exists()
    rc, d = bp(["build", name, "--reason=the plain idea, as carded", "--wait=0", *last], **env)
    assert rc == 0 and (d["ok"], d["command"], d["name"], d["phase"], d["round"], d["lines"]) == (True, "build", name, 2, 1, []) and d["job"]["state"] in ("queued", "running")
    jid = d["job"]["id"]
    assert (root / name / "rounds/1/reason.txt").read_text() == "the plain idea, as carded\n"                # saved before the job started
    for _ in range(30):
        rc, d = bp(["job", jid, "--wait=20", *last])
        if d["job"]["state"] not in ("queued", "running"):
            break
    assert rc == 0 and d["job"] == {"id": jid, "state": "done", "progress": d["job"]["progress"]} and d["ok"] and d["command"] == "build" and d["round"] == 1, d
    assert [x["line"] for x in d["lines"]] == BUILD_LINES and d["status"] == IS.status(name, root) and d["dry_run"] is False
    assert all(s["skipped"] for s in d["stores"]) and (root / name / "rounds/1/build.json").is_file()
    assert (root / name / "rounds/1/reason.txt").read_text() == "the plain idea, as carded\n" and IS.rounds(name, root) == [1]
    assert by(d)["2.3"]["controls"]["c1"]["replicates"] == 200                   # (the draws of the test run)
    rc, s = bp(["status", *last])
    assert rc == 0 and [(i["name"], i["status"], i["round"]) for i in s["ideas"]] == [(name, d["status"], 1)]
    rc, s = bp(["status", name, *last])
    assert rc == 0 and s["status"] == d["status"] and s["round"] == 1 and [x["line"] for x in s["lines"]] == BUILD_LINES
    # a second round inside its wait: done at once (everything is stored), the bar of round 2
    rc, d2 = bp(["build", name, "--reason=the same idea, read again", "--wait=300", *last], **env)
    assert rc == 0 and d2["job"]["state"] == "done" and d2["round"] == 2 and d2["bar"] == 0.975 and IS.rounds(name, root) == [1, 2]
    RESULTS["test_the_command_lines_of_the_connector"] = (2, 2, "rounds through the front door, one as a job")


CONNECTOR = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
from homebase.claude_mcp import tools
from homebase.claude_mcp.client import Client, ToolError
box = tools.Toolbox(Client("http://127.0.0.1:1"), sleep=lambda s: None)
out = []
for tool, args in json.loads(sys.argv[2]):
    try:
        out.append(box.call(tool, args))
    except ToolError as e:
        out.append("ToolError: " + str(e))
print(json.dumps(out))
'''


def test_the_apps_connector_against_this_toolkit():
    """The other side of the contract: homebase/claude_mcp/blueprint_tools.py (the app's Python) starts THIS bp.py with the
    engine's Python. The same tiny run through BP_TEST_RUN; the idea folder, the Lab and the tester's runs are temp folders."""
    if not APP_PYTHON.exists():
        import pytest
        pytest.skip(f"the app's Python is not there: {APP_PYTHON}")
    if S.compute_window_end() is not None:
        import pytest
        pytest.skip("no heavy run starts 09:18-09:36 ET on weekdays")
    life(1)
    root, name = tmp() / "ideas_app", NAME
    calls = [("blueprint_card", {"name": name, "card": CARD, "settings": SETTINGS}), ("blueprint_card", {"name": name, "card": {**CARD, "not_here": ""}, "settings": SETTINGS}),
             ("blueprint_build", {"name": name, "reason": "the plain idea, as carded", "wait_s": 600}), ("blueprint_status", {}), ("blueprint_status", {"name": name}),
             ("blueprint_build", {"name": "bpi_nobody", "reason": "x"})]
    env = {**os.environ, "HOMEBASE_IDEAS_ROOT": str(root), "HOMEBASE_DRAFTS_DIR": str(tmp() / "drafts_app"), "HOMEBASE_BP": str(W / "bp.py"),
           "HOMEBASE_BP_PYTHON": sys.executable, REC.TEST_RUN: json.dumps({**TINY, "tester": str(tmp() / "tester_app")})}
    q = subprocess.run([str(APP_PYTHON), "-B", "-c", CONNECTOR, str(S.REPO), json.dumps(calls)], capture_output=True, text=True, timeout=900, cwd=str(tmp()), env=env)
    assert q.returncode == 0, q.stderr[-2000:]
    card, bad, build, every, one, nobody = json.loads(q.stdout)
    _T["connector"] = {"blueprint_card": card, "blueprint_build": build, "blueprint_status": every, "blueprint_status(name)": one}
    assert card.split("\n")[0] == f"Blueprint card · {name} · IDEA · phase 0" and "0.6 PASS" in card and "0.7 PASS" in card and "Lines: 7 passed · 0 FAILED" in card
    assert "Lab: draft_bpi_orb is filed under Ideas." in card.split("\n") and card.count("Next: ") == 1 and "Saved: " in card
    assert bad.startswith("ToolError: Refused (blueprint card): ") and "0.4" in bad and "Nothing was run." in bad
    status = IS.status(name, root)
    assert build.split("\n")[0] == f"Blueprint build · {name} · {status.upper()} · phase 2 · round 1" and "2.9 PASS round 1 of at most 5" in build
    assert all(build.count(f"\n2.{i} ") == 1 for i in range(1, 10)) and "Lines: " in build and build.count("Next: ") == 1 and "Lab: the saved results read" not in build
    assert every.split("\n")[0] == "Blueprint status" and f"{name}: {status.upper()} · phase 2 · round 1 of 5" in every
    assert one.split("\n")[0] == f"Blueprint status · {name} · {status.upper()} · phase 2 · round 1" and "ROUNDS" in one and "the plain idea, as carded" in one
    assert nobody.startswith("ToolError: Refused (blueprint build): ") and "no card" in nobody
    assert (root / name / "rounds/1/build.json").is_file() and (tmp() / "drafts_app" / f"{name}.py").is_file()
    assert read(tmp() / "drafts_app" / "groups.json")["members"] == {f"draft_{name}": IS.group_for(status)}


# ================================================================ nothing outside the temp folder

def test_nothing_was_written_outside_the_temp_folder():
    assert _listing(HOME / "ideas") == BEFORE["ideas"] and _listing(HOME / "strategies") == BEFORE["drafts"], "a test wrote into ~/.homebase"
    assert _listing(tmp() / "ideas_env") is None                                 # the environment's idea folder was never needed
    assert not [k for k in (_listing(RUN.RUNS) or []) if k.startswith("bpi_")], "a test wrote into runs_bp/"
    assert not [r["key"] for r in LB.read_ledger() if r["key"].startswith("bpi_")], "a test wrote into ledger.csv"
    assert not [k for k in (_listing(APP_RUNS) or []) if "draft_bpi_" in k], "a test wrote into the app's tester runs"
    assert [p.exists() for p in PYC] == BEFORE["pyc"], "bytecode was written into homebase/"
    assert not [p for d in ("", "backtest", "claude_mcp") for p in (S.REPO / "homebase" / d / "__pycache__").glob("*.cpython-39.pyc")], "bytecode was written into homebase/"


if __name__ == "__main__":
    import time
    rc = 0
    for name, t in [(k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)]:
        t0 = time.monotonic()
        setup_function()
        try:
            t()
            ok, n, note = RESULTS.get(name, ("", "", ""))
            print(f"PASS {name}" + (f": {ok} of {n}" if n else "") + (f" -- {note}" if note else "") + f" ({time.monotonic() - t0:.0f} s)", flush=True)
        except AssertionError as e:
            rc = 1
            print(f"FAIL {name} ({time.monotonic() - t0:.0f} s)\n{e}", flush=True)
        except BaseException as e:                          # pytest.skip
            if type(e).__name__ != "Skipped":
                raise
            print(f"SKIP {name} ({e})", flush=True)
        finally:
            teardown_function()
    for tool, text in (_T.get("connector") or {}).items():
        print(f"\n--- {tool} ---\n{text}", flush=True)
    sys.exit(rc)


def test_a_choice_setting_written_as_a_number_is_the_same_choice():
    """A chat sends ib_min as 5, the engine names the choice "5": the card reads them as one (0.2 and 0.5 pass)."""
    from blueprint import records as REC
    spec = {"name": "bpi_numbers", "version": 1,
            "card": {"why": "A break of the opening range shows which side holds the larger orders.", "loser": "Traders who fade the first break.",
                     "home": {"market": "NQ", "session": "nyam", "bar": "15"}, "neighbors": ["5-minute bars"], "not_here": "the afternoon session (pm)",
                     "main_setting": "ib_min", "sides": "both", "sides_why": "A range can break either way.", "loses_when": "a week without a clear direction"},
            "run": {"family": "ib_n", "params": {"ib_min": [5, 15, 30, 60]}, "fixed": {"mode": "break"}, "filters": [], "exits": "standard", "limits": {}}}
    rows, plan = REC.card_lines(spec)
    assert all(r["passed"] for r in rows), [r["text"] for r in rows if not r["passed"]]
    assert plan and spec["run"]["params"]["ib_min"] == ["5", "15", "30", "60"]
