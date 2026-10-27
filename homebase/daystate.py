"""Moved to homebase.desk.daystate. This name is the SAME module object (sys.modules), so `homebase.daystate`, a monkeypatch through
either name and `from homebase.daystate import ...` all reach it."""
import sys

from .desk import daystate as _moved

sys.modules[__name__] = _moved
