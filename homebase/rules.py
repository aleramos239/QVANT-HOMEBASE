"""Moved to homebase.desk.rules. This name is the SAME module object (sys.modules), so `homebase.rules`, a monkeypatch through
either name and `from homebase.rules import ...` all reach it."""
import sys

from .desk import rules as _moved

sys.modules[__name__] = _moved
