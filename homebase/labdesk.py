"""Moved to homebase.desk.labdesk. This name is the SAME module object (sys.modules), so `homebase.labdesk`, a monkeypatch through
either name and `from homebase.labdesk import ...` all reach it."""
import sys

from .desk import labdesk as _moved

sys.modules[__name__] = _moved
