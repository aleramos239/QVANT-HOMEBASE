"""Moved to homebase.desk.desk_api. This name is the SAME module object (sys.modules), so `homebase.desk_api`, a monkeypatch through
either name and `from homebase.desk_api import ...` all reach it."""
import sys

from .desk import desk_api as _moved

sys.modules[__name__] = _moved
