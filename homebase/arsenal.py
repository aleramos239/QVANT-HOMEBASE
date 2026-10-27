"""Moved to homebase.store.arsenal. This name is the SAME module object (sys.modules), so `homebase.arsenal`, a monkeypatch through
either name and `python -m homebase.arsenal` all reach it."""
import sys

if __name__ == "__main__":         # the command line, run as it was before the move
    import runpy

    runpy.run_module("homebase.store.arsenal", run_name="__main__")
else:
    from .store import arsenal as _moved

    sys.modules[__name__] = _moved
