"""Moved to homebase.desk.timer. This name is the SAME module object (sys.modules), so `homebase.timer`, a monkeypatch through
either name and `from homebase.timer import ...` all reach it."""
import sys

from .desk import timer as _moved

sys.modules[__name__] = _moved
