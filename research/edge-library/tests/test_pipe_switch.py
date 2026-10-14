"""LOCK of the switch (blueprint/pipe_switch.py; the owner, 2026-10-13: "let me switch on and off each pipeline, so i can either have one
on and i pick which or none on").

1. ONE pipeline works, or none: now() is read off the disk -- the queue's pause file and the profile in use.
2. choose() of a profile puts that profile in use and lets the queue work; "off" pauses it and keeps the profile; a word that is none
   is refused and nothing changes.
3. A pause put by hand (`pipe pause`) reads "off"; a resume by hand reads the profile again.
4. `pipe list` carries the choice and the choices; `pipe mode` shows it and chooses it, and starts the runner for a profile.
5. The PAYOUT PIPELINE is a profile: its rules ask one idea for money on the build days, never for eval odds of its own.
6. THE LOCK: the payout pipeline is DISABLED until the owner enables it -- it cannot be chosen and none of its commands runs; disabling
   it while it is the one in use leaves nothing on.
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
from blueprint import pipe_stages as ST  # noqa: E402
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
    SW.enable("payout", True, root)
    PS.pause(root)
    for word in ("wr", "payout", "live"):
        assert SW.choose(word, root) == word and PR.active() == word and not PS.paused(root)


def test_off_pauses_the_queue_and_keeps_the_profile(root):
    SW.enable("payout", True, root)
    SW.choose("payout", root)
    assert SW.choose("off", root) == "off" and PS.paused(root) and PR.active() == "payout"
    assert SW.choose("payout", root) == "payout" and not PS.paused(root)


def test_a_pause_by_hand_reads_off_and_a_resume_reads_the_profile(root):
    PS.pause(root)
    assert SW.now(root) == "off"
    PS.resume(root)
    assert SW.now(root) == "live"


def test_a_word_that_is_none_is_refused_and_nothing_changes(root):
    with pytest.raises(J.Refuse, match="off, live, wr, payout"):
        SW.choose("fast", root)
    assert SW.now(root) == "live" and not PS.paused(root)


def test_the_choices_are_off_and_the_profiles_in_the_bars_order(root):
    assert [(o["id"], o["short"]) for o in SW.options(root)] == [("off", "Off"), ("live", "Live"), ("wr", "WR"), ("payout", "Payout")]
    assert SW.said("off") == "No pipeline is on" and SW.said("payout") == "PAYOUT PIPELINE is on"


def test_the_payout_rules_ask_one_idea_for_money_never_for_eval_odds_of_its_own(root):
    SW.choose("live", root)
    PR._all.cache_clear()
    assert ST._eval_asked("some_idea_a5-NQ-tf5") is True
    SW.enable("payout", True, root)
    SW.choose("payout", root)
    PR._all.cache_clear()
    assert PR.gates() == "prop" and PR.winlane("some_idea_a5-NQ-tf5") == "label" and ST._eval_asked("some_idea_a5-NQ-tf5") is False


def test_pipe_list_carries_the_choice_and_the_choices(root):
    SW.choose("off", root)
    got = PRN.listing(root)["pipeline"]
    assert got["mode"] == "off" and [o["id"] for o in got["modes"]] == list(SW.CHOICES)


def test_pipe_mode_shows_and_chooses_and_starts_the_runner_for_a_profile(root, monkeypatch):
    started = []
    monkeypatch.setattr(PRN, "start", lambda r=None: started.append(r) or {"pid": 1, "already": False})
    rc, got = run(["pipe", "mode", f"--root={root}"])
    assert rc == 0 and got["mode"] == "live" and "LIVE PIPELINE is on" in got["text"] and started == []
    rc, got = run(["pipe", "mode", "off", f"--root={root}"])
    assert rc == 0 and got["mode"] == "off" and "No pipeline is on" in got["text"] and started == []
    rc, got = run(["pipe", "mode", "wr", f"--root={root}"])
    assert rc == 0 and got["mode"] == "wr" and len(started) == 1              # on = working: the runner is started (it says `already` when one is)


# ================================================================ 6. the lock

def test_the_payout_pipeline_is_disabled_until_the_owner_enables_it(root):
    assert SW.enabled("live", root) and not SW.enabled("payout", root)
    assert [o["ready"] for o in SW.options(root)] == [True, True, True, False]
    with pytest.raises(J.Refuse, match="disabled"):
        SW.choose("payout", root)
    assert SW.now(root) == "live" and not PS.paused(root) and PR.active() == "live"
    rc, got = run(["pipe", "mode", "payout", f"--root={root}"])
    assert "disabled" in json.dumps(got) and SW.now(root) == "live"
    assert SW.enable("payout", True, root) is True and SW.choose("payout", root) == "payout"
    with pytest.raises(J.Refuse, match="no lock"):
        SW.enable("live", False, root)


def test_disabling_it_while_it_is_in_use_leaves_nothing_on(root):
    SW.enable("payout", True, root)
    SW.choose("payout", root)
    assert SW.enable("payout", False, root) is False
    assert SW.now(root) == "off" and PS.paused(root) and PR.active() == "live"
    SW.choose("wr", root)
    assert SW.enable("payout", False, root) is False and SW.now(root) == "wr"       # another pipeline is in use: it is not touched


def test_disabled_none_of_its_commands_runs(root, monkeypatch):
    from blueprint import pay_build
    monkeypatch.setattr(pay_build, "command", lambda *a, **k: pytest.fail("the payout pipeline ran while disabled"))
    monkeypatch.setattr(pay_build, "requeue", lambda *a, **k: pytest.fail("the payout pipeline ran while disabled"))
    rc, got = run(["pipe", "payout", f"--root={root}"])
    assert rc == 0 and got["enabled"] is False and got["payout"] is None and got["text"] == "The PAYOUT PIPELINE is disabled."
    for what in ("build", "tonight", "requeue"):
        rc, got = run(["pipe", "payout", what, f"--root={root}"])
        assert got["ok"] is False and "disabled" in got["text"]
    rc, got = run(["pipe", "payout", "enable", f"--root={root}"])
    assert got["enabled"] is True and SW.enabled("payout", root)
    rc, got = run(["pipe", "payout", "disable", f"--root={root}"])
    assert got["enabled"] is False and not SW.enabled("payout", root)


def test_the_runner_does_none_of_its_work_while_it_is_disabled_or_another_pipeline_is_on(root, monkeypatch):
    from blueprint import pay_build
    calls = []
    monkeypatch.setattr(pay_build, "idle", lambda r=None: calls.append(r) or {"built": False, "evening": None})
    PRN._idle(root)                                   # live is on
    SW.enable("payout", True, root)
    PRN._idle(root)                                   # enabled, but live is still the one that is on
    SW.choose("payout", root)
    PRN._idle(root)
    assert calls == [root]
    SW.enable("payout", False, root)
    PRN._idle(root)
    assert calls == [root]
