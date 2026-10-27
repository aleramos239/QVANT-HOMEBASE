"""Moved to homebase.store.secrets_store. This name is the SAME module object (sys.modules), so `homebase.secrets_store`, a monkeypatch through
either name and `python -m homebase.secrets_store` all reach it."""
import sys

if __name__ == "__main__":         # the command line, run as it was before the move
    import runpy

    runpy.run_module("homebase.store.secrets_store", run_name="__main__")
else:
    from .store import secrets_store as _moved

    sys.modules[__name__] = _moved
