"""Moved to homebase.desk.engine_lab. This name is the SAME module object (sys.modules), so `homebase.engine_lab`, a monkeypatch through
either name and `from homebase.engine_lab import ...` all reach it."""
import sys

from .desk import engine_lab as _moved

sys.modules[__name__] = _moved
