"""Suite-wide pins for the tester's machine-wide state:

  * HOMEBASE_TESTER_SHARED -> a fresh tmp dir per test, so no test ever touches the real
    per-machine ~/.homebase/tester (the backtest slots and looks.json); runner children
    started by a test inherit it through the environment;
  * the QUIET-window clock -> a Monday noon ET, so tests that start runs never fail for being
    executed between 09:20 and 09:35 ET on a weekday. A test that needs the window injects its
    own clock (Slots(clock=...)) or re-patches slots.et_now."""
from __future__ import annotations

import datetime as dt

import pytest

from homebase.backtest import slots


@pytest.fixture(autouse=True)
def tester_shared(tmp_path_factory, monkeypatch):
    d = tmp_path_factory.mktemp("tester-shared")
    monkeypatch.setenv("HOMEBASE_TESTER_SHARED", str(d))
    return d


@pytest.fixture(autouse=True)
def _outside_the_quiet_window(monkeypatch):
    monkeypatch.setattr(slots, "et_now", lambda: dt.datetime(2026, 9, 28, 12, 0, tzinfo=slots.ET))


@pytest.fixture(autouse=True)
def drafts_dir(tmp_path_factory, monkeypatch):
    """DRAFT strategies (homebase.draftstore): a fresh, empty tmp dir per test -- never ~/.homebase/strategies.
    Child processes (the draft host, runner exec) inherit it through the environment."""
    d = tmp_path_factory.mktemp("drafts")
    monkeypatch.setenv("HOMEBASE_DRAFTS_DIR", str(d))
    return d
