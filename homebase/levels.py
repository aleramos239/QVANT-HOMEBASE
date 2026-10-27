"""Moved to homebase.desk.levels. This name is the SAME module object (sys.modules), so `homebase.levels`, a monkeypatch through
either name and `from homebase.levels import ...` all reach it."""
import sys

from .desk import levels as _moved

sys.modules[__name__] = _moved
