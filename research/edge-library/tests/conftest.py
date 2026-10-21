"""conftest.py -- a test module with `PIPE_GATES = "law"` runs each of its tests against the pipeline rules file of mode "law" (pipe_law.file()),
whatever the shipped templates/pipeline.json says; every other module reads the shipped file. The file path and the loader's cache are put back
after each test."""
from __future__ import annotations

import os

import pytest

import pipe_law
from blueprint import pipe_rules as P


@pytest.fixture(autouse=True)
def _live_profile(monkeypatch, tmp_path):
    """Every test reads the LIVE PIPELINE (templates/pipeline.json) whatever profile the machine has chosen; a test of the WR PIPELINE sets HB_PIPELINE itself."""
    monkeypatch.setenv("HB_PIPELINE", "live")
    monkeypatch.setattr(P, "STATE", tmp_path / "pipeline_profile")
    P._all.cache_clear()
    yield
    P._all.cache_clear()


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


@pytest.fixture(autouse=True, scope="session")
def _old_route():
    """The old route's tests (build -> lock -> the one read, the early look) make their ideas and locks today: they stand for ideas of before
    ideastore.OLD_ROUTE_END (the owner, 2026-10-20), so they keep passing after that day. Temp idea folders only (ideastore.old_route).
    The new route's refusals are tested without it (engine/tests/test_hmwf.py)."""
    keep = os.environ.get("HOMEBASE_OLD_ROUTE_END")
    os.environ["HOMEBASE_OLD_ROUTE_END"] = "9999-12-31"
    yield
    if keep is None:
        os.environ.pop("HOMEBASE_OLD_ROUTE_END", None)
    else:
        os.environ["HOMEBASE_OLD_ROUTE_END"] = keep
