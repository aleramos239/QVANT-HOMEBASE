"""pipe_switch.py -- THE SWITCH (the owner, 2026-10-13: "let me switch on and off each pipeline, so i can either have one on and i pick
which or none on"). ONE pipeline works, or none: `bp.py pipe mode [off | live | wr | payout | funded]`, and the Lab's Pipeline bar.

  CHOICES                     ("off", "live", "wr", "payout", "funded"): off, then the profiles of pipe_rules.PROFILES
  now(root=None) -> word      the one that is on, READ OFF THE DISK (this module keeps no file of its own):
                                the idea queue is paused -> "off"          else -> the profile in use (pipe_rules.active)
                              so a pause put by hand (`pipe pause`) reads "off", and a resume by hand reads the profile again
  choose(word, root=None) -> word
                              a profile   it is put in use (pipe_rules.use) and the queue is not paused
                              "off"       the queue is paused: the runner stops after the stage in hand. The profile stays as it was
                              A word that is none of them: judge.Refuse, and nothing is changed.
                              It starts nothing: `pipe mode` starts the runner for a profile (blueprint/cli.py).
  options(root=None) -> [{"id", "label", "short", "ready"}]     the choices, in the bar's order; ready False = it is disabled

THE LOCK (the owner, 2026-10-13: "add an option to disable it, if its disabled, it cant be used by me or claude until i renable it"). A
choice of LOCKED (the payout pipeline) is DISABLED unless its file is in the pipeline root: it cannot be chosen, its commands run
nothing (blueprint/cli.py), the runner does none of its work. No file = disabled: that is how it ships.
  enabled(word, root=None) -> bool        a choice without a lock is always enabled
  enable(word, on, root=None) -> bool     put the file or take it away. Taking it away while that pipeline is the one in use puts the
                                          LIVE profile back and pauses the queue: nothing is on.
                                          THE OWNER'S, from the Lab's Pipeline bar. No chat tool calls it and no assistant runs it.

ALL THREE PIPELINES ARE ONE RUNNER with another rules file (pipe_rules.PROFILES), which is why one is on at a time. The PAYOUT PIPELINE
(docs/superpowers/specs/2026-10-13-payout-pipeline-design.md) also builds the set for the funded accounts while its queue is idle
(pay_build, called by the runner). Standard library only. Locked by tests/test_pipe_switch.py.
"""
from __future__ import annotations

import judge as J

from . import pipe_rules as PR
from . import pipe_store as PS

OFF = "off"
LOCKED = {"payout": "payout_enabled"}               # a choice with a lock: the file in the pipeline root that says it is enabled
CHOICES = (OFF, *PR.PROFILES)
LABELS = {OFF: "Off", **{k: v[0] for k, v in PR.PROFILES.items()}}
SHORT = {OFF: "Off", "live": "Live", "wr": "WR", "payout": "Payout", "funded": "Funded"}          # the bar's buttons: its label already says Pipeline


def now(root=None) -> str:
    return OFF if PS.paused(PS.root(root)) else PR.active()


def enabled(word: str, root=None) -> bool:
    return word not in LOCKED or (PS.root(root) / LOCKED[word]).exists()


def enable(word: str, on: bool, root=None) -> bool:
    if word not in LOCKED:
        raise J.Refuse(f"{word!r} has no lock: only {', '.join(LOCKED)}")
    r = PS.root(root)
    r.mkdir(parents=True, exist_ok=True)
    if on:
        (r / LOCKED[word]).write_text("", encoding="utf-8")
    else:
        (r / LOCKED[word]).unlink(missing_ok=True)
        if PR.active() == word:                     # it was the one in use: nothing is on now
            PR.use("live")
            PS.pause(r)
    return enabled(word, r)


def options(root=None) -> list:
    return [{"id": k, "label": LABELS[k], "short": SHORT.get(k, LABELS[k]), "ready": enabled(k, root)} for k in CHOICES]


def choose(word, root=None) -> str:
    word = str(word).lower()
    if word not in CHOICES:
        raise J.Refuse(f"pipeline {word!r}: one of {', '.join(CHOICES)}")
    r = PS.root(root)
    if not enabled(word, r):
        raise J.Refuse(f"the {LABELS[word]} is disabled: the owner enables it in the Lab (the Pipeline bar). Nothing was changed")
    r.mkdir(parents=True, exist_ok=True)
    if word == OFF:
        PS.pause(r)
    else:
        PR.use(word)
        PS.resume(r)
    return now(r)


def said(word: str) -> str:
    """One sentence for a person: what is on."""
    return "No pipeline is on" if word == OFF else f"{LABELS[word]} is on"
