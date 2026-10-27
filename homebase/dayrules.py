"""Moved to homebase.desk.dayrules. This name is the SAME module object (sys.modules), so `homebase.dayrules`, a monkeypatch through
either name and `from homebase.dayrules import ...` all reach it."""
import sys

from .desk import dayrules as _moved

sys.modules[__name__] = _moved
