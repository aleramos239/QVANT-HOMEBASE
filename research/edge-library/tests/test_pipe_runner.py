"""LOCK of the pipeline's runner and its commands (blueprint/pipe_runner.py, `bp.py pipe ...`) -- pipeline plan A, task 8.

1. step() runs ONE stage of ONE idea: the next one, its card on disk, the state after it. A failed stage stops the idea
   with the failed row as its why; stage 7 leaves it awaiting the owner; only a queued or running idea is stepped.
2. What a stage RAISES: a refusal stops the idea with the refusal's words; anything else is a code problem with the
   traceback on the stage card; the refusal of the no-compute window changes nothing and says when to look again.
3. Kill and resume: the state on disk says where to carry on -- a finished stage is never run again, a stage that was
   cut short is run again from its start.
4. loop(): the queue's order (the inbox first), the next idea after one stops, the pause between two stages, one runner
   a root, the window slept out, one line a stage on runner.log; one idea's failure never ends it.
5. approve / refuse: only from awaiting_owner; approve writes the book card, refuse needs its reason.
6. start(): the detached child's command line, its pid file, and "already" while a runner works.
7. The command line, end to end in a temp root: add (a whole card, one with a line missing, the same card again), list,
   show, pause / resume, _loop --once, approve, refuse, book, start.
THE STAGES ARE FAKES (pipe_runner.stage_fn is replaced): pipe_stages is never imported, no engine runs, and nothing is
written under ~/.homebase or in the repo. A few seconds (the card check of part 7 loads the engine's registry).

  pytest tests/test_pipe_runner.py -q
"""
from __future__ import annotations

import contextlib
import copy
import datetime as dt
import fcntl
import io
import json
import os
import sys
from pathlib import Path

import pytest

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
import judge as J  # noqa: E402
import l2sim as S  # noqa: E402
import test_blueprint_ideas as TI  # noqa: E402
import test_pipe_card as TPC  # noqa: E402
from blueprint import api  # noqa: E402
from blueprint import cli as C  # noqa: E402
from blueprint import pipe_runner as PR  # noqa: E402
from blueprint import pipe_store as PS  # noqa: E402
from blueprint import runner as RUN  # noqa: E402

TUE = lambda h, m: dt.datetime(2026, 10, 6, h, m, tzinfo=S.ET)  # noqa: E731 - a weekday
BOOK = {"name": "?", "label": "stands alone", "family": "fvg", "market": "NQ", "session": "nyam", "bar": "5"}


@pytest.fixture()
def root(tmp_path, monkeypatch):
    """A pipeline root of this test's own; a call that forgets its root still lands in the temp folder."""
    monkeypatch.setenv(PS.ENV, str(tmp_path / "env_root"))
    return tmp_path / "pipeline"


def idea(root, name: str, inbox: bool = False) -> dict:
    """A queued idea, filed as the store files a checked card (no card check: the store takes what it is given)."""
    card = {"name": name, "why": "Late buyers chase the first gap.", "loser": "Those who fade it.", "source": "owner", "market": "NQ", "session": "nyam", "sides": "both"}
    return PS.add(card, [{"name": f"{name}_a5", "way": 0, "bar": "5", "spec": {}}], root, inbox, sig=f"sig-{name}", family="fvg")


def card(n: int, name: str = "x", **more) -> dict:
    """The stage card a passing stage n returns (stage 7: no verdict, and the book card)."""
    c = {"stage": n, "name": PR.NAMES[n], "passed": None if n == 7 else True, "result": None, "lines": [], "text": f"stage {n} of {name} is fine\nmore words",
         "picked": None, "tries": None, "rules": {}, "utc": "2026-10-08T03:10:00+00:00", "seconds": 12.0}
    if n == 7:
        c["book"] = {**BOOK, "name": name}
    return {**c, **more}


def fakes(monkeypatch, plan: dict = None) -> list:
    """The stages as fakes -> the list of (idea, stage) they were called with. plan[(idea, n)] or plan[n] = what the stage
    does instead of passing: a dict over its card, an exception it raises, or a function (name, ctx) -> one of the two."""
    calls, plan = [], plan or {}

    def stage_fn(n):
        def stage(name, ctx, progress=None):
            calls.append((name, n))
            got = plan.get((name, n), plan.get(n))
            got = got(name, ctx) if callable(got) else got
            if isinstance(got, BaseException):
                raise got
            return card(n, name, **(got or {}))
        return stage
    monkeypatch.setattr(PR, "stage_fn", stage_fn)
    return calls


def ctx(root) -> dict:
    return {"root": root, "tiny": None}


def log(root) -> list:
    return [line.split("\t") for line in (root / PR.LOG).read_text().splitlines()]


