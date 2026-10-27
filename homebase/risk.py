"""Moved to homebase.desk.risk. This name is the SAME module object (sys.modules), so `homebase.risk`, a monkeypatch through
either name and `from homebase.risk import ...` all reach it."""
import sys

from .desk import risk as _moved

sys.modules[__name__] = _moved
