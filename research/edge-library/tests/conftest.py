"""conftest.py -- a test module with `PIPE_GATES = "law"` runs each of its tests against the pipeline rules file of mode "law" (pipe_law.file()),
whatever the shipped templates/pipeline.json says; every other module reads the shipped file. The file path and the loader's cache are put back
after each test."""
from __future__ import annotations

import pytest

import pipe_law
from blueprint import pipe_rules as P


@pytest.fixture(autouse=True)
def _pipeline_rules_file(request):
    if getattr(request.module, "PIPE_GATES", None) != "law":
        yield
        return
    keep = P.FILE
    P.FILE = pipe_law.file()
    P._all.cache_clear()
    try:
        yield
    finally:
        P.FILE = keep
        P._all.cache_clear()
