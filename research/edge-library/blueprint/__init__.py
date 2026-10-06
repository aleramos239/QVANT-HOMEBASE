"""The blueprint toolkit: BLUEPRINT.md section 2 (house law since 2026-10-05) as ONE saved tool, so that no chat rewrites test
code. Plan: out/blueprint/toolkit_plan.md. Front door: ../bp.py. judge.py stays the v2 judge; this package imports its functions.

  rules.py    the templates as data (templates/*.json): every threshold of the law, keyed by its line number
  lines.py    one small function per blueprint line: table data in -> {line, passed, number, need, text} out
  mc.py       the Monte Carlo of lines 2.8 and 4.7: whole days drawn with replacement, the same days for every variant
  tables.py   table data from the stores on disk, read-only, through the judge's own loaders and random-entry machinery
  runner.py   THE ONE STORE RUNNER of the build range (2021-09-22 .. 2025-06-30): an idea's table and its 10-seed control
              pool in one tape pass per market and bar size -> runs_bp/; the worse-fills table of the freeze; and run_test,
              THE ONLY CALLER of the engine's switch for the test days (for a read that is claimed) -> runs_bp_test/
  checks.py   the code check: lines 1.1-1.6 on a store or a plain trades file
  records.py  THE IDEA'S RECORD in the app's idea folder: the card (lines 0.1-0.6), the build with its counted rounds (the
              card names the tables; the reason is saved before the run; every line 2.1-2.9 is saved), the status
  jobs.py     long commands as jobs: --wait, a detached child, `bp.py job <id>`
  freeze.py   PHASE 3, `bp.py lock`: the worse-fills table of the build days, the default variant (the middle of the variants
              that make money on build and on build with worse fills), lock.json under one hash, the test range frozen
  oos.py      PHASE 4, `bp.py test`: THE ONE READ of the test days (2025-07-01 on) -- every refusal, the read claimed in
              the app's one-read log BEFORE the pass, lines 4.1-4.7, the verdict; a second look is labelled so everywhere
  reads.py    who has used the test days: the reads made before the blueprint (`bp.py seed-reads`), an idea's same-idea
              relatives (judge.same_idea)
  propodds.py PHASE 5, `bp.py sim`: the app's prop simulator on the test-period trades with the open-loss rule added -- the
              odds per pre-set size, plain and "live is worse"; lines 5.1-5.4
  evalcard.py PHASE 6, `bp.py eval-card`: the drawdown table of the variant's own test history, and lines 6.1-6.8 on the
              live fills of an eval
  blocklist.py  `bp.py blocks`: everything an idea can be built from without writing code, and what version 1 refuses
  api.py      each command as a function that returns a JSON-ready dict        cli.py    the command line of bp.py

Built so far (plan section 5): the templates (1), lines 2.1-2.8 and the dry run on stored units (2), the runner, the build on
the new range and the jobs (4), the idea's card, its rounds and its status on file (5, the toolkit half of 6), the code
check (the toolkit half of 7), the freeze, the one read of the test days and the one-read log (8), sim (9), eval card (10)
and the block list. (The cli imports propodds, evalcard and blocklist
only when a command line is read: the workers of a tape pass import cli.py and need none of them.)
"""
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[1]              # the edge-library root: judge.py, library.py and engine/ live here
for _p in (str(W), str(W / "engine")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