def window(monkeypatch, when):
    """The engine's no-compute window is back (09:18-09:36 ET on weekdays) and the runner's clock stands at `when`."""
    monkeypatch.setattr(S, "OPEN_WINDOW", (dt.time(9, 18), dt.time(9, 36)))
    now = [when]
    monkeypatch.setattr(RUN, "clock", lambda: now[0])
    return now


def same(a: dict, b: dict) -> bool:
    """Two states say the same (the store stamps updated_utc on every write)."""
    return {k: v for k, v in a.items() if k != "updated_utc"} == {k: v for k, v in b.items() if k != "updated_utc"}


def run(argv: list, stdin: str = "") -> tuple:
    """The command line in this process, with --json -> (exit code, the one object)."""
    rc, out = TI._run([*argv, "--json"], stdin)
    return rc, json.loads(out)


# ================================================================ 1. one stage of one idea

def test_a_step_runs_the_next_stage_writes_its_card_and_the_state(root, monkeypatch):
    idea(root, "fvg_open")
    seen = []

    def stage1(name, c):                                                    # the state says "running" while a stage works
        seen.append((PS.state(name, root)["status"], PS.state(name, root)["stage"], c))
        return {"tries": 2, "picked": {"sub": "fvg_open_a5", "bar": "5", "way": 0, "filter": None}, "result": "low"}
    calls = fakes(monkeypatch, {1: stage1})
    c = ctx(root)
    st = PR.step("fvg_open", c)
    assert (st["status"], st["stage"], st["stopped_at"], st["why"], st["tries"], st["picked"]) == ("running", 0, None, "", 0, None)
    st = PR.step("fvg_open", c)
    assert calls == [("fvg_open", 0), ("fvg_open", 1)] and seen == [("running", 0, c)]
    assert (st["status"], st["stage"], st["tries"], st["picked"]["sub"]) == ("running", 1, 2, "fvg_open_a5") and st == PS.state("fvg_open", root)
    assert PS.stages("fvg_open", root)[1] == card(1, "fvg_open", **stage1("fvg_open", c)) and sorted(PS.stages("fvg_open", root)) == [0, 1]
    st = PR.step("fvg_open", c)                                             # a later card without a pick or a count leaves the state's
    assert (st["stage"], st["tries"], st["picked"]["sub"]) == (2, 2, "fvg_open_a5")


def test_a_failed_stage_stops_the_idea_with_its_failed_row(root, monkeypatch):
    for name in ("one", "two", "three"):
        idea(root, name)
    rows = [{"line": "P1.0", "passed": True, "text": "P1.0 PASS 2 heat maps"}, {"line": "P1.1", "passed": False, "text": "P1.1 FAIL 41 % of boxes profitable (need 50 %)"},
            {"line": "P1.2", "passed": False, "text": "P1.2 FAIL average trade $12"}]
    fakes(monkeypatch, {("one", 1): {"passed": False, "lines": rows, "tries": 2}, ("two", 2): {"passed": False, "code_problem": True, "text": "a trade outside its session\nrow 7"},
                        ("three", 0): {"passed": False, "lines": [{"line": "P0.1", "passed": None, "text": "P0.1 n/a"}], "text": "the card is not whole"}})
    PR.step("one", ctx(root))
    st = PR.step("one", ctx(root))
    assert (st["status"], st["stage"], st["stopped_at"], st["why"], st["tries"]) == ("stopped", 1, 1, "P1.1 FAIL 41 % of boxes profitable (need 50 %)", 2)
    assert PS.stages("one", root)[1]["passed"] is False and PS.order(root) == ["two", "three"]
    for _ in range(3):
        st = PR.step("two", ctx(root))
    assert (st["status"], st["stopped_at"], st["why"]) == ("code_problem", 2, "a trade outside its session")     # no failed row: the text's first line
    st = PR.step("three", ctx(root))
    assert (st["status"], st["stage"], st["stopped_at"], st["why"]) == ("stopped", 0, 0, "the card is not whole")
    for name, status in (("one", "stopped"), ("two", "code_problem")):       # what has stopped is not stepped again
        assert f"{name} is {status}" in TI.refused(lambda name=name: PR.step(name, ctx(root)), "queued or running")
    assert "no pipeline idea" in TI.refused(lambda: PR.step("nobody", ctx(root)), "nobody")


def test_every_stage_passed_the_idea_waits_for_the_owner(root, monkeypatch):
    idea(root, "fvg_open")
    calls = fakes(monkeypatch)
    assert PR.loop(ctx(root), once=True) == 0
    st = PS.state("fvg_open", root)
    assert calls == [("fvg_open", n) for n in range(8)] and sorted(PS.stages("fvg_open", root)) == list(range(8))
    assert (st["status"], st["stage"], st["stopped_at"], st["why"]) == ("awaiting_owner", 7, None, "") and PS.order(root) == []
    assert [(r[1], r[2], r[3], r[4], r[5]) for r in log(root)] == [("fvg_open", str(n), "PASS", "12s", f"stage {n} of fvg_open is fine") for n in range(8)]
    assert all(dt.datetime.fromisoformat(r[0]).utcoffset() == dt.timedelta(0) for r in log(root))
    assert "fvg_open is awaiting_owner" in TI.refused(lambda: PR.step("fvg_open", ctx(root)), "queued or running")
    assert PR.loop(ctx(root), once=True) == 0 and len(calls) == 8                  # nothing is left to run


