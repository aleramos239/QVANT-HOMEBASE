"""LOCK of the pipeline's stages 5 to 7 (blueprint/pipe_stages.py) -- pipeline plan A, task 7.

5. ONE BOX, LOCKED. What the stage DECIDES, with the toolkit's commands answering canned (api.code_check, records.build,
   freeze.lock, pipe_prop.odds: their own test files lock them): the code check is asked on the heat map's OWN home store
   (after a low pass the store with the indicator on); a false line of it is a code problem; a False 2.5 after a low pass
   stops the idea and is NO code problem; any other False line of the build is one, with the toolkit's row and the
   pipeline's own in the text; a box row that fails = passed False with all six rows; no box that made money both ways;
   a refusal of the lock that is not the box's goes up; a locked idea = rows 3.3-3.8 + P5.9 + "locked". Every command
   gets the pipeline's folders (never the repo's), the toolkit's test switch for a tiny run and NO switch without one,
   and no Lab draft is filed while a stage runs.
   And ONCE FOR REAL, tiny (3 named build days, 2 exit cells, 1 worker; the days of tests/test_blueprint_ideas.py), with
   the gates of stages 1-4 patched: a strict pass and a low pass go through the real code check, the real build and the
   real lock under BP_TEST_RUN -- no box, a box that fails, locked, and the same stage run again.
6. THE ONE READ, canned (oos.test; its own tests lock it): pass / fail, the label of the three accounts on a pass, the
   folders, the switch; a refusal goes up; the verdict on file for THIS lock is read instead of a second read.
7. THE BOOK CARD on a HAND-MADE idea that is locked and tested without the engine (tests/blueprint_synth.py: six trades
   typed here, dated on test days, in the library's own store format): every fact with numbers done in the head, the
   three accounts with the unconfirmed one marked, then the runner's step and the owner's approve.

WHAT THE TINY REAL RUN PATCHES, and nothing else: line 1.5 of the code check (10 trades of one box cannot be looked at on 3
days: checks.chart says what `looked` says), the build's lines (records.LINES forced to pass: 3 days prove no edge),
`box: "said"` in the tiny run's settings (lines 3.3-3.8 are read, not enforced), and the gates of stages 1-4.
EVERYTHING IS IN TEMP FOLDERS of this file's own (the pipeline roots, the pools folder pipe_store links from, the Lab
drafts of test_blueprint_ideas' environment): the tests of stages 0-4 share nothing with it and hold in any order. No day
from 2025-07-01 on is opened: the read of the unseen days is never run here (the end-to-end test does that).

  pytest tests/test_pipe_finish.py -q          python tests/test_pipe_finish.py     the same, one line per test
"""
from __future__ import annotations

import contextlib
import copy
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import blueprint_synth as SY  # noqa: E402
import judge as J  # noqa: E402
import library as LB  # noqa: E402
import run_menus as RM  # noqa: E402
import test_blueprint_ideas as TI  # noqa: E402
import test_pipe_stages as TS  # noqa: E402
from blueprint import api  # noqa: E402
from blueprint import checks as CH  # noqa: E402
from blueprint import freeze as FRZ  # noqa: E402
from blueprint import lines as L  # noqa: E402
from blueprint import oos as OOS  # noqa: E402
from blueprint import pipe_card as PC  # noqa: E402
from blueprint import pipe_prop as PP  # noqa: E402
from blueprint import pipe_rules as PR  # noqa: E402
from blueprint import pipe_runner as RN  # noqa: E402
from blueprint import pipe_stages as ST  # noqa: E402
from blueprint import pipe_store as PS  # noqa: E402
from blueprint import propodds as PO  # noqa: E402
from blueprint import records as REC  # noqa: E402
from blueprint import runner as RUN  # noqa: E402
from blueprint import tables as T  # noqa: E402

_T: dict = {"keep": tempfile.TemporaryDirectory(prefix="pipe_finish_")}
D = Path(_T["keep"].name).resolve()
ROOT, POOLS, ROOT7 = D / "pipe", D / "pools", D / "pipe7"
TINY = {"days": TI.DAYS, "cells": TI.CELLS, "workers": 1, "draws": 200}
CTX = {"root": ROOT, "tiny": TINY}
SAID = {"root": ROOT, "tiny": {**TINY, "box": "said", "build_avg_trade": 100.0}}      # the lock's lines 3.3-3.8 are read, not enforced, on 3 days
FULL = {"root": ROOT, "tiny": None}                 # no tiny run: only where the toolkit answers canned
IS = api.ideastore()
DRAFTS = IS.draftstore.ENV
OWN, ACCOUNTS = PR.need("prop", "account"), PR.need("prop", "book_accounts")
FLEX, APEX = "lucid-flex-50k@2026-09-27", "apex-legacy-300k@2026-09-28"
BOXL = [f"3.{i}" for i in range(3, 9)]              # lines 3.3 .. 3.8
C, S, LW = "pfc_orb", "pfs_orb", "pfl_orb"          # three cards: the toolkit answers canned · a tiny real strict pass · a tiny real low pass
HASH = "0123456789abcdef"
_DONE: dict = {}


@pytest.fixture(autouse=True)
def world(monkeypatch):
    """Temp folders for all the toolkit writes, an empty pools folder to link from, a Saturday, the workers asked for."""
    TI.setup_function()
    POOLS.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(PS, "pools", lambda: POOLS)
    monkeypatch.setattr(RUN, "clock", lambda: TI.SAT)
    monkeypatch.setattr(RM, "auto_workers", lambda n=None: n)
    yield monkeypatch
    TI.teardown_function()


# ---------------------------------------------------------------- the runner's part, played by the tests

def add(name: str, max_tr: int) -> str:
    """The orb card of test_pipe_stages under another name and with its most entries a session stated (another card: another signature)."""
    if name not in _DONE:
        card = {**copy.deepcopy(TS.CARD), "name": name, "ways": [{**TS.CARD["ways"][0], "limits": {"max_tr": max_tr}}]}
        PS.add(card, PC.check(card)[1], ROOT, sig=PC.signature(card), family=PC.family_of(card))
        _DONE[name] = True
    return name


def ran(name: str, n: int, card: dict, root=ROOT) -> dict:
    PS.write_stage(name, n, card, root)
    return card


def hand(n: int, picked, tries: int, rows=(), **more) -> dict:
    """A stage card written by hand, as a stage that passed leaves it."""
    return {"stage": n, "name": ST.NAMES[n], "passed": True, "result": "pass", "lines": list(rows), "text": f"stage {n}, written by a test", "picked": picked,
            "tries": tries, "rules": {"by": "hand"}, "utc": "2026-10-07T00:00:00+00:00", "seconds": 0.0, **more}


