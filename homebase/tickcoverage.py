"""Moved to homebase.data.tickcoverage. This name is the SAME module object (sys.modules), so `homebase.tickcoverage`, a monkeypatch through
either name and `from homebase.tickcoverage import ...` all reach it."""
import sys

from .data import tickcoverage as _moved

sys.modules[__name__] = _moved
