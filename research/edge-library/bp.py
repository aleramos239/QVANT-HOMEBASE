#!/usr/bin/env python3
"""bp.py -- the front door of the blueprint toolkit: BLUEPRINT.md section 2 (house law since 2026-10-05) as one saved tool.
Plan: out/blueprint/toolkit_plan.md. Code: blueprint/ (rules.py = every threshold as data, lines.py = one function per line,
runner.py = the one store runner of the build range, checks.py = the code check, records.py = the idea's record: its card,
its rounds, its status; jobs.py = long commands as jobs).
Python: <repo>/.venv-research/bin/python (python3 -m venv .venv-research && pip install -r research/requirements-research.txt). The command line is the connector's: <command> <the idea's name> --opt=value.

  bp.py card <name> --spec=- | --spec=FILE                           PHASE 0: lines 0.1-0.7 off the idea card ({"name", "card",
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
  bp.py lock <name>                                                  PHASE 3, the freeze (blueprint/freeze.py): refused unless
                                                                     the latest round passes 2.1-2.9 and the code check of its
                                                                     home store is passed; the default variant = the middle of
                                                                     the variants that make money on build and on build with
                                                                     worse fills; lock.json under one hash, the test range frozen
  bp.py test <name> --confirm [--wait=S] [--second-look]             PHASE 4, THE ONE READ of the test days, 2025-07-01 on
                                                                     (blueprint/oos.py): the read is written to the one-read
                                                                     log FIRST, then lines 4.1-4.9. Refused when a read is on
                                                                     file for the idea or a same-idea relative; a fail is final
  bp.py test <name> --confirm --early-look                           AN EARLY LOOK at the test days, the owner's own ("warn,
                                                                     then run if I say yes"), for an idea that is NOT frozen:
                                                                     the same read, claimed the same way, labelled EARLY LOOK
                                                                     everywhere. It uses the test days up for the idea and can
                                                                     never prove it (kept in early_look/, not as its test.json)
  bp.py heatmap <name> [--place=home|1|2|..|not_here] [--round=N]    the HEAT MAP of a build round (blueprint/quick.py): every
                                                                     variant's net on the build days, value by exit cell, and
                                                                     what line 2.1 reads of it. Read-only: no round is counted
  bp.py mc <name> [--on=build|test]                                  the MONTE CARLO of an idea (blueprint/quick.py): line 2.8
                                                                     (or 4.7 on a test that is on file), then final net and
                                                                     worst drawdown of the 1,000 reshuffled runs. Read-only
  bp.py seed-reads [--dry-run]             the one-read log filled from the OLD read logs, once (blueprint/reads.py)
  bp.py sim <name> --account=ID --attempts=N --fee-budget=USD        PHASE 5, before the eval is bought (blueprint/propodds.py):
                                                                     the app's prop simulator on the test-period trades,
                                                                     OPEN LOSSES COUNTED; per pre-set size the odds of the
                                                                     eval within 10 trading days and of the maximum payout
                                                                     within 20, plain and "live is worse"; lines 5.1-5.4
  bp.py eval-card <name> [--fills=-|FILE]                            PHASE 6, the eval (blueprint/evalcard.py): lines 6.1-6.9
                                                                     and the drawdown table of its own test history; with
                                                                     the live fills, 6.1-6.5 are read (--help: the format)
  bp.py blocks                             everything an idea can be built from without writing code, and what version 1 refuses
  Every option: blueprint/cli.py. --json prints ONE JSON object (plan section 8). Exit: 0 = done (lines may still fail) ·
  2 = refused · 1 = crashed. No command reads a day on or after 2025-07-01 -- but `test`, once, for a frozen idea whose
  read is claimed in the one-read log (blueprint/runner.run_test: the one caller of the engine's switch for those days).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blueprint.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