# ================================================================ 2. what a stage raises

def test_a_stage_that_crashes_is_a_code_problem_and_the_loop_goes_on(root, monkeypatch):
    idea(root, "one")
    idea(root, "two")
    calls = fakes(monkeypatch, {("one", 1): ValueError("the table has no box\n" + "x" * 400), ("two", 3): {"passed": False, "text": "no indicator helps"}})
    assert PR.loop(ctx(root), once=True) == 0
    st, c = PS.state("one", root), PS.stages("one", root)[1]
    assert (st["status"], st["stage"], st["stopped_at"]) == ("code_problem", 0, 1) and st["why"].startswith("ValueError: the table has no box") and len(st["why"]) == 300
    assert c["passed"] is False and c["code_problem"] is True and c["stage"] == 1 and c["name"] == "raw heat map" and c["text"] == st["why"]
    assert 0 < len(c["trace"]) <= 20 and c["trace"][0].startswith("Traceback") and "ValueError: the table has no box" in "\n".join(c["trace"])
    assert calls == [("one", 0), ("one", 1), ("two", 0), ("two", 1), ("two", 2), ("two", 3)]
    assert (PS.state("two", root)["status"], PS.state("two", root)["stopped_at"]) == ("stopped", 3)
    assert [(r[1], r[2], r[3]) for r in log(root)] == [("one", "0", "PASS"), ("one", "1", "CODE"), ("two", "0", "PASS"), ("two", "1", "PASS"), ("two", "2", "PASS"), ("two", "3", "FAIL")]
    assert log(root)[1][5] == "ValueError: the table has no box"


def test_a_stage_that_returns_no_card_is_a_code_problem(root, monkeypatch):
    idea(root, "one")
    monkeypatch.setattr(PR, "stage_fn", lambda n: lambda name, c, progress=None: None)
    st = PR.step("one", ctx(root))
    assert (st["status"], st["stopped_at"], st["why"]) == ("code_problem", 0, "TypeError: stage 0 returned NoneType, not a stage card")


def test_a_refusal_from_a_stage_stops_the_idea_with_its_words(root, monkeypatch):
    idea(root, "one")
    idea(root, "two")
    assert J.Refuse in api.REFUSALS and S.HoldoutSealed in api.REFUSALS
    fakes(monkeypatch, {("one", 0): J.Refuse("line 3.4 FAIL: the box has 150 trades (need 200)"), ("two", 0): S.HoldoutSealed("2025-07-01 is sealed")})
    st = PR.step("one", ctx(root))
    assert (st["status"], st["stage"], st["stopped_at"], st["why"]) == ("stopped", None, 0, "line 3.4 FAIL: the box has 150 trades (need 200)")
    c = PS.stages("one", root)[0]
    assert c["passed"] is False and c["refused"] is True and c["text"] == st["why"] and "code_problem" not in c and "trace" not in c
    st = PR.step("two", ctx(root))                                              # every refusal of the toolkit, not judge.Refuse alone
    assert (st["status"], st["stopped_at"]) == ("stopped", 0) and "sealed" in st["why"]


def test_the_no_compute_window_is_a_wait_and_changes_nothing(root, monkeypatch):
    idea(root, "one")
    now = window(monkeypatch, TUE(9, 20))
    assert PR.WINDOW_WORDS in TI.refused(RUN.may_start, "09:18-09:36")           # the words the runner's own refusal is known by
    calls = fakes(monkeypatch, {1: lambda name, c: RUN.may_start()})
    PR.step("one", ctx(root))
    before = PS.state("one", root)
    st = PR.step("one", ctx(root))
    assert st.pop("wait_until") == "2026-10-06T09:36:00-04:00" and same(st, before) and same(PS.state("one", root), before)
    assert before["status"] == "running" and sorted(PS.stages("one", root)) == [0] and calls == [("one", 0), ("one", 1)]
    assert PR.loop(ctx(root), once=True) == 0                                    # once: it does not sleep the window out
    assert same(PS.state("one", root), before) and [(r[2], r[3]) for r in log(root)] == [("1", "WAIT")] and "nothing heavy starts" in log(root)[0][5]
    # an idea that was only queued goes back to queued
    idea(root, "two")
    fakes(monkeypatch, {0: lambda name, c: RUN.may_start()})
    st = PR.step("two", ctx(root))
    assert (st["status"], st["stage"]) == ("queued", None) and "wait_until" in st and PS.stages("two", root) == {}
    # another refusal while the window is open is a wait too: it is given again after the window, and stops the idea then
    fakes(monkeypatch, {0: J.Refuse("the card is not whole")})
    assert "wait_until" in PR.step("two", ctx(root)) and PS.state("two", root)["status"] == "queued"
    now[0] = TUE(9, 36)
    assert PR.step("two", ctx(root))["status"] == "stopped"
    # the window closed between the stage's refusal and the look: still a wait, a minute long
    idea(root, "three")
    fakes(monkeypatch, {0: J.Refuse("nothing heavy starts 09:18-09:36 ET on weekdays (the desk's open): start it after 09:36 ET")})
    st = PR.step("three", ctx(root))
    assert st["wait_until"] == "2026-10-06T09:37:00-04:00" and st["status"] == "queued" and PS.stages("three", root) == {}


