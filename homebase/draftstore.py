"""Moved to homebase.store.draftstore. This name is the SAME module object (sys.modules), so `homebase.draftstore`, a monkeypatch through
either name and `from homebase.draftstore import ...` all reach it."""
import sys

from .store import draftstore as _moved

sys.modules[__name__] = _moved
