"""mc.py -- the Monte Carlo of blueprint lines 2.8 (build) and 4.7 (test): the reshuffled runs of ONE table.

Reshuffled runs (montecarlo.json, quoted from BLUEPRINT.md section 2): 1,000 histories. A run draws as many WHOLE DAYS as the
range has, with replacement, and uses the same days for every variant, so the table keeps its own co-movement. reshuffle()
gives every variant's net and the table's trades in each run; the lines read them (lines.py):
  2.8   lines 2.1 and 2.2 are read again in every run: both must hold in 75 % of the runs or more
  4.7   the average variant makes money in 90 % of the runs or more
The math and the seed are those of out/blueprint/funnel.py and mc_gates.py (the evidence the lines rest on).
histories() gives the same runs day by day, for the view `bp.py mc` (quick.py: a run's worst drawdown); no line reads it.

THE SEED. Every table is reshuffled from a FRESH generator with the fixed seed: its number does not depend on what was judged
before it, and tables with the same number of days get the same draws (two rounds of one idea are read on the same histories).
funnel.py drew its 1,875 tables one after the other from ONE generator; `rng=` continues such a generator, and
tests/test_blueprint_lines.py reproduces funnel_units.csv with it exactly. A table's own number differs from its funnel number
by Monte Carlo noise only (the same test states how much).
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from . import rules as R


def generator() -> np.random.Generator:
    """A new generator with the fixed seed of montecarlo.json."""
    return np.random.default_rng(R.template("montecarlo")["seed"])


def draw(days: int, rng: np.random.Generator, runs: int) -> np.ndarray:
    """(days x runs): how many times each day is drawn in each run. A run = `days` draws of a whole day, with replacement."""
    return rng.multinomial(days, np.full(days, 1.0 / days), size=runs).T.astype(float)


@lru_cache(maxsize=8)
def _fixed(days: int, runs: int, seed: int) -> np.ndarray:
    """The draws of the fixed seed for a range of `days` days (the same for every table of that length; kept, read-only)."""
    w = draw(days, np.random.default_rng(seed), runs)
    w.setflags(write=False)
    return w


def reshuffle(net: np.ndarray, n: np.ndarray, rng: np.random.Generator | None = None) -> tuple:
    """net, n = (variants x days): net and trades of each variant on each session day. -> (variants x runs) the net of each
    variant in each reshuffled run, (runs,) the trades of all variants in each run. rng None = the fixed seed (module doc)."""
    mc = R.template("montecarlo")
    net, n = np.asarray(net, np.float64), np.asarray(n, np.float64)
    w = _fixed(net.shape[1], mc["runs"], mc["seed"]) if rng is None else draw(net.shape[1], rng, mc["runs"])
    with np.errstate(all="ignore"):                         # numpy 2.0 on macOS warns in matmul (funnel.py: checked against einsum)
        return net @ w, (n @ w).sum(0)


@lru_cache(maxsize=8)
def _order(days: int, runs: int, seed: int) -> np.ndarray:
    """(runs x days): THE SAME RUNS of the fixed seed AS HISTORIES -- the days of each run in an order. _fixed says how many
    times a run drew each day, and a drawdown also asks in which order. Of a draw with replacement every order is as likely
    as any other, so each run's days are put in a random order by a second generator of the same seed ([seed, 1]): the
    days, and so every total, stay those of the law's lines. Kept, read-only."""
    w = _fixed(days, runs, seed)
    seq = np.repeat(np.tile(np.arange(days), runs), w.T.astype(np.int64).ravel()).reshape(runs, days)
    seq = np.random.default_rng([seed, 1]).permuted(seq, axis=1)
    seq.setflags(write=False)
    return seq


def histories(net: np.ndarray) -> np.ndarray:
    """net = (variants x days) -> (variants x runs x days): each variant's net day by day through every reshuffled run of
    the fixed seed -- the runs of reshuffle(), the same days for every variant, in the order of _order. What `bp.py mc`
    reads a run's worst drawdown on (quick.py); a run's last total is reshuffle()'s."""
    mc = R.template("montecarlo")
    net = np.asarray(net, np.float64)
    return net[:, _order(net.shape[1], mc["runs"], mc["seed"])]