def test_the_loop_sleeps_the_window_out_and_carries_on(root, monkeypatch):
    idea(root, "one")
    now = window(monkeypatch, TUE(9, 34))
    calls = fakes(monkeypatch, {1: lambda name, c: RUN.may_start(), 2: {"passed": False, "text": "the machine check failed"}})
    slept = []

    class Done(Exception):
        pass

    def sleep(s):
        slept.append(s)
        if not PS.order(root):                                                   # the queue is empty: the endless loop is idle
            raise Done
        now[0] += dt.timedelta(seconds=s)
    with pytest.raises(Done):
        PR.loop(ctx(root), sleep=sleep, idle_s=45)
    assert slept == [45, 45, 30, 45] and calls == [("one", 0), ("one", 1), ("one", 1), ("one", 2)]
    assert [(r[2], r[3]) for r in log(root)] == [("0", "PASS"), ("1", "WAIT"), ("1", "PASS"), ("2", "FAIL")]


# ================================================================ 3. kill and resume

def test_a_new_call_carries_on_where_the_state_on_disk_says(root, monkeypatch):
    idea(root, "one")
    first = fakes(monkeypatch)
    PR.step("one", ctx(root))
    PR.step("one", ctx(root))
    assert first == [("one", 0), ("one", 1)]
    again = fakes(monkeypatch)                                                   # a fresh runner: nothing but the files
    st = PR.step("one", {"root": str(root), "tiny": None})
    assert again == [("one", 2)] and (st["status"], st["stage"]) == ("running", 2)


def test_a_stage_that_was_cut_short_is_run_again_from_its_start(root, monkeypatch):
    idea(root, "one")
    fakes(monkeypatch, {2: KeyboardInterrupt()})                                 # the runner is killed inside stage 2
    PR.step("one", ctx(root))
    PR.step("one", ctx(root))
    with pytest.raises(KeyboardInterrupt):
        PR.step("one", ctx(root))
    st = PS.state("one", root)
    assert (st["status"], st["stage"], st["stopped_at"]) == ("running", 1, None) and sorted(PS.stages("one", root)) == [0, 1]
    assert PS.order(root) == ["one"]
    calls = fakes(monkeypatch)
    assert PR.loop(ctx(root), once=True) == 0
    assert calls == [("one", n) for n in range(2, 8)] and PS.state("one", root)["status"] == "awaiting_owner"


def test_a_stage_that_cannot_be_loaded_moves_no_state_and_ends_no_loop(root, monkeypatch):
    idea(root, "one")
    idea(root, "two")

    def stage_fn(n):
        raise ImportError("No module named 'blueprint.pipe_stages'")
    monkeypatch.setattr(PR, "stage_fn", stage_fn)
    before = PS.state("one", root)
    with pytest.raises(ImportError):
        PR.step("one", ctx(root))
    assert PS.state("one", root) == before and PS.stages("one", root) == {}
    assert PR.loop(ctx(root), once=True) == 0                                    # each idea is tried once and left as it was
    assert PS.order(root) == ["one", "two"] and [s["status"] for s in PS.ideas(root)] == ["queued", "queued"]
    assert [(r[1], r[2], r[3]) for r in log(root)] == [("one", "-", "CODE"), ("two", "-", "CODE")] and "ImportError" in log(root)[0][5]


# ================================================================ 4. the loop

def test_a_stopped_idea_makes_room_for_the_next_and_the_inbox_goes_first(root, monkeypatch):
    idea(root, "one")
    idea(root, "two")
    idea(root, "urgent", inbox=True)
    calls = fakes(monkeypatch, {("urgent", 1): {"passed": False, "lines": [{"line": "P1.1", "passed": False, "text": "P1.1 FAIL no heat map passes"}]},
                                ("one", 1): {"passed": False, "text": "nothing"}, ("two", 0): {"passed": False, "text": "nothing"}})
    assert PS.order(root) == ["urgent", "one", "two"]
    assert PR.loop(ctx(root), once=True) == 0
    assert calls == [("urgent", 0), ("urgent", 1), ("one", 0), ("one", 1), ("two", 0)]
    st = PS.state("urgent", root)
    assert (st["status"], st["stopped_at"], st["why"]) == ("stopped", 1, "P1.1 FAIL no heat map passes")
    assert int((root / PR.PID).read_text()) == os.getpid()                       # the runner writes its own pid


