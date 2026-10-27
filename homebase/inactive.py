"""Moved to homebase.desk.inactive. This name is the SAME module object (sys.modules), so `homebase.inactive`, a monkeypatch through
either name and `from homebase.inactive import ...` all reach it."""
import sys

from .desk import inactive as _moved

sys.modules[__name__] = _moved
