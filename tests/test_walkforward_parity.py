"""Pin: the walk-forward ratio refactor did not move a 1:3 number.

tests/fixtures/walkforward_1to3_pre_change.json is wf.compute() at the DEFAULT 1:3 on the
deterministic input in tests/wf_parity_util.py, captured by running that same input under the
pre-change commit bb7e6a5 (a scratch worktree). Every key the old result had must come back
identical; keys the rework ADDED (the IS side, per-month figures, the OOS trades, `uncovered`,
`ratio`) are ignored here and tested on their own."""
from __future__ import annotations

import json
from pathlib import Path

from homebase.backtest import walkforward as wf
from tests.wf_parity_util import CAPITAL, MONTHS, compute_input

FIX = json.loads((Path(__file__).parent / "fixtures" / "walkforward_1to3_pre_change.json").read_text())


def _old_shape(new, old):
    """`new` cut down to exactly the keys `old` has, recursively."""
    if isinstance(old, dict):
        return {k: _old_shape(new.get(k), v) for k, v in old.items()}
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        return [_old_shape(n, o) for n, o in zip(new, old)]
    return new


def test_a_1to3_walkforward_is_identical_to_the_pre_change_result():
    cells, trades_of = compute_input(wf)
    r = wf.compute(cells, MONTHS, trades_of=trades_of, metric="net_profit", min_trades=5, capital=CAPITAL)
    got = json.loads(json.dumps(_old_shape(r, FIX), sort_keys=True))
    assert got == FIX


def test_the_pin_is_a_real_walkforward():
    assert FIX["n_steps"] == 11 and FIX["scheme"]["test_months"] == 3
    assert FIX["stability"]["changes"] > 0 and FIX["stitched"]["stats"]["trades"] > 0
    assert FIX["skipped_by_error"] >= 0 and len(FIX["steps"]) == 11