def test_a_pause_ends_the_work_after_the_stage_in_hand(root, monkeypatch):
    idea(root, "one")
    idea(root, "two")
    calls = fakes(monkeypatch, {("one", 1): lambda name, c: PS.pause(root) and None})      # the owner pauses while stage 1 works
    assert PR.loop(ctx(root), once=True) == 0
    st = PS.state("one", root)
    assert calls == [("one", 0), ("one", 1)] and (st["status"], st["stage"]) == ("running", 1) and PS.paused(root)
    assert PS.state("two", root)["status"] == "queued"
    assert PR.loop(ctx(root), once=True) == 0 and len(calls) == 2                # paused: a runner does nothing
    PS.resume(root)
    calls = fakes(monkeypatch)
    assert PR.loop(ctx(root), once=True) == 0
    assert calls == [("one", n) for n in range(2, 8)] + [("two", n) for n in range(8)]


def test_one_runner_a_root(root, monkeypatch, capsys):
    idea(root, "one")
    calls = fakes(monkeypatch)
    monkeypatch.setattr(PR, "GAP", 0.0)
    root.mkdir(parents=True, exist_ok=True)
    with open(root / PR.LOCK, "a") as fh:                                        # another runner works
        fcntl.flock(fh, fcntl.LOCK_EX)
        (root / PR.PID).write_text("4242")
        assert PR.loop(ctx(root), once=True) == 0
        assert calls == [] and PS.state("one", root)["status"] == "queued" and not (root / PR.LOG).exists()
        assert "a runner is already working" in capsys.readouterr().err
        s = PR.status(root)
        assert (s["running"], s["pid"], s["paused"]) == (True, 4242, False)
    s = PR.status(root)
    assert (s["running"], s["pid"]) == (False, None)
    assert PR.loop(ctx(root), once=True) == 0 and len(calls) == 8                # the lock is free again


def test_status_lists_what_can_run_first_then_the_latest_change(root, monkeypatch):
    assert PR.status(root) == {"running": False, "pid": None, "paused": False, "counts": {}, "ideas": []} and not root.exists()      # a look makes no folder
    tick = [0]

    def now():
        tick[0] += 1
        return f"2026-10-08T03:{tick[0]:02d}:00+00:00"
    monkeypatch.setattr(PS, "_now", now)
    for name in ("a1", "b2", "c3", "d4"):
        idea(root, name)
    idea(root, "e5", inbox=True)
    PS.set_state("b2", root, status="stopped", stopped_at=1, why="P1.1 FAIL")
    PS.set_state("a1", root, status="book")
    PS.set_state("d4", root, status="running", stage=2)
    PS.pause(root)
    s = PR.status(root)
    assert [x["name"] for x in s["ideas"]] == ["e5", "c3", "d4", "a1", "b2"] and s["paused"] is True
    assert s["counts"] == {"queued": 2, "running": 1, "stopped": 1, "book": 1}


# ================================================================ 5. the owner's two words

def test_approve_and_refuse_only_from_awaiting_owner(root, monkeypatch):
    for name in ("yes", "no", "early", "bare"):
        idea(root, name)
    fakes(monkeypatch, {("early", 1): {"passed": False, "text": "nothing"}, ("bare", 7): {"book": None}})
    assert PR.loop(ctx(root), once=True) == 0
    assert [PS.state(n, root)["status"] for n in ("yes", "no", "early", "bare")] == ["awaiting_owner", "awaiting_owner", "stopped", "awaiting_owner"]
    for fn in (lambda: PR.approve("early", root), lambda: PR.refuse("early", "too thin", root)):
        assert "early is stopped" in TI.refused(fn, "awaiting_owner")
    assert PS.book(root) == [] and PS.state("early", root)["status"] == "stopped"
    assert "nothing was written" in TI.refused(lambda: PR.approve("bare", root), "no book card") and PS.state("bare", root)["status"] == "awaiting_owner"
    st = PR.approve("yes", root)
    assert st["status"] == "book" and PS.book(root) == [{**BOOK, "name": "yes"}] and json.loads((root / "book" / "yes.json").read_text()) == {**BOOK, "name": "yes"}
    for why in ("", "   ", None):
        TI.refused(lambda why=why: PR.refuse("no", why, root), "needs the reason")
    assert PS.state("no", root)["status"] == "awaiting_owner"
    st = PR.refuse("no", "  the hours are\n too thin ", root)
    assert (st["status"], st["why"], st["stage"]) == ("refused", "the hours are too thin", 7) and [c["name"] for c in PS.book(root)] == ["yes"]
    for fn in (lambda: PR.approve("yes", root), lambda: PR.refuse("yes", "no", root), lambda: PR.approve("no", root)):      # a word is given once
        TI.refused(fn, "awaiting_owner")
    TI.refused(lambda: PR.approve("nobody", root), "no pipeline idea")


