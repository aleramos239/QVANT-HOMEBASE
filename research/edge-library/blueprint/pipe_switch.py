"""pipe_switch.py -- THE SWITCH (the owner, 2026-10-13: "let me switch on and off each pipeline, so i can either have one on and i pick
which or none on"). ONE pipeline works, or none: `bp.py pipe mode [off | live | wr | payout]`, and the Lab's Pipeline bar.

  CHOICES                     ("off", "live", "wr", "payout")
  now(root=None) -> word      the one that is on, READ OFF THE DISK (this module keeps one file of its own, the payout flag):
                                the idea queue is paused and the payout flag is there -> "payout"
                                the idea queue is paused                              -> "off"
                                else                                                  -> the profile in use (pipe_rules.active)
                              so a pause put by hand (`pipe pause`) reads "off", and a resume by hand reads the profile again
  choose(word, root=None) -> word
                              "live" | "wr"   the profile is put in use (pipe_rules.use), the payout flag goes, the queue is not paused
                              "off"           the queue is paused (the runner stops after the stage in hand), the payout flag goes
                              "payout"        the queue is paused and the payout flag is put -- REFUSED until its runner is built (READY)
                              A word that is none of the four, or one that is not ready: judge.Refuse, and nothing is changed.
                              It starts nothing: `pipe mode` starts the idea runner for a profile (blueprint/cli.py).
  options() -> [{"id", "label", "short", "ready"}]     the four, in the bar's order

THE PAYOUT PIPELINE (docs/superpowers/specs/2026-10-13-payout-pipeline-design.md) tunes and rotates a small set of session strategies
for the funded accounts. It is a runner of its own; while it works the idea queue is paused, which is why its flag counts only then.
Standard library only. Locked by tests/test_pipe_switch.py.
"""
from __future__ import annotations

import judge as J

from . import pipe_rules as PR
from . import pipe_store as PS

OFF, PAYOUT = "off", "payout"
CHOICES = (OFF, *PR.PROFILES, PAYOUT)
LABELS = {OFF: "Off", PAYOUT: "PAYOUT PIPELINE", **{k: v[0] for k, v in PR.PROFILES.items()}}
SHORT = {OFF: "Off", "live": "Live", "wr": "WR", PAYOUT: "Payout"}        # the bar's buttons: its label already says Pipeline
FLAG = "payout_on"                                  # in the pipeline root, beside the queue's pause file
READY = {PAYOUT: False}                             # a choice that cannot be made yet (its runner is not built): design step 3


def now(root=None) -> str:
    r = PS.root(root)
    if PS.paused(r):
        return PAYOUT if (r / FLAG).exists() else OFF
    return PR.active()


def options() -> list:
    return [{"id": k, "label": LABELS[k], "short": SHORT[k], "ready": READY.get(k, True)} for k in CHOICES]


def choose(word, root=None) -> str:
    word = str(word).lower()
    if word not in CHOICES:
        raise J.Refuse(f"pipeline {word!r}: one of {', '.join(CHOICES)}")
    if not READY.get(word, True):
        raise J.Refuse(f"the {LABELS[word]} is not built yet: it cannot be switched on. Nothing was changed")
    r = PS.root(root)
    r.mkdir(parents=True, exist_ok=True)
    if word in PR.PROFILES:
        PR.use(word)
        (r / FLAG).unlink(missing_ok=True)
        PS.resume(r)
    else:
        PS.pause(r)
        if word == PAYOUT:
            (r / FLAG).write_text("", encoding="utf-8")
        else:
            (r / FLAG).unlink(missing_ok=True)
    return now(r)


def said(word: str) -> str:
    """One sentence for a person: what is on."""
    return "No pipeline is on" if word == OFF else f"{LABELS[word]} is on"
