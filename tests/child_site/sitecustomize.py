"""Loaded at start-up by the Python processes a test starts (conftest.py puts this folder on PYTHONPATH): a backtest
child sees the tests' nq930 twin (tests/straddle_twin.py) just as the test process does. Never on the app's path."""
try:
    from homebase import strategies
    from tests.straddle_twin import NQ930
    strategies.REGISTRY.setdefault("nq930", NQ930)
except Exception:          # a child that cannot import the repo (another cwd) just runs without the twin
    pass