# ================================================================ 6. the detached runner

class Child:
    """subprocess.Popen, watched: nothing is started."""
    made: list = []

    def __init__(self, argv, **kw):
        self.pid = 4242
        Child.made.append((argv, kw))


def test_start_is_a_detached_child_or_says_one_is_working(root, monkeypatch):
    monkeypatch.setattr(PR.subprocess, "Popen", Child)
    Child.made.clear()
    assert PR.start(root) == {"pid": 4242, "already": False}
    (argv, kw), = Child.made
    assert argv == [sys.executable, str(W / "bp.py"), "pipe", "_loop", f"--root={root}"]
    assert kw["stdin"] == PR.subprocess.DEVNULL and kw["start_new_session"] is True and kw["cwd"] == str(W)
    assert kw["stdout"] is kw["stderr"] and str(kw["stdout"].name) == str(root / PR.OUT) and kw["stdout"].mode == "ab"
    assert (root / PR.PID).read_text() == "4242"
    with open(root / PR.LOCK, "a") as fh:                                        # the child took the lock: it works
        fcntl.flock(fh, fcntl.LOCK_EX)
        assert PR.start(root) == {"pid": 4242, "already": True} and len(Child.made) == 1
        rc, r = run(["pipe", "start", f"--root={root}"])
        assert rc == 0 and (r["command"], r["already"], r["pid"]) == ("pipe start", True, 4242) and "already working (pid 4242)" in r["text"]
    rc, r = run(["pipe", "start", f"--root={root}"])
    assert rc == 0 and r["already"] is False and len(Child.made) == 2 and "the runner is started (pid 4242)" in r["text"]


# ================================================================ 7. the command line

@pytest.fixture()
def cards():
    TPC.setup_function()
    yield
    TPC.teardown_function()


def test_pipe_list_is_one_aligned_row_an_idea(root, monkeypatch):
    rc, out = TI._run(["pipe", "list", f"--root={root}"])
    assert rc == 0 and out == "no idea is on file\n\n0 ideas\nrunner: not working · queue: not paused\n"
    for name in ("fvg_open", "orb_gold", "ib_break"):
        idea(root, name)
    long = "P1.1 FAIL 41 % of boxes profitable (need 50 %) " + "and more " * 10
    fakes(monkeypatch, {("fvg_open", 1): {"passed": False, "tries": 2, "lines": [{"line": "P1.1", "passed": False, "text": long}]}, ("orb_gold", 1): {"tries": 2},
                        ("orb_gold", 2): lambda name, c: PS.pause(root) and None})
    assert PR.loop(ctx(root), once=True) == 0
    rc, out = TI._run(["pipe", "list", f"--root={root}"])
    assert rc == 0 and out.splitlines() == [
        "name      family  status   stage  tries  why",
        "orb_gold  fvg     running      2      2",
        "ib_break  fvg     queued       -      0",
        "fvg_open  fvg     stopped      1      2  " + long[:80],
        "",
        "3 ideas: 1 queued, 1 running, 1 stopped",
        "runner: not working · queue: paused",
        "NEXT: bp.py pipe start runs the queue.",
    ]
    rc, r = run(["pipe", "list", f"--root={root}"])
    assert rc == 0 and r["ok"] and r["command"] == "pipe list" and r["phase"] is None and r["counts"] == {"queued": 1, "running": 1, "stopped": 1}
    assert [x["name"] for x in r["ideas"]] == ["orb_gold", "ib_break", "fvg_open"] and (r["running"], r["paused"]) == (False, True)


