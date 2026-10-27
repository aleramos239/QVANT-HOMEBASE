"""Moved to homebase.desk.trading. This name is the SAME module object (sys.modules), so `homebase.trading`, a monkeypatch through
either name and `from homebase.trading import ...` all reach it."""
import sys

from .desk import trading as _moved

sys.modules[__name__] = _moved
