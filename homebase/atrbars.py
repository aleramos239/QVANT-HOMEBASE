"""Moved to homebase.data.atrbars. This name is the SAME module object (sys.modules), so `homebase.atrbars`, a monkeypatch through
either name and `from homebase.atrbars import ...` all reach it."""
import sys

from .data import atrbars as _moved

sys.modules[__name__] = _moved
