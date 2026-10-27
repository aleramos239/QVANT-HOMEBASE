"""Moved to homebase.data.datawatch. This name is the SAME module object (sys.modules), so `homebase.datawatch`, a monkeypatch through
either name and `from homebase.datawatch import ...` all reach it."""
import sys

from .data import datawatch as _moved

sys.modules[__name__] = _moved
