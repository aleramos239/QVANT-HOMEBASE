"""THE pin for the tester's range rework: a 2021-2024 run's numbers must not move.

Removing the 2025+ holdout guard, replacing the range control with presets and making the
walk-forward ratio selectable all touch the path a run's range travels. None of it may change
what a run produces. This rebuilds the DEFAULT research-window run over the synthetic
multi-year archive and compares the whole bundle -- run.json (report, coverage, meta),
trades.json, equity.json, plots.json -- byte for byte against the fixture captured from the
code before the rework (tests/fixtures/make_tester_parity.py regenerates it).

If this fails, a number moved. Regenerate the fixture only for a change that is meant to
move numbers, never to make this pass.
"""
from __future__ import annotations

import json
from pathlib import Path

from tests.parity_util import parity_bundle

FIX = Path(__file__).parent / "fixtures" / "tester_research_bundle.json"


def _canon(b: dict) -> str:
    return json.dumps(b, indent=1, sort_keys=True) + "\n"


def test_a_2021_2024_run_is_byte_identical_to_the_pinned_bundle():
    got, want = _canon(parity_bundle()), FIX.read_text()
    if got != want:                       # a readable first difference before the byte assert
        g, w = json.loads(got), json.loads(want)
        assert g["run"]["report"] == w["run"]["report"], "the report moved"
        assert g["run"]["coverage"] == w["run"]["coverage"], "the coverage moved"
        assert g["trades"] == w["trades"], "the trades moved"
    assert got == want


def test_the_pinned_bundle_is_the_research_window_and_has_real_numbers():
    """A parity pin over an empty run would pass forever: hold the fixture to a real
    research-range run with winners, losers and a coverage hole."""
    b = json.loads(FIX.read_text())
    rng, cov = b["run"]["range"], b["run"]["coverage"]
    assert (rng["kind"], rng["start"], rng["end"]) == ("research", "2021-01-01", "2024-12-31")
    assert cov["sessions"] == 12 and cov["used"] == 10 and len(cov["skipped"]) == 2
    s = b["run"]["report"]["summary"]["all"]
    assert s["trades"] == 8 and s["wins"] == 4 and s["losses"] == 4
    assert {t["date"][:4] for t in b["trades"]} == {"2021", "2022", "2023", "2024"}
