"""Moved to homebase.desk.metrics. This name is the SAME module object (sys.modules), so `homebase.metrics`, a monkeypatch through
either name and `from homebase.metrics import ...` all reach it."""
import sys

from .desk import metrics as _moved

sys.modules[__name__] = _moved
