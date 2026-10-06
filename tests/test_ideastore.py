"""The idea store (homebase.ideastore): the idea folder of the blueprint toolkit's plan (section 3), the status
read off the saved results alone, the one-read log of the test days, and the idea's record in the Lab (a marked
comment block on top of its draft, and the group it is filed under). Temp folders only: the suite's `ideas_root`
and `drafts_dir`, and a temp HOME on top (`home`), which must still hold no .homebase when a test ends."""
from __future__ import annotations

import fcntl
import json
import os
import threading
from pathlib import Path

import pytest

from homebase import draftstore, ideastore

NAME = "nq_orb_pre"
SID = "draft_nq_orb_pre"
CARD = "Why: the 08:30 burst carries into the open.\nWho loses: late faders.\nHome: GC, pre-market, 15 min bars."
SPEC = {"name": NAME, "version": 1,
        "card": {"why": "the 08:30 burst carries", "loser": "late faders",
                 "home": {"market": "GC", "session": "pre", "bar": "15"}, "neighbors": ["NQ pre 15"],
                 "not_here": "asia", "main_setting": "or_min", "sides": "both", "sides_why": "a burst runs either way"},
        "run": {"family": "orb", "params": {"or_min": ["5", "15", "30"]}, "fixed": {}, "filters": [],
                "exits": "standard", "limits": {"max_tr": 1}}}
COUNT = {1: 6, 2: 9, 4: 7, 5: 4, 6: 8}       # the law's lines per phase: 1.1-1.6, 2.1-2.9, 4.1-4.7, 5.1-5.4, 6.1-6.8
ACCOUNT = "lucid-pro-50k@2026-09-27b"
LOCK = "9f2c41aa"
RANGE = {"start": "2025-07-01", "end": "2026-09-30"}
EARLY = {"early_look": True, "label": "EARLY LOOK"}      # what the result of an early look says, beyond a test's


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """No test here may fall back to the real ~/.homebase: HOME is a temp folder, and nothing may appear in it."""
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    yield h
    assert not (h / ".homebase").exists()


def lines(phase: int, fail=(), na=(), drop=()) -> list[dict]:
    out = []
    for i in range(1, COUNT[phase] + 1):
        k = f"{phase}.{i}"
        if k in drop:
            continue
        passed = None if k in na else k not in fail
        mark = "n/a " if passed is None else "PASS" if passed else "FAIL"
        out.append({"line": k, "passed": passed, "number": 1.0, "need": 0.5, "text": f"{k} {mark} words about {k}"})
    return out


def result(command: str, phase: int, fail=(), na=(), drop=(), **more) -> dict:
    """A command's result as the toolkit prints and saves it (toolkit plan, section 8)."""
    return {"ok": True, "command": command, "name": NAME, "status": None, "phase": phase, "round": None,
            "lines": lines(phase, fail, na, drop), "text": "", "next": f"after {command}", "job": None,
            "saved": [], "error": None, **more}


def build(n: int = 1, **kw) -> Path:
    """Round n as the toolkit saves it: the reason first, then the result. No filter: 2.7 does not apply."""
    kw.setdefault("na", ("2.7",))
    ideastore.write_reason(NAME, n, f"reason of round {n}")
    return ideastore.write_build(NAME, n, result("build", 2, **kw))


WHERE = ("early_look/test.json", "test.json")


def early(where: str, **kw) -> Path:
    """An early look's result on file: where the toolkit keeps it (its own files beside the idea's, written by the
    toolkit itself, the app's copies brought up to date after), or as the idea's test.json."""
    r = result("test", 4, **EARLY, **kw)
    if where == "test.json":
        return ideastore.write_test(NAME, r)
    p = ideastore.idea_dir(NAME) / where
    p.parent.mkdir(exist_ok=True)
    (p.parent / "lock.json").write_text(json.dumps({"early_look": True, "hash": "e4r1"}), encoding="utf-8")
    p.write_text(json.dumps(r), encoding="utf-8")
    ideastore.refresh(NAME)
    return p


def tree(d: Path) -> list[str]:
    return sorted(str(p.relative_to(d)) for p in d.rglob("*") if p.is_file())


# ---------------------------------------------------------------- where it lives, and names

def test_the_root_is_the_argument_then_the_environment_then_the_home_folder(ideas_root, tmp_path, monkeypatch, home):
    assert ideastore.ideas_root() == ideas_root
    assert ideastore.ideas_root(tmp_path / "x") == tmp_path / "x"
    monkeypatch.delenv(ideastore.ENV)
    assert ideastore.ideas_root() == home / ".homebase" / "ideas"       # only named here, never written


@pytest.mark.parametrize("bad", ["", "a", "Nq_orb", "9lives", "has-dash", "../etc", "a/b", "x" * 41, "draft_x",
                                 "nq930", "json", "homebase", None, 7])
def test_an_idea_is_named_like_its_draft(bad, ideas_root):
    for refused in (ideastore.create, ideastore.idea_dir, ideastore.status, ideastore.read_idea):
        with pytest.raises(ValueError):
            refused(bad)
    assert list(ideas_root.iterdir()) == []


def test_create_makes_the_folder_and_its_first_idea_json(ideas_root):
    assert not ideastore.exists(NAME)
    first = ideastore.create(NAME)
    assert first == {"name": NAME, "created": first["created"], "status": "idea", "phase": 0, "round": None,
                     "lines": [], "next": None, "early_look": False, "runs": [], "group": None}
    assert ideastore.exists(NAME) and ideastore.idea_dir(NAME) == ideas_root / NAME
    assert ideastore.read_idea(NAME) == first == json.loads((ideas_root / NAME / "idea.json").read_text())
    with pytest.raises(FileExistsError):
        ideastore.create(NAME)
    assert ideastore.create(NAME, exist_ok=True) == first


