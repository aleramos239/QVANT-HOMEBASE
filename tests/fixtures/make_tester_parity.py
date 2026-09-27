"""Regenerate the 2021-2024 parity fixture: `.venv/bin/python -m tests.fixtures.make_tester_parity`.

The fixture is the bundle a DEFAULT research-window run produced BEFORE the tester's range
rework (presets, no holdout guard, the walk-forward ratio). tests/test_tester_range_parity.py
rebuilds it and compares byte for byte, so none of that work may move a number. Regenerate it
only when a deliberate engine/report change is being pinned -- never to make the test pass.
"""
from __future__ import annotations

import json
from pathlib import Path

from tests.parity_util import parity_bundle

OUT = Path(__file__).parent / "tester_research_bundle.json"


def main() -> int:
    OUT.write_text(json.dumps(parity_bundle(), indent=1, sort_keys=True) + "\n")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