def upto4(mp, name: str, max_tr: int, result: str) -> dict:
    """Stages 0 to 4 of a card, for real on the tiny days with their gates patched -> the card of stage 4."""
    add(name, max_tr)
    ran(name, 0, ST.stage0(name, CTX))
    TS.raw(mp, b1=("fail", None), b5=(result, 40.0))
    ran(name, 1, ST.stage1(name, CTX))
    TS.gate(mp, "strict_extra")
    TS.gate(mp, "indicator")
    ran(name, 3, ST.stage3(name, CTX))
    TS.gate(mp, "reshuffle")
    TS.gate(mp, "random")
    return ran(name, 4, ST.stage4(name, CTX))


def base(mp, low: bool = False) -> dict:
    """The card the canned tests work on: stage 1 for real (once: its home store is there), stages 3 and 4 by hand -- after a
    strict pass, or after a low pass that moved on with the card's indicator (its heat map carded as stage 3 cards it)."""
    add(C, 4)
    ran(C, 0, ST.stage0(C, CTX))
    TS.raw(mp, b1=("fail", None), b5=("low" if low else "strict", 40.0))
    one = ran(C, 1, ST.stage1(C, CTX))
    picked, tries, rows = one["picked"], 2, [{"line": k, "passed": True, "number": 5.0, "need": 0, "text": f"{k} PASS by hand"} for k in ("P3.4", "P3.6")]
    if low:
        kw = ST._kw(C, CTX)
        spec, _, _ = ST._idea(f"{C}_a5", kw)
        assert REC.card(f"{C}_a5f1", {**copy.deepcopy(spec), "name": f"{C}_a5f1", "run": {**spec["run"], "filters": [{"block": "trend", "side": "with"}]}}, kw["root"])["ok"]
        picked, tries = {**picked, "sub": f"{C}_a5f1", "filter": "trend_with"}, 3
        rows = [{"line": f"P3.{i}", "passed": True, "number": 80.0, "need": 70, "text": f"trend with: P3.{i} PASS by hand", "sub": f"{C}_a5f1", "indicator": "trend_with"}
                for i in range(1, 7)]
    ran(C, 3, hand(3, picked, tries, rows))
    return ran(C, 4, hand(4, picked, tries, [{"line": f"P4.{i}", "passed": True, "number": 0.99, "need": 0.95, "text": f"P4.{i} PASS by hand"} for i in (1, 2)]))


def env() -> dict:
    """What a toolkit call finds in the environment: the test switch (read) and the Lab's drafts folder."""
    raw = os.environ.get(REC.TEST_RUN)
    return {"switch": json.loads(raw) if raw else None, "drafts": os.environ.get(DRAFTS)}


@contextlib.contextmanager
def environ(**put):
    """The environment with `put` over it while the block runs (None = not there), and as it was afterwards."""
    keep = {k: os.environ.get(k) for k in put}
    try:
        for k, v in put.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        yield
    finally:
        for k, v in keep.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def row(line: str, passed) -> dict:
    return {"line": line, "passed": passed, "number": 1.0, "need": 0.5, "text": f"{line} {'n/a ' if passed is None else 'PASS' if passed else 'FAIL'} canned"}


def odds_fake(calls: list):
    def odds(x, calendar, account=None, paths=None, seed=None):
        calls.append({"trades": len(x["net"]), "calendar": list(calendar), "account": account, "env": env()})
        return {"account": {"id": account, "name": f"the account {account}", "confirmed": account != APEX}, "days": 30, "size": 5, "payout_size": 3, "eval": 0.6,
                "payout": 0.7, "label": PP.ALONE, "need": {"eval": 0.5, "payout": 0.5}, "table": [], "text": f"PROP CHECK canned on {account} -- STANDS ALONE."}
    return odds


def fakes(mp, check=(), build=(), lock=None) -> dict:
    """The toolkit's commands of stage 5 answer canned -> every call, with what it was handed and the environment it saw.
    check / build = the lines that are False; lock = the lock's result, or the refusal it raises."""
    calls: dict = {k: [] for k in ("check", "build", "lock", "odds")}
    off, failed = tuple(check), tuple(build)

    def code_check(name, **k):
        calls["check"].append({"name": name, **k, "env": env()})
        return {"ok": True, "lines": [row(f"1.{i}", None if i == 6 else f"1.{i}" not in off) for i in range(1, 7)], "saved": [f"{name}/check.json"]}

    def build(name, reason, **k):
        calls["build"].append({"name": name, "reason": reason, **k, "env": env()})
        return {"ok": True, "lines": [row(f"2.{i}", None if i == 7 and "2.7" not in failed else f"2.{i}" not in failed) for i in range(1, 10)], "passed": not failed}

    def lock_(name, **k):
        calls["lock"].append({"name": name, **k, "env": env()})
        if isinstance(lock, Exception):
            raise lock
        return lock

    mp.setattr(api, "code_check", code_check)
    mp.setattr(REC, "build", build)
    mp.setattr(FRZ, "lock", lock_)
    mp.setattr(PP, "odds", odds_fake(calls["odds"]))
    return calls


def lines(card: dict) -> list:
    return [x["line"] for x in card["lines"]]


def chart(mp) -> None:
    """Line 1.5 says what `looked` says: 10 trades of one box cannot be looked at on 3 days (the ONE piece of the code check a tiny run patches)."""
    real = CH.chart
    mp.setattr(CH, "chart", lambda t, looked=False, cell=None: {**real(t, looked, cell), "passed": bool(looked)})


def no_repo_write(name: str) -> None:
    """Nothing of an idea is in the repo's own stores folders or ledger, and none of its heat maps is a Lab draft."""
    assert not [p.name for d in (RUN.RUNS, RUN.TESTS) if d.exists() for p in d.iterdir() if p.name.startswith(name)]
    assert not [r["key"] for r in LB.read_ledger() if r["key"].startswith(name)]
    assert not [p.name for p in Path(TI.ENV[DRAFTS]).glob(f"*{name}*")] and not (TI.HOME / "pipeline" / "p" / name).exists()


# ================================================================ what every stage and every command gets

def test_the_stage_map_names_eight_stages_and_the_runner_loads_them():
    assert set(ST.STAGES) == set(range(8)) == set(ST.NAMES) and [ST.NAMES[n] for n in range(8)] == list(RN.NAMES)
    assert all(RN.stage_fn(n) is ST.STAGES[n] and ST.STAGES[n].__name__ == f"stage{n}" for n in range(8)) and RN.LAST == max(ST.STAGES)