def test_nothing_is_written_for_an_idea_that_was_never_created(ideas_root):
    for write in (lambda: ideastore.write_card(NAME, CARD), lambda: ideastore.write_spec(NAME, SPEC),
                  lambda: ideastore.write_reason(NAME, 1, "why"), lambda: ideastore.append_log(NAME, "note"),
                  lambda: ideastore.read_idea(NAME), lambda: ideastore.refresh(NAME), lambda: ideastore.sync(NAME)):
        with pytest.raises(FileNotFoundError, match="no idea 'nq_orb_pre'"):
            write()
    assert list(ideas_root.iterdir()) == []


# ---------------------------------------------------------------- the folder

def test_the_folder_is_the_plans(ideas_root):
    ideastore.create(NAME)
    ideastore.write_card(NAME, CARD)
    ideastore.write_spec(NAME, SPEC)
    ideastore.write_check(NAME, result("code-check", 1))
    ideastore.write_reason(NAME, 1, "the plain idea, as carded")
    ideastore.write_round_spec(NAME, 1, SPEC)
    ideastore.write_build(NAME, 1, result("build", 2, na=("2.7",)))
    ideastore.write_lock(NAME, {"spec": SPEC, "default": "v2_s3_t2", "hash": LOCK})
    ideastore.write_test(NAME, result("test", 4))
    ideastore.write_sim(NAME, ACCOUNT, result("sim", 5))
    ideastore.write_eval(NAME, result("eval-card", 6))
    d = ideas_root / NAME
    assert tree(d) == sorted(["idea.json", "card.md", "spec.json", "check.json", "rounds/1/reason.txt",
                              "rounds/1/spec.json", "rounds/1/build.json", "lock.json", "test.json",
                              f"sim/{ACCOUNT}.json", "eval.json", "log.jsonl", ".lock"])
    assert (d / "card.md").read_text(encoding="utf-8") == CARD
    assert (d / "rounds/1/reason.txt").read_text(encoding="utf-8") == "the plain idea, as carded\n"
    assert json.loads((d / "spec.json").read_text()) == SPEC == json.loads((d / "rounds/1/spec.json").read_text())
    assert json.loads((d / "rounds/1/build.json").read_text()) == result("build", 2, na=("2.7",))
    assert json.loads((d / "lock.json").read_text())["hash"] == LOCK
    assert json.loads((d / f"sim/{ACCOUNT}.json").read_text())["command"] == "sim"
    assert ideastore.rounds(NAME) == [1]


def test_what_is_saved_is_checked_before_it_is_written(ideas_root):
    ideastore.create(NAME)
    for bad in (lambda: ideastore.write_card(NAME, ""), lambda: ideastore.write_card(NAME, {"why": "x"}),
                lambda: ideastore.write_spec(NAME, "not a dict"), lambda: ideastore.write_test(NAME, [1, 2]),
                lambda: ideastore.write_sim(NAME, "../evil", result("sim", 5)),
                lambda: ideastore.write_sim(NAME, "", result("sim", 5)),
                lambda: ideastore.write_sim(NAME, ".hidden", result("sim", 5))):
        with pytest.raises(ValueError):
            bad()
    assert tree(ideas_root) == [f"{NAME}/.lock", f"{NAME}/idea.json", f"{NAME}/log.jsonl"]


def test_a_write_is_a_temp_file_then_a_replace(ideas_root, monkeypatch):
    ideastore.create(NAME)
    ideastore.write_spec(NAME, SPEC)
    p = ideas_root / NAME / "spec.json"
    was, moves, real = p.read_text(), [], os.replace

    def failing(src, dst):
        moves.append((os.fspath(src), os.fspath(dst)))
        assert json.loads(Path(src).read_text(encoding="utf-8"))["version"] == 2     # complete before the move
        raise OSError("disk full")

    monkeypatch.setattr(ideastore.os, "replace", failing)
    with pytest.raises(OSError):
        ideastore.write_spec(NAME, {**SPEC, "version": 2})
    assert p.read_text() == was                                                      # the old file is whole
    (src, dst), = moves
    assert dst == str(p) and os.path.dirname(src) == str(p.parent) and src != dst
    monkeypatch.setattr(ideastore.os, "replace", real)
    ideastore.write_spec(NAME, {**SPEC, "version": 2})
    assert json.loads(p.read_text())["version"] == 2


def test_a_round_has_its_reason_first_and_there_is_no_round_six(ideas_root):
    """Line 2.9: at most 5 rounds, each with its reason written before the run."""
    ideastore.create(NAME)
    with pytest.raises(ValueError, match="reason"):
        ideastore.write_build(NAME, 1, result("build", 2))
    for empty in ("", "   \n", None):
        with pytest.raises(ValueError, match="reason"):
            ideastore.write_reason(NAME, 1, empty)
    for n in (0, 6, 7, -1, True, "1", 1.0, None):
        with pytest.raises(ValueError, match="1 to 5"):
            ideastore.write_reason(NAME, n, "one more try")
        with pytest.raises(ValueError, match="1 to 5"):
            ideastore.write_build(NAME, n, result("build", 2))
    assert not (ideas_root / NAME / "rounds").exists() and ideastore.rounds(NAME) == []
    build(1, fail=("2.2",))
    with pytest.raises(ValueError, match="round 1 has its result"):              # the reason was written BEFORE
        ideastore.write_reason(NAME, 1, "a better story, after the fact")
    assert (ideas_root / NAME / "rounds/1/reason.txt").read_text() == "reason of round 1\n"
    for n in range(2, 6):
        build(n, fail=("2.2",))
    assert ideastore.rounds(NAME) == [1, 2, 3, 4, 5]


