"""Moved to homebase.desk.equity. This name is the SAME module object (sys.modules), so `homebase.equity`, a monkeypatch through
either name and `from homebase.equity import ...` all reach it."""
import sys

from .desk import equity as _moved

sys.modules[__name__] = _moved
