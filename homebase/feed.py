"""Moved to homebase.data.feed. This name is the SAME module object (sys.modules), so `homebase.feed`, a monkeypatch through
either name and `from homebase.feed import ...` all reach it."""
import sys

from .data import feed as _moved

sys.modules[__name__] = _moved
