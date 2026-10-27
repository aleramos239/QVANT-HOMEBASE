"""Moved to homebase.desk.review. This name is the SAME module object (sys.modules), so `homebase.review`, a monkeypatch through
either name and `python -m homebase.review` all reach it."""
import sys

if __name__ == "__main__":         # the command line, run as it was before the move
    import runpy

    runpy.run_module("homebase.desk.review", run_name="__main__")
else:
    from .desk import review as _moved

    sys.modules[__name__] = _moved