# ---------------------------------------------------------------- the status, from saved results only

def test_a_new_idea_is_an_idea_and_a_card_or_a_code_check_does_not_change_that():
    ideastore.create(NAME)
    assert ideastore.status(NAME) == "idea"
    ideastore.write_card(NAME, CARD)
    ideastore.write_spec(NAME, SPEC)
    ideastore.write_check(NAME, result("code-check", 1))
    assert ideastore.status(NAME) == "idea"


def test_a_lead_is_every_build_line_passed_in_the_latest_round():
    ideastore.create(NAME)
    build(1, fail=("2.2", "2.4"))
    assert ideastore.status(NAME) == "idea"
    build(2)
    assert ideastore.status(NAME) == "lead"            # 2.7 does not apply (no filter): that is not a failure
    ideastore.write_reason(NAME, 3, "a round that has not run yet")
    assert ideastore.status(NAME) == "lead"            # the latest FINISHED round decides


@pytest.mark.parametrize("flaw", [{"fail": ("2.3",)}, {"drop": ("2.9",)}, {"dry_run": True}, {"ok": False},
                                  {"job": {"id": "j1", "state": "running", "progress": "table 3/12"}},
                                  {"na": tuple(f"2.{i}" for i in range(1, 10))}, {"lines": "2.1 PASS"}])
def test_a_build_that_is_not_a_whole_pass_is_not_a_lead(flaw):
    ideastore.create(NAME)
    build(1, **flaw)
    assert ideastore.status(NAME) == "idea"


def test_a_line_passes_only_when_it_says_true():
    ideastore.create(NAME)
    said = [{**ln, "passed": "yes"} if ln["line"] == "2.4" else ln for ln in lines(2, na=("2.7",))]
    build(1, lines=said)
    assert ideastore.status(NAME) == "idea"
    twice = lines(2, na=("2.7",)) + [{"line": "2.6", "passed": False, "text": "2.6 FAIL short side -$410"}]
    build(2, lines=twice)                              # a line reported twice (long, short): both must hold
    assert ideastore.status(NAME) == "idea"


def test_not_passed_after_round_five_is_shelved():
    ideastore.create(NAME)
    for n in range(1, 5):
        build(n, fail=("2.1",))
        assert ideastore.status(NAME) == "idea"
    build(5, fail=("2.1",))
    assert ideastore.status(NAME) == "shelved"


def test_proven_on_history_is_a_lead_with_every_test_line_passed():
    ideastore.create(NAME)
    ideastore.write_test(NAME, result("test", 4))
    assert ideastore.status(NAME) == "idea"                       # a test without a passed build proves nothing
    build(1)
    assert ideastore.status(NAME) == "proven_on_history"
    ideastore.write_test(NAME, result("test", 4, job={"id": "j2", "state": "running", "progress": ""}))
    assert ideastore.status(NAME) == "lead"                       # the read is still running
    ideastore.write_test(NAME, result("test", 4, drop=("4.7",)))
    assert ideastore.status(NAME) == "shelved"
    ideastore.write_test(NAME, result("test", 4, fail=("4.5",)))
    assert ideastore.status(NAME) == "shelved"                    # NOT PROVEN: never re-tuned and re-tested


def test_proven_live_needs_the_lines_that_are_read_on_live_trades():
    ideastore.create(NAME)
    build(1)
    ideastore.write_test(NAME, result("test", 4))
    ideastore.write_eval(NAME, result("eval-card", 6, na=("6.4", "6.5", "6.6", "6.8")))      # stage B not read yet
    assert ideastore.status(NAME) == "proven_on_history"
    ideastore.write_eval(NAME, result("eval-card", 6, fail=("6.2",), na=("6.6", "6.8")))
    assert ideastore.status(NAME) == "proven_on_history"
    ideastore.write_eval(NAME, result("eval-card", 6, na=("6.6", "6.8")))                    # no pause, no bust
    assert ideastore.status(NAME) == "proven_live"


@pytest.mark.parametrize("where", WHERE)
def test_an_early_look_never_proves_an_idea_and_never_shelves_it(where):
    """The owner's decision of 2026-10-06: the test days may be looked at for an idea that is not locked. That
    result says "early_look": true and never counts, wherever it is saved: the idea keeps the status its build
    gives it."""
    ideastore.create(NAME)
    early(where)                                                  # every 4.x line passed
    assert ideastore.status(NAME) == "idea"
    build(1, fail=("2.2",))
    assert ideastore.status(NAME) == "idea"
    build(2)
    assert ideastore.status(NAME) == "lead"                       # a lead, not proven on history
    ideastore.write_eval(NAME, result("eval-card", 6, na=("6.6", "6.8")))
    assert ideastore.status(NAME) == "lead"                       # ... and nothing later stands on it
    early(where, fail=("4.5",))
    assert ideastore.status(NAME) == "lead"                       # an early look that failed shelves nothing
    for n in (3, 4, 5):
        build(n, fail=("2.1",))
    assert ideastore.status(NAME) == "shelved"                    # the build's own word, as without the early look


