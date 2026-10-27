"""Moved to homebase.desk.engine_groups. This name is the SAME module object (sys.modules), so `homebase.engine_groups`, a monkeypatch through
either name and `from homebase.engine_groups import ...` all reach it."""
import sys

from .desk import engine_groups as _moved

sys.modules[__name__] = _moved
