#!/usr/bin/env python3
"""bp.py -- the front door of the blueprint toolkit: BLUEPRINT.md section 2 (house law since 2026-10-05) as one saved tool.
Plan: out/blueprint/toolkit_plan.md. Code: blueprint/ (rules.py = every threshold as data, lines.py = one function per line).
Python: "$HOME/ONYX TRADING/.venv/bin/python".

  bp.py build --stored <unit> [--json]     DRY RUN of lines 2.1-2.8 on the OLD build days (2021-09-22 .. 2023-12-31) for a unit
                                           whose stores are on disk; read-only; never a blueprint verdict
      e.g.  bp.py build --stored ib-NQ-tf15-mid:mode=break          bp.py build --stored 'orb-NQ-tf15|pre|' --json
  --json prints ONE JSON object (plan section 8). Exit: 0 = done (lines may still fail) · 2 = refused · 1 = crashed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blueprint.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
