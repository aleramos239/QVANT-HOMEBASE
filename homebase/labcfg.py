"""Moved to homebase.desk.labcfg. This name is the SAME module object (sys.modules), so `homebase.labcfg`, a monkeypatch through
either name and `from homebase.labcfg import ...` all reach it."""
import sys

from .desk import labcfg as _moved

sys.modules[__name__] = _moved
