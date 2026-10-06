"""The blueprint toolkit: BLUEPRINT.md section 2 (house law since 2026-10-05) as ONE saved tool, so that no chat rewrites test
code. Plan: out/blueprint/toolkit_plan.md. Front door: ../bp.py. judge.py stays the v2 judge; this package imports its functions.

  rules.py    the templates as data (templates/*.json): every threshold of the law, keyed by its line number
  lines.py    one small function per blueprint line: table data in -> {line, passed, number, need, text} out
  mc.py       the Monte Carlo of lines 2.8 and 4.7: whole days drawn with replacement, the same days for every variant
  tables.py   table data from the stores on disk, read-only, through the judge's own loaders and random-entry machinery
  api.py      each command as a function that returns a JSON-ready dict        cli.py    the command line of bp.py

Built so far (plan section 5, steps 1 and 2): the templates, lines 2.1-2.8, and `bp.py build --stored <unit>` = a DRY RUN of
those lines on the OLD build days (2021-09-22 .. 2023-12-31). A dry run is not a blueprint verdict.
"""
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[1]              # the edge-library root: judge.py, library.py and engine/ live here
for _p in (str(W), str(W / "engine")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
