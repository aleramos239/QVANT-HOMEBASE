"""Moved to homebase.data.tickarchive. This name is the SAME module object (sys.modules), so `homebase.tickarchive`, a monkeypatch through
either name and `from homebase.tickarchive import ...` all reach it."""
import sys

from .data import tickarchive as _moved

sys.modules[__name__] = _moved
