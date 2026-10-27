"""Moved to homebase.desk.bothistory. This name is the SAME module object (sys.modules), so `homebase.bothistory`, a monkeypatch through
either name and `from homebase.bothistory import ...` all reach it."""
import sys

from .desk import bothistory as _moved

sys.modules[__name__] = _moved