def test_no_lab_draft_while_a_stage_runs_and_the_environment_is_put_back(world):
    add(C, 4)
    seen, real = [], REC.card
    assert os.environ[DRAFTS] == TI.ENV[DRAFTS]                                                # the Lab's drafts folder is in the environment (a temp one)
    world.setattr(REC, "card", lambda *a, **k: seen.append(env()) or real(*a, **k))
    assert ST.stage0(C, CTX)["passed"] is True and seen and all(e == {"switch": None, "drafts": None} for e in seen)
    assert os.environ[DRAFTS] == TI.ENV[DRAFTS]                                                # ... and back when the stage returns
    world.setattr(REC, "card", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("planted")))
    with pytest.raises(RuntimeError):
        ST.stage0(C, CTX)
    assert os.environ[DRAFTS] == TI.ENV[DRAFTS]                                                # ... and when it raises
    world.setattr(REC, "card", real)
    with environ(**{DRAFTS: None}):
        assert ST.stage0(C, CTX)["passed"] is True and DRAFTS not in os.environ                # a variable that was not there stays away
    no_repo_write(C)


def test_every_store_states_its_most_entries_a_session_so_line_1_3_is_read_at_every_lock():
    """The lock asks lines 1.1-1.5 TRUE. 1.3 is read off each cell's own `max_tr`: every entry trigger has one (the engine's
    bar template's, or its own), a card's `limits` only changes it -- so no card has to name it for the lock."""
    fam = RUN._blocks().WRAPPED
    assert len(fam) >= 20 and not [k for k, c in fam.items() if not (isinstance(c.defaults().get("max_tr"), int) and c.defaults()["max_tr"] >= 1)]


# ================================================================ stage 5: what it decides (the toolkit answers canned)

def test_stage_5_asks_the_code_check_on_the_heat_maps_own_home_store_and_a_false_line_is_a_code_problem(world):
    four = base(world)
    calls = fakes(world, check=("1.2",))
    c = TS.whole(ST.stage5(C, CTX), 5)
    assert (c["passed"], c["result"], c["picked"], c["tries"]) == (False, "fail", four["picked"], 2) and c["code_problem"] is True
    assert lines(c) == ["1.1", "1.2", "1.3", "1.4"] and c["text"].startswith(f"CODE PROBLEM ({C}_a5, its home store {C}_a5-NQ-tf5): 1.2 FAIL")
    assert calls["build"] == [] and calls["lock"] == [] and c["check"] == [f"{C}_a5/check.json"]
    (k,) = calls["check"]
    assert (k["name"], k["store"], k["looked"], k["root"], k["out"]) == (f"{C}_a5", f"{C}_a5-NQ-tf5", True, ROOT / "ideas", ROOT / "runs")
    four = base(world, low=True)                                                               # after a low pass: the store WITH the indicator on
    calls = fakes(world, check=("1.4",))
    c = ST.stage5(C, CTX)
    assert calls["check"][0]["name"] == f"{C}_a5f1" and calls["check"][0]["store"] == f"{C}_a5f1__trend_with-NQ-tf5"
    assert c["code_problem"] is True and c["picked"] == four["picked"] and c["tries"] == 3 and "1.4 FAIL" in c["text"]


def test_stage_5_a_false_2_5_after_a_low_pass_stops_the_idea_and_is_no_code_problem(world):
    base(world, low=True)
    calls = fakes(world, build=("2.5",))
    c = TS.whole(ST.stage5(C, CTX), 5)
    assert (c["passed"], c["result"]) == (False, "other markets") and "code_problem" not in c and calls["lock"] == []
    assert lines(c) == [f"2.{i}" for i in range(1, 10)] and [x["line"] for x in c["lines"] if x["passed"] is False] == ["2.5"]
    assert f"{C}_a5f1 with trend with does not hold on its other markets" in c["text"] and "2.5 FAIL canned" in c["text"]
    assert c["rules"]["lines"]["2.5"] == 0.5 and c["rules"]["prop"] == PR.need("prop")
    base(world)                                                                                # after a STRICT pass stage 3 read the other markets: the two disagree
    fakes(world, build=("2.5",))
    c = ST.stage5(C, CTX)
    assert (c["passed"], c["result"]) == (False, "fail") and c["code_problem"] is True
    assert "fails 2.5 where the pipeline's gates passed (the toolkit: 2.5 FAIL canned -- the pipeline: P3.6 PASS by hand)" in c["text"]


def test_stage_5_any_other_false_line_of_the_build_is_a_code_problem_with_both_rows_in_its_text(world):
    base(world)
    mine = next(x for x in PS.stages(C, ROOT)[1]["lines"] if x["line"] == "P1.2" and x["sub"] == f"{C}_a5")       # the pipeline's own reading of the average trade
    calls = fakes(world, build=("2.2",))
    c = TS.whole(ST.stage5(C, CTX), 5)
    assert (c["passed"], c["result"]) == (False, "fail") and c["code_problem"] is True and calls["lock"] == []
    assert c["text"].startswith(f"CODE PROBLEM: the toolkit's build of {C}_a5 fails 2.2 where the pipeline's gates passed")
    assert f"the toolkit: 2.2 FAIL canned -- the pipeline: {mine['text']}" in c["text"] and mine["text"].startswith(f"{C}_a5: P1.2 ")
    base(world, low=True)                                                                      # with an indicator: the gates of stage 3, and 2.5 beside another line
    fakes(world, build=("2.5", "2.7", "2.9"))
    c = ST.stage5(C, CTX)
    assert c["code_problem"] is True and "fails 2.7, 2.9 where" in c["text"] and "the toolkit: 2.7 FAIL canned -- the pipeline: trend with: P3.5 PASS by hand" in c["text"]
    assert "the toolkit: 2.9 FAIL canned -- the pipeline: no gate of its own reads this line" in c["text"]
    assert [x["line"] for x in c["lines"] if x["passed"] is False] == ["2.5", "2.7", "2.9"]


def test_stage_5_the_locks_refusal_is_the_verdict_when_it_is_the_boxs(world):
    four = base(world)
    calls = fakes(world, lock=J.Refuse("the default variant does not meet every line read on it before the freeze"))
    six = [row(k, k != "3.4") for k in BOXL]
    world.setattr(ST, "_box", lambda u, kw: ("or_min15_atr3-r1", six))
    c = TS.whole(ST.stage5(C, CTX), 5)
    assert (c["passed"], c["result"], c["default"]) == (False, "box failed", "or_min15_atr3-r1") and "code_problem" not in c and "locked" not in c
    assert lines(c) == BOXL and [x["line"] for x in c["lines"] if not x["passed"]] == ["3.4"]      # ALL six rows, the failed one among them
    assert "the middle box or_min15_atr3-r1" in c["text"] and "does not meet 3.4: 3.4 FAIL canned" in c["text"] and "no second box" in c["text"]
    assert len(calls["lock"]) == 1 and calls["odds"] == [] and c["picked"] == four["picked"]
    world.setattr(ST, "_box", lambda u, kw: (None, []))                                        # no box makes money with normal AND with worse fills
    c = TS.whole(ST.stage5(C, CTX), 5)
    assert (c["passed"], c["result"], c["lines"]) == (False, "no box", []) and "there is no middle box to lock" in c["text"] and "code_problem" not in c
    for got in ((("or_min15_atr3-r1", [row(k, True) for k in BOXL])), None):                   # the box holds / the lock never reached it: not the box's refusal
        world.setattr(ST, "_box", lambda u, kw, got=got: got)
        TS.refused(lambda: ST.stage5(C, CTX), "does not meet every line")