@pytest.mark.parametrize("where", WHERE)
def test_a_later_test_that_is_not_an_early_look_counts_as_any_test_does(where):
    ideastore.create(NAME)
    build(1)
    early(where)
    assert ideastore.status(NAME) == "lead" and ideastore.read_idea(NAME)["early_look"] is True
    second = {"second_look": True, "label": "SECOND LOOK"}        # the toolkit's own: the days were read before
    ideastore.write_test(NAME, result("test", 4, **second))
    got = ideastore.read_idea(NAME)
    assert (got["status"], got["phase"]) == ("proven_on_history", 4)
    assert got["early_look"] is (where != "test.json")            # kept in its own folder, it is still on file
    ideastore.write_test(NAME, result("test", 4, fail=("4.5",), **second, early_look=False))
    assert ideastore.status(NAME) == "shelved"                    # NOT PROVEN, as today


@pytest.mark.parametrize("where", WHERE)
def test_idea_json_says_an_early_look_is_on_file_and_goes_on_following_the_build(where, ideas_root):
    compact = lambda phase, **kw: [{"line": x["line"], "passed": x["passed"], "text": x["text"]}   # noqa: E731
                                   for x in lines(phase, **kw)]
    ideastore.create(NAME)
    build(1, fail=("2.2",))
    assert ideastore.read_idea(NAME)["early_look"] is False
    early(where, next="after the early look")
    got = ideastore.read_idea(NAME)
    assert (got["status"], got["phase"], got["round"], got["early_look"]) == ("idea", 2, 1, True)
    assert got["lines"] == compact(2, fail=("2.2",), na=("2.7",)) and got["next"] == "after build"
    build(2)                                                      # the build goes on, and so does its record
    got = ideastore.read_idea(NAME)
    assert (got["status"], got["phase"], got["round"], got["early_look"]) == ("lead", 2, 2, True)
    assert got["lines"] == compact(2, na=("2.7",)) and got == json.loads((ideas_root / NAME / "idea.json").read_text())
    ideastore.write_lock(NAME, {"hash": LOCK})                    # the idea's own lock: the early look's is not it
    assert ideastore.read_idea(NAME)["phase"] == 3
    log = [json.loads(x) for x in (ideas_root / NAME / "log.jsonl").read_text().splitlines()]
    assert [(x["was"], x["now"]) for x in log if x["event"] == "status"] == [("idea", "lead")]


def test_an_early_look_is_a_result_that_says_so_and_its_own_lock_is_not_the_ideas():
    ideastore.create(NAME)
    build(1)
    p = early("early_look/test.json")
    assert ideastore.read_idea(NAME)["phase"] == 2                # early_look/lock.json is on file: the idea is not locked
    p.write_text("{torn")                                         # a result that does not read is not on file
    assert ideastore.refresh(NAME)["early_look"] is False
    p.write_text(json.dumps(result("test", 4)))                   # ... and it is the result that says what it is
    assert ideastore.refresh(NAME)["early_look"] is False and ideastore.status(NAME) == "lead"


def test_the_status_written_in_idea_json_is_never_taken_on_trust(ideas_root):
    ideastore.create(NAME)
    p = ideas_root / NAME / "idea.json"
    p.write_text(json.dumps({**json.loads(p.read_text()), "status": "proven_live"}))
    assert ideastore.status(NAME) == "idea"
    assert ideastore.refresh(NAME)["status"] == "idea" and json.loads(p.read_text())["status"] == "idea"


def test_a_field_another_hand_keeps_in_idea_json_survives_but_never_one_read_off_the_results(ideas_root):
    """The toolkit may keep fields of its own in idea.json: a refresh rewrites what it derives and nothing else."""
    ideastore.create(NAME)
    p = ideas_root / NAME / "idea.json"
    p.write_text(json.dumps({**json.loads(p.read_text()), "version": 2, "job": "job-7", "phase": 6, "round": 4,
                             "lines": [{"line": "4.1", "passed": True, "text": "4.1 PASS"}], "next": "buy the eval",
                             "early_look": True}))
    build(1)
    got = ideastore.read_idea(NAME)
    assert (got["version"], got["job"]) == (2, "job-7")
    assert (got["status"], got["phase"], got["round"], got["next"]) == ("lead", 2, 1, "after build")
    assert got["early_look"] is False
    assert [x["line"] for x in got["lines"]] == [f"2.{i}" for i in range(1, 10)]


def test_a_saved_file_that_does_not_read_counts_as_not_saved(ideas_root):
    ideastore.create(NAME)
    build(1)
    (ideas_root / NAME / "rounds/1/build.json").write_text("{torn")
    assert ideastore.status(NAME) == "idea" and ideastore.refresh(NAME)["lines"] == []


# ---------------------------------------------------------------- idea.json, the list, the log

