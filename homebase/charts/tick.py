"""Moved to homebase.core.tick (the tick record and the quote rule). This name is the SAME module object (sys.modules), so
`homebase.charts.tick`, a monkeypatch through either name and a pickle naming either path all resolve to it."""
import sys

from ..core import tick as _moved

sys.modules[__name__] = _moved