def test_stage_5_a_refusal_of_the_lock_that_is_not_the_boxs_goes_up_to_the_runner(world):
    base(world)
    calls = fakes(world, lock=J.Refuse("a job of the idea is still running"))
    assert ST._box(T.bp_unit({"name": f"{C}_a5", "family": "orb"}, "NQ", "5", "nyam"), ST._kw(C, CTX)) is None      # no worse-fills table: the lock read no box
    TS.refused(lambda: ST.stage5(C, CTX), "a job of the idea is still running")
    assert len(calls["lock"]) == 1 and calls["odds"] == []


def test_stage_5_a_locked_idea_is_six_rows_the_prop_label_and_what_was_locked(world):
    four = base(world)
    home = f"{C}_a5-NQ-tf5"
    st = J.store({"dir": ROOT / "runs", "key": home})
    cell = sorted(st["_idx"])[0]
    lock = {"home": {"folder": str(ROOT / "runs"), "key": home, "session": "nyam", "market": "NQ", "bar": "5"}, "default": cell, "survivors": [cell, "another"],
            "hash": HASH, "box": [row(k, True) for k in BOXL]}
    calls = fakes(world, lock={"ok": True, "lock": lock, "lines": [row("3.1", True), row("3.2", True), *lock["box"]]})
    c = TS.whole(ST.stage5(C, CTX), 5)
    assert (c["passed"], c["result"], c["picked"], c["tries"]) == (True, "locked", four["picked"], 2) and "code_problem" not in c
    assert lines(c) == [*BOXL, "P5.9"] and [x["passed"] for x in c["lines"]] == [True] * 6 + [None]
    p = c["lines"][-1]
    assert (p["label"], p["account"], p["eval"], p["payout"], p["size"], p["payout_size"]) == (PP.ALONE, OWN, 0.6, 0.7, 5, 3)
    assert p["text"] == f"P5.9 n/a  PROP CHECK canned on {OWN} -- STANDS ALONE." and p["need"] == {"days": 30, "eval": 0.5, "payout": 0.5}
    assert c["locked"] == {"default": cell, "lock": HASH, "prop": {OWN: {"name": f"the account {OWN}", "confirmed": True, "size": 5, "payout_size": 3, "eval": 0.6,
                                                                         "payout": 0.7, "label": PP.ALONE, "text": f"PROP CHECK canned on {OWN} -- STANDS ALONE."}}}
    assert f"the middle box {cell} (of 2 that make money" in c["text"] and f"lock {HASH}" in c["text"] and "STANDS ALONE" in c["text"]
    assert c["rules"]["lines"] == {k: 0.5 for k in BOXL} and c["rules"]["checked"] == ["1.1", "1.2", "1.3", "1.4"]
    (o,) = calls["odds"]                                                                       # the default box's BUILD trades on the build days, the pipeline's account
    assert (o["trades"], o["calendar"], o["account"]) == (len(J.cellx(st, cell, "nyam")["net"]), TI.DAYS, OWN)
    # every command got the pipeline's folders, the idea's own ledger and the tiny run's days -- never the repo's
    want = {"root": ROOT / "ideas", "out": ROOT / "runs", "ledger": ROOT / "p" / C / "ledger.csv", "workers": 1, "days": TI.DAYS, "cells": TI.CELLS}
    (b,), (k,) = calls["build"], calls["lock"]
    assert {x: b[x] for x in want} == want == {x: k[x] for x in want} and (b["name"], b["reason"], k["name"]) == (f"{C}_a5", ST.REASON, f"{C}_a5")
    # ... inside the toolkit's own test switch (a run on named days saves nothing without it), and with no Lab drafts folder
    switch = {**TINY, "out": str(ROOT / "runs"), "ledger": str(ROOT / "p" / C / "ledger.csv"), "test_out": str(ROOT / "runs_test")}
    assert all(x["env"] == {"switch": switch, "drafts": None} for x in (calls["check"][0], b, k))
    assert env() == {"switch": None, "drafts": TI.ENV[DRAFTS]} and RUN.RUNS not in (b["out"], k["out"])


def test_stage_5_without_a_tiny_run_the_test_switch_is_absent_whatever_the_environment_held(world):
    base(world)
    calls = fakes(world, build=("2.2",))
    with environ(**{REC.TEST_RUN: json.dumps({"days": ["2022-03-15"], "out": "/nowhere"})}):   # a switch left in the runner's environment
        c = ST.stage5(C, FULL)
        assert env() == {"switch": {"days": ["2022-03-15"], "out": "/nowhere"}, "drafts": TI.ENV[DRAFTS]}       # ... is put back as it was
        assert REC._test_run(ROOT / "ideas") == {"days": ["2022-03-15"], "out": "/nowhere"} and not REC._own(PS.ideas_root(ROOT))
    assert c["code_problem"] is True and all(x["env"] == {"switch": None, "drafts": None} for x in (*calls["check"], *calls["build"]))
    (b,) = calls["build"]
    assert (b["days"], b["cells"], b["workers"]) == (None, None, None) and (b["out"], b["ledger"]) == (ROOT / "runs", ROOT / "p" / C / "ledger.csv")
    assert ST._cmd(ST._kw(C, SAID)) == {"root": ROOT / "ideas", "out": ROOT / "runs", "ledger": ROOT / "p" / C / "ledger.csv", "workers": 1, "days": TI.DAYS,
                                         "cells": TI.CELLS}
    with ST._switch(C, {"root": ROOT, "tiny": {**SAID["tiny"], "test_days": ["2025-07-08"], "tester": "/never"}}):      # what a tiny run may hand over: no tester
        assert env()["switch"] == {**SAID["tiny"], "test_days": ["2025-07-08"], "out": str(ROOT / "runs"), "ledger": str(ROOT / "p" / C / "ledger.csv"),
                                   "test_out": str(ROOT / "runs_test")}
    assert env() == {"switch": None, "drafts": TI.ENV[DRAFTS]}