def test_idea_json_follows_what_is_saved(ideas_root):
    created = ideastore.create(NAME)["created"]
    compact = lambda phase, **kw: [{"line": x["line"], "passed": x["passed"], "text": x["text"]}   # noqa: E731
                                   for x in lines(phase, **kw)]
    ideastore.write_card(NAME, CARD)
    ideastore.write_spec(NAME, SPEC)
    assert ideastore.read_idea(NAME)["phase"] == 0
    ideastore.write_check(NAME, result("code-check", 1))
    got = ideastore.read_idea(NAME)
    assert (got["phase"], got["round"], got["lines"], got["next"]) == (1, None, compact(1), "after code-check")
    ideastore.write_reason(NAME, 1, "the plain idea")
    got = ideastore.read_idea(NAME)
    assert (got["status"], got["phase"], got["round"], got["lines"]) == ("idea", 2, 1, compact(1))
    ideastore.write_build(NAME, 1, result("build", 2, na=("2.7",)))
    got = ideastore.read_idea(NAME)
    assert (got["status"], got["phase"], got["round"]) == ("lead", 2, 1)
    assert got["lines"] == compact(2, na=("2.7",)) and got["next"] == "after build"
    ideastore.write_lock(NAME, {"hash": LOCK})
    got = ideastore.read_idea(NAME)
    assert (got["status"], got["phase"], got["lines"]) == ("lead", 3, compact(2, na=("2.7",)))
    ideastore.write_test(NAME, result("test", 4))
    assert (ideastore.read_idea(NAME)["status"], ideastore.read_idea(NAME)["phase"]) == ("proven_on_history", 4)
    ideastore.write_sim(NAME, ACCOUNT, result("sim", 5))
    got = ideastore.read_idea(NAME)
    assert (got["phase"], got["lines"], got["next"]) == (5, compact(5), "after sim")
    ideastore.write_eval(NAME, result("eval-card", 6, na=("6.6", "6.8")))
    got = ideastore.read_idea(NAME)
    assert (got["status"], got["phase"], got["round"]) == ("proven_live", 6, 1) and got["created"] == created
    assert got == json.loads((ideas_root / NAME / "idea.json").read_text())


def test_run_ids_are_kept_with_the_idea():
    ideastore.create(NAME)
    rid = "20261006-010203-draft_nq_orb_pre-abcd"
    assert ideastore.add_run(NAME, rid)["runs"] == [rid]
    assert ideastore.add_run(NAME, rid)["runs"] == [rid]                  # once
    build(1)
    assert ideastore.read_idea(NAME)["runs"] == [rid] and ideastore.read_idea(NAME)["status"] == "lead"
    for bad in ("", None, 7, "a\nb"):
        with pytest.raises(ValueError):
            ideastore.add_run(NAME, bad)


def test_list_ideas_reads_every_idea_and_nothing_else(ideas_root):
    assert ideastore.list_ideas() == [] and ideastore.list_ideas(ideas_root / "nowhere") == []
    for n in ("zz_last", "aa_first"):
        ideastore.create(n)
    ideastore.claim_read("aa_first", version=1, lock=LOCK, rng=RANGE)     # the read log sits beside the ideas
    (ideas_root / "Not An Idea").mkdir()
    (ideas_root / "no_json_here").mkdir()
    (ideas_root / "torn_json").mkdir()
    (ideas_root / "torn_json" / "idea.json").write_text("{torn")
    got = ideastore.list_ideas()
    assert [i["name"] for i in got] == ["aa_first", "zz_last"] and got[0] == ideastore.read_idea("aa_first")


def test_the_log_is_one_json_line_per_event_and_a_change_of_status_is_logged(ideas_root):
    ideastore.create(NAME)
    rec = ideastore.append_log(NAME, "note", text="started", n=1)
    build(1)
    build(2, fail=("2.1",))
    log = [json.loads(x) for x in (ideas_root / NAME / "log.jsonl").read_text().splitlines()]
    assert log[0]["event"] == "created" and log[1] == rec == {"utc": rec["utc"], "event": "note", "text": "started", "n": 1}
    changes = [(x["was"], x["now"]) for x in log if x["event"] == "status"]
    assert changes == [("idea", "lead"), ("lead", "idea")]
    assert all(x["utc"].endswith("+00:00") for x in log)


# ---------------------------------------------------------------- the one-read log

def reads_file(ideas_root) -> Path:
    return ideas_root / "test_reads.jsonl"


def test_a_claimed_read_is_one_line_and_is_found_by_name_version_or_lock(ideas_root):
    assert ideastore.read_on_file(NAME) is None and not reads_file(ideas_root).exists()
    rec = ideastore.claim_read(NAME, version=1, lock=LOCK, rng=RANGE)
    assert rec == {"utc": rec["utc"], "name": NAME, "version": 1, "lock": LOCK, "range": RANGE, "state": "claimed",
                   "verdict": None}
    assert [json.loads(x) for x in reads_file(ideas_root).read_text().splitlines()] == [rec] == ideastore.reads()
    for found in (ideastore.read_on_file(NAME), ideastore.read_on_file(NAME, version=1),
                  ideastore.read_on_file(NAME, lock=LOCK), ideastore.read_on_file(NAME, version=1, lock=LOCK)):
        assert found == rec
    for missing in (ideastore.read_on_file("another_idea"), ideastore.read_on_file(NAME, version=2),
                    ideastore.read_on_file(NAME, lock="0000"), ideastore.read_on_file(NAME, version=1, lock="0000")):
        assert missing is None


def test_the_test_days_are_read_once(ideas_root):
    ideastore.claim_read(NAME, version=1, lock=LOCK, rng=RANGE)
    with pytest.raises(ideastore.ReadOnFile, match="already on file"):
        ideastore.claim_read(NAME, version=1, lock=LOCK, rng=RANGE)
    with pytest.raises(ideastore.ReadOnFile):                              # a changed rule does not buy a new read
        ideastore.claim_read(NAME, version=2, lock="77aa", rng=RANGE)
    with pytest.raises(ideastore.ReadOnFile):                              # ... and a second look is never the SAME lock
        ideastore.claim_read(NAME, version=1, lock=LOCK, rng=RANGE, second_look=True)
    assert len(ideastore.reads()) == 1
    again = ideastore.claim_read(NAME, version=2, lock="77aa", rng=RANGE, second_look=True)
    assert again["second_look"] is True and len(ideastore.reads()) == 2
    assert ideastore.claim_read("another_idea", version=1, lock=LOCK, rng=RANGE)["name"] == "another_idea"
    assert isinstance(ideastore.ReadOnFile("x"), ValueError)


