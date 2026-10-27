"""Moved to homebase.data.marketdata. This name is the SAME module object (sys.modules), so `homebase.marketdata`, a monkeypatch through
either name and `from homebase.marketdata import ...` all reach it."""
import sys

from .data import marketdata as _moved

sys.modules[__name__] = _moved