def test_stage_5_runs_in_its_order_and_reads_the_build_on_file(world):
    base(world)
    name = add("pfn_orb", 5)                                                                   # a card whose stage 4 never ran
    TS.refused(lambda: ST.stage5(name, CTX), "stage 4 (proof) has no passed card on file")
    assert ST._built(f"{C}_a5", ST._kw(C, CTX)) is None                                        # no round on file: stage 5 builds one


# ================================================================ stage 5, once for real (tiny)

def test_a_tiny_real_stage_5_after_a_strict_pass_no_box_a_failed_box_locked_and_again(world):
    four = upto4(world, S, 2, "strict")
    chart(world)
    sub, home, kw = f"{S}_a5", f"{S}_a5-NQ-tf5", ST._kw(S, CTX)
    d, worse = ROOT / "ideas" / sub, ROOT / "runs" / f"{home}-nyam-worse"
    assert four["picked"]["sub"] == sub and not worse.exists()
    # (1) no box makes money with normal AND with worse fills: the lock's own refusal, read as the verdict
    middle = REC.middle
    world.setattr(REC, "middle", lambda rows, ids, worse=None: middle(rows, ids) if worse is None else (None, []))
    with TI.passing():
        c = TS.whole(ST.stage5(S, CTX), 5)
    assert (c["passed"], c["result"], c["lines"]) == (False, "no box", []) and "code_problem" not in c and not (d / "lock.json").exists()
    assert (worse / "run.json").is_file() and TI.read(worse / "run.json")["stage"] == RUN.WORSE     # the worse-fills table: in the pipeline's stores folder
    chk, b = TI.read(d / "check.json"), TI.read(d / "rounds" / "1" / "build.json")
    assert [x["passed"] for x in chk["lines"]][:5] == [True] * 5 and Path(chk["source"]["where"]).resolve() == (ROOT / "runs" / home).resolve()
    assert "the stated maximum of 2 a session and day" in chk["lines"][2]["text"]              # the card's limits.max_tr reached the store: line 1.3 reads it
    assert (b["reason"], b["counted"], b["test_run"], b["home_store"], b["round"]) == (ST.REASON, True, True, home, 1) and b["failed"] == []
    world.setattr(REC, "middle", middle)
    world.setattr(REC, "build", lambda *a, **k: (_ for _ in ()).throw(AssertionError("a second round was built")))     # from here on: the build on file
    # (2) the middle box fails a line: refused by the real lock, all six rows on the card
    ratio, box = L.box_ratio, L.BOX
    world.setattr(L, "BOX", tuple((lambda bx: {**ratio(bx), "passed": False}) if f is ratio else f for f in box))
    with TI.no_engine():
        c = TS.whole(ST.stage5(S, CTX), 5)
    assert (c["passed"], c["result"]) == (False, "box failed") and lines(c) == BOXL and "3.4" in [x["line"] for x in c["lines"] if not x["passed"]]
    assert "no second box" in c["text"] and "code_problem" not in c and not (d / "lock.json").exists() and all(x["number"] is not None for x in c["lines"])
    world.setattr(L, "BOX", box)
    # (3) locked (the tiny run's `box: "said"`: 3 days cannot hold lines 3.3-3.8)
    c = TS.whole(ST.stage5(S, SAID), 5)
    lock = TI.read(d / "lock.json")
    assert (c["passed"], c["result"], c["picked"], c["tries"]) == (True, "locked", four["picked"], 2) and lines(c) == [*BOXL, "P5.9"]
    assert c["locked"]["default"] == lock["default"] and lock["default"] in lock["survivors"]
    assert c["locked"]["lock"] == lock["hash"] and list(c["locked"]["prop"]) == [OWN] and c["locked"]["prop"][OWN]["label"] in (PP.ALONE, PP.HELPER)
    assert c["lines"][-1]["passed"] is None and c["lines"][-1]["label"] == c["locked"]["prop"][OWN]["label"] and "PROP CHECK on " in c["lines"][-1]["text"]
    h = lock["home"]
    assert (h["folder"], h["key"], h["worse"], h["filter"]) == (str(ROOT / "runs"), home, worse.name, None) and lock["round"] == 1
    assert {v["folder"] for v in lock["stores"].values()} == {str(ROOT / "runs")} and set(lock["stores"]) == {home, worse.name, "c1-NQ-tf5"}
    assert [x["number"] for x in lock["box"]] == [x["number"] for x in c["lines"][:6]] and IS.rounds(sub, ROOT / "ideas") == [1]
    _, plan, specs = ST._idea(sub, kw)
    got = ST._box(T.bp_unit(specs[0], "NQ", "5", "nyam"), kw)                                  # the lock's own reading of the box, off its two stores
    plain = lambda v: None if v == float("inf") else v                                         # (a lock keeps "no losing trade" as null)  # noqa: E731
    assert got[0] == lock["default"] and [(x["line"], plain(x["number"])) for x in got[1]] == [(x["line"], x["number"]) for x in lock["box"]]
    # nothing in the repo, nothing in the Lab; the ledger rows are the idea's own; the environment is as it was
    rows = LB.read_ledger(ROOT / "p" / S / "ledger.csv")
    assert {r["stage"] for r in rows} >= {"bp_build", RUN.WORSE} and worse.name in {r["key"] for r in rows}
    no_repo_write(S)
    assert env() == {"switch": None, "drafts": TI.ENV[DRAFTS]}
    # (4) the same stage again (the runner was stopped before its card was written): nothing is run, the lock on file is shown
    with TI.no_engine():
        again = ST.stage5(S, SAID)
    assert (again["result"], again["locked"]["lock"], lines(again)) == ("locked", lock["hash"], lines(c)) and TI.read(d / "lock.json") == lock