def test_the_verdict_is_a_second_line_and_the_latest_line_answers(ideas_root):
    ideastore.claim_read(NAME, version=1, lock=LOCK, rng=RANGE)
    before = reads_file(ideas_root).read_bytes()
    done = ideastore.log_read(NAME, version=1, lock=LOCK, rng=RANGE, state="judged", verdict="NOT PROVEN")
    assert reads_file(ideas_root).read_bytes().startswith(before)          # appended: nothing earlier is rewritten
    assert ideastore.read_on_file(NAME) == done and done["state"] == "judged" and done["verdict"] == "NOT PROVEN"
    assert [r["state"] for r in ideastore.reads()] == ["claimed", "judged"]
    with pytest.raises(ValueError, match="claimed or judged"):
        ideastore.log_read(NAME, version=1, lock=LOCK, rng=RANGE, state="maybe")
    with pytest.raises(ValueError):
        ideastore.claim_read("Bad Name", version=1, lock=LOCK, rng=RANGE)


def test_every_line_is_written_under_a_lock_and_synced_to_disk(ideas_root, monkeypatch):
    locks, syncs = [], []
    real_flock, real_fsync = fcntl.flock, os.fsync
    monkeypatch.setattr(ideastore.fcntl, "flock", lambda fh, op: (locks.append(op), real_flock(fh, op))[1])
    monkeypatch.setattr(ideastore.os, "fsync", lambda fd: (syncs.append(fd), real_fsync(fd))[1])
    ideastore.claim_read(NAME, version=1, lock=LOCK, rng=RANGE)
    assert locks == [fcntl.LOCK_EX] and len(syncs) == 1
    ideastore.log_read(NAME, version=1, lock=LOCK, rng=RANGE, state="judged", verdict="PROVEN ON HISTORY")
    assert locks == [fcntl.LOCK_EX] * 2 and len(syncs) == 2


def test_only_one_of_many_claims_at_once_gets_the_read(ideas_root):
    won, lost, go = [], [], threading.Event()

    def claim():
        go.wait()
        try:
            won.append(ideastore.claim_read(NAME, version=1, lock=LOCK, rng=RANGE))
        except ideastore.ReadOnFile:
            lost.append(1)

    threads = [threading.Thread(target=claim) for _ in range(8)]
    for t in threads:
        t.start()
    go.set()
    for t in threads:
        t.join(10)
    assert (len(won), len(lost)) == (1, 7)
    assert len(reads_file(ideas_root).read_text().splitlines()) == 1


@pytest.mark.parametrize("torn", ['{"name": "nq_orb', "[1, 2]", "not json at all"])
def test_a_read_log_that_does_not_read_is_refused_never_read_as_empty(torn, ideas_root):
    ideastore.claim_read("another_idea", version=1, lock=LOCK, rng=RANGE)
    with open(reads_file(ideas_root), "a", encoding="utf-8") as f:
        f.write(torn + "\n")
    was = reads_file(ideas_root).read_bytes()
    for refused in (lambda: ideastore.read_on_file(NAME), ideastore.reads,
                    lambda: ideastore.claim_read(NAME, version=1, lock=LOCK, rng=RANGE)):
        with pytest.raises(ideastore.ReadLogUnreadable, match="test_reads.jsonl"):
            refused()
    assert reads_file(ideas_root).read_bytes() == was
    assert isinstance(ideastore.ReadLogUnreadable("x"), ValueError)


# ---------------------------------------------------------------- the record on top of the Lab draft

def carded():
    ideastore.create(NAME)
    ideastore.write_card(NAME, CARD)
    ideastore.write_spec(NAME, SPEC)


def test_an_idea_without_a_draft_gets_a_record_draft(drafts_dir):
    carded()
    p = ideastore.write_draft_block(NAME)
    text = p.read_text(encoding="utf-8")
    assert p == drafts_dir / f"{NAME}.py" and sorted(x.name for x in drafts_dir.iterdir()) == [f"{NAME}.py"]
    head = text.splitlines()
    assert head[0].startswith(ideastore.BLOCK_START) and head[1] == f"# {NAME} · IDEA · phase 0"
    assert ideastore.BLOCK_END in head and all(ln.startswith("#") for ln in head[:head.index(ideastore.BLOCK_END) + 1])
    for line in CARD.splitlines():
        assert f"#   {line}" in head
    draftstore.check_source(text)                              # a draft the Lab lists: it reads, and it is one class
    meta = draftstore.static_meta(text)
    assert meta["root"] == "GC" and NAME in meta["name"] and "record" in meta["doc"].lower()   # the card's market


def test_the_record_draft_falls_back_to_nq_when_the_card_names_no_single_market(drafts_dir):
    ideastore.create(NAME)
    ideastore.write_spec(NAME, {**SPEC, "card": {**SPEC["card"], "home": {"market": "all", "session": "all", "bar": "all"}}})
    assert draftstore.static_meta(ideastore.write_draft_block(NAME).read_text())["root"] == "NQ"
    ideastore.create("no_spec_yet")
    assert draftstore.static_meta(ideastore.write_draft_block("no_spec_yet").read_text())["root"] == "NQ"


