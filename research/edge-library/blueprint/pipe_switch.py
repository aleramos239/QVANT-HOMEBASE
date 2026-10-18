"""pipe_switch.py -- THE SWITCH: the pipeline works, or it does not: `bp.py pipe mode [off | live]`, and the Lab's Pipeline bar.
ONE pipeline since 2026-10-18 (the owner: the WR, PAYOUT and FUNDED pipelines are retired; docs/superpowers/specs/2026-10-18-one-pipeline-two-tags-design.md).

  CHOICES                     ("off", "live")
  now(root=None) -> word      READ OFF THE DISK: the idea queue is paused -> "off", else "live"
  choose(word, root=None) -> word
                              "live"  the queue is not paused        "off"  the queue is paused: the runner stops after the stage in hand
                              A word that is neither: judge.Refuse, and nothing is changed. It starts nothing: `pipe mode` starts the runner.
  options(root=None) -> [{"id", "label", "short", "ready"}]     the choices, in the bar's order
  enabled(word, root=None) -> True                              (no choice has a lock any more; kept for the callers)

The payout lock file (`payout_enabled`) is neither read nor written here: the PAYOUT PIPELINE it guarded is retired.
Standard library only. Locked by tests/test_pipe_switch.py.
"""
from __future__ import annotations

import judge as J

from . import pipe_rules as PR
from . import pipe_store as PS

OFF = "off"
CHOICES = (OFF, *PR.PROFILES)
LABELS = {OFF: "Off", **{k: v[0] for k, v in PR.PROFILES.items()}}
SHORT = {OFF: "Off", "live": "On"}                  # the bar's buttons: its label already says Pipeline


def now(root=None) -> str:
    return OFF if PS.paused(PS.root(root)) else PR.active()


def enabled(word: str, root=None) -> bool:
    return True


def options(root=None) -> list:
    return [{"id": k, "label": LABELS[k], "short": SHORT.get(k, LABELS[k]), "ready": enabled(k, root)} for k in CHOICES]


def choose(word, root=None) -> str:
    word = str(word).lower()
    if word not in CHOICES:
        raise J.Refuse(f"pipeline {word!r}: one of {', '.join(CHOICES)}")
    r = PS.root(root)
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
