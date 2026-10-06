"""The blueprint toolkit: BLUEPRINT.md section 2 (house law since 2026-10-05) as ONE saved tool, so that no chat rewrites test
code. Plan: out/blueprint/toolkit_plan.md. Front door: ../bp.py. judge.py stays the v2 judge; this package imports its functions.

  rules.py    the templates as data (templates/*.json): every threshold of the law, keyed by its line number
  lines.py    one small function per blueprint line: table data in -> {line, passed, number, need, text} out
  mc.py       the Monte Carlo of lines 2.8 and 4.7: whole days drawn with replacement, the same days for every variant
  tables.py   table data from the stores on disk, read-only, through the judge's own loaders and random-entry machinery
  runner.py   THE ONE STORE RUNNER of the build range (2021-09-22 .. 2025-06-30): an idea's table and its 10-seed control
              pool in one tape pass per market and bar size -> runs_bp/
  checks.py   the code check: lines 1.1-1.6 on a store or a plain trades file
  jobs.py     long commands as jobs: --wait, a detached child, `bp.py job <id>`
  api.py      each command as a function that returns a JSON-ready dict        cli.py    the command line of bp.py

Built so far (plan section 5): the templates (1), lines 2.1-2.8 and the dry run on stored units (2), the runner, the build on
the new range and the jobs (4), the code check (the toolkit half of 7). Next: the idea's card and rounds on file (5), lock
and test (8), sim (9), eval card (10).
"""
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[1]              # the edge-library root: judge.py, library.py and engine/ live here
for _p in (str(W), str(W / "engine")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