def test_the_block_goes_on_top_of_a_draft_and_the_code_below_is_untouched(drafts_dir, monkeypatch):
    carded()
    draftstore.write(NAME, draftstore.DRAFT_TEMPLATE)
    p = ideastore.write_draft_block(NAME)
    first = p.read_text(encoding="utf-8")
    block = ideastore.draft_block(NAME)
    assert first == block + draftstore.DRAFT_TEMPLATE and "LATEST VERDICT" not in block
    build(1, fail=("2.2",))
    ideastore.write_draft_block(NAME)
    second = p.read_text(encoding="utf-8")
    block = ideastore.draft_block(NAME)
    assert second == block + draftstore.DRAFT_TEMPLATE and second.count(ideastore.BLOCK_START) == 1
    head = block.splitlines()
    assert head[1] == f"# {NAME} · IDEA · phase 2 · round 1" and "#   2.2 FAIL words about 2.2" in head
    assert "#   2.1 PASS words about 2.1" in head and "# NEXT: after build" in head
    build(2)
    ideastore.write_draft_block(NAME)
    third = p.read_text(encoding="utf-8")
    assert third.splitlines()[1] == f"# {NAME} · LEAD · phase 2 · round 2" and third.endswith(draftstore.DRAFT_TEMPLATE)
    assert "2.2 FAIL" not in third                             # the LATEST verdict, not a history
    draftstore.check_source(third)
    assert draftstore.static_meta(third)["class"] == "MyDraft"
    # nothing new to say: the file is left alone (no write, so the Lab's catalog is not re-read for nothing)
    writes = []
    monkeypatch.setattr(ideastore.draftstore, "write", lambda *a, **k: writes.append(a))
    assert ideastore.write_draft_block(NAME) == p and writes == []


def test_no_card_text_can_break_the_draft(drafts_dir):
    ideastore.create(NAME)
    ideastore.write_card(NAME, 'tricky """ \'\'\' \\ \x00 \x0c one\rtwo three\n' + ideastore.BLOCK_END + "\nimport os\n")
    draftstore.write(NAME, draftstore.DRAFT_TEMPLATE)
    for _ in range(2):
        text = ideastore.write_draft_block(NAME).read_text(encoding="utf-8")
        draftstore.check_source(text)
        assert text.endswith(draftstore.DRAFT_TEMPLATE) and text.count("\n" + ideastore.BLOCK_END + "\n") == 1
        assert "\x00" not in text and "\nimport os\n" not in text
        assert f"#   {ideastore.BLOCK_END}" in text.splitlines() and "#   import os" in text.splitlines()


def test_a_block_someone_broke_is_left_where_it_is(drafts_dir):
    carded()
    broken = ideastore.BLOCK_START + " an old block whose end line was deleted\n# old words\n" + draftstore.DRAFT_TEMPLATE
    (drafts_dir / f"{NAME}.py").write_text(broken, encoding="utf-8")
    text = ideastore.write_draft_block(NAME).read_text(encoding="utf-8")
    assert text == ideastore.draft_block(NAME) + broken        # a new block on top; not one character is lost


def test_a_draft_that_does_not_read_is_never_written_over(drafts_dir):
    carded()
    (drafts_dir / f"{NAME}.py").write_text("def broken(:\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SyntaxError"):
        ideastore.write_draft_block(NAME)
    assert (drafts_dir / f"{NAME}.py").read_text() == "def broken(:\n"


def test_a_moved_idea_folder_never_writes_the_real_lab(ideas_root, drafts_dir, tmp_path, monkeypatch, home):
    """Moving the idea folder (a test, a trial run) does not move the Lab's drafts with it. Unless they are told
    where to go too, nothing of the Lab is written -- the real ~/.homebase/strategies least of all."""
    carded()
    monkeypatch.delenv(draftstore.ENV)                          # the drafts dir is now the real one's default
    with pytest.raises(ValueError, match="HOMEBASE_DRAFTS_DIR"):
        ideastore.write_draft_block(NAME)
    got = ideastore.sync(NAME)                                  # said, never raised -- and nothing written
    assert got["filed"] is None and len(got["notes"]) == 1 and "HOMEBASE_DRAFTS_DIR" in got["notes"][0]
    assert got["idea"]["status"] == "idea" and list(drafts_dir.iterdir()) == []
    lab = tmp_path / "lab"                                      # told where: an argument (or the environment)
    assert ideastore.write_draft_block(NAME, drafts=lab) == lab / f"{NAME}.py"
    assert ideastore.sync(NAME, drafts=lab)["filed"] == "Ideas"
    assert sorted(x.name for x in lab.iterdir()) == ["groups.json", f"{NAME}.py"]
    monkeypatch.delenv(ideastore.ENV)                           # the app's own idea folder: the app's own Lab
    assert ideastore.lab_dir() == home / ".homebase" / "strategies" == draftstore.drafts_dir()   # named, not written
    monkeypatch.setenv(draftstore.ENV, str(drafts_dir))
    assert ideastore.lab_dir() == ideastore.lab_dir(ideas_root) == drafts_dir and ideastore.lab_dir(drafts=lab) == lab


# ---------------------------------------------------------------- the Lab group follows the status

def on_disk(drafts_dir) -> dict:
    return json.loads((drafts_dir / "groups.json").read_text(encoding="utf-8"))