def test_a_tiny_real_stage_5_after_a_low_pass_checks_and_locks_the_table_with_its_indicator(world):
    four = upto4(world, LW, 1, "low")
    chart(world)
    sub, calls = f"{LW}_a5f1", TS.spy(world)
    home = f"{sub}__trend_with-NQ-tf5"
    assert four["picked"] == {"sub": sub, "bar": "5", "way": 0, "filter": "trend_with"} and four["tries"] == 3
    assert not (ROOT / "runs" / f"{sub}__trend_with-ES-tf5").exists()                          # stage 3 ran its HOME tables only
    with TI.passing():
        c = TS.whole(ST.stage5(LW, SAID), 5)
    assert (c["passed"], c["result"], c["picked"], c["tries"]) == (True, "locked", four["picked"], 3) and lines(c) == [*BOXL, "P5.9"]
    ran_ = {k for x in calls for k, skipped in zip(x["keys"], x["skipped"]) if not skipped}    # the build RAN its other-market stores, plain and with the indicator
    assert {f"{sub}-ES-tf5", f"{sub}__trend_with-ES-tf5", f"{sub}-GC-tf5", f"{sub}__trend_with-GC-tf5"} <= ran_ and home not in ran_
    d = ROOT / "ideas" / sub
    chk, lock = TI.read(d / "check.json"), TI.read(d / "lock.json")
    assert Path(chk["source"]["where"]).resolve() == (ROOT / "runs" / home).resolve() and [x["passed"] for x in chk["lines"]][:5] == [True] * 5
    assert "the stated maximum of 1 a session and day" in chk["lines"][2]["text"]
    h = lock["home"]
    assert (h["key"], h["filter"], h["worse"], h["folder"]) == (home, "trend_with", f"{home}-nyam-worse", str(ROOT / "runs"))
    assert (ROOT / "runs" / f"{home}-nyam-worse" / "run.json").is_file() and c["locked"]["lock"] == lock["hash"] and "with trend with is locked" in c["text"]
    b = TI.read(d / "rounds" / "1" / "build.json")
    assert [x["line"] for x in b["lines"]] == [f"2.{i}" for i in range(1, 10)] and len(b["neighbors"]) == 2 and b["filter"] == "trend_with"
    no_repo_write(LW)


# ================================================================ stage 6: the one read (the toolkit answers canned)

def six(mp, name: str = C, fail=(), refuse=None, lock: str = HASH) -> dict:
    """Stage 5 on file by hand (locked), and oos.test, propodds.handed / cell and pipe_prop.odds canned -> the calls."""
    picked = {"sub": f"{name}_a5", "bar": "5", "way": 0, "filter": None}
    ran(name, 5, hand(5, picked, 2, result="locked", locked={"default": "or_min15_atr3-r1", "lock": HASH, "prop": {}}))
    calls: dict = {"test": [], "handed": [], "cell": [], "odds": []}

    def test(sub, confirm=False, second_look=False, root=None, **k):
        calls["test"].append({"name": sub, "confirm": confirm, "second_look": second_look, "root": root, **k, "env": env()})
        if refuse:
            raise refuse
        return {"ok": True, "passed": not fail, "failed": list(fail), "verdict": "NOT PROVEN" if fail else "PROVEN ON HISTORY", "lock": lock,
                "lines": [row(f"4.{i}", f"4.{i}" not in fail) for i in range(1, 10)], "range": {"start": "2025-07-01", "end": "2026-09-30"}}

    mp.setattr(OOS, "test", test)
    mp.setattr(PO, "handed", lambda sub, root=None: calls["handed"].append((sub, root)) or {"calendar": SY.weekdays(), "span": SY.SPAN})
    mp.setattr(PO, "cell", lambda h, vid: calls["cell"].append(vid) or LB.pack([SY.trade("2025-07-01", 20.0), SY.trade("2025-07-02", -5.0)]))
    mp.setattr(PP, "odds", odds_fake(calls["odds"]))
    return calls


def test_stage_6_reads_the_unseen_days_once_through_the_toolkit_and_labels_a_pass(world):
    base(world)
    calls = six(world)
    c = TS.whole(ST.stage6(C, CTX), 6)
    assert (c["passed"], c["result"], c["tries"]) == (True, "proven on history", 2) and c["picked"]["sub"] == f"{C}_a5" and "code_problem" not in c
    assert lines(c) == [f"4.{i}" for i in range(1, 10)] and "PROVEN ON HISTORY" in c["text"] and "2025-07-01 .. 2026-09-30" in c["text"]
    (t,) = calls["test"]                                                                       # ONE call: the one read, confirmed, never a second look
    assert (t["name"], t["confirm"], t["second_look"], t["root"]) == (f"{C}_a5", True, False, ROOT / "ideas")
    assert (t["out"], t["ledger"], t["workers"], t["days"]) == (ROOT / "runs_test", ROOT / "p" / C / "ledger.csv", 1, None)      # the pipeline's folders, never runs_bp_test
    assert t["out"] != RUN.TESTS and (ROOT / "runs_test").is_dir() and t["env"]["drafts"] is None
    assert t["env"]["switch"] == {**TINY, "out": str(ROOT / "runs"), "ledger": str(ROOT / "p" / C / "ledger.csv"), "test_out": str(ROOT / "runs_test")}
    # the label: the default box's TEST trades on the days the read replayed, on the pipeline's account and the book's accounts
    assert calls["handed"] == [(f"{C}_a5", ROOT / "ideas")] and calls["cell"] == ["or_min15_atr3-r1"]
    assert [o["account"] for o in calls["odds"]] == [OWN, FLEX, APEX] == list(c["prop"]) and ACCOUNTS == [OWN, FLEX, APEX]
    assert all((o["trades"], o["calendar"]) == (2, SY.weekdays()) for o in calls["odds"])
    assert c["label"] == PP.ALONE == c["prop"][OWN]["label"] and c["prop"][APEX]["confirmed"] is False and c["prop"][FLEX]["confirmed"] is True
    assert set(c["prop"][OWN]) == {"name", "confirmed", "size", "payout_size", "eval", "payout", "label", "text"}
    assert c["rules"]["lines"] == {f"4.{i}": 0.5 for i in range(1, 10)} and c["rules"]["range"] == {"start": "2025-07-01", "end": "2026-09-30"}
    calls = six(world)                                                                         # a tiny run names its test days; no tiny run: no days, no switch
    ST.stage6(C, {"root": ROOT, "tiny": {**TINY, "test_days": ["2025-07-08", "2026-02-11"]}})
    assert calls["test"][0]["days"] == ["2025-07-08", "2026-02-11"] and calls["test"][0]["env"]["switch"]["test_days"] == ["2025-07-08", "2026-02-11"]
    calls = six(world)
    ST.stage6(C, FULL)
    assert (calls["test"][0]["days"], calls["test"][0]["workers"], calls["test"][0]["env"]) == (None, None, {"switch": None, "drafts": None})
    assert env() == {"switch": None, "drafts": TI.ENV[DRAFTS]}


