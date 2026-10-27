"""charts/session.py and charts/tick.py are sys.modules aliases of homebase/core: one module object under both names, so a
monkeypatch through either name, `from homebase.charts.session import ...` (17 chart modules, tools/, research) and an
old pickle naming homebase.charts.tick all reach the same code. These aliases must never be deleted."""
import datetime as dt
import pickle
import subprocess
import sys
from pathlib import Path

import homebase.charts as charts
import homebase.charts.session as old_session
import homebase.charts.tick as old_tick
import homebase.core.session as session
import homebase.core.tick as tick


def test_the_old_names_are_the_same_module_objects():
    assert old_session is session and charts.session is session and sys.modules["homebase.charts.session"] is session
    assert old_tick is tick and charts.tick is tick and sys.modules["homebase.charts.tick"] is tick


def test_a_patch_through_the_old_name_reaches_the_moved_module(monkeypatch):
    monkeypatch.setattr("homebase.charts.session.ALWAYS_OPEN", frozenset({"NQ"}))
    assert session.always_open("NQ") and session.session_bounds(dt.date(2026, 10, 26), "NQ")[1].hour == 18


def test_an_old_pickle_of_a_tick_still_loads():
    t = tick.Tick(1, 2.0, 3, tick.BUY, 4)
    tick.Tick.__module__ = "homebase.charts.tick"           # what a process before the move wrote
    try:
        old = pickle.dumps(t)
    finally:
        tick.Tick.__module__ = "homebase.core.tick"
    assert b"homebase.charts.tick" in old and pickle.loads(old) == t and type(pickle.loads(old)) is tick.Tick


def test_the_old_name_imported_first_in_a_fresh_interpreter_is_the_same_module():
    code = ("import homebase.charts.session as a, homebase.charts.tick as b, homebase.core.session as c, homebase.core.tick as d; "
            "assert a is c and b is d")
    subprocess.run([sys.executable, "-c", code], check=True, cwd=Path(__file__).resolve().parent.parent, timeout=60)
