"""LOCK of the switch (blueprint/pipe_switch.py; the owner, 2026-10-13: "let me switch on and off each pipeline, so i can either have one
on and i pick which or none on").

1. ONE pipeline works, or none: now() is read off the disk -- the queue's pause file, the payout flag, the profile in use.
2. choose() of a profile puts that profile in use and lets the queue work; "off" pauses it; a word that is none is refused.
3. The payout pipeline is listed, not ready: it cannot be chosen until its runner is built, and nothing changes when it is asked for.
4. A pause put by hand (`pipe pause`) reads "off"; a resume by hand reads the profile again.
5. `pipe list` carries the choice and the choices; `pipe mode` shows it and chooses it.
A temp folder each test. No engine, no tape, no runner is started.

  pytest tests/test_pipe_switch.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
import judge as J  # noqa: E402
import test_blueprint_ideas as TI  # noqa: E402
from blueprint import pipe_rules as PR  # noqa: E402
from blueprint import pipe_runner as PRN  # noqa: E402
from blueprint import pipe_store as PS  # noqa: E402
from blueprint import pipe_switch as SW  # noqa: E402


@pytest.fixture()
def root(tmp_path, monkeypatch):
    monkeypatch.setenv(PS.ENV, str(tmp_path / "env_root"))
    monkeypatch.delenv("HB_PIPELINE")                # the choice is the state file's here, as on the owner's machine
    r = tmp_path / "pipeline"
    r.mkdir()
    return r


def run(argv: list) -> tuple:
    rc, out = TI._run([*argv, "--json"], "")
    return rc, json.loads(out)


def test_nothing_chosen_reads_the_live_pipeline(root):
    assert SW.now(root) == "live"


def test_a_profile_is_put_in_use_and_the_queue_works(root):
    PS.pause(root)
    assert SW.choose("wr", root) == "wr" and PR.active() == "wr" and not PS.paused(root)
    assert SW.choose("live", root) == "live" and PR.active() == "live" and not PS.paused(root)


def test_off_pauses_the_queue_and_keeps_the_profile(root):
    SW.choose("wr", root)
    assert SW.choose("off", root) == "off" and PS.paused(root) and PR.active() == "wr"
    assert SW.choose("wr", root) == "wr" and not PS.paused(root)


def test_a_pause_by_hand_reads_off_and_a_resume_reads_the_profile(root):
    PS.pause(root)
    assert SW.now(root) == "off"
    PS.resume(root)
    assert SW.now(root) == "live"


def test_a_word_that_is_none_is_refused_and_nothing_changes(root):
    with pytest.raises(J.Refuse, match="off, live, wr, payout"):
        SW.choose("fast", root)
    assert SW.now(root) == "live" and not PS.paused(root)


def test_the_payout_pipeline_is_listed_but_cannot_be_chosen_yet(root):
    assert [(o["id"], o["ready"]) for o in SW.options()] == [("off", True), ("live", True), ("wr", True), ("payout", False)]
    with pytest.raises(J.Refuse, match="not built yet"):
        SW.choose("payout", root)
    assert SW.now(root) == "live" and not PS.paused(root) and not (root / SW.FLAG).exists()


def test_the_payout_flag_reads_payout_only_while_the_queue_is_paused(root):
    (root / SW.FLAG).write_text("")
    assert SW.now(root) == "live"                    # the queue works: it is the one that is on
    PS.pause(root)
    assert SW.now(root) == "payout"
    assert SW.choose("off", root) == "off" and not (root / SW.FLAG).exists()


def test_pipe_list_carries_the_choice_and_the_choices(root):
    SW.choose("off", root)
    got = PRN.listing(root)["pipeline"]
    assert got["mode"] == "off" and [o["id"] for o in got["modes"]] == list(SW.CHOICES)


def test_pipe_mode_shows_and_chooses(root, monkeypatch):
    started = []
    monkeypatch.setattr(PRN, "start", lambda r=None: started.append(r) or {"pid": 1, "already": False})
    rc, got = run(["pipe", "mode", f"--root={root}"])
    assert rc == 0 and got["mode"] == "live" and "LIVE PIPELINE is on" in got["text"] and started == []
    rc, got = run(["pipe", "mode", "off", f"--root={root}"])
    assert rc == 0 and got["mode"] == "off" and "No pipeline is on" in got["text"] and started == []
    rc, got = run(["pipe", "mode", "wr", f"--root={root}"])
    assert rc == 0 and got["mode"] == "wr" and len(started) == 1          # on = working: the runner is started (it says `already` when one is)
    rc, got = run(["pipe", "mode", "payout", f"--root={root}"])
    assert rc != 0 and "not built yet" in json.dumps(got) and SW.now(root) == "wr"