def test_stage_6_a_failed_read_is_final_and_a_refusal_goes_up(world):
    base(world)
    calls = six(world, fail=("4.3", "4.7"))
    c = TS.whole(ST.stage6(C, CTX), 6)
    assert (c["passed"], c["result"]) == (False, "not proven") and "code_problem" not in c and "prop" not in c and "label" not in c
    assert [x["line"] for x in c["lines"] if x["passed"] is False] == ["4.3", "4.7"] and len(c["lines"]) == 9
    assert "NOT PROVEN, it fails 4.3, 4.7 (4.3 FAIL canned)" in c["text"] and "A fail is final" in c["text"] and calls["handed"] == [] and calls["odds"] == []
    six(world, refuse=J.Refuse("a read of the test days is already on file for the idea"))    # the toolkit's one-read rule: never caught here
    TS.refused(lambda: ST.stage6(C, CTX), "a read of the test days is already on file")
    name = add("pfm_orb", 6)                                                                   # a card whose stage 5 never ran
    TS.refused(lambda: ST.stage6(name, CTX), "stage 5 (pick one box and lock) has no passed card on file")


def test_stage_6_a_verdict_on_file_for_another_lock_is_not_this_locks(world):
    base(world)
    calls = six(world)
    (ROOT / "ideas" / f"{C}_a5" / "test.json").write_text(json.dumps({"lock": "feedfeedfeedfeed", "passed": True, "lines": [row("4.1", True)]}))
    try:
        ST.stage6(C, CTX)
        assert len(calls["test"]) == 1                                                         # another lock's verdict: the read of THIS lock is still to make
    finally:
        (ROOT / "ideas" / f"{C}_a5" / "test.json").unlink()


# ================================================================ stage 7: the book card (a hand-made idea, no engine)

N7, SUB7, CELL7 = "pfb_orb", "pfb_orb_a5", "or_min15_atr3-r1"
SPAN7 = ("2025-07-01", "2025-09-30")                 # 66 weekdays, each a session day of the hand-made read
CARD7 = {"name": N7, "why": "The first minutes of the New York morning set a range, and a break of it traps the traders who leaned on it.",
         "loser": "Traders who faded the opening range.", "source": "owner", "market": "NQ", "session": "nyam", "sides": "both", "sides_why": "",
         "ways": [{"family": "orb", "main_setting": "or_min", "values": ["5", "15", "30"], "fixed": {}, "limits": {}}], "indicators": []}
PICK7 = {"sub": SUB7, "bar": "15", "way": 0, "filter": None}
SPEC7 = {"name": SUB7, "version": 1, "card": SY.CARD, "run": SY.RUN}
CTX7 = {"root": ROOT7, "tiny": None}


def tr(day: str, at: str, net: float, secs: int = 600, mae: float = 0.0) -> dict:
    """A trade typed by hand: its net and its worst open point in dollars at ONE contract, held `secs` seconds."""
    a = SY.ms(day, at)
    return {**SY.trade(day, 0.0, at=at), "net": float(net), "mae_usd": float(mae), "exit_ms": a + secs * 1000}


TRADES7 = [tr("2025-07-01", "09:35", 300, secs=4),              # the one fast trade: $300 of the $1,000
           tr("2025-07-02", "10:15", 500), tr("2025-07-03", "10:45", -200),                  # July: +$600
           tr("2025-08-04", "09:40", 700),                      # the biggest day: $700 of the $1,000
           tr("2025-08-05", "10:00", -200, mae=2000),           # ... then a day that stood $2,000 (+ the $4 commission) under its start. August: +$500
           tr("2025-09-02", "10:30", -100)]                     # September: -$100


def seven(fail=()) -> Path:
    """The hand-made idea, locked and tested, inside a pipeline root of its own, with the stage cards 0-5 a run would have left."""
    ideas = PS.ideas_root(ROOT7)
    if N7 not in _DONE:
        PS.add(CARD7, [{"name": SUB7, "way": 0, "bar": "15", "spec": SPEC7}], ROOT7, sig="hand-made", family="orb")
        d = SY.proven(IS, ideas, SUB7, folder=PS.runs_test(ROOT7), cells={CELL7: TRADES7}, span=SPAN7, lock_more={"spec": SPEC7})
        IS.write_test(SUB7, {**TI.read(d / "test.json"), "passed": True, "failed": [], "verdict": "PROVEN ON HISTORY"}, ideas)     # as oos.run saves a verdict
        for n in range(5):
            ran(N7, n, hand(n, None if n == 0 else PICK7, 4, text=f"stage {n} passed\nand its second line"), ROOT7)
        ran(N7, 5, hand(5, PICK7, 4, result="locked", locked={"default": CELL7, "lock": SY.LOCK, "prop": {}}), ROOT7)
        _DONE[N7] = True
    return ideas / SUB7


