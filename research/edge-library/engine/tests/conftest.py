"""Tests of the L2 pilot. Never write bytecode into the repo's homebase/ package (read-only for this pilot).

SCRATCH RULE: a test never writes to a shared, fixed location (several agents run this suite at the same time).
  tmp_path / tmp_path_factory   anything that may live outside the pilot directory
  l_tmp                         a directory of the test's own UNDER the pilot (l2sim.write_bundle refuses paths outside it)
  trades_tmp                    score.TRADES pointed at a directory of the module's own (R bundle exports, 'file:<name>' sources)
"""
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
L = Path(__file__).resolve().parent.parent          # the engine directory
W = L.parent                                         # the edge-library root (library.py, run_menus.py)
REPO = Path.home() / "ramos-quant-homebase"
for p in (str(W), str(L), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture
def l_tmp():
    """A scratch directory under L/out, unique to this test and this process, removed afterwards."""
    (L / "out").mkdir(exist_ok=True)
    d = Path(tempfile.mkdtemp(prefix="_pytest_", dir=L / "out"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(scope="module")
def trades_tmp(tmp_path_factory):
    """score.TRADES = a directory of this module's own while its tests run: exports of R bundles and 'file:<name>' sources
    never touch L/trades (shared with every other run of the suite)."""
    import score
    d = tmp_path_factory.mktemp("trades")
    old = score.TRADES
    score.TRADES = d
    try:
        yield d
    finally:
        score.TRADES = old