def test_the_commands_end_to_end(root, monkeypatch, cards, tmp_path):
    R = f"--root={root}"
    good = json.dumps(TPC.CARD)
    # ---- add: a card with a line missing is refused with its rows, and nothing is saved
    rc, r = run(["pipe", "add", "--spec=-", R], json.dumps({**TPC.CARD, "why": ""}))
    assert rc == 2 and r["ok"] is False and r["command"] == "pipe add" and r["name"] == "fvg_open" and r["error"].startswith("the card is not whole: P0.1 FAIL")
    assert [x["line"] for x in r["lines"]] == ["P0.1", "P0.2", "P0.3", "P0.4"] and not root.exists()
    for argv, stdin, word in ((["pipe", "add", R], "", "needs the pipeline card"), (["pipe", "add", "--spec=-", R], "", "no card on stdin"),
                              (["pipe", "add", "--spec=-", R], "{not json", "does not read as JSON"), (["pipe", "add", f"--spec={tmp_path / 'none.json'}", R], "", "is not there"),
                              (["pipe", "add", "--spec=-", R], json.dumps({**TPC.CARD, "extra": 1}), "unknown fields"), (["pipe", "bogus", R], "", "invalid choice"),
                              (["pipe"], "", "required")):
        rc, r = run(argv, stdin)
        assert rc == 2 and r["ok"] is False and word in r["error"], (argv, r["error"])
    assert not root.exists()
    # ---- add: a whole card is filed and queued
    rc, r = run(["pipe", "add", "--spec=-", R], good)
    assert rc == 0 and r["ok"] and (r["command"], r["name"], r["status"]) == ("pipe add", "fvg_open", "queued") and r["subs"] == ["fvg_open_a1", "fvg_open_a5"]
    assert r["text"] == "fvg_open is in the queue: place 1 of 1.\nStage 1 will run 2 heat maps: fvg_open_a1, fvg_open_a5."
    assert all(x["passed"] for x in r["lines"]) and r["state"] == PS.state("fvg_open", root) and r["state"]["family"] == "fvg"
    assert [s["name"] for s in PS.card("fvg_open", root)["subs"]] == r["subs"] and PS.order(root) == ["fvg_open"]
    # ---- add: the same card again, under its own name and under another
    for again in (TPC.CARD, {**TPC.CARD, "name": "fvg_twin", "why": "The same idea in other words, said again."}):
        rc, r = run(["pipe", "add", "--spec=-", R], json.dumps(again))
        assert rc == 2 and r["ok"] is False and r["command"] == "pipe add" and ("already on file" in r["error"] or "the same card as 'fvg_open'" in r["error"])
    assert [s["name"] for s in PS.ideas(root)] == ["fvg_open"]
    # ---- add from a file, to the inbox: it goes first
    other = copy.deepcopy(TPC.CARD)
    other.update(name="fvg_mid", ways=[TPC.MID], indicators=[])
    (tmp_path / "card.json").write_text(json.dumps(other))
    rc, r = run(["pipe", "add", f"--spec={tmp_path / 'card.json'}", "--inbox", R])
    assert rc == 0 and r["text"].startswith("fvg_mid is in the queue: place 1 of 2 (inbox: it goes first).") and PS.order(root) == ["fvg_mid", "fvg_open"]
    # ---- pause / resume
    rc, r = run(["pipe", "pause", R])
    assert rc == 0 and (r["command"], r["paused"]) == ("pipe pause", True) and PS.paused(root) and "paused" in r["text"]
    calls = fakes(monkeypatch, {("fvg_mid", 1): {"tries": 2, "picked": {"sub": "fvg_mid_a5", "bar": "5", "way": 0, "filter": "trend_with"}}})
    rc, r = run(["pipe", "_loop", "--once", R])
    assert rc == 0 and r["command"] == "pipe _loop" and r["exit"] == 0 and calls == []                # paused: nothing runs
    rc, r = run(["pipe", "resume", R])
    assert rc == 0 and (r["paused"], r["running"]) == (False, False) and not PS.paused(root) and "no runner is working" in r["text"]
    # ---- the runner, once
    rc, r = run(["pipe", "_loop", "--once", R])
    assert rc == 0 and calls == [(n, k) for n in ("fvg_mid", "fvg_open") for k in range(8)]
    # ---- show
    rc, out = TI._run(["pipe", "show", "fvg_mid", R])
    assert rc == 0 and out.splitlines() == [
        "fvg_mid: fvg on NQ nyam, sides both (source owner)",
        "why: Late buyers chase the first gap after the open.",
        "loser: Traders who fade the first move.",
        "status: awaiting_owner · stage 7 · tries 2 · picked fvg_mid_a5 with trend_with",
        *[f"stage {n} {'n/a ' if n == 7 else 'PASS'} {PR.NAMES[n]}: stage {n} of fvg_mid is fine" for n in range(8)],
        "NEXT: bp.py pipe approve fvg_mid, or bp.py pipe refuse fvg_mid --why=TEXT.",
    ]
    rc, r = run(["pipe", "show", "fvg_mid", R])
    assert rc == 0 and r["status"] == "awaiting_owner" and sorted(r["stages"]) == [str(n) for n in range(8)] and r["card"]["name"] == "fvg_mid"
    rc, r = run(["pipe", "show", "nobody", R])
    assert rc == 2 and r["command"] == "pipe show" and r["name"] == "nobody" and "no pipeline idea" in r["error"]
    # ---- the owner's word
    rc, r = run(["pipe", "book", R])
    assert rc == 0 and r["book"] == [] and r["text"] == "the book is empty"
    rc, r = run(["pipe", "refuse", "fvg_open", R])
    assert rc == 2 and r["command"] == "pipe refuse" and "needs the reason" in r["error"] and PS.state("fvg_open", root)["status"] == "awaiting_owner"
    rc, r = run(["pipe", "refuse", "fvg_open", "--why=too few trades a week", R])
    assert rc == 0 and (r["status"], r["state"]["why"]) == ("refused", "too few trades a week") and r["text"] == "fvg_open is refused: too few trades a week"
    rc, r = run(["pipe", "approve", "fvg_mid", R])
    assert rc == 0 and r["status"] == "book" and r["saved"] == [str(root / "book" / "fvg_mid.json")] and (root / "book" / "fvg_mid.json").is_file()
    rc, r = run(["pipe", "approve", "fvg_open", R])
    assert rc == 2 and "fvg_open is refused" in r["error"]
    rc, out = TI._run(["pipe", "book", R])
    assert rc == 0 and out.splitlines() == ["name     label         family  market  session  bar", "fvg_mid  stands alone  fvg     NQ      nyam     5"]
    rc, out = TI._run(["pipe", "list", R])
    assert rc == 0 and out.splitlines()[-2:] == ["2 ideas: 1 book, 1 refused", "runner: not working · queue: not paused"]
    assert "fvg_open  fvg     refused      7      0  too few trades a week" in out.splitlines()[1:3]


