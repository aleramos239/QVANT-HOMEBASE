"""LOCK of the pipeline's files (blueprint/pipe_store.py) -- pipeline plan A, task 3.

1. The root: the argument, else HOMEBASE_PIPELINE_ROOT, else ~/.homebase/pipeline.
2. add() files a checked card: card.json (with its sub-ideas), state.json "queued", one line on seen.jsonl and one on
   order.jsonl. A name on file is refused; so is a signature already seen, under any name, naming the earlier card.
3. The state: read, changed (always stamped), one change at a time; a status that is none is no change.
4. The queue order: the cards of the inbox first, then by the time they were added; only what is queued or running.
5. Stage cards and the book round-trip; the ledger's path; the pause file.
6. The control pools are LINKED into the pipeline's stores folder, never copied, and nothing there is ever replaced.
   The stores of the one read of the unseen days have a folder of their own (runs_test), with no pool linked in.
7. A write that dies half-way leaves the file as it was.
A temp folder each test: nothing is written under ~/.homebase or in the repo. No engine, no tape. Under a second.

  pytest tests/test_pipe_store.py -q          python tests/test_pipe_store.py     the same, one line per test
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
import judge as J  # noqa: E402
from blueprint import pipe_store as PS  # noqa: E402

CARD = {"name": "fvg_open", "why": "Late buyers chase the first gap after the open.", "loser": "Traders who fade the first move.",
        "source": "owner", "market": "NQ", "session": "nyam", "sides": "both", "sides_why": "",
        "ways": [{"family": "fvg", "main_setting": "min_gap", "values": ["0.1", "0.25", "0.5"], "fixed": {"mode": "touch"}, "limits": {}}],
        "indicators": [{"block": "trend", "side": "with", "why": "A gap with the trend has more room."}]}
SUBS = [{"name": "fvg_open_a1", "way": 0, "bar": "1", "spec": {"name": "fvg_open_a1", "version": 1}},
        {"name": "fvg_open_a5", "way": 0, "bar": "5", "spec": {"name": "fvg_open_a5", "version": 1}}]
STAGE = {"stage": 1, "name": "raw heat map", "passed": True, "result": "low", "lines": [{"line": "P1.1", "passed": True, "number": 0.55, "need": 0.5, "text": "P1.1 PASS"}],
         "text": "low pass", "picked": {"sub": "fvg_open_a5", "bar": "5", "way": 0, "filter": None}, "tries": 2, "rules": {"share": 0.5},
         "utc": "2026-10-08T03:10:00+00:00", "seconds": 1180}
_OWN = {"now": PS._now, "replace": os.replace, "fsync": os.fsync}
TMP = {}


def setup_function(_=None):
    TMP["d"] = Path(tempfile.mkdtemp(prefix="pipe_store_"))
    TMP["env"] = os.environ.get(PS.ENV)
    os.environ[PS.ENV] = str(TMP["d"] / "env_root")              # a call that forgets its root still lands in the temp folder
    TMP["clock"] = [0]


def teardown_function(_=None):
    PS._now, os.replace, os.fsync = _OWN["now"], _OWN["replace"], _OWN["fsync"]
    shutil.rmtree(TMP.pop("d"), ignore_errors=True)
    if TMP.get("env") is None:
        os.environ.pop(PS.ENV, None)
    else:
        os.environ[PS.ENV] = TMP["env"]


def root() -> Path:
    return TMP["d"] / "pipeline"


def ticking():
    """A clock that moves a minute a call: 2026-10-08T03:00, 03:01, ..."""
    def now():
        TMP["clock"][0] += 1
        return f"2026-10-08T03:{TMP['clock'][0] - 1:02d}:00+00:00"
    PS._now = now


def card(name="fvg_open", **more) -> dict:
    return {**CARD, "name": name, **more}


def add(name="fvg_open", sig=None, family="fvg", inbox=False, **more) -> dict:
    return PS.add(card(name, **more), SUBS, root(), inbox=inbox, sig=sig or f"sig-{name}", family=family)


def refused(fn, *words) -> str:
    try:
        fn()
    except J.Refuse as e:
        assert all(w in str(e) for w in words), f"refused, but not for {words!r}: {e}"
        return str(e)
    raise AssertionError(f"not refused ({words})")


def lines(p: Path) -> list:
    return [json.loads(x) for x in p.read_text().splitlines()]


def tree(d: Path) -> list:
    return sorted(str(p.relative_to(d)) for p in d.rglob("*"))


# ================================================================ 1. the root

def test_the_root_is_the_argument_then_the_environment_then_the_apps_folder():
    assert PS.ENV == "HOMEBASE_PIPELINE_ROOT"
    assert PS.root("/x/y") == Path("/x/y") and PS.root(Path("/x/y")) == Path("/x/y")
    assert PS.root() == TMP["d"] / "env_root" and PS.root(None) == TMP["d"] / "env_root"
    os.environ.pop(PS.ENV)
    assert PS.root() == Path.home() / ".homebase" / "pipeline"                 # read, never written by a test
    assert PS.ideas_root(root()) == root() / "ideas" and (root() / "ideas").is_dir()
    assert PS.ideas_root(root()) == root() / "ideas"                           # twice is fine


# ================================================================ 2. add

def test_add_files_the_card_its_state_and_the_two_registry_lines():
    ticking()
    st = add()
    assert st == {"name": "fvg_open", "status": "queued", "stage": None, "stopped_at": None, "why": "", "tries": 0, "picked": None,
                  "added_utc": "2026-10-08T03:00:00+00:00", "updated_utc": "2026-10-08T03:00:00+00:00", "source": "owner", "family": "fvg"}
    d = root() / "p" / "fvg_open"
    assert json.loads((d / "state.json").read_text()) == st == PS.state("fvg_open", root())
    assert json.loads((d / "card.json").read_text()) == {**CARD, "subs": SUBS} == PS.card("fvg_open", root())
    assert (d / "stages").is_dir() and PS.stages("fvg_open", root()) == {}
    assert lines(root() / "seen.jsonl") == [{"sig": "sig-fvg_open", "name": "fvg_open", "utc": "2026-10-08T03:00:00+00:00"}]
    assert lines(root() / "order.jsonl") == [{"name": "fvg_open", "utc": "2026-10-08T03:00:00+00:00", "inbox": False}]
    assert "subs" not in CARD                                                  # the caller's card is not changed
    assert [p for p in tree(root()) if ".tmp" in p] == []                      # no temp file or folder is left
    assert PS.ideas(root()) == [st]
    add("orb_open", family="orb", inbox=True, source="video")
    assert [(s["name"], s["family"], s["source"]) for s in PS.ideas(root())] == [("fvg_open", "fvg", "owner"), ("orb_open", "orb", "video")]
    assert [x["name"] for x in lines(root() / "seen.jsonl")] == ["fvg_open", "orb_open"]
    assert lines(root() / "order.jsonl")[1] == {"name": "orb_open", "utc": "2026-10-08T03:01:00+00:00", "inbox": True}


def test_a_name_on_file_is_refused_and_nothing_is_written():
    ticking()
    add()
    before = {p: (root() / p).read_bytes() for p in tree(root()) if (root() / p).is_file()}
    why = refused(lambda: add(sig="another-signature", why="Another reason altogether, in a sentence."), "fvg_open", "already on file", "2026-10-08T03:00:00+00:00")
    assert "another name" in why
    assert {p: (root() / p).read_bytes() for p in tree(root()) if (root() / p).is_file()} == before
    refused(lambda: PS.add(card("Bad Name"), SUBS, root(), sig="s", family="fvg"), "Bad Name")          # a name that is no folder name
    refused(lambda: PS.add(card("../up"), SUBS, root(), sig="s", family="fvg"), "../up")
    assert not (root().parent / "up").exists() and len(lines(root() / "seen.jsonl")) == 1


def test_a_signature_already_seen_is_refused_under_any_name_and_names_the_earlier_card():
    ticking()
    add(sig="abc123")
    why = refused(lambda: add("fvg_again", sig="abc123"), "fvg_open", "2026-10-08T03:00:00+00:00", "same card")
    assert "fvg_again" in why and not (root() / "p" / "fvg_again").exists()
    assert len(lines(root() / "seen.jsonl")) == 1 and len(lines(root() / "order.jsonl")) == 1
    PS.set_state("fvg_open", root(), status="refused", why="the owner said no")
    refused(lambda: add("fvg_again", sig="abc123"), "fvg_open")                                         # seen for good: whatever became of it
    shutil.rmtree(root() / "p" / "fvg_open")
    refused(lambda: add("fvg_again", sig="abc123"), "fvg_open")                                         # ... and with its folder gone
    assert add("fvg_again", sig="def456")["status"] == "queued"                                         # another signature is another card
    (root() / "seen.jsonl").write_text((root() / "seen.jsonl").read_text() + "not json\n")
    refused(lambda: add("third_one", sig="ghi789"), "seen.jsonl", "line 3")                             # a registry that does not read is never read as "new"
    assert not (root() / "p" / "third_one").exists()


def test_adds_at_the_same_time_never_both_pass_and_every_line_is_whole():
    import threading
    won, lost = [], []

    def one(name, sig):
        try:
            won.append(add(name, sig=sig)["name"])
        except J.Refuse:
            lost.append(name)
    ts = [threading.Thread(target=one, args=(f"same_{i:02d}", "one-signature")) for i in range(8)]
    ts += [threading.Thread(target=one, args=(f"own_{i:02d}", f"sig-{i}")) for i in range(24)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len([n for n in won if n.startswith("same_")]) == 1 and len(lost) == 7          # one signature, eight names: one card
    assert sorted(x["name"] for x in lines(root() / "seen.jsonl")) == sorted(won) and len(won) == 25
    assert sorted(x["name"] for x in lines(root() / "order.jsonl")) == sorted(won) == sorted(PS.order(root()))
    assert sorted(p.name for p in (root() / "p").iterdir()) == sorted(won)                 # no folder of a card that lost, no temp folder

    def bump():
        for _ in range(10):
            with PS._locked(root() / "p" / "own_00"):                          # the lock set_state itself takes: one read-change-write at a time
                pass
            PS.set_state("own_00", root(), status="running")
    ts = [threading.Thread(target=bump) for _ in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert PS.state("own_00", root())["status"] == "running" and [p for p in tree(root()) if ".tmp" in p] == []


# ================================================================ 3. the state

def test_set_state_changes_what_it_is_given_and_always_stamps_the_time():
    ticking()
    add()
    st = PS.set_state("fvg_open", root(), status="running", stage=1, tries=2, picked={"sub": "fvg_open_a5", "bar": "5", "way": 0, "filter": None})
    assert st == PS.state("fvg_open", root()) and (st["status"], st["stage"], st["tries"]) == ("running", 1, 2)
    assert st["picked"]["sub"] == "fvg_open_a5" and st["added_utc"] == "2026-10-08T03:00:00+00:00" and st["updated_utc"] == "2026-10-08T03:01:00+00:00"
    st = PS.set_state("fvg_open", root())                                      # no change: stamped all the same
    assert st["updated_utc"] == "2026-10-08T03:02:00+00:00" and st["status"] == "running"
    st = PS.set_state("fvg_open", root(), status="stopped", stopped_at=2, why="P2.5 FAIL", updated_utc="1999-01-01T00:00:00+00:00")
    assert st["updated_utc"] == "2026-10-08T03:03:00+00:00" and (st["stopped_at"], st["why"]) == (2, "P2.5 FAIL")      # the stamp is the store's
    assert PS.STATUS == ("queued", "running", "stopped", "code_problem", "awaiting_owner", "book", "refused")
    for s in PS.STATUS:
        assert PS.set_state("fvg_open", root(), status=s)["status"] == s
    try:
        PS.set_state("fvg_open", root(), status="done")
        raise AssertionError("a status that is none was taken")
    except ValueError as e:
        assert "done" in str(e)
    assert PS.state("fvg_open", root())["status"] == "refused"                 # ... and changed nothing
    refused(lambda: PS.state("nobody", root()), "nobody")
    refused(lambda: PS.set_state("nobody", root(), status="running"), "nobody")
    refused(lambda: PS.state("../p", root()), "../p")
    assert not (root() / "p" / "nobody").exists()


# ================================================================ 4. the queue order

def test_order_is_the_inbox_first_then_by_the_time_added_and_only_what_is_queued_or_running():
    ticking()
    assert PS.order(root()) == [] and PS.ideas(root()) == []                   # an empty root is an empty queue (and stays unmade)
    for n, box in (("a_first", False), ("b_second", False), ("c_inbox", True), ("d_fourth", False), ("e_inbox", True)):
        add(n, inbox=box)
    assert PS.order(root()) == ["c_inbox", "e_inbox", "a_first", "b_second", "d_fourth"]
    assert [s["name"] for s in PS.ideas(root())] == ["a_first", "b_second", "c_inbox", "d_fourth", "e_inbox"]         # every idea, as added
    PS.set_state("a_first", root(), status="running")
    PS.set_state("c_inbox", root(), status="stopped", stopped_at=1)
    PS.set_state("d_fourth", root(), status="awaiting_owner")
    assert PS.order(root()) == ["e_inbox", "a_first", "b_second"]
    for s in ("code_problem", "book", "refused"):
        PS.set_state("b_second", root(), status=s)
        assert PS.order(root()) == ["e_inbox", "a_first"]
    PS.set_state("b_second", root(), status="queued")
    assert PS.order(root()) == ["e_inbox", "a_first", "b_second"]


def test_order_holds_when_two_cards_share_a_second_and_when_a_line_is_missing():
    PS._now = lambda: "2026-10-08T03:00:00+00:00"
    for n in ("zz_first", "mm_second", "aa_third"):
        add(n)
    assert PS.order(root()) == ["zz_first", "mm_second", "aa_third"]           # the same second: as they were added, not by name
    p = root() / "order.jsonl"
    p.write_text("".join(x + "\n" for x in p.read_text().splitlines() if "zz_first" not in x) + "half a li")
    assert PS.order(root()) == ["mm_second", "aa_third", "zz_first"]           # an idea without its line still gets its turn, last


# ================================================================ 5. stage cards, the book, the ledger, the pause

def test_stage_cards_round_trip():
    add()
    p = PS.write_stage("fvg_open", 1, STAGE, root())
    assert p == root() / "p" / "fvg_open" / "stages" / "1.json" and json.loads(p.read_text()) == STAGE
    PS.write_stage("fvg_open", 0, {"stage": 0, "name": "card", "passed": True}, root())
    PS.write_stage("fvg_open", 10, {"stage": 10, "passed": None}, root())
    got = PS.stages("fvg_open", root())
    assert list(got) == [0, 1, 10] and got[1] == STAGE and got[0]["name"] == "card"      # by number, as numbers
    PS.write_stage("fvg_open", 1, {**STAGE, "result": "strict"}, root())                 # a stage run again replaces its card
    assert PS.stages("fvg_open", root())[1]["result"] == "strict"
    (root() / "p" / "fvg_open" / "stages" / ".1.json.999.tmp").write_text("{half")        # what a killed write leaves is no card
    (root() / "p" / "fvg_open" / "stages" / "notes.txt").write_text("x")
    assert list(PS.stages("fvg_open", root())) == [0, 1, 10]
    refused(lambda: PS.write_stage("nobody", 1, STAGE, root()), "nobody")
    refused(lambda: PS.stages("nobody", root()), "nobody")
    try:
        PS.write_stage("fvg_open", "../../x", STAGE, root())
        raise AssertionError("a stage that is no number was written")
    except ValueError:
        pass


def test_numbers_of_the_toolkit_are_saved_as_plain_json():
    class Number:                                                              # numpy's numbers answer tolist(); the store imports no numpy
        def tolist(self):
            return 0.55
    add()
    PS.write_stage("fvg_open", 1, {"stage": 1, "number": Number(), "where": Path("/x/y")}, root())
    assert PS.stages("fvg_open", root())[1] == {"stage": 1, "number": 0.55, "where": "/x/y"}
    try:
        PS.write_stage("fvg_open", 2, {"stage": 2, "what": object()}, root())
        raise AssertionError("something that is no JSON was written")
    except TypeError:
        pass
    assert list(PS.stages("fvg_open", root())) == [1]


def test_the_book_the_ledger_and_the_pause():
    add()
    assert PS.book(root()) == []
    p = PS.write_book("fvg_open", {"name": "fvg_open", "label": "helper"}, root())
    assert p == root() / "book" / "fvg_open.json" and json.loads(p.read_text()) == {"name": "fvg_open", "label": "helper"}
    PS.write_book("aa_other", {"name": "aa_other", "label": "stands alone"}, root())
    assert [c["name"] for c in PS.book(root())] == ["aa_other", "fvg_open"]
    refused(lambda: PS.write_book("../x", {}, root()), "../x")
    assert PS.ledger("fvg_open", root()) == root() / "p" / "fvg_open" / "ledger.csv" and not PS.ledger("fvg_open", root()).exists()
    refused(lambda: PS.ledger("nobody", root()), "nobody")
    assert PS.paused(root()) is False
    assert PS.pause(root()) is True and PS.paused(root()) is True and (root() / "pause").is_file()
    assert PS.pause(root()) is True                                            # twice is fine
    assert PS.resume(root()) is False and PS.paused(root()) is False and not (root() / "pause").exists()
    assert PS.resume(root()) is False


# ================================================================ 6. the control pools are linked, never copied

def test_the_pools_are_linked_into_the_stores_folder_and_nothing_there_is_replaced():
    pools = TMP["d"] / "runs_bp"
    for k in ("c1-NQ-tf5", "c1-ES-tf1", "c1o-NQ-tf5", "fvg_open-NQ-tf5", "c1x-NQ-tf5", "c10-NQ-tf5"):
        (pools / k).mkdir(parents=True)
        (pools / k / "unit.json").write_text(k)
    (pools / "c1-NQ-tf5.lock").write_text("")                                  # a pool's lock file is no pool
    out = PS.runs(root(), pools=pools)
    assert out == root() / "runs" and sorted(p.name for p in out.iterdir()) == ["c1-ES-tf1", "c1-NQ-tf5", "c1o-NQ-tf5"]
    for k in ("c1-ES-tf1", "c1-NQ-tf5", "c1o-NQ-tf5"):
        assert (out / k).is_symlink() and (out / k).resolve() == (pools / k).resolve() and os.path.isabs(os.readlink(out / k))
        assert (out / k / "unit.json").read_text() == k
    (pools / "c1-NQ-tf5" / "seed9.json").write_text("new")                     # one folder, seen from both sides: a link, not a copy
    assert (out / "c1-NQ-tf5" / "seed9.json").read_text() == "new"
    # what is there stays: a store of the pipeline's own under a pool's name, and a link that points somewhere else
    (pools / "c1-GC-tf5").mkdir()
    (pools / "c1-GC-tf1").mkdir()
    (out / "c1-GC-tf5").mkdir()
    (out / "c1-GC-tf5" / "mine.json").write_text("mine")
    os.symlink(TMP["d"] / "elsewhere", out / "c1-GC-tf1")                      # (a dangling link: still something that is there)
    (out / "fvg_open_a5-NQ-tf5").mkdir()
    assert PS.runs(root(), pools=pools) == out
    assert not (out / "c1-GC-tf5").is_symlink() and (out / "c1-GC-tf5" / "mine.json").read_text() == "mine"
    assert os.readlink(out / "c1-GC-tf1") == str(TMP["d"] / "elsewhere")
    assert (out / "fvg_open_a5-NQ-tf5").is_dir() and len(list(out.iterdir())) == 6
    (pools / "c1o-ES-tf5").mkdir()                                             # a pool made later is linked by the next call
    assert (PS.runs(root(), pools=pools) / "c1o-ES-tf5").is_symlink()
    assert sorted(p.name for p in pools.iterdir() if p.is_dir()) == ["c1-ES-tf1", "c1-GC-tf1", "c1-GC-tf5", "c1-NQ-tf5", "c10-NQ-tf5", "c1o-ES-tf5", "c1o-NQ-tf5",
                                                                     "c1x-NQ-tf5", "fvg_open-NQ-tf5"]
    assert not any(p.is_symlink() for p in pools.iterdir())                    # the real folder is only read


def test_no_pools_folder_is_an_empty_stores_folder_and_the_real_one_is_the_runners():
    out = PS.runs(root(), pools=TMP["d"] / "not_there")
    assert out.is_dir() and list(out.iterdir()) == []
    assert PS.pools() == W / "runs_bp"                                         # the toolkit's own stores folder (runner.RUNS): named, not touched


def test_the_stores_of_the_one_read_have_a_folder_of_their_own_under_the_root():
    out = PS.runs_test(root())
    assert out == root() / "runs_test" and out.is_dir() and list(out.iterdir()) == []         # made, empty: no pool is linked into it
    (out / "fvg_open_a5-NQ-tf5-nyam-test").mkdir()
    assert PS.runs_test(root()) == out and [p.name for p in out.iterdir()] == ["fvg_open_a5-NQ-tf5-nyam-test"]      # again: what is there stays
    assert out != PS.runs(root(), pools=TMP["d"] / "not_there") and out.parent == PS.runs(root(), pools=TMP["d"] / "not_there").parent
    assert out.name != (W / "runs_bp_test").name                                               # never the toolkit's own folder of the reads


# ================================================================ 7. a write that dies leaves the old file

def test_a_write_that_dies_leaves_the_file_as_it_was():
    ticking()
    add()
    PS.write_stage("fvg_open", 1, STAGE, root())
    d = root() / "p" / "fvg_open"
    before = {p: (d / p).read_bytes() for p in ("state.json", "card.json", "stages/1.json")}

    def dies(*a, **k):
        raise OSError("the disk is full")
    for name in ("fsync", "replace"):                                          # before the new file is whole · before it takes the old one's place
        setattr(os, name, dies)
        for write in (lambda: PS.set_state("fvg_open", root(), status="running", stage=1),
                      lambda: PS.write_stage("fvg_open", 1, {**STAGE, "passed": False}, root()),
                      lambda: PS.write_book("fvg_open", {"name": "fvg_open"}, root()),
                      lambda: add("never_added")):
            try:
                write()
                raise AssertionError("the write did not die")
            except OSError as e:
                assert "disk is full" in str(e)
        setattr(os, name, _OWN[name])
        assert {p: (d / p).read_bytes() for p in before} == before
        assert PS.state("fvg_open", root())["status"] == "queued" and PS.stages("fvg_open", root())[1] == STAGE
        assert PS.book(root()) == [] and [s["name"] for s in PS.ideas(root())] == ["fvg_open"] and PS.order(root()) == ["fvg_open"]
        assert [x["name"] for x in lines(root() / "seen.jsonl")] == ["fvg_open"]                 # an add that died was never seen
    assert add("never_added")["status"] == "queued"                            # ... and its name and its card are still free
    assert PS.set_state("fvg_open", root(), status="running")["status"] == "running"


if __name__ == "__main__":
    import time
    rc = 0
    for name, t in [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]:
        t0 = time.monotonic()
        setup_function()
        try:
            t()
            print(f"PASS {name} ({time.monotonic() - t0:.1f} s)", flush=True)
        except AssertionError as e:
            rc = 1
            print(f"FAIL {name}\n{e}", flush=True)
        finally:
            teardown_function()
    sys.exit(rc)
