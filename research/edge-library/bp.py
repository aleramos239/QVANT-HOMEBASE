#!/usr/bin/env python3
"""bp.py -- the front door of the blueprint toolkit: BLUEPRINT.md section 2 (house law since 2026-10-05) as one saved tool.
Plan: out/blueprint/toolkit_plan.md. Code: blueprint/ (rules.py = every threshold as data, lines.py = one function per line,
runner.py = the one store runner of the build range, checks.py = the code check, records.py = the idea's record: its card,
its rounds, its status; jobs.py = long commands as jobs).
Python: "$HOME/ONYX TRADING/.venv/bin/python". The command line is the connector's: <command> <the idea's name> --opt=value.

  bp.py card <name> --spec=- | --spec=FILE                           PHASE 0: lines 0.1-0.6 off the idea card ({"name", "card",
                                                                     "run"} as JSON); saved in the app, with its Lab draft
  bp.py code-check <name> --store=KEY | --trades=FILE [--looked]     PHASE 1: lines 1.1-1.6 on a store or a trades file
  bp.py build <name> --reason=TEXT [--wait=S]                        PHASE 2, ONE ROUND of the idea on file, on the build range
                                                                     2021-09-22 .. 2025-06-30: the reason is saved first, what
                                                                     is missing is run, lines 2.1-2.9 are read and saved, the
                                                                     status follows (idea -> lead, or shelved after round 5)
  bp.py build <name> --reason=TEXT --spec-file=PATH                  the one-table build of a spec without a record (run_idea's
                                                                     format): nothing is saved, no round is counted
  bp.py build --stored <unit>              DRY RUN of lines 2.1-2.8 on the OLD build days (2021-09-22 .. 2023-12-31) for a unit
                                           whose stores are on disk; read-only; never a blueprint verdict
      e.g.  bp.py build --stored ib-NQ-tf15-mid:mode=break          bp.py build --stored 'orb-NQ-tf15|pre|' --json
  bp.py status [<name>]                    every idea on file, one line each -- or the full record of one
  bp.py job <id> [--wait=S]                keep waiting on a build that answered "running"
  bp.py pools [--roots=NQ,ES,GC] [--tf=1,5,15,30] [--workers=8]      the random-entry control pools of the build range (once)
  Every option: blueprint/cli.py. --json prints ONE JSON object (plan section 8). Exit: 0 = done (lines may still fail) ·
  2 = refused · 1 = crashed. Nothing here reads a day on or after 2025-07-01.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blueprint.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
