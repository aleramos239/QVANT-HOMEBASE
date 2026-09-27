"""Suite-wide: pin the backtest QUIET-window clock to a Monday noon ET, so tests that start runs
never fail for being executed between 09:20 and 09:35 ET on a weekday. A test that needs the
window injects its own clock (Slots(clock=...)) or re-patches slots.et_now."""
from __future__ import annotations

import datetime as dt

import pytest

from homebase.backtest import slots


@pytest.fixture(autouse=True)
def _outside_the_quiet_window(monkeypatch):
    monkeypatch.setattr(slots, "et_now", lambda: dt.datetime(2026, 9, 28, 12, 0, tzinfo=slots.ET))