def test_rerun_puts_a_stopped_idea_back_at_the_end_of_the_queue_and_show_names_the_picked_box(root, monkeypatch):
    R = f"--root={root}"
    idea(root, "fvg_open")
    idea(root, "fvg_two")
    pick = {"sub": "fvg_open_a5", "bar": "5", "way": 0, "filter": None, "cell": "d_atr0_pct0p2-r3", "variant": 0.0}
    calls = fakes(monkeypatch, {("fvg_open", 1): {"tries": 2, "picked": pick}, ("fvg_open", 2): {"passed": False, "text": "P2.5 FAIL a price is off"}, ("fvg_two", 0): {"passed": False}})
    assert PR.loop(ctx(root), once=True) == 0
    assert calls == [("fvg_open", 0), ("fvg_open", 1), ("fvg_open", 2), ("fvg_two", 0)] and PS.state("fvg_open", root)["status"] == "stopped"
    rc, out = TI._run(["pipe", "show", "fvg_open", R])
    assert rc == 0 and "status: stopped · stage 2 · tries 2 · picked fvg_open_a5, box d_atr0_pct0p2-r3" in out.splitlines()
    rc, r = run(["pipe", "rerun", "fvg_open", R])
    assert rc == 0 and r["ok"] and (r["command"], r["name"], r["status"], r["moved"]) == ("pipe rerun", "fvg_open", "queued", 3)
    assert r["text"] == ("fvg_open runs again from its first stage (place 1 of 1 in the queue); its 3 stage cards are kept under stages_old (nothing was deleted).")
    st = PS.state("fvg_open", root)
    assert (st["status"], st["stage"], st["stopped_at"], st["why"], st["tries"], st["picked"]) == ("queued", None, None, None, 0, None) and PS.stages("fvg_open", root) == {}
    assert len(list((root / "p" / "fvg_open" / "stages_old").iterdir())) == 1 and PS.order(root) == ["fvg_open"] and PS.state("fvg_two", root)["status"] == "stopped"
    calls = fakes(monkeypatch)                                                                 # this time every stage passes
    assert PR.loop(ctx(root), once=True) == 0 and calls[:1] == [("fvg_open", 0)] and PS.state("fvg_open", root)["status"] == "awaiting_owner"      # from its start
    rc, r = run(["pipe", "rerun", "fvg_open", R])                                              # it waits for the owner now
    assert rc == 2 and r["command"] == "pipe rerun" and "waits for the owner" in r["error"]
    rc, r = run(["pipe", "rerun", "nobody", R])
    assert rc == 2 and "no pipeline idea" in r["error"]
    rc, r = run(["pipe", "rerun", R])
    assert rc == 2 and "name" in r["error"]


def pipe_help() -> str:
    """What `bp.py pipe --help` prints."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), pytest.raises(SystemExit):
        C._parser().parse_args(["pipe", "--help"])
    return out.getvalue()


def test_the_help_keeps_the_two_roots_apart():
    text = pipe_help()
    assert all(w in text for w in PR.SUBS) and "_loop" not in text
    out = io.StringIO()
    with contextlib.redirect_stdout(out), pytest.raises(SystemExit):
        C._parser().parse_args(["pipe", "list", "--help"])
    assert "PIPELINE" in " ".join(out.getvalue().split()) and "HOMEBASE_PIPELINE_ROOT" in out.getvalue() and "not the app's idea folder" in " ".join(out.getvalue().split())
    assert C._parser().parse_args(["pipe", "_loop", "--once", "--root=/x"]).once is True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
