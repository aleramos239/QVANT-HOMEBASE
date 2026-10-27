"""Moved to homebase.store.ideastore. This name is the SAME module object (sys.modules), so `homebase.ideastore`, a monkeypatch through
either name and `from homebase.ideastore import ...` all reach it."""
import sys

from .store import ideastore as _moved

sys.modules[__name__] = _moved
