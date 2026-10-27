"""Moved to homebase.data.ticks. This name is the SAME module object (sys.modules), so `homebase.ticks`, a monkeypatch through
either name and `python -m homebase.ticks` all reach it."""
import sys

if __name__ == "__main__":         # the command line, run as it was before the move
    import runpy

    runpy.run_module("homebase.data.ticks", run_name="__main__")
else:
    from .data import ticks as _moved

    sys.modules[__name__] = _moved
