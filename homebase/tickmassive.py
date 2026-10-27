"""Moved to homebase.data.tickmassive. This name is the SAME module object (sys.modules), so `homebase.tickmassive`, a monkeypatch through
either name and `from homebase.tickmassive import ...` all reach it."""
import sys

from .data import tickmassive as _moved

sys.modules[__name__] = _moved