def test_stage_7_makes_the_book_card_from_the_test_trades_and_the_owner_approves_it(world):
    seven()
    world.setattr(OOS, "test", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the unseen days were read a second time")))
    with SY.no_engine():
        s6 = TS.whole(ST.stage6(N7, CTX7), 6)                                                  # the verdict of THIS lock is on file: it is read, the days are not
        assert (s6["passed"], s6["result"]) == (True, "proven on history") and "its verdict was on file" in s6["text"] and len(s6["lines"]) == 9
        assert list(s6["prop"]) == [OWN, FLEX, APEX] and s6["label"] == s6["prop"][OWN]["label"] and s6["label"] in (PP.ALONE, PP.HELPER)
        ran(N7, 6, s6, ROOT7)
        PS.set_state(N7, ROOT7, status="running", stage=6, picked=PICK7, tries=4)
        st = RN.step(N7, CTX7)                                                                 # the runner's own step: stage 7, then the idea waits
    assert (st["status"], st["stage"], st["stopped_at"]) == ("awaiting_owner", 7, None)
    c = TS.whole(PS.stages(N7, ROOT7)[7], 7)
    assert (c["passed"], c["result"], c["lines"], c["picked"], c["tries"]) == (None, "awaiting owner", [], PICK7, 4) and f"bp.py pipe approve {N7}" in c["text"]
    b = c["book"]
    assert list(b) == ["name", "sub", "family", "source", "why", "market", "session", "bar", "filter", "rule", "label", "prop", "hours", "trades", "days_traded",
                       "win_days_month", "winning_months", "biggest_day_share", "fast_profit_share", "worst_day", "worst_drawdown", "avg_trade", "profit_factor",
                       "net", "tries", "stages", "utc"]
    assert (b["name"], b["sub"], b["family"], b["source"], b["why"]) == (N7, SUB7, "orb", "owner", CARD7["why"])
    assert (b["market"], b["session"], b["bar"], b["filter"], b["tries"]) == ("NQ", "nyam", "15", None, 4)
    assert b["rule"] == {"spec": SPEC7, "default": CELL7, "lock": SY.LOCK}                     # the frozen rule
    # the money facts, at ONE contract: +300 (held 4 s) +500 -200 | +700 -200 | -100 = $1,000 in 6 trades on 6 days
    assert (b["net"], b["trades"], b["days_traded"], b["hours"]) == (1000.0, 6, 6, ["09:35", "10:45"])
    assert b["fast_profit_share"] == 0.3 and b["biggest_day_share"] == 0.7                     # $300 of $1,000 from the 4-second trade · the $700 day
    assert b["winning_months"] == [2, 3] and b["worst_day"] == -200.0                          # July and August won, September lost
    assert b["worst_drawdown"] == 2004.0                                                       # open losses counted: 5 August stood $2,004 under the high it started at
    assert b["profit_factor"] == 3.0 and b["avg_trade"] == pytest.approx(1000 / 6)             # $1,500 won / $500 lost
    # the accounts: the label is stage 6's on the pipeline's account; the unconfirmed rule file says so, and its numbers are there
    assert b["label"] == s6["label"] and list(b["prop"]) == [OWN, FLEX, APEX] and all(tuple(p) == ST.BOOK_PROP for p in b["prop"].values())
    assert [b["prop"][a]["confirmed"] for a in (OWN, FLEX, APEX)] == [True, True, False] and b["prop"][APEX]["name"] == PO.app().load_rules(APEX)["name"]
    assert all(isinstance(p["eval"], float) and isinstance(p["payout"], float) and p["size"] >= 1 for p in b["prop"].values())
    assert b["prop"] == {a: {k: s6["prop"][a][k] for k in ST.BOOK_PROP} for a in s6["prop"]}
    # winning days a month: at the label's eval size, a day at the account's $150 or more, per 21 session days (66 here)
    size = b["prop"][OWN]["size"]
    wins = sum(size * micro >= PO.app().load_rules(OWN)["win_day"] for micro in (29.4, 49.4, 69.4))      # the three winning days at one micro: (net + $4) / 10 - $1
    assert b["win_days_month"] == pytest.approx(wins / 66 * 21) and len(SY.weekdays(*SPAN7)) == 66
    assert list(b["stages"]) == [str(n) for n in range(7)] and b["stages"]["3"] == {"passed": True, "result": "pass", "text": "stage 3 passed"}
    assert b["stages"]["6"] == {"passed": True, "result": "proven on history", "text": s6["text"]} and dt.datetime.fromisoformat(b["utc"]).tzinfo is not None
    assert c["rules"] == {"prop": PR.need("prop"), "box": PR.need("box"), "unseen": list(SPAN7)}
    # the owner's yes: the book card of stage 7 is the book's
    assert RN.approve(N7, ROOT7)["status"] == "book" and PS.book(ROOT7) == [b] and TI.read(ROOT7 / "book" / f"{N7}.json")["fast_profit_share"] == 0.3
    assert not (ROOT7 / "runs").exists() or not [p for p in (ROOT7 / "runs").iterdir() if (p / "run.json").exists()]      # stage 7 ran nothing


def test_stage_7_refuses_a_lock_that_is_not_the_one_stage_5_froze_and_an_idea_that_was_not_read(world):
    seven()
    ran(N7, 6, hand(6, PICK7, 4, result="proven on history", prop={OWN: {"label": PP.HELPER, "size": 1, "name": "x"}}), ROOT7)
    five = PS.stages(N7, ROOT7)[5]
    ran(N7, 5, {**five, "locked": {**five["locked"], "lock": "feedfeedfeedfeed"}}, ROOT7)
    try:
        TS.refused(lambda: ST.stage7(N7, CTX7), f"the lock of {SUB7} on file ({SY.LOCK}) is not the one stage 5 froze (feedfeedfeedfeed)")
    finally:
        ran(N7, 5, five, ROOT7)
    (ROOT7 / "p" / N7 / "stages" / "6.json").unlink()
    TS.refused(lambda: ST.stage7(N7, CTX7), "stage 6 (unseen days) has no passed card on file")


def test_the_facts_of_a_book_card_by_hand():
    cal = SY.weekdays("2025-07-01", "2025-07-31")                                              # 23 session days
    x = LB.pack([tr("2025-07-01", "09:35", 30, secs=5), tr("2025-07-01", "10:00", 40), tr("2025-07-02", "09:50", 50, secs=6), tr("2025-08-01", "10:59", -20)])
    f = ST._facts(x, cal, PR.need("box", "fast_seconds"))
    assert PR.need("box", "fast_seconds") == 5 and f["fast_profit_share"] == 0.3              # held 5 seconds is fast, 6 is not: $30 of $100
    assert f["biggest_day_share"] == 0.7 and (f["net"], f["trades"], f["days_traded"]) == (100.0, 4, 3)      # a DAY's net: 30 + 40 on 1 July
    assert f["winning_months"] == [1, 2] and f["worst_day"] == -20.0 and f["hours"] == ["09:35", "10:59"]   # a day that traded off the calendar is not dropped
    assert f["profit_factor"] == 6.0 and f["avg_trade"] == 25.0 and f["worst_drawdown"] == 20.0             # 120 / 20 · from the high of $120 to $100
    f = ST._facts(LB.pack([tr("2025-07-01", "09:35", 30, secs=1), tr("2025-07-02", "09:35", 10)]), cal, 5)
    assert f["profit_factor"] is None and f["fast_profit_share"] == 0.75 and f["winning_months"] == [1, 1] and f["worst_day"] == 0.0      # no losing trade; a day without a trade is $0
    f = ST._facts(LB.pack([tr("2025-07-01", "09:35", -30, secs=1), tr("2025-07-02", "09:35", 10)]), cal, 5)
    assert (f["net"], f["biggest_day_share"], f["fast_profit_share"], f["winning_months"]) == (-20.0, None, None, [0, 1])     # no profit: no share of it
    f = ST._facts(LB.pack([]), cal, 5)
    assert (f["hours"], f["trades"], f["days_traded"], f["avg_trade"], f["profit_factor"], f["net"], f["worst_drawdown"]) == (None, 0, 0, None, None, 0.0, 0.0)
    json.dumps(f)                                                                              # plain numbers: a book card is a JSON file


def test_winning_days_a_month_at_a_size():
    cal = SY.weekdays("2025-07-01", "2025-08-27")
    x = LB.pack([SY.trade(d, 20.0) for d in cal[:4]] + [SY.trade(cal[4], -20.0)])              # four days of +$20 a micro, one of -$20
    assert len(cal) == 42 and PO.app().load_rules(OWN)["win_day"] == 150 and PR.need("box", "month_days") == 21
    assert ST._win_days(x, cal, OWN, 10) == pytest.approx(2.0)                                 # 10 micros: 4 days of $200 in 42 session days = 2 a month of 21
    assert ST._win_days(x, cal, OWN, 7) == 0.0 and ST._win_days(x, cal, OWN, None) is None     # 7 micros: $140 is under the $150 · no size: nothing to read


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-W", "ignore"]))
