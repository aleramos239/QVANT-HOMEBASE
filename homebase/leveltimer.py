"""Moved to homebase.desk.leveltimer. This name is the SAME module object (sys.modules), so `homebase.leveltimer`, a monkeypatch through
either name and `from homebase.leveltimer import ...` all reach it."""
import sys

from .desk import leveltimer as _moved

sys.modules[__name__] = _moved
