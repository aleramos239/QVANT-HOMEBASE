"""LOCK of the switch (blueprint/pipe_switch.py). ONE pipeline since 2026-10-18 (the owner): it works, or it does not.

1. now() is read off the disk: the queue's pause file -> "off", else "live".
2. choose("live") lets the queue work; "off" pauses it; a word that is neither (a retired profile among them) is refused and nothing changes.
3. A pause put by hand (`pipe pause`) reads "off"; a resume by hand reads "live" again.
4. `pipe list` carries the choice and the choices; `pipe mode` shows it and chooses it, and starts the runner for live.
5. A retired profile word left on the machine (wr, payout, funded) reads live, and the payout lock file is neither read nor written.
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


def test_live_lets_the_queue_work_and_off_pauses_it(root):
    PS.pause(root)
    assert SW.choose("live", root) == "live" and PR.active() == "live" and not PS.paused(root)
    assert SW.choose("off", root) == "off" and PS.paused(root)
    assert SW.choose("live", root) == "live" and not PS.paused(root)


def test_a_pause_by_hand_reads_off_and_a_resume_reads_live(root):
    PS.pause(root)
    assert SW.now(root) == "off"
    PS.resume(root)
    assert SW.now(root) == "live"


@pytest.mark.parametrize("word", ["fast", "wr", "payout", "funded"])
def test_a_word_that_is_neither_is_refused_and_nothing_changes(root, word):
    with pytest.raises(J.Refuse, match="one of off, live"):
        SW.choose(word, root)
    assert SW.now(root) == "live" and not PS.paused(root)


def test_the_choices_are_off_and_on(root):
    assert [(o["id"], o["short"], o["ready"]) for o in SW.options(root)] == [("off", "Off", True), ("live", "On", True)]
    assert SW.said("off") == "No pipeline is on" and SW.said("live") == "LIVE PIPELINE is on"


@pytest.mark.parametrize("word", ["wr", "payout", "funded"])
def test_a_retired_profile_left_on_the_machine_reads_live(root, word):
    PR.STATE.write_text(word + "\n")
    PR._all.cache_clear()
    assert PR.active() == "live" and SW.now(root) == "live" and PR.gates() == "edge"


def test_the_payout_lock_file_is_neither_read_nor_written(root):
    SW.choose("live", root)
    SW.choose("off", root)
    assert not (root / "payout_enabled").exists() and not hasattr(SW, "enable")


def test_pipe_list_carries_the_choice_and_the_choices(root):
    SW.choose("off", root)
    got = PRN.listing(root)["pipeline"]
    assert got["mode"] == "off" and [o["id"] for o in got["modes"]] == list(SW.CHOICES) and "settings" not in got


def test_pipe_mode_shows_and_chooses_and_starts_the_runner_for_live(root, monkeypatch):
    started = []
    monkeypatch.setattr(PRN, "start", lambda r=None: started.append(r) or {"pid": 1, "already": False})
    rc, got = run(["pipe", "mode", f"--root={root}"])
    assert rc == 0 and got["mode"] == "live" and "LIVE PIPELINE is on" in got["text"] and started == []
    rc, got = run(["pipe", "mode", "off", f"--root={root}"])
    assert rc == 0 and got["mode"] == "off" and "No pipeline is on" in got["text"] and started == []
    rc, got = run(["pipe", "mode", "live", f"--root={root}"])
    assert rc == 0 and got["mode"] == "live" and len(started) == 1              # on = working: the runner is started (it says `already` when one is)


@pytest.mark.parametrize("verb", ["payout", "profile", "settings", "mix", "portfolio"])
def test_the_retired_commands_are_gone(root, verb):
    rc, _ = TI._run(["pipe", verb, f"--root={root}"], "")
    assert rc != 0