def test_each_status_has_its_group():
    assert [ideastore.group_for(s) for s in ideastore.STATUSES] == ["Ideas", "Leads", "Proven on history",
                                                                     "Proven live", "Shelved"]
    assert ideastore.STATUSES == ("idea", "lead", "proven_on_history", "proven_live", "shelved")
    for g in ideastore.GROUPS.values():
        assert draftstore.validate_group(g) == g
    with pytest.raises(ValueError):
        ideastore.group_for("retired")


def test_sync_files_the_draft_under_its_status_and_moves_it_when_the_status_changes(drafts_dir):
    carded()
    got = ideastore.sync(NAME)
    assert got["filed"] == "Ideas" and got["notes"] == [] and got["idea"]["group"] == "Ideas"
    assert (drafts_dir / f"{NAME}.py").is_file()                           # the record draft it files
    assert on_disk(drafts_dir) == {"groups": ["Ideas"], "members": {SID: "Ideas"}}
    assert ideastore.read_idea(NAME)["group"] == "Ideas"
    build(1)
    got = ideastore.sync(NAME)
    assert got["filed"] == "Leads" and got["idea"]["status"] == "lead"
    assert on_disk(drafts_dir) == {"groups": ["Ideas", "Leads"], "members": {SID: "Leads"}}
    assert (drafts_dir / f"{NAME}.py").read_text().splitlines()[1] == f"# {NAME} · LEAD · phase 2 · round 1"
    ideastore.write_test(NAME, result("test", 4, fail=("4.1",)))
    assert ideastore.sync(NAME)["filed"] == "Shelved" and on_disk(drafts_dir)["members"] == {SID: "Shelved"}
    assert sorted(x.name for x in drafts_dir.iterdir()) == ["groups.json", f"{NAME}.py"]


@pytest.mark.parametrize("where", WHERE)
def test_an_early_look_moves_no_group_and_the_block_says_it_is_on_file(where, drafts_dir):
    carded()
    build(1)
    ideastore.sync(NAME)
    early(where)
    got = ideastore.sync(NAME)
    assert got["filed"] is None and got["notes"] == [] and got["idea"]["status"] == "lead"
    assert on_disk(drafts_dir) == {"groups": ["Leads"], "members": {SID: "Leads"}}
    head = (drafts_dir / f"{NAME}.py").read_text(encoding="utf-8").splitlines()
    assert head[1] == f"# {NAME} · LEAD · phase 2 · round 1 · EARLY LOOK on file"
    assert "#   2.1 PASS words about 2.1" in head and "#   4.1 PASS words about 4.1" not in head   # the build's verdict
    ideastore.write_test(NAME, result("test", 4))                          # a test that counts: as today
    assert ideastore.sync(NAME)["filed"] == "Proven on history"
    head = (drafts_dir / f"{NAME}.py").read_text(encoding="utf-8").splitlines()
    still = " · EARLY LOOK on file" if where != "test.json" else ""        # kept in its own folder, it stays on file
    assert head[1] == f"# {NAME} · PROVEN ON HISTORY · phase 4 · round 1{still}"
    assert "#   4.1 PASS words about 4.1" in head


def test_sync_leaves_the_lab_alone_while_the_status_stays(drafts_dir):
    carded()
    ideastore.sync(NAME)
    draftstore.set_group(SID, "Gold ideas")                                # the owner files it somewhere else
    stamp = (drafts_dir / "groups.json").stat().st_mtime_ns
    got = ideastore.sync(NAME)
    assert got["filed"] is None and got["notes"] == []
    assert on_disk(drafts_dir)["members"] == {SID: "Gold ideas"} and (drafts_dir / "groups.json").stat().st_mtime_ns == stamp
    build(1)                                                               # a new status moves it again
    assert ideastore.sync(NAME)["filed"] == "Leads" and on_disk(drafts_dir)["members"] == {SID: "Leads"}


def test_sync_uses_the_group_that_exists_whatever_its_capitals(drafts_dir):
    draftstore.add_group("ideas")
    draftstore.set_group("nq930", "ideas")
    carded()
    assert ideastore.sync(NAME)["filed"] == "ideas"
    assert on_disk(drafts_dir) == {"groups": ["ideas"], "members": {"nq930": "ideas", SID: "ideas"}}


def test_a_groups_file_that_does_not_read_is_reported_and_never_stops_the_idea(drafts_dir):
    (drafts_dir / "groups.json").write_text("{not json")
    carded()
    build(1)
    got = ideastore.sync(NAME)                                             # no exception: the phase is never failed for it
    assert got["filed"] is None and got["idea"]["status"] == "lead" and got["idea"]["group"] is None
    assert len(got["notes"]) == 1 and "groups.json" in got["notes"][0]
    assert (drafts_dir / "groups.json").read_text() == "{not json"         # never written over
    assert (drafts_dir / f"{NAME}.py").read_text().splitlines()[1] == f"# {NAME} · LEAD · phase 2 · round 1"
    (drafts_dir / "groups.json").unlink()                                  # once the file is fixed, the next sync files it
    assert ideastore.sync(NAME)["filed"] == "Leads" and on_disk(drafts_dir)["members"] == {SID: "Leads"}


def test_a_draft_that_cannot_be_written_is_reported_and_nothing_is_filed(drafts_dir):
    carded()
    (drafts_dir / f"{NAME}.py").write_text("def broken(:\n", encoding="utf-8")
    got = ideastore.sync(NAME)
    assert got["filed"] is None and len(got["notes"]) == 1 and "SyntaxError" in got["notes"][0]
    assert got["idea"]["status"] == "idea" and not (drafts_dir / "groups.json").exists()
